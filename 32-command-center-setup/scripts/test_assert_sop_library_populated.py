#!/usr/bin/env python3
"""
test_assert_sop_library_populated.py — regression guard for
assert-sop-library-populated.py (C2, onboarding side: Phase 6i SOP V2
library ingestion wiring in run-full-install.sh).

THE BUG THIS GUARD PROTECTS AGAINST: run-full-install.sh never called
ingest-sop-library.sh nor the CC converge(scope=sops) role-library import, so
a client's `sops` table shipped with 54 stale/test rows (30 test-dept
residue + 24 legacy-alias starter rows, all with `source` NULL) instead of
the real ~2,555-row V2 library, and the installer stamped success anyway.

THE BUG THE *FIRST FIX* SHIPPED, WHICH THIS FILE NOW ALSO GUARDS: that gate
FAILED OPEN. ingest-sop-library.sh runs under `set -euo pipefail` and prints
its "downloaded N SOP records" line only after curl+gunzip succeed, so any
network/asset failure aborted it before that line. The installer then parsed
no count, passed NEITHER --expected NOR --min-total, and the gate's old
default floor of 1 declared "healthy: 54 row(s) >= floor 1" over the exact
ghost it existed to catch. Two independent floors now close that:

  * --min-total has NO default -> an omitted floor exits EX_NO_FLOOR (3).
    The caller must state the floor it expects. (test_degraded_argv_*)
  * --min-role-library (default 1) counts rows WHERE source='role-library'
    -- the ONLY rows CC's converge/importRoleLibrary() writes. A bare
    COUNT(*) conflates the two writers, so a perfect 2,555-row JSONL ingest
    with a FAILED converge (ZERO role-library rows -- the live C2 shape)
    sails straight through it. (test_role_library_*)

WHAT THIS FILE PROVES:
    1. GHOST -- `sops` table exists but is EMPTY (0 rows): exit 1 (EX_GHOST).
    2. GHOST -- `sops` table does not exist at all (migration 028 never
       ran): exit 1, table_exists=false, reason mentions migration 028.
    3. Healthy -- a real-shaped library (2,555 rows incl. role-library rows,
       i.e. BOTH writers landed): exit 0 (EX_OK), ok=true.
    4. The EXACT historical ghost shape (54 rows: 30 test-dept + 24
       legacy-alias, source all NULL) fails loud against a floor that
       reflects a real library.
    5. THE FAIL-OPEN REGRESSION ITSELF: that same 54-row ghost, run under the
       installer's DEGRADED argv (no --min-total, no --expected -- exactly
       what a failed ingest used to produce), now exits 3 instead of
       rubber-stamping it as "healthy: 54 row(s) >= floor 1".
    6. Role-library floor: 2,555 healthy JSONL rows + ZERO role-library rows
       (successful ingest, FAILED converge) exits 4 (EX_NO_ROLE_LIBRARY),
       even though the total is far above --min-total.
    7. A `sops` table with no `source` column at all cannot hold role-library
       rows -> exit 4, has_source_column=false (never a crash, never a pass).
    8. --expected mismatch is WARN-only: total=2555, expected=2600 -> still
       exit 0, but row_count_mismatch=true in the JSON.
    9. Missing mission-control.db entirely -> exit 2 (EX_NO_DB), never
       mistaken for a healthy 0-row PASS.
   10. --min-total / --min-role-library are respected as configurable floors.
   11. JSON output round-trips (run-full-install.sh parses this with
       python3 -c, not by scraping text).

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
EX_NO_FLOOR = _mod.EX_NO_FLOOR
EX_NO_ROLE_LIBRARY = _mod.EX_NO_ROLE_LIBRARY


# --------------------------------------------------------------------------
# Fixture builders
# --------------------------------------------------------------------------
def _make_db(tmp, n_rows=0, with_table=True, sources=None, with_source_col=True,
             name="mission-control.db"):
    """Build a minimal mission-control.db with an optional `sops` table.

    sources: optional list of `source` values (len must equal n_rows) so the
    ghost shape (source all NULL) and the healthy shape (JSONL rows NULL +
    converge rows 'role-library') can be reproduced faithfully.
    with_source_col: omit the `source` column entirely (an older CC schema --
    role-library rows are then structurally impossible).
    """
    db_path = Path(tmp) / name
    conn = sqlite3.connect(db_path)
    if with_table:
        cols = "id TEXT PRIMARY KEY, slug TEXT, name TEXT, department TEXT"
        if with_source_col:
            cols += ", source TEXT"
        conn.execute(f"CREATE TABLE sops ({cols})")
        for i in range(n_rows):
            if with_source_col:
                src = sources[i] if sources else None
                conn.execute(
                    "INSERT INTO sops (id, slug, name, department, source) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (f"sop_{i}", f"slug-{i}", f"SOP {i}", "marketing", src),
                )
            else:
                conn.execute(
                    "INSERT INTO sops (id, slug, name, department) "
                    "VALUES (?, ?, ?, ?)",
                    (f"sop_{i}", f"slug-{i}", f"SOP {i}", "marketing"),
                )
    conn.commit()
    conn.close()
    return db_path


def _healthy_sources(total=2555, role_rows=107):
    """The shape of a library where BOTH writers landed: the JSONL ingest's
    rows (source NULL) plus converge/importRoleLibrary()'s role-library rows."""
    return [None] * (total - role_rows) + ["role-library"] * role_rows


