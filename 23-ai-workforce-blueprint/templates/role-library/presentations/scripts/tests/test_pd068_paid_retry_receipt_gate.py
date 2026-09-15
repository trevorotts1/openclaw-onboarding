"""PD-TEST-068 -- a valid, unconsumed local-operator repair receipt must lift
the paid-budget GATE, not just the post-claim reservation.

THE DEFECT (root-caused at code level, then observed live).

`should_dispatch()` carried an early return on its exhausted branch:

    if led.get('blocked') and int(led.get('paid_attempts') or 0) >= DISPATCH_RETRY_CAP:
        return False, 'paid retry budget exhausted: ...'

That clause PRECEDED every other clause of the same function. Meanwhile the
repair receipt written by `authorize_paid_retry_reset()` (kind
`local-operator-paid-retry-reset-v1`) was read in exactly ONE place --
`_reserve_paid_attempt()` -- which is only reached from `dispatch_complete()`,
i.e. only AFTER a claim, and every claim path is gated by `should_dispatch()`
(the three call sites in `sweep_run_dir`, the scheduler's claim loop and the
scan-root reporter).

So a valid, unconsumed receipt could never lift the very gate that blocks its
own consumption. Live observation: the receipt was issued rc=0, six 30s samples
over ~2.5 minutes showed zero consumption, zero dispatch, zero provider
requests, and the ledger unchanged (`status=exhausted`, `paid_attempts=3`,
`generation=0`, `repair_receipt_consumed=False`).

Two secondary contradictions are part of the same defect and are pinned here
too: `authorize_paid_retry_reset`'s docstring promises the receipt IS consumed
exactly once, while the human-readable marker written by `_park_blocked()` told
the operator that dispatch resumes ONLY after an approved-input amendment.

WHAT THIS FILE PINS

  A. THE GATE HONOURS AN ACTIONABLE RECEIPT, READ-ONLY.
     `should_dispatch()` returns True for an exhausted, blocked ledger carrying
     a valid unconsumed receipt -- and the ledger bytes and the receipt bytes
     are byte-identical afterwards. The gate consumes nothing, resets nothing
     and mutates nothing; three call sites rely on that.
  B. ONE SHARED PREDICATE, TWO CALL SITES.
     The gate and the reservation both call `_repair_receipt_is_actionable`.
     Every refusal below is asserted at BOTH seams, which is only possible
     because there is one predicate: a field the gate rejects is a field the
     reservation rejects, in the same words.
  C. THE RESERVATION IS STILL THE SINGLE CONSUMER.
     Consumed exactly once (durable `repair_receipt_consumed=True`); a second
     reservation is refused; one allowance can never buy two resets; two
     concurrent reservations produce exactly one winner, one generation bump and
     one consumed paid slot.
  D. THE BUDGET IS NOT WEAKENED FOR THE NO-RECEIPT CASE.
     Missing / stale / forged / already-consumed receipts all keep the existing
     truthful refusal text. Not-blocked-and-under-cap still returns `(True, "")`
     exactly as before, and the anti-starvation revision clause still precedes
     the receipt clause.
  E. THE OPERATOR MARKER TELLS THE TRUTH.
     `_park_blocked()`'s marker now names the bounded repair-receipt route as an
     alternative resume path -- and its `reason:` line still carries the
     `paid retry budget exhausted` text the Engine's own reader
     (`phases.Engine._read_blocked_marker`) keys the PD-014 park reaction on.

No test here touches the network, a provider, the live run directory, or the
installed mirrors. Everything is the real code against a scratch run dir.
"""
from __future__ import annotations

import hashlib
import json
import sys
import threading
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as dj  # noqa: E402
from presentation_job import phases as phases_mod  # noqa: E402

PHASE = "P-LIVE-VOICE"
OTHER_PHASE = "P-SPINE"
ARTIFACT = "working/live/voice.json"

# The truthful refusal text that predates this repair. It must survive verbatim
# for every case where no actionable receipt is present.
EXHAUSTED_REFUSAL = (
    f"paid retry budget exhausted: {dj.DISPATCH_RETRY_CAP} provider attempts for "
    f"unchanged approved input (DISPATCH_RETRY_CAP={dj.DISPATCH_RETRY_CAP})"
)


