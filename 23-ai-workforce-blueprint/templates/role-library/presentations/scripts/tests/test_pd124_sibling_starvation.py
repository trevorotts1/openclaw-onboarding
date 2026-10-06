"""PD-TEST-124 (half 2 of 2) -- SIBLING STARVATION under the per-phase paid cap.

THE DEFECT, MEASURED. P4-COPY is a fan-out phase with 8 units. Its dispatcher
log recorded:

    section-01 : completion_tokens=64000, reasoning_tokens=64000,
                 finish_reason='length'                       (empty output)
    section-02 : PaidBudgetExhausted: paid retry budget exhausted: 3 provider
                 attempts for unchanged approved input (DISPATCH_RETRY_CAP=3)
    section-03 .. section-08 : identical

ONE unit's three failed attempts consumed the entire PHASE-level paid
allowance, and the other SEVEN units were NEVER ATTEMPTED AT ALL. They did not
fail -- they never ran. The phase then quarantined having authored nothing.

THE CAUSE. `paid_attempts` is a single PHASE counter compared against
DISPATCH_RETRY_CAP (=3). A fan-out phase therefore has one three-attempt
allowance shared by every unit, with no per-unit accounting at all: the first
unit to fail repeatedly spends it, and its siblings are starved -- an unfair
scheduler, not a model failure.

WHAT THESE TESTS PIN (all of it scheduling-side; no request constant, no
DeepSeek call function and no reuse rule is touched):

  A. FAIR ADMISSION: the 8-unit phase where ONE unit repeatedly fails -- every
     eligible sibling receives its first paid attempt, and the failing unit is
     capped by its OWN ceiling rather than by draining the phase.
  B. FIRST-ATTEMPT PRIORITY: while any admitted unit has zero attempts, no unit
     may reserve a second or third.
  C. A BOUNDED, EXPLICIT TOTAL: `min(PHASE_TOTAL_PAID_HARD_CAP, units*1 + the
     legacy 3-attempt retry pool)` -- deliberately NOT `units *
     DISPATCH_RETRY_CAP` -- and aggregate spend never exceeds it.
  D. SUCCESSES ARE NEVER REGENERATED, and only failed/invalidated units retry.
  E. ATOMIC, DUPLICATE-SAFE RESERVATIONS: concurrent workers cannot
     double-reserve one unit's attempt, and concurrent reservations for
     distinct units never lose an update.
  F. A RESTART (a fresh read of the ledger, through record_outcome's rebuild)
     preserves successes, settled/in-flight reservations and failure history.
  G. CANNOT-FUND-ALL: more eligible units than the bound can fund -- the first
     `total_cap` in deterministic enumeration order are admitted, the rest are
     recorded by NAME with the reason, and none of them is silently dropped.
  H. THE LEGACY CAP IS NOT WEAKENED: outside a fan-out unit scope (every serial
     phase) the reservation and the gate behave EXACTLY as before, including
     the byte-identical refusal text.
  I. THE REUSE PATH'S REAL PROPERTY (coordinator-verified twice): a LATER
     `failed` row must not shadow an EARLIER `ok` row whose recorded
     `unit_inputs` still match -- that unit is REUSED, not re-paid; and when the
     recorded inputs DO differ it is correctly RE-DISPATCHED. Driven through the
     real `_dispatch_phase_fanout_units` with the transport stubbed.

No test touches the network, a provider, the live run directory or the
installed mirrors. Everything is the real code against a scratch run dir.
"""
from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as dj  # noqa: E402
from presentation_job import fanout  # noqa: E402

PHASE = "P4-COPY"
WORKER = "test-worker"
UNITS = [f"section-{n:02d}" for n in range(1, 9)]      # the measured 8 units
FAILING = UNITS[0]                                      # the measured section-01
# The bound the policy declares for 8 eligible units: 8 first attempts + the
# SAME 3-attempt retry pool. Never 8 * 3 = 24.
# getattr, not attribute access: this file is also run against the PRE-fix
# revision as the negative control, where the policy symbols do not exist yet --
# the missing symbol must surface as a FAILING TEST, never as a collection error.
EXPECTED_TOTAL_CAP = len(UNITS) + getattr(dj, "PHASE_RETRY_POOL_ATTEMPTS",
                                          dj.DISPATCH_RETRY_CAP)


# ---------------------------------------------------------------------------
# Fixtures -- a scratch run dir and the two ledger operations the fan-out path
# performs, driven through the REAL functions.
# ---------------------------------------------------------------------------
def _order_file(run_dir: Path) -> Path:
    return run_dir / "working" / "work-orders" / f"{PHASE}.json"


def _seed(tmp_path: Path, *, units=None) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "working" / "work-orders").mkdir(parents=True)
    (run_dir / "working" / "copy").mkdir(parents=True)
    (run_dir / "state.json").write_text(json.dumps({
        "phases": [{"id": PHASE, "status": "running"}],
    }), encoding="utf-8")
    _order_file(run_dir).write_text(json.dumps({
        "phase_id": PHASE, "produces_artifact": "working/copy/slides_copy.md",
    }), encoding="utf-8")
    if units:
        _declare(run_dir, units)
    return run_dir


