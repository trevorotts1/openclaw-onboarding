#!/usr/bin/env bash
# tests/unit/standard-first-cron-awareness.test.sh
#
# CI guard for AI WORKFORCE STANDARD-FIRST PHASE 5 (cron awareness,
# feat/aiwf-standard-first-2026-08-04). The standard prebuild driver
# (23-ai-workforce-blueprint/scripts/prebuild-standard-workforce.sh)
# materializes the canonical department floor BEFORE the interview and writes
# buildType=standard-first + standardPrebuild + departments[] status=prebuilt
# into .workforce-build-state.json. The two durable crons that drive a box
# after install must understand that state WITHOUT changing a single behavior
# for legacy boxes (buildType absent). This test runs BOTH crons against
# hermetic fixtures and asserts the contract:
#
#   (S1) PREBUILT_NO_STORM      -- a prebuilt box whose interview has not
#                                   started gets NO build self-ping on a cron
#                                   fire (no [WORKFORCE-RESUME] /
#                                   [LIBRARY-RESUME] / [CLOSEOUT-RESUME]);
#                                   the throttled operator report fires AT
#                                   MOST once (no storm across fires).
#   (S2) HOP1_NO_MISFIRE        -- the same fire must NOT promote the
#                                   interview: interviewComplete stays false
#                                   and the HOP-1 recovery path never runs
#                                   (the prebuild writes no lastQuestionAt,
#                                   so recovery cannot misfire on it).
#   (S3) SF_HOP4_CLOSEOUT       -- standard-first completion contract: all
#                                   non-prebuilt depts done + prebuilt depts
#                                   confirmed-or-declined (confirmationsComplete)
#                                   + libraries done + comms terminal => HOP-4
#                                   writes buildCompletedAt and the closeout
#                                   lane dispatches EXACTLY once. Prebuilt
#                                   slugs never appear in the dispatch.
#   (S4) SF_HOP4_GATED          -- same fixture with confirmationsComplete
#                                   MISSING => buildCompletedAt must NOT be
#                                   written and nothing dispatches (the
#                                   prebuilt depts were never reviewed).
#   (S5) PARTIAL_PREBUILD_LANE  -- a partial prebuild
#                                   (standardPrebuild.status=pending,
#                                   interview not complete) gets the
#                                   [STANDARD-PREBUILD-RESUME] dispatch with
#                                   an in-flight TTL marker: a second fire
#                                   inside the TTL does NOT dispatch again.
#   (S6) RESUME_AFTER_FLIP      -- interviewComplete flip + one pending custom
#                                   dept => EXACTLY ONE [WORKFORCE-RESUME]
#                                   dispatch, naming the pending dept and
#                                   NEVER the prebuilt ones.
#   (S7) LEGACY_UNTOUCHED       -- a legacy box (buildType absent) with a
#                                   pending dept still dispatches the normal
#                                   [WORKFORCE-RESUME]; the standard-first
#                                   lane never fires on it.
#   (S8) PREBUILT_NEVER_STALE   -- the disk-reality stale-state reset must
#                                   NOT demote a status=prebuilt department
#                                   to pending (a prebuilt dept is a
#                                   legitimate deliverable, not a stale
#                                   claim).
#   (N1) NUDGE_PREBUILT_NO_PROGRESS -- a prebuilt box with no interview
#                                   started gets NO nudge worker run and no
#                                   owner message (the prebuild does not
#                                   count as interview progress).
#   (N2) NUDGE_SF_COPY          -- a standard-first box with a stalled
#                                   interview runs the nudge worker with
#                                   WORKFORCE_NUDGE_COPY=review-prebuilt-company
#                                   ("Review your pre-built company" instead
#                                   of "Finish your interview").
#   (N3) NUDGE_LEGACY_COPY      -- a legacy box runs the worker with
#                                   WORKFORCE_NUDGE_COPY=default (unchanged).
#   (N4) NUDGE_ANCHOR           -- a standard-first box whose lastQuestionAt
#                                   is a pre-prebuild seeding artifact gets
#                                   its idle clock anchored to
#                                   standardReadyAt; a normal timestamp does
#                                   not.
#   (N5) NUDGE_KILL_UNCHANGED   -- the kill condition stays
#                                   interviewComplete==true on a
#                                   standard-first box.
#
# Each behavioral group is paired with a MUTATION PROOF where a discriminating
# assertion could otherwise pass vacuously: the same fixture run against a
# sandboxed copy of the script with ONLY the fix reverted must exhibit the OLD
# broken behavior.
#
# HERMETIC: every group sandboxes HOME (and OC_ROOT for the nudge cron) and
# runs a COPY of the script from inside the sandbox, so SCRIPT_DIR-resolved
# siblings resolve into the fixture and no real Skill-23 script, no real
# ~/.openclaw and no live client box is ever touched.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

RESUME="$REPO_ROOT/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
NUDGE="$REPO_ROOT/23-ai-workforce-blueprint/scripts/interview-nudge-cron.sh"
FAKE_OC="$REPO_ROOT/tests/fixtures/fake-openclaw-cron.py"

echo "=== standard-first-cron-awareness.test.sh ==="
echo ""

FUNCTIONAL=1
for _req in "$RESUME" "$NUDGE" "$FAKE_OC"; do
  if [[ ! -f "$_req" ]]; then
    echo "!! SKIPPED: $_req not found"
    FUNCTIONAL=0
  fi
done
if [[ -d /data/.openclaw ]]; then
  # resume-workforce-build.sh resolves OC_ROOT as /data/.openclaw FIRST and
  # offers no override; refuse to run rather than risk a real workspace.
  echo "!! SKIPPED: /data/.openclaw exists on this host — cannot guarantee fixture isolation"
  FUNCTIONAL=0
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "!! SKIPPED: python3 not installed"
  FUNCTIONAL=0
