# ZIVPN Panel

แผงควบคุมสำหรับเซิร์ฟเวอร์ **ZIVPN (UDP)** อย่างเดียว ติดตั้งด้วยคำสั่งเดียว แล้วจัดการผู้ใช้ผ่าน Web Panel หรือ CLI (`m`)

## ติดตั้ง

```bash
# บน VPS ใหม่ (Ubuntu 20.04/22.04/24.04, Debian 11/12) ด้วย root
git clone <repo-url> zivpn-panel && cd zivpn-panel
bash install.sh
```

ตัวติดตั้งจะถาม: โดเมน (เว้นว่าง = ใช้ IP + self-signed), พอร์ตภายใน Panel, และจะตั้ง admin ตอนนี้หรือไม่ จากนั้นติดตั้ง ZIVPN ให้อัตโนมัติ (ไม่ต้องเลือกโปรโตคอลแล้ว)
แบบ non-interactive: `UVPN_NONINTERACTIVE=1 UVPN_DOMAIN=panel.example.com UVPN_ADMIN_USER=boss UVPN_ADMIN_PASS=... UVPN_ASSUME_YES=1 bash install.sh`

**สำคัญ:** เก็บไฟล์ `/opt/unified-vpn/config/backup.key` ไว้ที่ปลอดภัย — backup เข้ารหัสด้วยคีย์นี้ ถ้าไม่มีจะ restore ไม่ได้

## ใช้งาน

| สิ่งที่ทำ | วิธี |
|---|---|
| Web Panel | URL ของ Vercel (เช่น `https://<project>.vercel.app`) หรือ `https://<โดเมน-VPS>/` (UI สำรองที่ Flask เสิร์ฟเอง) |
| CLI เมนู | `m` (หรือ `unified-vpn`) — เมนูภาษาไทย |
| จัดการผู้ดูแลระบบ | เมนู `m` → `7) จัดการผู้ดูแลระบบ` หรือ `unified-vpn create-admin --username NAME` |
| ตรวจสุขภาพ | `unified-vpn health` หรือ `scripts/health-check.sh` |
| ติดตั้ง/ติดตั้งซ้ำ ZIVPN | `bash scripts/setup-zivpn.sh` |
| Backup / Restore | หน้า Backups ใน Panel หรือ `scripts/backup.sh create|restore FILE` |
| อัปเดต | `/opt/unified-vpn/update.sh --from DIR` หรือ `--tarball URL --sha256 HEX` (backup + rollback อัตโนมัติ) |
| ถอนการติดตั้ง | `/opt/unified-vpn/uninstall.sh` (มี 3 โหมด + ถามยืนยัน) |

## สถาปัตยกรรม

```
Next.js Web UI (Vercel, SSR)  ──/api──►  Flask REST API (127.0.0.1:8080)  →  ZIVPN adapter  →  systemd (zivpn.service)
                                              ▲ nginx :443 (TLS) เป็นทางเข้าเดียว
```

Web UI อยู่ใน `panel-next/` (Next.js App Router + Tailwind 4) deploy บน **Vercel** ตั้ง env `UVPN_API_BASE = https://<โดเมน-VPS>` และ **Root Directory = `panel-next`**
รายละเอียดใน `docs/ARCHITECTURE.md` · เช็กลิสต์ทดสอบใน `docs/TESTING.md`

## ZIVPN

- ติดตั้งด้วย `scripts/setup-zivpn.sh` — pin upstream `zahidbd2/udp-zivpn` (release `udp-zivpn_1.4.9`) พร้อม SHA256 ต่อสถาปัตยกรรม adapter จะปฏิเสธทันทีถ้า hash ไม่ตรง
- พอร์ต: `5667/udp` + ช่วง `6000–19999/udp` (DNAT → 5667 สำหรับ port hopping) ปิดช่วงพอร์ตได้โดยตั้ง `"port_range": ""` ใน `/opt/unified-vpn/config/zivpn.json`
- รหัสผ่าน ZIVPN = รหัสของผู้ใช้ที่แอดมินตั้งตอนสร้าง; บัญชีเก่าที่สร้างก่อนอัปเดตจะยังใช้สตริงสุ่ม — รีเซ็ตรหัสผู้ใช้หนึ่งครั้งเพื่ออัปเดต
- **ยังไม่บังคับ Max Connections/Max Devices** ใน ZIVPN (เก็บค่าไว้เท่านั้น)
- ยังไม่เคยรันบน VPS จริง — โค้ดผ่านเทสต์ dry-run (`tests/smoke_test.py`) ต้องทดสอบตาม `docs/TESTING.md` ก่อนใช้งานจริง
- Panel รันเป็น root แต่ฟังเฉพาะ 127.0.0.1 หลัง nginx

## ใบอนุญาต

โค้ดในรีโปนี้: MIT. **ZIVPN upstream binary ที่ดาวน์โหลดต้องตรวจ license เองก่อนแจกจ่ายต่อ** (ดู `docs/SOURCE_AUDIT.md`)
