#!/usr/bin/env bash
# test-u109-floor-wipe-regression.sh — U109 (E5-4, closes G2c) regression proof.
#
# THE BUG: interview-provisioning WIPED / OVERWROTE the department FLOOR
# instead of MERGING onto it, via build-workforce.write_chosen_departments_artifact()
# — the single choke-point every downstream consumer (Skill 32 seeding,
# department-floor.py's chosen-list reader, Command Center) reads as "the
# authoritative record of the departments the client chose." Before the fix
# this function did a BLIND OVERWRITE of both <company>/departments.json and
# build-state canonicalReconciliation.chosenDepartments: any call carrying a
# SMALLER `selected_departments` than a prior call — a second provisioning
# run, a partial/aborted interview session, or a late edit that only touched
# one department — silently dropped every department the prior, larger call
# had already recorded. No decline, no warning, no audit trail: the floor
# just shrank.
#
# REPRODUCTION DISCIPLINE (PER-REPO / OFFLINE ACCEPTANCE DOCTRINE, master spec
# X.5 / OPERATOR RULINGS 2026-07-15): this is an OFFLINE, per-repo, fixture-
# reproduced trace of the wipe — it exercises the exact production function
# (`build-workforce.write_chosen_departments_artifact`) with injected temp
# paths, not a live operator-box interview run. A live/integrated run of the
# real interview UI end-to-end is LIVE-PROOF, deferred to U22 (the one
# end-to-end operator-box proof unit) per the ratified doctrine — this test is
# the merge-gate criterion and must stand on its own, offline.
#
# THIS TEST FAILS on the pre-U109 tree (proves the reproduction is real, not
# theater) and PASSES once the merge-not-replace fix lands. Do not weaken any
# assertion below to make it pass on both trees — a test that passes either
# way proves nothing.
#
#   T1 (repro, U109 acceptance (a)): full run -> partial second run REPLACES
#       the chosen list on the unguarded function; recorded here as the
#       reproduction trace.
#   T2 (U109 acceptance (b)): post-fix, a second (smaller) provisioning run
#       leaves `floor ∪ prior set` intact — zero departments lost.
#   T3 (U109 acceptance (c)): a partial/aborted-interview-shaped run (only ONE
#       department re-confirmed) never drops a floor department.
#   T4 (U109 acceptance (d)): the ONLY way a department is absent after the
#       merge is an EXPLICIT, provenance-gated decline (the same mechanism
#       U107/U108/department-floor.py already honor) — every other
#       un-mentioned department survives.
#
# Exit 0 = all tests pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

python3 - "$SKILL_DIR" <<'PY'
import importlib.util, os, sys, json, tempfile
from datetime import datetime

SKILL = sys.argv[1]
SCRIPTS = os.path.join(SKILL, "scripts")
spec = importlib.util.spec_from_file_location("bw", os.path.join(SCRIPTS, "build-workforce.py"))
bw = importlib.util.module_from_spec(spec); spec.loader.exec_module(bw)