def _capture(argv):
    """Run `run(argv)` and capture stdout, returning (rc, stdout_text)."""
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = run(argv)
    return rc, buf.getvalue()


# --------------------------------------------------------------------------
# Tests -- total-row floor (writer 1: the direct JSONL-asset ingest)
# --------------------------------------------------------------------------
def test_ghost_empty_table_fails_loud():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=0, with_table=True)
        rc, out = _capture(["--db", str(db), "--min-total", "1", "--json"])
        data = json.loads(out)
        assert rc == EX_GHOST, f"expected EX_GHOST, got rc={rc}"
        assert data["ok"] is False
        assert data["total"] == 0
        assert "GHOST" in data["reason"]


def test_ghost_missing_table_fails_loud():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=0, with_table=False)
        rc, out = _capture(["--db", str(db), "--min-total", "1", "--json"])
        data = json.loads(out)
        assert rc == EX_GHOST, f"expected EX_GHOST, got rc={rc}"
        assert data["table_exists"] is False
        assert "migration 028" in data["reason"]


def test_healthy_v2_library_passes():
    """BOTH writers landed: 2,448 JSONL rows (source NULL) + 107 role-library
    rows from converge. This is the only shape that may exit 0."""
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=2555, sources=_healthy_sources())
        rc, out = _capture(
            ["--db", str(db), "--min-total", "1277", "--min-role-library", "1", "--json"]
        )
        data = json.loads(out)
        assert rc == EX_OK, f"expected EX_OK, got rc={rc}: {data}"
        assert data["ok"] is True
        assert data["total"] == 2555
        assert data["role_library_total"] == 107


def test_exact_historical_ghost_shape_fails_against_a_real_floor():
    """The live-observed ghost: 54 rows (30 test-dept + 24 legacy-alias),
    source all NULL.

    PROVES (narrowly): the gate is count-sensitive, not merely emptiness-
    sensitive -- a NONZERO table still fails loud when the caller passes a
    floor that reflects a real library. It does NOT prove the installer
    always passes such a floor; that is exactly what the first fix got wrong,
    and it is proved separately by
    test_degraded_argv_no_min_total_refuses_to_run (script side) and by
    test-sop-library-phase-wiring.sh scenario 4c (installer side).
    """
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=54, sources=[None] * 54)
        rc, out = _capture(["--db", str(db), "--min-total", "500", "--json"])
        data = json.loads(out)
        assert rc == EX_GHOST, f"expected EX_GHOST for the 54-row ghost shape, got rc={rc}"
        assert data["total"] == 54


