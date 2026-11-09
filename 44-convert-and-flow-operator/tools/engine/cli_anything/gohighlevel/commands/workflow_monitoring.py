"""workflow_monitoring family commands (owner WF25). Registered by WF03.

Rows come from the frozen registry only; see commands/_registry.py for the
route discipline (public rows only, --dry-run sends nothing).
"""
from __future__ import annotations

from ._registry import family_group, register_group

FAMILY = "workflow_monitoring"
OWNER = "WF25"
OPERATION_ROOTS: tuple[str, ...] = ("workflows.logs.", "workflows.step_types.")
EXTRA_OPERATION_IDS: tuple[str, ...] = ("workflows.search", "workflows.definition.validate")

def build() -> object:
    return family_group(FAMILY, OWNER, OPERATION_ROOTS, EXTRA_OPERATION_IDS, "Workflow step types, validation, search and logs")

def register(cli) -> None:
    register_group(cli, build())
