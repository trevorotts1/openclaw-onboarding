#!/usr/bin/env python3
"""severities.py: adapter kept for callers that use the (code, where, detail)
shape. The one severity table is :mod:`clip_checks.severity` (N-98).

Two builders once landed two severity tables that disagreed on WARDROBE_MORPH
and on fifteen codes one had and the other did not. A fixed MAJOR list cannot
have two homes, so this module keeps the older call shape and delegates every
level decision to ``severity``: no table lives here.

stdlib only, no spend.
"""
from __future__ import annotations

from . import severity as _S
from .severity import (  # noqa: F401  re-exported for the old call sites
    MAJOR,
    MAJOR_ITEMS,
    MEDIUM,
    MINOR,
    only_major,
    worst,
)

TOOL_NAME = "clip_severities"
TOOL_VERSION = "1.1.0"

#: Code -> MAJOR item, from the one table.
CODE_ITEM = dict(_S.CODE_TO_ITEM)
N_ITEMS = len(MAJOR_ITEMS)

#: Items 12, 16, 17 and 19 are MAJOR only when their condition is proven.
CONDITIONAL_ITEMS = frozenset((12, 16, 17, 19))

#: Conditional codes and the item each names when its condition is proven.
CONDITIONAL_CODE_ITEM = {
    "CROWD_MISMATCH": 12,
    "CHOIR_COUNT_MISMATCH": 12,
    "SET_PIECE_MISSING": 12,
    "LIGHT_OFF_CLOCK": 12,
    "PLACE_MISMATCH": 12,
    "JUMP_CUT_DETECTED": 16,
    "SCREEN_DIRECTION_BREAK": 16,
    "PROP_CONTINUITY_BREAK": 17,
    "PROP_FACES_CAMERA": 19,
    "PROP_TURNED_TO_CAMERA": 19,
}


def level_for(code, condition=None):
    """The fixed level of one code. ``condition`` proves a conditional item
    (12, 16, 17, 19); without it such a code stays MEDIUM (3J). Any
    ``_UNAVAILABLE`` code is MAJOR item 15: it fails closed."""
    code = str(code or "")
    if code.endswith("_UNAVAILABLE"):
        return MAJOR
    if condition and code in CONDITIONAL_CODE_ITEM:
        return MAJOR
    return _S.level_for(code)[0]


def item_for(code, condition=None):
    """The MAJOR item number this finding names, or None when it is MEDIUM."""
    if level_for(code, condition) != MAJOR:
        return None
    if str(code or "").endswith("_UNAVAILABLE"):
        return 15
    if code in CONDITIONAL_CODE_ITEM:
        return CONDITIONAL_CODE_ITEM[code]
    return _S.level_for(code)[1]


def finding(code, where=None, detail="", level=None, condition=None, **extra):
    """One finding row in the older shape; the level comes from ``severity``."""
    kwargs_item = None
    if level is None and str(code or "").endswith("_UNAVAILABLE"):
        level = MAJOR
        kwargs_item = 15
    if level is None and condition and code in CONDITIONAL_CODE_ITEM:
        level = MAJOR
    kwargs = dict(extra)
    if kwargs_item is not None:
        kwargs["item"] = kwargs_item
    elif level == MAJOR and code in CONDITIONAL_CODE_ITEM:
        kwargs["item"] = CONDITIONAL_CODE_ITEM[code]
    if level == MAJOR and str(code or "").endswith("_UNAVAILABLE"):
        kwargs.setdefault("item", 15)
    row = _S.finding(code, detail, level=level, **kwargs)
    row["where"] = where
    if condition is not None:
        row["condition"] = bool(condition)
    return row


def summarize(findings):
    """Counts, the MAJOR rows and whether anything stops (3J)."""
    counts = {MINOR: 0, MEDIUM: 0, MAJOR: 0}
    majors = []
    for row in findings or []:
        lv = row.get("level") if isinstance(row, dict) else None
        if lv in counts:
            counts[lv] += 1
        if lv == MAJOR:
            majors.append(row)
    return {"counts": counts, "majors": majors, "pass": not majors,
            "worst": worst(findings)}
