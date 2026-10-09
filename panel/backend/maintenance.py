"""Run every minute by unified-expiry.timer.

1. expire users whose expires_at passed and REVOKE them in every adapter (not just hide them)
2. retry revocations that failed earlier
Overlapping runs are prevented with a file lock.
"""
import fcntl
import logging
import os
import sys

from backend import config, db, usermgr

log = logging.getLogger("uvpn.maintenance")


def run():
    os.makedirs(config.DATA, exist_ok=True)
    lock = open(os.path.join(config.DATA, "maintenance.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        return 0
    conn = db.connect()
    failures = 0
    try:
        now = db.now_iso()
        for r in conn.execute("SELECT id, username FROM users WHERE status='active' AND expires_at<=?", (now,)).fetchall():
            conn.execute("UPDATE users SET status='expired' WHERE id=?", (r["id"],))
            conn.commit()
            db.audit(conn, "user.expired", r["username"])
        pending = conn.execute(
            "SELECT DISTINCT u.id, u.username FROM users u JOIN protocol_accounts pa ON pa.user_id=u.id "
            "WHERE u.status IN ('expired','disabled') AND pa.status != 'revoked'").fetchall()
        for r in pending:
            try:
                usermgr._revoke(conn, r["id"])
                db.audit(conn, "user.revoked", r["username"])
            except Exception as exc:
                failures += 1
                log.error("revoke failed for %s: %s", r["username"], exc)
                db.audit(conn, "user.revoke_failed", "%s: %s" % (r["username"], exc))
    finally:
        conn.close()
        fcntl.flock(lock, fcntl.LOCK_UN)
    return 1 if failures else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(run())
