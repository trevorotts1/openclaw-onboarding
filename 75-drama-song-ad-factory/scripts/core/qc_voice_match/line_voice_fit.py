#!/usr/bin/env python3
"""H10: each line's voice must fit the character ON SCREEN (Part H, 2026-10-08).

Kiesett's sung verses came back at 70-86 Hz (a low voice) over the woman's
face. qc_voice_match checks a per-line wav against the SPEAKER's gender; this
module measures the line inside the vocal stem and judges it against the
declared voice of the character whose face is shown, then regenerates that
take on a mismatch. Stdlib only, no network, no spend.

Trevor's target rule (2026-10-08 12:30) applied to the distance OUTSIDE the
character's pitch band, as a percent of the nearest band edge:
  <= 5   accept
  5..10  accept WITH A FLAG in the receipt
  > 10   REDO -- regenerate the take; the closest take is never kept.
Pitch measurement and the male/female bands are qc_voice_match's (imported,
not copied). Declared band override: character["voice_band_hz"] = [lo, hi].

ponytail: per-line pitch = median of up to MAX_FRAMES autocorrelation frames
(pure python). Raise MAX_FRAMES, or swap in YIN, if real stems need it.

WW-27 adds the IDENTITY measurement D5 is judged from, beyond pitch: a
pitch-invariant timbre profile (the normalized overtone ratios at the take's own
fundamental), so a pitch difference alone is never a second voice and the same
pitch with different harmonic content is. This module measures; D5 delivers.
"""
from __future__ import annotations

import math
import os
import sys

try:
    from . import qc_voice_match as base
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import qc_voice_match as base

TOOL_NAME = "line_voice_fit"
TOOL_VERSION = "1.0.0"
CODE = "VOICE_FACE_MISMATCH"
ACCEPT_PCT = 5.0       # Trevor 12:30: within 5 accept
FLAG_PCT = 10.0        # 5..10 accept + flag; over 10 redo
FRAME_S = 0.06
MAX_FRAMES = 40
MAX_ROUNDS = 3


def character_band(char):
    """(low, high) Hz declared for a character, or None when undeclared."""
    if isinstance(char, dict):
        b = char.get("voice_band_hz")
        if isinstance(b, (list, tuple)) and len(b) == 2:
            return float(b[0]), float(b[1])
        g = base._norm(char.get("gender"))
        if g in base.PITCH_RANGES_HZ:
            return base.PITCH_RANGES_HZ[g]
    return None


