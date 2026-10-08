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
"""
from __future__ import annotations

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