# --------------------------------------------------------------------------
# Tests -- FAIL-OPEN regression: an absent floor must refuse, never assume
# --------------------------------------------------------------------------
def test_degraded_argv_no_min_total_refuses_to_run():
    """THE REGRESSION THAT FAILED QC, PINNED.

    When ingest-sop-library.sh dies (network/GitHub outage/rate-limit/asset
    gone/gunzip error) it aborts under `set -euo pipefail` BEFORE printing
    "downloaded N SOP records". The first fix parsed no count and therefore
    invoked this gate with NEITHER --expected NOR --min-total -- and the old
    default floor of 1 returned rc=0, ok=true, "healthy: 54 row(s) >= floor
    1" over the CC boot-seed ghost, then stamped
    commandCenterSopLibraryIngested=true.

    This is that EXACT degraded argv against that EXACT ghost DB (54 rows,
    source all NULL). It must now REFUSE (EX_NO_FLOOR), never rubber-stamp.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=54, sources=[None] * 54)
        rc, out = _capture(["--db", str(db), "--json"])   # the degraded argv, verbatim
        data = json.loads(out)
        assert rc == EX_NO_FLOOR, (
            f"a gate invoked with no --min-total MUST refuse (EX_NO_FLOOR={EX_NO_FLOOR}); "
            f"got rc={rc} -- this is the fail-open rubber stamp regressing"
        )
        assert data["ok"] is False
        assert "NO FLOOR" in data["reason"]


def test_no_min_total_refuses_even_on_a_healthy_db():
    """Fail-closed is a property of the INVOCATION, not of the data: even a
    perfectly healthy library must not be blessed by a floorless call."""
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=2555, sources=_healthy_sources())
        rc, _ = _capture(["--db", str(db), "--json"])
        assert rc == EX_NO_FLOOR, f"expected EX_NO_FLOOR regardless of data, got rc={rc}"


# --------------------------------------------------------------------------
# Tests -- role-library floor (writer 2: CC converge -> importRoleLibrary)
# --------------------------------------------------------------------------
def test_role_library_zero_rows_fails_even_when_total_is_healthy():
    """THE C2 SPEC MISS, PINNED. The live evidence is "ZERO role-library
    rows / converge importRoleLibrary never succeeded here" -- with the JSONL
    ingest perfectly healthy. A bare COUNT(*) >= floor passes that. It must
    not: role-library rows are written ONLY by converge(scope=sops), so zero
    of them means the role library is a ghost and Triad routing starves.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=2555, sources=[None] * 2555)  # ingest OK, converge FAILED
        rc, out = _capture(
            ["--db", str(db), "--min-total", "1277", "--min-role-library", "1", "--json"]
        )
        data = json.loads(out)
        assert rc == EX_NO_ROLE_LIBRARY, (
            f"2555 rows with ZERO role-library rows must exit "
            f"EX_NO_ROLE_LIBRARY={EX_NO_ROLE_LIBRARY}, got rc={rc} -- a bare COUNT(*) "
            f"conflates the two writers"
        )
        assert data["total"] == 2555
        assert data["role_library_total"] == 0
        assert "NO ROLE LIBRARY" in data["reason"]


def test_role_library_floor_defaults_to_one_not_zero():
    """The default must be strict (1), never 0 -- an omitted --min-role-library
    must not silently disable the role-library assert."""
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=2555, sources=[None] * 2555)
        rc, out = _capture(["--db", str(db), "--min-total", "1277", "--json"])
        data = json.loads(out)
        assert rc == EX_NO_ROLE_LIBRARY, "default --min-role-library must be 1, not 0"
        assert data["min_role_library"] == 1


def test_missing_source_column_cannot_hold_role_library_rows():
    """An older CC schema with no `source` column: role-library rows are
    structurally impossible, so the gate must fail loud (not crash, not pass)."""
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=2555, with_source_col=False)
        rc, out = _capture(
            ["--db", str(db), "--min-total", "1277", "--min-role-library", "1", "--json"]
        )
        data = json.loads(out)
        assert rc == EX_NO_ROLE_LIBRARY, f"expected EX_NO_ROLE_LIBRARY, got rc={rc}"
        assert data["has_source_column"] is False
        assert data["role_library_total"] == 0
        assert data["total"] == 2555


def test_role_library_source_value_is_overridable():
    """CC's `source` value is a cross-repo contract. If it is ever renamed, the
    installer must be able to track it with one flag, not a code rewrite."""
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=100, sources=[None] * 90 + ["dept-library"] * 10)
        rc_default, _ = _capture(["--db", str(db), "--min-total", "50", "--json"])
        rc_override, out = _capture([
            "--db", str(db), "--min-total", "50",
            "--role-library-source", "dept-library", "--json",
        ])
        data = json.loads(out)
        assert rc_default == EX_NO_ROLE_LIBRARY, "default source must not match 'dept-library'"
        assert rc_override == EX_OK, f"override should find the 10 rows, got rc={rc_override}"
        assert data["role_library_total"] == 10


