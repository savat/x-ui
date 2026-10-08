# Test checklist (run on a spare VPS — plan §30, §47)

Automated (no root needed): `PYTHONPATH=.:panel python3 tests/smoke_test.py`

Manual on a fresh Ubuntu VPS:
- [ ] `bash install.sh` finishes; `unified-vpn health` all `[OK]`
- [ ] Panel opens on https; admin login works; wrong password x5 locks the account
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
