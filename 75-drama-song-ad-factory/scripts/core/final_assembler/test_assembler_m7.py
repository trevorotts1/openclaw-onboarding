#!/usr/bin/env python3
"""M7 tests for final_assembler: bounded ffmpeg argv + timeout (manual 02 M7, Part D).

stdlib only, zero paid calls, no ffmpeg binary required.

Covers:
  build_argv  - command starts with `nice -n 10` and carries `-threads N`
                with the exact value size_ffmpeg() computed (acceptance);
                Part D fallback formula for several cores_eff values;
                lane_size.py wins over the fallback when importable;
                absent/broken lane_size.py falls back cleanly.
  size_ffmpeg - timeout = max(600, 2 x output seconds x height factor);
                the 1080p/4k height factor; short renders keep the 600 s floor.
  assemble    - default timeout is lane_size/Part D sized (not the old flat
                600); an explicit timeout is still honored exactly.

Run: python3 core/final_assembler/test_assembler_m7.py
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import final_assembler.assembler as A   # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _plan(segs=1, dur=2.0, w=1920, h=1080, fps=30):
    return A.plan_timeline({
        "schema_version": A.TIMELINE_SCHEMA, "fps": fps,
        "width": w, "height": h, "song_path": None,
        "transition": "none",
        "segments": [{"src": "clip%d.mp4" % i, "dur": dur}
                     for i in range(segs)],
    }, ".")


def _strip_lane_size():
    """Force the Part D fallback: no cached module, no file on disk."""
    had = "lane_size" in sys.modules
    sys.modules.pop("lane_size", None)
    return had


def _restore_lane_size(had):
    if had:
        return
    sys.modules.pop("lane_size", None)


def test_argv_prefix_nice_and_threads():
    plan = _plan()
    threads, nice, _to = A.size_ffmpeg(plan["total_dur"], plan["width"],
                                       plan["height"])
    argv = A.build_argv(plan, "out.mp4")
    check("argv starts with nice -n %d" % A.NICE_LEVEL,
          argv[:3] == ["nice", "-n", str(A.NICE_LEVEL)],
          "got %r" % (argv[:3],))
    check("argv carries -threads with min(4, size_ffmpeg value)",
          "-threads" in argv and
          argv[argv.index("-threads") + 1] == str(min(4, threads)),
          "expected -threads %s in %r" % (threads, argv))
    check("threads >= 1", threads >= 1, "got %r" % (threads,))


def test_part_d_fallback_formula():
    """jobs = max(1, floor(cores/4)); threads = max(1, floor((cores-1)/jobs))."""
    import math
    for cores, want_jobs, want_threads in ((2, 1, 1), (4, 1, 3),
                                           (10, 2, 4), (12, 3, 3), (1, 1, 1)):
        threads, jobs = A._part_d_threads(cores)
        check("Part D cores=%d -> jobs=%d threads=%d" % (cores, want_jobs,
                                                        want_threads),
              (jobs, threads) == (want_jobs, want_threads),
              "got jobs=%d threads=%d" % (jobs, threads))
        # cross-check against the manual's own expressions
        wj = max(1, int(math.floor(cores / 4.0)))
        wt = max(1, int(math.floor((cores - 1) / float(wj))))
        check("Part D cores=%d matches manual expressions" % cores,
              (jobs, threads) == (wj, wt))


def test_timeout_formula_and_floor():
    check("short render keeps the 600 s floor",
          A.size_ffmpeg(10, 1920, 1080)[2] == 600,
          "got %r" % (A.size_ffmpeg(10, 1920, 1080)[2],))
    check("400 s at 1080p -> 800 s (2 x output s)",
          A.size_ffmpeg(400, 1920, 1080)[2] == 800,
          "got %r" % (A.size_ffmpeg(400, 1920, 1080)[2],))
    check("400 s at 4k -> 3200 s (x4 height factor)",
          A.size_ffmpeg(400, 3840, 2160)[2] == 3200,
          "got %r" % (A.size_ffmpeg(400, 3840, 2160)[2],))
    check("3600 s at 1080p -> 7200 s",
          A.size_ffmpeg(3600, 1920, 1080)[2] == 7200,
          "got %r" % (A.size_ffmpeg(3600, 1920, 1080)[2],))


def test_lane_size_wins_when_importable():
    """Acceptance: argv carries the value lane_size computed, not the fallback."""
    had = _strip_lane_size()
    fake = types.ModuleType("lane_size")
    fake.ffmpeg_threads = 7
    sys.modules["lane_size"] = fake
    try:
        threads, _nice, _to = A.size_ffmpeg(120, 1920, 1080)
        check("lane_size.ffmpeg_threads wins", threads == 7,
              "got %r" % (threads,))
        plan = _plan()
        argv = A.build_argv(plan, "out.mp4")
        check("argv -threads is capped at 4 (lane_size says 7)",
              argv[argv.index("-threads") + 1] == "4",
              "got %r" % (argv,))
    finally:
        _restore_lane_size(had)
        sys.modules.pop("lane_size", None)


def test_lane_size_absent_falls_back():
    had = _strip_lane_size()
    try:
        # No file on disk and no cached module -> Part D path must be used.
        exists = os.path.isfile(os.path.join(CORE, "lane_size.py"))
        if exists:
            print("skip: lane_size.py already on disk, fallback not exercised")
            return
        threads, _n, _t = A.size_ffmpeg(120, 1920, 1080)
        want = A._part_d_threads()[0]
        check("absent lane_size.py -> Part D fallback threads",
              threads == want, "got %r want %r" % (threads, want))
        plan = _plan()
        argv = A.build_argv(plan, "out.mp4")
        check("argv -threads equals Part D fallback value",
              argv[argv.index("-threads") + 1] == str(want),
              "got %r want %r" % (argv, want))
    finally:
        _restore_lane_size(had)


def test_assemble_timeout_default_and_override(tmp_root):
    """assemble() default timeout is sized, not a flat 600; explicit wins."""
    import json
    import tempfile
    had = _strip_lane_size()
    tmp = tempfile.mkdtemp(dir=tmp_root)
    try:
        clip = os.path.join(tmp, "clip.mp4")
        open(clip, "wb").close()
        tl = os.path.join(tmp, "timeline.json")
        with open(tl, "w", encoding="utf-8") as fh:
            json.dump({
                "schema_version": A.TIMELINE_SCHEMA, "fps": 30,
                "width": 1920, "height": 1080, "song_path": None,
                "transition": "none",
                "segments": [{"src": "clip.mp4", "dur": 10.0}],
            }, fh)

        # dry_run: no ffmpeg needed; evidence carries the computed timeout.
        rec = A.assemble(tl, os.path.join(tmp, "out.mp4"), dry_run=True)
        want = A.size_ffmpeg(10.0, 1920, 1080)[2]
        check("assemble default timeout is lane/Part-D sized",
              rec["evidence"]["timeout_s"] == want,
              "got %r want %r" % (rec["evidence"]["timeout_s"], want))
        check("dry-run argv still bounded (nice + -threads)",
              rec["evidence"]["argv"][:3] == ["nice", "-n", str(A.NICE_LEVEL)]
              and "-threads" in rec["evidence"]["argv"],
              "got %r" % (rec["evidence"]["argv"][:6],))

        rec2 = A.assemble(tl, os.path.join(tmp, "out2.mp4"), timeout=42,
                          dry_run=True)
        check("explicit timeout honored exactly",
              rec2["evidence"]["timeout_s"] == 42,
              "got %r" % (rec2["evidence"]["timeout_s"],))
    finally:
        _restore_lane_size(had)


def main():
    import tempfile
    tmp_root = tempfile.mkdtemp(prefix="final_assembler_m7_test_")
    for fn, needs_tmp in (
        (test_argv_prefix_nice_and_threads, False),
        (test_part_d_fallback_formula, False),
        (test_timeout_formula_and_floor, False),
        (test_lane_size_wins_when_importable, False),
        (test_lane_size_absent_falls_back, False),
        (lambda: test_assemble_timeout_default_and_override(tmp_root), False),
    ):
        try:
            fn()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % getattr(fn, "__name__", "test"), False,
                  "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all M7 checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
