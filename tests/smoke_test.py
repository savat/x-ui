"""Dry-run smoke test (no root, no real services): exercises API, user manager, adapters' config rendering.
Run:  PYTHONPATH=.:panel python3 tests/smoke_test.py
"""
import json
import os
import sys
import tempfile

T = tempfile.mkdtemp(prefix="uvpn-test-")
os.environ.update(
    UVPN_DRY_RUN="1", UVPN_HOME=T + "/home", UVPN_DATA=T + "/data", UVPN_ETC=T + "/etc", UVPN_VARLOG=T + "/log",
    UVPN_SYSTEMD_DIR=T + "/systemd", UVPN_SECRET_KEY="test-secret", UVPN_INSECURE_COOKIES="1", UVPN_BACKUPS=T + "/bk",
    UVPN_NGINX_D=T + "/nginx.d", UVPN_NGINX_HTTP_D=T + "/nginx-http.d", UVPN_DB=T + "/data/database.db",
    UVPN_SCRIPTS=os.path.abspath("scripts"))
os.makedirs(T + "/etc/ssh/sshd_config.d")
open(T + "/etc/ssh/sshd_config", "w").write("Include /etc/ssh/sshd_config.d/*.conf\nPort 22\n")

from adapters import all_adapters                      # noqa: E402
from backend import config, db, maintenance, security  # noqa: E402
from backend.app import create_app                     # noqa: E402

ok = fail = 0


def check(name, cond):
    global ok, fail
    print(("PASS " if cond else "FAIL ") + name)
    ok, fail = ok + bool(cond), fail + (not cond)


app = create_app()
conn = db.connect()
conn.execute("INSERT INTO admins(username,password_hash,role,created_at) VALUES(?,?,?,?)",
             ("boss", security.hash_password("correct horse battery"), "superadmin", db.now_iso()))
conn.execute("INSERT INTO admins(username,password_hash,role,created_at) VALUES(?,?,?,?)",
             ("viewer", security.hash_password("support-password-1"), "support", db.now_iso()))
conn.commit()
db.set_setting(conn, "host", "vpn.example.com")
db.set_setting(conn, "tls_cert", "/etc/unified-vpn/tls/self.crt")
db.set_setting(conn, "tls_key", "/etc/unified-vpn/tls/self.key")

os.makedirs(config.CONF_DIR, exist_ok=True)
json.dump({"binary_url": "https://example.invalid/zivpn", "sha256": "0" * 64, "binary_path": T + "/zivpn-bin"},
          open(config.CONF_DIR + "/zivpn.json", "w"))
for ad in all_adapters().values():
    if ad.name == "openvpn":
        ad.mark_installed()      # real install needs apt + easy-rsa, not available in a dry run
    else:
        ad.install()
check("badvpn unit binds loopback only", "--listen-addr 127.0.0.1:7300" in open(T + "/systemd/unified-badvpn.service").read())
check("ssh drop-in written", os.path.exists(T + "/etc/ssh/sshd_config.d/90-unified-vpn.conf"))
check("nginx snippets written", os.path.exists(T + "/nginx.d/xray.conf") and os.path.exists(T + "/nginx-http.d/ssh-ws.conf"))

c = app.test_client()
check("unauthenticated API rejected", c.get("/api/users").status_code == 401)
r = c.post("/api/auth/login", json={"username": "boss", "password": "wrong"})
check("bad login rejected", r.status_code == 401)
r = c.post("/api/auth/login", json={"username": "boss", "password": "correct horse battery"})
check("login ok", r.status_code == 200)
H = {"X-CSRF-Token": r.get_json()["csrf"]}
check("CSRF enforced", c.post("/api/users", json={}).status_code == 403)

body = {"username": "test01", "password": "s3cretpass", "days": 30, "max_connections": 2,
        "protocols": ["ssh", "openvpn", "vless", "vmess", "trojan", "zivpn"]}
r = c.post("/api/users", json=body, headers=H)
check("create user (6 protocols)", r.status_code == 201)
uid = r.get_json()["id"]
check("duplicate username rejected", c.post("/api/users", json=body, headers=H).status_code == 400)
check("weak/invalid username rejected", c.post("/api/users", json=dict(body, username="Root!"), headers=H).status_code == 400)

xr = all_adapters()["xray"]
cfg = json.load(open(xr.conf_path))
protos = sorted(i["protocol"] for i in cfg["inbounds"])
check("xray config rendered from DB (vless/vmess/trojan)", protos == ["trojan", "vless", "vmess"])
check("xray listens on loopback only", all(i["listen"] == "127.0.0.1" for i in cfg["inbounds"]))

share = c.get("/api/users/%d/share" % uid).get_json()
links = [l["url"] for s in share for l in s["links"]]
check("share links generated", any(l.startswith("vless://") for l in links) and any(l.startswith("vmess://") for l in links)
      and any(l.startswith("trojan://") for l in links))

r = c.get("/api/users?status=active&protocol=vless")
check("list/filter users", len(r.get_json()) == 1 and "password_hash" not in r.get_json()[0])

check("disable user", c.post("/api/users/%d/disable" % uid, headers=H).status_code == 200)
cfg = json.load(open(xr.conf_path))
check("disabled user removed from xray config", [i["tag"] for i in cfg["inbounds"]] == ["idle"])
check("enable user", c.post("/api/users/%d/enable" % uid, headers=H).status_code == 200)
check("renew user", c.post("/api/users/%d/renew" % uid, json={"days": 10}, headers=H).status_code == 200)

