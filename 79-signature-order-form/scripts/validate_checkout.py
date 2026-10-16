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
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "references" / "checkout.schema.json"
VERIFIED_STATUSES = {"locally_verified", "installed_test_verified",
                     "ready_for_activation", "live_verified"}


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
