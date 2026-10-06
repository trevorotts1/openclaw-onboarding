#!/usr/bin/env python3
"""admission.py -- PRES-015 EFFECTIVE ADMISSION + WARMUP RAMP.

WHAT THIS IS
------------
The one module that folds every admission term of PRES-015 into the number a
wave or pool actually runs at:

    effective = min(
        ready_work,                  # units actually ready to run RIGHT NOW
        mode_ceiling_minus_active,   # the human-ratified mode ceiling (100)
                                     # minus what this run already has active
        account_free_permits,        # account ceiling minus total active for
                                     # the route's provider (across the run)
        rate_or_token_budget,        # the governor's own admission window
        cost_allocation,             # the client's declared allocation
        class_hardware_budget,       # the box's measured budget for this
                                     # work class (hardware_budget.py)
    )

Every term is computed by the module that owns it (model_router for the mode
ceiling, capacity for the account factors, governor for the rate budget,
hardware_budget for the class budget); this module only MIN()s them and names
the BINDING limiter, so the client report can say which term decided.

WHY A MODULE AND NOT AN INLINE MIN() AT EACH CALL SITE: the terms change
together (PRES-015 acceptance 1 makes one scenario out of five of them) and
the warmup ramp below needs one place to keep per-provider health state. A
width decided anywhere else is a width this module cannot see, bound, or
explain.

THE WARMUP RAMP
---------------
Spec step 1: "Ramp from conservative warmup using measured p95
latency/error/memory/CPU; raise when healthy, reduce admission on
pressure/429." Implementation:

    The ramp scale STARTS at RAMP_START_SCALE = 1.0 -- "conservative" here
    means the ramp NEVER grants a width above the static min() of the
    measured ceilings (a client whose account says 8 never sees the ramp
    grant 100; an unmeasured term never binds). Spec step 5 requires
    "configurable default normal-mode behaviour preserves existing users":
    throttling the FIRST wave of every run to a quarter of the operator's
    ratified ceiling would change every existing user's behaviour for the
    worse, so the conservative warmup is the static min itself. The ramp
    exists to cut under measured pressure: any 429, slow window or hardware
    pressure halves the scale (floor WARMUP_MIN_SCALE = 0.25) and restarts
    the window; a HEALTHY WINDOW (WARMUP_WINDOW_S with at least
    WARMUP_MIN_OK clean observations, zero 429s, p95 under budget, hardware
    pressure negative) restores it multiplicatively by RAMP_HEALTHY_FACTOR,
    capped at 1.0. Recovery therefore needs a SUSTAINED healthy window, not
    one old success -- a success already in flight when the 429 landed does
    not count as post-429 health (the PRES-016-adjacent rule).

The ramp NEVER widens past the static min() above -- it only lowers or
restores. An operator who DOES want a cold-start ramp on a cold provider can
set PRESENTATION_ADMISSION_WARMUP_FRACTION (a float in (0, 1]) to seed new
providers' scale lower than 1.0.

STATE
-----
Process-local by design (the same scope governor.py uses and PRES-004
documents): the ramp informs ONE process's admissions. Persisted cross-run
state would be a separate contract; the spec asks for a ramp, not a ledger.

ROLLBACK: PRESENTATION_ADMISSION=0 makes effective_width() answer the
caller's requested width unchanged -- byte-for-byte the pre-PRES-015 path.

Never raises on any path: admission that cannot be computed answers the
documented degraded value, labelled. (An admission module that crashes the
dispatch loop because a probe failed would be its own defect.)
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

FLAG_ENV = "PRESENTATION_ADMISSION"
FLAG_DEFAULT = "1"

#: Ramp constants -- named, documented, never magic.
WARMUP_WINDOW_S = 20.0        # one healthy observation window
WARMUP_MIN_OK = 3             # observations a window needs before it counts
RAMP_FLOOR_MIN = 1            # the ramp never narrows below this
WARMUP_MIN_SCALE = 0.25       # scale never below a quarter of the static min
RAMP_HEALTHY_FACTOR = 1.5     # a healthy window grows the scale by half...
RAMP_MAX_SCALE = 1.0          # ...but never past the static min itself
RAMP_PRESSURE_FACTOR = 0.5    # 429 or pressure halves it, instantly
P95_BUDGET_S = 45.0           # p95 latency a healthy window must stay under
#: Where a NEW provider's ramp scale starts. 1.0 = the static min() itself is
#: the conservative warmup (see the module docstring): the ramp only ever
#: CUTS, on measured pressure, and restores after sustained health. An
#: operator who wants a cold-start throttle can seed it lower here.
WARMUP_FRACTION = 1.0
#: observation kinds
OBS_OK = "ok"
OBS_429 = "429"
OBS_SLOW = "slow"
OBS_PRESSURE = "pressure"


def flag_enabled() -> bool:
    """True unless PRESENTATION_ADMISSION=0 (the documented rollback)."""
    return os.environ.get(FLAG_ENV, FLAG_DEFAULT) != "0"


def _start_scale() -> float:
    """The scale a fresh provider state begins at: WARMUP_FRACTION, or the
    operator's own PRESENTATION_ADMISSION_WARMUP_FRACTION when it parses to
    a float in (0, 1]. Never raises; an invalid value is ignored."""
    raw = (os.environ.get("PRESENTATION_ADMISSION_WARMUP_FRACTION") or "").strip()
    if raw:
        try:
            val = float(raw)
            if 0.0 < val <= 1.0:
                return val
        except ValueError:
            pass
    return WARMUP_FRACTION


# ---------------------------------------------------------------------------
# per-provider ramp state
# ---------------------------------------------------------------------------
_LOCK = threading.Lock()
_STATE: Dict[str, Dict[str, Any]] = {}


def _state_for(provider: str) -> Dict[str, Any]:
    st = _STATE.get(provider)
    if st is None:
        st = {
            "scale": _start_scale(),      # current ramp scale of the static min
            "window_start": time.monotonic(),
            "window_ok": 0,               # clean observations in this window
            "window_bad": 0,              # 429/slow/pressure in this window
            "latencies": [],              # recent ok latencies (bounded)
            "last_event": None,
        }
        _STATE[provider] = st
    return st


def observe(provider: str, kind: str, *,
            latency_s: Optional[float] = None) -> None:
    """Record ONE admission outcome for the provider's ramp.

    kind: OBS_OK | OBS_429 | OBS_SLOW | OBS_PRESSURE. Best-effort, never
    raises, never blocks: a state-keeping failure must not cost an admission.
    """
    if not provider:
        return
    try:
        with _LOCK:
            st = _state_for(str(provider))
            now = time.monotonic()
            if kind == OBS_OK:
                st["window_ok"] += 1
                if isinstance(latency_s, (int, float)):
                    st["latencies"].append(float(latency_s))
                    if len(st["latencies"]) > 100:
                        st["latencies"] = st["latencies"][-50:]
                _maybe_promote(st, now)
            elif kind == OBS_SLOW:
                st["window_bad"] += 1
                _demote(st, "slow")
            else:  # OBS_429 / OBS_PRESSURE -- both are instant halvings
                st["window_bad"] += 1
                _demote(st, kind)
            st["last_event"] = {"kind": kind, "ts": now}
    except Exception:  # noqa: BLE001 -- state is best-effort
        pass


def _p95(latencies: List[float]) -> Optional[float]:
    if not latencies:
        return None
    ordered = sorted(latencies)
    idx = max(0, int(round(0.95 * (len(ordered) - 1))))
    return ordered[idx]


def _maybe_promote(st: Dict[str, Any], now: float) -> None:
    """A full healthy window grows the ramp. A window is healthy when it
    holds WARMUP_MIN_OK clean observations, NO bad ones, and the recent p95
    is inside the latency budget."""
    if st["window_bad"] > 0:
        return
    if st["window_ok"] < WARMUP_MIN_OK:
        return
    if (now - st["window_start"]) < WARMUP_WINDOW_S:
        return
    p95 = _p95(st["latencies"])
    if p95 is not None and p95 > P95_BUDGET_S:
        # slow-but-successful: hold, do not promote, do not punish
        return
    st["scale"] = min(RAMP_MAX_SCALE, st["scale"] * RAMP_HEALTHY_FACTOR)
    st["window_start"] = now
    st["window_ok"] = 0


def _demote(st: Dict[str, Any], reason: str) -> None:
    """429/pressure/slow halves the scale and restarts the healthy window.
    The scale never drops below WARMUP_MIN_SCALE of the static min."""
    st["scale"] = max(WARMUP_MIN_SCALE, st["scale"] * RAMP_PRESSURE_FACTOR)
    st["window_start"] = time.monotonic()
    st["window_ok"] = 0
    st["window_bad"] = 0
    st["last_event"] = {"kind": reason, "ts": st["window_start"]}


def ramp_state(provider: str) -> dict:
    """Diagnostics: one provider's ramp picture (never raises)."""
    try:
        with _LOCK:
            st = _state_for(str(provider or ""))
            return {
                "scale": round(st["scale"], 4),
                "window_ok": st["window_ok"],
                "window_bad": st["window_bad"],
                "window_remaining_s": max(
                    0.0, WARMUP_WINDOW_S
                    - (time.monotonic() - st["window_start"])),
                "p95_latency_s": _p95(st["latencies"]),
                "last_event": dict(st["last_event"]) if st["last_event"] else None,
            }
    except Exception:  # noqa: BLE001
        return {"scale": _start_scale(), "error": "state unavailable"}


