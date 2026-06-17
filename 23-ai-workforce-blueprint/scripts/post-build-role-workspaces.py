#!/usr/bin/env python3
"""
Post-build role workspace creator (v10.5.1).

Runs after `build-workforce.py` finishes. Walks the active zero-human-company's
departments and AUGMENTS existing role folders (created by the v9.x
`create_role_workspace` in build-workforce.py) with v2.1 files: IDENTITY.md,
SOUL.md, MEMORY.md, HEARTBEAT.md, how-to.md stub, and symlinks for AGENTS.md,
TOOLS.md, USER.md.

This makes the v2.1 architecture real for existing builds without modifying
`build-workforce.py` itself.

Idempotent — safe to re-run. Only adds files that don't exist.

Behavior:
- For each department folder under `[ZHC]/[company]/departments/`:
  - For every role subfolder (any naming pattern, with or without numeric prefix):
    - Add IDENTITY.md, SOUL.md, MEMORY.md, HEARTBEAT.md, how-to.md if missing
    - (Re)create AGENTS.md, TOOLS.md, USER.md symlinks to workspace root
- For the company root, ensure a `master-orchestrator/` folder exists with CEO
  variant of the deferral clause.

Usage:
    python3 23-ai-workforce-blueprint/scripts/post-build-role-workspaces.py
    python3 23-ai-workforce-blueprint/scripts/post-build-role-workspaces.py --company-slug <slug>
    python3 23-ai-workforce-blueprint/scripts/post-build-role-workspaces.py --dry-run
"""
import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent

# BUG-3 FIX (mirrors department-floor.py BUG-2): sys.path.insert(0, ...) order
# matters — the LAST insert wins (each call pushes the previous down). The old
# order inserted lib/ first then shared-utils/ LAST, so the shared-utils
# detect_platform (which returns company_root=~/Downloads/openclaw-master-files/
# zero-human-company — an EMPTY copy — and never resolves the active company_dir)
# shadowed the lib/ version that correctly resolves the real workspace. Result:
# this script scanned 0 departments. Fix: insert shared-utils FIRST (fallbacks),
# then lib/ LAST so lib/ ends at position 0 — exactly the order qc-completeness.sh
# and department-floor.py use to get a working company_dir.
sys.path.insert(0, str(SCRIPT_DIR))
for _libp in (SKILL_DIR.parent / "shared-utils", SKILL_DIR / "shared-utils", SKILL_DIR / "lib"):
    sys.path.insert(0, str(_libp))

from detect_platform import get_openclaw_paths  # type: ignore
from create_role_workspaces import (  # type: ignore
    augment_all_existing_role_folders,
    create_role_workspace,
    augment_role_folder,
)


def process_company(company_root: Path, dry_run: bool = False) -> dict:
    """Walk a company and augment every dept + ensure CEO at company root."""
    counts = {
        "depts_scanned": 0,
        "role_folders_augmented": 0,
        "role_files_written": 0,
        "ceo_created_or_augmented": False,
    }
    workspace_root = company_root  # symlinks resolve here

    # 1. Master Orchestrator (CEO) — lives at company root
    ceo_path = company_root / "master-orchestrator"
    if not ceo_path.exists():
        tag = "[DRY-RUN] " if dry_run else ""
        print(f"  {tag}Creating master-orchestrator (CEO agent)")
        if not dry_run:
            create_role_workspace(
                company_root,
                "Master Orchestrator",
                workspace_root,
                role_metadata={"is_ceo": True, "type": "full-time-permanent"},
            )
            counts["ceo_created_or_augmented"] = True
    else:
        if not dry_run:
            print(f"  Augmenting existing master-orchestrator")
            result = augment_role_folder(
                ceo_path,
                workspace_root,
                role_metadata={"is_ceo": True, "name": "Master Orchestrator"},
            )
            if result["written"]:
                print(f"    + {len(result['written'])} files: {', '.join(result['written'])}")
            counts["ceo_created_or_augmented"] = bool(result["written"])
        else:
            print(f"  [DRY-RUN] would augment master-orchestrator")
            counts["ceo_created_or_augmented"] = True

    # 2. Departments
    departments_dir = company_root / "departments"
    if not departments_dir.exists():
        print(f"  WARN: no departments/ folder at {departments_dir}")
        return counts

    for dept_path in sorted(departments_dir.iterdir()):
        if not dept_path.is_dir():
            continue
        counts["depts_scanned"] += 1
        print(f"\n  === Department: {dept_path.name} ===")
        results = augment_all_existing_role_folders(dept_path, workspace_root, dry_run=dry_run)
        counts["role_folders_augmented"] += len(results)
        for r in results:
            if not r.get("dry_run"):
                counts["role_files_written"] += len(r.get("written", []))

    return counts


def main():
    parser = argparse.ArgumentParser(description="Augment existing role folders with v2.1 files")
    parser.add_argument("--company-slug", help="Process only this company slug. Defaults to all companies.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    paths = get_openclaw_paths()

    # BUG-3 FIX: resolve the REAL active workspace, not the (possibly empty)
    # company_root copy. Priority mirrors department-floor.py / qc-completeness.sh:
    #   1. paths["company_dir"] — the already-resolved active company folder
    #   2. paths["company_root"] — the parent ZHC root (scan its subdirs)
    # When company_dir resolves, process exactly that one company (its
    # departments/ are the live ones agents read). This is the fix for "scans 0
    # departments because it walked an empty /data/openclaw-master-files copy".
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
        if target.exists():
            companies.append(target)
        else:
            print(f"WARN: company slug '{args.company_slug}' not found, falling back to active company_dir")
    if not companies and company_dir and Path(company_dir).is_dir():
        # Prefer the resolved active company — its departments/ are the live tree.
        companies = [Path(company_dir)]
    if not companies and zhc_root and Path(zhc_root).is_dir():
        companies = [p for p in Path(zhc_root).iterdir() if p.is_dir()]
    if not companies:
        print(f"ERROR: no company workspace found "
              f"(company_dir={company_dir}, company_root={zhc_root}). "
              f"Has any company been built yet?")
        return 1

    total = {"depts_scanned": 0, "role_folders_augmented": 0, "role_files_written": 0, "ceos": 0}
    for company in companies:
        print(f"\n=== Company: {company.name} ===")
        result = process_company(company, dry_run=args.dry_run)
        for k in ["depts_scanned", "role_folders_augmented", "role_files_written"]:
            total[k] += result[k]
        if result["ceo_created_or_augmented"]:
            total["ceos"] += 1

    print("\n" + "=" * 60)
    print(f"Companies processed:               {len(companies)}")
    print(f"Departments scanned:               {total['depts_scanned']}")
    print(f"Role folders augmented:            {total['role_folders_augmented']}")
    print(f"v2.1 files written:                {total['role_files_written']}")
    print(f"Master Orchestrators ready:        {total['ceos']}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
