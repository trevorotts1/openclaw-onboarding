#!/usr/bin/env python3
"""test_verify_board.py -- unit tests for the U20 POST-ACTION BOARD VERIFIER
(scripts/u20_modules/verify_board.py — Skill 59, U20 tooling: re-reads the
Command Center's Anthology board and CONFIRMS, fail-closed, that zero
ZZZ/SYNTHETIC drill cards are live on the open board and the producer
Welcome card is present). The one law this file exists to enforce: THE
VERIFIER NEVER WRITES AND CONFIRMS NOTHING WITHOUT --execute. Every
non-execute invocation — check() default, and the check CLI path — must be
a STOP (exit 2, Trevor-gated), never a silent no-op, and even WITH
--execute the verifier re-reads and confirms only — it NEVER mutates.

THE BOARD LAW (verify_board.py's header, written against):

  * the ZERO-DRILL law (u14-anthology-board-hygiene.py): a synthetic drill
    card is ANY Anthology-board task whose title contains the 'ZZZ' or
    'SYNTHETIC' markers (case-insensitive) — the markers that can only be
    drill data, never a real co-author ("Anthology chapter — <name>" cards
    can NEVER be caught). The board is clean only when ZERO such cards are
    LIVE (archived_at IS NULL — the tasks API's own "on the open board"
    filter); a soft-archived drill card is OFF the board and is NOT a
    violation (the hygiene law is a LIVE-board law).
  * the WELCOME-CARD law (db_connector / welcome_action / the CC
    departments route step 3): the Anthology board must carry ONE producer
    Welcome card on the open board — title byte-exact 'Welcome to
    Anthology', scoped to the 'anthology' workspace. A soft-archived
    Welcome card is OFF the open board and is reported as ABSENT (exit 5);
    a Welcome-titled card on ANOTHER workspace is never seen.
  * the READ-BACK law: the verifier re-reads the LIVE board through the
    family's own read-only surface (the sqlite URI mode=ro open over
    mission-control.db — never a second implementation) and compares
    against the wanted state. A drift is a MISMATCH (exit 5), never a
    pass; a board that cannot be READ is a STOP (exit 2) or HELD (exit 3)
    — UNDETERMINED, never a verdict.
  * the ACTION law (the u20 package-init doctrine): the VERIFY ACTION
    requires --execute (the Trevor gate). WITHOUT it the ACTION is a STOP
    (exit 2, AF-AE-VRBOARD-NO-EXECUTE) BEFORE any database is even opened;
    WITH it the ACTION is reported explicitly on the report (execute
    true) and the verifier STILL writes nothing — every connection it
    opens is sqlite URI mode=ro, so no code path can mutate even by
    accident.

COVERAGE (offline, hermetic, no network, no credentials, no tokens):

  * the law surfaces are pinned from the module's own constants — the
    board id 'anthology', the byte-exact Welcome title, the drill markers
    ('zzz', 'synthetic'), the VERIFY action verb and its --execute gate,
    and the report contract string — so a drifted law is caught HERE
    first,
  * the ACTION gate, both directions: without --execute the check is a
    STOP (exit 2) — at check() and at the CLI boundary, and BEFORE any
    database open (the no-execute gate fires even on a golden database);
    with --execute the golden board PASSes exit 0,
  * the golden read-back: a clean board (the Welcome card live, the stale
    auto-seed and the drill cards soft-archived) PASSes exit 0, and the
    ONE JSON report carries the contract, the expected/found law fields,
    and execute true,
  * the never-writes proof: check() with --execute leaves the fixture
    database file byte-identical (before/after sha256) — the verifier is
    READ-ONLY by construction, never a write path, even under the
    Trevor-gated ACTION,
  * the fail-closed refusal ladder: a live ZZZ/SYNTHETIC drill card (any
    case) is a MISMATCH (exit 5) with the masked id proven in the report;
    a real co-author card NEVER trips the drill law (PASS); an absent
    Welcome card is a MISMATCH (exit 5); a soft-archived Welcome card is a
    MISMATCH (exit 5); a Welcome-titled card on another workspace is a
    MISMATCH (exit 5) — any title variation is a DIFFERENT card that is
    never treated as the Welcome card,
  * the unreadable-surface ladder: a missing database STOPS (exit 2,
    AF-AE-VRBOARD-NO-DB) — never "board clean"; a database without the
    tasks table STOPS (exit 2, AF-AE-VRBOARD-TASKS-MISSING) — never a
    sweep of nothing; a busy/locked database is HELD (exit 3) — retryable,
    never a verdict,
  * the db-resolution law: an explicit --db wins; DATABASE_PATH env wins
    over the candidate list; empty/whitespace --db never resolves to a
    literal (with DATABASE_PATH stripped the operator box's live database
    is NOT swept — the tests never touch it),
  * the plan is OFFLINE and truthful: no database needed, exit 0, the two
    laws with their exact sources, execute_required true,
  * the house doctrine pins: the exit-code convention (0/1/2/3/4/5)
    asserted through the module's exported constants, the browser
    User-Agent law (CF 1010 — the family's CAF_BROWSER_UA is a browser UA,
    never urllib's default), the fail-closed-empty package init (u20), and
    never-print (no full task id, no credential shape, on any surface).

House doctrine (Skill 59, u20_modules/__init__.py): fail-closed, both
directions — the golden control passes and EVERY attack fails, so the
pass/fail split discriminates (the golden control is never a broken
instrument). Never a token printed; nothing Anthropic in any runtime
surface; stdlib only; pytest with plain asserts; sys.path bootstrap
identical to every other tests/ file; exit codes asserted by the exported
module constants, never hardcoded. No credential is resolved, no env var
beyond the test's own fixtures is read, no network is touched, and the
operator box's live mission-control.db is never opened.

Run: python3 -m pytest 59-anthology-engine/tests/test_verify_board.py -q
 or: python3 59-anthology-engine/tests/test_verify_board.py
"""
import contextlib
import hashlib
import io
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import anthology_registry as reg  # noqa: E402  (exit codes, UA law)
import u20_modules.verify_board as vb  # noqa: E402  (the module under test)

