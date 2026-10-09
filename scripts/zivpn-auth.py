#!/usr/bin/env python3
"""ZIVPN HTTP auth endpoint (the ZIVPN/Hysteria-v1 build supports ``auth.mode: "http"``).

For every new client connection the ZIVPN server POSTs::

    {"addr": "1.2.3.4:5678", "auth": "<what the client sent>", "tx": 0}

and expects ``{"ok": <bool>, "id": "<string>"}`` back. We validate against the panel DB
(read-only) so access follows the panel exactly - unlike the static ``passwords`` mode this
enforces expiry, disable and max-connections:

  * the user is ``active`` and not expired
  * they have a ``zivpn`` protocol account
  * the password (or ``user:pass``) matches that account
  * their live connections < ``max_connections`` (0 = unlimited)

Connection tracking: the addr is registered on a successful auth and removed again when the
ZIVPN server logs ``client disconnected`` for it. The adapter redirects the ZIVPN unit's output
to ``ZIVPN_LOG`` for this. The current counts are mirrored to ``UVPN_DATA/zivpn-online.json``
so the panel dashboard can show them.

Stdlib only, loopback only. Never logs a password.
"""
import json
import os
import re
import socket
import sqlite3
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB = os.environ.get("UVPN_DB", "/var/lib/unified-vpn/database.db")
DATA = os.environ.get("UVPN_DATA", "/var/lib/unified-vpn")
PORT = int(os.environ.get("ZIVPN_AUTH_PORT", "18099"))
LOG = os.environ.get("ZIVPN_LOG", "/var/log/unified-vpn/zivpn.log")
ONLINE_FILE = os.path.join(DATA, "zivpn-online.json")

_addr_re = re.compile(r'"addr"\s*:\s*"([^"]+)"')
_lock = threading.Lock()
_sessions = {}          # addr -> {"user": str|None, "ts": float}


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _active_accounts():
    """[(username, password, max_connections)] for active, unexpired zivpn accounts."""
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=10)
    except sqlite3.Error:
        return []
    try:
        rows = conn.execute(
            "SELECT u.username, u.max_connections, pa.config FROM users u "
            "JOIN protocol_accounts pa ON pa.user_id = u.id AND pa.protocol = 'zivpn' AND pa.status = 'active' "
            "WHERE u.status = 'active' AND u.expires_at > ?", (_now_iso(),)).fetchall()
    finally:
        conn.close()
    out = []
    for username, maxc, cfg in rows:
        try:
            pw = (json.loads(cfg or "{}") or {}).get("password")
        except ValueError:
            pw = None
        if pw:
            out.append((username, pw, int(maxc or 0)))
    return out


def _match(accounts, auth):
    if not auth:
        return None
    if ":" in auth:                                   # allow "username:password" (userpass style)
        u, p = auth.split(":", 1)
        for username, pw, maxc in accounts:
            if username.lower() == u.lower() and pw == p:
                return username, maxc
    for username, pw, maxc in accounts:               # plain per-user password
        if pw == auth:
            return username, maxc
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
        fd, tmp = tempfile.mkstemp(dir=DATA, prefix=".zivpn-online-")
        with os.fdopen(fd, "w") as fh:
            json.dump(counts, fh)
        os.replace(tmp, ONLINE_FILE)
    except (IOError, OSError):
        pass


def authorize(addr, auth):
    user = _match(_active_accounts(), auth)
    if not user:
        return False, ""
    username, maxc = user
    with _lock:
        cur = _sessions.get(addr)
        if not (cur and cur.get("user") == username):
            if maxc and _count(username) >= maxc:
                return False, ""
            _sessions[addr] = {"user": username, "ts": time.time()}
            _flush()
        else:
            cur["ts"] = time.time()
    return True, username


def _handle_log_line(line):
    if "client disconnected" in line:
        m = _addr_re.search(line)
        if m:
            with _lock:
                if _sessions.pop(m.group(1), None):
                    _flush()
    elif "client connected" in line:
        m = _addr_re.search(line)
        if m:
            addr = m.group(1)
            with _lock:
                _sessions.setdefault(addr, {"user": None, "ts": time.time()})


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
        ok, ident = authorize(str(req.get("addr") or ""), req.get("auth") or "")
        body = json.dumps({"ok": bool(ok), "id": ident}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main():
    if not os.path.exists(DB):
        sys.stderr.write("zivpn-auth: DB not found at %s\n" % DB)
    t = threading.Thread(target=_tail)
    t.daemon = True
    t.start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    srv.daemon_threads = True
    sys.stderr.write("zivpn-auth: listening on 127.0.0.1:%d (db=%s, log=%s)\n" % (PORT, DB, LOG))
    sys.stderr.flush()
    srv.serve_forever()


if __name__ == "__main__":
    main()