# ---------------------------------------------------------------------------
# Fixtures -- a scratch run dir whose ledger says exactly what each test needs.
# ---------------------------------------------------------------------------
def _order_file(run_dir: Path) -> Path:
    return run_dir / "working" / "work-orders" / f"{PHASE}.json"


def _seed_run(tmp_path: Path, *, paid_attempts: int | None = None,
              generation: int = 0, blocked: bool = True,
              consumed: bool = False, revision: str = "initial") -> Path:
    """An exhausted run whose only work order is PHASE.

    The revision is `"initial"` because `_approved_input_revision()` returns
    `"initial"` for a run with no intake/amendments -- so the ledger and the
    live revision agree and the gate reaches the exhausted branch. Nothing is
    monkeypatched: the revision oracle is the real one.
    """
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
    dj._write_ledger(run_dir, PHASE, led)
    return run_dir


def _issue(run_dir: Path, allowance: int = 1) -> dict:
    """Issue a real receipt through the real control-plane action."""
    return dj.authorize_paid_retry_reset(run_dir, PHASE, allowance=allowance)


def _forge(run_dir: Path, **overrides) -> dict:
    """Issue, then rewrite ONE field on disk. Models a hand-edited receipt: the
    file is still valid JSON of the right kind, and the forged field is the only
    thing standing between it and a reset."""
    receipt = _issue(run_dir)
    receipt.update(overrides)
    dj._repair_receipt_path(run_dir, PHASE).write_text(
        json.dumps(receipt, sort_keys=True), encoding="utf-8")
    return receipt


def _ledger(run_dir: Path) -> dict:
    return dj._read_ledger(run_dir, PHASE)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _gate(run_dir: Path):
    return dj.should_dispatch(run_dir, PHASE, order_file=_order_file(run_dir))


def _reserve(run_dir: Path, worker: str = "w") -> None:
    dj._reserve_paid_attempt(run_dir, PHASE, worker)


def _assert_refused_at_both_seams(run_dir: Path) -> str:
    """The whole point of the shared predicate: whatever the gate refuses, the
    reservation refuses too -- and vice versa. Neither seam may leave a mark."""
    ledger_path = dj._ledger_path(run_dir, PHASE)
    before = _sha(ledger_path)
    may, why = _gate(run_dir)
    assert may is False, "the gate admitted a receipt it should have refused"
    assert why == EXHAUSTED_REFUSAL, (
        f"the no-actionable-receipt refusal text changed: {why!r}")
    assert _sha(ledger_path) == before, "the refusing gate mutated the ledger"
    with pytest.raises(dj.PaidBudgetExhausted):
        _reserve(run_dir)
    assert _sha(ledger_path) == before, "the refusing reservation wrote the ledger"
    assert _ledger(run_dir)["paid_attempts"] == dj.DISPATCH_RETRY_CAP
    return why


