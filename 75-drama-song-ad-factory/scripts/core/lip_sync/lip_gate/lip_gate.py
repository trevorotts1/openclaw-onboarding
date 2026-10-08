"""lip_gate.py: measured lip-sync gate (Part H H2; looser sung-aware check LSL001).

Every lip-sync clip is measured against the FINAL MIX envelope. The old rule made
a clip pass four tests at once (corr >= .50, |lag| <= 4 frames, margin >= .08,
z >= 1.5) with cut-offs tuned only on SPOKEN lines. On a held sung note the mouth
stays open while the voice holds steady, so plain correlation dropped on clips
that looked right to a person. That rule is gone. Now:

  * ONSET correlation: correlate only the frames where the voice is CHANGING
    (onsets and syllable changes; first differences of the log envelope with a
    threshold). Held-note frames carry no weight. Best lag searched +-8 frames; a best lag at the edge (8 or more) is FAIL.
  * Three verdicts (same shape as Trevor's 5/10 band):
      PASS             clearly matches (corr, lag and margin all comfortable)
      ACCEPT_WITH_FLAG borderline: accepted and USED; the flags go in the receipt
      FAIL             clearly wrong ONLY: timing off by about 8 frames or more, the
                       WRONG audio matches better than its own audio, no
                       relationship at all, or the face is still / not found
  * UNMEASURED         could not be measured (no mediapipe, silent audio, no
                       onsets): reported, never a pass; qc_check refuses it.
  * Trevor's 2-try rule: at most 2 paid lip-sync jobs per segment, then keep the
    best-measured take. A passing OR accepted-with-flag first take stops there.

Cut-offs were calibrated on known-good controls (calibrate_controls.py, table in
the PR): approved sung and spoken clips PASS, the same clips with wrong audio
FAIL, a still face FAILs. Pure stdlib; providers are injected so tests run at $0.
"""
from __future__ import annotations

import array
import subprocess
import math

try:                                   # package import
    from . import image_gate
except ImportError:                    # script import (tests run from here)
    import image_gate
# Skill 75 load governor: every heavy local job goes through it (see load_governor/).
import os as _gos, sys as _gsys
_gcore = _gos.path.abspath(_gos.path.join(_gos.path.dirname(__file__), '..', '..'))
if _gcore not in _gsys.path:
    _gsys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402

TOOL_NAME = "lip_gate"
SCHEMA_VERSION = "2.0.0"

# Calibrated on known-good controls (see calibrate_controls.py and the PR table).
MAX_LAG_FRAMES = 8           # lag search window (+-8 frames)
PASS_LAG_FRAMES = 4          # PASS needs |lag| <= this
FAIL_LAG_FRAMES = 8          # FAIL when the best lag sits at the edge of the window: off by 8 frames or more
PASS_CORR = 0.40             # onset correlation for PASS
PASS_MARGIN = 0.05           # lead over the best wrong-audio control, for PASS
FAIL_MARGIN = 0.0            # FAIL when a wrong audio matches better than the own audio
FAIL_CORR = 0.30             # FAIL when onset correlation is below this (no relationship)
ACTIVE_FRAC = 0.25           # a frame is "voice changing" when |d log-env| >= this x the max
MIN_ONSETS = 6               # fewer changing frames than this cannot be measured
MIN_MOUTH_RANGE = 0.015      # p95-p5 of mouth opening / face height; below = still face
MAX_TRIES = 2                # Trevor's 2-try rule: paid lip-sync jobs per segment

PASS = "PASS"
FLAG = "ACCEPT_WITH_FLAG"
FAIL = "FAIL"
UNMEASURED = "UNMEASURED"

LIP_OFFSET = "LIP_OFFSET"                    # flag: lag over 4 frames (still <= 8)
LIP_OFFSET_FAR = "LIP_OFFSET_FAR"            # fail: lag over 8 frames
LIP_CORR_LOW = "LIP_CORR_LOW"                # flag: onset corr under the PASS line
LIP_NO_RELATION = "LIP_NO_RELATION"          # fail: onset corr under the floor
LIP_CONTROL_MARGIN = "LIP_CONTROL_MARGIN"    # flag: margin under the PASS line
LIP_WRONG_AUDIO = "LIP_WRONG_AUDIO"          # fail: wrong audio matches better
LIP_STILL_FACE = "LIP_STILL_FACE"            # fail: mouth barely moves
LIP_FACE_NOT_FOUND = "LIP_FACE_NOT_FOUND"    # fail: no usable face
LIP_UNMEASURED = "LIP_UNMEASURED"
LIP_NO_ONSETS = "LIP_NO_ONSETS"

