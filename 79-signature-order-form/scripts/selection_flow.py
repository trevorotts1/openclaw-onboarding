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
Time (issue 77, CHK-07): `expires_at` and `now` are timezone-aware ISO-8601
date-times, parsed with bump_fixture_model.parse_aware and compared as
instants, never as strings. An integer, a naive or a junk time is refused by
name (SelectionTimeError, S79-SELECTION-TIME). Skill 78 keeps its session
clock in epoch seconds and hands this module an ISO `expires_at`
(selection_session.to_iso), so the seam carries one representation.
Billing (issue 78): the selection carries Skill 78's `billing_type` and its
schedule rows `{sequence, due, amount_minor}` (the checkout schema's row
shape); `billing_summary` is what the post-selection page renders.
Offer AVAILABILITY revalidation at checkout (doc 02 section 5) is an
S79-04/S78 seam item: this resolver checks identity, expiry, revision and
price binding; live availability comes from the native catalog read that
S78/S49 supply, and is named here rather than silently absent.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

# Load siblings even when this file is imported by path (no scripts/ on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bump_fixture_model import BumpError, parse_aware  # noqa: E402
from quote_display import format_minor  # noqa: E402

# Skill 78's selection.schema.json vocabulary: this module carries what the selection said, it does not translate it.
SELECTION_BILLING_TYPES = ("one_time", "recurring", "installment", "trial")


class SelectionTimeError(ValueError):
    """A selection time that is not a timezone-aware ISO-8601 date-time (CHK-07)."""
    code = "S79-SELECTION-TIME"


class SelectionBillingError(ValueError):
    """Billing terms a selection cannot carry: no or unknown billing type, or a schedule row of the wrong shape."""
    code = "S79-SELECTION-BILLING"


def _aware(label: str, value):
    try:
        return parse_aware(value, label)
    except BumpError as exc:
        raise SelectionTimeError(f"{exc} (CHK-07; got {type(value).__name__} {value!r})") from exc


def _schedule_rows(rows) -> tuple:
    """Schedule rows as ((sequence, due, amount_minor), ...), the shape quote_display.DisplayPrice takes.
    Accepts Skill 78's row objects or the tuples; anything else is refused. Sequences count up from 1 in order."""
    if rows in (None, ""):
        raise SelectionBillingError("selection schedule is missing; a one-time selection carries an empty list")
    if not isinstance(rows, (list, tuple)):
        raise SelectionBillingError("selection schedule must be a list of {sequence, due, amount_minor} rows")
    out = []
    for n, row in enumerate(rows, 1):
        if isinstance(row, Mapping):
            if set(row) != {"sequence", "due", "amount_minor"}:
                raise SelectionBillingError(
                    f"schedule row {n} must have exactly sequence, due and amount_minor; got {sorted(row)}")
            row = (row["sequence"], row["due"], row["amount_minor"])
        if not (isinstance(row, tuple) and len(row) == 3):
            raise SelectionBillingError(f"schedule row {n} must be {{sequence, due, amount_minor}}")
        sequence, due, amount = row
        if not (isinstance(sequence, int) and not isinstance(sequence, bool) and sequence >= 1):
            raise SelectionBillingError(f"schedule row {n} sequence must be an integer of at least 1")
        if sequence != n:
            raise SelectionBillingError(f"schedule row {n} has sequence {sequence}; sequences run 1, 2, 3 in order")
        if not (isinstance(due, str) and due.strip()):
            raise SelectionBillingError(f"schedule row {n} due must be non-empty text")
        if not (isinstance(amount, int) and not isinstance(amount, bool) and amount >= 0):
            raise SelectionBillingError(f"schedule row {n} amount_minor must be a non-negative integer of minor units")
        out.append((sequence, due, amount))
    return tuple(out)


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
    billing_type: str | None = None  # Skill 78's vocabulary; selection_from_intent always sets it
    schedule: tuple = ()  # ((sequence, due, amount_minor), ...)

    def __post_init__(self) -> None:
        if self.expires_at is not None:
            _aware("selection expires_at", self.expires_at)
        if self.billing_type is not None and self.billing_type not in SELECTION_BILLING_TYPES:
            raise SelectionBillingError(
                f"selection billing_type {self.billing_type!r} is not one of {SELECTION_BILLING_TYPES}")
        object.__setattr__(self, "schedule", _schedule_rows(self.schedule))


@dataclass(frozen=True)
class SelectionDecision:
    action: str  # proceed | recovery_choice | reconfirm_changed_offer | change_package
    reason: str
    offer_id: str | None


def selection_from_intent(intent: Mapping[str, Any], *, expires_at: str | None = None,
                          offer_revision: int | None = None) -> Selection:
    """The one adapter from Skill 78's selection.json intent to this module's
    Selection (the two shapes name the same facts differently: 78 carries
    amount_minor_snapshot and one revision, 79 wants amount_minor plus a
    launch and an offer revision). Refuses anything that is not a 78 intent
    or that carries no read-back native price id, so a launch-mode selection
    with null ids never becomes a checkout request. 78 versions the catalog
    once, so the offer revision defaults to the launch revision."""
    if intent.get("kind") != "selection_intent_not_payment_evidence":
        raise ValueError("not a Skill 78 selection intent")
    price_id = intent.get("native_price_id")
    if not isinstance(price_id, str) or not price_id.strip():
        raise ValueError("selection intent has no native_price_id; native product/price must be read back first")
    revision = int(intent["revision"])
    billing_type = intent.get("billing_type")
    if billing_type not in SELECTION_BILLING_TYPES:
        raise SelectionBillingError(
            f"selection intent billing_type {billing_type!r} is not one of {SELECTION_BILLING_TYPES}; "
            "the checkout cannot confirm billing terms it was never given")
    return Selection(
        offer_id=intent["offer_id"],
        native_price_id=price_id,
        amount_minor=int(intent["amount_minor_snapshot"]),
        currency=intent["currency"],
        quantity=int(intent.get("quantity", 1)),
        launch_revision=revision,
        offer_revision=revision if offer_revision is None else int(offer_revision),
        expires_at=expires_at,
        tenant_id=intent["tenant_id"],
        location_id=intent["location_id"],
        launch_id=intent["launch_id"],
        billing_type=billing_type,
        schedule=_schedule_rows(intent.get("schedule")),
    )


def billing_summary(selection: Selection, currency_exponent: int) -> dict:
    """The billing block the post-selection page renders, from the VALIDATED selection alone (never a URL or
    the visitor): the billing type and one row per scheduled payment with its amount formatted in the
    selection's currency at the given exponent. A selection that carries no billing terms is refused."""
    if selection.billing_type is None:
        raise SelectionBillingError("this selection carries no billing terms to show")
    return {
        "billing_type": selection.billing_type,
        "rows": [{"sequence": sequence, "due": due,
                  "amount": format_minor(amount, selection.currency, currency_exponent)}
                 for sequence, due, amount in selection.schedule],
    }


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
    now_at = _aware("now", now)  # CHK-07: an instant, never a string compare
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
    if selection.expires_at is not None and now_at > _aware("selection expires_at", selection.expires_at):
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
