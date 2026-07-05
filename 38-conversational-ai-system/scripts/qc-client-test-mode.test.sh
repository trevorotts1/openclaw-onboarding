#!/usr/bin/env bash
# qc-client-test-mode.test.sh - positive + negative fixture tests for
# qc-client-test-mode.sh (CARD-14, U-6).
#
# Proves the gate:
#   * PASSES the real skill tree (protocol + AGENTS wiring + MEMORY Rule 37 +
#     three-layer enforcement + banner + isolation/expiry + full suppression list),
#   * FAILS (exit 1) a copy whose protocol drops one allow-list action category
#     from the suppression list (the seeded bad fixture), and
#   * FAILS (exit 1) a copy whose protocol file is removed entirely.
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE="$SCRIPT_DIR/qc-client-test-mode.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

exit_of() {
  local rc=0
  bash "$GATE" --skill-dir "$1" >/dev/null 2>&1 || rc=$?
  echo "$rc"
}

echo "=== qc-client-test-mode.test: positive + suppression-gap + missing-protocol ==="

# --- POSITIVE: the real skill tree must PASS (exit 0). ----------------------
if [ "$(exit_of "$SKILL_DIR")" = "0" ]; then
  ok "real skill tree: gate PASS (exit 0)"
else
  bad "real skill tree: expected exit 0"
fi

# --- NEGATIVE 1: drop webhook_chain from the suppression list => FAIL. ------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -r "$SKILL_DIR" "$TMP/skill"
PROTO="$TMP/skill/protocols/client-test-mode-protocol.md"
grep -v 'webhook_chain' "$PROTO" > "$PROTO.tmp"
mv "$PROTO.tmp" "$PROTO"
if [ "$(exit_of "$TMP/skill")" = "1" ]; then
  ok "suppression gap (webhook_chain removed): gate FAIL (exit 1)"
else
  bad "suppression gap: expected exit 1 (gate did not bite)"
fi

# --- NEGATIVE 2: remove the protocol entirely => FAIL. ---------------------
TMP2="$(mktemp -d)"
cp -r "$SKILL_DIR" "$TMP2/skill"
rm -f "$TMP2/skill/protocols/client-test-mode-protocol.md"
rc2="$(exit_of "$TMP2/skill")"
rm -rf "$TMP2"
if [ "$rc2" = "1" ]; then
  ok "missing protocol: gate FAIL (exit 1)"
else
  bad "missing protocol: expected exit 1"
fi

echo ""
echo "qc-client-test-mode tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