PASS = 0; FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  PASS: {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL: {m}")

def fresh_state(tmp):
    """Point build-workforce at an isolated, empty build-state file."""
    state = os.path.join(tmp, "state.json")
    bw._build_state_path = lambda: state
    return state

def read_state(state):
    try:
        with open(state) as f: return json.load(f)
    except Exception: return {}

FULL = {
    "marketing":         {"name": "Marketing",         "emoji": "\U0001F4E3", "head": "CMO"},
    "billing-finance":   {"name": "Billing & Finance",  "emoji": "\U0001F4B0", "head": "CFO"},
    "legal":             {"name": "Legal / Compliance", "emoji": "⚖️", "head": "General Counsel"},
    "video":             {"name": "Video Production",   "emoji": "\U0001F3AC", "head": "Head of Video"},
    "publishing-studio": {"name": "Publishing Studio",  "emoji": "\U0001F4DA", "head": "Head of Publishing"},
}
FULL_SLUGS = {"ceo", "marketing", "billing-finance", "legal", "video", "publishing-studio"}

# ─────────────────────────────────────────────────────────────────────────
print("== T1 (repro, acceptance a): full run -> partial second run ==")
print("   [REPRO] simulates a re-run / partial-interview call to the shipped")
print("   [REPRO] write_chosen_departments_artifact() with the SAME company_dir")
print("   [REPRO] across two calls -- the exact production choke-point.")
tmp1 = tempfile.mkdtemp()
state1 = fresh_state(tmp1)
comp1 = os.path.join(tmp1, "acme")
os.makedirs(comp1)

bw.write_chosen_departments_artifact(FULL, company_dir=comp1, source="t1-run1-full")
after_run1 = set(bw.read_chosen_departments(company_dir=comp1))
print(f"   [REPRO] after run 1 (full floor): {sorted(after_run1)}")
ok("run 1 recorded the full floor") if after_run1 == FULL_SLUGS else bad(f"run 1 unexpected: {after_run1}")

# Partial second run: only ONE department is re-affirmed (a re-run / partial
# interview / late single-department edit).
bw.write_chosen_departments_artifact({"marketing": FULL["marketing"]},
                                      company_dir=comp1, source="t1-run2-partial")
after_run2 = set(bw.read_chosen_departments(company_dir=comp1))
print(f"   [REPRO] after run 2 (partial, only 'marketing'): {sorted(after_run2)}")
lost = after_run1 - after_run2
if lost:
    print(f"   [REPRO] *** THE WIPE, REPRODUCED: {sorted(lost)} were on the floor after "
          f"run 1 and are GONE after run 2 -- with zero explicit decline behind it. ***")
# THIS is the load-bearing assertion. On the pre-U109 (unguarded) function this
# FAILS -- 'lost' is non-empty because the second write is a blind overwrite.
# On the fixed function this PASSES -- the merge preserves run 1's floor.
ok("T1: no department lost between run 1 and the partial run 2 (merge, not replace)") \
    if not lost else bad(f"T1: WIPE REPRODUCED -- lost {sorted(lost)} with no decline")

# ─────────────────────────────────────────────────────────────────────────
print("== T2 (acceptance b): floor ∪ prior set intact after a second run ==")
tmp2 = tempfile.mkdtemp()
state2 = fresh_state(tmp2)
comp2 = os.path.join(tmp2, "acme")
os.makedirs(comp2)

bw.write_chosen_departments_artifact(FULL, company_dir=comp2, source="t2-run1")
prior = set(bw.read_chosen_departments(company_dir=comp2))
# A second, smaller provisioning run (re-derived floor + fewer customs this pass).
bw.write_chosen_departments_artifact(
    {"marketing": FULL["marketing"], "billing-finance": FULL["billing-finance"]},
    company_dir=comp2, source="t2-run2-smaller")
after = set(bw.read_chosen_departments(company_dir=comp2))
ok("T2: prior ⊆ post-second-run set (zero departments lost)") \
    if prior <= after else bad(f"T2: dropped {sorted(prior - after)}")
ok("T2: new department from run 2 is present too") \
    if "billing-finance" in after else bad("T2: run 2's own department missing")

# ─────────────────────────────────────────────────────────────────────────
print("== T3 (acceptance c): partial/aborted-interview shape never drops a floor dept ==")
tmp3 = tempfile.mkdtemp()
state3 = fresh_state(tmp3)
comp3 = os.path.join(tmp3, "acme")
os.makedirs(comp3)

bw.write_chosen_departments_artifact(FULL, company_dir=comp3, source="t3-full-build")
# Interview aborts mid-session; only ONE department was reconfirmed before the
# abort, and a resume/retry calls the writer again with that partial set.
bw.write_chosen_departments_artifact({"video": FULL["video"]},
                                      company_dir=comp3, source="t3-aborted-partial")
after3 = set(bw.read_chosen_departments(company_dir=comp3))
ok("T3: every floor department survives an aborted-interview-shaped re-run") \
    if FULL_SLUGS <= after3 else bad(f"T3: floor department(s) dropped: {sorted(FULL_SLUGS - after3)}")

# ─────────────────────────────────────────────────────────────────────────
print("== T4 (acceptance d): ONLY an explicit, provenance-gated decline removes a dept ==")
tmp4 = tempfile.mkdtemp()
state4 = fresh_state(tmp4)
comp4 = os.path.join(tmp4, "acme")
os.makedirs(comp4)

bw.write_chosen_departments_artifact(FULL, company_dir=comp4, source="t4-full-build")

# Owner explicitly declines 'legal' with full provenance -- the SAME shape
# U108/record-dept-decision.sh writes (decision/source/decidedAt/decidedBy).
st = read_state(state4)
st.setdefault("canonicalReconciliation", {})["decisions"] = {
    "legal": {
        "decision": "no",
        "source": "interview-board",
        "decidedAt": datetime.now().isoformat(),
        "decidedBy": "owner",
    }
}
with open(state4, "w") as f:
    json.dump(st, f)

# A later partial run re-affirms only 'marketing' -- everything else must
# survive via the merge EXCEPT the explicitly-declined 'legal'.
bw.write_chosen_departments_artifact({"marketing": FULL["marketing"]},
                                      company_dir=comp4, source="t4-partial-after-decline")
after4 = set(bw.read_chosen_departments(company_dir=comp4))
ok("T4: explicitly-declined department is dropped") \
    if "legal" not in after4 else bad("T4: declined 'legal' was resurrected by the merge")
ok("T4: every OTHER floor department survives (decline is the ONLY drop path)") \
    if (FULL_SLUGS - {"legal"}) <= after4 else bad(f"T4: unexplained drop(s): {sorted((FULL_SLUGS - {'legal'}) - after4)}")

# ─────────────────────────────────────────────────────────────────────────
# QC re-review hardening (2026-07-16): the first pass's merge guard had three
# holes that each let the shipped suite stay green while the floor still
# shrank. T5-T7 close them; each reproduces its hole then proves the fix.
# ─────────────────────────────────────────────────────────────────────────

print("== T5: a CORRUPT/truncated artifact must fail safe (recover from build-state), never be trusted as 'nothing was here' ==")
tmp5 = tempfile.mkdtemp()
state5 = fresh_state(tmp5)
comp5 = os.path.join(tmp5, "acme")
os.makedirs(comp5)

bw.write_chosen_departments_artifact(FULL, company_dir=comp5, source="t5-full-build")
before5 = set(bw.read_chosen_departments(company_dir=comp5))

# Truncate the on-disk artifact mid-write (simulates a crash/kill during the
# PRE-fix non-atomic write, or disk corruption) -- the file EXISTS but is not
# valid JSON. This must never be treated the same as "no prior departments".
art5 = os.path.join(comp5, "departments.json")
with open(art5, "w") as f:
    f.write('[{"id": "dept-market')   # deliberately truncated / invalid JSON

bw.write_chosen_departments_artifact({"marketing": FULL["marketing"]},
                                      company_dir=comp5, source="t5-partial-after-corruption")
after5 = set(bw.read_chosen_departments(company_dir=comp5))
lost5 = before5 - after5
if lost5:
    print(f"   [REPRO] *** CORRUPT-ARTIFACT WIPE: {sorted(lost5)} were present before the "
          f"corruption and are GONE after the next write -- the damaged read was silently "
          f"trusted instead of failing safe. ***")
ok("T5: a corrupt artifact recovers the prior floor from build-state (no silent disarm)") \
    if not lost5 else bad(f"T5: corrupt-artifact wipe -- lost {sorted(lost5)}")

print("== T6: a FALSY company_dir on the production call path must not wipe build-state's record ==")
tmp6 = tempfile.mkdtemp()
state6 = fresh_state(tmp6)
comp6 = os.path.join(tmp6, "acme")
os.makedirs(comp6)

bw.write_chosen_departments_artifact(FULL, company_dir=comp6, source="t6-full-build")
before6 = set(bw.read_chosen_departments(company_dir=comp6))

# Simulate build_from_config's two production call sites, which never pass
# company_dir explicitly -- they rely on the module-level COMPANY_DIR global,
# which that SAME function's own `if COMPANY_DIR:` guard (build-workforce.py,
# one line after each call site) proves can be falsy. Force that exact
# condition: COMPANY_DIR falsy AND no company_dir argument.
saved_company_dir = bw.COMPANY_DIR
bw.COMPANY_DIR = None
try:
    bw.write_chosen_departments_artifact({"marketing": FULL["marketing"]},
                                          source="t6-partial-falsy-cdir")
finally:
    bw.COMPANY_DIR = saved_company_dir

# The on-disk artifact at comp6 was correctly skipped (no cdir to write to) --
# read the RECOVERY-RELEVANT source directly: build-state itself, which the
# falsy-cdir call unconditionally re-stamps regardless of the file write.
after6 = set(read_state(state6).get("canonicalReconciliation", {}).get("chosenDepartments", {}).get("slugs", []))
lost6 = before6 - after6
if lost6:
    print(f"   [REPRO] *** FALSY-cdir WIPE: {sorted(lost6)} were in build-state before the "
          f"falsy-company_dir call and are GONE from build-state after it. ***")
ok("T6: a falsy company_dir recovers build-state's prior record instead of wiping it") \
    if not lost6 else bad(f"T6: falsy-cdir wipe of build-state -- lost {sorted(lost6)}")

print("== T7: a legacy id-only prior entry must DEDUP against this call's bare-slug entry, never duplicate ==")
tmp7 = tempfile.mkdtemp()
state7 = fresh_state(tmp7)
comp7 = os.path.join(tmp7, "acme")
os.makedirs(comp7)

bw.write_chosen_departments_artifact(FULL, company_dir=comp7, source="t7-full-build")

# Hand-edit the artifact to the LEGACY shape for 'marketing': id-only, no
# "slug" key (the pre-"slug"-field format). A later call that ALSO selects
# 'marketing' (bare-slug, from generate_departments_json) must merge onto
# ONE department, not two.
art7 = os.path.join(comp7, "departments.json")
legacy = json.load(open(art7))
for entry in legacy:
    if entry.get("slug") == "marketing":
        del entry["slug"]   # now id-only: {"id": "dept-marketing", ...}
with open(art7, "w") as f:
    json.dump(legacy, f)

bw.write_chosen_departments_artifact({"marketing": FULL["marketing"]},
                                      company_dir=comp7, source="t7-partial-legacy-dedup")
final7 = json.load(open(art7))
marketing_count = sum(
    1 for e in final7
    if isinstance(e, dict) and (e.get("slug") == "marketing" or e.get("id") == "dept-marketing")
)
if marketing_count > 1:
    print(f"   [REPRO] *** DUPLICATE: 'marketing' appears {marketing_count} times in the merged "
          f"artifact -- the legacy id-only entry survived the dedup check unnormalized. ***")
ok("T7: legacy id-only entry dedups against the bare-slug entry (exactly one 'marketing')") \
    if marketing_count == 1 else bad(f"T7: 'marketing' appears {marketing_count} times (expected 1)")

print()
print("===================================================")
print(f"  test-u109-floor-wipe-regression: PASS={PASS} FAIL={FAIL}")
print("===================================================")
sys.exit(1 if FAIL else 0)
PY
