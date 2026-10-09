# Architecture

```
install.sh ─► /opt/unified-vpn/{panel,adapters,scripts,config,backups,venv}  +  /var/lib/unified-vpn/database.db

Browser ──HTTPS──► nginx :443 ──► gunicorn 127.0.0.1:8080 (Flask)
                       │                 │
                       │                 ├─ usermgr  (DB state first, then adapters)
                       │                 ├─ servicemgr (allow-listed systemd units only)
                       │                 └─ adapters/{ssh,openvpn,xray,zivpn}
                       └─ /ssh-ws /vless /vmess /trojan  ─► loopback cores (WebSocket)
```

## Adapter interface (`adapters/base.py`)
`install, uninstall, configure, start, stop, restart, status, create_user, delete_user, list_users`
plus `revoke_user` (disable/expire), `sync` (declarative re-render), `share`, `health`, `online`.
The panel never contains protocol-specific commands.

| Adapter | Account model | Revocation |
|---|---|---|
| ssh | real Linux user (`useradd`, nologin shell, group `uvpn`, GECOS tag `uvpn-managed`) | `usermod -L -e 1` + kill sessions |
| openvpn | no system account; `ovpn-auth.py` checks the DB on every login | next login fails (active sessions end at reconnect) |
| xray | declarative: `config.json` built from DB → `xray run -test` → atomic swap → restart only if changed | removed on sync |
| hysteria2 | declarative: YAML rendered from DB (every active user in `userpass`) | removed on sync (restart) |
| hysteria1 | config rendered from DB; auth is per-connection via `hysteria1-auth.py` (`auth.mode: external`), counts from the server log | next login fails; live sessions dropped at reconnect |
| wireguard | declarative: `wg0.conf` peers rendered from DB, applied with `wg syncconf` | peer removed on sync |
| xray (reality) | same Xray config, extra VLESS+Reality inbound on tcp/8443, keys in `config/xray-reality.json` (0600) | removed on sync |
| zivpn | declarative: config rendered from DB (config-driven, see module docstring) | removed on sync |

## Key decisions
- **Order of operations:** DB status is written *before* adapters run, so declarative adapters render the right state.
- **Revocation is tracked** (`protocol_accounts.status`: active / revoked / revoke_failed). `maintenance.py` (every minute) retries failures, so a failed revoke never silently leaves access open.
- **Expiry:** timestamps are UTC; the 1-minute timer flips `status=expired` and revokes in each adapter (SSH `-e` date is only a backstop).
- **Passwords:** admin and VPN-user passwords are Argon2id hashes (scrypt fallback if argon2-cffi is missing). The VPN user's plaintext is used once (SSH `chpasswd`) and never stored or logged. Protocol secrets (UUID/trojan/ZIVPN) must be stored to build share links; they are redacted from logs.
- **Safety:** no shell strings (`subprocess` lists), usernames validated `^[a-z][a-z0-9_-]{0,31}$` (1-32 chars), system users are never taken over, services controlled only from an allow-list, `ssh`/`nginx`/panel can only be restarted, sshd_config changes go backup → `sshd -t` → reload → rollback, port conflicts abort (nothing is killed), firewall allows SSH before enabling.
- **Panel security:** loopback bind, HTTPS via nginx, Secure/HttpOnly/SameSite=Strict cookie, CSRF header, 30 min idle / 8 h absolute session, login rate limit + 5-strike lockout (15 min), CSP, audit log, roles (superadmin / admin / support-read-only).
- **Connection vs device limit:** only Max Connections is enforced. Max Devices is stored but explicitly *not* enforced (plan §31).

## Layout on the server
`/opt/unified-vpn` code+config (config/panel.env 0600, backup.key 0600) · `/var/lib/unified-vpn/database.db` · `/etc/xray/config.json` · `/etc/openvpn/server/uvpn-{udp,tcp}.conf` + `/etc/openvpn/uvpn-pki` · `/etc/zivpn` · `/etc/unified-vpn/{nginx.d,nginx-http.d,tls}`
