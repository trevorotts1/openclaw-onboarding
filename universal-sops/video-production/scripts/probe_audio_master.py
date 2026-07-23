#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_audio_master.py — fail-closed loudness/true-peak gate for the Fish Audio master
and the final voice/music mix (Personal Video Creator cluster, universal-sops/video-production).
HARD-FAILS (AF-PVC-AUDIO) unless:
  * integrated loudness within target +/- tolerance (default -16 +/- 1 LUFS)
  * true peak <= target (default -1.5 dBTP)
  * sample rate == expected (default 48000)
Measures via `ffmpeg -af ebur128=peak=true` when given a file, or accepts explicit values.
Exit 0 pass, 2 violation, 3 usage/fail-closed.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

EXIT_OK, EXIT_VIOLATION, EXIT_FAILCLOSED = 0, 2, 3


def _measure(path: Path) -> Tuple[Optional[float], Optional[float]]:
    """Return (integrated_lufs, true_peak_dbtp) via ffmpeg ebur128, or (None, None)."""
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path),
         "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True, timeout=300,
    )
    text = out.stderr
    integ = None
    peak = None
    # Summary block: "I: -16.0 LUFS" and "Peak: -1.5 dBFS"
    m = re.search(r"I:\s*(-?[0-9.]+)\s*LUFS", text)
    if m:
        integ = float(m.group(1))
    m = re.search(r"Peak:\s*(-?[0-9.]+)\s*dBFS", text)
    if m:
        peak = float(m.group(1))
    return integ, peak


def _sample_rate(path: Path) -> Optional[int]:
    if not shutil.which("ffprobe"):
        return None
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    try:
        return int(out.stdout.strip())
    except ValueError:
        return None


def verify(integrated_lufs: Optional[float], true_peak: Optional[float],
           sample_rate: Optional[int] = None,
           target_lufs: float = -16.0, lufs_tol: float = 1.0,
           tp_limit: float = -1.5, expected_sr: int = 48000) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    notes: List[str] = []
    if integrated_lufs is None:
        violations.append(("AF-PVC-AUDIO", "integrated loudness not measured"))
    elif abs(integrated_lufs - target_lufs) > lufs_tol:
        violations.append(("AF-PVC-AUDIO",
                           f"integrated loudness {integrated_lufs:.1f} LUFS outside {target_lufs}+/-{lufs_tol}"))
    else:
        notes.append(f"integrated {integrated_lufs:.1f} LUFS")

    if true_peak is None:
        violations.append(("AF-PVC-AUDIO", "true peak not measured"))
    elif true_peak > tp_limit:
        violations.append(("AF-PVC-AUDIO", f"true peak {true_peak:.1f} dBTP > {tp_limit} dBTP"))
    else:
        notes.append(f"true peak {true_peak:.1f} dBTP")

    if sample_rate is not None and sample_rate != expected_sr:
        violations.append(("AF-PVC-AUDIO", f"sample rate {sample_rate} != {expected_sr}"))

    return violations, notes


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: loudness/true-peak within target.")
        return
    print(f"FAIL: {len(violations)} audio violation(s).")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


def run_self_test() -> int:
    ok = True
    v, _ = verify(-16.0, -1.5, 48000)
    if v:
        ok = False
        print(f"SELF-TEST FAIL: on-target -> {v}")
    else:
        print("SELF-TEST ok: on-target -> PASS")

    v, _ = verify(-16.5, -2.0, 48000)  # within tol
    if v:
        ok = False
        print(f"SELF-TEST FAIL: within-tol -> {v}")
    else:
        print("SELF-TEST ok: within-tol -> PASS")

    v, _ = verify(-13.0, -1.5, 48000)  # too loud
    if not any("loudness" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: too-loud -> {v}")
    else:
        print("SELF-TEST ok: too-loud -> AF-PVC-AUDIO")

    v, _ = verify(-16.0, -0.5, 48000)  # peak too high
    if not any("true peak" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: peak -> {v}")
    else:
        print("SELF-TEST ok: peak -> AF-PVC-AUDIO")

    v, _ = verify(-16.0, -1.5, 44100)  # wrong sr
    if not any("sample rate" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: sr -> {v}")
    else:
        print("SELF-TEST ok: sr -> AF-PVC-AUDIO")

    v, _ = verify(None, None)
    if {c for c, _ in v} != {"AF-PVC-AUDIO"}:
        ok = False
        print(f"SELF-TEST FAIL: unmeasured -> {v}")
    else:
        print("SELF-TEST ok: unmeasured -> AF-PVC-AUDIO")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed loudness/true-peak gate.")
    ap.add_argument("--audio", help="path to the master/mix audio file (measured via ebur128)")
    ap.add_argument("--integrated-lufs", type=float)
    ap.add_argument("--true-peak", type=float)
    ap.add_argument("--target-lufs", type=float, default=-16.0)
    ap.add_argument("--lufs-tol", type=float, default=1.0)
    ap.add_argument("--tp-limit", type=float, default=-1.5)
    ap.add_argument("--expected-sr", type=int, default=48000)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()

    integ = args.integrated_lufs
    peak = args.true_peak
    sr = None
    if args.audio:
        if not shutil.which("ffmpeg"):
            print("USAGE/IO ERROR: ffmpeg not found on PATH.")
            return EXIT_FAILCLOSED
        integ, peak = _measure(Path(args.audio))
        sr = _sample_rate(Path(args.audio))
    if integ is None and peak is None:
        print("USAGE ERROR: pass --audio or --integrated-lufs/--true-peak (or --self-test).")
        return EXIT_FAILCLOSED
    violations, notes = verify(integ, peak, sr, args.target_lufs, args.lufs_tol, args.tp_limit, args.expected_sr)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
