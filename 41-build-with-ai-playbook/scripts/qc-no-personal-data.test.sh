#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-no-personal-data.sh"
REAL="$(cd "$SCRIPT_DIR/.." && pwd)"
fail() { echo "[TEST FAIL] qc-no-personal-data: $1"; exit 1; }
bash "$GATE" --skill-dir "$REAL" >/dev/null 2>&1 || fail "gate failed on intact tree"
c="$(mktemp -d)"; cp -a "$REAL/." "$c/"
# Break it: leak a real identifier into a doc
echo "internal note: contact trevor at blackceo for access" >> "$c/EXAMPLES.md"
if bash "$GATE" --skill-dir "$c" >/dev/null 2>&1; then rm -rf "$c"; fail "gate did NOT bite when a real identifier was leaked"; fi
rm -rf "$c"
echo "[TEST PASS] qc-no-personal-data bites"
exit 0
