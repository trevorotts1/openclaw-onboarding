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
#   T8. THE DOWNSTREAM READER: department-floor.evaluate_floor() — the single tool
#       every QC gate already consumes — surfaces the chosen list
#       (chosen_departments + chosen_departments_source), preferring build-state,
#       falling back to the on-disk artifact, NEVER fabricating one, and never
#       changing the floor rc contract (0/3/7).
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

print("== T8: department-floor READS the durable chosen-list (the downstream reader) ==")
# ENFORCEMENT, not description: the chosen list must be readable by the tool every
# downstream gate already consumes (department-floor.py --json), or "durable
# artifact" is a file nobody reads. The floor verdict must surface it WITHOUT
# changing the floor rc contract, and must NEVER fabricate one.
dfspec = importlib.util.spec_from_file_location("df", os.path.join(SCRIPTS, "department-floor.py"))
df = importlib.util.module_from_spec(dfspec); dfspec.loader.exec_module(df)

from pathlib import Path   # evaluate_floor takes a Path (same shape every real caller passes)

dd = Path(comp) / "departments"
os.makedirs(dd, exist_ok=True)
for slug in ("marketing", "billing-finance"):
    os.makedirs(dd / slug / "01-a-role", exist_ok=True)

bs_with = {"canonicalReconciliation": {"chosenDepartments": {"slugs": ["ceo", "marketing"], "count": 2}}}
v = df.evaluate_floor(departments_dir=dd, build_state=bs_with, core_answers={})
ok("floor verdict carries chosen_departments") if v.get("chosen_departments") == ["ceo", "marketing"] else bad(f"chosen_departments wrong: {v.get('chosen_departments')}")
ok("source == build-state (authoritative)") if v.get("chosen_departments_source") == "build-state" else bad(f"source wrong: {v.get('chosen_departments_source')}")

# Artifact fallback: no build-state record -> read <company>/departments.json on disk.
v2 = df.evaluate_floor(departments_dir=dd, build_state={}, core_answers={})
ok("falls back to the on-disk artifact") if v2.get("chosen_departments") == art_slugs and art_slugs else bad(f"artifact fallback wrong: {v2.get('chosen_departments')}")
ok("source == artifact") if v2.get("chosen_departments_source") == "artifact" else bad(f"source wrong: {v2.get('chosen_departments_source')}")

# Never fabricated: no build-state record AND no artifact -> [] / "none".
bare = Path(tmp) / "bare" / "departments"
os.makedirs(bare / "marketing" / "01-a-role", exist_ok=True)
v3 = df.evaluate_floor(departments_dir=bare, build_state={}, core_answers={})
ok("no chosen list -> [] (never fabricated)") if v3.get("chosen_departments") == [] else bad(f"fabricated: {v3.get('chosen_departments')}")
ok("no chosen list -> source none") if v3.get("chosen_departments_source") == "none" else bad(f"source wrong: {v3.get('chosen_departments_source')}")
# The chosen-list read must NOT touch the floor rc contract (0/3/7).
ok("floor rc contract unchanged (0/3/7)") if v.get("rc") in (0, 3, 7) and v3.get("rc") in (0, 3, 7) else bad(f"floor rc contract broken: {v.get('rc')}/{v3.get('rc')}")

print()
print("===================================================")
print(f"  test-chosen-departments-artifact: PASS={PASS} FAIL={FAIL}")
print("===================================================")
sys.exit(1 if FAIL else 0)
PY
