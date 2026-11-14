#!/usr/bin/env bash
# test-build-does-not-complete-gate-v2.sh — BU-32.
#
# Proves the build never marks a gate-v2 interview complete:
#
#   T1. A gate-v2 state whose interviewComplete flag is absent exits
#       EXIT_INTERVIEW_PENDING (87) and the flag is still absent afterwards.
#   T2. A gate-v2 state whose flag is true and whose interviewQc.status is
#       "pass" leaves the interviewQc object byte-identical; only the answers
#       path is recorded (no other interviewProgress key, no interviewQc write).
#   T3. A state with no engine field keeps the old behaviour (the flag is
#       written).
#
# Exit 0 = all tests pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

python3 - "$SKILL_DIR" <<'PY'
import importlib.util, os, sys, json, tempfile, io, contextlib

SKILL = sys.argv[1]
SCRIPTS = os.path.join(SKILL, "scripts")
spec = importlib.util.spec_from_file_location("bw", os.path.join(SCRIPTS, "build-workforce.py"))
bw = importlib.util.module_from_spec(spec); spec.loader.exec_module(bw)

PASS = 0; FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  PASS: {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL: {m}")

# Isolate build-state to a temp file (same pattern as test-retake-department-invalidation.sh).
tmp = tempfile.mkdtemp()
state = os.path.join(tmp, "state.json")
bw._build_state_path = lambda: state

def read_state():
    try:
        with open(state) as f: return json.load(f)
    except Exception: return {}

def write_state(obj):
    with open(state, "w") as f: json.dump(obj, f, indent=2)

def qc_text(obj):
    return json.dumps(obj.get("interviewQc"), sort_keys=True, separators=(",", ":"))

def call(answers_path=None):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        bw._write_interview_complete_to_state(answers_path=answers_path)
    return err.getvalue()

print("== T1: gate-v2 with the flag absent exits 87 and writes nothing ==")
write_state({
    "interviewProgress": {"engine": "gate-v2", "lastQuestionNumber": 12},
    "interviewQc": {"status": "pass"},
})
before = read_state()
try:
    call()
    bad("no exit raised for a gate-v2 state without the flag")
except SystemExit as e:
    ok(f"exited {e.code}") if e.code == bw.EXIT_INTERVIEW_PENDING else bad(f"exit code {e.code} != {bw.EXIT_INTERVIEW_PENDING}")
ok("interviewComplete still absent") if "interviewComplete" not in read_state() else bad("interviewComplete was written")
ok("state unchanged after the refusal") if read_state() == before else bad("state was modified after the refusal")

print("== T2: gate-v2 complete keeps interviewQc byte-identical ==")
write_state({
    "interviewComplete": True,
    "interviewCompletedAt": "2026-11-01T00:00:00",
    "interviewProgress": {"engine": "gate-v2", "lastQuestionNumber": 12,
                          "answersFilePath": "/old/answers.md"},
    "interviewQc": {"status": "pass", "reasons": ["all required answers present"],
                    "missingQuestionIds": []},
})
before = read_state()
qc_before = qc_text(before)
call(answers_path=os.path.join(tmp, "answers.md"))
after = read_state()
ok("interviewQc byte-identical") if qc_text(after) == qc_before else bad(f"interviewQc changed: {qc_before} -> {qc_text(after)}")
ok("interviewComplete still true") if after.get("interviewComplete") is True else bad("interviewComplete changed")
ok("answersFilePath recorded") if after.get("interviewProgress", {}).get("answersFilePath") == os.path.join(tmp, "answers.md") else bad("answers path not recorded")
added = set(after.get("interviewProgress", {})) - set(before.get("interviewProgress", {}))
ok("no other interviewProgress key added") if not added else bad(f"unexpected interviewProgress keys: {sorted(added)}")
ok("interviewCompletedAt untouched") if after.get("interviewCompletedAt") == "2026-11-01T00:00:00" else bad("interviewCompletedAt changed")

print("== T3: a state with no engine keeps the old behaviour ==")
write_state({"interviewQc": {"status": "pending"}})
call(answers_path=os.path.join(tmp, "answers.md"))
after = read_state()
ok("interviewComplete written") if after.get("interviewComplete") is True else bad("interviewComplete not written")
ok("interviewProgress.interviewComplete written") if after.get("interviewProgress", {}).get("interviewComplete") is True else bad("interviewProgress.interviewComplete not written")
ok("interviewCompletedAt written") if after.get("interviewCompletedAt") else bad("interviewCompletedAt not written")
ok("answersFilePath recorded") if after.get("interviewProgress", {}).get("answersFilePath") == os.path.join(tmp, "answers.md") else bad("answers path not recorded")

print()
print("===================================================")
print(f"  test-build-does-not-complete-gate-v2: PASS={PASS} FAIL={FAIL}")
print("===================================================")
sys.exit(1 if FAIL else 0)
PY
