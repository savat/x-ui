"""Hysteria 1 adapter (UDP/QUIC). Declarative config, but auth is checked per-connection against the DB.

Hysteria 1 is the first generation of apernet/hysteria (end-of-life upstream; last release v1.3.5).
It has no built-in userpass, so we use its "external" HTTP auth mode: on every connection the server
POSTs ``{"addr","payload","send","recv"}`` (payload = base64 of what the client sent) to
``scripts/hysteria1-auth.py``, which checks the panel DB (read-only) and answers ``{"ok","msg"}``.
That is what makes expiry, disable and max-connections work for Hysteria 1.

Connection tracking: the auth service registers the addr on a successful auth and removes it when the
server logs ``Client disconnected`` for the same ``src`` addr; the unit redirects the server output to
a log file for this (Hysteria 1's only connection gauge, ``hysteria_active_conn``, counts live streams,
not connections, so it cannot be used). Counts are mirrored to ``UVPN_DATA/hysteria1-online.json``.

Binary: GitHub release of apernet/hysteria tag v1.3.5, verified against the release hashes.txt
(install aborts otherwise). Listens on UDP 36712 (Hysteria 2 uses 443; nginx TCP 443 - no conflict).
Runs as root only because it must read the TLS private key; the unit is sandboxed.
"""
import json
import os
import platform
import re
import shutil
import tempfile
import time
from urllib.parse import quote, urlencode

from backend import config, db, servicemgr, shell
from adapters.base import Adapter, AdapterError, listening, port_free, write_file

PORT = 36712
AUTH_PORT = 18100
VERSION = "1.3.5"
DEFAULT_OBFS = "opo"
APP_VERSION = "20.6"
UNIT = "unified-hysteria1.service"
AUTH_UNIT = "unified-hysteria1-auth.service"
ARCH = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}


def _log_path():
    return os.path.join(config.VARLOG, "unified-vpn/hysteria1.log")


def _auth_unit_text():
    return """[Unit]
Description=Unified VPN - Hysteria 1 external auth (loopback)
After=network.target

[Service]
ExecStart=%s %s/hysteria1-auth.py
Environment=UVPN_HOME=%s UVPN_DB=%s UVPN_DATA=%s HYSTERIA1_AUTH_PORT=%d HYSTERIA1_LOG=%s
Restart=always
RestartSec=3
NoNewPrivileges=yes
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
""" % (config.PY, config.SCRIPTS_DIR, config.HOME, config.DB_PATH, config.DATA, AUTH_PORT, _log_path())


