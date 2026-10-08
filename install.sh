#!/usr/bin/env bash
# Unified VPN Panel installer.   bash install.sh
# Non-interactive: set UVPN_NONINTERACTIVE=1 and UVPN_DOMAIN, UVPN_EMAIL, UVPN_PANEL_PORT, UVPN_ADMIN_USER,
# UVPN_ADMIN_PASS, UVPN_PROTOCOLS="openvpn ssh xray zivpn", UVPN_ASSUME_YES=1
set -Eeuo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib.sh
source "$SRC_DIR/scripts/lib.sh"
mkdir -p "$(dirname "$LOG_FILE")"; : >>"$LOG_FILE"; chmod 600 "$LOG_FILE"
trap 'rc=$?; err "Installer stopped at line $LINENO (exit $rc). Nothing was killed or removed automatically. See $LOG_FILE"; exit $rc' ERR

echo "=============================="
echo "  Unified VPN Panel Installer"
echo "=============================="

# ---------------------------------------------------------------- 1. root / OS / resources
need_root
. /etc/os-release
case "${ID}:${VERSION_ID}" in
  ubuntu:20.04|ubuntu:22.04|ubuntu:24.04|debian:11|debian:12) ok "OS: $PRETTY_NAME" ;;
  *) [ "${UVPN_FORCE:-0}" = 1 ] || die "Unsupported OS: $PRETTY_NAME (supported: Ubuntu 20.04/22.04/24.04, Debian 11/12). Set UVPN_FORCE=1 to try anyway." ;;
esac
ARCH="$(uname -m)"; RAM_MB="$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)"
DISK_GB="$(df -BG --output=avail / | tail -1 | tr -dc '0-9')"; CPUS="$(nproc)"
log "Arch=$ARCH  CPU=$CPUS  RAM=${RAM_MB}MB  Disk free=${DISK_GB}GB  Kernel=$(uname -r)"
[ "$RAM_MB" -ge 1500 ] || warn "Less than 2GB RAM - fine for a single protocol, tight for several."
[ "$DISK_GB" -ge 10 ] || warn "Less than 10GB free disk."
curl -fsS --max-time 10 -o /dev/null https://github.com || die "No internet access (cannot reach github.com)"
ok "Internet reachable"

# ---------------------------------------------------------------- 2. questions
ask UVPN_DOMAIN "Panel domain (blank = use server IP with a self-signed certificate)" ""
if [ -n "$UVPN_DOMAIN" ]; then ask UVPN_EMAIL "Email for Let's Encrypt (optional)" ""; fi
ask UVPN_PANEL_PORT "Panel internal port (127.0.0.1 only)" "8080"
ask UVPN_ADMIN_USER "Admin username" "superadmin"
ask_secret UVPN_ADMIN_PASS "Admin password (min 10 chars)"
[ "${#UVPN_ADMIN_PASS}" -ge 10 ] || die "Admin password must be at least 10 characters"
if [ "$UVPN_ADMIN_USER" = admin ] && [ "$UVPN_ADMIN_PASS" = admin ]; then die "admin/admin is not allowed"; fi
if [ -z "${UVPN_PROTOCOLS:-}" ]; then
  UVPN_PROTOCOLS=""
  for p in openvpn ssh xray wireguard hysteria2 zivpn badvpn; do
    if [ "$p" = zivpn ] && [ ! -f "$UVPN_HOME/config/zivpn.json" ]; then
      log "  skipping zivpn - it needs $UVPN_HOME/config/zivpn.json first (audit your upstream, see docs/SOURCE_AUDIT.md)"
      continue
    fi
    def=y; [ "$p" = badvpn ] && def=n     # badvpn builds from source (slower); zivpn only reaches here when already configured
    if [ "${UVPN_NONINTERACTIVE:-0}" = 1 ] || [ ! -t 0 ]; then [ "$def" = y ] && UVPN_PROTOCOLS="$UVPN_PROTOCOLS $p"
    else confirm "Install $p?" "$def" && UVPN_PROTOCOLS="$UVPN_PROTOCOLS $p"; fi
  done
