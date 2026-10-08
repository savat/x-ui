#!/opt/unified-vpn/venv/bin/python
"""OpenVPN auth-user-pass-verify (via-env). Exit 0 = allow, 1 = deny.

Checks the panel DB: user active, not expired, has an openvpn account, password OK,
and current connections < max_connections. Never logs the password.
"""
import os
import sqlite3
import sys
import syslog
from datetime import datetime

HOME = os.environ.get("UVPN_HOME", "/opt/unified-vpn")
sys.path[:0] = [HOME, os.path.join(HOME, "panel")]
DB = os.environ.get("UVPN_DB", "/var/lib/unified-vpn/database.db")
VARLOG = os.environ.get("UVPN_VARLOG", "/var/log")


def deny(reason, user):
    syslog.syslog(syslog.LOG_WARNING, "uvpn openvpn auth denied for %r: %s" % (user[:32], reason))
    sys.exit(1)


def main():
    user, pw = os.environ.get("username", ""), os.environ.get("password", "")
    if not user or not pw:
        deny("empty credentials", user)
    from backend.security import verify_password
    from adapters.openvpn.status import count_for
    conn = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=10)
    row = conn.execute(
        "SELECT u.password_hash, u.status, u.expires_at, u.max_connections FROM users u "
        "JOIN protocol_accounts pa ON pa.user_id=u.id AND pa.protocol='openvpn' WHERE u.username=?", (user,)).fetchone()
    conn.close()
    if not row:
        verify_password("scrypt$AA==$AA==", pw)       # keep timing similar
        deny("unknown user", user)
    pw_hash, status, expires, max_conn = row
    if not verify_password(pw_hash, pw):
        deny("bad password", user)
    if status != "active" or expires <= datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"):
        deny("account %s" % ("expired" if status == "expired" else status), user)
    if max_conn and count_for(user, VARLOG) >= max_conn:
        deny("connection limit reached", user)
    sys.exit(0)


if __name__ == "__main__":
    main()
