#!/usr/bin/env python3
"""PD-TEST-095 -- the backoff must SATURATE, never overflow.

THE DEFECT
----------
`_backoff_delay_s(repeat)` computed

    min(DISPATCH_BACKOFF_CAP_S,
        DISPATCH_BACKOFF_BASE_S * (DISPATCH_BACKOFF_MULTIPLIER ** (repeat - 1)))

The power is evaluated BEFORE `min()` can clamp it, so it overflows float range
before the cap is ever applied. At exponent 1024 -- i.e. `repeat == 1025` --

    2.0 ** 1024  ->  OverflowError(34, 'Result too large')

`repeat` is NOT bounded by DISPATCH_REPEAT_CEILING. A work order that LINGERS on a
phase whose status stopped changing is re-folded on every sweep tick, so
`consecutive` climbs without limit: on the live run
`pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4` two phases had reached
`consecutive == 1025` (P-0.5-RESEARCH, P0A-INTAKE), with observations in the
1000s.

WHY IT IS A TOTAL STALL, NOT A SLOW BACKOFF
-------------------------------------------
`record_outcome` computes `delay` BEFORE it writes the ledger, so the raise aborts
the fold and `consecutive` can never advance past 1025. And the exception escapes
`sweep_run_dir`, whose caller catches it per-tick:

    except Exception as exc:
        print(f"[dispatcher {worker_id}] sweep error: {exc!r}")

so the ENTIRE sweep is abandoned and NO phase in the run is dispatched again.
Measured live: 271 consecutive `sweep error: OverflowError(34, 'Result too large')`
lines, `active_units: 0`, `last_claim_phase: null`, and a freshly issued P4-COPY
repair receipt that was never consumed -- because the dispatcher could no longer
reach any phase at all. Reproduced on a copy of the live run:

    record_outcome(..., "P-0.5-RESEARCH") ->
      dispatcher.py:8063  delay = _backoff_delay_s(consecutive - 1)
      dispatcher.py:7975  DISPATCH_BACKOFF_BASE_S * (MULT ** (repeat - 1))
      OverflowError: (34, 'Result too large')
    consecutive AFTER = 1025   # unchanged: the fold never wrote

THE FIX
-------
Multiply in a bounded loop and stop as soon as the cap is reached. That is exactly
equivalent to `min(cap, base * mult**exp)` for every value the old expression could
return, and it cannot overflow. These tests pin both halves: equivalence where the
old form worked, and saturation where it used to raise.
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

PHASE = "P-0.5-RESEARCH"
BASE = dj.DISPATCH_BACKOFF_BASE_S
CAP = dj.DISPATCH_BACKOFF_CAP_S
MULT = dj.DISPATCH_BACKOFF_MULTIPLIER

# The exact value the live run was stuck at.
LIVE_CONSECUTIVE = 1025


def _reference(repeat: int) -> float:
    """The old expression, evaluated where it does not raise."""
    if repeat <= 0:
        return 0.0
    return min(CAP, BASE * (MULT ** (repeat - 1)))


# ---------------------------------------------------------------------------
# 1. THE DEFECT: the boundary that killed the live run.
# ---------------------------------------------------------------------------
class TestTheOverflowIsGone:

    def test_the_exact_live_value_no_longer_raises(self):
        """`consecutive == 1025` is what the live ledgers held; the fold computes
        `_backoff_delay_s(consecutive - 1)` = `_backoff_delay_s(1024)` for the
        CURRENT tick and `1025` for the NEXT one. The next one used to raise."""
        assert dj._backoff_delay_s(LIVE_CONSECUTIVE) == CAP

    @pytest.mark.parametrize("repeat", [1024, 1025, 1026, 2048, 10 ** 6, 10 ** 9,
                                        2 ** 31, 2 ** 63])
    def test_large_repeats_saturate_instead_of_raising(self, repeat):
        assert dj._backoff_delay_s(repeat) == CAP

    def test_the_old_expression_really_did_raise_at_the_boundary(self):
        """Non-vacuousness: prove the pre-fix expression fails at this exact input,
        so this suite is testing a real defect and not a stylistic preference."""
        with pytest.raises(OverflowError) as ei:
            _reference(LIVE_CONSECUTIVE)
        assert ei.value.args == (34, "Result too large"), ei.value.args

    def test_the_raise_is_exactly_the_one_seen_in_the_live_log(self):
        """The live log's text, reproduced from the pre-fix expression."""
        try:
            _reference(LIVE_CONSECUTIVE + 1)
        except OverflowError as exc:
            assert repr(exc) == "OverflowError(34, 'Result too large')", repr(exc)
        else:
            pytest.fail("the pre-fix expression did not raise at 1026")


# ---------------------------------------------------------------------------
# 2. EQUIVALENCE: where the old form worked, the new one is identical.
# ---------------------------------------------------------------------------
class TestEquivalenceWhereTheOldFormWorked:

    def test_identical_over_the_whole_usable_range(self):
        diffs = [(r, _reference(r), dj._backoff_delay_s(r))
                 for r in range(-5, 1025)
                 if _reference(r) != dj._backoff_delay_s(r)]
        assert diffs == [], f"behaviour changed where the old form was fine: {diffs[:5]}"

    def test_the_documented_shape(self):
        assert dj._backoff_delay_s(-1) == 0.0
        assert dj._backoff_delay_s(0) == 0.0
        assert dj._backoff_delay_s(1) == BASE
        assert dj._backoff_delay_s(2) == BASE * MULT
        assert dj._backoff_delay_s(3) == BASE * MULT * MULT

    def test_saturates_at_the_cap_and_is_monotonic(self):
        seq = [dj._backoff_delay_s(r) for r in range(0, 64)]
        assert seq == sorted(seq), "backoff is not monotonic non-decreasing"
        assert all(v <= CAP for v in seq), "a value exceeded the cap"
        assert seq[-1] == CAP

    def test_it_does_not_multiply_more_than_it_has_to(self):
        """The loop must stop at the cap. A version that multiplied `repeat`
        times would be correct but quadratic; this pins the early exit."""
        import timeit
        t = timeit.timeit(lambda: dj._backoff_delay_s(10 ** 9), number=1000)
        assert t < 1.0, f"1e9 repeats took {t:.3f}s for 1000 calls - no early exit?"


