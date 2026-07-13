#!/usr/bin/env bash
# tests/unit/d5-dept-activation-floor-gate.test.sh
#
# CI guard for the D5 dept-agent activation floor check (F2 fix). Before this
# fix, update-skills.sh evaluated dept-agent activation against a fixed
# `agents.list[] -lt 2` magic number. A real interview-complete box carries
# the 28-department universal floor (department-naming-map.json: 22
# mandatory + 6 universal-primary), so a box whose dept-agent activation
# genuinely failed for MOST departments but still kept >=2 agents.list[]
# entries evaluated as a false "fully activated" -- the exact "copied !=
# live" defect this check exists to catch.
#
# v20.0.10 CONTRACT NOTE: dept-agent activation is WORKFORCE-provisioning
# completeness, so as of v20.0.10 a miss no longer WITHHOLDS the skills-content
# .onboarding-version stamp -- it feeds a workforce ADVISORY (surfaced + driven
# to green by the post-stamp qc-completeness run + the onboarding-resume cron).
# This test still asserts the FLOOR COMPARISON correctly DETECTS a partially-
# activated box (the signal the advisory consumes); it does not assert stamp
# withholding, so it is unaffected by the content-vs-workforce decoupling.
#
# Proves:
#   (A) STATIC          -- update-skills.sh's D5 gate no longer gates SOLELY
#                           on the fixed "-lt 2" threshold; it derives a
#                           per-box expected department count from
#                           department-floor.py's expected_floor_count.
#   (B) REAL FLOOR       -- department-floor.py, run hermetically against
#                           THIS repo's real department-naming-map.json with
#                           an empty (no-decline) build-state, reports
#                           expected_floor_count == 28 (22 mandatory + 6
#                           universal-primary) -- the actual data source the
#                           gate now reads, not another magic number.
#   (C) PARTIAL-ACTIVATION DETECTED -- replaying the exact bash comparison the
#                           check uses (agents.list[] count vs the computed
#                           expected floor) with an interview-complete,
#                           partially-materialized box (agent count 3 --
#                           ABOVE the OLD "-lt 2" threshold, so the OLD check
#                           would have false-PASSED it, but far below the
#                           28-department floor) asserts the NEW check DETECTS
#                           the incomplete activation (v20.0.10: this feeds the
#                           workforce advisory, not the content stamp).
#   (D) FULLY-ACTIVATED CLEARS -- the same comparison with agent count ==
#                           the computed floor (28) asserts the check does
#                           NOT flag a fully-activated box.
#
# Fully hermetic: department-floor.py accepts an explicit --departments-dir
# override so this test never touches a real ~/.openclaw or a real company
# workspace; HOME is sandboxed so load_build_state() never reads real state.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

UPDATE_SH="$REPO_ROOT/update-skills.sh"
FLOOR_SCRIPT="$REPO_ROOT/23-ai-workforce-blueprint/scripts/department-floor.py"

# Hermetic sandbox -- never resolve into a real ~/.openclaw.
SANDBOX="$(mktemp -d)"
export HOME="$SANDBOX/home"
mkdir -p "$HOME"
cleanup() { rm -rf "$SANDBOX" 2>/dev/null || true; }
trap cleanup EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox path resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

echo "=== d5-dept-activation-floor-gate.test.sh ==="
echo "  sandbox: $SANDBOX"
echo ""

# ---------------------------------------------------------------------------
# (A) STATIC -- the D5 gate reads department-floor.py's expected_floor_count,
# not a bare fixed "-lt 2" threshold.
# ---------------------------------------------------------------------------
echo "--- (A) STATIC: D5 gate derives its threshold from department-floor.py ---"

if [ -f "$UPDATE_SH" ] && grep -q '23-ai-workforce-blueprint/scripts/department-floor.py' "$UPDATE_SH"; then
  pass "A1: update-skills.sh D5 block references department-floor.py"
else
  fail "A1: update-skills.sh D5 block does not reference department-floor.py"
fi
if [ -f "$UPDATE_SH" ] && grep -q "expected_floor_count" "$UPDATE_SH"; then
  pass "A2: update-skills.sh D5 block reads expected_floor_count"
