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


_PROTO_ORDER = ("ssh", "openvpn", "vless", "vmess", "trojan", "reality", "hysteria2", "wireguard", "zivpn")
_PROTO_TH = {"ssh": "SSH", "openvpn": "OpenVPN", "vless": "VLESS", "vmess": "VMess", "trojan": "Trojan",
             "reality": "VLESS+Reality", "hysteria2": "Hysteria 2", "wireguard": "WireGuard", "zivpn": "ZIVPN (UDP)"}
_STATUS_TH = {"active": "ใช้งาน", "expired": "หมดอายุ", "disabled": "ปิด"}


def _color(s, code):
    if sys.stdout.isatty() and os.environ.get("NO_COLOR") is None:
        return "\033[%sm%s\033[0m" % (code, s)
    return s


def _ok(s):
    return _color(s, "1;32")


def _bad(s):
    return _color(s, "1;31")


def _title(s):
    return _color(s, "1;36")


def _dim(s):
    return _color(s, "2")


def _parse_protos(raw, avail):
    out = []
    for tok in raw.replace(" ", "").split(","):
        if not tok:
            continue
        if tok.isdigit():
            i = int(tok) - 1
            if 0 <= i < len(avail):
                out.append(avail[i])
                continue
            raise ValueError("หมายเลขโปรโตคอลไม่ถูกต้อง: %s" % tok)
        if tok in avail:
            out.append(tok)
        else:
            raise ValueError("ไม่รู้จักโปรโตคอล: %s" % tok)
    out = list(dict.fromkeys(out))
    if not out:
        raise ValueError("ต้องเลือกอย่างน้อย 1 โปรโตคอล")
    return out


def _print_users(conn, users=None):
    users = usermgr.list_users(conn) if users is None else users
    if not users:
        print(_dim("  (ยังไม่มีผู้ใช้)"))
        return
    print("  %-4s %-18s %-8s %-19s %s" % ("ID", "ชื่อผู้ใช้", "สถานะ", "หมดอายุ (UTC)", "โปรโตคอล"))
    print("  " + "-" * 78)
    for u in users:
        st = _STATUS_TH.get(u["status"], u["status"])
        print("  %-4s %-18s %-8s %-19s %s" % (u["id"], u["username"], st, u["expires_at"][:19], ",".join(u["protocols"])))


def _show_share(infos):
    for item in infos:
        print("    - %s" % _title(item["protocol"]))
        for link in item.get("links", []):
            print("        %s: %s" % (link.get("label", "link"), link["url"]))
        info = item.get("info") or {}
        if not item.get("links") and info:
            print("        " + ", ".join("%s=%s" % (k, v) for k, v in info.items()))


def _add_user(conn):
    avail = [p for p in _PROTO_ORDER if usermgr.adapter_for(p).installed()]
    if not avail:
        print(_bad("ยังไม่มีโปรโตคอลที่ติดตั้ง - รัน install.sh ก่อน"))
        return
    print(_title("โปรโตคอลที่ใช้ได้:"))
    for i, p in enumerate(avail, 1):
        print("  %d) %s" % (i, _PROTO_TH.get(p, p)))
    username = _ask("ชื่อผู้ใช้")
    password = getpass.getpass("รหัสผ่าน: ")
    days = _ask("จำนวนวัน", "30")
    maxc = _ask("จำนวน connection สูงสุด", "1")
    raw = _ask("เลือกโปรโตคอล (คั่นด้วย , หรือใส่หมายเลข)", ",".join(str(i) for i in range(1, len(avail) + 1)))
    try:
        protos = _parse_protos(raw, avail)
        uid = usermgr.create(conn, {"username": username, "password": password, "days": days,
                                    "max_connections": maxc, "protocols": protos})
    except Exception as exc:
        print(_bad("สร้างผู้ใช้ไม่สําเร็จ: %s" % exc))
        return
    print()
    print(_ok("สร้างผู้ใช้สําเร็จ  (id %d, ชื่อ %s)" % (uid, username)))
    _print_users(conn, usermgr.list_users(conn, q=username))
    try:
        print(_title("ข้อมูลเชื่อมต่อ (แชร์ให้ผู้ใช้):"))
        _show_share(usermgr.share_info(conn, uid))
    except Exception as exc:
        print(_dim("  (แสดงข้อมูลเชื่อมต่อไม่ได้: %s)" % exc))


def _list_admins(conn):
    return list(conn.execute("SELECT id, username, role FROM admins ORDER BY id"))