fi

# Python-based JSON value extractor — replaces jq for hermetic CI
# where jq may not be available. All assertion logic that previously
# piped through jq now routes through this single helper.
_pyjson() {
  # $1 = path to JSON file   $2 = Python expression (data = parsed dict)
  python3 -c "
import json, sys
with open('$1') as f:
    data = json.load(f)
v = $2
if v is None:
    pass
elif isinstance(v, bool):
    sys.stdout.write('true' if v else 'false')
else:
    sys.stdout.write(str(v))
"
}

if (( FUNCTIONAL == 1 )); then

set +e

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

RESUME_CRON_UUID="aabbccdd-1122-3344-5566-778899aabbcc"

# iso_ts <hours-ago> — ISO-8601 UTC timestamp N hours in the past.
iso_ts() {
  python3 -c "
from datetime import datetime, timezone, timedelta
dt = datetime.now(tz=timezone.utc) - timedelta(hours=$1)
print(dt.strftime('%Y-%m-%dT%H:%M:%SZ'))
"
}

# Build one hermetic box for the RESUME cron. Echoes the box HOME.
#   $1 = box name   $2 = build-state JSON   $3 = space-separated dept ids
#        needing a real how-to.md on disk (for the stale-state reset)
_mkbox() {
  local name="$1" state_json="$2" depts="${3:-}"
  local h="$SANDBOX/$name"
  local skill="$h/.openclaw/skills/23-ai-workforce-blueprint/scripts"
  mkdir -p "$skill" "$h/.openclaw/workspace" "$h/bin"

  cp "$RESUME" "$skill/resume-workforce-build.sh"
  cp "$REPO_ROOT/23-ai-workforce-blueprint/scripts/"{lib-workforce-state.sh,workforce_state.py,workforce_completion.py,interview_eligibility.py} "$skill/"
  cat > "$skill/department-floor.py" <<'PYEOF'
import sys
# Stub: department floor SATISFIED (rc=0).
sys.exit(0)
PYEOF

  cat > "$h/bin/openclaw" <<SHIM
#!/usr/bin/env bash
exec python3 "$FAKE_OC" "\$@"
SHIM
  chmod +x "$h/bin/openclaw"

  printf '%s' "$state_json" > "$h/.openclaw/workspace/.workforce-build-state.json"
  printf '[{"name":"workforce-build-resume","id":"%s","kind":"command"}]' "$RESUME_CRON_UUID" \
    > "$h/jobs.json"
  : > "$h/calls.log"

  local d
  for d in $depts; do
    mkdir -p "$h/.openclaw/workspace/departments/$d/lead"
    { echo "# how-to"; for _ in $(seq 1 12); do
        echo "Operating procedure line for the $d department role workspace."
      done; } > "$h/.openclaw/workspace/departments/$d/lead/how-to.md"
  done
  printf '%s' "$h"
}

# Completion scenarios model the post-interview runtime build, not just the
# prebuild inventory. Stage verifiers are explicit stubs; the shared evaluator
# still checks confirmations, identity, states and actual artifact digests.
_prepare_completion_box() {
  local h="$1" skill="$1/.openclaw/skills/23-ai-workforce-blueprint/scripts"
  for check in verify-wiring.sh qc-completeness.sh verify-library-gate.sh; do
    printf '#!/usr/bin/env bash\nexit 0\n' > "$skill/$check"
  done
  printf 'raise SystemExit(0)\n' > "$skill/post-build-role-workspaces.py"
  python3 - "$h" <<'PYPREPARE'
import json,sys
from pathlib import Path
home=Path(sys.argv[1]);path=home/'.openclaw/workspace/.workforce-build-state.json'
state=json.loads(path.read_text());root=home/'.openclaw/workspace/departments'
state.update(companySlug='fixture-company',companyId='fixture-company-id',buildId='fixture-build')
for dept in state['departments']:
    dept['status']='done'
    folder=root/dept['slug']/'lead';folder.mkdir(parents=True,exist_ok=True)
    (folder/'how-to.md').write_text('# Fixture operating procedure\n'+('Completed role operating procedure.\n'*30))
state['buildArtifactVerification']={'root':str(root)}
path.write_text(json.dumps(state))
PYPREPARE
}

# Run a box once. $1 = box home, $2 = script, rest = extra env assignments.
_runbox() {
  local h="$1" script="$2"; shift 2
  env -i \
    PATH="$h/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" \
    HOME="$h" \
    TMPDIR="${TMPDIR:-/tmp}" \
    FAKE_OC_JOBS_FILE="$h/jobs.json" \
    FAKE_OC_CALLS_FILE="$h/calls.log" \
    OPERATOR_ESCALATION_CHAT_ID="555000111" \
    "$@" \
    bash "$script" >"$h/run.out" 2>&1
  return 0
}

# Revert exactly one fix in a sandboxed copy. $1 = path, heredoc = python body.
_mutate() {
  local target="$1"; shift
  python3 - "$target" "$@"
}

# Count `message send` dispatches in a box's call log.
_send_count() {
  local c
  c=$(grep -c "^message send" "$1/calls.log" 2>/dev/null || true)
  case "$c" in ''|*[!0-9]*) c=0 ;; esac
  printf '%s' "$c"
}

NOW_ISO="$(iso_ts 0)"
READY_24H="$(iso_ts 24)"
READY_48H="$(iso_ts 48)"
LASTQ_25H="$(iso_ts 25)"