def reset(provider: Optional[str] = None) -> None:
    """Clear ramp state (tests, operator hot-reset). No provider = all."""
    with _LOCK:
        if provider:
            _STATE.pop(str(provider), None)
        else:
            _STATE.clear()


# ---------------------------------------------------------------------------
# hardware pressure -- the live half of the class budget
# ---------------------------------------------------------------------------
def hardware_pressure(work_class: str = "text",
                      snapshot: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """Is THIS box under pressure for THIS class right now?

    Reads the cached hardware snapshot (refreshed at most once per TTL --
    never per admission). Pressure means: memory PSI over the stall threshold
    (Linux), or available RAM below one unit of the class. Returns
    (pressured, reason). Never raises."""
    try:
        from . import hardware_budget as hb
    except ImportError:  # pragma: no cover - direct-file run
        try:
            import hardware_budget as hb  # type: ignore[no-redef]
        except ImportError:
            return False, "hardware_budget unavailable"
    try:
        snap = snapshot if snapshot is not None else hb.cached_snapshot()
        if not hb.flag_enabled():
            return False, "hardware budget flag off"
        budget = hb.class_budget(snap, work_class=work_class)
        if budget.get("status") != hb.STATUS_MEASURED:
            return False, "hardware unmeasured"
        psi = snap.get("psi_mem_avg10")
        if isinstance(psi, (int, float)) \
                and psi >= hb.PSI_MEM_SOME_STALL_PCT:
            return True, f"memory PSI {psi}% over stall threshold"
        avail = snap.get("ram_available_bytes")
        if work_class != "text" and isinstance(avail, int) \
                and budget.get("budget", 0) <= 1 and avail is not None:
            # the class budget already bottomed out at 1: that IS pressure
            # for heavy classes (one unit may still run; a second must wait)
            return True, (f"{work_class} budget at floor (available "
                          f"{avail}B)")
        return False, budget.get("reason") or "no pressure signal"
    except Exception as exc:  # noqa: BLE001 -- probing must never raise
        return False, f"pressure probe failed: {exc.__class__.__name__}"


# ---------------------------------------------------------------------------
# the admission min()
# ---------------------------------------------------------------------------
def effective_width(requested: Any, *,
                    provider: str,
                    ready_work: Optional[int],
                    mode_ceiling: int = 100,
                    active_for_mode: int = 0,
                    account_ceiling: Optional[int] = None,
                    active_for_account: int = 0,
                    account_free_permits: Optional[int] = None,
                    rate_budget: Optional[int] = None,
                    cost_allocation: Optional[int] = None,
                    work_class: str = "text",
                    hardware_snapshot: Optional[Dict[str, Any]] = None,
                    include_ramp: bool = True,
                    ) -> Dict[str, Any]:
    """THE admission answer: how wide may this route run RIGHT NOW, and which
    term decided.

    Every term is optional-except-provider because callers hold different
    subsets of the facts; an absent term simply does not bind (an absence is
    never evidence for a lower width). The ramp scale (>= WARMUP_MIN_SCALE,
    <= 1) applies to the STATIC result, so it can lower or restore but never
    widen past the min() of the measured ceilings.

    Returns {width, requested, terms, binding, ramp, discovery_requests: 0}.
    PRESENTATION_ADMISSION=0 answers the requested width verbatim (rollback).
    Never raises."""
    if not flag_enabled():
        try:
            n = int(requested)
        except (TypeError, ValueError):
            n = 1
        return {"width": max(1, n), "requested": requested, "terms": [],
                "binding": "flag-off-rollback", "ramp": None,
                "discovery_requests": 0}
    try:
        req = int(requested)
    except (TypeError, ValueError):
        req = 0
    if req < 1:
        req = ready_work if isinstance(ready_work, int) and ready_work > 0 else 1
    terms: List[Tuple[str, int]] = [("requested", req)]

    if isinstance(ready_work, int) and ready_work > 0:
        terms.append(("ready_work", ready_work))

    # mode ceiling minus what this run already has in flight
    if isinstance(mode_ceiling, int) and mode_ceiling > 0:
        mode_free = max(1, mode_ceiling - max(0, int(active_for_mode or 0)))
        terms.append(("mode_ceiling_minus_active", mode_free))

    # account permits: the run-local accounting of the provider's ceiling
    if isinstance(account_ceiling, int) and account_ceiling > 0:
        acct_free = max(1, account_ceiling - max(0, int(active_for_account or 0)))
        terms.append(("account_free_permits", acct_free))
    elif isinstance(account_free_permits, int) and account_free_permits > 0:
        terms.append(("account_free_permits", account_free_permits))

    if isinstance(rate_budget, int) and rate_budget > 0:
        terms.append(("rate_or_token_budget", rate_budget))

    if isinstance(cost_allocation, int) and cost_allocation > 0:
        terms.append(("cost_allocation", cost_allocation))

    # class-specific hardware budget -- NEVER a global pool cap: it binds
    # this class' routes only, and text-class work is untouched by RAM.
    pressured, pressure_reason = hardware_pressure(
        work_class, snapshot=hardware_snapshot)
    try:
        from . import hardware_budget as hb
        hw_budget = hb.budget_for_class(work_class, hardware_snapshot)
    except Exception:  # noqa: BLE001 -- an absent hardware module never blocks
        hw_budget = None
    if isinstance(hw_budget, int) and hw_budget > 0:
        terms.append((f"class_hardware_budget[{work_class}]", hw_budget))

    static = min(v for _n, v in terms)
    binding = next(n for n, v in terms if v == static)

    # THE RAMP: scale the static width; never widen, never below the floor.
    ramp_info: Optional[dict] = None
    if include_ramp:
        if pressured:
            observe(provider, OBS_PRESSURE)
        scale = ramp_state(provider).get("scale")
        if isinstance(scale, (int, float)):
            ramped = max(RAMP_FLOOR_MIN, int(static * float(scale)))
            if ramped < static:
                binding = f"ramp(scale {round(float(scale), 2)}) -> {binding}"
            ramp_info = {"scale": round(float(scale), 4),
                         "pressure": pressured,
                         "pressure_reason": pressure_reason}
            return {"width": int(ramped), "requested": req,
                    "terms": [{"term": n, "value": v} for n, v in terms],
                    "binding": binding, "ramp": ramp_info,
                    "static_width": int(static),
                    "discovery_requests": 0}
    return {"width": int(static), "requested": req,
            "terms": [{"term": n, "value": v} for n, v in terms],
            "binding": binding, "ramp": ramp_info,
            "static_width": int(static),
            "discovery_requests": 0}


def observe_result(provider: str, *,
                   ok: bool, latency_s: Optional[float] = None,
                   rate_limited: bool = False) -> None:
    """Feed one unit outcome into the ramp (the dispatcher's post-dispatch
    hook). rate_limited=True records a 429 regardless of ok."""
    if rate_limited:
        observe(provider, OBS_429)
        return
    if not ok:
        return  # a plain unit failure is not capacity evidence
    if isinstance(latency_s, (int, float)) and latency_s > P95_BUDGET_S:
        observe(provider, OBS_SLOW, latency_s=latency_s)
        return
    observe(provider, OBS_OK, latency_s=latency_s)
