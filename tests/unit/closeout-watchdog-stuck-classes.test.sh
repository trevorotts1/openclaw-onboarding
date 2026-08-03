#!/usr/bin/env bash
# tests/unit/closeout-watchdog-stuck-classes.test.sh
#
# CI guard for the closeout-readiness-watchdog BLIND SPOT fix.
#
# THE DEFECT. With interviewComplete=true, a build-eligible QC verdict and
# buildCompletedAt empty, the watchdog only tripped on (a) resumeAttempts >= max or
# (b) departments empty / all-pending. A box with EVERY department done, a FAILED
# library and resumeAttempts=0 matched NO class at all, so the watchdog logged
# "no stuck condition detected ... all clear" every 6h for the whole multi-day stall
# and nobody was ever told. That is the operator-visibility half of a silent strand.
#
# Nothing was watching the recovery MACHINERY either: resume-workforce-build.sh is,
# by its own header, "the ONLY autonomous-recovery layer in the workforce-build
# pipeline", it self-removes on several paths and parks itself after its stuck cap,
# and un-parking is operator-only -- so a box could sit with no recovery lane at all
# and no notification.
#
# GROUPS (each functional assertion is paired with a MUTATION PROOF that reverts
# only that fix in a sandboxed copy and confirms the old behavior returns, so no
# assertion can pass vacuously):
#   (1) GATES_INCOMPLETE      -- all departments done + a library not done +
#                                buildCompletedAt empty past the threshold raises
#                                STUCK_BUILD_GATES_INCOMPLETE and writes a blocker.
#   (2) PARTWAY_STALL         -- a build stalled mid-way with resumeAttempts under the
#                                cap raises STUCK_PRE_CLOSEOUT instead of "all clear".
#   (3) NEEDS_REVIEW_NO_MASK  -- needs-review is no longer classed STUCK_QC_FAILED, so
#                                it cannot pin a box at that class and mask the real
#                                reason it is wedged.
#   (4) VOCABULARY            -- departments written as "complete" still count as done.
#   (5) RECOVERY_LANE_MISSING -- an absent resume cron is detected, an auto-restore is
#                                attempted via ensure-pipeline-crons.sh, and the
#                                condition is escalated either way.
#   (6) RECOVERY_LANE_PARKED  -- a parked box is escalated but NEVER auto-un-parked.
#   (7) NO_FALSE_POSITIVE     -- a healthy, recently-progressing box stays "all clear".
#
# HERMETIC. Every case runs a COPY of the watchdog from inside a private sandbox with
# OC_ROOT/HOME/ZHC_STATE_FILE pointed into that sandbox, a fake `openclaw` on PATH,
# and ZHC_SKIP_TG_PREFLIGHT=1 so no Telegram send and no webhook POST is attempted.
# No real Skill-23 script runs and nothing can reach a real ~/.openclaw.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WATCHDOG="$REPO_ROOT/23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh"
FAKE_OC="$REPO_ROOT/tests/fixtures/fake-openclaw-cron.py"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== closeout-watchdog-stuck-classes.test.sh ==="
echo ""

for _need in "$WATCHDOG" "$FAKE_OC"; do
  if [[ ! -f "$_need" ]]; then
    echo "FAIL: required file missing: $_need"
    exit 1
  fi
done
if ! command -v python3 >/dev/null 2>&1; then
  echo "FAIL: python3 required"
  exit 1
fi

bash -n "$WATCHDOG" && pass "0a: closeout-readiness-watchdog.sh is bash -n clean" \
                    || fail "0a: closeout-readiness-watchdog.sh has a syntax error"

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

RESUME_CRON_UUID="aabbccdd-1122-3344-5566-778899aabbcc"