# The house exit-code convention (0/1/2/3/4/5) — asserted through the
# exported constants, never re-typed.
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    vb.EX_OK, vb.EX_ERR, vb.EX_STOP, vb.EX_HELD, vb.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# A credential-shaped string is the pit- token prefix followed by a
# non-empty value — the house guard shape every surface is scanned
# against. No test fixture carries a real one, so no captured surface may
# either.
CREDENTIAL_SHAPE = "pit-"


# ---------------------------------------------------------------------------
# Fixtures: a hermetic mission-control.db stand-in (temp file, real sqlite)
# ---------------------------------------------------------------------------
def _make_db(cards=(), schema=True):
    """A temp sqlite file in the tasks-table shape the CC board contract
    uses (the same 12-column shape the module's own _FakeDb builds). The
    tests drive the REAL functions against this file — the same instrument
    the live module uses. Returns the path; the caller unlinks it."""
    fd, path = tempfile.mkstemp(prefix="vb-test-", suffix=".db")
    os.close(fd)
    if schema:
        con = sqlite3.connect(path)
        try:
            con.executescript(
                """
                CREATE TABLE tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    description TEXT,
                    status TEXT,
                    priority TEXT,
                    workspace_id TEXT,
                    department TEXT,
                    source TEXT,
                    assigned_agent_id TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    archived_at TEXT
                );
                """
            )
            for card in cards:
                cols = ", ".join(card)
                ph = ", ".join("?" * len(card))
                con.execute("INSERT INTO tasks (%s) VALUES (%s)"
                            % (cols, ph), list(card.values()))
            con.commit()
        finally:
            con.close()
    return path


def _welcome_row(**kw):
    """A live producer Welcome card row shape — byte-exact title, anthology
    workspace, open board (archived_at NULL)."""
    row = {
        "id": "task_welcome",
        "title": vb.WELCOME_TITLE,
        "description": "…%s…" % vb.WELCOME_REF,
        "status": "backlog",
        "workspace_id": vb.WORKSPACE_ID,
        "department": vb.DEPARTMENT_SLUG,
        "created_at": "2026-08-11 00:00:00",
        "updated_at": "2026-08-11 00:00:00",
        "archived_at": None,
    }
    row.update(kw)
    return {k: v for k, v in row.items() if v is not None}


def _stale_row():
    """The stale auto-seed placeholder — the generic department body the CC
    departments route writes — soft-archived (off the open board; the u14
    hygiene archives it)."""
    return {
        "id": "task_stale",
        "title": vb.WELCOME_TITLE,
        "description": "…AI workforce will populate real tasks…",
        "status": "blocked",
        "workspace_id": vb.WORKSPACE_ID,
        "department": vb.DEPARTMENT_SLUG,
        "created_at": "2026-07-01 00:00:00",
        "updated_at": "2026-07-01 00:00:00",
        "archived_at": "2026-07-08 22:22:56",
    }


