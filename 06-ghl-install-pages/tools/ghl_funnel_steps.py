#!/usr/bin/env python3
"""ghl_funnel_steps.py - S06-02: funnel COMMERCE installer (plan + execute + read-back).

Before this module Skill 6 could only install a launch as linear opt-in custom-code
pages: no native order form, no order bump, no one-click upsell/downsell, no
accept/decline branching. This module turns the Skill 83 route graph
(``{"nodes": [{page_id, role}], "edges": [{from, event, to, guard}]}``) plus the
launch offers into funnel steps with NATIVE types, attaches product+price to each
purchase step, places the bump on the order form, wires one-click accept/decline
to the route-graph targets, and reads every one back.

SPLIT (same two-layer rule as ghl_order_elements.py)
  * THINK  - :func:`build_funnel_plan`, :func:`verify_funnel_readback`,
             :func:`payment_gate` are pure: no browser, no network.
  * DO     - :func:`install_funnel` drives a caller-supplied ``driver`` (the one
             concrete browser/REST driver binds to the funnel order-form step per
             DECISIONS 2026-11-02; this module never imports a browser). Driver
             contract (all keyword-free, all return plain data):
               payment_provider_status(location_id) -> {"connected": bool, "provider": str}
               create_step(funnel_id, name, step_type)           -> step_id
               attach_price(step_id, product_id, price_id)       -> None
               place_element(step_id, kind, price_id, default_checked) -> None
               set_action(step_id, action, target_step_id)       -> None
               read_back(funnel_id) -> {"steps": [{"step_id", "type", "price_ids": [...],
                    "elements": [{"kind", "price_id", "default_checked"}],
                    "accept_target", "decline_target"}]}

FAIL CLOSED
  * product_id / price_id come ONLY from the caller's ``catalog`` (offer_id ->
    {product_id, price_id[, amount_minor]}); never invented. A missing entry, or an
    amount that disagrees with the offer, refuses the plan.
  * A missing payment-provider connection is the named operator manual gate
    ``MANUAL-GATE:payment_provider_connection`` and blocks ``ready``.
  * Any write without a verified ``publish`` / ``automation_write`` approval record
    is refused. There is no default verifier: the caller must pass the Command Center
    verifier (a service the AI session cannot write).

NOT DONE HERE (ceiling): navigation edges that are not commerce outcomes
(interest_submitted, selection_validated) are the page buttons of non-purchase pages
and are not set; the live capture of the order-form surface waits for an approved
test location (DECISIONS CHK-19).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Dict, List, Optional

# route role -> native funnel step type
STEP_TYPES = {
    "landing": "landing",
    "product_selection": "landing",
    "checkout": "order_form",
    "upsell_1": "upsell",
    "upsell_2": "upsell",
    "downsell_1": "downsell",
    "thank_you": "thank_you",
}
# role -> offer role whose price the step charges
PURCHASE_OFFER_ROLE = {
    "checkout": "main",
    "upsell_1": "upsell_1",
    "upsell_2": "upsell_2",
    "downsell_1": "downsell_1",
}
ONE_CLICK = ("upsell", "downsell")
APPROVAL_SCOPES = ("publish", "automation_write")
PAYMENT_GATE = "MANUAL-GATE:payment_provider_connection"


class FunnelPlanError(ValueError):
    """The plan cannot be built without inventing data."""


class ApprovalRefused(PermissionError):
    """A write was attempted without a verified approval record."""


def _price(offer: Dict[str, Any], catalog: Dict[str, Any]) -> Dict[str, Any]:
    entry = catalog.get(offer["offer_id"])
    if not isinstance(entry, dict) or not entry.get("product_id") or not entry.get("price_id"):
        raise FunnelPlanError(f"no product_id/price_id for offer {offer['offer_id']!r}")
    want = (offer.get("price") or {}).get("amount_minor")
    if "amount_minor" in entry and want is not None and entry["amount_minor"] != want:
        raise FunnelPlanError(f"catalog amount for {offer['offer_id']!r} disagrees with the offer")
    return {"offer_id": offer["offer_id"], "product_id": entry["product_id"],
            "price_id": entry["price_id"]}


def build_funnel_plan(graph: Dict[str, Any], offers: List[Dict[str, Any]],
                      catalog: Dict[str, Any]) -> Dict[str, Any]:
    """Route graph + offers + caller catalog -> explicit step plan (pure)."""
    nodes, edges = graph.get("nodes") or [], graph.get("edges") or []
    by_role: Dict[str, List[Dict[str, Any]]] = {}
    for o in offers:
        by_role.setdefault(o["role"], []).append(o)
    steps = []
    for n in nodes:
        role = n["role"]
        if role not in STEP_TYPES:
            raise FunnelPlanError(f"unknown route role {role!r}")
        step: Dict[str, Any] = {"page_id": n["page_id"], "role": role,
                                "type": STEP_TYPES[role], "prices": [], "bump": None,
                                "accept_to": None, "decline_to": None}
        orole = PURCHASE_OFFER_ROLE.get(role)
        if orole:
            offs = by_role.get(orole) or []
            if not offs:
                raise FunnelPlanError(f"route has {role} but no {orole!r} offer")
            step["prices"] = [_price(o, catalog) for o in offs]
        if role == "checkout" and by_role.get("bump"):
            step["bump"] = _price(by_role["bump"][0], catalog)
        if STEP_TYPES[role] in ONE_CLICK:
            for e in edges:
                if e["from"] != n["page_id"]:
                    continue
                if e["event"] == "payment_succeeded":
                    step["accept_to"] = e["to"]
                elif e["event"] == "explicit_decline":
                    step["decline_to"] = e["to"]
            if not (step["accept_to"] and step["decline_to"]):
                raise FunnelPlanError(f"{role} needs both an accept and a decline edge")
        elif role == "checkout":
            nxt = [e["to"] for e in edges
                   if e["from"] == n["page_id"] and e["event"] == "payment_succeeded"]
            step["accept_to"] = nxt[0] if nxt else None
        steps.append(step)
    plan = {"steps": steps}
    plan["plan_hash"] = hashlib.sha256(
        json.dumps(steps, sort_keys=True).encode()).hexdigest()
    return plan


def payment_gate(status: Optional[Dict[str, Any]]) -> Optional[str]:
    """Named manual gate when the payment provider is not verifiably connected."""
    if not isinstance(status, dict) or status.get("connected") is not True:
        return PAYMENT_GATE
    return None


def require_approval(record: Optional[Dict[str, Any]], plan: Dict[str, Any],
                     location_id: str, verifier: Optional[Callable[[Dict[str, Any]], bool]]) -> None:
    """Refuse unless a verified publish/automation_write record binds this plan+location."""
    if not isinstance(record, dict) or record.get("scope") not in APPROVAL_SCOPES:
        raise ApprovalRefused("no publish/automation_write approval record")
    if record.get("location_id") != location_id:
        raise ApprovalRefused("approval record is for another location")
    if record.get("plan_hash_prefix") != plan["plan_hash"][:8]:
        raise ApprovalRefused("approval record does not carry this plan's hash prefix")
    if verifier is None or verifier(record) is not True:
        raise ApprovalRefused("approval record not verified by the approval service")


def verify_funnel_readback(plan: Dict[str, Any], readback: Dict[str, Any],
                           step_ids: Dict[str, str]) -> List[str]:
    """Compare read-back to the plan. Returns mismatch strings; [] means verified."""
    bad: List[str] = []
    got = {s.get("step_id"): s for s in readback.get("steps") or []}
    for s in plan["steps"]:
        sid = step_ids.get(s["page_id"])
        r = got.get(sid)
        if r is None:
            bad.append(f"{s['role']}: step not read back")
            continue
        if r.get("type") != s["type"]:
            bad.append(f"{s['role']}: type {r.get('type')!r} != {s['type']!r}")
        if sorted(r.get("price_ids") or []) != sorted(p["price_id"] for p in s["prices"]):
            bad.append(f"{s['role']}: attached price ids differ")
        els = r.get("elements") or []
        if s["prices"] and s["type"] == "order_form":
            if not any(e.get("kind") == "order_form" for e in els):
                bad.append(f"{s['role']}: native order-form element missing")
        if s["bump"]:
            b = [e for e in els if e.get("kind") == "order_bump"]
            if not b or b[0].get("price_id") != s["bump"]["price_id"]:
                bad.append(f"{s['role']}: bump not bound to its price")
            elif b[0].get("default_checked") is not False:
                bad.append(f"{s['role']}: bump default is not unchecked")
        for key, field in (("accept_to", "accept_target"), ("decline_to", "decline_target")):
            want = step_ids.get(s[key]) if s[key] else None
            if s[key] and r.get(field) != want:
                bad.append(f"{s['role']}: {field} {r.get(field)!r} != route edge {want!r}")
    return bad


def install_funnel(plan: Dict[str, Any], driver: Any, funnel_id: str, location_id: str,
                   approval: Optional[Dict[str, Any]],
                   verifier: Optional[Callable[[Dict[str, Any]], bool]]) -> Dict[str, Any]:
    """Create/attach/place/link then read back. Refuses every write without approval."""
    require_approval(approval, plan, location_id, verifier)
    gates = [g for g in [payment_gate(driver.payment_provider_status(location_id))] if g]
    ids: Dict[str, str] = {}
    for s in plan["steps"]:
        ids[s["page_id"]] = driver.create_step(funnel_id, s["role"], s["type"])
    for s in plan["steps"]:
        sid = ids[s["page_id"]]
        for p in s["prices"]:
            driver.attach_price(sid, p["product_id"], p["price_id"])
        if s["type"] == "order_form":
            driver.place_element(sid, "order_form", s["prices"][0]["price_id"], None)
        if s["bump"]:
            driver.place_element(sid, "order_bump", s["bump"]["price_id"], False)
        if s["accept_to"]:
            driver.set_action(sid, "accept", ids[s["accept_to"]])
        if s["decline_to"]:
            driver.set_action(sid, "decline", ids[s["decline_to"]])
    mismatches = verify_funnel_readback(plan, driver.read_back(funnel_id), ids)
    return {"step_ids": ids, "manual_gates": gates, "mismatches": mismatches,
            "ready": not gates and not mismatches}
