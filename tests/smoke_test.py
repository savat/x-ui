"""Dry-run smoke test (no root, no real services): exercises the API, user manager and the ZIVPN adapter.
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
    UVPN_DB=T + "/data/database.db", UVPN_SCRIPTS=os.path.abspath("scripts"))

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

os.makedirs(config.CONF_DIR, exist_ok=True)
json.dump({"binary_url": "https://example.invalid/zivpn", "sha256": "0" * 64, "binary_path": T + "/zivpn-bin"},
          open(config.CONF_DIR + "/zivpn.json", "w"))
check("only the zivpn adapter is registered", list(all_adapters()) == ["zivpn"])
zv = all_adapters()["zivpn"]
zv.install()
check("zivpn unit written", os.path.exists(T + "/systemd/zivpn.service"))
check("zivpn NAT unit written", os.path.exists(T + "/systemd/unified-zivpn-nat.service"))

c = app.test_client()
check("unauthenticated API rejected", c.get("/api/users").status_code == 401)
r = c.post("/api/auth/login", json={"username": "boss", "password": "wrong"})
check("bad login rejected", r.status_code == 401)
r = c.post("/api/auth/login", json={"username": "boss", "password": "correct horse battery"})
check("login ok", r.status_code == 200)
H = {"X-CSRF-Token": r.get_json()["csrf"]}
check("CSRF enforced", c.post("/api/users", json={}).status_code == 403)

body = {"username": "test01", "password": "s3cretpass", "days": 30, "max_connections": 2}
r = c.post("/api/users", json=body, headers=H)
check("create user (protocol defaults to zivpn)", r.status_code == 201)
uid = r.get_json()["id"]
check("duplicate username rejected", c.post("/api/users", json=body, headers=H).status_code == 400)
check("invalid username rejected", c.post("/api/users", json=dict(body, username="Root!"), headers=H).status_code == 400)
check("other protocols rejected",
      c.post("/api/users", json=dict(body, username="test02", protocols=["ssh"]), headers=H).status_code == 400)


def zcfg():
    return json.load(open(zv.conf_path))


check("zivpn config holds the user's chosen password", "s3cretpass" in zcfg()["auth"]["config"])
share = c.get("/api/users/%d/share" % uid).get_json()
info = share[0]["info"]
check("share info: server/port/obfs/password", info["server"] == "vpn.example.com" and info["port"] == 5667
      and info["password"] == "s3cretpass" and info["obfs"])

r = c.get("/api/users?status=active&protocol=zivpn")
check("list/filter users", len(r.get_json()) == 1 and "password_hash" not in r.get_json()[0])

check("disable user", c.post("/api/users/%d/disable" % uid, headers=H).status_code == 200)
check("disabled user removed from zivpn config", "s3cretpass" not in zcfg()["auth"]["config"])
check("enable user", c.post("/api/users/%d/enable" % uid, headers=H).status_code == 200)
check("password back in config after enable", "s3cretpass" in zcfg()["auth"]["config"])
check("renew user", c.post("/api/users/%d/renew" % uid, json={"days": 10}, headers=H).status_code == 200)
check("reset password", c.post("/api/users/%d/reset-password" % uid, json={"password": "newpass99"}, headers=H).status_code == 200)
check("new password in config, old one gone", "newpass99" in zcfg()["auth"]["config"] and "s3cretpass" not in zcfg()["auth"]["config"])

conn.execute("UPDATE users SET expires_at='2000-01-01T00:00:00Z' WHERE id=?", (uid,))
conn.commit()
check("maintenance runs", maintenance.run() == 0)
check("expired user flagged", conn.execute("SELECT status FROM users WHERE id=?", (uid,)).fetchone()["status"] == "expired")
check("expired user REVOKED (not just hidden)",
      conn.execute("SELECT COUNT(*) FROM protocol_accounts WHERE user_id=? AND status!='revoked'", (uid,)).fetchone()[0] == 0)
check("expired user absent from zivpn config", "newpass99" not in zcfg()["auth"]["config"])
check("cannot enable expired user without renew", c.post("/api/users/%d/enable" % uid, headers=H).status_code == 400)

check("service control rejects unknown unit", c.post("/api/services/evil/restart", headers=H).status_code == 400)
check("protected service cannot be stopped", c.post("/api/services/nginx/stop", headers=H).status_code == 400)
check("ssh is no longer a managed service", c.post("/api/services/ssh/restart", headers=H).status_code == 400)
check("logs for unknown unit rejected", c.get("/api/logs/..%2Fetc%2Fpasswd").status_code in (400, 404))
d = c.get("/api/dashboard")
check("dashboard lists only zivpn", d.status_code == 200 and [p["name"] for p in d.get_json()["protocols"]] == ["zivpn"])
check("removed endpoints are gone", c.get("/api/users/%d/qr?protocol=zivpn" % uid).status_code == 404
      and c.get("/api/users/%d/config" % uid).status_code == 404)
check("delete user", c.delete("/api/users/%d" % uid, headers=H).status_code == 200)

c2 = app.test_client()
r = c2.post("/api/auth/login", json={"username": "viewer", "password": "support-password-1"})
H2 = {"X-CSRF-Token": r.get_json()["csrf"]}
check("support role is read-only", c2.post("/api/users", json=body, headers=H2).status_code == 403
      and c2.get("/api/users").status_code == 200)

for _ in range(5):
    app.test_client().post("/api/auth/login", json={"username": "boss", "password": "nope"})
r = app.test_client().post("/api/auth/login", json={"username": "boss", "password": "correct horse battery"})
check("account locked after repeated failures", r.status_code == 401)

check("redaction", "secret" not in security.redact("password=secret123"))
print("\n%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
