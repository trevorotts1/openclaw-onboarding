#!/usr/bin/env python3
"""
ARCHITECT wiring: register the two new departments (bugs + healer) and their
standing roles into templates/role-library/_index.json.

Idempotent. Recomputes total_roles (== sum of dept role-list lengths, the
invariant converge validates) and total_departments. Leaves all other depts
untouched. Adds FULL flat-array entries (8 fields incl role_type) for every new
role file so _build_library_index() (create_role_workspaces.py) can resolve and
materialize them (Fable A.3 / C3 watch item).

role_type canonicalization (Fable C1): bugs specialists = 'specialist';
healer roles = 'healer' (NEVER 'qc', or the CC QC scorer could select a Healer
as the QC gate -> checks-and-balances violation).
"""
import json
import sys
from pathlib import Path

REPO = Path("/tmp/bugs-healer-build")
IDX = REPO / "23-ai-workforce-blueprint/templates/role-library/_index.json"
LIB = REPO / "23-ai-workforce-blueprint/templates/role-library"

# New standing role files that EXIST on disk (architect registers only real files).
# (slug, dept, title, role_type, path-relative-to-skill, in_roster)
# in_roster=True -> listed in departments.<dept>.roles (a materializable roster role)
# in_roster=False -> flat-array hygiene entry only (a per-dept instantiation TEMPLATE)
NEW_ROLES = [
    ("bug-intake-clerk",     "bugs",   "Bug Intake Clerk (Registrar)", "specialist", "templates/role-library/bugs/bug-intake-clerk.md",     True),
    ("triage-dedup-analyst", "bugs",   "Triage and Dedup Analyst",      "specialist", "templates/role-library/bugs/triage-dedup-analyst.md", True),
    ("bug-librarian",        "bugs",   "Bug Librarian (Pattern Keeper)","specialist", "templates/role-library/bugs/bug-librarian.md",        True),
    ("chief-healer",         "healer", "Chief Healer",                  "healer",     "templates/role-library/healer/chief-healer.md",       True),
    ("dept-healer-template", "healer", "The Healer (department template)","healer",   "templates/role-library/healer/dept-healer-template.md", False),
]


def count_words(path):
    try:
        return len((REPO / "23-ai-workforce-blueprint" / Path(path)).read_text(encoding="utf-8", errors="ignore").split())
    except Exception:
        return 0


def count_sops(path, dept):
    """Substantive-SOP count. Bugs roles carry B-9.x; healer roles carry 9.1-9.12."""
    try:
        txt = (REPO / "23-ai-workforce-blueprint" / Path(path)).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return 0
    import re
    if dept == "healer":
        return len(set(re.findall(r"(?m)^###?\s+SOP\s+9\.(\d+)", txt)))
    return len(set(re.findall(r"(?m)^###?\s+(?:SOP\s+)?B-9\.(\d+)", txt)))


def main():
    idx = json.loads(IDX.read_text(encoding="utf-8"))
    depts = idx.setdefault("departments", {})

    # 1. Register departments + rosters (idempotent).
    roster = {}
    for slug, dept, title, rtype, path, in_roster in NEW_ROLES:
        if in_roster:
            roster.setdefault(dept, []).append(slug)
    for dept, slugs in roster.items():
        d = depts.setdefault(dept, {"count": 0, "roles": []})
        existing = set(d.get("roles", []))
        for s in slugs:
            existing.add(s)
        d["roles"] = sorted(existing)
        d["count"] = len(d["roles"])

    # 2. Flat-array entries (FULL 8-field entries; materialization source).
    flat = idx.setdefault("roles", [])
    have = {(r.get("slug"), r.get("dept")) for r in flat}
    for slug, dept, title, rtype, path, in_roster in NEW_ROLES:
        if (slug, dept) in have:
            # update in place (idempotent re-run keeps fields fresh)
            for r in flat:
                if r.get("slug") == slug and r.get("dept") == dept:
                    r.update({
                        "title": title, "role_type": rtype, "path": path,
                        "word_count": count_words(path),
                        "sop_count": count_sops(path, dept),
                    })
            continue
        flat.append({
            "slug": slug,
            "dept": dept,
            "title": title,
            "role_type": rtype,
            "word_count": count_words(path),
            "sop_count": count_sops(path, dept),
            "sop_min": 5,
            "path": path,
        })

    # 3. Recompute invariants.
    idx["total_roles"] = sum(len(d.get("roles", [])) for d in depts.values())
    idx["total_departments"] = len(depts)

    IDX.write_text(json.dumps(idx, indent=2) + "\n", encoding="utf-8")

    print("departments now:", len(depts))
    print("bugs roster:", depts.get("bugs"))
    print("healer roster:", depts.get("healer"))
    print("total_roles:", idx["total_roles"])
    print("total_departments:", idx["total_departments"])
    print("flat entries for new roles:")
    for r in flat:
        if r.get("dept") in ("bugs", "healer"):
            print("  ", r["slug"], "|", r["dept"], "|", r["role_type"], "| wc", r["word_count"], "| sops", r["sop_count"])


if __name__ == "__main__":
    sys.exit(main())
