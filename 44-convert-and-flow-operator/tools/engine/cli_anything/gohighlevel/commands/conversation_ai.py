"""conversation_ai family commands (owner WF28). Registered by WF03.

Rows come from the frozen registry only; see commands/_registry.py for the
route discipline (public rows only, --dry-run sends nothing).
"""
from __future__ import annotations

from ._registry import family_group, register_group

FAMILY = "conversation_ai"
OWNER = "WF28"
OPERATION_ROOTS: tuple[str, ...] = ()
EXTRA_OPERATION_IDS: tuple[str, ...] = ("conversation.agents.create",)

def build() -> object:
    return family_group(FAMILY, OWNER, OPERATION_ROOTS, EXTRA_OPERATION_IDS, "Conversation AI agents")

def register(cli) -> None:
    register_group(cli, build())
