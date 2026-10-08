"""ZIVPN adapter (UDP).

!! UPSTREAM NOT AUDITED !!  Plan section 9/36/50: do not assume any repo's script/config format.
This adapter is therefore config-driven. Before installing you must audit your chosen upstream
(license, release, config schema) and write /opt/unified-vpn/config/zivpn.json:

{
  "binary_url":    "https://.../zivpn-linux-amd64",      # required
  "sha256":        "<64 hex>",                           # required - install refuses without it
  "binary_path":   "/usr/local/bin/zivpn",
  "exec_args":     "server -c /etc/zivpn/config.json",
  "listen_port":   5667,
  "obfs":          "zivpn",
  "config_template": { ... }   # optional: full config JSON; "@PASSWORDS@" is replaced by the list of
                               # each user's chosen password (NOT a random secret)
}

The DEFAULT_TEMPLATE below follows the layout used by common community builds and MUST be verified
against the upstream you pick.
"""
import hashlib
import json
import os
import shutil

from backend import config, db, servicemgr, shell
from adapters.base import Adapter, AdapterError, apt_install, listening, port_free, write_file

DEFAULT_TEMPLATE = {
    "listen": ":@PORT@",
    "cert": "@ETC@/zivpn/zivpn.crt",
    "key": "@ETC@/zivpn/zivpn.key",
    "obfs": "@OBFS@",
    "auth": {"mode": "passwords", "config": "@PASSWORDS@"},
}


class ZivpnAdapter(Adapter):
    name = "zivpn"
    label = "ZIVPN (UDP)"
    protocols = ("zivpn",)
    declarative = True

    @property
    def services(self):
        return ("zivpn.service",)

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
        s.setdefault("obfs", "zivpn")
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
        apt_install("openssl", "curl")
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
        unit = """[Unit]
Description=ZIVPN UDP (Unified VPN)
After=network.target

[Service]
ExecStart=%s %s
WorkingDirectory=%s
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
""" % (s["binary_path"], s["exec_args"], zdir)
        write_file(os.path.join(config.SYSTEMD_DIR, "zivpn.service"), unit)
        self._render(force=True, restart=False)
        shell.run(["systemctl", "daemon-reload"], check=True)
        shell.run(["systemctl", "enable", "--now", "zivpn.service"], check=True)
        self.mark_installed({"port": s["listen_port"]})

    def uninstall(self):
        shell.run(["systemctl", "disable", "--now", "zivpn.service"])
        p = os.path.join(config.SYSTEMD_DIR, "zivpn.service")
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
                return v.replace("@PORT@", str(s["listen_port"])).replace("@OBFS@", s["obfs"]).replace("@ETC@", config.ETC)
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

    def sync(self):
        if self.installed():
            self._render()

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
        return {"links": [], "files": [], "info": {
            "server": hostinfo["host"], "port": s["listen_port"], "obfs": s["obfs"],
            "password": self._pw(account), "note": "enter these in the ZIVPN client app"}}

    def info(self):
        try:
            s = self._settings()
            return {"port": s["listen_port"], "obfs": s["obfs"]}
        except AdapterError:
            return {"configured": False}

    def health(self):
        try:
            s = self._settings()
        except AdapterError as e:
            return [("zivpn.json present", False, str(e))]
        res = [("zivpn binary exists", os.path.exists(s["binary_path"]) or config.DRY_RUN, "")]
        ok = True
        try:
            json.load(open(self.conf_path))
        except (IOError, OSError, ValueError):
            ok = config.DRY_RUN
        res.append(("zivpn config valid JSON", ok, ""))
        res.append(("zivpn service active", servicemgr.unit_state("zivpn.service") in ("RUNNING", "UNKNOWN"), ""))
        res.append(("zivpn udp port listening", listening("udp", s["listen_port"]), ""))
        return res
