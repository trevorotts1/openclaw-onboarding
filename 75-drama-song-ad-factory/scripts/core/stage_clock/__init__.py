"""stage_clock: stage timing and the run-time budget (stdlib only).

The stage table lives in references/time-budgets.json so no stage time is
coded. Every stage stamps its start and end; an overrun is logged and the run
is never restarted for the clock (plan section 10D).
"""
from . import clock  # noqa: F401

__all__ = ["clock"]
