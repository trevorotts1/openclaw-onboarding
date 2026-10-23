#!/usr/bin/env python3
"""D3 control: the residual structure map must never read outside the grid.

The full-map residual in motion_score._affine_residual samples
`_bilinear(a, w, x - dx, y - dy)`, whose flat index is `y0 * w + x0`. A
negative `y0` (positive dy) silently resolves to the END of the same flat
grid in CPython: no exception, no log, wrong pixels. A positive overflow
(negative dy) raises a bare IndexError instead of a typed refusal.

Measured on origin/main d9c4220dd at 48x27 (out-of-range _bilinear calls):

    dy       before fix                after fix
    +6.00    0                        0
    +6.25    46                       0
    +7.75    92                       0
    +9.00    138                      0
    -5.75    0                        0
    -6.25    1 then IndexError        0 (measured)

Re-baseline table (only motion_structure moved; every subject score is
bit-identical, so no counted decision value changed):

    fixture       field                 before    after     delta    gate   clears  verdict
    pan           motion_structure      338.58    323.70    -14.88   4.0    yes     unchanged (refused)
    pan           subject_motion_score    0.000190  0.000190  0       0.012  no      unchanged (refused)
    pan_local     motion_structure       31.09     25.79     -5.30   4.0    yes     unchanged (allowed)
    pan_local     subject_motion_score    0.036126  0.036126  0       0.012  yes     unchanged (allowed)
    flash         motion_structure        8.39      8.39     0        4.0    yes     unchanged (refused)
    local         motion_structure       80.11     80.11     0        4.0    yes     unchanged (allowed)
    static        motion_structure        0.00      0.00     0        4.0    no      unchanged (refused)
    black_strobe  motion_structure        5.37      5.37     0        4.0    yes     unchanged (refused)
    gain_strobe   motion_structure        7.51      7.51     0        4.0    yes     unchanged (refused)
    noise8        motion_structure        2.36      2.36     0        4.0    no      unchanged (refused)
    noise48       motion_structure        1.70      1.70     0        4.0    no      unchanged (refused)
    noise64       motion_structure        1.73      1.73     0        4.0    no      unchanged (refused)
    noise80       motion_structure        1.70      1.70     0        4.0    no      unchanged (refused)

No fixture verdict flips and no value crosses its gate. The clamp only trims
rows/columns whose 2x2 bilinear window would leave the grid; the subject path
(interior loop with the shift+2 margin) is untouched and never sampled out of
range.

Run: python3 core/shot_planner/test_motion_d3_wraparound.py
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from shot_planner import motion_score as ms                    # noqa: E402
from shot_planner.motion_score import (                        # noqa: E402
    CLIP_MOTION_UNMEASURABLE, SPATIAL_GRID, MotionScoreError,
)

FAILS = []
W, H = SPATIAL_GRID


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _grids(w=W, h=H):
    """Two DC-removed, non-periodic grids of the requested shape."""
    a = [90.0 + 70.0 * math.sin(0.23 * x + 0.11 * y)
         + 40.0 * math.cos(0.31 * y + 0.05 * x)
         for y in range(h) for x in range(w)]
    b = [0.9 * v + 3.0 for v in a]
    return ms._dc(a)[0], ms._dc(b)[0]


def _probe_reads(a, b, w, h, dx, dy):
    """Run _affine_residual counting _bilinear calls whose 2x2 window leaves
    the grid. Returns (out_of_range_calls, exception_name_or_None)."""
    bad = {"n": 0}
    orig = ms._bilinear

    def probe(g, gw, x, y):
        x0 = int(x // 1)
        y0 = int(y // 1)
        if x0 < 0 or y0 < 0 or x0 + 1 >= gw or y0 + 1 >= len(g) // gw:
            bad["n"] += 1
        return orig(g, gw, x, y)

    raised = None
    ms._bilinear = probe
    try:
        ms._affine_residual(a, b, w, h, dx, dy)
    except Exception as exc:                                  # noqa: BLE001
        raised = type(exc).__name__
    finally:
        ms._bilinear = orig
    return bad["n"], raised


def test_no_out_of_range_residual_reads():
    """The control: zero out-of-range reads for dy = 6.25, 7.75, 9.00.

    Unmodified code measured 46, 92 and 138; dy = -6.25 raised IndexError.
    """
    base, other = _grids()
    results = {}
    for dy in (6.25, 7.75, 9.00, -6.25):
        n, raised = _probe_reads(base, other, W, H, 0.0, dy)
        results[dy] = (n, raised)
        check("zero out-of-range reads at dy=%+.2f" % dy,
              n == 0 and raised is None,
              "%d out-of-range call(s), raised=%r" % (n, raised))
    assert all(n == 0 and raised is None
               for n, raised in results.values()), results


def test_clamp_keeps_the_safe_window():
    """Inside the sampling radius the clamp must not shrink the map."""
    base, other = _grids()
    for dx, dy in ((0.0, 0.0), (2.0, -3.0), (5.0, 5.0), (-5.0, 5.0)):
        _, rows = ms._affine_residual(base, other, W, H, dx, dy)
        bx = min(int(math.floor(abs(dx))) + 1, W // 4)
        by = min(int(math.floor(abs(dy))) + 1, H // 4)
        ok = len(rows) == H - 2 * by and len(rows[0]) == W - 2 * bx
        check("window unchanged at dx=%r dy=%r" % (dx, dy), ok,
              "%dx%d vs %dx%d" % (len(rows[0]), len(rows),
                                  W - 2 * bx, H - 2 * by))
        assert ok


def test_unsamplable_shift_is_refused():
    """A shift whose window cannot exist refuses typed, never aliases."""
    small_a, small_b = _grids(8, 8)
    code = None
    try:
        ms._affine_residual(small_a, small_b, 8, 8, 9.25, 0.0)
    except MotionScoreError as exc:
        code = exc.code
    check("an unsamplable shift refuses with %s" % CLIP_MOTION_UNMEASURABLE,
          code == CLIP_MOTION_UNMEASURABLE, repr(code))
    assert code == CLIP_MOTION_UNMEASURABLE


def main():
    for fn in (test_no_out_of_range_residual_reads,
               test_clamp_keeps_the_safe_window,
               test_unsamplable_shift_is_refused):
        try:
            fn()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % getattr(fn, "__name__", "test"), False,
                  "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        print("D3 wraparound control FAILED: %s" % ", ".join(FAILS))
        return 1
    print("all D3 wraparound control checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
