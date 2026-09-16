"""PD-TEST-161 / PD-TEST-162 -- the PROMPT fan-out must be funded like the copy one.

THE DEFECTS, measured on run pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4.

PD-TEST-124 gave fan-out phases a declared, bounded, PER-UNIT paid budget with
first-attempt fairness -- but only the COPY fan-out ever used it: `paid_unit_scope`
is referenced in exactly ONE production place (`dispatcher._dispatch_phase_fanout_units`).
The PARALLEL PROMPT fan-out calls `dispatcher.dispatch_complete` directly, so its
reservations fell through to the LEGACY phase-level clause (`paid >=
DISPATCH_RETRY_CAP`, i.e. 3). An 8-slide prompt wave therefore had 8 units racing
for 3 attempts. Measured: slides 02-06 failed at attempt 1 with ZERO verification
codes at the SAME SECOND (13:07:55) -- they never reached a provider, they lost the
reservation race -- while 01/07/08 got real attempts. The ledger ended
`paid_attempts: 3`, `status: exhausted`, `failed_count: 8`, `missing_ordinals: [1..8]`.

PD-TEST-162 is why that was INVISIBLE. `parallel_prompt_worker._classify` ended in a
deliberate catch-all ("everything unknown is non-retryable so garbage never consumes
the provider budget"), and `PaidBudgetExhausted` / `PaidAttemptDeferred` derive from
`DeepSeekCallError(RuntimeError)` -- not ValueError/KeyError/TypeError, and carrying
no 401/403/429/5xx/timeout marker -- so a LOCAL SCHEDULING event was reported as a
PROVIDER fault, non-retryable:

    _classify(PaidBudgetExhausted(...))  ->  ('provider_error', False)

WHAT THESE TESTS PIN
  * all 8 slides of a prompt wave get a FIRST attempt under a declared budget,
    driven through the REAL `_reserve_paid_attempt` seam;
  * the legacy behaviour is preserved when nothing is declared (so no serial or
    undeclared path changes);
  * budget exhaustion/deferral classify as SCHEDULING and RETRYABLE, while genuine
    provider faults and auth failures keep their existing classes;
  * the declaration is a no-op for the budget already granted (monotonic), so a
    re-dispatch over fewer slides cannot shrink it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from presentation_job import dispatcher as dj  # noqa: E402
from presentation_job import parallel_prompt_worker as ppw  # noqa: E402

PHASE = "P4-PROMPT"
WORKER = "dispatcher-test-161"
SLIDES: List[str] = ["slide-%02d" % i for i in range(1, 9)]  # 8 slides, like the live wave


def _run_dir(tmp_path: Path, *, declare: bool) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "working" / "work-orders").mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps({
        "phases": [{"id": PHASE, "status": "running"}]}), encoding="utf-8")
    if declare:
        dj._declare_phase_paid_budget(run_dir, PHASE,
                                      unit_keys=list(SLIDES), worker_id=WORKER)
    return run_dir


def _reserve(run_dir: Path, unit: str) -> str:
    """One slide's pre-transport reservation, exactly as the worker makes it:
    one scope entry per ATTEMPT, through the real _reserve_paid_attempt."""
    try:
        with dj.paid_unit_scope(unit):
            dj._reserve_paid_attempt(run_dir, PHASE, WORKER)
        return "ok"
    except dj.PaidBudgetExhausted:
        return "budget_exhausted"
    except dj.PaidAttemptDeferred:
        return "budget_deferred"


# ---------------------------------------------------------------------------
# PD-TEST-161 -- fairness
# ---------------------------------------------------------------------------

def test_every_slide_gets_a_first_attempt_under_a_declared_budget(tmp_path):
    """The live defect: 5 of 8 slides never reached a provider."""
    run_dir = _run_dir(tmp_path, declare=True)
    outcomes = {slide: _reserve(run_dir, slide) for slide in SLIDES}

    starved = sorted(s for s, o in outcomes.items() if o != "ok")
    assert not starved, (
        f"slides starved of their FIRST paid attempt: {starved} (outcomes "
        f"{outcomes}). The prompt wave must fund one first attempt per slide, "
        "exactly as the copy fan-out has since PD-TEST-124.")

    led = dj._read_ledger(run_dir, PHASE)
    assert led.get("paid_attempts") == len(SLIDES), led.get("paid_attempts")
    assert led.get("phase_paid_budget", {}).get("total_cap") >= len(SLIDES), (
        "the declared bound must be able to fund every slide")


def test_the_legacy_cap_still_governs_when_nothing_is_declared(tmp_path):
    """The negative control, and the no-regression guarantee for every other
    path: undeclared, the phase-level cap of DISPATCH_RETRY_CAP still binds."""
    run_dir = _run_dir(tmp_path, declare=False)
    outcomes = [ _reserve(run_dir, slide) for slide in SLIDES ]
    ok = [o for o in outcomes if o == "ok"]

    assert len(ok) == dj.DISPATCH_RETRY_CAP, (
        f"undeclared reservations should stop at the legacy cap "
        f"{dj.DISPATCH_RETRY_CAP}; got {len(ok)} ({outcomes})")
    assert set(outcomes) - {"ok"} == {"budget_exhausted"}, (
        "past the legacy cap the refusal must be PaidBudgetExhausted")


def test_a_REFUSED_reservation_costs_nothing_so_retrying_cannot_burn_calls(tmp_path):
    """The safety property behind marking budget errors RETRYABLE.

    `_execute_slide` retries up to RETRY_CAP times, so making a budget error
    retryable is only safe if a REFUSED reservation is free. It is: the refusal
    happens in `_reserve_paid_attempt`, BEFORE any transport call, so the phase
    counter does not move. Measured here by exhausting the legacy cap and then
    retrying a starved unit three times."""
    run_dir = _run_dir(tmp_path, declare=False)
    for slide in SLIDES:
        _reserve(run_dir, slide)                      # spend the legacy cap
    spent = dj._read_ledger(run_dir, PHASE)["paid_attempts"]
    assert spent == dj.DISPATCH_RETRY_CAP, spent

    retries = [_reserve(run_dir, "slide-04") for _ in range(3)]
    assert retries == ["budget_exhausted"] * 3, retries
    assert dj._read_ledger(run_dir, PHASE)["paid_attempts"] == spent, (
        "a refused reservation must not consume a paid attempt -- otherwise "
        "RETRY_CAP retries of a budget error would burn the very budget they "
        "are waiting for")


def test_a_budget_cannot_be_shrunk_by_a_later_narrower_declaration(tmp_path):
    """Monotonic within a generation: a re-dispatch over fewer slides must not
    strand slides the pool is still paying for."""
    run_dir = _run_dir(tmp_path, declare=True)
    before = dj._read_ledger(run_dir, PHASE)["phase_paid_budget"]["total_cap"]
    dj._declare_phase_paid_budget(run_dir, PHASE,
                                  unit_keys=["slide-01"], worker_id=WORKER)
    after = dj._read_ledger(run_dir, PHASE)["phase_paid_budget"]["total_cap"]
    assert after >= before, f"declared bound shrank {before} -> {after}"


# ---------------------------------------------------------------------------
# PD-TEST-162 -- a scheduling event is not a provider fault
# ---------------------------------------------------------------------------

def test_budget_exhaustion_classifies_as_scheduling_and_is_retryable():
    cls, retryable = ppw._classify(
        dj.PaidBudgetExhausted("paid retry budget exhausted: 3 provider attempts"))
    assert cls == "budget_exhausted", cls
    assert retryable is True, (
        "budget exhaustion must be RETRYABLE -- the unit should be deferred "
        "until budget exists, not abandoned as if the provider had failed")


def test_budget_deferral_classifies_as_scheduling_and_is_retryable():
    cls, retryable = ppw._classify(
        dj.PaidAttemptDeferred("unit slide-03 retry budget exhausted"))
    assert cls == "budget_deferred", cls
    assert retryable is True


def test_genuine_provider_and_auth_faults_keep_their_classes():
    """The catch-all must still catch. This fix narrows ONE type, it does not
    loosen the classifier."""
    class Boom(RuntimeError):
        pass

    assert ppw._classify(Boom("something odd")) == ("provider_error", False)
    assert ppw._classify(RuntimeError("HTTP 401 (permanent): Unauthorized"))[0] == "auth_error"
    assert ppw._classify(RuntimeError("HTTP 429 too many requests"))[0] == "rate_limited"
    assert ppw._classify(RuntimeError("HTTP 503 server error"))[0] == "server_error"
    assert ppw._classify(TimeoutError("timed out"))[0] == "timeout"
    assert ppw._classify(ValueError("bad shape"))[0] == "verify_failed"


def test_the_worker_enters_a_unit_scope_per_attempt():
    """Structural pin: the per-attempt scope is what makes the accounting work,
    and deleting it would otherwise be silent."""
    import inspect
    src = inspect.getsource(ppw._execute_slide)
    assert "paid_unit_scope(slide_id)" in src, (
        "the prompt worker must bind each ATTEMPT to its slide's unit key, or "
        "its reservations fall back to the legacy per-phase cap (PD-TEST-161)")


def test_the_dispatcher_declares_the_budget_before_the_wave():
    """The scope alone is not enough: `_effective_phase_paid_cap` returns the
    LEGACY cap unless something declared a bound, so the declaration is the half
    that actually funds the wave. Pin both halves."""
    import inspect
    src = inspect.getsource(dj._dispatch_prompt_phase_parallel)
    assert "_declare_phase_paid_budget(" in src, (
        "the prompt wave must DECLARE its bounded total before any paid call, or "
        "every slide's first attempt competes for the legacy 3-attempt cap")
    assert "slide_id" in src and "unit_keys=_unit_keys" in src, (
        "the declaration must key on the slides' own unit ids: build the keys "
        "from each slide's `slide_id` and pass them as `unit_keys`")
    # The declaration must precede the wave, not follow it.
    assert src.index("_declare_phase_paid_budget(") < src.index("run_worker("), (
        "the budget must be declared BEFORE the wave runs -- a bound declared "
        "afterwards funds nothing")
    # ...and it must stay fail-soft, recording which path was taken.
    assert "paid_budget_declaration_failed" in src, (
        "a declaration failure must be recorded, never silent")
