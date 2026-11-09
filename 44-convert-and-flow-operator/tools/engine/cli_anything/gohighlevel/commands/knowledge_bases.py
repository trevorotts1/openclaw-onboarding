"""knowledge_bases family commands (owner WF30). Registered by WF03.

Rows come from the frozen registry only; see commands/_registry.py for the
route discipline (public rows only, --dry-run sends nothing).
"""
from __future__ import annotations

from ._registry import family_group, register_group

FAMILY = "knowledge_bases"
OWNER = "WF30"
OPERATION_ROOTS: tuple[str, ...] = ("knowledge_bases.",)
EXTRA_OPERATION_IDS: tuple[str, ...] = ()

def build() -> object:
    return family_group(FAMILY, OWNER, OPERATION_ROOTS, EXTRA_OPERATION_IDS, "Knowledge bases and file upload")

def register(cli) -> None:
    register_group(cli, build())
