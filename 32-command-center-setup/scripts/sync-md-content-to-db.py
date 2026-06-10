#!/usr/bin/env python3
"""sync-md-content-to-db.py - v10.15.6 (Mac) / v10.16.6 (VPS)

Populate the dashboard's `agents` table *_md columns from the on-disk role
folders. Closes the Angeleen gap where the dashboard DB had NULL for
identity_md / soul_md / memory_md / how_to_md / heartbeat_md columns because
seed-workspaces.py only writes companies + workspaces (departments).

This script is a fallback for the case where the dashboard repo's own
`sync-departments-from-build-state.py` (Phase 6c) is absent or stale. It
reads disk content into the rows that already exist (created by seed-
workspaces.py + sync-departments-from-build-state.py).

Idempotent via content-hash: skip the UPDATE when stored hash matches new.

Schema assumptions (best-effort, tolerant of column-missing):
  - Table `agents` (or fallback `dept_agents` or `workspaces`) with TEXT
    columns: identity_md, soul_md, memory_md, how_to_md, heartbeat_md,
    content_hash. If any column doesn't exist, the script skips that
    column (does not ALTER the schema).

Usage:
  python3 sync-md-content-to-db.py
  python3 sync-md-content-to-db.py --db /path/to/mission-control.db
  python3 sync-md-content-to-db.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

# Vendored detect_platform (v10.15.4) for resolving active workforce.
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SKILL23 = SKILL_DIR.parent / "23-ai-workforce-blueprint"
for cand in (
    SKILL23 / "lib",
    SKILL_DIR.parent.parent / "shared-utils",
    SKILL_DIR / "shared-utils",
    Path.home() / ".openclaw" / "skills" / "23-ai-workforce-blueprint" / "lib",
    Path("/data/.openclaw/skills/23-ai-workforce-blueprint/lib"),
):
    sys.path.insert(0, str(cand))

try:
    from detect_platform import get_openclaw_paths
except ImportError:
    def get_openclaw_paths():  # type: ignore
        return {}


MD_COLUMNS = {
    "identity_md": "IDENTITY.md",
    "soul_md": "SOUL.md",
    "memory_md": "MEMORY.md",
    "heartbeat_md": "HEARTBEAT.md",
    "how_to_md": "how-to.md",
}


def find_db(explicit: str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    candidates = [
        Path.home() / "projects" / "command-center" / "mission-control.db",
        Path.home() / "projects" / "mission-control" / "mission-control.db",
        Path("/opt/mission-control/mission-control.db"),
        Path("/app/mission-control.db"),
        Path.home() / ".openclaw" / "command-center" / "mission-control.db",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def resolve_company_root() -> Path | None:
    paths = get_openclaw_paths() or {}
    cand = paths.get("active_zhc_company") or paths.get("zhc_company_root")
    if cand:
        return Path(cand)
    workspace = paths.get("workspace_root") or paths.get("clawd_root") or str(Path.home() / "clawd")
    zhc = Path(workspace) / "zero-human-company"
    if zhc.is_dir():
        candidates = sorted(
            (d for d in zhc.iterdir() if d.is_dir() and not d.name.startswith(("_", "."))),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0]
    return None


def list_tables(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [r[0] for r in cur.fetchall()]


def list_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def pick_target_table(conn: sqlite3.Connection) -> tuple[str, list[str]] | None:
    """Find a table with at least one of the MD_COLUMNS columns + an id-like column."""
    for tbl in ("agents", "dept_agents", "workspaces"):
        if tbl in list_tables(conn):
            cols = list_columns(conn, tbl)
            present = [c for c in MD_COLUMNS if c in cols]
            if present:
                return tbl, present
    return None


def file_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def find_id_column(cols: list[str]) -> str | None:
    for c in ("agent_id", "id", "workspace_id", "slug", "name"):
        if c in cols:
            return c
    return None


def walk_role_folders(departments_dir: Path):
    """Yield (agent_key, role_dir) tuples for every role + dept-head."""
    for dept in sorted(departments_dir.iterdir()):
        if not dept.is_dir() or dept.name.startswith(("_", ".")):
            continue
        # dept head sometimes lives at e.g. <dept>/00-<head>/ — also try dept itself
        for role in sorted(dept.iterdir()):
            if role.is_dir() and not role.name.startswith(("_", ".")):
                yield f"{dept.name}/{role.name}", role
        yield dept.name, dept  # dept-level entry for files at dept root


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--company-root", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    db_path = find_db(args.db)
    if not db_path:
        print("[sync-md] ERROR: mission-control.db not found")
        return 4
    print(f"[sync-md] db={db_path}")

    company = Path(args.company_root) if args.company_root else resolve_company_root()
    if not company or not company.is_dir():
        print("[sync-md] ERROR: company root not resolvable on disk")
        return 4
    print(f"[sync-md] company_root={company}")

    departments_dir = company / "departments"
    if not departments_dir.is_dir():
        print(f"[sync-md] ERROR: {departments_dir} missing")
        return 4

    conn = sqlite3.connect(str(db_path))
    target = pick_target_table(conn)
    if not target:
        print("[sync-md] ERROR: no candidate table has MD content columns. "
              "Expected one of: agents, dept_agents, workspaces with columns "
              + ", ".join(MD_COLUMNS))
        conn.close()
        return 4
    table, available_cols = target
    cols = list_columns(conn, table)
    id_col = find_id_column(cols)
    has_hash = "content_hash" in cols
    print(f"[sync-md] table={table} id_col={id_col} md_cols={available_cols} hash={has_hash}")

    updates_planned = 0
    updates_applied = 0
    rows_seen = 0
    rows_skipped_no_match = 0
    rows_skipped_identical = 0

    for agent_key, role_dir in walk_role_folders(departments_dir):
        rows_seen += 1
        new_values: dict[str, str] = {}
        for col, fname in MD_COLUMNS.items():
            if col not in available_cols:
                continue
            f = role_dir / fname
            if f.is_file():
                try:
                    new_values[col] = f.read_text(errors="ignore")
                except Exception:
                    continue
        if not new_values:
            continue

        combined = "|".join(sorted(f"{k}:{file_hash(v)}" for k, v in new_values.items()))
        combined_hash = file_hash(combined)

        if not id_col:
            print(f"[sync-md] WARN no id column on {table}; skipping {agent_key}")
            rows_skipped_no_match += 1
            continue

        # Try several key strategies to find the existing row.
        slug = agent_key.replace("/", "-")
        bare = agent_key.split("/")[-1]
        cur = None
        for key in (agent_key, slug, bare):
            cur = conn.execute(f"SELECT rowid FROM {table} WHERE {id_col} = ?", (key,))
            row = cur.fetchone()
            if row:
                rowid = row[0]
                break
        else:
            rowid = None

        if rowid is None:
            rows_skipped_no_match += 1
            if args.verbose:
                print(f"[sync-md] skip no-row: {agent_key}")
            continue

        if has_hash:
            cur2 = conn.execute(f"SELECT content_hash FROM {table} WHERE rowid = ?", (rowid,))
            existing_hash_row = cur2.fetchone()
            if existing_hash_row and existing_hash_row[0] == combined_hash:
                rows_skipped_identical += 1
                continue

        updates_planned += 1
        set_clauses = [f"{c} = ?" for c in new_values]
        params = list(new_values.values())
        if has_hash:
            set_clauses.append("content_hash = ?")
            params.append(combined_hash)
        params.append(rowid)
        sql = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE rowid = ?"

        if args.dry_run:
            if args.verbose:
                print(f"[sync-md] DRY-RUN would UPDATE rowid={rowid} cols={list(new_values)}")
        else:
            conn.execute(sql, params)
            updates_applied += 1

    if not args.dry_run:
        conn.commit()
    conn.close()

    print("")
    print("[sync-md] summary:")
    print(f"  rows_seen              = {rows_seen}")
    print(f"  updates_planned        = {updates_planned}")
    print(f"  updates_applied        = {updates_applied}")
    print(f"  rows_skipped_no_match  = {rows_skipped_no_match}")
    print(f"  rows_skipped_identical = {rows_skipped_identical}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
