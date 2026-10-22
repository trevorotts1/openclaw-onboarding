#!/usr/bin/env python3
"""Regression: smooth scenery is not a gaussian fill.

A dim ceiling / shadowed wall / night sky measured 20.8% of frame height on a
real master and was refused GAUSSIAN_FILL, while the same shot at another
second measured 16.7% and passed. A fill is manufactured from existing pixels,
so it leaves one of three mechanical traces; smooth content leaves none.

Four assertions, each pinning one branch of the decision:

  1. smooth scenery (32% of the frame, rows all distinct, no copy of the strip
     below, continuous edge) -> NO violation. Control: the same frame is
     refused GAUSSIAN_FILL by the pre-fix classifier, which had no signature
     check at all.
  2. a repeated-row strip -> violation.
  3. _fill_signature: a band that is a near-copy of the strip below -> True
     (checked directly; driving the whole classifier to this branch would
     require a frame that is not a duplicated strip first).
  4. a flat band ending in a hard step -> violation.

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

def rows(n, fn):
    return [bytes(max(0, min(255, int(fn(y, x)))) for x in range(W)) for y in range(n)]

# 1. Smooth scenery: a dim gradient wall over 32% of the frame. Rows are all
#    distinct, the row means never match the strip below, and the edge is
#    continuous -- none of the three fill traces. The pre-fix classifier
#    refused this frame GAUSSIAN_FILL purely because it was smooth and big.
def wall(y, x):
    return 60 + 0.8 * y + 6 * math.sin(2 * math.pi * x / 97.0 + 0.7 * y)

def room(y, x):
    return 110 + 20 * ((x // 3 + y) % 2) + 0.8 * y

buf = frame(110, wall, room)
got, _ = codes(buf)
check("1: smooth scenery is not a fill", "GAUSSIAN_FILL" not in got, got)
sig = getattr(D, "_fill_signature", None)
if sig is None:
    check("1b: _fill_signature exists (the signature gate is what opens this case)", False,
          "the classifier has no _fill_signature: every big smooth band is a fill")
else:
    ok, why = sig(rows(220, lambda y, x: wall(y, x)), 0, 110)
    check("1b: _fill_signature reads the same frame as smooth-but-real", ok is False, why)

# 2. A stretched strip: few source rows copied over the whole band.
def repeated(y, x):
    return 58 + (y % 2) * 0.4 + 12 * math.sin(2 * math.pi * x / 48.0)

buf = frame(72, repeated, room)
got, _ = codes(buf)
check("2: a repeated-row strip is refused",
      bool(set(got) & {"DUPLICATED_BLURRED_STRIP", "GAUSSIAN_FILL"}), got)

# 3. The near-copy branch, checked at the predicate.
band = rows(40, lambda y, x: 70 + 8 * math.sin(2 * math.pi * x / 48.0 + 0.9 * y))
copy = rows(40, lambda y, x: 70 + 8 * math.sin(2 * math.pi * x / 48.0 + 0.9 * y))
sig = getattr(D, "_fill_signature", None)
ok, why = (sig(band + copy, 0, 40) if sig else (False, "no _fill_signature"))
check("3: a band that copies the strip below is evidence of a fill", ok is True, why)

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