# ---------------------------------------------------------------------------
# (S1) PREBUILT_NO_STORM + (S2) HOP1_NO_MISFIRE
# ---------------------------------------------------------------------------
echo "--- (S1/S2) PREBUILT_NO_STORM: prebuilt + interview not started => no build self-ping, no promotion ---"
STATE_SF_PREBUILT_NOT_STARTED='{
  "buildType": "standard-first",
  "standardPrebuild": {
    "status": "done",
    "standardReadyAt": "'"${READY_24H}"'",
    "agentRegistration": "deferred",
    "prebuiltDepartments": ["marketing", "sales", "finance"]
  },
  "interviewComplete": false,
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator",
  "departments": [
    {"id": "marketing", "slug": "marketing", "status": "prebuilt"},
    {"id": "sales", "slug": "sales", "status": "prebuilt"},
    {"id": "finance", "slug": "finance", "status": "prebuilt"}
  ]
}'
BOXS1="$(_mkbox boxs1 "$STATE_SF_PREBUILT_NOT_STARTED")"
_runbox "$BOXS1" "$BOXS1/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
SLOG1="$BOXS1/.openclaw/workspace/.workforce-build-state.log"

if grep -E "^message send .*(WORKFORCE-RESUME|LIBRARY-RESUME|CLOSEOUT-RESUME|QC-RESUME|COMMS-AUTOMATION-RESUME|WIRING-RESUME|STANDARD-PREBUILD-RESUME)" "$BOXS1/calls.log" >/dev/null 2>&1; then
  fail "S1a: a build self-ping was dispatched for a prebuilt box whose interview has not started"
else
  pass "S1a: NO build self-ping dispatched (prebuilt is not pending-build)"
fi
# The throttled operator-facing INTERVIEW-GATE report is legitimate, but AT MOST
# once. A second fire must not re-send it (no storm).
_runbox "$BOXS1" "$BOXS1/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
_n_msgs=$(_send_count "$BOXS1")
if (( _n_msgs <= 1 )); then
  pass "S1b: after TWO cron fires there is at most one operator report (throttled, no storm; $_n_msgs send(s))"
else
  fail "S1b: $_n_msgs sends across two fires — the cron is storming"
fi
if [[ -f "$BOXS1/.openclaw/workspace/.workforce-build-state.lock" ]]; then
  fail "S1c: the lockfile survived the exit (would block the next fire for 10 minutes)"
else
  pass "S1c: lockfile cleaned up on exit"
fi
_ic_after=$(_pyjson "$BOXS1/.openclaw/workspace/.workforce-build-state.json" "data.get('interviewComplete', False)")
if [[ "$_ic_after" == "true" ]]; then
  fail "S2a: the cron PROMOTED interviewComplete on prebuild state alone — HOP-1 misfired on the prebuild"
else
  pass "S2a: interviewComplete still false — the prebuild was never read as interview content"
fi
if grep -q "^.*RECOVERY:" "$SLOG1" 2>/dev/null; then
  fail "S2b: the HOP-1 recovery path ran on a prebuilt-but-uninterviewed box"
else
  pass "S2b: HOP-1 recovery path did not run (no lastQuestionAt to recover from)"
fi
if grep -q "interview not started" "$SLOG1" 2>/dev/null; then
  pass "S2c: the not-started condition was logged (visibility)"
else
  fail "S2c: no not-started log line — the exit was silent"
fi

# ---------------------------------------------------------------------------
# (S3) SF_HOP4_CLOSEOUT — the standard-first completion contract closes
# ---------------------------------------------------------------------------
echo ""
echo "--- (S3) SF_HOP4_CLOSEOUT: prebuilt confirmed-or-declined + libraries + comms => HOP-4 + exactly one dispatch ---"
STATE_SF_SETTLED='{
  "buildType": "standard-first",
  "standardPrebuild": {
    "status": "done",
    "standardReadyAt": "'"${READY_48H}"'",
    "agentRegistration": "deferred",
    "prebuiltDepartments": [
      {"slug": "marketing"},
      {"slug": "sales", "decision": "decline", "provenance": "owner-confirmed-interview"}
    ]
  },
  "confirmationsComplete": true,
  "interviewComplete": true,
  "interviewQc": {"status": "pass"},
  "roleLibraryStatus": "done",
  "sopLibraryStatus": "done",
  "commsAutomationStatus": "not-applicable",
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator",
  "departments": [
    {"id": "marketing", "slug": "marketing", "status": "prebuilt"},
    {"id": "sales", "slug": "sales", "status": "prebuilt"},
    {"id": "ops-custom", "slug": "ops-custom", "status": "done"}
  ]
}'
BOXS3="$(_mkbox boxs3 "$STATE_SF_SETTLED" "ops-custom")"
_prepare_completion_box "$BOXS3"
_runbox "$BOXS3" "$BOXS3/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
SLOG3="$BOXS3/.openclaw/workspace/.workforce-build-state.log"

_bca=$(_pyjson "$BOXS3/.openclaw/workspace/.workforce-build-state.json" "data.get('buildCompletedAt') or ''")
if [[ -n "$_bca" ]]; then
  pass "S3a: HOP-4 wrote buildCompletedAt under the standard-first contract (runtime departments done with current verification and owner confirmations)"
else
  fail "S3a: buildCompletedAt NOT written — the standard-first completion contract did not close"
fi
if grep -q "AUTO-COMPLETE (HOP-4)" "$SLOG3" 2>/dev/null; then
  pass "S3b: the HOP-4 auto-complete was logged"
else
  fail "S3b: no AUTO-COMPLETE (HOP-4) log line"
