#!/usr/bin/env python3
"""speed.poll: tiered poll cadence with overlapped in-wait checks (F-SPD-2).

2 seconds early, 5 seconds through the middle, 10 seconds late. A wait is
not idle: `overlapped` runs the in-wait checks while the job is out, so a
check never adds its own stage after the job lands.
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


def tier_for(elapsed_s):
    """Seconds to wait before the next status read at this wait age."""
    return float(_S.poll_interval_s(elapsed_s))


def tiers():
    return tuple(float(t) for t in (_S.load_limits().get("poll_tiers_seconds")
                                    or [2.0, 5.0, 10.0]))


def overdue(elapsed_s, job_kind):
    """True when a job is past twice its route's 9-in-10 time (N-80)."""
    return _S.outlier_resend_due(elapsed_s, job_kind)


def overlapped(checks):
    """Run every in-wait check once during a wait; return their results.

    checks: iterable of zero-argument callables. An exception is captured
    as {"error": ...} and never stops the wait.
    """
    out = []
    for check in checks or []:
        try:
            out.append(check())
        except Exception as exc:  # noqa: BLE001 - a check must not break a wait
            out.append({"error": "%s: %s" % (type(exc).__name__, exc)})
    return out


if __name__ == "__main__":  # self-check
    assert tier_for(0) == 2.0
    assert tier_for(29) == 2.0
    assert tier_for(30) == 5.0
    assert tier_for(181) == 10.0
    assert overdue(120, "picture") is True
    assert overdue(119, "picture") is False
    assert overdue(600, "h3_image_to_video") is True
    assert overdue(599, "h3_image_to_video") is False
    assert overdue(1320, "nine_picture") is True
    assert overdue(1319, "nine_picture") is False
    assert overdue(420, "lipsync") is True
    assert overdue(419, "lipsync") is False
    assert overlapped([lambda: 1, lambda: 1 / 0])[0] == 1
    print("speed.poll self-check OK")