def _manage_admin(conn):
    while True:
        rows = _list_admins(conn)
        print(_title("ผู้ดูแลระบบ (Panel admin):"))
        if rows:
            print("  %-4s %-22s %s" % ("ID", "ชื่อผู้ใช้", "สิทธิ์"))
            for r in rows:
                print("  %-4s %-22s %s" % (r["id"], r["username"], r["role"]))
        else:
            print(_dim("  (ยังไม่มีผู้ดูแลระบบ - กด [a] เพื่อเพิ่มได้เลย)"))
        print("  [a] เพิ่ม/แก้ไขผู้ดูแล   [d] ลบผู้ดูแล   [Enter] กลับ")
        act = input(_title("เลือก > ")).strip().lower()
        if not act:
            return
        if act == "a":
            username = _ask("ชื่อผู้ใช้ผู้ดูแล")
            if not username:
                print(_bad("ต้องระบุชื่อผู้ใช้"))
                continue
            pw = getpass.getpass("รหัสผ่าน (ขั้นต่ำ 10 ตัว): ")
            try:
                security.validate_password(pw, min_len=10)
            except ValueError as exc:
                print(_bad(str(exc)))
                continue
            role = _ask("สิทธิ์ (superadmin/admin/support)", "superadmin")
            if role not in ("superadmin", "admin", "support"):
                print(_bad("สิทธิ์ไม่ถูกต้อง"))
                continue
            if conn.execute("SELECT 1 FROM admins WHERE username=?", (username,)).fetchone():
                conn.execute("UPDATE admins SET password_hash=?, role=?, failed_attempts=0, locked_until=NULL WHERE username=?",
                             (security.hash_password(pw), role, username))
                db.audit(conn, "admin.update", username)
                print(_ok("อัปเดตผู้ดูแล '%s' แล้ว" % username))
            else:
                conn.execute("INSERT INTO admins(username, password_hash, role, created_at) VALUES(?,?,?,?)",
                             (username, security.hash_password(pw), role, db.now_iso()))
                db.audit(conn, "admin.create", username)
                print(_ok("เพิ่มผู้ดูแล '%s' แล้ว" % username))
            conn.commit()
        elif act == "d":
            username = _ask("ชื่อผู้ใช้ผู้ดูแลที่จะลบ")
            if not username:
                continue
            total = conn.execute("SELECT COUNT(*) AS c FROM admins").fetchone()["c"]
            if total <= 1:
                print(_bad("ลบไม่ได้: ต้องเหลือผู้ดูแลอย่างน้อย 1 คน"))
                continue
            cur = conn.execute("DELETE FROM admins WHERE username=?", (username,))
            conn.commit()
            if cur.rowcount:
                db.audit(conn, "admin.delete", username)
                print(_ok("ลบผู้ดูแล '%s' แล้ว" % username))
            else:
                print(_bad("ไม่พบผู้ดูแล '%s'" % username))
        else:
            print(_bad("ไม่รู้จักตัวเลือก: %s" % act))


def _reset_password(conn):
    uid = int(_ask("รหัสผู้ใช้ (ID)"))
    pw = getpass.getpass("รหัสผ่านใหม่: ")
    usermgr.reset_password(conn, uid, pw)
    print(_ok("รีเซ็ตรหัสผู้ใช้ id %d แล้ว" % uid))


def _show_services():
    for s in servicemgr.list_services():
        state = _ok(s["state"]) if s["state"] == "RUNNING" else _dim(s["state"])
        print("  %-26s %s" % (s["name"], state))


def _health_report():
    bad = 0
    for item in health.run_all():
        print("  [%s] %s" % (_ok("OK") if item["ok"] else _bad("FAIL"), item["component"]))
        for ch in item["checks"]:
            if not ch["ok"]:
                bad += 1
                print("        - %s %s" % (ch["name"], ch["msg"]))
    print(_ok("สุขภาพระบบปกติ") if not bad else _bad("พบปัญหา %d รายการ" % bad))


_MENU = """
  ── ผู้ใช้ ─────────────────────────────
   1) รายการผู้ใช้           2) เพิ่มผู้ใช้ใหม่
   3) รีเซ็ตรหัสผู้ใช้       4) ต่ออายุผู้ใช้
   5) เปิด/ปิดใช้งาน        6) ลบผู้ใช้
  ── ระบบ ──────────────────────────────
   7) จัดการผู้ดูแลระบบ
   8) สถานะบริการ           9) รีสตาร์ทบริการ
  10) ตรวจสุขภาพระบบ       11) สำรองข้อมูล
  ─────────────────────────────────────
   0) ออก
"""


def menu():
    conn = db.init_db()
    while True:
        host = db.get_setting(conn, "host", "") or "?"
        admins = _list_admins(conn)
        print()
        print(_title("  ╔══════════════════════════════════════"))
        print(_title("  ║  Unified VPN Panel  -  เมนูจัดการ"))
        print(_title("  ╚══════════════════════════════════════"))
        print(_dim("   server: %s%s" % (host, "" if admins else "   (ยังไม่มีผู้ดูแลระบบ)")))
        print(_MENU)
        c = input(_title("  เลือกเมนู > ")).strip()
        try:
            if c in ("1", ""):
                _print_users(conn)
            elif c == "2":
                _add_user(conn)
            elif c == "3":
                _reset_password(conn)
            elif c == "4":
                uid = int(_ask("รหัสผู้ใช้ (ID)"))
                usermgr.renew(conn, uid, _ask("จำนวนวัน", "30"))
                print(_ok("ต่ออายุผู้ใช้ id %d แล้ว" % uid))
            elif c == "5":
                uid = int(_ask("รหัสผู้ใช้ (ID)"))
                act = _ask("ทำอะไร (ปิด=disable / เปิด=enable)", "disable")
                usermgr.set_status(conn, uid, "active" if act in ("enable", "เปิด", "1") else "disabled")
                print(_ok("อัปเดตสถานะผู้ใช้ id %d แล้ว" % uid))
            elif c == "6":
                uid = int(_ask("รหัสผู้ใช้ (ID)"))
                if _ask("ยืนยันลบ? พิมพ์ yes") == "yes":
                    usermgr.delete(conn, uid)
                    print(_ok("ลบผู้ใช้ id %d แล้ว" % uid))
            elif c == "7":
                _manage_admin(conn)
            elif c == "8":
                _show_services()
            elif c == "9":
                name = _ask("ชื่อบริการ")
                print(_ok("สถานะ: %s" % servicemgr.control("restart", name)))
            elif c == "10":
                _health_report()
            elif c == "11":
                from backend import backup
                print(_ok("สำรองข้อมูลแล้ว: %s" % backup.create()))
            elif c == "0":
                print(_dim("ออกจากเมนู"))
                return
            else:
                print(_bad("ไม่รู้จักเมนู: %s" % c))
        except Exception as exc:
            print(_bad("ผิดพลาด: %s" % exc))


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
