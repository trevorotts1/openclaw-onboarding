#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u06_modules/test_verify_archived.py
# UNIT TESTS for the ARCHIVED-STATE VERIFIER (scripts/u06_modules/
# verify_archived.py — U06 tooling: re-reads the engine's TWO archive
# targets — the board footprint and the ledger rows, the revoke flow's R2 /
# R6 pair — after a revocation and CONFIRMS the archived status held,
# fail-closed). The one law this file exists to enforce: THE VERIFIER NEVER
# WRITES AND CONFIRMS NOTHING WITHOUT --execute. Every non-execute
# invocation — check() default, and the check CLI path — must be a STOP
# (exit 2, Trevor-gated), never a silent no-op, and even WITH --execute the
# verifier re-reads and confirms only — it NEVER mutates.
#
# THE READ-BACK LAW (verify_archived.py's header, written against):
#   * the LEDGER target — the anthology's status rows, archived by
#     anthology_state.py upsert-anthology --status archived
#     (deactivate-never-delete, ninety-day retention); the verifier re-reads
#     through the SOLE WRITER's own read-only surface and confirms the
#     anthology's status is byte-exact 'archived',
#   * the BOARD footprint — the Assembly card + every participant card
#     (keyed by participant_key, the KEYING LAW contact_id::anthology_id,
#     read once from anthology_state.participant_key), archived by
#     mc_board.py cmd_archive to 'blocked' (the board's archive status — the
#     signed-status route has no 'archived' primitive); the board card is
#     read back through the board client's own fail-soft status projection
#     (mc_board._read_subject + _target_status — the exact surface the
#     board client's cmd_status uses) and must carry EXACTLY the board's
#     archive status, never 'done',
#   * a drift — a ledger row still active, a board card not at the board's
#     archive status, a card the sweep should have moved cannot be found, a
#     credential-shaped value on any surface — is a MISMATCH (exit 5),
#     never a pass, never a fabricated success,
#   * a target that cannot be READ (the mirror unavailable, the
#     sole-writer surface failing) is HELD (exit 3) — UNDETERMINED, never a
#     verdict.
#
# COVERAGE (offline, hermetic, no network, no credentials, no tokens):
#   * the ACTION gate, both directions: without --execute the check is a
#     STOP (exit 2) — at the CLI boundary and at check() — never a silent
#     no-op; with --execute the verifier still writes NOTHING (the golden
#     journal PASSes and no surface mutates),
#   * the golden read-back: a journal with BOTH targets archived byte-exact
#     (ledger 'archived'; the Assembly card and every participant card at
#     the board's 'blocked') PASSes exit 0,
#   * the fail-closed refusal ladder: a ledger status not archived, an
#     Assembly card not at the board's archive status, a participant card
#     not at the board's archive status, a card the sweep should have moved
#     (unknown card) — each MISMATCH (exit 5); a board card at 'done' (the
#     status this client is FORBIDDEN to touch) STOPS (exit 2); an empty
#     anthology id REFUSES (exit 5, never a sweep); a credential-shaped
#     read value REFUSES (exit 5, never echoed),
#   * the LIVE mirror read (the engine's own local mirror): an archived
#     anthology row + a participant at a held / exception cursor (which the
#     board projection maps to 'blocked') PASSes — proving the projection
#     seam (mc_board._target_status) is the read-back, never a raw cursor
#     compare; an archived ledger with an ACTIVE participant is a MISMATCH;
#     an unknown anthology id on a real mirror is a MISMATCH (the sweep
#     should have moved it — a vanished card is not proof of archived); an
#     unreadable mirror db is HELD (exit 3), never a verdict,
#   * the never-a-token law: no surface carries a credential shape or a
#     full id (markers are last-4-char suffixes only),
#   * the house doctrine pins: the exit-code convention (0/1/2/3/4/5)
#     asserted through the registry's exported constants, the browser
#     User-Agent law (CF 1010 — CAF_BROWSER_UA is a browser UA, never
#     optional), the fail-closed-empty package init, the sibling U06
#     batteries green (verify_archived's own self-test, golden_absent's
#     self-test, attack_no_execute's self-test — a red sibling is caught
#     HERE first), and determinism (the same journal gives the same verdict
#     every time; the golden journal never mutates through the read).
#
# House doctrine (Skill 59, u06_modules/__init__.py): fail-closed, both
# directions — the golden control passes and EVERY attack fails, so the
# pass/fail split discriminates (the golden control is never a broken
# instrument). Never a token printed; nothing Anthropic in any runtime
# surface; stdlib only; pytest with plain asserts; sys.path bootstrap
# identical to every other tests/ file; exit codes asserted by the exported
# module constants, never hardcoded. The registry's CafClient and the rail
# clients are NEVER constructed here, no env var is read, no network is
# touched.
#
# Run: python3 -m pytest 59-anthology-engine/scripts/u06_modules/test_verify_archived.py -q
#  or: python3 59-anthology-engine/scripts/u06_modules/test_verify_archived.py
# =============================================================================
"""test_verify_archived.py -- the archived-state verifier's read-back law,
Trevor-gated ACTION, and never-a-token guards (U06)."""

