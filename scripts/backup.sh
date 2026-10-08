#!/usr/bin/env bash
# Encrypted backup / restore.
#   backup.sh create            -> prints the archive path
#   backup.sh restore <file>    -> restore (stops services, snapshots current state first)
#   backup.sh list
# Archive = tar.gz of DB (consistent .backup copy) + panel config + protocol configs + OpenVPN PKI,
# encrypted with AES-256 using /opt/unified-vpn/config/backup.key. Private keys are never stored in the clear.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

BACKUP_DIR="${UVPN_BACKUPS:-$UVPN_HOME/backups}"
KEY_FILE="${UVPN_BACKUP_KEY:-$UVPN_HOME/config/backup.key}"
DB="${UVPN_DB:-$UVPN_DATA/database.db}"
ETC="${UVPN_ETC:-/etc}"
KEEP="${UVPN_BACKUP_KEEP:-14}"
PATHS=("$UVPN_HOME/config" "$ETC/xray" "$ETC/openvpn/server" "$ETC/openvpn/uvpn-pki" "$ETC/zivpn" "$ETC/unified-vpn")

need_root
umask 077
[ -f "$KEY_FILE" ] || die "backup key missing: $KEY_FILE"

create() {
  mkdir -p "$BACKUP_DIR"
  local ts stage out
  ts="$(date -u +%Y%m%d-%H%M%S)"
  stage="$(mktemp -d)"; trap 'rm -rf "$stage"' RETURN
  mkdir -p "$stage$UVPN_DATA"
  sqlite3 "$DB" ".backup '$stage$UVPN_DATA/database.db'"
  for p in "${PATHS[@]}"; do
    [ -e "$p" ] && { mkdir -p "$stage$(dirname "$p")"; cp -a "$p" "$stage$p"; }
  done
  out="$BACKUP_DIR/uvpn-$ts.tar.gz.enc"
  tar -C "$stage" -czf - . | openssl enc -aes-256-cbc -pbkdf2 -salt -pass "file:$KEY_FILE" -out "$out"
  chmod 600 "$out"
  # retention
  ls -1t "$BACKUP_DIR"/uvpn-*.tar.gz.enc 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f --
  echo "$out"
}

restore() {
  local f="${1:-}"; [ -f "$f" ] || die "backup file not found: $f"
  local work; work="$(mktemp -d)"; trap 'rm -rf "$work"' RETURN
  log "Verifying archive ..."
  openssl enc -d -aes-256-cbc -pbkdf2 -pass "file:$KEY_FILE" -in "$f" | tar -tzf - >/dev/null \
    || die "cannot decrypt/read archive (wrong key or corrupt file)"
  log "Taking a safety snapshot of the current state ..."
  local snap; snap="$(create)"; ok "snapshot: $snap"
  log "Stopping services ..."
  systemctl stop unified-expiry.timer 2>/dev/null || true
  for u in xray zivpn "openvpn-server@uvpn-udp" "openvpn-server@uvpn-tcp"; do systemctl stop "$u" 2>/dev/null || true; done
  log "Restoring ..."
  openssl enc -d -aes-256-cbc -pbkdf2 -pass "file:$KEY_FILE" -in "$f" | tar -C / -xzf -
  systemctl daemon-reload
  for u in xray zivpn "openvpn-server@uvpn-udp" "openvpn-server@uvpn-tcp"; do
    systemctl is-enabled "$u" >/dev/null 2>&1 && systemctl start "$u" 2>/dev/null || true
  done
  systemctl start unified-expiry.timer 2>/dev/null || true
  systemctl restart unified-panel
  ok "Restore finished (rollback snapshot: $snap)"
}

case "${1:-}" in
  create)  create ;;
  restore) shift; restore "${1:-}" ;;
  list)    ls -1t "$BACKUP_DIR"/uvpn-*.tar.gz.enc 2>/dev/null || true ;;
  *) die "usage: backup.sh create|restore <file>|list" ;;
esac
