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
- A `recommended_unapproved` price (a stated price the client has not separately
  approved) is production-bound only when the plan approval covers it: the request's
  `launch_plan_approval_ref` must be a `launch_plan_build` approval for
  `approved_plan_hash` that the ONE shared verifier (shared-utils approval_record.verify,
  a Command Center read) confirms. This is the same rule Skill 78 applies when it lets
  the selection page show that price (decision D-C, issue 71). A reference the verifier
  cannot confirm, or a verifier that is not installed, refuses the price.
"""
from __future__ import annotations

import importlib.util
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
PLAN_APPROVAL_KIND = "launch_plan_build"
# The one approval verifier lives beside this skill in the skills tree (repo checkout or installed).
APPROVAL_RECORD = Path(__file__).resolve().parents[2] / "shared-utils" / "signature_launch_contract" / "approval_record.py"


class CheckoutValidationError(ValueError):
    pass


def _schema():
    return json.loads(SCHEMA_PATH.read_text())


def _validate_def(name: str, instance, *, relax: dict | None = None) -> None:
    schema = _schema()
    if relax:
        # `relax` maps a definition name to keys the caller may leave out (copy requests only); every other
        # rule of every definition still applies, and a key that is present is checked in full.
        defs = dict(schema["$defs"])
        for def_name, keys in relax.items():
            d = dict(defs[def_name])
            d["required"] = [k for k in d["required"] if k not in keys]
            defs[def_name] = d
        schema = dict(schema, **{"$defs": defs})
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


def _shared_verify():
    """approval_record.verify, loaded by path. Not installed means no approval can be confirmed."""
    if not APPROVAL_RECORD.is_file():
        raise CheckoutValidationError(
            "the shared approval verifier (approval_record.py) is not installed, so no plan approval can be confirmed")
    spec = importlib.util.spec_from_file_location("approval_record_s79", APPROVAL_RECORD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify


def _require_plan_approval(label: str, request: dict) -> None:
    """Refuse unless the request's plan approval is a Command Center `launch_plan_build` record for
    its approved plan hash (issue 71). Every failure of the verifier, whatever its type, is a refusal.
    There is no verifier argument and no flag: the only verifier is the shared one (_shared_verify, which
    a test patches by name), so a caller cannot hand this gate its own."""
    ref, plan_hash = request.get("launch_plan_approval_ref"), request.get("approved_plan_hash")
    if _blank(ref) or _blank(plan_hash):
        raise CheckoutValidationError(
            f"production-bound {label} price is only a recommendation and the request names no plan approval "
            "and plan hash to cover it")
    try:
        verify = _shared_verify()
        got = verify(ref, PLAN_APPROVAL_KIND, plan_hash, [PLAN_APPROVAL_KIND], test_only=False)
    except CheckoutValidationError:
        raise
    except Exception as exc:  # ApprovalRefused / ApprovalUnavailable: neither is an approval
        raise CheckoutValidationError(
            f"production-bound {label} price is only a recommendation and its plan approval could not be "
            f"confirmed ({getattr(exc, 'code', type(exc).__name__)}: {exc})") from exc
    if not (isinstance(got, dict) and got.get("ok") is True and got.get("kind") == PLAN_APPROVAL_KIND
            and got.get("approval_id") == ref and got.get("authority") == "command-center"):
        raise CheckoutValidationError(
            f"production-bound {label} price is only a recommendation and {ref!r} is not a "
            f"{PLAN_APPROVAL_KIND} plan approval recorded in Command Center")


def _check_production_price(label: str, price: dict, request: dict) -> None:
    status = price.get("approval_status")
    if status not in ("approved", "recommended_unapproved"):
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
    if status == "recommended_unapproved":  # last: the one Command Center read happens only for an otherwise sound price
        _require_plan_approval(label, request)


def _check_production_bump(request: dict, bump: dict) -> None:
    main = request["main_price"]
    price = bump["price"]
    _check_production_price("bump", price, request)
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


# The three facts only Skill 06's native read-back can supply. The page COPY needs none of them, so
# validate_copy_request leaves them optional; validate_request (the production gate) requires them.
READBACK_FACTS = ("native_capability_evidence_ref", "fulfillment_mapping_ref", "failed_pending_requirements")
# The order bump's own read-back facts (Skill 83 checkout_instances.BUMP_READBACK_KEYS): the same Skill 06
# read-back, carried inside the bump block, equally unused by the copy.
BUMP_READBACK_FACTS = ("component_id", "component_version", "quantity_policy", "fulfillment_rule_ref")
COPY_RELAX = {"checkout_request": READBACK_FACTS, "bump_config": BUMP_READBACK_FACTS}


def validate_copy_request(request: dict, now: str | None = None) -> None:
    """validate_request without the Skill 06 read-back keys being required (the copy emitter's gate).

    Everything else is unchanged: the full schema, mapping expiry, price approval, bump gates. A read-back key
    that IS present is validated like any other. This is never the production gate."""
    validate_request(request, now, _relax=COPY_RELAX)


def validate_request(request: dict, now: str | None = None, *, _relax: dict | None = None) -> None:
    _validate_def("checkout_request", request, relax=_relax)
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
        _check_production_price("main", request["main_price"], request)
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
