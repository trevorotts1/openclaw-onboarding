#!/usr/bin/env python3
"""ghl_order_elements.py - S06-06: the THINK layer for native GHL order
elements (prep steps 4-5, gaps 1-4).

WHAT EXISTS AND WHAT THIS MODULE ADDS
-------------------------------------
Before S06-06 the tree had NO native order-element builder: no module
created, configured, bound, or read back any native order element, and no
code bound a product to a page, form, or order element. The form builder's
generic F5 machinery WOULD drag a named Payments Quick-Add tile ("Sell
Products" / "Collect Payment", ``ghl_form_builder.QUICK_ADD_TAXONOMY``) onto
a canvas as an ordinary standard field - but with NO order-specific
placement step, NO product configuration or assignment, and NO verification
of a selected product afterwards; no default task, example plan, or test
included a Payments tile.

This module is the missing THINK layer, following the form builder's hard
two-layer split (intelligence here, dumb execution in the browser layer):

  * :func:`build_order_plan` turns an order spec into an explicit,
    validated plan: which native elements are placed (order form /
    collect-payment tiles through the form builder's F5 Quick-Add path, the
    order bump, the one-click upsell, the downsell), which product each
    element is bound to, and what must be verified afterwards.
  * :func:`verify_order_render` checks RENDERED / read-back evidence against
    the plan: the selected product matches the binding, and the bump's
    default state is UNCHECKED - verified in the rendered page, never in
    stored bytes (prep step 5).
  * :func:`form_task_patch` returns the ``order_binding`` a caller merges
    into a ``ghl_form_builder`` task dict so the form builder's preflight
    (F-P10) and F5 placement guard recognize the Payments tiles as ORDER
    elements with a binding instead of ordinary fields.

PRODUCT BINDINGS - FAIL CLOSED, NEVER FABRICATED
------------------------------------------------
An order element is meaningless without a product binding, so every element
in a plan MUST carry one, and the plan builder FAILS CLOSED when one is
missing or malformed. A binding is a reference ONLY:

    {"product_ref": "<reference, carried verbatim>",
     "source": "caller_supplied" | "s44_phase_a",
     "offer_id": "<optional: the approved offer record's own id>",
     "price_ref": "<optional: the read-back price id>",
     "billing": {"billing_type": "...", ...}}       # optional, carried verbatim

``product_ref`` is whatever identifier the caller supplies - an S44 Phase A
product reference when Phase A delivers one (prep Q2; NOT delivered at the
time of this build, so plans today carry ``caller_supplied`` references),
otherwise an explicitly caller-supplied reference. This module NEVER
invents an S44 ID, a price, a variant, or catalog data. A binding may carry
a ``price_ref`` (the read-back price id) but never an amount: pricing lives
with the product's owner, not in a placement plan.

BUMP DEFAULT (packet section 9 acceptance shape)
------------------------------------------------
An order bump's default state is UNCHECKED. A spec that asks for a
pre-checked bump is refused (:class:`OrderPlanError`): pre-checked consent /
offer boxes are not a state this builder will plan.

CHECKOUT SURFACE (CHK-19, prep Q3 - decided 2026-11-02, DECISIONS.md)
--------------------------------------------------------------------
The plan targets the GHL FUNNEL ORDER-FORM STEP (``SURFACE_FUNNEL_ORDER_STEP``):
the order form, the order bump and the post-purchase steps are elements of
the funnel's own checkout step. The form builder's Payments Quick-Add tiles
are NOT the checkout surface; ``tile`` on an element is only the legacy name
of the native element, and ``placement.target`` is where it goes. Undo: swap
the driver target. One live capture of that step on Trevor's named TEST
location (never a client's) is still OWNER-OPEN; until it exists the plan is
fixture-verified only.

PRICE BINDING
-------------
A binding may carry ``price_ref`` - the read-back price id (never an amount,
never invented; the major/minor unit question is also open until the live
capture). When present, the rendered read-back must show that same price.

BUMP PLACEMENT AND PRODUCT VERIFICATION
---------------------------------------
The bump has its own placement step (``add_order_bump``, after the order
form) and its selected product is verified against its binding
(``bump_selected_product_matches_binding``) - the bump used to attach any
product unnoticed.

ONE APPROVED ROUTE GRAPH, DISTINCT SLOTS
----------------------------------------
:func:`approved_routes` READS the approved route graph compiled by Skill 49
(``49-signature-funnel/scripts/compile_launch_route.py``) and nothing else
plans a route here. The plan carries the graph's own page ids and its paid /
explicit-decline edges per offer slot, so page generation, the native button
configuration and the workflow delivery all consume the same graph. A
failed or pending payment traverses no edge and is never a decline
(``payment_recovery`` says so on the plan's face).

Every offer has a distinct slot identity (``main``, ``collect_payment``,
``bump``, ``upsell_1``, ``downsell_1``, ``upsell_2``) and its bindings are
keyed by slot, so two upsells cannot share one generic key or overwrite each
other. The approved sequence is the graph's: main paid -> U1; U1 paid -> U2;
U1 declined -> D1; D1 paid -> the SAME U2; D1 declined -> thank-you; U2 paid
or declined -> thank-you.

NATIVE CHECKOUT FAMILY AND NATIVE PURCHASE ACTIONS
--------------------------------------------------
An extra offer's purchase action is a NATIVE one-click action bound to the
bound product and price inside the native payment session
(``native_action``); ``action_id`` stays null until Skill 6 records the
installed binding. A link/button that navigates to a thank-you page is NOT a
purchase action and is refused. The native checkout family is identified
before an upsell sequence is planned (``checkout_family``): Order Upsell in
Forms is a V2 funnel on the same domain; Store Upsell is a Website page
using the native Upsell element. A plan built without the family and graph
keeps its slot identities but is marked ``install_ready: false`` with a
named blocker - it is never presented as an install plan.

EVIDENCE MUST COME FROM THE CAPTURE FUNCTION
--------------------------------------------
:func:`capture_order_render` is the only producer of render evidence. It
wraps the browser layer's read-back with the plan hash, source, capture time
and a ``provenance_hash``. :func:`verify_order_render` with
``require_capture=True`` (what ``--verify-render`` always uses) refuses a
bare / hand-written dict and any envelope whose hash or plan hash does not
recompute. ponytail: a plain sha256 is tamper-evidence, not authentication;
a signing key owned by the browser layer is the upgrade if forging by hand
ever matters.

WHAT THIS MODULE DOES NOT DO
----------------------------
No browser, no network, no GHL writes. The driver that clicks through the
funnel order-form step consumes ``plan["steps"]``; the native styling
surface, the two saves, ``render_check``, and receipts ride the existing
rails (prep steps 7-8). Live placement proof stays LIVE_PROOF_PENDING until
Trevor's named test location is used for the one live capture.

CLI
---
    python3 ghl_order_elements.py --selftest
    python3 ghl_order_elements.py --plan <spec.json>   # print the plan JSON
    python3 ghl_order_elements.py --verify-render <plan.json> <evidence.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from typing import Any, List, Optional

PLAN_SCHEMA = "skill6-order-plan/1"

#: The Payments category of ghl_form_builder.QUICK_ADD_TAXONOMY. These two
#: tiles are the native order elements placeable through the form builder's
#: F5 Quick-Add path; every other tile is an ordinary form field.
TILE_ORDER_FORM = "Sell Products"
TILE_COLLECT_PAYMENT = "Collect Payment"
PAYMENTS_TILES = (TILE_ORDER_FORM, TILE_COLLECT_PAYMENT)
QUICK_ADD_CATEGORY = "Payments"

#: Element kinds a plan can carry.
KIND_ORDER_FORM = "order_form"
KIND_COLLECT_PAYMENT = "collect_payment"
KIND_ORDER_BUMP = "order_bump"
KIND_UPSELL = "upsell"
KIND_DOWNSELL = "downsell"
KIND_THANK_YOU = "thank_you"
KIND_LEAD_CAPTURE = "lead_capture"

#: Where the order elements live (decision 2026-11-02): the funnel's
#: order-form step, not the form builder's Payments tiles.
SURFACE_FUNNEL_ORDER_STEP = "funnel_order_form_step"
EVIDENCE_SCHEMA = "skill6-order-render-evidence/1"
CAPTURE_TOOL = "ghl_order_elements.capture_order_render"
EVIDENCE_SOURCES = ("live", "fixture")

#: Where a product binding may come from. There is no third source: a
#: reference is either delivered by S44 Phase A or explicitly supplied by
#: the caller of this build. Anything else is refused.
BINDING_SOURCES = ("caller_supplied", "s44_phase_a")

#: Billing terms the native price/checkout surface can actually express
#: (shared-utils/ghl/products_prices.py BILLING_TYPES — the CreatePriceDto
#: shape). A term outside this set is CARRIED and refused at bind time with a
#: named reason, never rewritten into ``one_time``: flattening a recurring or
#: installment offer into a single charge changes what the buyer is charged.
NATIVE_BILLING_TYPES = ("one_time", "recurring", "trial_then_recurring")
#: The APPROVED offer record's own vocabulary (Skill 49 launch schema price
#: entry). It is not the native one: an approved ``trial`` is a native
#: ``trial_then_recurring``. Translating here, once, is what keeps an approved
#: recurring/trial term from being refused as unknown -- or bound as one_time.
APPROVED_BILLING_TYPES = ("one_time", "recurring", "trial", "installment")
APPROVED_TO_NATIVE = {"one_time": "one_time", "recurring": "recurring",
                      "trial": "trial_then_recurring"}
RECURRING_INTERVALS = ("day", "week", "month", "year")
#: Approved F08 terms with NO native price shape here. They are recognised so
#: the refusal names the real reason instead of "unknown billing_type".
UNSUPPORTED_BILLING_TERMS = ("installment", "installments")
BILLING_TERM_FIELDS = ("billing_type", "recurring_interval", "trial_days",
                       "installment_count", "installment_interval")
BILLING_NOT_NATIVE = (
    "installment billing has no native CreatePriceDto shape on this surface "
    "(products_prices.BILLING_TYPES is one_time|recurring|trial_then_recurring); "
    "refusing to flatten an installment offer into one_time")

#: THE APPROVED ROUTE GRAPH IS THE ONLY ROUTE SOURCE. Skill 49 compiles it
#: (49-signature-funnel/scripts/compile_launch_route.py) from the approved
#: launch record; this module READS it and never plans a route of its own.
#: Roles are the graph's own vocabulary and the events are the two commerce
#: outcomes the graph carries.
ROUTE_ROLES = ("landing", "product_selection", "checkout", "upsell_1",
               "downsell_1", "upsell_2", "thank_you")
ROUTE_EVENT_PAID = "payment_succeeded"
ROUTE_EVENT_DECLINE = "explicit_decline"
ROUTE_EVENTS = (ROUTE_EVENT_PAID, ROUTE_EVENT_DECLINE)
PAID_GUARD_PREFIX = "verified_"
DECLINE_GUARD = "no_charge_decline"
PENDING_BEHAVIOR = ("retain_current_purchase_state_until_resolved_or_"
                    "explicit_decline")

#: Distinct slot identities. Two upsells must never share one generic key:
#: the slot names the offer in the approved launch record, in the page plan,
#: in the element bindings and in the workflow delivery, so U1 and U2 cannot
#: overwrite each other. ``upsell``/``downsell`` remain accepted as single
#: aliases and are recorded under their slot, never as a bare "upsell".
SLOT_MAIN = "main"
SLOT_COLLECT_PAYMENT = "collect_payment"
SLOT_BUMP = "bump"
SLOT_UPSELL_1 = "upsell_1"
SLOT_UPSELL_2 = "upsell_2"
SLOT_DOWNSELL_1 = "downsell_1"
EXTRA_SLOT_ROLE = {SLOT_UPSELL_1: "upsell_1", SLOT_DOWNSELL_1: "downsell_1",
                   SLOT_UPSELL_2: "upsell_2"}
EXTRA_SLOTS = (SLOT_UPSELL_1, SLOT_DOWNSELL_1, SLOT_UPSELL_2)

#: Native checkout family - identified BEFORE the upsell sequence is
#: installed. The two families are different surfaces: Order Upsell in Forms
#: is a V2 funnel on the same domain; Store Upsell is a Website page using
#: the native Upsell element. Installing the sequence on the wrong family
#: produces steps that cannot carry a one-click action.
CHECKOUT_FAMILY_ORDER_UPSELL_V2_FUNNEL = "order_upsell_v2_funnel"
CHECKOUT_FAMILY_STORE_UPSELL_WEBSITE = "store_upsell_website"
CHECKOUT_FAMILIES = {
    CHECKOUT_FAMILY_ORDER_UPSELL_V2_FUNNEL: {
        "surface": "form_v2_funnel_same_domain",
        "native_element": "order_upsell_forms_step",
    },
    CHECKOUT_FAMILY_STORE_UPSELL_WEBSITE: {
        "surface": "website_page",
        "native_element": "native_upsell_element",
    },
}

#: A purchase action is a native one-click action charging the bound
#: product/price inside the native payment session. A link or button that
#: merely navigates to a thank-you page is NOT a purchase action and is
#: refused as one.
NATIVE_PURCHASE_KIND = "one_click_purchase"
NATIVE_PAYMENT_SESSION = "native"
PURCHASE_CONTROL_KEYS = ("href", "navigate_to", "url", "redirect_to")

#: The order bump's default state. The packet section 9 acceptance shape
#: verifies the bump present with its default state UNCHECKED; a plan may
#: not ask for anything else.
BUMP_DEFAULT_CHECKED = False


class OrderPlanError(ValueError):
    """Raised when an order spec cannot become an honest plan: a missing or
    provenance-less product binding, a pre-checked bump, an upsell that is
    not one-click, a duplicate element, or an empty location. The plan
    builder fails closed; it never defaults a binding into existence."""


def is_payments_tile(field_name: Any) -> bool:
    """True when ``field_name`` names one of the Payments Quick-Add tiles.
    Mirrors ``ghl_form_builder.QUICK_ADD_TAXONOMY['Payments']`` exactly -
    the form builder's carve-out uses its own taxonomy; this predicate is
    for plan-side callers."""
    return str(field_name or "").strip() in PAYMENTS_TILES


def _billing_terms(raw: Any, *, element: str) -> Optional[dict]:
    """Validate and carry approved billing terms, verbatim.

    Returns ``None`` when the caller supplied no billing key at all (an absent
    term stays absent - it is never defaulted to ``one_time``). A term the
    native price surface cannot express (installment) is refused with the real
    reason; it is NEVER flattened into a single charge.
    """
    if not isinstance(raw, dict):
        return None
    if not any(k in raw for k in BILLING_TERM_FIELDS):
        return None
    billing_type = str(raw.get("billing_type") or "").strip()
    if not billing_type:
        raise OrderPlanError(
            f"{element}: billing terms are present but carry no billing_type - "
            "an unlabelled term would be flattened into an assumed charge")
    if billing_type in UNSUPPORTED_BILLING_TERMS:
        raise OrderPlanError(f"{element}: {BILLING_NOT_NATIVE}")
    # An APPROVED record says ``trial``; the native shape is trial_then_recurring.
    billing_type = APPROVED_TO_NATIVE.get(billing_type, billing_type)
    if billing_type not in NATIVE_BILLING_TYPES:
        raise OrderPlanError(
            f"{element}: billing_type {billing_type!r} is not one of "
            f"{NATIVE_BILLING_TYPES} - supply the approved native term, never a "
            "shorthand that would have to be guessed")
    interval = raw.get("recurring_interval")
    interval = str(interval).strip() if interval is not None else None
    trial = raw.get("trial_days")
    if trial is not None and (not isinstance(trial, int) or isinstance(trial, bool)):
        raise OrderPlanError(f"{element}: trial_days must be an integer, never {trial!r}")
    out: dict = {"billing_type": billing_type}
    if billing_type == "one_time":
        if interval or trial is not None:
            raise OrderPlanError(
                f"{element}: one_time price must not carry recurrence or trial terms")
    elif billing_type == "recurring":
        if interval not in RECURRING_INTERVALS:
            raise OrderPlanError(
                f"{element}: recurring price requires recurring_interval in "
                f"{RECURRING_INTERVALS}")
        if trial is not None:
            raise OrderPlanError(
                f"{element}: recurring price must not carry trial_days")
        out["recurring_interval"] = interval
    else:  # trial_then_recurring
        if interval not in RECURRING_INTERVALS:
            raise OrderPlanError(
                f"{element}: trial_then_recurring requires recurring_interval in "
                f"{RECURRING_INTERVALS}")
        if not isinstance(trial, int) or isinstance(trial, bool) or trial < 1:
            raise OrderPlanError(
                f"{element}: trial_then_recurring requires trial_days >= 1")
        out["recurring_interval"] = interval
        out["trial_days"] = trial
    for key in ("installment_count", "installment_interval"):
        if raw.get(key) is not None:
            raise OrderPlanError(f"{element}: {BILLING_NOT_NATIVE}")
    return out


def _binding(raw: Any, *, element: str) -> dict:
    """Validate one product binding. Accepts the canonical key
    ``product_ref`` (and the S44 design-notes key ``native_product_ref``,
    carried verbatim). Returns ``{product_ref, binding_source[, price_ref][, billing]}``."""
    if not isinstance(raw, dict):
        raise OrderPlanError(
            f"{element}: product binding must be a mapping with "
            "product_ref + source; got "
            f"{type(raw).__name__} - an order element without a product "
            "binding is refused (fail closed)")
    ref = raw.get("product_ref") or raw.get("native_product_ref")
    ref = str(ref or "").strip()
    if not ref:
        raise OrderPlanError(
            f"{element}: product binding carries no product_ref - refusing "
            "to plan an unbound order element, and refusing to fabricate a "
            "product reference")
    source = str(raw.get("source") or raw.get("binding_source") or "").strip()
    if source not in BINDING_SOURCES:
        raise OrderPlanError(
            f"{element}: binding source {source!r} is not one of "
            f"{BINDING_SOURCES} - a product reference must name its "
            "provenance (delivered by S44 Phase A, or explicitly supplied "
            "by the caller)")
    out = {"product_ref": ref, "binding_source": source}
    offer_id = str(raw.get("offer_id") or "").strip()
    if raw.get("offer_id") is not None and not offer_id:
        raise OrderPlanError(
            f"{element}: offer_id is present but blank - supply the approved "
            "offer's own id or omit it (never a placeholder)")
    if offer_id:
        # The approved offer identity travels with the binding, so the element
        # names the offer it sells instead of an unattributed product reference.
        out["offer_id"] = offer_id
    price = str(raw.get("price_ref") or "").strip()
    if raw.get("price_ref") is not None and not price:
        raise OrderPlanError(
            f"{element}: price_ref is present but blank - supply the "
            "read-back price id or omit it (never a placeholder)")
    if price:
        out["price_ref"] = price
    billing = _billing_terms(raw.get("billing") if isinstance(raw.get("billing"), dict)
                             else raw, element=element)
    if billing is not None:
        out["billing"] = billing
    return out


def _tile_element(kind: str, tile: str, binding: dict,
                  slot: Optional[str] = None,
                  page_id: Optional[str] = None) -> dict:
    """An order element placed on the funnel order-form step. ``tile`` is the
    legacy native-element name only; it is NOT placed through the form
    builder (see CHECKOUT SURFACE)."""
    verify = {"selected_product_matches_binding": True}
    if "price_ref" in binding:
        verify["selected_price_matches_binding"] = True
    element = {
        "kind": kind,
        "tile": tile,
        "quick_add_category": QUICK_ADD_CATEGORY,
        "surface": SURFACE_FUNNEL_ORDER_STEP,
        "placement": {
            "target": SURFACE_FUNNEL_ORDER_STEP,
            "via": "funnel order-form step element (driver click-through); "
                   "not a form-builder Payments tile",
            "requires_order_binding": True,
        },
        "binding": binding,
        "verify": verify,
    }
    if slot:
        element["slot"] = slot
    if page_id:
        element["page_id"] = page_id
    return element


def _price_verify(binding: dict, verify: dict) -> dict:
    if "price_ref" in binding:
        verify["selected_price_matches_binding"] = True
    return verify


def _route_graph_bytes(graph: dict) -> bytes:
    """The approved route graph's bytes, EXACTLY as Skill 49's
    ``compile_launch_route.serialize_graph`` emits them: ``json.dumps(...,
    indent=2, ensure_ascii=False)`` plus one trailing newline, keys in the
    graph's own order. This is a copy of the authority's serializer, not a
    lookalike: the launch record's ``route_graph_hash`` IS these bytes."""
    return (json.dumps(graph, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8")


def graph_hash(graph: dict) -> str:
    """sha256 of the approved route graph in the SAME form Skill 49 records as
    the launch record's ``route_graph_hash``
    (``compile_launch_route.serialize_graph`` / ``graph_hash``). Byte equality
    with that serializer is the contract - button binding and page generation
    must read one identity for one graph, so this hash is NOT ``_canon``
    (that is the plan canonicaliser, a different function for a different
    job)."""
    return hashlib.sha256(_route_graph_bytes(graph)).hexdigest()


def approved_routes(graph: Any) -> Dict[str, dict]:
    """READ the approved route graph once. Returns ``{role: route}`` where a
    route is ``{page_id, accept, decline}`` and each link carries the graph's
    own ``event``, target role, target page id and guard, verbatim.

    This is a reader, not a planner: it never derives a route the graph does
    not carry, and it refuses a graph whose commerce edges are missing,
    duplicated, dangling, or unguarded. Pending/failed payment has no edge by
    design and is carried separately by the plan (``payment_recovery``).
    """
    if not isinstance(graph, dict):
        raise OrderPlanError(
            "route_graph must be the approved route graph object compiled by "
            "Skill 49; a plan that needs routes cannot be built without it")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not nodes:
        raise OrderPlanError("route_graph carries no 'nodes' array")
    if not isinstance(edges, list):
        raise OrderPlanError("route_graph carries no 'edges' array")
    role_of: Dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise OrderPlanError(f"route_graph node is not an object: {node!r}")
        pid = str(node.get("page_id") or "").strip()
        role = str(node.get("role") or "").strip()
        if not pid or role not in ROUTE_ROLES:
            raise OrderPlanError(
                f"route_graph node {node!r} needs a page_id and one of "
                f"{ROUTE_ROLES}")
        if pid in role_of:
            raise OrderPlanError(f"route_graph repeats page_id {pid!r}")
        if role in role_of.values():
            raise OrderPlanError(
                f"route_graph repeats role {role!r} - one page per role")
        role_of[pid] = role
    by_role = {role: {"page_id": pid, "accept": None, "decline": None}
               for pid, role in role_of.items()}
    seen = set()
    for edge in edges:
        if not isinstance(edge, dict):
            raise OrderPlanError(f"route_graph edge is not an object: {edge!r}")
        frm, to = edge.get("from"), edge.get("to")
        event, guard = edge.get("event"), edge.get("guard")
        if frm not in role_of or to not in role_of:
            raise OrderPlanError(f"route_graph edge {edge!r} is dangling")
        if event not in ROUTE_EVENTS:
            continue  # non-commerce entry edges are not this plan's business
        role = role_of[frm]
        if (role, event) in seen:
            raise OrderPlanError(
                f"route_graph carries a second {event} edge from {role!r} - "
                "routing must be deterministic")
        seen.add((role, event))
        if not isinstance(guard, str) or not guard.strip():
            raise OrderPlanError(f"route_graph edge {edge!r} names no guard")
        if event == ROUTE_EVENT_PAID and not guard.startswith(PAID_GUARD_PREFIX):
            raise OrderPlanError(
                f"paid edge from {role!r} carries guard {guard!r}; a paid "
                f"route must name a verified_* guard")
        if event == ROUTE_EVENT_DECLINE and guard != DECLINE_GUARD:
            raise OrderPlanError(
                f"decline edge from {role!r} carries guard {guard!r}; a "
                f"decline edge must name {DECLINE_GUARD!r} (no charge)")
        link = {"event": event, "target_role": role_of[to], "target_page_id": to,
                "guard": guard}
        if event == ROUTE_EVENT_PAID:
            by_role[role]["accept"] = link
        else:
            by_role[role]["decline"] = link
    return by_role


def _links(elements: List[dict], routes: Dict[str, dict]) -> None:
    """Attach each purchase element's routes FROM THE APPROVED GRAPH.

    A purchase step carries a paid edge and an explicit-decline edge; a
    failed or pending payment carries neither (it stays in payment recovery
    on the same page). Decline is kept apart from pending/failed on the face
    of the element: ``on_explicit_decline`` is the only route a decline takes.
    """
    for e in elements:
        role = EXTRA_SLOT_ROLE.get(e.get("slot"))
        if not role:
            continue
        route = routes.get(role)
        if not route:
            raise OrderPlanError(
                f"{role}: the approved route graph has no node for this offer "
                "slot - an offer must appear in the graph before it is planned")
        if not (route["accept"] and route["decline"]):
            raise OrderPlanError(
                f"{role}: the approved route graph needs both a "
                f"{ROUTE_EVENT_PAID} edge and a {ROUTE_EVENT_DECLINE} edge")
        e["links"] = {
            "accept": route["accept"]["target_page_id"],
            "decline": route["decline"]["target_page_id"],
            "on_payment_succeeded": dict(route["accept"]),
            "on_explicit_decline": dict(route["decline"]),
            "on_payment_failed": {
                "is_decline": False, "is_acceptance": False,
                "behaviour": PENDING_BEHAVIOR,
                "stays_on_page_id": e.get("page_id")},
            "on_payment_pending": {
                "is_decline": False, "is_acceptance": False,
                "behaviour": PENDING_BEHAVIOR,
                "stays_on_page_id": e.get("page_id")},
        }


_STEP_ACTIONS = {
    KIND_ORDER_FORM: "set_order_form_product",
    KIND_COLLECT_PAYMENT: "set_collect_payment_product",
    KIND_ORDER_BUMP: "add_order_bump",
    KIND_UPSELL: "add_one_click_upsell_step",
    KIND_DOWNSELL: "add_downsell_step",
    KIND_THANK_YOU: "add_thank_you_step",
    KIND_LEAD_CAPTURE: "add_lead_capture_form",
}


def placement_steps(elements: List[dict]) -> List[dict]:
    """The ordered driver steps: open the funnel order-form step, place each
    element (the bump AFTER the order form), then capture the render. Each
    step names the element's SLOT and PAGE ID, so the two upsells are two
    distinct placements and neither can overwrite the other."""
    steps: List[dict] = [{"n": 1, "action": "open_funnel_order_form_step",
                          "target": SURFACE_FUNNEL_ORDER_STEP}]
    for e in elements:
        step = {"n": len(steps) + 1, "action": _STEP_ACTIONS[e["kind"]],
                "element": e["kind"]}
        if e.get("slot"):
            step["slot"] = e["slot"]
        if e.get("page_id"):
            step["page_id"] = e["page_id"]
        if e.get("binding"):
            step["binding"] = dict(e["binding"])
        if e["kind"] == KIND_ORDER_BUMP:
            step["after"] = KIND_ORDER_FORM
        steps.append(step)
    steps.append({"n": len(steps) + 1, "action": "capture_order_render",
                  "via": CAPTURE_TOOL})
    return steps


def _patch_binding(binding: dict) -> dict:
    """The binding as handed to the form builder / driver. Approved billing
    terms travel with it: dropping them would let the native side bind a
    recurring offer as a single charge."""
    out = {"product_ref": binding["product_ref"],
           "source": binding["binding_source"]}
    if binding.get("offer_id"):
        out["offer_id"] = binding["offer_id"]
    if binding.get("price_ref"):
        out["price_ref"] = binding["price_ref"]
    if binding.get("billing"):
        out["billing"] = dict(binding["billing"])
    return out


def _extra_specs(spec: dict) -> List[dict]:
    """The extra offers in the spec, each with a DISTINCT slot.

    Accepted shapes, both recorded under a slot identity:

      * ``"upsells":   [{"slot": "upsell_1", "product": {...}},
                        {"slot": "upsell_2", "product": {...}}]``
      * ``"downsells": [{"slot": "downsell_1", "product": {...}}]``
      * the single aliases ``"upsell"`` -> ``upsell_1`` and ``"downsell"`` ->
        ``downsell_1`` (kept because existing callers use them).

    A list entry must name its slot; a bare generic "upsell" key is refused
    on a list entry because two upsells sharing one key is exactly the
    collision this plan cannot allow.
    """
    out: List[dict] = []
    for key, default_slot, known in (
            ("upsells", SLOT_UPSELL_1, (SLOT_UPSELL_1, SLOT_UPSELL_2)),
            ("downsells", SLOT_DOWNSELL_1, (SLOT_DOWNSELL_1,))):
        raw = spec.get(key)
        if raw is not None:
            if not isinstance(raw, list) or not raw:
                raise OrderPlanError(f"{key}: expected a non-empty list of offers")
            for entry in raw:
                if not isinstance(entry, dict):
                    raise OrderPlanError(f"{key}: offer entry is not an object")
                slot = str(entry.get("slot") or "").strip()
                if slot not in known:
                    raise OrderPlanError(
                        f"{key}: offer entry carries slot {slot!r}; each offer "
                        f"must name its own slot, one of {list(known)} - two "
                        "offers never share one generic key")
                out.append(dict(entry, slot=slot))
    for key, slot, kind in (("upsell", SLOT_UPSELL_1, KIND_UPSELL),
                            ("downsell", SLOT_DOWNSELL_1, KIND_DOWNSELL)):
        raw = spec.get(key)
        if raw is not None:
            if not isinstance(raw, dict):
                raise OrderPlanError(f"{key}: offer is not an object")
            if any(e["slot"] == slot for e in out):
                raise OrderPlanError(
                    f"{slot}: offered twice (as {key!r} and in the list form)")
            if "slot" in raw and raw["slot"] != slot:
                raise OrderPlanError(
                    f"{key}: slot {raw['slot']!r} contradicts the single "
                    f"alias, which is {slot!r}")
            out.append(dict(raw, slot=slot))
    return out


def _native_action(binding: dict, family: str, *, role: str) -> dict:
    """The native one-click purchase action for an extra offer.

    It charges the BOUND product/price inside the native payment session.
    ``action_id`` stays null until Skill 6 records the installed binding; no
    id is invented. Navigation is never a purchase action, so the action
    carries no href/url of any kind.
    """
    action = {
        "kind": NATIVE_PURCHASE_KIND,
        "family": family,
        "family_native_element": CHECKOUT_FAMILIES[family]["native_element"],
        "product_ref": binding["product_ref"],
        "payment_session": NATIVE_PAYMENT_SESSION,
        "action_id": None,
        "binding_status": "pending_s06_install",
        "navigates": False,
    }
    if binding.get("price_ref"):
        action["price_ref"] = binding["price_ref"]
    return action


def _extra_element(spec: dict, *, slot: str, family: Optional[str],
                   route: Dict[str, dict], install_ready: bool) -> dict:
    """One extra offer as a plan element with its own slot identity, its own
    page id from the approved graph, and (on the install path) a native
    purchase action.

    A plan built WITHOUT the approved graph/family is a legacy think-layer
    plan: it keeps its slot identity but is explicitly not install-ready, so
    the missing route source can never be mistaken for an approved route.
    """
    role = EXTRA_SLOT_ROLE[slot]
    kind = KIND_UPSELL if slot in (SLOT_UPSELL_1, SLOT_UPSELL_2) \
        else KIND_DOWNSELL
    for control in PURCHASE_CONTROL_KEYS:
        if control in spec:
            raise OrderPlanError(
                f"{slot}: purchase control {control!r} is a navigation, not a "
                "purchase action; a purchase is the native one-click action "
                "bound to the product/price, never a link that navigates to "
                "another page")
    if not isinstance(spec.get("product"), dict):
        raise OrderPlanError(
            f"{slot}: a one-click extra offer needs its own product binding "
            "(fail closed)")
    if spec.get("one_click") is False:
        raise OrderPlanError(
            f"{slot}: one_click=false contradicts the element - the native "
            "post-purchase offer is a one-click offer; a multi-step offer is "
            "a separate funnel step, not this element")
    binding = _binding(spec.get("product"), element=role)
    page = route.get(role) if route else None
    if install_ready:
        if not binding.get("price_ref"):
            raise OrderPlanError(
                f"{slot}: the purchase action needs the approved price_ref it "
                "charges - a one-click action without a price cannot disclose "
                "or charge the correct amount")
        if not page:
            raise OrderPlanError(
                f"{slot}: the approved route graph has no {role!r} node; an "
                "offer that is not in the approved graph is never planned")
    element = {
        "kind": kind,
        "slot": slot,
        "tile": None,
        "placement": {"target": (page["page_id"] if page
                                 else SURFACE_FUNNEL_ORDER_STEP),
                      "step": _STEP_ACTIONS[kind],
                      "requires_order_binding": True},
        "surface": ("native post-purchase one-click upsell step"
                    if kind == KIND_UPSELL
                    else "native post-purchase downsell step (shown only "
                         "after an explicit upsell 1 decline)"),
        "one_click": True,
        "binding": binding,
        "verify": {"selected_product_matches_binding": True},
    }
    if page:
        element["page_id"] = page["page_id"]
        element["placement"]["surface_family"] = \
            CHECKOUT_FAMILIES[family]["surface"]
    if install_ready:
        element["native_action"] = _native_action(binding, family, role=role)
        element["verify"] = _price_verify(binding, {
            "selected_product_matches_binding": True,
            "selected_price_matches_binding": True,
            "native_action_bound": True,
            "purchase_is_not_navigation": True})
    return element


def build_order_plan(spec: dict) -> dict:
    """Build (and fully validate) an order-element plan from ``spec``.

    Spec shape::

        {
          "location_id": "<subaccount id>",            # required
          "form_name": "<native form name>",           # optional label
          "checkout_family": "order_upsell_v2_funnel"  # REQUIRED when any
                     # upsell/downsell is planned; one of
                     # order_upsell_v2_funnel | store_upsell_website
          "route_graph": {"nodes": [...], "edges": [...]},  # REQUIRED when any
                     # upsell/downsell is planned - the APPROVED graph compiled
                     # by Skill 49; this module never plans routes
          "order_form":      {"product": {binding}},   # REQUIRED
          "collect_payment": {"product": {binding}},   # optional; defaults
                                                       # to the order-form
                                                       # binding when true
          "bump":    {"product": {binding}},           # optional; may carry
                     # "default_checked": false - true is REFUSED
          "upsells":   [{"slot": "upsell_1", "product": {binding}},
                        {"slot": "upsell_2", "product": {binding}}],  # optional
          "downsells": [{"slot": "downsell_1", "product": {binding}}],  # optional
          "upsell":  {"product": {binding}},   # single alias -> upsell_1
          "downsell": {"product": {binding}},  # single alias -> downsell_1
          "thank_you": true,                   # optional step
          "lead_capture": {"fields": ["email"]},  # optional native form
        }

    A binding is ``{"product_ref", "source", "offer_id"?, "price_ref"?, "billing"?}``.
    An extra offer's binding MUST carry ``price_ref`` because its native
    one-click action charges that price. ``billing`` carries the approved F08
    terms verbatim (``billing_type`` / ``recurring_interval`` /
    ``trial_days``); it is never flattened into ``one_time`` and an
    installment term is refused. An approved record's ``trial`` is carried as
    the native ``trial_then_recurring``.

    Every element carries its product binding or the plan is refused. Every
    element carries its own SLOT identity and, where the approved graph names
    one, its own PAGE ID. Returns the plan dict (schema
    ``skill6-order-plan/1``)."""
    if not isinstance(spec, dict):
        raise OrderPlanError(f"order spec must be a mapping, got "
                             f"{type(spec).__name__}")
    location_id = str(spec.get("location_id") or "").strip()
    if not location_id:
        raise OrderPlanError("order spec carries no location_id - an order "
                             "plan is always scoped to one subaccount")

    extras = _extra_specs(spec)

    # The native checkout family is identified BEFORE the upsell sequence is
    # installed: the wrong family installs one-click steps on a surface that
    # cannot host them. Family + graph always travel together; a plan that
    # carries neither keeps its legacy slot shape but is NOT install-ready.
    family = str(spec.get("checkout_family") or "").strip()
    if family and family not in CHECKOUT_FAMILIES:
        raise OrderPlanError(
            f"checkout_family {family!r} is not one of "
            f"{sorted(CHECKOUT_FAMILIES)} (Order Upsell in Forms is a V2 "
            "funnel on the same domain; Store Upsell is a Website page using "
            "the native Upsell element)")
    graph = spec.get("route_graph")
    if extras and bool(family) != (graph is not None):
        raise OrderPlanError(
            "checkout_family and route_graph must be supplied together: the "
            "native family and the ONE approved route graph are both needed "
            "before an upsell/downsell sequence can be installed")
    install_ready = bool(extras) and bool(family) and graph is not None

    routes: Dict[str, dict] = {}
    if graph is not None:
        routes = approved_routes(graph)
    if install_ready:
        missing = [e["slot"] for e in extras
                   if EXTRA_SLOT_ROLE[e["slot"]] not in routes]
        if missing:
            raise OrderPlanError(
                "the approved route graph has no node for: "
                + ", ".join(missing))
        extra_roles = {EXTRA_SLOT_ROLE[e["slot"]] for e in extras}
        if SLOT_DOWNSELL_1 in {e["slot"] for e in extras} \
                and SLOT_UPSELL_1 not in {e["slot"] for e in extras}:
            raise OrderPlanError(
                "downsell_1 is enabled without upsell_1 - route law requires "
                "U1 enabled for D1 to be reached; the graph cannot carry a "
                "downsell nobody can decline into")
        if SLOT_UPSELL_2 in {e["slot"] for e in extras} \
                and not extra_roles & {"upsell_1", "downsell_1"}:
            raise OrderPlanError(
                "upsell_2 is enabled with no upsell_1 or downsell_1 entry "
                "path - U2 is reached only after an accepted U1 or D1")
        if not routes.get("checkout"):
            raise OrderPlanError(
                "the approved route graph carries no checkout node")

    checkout_page_id = routes["checkout"]["page_id"] \
        if install_ready else None

    order_form_spec = spec.get("order_form")
    if not isinstance(order_form_spec, dict) or "product" not in order_form_spec:
        raise OrderPlanError(
            "order spec has no order_form product binding - the order form "
            "is the core native order element and it cannot be planned "
            "unbound (fail closed)")
    main_binding = _binding(order_form_spec.get("product"),
                            element=KIND_ORDER_FORM)

    elements: List[dict] = [
        _tile_element(KIND_ORDER_FORM, TILE_ORDER_FORM, main_binding,
                      slot=SLOT_MAIN, page_id=checkout_page_id)]

    cp_spec = spec.get("collect_payment")
    if cp_spec is not None:
        if cp_spec is True:
            cp_binding = dict(main_binding)
        elif isinstance(cp_spec, dict):
            cp_binding = _binding(cp_spec.get("product", main_binding)
                                  if "product" in cp_spec else main_binding,
                                  element=KIND_COLLECT_PAYMENT)
        else:
            raise OrderPlanError(
                f"collect_payment spec must be a mapping or true, got "
                f"{type(cp_spec).__name__}")
        elements.append(_tile_element(KIND_COLLECT_PAYMENT,
                                      TILE_COLLECT_PAYMENT, cp_binding,
                                      slot=SLOT_COLLECT_PAYMENT,
                                      page_id=checkout_page_id))

    lc_spec = spec.get("lead_capture")
    if lc_spec is not None:
        if lc_spec is True:
            lc_spec = {}
        if not isinstance(lc_spec, dict):
            raise OrderPlanError(
                f"lead_capture spec must be a mapping or true, got "
                f"{type(lc_spec).__name__}")
        raw_fields = lc_spec.get("fields")
        if not isinstance(raw_fields, list) or not raw_fields:
            raise OrderPlanError(
                "lead_capture: an explicit non-empty fields list is required - "
                "this module never invents contact fields")
        fields: List[str] = []
        for raw_field in raw_fields:
            name = str(raw_field or "").strip()
            if not name:
                raise OrderPlanError(
                    "lead_capture: every field name must be a non-empty string")
            if name in fields:
                raise OrderPlanError(f"lead_capture: duplicate field {name!r}")
            fields.append(name)
        # The lead-capture form sells nothing, so it carries no product
        # binding; it is placed through the NATIVE builder route because the
        # API/MCP catalog has no form-designer operation.
        elements.append({
            "kind": KIND_LEAD_CAPTURE,
            "tile": None,
            "surface": "native lead-capture form on the funnel order-form step",
            "placement": {
                "target": SURFACE_FUNNEL_ORDER_STEP,
                "step": _STEP_ACTIONS[KIND_LEAD_CAPTURE],
                "via": "native builder route (page-builder Insert Element); the "
                       "API/MCP catalog has no form-designer operation",
                "requires_order_binding": False,
            },
            "fields": fields,
            "binding": None,
            "verify": {"lead_capture_present": True, "fields_match": True,
                       "evidence": "rendered page (never stored bytes)"},
        })

    bump_spec = spec.get("bump")
    if bump_spec is not None:
        if not isinstance(bump_spec, dict) or "product" not in bump_spec:
            raise OrderPlanError("bump: a bump offer needs its own product "
                                 "binding (fail closed)")
        if bump_spec.get("default_checked"):
            raise OrderPlanError(
                "bump: default_checked=true is REFUSED - the order bump's "
                "default state is UNCHECKED (packet section 9 acceptance "
                "shape); pre-checked offer boxes are never planned")
        bump_binding = _binding(bump_spec.get("product"),
                                element=KIND_ORDER_BUMP)
        elements.append({
            "kind": KIND_ORDER_BUMP,
            "slot": SLOT_BUMP,
            "tile": None,
            "page_id": checkout_page_id,
            "surface": "native order-form bump offer",
            "placement": {
                "target": SURFACE_FUNNEL_ORDER_STEP,
                "step": "add_order_bump",
                "after": KIND_ORDER_FORM,
                "requires_order_binding": True,
            },
            "binding": bump_binding,
            "default_checked": BUMP_DEFAULT_CHECKED,
            "verify": _price_verify(bump_binding, {
                "default_state": "unchecked",
                "selected_product_matches_binding": True,
                "evidence": "rendered page (never stored bytes)"}),
        })

    if extras:
        if install_ready:
            # Extra offers are placed in the APPROVED GRAPH's own node order
            # (upsell_1, downsell_1, upsell_2), so the driver follows the one
            # route plan rather than an order this module invents.
            graph_order = [n.get("page_id") for n in graph.get("nodes") or []]

            def _graph_index(entry: dict) -> int:
                page = routes[EXTRA_SLOT_ROLE[entry["slot"]]]["page_id"]
                return graph_order.index(page) if page in graph_order \
                    else len(graph_order)

            extras.sort(key=_graph_index)
        for extra in extras:
            slot = extra["slot"]
            elements.append(_extra_element(
                extra, slot=slot, family=family or None,
                route={EXTRA_SLOT_ROLE[slot]: routes[EXTRA_SLOT_ROLE[slot]]}
                if install_ready else {}, install_ready=install_ready))

    ty_spec = spec.get("thank_you")
    if ty_spec:
        # DTY-11: the post-purchase thank-you step has a placement too; it
        # sells nothing, so it carries no product binding.
        ty_node = routes.get("thank_you") or {}
        elements.append({
            "kind": KIND_THANK_YOU,
            "slot": "thank_you",
            "tile": None,
            "page_id": ty_node.get("page_id"),
            "surface": "native post-purchase thank-you step",
            "placement": {"target": ty_node.get("page_id")
                          or SURFACE_FUNNEL_ORDER_STEP,
                          "step": "add_thank_you_step",
                          "requires_order_binding": False},
            "binding": None,
            "verify": {"step_present": True},
        })

    slots = [e.get("slot") for e in elements]
    if len(slots) != len(set(slots)):
        raise OrderPlanError(f"duplicate element slots in plan: {slots}")

    if install_ready:
        _links(elements, routes)
    # Bindings are keyed by SLOT so two upsells can never overwrite each
    # other. The two Payments tiles are ALSO addressable by their tile name
    # because that is how the form builder addresses them; tile names and
    # slot names are disjoint, and only those two elements have a tile.
    element_bindings = {
        e["tile"]: _patch_binding(e["binding"])
        for e in elements if e.get("tile") and e.get("binding")}
    element_bindings.update({
        e["slot"]: _patch_binding(e["binding"])
        for e in elements
        if e.get("slot") and e.get("binding") and e.get("kind") in (
            KIND_ORDER_FORM, KIND_COLLECT_PAYMENT, KIND_ORDER_BUMP,
            KIND_UPSELL, KIND_DOWNSELL)})
    blockers = []
    if extras and not install_ready:
        blockers.append(
            "install_blocked: the approved route graph and the native "
            "checkout family were not supplied, so no route or native "
            "purchase action is carried; this plan is not install-ready")
    return {
        "schema": PLAN_SCHEMA,
        "location_id": location_id,
        "form_name": str(spec.get("form_name") or ""),
        "surface": SURFACE_FUNNEL_ORDER_STEP,
        "install_ready": install_ready,
        "blockers": blockers,
        "checkout_family": (dict(CHECKOUT_FAMILIES[family], id=family)
                            if family and family in CHECKOUT_FAMILIES
                            else None),
        "route_graph": ({
            "ref": str(spec.get("route_graph_ref") or ""),
            "hash": graph_hash(graph),
            "roles": [n["role"] for n in graph["nodes"]],
            "page_ids": {n["role"]: n["page_id"] for n in graph["nodes"]},
        } if graph is not None else None),
        "elements": elements,
        "steps": placement_steps(elements),
        "form_task_patch": {
            "order_binding": _patch_binding(main_binding),
            "order_element_bindings": element_bindings,
        },
        "payment_recovery": {
            "behaviour": PENDING_BEHAVIOR,
            "is_acceptance": False,
            "is_decline": False,
            "grants_entitlement": False,
            "applies_to": ["payment_failed", "payment_pending",
                           "requires_customer_action"],
        },
        "provenance": {
            "bindings": "every product reference is carried verbatim from "
                        "its named source; no product ID, price, variant, "
                        "or catalog data was fabricated by this plan",
            "routes": "every route is READ from the approved Skill 49 route "
                      "graph; this plan never derives a route of its own",
            "s44_phase_a": ("Phase A output was not delivered to this "
                            "build (prep Q2 open); bindings sourced "
                            "'s44_phase_a' are accepted in shape only and "
                            "stay unverified until Phase A lands"),
        },
        "live_proof": ("LIVE_PROOF_PENDING: placement on a live location, "
                       "selected-product read-back, and rendered bump state "
                       "are proven only on an explicitly approved test "
                       "location (prep Q4); this plan is fixture-verified "
                       "only"),
    }


def form_task_patch(plan: dict, *, per_element: bool = False) -> dict:
    """The dict a caller merges into a ``ghl_form_builder`` task so the form
    builder treats Payments tiles as bound order elements: preflight F-P10
    requires it, ``_resolve_fields`` stamps it onto the tile fields, and the
    F5 walk refuses to drag a Payments tile without it.

    ``per_element=True`` also carries ``order_element_bindings`` (one binding
    per SLOT, so U1 and U2 keep their own product/price and neither
    overwrites the other)."""
    patch = (plan or {}).get("form_task_patch") or {}
    binding = patch.get("order_binding") or {}
    if not binding.get("product_ref"):
        raise OrderPlanError("plan carries no form_task_patch order_binding "
                             "- cannot hand an unbound plan to the form "
                             "builder")
    out = {"order_binding": dict(binding)}
    if per_element:
        out["order_element_bindings"] = {
            k: dict(v) for k, v in
            (patch.get("order_element_bindings") or {}).items()}
    return out


# ── Evidence capture (provenance) ────────────────────────────────────────────

def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def plan_hash(plan: dict) -> str:
    """sha256 of the canonical plan: evidence is bound to ONE plan."""
    return hashlib.sha256(_canon(plan)).hexdigest()


def _provenance_hash(envelope: dict) -> str:
    body = {k: v for k, v in envelope.items() if k != "provenance_hash"}
    return hashlib.sha256(_canon(body)).hexdigest()


def capture_order_render(plan: dict, reader: Any, *, source: str = "live",
                         captured_at: Optional[str] = None) -> dict:
    """The ONLY producer of render evidence. ``reader(plan)`` is the browser
    layer's read-back of the rendered funnel order-form step (a dict of
    observations, shape in :func:`verify_order_render`). Returns the evidence
    envelope with the plan hash and a ``provenance_hash``. ``source`` is
    ``"live"`` (a real capture) or ``"fixture"`` (selftest / offline); the
    verdict reports which, so a fixture never reads as the live proof."""
    if source not in EVIDENCE_SOURCES:
        raise OrderPlanError(f"evidence source {source!r} is not one of "
                             f"{EVIDENCE_SOURCES}")
    if not callable(reader):
        raise OrderPlanError("capture_order_render needs a reader callable "
                             "(the browser layer's read-back)")
    observations = reader(plan)
    if not isinstance(observations, dict) or not observations:
        raise OrderPlanError("reader returned no observations - nothing to "
                             "capture")
    envelope = {
        "schema": EVIDENCE_SCHEMA,
        "capture_tool": CAPTURE_TOOL,
        "source": source,
        "captured_at": captured_at or time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "plan_hash": plan_hash(plan),
        "observations": observations,
    }
    envelope["provenance_hash"] = _provenance_hash(envelope)
    return envelope


def _envelope_problems(plan: dict, ev: Any) -> List[str]:
    """Why ``ev`` is not capture-function evidence for ``plan`` (empty list =
    it is). Never raises."""
    if not isinstance(ev, dict) or ev.get("schema") != EVIDENCE_SCHEMA:
        return ["not a capture envelope (hand-written / bare evidence is "
                "refused; produce it with capture_order_render)"]
    problems: List[str] = []
    if ev.get("capture_tool") != CAPTURE_TOOL:
        problems.append("capture_tool is not the capture function")
    if ev.get("source") not in EVIDENCE_SOURCES:
        problems.append(f"source {ev.get('source')!r} not in {EVIDENCE_SOURCES}")
    if not isinstance(ev.get("observations"), dict):
        problems.append("observations missing")
    if ev.get("plan_hash") != plan_hash(plan):
        problems.append("plan_hash does not match this plan")
    if ev.get("provenance_hash") != _provenance_hash(ev):
        problems.append("provenance_hash does not recompute (edited after "
                        "capture)")
    return problems


def write_evidence(path: str, envelope: dict) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(envelope, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def verify_order_render(plan: dict, rendered: dict, *,
                        require_capture: bool = False) -> dict:
    """Verify RENDERED / read-back evidence against the plan (prep step 5).

    ``rendered`` is either a capture envelope from
    :func:`capture_order_render` (preferred) or, for offline fixtures only, a
    bare observations dict::

        {
          "order_tile_present": bool,
          "payment_tile_present": bool,
          "selected_product_ref": "<the product the placed element is "
                                   "actually bound to, as read back>",
          "selected_price_ref": "<read-back price; required when the "
                                 "binding carries a price_ref>",
          "collect_payment_selected_product_ref": "<the product the "
                                   "Collect Payment tile is bound to, as "
                                   "read back; required when that element "
                                   "carries a binding distinct from the "
                                   "order form's>",
          "bump_present": bool,
          "bump_selected_product_ref": "<the product the bump actually "
                                   "offers, as read back>",
          "bump_checked": bool | None,   # None = state not observed
          "thank_you_step_present": bool,
        }

    Returns ``{ok, checks, reasons, attested, live_capture}`` - a pure verdict
    that never raises, in the style of ``ghl_builder.assert_seo_populated``.
    ``attested`` is True only for a valid capture envelope. With
    ``require_capture=True`` a bare dict is refused outright, and a capture
    envelope also REQUIRES the bump product read-back. A bare dict (legacy
    fixtures, ``require_capture=False``) checks what it carries and an absent
    bump product key is not failed - it is never ``attested``. A collect-
    payment element whose binding is DISTINCT from the order form's is
    verified against its own read-back key; when equal, the shared
    ``selected_product_ref`` check covers it."""
    checks: List[dict] = []
    reasons: List[str] = []
    elements = (plan or {}).get("elements") or []
    by_kind = {e.get("kind"): e for e in elements}

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            reasons.append(f"{name}: {detail}")

    attested = False
    live_capture = False
    if isinstance(rendered, dict) and rendered.get("schema") == EVIDENCE_SCHEMA:
        problems = _envelope_problems(plan, rendered)
        check("evidence_provenance", not problems,
              "; ".join(problems) or "capture envelope verified")
        attested = not problems
        live_capture = attested and rendered.get("source") == "live"
        rendered = rendered.get("observations") or {}
    elif require_capture:
        check("evidence_provenance", False,
              "; ".join(_envelope_problems(plan, rendered)))
        rendered = {}
    rendered = rendered or {}
    strict = attested or require_capture

    def price_check(name: str, binding: dict, key: str) -> None:
        if binding.get("price_ref"):
            observed = rendered.get(key)
            check(name, observed == binding["price_ref"],
                  f"price read back as {observed!r} under {key}; the "
                  f"binding requires exactly {binding['price_ref']!r}")

    if KIND_ORDER_FORM in by_kind:
        check("order_tile_present",
              bool(rendered.get("order_tile_present")),
              "the order form must be present in the rendered funnel "
              "order-form step")
        expected = by_kind[KIND_ORDER_FORM]["binding"]["product_ref"]
        observed = rendered.get("selected_product_ref")
        check("selected_product_matches_binding",
              observed == expected,
              f"selected product read back as {observed!r}; the binding "
              f"requires exactly {expected!r}")
        price_check("selected_price_matches_binding",
                    by_kind[KIND_ORDER_FORM]["binding"], "selected_price_ref")
    if KIND_COLLECT_PAYMENT in by_kind:
        check("payment_tile_present",
              bool(rendered.get("payment_tile_present")),
              "the payment element must be present in the rendered funnel "
              "order-form step")
        cp_expected = by_kind[KIND_COLLECT_PAYMENT]["binding"]["product_ref"]
        form_expected = (by_kind[KIND_ORDER_FORM]["binding"]["product_ref"]
                         if KIND_ORDER_FORM in by_kind else None)
        if cp_expected != form_expected:
            # A DISTINCT collect-payment binding (D1 cure): verified against
            # its own read-back key; an unobserved read-back fails.
            cp_observed = rendered.get("collect_payment_selected_product_ref")
            check("collect_payment_selected_product_matches_binding",
                  cp_observed == cp_expected,
                  f"collect-payment product read back as {cp_observed!r}; "
                  f"the distinct collect-payment binding requires exactly "
                  f"{cp_expected!r}")
    if KIND_ORDER_BUMP in by_kind:
        bump = by_kind[KIND_ORDER_BUMP]
        check("bump_present", bool(rendered.get("bump_present")),
              "the bump offer must be present on the rendered order form")
        observed_state = rendered.get("bump_checked")
        check("bump_default_unchecked",
              observed_state is False,
              "the bump's rendered default state must be observed "
              f"UNCHECKED (observed: {observed_state!r}); a checked or "
              "unobserved bump does not pass")
        # CHK-19: the bump used to attach any product unnoticed.
        b_expected = bump["binding"]["product_ref"]
        b_observed = rendered.get("bump_selected_product_ref")
        check("bump_selected_product_matches_binding",
              b_observed == b_expected if (strict or b_observed is not None)
              else True,
              f"bump product read back as {b_observed!r}; the binding "
              f"requires exactly {b_expected!r}")
        price_check("bump_selected_price_matches_binding", bump["binding"],
                    "bump_selected_price_ref")
    for element in elements:
        kind = element.get("kind")
        if kind not in (KIND_UPSELL, KIND_DOWNSELL):
            continue
        # Each extra offer is verified against its OWN slot's read-back, so
        # the second upsell can never be satisfied by the first one's value.
        # The kind-only key is still accepted for a legacy single-offer plan.
        slot = element.get("slot")
        keys = ([f"{slot}_selected_product_ref"] if slot else []) \
            + [f"{kind}_selected_product_ref"]
        observed = next((rendered[k] for k in keys if rendered.get(k) is not None),
                        None)
        expected = element["binding"]["product_ref"]
        check(f"{slot or kind}_selected_product_matches_binding",
              observed == expected,
              f"{slot or kind} product read back as {observed!r}; the binding "
              f"requires exactly {expected!r}")
        if element["binding"].get("price_ref"):
            price_keys = ([f"{slot}_selected_price_ref"] if slot else []) \
                + [f"{kind}_selected_price_ref"]
            price_observed = next(
                (rendered[k] for k in price_keys if rendered.get(k) is not None),
                None)
            check(f"{slot or kind}_selected_price_matches_binding",
                  price_observed == element["binding"]["price_ref"],
                  f"price read back as {price_observed!r}; the binding "
                  f"requires exactly {element['binding']['price_ref']!r}")
    if KIND_THANK_YOU in by_kind:
        check("thank_you_step_present",
              bool(rendered.get("thank_you_step_present")),
              "the thank-you step must be present in the funnel")
    if KIND_LEAD_CAPTURE in by_kind:
        planned = by_kind[KIND_LEAD_CAPTURE].get("fields") or []
        check("lead_capture_present",
              bool(rendered.get("lead_capture_present")),
              "the native lead-capture form must be present on the rendered "
              "order-form step (placed through the native builder route)")
        observed_fields = rendered.get("lead_capture_fields")
        ok_fields = (isinstance(observed_fields, list)
                     and sorted(str(f) for f in observed_fields) == sorted(planned))
        check("lead_capture_fields_match", ok_fields,
              f"lead-capture fields read back as {observed_fields!r}; the plan "
              f"requires exactly {planned!r}")
    if not elements:
        check("plan_has_elements", False, "the plan carries no elements")
    return {"ok": not reasons, "checks": checks, "reasons": reasons,
            "attested": attested, "live_capture": live_capture}


# ── Self-test - no network, no browser ───────────────────────────────────────

# Self-test fixtures ONLY. Every id is a SELFTEST-* placeholder that never
# leaves this file: none of it is an approved route graph, an approved launch
# record, a native id, or a publication result. The graph below has exactly
# the shape Skill 49's compiler emits, so the reader is exercised against the
# approved contract rather than against a shape invented here.
_SELFTEST_GRAPH = {
    "schema_version": "1.0",
    "tenant_id": "SELFTEST-TENANT",
    "location_id": "LOC_TEST",
    "launch_id": "SELFTEST-LAUNCH",
    "revision": 1,
    "nodes": [
        {"page_id": "SELFTEST-LANDING", "role": "landing"},
        {"page_id": "SELFTEST-CHECKOUT", "role": "checkout"},
        {"page_id": "SELFTEST-U1", "role": "upsell_1"},
        {"page_id": "SELFTEST-D1", "role": "downsell_1"},
        {"page_id": "SELFTEST-U2", "role": "upsell_2"},
        {"page_id": "SELFTEST-TY", "role": "thank_you"},
    ],
    "edges": [
        {"from": "SELFTEST-LANDING", "event": "interest_submitted",
         "to": "SELFTEST-CHECKOUT", "guard": "verified_native_contact_submit"},
        {"from": "SELFTEST-CHECKOUT", "event": "payment_succeeded",
         "to": "SELFTEST-U1", "guard": "verified_main_payment"},
        {"from": "SELFTEST-U1", "event": "payment_succeeded",
         "to": "SELFTEST-U2", "guard": "verified_u1_payment"},
        {"from": "SELFTEST-U1", "event": "explicit_decline",
         "to": "SELFTEST-D1", "guard": "no_charge_decline"},
        {"from": "SELFTEST-D1", "event": "payment_succeeded",
         "to": "SELFTEST-U2", "guard": "verified_d1_payment"},
        {"from": "SELFTEST-D1", "event": "explicit_decline",
         "to": "SELFTEST-TY", "guard": "no_charge_decline"},
        {"from": "SELFTEST-U2", "event": "payment_succeeded",
         "to": "SELFTEST-TY", "guard": "verified_u2_payment"},
        {"from": "SELFTEST-U2", "event": "explicit_decline",
         "to": "SELFTEST-TY", "guard": "no_charge_decline"},
    ],
    "pending_failed_payment_behavior": PENDING_BEHAVIOR,
    "test_only": True,
}


def _selftest_offer(ref: str, price: str) -> dict:
    return {"product": {"product_ref": ref, "price_ref": price,
                        "source": "caller_supplied"}}


_EXAMPLE_SPEC = {
    "location_id": "LOC_TEST",
    "form_name": "Signature Order Form",
    "checkout_family": CHECKOUT_FAMILY_ORDER_UPSELL_V2_FUNNEL,
    "route_graph": _SELFTEST_GRAPH,
    "order_form": {"product": {"product_ref": "prod_main_offer",
                               "price_ref": "price_main",
                               "source": "caller_supplied"}},
    "collect_payment": True,
    "bump": {"product": {"product_ref": "prod_bump_offer",
                         "source": "caller_supplied"}},
    "upsells": [dict(_selftest_offer("prod_upsell_1", "price_u1"),
                     slot=SLOT_UPSELL_1),
                dict(_selftest_offer("prod_upsell_2", "price_u2"),
                     slot=SLOT_UPSELL_2)],
    "downsells": [dict(_selftest_offer("prod_downsell_1", "price_d1"),
                       slot=SLOT_DOWNSELL_1)],
    "thank_you": True,
}


_GOOD_RENDER = {
    "order_tile_present": True, "payment_tile_present": True,
    "selected_product_ref": "prod_main_offer",
    "selected_price_ref": "price_main",
    "bump_present": True, "bump_checked": False,
    "bump_selected_product_ref": "prod_bump_offer",
    "upsell_1_selected_product_ref": "prod_upsell_1",
    "upsell_1_selected_price_ref": "price_u1",
    "upsell_2_selected_product_ref": "prod_upsell_2",
    "upsell_2_selected_price_ref": "price_u2",
    "downsell_1_selected_product_ref": "prod_downsell_1",
    "downsell_1_selected_price_ref": "price_d1",
    "thank_you_step_present": True,
}


def _selftest() -> int:
    errors: List[str] = []

    plan = build_order_plan(_EXAMPLE_SPEC)
    slots = [e.get("slot") for e in plan["elements"]]
    if slots != [SLOT_MAIN, SLOT_COLLECT_PAYMENT, SLOT_BUMP, SLOT_UPSELL_1,
                 SLOT_DOWNSELL_1, SLOT_UPSELL_2, "thank_you"]:
        errors.append(f"element slots/order wrong: {slots}")
    by_slot = {e["slot"]: e for e in plan["elements"] if e.get("slot")}
    if by_slot[SLOT_UPSELL_1].get("page_id") == by_slot[SLOT_UPSELL_2].get("page_id"):
        errors.append("the two upsells share one page id - slots must be distinct")
    if by_slot[SLOT_UPSELL_2].get("page_id") != "SELFTEST-U2" \
            or by_slot[SLOT_DOWNSELL_1].get("page_id") != "SELFTEST-D1":
        errors.append(f"extra offers did not take the graph's page ids: "
                      f"{ {k: v.get('page_id') for k, v in by_slot.items()} }")
    tiles = {e["slot"]: e.get("tile") for e in plan["elements"]}
    if tiles[SLOT_MAIN] != "Sell Products" \
            or tiles[SLOT_COLLECT_PAYMENT] != "Collect Payment":
        errors.append(f"tile mapping wrong: {tiles}")
    bump = by_slot[SLOT_BUMP]
    if bump["default_checked"] is not False:
        errors.append("bump default must be unchecked (False)")

    # A native one-click purchase action, per extra slot: bound to its own
    # product and price, inside the native payment session, with no action id
    # invented and no navigation.
    for slot, price in ((SLOT_UPSELL_1, "price_u1"),
                        (SLOT_UPSELL_2, "price_u2"),
                        (SLOT_DOWNSELL_1, "price_d1")):
        action = by_slot[slot].get("native_action") or {}
        if action.get("kind") != NATIVE_PURCHASE_KIND \
                or action.get("price_ref") != price \
                or action.get("payment_session") != NATIVE_PAYMENT_SESSION \
                or action.get("action_id") is not None \
                or action.get("navigates") is not False:
            errors.append(f"{slot}: native purchase action wrong: {action}")

    # Links come from the approved graph - the approved sequence exactly.
    u1, d1, u2 = (by_slot[SLOT_UPSELL_1]["links"],
                  by_slot[SLOT_DOWNSELL_1]["links"],
                  by_slot[SLOT_UPSELL_2]["links"])
    if (u1["accept"], u1["decline"]) != ("SELFTEST-U2", "SELFTEST-D1"):
        errors.append(f"U1 links wrong: {u1}")
    if (d1["accept"], d1["decline"]) != ("SELFTEST-U2", "SELFTEST-TY"):
        errors.append(f"D1 links wrong: {d1}")
    if (u2["accept"], u2["decline"]) != ("SELFTEST-TY", "SELFTEST-TY"):
        errors.append(f"U2 links wrong: {u2}")
    for label, links in (("U1", u1), ("D1", d1), ("U2", u2)):
        if links["on_payment_failed"]["is_decline"] is not False \
                or links["on_payment_pending"]["is_acceptance"] is not False:
            errors.append(f"{label}: pending/failed must not be a decline")
        if links["on_explicit_decline"]["guard"] != DECLINE_GUARD:
            errors.append(f"{label}: decline edge guard not carried verbatim")

    patch = form_task_patch(plan)
    if patch["order_binding"]["product_ref"] != "prod_main_offer":
        errors.append(f"form_task_patch wrong: {patch}")
    pe = form_task_patch(plan, per_element=True)["order_element_bindings"]
    for slot in (SLOT_MAIN, SLOT_COLLECT_PAYMENT, SLOT_BUMP, SLOT_UPSELL_1,
                 SLOT_UPSELL_2, SLOT_DOWNSELL_1):
        if slot not in pe:
            errors.append(f"{slot} binding dropped from the per-element patch")
    if pe.get(SLOT_UPSELL_2, {}).get("price_ref") != "price_u2":
        errors.append(f"U2 per-element binding wrong: {pe.get(SLOT_UPSELL_2)}")

    # Fail-closed gates.
    no_decline = json.loads(json.dumps(_SELFTEST_GRAPH))
    no_decline["edges"] = [e for e in no_decline["edges"]
                           if not (e["from"] == "SELFTEST-U1"
                                   and e["event"] == "explicit_decline")]
    base = {"location_id": "L",
            "order_form": {"product": {"product_ref": "p",
                                       "source": "caller_supplied"}}}
    bad_specs = [
        ({}, "no location"),
        ({"location_id": "L"}, "no order_form"),
        ({"location_id": "L", "order_form": {}}, "unbound order form"),
        ({"location_id": "L",
          "order_form": {"product": {"source": "caller_supplied"}}}, "no ref"),
        ({"location_id": "L",
          "order_form": {"product": {"product_ref": "p",
                                     "source": "guessed"}}}, "bad source"),
        (dict(base, bump={"product": {"product_ref": "b",
                                      "source": "caller_supplied"},
                          "default_checked": True}), "pre-checked bump"),
        (dict(base, checkout_family=CHECKOUT_FAMILY_ORDER_UPSELL_V2_FUNNEL,
              route_graph=_SELFTEST_GRAPH,
              upsell={"product": {"product_ref": "u", "price_ref": "pu",
                                  "source": "caller_supplied"},
                      "one_click": False}), "one_click=false"),
        (dict(base, route_graph=_SELFTEST_GRAPH,
              upsell={"product": {"product_ref": "u", "price_ref": "pu",
                                  "source": "caller_supplied"}}),
         "extras without checkout_family"),
        (dict(base, checkout_family=CHECKOUT_FAMILY_ORDER_UPSELL_V2_FUNNEL,
              upsell={"product": {"product_ref": "u", "price_ref": "pu",
                                  "source": "caller_supplied"}}),
         "extras without route_graph"),
        (dict(base, checkout_family=CHECKOUT_FAMILY_ORDER_UPSELL_V2_FUNNEL,
              route_graph=_SELFTEST_GRAPH,
              upsells=[dict(_selftest_offer("u", "pu"), slot=SLOT_UPSELL_1),
                       dict(_selftest_offer("u2", "pu2"), slot=SLOT_UPSELL_1)]),
         "duplicate upsell slot"),
        (dict(base, checkout_family=CHECKOUT_FAMILY_ORDER_UPSELL_V2_FUNNEL,
              route_graph=_SELFTEST_GRAPH,
              upsell={"product": {"product_ref": "u",
                                  "source": "caller_supplied"}}),
         "extra without price_ref"),
        (dict(base, checkout_family=CHECKOUT_FAMILY_ORDER_UPSELL_V2_FUNNEL,
              route_graph=_SELFTEST_GRAPH,
              upsell={"product": {"product_ref": "u", "price_ref": "pu",
                                  "source": "caller_supplied"},
                      "href": "#thank-you"}), "navigation as purchase"),
        (dict(base, checkout_family=CHECKOUT_FAMILY_ORDER_UPSELL_V2_FUNNEL,
              route_graph=no_decline,
              upsell={"product": {"product_ref": "u", "price_ref": "pu",
                                  "source": "caller_supplied"}}),
         "graph missing the decline edge"),
    ]
    for spec, label in bad_specs:
        try:
            build_order_plan(spec)
            errors.append(f"bad spec ({label}) was not refused")
        except OrderPlanError:
            pass

    # Rendered-evidence verification: pass shape + each failure shape.
    good = verify_order_render(plan, dict(_GOOD_RENDER))
    if not good["ok"]:
        errors.append(f"good render must pass: {good['reasons']}")
    for label, rendered in (
        ("wrong product", dict(_GOOD_RENDER, selected_product_ref="prod_OTHER")),
        ("checked bump", dict(_GOOD_RENDER, bump_checked=True)),
        ("unobserved bump", dict(_GOOD_RENDER, bump_checked=None)),
        ("missing tile", dict(_GOOD_RENDER, order_tile_present=False)),
        ("wrong second upsell", dict(_GOOD_RENDER,
                                     upsell_2_selected_product_ref="prod_OTHER")),
    ):
        verdict = verify_order_render(plan, rendered)
        if verdict["ok"]:
            errors.append(f"render case {label!r} must fail but passed")

    # CHK-19 proof: a bump bound to product X but rendering product Y fails.
    wrong_bump = dict(_GOOD_RENDER, bump_selected_product_ref="prod_WRONG_BUMP")
    verdict = verify_order_render(plan, wrong_bump)
    if verdict["ok"] or not any(
            c["check"] == "bump_selected_product_matches_binding"
            and not c["ok"] for c in verdict["checks"]):
        errors.append("bump_selected_product_ref != binding must fail "
                      f"bump_selected_product_matches_binding: {verdict}")

    # Funnel order-form step target, bump placement, driver steps.
    if plan["surface"] != SURFACE_FUNNEL_ORDER_STEP or any(
            not e.get("page_id") for e in plan["elements"]):
        errors.append("every element must carry a page id from the graph")
    if bump.get("placement", {}).get("after") != KIND_ORDER_FORM:
        errors.append("bump has no placement step after the order form")
    actions = [s["action"] for s in plan["steps"]]
    if actions.index("add_order_bump") < actions.index("set_order_form_product") \
            or actions[-1] != "capture_order_render":
        errors.append(f"driver steps out of order: {actions}")
    step_slots = [s.get("slot") for s in plan["steps"] if s.get("slot")]
    if len(step_slots) != len(set(step_slots)) \
            or SLOT_UPSELL_1 not in step_slots or SLOT_UPSELL_2 not in step_slots:
        errors.append(f"driver steps do not carry distinct slots: {step_slots}")

    # Evidence must come from the capture function.
    cap = capture_order_render(plan, lambda _p: dict(_GOOD_RENDER),
                               source="fixture")
    good_cap = verify_order_render(plan, cap, require_capture=True)
    if not good_cap["ok"] or not good_cap["attested"] or good_cap["live_capture"]:
        errors.append(f"fixture capture must verify, attested, not live: {good_cap}")
    for label, ev in (
        ("hand-written dict", dict(_GOOD_RENDER)),
        ("edited after capture", dict(cap, observations=dict(
            cap["observations"], bump_selected_product_ref="prod_WRONG_BUMP"))),
        ("forged hash", dict(cap, provenance_hash="0" * 64)),
        ("other plan", capture_order_render(
            build_order_plan(dict(_EXAMPLE_SPEC, location_id="OTHER")),
            lambda _p: dict(_GOOD_RENDER), source="fixture")),
    ):
        if verify_order_render(plan, ev, require_capture=True)["ok"]:
            errors.append(f"evidence {label!r} must be refused")
    no_bump_key = {k: v for k, v in _GOOD_RENDER.items()
                   if k != "bump_selected_product_ref"}
    if verify_order_render(plan, capture_order_render(
            plan, lambda _p: dict(no_bump_key), source="fixture"))["ok"]:
        errors.append("captured evidence without the bump product read-back "
                      "must fail")

    # Price binding + per-element patch.
    priced = build_order_plan(dict(_EXAMPLE_SPEC, order_form={"product": {
        "product_ref": "prod_main_offer", "price_ref": "price_main",
        "source": "caller_supplied"}}))
    no_price_readback = {k: v for k, v in _GOOD_RENDER.items()
                         if k != "selected_price_ref"}
    if verify_order_render(priced, no_price_readback)["ok"] or \
            not verify_order_render(priced, dict(
                _GOOD_RENDER, selected_price_ref="price_main"))["ok"]:
        errors.append("price_ref binding must require the matching read-back")
    pe = form_task_patch(priced, per_element=True)["order_element_bindings"]
    if pe["Sell Products"].get("price_ref") != "price_main" \
            or "Collect Payment" not in pe:
        errors.append(f"per-element bindings not carried: {pe}")

    # Billing terms carry through the plan, the driver step and the patch.
    billed = build_order_plan(dict(_EXAMPLE_SPEC, order_form={"product": {
        "product_ref": "prod_main_offer", "price_ref": "price_main",
        "billing": {"billing_type": "recurring", "recurring_interval": "month"},
        "source": "caller_supplied"}}))
    bb = next(e for e in billed["elements"]
              if e["kind"] == KIND_ORDER_FORM)["binding"]["billing"]
    patch_b = form_task_patch(billed, per_element=True)
    step_b = next(s for s in billed["steps"]
                  if s["action"] == "set_order_form_product")
    if bb.get("billing_type") != "recurring" \
            or patch_b["order_binding"].get("billing", {}).get("recurring_interval") != "month" \
            or step_b.get("binding", {}).get("billing", {}).get("recurring_interval") != "month":
        errors.append("approved billing terms must reach the patch and the driver step")
    for bad_billing in ({"billing_type": "installment", "installment_count": 3},
                        {"recurring_interval": "month"},
                        {"billing_type": "one_time", "recurring_interval": "month"}):
        try:
            build_order_plan(dict(_EXAMPLE_SPEC, order_form={"product": {
                "product_ref": "p", "source": "caller_supplied",
                "billing": bad_billing}}))
            errors.append(f"billing term {bad_billing!r} was not refused")
        except OrderPlanError:
            pass

    # Lead capture: native builder route, explicit fields, verified in render.
    lc = build_order_plan(dict(_EXAMPLE_SPEC,
                               lead_capture={"fields": ["email", "phone"]}))
    lc_el = next(e for e in lc["elements"] if e["kind"] == KIND_LEAD_CAPTURE)
    if lc_el["placement"]["step"] != "add_lead_capture_form" \
            or lc_el["placement"]["requires_order_binding"] is not False \
            or lc_el["binding"] is not None \
            or lc_el["fields"] != ["email", "phone"]:
        errors.append(f"lead_capture element wrong: {lc_el}")
    lc_rendered = dict(_GOOD_RENDER, lead_capture_present=True,
                       lead_capture_fields=["phone", "email"])
    if not verify_order_render(lc, lc_rendered)["ok"]:
        errors.append("a present lead-capture form with the planned fields must pass")
    if verify_order_render(lc, dict(lc_rendered,
                                   lead_capture_fields=["email"]))["ok"]:
        errors.append("a lead-capture form missing a planned field must fail")
    if verify_order_render(lc, _GOOD_RENDER)["ok"]:
        errors.append("an unobserved lead-capture form must fail")
    try:
        build_order_plan(dict(_EXAMPLE_SPEC, lead_capture={}))
        errors.append("lead_capture without explicit fields was not refused")
    except OrderPlanError:
        pass

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL - {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS - order-element plan verified (no network / no browser)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="ghl_order_elements",
        description="Skill-6 native order-element THINK layer "
                    "(schema skill6-order-plan/1).",
    )
    p.add_argument("--selftest", action="store_true",
                   help="Run the no-network self-test and exit.")
    p.add_argument("--plan", metavar="SPEC_JSON",
                   help="Build a plan from a spec JSON file and print it.")
    p.add_argument("--verify-render", nargs=2,
                   metavar=("PLAN_JSON", "EVIDENCE_JSON"),
                   help="Verify capture evidence against a plan; a "
                        "hand-written evidence file is refused.")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.verify_render:
        with open(args.verify_render[0], "r", encoding="utf-8") as fh:
            plan = json.load(fh)
        with open(args.verify_render[1], "r", encoding="utf-8") as fh:
            evidence = json.load(fh)
        verdict = verify_order_render(plan, evidence, require_capture=True)
        print(json.dumps(verdict, indent=2))
        return 0 if verdict["ok"] else 1
    if args.plan:
        with open(args.plan, "r", encoding="utf-8") as fh:
            spec = json.load(fh)
        print(json.dumps(build_order_plan(spec), indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
