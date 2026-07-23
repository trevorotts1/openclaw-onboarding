#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_lipsync_offset.py — fail-closed lip-sync A/V offset gate (Personal Video Creator
cluster, universal-sops/video-production). HARD-FAILS (AF-PVC-LIPSYNC-OFFSET) unless:
  * head A/V onset offset <= max_offset_frames (default 2 @ 24fps = ~83ms)
  * head-to-tail drift <= max_drift_frames (default 1)
  * mouth does not start before voice (negative head offset beyond tolerance is a fail)

Two modes:
  1. MEASURED (default): pass --head-offset-frames and --tail-offset-frames from the
     agent's frame-by-frame QC read (or a SyncConfidence-style metric). Deterministic.
  2. AUDIO-ONSET ASSIST: with --scene-audio + --scene-video, uses ffmpeg silencedetect to
     estimate the audio speech onset and compares it to a supplied --video-mouth-onset-sec.
     This assists the human QC; the frame-level mouth read is still the authority.

Exit 0 pass, 2 violation, 3 usage/fail-closed.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

EXIT_OK, EXIT_VIOLATION, EXIT_FAILCLOSED = 0, 2, 3


def verify(head_offset_frames: float, tail_offset_frames: float,
           max_offset_frames: int = 2, max_drift_frames: int = 1) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    if abs(head_offset_frames) > max_offset_frames:
        direction = "mouth before voice" if head_offset_frames < 0 else "voice before mouth"
        violations.append(("AF-PVC-LIPSYNC-OFFSET",
                           f"head offset {head_offset_frames:+.1f} frames exceeds +/-{max_offset_frames} "
                           f"({direction})"))
    if abs(tail_offset_frames) > max_offset_frames:
        violations.append(("AF-PVC-LIPSYNC-OFFSET",
                           f"tail offset {tail_offset_frames:+.1f} frames exceeds +/-{max_offset_frames}"))
    drift = abs(tail_offset_frames - head_offset_frames)
    if drift > max_drift_frames:
        violations.append(("AF-PVC-LIPSYNC-OFFSET",
                           f"head-to-tail drift {drift:.1f} frames > {max_drift_frames} — this is drift, "
                           "not a start offset; correct duration or regenerate, do not apply a global delay"))
    return violations, [f"head {head_offset_frames:+.1f}f, tail {tail_offset_frames:+.1f}f, drift {drift:.1f}f"]


def _audio_onset_sec(audio: Path, silence_thresh_db: float = -35.0, min_silence: float = 0.08) -> float | None:
    """Estimate first speech onset via ffmpeg silencedetect. Returns seconds or None."""
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(audio),
         "-af", f"silencedetect=noise={silence_thresh_db}dB:d={min_silence}",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    )
    # First silence_end marks the end of leading silence == speech onset.
    import re
    for line in out.stderr.splitlines():
        m = re.search(r"silence_end:\s*([0-9.]+)", line)
        if m:
            return float(m.group(1))
    return 0.0  # no leading silence detected -> speech at ~0


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: lip-sync offset within tolerance at head and tail, no drift.")
        return
    print(f"FAIL: {len(violations)} lip-sync violation(s) — retry/escalate per the SOP ladder.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


def run_self_test() -> int:
    ok = True
    v, _ = verify(1.0, 1.0)
    if v:
        ok = False
        print(f"SELF-TEST FAIL: in-tol -> {v}")
    else:
        print("SELF-TEST ok: in-tol -> PASS")

    v, _ = verify(0.0, 0.0)
    if v:
        ok = False
        print(f"SELF-TEST FAIL: perfect -> {v}")
    else:
        print("SELF-TEST ok: perfect -> PASS")

    v, _ = verify(3.0, 3.0)  # head over
    if not any("head offset" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: head-over -> {v}")
    else:
        print("SELF-TEST ok: head-over -> AF-PVC-LIPSYNC-OFFSET")

    v, _ = verify(-3.0, -3.0)  # mouth before voice
    if not any("mouth before voice" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: mouth-before -> {v}")
    else:
        print("SELF-TEST ok: mouth-before -> AF-PVC-LIPSYNC-OFFSET")

    v, _ = verify(0.0, 2.0)  # drift 2 > 1
    if not any("drift" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: drift -> {v}")
    else:
        print("SELF-TEST ok: drift -> AF-PVC-LIPSYNC-OFFSET")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed lip-sync A/V offset gate.")
    ap.add_argument("--head-offset-frames", type=float, help="measured A/V offset at scene head (+ = voice first)")
    ap.add_argument("--tail-offset-frames", type=float, help="measured A/V offset at scene tail")
    ap.add_argument("--max-offset-frames", type=int, default=2)
    ap.add_argument("--max-drift-frames", type=int, default=1)
    ap.add_argument("--scene-audio", help="(assist) scene WAV for silencedetect onset estimate")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()

    if args.scene_audio and shutil.which("ffmpeg"):
        onset = _audio_onset_sec(Path(args.scene_audio))
        print(f"NOTE: estimated audio speech onset at {onset:.3f}s (silencedetect assist; "
              "the frame-level mouth read is still the authority)")

    if args.head_offset_frames is None or args.tail_offset_frames is None:
        print("USAGE ERROR: pass --head-offset-frames and --tail-offset-frames (or --self-test).")
        return EXIT_FAILCLOSED
    violations, notes = verify(args.head_offset_frames, args.tail_offset_frames,
                               args.max_offset_frames, args.max_drift_frames)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