# ---------------------------------------------------------------------------
# 3. END TO END: the fold that used to abort must now complete AND write.
# ---------------------------------------------------------------------------
def _seed_stalled_ledger(tmp_path: Path, consecutive: int) -> Path:
    """A run dir whose ledger sits exactly where the live one sat.

    Faithfulness matters here: `record_outcome` only INCREMENTS `consecutive`
    when `same` is true, i.e. when the ledger already carries the SAME
    `signature` and `revision` this fold computes -- otherwise it resets the
    counter to 1 and the overflow is never reached. The live ledgers carry a real
    signature/revision (e.g. P4-COPY's `exhausted::1916aa6bb21edf33` over
    `wo=...|state=running`) alongside a counter in the 1000s, because the same
    outcome was re-folded on every sweep tick.

    So: perform one REAL fold to let the engine write its own signature/revision,
    then pin only the counter at the boundary. That reproduces the live shape
    instead of a shape that merely looks like it."""
    run_dir = tmp_path / "run"
    (run_dir / "working" / "work-orders").mkdir(parents=True)
    (run_dir / "state.json").write_text(json.dumps({
        "phases": [{"id": PHASE, "status": "done"}],
    }), encoding="utf-8")
    (run_dir / "working" / "work-orders" / f"{PHASE}.json").write_text(
        json.dumps({"phase_id": PHASE}), encoding="utf-8")

    dj.record_outcome(run_dir, PHASE, status="already_done_in_state",
                      reasons=[], worker_id="t", paid_attempts=1)
    led = dj._read_ledger(run_dir, PHASE)
    assert led.get("signature") and led.get("revision"), (
        "the fixture did not establish a real signature/revision, so the next "
        "fold would reset `consecutive` instead of incrementing it")
    led["consecutive"] = consecutive
    led["observations"] = consecutive + 1
    dj._write_ledger(run_dir, PHASE, led)
    return run_dir


class TestTheStallIsGone:

    def test_the_fold_completes_and_ADVANCES_the_counter(self, tmp_path):
        """The heart of the defect: with the counter at the boundary, the fold
        used to raise BEFORE writing, so the counter could never advance and the
        sweep died every tick forever. It must now complete AND persist."""
        rd = _seed_stalled_ledger(tmp_path, LIVE_CONSECUTIVE)
        before = dj._read_ledger(rd, PHASE)
        assert before["consecutive"] == LIVE_CONSECUTIVE

        entry = dj.record_outcome(rd, PHASE, status="already_done_in_state",
                                  reasons=[], worker_id="t", paid_attempts=1)

        after = dj._read_ledger(rd, PHASE)
        assert after["consecutive"] == LIVE_CONSECUTIVE + 1, (
            "the fold did not advance the counter - the stall would repeat")
        assert entry["backoff_s"] == CAP
        assert after["next_eligible_at_epoch"] > 0

    def test_the_old_expression_would_have_aborted_this_very_fold(self, tmp_path):
        """Non-vacuousness for the test above, on the SAME fixture."""
        rd = _seed_stalled_ledger(tmp_path, LIVE_CONSECUTIVE)
        led = dj._read_ledger(rd, PHASE)
        with pytest.raises(OverflowError):
            # exactly what record_outcome computes for the NEXT tick
            _reference(led["consecutive"] + 1 - 1)

    @pytest.mark.parametrize("consecutive", [1024, 1025, 4096, 10 ** 7])
    def test_folds_keep_working_far_past_the_old_boundary(self, tmp_path, consecutive):
        rd = _seed_stalled_ledger(tmp_path, consecutive)
        for _ in range(3):
            dj.record_outcome(rd, PHASE, status="already_done_in_state",
                              reasons=[], worker_id="t", paid_attempts=1)
        led = dj._read_ledger(rd, PHASE)
        assert led["consecutive"] == consecutive + 3
        assert led["backoff_s"] if "backoff_s" in led else True

    def test_a_sweep_over_the_stalled_run_dir_no_longer_reports_an_error(self, tmp_path, monkeypatch):
        """The whole-sweep consequence: one poisoned counter used to abort the
        sweep for EVERY phase. The sweep must now return normally."""
        rd = _seed_stalled_ledger(tmp_path, LIVE_CONSECUTIVE)
        # no network: nothing here should reach a provider
        monkeypatch.setattr(dj, "dispatch_complete",
                            lambda *a, **k: (_ for _ in ()).throw(
                                AssertionError("a provider call was attempted")),
                            raising=False)
        try:
            res = dj.sweep_run_dir(rd, worker_id="probe", max_workers=1)
        except OverflowError as exc:  # pragma: no cover - the defect itself
            pytest.fail(f"sweep still overflows: {exc!r}")
        assert isinstance(res, list)
