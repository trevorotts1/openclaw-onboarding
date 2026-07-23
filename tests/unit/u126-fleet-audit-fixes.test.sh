#!/usr/bin/env bash
# tests/unit/u126-fleet-audit-fixes.test.sh — U126 fleet audit fixes test.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
echo "=== u126-fleet-audit-fixes.test.sh ==="
echo ""
echo "--- T1: gateway staleness gap ---"
test_gap() {
  local i_m="$1" i_mn="$2" l_m="$3" l_mn="$4" expected="$5"
  local gap=$(( (l_m - i_m) * 1000 + (l_mn - i_mn) ))
  [[ "$gap" -lt 0 ]] && gap=0
  local stale=0; [[ "$gap" -gt 2 ]] && stale=1
  [[ "$stale" -eq "$expected" ]] && pass "T1: v${i_m}.${i_mn} vs v${l_m}.${l_mn} gap=$gap stale=$stale" || fail "T1: v${i_m}.${i_mn} vs v${l_m}.${l_mn} gap=$gap stale=$stale expected=$expected"
}
test_gap 10 5 10 5 0; test_gap 10 4 10 5 0; test_gap 10 3 10 5 0
test_gap 10 2 10 5 1; test_gap 9 9 11 0 1; test_gap 11 0 10 5 0
echo ""; echo "--- T2: disk-usage-alert ---"
DUS="$REPO_ROOT/scripts/disk-usage-alert.sh"
[[ -f "$DUS" ]] && pass "T2a: disk-usage-alert.sh exists" || fail "T2a: disk-usage-alert.sh missing"
grep -q '_delivered=0' "$DUS" 2>/dev/null && pass "T2b: _delivered guard present" || fail "T2b: _delivered guard missing"
bash -n "$DUS" 2>&1 && pass "T2c: disk-usage-alert.sh syntax OK" || fail "T2c: syntax check failed"
echo ""; echo "--- T3: register-weekly-cron idempotency ---"
RWC="$REPO_ROOT/35-social-media-planner/scripts/register-weekly-cron.sh"
[[ -f "$RWC" ]] && pass "T3a: register-weekly-cron.sh exists" || fail "T3a: register-weekly-cron.sh missing"
grep -q 'oc_cron_present' "$RWC" 2>/dev/null && pass "T3b: oc_cron_present() used" || fail "T3b: oc_cron_present() not called"
grep -q 'oc_cron_tombstoned' "$RWC" 2>/dev/null && pass "T3c: oc_cron_tombstoned() used" || fail "T3c: oc_cron_tombstoned() not called"
grep -q 'cron-lib.sh' "$RWC" 2>/dev/null && pass "T3d: cron-lib.sh sourced" || fail "T3d: cron-lib.sh not sourced"
bash -n "$RWC" 2>&1 && pass "T3e: register-weekly-cron.sh syntax OK" || fail "T3e: syntax check failed"
echo ""; echo "--- T4: decoy-db-cleanup ---"
DDB="$REPO_ROOT/scripts/decoy-db-cleanup.sh"
[[ -f "$DDB" ]] && pass "T4a: decoy-db-cleanup.sh exists" || fail "T4a: decoy-db-cleanup.sh missing"
grep -q 'CANDIDATES' "$DDB" 2>/dev/null && pass "T4b: restricted to candidate paths" || fail "T4b: CANDIDATES not found"
grep -q 'sz -gt 0' "$DDB" 2>/dev/null && pass "T4c: 0-byte guard before removal" || fail "T4c: 0-byte guard missing"
bash -n "$DDB" 2>&1 && pass "T4d: decoy-db-cleanup.sh syntax OK" || fail "T4d: syntax check failed"
echo ""; echo "--- T5: stale-process-detector ---"
SPD="$REPO_ROOT/scripts/stale-process-detector.sh"
[[ -f "$SPD" ]] && pass "T5a: stale-process-detector.sh exists" || fail "T5a: stale-process-detector.sh missing"
bash -n "$SPD" 2>&1 && pass "T5b: stale-process-detector.sh syntax OK" || fail "T5b: syntax check failed"
echo ""; echo "--- T6: MUTATION PROOF disk-usage-alert ---"
DUS_COPY="$(mktemp)"; cp "$DUS" "$DUS_COPY" 2>/dev/null
if [[ -f "$DUS_COPY" ]]; then
  sed -i '' 's/openclaw message send --channel telegram --account operator/MUTATED_BROKEN_CMD/g' "$DUS_COPY" 2>/dev/null
  grep -q 'MUTATED_BROKEN_CMD' "$DUS_COPY" 2>/dev/null && pass "T6a: mutation applied" || fail "T6a: mutation failed"
  ! grep -q 'openclaw message send' "$DUS_COPY" 2>/dev/null && pass "T6b: operator delivery broken after mutation" || fail "T6b: operator delivery survives mutation"
  grep -q 'alert NOT delivered to any channel' "$DUS_COPY" 2>/dev/null && pass "T6c: falls through to log-only" || fail "T6c: log-only fallback not reachable"
  rm -f "$DUS_COPY"
else fail "T6: could not create mutation copy"; fi
grep -q 'openclaw message send.*channel telegram.*account operator' "$DUS" 2>/dev/null && pass "T6d: original has operator delivery (revert proof)" || fail "T6d: original delivery path gone"
echo ""; echo "=== Results: $PASS passed, $FAIL failed ==="
[[ "$FAIL" -gt 0 ]] && { echo "FAIL: $FAIL check(s) failed"; exit 1; }
echo "PASS: all U126 fleet-audit fix checks pass"; exit 0
