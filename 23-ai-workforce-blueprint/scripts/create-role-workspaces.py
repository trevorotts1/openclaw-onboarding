#!/usr/bin/env python3
"""
Create role-level workspaces inside an existing department workspace.

Extends the v9.6.1 department-level symlink pattern to the role level.

Per role within each department:
    [DEPT]/[role-slug]/
    ├── IDENTITY.md         (unique)
    ├── SOUL.md             (unique, with Persona Governance Override clause)
    ├── MEMORY.md           (unique, starts empty)
    ├── HEARTBEAT.md        (unique)
    ├── how-to.md           (universal 18-section template — see templates/universal-how-to-template.md)
    ├── AGENTS.md → workspace_root/AGENTS.md  (symlink)
    ├── TOOLS.md  → workspace_root/TOOLS.md   (symlink)
    └── USER.md   → workspace_root/USER.md    (symlink)

For the master-orchestrator role, the SOUL.md and IDENTITY.md use the CEO variant
of the deferral clause (mission/owner override persona on conflict).

This module is intentionally separate from build-workforce.py so existing
build-workforce code can stay stable. Call this from build-workforce.py after
create_department_workspace() returns:

    from create_role_workspaces import create_role_workspace, build_all_roles_for_dept
    build_all_roles_for_dept(dept_path, dept_id, roles, workspace_root, master_orchestrator=False)
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared-utils"))
try:
    from detect_platform import get_openclaw_paths
except ImportError:
    def get_openclaw_paths():
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
    """
    Placeholder how-to.md. The real one is generated by the role-doc-generation
    sub-agent per the universal template. This stub is what exists between
    workspace creation and the sub-agent run.
    """
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
    # Replace whitespace and punctuation with hyphens
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


def create_role_workspace(dept_path: Path, role_name: str, workspace_root: Path,
                          role_metadata: dict = None) -> Path:
    """
    Create a single role-level workspace inside dept_path.

    Args:
        dept_path: Path to the department workspace
        role_name: Human-readable role name (e.g., "Director of Marketing")
        workspace_root: The company workspace root (where shared MD files live)
        role_metadata: Optional dict with 'type' (full-time-permanent | on-call), 'is_ceo' (bool)

    Returns:
        Path to the created role folder.
    """
    role_metadata = role_metadata or {}
    role_slug = slugify(role_name)
    role_path = dept_path / role_slug
    role_path.mkdir(parents=True, exist_ok=True)

    is_ceo = role_metadata.get("is_ceo", False) or role_slug == "master-orchestrator"
    dept_name = dept_path.name.replace("-dept", "").replace("-", " ").title()

    # Unique files
    (role_path / "IDENTITY.md").write_text(stub_identity(role_name, dept_name, is_ceo), encoding="utf-8")
    (role_path / "SOUL.md").write_text(stub_soul(role_name, dept_name, is_ceo), encoding="utf-8")
    (role_path / "MEMORY.md").write_text(stub_memory(role_name), encoding="utf-8")
    (role_path / "HEARTBEAT.md").write_text(stub_heartbeat(role_name, dept_name), encoding="utf-8")
    (role_path / "how-to.md").write_text(stub_how_to(role_name, dept_name, is_ceo), encoding="utf-8")

    # Symlinks for shared files
    for shared in ["AGENTS.md", "TOOLS.md", "USER.md"]:
        link_path = role_path / shared
        target = workspace_root / shared
        try:
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
            link_path.symlink_to(target)
        except OSError as e:
            print(f"  WARN: could not symlink {shared} in {role_path}: {e}", file=sys.stderr)
            # Fall back to writing a stub note (don't duplicate the content)
            link_path.write_text(f"# {shared} — see workspace root\n\nThis file should be a symlink to {target}. Symlink creation failed; please run create-role-workspaces.py with appropriate permissions.\n")

    return role_path


def build_all_roles_for_dept(dept_path: Path, dept_id: str, roles: list,
                              workspace_root: Path) -> list:
    """
    Create all role workspaces for a department.

    Args:
        dept_path: dept workspace path
        dept_id: dept slug
        roles: list of dicts with 'name', optionally 'type' and 'is_ceo'
        workspace_root: company workspace root

    Returns:
        List of created role paths.
    """
    created = []
    for role in roles:
        role_path = create_role_workspace(
            dept_path,
            role["name"],
            workspace_root,
            role_metadata=role,
        )
        created.append(role_path)
        print(f"  ✓ Created role workspace: {role_path.relative_to(workspace_root.parent.parent)}")
    return created


def main():
    parser = argparse.ArgumentParser(description="Create role-level workspaces inside a department.")
    parser.add_argument("--dept-path", required=True, help="Path to the department workspace")
    parser.add_argument("--roles-json", required=True, help="JSON file with list of {name, type, is_ceo}")
    parser.add_argument("--workspace-root", help="Override workspace root (default: detect)")
    args = parser.parse_args()

    dept_path = Path(args.dept_path)
    if args.workspace_root:
        workspace_root = Path(args.workspace_root)
    else:
        paths = get_openclaw_paths()
        workspace_root = paths["workspace"]

    with open(args.roles_json, encoding="utf-8") as f:
        roles = json.load(f)

    created = build_all_roles_for_dept(dept_path, dept_path.name, roles, workspace_root)
    print(f"\nCreated {len(created)} role workspaces in {dept_path.name}")


if __name__ == "__main__":
    main()
