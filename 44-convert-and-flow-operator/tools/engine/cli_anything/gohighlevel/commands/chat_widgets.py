"""chat_widgets family commands (owner WF31). Registered by WF03.

Rows come from the frozen registry only; see commands/_registry.py for the
route discipline (public rows only, --dry-run sends nothing).
"""
from __future__ import annotations

from ._registry import family_group, register_group

FAMILY = "chat_widgets"
OWNER = "WF31"
OPERATION_ROOTS: tuple[str, ...] = ("widgets.",)
EXTRA_OPERATION_IDS: tuple[str, ...] = ()

def build() -> object:
    return family_group(FAMILY, OWNER, OPERATION_ROOTS, EXTRA_OPERATION_IDS, "Chat widgets")

def register(cli) -> None:
    register_group(cli, build())
