#!/usr/bin/env python3
"""morph.py: the intra-clip slow-morph detector (F-MORPH-1).

Scene score catches a hard cut and nothing else; a face that drifts, a jacket
that becomes another jacket, a person who shrinks or vanishes, or a body that
slides across the set all stay under a cut's score and land in the master.
This detector compares a take against itself:

  * first, middle and last frames (``samples_for`` names them);
  * face identity drift  -> FACE_MORPH
  * wardrobe-region drift -> WARDROBE_MORPH
  * character-vs-set height ratio swing -> SCALE_BREAK
  * a credited-cast face gone mid-take -> PRESENCE_BREAK
  * gradual position drift over the floor -> DRIFT_BREAK

It is read-only over a landed take and needs approved reference stills on
disk. The judgement is a ``judge`` callback so the check can run on any
vision model, and a missing judge or reference raises MorphUnavailable and
the row is ``MORPH_CHECK_UNAVAILABLE`` -- never a pass (3J item 15).

Thresholds are calibrated on the T10/T28/T14/T25/T16 takes: they are
defaults the first run stamps. stdlib only; frame sampling accepts ``run``.
"""
from __future__ import annotations

import os
import subprocess

TOOL_NAME = "morph"
TOOL_VERSION = "1.0.0"

FACE_MORPH = "FACE_MORPH"
WARDROBE_MORPH = "WARDROBE_MORPH"
SCALE_BREAK = "SCALE_BREAK"
PRESENCE_BREAK = "PRESENCE_BREAK"
DRIFT_BREAK = "DRIFT_BREAK"
MORPH_CHECK_UNAVAILABLE = "MORPH_CHECK_UNAVAILABLE"

#: Drift floors. The scene-score cut line is 0.25; a slow morph sits under it.
MAX_IDENTITY_DRIFT = 0.20      # 1 - similarity to the approved reference
MAX_WARDROBE_DRIFT = 0.20
MAX_SCALE_SWING = 0.15         # relative change of the height ratio
MAX_POSITION_DRIFT = 0.10      # fraction of frame width between samples

#: Where in the take the samples come from (first, middle, last).
SAMPLE_POINTS = (0.02, 0.50, 0.98)


class MorphUnavailable(Exception):
    def __init__(self, message):
        super().__init__("%s: %s" % (MORPH_CHECK_UNAVAILABLE, message))
        self.code = MORPH_CHECK_UNAVAILABLE


def _default_run(argv):
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise MorphUnavailable("ffmpeg exited %s: %s"
                               % (proc.returncode, (proc.stderr or "")[-200:]))
    return proc.stdout or ""


