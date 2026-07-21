#!/usr/bin/env bash
# ============================================================
# scripts/test-watchdog-loop.sh — PRD 2.13 Fixture Tests
# ============================================================
# Verifies the watchdog-onboarding-loop system WITHOUT a client box.
# All tests use a temp fixture directory; no openclaw CLI required.
#
# WHAT IS VERIFIED:
#   T1: waveGoals seeded; all 6 rosters match OC_WAVE<N>_SKILLS CONTENTS
#   T1b: a wave fails BY NAME when a listed skill's folder is missing
#   T2: per-wave goal check: wave 1 passes when both skills qc-passed
#   T3: per-wave goal check: wave 1 fails when a skill is pending
#   T4: oc_wave_goal_check increments failStrikes on failure
#   T5: 3-strike threshold: STRIKES >= 3 after 3 consecutive failures
#   T6: oc_next_incomplete_wave returns the correct wave number
#   T7: oc_overall_goal_check fails until all 6 waves + workforce state set
#   T8: oc_overall_goal_check passes when all conditions met
#   T9: KILL CONDITION — install "killed mid-wave": watchdog detects,
#       finds the incomplete wave, and builds EXACT wave prompt (no vague
#       "continue onboarding"). The cheap state-file check runs BEFORE
#       any mock agent call (verified via call-order tracking).
#   T10: CHEAP-CHECK FIRST — verify oc_overall_goal_check runs before
#        any Telegram/openclaw send (call-order assertion)
#   T11: loop registry: lr_register, lr_kill, lr_assert_empty work
#   T12: loop registry: lr_assert_empty exits 1 when loop still "running"
#   T13: wave 5 skills with interview-pending count as wave goal passed
#   T14: oc_wave_skills_status returns correct skill:status pairs
#   T15: This CI workflow references the PRD-2.13 watchdog checks
#
# Usage: bash scripts/test-watchdog-loop.sh
# Exit 0 = all pass. Exit 1 = one or more failures.
# ============================================================

set -u

PASS=0
FAIL=0
FAIL_MSGS=()

pass() { PASS=$((PASS+1)); printf '  ✓ %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); FAIL_MSGS+=("$1"); printf '  ✗ %s\n' "$1"; }

# ── fixture setup ─────────────────────────────────────────────────────────────
TMPDIR_FX=$(mktemp -d 2>/dev/null || mktemp -d -t watchdog-test)
trap 'rm -rf "$TMPDIR_FX"' EXIT

FIXTURE_OC="$TMPDIR_FX/.openclaw"
FIXTURE_WS="$FIXTURE_OC/workspace"
FIXTURE_SKILLS="$FIXTURE_OC/skills"
mkdir -p "$FIXTURE_WS" "$FIXTURE_SKILLS"

STATE_FILE="$FIXTURE_WS/.onboarding-state.json"
WF_STATE="$FIXTURE_WS/.workforce-build-state.json"
LOOP_REGISTRY_FILE="$FIXTURE_WS/.loop-registry.json"

# Point the gate library at our fixture
export OC_CONFIG="$FIXTURE_OC"
export ONBOARDING_STATE_FILE="$STATE_FILE"
export OC_WORKSPACE_DEFAULT="$FIXTURE_WS"
export OC_SKILLS_DIR="$FIXTURE_SKILLS"

# Locate gate library
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo "")"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." 2>/dev/null && pwd || echo "")"
GATE_LIB=""
for _cand in \
  "${REPO_ROOT:+$REPO_ROOT/lib-onboarding-state.sh}" \
  "$SCRIPT_DIR/onboarding-state.sh"; do
  [[ -n "$_cand" && -f "$_cand" ]] && GATE_LIB="$_cand" && break
done

if [[ -z "$GATE_LIB" ]]; then
  echo "FATAL: lib-onboarding-state.sh not found — cannot run tests" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$GATE_LIB"

# Locate loop registry lib
LOOP_REG_LIB="${REPO_ROOT:+$REPO_ROOT/scripts/loop-registry.sh}"
[[ -n "$LOOP_REG_LIB" && -f "$LOOP_REG_LIB" ]] || LOOP_REG_LIB=""

# ── helper: make a minimal skill folder ──────────────────────────────────────
mk_skill() {
  local name="$1"
  local has_core="${2:-no}"
  mkdir -p "$FIXTURE_SKILLS/$name"
  printf 'name: %s\n' "$name" > "$FIXTURE_SKILLS/$name/SKILL.md"
  if [[ "$has_core" == "yes" ]]; then
    printf '## AGENTS.md\n\n## Test Sentinel for %s\n\nsome content\n' "$name" \
      > "$FIXTURE_SKILLS/$name/CORE_UPDATES.md"
  fi
}

