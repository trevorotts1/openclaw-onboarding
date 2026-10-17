"""S79-10 attempt recovery: refresh, back-navigation and lost browser
context (doc 09 sections 7, 8 and 11; doc 18 section 4). Fixture level L1.

The scenario: a buyer submits, then refreshes the page, navigates back, or
loses the browser context entirely (closed tab, crashed browser, new
device). The checkout must never guess the outcome of an in-flight payment:
section 8 requires reconciling unknown outcomes against actual native
records before retrying, and a failed or pending payment must never
traverse a paid route edge.

Restore strategy (documented choice): PurchaseAttempt is a frozen
dataclass whose construction is restricted to the `ready` state, so a
serialized attempt is restored by REPLAY: construct a fresh attempt and
re-apply every recorded history event in order, verifying each recorded
transition against the live transition table. A state is therefore only
ever restored if the machine itself can reach it through the recorded
events, including `paid`, which is restorable only when the history
contains the verified native success event that produced it. Nothing in
this module constructs a PurchaseAttempt in a non-ready state directly.

Reconcile-on-restore rule: an attempt restored in `submitting` or
`pending_confirmation` was in flight when the context was lost, so its
outcome is UNKNOWN at restore time, exactly like the machine's timeout
case. The restore therefore sets reconcile_required (the same sanctioned
flag the timeout transition sets) and the RecoveredAttempt wrapper blocks
the two things that must wait for reconciliation: retry
(`retry_after_reconciliation`) and paid routing (any
`native_paid_verified` resolution, and can_traverse_paid_edge()). The
caller resolves the hold only by record_reconciliation(found_paid=...),
which models the native-record check. Other native resolutions (for
example a native failure read-back) delegate to the live machine, whose
own rules clear the flag on a direct resolution from pending (defect
D-new1 behavior, preserved).

Lost browser context: restore_attempt(None) is the context-free restore.
It returns a fresh `ready` attempt with order_ref None. There is no API
to attach an order reference after restore, and a fresh attempt cannot
traverse a paid edge, so a context-free restore can never claim an
existing paid order.

Sanctioned surface (review defect AR-2): the RecoveredAttempt wrapper is
the ONLY sanctioned surface for a restored attempt. The inner
PurchaseAttempt is stored privately and is not part of the public API:
reaching it directly would let a consumer call the inner attempt's
apply() and bypass the reconcile-on-restore hold entirely. Consumers use
the wrapper's state, can_traverse_paid_edge(), reconciliation_outstanding,
apply(), record_reconciliation() and serialize().
"""
from __future__ import annotations

from dataclasses import dataclass

from purchase_state import STATES, PurchaseAttempt, StateError

FORMAT = "s79.purchase_attempt/v1"

# States whose outcome is unknown if the browser context disappears while
# the attempt is in them: a submission may or may not have reached the
# native processor.
IN_FLIGHT_STATES = ("submitting", "pending_confirmation")

# Events that must wait until an in-flight restore has been reconciled
# against native records: retrying, and the only event that can move an
# attempt into `paid`.
_HELD_EVENTS = ("retry_after_reconciliation", "native_paid_verified")


class RecoveryError(StateError):
    """Serialized attempt state is corrupt, or a held event was attempted
    before reconciliation. A StateError subclass so restored-attempt
    failures surface with the same error type the live machine raises."""


def serialize_attempt(attempt: PurchaseAttempt, order_ref: str | None = None) -> dict:
    """JSON-safe snapshot of an attempt. `order_ref` is the native order
    reference the caller's session holds, if any; the state machine itself
    carries no order identity."""
    if order_ref is not None and not isinstance(order_ref, str):
        raise RecoveryError("order_ref must be a string or None")
    return {
        "format": FORMAT,
        "state": attempt.state,
        "reconcile_required": attempt.reconcile_required,
        "reconciled": attempt.reconciled,
        "order_ref": order_ref,
        "history": [list(entry) for entry in attempt.history],
    }


