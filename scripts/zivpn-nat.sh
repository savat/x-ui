#!/usr/bin/env bash
# ZIVPN multi-port support: DNAT incoming UDP 6000:19999 -> :5667 (client "port hopping").
# Idempotent. Used by unified-zivpn-nat.service (up at boot, down on stop).
# The zivpn binary itself listens on a single UDP port; the range is a NAT redirect.
set -euo pipefail

ACTION="${1:-up}"
PORT="${ZIVPN_PORT:-5667}"
RANGE="${ZIVPN_RANGE:-6000:19999}"
CHAIN="UVPN_ZIVPN"

IFACE="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev" && !d){d=$(i+1)}} END {if (d) print d}')"
[ -n "$IFACE" ] || { echo "zivpn-nat: cannot detect default interface" >&2; exit 1; }

if [ "$ACTION" = up ]; then
  iptables -t nat -N "$CHAIN" 2>/dev/null || true
  iptables -t nat -F "$CHAIN"
  iptables -t nat -A "$CHAIN" -p udp --dport "$RANGE" -j DNAT --to-destination ":$PORT"
  iptables -t nat -C PREROUTING -i "$IFACE" -p udp -j "$CHAIN" 2>/dev/null \
    || iptables -t nat -A PREROUTING -i "$IFACE" -p udp -j "$CHAIN"
else
  while iptables -t nat -D PREROUTING -i "$IFACE" -p udp -j "$CHAIN" 2>/dev/null; do :; done
  iptables -t nat -F "$CHAIN" 2>/dev/null || true
  iptables -t nat -X "$CHAIN" 2>/dev/null || true
fi