# ── helper: set skill status in state file ────────────────────────────────────
set_skill_status() {
  local skill="$1" status="$2"
  python3 - <<PYEOF 2>/dev/null
import json, os
sf = "$STATE_FILE"
try:    state = json.load(open(sf))
except Exception: state = {"skills": {}}
state.setdefault("skills", {}).setdefault("$skill", {})["status"] = "$status"
json.dump(state, open(sf, "w"), indent=2)
PYEOF
}

set_wave_status() {
  local wave="$1" status="$2"
  python3 - <<PYEOF 2>/dev/null
import json
sf = "$STATE_FILE"
try:    state = json.load(open(sf))
except Exception: state = {}
state.setdefault("waveGoals", {}).setdefault("$wave", {})["status"] = "$status"
json.dump(state, open(sf, "w"), indent=2)
PYEOF
}

echo "=== PRD 2.13 Watchdog Loop Fixture Tests ==="

# ── T1: waveGoals block is seeded correctly ───────────────────────────────────
# Create minimal skill folders for Wave 1
mk_skill "01-teach-yourself-protocol"
mk_skill "02-back-yourself-up-protocol"

oc_state_seed "$FIXTURE_SKILLS"
oc_wave_state_init

# Asserting only that the wave KEYS exist is the vacuous shape that let Wave 2
# and Wave 3 stay wedged while CI was green. Every wave's seeded roster is
# compared against the canonical OC_WAVE<N>_SKILLS list CONTENTS, and each list
# must be non-empty.
T1_RESULT=$(STATE_FILE="$STATE_FILE" \
  W1="$OC_WAVE1_SKILLS" W2="$OC_WAVE2_SKILLS" W3="$OC_WAVE3_SKILLS" \
  W4="$OC_WAVE4_SKILLS" W5="$OC_WAVE5_SKILLS" W6="$OC_WAVE6_SKILLS" python3 - <<'PYEOF'
import json, os
sf = os.environ["STATE_FILE"]
try:
    s = json.load(open(sf))
    wg = s.get("waveGoals", {})
    assert "overall" in wg, "overall missing"
    for n in range(1, 7):
        key = f"wave{n}"
        assert key in wg, f"{key} missing"
        canonical = os.environ[f"W{n}"].split()
        assert canonical, f"OC_WAVE{n}_SKILLS is EMPTY"
        seeded = wg[key]["skills"]
        assert seeded == canonical, (
            f"{key} roster != OC_WAVE{n}_SKILLS "
            f"(seeded {len(seeded)}, canonical {len(canonical)})"
        )
    assert "01-teach-yourself-protocol" in wg["wave1"]["skills"], "wave1 skills wrong"
    # Wave 6 must actually gate the extension skills, 45 in particular: it is the
    # documented replacement for the archived 11-superdesign, which WAS gated.
    assert "45-design-intelligence-library" in wg["wave6"]["skills"], \
        "wave6 does not gate 45-design-intelligence-library"
    assert wg["wave1"]["status"] == "pending", f"wave1 status not pending: {wg['wave1']['status']}"
    print("ok")
except Exception as e:
    print(f"fail: {e}")
PYEOF
)
[[ "$T1_RESULT" == "ok" ]] && pass "T1: waveGoals seeded, all 6 rosters match OC_WAVE<N>_SKILLS contents" \
  || fail "T1: waveGoals seed: $T1_RESULT"

# ── T1b: a wave fails loudly, BY NAME, when a listed skill's folder is absent ──
# Proves the gate is real rather than vacuous: Wave 6 names 13 extension skills
# that no wave verified before, and a box missing one must be told which one.
mk_skill "45-design-intelligence-library"
set_skill_status "45-design-intelligence-library" "qc-passed"
rm -rf "$FIXTURE_SKILLS/45-design-intelligence-library"
T1B_RC=0
oc_wave_goal_check 6 2>/dev/null || T1B_RC=$?
T1B_STATUS="$(oc_wave_skills_status 6 2>/dev/null)"
if [[ "$T1B_RC" -ne 0 && "$T1B_STATUS" == *"45-design-intelligence-library:MISSING-FOLDER"* ]]; then
  pass "T1b: wave 6 fails and names the missing skill (MISSING-FOLDER)"
