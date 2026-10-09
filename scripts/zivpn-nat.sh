#!/usr/bin/env bash
# ZIVPN multi-port support: DNAT incoming UDP 6000:19999 -> :5667 (client "port hopping").
# Idempotent. Used by unified-zivpn-nat.service (up at boot, down on stop).
# The zivpn binary itself listens on a single UDP port; the range is a NAT redirect.
set -euo pipefail

ACTION="${1:-up}"
PORT="${ZIVPN_PORT:-5667}"
RANGE="${ZIVPN_RANGE:-6000:19999}"
CHAIN="UVPN_ZIVPN"
# Ports that must NOT be hijacked by the range (they belong to other services on this host).
# Hysteria2 443, OpenVPN 1194, WireGuard 51820, Hysteria1 36712. Extra ports can be added with
# ZIVPN_EXCLUDE="port port ..." (the adapter passes zivpn.json "exclude_ports").
EXCLUDE_UDP=(443 1194 51820 36712)
[ -n "${ZIVPN_EXCLUDE:-}" ] && EXCLUDE_UDP+=($ZIVPN_EXCLUDE)
EXCLUDE_UDP+=("${ZIVPN_PORT:-5667}")   # never hijack our own listen port either

IFACE="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev" && !d){d=$(i+1)}} END {if (d) print d}')"
[ -n "$IFACE" ] || { echo "zivpn-nat: cannot detect default interface" >&2; exit 1; }

if [ "$ACTION" = up ]; then
  iptables -t nat -N "$CHAIN" 2>/dev/null || true
  iptables -t nat -F "$CHAIN"
  for p in "${EXCLUDE_UDP[@]}"; do
    iptables -t nat -A "$CHAIN" -p udp --dport "$p" -j RETURN
  done
  iptables -t nat -A "$CHAIN" -p udp --dport "$RANGE" -j DNAT --to-destination ":$PORT"
  iptables -t nat -C PREROUTING -i "$IFACE" -p udp -j "$CHAIN" 2>/dev/null \
    || iptables -t nat -A PREROUTING -i "$IFACE" -p udp -j "$CHAIN"
else
  while iptables -t nat -D PREROUTING -i "$IFACE" -p udp -j "$CHAIN" 2>/dev/null; do :; done
  iptables -t nat -F "$CHAIN" 2>/dev/null || true
  iptables -t nat -X "$CHAIN" 2>/dev/null || true
fi
