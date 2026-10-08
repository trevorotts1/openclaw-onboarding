#!/usr/bin/env python3
"""Per-ad spoken share target. Run: python3 core/spoken_share/test_per_ad_target.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import spoken_share as S  # noqa: E402

assert S.target_for_range() == 22.5 and S.target_for_range((15, 20)) == 17.5
r = S.check_share(0.175, target_pct=17.5)
assert r["verdict"] == "PASS" and r["target_pct"] == 17.5, r
assert S.check_share(0.175)["verdict"] == "PASS"          # default 22.5: 5 points, accept
assert S.check_share(0.10, target_pct=17.5)["verdict"] == "FLAG"
assert S.check_share(0.05, target_pct=17.5)["verdict"] == "FAIL"
print("ok: per-ad spoken target")
