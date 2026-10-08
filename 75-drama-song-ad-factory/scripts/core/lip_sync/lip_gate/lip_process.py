#!/usr/bin/env python3
"""lip_process.py: the approved lip-sync PROCESS (Trevor, 2026-10-08, Stephanie
Brown ads). One place, six rules; every later run follows it.

  1. REUSE FIRST   re-measure every take on disk for the segment, keep the
                   best: SYNCED, then WEAK, then NOT_SYNCED, then corr; a take
                   with a visible defect flag is dropped. No new paid job where
                   a usable take exists.
  2. KEPT_BEST     a sung line the checker cannot confirm keeps its best take,
                   tagged "KEPT_BEST (UNDETERMINED, sung)". A borderline
                   spoken line is kept, flagged.
  3. MOUTH STRIPS  8-frame strip for every UNDETERMINED or flagged segment at
                   <delivery>/mouth-strips/<segment>.png, listed in the receipt.
  4. RETRY         only on a person's call (person_verdict "DEFECT"), with
                   fewer than 2 jobs (all name variants counted) and a CHANGED
                   input. Never on a checker verdict.
  5. EDIT          trim to audio length, place at the Suno word time corrected
                   by the measured stem offset, lanczos 720x1280 -> 1080x1920,
                   conform to native fps by DROPPING frames (never invented),
                   all ffmpeg through load_governor.
  6. QC            items 8 and 11 accept KEPT_BEST and flagged rows that carry
                   a strip path.

Pure stdlib. Measuring and generating are injected; nothing here spends money.
"""
from __future__ import annotations

import os as _gos
import re
import sys as _gsys

_gcore = _gos.path.abspath(_gos.path.join(_gos.path.dirname(__file__), "..", ".."))
if _gcore not in _gsys.path:
    _gsys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402
import lipsync_clips as _LC  # noqa: E402

TOOL_NAME = "lip_process"
MAX_JOBS = _LC.MAX_TRIES           # 2 paid jobs per segment, every name variant counted (lipsync_clips.count_jobs)
STRIP_FRAMES = 8
OUT_W, OUT_H = 1080, 1920          # Kling standard renders 720x1280

SYNCED, WEAK, NOT_SYNCED = "SYNCED", "WEAK", "NOT_SYNCED"
_TIER = {SYNCED: 0, WEAK: 1, NOT_SYNCED: 2}
KEPT_BEST = "KEPT_BEST"
TAG_SUNG = "KEPT_BEST (UNDETERMINED, sung)"
TAG_SPOKEN = "KEPT_BEST (spoken, margin)"

REUSE_FIRST = "LIP_REUSE_FIRST"
NO_PERSON_CALL = "LIP_RETRY_NO_PERSON_CALL"
JOB_LIMIT = "LIP_RETRY_JOB_LIMIT"
SAME_INPUT = "LIP_RETRY_SAME_INPUT"
NO_STRIP = "LIP_ROW_NO_STRIP"
NO_NUMBERS = "LIP_ROW_NO_NUMBERS"

