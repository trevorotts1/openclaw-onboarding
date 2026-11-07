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
  * DO     - :func:`install_funnel` drives a caller-supplied ``driver``. The one
             concrete EDITOR driver is :class:`ManagedUiFunnelDriver` below: it
             reuses this module's plan, creates steps and reads back through the
             live-captured REST routes, and drives element insertion,
             product/price binding and the configured purchase action through the
             managed GHL editor adapter in ``order_components``. Driver contract:
               payment_provider_status(location_id) -> {"connected": bool, "provider": str}
               create_step(funnel_id, name, step_type[, step_id]) -> step_id
               attach_price(step_id, product_id, price_id[, billing][, approved]) -> None
                     ``billing`` is the native term the price must be read back with;
                     ``approved`` is the approved offer record's own identity
                     ({offer_id, billing_type, amount_minor, currency}) and a driver that
                     accepts it must refuse a native price that differs from it.
               place_element(step_id, kind, price_id, default_checked) -> None
               set_action(step_id, action, target_step_id)       -> None
               read_back(funnel_id) -> {"steps": [{"step_id", "type", "price_ids": [...],
                    "elements": [{"kind", "price_id", "default_checked"}],
                    "accept_target", "decline_target"[, "price_billing", "bump_billing"]]}
             OPTIONAL resume hooks a driver may implement:
               resolve_step(funnel_id, role, step_type) -> existing step id | ""
               inspect_step(funnel_id, step_id)         -> True | False | None
               note_step(step_id, step_type)            -> None
             ``True``/``False`` are PROOFS; ``None`` means "cannot tell" and never
             permits a retry.

RESUME (durable, in existing run state)
  ``install_funnel(..., state=ghl_run_state.RunState, launch_id=...)`` persists
  each confirmed launch/location/funnel/logical-slot/native-id mapping under
  ``carry`` BEFORE and AFTER every create. A resume adopts a confirmed mapping,
  else reconciles against the native side (``resolve_step``), else mints and
  persists the intended step id BEFORE creating. An uncertain create is
  inspected by that exact id: exists -> adopt, provably absent -> retry the SAME
  id once, unknown -> raise ``StepCreateUncertain``. Nothing is ever recreated
  just because the process died.

CHECKOUT INSTANCES
  ``build_funnel_plan(..., checkout_instances=instances)`` consumes the EXISTING
  per-offer checkout plan (83 launcher_core/checkout_instances: one native order
  form per main price choice, realising ``multiple_options`` and
  ``folded_levels``). Each instance becomes its own checkout step. No
  checkout-mode enum is introduced here and the instance record is not altered.

FAIL CLOSED
  * product_id / price_id come ONLY from the caller's ``catalog`` (offer_id ->
    {product_id, price_id[, amount_minor][, currency][, billing]}), or from an
    existing checkout instance's own resolved request; never invented. A missing
    entry, or an amount/currency that disagrees with the approved offer, refuses
    the plan.
  * The APPROVED OFFER RECORD's billing term travels with every price it
    produced (``approved_billing``): its own vocabulary is the Skill 49 launch
    schema's price entry (one_time | recurring | installment | trial), which is
    not the native one. ``order_components.billing_terms_for_offer`` translates
    it once. Where the native surface / the approved record cannot express the
    term, the price carries ``unresolved`` naming the exact unsupported term and
    that slot is NEVER bound — a recurring, trial or installment offer is never
    flattened into one_time, and the request stays unresolved.
  * A missing payment-provider connection is the named operator manual gate
    ``MANUAL-GATE:payment_provider_connection`` and blocks ``ready``.
  * Any write without a verified ``publish`` / ``automation_write`` approval record
    is refused. There is no default verifier: the caller must pass the Command Center
    verifier (a service the AI session cannot write).

CONCRETE DRIVERS
  :class:`ManagedUiFunnelDriver` is the production editor driver described above.
  :class:`RestCanvasFunnelDriver` remains the raw REST driver: it implements the
  contract over the live-captured REST routes in ghl_rest_canvas (create-step,
  funnel fetch, page read), through a caller-bound ``run_eval(js)``. Every
  commerce surface that SELECTORS-LIVE-funnel.md does not capture (native
  step-type strings, price attach, order-form/bump elements, accept/decline
  actions, read-back field paths, payment-provider status) comes ONLY from a
  ``capture`` dict loaded by :func:`load_commerce_capture`; without it the driver
  refuses before any write (:class:`CommerceCaptureRequired`, ``CAPTURE-GATE:CHK-19``).
  That refusal is deliberate and stays enabled: an uncaptured REST commerce write
  is never attempted.

NOT DONE HERE (ceiling): navigation edges that are not commerce outcomes
(interest_submitted, selection_validated) are the page buttons of non-purchase pages
and are not set; the live commerce capture and the live read-back wait for an
approved test location (DECISIONS CHK-19). ``install_funnel`` returns the read-back
as ``out["readback"]`` - the object the S06-02 live proof inspects.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Callable, Dict, List, Mapping, Optional

import ghl_rest_canvas as _rc
import order_components as _oc

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

