#!/usr/bin/env bash
# Enable the optional ZIVPN (UDP) adapter.
#
# Upstream : https://github.com/zahidbd2/udp-zivpn   (release tag udp-zivpn_1.4.9)
# License  : verify with the upstream project before redistributing the binary.
# Safety   : the release asset is pinned here by SHA256, so the installer refuses to run any
#            binary whose hash does not match. This is the "audit" step docs/SOURCE_AUDIT.md asks
#            for - a human still has to accept the upstream; we just make it reproducible.
#
# install.sh calls this script for you. To re-run it by hand (the panel + unified-vpn CLI must exist):
#     bash scripts/setup-zivpn.sh
set -Eeuo pipefail

UVPN_HOME="${UVPN_HOME:-/opt/unified-vpn}"
CONF="$UVPN_HOME/config/zivpn.json"
REL="udp-zivpn_1.4.9"
BASE="https://github.com/zahidbd2/udp-zivpn/releases/download/$REL"

case "$(uname -m)" in
  x86_64|amd64)  A=amd64; SHA=df6658c195882ff2f6cefb44050e8cb2c238ceb2b6e3fbefb931698f4f0519cb ;;
  aarch64|arm64) A=arm64; SHA=1bc3f0a46db2b4a4771dd08e68e2134c55d7c48874334ed7bba512d983bfa83a ;;
  armv7l|armv6l|arm) A=arm; SHA=45671cdf1ee995a33273128f8c953747c003da7cdc228b9b34e68e080eb6a123 ;;
  *) echo "setup-zivpn: unsupported architecture $(uname -m)" >&2; exit 1 ;;
esac

command -v unified-vpn >/dev/null 2>&1 || { echo "setup-zivpn: run install.sh first (unified-vpn CLI not found)" >&2; exit 1; }

mkdir -p "$(dirname "$CONF")"
OBFS='hu``hqb`c'
cat >"$CONF" <<EOF
{
  "binary_url":   "$BASE/udp-zivpn-linux-$A",
  "sha256":       "$SHA",
  "binary_path":  "/usr/local/bin/zivpn",
  "exec_args":    "server -c /etc/zivpn/config.json",
  "listen_port":  5667,
  "obfs":         "$OBFS",
  "port_range":   "6000:19999"
}
EOF
chmod 600 "$CONF"
echo "wrote $CONF  (arch=$A, ${REL})"

# The adapter downloads the pinned asset, verifies the SHA256 above, and only then installs.
unified-vpn adapter-install zivpn

# Allow UDP. The DNAT rewrites the range to :5667 in PREROUTING, so the filter stage sees the
# rewritten port 5667 - both the direct port AND the range must be allowed when UFW is active.
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep "Status: active" >/dev/null; then
  ufw allow 5667/udp
  ufw allow 6000:19999/udp
fi