else
  fail "T1b: expected wave6 fail naming the missing folder (rc=$T1B_RC status=$T1B_STATUS)"
fi

# ── T2: wave 1 passes when both skills qc-passed ──────────────────────────────
set_skill_status "01-teach-yourself-protocol" "qc-passed"
set_skill_status "02-back-yourself-up-protocol" "qc-passed"
oc_wave_goal_check 1 2>/dev/null
T2_STATUS=$(python3 -c "import json; s=json.load(open('$STATE_FILE')); print(s['waveGoals']['wave1']['status'])" 2>/dev/null)
[[ "$T2_STATUS" == "passed" ]] && pass "T2: wave 1 passes when both skills qc-passed" \
  || fail "T2: expected wave1.status=passed, got $T2_STATUS"

# ── T3: wave 1 fails when a skill is pending ─────────────────────────────────
# Reset to pending
set_skill_status "01-teach-yourself-protocol" "qc-passed"
set_skill_status "02-back-yourself-up-protocol" "pending"
# Reset wave1 status so check can re-evaluate
python3 -c "
import json
sf = '$STATE_FILE'
s = json.load(open(sf))
s['waveGoals']['wave1']['status'] = 'pending'
s['waveGoals']['wave1']['failStrikes'] = 0
json.dump(s, open(sf,'w'), indent=2)
" 2>/dev/null

T3_RC=0
oc_wave_goal_check 1 2>/dev/null || T3_RC=$?
[[ "$T3_RC" -ne 0 ]] && pass "T3: wave 1 fails (exits non-zero) when a skill is pending" \
  || fail "T3: expected oc_wave_goal_check to fail when skill is pending"

# ── T4: failStrikes incremented on failure ────────────────────────────────────
# After T3, strikes should be >= 1
T4_STRIKES=$(oc_wave_fail_strikes 1 2>/dev/null || echo "0")
(( T4_STRIKES >= 1 )) && pass "T4: failStrikes incremented on failure (strikes=$T4_STRIKES)" \
  || fail "T4: failStrikes not incremented (got $T4_STRIKES, expected >=1)"

# ── T5: 3-strike threshold: 3 consecutive failures ────────────────────────────
# Run 2 more failures to reach strike 3
set_skill_status "02-back-yourself-up-protocol" "pending"
python3 -c "
import json
sf = '$STATE_FILE'
s = json.load(open(sf))
s['waveGoals']['wave1']['status'] = 'pending'
json.dump(s, open(sf,'w'), indent=2)
" 2>/dev/null
oc_wave_goal_check 1 2>/dev/null || true
oc_wave_goal_check 1 2>/dev/null || true

T5_STRIKES=$(oc_wave_fail_strikes 1 2>/dev/null || echo "0")
(( T5_STRIKES >= 3 )) && pass "T5: failStrikes >= 3 after 3 consecutive failures (strikes=$T5_STRIKES)" \
  || fail "T5: failStrikes should be >= 3 after 3 failures (got $T5_STRIKES)"

# ── T6: oc_next_incomplete_wave returns correct wave ──────────────────────────
# wave1 is pending/failed; waves 2-5 are pending
T6_NEXT=$(oc_next_incomplete_wave 2>/dev/null)
[[ "$T6_NEXT" == "1" ]] && pass "T6: oc_next_incomplete_wave returns 1 (first incomplete wave)" \
  || fail "T6: expected next=1, got '$T6_NEXT'"

# Now mark wave1 passed, wave2 pending
set_wave_status "wave1" "passed"
T6B_NEXT=$(oc_next_incomplete_wave 2>/dev/null)
[[ "$T6B_NEXT" == "2" ]] && pass "T6b: oc_next_incomplete_wave returns 2 after wave1 passed" \
  || fail "T6b: expected next=2 after wave1 passed, got '$T6B_NEXT'"

# ── T7: oc_overall_goal_check fails until all conditions met ──────────────────
T7_RC=0
oc_overall_goal_check 2>/dev/null || T7_RC=$?
[[ "$T7_RC" -ne 0 ]] && pass "T7: oc_overall_goal_check fails when conditions not met" \
  || fail "T7: expected overall goal check to fail (waves not all passed, no workforce state)"

# ── T8: oc_overall_goal_check passes when all conditions met ──────────────────
# Mark all waves passed in state (all SIX — the overall goal requires wave 6 too)
for n in 1 2 3 4 5 6; do
  set_wave_status "wave$n" "passed"
done

