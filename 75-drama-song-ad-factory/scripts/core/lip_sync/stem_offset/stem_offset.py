#!/usr/bin/env python3
"""Part H H1: stem-vs-mix offset, measured per track and compensated.

The separated vocal stem ran 0.066 s LATE against the full mix in the
Kiesett ad: a clip cut from the stem at time T and placed at T on the mix
timeline showed every word 0.066 s late. Sign convention used everywhere:
offset > 0 means the STEM is LATE (a sound at mix time t is at stem time
t + offset).

  measure_offset(stem, mix, rate)  -> {"offset_s", "corr"}   (cross-correlation)
  cut_plan(word_start, word_end, offset_s) -> where to cut the stem and
      where to place the clip: cut at (mix word start + offset), place at
      the line's REAL Suno timestamp minus the lead-in. Never re-timed.

Stdlib only; zero spend. ffmpeg (-threads 4) only to decode files.
"""
import array
import os
import subprocess
import tempfile

# Skill 75 load governor: every heavy local job goes through it (see load_governor/).
import os as _gos, sys as _gsys
_gcore = _gos.path.abspath(_gos.path.join(_gos.path.dirname(__file__), '..', '..'))
if _gcore not in _gsys.path:
    _gsys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402
import wave

ENV_RATE = 1000          # envelope samples per second -> 1 ms resolution
MAX_LAG_S = 0.5          # search window either side
LEAD_S = 0.35            # lead-in before the first word (H2 input spec)
TAIL_S = 0.2             # tail after the last word


def _envelope(samples, rate):
    """Mean |x| per 1/ENV_RATE s block, mean removed."""
    blk = max(1, int(round(rate / ENV_RATE)))
    n = len(samples) // blk
    env = [sum(abs(v) for v in samples[i * blk:(i + 1) * blk]) / blk
           for i in range(n)]
    m = sum(env) / len(env) if env else 0.0
    return [e - m for e in env]


def measure_offset(stem, mix, rate, max_lag_s=MAX_LAG_S):
    """Cross-correlate loudness envelopes. stem, mix: sample sequences at
    `rate` Hz (use a loud stretch). Returns offset_s (>0 = stem late) and
    the normalised correlation at that lag. ValueError on silence/short."""
    a, b = _envelope(stem, rate), _envelope(mix, rate)
    L = max_lag_s * ENV_RATE
    L = int(L)
    if len(a) <= 2 * L or len(b) <= 2 * L:
        raise ValueError("STEM_OFFSET_TOO_SHORT: need > %.1f s of audio"
                         % (2 * max_lag_s))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na < 1e-9 or nb < 1e-9:
        raise ValueError("STEM_OFFSET_SILENT: no signal to correlate")
    best, best_lag = -2.0, 0
    n = min(len(a), len(b))
    for lag in range(-L, L + 1):       # stem[i + lag] ~ mix[i]
        lo, hi = max(0, -lag), min(n, n - lag)
        s = sum(a[i + lag] * b[i] for i in range(lo, hi))
        if s > best:
            best, best_lag = s, lag
    return {"offset_s": best_lag / ENV_RATE, "corr": best / (na * nb)}


def cut_plan(word_start, word_end, offset_s, lead_s=LEAD_S, tail_s=TAIL_S):
    """Times (seconds) for one lip-sync line. word_start/end are the line's
    real Suno timestamps on the MIX timeline.

    cut_start_stem: where to cut the stem so the audio is time-true to the
    mix. place_at: where the clip goes on the mix timeline (= word_start -
    lead, the line's real timestamp, never re-timed)."""
    if not word_start < word_end:
        raise ValueError("STEM_OFFSET_BAD_LINE: start must be < end")
    lead = min(lead_s, word_start)     # cannot start before the track
    return {"cut_start_stem": word_start + offset_s - lead,
            "cut_dur": lead + (word_end - word_start) + tail_s,
            "place_at": word_start - lead, "lead_s": lead,
            "offset_s": offset_s}


def decode_mono(path, rate=8000, start=0.0, dur=None, ffmpeg="ffmpeg"):
    """Decode any audio file to a mono int sample list via ffmpeg."""
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        cmd = [ffmpeg, "-v", "error", "-y", "-threads", "4", "-ss",
               str(start)] + (["-t", str(dur)] if dur else []) + [
               "-i", path, "-ac", "1", "-ar", str(rate), tmp]
        _LG.run_ffmpeg(cmd, "stem-offset-decode", check=True, timeout=300)
        with wave.open(tmp, "rb") as w:
            return list(array.array("h", w.readframes(w.getnframes())))
    finally:
        os.unlink(tmp)


def measure_offset_files(stem_path, mix_path, start=0.0, dur=30.0, rate=8000,
                         ffmpeg="ffmpeg"):
    """File form for the pipeline: one loud stretch of both files."""
    return measure_offset(decode_mono(stem_path, rate, start, dur, ffmpeg),
                          decode_mono(mix_path, rate, start, dur, ffmpeg),
                          rate)
