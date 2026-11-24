#!/usr/bin/env python3
"""style_check.py: N-30, implemented once in ``vision``.

A named entry point for the style check. The rules live in
``vision.style_check``: one answer against the locked look wording, a required
control pair, STYLE_MISMATCH on a no, STYLE_CHECK_UNAVAILABLE when it cannot
run, and no waiver.
"""
from __future__ import annotations

from .vision import (STYLE_CHECK_UNAVAILABLE, STYLE_MISMATCH, STYLE_WAIVER_REFUSED,
                     style_check, style_question, style_waiver)

TOOL_NAME = "clip_checks.style_check"
TOOL_VERSION = "1.0.0"

check_style = style_check

__all__ = ["STYLE_CHECK_UNAVAILABLE", "STYLE_MISMATCH", "STYLE_WAIVER_REFUSED",
           "check_style", "style_check", "style_question", "style_waiver"]


if __name__ == "__main__":
    # N-30 control: no answer fails closed, a no is MAJOR item 6, a bad control
    # pair is unavailable, a yes passes, and there is no waiver.
    assert check_style(None, (True, False))["item"] == 15
    assert check_style(False, (True, False))["item"] == 6
    assert check_style(True, (None, None))["item"] == 15
    assert check_style(True, (True, False))["pass"] is True
    assert style_waiver()["code"] == STYLE_WAIVER_REFUSED
    assert "a painted look" in style_question("a painted look")
    assert "photograph" in style_question("a painted look").lower()
    print("style_check: control PASS")
