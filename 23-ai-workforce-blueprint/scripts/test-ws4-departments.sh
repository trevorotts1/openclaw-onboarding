#!/usr/bin/env bash
# test-ws4-departments.sh — WS-4 static regression guard.
#
# Proves the two WS-4 department-selection behaviors from a clean checkout
# (no live OpenClaw install required), so a regression is caught on every push:
#
#   1. generate_departments_json() ALWAYS emits the CEO department FIRST,
#      with id `dept-ceo` AND slug `ceo` (the shape the Command Center keys on
#      in autoSeedFromDepartmentsJson / migration 046 / AgentsSidebar hoist),
#      and never double-emits a worker CEO/master-orchestrator column.
#
#   2. Every vertical-pack department in department-naming-map.json carries a
#      base_suggested_roles file that EXISTS in suggested-roles/, so an
#      auto-added industry dept resolves in assert_dept_map_resolves() instead
#      of hard-failing the build. Also asserts apply_vertical_packs() exists,
#      is wired into build_from_config, de-dups across packs, and writes the
#      McKinsey-style industry-org-design research manifest.
#
# Exit 0 on pass, 1 on any failure.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

python3 - "$SKILL_DIR" <<'PY'
import sys, os, json, importlib.util, tempfile

SKILL = sys.argv[1]
SCRIPTS = os.path.join(SKILL, "scripts")
ROLES_DIR = os.path.join(SKILL, "suggested-roles")
MAP = os.path.join(SKILL, "department-naming-map.json")

spec = importlib.util.spec_from_file_location("bw", os.path.join(SCRIPTS, "build-workforce.py"))
bw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bw)

fail = 0
def check(cond, msg):
    global fail
    if cond:
        print(f"  ✓ {msg}")
    else:
        print(f"  ✗ {msg}")
        fail = 1

# ---- 1. CEO column first ----------------------------------------------------
floor = bw.load_canonical_floor()
djson = bw.generate_departments_json({cid: info.copy() for cid, info in floor.items()})
check(len(djson) > 0 and djson[0].get("id") == "dept-ceo" and djson[0].get("slug") == "ceo",
      "generate_departments_json emits CEO (id=dept-ceo, slug=ceo) as the FIRST column")
worker_ceo = [e for e in djson[1:] if e.get("id") in ("dept-ceo", "dept-master-orchestrator")]
check(not worker_ceo, "no duplicate CEO/master-orchestrator worker column")

# ---- 2. vertical-pack base_suggested_roles all resolve ----------------------
data = json.load(open(MAP))
missing = []
total = 0
for pack in (data.get("vertical_packs", {}) or {}).values():
    for dept in pack.get("auto_add_departments", []) or []:
        total += 1
        base = dept.get("base_suggested_roles", "")
        if not base or not os.path.isfile(os.path.join(ROLES_DIR, base)):
            missing.append((dept.get("id"), base))
check(not missing, f"all {total} vertical-pack depts carry a base_suggested_roles file that exists (missing: {missing})")

# every vertical-pack dept id resolves in the dept->roles map
m = bw.build_dept_to_suggested_roles()
unresolved = []
for pack in (data.get("vertical_packs", {}) or {}).values():
    for dept in pack.get("auto_add_departments", []) or []:
        did = dept.get("id")
        f = m.get(did)
        if not f or not os.path.isfile(os.path.join(ROLES_DIR, f)):
            unresolved.append(did)
check(not unresolved, f"build_dept_to_suggested_roles resolves every vertical-pack dept (unresolved: {unresolved})")

# ---- 3. apply_vertical_packs exists, de-dups, writes research manifest ------
check(hasattr(bw, "apply_vertical_packs"), "apply_vertical_packs() exists")
src = open(os.path.join(SCRIPTS, "build-workforce.py")).read()
check("selected_departments = apply_vertical_packs(" in src,
      "apply_vertical_packs is wired into build_from_config")

bw.DEPARTMENTS_DIR = tempfile.mkdtemp()
tmpstate = os.path.join(tempfile.mkdtemp(), "state.json")
bw._build_state_path = lambda: tmpstate
sel = {cid: info.copy() for cid, info in floor.items()}
before = set(sel)
# Signal triggering BOTH personal-pro-dev and content-creator (shared podcast/community)
ans = {"company_name": "WS4 Test", "industry": "creator and coach",
       "company_description": "youtube channel host, mastermind, influencer, podcast host",
       "biggest_challenge": "", "tools": ""}
sel = bw.apply_vertical_packs(sel, ans)
from collections import Counter
dupes = [k for k, v in Counter(sel.keys()).items() if v > 1]
check(not dupes, f"no duplicate dept keys after apply_vertical_packs (dupes: {dupes})")
check(before.issubset(set(sel)), "canonical floor preserved (no canonical dept lost)")
rec = json.load(open(tmpstate)).get("verticalPacks", {})
skipped_ids = {d["id"] for d in rec.get("skippedDuplicates", [])}
check("podcast" in skipped_ids or "community-management" in skipped_ids,
      "cross-pack duplicate (podcast / community-management) is de-duped")
man = rec.get("researchManifest", "")
ok_man = bool(man) and os.path.isfile(man)
if ok_man:
    mj = json.load(open(man))
    ok_man = mj.get("researchRole") == "research/industry-analysis-specialist-mckinsey-style"
check(ok_man, "industry-org-design research manifest written + cites the McKinsey-style research role")

# ---- 4. assert_dept_map_resolves does not hard-fail on the augmented set ----
bw.MASTER_FILES = ""
try:
    bw.assert_dept_map_resolves(list(sel.keys()))
    check(True, "assert_dept_map_resolves passes for canonical floor + vertical depts")
except SystemExit:
    check(False, "assert_dept_map_resolves passes for canonical floor + vertical depts")

print("")
if fail:
    print("WS-4 department checks: FAIL")
    sys.exit(1)
print("WS-4 department checks: PASS")
PY
rc=$?
exit $rc