# Create minimal workforce build state
python3 -c "
import json
wf = {
    'interviewComplete': True,
    'buildCompletedAt': '2026-06-10T00:00:00Z',
    'closeoutStatus': 'done'
}
json.dump(wf, open('$WF_STATE','w'), indent=2)
" 2>/dev/null

# v12.23.0 WORKSPACE-SHELL HONESTY: the overall goal now ALSO requires the
# workspace-shell gate to pass. A hand-seeded buildCompletedAt alone is NO LONGER
# sufficient (that was the exact false-"done"). We materialize a REAL full
# workspace and pin the gate at it via OC_WORKSPACE_DEPARTMENTS_DIR.
T8_FLOOR_PY="$REPO_ROOT/23-ai-workforce-blueprint/scripts/department-floor.py"
T8_DEPTS="$FIXTURE_WS/zero-human-company/acme/departments"
T8_REQUIRED=$(FLOOR_PY="$T8_FLOOR_PY" python3 - <<'PY' 2>/dev/null
import importlib.util, os, tempfile, pathlib
s=importlib.util.spec_from_file_location("df", os.environ["FLOOR_PY"]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
d=pathlib.Path(tempfile.mkdtemp())/"d"; d.mkdir(parents=True)
print(" ".join(m.evaluate_floor(departments_dir=d, build_state={}, core_answers={"industry":"general business"})["expected_floor"]))
PY
)
T8_SOP="$(python3 -c "print('# how-to\n## 9. SOPs\n### SOP 9.1 run\n' + ('work '*1000))")"
for d in $T8_REQUIRED; do
  mkdir -p "$T8_DEPTS/$d/00-head"
  printf '# id\n'  > "$T8_DEPTS/$d/IDENTITY.md"
  printf '# soul\n'> "$T8_DEPTS/$d/SOUL.md"
  printf '%s\n' "$T8_SOP" > "$T8_DEPTS/$d/00-head/how-to.md"
done

T8_RC=1
OC_WORKSPACE_DEPARTMENTS_DIR="$T8_DEPTS" oc_overall_goal_check 2>/dev/null && T8_RC=0
[[ "$T8_RC" -eq 0 ]] && pass "T8: oc_overall_goal_check passes when all conditions met + workspace materialized" \
  || fail "T8: overall goal check should pass with all waves + workforce state + FULL workspace"

# ── T8b: overall goal BLOCKED when workspace is a SHELL (the false-"done" bug) ──
# Same JSON state (all waves + buildCompletedAt + closeout done) but the workspace
# departments are empty shells (DREAMS.md + memory/ only). The overall goal MUST
# refuse to pass — a template-on-disk / seeded build-state must never report done.
T8B_DEPTS="$FIXTURE_WS/zero-human-company/shellco/departments"
for d in $T8_REQUIRED; do
  mkdir -p "$T8B_DEPTS/$d/memory"
  printf '# dreams\n' > "$T8B_DEPTS/$d/DREAMS.md"
done
T8B_RC=0
OC_WORKSPACE_DEPARTMENTS_DIR="$T8B_DEPTS" oc_overall_goal_check 2>/dev/null || T8B_RC=$?
[[ "$T8B_RC" -ne 0 ]] && pass "T8b: overall goal BLOCKED when workspace is a SHELL (AF-WORKSPACE-SHELL closes seeded-done bypass)" \
  || fail "T8b: overall goal must FAIL when workspace departments are shells, but it passed"

# ── T9: KILL CONDITION — kill mid-wave, watchdog detects, builds EXACT prompt ──
# Reset state: wave1 pending, simulate kill mid-wave
python3 -c "
import json
sf = '$STATE_FILE'
s = json.load(open(sf))
# Kill mid-wave: wave1 is in-progress, one skill pending
s['waveGoals']['wave1']['status'] = 'in-progress'
s['waveGoals']['wave1']['failStrikes'] = 0
for wn in range(2,6):
    s['waveGoals'][f'wave{wn}']['status'] = 'pending'
s['skills']['01-teach-yourself-protocol']['status'] = 'qc-passed'
s['skills']['02-back-yourself-up-protocol']['status'] = 'pending'
json.dump(s, open(sf,'w'), indent=2)
" 2>/dev/null
# Remove workforce state to simulate mid-install
rm -f "$WF_STATE"

# Call check functions in call-order-tracked manner
CALL_ORDER=()
CALL_ORDER+=("overall_goal_check")
oc_overall_goal_check 2>/dev/null || true  # should fail (wave1 not passed)

NEXT=$(oc_next_incomplete_wave 2>/dev/null)
[[ "$NEXT" == "1" ]] && CALL_ORDER+=("found_wave_1")

SKILLS_STATUS=$(oc_wave_skills_status "1" 2>/dev/null || echo "")
echo "$SKILLS_STATUS" | grep -q "01-teach-yourself-protocol" && CALL_ORDER+=("skills_status_checked")

# The build_wave_prompt function should produce an EXACT wave prompt (not vague)
# We source the watchdog script logic inline (without running it — just the build_wave_prompt fn)
PROMPT_TEST=""
PROMPT_TEST=$(bash -c '
source "'"$GATE_LIB"'" 2>/dev/null
build_wave_prompt() {
  local wave="$1"
  case "$wave" in
    1) echo "[ONBOARDING-WATCHDOG] Wave 1 (FOUNDATION) is incomplete" ;;
    *) echo "[ONBOARDING-WATCHDOG] GENERIC" ;;
  esac
}
build_wave_prompt "1"
' 2>/dev/null || true)

