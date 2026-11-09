"""One native checkout instance per main price choice (CHK-10, CHK-12).

GHL has no post-selection store: each package or level needs its own order form.
So the launch carries N checkout instances, one per (main offer, price choice),
each a Skill 79 ``combined_single_offer`` request with its own main and its own
bump applicability. ``multiple_options`` and ``folded_levels`` share this one
realisation; only the page in front of the checkout differs (selection page or
the folded signature page).

The route graph keeps its single ``checkout`` node. Each instance rides on it as
a ``role_instance`` (the same pattern as ``downsell_2`` on ``downsell_1``) with
its own page id, so Skill 78's ``per_offer_targets`` binding plan can point one
native target at each. Skill 78 and Skill 79 are called, never reimplemented.

Nothing commercial is invented: prices come from the Skill 49 launch record,
the bump applies only to the levels its ``included_in`` / ``requires``
relationships allow, and every other S79 field the launch does not hold is
taken from the caller's ``commercial`` facts or stays missing, in which case the
real S79 validator rejects the request and the rejection is recorded.

``selection_ref`` is always null: combined mode forbids one, and there is no
selection session to reference.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROUTES_DIR = Path(__file__).resolve().parent.parent / "routes"
if str(_ROUTES_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTES_DIR))

import substrate  # noqa: E402

from . import checkout as checkout_module  # noqa: E402
from . import launch_bridge  # noqa: E402

MODE = "combined_single_offer"
# S79 fields the launch itself never holds; the caller supplies them or they stay missing.
COMMERCIAL_KEYS = ("terms_ref", "consent_ref", "native_capability_evidence_ref",
                   "fulfillment_mapping_ref", "failed_pending_requirements")
BUMP_KEYS = ("component_id", "component_version", "headline", "benefit_explanation",
             "quantity_policy", "fulfillment_rule_ref")
# Facts that come only from the Skill 06 read-back; intake owns terms, consent and bump copy.
READBACK_KEYS = ("native_capability_evidence_ref", "fulfillment_mapping_ref",
                 "failed_pending_requirements", "bump", "native")
BUMP_READBACK_KEYS = ("component_id", "component_version", "quantity_policy", "fulfillment_rule_ref")


class CheckoutInstanceError(Exception):
    """Instances that cannot be built. Carries a stable autofail code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _s78(name: str):
    return substrate.load(f"78-signature-product-selection/scripts/{name}.py",
                          f"launcher_s78_{name}",
                          sibling_dir="78-signature-product-selection/scripts")


def _with_native(launch: Dict[str, Any], native: Dict[str, Any]) -> Dict[str, Any]:
    """Copy of the launch record with caller-supplied native ids, keyed by price_choice_id."""
    out = copy.deepcopy(launch)
    for offer in out["offers"]:
        for price in offer["prices"]:
            ids = native.get(price["price_choice_id"]) or {}
            if "native_product_id" in ids:
                offer["native_product_id"] = ids["native_product_id"]
            if "native_price_id" in ids:
                price["native_price_id"] = ids["native_price_id"]
    return out


def _price_choice(offer: Dict[str, Any], price: Dict[str, Any], test_only: bool) -> Dict[str, Any]:
    return {
        "price_choice_id": price["price_choice_id"],
        "currency": price["currency"],
        "currency_exponent": checkout_module.currency_exponent(price["currency"]),
        "amount_minor": price["amount_minor"],
        "billing_type": price["billing_type"],
        "native_product_id": offer.get("native_product_id"),
        "native_price_id": price.get("native_price_id"),
        # the checkout contract knows approved / recommended_unapproved / test_only; the record's "provided" is the
        # client's own price, i.e. approved (the same mapping shared-utils offer_mapper.record_to_checkout_request makes)
        "approval_status": "test_only" if test_only else (
            "recommended_unapproved" if price["approval_status"] == "recommended_unapproved" else "approved"),
    }


