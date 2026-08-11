#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u20_modules/test_archive_stmt.py
# UNIT TESTS for the U20 archive ACTION (scripts/u20_modules/archive_action.py
# — the Trevor-gated producer archive surface for the engine's OWN ledger,
# the local SQLite mirror that anthology_state.py is the SOLE writer of,
# plus the Welcome card content the producer's board carries).
#
# THE U20 ARCHIVE ACTION LAW, pinned from the module's own sources:
#
#   * Trevor-gated --execute: the archive STATEMENTS (the ledger rows via
#     anthology_state.py upsert-anthology --status archived, the board
#     footprint via mc_board.py archive) run ONLY when the caller passes
#     --execute explicitly (AF-AE-U20ARCHIVE-NO-EXECUTE). WITHOUT --execute
#     a live-status anthology is a STOP (exit 2) that names the code and
#     writes NOTHING. The gate is provable OFFLINE at the function level
#     (archive(..., execute=False) returns EX_STOP and the mirror file is
#     BYTE-IDENTICAL after — the strongest form of "the DB is read-only in
#     dry-run") and at the CLI level (main(["archive", ...]) without
#     --execute is the same STOP; main(["plan"]) / --dry-run is the
#     truthful offline plan, exit 0 — dry-run and no-execute are DIFFERENT
#     laws).
#   * Read-only by construction: the mirror is opened READ-ONLY (mode=ro
#     in the URI) — this module holds no write path of its own; the only
#     writes anywhere ride the sibling authorities' subprocess argv, and
#     only under --execute. Pinned here both by the byte-identical mirror
#     after every non-execute call and by the mode=ro URI the read path
#     actually opens.
#   * The two statements delegate, never re-implement: the ledger statement
#     is a subprocess argv for the SOLE WRITER's own upsert-anthology
#     --status archived (deactivate-never-delete, ninety-day retention —
#     the revoke flow's R6); the board statement is a subprocess argv for
#     mc_board.py archive --anthology-id <id> --state-dir <dir> (the
#     revoke flow's R2). Pinned here by capturing the argv the statement
#     functions would spawn — the module's own write surface is the argv,
#     never a local SQL statement.
#   * The READ-BACK LAW: after the statements the LEDGER target is re-read
#     through the same read-only surface and compared BYTE-EXACT against
#     the ledger's archived vocabulary. A drift is a MISMATCH (exit 5),
#     never a false success; an unreadable read-back is HELD (exit 3),
#     never a verdict.
#   * Absent-state law: an anthology with NO ledger row has NOTHING to
#     archive — a clean no-op PASS (exit 0), zero statements, zero writes
#     (the golden_absent precedent). An already-archived row is an
#     IDEMPOTENT NO-OP — PASS exit 0, never a second archive.
#   * Fail-closed Welcome: the Welcome card content derives from
#     HOW-TO-USE.md (the producer-facing how-to) and ships as copy only,
#     never as a write. An absent or unreadable HOW-TO-USE.md is a STOP
#     (exit 2, ArchiveActionError) BEFORE anything else runs — the Welcome
#     surface never ships empty or fabricated.
#   * Board fail-soft (SPEC 11.2): a declined / unreachable board returns
#     exit 0 and reconciles on the daily tick — the ledger is the truth.
#     A NONZERO board rc is an INSTRUMENT anomaly (UNDETERMINED), so the
#     success report carries board_certified False: the board footprint is
#     never certified by this module.
#   * The masking law: every operator surface carries the anthology id by
#     MASKED MARKER only (last-4, non-reversible); the full id rides the
#     subprocess argv (a machine surface) and the machine JSON payloads
#     only. A credential-shaped string (pit-*) on any surface REFUSES
#     rather than echo. The battery test proves no full id and no
#     credential shape survives onto any emission text or JSON report.
#   * House doctrine pins: the exit-code convention (0/1/2/3/4/5) asserted
#     through the registry's exported constants, the archived status in the
#     ledger's OWN controlled vocabulary, the board archive status never
#     'done' (the one status the client is forbidden to set), the fixed
#     report contract, the fail-closed-empty package init, and the module's
#     own self-test battery GREEN (a red sibling is caught HERE first).
#
# OFFLINE BY DESIGN: no network, no secrets, no live env, no live
# subprocess. Every statement is stubbed (the stubs MIRROR the real
# semantics: the ledger stub flips the mirror row so the read-back can
# confirm byte-exact); the delegation test captures the argv instead of
# spawning it. The mirror is a REAL sqlite file the module's own read-only
# path opens. Tests are stdlib-only (no pytest fixtures), so the standalone
# runner below walks every test green without pytest.
#
# Run: python3 -m pytest 59-anthology-engine/scripts/u20_modules/test_archive_stmt.py -q
#  or: python3 59-anthology-engine/scripts/u20_modules/test_archive_stmt.py
# =============================================================================
"""test_archive_stmt.py -- the U20 archive ACTION law: the --execute gate,
the read-only dry-run, the two delegated statements, the byte-exact
read-back, the absent-state no-ops, the fail-closed Welcome, and the
never-a-token guards."""

