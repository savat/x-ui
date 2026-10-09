# Unified VPN Panel

ระบบ VPN Server แบบรวมศูนย์ ติดตั้งด้วยคำสั่งเดียว แล้วจัดการ SSH / OpenVPN / Xray (VLESS, VMess, Trojan, **VLESS+Reality**) / **Hysteria 2** / **WireGuard** / ZIVPN / BadVPN ได้จาก Web Panel หรือ CLI เดียว
สร้างตามเอกสาร `Unified_VPN_Panel_Project_Plan.txt` (Phase 1)

## ติดตั้ง

```bash
# บน VPS ใหม่ (Ubuntu 20.04/22.04/24.04, Debian 11/12) ด้วย root
git clone https://github.com/savat/x-ui.git unified-vpn-panel && cd unified-vpn-panel
bash install.sh
```

ตัวติดตั้งจะถาม: โดเมน (เว้นว่าง = ใช้ IP + self-signed), พอร์ตภายใน Panel, จะตั้ง admin ตอนนี้หรือไม่ (เว้นว่าง/เลือกไม่ = ไปตั้งทีหลังได้ตลอดด้วยเมนู `m`), และเลือก protocol แบบ **เลือกทั้งหมด** หรือ **เลือกเอง** (เลือกเป็นหมายเลขได้)
แบบ non-interactive: `UVPN_NONINTERACTIVE=1 UVPN_DOMAIN=panel.example.com UVPN_ADMIN_USER=boss UVPN_ADMIN_PASS=... UVPN_PROTOCOLS="openvpn ssh xray" UVPN_ASSUME_YES=1 bash install.sh` (ถ้าไม่ตั้ง `UVPN_ADMIN_USER`/`UVPN_ADMIN_PASS` ระบบจะข้าม admin แล้วไปตั้งทีหลังผ่านเมนู)

**สำคัญ:** เก็บไฟล์ `/opt/unified-vpn/config/backup.key` ไว้ที่ปลอดภัย — backup เข้ารหัสด้วยคีย์นี้ ถ้าไม่มีจะ restore ไม่ได้

## ใช้งาน

| สิ่งที่ทำ | วิธี |
|---|---|
| Web Panel | `https://<domain หรือ IP>` |
| CLI เมนู | `m` (หรือ `unified-vpn`) — เมนูภาษาไทย |
| จัดการผู้ดูแลระบบ | เมนู `m` → `7) จัดการผู้ดูแลระบบ` (เพิ่ม/แก้ไข/ลบ ได้ตลอด) หรือ `unified-vpn create-admin --username NAME` |
| ตรวจสุขภาพ | `unified-vpn health` หรือ `scripts/health-check.sh` |
| ติดตั้ง protocol เพิ่ม | `unified-vpn adapter-install xray` |
| Backup / Restore | หน้า Backups ใน Panel หรือ `scripts/backup.sh create|restore FILE` |
| อัปเดต | `/opt/unified-vpn/update.sh --from DIR` หรือ `--tarball URL --sha256 HEX` (backup + rollback อัตโนมัติ) |
| ถอนการติดตั้ง | `/opt/unified-vpn/uninstall.sh` (มี 3 โหมด + ถามยืนยัน; ไม่แตะ SSH ของแอดมิน) |

## สถาปัตยกรรม (4 ชั้น)

```
Web Panel (static JS)  →  Flask REST API (127.0.0.1:8080)  →  Adapters  →  systemd services
                              ▲ nginx :443 (TLS) เป็นทางเข้าเดียว
```

รายละเอียดใน `docs/ARCHITECTURE.md` · ขั้นตอนตรวจ upstream ใน `docs/SOURCE_AUDIT.md` · เช็กลิสต์ทดสอบบน VPS จริงใน `docs/TESTING.md`

## สิ่งที่ "ยังไม่ได้ทำ/มีข้อจำกัด" (พูดตรง ๆ ตามหลักในแผน)

