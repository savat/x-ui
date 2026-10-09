#!/usr/bin/env python3
"""Hysteria 1 external authentication endpoint (loopback HTTP).

Hysteria 1 (the now end-of-life first generation of apernet/hysteria) has no built-in userpass, so
the adapter runs it with::

    "auth": {"mode": "external", "config": {"http": "http://127.0.0.1:18100/auth"}}

On every client connection the server POSTs::

    {"addr": "1.2.3.4:5678", "payload": "<base64 of what the client sent>", "send": .., "recv": ..}

and expects ``{"ok": <bool>, "msg": "<string>"}`` (HTTP 200 either way). We decode the payload and
validate it against the panel DB (read-only) so access follows the panel exactly - unlike the static
``passwords`` mode this enforces expiry, disable and max-connections:

  * the user is ``active`` and not expired
  * they have an ``active`` ``hysteria1`` protocol account
  * the credential (the account secret, or the chosen password) matches, either bare or as ``user:pass``
  * their live connections < ``max_connections`` (0 = unlimited)

Connection tracking: the addr is registered on a successful auth and removed again when the server
logs ``Client disconnected`` for the same ``src`` addr (the adapter redirects the server output to
``HYSTERIA1_LOG`` for this). Hysteria 1 has no connection gauge - ``hysteria_active_conn`` counts live
*streams*, not connections - so log tailing is what makes limits work. Counts are mirrored to
``UVPN_DATA/hysteria1-online.json`` for the panel dashboard.

Stdlib only, loopback only. Never logs a password.
"""
import base64
import json
import os
import re
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB = os.environ.get("UVPN_DB", "/var/lib/unified-vpn/database.db")
DATA = os.environ.get("UVPN_DATA", "/var/lib/unified-vpn")
PORT = int(os.environ.get("HYSTERIA1_AUTH_PORT", "18100"))
LOG = os.environ.get("HYSTERIA1_LOG", "/var/log/unified-vpn/hysteria1.log")
ONLINE_FILE = os.path.join(DATA, "hysteria1-online.json")
PROTOCOL = "hysteria1"

_addr_re = re.compile(r"\[src:([^\]]+)\]")
_lock = threading.Lock()
_sessions = {}          # addr -> {"user": str|None, "ts": float}


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _active_accounts():
    """[(username, {credentials...}, max_connections)] for active, unexpired hysteria1 accounts."""
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=10)
    except sqlite3.Error:
        return []
    try:
        rows = conn.execute(
            "SELECT u.username, u.max_connections, pa.secret, pa.config FROM users u "
            "JOIN protocol_accounts pa ON pa.user_id = u.id AND pa.protocol = ? AND pa.status = 'active' "
            "WHERE u.status = 'active' AND u.expires_at > ?", (PROTOCOL, _now_iso())).fetchall()
    finally:
        conn.close()
    out = []
    for username, maxc, secret, cfg in rows:
        creds = set()
        if secret:
            creds.add(secret)
        try:
            pw = (json.loads(cfg or "{}") or {}).get("password")
        except ValueError:
            pw = None
        if pw:
            creds.add(pw)
        if creds:
            out.append((username, creds, int(maxc or 0)))
    return out


def _match(accounts, raw):
    """Return (username, maxc) for a raw client credential, or None."""
    if not raw:
        return None
    u_part, sep, p_part = raw.partition(":")
    for username, creds, maxc in accounts:
        if raw in creds:                                          # bare secret/password
            return username, maxc
        if sep and u_part and u_part.lower() == username.lower() and p_part in creds:
            return username, maxc                                # user:pass
    return None


def _count(username):
    return sum(1 for s in _sessions.values() if s.get("user") == username)


def _flush():
    counts = {}
    for s in _sessions.values():
        if s.get("user"):
            counts[s["user"]] = counts.get(s["user"], 0) + 1
    try:
        os.makedirs(DATA, exist_ok=True)
        tmp = ONLINE_FILE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(counts, fh)
        os.replace(tmp, ONLINE_FILE)
    except (IOError, OSError):
        pass


def authorize(addr, raw):
    got = _match(_active_accounts(), raw)
    if not got:
        return False, "invalid credentials"
    username, maxc = got
    with _lock:
        cur = _sessions.get(addr)
        if not (cur and cur.get("user") == username):
            if maxc and _count(username) >= maxc:
                return False, "too many connections"
            _sessions[addr] = {"user": username, "ts": time.time()}
            _flush()
        else:
            cur["ts"] = time.time()
    return True, username


def _handle_log_line(line):
    # Hysteria 1 only logs the disconnect addr (no auth payload), so we key by the same src addr the
    # auth request used. "Client connected" is ignored - we already registered on auth success.
    if "Client disconnected" in line:
        m = _addr_re.search(line)
        if m:
            with _lock:
                if _sessions.pop(m.group(1), None):
                    _flush()


def _tail():
    fh, ino, pos = None, None, 0
    while True:
        try:
            st = os.stat(LOG)
            if fh is None or ino != st.st_ino or st.st_size < pos:   # new file / rotated (copytruncate)
                if fh:
                    fh.close()
                fh, ino, pos = open(LOG, "r", errors="replace"), st.st_ino, 0
            fh.seek(pos)
            while True:
                line = fh.readline()
                if not line:
                    break
                pos = fh.tell()
                _handle_log_line(line)
        except (IOError, OSError):
            pass
        time.sleep(2)


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            req = {}
        payload = req.get("payload") or ""
        try:
            if isinstance(payload, list):                    # Go []byte can be a JSON array too
                raw = base64.b64decode(bytes(payload)).decode("utf-8", "replace")
            else:
                raw = base64.b64decode(str(payload)).decode("utf-8", "replace")
        except Exception:
            raw = ""
        ok, msg = authorize(str(req.get("addr") or ""), raw)
        body = json.dumps({"ok": bool(ok), "msg": msg}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main():
    if not os.path.exists(DB):
        sys.stderr.write("hysteria1-auth: DB not found at %s\n" % DB)
    t = threading.Thread(target=_tail)
    t.daemon = True
    t.start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    srv.daemon_threads = True
    sys.stderr.write("hysteria1-auth: listening on 127.0.0.1:%d (db=%s, log=%s)\n" % (PORT, DB, LOG))
    sys.stderr.flush()
    srv.serve_forever()


if __name__ == "__main__":
    main()