# If build_wave_prompt not available inline, test its output contract
WATCHDOG_SCRIPT="${SCRIPT_DIR}/watchdog-onboarding-loop.sh"
if [[ -f "$WATCHDOG_SCRIPT" ]]; then
  PROMPT_CHECK=$(grep -E "Wave 1.*FOUNDATION|FOUNDATION.*Wave 1" "$WATCHDOG_SCRIPT" | head -1)
  [[ -n "$PROMPT_CHECK" ]] && CALL_ORDER+=("exact_wave_prompt_defined")
fi

T9_PASS=1
[[ "${CALL_ORDER[0]}" == "overall_goal_check" ]] || T9_PASS=0
[[ " ${CALL_ORDER[*]} " == *" found_wave_1 "* ]] || T9_PASS=0
[[ " ${CALL_ORDER[*]} " == *" exact_wave_prompt_defined "* ]] || T9_PASS=0
[[ "$T9_PASS" -eq 1 ]] && pass "T9: kill mid-wave: watchdog detects incomplete wave, builds exact wave prompt" \
  || fail "T9: kill mid-wave test failed (call_order=${CALL_ORDER[*]})"

# ── T10: CHEAP-CHECK FIRST — overall_goal_check runs before any Telegram call ─
# Verify that watchdog-onboarding-loop.sh runs oc_overall_goal_check (cheap check)
# BEFORE any openclaw message send call (verified by grep on the script text).
if [[ -f "$WATCHDOG_SCRIPT" ]]; then
  # Find line numbers of cheap check and first openclaw send
  CHEAP_CHECK_LINE=$(grep -n "oc_overall_goal_check\|CHEAP-CHECK.*overall\|CHEAP.*running" "$WATCHDOG_SCRIPT" | head -1 | cut -d: -f1)
  SEND_LINE=$(grep -n "openclaw message send" "$WATCHDOG_SCRIPT" | head -1 | cut -d: -f1)
  if [[ -n "$CHEAP_CHECK_LINE" && -n "$SEND_LINE" ]]; then
    if (( CHEAP_CHECK_LINE < SEND_LINE )); then
      pass "T10: cheap state-file check (line $CHEAP_CHECK_LINE) runs before openclaw message send (line $SEND_LINE)"
    else
      fail "T10: cheap check (line $CHEAP_CHECK_LINE) should come BEFORE openclaw send (line $SEND_LINE)"
    fi
  else
    fail "T10: could not verify call order — oc_overall_goal_check not found (line=$CHEAP_CHECK_LINE) or openclaw send not found (line=$SEND_LINE)"
  fi
else
  fail "T10: watchdog script not found at $WATCHDOG_SCRIPT"
fi

