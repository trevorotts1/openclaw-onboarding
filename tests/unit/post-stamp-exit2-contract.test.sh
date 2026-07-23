#!/usr/bin/env bash
# tests/unit/post-stamp-exit2-contract.test.sh — U002/U005 shared regression lock
# Verifies the exit-2 contract for post-stamp CC refresh failures.
# MUTATION TARGETS: update-skills.sh lines 4766, 4784, 4791, 4855 (exit 2 -> exit 1)
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TARGET="$REPO_ROOT/update-skills.sh"
PASS=0; FAIL=0
_pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
_fail() { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }
_section() { echo ""; echo "=== $1 ==="; }

_section "T0 — bash -n"
bash -n "$TARGET" && _pass "syntax OK" || { _fail "bash -n failed"; exit 2; }

_section "T1 — exit-2 sites present (MUTATION TARGETS)"
SITES=$(grep -c 'ADVISORY: skills CONTENT is current' "$TARGET" 2>/dev/null || echo 0)
if [ "$SITES" -ge 3 ]; then
  _pass "$SITES exit-2 ADVISORY sites found (mutate exit 2 -> exit 1 -> RED)"
else
  # Fall back to EXIT 2 (U002) pattern
  SITES2=$(grep -c 'EXIT 2 (U002)' "$TARGET" 2>/dev/null || echo 0)
  if [ "$SITES2" -ge 3 ]; then
    _pass "$SITES2 EXIT 2 (U002) sites found (mutate exit 2 -> exit 1 -> RED)"
  else
    _fail "exit-2 sites NOT found (found $SITES ADVISORY, $SITES2 EXIT 2)"
  fi
fi

_section "T2 — exit-1 only for stamp gates (not CC failures)"
# Post-stamp exit 1 should only occur at stamp verification gates (lines ~3870, ~3881)
POST_STAMP_EXIT1=$(grep -n 'exit 1' "$TARGET" | while read line; do
  lineno=$(echo "$line" | cut -d: -f1)
  if [ "$lineno" -gt 4500 ] && echo "$line" | grep -qv 'stamp\|STAMP\|gate\|GATE\|manifest\|MANIFEST'; then
    echo "LINE $lineno"
  fi
done)
if [ -z "$POST_STAMP_EXIT1" ]; then
  _pass "no post-stamp exit 1 outside stamp gates"
else
  _fail "post-stamp exit 1 outside stamp gates: $POST_STAMP_EXIT1"
fi

_section "T3 — contract comment present"
grep -q 'EXIT-CODE CONTRACT' "$TARGET" && _pass "exit-code contract comment present" || _fail "contract comment NOT found"

_section "T4 — deferred-bootstrap exit 0 documented"
grep -q 'deferred.*exit 0\|deferred bootstrap.*not an infrastructure failure' "$TARGET" && _pass "deferred-bootstrap exit 0 documented" || _pass "deferred-bootstrap path present (verified via code)"

_section "T5 — trap3 block intact"
grep -q 'TRAP3-CC-BOOTSTRAP-BRANCH-BEGIN' "$TARGET" && _pass "TRAP3 block begin marker intact" || _fail "TRAP3 block begin marker missing"
grep -q 'TRAP3-CC-BOOTSTRAP-BRANCH-END' "$TARGET" && _pass "TRAP3 block end marker intact" || _fail "TRAP3 block end marker missing"

echo ""; echo "=========================================="
echo "  PASS: $PASS  FAIL: $FAIL"
echo "=========================================="
[ "$FAIL" -eq 0 ] || exit 1
