#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_video_clip.py — fail-closed technical QC for a raw Agnes clip (Personal Video
Creator cluster, universal-sops/video-production). ffprobes the clip and HARD-FAILS
(AF-PVC-CLIP-TECH) unless it matches the project spec:
  * orientation/resolution (width x height) matches the expected canvas
  * constant frame rate (r_frame_rate == avg_frame_rate)
  * frame rate == expected fps
  * duration >= required_video_duration - 0.05s
  * a video stream exists
Requires ffprobe on PATH. Exit 0 pass, 2 violation, 3 usage/fail-closed.
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
           required_duration: float) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    vstreams = [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]
    if not vstreams:
        violations.append(("AF-PVC-CLIP-TECH", "no video stream found"))
        return violations, []
    v = vstreams[0]

    w = int(v.get("width", 0))
    h = int(v.get("height", 0))
    if (w, h) != (width, height):
        violations.append(("AF-PVC-CLIP-TECH", f"resolution {w}x{h} != expected {width}x{height}"))

    rfr = _ratio(str(v.get("r_frame_rate", "0/1")))
    afr = _ratio(str(v.get("avg_frame_rate", "0/1")))
    if rfr and afr and abs(rfr - afr) > 0.5:
        violations.append(("AF-PVC-CLIP-TECH", f"variable frame rate (r={rfr:.3f} avg={afr:.3f}) — convert to CFR"))
    if rfr and abs(rfr - fps) > 0.5:
        violations.append(("AF-PVC-CLIP-TECH", f"frame rate {rfr:.3f} != expected {fps}"))

    dur = float(probe.get("format", {}).get("duration", 0) or 0)
    if required_duration and dur + DUR_TOL < required_duration:
        violations.append(("AF-PVC-CLIP-TECH",
                           f"duration {dur:.3f}s < required {required_duration:.3f}s"))

    return violations, [f"clip {w}x{h} @ {rfr:.3f}fps, {dur:.3f}s"]


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: clip matches the project technical spec.")
        return
    print(f"FAIL: {len(violations)} clip violation(s) — reject before lip-sync.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


def run_self_test() -> int:
    ok = True
    good = {"streams": [{"codec_type": "video", "width": 1080, "height": 1920,
                         "r_frame_rate": "24/1", "avg_frame_rate": "24/1"}],
            "format": {"duration": "9.300"}}
    v, _ = verify(good, 1080, 1920, 24, 9.290)
    if v:
        ok = False
        print(f"SELF-TEST FAIL: good -> {v}")
    else:
        print("SELF-TEST ok: good -> PASS")

    wrongres = {"streams": [{"codec_type": "video", "width": 1920, "height": 1080,
                             "r_frame_rate": "24/1", "avg_frame_rate": "24/1"}],
                "format": {"duration": "9.300"}}
    v, _ = verify(wrongres, 1080, 1920, 24, 9.290)
    if not any("resolution" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: wrong-res -> {v}")
    else:
        print("SELF-TEST ok: wrong-res -> AF-PVC-CLIP-TECH")

    vfr = {"streams": [{"codec_type": "video", "width": 1080, "height": 1920,
                        "r_frame_rate": "30/1", "avg_frame_rate": "24/1"}],
           "format": {"duration": "9.300"}}
    v, _ = verify(vfr, 1080, 1920, 24, 9.290)
    if not any("variable frame rate" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: vfr -> {v}")
    else:
        print("SELF-TEST ok: vfr -> AF-PVC-CLIP-TECH")

    short = {"streams": [{"codec_type": "video", "width": 1080, "height": 1920,
                          "r_frame_rate": "24/1", "avg_frame_rate": "24/1"}],
             "format": {"duration": "5.000"}}
    v, _ = verify(short, 1080, 1920, 24, 9.290)
    if not any("duration" in m for _, m in v):
        ok = False
        print(f"SELF-TEST FAIL: short -> {v}")
    else:
        print("SELF-TEST ok: short -> AF-PVC-CLIP-TECH")

    novid = {"streams": [{"codec_type": "audio"}], "format": {"duration": "9.3"}}
    v, _ = verify(novid, 1080, 1920, 24, 9.290)
    if {c for c, _ in v} != {"AF-PVC-CLIP-TECH"}:
        ok = False
        print(f"SELF-TEST FAIL: no-video -> {v}")
    else:
        print("SELF-TEST ok: no-video -> AF-PVC-CLIP-TECH")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed raw-clip technical QC (ffprobe).")
    ap.add_argument("--clip", help="path to the clip")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--required-duration", type=float, default=0.0)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()
    if not shutil.which("ffprobe"):
        print("USAGE/IO ERROR: ffprobe not found on PATH.")
        return EXIT_FAILCLOSED
    if not args.clip or not Path(args.clip).exists():
        print(f"USAGE/IO ERROR: clip not found ({args.clip}).")
        return EXIT_FAILCLOSED
    try:
        probe = _ffprobe(Path(args.clip))
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: {exc}")
        return EXIT_FAILCLOSED
    violations, notes = verify(probe, args.width, args.height, args.fps, args.required_duration)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
