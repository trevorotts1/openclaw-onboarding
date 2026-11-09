"""Cross-field validator for S79 checkout documents (doc 09 sections 3, 6, 9;
doc 02 section 6). JSON Schema cannot compare two fields or make a field
required based on a sibling in another object, so the rules the independent
review flagged as C4/C5 live here, on top of schema validation:

- A verified-or-better result must name a reviewer who is NOT its producer.
- A non-test (production-bound) request must carry real native product and
  price IDs for the main offer and for an enabled bump; test_only documents
  may carry null native IDs and must say so.
- An enabled bump in a production-bound request must carry a native mapping
  that has not expired at validation time (caller supplies `now`).
- A production-bound request must also be approved, non-zero, same currency
  and exponent across main and bump, offerable (applicable, not already owned
  or included), carry recurrence terms by billing type, and supply `now`
  (CHK-06). Mapping expiry is compared as tz-aware datetimes (CHK-07).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# PYDEPS-ACTIVATION:BEGIN (shared contract, byte-identical in every file that imports jsonschema; stdlib only)
# jsonschema lives in <root>/pydeps/py<X.Y>/ when pip refuses the interpreter (PEP 668); put it on sys.path first.
import os as _os
import sys as _sys

_pytag = "py%d.%d" % _sys.version_info[:2]
_pyroot = _os.environ.get("OPENCLAW_ROOT") or (
    "/data/.openclaw" if _os.path.isdir("/data/.openclaw") else _os.path.expanduser("~/.openclaw"))
_sys.path[:0] = [_d for _d in (
    [_os.environ["OC_PYDEPS_DIR"]] if _os.environ.get("OC_PYDEPS_DIR") else
    [_os.path.join(_pyroot, "pydeps", _pytag), _os.path.expanduser("~/.claude/pydeps/" + _pytag)])
    if _os.path.isdir(_d) and _d not in _sys.path]
del _pytag, _pyroot
# PYDEPS-ACTIVATION:END

import jsonschema

# Load siblings even when this file is imported by path (no scripts/ on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bump_fixture_model import BumpConfig, BumpError, PriceChoice, initial_quote, parse_aware  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "references" / "checkout.schema.json"
VERIFIED_STATUSES = {"locally_verified", "installed_test_verified",
                     "ready_for_activation", "live_verified"}
RECURRING = ("recurring", "trial_then_recurring")


class CheckoutValidationError(ValueError):
    pass


def _schema():
    return json.loads(SCHEMA_PATH.read_text())


def _validate_def(name: str, instance) -> None:
    schema = _schema()
    sub = {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": f"#/$defs/{name}"}
    try:
        jsonschema.validate(instance, sub, format_checker=jsonschema.FormatChecker())
    except jsonschema.ValidationError as exc:
        raise CheckoutValidationError(f"{name} schema validation failed: {exc.message}") from exc


def _aware(label: str, value):
    try:
        return parse_aware(value, label)
    except BumpError as exc:
        raise CheckoutValidationError(str(exc)) from exc


def _check_mapping_expiry(label: str, expires_at, now: str | None) -> None:
    if expires_at is None:
        return
    # CHK-07: parse both sides as tz-aware datetimes; junk or naive values are
    # refused, never treated as "not expired".
    expires = _aware(f"{label} price_mapping_expires_at", expires_at)
    if now is not None and _aware("now", now) >= expires:
        raise CheckoutValidationError(f"{label} native price mapping is expired")


def _blank(value) -> bool:
    return not (isinstance(value, str) and value.strip())


def _check_production_price(label: str, price: dict) -> None:
    if price.get("approval_status") != "approved":
        raise CheckoutValidationError(f"production-bound {label} price must be approved (approval_status 'approved')")
    if price["amount_minor"] <= 0:
        raise CheckoutValidationError(f"production-bound {label} price must be greater than zero")
    if _blank(price.get("native_product_id")) or _blank(price.get("native_price_id")):
        raise CheckoutValidationError(
            f"production-bound request requires native product and price IDs for the {label} price (C5)")
    billing = price["billing_type"]
    if billing in RECURRING and _blank(price.get("recurring_interval")):
        raise CheckoutValidationError(f"{label} recurring price requires recurring_interval")
    if billing == "trial_then_recurring" and _blank(price.get("trial_period")):
        raise CheckoutValidationError(f"{label} trial price requires trial_period")
    due = price.get("amount_due_now_minor")
    if due is not None and due > price["amount_minor"]:
        raise CheckoutValidationError(f"{label} amount_due_now_minor exceeds amount_minor")


def _check_production_bump(request: dict, bump: dict) -> None:
    main = request["main_price"]
    price = bump["price"]
    _check_production_price("bump", price)
    if _blank(bump.get("native_product_id")) or _blank(bump.get("native_price_id")):
        raise CheckoutValidationError(
            "production-bound request requires native product and price IDs for the bump (C5)")
    if bump["offer_id"] == request["main_offer_id"]:
        raise CheckoutValidationError("bump offer_id must differ from the main offer")
    if price["currency_exponent"] != main["currency_exponent"]:
        raise CheckoutValidationError("bump currency exponent does not match main offer exponent")
    # Reuse the fixture model's rules (currency, applicability, included or
    # previously purchased entitlement) instead of restating them here.
    try:
        config = BumpConfig(
            component_id=bump["component_id"], enabled=True, offer_id=bump["offer_id"],
            price=PriceChoice(price["price_choice_id"], price["currency"], price["amount_minor"],
                              price["billing_type"]),
            entitlement_ids=frozenset(bump["entitlement_ids"]),
            applicable_main_offer_ids=frozenset(bump["applicable_main_offer_ids"]),
            default_selected=bump["default_selected"], quantity_policy=bump["quantity_policy"],
            # The request carries recurrence terms (validated above) rather than a disclosure flag.
            recurring_disclosure_required=price["billing_type"] != "one_time")
        quote = initial_quote(
            request["main_offer_id"],
            PriceChoice(main["price_choice_id"], main["currency"], main["amount_minor"], main["billing_type"]),
            request["quantity"], frozenset(request["main_entitlement_ids"]), config,
            frozenset(request["previously_purchased_entitlement_ids"]))
    except BumpError as exc:
        raise CheckoutValidationError(f"bump refused: {exc}") from exc
    if quote.bump_state != "offered_unchecked":
        raise CheckoutValidationError(
            f"bump cannot be offered on this order: {quote.bump_state} ({quote.suppression_source})")


def validate_request(request: dict, now: str | None = None) -> None:
    _validate_def("checkout_request", request)
    # Review defect A2: expiry must be checked in every location the schema
    # defines it, not only the bump's top-level field: the main price choice,
    # the bump price choice, and the bump config itself.
    _check_mapping_expiry("main", request["main_price"].get("price_mapping_expires_at"), now)
    bump = request.get("bump")
    if bump:
        _check_mapping_expiry("bump", bump.get("price_mapping_expires_at"), now)
        _check_mapping_expiry("bump price", (bump.get("price") or {}).get("price_mapping_expires_at"), now)
    if request.get("test_only") is False:
        if now is None:
            raise CheckoutValidationError("production-bound request requires `now` to check mapping expiry")
        _check_production_price("main", request["main_price"])
        if not request["main_entitlement_ids"]:
            raise CheckoutValidationError("production-bound request requires main_entitlement_ids")
        if request["checkout_mode"] == "post_selection" and not request.get("selection_revision"):
            raise CheckoutValidationError("post_selection request requires selection_revision")
        if bump and bump.get("enabled"):
            _check_production_bump(request, bump)


def validate_result(result: dict) -> None:
    _validate_def("checkout_result", result)
    if result.get("status") in VERIFIED_STATUSES:
        reviewer = result.get("reviewer_id")
        if not reviewer:
            raise CheckoutValidationError("verified result requires a reviewer_id")
        if reviewer == result.get("producer_id"):
            raise CheckoutValidationError(
                "reviewer must differ from producer; a result cannot be its own independent review (C4)")
