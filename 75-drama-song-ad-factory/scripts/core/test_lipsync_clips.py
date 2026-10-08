#!/usr/bin/env python3
"""Doubled lip-sync: 6-8 clips of 4-6 s per 60 s ad, scaled by length, cost cap
refuses loudly. $0. Run: python3 scripts/core/test_lipsync_clips.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lipsync_clips as C                              # noqa: E402


def raises(code, fn, *a):
    try:
        fn(*a)
    except C.LipsyncClipsError as e:
        assert e.code == code, e.code
        return
    raise AssertionError("did not refuse")


def test_sixty_second_ad_is_doubled():
    b = C.budget(60)
    assert (b["min_clips"], b["max_clips"]) == (6, 8)
    assert (b["total_min_s"], b["total_max_s"]) == (30.0, 40.0)
    assert (b["clip_min_s"], b["clip_max_s"]) == (4.0, 6.0)


def test_scales_linearly_with_length_and_keeps_floor():
    assert C.budget(120)["total_min_s"] == 60.0 and C.budget(120)["max_clips"] == 16
    assert C.budget(90)["min_clips"] == 9
    b = C.budget(30)
    assert b["total_min_s"] == 15.0 and b["min_clips"] == 3
    assert C.budget(10)["min_clips"] == 3            # never fewer than 3
    raises("BAD_INPUT", C.budget, 0)
    raises("BAD_INPUT", C.budget, True)


def test_check_clips():
    assert C.check_clips([5, 5, 5, 5, 5, 5, 5], 60)["pass"]       # 7 x 5 = 35
    assert C.check_clips([5] * 6, 60)["pass"]                      # 30 exactly
    old = C.check_clips([5, 5, 5, 4], 60)                          # old 15-20 s plan
    assert not old["pass"] and old["reason_code"] == C.BAD_PLAN
    assert not C.check_clips([7, 5, 5, 5, 5, 5], 60)["pass"]       # clip over 6 s
    assert not C.check_clips([6] * 9, 60)["pass"]                  # 9 clips, 54 s
    assert not C.check_clips([6] * 7 + [0], 60)["pass"]


def test_cost_is_doubled_and_cap_refuses_loudly():
    rate = 0.04                                      # 720P Kling, from Skill 74
    one = C.estimate_cost_usd(17.5, rate)            # old midpoint
    two = C.estimate_cost_usd(35, rate)
    assert abs(two - 2 * one) < 1e-9 and two == 1.4
    assert C.estimate_cost_usd(35, rate, shapes=2) == 2.8
    ok = C.check_budget(35, rate, 2.0)
    assert ok["pass"] and ok["cost_usd"] == 1.4
    raises(C.OVER_CAP, C.check_budget, 35, rate, 1.0)      # not trimmed, refused
    raises(C.OVER_CAP, C.check_budget, 35, rate, 2.0, 1, 2)  # worst case, 2 attempts
    raises(C.PRICE_UNKNOWN, C.check_budget, 35, None, 2.0)
    raises(C.PRICE_UNKNOWN, C.check_budget, 35, 0, 2.0)
    raises(C.CAP_UNKNOWN, C.check_budget, 35, rate, None)


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("ALL CHECKS PASS")
