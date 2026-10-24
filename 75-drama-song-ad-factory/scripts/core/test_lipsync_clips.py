#!/usr/bin/env python3
"""Coverage is a share of the ad: 25-30% target, 35% hard maximum, first 12 s
articulated, 4-6 s clips; cost cap refuses loudly. $0.
Run: python3 scripts/core/test_lipsync_clips.py"""
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


def test_sixty_second_ad_is_a_share_of_the_ad():
    b = C.budget(60)
    assert (b["min_clips"], b["max_clips"]) == (3, 5)
    assert (b["total_min_s"], b["total_max_s"]) == (15.0, 18.0)   # 25-30%
    assert b["hard_max_s"] == 21.0                                # 35%
    assert b["floor_s"] == 12.0                                   # 3 x 4 s
    assert (b["clip_min_s"], b["clip_max_s"]) == (4.0, 6.0)
    assert b["opening_window_s"] == 12.0
    assert C.TARGET_SHARE == (0.25, 0.30) and C.MAX_SHARE == 0.35
    assert C.TOTAL_PER_REF_S == (15.0, 18.0)      # derived 60 s reference
    assert C.CLIPS_PER_REF == (3, 5)


def test_scales_with_length_and_keeps_floor():
    assert C.budget(120)["total_min_s"] == 30.0 and C.budget(120)["max_clips"] == 10
    assert C.budget(90)["min_clips"] == 4
    b = C.budget(30)
    assert b["total_min_s"] == 7.5 and b["min_clips"] == 3
    assert C.budget(10)["min_clips"] == 3            # never fewer than 3
    raises("BAD_INPUT", C.budget, 0)
    raises("BAD_INPUT", C.budget, True)


def test_duration_conflict_is_exposed_not_replanned():
    assert C.duration_conflicts(60) == []            # 12 s floor fits in 21 s
    assert C.duration_conflicts(35) == []            # 12.25 s max > 12 s floor
    short = C.duration_conflicts(30)                 # 12 s floor vs 10.5 s max
    assert len(short) == 1 and "floor" in short[0] and "maximum" in short[0]
    r = C.check_clips([5, 5], 30)
    assert not r["pass"] and any("floor" in w for w in r["reasons"])


def test_check_clips():
    assert C.check_clips([5, 5, 5], 60)["pass"]                    # 15 s exactly
    assert C.check_clips([6, 6, 6], 60)["pass"]                    # 6 s clips
    assert C.check_clips([5, 5, 5, 5], 60)["pass"]                 # 20 s <= 21
    assert not C.check_clips([5, 5, 5, 5, 5], 60)["pass"]          # 25 s > 35%
    old = C.check_clips([5] * 7, 60)                               # old 30-40 s plan
    assert not old["pass"] and old["reason_code"] == C.BAD_PLAN
    assert not C.check_clips([7, 5, 5], 60)["pass"]                # clip over 6 s
    assert not C.check_clips([6] * 6, 60)["pass"]                  # 6 clips, 36 s
    assert not C.check_clips([5, 5, 5, 0], 60)["pass"]


def test_opening_twelve_seconds():
    assert C.check_opening(0.0, 60)["pass"]
    assert C.check_opening(12.0, 60)["pass"]
    late = C.check_opening(12.5, 60)
    assert not late["pass"] and late["reason_code"] == C.OPENING_SHORT
    assert not C.check_clips([5, 5, 5], 60, first_clip_start_s=14)["pass"]
    assert C.check_opening(5.0, 8)["pass"]           # a short ad: window is 8 s


def test_free_no_lipsync_route_is_explicit():
    ok = C.check_clips([], 60, route=C.ROUTE_NO_LIPSYNC)
    assert ok["pass"] and ok["reason_code"] == C.FREE_ROUTE_OK
    assert not C.check_clips([5, 5, 5], 60, route=C.ROUTE_NO_LIPSYNC)["pass"]
    assert C.check_clips([5, 5, 5], 60)["pass"]      # ordinary runs keep lip-sync
    raises(C.BAD_PLAN, C.check_clips, [5, 5, 5], 60, "sometimes")


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
