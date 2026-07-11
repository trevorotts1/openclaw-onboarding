#!/usr/bin/env python3
"""
test_assert_sop_library_populated.py — regression guard for
assert-sop-library-populated.py (C2, onboarding side: Phase 6c/6i SOP V2
library ingestion wiring in run-full-install.sh).

THE BUG THIS GUARD PROTECTS AGAINST: run-full-install.sh never called
ingest-sop-library.sh nor the CC converge(scope=sops) role-library import, so
a client's `sops` table shipped with 54 stale/test rows (30 test-dept
residue + 24 legacy-alias starter rows, all with `source` NULL) instead of
the real ~2,555-row V2 library, and the installer stamped success anyway. The
row-count assert this file guards is the fail-loud check that closes that
gap: a truly empty (or missing) `sops` table must fail loud (exit 1); a
non-empty table that merely doesn't match the ingest's own reported download
count is a WARN, never a hard block (per the C2 spec's "fail-warn on
row-count != 2555" -- some upsert errors / legacy overlap is not a ghost).

WHAT THIS FILE PROVES:
    1. GHOST -- `sops` table exists but is EMPTY (0 rows): exit 1 (EX_GHOST),
       ok=false, reason mentions GHOST.
    2. GHOST -- `sops` table does not exist at all (migration 028 never
       ran): exit 1, table_exists=false, reason mentions migration 028.
    3. Healthy -- a real-shaped library (2,555 rows, mixed source NULL /
       'role-library'): exit 0 (EX_OK), ok=true.
    4. The EXACT historical ghost shape (54 rows: 30 test-dept + 24
       legacy-alias, source all NULL) is BELOW a sane installer floor and
       must still fail loud when the floor reflects "a real library", never
       silently pass just because the count is nonzero.
    5. --expected mismatch is WARN-only: total=2555, expected=2600 -> still
       exit 0, but row_count_mismatch=true in the JSON.
    6. --expected match: no mismatch flag.
    7. Missing mission-control.db entirely -> exit 2 (EX_NO_DB), never
       mistaken for a healthy 0-row PASS.
    8. --min-total is respected as a configurable floor (installer default
       is 1 == not-empty; this proves the flag actually gates, so a future
       caller can raise it without touching this script).
    9. JSON output round-trips (installer's run-full-install.sh parses this
       with python3 -c, not by scraping text).

Run:  python3 -m pytest test_assert_sop_library_populated.py -q
   or: python3 test_assert_sop_library_populated.py     (no pytest required)
"""
import importlib.util
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "assert-sop-library-populated.py"

_spec = importlib.util.spec_from_file_location("assert_sop_lib", SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
run = _mod.run
EX_OK = _mod.EX_OK
EX_GHOST = _mod.EX_GHOST
EX_NO_DB = _mod.EX_NO_DB


# --------------------------------------------------------------------------
# Fixture builders
# --------------------------------------------------------------------------
def _make_db(tmp, n_rows=0, with_table=True, sources=None):
    """Build a minimal mission-control.db with an optional `sops` table.

    sources: optional list of `source` values (len must equal n_rows) so the
    ghost-shape fixture (source all NULL) and the healthy-shape fixture
    (mixed NULL / 'role-library') can be reproduced faithfully.
    """
    db_path = Path(tmp) / "mission-control.db"
    conn = sqlite3.connect(db_path)
    if with_table:
        conn.execute(
            "CREATE TABLE sops (id TEXT PRIMARY KEY, slug TEXT, name TEXT, "
            "department TEXT, source TEXT)"
        )
        for i in range(n_rows):
            src = sources[i] if sources else None
            conn.execute(
                "INSERT INTO sops (id, slug, name, department, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"sop_{i}", f"slug-{i}", f"SOP {i}", "marketing", src),
            )
    conn.commit()
    conn.close()
    return db_path


def _capture(argv):
    """Run `run(argv)` and capture stdout, returning (rc, stdout_text)."""
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = run(argv)
    return rc, buf.getvalue()


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------
def test_ghost_empty_table_fails_loud():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=0, with_table=True)
        rc, out = _capture(["--db", str(db), "--json"])
        data = json.loads(out)
        assert rc == EX_GHOST, f"expected EX_GHOST, got rc={rc}"
        assert data["ok"] is False
        assert data["total"] == 0
        assert "GHOST" in data["reason"]


