"""WireGuard adapter. Declarative: wg0.conf is rendered from active DB accounts and applied with
`wg syncconf` (no dropped tunnels for other users). Expired/disabled users are REMOVED from the peer list.

The server generates each client's keypair (+ preshared key) so the panel can re-download the .conf / QR;
client private keys live in the root-only DB. Max-connections cannot be enforced (UDP, one peer = one key).
"""
import base64
import os
import re
import time

from backend import config, db, servicemgr, shell
from adapters.base import Adapter, AdapterError, apt_install, ensure_nat, listening, port_free, write_file

PORT = 51820
SUBNET = "10.66.0.0/24"
SERVER_IP = "10.66.0.1"
IFACE = "wg0"


def _rand_key():
    return base64.b64encode(os.urandom(32)).decode()


class WireGuardAdapter(Adapter):
    name = "wireguard"
    label = "WireGuard"
    protocols = ("wireguard",)
    declarative = True

    @property
    def services(self):
        return ("wg-quick@%s.service" % IFACE,)

    @property
    def wgdir(self):
        return os.path.join(config.ETC, "wireguard")

    @property
    def conf_path(self):
        return os.path.join(self.wgdir, IFACE + ".conf")

    # ---- keys -------------------------------------------------------------------------
    def _genkey(self):
        if config.DRY_RUN:
            return _rand_key()
        return shell.run(["wg", "genkey"], check=True).out.strip()

    def _pubkey(self, priv):
        if config.DRY_RUN:
            return _rand_key()
        return shell.run(["wg", "pubkey"], input_text=priv + "\n", check=True).out.strip()

    def _genpsk(self):
        return _rand_key() if config.DRY_RUN else shell.run(["wg", "genpsk"], check=True).out.strip()

    def _server_keys(self):
        kp, pp = os.path.join(self.wgdir, "server.key"), os.path.join(self.wgdir, "server.pub")
        if not os.path.exists(kp):
            os.makedirs(self.wgdir, exist_ok=True)
            priv = self._genkey()
            write_file(kp, priv + "\n", 0o600)
            write_file(pp, self._pubkey(priv) + "\n", 0o644)
        return open(kp).read().strip(), open(pp).read().strip()

    # ---- install ------------------------------------------------------------------------
    def install(self, opts=None):
        if not port_free("udp", PORT):
            raise AdapterError("udp/%d already in use; nothing was killed" % PORT)
        apt_install("wireguard", "wireguard-tools", "iptables")
        self._server_keys()
        ensure_nat()
        self._render(force=True, restart=False)
        shell.run(["systemctl", "enable", "--now", self.services[0]], check=True)
        self.mark_installed({"port": PORT, "subnet": SUBNET})

    def uninstall(self):
        shell.run(["systemctl", "disable", "--now", self.services[0]])
        self.unmark_installed()          # keys/conf are kept on purpose

    # ---- rendering ------------------------------------------------------------------------
    def build_config(self, accounts, server_priv):
        parts = ["# managed by unified-vpn - do not edit\n[Interface]\nAddress = %s/24\nListenPort = %d\nPrivateKey = %s\n"
                 % (SERVER_IP, PORT, server_priv)]
        for a in accounts:
            c = a["config"]
            if not (c.get("public_key") and c.get("ip")):
                continue
            parts.append("\n[Peer]\n# %s\nPublicKey = %s\nPresharedKey = %s\nAllowedIPs = %s/32\n"
                         % (a["username"], c["public_key"], c.get("psk", ""), c["ip"]))
        return "".join(parts)

    def _render(self, force=False, restart=True):
        priv, _ = self._server_keys()
        conn = db.connect()
        try:
            accounts = db.active_accounts(conn, ("wireguard",))
        finally:
            conn.close()
        text = self.build_config(accounts, priv)
        try:
            if not force and open(self.conf_path).read() == text:
                return False
        except (IOError, OSError):
            pass
        write_file(self.conf_path, text, 0o600)
        if restart and servicemgr.unit_state(self.services[0]) == "RUNNING":
            strip = shell.run(["wg-quick", "strip", IFACE])
            ok = False
            if strip.ok and strip.out.strip():
                tmp = os.path.join(self.wgdir, ".sync.tmp")
                write_file(tmp, strip.out, 0o600)
                ok = shell.run(["wg", "syncconf", IFACE, tmp]).ok
                os.remove(tmp)
            if not ok:                       # fall back to a restart (drops tunnels briefly)
                shell.run(["systemctl", "restart", self.services[0]], check=True)
        return True

    def sync(self):
        if self.installed():
            self._render()

    # ---- users ----------------------------------------------------------------------------
    def _alloc_ip(self, own_id):
        conn = db.connect()
        try:
            used = set()
            for r in conn.execute("SELECT id, config FROM protocol_accounts WHERE protocol='wireguard'"):
                if r["id"] != own_id:
                    m = re.search(r'"ip":\s*"([0-9.]+)"', r["config"] or "")
                    if m:
                        used.add(m.group(1))
        finally:
            conn.close()
        for n in range(2, 255):
            ip = "10.66.0.%d" % n
            if ip not in used:
                return ip
        raise AdapterError("WireGuard subnet is full (253 peers)")

    def create_user(self, user, account):
        c = account.get("config") or {}
        if c.get("public_key") and c.get("ip") and c.get("private_key"):
            return {}                                         # idempotent: keep existing keys/IP
        priv = self._genkey()
        return {"private_key": priv, "public_key": self._pubkey(priv), "psk": self._genpsk(),
                "ip": self._alloc_ip(account.get("id"))}

    def delete_user(self, user, account):
        pass

    def list_users(self):
        conn = db.connect()
        try:
            return sorted(a["username"] for a in db.active_accounts(conn, ("wireguard",)))
        finally:
            conn.close()

    def online(self):
        r = shell.run(["wg", "show", IFACE, "latest-handshakes"])
        now, recent = time.time(), set()
        for line in r.out.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].isdigit() and now - int(parts[1]) < 180:
                recent.add(parts[0])
        if not recent:
            return {}
        conn = db.connect()
        try:
            return dict((a["username"], 1) for a in db.active_accounts(conn, ("wireguard",))
                        if a["config"].get("public_key") in recent)
        finally:
            conn.close()

    # ---- client config ---------------------------------------------------------------------
    def generate_config(self, user, account, host):
        c = account["config"]
        if not c.get("private_key"):
            raise AdapterError("WireGuard keys missing for this account")
        if servicemgr.unit_state(self.services[0]) not in ("RUNNING", "UNKNOWN") or not listening("udp", PORT):
            raise AdapterError("WireGuard is not running / not listening on udp/%d" % PORT)
        _, spub = self._server_keys()
        text = ("[Interface]\nPrivateKey = %s\nAddress = %s/32\nDNS = 1.1.1.1\n\n[Peer]\nPublicKey = %s\nPresharedKey = %s\n"
                "Endpoint = %s:%d\nAllowedIPs = 0.0.0.0/0\nPersistentKeepalive = 25\n"
                % (c["private_key"], c["ip"], spub, c.get("psk", ""), host, PORT))
        return "%s-wg.conf" % user["username"], text

    def share(self, user, account, hostinfo):
        return {"links": [], "files": [{"label": "WireGuard (.conf / QR)", "protocol": "wireguard", "proto": ""}],
                "info": {"endpoint": "%s:%d/udp" % (hostinfo["host"], PORT), "address": account["config"].get("ip", "")}}

    def info(self):
        return {"port": "%d/udp" % PORT, "subnet": SUBNET}

    def health(self):
        return [("wg0.conf present", os.path.exists(self.conf_path), ""),
                ("wireguard service active", servicemgr.unit_state(self.services[0]) in ("RUNNING", "UNKNOWN"), ""),
                ("udp/%d listening" % PORT, listening("udp", PORT), "")]
