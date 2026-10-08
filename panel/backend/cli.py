"""unified-vpn CLI (wrapper: /usr/local/bin/unified-vpn). Interactive menu when run without arguments."""
import argparse
import getpass
import os
import sys

from adapters import all_adapters, get_adapter
from backend import db, health, maintenance, security, servicemgr, usermgr


def cmd_init_db(a):
    db.init_db().close()
    print("database ready")


def cmd_create_admin(a):
    pw = os.environ.get("UVPN_ADMIN_PASS") or getpass.getpass("Admin password: ")
    if a.username.lower() == "admin" and pw == "admin":
        sys.exit("admin/admin is not allowed")
    if not a.username or len(a.username) < 3 or not a.username.replace("_", "").replace("-", "").isalnum():
        sys.exit("admin username: min 3 chars, letters/digits/_/-")
    security.validate_password(pw, min_len=10)
    conn = db.init_db()
    if conn.execute("SELECT 1 FROM admins WHERE username=?", (a.username,)).fetchone():
        conn.execute("UPDATE admins SET password_hash=?, failed_attempts=0, locked_until=NULL WHERE username=?",
                     (security.hash_password(pw), a.username))
    else:
        conn.execute("INSERT INTO admins(username, password_hash, role, created_at) VALUES(?,?,?,?)",
                     (a.username, security.hash_password(pw), a.role, db.now_iso()))
    conn.commit()
    db.audit(conn, "admin.create", a.username)
    print("admin '%s' saved" % a.username)


def cmd_set_setting(a):
    conn = db.init_db()
    db.set_setting(conn, a.key, a.value)


def cmd_adapter_install(a):
    opts = dict(kv.split("=", 1) for kv in (a.opt or []))
    ad = get_adapter(a.name)
    ad.install(opts)
    print("installed: %s" % a.name)


def cmd_adapter_uninstall(a):
    get_adapter(a.name).uninstall()
    print("uninstalled: %s" % a.name)


def cmd_health(a):
    bad = 0
    for item in health.run_all():
        print("[%s] %s" % ("OK" if item["ok"] else "FAIL", item["component"]))
        for c in item["checks"]:
            if not c["ok"]:
                bad += 1
                print("      - %s %s" % (c["name"], c["msg"]))
    sys.exit(1 if bad else 0)


def cmd_users(a):
    conn = db.connect()
    for u in usermgr.list_users(conn):
        print("%-4s %-20s %-9s %-20s %s" % (u["id"], u["username"], u["status"], u["expires_at"], ",".join(u["protocols"])))


def cmd_maintenance(a):
    sys.exit(maintenance.run())


def _ask(prompt, default=""):
    v = input("%s%s: " % (prompt, " [%s]" % default if default else "")).strip()
    return v or default


def menu():
    conn = db.init_db()
    while True:
        print("\n=== Unified VPN Panel ===\n1) List users\n2) Add user\n3) Delete user\n4) Renew user\n"
              "5) Disable / enable user\n6) Services status\n7) Restart a service\n8) Health check\n9) Backup now\n0) Exit")
        c = input("> ").strip()
        try:
            if c == "1":
                cmd_users(None)
            elif c == "2":
                avail = [p for p in ("ssh", "openvpn", "vless", "vmess", "trojan", "reality", "hysteria2", "wireguard", "zivpn")
                         if usermgr.adapter_for(p).installed()]
                print("available protocols:", ", ".join(avail) or "(none installed)")
                data = {"username": _ask("username"), "password": getpass.getpass("password: "),
                        "days": _ask("days", "30"), "max_connections": _ask("max connections", "1"),
                        "protocols": [p.strip() for p in _ask("protocols (comma separated)", ",".join(avail)).split(",") if p.strip()]}
                print("created id", usermgr.create(conn, data))
            elif c == "3":
                uid = int(_ask("user id"))
                if _ask("really delete? type yes") == "yes":
                    usermgr.delete(conn, uid)
            elif c == "4":
                usermgr.renew(conn, int(_ask("user id")), _ask("days", "30"))
            elif c == "5":
                uid = int(_ask("user id"))
                usermgr.set_status(conn, uid, "disabled" if _ask("action (disable/enable)", "disable") == "disable" else "active")
            elif c == "6":
                for s in servicemgr.list_services():
                    print("%-24s %s" % (s["name"], s["state"]))
            elif c == "7":
                name = _ask("service name")
                print(servicemgr.control("restart", name))
            elif c == "8":
                for item in health.run_all():
                    print("[%s] %s" % ("OK" if item["ok"] else "FAIL", item["component"]))
            elif c == "9":
                from backend import backup
                print(backup.create())
            elif c == "0":
                return
        except Exception as exc:
            print("ERROR:", exc)


def main():
    p = argparse.ArgumentParser(prog="unified-vpn")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("init-db").set_defaults(fn=cmd_init_db)
    s = sub.add_parser("create-admin")
    s.add_argument("--username", required=True)
    s.add_argument("--role", default="superadmin", choices=["superadmin", "admin", "support"])
    s.set_defaults(fn=cmd_create_admin)
    s = sub.add_parser("set-setting")
    s.add_argument("key")
    s.add_argument("value")
    s.set_defaults(fn=cmd_set_setting)
    s = sub.add_parser("adapter-install")
    s.add_argument("name")
    s.add_argument("--opt", action="append", help="key=value")
    s.set_defaults(fn=cmd_adapter_install)
    s = sub.add_parser("adapter-uninstall")
    s.add_argument("name")
    s.set_defaults(fn=cmd_adapter_uninstall)
    sub.add_parser("health").set_defaults(fn=cmd_health)
    sub.add_parser("users").set_defaults(fn=cmd_users)
    sub.add_parser("maintenance").set_defaults(fn=cmd_maintenance)
    a = p.parse_args()
    if a.cmd:
        a.fn(a)
    else:
        menu()


if __name__ == "__main__":
    main()
