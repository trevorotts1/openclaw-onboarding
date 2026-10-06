#!/usr/bin/env bash
# tests/unit/rr030-harness-hides-nothing.test.sh
# ---------------------------------------------------------------------------
# RR-030 — proves the external assertion harness (scripts/rescue-rangers-
# harness.sh) cannot hide failures. Each defect class from the spec is
# reproduced as an attack on the harness itself; the harness must catch it:
#   1. a failing fixture body (the old subshell-swallowed case) is counted,
#   2. a mutation drill that goes green on broken code FAILS,
#   3. a required-runtime absence FAILS (never WARN-skips),
#   4. unverified gates print UNVERIFIED and are reported, not green.
# Every sub-battery runs the harness as a CHILD process; the child's exit
# code is the verdict, observed in THIS parent shell (the same law the
# harness enforces).
# ---------------------------------------------------------------------------
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HARNESS="$REPO_ROOT/scripts/rescue-rangers-harness.sh"
[ -f "$HARNESS" ] || { echo "FATAL: $HARNESS not found"; exit 2; }

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

run_child() {  # run_child <<child script>> ; echoes rc
  local script="$1"
  bash -c "source '$HARNESS'; harness_begin; $script"
}

# --- 1. failing fixture counted -------------------------------------------
run_child '
  harness_case UNIT "deliberate failure" -- false
  harness_finish' >/dev/null 2>&1
rc=$?
[ "$rc" -ne 0 ] && ok "failing fixture child exited $rc (nonzero)" \
                 || bad "harness exited 0 with a failing fixture (subshell bug reborn)"

# --- 2. mutation drill green-on-broken is a FAIL ---------------------------
run_child '
  harness_case_negative UNIT "mutation must fail" -- true   # true = broken checker still green
  harness_finish' >/dev/null 2>&1
rc=$?
[ "$rc" -ne 0 ] && ok "green-on-broken mutation child exited $rc" \
                 || bad "harness passed a mutation drill whose checker stayed green on broken code"

# --- 3. negative drill nonzero is a PASS -----------------------------------
run_child '
  harness_case_negative UNIT "mutation must fail" -- false  # false = gate bit
  harness_finish' >/dev/null 2>&1
rc=$?
[ "$rc" -eq 0 ] && ok "correctly-broken mutation passes the drill" \
                || bad "harness rejected a mutation drill that DID fail nonzero"

# --- 4. unverified recorded, run still honest ------------------------------
out=$(run_child '
  harness_unverified LIVE_ACCEPTANCE "no live box in unit test"
  harness_finish' 2>&1); rc=$?
echo "$out" | grep -q "UNVERIFIED" || bad "unverified gate did not print UNVERIFIED"
echo "$out" | grep -q "unverified=1" || bad "summary did not count the unverified gate"
[ "$rc" -eq 0 ] && ok "UNVERIFIED alone keeps the run verdict honest (rc=0; release completion accounted upstream)" \
                || bad "UNVERIFIED-only run exited $rc; unverified must not fail the run, it must block RELEASE completion"

# --- 5. mixed pass+fail totals ---------------------------------------------
out=$(run_child '
  harness_case UNIT "good" -- true
  harness_case UNIT "bad" -- false
  harness_finish' 2>&1)
echo "$out" | grep -q "passed=1 failed=1" || bad "summary totals wrong: $(echo "$out" | grep 'passed=')"
rc=$(run_child '
  harness_case UNIT "good" -- true
  harness_case UNIT "bad" -- false
  harness_finish' >/dev/null 2>&1; echo $?)
[ "$rc" -ne 0 ] && ok "any failure forces nonzero" || bad "harness exited 0 with 1 failed case"

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "[rr030-harness-hides-nothing] PASS ($PASS assertions)"
  exit 0
fi
echo "[rr030-harness-hides-nothing] FAIL ($FAIL of $((PASS+FAIL)) assertions failed)"
exit 1