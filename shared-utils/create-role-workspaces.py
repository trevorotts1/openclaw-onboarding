#!/usr/bin/env python3
"""
Create or augment role-level workspaces inside a department.

Two operations:

1. `create_role_workspace(dept_path, role_name, workspace_root, role_metadata)`
   — Creates a NEW role folder with v2.1 files (IDENTITY.md, SOUL.md, MEMORY.md,
   HEARTBEAT.md, how-to.md stub) + symlinks (AGENTS.md, TOOLS.md, USER.md).

2. `augment_role_folder(role_path, workspace_root, role_metadata)`
   — Adds v2.1 files to an EXISTING role folder (e.g. one created by the
   pre-v2.1 `build-workforce.py:create_role_workspace` which makes folders like
   `00-chief-marketing-officer/` with `00-START-HERE.md` + SOP stubs). Augments
   in place — does not overwrite existing files.

Master Orchestrator role uses the CEO variant of the Persona Governance Override
clause; all other roles use the standard clause.

Symlinks resolve AGENTS.md / TOOLS.md / USER.md to the company workspace root so
edits propagate across every agent in the company.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared-utils"))
sys.path.insert(0, str(Path(__file__).parent.parent / "shared-utils"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared-utils"))
try:
    from detect_platform import get_openclaw_paths  # type: ignore
except ImportError:
    def get_openclaw_paths():  # type: ignore
        raise RuntimeError("detect_platform.py not on sys.path")


STANDARD_DEFERRAL = """
## Persona Governance Override

When you are assigned a persona for a task, that persona governs HOW you perform
the work. Your beliefs, voice, decision logic, quality bar, and judgment for that
task come from the persona — not from this file.

Act AS IF you ARE the persona for the duration of the task. Use their frameworks.
Use their phrasing. Hold their standards. Make the calls they would make.

This file is your fallback identity. It governs only when no persona is assigned.
When a persona is present, this file is subordinate to it.

**Order of operations:**
1. Check for an assigned persona. If present → act AS that persona.
2. If no persona is assigned → use this file.
3. In all cases: honor the company's mission (workspace SOUL.md) and the owner's
   stated values (workspace USER.md).
"""

CEO_DEFERRAL = """
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


def stub_identity(role_name: str, dept_name: str, is_ceo: bool) -> str:
    deferral = CEO_DEFERRAL if is_ceo else STANDARD_DEFERRAL
    return f"""# {role_name} — IDENTITY

**Department:** {dept_name}
**Generated:** {datetime.utcnow().isoformat()}Z

## Role
{role_name} in the {dept_name} department. Detailed responsibilities live in `how-to.md`.

## Tools
See symlinked `TOOLS.md` (shared across company).

## Behavior Rules
See symlinked `AGENTS.md` (shared across company).
{deferral}
"""


def stub_soul(role_name: str, dept_name: str, is_ceo: bool) -> str:
    deferral = CEO_DEFERRAL if is_ceo else STANDARD_DEFERRAL
    return f"""# {role_name} — SOUL

## Mission
Serve the {dept_name} department by executing this role's responsibilities at a
standard high enough to deserve the trust of the human owner.

## Voice
Mirror the owner's communication style (see workspace USER.md > Behavioral
Identity Profile). Plain, direct, no jargon unless the task domain requires it.

## Values
- Output quality beats output speed
- Honor the persona when assigned; honor the mission always
- Surface uncertainty rather than guess
- Document what you learn in MEMORY.md
{deferral}
"""


def stub_memory(role_name: str) -> str:
    return f"""# {role_name} — MEMORY

(Empty — fills with use.)

## Long-term facts
- (Updated as the role accumulates work)

## Decisions
- (Logged at the time they're made)

## What I've learned about the owner / customers
- (Captured from feedback over time)
"""


def stub_heartbeat(role_name: str, dept_name: str) -> str:
    return f"""# {role_name} — HEARTBEAT

Cadence: every 30 minutes (default).
Owner: this role
Dept: {dept_name}

## Scheduled tasks
(Empty — populated by the role's daily/weekly routines in how-to.md.)

## On startup
1. Read `how-to.md` for full procedure
2. Read inherited `AGENTS.md`, `TOOLS.md`, `USER.md` (via symlinks)
3. Check for assigned persona (if any)
4. Read your latest entries in `MEMORY.md`
"""


