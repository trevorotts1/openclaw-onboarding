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
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "references" / "checkout.schema.json"
VERIFIED_STATUSES = {"locally_verified", "installed_test_verified",
                     "ready_for_activation", "live_verified"}
_REQUIRED_MESSAGE = re.compile(r"^'([^']+)' is a required property$")


class CheckoutValidationError(ValueError):
    pass


def _schema():
    return json.loads(SCHEMA_PATH.read_text())


def _validate_def(name: str, instance) -> None:
    schema = _schema()
    sub = {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": f"#/$defs/{name}"}
    try:
        jsonschema.validate(instance, sub)
    except jsonschema.ValidationError as exc:
        raise CheckoutValidationError(f"{name} schema validation failed: {exc.message}") from exc


def request_failures(request: dict) -> list[dict]:
    """Every JSON-Schema failure for one ``checkout_request``, as typed data.

    ``validate_request`` raises on the first failure, which is enough to refuse
    a document but not enough to say WHY it was refused. A binding probe needs
    to tell "this launch still has named unknown facts" apart from "this
    document carries a field the contract does not define". Each failure is::

        {"kind": "<jsonschema keyword>", "path": "bump/price",
         "missing": "<required property name>" (kind == "required" only),
         "message": "<contract wording>"}

    ``schema_version`` is deliberately absent from the result: it belongs to
    the contract's outer envelope and is never a member of this $def.
    """
    schema = _schema()
    sub = {"$schema": schema["$schema"], "$defs": schema["$defs"],
           "$ref": "#/$defs/checkout_request"}
    validator = jsonschema.Draft202012Validator(sub)
    failures = []
    for error in validator.iter_errors(request):
        failure = {
            "kind": error.validator,
            "path": "/".join(str(part) for part in error.absolute_path),
            "message": error.message,
        }
        if error.validator == "required":
            match = _REQUIRED_MESSAGE.match(error.message)
            if match:
                failure["missing"] = match.group(1)
        failures.append(failure)
    return sorted(failures, key=lambda f: (f["path"], f["kind"], f.get("missing", "")))


def contract_control() -> dict:
    """A minimal synthetic request the contract's own schema accepts.

    This is the known-good control for a binding probe: it proves the
    validator CAN accept, so a rejection of a real document is a fact about
    that document rather than a broken instrument. Every value is a synthetic
    test value - no launch fact, no commercial default, no native ID.
    """
    return {
        "tenant_id": "control-tenant",
        "location_id": "control-location",
        "launch_id": "control-launch",
        "launch_revision": 1,
        "launch_plan_approval_ref": "control-approval",
        "approved_plan_hash": "0" * 64,
        "checkout_mode": "combined_single_offer",
        "main_offer_id": "control-main-offer",
        "main_price": {
            "price_choice_id": "control-price",
            "currency": "USD",
            "currency_exponent": 2,
            "amount_minor": 1,
            "billing_type": "one_time",
            "native_product_id": None,
            "native_price_id": None,
            "approval_status": "test_only",
            "price_mapping_expires_at": None,
        },
        "quantity": 1,
        "selection_ref": None,
        "main_entitlement_ids": [],
        "previously_purchased_entitlement_ids": [],
        "bump": None,
        "brand_ref": "control-brand",
        "brand_revision": "0" * 64,
        "terms_ref": "control-terms",
        "native_capability_evidence_ref": "control-capability",
        "successful_payment_next_route": "thank-you",
        "fulfillment_mapping_ref": "control-fulfillment",
        "test_only": True,
        "consent_ref": "control-consent",
        "failed_pending_requirements": {
            "failed_state_copy_ref": "control-failed-copy",
            "pending_state_copy_ref": "control-pending-copy",
            "retry_policy": "reconcile_native_records_first",
            "requires_customer_action_copy_ref": None,
        },
    }


def _check_mapping_expiry(label: str, expires_at, now: str | None) -> None:
    if now is not None and expires_at is not None and now > expires_at:
        raise CheckoutValidationError(f"{label} native price mapping is expired")


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
        main_price = request["main_price"]
        if not main_price.get("native_product_id") or not main_price.get("native_price_id"):
            raise CheckoutValidationError(
                "production-bound request requires native product and price IDs for the main offer (C5)")
        bump = request.get("bump")
        if bump and bump.get("enabled"):
            if not bump.get("native_product_id") or not bump.get("native_price_id"):
                raise CheckoutValidationError(
                    "production-bound request requires native product and price IDs for the bump (C5)")
            expiry = bump.get("price_mapping_expires_at")
            if now is not None and expiry is not None and now > expiry:
                raise CheckoutValidationError("bump native price mapping is expired")


def validate_result(result: dict) -> None:
    _validate_def("checkout_result", result)
    if result.get("status") in VERIFIED_STATUSES:
        reviewer = result.get("reviewer_id")
        if not reviewer:
            raise CheckoutValidationError("verified result requires a reviewer_id")
        if reviewer == result.get("producer_id"):
            raise CheckoutValidationError(
                "reviewer must differ from producer; a result cannot be its own independent review (C4)")
