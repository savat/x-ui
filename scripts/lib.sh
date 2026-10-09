#!/usr/bin/env bash
# Shared helpers for ZIVPN Panel scripts (sourced, not executed)

UVPN_HOME="${UVPN_HOME:-/opt/unified-vpn}"
UVPN_DATA="${UVPN_DATA:-/var/lib/unified-vpn}"
LOG_FILE="${LOG_FILE:-/var/log/unified-vpn-install.log}"

if [ -t 1 ]; then C_R=$'\e[31m'; C_G=$'\e[32m'; C_Y=$'\e[33m'; C_B=$'\e[34m'; C_0=$'\e[0m'; else C_R=; C_G=; C_Y=; C_B=; C_0=; fi

log()  { printf '%s[*]%s %s\n' "$C_B" "$C_0" "$*" | tee -a "$LOG_FILE" 2>/dev/null; }
ok()   { printf '%s[OK]%s %s\n' "$C_G" "$C_0" "$*" | tee -a "$LOG_FILE" 2>/dev/null; }
warn() { printf '%s[!]%s %s\n' "$C_Y" "$C_0" "$*" >&2; }
err()  { printf '%s[ERROR]%s %s\n' "$C_R" "$C_0" "$*" >&2; }
die()  { err "$*"; exit 1; }

need_root() { [ "$(id -u)" -eq 0 ] || die "Please run as root"; }

# ask VAR "prompt" "default"   (skips when VAR is already set; uses default when non-interactive)
ask() {
  local __var="$1" __prompt="$2" __def="${3:-}" __ans=""
  if [ -n "${!__var:-}" ]; then return 0; fi
  if [ "${UVPN_NONINTERACTIVE:-0}" = "1" ] || [ ! -t 0 ]; then printf -v "$__var" '%s' "$__def"; return 0; fi
  read -r -p "$__prompt${__def:+ [$__def]}: " __ans || true
  printf -v "$__var" '%s' "${__ans:-$__def}"
}

ask_secret() {
  local __var="$1" __prompt="$2" __ans=""
  if [ -n "${!__var:-}" ]; then return 0; fi
  [ -t 0 ] || die "$__var must be provided via environment in non-interactive mode"
  read -r -s -p "$__prompt: " __ans || true; echo
  printf -v "$__var" '%s' "$__ans"
}

# confirm "message" [y|n default]
confirm() {
  local def="${2:-n}" ans=""
  if [ "${UVPN_ASSUME_YES:-0}" = "1" ]; then return 0; fi
  if [ ! -t 0 ]; then [ "$def" = y ]; return; fi
  read -r -p "$1 [$([ "$def" = y ] && echo 'Y/n' || echo 'y/N')]: " ans || true
  ans="${ans:-$def}"
  [[ "$ans" =~ ^[Yy] ]]
}

# port_in_use tcp|udp PORT
# NOTE: consumers must read the whole stream (no `grep -q`/`head`/`awk ... exit`) so the
# upstream `ss` never gets SIGPIPE, which `set -o pipefail` would surface as exit 141.
# We match the whole line (not a fixed field) because `ss` inserts an extra "Netid"
# column when both -t and -u are given, which shifts the column positions.
port_in_use() {
  local flag="-lntH"; [ "$1" = udp ] && flag="-lnuH"
  ss $flag 2>/dev/null | awk -v p="$2" '$0 ~ ("[:.]" p "([[:space:]]|$)") {found=1} END {exit(found?0:1)}'
}

port_owner() {
  ss -lntupH 2>/dev/null \
    | awk -v p="$1" '$0 ~ ("[:.]" p "([[:space:]]|$)") {if (line == "") line=$0} END {if (line != "") print line}' \
    | sed 's/.*users:/users:/'
}

detect_ssh_port() {
  local out p
  out="$(sshd -T 2>/dev/null || true)"
  p="$(awk '/^port /{print $2; exit}' <<<"$out")"
  echo "${p:-22}"
}

public_ip() {
  curl -4fsS --max-time 6 https://api.ipify.org 2>/dev/null \
    || ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src" && !s){s=$(i+1)}} END {if (s) print s}'
}

ssh_service_name() { if systemctl list-unit-files 2>/dev/null | grep -E '^ssh\.service' >/dev/null; then echo ssh; else echo sshd; fi; }

unified_py() { PYTHONPATH="$UVPN_HOME:$UVPN_HOME/panel" "$UVPN_HOME/venv/bin/python" -m backend "$@"; }