# ISO timestamp N hours in the past — the fixtures' clock.
_ago() { python3 -c "
import sys
from datetime import datetime, timedelta, timezone
print((datetime.now(timezone.utc) - timedelta(hours=int(sys.argv[1]))).strftime('%Y-%m-%dT%H:%M:%SZ'))
" "$1"; }

# Build a hermetic box.
#   $1 = name  $2 = build-state JSON  $3 = "present"|"absent" resume cron
#   $4 = optional: "parked" to lay down the park marker
#   $5 = optional: "stub-registrar" to provide a registrar that really registers
_mkbox() {
  local name="$1" state_json="$2" cron="$3" parked="${4:-}" registrar="${5:-}"
  local h="$SANDBOX/$name"
  local skill="$h/.openclaw/skills/23-ai-workforce-blueprint/scripts"
  mkdir -p "$skill" "$h/.openclaw/workspace" "$h/bin"

  # Run a COPY from inside the sandbox so SCRIPT_DIR/REPO_ROOT resolve here, not
  # into the checkout — that keeps the registrar lookup under test control.
  cp "$WATCHDOG" "$skill/closeout-readiness-watchdog.sh"

  cat > "$h/bin/openclaw" <<SHIM
#!/usr/bin/env bash
exec python3 "$FAKE_OC" "\$@"
SHIM
  chmod +x "$h/bin/openclaw"

  printf '%s' "$state_json" > "$h/.openclaw/workspace/.workforce-build-state.json"
  if [[ "$cron" == "present" ]]; then
    printf '[{"name":"workforce-build-resume","id":"%s","kind":"command"}]' "$RESUME_CRON_UUID" > "$h/jobs.json"
  else
    printf '[]' > "$h/jobs.json"
  fi
  : > "$h/calls.log"

  if [[ "$parked" == "parked" ]]; then
    mkdir -p "$h/.openclaw/workspace/.park"
    echo "PARKED test-fixture reason=stuck" > "$h/.openclaw/workspace/.park/workforce-build.parked"
  fi

  if [[ "$registrar" == "stub-registrar" ]]; then
    # Stands in for scripts/ensure-pipeline-crons.sh at a path the watchdog probes
    # ($OC_ROOT/scripts/...). Registers the cron through the same fake CLI, so the
    # watchdog's post-restore re-check sees a genuine state change.
    mkdir -p "$h/.openclaw/scripts"
    cat > "$h/.openclaw/scripts/ensure-pipeline-crons.sh" <<'REGEOF'
#!/usr/bin/env bash
openclaw cron add --name workforce-build-resume --cron "*/15 * * * *" --command /bin/true
REGEOF
  fi
  printf '%s' "$h"
}

# Run a box's watchdog. Echoes nothing; output lands in $h/run.out.
_run() {
  local h="$1"; shift
  env -i \
    PATH="$h/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" \
    HOME="$h" \
    TMPDIR="${TMPDIR:-/tmp}" \
    OC_ROOT="$h/.openclaw" \
    ZHC_STATE_FILE="$h/.openclaw/workspace/.workforce-build-state.json" \
    ZHC_SKIP_TG_PREFLIGHT=1 \
    FAKE_OC_JOBS_FILE="$h/jobs.json" \
    FAKE_OC_CALLS_FILE="$h/calls.log" \
    "$@" \
    bash "$h/.openclaw/skills/23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh" --local \
    >"$h/run.out" 2>&1
  return 0
}

# Does the state file carry a blocker of this class?
_has_blocker() {
  python3 -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
sys.exit(0 if any(
    isinstance(b, dict) and b.get('class') == sys.argv[2]
    for b in (d.get('closeoutBlockers') or [])
) else 1)
" "$1" "$2"
}

T48="$(_ago 48)"
T1="$(_ago 1)"

# All departments done, SOP library FAILED, buildCompletedAt never written.
STATE_GATES_OPEN="$(cat <<EOF
{
  "interviewComplete": true,
  "interviewQc": {"status": "pass"},
  "companyName": "Fixture Co",
  "agentName": "FixtureOrchestrator",
  "closeoutStatus": "pending",
  "roleLibraryStatus": "done",
  "sopLibraryStatus": "failed",
  "commsAutomationStatus": "not-applicable",
  "resumeAttempts": 0,
  "maxResumeAttempts": 12,
  "interviewCompletedAt": "$T48",
  "interviewProgress": {"lastQuestionAt": "$T48"},
  "departments": [
    {"id": "alpha", "status": "done", "completedAt": "$T48"},
    {"id": "bravo", "status": "done", "completedAt": "$T48"},
    {"id": "charlie", "status": "done", "completedAt": "$T48"}
  ]
}
EOF
)"

# ---------------------------------------------------------------------------
# (1) GATES_INCOMPLETE
# ---------------------------------------------------------------------------
echo ""
echo "--- (1) GATES_INCOMPLETE: all depts done + failed library + no buildCompletedAt ---"
B1="$(_mkbox box1 "$STATE_GATES_OPEN" present)"
_run "$B1"
if grep -q "STUCK CLASS: STUCK_BUILD_GATES_INCOMPLETE" "$B1/run.out"; then
  pass "1a: raised STUCK_BUILD_GATES_INCOMPLETE"
