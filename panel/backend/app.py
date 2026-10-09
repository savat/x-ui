"""ZIVPN Panel - REST API (Flask). Bind to 127.0.0.1 only; nginx exposes it over HTTPS."""
import functools
import logging
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta

from flask import Flask, jsonify, request, send_file, send_from_directory, session

from adapters import AdapterError, all_adapters
from backend import backup, config, db, health, security, servicemgr, sysinfo, usermgr

log = logging.getLogger("uvpn.api")
FRONTEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
ROLE_PERMS = {"superadmin": {"read", "users", "system"}, "admin": {"read", "users"}, "support": {"read"}}
IDLE_TIMEOUT = 30 * 60
LOCK_AFTER, LOCK_MINUTES = 5, 15
_DUMMY_HASH = security.hash_password("dummy-password-for-timing")


class RateLimiter(object):
    def __init__(self):
        self.hits, self.lock = defaultdict(deque), threading.Lock()

    def allow(self, key, limit, window):
        now = time.time()
        with self.lock:
            q = self.hits[key]
            while q and q[0] < now - window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True


limiter = RateLimiter()


def client_ip():
    if request.remote_addr in ("127.0.0.1", "::1"):
        return request.headers.get("X-Real-IP", request.remote_addr)
    return request.remote_addr


