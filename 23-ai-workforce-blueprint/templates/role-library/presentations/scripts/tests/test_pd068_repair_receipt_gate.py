"""PD-TEST-068 -- the local-operator repair receipt must actually release the
exhausted paid-retry cap, in BOTH the read-only gate and the consumer.

The defect this pins (proven live on run
pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4, phase P4-COPY):

  * `should_dispatch()` early-returned `(False, "paid retry budget exhausted")`
    the moment `blocked and paid_attempts >= DISPATCH_RETRY_CAP`.
  * `_reserve_paid_attempt()` is the ONLY consumer of the operator's receipt.
  * Every claim path (sweep, scan-root scheduler, ready-queue scan) is gated
    by `should_dispatch()`, so the receipt could never be reached.  The one
    sanctioned operator release from a spent budget was INERT: `--authorize-
    paid-retry-reset` returned rc 0, wrote a correctly-bound receipt, and
    nothing ever consumed it (no dispatch, no provider call, ledger unchanged).

The repair factors the receipt-validity predicate out of the consumer into ONE
shared helper (`_repair_receipt_releases_cap`) and makes the gate consult it.
Two directions, because a release that skips validation is worse than the bug:

  A. EXHAUSTED + VALID receipt -> the gate ADMITS, the reservation consumes the
     receipt exactly once, the allowance is honoured, and the phase re-blocks
     when the allowance is spent.
  B. EXHAUSTED + absent / invalid / already-consumed receipt -> still REFUSED
     by both the gate and the consumer, for every binding field.

No network, no provider call and no real run is touched: the ledger is a
throwaway tmp_path fixture shaped exactly like the live P4-COPY ledger.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as D  # noqa: E402

PHASE = "P-T"
CAP = D.DISPATCH_RETRY_CAP  # = 3 (HEAL_CAP_TRANSIENT), asserted below


def _state_dir(run: Path) -> Path:
    return run / "working" / "work-orders" / ".dispatch-state"


def _ledger_path(run: Path) -> Path:
    return _state_dir(run) / f"{PHASE}.json"


def _receipt_path(run: Path) -> Path:
    return _state_dir(run) / f"{PHASE}.repair-receipt.json"


def _seed(tmp_path: Path, *, paid: int = CAP, blocked: bool = True,
          generation: int = 0, consumed: bool = False) -> Path:
    """A run whose P4-COPY-shaped ledger is exhausted, exactly like the live
    one: blocked, paid_attempts at the cap, generation 0, no receipt consumed."""
    run = tmp_path / "run"
    _state_dir(run).mkdir(parents=True)
    _ledger_path(run).write_text(json.dumps({
        "phase_id": PHASE,
        "status": "exhausted",
        "signature": "exhausted::deadbeefdeadbeef",
        "revision": "wo=1:2|state=running",
        "consecutive": 3,
        "observations": 3,
        "reasons": ["section-01: unit returned empty output"],
        "backoff_s": 60.0,
        "blocked": blocked,
        "blocked_reason": ("paid retry budget exhausted after 3 provider attempts "
                           f"for {PHASE} with unchanged approved input "
                           f"(DISPATCH_RETRY_CAP={CAP})."),
        "paid_attempts": paid,
        "generation": generation,
        "repair_receipt_consumed": consumed,
        "repair_receipt": None,
        "approved_input_revision": "initial",
    }, indent=2), encoding="utf-8")
    return run


def _ledger(run: Path) -> dict:
    return json.loads(_ledger_path(run).read_text(encoding="utf-8"))


def _receipt(run: Path) -> dict:
    return json.loads(_receipt_path(run).read_text(encoding="utf-8"))


def _write_receipt(run: Path, receipt: dict) -> None:
    _receipt_path(run).write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")


def _authorize(run: Path, *, allowance: int = 2) -> dict:
    """The product's OWN issue path -- never a hand-built receipt for the VALID
    direction, so the binding fields are the real ones."""
    return D.authorize_paid_retry_reset(run, PHASE, allowance=allowance)


def test_premise_cap_and_initial_refusal(tmp_path):
    assert CAP == 3, "DISPATCH_RETRY_CAP changed; review this repair against it"
    run = _seed(tmp_path)
    may, why = D.should_dispatch(run, PHASE)
    assert may is False and "exhausted" in why
    with pytest.raises(D.PaidBudgetExhausted):
        D._reserve_paid_attempt(run, PHASE, "worker-1")
    assert not _receipt_path(run).exists()


# ---------------------------------------------------------------------------
# Direction A: exhausted + VALID receipt -> admitted, consumed once, honoured.
# ---------------------------------------------------------------------------
def test_valid_receipt_admits_the_gate_without_consuming_it(tmp_path):
    run = _seed(tmp_path)
    assert D.should_dispatch(run, PHASE)[0] is False

    _authorize(run, allowance=2)

    may, why = D.should_dispatch(run, PHASE)
    assert may is True, f"the gate must admit a valid unconsumed receipt ({why})"
    assert "receipt" in why
    # The preflight is READ-ONLY: it must not consume or mutate anything.
    led = _ledger(run)
    assert led["repair_receipt_consumed"] is False
    assert led["generation"] == 0
    assert led["paid_attempts"] == CAP
    assert _receipt_path(run).exists()
    # Idempotent: a second preflight still admits.
    assert D.should_dispatch(run, PHASE)[0] is True


def test_reservation_consumes_exactly_once_and_honours_the_allowance(tmp_path):
    run = _seed(tmp_path)
    _authorize(run, allowance=2)
    assert D.should_dispatch(run, PHASE)[0] is True  # the gate must first ADMIT

    D._reserve_paid_attempt(run, PHASE, "worker-1")

    led = _ledger(run)
    assert led["repair_receipt_consumed"] is True
    assert led["generation"] == 1, "consumption must burn the bound generation"
    assert led["paid_attempts"] == CAP - 2 + 1, "allowance 2 releases 2 attempts"
    assert led["repair_receipt"]["allowance"] == 2
    assert led["repair_receipt"]["kind"] == "local-operator-paid-retry-reset-v1"

    # Second released attempt, then the cap re-applies.  CONSUMED ONCE.
    D._reserve_paid_attempt(run, PHASE, "worker-1")
    assert _ledger(run)["paid_attempts"] == CAP
    with pytest.raises(D.PaidBudgetExhausted):
        D._reserve_paid_attempt(run, PHASE, "worker-1")
    assert _ledger(run)["paid_attempts"] == CAP

    # Re-blocked when spent: the consumed receipt no longer releases the gate.
    may, why = D.should_dispatch(run, PHASE)
    assert may is False and "exhausted" in why


def test_consumed_receipt_is_never_replayed(tmp_path):
    run = _seed(tmp_path)
    _authorize(run, allowance=1)
    stale_receipt = _receipt(run)
    assert D.should_dispatch(run, PHASE)[0] is True  # admitted before consumption

    D._reserve_paid_attempt(run, PHASE, "worker-1")
    assert _ledger(run)["repair_receipt_consumed"] is True

    # Put the SAME (now stale) receipt back on disk, as a crash/restart would.
    _write_receipt(run, stale_receipt)
    assert D.should_dispatch(run, PHASE)[0] is False
    with pytest.raises(D.PaidBudgetExhausted):
        D._reserve_paid_attempt(run, PHASE, "worker-1")


# ---------------------------------------------------------------------------
# Direction B: exhausted + absent / invalid / consumed -> still REFUSED.
# ---------------------------------------------------------------------------
def _mutations():
    return {
        "wrong_kind": lambda r: r.update(kind="some-other-reset-v1"),
        "wrong_run": lambda r: r.update(run="/some/other/run"),
        "wrong_phase_id": lambda r: r.update(phase_id="P-OTHER"),
        "wrong_approved_input_revision": lambda r: r.update(approved_input_revision="approved-intake:deadbeef"),
        "wrong_prior_generation": lambda r: r.update(prior_generation=99),
        "wrong_dispatcher_sha256": lambda r: r.update(dispatcher_sha256="0" * 64),
        "wrong_operator_uid": lambda r: r.update(operator_uid=os.getuid() + 1),
        "allowance_zero": lambda r: r.update(allowance=0),
        "allowance_over_cap": lambda r: r.update(allowance=CAP + 1),
    }


@pytest.mark.parametrize("mutation", sorted(_mutations()))
def test_invalid_receipt_still_refuses(tmp_path, mutation):
    run = _seed(tmp_path)
    _authorize(run, allowance=2)
    receipt = _receipt(run)
    _mutations()[mutation](receipt)
    _write_receipt(run, receipt)

    may, why = D.should_dispatch(run, PHASE)
    assert may is False, f"mutated receipt {mutation} must NOT release the cap"
    assert "exhausted" in why
    with pytest.raises(D.PaidBudgetExhausted):
        D._reserve_paid_attempt(run, PHASE, "worker-1")
    assert _ledger(run)["repair_receipt_consumed"] is False


def test_absent_receipt_still_refuses(tmp_path):
    run = _seed(tmp_path)
    assert not _receipt_path(run).exists()
    assert D.should_dispatch(run, PHASE)[0] is False
    with pytest.raises(D.PaidBudgetExhausted):
        D._reserve_paid_attempt(run, PHASE, "worker-1")


def test_already_consumed_receipt_still_refuses(tmp_path):
    run = _seed(tmp_path, consumed=True)
    _authorize(run, allowance=2)  # issue binds generation 0; ledger says consumed
    assert D.should_dispatch(run, PHASE)[0] is False
    with pytest.raises(D.PaidBudgetExhausted):
        D._reserve_paid_attempt(run, PHASE, "worker-1")


def test_hand_written_ledger_generation_cannot_be_defaulted(tmp_path):
    """A ledger with no durable generation can never satisfy a receipt, and the
    issue path itself refuses to mint one (the PD-014 generation guard)."""
    run = _seed(tmp_path)
    led = _ledger(run)
    del led["generation"]
    _ledger_path(run).write_text(json.dumps(led), encoding="utf-8")
    with pytest.raises(RuntimeError):
        D.authorize_paid_retry_reset(run, PHASE, allowance=2)
    assert D.should_dispatch(run, PHASE)[0] is False


def test_ordinary_backoff_path_is_untouched(tmp_path):
    """A non-exhausted parked phase still gates on its own backoff window; the
    receipt-aware branch changes nothing for the ordinary park."""
    run = _seed(tmp_path, paid=1, blocked=True)
    led = _ledger(run)
    led.update({"status": "error", "consecutive": 2, "next_eligible_at_epoch": 10 ** 12,
                # must match _dispatch_revision() for this empty fixture run,
                # or the anti-starvation branch correctly un-parks the phase.
                "revision": "wo=absent|state=unknown"})
    _ledger_path(run).write_text(json.dumps(led), encoding="utf-8")
    may, why = D.should_dispatch(run, PHASE, now=10 ** 11)
    assert may is False and "backoff" in why
