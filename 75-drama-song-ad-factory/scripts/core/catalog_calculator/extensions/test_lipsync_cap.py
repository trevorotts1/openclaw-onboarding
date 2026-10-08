#!/usr/bin/env python3
"""Price card refuses a lip-sync plan with a clip over 6 s (loudly, no price).
$0. Run: python3 scripts/core/catalog_calculator/extensions/test_lipsync_cap.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import price_extension as P                            # noqa: E402

M = "kling/ai-avatar-standard"


def spec(seconds, lines):
    return P._lip_sync_spec({"lip_sync": {"model": M, "seconds": seconds,
                                          "lines": lines}})


def test_doubled_plan_is_accepted():
    s, err, kind = spec(35, 7)               # 7 clips of 5 s in a 60 s ad
    assert err is None and s["seconds"] == 35 and s["lines"] == 7
    assert spec(36, 6)[1] is None            # 6 clips of exactly 6 s


def test_clip_over_6_s_is_refused_loudly():
    s, err, kind = spec(18, 3)               # three 6.0+ s clips... 18 == 3 x 6 ok
    assert err is None
    s, err, kind = spec(20, 3)               # a 6.67 s average clip
    assert (s, err, kind) == (None, "LIPSYNC_CLIP_OVER_CAP", "unavailable")
    assert spec(15, 1)[1] == "LIPSYNC_CLIP_OVER_CAP"   # one long 15 s job


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("ALL CHECKS PASS")
