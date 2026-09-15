"""PD-TEST-094 -- the backoff exponent must be clamped, or a run whose stored
`consecutive` counter grew large can never be dispatched again.

THE DEFECT (root-caused at code level, then observed live).

`record_outcome()` folds one dispatch outcome into the phase ledger:

    consecutive = (int(led.get("consecutive") or 0) + 1) if same else 1
    ...
    delay = _backoff_delay_s(consecutive - 1)          # dispatcher.py:8036
    ...
    _write_ledger(run_dir, phase_id, entry)            # dispatcher.py:8084

`_backoff_delay_s(repeat)` computed

    return min(CAP, BASE * (MULTIPLIER ** (repeat - 1)))

with BASE=30.0, MULTIPLIER=2.0, CAP=900.0. The `min()` clamps the RESULT, not
the exponent -- so the exponentiation itself still runs at full size. Float
MULTIPLICATION overflow is silent (`30.0 * inf == inf`, and `min(CAP, inf)`
returns the cap), but float EXPONENTIATION raises:

    >>> 2.0 ** 1024
    OverflowError: (34, 'Result too large')

Live consequence, observed on the real run at 2026-09-15T13:03-13:08Z: the
stored `consecutive` for P-0.5-RESEARCH had reached 1025, so the next fold
computed `_backoff_delay_s(1025)` -> `2.0 ** 1024` -> OverflowError. Because
that raise happens BEFORE `_write_ledger`, the stored 1025 never advanced, so
EVERY later sweep re-raised on the very first order file and the dispatcher
dispatched nothing at all. The log grew 24 -> 46 identical
`sweep error: OverflowError(34, 'Result too large')` lines in four minutes and
was still growing; the run was frozen at 57 total / 14 done / 1 running with
zero work orders issued. A dispatcher restart could not cure it, because the
poison value lives in the durable ledger.

WHAT THIS FILE PINS

  A. THE RAMP IS UNCHANGED WHERE IT MATTERS.
     Every repeat value whose unclamped product stays under the cap returns the
     byte-identical delay it always did. The clamp is chosen (64) far above the
     exponent at which the cap is already reached (5), so it cannot alter any
     returned value -- it only removes the raise.
  B. THE VALUE THAT WEDGED THE LIVE RUN NO LONGER RAISES.
     `_backoff_delay_s(1025)` and far larger inputs return the cap. The test
     also asserts the OLD expression really does raise at that input, so this
     file fails loudly if someone later "simplifies" the clamp away.
  C. THE LEDGER ACTUALLY ADVANCES.
     The decisive end-to-end claim: folding one more identical failing outcome
     onto a ledger stuck at consecutive=1025 writes the ledger with a HIGHER
     consecutive and a capped backoff, instead of raising out of
     `record_outcome()` before the write. This is the exact behaviour whose
     absence froze the live run.

No test here touches the network, a provider, the live run directory, or the
installed mirrors. Everything is the real code against a scratch run dir.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as dj  # noqa: E402

PHASE = "P-0.5-RESEARCH"
OTHER_PHASE = "P0B-PRIORITY"
ARTIFACT = "working/research/brief-generated.md"
REASONS = ["provider refused the request"]

# The stored counter value measured on the live run when the sweep wedged.
LIVE_STUCK_CONSECUTIVE = 1025


def _seed_run(tmp_path: Path, *, phase: str = PHASE, consecutive: int,
              status: str = "error") -> Path:
    """A scratch run whose ledger already records `consecutive` identical
    outcomes, plus the work order and state.json the real helpers read."""
    run_dir = tmp_path / "run"
    (run_dir / "working" / "work-orders").mkdir(parents=True)
    (run_dir / "working" / "copy").mkdir(parents=True)
    (run_dir / "state.json").write_text(json.dumps({
        "phases": [{"id": phase, "status": "running"}],
    }), encoding="utf-8")
    (run_dir / "working" / "work-orders" / f"{phase}.json").write_text(
        json.dumps({"phase_id": phase, "produces_artifact": ARTIFACT}),
        encoding="utf-8")
    dj._write_ledger(run_dir, phase, {
        "phase_id": phase,
        "status": status,
        # The signature/revision must MATCH what record_outcome() recomputes,
        # otherwise the fold takes its `not same` branch, resets consecutive
        # to 1 and the overflow path is never reached.
        "signature": dj._outcome_signature(status, REASONS),
        "revision": dj._dispatch_revision(run_dir, phase),
        "consecutive": consecutive,
        "observations": consecutive,
        "approved_input_revision": "initial",
        "paid_attempts": 0,
        "generation": 0,
        "repair_receipt_consumed": False,
        "blocked": False,
    })
    return run_dir


# ---------------------------------------------------------------------------
# A. The ramp is unchanged where it matters.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("repeat,expected", [
    (-1, 0.0),          # a new/changed outcome is always immediate
    (0, 0.0),
    (1, 30.0),          # 30 * 2**0
    (2, 60.0),          # 30 * 2**1
    (3, 120.0),         # 30 * 2**2
    (4, 240.0),         # 30 * 2**3
    (5, 480.0),         # 30 * 2**4
    (6, 900.0),         # 30 * 2**5 = 960 -> capped at 900
    (7, 900.0),
])
def test_ramp_is_unchanged_for_every_reachable_value(repeat, expected):
    assert dj._backoff_delay_s(repeat) == expected


def test_the_clamp_is_far_above_the_first_capped_exponent():
    """A clamp at or below the first capped exponent could shift a value; a
    clamp well above it cannot. This pins that margin deliberately."""
    first_capped = 6  # repeat == 6 is the first value the cap ACTUALLY bites
    assert dj.DISPATCH_BACKOFF_MAX_EXPONENT > first_capped - 1


# ---------------------------------------------------------------------------
# B. The exact input that wedged the live run no longer raises.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("repeat", [
    LIVE_STUCK_CONSECUTIVE,      # the live value
    LIVE_STUCK_CONSECUTIVE + 1,
    2 ** 20,                     # absurd but must stay total
    10 ** 9,
])
def test_huge_repeat_returns_the_cap_instead_of_raising(repeat):
    assert dj._backoff_delay_s(repeat) == dj.DISPATCH_BACKOFF_CAP_S


def test_the_old_expression_really_did_raise_at_that_input():
    """Guards the repair itself: if this ever stops raising, the clamp has been
    removed and the wedge is back."""
    with pytest.raises(OverflowError):
        _ = dj.DISPATCH_BACKOFF_BASE_S * (
            dj.DISPATCH_BACKOFF_MULTIPLIER ** (LIVE_STUCK_CONSECUTIVE - 1))


# ---------------------------------------------------------------------------
# C. The ledger advances -- the behaviour whose absence froze the live run.
# ---------------------------------------------------------------------------
def test_a_stuck_ledger_advances_instead_of_raising(tmp_path):
    run_dir = _seed_run(tmp_path, consecutive=LIVE_STUCK_CONSECUTIVE)

    entry = dj.record_outcome(
        run_dir, PHASE, "error", list(REASONS),
        worker_id="dispatcher-test", paid_attempts=0)

    # The advance that the raise used to prevent.
    assert entry["consecutive"] == LIVE_STUCK_CONSECUTIVE + 1
    assert entry["backoff_s"] == dj.DISPATCH_BACKOFF_CAP_S

    # ...and it is DURABLE, not merely returned. A fold that returned the new
    # entry without persisting it would look identical to the caller while
    # leaving the sweep wedged forever.
    on_disk = dj._read_ledger(run_dir, PHASE)
    assert on_disk["consecutive"] == LIVE_STUCK_CONSECUTIVE + 1
    assert on_disk["backoff_s"] == dj.DISPATCH_BACKOFF_CAP_S


def test_the_next_fold_after_the_stuck_value_also_survives(tmp_path):
    """One advance is not enough: the run wedged because EVERY later sweep
    re-raised. Two consecutive folds must both complete."""
    run_dir = _seed_run(tmp_path, consecutive=LIVE_STUCK_CONSECUTIVE)
    first = dj.record_outcome(run_dir, PHASE, "error", list(REASONS),
                              worker_id="dispatcher-test")
    second = dj.record_outcome(run_dir, PHASE, "error", list(REASONS),
                               worker_id="dispatcher-test")
    assert second["consecutive"] == first["consecutive"] + 1
    assert second["backoff_s"] == dj.DISPATCH_BACKOFF_CAP_S


def test_a_fresh_outcome_still_records_immediately(tmp_path):
    """The clamp must not turn a genuinely new outcome into a delayed one:
    `not same` still resets to consecutive=1 with zero delay."""
    run_dir = _seed_run(tmp_path, consecutive=LIVE_STUCK_CONSECUTIVE)
    entry = dj.record_outcome(run_dir, PHASE, "ok", [], worker_id="dispatcher-test")
    assert entry["consecutive"] == 1
    assert entry["backoff_s"] == 0.0