def _declare(run_dir: Path, units):
    """Declare the phase's bounded total budget through the real declaration."""
    return dj._declare_phase_paid_budget(run_dir, PHASE,
                                         unit_keys=list(units), worker_id=WORKER)


def _ledger(run_dir: Path) -> dict:
    return dj._read_ledger(run_dir, PHASE)


def _reserve(run_dir: Path, unit: str, *, token: str | None = None,
             allow_reauthor: bool = False) -> None:
    """One unit's pre-transport reservation, exactly as the unit worker makes
    it: inside paid_unit_scope, through the real _reserve_paid_attempt."""
    with dj.paid_unit_scope(unit, token=token, allow_reauthor=allow_reauthor):
        dj._reserve_paid_attempt(run_dir, PHASE, WORKER)


def _attempt(run_dir: Path, unit: str, *, ok: bool,
             token: str | None = None) -> None:
    """One unit's whole paid dispatch: reserve, then settle its outcome."""
    _reserve(run_dir, unit, token=token)
    dj._settle_unit_paid_attempts(
        run_dir, PHASE,
        [(unit, "ok" if ok else "failed",
          [] if ok else ["empty completion"])],
        worker_id=WORKER)


def _fund_all_first_attempts(run_dir: Path, units, *, failing=()) -> list:
    """Give EVERY admitted unit its first paid attempt, in admission order.

    Under first-attempt fairness this is the only order the reservation accepts,
    so the helper is also the fixture that proves the rule: a retry attempted
    before this point would be deferred."""
    charged = []
    for unit in units:
        _attempt(run_dir, unit, ok=(unit not in failing))
        charged.append(unit)
    return charged


def _sweep(run_dir: Path, units, failing, ok_so_far, log):
    """One dispatch sweep, exactly as the fan-out path runs it: declare over
    the units that still need work, then attempt each pending unit once, in
    admission (enumeration) order."""
    pending = [u for u in units if u not in ok_so_far]
    _declare(run_dir, pending)
    for unit in pending:
        try:
            _attempt(run_dir, unit, ok=(unit not in failing))
        except (dj.PaidBudgetExhausted, dj.PaidAttemptDeferred) as exc:
            log.append((unit, type(exc).__name__))
            continue
        log.append((unit, "charged"))
        if unit not in failing:
            ok_so_far.add(unit)


# ---------------------------------------------------------------------------
# A/C. The measured scenario: 8 units, ONE repeatedly failing.
# ---------------------------------------------------------------------------
class TestSiblingStarvationIsFixed:
    def test_one_failing_unit_no_longer_starves_seven_siblings(self, tmp_path):
        """The exact live shape: section-01 fails on every sweep. Before the
        repair its three attempts consumed the whole phase allowance and
        section-02..08 were never attempted. Now every sibling gets its first
        paid attempt, and the failing unit is bounded by its OWN ceiling."""
        run_dir = _seed(tmp_path)
        log: list = []
        ok_so_far: set = set()

        # Four sweeps -- more than the three attempts the live run needed to
        # exhaust the old phase allowance. The failing unit is re-offered on
        # every sweep, which is precisely how it starved its siblings.
        for _ in range(4):
            _sweep(run_dir, UNITS, {FAILING}, ok_so_far, log)

        charged = [u for u, what in log if what == "charged"]
        refused = {u: what for u, what in log if what != "charged"}

        # (1) EVERY sibling received its first paid attempt.
        for sibling in UNITS[1:]:
            assert charged.count(sibling) == 1, (
                f"{sibling} was starved: charged {charged.count(sibling)} "
                f"time(s); log={log}")

        # (2) The failing unit got its three attempts (its own ceiling) and no
        #     more -- it can no longer spend a sibling's budget.
        assert charged.count(FAILING) == dj.DISPATCH_RETRY_CAP, charged
        assert refused.get(FAILING) == "PaidBudgetExhausted", (
            "the failing unit must stop at its OWN cap, not the phase's")

        # (3) Sibling first attempts all precede the failing unit's retries.
        first_sibling = max(charged.index(s) for s in UNITS[1:])
        retries_of_failing = [i for i, u in enumerate(charged) if u == FAILING][1:]
        assert retries_of_failing, "the failing unit never retried"
        assert min(retries_of_failing) > first_sibling, (
            "a retry of the failing unit preceded a sibling's first attempt")

        # (4) Aggregate spend is bounded by the declared total.
        budget = _ledger(run_dir)["phase_paid_budget"]
        assert len(charged) <= budget["total_cap"] == EXPECTED_TOTAL_CAP
        assert _ledger(run_dir)["paid_attempts"] == len(charged)

    def test_a_retry_cannot_preempt_a_siblings_first_attempt(self, tmp_path):
        """The fairness rule itself: a unit with attempts already spent is
        DEFERRED while any admitted sibling still has zero."""
        run_dir = _seed(tmp_path, units=UNITS)
        _attempt(run_dir, FAILING, ok=False)          # one attempt spent
        before = json.dumps(_ledger(run_dir), sort_keys=True)

        with pytest.raises(dj.PaidAttemptDeferred) as refused:
            _reserve(run_dir, FAILING)
        assert "first attempt" in str(refused.value), str(refused.value)
        assert json.dumps(_ledger(run_dir), sort_keys=True) == before, (
            "a deferred retry must not touch the ledger")

        # The sibling owed its first attempt IS admitted, immediately.
        _reserve(run_dir, UNITS[1])
        assert _ledger(run_dir)["unit_paid_attempts"][UNITS[1]] == 1

        # And once every admitted unit has had a first attempt, the retry of
        # the failing unit is admitted again.
        for unit in UNITS[2:]:
            _attempt(run_dir, unit, ok=False)
        _reserve(run_dir, FAILING)
        assert _ledger(run_dir)["unit_paid_attempts"][FAILING] == 2

    def test_only_failed_units_are_retried(self, tmp_path):
        """Requirement 5: a sweep after partial failure retries exactly the
        units that failed -- successes cost nothing."""
        run_dir = _seed(tmp_path, units=UNITS)
        charged = _fund_all_first_attempts(run_dir, UNITS, failing={FAILING})
        assert len(charged) == len(UNITS)

        # Next sweep: only the failed unit is still pending.
        log: list = []
        ok_so_far = set(UNITS[1:])
        _sweep(run_dir, UNITS, {FAILING}, ok_so_far, log)
        assert [u for u, what in log if what == "charged"] == [FAILING]
        # The successes were never even offered a second paid attempt.
        for unit in UNITS[1:]:
            assert _ledger(run_dir)["unit_paid_attempts"][unit] == 1


