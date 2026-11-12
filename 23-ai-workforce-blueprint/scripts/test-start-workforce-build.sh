#!/usr/bin/env bash
# test-start-workforce-build.sh
#
# Acceptance test for BU-21 (finishing the interview starts the build).
# Self-contained: every fixture lives under a temp folder on the drive, runs
# under its own HOME with an explicit --state, and writes nothing outside.
#
# Cases (from 01-BUILD-SPEC.md BU-21):
#   (a) standard-first fixture, complete and eligible -> the stub build runs and
#       its recorded arguments contain --apply-standard-edits; a second call
#       inside 20 minutes prints already-running and starts nothing.
#   (b) legacy fixture with departments: [] -> .workforce-build-wanted.json
#       exists and no process is started.
#   (c) interviewComplete false -> exit 3.
#   (d) a stub openclaw on PATH that records its arguments is never called with
#       "message send" by update-interview-state.sh --complete.
#   (e) resume-workforce-build.sh run against fixture (a) with the in-flight
#       marker removed calls the start script (the build marker is written
#       again) instead of logging "nothing to do".
#
# The gate-side programs are stubbed ON PURPOSE: this test exercises the start
# path (who starts what, and what is recorded), not answers_to_config.py or
# build-workforce.py, which own their own acceptance tests. The stub
# build-workforce.py appends its argv to $SWB_TEST_MARKER, one line per run, so
# "started nothing" is countable rather than inferred.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START="$HERE/start-workforce-build.py"
RESUME="$HERE/resume-workforce-build.sh"
UPD="$HERE/update-interview-state.sh"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; [ -n "${2:-}" ] && echo "        $2"; FAIL=$((FAIL + 1)); }

echo "=== test-start-workforce-build.sh ==="
echo ""

FUNCTIONAL=1
for _req in "$START" "$RESUME" "$UPD" \
            "$HERE/lib-workforce-state.sh" "$HERE/lib-interview-rate-limit.sh" \
            "$HERE/workforce_state.py" "$HERE/workforce_completion.py" \
            "$HERE/interview_eligibility.py"; do
  if [[ ! -f "$_req" ]]; then
    echo "!! SKIPPED: $_req not found"
    FUNCTIONAL=0
  fi
done
if [[ -d /data/.openclaw ]]; then
  # resume-workforce-build.sh resolves OC_ROOT as /data/.openclaw FIRST and
  # offers no override; refuse to run rather than risk a real workspace.
  echo "!! SKIPPED: /data/.openclaw exists on this host - cannot guarantee fixture isolation"
  FUNCTIONAL=0
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "!! SKIPPED: python3 not installed"
  FUNCTIONAL=0
fi
if ! command -v jq >/dev/null 2>&1; then
  # resume-workforce-build.sh exits early without jq (case e cannot run).
  echo "!! SKIPPED: jq not installed"
  FUNCTIONAL=0
fi

if (( FUNCTIONAL == 1 )); then

WORK="$(mktemp -d "${TMPDIR:-/tmp}/swb-bu21.XXXXXX")"
trap 'rm -rf "$WORK" 2>/dev/null || true' EXIT
case "$WORK" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox resolved into a real .openclaw ($WORK)"; exit 2 ;;
esac