def safe_name(segment):
    """File-safe segment name for the strip path."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(segment).strip()).strip("_") or "segment"


# 1 + 2 -------------------------------------------------------------------

def _rank(t):
    corr = t.get("corr")
    return (_TIER.get(t.get("verdict"), 3), -(corr if isinstance(corr, (int, float)) else -2.0))


def pick_kept(takes, measure, sung):
    """Re-measure every take on disk and keep the best.

    takes: [{"path", "defect": bool/str optional}]; measure(path) -> dict with
    verdict (SYNCED/WEAK/NOT_SYNCED), corr, and optional lag/margin; a measure
    error leaves the take unmeasured (ranked last, never dropped).
    Returns None when no usable take exists, else the receipt-ready choice
    {take, measured, tag, flag, needs_strip, usable_takes}.
    """
    usable = []
    for t in takes:
        if t.get("defect"):
            continue                                  # visible defect: dropped
        try:
            m = dict(measure(t["path"]))
        except Exception:                             # unmeasured, not rejected
            m = {"verdict": None, "corr": None}
        usable.append((_rank(m), t["path"], t, m))
    if not usable:
        return None
    usable.sort(key=lambda x: (x[0], x[1]))
    _, _, take, m = usable[0]
    v = m.get("verdict")
    if v == SYNCED:
        tag, flag = KEPT_BEST, None
    elif v == WEAK:
        tag, flag = KEPT_BEST, WEAK
    elif sung:
        tag, flag = TAG_SUNG, "UNDETERMINED_SUNG"
    else:
        tag, flag = TAG_SPOKEN, "SPOKEN_BORDERLINE"
    return {"take": take["path"], "measured": m, "tag": tag, "flag": flag,
            "needs_strip": flag is not None, "usable_takes": len(usable)}


# 4 -----------------------------------------------------------------------

def retry_allowed(*, usable_take, person_verdict, jobs, input_fingerprint,
                  prior_fingerprints=()):
    """May ONE more paid job run? Returns (ok, reason_code).

    Never on a checker verdict: only person_verdict == "DEFECT" opens a retry,
    and only with fewer than MAX_JOBS jobs and an input unlike every prior job.
    A first job (no take, no job yet) is not a retry and is always allowed.
    """
    if jobs == 0 and not usable_take:
        return True, None
    if usable_take and str(person_verdict).upper() != "DEFECT":
        return False, REUSE_FIRST
    if str(person_verdict).upper() != "DEFECT":
        return False, NO_PERSON_CALL
    if jobs >= MAX_JOBS:
        return False, JOB_LIMIT
    if input_fingerprint in list(prior_fingerprints):
        return False, SAME_INPUT
    return True, None


# 3 -----------------------------------------------------------------------

def strip_path(delivery_dir, segment):
    return _gos.path.join(str(delivery_dir), "mouth-strips",
                          safe_name(segment) + ".png")


def mouth_strip_argv(clip, out_png, duration_s, crop=None, ffmpeg="ffmpeg"):
    """ffmpeg argv (bounded, run it with load_governor.run_ffmpeg) for ONE
    image of 8 frames spread evenly over the clip. crop=(x, y, w, h) zooms on
    the mouth."""
    if duration_s <= 0:
        raise ValueError("LIP_STRIP_BAD_DURATION")
    vf = ["fps=%.6f" % (STRIP_FRAMES / float(duration_s))]
    if crop:
        vf.append("crop=%d:%d:%d:%d" % (crop[2], crop[3], crop[0], crop[1]))
    vf += ["scale=-2:240", "tile=%dx1" % STRIP_FRAMES]
    return _LG.ffmpeg_argv(["-v", "error", "-y", "-i", str(clip), "-vf",
                            ",".join(vf), "-frames:v", "1", str(out_png)],
                           ffmpeg=ffmpeg)


# 5 -----------------------------------------------------------------------

def placement_s(word_start, lead_s, stem_offset_s, cut_corrected):
    """Where the clip goes on the mix timeline. stem_offset_s > 0 = the stem
    runs LATE (stem_offset.py). A clip cut with stem_offset.cut_plan is already
    time-true: place at word_start - lead. A take cut from the stem WITHOUT
    that correction carries the lateness, so it goes earlier by the offset."""
    t = word_start - lead_s - (0.0 if cut_corrected else stem_offset_s)
    return round(max(0.0, t), 4)


def fps_filter(src_fps, dst_fps):
    """Frame-rate conform by DROPPING frames only. Equal or lower source: no
    filter (a missing frame is never invented, no minterpolate, no dup)."""
    return "fps=%g" % dst_fps if float(src_fps) > float(dst_fps) + 1e-3 else ""


def edit_plan(clip, out, audio_len_s, word_start, lead_s, stem_offset_s,
              cut_corrected, src_fps=30.0, dst_fps=30.0, ffmpeg="ffmpeg"):
    """One lip-sync clip for the edit: argv (bounded, via load_governor) and
    the timeline place_at. Kling pads the tail, so the clip is cut to the
    audio length; 720x1280 is upscaled with lanczos."""
    if audio_len_s <= 0:
        raise ValueError("LIP_EDIT_BAD_AUDIO_LENGTH")
    vf = [f for f in (fps_filter(src_fps, dst_fps),
                      "scale=%d:%d:flags=lanczos" % (OUT_W, OUT_H)) if f]
    argv = _LG.ffmpeg_argv(["-v", "error", "-y", "-i", str(clip), "-t",
                            "%.3f" % audio_len_s, "-vf", ",".join(vf),
                            str(out)], ffmpeg=ffmpeg)
    return {"argv": argv, "place_at": placement_s(word_start, lead_s,
            stem_offset_s, cut_corrected), "trim_s": round(audio_len_s, 3),
            "vf": ",".join(vf)}


# 6 -----------------------------------------------------------------------

def receipt_row(segment, choice, jobs, strip=None, person_verdict=None):
    """The row QC reads: take kept, jobs used (n of 2), verdict and numbers,
    flag and strip path."""
    m = choice["measured"]
    return {"tool": TOOL_NAME, "segment": safe_name(segment),
            "line_id": safe_name(segment),
            "kept_take": choice["take"], "tag": choice["tag"],
            "jobs_used": "%d of %d" % (jobs, MAX_JOBS),
            "verdict": m.get("verdict"),
            "numbers": {k: m[k] for k in ("corr", "lag", "margin") if k in m},
            "flag": choice["flag"], "mouth_strip": strip,
            "person_verdict": person_verdict}


def qc_rows(rows):
    """Checklist items 8 and 11. A clean SYNCED row passes with its numbers.
    Any other row must be a KEPT_BEST row (or carry a flag) with numbers and a
    strip path; a flagged row without a strip is refused."""
    bad = []
    for r in rows:
        seg = r.get("segment")
        clean = r.get("verdict") == SYNCED and not r.get("flag")
        if r.get("verdict") and not r.get("numbers"):
            bad.append((seg, NO_NUMBERS))
        elif not clean and not r.get("mouth_strip"):
            bad.append((seg, NO_STRIP))
        elif not clean and not (r.get("flag") or
                                str(r.get("tag", "")).startswith(KEPT_BEST)):
            bad.append((seg, "LIP_ROW_NOT_KEPT"))
    return {"pass": not bad, "failed": bad,
            "strips": [r["mouth_strip"] for r in rows if r.get("mouth_strip")]}