fi
log "Protocols: ${UVPN_PROTOCOLS:-none}"

# ---------------------------------------------------------------- 2b. stop a previous install of *ours*
# Re-running the installer must not be blocked by the services it installed last time
# (panel on the loopback port, OpenVPN 1194, WireGuard 51820, ...). We only touch our own units.
if [ -f /etc/systemd/system/unified-panel.service ] || [ -f "$UVPN_HOME/config/panel.env" ] \
   || [ -f /etc/openvpn/server/uvpn-udp.conf ] || [ -f /etc/wireguard/wg0.conf ]; then
  log "Existing Unified VPN install detected - stopping its services so ports can be reused ..."
  for u in unified-panel.service unified-ws-ssh.service unified-hysteria.service unified-badvpn.service \
           unified-vpn-nat.service xray.service zivpn.service unified-expiry.timer unified-expiry.service \
           openvpn-server@uvpn-udp.service openvpn-server@uvpn-tcp.service wg-quick@wg0.service; do
    systemctl stop "$u" >/dev/null 2>&1 || true
  done
  pkill -f "$UVPN_HOME/venv/bin/gunicorn" >/dev/null 2>&1 || true   # leftover from an interrupted run
  log "  previous services stopped (ports should be free now)"
  sleep 1
fi

# ---------------------------------------------------------------- 3. port check (never kills anything)
log "Checking ports ..."
show_owner() { local o; o="$(port_owner "$1")"; printf '%s' "${o:-unknown - find it with: ss -lntup | grep ':$1 '}"; }
bad=0
for spec in tcp:80 tcp:443; do
  proto="${spec%%:*}"; port="${spec##*:}"
  if port_in_use "$proto" "$port"; then
    if port_owner "$port" | grep nginx >/dev/null; then
      log "  tcp/$port is held by nginx (this installer manages nginx) - OK"
    else
      err "$proto/$port is in use by: $(show_owner "$port")"; bad=1
    fi
  fi
done
if port_in_use tcp "$UVPN_PANEL_PORT"; then err "tcp/$UVPN_PANEL_PORT already in use by: $(show_owner "$UVPN_PANEL_PORT")"; bad=1; fi
[[ " $UVPN_PROTOCOLS " == *" openvpn "* ]] && for pr in udp tcp; do port_in_use "$pr" 1194 && { err "$pr/1194 in use by: $(show_owner 1194)"; bad=1; }; done
[[ " $UVPN_PROTOCOLS " == *" xray "* ]] && port_in_use tcp 8443 && { err "tcp/8443 (REALITY) in use by: $(show_owner 8443)"; bad=1; }
[[ " $UVPN_PROTOCOLS " == *" wireguard "* ]] && port_in_use udp 51820 && { err "udp/51820 in use by: $(show_owner 51820)"; bad=1; }
[[ " $UVPN_PROTOCOLS " == *" hysteria2 "* ]] && port_in_use udp 443 && { err "udp/443 (Hysteria2) in use by: $(show_owner 443)"; bad=1; }
[ "$bad" -eq 0 ] || die "Free the ports above (or pick another panel port) and re-run. The installer never kills other processes."
ok "Ports free"

# ---------------------------------------------------------------- 4. dependencies
log "Installing base packages ..."
export DEBIAN_FRONTEND=noninteractive
log "  apt-get update ..."
apt-get update -y 2>&1 | tee -a "$LOG_FILE"
log "  apt-get install (curl wget git unzip tar jq openssl ca-certificates socat nginx sqlite3 cron iptables ufw python3 python3-venv python3-pip rsync) ..."
apt-get install -y --no-install-recommends curl wget git unzip tar jq openssl ca-certificates socat nginx sqlite3 cron \
  iptables ufw python3 python3-venv python3-pip rsync 2>&1 | tee -a "$LOG_FILE"
