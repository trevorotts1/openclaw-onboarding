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
     "source": "caller_supplied" | "s44_phase_a"}

``product_ref`` is whatever identifier the caller supplies - an S44 Phase A
product reference when Phase A delivers one (prep Q2; NOT delivered at the
time of this build, so plans today carry ``caller_supplied`` references),
otherwise an explicitly caller-supplied reference. This module NEVER
invents an S44 ID, a price, a variant, or catalog data, and it carries no
price field at all: pricing lives with the product's owner, not in a
placement plan.

BUMP DEFAULT (packet section 9 acceptance shape)
------------------------------------------------
An order bump's default state is UNCHECKED. A spec that asks for a
pre-checked bump is refused (:class:`OrderPlanError`): pre-checked consent /
offer boxes are not a state this builder will plan.

WHAT THIS MODULE DOES NOT DO
----------------------------
No browser, no network, no GHL writes. Placement itself rides the form
builder's existing F5 machinery (the dumb layer); the native styling
surface, the two saves, ``render_check``, and receipts ride the existing
rails (prep steps 7-8). Whether GHL also exposes order elements as
page-data the REST canvas can splice is prep Q3 - OPEN; this plan is
surface-neutral (it names the native element and its binding, not a splice
mechanism), and live placement proof stays LIVE_PROOF_PENDING until an
approved test location exists (prep Q4).

CLI
---
    python3 ghl_order_elements.py --selftest
    python3 ghl_order_elements.py --plan <spec.json>   # print the plan JSON
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any, Dict, List, Optional

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

#: Where a product binding may come from. There is no third source: a
#: reference is either delivered by S44 Phase A or explicitly supplied by
#: the caller of this build. Anything else is refused.
BINDING_SOURCES = ("caller_supplied", "s44_phase_a")

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


def _binding(raw: Any, *, element: str) -> dict:
    """Validate one product binding. Accepts the canonical key
    ``product_ref`` (and the S44 design-notes key ``native_product_ref``,
    carried verbatim). Returns ``{product_ref, binding_source}``."""
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
    return {"product_ref": ref, "binding_source": source}