def duration(path, ffprobe="ffprobe", run=None):
    """Clip length in seconds, or MorphUnavailable."""
    argv = [ffprobe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", os.fspath(path)]
    try:
        out = (run or _default_run)(argv)
        return float(str(out).strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError) as exc:
        raise MorphUnavailable("duration of %s unreadable: %s"
                               % (path, exc)) from exc


def samples_for(path, out_dir, ffmpeg="ffmpeg", ffprobe="ffprobe", run=None,
                points=SAMPLE_POINTS):
    """Extract the first, middle and last frames; one path per point."""
    total = duration(path, ffprobe=ffprobe, run=run)
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i, frac in enumerate(points):
        t = max(0.0, min(total - 0.04, total * float(frac)))
        out = os.path.join(out_dir, "morph-%02d.png" % i)
        argv = [ffmpeg, "-hide_banner", "-nostats", "-y", "-ss", "%.3f" % t,
                "-i", os.fspath(path), "-frames:v", "1", out]
        try:
            (run or _default_run)(argv)
        except (OSError, subprocess.SubprocessError) as exc:
            raise MorphUnavailable("frame at %.2fs unreadable: %s"
                                   % (t, exc)) from exc
        if not os.path.isfile(out) or os.path.getsize(out) == 0:
            raise MorphUnavailable("frame at %.2fs was not written" % t)
        paths.append(out)
    return {"seconds": total, "frames": paths, "points": list(points)}


def _answers(judge, frames, reference, cast):
    """Ask the judge once per frame; a bad answer is unavailable, not a pass."""
    out = []
    for frame in frames:
        try:
            got = judge(frame, reference, cast)
        except Exception as exc:              # noqa: BLE001  fail closed
            raise MorphUnavailable("judge failed on %s: %s"
                                   % (frame, exc)) from exc
        if not isinstance(got, dict):
            raise MorphUnavailable("judge returned %s for %s; must be a dict"
                                   % (type(got).__name__, frame))
        out.append(got)
    return out


def check_take(frames, reference, cast, judge, limits=None):
    """Score one take from its sampled frames.

    ``judge(frame, reference, cast)`` answers, per frame:
      face_similarity (0..1), wardrobe_similarity (0..1),
      height_ratio (character height / set height), x (face centre, 0..1),
      faces (list of cast ids seen).

    Returns ``{verdict, findings, frames}``; findings carry the codes above.
    """
    lim = {"identity": MAX_IDENTITY_DRIFT, "wardrobe": MAX_WARDROBE_DRIFT,
           "scale": MAX_SCALE_SWING, "position": MAX_POSITION_DRIFT}
    lim.update(limits or {})
    frames = list(frames or [])
    if len(frames) < 3:
        raise MorphUnavailable("a take needs first/middle/last frames; got %d"
                               % len(frames))
    rows = _answers(judge, frames, reference, cast)
    findings = []
    for i, a in enumerate(rows):
        face = a.get("face_similarity")
        if isinstance(face, (int, float)) and (1.0 - float(face)) > lim["identity"]:
            findings.append({"code": FACE_MORPH, "frame": frames[i],
                             "drift": round(1.0 - float(face), 3)})
        ward = a.get("wardrobe_similarity")
        if isinstance(ward, (int, float)) and (1.0 - float(ward)) > lim["wardrobe"]:
            findings.append({"code": WARDROBE_MORPH, "frame": frames[i],
                             "drift": round(1.0 - float(ward), 3)})
        seen = set(a.get("faces") or [])
        missing = [c for c in (cast or []) if c not in seen]
        if missing:
            findings.append({"code": PRESENCE_BREAK, "frame": frames[i],
                             "missing": missing})
    ratios = [a.get("height_ratio") for a in rows
              if isinstance(a.get("height_ratio"), (int, float))]
    if len(ratios) >= 2 and min(ratios) > 0:
        swing = (max(ratios) - min(ratios)) / min(ratios)
        if swing > lim["scale"]:
            findings.append({"code": SCALE_BREAK, "swing": round(swing, 3)})
    xs = [a.get("x") for a in rows if isinstance(a.get("x"), (int, float))]
    if len(xs) >= 2 and (max(xs) - min(xs)) > lim["position"]:
        findings.append({"code": DRIFT_BREAK, "drift": round(max(xs) - min(xs), 3)})
    return {"verdict": "FAIL" if findings else "PASS", "findings": findings,
            "frames": frames, "limits": lim}


def unavailable_row(detail):
    """The row a caller records when the detector could not run."""
    return {"verdict": "UNAVAILABLE", "reason_code": MORPH_CHECK_UNAVAILABLE,
            "findings": [], "detail": str(detail)}


if __name__ == "__main__":
    # Control: a T28-class face morph refuses FACE_MORPH; a clean take admits;
    # a vanishing choir member refuses PRESENCE_BREAK; a wrong frame count is
    # UNAVAILABLE, never a pass.
    frames = ["first.png", "middle.png", "last.png"]

    def clean_judge(frame, reference, cast):
        return {"face_similarity": 0.95, "wardrobe_similarity": 0.95,
                "height_ratio": 0.50, "x": 0.50, "faces": ["lead", "choir"]}

    ok = check_take(frames, "ref.png", ["lead", "choir"], clean_judge)
    assert ok["verdict"] == "PASS", ok

    def morphing(frame, reference, cast):
        sim = 0.95 if frame != "last.png" else 0.55     # 0.45 drift
        return {"face_similarity": sim, "wardrobe_similarity": 0.95,
                "height_ratio": 0.50, "x": 0.50, "faces": ["lead", "choir"]}

    bad = check_take(frames, "ref.png", ["lead", "choir"], morphing)
    assert bad["verdict"] == "FAIL"
    assert [f["code"] for f in bad["findings"]] == [FACE_MORPH]

    def vanishing(frame, reference, cast):
        seen = ["lead", "choir"] if frame != "last.png" else ["lead"]
        return {"face_similarity": 0.95, "wardrobe_similarity": 0.95,
                "height_ratio": 0.50, "x": 0.50, "faces": seen}

    gone = check_take(frames, "ref.png", ["lead", "choir"], vanishing)
    assert gone["findings"][0]["code"] == PRESENCE_BREAK
    assert gone["findings"][0]["missing"] == ["choir"]

    def drifting(frame, reference, cast):
        x = {"first.png": 0.20, "middle.png": 0.45, "last.png": 0.70}[frame]
        return {"face_similarity": 0.95, "wardrobe_similarity": 0.95,
                "height_ratio": 0.50, "x": x, "faces": ["lead"]}

    moved = check_take(frames, "ref.png", ["lead"], drifting)
    assert moved["findings"][0]["code"] == DRIFT_BREAK

    try:
        check_take(frames[:2], "ref.png", ["lead"], clean_judge)
    except MorphUnavailable as exc:
        assert exc.code == MORPH_CHECK_UNAVAILABLE
    else:
        raise AssertionError("two frames must not pass")
    assert unavailable_row("judge down")["verdict"] == "UNAVAILABLE"
    print("morph: control PASS")