# ---------------------------------------------------------------------------
# B/C. The declared bound is explicit, bounded and enforced.
# ---------------------------------------------------------------------------
class TestTheBudgetIsBoundedAndExplicit:
    def test_the_total_is_units_plus_the_retry_pool_not_units_times_the_cap(
            self, tmp_path):
        run_dir = _seed(tmp_path)
        decl = _declare(run_dir, UNITS)
        budget = decl["budget"]
        assert budget["total_cap"] == EXPECTED_TOTAL_CAP
        assert budget["total_cap"] == dj._fanout_total_paid_cap(len(UNITS))
        assert budget["total_cap"] != len(UNITS) * dj.DISPATCH_RETRY_CAP, (
            "the total must not be units x DISPATCH_RETRY_CAP")
        assert budget["per_unit_cap"] == dj.DISPATCH_RETRY_CAP
        assert budget["retry_pool"] == dj.PHASE_RETRY_POOL_ATTEMPTS
        assert budget["policy"] == dj.PHASE_PAID_BUDGET_POLICY
        # The declared policy is recorded in the LEDGER, not just in memory.
        assert _ledger(run_dir)["phase_paid_budget"]["total_cap"] == EXPECTED_TOTAL_CAP

    def test_aggregate_spend_stays_within_the_declared_bound(self, tmp_path):
        """Drive every unit at its per-unit cap: the total stops at the declared
        bound, never at units*cap."""
        run_dir = _seed(tmp_path, units=UNITS)
        charged = 0
        for _round in range(dj.DISPATCH_RETRY_CAP):
            for unit in UNITS:
                try:
                    _attempt(run_dir, unit, ok=False)
                except (dj.PaidBudgetExhausted, dj.PaidAttemptDeferred):
                    continue
                charged += 1

        led = _ledger(run_dir)
        assert charged == EXPECTED_TOTAL_CAP, charged
        assert led["paid_attempts"] == EXPECTED_TOTAL_CAP
        assert charged <= led["phase_paid_budget"]["total_cap"]
        assert charged < len(UNITS) * dj.DISPATCH_RETRY_CAP
        # No unit exceeded its own ceiling...
        assert all(v <= dj.DISPATCH_RETRY_CAP
                   for v in led["unit_paid_attempts"].values())
        # ...and the never-reset audit total agrees with the generation count.
        assert led["unit_paid_attempts_lifetime"] == led["unit_paid_attempts"]

    def test_the_bound_is_hard_capped_and_the_arithmetic_is_declared(self):
        assert dj._fanout_total_paid_cap(8) == 11
        assert dj._fanout_total_paid_cap(100) == 103
        assert dj._fanout_total_paid_cap(10_000) == dj.PHASE_TOTAL_PAID_HARD_CAP