def _tile_element(kind: str, tile: str, binding: dict) -> dict:
    return {
        "kind": kind,
        "tile": tile,
        "quick_add_category": QUICK_ADD_CATEGORY,
        "placement": {
            "via": "ghl_form_builder F5 Quick-Add drag (form builder dumb "
                   "layer), guarded as an order element",
            "requires_order_binding": True,
        },
        "binding": binding,
        "verify": {"selected_product_matches_binding": True},
    }


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
        }

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
        elements.append({
            "kind": KIND_ORDER_BUMP,
            "tile": None,
            "surface": "native order-form bump offer",
            "binding": _binding(bump_spec.get("product"),
                                element=KIND_ORDER_BUMP),
            "default_checked": BUMP_DEFAULT_CHECKED,
            "verify": {"default_state": "unchecked",
                       "evidence": "rendered page (never stored bytes)"},
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
        elements.append({
            "kind": KIND_UPSELL,
            "tile": None,
            "surface": "native post-purchase one-click upsell step",
            "one_click": True,
            "binding": _binding(upsell_spec.get("product"),
                                element=KIND_UPSELL),
            "verify": {"selected_product_matches_binding": True},
        })

    downsell_spec = spec.get("downsell")
    if downsell_spec is not None:
        if not isinstance(downsell_spec, dict) or "product" not in downsell_spec:
            raise OrderPlanError("downsell: a downsell needs its own product "
                                 "binding (fail closed)")
        elements.append({
            "kind": KIND_DOWNSELL,
            "tile": None,
            "surface": "native post-purchase downsell step (shown when the "
                       "upsell is declined)",
            "binding": _binding(downsell_spec.get("product"),
                                element=KIND_DOWNSELL),
            "verify": {"selected_product_matches_binding": True},
        })

    kinds = [e["kind"] for e in elements]
    if len(kinds) != len(set(kinds)):
        raise OrderPlanError(f"duplicate element kinds in plan: {kinds}")

    return {
        "schema": PLAN_SCHEMA,
        "location_id": location_id,
        "form_name": str(spec.get("form_name") or ""),
        "elements": elements,
        "form_task_patch": {
            "order_binding": {
                "product_ref": main_binding["product_ref"],
                "source": main_binding["binding_source"],
            },
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


def form_task_patch(plan: dict) -> dict:
    """The dict a caller merges into a ``ghl_form_builder`` task so the form
    builder treats Payments tiles as bound order elements: preflight F-P10
    requires it, ``_resolve_fields`` stamps it onto the tile fields, and the
    F5 walk refuses to drag a Payments tile without it."""
    patch = (plan or {}).get("form_task_patch") or {}
    binding = patch.get("order_binding") or {}
    if not binding.get("product_ref"):
        raise OrderPlanError("plan carries no form_task_patch order_binding "
                             "- cannot hand an unbound plan to the form "
                             "builder")
    return {"order_binding": dict(binding)}


def verify_order_render(plan: dict, rendered: dict) -> dict:
    """Verify RENDERED / read-back evidence against the plan (prep step 5).

    ``rendered`` is evidence captured from the rendered page or a native
    read-back - NEVER stored autosave bytes::

        {
          "order_tile_present": bool,
          "payment_tile_present": bool,
          "selected_product_ref": "<the product the placed element is "
                                   "actually bound to, as read back>",
          "collect_payment_selected_product_ref": "<the product the "
                                   "Collect Payment tile is bound to, as "
                                   "read back; required when that element "
                                   "carries a binding distinct from the "
                                   "order form's>",
          "bump_present": bool,
          "bump_checked": bool | None,   # None = state not observed
        }

    Returns ``{ok, checks, reasons}`` - a pure verdict that never raises,
    in the style of ``ghl_builder.assert_seo_populated``. ``ok`` is True
    only when every planned element's evidence matches: tiles present,
    selected product EXACTLY equal to the binding reference, bump present
    and observed UNCHECKED. A collect-payment element whose binding is
    DISTINCT from the order form's is verified against its own read-back
    key (``collect_payment_selected_product_ref``), which must be present
    and exactly equal to that binding; when the collect-payment binding
    equals the order form's, the shared ``selected_product_ref`` check
    covers it and the separate key is not required."""
    checks: List[dict] = []
    reasons: List[str] = []
    rendered = rendered or {}
    elements = (plan or {}).get("elements") or []
    by_kind = {e.get("kind"): e for e in elements}

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            reasons.append(f"{name}: {detail}")

    if KIND_ORDER_FORM in by_kind:
        check("order_tile_present",
              bool(rendered.get("order_tile_present")),
              "the 'Sell Products' native tile must be present in the "
              "rendered form")
        expected = by_kind[KIND_ORDER_FORM]["binding"]["product_ref"]
        observed = rendered.get("selected_product_ref")
        check("selected_product_matches_binding",
              observed == expected,
              f"selected product read back as {observed!r}; the binding "
              f"requires exactly {expected!r}")
    if KIND_COLLECT_PAYMENT in by_kind:
        check("payment_tile_present",
              bool(rendered.get("payment_tile_present")),
              "the 'Collect Payment' native tile must be present in the "
              "rendered form")
        cp_expected = by_kind[KIND_COLLECT_PAYMENT]["binding"]["product_ref"]
        form_expected = (by_kind[KIND_ORDER_FORM]["binding"]["product_ref"]
                         if KIND_ORDER_FORM in by_kind else None)
        if cp_expected != form_expected:
            # A DISTINCT collect-payment binding (D1 cure): the order-form
            # check above compares the rendered selected product against
            # the ORDER FORM's binding only, so this element's declared
            # selected-product verification is performed here, against its
            # own read-back key, mirroring the upsell / downsell branches
            # below. A missing (unobserved) read-back fails. When the
            # collect-payment binding equals the order form's, the shared
            # check already covers it and no separate key is required.
            cp_observed = rendered.get("collect_payment_selected_product_ref")
            check("collect_payment_selected_product_matches_binding",
                  cp_observed == cp_expected,
                  f"collect-payment product read back as {cp_observed!r}; "
                  f"the distinct collect-payment binding requires exactly "
                  f"{cp_expected!r}")
    if KIND_ORDER_BUMP in by_kind:
        check("bump_present", bool(rendered.get("bump_present")),
              "the bump offer must be present on the rendered order form")
        observed_state = rendered.get("bump_checked")
        check("bump_default_unchecked",
              observed_state is False,
              "the bump's rendered default state must be observed "
              f"UNCHECKED (observed: {observed_state!r}); a checked or "
              "unobserved bump does not pass")
    for kind in (KIND_UPSELL, KIND_DOWNSELL):
        if kind in by_kind:
            expected = by_kind[kind]["binding"]["product_ref"]
            observed = rendered.get(f"{kind}_selected_product_ref")
            check(f"{kind}_selected_product_matches_binding",
                  observed == expected,
                  f"{kind} product read back as {observed!r}; the binding "
                  f"requires exactly {expected!r}")
    if not elements:
        check("plan_has_elements", False, "the plan carries no elements")
    return {"ok": not reasons, "checks": checks, "reasons": reasons}


# ── Checkout bindings - a Skill 83 mapping installed natively ───────────────
#
# The order-element layer above plans one native form. A launcher checkout is
# a JOURNEY: one simple offer, an offer chosen on a Product Selection page, or
# several levels folded into the signature page with no selection page. These
# functions turn the Skill 83 checkout mapping into an installation plan for
# each shape and read the result back into a receipt. They never create a
# selection page: the selection surface already exists (a Product Selection
# page, or the signature page's own level control).

CHECKOUT_BINDING_SCHEMA = "skill6-checkout-binding/1"
CHECKOUT_RECEIPT_SCHEMA = "skill6-checkout-readback/1"

MODE_TO_JOURNEY = {
    "combined_single_offer": "single_simple",
    "post_selection": "multiple_options",
    None: "folded_levels",
}

#: A builder-produced receipt is never a verified class. S79's verified
#: statuses require an independent reviewer; self-approval is not offered.
UNVERIFIED_RECEIPT_STATUSES = ("authored", "blocked")


class CheckoutBindingError(ValueError):
    """Raised when a journey cannot become an honest native installation: no
    native catalog readback for a bound offer, a selection mode without a
    selection, or a selection offered to a mode that has no selection page."""


def _native_readback(native_products: Any, offer_id: str, element: str) -> dict:
    """One offer's native product/price IDs, carried verbatim from the catalog
    readback. Never inferred from an offer ID and never fabricated."""
    readback = (native_products or {}).get(offer_id)
    if not isinstance(readback, dict):
        raise CheckoutBindingError(
            f"{element}: no native catalog readback for offer {offer_id!r} - "
            "a native order element is never installed against an unread "
            "product (fail closed)")
    product_id = str(readback.get("native_product_id") or "").strip()
    price_id = str(readback.get("native_price_id") or "").strip()
    if not product_id or not price_id:
        raise CheckoutBindingError(
            f"{element}: offer {offer_id!r} readback carries no native product "
            "and price id - refusing to bind an incomplete native mapping")
    return {"native_product_id": product_id, "native_price_id": price_id}


def build_checkout_binding(mapping: dict, *, native_products: dict,
                           selection: Optional[dict] = None) -> dict:
    """Build the native installation plan for one Skill 83 checkout mapping.

    ``mapping`` is ``launcher_core.checkout.order_form_mapping(...)`` as JSON.
    ``native_products`` maps ``offer_id -> {native_product_id, native_price_id}``
    from a native catalog readback (synthetic in tests). ``selection`` is
    ``{selection_ref, selection_revision}`` and is required for
    ``post_selection``, forbidden for every other mode.

    ``native_ready`` is False whenever the Skill 79 probe was not accepted or
    the contract has no mode for the journey shape; the blockers name why.
    """
    if not isinstance(mapping, dict):
        raise CheckoutBindingError(
            f"checkout mapping must be a mapping, got {type(mapping).__name__}")
    mode = mapping.get("checkout_mode")
    journey = mapping.get("journey_mode") or MODE_TO_JOURNEY.get(mode, "unknown")
    mains = list(mapping.get("main_offers") or [])
    if not mains:
        raise CheckoutBindingError(
            "checkout mapping carries no main offer - nothing native to install")

    if mode == "post_selection":
        ref = str((selection or {}).get("selection_ref") or "").strip()
        try:
            revision = int((selection or {}).get("selection_revision") or 0)
        except (TypeError, ValueError):
            revision = 0
        selected_offer_id = str((selection or {}).get("selected_offer_id")
                                or "").strip()
        if not ref or revision < 1:
            raise CheckoutBindingError(
                "post_selection: a selection_ref and selection_revision >= 1 "
                "are required; a checkout after a selection page without the "
                "selection it follows is refused")
        if selected_offer_id not in {o["offer_id"] for o in mains}:
            raise CheckoutBindingError(
                f"post_selection: selected_offer_id {selected_offer_id!r} is "
                "not one of the mapping's main offers; the checkout cannot be "
                "bound to an offer the selection page did not choose")
        selection_record = {"selection_ref": ref,
                            "selection_revision": revision,
                            "selected_offer_id": selected_offer_id}
    elif selection is not None:
        raise CheckoutBindingError(
            f"checkout_mode {mode!r} has no selection surface; a supplied "
            "selection would invent a page the journey does not have")
    else:
        selection_record = None

    folded = mode is None
    if mode == "combined_single_offer" and len(mains) != 1:
        raise CheckoutBindingError(
            f"combined_single_offer carries {len(mains)} main offers; the mode "
            "describes exactly one")

    bindings: List[dict] = []
    for index, offer in enumerate(mains):
        native = _native_readback(native_products, offer["offer_id"],
                                  "order_form")
        price = offer.get("price") or {}
        bindings.append({
            "element": KIND_ORDER_FORM,
            "offer_id": offer["offer_id"],
            "level_index": index if folded else None,
            "selected_price": {"amount_minor": price.get("amount_minor"),
                               "currency": price.get("currency")},
            "native": native,
            "binding": {"product_ref": native["native_product_id"],
                        "binding_source": "caller_supplied"},
            "price_binding": {"price_ref": native["native_price_id"],
                              "binding_source": "caller_supplied"},
        })

    bump_record = (mapping.get("supplied") or {}).get("bump")
    bump = None
    if isinstance(bump_record, dict):
        native = _native_readback(native_products, bump_record.get("offer_id"),
                                  KIND_ORDER_BUMP)
        bump = {
            "element": KIND_ORDER_BUMP,
            "offer_id": bump_record.get("offer_id"),
            "native": native,
            "binding": {"product_ref": native["native_product_id"],
                        "binding_source": "caller_supplied"},
            "default_checked": BUMP_DEFAULT_CHECKED,
        }

    def _optional(kind: str, offers: List[dict]) -> List[dict]:
        result = []
        for offer in offers or []:
            native = _native_readback(native_products, offer["offer_id"], kind)
            price = offer.get("price") or {}
            result.append({
                "element": kind,
                "offer_id": offer["offer_id"],
                "role": offer.get("role"),
                "selected_price": {"amount_minor": price.get("amount_minor"),
                                   "currency": price.get("currency")},
                "native": native,
                "binding": {"product_ref": native["native_product_id"],
                            "binding_source": "caller_supplied"},
            })
        return result

    upsells = _optional(KIND_UPSELL, mapping.get("upsell_offers") or [])
    downsells = _optional(KIND_DOWNSELL, mapping.get("downsell_offers") or [])

    probe = mapping.get("validator") or {}
    blocker_list: List[str] = []
    if mapping.get("checkout_mode_state") != "resolved":
        blocker_list.append(
            f"contract_gap: journey {journey!r} has no Skill 79 checkout_mode; "
            "folded levels keep their signature-page selection and no selection "
            "page or invented mode is added")
    if probe.get("state") != "bound":
        blocker_list.append(
            f"probe_unavailable: {probe.get('error', 'validator not bound')}")
    else:
        if (probe.get("control") or {}).get("result") != "accepted":
            blocker_list.append(
                "probe_control_rejected: the binding probe's known-good control "
                f"was refused ({(probe.get('control') or {}).get('error', '')})")
        result = (probe.get("probe") or {}).get("result")
        if result != "accepted":
            blocker_list.append(
                "probe_rejected: "
                f"{(probe.get('probe') or {}).get('rejected_because', 'unknown')}"
                f" ({(probe.get('probe') or {}).get('error', '')})")

    return {
        "schema": CHECKOUT_BINDING_SCHEMA,
        "journey_mode": journey,
        "checkout_mode": mode,
        "checkout_mode_state": mapping.get("checkout_mode_state"),
        "route_node": mapping.get("route_node") or "checkout",
        "location_id": (mapping.get("supplied") or {}).get("location_id"),
        "selection": selection_record,
        "new_selection_page": False,
        "bindings": bindings,
        "bump": bump,
        "upsells": upsells,
        "downsells": downsells,
        "installation": {
            "surface": "native Convert and Flow order form (F5 Payments "
                       "Quick-Add through ghl_form_builder)",
            "tiles": [TILE_ORDER_FORM, TILE_COLLECT_PAYMENT],
            "forms": ["order_form"] if not folded else
                     [f"order_form[{b['offer_id']}]" for b in bindings],
            "selection_surface": ("product_selection_page (already planned by "
                                  "Skill 78)" if mode == "post_selection" else
                                  "signature_page_level_control" if folded else
                                  "none"),
        },
        "native_ready": not blocker_list,
        "blockers": blocker_list,
    }


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def checkout_readback_receipt(plan: dict, readback: dict, *, producer_id: str,
                              request_input_hash: str) -> dict:
    """Verify a native installation readback and seal one receipt.

    ``readback`` is read from the installed native surface, never from stored
    autosave bytes::

        {"native_form_id", "native_page_id",
         "levels": {offer_id: {"selected_product_ref",
                               "selected_price_minor", "selected_currency"}},
         "bump": {"present", "checked", "native_product_ref"},
         "upsell": {"present", "selected_product_ref", "decline_destination"},
         "downsell": {...},
         "success_destination", "decline_destination", "error_destination",
         "payment": {"pending_state_copy_ref", "failed_state_copy_ref",
                     "retry_policy", "failed_access_granted"},
         "access": {"granted_on", "entitlement_ids"}}

    The receipt covers the selected price, upsell/decline paths, pending and
    failed payment, and access. A failed or pending payment that grants access
    fails. Status is only ``authored`` or ``blocked``: verification needs an
    independent reviewer and this layer never self-approves.
    """
    checks: List[dict] = []
    reasons: List[str] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            reasons.append(f"{name}: {detail}")

    readback = readback or {}
    check("native_form_installed", bool(readback.get("native_form_id")),
          "the installed native form id must be read back")
    check("native_page_installed", bool(readback.get("native_page_id")),
          "the installed native page id must be read back")

    levels = readback.get("levels") or {}
    selected_offer_id = (plan.get("selection") or {}).get("selected_offer_id")
    if plan.get("checkout_mode") == "post_selection":
        receipt_bindings = [b for b in plan.get("bindings") or []
                            if b["offer_id"] == selected_offer_id]
    else:
        receipt_bindings = list(plan.get("bindings") or [])
    for binding in receipt_bindings:
        offer_id = binding["offer_id"]
        label = f"level[{offer_id}]" if plan.get("checkout_mode") is None \
            else "checkout"
        observed = levels.get(offer_id) or {}
        price = binding.get("selected_price") or {}
        check(f"{label}.selected_product",
              observed.get("selected_product_ref")
              == binding["native"]["native_product_id"],
              f"selected product read back as "
              f"{observed.get('selected_product_ref')!r}; the binding requires "
              f"{binding['native']['native_product_id']!r}")
        check(f"{label}.selected_price",
              observed.get("selected_price_minor") == price.get("amount_minor")
              and observed.get("selected_currency") == price.get("currency"),
              f"selected price read back as "
              f"{observed.get('selected_price_minor')!r} "
              f"{observed.get('selected_currency')!r}; the mapping states "
              f"{price.get('amount_minor')!r} {price.get('currency')!r}")

    bump = plan.get("bump")
    bump_read = readback.get("bump") or {}
    if bump:
        check("bump.present", bool(bump_read.get("present")),
              "the bump offer must be present on the native form")
        check("bump.default_unchecked", bump_read.get("checked") is False,
              "the bump's read-back default state must be UNCHECKED "
              f"(observed: {bump_read.get('checked')!r})")
        check("bump.selected_product",
              bump_read.get("native_product_ref")
              == bump["native"]["native_product_id"],
              f"bump product read back as "
              f"{bump_read.get('native_product_ref')!r}; the binding requires "
              f"{bump['native']['native_product_id']!r}")
    else:
        check("bump.not_planned", True, "no bump offer was planned")

    for element, key in ((KIND_UPSELL, "upsell"), (KIND_DOWNSELL, "downsell")):
        planned = plan.get(element + "s") or []
        observed = readback.get(key) or {}
        if not planned:
            check(f"{key}.not_planned", True, f"no {key} was planned")
            continue
        check(f"{key}.present", bool(observed.get("present")),
              f"the {key} step must be present after checkout")
        check(f"{key}.selected_product",
              observed.get("selected_product_ref")
              == planned[0]["native"]["native_product_id"],
              f"{key} product read back as "
              f"{observed.get('selected_product_ref')!r}; the binding requires "
              f"{planned[0]['native']['native_product_id']!r}")
    upsell_read = readback.get("upsell") or {}
    if plan.get("upsells"):
        check("upsell.decline_path",
              bool(upsell_read.get("decline_destination")),
              "an explicit decline destination must be read back")
    check("checkout.decline_destination",
          bool(readback.get("decline_destination")),
          "checkout must carry a decline destination")
    check("checkout.error_destination",
          bool(readback.get("error_destination")),
          "checkout must carry a payment-error destination")
    check("checkout.success_destination",
          bool(readback.get("success_destination")),
          "checkout must carry a success destination")

    payment = readback.get("payment") or {}
    for field in ("pending_state_copy_ref", "failed_state_copy_ref",
                  "retry_policy"):
        check(f"payment.{field}", bool(payment.get(field)),
              f"{field} must be supplied for pending/failed payment states")
    check("payment.failed_grants_no_access",
          payment.get("failed_access_granted") is False,
          "a failed payment must never grant access")
    access = readback.get("access") or {}
    check("access.after_payment_only",
          access.get("granted_on") in ("payment_succeeded",
                                       "test_payment_succeeded"),
          "access is granted only by a succeeded payment; read back "
          f"{access.get('granted_on')!r}")

    if plan.get("checkout_mode") is None:
        check("folded.no_new_selection_page",
              plan.get("new_selection_page") is False
              and plan.get("selection") is None,
              "folded levels keep the signature page's own level control; no "
              "selection page is installed and no selection is invented")
    if plan.get("checkout_mode") == "post_selection":
        check("selection.bound_to_existing_page",
              bool((plan.get("selection") or {}).get("selection_ref"))
              and plan.get("new_selection_page") is False,
              "the checkout binds to the existing Product Selection page")

    blockers = list(plan.get("blockers") or []) + reasons
    body = {
        "schema": CHECKOUT_RECEIPT_SCHEMA,
        "contract": "s79/checkout.schema.json#checkout_result",
        "journey_mode": plan.get("journey_mode"),
        "checkout_mode": plan.get("checkout_mode"),
        "request_input_hash": request_input_hash,
        "producer_id": producer_id,
        "reviewer_id": None,
        "independent_review": False,
        "status": "blocked" if blockers else "authored",
        "test_record_refs": [f"local-fixture:{_canonical_sha256(plan)[:32]}"],
        "known_blockers": blockers,
        "native_form_id": readback.get("native_form_id"),
        "native_page_id": readback.get("native_page_id"),
        "native_product_id": (receipt_bindings[0]["native"]["native_product_id"]
                              if len(receipt_bindings) == 1 else None),
        "native_price_id": (receipt_bindings[0]["native"]["native_price_id"]
                            if len(receipt_bindings) == 1 else None),
        "bump_binding": ({"component_id": bump["offer_id"],
                          "default_selected": bump["default_checked"],
                          "native_product_id": bump["native"]["native_product_id"],
                          "native_price_id": bump["native"]["native_price_id"]}
                         if bump else None),
        "expected_success_destination": readback.get("success_destination"),
        "expected_decline_destination": readback.get("decline_destination"),
        "expected_error_destination": readback.get("error_destination"),
        "levels": [{"offer_id": b["offer_id"],
                    "native_product_id": b["native"]["native_product_id"],
                    "native_price_id": b["native"]["native_price_id"],
                    "selected_price": b.get("selected_price")}
                   for b in receipt_bindings],
        "checks": checks,
        "native_ready": not blockers,
        "artifact_hashes": [_canonical_sha256(plan),
                            _canonical_sha256(readback)],
    }
    body["receipt_sha256"] = _canonical_sha256(body)
    body["receipt_id"] = f"s06-checkout-{body['receipt_sha256'][:16]}"
    return body


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
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.plan:
        with open(args.plan, "r", encoding="utf-8") as fh:
            spec = json.load(fh)
        print(json.dumps(build_order_plan(spec), indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
