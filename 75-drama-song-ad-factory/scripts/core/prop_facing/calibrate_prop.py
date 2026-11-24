#!/usr/bin/env python3
"""calibrate_prop.py: the calibration control the prop check must pass first.

Same rule as the book check: run the checker on a KNOWN-GOOD picture (a
person facing the camera, reading a phone with the fixed sentence -- the
camera sees the phone's back) and on the old camera-facing picture of the
same beat (the phone screen facing the camera, readable). The check must
PASS the first and FAIL the second, or the check itself is broken and
every verdict it returns is UNAVAILABLE.

The control is fixture-driven and offline: both pictures are written
locally from the seeded fixtures. Zero network, zero provider spend.

Run (prints the receipt, exits 0 only when the pair sorts correctly):
    python3 scripts/core/prop_facing/calibrate_prop.py
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile

_ghere = os.path.dirname(os.path.abspath(__file__))
if _ghere not in sys.path:
    sys.path.insert(0, _ghere)
_gcore = os.path.abspath(os.path.join(_ghere, ".."))
if _gcore not in sys.path:
    sys.path.insert(0, _gcore)

try:                                    # imported as prop_facing.calibrate_prop
    from . import prop_facing as PF
    from .fixtures import build_fixtures as FIX
except ImportError:                     # run as a plain script
    import prop_facing as PF              # type: ignore # noqa: E402
    from fixtures import build_fixtures as FIX  # type: ignore # noqa: E402

TOOL_NAME = "calibrate_prop"
TOOL_VERSION = "1.0.0"

#: The known-good record: a phone the person uses, facing the user.
GOOD_RECORD = {"user": "her", "faces": "user", "viewer_must_read": "no"}


class CalibrationError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _write_clip(path, frames, cv2):
    h, w = frames[0].shape[:2]
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 12.0, (w, h))
    if not writer.isOpened():
        raise CalibrationError(PF.PROP_FRAMES_UNAVAILABLE,
                               "cv2 VideoWriter unavailable for %s" % path)
    try:
        for f in frames:
            writer.write(f)
    finally:
        writer.release()
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise CalibrationError(PF.PROP_FRAMES_UNAVAILABLE,
                               "cv2 wrote no clip at %s" % path)


def calibrate(tmpdir=None):
    """Run the control. Returns a receipt dict; a FAIL is a receipt, not a raise."""
    own = tmpdir is None
    tmpdir = tmpdir or tempfile.mkdtemp(prefix="prop-cal-")
    try:
        import cv2
        fx = FIX.build(tmpdir)
        spec = {"record": dict(GOOD_RECORD), "kind": "phone",
                "shot": "main", "prop_is_subject": True}
        good = PF.check_picture(None, spec, image=fx["images"]["good_frame"])
        bad = PF.check_picture(None, spec, image=fx["images"]["bad_frame"])
        if good["verdict"] == "UNAVAILABLE" or bad["verdict"] == "UNAVAILABLE":
            raise CalibrationError(PF.PROP_FRAMES_UNAVAILABLE,
                                   "control could not run: good=%s bad=%s"
                                   % (good["reason_code"], bad["reason_code"]))
        ok = good["verdict"] == "PASS" and bad["verdict"] == "FAIL"
        return {
            "schema_version": PF.SCHEMA_VERSION, "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION, "calibrated": bool(ok),
            "reason_code": "PROP_CALIBRATION_OK" if ok
            else PF.PROP_CHECK_UNAVAILABLE,
            "good": {"verdict": good["verdict"], "reason": good["reason_code"]},
            "bad": {"verdict": bad["verdict"], "reason": bad["reason_code"]},
            "next_action": "the check sorts the control pair" if ok else
            "the check does NOT sort the control pair: every prop verdict is "
            "UNAVAILABLE until it does",
        }
    finally:
        if own:
            shutil.rmtree(tmpdir, ignore_errors=True)


def is_calibrated(receipt):
    return bool(isinstance(receipt, dict) and receipt.get("calibrated"))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="calibrate_prop.py")
    ap.add_argument("--json", action="store_true", help="compact output")
    ns = ap.parse_args(argv)
    rec = calibrate()
    print(json.dumps(rec, indent=None if ns.json else 1, sort_keys=True))
    return 0 if rec["calibrated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