class Hysteria1Adapter(Adapter):
    name = "hysteria1"
    label = "Hysteria 1 (UDP)"
    protocols = ("hysteria1",)
    declarative = True

    @property
    def services(self):
        return (UNIT, AUTH_UNIT)

    @property
    def binary(self):
        return os.path.join(config.HOME, "hysteria1/hysteria")

    @property
    def conf_path(self):
        return os.path.join(config.ETC, "hysteria1/config.json")

    def _download(self, version):
        import urllib.request
        arch = ARCH.get(platform.machine())
        if not arch:
            raise AdapterError("unsupported architecture %s" % platform.machine())
        tag = version if version.startswith("v") else "v" + version
        api = "https://api.github.com/repos/apernet/hysteria/releases/tags/" + tag
        with urllib.request.urlopen(api, timeout=20) as r:
            rel = json.load(r)
        assets = dict((a["name"], a["browser_download_url"]) for a in rel["assets"])
        want = "hysteria-linux-%s" % arch
        if want not in assets or "hashes.txt" not in assets:
            raise AdapterError("release %s has no %s / hashes.txt - refusing to install unverified binary" % (tag, want))
        with urllib.request.urlopen(assets["hashes.txt"], timeout=20) as r:
            hashes = r.read().decode()
        m = re.search(r"^([0-9a-fA-F]{64})\s+\*?\S*%s\s*$" % re.escape(want), hashes, re.M)
        if not m:
            raise AdapterError("no SHA256 for %s in hashes.txt" % want)
        tmp = tempfile.mkdtemp(prefix="hy1-")
        path = os.path.join(tmp, want)
        urllib.request.urlretrieve(assets[want], path)
        import hashlib
        if hashlib.sha256(open(path, "rb").read()).hexdigest().lower() != m.group(1).lower():
            raise AdapterError("SHA256 mismatch for Hysteria 1 download - aborting")
        os.makedirs(os.path.dirname(self.binary), exist_ok=True)
        shutil.move(path, self.binary)
        os.chmod(self.binary, 0o755)
        shutil.rmtree(tmp, ignore_errors=True)
        return rel.get("tag_name", tag)

    def install(self, opts=None):
        opts = opts or {}
        if not port_free("udp", PORT):
            raise AdapterError("udp/%d already in use; nothing was killed" % PORT)
        version = "dry-run" if config.DRY_RUN else self._download(
            opts.get("version") or os.environ.get("HYSTERIA1_VERSION", VERSION))
        log = _log_path()
        os.makedirs(os.path.dirname(log), exist_ok=True)
        write_file(os.path.join(config.SYSTEMD_DIR, AUTH_UNIT), _auth_unit_text())
        shell.run(["systemctl", "daemon-reload"], check=True)
        shell.run(["systemctl", "enable", "--now", AUTH_UNIT], check=True)
        unit = """[Unit]
Description=Hysteria 1 (Unified VPN)
After=network.target %s

[Service]
ExecStart=%s server -c %s
WorkingDirectory=%s
Environment=LOGGING_LEVEL=info
Restart=on-failure
RestartSec=3
LimitNOFILE=1048576
NoNewPrivileges=yes
ProtectHome=yes
PrivateTmp=yes
StandardOutput=append:%s
StandardError=append:%s

[Install]
WantedBy=multi-user.target
""" % (AUTH_UNIT, self.binary, self.conf_path, os.path.dirname(self.conf_path), log, log)
        write_file(os.path.join(config.SYSTEMD_DIR, UNIT), unit)
        shell.run(["systemctl", "daemon-reload"], check=True)
        self._render(force=True, restart=True)
        if not config.DRY_RUN:
            self._verify_listening(version)
        self.mark_installed({"version": version})

    def _verify_listening(self, version, wait=15):
        """A crash-loop unit can still report 'active', so confirm the port actually binds."""
        for _ in range(wait):
            if listening("udp", PORT):
                return
            time.sleep(1)
        st = shell.run(["systemctl", "status", UNIT, "-n", "20", "--no-pager"])
        lg = shell.run(["journalctl", "-u", UNIT, "-n", "40", "--no-pager", "-q"])
        raise AdapterError(
            "hysteria 1 (%s) did not bind udp/%d within %ds.\n--- status ---\n%s\n--- journal ---\n%s"
            % (version, PORT, wait, st.out.strip()[-1500:], lg.out.strip()[-3500:]))

    def uninstall(self):
        for u in (UNIT, AUTH_UNIT):
            shell.run(["systemctl", "disable", "--now", u])
            p = os.path.join(config.SYSTEMD_DIR, u)
            if os.path.exists(p):
                os.remove(p)
        shutil.rmtree(os.path.dirname(self.binary), ignore_errors=True)
        shell.run(["systemctl", "daemon-reload"])
        self.unmark_installed()

    # ---- rendering -------------------------------------------------------------------
    def build_config(self, cert, key, obfs):
        cfg = {
            "listen": ":%d" % PORT,
            "cert": cert,
            "key": key,
            "auth": {"mode": "external", "config": {"http": "http://127.0.0.1:%d/auth" % AUTH_PORT}},
        }
        if obfs:
            cfg["obfs"] = obfs
        return json.dumps(cfg, indent=2, sort_keys=True) + "\n"

    def _render(self, force=False, restart=True):
        conn = db.connect()
        try:
            cert = db.get_setting(conn, "tls_cert", "")
            key = db.get_setting(conn, "tls_key", "")
            obfs = self._obfs(conn)
        finally:
            conn.close()
        if not cert or not key:
            raise AdapterError("settings tls_cert/tls_key missing (installer sets them)")
        text = self.build_config(cert, key, obfs)
        json.loads(text)                                      # validation: must be well-formed JSON
        try:
            if not force and open(self.conf_path).read() == text:
                return False
        except (IOError, OSError):
            pass
        if os.path.exists(self.conf_path):
            shutil.copy2(self.conf_path, self.conf_path + ".bak")
        write_file(self.conf_path, text, 0o600)
        if config.DRY_RUN:
            return True
        if restart:
            shell.run(["systemctl", "enable", "--now", UNIT], check=True)
        else:
            shell.run(["systemctl", "enable", UNIT], check=True)
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
            return sorted(a["username"] for a in db.active_accounts(conn, ("hysteria1",)))
        finally:
            conn.close()

    def _obfs(self, conn):
        return db.get_setting(conn, "hysteria1_obfs", "") or DEFAULT_OBFS

    @staticmethod
    def _cred(user, account):
        """username:password sent by the client as auth_str. The auth service matches the password
        chosen by the admin, falling back to the auto-generated secret."""
        pw = (account.get("config") or {}).get("password") or account["secret"]
        return "%s:%s" % (user["username"], pw)

    def share(self, user, account, hostinfo):
        h = hostinfo["host"]
        conn = db.connect()
        try:
            obfs = self._obfs(conn)
        finally:
            conn.close()
        query = {"protocol": "udp", "auth": self._cred(user, account), "peer": h,
                 "upmbps": 10, "downmbps": 20, "obfs": "xplus", "obfsParam": obfs}
        if hostinfo.get("selfsigned"):
            query["insecure"] = 1
        url = "hysteria://%s:%d?%s#%s" % (h, PORT, urlencode(query), quote("%s-hy1" % user["username"]))
        return {"links": [{"label": "HYSTERIA1", "protocol": "hysteria1", "url": url}],
                "files": [{"label": "โปรไฟล์แอป Hysteria1 (.json)", "protocol": "hysteria1", "proto": ""}],
                "info": {"server": h, "port": "%d/udp" % PORT, "obfs": obfs,
                         "auth": "username:password (in the link)"}}

    def generate_config(self, user, account, host):
        """Profile JSON for the Hysteria 1 client app (the Servers/Networks file, see new.json).

        ``ServerIP`` defaults to the panel host; override with
        ``unified-vpn set-setting hysteria1_app_server <ip[:port]>`` if the app needs the port there.
        """
        conn = db.connect()
        try:
            obfs = self._obfs(conn)
            selfsigned = db.get_setting(conn, "tls_selfsigned") == "1"
            server_ip = db.get_setting(conn, "hysteria1_app_server", "") or host
        finally:
            conn.close()
        udp = {
            "server": "%s:%d" % (server_ip, PORT),
            "auth_str": self._cred(user, account),
            "obfs": obfs,
            "up_mbps": 10,
            "down_mbps": 20,
            "retry": 3,
            "retry_interval": 1,
            "socks5": {"listen": "127.0.0.1:1080"},
            "http": {"listen": "127.0.0.1:8989"},
            "insecure": bool(selfsigned),
            "ca": "",
            "recv_window_conn": 196608,
            "recv_window": 491520,
        }
        profile = {
            "Version": APP_VERSION,
            "Message": "Unified VPN",
            "Servers": [{
                "ServerName": host, "ServerFlag": "", "ServerIP": server_ip,
                "Cloudfront": "", "CloudfrontPort": "", "TCPPort": "", "SSHPort": "",
                "OpenVPNSSLPort": "", "SSHSSLPort": "", "NameServer": "", "PublicKey": "",
                "ServerDNS": "", "ProxyIP": "", "ProxyPort": "", "AutoLogIn": "true",
                "Username": "", "Password": "", "MultiCert": "true", "setOpenVPN": "", "V2Ray": "",
                "UDPConfig": json.dumps(udp, ensure_ascii=False),
                "SelectType": "UDP",
            }],
            "Networks": [{
                "PayloadName": "UnifiedVPN", "PayloadFlag": "", "PayloadInfo": "", "Sni": "",
                "ServerDNS": "", "Payload": "", "UseDefProxy": "false", "SquidProxy": "",
                "SquidPort": "", "SelectedProtocal": "UDP Hysteria", "Protocal": "OVPN",
            }],
            "setOpenVPN": "",
        }
        return "%s-hysteria1.json" % user["username"], json.dumps(profile, ensure_ascii=False, indent=2) + "\n"

    def online(self):
        """{username: connection_count} as mirrored by the external auth service."""
        try:
            with open(os.path.join(config.DATA, "hysteria1-online.json")) as fh:
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

    def _auth_reachable(self):
        if config.DRY_RUN:
            return True
        import socket
        try:
            with socket.create_connection(("127.0.0.1", AUTH_PORT), timeout=2):
                return True
        except OSError:
            return False

    def info(self):
        return {"port": "%d/udp" % PORT, "auth": "external (DB-backed)", "auth_port": AUTH_PORT}

    def health(self):
        res = [("hysteria1 binary exists", os.path.exists(self.binary) or config.DRY_RUN, ""),
               ("hysteria1 auth script present",
                os.path.exists(os.path.join(config.SCRIPTS_DIR, "hysteria1-auth.py")) or config.DRY_RUN, "")]
        ok = True
        try:
            json.load(open(self.conf_path))
        except (IOError, OSError, ValueError):
            ok = config.DRY_RUN
        res.append(("hysteria1 config valid JSON", ok, ""))
        res.append(("hysteria1 auth service active", servicemgr.unit_state(AUTH_UNIT) in ("RUNNING", "UNKNOWN"), ""))
        res.append(("hysteria1 auth endpoint reachable", self._auth_reachable(), "127.0.0.1:%d" % AUTH_PORT))
        res.append(("hysteria1 service active", servicemgr.unit_state(UNIT) in ("RUNNING", "UNKNOWN"), ""))
        res.append(("udp/%d listening" % PORT, listening("udp", PORT), ""))
        return res
