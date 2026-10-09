# Source Audit — complete BEFORE trusting any upstream

| Component | How it is obtained | Verified by | Status |
|---|---|---|---|
| nginx / OpenSSL / iptables | distro `apt` | distro signatures | ready |
| ZIVPN | GitHub release of `zahidbd2/udp-zivpn` (release `udp-zivpn_1.4.9`), configured by `scripts/setup-zivpn.sh` | asset pinned by SHA256 in that script; adapter aborts on mismatch | supported — **verify the upstream license yourself** before redistributing |

## Record for the upstream
```
GitHub URL:        Branch:        Commit/Tag:
License:           (MIT/Apache/GPL/AGPL/BSD/Proprietary/NONE -> NONE = not redistributable)
OS support:        Architecture:
Install command:   Binary + SHA256:
Config path:       Service name:      Port(s):
Repo alive? last commit? open security issues? untrusted binaries?
```
Rules: never `curl | bash` unknown scripts; download, read, hash, then run.

## ZIVPN checklist
1. Record the table above and confirm the license allows what you plan.
2. `install.sh` runs `scripts/setup-zivpn.sh`, which writes `/opt/unified-vpn/config/zivpn.json` (arch-specific URL + pinned SHA256) and runs `unified-vpn adapter-install zivpn`. To use another upstream, edit that file (URL + `sha256` are mandatory) and/or supply `config_template` (`@PASSWORDS@`, `@PORT@`, `@OBFS@`, `@ETC@`).
3. Test auth, reconnect, expiry and removal on a spare VPS. The client connects on UDP `5667`; the 6000–19999 multi-port DNAT is enabled by default (`port_range` → `unified-zivpn-nat.service` runs `scripts/zivpn-nat.sh`). Set `"port_range": ""` to disable it.
