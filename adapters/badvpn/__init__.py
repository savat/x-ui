"""BadVPN UDPGW adapter (Phase 2). Service-only: no per-user accounts.

udpgw lets SSH clients relay UDP (games/VoIP) through their SSH tunnel. It binds to 127.0.0.1 ONLY,
so it is reachable just from inside an authenticated SSH session, never from the Internet.
Package: distro `badvpn` (provides /usr/bin/badvpn-udpgw). Not tied to ZIVPN or any other adapter.
"""
import os

from backend import config, servicemgr, shell
from adapters.base import Adapter, AdapterError, apt_install, listening, port_free, write_file

PORT = 7300
BIN = "/usr/bin/badvpn-udpgw"


class BadVPNAdapter(Adapter):
    name = "badvpn"
    label = "BadVPN UDPGW"
    protocols = ()

    @property
    def services(self):
        return ("unified-badvpn.service",)

    def install(self, opts=None):
        opts = opts or {}
        port = int(opts.get("port", PORT))
        if not port_free("tcp", port):
            raise AdapterError("tcp/%d already in use; nothing was killed" % port)
        apt_install("badvpn")
        if not os.path.exists(BIN) and not config.DRY_RUN:
            raise AdapterError("%s not found after install (package unavailable on this OS?)" % BIN)
        self.configure(port, int(opts.get("max_clients", 500)))
        shell.run(["systemctl", "daemon-reload"], check=True)
        shell.run(["systemctl", "enable", "--now", "unified-badvpn.service"], check=True)
        self.mark_installed({"port": port})

    def configure(self, port=PORT, max_clients=500):
        unit = """[Unit]
Description=BadVPN UDPGW (loopback only)
After=network.target

[Service]
ExecStart=%s --listen-addr 127.0.0.1:%d --max-clients %d --max-connections-for-client 8
User=nobody
Group=nogroup
Restart=always
RestartSec=2
NoNewPrivileges=yes
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
""" % (BIN, port, max_clients)
        write_file(os.path.join(config.SYSTEMD_DIR, "unified-badvpn.service"), unit)

    def uninstall(self):
        shell.run(["systemctl", "disable", "--now", "unified-badvpn.service"])
        p = os.path.join(config.SYSTEMD_DIR, "unified-badvpn.service")
        if os.path.exists(p):
            os.remove(p)
        shell.run(["systemctl", "daemon-reload"])
        self.unmark_installed()

    def _port(self):
        try:
            import json
            return json.load(open(self._marker())).get("port", PORT)
        except (IOError, OSError, ValueError):
            return PORT

    def info(self):
        return {"listen": "127.0.0.1:%d" % self._port(), "client_setting": "udpgw 127.0.0.1:%d" % self._port()}

    def health(self):
        return [("badvpn binary exists", os.path.exists(BIN) or config.DRY_RUN, ""),
                ("badvpn service active", servicemgr.unit_state("unified-badvpn.service") in ("RUNNING", "UNKNOWN"), ""),
                ("udpgw listening", listening("tcp", self._port()), "")]
