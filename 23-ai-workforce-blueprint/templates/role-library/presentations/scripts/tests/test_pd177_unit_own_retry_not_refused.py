"""PD-TEST-177 -- a unit's own in-run retry must not be refused by its OWN
in-flight paid reservation.

THE DEFECT, measured on the shipped code (main 850b81034, which is also the
installed runtime).

`_reserve_paid_attempt`'s double-reserve guard refuses a second attempt for a
unit while the unit already holds a `reserved` row -- unless the row's owner
process is provably gone. `_reservation_owner_is_gone()` answers False for
`pid == os.getpid()` (dispatcher.py, fail-closed), so a process's OWN row is
treated as live. But a unit's retries run INSIDE the worker
(`parallel_prompt_worker._execute_slide`'s `while attempt < RETRY_CAP` loop),
and the rows are settled only AFTER the whole wave returns
(`_settle_unit_paid_attempts`, called by `_dispatch_prompt_phase_parallel`).
Each attempt opens its own `paid_unit_scope`, so it carries a DIFFERENT token
and never takes the same-token idempotent early return.

Measured by an independent delta review, driving the real wave with only
`urllib.request.urlopen` stubbed -- identical 1-slide wave whose transport
raises HTTP 500:

    pristine main : 3 transport calls, paid_attempts 3, class server_error x3
    head          : 1 transport call,  paid_attempts 1, class budget_deferred
                    (server_error, then budget_deferred x2)

reproduced with NO declaration at all (`phase_paid_budget: null`, paid 1 vs 3),
which rules the declaration out as the cause. So ONE transient 5xx/429/timeout
lost the slide for the whole wave, and the durable record named the local
refusal instead of the provider fault -- the same masking class as PD-TEST-162.

WHY THIS FILE EXISTS AT ALL: the PD-TEST-161 test that covers neighbouring
behaviour settles the batch MANUALLY and never drives the wave, so it cannot
observe that attempts 2-3 happen BEFORE the settle. These tests pin the
property at the seam the worker actually calls, one scope entry per ATTEMPT.

WHAT THESE TESTS PIN
  * the same thread's own next attempt for the same unit is ALLOWED, and is
    charged (paid_attempts increments) -- it is a retry, not a free re-roll;
  * a DIFFERENT thread in the same process still REFUSES (the guard's real job
    is stopping two concurrent attempts for one unit, and the wave runs units
    as in-process threads);
  * a row written before this change (no `thread` field) still REFUSES, so the
    fix is fail-safe on any already-reserved row;
  * the per-unit ceiling still binds: the fix restores the retry, it does not
    remove the bound.
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import List

import pytest  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as dj  # noqa: E402

PHASE = "P4-PROMPT"
WORKER = "dispatcher-test-177"
UNIT = "slide-03"


def _run_dir(tmp_path: Path, *, declare: bool) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "working" / "work-orders").mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps({
        "phases": [{"id": PHASE, "status": "running"}]}), encoding="utf-8")
    if declare:
        dj._declare_phase_paid_budget(run_dir, PHASE,
                                      unit_keys=[UNIT], worker_id=WORKER)
    return run_dir


def _attempt(run_dir: Path) -> str:
    """One attempt for UNIT, exactly as the worker makes it: a FRESH scope entry
    (hence a fresh token) per attempt, through the real _reserve_paid_attempt."""
    try:
        with dj.paid_unit_scope(UNIT):
            dj._reserve_paid_attempt(run_dir, PHASE, WORKER)
        return "ok"
    except dj.PaidBudgetExhausted:
        return "budget_exhausted"
    except dj.PaidAttemptDeferred:
        return "budget_deferred"


def _paid(run_dir: Path) -> int:
    return int(dj._read_ledger(run_dir, PHASE).get("paid_attempts") or 0)


# ---------------------------------------------------------------------------
# The regression itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("declare", [True, False])
def test_the_same_threads_next_attempt_is_allowed_and_charged(tmp_path, declare):
    """THE REGRESSION. The review reproduced it with NO declaration too
    (`phase_paid_budget: null`, paid 1 vs 3), so both shapes are pinned."""
    run_dir = _run_dir(tmp_path, declare=declare)

    assert _attempt(run_dir) == "ok"
    assert _paid(run_dir) == 1

    # The retry the worker would make for the SAME unit, in the SAME thread.
    assert _attempt(run_dir) == "ok", (
        "the unit's own retry was refused by its own in-flight reservation -- "
        "this is PD-TEST-177: the previous attempt ENDED (a worker task runs "
        "one unit sequentially), and the row is only settled after the whole "
        "wave returns, so refusing here disables RETRY_CAP entirely and "
        "reports `budget_deferred` instead of the real provider fault")
    assert _paid(run_dir) == 2, (
        "the retry must be CHARGED, not waved through as an idempotent repeat -- "
        "otherwise the per-unit ceiling could never bind")


def test_the_full_retry_ceiling_is_now_reachable(tmp_path):
    """Before the fix only ONE provider call could ever happen per unit per
    wave, so DISPATCH_RETRY_CAP=3 was unreachable for transient faults."""
    run_dir = _run_dir(tmp_path, declare=True)
    outcomes = [_attempt(run_dir) for _ in range(dj.DISPATCH_RETRY_CAP)]
    assert outcomes == ["ok"] * dj.DISPATCH_RETRY_CAP, outcomes
    assert _paid(run_dir) == dj.DISPATCH_RETRY_CAP
    # ...and the ceiling still STOPS the next one.
    assert _attempt(run_dir) == "budget_exhausted"


# ---------------------------------------------------------------------------
# The guard the fix must NOT weaken
# ---------------------------------------------------------------------------

def test_a_different_thread_still_refuses(tmp_path):
    """The guard's real job: two CONCURRENT attempts for one unit. The wave runs
    units as in-process threads, so a different thread in this same process is
    precisely the case that must keep refusing."""
    run_dir = _run_dir(tmp_path, declare=True)
    assert _attempt(run_dir) == "ok"

    seen: List[str] = []

    def _other() -> None:
        seen.append(_attempt(run_dir))

    t = threading.Thread(target=_other)
    t.start()
    t.join()

    assert seen == ["budget_deferred"], (
        "a DIFFERENT thread was allowed to double-reserve one unit's attempt -- "
        "the PD-TEST-177 fix must key on this thread's own previous attempt, "
        f"never on the process alone. Got: {seen}")
    assert _paid(run_dir) == 1, "a refused attempt must never be charged"


def test_a_row_without_a_thread_still_refuses(tmp_path):
    """Fail-safe on rows written before this change: no `thread` field means we
    cannot prove the row is our own finished attempt, so it must still refuse."""
    run_dir = _run_dir(tmp_path, declare=True)
    assert _attempt(run_dir) == "ok"

    led = dj._read_ledger(run_dir, PHASE)
    rows = led.get("unit_reservations") or {}
    assert rows.get(UNIT), "expected a reservation row for the unit"
    rows[UNIT].pop("thread", None)          # simulate a pre-PD-TEST-177 row
    dj._write_ledger(run_dir, PHASE, led)   # noqa: SLF001 -- test seam only

    assert _attempt(run_dir) == "budget_deferred", (
        "a reservation row with no recorded thread was treated as our own "
        "finished attempt -- the fix must fail CLOSED on rows it cannot prove")
