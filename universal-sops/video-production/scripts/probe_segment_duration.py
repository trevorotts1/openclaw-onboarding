#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_segment_duration.py — fail-closed scene-WAV duration validator (Personal Video
Creator cluster, universal-sops/video-production). ffprobes an extracted scene WAV and
HARD-FAILS (AF-PVC-SEGMENT-DUR) unless its duration equals audio_end - audio_start within
+/-0.05s (minimal container rounding). Requires ffprobe. Exit 0 pass, 2 violation, 3 usage.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

EXIT_OK, EXIT_VIOLATION, EXIT_FAILCLOSED = 0, 2, 3
TOL = 0.05


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {out.stderr.strip()[:300]}")
    return float(out.stdout.strip())


def verify(duration: float, audio_start: float, audio_end: float) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    expected = audio_end - audio_start
    if abs(duration - expected) > TOL:
        violations.append(("AF-PVC-SEGMENT-DUR",
                           f"segment duration {duration:.3f}s != audio_end-audio_start {expected:.3f}s "
                           f"(tol {TOL}s) — re-extract from the master"))
    return violations, [f"segment {duration:.3f}s, expected {expected:.3f}s"]


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: segment duration matches audio_end - audio_start.")
        return
    print(f"FAIL: {len(violations)} segment-duration violation(s).")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


def run_self_test() -> int:
    ok = True
    v, _ = verify(8.740, 0.000, 8.740)
    if v:
        ok = False
        print(f"SELF-TEST FAIL: exact -> {v}")
    else:
        print("SELF-TEST ok: exact -> PASS")

    v, _ = verify(8.760, 0.000, 8.740)  # within tol
    if v:
        ok = False
        print(f"SELF-TEST FAIL: within-tol -> {v}")
    else:
        print("SELF-TEST ok: within-tol -> PASS")

    v, _ = verify(9.500, 0.000, 8.740)
    if {c for c, _ in v} != {"AF-PVC-SEGMENT-DUR"}:
        ok = False
        print(f"SELF-TEST FAIL: too-long -> {v}")
    else:
        print("SELF-TEST ok: too-long -> AF-PVC-SEGMENT-DUR")

    v, _ = verify(5.000, 14.900, 25.480)
    if {c for c, _ in v} != {"AF-PVC-SEGMENT-DUR"}:
        ok = False
        print(f"SELF-TEST FAIL: too-short -> {v}")
    else:
        print("SELF-TEST ok: too-short -> AF-PVC-SEGMENT-DUR")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed scene-WAV duration validator (ffprobe).")
    ap.add_argument("--segment", help="path to the scene WAV")
    ap.add_argument("--audio-start", type=float)
    ap.add_argument("--audio-end", type=float)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()
    if not shutil.which("ffprobe"):
        print("USAGE/IO ERROR: ffprobe not found on PATH.")
        return EXIT_FAILCLOSED
    if not args.segment or not Path(args.segment).exists():
        print(f"USAGE/IO ERROR: segment not found ({args.segment}).")
        return EXIT_FAILCLOSED
    if args.audio_start is None or args.audio_end is None:
        print("USAGE ERROR: pass --audio-start and --audio-end.")
        return EXIT_FAILCLOSED
    try:
        dur = _duration(Path(args.segment))
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: {exc}")
        return EXIT_FAILCLOSED
    violations, notes = verify(dur, args.audio_start, args.audio_end)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
