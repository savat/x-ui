#!/usr/bin/env python3
"""End-to-end test for scripts/zivpn-auth.py (the ZIVPN HTTP auth endpoint).

Stdlib only, no root: it builds a throwaway SQLite DB from database/schema.sql, starts the auth
service on a random loopback port, and drives it over HTTP like the ZIVPN server does.

    python3 tests/zivpn_auth_test.py
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    tmp = tempfile.mkdtemp(prefix="zivpn-auth-")
    db, log = os.path.join(tmp, "database.db"), os.path.join(tmp, "zivpn.log")
    port = 18299
    os.environ.update(UVPN_DB=db, UVPN_DATA=tmp, ZIVPN_AUTH_PORT=str(port), ZIVPN_LOG=log)

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    future = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
    past = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))

    conn = sqlite3.connect(db)
    conn.executescript(open(os.path.join(ROOT, "database/schema.sql")).read())

    def add_user(name, pw, expires, maxc, status="active"):
        uid = conn.execute(
            "INSERT INTO users(username,password_hash,status,created_at,expires_at,max_connections) "
            "VALUES(?,?,?,?,?,?)", (name, "x", status, now, expires, maxc)).lastrowid
        conn.execute(
            "INSERT INTO protocol_accounts(user_id,protocol,uuid,secret,config,status,created_at) "
            "VALUES(?,?,?,?,?,?,?)", (uid, "zivpn", "u", "s", json.dumps({"password": pw}), "active", now))
        conn.commit()

    add_user("alice", "pw1", future, 0)
    add_user("bob", "pw2", future, 1)
    add_user("expired", "pw3", past, 0)
    add_user("off", "pw4", future, 0, status="disabled")
    conn.close()
    open(log, "w").close()

    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "scripts/zivpn-auth.py")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.2)

    def post(addr, auth):
        req = urllib.request.Request(
            "http://127.0.0.1:%d/auth" % port,
            data=json.dumps({"addr": addr, "auth": auth, "tx": 0}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.load(r)

    passed = failed = 0

    def check(name, cond):
        nonlocal passed, failed
        print(("PASS " if cond else "FAIL ") + name)
        passed, failed = passed + bool(cond), failed + (not cond)

    try:
        check("valid password allowed", post("1.1.1.1:1", "pw1") == {"ok": True, "id": "alice"})
        check("bad password denied", post("1.1.1.1:2", "nope")["ok"] is False)
        check("expired user denied", post("1.1.1.1:3", "pw3")["ok"] is False)
        check("disabled user denied", post("1.1.1.1:4", "pw4")["ok"] is False)
        check("userpass form allowed", post("9.9.9.9:1", "alice:pw1")["ok"] is True)
        check("1st connection allowed", post("2.2.2.2:1", "pw2")["ok"] is True)
        check("2nd connection denied (max=1)", post("2.2.2.2:2", "pw2")["ok"] is False)
        online = json.load(open(os.path.join(tmp, "zivpn-online.json")))
        check("online state mirrors sessions", online.get("bob") == 1 and online.get("alice", 0) >= 1)

        with open(log, "a") as fh:
            fh.write('2026-01-01T00:00:00Z\tINFO\tclient disconnected\t{"addr": "2.2.2.2:1", "error": "x"}\n')
        time.sleep(3)
        check("reconnect allowed after disconnect", post("2.2.2.2:3", "pw2")["ok"] is True)
    finally:
        proc.terminate()
        proc.wait()

    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
