# Architecture (ZIVPN only)

```
VPS:  install.sh ─► /opt/unified-vpn/{panel,adapters,scripts,config,backups,venv}  +  /var/lib/unified-vpn/database.db

Browser ──HTTPS──► Vercel (Next.js SSR UI, panel-next/) ─────────────► VPS
                     │  server components fetch API server-side         │
                     │  browser /api/* proxied by                          nginx :443
                     │  app/api/[...path]/route.ts (relays Set-Cookie)  ──► gunicorn 127.0.0.1:8080 (Flask JSON API)
                     │                                                       │  usermgr / servicemgr / adapters
                     └─ UI pages (SSR)                                    └─ zivpn.service (UDP 5667 + DNAT 6000-19999)
```

The web UI is a **Next.js (App Router, SSR) app** in `panel-next/`, deployed to **Vercel**. The Flask
backend stays on the VPS and is the single source of truth — the Next app contains no protocol logic.

- Set `UVPN_API_BASE` on Vercel to the VPS origin, e.g. `https://vpn.example.com` (must be HTTPS with
  a valid certificate).
- Server components render by fetching `UVPN_API_BASE/api/*` and forwarding the browser session
  cookie (`lib/server.ts`).
- Every browser `/api/*` call is proxied through the Vercel app by
  `app/api/[...path]/route.ts`, which forwards method/body and **relays `Set-Cookie`**. This keeps the
  Flask session cookie same-origin with the UI, so there is no CORS and the `X-CSRF-Token` flow is
  unchanged. The Flask cookie is signed by `UVPN_SECRET_KEY`; the proxy just passes it back and forth.
- The VPS nginx serves the Flask API on `:443` (the same endpoints the legacy bundled UI used); the VPS
  no longer runs any Node process.

Note: large responses (e.g. multi-GB backup downloads) are relayed through Vercel and may hit Vercel's
response limits; download very large backups directly from the VPS if needed.

## Adapter interface (`adapters/base.py`)
`install, uninstall, configure, start, stop, restart, status, create_user, delete_user, list_users`
plus `revoke_user` (disable/expire), `sync` (declarative re-render), `share`, `health`, `online`.
The panel never contains protocol-specific commands.

| Adapter | Account model | Revocation |
|---|---|---|
| zivpn | declarative: `/etc/zivpn/config.json` rendered from DB (the user's chosen password is the ZIVPN password) | removed on sync (service restarted only if the config changed) |

## Key decisions
- **Order of operations:** DB status is written *before* adapters run, so declarative adapters render the right state.
- **Revocation is tracked** (`protocol_accounts.status`: active / revoked / revoke_failed). `maintenance.py` (every minute) retries failures, so a failed revoke never silently leaves access open.
- **Expiry:** timestamps are UTC; the 1-minute timer flips `status=expired` and revokes in each adapter (SSH `-e` date is only a backstop).
- **Passwords:** admin and VPN-user passwords are Argon2id hashes (scrypt fallback if argon2-cffi is missing). The ZIVPN password must be stored in the account config to render the server config and show connection info; it is redacted from logs.
- **Safety:** no shell strings (`subprocess` lists), usernames validated `^[a-z][a-z0-9_-]{0,31}$` (1-32 chars), services controlled only from an allow-list, `nginx`/panel can only be restarted, port conflicts abort (nothing is killed), firewall allows SSH before enabling.
- **Panel security:** loopback bind, HTTPS via nginx, Secure/HttpOnly/SameSite=Strict cookie, CSRF header, 30 min idle / 8 h absolute session, login rate limit + 5-strike lockout (15 min), CSP, audit log, roles (superadmin / admin / support-read-only).
- **Limits:** Max Connections / Max Devices are stored but not enforced for ZIVPN.
- **Web UI:** Next.js App Router + React 19 + Tailwind CSS 4 in `panel-next/` (server components for data, client components for actions). Deployed to **Vercel** (Root Directory = `panel-next`, env `UVPN_API_BASE=https://<vps>`); the VPS runs only the Flask API. Built with webpack (no Turbopack native binding needed).

## Layout on the server
`/opt/unified-vpn` code+config (config/panel.env 0600, backup.key 0600, zivpn.json) · `/var/lib/unified-vpn/database.db` · `/etc/zivpn` · `/etc/unified-vpn/tls`
