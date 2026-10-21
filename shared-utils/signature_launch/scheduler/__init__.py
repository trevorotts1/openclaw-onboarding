"""Signature Launch swarm scheduler (WF-SWARM lane).

Reads a launch plan (shared-utils/signature_launch_contract/launch-plan.schema.json)
and turns `waits_for` into waves of units that may start together.

The public API is re-exported here so ``from signature_launch.scheduler import
unit_index`` and the script entry point agree.  ``model`` is the one authority
for the unit expansion and the result envelope (lane L03).
"""

from . import model
from .scheduler import (
    SchedulerError,
    ai_state,
    blockers,
    expansion,
    load_plan,
    ready_units,
    run_all,
    schedule_waves,
    start,
    unit_index,
    validate_plan,
)

__all__ = [
    "model",
    "SchedulerError",
    "ai_state",
    "blockers",
    "expansion",
    "load_plan",
    "ready_units",
    "run_all",
    "schedule_waves",
    "start",
    "unit_index",
    "validate_plan",
]
