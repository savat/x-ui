"""User manager: the only place that coordinates DB state and adapters.

Order matters: the DB status is written FIRST so declarative adapters (Xray/ZIVPN), which render
their config from the DB, see the new state when sync() runs.
"""
import json
import logging
from datetime import timedelta

from adapters import AdapterError, PROTOCOLS, adapter_for
from backend import db, security

log = logging.getLogger("uvpn.users")


def _ctx(row, password=None):
    d = {"id": row["id"], "username": row["username"], "expires_at": row["expires_at"],
         "max_connections": row["max_connections"], "max_devices": row["max_devices"], "status": row["status"]}
    if password:
        d["password"] = password
    return d


def get_user(conn, uid):
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        raise KeyError("user not found")
    return row


def accounts_of(conn, uid):
    return [db.row_account(r) for r in conn.execute(
        "SELECT * FROM protocol_accounts WHERE user_id=? ORDER BY id", (uid,))]


def _save_account(conn, acct, status=None):
    conn.execute("UPDATE protocol_accounts SET config=?, status=COALESCE(?, status) WHERE id=?",
                 (json.dumps(acct["config"]), status, acct["id"]))


def _int(v, lo, hi, name):
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise ValueError("%s must be a number" % name)
    if not lo <= v <= hi:
        raise ValueError("%s must be between %d and %d" % (name, lo, hi))
    return v


# ---------------------------------------------------------------- provisioning
def _provision(conn, uid, password=None):
    row = get_user(conn, uid)
    ctx = _ctx(row, password)
    touched = {}
    for acct in accounts_of(conn, uid):
        ad = adapter_for(acct["protocol"])
        res = ad.create_user(ctx, acct) or {}
        acct["config"].update(res)
        _save_account(conn, acct, "active")
        touched[ad.name] = ad
    for ad in touched.values():
        ad.sync()
    conn.commit()


def _revoke(conn, uid):
    row = get_user(conn, uid)
    ctx = _ctx(row)
    errors, touched = [], {}
    for acct in accounts_of(conn, uid):
        ad = adapter_for(acct["protocol"])
        try:
            ad.revoke_user(ctx, acct)
            touched.setdefault(ad.name, (ad, []))[1].append(acct)
        except Exception as exc:
            errors.append("%s: %s" % (acct["protocol"], exc))
            _save_account(conn, acct, "revoke_failed")
    for ad, accts in touched.values():
        try:
            ad.sync()
            for a in accts:
                _save_account(conn, a, "revoked")
        except Exception as exc:
            errors.append("%s sync: %s" % (ad.name, exc))
            for a in accts:
                _save_account(conn, a, "revoke_failed")
    conn.commit()
    if errors:
        raise AdapterError("; ".join(errors))


# ---------------------------------------------------------------- operations
def create(conn, data):
    username = security.validate_username(data.get("username"))
    password = security.validate_password(data.get("password"), min_len=1)
    days = _int(data.get("days", 30), 1, 3650, "days")
    max_conn = _int(data.get("max_connections", 1), 0, 1000, "max_connections")
    max_dev = _int(data.get("max_devices", 0), 0, 1000, "max_devices")
    protocols = data.get("protocols") or []
    if not isinstance(protocols, list) or not protocols:
        raise ValueError("select at least one protocol")
    protocols = list(dict.fromkeys(protocols))
    for p in protocols:
        if p not in PROTOCOLS:
            raise ValueError("unknown protocol: %s" % p)
        if not adapter_for(p).installed():
            raise ValueError("protocol '%s' is not installed on this server" % p)
    if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        raise ValueError("username already exists")
    now = db.utcnow()
    cur = conn.execute(
        "INSERT INTO users(username, password_hash, status, created_at, expires_at, max_devices, max_connections, note) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (username, security.hash_password(password), "active", db.iso(now), db.iso(now + timedelta(days=days)),
         max_dev, max_conn, str(data.get("note", ""))[:200]))
    uid = cur.lastrowid
    conn.commit()
    ctx = _ctx(get_user(conn, uid), password)
    done, touched = [], {}
    try:
        for p in protocols:
            ad = adapter_for(p)
            acct = {"protocol": p, "uuid": security.gen_uuid(), "secret": security.gen_secret(), "config": {}}
            acct["id"] = conn.execute(
                "INSERT INTO protocol_accounts(user_id, protocol, uuid, secret, config, status, created_at) "
                "VALUES(?,?,?,?,?,?,?)", (uid, p, acct["uuid"], acct["secret"], "{}", "active", db.now_iso())).lastrowid
            conn.commit()
            acct["config"].update(ad.create_user(ctx, acct) or {})
            _save_account(conn, acct)
            done.append((ad, acct))
            touched[ad.name] = ad
        for ad in touched.values():
            ad.sync()
        conn.commit()
    except Exception:
        log.exception("create user failed, rolling back")
        for ad, acct in done:
            try:
                ad.delete_user(ctx, acct)
            except Exception:
                log.exception("rollback delete_user failed")
        conn.execute("DELETE FROM users WHERE id=?", (uid,))
        conn.commit()
        for ad in touched.values():
            try:
                ad.sync()
            except Exception:
                log.exception("rollback sync failed")
        raise
    return uid


def delete(conn, uid):
    row = get_user(conn, uid)
    ctx = _ctx(row)
    touched = {}
    for acct in accounts_of(conn, uid):
        ad = adapter_for(acct["protocol"])
        ad.delete_user(ctx, acct)          # raises -> DB row kept so the admin can retry
        touched[ad.name] = ad
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    for ad in touched.values():
        ad.sync()


