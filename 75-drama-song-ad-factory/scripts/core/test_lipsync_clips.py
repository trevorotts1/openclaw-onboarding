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


def test_cost_is_priced_for_two_tries_by_default():
    rate = 0.04                                      # 720P Kling, from Skill 74
    assert C.MAX_TRIES == 2
    one = C.estimate_cost_usd(17.5, rate, attempts=1)  # old midpoint, one try
    two = C.estimate_cost_usd(35, rate, attempts=1)
    assert abs(two - 2 * one) < 1e-9 and two == 1.4
    worst = C.estimate_cost_usd(35, rate)            # default attempts=MAX_TRIES
    assert worst == 2.8 == C.estimate_cost_usd(35, rate, attempts=2)
    assert C.estimate_cost_usd(35, rate, shapes=2) == 5.6
    ok = C.check_budget(35, rate, 3.0)
    assert ok["pass"] and ok["cost_usd"] == 2.8
    raises(C.OVER_CAP, C.check_budget, 35, rate, 2.0)    # 2 tries do not fit
    assert C.check_budget(35, rate, 2.0, 1, 1)["cost_usd"] == 1.4
    raises(C.PRICE_UNKNOWN, C.check_budget, 35, None, 3.0)
    raises(C.PRICE_UNKNOWN, C.check_budget, 35, 0, 3.0)
    raises(C.CAP_UNKNOWN, C.check_budget, 35, rate, None)


def test_two_try_rule_counts_every_name_variant():
    keys = ["run/lip-ad-ss3", "run/lip-ad-ss3-b", "run/lip-ad-ss30", "run/lip-ad-ss4"]
    assert C.count_jobs(keys, "ss3") == 2           # ss30 is another segment
    assert C.count_jobs(keys, "ss4") == 1
    assert C.check_try_limit(keys, "ss4") == 1      # one try left
    assert C.check_try_limit([], "ss9") == 2
    raises(C.TRY_LIMIT, C.check_try_limit, keys, "ss3")   # 3rd job refused


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("ALL CHECKS PASS")
