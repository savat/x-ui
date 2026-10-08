#!/usr/bin/env bash
# NAT/forward rules for OpenVPN subnets. Idempotent (-C before -A/-I). Used by unified-vpn-nat.service.
set -euo pipefail
ACTION="${1:-up}"
SUBNETS=("10.8.0.0/24" "10.9.0.0/24" "10.66.0.0/24")   # OpenVPN udp, OpenVPN tcp, WireGuard
IFACE="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev" && !d){d=$(i+1)}} END {if (d) print d}')"
[ -n "$IFACE" ] || { echo "cannot detect default interface" >&2; exit 1; }

for net in "${SUBNETS[@]}"; do
  if [ "$ACTION" = up ]; then
    iptables -t nat -C POSTROUTING -s "$net" -o "$IFACE" -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s "$net" -o "$IFACE" -j MASQUERADE
    iptables -C FORWARD -s "$net" -j ACCEPT 2>/dev/null || iptables -I FORWARD -s "$net" -j ACCEPT
    iptables -C FORWARD -d "$net" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || iptables -I FORWARD -d "$net" -m state --state RELATED,ESTABLISHED -j ACCEPT
  else
    iptables -t nat -D POSTROUTING -s "$net" -o "$IFACE" -j MASQUERADE 2>/dev/null || true
    iptables -D FORWARD -s "$net" -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -d "$net" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
  fi
done
