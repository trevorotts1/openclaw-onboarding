#!/usr/bin/env python3
"""Price card refuses a lip-sync plan with a piece over 30 s (loudly, no price).

N-101/S-41 raised the per-piece top from 6 s to 30 s (a piece is the whole
sentence, 5 to 30 s; a longer passage is a stitch group). The refusal is now
``seconds > lines * 30``: 31 s in one piece and 61 s in two are refused, while
20 s in three and 60 s in two are legal.
$0. Run: python3 scripts/core/catalog_calculator/extensions/test_lipsync_cap.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import price_extension as P                            # noqa: E402

M = "omnihuman-2-0"                     # S-42/3C.1a: the one lip-sync model


def spec(seconds, lines):
    return P._lip_sync_spec({"lip_sync": {"model": M, "seconds": seconds,
                                          "lines": lines}})


def test_doubled_plan_is_accepted():
    s, err, kind = spec(35, 7)               # 7 pieces, 5 s each
    assert err is None and s["seconds"] == 35 and s["lines"] == 7
    assert spec(36, 6)[1] is None            # 6 pieces of exactly 6 s
    assert spec(60, 2)[1] is None            # 2 pieces of 30 s: the new top
    assert spec(90, 3)[1] is None            # 3 pieces of 30 s


def test_piece_over_30_s_is_refused_loudly():
    s, err, kind = spec(18, 3)               # three 6 s pieces: legal now
    assert err is None
    s, err, kind = spec(20, 3)               # a 6.67 s average piece: also legal
    assert err is None
    s, err, kind = spec(31, 1)               # one 31 s piece: over the 30 s top
    assert (s, err, kind) == (None, "LIPSYNC_CLIP_OVER_CAP", "unavailable")
    assert spec(61, 2)[1] == "LIPSYNC_CLIP_OVER_CAP"   # 30.5 s average piece
    assert spec(15, 1)[1] is None                      # one 15 s piece is legal


def test_percent_maximum_and_duration_conflict():
    LC = P.lipsync_clips
    ok = {"seconds": 21, "lines": 4}                 # 60 s: exactly 35%
    assert P._lip_sync_duration_guard(ok, {"length_seconds": 60}) is None
    over = P._lip_sync_duration_guard({"seconds": 24, "lines": 4},
                                      {"length_seconds": 60})
    assert over and over.startswith(LC.OVER_CAP), over
    # No length on the card: nothing to judge, nothing invented.
    assert P._lip_sync_duration_guard(ok, {}) is None


def test_duration_conflict_is_exposed_when_the_bounds_collide():
    """DURATION_CONFLICT still fires, and it is the code's own collision.

    Under N-101 the 3-piece floor is 3 x 5 s = 15 s and applies from 90 s up,
    where the 35% top is 31.5 s, so no ad length collides by itself. The
    collision is proved by moving the floor above the top, which is exactly
    the shape the guard reports (never a re-plan, never a silent trim).
    """
    LC = P.lipsync_clips
    old = LC.CLIP_MIN_S
    LC.CLIP_MIN_S = 40.0                      # 3 x 40 = 120 s floor > 31.5 s
    try:
        conf = P._lip_sync_duration_guard({"seconds": 31, "lines": 1},
                                          {"length_seconds": 90})
    finally:
        LC.CLIP_MIN_S = old
    assert conf and conf.startswith(LC.DURATION_CONFLICT), conf
    assert LC.duration_conflicts(90.0) == []  # restored: no natural collision


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("ALL CHECKS PASS")