# What "better input" means on the regenerate attempt.
IMPROVED_INPUT = {
    "line": "single clean line (no internal pause > 0.5 s)",
    "crop": "front-facing tight face crop",
    "image": "still image, relaxed slightly open mouth",
    "lead_in_s": 0.35,
    "tail_s": 0.2,
}


def _pearson(a, b):
    n = len(a)
    if n < 3 or n != len(b):
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    da = [x - ma for x in a]
    db = [x - mb for x in b]
    va, vb = sum(x * x for x in da), sum(x * x for x in db)
    if va <= 1e-12 or vb <= 1e-12:
        return 0.0
    return sum(x * y for x, y in zip(da, db)) / (va * vb) ** 0.5


def _diff(x):
    return [x[i + 1] - x[i] for i in range(len(x) - 1)]


def _prep(x):
    """Log-compress a loudness series (loud and quiet syllables weigh alike),
    then smooth 3 frames."""
    top = max(x) if x else 0.0
    return _smooth([math.log(v + 0.02 * top + 1e-9) for v in x])


def _active(dv):
    """Frames where the voice is changing (onsets, syllable changes), widened
    by one frame each side. Held notes (steady energy) are left out."""
    top = max((abs(v) for v in dv), default=0.0)
    if top <= 1e-9:
        return [False] * len(dv)
    hit = [abs(v) >= ACTIVE_FRAC * top for v in dv]
    return [hit[i] or (i > 0 and hit[i - 1]) or (i + 1 < len(hit) and hit[i + 1])
            for i in range(len(hit))]


def onset_xcorr(mouth, voice, max_lag=MAX_LAG_FRAMES):
    """-> (best_corr, best_k, n_onsets). Pearson of mouth-change vs voice-change,
    taken ONLY on frames where the voice is changing. k>0 = the voice change
    comes k frames AFTER the mouth change = mouth is early."""
    dm, dv = _diff(_smooth(mouth)), _diff(_prep(voice))
    act = _active(dv)
    best, bk = -2.0, 0
    for k in range(-max_lag, max_lag + 1):
        idx = [t for t in range(len(dv)) if act[t] and 0 <= t - k < len(dm)]
        # mouth sample at t-k pairs with voice sample at t
        c = _pearson([dm[t - k] for t in idx], [dv[t] for t in idx]) \
            if len(idx) >= MIN_ONSETS else 0.0
        if c > best:
            best, bk = c, k
    return best, bk, sum(act)


def frozen_seconds(mouth, voice, fps):
    """Informational only (no longer a verdict input: a held sung note keeps the
    mouth still on purpose). Longest still-mouth run inside the voiced span."""
    vmax = max(voice) if voice else 0.0
    voiced = [i for i, v in enumerate(voice) if v > 0.2 * vmax]
    if not voiced or not mouth:
        return 0.0
    thr = 0.1 * max(mouth)
    run = longest = 0
    for i in range(voiced[0], min(voiced[-1] + 1, len(mouth))):
        run = run + 1 if mouth[i] <= thr else 0
        longest = max(longest, run)
    return longest / fps