# ---------------------------------------------------------------------------
# D. Successes are never regenerated; a failed unit may be retried.
# ---------------------------------------------------------------------------
class TestSuccessesAreNeverRegenerated:
    def test_a_successful_unit_is_not_regenerated_on_a_later_retry(self, tmp_path):
        run_dir = _seed(tmp_path, units=UNITS)
        _attempt(run_dir, UNITS[0], ok=True)
        led_before = _ledger(run_dir)

        with pytest.raises(dj.PaidAttemptDeferred) as refused:
            _reserve(run_dir, UNITS[0])
        assert "already succeeded" in str(refused.value), str(refused.value)
        assert _ledger(run_dir)["paid_attempts"] == led_before["paid_attempts"], (
            "refusing to regenerate a success must cost nothing")

    def test_an_INVALIDATED_success_may_still_be_re_author(self, tmp_path):
        """The other half: PD-TEST-119/120/121's repair path. A unit whose
        success was invalidated (changed inputs, corrupt output, or an operator
        repair receipt that voided the bank) is re-authorable -- 'never
        regenerate a success' must not become 'never repair a broken deck'."""
        run_dir = _seed(tmp_path, units=UNITS)
        # First-attempt fairness still governs: the siblings' first attempts
        # come before ANY unit's second, including an invalidated re-author.
        _fund_all_first_attempts(run_dir, UNITS)
        assert _ledger(run_dir)["unit_outcomes"][UNITS[0]]["status"] == "ok"
        _reserve(run_dir, UNITS[0], allow_reauthor=True)
        assert _ledger(run_dir)["unit_paid_attempts"][UNITS[0]] == 2

    def test_the_dedup_token_makes_a_duplicate_call_a_no_op(self, tmp_path):
        """One logical attempt, reserved twice: the second call is idempotent."""
        run_dir = _seed(tmp_path, units=UNITS)
        _reserve(run_dir, UNITS[0], token="one-logical-attempt")
        _reserve(run_dir, UNITS[0], token="one-logical-attempt")
        led = _ledger(run_dir)
        assert led["unit_paid_attempts"][UNITS[0]] == 1
        assert led["paid_attempts"] == 1
        assert led["reservation_tokens"] == ["one-logical-attempt"]


# ---------------------------------------------------------------------------
# E. Concurrency: atomic, duplicate-safe reservations.
# ---------------------------------------------------------------------------
class TestAtomicReservations:
    def test_concurrent_workers_cannot_duplicate_a_reservation(self, tmp_path):
        """Eight workers racing ONE logical attempt for one unit: exactly one
        paid slot is charged, and no worker sees a torn ledger."""
        run_dir = _seed(tmp_path, units=UNITS)
        outcomes: list = []
        lock = threading.Lock()
        barrier = threading.Barrier(8)
        token = "section-01-attempt-1"

        def worker():
            barrier.wait()
            try:
                _reserve(run_dir, UNITS[0], token=token)
                outcome = "charged"
            except Exception as exc:  # noqa: BLE001 -- any refusal is data
                outcome = type(exc).__name__
            with lock:
                outcomes.append(outcome)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        led = _ledger(run_dir)
        assert led["paid_attempts"] == 1, (outcomes, led["paid_attempts"])
        assert led["unit_paid_attempts"][UNITS[0]] == 1
        assert led["reservation_tokens"] == [token]
        # Idempotent: the duplicate callers were satisfied, not refused.
        assert outcomes.count("charged") == 8, outcomes

    def test_concurrent_units_are_charged_atomically_without_lost_updates(
            self, tmp_path):
        """Eight workers, eight DISTINCT units: every unit is charged exactly
        once and the phase total equals the sum -- a read-modify-write that
        interleaved would lose one."""
        run_dir = _seed(tmp_path, units=UNITS)
        barrier = threading.Barrier(len(UNITS))

        def worker(unit):
            barrier.wait()
            try:
                _reserve(run_dir, unit, token=f"{unit}-attempt-1")
            except Exception:  # noqa: BLE001 -- a refusal would show as a miss
                pass

        threads = [threading.Thread(target=worker, args=(u,)) for u in UNITS]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        led = _ledger(run_dir)
        assert led["paid_attempts"] == len(UNITS)
        assert led["unit_paid_attempts"] == {u: 1 for u in UNITS}

    def test_two_logical_attempts_for_one_unit_cannot_both_reserve(self, tmp_path):
        """A second, DISTINCT logical attempt for a unit whose first attempt is
        still in flight is refused until its owner settles (or is proven gone):
        one unit can never be billed twice for one dispatch."""
        run_dir = _seed(tmp_path, units=UNITS)
        _fund_all_first_attempts(run_dir, UNITS, failing={UNITS[0]})
        _reserve(run_dir, UNITS[0], token="attempt-2")     # in flight, unsettled
        with pytest.raises(dj.PaidAttemptDeferred) as refused:
            _reserve(run_dir, UNITS[0], token="attempt-3")
        assert "in-flight" in str(refused.value), str(refused.value)
        assert _ledger(run_dir)["unit_paid_attempts"][UNITS[0]] == 2

        # Settling releases the unit for a genuine third attempt.
        dj._settle_unit_paid_attempts(
            run_dir, PHASE, [(UNITS[0], "failed", ["empty completion"])],
            worker_id=WORKER)
        _reserve(run_dir, UNITS[0], token="attempt-3")
        assert _ledger(run_dir)["unit_paid_attempts"][UNITS[0]] == 3

    def test_a_dead_owners_reservation_is_taken_over_not_deadlocked(self, tmp_path):
        """The crash case: a reservation left by a process that is gone must not
        lock its unit out forever. The dead pid is never reused by this test."""
        run_dir = _seed(tmp_path, units=UNITS)
        _fund_all_first_attempts(run_dir, UNITS, failing={UNITS[0]})
        _reserve(run_dir, UNITS[0], token="attempt-2")
        led = _ledger(run_dir)
        # Re-point the in-flight reservation at a pid that cannot be alive.
        led["unit_reservations"][UNITS[0]]["pid"] = 999_999_99
        dj._write_ledger(run_dir, PHASE, led)

        _reserve(run_dir, UNITS[0], token="attempt-3")
        after = _ledger(run_dir)
        assert after["unit_paid_attempts"][UNITS[0]] == 3
        assert after["unit_reservations"][UNITS[0]]["token"] == "attempt-3"


