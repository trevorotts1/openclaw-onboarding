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

CONCRETE DRIVER: :class:`RestCanvasFunnelDriver` implements the contract over the
live-captured REST routes in ghl_rest_canvas (create-step, funnel fetch, page read),
through a caller-bound ``run_eval(js)`` (an authenticated agent-browser eval; this
module never launches a browser). Every commerce surface that SELECTORS-LIVE-funnel.md
does not capture (native step-type strings, price attach, order-form/bump elements,
accept/decline actions, read-back field paths, payment-provider status) comes ONLY
from a ``capture`` dict loaded by :func:`load_commerce_capture`; without it the driver
refuses before any write (:class:`CommerceCaptureRequired`, ``CAPTURE-GATE:CHK-19``).

NOT DONE HERE (ceiling): navigation edges that are not commerce outcomes
(interest_submitted, selection_validated) are the page buttons of non-purchase pages
and are not set; the live commerce capture and the live read-back wait for an
approved test location (DECISIONS CHK-19). ``install_funnel`` returns the read-back
as ``out["readback"]`` - the object the S06-02 live proof inspects.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Dict, List, Optional

import ghl_rest_canvas as _rc

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


class CommerceCaptureRequired(RuntimeError):
    """The live commerce capture is missing/invalid/synthetic: no write may happen."""


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
    preflight = getattr(driver, "preflight", None)
    if preflight:
        preflight()  # fail closed on a missing capture BEFORE the first write
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
    readback = driver.read_back(funnel_id)
    mismatches = verify_funnel_readback(plan, readback, ids)
    return {"step_ids": ids, "manual_gates": gates, "mismatches": mismatches,
            "ready": not gates and not mismatches, "readback": readback}


# ---------------------------------------------------------------------------
# Concrete driver (REST canvas) + capture gate
# ---------------------------------------------------------------------------
STEP_TYPE_KEYS = ("landing", "order_form", "upsell", "downsell", "thank_you")
ROUTE_KEYS = ("attach_price", "place_element", "set_action")  # {method, path, body}
READ_BACK_KEYS = ("steps_path", "step_page_id_path", "step_type_path", "price_ids_path",
                  "elements_path", "element_kind", "element_price_id",
                  "element_default_checked", "accept_target_path", "decline_target_path")
COMMERCE_CAPTURE_KEYS = ("step_types",) + ROUTE_KEYS + ("read_back_fields",)


def _ok_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def validate_commerce_capture(capture: Any) -> List[str]:
    """Problems (surface names) with a commerce capture; [] means usable. Pure."""
    if not isinstance(capture, dict):
        return list(COMMERCE_CAPTURE_KEYS)
    bad: List[str] = []
    st = capture.get("step_types")
    if not (isinstance(st, dict) and all(_ok_str(st.get(k)) for k in STEP_TYPE_KEYS)):
        bad.append("step_types")
    for k in ROUTE_KEYS + ("payment_status",):
        r = capture.get(k)
        if r is None and k == "payment_status":
            continue  # optional: absent -> payment gate stays closed
        if not (isinstance(r, dict) and r.get("method") in ("GET", "POST", "PUT")
                and _ok_str(r.get("path")) and r["path"].startswith("/")):
            bad.append(k)
        elif k == "payment_status" and not (_ok_str(r.get("connected_path"))
                                            and _ok_str(r.get("provider_path"))):
            bad.append(k)
    rb = capture.get("read_back_fields")
    if not (isinstance(rb, dict) and all(_ok_str(rb.get(k)) for k in READ_BACK_KEYS)):
        bad.append("read_back_fields")
    return bad


def _refuse(problems: List[str]) -> "CommerceCaptureRequired":
    return CommerceCaptureRequired("; ".join(f"CAPTURE-GATE:CHK-19:{p}" for p in problems))


def load_commerce_capture(path: str) -> Dict[str, Any]:
    """The only production ingress for a commerce capture: refuses synthetic/invalid."""
    try:
        with open(path, encoding="utf-8") as f:
            cap = json.load(f)
    except (OSError, ValueError) as exc:
        raise _refuse([f"capture_file({type(exc).__name__})"])
    if isinstance(cap, dict) and cap.get("synthetic"):
        raise _refuse(["synthetic_fixture"])
    problems = validate_commerce_capture(cap)
    if problems:
        raise _refuse(problems)
    return cap


def _dig(obj: Any, path: str) -> Any:
    """Dotted-path lookup (list indexes are digits); None when any hop is missing."""
    for part in path.split("."):
        if isinstance(obj, list) and part.isdigit() and int(part) < len(obj):
            obj = obj[int(part)]
        elif isinstance(obj, dict) and part in obj:
            obj = obj[part]
        else:
            return None
    return obj