def line_median_hz(samples, rate, start_s, end_s):
    """Median fundamental of the voiced frames of samples[start_s:end_s]."""
    a, b = int(max(0.0, start_s) * rate), int(max(0.0, end_s) * rate)
    seg = samples[a:b]
    n = max(64, int(FRAME_S * rate))
    starts = list(range(0, max(1, len(seg) - n + 1), n))
    if len(starts) > MAX_FRAMES:
        step = len(starts) / MAX_FRAMES
        starts = [starts[int(i * step)] for i in range(MAX_FRAMES)]
    hz = sorted(h for h in (base.measure_pitch_hz(seg[s:s + n], rate)
                            for s in starts) if h is not None)
    return hz[len(hz) // 2] if hz else None


def grade(hz, band):
    """(deviation_pct, verdict) -- verdict accept | accept_flagged | redo."""
    if hz is None or band is None:
        return None, "redo"
    lo, hi = band
    out = lo - hz if hz < lo else hz - hi if hz > hi else 0.0
    pct = 100.0 * out / (lo if hz < lo else hi)
    return round(pct, 2), ("accept" if pct <= ACCEPT_PCT else
                           "accept_flagged" if pct <= FLAG_PCT else "redo")


def _audio(src):
    """(rate, samples) from {samples, sample_rate} or {wav_path}."""
    if src.get("samples"):
        return src["sample_rate"], src["samples"]
    return base.load_wav_samples(src["wav_path"])


def measure_line(line, characters, src):
    """One receipt row (numbers included) for one line against its face."""
    cid = base._norm(line.get("onscreen"))
    band = character_band((characters or {}).get(cid))
    row = {"line_id": line.get("line_id"), "onscreen": cid,
           "band_hz": list(band) if band else None,
           "median_hz": None, "deviation_pct": None}
    if not cid or band is None:
        row.update(verdict="redo", code="CHARACTER_VOICE_UNDECLARED")
        return row
    try:
        rate, samples = _audio(src)
    except (base.VoiceMatchError, KeyError, TypeError):
        row.update(verdict="redo", code="AUDIO_UNREADABLE")
        return row
    hz = line_median_hz(samples, rate, line.get("start_s", 0.0),
                        line.get("end_s", len(samples) / float(rate)))
    pct, verdict = grade(hz, band)
    row.update(median_hz=None if hz is None else round(hz, 1),
               deviation_pct=pct, verdict=verdict)
    if hz is None:
        row["code"] = "PITCH_UNAVAILABLE"
    elif verdict == "redo":
        row["code"] = CODE
    elif verdict == "accept_flagged":
        row["flag"] = "voice %.1f Hz is %.1f%% outside %s-%s Hz" % (
            hz, pct, band[0], band[1])
    return row


def enforce(lines, characters, sources, regenerate, max_rounds=MAX_ROUNDS):
    """Measure every line; regenerate each 'redo' take until it fits.

    sources: {line_id: audio dict}. regenerate(line, attempt) -> new audio
    dict for that line (the caller owns the provider call; mock it in tests).
    A line still 'redo' after max_rounds stays failed (never keep closest).
    Returns the receipt: per-line rows with attempts, summary, outcome.
    """
    rows = []
    for line in lines:
        lid = line.get("line_id")
        src, attempts = sources[lid], []
        row = measure_line(line, characters, src)
        attempts.append({k: row[k] for k in ("median_hz", "deviation_pct",
                                              "verdict")})
        while row["verdict"] == "redo" and len(attempts) <= max_rounds \
                and row.get("code") in (CODE, "PITCH_UNAVAILABLE"):
            src = regenerate(line, len(attempts))
            row = measure_line(line, characters, src)
            attempts.append({k: row[k] for k in ("median_hz", "deviation_pct",
                                                  "verdict")})
        row["attempts"] = attempts
        row["regenerated"] = len(attempts) - 1
        rows.append(row)
    bad = [r for r in rows if r["verdict"] == "redo"]
    return {"tool": TOOL_NAME, "tool_version": TOOL_VERSION,
            "rule": {"accept_pct": ACCEPT_PCT, "flag_pct": FLAG_PCT},
            "lines": rows,
            "summary": {"lines": len(rows),
                        "accepted": sum(r["verdict"] == "accept" for r in rows),
                        "flagged": sum(r["verdict"] == "accept_flagged"
                                       for r in rows),
                        "regenerated": sum(r["regenerated"] for r in rows),
                        "failed": len(bad)},
            "outcome": "ok" if not bad else "rejected",
            "reason_code": "VOICE_FIT_OK" if not bad else
                           "+".join(sorted({r["code"] for r in bad}))}


# ---- WW-27: identity BEYOND PITCH (the D5 input) ----------------------------
#
# WW-27 (2026-10-11): more than one character voice is audio gate D5's job, and
# D5 must judge ACTUAL voices BEYOND PITCH. A pitch band alone proves nothing: a
# single performer pitch-shifted reads as a second pitch band while still being
# ONE voice. The measurement below is pitch-INVARIANT: the harmonic content of
# the voice (the normalized overtone ratios at the take's own measured
# fundamental), so two takes of the SAME voice at DIFFERENT pitches read the same
# profile and two voices at the SAME pitch with different harmonic content read
# differently. Names, duet tags and pitch-band fit are never asked.
#
# This module measures; D5 alone delivers the verdict. TIMBRE_MIN_SEP is a
# PROPOSED acceptance rule, not a measured limit and never a number Trevor set.
# One full-song track only: a stitched voice pack is refused.

TIMBRE_MIN_SEP = 0.15        # PROPOSED: relative separation of the overtone ratios
TIMBRE_FRAME_S = 0.5         # the analysis window, from the middle of the take
TIMBRE_OVERTONES = ("h2", "h3")   # first two overtones, normalized to the fundamental
CODE_VOICE_PACK_STITCHED = "VOICE_PACK_STITCHED"
CODE_SAME_IDENTITY_PITCH_SHIFT = "SAME_IDENTITY_PITCH_SHIFT"
CODE_SAME_IDENTITY_SAME_PITCH = "SAME_IDENTITY_SAME_PITCH"
CODE_ONE_IDENTITY_ONLY = "ONE_IDENTITY_ONLY"


def _timbre_window(samples, rate):
    """The analysis window: at most TIMBRE_FRAME_S, from the middle of the take."""
    n = max(64, int(TIMBRE_FRAME_S * rate))
    samples = list(samples)
    if len(samples) <= n:
        return samples
    start = (len(samples) - n) // 2
    return samples[start:start + n]


def _goertzel_power(frame, rate, freq):
    """Power at one exact frequency (Goertzel), Hann-windowed. Pure python."""
    import math
    n = len(frame)
    if n < 4 or freq <= 0.0 or freq >= rate / 2.0:
        return 0.0
    w = 2.0 * math.pi * freq / rate
    c = 2.0 * math.cos(w)
    s1 = s2 = 0.0
    for i, x in enumerate(frame):
        x = x * (0.5 - 0.5 * math.cos(2.0 * math.pi * i / (n - 1)))
        s0 = x + c * s1 - s2
        s2, s1 = s1, s0
    return max(0.0, s1 * s1 + s2 * s2 - c * s1 * s2)


#: The fundamental is refined within this fraction of the measured pitch before
#: the profile is read, so a 1-2 Hz autocorrelation error cannot slide the
#: overtone bins off the real partials (300 Hz read as 301.9 Hz would otherwise
#: miss the 600 Hz partial entirely).
F0_REFINE_PCT = 0.05
F0_REFINE_STEPS = 10


def _refine_f0(frame, rate, f0):
    """The strongest fundamental within +/-F0_REFINE_PCT of the measured pitch."""
    best, best_p = float(f0), -1.0
    for i in range(-F0_REFINE_STEPS, F0_REFINE_STEPS + 1):
        cand = float(f0) * (1.0 + (F0_REFINE_PCT / F0_REFINE_STEPS) * i)
        p = _goertzel_power(frame, rate, cand)
        if p > best_p:
            best, best_p = cand, p
    return best


def timbre_profile(samples, rate, f0):
    """The pitch-INVARIANT timbre vector: sqrt(H2/H1) and sqrt(H3/H1).

    Measured at the take's OWN fundamental (refined within F0_REFINE_PCT so a
    small pitch error cannot slide the overtone bins), so a pitch shift does not
    move it. None when no fundamental is known or nothing is there to measure."""
    if f0 is None or f0 <= 0:
        return None
    frame = _timbre_window(samples, rate)
    f0 = _refine_f0(frame, rate, f0)
    p1 = _goertzel_power(frame, rate, f0)
    if p1 <= 0.0:
        return None
    return {k: round(math.sqrt(_goertzel_power(frame, rate, mult * f0) / p1), 4)
            for k, mult in (("h2", 2.0), ("h3", 3.0))}


def identity_of(src):
    """The measured identity of ONE take: its f0 and its timbre profile."""
    rate, samples = _audio(src)
    hz = line_median_hz(samples, rate, 0.0, len(samples) / float(rate))
    return {"median_hz": None if hz is None else round(hz, 1),
            "timbre": timbre_profile(samples, rate, hz) if hz else None}


def timbre_separation(a, b):
    """How far apart two takes' TIMBRE profiles are: the max absolute difference
    over the normalized overtone ratios. None when either profile is missing."""
    ta, tb = (a or {}).get("timbre"), (b or {}).get("timbre")
    if not isinstance(ta, dict) or not isinstance(tb, dict):
        return None
    return round(max(abs(ta[k] - tb[k]) for k in TIMBRE_OVERTONES), 4)


def distinct_identity(a, b, timbre_tol=TIMBRE_MIN_SEP):
    """True when two takes are two AUDIBLE identities. TIMBRE decides.

    A pitch difference ALONE -- one performer pitch-shifted -- is the SAME
    identity: "different pitch, same timbre" is ONE voice. "Same pitch,
    different timbre" is TWO. Names, duet tags and pitch-band fit are never
    asked."""
    sep = timbre_separation(a, b)
    return sep is not None and sep > timbre_tol


def identity_receipt(lines, characters, sources, tracks=1, voice_pack=None):
    """WW-27: the identity receipt D5 is judged from, BEYOND PITCH.

    One row per line (measured f0, the pitch-invariant timbre profile) and one
    row per SPEAKER PAIR (the pitch delta and the timbre separation). Two
    characters are two audible identities only when their timbre separates; a
    pitch delta alone refuses as SAME_IDENTITY_PITCH_SHIFT. ONE full-song track
    only: a stitched voice pack refuses as VOICE_PACK_STITCHED. This measures no
    audio-quality outcome of its own -- D5 alone confirms the delivered voices.
    """
    rows, by_char = [], {}
    for line in lines:
        cid = base._norm(line.get("onscreen") or line.get("speaker"))
        src = (sources or {}).get(line.get("line_id"))
        ident = identity_of(src) if src else {"median_hz": None, "timbre": None}
        who = (characters or {}).get(cid) if isinstance(characters, dict) else None
        rows.append({"line_id": line.get("line_id"), "speaker": cid,
                     "gender": who.get("gender") if isinstance(who, dict) else None,
                     "median_hz": ident["median_hz"], "timbre": ident["timbre"]})
        if cid and ident["timbre"] is not None and cid not in by_char:
            by_char[cid] = ident
    speakers = sorted(by_char)
    pairs = []
    for i in range(len(speakers)):
        for j in range(i + 1, len(speakers)):
            a, b = by_char[speakers[i]], by_char[speakers[j]]
            delta = (None if a["median_hz"] is None or b["median_hz"] is None
                     else round(abs(a["median_hz"] - b["median_hz"]), 1))
            pairs.append({"a": speakers[i], "b": speakers[j],
                          "pitch_delta_hz": delta,
                          "timbre_sep": timbre_separation(a, b),
                          "distinct": distinct_identity(a, b)})
    reasons, code = [], "VOICE_IDENTITY_OK"
    if voice_pack or (isinstance(tracks, int) and not isinstance(tracks, bool) and tracks > 1):
        code = CODE_VOICE_PACK_STITCHED
        reasons.append("the take is a stitched voice pack (%r tracks), not one full-song "
                       "track; the stitched voice-pack revival is not approved" % (tracks,))
    elif len(speakers) < 2:
        code = CODE_ONE_IDENTITY_ONLY
        reasons.append("%d character voice(s) measured; more than one character voice is "
                       "required" % len(speakers))
    else:
        shift = [p for p in pairs if not p["distinct"] and p["pitch_delta_hz"]]
        same = [p for p in pairs if not p["distinct"] and not p["pitch_delta_hz"]]
        if shift:
            code = CODE_SAME_IDENTITY_PITCH_SHIFT
            reasons.append("%s and %s differ in pitch (%.1f Hz) but not in timbre (%.4f): a "
                           "pitch shift is ONE performer, not two audible identities"
                           % (shift[0]["a"], shift[0]["b"], shift[0]["pitch_delta_hz"],
                              shift[0]["timbre_sep"]))
        elif same:
            code = CODE_SAME_IDENTITY_SAME_PITCH
            reasons.append("%s and %s share one timbre profile (%.4f): the same voice twice, "
                           "not two characters" % (same[0]["a"], same[0]["b"],
                                                   same[0]["timbre_sep"]))
    return {"tool": TOOL_NAME, "tool_version": TOOL_VERSION,
            "rule": {"timbre_min_sep": TIMBRE_MIN_SEP},
            "pitch_alone_is_not_identity": True,
            "lines": rows, "speakers": speakers, "pairs": pairs,
            "identity_count": len(speakers),
            "outcome": "ok" if not reasons else "rejected",
            "reason_code": code, "reasons": reasons}