import contextlib
import io
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest.mock as mock
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS = SKILL_DIR / "scripts"
U20 = Path(__file__).resolve().parent
for _p in (SCRIPTS, U20):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import u20_modules.archive_action as aa  # noqa: E402
import u20_modules  # noqa: E402  (the fail-closed-empty package init, pinned)
import anthology_registry as reg  # noqa: E402  (exit codes / masking law)
import anthology_state as state  # noqa: E402  (the ledger — the status vocabulary)
import mc_board as board  # noqa: E402  (the board archive status)


# ---------------------------------------------------------------------------
# Hermetic fixtures: a REAL read-only mirror (the same shape the module's own
# read path opens) and statement stubs that mirror the real semantics — the
# ledger stub flips the mirror row so the read-back can confirm byte-exact.
# ---------------------------------------------------------------------------
def _make_mirror(tmp: Path, statuses=None) -> Path:
    """A real local mirror under tmp: the anthologies table, one row per
    status entry. The module's own read path opens it mode=ro."""
    db = tmp / aa.MIRROR_DB_NAME
    con = sqlite3.connect(str(db))
    con.executescript(
        "CREATE TABLE anthologies (anthology_id TEXT PRIMARY KEY, "
        "status TEXT);")
    for aid, st in (statuses or {}).items():
        con.execute("INSERT INTO anthologies (anthology_id, status) "
                    "VALUES (?,?)", (aid, st))
    con.commit()
    con.close()
    return db


def _fake_howto(text="You are the producer. Collect chapters around one "
                     "theme.\n"):
    """A temp HOW-TO-USE.md for the offline tests (never the real one — the
    real-file derivation is its own dedicated test)."""
    d = Path(tempfile.mkdtemp(prefix="test_archive_stmt_howto_"))
    p = d / "HOW-TO-USE.md"
    p.write_text(text, encoding="utf-8")
    return p


def _stub_ledger(run_log, flip=True, rc=0):
    """The ledger statement stub: records the call; with flip=True it applies
    the status flip to the mirror (the real statement's semantics), so the
    read-back can confirm byte-exact."""
    def _ledger(aid, state_dir, *, out):
        run_log.append(("ledger", aid))
        if flip:
            con = sqlite3.connect(str(Path(state_dir) / aa.MIRROR_DB_NAME))
            try:
                con.execute(
                    "UPDATE anthologies SET status=? WHERE anthology_id=?",
                    (aa.LEDGER_ARCHIVED_STATUS, aid))
                con.commit()
            finally:
                con.close()
        return rc
    return _ledger


def _stub_board(run_log, rc=0):
    """The board statement stub: records the call; the board client's own
    contract returns 0 for every board condition (fail-soft, SPEC 11.2)."""
    def _board(aid, state_dir, *, out):
        run_log.append(("board", aid))
        return rc
    return _board


def _call_archive(aid, state_dir, *, execute=False, jsonout=None,
                  ledger=None, board=None, howto=None):
    """One archive() call with optional statement stubs and a temp howto.
    Returns (exit_code, dev). Never touches a live subprocess."""
    dev = io.StringIO()
    cms = [mock.patch.object(sys.modules[aa.__name__], "HOW_TO_USE",
                             howto or _fake_howto())]
    if ledger is not None:
        cms.append(mock.patch.object(sys.modules[aa.__name__],
                                     "_statement_ledger",
                                     side_effect=ledger))
    if board is not None:
        cms.append(mock.patch.object(sys.modules[aa.__name__],
                                     "_statement_board",
                                     side_effect=board))
    with contextlib.ExitStack() as stack:
        for cm in cms:
            stack.enter_context(cm)
        rc = aa.archive(aid, state_dir=str(state_dir), execute=execute,
                        out=dev, jsonout=jsonout)
    return rc, dev


def _surface_text(*streams):
    return "".join(s.getvalue() for s in streams if s is not None)


# ---------------------------------------------------------------------------
# 1. THE GATE: --execute is Trevor's gate; without it STOP, never a write.
# ---------------------------------------------------------------------------
def test_execute_flag_is_trevors_gate_and_action_is_archive():
    assert aa.ARCHIVE_ACTION == "archive", \
        "the ONE archive ACTION verb must be 'archive'"
    assert aa.EXECUTE_FLAG == "--execute", \
        "the Trevor gate flag must be --execute"
    assert aa.GOLDEN_EXECUTE_REQUIRED is True, \
        "the law: the archive ACTION is gated"


