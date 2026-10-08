#!/usr/bin/env bash
# Firewall helper (UFW). Safety first: the SSH port is allowed BEFORE the firewall is enabled,
# and nothing is enabled without confirmation.
#   firewall.sh apply   [extra ports e.g. 1194/udp 1194/tcp 5667/udp]
#   firewall.sh status
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

cmd="${1:-status}"; shift || true
case "$cmd" in
  status) command -v ufw >/dev/null && ufw status verbose || echo "ufw not installed" ;;
  apply)
    need_root
    command -v ufw >/dev/null || die "ufw not installed"
    SSH_PORT="$(detect_ssh_port)"
    log "Detected SSH port: $SSH_PORT"
    warn "About to configure UFW. SSH ($SSH_PORT/tcp) will be allowed FIRST so you are not locked out."
    confirm "Continue with firewall changes?" y || { warn "Firewall left unchanged"; exit 0; }
    ufw allow "${SSH_PORT}/tcp" >/dev/null
    ufw allow 80/tcp >/dev/null
    ufw allow 443/tcp >/dev/null
    for p in "$@"; do ufw allow "$p" >/dev/null; done
    ufw status | grep "${SSH_PORT}/tcp" >/dev/null || die "SSH rule missing - refusing to enable firewall"
    if ufw status | grep "Status: inactive" >/dev/null; then
      ufw default deny incoming >/dev/null
      ufw default allow outgoing >/dev/null
      ufw --force enable >/dev/null
    fi
    ok "Firewall active. Allowed: ssh:$SSH_PORT 80 443 $*"
    ;;
  *) die "usage: firewall.sh apply|status" ;;
esac
