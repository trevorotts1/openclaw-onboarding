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


def _tile_element(kind: str, tile: str, binding: dict) -> dict:
    """An order element placed on the funnel order-form step. ``tile`` is the
    legacy native-element name only; it is NOT placed through the form
    builder (see CHECKOUT SURFACE)."""
    verify = {"selected_product_matches_binding": True}
    if "price_ref" in binding:
        verify["selected_price_matches_binding"] = True
    return {
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


def _price_verify(binding: dict, verify: dict) -> dict:
    if "price_ref" in binding:
        verify["selected_price_matches_binding"] = True
    return verify


def _links(elements: List[dict]) -> None:
    """Accept / decline step links (S06-02): which funnel step the buyer
    lands on after Yes / No thanks. Names step kinds, never invented ids."""
    kinds = [e["kind"] for e in elements]

    def first(*cands: str) -> Optional[str]:
        return next((c for c in cands if c in kinds), None)

    for e in elements:
        if e["kind"] == KIND_UPSELL:
            e["links"] = {"accept": first(KIND_THANK_YOU),
                          "decline": first(KIND_DOWNSELL, KIND_THANK_YOU)}
        elif e["kind"] == KIND_DOWNSELL:
            e["links"] = {"accept": first(KIND_THANK_YOU),
                          "decline": first(KIND_THANK_YOU)}


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
    element (the bump AFTER the order form), then capture the render."""
    steps: List[dict] = [{"n": 1, "action": "open_funnel_order_form_step",
                          "target": SURFACE_FUNNEL_ORDER_STEP}]
    for e in elements:
        step = {"n": len(steps) + 1, "action": _STEP_ACTIONS[e["kind"]],
                "element": e["kind"]}
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


def build_order_plan(spec: dict) -> dict:
    """Build (and fully validate) an order-element plan from ``spec``.

    Spec shape::

        {
          "location_id": "<subaccount id>",            # required
          "form_name": "<native form name>",           # optional label
          "order_form":      {"product": {binding}},   # REQUIRED
          "collect_payment": {"product": {binding}},   # optional; defaults
                                                       # to the order-form
                                                       # binding when true
          "bump":    {"product": {binding}},           # optional; may carry
                     # "default_checked": false - true is REFUSED
          "upsell":  {"product": {binding}},           # optional one-click
          "downsell": {"product": {binding}},          # optional
          "thank_you": true,                           # optional step
          "lead_capture": {"fields": ["email"]},       # optional native form
        }

    A binding is ``{"product_ref", "source", "offer_id"?, "price_ref"?, "billing"?}``.
    ``billing`` carries the approved F08 terms verbatim
    (``billing_type`` / ``recurring_interval`` / ``trial_days``); it is never
    flattened into ``one_time`` and an installment term is refused. An approved
    record's ``trial`` is carried as the native ``trial_then_recurring``.

    Every element carries its product binding or the plan is refused.
    Returns the plan dict (schema ``skill6-order-plan/1``)."""
    if not isinstance(spec, dict):
        raise OrderPlanError(f"order spec must be a mapping, got "
                             f"{type(spec).__name__}")
    location_id = str(spec.get("location_id") or "").strip()
    if not location_id:
        raise OrderPlanError("order spec carries no location_id - an order "
                             "plan is always scoped to one subaccount")

    order_form_spec = spec.get("order_form")
    if not isinstance(order_form_spec, dict) or "product" not in order_form_spec:
        raise OrderPlanError(
            "order spec has no order_form product binding - the order form "
            "is the core native order element and it cannot be planned "
            "unbound (fail closed)")
    main_binding = _binding(order_form_spec.get("product"),
                            element=KIND_ORDER_FORM)

    elements: List[dict] = [
        _tile_element(KIND_ORDER_FORM, TILE_ORDER_FORM, main_binding)]

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
                                      TILE_COLLECT_PAYMENT, cp_binding))

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
            "tile": None,
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

    upsell_spec = spec.get("upsell")
    if upsell_spec is not None:
        if not isinstance(upsell_spec, dict) or "product" not in upsell_spec:
            raise OrderPlanError("upsell: a one-click upsell needs its own "
                                 "product binding (fail closed)")
        if upsell_spec.get("one_click") is False:
            raise OrderPlanError(
                "upsell: one_click=false contradicts the element - the "
                "native order form's upsell is a one-click offer; a "
                "multi-step offer is a separate funnel step, not this "
                "element")
        up_binding = _binding(upsell_spec.get("product"),
                              element=KIND_UPSELL)
        elements.append({
            "kind": KIND_UPSELL,
            "tile": None,
            "placement": {"target": SURFACE_FUNNEL_ORDER_STEP,
                          "step": _STEP_ACTIONS[KIND_UPSELL],
                          "requires_order_binding": True},
            "surface": "native post-purchase one-click upsell step",
            "one_click": True,
            "binding": up_binding,
            "verify": _price_verify(up_binding,
                                    {"selected_product_matches_binding": True}),
        })

    downsell_spec = spec.get("downsell")
    if downsell_spec is not None:
        if not isinstance(downsell_spec, dict) or "product" not in downsell_spec:
            raise OrderPlanError("downsell: a downsell needs its own product "
                                 "binding (fail closed)")
        down_binding = _binding(downsell_spec.get("product"),
                                element=KIND_DOWNSELL)
        elements.append({
            "kind": KIND_DOWNSELL,
            "tile": None,
            "placement": {"target": SURFACE_FUNNEL_ORDER_STEP,
                          "step": _STEP_ACTIONS[KIND_DOWNSELL],
                          "requires_order_binding": True},
            "surface": "native post-purchase downsell step (shown when the "
                       "upsell is declined)",
            "binding": down_binding,
            "verify": _price_verify(down_binding,
                                    {"selected_product_matches_binding": True}),
        })

    ty_spec = spec.get("thank_you")
    if ty_spec:
        # DTY-11: the post-purchase thank-you step has a placement too; it
        # sells nothing, so it carries no product binding.
        elements.append({
            "kind": KIND_THANK_YOU,
            "tile": None,
            "surface": "native post-purchase thank-you step",
            "placement": {"target": SURFACE_FUNNEL_ORDER_STEP,
                          "step": "add_thank_you_step",
                          "requires_order_binding": False},
            "binding": None,
            "verify": {"step_present": True},
        })

    kinds = [e["kind"] for e in elements]
    if len(kinds) != len(set(kinds)):
        raise OrderPlanError(f"duplicate element kinds in plan: {kinds}")

    _links(elements)
    element_bindings = {
        e["tile"]: _patch_binding(e["binding"])
        for e in elements if e.get("tile") and e.get("binding")}
    return {
        "schema": PLAN_SCHEMA,
        "location_id": location_id,
        "form_name": str(spec.get("form_name") or ""),
        "surface": SURFACE_FUNNEL_ORDER_STEP,
        "elements": elements,
        "steps": placement_steps(elements),
        "form_task_patch": {
            "order_binding": _patch_binding(main_binding),
            "order_element_bindings": element_bindings,
        },
        "provenance": {
            "bindings": "every product reference is carried verbatim from "
                        "its named source; no product ID, price, variant, "
                        "or catalog data was fabricated by this plan",
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
    per tile, so Collect Payment keeps its own product/price instead of
    inheriting the order form's)."""
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
    for kind in (KIND_UPSELL, KIND_DOWNSELL):
        if kind in by_kind:
            expected = by_kind[kind]["binding"]["product_ref"]
            observed = rendered.get(f"{kind}_selected_product_ref")
            check(f"{kind}_selected_product_matches_binding",
                  observed == expected,
                  f"{kind} product read back as {observed!r}; the binding "
                  f"requires exactly {expected!r}")
            price_check(f"{kind}_selected_price_matches_binding",
                        by_kind[kind]["binding"],
                        f"{kind}_selected_price_ref")
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

_EXAMPLE_SPEC = {
    "location_id": "LOC_TEST",
    "form_name": "Signature Order Form",
    "order_form": {"product": {"product_ref": "prod_main_offer",
                               "source": "caller_supplied"}},
    "collect_payment": True,
    "bump": {"product": {"product_ref": "prod_bump_offer",
                         "source": "caller_supplied"}},
    "upsell": {"product": {"native_product_ref": "prod_upsell",
                           "source": "s44_phase_a"}},
    "downsell": {"product": {"product_ref": "prod_downsell",
                             "source": "caller_supplied"}},
}


_GOOD_RENDER = {
    "order_tile_present": True, "payment_tile_present": True,
    "selected_product_ref": "prod_main_offer",
    "bump_present": True, "bump_checked": False,
    "bump_selected_product_ref": "prod_bump_offer",
    "upsell_selected_product_ref": "prod_upsell",
    "downsell_selected_product_ref": "prod_downsell",
}


def _selftest() -> int:
    errors: List[str] = []

    plan = build_order_plan(_EXAMPLE_SPEC)
    kinds = [e["kind"] for e in plan["elements"]]
    if kinds != [KIND_ORDER_FORM, KIND_COLLECT_PAYMENT, KIND_ORDER_BUMP,
                 KIND_UPSELL, KIND_DOWNSELL]:
        errors.append(f"element kinds/order wrong: {kinds}")
    tiles = {e["kind"]: e.get("tile") for e in plan["elements"]}
    if tiles[KIND_ORDER_FORM] != "Sell Products" \
            or tiles[KIND_COLLECT_PAYMENT] != "Collect Payment":
        errors.append(f"tile mapping wrong: {tiles}")
    bump = next(e for e in plan["elements"] if e["kind"] == KIND_ORDER_BUMP)
    if bump["default_checked"] is not False:
        errors.append("bump default must be unchecked (False)")
    upsell = next(e for e in plan["elements"] if e["kind"] == KIND_UPSELL)
    if upsell["binding"]["product_ref"] != "prod_upsell" \
            or upsell["binding"]["binding_source"] != "s44_phase_a":
        errors.append(f"native_product_ref key not carried verbatim: {upsell}")
    patch = form_task_patch(plan)
    if patch["order_binding"]["product_ref"] != "prod_main_offer":
        errors.append(f"form_task_patch wrong: {patch}")

    # Fail-closed gates.
    bad_specs = [
        {},                                                            # no location
        {"location_id": "L"},                                          # no order_form
        {"location_id": "L", "order_form": {}},                        # unbound
        {"location_id": "L", "order_form": {"product": {"source": "caller_supplied"}}},   # no ref
        {"location_id": "L", "order_form": {"product": {"product_ref": "p", "source": "guessed"}}},
        {"location_id": "L",
         "order_form": {"product": {"product_ref": "p", "source": "caller_supplied"}},
         "bump": {"product": {"product_ref": "b", "source": "caller_supplied"},
                  "default_checked": True}},                          # pre-checked bump
        {"location_id": "L",
         "order_form": {"product": {"product_ref": "p", "source": "caller_supplied"}},
         "upsell": {"product": {"product_ref": "u", "source": "caller_supplied"},
                    "one_click": False}},
    ]
    for i, bad in enumerate(bad_specs):
        try:
            build_order_plan(bad)
            errors.append(f"bad spec #{i} was not refused: {bad}")
        except OrderPlanError:
            pass

    # Rendered-evidence verification: pass shape + each failure shape.
    good = verify_order_render(plan, {
        "order_tile_present": True, "payment_tile_present": True,
        "selected_product_ref": "prod_main_offer",
        "bump_present": True, "bump_checked": False,
        "upsell_selected_product_ref": "prod_upsell",
        "downsell_selected_product_ref": "prod_downsell",
    })
    if not good["ok"]:
        errors.append(f"good render must pass: {good['reasons']}")
    for label, rendered in (
        ("wrong product", {"order_tile_present": True,
                           "payment_tile_present": True,
                           "selected_product_ref": "prod_OTHER",
                           "bump_present": True, "bump_checked": False,
                           "upsell_selected_product_ref": "prod_upsell",
                           "downsell_selected_product_ref": "prod_downsell"}),
        ("checked bump", {"order_tile_present": True,
                          "payment_tile_present": True,
                          "selected_product_ref": "prod_main_offer",
                          "bump_present": True, "bump_checked": True,
                          "upsell_selected_product_ref": "prod_upsell",
                          "downsell_selected_product_ref": "prod_downsell"}),
        ("unobserved bump", {"order_tile_present": True,
                             "payment_tile_present": True,
                             "selected_product_ref": "prod_main_offer",
                             "bump_present": True, "bump_checked": None,
                             "upsell_selected_product_ref": "prod_upsell",
                             "downsell_selected_product_ref": "prod_downsell"}),
        ("missing tile", {"order_tile_present": False,
                          "payment_tile_present": True,
                          "selected_product_ref": "prod_main_offer",
                          "bump_present": True, "bump_checked": False,
                          "upsell_selected_product_ref": "prod_upsell",
                          "downsell_selected_product_ref": "prod_downsell"}),
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
    if not verify_order_render(plan, _GOOD_RENDER)["ok"]:
        errors.append("matching bump product must pass")

    # Funnel order-form step target, bump placement, driver steps, links.
    if plan["surface"] != SURFACE_FUNNEL_ORDER_STEP or any(
            e["placement"]["target"] != SURFACE_FUNNEL_ORDER_STEP
            for e in plan["elements"] if e.get("placement")):
        errors.append("plan must target the funnel order-form step")
    if bump.get("placement", {}).get("after") != KIND_ORDER_FORM:
        errors.append("bump has no placement step after the order form")
    actions = [s["action"] for s in plan["steps"]]
    if actions.index("add_order_bump") < actions.index("set_order_form_product") \
            or actions[-1] != "capture_order_render":
        errors.append(f"driver steps out of order: {actions}")
    if upsell["links"] != {"accept": None, "decline": KIND_DOWNSELL}:
        errors.append(f"upsell links wrong: {upsell['links']}")

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
    if verify_order_render(priced, dict(_GOOD_RENDER))["ok"] or \
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
