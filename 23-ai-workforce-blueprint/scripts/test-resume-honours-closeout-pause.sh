#!/usr/bin/env bash
# test-resume-honours-closeout-pause.sh — BU-69 (closes WF-088): the 15-minute
# resume job honours the operator's closeout pause.
#
# BEFORE: the closeout branch launched (or fell back to a self-ping for)
# run-closeout.sh whenever buildCompletedAt was set and closeoutStatus was not
# done|sent. An operator who paused the closeout by setting
# closeoutResumePaused=true had it restarted under them on the next cron fire.
#
# AFTER: one check between the owner-sends hold and the launch clears
# _CLOSEOUT_SCRIPT when closeoutResumePaused is true, so run-closeout.sh is NOT
# launched on that fire.
#
# Two assertions, exactly the acceptance bar:
#   T1: state with buildCompletedAt, closeoutStatus "partial" and
#       closeoutResumePaused true -> the stub run-closeout.sh writes NO marker.
#   T2 (control): the same state without the pause -> the marker IS written,
#       proving T1 is load-bearing rather than vacuous.
#
# Hermetic: fresh $HOME sandbox, stub `openclaw` on PATH (records its calls,
# never touches a gateway), no network, no live box. Exit 0 = pass.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESUME="$SCRIPT_DIR/resume-workforce-build.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  PASS: $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

T_HOME="$(mktemp -d)"
FIXTURE_BIN="$(mktemp -d)"
STUB_LOG="$FIXTURE_BIN/calls.log"
export STUB_LOG
cleanup() { rm -rf "$T_HOME" "$FIXTURE_BIN"; }
trap cleanup EXIT

if [[ ! -f "$RESUME" ]]; then
  echo "FATAL: $RESUME not found"
  exit 1
fi

# Stub CLI: records every call, never reaches a real gateway.
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" >> "$STUB_LOG"\nexit 0\n' > "$FIXTURE_BIN/openclaw"
chmod +x "$FIXTURE_BIN/openclaw"

# Hermetic box: $HOME/.openclaw is the resolved OC_ROOT. The stub closeout
# records that it ran by touching a marker beside this run's sandbox.
run_resume() {
  local label="$1" paused="$2"
  local home="$T_HOME/$label"
  local workspace="$home/.openclaw/workspace"
  local marker="$home/closeout-ran.marker"
  local state="$workspace/.workforce-build-state.json"
  local depts_dir="$workspace/departments"
  local role_dir="$depts_dir/fixture-dept/fixture-role"

  mkdir -p "$workspace" "$role_dir" "$home/.openclaw/skills/37-zhc-closeout/scripts"
  printf '#!/usr/bin/env bash\ntouch "%s"\n' "$marker" \
    > "$home/.openclaw/skills/37-zhc-closeout/scripts/run-closeout.sh"
  chmod +x "$home/.openclaw/skills/37-zhc-closeout/scripts/run-closeout.sh"

  # A real, non-stub how-to.md: the resume lane's disk-reality audit demotes a
  # "done" department with no real how-to.md (>= 256 bytes, no placeholder
  # marker) back to pending, which would also clear buildCompletedAt.
  {
    printf 'Fixture role how-to for BU-69. '
    i=0
    while (( i < 8 )); do
      printf 'Padding line %d keeps this file above the 256-byte stub floor and free of placeholder markers. ' "$i"
      i=$((i + 1))
    done
    printf '\n'
  } > "$role_dir/how-to.md"

  # The resume lane calls workforce_completion.finalize() on EVERY fire, before
  # any branch is chosen, and finalize() DELETES buildCompletedAt whenever
  # evaluate() reports any unmet requirement (workforce_completion.py). A thin
  # fixture (no departments, no buildChecks, no digests) is therefore stripped
  # into a "nothing to do" state and never reaches the closeout branch at all —
  # which is exactly how this test can pass or fail without proving anything.
  # So build a genuinely verified state, computing both digests with the real
  # module rather than re-implementing them here.
  python3 - "$SCRIPT_DIR" "$state" "$depts_dir" "$paused" <<'PY'
import json, sys
scripts, state_path, root, paused = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "true"
sys.path.insert(0, scripts)
from workforce_completion import artifact_digest, input_digest, DIGEST_VERSION

state = {
    "companyId": "fixture-company",
    "companySlug": "fixture-company",
    "companyName": "Fixture Company",
    "interviewComplete": True,
    "interviewCompletedAt": "2026-11-12T00:00:00Z",
    "interviewQc": {"status": "pass"},
    "roleLibraryStatus": "done",
    "sopLibraryStatus": "done",
    "commsAutomationStatus": "not-applicable",
    "departments": [{"id": "fixture-dept", "slug": "fixture-dept", "status": "done"}],
    "buildId": "fixture-build",
    "buildChecks": {
        name: {"status": "pass", "buildId": "fixture-build"}
        for name in ("registration", "postBuild", "qc", "libraries")
    },
    "buildCompletedAt": "2026-11-12T01:00:00Z",
    "closeoutStatus": "partial",
    "maxResumeAttempts": 12,
}
if paused:
    state["closeoutResumePaused"] = True
state["buildArtifactVerification"] = {
    "root": root,
    "digest": artifact_digest(root, DIGEST_VERSION),
    "digestVersion": DIGEST_VERSION,
    "inputDigest": input_digest(state),
}
with open(state_path, "w", encoding="utf-8") as handle:
    handle.write(json.dumps(state, indent=2) + "\n")
PY
  local fixture_rc=$?
  if [[ "$fixture_rc" -ne 0 ]]; then
    echo "FATAL: fixture setup failed (rc=$fixture_rc)"
    exit 1
  fi

  HOME="$home" PATH="$FIXTURE_BIN:$PATH" bash "$RESUME" >/dev/null 2>&1
  echo "  ($label: resume exit $?)" >&2

  # The closeout is launched detached (nohup ... &); give it a moment to land.
  local i
  for i in $(seq 1 50); do
    [[ -f "$marker" ]] && break
    sleep 0.1
  done

  if [[ -f "$marker" ]]; then echo "ran"; else echo "not-ran"; fi
}

# ─────────────────────────────────────────────────────────────────────────
echo "== T1: closeoutResumePaused=true -> run-closeout.sh NOT launched =="

T1_OUT="$(run_resume paused true 2>/dev/null)"
if [[ "$T1_OUT" == "not-ran" ]]; then
  ok "T1: no closeout marker — the paused closeout was not relaunched"
else
  bad "T1: closeout marker present — the resume lane ignored closeoutResumePaused"
fi

T1_LOG="$T_HOME/paused/.openclaw/workspace/.workforce-build-state.log"
if [[ -f "$T1_LOG" ]] && python3 - "$T1_LOG" <<'PY'
import sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
assert "closeoutResumePaused=true -- run-closeout.sh NOT launched." in text, text[-2000:]
PY
then
  ok "T1: the log records the pause decision"
else
  bad "T1: the log does not record the pause decision"
fi

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "== T2 (control): without the pause the same state DOES launch it =="

T2_OUT="$(run_resume control '' 2>/dev/null)"
if [[ "$T2_OUT" == "ran" ]]; then
  ok "T2: closeout marker present — the same fixture launches the closeout when not paused"
else
  bad "T2: no marker without the pause — the control did not fire, T1 proves nothing"
fi

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "==================================================="
echo "  test-resume-honours-closeout-pause: PASS=$PASS FAIL=$FAIL"
echo "==================================================="
if (( FAIL > 0 )); then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all BU-69 closeout-pause checks pass"
exit 0