@dataclass(frozen=True)
class RecoveredAttempt:
    """A restored attempt plus the identity and hold state restore adds.
    The wrapper is frozen: order_ref cannot be attached or changed after
    restore. The inner PurchaseAttempt is private (review defect AR-2):
    this wrapper is the only sanctioned surface, so the reconcile-on-
    restore hold cannot be bypassed by driving the inner attempt directly."""
    _attempt: PurchaseAttempt
    order_ref: str | None
    restore_hold: bool = False

    @property
    def state(self) -> str:
        return self._attempt.state

    @property
    def reconciliation_outstanding(self) -> bool:
        return (self.restore_hold and self._attempt.reconcile_required
                and not self._attempt.reconciled)

    def can_traverse_paid_edge(self) -> bool:
        if self.reconciliation_outstanding:
            return False
        return self._attempt.can_traverse_paid_edge()

    def apply(self, event: str) -> str:
        if self.reconciliation_outstanding and event in _HELD_EVENTS:
            raise RecoveryError(
                "restored in-flight attempt must be reconciled against native "
                f"records before {event}")
        return self._attempt.apply(event)

    def record_reconciliation(self, found_paid: bool) -> str:
        result = self._attempt.record_reconciliation(found_paid)
        if not found_paid and self._attempt.state == "submitting":
            # Review defect AR-1: the shared machine resolves a not-paid
            # reconciliation to `failed` only from pending_confirmation;
            # from `submitting` it lifts the hold and stays in submitting,
            # which would let a later caller-fed native_paid_verified
            # still reach paid after the record check said not-paid. The
            # wrapper closes that asymmetry here (the machine's table
            # already allows submitting -> native_failed): a restored
            # submitting attempt reconciled as not paid is a known
            # failure, exactly like the pending path.
            return self._attempt.apply("native_failed")
        return result

    def serialize(self) -> dict:
        """JSON-safe snapshot of the wrapped attempt under its restored
        order_ref; the sanctioned replacement for reaching the inner
        attempt to serialize it."""
        return serialize_attempt(self._attempt, order_ref=self.order_ref)


def _replay(history) -> PurchaseAttempt:
    if not isinstance(history, list):
        raise RecoveryError("serialized history must be a list")
    attempt = PurchaseAttempt()
    for entry in history:
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            raise RecoveryError(f"corrupt history entry: {entry!r}")
        from_state, event, to_state = entry
        if from_state not in STATES or to_state not in STATES:
            raise RecoveryError(f"history entry names a state outside doc 09 section 8: {entry!r}")
        if from_state != attempt.state:
            raise RecoveryError(
                f"history gap: entry starts at {from_state} but replay is at {attempt.state}")
        try:
            attempt.apply(event)
        except StateError as exc:
            raise RecoveryError(f"history event cannot be replayed: {entry!r}: {exc}") from exc
        if attempt.state != to_state:
            raise RecoveryError(
                f"history entry records {to_state} but replay produced {attempt.state}: {entry!r}")
    return attempt


def restore_attempt(payload) -> RecoveredAttempt:
    """Restore from a serialize_attempt payload. `None` is the lost-context
    restore: a fresh ready attempt tied to no order."""
    if payload is None:
        return RecoveredAttempt(_attempt=PurchaseAttempt(), order_ref=None, restore_hold=False)
    if not isinstance(payload, dict):
        raise RecoveryError("serialized attempt must be an object or None")
    if payload.get("format") != FORMAT:
        raise RecoveryError("serialized attempt has a missing or unknown format")
    state = payload.get("state")
    if state not in STATES:
        raise RecoveryError(f"serialized state is not one of the doc 09 section 8 states: {state!r}")
    order_ref = payload.get("order_ref")
    if order_ref is not None and not isinstance(order_ref, str):
        raise RecoveryError("serialized order_ref must be a string or None")
    attempt = _replay(payload.get("history"))
    if attempt.state != state:
        raise RecoveryError(
            f"serialized state {state} does not match the replayed history, which ends at {attempt.state}")
    hold = attempt.state in IN_FLIGHT_STATES
    if hold:
        # Reconcile-on-restore: the in-flight outcome is unknown, so the
        # restored attempt carries the same reconciliation requirement the
        # machine sets on a timeout. object.__setattr__ is the machine's
        # own internal mutation path for its frozen dataclass.
        object.__setattr__(attempt, "reconcile_required", True)
        object.__setattr__(attempt, "reconciled", False)
    return RecoveredAttempt(_attempt=attempt, order_ref=order_ref, restore_hold=hold)
