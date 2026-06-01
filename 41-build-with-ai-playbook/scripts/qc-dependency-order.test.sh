#!/usr/bin/env bash
# Negative test: qc-dependency-order must PASS intact and FAIL when the invariant is removed.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-dependency-order.sh"
REAL="$(cd "$SCRIPT_DIR/.." && pwd)"
fail() { echo "[TEST FAIL] qc-dependency-order: $1"; exit 1; }
bash "$GATE" --skill-dir "$REAL" >/dev/null 2>&1 || fail "gate failed on intact tree"
c="$(mktemp -d)"; cp -a "$REAL/." "$c/"
# Break it: remove every 'Dependency creation' line so order/presence check fails
grep -v "Dependency creation" "$c/protocols/build-with-ai-protocol.md" > "$c/p.tmp" && mv "$c/p.tmp" "$c/protocols/build-with-ai-protocol.md"
if bash "$GATE" --skill-dir "$c" >/dev/null 2>&1; then rm -rf "$c"; fail "gate did NOT bite when dependency-creation removed"; fi
rm -rf "$c"
echo "[TEST PASS] qc-dependency-order bites"
exit 0
