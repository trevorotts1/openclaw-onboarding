#!/usr/bin/env python3
"""
sync-md-content-to-db.py — build E: read each department's SOUL.md from disk
and write it into agents.soul_md in mission-control.db.

Problem this solves
-------------------
On every live box, agents.soul_md is NULL for all department-head agents because
seed-dashboard-content.py / seed-workspaces.py only create the row skeleton —
they do not populate soul_md.  The persona-selector reads SOUL.md from the
filesystem fine, but the Command Center dashboard (and any DB-backed query) sees
empty soul content.

What it does (idempotent)
-------------------------
1. Locate mission-control.db via the same search order as seed-workspaces.py.
2. Find the ZHC company directory (most-recently-modified, or $COMPANY_SLUG).
3. Walk departments/ — for each dept folder that has a SOUL.md, look up the
   department-head agent row in agents where workspace_id = <dept-slug>.
4. UPDATE agents SET soul_md = <content>, updated_at = NOW
   WHERE workspace_id = <slug> AND soul_md IS NULL OR soul_md = ''.
   (Safe: never overwrites a non-empty soul_md unless --force is passed.)
5. Print a per-dept summary and exit 0.

Exit codes:
    0 = success (all reachable soul_md rows synced or already populated)
    1 = fatal (DB not found, table missing, etc.)
    2 = partial (at least one dept has no SOUL.md on disk — manual action needed)

Usage:
    python3 sync-md-content-to-db.py
    python3 sync-md-content-to-db.py --force          # overwrite even non-empty
    python3 sync-md-content-to-db.py --dry-run         # print actions, no writes
    COMPANY_SLUG=my-company python3 sync-md-content-to-db.py
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# PRD 1.3: use the single shared DB resolver (shared-utils/resolve_db.py).
# The local find_db() was removed to eliminate divergent candidate lists.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "shared-utils"))
from resolve_db import find_dashboard_db  # type: ignore


# ─── Path discovery ───────────────────────────────────────────────────────────

def find_db() -> str | None:
    """Thin wrapper around the shared resolver for backward-compat call sites."""
    p = find_dashboard_db()
    return str(p) if p.exists() else None


def find_company_dir() -> Path | None:
    target_slug = os.environ.get("COMPANY_SLUG", "").strip()
    # PRD 1.9: canonical root first, legacy roots for backward compat (READ-ONLY).
    _canonical = None
    try:
        _su = str(Path(__file__).resolve().parent.parent.parent / "shared-utils")
        if _su not in sys.path:
            sys.path.insert(0, _su)
        from detect_platform import get_openclaw_paths as _gop
        _canonical = _gop()["company_root"]
    except Exception:
        pass

    roots = []
    if _canonical is not None:
        roots.append(_canonical)
    roots.extend([
        Path.home() / "clawd" / "zero-human-company",
        Path("/data/clawd/zero-human-company"),
        Path.home() / "clawd" / "zhc",
        Path("/data/clawd/zhc"),
    ])
    best: tuple[float, Path] | None = None
    for root in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if target_slug and child.name != target_slug:
                continue
            mtime = child.stat().st_mtime
            if best is None or mtime > best[0]:
                best = (mtime, child)
    return best[1] if best else None


def find_departments_dir(company_dir: Path | None) -> Path | None:
    if company_dir:
        d = company_dir / "departments"
        if d.is_dir():
            return d
    # Legacy fallbacks
    for legacy in [
        Path.home() / ".openclaw/workspace/departments",
        Path("/data/.openclaw/workspace/departments"),
    ]:
        if legacy.is_dir():
            return legacy
    return None


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Sync SOUL.md files to agents.soul_md in mission-control.db")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite agents.soul_md even if already non-empty")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print planned updates without writing")
    args = parser.parse_args()

    db_path = find_db()
    if not db_path:
        print("[sync-soul-md] FATAL: mission-control.db not found. Is the Command Center installed?",
              file=sys.stderr)
        return 1

    company_dir = find_company_dir()
    departments_dir = find_departments_dir(company_dir)
    if not departments_dir:
        print("[sync-soul-md] FATAL: departments dir not found. Run Skill 23 first.", file=sys.stderr)
        return 1

    print(f"[sync-soul-md] DB: {db_path}")
    print(f"[sync-soul-md] Departments: {departments_dir}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Verify agents table has soul_md column
    cols = {row["name"] for row in cur.execute("PRAGMA table_info(agents)").fetchall()}
    if "soul_md" not in cols:
        print("[sync-soul-md] FATAL: agents table has no soul_md column — "
              "apply DB migration first (ALTER TABLE agents ADD COLUMN soul_md TEXT DEFAULT '')",
              file=sys.stderr)
        conn.close()
        return 1

    now = datetime.now(timezone.utc).isoformat()

    synced = 0
    skipped_already_populated = 0
    missing_soul_md = 0
    no_agent_row = 0

    dept_dirs = sorted(p for p in departments_dir.iterdir()
                       if p.is_dir() and not p.name.startswith("."))

    for dept_dir in dept_dirs:
        slug = dept_dir.name
        soul_path = dept_dir / "SOUL.md"

        if not soul_path.exists():
            print(f"  [sync-soul-md] SKIP {slug}: no SOUL.md on disk", file=sys.stderr)
            missing_soul_md += 1
            continue

        soul_content = soul_path.read_text(encoding="utf-8", errors="replace").strip()
        if not soul_content:
            print(f"  [sync-soul-md] SKIP {slug}: SOUL.md is empty", file=sys.stderr)
            missing_soul_md += 1
            continue

        # Find the department-head agent row (workspace_id = slug)
        row = cur.execute(
            "SELECT id, soul_md FROM agents WHERE workspace_id = ? LIMIT 1",
            (slug,)
        ).fetchone()

        if not row:
            # Also try with "dept-" prefix stripped/added
            row = cur.execute(
                "SELECT id, soul_md FROM agents WHERE workspace_id = ? LIMIT 1",
                (f"dept-{slug}",)
            ).fetchone()

        if not row:
            print(f"  [sync-soul-md] SKIP {slug}: no agent row found in DB (workspace_id='{slug}')",
                  file=sys.stderr)
            no_agent_row += 1
            continue

        agent_id = row["id"]
        current_soul = row["soul_md"] or ""

        if current_soul and not args.force:
            print(f"  [sync-soul-md] SKIP {slug}: soul_md already populated for agent {agent_id} (use --force to overwrite)")
            skipped_already_populated += 1
            continue

        if args.dry_run:
            print(f"  [sync-soul-md] DRY-RUN: would UPDATE agents SET soul_md=<{len(soul_content)} chars> "
                  f"WHERE id='{agent_id}' (dept={slug})")
        else:
            cur.execute(
                "UPDATE agents SET soul_md = ?, updated_at = ? WHERE id = ?",
                (soul_content, now, agent_id),
            )
            print(f"  [sync-soul-md] SYNCED {slug} → agent {agent_id} ({len(soul_content)} chars)")
        synced += 1

    if not args.dry_run:
        conn.commit()
    conn.close()

    print("")
    print(f"[sync-soul-md] Summary: {len(dept_dirs)} departments scanned")
    print(f"[sync-soul-md]   {synced} synced (or would sync in dry-run)")
    print(f"[sync-soul-md]   {skipped_already_populated} already populated (skipped)")
    print(f"[sync-soul-md]   {missing_soul_md} missing SOUL.md on disk")
    print(f"[sync-soul-md]   {no_agent_row} no matching agent row in DB")

    if missing_soul_md > 0:
        print(f"[sync-soul-md] WARN: {missing_soul_md} dept(s) have no SOUL.md on disk. "
              f"Re-run Skill 23 build for those departments.", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