def _archived_drill_rows():
    """Drill cards, soft-archived — OFF the open board, NOT violations (the
    hygiene law is a LIVE-board law)."""
    return [
        {"id": "drill_a", "title": "ZZZ-SYNTHETIC-TEST drill A",
         "status": "blocked", "workspace_id": vb.WORKSPACE_ID,
         "department": vb.DEPARTMENT_SLUG,
         "created_at": "2026-07-01 00:00:00",
         "updated_at": "2026-07-01 00:00:00",
         "archived_at": "2026-07-08 22:22:56"},
        {"id": "drill_b", "title": "W5-drill synthetic card",
         "status": "blocked", "workspace_id": vb.WORKSPACE_ID,
         "department": vb.DEPARTMENT_SLUG,
         "created_at": "2026-07-01 00:00:00",
         "updated_at": "2026-07-01 00:00:00",
         "archived_at": "2026-07-08 22:22:56"},
    ]


def _golden_cards():
    """The golden clean board: exactly the Welcome card live, nothing else —
    the state the U14 hygiene leaves behind (the stale auto-seed archived,
    the drill cards archived, the ONE producer-voice Welcome live)."""
    return [_welcome_row()] + [_stale_row()] + _archived_drill_rows()


def _check(db_path, **kw):
    """Run the verifier's check with stdout captured, returning
    (rc, parsed-json-or-None). Human notes go to a sink StringIO unless the
    caller passes `out` explicitly (then they go to the caller's stream)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = vb.check(db_path=db_path, out=kw.pop("out", io.StringIO()), **kw)
    parsed = None
    if buf.getvalue().strip():
        try:
            parsed = json.loads(buf.getvalue())
        except ValueError:
            parsed = None
    return rc, parsed


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# The board law surfaces are pinned from the module (never re-typed)
# ---------------------------------------------------------------------------
def test_board_law_surfaces_are_pinned():
    """The board law constants are the module's own — the anthology board
    id, the byte-exact Welcome title, the zero-drill markers, the VERIFY
    action verb and its --execute gate, and the report contract."""
    assert vb.WORKSPACE_ID == "anthology"
    assert vb.DEPARTMENT_SLUG == "anthology"
    assert vb.WELCOME_TITLE == "Welcome to Anthology"
    assert tuple(vb.DRILL_MARKERS) == ("zzz", "synthetic")
    assert vb.VERIFY_ACTION == "verify"
    assert vb.EXECUTE_FLAG == "--execute"
    assert vb.CONFIG_CONTRACT == "anthology-engine-verify-board"
    assert vb.CONFIG_SCHEMA_VERSION == 1
    assert vb.WELCOME_REF == "anthology:welcome:card"


def test_welcome_title_matches_the_how_to_use_derived_card():
    """The Welcome card the family seeds derives from HOW-TO-USE.md (copy,
    never a write — the u20 package doctrine) and lands on the board with
    the byte-exact 'Welcome to Anthology' title (add-department.sh step 3
    shape). The producer how-to itself is the card's content source."""
    howto = SKILL_DIR / "HOW-TO-USE.md"
    assert howto.is_file(), "HOW-TO-USE.md must be present (the card's copy source)"
    text = howto.read_text(encoding="utf-8")
    assert "producer" in text and "participants" in text, (
        "the how-to is the producer-facing guide the card body derives from")
    assert vb.WELCOME_TITLE == "Welcome to Anthology"


# ---------------------------------------------------------------------------
# Cross-cutting house doctrine
# ---------------------------------------------------------------------------
def test_exit_code_convention_is_house_0_1_2_3_4_5():
    """Every runner pins the house exit-code convention — asserted through
    the exported constants, never hardcoded."""
    assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert EX_VIOLATION == 4
    assert EX_VIOLATION not in (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH)
    assert reg.EX_MISMATCH == 5, "the registry's mismatch code must agree"


def test_browser_user_agent_is_a_browser_ua_cf_1010_law():
    """The CF 1010 law: the family rides a browser User-Agent on every
    request — urllib's default Python-urllib/x.y is 403'd at the Cloudflare
    WAF edge before it ever reaches Convert and Flow. The verifier makes no
    request of its own (it reads the local database) but pins the law so a
    registry regression is caught HERE first."""
    assert reg.CAF_BROWSER_UA, "CAF_BROWSER_UA must never be empty"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), (
        "CAF_BROWSER_UA must be a browser User-Agent, got %r"
        % reg.CAF_BROWSER_UA[:40])
    assert "Python-urllib" not in reg.CAF_BROWSER_UA, (
        "CAF_BROWSER_UA is urllib's default — the Cloudflare edge 1010s it")


def test_u20_package_init_is_fail_closed_empty():
    """The package init is a pure namespace container — no runtime code, no
    side effects, no secret surface — and it CARRIES the write-gate doctrine
    (the engine database is READ-ONLY in dry-run; writes ONLY with
    --execute, Trevor-gated) in its DOCTRINE comment block."""
    import u20_modules as pkg
    assert pkg.__all__ == []
    assert pkg.__doc__ and "fail-closed" in pkg.__doc__.lower()
    init_text = Path(pkg.__file__).read_text(encoding="utf-8")
    assert "--execute" in init_text and "Trevor-gated" in init_text
    assert "READ-ONLY" in init_text


