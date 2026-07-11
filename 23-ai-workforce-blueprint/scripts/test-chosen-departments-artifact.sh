#!/usr/bin/env bash
# test-chosen-departments-artifact.sh — C7 durable "chosen-list" artifact + reader.
#
# Proves the C7 fix (no durable chosen-list artifact -> downstream cannot
# authoritatively read the departments the client chose):
#
#   T1. write_chosen_departments_artifact() writes <company>/departments.json AND
#       records canonicalReconciliation.chosenDepartments {slugs,count,source} in
#       build-state.
#   T2. read_chosen_departments() prefers the build-state record (authoritative).
#   T3. read_chosen_departments() falls back to the departments.json artifact when
#       the build-state record is absent.
#   T4. read_chosen_departments() returns [] when neither source exists (never
#       fabricates a floor).
#   T5. Idempotent re-write yields the same chosen set.
#   T6. The build-state stamp is NON-DESTRUCTIVE: pre-existing
#       canonicalReconciliation fields (e.g. decisions) are preserved.
#   T7. Slugs are CEO-first, canonical, and deduped (same contract as the CC-facing
#       departments.json).
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

# Isolate build-state to a temp file (same pattern as test-reconciliation-engine.sh).
tmp = tempfile.mkdtemp()
state = os.path.join(tmp, "state.json")
bw._build_state_path = lambda: state
def read_state():
    try:
        with open(state) as f: return json.load(f)
    except Exception: return {}

comp = os.path.join(tmp, "acme")
os.makedirs(comp)
sel = {
    "marketing":        {"name": "Marketing",        "emoji": "\U0001F4E3", "head": "CMO"},
    "billing-finance":  {"name": "Billing & Finance","emoji": "\U0001F4B0", "head": "CFO"},
    "publishing-studio":{"name": "Publishing Studio", "emoji": "\U0001F4DA", "head": "Head of Publishing"},
}

print("== T1: write artifact + build-state record ==")
if os.path.exists(state):
    os.remove(state)
written = bw.write_chosen_departments_artifact(sel, company_dir=comp, source="test")
art_path = os.path.join(comp, "departments.json")
ok("artifact file written") if os.path.isfile(art_path) else bad("artifact file NOT written")
art = json.load(open(art_path)) if os.path.isfile(art_path) else []
art_slugs = [e.get("slug") for e in art]
st = read_state()
cd = st.get("canonicalReconciliation", {}).get("chosenDepartments", {})
ok("build-state chosenDepartments recorded") if cd.get("slugs") else bad("build-state chosenDepartments MISSING")
ok(f"count == {cd.get('count')} matches slug list") if cd.get("count") == len(cd.get("slugs", [])) else bad("count mismatch")
ok("source recorded == test") if cd.get("source") == "test" else bad(f"source wrong: {cd.get('source')}")
ok("artifact slugs == build-state slugs") if art_slugs == cd.get("slugs") else bad(f"slug mismatch {art_slugs} != {cd.get('slugs')}")

print("== T2: reader prefers build-state ==")
r = bw.read_chosen_departments(company_dir=comp)
ok("read from build-state returns chosen slugs") if r == cd.get("slugs") else bad(f"reader wrong: {r}")

print("== T3: reader falls back to artifact when build-state absent ==")
r2 = bw.read_chosen_departments(build_state={}, company_dir=comp)
ok("read falls back to departments.json artifact") if r2 == art_slugs and r2 else bad(f"fallback wrong: {r2}")

print("== T4: reader returns [] when neither source exists ==")
r3 = bw.read_chosen_departments(build_state={}, company_dir=os.path.join(tmp, "nope"))
ok("empty -> [] (never fabricates)") if r3 == [] else bad(f"expected [], got {r3}")

print("== T5: idempotent re-write ==")
bw.write_chosen_departments_artifact(sel, company_dir=comp, source="test2")
cd2 = read_state().get("canonicalReconciliation", {}).get("chosenDepartments", {})
ok("re-write yields identical chosen set") if cd2.get("slugs") == cd.get("slugs") else bad("re-write changed slug set")

print("== T6: build-state stamp is non-destructive ==")
# Seed a build-state with a pre-existing canonicalReconciliation.decisions block.
with open(state, "w") as f:
    json.dump({"canonicalReconciliation": {"decisions": {"legal": {"decision": "no"}},
                                           "floorSize": 22}}, f)
bw.write_chosen_departments_artifact(sel, company_dir=comp, source="test3")
recon = read_state().get("canonicalReconciliation", {})
ok("pre-existing decisions preserved") if recon.get("decisions", {}).get("legal", {}).get("decision") == "no" else bad("decisions clobbered")
ok("floorSize preserved") if recon.get("floorSize") == 22 else bad("floorSize clobbered")
ok("chosenDepartments added alongside") if recon.get("chosenDepartments", {}).get("slugs") else bad("chosenDepartments not added")

print("== T7: slugs are CEO-first, canonical, deduped ==")
slugs = cd.get("slugs", [])
ok("CEO column first") if slugs and slugs[0] == "ceo" else bad(f"CEO not first: {slugs[:1]}")
ok("no duplicate slugs") if len(slugs) == len(set(slugs)) else bad("duplicate slugs present")
ok("client customs preserved (publishing-studio present)") if "publishing-studio" in slugs else bad("custom dept dropped")

print()
print("===================================================")
print(f"  test-chosen-departments-artifact: PASS={PASS} FAIL={FAIL}")
print("===================================================")
sys.exit(1 if FAIL else 0)
PY