def current_admin():
    aid = session.get("aid")
    if not aid:
        return None
    if time.time() - session.get("last", 0) > IDLE_TIMEOUT:
        session.clear()
        return None
    session["last"] = time.time()
    conn = db.connect()
    try:
        row = conn.execute("SELECT id, username, role FROM admins WHERE id=?", (aid,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def api(perm="read"):
    """Auth + role check + CSRF + rate limit + uniform error handling."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            admin = current_admin()
            if not admin:
                return jsonify(error="authentication required"), 401
            if perm not in ROLE_PERMS.get(admin["role"], ()):
                return jsonify(error="permission denied for role '%s'" % admin["role"]), 403
            if request.method not in ("GET", "HEAD"):
                tok = request.headers.get("X-CSRF-Token", "")
                if not tok or not secrets.compare_digest(tok, session.get("csrf", "")):
                    return jsonify(error="CSRF check failed"), 403
            if not limiter.allow("api:" + client_ip(), 300, 60):
                return jsonify(error="rate limit exceeded"), 429
            conn = db.connect()
            try:
                return fn(conn, admin, *a, **kw)
            except ValueError as e:
                return jsonify(error=str(e)), 400
            except KeyError as e:
                return jsonify(error=str(e.args[0]) if e.args else "not found"), 404
            except (AdapterError, RuntimeError) as e:
                log.error("%s: %s", request.path, e)
                return jsonify(error=security.redact(str(e))), 500
            finally:
                conn.close()
        return wrapper
    return deco


def create_app():
    app = Flask(__name__, static_folder=None)
    secret = os.environ.get("UVPN_SECRET_KEY")
    if not secret:
        raise SystemExit("UVPN_SECRET_KEY is not set (see %s/panel.env)" % config.CONF_DIR)
    app.config.update(
        SECRET_KEY=secret,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=os.environ.get("UVPN_INSECURE_COOKIES") != "1",
        SESSION_COOKIE_NAME="uvpn_session",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_REFRESH_EACH_REQUEST=False,
        MAX_CONTENT_LENGTH=64 * 1024,
        JSON_SORT_KEYS=False,
    )
    db.init_db().close()

    @app.after_request
    def headers(resp):
        resp.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                                   "script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ------------------------------------------------------------------ static
    @app.get("/")
    def index():
        return send_from_directory(FRONTEND, "index.html")

    @app.get("/assets/<path:name>")
    def assets(name):
        return send_from_directory(FRONTEND, name)

    # ------------------------------------------------------------------ auth
    @app.post("/api/auth/login")
    def login():
        ip = client_ip()
        if not limiter.allow("login:" + ip, 10, 300):
            return jsonify(error="too many attempts, try again later"), 429
        data = request.get_json(silent=True) or {}
        username, password = data.get("username"), data.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            return jsonify(error="invalid credentials"), 401
        conn = db.connect()
        try:
            row = conn.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
            if row and row["locked_until"] and row["locked_until"] > db.now_iso():
                security.verify_password(_DUMMY_HASH, password)
                db.audit(conn, "login.locked", username, ip=ip)
                return jsonify(error="invalid credentials"), 401
            good = security.verify_password(row["password_hash"] if row else _DUMMY_HASH, password) and row is not None
            if not good:
                if row:
                    fails = row["failed_attempts"] + 1
                    locked = db.iso(db.utcnow() + timedelta(minutes=LOCK_MINUTES)) if fails >= LOCK_AFTER else None
                    conn.execute("UPDATE admins SET failed_attempts=?, locked_until=? WHERE id=?",
                                 (0 if locked else fails, locked, row["id"]))
                    conn.commit()
                db.audit(conn, "login.failed", username[:64], ip=ip)
                return jsonify(error="invalid credentials"), 401
            conn.execute("UPDATE admins SET failed_attempts=0, locked_until=NULL, last_login=? WHERE id=?",
                         (db.now_iso(), row["id"]))
            conn.commit()
            session.clear()
            session.update(aid=row["id"], role=row["role"], csrf=secrets.token_urlsafe(32), last=time.time())
            session.permanent = True
            db.audit(conn, "login.ok", username, admin=dict(row), ip=ip)
            return jsonify(username=row["username"], role=row["role"], csrf=session["csrf"])
        finally:
            conn.close()

    @app.post("/api/auth/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/auth/me")
    def me():
        admin = current_admin()
        if not admin:
            return jsonify(error="authentication required"), 401
        return jsonify(username=admin["username"], role=admin["role"], csrf=session["csrf"])

    @app.post("/api/auth/password")
    @api("read")
    def change_password(conn, admin):
        d = request.get_json(silent=True) or {}
        row = conn.execute("SELECT password_hash FROM admins WHERE id=?", (admin["id"],)).fetchone()
        if not security.verify_password(row["password_hash"], d.get("current", "")):
            raise ValueError("current password is wrong")
        new = security.validate_password(d.get("new"), min_len=10)
        conn.execute("UPDATE admins SET password_hash=? WHERE id=?", (security.hash_password(new), admin["id"]))
        conn.commit()
        db.audit(conn, "admin.password_changed", admin=admin, ip=client_ip())
        return jsonify(ok=True)

    # ------------------------------------------------------------------ dashboard / health
    @app.get("/api/dashboard")
    @api("read")
    def dashboard(conn, admin):
        online = {}
        for ad in all_adapters().values():
            if ad.installed():
                for name, n in ad.online().items():
                    online[name] = online.get(name, 0) + n
        counts = dict((r["status"], r["c"]) for r in conn.execute("SELECT status, COUNT(*) c FROM users GROUP BY status"))
        data = sysinfo.snapshot()
        data.update(public_ip=db.get_setting(conn, "public_ip", ""), host=db.get_setting(conn, "host", ""),
                    online_users=len(online), online_connections=sum(online.values()), user_counts=counts,
                    protocols=[{"name": a.name, "label": a.label, "state": a.overall_status()} for a in all_adapters().values()],
                    services=servicemgr.list_services())
        return jsonify(data)

    @app.get("/api/health")
    @api("read")
    def health_check(conn, admin):
        return jsonify(health.run_all())

    # ------------------------------------------------------------------ users
    @app.get("/api/users")
    @api("read")
    def users_list(conn, admin):
        return jsonify(usermgr.list_users(conn, request.args.get("q", ""), request.args.get("status", ""),
                                          request.args.get("protocol", "")))

    @app.post("/api/users")
    @api("users")
    def users_create(conn, admin):
        d = request.get_json(silent=True) or {}
        uid = usermgr.create(conn, d)
        db.audit(conn, "user.create", d.get("username", ""), admin=admin, ip=client_ip())
        return jsonify(id=uid), 201

    def _uname(conn, uid):
        return usermgr.get_user(conn, uid)["username"]

    @app.get("/api/users/<int:uid>")
    @api("read")
    def users_get(conn, admin, uid):
        row = dict(usermgr.get_user(conn, uid))
        row.pop("password_hash", None)
        row["protocols"] = [a["protocol"] for a in usermgr.accounts_of(conn, uid)]
        return jsonify(row)

    @app.put("/api/users/<int:uid>")
    @api("users")
    def users_update(conn, admin, uid):
        usermgr.update(conn, uid, request.get_json(silent=True) or {})
        db.audit(conn, "user.update", _uname(conn, uid), admin=admin, ip=client_ip())
        return jsonify(ok=True)

    @app.delete("/api/users/<int:uid>")
    @api("users")
    def users_delete(conn, admin, uid):
        name = _uname(conn, uid)
        usermgr.delete(conn, uid)
        db.audit(conn, "user.delete", name, admin=admin, ip=client_ip())
        return jsonify(ok=True)

    @app.post("/api/users/<int:uid>/renew")
    @api("users")
    def users_renew(conn, admin, uid):
        usermgr.renew(conn, uid, (request.get_json(silent=True) or {}).get("days"))
        db.audit(conn, "user.renew", _uname(conn, uid), admin=admin, ip=client_ip())
        return jsonify(ok=True)

    @app.post("/api/users/<int:uid>/disable")
    @api("users")
    def users_disable(conn, admin, uid):
        usermgr.set_status(conn, uid, "disabled")
        db.audit(conn, "user.disable", _uname(conn, uid), admin=admin, ip=client_ip())
        return jsonify(ok=True)

    @app.post("/api/users/<int:uid>/enable")
    @api("users")
    def users_enable(conn, admin, uid):
        usermgr.set_status(conn, uid, "active")
        db.audit(conn, "user.enable", _uname(conn, uid), admin=admin, ip=client_ip())
        return jsonify(ok=True)

    @app.post("/api/users/<int:uid>/reset-password")
    @api("users")
    def users_reset(conn, admin, uid):
        usermgr.reset_password(conn, uid, (request.get_json(silent=True) or {}).get("password"))
        db.audit(conn, "user.reset_password", _uname(conn, uid), admin=admin, ip=client_ip())
        return jsonify(ok=True)

    @app.get("/api/users/<int:uid>/share")
    @api("users")
    def users_share(conn, admin, uid):
        db.audit(conn, "user.view_config", _uname(conn, uid), admin=admin, ip=client_ip())
        return jsonify(usermgr.share_info(conn, uid))

    # ------------------------------------------------------------------ protocols / services / logs
    @app.get("/api/protocols")
    @api("read")
    def protocols(conn, admin):
        return jsonify([{"name": a.name, "label": a.label, "installed": a.installed(), "state": a.overall_status(),
                         "units": a.status() if a.installed() else {}, "info": a.info()} for a in all_adapters().values()])

    @app.get("/api/services")
    @api("read")
    def services(conn, admin):
        return jsonify(servicemgr.list_services())

    @app.post("/api/services/<name>/<action>")
    @api("system")
    def service_action(conn, admin, name, action):
        state = servicemgr.control(action, name)
        db.audit(conn, "service.%s" % action, name, admin=admin, ip=client_ip())
        return jsonify(state=state)

    @app.get("/api/logs/<name>")
    @api("read")
    def logs(conn, admin, name):
        return jsonify(text=servicemgr.logs(name, request.args.get("lines", 200)))

    # ------------------------------------------------------------------ backups
    @app.get("/api/backups")
    @api("system")
    def backups_list(conn, admin):
        return jsonify(backup.list_backups())

    @app.post("/api/backups")
    @api("system")
    def backups_create(conn, admin):
        path = backup.create()
        db.audit(conn, "backup.create", os.path.basename(path), admin=admin, ip=client_ip())
        return jsonify(path=os.path.basename(path)), 201

    @app.get("/api/backups/<name>")
    @api("system")
    def backups_download(conn, admin, name):
        db.audit(conn, "backup.download", name, admin=admin, ip=client_ip())
        return send_file(backup.path_of(name), as_attachment=True, download_name=name)

    @app.delete("/api/backups/<name>")
    @api("system")
    def backups_delete(conn, admin, name):
        backup.delete(name)
        db.audit(conn, "backup.delete", name, admin=admin, ip=client_ip())
        return jsonify(ok=True)

    @app.post("/api/backups/<name>/restore")
    @api("system")
    def backups_restore(conn, admin, name):
        if (request.get_json(silent=True) or {}).get("confirm") != name:
            raise ValueError("send {\"confirm\": \"<backup name>\"} to confirm the restore")
        db.audit(conn, "backup.restore", name, admin=admin, ip=client_ip())
        backup.restore(name)
        return jsonify(ok=True, note="restore started; the panel will restart")

    # ------------------------------------------------------------------ settings / audit
    @app.get("/api/settings")
    @api("read")
    def settings_get(conn, admin):
        return jsonify(host=db.get_setting(conn, "host", ""), public_ip=db.get_setting(conn, "public_ip", ""),
                       tls_selfsigned=db.get_setting(conn, "tls_selfsigned") == "1")

    @app.put("/api/settings")
    @api("system")
    def settings_put(conn, admin):
        d = request.get_json(silent=True) or {}
        if "host" in d:
            db.set_setting(conn, "host", security.validate_host(d["host"]))
        db.audit(conn, "settings.update", ",".join(d.keys()), admin=admin, ip=client_ip())
        return jsonify(ok=True)

    @app.get("/api/audit")
    @api("read")
    def audit_list(conn, admin):
        n = max(1, min(int(request.args.get("limit", 100)), 500))
        return jsonify([dict(r) for r in conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (n,))])

    @app.errorhandler(404)
    def nf(_):
        return jsonify(error="not found"), 404

    @app.errorhandler(413)
    def too_big(_):
        return jsonify(error="request too large"), 413

    return app