- **ยังไม่เคยรันบน VPS จริง** — โค้ดผ่านเทสต์ dry-run (`tests/smoke_test.py`, 43 รายการ) แต่ต้องทดสอบตามเช็กลิสต์ `docs/TESTING.md` บน VPS สำรองก่อนใช้งานจริง
- **ZIVPN:** เปิดใช้ด้วย `bash scripts/setup-zivpn.sh` (หลัง `install.sh`) — สคริปต์เขียน `/opt/unified-vpn/config/zivpn.json` ให้ โดย pin upstream `zahidbd2/udp-zivpn` (release `udp-zivpn_1.4.9`) พร้อม SHA256 ต่อสถาปัตยกรรม แล้วสั่งติดตั้งให้; adapter จะปฏิเสธทันทีถ้า hash ไม่ตรง. รหัสผ่าน ZIVPN = รหัสของผู้ใช้ที่แอดมินตั้งตอนสร้าง (ไม่ใช่สตริงสุ่ม); บัญชีเก่าที่สร้างก่อนอัปเดตจะยังใช้สตริงสุ่ม — รีเซ็ตรหัสผู้ใช้หนึ่งครั้งเพื่ออัปเดต. ถ้าจะใช้ upstream อื่นให้แก้ไฟล์นั้นเอง (URL + SHA256 บังคับ) และตรวจ license/ที่มาเอง (ดู `docs/SOURCE_AUDIT.md`)
- **Max Devices ไม่ได้บังคับ** (connection ≠ เครื่อง) — มีเฉพาะ Max Connections: SSH = soft limit (เตะ connection ใหม่เกินภายใน ~1 นาที), OpenVPN = ปฏิเสธตอน auth, Xray/ZIVPN = ยังไม่บังคับ
- **พอร์ตที่เปิดสาธารณะ:** nginx 443/tcp (Panel + WS), Reality 8443/tcp, Hysteria2 443/udp, WireGuard 51820/udp, OpenVPN 1194 udp+tcp, ZIVPN 5667/udp + ช่วง 6000–19999/udp (DNAT → 5667 สำหรับ port hopping; เลือกพอร์ต WireGuard 51820 ไว้ไม่ให้ถูก DNAT ทับ) (ตัวติดตั้งตรวจพอร์ตชน และไม่ kill โปรเซสของใคร)
- **WireGuard:** เซิร์ฟเวอร์สร้าง keypair+preshared key ให้ client (เก็บใน DB ที่เป็น root-only เพื่อโหลด .conf/QR ซ้ำได้) ใช้ `wg syncconf` จึงไม่ตัด tunnel คนอื่น; **ไม่สามารถบังคับ Max Connections ได้** (UDP 1 peer = 1 key)
- **Hysteria 2:** ใช้ userpass, binary ตรวจ SHA256 จาก `hashes.txt` ของ release; รันเป็น root เพราะต้องอ่าน TLS private key (มี sandbox) ยังไม่รองรับ obfs/salamander และการวัด traffic
- **Reality:** ใช้ `dest` เริ่มต้น `www.cloudflare.com:443` (เปลี่ยนได้ด้วย `unified-vpn set-setting reality_dest host:443`); คีย์/shortId สร้างครั้งเดียวแล้วคงที่; ถ้า Xray รุ่นใหม่เปลี่ยนรูปแบบ output ของ `xray x25519` ตัวติดตั้งจะหยุดพร้อมข้อความ ไม่เดา
- **BadVPN UDPGW:** ทำแล้ว (`unified-vpn adapter-install badvpn`) ฟังเฉพาะ 127.0.0.1:7300 ใช้ผ่าน SSH tunnel เท่านั้น (ตั้ง udpgw 127.0.0.1:7300 ในแอปไคลเอนต์)
- OpenVPN WS/WSS, Xray gRPC/Shadowsocks, UDP Custom, Quota/Traffic ต่อ user, multi-server = Phase 2/3 ที่เหลือ
- Panel รันเป็น root (ต้องจัดการ user/service) แต่ฟังเฉพาะ 127.0.0.1 หลัง nginx; การแยกสิทธิ์ (agent) อยู่ใน Phase 3
- Xray ต้อง restart เมื่อเพิ่ม/ลบ user (connection ของ Xray ทุกคนสะดุดสั้น ๆ)

## ใบอนุญาต

โค้ดในรีโปนี้: MIT. **upstream binary ที่ดาวน์โหลด (Xray = MPL-2.0, OpenVPN = GPL-2.0, ZIVPN = ตรวจเอง) ต้องเช็ก license เองก่อนแจกจ่ายต่อ**
