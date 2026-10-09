"""ZIVPN adapter (UDP).

Auth: the upstream binary (zahidbd2/udp-zivpn 1.4.9, a Hysteria-v1 fork) supports modes
``passwords`` / ``userpass`` / ``http`` / ``command``. We use ``http``: the server POSTs
``{"addr","auth","tx"}`` to scripts/zivpn-auth.py on every connection, which checks the panel DB
(read-only) and answers ``{"ok","id"}``. That is what makes expiry, disable and max-connections
work for ZIVPN - the static ``passwords`` mode cannot. The endpoint runs as the loopback-only
``unified-zivpn-auth.service`` managed by this adapter.

Before installing you must audit your chosen upstream (license, release, config schema) and write
/opt/unified-vpn/config/zivpn.json:

{
  "binary_url":    "https://.../zivpn-linux-amd64",      # required
  "sha256":        "<64 hex>",                           # required - install refuses without it
  "binary_path":   "/usr/local/bin/zivpn",
  "exec_args":     "server -c /etc/zivpn/config.json",
  "listen_port":   5667,
  "obfs":          "hu``hqb`c",
  "port_range":    "6000:19999",   # optional: DNAT incoming UDP range -> listen_port ("" disables)
  "auth_port":     18099,          # optional: loopback port of this adapter's HTTP auth service
  "config_template": { ... }   # optional: full config JSON. "@PASSWORDS@" expands to the list of
                               # each user's chosen password (static mode); "@AUTH_PORT@" to auth_port.
}

The DEFAULT_TEMPLATE below uses the verified ``http`` auth schema.
"""
import hashlib
import json
import os
import shutil
import socket

from backend import config, db, servicemgr, shell
from adapters.base import Adapter, AdapterError, apt_install, listening, port_free, write_file

AUTH_UNIT = "unified-zivpn-auth.service"
DEFAULT_AUTH_PORT = 18099

DEFAULT_TEMPLATE = {
    "listen": ":@PORT@",
    "cert": "@ETC@/zivpn/zivpn.crt",
    "key": "@ETC@/zivpn/zivpn.key",
    "obfs": "@OBFS@",
    "auth": {"mode": "http", "http": {"url": "http://127.0.0.1:@AUTH_PORT@/auth"}},
}

NAT_UNIT = "unified-zivpn-nat.service"


def _nat_unit_text(port, prange):
    return """[Unit]
Description=Unified VPN - ZIVPN UDP port-range DNAT
After=network-online.target
Before=zivpn.service

[Service]
Type=oneshot
RemainAfterExit=yes
Environment=ZIVPN_PORT=%s ZIVPN_RANGE=%s
ExecStart=%s/zivpn-nat.sh up
ExecStop=%s/zivpn-nat.sh down

[Install]
WantedBy=multi-user.target
""" % (port, prange, config.SCRIPTS_DIR, config.SCRIPTS_DIR)


def _auth_unit_text(s):
    log = _log_path(s)
    return """[Unit]
Description=Unified VPN - ZIVPN HTTP auth (loopback)
After=network.target

[Service]
ExecStart=%s %s/zivpn-auth.py
Environment=UVPN_HOME=%s UVPN_DB=%s UVPN_DATA=%s ZIVPN_AUTH_PORT=%s ZIVPN_LOG=%s
Restart=always
RestartSec=3
NoNewPrivileges=yes
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
""" % (config.PY, config.SCRIPTS_DIR, config.HOME, config.DB_PATH, config.DATA, s["auth_port"], log)


def _log_path(s):
    return os.path.join(config.VARLOG, "unified-vpn/zivpn.log")