if [ -n "$UVPN_DOMAIN" ]; then
  log "  apt-get install certbot ..."
  apt-get install -y --no-install-recommends certbot 2>&1 | tee -a "$LOG_FILE"
fi
ok "Packages installed"

# ---------------------------------------------------------------- 5. firewall (warn + confirm inside)
SSH_PORT="$(detect_ssh_port)"
FW_EXTRA=()
[[ " $UVPN_PROTOCOLS " == *" openvpn "* ]] && FW_EXTRA+=("1194/udp" "1194/tcp")
[[ " $UVPN_PROTOCOLS " == *" xray "* ]] && FW_EXTRA+=("8443/tcp")
[[ " $UVPN_PROTOCOLS " == *" wireguard "* ]] && FW_EXTRA+=("51820/udp")
[[ " $UVPN_PROTOCOLS " == *" hysteria2 "* ]] && FW_EXTRA+=("443/udp")
[[ " $UVPN_PROTOCOLS " == *" zivpn "* ]] && FW_EXTRA+=("5667/udp")
if confirm "Configure the UFW firewall now? (SSH port $SSH_PORT will be allowed first)" y; then
  UVPN_ASSUME_YES=1 bash "$SRC_DIR/scripts/firewall.sh" apply "${FW_EXTRA[@]}"
else
  warn "Firewall skipped. Remember to open: 80/tcp 443/tcp ${FW_EXTRA[*]:-}"
fi

