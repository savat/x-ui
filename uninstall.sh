#!/usr/bin/env bash
# Uninstall with safety checks. Never touches sshd, the admin's SSH access or the SSH firewall rule.
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/scripts/lib.sh" 2>/dev/null || source "$UVPN_HOME/scripts/lib.sh"
LOG_FILE=/var/log/unified-vpn-uninstall.log
need_root

echo "Unified VPN Panel - uninstall"
echo "  1) Remove Panel only            (protocol services keep running, users keep working)"
echo "  2) Remove Panel + Protocols     (OpenVPN/Xray/ZIVPN/SSH-WS adapters, VPN users)"
echo "  3) Full cleanup                 (2 + all data, backups, certificates created by the installer)"
echo "  0) Cancel"
MODE="${UVPN_UNINSTALL_MODE:-}"
[ -n "$MODE" ] || read -r -p "Choose: " MODE
case "$MODE" in 1|2|3) ;; *) echo "Cancelled."; exit 0 ;; esac

warn "This will NOT remove OpenSSH or change your SSH port/firewall rule for SSH."
if [ "$MODE" != 1 ]; then
  confirm "Create a final backup first?" y && bash "$UVPN_HOME/scripts/backup.sh" create || true
  echo "Backups live in $UVPN_HOME/backups and are deleted in mode 3. Copy them elsewhere now if you need them."
fi
if [ "${UVPN_ASSUME_YES:-0}" != 1 ]; then
  read -r -p "Type UNINSTALL to continue: " c; [ "$c" = UNINSTALL ] || { echo "Cancelled."; exit 0; }
fi

if [ "$MODE" -ge 2 ]; then
  for a in openvpn xray zivpn ssh; do unified_py adapter-uninstall "$a" 2>/dev/null && ok "adapter $a removed" || warn "adapter $a: skipped/failed"; done
fi

systemctl disable --now unified-expiry.timer unified-panel.service 2>/dev/null || true
rm -f /etc/systemd/system/unified-panel.service /etc/systemd/system/unified-expiry.service /etc/systemd/system/unified-expiry.timer
rm -f /etc/nginx/conf.d/unified-vpn.conf /usr/local/bin/unified-vpn
systemctl daemon-reload
nginx -t >/dev/null 2>&1 && systemctl reload nginx 2>/dev/null || true

if [ "$MODE" = 3 ]; then
  rm -rf "$UVPN_HOME" "$UVPN_DATA" /etc/unified-vpn
  ok "All data removed"
else
  rm -rf "$UVPN_HOME/panel" "$UVPN_HOME/venv"
  ok "Panel removed; data kept in $UVPN_DATA and $UVPN_HOME/config"
fi
echo "Firewall rules were left untouched (review with: ufw status)."
