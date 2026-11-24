#!/usr/bin/env python3
"""UNIT U2: the blueprint ERM must sit inside the method's ERM window.

The ERM apex is a property of the method record's runtime_targets, built by
length_formula.plan(); control/method.json is the authority and wins over the
blueprint and req.json. A blueprint ERM outside that window is rejected with
ERM_OUTSIDE_WINDOW before any lyric spend.

Run: python3 scripts/core/method_plan/test_erm_window_s75.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]
for _p in (str(_HERE), str(_CORE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import method_plan.method_plan as MP            # noqa: E402
import length_formula.length_formula as LF      # noqa: E402
import test_method_plan as T                    # noqa: E402  fixture + helpers


def _codes(report):
    return [e["error"] for e in report["errors"]]


def _detail(report, code):
    for e in report["errors"]:
        if e["error"] == code:
            return e["detail"]
    return ""


def test_erm_inside_the_method_window_passes():
    method = T._method(runtime_targets=LF.plan(90, method=True)["method"])
    report = MP.validate(T._blueprint(), method)
    assert report["outcome"] == "ok", report["errors"]
    assert "ERM_OUTSIDE_WINDOW" not in _codes(report), report["errors"]


def test_erm_after_the_window_is_rejected():
    method = T._method(runtime_targets=LF.plan(90, method=True)["method"])
    blueprint = T._blueprint()
    T._cue(blueprint, "ERM_DROP")["start_s"] = 65
    report = MP.validate(blueprint, method)
    codes = _codes(report)
    assert "ERM_OUTSIDE_WINDOW" in codes, report["errors"]
    detail = _detail(report, "ERM_OUTSIDE_WINDOW")
    assert "65" in detail, detail
    assert "END times" in detail, detail
    assert "control/method.json" in detail, detail
    assert "erm_apex_s" in detail, detail


def test_no_runtime_targets_is_unchanged():
    report = MP.validate(T._blueprint(), T._method())
    assert "ERM_OUTSIDE_WINDOW" not in _codes(report), report["errors"]
    assert report["outcome"] == "ok", report["errors"]


if __name__ == "__main__":
    for _name in sorted(n for n in list(globals()) if n.startswith("test_")):
        _fn = globals()[_name]
        if callable(_fn):
            _fn()
            print("ok", _name)
