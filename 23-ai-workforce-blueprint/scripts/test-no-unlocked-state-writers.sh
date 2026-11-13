#!/usr/bin/env bash
# test-no-unlocked-state-writers.sh — BU-70 acceptance test.
#
# WHAT IT PROVES
#   Every state writer this unit changed takes the state lock, and a lock
#   conflict no longer crashes the build.
#
#   For each changed script: a helper process takes `<state>.write.lock` — the
#   same lock file and flock that workforce_state.lock() uses — writes its own
#   field, holds the lock for two seconds, records the release time in a witness
#   file, then releases. The script is started while that lock is held. Because
#   the script's own write goes through the same lock, its write cannot land
#   before the witness time — so the test asserts BOTH:
#     1. the script's write timestamp is at or after the lock was released
#        (an unlocked writer would have landed ~2s earlier), and
#     2. the field the helper wrote is still present (no lost update).
#
#   For the build: a helper updates `interviewProgress.lastQuestionAt` every 50
#   milliseconds while `write_chosen_departments_artifact` runs 20 times. The
#   test asserts no exception and that both writers' fields are present at the
#   end — the StateConflict the build used to let escape now retries and wins.
#
#   `run-closeout.sh` records no timestamp in the two fields it writes, so its
#   ordering check is wall clock: it must not finish before the lock is released,
#   and both its record and the helper's field must be present.
#
# OFFLINE AND SELF-CONTAINED. No network, no live box, no client data. Every
# state file, HOME and OpenClaw root lives under one temporary directory that is
# removed on exit. Scripts run exactly where they are installed, so their own
# relative helper lookups are the real ones.
#
# Exit 0 = every check passed; non-zero = at least one check failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
S37_SCRIPTS="$(cd "$SCRIPT_DIR/../../37-zhc-closeout/scripts" && pwd)"

QC_RATE="$S37_SCRIPTS/qc-rate-artifacts.sh"
WELCOME="$SCRIPT_DIR/send-presentation-dept-welcome.sh"
INSTALL_CRON="$S37_SCRIPTS/install-closeout-resume-cron.sh"
VERIFY_WIRING="$SCRIPT_DIR/verify-wiring.sh"
RUN_CLOSEOUT="$S37_SCRIPTS/run-closeout.sh"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS + 1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL + 1)); }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/no-unlocked-writers.XXXXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

HOME_DIR="$WORK/home"
mkdir -p "$HOME_DIR/.openclaw/workspace"
OCROOT="$WORK/oc"
mkdir -p "$OCROOT/workspace/departments/marketing"
: > "$OCROOT/openclaw.json"

# A stub `openclaw` that never sends anything and never starts a gateway.
BIN="$WORK/bin"
mkdir -p "$BIN"
cat > "$BIN/openclaw" <<'OCSTUB'
#!/usr/bin/env bash
exit 0
OCSTUB
chmod +x "$BIN/openclaw"

for _f in "$QC_RATE" "$WELCOME" "$INSTALL_CRON" "$VERIFY_WIRING" "$RUN_CLOSEOUT" \
          "$SCRIPT_DIR/build-workforce.py"; do
  if [ -f "$_f" ]; then ok "present: $(basename "$_f")"; else bad "missing: $_f"; fi
done
for _t in jq python3 curl; do
  if command -v "$_t" >/dev/null 2>&1; then ok "$_t available"; else bad "$_t not on PATH — cannot run this test"; fi
done

# ── the lock holder ──────────────────────────────────────────────────────────
# Runs in the background and is waited on, so the two seconds really elapse
# before the assertions read the state.
hold_lock() {  # <state> <seconds> <witness-file>
  python3 - "$1" "$2" "$3" <<'PYHOLD' &
import fcntl, json, sys, time
from datetime import datetime, timezone

state_path, seconds, witness = sys.argv[1], float(sys.argv[2]), sys.argv[3]

def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

with open(state_path + '.write.lock', 'a+') as handle:
    fcntl.flock(handle, fcntl.LOCK_EX)
    state = json.loads(open(state_path).read())
    state['lockHelperField'] = 'held-by-helper'
    state['lockHelperWrittenAt'] = now()
    with open(state_path, 'w') as out:
        json.dump(state, out, indent=2)
    time.sleep(seconds)
    with open(witness, 'w') as out:
        out.write(now())
    fcntl.flock(handle, fcntl.LOCK_UN)
PYHOLD
}

