#!/usr/bin/env python3
"""calibrate_book.py: the calibration control the book check must pass first.

Same rule as the lip-sync gate: run the checker on a KNOWN-GOOD clip (a
correct book open made from a real cover) and on the same clip mirrored with
ffmpeg hflip. The check must PASS the first and FAIL the second, or the check
itself is broken and every verdict it returns is UNAVAILABLE.

The control is fixture-driven and offline: the good clip is written locally
from the seeded fixtures (an upright front cover, then a leaf turning right to
left), and the mirrored one is that same file through ffmpeg hflip. Both are
read back from disk by the checker's own frame reader, so a broken reader
fails the control too. Zero network, zero provider spend.

Run (prints the receipt, exits 0 only when the pair sorts correctly):
    python3 scripts/core/book_shot/calibrate_book.py
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

_ghere = os.path.dirname(os.path.abspath(__file__))
if _ghere not in sys.path:
    sys.path.insert(0, _ghere)
_gcore = os.path.abspath(os.path.join(_ghere, ".."))
if _gcore not in sys.path:
    sys.path.insert(0, _gcore)

try:                                    # imported as book_shot.calibrate_book
    from . import book_shot as BS
    from .fixtures import build_fixtures as FIX
except ImportError:                     # run as a plain script
    import book_shot as BS              # type: ignore # noqa: E402
    from fixtures import build_fixtures as FIX  # type: ignore # noqa: E402

TOOL_NAME = "calibrate_book"
TOOL_VERSION = "1.0.0"

class CalibrationError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code

def _write_clip(path, frames, cv2):
    h, w = frames[0].shape[:2]
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 12.0, (w, h))
    if not writer.isOpened():
        raise CalibrationError(BS.BOOK_FRAMES_UNAVAILABLE,
                               "cv2 VideoWriter unavailable for %s" % path)
    try:
        for f in frames:
            writer.write(f)
    finally:
        writer.release()
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise CalibrationError(BS.BOOK_FRAMES_UNAVAILABLE,
                               "cv2 wrote no clip at %s" % path)

def _hflip(src, dst):
    ff = shutil.which("ffmpeg")
    if ff is None:
        raise CalibrationError(BS.BOOK_FRAMES_UNAVAILABLE,
                               "ffmpeg missing: cannot build the hflip control")
    r = subprocess.run([ff, "-y", "-loglevel", "error", "-i", src,
                        "-vf", "hflip", "-crf", "18", dst],
                       capture_output=True, text=True, timeout=180, check=False)
    if r.returncode != 0 or not os.path.isfile(dst):
        raise CalibrationError(BS.BOOK_FRAMES_UNAVAILABLE,
                               "ffmpeg hflip rc=%d: %s"
                               % (r.returncode, r.stderr.strip()[:160]))
    return dst

def calibrate(tmpdir=None, language="en"):
    """Run the control. Returns a receipt dict; a FAIL is a receipt, not a raise."""
    own = tmpdir is None
    tmpdir = tmpdir or tempfile.mkdtemp(prefix="book-cal-")
    try:
        import cv2
        import numpy as np
        fx = FIX.build(tmpdir)
        # Known-good: upright front cover first, then a leaf turning right to
        # left (correct for a left-to-right book).
        frames = [fx["images"]["front_frame"]] + fx["leaf_left"]
        good_clip = os.path.join(tmpdir, "good.mp4")
        _write_clip(good_clip, frames, cv2)
        bad_clip = _hflip(good_clip, os.path.join(tmpdir, "good-hflip.mp4"))
        # Frame 0 is the closed cover (the cover check); the flow window is
        # every frame after it (the turn itself).
        spec = {"language": language, "action": "flip", "title": fx["title"],
                "cover_path": fx["paths"]["cover"],
                "window": [1, len(frames)]}
        good = BS.check_clip(good_clip, spec)
        bad = BS.check_clip(bad_clip, spec)
        if good["verdict"] == "UNAVAILABLE" or bad["verdict"] == "UNAVAILABLE":
            raise CalibrationError(BS.BOOK_FRAMES_UNAVAILABLE,
                                   "control could not run: good=%s bad=%s"
                                   % (good["reason_code"], bad["reason_code"]))
        ok = good["verdict"] == "PASS" and bad["verdict"] == "FAIL"
        return {
            "schema_version": BS.SCHEMA_VERSION, "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION, "calibrated": bool(ok),
            "reason_code": "BOOK_CALIBRATION_OK" if ok
            else BS.BOOK_CALIBRATION_FAILED,
            "good": {"verdict": good["verdict"], "reason": good["reason_code"]},
            "hflip": {"verdict": bad["verdict"], "reason": bad["reason_code"]},
            "next_action": "the check sorts the control pair" if ok else
            "the check does NOT sort the control pair: every book verdict is "
            "UNAVAILABLE until it does",
        }
    finally:
        if own:
            shutil.rmtree(tmpdir, ignore_errors=True)

def is_calibrated(receipt):
    return bool(isinstance(receipt, dict) and receipt.get("calibrated"))

def main(argv=None):
    ap = argparse.ArgumentParser(prog="calibrate_book.py")
    ap.add_argument("--json", action="store_true", help="compact output")
    ns = ap.parse_args(argv)
    rec = calibrate()
    print(json.dumps(rec, indent=None if ns.json else 1, sort_keys=True))
    return 0 if rec["calibrated"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