def test_ghost_missing_table_fails_loud():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=0, with_table=False)
        rc, out = _capture(["--db", str(db), "--json"])
        data = json.loads(out)
        assert rc == EX_GHOST, f"expected EX_GHOST, got rc={rc}"
        assert data["table_exists"] is False
        assert "migration 028" in data["reason"]


def test_healthy_v2_library_passes():
    with tempfile.TemporaryDirectory() as tmp:
        sources = [None] * 2448 + ["role-library"] * 107
        db = _make_db(tmp, n_rows=2555, with_table=True, sources=sources)
        rc, out = _capture(["--db", str(db), "--json"])
        data = json.loads(out)
        assert rc == EX_OK, f"expected EX_OK, got rc={rc}: {data}"
        assert data["ok"] is True
        assert data["total"] == 2555


def test_exact_historical_ghost_shape_fails_against_real_floor():
    """The live-observed ghost: 54 rows (30 test-dept + 24 legacy-alias),
    source all NULL. Nonzero, but must still fail loud against a floor that
    reflects a real library (proves --min-total isn't rubber-stamped at 1 in
    the installer's actual invocation for this exact regression)."""
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=54, with_table=True, sources=[None] * 54)
        rc, out = _capture(["--db", str(db), "--min-total", "500", "--json"])
        data = json.loads(out)
        assert rc == EX_GHOST, f"expected EX_GHOST for the 54-row ghost shape, got rc={rc}"
        assert data["total"] == 54


def test_expected_mismatch_is_warn_only_never_blocks():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=2555, with_table=True)
        rc, out = _capture(["--db", str(db), "--expected", "2600", "--json"])
        data = json.loads(out)
        assert rc == EX_OK, "row-count mismatch vs --expected must be WARN-only, never a hard block"
        assert data["ok"] is True
        assert data["row_count_mismatch"] is True


def test_expected_match_no_mismatch_flag():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=2555, with_table=True)
        rc, out = _capture(["--db", str(db), "--expected", "2555", "--json"])
        data = json.loads(out)
        assert rc == EX_OK
        assert data["row_count_mismatch"] is False


def test_missing_db_is_distinct_exit_code():
    with tempfile.TemporaryDirectory() as tmp:
        nonexistent = Path(tmp) / "does-not-exist.db"
        rc, out = _capture(["--db", str(nonexistent), "--json"])
        data = json.loads(out)
        assert rc == EX_NO_DB, f"expected EX_NO_DB, got rc={rc}"
        assert data["ok"] is False
        assert data["total"] == 0  # never mistaken for a healthy 0-row pass


def test_min_total_floor_is_configurable():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=10, with_table=True)
        rc_low, _ = _capture(["--db", str(db), "--min-total", "1"])
        rc_high, _ = _capture(["--db", str(db), "--min-total", "100"])
        assert rc_low == EX_OK, "10 rows should pass a floor of 1"
        assert rc_high == EX_GHOST, "10 rows should fail a floor of 100"


def test_json_output_round_trips():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=5, with_table=True)
        rc, out = _capture(["--db", str(db), "--json"])
        data = json.loads(out)  # must not raise
        assert set(["db_path", "total", "table_exists", "ok", "row_count_mismatch", "reason"]).issubset(data.keys())
        assert rc == EX_OK


def test_text_mode_prints_pass_fail_label():
    with tempfile.TemporaryDirectory() as tmp:
        db_pass = _make_db(tmp, n_rows=5, with_table=True)
        _, out_pass = _capture(["--db", str(db_pass)])
        assert out_pass.startswith("[assert-sop-library-populated] PASS:")

        sub = Path(tmp) / "sub"
        sub.mkdir(exist_ok=True)
        db_fail = _make_db(sub, n_rows=0, with_table=True)
        _, out_fail = _capture(["--db", str(db_fail)])
        assert out_fail.startswith("[assert-sop-library-populated] FAIL:")


def _main():
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS: {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL: {name}: {e}", file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"ERROR: {name}: {e}", file=sys.stderr)
    if failures:
        print(f"\n{failures} test(s) failed", file=sys.stderr)
        sys.exit(1)
    print("\nall assert-sop-library-populated tests passed")


if __name__ == "__main__":
    _main()