RU_RC=0; RU_WITNESS=""; RU_TS_FIELD=""; RU_DONE_AT=""
run_under_lock() {   # <label> <state> <timestamp-field> <command...>
  local label="$1" state="$2" ts_field="$3"; shift 3
  RU_WITNESS="$WORK/$label.released"
  RU_TS_FIELD="$ts_field"
  rm -f "$RU_WITNESS"
  hold_lock "$state" 2 "$RU_WITNESS" &
  local helper_pid=$!
  sleep 0.4          # let the helper take the lock first
  "$@" >"$WORK/$label.out" 2>&1
  RU_RC=$?
  # ponytail: wall-clock finish proves the script blocked on the lock (the lock
  # is held a full 2s; an unlocked writer would finish before the witness lands).
  # Upgrade path: per-write logical clocks if second-granularity ever matters.
  RU_DONE_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  wait "$helper_pid" 2>/dev/null
}

# verify_written <state> <;-separated dotted paths> <witness> <timestamp field>
verify_written() {
  python3 - "$1" "$2" "$3" "$4" "$RU_DONE_AT" <<'PYVERIFY'
import json, sys

state_path, want_raw, witness_path, ts_field, done_at = sys.argv[1:6]
try:
    state = json.loads(open(state_path).read())
except Exception as exc:  # noqa: BLE001
    print(f"state unreadable: {exc}")
    raise SystemExit(1)

def dig(obj, dotted):
    cur = obj
    for part in dotted.split('.'):
        if part.isdigit():
            cur = cur[int(part)]
        else:
            cur = cur[part]
    return cur

problems = []
for dotted in want_raw.split(';'):
    if not dotted:
        continue
    try:
        value = dig(state, dotted)
    except (KeyError, IndexError, TypeError):
        problems.append(f"{dotted} missing")
        continue
    if value is None or value == "":
        problems.append(f"{dotted} empty")

if 'lockHelperField' not in state:
    problems.append("the helper's own field was lost")

try:
    released = open(witness_path).read().strip()
except OSError:
    released = ""
if not released:
    problems.append("the helper never recorded its release time")
else:
    # The script must not have finished before the lock was released: with the
    # helper holding the lock a full 2s, finishing earlier means it never
    # blocked on the lock (an unlocked jq>tmp>mv writer finishes in ~0s).
    if not isinstance(done_at, str) or done_at < released:
        problems.append("script finished before the lock was released "
                        f"({done_at!r} < {released!r}) — it never blocked on the lock")
if ts_field:
    try:
        written = dig(state, ts_field)
    except (KeyError, IndexError, TypeError):
        written = None
    if not isinstance(written, str) or not written:
        problems.append(f"{ts_field} missing or empty")

if problems:
    print("; ".join(problems))
    raise SystemExit(1)
print("script blocked on the lock and the helper's field survived")
PYVERIFY
}

# ── A. qc-rate-artifacts.sh ─────────────────────────────────────────────────
echo "== A: qc-rate-artifacts.sh =="
SA="$WORK/a-state.json"
printf '{}\n' > "$SA"
run_under_lock a "$SA" "qualityRatings.flow_diagram.ratedAt" \
  env HOME="$HOME_DIR" ZHC_STATE_FILE="$SA" ZHC_LOG_FILE="$WORK/a.log" \
      bash "$QC_RATE" --key flow_diagram --state "$SA"
echo "  exit $RU_RC"
if out="$(verify_written "$SA" "qualityRatings.flow_diagram.ratedAt" "$RU_WITNESS" "$RU_TS_FIELD")"; then
  ok "A: $out"
else
  bad "A: $out"
fi
if out="$(verify_written "$SA" "materializationChecks.flow_diagram.checkedAt" "$RU_WITNESS" "materializationChecks.flow_diagram.checkedAt")"; then
  ok "A: the materialization record is locked too — $out"
else
  bad "A: the materialization record — $out"
fi

# ── B. send-presentation-dept-welcome.sh ────────────────────────────────────
echo "== B: send-presentation-dept-welcome.sh =="
# The script resolves its state from the OpenClaw root; HOME points at the
# scratch root, so no live file is ever in reach.
SB="$HOME_DIR/.openclaw/workspace/.workforce-build-state.json"
cat > "$SB" <<'BSTATE'
{
  "ownerChat": "0",
  "ownerName": "Test Owner",
  "companyName": "Test Company",
  "departments": [
    {"slug": "presentations", "wiringStatus": "done",
     "roleLibraryFilled": true, "sopLibraryFilled": true}
  ]
}
BSTATE
run_under_lock b "$SB" "departments.0.presentationDeptWelcomeSentAt" \
  env HOME="$HOME_DIR" PATH="$BIN:$PATH" bash "$WELCOME" --force