# ---------------------------------------------------------------------------
# F. Restart durability.
# ---------------------------------------------------------------------------
class TestRestartDurability:
    def test_a_restart_preserves_successes_reservations_and_failure_history(
            self, tmp_path):
        """Simulated restart: the ledger is re-read from disk and passed through
        record_outcome's rebuild (which is what a restart's first fold does).
        Successes, the in-flight reservation and the failure history must all
        survive -- and a field dropped by the rebuild would erase them."""
        run_dir = _seed(tmp_path, units=UNITS)
        _fund_all_first_attempts(run_dir, UNITS, failing={UNITS[1]})
        _reserve(run_dir, UNITS[1], token="in-flight")  # a retry, never settled

        before = _ledger(run_dir)
        assert before["unit_outcomes"][UNITS[0]]["status"] == "ok"
        assert before["unit_outcomes"][UNITS[1]]["status"] == "failed"
        assert before["unit_reservations"][UNITS[1]]["state"] == "reserved"

        # The restart's own fold.
        dj.record_outcome(run_dir, PHASE, "partial_failure",
                          [f"{UNITS[1]}: empty completion"], worker_id="restarted",
                          order_file=_order_file(run_dir))
        after = _ledger(run_dir)

        assert after["phase_paid_budget"] == before["phase_paid_budget"]
        assert after["unit_admission_order"] == before["unit_admission_order"]
        assert after["unit_paid_attempts"] == before["unit_paid_attempts"]
        assert after["unit_paid_attempts_lifetime"] == before["unit_paid_attempts_lifetime"]
        assert after["unit_outcomes"][UNITS[0]]["status"] == "ok"
        assert after["unit_outcomes"][UNITS[1]]["status"] == "failed"
        assert "empty completion" in after["unit_outcomes"][UNITS[1]]["reasons"][0]
        assert after["unit_reservations"][UNITS[1]]["state"] == "reserved"
        assert after["paid_attempts"] == before["paid_attempts"]
        assert after["reservation_tokens"] == before["reservation_tokens"]

        # ...and the restored state still protects the success, still refuses a
        # second logical attempt while one is in flight, and still treats the
        # RESTARTED re-presentation of that same attempt as the no-op it is.
        with pytest.raises(dj.PaidAttemptDeferred):
            _reserve(run_dir, UNITS[0])
        with pytest.raises(dj.PaidAttemptDeferred) as dup:
            _reserve(run_dir, UNITS[1], token="a-different-logical-attempt")
        assert "in-flight" in str(dup.value), str(dup.value)
        # Same logical attempt, re-presented after the restart: idempotent.
        _reserve(run_dir, UNITS[1], token="in-flight")
        assert _ledger(run_dir)["paid_attempts"] == before["paid_attempts"], (
            "a restarted re-presentation of one attempt must not buy a second "
            "paid slot")


# ---------------------------------------------------------------------------
# G. Cannot fund all units: deterministic admission, recorded reason.
# ---------------------------------------------------------------------------
class TestCannotFundAllUnits:
    def test_a_bound_that_cannot_fund_all_units_admits_in_order_and_says_why(
            self, tmp_path):
        units = [f"slide-{n:03d}" for n in range(1, 201)]     # 200 > hard cap
        run_dir = _seed(tmp_path)
        decl = _declare(run_dir, units)
        budget = decl["budget"]

        assert budget["units_eligible"] == 200
        assert budget["total_cap"] == dj.PHASE_TOTAL_PAID_HARD_CAP
        assert budget["units_admitted_first_attempt"] == dj.PHASE_TOTAL_PAID_HARD_CAP
        assert budget["units_not_admitted"] == 200 - dj.PHASE_TOTAL_PAID_HARD_CAP
        # Deterministic enumeration order, never a race.
        assert decl["admitted"] == units[:dj.PHASE_TOTAL_PAID_HARD_CAP]
        assert sorted(decl["not_admitted"]) == sorted(units[dj.PHASE_TOTAL_PAID_HARD_CAP:])

        led = _ledger(run_dir)
        assert sorted(led["unit_not_admitted"]) == sorted(decl["not_admitted"])
        why = led["unit_not_admitted"][units[-1]]
        assert "did NOT attempt" in why or "NOT attempted" in why, why
        assert "did not fail" in why, why

        # An admitted unit reserves; an un-admitted one is refused BY NAME.
        _reserve(run_dir, units[0])
        with pytest.raises(dj.PaidAttemptDeferred) as refused:
            _reserve(run_dir, units[-1])
        assert units[-1] in str(refused.value)
        assert "not admitted" in str(refused.value)

        # Re-declaring is deterministic...
        again = _declare(run_dir, units)
        assert again["admitted"] == decl["admitted"]
        # ...and never silently changes who was told they could not run.
        assert sorted(again["not_admitted"]) == sorted(decl["not_admitted"])

    def test_the_declared_bound_never_shrinks_within_a_generation(self, tmp_path):
        """A later sweep over FEWER pending units must not shrink the bound an
        earlier sweep already granted -- that would strand the units the retry
        pool is still paying for."""
        run_dir = _seed(tmp_path)
        first = _declare(run_dir, UNITS)
        assert first["budget"]["total_cap"] == EXPECTED_TOTAL_CAP
        later = _declare(run_dir, UNITS[:3])
        assert later["budget"]["total_cap"] == EXPECTED_TOTAL_CAP
        assert later["admitted"] == UNITS[:3]

    def test_a_small_phase_is_fully_funded(self, tmp_path):
        run_dir = _seed(tmp_path)
        decl = _declare(run_dir, UNITS[:2])
        assert decl["budget"]["total_cap"] == 2 + dj.PHASE_RETRY_POOL_ATTEMPTS
        assert decl["not_admitted"] == {}


