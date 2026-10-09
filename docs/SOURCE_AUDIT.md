# Source Audit (plan §36, §50) — complete BEFORE trusting any upstream

What this repo already downloads/uses, and what is still **your** job:

| Component | How it is obtained | Verified by | Status |
|---|---|---|---|
| OpenVPN / easy-rsa / OpenSSH / nginx | distro `apt` | distro signatures | ready |
| Xray-core | GitHub release zip of `XTLS/Xray-core` (pin with `XRAY_VERSION=vX.Y.Z`) | SHA256 from the release `.dgst` — install aborts on mismatch | ready (check license MPL-2.0) |
| ZIVPN | GitHub release of `zahidbd2/udp-zivpn` (release `udp-zivpn_1.4.9`), configured by `scripts/setup-zivpn.sh` | asset pinned by SHA256 in that script; adapter aborts on mismatch | supported — **verify the upstream license yourself** before redistributing |
| Hysteria 2 | GitHub release of `apernet/hysteria` (pin with `HYSTERIA_VERSION=vX.Y.Z`) | SHA256 from release `hashes.txt` — aborts on mismatch/missing | ready (license MIT) |
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