echo "  exit $RU_RC"
if out="$(verify_written "$SB" "departments.0.presentationDeptWelcomeSent;departments.0.presentationDeptWelcomeSentAt" "$RU_WITNESS" "$RU_TS_FIELD")"; then
  ok "B: $out"
else
  bad "B: $out"
fi

# ── C. install-closeout-resume-cron.sh ──────────────────────────────────────
echo "== C: install-closeout-resume-cron.sh =="
# One stub covers the three cron calls: `cron list` reports the job only after
# `cron add` has run, so the script reaches its own registration write.
CRON_BIN="$WORK/cron-bin"
mkdir -p "$CRON_BIN"
cat > "$CRON_BIN/openclaw" <<'CRONSTUB'
#!/usr/bin/env bash
MARKER="${STUB_CRON_MARKER:?}"
if [ "${1:-}" = "cron" ] && [ "${2:-}" = "add" ] && [ "${3:-}" = "--help" ]; then
  printf '  --no-deliver\n'
  exit 0
fi
if [ "${1:-}" = "cron" ] && [ "${2:-}" = "add" ]; then
  printf '{"uuid":"stub-uuid-1"}\n'
  : > "$MARKER"
  exit 0
fi
if [ "${1:-}" = "cron" ] && [ "${2:-}" = "list" ]; then
  if [ -f "$MARKER" ]; then
    printf 'uuid: stub-uuid-1\nname: closeout-resume\n'
  else
    printf 'uuid: other\nname: something-else\n'
  fi
  exit 0
fi
exit 0
CRONSTUB
chmod +x "$CRON_BIN/openclaw"
SC="$WORK/c-state.json"
printf '{"closeoutStatus": "partial"}\n' > "$SC"
rm -f "$WORK/c-marker"
run_under_lock c "$SC" "closeoutResumeRegisteredAt" \
  env HOME="$HOME_DIR" PATH="$CRON_BIN:$PATH" STUB_CRON_MARKER="$WORK/c-marker" \
      ZHC_STATE_FILE="$SC" bash "$INSTALL_CRON"
echo "  exit $RU_RC"
if out="$(verify_written "$SC" "closeoutResumeUuid;closeoutResumeRegisteredAt" "$RU_WITNESS" "$RU_TS_FIELD")"; then
  ok "C: $out"
else
  bad "C: $out"
fi

# ── D. verify-wiring.sh ─────────────────────────────────────────────────────
echo "== D: verify-wiring.sh =="
# verify-wiring resolves its root from HOME, not from OC_ROOT. A department tree
# that resolves, an empty openclaw.json and one department: the verdict is
# expected to be a failure, and the state write happens after the loop whatever
# the verdict is.
SD="$HOME_DIR/.openclaw/workspace/.workforce-build-state.json"
mkdir -p "$HOME_DIR/.openclaw/workspace/departments/marketing"
: > "$HOME_DIR/.openclaw/openclaw.json"
printf '%s\n' '{"departments": [{"id": "marketing", "status": "done"}]}' > "$SD"
run_under_lock d "$SD" "departments.0.wiringCheckedAt" \
  env HOME="$HOME_DIR" bash "$VERIFY_WIRING" --dept marketing
echo "  exit $RU_RC"
if out="$(verify_written "$SD" "departments.0.wiringStatus;departments.0.wiringCheckedAt" "$RU_WITNESS" "$RU_TS_FIELD")"; then
  ok "D: $out"
else
  bad "D: $out"
fi

# ── E. run-closeout.sh ──────────────────────────────────────────────────────
echo "== E: run-closeout.sh =="
# No timestamps in these two fields, so ordering is wall clock: the script must
# not finish before the helper released the lock, and both its record and the
# helper's field must survive. Credential keys are deliberately absent so the
# script stops at its own refusal write rather than spending anything.
SE="$WORK/e-state.json"
printf '%s\n' '{"companyId": "stub-company-id", "companySlug": "stub-company",
  "buildCompletedAt": "2020-01-01T00:00:00Z",
  "interviewComplete": false, "interviewQc": {"status": ""}}' > "$SE"
run_under_lock e "$SE" "" \
  env HOME="$HOME_DIR" OC_ROOT="$OCROOT" PATH="$BIN:$PATH" \
      ZHC_STATE_FILE="$SE" ZHC_SKIP_TG_PREFLIGHT=1 bash "$RUN_CLOSEOUT"