# Build one hermetic box. Echoes the box HOME.
#   $1 = box name   $2 = build-state JSON
_mkbox() {
  local name="$1" state_json="$2"
  local h="$WORK/$name"
  local skill="$h/.openclaw/skills/23-ai-workforce-blueprint/scripts"
  mkdir -p "$skill" "$h/.openclaw/workspace" "$h/bin"

  cp "$START" "$skill/start-workforce-build.py"
  cp "$RESUME" "$skill/resume-workforce-build.sh"
  cp "$UPD" "$skill/update-interview-state.sh"
  cp "$HERE/lib-workforce-state.sh" "$HERE/lib-interview-rate-limit.sh" \
     "$HERE/workforce_state.py" "$HERE/workforce_completion.py" \
     "$HERE/interview_eligibility.py" "$skill/"
  printf 'import sys\nsys.exit(0)\n' > "$skill/department-floor.py"

  # Config stub: the gate side is BU-29's acceptance test, not this one.
  cat > "$skill/answers_to_config.py" <<'PYEOF'
import pathlib, sys
out = sys.argv[sys.argv.index("--out") + 1]
pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
pathlib.Path(out).write_text("{}\n", encoding="utf-8")
sys.exit(0)
PYEOF

  # Build stub: one line per run, the exact arguments it was started with.
  cat > "$skill/build-workforce.py" <<'PYEOF'
import os, sys
marker = os.environ.get("SWB_TEST_MARKER", "")
if marker:
    with open(marker, "a", encoding="utf-8") as fh:
        fh.write(" ".join(sys.argv[1:]) + "\n")
sys.exit(0)
PYEOF

  # QC stub for the legacy completion path used by case (d).
  cat > "$skill/qc-interview-completion.py" <<'PYEOF'
import json, sys
path = sys.argv[sys.argv.index("--state") + 1]
with open(path) as fh:
    data = json.load(fh)
data.setdefault("interviewQc", {})["status"] = "pass"
with open(path, "w") as fh:
    json.dump(data, fh, indent=2)
sys.exit(0)
PYEOF

  # openclaw recorder: every call, verbatim, into $SWB_TEST_CALLS.
  cat > "$h/bin/openclaw" <<'SHEOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${SWB_TEST_CALLS:-/dev/null}"
exit 0
SHEOF
  chmod +x "$h/bin/openclaw"

  printf '%s' "$state_json" > "$h/.openclaw/workspace/.workforce-build-state.json"
  printf '%s' "$h"
}

# Run a box. $1 = box home, $2 = interpreter ("start"|"bash"), $3 = script,
# rest = the script's own arguments.
_run() {
  local h="$1" kind="$2" script="$3"; shift 3
  local -a cmd
  if [[ "$kind" == "start" ]]; then
    cmd=(python3 -B "$script")
  else
    cmd=(bash "$script")
  fi
  env -i \
    PATH="$h/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" \
    HOME="$h" \
    TMPDIR="${TMPDIR:-/tmp}" \
    PYTHONDONTWRITEBYTECODE=1 \
    SWB_TEST_MARKER="$h/build-marker.txt" \
    SWB_TEST_CALLS="$h/openclaw-calls.log" \
    "${cmd[@]}" "$@"
}

STATE_SF_ELIGIBLE='{
  "companySlug": "fixture-company",
  "companyId": "fixture-company-id",
  "buildId": "fixture-build",
  "buildType": "standard-first",
  "standardPrebuild": {"status": "done", "prebuiltDepartments": ["marketing"]},
  "interviewComplete": true,
  "interviewQc": {"status": "pass"},
  "departments": [{"id": "marketing", "slug": "marketing", "status": "prebuilt"}]
}'
STATE_LEGACY_EMPTY='{
  "companySlug": "fixture-company",
  "companyId": "fixture-company-id",
  "buildId": "fixture-build",
  "interviewComplete": true,
  "interviewQc": {"status": "pass"},
  "departments": []
}'
STATE_NOT_COMPLETE='{
  "companySlug": "fixture-company",
  "interviewComplete": false,
  "departments": []
}'
STATE_COMPLETE_PENDING_DEPT='{
  "companySlug": "fixture-company",
  "companyId": "fixture-company-id",
  "interviewComplete": false,
  "closeoutStatus": "pending",
  "departments": [{"id": "alpha", "slug": "alpha", "status": "pending"}]
}'

# ---------------------------------------------------------------------------
# (a) standard-first, complete and eligible -> the apply build starts once
# ---------------------------------------------------------------------------
echo "--- (a) standard-first eligible -> apply-started; a second call starts nothing ---"
BOXA="$(_mkbox boxa "$STATE_SF_ELIGIBLE")"
SKILLA="$BOXA/.openclaw/skills/23-ai-workforce-blueprint/scripts"
STATEA="$BOXA/.openclaw/workspace/.workforce-build-state.json"
OUTA="$(_run "$BOXA" start "$SKILLA/start-workforce-build.py" --state "$STATEA" 2>"$BOXA/start.err")"
RCA=$?

_i=0
while (( _i < 50 )); do
  [[ -s "$BOXA/build-marker.txt" ]] && break
  _i=$((_i + 1))
  sleep 0.1
done

if [[ -s "$BOXA/build-marker.txt" ]]; then
  pass "(a1) the detached build ran within 5 seconds"
else
  fail "(a1) no build started within 5 seconds" "$(cat "$BOXA/start.err" 2>/dev/null | tail -3)"
