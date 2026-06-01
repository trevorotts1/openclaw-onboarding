#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-prompt-completeness.sh"
REAL="$(cd "$SCRIPT_DIR/.." && pwd)"
fail() { echo "[TEST FAIL] qc-prompt-completeness: $1"; exit 1; }
bash "$GATE" --skill-dir "$REAL" >/dev/null 2>&1 || fail "gate failed on intact tree"
c="$(mktemp -d)"; cp -a "$REAL/." "$c/"
# Break it: strip the 'Webhook configuration' section from the template
grep -vi "Webhook configuration" "$c/templates/build-with-ai-prompt-template.md" > "$c/t.tmp" && mv "$c/t.tmp" "$c/templates/build-with-ai-prompt-template.md"
if bash "$GATE" --skill-dir "$c" >/dev/null 2>&1; then rm -rf "$c"; fail "gate did NOT bite when a required section was removed"; fi
rm -rf "$c"
echo "[TEST PASS] qc-prompt-completeness bites"
exit 0