# ---------------------------------------------------------------------------
# A. The gate honours an actionable receipt, and is READ-ONLY.
# ---------------------------------------------------------------------------
class TestGateHonoursAnActionableReceipt:
    def test_exhausted_blocked_ledger_with_valid_receipt_dispatches(
            self, tmp_path):
        run_dir = _seed_run(tmp_path)
        # Before the receipt: the live PD-TEST-068 state, refused.
        assert _gate(run_dir)[0] is False
        _issue(run_dir, allowance=1)
        may, why = _gate(run_dir)
        assert may is True
        assert why == "valid unconsumed paid-retry repair receipt"

    def test_gate_leaves_ledger_and_receipt_bytes_untouched(self, tmp_path):
        """`should_dispatch` is a read-only preflight. Callers rely on it: it
        must not consume the receipt, reset the counters, or touch the ledger."""
        run_dir = _seed_run(tmp_path)
        receipt = _issue(run_dir, allowance=1)
        ledger_path = dj._ledger_path(run_dir, PHASE)
        receipt_path = dj._repair_receipt_path(run_dir, PHASE)
        led_before = _sha(ledger_path)
        rec_before = _sha(receipt_path)
        snapshot = json.loads(ledger_path.read_text(encoding="utf-8"))

        # Repeated reads, exactly as the sweep / scheduler / reporter do.
        for _ in range(3):
            assert _gate(run_dir)[0] is True

        assert _sha(ledger_path) == led_before, "the gate rewrote the ledger"
        assert _sha(receipt_path) == rec_before, "the gate consumed the receipt"
        assert json.loads(ledger_path.read_text(encoding="utf-8")) == snapshot
        assert _ledger(run_dir)["generation"] == 0
        assert _ledger(run_dir)["paid_attempts"] == dj.DISPATCH_RETRY_CAP
        assert _ledger(run_dir)["repair_receipt_consumed"] is False
        # And the marker is not cleared by a read either.
        assert json.loads(receipt_path.read_text(encoding="utf-8")) == receipt

    def test_gate_admits_then_the_reservation_still_binds_the_budget(
            self, tmp_path):
        """Admitting the phase is not the same as spending an unbounded budget:
        the receipt buys exactly its allowance, and the ceiling still bites."""
        run_dir = _seed_run(tmp_path)
        _issue(run_dir, allowance=1)
        assert _gate(run_dir)[0] is True
        _reserve(run_dir, "w1")
        assert _ledger(run_dir)["paid_attempts"] == dj.DISPATCH_RETRY_CAP
        assert _ledger(run_dir)["generation"] == 1
        assert _ledger(run_dir)["repair_receipt_consumed"] is True
        _assert_refused_at_both_seams(run_dir)


