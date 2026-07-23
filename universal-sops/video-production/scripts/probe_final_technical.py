#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_final_technical.py — fail-closed technical QC for the delivered master MP4
(Personal Video Creator cluster, universal-sops/video-production). ffprobes the file and
HARD-FAILS (AF-PVC-FINAL-TECH) unless it meets the delivery spec:
  * resolution == expected (width x height)
  * video codec == h264, pixel format == yuv420p
  * constant frame rate == expected fps
  * audio stream present, codec aac, sample rate == expected (48000)
  * exactly one video + one audio stream (no unintended extra streams)
  * duration within tolerance of the expected master duration (when supplied)
Requires ffprobe. Exit 0 pass, 2 violation, 3 usage/fail-closed.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

EXIT_OK, EXIT_VIOLATION, EXIT_FAILCLOSED = 0, 2, 3
DUR_TOL = 0.05


def _ffprobe(path: Path) -> Dict[str, Any]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {out.stderr.strip()[:300]}")
    return json.loads(out.stdout)


def _ratio(s: str) -> float:
    try:
        num, _, den = s.partition("/")
        den = float(den)
        return float(num) / den if den else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def verify(probe: Dict[str, Any], width: int, height: int, fps: int,
           expected_duration: float, expected_sr: int = 48000) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    streams = probe.get("streams", [])
    vstreams = [s for s in streams if s.get("codec_type") == "video"]
    astreams = [s for s in streams if s.get("codec_type") == "audio"]
    others = [s for s in streams if s.get("codec_type") not in ("video", "audio")]

    if len(vstreams) != 1:
        violations.append(("AF-PVC-FINAL-TECH", f"expected exactly 1 video stream, found {len(vstreams)}"))
    if len(astreams) != 1:
        violations.append(("AF-PVC-FINAL-TECH", f"expected exactly 1 audio stream, found {len(astreams)}"))
    if others:
        violations.append(("AF-PVC-FINAL-TECH", f"{len(others)} unintended extra stream(s) present"))

    if vstreams:
        v = vstreams[0]
        w, h = int(v.get("width", 0)), int(v.get("height", 0))
        if (w, h) != (width, height):
            violations.append(("AF-PVC-FINAL-TECH", f"resolution {w}x{h} != expected {width}x{height}"))
        if str(v.get("codec_name", "")).lower() != "h264":
            violations.append(("AF-PVC-FINAL-TECH", f"video codec '{v.get('codec_name')}' != h264"))
        if str(v.get("pix_fmt", "")) != "yuv420p":
            violations.append(("AF-PVC-FINAL-TECH", f"pixel format '{v.get('pix_fmt')}' != yuv420p"))
        rfr = _ratio(str(v.get("r_frame_rate", "0/1")))
        afr = _ratio(str(v.get("avg_frame_rate", "0/1")))
        if rfr and afr and abs(rfr - afr) > 0.5:
            violations.append(("AF-PVC-FINAL-TECH", f"variable frame rate (r={rfr:.3f} avg={afr:.3f})"))
        if rfr and abs(rfr - fps) > 0.5:
            violations.append(("AF-PVC-FINAL-TECH", f"frame rate {rfr:.3f} != expected {fps}"))

    if astreams:
        a = astreams[0]
        if str(a.get("codec_name", "")).lower() != "aac":
            violations.append(("AF-PVC-FINAL-TECH", f"audio codec '{a.get('codec_name')}' != aac"))
        sr = a.get("sample_rate")
        if sr is not None and int(sr) != expected_sr:
            violations.append(("AF-PVC-FINAL-TECH", f"audio sample rate {sr} != {expected_sr}"))

    if expected_duration:
        dur = float(probe.get("format", {}).get("duration", 0) or 0)
        if abs(dur - expected_duration) > DUR_TOL:
            violations.append(("AF-PVC-FINAL-TECH",
                               f"duration {dur:.3f}s != expected master {expected_duration:.3f}s (tol {DUR_TOL}s)"))

    return violations, [f"{len(vstreams)} video / {len(astreams)} audio stream(s)"]


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: final master meets the delivery technical spec.")
        return
    print(f"FAIL: {len(violations)} final-technical violation(s).")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


