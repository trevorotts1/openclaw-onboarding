#!/usr/bin/env python3
"""Run: python3 core/length_formula/test_length_formula.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import length_formula as LF  # noqa: E402
import sung_hook  # noqa: E402

# L=60 (58 s delivered), BSW share: the measured ~65-word recipe.
p = LF.plan(60, (15, 20))
assert p["delivered_s"] == 58 and 63 <= p["words"]["total"] <= 67, p["words"]
assert p["words"]["opener_max"] <= 3 and p["hook_repeats"] == 3, p
assert p["instrumental"]["breaks"] == 0 and p["extend"] == [], p
assert p["first_sung_by_s"] == 8.7, p

for L in (60, 90, 120, 180, 300, 420, 600, 75, 150, 240):
    p = LF.plan(L)
    D = L - 2
    assert p["delivered_s"] == D
    assert p["hook_repeats"] == sung_hook.hook_count(D)
    assert p["words"]["spoken"] + p["words"]["sung"] == p["words"]["total"]
    assert p["spoken_share_pct_planned"] <= p["spoken_share_pct_requested"] + 0.6, (L, p)
    assert p["sections"]["chorus"] >= 1 and p["sections"]["verses"] >= 1
    assert "mid-song" in p["spoken_placement"]
    if L > 300:
        segs = p["extend"]
        assert segs[0]["kind"] == "base" and segs[0]["duration_s"] == 300
        assert all(s["continue_at_s"] == segs[i]["covers_to_s"] - 30 for i, s in enumerate(segs[1:]))
        assert abs(segs[-1]["covers_to_s"] - D) < 0.2 and p["continuity"], segs
    else:
        assert p["extend"] == [] and p["continuity"] is None
tot = [LF.plan(L)["words"]["total"] for L in (60, 90, 120, 180, 300, 600)]
assert tot == sorted(tot) and tot[-1] > 5 * tot[0], tot
assert LF.plan(60)["spoken_share_pct_requested"] == 22.5
assert LF.plan(60, (15, 20))["words"]["spoken"] <= LF.plan(60)["words"]["spoken"]
for bad in (10, True, "60"):
    try:
        LF.plan(bad)
    except LF.LengthError:
        pass
    else:
        raise AssertionError(bad)
try:
    LF.plan(60, 80)
except LF.LengthError:
    pass
else:
    raise AssertionError("share 80")
print("ok: length_formula")
