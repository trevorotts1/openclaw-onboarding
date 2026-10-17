"""S79-04 selection validation behavior (doc 09 section 5, doc 02 section 5).

The selection is intent, not payment evidence. Checkout must:
- proceed only on a validated, current, price-consistent selection;
- show a recovery choice when the selection is missing or expired, and
  NEVER silently default to another package;
- require clear reconfirmation when the offer revision changed or the
  price binding moved since selection;
- preserve a change-package path back to Product Selection.

Ordering (review batch #3, probe D): expiry is checked before revision,
because reconfirming an expired selection would invite re-approving a dead
session reference; recovery cannot charge, reconfirmation is a pre-charge
step. Structural validity (identity, quantity) is checked before either.
Timestamps are ISO-8601 strings compared lexicographically; callers must
supply them in one consistent format (same assumption as the bump model).
Offer AVAILABILITY revalidation at checkout (doc 02 section 5) is an
S79-04/S78 seam item: this resolver checks identity, expiry, revision and
price binding; live availability comes from the native catalog read that
S78/S49 supply, and is named here rather than silently absent.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Selection:
    offer_id: str
    native_price_id: str
    amount_minor: int
    currency: str
    quantity: int
    launch_revision: int
    offer_revision: int
    expires_at: str | None
    tenant_id: str = ""
    location_id: str = ""
    launch_id: str = ""


@dataclass(frozen=True)
class SelectionDecision:
    action: str  # proceed | recovery_choice | reconfirm_changed_offer | change_package
    reason: str
    offer_id: str | None


def resolve_selection(selection: Selection | None, *, current_launch_revision: int,
                      current_offer_revision: int, current_native_price_id: str,
                      current_amount_minor: int, current_currency: str,
                      now: str, expected_tenant_id: str,
                      expected_location_id: str, expected_launch_id: str,
                      visitor_action: str | None = None) -> SelectionDecision:
    # Review defect N3: the expected tenant/location/launch identity is a
    # REQUIRED argument. Identity enforcement must not be opt-in; a caller
    # cannot silently skip it by forgetting a parameter.
    # Re-check residual R1: an explicit None is also a bypass and is refused.
    if expected_tenant_id is None or expected_location_id is None or expected_launch_id is None:
        raise ValueError("expected tenant, location and launch identity are required and cannot be None")
    if selection is None:
        return SelectionDecision(
            "recovery_choice",
            "selection is missing; offer a recovery choice, never default to another package",
            None)
    # Structural checks first (review defect D-1/D-2): identity and quantity
    # are validated before expiry/revision/price, so an invalid selection
    # is never masked by a reconfirmation branch.
    for label, actual, expected in (
            ("tenant", selection.tenant_id, expected_tenant_id),
            ("location", selection.location_id, expected_location_id),
            ("launch", selection.launch_id, expected_launch_id)):
        if expected is not None and actual != expected:
            return SelectionDecision(
                "recovery_choice",
                f"selection belongs to another {label}; it cannot be used in this checkout",
                selection.offer_id)
    if selection.quantity < 1:
        return SelectionDecision(
            "recovery_choice",
            "selection quantity is invalid; offer a recovery choice",
            selection.offer_id)
    if visitor_action == "change_package":
        # Doc 09 section 5: an explicit change-package action returns the
        # visitor to Product Selection (review defect D-3: this decision
        # was declared but unreachable).
        return SelectionDecision(
            "change_package",
            "visitor chose to change package; return to Product Selection",
            selection.offer_id)
    if selection.expires_at is not None and now > selection.expires_at:
        return SelectionDecision(
            "recovery_choice",
            "selection expired; offer a recovery choice or a fresh selection",
            selection.offer_id)
    if (selection.launch_revision != current_launch_revision
            or selection.offer_revision != current_offer_revision):
        return SelectionDecision(
            "reconfirm_changed_offer",
            "offer revision changed since selection; the visitor must reconfirm before charging",
            selection.offer_id)
    if (selection.native_price_id != current_native_price_id
            or selection.amount_minor != current_amount_minor
            or selection.currency != current_currency):
        return SelectionDecision(
            "reconfirm_changed_offer",
            "price binding changed since selection; the visitor must reconfirm before charging",
            selection.offer_id)
    return SelectionDecision("proceed", "selection validated against current offer and price binding",
                             selection.offer_id)
