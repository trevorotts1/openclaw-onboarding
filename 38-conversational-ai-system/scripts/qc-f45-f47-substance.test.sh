#!/usr/bin/env bash
# qc-f45-f47-substance.test.sh - positive + negative fixture tests for
# qc-f45-f47-substance.sh, focused on the U-3 Learning Loop extension (CARD-04).
#
# Proves the gate:
#   * PASSES the real skill tree (every F45 + F47 substance point present, incl.
#     the U-3 Learning Loop, the two new event types, and the operator-only write
#     rule), and
#   * FAILS (exit 1) a copy whose smart-faq-tool-protocol.md has the Learning Loop
#     section stripped (the seeded bad fixture) - so a deep-fix regression that
#     drops the loop cannot pass silently.
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE="$SCRIPT_DIR/qc-f45-f47-substance.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

exit_of() {
  local rc=0
  bash "$GATE" --skill-dir "$1" >/dev/null 2>&1 || rc=$?
  echo "$rc"
}

echo "=== qc-f45-f47-substance.test: positive + Learning Loop negative fixture ==="

# --- POSITIVE: the real skill tree must PASS (exit 0). ----------------------
if [ "$(exit_of "$SKILL_DIR")" = "0" ]; then
  ok "real skill tree: gate PASS (exit 0)"
else
  bad "real skill tree: expected exit 0"
fi

# --- NEGATIVE: strip the Learning Loop section => FAIL (exit 1). ------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -r "$SKILL_DIR" "$TMP/skill"
F47="$TMP/skill/protocols/smart-faq-tool-protocol.md"

# Drop every line from the "## Learning Loop" heading up to (but not including)
# the next "## Per-workflow FAQ scope" heading, and also drop the two new event
# types + the operator-only write rule wherever they appear. This models a
# regression that strips the U-3 loop.
awk '
  /^## Learning Loop/ { skip=1 }
  /^## Per-workflow FAQ scope/ { skip=0 }
  skip==1 { next }
  /faq_unknown_flagged/ { next }
  /faq_learned/ { next }
  /ONLY an operator Telegram reply can write to/ { next }
  { print }
' "$F47" > "$F47.tmp"
mv "$F47.tmp" "$F47"

if [ "$(exit_of "$TMP/skill")" = "1" ]; then
  ok "Learning Loop stripped: gate FAIL (exit 1)"
else
  bad "Learning Loop stripped: expected exit 1 (gate did not bite)"
fi

echo ""
echo "qc-f45-f47-substance tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