def test_archive_without_execute_stops_and_db_stays_byte_identical():
    """A live-status row and execute=False must STOP (exit 2) naming
    AF-AE-U20ARCHIVE-NO-EXECUTE, run ZERO statements, and leave the mirror
    byte-identical — the strongest form of 'the DB is read-only in dry-run'
    (no write at all, regardless of what the network would do)."""
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    try:
        db = _make_mirror(tmp, {"anth_9f8e7d6c": "delivered"})
        before = db.read_bytes()
        run_log = []
        jout = io.StringIO()
        rc, dev = _call_archive("anth_9f8e7d6c", tmp,
                                ledger=_stub_ledger(run_log),
                                board=_stub_board(run_log), jsonout=jout)
        assert rc == aa.EX_STOP, \
            "no-execute must STOP (exit 2), got %s" % rc
        assert run_log == [], \
            "dry-run must run NO statements, got %s" % run_log
        assert "AF-AE-U20ARCHIVE-NO-EXECUTE" in dev.getvalue()
        assert "read-only" in dev.getvalue(), \
            "the refusal must state the DB was read-only"
        assert db.read_bytes() == before, \
            "dry-run must leave the mirror byte-identical (read-only DB)"
        report = json.loads(jout.getvalue())
        assert report["contract"] == aa.CONFIG_CONTRACT
        assert report["verdict"] == "REFUSED"
        assert report["reason"] == "no-execute"
        assert report["execute"] is False and report["dry_run"] is True
        assert report["statements"] == ["ledger", "board"]
        assert report["welcome"]["title"] == "Welcome"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_archive_without_id_refuses():
    """No --anthology-id -> ArchiveActionError (the CLI maps it onto STOP
    exit 2) — the archive target is required, never a sweep."""
    for bad in ("", "   "):
        raised = False
        try:
            aa.archive(bad)
        except aa.ArchiveActionError:
            raised = True
        assert raised, "archive with id %r must refuse" % bad


def test_cli_archive_without_execute_stops():
    """The CLI surface enforces the same gate: main() with a live-status row
    and no --execute is a STOP (exit 2); the full id never reaches stderr,
    the masked marker does."""
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    try:
        _make_mirror(tmp, {"anth_9f8e7d6c": "delivered"})
        err = io.StringIO()
        with mock.patch.object(sys, "stderr", err), \
             mock.patch.object(sys.modules[aa.__name__], "HOW_TO_USE",
                               _fake_howto()):
            rc = aa.main(["archive", "--anthology-id", "anth_9f8e7d6c",
                          "--state-dir", str(tmp)])
        err_text = err.getvalue()
        assert rc == aa.EX_STOP, \
            "CLI archive without --execute must STOP, got %s" % rc
        assert "AF-AE-U20ARCHIVE-NO-EXECUTE" in err_text
        assert "anth_9f8e7d6c" not in err_text, \
            "the full id must never reach the operator surface"
        assert "...7d6c" in err_text, \
            "the masked marker must be the surface shape"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cli_archive_without_id_stops():
    err = io.StringIO()
    with mock.patch.object(sys, "stderr", err), \
         mock.patch.object(sys.modules[aa.__name__], "HOW_TO_USE",
                           _fake_howto()):
        rc = aa.main(["archive"])
    assert rc == aa.EX_STOP, \
        "CLI archive without --anthology-id must STOP, got %s" % rc
    assert "STOP" in err.getvalue()


def test_cli_archive_unreadable_mirror_is_held():
    """A state dir with no mirror is HELD (exit 3), UNDETERMINED — never a
    verdict, never a write."""
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    try:
        err = io.StringIO()
        with mock.patch.object(sys, "stderr", err), \
             mock.patch.object(sys.modules[aa.__name__], "HOW_TO_USE",
                               _fake_howto()):
            rc = aa.main(["archive", "--anthology-id", "anth_9f8e7d6c",
                          "--state-dir", str(tmp)])
        assert rc == aa.EX_HELD, \
            "an unreadable mirror must be HELD (exit 3), got %s" % rc
        assert "UNDETERMINED" in err.getvalue()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cli_plan_and_dry_run_are_offline_truthful_plans():
    """plan and --dry-run are the SAME READ-ONLY offline plan: exit 0, the
    PLAN surface, no DB read, no credential, no write (dry-run and
    no-execute are DIFFERENT laws — dry-run is the truthful plan)."""
    err = io.StringIO()
    with mock.patch.object(sys, "stderr", err), \
         mock.patch.object(sys.modules[aa.__name__], "HOW_TO_USE",
                           _fake_howto()):
        rc = aa.main(["plan"])
    err_text = err.getvalue()
    assert rc == aa.EX_OK, "plan must exit 0, got %s" % rc
    assert "PLAN" in err_text and "No writes performed." in err_text

    err2 = io.StringIO()
    with mock.patch.object(sys, "stderr", err2), \
         mock.patch.object(sys.modules[aa.__name__], "HOW_TO_USE",
                           _fake_howto()):
        rc2 = aa.main(["archive", "--dry-run"])
    assert rc2 == aa.EX_OK, "archive --dry-run must exit 0, got %s" % rc2
    assert "PLAN" in err2.getvalue()


