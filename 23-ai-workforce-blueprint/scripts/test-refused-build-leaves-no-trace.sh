#!/usr/bin/env bash
# test-refused-build-leaves-no-trace.sh — BU-53 acceptance test.
#
# A refused build must leave no trace. Legacy fixture: a genuine eight-answer
# transcript, no canon department decisions recorded, a recorded industry pack,
# and a build-state that already carries buildCompletedAt and
# completionVerification.status == "verified".
#
#   A1  the build exits 88 at the decision-coverage gate
#   A2  the transcript's bytes are unchanged
#   A3  interviewComplete is absent afterwards
#   A4  buildCompletedAt is unchanged
#   A5  buildId is unchanged
#   A6  interview-handoff.md does not exist
#   A7  a second run exits 88 again (not 87)
#
# Exit 0 = all guards pass; non-zero = a guard failed.
# Hermetic: sandboxed $HOME, $MASTER_FILES_DIR, scratch build-state. Nothing
# may escape the sandbox.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BW="$SCRIPT_DIR/build-workforce.py"

PASS=0
FAIL=0
good() { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad()  { FAIL=$((FAIL + 1)); echo "FAIL: $1" >&2; }

if [ ! -f "$BW" ]; then bad "required file missing: $BW"; echo "ABORT"; exit 1; fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
SANDBOX_HOME="$TMP/home"
MASTER="$TMP/master-files"
DISCOVERY="$MASTER/company-discovery"
STATE="$SANDBOX_HOME/.openclaw/workspace/.workforce-build-state.json"
mkdir -p "$SANDBOX_HOME/.openclaw/workspace" "$DISCOVERY" "$MASTER/zero-human-company"

# Genuine eight-answer transcript: no non-interactive header, > 512 bytes,
# eight **Q:** blocks.
TRANSCRIPT="$DISCOVERY/workforce-interview-answers.md"
cat > "$TRANSCRIPT" <<'ANSWERS'
# Workforce Interview Answers

**Q:** What is the name of your business?
**A:** Scratch Canary Co

---

**Q:** What industry are you in?
**A:** Professional services for small businesses

---

**Q:** What does your business do?
**A:** We help owners turn their scattered know-how into a team that runs without them.

---

**Q:** What tools do you use?
**A:** Slack, Notion, Google Workspace

---

**Q:** What is your biggest challenge?
**A:** Everything depends on me and I cannot hand work off cleanly.

---

**Q:** Tell me about your Marketing department.
**A:** Activities: social media and email
KPIs: leads per month
Challenges: no consistent publishing rhythm

---

**Q:** Tell me about your Sales department.
**A:** Activities: inbound follow-up and proposals
KPIs: close rate
Challenges: leads sit untouched for days

---

**Q:** Tell me about your Support department.
**A:** Activities: answering customer questions
KPIs: first response time
Challenges: the same questions keep coming back

---
ANSWERS

# Legacy build-state: buildCompletedAt + a verified completion, a recorded
# industry pack, and NO canon department decisions recorded.
python3 - "$STATE" <<'PYSTATE'
import json, sys
state = {
    "companyId": "scratch-canary-co",
    "companySlug": "scratch-canary-co",
    "buildCompletedAt": "2026-10-01T12:00:00",
    "buildId": "build-before-refusal",
    "completionVerification": {
        "version": 1,
        "buildId": "build-before-refusal",
        "status": "verified",
    },
    "industryPack": {"slug": "professional-services", "source": "record-industry-pack.sh"},
}
json.dump(state, open(sys.argv[1], "w"), indent=2)
PYSTATE

python3 - "$BW" "$TMP" "$SANDBOX_HOME" "$MASTER" "$DISCOVERY" "$STATE" "$TRANSCRIPT" <<'PY'
import importlib.util, json, os, sys

bw_path, tmp, home, master, discovery, state_path, transcript = sys.argv[1:8]

# Sandbox every path BEFORE the module is imported (HOME/MASTER_FILES_DIR are
# read at import time) and again after, so no code path resolves a live box.
os.environ["HOME"] = home
os.environ["MASTER_FILES_DIR"] = master
os.environ["WORKFORCE_BUILD_STATE_FILE"] = state_path
os.environ.pop("MC_COMPANY_ID", None)
os.environ.pop("ZERO_HUMAN_COMPANY_DIR", None)

sys.path.insert(0, os.path.dirname(os.path.abspath(bw_path)))
spec = importlib.util.spec_from_file_location("bw", bw_path)
bw = importlib.util.module_from_spec(spec)
sys.modules["bw"] = bw
spec.loader.exec_module(bw)

bw.HOME = home
bw.MASTER_FILES = master
bw.COMPANY_DISCOVERY_DIR = discovery
bw.ZHC_ROOT = os.path.join(tmp, "zhc")
bw.WORKSPACE_ROOT = os.path.join(tmp, "ws")
bw.LEGACY_DEPARTMENTS_DIR = os.path.join(tmp, "ws", "departments")
bw._build_state_path = lambda: state_path

CONFIG = {
    "company_name": "Scratch Canary Co",
    "industry": "Professional Services",
    "company_description": "We help owners build a team that runs without them.",
    "tools": "Slack, Notion, Google Workspace",
    "biggest_challenge": "Everything depends on the owner.",
    "departments": {
        "marketing": {"enabled": True},
        "sales": {"enabled": True},
    },
}

def read_state():
    with open(state_path) as f:
        return json.load(f)

def run_build():
    try:
        bw.build_from_config(dict(CONFIG))
    except SystemExit as exc:
        return exc.code
    return 0

PASS = [0]
FAIL = [0]
def ok(msg):
    PASS[0] += 1
    print(f"PASS: {msg}")
def bad(msg):
    FAIL[0] += 1
    print(f"FAIL: {msg}", file=sys.stderr)

with open(transcript, "rb") as f:
    transcript_before = f.read()
state_before = read_state()

code1 = run_build()
state_after = read_state()

ok("first run exits 88 at the decision-coverage gate") if code1 == 88 else bad(
    f"first run exit code {code1!r}, expected 88")

with open(transcript, "rb") as f:
    transcript_after = f.read()
ok("transcript bytes unchanged") if transcript_after == transcript_before else bad(
    "transcript was overwritten by the refused build")

ok("interviewComplete is absent") if "interviewComplete" not in state_after else bad(
    f"interviewComplete was stamped: {state_after.get('interviewComplete')!r}")

ok("buildCompletedAt unchanged") if (
    state_after.get("buildCompletedAt") == state_before.get("buildCompletedAt")
) else bad(f"buildCompletedAt changed: {state_before.get('buildCompletedAt')!r} -> "
           f"{state_after.get('buildCompletedAt')!r}")

ok("buildId unchanged") if state_after.get("buildId") == state_before.get("buildId") \
    else bad(f"buildId changed: {state_before.get('buildId')!r} -> {state_after.get('buildId')!r}")

ok("interview-handoff.md does not exist") if not os.path.exists(
    os.path.join(discovery, "interview-handoff.md")) else bad(
    "interview-handoff.md was written by a refused build")

code2 = run_build()
ok("second run exits 88 again (not 87)") if code2 == 88 else bad(
    f"second run exit code {code2!r}, expected 88")

print(f"test-refused-build-leaves-no-trace: PASS={PASS[0]} FAIL={FAIL[0]}")
sys.exit(1 if FAIL[0] else 0)
PY
PY_EXIT=$?

if [ "$PY_EXIT" -eq 0 ]; then
  good "all refusal-trace guards pass"
else
  bad "refusal-trace guards failed (exit $PY_EXIT)"
fi

echo "=============================================="
echo "test-refused-build-leaves-no-trace: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
