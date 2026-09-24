#!/usr/bin/env python3
"""PD-TEST-092 -- one consumed repair receipt must not latch the phase forever.

THE DEFECT
----------
`_repair_receipt_is_actionable` gated on the bare bool `repair_receipt_consumed`:

    if led.get("repair_receipt_consumed"):
        return False, "paid-retry repair receipt already consumed"

Nothing ever clears that field -- `authorize_paid_retry_reset` writes only the
receipt, and `_reserve_paid_attempt` is the only writer of the bool, setting it
True.  So after a phase consumed its FIRST receipt, every LATER receipt was
refused no matter how valid it was: right phase, right run, right owner, right
allowance, right approved-input revision, right generation, matching installed
dispatcher hash.  A phase could be repaired exactly once in its lifetime.

Measured on the live run pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4
after the operator issued a fresh, correctly-bound receipt:

    live ledger : status=exhausted generation=1 paid_attempts=3
                  repair_receipt_consumed=True
    live receipt: prior_generation=1 allowance=3 dispatcher_sha256=63cb70f2...
    predicate   -> (False, 'paid-retry repair receipt already consumed')

P4-COPY is the phase in question, and it produces working/copy/slides_copy.md --
the input PD-TEST-081's slides_assembly.py needs to produce working/copy/slides.json,
which build_deck.py hard-requires.  So this latch makes the deck unreachable.

WHY REMOVING THE GATE IS SAFE -- exactly-once is the GENERATION's job
--------------------------------------------------------------------
The latch was redundant.  Single-use is enforced by the clause that requires
`receipt["prior_generation"] == led["generation"]`, because:

  * consumption is the ONLY writer of the ledger generation anywhere in the
    package -- `_reserve_paid_attempt`: `led["generation"] = int(...) + 1`;
  * it only ever increments, so a generation value never recurs;
  * therefore the instant a receipt is consumed the generation advances past its
    `prior_generation`, and that same receipt can never match again, in this
    process or any later one.

The bool is still WRITTEN on consumption as an audit record; it is simply no
longer a gate.  These tests pin both halves: a second receipt must be admitted,
and the same receipt must still be refused twice.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from presentation_job import dispatcher as dj  # noqa: E402

PHASE = "P4-COPY"
ARTIFACT = "working/copy/slides_copy.md"


def _order_file(run_dir: Path) -> Path:
    return run_dir / "working" / "work-orders" / f"{PHASE}.json"


def _seed_run(tmp_path: Path, *, paid_attempts: int | None = None,
              generation: int = 0, blocked: bool = True,
              consumed: bool = False, revision: str = "initial",
              extra: dict | None = None) -> Path:
    """An exhausted run whose only work order is PHASE.  Mirrors the PD-068
    harness so the two suites exercise the same real predicate."""
    run_dir = tmp_path / "run"
    (run_dir / "working" / "work-orders").mkdir(parents=True)
    (run_dir / "working" / "copy").mkdir(parents=True)
    (run_dir / "state.json").write_text(json.dumps({
        "phases": [{"id": PHASE, "status": "running"}],
    }), encoding="utf-8")
    _order_file(run_dir).write_text(json.dumps({
        "phase_id": PHASE, "produces_artifact": ARTIFACT,
    }), encoding="utf-8")
    led = {
        "phase_id": PHASE,
        "status": "exhausted",
        "approved_input_revision": revision,
        "paid_attempts": dj.DISPATCH_RETRY_CAP if paid_attempts is None else paid_attempts,
        "generation": generation,
        "blocked": blocked,
        "consecutive": dj.DISPATCH_REPEAT_CEILING,
        "repair_receipt_consumed": consumed,
    }
    if extra:
        led.update(extra)
    dj._write_ledger(run_dir, PHASE, led)
    return run_dir


def _issue(run_dir: Path, allowance: int = 1) -> dict:
    return dj.authorize_paid_retry_reset(run_dir, PHASE, allowance=allowance)


def _ledger(run_dir: Path) -> dict:
    return dj._read_ledger(run_dir, PHASE)


def _actionable(run_dir: Path):
    return dj._repair_receipt_is_actionable(_ledger(run_dir), PHASE, run_dir)


def _gate(run_dir: Path):
    return dj.should_dispatch(run_dir, PHASE, order_file=_order_file(run_dir))


def _reserve(run_dir: Path, worker: str = "w") -> None:
    dj._reserve_paid_attempt(run_dir, PHASE, worker)


# ---------------------------------------------------------------------------
# 1. THE DEFECT: a second receipt must be admitted after the first was spent.
# ---------------------------------------------------------------------------
class TestASecondReceiptIsAdmitted:

    def test_second_receipt_after_consumption_is_actionable(self, tmp_path):
        """Consume receipt #1, issue receipt #2, and require the predicate to
        admit it.  On the pre-fix code this returns
        (False, 'paid-retry repair receipt already consumed')."""
        rd = _seed_run(tmp_path, paid_attempts=dj.DISPATCH_RETRY_CAP)
        _issue(rd, allowance=1)
        _reserve(rd)                                  # consume #1
        after_first = _ledger(rd)
        assert after_first["generation"] == 1
        assert after_first["repair_receipt_consumed"] is True

        _issue(rd, allowance=1)                       # issue #2 for generation 1
        ok, why = _actionable(rd)
        assert ok, f"a fresh receipt for the current generation was refused: {why!r}"

    def test_second_receipt_actually_lifts_the_dispatch_gate(self, tmp_path):
        """The real gate -- not just the predicate -- must admit the phase."""
        rd = _seed_run(tmp_path, paid_attempts=dj.DISPATCH_RETRY_CAP)
        _issue(rd, allowance=1)
        _reserve(rd)
        _issue(rd, allowance=1)
        allowed, reason = _gate(rd)
        assert allowed, f"should_dispatch still refuses: {reason!r}"

    def test_second_receipt_is_consumed_and_restores_allowance(self, tmp_path):
        """End to end: banner #2 must actually be spendable."""
        rd = _seed_run(tmp_path, paid_attempts=dj.DISPATCH_RETRY_CAP)
        _issue(rd, allowance=3)
        _reserve(rd)
        assert _ledger(rd)["generation"] == 1

        _issue(rd, allowance=3)
        _reserve(rd)                                  # consume #2
        led = _ledger(rd)
        assert led["generation"] == 2, "the second consumption did not advance the generation"
        assert led["paid_attempts"] == 1, "allowance 3 was not spent down to one attempt"
        assert led["repair_receipt_consumed_generation"] == 1

    def test_three_successive_repairs_all_work(self, tmp_path):
        """The latch was a LIFETIME limit.  Prove it is gone for good."""
        rd = _seed_run(tmp_path, paid_attempts=dj.DISPATCH_RETRY_CAP)
        for expected_generation in (1, 2, 3):
            _issue(rd, allowance=1)
            ok, why = _actionable(rd)
            assert ok, f"repair #{expected_generation} refused: {why!r}"
            _reserve(rd)
            assert _ledger(rd)["generation"] == expected_generation


