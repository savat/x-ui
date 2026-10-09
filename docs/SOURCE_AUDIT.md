# Source Audit (plan §36, §50) — complete BEFORE trusting any upstream

What this repo already downloads/uses, and what is still **your** job:

| Component | How it is obtained | Verified by | Status |
|---|---|---|---|
| OpenVPN / easy-rsa / OpenSSH / nginx | distro `apt` | distro signatures | ready |
| Xray-core | GitHub release zip of `XTLS/Xray-core` (pin with `XRAY_VERSION=vX.Y.Z`) | SHA256 from the release `.dgst` — install aborts on mismatch | ready (check license MPL-2.0) |
| ZIVPN | GitHub release of `zahidbd2/udp-zivpn` (release `udp-zivpn_1.4.9`), configured by `scripts/setup-zivpn.sh` | asset pinned by SHA256 in that script; adapter aborts on mismatch | supported — **verify the upstream license yourself** before redistributing |
| Hysteria 2 | GitHub release of `apernet/hysteria` (pin with `HYSTERIA_VERSION=vX.Y.Z`) | SHA256 from release `hashes.txt` — aborts on mismatch/missing | ready (license MIT) |
| Hysteria 1 | GitHub release of `apernet/hysteria` tag `v1.3.5` (pin with `HYSTERIA1_VERSION`) | SHA256 from release `hashes.txt` — aborts on mismatch/missing | ready (license MIT; upstream EOL — v1.3.5 is the last release) |
| WireGuard | distro `apt` (kernel module / wireguard-tools) | distro signatures | ready (needs kernel support; some OpenVZ/LXC VPS lack it) |
| BadVPN | source build of `ambrop72/badvpn` (udpgw-only target, `cmake -DBUILD_NOTHING_BY_DEFAULT=1 -DBUILD_UDPGW=1`) | source code + pinned upstream repo | ready (no distro package exists) |
| UDP Custom | Phase 2 | — | — |

## Record for every upstream (copy per repo)
```
GitHub URL:        Branch:        Commit/Tag:
License:           (MIT/Apache/GPL/AGPL/BSD/Proprietary/NONE -> NONE = not redistributable)
OS support:        Architecture:
Install command:   Binary + SHA256:
Config path:       Service name:      Port(s):
User database:     Uninstall method:  Known issues:
Repo alive? last commit? open security issues? untrusted binaries?
```
Rules: never `curl | bash` unknown scripts; download, read, hash, then run. GPL/AGPL obligations apply if you redistribute modified code.

## ZIVPN checklist
1. Pick upstream and record the table above; confirm the license allows what you plan. The helper
   defaults to `zahidbd2/udp-zivpn` (release `udp-zivpn_1.4.9`) because its `config.json` matches
   `DEFAULT_TEMPLATE` in `adapters/zivpn/__init__.py`.
2. After `bash install.sh` (panel + CLI installed) run `bash scripts/setup-zivpn.sh`. It writes
   `/opt/unified-vpn/config/zivpn.json` with the arch-appropriate URL and a pinned SHA256, then runs
   `unified-vpn adapter-install zivpn`. To use a different upstream, edit that file (URL + `sha256`
   are mandatory) and/or supply `config_template` (`@PASSWORDS@`, `@PORT@`, `@OBFS@`, `@ETC@`).
3. Test auth, reconnect, expiry and removal on a spare VPS. The client connects on UDP `5667`, and the
   upstream's optional 6000–19999 multi-port DNAT is enabled by default (`port_range` in
   `zivpn.json` → `unified-zivpn-nat.service` runs `scripts/zivpn-nat.sh`, which DNATs `6000:19999/udp`
   → `:5667` and excludes WireGuard's 51820). Set `"port_range": ""` to disable it.
4. Auth: the 1.4.9 binary accepts `auth.mode` = `passwords` / `userpass` / `http` / `command` (verified
   by probing; `password`, `external`, `cmd`, `none` are rejected). The adapter uses `http`: the server
   POSTs `{"addr","auth","tx"}` to the loopback `unified-zivpn-auth.service` (`scripts/zivpn-auth.py`),
   which checks the panel DB and answers `{"ok","id"}`. This is what enforces expiry/disable/
   max-connections for ZIVPN; the older static `passwords` mode could not. Set `"config_template"` with
   `@PASSWORDS@` to fall back to static passwords (no expiry/limit enforcement).

## Hysteria 1 checklist

1. Upstream `apernet/hysteria` is **end-of-life** for v1 (the author moved to Hysteria 2). Tag `v1.3.5`
   is the last v1 release; the adapter pins it and verifies the binary against the release `hashes.txt`.
   The tag is `v1.3.5` (not `app/…`, which is the Hysteria 2 scheme).
2. Config is JSON at `/etc/hysteria1/config.json`, rendered from the DB. TLS uses the panel's
   `tls_cert`/`tls_key` settings (same cert as Hysteria 2 / nginx). Obfuscation password via
   `unified-vpn set-setting hysteria1_obfs <password>` (default `opo`; the client link then carries
   `obfs=xplus&obfsParam=…`). The user's config page also offers a "โปรไฟล์แอป Hysteria1 (.json)"
   download (the app's Servers/Networks profile, `new.json` shape) whose `UDPConfig.auth_str` is
   `username:password`; `hysteria1_app_server` overrides the `ServerIP` if the app wants the port there.
3. Auth is `auth.mode: "external"` → `scripts/hysteria1-auth.py` (loopback `unified-hysteria1-auth.service`).
   The server POSTs `{"addr","payload","send","recv"}` (payload = base64 of the client credential) and
   the endpoint answers `{"ok","msg"}`. We validate the DB (active/unexpired/`hysteria1` account) and
   enforce `max_connections`: the addr is registered on a successful auth and removed when the server
   logs `Client disconnected` for the same `src` (the unit redirects server output to a log file for
   this), mirroring live counts to `hysteria1-online.json`. This is what enforces expiry/disable/
   limits; a plain `passwords` config would not. (Hysteria 1's only connection gauge,
   `hysteria_active_conn`, counts live *streams* not connections, so it cannot be used for this.)
4. Listens on **UDP 36712** (Hysteria 2 keeps 443/udp; no conflict). Open `36712/udp` in the firewall.
