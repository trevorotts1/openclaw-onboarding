#!/usr/bin/env python3
"""
Create / augment role-level workspaces inside a department.

v10.6.1 (Wave 5b) changes:
  - Renamed from create-role-workspaces.py (hyphens are not valid in Python
    import names — Wave 4's import was broken).
  - Added augment_role_folder() and augment_all_existing_role_folders() —
    these were referenced by post-build-role-workspaces.py since Wave 4 but
    never actually written.
  - Added library template-fill: when creating a role's how-to.md, check
    templates/role-library/_index.json for a matching pre-written doc. If
    one exists, read it from templates/role-library/[dept]/[slug].md, fill
    company-specific tokens, and use that instead of the stub. Falls back
    to the stub when no library match.

Per-role workspace layout:
    [DEPT]/[role-slug]/
    ├── IDENTITY.md         (unique, with Persona Governance Override clause)
    ├── SOUL.md             (unique, with Persona Governance Override clause)
    ├── MEMORY.md           (unique, starts empty)
    ├── HEARTBEAT.md        (unique)
    ├── how-to.md           (from library if available, else stub)
    ├── AGENTS.md → workspace_root/AGENTS.md   (symlink)
    ├── TOOLS.md  → workspace_root/TOOLS.md    (symlink)
    └── USER.md   → workspace_root/USER.md     (symlink)

For master-orchestrator, SOUL.md and IDENTITY.md use the CEO variant of the
deferral clause (mission/owner override persona on conflict).
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared-utils"))
try:
    from detect_platform import get_openclaw_paths
except ImportError:
    def get_openclaw_paths():
        raise RuntimeError("detect_platform.py not on sys.path")


# ─── DEFERRAL CLAUSES ─────────────────────────────────────────────────────────

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


# ─── STUB GENERATORS (used as fallback when library has no match) ────────────

def stub_identity(role_name, dept_name, is_ceo):
    deferral = CEO_DEFERRAL if is_ceo else STANDARD_DEFERRAL
    return f"""# {role_name} — IDENTITY

**Department:** {dept_name}
**Generated:** {_now_iso()}

## Role
{role_name} in the {dept_name} department. Detailed responsibilities live in `how-to.md`.

## Tools
See symlinked `TOOLS.md` (shared across company).

## Behavior Rules
See symlinked `AGENTS.md` (shared across company).
{deferral}
"""


def stub_soul(role_name, dept_name, is_ceo):
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


def stub_memory(role_name):
    return f"""# {role_name} — MEMORY

(Empty — fills with use.)

## Long-term facts
- (Updated as the role accumulates work)