class ZivpnAdapter(Adapter):
    name = "zivpn"
    label = "ZIVPN (UDP)"
    protocols = ("zivpn",)
    declarative = True

    @property
    def services(self):
        return ("zivpn.service", AUTH_UNIT)

    def _settings(self):
        path = os.path.join(config.CONF_DIR, "zivpn.json")
        try:
            with open(path) as fh:
                s = json.load(fh)
        except (IOError, OSError, ValueError):
            raise AdapterError("missing/invalid %s - audit your ZIVPN upstream first (see adapters/zivpn/__init__.py)" % path)
        s.setdefault("binary_path", "/usr/local/bin/zivpn")
        s.setdefault("exec_args", "server -c %s/zivpn/config.json" % config.ETC)
        s.setdefault("listen_port", 5667)
        s.setdefault("obfs", "hu``hqb`c")
        s.setdefault("port_range", "6000:19999")
        s.setdefault("auth_port", DEFAULT_AUTH_PORT)
        return s

    @property
    def conf_path(self):
        return os.path.join(config.ETC, "zivpn/config.json")

    # ---- install ---------------------------------------------------------------------------
    def install(self, opts=None):
        s = self._settings()
        if not s.get("binary_url") or not s.get("sha256"):
            raise AdapterError("zivpn.json needs binary_url and sha256 (no unverified binaries)")
        if not port_free("udp", s["listen_port"]):
            raise AdapterError("udp/%s already in use" % s["listen_port"])
        apt_install("openssl", "curl", "iptables")
        if not config.DRY_RUN:
            tmp = s["binary_path"] + ".download"
            shell.run(["curl", "-fsSL", "-o", tmp, s["binary_url"]], timeout=300, check=True)
            got = hashlib.sha256(open(tmp, "rb").read()).hexdigest()
            if got.lower() != s["sha256"].lower():
                os.remove(tmp)
                raise AdapterError("SHA256 mismatch for ZIVPN binary - aborting")
            os.chmod(tmp, 0o755)
            os.replace(tmp, s["binary_path"])
        zdir = os.path.join(config.ETC, "zivpn")
        os.makedirs(zdir, exist_ok=True)
        if not os.path.exists(os.path.join(zdir, "zivpn.key")):
            shell.run(["openssl", "req", "-new", "-newkey", "rsa:2048", "-days", "3650", "-nodes", "-x509",
                       "-subj", "/CN=zivpn", "-keyout", os.path.join(zdir, "zivpn.key"),
                       "-out", os.path.join(zdir, "zivpn.crt")], check=True)
            if not config.DRY_RUN:
                os.chmod(os.path.join(zdir, "zivpn.key"), 0o600)
        log = _log_path(s)
        os.makedirs(os.path.dirname(log), exist_ok=True)
        write_file(os.path.join(config.SYSTEMD_DIR, AUTH_UNIT), _auth_unit_text(s))
        shell.run(["systemctl", "daemon-reload"], check=True)
        shell.run(["systemctl", "enable", "--now", AUTH_UNIT], check=True)
        unit = """[Unit]
Description=ZIVPN UDP (Unified VPN)
After=network.target %s

[Service]
ExecStart=%s %s
WorkingDirectory=%s
Restart=always
RestartSec=3
LimitNOFILE=65535
StandardOutput=append:%s
StandardError=append:%s

[Install]
WantedBy=multi-user.target
""" % (AUTH_UNIT, s["binary_path"], s["exec_args"], zdir, log, log)
        write_file(os.path.join(config.SYSTEMD_DIR, "zivpn.service"), unit)
        self._render(force=True, restart=False)
        shell.run(["systemctl", "daemon-reload"], check=True)
        shell.run(["systemctl", "enable", "--now", "zivpn.service"], check=True)
        self._ensure_nat(s)
        self.mark_installed({"port": s["listen_port"], "port_range": s.get("port_range", ""),
                             "auth_port": s["auth_port"]})

    def uninstall(self):
        self._remove_nat()
        for u in ("zivpn.service", AUTH_UNIT):
            shell.run(["systemctl", "disable", "--now", u])
            p = os.path.join(config.SYSTEMD_DIR, u)
            if os.path.exists(p):
                os.remove(p)
        shell.run(["systemctl", "daemon-reload"])
        self.unmark_installed()

    # ---- rendering ---------------------------------------------------------------------------
    @staticmethod
    def _pw(account):
        """ZIVPN password = the password the admin chose for the user (falls back to the
        auto-generated secret for accounts created before this behaviour)."""
        return (account.get("config") or {}).get("password") or account["secret"]

    def build_config(self, accounts, s):
        tpl = s.get("config_template") or DEFAULT_TEMPLATE
        pw = [self._pw(a) for a in accounts]

        def sub(v):
            if isinstance(v, str):
                if v == "@PASSWORDS@":
                    return pw if pw else [self._placeholder()]
                return (v.replace("@PORT@", str(s["listen_port"])).replace("@OBFS@", s["obfs"])
                        .replace("@ETC@", config.ETC).replace("@AUTH_PORT@", str(s["auth_port"])))
            if isinstance(v, dict):
                return dict((k, sub(x)) for k, x in v.items())
            if isinstance(v, list):
                return [sub(x) for x in v]
            return v
        return sub(tpl)

    def _placeholder(self):
        """Stable unguessable password used when there are no users (an empty list may break some builds)."""
        path = os.path.join(config.CONF_DIR, "zivpn.placeholder")
        try:
            return open(path).read().strip()
        except (IOError, OSError):
            val = hashlib.sha256(os.urandom(32)).hexdigest()
            write_file(path, val + "\n", 0o600)
            return val

    def _render(self, force=False, restart=True):
        s = self._settings()
        conn = db.connect()
        try:
            accounts = db.active_accounts(conn, ("zivpn",))
        finally:
            conn.close()
        cfg = self.build_config(accounts, s)
        text = json.dumps(cfg, indent=2, sort_keys=True) + "\n"
        try:
            if not force and open(self.conf_path).read() == text:
                return False
        except (IOError, OSError):
            pass
        json.loads(text)                                      # validation: must be well-formed JSON
        if os.path.exists(self.conf_path):
            shutil.copy2(self.conf_path, self.conf_path + ".bak")
        write_file(self.conf_path, text, 0o600)
        if restart:
            shell.run(["systemctl", "restart", "zivpn.service"], check=True)
        return True

    def _ensure_fw(self, s):
        """Open UDP in UFW when it is active. The DNAT rewrites the range to listen_port in
        PREROUTING, so the filter stage sees the rewritten port - allow both the direct port and
        the range, otherwise the service is unreachable even though it is listening."""
        if config.DRY_RUN or not shutil.which("ufw"):
            return
        try:
            status = shell.run(["ufw", "status"]).out or ""
        except Exception:
            return
        if "Status: active" not in status:
            return
        shell.run(["ufw", "allow", "%s/udp" % s["listen_port"]])
        prange = str(s.get("port_range") or "").strip()
        if prange:
            shell.run(["ufw", "allow", "%s/udp" % prange])

    def _ensure_nat(self, s):
        """Enable UDP port-range DNAT (6000:19999 -> listen_port) when port_range is set."""
        prange = str(s.get("port_range") or "").strip()
        path = os.path.join(config.SYSTEMD_DIR, NAT_UNIT)
        if not prange:
            self._remove_nat()
            self._ensure_fw(s)
            return
        changed = write_file(path, _nat_unit_text(s["listen_port"], prange))
        if changed:
            shell.run(["systemctl", "daemon-reload"])
        if changed or servicemgr.unit_state(NAT_UNIT) != "RUNNING":
            shell.run(["systemctl", "enable", "--now", NAT_UNIT])
        self._ensure_fw(s)

    def _remove_nat(self):
        path = os.path.join(config.SYSTEMD_DIR, NAT_UNIT)
        if os.path.exists(path):
            shell.run(["systemctl", "disable", "--now", NAT_UNIT])
            os.remove(path)
            shell.run(["systemctl", "daemon-reload"])

    def sync(self):
        if self.installed():
            self._render()
            self._ensure_nat(self._settings())

    def create_user(self, user, account):
        return {"password": user["password"]} if user.get("password") else {}

    def delete_user(self, user, account):
        pass

    def list_users(self):
        conn = db.connect()
        try:
            return sorted(a["username"] for a in db.active_accounts(conn, ("zivpn",)))
        finally:
            conn.close()

    def share(self, user, account, hostinfo):
        s = self._settings()
        info = {"server": hostinfo["host"], "port": s["listen_port"], "obfs": s["obfs"],
                "password": self._pw(account), "note": "enter these in the ZIVPN client app"}
        if s.get("port_range"):
            info["port_range"] = s["port_range"]
        return {"links": [], "files": [], "info": info}

    def online(self):
        """{username: connection_count} as tracked by the HTTP auth service (zivpn-online.json)."""
        try:
            with open(os.path.join(config.DATA, "zivpn-online.json")) as fh:
                d = json.load(fh)
        except (IOError, OSError, ValueError):
            return {}
        out = {}
        for name, n in d.items():
            try:
                n = int(n)
            except (TypeError, ValueError):
                continue
            if n > 0:
                out[name] = n
        return out

    def _auth_reachable(self, s):
        if config.DRY_RUN:
            return True
        try:
            with socket.create_connection(("127.0.0.1", int(s["auth_port"])), timeout=2):
                return True
        except OSError:
            return False

    def info(self):
        try:
            s = self._settings()
            return {"port": s["listen_port"], "obfs": s["obfs"], "port_range": s.get("port_range", ""),
                    "auth": "http (DB-backed)", "auth_port": s["auth_port"]}
        except AdapterError:
            return {"configured": False}

    def health(self):
        try:
            s = self._settings()
        except AdapterError as e:
            return [("zivpn.json present", False, str(e))]
        res = [("zivpn binary exists", os.path.exists(s["binary_path"]) or config.DRY_RUN, ""),
               ("zivpn auth script present",
                os.path.exists(os.path.join(config.SCRIPTS_DIR, "zivpn-auth.py")) or config.DRY_RUN, "")]
        ok = True
        try:
            json.load(open(self.conf_path))
        except (IOError, OSError, ValueError):
            ok = config.DRY_RUN
        res.append(("zivpn config valid JSON", ok, ""))
        res.append(("zivpn auth service active", servicemgr.unit_state(AUTH_UNIT) in ("RUNNING", "UNKNOWN"), ""))
        res.append(("zivpn auth endpoint reachable", self._auth_reachable(s), "127.0.0.1:%s" % s["auth_port"]))
        res.append(("zivpn service active", servicemgr.unit_state("zivpn.service") in ("RUNNING", "UNKNOWN"), ""))
        res.append(("zivpn udp port listening", listening("udp", s["listen_port"]), ""))
        if s.get("port_range"):
            res.append(("zivpn port-range DNAT active", servicemgr.unit_state(NAT_UNIT) in ("RUNNING", "UNKNOWN"), ""))
        return res
