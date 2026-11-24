#!/usr/bin/env python3
"""jump_cut.py: a measured in-clip jump-cut detector (F-CG-1, CG-01).

Today only the whole-master mpdecimate 2 percent cap and the assembler's
``HARD_CUT_UNMARKED`` (unmarked transitions) existed; no scene-score detector
ran inside a clip. Rule: an ffmpeg scene score above 0.25 anywhere after the
first frame means a jump cut, and the clip is remade (never patched by a
zoom, freeze or crop, section 3.8). The first frame is excluded: it has no
previous frame to score against.

Input is the clip file. The detector is also the control: ``discriminates``
runs a known-clean clip and a known-cut clip and is True only when the clean
one has no cut and the cut one has at least one. A detector that cannot run
raises, and the caller records ``JUMP_CUT_UNAVAILABLE`` -- never a pass.

ffmpeg only, no spend. ``run`` is injectable (returns stderr text).
"""
from __future__ import annotations

import os
import re
import subprocess

TOOL_NAME = "jump_cut"
TOOL_VERSION = "1.0.0"

JUMP_CUT_DETECTED = "JUMP_CUT_DETECTED"
JUMP_CUT_UNAVAILABLE = "JUMP_CUT_UNAVAILABLE"

#: A cut to a different shot scores far above this; gradual motion does not.
SCENE_THRESHOLD = 0.25

_PTS_TIME = re.compile(r"pts_time:\s*([0-9.]+)")


class JumpCutError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _default_run(argv):
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise JumpCutError(JUMP_CUT_UNAVAILABLE,
                           "ffmpeg exited %s: %s"
                           % (proc.returncode, (proc.stderr or "")[-300:]))
    return proc.stderr or ""


def scan(path, ffmpeg="ffmpeg", run=None, threshold=SCENE_THRESHOLD):
    """Every frame time whose scene score is above ``threshold``.

    Returns ``{"path", "threshold", "cut_times", "first_frame_excluded"}``.
    Raises JumpCutError when the scan cannot run.
    """
    if not isinstance(path, (str, os.PathLike)):
        raise JumpCutError(JUMP_CUT_UNAVAILABLE, "no clip file to scan")
    if run is None and not os.path.isfile(path):
        raise JumpCutError(JUMP_CUT_UNAVAILABLE, "no clip file to scan: %s"
                           % path)
    argv = [ffmpeg, "-hide_banner", "-nostats", "-i", os.fspath(path),
            "-vf", "select='gt(scene,%.2f)',showinfo" % float(threshold),
            "-an", "-f", "null", "-"]
    try:
        stderr = (run or _default_run)(argv)
    except (OSError, subprocess.SubprocessError) as exc:
        raise JumpCutError(JUMP_CUT_UNAVAILABLE,
                           "%s could not run: %s" % (ffmpeg, exc)) from exc
    # A clean clip selects no frame, so an empty list is a real PASS; only a
    # build that cannot run the filter is unavailable (ffmpeg says so).
    if "No such filter" in (stderr or "") or "Error initializing" in (stderr or ""):
        raise JumpCutError(JUMP_CUT_UNAVAILABLE,
                           "the scene filter is not available: %s"
                           % (stderr or "")[-200:])
    times = sorted({float(m.group(1)) for m in _PTS_TIME.finditer(stderr)})
    # The first frame is excluded (it is scored against nothing); so is any
    # zero stamp a build may print for the very first selected frame.
    times = [t for t in times if t > 0.0]
    return {"path": os.fspath(path), "threshold": float(threshold),
            "cut_times": times, "first_frame_excluded": True}


def check(path, ffmpeg="ffmpeg", run=None, threshold=SCENE_THRESHOLD):
    """One severity-ready row: JUMP_CUT_DETECTED when a cut is found."""
    try:
        out = scan(path, ffmpeg=ffmpeg, run=run, threshold=threshold)
    except JumpCutError as exc:
        return {"path": os.fspath(path) if path else path,
                "verdict": "UNAVAILABLE", "reason_code": exc.code,
                "detail": str(exc), "cut_times": []}
    cuts = out["cut_times"]
    return {"path": out["path"], "verdict": "FAIL" if cuts else "PASS",
            "reason_code": JUMP_CUT_DETECTED if cuts else None,
            "cut_times": cuts}


def discriminates(clean_path, cut_path, ffmpeg="ffmpeg", run=None,
                  threshold=SCENE_THRESHOLD):
    """The module's control test: clean finds none, cut finds at least one.

    Returns ``{"discriminates": bool, "clean": row, "cut": row}``. False is a
    broken detector, not a clean clip (the negative-result rule): the caller
    must report the check unavailable, never pass the take.
    """
    clean = check(clean_path, ffmpeg=ffmpeg, run=run, threshold=threshold)
    cut = check(cut_path, ffmpeg=ffmpeg, run=run, threshold=threshold)
    ok = (clean.get("verdict") == "PASS"
          and cut.get("verdict") == "FAIL"
          and bool(cut.get("cut_times")))
    return {"discriminates": ok, "clean": clean, "cut": cut}


if __name__ == "__main__":
    # Control: a clean clip selects no frame; a jump cut is found; the very
    # first frame (pts 0.0) never counts; a filter that will not run is
    # UNAVAILABLE, never a clean clip.
    clean = lambda argv: ""
    cut = lambda argv: ("[Parsed_showinfo_1 @ 0x1] n:0 pts:12 pts_time:0.45 "
                        "s:1.0\n[Parsed_showinfo_1 @ 0x1] n:1 pts:30 "
                        "pts_time:1.250000 s:1.0\n")
    assert check("c.mp4", run=clean)["verdict"] == "PASS"
    row = check("c.mp4", run=cut)
    assert row["verdict"] == "FAIL" and row["cut_times"] == [0.45, 1.25]
    first = check("c.mp4", run=lambda a: "pts_time:0.000000\n")
    assert first["verdict"] == "PASS", first
    broken = check("c.mp4", run=lambda a: "No such filter: 'scene'\n")
    assert broken["verdict"] == "UNAVAILABLE"
    assert broken["reason_code"] == JUMP_CUT_UNAVAILABLE
    d = discriminates("clean.mp4", "cut.mp4",
                      run=lambda a: "" if "clean" in a[4] else cut(a))
    assert d["discriminates"] is True
    assert discriminates("clean.mp4", "cut.mp4",
                         run=lambda a: "")["discriminates"] is False
    print("jump_cut: control PASS")
