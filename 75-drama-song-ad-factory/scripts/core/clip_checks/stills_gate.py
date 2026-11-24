#!/usr/bin/env python3
"""stills_gate.py: brightness and sharpness floors for storyboard stills (F-PIC-5).

Today the close-up floors in ``lip_sync/lip_gate/image_gate.py``
(MIN_LIGHT_EVENNESS 0.70, sharp-face floor 60.0 on a 256 px face crop) apply
only to lip-sync source pictures. Storyboard stills and H3 clips were cleared
by eye. This small stills gate gives them a measured floor:

  * ``STILL_TOO_DARK``  mean luma below 0.20, or a luma range below 0.15
    (a flat, muddy picture reads dark however its average lands)
  * ``STILL_TOO_SOFT``  ffmpeg's blurdetect score above 20 (very soft)

The floors mirror the intent of the close-up floors -- a picture too dark or
too soft to read is refused before any spend -- at whole-frame scale, where a
face-crop Laplacian number does not apply. ``STILL_GATE_UNAVAILABLE`` when
ffmpeg cannot measure: a still nobody measured is never a pass (3J item 15).

ffmpeg only, no spend. ``run`` is injectable for tests.
"""
from __future__ import annotations

import os
import re
import subprocess

TOOL_NAME = "stills_gate"
TOOL_VERSION = "1.0.0"

STILL_TOO_DARK = "STILL_TOO_DARK"
STILL_TOO_SOFT = "STILL_TOO_SOFT"
STILL_GATE_UNAVAILABLE = "STILL_GATE_UNAVAILABLE"

#: Floors. Chosen to sit just under a correctly exposed, in-focus picture of
#: the kind the close-up floors already accept; raise them once a run stamps
#: real stills (ponytail: whole-frame proxies, not the face-crop measures).
MIN_BRIGHTNESS = 0.20          # mean luma / 255
MIN_CONTRAST = 0.15            # (max luma - min luma) / 255
MAX_BLUR = 20.0                # blurdetect "blur" score; higher is softer

_YAVG = re.compile(r"lavfi\.signalstats\.YAVG=([0-9.]+)")
_YMIN = re.compile(r"lavfi\.signalstats\.YMIN=([0-9.]+)")
_YMAX = re.compile(r"lavfi\.signalstats\.YMAX=([0-9.]+)")
_BLUR = re.compile(r"lavfi\.blur=([0-9.]+)")


def _float(pattern, text):
    m = pattern.search(text or "")
    return float(m.group(1)) if m else None


def _default_run(argv):
    return subprocess.run(argv, capture_output=True, text=True,
                          check=False).stdout or ""


def measure(path, ffmpeg="ffmpeg", run=None):
    """Read luma average/range and blur from one still.

    Returns ``{"numbers": {...}, "available": bool, "detail": str}``. The
    numbers are None when ffmpeg (or the filter) could not measure; the
    caller turns that into STILL_GATE_UNAVAILABLE, never a pass.
    """
    if not isinstance(path, (str, os.PathLike)):
        return {"numbers": {}, "available": False, "detail": "no still path"}
    argv = [ffmpeg, "-hide_banner", "-nostats", "-i", os.fspath(path),
            "-vf", "signalstats,blurdetect,metadata=mode=print:file=-",
            "-frames:v", "1", "-f", "null", "-"]
    try:
        out = (run or _default_run)(argv)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"numbers": {}, "available": False,
                "detail": "%s could not run: %s" % (ffmpeg, exc)}
    nums = {"yavg": _float(_YAVG, out), "ymin": _float(_YMIN, out),
            "ymax": _float(_YMAX, out), "blur": _float(_BLUR, out)}
    available = nums["yavg"] is not None
    detail = "" if available else "signalstats read no luma average"
    return {"numbers": nums, "available": available, "detail": detail}


def check_still(path, ffmpeg="ffmpeg", run=None, numbers=None):
    """One row: ``{path, verdict, reasons, numbers, available}``.

    ``verdict`` PASS | FAIL | UNAVAILABLE. ``numbers`` may be supplied (the
    close-up gate already measured the picture) instead of running ffmpeg.
    """
    nums = dict(numbers or {})
    if not nums:
        got = measure(path, ffmpeg=ffmpeg, run=run)
        nums = got["numbers"]
        if not got["available"]:
            return {"path": os.fspath(path) if path else path,
                    "verdict": "UNAVAILABLE", "reasons": [],
                    "reason_code": STILL_GATE_UNAVAILABLE,
                    "detail": got["detail"], "numbers": nums}
    reasons = []
    yavg = nums.get("yavg")
    if yavg is not None and yavg / 255.0 < MIN_BRIGHTNESS:
        reasons.append([STILL_TOO_DARK, "mean luma %.2f < %.2f"
                        % (yavg / 255.0, MIN_BRIGHTNESS)])
    ymin, ymax = nums.get("ymin"), nums.get("ymax")
    if ymin is not None and ymax is not None:
        contrast = (ymax - ymin) / 255.0
        if contrast < MIN_CONTRAST:
            reasons.append([STILL_TOO_DARK, "luma range %.2f < %.2f (flat)"
                            % (contrast, MIN_CONTRAST)])
    blur = nums.get("blur")
    if blur is not None and blur > MAX_BLUR:
        reasons.append([STILL_TOO_SOFT, "blur %.1f > %.1f" % (blur, MAX_BLUR)])
    return {"path": os.fspath(path) if path else path,
            "verdict": "FAIL" if reasons else "PASS",
            "reasons": reasons, "reason_code": None, "numbers": nums}


def check_paths(paths, ffmpeg="ffmpeg", run=None):
    """One row per still, in caller order (a clip's frames pass as stills)."""
    return [check_still(p, ffmpeg=ffmpeg, run=run) for p in paths or []]


def blocked(rows):
    """The rows a caller must act on: FAIL or UNAVAILABLE, never PASS."""
    return [r for r in rows or [] if r.get("verdict") != "PASS"]


if __name__ == "__main__":
    # Control: a dark still refuses STILL_TOO_DARK, a soft one STILL_TOO_SOFT,
    # a good one passes, and a measure that reads nothing is UNAVAILABLE.
    dark = check_still("s.png", numbers={"yavg": 20.0, "ymin": 5.0,
                                         "ymax": 60.0, "blur": 1.0})
    assert dark["verdict"] == "FAIL"
    assert [r[0] for r in dark["reasons"]] == [STILL_TOO_DARK]
    flat = check_still("s.png", numbers={"yavg": 128.0, "ymin": 120.0,
                                         "ymax": 130.0, "blur": 1.0})
    assert flat["verdict"] == "FAIL" and flat["reasons"][0][0] == STILL_TOO_DARK
    soft = check_still("s.png", numbers={"yavg": 128.0, "ymin": 10.0,
                                        "ymax": 240.0, "blur": 40.0})
    assert soft["verdict"] == "FAIL" and soft["reasons"][0][0] == STILL_TOO_SOFT
    good = check_still("s.png", numbers={"yavg": 128.0, "ymin": 10.0,
                                        "ymax": 240.0, "blur": 2.0})
    assert good["verdict"] == "PASS" and good["reasons"] == []
    blind = check_still("s.png", run=lambda a: "")
    assert blind["verdict"] == "UNAVAILABLE"
    assert blind["reason_code"] == STILL_GATE_UNAVAILABLE
    assert len(blocked([good, dark])) == 1
    print("stills_gate: control PASS")