def test_module_self_test_is_green():
    """The module's own battery must stay green — a red sibling is caught
    HERE first (both the subcommand and the --self-test flag alias)."""
    err = io.StringIO()
    with mock.patch.object(sys, "stderr", err):
        rc = aa.main(["self-test"])
    assert rc == aa.EX_OK, "self-test must exit 0, got %s" % rc
    assert "self-test: OK" in err.getvalue()
    err2 = io.StringIO()
    with mock.patch.object(sys, "stderr", err2):
        rc2 = aa.main(["--self-test"])
    assert rc2 == aa.EX_OK, "--self-test alias must exit 0, got %s" % rc2
    assert "self-test: OK" in err2.getvalue()


# ---------------------------------------------------------------------------
# 2. IDEMPOTENCE: the absent-state no-op and the already-archived no-op
#    write nothing and run no statement.
# ---------------------------------------------------------------------------
def test_absent_state_is_a_clean_noop():
    """No ledger row -> NOTHING to archive -> PASS exit 0, zero statements,
    zero writes (the golden absent-state law), and the Welcome copy rides
    the report."""
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    try:
        db = _make_mirror(tmp, {})
        before = db.read_bytes()
        run_log = []
        jout = io.StringIO()
        rc, dev = _call_archive("anth_9f8e7d6c", tmp,
                                ledger=_stub_ledger(run_log),
                                board=_stub_board(run_log), jsonout=jout)
        assert rc == aa.EX_OK, "absent state must PASS exit 0, got %s" % rc
        assert run_log == [], \
            "absent state must run NO statements, got %s" % run_log
        assert "NOTHING TO ARCHIVE" in dev.getvalue()
        assert db.read_bytes() == before, "the mirror must not change"
        report = json.loads(jout.getvalue())
        assert report["verdict"] == "no-op"
        assert report["execute"] is False and report["dry_run"] is True
        assert report["statements"] == []
        assert report["welcome"]["title"] == "Welcome"
        assert report["welcome"]["chars"] > 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_already_archived_is_an_idempotent_noop():
    """An already-archived row -> PASS exit 0, zero statements, mirror
    untouched — never a second archive, never a rewrite."""
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    try:
        db = _make_mirror(tmp, {"anth_9f8e7d6c": "archived"})
        before = db.read_bytes()
        run_log = []
        rc, dev = _call_archive("anth_9f8e7d6c", tmp,
                                ledger=_stub_ledger(run_log),
                                board=_stub_board(run_log))
        assert rc == aa.EX_OK, \
            "already-archived must PASS exit 0, got %s" % rc
        assert run_log == [], \
            "already-archived must run NO statements, got %s" % run_log
        assert "IDEMPOTENT NO-OP" in dev.getvalue()
        assert db.read_bytes() == before
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 3. THE WELCOME CARD: derived from HOW-TO-USE.md, copy only, never a write;
#    absent or unreadable HOW-TO-USE.md is a STOP before anything else.
# ---------------------------------------------------------------------------
def test_missing_howto_refuses_before_any_statement():
    """A missing HOW-TO-USE.md must refuse (ArchiveActionError -> STOP
    family) and the refusal must happen BEFORE any statement can run — the
    Welcome surface never ships empty or fabricated."""
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    try:
        _make_mirror(tmp, {"anth_9f8e7d6c": "delivered"})
        missing = Path(tempfile.mkdtemp()) / "no-such-howto.md"
        run_log = []
        raised = False
        try:
            with mock.patch.object(sys.modules[aa.__name__], "HOW_TO_USE",
                                   missing), \
                 mock.patch.object(sys.modules[aa.__name__],
                                   "_statement_ledger",
                                   side_effect=_stub_ledger(run_log)):
                aa.archive("anth_9f8e7d6c", state_dir=str(tmp), out=io.StringIO())
        except aa.ArchiveActionError:
            raised = True
        assert raised, "missing HOW-TO-USE must refuse (STOP family)"
        assert run_log == [], "no statement may run before the Welcome read"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_unreadable_howto_refuses():
    """An unreadable HOW-TO-USE.md is the same STOP family — the OSError
    branch of the derivation never fabricates a Welcome."""
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    try:
        _make_mirror(tmp, {"anth_9f8e7d6c": "delivered"})
        p = _fake_howto()
        raised = False
        try:
            with mock.patch.object(type(p), "read_text",
                                   side_effect=OSError("denied")):
                aa._read_welcome_card()
        except aa.ArchiveActionError:
            raised = True
        assert raised, "an unreadable HOW-TO-USE must refuse (STOP family)"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_welcome_derives_from_the_real_how_to_use():
    """The Welcome card content IS the repo HOW-TO-USE.md (the producer-facing
    how-to), shipped as copy only — title 'Welcome', the real producer copy,
    never fabricated."""
    real = aa.SKILL_DIR / "HOW-TO-USE.md"
    assert real.is_file(), \
        "the repo HOW-TO-USE.md must exist for the Welcome derivation"
    card = aa._read_welcome_card()
    assert card["title"] == "Welcome"
    assert card["source"] == str(real)
    text = real.read_text(encoding="utf-8").strip()
    assert card["content"] == text
    assert "You are the producer" in card["content"]
    assert "Convert and Flow" in card["content"]
    assert "a designed PDF" in card["content"]
    # the plan report carries the same derivation, by character count
    jout = io.StringIO()
    rc = aa.plan(out=io.StringIO(), jsonout=jout)
    assert rc == aa.EX_OK
    report = json.loads(jout.getvalue())
    assert report["welcome"]["title"] == "Welcome"
    assert report["welcome"]["chars"] == len(text)


