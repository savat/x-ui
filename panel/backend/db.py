"""SQLite helpers. Timestamps are always UTC."""
import json
import os
import sqlite3
from datetime import datetime, timedelta

from . import config

FMT = "%Y-%m-%dT%H:%M:%SZ"


def utcnow():
    return datetime.utcnow().replace(microsecond=0)


def iso(dt):
    return dt.strftime(FMT)


def now_iso():
    return iso(utcnow())


def parse(ts):
    return datetime.strptime(ts, FMT)


def connect():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _schema_path():
    for p in (os.path.join(config.HOME, "database/schema.sql"),
              os.path.join(os.path.dirname(__file__), "../../database/schema.sql")):
        if os.path.exists(p):
            return p
    raise IOError("schema.sql not found")


def init_db():
    conn = connect()
    with open(_schema_path()) as fh:
        conn.executescript(fh.read())
    conn.commit()
    try:
        os.chmod(config.DB_PATH, 0o600)
    except OSError:
        pass
    return conn


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()


def audit(conn, action, detail="", admin=None, ip=None):
    """Audit trail. Never pass passwords/tokens in `detail`."""
    conn.execute("INSERT INTO audit_logs(user_id, actor, action, detail, ip, created_at) VALUES(?,?,?,?,?,?)",
                 (admin["id"] if admin else None, admin["username"] if admin else "system",
                  action, detail[:500], ip, now_iso()))
    conn.commit()


def row_account(row):
    d = dict(row)
    try:
        d["config"] = json.loads(d.get("config") or "{}")
    except ValueError:
        d["config"] = {}
    return d


def active_accounts(conn, protocols):
    """Accounts that must currently be able to connect (user active and not expired)."""
    q = ",".join("?" for _ in protocols)
    rows = conn.execute(
        "SELECT pa.*, u.username, u.expires_at, u.max_connections FROM protocol_accounts pa "
        "JOIN users u ON u.id = pa.user_id WHERE u.status='active' AND u.expires_at > ? "
        "AND pa.protocol IN (%s) ORDER BY pa.id" % q, [now_iso()] + list(protocols)).fetchall()
    return [row_account(r) for r in rows]