# Approved billing vocabulary (structural twin of order_components /
# 79-signature-order-form order_bumps). Carried verbatim into the native
# binding; an installment term has no native shape and is NEVER flattened.
BILLING_TYPES = ("one_time", "recurring", "trial_then_recurring")
RECURRING_INTERVALS = ("day", "week", "month", "year")
UNSUPPORTED_BILLING_TERMS = ("installment", "installments")
BILLING_NOT_NATIVE = (
    "installment billing has no native CreatePriceDto shape on this surface; "
    "refusing to flatten an installment offer into one_time")

# Resume: the durable record for one logical slot. Written BEFORE the create
# so a timeout can inspect the minted id instead of creating a duplicate.
RESUME_NAMESPACE = "funnel_steps"


class FunnelPlanError(ValueError):
    """The plan cannot be built without inventing data."""


class ApprovalRefused(PermissionError):
    """A write was attempted without a verified approval record."""


class CommerceCaptureRequired(RuntimeError):
    """The live commerce capture is missing/invalid/synthetic: no write may happen."""


def _billing_terms(raw: Any, where: str) -> Optional[Dict[str, Any]]:
    """Validate approved billing terms and carry them verbatim.

    ``None`` means the caller supplied no term at all (absent stays absent — it
    is never defaulted to ``one_time``). An installment term is refused with the
    real reason; a term missing its required interval/trial is refused rather
    than guessed.
    """
    if not isinstance(raw, Mapping):
        return None
    billing_type = str(raw.get("billing_type") or "").strip()
    if not billing_type:
        if any(k in raw for k in ("recurring_interval", "trial_days",
                                  "installment_count", "installment_interval")):
            raise FunnelPlanError(
                f"{where}: billing terms carry no billing_type - refusing to "
                "assume one_time")
        return None
    if billing_type in UNSUPPORTED_BILLING_TERMS:
        raise FunnelPlanError(f"{where}: {BILLING_NOT_NATIVE}")
    if billing_type not in BILLING_TYPES:
        raise FunnelPlanError(
            f"{where}: billing_type {billing_type!r} is not one of {BILLING_TYPES}")
    interval = raw.get("recurring_interval")
    interval = str(interval).strip() if interval is not None else None
    trial = raw.get("trial_days")
    if trial is not None and (not isinstance(trial, int) or isinstance(trial, bool)):
        raise FunnelPlanError(f"{where}: trial_days must be an integer")
    if billing_type == "one_time":
        if interval or trial is not None:
            raise FunnelPlanError(
                f"{where}: one_time price must not carry recurrence or trial terms")
        return {"billing_type": billing_type}
    if interval not in RECURRING_INTERVALS:
        raise FunnelPlanError(
            f"{where}: {billing_type} requires recurring_interval in "
            f"{RECURRING_INTERVALS}; a missing interval stays missing")
    if billing_type == "recurring" and trial is not None:
        raise FunnelPlanError(f"{where}: recurring price must not carry trial_days")
    if billing_type == "trial_then_recurring" and (
            not isinstance(trial, int) or trial < 1):
        raise FunnelPlanError(
            f"{where}: trial_then_recurring requires trial_days >= 1")
    out = {"billing_type": billing_type, "recurring_interval": interval}
    if billing_type == "trial_then_recurring":
        out["trial_days"] = trial
    return out


