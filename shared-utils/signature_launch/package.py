"""Launch package assembly with contained failure.

The package record is the run's final word: ``status`` is ``failed`` whenever
any unit failed, even though every other unit still completed. Kept JSON-safe
so it can be written beside the run folder unchanged.
"""

from __future__ import annotations

from .failure import DONE, FAILED, aggregate_status, failed_unit_ids, run_units


def build_package(units, runner):
    """Run all units and return the package record.

    ``units`` is ``{unit_id: payload}``; ``runner`` is called once per unit.
    A failing unit is recorded, not raised, and the remaining units still run.
    """
    outcomes = run_units(units, runner)
    package_status = aggregate_status(outcomes)
    complete = [o["unit_id"] for o in outcomes if o["status"] == DONE]
    failed = failed_unit_ids(outcomes)
    return {
        "schema_version": "1.0",
        "status": package_status,
        "ok": package_status != FAILED,
        "counts": {
            "total": len(outcomes),
            "done": len(complete),
            "failed": len(failed),
        },
        "completed_units": complete,
        "failed_units": failed,
        "units": outcomes,
    }
