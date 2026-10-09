# Test checklist (run on a spare VPS)

Automated (no root needed): `PYTHONPATH=.:panel python3 tests/smoke_test.py`

Next.js web UI (`panel-next/`, deployed on Vercel): `cd panel-next && npm install && npm run build`, then with a backend reachable set
`UVPN_API_BASE=https://<vps>` and run `npm run start` (or `npm run dev`). On Vercel set `UVPN_API_BASE` (VPS origin, HTTPS with a valid cert) and Root Directory = `panel-next`.

Manual on a fresh Ubuntu VPS:
- [ ] `bash install.sh` finishes; `unified-vpn health` all `[OK]`
- [ ] Web UI loads; login works; every page renders; backup downloads work through the proxy
- [ ] Installing with no admin, then `m` → `7) จัดการผู้ดูแลระบบ` creates one; login works; wrong password x5 locks the account
- [ ] Create / delete / disable / enable / renew / reset-password a ZIVPN user; "ข้อมูลเชื่อมต่อ" shows server, port, obfs, password
- [ ] ZIVPN client app connects on UDP 5667 and on a port inside 6000–19999; reconnect works
- [ ] Expiry: create 1-day user, set `expires_at` to the past in the DB, wait ≤1 min → connection refused
- [ ] Panel → Services: restart works; `nginx`/panel cannot be stopped
- [ ] Logs page shows no passwords/keys
- [ ] Backup → download → Restore on a fresh VPS (needs backup.key)
- [ ] Firewall: SSH still reachable after `ufw enable`
- [ ] `update.sh --from` with a broken release rolls back; with a good one succeeds
- [ ] `uninstall.sh` modes 1/2/3 ask for confirmation and leave SSH access intact
- [ ] Reboot: panel and zivpn come back