import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import anthology_registry as reg  # noqa: E402
import anthology_state as state  # noqa: E402  (the KEYING LAW + vocabulary)
import mc_board as board  # noqa: E402  (the board archive status + projection)
import u06_modules.verify_archived as va  # noqa: E402  (the module under test)

# The house exit-code convention (0/1/2/3/4/5) — asserted through the
# exported constants, never re-typed.
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The two archive targets, read once from the module's single authority.
BOARD, LEDGER = va.ARCHIVE_TARGETS  # ("board", "ledger"), in order

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value — the house guard shape every u06 surface is scanned against. No test
# fixture carries a real one, so no captured surface may either.
CREDENTIAL_SHAPE = "pit-"

# The golden archived-state journal: the ledger status byte-exact 'archived'
# and the board surface at the board's archive status on the Assembly card
# AND every participant card (the census the archive sweep leaves behind).
def _golden_journal():
    return {
        "ledger_status": va.LEDGER_ARCHIVED_STATUS,
        "board_surface": {
            "assembly": va.BOARD_ARCHIVED_STATUS,
            "participants": [
                {"participant_key_masked": "....d01",
                 "status": va.BOARD_ARCHIVED_STATUS},
            ],
        },
    }


def _check(anthology_id, **kw):
    """Run the verifier's check with stdout captured, returning (rc, json)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = va.check(anthology_id, out=io.StringIO(), **kw)
    parsed = None
    if buf.getvalue().strip():
        try:
            parsed = json.loads(buf.getvalue())
        except ValueError:
            parsed = None
    return rc, parsed


def _make_mirror(rows_sql):
    """A temp engine mirror (anthology_state.db) seeded with the given SQL
    script. Returns the state-dir path."""
    tmp = tempfile.mkdtemp(prefix="u06-verify-test-")
    db = os.path.join(tmp, "anthology_state.db")
    con = sqlite3.connect(db)
    con.executescript(rows_sql)
    con.commit()
    con.close()
    return tmp


def _seed_schema():
    """The minimal mirror schema the verifier reads (the ledger table + the
    participants table, the same shape the sole writer ships)."""
    return """
    CREATE TABLE anthologies (anthology_id TEXT PRIMARY KEY, status TEXT,
                              assembly_state TEXT);
    CREATE TABLE participants (participant_key TEXT PRIMARY KEY,
                               anthology_id TEXT, stage_cursor TEXT);
    """


# ---------------------------------------------------------------------------
# Cross-cutting house doctrine
# ---------------------------------------------------------------------------
def test_verifier_self_test_passes_offline():
    """The module's own offline battery passes — exit 0, no network, no
    credential (golden archived state plus every drift fixture refused)."""
    assert va.self_test(out=io.StringIO()) == EX_OK


def test_exit_code_convention_is_house_0_1_2_3_4_5():
    """Every runner pins the house exit-code convention — asserted through
    the exported constants, never hardcoded."""
    assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert EX_VIOLATION == 4
    assert EX_VIOLATION not in (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH)


def test_browser_user_agent_is_a_browser_ua_cf_1010_law():
    """The CF 1010 law: the house client rides a browser User-Agent on every
    request — urllib's default Python-urllib/x.y is 403'd at the Cloudflare
    WAF edge before it ever reaches Convert and Flow. The law is a house
    constant, never optional."""
    assert reg.CAF_BROWSER_UA, "CAF_BROWSER_UA must never be empty"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), (
        "CAF_BROWSER_UA must be a browser User-Agent, got %r"
        % reg.CAF_BROWSER_UA[:40])


def test_u06_package_init_is_fail_closed_empty():
    """The package init is a pure namespace container — no runtime code, no
    side effects, no secret surface, and it CARRIES the archive-ACTION gate
    doctrine (--execute, Trevor-gated) in its DOCTRINE comment block."""
    import u06_modules as pkg
    assert pkg.__all__ == []
    assert pkg.__doc__ and "fail-closed" in pkg.__doc__.lower()
    init_text = Path(pkg.__file__).read_text(encoding="utf-8")
    assert "--execute" in init_text and "Trevor-gated" in init_text
    assert "archive ACTION" in init_text


# ---------------------------------------------------------------------------
# The golden read-back: both targets archived byte-exact -> PASS.
# ---------------------------------------------------------------------------
def test_golden_read_back_passes_with_both_targets_archived():
    """The golden archived-state journal (ledger 'archived'; Assembly card
    and every participant card at the board's 'blocked') PASSes exit 0, and
    the ONE JSON report carries the contract, the byte-exact wanted
    statuses, and execute true."""
    rc, parsed = _check("anth_golden", journal=_golden_journal(),
                        execute=True)
    assert rc == EX_OK
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["contract"] == va.CONFIG_CONTRACT
    assert parsed["expected"]["ledger_status"] == "archived"
    assert parsed["expected"]["board_status"] == "blocked"
    assert parsed["execute"] is True
    assert parsed["found"]["ledger_status"] == "archived"
    assert parsed["found"]["board"]["assembly_status"] == "blocked"
    assert parsed["found"]["board"]["participant_cards"] == 1


def test_read_back_is_deterministic_and_never_mutates_its_inputs():
    """The same journal gives the same verdict every time, and the journal
    handed in is never mutated through the read (the verifier is READ-ONLY)."""
    journal = _golden_journal()
    before = json.dumps(journal, sort_keys=True)
    rc1, _ = _check("anth_golden", journal=journal, execute=True)
    rc2, _ = _check("anth_golden", journal=journal, execute=True)
    assert rc1 == rc2 == EX_OK
    assert json.dumps(journal, sort_keys=True) == before


# ---------------------------------------------------------------------------
# The ACTION gate: --execute required (Trevor-gated), never a silent no-op.
# ---------------------------------------------------------------------------
def test_check_without_execute_stops_at_the_action_boundary():
    """An ACTION without --execute is a STOP (exit 2) — even on the golden
    journal, so a plan that could be mistaken for a confirmation is
    impossible. Never a silent no-op, never a mutation."""
    rc, _ = _check("anth_golden", journal=_golden_journal(), execute=False)
    assert rc == EX_STOP


def test_check_cli_without_execute_stops():
    """The CLI boundary enforces the same Trevor gate: check without
    --execute STOPS (exit 2) before any read."""
    rc = va.main(["check", "--anthology-id", "anth_golden"])
    assert rc == EX_STOP


def test_verifier_never_writes_even_with_execute():
    """WITH --execute the verifier still performs NO write: the golden
    read-back PASSes and the journal (the only thing it could touch) is
    byte-identical after the check."""
    journal = _golden_journal()
    before = json.dumps(journal, sort_keys=True)
    rc, _ = _check("anth_golden", journal=journal, execute=True)
    assert rc == EX_OK
    assert json.dumps(journal, sort_keys=True) == before


# ---------------------------------------------------------------------------
# The fail-closed refusal ladder: every deviation REFUSED.
# ---------------------------------------------------------------------------
def test_ledger_status_not_archived_is_a_mismatch():
    """A ledger row still active is a MISMATCH (exit 5), never a pass."""
    rc, parsed = _check("anth_golden", journal={
        "ledger_status": "active",
        "board_surface": _golden_journal()["board_surface"]},
        execute=True)
    assert rc == EX_MISMATCH
    assert parsed["verdict"] == "MISMATCH"


def test_assembly_card_not_at_board_archive_status_is_a_mismatch():
    """An Assembly card not at the board's archive status is a MISMATCH."""
    rc, _ = _check("anth_golden", journal={
        "ledger_status": va.LEDGER_ARCHIVED_STATUS,
        "board_surface": {"assembly": "in_progress", "participants": []}},
        execute=True)
    assert rc == EX_MISMATCH


def test_participant_card_not_at_board_archive_status_is_a_mismatch():
    """A participant card not at the board's archive status is a MISMATCH."""
    rc, _ = _check("anth_golden", journal={
        "ledger_status": va.LEDGER_ARCHIVED_STATUS,
        "board_surface": {"assembly": va.BOARD_ARCHIVED_STATUS,
                          "participants": [
                              {"participant_key_masked": "....d01",
                               "status": "review"}]}},
        execute=True)
    assert rc == EX_MISMATCH


def test_unknown_card_is_a_mismatch_never_proof_of_archived():
    """A card the sweep should have moved (unknown — empty status) is a
    MISMATCH: a vanished card is not proof of archived."""
    rc, _ = _check("anth_golden", journal={
        "ledger_status": va.LEDGER_ARCHIVED_STATUS,
        "board_surface": {"assembly": "", "participants": []}},
        execute=True)
    assert rc == EX_MISMATCH


def test_done_card_stops_never_a_pass():
    """A board card at 'done' — the one status this client is FORBIDDEN to
    touch — STOPS (exit 2), never a MISMATCH and never a pass."""
    rc, _ = _check("anth_golden", journal={
        "ledger_status": va.LEDGER_ARCHIVED_STATUS,
        "board_surface": {"assembly": board.DONE_STATUS, "participants": []}},
        execute=True)
    assert rc == EX_STOP


def test_empty_anthology_id_refuses_never_a_sweep():
    """An empty anthology id REFUSES (exit 5) — the target of the read-back
    is required, never a sweep."""
    rc, _ = _check("", journal=_golden_journal(), execute=True)
    assert rc == EX_MISMATCH


def test_credential_shaped_read_value_refuses_never_echoed():
    """A credential-shaped value on the read REFUSES (exit 5) — never
    echoed, never judged a status."""
    rc, _ = _check("anth_golden", journal={
        "ledger_status": "pit-abc123",
        "board_surface": _golden_journal()["board_surface"]},
        execute=True)
    assert rc == EX_MISMATCH


# ---------------------------------------------------------------------------
# The LIVE mirror read (the engine's own local mirror): the projection seam.
# ---------------------------------------------------------------------------
def test_live_mirror_archived_ledger_and_held_participant_passes():
    """The live read against a real mirror: an archived anthology row and a
    participant at a held cursor (which the board's own projection maps to
    'blocked') PASS — proving the read-back rides the board client's
    projection (mc_board._target_status), never a raw cursor compare."""
    state_dir = _make_mirror(_seed_schema() + """
        INSERT INTO anthologies (anthology_id, status, assembly_state)
        VALUES ('anth_live1', 'archived', 'not_ready');
        INSERT INTO participants (participant_key, anthology_id, stage_cursor)
        VALUES ('cnt_a::anth_live1', 'anth_live1', 'held');
        """)
    rc, parsed = _check("anth_live1", state_dir=state_dir, execute=True)
    assert rc == EX_OK
    assert parsed["found"]["board"]["assembly_status"] == "blocked"
    assert parsed["found"]["board"]["participant_cards"] == 1


def test_live_mirror_archived_ledger_with_active_participant_is_a_mismatch():
    """An archived ledger with an ACTIVE participant is a MISMATCH — the
    participant card was not archived."""
    state_dir = _make_mirror(_seed_schema() + """
        INSERT INTO anthologies (anthology_id, status, assembly_state)
        VALUES ('anth_live2', 'archived', 'not_ready');
        INSERT INTO participants (participant_key, anthology_id, stage_cursor)
        VALUES ('cnt_b::anth_live2', 'anth_live2', 's5_chapter');
        """)
    rc, _ = _check("anth_live2", state_dir=state_dir, execute=True)
    assert rc == EX_MISMATCH


def test_live_mirror_unknown_anthology_is_a_mismatch():
    """An anthology id absent from a real mirror is a MISMATCH — the sweep
    should have moved its card; a vanished card is not proof of archived."""
    state_dir = _make_mirror(_seed_schema())
    rc, _ = _check("anth_ghost", state_dir=state_dir, execute=True)
    assert rc == EX_MISMATCH


def test_live_mirror_unreadable_db_is_held_never_a_verdict():
    """A mirror db that cannot be read (a directory where the db file should
    be) is HELD (exit 3) — UNDETERMINED, never a verdict and never a pass."""
    tmp = tempfile.mkdtemp(prefix="u06-verify-bad-")
    db = os.path.join(tmp, "anthology_state.db")
    os.makedirs(db)  # a DIRECTORY at the db path — the read cannot open it
    rc, _ = _check("anth_live1", state_dir=tmp, execute=True)
    assert rc == EX_HELD


def test_board_status_maps_through_the_board_clients_projection():
    """The verifier's board read rides the board client's OWN projection:
    a participant at a held / exception cursor reads the board's 'blocked'
    status (the board archive status), and an archived anthology's Assembly
    card reads 'blocked' from the archived ledger row (the ledger is the
    truth — the CC card was moved by cmd_archive, fail-soft per SPEC 11.2)."""
    assert board._target_status("participant", {"stage_cursor": "held"}) == \
        va.BOARD_ARCHIVED_STATUS
    assert board._target_status("participant",
                                {"stage_cursor": "exception"}) == \
        va.BOARD_ARCHIVED_STATUS
    state_dir = _make_mirror(_seed_schema() + """
        INSERT INTO anthologies (anthology_id, status, assembly_state)
        VALUES ('anth_live3', 'archived', 'not_ready');
        INSERT INTO participants (participant_key, anthology_id, stage_cursor)
        VALUES ('cnt_c::anth_live3', 'anth_live3', 'exception');
        """)
    rc, parsed = _check("anth_live3", state_dir=state_dir, execute=True)
    assert rc == EX_OK
    assert parsed["found"]["board"]["assembly_status"] == "blocked"


# ---------------------------------------------------------------------------
# The archive LAW authorities are coherent (never a split law).
# ---------------------------------------------------------------------------
def test_archive_targets_and_statuses_are_pinned_from_the_authorities():
    """The two-target archive law, the ledger archived status, and the board
    archive status are read once from the family authorities — the golden
    absent-state fixture, the ledger vocabulary, and the board client."""
    import u06_modules.golden_absent as ga
    assert va.ARCHIVE_TARGETS == ga.ARCHIVE_TARGETS == ("board", "ledger")
    assert va.ARCHIVE_ACTION == ga.ARCHIVE_ACTION == "archive"
    assert va.EXECUTE_FLAG == ga.EXECUTE_FLAG == "--execute"
    assert va.LEDGER_ARCHIVED_STATUS == "archived"
    assert va.LEDGER_ARCHIVED_STATUS in state.ANTHOLOGY_STATUS
    assert va.BOARD_ARCHIVED_STATUS == board.ARCHIVE_STATUS == "blocked"
    assert board.ARCHIVE_STATUS != board.DONE_STATUS


def test_the_keying_law_is_the_shape_authority():
    """The board footprint is keyed by participant_key — the KEYING LAW
    composite (contact_id::anthology_id), read once from the ledger."""
    assert state.participant_key("cnt_golden", "anth_golden") == \
        "cnt_golden::anth_golden"


def test_no_surface_prints_a_token_or_a_full_id():
    """Every captured surface — the golden PASS report, the refusal reports,
    the plan — carries markers (last-4 suffixes) only: no credential shape,
    no full synthetic id, no full workflow id."""
    _, parsed = _check("anth_golden", journal=_golden_journal(), execute=True)
    blob = json.dumps(parsed)
    assert CREDENTIAL_SHAPE not in blob and "Bearer" not in blob
    assert "cnt_golden" not in blob and "anth_golden" not in blob
    _, parsed = _check("", journal=_golden_journal(), execute=True)
    blob = json.dumps(parsed)
    assert CREDENTIAL_SHAPE not in blob and "Bearer" not in blob
    assert "cnt_golden" not in blob and "anth_golden" not in blob


def test_plan_surface_never_carries_credential_shape():
    """The offline plan carries the read-back law as data and never a
    credential shape; it exits 0 with no network and no credential."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = va.plan()
    assert rc == EX_OK
    plan = json.loads(buf.getvalue())
    assert plan["contract"] == va.CONFIG_CONTRACT + "-plan"
    assert plan["targets"] == ["board", "ledger"]
    assert plan["execute_required"] is True
    assert plan["ledger_status_wanted"] == "archived"
    assert plan["board_status_wanted"] == "blocked"
    assert CREDENTIAL_SHAPE not in buf.getvalue()


# ---------------------------------------------------------------------------
# The sibling family batteries are green (a red sibling is caught HERE first).
# ---------------------------------------------------------------------------
def test_sibling_u06_batteries_are_green():
    """The U06 family's other offline batteries pass — the golden absent-
    state fixture, the no-execute attack — so the verifier is tested against
    a green family."""
    import u06_modules.golden_absent as ga
    import u06_modules.attack_no_execute as attack
    assert va.self_test(out=io.StringIO()) == EX_OK
    assert ga.self_test(out=io.StringIO()) == EX_OK
    assert attack.self_test(out=io.StringIO()) == EX_OK


def test_no_execute_attack_fails_the_family_gate_while_the_control_passes():
    """The archive-without---execute attack FAILS the family gate (exit 5)
    and the golden execute-required dry-run control PASSES (exit 0) — the
    pass/fail split discriminates the missing-gate boundary, never a broken
    instrument."""
    import u06_modules.attack_no_execute as attack
    assert attack.verify_archive(attack.ATTACK_ACTION_RECORD,
                                 out=io.StringIO()) == EX_MISMATCH
    assert attack.verify_archive(attack.GOLDEN_RECORD,
                                 out=io.StringIO()) == EX_OK


# ---------------------------------------------------------------------------
# Plain-python runner (no pytest required) — house style.
# ---------------------------------------------------------------------------
TESTS = [
    (test_verifier_self_test_passes_offline, False),
    (test_exit_code_convention_is_house_0_1_2_3_4_5, False),
    (test_browser_user_agent_is_a_browser_ua_cf_1010_law, False),
    (test_u06_package_init_is_fail_closed_empty, False),
    (test_golden_read_back_passes_with_both_targets_archived, False),
    (test_read_back_is_deterministic_and_never_mutates_its_inputs, False),
    (test_check_without_execute_stops_at_the_action_boundary, False),
    (test_check_cli_without_execute_stops, False),
    (test_verifier_never_writes_even_with_execute, False),
    (test_ledger_status_not_archived_is_a_mismatch, False),
    (test_assembly_card_not_at_board_archive_status_is_a_mismatch, False),
    (test_participant_card_not_at_board_archive_status_is_a_mismatch, False),
    (test_unknown_card_is_a_mismatch_never_proof_of_archived, False),
    (test_done_card_stops_never_a_pass, False),
    (test_empty_anthology_id_refuses_never_a_sweep, False),
    (test_credential_shaped_read_value_refuses_never_echoed, False),
    (test_live_mirror_archived_ledger_and_held_participant_passes, False),
    (test_live_mirror_archived_ledger_with_active_participant_is_a_mismatch, False),
    (test_live_mirror_unknown_anthology_is_a_mismatch, False),
    (test_live_mirror_unreadable_db_is_held_never_a_verdict, False),
    (test_board_status_maps_through_the_board_clients_projection, False),
    (test_archive_targets_and_statuses_are_pinned_from_the_authorities, False),
    (test_the_keying_law_is_the_shape_authority, False),
    (test_no_surface_prints_a_token_or_a_full_id, False),
    (test_plan_surface_never_carries_credential_shape, False),
    (test_sibling_u06_batteries_are_green, False),
    (test_no_execute_attack_fails_the_family_gate_while_the_control_passes, False),
]


def main():
    failed = 0
    for t, _ in TESTS:
        try:
            t()
            print("  PASS: %s" % t.__name__)
        except AssertionError as exc:
            failed += 1
            print("  FAIL: %s\n        %s" % (t.__name__, exc))
        except Exception as exc:  # noqa: BLE001 — a crash is a failure, reported as one
            failed += 1
            print("  ERROR: %s\n        %r" % (t.__name__, exc))
    print("\n=== %d passed, %d failed ===" % (len(TESTS) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
