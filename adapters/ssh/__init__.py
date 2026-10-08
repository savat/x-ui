"""SSH adapter: OpenSSH accounts + SSH over WebSocket (plain via :80, TLS via :443 through nginx)."""
import os
import pwd
import re
import shutil
import time
from datetime import timedelta

from backend import config, db, servicemgr, shell
from adapters.base import Adapter, AdapterError, apt_install, listening, nginx_reload, write_file

GROUP = "uvpn"
TAG = "uvpn-managed"
NOLOGIN = "/usr/sbin/nologin"
WS_PORT = 10015
WS_PATH = "/ssh-ws"
BEGIN, END = "# BEGIN unified-vpn", "# END unified-vpn"
BLOCK = BEGIN + """
Match Group %s
    PasswordAuthentication yes
    AllowTcpForwarding yes
    PermitTTY no
    X11Forwarding no
    AllowAgentForwarding no
""" % GROUP + END + "\n"

LOCATION = """location %s {
    proxy_pass http://127.0.0.1:%d;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;
    proxy_buffering off;
}
""" % (WS_PATH, WS_PORT)

PRIV_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+sshd: ([a-z][a-z0-9_-]*) \[priv\]\s*$")


class SSHAdapter(Adapter):
    name = "ssh"
    label = "SSH"
    protocols = ("ssh",)

    @property
    def services(self):
        return (servicemgr.ssh_unit(), "unified-ws-ssh.service")

    # ---- helpers -----------------------------------------------------------
    def _ssh_port(self):
        r = shell.run(["sshd", "-T"])
        m = re.search(r"^port (\d+)", r.out, re.M)
        return int(m.group(1)) if m else 22

    def _managed(self, name):
        try:
            return TAG in pwd.getpwnam(name).pw_gecos
        except KeyError:
            return False

    def _exists(self, name):
        try:
            pwd.getpwnam(name)
            return True
        except KeyError:
            return False

    # ---- install -------------------------------------------------------------
    def configure_sshd(self):
        """backup -> write -> sshd -t -> reload; rollback on any error (never overwrite sshd_config blindly)."""
        main = os.path.join(config.ETC, "ssh/sshd_config")
        dropin_dir = main + ".d"
        with open(main) as fh:
            text = fh.read()
        use_dropin = re.search(r"^\s*Include\s+\S*sshd_config\.d", text, re.M) and os.path.isdir(dropin_dir)
        if use_dropin:
            target = os.path.join(dropin_dir, "90-unified-vpn.conf")
            prev = open(target).read() if os.path.exists(target) else None
            write_file(target, BLOCK)
            if not shell.run(["sshd", "-t"]).ok:
                if prev is None:
                    os.remove(target)
                else:
                    write_file(target, prev)
                raise AdapterError("sshd -t failed after adding drop-in; change rolled back")
        else:
            bak = "%s.uvpn-bak-%d" % (main, int(time.time()))
            shutil.copy2(main, bak)
            if BEGIN in text:
                new = re.sub(re.escape(BEGIN) + ".*?" + re.escape(END) + "\n", BLOCK, text, flags=re.S)
            else:
                new = text.rstrip("\n") + "\n\n" + BLOCK
            write_file(main, new, 0o644)
            if not shell.run(["sshd", "-t"]).ok:
                shutil.copy2(bak, main)
                raise AdapterError("sshd -t failed; sshd_config restored from %s" % bak)
        r = shell.run(["systemctl", "reload", servicemgr.ssh_unit()])
        if not r.ok:
            raise AdapterError("ssh reload failed: %s" % r.out.strip()[-200:])

    def install(self, opts=None):
        apt_install("openssh-server")
        if not shell.run(["getent", "group", GROUP]).ok:
            shell.run(["groupadd", GROUP], check=True)
        self.configure_sshd()
        unit = """[Unit]
Description=Unified VPN - SSH WebSocket tunnel (127.0.0.1:%d -> sshd)
After=network.target ssh.service

[Service]
ExecStart=%s %s/adapters/ssh/ws_tunnel.py --listen 127.0.0.1:%d --target 127.0.0.1:%d
Restart=always
RestartSec=2
User=nobody
Group=nogroup
NoNewPrivileges=yes
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
""" % (WS_PORT, config.PY, config.HOME, WS_PORT, self._ssh_port())
        write_file(os.path.join(config.SYSTEMD_DIR, "unified-ws-ssh.service"), unit)
        write_file(os.path.join(config.NGINX_HTTPS_D, "ssh-ws.conf"), LOCATION)
        write_file(os.path.join(config.NGINX_HTTP_D, "ssh-ws.conf"), LOCATION)
        shell.run(["systemctl", "daemon-reload"], check=True)
        shell.run(["systemctl", "enable", "--now", "unified-ws-ssh.service"], check=True)
        nginx_reload()
        self.mark_installed({"ws_port": WS_PORT, "path": WS_PATH})

    def uninstall(self):
        shell.run(["systemctl", "disable", "--now", "unified-ws-ssh.service"])
        for p in (os.path.join(config.SYSTEMD_DIR, "unified-ws-ssh.service"),
                  os.path.join(config.NGINX_HTTPS_D, "ssh-ws.conf"),
                  os.path.join(config.NGINX_HTTP_D, "ssh-ws.conf"),
                  os.path.join(config.ETC, "ssh/sshd_config.d/90-unified-vpn.conf")):
            if os.path.exists(p):
                os.remove(p)
        for name in self.list_users():
            shell.run(["userdel", name])
        shell.run(["systemctl", "daemon-reload"])
        try:
            nginx_reload()
        except AdapterError:
            pass
        # NOTE: sshd itself and the admin's SSH access are never touched.
        self.unmark_installed()

    # ---- users ------------------------------------------------------------------
    def create_user(self, user, account):
        name = user["username"]
        exp_day = (db.parse(user["expires_at"]) + timedelta(days=1)).strftime("%Y-%m-%d")  # backstop only
        if not self._exists(name):
            shell.run(["useradd", "-M", "-s", NOLOGIN, "-G", GROUP, "-e", exp_day, "-c", TAG, name], check=True)
        elif self._managed(name):
            shell.run(["usermod", "-U", "-e", exp_day, "-s", NOLOGIN, name], check=True)
        else:
            raise AdapterError("a system user named '%s' already exists; refusing to take it over" % name)
        if user.get("password"):
            shell.run(["chpasswd"], input_text="%s:%s\n" % (name, user["password"]), check=True)
        return {"managed": True}

    def _kill_sessions(self, name):
        shell.run(["pkill", "-KILL", "-u", name])

    def revoke_user(self, user, account):
        name = user["username"]
        if self._managed(name):
            shell.run(["usermod", "-L", "-e", "1", name], check=True)
            self._kill_sessions(name)

    def delete_user(self, user, account):
        name = user["username"]
        if self._managed(name):
            self._kill_sessions(name)
            shell.run(["userdel", name], check=True)

    def list_users(self):
        return [p.pw_name for p in pwd.getpwall() if TAG in p.pw_gecos]

    # ---- connections ----------------------------------------------------------------
    def _privs(self):
        """[(pid, age_seconds, username)] for every established SSH connection."""
        out = shell.run(["ps", "-eo", "pid=,etimes=,args="]).out
        res = []
        for line in out.splitlines():
            m = PRIV_RE.match(line)
            if m:
                res.append((int(m.group(1)), int(m.group(2)), m.group(3)))
        return res

    def online(self):
        counts = {}
        for _, _, name in self._privs():
            if self._managed(name):
                counts[name] = counts.get(name, 0) + 1
        return counts

    def enforce_limits(self, conn):
        """Soft limit: newest connections beyond max_connections are killed (runs every minute).
        sshd has no per-user connection cap for tunnel-only sessions, so this is best-effort."""
        limits = dict((r["username"], r["max_connections"]) for r in conn.execute(
            "SELECT u.username, u.max_connections FROM users u JOIN protocol_accounts pa ON pa.user_id=u.id "
            "WHERE pa.protocol='ssh' AND u.status='active' AND u.max_connections > 0"))
        by_user = {}
        for pid, age, name in self._privs():
            if name in limits:
                by_user.setdefault(name, []).append((age, pid))
        killed = []
        for name, conns in by_user.items():
            conns.sort()                         # youngest first
            for age, pid in conns[:max(0, len(conns) - limits[name])]:
                shell.run(["kill", "-TERM", str(pid)])
                killed.append(name)
        return killed

    # ---- client info ----------------------------------------------------------------
    def share(self, user, account, hostinfo):
        h = hostinfo["host"]
        return {"links": [], "files": [], "info": {
            "host": h, "username": user["username"], "ssh_port": self._ssh_port(),
            "ssh_ws": "ws://%s:80%s" % (h, WS_PATH),
            "ssh_ws_tls": "wss://%s:443%s" % (h, WS_PATH),
            "payload_hint": "GET %s HTTP/1.1[crlf]Host: %s[crlf]Upgrade: websocket[crlf][crlf]" % (WS_PATH, h),
        }}

    def info(self):
        return {"ssh_port": self._ssh_port(), "ws_path": WS_PATH, "ws_http": 80, "ws_tls": 443}

    def health(self):
        res = [("sshd config valid", shell.run(["sshd", "-t"]).ok, "")]
        res.append(("ssh service active", servicemgr.unit_state(servicemgr.ssh_unit()) in ("RUNNING", "UNKNOWN"), ""))
        res.append(("ssh port listening", listening("tcp", self._ssh_port()), ""))
        res.append(("ws tunnel active", servicemgr.unit_state("unified-ws-ssh.service") in ("RUNNING", "UNKNOWN"), ""))
        res.append(("ws tunnel port listening", listening("tcp", WS_PORT), ""))
        return res