# ---------------------------------------------------------------------------
# H. The legacy (serial) path is not weakened.
# ---------------------------------------------------------------------------
class TestTheLegacyCapIsNotWeakened:
    def test_outside_a_unit_scope_the_phase_cap_is_unchanged(self, tmp_path):
        """Every serial phase keeps the exact legacy behaviour: three
        reservations, then the byte-identical refusal."""
        run_dir = _seed(tmp_path)
        for _ in range(dj.DISPATCH_RETRY_CAP):
            dj._reserve_paid_attempt(run_dir, PHASE, WORKER)
        assert _ledger(run_dir)["paid_attempts"] == dj.DISPATCH_RETRY_CAP
        with pytest.raises(dj.PaidBudgetExhausted) as refused:
            dj._reserve_paid_attempt(run_dir, PHASE, WORKER)
        assert str(refused.value) == (
            f"paid retry budget exhausted: {dj.DISPATCH_RETRY_CAP} provider "
            f"attempts for unchanged approved input "
            f"(DISPATCH_RETRY_CAP={dj.DISPATCH_RETRY_CAP})")

    def test_an_undeclared_ledger_keeps_the_legacy_gate_refusal(self, tmp_path):
        """should_dispatch's exhausted refusal is unchanged when no fan-out
        budget is declared -- the PD-068/PD-092 contract."""
        run_dir = _seed(tmp_path)
        led = _ledger(run_dir) or {}
        led.update({"phase_id": PHASE, "status": "exhausted",
                    "approved_input_revision": "initial",
                    "paid_attempts": dj.DISPATCH_RETRY_CAP,
                    "generation": 0, "blocked": True,
                    "consecutive": dj.DISPATCH_REPEAT_CEILING})
        dj._write_ledger(run_dir, PHASE, led)

        may, why = dj.should_dispatch(run_dir, PHASE, order_file=_order_file(run_dir))
        assert may is False
        assert why == (
            f"paid retry budget exhausted: {dj.DISPATCH_RETRY_CAP} provider "
            f"attempts for unchanged approved input "
            f"(DISPATCH_RETRY_CAP={dj.DISPATCH_RETRY_CAP})")

    def test_a_declared_phase_is_not_gated_at_the_legacy_three_attempts(
            self, tmp_path):
        """The fix at the GATE: an 8-unit phase that has spent 3 attempts with
        seven units still unfunded must still be dispatched."""
        run_dir = _seed(tmp_path, units=UNITS)
        # The exact shape the live phase parked in: blocked, and the PHASE
        # counter sitting at the legacy three-attempt ceiling while seven of the
        # eight units have never been attempted.
        led = _ledger(run_dir)
        led.update({"blocked": True, "status": "exhausted",
                    "paid_attempts": dj.DISPATCH_RETRY_CAP,
                    "consecutive": dj.DISPATCH_REPEAT_CEILING})
        dj._write_ledger(run_dir, PHASE, led)

        before = json.dumps(_ledger(run_dir), sort_keys=True)
        may, why = dj.should_dispatch(run_dir, PHASE, order_file=_order_file(run_dir))
        assert may is True, why
        assert json.dumps(_ledger(run_dir), sort_keys=True) == before, (
            "the gate must stay read-only")

        # At the declared bound it does refuse -- and says which bound it was.
        led = _ledger(run_dir)
        led["paid_attempts"] = led["phase_paid_budget"]["total_cap"]
        dj._write_ledger(run_dir, PHASE, led)
        may, why = dj.should_dispatch(run_dir, PHASE, order_file=_order_file(run_dir))
        assert may is False
        assert "declared bounded total" in why, why


# ---------------------------------------------------------------------------
# I. The reuse path's real property (coordinator-verified), driven end to end.
# ---------------------------------------------------------------------------
class _FakePhase:
    def __init__(self, pid: str, role: str):
        self.id = pid
        self.owning_role = role
        self.workers = 1
        self.budget_minutes = 5
        self.executor_kind = "agent"


_SECTIONS = (("Hook", 1, 5), ("Teach", 6, 15), ("Offer", 16, 20))
_N_SLIDES = 20


def _section_body(name, lo, hi):
    return "\n".join(f"SLIDE {n}\nHEADLINE for {n}\nNOTE {n}"
                     for n in range(lo, hi + 1))


