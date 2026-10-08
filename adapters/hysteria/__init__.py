"""Hysteria 2 adapter (UDP/QUIC, userpass auth). Declarative: config rendered from ALL active DB accounts.

Binary: GitHub release of apernet/hysteria, verified against the release hashes.txt (install aborts otherwise).
Runs as root only because it must read the TLS private key (Let's Encrypt keys are root-only);
the unit is sandboxed (NoNewPrivileges, ProtectHome, PrivateTmp).
Listens on UDP 443 (nginx uses TCP 443, no conflict).
"""
import json
import os
import platform
import re
import shutil
import tempfile
from urllib.parse import quote

from backend import config, db, servicemgr, shell
from adapters.base import Adapter, AdapterError, listening, port_free, write_file

PORT = 443
ARCH = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}


def _q(s):
    return json.dumps(str(s))          # JSON string == valid double-quoted YAML scalar (no injection)


class HysteriaAdapter(Adapter):
    name = "hysteria2"
    label = "Hysteria 2 (UDP)"
    protocols = ("hysteria2",)
    declarative = True

    @property
    def services(self):
        return ("unified-hysteria.service",)

    @property
    def binary(self):
        return os.path.join(config.HOME, "hysteria/hysteria")

    @property
    def conf_path(self):
        return os.path.join(config.ETC, "hysteria/config.yaml")

    def _download(self, version):
        import urllib.request
        arch = ARCH.get(platform.machine())
        if not arch:
            raise AdapterError("unsupported architecture %s" % platform.machine())
        api = "https://api.github.com/repos/apernet/hysteria/releases/" + ("latest" if version == "latest" else "tags/app/" + version)
        with urllib.request.urlopen(api, timeout=20) as r:
            rel = json.load(r)
        assets = dict((a["name"], a["browser_download_url"]) for a in rel["assets"])
        want = "hysteria-linux-%s" % arch
        if want not in assets or "hashes.txt" not in assets:
            raise AdapterError("release has no %s / hashes.txt - refusing to install unverified binary" % want)
        with urllib.request.urlopen(assets["hashes.txt"], timeout=20) as r:
            hashes = r.read().decode()
        m = re.search(r"^([0-9a-fA-F]{64})\s+\*?\S*%s\s*$" % re.escape(want), hashes, re.M)
        if not m:
            raise AdapterError("no SHA256 for %s in hashes.txt" % want)
        tmp = tempfile.mkdtemp(prefix="hy2-")
        path = os.path.join(tmp, want)
        urllib.request.urlretrieve(assets[want], path)
        import hashlib
        if hashlib.sha256(open(path, "rb").read()).hexdigest().lower() != m.group(1).lower():
            raise AdapterError("SHA256 mismatch for Hysteria download - aborting")
        os.makedirs(os.path.dirname(self.binary), exist_ok=True)
        shutil.move(path, self.binary)
        os.chmod(self.binary, 0o755)
        shutil.rmtree(tmp, ignore_errors=True)
        return rel.get("tag_name", version)

    def install(self, opts=None):
        opts = opts or {}
        if not port_free("udp", PORT):
            raise AdapterError("udp/%d already in use; nothing was killed" % PORT)
        version = "dry-run" if config.DRY_RUN else self._download(opts.get("version") or os.environ.get("HYSTERIA_VERSION", "latest"))
        unit = """[Unit]
Description=Hysteria 2 (Unified VPN)
After=network.target

[Service]
ExecStart=%s server -c %s
WorkingDirectory=%s
Restart=on-failure
RestartSec=3
LimitNOFILE=1048576
NoNewPrivileges=yes
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
""" % (self.binary, self.conf_path, os.path.dirname(self.conf_path))
        write_file(os.path.join(config.SYSTEMD_DIR, "unified-hysteria.service"), unit)
        self._render(force=True, restart=False)
        shell.run(["systemctl", "daemon-reload"], check=True)
        shell.run(["systemctl", "enable", "--now", "unified-hysteria.service"], check=True)
        self.mark_installed({"version": version})

    def uninstall(self):
        shell.run(["systemctl", "disable", "--now", "unified-hysteria.service"])
        p = os.path.join(config.SYSTEMD_DIR, "unified-hysteria.service")
        if os.path.exists(p):
            os.remove(p)
        shutil.rmtree(os.path.dirname(self.binary), ignore_errors=True)
        shell.run(["systemctl", "daemon-reload"])
        self.unmark_installed()

    # ---- rendering -------------------------------------------------------------------
    def build_config(self, accounts, cert, key, masquerade):
        lines = ["# managed by unified-vpn - do not edit", "listen: :%d" % PORT, "tls:",
                 "  cert: %s" % _q(cert), "  key: %s" % _q(key), "auth:", "  type: userpass", "  userpass:"]
        for a in accounts:                       # EVERY active account (not just the last one)
            lines.append("    %s: %s" % (_q(a["username"]), _q(a["secret"])))
        if not accounts:
            lines[-1:] = ["  userpass: {}"]
        lines += ["masquerade:", "  type: proxy", "  proxy:", "    url: %s" % _q(masquerade), "    rewriteHost: true"]
        return "\n".join(lines) + "\n"

    def _render(self, force=False, restart=True):
        conn = db.connect()
        try:
            accounts = db.active_accounts(conn, ("hysteria2",))
            cert = db.get_setting(conn, "tls_cert", "")
            key = db.get_setting(conn, "tls_key", "")
            masq = db.get_setting(conn, "hysteria_masquerade", "https://www.bing.com")
        finally:
            conn.close()
        if not cert or not key:
            raise AdapterError("settings tls_cert/tls_key missing (installer sets them)")
        text = self.build_config(accounts, cert, key, masq)
        try:
            if not force and open(self.conf_path).read() == text:
                return False
        except (IOError, OSError):
            pass
        write_file(self.conf_path, text, 0o600)
        if restart:
            shell.run(["systemctl", "restart", "unified-hysteria.service"], check=True)
        return True

    def sync(self):
        if self.installed():
            self._render()

    def create_user(self, user, account):
        return {}

    def delete_user(self, user, account):
        pass

    def list_users(self):
        conn = db.connect()
        try:
            return sorted(a["username"] for a in db.active_accounts(conn, ("hysteria2",)))
        finally:
            conn.close()

    def share(self, user, account, hostinfo):
        h = hostinfo["host"]
        q = "sni=%s%s" % (h, "&insecure=1" if hostinfo.get("selfsigned") else "")
        url = "hysteria2://%s:%s@%s:%d/?%s#%s" % (quote(user["username"]), quote(account["secret"]), h, PORT, q,
                                                  quote("%s-hy2" % user["username"]))
        return {"links": [{"label": "HYSTERIA2", "protocol": "hysteria2", "url": url}], "files": [],
                "info": {"server": h, "port": "%d/udp" % PORT, "auth": "username:password (in the link)"}}

    def info(self):
        return {"port": "%d/udp" % PORT, "auth": "userpass"}

    def health(self):
        res = [("hysteria binary exists", os.path.exists(self.binary) or config.DRY_RUN, ""),
               ("hysteria config present", os.path.exists(self.conf_path), ""),
               ("hysteria service active", servicemgr.unit_state("unified-hysteria.service") in ("RUNNING", "UNKNOWN"), ""),
               ("udp/%d listening" % PORT, listening("udp", PORT), "")]
        return res