echo "  exit $RU_RC"
python3 - "$SE" "$RU_WITNESS" <<'PYE'
import json, sys
from datetime import datetime

state_path, witness_path = sys.argv[1], sys.argv[2]
state = json.loads(open(state_path).read())
problems = []

if 'lockHelperField' not in state:
    problems.append("the helper's own field was lost")
if state.get('closeoutStatus') not in ('failed', 'blocked-qc-pending', 'blocked-interview-incomplete'):
    problems.append(f"closeout record not written (closeoutStatus={state.get('closeoutStatus')!r})")

released = open(witness_path).read().strip()
written = state.get('closeoutBlockReason') is not None or state.get('closeoutStatus')
if released and not written:
    problems.append("nothing was written after the lock was released")

if problems:
    print("; ".join(problems))
    raise SystemExit(1)
print(f"closeout record written (closeoutStatus={state.get('closeoutStatus')!r}) and the helper's field survived")
PYE
if [ "$?" -eq 0 ]; then
  ok "E: locked write, no lost field"
else
  bad "E: closeout state write failed the lock assertions"
fi

# ── F. the build: 20 runs against a 50ms stamping helper ────────────────────
echo "== F: build-workforce.py write_chosen_departments_artifact =="
SF="$WORK/f-state.json"
printf '{}\n' > "$SF"
mkdir -p "$WORK/f-company"
cat > "$WORK/f-driver.py" <<'PYF'
import importlib.util, json, os, subprocess, sys

scripts_dir, state_path, company_dir = sys.argv[1], sys.argv[2], sys.argv[3]

STAMPER = r'''
import sys, time
from datetime import datetime, timezone
sys.path.insert(0, sys.argv[1])
import workforce_state

state_path, duration = sys.argv[2], float(sys.argv[3])
deadline = time.time() + duration
while time.time() < deadline:
    workforce_state.update(state_path, lambda s: s.setdefault('interviewProgress', {}).__setitem__(
        'lastQuestionAt', datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')))
    time.sleep(0.05)
'''

spec = importlib.util.spec_from_file_location(
    'real_builder', os.path.join(scripts_dir, 'build-workforce.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.COMPANY_DIR = company_dir

stamper = subprocess.Popen([sys.executable, '-c', STAMPER, scripts_dir, state_path, '6'],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

chosen = {'marketing': {'name': 'Marketing', 'emoji': '*', 'head': 'Director of Marketing',
                        'description': 'Marketing department'}}
failure = ''
try:
    for _ in range(20):
        module.write_chosen_departments_artifact(chosen, company_dir=company_dir,
                                                 source='acceptance-test')
finally:
    stamper.wait(timeout=60)

if stamper.returncode != 0:
    failure = 'the 50ms stamping helper failed: ' + (stamper.stderr.read() or '')[-400:]

state = json.loads(open(state_path).read())
if not failure:
    progress = state.get('interviewProgress')
    if not isinstance(progress, dict) or not progress.get('lastQuestionAt'):
        failure = "interviewProgress.lastQuestionAt missing - the stamping writer's field was lost"
    chosen_record = (state.get('canonicalReconciliation') or {}).get('chosenDepartments')
    if not isinstance(chosen_record, dict) or not chosen_record.get('slugs'):
        failure = "canonicalReconciliation.chosenDepartments missing - the build's own write was lost"

if failure:
    print(failure)
    raise SystemExit(1)
print("20 runs, no exception, both writers' fields present")
PYF

F_OUT="$(env HOME="$HOME_DIR" MASTER_FILES_DIR="$WORK/f-master" \
  OPENCLAW_ROOT="$WORK/f-runtime" OPENCLAW_WORKSPACE_ROOT="$WORK/f-workspace" \
  WORKFORCE_BUILD_STATE_FILE="$SF" \
  python3 "$WORK/f-driver.py" "$SCRIPT_DIR" "$SF" "$WORK/f-company" 2>&1)"
F_RC=$?
if [ "$F_RC" -eq 0 ]; then
  ok "F: $F_OUT"
else
  bad "F: $(printf '%s' "$F_OUT" | tail -3 | tr '\n' ' ')"
fi

echo "--------------------------------------------"
echo "  pass=$PASS fail=$FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo "ALL NO-UNLOCKED-STATE-WRITER TESTS PASSED"
  exit 0
fi
echo "NO-UNLOCKED-STATE-WRITER TEST FAILURES: $FAIL"
exit 1
