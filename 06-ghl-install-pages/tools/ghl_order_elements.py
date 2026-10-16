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
          "bump_present": bool,
          "bump_checked": bool | None,   # None = state not observed
        }

    Returns ``{ok, checks, reasons}`` - a pure verdict that never raises,
    in the style of ``ghl_builder.assert_seo_populated``. ``ok`` is True
    only when every planned element's evidence matches: tiles present,
    selected product EXACTLY equal to the binding reference, bump present
    and observed UNCHECKED."""
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
