#!/usr/bin/env python3
"""chain_join.py: SSIM score for a chained-join between two landed frames (F-CG-5).

Chained shots (a T25-to-T26 style hand-off) are joined picture to picture.
Nothing scored that join today, so a near-hard-cut seam (the 0.244 class)
could land in the master and read as a jump. This scorer reads the two
landed frames with ffmpeg's ssim filter and refuses a join below the floor
with ``CHAIN_NOT_CONTINUOUS``.

Plan 02 owns the chain itself (the codes and the ordering); this module is
the scorer those units call. Input is the two frames only -- no clip decode,
no spend. A join that cannot be measured is ``CHAIN_SSIM_UNAVAILABLE``,
never a pass.

ffmpeg only; ``run`` is injectable (returns stderr text).
"""
from __future__ import annotations

import os
import re
import subprocess

TOOL_NAME = "chain_join"
TOOL_VERSION = "1.0.0"

CHAIN_NOT_CONTINUOUS = "CHAIN_NOT_CONTINUOUS"
CHAIN_SSIM_UNAVAILABLE = "CHAIN_SSIM_UNAVAILABLE"

#: Floor for a continuous chained join. The measured near-hard-cut class is
#: 0.244, so the floor sits above it with margin (ponytail: one SSIM number;
#: raise it once a run stamps real chained joins).
MIN_CHAIN_SSIM = 0.40

_ALL = re.compile(r"All:\s*([0-9.]+)")


class ChainJoinError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _default_run(argv):
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise ChainJoinError(CHAIN_SSIM_UNAVAILABLE,
                             "ffmpeg exited %s: %s"
                             % (proc.returncode, (proc.stderr or "")[-300:]))
    return proc.stderr or ""


def ssim(frame_a, frame_b, ffmpeg="ffmpeg", run=None):
    """The ssim score of two frames (0..1; 1 is identical)."""
    for path in (frame_a, frame_b):
        if not isinstance(path, (str, os.PathLike)):
            raise ChainJoinError(CHAIN_SSIM_UNAVAILABLE, "no frame path")
        if run is None and not os.path.isfile(path):
            raise ChainJoinError(CHAIN_SSIM_UNAVAILABLE,
                                 "no frame file: %s" % path)
    argv = [ffmpeg, "-hide_banner", "-nostats", "-i", os.fspath(frame_a),
            "-i", os.fspath(frame_b), "-lavfi", "ssim", "-f", "null", "-"]
    try:
        stderr = (run or _default_run)(argv)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ChainJoinError(CHAIN_SSIM_UNAVAILABLE,
                             "%s could not run: %s" % (ffmpeg, exc)) from exc
    m = _ALL.search(stderr or "")
    if not m:
        raise ChainJoinError(CHAIN_SSIM_UNAVAILABLE,
                             "ssim printed no All score: %s"
                             % (stderr or "")[-200:])
    return float(m.group(1))


def score_join(frame_a, frame_b, ffmpeg="ffmpeg", run=None,
               floor=MIN_CHAIN_SSIM):
    """One join row: PASS below/above the floor decided, never guessed."""
    row = {"frame_a": os.fspath(frame_a) if frame_a else frame_a,
           "frame_b": os.fspath(frame_b) if frame_b else frame_b,
           "floor": float(floor), "ssim": None, "verdict": "UNAVAILABLE",
           "reason_code": None}
    try:
        row["ssim"] = ssim(frame_a, frame_b, ffmpeg=ffmpeg, run=run)
    except ChainJoinError as exc:
        row["reason_code"] = exc.code
        row["detail"] = str(exc)
        return row
    if row["ssim"] < row["floor"]:
        row["verdict"] = "FAIL"
        row["reason_code"] = CHAIN_NOT_CONTINUOUS
    else:
        row["verdict"] = "PASS"
    return row


def check_chain(frames, ffmpeg="ffmpeg", run=None, floor=MIN_CHAIN_SSIM):
    """Score every consecutive pair. Returns rows, the weakest score and the findings."""
    frames = list(frames or [])
    rows = [score_join(frames[i], frames[i + 1], ffmpeg=ffmpeg, run=run,
                       floor=floor)
            for i in range(max(0, len(frames) - 1))]
    scores = [r["ssim"] for r in rows if r.get("ssim") is not None]
    findings = []
    for r in rows:
        if r["verdict"] != "PASS":
            findings.append({"code": r["reason_code"] or CHAIN_SSIM_UNAVAILABLE,
                             "join": [r["frame_a"], r["frame_b"]],
                             "ssim": r.get("ssim")})
    return {"rows": rows, "weakest": min(scores) if scores else None,
            "findings": findings, "pass": not findings}


if __name__ == "__main__":
    # Control: a near-hard-cut join (the 0.244 class) refuses; a close join
    # passes; a join that cannot be scored is UNAVAILABLE, never a pass.
    def score(value):
        return lambda argv: "SSIM Y:0.9 U:0.9 V:0.9 All:%s (10.0)\n" % value

    assert score_join("a.png", "b.png", run=score("0.244"))["verdict"] == "FAIL"
    assert score_join("a.png", "b.png", run=score("0.244"))["reason_code"] == \
        CHAIN_NOT_CONTINUOUS
    assert score_join("a.png", "b.png", run=score("0.900"))["verdict"] == "PASS"
    broke = score_join("a.png", "b.png", run=lambda a: "")
    assert broke["verdict"] == "UNAVAILABLE" and \
        broke["reason_code"] == CHAIN_SSIM_UNAVAILABLE
    chain = check_chain(["f1", "f2", "f3"],
                        run=lambda a: "All:0.10\n" if "f3" in a else
                        "All:0.90\n")
    assert chain["weakest"] == 0.10
    assert not chain["pass"] and chain["findings"][0]["code"] == \
        CHAIN_NOT_CONTINUOUS
    assert check_chain(["f1"], run=score("0.9"))["pass"]      # nothing to join
    print("chain_join: control PASS")
