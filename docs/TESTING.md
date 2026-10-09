# Test checklist (run on a spare VPS — plan §30, §47)

Automated (no root needed): `PYTHONPATH=.:panel python3 tests/smoke_test.py`

Next.js web UI (`panel-next/`, deployed on Vercel): locally `cd panel-next && npm install && npm run build`,
then with a backend reachable set `UVPN_API_BASE=https://<vps>` and run `npm run start` (or `npm run dev`).
Set `UVPN_API_BASE` in the Vercel project env (VPS origin, HTTPS with a valid cert) and Root Directory
= `panel-next`. The SSR smoke harness in the repo's scratch dir (`mock_api.py` + `ssr_smoke.sh` +
`proxy_smoke.sh`) checks page rendering, auth redirects, and that the `/api/*` proxy forwards the session
cookie/CSRF header and relays `Set-Cookie`.

Manual on a fresh Ubuntu VPS:
- [ ] `bash install.sh` finishes; `unified-vpn health` all `[OK]`
- [ ] Vercel UI loads; login works; every page renders; QR images and config/backup downloads work through the proxy
- [ ] Protocol choice works for both "เลือกทั้งหมด" and "เลือกเอง" (numbers/names)
- [ ] Installing with no admin, then `m` → `7) จัดการผู้ดูแลระบบ` creates one; login works; wrong password x5 locks the account
- [ ] Create a user with each protocol; delete; disable; enable; renew
- [ ] SSH: direct, `/ssh-ws` on :80, `/ssh-ws` over TLS :443 (`ssh -o ProxyCommand=...` or an injector app)
- [ ] OpenVPN: download .ovpn (UDP and TCP), connect, browse the internet (NAT works)
- [ ] Xray: import vless/vmess/trojan links (and QR) in a client; traffic flows
- [ ] Reality: import the vless:// link (tcp/8443) in v2rayN/Streisand/Hiddify; traffic flows; links keep working after adding/removing other users
- [ ] Hysteria2: import hysteria2:// link; connect with 2+ users at once; expired user is refused
- [ ] WireGuard: scan the QR / import .conf; internet works; disable user -> handshake no longer works; other users unaffected
- [ ] ZIVPN: auth, connection, reconnect, expiry (after upstream audit)
- [ ] Expiry: create 1-day user, set `expires_at` to the past in the DB, wait ≤1 min → connection/login refused in every protocol
- [ ] Connection limit: max 2, open 3 → SSH 3rd is kicked within ~1 min, OpenVPN 3rd refused at login
- [ ] Panel → Services: restart works; `ssh`/`nginx`/panel cannot be stopped
- [ ] Logs page shows no passwords/keys/UUIDs
- [ ] Backup → download → Restore on a fresh VPS (needs backup.key)
- [ ] Firewall: SSH still reachable after `ufw enable`
- [ ] `update.sh --from` with a broken release rolls back; with a good one succeeds
- [ ] `uninstall.sh` modes 1/2/3 ask for confirmation and leave SSH access intact
- [ ] Reboot: all services come back