def run_self_test() -> int:
    ok = True
    good = {"streams": [
        {"codec_type": "video", "width": 1080, "height": 1920, "codec_name": "h264",
         "pix_fmt": "yuv420p", "r_frame_rate": "24/1", "avg_frame_rate": "24/1"},
        {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000"},
    ], "format": {"duration": "59.840"}}
    v, _ = verify(good, 1080, 1920, 24, 59.840)
    if v:
        ok = False
        print(f"SELF-TEST FAIL: good -> {v}")
    else:
        print("SELF-TEST ok: good -> PASS")

    badcodec = {"streams": [
        {"codec_type": "video", "width": 1080, "height": 1920, "codec_name": "hevc",
         "pix_fmt": "yuv420p", "r_frame_rate": "24/1", "avg_frame_rate": "24/1"},
        {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000"},
    ], "format": {"duration": "59.840"}}
    v, _ = verify(badcodec, 1080, 1920, 24, 59.840)
    if not any("video codec" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: bad-codec -> {v}")
    else:
        print("SELF-TEST ok: bad-codec -> AF-PVC-FINAL-TECH")

    noaudio = {"streams": [
        {"codec_type": "video", "width": 1080, "height": 1920, "codec_name": "h264",
         "pix_fmt": "yuv420p", "r_frame_rate": "24/1", "avg_frame_rate": "24/1"},
    ], "format": {"duration": "59.840"}}
    v, _ = verify(noaudio, 1080, 1920, 24, 59.840)
    if not any("audio stream" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: no-audio -> {v}")
    else:
        print("SELF-TEST ok: no-audio -> AF-PVC-FINAL-TECH")

    extra = {"streams": [
        {"codec_type": "video", "width": 1080, "height": 1920, "codec_name": "h264",
         "pix_fmt": "yuv420p", "r_frame_rate": "24/1", "avg_frame_rate": "24/1"},
        {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000"},
        {"codec_type": "data", "codec_name": "bin_data"},
    ], "format": {"duration": "59.840"}}
    v, _ = verify(extra, 1080, 1920, 24, 59.840)
    if not any("extra stream" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: extra-stream -> {v}")
    else:
        print("SELF-TEST ok: extra-stream -> AF-PVC-FINAL-TECH")

    wrongsr = {"streams": [
        {"codec_type": "video", "width": 1080, "height": 1920, "codec_name": "h264",
         "pix_fmt": "yuv420p", "r_frame_rate": "24/1", "avg_frame_rate": "24/1"},
        {"codec_type": "audio", "codec_name": "aac", "sample_rate": "44100"},
    ], "format": {"duration": "59.840"}}
    v, _ = verify(wrongsr, 1080, 1920, 24, 59.840)
    if not any("sample rate" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: wrong-sr -> {v}")
    else:
        print("SELF-TEST ok: wrong-sr -> AF-PVC-FINAL-TECH")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed final-master technical QC (ffprobe).")
    ap.add_argument("--master", help="path to 12_delivery/final_master.mp4")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--expected-duration", type=float, default=0.0)
    ap.add_argument("--expected-sr", type=int, default=48000)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()
    if not shutil.which("ffprobe"):
        print("USAGE/IO ERROR: ffprobe not found on PATH.")
        return EXIT_FAILCLOSED
    if not args.master or not Path(args.master).exists():
        print(f"USAGE/IO ERROR: master not found ({args.master}).")
        return EXIT_FAILCLOSED
    try:
        probe = _ffprobe(Path(args.master))
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: {exc}")
        return EXIT_FAILCLOSED
    violations, notes = verify(probe, args.width, args.height, args.fps,
                               args.expected_duration, args.expected_sr)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