def measure(mouth, voice, control_voice, fps, mouth_range=None, face_found=True):
    """Measure one clip. mouth/voice: equal-rate series at fps. control_voice:
    ONE other-audio series or a LIST of them (the other lines of the chapter).
    mouth_range: p95-p5 of mouth opening / face height (landmark series), the
    still-face test. face_found False -> judged FAIL (LIP_FACE_NOT_FOUND)."""
    if not mouth or not voice or not control_voice or fps <= 0:
        raise ValueError(LIP_UNMEASURED)
    controls = control_voice if isinstance(control_voice[0], (list, tuple)) \
        else [control_voice]
    corr, k, n_on = onset_xcorr(mouth, voice)
    # like with like: a control shorter than the clip is compared on ITS length,
    # against the clip's own audio over the same frames (no tiling tricks).
    margin, ctrl = 9.0, -2.0
    for c in controls:
        n = min(len(mouth), len(voice), len(c))
        own = onset_xcorr(mouth[:n], voice[:n])[0]
        other = onset_xcorr(mouth[:n], c[:n])[0]
        ctrl = max(ctrl, other)
        margin = min(margin, own - other)
    return {"offset_s": round(-k / fps, 4), "lag_frames": k,
            "corr": round(corr, 4), "onsets": n_on,
            "control_corr": round(ctrl, 4), "margin": round(margin, 4),
            "frozen_s": round(frozen_seconds(mouth, voice, fps), 4),
            "mouth_range": None if mouth_range is None else round(mouth_range, 4),
            "face_found": bool(face_found), "fps": fps}


def judge(m):
    """Three verdicts + UNMEASURED. FAIL only when clearly wrong; PASS when it
    clearly matches; anything between is ACCEPT_WITH_FLAG (used, noted).
    Adds verdict, reasons (fail causes) or flags (borderline notes), and
    shift_s (delay the clip by this to zero the offset; + = move clip later)."""
    shift = round(-m["offset_s"], 4)
    if m.get("onsets", MIN_ONSETS) < MIN_ONSETS:
        return dict(m, verdict=UNMEASURED, reasons=[LIP_NO_ONSETS], flags=[],
                    shift_s=shift)
    fails, flags = [], []
    if not m.get("face_found", True):
        fails.append(LIP_FACE_NOT_FOUND)
    if m.get("mouth_range") is not None and m["mouth_range"] < MIN_MOUTH_RANGE:
        fails.append(LIP_STILL_FACE)
    if abs(m["lag_frames"]) >= FAIL_LAG_FRAMES:
        fails.append(LIP_OFFSET_FAR)
    if m["margin"] < FAIL_MARGIN:
        fails.append(LIP_WRONG_AUDIO)
    if m["corr"] < FAIL_CORR:
        fails.append(LIP_NO_RELATION)
    if fails:
        return dict(m, verdict=FAIL, reasons=fails, flags=[], shift_s=shift)
    if abs(m["lag_frames"]) > PASS_LAG_FRAMES:
        flags.append(LIP_OFFSET)
    if m["corr"] < PASS_CORR:
        flags.append(LIP_CORR_LOW)
    if m["margin"] < PASS_MARGIN:
        flags.append(LIP_CONTROL_MARGIN)
    return dict(m, verdict=FLAG if flags else PASS, reasons=[], flags=flags,
                shift_s=shift)


def unmeasured(why):
    """Judged row for a clip that could not be measured (no mediapipe, no model,
    silent audio...). Reported; never a pass."""
    return {"verdict": UNMEASURED, "reasons": [LIP_UNMEASURED], "flags": [],
            "why": str(why), "offset_s": 0.0, "lag_frames": 0, "corr": 0.0,
            "control_corr": 0.0, "margin": 0.0, "frozen_s": 0.0, "shift_s": 0.0}


_RANK = {PASS: 2, FLAG: 1, FAIL: 0, UNMEASURED: -1}


def score(j):
    """Higher is better: PASS > ACCEPT_WITH_FLAG > FAIL > UNMEASURED, then the
    own-audio lead and the onset correlation, minus the timing error."""
    return (_RANK[j["verdict"]] * 10 + j["margin"] + j["corr"]
            - abs(j["lag_frames"]) / 10)


