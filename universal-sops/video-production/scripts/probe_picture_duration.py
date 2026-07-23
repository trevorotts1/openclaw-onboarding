#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_picture_duration.py — fail-closed picture/audio duration match (Personal Video
Creator cluster, universal-sops/video-production). ffprobes the assembled picture and the
master audio and HARD-FAILS (AF-PVC-DURATION) unless
    abs(video_duration - audio_duration) <= 1 frame
(1 frame = 1/fps; 0.041667s at 24fps). Requires ffprobe. Exit 0 pass, 2 violation, 3 usage.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

EXIT_OK, EXIT_VIOLATION, EXIT_FAILCLOSED = 0, 2, 3


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {out.stderr.strip()[:300]}")
    return float(out.stdout.strip())


def verify(video_duration: float, audio_duration: float, fps: int = 24,
           tolerance_frames: int = 1) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    frame = 1.0 / fps
    tol = tolerance_frames * frame
    diff = abs(video_duration - audio_duration)
    if diff > tol:
        violations.append(("AF-PVC-DURATION",
                           f"|video {video_duration:.4f}s - audio {audio_duration:.4f}s| = {diff:.4f}s "
                           f"> {tolerance_frames} frame ({tol:.4f}s @ {fps}fps)"))
    return violations, [f"video {video_duration:.4f}s, audio {audio_duration:.4f}s, diff {diff:.4f}s (tol {tol:.4f}s)"]


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: picture duration matches the master audio within 1 frame.")
        return
    print(f"FAIL: {len(violations)} duration violation(s).")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


def run_self_test() -> int:
    ok = True
    v, _ = verify(59.840, 59.840)
    if v:
        ok = False
        print(f"SELF-TEST FAIL: exact -> {v}")
    else:
        print("SELF-TEST ok: exact -> PASS")

    v, _ = verify(59.860, 59.840)  # 0.02s < 0.0417 frame
    if v:
        ok = False
        print(f"SELF-TEST FAIL: within-frame -> {v}")
    else:
        print("SELF-TEST ok: within-frame -> PASS")

    v, _ = verify(60.200, 59.840)  # 0.36s >> 1 frame
    if {c for c, _ in v} != {"AF-PVC-DURATION"}:
        ok = False
        print(f"SELF-TEST FAIL: off -> {v}")
    else:
        print("SELF-TEST ok: off -> AF-PVC-DURATION")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed picture/audio duration match (ffprobe).")
    ap.add_argument("--picture", help="path to the assembled picture MP4")
    ap.add_argument("--audio", help="path to the master audio")
    ap.add_argument("--video-duration", type=float)
    ap.add_argument("--audio-duration", type=float)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--tolerance-frames", type=int, default=1)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()

    vdur = args.video_duration
    adur = args.audio_duration
    if vdur is None and args.picture:
        if not shutil.which("ffprobe"):
            print("USAGE/IO ERROR: ffprobe not found on PATH.")
            return EXIT_FAILCLOSED
        vdur = _duration(Path(args.picture))
    if adur is None and args.audio:
        if not shutil.which("ffprobe"):
            print("USAGE/IO ERROR: ffprobe not found on PATH.")
            return EXIT_FAILCLOSED
        adur = _duration(Path(args.audio))
    if vdur is None or adur is None:
        print("USAGE ERROR: pass --picture/--audio or --video-duration/--audio-duration (or --self-test).")
        return EXIT_FAILCLOSED
    violations, notes = verify(vdur, adur, args.fps, args.tolerance_frames)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