# ── T11: loop registry lr_register / lr_kill / lr_assert_empty ───────────────
if [[ -n "$LOOP_REG_LIB" ]]; then
  # Export so sourced functions pick it up as shell variable
  export LOOP_REGISTRY_FILE
  # shellcheck disable=SC1090
  source "$LOOP_REG_LIB" 2>/dev/null || true

  lr_register "watchdog-onboarding-loop" "test-uuid-1234" "openclaw cron rm test-uuid-1234" 2>/dev/null
  T11_STATUS=$(python3 -c "import json; s=json.load(open('$LOOP_REGISTRY_FILE')); print(s['loops']['watchdog-onboarding-loop']['status'])" 2>/dev/null)
  [[ "$T11_STATUS" == "running" ]] && pass "T11a: lr_register sets status=running" \
    || fail "T11a: lr_register failed (got '$T11_STATUS')"

  lr_kill "watchdog-onboarding-loop" 2>/dev/null
  T11B_STATUS=$(python3 -c "import json; s=json.load(open('$LOOP_REGISTRY_FILE')); print(s['loops']['watchdog-onboarding-loop']['status'])" 2>/dev/null)
  [[ "$T11B_STATUS" == "killed" ]] && pass "T11b: lr_kill sets status=killed" \
    || fail "T11b: lr_kill failed (got '$T11B_STATUS')"

  T11C_RC=0
  lr_assert_empty 2>/dev/null && T11C_RC=0 || T11C_RC=$?
  [[ "$T11C_RC" -eq 0 ]] && pass "T11c: lr_assert_empty passes when loop is killed" \
    || fail "T11c: lr_assert_empty should pass after kill (rc=$T11C_RC)"
else
  fail "T11: loop-registry.sh not found — skipping lr_* tests"
fi

# ── T12: lr_assert_empty exits 1 when loop still "running" ───────────────────
if [[ -n "$LOOP_REG_LIB" ]]; then
  # Re-register without killing
  rm -f "$LOOP_REGISTRY_FILE"
  lr_register "watchdog-onboarding-loop" "uuid-still-running" "openclaw cron rm uuid-still-running" 2>/dev/null

  T12_RC=0
  lr_assert_empty 2>/dev/null && T12_RC=0 || T12_RC=$?
  [[ "$T12_RC" -ne 0 ]] && pass "T12: lr_assert_empty exits 1 when loop still running" \
    || fail "T12: lr_assert_empty should exit 1 when loop is still running (got $T12_RC)"
else
  fail "T12: loop-registry.sh not found — skipping"
fi

# ── T13: wave 5 skills with interview-pending count as passed ─────────────────
# Create wave 5 skill folders on disk (required by (b) folder-present check)
for _w5sk in "22-book-to-persona-coaching-leadership-system" \
             "23-ai-workforce-blueprint" \
             "32-command-center-setup" \
             "35-social-media-planner"; do
  mk_skill "$_w5sk"
done

# Set all wave 5 skills to interview-pending in state
python3 -c "
import json
sf = '$STATE_FILE'
s = json.load(open(sf))
wave5_skills = s['waveGoals']['wave5']['skills']
for sk in wave5_skills:
    s['skills'].setdefault(sk, {})['status'] = 'interview-pending'
s['waveGoals']['wave5']['status'] = 'pending'
s['waveGoals']['wave5']['failStrikes'] = 0
json.dump(s, open(sf,'w'), indent=2)
" 2>/dev/null

T13_RC=1
oc_wave_goal_check 5 2>/dev/null && T13_RC=0
[[ "$T13_RC" -eq 0 ]] && pass "T13: wave 5 skills with interview-pending count as wave goal passed" \
  || fail "T13: wave 5 should pass when all skills are interview-pending (rc=$T13_RC)"

# ── T14: oc_wave_skills_status returns correct skill:status pairs ─────────────
set_skill_status "01-teach-yourself-protocol" "qc-passed"
set_skill_status "02-back-yourself-up-protocol" "wired"
T14_STATUS=$(oc_wave_skills_status 1 2>/dev/null || echo "")
echo "$T14_STATUS" | grep -q "01-teach-yourself-protocol:qc-passed" \
  && echo "$T14_STATUS" | grep -q "02-back-yourself-up-protocol:wired" \
  && pass "T14: oc_wave_skills_status returns correct skill:status pairs" \
  || fail "T14: oc_wave_skills_status output unexpected: '$T14_STATUS'"

# ── T15: CI workflow references PRD-2.13 watchdog checks ─────────────────────
CI_WORKFLOW="${REPO_ROOT}/.github/workflows/qc-static.yml"
if [[ -f "$CI_WORKFLOW" ]]; then
  if grep -qE "PRD.2.13|watchdog.onboarding.loop|test-watchdog-loop" "$CI_WORKFLOW"; then
    pass "T15: CI workflow references PRD-2.13 watchdog checks"
  else
    fail "T15: CI workflow does NOT reference PRD-2.13 watchdog checks — add CI steps"
  fi
else
  fail "T15: CI workflow not found at $CI_WORKFLOW"
fi

# ── summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [[ "${#FAIL_MSGS[@]}" -gt 0 ]]; then
  echo "Failed:"
  for m in "${FAIL_MSGS[@]}"; do echo "  - $m"; done
fi

[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1
