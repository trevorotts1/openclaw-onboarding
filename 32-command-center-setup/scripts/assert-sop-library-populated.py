#!/usr/bin/env python3
"""Skill 32 -- SOP V2 library row-count assert (C2 fix, onboarding side).

THE BUG THIS CLOSES: a fresh install never called ingest-sop-library.sh and
never triggered the Command Center's converge(scope=sops) role-library
import, so a client's `sops` table shipped with whatever CC's own
autoSeedStarterSOPs boot-seed happened to write (a handful of stale rows
keyed by legacy department-alias slugs) instead of the real ~2,555-row V2
library -- a "ghost" library that silently starves dispatch_rules.sop_id
matching and Triad routing. This script is the fail-loud gate
run-full-install.sh's SOP-ingestion phase runs immediately after
ingest-sop-library.sh + the CC converge(scope=sops) call, so a fresh install
can never again silently claim success over an empty/near-empty table.

Reads the SAME mission-control.db both writers (ingest-sop-library.py's
direct INSERT OR REPLACE and the CC converge route's importRoleLibrary(),
which upserts role-library rows into the identical `sops` table with
source='role-library') land in -- one COUNT(*) sees both.

Usage:
  assert-sop-library-populated.py [--db PATH] [--min-total N] [--expected N] [--json]

Exit codes:
  0 - healthy: sops COUNT(*) >= --min-total (default 1 == "not empty / not a
      ghost"). A --expected mismatch does NOT change this -- fail-WARN only
      (row_count_mismatch=true in the JSON), never a hard block.
  1 - GHOST: COUNT(*) < --min-total (0 rows, or the `sops` table itself does
      not exist yet -- migration 028 never ran). FAIL LOUD.
  2 - mission-control.db not found at all (install ran out of order -- the
      Phase 6 dashboard deploy must complete, and its DB must exist, first).
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

_SHARED_UTILS = Path(__file__).resolve().parent.parent.parent / "shared-utils"
sys.path.insert(0, str(_SHARED_UTILS))
try:
    from resolve_db import find_dashboard_db, is_db_found  # type: ignore
    _HAS_SHARED_RESOLVER = True
except ImportError:
    _HAS_SHARED_RESOLVER = False


EX_OK = 0
EX_GHOST = 1
EX_NO_DB = 2


def resolve_db(explicit: "str | None"):
    """Explicit --db wins; otherwise the shared resolver (same candidate list
    every other Skill 32 python script uses -- Mac first, then VPS/legacy)."""
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    if _HAS_SHARED_RESOLVER:
        p = find_dashboard_db()
        if is_db_found(p):
            return p
    return None


def count_sops(db_path: Path):
    """Returns (total, table_exists). Read-only connection -- never writes."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "sops" not in tables:
            return 0, False
        total = conn.execute("SELECT COUNT(*) FROM sops").fetchone()[0]
        return total, True
    finally:
        conn.close()


def run(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--db", default=None,
        help="explicit mission-control.db path (default: shared resolver)",
    )
    ap.add_argument(
        "--min-total", type=int, default=1,
        help="hard floor -- exit 1 below this (default 1 == not-empty)",
    )
    ap.add_argument(
        "--expected", type=int, default=None,
        help="ingest-reported download count (e.g. ingest-sop-library.sh's "
             "'downloaded N SOP records' line) -- mismatch is WARN-only",
    )
    ap.add_argument(
        "--json", action="store_true", help="emit JSON on stdout instead of text",
    )
    args = ap.parse_args(argv)

    result = {
        "db_path": None,
        "total": 0,
        "table_exists": False,
        "ok": False,
        "row_count_mismatch": False,
        "expected": args.expected,
        "reason": "",
    }

    db_path = resolve_db(args.db)
    if db_path is None:
        result["reason"] = (
            "mission-control.db not found (checked $DASHBOARD_DB_PATH / "
            "$DATABASE_PATH + install candidates) -- run Phase 6 dashboard "
            "deploy before this phase"
        )
        _emit(result, args.json)
        return EX_NO_DB
    result["db_path"] = str(db_path)

    try:
        total, table_exists = count_sops(db_path)
    except sqlite3.Error as exc:
        result["reason"] = f"sqlite error reading {db_path}: {exc}"
        _emit(result, args.json)
        return EX_NO_DB

    result["total"] = total
    result["table_exists"] = table_exists

    if args.expected is not None and total != args.expected:
        result["row_count_mismatch"] = True

    if total < args.min_total:
        result["ok"] = False
        if not table_exists:
            result["reason"] = (
                "GHOST: `sops` table does not exist -- migration 028 never "
                "ran (ingest-sop-library.sh did not complete)"
            )
        else:
            result["reason"] = (
                f"GHOST: sops table has {total} row(s), floor is "
                f"{args.min_total} -- a fresh install must never leave the "
                f"Command Center SOP library empty"
            )
        _emit(result, args.json)
        return EX_GHOST

    result["ok"] = True
    warn = (
        f" (WARN: expected {args.expected}, got {total} -- row_count_mismatch)"
        if result["row_count_mismatch"] else ""
    )
    result["reason"] = f"healthy: {total} row(s) >= floor {args.min_total}{warn}"
    _emit(result, args.json)
    return EX_OK


def _emit(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result))
    else:
        status = "PASS" if result["ok"] else "FAIL"
        print(f"[assert-sop-library-populated] {status}: {result['reason']}")


if __name__ == "__main__":
    sys.exit(run())
