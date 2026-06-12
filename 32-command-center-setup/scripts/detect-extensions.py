#!/usr/bin/env python3
"""
detect-extensions.py — Skill 32 Command Center Setup

PURPOSE
    Compares the current role-library _index.json + on-disk SOPs + persona
    registry against a saved last-sync manifest (last-sync.json) and emits
    the delta: what is NEW since the last sync run.

OUTPUT FORMAT (stdout)
    NEW: <dept-slug>           — new department (back-compat alias: NEW-DEPT:)
    NEW-DEPT: <dept-slug>      — new department
    NEW-ROLE: <dept>/<role>    — new role within an existing dept
    NEW-SOP: <dept>/<sop-slug> — new SOP (dept-level or role-level)
    NEW-PERSONA: <slug>        — new persona in persona-categories.json
    UNTAGGED: <slug>           — persona with empty domain[] OR perspective[]
    SKIP: <dept-slug>          — already-synced dept (verbose only)
    INFO: <message>            — informational line (verbose only)

    Exit 0 = success (even if no new entities)
    Exit 1 = error (malformed index or unreadable files)

USAGE
    python3 detect-extensions.py \\
        --index  /path/to/_index.json \\
        [--last-sync /path/to/last-sync.json] \\
        [--workspace-root /path/to/departments/] \\
        [--persona-categories /path/to/persona-categories.json] \\
        [--verbose]
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone


def load_json(path: str, label: str, required: bool = True) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        if required:
            print(f"INFO: {label} not found at {path} — treating as empty baseline",
                  flush=True)
        return {}
    except json.JSONDecodeError as e:
        print(f"ERROR: Cannot parse {label} at {path}: {e}", file=sys.stderr)
        sys.exit(1)


def find_workspace_depts_dir() -> Path | None:
    """Locate the on-disk departments directory (auto-detect)."""
    candidates = [
        Path("/data/.openclaw/workspace/agents/main/departments"),
        Path.home() / ".openclaw/workspace/agents/main/departments",
        Path("/data/.openclaw/workspace/departments"),
        Path.home() / ".openclaw/workspace/departments",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def find_persona_categories_path() -> Path | None:
    """Locate persona-categories.json via canonical resolver order (§1.7)."""
    candidates = [
        Path("/data/.openclaw/workspace/data/coaching-personas/persona-categories.json"),
        Path.home() / ".openclaw/workspace/data/coaching-personas/persona-categories.json",
        Path("/data/.openclaw/workspace/coaching-personas/persona-categories.json"),
        Path.home() / ".openclaw/workspace/coaching-personas/persona-categories.json",
        Path.home() / "clawd/coaching-personas/persona-categories.json",
        Path("/data/.openclaw/skills/22-book-to-persona-coaching-leadership-system/persona-categories.json"),
        Path.home() / ".openclaw/skills/22-book-to-persona-coaching-leadership-system/persona-categories.json",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def scan_on_disk_sops(depts_dir: Path | None) -> list[str]:
    """Return sorted list of '<dept>/<sop-slug>' for all on-disk SOP files."""
    if not depts_dir or not depts_dir.is_dir():
        return []
    sop_slugs = []
    for dept_dir in sorted(depts_dir.iterdir()):
        if not dept_dir.is_dir() or dept_dir.name.startswith("."):
            continue
        dept = dept_dir.name
        # Dept-level SOPs
        dept_sop_dir = dept_dir / "SOP"
        if dept_sop_dir.is_dir():
            for sop_file in sorted(dept_sop_dir.glob("*.md")):
                if sop_file.name == "00-INDEX.md":
                    continue
                stem = sop_file.stem
                parts = stem.split("-", 1)
                slug = parts[1] if (len(parts) == 2 and parts[0].isdigit()) else stem
                sop_slugs.append(f"{dept}/{slug}")
        # Role-level SOPs
        roles_dir = dept_dir / "roles"
        if roles_dir.is_dir():
            for role_dir in sorted(roles_dir.iterdir()):
                if not role_dir.is_dir() or role_dir.name.startswith("."):
                    continue
                role_sop_dir = role_dir / "SOP"
                if role_sop_dir.is_dir():
                    for sop_file in sorted(role_sop_dir.glob("*.md")):
                        if sop_file.name == "00-INDEX.md":
                            continue
                        stem = sop_file.stem
                        parts = stem.split("-", 1)
                        slug = parts[1] if (len(parts) == 2 and parts[0].isdigit()) else stem
                        sop_slugs.append(f"{dept}/{slug}")
    return sorted(set(sop_slugs))


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect role-library extension delta")
    parser.add_argument("--index",     required=True,
                        help="Path to role-library _index.json (current truth)")
    parser.add_argument("--last-sync", default=None,
                        help="Path to last-sync.json (prior sync state)")
    parser.add_argument("--workspace-root", default=None,
                        help="Path to workspace departments dir (auto-detected if absent)")
    parser.add_argument("--persona-categories", default=None,
                        help="Path to persona-categories.json (auto-detected if absent)")
    parser.add_argument("--verbose",   action="store_true",
                        help="Also emit SKIP: lines for already-synced depts")
    args = parser.parse_args()

    # ── Load current index ───────────────────────────────────────────────────
    index = load_json(args.index, "_index.json")
    current_depts: set[str] = set(index.get("departments", {}).keys())
    current_roles: set[str] = set()
    for dept, ddata in index.get("departments", {}).items():
        for role in ddata.get("roles", []):
            current_roles.add(f"{dept}/{role}")
    index_version = index.get("version", "unknown")

    if not current_depts:
        print("INFO: _index.json has no departments — nothing to sync", flush=True)
        sys.exit(0)

    if args.verbose:
        print(f"INFO: _index.json version={index_version}, "
              f"departments={len(current_depts)}, roles={len(current_roles)}", flush=True)

    # ── Load prior sync state ────────────────────────────────────────────────
    synced_depts: set[str] = set()
    synced_roles: set[str] = set()
    synced_sops: set[str] = set()
    synced_personas: set[str] = set()

    if args.last_sync and Path(args.last_sync).exists():
        last_sync = load_json(args.last_sync, "last-sync.json")
        synced_depts = set(last_sync.get("departments", []))
        synced_roles = set(last_sync.get("roles", []))
        synced_sops = set(last_sync.get("sops", []))
        synced_personas = set(last_sync.get("personas", []))
        synced_at = last_sync.get("synced_at", "unknown")
        if args.verbose:
            print(f"INFO: last-sync.json synced_at={synced_at}, "
                  f"depts={len(synced_depts)}, roles={len(synced_roles)}, "
                  f"sops={len(synced_sops)}, personas={len(synced_personas)}", flush=True)
    else:
        if args.verbose:
            print("INFO: No last-sync.json — treating all entities as new", flush=True)

    # ── Compute dept delta ───────────────────────────────────────────────────
    new_depts = sorted(current_depts - synced_depts)
    already_synced_depts = sorted(current_depts & synced_depts)
    removed_depts = sorted(synced_depts - current_depts)

    if args.verbose:
        for dept in removed_depts:
            print(f"INFO: dept removed from index since last sync: {dept}", flush=True)
        for dept in already_synced_depts:
            print(f"SKIP: {dept}", flush=True)

    for dept in new_depts:
        # Emit both NEW: (back-compat) and NEW-DEPT: (new canonical)
        print(f"NEW: {dept}", flush=True)
        print(f"NEW-DEPT: {dept}", flush=True)

    # ── Compute role delta ───────────────────────────────────────────────────
    new_roles = sorted(current_roles - synced_roles)
    for role_path in new_roles:
        print(f"NEW-ROLE: {role_path}", flush=True)
    if args.verbose and new_roles:
        print(f"INFO: {len(new_roles)} new roles detected", flush=True)

    # ── Compute SOP delta ────────────────────────────────────────────────────
    depts_dir = Path(args.workspace_root) if args.workspace_root else find_workspace_depts_dir()
    current_sops: set[str] = set(scan_on_disk_sops(depts_dir))
    new_sops = sorted(current_sops - synced_sops)
    for sop_path in new_sops:
        print(f"NEW-SOP: {sop_path}", flush=True)
    if args.verbose and new_sops:
        print(f"INFO: {len(new_sops)} new SOPs detected", flush=True)

    # ── Compute persona delta ─────────────────────────────────────────────────
    pc_path = args.persona_categories or str(find_persona_categories_path() or "")
    current_personas: set[str] = set()
    untagged_personas: list[str] = []

    if pc_path and Path(pc_path).is_file():
        pc_data = load_json(pc_path, "persona-categories.json", required=False)
        raw_personas = pc_data.get("personas", {})
        for slug, pdata in raw_personas.items():
            current_personas.add(slug)
            # Emit UNTAGGED if domain or perspective are empty
            domain = pdata.get("domain", [])
            perspective = pdata.get("perspective", [])
            if not domain or not perspective:
                untagged_personas.append(slug)
    elif args.verbose:
        print("INFO: persona-categories.json not found — skipping persona delta", flush=True)

    new_personas = sorted(current_personas - synced_personas)
    for persona_slug in new_personas:
        print(f"NEW-PERSONA: {persona_slug}", flush=True)
    for persona_slug in sorted(untagged_personas):
        print(f"UNTAGGED: {persona_slug}", flush=True)

    if args.verbose:
        print(f"INFO: delta summary — "
              f"new_depts={len(new_depts)}, new_roles={len(new_roles)}, "
              f"new_sops={len(new_sops)}, new_personas={len(new_personas)}, "
              f"untagged_personas={len(untagged_personas)}", flush=True)


if __name__ == "__main__":
    main()