# ---------------------------------------------------------------------------
# 2. EXACTLY-ONCE SURVIVES: the generation clause is the real guard.
# ---------------------------------------------------------------------------
class TestExactlyOnceIsPreserved:

    def test_the_same_receipt_is_spent_exactly_once(self, tmp_path):
        """Spend receipt #1, then keep reserving.

        The receipt must be consumed exactly ONCE: the generation must never
        advance again, and the granted allowance must DRAIN to exhaustion rather
        than being re-granted.  (Consumption itself resets paid_attempts to
        DISPATCH_RETRY_CAP - allowance, so the phase is deliberately NOT
        exhausted immediately afterwards -- that reset is the whole point of the
        receipt.  The property under test is that it is not granted TWICE.)"""
        rd = _seed_run(tmp_path, paid_attempts=dj.DISPATCH_RETRY_CAP)
        _issue(rd, allowance=3)
        _reserve(rd)                        # consume #1
        led = _ledger(rd)
        assert led["generation"] == 1
        assert led["paid_attempts"] == 1, "allowance 3 should leave 1 of 3 spent"

        # the spent receipt is still on disk; it must not re-arm anything
        ok, why = _actionable(rd)
        assert not ok, "the spent receipt was actionable a second time"
        assert "generation" in why, (
            f"expected the generation clause to refuse it, got {why!r}")

        # the remaining two granted attempts are ordinary reservations
        _reserve(rd)
        assert _ledger(rd)["paid_attempts"] == 2
        assert _ledger(rd)["generation"] == 1, "the spent receipt re-armed the generation"
        _reserve(rd)
        assert _ledger(rd)["paid_attempts"] == 3

        # the fourth is past the granted allowance -> exhausted, not re-granted
        with pytest.raises(dj.PaidBudgetExhausted):
            _reserve(rd)
        final = _ledger(rd)
        assert final["generation"] == 1, "the refused retry advanced the generation"
        assert final["paid_attempts"] == 3

    def test_a_stale_generation_receipt_is_refused_and_spends_nothing(self, tmp_path):
        rd = _seed_run(tmp_path, paid_attempts=dj.DISPATCH_RETRY_CAP)
        _issue(rd, allowance=1)
        _reserve(rd)
        old = _ledger(rd)["repair_receipt"]
        assert old["prior_generation"] == 0
        before = _ledger(rd)

        # put the ALREADY-SPENT receipt back on disk and confirm it is inert
        dj._repair_receipt_path(rd, PHASE).write_text(
            json.dumps(old, sort_keys=True), encoding="utf-8")
        ok, why = _actionable(rd)
        assert not ok
        assert "generation" in why, why
        with pytest.raises(dj.PaidBudgetExhausted):
            _reserve(rd)
        after = _ledger(rd)
        assert after["generation"] == before["generation"]
        assert after["paid_attempts"] == before["paid_attempts"]

    def test_a_receipt_cannot_rearm_a_generation_it_was_not_issued_for(self, tmp_path):
        """Forge the receipt forward (prior_generation ahead of the ledger)."""
        rd = _seed_run(tmp_path, paid_attempts=dj.DISPATCH_RETRY_CAP, generation=1)
        rec = _issue(rd, allowance=1)
        rec["prior_generation"] = 99
        dj._repair_receipt_path(rd, PHASE).write_text(
            json.dumps(rec, sort_keys=True), encoding="utf-8")
        ok, why = _actionable(rd)
        assert not ok
        assert "generation" in why, why


