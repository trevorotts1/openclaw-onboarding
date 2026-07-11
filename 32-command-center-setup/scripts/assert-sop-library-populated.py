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

TWO WRITERS, TWO INDEPENDENT ASSERTS. Both writers land in the SAME `sops`
table, but a single COUNT(*) CANNOT see both -- it conflates them:

  1. ingest-sop-library.py  -- direct JSONL-asset upsert (~2,555 rows). It
     never sets `source`, so its rows carry source NULL.
  2. CC converge(scope=sops) -> importRoleLibrary() -- upserts the on-disk
     departments/ role library with source='role-library'.

A successful (1) with a FAILED (2) yields ~2,555 rows and ZERO role-library
rows -- which is EXACTLY the live C2 evidence. One bare COUNT(*) passes that
happily. So this script asserts BOTH independently: --min-total (all rows)
AND --min-role-library (rows WHERE source=<--role-library-source>). Neither
subsumes the other.

FAIL-CLOSED BY CONSTRUCTION. --min-total has NO default. A caller that omits
it is a misconfigured caller, and this script REFUSES to run (EX_NO_FLOOR)
rather than fall back to a floor of 1 -- because the CC boot-seed guarantees
the table is never empty by the time this gate runs, a floor of 1 would
rubber-stamp the very ghost this gate exists to catch. A gate that fails open
is not a gate. --min-role-library likewise defaults to 1 (strict), never 0.

Usage:
  assert-sop-library-populated.py --min-total N [--db PATH]
                                  [--min-role-library N] [--expected N]
                                  [--role-library-source S] [--json]

Exit codes:
  0 - healthy: total >= --min-total AND role-library rows >= --min-role-library.
      A --expected mismatch does NOT change this -- fail-WARN only
      (row_count_mismatch=true in the JSON), never a hard block.
  1 - GHOST: total < --min-total (or the `sops` table itself does not exist
      yet -- migration 028 never ran). FAIL LOUD.
  2 - mission-control.db not found at all (install ran out of order -- the
      Phase 6 dashboard deploy must complete, and its DB must exist, first).
  3 - NO FLOOR: --min-total was not supplied. Refusing to run: an implicit
      floor is a rubber stamp. FAIL LOUD (never silently degrade).
  4 - NO ROLE LIBRARY: role-library rows < --min-role-library. The JSONL
      ingest may well have succeeded -- but converge(scope=sops) /
      importRoleLibrary() did not, so the role library is a ghost. FAIL LOUD.
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
EX_NO_FLOOR = 3
EX_NO_ROLE_LIBRARY = 4

# The `source` value CC's converge(scope=sops) -> importRoleLibrary() stamps on
# every role-library row. Overridable via --role-library-source so a CC-side
# rename is a one-flag installer change, not a code rewrite. The direct JSONL
# ingester (ingest-sop-library.py) never sets `source` at all -- its rows are
# NULL -- which is what makes this value a clean discriminator between the two
# writers.
DEFAULT_ROLE_LIBRARY_SOURCE = "role-library"


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


