#!/usr/bin/env python3
"""Fault boundary: timing_guard rejects wrong alignment. Stdlib only."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "core"))
import timing_guard as T

LIM = dict(median_max_ms=10, p95_max_ms=50, critical_max_ms=100)


def check(name, fn, code):
    try:
        fn()
    except T.TimingError as e:
        assert e.code == code, "%s: got %s want %s" % (name, e.code, code)
        print("ok: %s (%s)" % (name, code))
        return
    raise AssertionError("FAILED (no raise): %s" % name)


check("median breach rejects",
      lambda: T.check_alignment([100.0] * 10, [], **LIM),
      "TIMING_MEDIAN_EXCEEDED")
check("p95 breach rejects",
      lambda: T.check_alignment([1.0] * 18 + [100.0, 200.0], [], **LIM),
      "TIMING_P95_EXCEEDED")
check("critical breach rejects",
      lambda: T.check_alignment([1.0] * 5, [500.0], **LIM),
      "TIMING_CRITICAL_EXCEEDED")
check("missing sample rejects",
      lambda: T.check_alignment([], [], **LIM), "NO_TIMING_SAMPLE")
check("unordered timestamps reject",
      lambda: T.check_order([{"start": 0.0, "end": 1.0},
                             {"start": 0.5, "end": 2.0}]),
      "UNORDERED_TIMESTAMPS")
check("backward step rejects",
      lambda: T.check_order([{"start": 2.0, "end": 3.0},
                             {"start": 1.0, "end": 1.5}]),
      "UNORDERED_TIMESTAMPS")
check("missing critical word rejects",
      lambda: T.check_coverage([{"text": "midnight train", "critical": True}],
                               ["midnight"]),
      "MISSING_CRITICAL")
check("low overall coverage rejects",
      lambda: T.check_coverage(
          [{"text": "a b c d e f g h i j", "critical": False}], ["a"]),
      "LOW_COVERAGE")
check("drift cascade rejects",
      lambda: T.check_cumulative_drift([0.01] * 5, fps=30, cap_frames=1),
      "DRIFT_CASCADE")
check("AV sync breach rejects",
      lambda: T.check_av_sync(10.0, 10.2, fps=30, max_frames=1),
      "AV_SYNC_EXCEEDED")
check("off-grid stamp rejects",
      lambda: T.check_frame_grid([0.015], 30), "BAD_FRAME_ROUNDING")

ok = T.check_alignment([1.0, 2.0, 3.0], [5.0], **LIM)
assert ok["median_ms"] == 2.0
print("ok: in-tolerance alignment passes")
print("OK test_timing_guard_faults: 12 checks")
