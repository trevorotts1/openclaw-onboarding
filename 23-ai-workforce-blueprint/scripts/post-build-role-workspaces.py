#!/usr/bin/env python3
"""
Post-build role workspace creator.

Runs after `build-workforce.py` finishes. Walks the active zero-human-company's
departments and creates role-level workspaces for every dept that doesn't have
them yet.

This is the integration that makes the v2.1 role-level architecture real for
existing builds — without modifying `build-workforce.py` itself.

Idempotent — safe to re-run. Only creates folders that don't exist.

Usage:
    python3 23-ai-workforce-blueprint/scripts/post-build-role-workspaces.py
    python3 23-ai-workforce-blueprint/scripts/post-build-role-workspaces.py --company-slug <slug>
    python3 23-ai-workforce-blueprint/scripts/post-build-role-workspaces.py --dry-run
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Make sibling modules importable
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared-utils"))

from detect_platform import get_openclaw_paths  # type: ignore
from create_role_workspaces import build_all_roles_for_dept, slugify  # type: ignore


# Default roles every department gets (regardless of dept-specific specialists)
DEFAULT_DEPT_ROLES = [
    {"name": "Director of {dept}", "type": "full-time-permanent", "is_ceo": False},
    {"name": "QC Specialist", "type": "full-time-permanent"},
    {"name": "Deep Research Specialist", "type": "on-call"},
]


def parse_suggested_roles_md(roles_md_path: Path) -> list:
    """
    Parse a suggested-roles/[dept]-suggested-roles.md file to extract role names.

    Roles are listed under `### N. Role Name (...)`. We extract the name only;
    everything else is filled by the role-doc-generation sub-agent later.
    """
    if not roles_md_path.exists():
        return []

    content = roles_md_path.read_text(encoding="utf-8", errors="replace")
    roles = []
    # Match patterns like "### 1. Role Name (full-time-permanent)" or "### 1. Role Name"
    pattern = re.compile(r"^###\s+\d+\.\s+(.+?)$", re.MULTILINE)
    for match in pattern.finditer(content):
        line = match.group(1).strip()
        # Strip parenthetical role type
        name = re.sub(r"\s*\(.*?\)\s*$", "", line).strip()
        # Strip trailing flags like "⭐ FLAGSHIP ROLE"
        name = re.sub(r"\s*[⭐🔧🚨]\s*FLAGSHIP.*$", "", name).strip()
        if name and len(name) < 80:
            roles.append({"name": name, "type": "full-time-permanent"})
    return roles


def find_suggested_roles_file(skill_root: Path, dept_id: str) -> Path:
    """
    Map dept_id to a suggested-roles file path. Try multiple naming conventions.
    """
    candidates = [
        skill_root / "suggested-roles" / f"{dept_id}-suggested-roles.md",
        skill_root / "suggested-roles" / f"{dept_id.replace('-dept','')}-suggested-roles.md",
        skill_root / "suggested-roles" / f"{dept_id.replace('_','-')}-suggested-roles.md",
    ]
    # Also try replacing common naming variants
    aliases = {
        "billing-finance": "billing",
        "openclaw-maintenance": "openclaw-maintenance",
        "social-media": "social-media",
        "paid-advertisement": "paid-advertisement",
        "legal": "legal-compliance",
        "customer-support": "customer-support",
        "web-development": "web-development",
        "app-development": "app-development",
    }
    if dept_id in aliases:
        candidates.append(skill_root / "suggested-roles" / f"{aliases[dept_id]}-suggested-roles.md")
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # return non-existent canonical for error reporting


def process_company(company_root: Path, skill_root: Path, dry_run: bool = False) -> dict:
    """
    Walk a single company workspace and create role-level workspaces.
    """
    workspace_root = company_root  # symlinks resolve here
    departments_json = company_root / "departments.json"

    counts = {"depts_scanned": 0, "roles_created": 0, "roles_skipped_exist": 0, "depts_without_roles_file": 0}

    # Master orchestrator (CEO) lives at company root, not inside departments/
    if not (company_root / "master-orchestrator").exists():
        tag = "[DRY-RUN] " if dry_run else ""
        print(f"  {tag}Creating master-orchestrator (CEO agent)")
        if not dry_run:
            build_all_roles_for_dept(
                company_root,  # dept_path = company_root because CEO sits at company level
                "master-orchestrator",
                [{"name": "Master Orchestrator", "type": "full-time-permanent", "is_ceo": True}],
                workspace_root,
            )
            counts["roles_created"] += 1
    else:
        counts["roles_skipped_exist"] += 1

    # Departments
    dept_ids = []
    if departments_json.exists():
        try:
            data = json.loads(departments_json.read_text(encoding="utf-8"))
            if isinstance(data, list):
                dept_ids = [d.get("id", "").replace("dept-", "") for d in data if isinstance(d, dict)]
            elif isinstance(data, dict) and "departments" in data:
                dept_ids = [d.get("id", "").replace("dept-", "") for d in data["departments"]]
        except Exception as e:
            print(f"  WARN: failed to parse departments.json: {e}")

    departments_dir = company_root / "departments"
    if departments_dir.exists():
        # Also scan filesystem for any depts not in departments.json
        for entry in departments_dir.iterdir():
            if entry.is_dir():
                dept_slug = entry.name.replace("-dept", "")
                if dept_slug not in dept_ids:
                    dept_ids.append(dept_slug)

    for dept_id in dept_ids:
        if not dept_id:
            continue
        dept_path = departments_dir / f"{dept_id}-dept"
        if not dept_path.exists():
            dept_path = departments_dir / dept_id
        if not dept_path.exists():
            print(f"  WARN: dept folder not found for {dept_id}")
            continue
        counts["depts_scanned"] += 1

        # Find the suggested-roles file
        roles_file = find_suggested_roles_file(skill_root, dept_id)
        roles_from_file = parse_suggested_roles_md(roles_file)

        if not roles_from_file:
            counts["depts_without_roles_file"] += 1
            # Fall back to just the defaults (Director / QC / Deep Research)
            roles = [
                {"name": f"Director of {dept_id.replace('-', ' ').title()}", "type": "full-time-permanent"},
                {"name": "QC Specialist", "type": "full-time-permanent"},
                {"name": "Deep Research Specialist", "type": "on-call"},
            ]
        else:
            roles = roles_from_file

        # Skip role folders that already exist
        new_roles = []
        for role in roles:
            slug = slugify(role["name"])
            if (dept_path / slug).exists():
                counts["roles_skipped_exist"] += 1
            else:
                new_roles.append(role)

        if not new_roles:
            print(f"  Department '{dept_id}': all {len(roles)} roles already exist, skipping")
            continue

        tag = "[DRY-RUN] " if dry_run else ""
        print(f"  {tag}Department '{dept_id}': creating {len(new_roles)} new role workspaces")
        if not dry_run:
            build_all_roles_for_dept(dept_path, dept_id, new_roles, workspace_root)
            counts["roles_created"] += len(new_roles)

    return counts


def main():
    parser = argparse.ArgumentParser(description="Create role-level workspaces post-build for all departments in the active zero-human-company")
    parser.add_argument("--company-slug", help="Process only this company slug. Defaults to all companies in ZHC root.")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be created without writing.")
    parser.add_argument("--skill-root", help="Path to the 23-ai-workforce-blueprint skill (defaults to detect)")
    args = parser.parse_args()

    paths = get_openclaw_paths()
    zhc_root = paths["company_root"]
    skill_root = Path(args.skill_root) if args.skill_root else (paths["skills"] / "23-ai-workforce-blueprint")
    if not skill_root.exists():
        # Fallback to current source repo if installed skills aren't found
        skill_root = Path(__file__).resolve().parent.parent

    print(f"Platform:       {paths['platform']}")
    print(f"ZHC root:       {zhc_root}")
    print(f"Skill root:     {skill_root}")
    if args.dry_run:
        print("DRY-RUN MODE — no files written")
    print()

    if not zhc_root.exists():
        print(f"ERROR: ZHC root {zhc_root} does not exist. Has any company been built yet?")
        return 1

    total = {"depts_scanned": 0, "roles_created": 0, "roles_skipped_exist": 0, "depts_without_roles_file": 0}
    companies = []
    if args.company_slug:
        target = zhc_root / args.company_slug
        if target.exists():
            companies.append(target)
    else:
        companies = [p for p in zhc_root.iterdir() if p.is_dir()]

    for company in companies:
        print(f"=== Company: {company.name} ===")
        result = process_company(company, skill_root, dry_run=args.dry_run)
        for k, v in result.items():
            total[k] = total.get(k, 0) + v
        print()

    print("=" * 60)
    print(f"Companies processed:           {len(companies)}")
    print(f"Departments scanned:           {total['depts_scanned']}")
    print(f"Role workspaces created:       {total['roles_created']}")
    print(f"Role workspaces already exist: {total['roles_skipped_exist']}")
    print(f"Depts without roles file:      {total['depts_without_roles_file']}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
