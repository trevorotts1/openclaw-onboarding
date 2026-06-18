#!/usr/bin/env python3
"""
Regenerate department ROSTER.md from the on-disk role folders (idempotent).

ROOT PROBLEM this fixes: when a workforce build/materialization writes role
folders (NN-<slug>/IDENTITY.md, how-to.md, ...) into a department's LIVE
workspace, the department's ROSTER.md — the "When-to Reference Map" the director
agent actually reads before dispatching — was NOT (re)generated. The director
reads ROSTER.md, not the folders, so it under-reported its roles (the bot said
"1 role" when 24 role folders existed). This script (re)writes ROSTER.md so it
ALWAYS matches the role folders that EXIST on disk.

It is the standalone, fleet-callable companion to
create_role_workspaces.regenerate_department_roster. The build/materialization
paths already call that function automatically; this script is for the fleet
pass / a manual repair to refresh a stale roster on any already-materialized box.

Usage:
    # Refresh ROSTER.md for every department of the active company:
    python3 23-ai-workforce-blueprint/scripts/regenerate-dept-roster.py

    # One specific department folder:
    python3 .../regenerate-dept-roster.py --dept-path <ZHC>/<company>/departments/<dept>

    # A specific company by slug, or all companies under the ZHC root:
    python3 .../regenerate-dept-roster.py --company-slug <slug>
    python3 .../regenerate-dept-roster.py --all-companies

    # Preview only:
    python3 .../regenerate-dept-roster.py --dry-run
"""
import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent

# Mirror post-build-role-workspaces.py's sys.path order: insert shared-utils
# FIRST (fallbacks), then lib/ LAST so lib/ ends at position 0 — the order that
# resolves the REAL active company_dir rather than an empty master-files copy.
sys.path.insert(0, str(SCRIPT_DIR))
for _libp in (SKILL_DIR.parent / "shared-utils", SKILL_DIR / "shared-utils", SKILL_DIR / "lib"):
    sys.path.insert(0, str(_libp))

from create_role_workspaces import (  # type: ignore
    regenerate_department_roster,
    scan_department_roles_on_disk,
)


def _looks_like_department(dept_path: Path) -> bool:
    """True if dept_path holds at least one materialized role folder."""
    try:
        return bool(scan_department_roles_on_disk(dept_path))
    except Exception:
        return False


def regenerate_company(company_root: Path, dry_run: bool = False) -> dict:
    """Refresh ROSTER.md for every department under a company root."""
    counts = {"depts": 0, "rosters_written": 0, "roles_total": 0}
    departments_dir = company_root / "departments"
    if not departments_dir.is_dir():
        print(f"  WARN: no departments/ folder at {departments_dir}")
        return counts
    for dept_path in sorted(departments_dir.iterdir()):
        if not dept_path.is_dir():
            continue
        counts["depts"] += 1
        roles = scan_department_roles_on_disk(dept_path)
        counts["roles_total"] += len(roles)
        roster_path = regenerate_department_roster(dept_path, dry_run=dry_run)
        if roster_path is not None:
            counts["rosters_written"] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate department ROSTER.md from on-disk role folders.")
    parser.add_argument("--dept-path",
                        help="Refresh ROSTER.md for exactly this department folder.")
    parser.add_argument("--company-slug",
                        help="Refresh every department of this company slug "
                             "(under the resolved ZHC root).")
    parser.add_argument("--all-companies", action="store_true",
                        help="Refresh every department of every company under "
                             "the ZHC root.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be written; write nothing.")
    args = parser.parse_args()

    # ── Single explicit department: simplest, fleet-friendly path ────────────
    if args.dept_path:
        dept_path = Path(args.dept_path)
        if not dept_path.is_dir():
            print(f"ERROR: --dept-path is not a directory: {dept_path}", file=sys.stderr)
            return 1
        roster_path = regenerate_department_roster(dept_path, dry_run=args.dry_run)
        return 0 if roster_path is not None else 1

    # ── Otherwise resolve the active workspace and walk companies ────────────
    try:
        from detect_platform import get_openclaw_paths  # type: ignore
        paths = get_openclaw_paths()
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: could not resolve workspace ({e}). "
              f"Pass --dept-path explicitly.", file=sys.stderr)
        return 1

    company_dir = paths.get("company_dir")
    zhc_root = paths.get("company_root")
    print(f"Platform: {paths.get('platform')}")
    if company_dir and Path(company_dir).is_dir():
        print(f"Active company_dir: {company_dir}")
    print(f"ZHC root: {zhc_root}")
    if args.dry_run:
        print("DRY-RUN — no files written")
    print()

    companies = []
    if args.company_slug and zhc_root and Path(zhc_root).is_dir():
        target = Path(zhc_root) / args.company_slug
        if target.is_dir():
            companies.append(target)
        else:
            print(f"WARN: company slug '{args.company_slug}' not found under {zhc_root}")
    if not companies and args.all_companies and zhc_root and Path(zhc_root).is_dir():
        companies = [p for p in sorted(Path(zhc_root).iterdir()) if p.is_dir()]
    if not companies and company_dir and Path(company_dir).is_dir():
        companies = [Path(company_dir)]
    if not companies and zhc_root and Path(zhc_root).is_dir():
        companies = [p for p in sorted(Path(zhc_root).iterdir()) if p.is_dir()]
    if not companies:
        print(f"ERROR: no company workspace found "
              f"(company_dir={company_dir}, company_root={zhc_root}).",
              file=sys.stderr)
        return 1

    total = {"depts": 0, "rosters_written": 0, "roles_total": 0}
    for company in companies:
        print(f"=== Company: {company.name} ===")
        result = regenerate_company(company, dry_run=args.dry_run)
        for k in total:
            total[k] += result[k]
        print()

    print("=" * 60)
    print(f"Companies processed:   {len(companies)}")
    print(f"Departments scanned:   {total['depts']}")
    print(f"Rosters regenerated:   {total['rosters_written']}")
    print(f"Role folders listed:   {total['roles_total']}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