def stub_how_to(role_name: str, dept_name: str, is_ceo: bool) -> str:
    deferral = CEO_DEFERRAL if is_ceo else STANDARD_DEFERRAL
    return f"""# {role_name} — how-to.md (stub)

**Department:** {dept_name}
**Status:** STUB — will be replaced by the role-doc-generation sub-agent
**Generated:** {datetime.utcnow().isoformat()}Z

> This file is a placeholder. The sub-agent assigned to generate role
> documentation will replace it with the full 18-section how-to.md per the
> universal template at `23-ai-workforce-blueprint/templates/universal-how-to-template.md`.

## 1. Role Identity

### Who You Are
{role_name} in {dept_name}.

### What This Role Is NOT
(Pending sub-agent generation.)

## 2. Persona Governance Override
{deferral}

## 3-18. Pending sub-agent generation

The remaining 16 sections (Daily Operations, Weekly Operations, Monthly Operations,
Quarterly Operations, KPIs, Tools, SOPs, Quality Gates, Handoffs, Escalation Paths,
Good Examples, Bad Examples, Common Mistakes, Research Sources, Edge Cases, Update
Triggers) are generated by the role-doc-generation sub-agent.
"""


def slugify(name: str) -> str:
    s = name.lower().strip()
    out = []
    prev_dash = False
    for ch in s:
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "".join(out).strip("-")


# ============================================================
# Core operations
# ============================================================

def _write_unique_files(role_path: Path, role_name: str, dept_name: str, is_ceo: bool, force: bool = False):
    """Write unique-per-role files. If force=False, skips files that already exist."""
    files = {
        "IDENTITY.md":  stub_identity(role_name, dept_name, is_ceo),
        "SOUL.md":      stub_soul(role_name, dept_name, is_ceo),
        "MEMORY.md":    stub_memory(role_name),
        "HEARTBEAT.md": stub_heartbeat(role_name, dept_name),
        "how-to.md":    stub_how_to(role_name, dept_name, is_ceo),
    }
    written = []
    skipped = []
    for fname, content in files.items():
        fp = role_path / fname
        if fp.exists() and not force:
            skipped.append(fname)
            continue
        fp.write_text(content, encoding="utf-8")
        written.append(fname)
    return written, skipped


def _create_symlinks(role_path: Path, workspace_root: Path):
    """Create AGENTS.md / TOOLS.md / USER.md symlinks. Replaces broken symlinks."""
    for shared in ["AGENTS.md", "TOOLS.md", "USER.md"]:
        link_path = role_path / shared
        target = workspace_root / shared
        try:
            if link_path.is_symlink() or link_path.exists():
                link_path.unlink()
            link_path.symlink_to(target)
        except OSError as e:
            print(f"  WARN: symlink {shared} in {role_path}: {e}", file=sys.stderr)
            # Last-resort: write a stub note rather than fail
            link_path.write_text(
                f"# {shared} — see workspace root\n\n"
                f"This file should be a symlink to {target}.\n"
            )


def create_role_workspace(dept_path: Path, role_name: str, workspace_root: Path,
                           role_metadata: dict = None) -> Path:
    """
    Create a NEW role-level workspace folder inside dept_path.

    If a folder for this role already exists (matched by slug), augment it in
    place rather than creating a duplicate.
    """
    role_metadata = role_metadata or {}
    slug = slugify(role_name)
    role_path = dept_path / slug
    is_ceo = role_metadata.get("is_ceo", False) or slug == "master-orchestrator"
    dept_name = dept_path.name.replace("-dept", "").replace("-", " ").title()

    role_path.mkdir(parents=True, exist_ok=True)
    _write_unique_files(role_path, role_name, dept_name, is_ceo, force=False)
    _create_symlinks(role_path, workspace_root)
    return role_path


