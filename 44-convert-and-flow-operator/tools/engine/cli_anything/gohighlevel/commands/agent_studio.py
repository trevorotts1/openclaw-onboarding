"""agent_studio family commands (owner WF29). Registered by WF03.

Rows come from the frozen registry only; see commands/_registry.py for the
route discipline (public rows only, --dry-run sends nothing).
"""
from __future__ import annotations

from ._registry import family_group, register_group

FAMILY = "agent_studio"
OWNER = "WF29"
OPERATION_ROOTS: tuple[str, ...] = ("agentStudio.",)
EXTRA_OPERATION_IDS: tuple[str, ...] = ()

def build() -> object:
    return family_group(FAMILY, OWNER, OPERATION_ROOTS, EXTRA_OPERATION_IDS, "Agent Studio agents, versions and execution")

def register(cli) -> None:
    register_group(cli, build())