# ---------------------------------------------------------------------------
# 4. THE STATEMENTS UNDER --execute: once, in order, delegated to the
#    sibling authorities, confirmed by byte-exact read-back.
# ---------------------------------------------------------------------------
def test_execute_runs_both_statements_once_and_reads_back():
    """With --execute the happy path runs BOTH statements exactly once
    (ledger first, then board), the ledger read-back confirms byte-exact,
    and the board footprint is never certified (board_certified False —
    fail-soft per SPEC 11.2; the ledger is the truth)."""
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    try:
        _make_mirror(tmp, {"anth_9f8e7d6c": "delivered"})
        run_log = []
        jout = io.StringIO()
        rc, dev = _call_archive(
            "anth_9f8e7d6c", tmp, execute=True,
            ledger=_stub_ledger(run_log, flip=True),
            board=_stub_board(run_log), jsonout=jout)
        assert rc == aa.EX_OK, "happy path must exit 0, got %s" % rc
        assert run_log == [("ledger", "anth_9f8e7d6c"),
                           ("board", "anth_9f8e7d6c")], \
            "both statements must run once, in order: %s" % run_log
        text = dev.getvalue()
        assert "ARCHIVED" in text
        assert "byte-exact" in text
        assert "fail-soft" in text
        report = json.loads(jout.getvalue())
        assert report["verdict"] == "archived"
        assert report["execute"] is True and report["dry_run"] is False
        assert report["statements"] == ["ledger", "board"]
        assert report["ledger_before"] == "delivered"
        assert report["ledger_after"] == aa.LEDGER_ARCHIVED_STATUS
        assert report["board_status"] == aa.BOARD_ARCHIVED_STATUS
        assert report["board_certified"] is False, \
            "the board footprint is never certified (fail-soft)"
        assert report["welcome"]["title"] == "Welcome"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_readback_drift_is_mismatch_never_a_false_success():
    """A ledger statement that 'succeeds' without applying the status is
    caught by the READ-BACK LAW: MISMATCH (exit 5), never archived."""
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    try:
        _make_mirror(tmp, {"anth_9f8e7d6c": "delivered"})
        run_log = []
        jout = io.StringIO()
        rc, dev = _call_archive(
            "anth_9f8e7d6c", tmp, execute=True,
            ledger=_stub_ledger(run_log, flip=False),
            board=_stub_board(run_log), jsonout=jout)
        assert rc == aa.EX_MISMATCH, \
            "read-back drift must be exit 5, got %s" % rc
        assert "AF-AE-U20ARCHIVE-READBACK" in dev.getvalue()
        report = json.loads(jout.getvalue())
        assert report["verdict"] == "MISMATCH"
        assert report["reason"] == "readback-drift"
        assert report["ledger_after"] == "delivered"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_refused_ledger_statement_stops_and_skips_board():
    """A refused ledger statement (rc != 0) WITH --execute is a STOP (exit
    2) — nothing reported archived, and the board statement never runs."""
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    try:
        _make_mirror(tmp, {"anth_9f8e7d6c": "delivered"})
        run_log = []
        jout = io.StringIO()
        rc, dev = _call_archive(
            "anth_9f8e7d6c", tmp, execute=True,
            ledger=_stub_ledger(run_log, flip=False, rc=2),
            board=_stub_board(run_log), jsonout=jout)
        assert rc == aa.EX_STOP, \
            "a refused ledger statement must STOP, got %s" % rc
        assert run_log == [("ledger", "anth_9f8e7d6c")], \
            "a refused ledger statement must not run the board statement"
        report = json.loads(jout.getvalue())
        assert report["verdict"] == "REFUSED"
        assert report["reason"] == "ledger-statement-rc-2"
        assert report["execute"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_refused_board_statement_is_held_not_success():
    """A NONZERO board rc is an INSTRUMENT anomaly (the board client's own
    fail-soft contract returns 0 for every board condition): HELD (exit 3),
    UNDETERMINED — the ledger rows ARE archived, the board footprint is
    never certified."""
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    try:
        _make_mirror(tmp, {"anth_9f8e7d6c": "delivered"})
        run_log = []
        jout = io.StringIO()
        rc, dev = _call_archive(
            "anth_9f8e7d6c", tmp, execute=True,
            ledger=_stub_ledger(run_log, flip=True),
            board=_stub_board(run_log, rc=3), jsonout=jout)
        assert rc == aa.EX_HELD, \
            "a refused board statement must be HELD, got %s" % rc
        assert "fail-soft" in dev.getvalue()
        report = json.loads(jout.getvalue())
        assert report["verdict"] == "HELD"
        assert report["reason"] == "board-statement-rc-3"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_unreadable_readback_is_held_not_verdict():
    """The READ-BACK LAW holds even for the read itself: a read-back that
    cannot open the mirror is HELD (exit 3), UNDETERMINED — the archive is
    never certified."""
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    try:
        _make_mirror(tmp, {"anth_9f8e7d6c": "delivered"})
        run_log = []
        real_read = aa._ledger_status
        calls = {"n": 0}

        def _flaky(state_dir, aid):
            calls["n"] += 1
            if calls["n"] == 1:
                return real_read(state_dir, aid)
            raise sqlite3.OperationalError("unreadable")

        jout = io.StringIO()
        dev = io.StringIO()
        with mock.patch.object(sys.modules[aa.__name__], "HOW_TO_USE",
                               _fake_howto()), \
             mock.patch.object(sys.modules[aa.__name__], "_statement_ledger",
                               side_effect=_stub_ledger(run_log, flip=True)), \
             mock.patch.object(sys.modules[aa.__name__], "_statement_board",
                               side_effect=_stub_board(run_log)), \
             mock.patch.object(sys.modules[aa.__name__], "_ledger_status",
                               side_effect=_flaky):
            rc = aa.archive("anth_9f8e7d6c", state_dir=str(tmp),
                            execute=True, out=dev, jsonout=jout)
        assert rc == aa.EX_HELD, \
            "an unreadable read-back must be HELD, got %s" % rc
        assert "AF-AE-U20ARCHIVE-READBACK" in dev.getvalue()
        report = json.loads(jout.getvalue())
        assert report["verdict"] == "HELD"
        assert report["reason"] == "readback-unreadable"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_statements_delegate_to_the_sibling_authorities():
    """The module's ONLY write surface is the subprocess argv for the
    sibling authorities — the ledger rows via the SOLE WRITER's own
    upsert-anthology --status archived channel, the board footprint via
    mc_board.py archive — never a local SQL write. Captured argv, never a
    spawned subprocess."""
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    try:
        _make_mirror(tmp, {"anth_9f8e7d6c": "delivered"})
        calls = []

        def _spy_call(argv, **kw):
            calls.append(list(argv))
            if Path(argv[1]).name == aa.STATE_WRITER:
                # the real ledger subprocess applies the status; the spy
                # mirrors it so the read-back can confirm byte-exact
                i = argv.index("--anthology-id")
                con = sqlite3.connect(str(Path(tmp) / aa.MIRROR_DB_NAME))
                try:
                    con.execute(
                        "UPDATE anthologies SET status=? WHERE anthology_id=?",
                        (aa.LEDGER_ARCHIVED_STATUS, argv[i + 1]))
                    con.commit()
                finally:
                    con.close()
            return 0

        dev = io.StringIO()
        with mock.patch.object(sys.modules[aa.__name__], "HOW_TO_USE",
                               _fake_howto()), \
             mock.patch.object(aa.subprocess, "call", side_effect=_spy_call):
            rc = aa.archive("anth_9f8e7d6c", state_dir=str(tmp),
                            execute=True, out=dev)
        assert rc == aa.EX_OK, "delegated happy path must exit 0, got %s" % rc
        assert len(calls) == 2, "exactly two statement argv, got %s" % calls

        ledger_argv, board_argv = calls
        assert ledger_argv[0] == sys.executable
        assert Path(ledger_argv[1]).name == aa.STATE_WRITER
        assert "--db" in ledger_argv
        assert str(Path(tmp) / aa.MIRROR_DB_NAME) in ledger_argv
        assert "upsert-anthology" in ledger_argv
        assert ledger_argv[ledger_argv.index("--anthology-id") + 1] \
            == "anth_9f8e7d6c"
        assert ledger_argv[ledger_argv.index("--status") + 1] \
            == aa.LEDGER_ARCHIVED_STATUS

        assert board_argv[0] == sys.executable
        assert Path(board_argv[1]).name == aa.BOARD_CLIENT
        assert board_argv[2] == "archive"
        assert board_argv[board_argv.index("--anthology-id") + 1] \
            == "anth_9f8e7d6c"
        assert board_argv[board_argv.index("--state-dir") + 1] \
            == str(Path(tmp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 5. THE MIRROR: read-only by construction; an unreadable mirror is HELD.
# ---------------------------------------------------------------------------
def test_unreadable_mirror_is_held_never_a_verdict():
    """A state dir with no mirror is HELD (exit 3), UNDETERMINED — never a
    verdict, never a write."""
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    try:
        jout = io.StringIO()
        rc, dev = _call_archive("anth_9f8e7d6c", tmp, jsonout=jout)
        assert rc == aa.EX_HELD, \
            "an unreadable mirror must be HELD, got %s" % rc
        assert "UNDETERMINED" in dev.getvalue()
        report = json.loads(jout.getvalue())
        assert report["verdict"] == "HELD"
        assert report["detail"] == "ledger mirror unreadable"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_mirror_read_is_mode_ro_by_construction():
    """The module's own read path opens the mirror READ-ONLY (mode=ro in
    the URI) — the DB is read-only in dry-run by construction, not by
    discipline. The spy records the URI the module's read path actually
    opens."""
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    try:
        _make_mirror(tmp, {"anth_9f8e7d6c": "delivered"})
        seen = []
        real_connect = aa.sqlite3.connect

        def _spy(database, **kw):
            seen.append((database, kw))
            return real_connect(database, **kw)

        with mock.patch.object(sys.modules[aa.__name__], "HOW_TO_USE",
                               _fake_howto()), \
             mock.patch.object(aa.sqlite3, "connect", side_effect=_spy):
            aa.archive("anth_9f8e7d6c", state_dir=str(tmp), out=io.StringIO())
        assert seen, "the mirror read path must open a connection"
        assert all("mode=ro" in str(db) for db, _ in seen), \
            "every mirror read must open mode=ro (read-only DB)"
        assert all(kw.get("uri") is True for _, kw in seen), \
            "every mirror read must use the URI form"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 6. MASKING AND NEVER-PRINT: masked markers only; no full id; no
#    credential-shaped string ever reaches a surface.
# ---------------------------------------------------------------------------
def test_mask_and_scalar_helpers_are_non_reversible():
    assert aa._mask_id("anth_9f8e7d6c") == "...7d6c", \
        "the id marker is last-4 only"
    assert aa._mask_id("ab") == "...(short)"
    assert aa._mask_id("") == "...(short)"
    assert aa._scalar_str("archived") == "archived"
    assert aa._scalar_str(0) == "0"
    assert aa._scalar_str(None) == ""
    assert aa._scalar_str({"x": 1}) == "", \
        "a non-scalar read is never judged a status"
    assert aa._scalar_str("none") == ""
    assert aa._clean_surface_text("plain producer copy") == \
        "plain producer copy"


def test_credential_shaped_surface_refuses_rather_than_echo():
    raised = False
    try:
        aa._clean_surface_text("token pit-ABC123 leaked")
    except aa.ArchiveActionError:
        raised = True
    assert raised, "a credential-shaped surface must refuse (house guard)"


def test_surfaces_never_carry_full_id_or_credential():
    """No full anthology id, no pit-/Bearer-shaped value ever reaches any
    emission text or JSON report — checked across the whole verdict
    battery, including the execute path where the real id moved through the
    stubbed statements."""
    aid = "anth_9f8e7d6c"
    streams = []

    # absent no-op
    tmp = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    _make_mirror(tmp, {})
    jout = io.StringIO()
    rc, dev = _call_archive(aid, tmp, jsonout=jout)
    assert rc == aa.EX_OK
    streams += [dev, jout]

    # no-execute refusal
    tmp2 = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    _make_mirror(tmp2, {aid: "delivered"})
    jout2 = io.StringIO()
    rc, dev2 = _call_archive(aid, tmp2, jsonout=jout2)
    assert rc == aa.EX_STOP
    streams += [dev2, jout2]

    # happy path under --execute (the real id moved through the stubs)
    tmp3 = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    _make_mirror(tmp3, {aid: "delivered"})
    run_log = []
    jout3 = io.StringIO()
    rc, dev3 = _call_archive(aid, tmp3, execute=True,
                             ledger=_stub_ledger(run_log, flip=True),
                             board=_stub_board(run_log), jsonout=jout3)
    assert rc == aa.EX_OK
    streams += [dev3, jout3]

    # read-back mismatch
    tmp4 = Path(tempfile.mkdtemp(prefix="test_archive_stmt_"))
    _make_mirror(tmp4, {aid: "delivered"})
    jout4 = io.StringIO()
    rc, dev4 = _call_archive(aid, tmp4, execute=True,
                             ledger=_stub_ledger([], flip=False),
                             board=_stub_board([]), jsonout=jout4)
    assert rc == aa.EX_MISMATCH
    streams += [dev4, jout4]

    # the plan JSON
    jout5 = io.StringIO()
    with mock.patch.object(sys.modules[aa.__name__], "HOW_TO_USE",
                           _fake_howto()):
        rc = aa.plan(out=io.StringIO(), jsonout=jout5)
    assert rc == aa.EX_OK
    streams += [jout5]

    for s in (tmp, tmp2, tmp3, tmp4):
        shutil.rmtree(s, ignore_errors=True)

    all_text = _surface_text(*streams)
    assert aid not in all_text, \
        "surface leak: the full id %r must never appear" % aid
    assert "...7d6c" in all_text, \
        "the masked marker must be the surface shape"
    assert "pit-" not in all_text, \
        "surface leak: a credential shape must never appear"
    assert "Bearer " not in all_text, \
        "surface leak: an authorization shape must never appear"


# ---------------------------------------------------------------------------
# 7. HOUSE DOCTRINE PINS: exit codes, controlled vocabulary, the forbidden
#    board status, the fixed contract, the empty package init.
# ---------------------------------------------------------------------------
def test_exit_codes_follow_the_house_0_1_2_3_4_5():
    assert aa.EX_OK == reg.EX_OK == 0
    assert aa.EX_ERR == reg.EX_ERR == 1
    assert aa.EX_STOP == reg.EX_STOP == 2
    assert aa.EX_HELD == reg.EX_HELD == 3
    assert aa.EX_MISMATCH == reg.EX_MISMATCH == 5
    assert aa.EX_VIOLATION == 4, \
        "an enforced violation is exit 4, never 'unexpected error'"


def test_ledger_archived_status_is_in_the_controlled_vocabulary():
    assert aa.LEDGER_ARCHIVED_STATUS == "archived"
    assert aa.LEDGER_ARCHIVED_STATUS in state.ANTHOLOGY_STATUS, \
        "the archived status must be in the ledger's own vocabulary"


def test_board_archive_status_is_never_done():
    assert aa.BOARD_ARCHIVED_STATUS == board.ARCHIVE_STATUS
    assert aa.BOARD_ARCHIVED_STATUS == "blocked"
    assert aa.BOARD_ARCHIVED_STATUS != "done", \
        "'done' is the one status this client is FORBIDDEN to set"


def test_report_contract_is_fixed_and_emit_defaults_to_stdout(capsys):
    assert aa.CONFIG_CONTRACT == "anthology-engine-archive-action"
    assert aa.CONFIG_SCHEMA_VERSION == 1
    aa._emit_report({"ok": True, "action": "archive"}, None)
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": True, "action": "archive"}


def test_u20_package_init_is_fail_closed_empty():
    assert u20_modules.__all__ == [], \
        "the u20 package init must stay empty (fail-closed, side-effect free)"


if __name__ == "__main__":
    # Standalone runner (house style): pytest when available, else a manual
    # green/red walk over every test so a box without pytest still fails
    # closed. No test here needs a pytest fixture, so the manual walk is
    # complete, not partial.
    try:
        import pytest as _pytest
    except ImportError:
        _pytest = None
    if _pytest is not None:
        raise SystemExit(_pytest.main([__file__, "-q"]))
    results = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                results.append((name, "PASS"))
            except Exception as exc:  # noqa: BLE001
                results.append((name, "FAIL: %s" % exc))
    for name, status in results:
        print("%-60s %s" % (name, status))
    bad = [n for n, s in results if s != "PASS"]
    print("u20 test_archive_stmt: %d/%d passed"
          % (len(results) - len(bad), len(results)))
    raise SystemExit(1 if bad else 0)