def run_gate(line_id, generate, measure_clip, ab_state=None, source_image=None,
             image_check=None):
    """Orchestrate at most MAX_TRIES (2) paid lip-sync jobs. Injected, so mocked
    providers work at $0.

    generate(provider, input_spec) -> clip
    measure_clip(clip) -> measurement from measure(), or the Unmeasured
        exception from mouth_landmarks (turned into an UNMEASURED verdict)
    ab_state: kept for callers; the InfiniTalk third job is gone (2-try rule).
    source_image / image_check: the picture gate, runs BEFORE any generate()
    call; no picture, no checker, or a failing picture raises
    image_gate.LipsyncImageRefused with every reason; nothing is spent.

    Stops at the first PASS or ACCEPT_WITH_FLAG (accepted and used). Stops after
    an UNMEASURED take (a second paid job could not be judged either). After two
    FAILs keeps the best-measured take. Returns the receipt row.
    """
    if not source_image:
        raise image_gate.LipsyncImageRefused(
            [(image_gate.IMAGE_MISSING, "no lip-sync source picture")], line_id)
    if image_check is None:
        raise image_gate.LipsyncImageRefused(
            [(image_gate.IMAGE_UNCHECKED, "no image check supplied")], line_id)
    res = image_check(source_image)
    if not isinstance(res, dict) or res.get("pass") is not True:
        raise image_gate.LipsyncImageRefused(
            (res or {}).get("reasons") or [(image_gate.UNMEASURED,
                                            "image check gave no verdict")],
            line_id)
    src = {"source_image": source_image}
    plan = [("kling", src), ("kling", dict(IMPROVED_INPUT, **src))][:MAX_TRIES]
    attempts = []
    for provider, spec in plan:
        attempts.append(_attempt(provider, spec, generate, measure_clip))
        if attempts[-1]["judge"]["verdict"] != FAIL:
            break
    return _row(line_id, attempts)


def _attempt(provider, spec, generate, measure_clip):
    clip = generate(provider, spec)
    try:
        j = judge(measure_clip(clip))
    except Exception as e:          # Unmeasured from mouth_landmarks, bad input
        if str(e).startswith(LIP_UNMEASURED) or isinstance(e, ValueError):
            j = unmeasured(e)
        else:
            raise
    return {"provider": provider, "input": spec or "base", "clip": clip,
            "judge": j}


def _row(line_id, attempts):
    kept = max(attempts, key=lambda a: score(a["judge"]))
    j = kept["judge"]
    verdict = {PASS: PASS, FLAG: FLAG, UNMEASURED: UNMEASURED}.get(
        j["verdict"], "FAIL_REPLACE")
    return {"tool": TOOL_NAME, "line_id": line_id, "attempts": attempts,
            "paid_jobs": len(attempts), "infinitalk_ab": False,
            "kept": kept["provider"], "kept_clip": kept["clip"],
            "verdict": verdict, "flags": j.get("flags", []),
            "reasons": j.get("reasons", []),
            "numbers": {k: j[k] for k in (
                "offset_s", "lag_frames", "corr", "control_corr", "margin",
                "frozen_s")}}


LIPSYNC_VIEW = "lipsync-closeup"
LIPSYNC_REF_MISSING = "LIPSYNC_CLOSEUP_MISSING"
LIPSYNC_MOUTH_BAD = "LIPSYNC_CLOSEUP_MOUTH_NOT_CLEAR"


def lipsync_closeup(reference_set, character):
    """The character's lip-sync close-up entry (the default source image), or None."""
    for r in reference_set:
        if r.get("character") == character and r.get("view") == LIPSYNC_VIEW:
            return r
    return None


def check_reference_set(reference_set, characters, mouth_clear):
    """Owner order 2026-10-08: every speaking/singing character needs a lip-sync
    close-up whose mouth is sharp and unobstructed. mouth_clear(entry) -> bool is
    the injected face/mouth detection or vision check. A set without it FAILS."""
    bad = []
    for c in characters:
        e = lipsync_closeup(reference_set, c)
        if e is None:
            bad.append({"character": c, "reason_code": LIPSYNC_REF_MISSING})
        elif not mouth_clear(e):
            bad.append({"character": c, "reason_code": LIPSYNC_MOUTH_BAD})
    return {"pass": not bad, "failed": bad}


def qc_check(rows):
    """Receipt-level check: every lip clip has a PASS or ACCEPT_WITH_FLAG row with
    numbers. FAIL_REPLACE and UNMEASURED rows fail the check."""
    bad = [r.get("line_id") for r in rows
           if r.get("verdict") not in (PASS, FLAG) or "numbers" not in r]
    return {"pass": not bad, "failed_lines": bad,
            "reason_code": None if not bad else "LIP_SYNC_GATE_FAILED"}


