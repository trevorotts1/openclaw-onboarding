"""PD-TEST-182 -- a repair receipt must be able to FUND the work it invalidates.

THE DEFECT. `authorize_paid_retry_reset` is the local-operator control-plane verb
that clears an exhausted paid-retry wall after a deployed code repair. Its
consumer refuses to act unless the allowance covers EVERY unit the fan-out would
invalidate:

    _n_units = len(wanted_items)
    if _allowance < _n_units:
        _force_reauthor = False        # bank left INTACT, receipt ignored

but the producer capped the allowance at `DISPATCH_RETRY_CAP`, which is **3**:

    if allowance < 1 or allowance > DISPATCH_RETRY_CAP:
        raise ValueError(f"allowance must be 1..{DISPATCH_RETRY_CAP}")

On the live run `P4-PROMPT` has **8** units, so the engine demanded
`allowance >= 8` while itself rejecting anything above 3 -- and its own refusal
text asked the operator to "Re-issue with --reset-allowance >= 8 (max 3)", a
value it would refuse. The run was walled by an internal contradiction in its
own recovery path: no operator action could clear it.

This is PD-TEST-124's theme inside the recovery instrument. The fair-budget work
gave the fan-out a bounded total of `min(128, units + pool)` precisely because
the legacy per-phase cap of 3 starved an 8-unit fan-out, but the receipt that
must fund the re-authoring was left on that same legacy ceiling.

WHAT THESE TESTS PIN
  * a receipt sized for a real 8-unit fan-out is ACCEPTED (was rejected);
  * the ceiling is still a declared bound, not unbounded -- above
    `PHASE_TOTAL_PAID_HARD_CAP` is refused;
  * an allowance below 1 is still refused;
  * the receipt still binds the CURRENT installed dispatcher sha and the durable
    generation, so it cannot be replayed against different bytes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as dj  # noqa: E402

PHASE = "P4-PROMPT"
WORKER = "dispatcher-test-182"
# The live shape: P4-PROMPT fans out per slide, and this run has 8.
UNITS = ["slide-%02d" % i for i in range(1, 9)]


def _run_dir(tmp_path: Path) -> Path:
    """A run dir whose ledger carries a durable int `generation`, which
    authorize_paid_retry_reset requires -- a hand-created legacy ledger must not
    be able to satisfy a freshly issued receipt."""
    run_dir = tmp_path / "run"
    (run_dir / "working" / "work-orders").mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps({
        "phases": [{"id": PHASE, "status": "running"}]}), encoding="utf-8")
    dj._declare_phase_paid_budget(run_dir, PHASE, unit_keys=UNITS, worker_id=WORKER)
    # A durable int `generation` is REQUIRED, so a hand-created legacy ledger
    # cannot satisfy a fresh receipt. It is written at dispatcher.py:9788 when a
    # receipt is CONSUMED (not by the declaration or by a plain reservation), so
    # the live P4-PROMPT ledger carries one from its earlier consumption
    # (generation: 2, repair_receipt_consumed: True). The fixture must therefore
    # carry one too -- seeding it here rather than driving a full prior
    # consumption keeps this test about the ALLOWANCE BOUND, which is the defect.
    led = dj._read_ledger(run_dir, PHASE)
    led["generation"] = 1
    dj._write_ledger(run_dir, PHASE, led)
    return run_dir


# ---------------------------------------------------------------------------
# The defect
# ---------------------------------------------------------------------------

def test_a_receipt_can_fund_the_whole_8_unit_fanout(tmp_path):
    """THE REGRESSION. Before the fix this raised ValueError, so the only
    instrument that could clear an exhausted wall refused to cover the work it
    existed to fund -- and the engine's own advice ('max 3' for a needed 8) was
    unsatisfiable."""
    run_dir = _run_dir(tmp_path)
    receipt = dj.authorize_paid_retry_reset(run_dir, PHASE, allowance=len(UNITS))
    assert receipt["allowance"] == len(UNITS), receipt
    assert receipt["phase_id"] == PHASE
    assert receipt["dispatcher_sha256"], "the receipt must bind the installed bytes"
    assert receipt["kind"] == dj.DISPATCH_REPAIR_RECEIPT_KIND


def test_the_ceiling_is_still_a_declared_bound(tmp_path):
    run_dir = _run_dir(tmp_path)
    with pytest.raises(ValueError):
        dj.authorize_paid_retry_reset(
            run_dir, PHASE, allowance=dj.PHASE_TOTAL_PAID_HARD_CAP + 1)


def test_a_zero_or_negative_allowance_is_still_refused(tmp_path):
    run_dir = _run_dir(tmp_path)
    for bad in (0, -1):
        with pytest.raises(ValueError):
            dj.authorize_paid_retry_reset(run_dir, PHASE, allowance=bad)


def test_the_receipt_still_binds_the_installed_dispatcher_bytes(tmp_path):
    """A receipt is not a blank cheque: it records the sha of the dispatcher
    that issued it, so it cannot be replayed after the code moves."""
    run_dir = _run_dir(tmp_path)
    receipt = dj.authorize_paid_retry_reset(run_dir, PHASE, allowance=len(UNITS))
    assert receipt["dispatcher_sha256"] == dj._file_sha(Path(dj.__file__))
    assert isinstance(receipt["prior_generation"], int)


# ---------------------------------------------------------------------------
# The two ways the FIRST version of this fix was inert or harmful
# ---------------------------------------------------------------------------

def test_the_CONSUMER_validator_accepts_what_the_producer_issues(tmp_path):
    """The first version of this fix changed only the producer. The consumer's
    own validator (`_repair_receipt_is_actionable`) still required
    `1 <= allowance <= DISPATCH_RETRY_CAP`, so an 8-unit receipt would have been
    ISSUED and then REJECTED as invalid -- the fan-out still never re-authors.
    Producer and consumer must agree on the ceiling."""
    run_dir = _run_dir(tmp_path)
    receipt = dj.authorize_paid_retry_reset(run_dir, PHASE, allowance=len(UNITS))
    led = dj._read_ledger(run_dir, PHASE)
    ok, why = dj._repair_receipt_is_actionable(led, PHASE, run_dir)
    assert ok, (
        f"the consumer rejected a receipt the producer just issued: {why!r}. "
        "The two ceilings must be the same constant.")


def test_consuming_a_fanout_sized_receipt_never_writes_a_negative_counter(tmp_path):
    """The re-arm is `paid = DISPATCH_RETRY_CAP - allowance`. With an 8-unit
    allowance that is 3 - 8 = -5. A negative phase counter makes `paid >= cap`
    unsatisfiable, i.e. UNBOUNDED re-dispatch -- strictly worse than the bug
    being fixed. It must clamp at zero."""
    run_dir = _run_dir(tmp_path)
    dj.authorize_paid_retry_reset(run_dir, PHASE, allowance=len(UNITS))
    # Drive the real reservation path, which is where the receipt is consumed.
    with dj.paid_unit_scope(UNITS[1]):
        dj._reserve_paid_attempt(run_dir, PHASE, WORKER)
    led = dj._read_ledger(run_dir, PHASE)
    paid = int(led.get("paid_attempts") or 0)
    assert paid >= 0, (
        f"paid_attempts went NEGATIVE ({paid}) after consuming a "
        f"{len(UNITS)}-unit receipt -- the phase bound is now unsatisfiable")
    assert led.get("repair_receipt_consumed") is True, (
        "the receipt was not consumed on the reservation path")