else
  fail "1a: did NOT raise STUCK_BUILD_GATES_INCOMPLETE — got: $(grep -oE 'STUCK CLASS: [A-Z_]+|no stuck condition detected' "$B1/run.out" | head -1)"
fi
if grep -q "sopLibraryStatus=failed" "$B1/run.out"; then
  pass "1b: the escalation reason names the gate that is open"
else
  fail "1b: the escalation reason does not name the open gate"
fi
if _has_blocker "$B1/.openclaw/workspace/.workforce-build-state.json" STUCK_BUILD_GATES_INCOMPLETE; then
  pass "1c: a closeoutBlockers entry was persisted for the operator surface"
else
  fail "1c: no closeoutBlockers entry persisted"
fi

echo ""
echo "--- (1-MUT) MUTATION PROOF: without the new class the SAME box reports all clear ---"
B1M="$(_mkbox box1m "$STATE_GATES_OPEN" present)"
MUT1="$B1M/.openclaw/skills/23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh"
python3 - "$MUT1" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
start = src.index('  elif (( dept_total > 0 )) && (( build_idle_hours >= ZHC_STUCK_CLOSEOUT_HOURS )); then')
end = src.index('  fi\nelse\n  # buildCompletedAt set - check closeout', start)
open(path, "w").write(src[:start] + src[end:])
PYEOF
mut1_rc=$?
if (( mut1_rc != 0 )); then
  fail "1-MUT: could not remove the new branch — cannot prove 1a discriminates"
else
  _run "$B1M"
  if grep -q "no stuck condition detected" "$B1M/run.out"; then
    pass "1-MUT: pre-fix watchdog reports 'no stuck condition detected ... all clear' on this box — 1a is a real, non-vacuous check"
  else
    fail "1-MUT: pre-fix watchdog did not report all-clear — 1a proves nothing ($(grep -oE 'STUCK CLASS: [A-Z_]+' "$B1M/run.out" | head -1))"
  fi
fi

# ---------------------------------------------------------------------------
# (2) PARTWAY_STALL
# ---------------------------------------------------------------------------
echo ""
echo "--- (2) PARTWAY_STALL: build stalled mid-way, attempts under the cap ---"
STATE_PARTWAY="$(cat <<EOF
{
  "interviewComplete": true,
  "interviewQc": {"status": "pass"},
  "companyName": "Fixture Co",
  "agentName": "FixtureOrchestrator",
  "closeoutStatus": "pending",
  "roleLibraryStatus": "pending",
  "sopLibraryStatus": "pending",
  "resumeAttempts": 3,
  "maxResumeAttempts": 12,
  "interviewCompletedAt": "$T48",
  "interviewProgress": {"lastQuestionAt": "$T48"},
  "departments": [
    {"id": "alpha", "status": "done", "completedAt": "$T48"},
    {"id": "bravo", "status": "building"},
    {"id": "charlie", "status": "pending"}
  ]
}
EOF
)"
B2="$(_mkbox box2 "$STATE_PARTWAY" present)"
_run "$B2"
if grep -q "STUCK CLASS: STUCK_PRE_CLOSEOUT" "$B2/run.out"; then
  pass "2a: a part-way stall under the attempt cap raises STUCK_PRE_CLOSEOUT"
else
  fail "2a: part-way stall not detected — got: $(grep -oE 'STUCK CLASS: [A-Z_]+|no stuck condition detected' "$B2/run.out" | head -1)"
fi
if grep -q "1/3 departments done" "$B2/run.out"; then
  pass "2b: the reason quantifies how far the build actually got"
else
  fail "2b: the reason does not quantify build progress"
fi

# ---------------------------------------------------------------------------
# (3) NEEDS_REVIEW_NO_MASK
# ---------------------------------------------------------------------------
echo ""
echo "--- (3) NEEDS_REVIEW_NO_MASK: needs-review must not pin the box at STUCK_QC_FAILED ---"
STATE_NR="${STATE_GATES_OPEN/\"status\": \"pass\"/\"status\": \"needs-review\"}"
B3="$(_mkbox box3 "$STATE_NR" present)"
_run "$B3"
if grep -q "STUCK CLASS: STUCK_QC_FAILED" "$B3/run.out"; then
  fail "3a: needs-review still classed STUCK_QC_FAILED — it masks the real blocker"