## Decisions
- (Logged at the time they're made)

## What I've learned about the owner / customers
- (Captured from feedback over time)
"""


def stub_heartbeat(role_name, dept_name):
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


def stub_how_to(role_name, dept_name, is_ceo):
    """Placeholder used when the library has no matching doc."""
    deferral = CEO_DEFERRAL if is_ceo else STANDARD_DEFERRAL
    return f"""# {role_name} — how-to.md (stub)

**Department:** {dept_name}
**Status:** STUB — no pre-written library doc matched. Sub-agent should regenerate.
**Generated:** {_now_iso()}

> This file is a placeholder. The role-doc-generation sub-agent will replace it
> with the full 19-section how-to.md per the universal template at
> `23-ai-workforce-blueprint/templates/universal-how-to-template.md`.

## 1. Role Identity

### Who You Are
{role_name} in {dept_name}.

### What This Role Is NOT
(Pending sub-agent generation.)

## 2. Persona Governance Override
{deferral}

## 3-19. Pending sub-agent generation
"""


# ─── LIBRARY TEMPLATE-FILL (Wave 5b) ──────────────────────────────────────────

def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _resolve_skill_dir():
    """Return absolute path to 23-ai-workforce-blueprint inside the install."""
    try:
        paths = get_openclaw_paths()
        return paths["skills"] / "23-ai-workforce-blueprint"
    except Exception:
        # Fallback: assume this file is at skills/23-ai-workforce-blueprint/scripts/
        return Path(__file__).resolve().parent.parent


def library_lookup(role_slug, dept_slug):
    """
    Return (library_doc_path, role_entry_dict) or (None, None) if no match.
    Reads templates/role-library/_index.json from the installed skill folder.
    """
    skill_dir = _resolve_skill_dir()
    index_path = skill_dir / "templates" / "role-library" / "_index.json"
    if not index_path.exists():
        return None, None
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [Wave 5b] WARN: could not parse _index.json: {e}", file=sys.stderr)
        return None, None

    # Normalize dept slug (strip "-dept" suffix, lowercase)
    dept_key = dept_slug.replace("-dept", "").strip().lower()

    for role_entry in index.get("roles", []):
        if (role_entry.get("dept", "").lower() == dept_key
                and role_entry.get("slug", "").lower() == role_slug.lower()):
            doc_rel = role_entry.get("path", "")
            doc_abs = skill_dir / doc_rel
            if doc_abs.exists():
                return doc_abs, role_entry
            # Fallback: built from convention
            fallback = skill_dir / "templates" / "role-library" / role_entry["dept"] / f"{role_entry['slug']}.md"
            if fallback.exists():
                return fallback, role_entry
            return None, role_entry
    return None, None


def _load_company_config():
    """Read company-config.json from the workspace, or {} if missing."""
    try:
        paths = get_openclaw_paths()
        cfg_path = paths.get("company_config")
        if cfg_path and Path(cfg_path).exists():
            return json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _load_user_md_excerpt():
    """Pull a short owner-profile excerpt from workspace USER.md for tokens."""
    try:
        paths = get_openclaw_paths()
        user_md = paths.get("user_md")
        if user_md and Path(user_md).exists():
            text = Path(user_md).read_text(encoding="utf-8")
            return text[:2000]
    except Exception:
        pass
    return ""


def _compute_revenue_cascade(yearly):
    """Return monthly/weekly/daily/quarterly given yearly. Empty dict if no yearly."""
    try:
        y = float(str(yearly).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return {}
    return {
        "YEARLY_GOAL": f"${y:,.0f}",
        "QUARTERLY_TARGET": f"${y/4:,.0f}",
        "MONTHLY_TARGET": f"${y/12:,.0f}",
        "WEEKLY_TARGET": f"${y/52:,.0f}",
        "DAILY_TARGET": f"${y/250:,.0f}",  # 250 working days
    }


def fill_tokens(content, role_name, dept_name, is_ceo, role_entry=None):
    """
    Replace {{TOKEN}} placeholders in `content` with values derived from the
    company config + USER.md + role metadata. Tokens that have no source value
    are left in place (the sub-agent or runtime can fill later).
    """
    cfg = _load_company_config()

    # Pull token values from config — accept multiple key variants
    company_name = (cfg.get("companyName") or cfg.get("company_name")
                    or cfg.get("name") or "")
    company_industry = (cfg.get("companyIndustry") or cfg.get("industry")
                        or cfg.get("industryVertical") or "")
    yearly = (cfg.get("yearlyRevenueGoal") or cfg.get("yearly_revenue_goal")
              or cfg.get("revenueGoal") or cfg.get("yearlyGoal") or "")

    cascade = _compute_revenue_cascade(yearly)

    director = "Master Orchestrator" if is_ceo else f"Director of {dept_name}"

    tokens = {
        "COMPANY_NAME": company_name,
        "COMPANY_INDUSTRY": company_industry,
        "INDUSTRY_VERTICAL": company_industry,
        "ROLE_TITLE": role_name,
        "DEPARTMENT_NAME": dept_name,
        "DIRECTOR_OR_MASTER_ORCHESTRATOR": director,
        "ISO_DATE": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "ASSIGNED_PERSONA": "—",
        'CURRENTLY_ASSIGNED_PERSONA or "—"': "—",
        "full-time-permanent": "full-time-permanent",
        "on-call": "on-call",
    }
    tokens.update(cascade)

    out = content
    for key, val in tokens.items():
        if not val:
            continue
        out = out.replace("{{" + key + "}}", str(val))

    return out


def try_library_fill(role_name, dept_path, is_ceo):
    """
    Look up the library for a pre-written how-to.md, token-fill it, and return
    the filled content. Returns None if no library match (caller falls back
    to stub_how_to).
    """
    role_slug = slugify(role_name)
    dept_slug = dept_path.name.replace("-dept", "").strip().lower()

    doc_path, role_entry = library_lookup(role_slug, dept_slug)
    if not doc_path:
        return None

    try:
        raw = doc_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  [Wave 5b] WARN: failed reading {doc_path}: {e}", file=sys.stderr)
        return None

    dept_name = dept_path.name.replace("-dept", "").replace("-", " ").title()
    filled = fill_tokens(raw, role_name, dept_name, is_ceo, role_entry=role_entry)

    # Stamp the front so reviewers can tell at a glance this came from library
    header = (f"<!-- Filled from role-library v{role_entry.get('version', '?')} on "
              f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')} -->\n")
    return header + filled


# ─── PATH / NAMING HELPERS ────────────────────────────────────────────────────

def slugify(name):
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


# ─── CORE: CREATE A SINGLE ROLE WORKSPACE ─────────────────────────────────────

def create_role_workspace(dept_path, role_name, workspace_root, role_metadata=None):
    """
    Create a single role-level workspace inside dept_path. Uses library
    template-fill for how-to.md when a matching doc exists; falls back to
    stub otherwise.
    """
    role_metadata = role_metadata or {}
    role_slug = slugify(role_name)
    role_path = Path(dept_path) / role_slug
    role_path.mkdir(parents=True, exist_ok=True)

    is_ceo = (role_metadata.get("is_ceo", False)
              or role_slug == "master-orchestrator")
    dept_name = Path(dept_path).name.replace("-dept", "").replace("-", " ").title()

    # Unique identity files
    (role_path / "IDENTITY.md").write_text(
        stub_identity(role_name, dept_name, is_ceo), encoding="utf-8")
    (role_path / "SOUL.md").write_text(
        stub_soul(role_name, dept_name, is_ceo), encoding="utf-8")
    (role_path / "MEMORY.md").write_text(
        stub_memory(role_name), encoding="utf-8")
    (role_path / "HEARTBEAT.md").write_text(
        stub_heartbeat(role_name, dept_name), encoding="utf-8")

    # how-to.md: library first, stub fallback
    filled = try_library_fill(role_name, Path(dept_path), is_ceo)
    if filled is not None:
        (role_path / "how-to.md").write_text(filled, encoding="utf-8")
        print(f"  [library-fill] {role_slug} ← templates/role-library/...")
    else:
        (role_path / "how-to.md").write_text(
            stub_how_to(role_name, dept_name, is_ceo), encoding="utf-8")

    # Symlinks for shared files
    for shared in ["AGENTS.md", "TOOLS.md", "USER.md"]:
        link_path = role_path / shared
        target = Path(workspace_root) / shared
        try:
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
            link_path.symlink_to(target)
        except OSError as e:
            print(f"  WARN: could not symlink {shared} in {role_path}: {e}",
                  file=sys.stderr)
            link_path.write_text(
                f"# {shared} — see workspace root\n\n"
                f"Symlink to {target} failed. Re-run create_role_workspaces.py "
                f"with appropriate permissions.\n")

    return role_path


# ─── AUGMENT EXISTING ROLE FOLDERS (Wave 5b: previously missing!) ────────────

V21_REQUIRED = ["IDENTITY.md", "SOUL.md", "MEMORY.md", "HEARTBEAT.md", "how-to.md"]
V21_SYMLINKS = ["AGENTS.md", "TOOLS.md", "USER.md"]


def augment_role_folder(role_path, workspace_root, role_metadata=None):
    """
    Add v2.1 files to an existing role folder if missing. Idempotent.
    Returns {"written": [filenames], "symlinked": [filenames]}.
    """
    role_path = Path(role_path)
    workspace_root = Path(workspace_root)
    role_metadata = role_metadata or {}

    if not role_path.is_dir():
        return {"written": [], "symlinked": [], "error": f"not a directory: {role_path}"}

    role_slug = role_path.name
    # Strip leading numeric prefix like "00-" or "12-"
    name_for_display = re.sub(r"^\d+-", "", role_slug)
    role_name = role_metadata.get("name") or name_for_display.replace("-", " ").title()
    is_ceo = (role_metadata.get("is_ceo", False)
              or role_slug == "master-orchestrator")
    dept_path = role_path.parent
    dept_name = dept_path.name.replace("-dept", "").replace("-", " ").title()

    written = []
    for filename in V21_REQUIRED:
        fpath = role_path / filename
        if fpath.exists():
            continue
        if filename == "IDENTITY.md":
            fpath.write_text(stub_identity(role_name, dept_name, is_ceo), encoding="utf-8")
        elif filename == "SOUL.md":
            fpath.write_text(stub_soul(role_name, dept_name, is_ceo), encoding="utf-8")
        elif filename == "MEMORY.md":
            fpath.write_text(stub_memory(role_name), encoding="utf-8")
        elif filename == "HEARTBEAT.md":
            fpath.write_text(stub_heartbeat(role_name, dept_name), encoding="utf-8")
        elif filename == "how-to.md":
            filled = try_library_fill(role_name, dept_path, is_ceo)
            if filled is not None:
                fpath.write_text(filled, encoding="utf-8")
                print(f"  [library-fill] {role_slug} ← templates/role-library/...")
            else:
                fpath.write_text(stub_how_to(role_name, dept_name, is_ceo), encoding="utf-8")
        written.append(filename)

    symlinked = []
    for shared in V21_SYMLINKS:
        link_path = role_path / shared
        if link_path.exists() or link_path.is_symlink():
            continue
        target = workspace_root / shared
        try:
            link_path.symlink_to(target)
            symlinked.append(shared)
        except OSError as e:
            print(f"  WARN: could not symlink {shared}: {e}", file=sys.stderr)

    return {"written": written, "symlinked": symlinked}


def augment_all_existing_role_folders(dept_path, workspace_root, dry_run=False):
    """
    Walk every subfolder of dept_path. For each subfolder that looks like a role
    folder (not a known special name), augment it.
    Returns a list of {"role": slug, "written": [...], "symlinked": [...]}.
    """
    dept_path = Path(dept_path)
    workspace_root = Path(workspace_root)
    SKIP_NAMES = {"memory", "devils-advocate", "_archive", "_index",
                  "_compliance_audit", "_pending_rewrite", "_stage1_drafts"}

    results = []
    for entry in sorted(dept_path.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in SKIP_NAMES or entry.name.startswith("."):
            continue

        if dry_run:
            results.append({"role": entry.name, "written": [], "symlinked": [], "dry_run": True})
            print(f"    [DRY-RUN] would augment {entry.name}")
            continue

        result = augment_role_folder(entry, workspace_root)
        result["role"] = entry.name
        results.append(result)
        if result["written"] or result["symlinked"]:
            extras = []
            if result["written"]:
                extras.append(f"+files: {','.join(result['written'])}")
            if result["symlinked"]:
                extras.append(f"+links: {','.join(result['symlinked'])}")
            print(f"    {entry.name}: {' | '.join(extras)}")
    return results


# ─── BUILD ALL ROLES FOR A DEPT (used by build-workforce.py) ──────────────────

def build_all_roles_for_dept(dept_path, dept_id, roles, workspace_root):
    """
    Create all role workspaces for a department. Each role gets library
    template-fill on its how-to.md when a matching library doc exists.
    """
    created = []
    for role in roles:
        role_path = create_role_workspace(
            dept_path, role["name"], workspace_root, role_metadata=role)
        created.append(role_path)
        try:
            rel = role_path.relative_to(Path(workspace_root).parent.parent)
        except ValueError:
            rel = role_path
        print(f"  ✓ Created role workspace: {rel}")
    return created


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Create or augment role-level workspaces inside a department.")
    parser.add_argument("--dept-path", help="Path to the department workspace")
    parser.add_argument("--roles-json", help="JSON file with list of {name, type, is_ceo}")
    parser.add_argument("--workspace-root", help="Override workspace root (default: detect)")
    parser.add_argument("--augment", action="store_true",
                        help="Augment all existing role folders in --dept-path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.dept_path:
        parser.error("--dept-path is required")
    dept_path = Path(args.dept_path)

    if args.workspace_root:
        workspace_root = Path(args.workspace_root)
    else:
        paths = get_openclaw_paths()
        workspace_root = paths["workspace"]

    if args.augment:
        results = augment_all_existing_role_folders(dept_path, workspace_root,
                                                     dry_run=args.dry_run)
        print(f"\nAugmented {len(results)} role folders in {dept_path.name}")
        return 0

    if not args.roles_json:
        parser.error("--roles-json is required unless --augment is used")
    with open(args.roles_json, encoding="utf-8") as f:
        roles = json.load(f)

    created = build_all_roles_for_dept(dept_path, dept_path.name, roles, workspace_root)
    print(f"\nCreated {len(created)} role workspaces in {dept_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
