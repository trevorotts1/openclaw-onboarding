#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-no-fabrication.sh"
REAL="$(cd "$SCRIPT_DIR/.." && pwd)"
fail() { echo "[TEST FAIL] qc-no-fabrication: $1"; exit 1; }
bash "$GATE" --skill-dir "$REAL" >/dev/null 2>&1 || fail "gate failed on intact tree"
c="$(mktemp -d)"; cp -a "$REAL/." "$c/"
# Break it: remove the honest-gap path from the runtime guide
grep -vi "honest gap" "$c/INSTRUCTIONS.md" > "$c/i.tmp" && mv "$c/i.tmp" "$c/INSTRUCTIONS.md"
if bash "$GATE" --skill-dir "$c" >/dev/null 2>&1; then rm -rf "$c"; fail "gate did NOT bite when honest-gap path removed"; fi
rm -rf "$c"
echo "[TEST PASS] qc-no-fabrication bites"
exit 0
