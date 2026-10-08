#!/usr/bin/env python3
"""lip_gate.py: measured lip-sync gate (Part H H2; event_sync rewrite LSR001, 2026-10-08).

Why it changed: the old gate correlated mouth MOVEMENT with the loudness of the
FINAL MIX. A held sung vowel keeps the mouth almost flat while vibrato keeps the
loudness moving, so it read NOT_SYNCED on approved sung clips and drove paid
re-rolls that no new take could change (45% of the lip-sync spend). It also
could not tell wrong audio from right audio on repeated hooks.

Now: `event_sync` checks the mouth against EVENTS taken from the lead-vocal
stem span and the Suno word timestamps, with a +/-0.2 s tolerance:
  * a voiced-run ONSET after a rest      -> the mouth opens
  * a voiced-run OFFSET before a rest    -> the mouth closes (below p35)
  * every word with p, b or m            -> a lip-closure dip (below p35)
`hit` is the share of events matched; controls use the same mouth against the
events shifted +/-0.5 s and +/-1.0 s and against the OTHER lines' events.
Verdicts:
  SYNCED        hit >= 0.70 and margin >= 0.20
  WEAK          keep it, flag it, never a redo
  UNMEASURABLE  < 4 events or face in < 90% of frames: human mouth strip
  NOT_SYNCED    HARD defects only (still / closed through voice / moving through
                a long rest / hit <= 0.40 with >= 6 events): the only redo trigger

The 2-TRY RULE is in code (Trevor 2026-10-08: "only allow 2 try twice per thing
it creates after that it goes with whatever is the best one"): at most 2 Kling
standard jobs per segment (`prior_jobs` counts the ones already paid, every name
variant), try 2 only on a hard defect and only with a CHANGED input, then the
best-measured take is kept and the receipt says KEPT_BEST_OF_2. No third job and
no model switch (the InfiniTalk A/B is gone). Paid submits go through
load_governor.kie_request; landmark extraction goes through heavy_slot.

`python3 lip_gate.py selftest` runs the control battery and exits non-zero if any
negative control reads SYNCED or any positive reads NOT_SYNCED.
Pure stdlib except mouth_series (mediapipe + cv2, imported lazily). Providers are
injected so tests run at $0.
"""
from __future__ import annotations

import array
import math
import subprocess

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

# --- event_sync numbers (design doc 13, 2e; calibrate on the human-scored set)
TOL_S = 0.2                  # +/-0.2 s: not detectable by people
MIN_EVENTS = 4
MIN_FACE_FRAC = 0.90
REST_S = 0.12                # a real rest between voiced runs
RISE_FRAC = 0.30             # onset: mouth rises >= 30% of its range
LOW_PCT = 35                 # offset / bilabial: mouth below its p35
CLOSED_PCT = 20
SYNCED_HIT = 0.70
SYNCED_MARGIN = 0.20
HARD_HIT = 0.40
HARD_HIT_MIN_EVENTS = 6
STILL_RANGE = 0.015
MAX_CLOSED_VOICED_S = 0.5
MAX_MOVING_REST_S = 0.5
SHIFTS_S = (-1.0, -0.5, 0.5, 1.0)
MAX_TRIES = 2                # Trevor 2026-10-08: 2 tries, then keep the best

SYNCED, WEAK, UNMEASURABLE, NOT_SYNCED = "SYNCED", "WEAK", "UNMEASURABLE", "NOT_SYNCED"
TIER = {SYNCED: 3, WEAK: 2, UNMEASURABLE: 1, NOT_SYNCED: 0}
KEPT = "KEPT_BEST_OF_2"

LIP_UNMEASURED = "LIP_UNMEASURED"
LIP_STILL = "LIP_STILL_MOUTH"
LIP_CLOSED_VOICED = "LIP_CLOSED_THROUGH_VOICE"
LIP_MOVING_REST = "LIP_MOVING_THROUGH_REST"
LIP_HIT_LOW = "LIP_HIT_LOW"
LIP_TRY_LIMIT = "LIP_TRY_LIMIT"
LIP_SAME_INPUT = "LIP_RETRY_SAME_INPUT"