# ---------------------------------------------------------------------------
# 3. THE LIVE LEDGER SHAPE: a legacy bool latch must not block a new receipt.
# ---------------------------------------------------------------------------
class TestTheLiveLedgerShape:

    def test_legacy_bool_latch_with_a_new_receipt_is_actionable(self, tmp_path):
        """Reproduce the live bytes exactly: generation=1,
        repair_receipt_consumed=True (a bare bool, written before this fix), and
        a fresh receipt issued for generation 1.  This is the state the real run
        was stuck in; it must now be actionable.

        Note on the `extra` field (raised in independent review): `repair_receipt`
        is carried in the fixture because the LIVE ledger carries it, so the
        fixture is faithful to the bytes this bug was found on. The predicate
        reads the receipt from DISK, never from `led["repair_receipt"]`, so that
        key is not what makes this test pass -- `test_a_consumed_bool_alone_does_not_block`
        below is the same assertion with no `extra` at all."""
        rd = _seed_run(
            tmp_path, paid_attempts=dj.DISPATCH_RETRY_CAP, generation=1,
            consumed=True,
            extra={"repair_receipt": {
                "kind": dj.DISPATCH_REPAIR_RECEIPT_KIND, "phase_id": PHASE,
                "prior_generation": 0, "allowance": 3,
            }},
        )
        _issue(rd, allowance=3)
        ok, why = _actionable(rd)
        assert ok, f"the live ledger shape is still latched: {why!r}"
        assert _gate(rd)[0], "should_dispatch still refuses the live shape"

    def test_a_consumed_bool_alone_does_not_block(self, tmp_path):
        """The bool on its own -- nothing else -- must no longer refuse."""
        rd = _seed_run(tmp_path, paid_attempts=dj.DISPATCH_RETRY_CAP,
                       generation=1, consumed=True)
        _issue(rd, allowance=1)
        ok, why = _actionable(rd)
        assert ok, f"the bare bool still latches the phase: {why!r}"


