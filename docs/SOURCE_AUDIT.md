# Source Audit (plan §36, §50) — complete BEFORE trusting any upstream

What this repo already downloads/uses, and what is still **your** job:

| Component | How it is obtained | Verified by | Status |
|---|---|---|---|
| OpenVPN / easy-rsa / OpenSSH / nginx | distro `apt` | distro signatures | ready |
| Xray-core | GitHub release zip of `XTLS/Xray-core` (pin with `XRAY_VERSION=vX.Y.Z`) | SHA256 from the release `.dgst` — install aborts on mismatch | ready (check license MPL-2.0) |
| ZIVPN | **you choose** the upstream | `sha256` in `zivpn.json` is mandatory | **NOT audited — do it first** |
| Hysteria 2 | GitHub release of `apernet/hysteria` (pin with `HYSTERIA_VERSION=vX.Y.Z`) | SHA256 from release `hashes.txt` — aborts on mismatch/missing | ready (license MIT) |
| WireGuard | distro `apt` (kernel module / wireguard-tools) | distro signatures | ready (needs kernel support; some OpenVZ/LXC VPS lack it) |
| BadVPN | distro `apt` (`badvpn`) | distro signatures | ready |
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
1. Pick upstream, record the table above, confirm the license allows what you plan.
2. Download the binary yourself, `sha256sum` it, put URL + hash in `/opt/unified-vpn/config/zivpn.json`.
3. Compare the upstream's real config file with `DEFAULT_TEMPLATE` in `adapters/zivpn/__init__.py`; supply `config_template` if it differs (`@PASSWORDS@`, `@PORT@`, `@OBFS@`, `@ETC@` placeholders).
4. Test auth, reconnect, expiry and removal on a spare VPS, then `unified-vpn adapter-install zivpn`.
