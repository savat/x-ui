#!/usr/bin/env bash
# Prints [OK]/[FAIL] per component (binary, config, port, service, log errors). Exit 1 on any failure.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
unified_py health