def bump_applies_to(intake: Dict[str, Any]) -> Dict[str, bool]:
    """{main offer id: does the bump apply to that level}. A bump already ``included_in``
    a level is not sold again there; ``requires`` narrows it to the listed levels."""
    offers = intake["offers"]
    bump = next((o for o in offers if o["role"] == "bump"), None)
    out = {o["offer_id"]: False for o in offers if o["role"] == "main"}
    if bump is None:
        return out
    included = set(bump["relationships"].get("included_in", []))
    requires = set(bump["relationships"].get("requires", []))
    for main_id in out:
        out[main_id] = main_id not in included and (not requires or main_id in requires)
    return out


def _next_route(graph: Dict[str, Any]) -> str:
    node = next((n for n in graph["nodes"] if n["role"] == "checkout"), None)
    if node is None:
        raise CheckoutInstanceError("AF-LAUNCH-CHECKOUT-NODE", "the route has no checkout node")
    role_of = {n["page_id"]: n["role"] for n in graph["nodes"]}
    edge = next(e for e in graph["edges"]
                if e["from"] == node["page_id"] and e["event"] == "payment_succeeded")
    return role_of[edge["to"]]


def commercial_facts(intake: Dict[str, Any], readback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The ``commercial`` dict ``build`` takes, each fact from the one source that owns it.

    Intake owns terms_ref / consent_ref (``checkout_terms``) and the bump copy (the bump
    offer's ``checkout`` block); the Skill 06 read-back owns the native ids, the
    capability and fulfillment refs, the failed/pending requirements and the bump
    component facts. A key missing from its source stays missing, so S79 rejects it.
    A read-back may not stand in for an intake-owned fact (CHK-16).
    """
    readback = readback or {}
    stray = sorted(set(readback) - set(READBACK_KEYS))
    if stray:
        raise CheckoutInstanceError("AF-LAUNCH-CHECKOUT-READBACK",
                                    f"the read-back may not supply {stray}; intake owns them")
    rb_bump = readback.get("bump") or {}
    stray = sorted(set(rb_bump) - set(BUMP_READBACK_KEYS))
    if stray:
        raise CheckoutInstanceError("AF-LAUNCH-CHECKOUT-READBACK",
                                    f"the read-back bump may not supply {stray}; intake owns them")
    terms = intake.get("checkout_terms") or {}
    out: Dict[str, Any] = {k: terms[k] for k in ("terms_ref", "consent_ref") if k in terms}
    for k in ("native_capability_evidence_ref", "fulfillment_mapping_ref",
              "failed_pending_requirements", "native"):
        if k in readback:
            out[k] = readback[k]
    bump_offer = next((o for o in intake["offers"] if o["role"] == "bump"), None)
    copy_block = (bump_offer or {}).get("checkout") or {}
    bump = {k: copy_block[k] for k in ("headline", "benefit_explanation") if k in copy_block}
    bump.update(rb_bump)
    if bump:
        out["bump"] = bump
    return out


def record(intake: Dict[str, Any], graph: Dict[str, Any], *, readback: Optional[Dict[str, Any]] = None,
           launch: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The one entry point for the package: instances, verdicts and binding plan for an intake."""
    # ponytail: the derived launch only carries price-choice ids (checkout never reads
    # image_provider or design_style, and the record is never written or dispatched, so the
    # style below is a placeholder for the plan-bound structure refs only); pass the dispatch
    # run's own launch record when assemble is bound to one.
    launch = launch or launch_bridge.to_launch_record(intake, graph, {"image_provider": "other_explicit", "design_style": "A"})
    return build(intake, graph, launch, commercial_facts(intake, readback))


def build(intake: Dict[str, Any], graph: Dict[str, Any], launch: Dict[str, Any],
          commercial: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The checkout instances for a launch, their S79 verdicts and the S78 binding plan.

    ``launch`` is the Skill 49 launch record (``launch_bridge.to_launch_record``).
    ``commercial`` holds what the launch does not: the COMMERCIAL_KEYS, ``bump``
    (BUMP_KEYS) and ``native`` ({price_choice_id: native ids}). Missing facts
    are never defaulted; the S79 validator rejects the request that lacks them.
    """
    commercial = commercial or {}
    launch = _with_native(launch, commercial.get("native") or {})
    test_only = bool(launch["test_only"])
    next_route = _next_route(graph)  # also refuses a route with no checkout node
    node = next(n for n in graph["nodes"] if n["role"] == "checkout")
    applies = bump_applies_to(intake)
    bump_offer = next((o for o in launch["offers"] if o["slot"] == "bump"), None)
    choices = [(o, p) for o in launch["offers"] if o["slot"] == "main" for p in o["prices"]]
    many = len(choices) > 1
    validator = substrate.s79_validate_checkout()
    required = checkout_module.required_fields(checkout_module.load_contract())

    instances: List[Dict[str, Any]] = []
    for offer, price in choices:
        slot = "checkout-" + price["price_choice_id"].lower() if many else None
        page_id = (substrate.compiler().page_id(launch["launch_id"], slot)
                   if slot else node["page_id"])
        bump = None
        if bump_offer is not None and applies[offer["offer_id"]]:
            bump = {
                **{k: commercial["bump"][k] for k in BUMP_KEYS if k in (commercial.get("bump") or {})},
                "enabled": True,
                "offer_id": bump_offer["offer_id"],
                "applicable_main_offer_ids": [offer["offer_id"]],
                "entitlement_ids": list(bump_offer["entitlement_ids"]),
                "price": _price_choice(bump_offer, bump_offer["prices"][0], test_only),
                "default_selected": False,
                "native_product_id": bump_offer.get("native_product_id"),
                "native_price_id": bump_offer["prices"][0].get("native_price_id"),
            }
        request = {
            "tenant_id": launch["tenant_id"],
            "location_id": launch["location_id"],
            "launch_id": launch["launch_id"],
            "launch_revision": launch["revision"],
            "launch_plan_approval_ref": launch["plan_approval_ref"],
            "approved_plan_hash": intake["approval"]["hash"],
            "checkout_mode": MODE,
            "main_offer_id": offer["offer_id"],
            "main_price": _price_choice(offer, price, test_only),
            "quantity": 1,  # single-quantity order form; not a commercial fact
            "selection_ref": None,
            "selection_revision": None,
            "main_entitlement_ids": list(offer["entitlement_ids"]),
            "previously_purchased_entitlement_ids": [],
            "bump": bump,
            "brand_ref": launch["brand_ref"],
            "brand_revision": launch["brand_hash"],
            "successful_payment_next_route": next_route,
            "test_only": test_only,
            **{k: commercial[k] for k in COMMERCIAL_KEYS if k in commercial},
        }
        try:
            validator.validate_request(request)
            verdict: Dict[str, Any] = {"result": "accepted"}
        except Exception as exc:  # the contract's own typed error is the record
            verdict = {"result": "rejected", "error": str(exc)}
        instances.append({
            "role": "checkout",
            "role_instance": slot,
            "slot": slot or "checkout",
            "page_id": page_id,
            "main_offer_id": offer["offer_id"],
            "price_choice_id": price["price_choice_id"],
            "checkout_mode": MODE,
            "selection_ref": None,
            "checkout_target_ref": page_id,
            "bump_applies": bump is not None,
            "request": request,
            "missing": sorted(f for f in required if f not in request),
            "validation": verdict,
        })

    plan = None
    if len({o["offer_id"] for o, _ in choices}) > 1:  # S78 declines a single main
        targets = [{"offer_id": i["main_offer_id"], "price_choice_id": i["price_choice_id"],
                    "native_product_id": i["request"]["main_price"]["native_product_id"],
                    "native_price_id": i["request"]["main_price"]["native_price_id"],
                    "target_ref": i["checkout_target_ref"]} for i in instances]
        try:
            # Skill 78 (U-products-07) declines any journey mode but multiple_options. This per-offer
            # route has no selection page for any journey (folded_levels included): one native
            # target per main price choice is the realisation, so 78 judges the catalog and targets
            # as the multiple-options shape they are. The launch itself is not altered.
            plan = _s78("emit_binding_plan").emit_plan(dict(launch, journey_mode="multiple_options"), targets,
                                                       route="per_offer_targets")
        except Exception as exc:
            raise CheckoutInstanceError(getattr(exc, "code", "AF-LAUNCH-CHECKOUT-BINDING"),
                                        str(exc)) from exc
    built = {
        "journey_mode": intake["journey_mode"],
        "surface": "native Convert and Flow order form installed by Skill 06",
        "dispatch_adapter": False,
        "realisation": "per_offer_instances",
        "checkout_mode": MODE,
        "instances": instances,
        "binding_plan": plan,
    }
    built["violations"] = check(built)
    return built


def check(built: Dict[str, Any]) -> List[str]:
    """Violations of the instance set; an empty list is a clean set."""
    out: List[str] = []
    instances = built.get("instances") or []
    if not instances:
        out.append("AF-LAUNCH-CHECKOUT-NONE: no checkout instance")
    for n, i in enumerate(instances):
        for field in ("slot", "page_id", "checkout_target_ref", "main_offer_id", "price_choice_id",
                      "checkout_mode", "validation"):
            if field not in i:
                out.append(f"AF-LAUNCH-CHECKOUT-FIELD: instance {n} has no {field}")
    for field in ("slot", "page_id", "checkout_target_ref"):
        values = [i[field] for i in instances if field in i]
        if len(set(values)) != len(values):
            out.append(f"AF-LAUNCH-CHECKOUT-DUPLICATE: two instances share a {field}")
    for i in instances:
        if i.get("checkout_mode") != MODE or i.get("selection_ref") is not None:
            out.append(f"AF-LAUNCH-CHECKOUT-MODE: {i.get('slot')} is not a {MODE} request")
        validation = i.get("validation") or {}
        if validation.get("result") != "accepted":
            out.append(f"AF-LAUNCH-CHECKOUT-REJECTED: {i.get('slot')}: {validation.get('error')}")
    plan = built.get("binding_plan")
    if plan is not None:
        targets = {(i.get("main_offer_id"), i.get("price_choice_id")): i.get("checkout_target_ref")
                   for i in instances}
        mapped = {(m.get("offer_id"), m.get("price_choice_id")): m.get("checkout_target_ref")
                  for m in plan.get("mappings") or []}
        if mapped != targets:
            out.append("AF-LAUNCH-CHECKOUT-BINDING: the 78 binding plan does not reference "
                       "exactly the checkout instances")
    return out


def replay_violations(rec: Dict[str, Any]) -> List[str]:
    """``check`` plus a fresh S79 verdict per request; a recorded verdict is never trusted."""
    out = check(rec)
    validator = substrate.s79_validate_checkout()
    for i in rec.get("instances") or []:
        slot = i.get("slot")
        req = i.get("request")
        if not isinstance(req, dict):
            out.append(f"AF-LAUNCH-CHECKOUT-REPLAY: {slot} has no request to replay")
            continue
        try:
            validator.validate_request(req)
            now = "accepted"
        except Exception:
            now = "rejected"
        recorded = (i.get("validation") or {}).get("result")
        if now != recorded:
            out.append(f"AF-LAUNCH-CHECKOUT-REPLAY: {slot} recorded {recorded}, "
                       f"the S79 contract says {now}")
        if (req.get("main_offer_id") != i.get("main_offer_id") or req.get("checkout_mode") != MODE
                or req.get("selection_ref") is not None):
            out.append(f"AF-LAUNCH-CHECKOUT-MODE: {slot} request is not a {MODE} request "
                       "for its own main")
    return out
