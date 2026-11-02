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

MODE = "combined_single_offer"
# S79 fields the launch itself never holds; the caller supplies them or they stay missing.
COMMERCIAL_KEYS = ("terms_ref", "consent_ref", "native_capability_evidence_ref",
                   "fulfillment_mapping_ref", "failed_pending_requirements")
BUMP_KEYS = ("component_id", "component_version", "headline", "benefit_explanation",
             "quantity_policy", "fulfillment_rule_ref")


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
        "currency_exponent": _s78("selection_core").currency_exponent(price["currency"]),
        "amount_minor": price["amount_minor"],
        "billing_type": price["billing_type"],
        "native_product_id": offer.get("native_product_id"),
        "native_price_id": price.get("native_price_id"),
        "approval_status": "test_only" if test_only else price["approval_status"],
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
            plan = _s78("emit_binding_plan").emit_plan(launch, targets, route="per_offer_targets")
        except Exception as exc:
            raise CheckoutInstanceError(getattr(exc, "code", "AF-LAUNCH-CHECKOUT-BINDING"),
                                        str(exc)) from exc
    built = {
        "journey_mode": intake["journey_mode"],
        "surface": "native Convert and Flow order form installed by Skill 06",
        "dispatch_adapter": False,
        "checkout_mode": MODE,
        "instances": instances,
        "binding_plan": plan,
    }
    built["violations"] = check(built)
    return built


def check(built: Dict[str, Any]) -> List[str]:
    """Violations of the instance set; an empty list is a clean set."""
    out: List[str] = []
    instances = built["instances"]
    if not instances:
        out.append("AF-LAUNCH-CHECKOUT-NONE: no checkout instance")
    for field in ("slot", "page_id", "checkout_target_ref"):
        values = [i[field] for i in instances]
        if len(set(values)) != len(values):
            out.append(f"AF-LAUNCH-CHECKOUT-DUPLICATE: two instances share a {field}")
    for i in instances:
        if i["checkout_mode"] != MODE or i["selection_ref"] is not None:
            out.append(f"AF-LAUNCH-CHECKOUT-MODE: {i['slot']} is not a {MODE} request")
        if i["validation"]["result"] != "accepted":
            out.append(f"AF-LAUNCH-CHECKOUT-REJECTED: {i['slot']}: {i['validation'].get('error')}")
    plan = built.get("binding_plan")
    if plan is not None:
        targets = {(i["main_offer_id"], i["price_choice_id"]): i["checkout_target_ref"]
                   for i in instances}
        mapped = {(m["offer_id"], m["price_choice_id"]): m["checkout_target_ref"]
                  for m in plan["mappings"]}
        if mapped != targets:
            out.append("AF-LAUNCH-CHECKOUT-BINDING: the 78 binding plan does not reference "
                       "exactly the checkout instances")
    return out


def dispatch_rows(launch: Dict[str, Any], graph: Dict[str, Any], built: Dict[str, Any], *,
                  copy_profile: str, allowed_write_target: str) -> List[Dict[str, Any]]:
    """One Skill 49 checkout request per instance, carrying main_offer_id, selection_ref
    and the S78 target. Built from dispatch's own checkout request, so every other field
    (approval, brand, route hash) is the one dispatch already stamps."""
    dl = substrate.dispatch()
    base = next(r for r in dl.build_requests(launch, graph, copy_profile=copy_profile,
                                             allowed_write_target=allowed_write_target)
                if r["page_role"] == "checkout")
    rows: List[Dict[str, Any]] = []
    for inst in built["instances"]:
        ih = dl.request_input_hash(launch, inst["page_id"], "checkout")
        bump_id = inst["request"]["bump"]["offer_id"] if inst["bump_applies"] else None
        row = {**base,
               "page_id": inst["page_id"], "input_hash": ih,
               "request_id": dl.dispatch_key(launch, "checkout", ih),
               "offer_refs": [inst["main_offer_id"]] + ([bump_id] if bump_id else []),
               "role_instance": inst["role_instance"],
               "checkout_mode": inst["checkout_mode"],
               "main_offer_id": inst["main_offer_id"],
               "price_choice_id": inst["price_choice_id"],
               "selection_ref": inst["selection_ref"],
               "checkout_target_ref": inst["checkout_target_ref"]}
        fails = dl.validate_request(row)
        if fails:
            raise CheckoutInstanceError("AF-LAUNCH-CHECKOUT-DISPATCH", "; ".join(fails))
        rows.append(row)
    return rows
