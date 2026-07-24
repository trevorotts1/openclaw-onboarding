#!/usr/bin/env bash
# ============================================================================
# U002 — Post-stamp CC refresh hard exit fix regression suite.
#
# Verifies that every `exit` call inside the post-stamp D5 Command Center
# refresh section (between TRAP3-CC-GUARD-HELPERS and the end of
# TRAP3-CC-BOOTSTRAP-BRANCH) uses exit 0 or exit 2 — NEVER exit 1 —
# because the version stamp has already been written at that point and an
# exit 1 would masquerade as "stamp withheld."
#
# The exit-code contract is:
#   0 = fully current (skills content + CC infrastructure both up to date)
#   1 = stamp WITHHELD (a content-integrity gate before the stamp failed)
#   2 = content current, but CC infrastructure needs attention (advisory)
#
# METHOD. Statically scans update-skills.sh for `exit` statements between
# the two TRAP3 markers. Does NOT need to run the updater or mock anything.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
TARGET="$REPO/update-skills.sh"

PASS=0; FAIL=0
ok()  { printf '  \033[32m✓ PASS\033[0m — %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  \033[31m✗ FAIL\033[0m — %s\n' "$1"; FAIL=$((FAIL+1)); }

[ -f "$TARGET" ] || { echo "FATAL: $TARGET not found"; exit 2; }

# ── 1. Static scan: no exit 1 in the post-stamp CC section ────────────
POST_STAMP_CC_BEGIN=$(grep -n '>>> TRAP3-CC-GUARD-HELPERS-BEGIN' "$TARGET" | cut -d: -f1)
POST_STAMP_CC_END=$(grep -n '<<< TRAP3-CC-BOOTSTRAP-BRANCH-END' "$TARGET" | cut -d: -f1)

if [ -z "$POST_STAMP_CC_BEGIN" ]; then
  bad "TRAP3-CC-GUARD-HELPERS-BEGIN marker not found in $TARGET"
  exit 2
fi
if [ -z "$POST_STAMP_CC_END" ]; then
  bad "TRAP3-CC-BOOTSTRAP-BRANCH-END marker not found in $TARGET"
  exit 2
fi

# Lines between the two markers (exclusive of marker lines themselves)
VIOLATIONS=$(sed -n "$((POST_STAMP_CC_BEGIN+1)),$((POST_STAMP_CC_END-1))p" "$TARGET" \
  | grep -n '^[[:space:]]*exit[[:space:]]*1' || true)

if [ -n "$VIOLATIONS" ]; then
  while IFS= read -r line; do
    bad "exit 1 found in post-stamp CC section (line $((POST_STAMP_CC_BEGIN + ${line%%:*}))): ${line#*:}"
  done <<< "$VIOLATIONS"
else
  ok "No exit 1 found between TRAP3-CC guard helpers and bootstrap markers"
fi

# ── 2. Verify exit-code contract comment is present ───────────────────
# The contract must document exit codes 0, 1, 2 at least once somewhere
# in the file (ideally near the post-stamp section).
if grep -q 'exit 0.*fully current\|exit 0.*skills content.*CC infrastructure' "$TARGET"; then
  ok "Exit-code contract comment references exit 0 = fully current"
else
  bad "Exit-code contract comment missing: no 'exit 0 = fully current' reference"
fi

if grep -q 'exit 1.*stamp WITHHELD\|exit 1.*stamp withheld' "$TARGET"; then
  ok "Exit-code contract comment references exit 1 = stamp withheld"
else
  bad "Exit-code contract comment missing: no 'exit 1 = stamp withheld' reference"
fi

if grep -q 'exit 2.*content current.*CC\|exit 2.*CC infrastructure' "$TARGET"; then
  ok "Exit-code contract comment references exit 2 = content current, CC needs attention"
else
  bad "Exit-code contract comment missing: no 'exit 2 = CC advisory' reference"
fi

# ── 3. Verify the post-stamp CC section actually uses exit 0 or exit 2 ──
POST_CC_EXITS=$(sed -n "$((POST_STAMP_CC_BEGIN+1)),$((POST_STAMP_CC_END-1))p" "$TARGET" \
  | sed -n 's/^[[:space:]]*exit[[:space:]]*\([0-9][0-9]*\).*/\1/p' || true)

HAS_BAD_EXIT=false
if [ -n "$POST_CC_EXITS" ]; then
  while IFS= read -r code; do
    [ "$code" = "0" ] || [ "$code" = "2" ] || { HAS_BAD_EXIT=true; bad "Invalid exit code $code in post-stamp CC section"; }
  done <<< "$POST_CC_EXITS"
fi

if [ "$HAS_BAD_EXIT" = false ]; then
  ok "All exit codes in post-stamp CC section are 0 or 2"
fi

# ── 4. Bash syntax check ─────────────────────────────────────────────
if bash -n "$TARGET" 2>/dev/null; then
  ok "bash -n $TARGET passes"
else
  bad "bash -n $TARGET fails"
fi

# ── Summary ──────────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo "  U002 regressions: $PASS passed, $FAIL failed"
echo "=============================================="
[ "$FAIL" -eq 0 ] || echo "  ❌ SOME CHECKS FAILED"
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
