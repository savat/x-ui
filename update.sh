#!/usr/bin/env bash
# Update Unified VPN Panel with automatic backup and rollback.
#   update.sh --from /path/to/extracted/release
#   update.sh --tarball URL --sha256 HEX
# The new code is validated (python compile + shell syntax) BEFORE anything is replaced.
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/scripts/lib.sh" 2>/dev/null || source "$UVPN_HOME/scripts/lib.sh"
LOG_FILE=/var/log/unified-vpn-update.log
need_root

SRC=""; TARBALL=""; SHA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --from) SRC="$2"; shift 2 ;;
    --tarball) TARBALL="$2"; shift 2 ;;
    --sha256) SHA="$2"; shift 2 ;;
    *) die "unknown option $1" ;;
  esac
done
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

if [ -n "$TARBALL" ]; then
  [ -n "$SHA" ] || die "--sha256 is required with --tarball (no unverified downloads)"
  log "Downloading $TARBALL"
  curl -fsSL -o "$WORK/release.tar.gz" "$TARBALL"
  echo "$SHA  $WORK/release.tar.gz" | sha256sum -c - || die "SHA256 mismatch - aborting"
  mkdir "$WORK/src"; tar -xzf "$WORK/release.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi
[ -n "$SRC" ] && [ -d "$SRC/panel" ] && [ -d "$SRC/adapters" ] || die "usage: update.sh --from DIR | --tarball URL --sha256 HEX"

log "Validating new release ..."
python3 -m compileall -q "$SRC/panel" "$SRC/adapters" >/dev/null || die "python validation failed"
for f in "$SRC"/scripts/*.sh "$SRC"/install.sh "$SRC"/update.sh "$SRC"/uninstall.sh; do bash -n "$f" || die "syntax error in $f"; done
find "$SRC" -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

log "Backing up (data + code snapshot) ..."
bash "$UVPN_HOME/scripts/backup.sh" create
SNAP="$UVPN_HOME/backups/code-$(date -u +%Y%m%d-%H%M%S).tar.gz"
tar -C "$UVPN_HOME" -czf "$SNAP" panel adapters scripts database VERSION update.sh uninstall.sh 2>/dev/null
chmod 600 "$SNAP"

rollback() {
  err "Update failed - rolling back code from $SNAP"
  tar -C "$UVPN_HOME" -xzf "$SNAP"
  systemctl restart unified-panel || true
  exit 1
}
trap rollback ERR

log "Installing new code ..."
rsync -a --delete --exclude '__pycache__' "$SRC/panel/" "$UVPN_HOME/panel/"
rsync -a --delete --exclude '__pycache__' "$SRC/adapters/" "$UVPN_HOME/adapters/"
rsync -a "$SRC/scripts/" "$UVPN_HOME/scripts/"
rsync -a "$SRC/database/" "$UVPN_HOME/database/"
cp "$SRC/update.sh" "$SRC/uninstall.sh" "$UVPN_HOME/"; cp "$SRC/VERSION" "$UVPN_HOME/VERSION" 2>/dev/null || true
chmod +x "$UVPN_HOME"/scripts/*.sh "$UVPN_HOME"/scripts/*.py "$UVPN_HOME"/update.sh "$UVPN_HOME"/uninstall.sh
"$UVPN_HOME/venv/bin/pip" install --quiet -r "$UVPN_HOME/panel/backend/requirements.txt"
cp "$SRC"/systemd/unified-*.service "$SRC"/systemd/unified-*.timer /etc/systemd/system/ && systemctl daemon-reload
unified_py init-db                       # schema is CREATE IF NOT EXISTS
systemctl restart unified-panel
sleep 3
systemctl is-active --quiet unified-panel || false      # triggers rollback via ERR trap
unified_py health || { warn "Health check reports problems (code update itself succeeded)"; }
trap - ERR
ok "Updated to $(cat "$UVPN_HOME/VERSION")"