else
  pass "3a: needs-review is not classed STUCK_QC_FAILED"
fi
if grep -q "STUCK CLASS: STUCK_BUILD_GATES_INCOMPLETE" "$B3/run.out"; then
  pass "3b: with the mask gone the box reaches its REAL class (gates incomplete)"
else
  fail "3b: needs-review box did not reach the real class"
fi
# `fail` must still be a genuine QC stop.
STATE_FAILQC="${STATE_GATES_OPEN/\"status\": \"pass\"/\"status\": \"fail\"}"
B3B="$(_mkbox box3b "$STATE_FAILQC" present)"
_run "$B3B"
if grep -q "STUCK CLASS: STUCK_QC_FAILED" "$B3B/run.out"; then
  pass "3c: a genuine qc=fail is still classed STUCK_QC_FAILED"
else
  fail "3c: qc=fail is no longer detected — the QC stop was widened too far"
fi

# ---------------------------------------------------------------------------
# (4) VOCABULARY
# ---------------------------------------------------------------------------
echo ""
echo "--- (4) VOCABULARY: departments written as 'complete' still count as done ---"
STATE_VOCAB="${STATE_GATES_OPEN//\"status\": \"done\", \"completedAt\"/\"status\": \"complete\", \"completedAt\"}"
B4="$(_mkbox box4 "$STATE_VOCAB" present)"
_run "$B4"
if grep -q "STUCK CLASS: STUCK_BUILD_GATES_INCOMPLETE" "$B4/run.out"; then
  pass "4a: 'complete' departments counted as done — the gates class still fires"
else
  fail "4a: the synonym blinded the watchdog — got: $(grep -oE 'STUCK CLASS: [A-Z_]+|no stuck condition detected' "$B4/run.out" | head -1)"
fi
if grep -q "All 3 departments are done" "$B4/run.out"; then
  pass "4b: all 3 synonym-written departments were counted"
else
  fail "4b: department count is wrong under the synonym"
fi

# ---------------------------------------------------------------------------
# (5) RECOVERY_LANE_MISSING
# ---------------------------------------------------------------------------
echo ""
echo "--- (5) RECOVERY_LANE_MISSING: an absent resume cron is detected + escalated ---"
B5="$(_mkbox box5 "$STATE_GATES_OPEN" absent)"
_run "$B5"
if grep -q "STUCK CLASS: STUCK_RECOVERY_LANE_MISSING" "$B5/run.out"; then
  pass "5a: an absent workforce-build-resume cron raises STUCK_RECOVERY_LANE_MISSING"
else
  fail "5a: an absent recovery cron was NOT escalated"
fi
if grep -q "AUTO-HEAL UNAVAILABLE" "$B5/run.out"; then
  pass "5b: with no registrar reachable it says so explicitly instead of claiming a heal"
else
  fail "5b: did not report the auto-heal outcome honestly"
fi
# The independent finding must NOT swallow the client stuck class in the same pass.
if grep -q "STUCK CLASS: STUCK_BUILD_GATES_INCOMPLETE" "$B5/run.out"; then
  pass "5c: the client stuck class ALSO fired in the same pass (neither masks the other)"
else
  fail "5c: the recovery-lane finding masked the client stuck class"
fi

echo ""
echo "--- (5b) SELF-HEAL: with a registrar reachable the cron is restored ---"
B5B="$(_mkbox box5b "$STATE_GATES_OPEN" absent "" stub-registrar)"
_run "$B5B"
if grep -q "AUTO-HEALED" "$B5B/run.out"; then
  pass "5d: the watchdog ran the registrar and confirmed the cron came back"
else
  fail "5d: the self-heal path did not confirm a restore ($(grep -oE 'AUTO-HEAL[A-Z -]*' "$B5B/run.out" | head -1))"
fi
if grep -q '^cron add --name workforce-build-resume' "$B5B/calls.log" 2>/dev/null; then
  pass "5e: the restore really registered the cron through the CLI (not just logged)"
else
  fail "5e: no cron add was issued — the restore was cosmetic"
fi