fi
if grep -q -- "--apply-standard-edits" "$BOXA/build-marker.txt" 2>/dev/null; then
  pass "(a2) the build was started with --apply-standard-edits"
else
  fail "(a2) the recorded build arguments do not contain --apply-standard-edits" \
    "$(cat "$BOXA/build-marker.txt" 2>/dev/null)"
fi
case "$OUTA" in
  *'"action":"apply-started"'*) pass "(a3) the start script printed apply-started" ;;
  *) fail "(a3) expected {\"action\":\"apply-started\",\"pid\":N}" "got: $OUTA (rc=$RCA)" ;;
esac
if [[ -f "$BOXA/.openclaw/workspace/.workforce-build-start.json" ]]; then
  pass "(a4) .workforce-build-start.json was written"
else
  fail "(a4) .workforce-build-start.json missing"
fi

OUTA2="$(_run "$BOXA" start "$SKILLA/start-workforce-build.py" --state "$STATEA" 2>"$BOXA/start2.err")"
case "$OUTA2" in
  *'"action":"already-running"'*) pass "(a5) a second call inside 20 minutes reports already-running" ;;
  *) fail "(a5) expected already-running" "got: $OUTA2" ;;
esac
LINESA=$(wc -l < "$BOXA/build-marker.txt" 2>/dev/null | tr -d ' ')
if [[ "$LINESA" == "1" ]]; then
  pass "(a6) the second call started nothing (one build run recorded)"
else
  fail "(a6) expected 1 build run, got ${LINESA:-0}"
fi

# ---------------------------------------------------------------------------
# (b) legacy fixture with no departments -> the wanted record, no process
# ---------------------------------------------------------------------------
echo ""
echo "--- (b) legacy fixture with departments: [] -> agent-turn-wanted, nothing started ---"
BOXB="$(_mkbox boxb "$STATE_LEGACY_EMPTY")"
SKILLB="$BOXB/.openclaw/skills/23-ai-workforce-blueprint/scripts"
STATEB="$BOXB/.openclaw/workspace/.workforce-build-state.json"
OUTB="$(_run "$BOXB" start "$SKILLB/start-workforce-build.py" --state "$STATEB" 2>"$BOXB/start.err")"
RCB=$?
WANTEDB="$BOXB/.openclaw/workspace/.workforce-build-wanted.json"
if [[ -f "$WANTEDB" ]]; then
  pass "(b1) .workforce-build-wanted.json was written"
else
  fail "(b1) .workforce-build-wanted.json missing" "rc=$RCB out=$OUTB $(tail -2 "$BOXB/start.err" 2>/dev/null)"
fi
REASONB=$(python3 - "$WANTEDB" <<'PYEOF'
import json, sys
try:
    with open(sys.argv[1]) as fh:
        data = json.load(fh)
except Exception:
    print("")
else:
    print(data.get("reason") or "")
PYEOF
)
if [[ "$REASONB" == "interview complete, departments not planned" ]]; then
  pass "(b2) the wanted reason names the unplanned departments"
else
  fail "(b2) the wanted reason is not 'interview complete, departments not planned'" \
    "$(cat "$WANTEDB" 2>/dev/null)"
fi
case "$OUTB" in
  *'"action":"agent-turn-wanted"'*) pass "(b3) the start script printed agent-turn-wanted" ;;
  *) fail "(b3) expected {\"action\":\"agent-turn-wanted\"}" "got: $OUTB (rc=$RCB)" ;;
esac
if [[ ! -f "$BOXB/build-marker.txt" && ! -f "$BOXB/.openclaw/workspace/.workforce-build-start.json" ]]; then
  pass "(b4) no process was started"
else
  fail "(b4) a build process was started for a legacy fixture"
fi

# ---------------------------------------------------------------------------
# (c) interviewComplete false -> exit 3
# ---------------------------------------------------------------------------
echo ""
echo "--- (c) interviewComplete false -> exit 3 ---"
BOXC="$(_mkbox boxc "$STATE_NOT_COMPLETE")"
SKILLC="$BOXC/.openclaw/skills/23-ai-workforce-blueprint/scripts"
STATEC="$BOXC/.openclaw/workspace/.workforce-build-state.json"
OUTC="$(_run "$BOXC" start "$SKILLC/start-workforce-build.py" --state "$STATEC" 2>"$BOXC/start.err")"
RCC=$?
if [[ "$RCC" == "3" ]]; then
  pass "(c1) exit 3 for an interview that is not complete"