# ---------------------------------------------------------------- 6. files, venv, config
log "Installing files to $UVPN_HOME ..."
mkdir -p "$UVPN_HOME"/{bin,config/installed,log,backups,scripts,adapters,panel,database} "$UVPN_DATA" /etc/unified-vpn/nginx.d /etc/unified-vpn/nginx-http.d
log "  syncing panel/ adapters/ scripts/ database/ ..."
rsync -av --delete --exclude '__pycache__' "$SRC_DIR/panel/" "$UVPN_HOME/panel/" 2>&1 | tee -a "$LOG_FILE"
rsync -av --delete --exclude '__pycache__' "$SRC_DIR/adapters/" "$UVPN_HOME/adapters/" 2>&1 | tee -a "$LOG_FILE"
rsync -av "$SRC_DIR/scripts/" "$UVPN_HOME/scripts/" 2>&1 | tee -a "$LOG_FILE"
rsync -av "$SRC_DIR/database/" "$UVPN_HOME/database/" 2>&1 | tee -a "$LOG_FILE"
cp "$SRC_DIR/update.sh" "$SRC_DIR/uninstall.sh" "$UVPN_HOME/"
cp "$SRC_DIR/VERSION" "$UVPN_HOME/VERSION" 2>/dev/null || echo "dev" >"$UVPN_HOME/VERSION"
chmod +x "$UVPN_HOME"/scripts/*.sh "$UVPN_HOME"/scripts/*.py "$UVPN_HOME"/update.sh "$UVPN_HOME"/uninstall.sh
chmod 700 "$UVPN_HOME/config" "$UVPN_HOME/backups" "$UVPN_DATA"

log "Creating Python virtualenv at $UVPN_HOME/venv ..."
python3 -m venv "$UVPN_HOME/venv" 2>&1 | tee -a "$LOG_FILE"
log "  upgrading pip ..."
"$UVPN_HOME/venv/bin/pip" install --upgrade pip 2>&1 | tee -a "$LOG_FILE"
log "  installing Python requirements ..."
"$UVPN_HOME/venv/bin/pip" install -r "$UVPN_HOME/panel/backend/requirements.txt" 2>&1 | tee -a "$LOG_FILE"
ok "Python environment ready"

if [ ! -f "$UVPN_HOME/config/panel.env" ]; then
  umask 077
  cat >"$UVPN_HOME/config/panel.env" <<ENV
UVPN_SECRET_KEY=$(openssl rand -hex 32)
UVPN_BIND=127.0.0.1
UVPN_PORT=$UVPN_PANEL_PORT
ENV
fi
[ -f "$UVPN_HOME/config/backup.key" ] || { umask 077; openssl rand -base64 32 >"$UVPN_HOME/config/backup.key"; }
printf '#!/usr/bin/env bash\nexport PYTHONPATH=%s:%s/panel\nset -a; . %s/config/panel.env; set +a\nexec %s/venv/bin/python -m backend "$@"\n' \
  "$UVPN_HOME" "$UVPN_HOME" "$UVPN_HOME" "$UVPN_HOME" >/usr/local/bin/unified-vpn
chmod 755 /usr/local/bin/unified-vpn
ln -sf /usr/local/bin/unified-vpn /usr/local/bin/m
chmod 755 /usr/local/bin/m

log "Detecting public IP ..."
PUBLIC_IP="$(public_ip || true)"
HOST="${UVPN_DOMAIN:-$PUBLIC_IP}"
[ -n "$HOST" ] || die "Could not determine public IP; set UVPN_DOMAIN"
log "  public IP: ${PUBLIC_IP:-unknown}  host: $HOST"

# ---------------------------------------------------------------- 7. database + admin
log "Initialising database and admin account ..."
unified-vpn init-db
unified-vpn set-setting host "$HOST"
unified-vpn set-setting public_ip "${PUBLIC_IP:-}"
UVPN_ADMIN_PASS="$UVPN_ADMIN_PASS" unified-vpn create-admin --username "$UVPN_ADMIN_USER"
ok "Database and admin account ready"

# ---------------------------------------------------------------- 8. nginx base config BEFORE protocols (they drop snippets in)
rm -f /etc/nginx/sites-enabled/default      # only the symlink; the original stays in sites-available
mkdir -p /var/www/html
render_nginx() {  # render_nginx CERT KEY
  local server_name="${UVPN_DOMAIN:-_}" default="" hsts=""
  [ -n "$UVPN_DOMAIN" ] || default=" default_server"
  [ "${3:-}" = hsts ] && hsts='add_header Strict-Transport-Security "max-age=31536000" always;'
  sed -e "s|@SERVER_NAME@|$server_name|g" -e "s|@DEFAULT@|$default|g" -e "s|@CERT@|$1|g" -e "s|@KEY@|$2|g" \
      -e "s|@PANEL_PORT@|$UVPN_PANEL_PORT|g" -e "s|@HSTS@|$hsts|g" "$SRC_DIR/nginx/panel.conf.tpl" >/etc/nginx/conf.d/unified-vpn.conf
}
CERT=""; KEY=""; SELF=1
if [ -n "$UVPN_DOMAIN" ]; then
  # temporary self-signed so nginx can start, then try Let's Encrypt (webroot)
  mkdir -p /etc/unified-vpn/tls
  openssl req -x509 -nodes -newkey rsa:2048 -days 3650 -subj "/CN=$UVPN_DOMAIN" \
    -keyout /etc/unified-vpn/tls/self.key -out /etc/unified-vpn/tls/self.crt >/dev/null 2>&1
  chmod 600 /etc/unified-vpn/tls/self.key
  render_nginx /etc/unified-vpn/tls/self.crt /etc/unified-vpn/tls/self.key
  log "  validating nginx config and starting nginx ..."
  nginx -t 2>&1 | tee -a "$LOG_FILE"
  systemctl enable --now nginx
  systemctl reload nginx
  email_args=(--register-unsafely-without-email); [ -z "${UVPN_EMAIL:-}" ] || email_args=(-m "$UVPN_EMAIL")
  log "  requesting Let's Encrypt certificate for $UVPN_DOMAIN (certbot) ..."
  if certbot certonly --webroot -w /var/www/html -d "$UVPN_DOMAIN" --non-interactive --agree-tos "${email_args[@]}" \
       --deploy-hook "systemctl reload nginx" 2>&1 | tee -a "$LOG_FILE"; then
    CERT="/etc/letsencrypt/live/$UVPN_DOMAIN/fullchain.pem"; KEY="/etc/letsencrypt/live/$UVPN_DOMAIN/privkey.pem"; SELF=0
    ok "Let's Encrypt certificate issued (auto-renewal via certbot timer)"
  else
    warn "Let's Encrypt failed (check DNS A record for $UVPN_DOMAIN -> $PUBLIC_IP, and port 80). Using a self-signed certificate."
  fi
fi
if [ "$SELF" = 1 ]; then
  mkdir -p /etc/unified-vpn/tls
  [ -f /etc/unified-vpn/tls/self.crt ] || { openssl req -x509 -nodes -newkey rsa:2048 -days 3650 -subj "/CN=${HOST}" \
      -keyout /etc/unified-vpn/tls/self.key -out /etc/unified-vpn/tls/self.crt >/dev/null 2>&1; chmod 600 /etc/unified-vpn/tls/self.key; }
  CERT=/etc/unified-vpn/tls/self.crt; KEY=/etc/unified-vpn/tls/self.key
  unified-vpn set-setting tls_selfsigned 1
  render_nginx "$CERT" "$KEY"
else
  unified-vpn set-setting tls_selfsigned 0
  render_nginx "$CERT" "$KEY" hsts
fi
unified-vpn set-setting tls_cert "$CERT"; unified-vpn set-setting tls_key "$KEY"      # used by Hysteria2
log "Final nginx config test ..."
nginx -t 2>&1 | tee -a "$LOG_FILE" || die "nginx config test failed"
systemctl enable --now nginx; systemctl reload nginx

# ---------------------------------------------------------------- 9. systemd (panel first so DB exists), then protocols
log "Installing systemd units and starting the panel ..."
cp "$SRC_DIR"/systemd/unified-*.service "$SRC_DIR"/systemd/unified-*.timer /etc/systemd/system/
install -m 644 "$SRC_DIR/scripts/logrotate-unified-vpn" /etc/logrotate.d/unified-vpn
systemctl daemon-reload
systemctl enable --now unified-panel.service unified-expiry.timer

FAILED=()
for p in $UVPN_PROTOCOLS; do
  if [ "$p" = zivpn ] && [ ! -f "$UVPN_HOME/config/zivpn.json" ]; then
    warn "zivpn skipped: $UVPN_HOME/config/zivpn.json is missing (audit your upstream first - docs/SOURCE_AUDIT.md)"
    continue
  fi
  log "Installing protocol: $p ..."
  if unified-vpn adapter-install "$p" 2>&1 | tee -a "$LOG_FILE"; then ok "$p installed"; else err "$p failed (see $LOG_FILE)"; FAILED+=("$p"); fi
done
systemctl reload nginx || true

# ---------------------------------------------------------------- 10. health check
log "Health check ..."
sleep 2
unified-vpn health || warn "Some checks failed - run: unified-vpn health"

echo
ok "Installation finished"
if [ -n "$UVPN_DOMAIN" ] && [ "$SELF" = 0 ]; then URL="https://$UVPN_DOMAIN"; else URL="https://$HOST (self-signed certificate: your browser will warn)"; fi
echo "  Panel URL : $URL"
echo "  Admin user: $UVPN_ADMIN_USER"
echo "  CLI       : m   (หรือ unified-vpn)  - เมนูภาษาไทย"
echo "  Backup key: $UVPN_HOME/config/backup.key   <-- copy it somewhere safe, backups cannot be restored without it"
if [ ! -f "$UVPN_HOME/config/zivpn.json" ]; then
  echo "  ZIVPN     : optional (UDP) - enable later with: bash scripts/setup-zivpn.sh"
fi
[ "${#FAILED[@]}" -eq 0 ] || warn "Protocols that failed to install: ${FAILED[*]}  (ZIVPN needs $UVPN_HOME/config/zivpn.json first - docs/SOURCE_AUDIT.md)"