def _fill(tpl: Any, vals: Dict[str, Any]) -> Any:
    """Substitute {name} in a captured route template; a lone "{name}" keeps its type."""
    if isinstance(tpl, dict):
        return {k: _fill(v, vals) for k, v in tpl.items()}
    if isinstance(tpl, list):
        return [_fill(v, vals) for v in tpl]
    if isinstance(tpl, str):
        if tpl.startswith("{") and tpl.endswith("}") and tpl[1:-1] in vals:
            return vals[tpl[1:-1]]
        for k, v in vals.items():
            tpl = tpl.replace("{" + k + "}", str(v))
    return tpl


class RestCanvasFunnelDriver:
    """Funnel driver over the captured REST routes. ``run_eval(js) -> {status, ok, body}``
    is bound by the caller to an authenticated agent-browser session
    (``ghl_rest_canvas.agent_browser_eval_cmd``); no browser is launched here."""

    def __init__(self, run_eval: Callable[[str], Dict[str, Any]], location_id: str,
                 capture: Optional[Dict[str, Any]], allow_synthetic: bool = False):
        self.run_eval, self.location_id = run_eval, location_id
        self.capture, self.allow_synthetic = capture, allow_synthetic

    def preflight(self) -> None:
        problems = validate_commerce_capture(self.capture)
        if isinstance(self.capture, dict) and self.capture.get("synthetic") and not self.allow_synthetic:
            problems.append("synthetic_fixture")
        if problems:
            raise _refuse(problems)

    def _call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None,
              expect: Optional[int] = None) -> Any:
        res = self.run_eval(_rc.build_fetch_js(method, path, body))
        if (res.get("status") != expect) if expect else (not res.get("ok")):
            raise RuntimeError(f"{method} {path.split('?')[0]} -> HTTP {res.get('status')}")
        return res.get("body")

    def _route(self, key: str, **vals: Any) -> None:
        self.preflight()
        r = self.capture[key]
        vals.update(location_id=self.location_id)
        self._call(r["method"], _fill(r["path"], vals), _fill(r.get("body"), vals) if r.get("body") else None)

    def payment_provider_status(self, location_id: str) -> Dict[str, Any]:
        r = (self.capture or {}).get("payment_status") if isinstance(self.capture, dict) else None
        if not r:
            return {"connected": None, "provider": None}  # no captured route -> manual gate
        body = self._call(r["method"], _fill(r["path"], {"location_id": location_id}))
        c = _dig(body, r["connected_path"])
        return {"connected": c if isinstance(c, bool) else None, "provider": _dig(body, r["provider_path"])}

    def create_step(self, funnel_id: str, name: str, step_type: str) -> str:
        self.preflight()
        ev = _rc.step_create(funnel_id, name, name.replace("_", "-"),
                             step_type=self.capture["step_types"][step_type])["eval"]
        res = self.run_eval(ev)
        if res.get("status") != 201:
            raise RuntimeError(f"create-step {name} -> HTTP {res.get('status')}")
        return _rc.created_page_id(res.get("body"))

    def attach_price(self, step_id: str, product_id: str, price_id: str) -> None:
        self._route("attach_price", step_id=step_id, product_id=product_id, price_id=price_id)

    def place_element(self, step_id: str, kind: str, price_id: str, default_checked: Optional[bool]) -> None:
        self._route("place_element", step_id=step_id, kind=kind, price_id=price_id,
                    default_checked=default_checked)

    def set_action(self, step_id: str, action: str, target_step_id: str) -> None:
        self._route("set_action", step_id=step_id, action=action, target_step_id=target_step_id)

    def read_back(self, funnel_id: str) -> Dict[str, Any]:
        self.preflight()
        f, native = self.capture["read_back_fields"], {v: k for k, v in self.capture["step_types"].items()}
        fetched = self._call("GET", _rc.funnel_fetch_path(funnel_id))
        out = []
        for st in _dig(fetched, f["steps_path"]) or []:
            pid = _dig(st, f["step_page_id_path"])
            if not pid:
                continue
            page = self._call("GET", _rc.page_read_path(str(pid), self.location_id))
            els = [{"kind": _dig(e, f["element_kind"]), "price_id": _dig(e, f["element_price_id"]),
                    "default_checked": _dig(e, f["element_default_checked"])}
                   for e in _dig(page, f["elements_path"]) or []]
            ntype = _dig(st, f["step_type_path"])
            out.append({"step_id": str(pid), "type": native.get(ntype, ntype),
                        "price_ids": list(_dig(page, f["price_ids_path"]) or []), "elements": els,
                        "accept_target": _dig(page, f["accept_target_path"]),
                        "decline_target": _dig(page, f["decline_target_path"])})
        return {"steps": out}
