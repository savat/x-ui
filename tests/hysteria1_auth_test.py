#!/usr/bin/env python3
"""End-to-end test for scripts/hysteria1-auth.py (Hysteria 1 external HTTP auth).

Stdlib only, no root: builds a throwaway DB from database/schema.sql, starts the auth service on a
loopback port and drives it the way the Hysteria 1 server does (payload = base64 of the client
credential). Connection tracking is exercised by appending the server's real "Client disconnected"
log lines to the file the service tails.

    python3 tests/hysteria1_auth_test.py
"""
import base64
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
    tmp = tempfile.mkdtemp(prefix="hy1-auth-")
    db = os.path.join(tmp, "database.db")
    log = os.path.join(tmp, "hysteria1.log")
    auth_port = 18131
    os.environ.update(UVPN_DB=db, UVPN_DATA=tmp, HYSTERIA1_AUTH_PORT=str(auth_port), HYSTERIA1_LOG=log)
    open(log, "w").close()

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    future = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
    past = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))

    conn = sqlite3.connect(db)
    conn.executescript(open(os.path.join(ROOT, "database/schema.sql")).read())

    def add_user(name, secret, expires, maxc, status="active"):
        uid = conn.execute(
            "INSERT INTO users(username,password_hash,status,created_at,expires_at,max_connections) "
            "VALUES(?,?,?,?,?,?)", (name, "x", status, now, expires, maxc)).lastrowid
        conn.execute(
            "INSERT INTO protocol_accounts(user_id,protocol,uuid,secret,config,status,created_at) "
            "VALUES(?,?,?,?,?,?,?)", (uid, "hysteria1", "u", secret, "{}", "active", now))
        conn.commit()

    add_user("alice", "alicesecret", future, 0)
    add_user("bob", "bobsecret", future, 1)
    add_user("expired", "expsecret", past, 0)
    add_user("off", "offsecret", future, 0, status="disabled")
    conn.close()

    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "scripts/hysteria1-auth.py")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.2)

    def post(raw, addr):
        body = json.dumps({"addr": addr, "payload": base64.b64encode(raw.encode()).decode(),
                           "send": 0, "recv": 0}).encode()
        req = urllib.request.Request("http://127.0.0.1:%d/auth" % auth_port, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.load(r)

    def disconnect(addr):
        with open(log, "a") as fh:
            fh.write("2026-01-01T00:00:00Z [INFO] [src:%s] Client disconnected\n" % addr)
        time.sleep(3)                                   # the tail thread polls every 2s

    def online():
        try:
            return json.load(open(os.path.join(tmp, "hysteria1-online.json")))
        except (IOError, OSError, ValueError):
            return {}

    passed = failed = 0

    def check(name, cond):
        nonlocal passed, failed
        print(("PASS " if cond else "FAIL ") + name)
        passed, failed = passed + bool(cond), failed + (not cond)

    try:
        check("valid secret allowed", post("alicesecret", "10.0.0.1:1000") == {"ok": True, "msg": "alice"})
        check("user:pass allowed", post("alice:alicesecret", "10.0.0.2:2000")["ok"] is True)
        check("bad credential denied", post("nope", "10.0.0.1:1000")["ok"] is False)
        check("expired user denied", post("expsecret", "10.0.0.1:1000")["ok"] is False)
        check("disabled user denied", post("offsecret", "10.0.0.1:1000")["ok"] is False)

        check("online counts both alice connections", online() == {"alice": 2})

        check("bob first connection allowed", post("bobsecret", "10.0.0.3:3000")["ok"] is True)
        check("bob over max-connections denied", post("bobsecret", "10.0.0.4:4000") == {"ok": False, "msg": "too many connections"})
        disconnect("10.0.0.3:3000")
        check("bob allowed again after disconnect", post("bobsecret", "10.0.0.5:5000")["ok"] is True)
        check("online reflects live sessions", online() == {"alice": 2, "bob": 1})

        disconnect("10.0.0.1:1000")
        check("alice count drops after disconnect", online() == {"alice": 1, "bob": 1})
    finally:
        proc.terminate()
        proc.wait()

    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
