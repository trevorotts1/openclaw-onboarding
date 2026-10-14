#!/usr/bin/env python3
"""width_controller.py -- ITEM 15: swarm FORCING (the width controller).

WHAT THIS MODULE IS
-------------------
The one place a swarm width stops being a stack of independent min() folds
and becomes a DECISION with a name. Before this module every layer of the
engine only ever took minimums of ceilings:

  * dispatcher._routing_stamp folded probe -> mode ceiling -> admission
    (hardware / ramp / account permits) into `measured_capacity`;
  * fanout.resolve_effective_workers min()d that against the unit count and
    the per-phase env override;
  * phases._run_ready_queue took the plan's `available` verbatim -- and
    collapsed an UNBOUNDED (bring-your-own-key) measurement to a hard-coded
    8, because the sentinel is not an int.

Each fold was defensible alone; together they meant the swarm could only
ever SLOW DOWN. Nothing anywhere said "the plan calls for N workers: reach
N, hold N, and if a hard limit stops you, record WHICH limit and AT WHAT
VALUE". A deck on a strong box with an uncapped provider crawled at
fallback widths (8, 3, 12) written for safety, not speed, and no record
could answer "why is it running at 3".

THE FORCING CONTRACT (FIX-PLAN Item 15 + the stream brief)
----------------------------------------------------------
1. A planned width is a TARGET to reach and hold, not a ceiling to
   approach when convenient. fanout.run_units (the pool this controller
   feeds) spawns to the target, replaces a worker invocation that dies
   mid-phase, and records a forcing shortfall instead of quietly degrading.
2. Forcing never exceeds a hard cap:
     capacity_cap           capacity.py's reserve-adjusted account ceiling
                            (ACCOUNT_LIMITS with the reserve rule, as
                            resolve_capacity()/probe() report it in
                            `available`); UNBOUNDED contributes no term.
     hardware_budget        hardware_budget.py's class budget / live
                            memory-pressure verdict for the work class.
     mode_operator_ceiling  model_router.MODE_OPERATOR_CEILING for the
                            run's mode (ultra 400, standard 25, economy
                            100 as coded) -- a hard operator ceiling ABOVE
                            everything; forcing operates beneath it, and a
                            plan that asks above it is refused down to it
                            with the refusal named, never silently.
     provider_limit         a provider-side in-flight limit (the pacing
                            governor's max_inflight, or admission's
                            rate/token budget term).
   When one of these binds below the planned width the decision is a
   SHORTFALL and names the limiter + its value. Softer terms (the plan's
   own declaration, the ready-work count, an operator env override, the
   admission warmup ramp) also bound the target and are named when they
   bind, but they are not shortfalls: the plan asked for less, the work
   was not there, the operator throttled it by hand, or admission backed
   off on a live signal (Item 15: forcing "backs off on the same signals
   admission uses today" -- the ramp is preserved, never overridden).
3. The decision is a RECORD, not just a number: planned vs target, every
   cap term's value, and the binding constraint ride into the run record
   (the routing stamp / wave input on the dispatcher side,
   state["ready_queue"]["swarm"] on the Engine side) and the event stream
   (dispatcher sidecar rows / Engine report events), so "why is it running
   at 3" always has a named answer.

This module decides and records. It never dispatches, never probes the
network (capacity.resolve_capacity is the pure scheduling-path read), and
never raises on its decision paths: a controller fault must degrade to the
caller's pre-Item-15 behaviour, labelled, never to a crashed run.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# The limiter taxonomy. These strings are the vocabulary of every swarm
# record this build writes; a shortfall event names its limiter with one of
# the HARD names below, verbatim.
# ---------------------------------------------------------------------------
LIMITER_CAPACITY_CAP = "capacity_cap"
LIMITER_HARDWARE_BUDGET = "hardware_budget"
LIMITER_MODE_CEILING = "mode_operator_ceiling"
LIMITER_PROVIDER_LIMIT = "provider_limit"
LIMITER_COST_ALLOCATION = "cost_allocation"
LIMITER_DECLARED = "declared_width"
LIMITER_READY_WORK = "ready_work"
LIMITER_ENV_OVERRIDE = "env_override"
LIMITER_ADMISSION_RAMP = "admission_ramp"
LIMITER_WORKER_LOSS = "worker_loss"
#: The stamp's width bound the swarm but NO hard term can be attributed
#: from the record (the router-absent rollback's DEFAULT_MAX_WORKERS, for
#: example): the width is a fallback, not a measurement, and the record
#: must say so rather than dressing it up as a capacity verdict. A soft
#: binding -- recorded, never a shortfall.
LIMITER_UNMEASURED_FALLBACK = "unmeasured_fallback"

#: Limiters whose binding below the planned width is a FORCING SHORTFALL:
#: a hard cap stopped the swarm from reaching the width the plan called
#: for, and the event must name it. (cost_allocation is the client's own
#: declared allocation -- a hard number admission already enforces, so a
#: width it cuts is a shortfall with a named cause, not a silent fold.)
HARD_LIMITERS = (
    LIMITER_CAPACITY_CAP,
    LIMITER_HARDWARE_BUDGET,
    LIMITER_MODE_CEILING,
    LIMITER_PROVIDER_LIMIT,
    LIMITER_COST_ALLOCATION,
)

#: Tie-break order when several terms equal the target: the hardest, most
#: external constraint wins the name (an operator ceiling outranks an
#: account cap, which outranks the local box, and so on down to the plan's
#: own declaration, which is not a constraint on the plan at all).
_BINDING_PRIORITY = (
    LIMITER_MODE_CEILING,
    LIMITER_CAPACITY_CAP,
    LIMITER_HARDWARE_BUDGET,
    LIMITER_PROVIDER_LIMIT,
    LIMITER_COST_ALLOCATION,
    LIMITER_ENV_OVERRIDE,
    LIMITER_READY_WORK,
    LIMITER_DECLARED,
)


def _is_unbounded(value: Any) -> bool:
    """capacity.is_unbounded without a hard import: the sentinel's class
    name is the check every duck-typed consumer in this package already
    relies on (int() raises on it by design, so isinstance games are out)."""
    return value is not None and type(value).__name__ == "_Unbounded"


def _pos_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 1 else None
    return None


def mode_operator_ceiling(mode: Optional[str]) -> Optional[int]:
    """MODE_OPERATOR_CEILING[mode] from model_router -- the ONE table.

    Lazy import (this module is imported by fanout-adjacent paths that must
    never grow a cycle). Returns None when the router cannot be read; the
    caller then has no mode term, which decide_width records honestly
    rather than inventing a ceiling."""
    try:
        try:
            from . import model_router as _mr
        except ImportError:  # direct file run from presentation_job/
            import model_router as _mr  # type: ignore[no-redef]
        m = _mr.normalize_mode(str(mode or _mr.DEFAULT_MODE))
        val = _mr.MODE_OPERATOR_CEILING.get(m)
        return int(val) if isinstance(val, int) and val >= 1 else None
    except Exception:  # noqa: BLE001 -- a ceiling that cannot be read is absent
        return None


def active_mode() -> str:
    """The run's mode through model_router's one resolution order
    (explicit > PRESENTATION_MODE env > standard), non-strict: an unknown
    env value answers the default rather than crashing a width decision."""
    try:
        try:
            from . import model_router as _mr
        except ImportError:
            import model_router as _mr  # type: ignore[no-redef]
        return _mr.active_mode(strict=False)
    except Exception:  # noqa: BLE001
        return "standard"


def decide_width(planned_width: Any, *,
                 mode: Optional[str] = None,
                 mode_ceiling: Optional[int] = None,
                 capacity_available: Any = None,
                 hardware_budget: Any = None,
                 provider_limit: Any = None,
                 ready_work: Any = None,
                 env_override: Any = None,
                 provider: Optional[str] = None,
                 work_class: Optional[str] = None,
                 phase_id: Optional[str] = None) -> Dict[str, Any]:
    """THE width decision: how wide may this swarm run, and what decided.

    planned_width   the width the plan calls for (a manifest declaration,
                    a phase's declared workers, or -- for an undeclared
                    phase -- the mode ceiling itself, which is Item 15's
                    formula headroom: as wide as the hard caps allow).
    capacity_available  capacity.py's reserve-adjusted `available` for the
                    routed provider: a positive int, the UNBOUNDED sentinel
                    (no term -- the account has no structural ceiling), or
                    None (unmeasured -- no term; the dispatcher's refusal
                    machinery owns that case upstream and has already
                    substituted its labelled floor into the stamp).
    hardware_budget hardware_budget.py's budget for the phase's work class
                    (an int) or None when unmeasured (an absence is never
                    evidence for a lower width -- hardware_budget's own
                    doctrine).
    provider_limit  a provider-side in-flight limit (governor
                    max_inflight) or None.
    ready_work      units actually ready; bounds the target but is never
                    a shortfall (less work than plan is not degradation).
    env_override    the operator's per-phase PRESENTATION_PHASE_WORKERS_*
                    value, when set: an explicit hand throttle, recorded,
                    never a shortfall.

    Returns the decision dict:
        {phase_id, planned_width, target_width, binding_constraint,
         binding_value, shortfall, mode, provider, work_class,
         caps: {declared_width, mode_operator_ceiling, capacity_cap,
                hardware_budget, provider_limit, ready_work, env_override}}
    where caps values are ints, the string "UNBOUNDED", or None (term
    absent). Never raises.
    """
    try:
        planned = int(planned_width)
    except (TypeError, ValueError):
        planned = 1
    planned = max(1, planned)

    resolved_mode = str(mode or "standard")
    ceiling = _pos_int(mode_ceiling)
    if ceiling is None:
        ceiling = mode_operator_ceiling(resolved_mode)

    caps: Dict[str, Any] = {
        LIMITER_DECLARED: planned,
        LIMITER_MODE_CEILING: ceiling,
        LIMITER_CAPACITY_CAP: None,
        LIMITER_HARDWARE_BUDGET: _pos_int(hardware_budget),
        LIMITER_PROVIDER_LIMIT: _pos_int(provider_limit),
        LIMITER_READY_WORK: None,
        LIMITER_ENV_OVERRIDE: _pos_int(env_override),
    }
    if _is_unbounded(capacity_available):
        caps[LIMITER_CAPACITY_CAP] = "UNBOUNDED"
    else:
        caps[LIMITER_CAPACITY_CAP] = _pos_int(capacity_available)
    ready = ready_work if isinstance(ready_work, int) \
        and not isinstance(ready_work, bool) else None
    if ready is not None:
        caps[LIMITER_READY_WORK] = max(0, ready)

    terms: List[Tuple[str, int]] = [(LIMITER_DECLARED, planned)]
    for name in (LIMITER_MODE_CEILING, LIMITER_CAPACITY_CAP,
                 LIMITER_HARDWARE_BUDGET, LIMITER_PROVIDER_LIMIT,
                 LIMITER_ENV_OVERRIDE):
        val = caps.get(name)
        if isinstance(val, int):
            terms.append((name, val))
    if ready is not None:
        terms.append((LIMITER_READY_WORK, ready))

    target = min(v for _n, v in terms)
    if ready == 0:
        target = 0
    elif target < 1:
        target = 1
    binding: Optional[str] = None
    for name in _BINDING_PRIORITY:
        if caps.get(name) == target or \
                (name == LIMITER_DECLARED and planned == target):
            binding = name
            break
    if binding is None:  # pragma: no cover - terms guarantee a match
        binding = LIMITER_DECLARED
    shortfall = bool(target < planned and binding in HARD_LIMITERS)
    return {
        "phase_id": phase_id,
        "planned_width": planned,
        "target_width": int(target),
        "binding_constraint": binding,
        "binding_value": int(target) if binding != LIMITER_DECLARED
        else planned,
        "shortfall": shortfall,
        "mode": resolved_mode,
        "provider": provider,
        "work_class": work_class,
        "caps": caps,
    }


# ---------------------------------------------------------------------------
# Admission term-name mapping. admission.effective_width already names its
# binding term; the swarm taxonomy renames the SAME facts so a reader sees
# one vocabulary across the stamp, the fanout record and the ready queue.
# An unmapped term keeps admission's own name verbatim -- the actual
# limiter, never a paraphrase.
# ---------------------------------------------------------------------------
_ADMISSION_TERM_MAP = (
    ("class_hardware_budget", LIMITER_HARDWARE_BUDGET),
    ("account_free_permits", LIMITER_CAPACITY_CAP),
    ("rate_or_token_budget", LIMITER_PROVIDER_LIMIT),
    ("cost_allocation", LIMITER_COST_ALLOCATION),
    ("mode_ceiling_minus_active", LIMITER_MODE_CEILING),
    ("ready_work", LIMITER_READY_WORK),
    ("requested", LIMITER_DECLARED),
)


def map_admission_term(term: Any) -> Optional[str]:
    if not isinstance(term, str):
        return None
    for prefix, mapped in _ADMISSION_TERM_MAP:
        if term == prefix or term.startswith(prefix):
            return mapped
    return term


def decision_from_stamp(stamp: Dict[str, Any], *,
                        planned_width: Optional[int] = None,
                        ready_work: Optional[int] = None,
                        env_override: Optional[int] = None,
                        phase_id: Optional[str] = None) -> Dict[str, Any]:
    """Build the width decision for a fan-out phase from its routing stamp.

    The stamp (dispatcher._routing_stamp) has ALREADY folded the probe, the
    mode ceiling and the PRES-015 admission fold (hardware budget, account
    permits, rate budget, cost allocation, warmup ramp) into
    `measured_capacity`. This function does NOT re-decide that number --
    re-folding would double-apply the ramp and could only disagree with the
    one width authority. It decides the FORCING question the stamp never
    asked: given the plan's planned width, does the stamp's width reach it,
    and when it does not, WHICH hard limiter (named from the stamp's own
    recorded terms) is the reason?

    planned_width   the phase's declared plan width (manifest `workers`
                    when the phase declares one). None -- an undeclared
                    phase -- plans at the mode ceiling: Item 15's formula
                    headroom, bounded by the hard caps and the ready work.
    """
    stamp = stamp or {}
    mode = str(stamp.get("mode") or "standard")
    measured = _pos_int(stamp.get("measured_capacity"))

    ceiling = None
    mode_cap = stamp.get("mode_cap")
    if isinstance(mode_cap, dict):
        ceiling = _pos_int(mode_cap.get("ceiling"))
    if ceiling is None:
        ceiling = mode_operator_ceiling(mode)

    if planned_width is None:
        planned = ceiling if ceiling is not None else (measured or 1)
    else:
        planned = max(1, int(planned_width))

    # --- the stamp's own cap terms, renamed into the swarm taxonomy -----
    capacity_cap: Any = None
    hardware: Optional[int] = None
    provider_limit: Optional[int] = None
    extra_terms: List[Tuple[str, int]] = []
    refusal = stamp.get("capacity_refusal")
    raw_available = stamp.get("capacity_raw_available")
    if isinstance(refusal, dict):
        # The probe could not attribute a measurement to this route and the
        # stamp refused loudly, proceeding at the conservative floor. The
        # capacity axis IS the binding constraint, at the floor's value.
        capacity_cap = _pos_int(refusal.get("width_applied"))
    elif _is_unbounded(raw_available) or \
            str(stamp.get("capacity_status") or "").startswith("unbounded"):
        capacity_cap = "UNBOUNDED"
    elif _pos_int(raw_available) is not None:
        capacity_cap = _pos_int(raw_available)

    admission = stamp.get("admission")
    admission_binding_raw: Optional[str] = None
    if isinstance(admission, dict):
        admission_binding_raw = admission.get("binding")
        for term in admission.get("terms") or []:
            if not isinstance(term, dict):
                continue
            mapped = map_admission_term(term.get("term"))
            val = _pos_int(term.get("value"))
            if mapped is None or val is None:
                continue
            if mapped == LIMITER_HARDWARE_BUDGET:
                hardware = val if hardware is None else min(hardware, val)
            elif mapped == LIMITER_PROVIDER_LIMIT:
                provider_limit = val if provider_limit is None \
                    else min(provider_limit, val)
            elif mapped == LIMITER_COST_ALLOCATION:
                extra_terms.append((LIMITER_COST_ALLOCATION, val))
            elif mapped == LIMITER_CAPACITY_CAP:
                if isinstance(capacity_cap, int):
                    capacity_cap = min(capacity_cap, val)
                elif capacity_cap is None:
                    capacity_cap = val
            # mode_ceiling_minus_active is the mode ceiling term already
            # carried by `ceiling`; the active count is dynamic and the
            # stamp's folded width below already reflects it.

    decision = decide_width(
        planned, mode=mode, mode_ceiling=ceiling,
        capacity_available=capacity_cap, hardware_budget=hardware,
        provider_limit=provider_limit, ready_work=ready_work,
        env_override=env_override, provider=stamp.get("provider"),
        work_class=(admission.get("work_class")
                    if isinstance(admission, dict) else None),
        phase_id=phase_id)
    caps = decision["caps"]
    for name, val in extra_terms:
        caps[name] = val
    caps["stamp_measured_capacity"] = measured
    if admission_binding_raw:
        caps["stamp_admission_binding"] = str(admission_binding_raw)

    # The stamp's folded width is itself a hard bound (it already includes
    # the ramp and any unmapped admission term): the target may never
    # exceed it, and when it alone binds below the plan the binding name
    # comes from the stamp's own admission record.
    if measured is not None and measured < decision["target_width"]:
        decision["target_width"] = measured
        binding = map_admission_term(admission_binding_raw) \
            if admission_binding_raw else None
        if admission_binding_raw and \
                str(admission_binding_raw).startswith("ramp"):
            decision["binding_constraint"] = LIMITER_ADMISSION_RAMP
            decision["binding_value"] = measured
            decision["shortfall"] = False
        elif binding in HARD_LIMITERS:
            decision["binding_constraint"] = binding
            decision["binding_value"] = measured
            decision["shortfall"] = bool(measured < planned)
        elif binding:
            decision["binding_constraint"] = binding
            decision["binding_value"] = measured
            decision["shortfall"] = bool(
                measured < planned and binding in HARD_LIMITERS)
        else:
            decision["binding_constraint"] = LIMITER_UNMEASURED_FALLBACK
            decision["binding_value"] = measured
            decision["shortfall"] = False
    if decision["target_width"] < planned and \
            decision["binding_constraint"] in HARD_LIMITERS:
        decision["shortfall"] = True
    return decision


def shortfall_reason(decision: Dict[str, Any]) -> str:
    """One sentence naming the shortfall, for sidecar rows and events:
    planned vs actual, the limiter, and its value -- the answer to
    "why is it running at N" in the record's own words."""
    return (
        f"forcing shortfall: planned width {decision.get('planned_width')} "
        f"could not be reached; the swarm runs at "
        f"{decision.get('target_width')} because "
        f"{decision.get('binding_constraint')} = "
        f"{decision.get('binding_value')} binds below the plan "
        f"(mode {decision.get('mode')}, provider "
        f"{decision.get('provider')}, caps {decision.get('caps')})")