conn.execute("UPDATE users SET expires_at='2000-01-01T00:00:00Z' WHERE id=?", (uid,))
conn.commit()
check("maintenance runs", maintenance.run() == 0)
row = conn.execute("SELECT status FROM users WHERE id=?", (uid,)).fetchone()
check("expired user flagged", row["status"] == "expired")
check("expired user REVOKED in adapters (not just hidden)",
      conn.execute("SELECT COUNT(*) FROM protocol_accounts WHERE user_id=? AND status!='revoked'", (uid,)).fetchone()[0] == 0)
cfg = json.load(open(xr.conf_path))
check("expired user absent from xray config", [i["tag"] for i in cfg["inbounds"]] == ["idle"])
check("cannot enable expired user without renew", c.post("/api/users/%d/enable" % uid, headers=H).status_code == 400)

check("service control rejects unknown unit", c.post("/api/services/evil/restart", headers=H).status_code == 400)
check("protected service cannot be stopped", c.post("/api/services/ssh/stop", headers=H).status_code == 400)
check("logs for unknown unit rejected", c.get("/api/logs/..%2Fetc%2Fpasswd").status_code in (400, 404))
check("dashboard works", c.get("/api/dashboard").status_code == 200)
check("delete user", c.delete("/api/users/%d" % uid, headers=H).status_code == 200)

# ---------------- Phase 2 protocols: Reality, Hysteria2, WireGuard -------------------------------
import re  # noqa: E402
ids = []
for n in ("alice", "bobby", "carol"):
    r = c.post("/api/users", json={"username": n, "password": "passw0rd-" + n, "days": 5,
                                   "protocols": ["reality", "hysteria2", "wireguard"]}, headers=H)
    ids.append(r.get_json().get("id"))
    check("create %s (reality+hysteria2+wireguard)" % n, r.status_code == 201)
hy = open(os.path.join(config.ETC, "hysteria/config.yaml")).read()
check("hysteria2 config contains ALL 3 users (regression for single-user bug)",
      all(('"%s":' % n) in hy for n in ("alice", "bobby", "carol")))
check("hysteria2 masquerade uses proxy.url form", "proxy:\n    url:" in hy)
cfg = json.load(open(xr.conf_path))
rl = [i for i in cfg["inbounds"] if i["tag"] == "reality"]
check("reality inbound present with vision flow for 3 users",
      len(rl) == 1 and len(rl[0]["settings"]["clients"]) == 3 and rl[0]["settings"]["clients"][0]["flow"] == "xtls-rprx-vision")
sid1 = rl[0]["streamSettings"]["realitySettings"]["shortIds"][0]
c.post("/api/users/%d/renew" % ids[0], json={"days": 1}, headers=H)
sid2 = [i for i in json.load(open(xr.conf_path))["inbounds"] if i["tag"] == "reality"][0]["streamSettings"]["realitySettings"]["shortIds"][0]
check("reality shortId stays stable across re-renders", sid1 == sid2 and len(sid1) == 8)
wg = open(os.path.join(config.ETC, "wireguard/wg0.conf")).read()
ips = re.findall(r"AllowedIPs = (10\.66\.0\.\d+)/32", wg)
check("wireguard: 3 peers with unique IPs", len(ips) == 3 and len(set(ips)) == 3)
share = dict((s["protocol"], s) for s in c.get("/api/users/%d/share" % ids[0]).get_json())
check("share links: hysteria2:// and reality vless://",
      share["hysteria2"]["links"][0]["url"].startswith("hysteria2://alice:") and
      "security=reality" in share["reality"]["links"][0]["url"] and "pbk=" in share["reality"]["links"][0]["url"])
r = c.get("/api/users/%d/config?protocol=wireguard" % ids[0])
check("wireguard .conf download", r.status_code == 200 and b"[Peer]" in r.data and b"Endpoint = vpn.example.com:51820" in r.data)
c.post("/api/users/%d/disable" % ids[1], headers=H)
check("disabled user removed from hysteria2 + wireguard",
      '"bobby":' not in open(os.path.join(config.ETC, "hysteria/config.yaml")).read()
      and len(re.findall(r"AllowedIPs", open(os.path.join(config.ETC, "wireguard/wg0.conf")).read())) == 2)
conn.execute("UPDATE users SET expires_at='2000-01-01T00:00:00Z' WHERE id=?", (ids[2],))
conn.commit()
maintenance.run()
check("expired user revoked from reality/hysteria2/wireguard",
      '"carol":' not in open(os.path.join(config.ETC, "hysteria/config.yaml")).read()
      and "carol" not in open(os.path.join(config.ETC, "wireguard/wg0.conf")).read()
      and len([i for i in json.load(open(xr.conf_path))["inbounds"] if i["tag"] == "reality"][0]["settings"]["clients"]) == 1)

c2 = app.test_client()
r = c2.post("/api/auth/login", json={"username": "viewer", "password": "support-password-1"})
H2 = {"X-CSRF-Token": r.get_json()["csrf"]}
check("support role is read-only", c2.post("/api/users", json=body, headers=H2).status_code == 403
      and c2.get("/api/users").status_code == 200)

for _ in range(5):
    app.test_client().post("/api/auth/login", json={"username": "boss", "password": "nope"})
r = app.test_client().post("/api/auth/login", json={"username": "boss", "password": "correct horse battery"})
check("account locked after repeated failures", r.status_code == 401)

check("redaction", "secret" not in security.redact("password=secret123 vless://abc") and "abc" not in security.redact("vless://abc"))
print("\n%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
