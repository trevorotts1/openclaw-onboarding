"""Contained unit failure for signature-launch swarms.

One unit failing never stops the others. Every unit supplied to ``run_units``
is attempted exactly once; its outcome is recorded as ``done`` or ``failed``.
``aggregate_status`` / ``build_package`` then mark the whole package ``failed``
if any unit failed, so a caller can never report a package as done while a
unit failed.

``KeyboardInterrupt`` and ``SystemExit`` are not swallowed: only ``Exception``
is contained, so an operator abort still stops the run.
"""

from __future__ import annotations

DONE = "done"
FAILED = "failed"
BLOCKED = "blocked"


def run_units(units, runner):
    """Run every ``(unit_id, payload)``; contain each failure.

    ``units`` is a mapping ``{unit_id: payload}``; ``runner(unit_id, payload)``
    returns any value or raises. Returns one outcome dict per unit, in input
    order. Never raises for a unit failure.
    """
    outcomes = []
    for unit_id, payload in units.items():
        try:
            outcomes.append({
                "unit_id": unit_id,
                "status": DONE,
                "value": runner(unit_id, payload),
                "error": None,
            })
        except Exception as exc:  # contained per unit; interrupts still propagate
            outcomes.append({
                "unit_id": unit_id,
                "status": FAILED,
                "value": None,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            })
    return outcomes


def aggregate_status(outcomes):
    """Package status: ``failed`` if any unit failed, else ``done``.

    ``blocked`` is returned only when no unit failed and a caller explicitly
    marked one blocked; this module never invents blocked units.
    """
    if any(o.get("status") == FAILED for o in outcomes):
        return FAILED
    if any(o.get("status") == BLOCKED for o in outcomes):
        return BLOCKED
    return DONE


def failed_unit_ids(outcomes):
    return [o["unit_id"] for o in outcomes if o.get("status") == FAILED]