else
  fail "(c1) expected exit 3, got $RCC" "$OUTC"
fi
case "$OUTC" in
  *refused*) pass "(c2) the refusal is one JSON line with a reason" ;;
  *) fail "(c2) no refused JSON line on standard output" "got: $OUTC" ;;
esac
if [[ ! -f "$BOXC/build-marker.txt" && ! -f "$BOXC/.openclaw/workspace/.workforce-build-wanted.json" ]]; then
  pass "(c3) nothing was started and nothing was written"
else
  fail "(c3) a refusal still wrote or started something"
fi

# ---------------------------------------------------------------------------
# (d) update-interview-state.sh --complete never issues a Telegram send
# ---------------------------------------------------------------------------
echo ""
echo "--- (d) --complete never calls 'openclaw message send' ---"
BOXD="$(_mkbox boxd "$STATE_COMPLETE_PENDING_DEPT")"
SKILLD="$BOXD/.openclaw/skills/23-ai-workforce-blueprint/scripts"
STATED="$BOXD/.openclaw/workspace/.workforce-build-state.json"
OUTD="$(_run "$BOXD" bash "$SKILLD/update-interview-state.sh" --state "$STATED" --complete 2>&1)"
RCD=$?
if grep -q '^message send' "$BOXD/openclaw-calls.log" 2>/dev/null; then
  fail "(d1) --complete still issued an openclaw message send" "$(cat "$BOXD/openclaw-calls.log" 2>/dev/null)"
else
  pass "(d1) --complete issued no 'message send' call"
fi
case "$OUTD" in
  *'"action":"agent-turn-wanted"'*|*'"action":"apply-started"'*)
    pass "(d2) --complete called the start script and printed its JSON line" ;;
  *) fail "(d2) no start-script action line on standard output" "rc=$RCD tail: $(printf '%s' "$OUTD" | tail -3)" ;;
esac
FLAGD=$(python3 - "$STATED" <<'PYEOF'
import json, sys
try:
    with open(sys.argv[1]) as fh:
        print(json.load(fh).get("interviewComplete"))
except Exception:
    print("unreadable")
PYEOF
)
if [[ "$FLAGD" == "True" ]]; then
  pass "(d3) interviewComplete is still written by --complete"
else
  fail "(d3) interviewComplete was not written" "got: $FLAGD"
fi

# ---------------------------------------------------------------------------
# (e) resume-workforce-build.sh calls the start script, not a self-ping
# ---------------------------------------------------------------------------
echo ""
echo "--- (e) resume calls the start script instead of logging 'nothing to do' ---"
BOXE="$(_mkbox boxe "$STATE_SF_ELIGIBLE")"
SKILLE="$BOXE/.openclaw/skills/23-ai-workforce-blueprint/scripts"
WSE="$BOXE/.openclaw/workspace"
# Same fixture as (a), with the in-flight marker and the start record removed.
rm -f "$WSE/.workforce-build-resume.inflight" "$WSE/.workforce-build-start.json" \
      "$BOXE/build-marker.txt"
_run "$BOXE" bash "$SKILLE/resume-workforce-build.sh" >"$BOXE/resume.out" 2>&1

_i=0
while (( _i < 50 )); do
  [[ -s "$BOXE/build-marker.txt" ]] && break
  _i=$((_i + 1))
  sleep 0.1
done
if [[ -s "$BOXE/build-marker.txt" ]]; then
  pass "(e1) resume called the start script (the build ran)"
else
  fail "(e1) resume did not start the build" "$(tail -3 "$BOXE/resume.out" 2>/dev/null)"
fi
if grep -q 'nothing to do' "$WSE/.workforce-build-state.log" 2>/dev/null; then
  fail "(e2) resume logged 'nothing to do' for a finished interview awaiting its build"
else
  pass "(e2) resume did not log 'nothing to do'"
fi
if grep -q 'start-workforce-build:' "$WSE/.workforce-build-state.log" 2>/dev/null; then
  pass "(e3) the start script's JSON line was logged"
else
  fail "(e3) the start script's line was not logged" "$(tail -3 "$WSE/.workforce-build-state.log" 2>/dev/null)"
fi

fi  # FUNCTIONAL

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if (( FAIL > 0 )); then
  echo "FAIL: $FAIL check(s) failed - acceptance test triggered"
  exit 1
fi
echo "PASS: all start-workforce-build checks pass"
exit 0
