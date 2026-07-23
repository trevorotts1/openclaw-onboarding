#!/usr/bin/env bash
# tests/unit/u058-anthology-eight-stage-contract.test.sh — U058
#
# Proves the anthology writer's eight-stage contract is MACHINE-CHECKABLE and
# that the done transition is gated on per-stage prover evidence, not the
# producing agent's self-assessment:
#
#   T1. PHASE_ORDER defines exactly the canonical eight stages in order
#       (P0-INTAKE → P0A-AVATAR → P1-FIDELITY → P2-TONE-AUTHOR → P3-TONE-QC →
#        P4-TITLE-LOCK → P5-CHAPTER-AUTHOR → P6-CHAPTER-QC → P7-DELIVER).
#   T2. The built-in self-test (run_anthology.py --self-test) passes — it proves
#       the phase wiring, the fail-closed checkers, and the prover-gated
#       delivery gate all BITE (each was an evidence-free no-op before the fix).
#   T3. MUTATION: breaking the contract (removing a stage from PHASE_ORDER)
#       makes the self-test FAIL (RED); the original still passes (GREEN) — the
#       gate is discriminating, not blind.
#
# Exit 0 = all pass; non-zero = a check failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SKILL_DIR="$REPO_ROOT/54-anthology-writer"
RUN="$SKILL_DIR/run_anthology.py"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1" >&2; FAIL=$((FAIL+1)); }

echo "== T1: PHASE_ORDER defines the canonical eight stages in order =="
python3 - "$RUN" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("ra", sys.argv[1])
ra = importlib.util.module_from_spec(spec); spec.loader.exec_module(ra)
expected = ["P0-INTAKE", "P0A-AVATAR", "P1-FIDELITY", "P2-TONE-AUTHOR", "P3-TONE-QC",
            "P4-TITLE-LOCK", "P5-CHAPTER-AUTHOR", "P6-CHAPTER-QC", "P7-DELIVER"]
sys.exit(0 if ra.PHASE_ORDER == expected else 1)
PY
[ $? -eq 0 ] && pass "PHASE_ORDER is the canonical eight stages in order" \
  || fail "PHASE_ORDER is not the canonical eight stages"

echo "== T2: the built-in self-test passes (contract is machine-checkable) =="
out="$(python3 "$RUN" --self-test 2>&1)"; rc=$?
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q "ALL ASSERTIONS PASSED"; then
  pass "run_anthology.py --self-test passes (exit 0, ALL ASSERTIONS PASSED)"
else
  fail "run_anthology.py --self-test failed (exit $rc)"
fi

echo "== T3: MUTATION — breaking the contract makes the self-test FAIL =="
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -R "$SKILL_DIR" "$TMP/skill"
# Break the contract: remove a stage from PHASE_ORDER (the producing agent would
# then be able to skip P0A-AVATAR with no machine-checkable gate).
python3 - "$TMP/skill/run_anthology.py" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
s = s.replace('"P0-INTAKE", "P0A-AVATAR", "P1-FIDELITY"', '"P0-INTAKE", "P1-FIDELITY"')
open(p, "w").write(s)
PY
python3 "$TMP/skill/run_anthology.py" --self-test >/dev/null 2>&1; mut_rc=$?
if [ $mut_rc -ne 0 ]; then
  pass "MUTATION: a broken contract (missing stage) makes the self-test FAIL (exit $mut_rc) — RED"
else
  fail "MUTATION: a broken contract still passed the self-test — the gate is blind"
fi
# The original still passes (GREEN).
python3 "$RUN" --self-test >/dev/null 2>&1; orig_rc=$?
[ "$orig_rc" = "0" ] && pass "MUTATION: the original contract still passes (GREEN)" \
  || fail "MUTATION: the original contract no longer passes (exit $orig_rc)"

echo ""
echo "==================================================="
echo "  u058-anthology-eight-stage-contract: PASS=$PASS FAIL=$FAIL"
echo "==================================================="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
