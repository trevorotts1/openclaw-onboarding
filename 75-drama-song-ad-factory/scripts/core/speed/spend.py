#!/usr/bin/env python3
"""speed.spend: the burst spend guard over the speed rules (N-87, 10C).

ceiling = estimate x 1.5 before the first paid job; one line at 80 percent;
at 100 percent only paid bursts stop and the owner is asked once. Never a
silent park.
"""
from __future__ import annotations

import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

try:  # packaged: speed.speed
    from . import speed as _S
except ImportError:  # run as a script
    import speed as _S  # type: ignore


def ceiling(estimate):
    """The run ceiling from the estimate: estimate x 1.5."""
    limits = _S.load_limits()
    mult = float((limits.get("spend_guard") or {}).get("ceiling_multiple") or 1.5)
    return int(float(estimate or 0) * mult)


def guard(spent, estimate, balance=None):
    """allowed | warn | stop, with the one line.

    balance None means the balance was not read: the guard reasons from
    spend against the ceiling and does not claim a balance.
    """
    limits = _S.load_limits()
    sg = limits.get("spend_guard") or {}
    cap = ceiling(estimate)
    if balance is not None:
        status, _cap, code = _S.spend_guard(balance, estimate, limits)
        if status == "stop":
            return {"verdict": "stop", "code": code, "ceiling": cap,
                    "line": "balance %.2f is under this burst's estimate "
                            "%.2f plus its remake round; nothing sent, the "
                            "owner is asked once" % (float(balance),
                                                     float(estimate or 0))}
    used = float(spent or 0)
    if cap and used >= cap * float(sg.get("stop_fraction") or 1.0):
        return {"verdict": "stop", "code": "SPEND_CEILING", "ceiling": cap,
                "line": "spend %.2f is at the ceiling %.2f from the estimate "
                        "x1.5; paid bursts stop, free work goes on, the owner "
                        "is asked once - never a silent park" % (used, cap)}
    if cap and used >= cap * float(sg.get("warn_fraction") or 0.8):
        return {"verdict": "warn", "code": "SPEND_80", "ceiling": cap,
                "line": "spend %.2f is past 80 percent of the ceiling %.2f; "
                        "the run continues" % (used, cap)}
    return {"verdict": "allowed", "code": "OK", "ceiling": cap, "line": ""}


def check_burst(spent, estimate, balance=None):
    """(allowed, code, line) for a paid burst."""
    verdict = guard(spent, estimate, balance)
    if verdict["verdict"] == "stop":
        return False, verdict["code"], verdict["line"]
    return True, verdict["code"], verdict["line"]