fi
_n3=$(_send_count "$BOXS3")
if (( _n3 == 1 )); then
  pass "S3c: exactly ONE dispatch on the completing fire (no self-ping storm)"
else
  fail "S3c: expected exactly 1 dispatch, got $_n3"
fi
if grep -q "CLOSEOUT-RESUME" "$BOXS3/calls.log" 2>/dev/null; then
  pass "S3d: the single dispatch is the [CLOSEOUT-RESUME] lane (closeout now owns the box)"
else
  fail "S3d: the dispatch was not [CLOSEOUT-RESUME]"
fi
if grep -E "^message send" "$BOXS3/calls.log" 2>/dev/null | grep -E "marketing|sales" >/dev/null 2>&1; then
  fail "S3e: a prebuilt department slug leaked into the dispatch text"
else
  pass "S3e: no prebuilt department slug in the dispatch text"
fi

# ---------------------------------------------------------------------------
# (S4) SF_HOP4_GATED — missing confirmationsComplete must NOT close the build
# ---------------------------------------------------------------------------
echo ""
echo "--- (S4) SF_HOP4_GATED: confirmationsComplete absent => buildCompletedAt must NOT be written ---"
STATE_SF_UNSETTLED='{
  "buildType": "standard-first",
  "standardPrebuild": {
    "status": "done",
    "standardReadyAt": "'"${READY_48H}"'",
    "agentRegistration": "deferred",
    "prebuiltDepartments": [{"slug": "marketing"}, {"slug": "sales"}]
  },
  "interviewComplete": true,
  "interviewQc": {"status": "pass"},
  "roleLibraryStatus": "done",
  "sopLibraryStatus": "done",
  "commsAutomationStatus": "not-applicable",
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator",
  "departments": [
    {"id": "marketing", "slug": "marketing", "status": "prebuilt"},
    {"id": "sales", "slug": "sales", "status": "prebuilt"},
    {"id": "ops-custom", "slug": "ops-custom", "status": "done"}
  ]
}'
BOXS4="$(_mkbox boxs4 "$STATE_SF_UNSETTLED" "ops-custom")"
_prepare_completion_box "$BOXS4"
_runbox "$BOXS4" "$BOXS4/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
SLOG4="$BOXS4/.openclaw/workspace/.workforce-build-state.json"
_bca4=$(_pyjson "$SLOG4" "data.get('buildCompletedAt') or ''")
if [[ -z "$_bca4" ]]; then
  pass "S4a: buildCompletedAt NOT written while the prebuilt set is unreviewed (confirmationsComplete absent)"
else
  fail "S4a: buildCompletedAt was written WITHOUT confirmationsComplete — the closeout would race the interview review"
fi
_n4=$(_send_count "$BOXS4")
if (( _n4 == 0 )); then
  pass "S4b: nothing dispatched — an unsettled standard-first box is quiet, not pinged"
else
  fail "S4b: $_n4 dispatch(es) on a quiet unsettled box"
fi

echo ""
echo "--- (S4-MUT) MUTATION PROOF: without the confirmationsComplete conjunct HOP-4 closes prematurely ---"
BOXS4M="$(_mkbox boxs4m "$STATE_SF_UNSETTLED" "ops-custom")"
_prepare_completion_box "$BOXS4M"
MUTS4="$BOXS4M/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
_mutate "$MUTS4" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
old = " && (( _sf_depts_settled == 1 ))"
if old not in src:
    sys.exit(1)
# Reproduce the old omission in both the dispatch guard and shared evaluator.
open(path, "w").write(src.replace(old, ""))
from pathlib import Path
completion=Path(path).parent/'workforce_completion.py'
evaluator=completion.read_text()
conjunct="    if state.get('buildType')=='standard-first' and state.get('confirmationsComplete') is not True:missing.append('confirmations')"
assert conjunct in evaluator
completion.write_text(evaluator.replace(conjunct,'',1))
PYEOF
muts4_rc=$?
if (( muts4_rc != 0 )); then
  fail "S4-MUT: could not revert the confirmationsComplete conjunct — cannot prove S4a discriminates"
else
  _runbox "$BOXS4M" "$MUTS4"
  _bca4m=$(_pyjson "$BOXS4M/.openclaw/workspace/.workforce-build-state.json" "data.get('buildCompletedAt') or ''")
  if [[ -n "$_bca4m" ]]; then
    pass "S4-MUT: the mutated script DOES write buildCompletedAt prematurely — S4a is a real, non-vacuous check"
  else
    fail "S4-MUT: the mutated script still withheld buildCompletedAt — S4a proves nothing"
  fi
fi

# ---------------------------------------------------------------------------
# (S5) PARTIAL_PREBUILD_LANE
# ---------------------------------------------------------------------------
echo ""
echo "--- (S5) PARTIAL_PREBUILD_LANE: a partial prebuild gets ONE [STANDARD-PREBUILD-RESUME], TTL-guarded ---"
STATE_SF_PARTIAL='{
  "buildType": "standard-first",
  "standardPrebuild": {
    "status": "pending",
    "agentRegistration": "deferred",
    "prebuiltDepartments": ["marketing", "sales", "finance"]
  },
  "interviewComplete": false,
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator",
  "departments": [
    {"id": "marketing", "slug": "marketing", "status": "prebuilt"},
    {"id": "sales", "slug": "sales", "status": "pending"},
    {"id": "finance", "slug": "finance", "status": "pending"}
  ]
}'
BOXS5="$(_mkbox boxs5 "$STATE_SF_PARTIAL")"
_runbox "$BOXS5" "$BOXS5/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
SLOG5="$BOXS5/.openclaw/workspace/.workforce-build-state.log"

