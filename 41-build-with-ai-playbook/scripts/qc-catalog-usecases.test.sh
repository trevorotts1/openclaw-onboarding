#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-catalog-usecases.sh"
REAL="$(cd "$SCRIPT_DIR/.." && pwd)"
fail() { echo "[TEST FAIL] qc-catalog-usecases: $1"; exit 1; }
bash "$GATE" --skill-dir "$REAL" >/dev/null 2>&1 || fail "gate failed on intact tree"
c="$(mktemp -d)"; cp -a "$REAL/." "$c/"
# Break it: strip the per-item use cases from the triggers catalog
grep -v 'Use when:' "$c/references/ghl-triggers-catalog.md" > "$c/x.tmp" && mv "$c/x.tmp" "$c/references/ghl-triggers-catalog.md"
if bash "$GATE" --skill-dir "$c" >/dev/null 2>&1; then rm -rf "$c"; fail "gate did NOT bite when use cases removed"; fi
rm -rf "$c"
echo "[TEST PASS] qc-catalog-usecases bites"
exit 0
