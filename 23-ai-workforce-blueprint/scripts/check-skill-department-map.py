#!/usr/bin/env python3
"""
check-skill-department-map.py — orphan check + consistency assertion for
23-ai-workforce-blueprint/skill-department-map.json (PRD Departments-That-Use-Skills, Wave 0.2).

Proves, WITHOUT grepping for scores (structural facts only):
  1. Every client-facing skill resolves to >=1 live owning department AND >=1 live
     owning specialist role that EXISTS in templates/role-library/_index.json.
  2. Every client-facing skill carries >=1 owning dept, >=1 role, >=1 intent trigger,
     and exactly one primary role.
  3. Every referenced (dept, role) pair exists in the role library.
  4. Every infra skill carries a live dept_owner and NO intent triggers.
  5. Every numbered skill folder on disk appears in the map (no skill left unmapped),
     and every mapped skill folder exists on disk.
  6. Referenced execution_sops resolve under universal-sops/ (dir cluster or loose file).

Exit codes:
  0 = all green (no orphans, fully consistent)
  7 = one or more violations (details printed)
"""
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAP_PATH = os.path.join(REPO, "23-ai-workforce-blueprint", "skill-department-map.json")
INDEX_PATH = os.path.join(REPO, "23-ai-workforce-blueprint", "templates", "role-library", "_index.json")
USOPS = os.path.join(REPO, "universal-sops")


def load_json(p):
    with open(p) as f:
        return json.load(f)


def main():
    errors = []
    warns = []

    m = load_json(MAP_PATH)
    idx = load_json(INDEX_PATH)

    # Live departments + (dept, role) pairs from the role library index.
    live_depts = set(idx["departments"].keys())
    live_pairs = {(r["dept"], r["slug"]) for r in idx["roles"]}
    live_roles_by_dept = {}
    for r in idx["roles"]:
        live_roles_by_dept.setdefault(r["dept"], set()).add(r["slug"])

    skills = m["skills"]
    mapped_nums = {s["skill"] for s in skills}

    # --- Skill-folder coverage on disk (both directions) ---
    disk_nums = set()
    for entry in os.listdir(REPO):
        if len(entry) >= 3 and entry[:2].isdigit() and entry[2] == "-" and os.path.isdir(os.path.join(REPO, entry)):
            disk_nums.add(entry[:2])
    missing_from_map = sorted(disk_nums - mapped_nums)
    missing_from_disk = sorted(mapped_nums - disk_nums)
    for n in missing_from_map:
        errors.append(f"[coverage] skill folder {n}-* exists on disk but is NOT in the map")
    for n in missing_from_disk:
        errors.append(f"[coverage] skill {n} is in the map but has NO skill folder on disk")

    cf_count = 0
    infra_count = 0

    for s in skills:
        sk = s["skill"]
        cf = s.get("client_facing", False)

        if cf:
            cf_count += 1
            depts = s.get("departments", [])
            roles = s.get("roles", [])
            triggers = s.get("intent_triggers", [])

            if not depts:
                errors.append(f"[skill {sk}] client-facing but has no departments")
            for d in depts:
                if d not in live_depts:
                    errors.append(f"[skill {sk}] department '{d}' is not a live department")

            if not roles:
                errors.append(f"[skill {sk}] ORPHAN: client-facing but resolves to no owning role")
            primaries = [r for r in roles if r.get("primary")]
            if len(primaries) != 1:
                errors.append(f"[skill {sk}] must have exactly one primary role, found {len(primaries)}")
            for r in roles:
                pair = (r["dept"], r["slug"])
                if pair not in live_pairs:
                    errors.append(
                        f"[skill {sk}] ORPHAN: role '{r['slug']}' in dept '{r['dept']}' "
                        f"does not exist in the role library"
                    )
                elif r["dept"] not in depts:
                    warns.append(
                        f"[skill {sk}] role dept '{r['dept']}' not listed in the skill's departments {depts}"
                    )

            if not triggers:
                errors.append(f"[skill {sk}] client-facing but has no intent_triggers")

            for sop in s.get("execution_sops", []):
                p = os.path.join(USOPS, sop)
                if not (os.path.isdir(p) or os.path.isfile(p)):
                    errors.append(f"[skill {sk}] execution_sop '{sop}' not found under universal-sops/")
        else:
            infra_count += 1
            owner = s.get("dept_owner")
            if not owner:
                errors.append(f"[skill {sk}] infra skill has no dept_owner")
            elif owner not in live_depts:
                errors.append(f"[skill {sk}] infra dept_owner '{owner}' is not a live department")
            if s.get("intent_triggers"):
                errors.append(f"[skill {sk}] infra skill must not carry intent_triggers")

    print(f"role-library version: {idx.get('version')}  live departments: {len(live_depts)}  live roles: {len(idx['roles'])}")
    print(f"skills in map: {len(skills)}  client-facing: {cf_count}  infra: {infra_count}")
    print(f"skill folders on disk: {len(disk_nums)}")

    if warns:
        print("\nWARNINGS (non-blocking):")
        for w in warns:
            print("  ! " + w)

    if errors:
        print(f"\nFAIL — {len(errors)} violation(s):")
        for e in errors:
            print("  x " + e)
        return 7

    print("\nOK — orphan check PASSED: every client-facing skill resolves to a live department + specialist role.")
    print("     Coverage complete (map <-> disk), infra ownership valid, execution SOPs resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
