#!/usr/bin/env bash
# tests/unit/dual-sunday-mutex.test.sh — U001 regression lock
# Mutation targets: update-skills.sh:1608 (flock -n) and :1683 (retirement grep -E).
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TARGET="$REPO_ROOT/update-skills.sh"
PASS=0; FAIL=0
_pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
_fail() { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }
_section() { echo ""; echo "=== $1 ==="; }

_section "T0 — bash -n"
bash -n "$TARGET" && _pass "update-skills.sh passes bash -n" || { _fail "bash -n failed"; exit 2; }

_section "T1 — lock functions"
grep -q 'acquire_update_lock()' "$TARGET" && _pass "acquire_update_lock defined" || _fail "acquire_update_lock NOT found"
grep -q 'release_update_lock()' "$TARGET" && _pass "release_update_lock defined" || _fail "release_update_lock NOT found"

_section "T2 — MUTATION TARGET: flock -n guard"
grep -q 'flock -n.*UPDATE_LOCK_FD' "$TARGET" && _pass "flock -n guard present (line ~1608 — mutate to no-op -> RED)" || _fail "flock -n guard NOT found"

_section "T3 — crontab functions"
grep -q 'detect_legacy_sunday_crontab()' "$TARGET" && _pass "detect_legacy defined" || _fail "detect_legacy NOT found"
grep -q 'retire_legacy_sunday_crontab()' "$TARGET" && _pass "retire_legacy defined" || _fail "retire_legacy NOT found"

_section "T4 — MUTATION TARGET: retirement grep -E"
grep -q 'grep -E.*0.*3.*\*.*\*' "$TARGET" && _pass "retirement grep -E present (line ~1683 — mutate gating -> RED)" || _fail "retirement grep -E NOT found"

_section "T5 — Sunday variant coverage"
grep -q '0|7|0,6' "$TARGET" && _pass "Sunday matcher covers 0, 7, and 0,6" || _fail "Sunday matcher NOT widened"

_section "T6 — env failure distinct from contention"
grep -q 'FATAL: cannot create lock' "$TARGET" && _pass "FATAL lock-create message present" || _fail "FATAL lock-create message NOT found"

_section "T7 — trap wired"
grep -q 'trap release_update_lock EXIT' "$TARGET" && _pass "release trap wired in main()" || _fail "release trap NOT wired"

_section "T8 — retirement messages"
grep -q 'RETIRED.*legacy Sunday' "$TARGET" && grep -q 'OWNER NOTICE' "$TARGET" && _pass "retirement prints RETIRED + OWNER NOTICE" || _fail "retirement messages missing"

_section "T9 — install failure preserves original"
grep -q 'original.*intact\|failed to reinstall' "$TARGET" && _pass "install failure preserves original" || _fail "original-intact NOT found"

_section "T10 — acquire_lock first in main()"
MAIN_LINE=$(grep -n '^main()' "$TARGET" | head -1 | cut -d: -f1)
if [ -n "$MAIN_LINE" ]; then
  BLOCK=$(tail -n +"$MAIN_LINE" "$TARGET" | head -25)
  echo "$BLOCK" | grep -q 'acquire_update_lock' && _pass "acquire_update_lock is first action in main()" || _fail "acquire_update_lock NOT first in main()"
else
  _fail "main() not found"
fi

echo ""; echo "=========================================="
echo "  PASS: $PASS  FAIL: $FAIL"
echo "=========================================="
[ "$FAIL" -eq 0 ] || exit 1