def _p4_run(tmp_path: Path) -> Path:
    rd = tmp_path / "run"
    for sub in ("copy", "research", "work-orders"):
        (rd / "working" / sub).mkdir(parents=True)
    slots = [{"ordinal": n, "arc": name}
             for name, lo, hi in _SECTIONS for n in range(lo, hi + 1)]
    (rd / "working" / "copy" / "arc_allocation.json").write_text(json.dumps({"slots": slots}))
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps({"client": "t"}))
    (rd / "working" / "copy" / "priority_shift_spec.json").write_text(json.dumps({"p": 1}))
    (rd / "working" / "copy" / "sp_intake.json").write_text(json.dumps({"s": 1}))
    (rd / "working" / "research" / "research_map.json").write_text(json.dumps({"m": 1}))
    (rd / "working" / "copy" / "slides.json").write_text(
        json.dumps({"slides": [{"ordinal": n} for n in range(1, _N_SLIDES + 1)]}))
    return rd


def _dept(tmp_path: Path, role: str) -> Path:
    dept = tmp_path / "dept"
    d = dept / role
    d.mkdir(parents=True)
    (d / "how-to.md").write_text("SOP")
    return dept


@pytest.fixture()
def p4_env(tmp_path, monkeypatch):
    rd = _p4_run(tmp_path)
    dept = _dept(tmp_path, "slide-copywriter")
    calls: list = []

    def ok_dispatch(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        calls.append(user_prompt)
        for name, lo, hi in _SECTIONS:
            if repr(name) in user_prompt and "AUTHORS EXACTLY ONE SECTION" in user_prompt:
                return (_section_body(name, lo, hi), {"request_id": "stub"},
                        {"provider": "stub", "model": "stub-1"})
        raise AssertionError("unit prompt lost its one-scope instruction")

    def failing_teach(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        calls.append(user_prompt)
        if repr("Teach") in user_prompt and "AUTHORS EXACTLY ONE SECTION" in user_prompt:
            raise RuntimeError("stub transport failure mid-deck")
        for name, lo, hi in _SECTIONS:
            if repr(name) in user_prompt and "AUTHORS EXACTLY ONE SECTION" in user_prompt:
                return (_section_body(name, lo, hi), {"request_id": "stub"},
                        {"provider": "stub", "model": "stub-1"})
        raise AssertionError("unit prompt lost its one-scope instruction")

    monkeypatch.setattr(dj, "_verify", lambda pid, rdir: (True, []))
    monkeypatch.setattr(dj, "dispatch_complete", ok_dispatch)
    return {"rd": rd, "dept": dept, "calls": calls,
            "use_failing_teach": lambda: monkeypatch.setattr(
                dj, "dispatch_complete", failing_teach),
            "use_ok_dispatch": lambda: monkeypatch.setattr(
                dj, "dispatch_complete", ok_dispatch),
            "order": {"owning_role": "slide-copywriter",
                      "produces_artifact": "working/copy/slides_copy.md"},
            "spec": fanout.parse_fanout_field({"by": "section", "max_units": 5}),
            "phase": _FakePhase("P4-COPY", "slide-copywriter"),
            "target": rd / "working" / "copy" / "slides_copy.md",
            "ledger": rd / "working" / "work-orders" / dj._LEDGER_DIRNAME / "P4-COPY.json"}


def _dispatch(env):
    return dj._dispatch_phase_fanout_units(
        env["rd"], env["order"], dept_root=env["dept"], phase_obj=env["phase"],
        worker_id="test", spec=env["spec"],
        patterns=["working/copy/slides_copy.md"], target=env["target"],
        prior_reasons=[])


def _ledger_rows(env):
    return dj._read_units_ledger(env["rd"], "P4-COPY")


def _drop_unit_store(env):
    """Remove the per-unit state store, leaving the units LEDGER and the scratch
    outputs in place.

    This is the documented absent-store case (unit_store.load_state: "the caller
    then admits everything ... a corrupt ledger must never skip work"). It is
    also what isolates the property under test: a store record is the fan-out's
    own most recent decision about a unit and takes precedence over the ledger,
    so with no store record the ONLY evidence about whether a unit's output is
    still good is the append-only units ledger plus the bytes on disk."""
    (env["rd"] / "working" / "fanout" / "_units" / "P4-COPY"
     / "state.json").unlink(missing_ok=True)


def _append_failed_row_for(env, unit, *, unit_inputs="same"):
    """Append the history shape a LATER failed attempt leaves behind: a
    `failed` row for a unit that already has an `ok` row, naming the same
    scratch (`reuse_key` is deterministic per unit) and the input snapshot of
    the attempt that failed.

    `unit_inputs="same"` models a provider failure under UNCHANGED inputs -- the
    snapshot recorded alongside the failure is identical to the earlier success's
    -- which is the live shape: a later failure appends a failed row without
    touching the inputs the good output was produced from.

    NOTE (measured while writing this test): a contract input's digest covers
    (path, size, MTIME_NS, content sha256) -- `_hash_contract_entry`. So rewriting
    even byte-identical input content moves the hash. That is why "the earlier ok
    row still matches" has to be modelled with an unchanged input, and why a
    genuine input change always reads as one."""
    rows = [r for r in _ledger_rows(env) if r["unit"] == unit]
    src = rows[-1]
    fanout.append_unit_ledger_row(env["rd"], "P4-COPY", {
        "unit": unit, "status": "failed", "attempts": 1, "target": None,
        "reasons": ["empty completion"], "reuse_key": src["reuse_key"],
        "unit_inputs": src["unit_inputs"] if unit_inputs == "same" else unit_inputs,
    })
    return src["unit_inputs"]


class TestReuseHistoryIsNotShadowedByALaterFailure:
    def test_a_failed_head_row_does_not_shadow_an_earlier_valid_ok_row(
            self, p4_env):
        """(a) The units ledger is APPEND-ONLY. The latest row for a unit says
        `failed`, but an earlier `ok` row records the SAME input snapshot and its
        scratch still validates against the current inputs -- so the unit is
        REUSED and NOT re-paid."""
        assert _dispatch(p4_env).status == "ok"
        assert len(p4_env["calls"]) == 3
        snapshot = _append_failed_row_for(p4_env, "section-02")
        rows = [r for r in _ledger_rows(p4_env) if r["unit"] == "section-02"]
        assert [r["status"] for r in rows] == ["ok", "failed"], rows
        assert rows[0]["unit_inputs"] == rows[-1]["unit_inputs"] == snapshot

        _drop_unit_store(p4_env)
        p4_env["calls"].clear()
        res = _dispatch(p4_env)
        assert res.status == "ok", res.reasons
        assert p4_env["calls"] == [], (
            "a unit whose earlier ok row matches the current inputs and whose "
            "scratch validates must be REUSED despite a failed head row; paid "
            f"{len(p4_env['calls'])} call(s)")

    def test_recorded_inputs_that_differ_are_still_re_dispatched(self, p4_env):
        """(b) The same history, but the inputs genuinely changed: the ok row's
        recorded snapshot no longer matches, so the stale success is NOT reused
        and the affected unit RE-RUNS. The reuse path must never paper over a
        real input change."""
        assert _dispatch(p4_env).status == "ok"
        stale = _append_failed_row_for(p4_env, "section-02")
        _drop_unit_store(p4_env)

        # A whole-phase input the sections consume changes: the recorded
        # snapshot is now stale.
        (p4_env["rd"] / "working" / "copy" / "intake.json").write_text(
            json.dumps({"client": "t2"}))
        p4_env["calls"].clear()
        res = _dispatch(p4_env)
        assert res.status == "ok", res.reasons
        assert any("Teach" in c for c in p4_env["calls"]), (
            "the changed-input unit must be re-dispatched, not reused")
        assert len(p4_env["calls"]) == 3
        # ...and the stale snapshot really was the difference.
        assert stale["working/copy/intake.json"] != dj.unit_input_hashes(
            p4_env["rd"], "P4-COPY")["working/copy/intake.json"]

    def test_a_failed_rows_matching_snapshot_does_not_license_a_stale_ok_row(
            self, p4_env):
        """The guard on (a): when the snapshot that matches the CURRENT inputs is
        the FAILED row's while the ok row was produced against different inputs,
        nothing licenses reuse of the older output -- only the affected unit
        re-runs, and its siblings' fresh ok rows are still reused for free."""
        assert _dispatch(p4_env).status == "ok"

        # The input changes and the re-attempts happen under the new input; the
        # Teach unit's re-attempt fails, so its head row is `failed` with the NEW
        # snapshot while its ok row still records the OLD one.
        (p4_env["rd"] / "working" / "copy" / "intake.json").write_text(
            json.dumps({"client": "t2"}))
        p4_env["use_failing_teach"]()
        assert _dispatch(p4_env).status == "partial_failure"
        teach = [r for r in _ledger_rows(p4_env) if r["unit"] == "section-02"]
        assert [r["status"] for r in teach] == ["ok", "failed"]
        assert teach[0]["unit_inputs"] != teach[-1]["unit_inputs"]

        _drop_unit_store(p4_env)
        p4_env["calls"].clear()
        p4_env["use_ok_dispatch"]()
        res = _dispatch(p4_env)
        assert res.status == "ok", res.reasons
        assert any("Teach" in c for c in p4_env["calls"]), (
            "a stale ok row must not be reused just because a later failed row's "
            "snapshot matches")
        assert len(p4_env["calls"]) == 1, (
            "only the affected unit re-runs; its siblings are reused for free")


def test_the_history_shape_the_reuse_pins_depend_on(p4_env):
    """The fixture's own floor: the append really does produce ok-then-failed for
    one unit, with the earlier row still naming a validating scratch and the
    input snapshot its output was produced against."""
    assert _dispatch(p4_env).status == "ok"
    _append_failed_row_for(p4_env, "section-02")
    rows = [r for r in _ledger_rows(p4_env) if r["unit"] == "section-02"]
    assert [r["status"] for r in rows] == ["ok", "failed"]
    scratch = p4_env["rd"] / rows[0]["reuse_key"]
    assert scratch.is_file() and scratch.read_text(encoding="utf-8").strip()
