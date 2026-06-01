#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-zhc-tag-prefix.sh"
REAL="$(cd "$SCRIPT_DIR/.." && pwd)"
fail() { echo "[TEST FAIL] qc-zhc-tag-prefix: $1"; exit 1; }
bash "$GATE" --skill-dir "$REAL" >/dev/null 2>&1 || fail "gate failed on intact tree"
c="$(mktemp -d)"; cp -a "$REAL/." "$c/"
# Break it: remove the ZHC_ field-prefix discipline from the dependency protocol
grep -v "ZHC_" "$c/protocols/dependency-creation-protocol.md" > "$c/d.tmp" && mv "$c/d.tmp" "$c/protocols/dependency-creation-protocol.md"
if bash "$GATE" --skill-dir "$c" >/dev/null 2>&1; then rm -rf "$c"; fail "gate did NOT bite when ZHC_ prefix removed"; fi
rm -rf "$c"
echo "[TEST PASS] qc-zhc-tag-prefix bites"
exit 0