def count_sops(db_path: Path, role_library_source: str):
    """Returns (total, role_library_total, table_exists, has_source_col).

    Read-only connection -- never writes. A `sops` table with no `source`
    column cannot hold role-library rows at all, so role_library_total is 0
    (reported honestly via has_source_col=False rather than crashing).
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "sops" not in tables:
            return 0, 0, False, False
        total = conn.execute("SELECT COUNT(*) FROM sops").fetchone()[0]
        cols = {c[1] for c in conn.execute("PRAGMA table_info(sops)")}
        if "source" not in cols:
            return total, 0, True, False
        role_total = conn.execute(
            "SELECT COUNT(*) FROM sops WHERE source = ?", (role_library_source,)
        ).fetchone()[0]
        return total, role_total, True, True
    finally:
        conn.close()


def run(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--db", default=None,
        help="explicit mission-control.db path (default: shared resolver)",
    )
    ap.add_argument(
        "--min-total", type=int, default=None,
        help="REQUIRED hard floor on total sops rows -- exit 1 below it. No "
             "default: omitting it exits 3 (a gate with an implicit floor of "
             "1 would rubber-stamp the CC boot-seed ghost)",
    )
    ap.add_argument(
        "--min-role-library", type=int, default=1,
        help="hard floor on rows WHERE source=<--role-library-source> -- exit "
             "4 below it (default 1: converge(scope=sops) must have imported "
             "at least one role-library row)",
    )
    ap.add_argument(
        "--role-library-source", default=DEFAULT_ROLE_LIBRARY_SOURCE,
        help=f"`source` value CC's importRoleLibrary() stamps on role-library "
             f"rows (default {DEFAULT_ROLE_LIBRARY_SOURCE!r})",
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
        "role_library_total": 0,
        "table_exists": False,
        "has_source_column": False,
        "ok": False,
        "row_count_mismatch": False,
        "expected": args.expected,
        "min_total": args.min_total,
        "min_role_library": args.min_role_library,
        "reason": "",
    }

    # (0) FAIL-CLOSED: no explicit floor -> refuse to run. This is the exact
    # hole that shipped a green check over the live 54-row ghost: when the
    # ingest failed, the installer parsed no download count, passed no
    # --min-total, and the old default of 1 declared "healthy: 54 row(s) >=
    # floor 1" over a table the CC boot-seed had already filled. Never again:
    # an absent floor is a misconfigured caller, not a permissive one.
    if args.min_total is None:
        result["reason"] = (
            "NO FLOOR: --min-total was not supplied -- refusing to run. The CC "
            "boot-seed (autoSeedStarterSOPs) guarantees `sops` is non-empty by "
            "the time this gate runs, so an implicit floor would rubber-stamp a "
            "ghost library. The caller must pass the floor it actually expects."
        )
        _emit(result, args.json)
        return EX_NO_FLOOR

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
        total, role_total, table_exists, has_source_col = count_sops(
            db_path, args.role_library_source
        )
    except sqlite3.Error as exc:
        result["reason"] = f"sqlite error reading {db_path}: {exc}"
        _emit(result, args.json)
        return EX_NO_DB

    result["total"] = total
    result["role_library_total"] = role_total
    result["table_exists"] = table_exists
    result["has_source_column"] = has_source_col

    if args.expected is not None and total != args.expected:
        result["row_count_mismatch"] = True

    # (1) total-row floor -- the direct JSONL-asset ingest landed.
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

    # (2) role-library floor -- converge(scope=sops)/importRoleLibrary() landed.
    # Deliberately INDEPENDENT of the total: a healthy 2,555-row JSONL ingest
    # with a failed converge is precisely the live C2 shape, and a bare
    # COUNT(*) waves it straight through.
    if role_total < args.min_role_library:
        result["ok"] = False
        if not has_source_col:
            result["reason"] = (
                f"NO ROLE LIBRARY: sops table has {total} row(s) but NO `source` "
                f"column, so no role-library row can exist -- CC "
                f"converge(scope=sops)/importRoleLibrary() has never run against "
                f"this DB (floor is {args.min_role_library})"
            )
        else:
            result["reason"] = (
                f"NO ROLE LIBRARY: sops table has {total} row(s) but only "
                f"{role_total} with source='{args.role_library_source}' (floor "
                f"{args.min_role_library}) -- the JSONL ingest may have "
                f"succeeded, but CC converge(scope=sops)/importRoleLibrary() did "
                f"NOT: the role library is a ghost and Triad routing will starve"
            )
        _emit(result, args.json)
        return EX_NO_ROLE_LIBRARY

    result["ok"] = True
    warn = (
        f" (WARN: expected {args.expected}, got {total} -- row_count_mismatch)"
        if result["row_count_mismatch"] else ""
    )
    result["reason"] = (
        f"healthy: {total} row(s) >= floor {args.min_total}, "
        f"{role_total} role-library row(s) >= floor {args.min_role_library}{warn}"
    )
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
