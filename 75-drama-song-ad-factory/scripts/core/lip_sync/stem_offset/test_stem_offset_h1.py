#!/usr/bin/env python3
"""Part H H1 test: a stem delayed 0.066 s against the mix is measured and
the clip lands within one frame. Synthetic audio, stdlib, $0.
Run: python3 core/lip_sync/stem_offset/test_stem_offset_h1.py"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))   # core/

from lip_sync.stem_offset import cut_plan, measure_offset   # noqa: E402

RATE, FPS, DELAY = 8000, 30, 0.066
BURSTS = [(2.0, 2.6), (3.5, 4.4), (5.2, 5.5), (6.0, 7.1), (8.0, 8.4)]


def _sig(delay):
    rnd = random.Random(7)
    out = [0.0] * (10 * RATE)
    for s, e in BURSTS:
        for i in range(int((s + delay) * RATE), int((e + delay) * RATE)):
            out[i] = rnd.uniform(-1, 1)
    return out


def _first_sound(x, thr=0.2):
    return next(i for i, v in enumerate(x) if abs(v) > thr) / RATE


def test():
    mix, stem = _sig(0.0), _sig(DELAY)
    m = measure_offset(stem, mix, RATE)
    assert abs(m["offset_s"] - DELAY) <= 0.01, m
    assert m["corr"] > 0.9, m
    # line = burst 3.5-4.4 s on the mix timeline (its real Suno timestamps)
    p = cut_plan(3.5, 4.4, m["offset_s"])
    a = int(p["cut_start_stem"] * RATE)
    clip = stem[a:a + int(p["cut_dur"] * RATE)]
    heard = p["place_at"] + _first_sound(clip)       # on the mix timeline
    assert abs(heard - 3.5) <= 1 / FPS, heard        # within one frame
    assert p["place_at"] == 3.5 - p["lead_s"]        # never re-timed
    # control: uncompensated cut is late by the offset
    q = cut_plan(3.5, 4.4, 0.0)
    b = int(q["cut_start_stem"] * RATE)
    late = q["place_at"] + _first_sound(stem[b:b + int(q["cut_dur"] * RATE)])
    assert abs(late - 3.5 - DELAY) <= 0.01, late
    # silence fails closed
    try:
        measure_offset([0] * 10 * RATE, mix, RATE)
        raise SystemExit("silence must fail")
    except ValueError as e:
        assert "STEM_OFFSET_SILENT" in str(e)
    print("ok: stem_offset H1 (measured %.3f s, corr %.2f)"
          % (m["offset_s"], m["corr"]))


if __name__ == "__main__":
    test()