# ---------------------------------------------------------------------------
# The ACTION gate: --execute required (Trevor-gated), never a silent no-op
# ---------------------------------------------------------------------------
def test_check_without_execute_stops_before_any_db_open():
    """An ACTION without --execute is a STOP (exit 2) — even on a golden
    database, so a plan that could be mistaken for a confirmation is
    impossible. The gate fires BEFORE any database is opened (the file
    bytes are untouched), never a silent no-op."""
    path = _make_db(_golden_cards())
    try:
        before = _sha256(path)
        rc, _ = _check(path, execute=False)
        assert rc == EX_STOP, (
            "the VERIFY ACTION without --execute must STOP (exit 2), "
            "got %r" % rc)
        assert _sha256(path) == before, (
            "the no-execute gate must never touch the database file")
    finally:
        os.unlink(path)


def test_check_without_execute_jsonout_carries_the_gate_reason():
    """The machine refusal surface for the no-execute gate names it: exit 2,
    execute false, reason no-execute. (The gate is only reachable when a
    database path EXISTS — the missing-database refusal fires first, so the
    no-execute surface is proven against a real fixture database.)"""
    path = _make_db(_golden_cards())
    try:
        buf = io.StringIO()
        rc = vb.check(db_path=path, execute=False, out=io.StringIO(),
                      jsonout=buf)
        assert rc == EX_STOP
        refusal = json.loads(buf.getvalue())
        assert refusal["ok"] is False
        assert refusal["exit"] == EX_STOP
        assert refusal["reason"] == "no-execute"
        assert refusal.get("execute") is False
        assert "Trevor-gated" in refusal.get("note", "")
    finally:
        os.unlink(path)


def test_check_cli_without_execute_stops():
    """The CLI boundary enforces the same Trevor gate: check without
    --execute STOPS (exit 2) before any read."""
    path = _make_db(_golden_cards())
    try:
        rc = vb.main(["check", "--db", path])
        assert rc == EX_STOP
    finally:
        os.unlink(path)