if grep -q "STANDARD-PREBUILD-RESUME" "$BOXS5/calls.log" 2>/dev/null; then
  pass "S5a: the [STANDARD-PREBUILD-RESUME] lane dispatched for the partial prebuild"
else
  fail "S5a: NO [STANDARD-PREBUILD-RESUME] dispatch — the partial prebuild would sit forever"
fi
if grep -E "^message send .*-t 111222333" "$BOXS5/calls.log" >/dev/null 2>&1; then
  fail "S5b: the prebuild resume went to the OWNER chat (internal traffic leak)"
else
  pass "S5b: the prebuild resume stayed internal (operator chat only)"
fi
if [[ -f "$BOXS5/.openclaw/workspace/.standard-prebuild-resume.inflight" ]]; then
  pass "S5c: the in-flight marker was set (overlap guard armed)"
else
  fail "S5c: no in-flight marker — overlapping prebuild re-runs are unguarded"
fi
_n5a=$(_send_count "$BOXS5")
_runbox "$BOXS5" "$BOXS5/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
_n5b=$(_send_count "$BOXS5")
if (( _n5b == _n5a )); then
  pass "S5d: a second fire inside the TTL dispatched NOTHING (no overlap storm)"
else
  fail "S5d: second fire dispatched again ($_n5a -> $_n5b) — the TTL guard failed"
fi
if grep -q "STANDARD-PREBUILD-RESUME: in-flight marker" "$SLOG5" 2>/dev/null; then
  pass "S5e: the TTL skip was logged"
else
  fail "S5e: the TTL skip went unlogged"
fi

echo ""
echo "--- (S5-MUT) MUTATION PROOF: without the TTL guard a second fire stacks a second re-run ---"
BOXS5M="$(_mkbox boxs5m "$STATE_SF_PARTIAL")"
MUTS5="$BOXS5M/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
_mutate "$MUTS5" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
old = "        _pb_dispatch_ok=0\n"
if old not in src:
    sys.exit(1)
open(path, "w").write(src.replace(old, "          : # MUTATED: TTL gate disabled\n", 1))
PYEOF
muts5_rc=$?
if (( muts5_rc != 0 )); then
  fail "S5-MUT: could not disable the TTL guard — cannot prove S5d discriminates"
else
  _runbox "$BOXS5M" "$MUTS5"
  _m1=$(_send_count "$BOXS5M")
  _runbox "$BOXS5M" "$MUTS5"
  _m2=$(_send_count "$BOXS5M")
  if (( _m2 > _m1 )); then
    pass "S5-MUT: the mutated script dispatches on EVERY fire — S5d is a real, non-vacuous check"
  else
    fail "S5-MUT: the mutated script did not re-dispatch — S5d proves nothing"
  fi
fi

echo ""
echo "--- (S5-PARK) a PARKED box never gets the prebuild resume ---"
BOXS5P="$(_mkbox boxs5p "$STATE_SF_PARTIAL")"
mkdir -p "$BOXS5P/.openclaw/workspace/.park"
echo "PARKED test" > "$BOXS5P/.openclaw/workspace/.park/workforce-build.parked"
_runbox "$BOXS5P" "$BOXS5P/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
if grep -q "STANDARD-PREBUILD-RESUME" "$BOXS5P/calls.log" 2>/dev/null; then
  fail "S5-PARK: a PARKED box dispatched the prebuild resume — park must win over every lane"
else
  pass "S5-PARK: PARKED box dispatched nothing (park gate precedes the prebuild lane)"
fi

# ---------------------------------------------------------------------------
# (S6) RESUME_AFTER_FLIP — interviewComplete flip => exactly one WORKFORCE-RESUME
# ---------------------------------------------------------------------------
echo ""
echo "--- (S6) RESUME_AFTER_FLIP: completed interview + pending custom dept => exactly one [WORKFORCE-RESUME] ---"
STATE_SF_FLIPPED='{
  "buildType": "standard-first",
  "standardPrebuild": {
    "status": "done",
    "standardReadyAt": "'"${READY_48H}"'",
    "agentRegistration": "deferred",
    "prebuiltDepartments": [{"slug": "marketing"}, {"slug": "sales"}]
  },
  "interviewComplete": true,
  "interviewQc": {"status": "pass"},
  "roleLibraryStatus": "pending",
  "sopLibraryStatus": "pending",
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator",
  "departments": [
    {"id": "marketing", "slug": "marketing", "status": "prebuilt"},
    {"id": "sales", "slug": "sales", "status": "prebuilt"},
    {"id": "legal-custom", "slug": "legal-custom", "status": "pending"}
  ]
}'
BOXS6="$(_mkbox boxs6 "$STATE_SF_FLIPPED")"
_runbox "$BOXS6" "$BOXS6/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
_n6=$(_send_count "$BOXS6")
if (( _n6 == 1 )); then
  pass "S6a: exactly ONE dispatch after the interviewComplete flip"
else
  fail "S6a: expected exactly 1 dispatch, got $_n6"
fi
if grep -q "WORKFORCE-RESUME" "$BOXS6/calls.log" 2>/dev/null; then
  pass "S6b: the dispatch is a [WORKFORCE-RESUME] build resume"
else
  fail "S6b: no [WORKFORCE-RESUME] dispatch after the flip"
fi
if grep -E "^message send" "$BOXS6/calls.log" 2>/dev/null | grep -q "legal-custom"; then
  pass "S6c: the dispatch names the pending custom department"
else
  fail "S6c: the pending custom department was not named in the dispatch"
