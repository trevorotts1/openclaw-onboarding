#!/usr/bin/env python3
"""consistency_check.py: N-45 and N-72, implemented once in ``vision``.

Five items (face, hair, wardrobe, accessories, look) plus the sixth expression
question; any no fails closed, a missing answer is unavailable, and every
result carries a ledger row. The rules live in ``vision.consistency_check``.
"""
from __future__ import annotations

from .vision import (CHARACTER_MISMATCH, CONSISTENCY_CHECK_UNAVAILABLE,
                     EXPRESSION_CHECK_UNAVAILABLE, EXPRESSION_MISMATCH,
                     ExpressionGuard, consistency_check, expression_question,
                     ledger_row)

TOOL_NAME = "clip_checks.consistency_check"
TOOL_VERSION = "1.0.0"

check_consistency = consistency_check

__all__ = ["CHARACTER_MISMATCH", "CONSISTENCY_CHECK_UNAVAILABLE",
           "EXPRESSION_CHECK_UNAVAILABLE", "EXPRESSION_MISMATCH",
           "ExpressionGuard", "check_consistency", "consistency_check",
           "expression_question", "ledger_row"]


if __name__ == "__main__":
    # N-45 control: five items plus the sixth; a no names its item; a missing
    # answer fails closed; the ledger row carries the six answers.
    clean = {item: True for item in ("face", "hair", "wardrobe",
                                     "accessories", "look")}
    assert check_consistency(clean, (True, False), expression=True)["pass"]
    out = check_consistency(dict(clean, hair=False), (True, False),
                            expression=True)
    assert not out["pass"] and out["findings"][0].get("item_name") == "hair"
    assert check_consistency(clean, (None, None), expression=True)[
        "findings"][0]["item"] == 15
    assert check_consistency(clean, (True, False), expression=None)[
        "findings"][0]["code"] == EXPRESSION_CHECK_UNAVAILABLE
    row = ledger_row("S12", "sha", "lead", 2, clean, "m", "19:05")
    assert row["answers"] == clean and row["shot"] == "S12"
    assert "face" in expression_question("pain", 2)
    print("consistency_check: control PASS")
