#!/usr/bin/env python3
"""test_a7_selfheal_reconcile.py -- GK-17/U79 (A7): the S0->mc_board mirror silent
-drop repair proven CONVERGING, not merely detected.

ROOT CAUSE (see references/gk17-a7-selfheal.md for the full write-up): stage_s0_
intake.py's board-mirror step (mc_board.py ensure, WIRING[2]) runs inside intake_
router.py's spawn_stage_detached() subprocess -- launched fully DETACHED
(start_new_session=True), fire-and-forget, NEVER waited on and NEVER retried by
its parent. If that detached process dies at ANY point before reaching the mirror
step (an OSError launching the interpreter, an uncaught exception in an earlier
WIRING step, an OOM kill, a box restart mid-run), the participant's LEDGER row is
already durably written (anthology_state.py's upsert committed before the spawn),
but the board card is NEVER created and NOTHING records the drop -- the acknowledge
already returned 200 to the webhook caller. Before this unit, the ONLY recovery was
the once-daily `mc_board.py reconcile` tick, and the daily-tick wrapper
(reconcile_board() in anthology-smoke-test.py) reported "reconciled" off the
subprocess EXIT CODE alone -- which mc_board.py always returns 0 for by design
(fail-soft), even when a subject could not actually be repaired. Detection (a
v5.4.0 board-drift banner) and repair (this daily tick) were never linked by any
machine-checkable signal: "detection is not repair".

WHAT THIS SUITE PROVES (GK-17 BINARY acceptance, verbatim): given a ledger with one
participant whose card was never created (the induced A7 drop -- ensure was
suppressed, exactly as a dead detached spawn would suppress it) and one whose card
already exists, ONE `mc_board.py reconcile` pass (one scheduled cycle) creates
exactly the missing card, leaves the existing card's task_id untouched (zero
duplicate cards; a board read-back shows exactly one card per ledger subject), a
SECOND pass creates zero additional cards (idempotency_key dedupe holds across
repeated sweeps), and reconcile's own `converged` signal is True only when every
subject actually landed -- False when the repair path is deliberately broken,
which is the ONLY condition under which a caller should escalate to the banner.

Hermetic: imports mc_board.py directly (stdlib only); FakeBoard is an in-memory
stand-in for the Command Center that dedupes POST /api/tasks/ingest by
idempotency_key -- exactly the contract mc_board.py's own module docstring
documents for the real route -- so the dedupe proof below is REAL dedupe behavior,
not a scripted response. No network, no board process; a temp sqlite mirror per
test (never the real ~/.anthology-engine/state).

Run: python3 -m pytest 59-anthology-engine/tests/test_a7_selfheal_reconcile.py -q
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import mc_board  # noqa: E402


def _make_mirror(tmp_path, participants, anthologies):
    """Build a temp read-only-shaped mirror db with the given rows (the SAME schema
    mc_board.py's own self_test._make_temp_mirror uses, extended to accept MULTIPLE
    subjects so a mixed 'one dropped, one already-mirrored' scenario -- the shape a
    real daily tick sees -- is representable)."""
    db = Path(tmp_path) / "anthology_state.db"
    con = sqlite3.connect(str(db))
    con.executescript(
        "CREATE TABLE participants(participant_key TEXT PRIMARY KEY, contact_id TEXT,"
        " anthology_id TEXT, first_name TEXT, last_name TEXT, stage_cursor TEXT);"
        "CREATE TABLE anthologies(anthology_id TEXT PRIMARY KEY, name TEXT,"
        " assembly_state TEXT);")
    for p in participants:
        con.execute("INSERT INTO participants VALUES(?,?,?,?,?,?)", p)
    for a in anthologies:
        con.execute("INSERT INTO anthologies VALUES(?,?,?)", a)
    con.commit()
    con.close()
    return db


class FakeBoard:
    """In-memory stand-in for the Command Center task store: dedupes POST
    /api/tasks/ingest by idempotency_key (mc_board.py's own module docstring names
    this as the real route's contract) and records every status move. Installed as
    mc_board._TRANSPORT, so post_ingest/post_status run their REAL logic against
    this fake wire -- only the network hop is replaced.

    `refuse_ingest_for` names idempotency_key(s) whose ingest is made to fail
    PERMANENTLY (every call, every pass) -- the "repair path is deliberately
    broken" fixture GK-17's acceptance criterion asks for, distinct from a
    transient blip."""

    def __init__(self, refuse_ingest_for=frozenset()):
        self.cards = {}       # idempotency_key -> task_id
        self.statuses = {}    # task_id -> status
        self.ingest_calls = 0
        self.status_calls = 0
        self.refuse_ingest_for = frozenset(refuse_ingest_for)
        self._next = 1

    def seed(self, idem, status="backlog"):
        """Pre-populate a card as if an earlier, successful S0 ensure already
        created it -- the 'already-mirrored participant' half of the fixture."""
        tid = "card_seed_%d" % self._next
        self._next += 1
        self.cards[idem] = tid
        self.statuses[tid] = status
        return tid

    def transport(self, url, body_bytes, headers, timeout):
        body = json.loads(body_bytes)
        if url.endswith(mc_board.DEFAULT_INGEST_PATH):
            self.ingest_calls += 1
            idem = body.get("idempotency_key")
            if idem in self.refuse_ingest_for:
                return 503, {"error": "board refusing ingest for this fixture"}
            if idem in self.cards:
                return 200, {"ok": True, "deduped": True, "task_id": self.cards[idem]}
            tid = "card_%d" % self._next
            self._next += 1
            self.cards[idem] = tid
            self.statuses[tid] = "backlog"
            return 201, {"ok": True, "deduped": False, "task_id": tid}
        self.status_calls += 1
        tid = url.rsplit("/api/tasks/", 1)[1].split("/status", 1)[0]
        if tid not in self.statuses:
            return 404, {"error": "unknown task"}
        self.statuses[tid] = body.get("status")
        return 200, {"id": tid, "status": body.get("status")}


@pytest.fixture(autouse=True)
def _restore_transport():
    """mc_board._TRANSPORT is a MODULE-level hook; every test below swaps it in.
    Guarantee it is restored even if a test raises -- mirrors mc_board.py's own
    self_test() try/finally discipline so this suite can never leak a fake
    transport into a test that runs after it."""
    original = mc_board._TRANSPORT
    yield
    mc_board._TRANSPORT = original


def test_induced_drop_is_repaired_within_one_reconcile_pass(tmp_path):
    """GK-17 BINARY acceptance, clause 1: an induced drop (one participant whose
    ensure was suppressed -- it has a ledger row but no board card) is fully
    repaired by ONE `reconcile` sweep (one scheduled cycle) with zero operator
    action, and the already-mirrored participant's existing card is left
    untouched -- never duplicated."""
    mirror = _make_mirror(
        tmp_path,
        participants=[
            ("dropped::ANTH1", "dropped", "ANTH1", "Drop", "Ped", "s1_avatar"),
            ("mirrored::ANTH1", "mirrored", "ANTH1", "Already", "Mirrored", "s1_avatar"),
        ],
        anthologies=[("ANTH1", "Test Anthology", "not_ready")],
    )
    board = FakeBoard()
    bcfg = mc_board.BoardConfig({})
    # -- the "mirrored" participant's S0 ensure succeeded normally: its card
    #    already exists BEFORE reconcile ever runs.
    already_idem = "anthology:card:mirrored::ANTH1"
    pre_existing_id = board.seed(already_idem)
    # -- the "dropped" participant's S0 ensure call NEVER HAPPENED (the induced A7
    #    drop, e.g. its detached spawn died before reaching WIRING[2]): deliberately
    #    do NOT seed or call post_ingest for it.

    mc_board._TRANSPORT = board.transport
    result = mc_board._reconcile_sweep(bcfg, str(mirror.parent), timeout=5, verbose=True)

    assert result["ok"] is True
    assert result["subjects"] == 3          # 1 anthology + 2 participants
    assert result["converged"] is True, "a clean reconcile with no fixture breakage must converge"
    assert result["failsoft"] is False
    assert result["counts"]["synced"] == 3
    assert result["counts"]["deferred"] == 0 and result["counts"]["error"] == 0

    # -- the dropped participant now HAS a card -------------------------------
    dropped_idem = "anthology:card:dropped::ANTH1"
    assert dropped_idem in board.cards, "the induced drop must be repaired by the reconcile sweep"
    assert board.statuses[board.cards[dropped_idem]] == "in_progress", (
        "s1_avatar projects to in_progress; the repaired card must land in the right column")

    # -- the already-mirrored participant's card was NOT duplicated ----------
    assert board.cards[already_idem] == pre_existing_id, (
        "an already-mirrored participant's task_id must be UNCHANGED by reconcile "
        "(idempotent dedupe, never a second card)")

    # -- board read-back: exactly ONE card per ledger subject, zero duplicates --
    assert len(board.cards) == 3   # 2 participant cards + 1 Assembly card
    assert board.ingest_calls == 3, "every subject is re-POSTed (idempotent), never skipped"


def test_second_reconcile_pass_creates_zero_duplicate_cards(tmp_path):
    """GK-17 BINARY acceptance, clause 2 ('zero duplicate cards'): running
    reconcile TWICE in a row (the daily tick recurring) must never create a second
    task_id for the same subject -- idempotency_key dedupe holds across repeated
    sweeps."""
    mirror = _make_mirror(
        tmp_path,
        participants=[("c1::A1", "c1", "A1", "One", "Fish", "s5_gate")],
        anthologies=[("A1", "Anthology One", "compiled")],
    )
    board = FakeBoard()
    bcfg = mc_board.BoardConfig({})
    mc_board._TRANSPORT = board.transport

    r1 = mc_board._reconcile_sweep(bcfg, str(mirror.parent), timeout=5)
    assert r1["converged"] is True
    cards_after_first = dict(board.cards)
    ingest_calls_after_first = board.ingest_calls
    assert len(cards_after_first) == 2   # 1 participant + 1 assembly

    r2 = mc_board._reconcile_sweep(bcfg, str(mirror.parent), timeout=5)
    assert r2["converged"] is True
    assert board.cards == cards_after_first, (
        "a second reconcile pass must dedupe onto the SAME task_ids, never mint new ones")
    assert len(board.cards) == 2, "the board's card count must never grow across repeated sweeps"
    # the second pass still re-POSTS ingest per subject (idempotent by design), but
    # the board's own idempotency_key dedupe means it never allocates a new task_id.
    assert board.ingest_calls == ingest_calls_after_first + 2


def test_deliberately_broken_repair_path_fails_to_converge(tmp_path):
    """GK-17 BINARY acceptance, clause 3: the banner is the escalation of LAST
    RESORT -- it must render ONLY when the repair path is deliberately broken.
    Here the fixture permanently refuses to ingest ONE participant's card
    (simulating a repair path that cannot succeed, not merely a transient blip);
    reconcile must still exit cleanly (fail-soft, never blocks the tick) but its
    `converged` signal must be False -- the ONLY condition a drift-detector banner
    should key on."""
    mirror = _make_mirror(
        tmp_path,
        participants=[
            ("ok::A1", "ok", "A1", "Ok", "Fish", "s1_avatar"),
            ("broken::A1", "broken", "A1", "Broken", "Fish", "s1_avatar"),
        ],
        anthologies=[("A1", "Anthology One", "not_ready")],
    )
    broken_idem = "anthology:card:broken::A1"
    board = FakeBoard(refuse_ingest_for={broken_idem})
    bcfg = mc_board.BoardConfig({})
    mc_board._TRANSPORT = board.transport

    result = mc_board._reconcile_sweep(bcfg, str(mirror.parent), timeout=5, verbose=True)

    assert result["converged"] is False, (
        "a permanently-refused ingest must prevent convergence -- this is the "
        "escalate-to-banner signal")
    assert result["failsoft"] is True
    assert result["counts"]["deferred"] >= 1
    assert broken_idem not in board.cards, "the deliberately-broken subject must genuinely have no card"
    # one bad subject never blocks the rest of the sweep (mirrors _sync_one's own
    # per-subject fail-soft contract) -- the healthy subject in the SAME sweep
    # still gets its card.
    ok_idem = "anthology:card:ok::A1"
    assert ok_idem in board.cards


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