echo ""
echo "--- (5-MUT) MUTATION PROOF: without the check an absent cron is invisible ---"
B5M="$(_mkbox box5m "$STATE_GATES_OPEN" absent)"
MUT5="$B5M/.openclaw/skills/23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh"
python3 - "$MUT5" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
start = src.index('# ── RECOVERY-LANE CHECK')
end = src.index('# ── Stuck class classification', start)
open(path, "w").write(src[:start] + src[end:])
PYEOF
mut5_rc=$?
if (( mut5_rc != 0 )); then
  fail "5-MUT: could not remove the recovery-lane check — cannot prove 5a discriminates"
else
  _run "$B5M"
  if grep -q "STUCK_RECOVERY_LANE_MISSING" "$B5M/run.out"; then
    fail "5-MUT: the mutated watchdog still escalated — 5a proves nothing"
  else
    pass "5-MUT: without the check a box with NO recovery lane is never reported — 5a is a real, non-vacuous check"
  fi
fi

# ---------------------------------------------------------------------------
# (6) RECOVERY_LANE_PARKED
# ---------------------------------------------------------------------------
echo ""
echo "--- (6) RECOVERY_LANE_PARKED: a parked box is escalated but never auto-un-parked ---"
B6="$(_mkbox box6 "$STATE_GATES_OPEN" absent parked stub-registrar)"
_run "$B6"
if grep -q "STUCK CLASS: STUCK_RECOVERY_LANE_MISSING" "$B6/run.out"; then
  pass "6a: a parked box with an unfinished build is escalated"
else
  fail "6a: a parked box was not escalated"
fi
if [[ -f "$B6/.openclaw/workspace/.park/workforce-build.parked" ]]; then
  pass "6b: the park marker was NOT cleared (un-parking stays operator-only)"
else
  fail "6b: the watchdog CLEARED the park marker — auto-resume must never happen silently"
fi
if grep -q '^cron add' "$B6/calls.log" 2>/dev/null; then
  fail "6c: the watchdog re-registered the cron on a PARKED box — it resurrected a furnace an operator stopped"
else
  pass "6c: no cron was registered on a parked box"
fi
if grep -qi "unpark-build.sh" "$B6/run.out"; then
  pass "6d: the escalation tells the operator the exact un-park path"
else
  fail "6d: the escalation does not name the un-park path"
fi

# ---------------------------------------------------------------------------
# (7) NO_FALSE_POSITIVE
# ---------------------------------------------------------------------------
echo ""
echo "--- (7) NO_FALSE_POSITIVE: a healthy, recently-progressing box stays all clear ---"
STATE_HEALTHY="$(cat <<EOF
{
  "interviewComplete": true,
  "interviewQc": {"status": "pass"},
  "companyName": "Fixture Co",
  "agentName": "FixtureOrchestrator",
  "closeoutStatus": "pending",
  "roleLibraryStatus": "pending",
  "sopLibraryStatus": "pending",
  "resumeAttempts": 2,
  "maxResumeAttempts": 12,
  "interviewCompletedAt": "$T1",
  "interviewProgress": {"lastQuestionAt": "$T1"},
  "departments": [
    {"id": "alpha", "status": "done", "completedAt": "$T1"},
    {"id": "bravo", "status": "building"}
  ]
}
EOF
)"
B7="$(_mkbox box7 "$STATE_HEALTHY" present)"
_run "$B7"
if grep -q "no stuck condition detected" "$B7/run.out"; then
  pass "7a: a box that made progress an hour ago is left alone (no false escalation)"
else
  fail "7a: FALSE POSITIVE on a healthy box — got: $(grep -oE 'STUCK CLASS: [A-Z_]+' "$B7/run.out" | head -1)"
fi

# A closeout that is DONE must still self-remove and exit before any of this.
STATE_DONE="${STATE_GATES_OPEN/\"closeoutStatus\": \"pending\"/\"closeoutStatus\": \"done\"}"
B7B="$(_mkbox box7b "$STATE_DONE" present)"
_run "$B7B"
if grep -q "closeout complete; self-removing watchdog cron" "$B7B/run.out"; then
  pass "7b: a completed closeout still short-circuits to self-removal (lifecycle intact)"
else
  fail "7b: the lifecycle-complete self-removal path regressed"
fi
if grep -q "STUCK_RECOVERY_LANE_MISSING" "$B7B/run.out"; then
  fail "7c: the recovery-lane check fired on a COMPLETED box (it must exit before that)"
else
  pass "7c: no recovery-lane escalation on a completed box"
fi

# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if (( FAIL > 0 )); then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all closeout-watchdog-stuck-classes checks pass"
exit 0