def _approved_terms(offer: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    """The approved billing term an offer record carries, in its own vocabulary.

    Two record shapes reach this plan: the plan's documented ``billing`` block and
    the Launcher's approved ``checkout`` block (an intake offer, which the intake
    only ever fills with ``one_time``). No third source, and an absent term stays
    absent — it is never defaulted to ``one_time``.
    """
    for key in ("billing", "checkout"):
        block = offer.get(key)
        if isinstance(block, Mapping) and block.get("billing_type") is not None:
            return block
    return None


def _carry_billing(out: Dict[str, Any], approved: Optional[Mapping[str, Any]] = None,
                   native: Optional[Mapping[str, Any]] = None,
                   where: str = "") -> Dict[str, Any]:
    """Put the approved term and its native shape on one plan price.

    ``native`` is a caller-supplied native term (a catalog entry). It may never
    contradict the approved record: a catalog that says one_time for a recurring
    offer would charge the buyer once for a subscription. ``billing`` carries the
    native shape only when it needs specifics beyond one_time (that is what the
    installer demands be read back); ``approved_billing`` always carries the
    approved record's own term, so the binding call can refuse a native price that
    is not the approved one. A term the native surface cannot express becomes
    ``unresolved`` — the slot is never bound and never flattened.
    """
    if native is not None and approved is None:
        out["billing"] = dict(native)
        return out
    if approved is None:
        return out
    terms = _oc.billing_terms_for_offer(approved)
    if not terms:
        if native is not None:
            out["billing"] = dict(native)
        return out
    if terms.get("unresolved"):
        # Not expressible natively: record the exact term and carry NO native
        # term, so the slot cannot look bindable.
        out["unresolved"] = dict(terms["unresolved"])
        return out
    billing = terms["billing"]
    out["approved_billing"] = dict(billing)
    if native is not None:
        got = _oc.NATIVE_TO_APPROVED.get(str(native.get("billing_type") or ""))
        if got != billing["billing_type"]:
            raise FunnelPlanError(
                f"{where}: the supplied native terms ({got!r}) disagree with the approved "
                f"billing term ({billing['billing_type']!r}); refusing to bind a term the "
                "offer does not carry")
    elif billing["billing_type"] != "one_time":
        out["billing"] = dict(billing)   # recurrence must be read back, never assumed
    return out


def _price(offer: Dict[str, Any], catalog: Dict[str, Any]) -> Dict[str, Any]:
    entry = catalog.get(offer["offer_id"])
    if not isinstance(entry, dict) or not entry.get("product_id") or not entry.get("price_id"):
        raise FunnelPlanError(f"no product_id/price_id for offer {offer['offer_id']!r}")
    approved_price = offer.get("price") or {}
    want = approved_price.get("amount_minor")
    if "amount_minor" in entry and want is not None and entry["amount_minor"] != want:
        raise FunnelPlanError(f"catalog amount for {offer['offer_id']!r} disagrees with the offer")
    currency = approved_price.get("currency")
    if entry.get("currency") is not None and currency is not None and entry["currency"] != currency:
        raise FunnelPlanError(
            f"catalog currency for {offer['offer_id']!r} disagrees with the offer")
    out = {"offer_id": offer["offer_id"], "product_id": entry["product_id"],
           "price_id": entry["price_id"], "amount_minor": want, "currency": currency}
    native = (_billing_terms(entry["billing"], where=f"offer {offer['offer_id']!r}")
              if isinstance(entry.get("billing"), Mapping) else None)
    return _carry_billing(out, _approved_terms(offer), native,
                          where=f"offer {offer['offer_id']!r}")


def _instance_price(instance: Mapping[str, Any]) -> Dict[str, Any]:
    """One per-offer checkout instance -> the SAME price shape the plan uses.

    Native ids come only from the instance's own request; a missing id stays
    missing and refuses the plan instead of being minted here.
    """
    slot = instance.get("slot") or instance.get("role_instance") or "checkout"
    request = instance.get("request") if isinstance(instance.get("request"), Mapping) else {}
    main = request.get("main_price") if isinstance(request.get("main_price"), Mapping) else {}
    product_id = str(main.get("native_product_id") or "").strip()
    price_id = str(main.get("native_price_id") or "").strip()
    if not product_id or not price_id:
        raise FunnelPlanError(
            f"checkout instance {slot!r} carries no resolved native product/price")
    out = {"offer_id": str(instance.get("main_offer_id") or ""),
           "price_choice_id": str(instance.get("price_choice_id") or ""),
           "product_id": product_id, "price_id": price_id,
           "amount_minor": main.get("amount_minor"), "currency": main.get("currency")}
    # ``main`` is the approved offer record's own price block (price/currency/
    # approved billing term), so its term is the approved term — never a guess.
    return _carry_billing(out, main, where=f"checkout instance {slot!r}")


def _instance_bump(instance: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    request = instance.get("request") if isinstance(instance.get("request"), Mapping) else {}
    bump = request.get("bump") if isinstance(request.get("bump"), Mapping) else None
    if not bump:
        return None
    price = bump.get("price") if isinstance(bump.get("price"), Mapping) else {}
    product_id = str(price.get("native_product_id") or "").strip()
    price_id = str(price.get("native_price_id") or "").strip()
    if not product_id or not price_id:
        raise FunnelPlanError(
            f"checkout instance {instance.get('slot')!r} declares a bump with no "
            "resolved native product/price")
    out = {"offer_id": str(bump.get("offer_id") or ""),
           "product_id": product_id, "price_id": price_id,
           "amount_minor": price.get("amount_minor"), "currency": price.get("currency")}
    return _carry_billing(out, price, where=f"checkout bump {out['offer_id']!r}")


def _checkout_instance_steps(node: Dict[str, Any], graph: Dict[str, Any],
                             instances: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """One checkout STEP per existing per-offer instance.

    The instance record already REALISED ``multiple_options``/``folded_levels``
    as one native order form per (main offer, price choice). This consumes that
    plan as-is: it adds no checkout-mode enum and creates no mode branch.
    """
    nxt = [e["to"] for e in (graph.get("edges") or [])
           if e["from"] == node["page_id"] and e["event"] == "payment_succeeded"]
    accept_to = nxt[0] if nxt else None
    out: List[Dict[str, Any]] = []
    seen = set()
    for instance in instances:
        page_id = str(instance.get("page_id") or instance.get("checkout_target_ref") or "")
        if not page_id:
            raise FunnelPlanError(
                f"checkout instance {instance.get('slot')!r} has no page_id")
        if page_id in seen:
            raise FunnelPlanError(f"two checkout instances share page_id {page_id!r}")
        seen.add(page_id)
        out.append({
            "page_id": page_id,
            "role": "checkout",
            "slot": str(instance.get("slot") or instance.get("role_instance") or "checkout"),
            "type": STEP_TYPES["checkout"],
            "prices": [_instance_price(instance)],
            "bump": _instance_bump(instance),
            "accept_to": accept_to,
            "decline_to": None,
        })
    if not out:
        raise FunnelPlanError("checkout instances were supplied but none is usable")
    return out


def build_funnel_plan(graph: Dict[str, Any], offers: List[Dict[str, Any]],
                      catalog: Dict[str, Any], *,
                      checkout_instances: Optional[List[Mapping[str, Any]]] = None
                      ) -> Dict[str, Any]:
    """Route graph + offers + caller catalog -> explicit step plan (pure).

    ``checkout_instances`` is the EXISTING per-offer checkout plan
    (83 launcher_core/checkout_instances.build()["instances"]): when supplied,
    each instance becomes its own checkout step and the ``checkout`` node's
    single-offer branch is replaced. No checkout-mode enum is introduced here.
    """
    nodes, edges = graph.get("nodes") or [], graph.get("edges") or []
    by_role: Dict[str, List[Dict[str, Any]]] = {}
    for o in offers:
        by_role.setdefault(o["role"], []).append(o)
    steps = []
    for n in nodes:
        role = n["role"]
        if role not in STEP_TYPES:
            raise FunnelPlanError(f"unknown route role {role!r}")
        if role == "checkout" and checkout_instances:
            steps.extend(_checkout_instance_steps(n, graph, list(checkout_instances)))
            continue
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


_MINT = object()


class VerifiedApproval:
    """Proof that require_approval passed for one plan+location. Minted only by require_approval."""
    __slots__ = ("plan_hash", "location_id")

    def __init__(self, mint: object, plan_hash: str, location_id: str):
        if mint is not _MINT:
            raise ApprovalRefused("VerifiedApproval is minted only by require_approval")
        self.plan_hash, self.location_id = plan_hash, location_id


def require_approval(record: Optional[Dict[str, Any]], plan: Dict[str, Any],
                     location_id: str, verifier: Optional[Callable[[Dict[str, Any]], bool]]) -> VerifiedApproval:
    """Refuse unless a verified publish/automation_write record binds this plan+location."""
    if not isinstance(record, dict) or record.get("scope") not in APPROVAL_SCOPES:
        raise ApprovalRefused("no publish/automation_write approval record")
    if record.get("location_id") != location_id:
        raise ApprovalRefused("approval record is for another location")
    if record.get("plan_hash_prefix") != plan["plan_hash"][:8]:
        raise ApprovalRefused("approval record does not carry this plan's hash prefix")
    if verifier is None or verifier(record) is not True:
        raise ApprovalRefused("approval record not verified by the approval service")
    return VerifiedApproval(_MINT, plan["plan_hash"], location_id)


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
        if any(p.get("billing") for p in s["prices"]):
            observed = r.get("price_billing")
            if not isinstance(observed, list) or len(observed) != len(s["prices"]):
                bad.append(f"{s['role']}: billing terms were not read back")
            else:
                for i, price in enumerate(s["prices"]):
                    if price.get("billing") and observed[i] != price["billing"]:
                        bad.append(
                            f"{s['role']}: price {i} billing {observed[i]!r} != "
                            f"{price['billing']!r}")
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
            if s["bump"].get("billing") and r.get("bump_billing") != s["bump"]["billing"]:
                bad.append(f"{s['role']}: bump billing terms were not read back")
        for key, field in (("accept_to", "accept_target"), ("decline_to", "decline_target")):
            want = step_ids.get(s[key]) if s[key] else None
            if s[key] and r.get(field) != want:
                bad.append(f"{s['role']}: {field} {r.get(field)!r} != route edge {want!r}")
    return bad


class StepCreateUncertain(RuntimeError):
    """A create-step call had no authoritative outcome AND the native object
    could not be inspected. Nothing is retried from that state."""


def _is_uncertain(exc: BaseException) -> bool:
    return (isinstance(exc, (TimeoutError, StepCreateUncertain))
            or getattr(exc, "uncertain", False) is True)


def _resume_key(location_id: str, funnel_id: str, launch_id: str, slot: str) -> str:
    """The durable key for one logical slot: launch + location + funnel + slot."""
    return ":".join((RESUME_NAMESPACE, location_id, launch_id or "-", funnel_id, slot))


def _resume_get(state: Any, key: str) -> Dict[str, Any]:
    if state is None:
        return {}
    rec = state.carry_get(key)
    return dict(rec) if isinstance(rec, Mapping) else {}


def _resume_put(state: Any, key: str, record: Dict[str, Any]) -> None:
    if state is not None:
        state.carry_set(key, record)


def _resolve_step(driver: Any, funnel_id: str, name: str, step_type: str) -> str:
    """Ask the driver for an EXISTING native step by logical identity. A blank
    answer means "not resolved", never "does not exist"."""
    probe = getattr(driver, "resolve_step", None)
    if not callable(probe):
        return ""
    return str(probe(funnel_id, name, step_type) or "")


def _inspect_step(driver: Any, funnel_id: str, step_id: str) -> Optional[bool]:
    """True/False when the driver can prove existence/absence; None when it
    cannot. Only a proven False permits a retry."""
    probe = getattr(driver, "inspect_step", None)
    if not callable(probe):
        return None
    got = probe(funnel_id, step_id)
    if isinstance(got, Mapping):
        if got.get("exists") is True:
            return True
        if got.get("exists") is False:
            return False
        return None
    if got is True or got is False:
        return bool(got)
    return None


def _accepts_kwarg(fn: Any, name: str) -> bool:
    import inspect
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return name in params or any(p.kind == p.VAR_KEYWORD for p in params.values())


def _ensure_step(plan_step: Dict[str, Any], driver: Any, funnel_id: str,
                 location_id: str, launch_id: str, state: Any) -> tuple:
    """Resolve-or-create ONE step, durably.

    1. a CONFIRMED mapping in run state is adopted — no create;
    2. otherwise the driver reconciles against the NATIVE side by logical
       identity (``resolve_step``); adopted and persisted when found;
    3. otherwise the intended step id is persisted BEFORE the create, so a
       timeout can inspect that exact object;
    4. an uncertain create is inspected: exists -> adopt; provably absent ->
       retry the SAME persisted id once; unknown -> raise (never retry blind).
    """
    slot = str(plan_step.get("slot") or plan_step["page_id"])
    key = _resume_key(location_id, funnel_id, launch_id, slot)
    record = _resume_get(state, key)
    if record.get("state") == "confirmed" and record.get("step_id"):
        return str(record["step_id"]), "resumed"

    step_id = str(record.get("step_id") or "")
    if not step_id:
        found = _resolve_step(driver, funnel_id, plan_step["role"], plan_step["type"])
        if found:
            _resume_put(state, key, {"state": "confirmed", "step_id": found,
                                     "role": plan_step["role"],
                                     "page_id": plan_step["page_id"]})
            return found, "reconciled"
        step_id = uuid.uuid4().hex
    _resume_put(state, key, {"state": "creating", "step_id": step_id,
                             "role": plan_step["role"],
                             "page_id": plan_step["page_id"]})

    supports_id = _accepts_kwarg(driver.create_step, "step_id")
    attempts = 0
    while True:
        attempts += 1
        how = "created" if attempts == 1 else "retried"
        try:
            if supports_id:
                sid = driver.create_step(funnel_id, plan_step["role"],
                                         plan_step["type"], step_id=step_id)
            else:
                sid = driver.create_step(funnel_id, plan_step["role"],
                                         plan_step["type"])
        except Exception as exc:
            if not _is_uncertain(exc) or attempts >= 2:
                raise
            if not supports_id:
                raise StepCreateUncertain(
                    f"{plan_step['role']}: the create outcome is unknown and this "
                    "driver cannot inspect a previously minted step id; refusing "
                    "to retry blind") from exc
            exists = _inspect_step(driver, funnel_id, step_id)
            if exists is None:
                raise StepCreateUncertain(
                    f"{plan_step['role']}: the create outcome is unknown and the "
                    "native object could not be inspected; refusing to retry "
                    f"({type(exc).__name__})") from exc
            if exists:
                sid = step_id
                how = "reconciled"  # adopted the native object, never re-created
            else:
                continue  # provably absent -> retry the SAME persisted id
        confirmed = str(sid or step_id)
        _resume_put(state, key, {"state": "confirmed", "step_id": confirmed,
                                 "role": plan_step["role"],
                                 "page_id": plan_step["page_id"]})
        return confirmed, how


def _attach_price(driver: Any, step_id: str, price: Mapping[str, Any]) -> None:
    """Hand ONE approved price to the driver's native product/price binding call.

    ``billing`` (the native recurrence specifics) may never be dropped by a driver
    that cannot carry it: refusing here is what stops a subscription binding as a
    single charge. ``approved`` carries the approved record's own identity
    (offer_id, its billing term, amount, currency); a driver that accepts it must
    check the native price it resolved against it.
    """
    kwargs: Dict[str, Any] = {}
    if _accepts_kwarg(driver.attach_price, "billing"):
        kwargs["billing"] = price.get("billing")
    elif price.get("billing"):
        raise FunnelPlanError(
            f"driver cannot carry billing terms for price {price['price_id']!r}; "
            "refusing to drop them")
    approved = {"offer_id": price.get("offer_id"),
                "billing_type": (price.get("approved_billing") or {}).get("billing_type"),
                "amount_minor": price.get("amount_minor"),
                "currency": price.get("currency")}
    if _accepts_kwarg(driver.attach_price, "approved") \
            and any(value is not None for value in approved.values()):
        kwargs["approved"] = approved
    driver.attach_price(step_id, price["product_id"], price["price_id"], **kwargs)


def _place_element(driver: Any, step_id: str, kind: str, price: Mapping[str, Any],
                   default_checked: Optional[bool]) -> None:
    """Place one native element for a price this plan already validated.

    A bump is its own approved price, so it gets the same approved-term and
    native-recurrence checks the main price got at attach time; a driver that can
    carry neither is not asked to invent one.
    """
    kwargs: Dict[str, Any] = {}
    if kind != "order_form":
        if _accepts_kwarg(driver.place_element, "billing"):
            kwargs["billing"] = price.get("billing")
        elif price.get("billing"):
            raise FunnelPlanError(
                f"driver cannot carry billing terms for price {price['price_id']!r}; "
                "refusing to drop them")
        approved = {"offer_id": price.get("offer_id"),
                    "billing_type": (price.get("approved_billing") or {}).get("billing_type"),
                    "amount_minor": price.get("amount_minor"),
                    "currency": price.get("currency")}
        if _accepts_kwarg(driver.place_element, "approved") \
                and any(value is not None for value in approved.values()):
            kwargs["approved"] = approved
    driver.place_element(step_id, kind, price["price_id"], default_checked, **kwargs)


def install_funnel(plan: Dict[str, Any], driver: Any, funnel_id: str, location_id: str,
                   approval: Optional[Dict[str, Any]],
                   verifier: Optional[Callable[[Dict[str, Any]], bool]], *,
                   state: Optional[Any] = None,
                   launch_id: str = "") -> Dict[str, Any]:
    """Create/attach/place/link then read back. Refuses every write without approval.

    ``state`` is the existing run state (``ghl_run_state.RunState`` surface:
    ``carry_get`` / ``carry_set``). With it, each confirmed launch/location/
    funnel/logical-slot/native-id mapping is persisted before and after the
    create, and a resume resolves prior mappings instead of recreating steps.

    Returns ``bound`` (the offer -> slot binding actually made, with the approved
    amount, currency and billing term carried) and ``unresolved`` (each approved
    term the native surface cannot express, named). An unresolved term keeps its
    request unbound and keeps ``ready`` false; it is never flattened into one_time.
    """
    grant = require_approval(approval, plan, location_id, verifier)  # always, whatever the driver is
    if isinstance(driver, RestCanvasFunnelDriver):
        driver.accept_grant(grant)  # hand over the proof; the verifier is not called twice
    preflight = getattr(driver, "preflight", None)
    if preflight:
        preflight()  # fail closed on a missing capture BEFORE the first write
    gates = [g for g in [payment_gate(driver.payment_provider_status(location_id))] if g]
    ids: Dict[str, str] = {}
    resumed: List[Dict[str, Any]] = []
    for s in plan["steps"]:
        sid, how = _ensure_step(s, driver, funnel_id, location_id, launch_id, state)
        ids[s["page_id"]] = sid
        note = getattr(driver, "note_step", None)
        if callable(note):
            note(sid, s["type"])
        if how != "created":
            resumed.append({"slot": s.get("slot") or s["page_id"],
                            "step_id": sid, "how": how})
    bound: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []
    for s in plan["steps"]:
        sid = ids[s["page_id"]]
        slot = str(s.get("slot") or s["page_id"])
        for p in s["prices"]:
            if p.get("unresolved"):
                # The approved term has no native shape here: the request stays
                # unresolved and is NEVER bound as one_time.
                unresolved.append({"slot": slot, "page_id": s["page_id"], "kind": "price",
                                   **dict(p["unresolved"]),
                                   "offer_id": p.get("offer_id"),
                                   "price_id": p.get("price_id")})
                continue
            _attach_price(driver, sid, p)
            bound.append({"slot": slot, "page_id": s["page_id"], "kind": "price",
                          "offer_id": p.get("offer_id"), "price_id": p.get("price_id"),
                          "amount_minor": p.get("amount_minor"),
                          "currency": p.get("currency"),
                          "approved_billing": dict(p.get("approved_billing") or {})})
        main_unresolved = bool(not s["prices"] or any(p.get("unresolved") for p in s["prices"]))
        if s["type"] == "order_form" and not main_unresolved:
            _place_element(driver, sid, "order_form", s["prices"][0], None)
        if s["bump"]:
            if s["bump"].get("unresolved"):
                unresolved.append({"slot": slot, "page_id": s["page_id"], "kind": "bump",
                                   **dict(s["bump"]["unresolved"]),
                                   "offer_id": s["bump"].get("offer_id"),
                                   "price_id": s["bump"].get("price_id")})
            else:
                _place_element(driver, sid, "order_bump", s["bump"], False)
                bound.append({"slot": slot, "page_id": s["page_id"], "kind": "bump",
                              "offer_id": s["bump"].get("offer_id"),
                              "price_id": s["bump"]["price_id"],
                              "amount_minor": s["bump"].get("amount_minor"),
                              "currency": s["bump"].get("currency"),
                              "approved_billing": dict(s["bump"].get("approved_billing") or {})})
        if s["accept_to"]:
            driver.set_action(sid, "accept", ids[s["accept_to"]])
        if s["decline_to"]:
            driver.set_action(sid, "decline", ids[s["decline_to"]])
    readback = driver.read_back(funnel_id)
    mismatches = verify_funnel_readback(plan, readback, ids)
    return {"step_ids": ids, "manual_gates": gates, "mismatches": mismatches,
            "ready": not gates and not mismatches and not unresolved,
            "readback": readback, "resumed": resumed, "resume_state": state is not None,
            "bound": bound, "unresolved": unresolved}


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
        self._grant: Optional[VerifiedApproval] = None

    def authorize(self, plan: Dict[str, Any], approval: Optional[Dict[str, Any]],
                  verifier: Optional[Callable[[Dict[str, Any]], bool]]) -> None:
        """The only way to unlock the write methods: the same verified approval as install_funnel."""
        self._grant = None
        self.accept_grant(require_approval(approval, plan, self.location_id, verifier))

    def accept_grant(self, grant: Any) -> None:
        """Unlock with a VerifiedApproval minted for this driver's location; anything else re-locks."""
        self._grant = None
        if not isinstance(grant, VerifiedApproval) or grant.location_id != self.location_id:
            raise ApprovalRefused("RestCanvasFunnelDriver: not a verified approval for this location")
        self._grant = grant

    def _require_approved(self, method: str) -> None:
        if self._grant is None:
            raise ApprovalRefused(f"RestCanvasFunnelDriver.{method}: no verified approval (call authorize)")

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
        self._require_approved(key)
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

    def create_step(self, funnel_id: str, name: str, step_type: str,
                    step_id: Optional[str] = None) -> str:
        self._require_approved("create_step")
        self.preflight()
        ev = _rc.step_create(funnel_id, name, name.replace("_", "-"),
                             step_type=self.capture["step_types"][step_type],
                             step_id=step_id)["eval"]
        res = self.run_eval(ev)
        if res.get("status") != 201:
            raise RuntimeError(f"create-step {name} -> HTTP {res.get('status')}")
        return _rc.created_page_id(res.get("body"))

    def inspect_step(self, funnel_id: str, step_id: str) -> Optional[bool]:
        """True/False only when the page read proves it; None when unknowable."""
        res = self.run_eval(_rc.build_fetch_js(
            "GET", _rc.page_read_path(step_id, self.location_id)))
        status = res.get("status")
        if status == 200:
            return True
        if status in (400, 404):
            return False
        return None

    def resolve_step(self, funnel_id: str, name: str, step_type: str) -> str:
        """Logical identity -> native step id, only through a captured read.

        This driver has no captured step-NAME path, so it honestly resolves
        nothing; run state remains the resume authority here.
        """
        return ""

    def _require_billing_route(self, key: str) -> None:
        route_text = json.dumps((self.capture or {}).get(key) or {})
        if "billing" not in route_text:
            raise _refuse([f"{key}_billing"])

    def attach_price(self, step_id: str, product_id: str, price_id: str,
                     billing: Optional[Mapping[str, Any]] = None) -> None:
        vals: Dict[str, Any] = {"step_id": step_id, "product_id": product_id,
                                "price_id": price_id}
        if billing:
            # The captured route must actually be able to carry the approved
            # terms; otherwise they would be silently dropped.
            self._require_billing_route("attach_price")
            vals.update({k: v for k, v in billing.items() if v is not None})
        self._route("attach_price", **vals)

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


def _billing_view(price: Mapping[str, Any]) -> Dict[str, Any]:
    """The billing terms as read back, in the plan's vocabulary (absent stays absent)."""
    out = {"billing_type": price.get("billing_type")}
    if price.get("recurring_interval") is not None:
        out["recurring_interval"] = price["recurring_interval"]
    if price.get("trial_days") is not None:
        out["trial_days"] = price["trial_days"]
    return out


class ManagedUiFunnelDriver(RestCanvasFunnelDriver):
    """The MANAGED EDITOR driver for the native funnel order-form step.

    Creation and read-back ride the same captured REST routes as the REST
    driver (they are live-captured; see SELECTORS-LIVE-funnel.md). Element
    insertion, product/price binding and the configured purchase action ride
    the MANAGED GHL editor adapter from ``order_components`` (a
    ``BrowserManagerDriver`` over a ``ManagedEditorBridge``), reached through
    ``editor_factory(step_id)``. With no editor, no resolved price, or no bump
    copy the operation refuses — it never degrades to an invented element
    write. The inherited CAPTURE-GATE:CHK-19 preflight is unchanged.
    """

    def __init__(self, run_eval: Callable[[str], Dict[str, Any]], location_id: str,
                 capture: Optional[Dict[str, Any]], *,
                 editor_factory: Optional[Callable[[str], Any]] = None,
                 resolver: Optional[Callable[[str], Mapping[str, Any]]] = None,
                 bump_copy: Optional[Mapping[str, Mapping[str, Any]]] = None,
                 component_kinds: Optional[Mapping[str, str]] = None,
                 allow_synthetic: bool = False) -> None:
        super().__init__(run_eval, location_id, capture,
                         allow_synthetic=allow_synthetic)
        self._editor_factory = editor_factory
        self._resolver = resolver
        self._bump_copy = dict(bump_copy or {})
        self._component_kinds = dict(component_kinds or {
            "order_form": "checkout", "upsell": "checkout", "downsell": "checkout"})
        self._step_types: Dict[str, str] = {}

    # -- managed editor seam -------------------------------------------------

    def _executor(self, step_id: str) -> Any:
        if not callable(self._editor_factory):
            raise CommerceCaptureRequired(
                "managed editor adapter is not bound — no element can be placed or bound")
        executor = self._editor_factory(str(step_id))
        if executor is None:
            raise CommerceCaptureRequired(
                f"managed editor adapter is not bound for step {step_id!r}")
        return executor

    def _price_ref(self, price_id: str) -> Any:
        if not callable(self._resolver):
            raise FunnelPlanError(
                "no product/price resolver is bound; native ids are never invented")
        ref = self._resolver(str(price_id))
        if not isinstance(ref, Mapping):
            raise FunnelPlanError(f"resolver returned no price reference for {price_id!r}")
        return _oc.validate_price_ref(ref)

    def _component(self, executor: Any, step_id: str) -> str:
        kind = self._component_kinds.get(self._step_types.get(step_id, "order_form"),
                                         "checkout")
        return executor.find_component(kind)

    # -- driver contract ------------------------------------------------------

    def create_step(self, funnel_id: str, name: str, step_type: str,
                    step_id: Optional[str] = None) -> str:
        created = super().create_step(funnel_id, name, step_type, step_id=step_id)
        self._step_types[created] = step_type
        return created

    def note_step(self, step_id: str, step_type: str) -> None:
        """Let the installer declare a resumed step's type for component lookup."""
        self._step_types[str(step_id)] = str(step_type)

    def attach_price(self, step_id: str, product_id: str, price_id: str,
                     billing: Optional[Mapping[str, Any]] = None,
                     approved: Optional[Mapping[str, Any]] = None) -> None:
        """Bind the resolved native price to the step's checkout element.

        ``approved`` is the APPROVED OFFER RECORD's own identity: its offer id, its
        billing term, its amount and currency. The native price this step resolves
        must be that same price and that same term — a native price for another
        amount, another currency or another billing term is refused here rather
        than bound, because that is a different charge from the one approved.
        """
        self._require_approved("attach_price")
        self.preflight()
        executor = self._executor(step_id)
        ref = self._price_ref(price_id)
        if ref.native_product_id != str(product_id):
            raise FunnelPlanError(
                f"resolved price {price_id!r} belongs to {ref.native_product_id!r}, "
                f"not the planned product {product_id!r}")
        if billing and _billing_view(ref.as_fields()) != _billing_view(billing):
            raise FunnelPlanError(
                f"resolved price terms {_billing_view(ref.as_fields())!r} disagree with "
                f"the approved billing terms {_billing_view(billing)!r}; refusing to "
                "bind either one on assumption")
        if approved:
            self._assert_approved_price(ref, price_id, approved)
        component = self._component(executor, step_id)
        executor.bind_main_price(component, ref)

    @staticmethod
    def _assert_approved_price(ref: Any, price_id: str,
                               approved: Mapping[str, Any]) -> None:
        """The native price must BE the approved one: same amount, currency, term."""
        offer_id = approved.get("offer_id")
        amount = approved.get("amount_minor")
        if amount is not None and ref.amount_minor != amount:
            raise FunnelPlanError(
                f"native price {price_id!r} is {ref.amount_minor} minor units; the approved "
                f"offer {offer_id!r} is {amount}; refusing to bind a different charge")
        currency = approved.get("currency")
        if currency is not None and ref.currency != currency:
            raise FunnelPlanError(
                f"native price {price_id!r} is in {ref.currency!r}; the approved offer "
                f"{offer_id!r} is in {currency!r}; refusing to bind a different charge")
        want = approved.get("billing_type")
        got = _oc.NATIVE_TO_APPROVED.get(ref.billing_type)
        if want is not None and got != want:
            raise FunnelPlanError(
                f"native price {price_id!r} bills {ref.billing_type!r} ({got!r}); the "
                f"approved offer {offer_id!r} bills {want!r}; a billing term is never "
                "flattened or upgraded on assumption")

    def place_element(self, step_id: str, kind: str, price_id: str,
                      default_checked: Optional[bool],
                      billing: Optional[Mapping[str, Any]] = None,
                      approved: Optional[Mapping[str, Any]] = None) -> None:
        self._require_approved(f"place_element:{kind}")
        self.preflight()
        executor = self._executor(step_id)
        component = self._component(executor, step_id)
        if kind == "order_form":
            # The order form IS the checkout component; re-read the binding and
            # refuse drift rather than silently rewriting it.
            observed = executor.read_component(component) or {}
            main = observed.get("main_price") if isinstance(observed, Mapping) else None
            ref = self._price_ref(price_id)
            if not isinstance(main, Mapping) or _oc.validate_price_ref(main) != ref:
                raise RuntimeError(
                    f"order-form element on step {step_id!r} is not bound to "
                    f"price {price_id!r}; the price attach did not land")
            return
        if kind == "order_bump":
            copy = self._bump_copy.get(str(price_id))
            if not isinstance(copy, Mapping) or not copy.get("headline") \
                    or not copy.get("benefit_explanation"):
                raise FunnelPlanError(
                    f"bump {price_id!r} has no approved headline/benefit copy; "
                    "bump copy is never invented")
            ref = self._price_ref(price_id)
            # The bump is its own approved price: same amount/currency/term checks
            # as the main price, or a subscription bump binds as a single charge.
            if billing and _billing_view(ref.as_fields()) != _billing_view(billing):
                raise FunnelPlanError(
                    f"bump price terms {_billing_view(ref.as_fields())!r} disagree with the "
                    f"approved billing terms {_billing_view(billing)!r}; refusing to bind "
                    "either one on assumption")
            if approved:
                self._assert_approved_price(ref, price_id, approved)
            executor.attach_bump(component, _oc.BumpAttach(
                offer_id=str(copy.get("offer_id") or price_id),
                headline=str(copy["headline"]),
                benefit_explanation=str(copy["benefit_explanation"]),
                price=ref,
                disclosure_text=copy.get("disclosure_text")))
            return
        raise FunnelPlanError(
            f"element kind {kind!r} has no managed editor operation; refusing to "
            "approximate it")

    def set_action(self, step_id: str, action: str, target_step_id: str) -> None:
        self._require_approved("set_action")
        self.preflight()
        executor = self._executor(step_id)
        executor.set_action(self._component(executor, step_id), action, target_step_id)

    def read_back(self, funnel_id: str) -> Dict[str, Any]:
        out = super().read_back(funnel_id)
        for step in out.get("steps") or []:
            step_id = str(step.get("step_id") or "")
            self._step_types.setdefault(step_id, step.get("type") or "order_form")
            try:
                executor = self._executor(step_id)
                component = self._component(executor, step_id)
                state = executor.read_component(component) or {}
            except Exception:  # no editor surface here: terms simply not read back
                continue
            main = state.get("main_price") if isinstance(state, Mapping) else None
            if isinstance(main, Mapping):
                step["price_billing"] = [_billing_view(main)]
            bumps = state.get("bumps") if isinstance(state, Mapping) else None
            if isinstance(bumps, list) and bumps and isinstance(bumps[0], Mapping):
                price = bumps[0].get("price")
                if isinstance(price, Mapping):
                    step["bump_billing"] = _billing_view(price)
        return out