fi
if grep -E "^message send" "$BOXS6/calls.log" 2>/dev/null | grep -E "Pending: [^.]*(marketing|sales)" >/dev/null 2>&1; then
  fail "S6d: prebuilt departments were listed as pending in the resume message"
else
  pass "S6d: prebuilt departments are NOT listed as pending (they are not pending-build)"
fi

# ---------------------------------------------------------------------------
# (S7) LEGACY_UNTOUCHED
# ---------------------------------------------------------------------------
echo ""
echo "--- (S7) LEGACY_UNTOUCHED: a legacy box still gets the normal lane, never the standard-first lane ---"
STATE_LEGACY='{
  "interviewComplete": true,
  "interviewQc": {"status": "pass"},
  "roleLibraryStatus": "pending",
  "sopLibraryStatus": "pending",
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator",
  "departments": [
    {"id": "alpha", "slug": "alpha", "status": "done"},
    {"id": "bravo", "slug": "bravo", "status": "pending"}
  ]
}'
BOXS7="$(_mkbox boxs7 "$STATE_LEGACY" "alpha")"
_runbox "$BOXS7" "$BOXS7/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
if grep -q "WORKFORCE-RESUME" "$BOXS7/calls.log" 2>/dev/null; then
  pass "S7a: legacy box still dispatches the normal [WORKFORCE-RESUME] lane"
else
  fail "S7a: legacy box got no resume dispatch — the legacy lane changed"
fi
if grep -q "STANDARD-PREBUILD-RESUME" "$BOXS7/calls.log" 2>/dev/null; then
  fail "S7b: the standard-first prebuild lane fired on a legacy box (buildType absent)"
else
  pass "S7b: the standard-first lane never fires on a legacy box"
fi

# ---------------------------------------------------------------------------
# (S8) PREBUILT_NEVER_STALE — the stale-state reset must skip prebuilt depts
# ---------------------------------------------------------------------------
echo ""
echo "--- (S8) PREBUILT_NEVER_STALE: the disk-reality reset must not demote a prebuilt dept ---"
# prebuilt dept carries roleLibraryFilled=true but has NO how-to on disk; the
# stale-check audits only done/library-filled claims and must still skip it.
STATE_SF_STALETRAP='{
  "buildType": "standard-first",
  "standardPrebuild": {
    "status": "done",
    "standardReadyAt": "'"${READY_48H}"'",
    "agentRegistration": "deferred",
    "prebuiltDepartments": [{"slug": "marketing"}]
  },
  "interviewComplete": true,
  "interviewQc": {"status": "pass"},
  "roleLibraryStatus": "pending",
  "sopLibraryStatus": "pending",
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator",
  "departments": [
    {"id": "marketing", "slug": "marketing", "status": "prebuilt", "roleLibraryFilled": true},
    {"id": "ops-custom", "slug": "ops-custom", "status": "done"}
  ]
}'
BOXS8="$(_mkbox boxs8 "$STATE_SF_STALETRAP" "ops-custom")"
_runbox "$BOXS8" "$BOXS8/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
SLOG8="$BOXS8/.openclaw/workspace/.workforce-build-state.log"
_status8=$(_pyjson "$BOXS8/.openclaw/workspace/.workforce-build-state.json" "next((d['status'] for d in data.get('departments',[]) if d.get('id')=='marketing'), '')")
if [[ "$_status8" == "prebuilt" ]]; then
  pass "S8a: the prebuilt department survived the stale-state reset at status=prebuilt"
else
  fail "S8a: the prebuilt department was demoted to '$_status8' — it would now be counted as pending-build"
fi
if grep -q "STALE_RESET: dept 'marketing'" "$SLOG8" 2>/dev/null; then
  fail "S8b: the stale-check reset the prebuilt department"
else
  pass "S8b: no STALE_RESET against the prebuilt department"
fi

echo ""
echo "--- (S8-MUT) MUTATION PROOF: without the prebuilt skip, the reset demotes it ---"
BOXS8M="$(_mkbox boxs8m "$STATE_SF_STALETRAP" "ops-custom")"
MUTS8="$BOXS8M/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
_mutate "$MUTS8" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
old = '    if status == "prebuilt":\n        continue\n'
if old not in src:
    sys.exit(1)
open(path, "w").write(src.replace(old, "", 1))
PYEOF
muts8_rc=$?
if (( muts8_rc != 0 )); then
  fail "S8-MUT: could not remove the prebuilt skip — cannot prove S8a discriminates"
else
  _runbox "$BOXS8M" "$MUTS8"
  _status8m=$(_pyjson "$BOXS8M/.openclaw/workspace/.workforce-build-state.json" "next((d['status'] for d in data.get('departments',[]) if d.get('id')=='marketing'), '')")
  if [[ "$_status8m" == "pending" ]]; then
    pass "S8-MUT: without the skip the prebuilt dept IS demoted to pending — S8a is a real, non-vacuous check"
  else
    fail "S8-MUT: the mutated script kept the prebuilt status — S8a proves nothing"
  fi
fi

# ===========================================================================
# NUDGE CRON GROUPS — run a COPY of interview-nudge-cron.sh in a sandbox repo
# layout so its SCRIPT_DIR/REPO_ROOT resolution lands inside the fixture.
# ===========================================================================