else
  fail "A2: update-skills.sh D5 block does not read expected_floor_count"
fi
if [ -f "$UPDATE_SH" ] && grep -q '_D5_EXPECTED_COUNT' "$UPDATE_SH"; then
  pass "A3: update-skills.sh D5 block computes a per-box _D5_EXPECTED_COUNT (not a bare magic number)"
else
  fail "A3: update-skills.sh D5 block has no per-box expected-count variable -- still a bare magic number?"
fi

# ---------------------------------------------------------------------------
# (B) REAL FLOOR -- department-floor.py reports the true 28-department floor
# hermetically (sandboxed HOME, empty build-state, explicit --departments-dir).
# ---------------------------------------------------------------------------
echo ""
echo "--- (B) REAL FLOOR: department-floor.py expected_floor_count (hermetic) ---"

EXPECTED_COUNT=""
if [ -f "$FLOOR_SCRIPT" ] && command -v python3 >/dev/null 2>&1; then
  FIXTURE_DEPTS="$SANDBOX/departments"
  mkdir -p "$FIXTURE_DEPTS"
  FLOOR_JSON="$(python3 "$FLOOR_SCRIPT" --json --departments-dir "$FIXTURE_DEPTS" 2>/dev/null || true)"
  EXPECTED_COUNT="$(printf '%s' "$FLOOR_JSON" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
n = d.get('expected_floor_count')
if isinstance(n, int) and n > 0:
    sys.stdout.write(str(n))
" 2>/dev/null || true)"
else
  fail "B1: department-floor.py or python3 not available -- cannot verify real floor"
fi

if [ "$EXPECTED_COUNT" = "28" ]; then
  pass "B1: department-floor.py reports expected_floor_count=28 (22 mandatory + 6 universal-primary, no declines)"
else
  fail "B1: department-floor.py reported expected_floor_count='$EXPECTED_COUNT' (expected 28)"
fi

# ---------------------------------------------------------------------------
# (C) / (D) -- replay the exact D5 comparison the gate uses.
# ---------------------------------------------------------------------------
echo ""
echo "--- (C/D) GATE COMPARISON: partial-activation blocked, full-activation passes ---"

d5_gate_blocks() {
  # Mirrors update-skills.sh's D5 comparison exactly:
  #   [ -z "$AGENT_COUNT" ] || [ "$AGENT_COUNT" -lt "$EXPECTED_COUNT" ]
  local agent_count="$1" expected_count="$2"
  [ -z "$agent_count" ] || [ "$agent_count" -lt "$expected_count" ]
}

if [ -n "$EXPECTED_COUNT" ]; then
  # (C) Partial activation: agent_count=3 is ABOVE the OLD "-lt 2" threshold
  # (the old gate would have PASSED this box) but far below the real floor --
  # this is the exact false-PASS hole F2 reported.
  if d5_gate_blocks "3" "$EXPECTED_COUNT"; then
    pass "C1: partial-activation box (3 agents, floor=$EXPECTED_COUNT) is DETECTED by the new floor check (feeds workforce advisory)"
  else
    fail "C1: partial-activation box (3 agents, floor=$EXPECTED_COUNT) was NOT detected -- false-PASS hole still open"
  fi
  # Sanity: the OLD threshold alone would have let 3 agents PASS -- prove that
  # was true, so the fixture above is a genuine regression case, not a strawman.
  if [ 3 -lt 2 ]; then
    fail "sanity: 3 -lt 2 evaluated true (fixture is broken)"
  else
    pass "C2: sanity -- 3 agents would have PASSED the OLD '-lt 2' gate (confirms this is the real false-PASS case)"
  fi

  # (D) Full activation: agent_count == the computed floor must NOT block.
  if d5_gate_blocks "$EXPECTED_COUNT" "$EXPECTED_COUNT"; then
    fail "D1: fully-activated box (agents==floor==$EXPECTED_COUNT) was incorrectly FLAGGED"
  else
    pass "D1: fully-activated box (agents==floor==$EXPECTED_COUNT) is NOT flagged"
  fi
else
  fail "C1/C2/D1: skipped -- department-floor.py did not produce a usable expected_floor_count in (B)"
fi

echo ""
echo "=== RESULTS: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