def set_status(conn, uid, status):
    row = get_user(conn, uid)
    if status == "disabled":
        conn.execute("UPDATE users SET status='disabled' WHERE id=?", (uid,))
        conn.commit()
        _revoke(conn, uid)
    elif status == "active":
        if db.parse(row["expires_at"]) <= db.utcnow():
            raise ValueError("account is expired - renew it instead")
        conn.execute("UPDATE users SET status='active' WHERE id=?", (uid,))
        conn.commit()
        _provision(conn, uid)
    else:
        raise ValueError("invalid status")


def renew(conn, uid, days):
    days = _int(days, 1, 3650, "days")
    row = get_user(conn, uid)
    base = max(db.utcnow(), db.parse(row["expires_at"]))
    conn.execute("UPDATE users SET expires_at=?, status='active' WHERE id=?", (db.iso(base + timedelta(days=days)), uid))
    conn.commit()
    _provision(conn, uid)


def reset_password(conn, uid, password):
    password = security.validate_password(password, min_len=1)
    get_user(conn, uid)
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (security.hash_password(password), uid))
    conn.commit()
    row = get_user(conn, uid)
    if row["status"] == "active":
        _provision(conn, uid, password)    # SSH: chpasswd once; ZIVPN: stored in the account config (shown to the user)


def update(conn, uid, data):
    row = get_user(conn, uid)
    sets, vals = [], []
    if "max_connections" in data:
        sets.append("max_connections=?"); vals.append(_int(data["max_connections"], 0, 1000, "max_connections"))
    if "max_devices" in data:
        sets.append("max_devices=?"); vals.append(_int(data["max_devices"], 0, 1000, "max_devices"))
    if "quota" in data:
        sets.append("quota=?"); vals.append(_int(data["quota"], 0, 2 ** 50, "quota"))
    if "note" in data:
        sets.append("note=?"); vals.append(str(data["note"])[:200])
    if sets:
        conn.execute("UPDATE users SET %s WHERE id=?" % ",".join(sets), vals + [uid])
        conn.commit()
    if "protocols" in data:
        _set_protocols(conn, uid, row, data["protocols"], data.get("password"))


def _set_protocols(conn, uid, row, protocols, password):
    if not isinstance(protocols, list) or not protocols:
        raise ValueError("select at least one protocol")
    want = set(protocols)
    have = dict((a["protocol"], a) for a in accounts_of(conn, uid))
    ctx = _ctx(row, security.validate_password(password, min_len=1) if password else None)
    for p in want - set(have):
        if p not in PROTOCOLS or not adapter_for(p).installed():
            raise ValueError("protocol '%s' unavailable" % p)
        if p in ("ssh", "zivpn") and not password:
            raise ValueError("password is required when adding %s to an existing user" % p)
    touched = {}
    for p in want - set(have):
        ad = adapter_for(p)
        acct = {"protocol": p, "uuid": security.gen_uuid(), "secret": security.gen_secret(), "config": {}}
        acct["id"] = conn.execute(
            "INSERT INTO protocol_accounts(user_id, protocol, uuid, secret, config, status, created_at) VALUES(?,?,?,?,?,?,?)",
            (uid, p, acct["uuid"], acct["secret"], "{}", "active", db.now_iso())).lastrowid
        conn.commit()
        if row["status"] == "active":
            acct["config"].update(ad.create_user(ctx, acct) or {})
            _save_account(conn, acct)
        touched[ad.name] = ad
    for p in set(have) - want:
        ad = adapter_for(p)
        ad.delete_user(ctx, have[p])
        conn.execute("DELETE FROM protocol_accounts WHERE id=?", (have[p]["id"],))
        touched[ad.name] = ad
    conn.commit()
    for ad in touched.values():
        ad.sync()


# ---------------------------------------------------------------- queries
def list_users(conn, q="", status="", protocol=""):
    sql = "SELECT u.*, (SELECT group_concat(protocol) FROM protocol_accounts WHERE user_id=u.id) AS protocols FROM users u WHERE 1=1"
    args = []
    if q:
        sql += " AND (u.username LIKE ? OR u.note LIKE ?)"
        args += ["%" + q + "%"] * 2
    if status in ("active", "expired", "disabled"):
        sql += " AND u.status=?"
        args.append(status)
    if protocol:
        sql += " AND EXISTS(SELECT 1 FROM protocol_accounts WHERE user_id=u.id AND protocol=?)"
        args.append(protocol)
    out = []
    for r in conn.execute(sql + " ORDER BY u.id DESC LIMIT 1000", args):
        d = dict(r)
        d.pop("password_hash", None)
        d["protocols"] = d["protocols"].split(",") if d["protocols"] else []
        out.append(d)
    return out


def share_info(conn, uid):
    row = get_user(conn, uid)
    hostinfo = {"host": db.get_setting(conn, "host", ""), "selfsigned": db.get_setting(conn, "tls_selfsigned") == "1",
                "reality_dest": db.get_setting(conn, "reality_dest", "")}
    if not hostinfo["host"]:
        raise ValueError("server host is not configured (Settings)")
    out = []
    for acct in accounts_of(conn, uid):
        res = adapter_for(acct["protocol"]).share(_ctx(row), acct, hostinfo)
        res["protocol"] = acct["protocol"]
        res["account_status"] = acct["status"]
        out.append(res)
    return out


def get_account(conn, uid, protocol):
    for a in accounts_of(conn, uid):
        if a["protocol"] == protocol:
            return a
    raise KeyError("user has no %s account" % protocol)
