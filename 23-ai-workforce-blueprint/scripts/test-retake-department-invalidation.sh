#!/usr/bin/env bash
# test-retake-department-invalidation.sh — U053 interview re-take invalidation.
#
# Proves the U053 fix (re-taking the interview leaves deselected departments
# orphaned forever — no garbage collection):
#
#   T1. A department a PRIOR interview selected but THIS run does not is detected
#       as an orphan and a durable proposal artifact is written naming it.
#   T2. Nothing is deleted: the U109 chosen-list merge still carries the orphan
#       forward (its safety guarantee is untouched) — removal is proposal-only.
#   T3. The proposal names the EXACT confirmation command (record-dept-decision.sh
#       --decision no <slug>) — removal requires explicit operator confirmation.
#   T4. A department still selected this run is NOT flagged (no false positive).
#   T5. A department already explicitly DECLINED is NOT flagged (a decline is the
#       operator's confirmation, already honored by the merge).
#   T6. The CEO column (prepended by the artifact writer, never in the selection)
#       is NEVER flagged as an orphan.
#   T7. A re-take with the SAME selection produces NO orphans (idempotent, no
#       spurious proposal).
#
# Exit 0 = all tests pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

python3 - "$SKILL_DIR" <<'PY'
import importlib.util, os, sys, json, tempfile

SKILL = sys.argv[1]
SCRIPTS = os.path.join(SKILL, "scripts")
spec = importlib.util.spec_from_file_location("bw", os.path.join(SCRIPTS, "build-workforce.py"))
bw = importlib.util.module_from_spec(spec); spec.loader.exec_module(bw)

PASS = 0; FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  PASS: {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL: {m}")

# Isolate build-state to a temp file (same pattern as test-chosen-departments-artifact.sh).
tmp = tempfile.mkdtemp()
state = os.path.join(tmp, "state.json")
bw._build_state_path = lambda: state
def read_state():
    try:
        with open(state) as f: return json.load(f)
    except Exception: return {}

comp = os.path.join(tmp, "acme")
os.makedirs(comp)
PROPOSAL = os.path.join(comp, "departments-invalidation-proposal.json")
ART = os.path.join(comp, "departments.json")

full = {
    "marketing":        {"name": "Marketing",         "emoji": "\U0001F4E3", "head": "CMO"},
    "billing-finance":  {"name": "Billing & Finance", "emoji": "\U0001F4B0", "head": "CFO"},
    "publishing-studio":{"name": "Publishing Studio", "emoji": "\U0001F4DA", "head": "Head of Publishing"},
}
reduced = {
    "marketing":        {"name": "Marketing",         "emoji": "\U0001F4E3", "head": "CMO"},
    "billing-finance":  {"name": "Billing & Finance", "emoji": "\U0001F4B0", "head": "CFO"},
}

def reset_state():
    if os.path.exists(state): os.remove(state)
    for f in (ART, PROPOSAL):
        if os.path.exists(f): os.remove(f)

def art_slugs():
    return [e.get("slug") for e in json.load(open(ART))] if os.path.isfile(ART) else []

print("== T1: a deselected department is detected as an orphan + proposal written ==")
reset_state()
bw.write_chosen_departments_artifact(full, company_dir=comp, source="first-interview")
bw.write_chosen_departments_artifact(reduced, company_dir=comp, source="retake")
if os.path.isfile(PROPOSAL):
    prop = json.load(open(PROPOSAL))
    ok("proposal artifact written on re-take")
    ok("publishing-studio flagged as orphan") if "publishing-studio" in prop.get("orphans", []) else bad(f"orphans wrong: {prop.get('orphans')}")
else:
    bad("proposal artifact NOT written on re-take")

print("== T2: nothing deleted — the merge still carries the orphan forward ==")
slugs = art_slugs()
ok("publishing-studio still present in departments.json (merge preserved it)") if "publishing-studio" in slugs else bad(f"orphan was deleted: {slugs}")

print("== T3: proposal names the exact confirmation command ==")
prop = json.load(open(PROPOSAL)) if os.path.isfile(PROPOSAL) else {}
ok("confirmCommand present") if "record-dept-decision.sh" in prop.get("confirmCommand", "") and "--decision no" in prop.get("confirmCommand", "") else bad(f"confirmCommand wrong: {prop.get('confirmCommand')}")

print("== T4: a still-selected department is NOT flagged ==")
ok("marketing not flagged") if "marketing" not in prop.get("orphans", []) else bad("marketing falsely flagged")
ok("billing-finance not flagged") if "billing-finance" not in prop.get("orphans", []) else bad("billing-finance falsely flagged")

print("== T5: an already-declined department is NOT flagged ==")
reset_state()
bw.write_chosen_departments_artifact(full, company_dir=comp, source="first-interview")
# Record a provenance-gated decline for publishing-studio (the operator's confirmation).
st = read_state()
st.setdefault("canonicalReconciliation", {}).setdefault("decisions", {})["publishing-studio"] = {
    "decision": "no", "source": "interview", "decidedAt": "2026-07-23T00:00:00", "decidedBy": "owner",
}
with open(state, "w") as f: json.dump(st, f)
bw.write_chosen_departments_artifact(reduced, company_dir=comp, source="retake")
prop5 = json.load(open(PROPOSAL)) if os.path.isfile(PROPOSAL) else {}
ok("declined publishing-studio not flagged as orphan") if "publishing-studio" not in prop5.get("orphans", []) else bad(f"declined dept flagged: {prop5.get('orphans')}")

print("== T6: the CEO column is NEVER flagged ==")
reset_state()
bw.write_chosen_departments_artifact(full, company_dir=comp, source="first-interview")
bw.write_chosen_departments_artifact(reduced, company_dir=comp, source="retake")
prop6 = json.load(open(PROPOSAL)) if os.path.isfile(PROPOSAL) else {}
ceo_flagged = [o for o in prop6.get("orphans", []) if o in ("ceo", "dept-ceo", "master-orchestrator")]
ok("CEO column not flagged as orphan") if not ceo_flagged else bad(f"CEO flagged: {ceo_flagged}")

print("== T7: a re-take with the SAME selection produces NO orphans ==")
reset_state()
bw.write_chosen_departments_artifact(full, company_dir=comp, source="first-interview")
bw.write_chosen_departments_artifact(full, company_dir=comp, source="retake-same")
prop7 = json.load(open(PROPOSAL)) if os.path.isfile(PROPOSAL) else {}
ok("no orphans on identical re-take") if not prop7.get("orphans") else bad(f"spurious orphans: {prop7.get('orphans')}")

print()
print("===================================================")
print(f"  test-retake-department-invalidation: PASS={PASS} FAIL={FAIL}")
print("===================================================")
sys.exit(1 if FAIL else 0)
PY
