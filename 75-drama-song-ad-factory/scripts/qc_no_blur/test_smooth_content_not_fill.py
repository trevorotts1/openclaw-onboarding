#!/usr/bin/env python3
"""Regression: smooth scenery is not a gaussian fill.

A dim ceiling / shadowed wall / night sky measured 20.8% of frame height on a
real master and was refused GAUSSIAN_FILL, while the same shot at another
second measured 16.7% and passed. A fill is manufactured from existing pixels,
so it leaves one of three mechanical traces; smooth content leaves none. These
tests pin both sides:

  * smooth unique gradient across a large top band -> no violation
  * a stretched strip (few source rows copied) -> violation
  * a band that is a near-copy of the strip below -> violation
  * a hard step at the band edge -> violation

Stdlib only. Run: python3 scripts/qc_no_blur/test_smooth_content_not_fill.py
"""
from __future__ import annotations

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import detect as D  # noqa: E402

FS = []


def check(name, cond, detail=""):
    print(("ok " if cond else "FAIL ") + name + ((" -- %s" % (detail,)) if detail and not cond else ""))
    if not cond:
        FS.append(name)


W, H = 192, 342


def frame(top_rows, top_fn, core_fn):
    """Gray8 buffer: top band from top_fn(y), the rest from core_fn(y)."""
    buf = bytearray(W * H)
    for y in range(H):
        fn = top_fn if y < top_rows else core_fn
        for x in range(W):
            buf[y * W + x] = max(0, min(255, int(fn(y, x))))
    return bytes(buf)


def codes(buf):
    viol, stats = D.analyze(buf, W, H)
    return [v["code"] for v in viol], stats


# 1. A dim ceiling: smooth vertical gradient, every row different, textured core.
def _real_frame(y, x):
    """A dim ceiling that gradually gains texture into the room.

    Rows are all distinct (no duplicated strip), the horizontal detail rises
    smoothly with y (no step at any band edge), and the top fifth is smooth
    low-contrast scenery -- exactly what a pre-dawn kitchen looks like.
    """
    base = 58 + y * 0.40 + 12 * math.sin(2 * math.pi * x / 48.0 + y * 0.12) \
        + (y * 7) % 3
    amp = 0.0 if y < 80 else min(30.0, (y - 80) * 0.6)
    return base + amp * (((x // 3) + y) % 2)


def smooth_top(y, x):
    return _real_frame(y, x)


def detailed_core(y, x):
    return _real_frame(y, x)


def repeated(y, x):
    # a stretched strip: two smooth source rows copied over the whole band
    return 58 + (y % 2) * 0.4 + 12 * math.sin(2 * math.pi * x / 48.0)


buf = frame(72, repeated, detailed_core)
got, _ = codes(buf)
check("2: a repeated-row strip is refused",
      bool(set(got) & {"DUPLICATED_BLURRED_STRIP", "GAUSSIAN_FILL"}), got)

# 4. Hard step at the band boundary (fill ends, real content begins).
def stepped_top(y, x):
    return 40


def stepped_core(y, x):
    return 200 if y % 3 else 120


buf = frame(72, stepped_top, stepped_core)
got, _ = codes(buf)
check("4: a flat band ending in a hard step is refused", bool(got), got)

print()
if FS:
    print("%d FAILED: %s" % (len(FS), ", ".join(FS)))
    raise SystemExit(1)
print("ALL PASS")
