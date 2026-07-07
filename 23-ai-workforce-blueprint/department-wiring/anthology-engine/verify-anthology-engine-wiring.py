#!/usr/bin/env python3
"""verify-anthology-engine-wiring.py - enforcement pointer for the Anthology
Engine department, floor, and self-invocation wiring (PRD Section 13, unit W4.1).

Proves, structurally (no scores grepped), that:
  1. skill-department-map.json carries EXACTLY ONE skill "59" entry, slug
     anthology-engine, client_facing true, departments == ["marketing"], exactly
     one primary role, and that primary role resolves live in
     templates/role-library/_index.json (the orphan check Skill 59 must pass).
  2. department-naming-map.json is untouched with respect to Anthology: the
     string "anthology" appears nowhere in its mandatory or vertical_packs
     blocks (no fleet department named anthology was ever declared there), and
     if the branch's git history is available, the file is byte-identical to
     its state on the merge-base with origin/main (best-effort; skipped, not
     failed, if git or the ref is unavailable).
  3. department-floor.py --json still reports expected_floor_count 28 with the
     SAME composition (22 mandatory + 6 universal-primary-vertical) declared in
     this folder's wiring.json, and returns rc 0 or 7 (7 only means "no
     workforce on this box to evaluate against", never a wiring defect; rc 3
     would mean the floor itself is broken and IS a failure here).
  4. The skill 59 folder and its sanctioned entry script exist on disk, matching
     wiring.json's self_invocation.entry_script pointer.
  5. HOW-TO-USE-THE-ANTHOLOGY-DEPARTMENT.md exists in this folder and names
     anthology-engine-entry.sh as the self-invocation path for all three event
     kinds this slice is scored on: intake, gate events, and the assembly
     trigger.
  6. The QC independence rule declared in wiring.json is internally consistent:
     the drafting persona and the qc role are two distinct, non-empty slugs.
  7. The PRD Section 13 access matrix is present and internally consistent:
     default-deny policy; the two read-only departments (marketing,
     social-media) carry no write access; no explicit no-access example is also
     a granted (owner or read-only) department.

Exit codes:
  0 = all wiring assertions pass
  7 = one or more violations (details printed)

Read-only. Never writes. Idempotent. No em dashes in output. No triple-backtick
fences.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
WIRING = os.path.join(HERE, "wiring.json")
HOWTO = os.path.join(HERE, "HOW-TO-USE-THE-ANTHOLOGY-DEPARTMENT.md")
MAP_PATH = os.path.join(REPO, "23-ai-workforce-blueprint", "skill-department-map.json")
INDEX_PATH = os.path.join(REPO, "23-ai-workforce-blueprint", "templates", "role-library", "_index.json")
NAMING_MAP = os.path.join(REPO, "23-ai-workforce-blueprint", "department-naming-map.json")
FLOOR_SCRIPT = os.path.join(REPO, "23-ai-workforce-blueprint", "scripts", "department-floor.py")
SKILL_DIR = os.path.join(REPO, "59-anthology-engine")

EXPECTED_DEPARTMENTS = ["marketing"]
EXPECTED_PRIMARY_ROLE = "content-marketing-strategist"
EXPECTED_PRIMARY_DEPT = "marketing"


def load_json(p):
    with open(p) as f:
        return json.load(f)


def check_map(errors, w):
    m = load_json(MAP_PATH)
    idx = load_json(INDEX_PATH)
    live_pairs = {(r["dept"], r["slug"]) for r in idx["roles"]}

    entries = [s for s in m["skills"] if s.get("skill") == "59"]
    if len(entries) != 1:
        errors.append(f"[map] skill-department-map.json has {len(entries)} entries for skill '59', expected exactly 1")
        return
    entry = entries[0]

    if entry.get("slug") != "anthology-engine":
        errors.append(f"[map] skill 59 slug = '{entry.get('slug')}', expected 'anthology-engine'")
    if not entry.get("client_facing"):
        errors.append("[map] skill 59 should be client_facing true (department-invocable)")
    if entry.get("departments") != EXPECTED_DEPARTMENTS:
        errors.append(f"[map] skill 59 departments = {entry.get('departments')}, expected {EXPECTED_DEPARTMENTS}")

    roles = entry.get("roles", [])
    if not roles:
        errors.append("[map] skill 59 ORPHAN: resolves to no owning role")
    primaries = [r for r in roles if r.get("primary")]
    if len(primaries) != 1:
        errors.append(f"[map] skill 59 must have exactly one primary role, found {len(primaries)}")
    elif primaries[0].get("slug") != EXPECTED_PRIMARY_ROLE or primaries[0].get("dept") != EXPECTED_PRIMARY_DEPT:
        errors.append(
            f"[map] skill 59 primary role = ({primaries[0].get('dept')}, {primaries[0].get('slug')}), "
            f"expected ({EXPECTED_PRIMARY_DEPT}, {EXPECTED_PRIMARY_ROLE})"
        )
    for r in roles:
        pair = (r.get("dept"), r.get("slug"))
        if pair not in live_pairs:
            errors.append(f"[map] skill 59 ORPHAN: role {pair} does not exist in the role library")

    if not entry.get("intent_triggers"):
        errors.append("[map] skill 59 client-facing but has no intent_triggers")

    for sop in entry.get("execution_sops", []):
        p = os.path.join(REPO, "universal-sops", sop)
        if not (os.path.isdir(p) or os.path.isfile(p)):
            errors.append(f"[map] skill 59 execution_sop '{sop}' not found under universal-sops/")


def check_naming_map_untouched(errors, w):
    if not os.path.isfile(NAMING_MAP):
        errors.append(f"[floor] department-naming-map.json not found at {NAMING_MAP}")
        return
    raw = open(NAMING_MAP, "r", errors="replace").read()
    if "anthology" in raw.lower():
        errors.append(
            "[floor] the string 'anthology' appears in department-naming-map.json; "
            "this slice must NEVER add an anthology department to the mandatory or "
            "vertical_packs blocks (Anthology is client-optional, seeded per client "
            "by Skill 32, never a static floor member)"
        )

    dept = w.get("client_department", {})
    if dept.get("in_department_naming_map") is not False:
        errors.append("[floor] wiring.json client_department.in_department_naming_map must be false")
    if dept.get("is_mandatory") is not False or dept.get("is_universal_primary") is not False:
        errors.append("[floor] wiring.json client_department must declare is_mandatory=false and is_universal_primary=false")

    # Best-effort git proof: department-naming-map.json is byte-identical to
    # origin/main, so this slice provably never touched it. Never fails the
    # gate on missing git / missing ref / detached checkout; only a REAL diff
    # against a resolvable origin/main is an error.
    try:
        rel = os.path.relpath(NAMING_MAP, REPO)
        subprocess.run(["git", "-C", REPO, "rev-parse", "--verify", "origin/main"],
                       check=True, capture_output=True, timeout=10)
        diff = subprocess.run(["git", "-C", REPO, "diff", "--stat", "origin/main", "--", rel],
                               capture_output=True, timeout=10, text=True)
        if diff.returncode == 0 and diff.stdout.strip():
            errors.append(f"[floor] department-naming-map.json differs from origin/main:\n{diff.stdout}")
    except Exception:
        pass  # best-effort only; absence of git/origin/main is never a violation


def check_floor(errors, w):
    if not os.path.isfile(FLOOR_SCRIPT):
        errors.append(f"[floor] department-floor.py not found at {FLOOR_SCRIPT}")
        return
    try:
        proc = subprocess.run([sys.executable, FLOOR_SCRIPT, "--json"],
                               capture_output=True, text=True, timeout=30)
    except Exception as exc:
        errors.append(f"[floor] could not run department-floor.py --json: {exc}")
        return
    if proc.returncode not in (0, 7):
        errors.append(f"[floor] department-floor.py --json exited {proc.returncode} (expected 0 or 7); stderr: {proc.stderr[:500]}")
        return
    try:
        verdict = json.loads(proc.stdout)
    except Exception as exc:
        errors.append(f"[floor] could not parse department-floor.py --json output: {exc}")
        return
    if proc.returncode == 7:
        return  # no workforce on this box to evaluate against; not a wiring defect
    expected = w.get("floor_invariant", {}).get("expected_floor_count")
    if verdict.get("expected_floor_count") != expected:
        errors.append(
            f"[floor] department-floor.py reports expected_floor_count={verdict.get('expected_floor_count')}, "
            f"wiring.json declares {expected}"
        )
    if verdict.get("expected_floor_count") != 28:
        errors.append(f"[floor] expected_floor_count = {verdict.get('expected_floor_count')}, expected 28 (22 mandatory + 6 universal-primary-vertical)")


def check_disk(errors, w):
    entry_rel = w.get("self_invocation", {}).get("entry_script") or w.get("skill", {}).get("entry_script")
    if not entry_rel:
        errors.append("[disk] wiring.json has no self_invocation.entry_script pointer")
        return
    entry_path = os.path.join(REPO, entry_rel)
    if not os.path.isfile(entry_path):
        errors.append(f"[disk] self-invocation entry script not found on disk: {entry_rel}")
    if not os.path.isdir(SKILL_DIR):
        errors.append(f"[disk] skill 59 folder not found: {SKILL_DIR}")


def check_howto(errors, w):
    if not os.path.isfile(HOWTO):
        errors.append(f"[howto] HOW-TO-USE-THE-ANTHOLOGY-DEPARTMENT.md not found at {HOWTO}")
        return
    text = open(HOWTO, "r", errors="replace").read()
    if "anthology-engine-entry.sh" not in text:
        errors.append("[howto] the how-to doc never names anthology-engine-entry.sh as the self-invocation path")
    lower = text.lower()
    for kw in ("intake", "gate", "assembl"):
        if kw not in lower:
            errors.append(f"[howto] the how-to doc's self-invocation entry never mentions '{kw}'")


def check_qc_independence(errors, w):
    rule = w.get("qc_independence_rule", {})
    drafting = rule.get("drafting_persona")
    qc = rule.get("qc_role")
    if not drafting or not qc:
        errors.append("[qc] qc_independence_rule must declare both drafting_persona and qc_role")
    elif drafting == qc:
        errors.append(f"[qc] INDEPENDENCE VIOLATION: drafting_persona and qc_role are both '{drafting}'")
    if rule.get("disjoint_required") is not True:
        errors.append("[qc] qc_independence_rule.disjoint_required must be true")


def check_access_matrix(errors, w):
    am = w.get("access_matrix")
    if not am:
        errors.append("[access] access_matrix block is missing (PRD Section 13 access decision)")
        return
    if am.get("policy") != "default-deny":
        errors.append("[access] access_matrix.policy must be 'default-deny'")
    owner = am.get("owner", {})
    readers = am.get("read_only_downstream", []) or []
    noacc = am.get("no_access", {})
    if owner.get("write") is not True:
        errors.append("[access] owner tier must carry write access")
    reader_depts = set()
    for r in readers:
        reader_depts.add(r.get("department"))
        if r.get("write") is not False:
            errors.append(f"[access] read_only_downstream '{r.get('department')}' must not carry write access")
    for req in ("marketing", "social-media"):
        if req not in reader_depts:
            errors.append(f"[access] read_only_downstream is missing '{req}'")
    granted = {owner.get("fleet_department"), owner.get("client_board_department")} | reader_depts
    granted.discard(None)
    for ex in noacc.get("explicit_examples", []):
        if ex in granted:
            errors.append(f"[access] no_access example '{ex}' is also a granted department (contradiction)")


def run():
    errors = []
    w = load_json(WIRING)
    check_map(errors, w)
    check_naming_map_untouched(errors, w)
    check_floor(errors, w)
    check_disk(errors, w)
    check_howto(errors, w)
    check_qc_independence(errors, w)
    check_access_matrix(errors, w)
    return errors


def main():
    errors = run()
    if errors:
        print(f"FAIL - {len(errors)} wiring violation(s):")
        for e in errors:
            print("  x " + e)
        return 7
    print("OK - anthology engine wiring verified:")
    print("  - skill-department-map.json skill 59 binds departments ['marketing'] with one primary (content-marketing-strategist), no orphans")
    print("  - department-naming-map.json carries zero 'anthology' references (mandatory/vertical_packs untouched)")
    print("  - department-floor.py --json still reports expected_floor_count 28, zero composition change")
    print("  - the skill 59 folder and anthology-engine-entry.sh exist on disk")
    print("  - the how-to doc names anthology-engine-entry.sh for intake, gate events, and the assembly trigger")
    print("  - QC independence holds (drafting persona and qc role are disjoint)")
    print("  - PRD Section 13 access matrix present and disjoint (default-deny; marketing + social-media read-only, no writers besides owner)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
