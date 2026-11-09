"""community family commands (owner WF10). Registered by WF03.

Rows come from the frozen registry only; see commands/_registry.py for the
route discipline (public rows only, --dry-run sends nothing).
"""
from __future__ import annotations

from ._registry import family_group, register_group

FAMILY = "community"
OWNER = "WF10"
OPERATION_ROOTS: tuple[str, ...] = ("social.community.",)
EXTRA_OPERATION_IDS: tuple[str, ...] = ()

def build() -> object:
    return family_group(FAMILY, OWNER, OPERATION_ROOTS, EXTRA_OPERATION_IDS, "Community social accounts, authors and comments")

def register(cli) -> None:
    register_group(cli, build())
