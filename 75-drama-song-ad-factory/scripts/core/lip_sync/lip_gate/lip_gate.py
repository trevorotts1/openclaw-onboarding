#!/usr/bin/env python3
"""lip_gate.py: measured lip-sync gate (Part H H2, Kiesett Stop Stale root cause 05).

Kling ai-avatar mouths followed the voice weakly (corr 0.43-0.73, mouth up to
0.17 s early) and nothing measured it. Every lip-sync clip is now measured
against the FINAL MIX envelope and must pass ALL of:

  * |offset| <= 0.05 s            (negative offset = mouth BEFORE the sound)
  * corr >= 0.55 AND corr - wrong-audio-control corr >= 0.25
  * no frozen face (still mouth inside the line) longer than 0.75 s

Below it: regenerate once with better input (single clean line, front-facing
tight face crop, still image, 0.35 s lead-in / 0.2 s tail); then InfiniTalk
only through a ONE-TIME single-line A/B (keep whichever MEASURES better); a
clip that still fails is flagged FAIL_REPLACE (swap for a non-face shot).
All numbers go in the receipt row. Pure stdlib; providers are injected so
tests run at $0. ffmpeg helpers (-threads 4) are optional.
"""
from __future__ import annotations

import array
import subprocess

TOOL_NAME = "lip_gate"
SCHEMA_VERSION = "1.0.0"

# Calibrated on 3 clips (n=3); tune on first real runs.
MAX_OFFSET_S = 0.05
MIN_CORR = 0.55
MIN_CONTROL_MARGIN = 0.25
MAX_FROZEN_S = 0.75
MAX_LAG_S = 0.6

LIP_OFFSET = "LIP_OFFSET"
LIP_CORR_LOW = "LIP_CORR_LOW"
LIP_CONTROL_MARGIN = "LIP_CONTROL_MARGIN"
LIP_FROZEN_FACE = "LIP_FROZEN_FACE"
LIP_UNMEASURED = "LIP_UNMEASURED"

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


def _xcorr(mouth, voice, max_lag):
    """Return (best_corr, best_k). k>0 = voice sample k frames AFTER the
    mouth sample matches -> mouth is early."""
    best, bk = -2.0, 0
    for k in range(-max_lag, max_lag + 1):
        if k >= 0:
            m, v = mouth[:len(mouth) - k], voice[k:]
        else:
            m, v = mouth[-k:], voice[:len(voice) + k]
        n = min(len(m), len(v))
        c = _pearson(m[:n], v[:n])
        if c > best:
            best, bk = c, k
    return best, bk


def frozen_seconds(mouth, voice, fps):
    """Longest still-mouth run inside the line span (first..last voiced frame)."""
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


def measure(mouth, voice, control_voice, fps):
    """Measure one clip. mouth/voice/control_voice: equal-rate series at fps."""
    if not mouth or not voice or not control_voice or fps <= 0:
        raise ValueError(LIP_UNMEASURED)
    ml = int(MAX_LAG_S * fps)
    corr, k = _xcorr(mouth, voice, ml)
    ctrl, _ = _xcorr(mouth, control_voice, ml)
    return {"offset_s": round(-k / fps, 4), "corr": round(corr, 4),
            "control_corr": round(ctrl, 4),
            "margin": round(corr - ctrl, 4),
            "frozen_s": round(frozen_seconds(mouth, voice, fps), 4),
            "fps": fps}


def judge(m):
    """Pass/fail a measurement; adds verdict, reasons, shift_s (delay the
    clip by this to zero the offset; positive = move clip later)."""
    reasons = []
    if abs(m["offset_s"]) > MAX_OFFSET_S:
        reasons.append(LIP_OFFSET)
    if m["corr"] < MIN_CORR:
        reasons.append(LIP_CORR_LOW)
    if m["margin"] < MIN_CONTROL_MARGIN:
        reasons.append(LIP_CONTROL_MARGIN)
    if m["frozen_s"] > MAX_FROZEN_S:
        reasons.append(LIP_FROZEN_FACE)
    return dict(m, verdict="PASS" if not reasons else "FAIL",
                reasons=reasons, shift_s=round(-m["offset_s"], 4))


def score(j):
    """Higher is better; any passing clip beats any failing clip."""
    s = j["margin"] - abs(j["offset_s"]) - j["frozen_s"] / 10
    return s + (10 if j["verdict"] == "PASS" else 0)


def run_gate(line_id, generate, measure_clip, ab_state, source_image=None):
    """Orchestrate attempts. Injected, so mocked providers work at $0.

    generate(provider, input_spec) -> clip ; provider in {"kling","infinitalk"}
    measure_clip(clip) -> measurement dict from measure()
    ab_state: {"infinitalk_used": bool}, shared across the run: the
    InfiniTalk A/B is ONE-TIME on a single line.
    source_image: the speaker's lip-sync close-up (lipsync_closeup()); every
    attempt, InfiniTalk included, takes it as its source image by default.
    Returns the receipt row (all attempts' numbers + kept attempt).
    """
    src = {"source_image": source_image} if source_image else {}
    improved = dict(IMPROVED_INPUT, **src)
    plan = [("kling", src or None), ("kling", improved)]
    attempts = []
    for provider, spec in plan:
        attempts.append(_attempt(provider, spec, generate, measure_clip))
        if attempts[-1]["judge"]["verdict"] == "PASS":
            return _row(line_id, attempts, False)
    ab = False
    if not ab_state.get("infinitalk_used"):
        ab_state["infinitalk_used"] = True
        ab = True
        attempts.append(_attempt("infinitalk", improved, generate,
                                 measure_clip))
    return _row(line_id, attempts, ab)


def _attempt(provider, spec, generate, measure_clip):
    clip = generate(provider, spec)
    return {"provider": provider, "input": spec or "base", "clip": clip,
            "judge": judge(measure_clip(clip))}


def _row(line_id, attempts, ab):
    kept = max(attempts, key=lambda a: score(a["judge"]))
    ok = kept["judge"]["verdict"] == "PASS"
    return {"tool": TOOL_NAME, "line_id": line_id, "attempts": attempts,
            "infinitalk_ab": ab, "kept": kept["provider"],
            "kept_clip": kept["clip"], "verdict": "PASS" if ok else
            "FAIL_REPLACE", "numbers": {k: kept["judge"][k] for k in (
                "offset_s", "corr", "control_corr", "margin", "frozen_s")}}


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
    """Receipt-level check: every lip clip has a PASS row with numbers."""
    bad = [r.get("line_id") for r in rows
           if r.get("verdict") != "PASS" or "numbers" not in r]
    return {"pass": not bad, "failed_lines": bad,
            "reason_code": None if not bad else "LIP_SYNC_GATE_FAILED"}


# ------------------------------------------------ optional ffmpeg helpers ----

def _run_raw(argv):
    p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