class LipTryLimit(Exception):
    """A third paid lip-sync job was asked for. Nothing was spent."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


# Default input for try 1 (was the redo-only input): padded cut, clean line.
IMPROVED_INPUT = {
    "line": "single clean line (no internal pause > 0.5 s)",
    "crop": "front-facing tight face crop",
    "image": "still image, lips relaxed and very slightly parted",
    "lead_in_s": 0.30,
    "tail_s": 0.20,
}

_PROMPT = {
    "sung": "A 3D animated {who} sings this line to the camera with a {emo} "
            "expression. Minimal head movement, steady locked camera, natural "
            "blinks, relaxed shoulders. {Poss} whole face and mouth stay fully "
            "visible. No text, captions or watermark.",
    "spoken": "A 3D animated {who} says this line to the camera, {emo}. "
              "Minimal head movement, steady locked camera, natural blinks. "
              "{Poss} whole face and mouth stay fully visible. No text, "
              "captions or watermark.",
}


def kling_prompt(kind, who="woman", emotion=None):
    """Kling prompt: 'sings' on sung lines, 'says' on spoken ones, ONE emotion,
    minimal head movement, steady camera. Mouth timing comes from the audio, so
    it never says 'lips open and close in time'."""
    if kind not in _PROMPT:
        raise ValueError("kind must be 'sung' or 'spoken'")
    emo = (emotion or ("calm, earnest" if kind == "sung" else "calm and sincere")).strip()
    poss = "His" if who.strip().lower() in ("man", "boy", "father", "dad") else "Her"
    return _PROMPT[kind].format(who=who.strip(), emo=emo, Poss=poss)


# ------------------------------------------------------------ small maths ----

def _pct(x, p):
    s = sorted(x)
    if not s:
        return 0.0
    k = (len(s) - 1) * p / 100.0
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _smooth(x, w=3):
    h = w // 2
    return [sum(x[max(0, i - h):i + h + 1]) / len(x[max(0, i - h):i + h + 1])
            for i in range(len(x))]


def _fill(m):
    """Forward/back fill NaN (no face) frames; returns (series, face_fraction)."""
    ok = [v for v in m if v == v]
    if not ok:
        return [], 0.0
    out, last = [], next(v for v in m if v == v)
    for v in m:
        last = v if v == v else last
        out.append(last)
    return out, len(ok) / float(len(m))


def _win(m, fps, a, b):
    i, j = max(0, int(math.floor(a * fps))), min(len(m), int(math.ceil(b * fps)) + 1)
    return m[i:j]


# ------------------------------------------------------- events from audio ----

def voiced_runs(env, fps, thr_frac=0.2, rest_s=REST_S, min_s=0.1):
    """Voiced runs (start_s, end_s) from a loudness envelope of the lead-vocal
    STEM: frames above thr_frac x max, gaps shorter than rest_s merged."""
    if not env:
        return []
    thr = thr_frac * max(env)
    runs, s = [], None
    for i, v in enumerate(env + [0.0]):
        if v > thr and s is None:
            s = i
        elif v <= thr and s is not None:
            runs.append([s / float(fps), i / float(fps)])
            s = None
    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < rest_s:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [tuple(r) for r in merged if r[1] - r[0] >= min_s]


def events(voiced, words=(), dur=None, rest_s=REST_S):
    """Build the event set for one span. voiced: [(s, e)] from voiced_runs;
    words: [{"word","start","end"}] Suno stamps relative to the span start."""
    onsets = [s for s, _ in voiced]
    offsets = [e for _, e in voiced]
    bil = [(w["start"], w["end"]) for w in words
           if any(c in "pbm" for c in str(w.get("word", "")).lower())]
    rests = [(voiced[i][1], voiced[i + 1][0]) for i in range(len(voiced) - 1)
             if voiced[i + 1][0] - voiced[i][1] >= rest_s]
    end = dur if dur else (voiced[-1][1] if voiced else 0.0)
    return {"onsets": onsets, "offsets": offsets, "bilabial": bil,
            "voiced": list(voiced), "rests": rests, "dur": end}


def _n_events(ev):
    return len(ev["onsets"]) + len(ev["offsets"]) + len(ev["bilabial"])


def _shift(ev, d, scale=1.0):
    f = lambda t: t * scale + d
    return {"onsets": [f(t) for t in ev["onsets"]],
            "offsets": [f(t) for t in ev["offsets"]],
            "bilabial": [(f(a), f(b)) for a, b in ev["bilabial"]],
            "voiced": [(f(a), f(b)) for a, b in ev["voiced"]],
            "rests": [(f(a), f(b)) for a, b in ev["rests"]],
            "dur": ev["dur"] * scale}


def _hits(m, fps, ev, lo_thr, rng, tol=TOL_S):
    """(matched, total) for one event set against one mouth series."""
    hit = tot = 0
    n = len(m) / float(fps)
    for t in ev["onsets"]:
        tot += 1
        if t - tol < 0 or t + tol > n + tol:
            continue
        before, after = _win(m, fps, t - tol, t), _win(m, fps, t, t + tol)
        if before and after and max(after) - min(before) >= RISE_FRAC * rng:
            hit += 1
    for t in ev["offsets"]:
        tot += 1
        w = _win(m, fps, t - tol, t + tol) if 0 <= t <= n + tol else []
        if w and min(w) <= lo_thr:
            hit += 1
    for a, b in ev["bilabial"]:
        tot += 1
        w = _win(m, fps, a, b) if 0 <= a <= n else []
        if w and min(w) <= lo_thr:
            hit += 1
    return hit, tot


def _rate(m, fps, ev, lo_thr, rng):
    h, t = _hits(m, fps, ev, lo_thr, rng)
    return h / float(t) if t else 0.0


def _defects(m, fps, ev, rng, p20):
    d = []
    voiced_total = sum(b - a for a, b in ev["voiced"])
    if rng < STILL_RANGE and voiced_total > 0:
        d.append(LIP_STILL)
    run_max = 0
    for a, b in ev["voiced"]:
        run = 0
        for v in _win(m, fps, a, b):
            run = run + 1 if v <= p20 else 0
            run_max = max(run_max, run)
    if run_max / float(fps) > MAX_CLOSED_VOICED_S and LIP_STILL not in d:
        d.append(LIP_CLOSED_VOICED)
    for a, b in ev["rests"]:
        if b - a > MAX_MOVING_REST_S:
            w = _win(m, fps, a + TOL_S, b - TOL_S)
            if w and max(w) - min(w) >= 0.5 * rng and rng >= STILL_RANGE:
                d.append(LIP_MOVING_REST)
                break
    return d


def event_sync(mouth, ev, control_events, fps, extra_defects=()):
    """Judge one clip. mouth: per-frame inner-lip gap / face height (NaN = no
    face); ev: events() of the lead-vocal span; control_events: events() of the
    chapter's OTHER lines. Returns a dict with verdict, hit, control_hit, margin,
    lag_s, n_events, face_frac, hard_defects."""
    if fps <= 0:
        raise ValueError(LIP_UNMEASURED)
    m, face = _fill(list(mouth))
    n_ev = _n_events(ev)
    base = {"hit": 0.0, "control_hit": 0.0, "margin": 0.0, "lag_s": 0.0,
            "n_events": n_ev, "face_frac": round(face, 4), "hard_defects": [],
            "fps": fps, "tol_s": TOL_S}
    if not m or face < MIN_FACE_FRAC or n_ev < MIN_EVENTS:
        why = "face in %.0f%% of frames" % (face * 100) if face < MIN_FACE_FRAC \
            else "%d events (need %d)" % (n_ev, MIN_EVENTS)
        return dict(base, verdict=UNMEASURABLE, reason=why,
                    hard_defects=list(extra_defects))
    m = _smooth(m)
    p5, p95 = _pct(m, 5), _pct(m, 95)
    rng = p95 - p5
    # below the p35, but never above 40% of the way up the range (a mouth that
    # is open most of the time has a p35 inside its open values)
    lo, p20 = min(_pct(m, LOW_PCT), p5 + 0.4 * rng), _pct(m, CLOSED_PCT)
    hit = _rate(m, fps, ev, lo, rng)
    ctrl = []
    for d in SHIFTS_S:
        ctrl.append(_rate(m, fps, _shift(ev, d), lo, rng))
    dur = len(m) / float(fps)
    for oc in control_events:
        sc = dur / oc["dur"] if oc.get("dur") else 1.0
        ctrl.append(_rate(m, fps, _shift(oc, 0.0, sc), lo, rng))
    best_ctrl = max(ctrl) if ctrl else 0.0
    # lag: the shift (frames, -6..6) at which the real events match best; smaller |lag| wins ties
    lags = sorted(range(-6, 7), key=abs)
    lag = max(lags, key=lambda k: (_rate(m, fps, _shift(ev, k / float(fps)), lo, rng), -abs(k)))
    defects = list(extra_defects) + _defects(m, fps, ev, rng, p20)
    if hit <= HARD_HIT and n_ev >= HARD_HIT_MIN_EVENTS:
        defects.append(LIP_HIT_LOW)
    if defects:
        verdict = NOT_SYNCED
    elif hit >= SYNCED_HIT and hit - best_ctrl >= SYNCED_MARGIN:
        verdict = SYNCED
    else:
        verdict = WEAK
    return dict(base, verdict=verdict, hit=round(hit, 4),
                control_hit=round(best_ctrl, 4), margin=round(hit - best_ctrl, 4),
                lag_s=round(-lag / float(fps), 4), hard_defects=defects)


def judge(j):
    """Row-level view of an event_sync result."""
    return dict(j, hard=bool(j.get("hard_defects")) or j["verdict"] == NOT_SYNCED)


def score(j):
    """Higher is better (design 2f): no hard defect, then verdict tier, then
    hit and margin, then smaller |lag|."""
    return (not (j.get("hard_defects") or j["verdict"] == NOT_SYNCED),
            TIER[j["verdict"]], j.get("hit", 0.0), j.get("margin", 0.0),
            -abs(j.get("lag_s", 0.0)))


# ----------------------------------------------------------------- the gate ----

def _same(a, b):
    return {k: v for k, v in a.items() if k != "try"} == {k: v for k, v in b.items() if k != "try"}


def run_gate(line_id, generate, measure_clip, source_image=None, image_check=None,
             retry_input=None, prior_jobs=0, make_strip=None, acquire=None):
    """Orchestrate at most 2 Kling standard jobs for one segment.

    generate(provider, input_spec) -> clip     provider is always "kling"
    measure_clip(clip) -> event_sync() result (may carry extra hard_defects
                          found by eye: garbled face, hand over mouth, ...)
    prior_jobs: paid jobs already made for this segment under ANY name variant
                (lipsync_clips.count_jobs). Tries left = 2 - prior_jobs; 0 left
                raises LipTryLimit before anything is spent.
    retry_input: the CHANGED input for try 2 (next-best choose_window window or
                the padded cut). Missing or identical = try 2 is refused, the
                take is kept and flagged.
    make_strip(clip) -> path of the 8-frame mouth strip for the kept take.
    acquire: injected KIE pacing (tests); default load_governor's bucket.
    image_check / source_image: the picture gate; runs BEFORE the first paid
    job. Nothing is spent when the picture is refused.
    Try 2 runs ONLY when try 1 has a hard defect; never on WEAK/UNMEASURABLE.
    """
    left = MAX_TRIES - int(prior_jobs)
    if left <= 0:
        raise LipTryLimit(LIP_TRY_LIMIT, "segment %s already has %d paid lip-sync "
                          "job(s); the limit is %d. Keep the best-measured take, "
                          "mark it in the receipt, move on." % (line_id, prior_jobs, MAX_TRIES))
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
    spec1 = dict(IMPROVED_INPUT, source_image=source_image, **{"try": 1})
    attempts = [_attempt(spec1, generate, measure_clip, acquire, line_id)]
    flag = None
    if attempts[0]["judge"]["hard"] and left >= 2:
        spec2 = dict(retry_input or {}, source_image=source_image, **{"try": 2})
        if retry_input and not _same(spec2, spec1):
            attempts.append(_attempt(spec2, generate, measure_clip, acquire, line_id))
        else:
            flag = "RETRY_REFUSED: try 2 needs a changed input; kept try 1"
    return _row(line_id, attempts, flag, make_strip, prior_jobs)


def _attempt(spec, generate, measure_clip, acquire, line_id):
    # every paid submit goes through the KIE pacing bucket (20 new jobs / 10 s)
    clip = _LG.kie_request(lambda: generate("kling", spec),
                           "lipsync %s try %s" % (line_id, spec.get("try")),
                           generation=True, acquire=acquire)
    return {"provider": "kling", "input": spec, "clip": clip,
            "judge": judge(measure_clip(clip))}


def _row(line_id, attempts, flag, make_strip, prior_jobs=0):
    kept = max(attempts, key=lambda a: score(a["judge"]))
    j = kept["judge"]
    ok = j["verdict"] == SYNCED and not j["hard"]
    if not ok and flag is None:
        flag = "%s%s (hit %.2f, margin %.2f)%s" % (
            j["verdict"], "+" + ",".join(j["hard_defects"]) if j["hard_defects"] else "",
            j["hit"], j["margin"],
            "; UNDETERMINED until a person checks the mouth strip"
            if j["verdict"] in (WEAK, UNMEASURABLE) else "")
    return {"tool": TOOL_NAME, "line_id": line_id, "attempts": attempts,
            "jobs_used": len(attempts), "jobs_total": int(prior_jobs) + len(attempts),
            "kept": kept["provider"], "kept_try": kept["input"].get("try"),
            "kept_clip": kept["clip"],
            "verdict": "PASS" if ok else KEPT,
            "flag": None if ok else flag,
            "receipt": None if ok else "KEPT_BEST_OF_2 (t%s), %s, hit %.2f margin %.2f, %s"
            % (kept["input"].get("try"), j["verdict"], j["hit"], j["margin"], flag),
            "mouth_strip": make_strip(kept["clip"]) if make_strip else None,
            "numbers": {k: j[k] for k in ("hit", "control_hit", "margin", "lag_s",
                                          "n_events", "face_frac")}}


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
    """Receipt-level check: every lip clip has a PASS row with numbers, or a
    flagged KEPT_BEST_OF_2 row (Trevor's keep-best-of-2 rule) that carries
    numbers, the flag text and a mouth-strip path. Never more than 2 jobs."""
    bad = []
    for r in rows:
        v, ok = r.get("verdict"), False
        if "numbers" in r and r.get("jobs_total", r.get("jobs_used", 1)) <= MAX_TRIES:
            ok = v == "PASS" or (v == KEPT and r.get("flag") and r.get("mouth_strip"))
        if not ok:
            bad.append(r.get("line_id"))
    return {"pass": not bad, "failed_lines": bad,
            "reason_code": None if not bad else "LIP_SYNC_GATE_FAILED"}


# ------------------------------------------------ optional ffmpeg helpers ----

def _run_raw(argv):
    p = _LG.run_ffmpeg(argv, "lip-gate-measure", stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError("%s: %s" % (LIP_UNMEASURED, p.stderr[-300:]))
    return p.stdout


def inner_lip_gap(p):
    """Inner-lip gap / face height from a landmark list (indices 13, 14 inner
    lips; 10 forehead, 152 chin): the mouth signal event_sync reads."""
    fh = max(abs(p[152].y - p[10].y), 1e-6)
    return abs(p[14].y - p[13].y) / fh


def mouth_series(clip, model_path, fps=30, detect=None):
    """Per-frame inner-lip gap / face height (mediapipe), resampled to fps;
    NaN where no face. Runs inside load_governor.heavy_slot. detect(frame) ->
    landmark list or None can be injected (tests); default is mediapipe's
    FaceLandmarker with model_path."""
    with _LG.heavy_slot("lip-gate-landmarks"):
        import cv2
        if detect is None:
            import mediapipe as mp
            from mediapipe.tasks.python import vision, BaseOptions
            lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=model_path),
                running_mode=vision.RunningMode.IMAGE, num_faces=1))

            def detect(bgr):
                r = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                       data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
                return r.face_landmarks[0] if r.face_landmarks else None
        cap = cv2.VideoCapture(clip)
        native = cap.get(cv2.CAP_PROP_FPS) or float(fps)
        raw = []
        while True:
            ok, f = cap.read()
            if not ok:
                break
            p = detect(f)
            raw.append(inner_lip_gap(p) if p else float("nan"))
        cap.release()
    if not raw:
        raise RuntimeError("%s: no frames read from %s" % (LIP_UNMEASURED, clip))
    n = int(len(raw) * fps / native)
    return [raw[min(len(raw) - 1, int(i * native / fps))] for i in range(n)]


def envelope(audio, fps=30, ffmpeg="ffmpeg", start=0.0, dur=None):
    """RMS loudness per 1/fps window of the LEAD-VOCAL STEM span (start, dur),
    never the final mix; smoothed 3 frames. Feed it to voiced_runs()."""
    sr = 16000
    argv = [ffmpeg, "-v", "error", "-threads", "4", "-ss", str(start)]
    if dur:
        argv += ["-t", str(dur)]
    raw = _run_raw(argv + ["-i", audio, "-ac", "1", "-ar", str(sr),
                           "-f", "s16le", "-"])
    s = array.array("h")
    s.frombytes(raw[:len(raw) // 2 * 2])
    win = sr // fps
    out = [(sum(v * v for v in s[i:i + win]) / win) ** 0.5
           for i in range(0, len(s) - win + 1, win)]
    return _smooth(out)


# ------------------------------------------------------------- selftest ----

def synth_clip(seed, fps=30, dur=6.0, n_words=9):
    """Synthetic (mouth, events) pair for the control battery: an irregular
    word rhythm with rests, a mouth that opens at onsets, closes at offsets and
    dips on p/b/m words."""
    import random
    r = random.Random(seed)
    t, words, voiced = 0.4, [], []
    while len(words) < n_words and t < dur - 0.8:
        s = t
        for _ in range(r.randint(3, 5)):
            w = r.uniform(0.25, 0.6)
            words.append({"word": r.choice(["map", "love", "be", "sun", "you", "my", "dream", "go"]),
                          "start": t, "end": t + w})
            t += w + r.uniform(0.0, 0.05)
        voiced.append((s, t))
        t += r.uniform(0.3, 0.45)
    n = int(dur * fps)
    mouth = [0.02] * n
    for a_, b_ in voiced:                 # legato: open through the phrase, shut in rests
        ph = r.uniform(0, 6.28)
        for i in range(int(a_ * fps), min(n, int(b_ * fps))):
            mouth[i] = 0.13 + 0.02 * math.sin(ph + i / 5.0)
    for w in words:
        if any(c in "pbm" for c in w["word"]):       # lip closure at the word start
            for i in range(int(w["start"] * fps), min(n, int((w["start"] + 0.15) * fps))):
                mouth[i] = 0.02
    return mouth, events(voiced, words, dur)


def selftest(extra_controls=()):
    """The control battery. extra_controls: [(name, 'positive'|'negative', mouth,
    ev, others, fps)] from real clips. Returns a list of failures; empty = pass.
    FAILS if ANY negative control comes out SYNCED or any positive NOT_SYNCED
    (the bug in the old v2: wrong audio passed and the selftest still said PASS)."""
    fps, bad, rows = 30, [], []
    pool = [synth_clip(s) for s in range(1, 7)]
    for i, (mouth, ev) in enumerate(pool):
        others = [e for j, (_, e) in enumerate(pool) if j != i]
        rows.append(("own audio #%d" % i, "positive", mouth, ev, others, fps))
        sh = int(0.5 * fps)
        rows.append(("own audio shifted 0.5 s #%d" % i, "negative",
                     mouth[sh:] + [mouth[-1]] * sh, ev, others, fps))
        rows.append(("still face #%d" % i, "negative", [0.07] * len(mouth), ev, others, fps))
        rows.append(("no face (cartoon) #%d" % i, "unmeasurable",
                     [float("nan")] * len(mouth), ev, others, fps))
        for k, (_, wrong) in enumerate(pool):
            if k != i:
                rows.append(("wrong audio %d on clip %d" % (k, i), "negative",
                             mouth, wrong, [e for j, (_, e) in enumerate(pool) if j not in (i, k)], fps))
    rows += list(extra_controls)
    for name, kind, mouth, ev, others, f in rows:
        v = event_sync(mouth, ev, others, f)["verdict"]
        if kind == "negative" and v == SYNCED:
            bad.append("%s: negative control read SYNCED" % name)
        elif kind == "positive" and v == NOT_SYNCED:
            bad.append("%s: positive control read NOT_SYNCED" % name)
        elif kind == "unmeasurable" and v != UNMEASURABLE:
            bad.append("%s: expected UNMEASURABLE, got %s" % (name, v))
    return bad



if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["selftest"]:
        fails = selftest()
        print("SELFTEST", "FAIL" if fails else "PASS")
        for f in fails:
            print(" ", f)
        sys.exit(1 if fails else 0)
    sys.exit(__doc__)