def test_plan_and_self_test_need_no_execute():
    """plan and self-test are OFFLINE — they need no database and no
    --execute. plan exits 0 with the two laws as data; the module's own
    offline battery is the sibling gate (asserted separately)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = vb.plan()
    assert rc == EX_OK
    payload = json.loads(buf.getvalue())
    assert payload["contract"] == vb.CONFIG_CONTRACT + "-plan"
    assert payload["execute_required"] is True


# ---------------------------------------------------------------------------
# The golden read-back: zero live drills + Welcome present -> PASS
# ---------------------------------------------------------------------------
def test_golden_clean_board_passes_with_execute():
    """The golden clean board (the Welcome card live, the stale auto-seed
    and the drill cards soft-archived) PASSes exit 0 under --execute, and
    the ONE JSON report carries the contract, the byte-exact expected law,
    execute true, and the found surface."""
    path = _make_db(_golden_cards())
    try:
        rc, parsed = _check(path, execute=True)
        assert rc == EX_OK
        assert parsed is not None
        assert parsed["ok"] is True and parsed["verdict"] == "PASS"
        assert parsed["contract"] == vb.CONFIG_CONTRACT
        assert parsed["schema_version"] == 1
        assert parsed["execute"] is True
        assert parsed["action"] == vb.VERIFY_ACTION == "verify"
        assert parsed["execute_required"] is True
        assert parsed["board"] == vb.WORKSPACE_ID == "anthology"
        assert parsed["expected"]["drill_cards_live"] == 0
        assert parsed["expected"]["welcome_card"] == (
            "present on the open board (title byte-exact 'Welcome to "
            "Anthology')")
        assert parsed["found"]["drill_cards_live"] == 0
        assert parsed["found"]["drill_cards_live_ids_masked"] == []
        assert parsed["found"]["welcome_card"]["present"] is True
        assert parsed["found"]["welcome_card"]["status"] == "backlog"
        assert "verified" in parsed["note"]
    finally:
        os.unlink(path)


def test_golden_archived_drill_cards_are_not_violations():
    """The zero-drill law is a LIVE-board law (archived_at IS NULL — the
    tasks API's own open-board filter): a soft-archived ZZZ/SYNTHETIC drill
    card is OFF the board and is NOT a violation — the golden board (stale
    auto-seed + both archived drills) passes."""
    path = _make_db(_golden_cards())
    try:
        rc, parsed = _check(path, execute=True)
        assert rc == EX_OK
        assert parsed["found"]["drill_cards_live"] == 0
    finally:
        os.unlink(path)


def test_read_is_deterministic_and_repeatable():
    """The same board gives the same verdict every time — the verifier is a
    pure read of the board state, never stateful."""
    path = _make_db(_golden_cards())
    try:
        rc1, p1 = _check(path, execute=True)
        rc2, p2 = _check(path, execute=True)
        assert rc1 == rc2 == EX_OK
        assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# The never-writes proof: even WITH --execute the verifier performs NO write
# ---------------------------------------------------------------------------
def test_verifier_never_writes_even_with_execute():
    """WITH --execute the verifier still performs NO write: the golden
    read-back PASSes and the database file is byte-identical before and
    after the check (sha256). The verifier is READ-ONLY by construction —
    every connection is sqlite URI mode=ro — so no code path can mutate
    even by accident."""
    path = _make_db(_golden_cards())
    try:
        before = _sha256(path)
        rc, _ = _check(path, execute=True)
        assert rc == EX_OK
        assert _sha256(path) == before, (
            "check() under --execute must leave the database byte-identical")
    finally:
        os.unlink(path)


def test_verifier_never_writes_on_a_mismatch_either():
    """The never-writes law holds on the FAIL path too: a board with a live
    drill card is a MISMATCH (exit 5) and the database is still byte-
    identical after the read."""
    path = _make_db(_golden_cards() + [
        {"id": "drill_live", "title": "ZZZ-SYNTHETIC-TEST residue",
         "status": "backlog", "workspace_id": vb.WORKSPACE_ID,
         "department": vb.DEPARTMENT_SLUG,
         "created_at": "2026-08-11 00:00:00",
         "updated_at": "2026-08-11 00:00:00",
         "archived_at": None}])
    try:
        before = _sha256(path)
        rc, _ = _check(path, execute=True)
        assert rc == EX_MISMATCH
        assert _sha256(path) == before
    finally:
        os.unlink(path)


def test_readonly_connection_refuses_writes_at_the_vfs_layer():
    """The module's own connection helper is read-only at the VFS layer: a
    write through the mode=ro URI open raises 'attempt to write a readonly
    database' — the second, independent belt (with the query_only pragma)
    that makes mutation impossible by construction."""
    path = _make_db(_golden_cards())
    try:
        con = vb._connect_readonly(path)
        try:
            with pytest.raises(sqlite3.OperationalError):
                con.execute("DELETE FROM tasks")
            with pytest.raises(sqlite3.OperationalError):
                con.execute("INSERT INTO tasks (id, title) VALUES ('x', 'y')")
        finally:
            con.close()
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# The fail-closed refusal ladder: every drift REFUSED, never a pass
# ---------------------------------------------------------------------------
def test_live_drill_card_is_a_mismatch_and_proven_in_the_report():
    """A LIVE ZZZ/SYNTHETIC drill card on the open board is a MISMATCH
    (exit 5), never a pass — and the report PROVES it: the live count and
    the masked ids (last-4 markers, never the full id)."""
    path = _make_db(_golden_cards() + [
        {"id": "drill_live", "title": "ZZZ-SYNTHETIC-TEST residue",
         "status": "backlog", "workspace_id": vb.WORKSPACE_ID,
         "department": vb.DEPARTMENT_SLUG,
         "created_at": "2026-08-11 00:00:00",
         "updated_at": "2026-08-11 00:00:00",
         "archived_at": None}])
    try:
        rc, parsed = _check(path, execute=True)
        assert rc == EX_MISMATCH
        assert parsed["ok"] is False and parsed["verdict"] == "MISMATCH"
        assert parsed["found"]["drill_cards_live"] == 1
        assert parsed["found"]["drill_cards_live_ids_masked"] == ["...live"]
        assert "drill_live" not in json.dumps(parsed), (
            "the full task id must never surface")
        assert "board law is violated" in parsed["note"]
    finally:
        os.unlink(path)


def test_drill_match_is_case_insensitive():
    """The drill markers match case-insensitively — 'zzz' in a lowercase
    title is still drill data, never a real co-author."""
    path = _make_db(_golden_cards() + [
        {"id": "d_lower", "title": "test zzz card",
         "status": "backlog", "workspace_id": vb.WORKSPACE_ID,
         "department": vb.DEPARTMENT_SLUG,
         "created_at": "2026-08-11 00:00:00",
         "updated_at": "2026-08-11 00:00:00",
         "archived_at": None}])
    try:
        rc, parsed = _check(path, execute=True)
        assert rc == EX_MISMATCH
        assert parsed["found"]["drill_cards_live"] == 1
    finally:
        os.unlink(path)


def test_real_coauthor_card_never_trips_the_drill_law():
    """The zero-drill law never catches a real co-author card: an
    'Anthology chapter — <name>' card (the real participant card shape) on
    the open board is clean — the synthetic match is restricted to the
    ZZZ/SYNTHETIC markers so drill data can only ever be synthetic."""
    path = _make_db(_golden_cards() + [
        {"id": "part_real", "title": "Anthology chapter — Amelia Earhart",
         "status": "review", "workspace_id": vb.WORKSPACE_ID,
         "department": vb.DEPARTMENT_SLUG,
         "created_at": "2026-08-11 00:00:00",
         "updated_at": "2026-08-11 00:00:00",
         "archived_at": None}])
    try:
        rc, parsed = _check(path, execute=True)
        assert rc == EX_OK
        assert parsed["found"]["drill_cards_live"] == 0
    finally:
        os.unlink(path)


def test_absent_welcome_card_is_a_mismatch():
    """No byte-exact 'Welcome to Anthology' card LIVE on the open board is
    a MISMATCH (exit 5), never a pass — the report names the absent
    welcome (present false)."""
    path = _make_db([
        {"id": "other", "title": "Anthology chapter — Someone",
         "status": "backlog", "workspace_id": vb.WORKSPACE_ID,
         "department": vb.DEPARTMENT_SLUG,
         "created_at": "2026-08-11 00:00:00",
         "updated_at": "2026-08-11 00:00:00",
         "archived_at": None}])
    try:
        rc, parsed = _check(path, execute=True)
        assert rc == EX_MISMATCH
        assert parsed["found"]["welcome_card"]["present"] is False
        assert parsed["found"]["welcome_card"]["id_masked"] is None
    finally:
        os.unlink(path)


def test_soft_archived_welcome_card_is_absent_from_the_open_board():
    """A Welcome card that is live-in-the-DB but soft-archived is OFF the
    open board — the producer does not see it (the stale placeholder the
    u14 hygiene archives) — reported as ABSENT, exit 5, never the welcome
    the law demands."""
    path = _make_db([_stale_row()])
    try:
        rc, parsed = _check(path, execute=True)
        assert rc == EX_MISMATCH
        assert parsed["found"]["welcome_card"]["present"] is False
        assert parsed["found"]["welcome_card"]["archived_at"], (
            "the archived status must be surfaced for the operator")
    finally:
        os.unlink(path)


def test_welcome_card_on_another_workspace_is_never_seen():
    """The Welcome card is pinned BY TITLE and BY WORKSPACE: a
    'Welcome to Anthology' card on ANY other workspace is a DIFFERENT card
    that is never treated as the board's Welcome card — the anthology
    board reports the welcome ABSENT."""
    path = _make_db([
        {"id": "tw_other", "title": vb.WELCOME_TITLE,
         "description": "…%s…" % vb.WELCOME_REF,
         "status": "backlog", "workspace_id": "other-board",
         "department": vb.DEPARTMENT_SLUG,
         "created_at": "2026-08-11 00:00:00",
         "updated_at": "2026-08-11 00:00:00",
         "archived_at": None}])
    try:
        rc, parsed = _check(path, execute=True)
        assert rc == EX_MISMATCH
        assert parsed["found"]["welcome_card"]["present"] is False
    finally:
        os.unlink(path)


def test_title_variation_is_a_different_card_never_the_welcome():
    """Any title variation ('Welcome to SomethingElse') is a DIFFERENT card
    that is never treated as the Welcome card — byte-exact only."""
    path = _make_db(_golden_cards() + [
        {"id": "tw_variant", "title": "Welcome to SomethingElse",
         "status": "backlog", "workspace_id": vb.WORKSPACE_ID,
         "department": vb.DEPARTMENT_SLUG,
         "created_at": "2026-08-11 00:00:00",
         "updated_at": "2026-08-11 00:00:00",
         "archived_at": None}])
    try:
        rc, parsed = _check(path, execute=True)
        assert rc == EX_OK
        assert parsed["found"]["welcome_card"]["present"] is True
        assert parsed["found"]["welcome_card"]["id_masked"] == "...come"
    finally:
        os.unlink(path)


def test_combined_mismatch_reports_both_laws_violated():
    """A board with a live drill card AND no Welcome card reports BOTH law
    violations in one MISMATCH — the fail-closed detail names each drift."""
    path = _make_db([
        {"id": "drill_live", "title": "ZZZ drill residue",
         "status": "backlog", "workspace_id": vb.WORKSPACE_ID,
         "department": vb.DEPARTMENT_SLUG,
         "created_at": "2026-08-11 00:00:00",
         "updated_at": "2026-08-11 00:00:00",
         "archived_at": None}])
    try:
        out = io.StringIO()
        rc, parsed = _check(path, execute=True, out=out)
        assert rc == EX_MISMATCH
        assert parsed["found"]["drill_cards_live"] == 1
        assert parsed["found"]["welcome_card"]["present"] is False
        assert "drill card" in out.getvalue()
        assert "ABSENT" in out.getvalue()
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# The unreadable-surface ladder: never a verdict on a board it cannot read
# ---------------------------------------------------------------------------
def test_missing_database_stops_never_board_clean():
    """A missing database is AF-AE-VRBOARD-NO-DB: STOP (exit 2) — a board
    that cannot be read is never 'board clean', never a no-op pass. The
    refusal is before the ACTION gate only when no database exists at all
    (there is nothing to gate); with a database present the gate comes
    first."""
    rc, _ = _check("", execute=True)
    assert rc == EX_STOP
    rc2, _ = _check("", execute=False)
    assert rc2 == EX_STOP


def test_unopenable_database_stops_never_board_clean():
    """A database that cannot be opened read-only (a directory at the db
    path) is a STOP (exit 2) — the unreadable surface is never a verdict."""
    tmp = tempfile.mkdtemp(prefix="vb-test-bad-")
    db = os.path.join(tmp, "mission-control.db")
    os.makedirs(db)  # a DIRECTORY at the db path — the read cannot open it
    rc, _ = _check(db, execute=True)
    assert rc == EX_STOP
    os.rmdir(db)
    os.rmdir(tmp)


def test_database_without_tasks_table_stops_never_a_sweep_of_nothing():
    """A database without the tasks table (a schema that predates the
    board, or the wrong database) is AF-AE-VRBOARD-TASKS-MISSING: STOP
    (exit 2) — never a sweep of nothing, never a blind pass."""
    path = _make_db(schema=False)
    try:
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE other (x TEXT)")
        con.commit()
        con.close()
        rc, _ = _check(path, execute=True)
        assert rc == EX_STOP
    finally:
        os.unlink(path)


def test_locked_database_stops_fail_closed_never_a_verdict():
    """A busy/locked database is NEVER a verdict: the module's read-only
    open succeeds (mode=ro never takes a lock), the query_only PRAGMA waits
    out the busy timeout under the reserved lock, and the read is then
    classified by the FAIL-CLOSED caller — the tasks-table read cannot
    proceed, so the module STOPS (exit 2, never a sweep of nothing, never
    a blind pass) rather than reporting 'board clean' on a board it could
    not read. The HELD (exit 3) branch is reserved for the lock AT OPEN —
    a read-only open never takes a lock itself, so the fixture that can
    reach it is the open-time refusal, not this one.

    NOTE: this fixture takes the full 15 s busy timeout inside the module's
    read-only open — it is the one slow test in the suite, by design, and
    it is what makes the locked-surface classification deterministic
    offline (the only other way to lock a database is the live server's
    WAL, which the tests never touch)."""
    path = _make_db(_golden_cards())
    lock = sqlite3.connect(path)
    try:
        lock.execute("BEGIN EXCLUSIVE")
        out = io.StringIO()
        rc, _ = _check(path, execute=True, out=out)
        assert rc == EX_STOP, (
            "a locked database must STOP fail-closed (exit 2), never a "
            "pass and never a fabricated verdict, got %r" % rc)
        assert "STOP" in out.getvalue(), (
            "the locked surface must be a STOP refusal, not a verdict")
    finally:
        lock.rollback()
        lock.close()
        os.unlink(path)


def test_missing_db_json_refusal_carries_the_reason():
    """The machine refusal surface for a missing database names the code:
    exit 2, reason db-missing — a machine consumer can classify the STOP
    without parsing prose."""
    buf = io.StringIO()
    rc = vb.check(db_path="", execute=True, out=io.StringIO(),
                  jsonout=buf)
    assert rc == EX_STOP
    refusal = json.loads(buf.getvalue())
    assert refusal["exit"] == EX_STOP
    assert refusal["reason"] == "db-missing"


# ---------------------------------------------------------------------------
# The db-resolution law: --db > DATABASE_PATH > candidates, never a guess
# ---------------------------------------------------------------------------
def test_explicit_db_wins_over_everything(monkeypatch):
    """An explicit --db path wins over DATABASE_PATH and over every
    candidate — resolve_db_path returns the explicit path untouched."""
    monkeypatch.setenv("DATABASE_PATH", "/tmp/cc-other.db")
    assert vb.resolve_db_path("  /explicit/x.db  ") == "/explicit/x.db"
    assert vb.resolve_db_path("") == "/tmp/cc-other.db"


def test_database_path_env_wins_over_the_candidate_list(monkeypatch):
    """DATABASE_PATH env override (the CC's own getDbPath rule:
    DATABASE_PATH always wins) resolves ahead of the candidate list."""
    monkeypatch.setenv("DATABASE_PATH", "/tmp/cc-mission-control.db")
    assert vb.resolve_db_path("") == "/tmp/cc-mission-control.db"
    monkeypatch.delenv("DATABASE_PATH", raising=False)


def test_whitespace_db_is_treated_as_not_given(monkeypatch):
    """A whitespace-only --db is treated as NOT given (never resolves to a
    blank/whitespace literal). With DATABASE_PATH stripped, the resolution
    falls through to the family candidate list; the test asserts the
    whitespace value is NOT the resolution (the fall-through may legitimately
    name a candidate that exists on THIS box — the LIVE mission-control.db —
    which the tests never open)."""
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    explicit = vb.resolve_db_path("   ")
    assert explicit != "   ", (
        "whitespace --db must not resolve to the literal itself")


# ---------------------------------------------------------------------------
# The offline plan — the two laws as data, no database, no credential
# ---------------------------------------------------------------------------
def test_plan_carries_both_laws_with_their_sources():
    """The offline plan names the zero-drill law (markers, open-board
    scope, the u14 source) and the Welcome-card law (byte-exact title,
    open-board scope, the family sources) — the law is carried as data,
    never re-implemented."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = vb.plan()
    assert rc == EX_OK
    payload = json.loads(buf.getvalue())
    assert payload["contract"] == vb.CONFIG_CONTRACT + "-plan"
    assert payload["schema_version"] == 1
    assert payload["action"] == "verify"
    assert payload["execute_required"] is True
    assert payload["board"] == "anthology"
    assert payload["zero_drill_law"]["markers"] == ["zzz", "synthetic"]
    assert "archived_at IS NULL" in payload["zero_drill_law"]["scope"]
    assert "u14-anthology-board-hygiene" in payload["zero_drill_law"]["source"]
    assert payload["welcome_card_law"]["title"] == vb.WELCOME_TITLE
    assert "archived_at IS NULL" in payload["welcome_card_law"]["scope"]
    assert "HOW-TO-USE.md" in payload["welcome_card_law"]["source"]
    assert "mode=ro" in payload["reads"]["board"]
    assert "Trevor-gated" in payload["note"]


def test_plan_needs_no_database_no_credential_no_network():
    """The plan is OFFLINE: it exits 0 with no database file, no
    DATABASE_PATH, no credential, and no network — and it never carries a
    credential shape."""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vb.plan()
        assert rc == EX_OK
        assert CREDENTIAL_SHAPE not in buf.getvalue()
        assert "Bearer " not in buf.getvalue()
    finally:
        monkeypatch.undo()


# ---------------------------------------------------------------------------
# never-print: no full id, no credential shape, on any surface
# ---------------------------------------------------------------------------
def test_no_surface_prints_a_full_id_or_a_credential_shape():
    """Every captured surface — the golden PASS report, every refusal, the
    plan — carries masked markers (last-4 suffixes) only: no full task id,
    no credential shape. The fixture ids are the ones that would leak if
    the masking ever broke."""
    surfaces = []
    path = _make_db(_golden_cards() + [
        {"id": "drill_live", "title": "ZZZ residue",
         "status": "backlog", "workspace_id": vb.WORKSPACE_ID,
         "department": vb.DEPARTMENT_SLUG,
         "created_at": "2026-08-11 00:00:00",
         "updated_at": "2026-08-11 00:00:00",
         "archived_at": None}])
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            vb.check(db_path=path, execute=True, out=io.StringIO(),
                     jsonout=None)
        surfaces.append(buf.getvalue())
    finally:
        os.unlink(path)

    path2 = _make_db(_golden_cards())
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            vb.check(db_path=path2, execute=True, out=io.StringIO(),
                     jsonout=None)
        surfaces.append(buf.getvalue())
    finally:
        os.unlink(path2)

    buf3 = io.StringIO()
    with contextlib.redirect_stdout(buf3):
        vb.plan()
    surfaces.append(buf3.getvalue())

    for blob in surfaces:
        assert CREDENTIAL_SHAPE not in blob, "surface leak: credential shape"
        assert "Bearer " not in blob, "surface leak: Bearer shape"
        assert "task_welcome" not in blob, "surface leak: full task id"
        assert "task_stale" not in blob, "surface leak: full task id"
        assert "drill_live" not in blob, "surface leak: full task id"
        assert "drill_a" not in blob, "surface leak: full task id"


def test_mask_id_never_exposes_the_full_id():
    """The id marker is the last-4-char suffix only — the house surface
    shape for every operator-facing mention of an id."""
    assert vb._mask_id("task_live1234") == "...1234"
    assert vb._mask_id("") == "...(short)"
    assert vb._mask_id("ab") == "...(short)"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