def augment_role_folder(role_path: Path, workspace_root: Path,
                         role_metadata: dict = None) -> dict:
    """
    Add v2.1 files to an EXISTING role folder (e.g. one created by the pre-v2.1
    build-workforce.py `create_role_workspace` which made folders like
    `00-chief-marketing-officer/` with `00-START-HERE.md` and SOP stubs).

    In-place: existing files (including pre-v2.1 files like 00-START-HERE.md) are
    preserved. Missing v2.1 files are added.

    Returns: dict with 'written' (list), 'skipped' (list), 'symlinks_created' (bool).
    """
    role_metadata = role_metadata or {}

    # Detect role name from folder name (strip leading number prefix if present)
    folder_name = role_path.name
    # Strip leading "NN-" or "N-" if present
    name_part = folder_name
    if "-" in folder_name:
        head, _, rest = folder_name.partition("-")
        if head.isdigit():
            name_part = rest
    role_name = role_metadata.get("name") or name_part.replace("-", " ").title()

    is_ceo = role_metadata.get("is_ceo", False) or "master-orchestrator" in folder_name.lower()
    dept_path = role_path.parent
    dept_name = dept_path.name.replace("-dept", "").replace("-", " ").title()

    role_path.mkdir(parents=True, exist_ok=True)
    written, skipped = _write_unique_files(role_path, role_name, dept_name, is_ceo, force=False)
    _create_symlinks(role_path, workspace_root)

    return {
        "role_path": str(role_path),
        "role_name": role_name,
        "is_ceo": is_ceo,
        "written": written,
        "skipped": skipped,
        "symlinks_created": True,
    }


def build_all_roles_for_dept(dept_path: Path, dept_id: str, roles: list,
                              workspace_root: Path) -> list:
    """Create role workspaces for every role in the list. Returns list of paths."""
    created = []
    for role in roles:
        role_path = create_role_workspace(dept_path, role["name"], workspace_root, role_metadata=role)
        created.append(role_path)
        try:
            rel = role_path.relative_to(workspace_root.parent.parent)
        except Exception:
            rel = role_path
        print(f"  ✓ Created role workspace: {rel}")
    return created


def augment_all_existing_role_folders(dept_path: Path, workspace_root: Path,
                                       dry_run: bool = False) -> list:
    """
    Walk every subfolder of dept_path that looks like a role folder and augment
    it with v2.1 files. Skips non-role subfolders (memory/, devils-advocate/,
    anything starting with a dot).
    """
    if not dept_path.exists():
        return []
    augmented = []
    for entry in dept_path.iterdir():
        if not entry.is_dir():
            continue
        # Skip non-role subfolders
        if entry.name in ("memory", "devils-advocate") or entry.name.startswith("."):
            continue
        if entry.name.startswith("_"):
            continue
        if dry_run:
            print(f"  [DRY-RUN] would augment: {entry.relative_to(dept_path.parent)}")
            augmented.append({"role_path": str(entry), "dry_run": True})
            continue
        result = augment_role_folder(entry, workspace_root)
        augmented.append(result)
        if result["written"]:
            print(f"  + {entry.name}: +{len(result['written'])} files ({', '.join(result['written'])})")
        elif result["skipped"]:
            print(f"  = {entry.name}: all v2.1 files present, symlinks refreshed")
    return augmented


def main():
    parser = argparse.ArgumentParser(description="Create or augment role-level workspaces")
    parser.add_argument("--dept-path", required=True, help="Path to the department workspace")
    parser.add_argument("--roles-json", help="JSON file with [{name, type, is_ceo}, ...]. If omitted, augments existing folders instead.")
    parser.add_argument("--workspace-root", help="Override workspace root (default: detect)")
    parser.add_argument("--augment-existing", action="store_true", help="Augment existing role folders instead of creating from roles list")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dept_path = Path(args.dept_path)
    if args.workspace_root:
        workspace_root = Path(args.workspace_root)
    else:
        paths = get_openclaw_paths()
        workspace_root = paths["workspace"]

    if args.augment_existing or not args.roles_json:
        results = augment_all_existing_role_folders(dept_path, workspace_root, dry_run=args.dry_run)
        print(f"\nAugmented {len(results)} existing role folders.")
    else:
        with open(args.roles_json, encoding="utf-8") as f:
            roles = json.load(f)
        created = build_all_roles_for_dept(dept_path, dept_path.name, roles, workspace_root)
        print(f"\nCreated {len(created)} role workspaces in {dept_path.name}")


if __name__ == "__main__":
    main()