# Build a hermetic box for the NUDGE cron. Echoes the box OC_ROOT.
#   $1 = box name   $2 = build-state JSON
_mkbox_nudge() {
  local name="$1" state_json="$2"
  local repo="$SANDBOX/$name/repo"
  local skill="$repo/23-ai-workforce-blueprint/scripts"
  local oc="$SANDBOX/$name/oc"
  mkdir -p "$skill" "$repo/shared-utils" "$oc/workspace" "$SANDBOX/$name/bin"

  cp "$NUDGE" "$skill/interview-nudge-cron.sh"
  # Stub worker: records the WORKFORCE_NUDGE_COPY env it was invoked with.
  cat > "$repo/shared-utils/nudge-incomplete-interviews.py" <<PYEOF
import os, sys
line = "WORKER-CALLED WORKFORCE_NUDGE_COPY=%s\n" % os.environ.get("WORKFORCE_NUDGE_COPY", "<unset>")
with open(os.path.join("$oc", "worker.log"), "a") as fh:
    fh.write(line)
sys.exit(0)
PYEOF

  cat > "$SANDBOX/$name/bin/openclaw" <<SHIM
#!/usr/bin/env bash
exec python3 "$FAKE_OC" "\$@"
SHIM
  chmod +x "$SANDBOX/$name/bin/openclaw"

  printf '%s' "$state_json" > "$oc/workspace/.workforce-build-state.json"
  printf '[{"name":"interview-nudge","id":"%s","kind":"command"}]' "$RESUME_CRON_UUID" \
    > "$SANDBOX/$name/jobs.json"
  : > "$SANDBOX/$name/calls.log"
  printf '%s' "$oc"
}

# Run the nudge cron once for a box. $1 = box name, $2 = state JSON (rebuilds).
_run_nudge() {
  local name="$1"
  local root="$SANDBOX/$name"
  env -i \
    PATH="$root/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" \
    HOME="$root" \
    TMPDIR="${TMPDIR:-/tmp}" \
    OC_ROOT="$root/oc" \
    FAKE_OC_JOBS_FILE="$root/jobs.json" \
    FAKE_OC_CALLS_FILE="$root/calls.log" \
    bash "$root/repo/23-ai-workforce-blueprint/scripts/interview-nudge-cron.sh" \
    >"$root/run.out" 2>&1
  return 0
}

# ---------------------------------------------------------------------------
# (N1) NUDGE_PREBUILT_NO_PROGRESS
# ---------------------------------------------------------------------------
echo ""
echo "--- (N1) NUDGE_PREBUILT_NO_PROGRESS: prebuilt + interview not started => no worker, no owner message ---"
STATE_N1='{
  "buildType": "standard-first",
  "standardPrebuild": {"status": "done", "standardReadyAt": "'"${READY_24H}"'"},
  "interviewComplete": false,
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator"
}'
OCN1="$(_mkbox_nudge boxn1 "$STATE_N1")"
_run_nudge boxn1
NLOG1="$OCN1/workspace/.interview-nudge.log"
if [[ -f "$OCN1/worker.log" ]]; then
  fail "N1a: the nudge worker ran for a prebuilt box with no interview started (prebuild counted as progress)"
else
  pass "N1a: no nudge worker run — the prebuild does not count as interview progress"
fi
if grep -E "^message send" "$SANDBOX/boxn1/calls.log" >/dev/null 2>&1; then
  fail "N1b: an owner-facing nudge was sent before the interview even started"
else
  pass "N1b: no owner message sent"
fi
if grep -q "owner has not started the interview" "$NLOG1" 2>/dev/null; then
  pass "N1c: the standard-first not-started condition was logged explicitly (visibility)"
else
  fail "N1c: no standard-first not-started log line"
fi

# ---------------------------------------------------------------------------
# (N2) NUDGE_SF_COPY — stalled standard-first interview gets the review copy
# ---------------------------------------------------------------------------
echo ""
echo "--- (N2) NUDGE_SF_COPY: stalled standard-first interview => WORKFORCE_NUDGE_COPY=review-prebuilt-company ---"
STATE_N2='{
  "buildType": "standard-first",
  "standardPrebuild": {"status": "done", "standardReadyAt": "'"${READY_48H}"'"},
  "interviewComplete": false,
  "interviewProgress": {"lastQuestionAt": "'"${LASTQ_25H}"'", "lastQuestionNumber": 4, "lastQuestionPhase": "phase1"},
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator"
}'
OCN2="$(_mkbox_nudge boxn2 "$STATE_N2")"
_run_nudge boxn2
if [[ -f "$OCN2/worker.log" ]] && grep -q "WORKFORCE_NUDGE_COPY=review-prebuilt-company" "$OCN2/worker.log"; then
  pass "N2a: the worker ran with WORKFORCE_NUDGE_COPY=review-prebuilt-company (review your pre-built company)"
else
  fail "N2a: the worker did not receive the standard-first nudge copy ($(cat "$OCN2/worker.log" 2>/dev/null || echo 'worker never ran'))"
fi
if grep -q "WORKFORCE_NUDGE_COPY=review-prebuilt-company" "$OCN2/workspace/.interview-nudge.log" 2>/dev/null; then
  pass "N2b: the copy switch was logged"
else
  fail "N2b: the copy switch went unlogged"
fi

echo ""
echo "--- (N2-MUT) MUTATION PROOF: without the standard-first assignment the worker gets only the legacy copy ---"
OCN2M="$(_mkbox_nudge boxn2m "$STATE_N2")"
MUTN2="$SANDBOX/boxn2m/repo/23-ai-workforce-blueprint/scripts/interview-nudge-cron.sh"
_mutate "$MUTN2" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
old = '  WORKFORCE_NUDGE_COPY="review-prebuilt-company"\n'
if old not in src:
    sys.exit(1)
open(path, "w").write(src.replace(old, "  : # MUTATED: standard-first copy not set\n", 1))
PYEOF
mutn2_rc=$?
if (( mutn2_rc != 0 )); then
  fail "N2-MUT: could not remove the standard-first copy assignment — cannot prove N2a discriminates"