# ------------------------------------------------ optional ffmpeg helpers ----

def _run_raw(argv):
    p = _LG.run_ffmpeg(argv, "lip-gate-measure", stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError("%s: %s" % (LIP_UNMEASURED, p.stderr[-300:]))
    return p.stdout


def _smooth(x, w=3):
    h = w // 2
    return [sum(x[max(0, i - h):i + h + 1]) / len(x[max(0, i - h):i + h + 1])
            for i in range(len(x))]


def mouth_series(clip, box, fps=30, ffmpeg="ffmpeg"):
    """Mean abs frame difference inside box=(x, y, w, h), smoothed 3 frames."""
    x, y, w, h = box
    raw = _run_raw([ffmpeg, "-v", "error", "-threads", "4", "-i", clip,
                    "-vf", "fps=%d,crop=%d:%d:%d:%d,format=gray" % (
                        fps, w, h, x, y), "-f", "rawvideo", "-"])
    n, size = len(raw) // (w * h), w * h
    out, prev = [0.0], None
    for i in range(n):
        f = raw[i * size:(i + 1) * size]
        if prev is not None:
            out.append(sum(abs(a - b) for a, b in zip(f, prev)) / size)
        prev = f
    return _smooth(out[:n])


def envelope(audio, fps=30, ffmpeg="ffmpeg", start=0.0):
    """RMS loudness per 1/fps window of the FINAL MIX, smoothed 3 frames."""
    sr = 16000
    raw = _run_raw([ffmpeg, "-v", "error", "-threads", "4", "-ss",
                    str(start), "-i", audio, "-ac", "1", "-ar", str(sr),
                    "-f", "s16le", "-"])
    s = array.array("h")
    s.frombytes(raw[:len(raw) // 2 * 2])
    win = sr // fps
    out = [(sum(v * v for v in s[i:i + win]) / win) ** 0.5
           for i in range(0, len(s) - win + 1, win)]
    return _smooth(out)


# ------------------------------------------------ clip-level entry point ----

def _fit(x, n, tile=True):
    """Cut a series to n frames; a short one is tiled (other lines' audio vs this
    clip) or, with tile=False (the clip's OWN audio), padded with silence at the end."""
    if not x:
        return []
    if tile:
        return [x[i % len(x)] for i in range(n)]
    return (x + [min(x)] * n)[:n]


def measure_file(clip, audio=None, others=(), ffmpeg="ffmpeg"):
    """Measure a real clip: landmark mouth opening vs the voice envelope.
    audio = the audio span the clip should follow (default: the clip's own
    track); others = >= 2 other lines' audio of the same chapter (the wrong-audio
    control). Raises mouth_landmarks.Unmeasured when mediapipe / the model is
    missing, and ValueError(LIP_UNMEASURED) for silent audio or < 2 controls:
    run_gate turns both into an UNMEASURED verdict, never a pass."""
    try:
        from . import mouth_landmarks as ML
    except ImportError:
        import mouth_landmarks as ML
    if len(others) < 2:
        raise ValueError("%s: need >= 2 other-line audios for the control" %
                         LIP_UNMEASURED)
    s = ML.mouth_series(clip)
    fps = s["fps"]
    filled, why = ML.usable(s)
    if why:                       # no face / not human: clearly wrong, not unmeasured
        return {"offset_s": 0.0, "lag_frames": 0, "corr": 0.0,
                "onsets": MIN_ONSETS, "control_corr": 0.0, "margin": 0.0,
                "frozen_s": 0.0, "mouth_range": None, "face_found": False,
                "fps": fps, "why": why}
    n = len(filled)
    voice = _fit(envelope(audio or clip, fps=round(fps), ffmpeg=ffmpeg), n, tile=False)
    if not voice or max(voice) < 1e-4:
        raise ValueError("%s: audio silent" % LIP_UNMEASURED)
    ctrl = [envelope(o, fps=round(fps), ffmpeg=ffmpeg) for o in others]
    srt = sorted(filled)
    rng = srt[int(.95 * (n - 1))] - srt[int(.05 * (n - 1))]
    return measure(filled, voice, ctrl, fps, mouth_range=rng)
