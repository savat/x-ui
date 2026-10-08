"""Xray adapter (VLESS / VMess / Trojan over WebSocket, TLS terminated by nginx on :443).

Declarative: config.json is built from Python objects (never string replacement) from the DB,
validated with `xray run -test`, then swapped in atomically. Restart only if the content changed.
Reality / gRPC / Shadowsocks are Phase 2.
"""
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import tempfile
import zipfile
from urllib.parse import quote

from backend import config, db, servicemgr, shell
from adapters.base import Adapter, AdapterError, apt_install, listening, nginx_reload, port_free, write_file

INBOUNDS = {            # protocol -> (local port, ws path)
    "vless": (10001, "/vless"),
    "vmess": (10002, "/vmess"),
    "trojan": (10003, "/trojan"),
}
REALITY_PORT = 8443          # public TCP port for VLESS+REALITY (nginx owns 443)
DEFAULT_DEST = "www.cloudflare.com:443"
ARCH = {"x86_64": "64", "amd64": "64", "aarch64": "arm64-v8a", "arm64": "arm64-v8a"}


class XrayAdapter(Adapter):
    name = "xray"
    label = "Xray (VLESS/VMess/Trojan)"
    protocols = tuple(INBOUNDS) + ("reality",)
    declarative = True

    @property
    def services(self):
        return ("xray.service",)

    @property
    def conf_path(self):
        return os.path.join(config.ETC, "xray/config.json")

    @property
    def binary(self):
        return os.path.join(config.HOME, "xray/xray")

    # ---- install (download is verified against the release .dgst file) ----------------
    def _download(self, version):
        import platform
        import urllib.request
        arch = ARCH.get(platform.machine())
        if not arch:
            raise AdapterError("unsupported architecture %s" % platform.machine())
        if version == "latest":
            with urllib.request.urlopen("https://api.github.com/repos/XTLS/Xray-core/releases/latest", timeout=20) as r:
                version = json.load(r)["tag_name"]
        base = "https://github.com/XTLS/Xray-core/releases/download/%s/Xray-linux-%s.zip" % (version, arch)
        tmp = tempfile.mkdtemp(prefix="xray-")
        zpath = os.path.join(tmp, "xray.zip")
        urllib.request.urlretrieve(base, zpath)
        with urllib.request.urlopen(base + ".dgst", timeout=20) as r:
            dgst = r.read().decode()
        m = re.search(r"(?:SHA2-256|SHA256)\s*=\s*([0-9a-fA-F]{64})", dgst)
        if not m:
            raise AdapterError("could not read SHA256 from .dgst - refusing to install unverified binary")
        h = hashlib.sha256(open(zpath, "rb").read()).hexdigest()
        if h.lower() != m.group(1).lower():
            raise AdapterError("SHA256 mismatch for Xray download - aborting")
        os.makedirs(os.path.dirname(self.binary), exist_ok=True)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(os.path.dirname(self.binary))
        os.chmod(self.binary, 0o755)
        shutil.rmtree(tmp, ignore_errors=True)
        return version

    def install(self, opts=None):
        opts = opts or {}
        if not port_free("tcp", REALITY_PORT):
            raise AdapterError("tcp/%d (REALITY) already in use; nothing was killed" % REALITY_PORT)
        apt_install("unzip", "curl")
        if config.DRY_RUN:
            version = "dry-run"
        else:
            version = self._download(opts.get("version") or os.environ.get("XRAY_VERSION", "latest"))
        self._ensure_reality()
        os.makedirs(os.path.join(config.VARLOG, "xray"), exist_ok=True)
        shell.run(["chown", "nobody:nogroup", os.path.join(config.VARLOG, "xray")])
        os.makedirs(os.path.dirname(self.conf_path), exist_ok=True)
        unit = """[Unit]
Description=Xray (Unified VPN)
After=network.target nss-lookup.target

[Service]
User=nobody
Group=nogroup
ExecStart=%s run -config %s
Restart=on-failure
RestartSec=3
LimitNOFILE=1048576
NoNewPrivileges=yes
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
""" % (self.binary, self.conf_path)
        write_file(os.path.join(config.SYSTEMD_DIR, "xray.service"), unit)
        loc = ""
        for proto, (port, path) in INBOUNDS.items():
            loc += """location %s {
    if ($http_upgrade != "websocket") { return 404; }
    proxy_pass http://127.0.0.1:%d;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 86400s;
    proxy_buffering off;
}
""" % (path, port)
        write_file(os.path.join(config.NGINX_HTTPS_D, "xray.conf"), loc)
        self._render(force=True, restart=False)
        shell.run(["systemctl", "daemon-reload"], check=True)
        shell.run(["systemctl", "enable", "--now", "xray.service"], check=True)
        nginx_reload()
        self.mark_installed({"version": version})

    def uninstall(self):
        shell.run(["systemctl", "disable", "--now", "xray.service"])
        for p in (os.path.join(config.SYSTEMD_DIR, "xray.service"), os.path.join(config.NGINX_HTTPS_D, "xray.conf")):
            if os.path.exists(p):
                os.remove(p)
        shutil.rmtree(os.path.dirname(self.binary), ignore_errors=True)
        shell.run(["systemctl", "daemon-reload"])
        try:
            nginx_reload()
        except AdapterError:
            pass
        self.unmark_installed()

    # ---- REALITY material (generated once; shortId/keys stay stable so client links never break) ----
    @property
    def reality_path(self):
        return os.path.join(config.CONF_DIR, "xray-reality.json")

    def _ensure_reality(self):
        if os.path.exists(self.reality_path):
            return
        if config.DRY_RUN:
            priv, pub = [base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=") for _ in range(2)]
        else:
            out = shell.run([self.binary, "x25519"], check=True).out
            # Output labels changed across Xray versions:
            #   old:  "Private key: ..."        "Public key: ..."
            #   new:  "PrivateKey: ..."         "Password (PublicKey): ..."     "Hash32: ..."
            m1 = re.search(r"private\s*key\s*:\s*(\S+)", out, re.I)
            m2 = re.search(r"(?:password(?:\s*\(\s*public\s*key\s*\))?|public\s*key)\s*:\s*(\S+)", out, re.I)
            if m1 and m2:
                priv, pub = m1.group(1), m2.group(1)
            else:
                # Last-resort fallback: the two (and only two, before Hash32) 32-byte base64url keys.
                keys = re.findall(r"\b[A-Za-z0-9_-]{43}\b", out)
                if len(keys) < 2:
                    raise AdapterError("could not parse `xray x25519` output: %r" % out.strip()[:200])
                priv, pub = keys[0], keys[1]
        write_file(self.reality_path, json.dumps({"private": priv, "public": pub, "short_id": secrets.token_hex(4)}), 0o600)

    def _reality(self, dest):
        try:
            r = json.load(open(self.reality_path))
        except (IOError, OSError, ValueError):
            raise AdapterError("REALITY keys missing (%s); reinstall the xray adapter" % self.reality_path)
        r["dest"] = dest
        return r

    # ---- config rendering ----------------------------------------------------------------
    def build_config(self, accounts, reality=None):
        by = dict((p, []) for p in tuple(INBOUNDS) + ("reality",))
        for a in accounts:
            by[a["protocol"]].append(a)
        inbounds = []
        ws = lambda path: {"network": "ws", "security": "none", "wsSettings": {"path": path}}
        if by["vless"]:
            inbounds.append({"tag": "vless-ws", "listen": "127.0.0.1", "port": INBOUNDS["vless"][0], "protocol": "vless",
                             "settings": {"decryption": "none",
                                          "clients": [{"id": a["uuid"], "email": a["username"]} for a in by["vless"]]},
                             "streamSettings": ws(INBOUNDS["vless"][1])})
        if by["vmess"]:
            inbounds.append({"tag": "vmess-ws", "listen": "127.0.0.1", "port": INBOUNDS["vmess"][0], "protocol": "vmess",
                             "settings": {"clients": [{"id": a["uuid"], "email": a["username"]} for a in by["vmess"]]},
                             "streamSettings": ws(INBOUNDS["vmess"][1])})
        if by["trojan"]:
            inbounds.append({"tag": "trojan-ws", "listen": "127.0.0.1", "port": INBOUNDS["trojan"][0], "protocol": "trojan",
                             "settings": {"clients": [{"password": a["secret"], "email": a["username"]} for a in by["trojan"]]},
                             "streamSettings": ws(INBOUNDS["trojan"][1])})
        if by["reality"]:
            sni = reality["dest"].rsplit(":", 1)[0]
            inbounds.append({"tag": "reality", "listen": "0.0.0.0", "port": REALITY_PORT, "protocol": "vless",
                             "settings": {"decryption": "none", "clients": [
                                 {"id": a["uuid"], "email": a["username"], "flow": "xtls-rprx-vision"} for a in by["reality"]]},
                             "streamSettings": {"network": "tcp", "security": "reality", "realitySettings": {
                                 "show": False, "dest": reality["dest"], "xver": 0, "serverNames": [sni],
                                 "privateKey": reality["private"], "shortIds": [reality["short_id"]]}}})
        if not inbounds:   # keep Xray startable with zero users
            inbounds.append({"tag": "idle", "listen": "127.0.0.1", "port": 10000, "protocol": "dokodemo-door",
                             "settings": {"address": "127.0.0.1"}})
        return {"log": {"loglevel": "warning", "access": "none",
                        "error": os.path.join(config.VARLOG, "xray/error.log")},
                "inbounds": inbounds,
                "outbounds": [{"protocol": "freedom", "tag": "direct"}, {"protocol": "blackhole", "tag": "block"}]}

    def _render(self, force=False, restart=True):
        conn = db.connect()
        try:
            accounts = db.active_accounts(conn, tuple(INBOUNDS) + ("reality",))
            dest = db.get_setting(conn, "reality_dest", DEFAULT_DEST)
            reality = self._reality(dest) if any(a["protocol"] == "reality" for a in accounts) else None
            cfg = self.build_config(accounts, reality)
        finally:
            conn.close()
        text = json.dumps(cfg, indent=2, sort_keys=True) + "\n"
        try:
            if not force and open(self.conf_path).read() == text:
                return False                     # nothing changed - no restart, no dropped connections
        except (IOError, OSError):
            pass
        # Temp file must keep a recognised extension (.json): newer Xray detects the config
        # format from the filename suffix and rejects e.g. "config.json.new".
        tmp = self.conf_path + ".new.json"
        write_file(tmp, text, 0o640, group="nogroup")
        if os.path.exists(self.binary) or not config.DRY_RUN:
            t = shell.run([self.binary, "run", "-test", "-config", tmp])
            if not t.ok:
                os.remove(tmp)
                raise AdapterError("xray config validation failed: %s" % t.out.strip()[-300:])
        if os.path.exists(self.conf_path):
            shutil.copy2(self.conf_path, self.conf_path + ".bak")
        os.replace(tmp, self.conf_path)
        if restart:
            shell.run(["systemctl", "restart", "xray.service"], check=True)
        return True

    def sync(self):
        if self.installed():
            self._render()

    # ---- users ---------------------------------------------------------------------------
    def create_user(self, user, account):
        return {}                                # uuid/secret are created by the user manager; sync() renders

    def delete_user(self, user, account):
        pass

    def list_users(self):
        try:
            cfg = json.load(open(self.conf_path))
        except (IOError, OSError, ValueError):
            return []
        names = set()
        for ib in cfg.get("inbounds", []):
            for c in ib.get("settings", {}).get("clients", []) or []:
                if c.get("email"):
                    names.add(c["email"])
        return sorted(names)

    # ---- share links ------------------------------------------------------------------------
    def share(self, user, account, hostinfo):
        h, proto = hostinfo["host"], account["protocol"]
        if proto == "reality":
            r = self._reality(hostinfo.get("reality_dest") or DEFAULT_DEST)
            sni = r["dest"].rsplit(":", 1)[0]
            link = ("vless://%s@%s:%d?encryption=none&flow=xtls-rprx-vision&security=reality&sni=%s&fp=chrome&pbk=%s&sid=%s&type=tcp#%s"
                    % (account["uuid"], h, REALITY_PORT, sni, r["public"], r["short_id"], quote("%s-reality" % user["username"])))
            return {"links": [{"label": "VLESS REALITY", "protocol": "reality", "url": link}], "files": [],
                    "info": {"host": h, "port": REALITY_PORT, "sni": sni, "flow": "xtls-rprx-vision"}}
        port, path = INBOUNDS[proto]
        name = quote("%s-%s" % (user["username"], proto))
        insecure = "&allowInsecure=1" if hostinfo.get("selfsigned") else ""
        q = "security=tls&type=ws&host=%s&path=%s&sni=%s%s" % (h, quote(path, safe=""), h, insecure)
        if proto == "vless":
            link = "vless://%s@%s:443?encryption=none&%s#%s" % (account["uuid"], h, q, name)
        elif proto == "trojan":
            link = "trojan://%s@%s:443?%s#%s" % (quote(account["secret"]), h, q, name)
        else:
            obj = {"v": "2", "ps": "%s-%s" % (user["username"], proto), "add": h, "port": "443", "id": account["uuid"],
                   "aid": "0", "scy": "auto", "net": "ws", "type": "none", "host": h, "path": path, "tls": "tls", "sni": h}
            link = "vmess://" + base64.b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode()
        return {"links": [{"label": proto.upper(), "protocol": proto, "url": link}], "files": [],
                "info": {"host": h, "port": 443, "path": path, "transport": "ws+tls"}}

    def info(self):
        return {"paths": dict((p, v[1]) for p, v in INBOUNDS.items()), "public_port": 443, "reality_port": REALITY_PORT}

    def health(self):
        res = [("xray binary exists", os.path.exists(self.binary) or config.DRY_RUN, "")]
        valid = True
        if os.path.exists(self.binary) and os.path.exists(self.conf_path):
            valid = shell.run([self.binary, "run", "-test", "-config", self.conf_path]).ok
        res.append(("xray config valid", valid, ""))
        res.append(("xray service active", servicemgr.unit_state("xray.service") in ("RUNNING", "UNKNOWN"), ""))
        conn = db.connect()
        try:
            active = set(a["protocol"] for a in db.active_accounts(conn, tuple(INBOUNDS) + ("reality",)))
        finally:
            conn.close()
        for proto in sorted(active):
            port = REALITY_PORT if proto == "reality" else INBOUNDS[proto][0]
            res.append(("%s inbound listening" % proto, listening("tcp", port), ""))
        return res