else
  _run_nudge boxn2m
  if [[ -f "$OCN2M/worker.log" ]] && grep -q "WORKFORCE_NUDGE_COPY=default" "$OCN2M/worker.log"; then
    pass "N2-MUT: the mutated script passes only the legacy default copy — N2a is a real, non-vacuous check"
  else
    fail "N2-MUT: the mutated script still passed the standard-first copy — N2a proves nothing"
  fi
fi

# ---------------------------------------------------------------------------
# (N3) NUDGE_LEGACY_COPY — a legacy box keeps the default copy
# ---------------------------------------------------------------------------
echo ""
echo "--- (N3) NUDGE_LEGACY_COPY: legacy box => WORKFORCE_NUDGE_COPY=default ---"
STATE_N3='{
  "interviewComplete": false,
  "interviewProgress": {"lastQuestionAt": "'"${LASTQ_25H}"'", "lastQuestionNumber": 4, "lastQuestionPhase": "phase1"},
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator"
}'
OCN3="$(_mkbox_nudge boxn3 "$STATE_N3")"
_run_nudge boxn3
if [[ -f "$OCN3/worker.log" ]] && grep -q "WORKFORCE_NUDGE_COPY=default" "$OCN3/worker.log"; then
  pass "N3a: legacy box ran the worker with the default copy (byte-identical nudge behavior)"
else
  fail "N3a: legacy box did not get the default copy ($(cat "$OCN3/worker.log" 2>/dev/null || echo 'worker never ran'))"
fi
if grep -q "standard-first" "$OCN3/workspace/.interview-nudge.log" 2>/dev/null; then
  fail "N3b: standard-first code paths logged on a legacy box"
else
  pass "N3b: no standard-first log lines on a legacy box"
fi

# ---------------------------------------------------------------------------
# (N4) NUDGE_ANCHOR — seeding-artifact lastQuestionAt anchored to standardReadyAt
# ---------------------------------------------------------------------------
echo ""
echo "--- (N4) NUDGE_ANCHOR: an implausibly old lastQuestionAt is anchored to standardReadyAt ---"
STATE_N4='{
  "buildType": "standard-first",
  "standardPrebuild": {"status": "done", "standardReadyAt": "'"${LASTQ_25H}"'"},
  "interviewComplete": false,
  "interviewProgress": {"lastQuestionAt": "2020-01-01T00:00:00Z", "lastQuestionNumber": 4, "lastQuestionPhase": "phase1"},
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator"
}'
OCN4="$(_mkbox_nudge boxn4 "$STATE_N4")"
_run_nudge boxn4
if grep -q "anchoring the nudge idle clock to standardReadyAt" "$OCN4/workspace/.interview-nudge.log" 2>/dev/null; then
  pass "N4a: the seeding-artifact timestamp was re-anchored to standardReadyAt"
else
  fail "N4a: the artifact timestamp was not re-anchored"
fi
if [[ -f "$OCN4/worker.log" ]]; then
  pass "N4b: the worker still ran after re-anchoring (idle measured from the prebuild ready-time)"
else
  fail "N4b: the worker did not run after re-anchoring"
fi

STATE_N4B='{
  "buildType": "standard-first",
  "standardPrebuild": {"status": "done", "standardReadyAt": "'"${READY_48H}"'"},
  "interviewComplete": false,
  "interviewProgress": {"lastQuestionAt": "'"${LASTQ_25H}"'", "lastQuestionNumber": 4, "lastQuestionPhase": "phase1"},
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator"
}'
OCN4B="$(_mkbox_nudge boxn4b "$STATE_N4B")"
_run_nudge boxn4b
if grep -q "anchoring the nudge idle clock to standardReadyAt" "$OCN4B/workspace/.interview-nudge.log" 2>/dev/null; then
  fail "N4c: a NORMAL lastQuestionAt (newer than the prebuild) was re-anchored — real idle time would be corrupted"
else
  pass "N4c: a normal lastQuestionAt was left untouched (anchoring only engages on artifacts)"
fi

# ---------------------------------------------------------------------------
# (N5) NUDGE_KILL_UNCHANGED — interviewComplete==true still kills the cron
# ---------------------------------------------------------------------------
echo ""
echo "--- (N5) NUDGE_KILL_UNCHANGED: interviewComplete=true on a standard-first box still self-removes ---"
STATE_N5='{
  "buildType": "standard-first",
  "standardPrebuild": {"status": "done", "standardReadyAt": "'"${READY_48H}"'"},
  "interviewComplete": true,
  "interviewNudgeUuid": "'"${RESUME_CRON_UUID}"'",
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator"
}'
OCN5="$(_mkbox_nudge boxn5 "$STATE_N5")"
_run_nudge boxn5
if grep -q "interviewComplete=true - interview done, no nudge needed" "$OCN5/workspace/.interview-nudge.log" 2>/dev/null; then
  pass "N5a: the kill condition fired on interviewComplete==true (unchanged under standard-first)"
else
  fail "N5a: the kill condition did not fire"
fi
if grep -q "^cron rm" "$SANDBOX/boxn5/calls.log" 2>/dev/null; then
  pass "N5b: the nudge cron self-removed"
else
  fail "N5b: the nudge cron did not self-remove"
fi
if [[ -f "$OCN5/worker.log" ]]; then
  fail "N5c: the worker ran on a completed interview"
else
  pass "N5c: no nudge sent on a completed interview"
fi

fi  # FUNCTIONAL

# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if (( FAIL > 0 )); then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all standard-first cron awareness checks pass"
exit 0
