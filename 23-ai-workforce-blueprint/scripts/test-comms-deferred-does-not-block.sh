#!/usr/bin/env bash
# test-comms-deferred-does-not-block.sh — BU-54 (closes WF-074, decision D-6):
# the Skill 38 communication-automation handoff is RECORDED AS DEFERRED, never
# waited on.
#
# BEFORE: resume-workforce-build.sh treated commsAutomationStatus as terminal only
# for done|not-applicable. A workforce whose Skill 38 handoff never happened sat
# with comms_automation_dirty=1 forever: HOP-4 (the buildCompletedAt writer) could
# never fire, the progress score never rose, and the watchdog's gates_open stayed
# open. The client build was blocked on a handoff nobody was going to make.
#
# AFTER: on the first fire where the status is absent or "pending", the resume
# lane stamps commsAutomationStatus="deferred" + commsAutomationDeferredAt and
# appends ONE closeoutBlockers entry of class "comms-automation-deferred".
# "deferred" is terminal in every gate that reads it (workforce_completion.evaluate,
# the resume progress score, the resume dirty case, the watchdog's gates_open), so
# the build advances without the handoff.
#
# Two assertions, exactly the acceptance bar:
#   T1: one hermetic run of the real resume script leaves commsAutomationStatus
#       == "deferred" and exactly one blocker of that class.
#   T2: workforce_completion.evaluate() on a state that passes every other check
#       does not report "communications"; with the field absent it does (the
#       negative control proves the change is load-bearing).
#
# Hermetic: fresh $HOME sandbox, stub `openclaw` on PATH (records its calls, never
# touches a gateway), no network, no live box. Exit 0 = pass, non-zero = fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESUME="$SCRIPT_DIR/resume-workforce-build.sh"
COMPLETION="$SCRIPT_DIR/workforce_completion.py"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  PASS: $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

T_HOME="$(mktemp -d)"
FIXTURE_BIN="$(mktemp -d)"
STUB_LOG="$FIXTURE_BIN/calls.log"
export STUB_LOG
ART_DIR="$(mktemp -d)"
cleanup() { rm -rf "$T_HOME" "$FIXTURE_BIN" "$ART_DIR"; }
trap cleanup EXIT

if [[ ! -f "$RESUME" ]]; then
  echo "FATAL: $RESUME not found"
  exit 1
fi
if [[ ! -f "$COMPLETION" ]]; then
  echo "FATAL: $COMPLETION not found"
  exit 1
fi

# ─────────────────────────────────────────────────────────────────────────
echo "== T1: the resume lane records the handoff as deferred =="

printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" >> "$STUB_LOG"\nexit 0\n' > "$FIXTURE_BIN/openclaw"
chmod +x "$FIXTURE_BIN/openclaw"

WORKSPACE="$T_HOME/.openclaw/workspace"
mkdir -p "$WORKSPACE/departments/communications/director" \
         "$WORKSPACE/departments/operations/coordinator"

# The stale-state reset demotes a "done" department with no real how-to.md on
# disk, so every department the fixture calls done must have one.
for role_dir in "$WORKSPACE/departments/communications/director" \
                "$WORKSPACE/departments/operations/coordinator"; do
  {
    echo "# Role guide"
    for i in $(seq 1 12); do
      echo "This role owns its department's weekly review and escalates to the operator when a task stalls."
    done
  } > "$role_dir/how-to.md"
done

STATE="$WORKSPACE/.workforce-build-state.json"
cat > "$STATE" <<'JSON'
{
  "companyId": "fixture-company",
  "companySlug": "fixture-company",
  "companyName": "Fixture Company",
  "interviewComplete": true,
  "interviewCompletedAt": "2026-11-12T00:00:00Z",
  "interviewQc": {"status": "pass"},
  "roleLibraryStatus": "done",
  "sopLibraryStatus": "done",
  "departments": [
    {"id": "communications", "slug": "communications", "status": "done", "completedAt": "2026-11-12T01:00:00Z"},
    {"id": "operations", "slug": "operations", "status": "done", "completedAt": "2026-11-12T01:00:00Z"}
  ]
}
JSON

T1_RC=0
HOME="$T_HOME" PATH="$FIXTURE_BIN:$PATH" bash "$RESUME" >/dev/null 2>&1 || T1_RC=$?

[[ "$T1_RC" -eq 0 ]] && ok "T1: resume-workforce-build.sh exits 0 (a recorded deferral is not an error)" \
                     || bad "T1: resume-workforce-build.sh exited $T1_RC (expected 0)"

[[ -s "$STUB_LOG" ]] && ok "T1: the stub openclaw was invoked (the run reached the recovery lane)" \
                     || bad "T1: the stub openclaw was never called (the run never reached the recovery lane)"

python3 - "$STATE" <<'PY' && ok "T1: state has commsAutomationStatus=deferred and exactly one blocker of that class" \
                          || bad "T1: the deferral was not recorded correctly"
import json, sys

state = json.load(open(sys.argv[1]))
reason = "Skill 38 handoff not done; company build not blocked"

assert state.get("commsAutomationStatus") == "deferred", state.get("commsAutomationStatus")
stamped = state.get("commsAutomationDeferredAt")
assert isinstance(stamped, str) and stamped, stamped

blockers = state.get("closeoutBlockers") or []
assert isinstance(blockers, list), blockers
matching = [b for b in blockers if isinstance(b, dict) and b.get("class") == "comms-automation-deferred"]
assert len(matching) == 1, matching
entry = matching[0]
assert entry.get("cleared") is False, entry
assert entry.get("reason") == reason, entry
assert entry.get("since") == stamped, entry
PY

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "== T2: evaluate() does not block on a deferred handoff =="

echo "# Artifact" > "$ART_DIR/brief.md"

PYTHONPATH="$SCRIPT_DIR" python3 - "$ART_DIR" <<'PY' && ok "T2: 'communications' leaves evaluate() for deferred and returns for absent (control)" \
                                              || bad "T2: evaluate() still blocks on a deferred handoff, or the control did not fire"
import sys

import workforce_completion as wc

art_root = sys.argv[1]

state = {
    "companyId": "fixture-company",
    "companySlug": "fixture-company",
    "interviewComplete": True,
    "interviewCompletedAt": "2026-11-12T00:00:00Z",
    "interviewQc": {"status": "pass"},
    "roleLibraryStatus": "done",
    "sopLibraryStatus": "done",
    "departments": [{"slug": "operations", "status": "done"}],
    "buildId": "fixture-build",
}
state["buildChecks"] = {
    name: {"status": "pass", "buildId": "fixture-build"} for name in wc.REQUIRED_CHECKS
}
verification = {
    "root": art_root,
    "digest": wc.artifact_digest(art_root),
    "digestVersion": wc.DIGEST_VERSION,
}
state["buildArtifactVerification"] = verification
verification["inputDigest"] = wc.input_digest(state)

# The fixture passes every check that is not about the handoff.
assert wc.evaluate(state) == [], wc.evaluate(state)

state["commsAutomationStatus"] = "deferred"
missing = wc.evaluate(state)
assert missing == [], missing
assert "communications" not in missing, missing

# Negative control: without the stamp the gate still blocks.
del state["commsAutomationStatus"]
control = wc.evaluate(state)
assert "communications" in control, control
PY

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "==================================================="
echo "  test-comms-deferred-does-not-block: PASS=$PASS FAIL=$FAIL"
echo "==================================================="
if (( FAIL > 0 )); then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all BU-54 comms-deferred checks pass"
exit 0