# ---------------------------------------------------------------------------
# 4. Everything the receipt still must prove is STILL enforced.
# ---------------------------------------------------------------------------
class TestAllOtherClausesStillFailClosed:

    @pytest.mark.parametrize("field,value,needle", [
        ("kind", "something-else", "kind"),
        ("phase_id", "P-OTHER", "different phase"),
        ("run", "/tmp/not-this-run", "different run"),
        ("allowance", 0, "allowance"),
        # PD-TEST-182: above the ceiling the producer actually enforces
        # (PHASE_TOTAL_PAID_HARD_CAP), not the legacy DISPATCH_RETRY_CAP.
        ("allowance", dj.PHASE_TOTAL_PAID_HARD_CAP + 1, "allowance"),
        ("prior_generation", 42, "generation"),
        ("approved_input_revision", "moved", "input revision"),
        ("operator_uid", 99999, "owner"),
        ("dispatcher_sha256", "0" * 64, "dispatcher source"),
    ])
    def test_a_forged_field_is_still_refused_after_the_fix(
            self, tmp_path, field, value, needle):
        rd = _seed_run(tmp_path, paid_attempts=dj.DISPATCH_RETRY_CAP)
        _issue(rd, allowance=1)
        _reserve(rd)                       # consume #1 so the phase is mid-life
        rec = _issue(rd, allowance=1)      # a legitimately fresh receipt
        rec[field] = value
        dj._repair_receipt_path(rd, PHASE).write_text(
            json.dumps(rec, sort_keys=True), encoding="utf-8")
        ok, why = _actionable(rd)
        assert not ok, f"forged {field}={value!r} was admitted"
        assert needle in why, f"expected {needle!r} in {why!r}"

    def test_a_missing_receipt_is_still_refused(self, tmp_path):
        rd = _seed_run(tmp_path, paid_attempts=dj.DISPATCH_RETRY_CAP, consumed=True)
        ok, why = _actionable(rd)
        assert not ok
        assert "no readable" in why, why

    def test_an_absent_ledger_is_still_refused(self, tmp_path):
        rd = tmp_path / "run"
        rd.mkdir()
        ok, why = dj._repair_receipt_is_actionable({}, PHASE, rd)
        assert not ok
        assert "no dispatch ledger" in why, why


# ---------------------------------------------------------------------------
# 5. The durable budget itself is untouched by any of this.
# ---------------------------------------------------------------------------
class TestTheDurableBudgetIsUnchanged:

    def test_exhaustion_without_a_receipt_is_still_exhaustion(self, tmp_path):
        rd = _seed_run(tmp_path, paid_attempts=dj.DISPATCH_RETRY_CAP)
        allowed, reason = _gate(rd)
        assert not allowed
        assert "budget" in reason or "exhausted" in reason, reason

    def test_consumed_bool_still_recorded_as_an_audit_trail(self, tmp_path):
        """We removed the GATE, not the RECORD."""
        rd = _seed_run(tmp_path, paid_attempts=dj.DISPATCH_RETRY_CAP)
        _issue(rd, allowance=2)
        _reserve(rd)
        led = _ledger(rd)
        assert led["repair_receipt_consumed"] is True
        assert led["repair_receipt_consumed_generation"] == 0
        assert led["repair_receipt"]["allowance"] == 2

    def test_the_audit_record_survives_an_outcome_fold(self, tmp_path):
        """The audit record must be DURABLE, not just written once.

        `record_outcome` rebuilds the ledger from a fresh dict, so any field it
        does not name is ERASED on the next tick.  The independent review of PR
        #1143 measured exactly that: the field was present after `_reserve` and
        gone after one fold, which made the advertised audit trail fiction.  Both
        of the other tests here assert it immediately after `_reserve` and so
        never crossed a fold -- this one does.
        """
        rd = _seed_run(tmp_path, paid_attempts=dj.DISPATCH_RETRY_CAP)
        _issue(rd, allowance=2)
        _reserve(rd)
        assert _ledger(rd)["repair_receipt_consumed_generation"] == 0

        dj.record_outcome(rd, PHASE, worker_id="w", status="failed",
                          reasons=["synthetic fold"], paid_attempts=1)
        folded = _ledger(rd)
        assert "repair_receipt_consumed_generation" in folded, (
            "the audit field was dropped by an outcome fold")
        assert folded["repair_receipt_consumed_generation"] == 0
        # and the fields exactly-once depends on must survive the same fold
        assert folded["generation"] == 1
        assert folded["repair_receipt_consumed"] is True

        # The carry-forward is UNCONDITIONAL, so the key alone proves nothing: it
        # is present with a null value even when no receipt was ever consumed
        # (raised as nit N8 in the delta re-review). Pin that explicitly, so the
        # operative assertion is always the VALUE and never mere membership.
        fresh = _seed_run(tmp_path / "fresh", paid_attempts=0, consumed=False)
        dj.record_outcome(fresh, PHASE, worker_id="w", status="ok", reasons=[])
        assert _ledger(fresh).get("repair_receipt_consumed_generation") is None, (
            "a never-consumed ledger must fold to a null audit generation")

        # The receipt is still not re-armable after the fold.
        ok, why = _actionable(rd)
        assert not ok, "the spent receipt became actionable again across a fold"
        assert "generation" in why, why
