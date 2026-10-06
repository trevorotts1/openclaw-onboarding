"""PD-TEST-179 -- a unit's own retry is allowed because NOTHING IS IN FLIGHT,
not because a thread was recognised.

HISTORY, because this file replaced a wrong one. PD-TEST-177 correctly
diagnosed that a unit's in-run retry was refused by its OWN attempt-1
reservation, and shipped a fix that relaxed the double-reserve guard to accept
any later reservation from the same `(pid, thread)`. That fix was measured
working -- and it REPEALED the guarantee the guard exists for: it admitted a
genuinely in-flight second attempt, breaking
`tests/test_pd124_sibling_starvation.py` (24 passed -> 2 failed / 22 passed on
main). The tests in the old file asserted THAT mechanism, so they could not see
the harm: they drove `_reserve_paid_attempt` directly and demanded that an
in-flight reservation be bypassed, which is precisely what must not happen.

THE REAL FIX is in the worker, not the guard: `parallel_prompt_worker.
_execute_slide` now SETTLES the attempt that just ended before starting the
next one, so at the moment of a retry the unit holds no in-flight reservation
and the guard admits it on its own unchanged terms.

WHAT THESE TESTS PIN, all through the real seam:
  * an UNSETTLED reservation still REFUSES a second attempt for the same unit
    -- the PD-TEST-124 guarantee, intact;
  * once that attempt is SETTLED, the same unit's retry is ALLOWED and is
    CHARGED;
  * the per-unit ceiling still binds;
  * settling never refunds or hides spend.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as dj  # noqa: E402

PHASE = "P4-PROMPT"
WORKER = "dispatcher-test-179"
UNIT = "slide-03"


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "working" / "work-orders").mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps({
        "phases": [{"id": PHASE, "status": "running"}]}), encoding="utf-8")
    dj._declare_phase_paid_budget(run_dir, PHASE, unit_keys=[UNIT], worker_id=WORKER)
    return run_dir


def _attempt(run_dir: Path) -> str:
    """One attempt for UNIT through the REAL seam: a fresh scope entry (hence a
    fresh logical token) per attempt, exactly as the worker makes it."""
    try:
        with dj.paid_unit_scope(UNIT):
            dj._reserve_paid_attempt(run_dir, PHASE, WORKER)
        return "ok"
    except dj.PaidBudgetExhausted:
        return "budget_exhausted"
    except dj.PaidAttemptDeferred:
        return "budget_deferred"


def _settle(run_dir: Path, status: str = "failed") -> None:
    """Exactly what _execute_slide now does between attempts."""
    dj._settle_unit_paid_attempts(run_dir, PHASE, [(UNIT, status, [])],
                                  worker_id=WORKER)


def _paid(run_dir: Path) -> int:
    return int(dj._read_ledger(run_dir, PHASE).get("paid_attempts") or 0)


# ---------------------------------------------------------------------------
# The guarantee that must NOT be weakened (this is what the old file got wrong)
# ---------------------------------------------------------------------------

def test_an_in_flight_reservation_still_refuses_a_second_attempt(tmp_path):
    """THE PD-TEST-124 CONTRACT. A second logical attempt for a unit whose
    previous attempt has NOT been settled must be refused -- that is the whole
    point of the guard, and the thread-identity fix repealed it."""
    run_dir = _run_dir(tmp_path)
    assert _attempt(run_dir) == "ok"
    assert _paid(run_dir) == 1

    assert _attempt(run_dir) == "budget_deferred", (
        "a second attempt was admitted while the unit still held an IN-FLIGHT "
        "reservation -- the double-reserve guarantee is broken")
    assert _paid(run_dir) == 1, "a refused attempt must never be charged"


# ---------------------------------------------------------------------------
# The retry the worker now legitimately gets
# ---------------------------------------------------------------------------

def test_after_the_attempt_is_settled_the_retry_is_allowed_and_charged(tmp_path):
    """The mechanism: settling between attempts is what lets the retry through,
    on the guard's own unchanged terms."""
    run_dir = _run_dir(tmp_path)
    assert _attempt(run_dir) == "ok"
    _settle(run_dir)

    assert _attempt(run_dir) == "ok", (
        "the unit's retry was refused even though its previous attempt had been "
        "SETTLED -- nothing was in flight, so the guard should admit it")
    assert _paid(run_dir) == 2, (
        "the retry must be CHARGED, not waved through as an idempotent repeat")


def test_the_full_retry_ceiling_is_reachable_and_then_stops(tmp_path):
    """Before the fix only ONE provider call could happen per unit per wave, so
    DISPATCH_RETRY_CAP was unreachable for transient faults."""
    run_dir = _run_dir(tmp_path)
    outcomes = []
    for _ in range(dj.DISPATCH_RETRY_CAP):
        outcomes.append(_attempt(run_dir))
        if outcomes[-1] == "ok":
            _settle(run_dir)
    assert outcomes == ["ok"] * dj.DISPATCH_RETRY_CAP, outcomes
    assert _paid(run_dir) == dj.DISPATCH_RETRY_CAP
    # ...and the ceiling still STOPS the next one, settled or not.
    assert _attempt(run_dir) == "budget_exhausted"


def test_settling_does_not_bypass_the_charged_count(tmp_path):
    """Settling frees the IN-FLIGHT slot; it must never refund or hide spend."""
    run_dir = _run_dir(tmp_path)
    assert _attempt(run_dir) == "ok"
    before = _paid(run_dir)
    _settle(run_dir)
    assert _paid(run_dir) == before, "settling changed the charged count"
    assert _attempt(run_dir) == "ok"
    assert _paid(run_dir) == before + 1
