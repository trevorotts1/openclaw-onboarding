#!/usr/bin/env python3
"""
Walk every existing zero-human-company workspace and append the appropriate
Persona Governance Override clause to any SOUL.md or IDENTITY.md that doesn't
have it yet.

Idempotent — safe to run multiple times. Reports counts of patches applied.

Master Orchestrator (CEO) gets the special CEO clause. Every other agent gets
the standard clause.

Usage:
    python3 shared-utils/migrate-deferral-clauses.py [--dry-run]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from detect_platform import get_openclaw_paths

STANDARD_CLAUSE_MARKER = "## Persona Governance Framework"
CEO_CLAUSE_MARKER = "## Persona Governance — CEO Mode"

STANDARD_CLAUSE = """

## Persona Governance Framework

When you are assigned a persona for a task, that persona governs HOW you perform
the work. Your beliefs, voice, decision logic, quality bar, and judgment for that
task come from the persona — not from this file.

This file is your primary identity. It governs when no persona is assigned. When a persona is present, use its frameworks as a tool -- not as a replacement for your own judgment or accountability.

**Order of operations when picking up a task:**
1. Check for an assigned persona. If present → apply that persona's frameworks and standards as a reference, not as an identity.
2. If no persona is assigned → use this file (SOUL.md / IDENTITY.md / how-to.md).
3. In all cases: honor the company's mission (workspace SOUL.md) and the owner's
   stated values (workspace USER.md).
"""

CEO_CLAUSE = """

## Persona Governance — CEO Mode

As the CEO / Master Orchestrator, you do NOT fully defer to assigned personas.
You use them as INPUT, but you remain accountable to the company's mission and
the owner's values at all times — those override the persona when there is conflict.

When a persona is assigned to a CEO-level task:
1. Read the persona's frameworks, voice, and decision logic. Consider them.
2. Compare to mission (workspace SOUL.md) and owner profile (workspace USER.md).
3. Where the persona ALIGNS → embody it for the task.
4. Where the persona CONFLICTS → mission and owner WIN. Log conflict in MEMORY.md.
5. Your own identity governs when no persona is assigned.

You are the protector of the mission. Personas are tools you use, not authorities
you serve.
"""

def is_ceo_file(file_path: Path) -> bool:
    """A file belongs to the CEO if its path includes 'master-orchestrator'."""
    return "master-orchestrator" in str(file_path).lower()

def migrate_file(file_path: Path, dry_run: bool = False) -> str:
    """Returns one of: 'patched', 'already_has_clause', 'wrong_clause_fixed', 'error'."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  ERROR reading {file_path}: {e}", file=sys.stderr)
        return "error"

    is_ceo = is_ceo_file(file_path)
    target_marker = CEO_CLAUSE_MARKER if is_ceo else STANDARD_CLAUSE_MARKER
    target_clause = CEO_CLAUSE if is_ceo else STANDARD_CLAUSE

    # Already correct
    if target_marker in content:
        return "already_has_clause"

    # Wrong clause present? (CEO file has standard clause, or vice versa)
    wrong_marker = STANDARD_CLAUSE_MARKER if is_ceo else CEO_CLAUSE_MARKER
    if wrong_marker in content:
        # Strip wrong clause, append correct one
        idx = content.index(wrong_marker)
        content = content[:idx].rstrip() + target_clause
        if not dry_run:
            file_path.write_text(content, encoding="utf-8")
        return "wrong_clause_fixed"

    # Missing — append
    if not content.endswith("\n"):
        content += "\n"
    content += target_clause
    if not dry_run:
        file_path.write_text(content, encoding="utf-8")
    return "patched"

def migrate_workspace(zhc_root: Path, dry_run: bool = False) -> dict:
    counts = {
        "patched": 0,
        "already_has_clause": 0,
        "wrong_clause_fixed": 0,
        "error": 0,
        "scanned": 0,
    }
    if not zhc_root.exists():
        print(f"Zero-human-company root not found: {zhc_root}")
        return counts

    for company in zhc_root.iterdir():
        if not company.is_dir():
            continue
        print(f"  Company: {company.name}")
        for file_path in company.rglob("SOUL.md"):
            counts["scanned"] += 1
            result = migrate_file(file_path, dry_run=dry_run)
            counts[result] += 1
            if result in ("patched", "wrong_clause_fixed"):
                kind = "CEO" if is_ceo_file(file_path) else "Standard"
                tag = "[DRY-RUN] " if dry_run else ""
                print(f"    {tag}{result.upper()} ({kind}): {file_path.relative_to(zhc_root)}")
        for file_path in company.rglob("IDENTITY.md"):
            counts["scanned"] += 1
            result = migrate_file(file_path, dry_run=dry_run)
            counts[result] += 1
            if result in ("patched", "wrong_clause_fixed"):
                kind = "CEO" if is_ceo_file(file_path) else "Standard"
                tag = "[DRY-RUN] " if dry_run else ""
                print(f"    {tag}{result.upper()} ({kind}): {file_path.relative_to(zhc_root)}")
    return counts

def main():
    parser = argparse.ArgumentParser(description="Append Persona Governance Override clause to all SOUL.md and IDENTITY.md files in zero-human-company workspaces. Idempotent.")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing.")
    args = parser.parse_args()

    paths = get_openclaw_paths()
    print(f"Platform: {paths['platform']}")
    print(f"Zero-human-company root: {paths['company_root']}")
    if args.dry_run:
        print("DRY-RUN MODE — no files will be modified")
    print()

    counts = migrate_workspace(paths["company_root"], dry_run=args.dry_run)

    print()
    print("=" * 60)
    print(f"Scanned:           {counts['scanned']} files")
    print(f"Patched (new):     {counts['patched']}")
    print(f"Fixed (wrong):     {counts['wrong_clause_fixed']}")
    print(f"Already had:       {counts['already_has_clause']}")
    print(f"Errors:            {counts['error']}")
    print("=" * 60)

    return 1 if counts["error"] > 0 else 0

if __name__ == "__main__":
    sys.exit(main())
