"""S79-07 purchase state machine, fixture level (doc 09 section 8).

States: ready, validating, submitting, pending_confirmation, paid, failed,
requires_customer_action, cancelled.

Rules enforced here (doc 09 section 8, doc 02 section 4, doc 18 section 4):
- A clicked button is not paid; only an explicitly verified native success
  event moves submitting/pending/requires-action into paid.
- Failed or pending payment never traverses a paid route edge:
  can_traverse_paid_edge() is true only in state `paid`.
- Repeated submission while submitting or pending is rejected (UI-level
  guard; the doc is explicit this is NOT the only duplicate-charge defense).
- An unknown timeout outcome lands in pending_confirmation with
  reconcile_required=True; a retry from failed or unknown is allowed only
  after the caller records that native records were reconciled. This model
  never invents a charge endpoint and never retries on its own.
- Cancellation is possible before submission; after a verified payment the
  purchase cannot be cancelled by a page action.
- Paid is terminal for this initial-purchase machine. Extra-offer outcomes
  live in their own machines; an extra failure must not roll this back
  (asserted by test: no transition out of paid exists at all).
"""
from __future__ import annotations

from dataclasses import dataclass, field


class StateError(ValueError):
    pass


STATES = ("ready", "validating", "submitting", "pending_confirmation",
          "paid", "failed", "requires_customer_action", "cancelled")

# (from_state, event) -> to_state. Anything not listed is rejected.
TRANSITIONS = {
    ("ready", "begin_validation"): "validating",
    ("validating", "validation_failed"): "failed",
    ("validating", "submit"): "submitting",
    ("ready", "cancel"): "cancelled",
    ("validating", "cancel"): "cancelled",
    ("submitting", "native_paid_verified"): "paid",
    ("submitting", "native_failed"): "failed",
    ("submitting", "native_pending"): "pending_confirmation",
    ("submitting", "native_requires_customer_action"): "requires_customer_action",
    ("submitting", "timeout_unknown_outcome"): "pending_confirmation",
    ("pending_confirmation", "native_paid_verified"): "paid",
    ("pending_confirmation", "native_failed"): "failed",
    ("pending_confirmation", "native_requires_customer_action"): "requires_customer_action",
    ("requires_customer_action", "native_paid_verified"): "paid",
    ("requires_customer_action", "native_failed"): "failed",
    ("requires_customer_action", "native_pending"): "pending_confirmation",
    ("requires_customer_action", "customer_abandons_action"): "cancelled",
    ("failed", "retry_after_reconciliation"): "ready",
}


@dataclass(frozen=True)
class PurchaseAttempt:
    # Frozen (review defect N4): after construction the state fields cannot
    # be assigned directly; every state change goes through apply(), which
    # uses object.__setattr__ internally. `a.state = "paid"` now raises.
    state: str = "ready"
    reconcile_required: bool = False
    reconciled: bool = False
    history: list = field(default_factory=list)

    def __post_init__(self) -> None:
        # Review defects D-new2 and its residual: a bogus state must not be
        # constructible, and neither may a directly-constructed `paid`
        # attempt (which would make can_traverse_paid_edge() true without
        # any verified native event). Attempts always start at `ready`;
        # every other state is reached only through apply().
        if self.state not in STATES:
            raise StateError(f"unknown purchase state: {self.state}")
        if self.state != "ready":
            raise StateError("a purchase attempt must start at ready; other states are reached only by transitions")

    def apply(self, event: str) -> str:
        if event in ("submit",) and self.state in ("submitting", "pending_confirmation"):
            raise StateError("repeated submission while processing is rejected")
        if event == "retry_after_reconciliation":
            if self.reconcile_required and not self.reconciled:
                raise StateError("unknown outcome must be reconciled against native records before retry")
            # A failed attempt with a known outcome (reconcile_required False)
            # may retry directly; an unknown-outcome attempt may retry only
            # once reconciled is recorded.
        key = (self.state, event)
        if key not in TRANSITIONS:
            raise StateError(f"no transition from {self.state} on {event}")
        previous = self.state
        object.__setattr__(self, "state", TRANSITIONS[key])
        if event == "timeout_unknown_outcome":
            object.__setattr__(self, "reconcile_required", True)
            object.__setattr__(self, "reconciled", False)
        elif previous == "pending_confirmation" and event in (
                "native_paid_verified", "native_failed", "native_requires_customer_action"):
            # Review defect D-new1: a direct native resolution arriving
            # while pending IS the reconciliation of the unknown outcome;
            # clear the flag instead of leaving retry permanently blocked.
            object.__setattr__(self, "reconcile_required", False)
            object.__setattr__(self, "reconciled", False)
        if self.state == "ready" and event == "retry_after_reconciliation":
            object.__setattr__(self, "reconcile_required", False)
            object.__setattr__(self, "reconciled", False)
        self.history.append((previous, event, self.state))
        return self.state

    def record_reconciliation(self, found_paid: bool) -> str:
        """Caller checked native records for an unknown outcome."""
        if not self.reconcile_required:
            raise StateError("no reconciliation is outstanding for this attempt")
        if found_paid and (self.state, "native_paid_verified") not in TRANSITIONS:
            # Review defect D-new1: never mutate flags and then raise,
            # leaving the object in a contradictory state.
            raise StateError(f"reconciled-as-paid cannot be applied from {self.state}")
        object.__setattr__(self, "reconciled", True)
        if found_paid:
            return self.apply("native_paid_verified")
        # Reconciled as not paid: the attempt is a known failure now, and a
        # retry becomes possible from failed (with reconciliation recorded).
        if self.state == "pending_confirmation":
            return self.apply("native_failed")
        return self.state

    def can_traverse_paid_edge(self) -> bool:
        return self.state == "paid"
