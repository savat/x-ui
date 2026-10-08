"""BadVPN UDPGW adapter (Phase 2). Service-only: no per-user accounts.

udpgw lets SSH clients relay UDP (games/VoIP) through their SSH tunnel. It binds to 127.0.0.1 ONLY,
so it is reachable just from inside an authenticated SSH session, never from the Internet.

No Debian/Ubuntu package exists (`apt-get install badvpn` -> "Unable to locate package"), so
/usr/bin/badvpn-udpgw is built from source (ambrop72/badvpn) exactly as the project README describes
for a udpgw-only build: `cmake -DBUILD_NOTHING_BY_DEFAULT=1 -DBUILD_UDPGW=1` (no OpenSSL/NSS needed).
"""
import glob
import os
import shutil

from backend import config, servicemgr, shell
from adapters.base import Adapter, AdapterError, apt_install, listening, port_free, write_file

PORT = 7300
BIN = "/usr/bin/badvpn-udpgw"
SOURCE_URL = "https://github.com/ambrop72/badvpn"


def _build_binary():
    """Compile only the udpgw target from upstream source and install it at BIN."""
    if config.DRY_RUN or os.path.exists(BIN):
        return
    apt_install("build-essential", "cmake", "git")
    scratch = os.path.join(config.DATA, "sources", "badvpn")
    if not os.path.exists(os.path.join(scratch, "CMakeLists.txt")):
        shutil.rmtree(scratch, ignore_errors=True)
        os.makedirs(scratch, exist_ok=True)
        shell.run(["git", "clone", "--depth", "1", SOURCE_URL, scratch], timeout=300, check=True)
    build = os.path.join(scratch, "build")
    shell.run(["cmake", "-S", scratch, "-B", build,
               "-DBUILD_NOTHING_BY_DEFAULT=1", "-DBUILD_UDPGW=1",
               "-DCMAKE_BUILD_TYPE=Release"], timeout=300, check=True)
    shell.run(["cmake", "--build", build], timeout=600, check=True)
    cands = []
    for pat in ("*/badvpn-udpgw", "*/udpgw"):
        cands += [p for p in glob.glob(os.path.join(build, pat))
                  if os.path.isfile(p) and os.access(p, os.X_OK)]
    if not cands:
        raise AdapterError("badvpn build finished but no udpgw binary was produced in %s" % build)
    shutil.copy2(sorted(cands)[0], BIN)
    os.chmod(BIN, 0o755)
    shutil.rmtree(scratch, ignore_errors=True)   # keep only the installed binary


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
        _build_binary()
        if not os.path.exists(BIN) and not config.DRY_RUN:
            raise AdapterError("%s missing after build (source build failed?)" % BIN)
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
