#!/usr/bin/env python3
"""H10 done-when: a woman's face over a 72 Hz line is flagged
VOICE_FACE_MISMATCH, that take is regenerated, and the receipt has numbers.
Run: python3 test_line_voice_fit.py"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import line_voice_fit as v  # noqa: E402
try:  # pytest binds the package; line_voice_fit needs the module file itself
    import qc_voice_match.qc_voice_match as _base  # noqa: E402
except ImportError:  # script run already bound the module as its base
    import qc_voice_match as _base  # noqa: E402
v.base = _base

R = 8000


def tone(hz, secs=0.6):
    return {"sample_rate": R, "samples": [
        math.sin(2 * math.pi * hz * i / R) + 0.4 * math.sin(4 * math.pi * hz * i / R)
        for i in range(int(R * secs))]}


CH = {"kiesett": {"gender": "female"}, "stale": {"gender": "male"}}
LINE = {"line_id": "V1", "onscreen": "kiesett", "start_s": 0.0, "end_s": 0.6}

# 1. the Kiesett case: 72 Hz over the woman's face -> mismatch, numbers present
r = v.measure_line(LINE, CH, tone(72))
assert r["code"] == v.CODE and r["verdict"] == "redo", r
assert 60 < r["median_hz"] < 85 and r["deviation_pct"] > 10, r

# 2. target rule bands: 160 Hz is 3.0% under 165 -> accept; 152 -> 7.9% flag
assert v.grade(160, (165, 255)) == (3.03, "accept")
assert v.grade(152, (165, 255))[1] == "accept_flagged"
assert v.grade(140, (165, 255))[1] == "redo"
assert v.grade(None, (165, 255))[1] == "redo"

# 3. regenerate: first take 72 Hz, second 200 Hz -> fixed, 1 regeneration
calls = []
def regen(line, n):
    calls.append(n)
    return tone(200)
rc = v.enforce([LINE], CH, {"V1": tone(72)}, regen)
assert rc["outcome"] == "ok" and rc["summary"]["regenerated"] == 1 and calls == [1], rc
a = rc["lines"][0]["attempts"]
assert a[0]["verdict"] == "redo" and a[1]["verdict"] == "accept", a

# 4. never keep the closest: always-low regenerations end rejected after MAX_ROUNDS
rc = v.enforce([LINE], CH, {"V1": tone(72)}, lambda l, n: tone(80), max_rounds=2)
assert rc["outcome"] == "rejected" and rc["reason_code"] == v.CODE, rc
assert rc["lines"][0]["regenerated"] == 2 and rc["summary"]["failed"] == 1

# 5. a fitting line is untouched; undeclared character fails closed
rc = v.enforce([LINE], CH, {"V1": tone(210)}, regen)
assert rc["lines"][0]["regenerated"] == 0 and rc["outcome"] == "ok"
r = v.measure_line({"line_id": "X", "onscreen": "ghost"}, CH, tone(210))
assert r["code"] == "CHARACTER_VOICE_UNDECLARED" and r["verdict"] == "redo"
print("ok: line_voice_fit (H10)")
