#!/usr/bin/env python3
"""
regenerate-sop-index.py — Skill 23 AI Workforce Blueprint (§1.2)

PURPOSE
    For a given department (or all departments), scan on-disk SOP markdown
    files and rebuild SOP/00-INDEX.md deterministically. The index is a
    human/agent navigation aid; the CC ingests the raw markdown directly via
    POST /api/sops/import-role-library (no separate jsonl needed).

WHAT IT DOES
    1. Scans departments/<dept>/**/SOP/*.md files (sorted by filename ordinal)
    2. Extracts title (from H1 or <!-- sop-meta title: ... --> comment),
       keywords (from <!-- sop-meta keywords: ... --> comment),
       and owning role (from <!-- sop-meta role: ... --> comment or dir path)
    3. Writes a clean markdown table to SOP/00-INDEX.md
    4. Exits 0 with "changed=N" on stdout

USAGE
    python3 regenerate-sop-index.py --dept podcast
    python3 regenerate-sop-index.py --all
    python3 regenerate-sop-index.py --dept podcast --dry-run

EXIT CODES
    0 — success
    1 — dept directory not found
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def find_workspace_root() -> Path | None:
    """Locate the workspace departments directory (VPS first, Mac fallback)."""
    candidates = [
        Path("/data/.openclaw/workspace/agents/main"),
        Path.home() / ".openclaw/workspace/agents/main",
        Path("/data/.openclaw/workspace"),
        Path.home() / ".openclaw/workspace",
    ]
    for c in candidates:
        depts = c / "departments"
        if depts.is_dir():
            return depts
    return None


def parse_sop_meta(content: str, file_path: Path) -> dict:
    """Extract meta from <!-- sop-meta ... --> comment or H1 heading."""
    meta = {
        "title": None,
        "keywords": [],
        "role": None,
        "slug": None,
    }

    # Try sop-meta comment block
    meta_block = re.search(r"<!--\s*sop-meta(.*?)-->", content, re.DOTALL)
    if meta_block:
        block = meta_block.group(1)
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("title:"):
                meta["title"] = line[6:].strip()
            elif line.startswith("keywords:"):
                raw = line[9:].strip()
                meta["keywords"] = [k.strip() for k in raw.split(",") if k.strip()]
            elif line.startswith("role:"):
                role_val = line[5:].strip()
                if role_val:
                    meta["role"] = role_val
            elif line.startswith("slug:"):
                meta["slug"] = line[5:].strip()

    # Fallback: extract H1 as title
    if not meta["title"]:
        h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if h1_match:
            meta["title"] = h1_match.group(1).strip()
        else:
            meta["title"] = file_path.stem

    # Infer role from directory structure
    if not meta["role"]:
        # Check if parent is a role dir (dept/roles/<role>/SOP/)
        parts = file_path.parts
        try:
            sop_idx = parts.index("SOP")
            if sop_idx >= 2 and parts[sop_idx - 2] == "roles":
                meta["role"] = parts[sop_idx - 1]
        except ValueError:
            pass

    return meta


def regenerate_dept_index(dept_dir: Path, dry_run: bool = False) -> int:
    """Rebuild 00-INDEX.md for one department. Returns count of SOPs indexed."""
    # Collect all SOP files recursively, sorted
    all_sop_files = []

    # Dept-level SOPs
    dept_sop_dir = dept_dir / "SOP"
    if dept_sop_dir.is_dir():
        for f in sorted(dept_sop_dir.glob("*.md")):
            if f.name != "00-INDEX.md":
                all_sop_files.append(f)

    # Role-level SOPs
    roles_dir = dept_dir / "roles"
    if roles_dir.is_dir():
        for role_dir in sorted(roles_dir.iterdir()):
            if not role_dir.is_dir() or role_dir.name.startswith("."):
                continue
            role_sop_dir = role_dir / "SOP"
            if role_sop_dir.is_dir():
                for f in sorted(role_sop_dir.glob("*.md")):
                    if f.name != "00-INDEX.md":
                        all_sop_files.append(f)

    if not all_sop_files:
        return 0

    # Build index rows
    rows = []
    for sop_file in all_sop_files:
        try:
            content = sop_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            content = ""
        meta = parse_sop_meta(content, sop_file)
        # Make path relative to dept_dir for readability
        try:
            rel_path = sop_file.relative_to(dept_dir)
        except ValueError:
            rel_path = sop_file
        rows.append({
            "file": str(rel_path),
            "title": meta["title"] or sop_file.stem,
            "keywords": ", ".join(meta["keywords"]) if meta["keywords"] else "",
            "role": meta["role"] or "(dept-level)",
        })

    # Build markdown table
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# SOP Index — {dept_dir.name}",
        "",
        f"> Auto-generated by regenerate-sop-index.py on {now_str}.",
        f"> Do NOT edit by hand — run `add-sop.sh` to add a SOP, which regenerates this file.",
        "",
        "| SOP File | Title | Keywords | Owning Role |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| `{row['file']}` | {row['title']} | {row['keywords']} | {row['role']} |")
    lines.append("")

    index_content = "\n".join(lines)

    # Write to dept-level SOP/00-INDEX.md
    if not dept_sop_dir.exists() and not dry_run:
        dept_sop_dir.mkdir(parents=True, exist_ok=True)
    index_path = dept_sop_dir / "00-INDEX.md"

    if dry_run:
        print(f"  [DRY-RUN] would write {index_path} ({len(rows)} SOPs)")
        return len(rows)

    index_path.write_text(index_content, encoding="utf-8")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate SOP/00-INDEX.md for departments")
    parser.add_argument("--dept", default=None, help="Department slug to regenerate")
    parser.add_argument("--all", action="store_true", help="Regenerate for ALL departments")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no writes")
    parser.add_argument("--workspace-root", default=None,
                        help="Override path to workspace/agents/main/departments/")
    args = parser.parse_args()

    if not args.dept and not args.all:
        print("ERROR: specify --dept <slug> or --all", file=sys.stderr)
        sys.exit(1)

    # Resolve departments root
    if args.workspace_root:
        depts_root = Path(args.workspace_root)
    else:
        depts_root = find_workspace_root()

    if not depts_root or not depts_root.is_dir():
        print(f"ERROR: departments directory not found. Set --workspace-root or install OpenClaw first.",
              file=sys.stderr)
        sys.exit(1)

    total_changed = 0

    if args.all:
        depts = sorted(d for d in depts_root.iterdir() if d.is_dir() and not d.name.startswith("."))
    else:
        dept_dir = depts_root / args.dept
        if not dept_dir.is_dir():
            print(f"ERROR: dept '{args.dept}' not found at {dept_dir}", file=sys.stderr)
            sys.exit(1)
        depts = [dept_dir]

    for dept_dir in depts:
        count = regenerate_dept_index(dept_dir, dry_run=args.dry_run)
        if count > 0:
            print(f"  {'[DRY-RUN] ' if args.dry_run else ''}regenerated {dept_dir.name}/SOP/00-INDEX.md "
                  f"({count} SOPs)")
            total_changed += count

    print(f"changed={total_changed}")
    sys.exit(0)


if __name__ == "__main__":
    main()
