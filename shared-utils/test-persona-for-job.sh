#!/usr/bin/env bash
# =============================================================================
# test-persona-for-job.sh — contract tests for the shared persona entry point.
#
#   1. NO-NAKED contract: across every reachable branch (normal, mechanical,
#      selector-null, selector-missing, client-choice) the returned selection is
#      GOVERNED — a usable persona_id OR no_persona_required + governance persona.
#   2. MULTI-PERSONA: persona_for_jobs resolves N slots (the tone-core 4-slot
#      blend), client-named slots stay FINAL, N/A slots route through the selector,
#      and no slot comes back naked.
#
# stdlib python only; uses the PERSONA_FOR_JOB_FIXTURE escape hatch so NO OpenClaw
# install / DB / network is required. Exit 0 = all pass.
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"
fail=0
pass() { printf '  [PASS] %s\n' "$1"; }
bad()  { printf '  [FAIL] %s\n' "$1"; fail=1; }

echo "== 1. never-naked consumer contract (module self-test) =="
if "$PY" "$HERE/persona_for_job.py" --self-test; then
  pass "persona_for_job --self-test"
else
  bad "persona_for_job --self-test"
fi

echo "== 2. multi-persona / multi-slot resolver (tone-core 4-slot) =="
"$PY" - "$HERE" <<'PYEOF'
import json, os, sys
sys.path.insert(0, sys.argv[1])
import persona_for_job as P

rc = 0
def check(label, cond):
    global rc
    print("  [%s] %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        rc = 1

def governed(sel):
    if sel.get("persona_id"):
        return True
    return sel.get("no_persona_required") and sel.get("governance_persona_id")

# Slot 1 = client-named (FINAL). Slots 2-4 = N/A -> route through selector.
# Fixture makes the selector return a real persona for the N/A slots.
os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
    {"persona_id": "covey-7-habits", "persona_name": "Covey", "score": 0.8})
jobs = [
    {"job_text": "warm mentor tone for a leadership book",
     "department": "book", "client_persona_id": "td-jakes-instinct",
     "persona_source": "client-choice"},
    {"job_text": "analytical clarity tone", "department": "book"},
    {"job_text": "high-energy motivational tone", "department": "book"},
    {"job_text": "story-driven intimate tone", "department": "book"},
]
sels = P.persona_for_jobs(jobs)
check("4 slots resolved", len(sels) == 4)
check("no naked slot", all(governed(s) for s in sels))
check("client-named slot #1 is FINAL (verbatim, not overridden)",
      sels[0]["persona_id"] == "td-jakes-instinct" and sels[0]["source"] == "client-choice")
check("N/A slots routed through selector",
      all(sels[i]["source"] == "selector" for i in (1, 2, 3)))
check("client-named slot never touched the selector fixture value",
      sels[0]["persona_id"] != "covey-7-habits")
os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)
sys.exit(rc)
PYEOF
if [ $? -eq 0 ]; then pass "persona_for_jobs multi-slot"; else bad "persona_for_jobs multi-slot"; fi

echo
if [ "$fail" -eq 0 ]; then
  echo "== persona_for_job contract tests: ALL PASSED =="
  exit 0
fi
echo "== persona_for_job contract tests: FAILED =="
exit 1