# ---------------------------------------------------------------------------
# B/C. The reservation is the single consumer: exactly once.
# ---------------------------------------------------------------------------
class TestReservationIsTheSingleConsumer:
    def test_reservation_consumes_the_receipt_exactly_once(self, tmp_path):
        run_dir = _seed_run(tmp_path)
        _issue(run_dir, allowance=1)
        _reserve(run_dir, "w1")
        led = _ledger(run_dir)
        assert led["repair_receipt_consumed"] is True
        assert led["generation"] == 1, "the allowance was applied, not a no-op"
        assert led["repair_receipt"]["kind"] == dj.DISPATCH_REPAIR_RECEIPT_KIND
        assert led["repair_receipt"]["allowance"] == 1
        assert led["paid_attempts"] == dj.DISPATCH_RETRY_CAP

    def test_second_claim_is_refused(self, tmp_path):
        run_dir = _seed_run(tmp_path)
        _issue(run_dir, allowance=1)
        _reserve(run_dir, "w1")
        with pytest.raises(dj.PaidBudgetExhausted):
            _reserve(run_dir, "w1")
        # A DIFFERENT worker must not fare better: consumption is durable, not
        # per-process state.
        with pytest.raises(dj.PaidBudgetExhausted):
            _reserve(run_dir, "restarted-worker")
        assert _ledger(run_dir)["generation"] == 1

    def test_one_allowance_never_buys_two_resets(self, tmp_path):
        """allowance=3 buys three RESERVATIONS, not two resets: the generation
        advances exactly once and the receipt is spent on the first claim."""
        run_dir = _seed_run(tmp_path)
        _issue(run_dir, allowance=3)
        _reserve(run_dir, "w1")
        led = _ledger(run_dir)
        assert led["paid_attempts"] == 1, "paid = CAP - allowance, then +1"
        assert led["generation"] == 1
        assert led["repair_receipt_consumed"] is True
        # The remaining two slots are ordinary budget -- each claim spends one,
        # and the reset is never re-applied.
        _reserve(run_dir, "w1")
        _reserve(run_dir, "w1")
        assert _ledger(run_dir)["paid_attempts"] == dj.DISPATCH_RETRY_CAP
        assert _ledger(run_dir)["generation"] == 1, "a second reset was applied"
        with pytest.raises(dj.PaidBudgetExhausted):
            _reserve(run_dir, "w1")

    def test_two_concurrent_reservations_exactly_one_wins(self, tmp_path):
        """Two concurrent claim attempts race the SAME receipt. The phase's
        budget transaction (flock) plus the durable consumed flag must give
        exactly one winner, exactly one generation bump, and exactly one
        consumed paid slot -- never two resets."""
        run_dir = _seed_run(tmp_path)
        _issue(run_dir, allowance=1)
        start = threading.Barrier(2)
        results: list = []
        guard = threading.Lock()

        def claim(worker: str) -> None:
            start.wait(10)
            try:
                _reserve(run_dir, worker)
                outcome = "won"
            except dj.PaidBudgetExhausted:
                outcome = "refused"
            with guard:
                results.append(outcome)

        threads = [threading.Thread(target=claim, args=(f"w{i}",)) for i in (1, 2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(20)
        assert not any(t.is_alive() for t in threads), "a claim deadlocked"

        assert sorted(results) == ["refused", "won"], (
            f"expected exactly one winner, got {results!r}")
        led = _ledger(run_dir)
        assert led["generation"] == 1, "the allowance was applied twice or never"
        assert led["repair_receipt_consumed"] is True
        # allowance 1 gave back exactly one slot and the single winner spent it.
        assert led["paid_attempts"] == dj.DISPATCH_RETRY_CAP


# ---------------------------------------------------------------------------
# D. Every refusal is fail-closed, at BOTH seams, with the old truthful text.
# ---------------------------------------------------------------------------
class TestRefusalsAreFailClosed:
    def test_missing_receipt_is_refused_with_the_existing_truthful_message(
            self, tmp_path):
        run_dir = _seed_run(tmp_path)
        assert not dj._repair_receipt_path(run_dir, PHASE).exists()
        assert _assert_refused_at_both_seams(run_dir) == EXHAUSTED_REFUSAL

    def test_unreadable_receipt_is_refused(self, tmp_path):
        run_dir = _seed_run(tmp_path)
        path = dj._repair_receipt_path(run_dir, PHASE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json at all", encoding="utf-8")
        _assert_refused_at_both_seams(run_dir)

    def test_foreign_receipt_kind_is_refused(self, tmp_path):
        run_dir = _seed_run(tmp_path)
        _forge(run_dir, kind="some-other-repair-v1")
        _assert_refused_at_both_seams(run_dir)

    def test_stale_dispatcher_sha256_is_refused(self, tmp_path):
        """A receipt issued against a DIFFERENT dispatcher source is stale: it
        cannot authorise attempts under code it was never issued for."""
        run_dir = _seed_run(tmp_path)
        _forge(run_dir, dispatcher_sha256="0" * 64)
        _assert_refused_at_both_seams(run_dir)

    def test_already_consumed_receipt_is_refused(self, tmp_path):
        run_dir = _seed_run(tmp_path)
        _issue(run_dir, allowance=1)
        _reserve(run_dir, "w1")                      # consumes it
        assert _ledger(run_dir)["repair_receipt_consumed"] is True
        _assert_refused_at_both_seams(run_dir)

    def test_consumed_flag_alone_refuses_a_fresh_looking_receipt(self, tmp_path):
        """The durable flag is the claim, not the file's presence: a receipt
        re-copied onto disk after consumption must not re-arm anything."""
        run_dir = _seed_run(tmp_path, consumed=True)
        _issue(run_dir, allowance=dj.DISPATCH_RETRY_CAP)
        assert dj._repair_receipt_path(run_dir, PHASE).exists()
        _assert_refused_at_both_seams(run_dir)

    def test_wrong_run_is_refused(self, tmp_path):
        run_dir = _seed_run(tmp_path)
        _forge(run_dir, run=str(tmp_path / "some" / "other" / "run"))
        _assert_refused_at_both_seams(run_dir)

    def test_wrong_phase_id_is_refused(self, tmp_path):
        run_dir = _seed_run(tmp_path)
        _forge(run_dir, phase_id=OTHER_PHASE)
        _assert_refused_at_both_seams(run_dir)

    def test_wrong_generation_on_the_receipt_is_refused(self, tmp_path):
        run_dir = _seed_run(tmp_path)
        _forge(run_dir, prior_generation=99)
        _assert_refused_at_both_seams(run_dir)

    def test_ledger_generation_moving_on_stales_the_receipt(self, tmp_path):
        """The other direction: the receipt is honest, the LEDGER moved. A
        receipt can never re-arm a generation it was not issued against."""
        run_dir = _seed_run(tmp_path, generation=0)
        _issue(run_dir, allowance=1)
        led = _ledger(run_dir)
        led["generation"] = 1
        dj._write_ledger(run_dir, PHASE, led)
        _assert_refused_at_both_seams(run_dir)

    def test_wrong_approved_input_revision_is_refused(self, tmp_path):
        run_dir = _seed_run(tmp_path)
        _forge(run_dir, approved_input_revision="approved-intake:" + "f" * 64)
        _assert_refused_at_both_seams(run_dir)

    def test_wrong_owner_uid_is_refused(self, tmp_path):
        run_dir = _seed_run(tmp_path)
        _forge(run_dir, operator_uid=-1)
        _assert_refused_at_both_seams(run_dir)

    def test_ledger_without_a_durable_generation_is_refused(self, tmp_path):
        """A legacy/hand-written ledger with no integer generation cannot be
        bound to any receipt: treating a missing field as generation zero is
        exactly how a hand-created legacy ledger would satisfy a fresh receipt."""
        run_dir = _seed_run(tmp_path)
        _issue(run_dir, allowance=1)
        led = _ledger(run_dir)
        del led["generation"]
        dj._write_ledger(run_dir, PHASE, led)
        _assert_refused_at_both_seams(run_dir)

    @pytest.mark.parametrize("allowance", [0, -1, -3,
                                           dj.DISPATCH_RETRY_CAP + 1,
                                           None, "1", True])
    def test_non_positive_or_unbounded_allowance_is_refused(
            self, tmp_path, allowance):
        """`allowance` must be a positive int within DISPATCH_RETRY_CAP.

        The bound and the `isinstance(..., int)` test are the pre-existing
        predicate's own; the only tightening is that `bool` is refused
        explicitly (it is an `int` SUBCLASS in Python, so the old clause would
        have accepted a forged `"allowance": true` as a one-attempt allowance).
        That is strictly fail-closed: it can only refuse receipts the old
        predicate would also have refused, plus the bool impostor.
        """
        run_dir = _seed_run(tmp_path)
        _forge(run_dir, allowance=allowance)
        _assert_refused_at_both_seams(run_dir)

    def test_forged_receipt_is_refused_even_when_the_gate_alone_is_asked(
            self, tmp_path):
        """Belt and braces: the gate must refuse on its own predicate, without
        relying on the reservation to catch it later."""
        run_dir = _seed_run(tmp_path)
        _forge(run_dir, prior_generation=42)
        may, why = _gate(run_dir)
        assert may is False and why == EXHAUSTED_REFUSAL


# ---------------------------------------------------------------------------
# D. Normal protection intact: nothing changed for the no-receipt world.
# ---------------------------------------------------------------------------
class TestNormalProtectionIntact:
    def test_not_blocked_and_under_cap_still_dispatches(self, tmp_path):
        run_dir = _seed_run(tmp_path, paid_attempts=0, blocked=False)
        assert _gate(run_dir) == (True, "")

    def test_blocked_over_cap_with_no_receipt_is_refused(self, tmp_path):
        run_dir = _seed_run(tmp_path, paid_attempts=dj.DISPATCH_RETRY_CAP,
                            blocked=True)
        may, why = _gate(run_dir)
        assert may is False
        assert why == EXHAUSTED_REFUSAL

    def test_blocked_over_cap_receipt_route_does_not_leak_into_normal_path(
            self, tmp_path):
        """The receipt clause lives INSIDE the exhausted branch: an unblocked
        phase under cap takes the ordinary path, reason and all, whether or not
        a receipt happens to be sitting on disk."""
        run_dir = _seed_run(tmp_path, paid_attempts=1, blocked=False)
        _forge(run_dir, prior_generation=0)      # a durable, wrong receipt
        assert _gate(run_dir) == (True, "")

    def test_blocked_below_cap_takes_the_backoff_path_not_the_receipt_path(
            self, tmp_path):
        """A receipt only speaks to the PAID-BUDGET park. An unpaid repeat-ceiling
        park below the cap keeps its ordinary backoff semantics."""
        run_dir = _seed_run(tmp_path, paid_attempts=1, blocked=True)
        led = _ledger(run_dir)
        led["next_eligible_at_epoch"] = 1e12
        led["revision"] = dj._dispatch_revision(run_dir, PHASE, _order_file(run_dir))
        led["consecutive"] = dj.DISPATCH_REPEAT_CEILING
        dj._write_ledger(run_dir, PHASE, led)
        _issue(run_dir, allowance=1)
        may, why = _gate(run_dir)
        assert may is False
        assert "backoff" in why and "consecutive" in why

    def test_anti_starvation_revision_clause_still_precedes_the_receipt_clause(
            self, tmp_path, monkeypatch):
        """Ordering is part of the contract. An approved-input revision change
        must still win first, with its own reason -- never the receipt's."""
        run_dir = _seed_run(tmp_path)
        _issue(run_dir, allowance=1)
        monkeypatch.setattr(dj, "_approved_input_revision",
                            lambda *_a, **_k: "approved-intake:" + "a" * 64)
        may, why = _gate(run_dir)
        assert may is True
        assert why == "approved input revision changed", (
            "the anti-starvation clause no longer precedes the receipt clause")

    def test_repeat_ceiling_constant_is_untouched(self):
        """The ceiling this repair must not weaken."""
        assert dj.DISPATCH_REPEAT_CEILING == 8
        assert dj.DISPATCH_RETRY_CAP == 3


# ---------------------------------------------------------------------------
# E. The operator marker tells the truth, and still trips the engine's reader.
# ---------------------------------------------------------------------------
class _MarkerReaderStub:
    """The Engine's OWN marker reader, with only the two attributes it touches.

    Calling the real `phases.Engine._read_blocked_marker` (rather than copying
    its extraction logic here) is what makes the second assertion below a real
    regression guard: the engine's PD-014 paid-budget reaction is keyed on this
    exact string.
    """

    _BLOCKED_MARKER_SUMMARY_CHARS = 200

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir

    def _blocked_marker_path(self, phase_id: str) -> Path:
        return dj._blocked_marker_path(self.run_dir, phase_id)


def _park_at_paid_cap(run_dir: Path) -> str:
    """Drive the REAL fold so the marker carries the real paid-budget reason."""
    order = _order_file(run_dir)
    entry = dj.record_outcome(run_dir, PHASE, "exhausted",
                              ["deterministic provider failure"],
                              worker_id="w", order_file=order,
                              paid_attempts=dj.DISPATCH_RETRY_CAP)
    assert entry["blocked"] is True
    return dj._blocked_marker_path(run_dir, PHASE).read_text(encoding="utf-8")


class TestOperatorMarkerNamesBothRoutes:
    def test_marker_names_the_bounded_repair_receipt_route(self, tmp_path):
        run_dir = _seed_run(tmp_path, paid_attempts=0, blocked=False)
        text = _park_at_paid_cap(run_dir)
        assert "REPAIR-RECEIPT route" in text
        assert dj.DISPATCH_REPAIR_RECEIPT_KIND in text
        assert f"allowance 1..{dj.DISPATCH_RETRY_CAP}" in text
        assert "--authorize-paid-retry-reset" in text
        assert "--reset-allowance" in text
        # The engine route is still named, and the OLD lie is gone.
        assert "ENGINE route" in text
        assert "resumes only after a verified owner" not in text

    def test_marker_reason_line_still_trips_the_engine_paid_budget_reaction(
            self, tmp_path):
        run_dir = _seed_run(tmp_path, paid_attempts=0, blocked=False)
        _park_at_paid_cap(run_dir)
        summary = phases_mod.Engine._read_blocked_marker(
            _MarkerReaderStub(run_dir), PHASE)
        assert summary is not None
        assert "paid retry budget exhausted" in summary, (
            "the engine's PD-014 paid-budget park reaction no longer fires: "
            f"{summary!r}")

    def test_marker_keeps_its_operator_facing_header_and_ledger_pointer(
            self, tmp_path):
        run_dir = _seed_run(tmp_path, paid_attempts=0, blocked=False)
        text = _park_at_paid_cap(run_dir)
        assert text.startswith("DISPATCH BLOCKED -- NEEDS ATTENTION\n")
        assert f"phase:       {PHASE}\n" in text
        assert f"working/work-orders/{dj._LEDGER_DIRNAME}/{PHASE}.json" in text