def test_role_library_floor_is_configurable():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=2555, sources=_healthy_sources(2555, 107))
        rc_low, _ = _capture(["--db", str(db), "--min-total", "1277",
                              "--min-role-library", "107", "--json"])
        rc_high, _ = _capture(["--db", str(db), "--min-total", "1277",
                               "--min-role-library", "108", "--json"])
        assert rc_low == EX_OK, "107 role-library rows should pass a floor of 107"
        assert rc_high == EX_NO_ROLE_LIBRARY, "107 role-library rows should fail a floor of 108"


# --------------------------------------------------------------------------
# Tests -- --expected is WARN-only; exit codes; output contract
# --------------------------------------------------------------------------
def test_expected_mismatch_is_warn_only_never_blocks():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=2555, sources=_healthy_sources())
        rc, out = _capture([
            "--db", str(db), "--min-total", "1277", "--expected", "2600", "--json",
        ])
        data = json.loads(out)
        assert rc == EX_OK, "row-count mismatch vs --expected must be WARN-only, never a hard block"
        assert data["ok"] is True
        assert data["row_count_mismatch"] is True


def test_expected_match_no_mismatch_flag():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=2555, sources=_healthy_sources())
        rc, out = _capture([
            "--db", str(db), "--min-total", "1277", "--expected", "2555", "--json",
        ])
        data = json.loads(out)
        assert rc == EX_OK
        assert data["row_count_mismatch"] is False


def test_missing_db_is_distinct_exit_code():
    with tempfile.TemporaryDirectory() as tmp:
        nonexistent = Path(tmp) / "does-not-exist.db"
        rc, out = _capture(["--db", str(nonexistent), "--min-total", "1", "--json"])
        data = json.loads(out)
        assert rc == EX_NO_DB, f"expected EX_NO_DB, got rc={rc}"
        assert data["ok"] is False
        assert data["total"] == 0  # never mistaken for a healthy 0-row pass


def test_min_total_floor_is_configurable():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=10, sources=[None] * 9 + ["role-library"])
        rc_low, _ = _capture(["--db", str(db), "--min-total", "1"])
        rc_high, _ = _capture(["--db", str(db), "--min-total", "100"])
        assert rc_low == EX_OK, "10 rows (1 role-library) should pass a floor of 1"
        assert rc_high == EX_GHOST, "10 rows should fail a floor of 100"


def test_all_exit_codes_are_distinct():
    """The installer branches on these; a collision would let one failure mode
    be handled as another (that is how a gate starts failing open)."""
    codes = [EX_OK, EX_GHOST, EX_NO_DB, EX_NO_FLOOR, EX_NO_ROLE_LIBRARY]
    assert len(set(codes)) == len(codes), f"exit codes collide: {codes}"
    assert EX_OK == 0 and all(c != 0 for c in codes[1:]), "only EX_OK may be 0"


def test_json_output_round_trips():
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp, n_rows=5, sources=[None] * 4 + ["role-library"])
        rc, out = _capture(["--db", str(db), "--min-total", "1", "--json"])
        data = json.loads(out)  # must not raise
        expected_keys = {
            "db_path", "total", "role_library_total", "table_exists",
            "has_source_column", "ok", "row_count_mismatch", "min_total",
            "min_role_library", "reason",
        }
        assert expected_keys.issubset(data.keys()), (
            f"missing keys the installer parses: {expected_keys - set(data.keys())}"
        )
        assert rc == EX_OK


def test_text_mode_prints_pass_fail_label():
    with tempfile.TemporaryDirectory() as tmp:
        db_pass = _make_db(tmp, n_rows=5, sources=[None] * 4 + ["role-library"])
        _, out_pass = _capture(["--db", str(db_pass), "--min-total", "1"])
        assert out_pass.startswith("[assert-sop-library-populated] PASS:")

        sub = Path(tmp) / "sub"
        sub.mkdir(exist_ok=True)
        db_fail = _make_db(sub, n_rows=0)
        _, out_fail = _capture(["--db", str(db_fail), "--min-total", "1"])
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
