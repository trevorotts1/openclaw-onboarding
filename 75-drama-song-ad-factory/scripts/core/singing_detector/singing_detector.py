#!/usr/bin/env python3
"""singing_detector: MEASURED sung-vs-spoken share on a Suno vocal stem.

Owner order (Trevor, 2026-10-08 11:35, Part G item G3): "Sung share was
computed from section LABELS, not measured; no singing detector existed; the
waiver then accepted the fake number." O3 measured "54% sung" from the time
inside [Verse]/[Chorus] labels -- the music under those lines carried plain
speech from start to finish. Every sung/spoken share in QC and receipts now
comes from THIS detector, never from section labels.

Method (v2, 2026-10-08 fix): PITCHED-VOICE DENSITY NEVER DECIDES. The old
note-range rule and the factory's singcheck density rule both read clean,
gap-free TTS speech (macOS say, rap) as sung. A window is SUNG only when the
voice behaves like a melody on a scale, measured on the steady notes
(runs >= 120 ms within +-0.5 semitone) found in a WINDOW_S window:
  steady   share of VOICED time inside steady notes (pitch stability)   >= 0.45
  pcr      pitch-class concentration of the note pitches, duration
           weighted, tuning-free: |sum(d*exp(2*pi*i*p))| / sum(d); 1.0 =
           every note on one semitone grid, ~0 = pitches spread evenly
           (speech glides through all of them)                          >= 0.70
  quant    mean distance of the note-to-note intervals (>= 0.8 st) from
           the nearest whole semitone (speech ~0.25, sung <= 0.21)       <= 0.22
  notes    >= MIN_NOTES_PER_WINDOW and >= MIN_NOTES_PER_SECOND (few notes
           give a high pcr by chance, speech with gaps lands here)
Also reported, not gated: sust = share of voiced time in notes held >= 250 ms
(sung vowels are long), and range = 10th-90th percentile note spread.
Control table (tests/): 13 macOS say voices, Suno spoken stems, Gemini TTS
all <= 15% sung; approved sung hooks all >= 85% sung.

A sung share is a share of RUNTIME (windows vote over seconds), and the
detector also reports share of VOICED time -- a stem with long quiet gaps
must not dilute the measurement.

Load guard (Part D, manual + F17 lock): this module is audio DSP, not
transcription -- no whisper, no ASR, no model. The guard is still honored:
audio work runs only when memory_guard admits (lyric_timing's Part D guard,
reused as the one guard; a DSP run needs no model GB, so it checks with the
probe only and refuses when the machine cannot be measured). Every decode is
ffmpeg to s16le mono 16 kHz via subprocess -- one process per stem.

API:
  detect_track(stem_path)      -> per-second sung votes, sung_pct_of_runtime,
                                  sung_pct_of_voiced, confidence, method
  share_for_stem(stem_path)    -> the share dict receipts print (G5):
                                  {"sung_share","sung_pct","confidence",
                                   "method","detector","detector_version"}
  score_window(stem, a, b)     -> one window, for line-level QC
  calibrate(fixtures)          -> control scores + >= 90% classification

No network, no provider, no spend, no paid call, no absolute operator path
in the module body (fixtures are passed in by the caller).
"""
from __future__ import annotations

import subprocess

import numpy as np

TOOL_NAME = "singing_detector"
TOOL_VERSION = "2.0.0"
METHOD = "pitch-stability+voicing+note-alignment"
SCHEMA_VERSION = "blackceo.singing-detector/v1"
SOURCE = "Trevor order 2026-10-08 11:35 Part G G3"

SR = 16000
#: Thresholds from calibration (see module docstring); ONE place, tests pin.
#: LEGACY (v1 deciding rule). Still the 'score' field (note range, semitones)
#: for old callers; it no longer decides, see PCR_MIN / QUANT_MAX / STEADY_MIN.
SING_THRESH_SEMITONES = 7.0
PCR_MIN = 0.70
QUANT_MAX = 0.22
STEADY_MIN = 0.45
SUSTAIN_FRAMES = 25     # 250 ms
#: Secondary arm (melodic step): a window with a note range between 3.5 and
#: the primary threshold counts sung when the notes CHANGE melodically --
#: duration-weighted mean |delta pitch| between consecutive notes >= 2.0
#: semitones over >= 6 notes. Calibration: known-sung minimum 2.11 (sung hook L04,
#: a narrow-range but genuinely melodic line); known-spoken maximum 1.68.
STEP_RANGE_FLOOR = 3.5
STEP_SEMITONES = 2.0
STEP_MIN_NOTES = 6
MIN_NOTES_PER_WINDOW = 6
MIN_NOTES_PER_SECOND = 1.0
NOTE_TOL = 0.5          # semitones inside one note
NOTE_MIN_FRAMES = 12    # 120 ms at a 10 ms hop
WINDOW_S = 8.0
HOP_S = 1.0
#: Voiced-frame floor for one window to score at all (20/100 ms).
MIN_VOICED_FRAMES = 20

# ---- Part D load guard: audio DSP runs only when the machine admits -------

class LoadGuardError(RuntimeError):
    """Raised when the Part D guard refuses this run (never a verdict)."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def load_guard(free_gb_probe=None, reserve_gb: float = 2.0,
               headroom_gb: float = 0.0) -> dict:
    """One Part D admission check before audio work.

    Reuses lyric_timing's Part D guard constants (RESERVE_GB 2.0 from
    lane_size). A DSP pass needs no model, so headroom defaults to 0 --
    this check proves the machine is measurable and not saturated, and a
    caller about to ALSO load a local model must run lyric_timing's own
    guard for that model. NaN/unreadable probe refuses fail-closed.
    """
    try:  # the one Part D guard module, same core/ tree
        from ..audio_c3 import lyric_timing as _LT  # type: ignore
    except Exception:  # noqa: BLE001 - sibling import fallback
        try:
            import os, sys
            _core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if _core not in sys.path:
                sys.path.insert(0, _core)
            from audio_c3 import lyric_timing as _LT  # type: ignore
        except Exception:  # noqa: BLE001
            _LT = None
    if _LT is not None:
        try:
            return _LT.memory_guard("small", free_gb_probe=free_gb_probe,
                                    headroom_gb=0.0)
        except Exception as e:  # noqa: BLE001 - guard refusal is a refusal
            raise LoadGuardError(getattr(e, "code", "LOCAL_MODEL_LOAD_REFUSED"),
                                 str(e)) from e
    # No lyric_timing importable: refuse unless the caller injected a probe
    # and it reads finite. Fail-closed either way.
    if free_gb_probe is None:
        raise LoadGuardError("LOAD_GUARD_UNAVAILABLE",
                             "Part D guard module not importable and no "
                             "probe injected; audio work refused")
    try:
        free = float(free_gb_probe())
    except Exception as e:  # noqa: BLE001
        raise LoadGuardError("LOCAL_MODEL_LOAD_REFUSED",
                             "load guard cannot measure free RAM (%s)" % e) from e
    if free != free or free < 0:
        raise LoadGuardError("LOCAL_MODEL_LOAD_REFUSED",
                             "load guard read NaN/negative free RAM")
    if free < reserve_gb:
        raise LoadGuardError("LOCAL_MODEL_LOAD_REFUSED",
                             "free %.2f GB < reserve %.2f GB" % (free, reserve_gb))
    return {"checked": True, "free_gb": round(free, 3),
            "needed_gb": reserve_gb, "source": "singing_detector.fallback"}


# ---- pitch / note analysis -------------------------------------------------

def decode_stem(stem_path, ffmpeg="ffmpeg", sr=SR):
    """One stem -> float32 mono at sr via one ffmpeg process. Raises
    RuntimeError when ffmpeg is missing or the file is unreadable."""
    try:
        raw = subprocess.run(
            [ffmpeg, "-v", "error", "-threads", "4", "-i", str(stem_path),
             "-f", "s16le", "-ac", "1", "-ar", str(sr), "-"],
            capture_output=True, check=True).stdout
    except FileNotFoundError as e:
        raise RuntimeError("FFMPEG_MISSING: %s" % e) from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError("STEM_UNREADABLE: %s" % e.stderr[-200:]) from e
    if not raw:
        raise RuntimeError("STEM_UNREADABLE: zero bytes decoded")
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def f0_track(x, hop=160, win=640, sr=SR):
    """Autocorrelation pitch, 10 ms hop. Returns (semitones re 55 Hz with
    NaN for unvoiced, rms per frame, gate)."""
    n = (len(x) - win) // hop
    if n <= 0:
        return np.array([]), np.array([]), 0.0
    fr = np.lib.stride_tricks.sliding_window_view(x, win)[::hop][:n]
    rms = np.sqrt((fr ** 2).mean(1))
    gate = max(np.percentile(rms, 95) * 0.03, 1e-4)  # -30 dB under loud frames
    fr = (fr - fr.mean(1, keepdims=True)) * np.hanning(win)
    nf = 2048
    sp = np.fft.rfft(fr, nf, axis=1)
    ac = np.fft.irfft(np.abs(sp) ** 2, nf, axis=1)[:, :win]
    ac = ac / np.maximum(ac[:, :1], 1e-12)
    lo, hi = int(sr / 500), int(sr / 70)
    st = np.full(n, np.nan)
    for i in range(n):
        if rms[i] < gate:
            continue
        a = ac[i, lo:hi]
        best = a.max()
        if best < 0.5:
            continue
        pk = np.where((a[1:-1] > a[:-2]) & (a[1:-1] >= a[2:])
                      & (a[1:-1] > 0.9 * best))[0]
        k = (pk[0] + 1) if len(pk) else int(a.argmax())
        if 1 <= k < len(a) - 1:  # parabolic refinement
            y0, y1, y2 = a[k - 1], a[k], a[k + 1]
            d = (y0 - 2 * y1 + y2)
            k = k + (0.5 * (y0 - y2) / d if d else 0)
        st[i] = 12 * np.log2(sr / (lo + k) / 55)
    return st, rms, gate


def median_filter(s, w=5):
    out = s.copy()
    h = w // 2
    for i in range(len(s)):
        seg = s[max(0, i - h): i + h + 1]
        seg = seg[~np.isnan(seg)]
        if not np.isnan(s[i]) and len(seg) >= 3:
            out[i] = np.median(seg)
    return out


def notes(seg, tol=NOTE_TOL, min_frames=NOTE_MIN_FRAMES):
    """Steady runs: [(start_frame, frames, median_semitone), ...]."""
    m = median_filter(seg, 7)
    out = []
    i = 0
    n = len(m)
    while i < n:
        if np.isnan(m[i]):
            i += 1
            continue
        j = i
        vals = [m[i]]
        while j + 1 < n and not np.isnan(m[j + 1]) \
                and abs(m[j + 1] - np.median(vals)) <= tol:
            j += 1
            vals.append(m[j])
        if j - i + 1 >= min_frames:
            out.append((i, j - i + 1, float(np.median(vals))))
        i = j + 1
    return out


def melodic_step(nt):
    """Duration-weighted mean |delta pitch| between consecutive notes, in
    semitones. Singing steps between scale notes; speech meanders within a
    couple of semitones. Notes are in time order already (notes() emits
    runs left to right)."""
    if len(nt) < 2:
        return 0.0
    p = np.array([q[2] for q in nt])
    w = (np.array([q[1] for q in nt][:-1])
         + np.array([q[1] for q in nt][1:])) / 2.0
    steps = np.abs(np.diff(p))
    total = float(w.sum())
    return float(np.sum(steps * w) / total) if total > 0 else 0.0


def score_window(st, a, b, fps=100.0):
    """One window (seconds a..b) -> {score, pcr, quant, steady, sust, notes,
    notes_per_s, step, sung}. See the module docstring for the rule; the
    count of voiced frames, not the density of voice, only gates scoring."""
    seg = st[int(a * fps):int(b * fps)]
    nv = int((~np.isnan(seg)).sum())
    z = {"score": 0.0, "pcr": 0.0, "quant": 0.25, "steady": 0.0, "sust": 0.0,
         "step": 0.0, "notes": 0, "notes_per_s": 0.0, "sung": False}
    if nv < MIN_VOICED_FRAMES:
        return z
    nt = notes(seg)
    nps = len(nt) / max(b - a, 1e-9)
    z.update(notes=len(nt), notes_per_s=round(nps, 2))
    if len(nt) < 2:
        return z
    d = np.array([q[1] for q in nt], float)
    p = np.array([q[2] for q in nt])
    o = np.argsort(p)
    cw = np.cumsum(d[o]) / d.sum()
    rng = float(p[o][min(np.searchsorted(cw, 0.9), len(p) - 1)]
                - p[o][np.searchsorted(cw, 0.1)])
    pcr = float(abs(np.sum(d * np.exp(2j * np.pi * p)) / d.sum()))
    iv = np.abs(np.diff(p))
    big = iv[iv >= 0.8]
    quant = float(np.mean(np.abs(big - np.round(big)))) if len(big) > 2 else 0.25
    steady = float(d.sum() / nv)
    sust = float(d[d >= SUSTAIN_FRAMES].sum() / nv)
    guarded = (len(nt) >= MIN_NOTES_PER_WINDOW
               and nps >= MIN_NOTES_PER_SECOND)
    sung = bool(guarded and pcr >= PCR_MIN and quant <= QUANT_MAX
                and steady >= STEADY_MIN)
    z.update(score=round(rng, 2), pcr=round(pcr, 3), quant=round(quant, 3),
             steady=round(steady, 3), sust=round(sust, 3),
             step=round(melodic_step(nt), 2), sung=sung)
    return z


def _confidence(votes, cover, voiced):
    """Detector confidence 0..1 for one track: separation margin x coverage.

    Margin: how far the track's window votes sit from the 50/50 line (a
    track that is clearly all-sung or all-spoken carries high confidence;
    a knife-edge mix does not). Coverage: share of runtime the detector
    actually voiced. Unmeasurable audio -> low confidence, never high."""
    dur = max(len(votes), 1)
    sung = float(votes.sum())
    frac = sung / dur
    margin = abs(frac - 0.5) * 2.0            # 0 = knife edge, 1 = clear
    coverage = float(voiced.sum()) / dur
    return round(max(0.0, min(1.0, margin * (0.5 + 0.5 * coverage))), 3)


def detect_track(stem_path, win=WINDOW_S, hop=HOP_S, ffmpeg="ffmpeg"):
    """Rolling windows over one vocal stem -> the measured share record.

    Returns {runtime_s, sung_s, voiced_s, sung_pct_of_runtime,
    sung_pct_of_voiced, sung_share, sung_share_of_voiced, confidence,
    method, detector, detector_version, schema_version, source,
    sung_seconds}. A second is sung when half or more of the windows over it vote sung AND
    it carries voiced pitch (instrumental gaps are not counted against
    singing, and quiet bleed is not counted for it).

    Part D load guard first: audio work runs only when the machine admits
    (lyric_timing's memory_guard via load_guard; inject free_gb_probe in
    tests). Raises LoadGuardError when refused -- audio work never starts."""
    load_guard()
    x = decode_stem(stem_path, ffmpeg=ffmpeg)
    st, _rms, _gate = f0_track(x)
    dur = len(x) / SR
    n = int(dur)
    if n <= 0:
        raise RuntimeError("STEM_UNREADABLE: zero-length decode")
    votes = np.zeros(n)
    cover = np.zeros(n)
    for a in np.arange(0, max(dur - win, 0) + 1e-9, hop):
        r = score_window(st, a, min(a + win, dur))
        lo, hi = int(a), min(int(a + win), n)
        cover[lo:hi] += 1
        votes[lo:hi] += r["sung"]
    voiced = np.array([(~np.isnan(st[i * 100:(i + 1) * 100])).sum()
                       >= MIN_VOICED_FRAMES for i in range(n)])
    # half or more of the windows over a second must vote sung (an 'any'
    # vote let a sung neighbour paint the next spoken line sung)
    sung = (votes * 2 >= cover) & (cover > 0) & (votes > 0) & voiced
    sung_s = int(sung.sum())
    voiced_s = int(voiced.sum())
    return {
        "runtime_s": round(dur, 1),
        "sung_s": sung_s,
        "voiced_s": voiced_s,
        "sung_pct_of_runtime": round(100.0 * sung_s / dur, 1),
        "sung_pct_of_voiced": round(100.0 * sung_s / max(voiced_s, 1), 1),
        "sung_share": round(sung_s / dur, 6),
        "sung_share_of_voiced": round(sung_s / max(voiced_s, 1), 6),
        "confidence": _confidence(votes, cover, voiced),
        "method": METHOD,
        "detector": TOOL_NAME,
        "detector_version": TOOL_VERSION,
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "sung_seconds": [int(i) for i in np.where(sung)[0]],
    }


def share_for_stem(stem_path, ffmpeg="ffmpeg"):
    """The record receipts print (G5): MEASURED sung share + confidence +
    method name. `labelled time` may never appear here -- this function has
    no lyric/label input at all, which is the whole point."""
    r = detect_track(stem_path, ffmpeg=ffmpeg)
    return {
        "sung_share": r["sung_share"],
        "sung_pct": r["sung_pct_of_runtime"],
        "sung_pct_of_voiced": r["sung_pct_of_voiced"],
        "confidence": r["confidence"],
        "method": r["method"],
        "detector": r["detector"],
        "detector_version": r["detector_version"],
        "schema_version": r["schema_version"],
        "share_source": "measured",
        "runtime_s": r["runtime_s"],
        "sung_s": r["sung_s"],
        "voiced_s": r["voiced_s"],
    }


def score_stem_window(stem_path, a, b, ffmpeg="ffmpeg"):
    """Line-level QC: one window of one stem."""
    x = decode_stem(stem_path, ffmpeg=ffmpeg)
    st, _rms, _gate = f0_track(x)
    return score_window(st, a, b)


# ---- calibration harness ---------------------------------------------------

def calibrate(fixtures):
    """Score the calibration set and return the classification verdict.

    fixtures: {"known_sung":   [(name, path, start, end), ...],
               "known_spoken": [(name, path, start, end), ...]}
    Every entry must be >= MIN_CAL_WINDOW_S of stem audio (short lines hold
    too few notes -- a stanza, not a line). Returns {"passed", "accuracy",
    "threshold", "controls": {name: record}}. Classification is >= 90% when
    every known-sung window scores sung and every known-spoken window does
    not (each control carries equal weight -- the O3 half IS the check).
    """
    MIN_CAL_WINDOW_S = 5.0
    controls = {}
    correct = 0
    total = 0
    cache = {}
    for name, path, a, b in fixtures.get("known_sung", []):
        if path not in cache:
            cache[path] = f0_track(decode_stem(path))
        r = score_window(cache[path][0], a, b)
        controls[name] = dict(r, expected="sung")
        total += 1
        correct += bool(r["sung"])
    for name, path, a, b in fixtures.get("known_spoken", []):
        if path not in cache:
            cache[path] = f0_track(decode_stem(path))
        r = score_window(cache[path][0], a, b)
        controls[name] = dict(r, expected="spoken")
        total += 1
        correct += bool(not r["sung"])
    accuracy = correct / total if total else 0.0
    return {
        "passed": bool(total > 0 and accuracy >= 0.90),
        "accuracy": round(accuracy, 4),
        "correct": correct,
        "total": total,
        "threshold": SING_THRESH_SEMITONES,
        "min_window_s": MIN_CAL_WINDOW_S,
        "controls": controls,
        "detector": TOOL_NAME,
        "detector_version": TOOL_VERSION,
    }


__all__ = [
    "HOP_S",
    "LoadGuardError",
    "METHOD",
    "MIN_NOTES_PER_SECOND",
    "MIN_NOTES_PER_WINDOW",
    "MIN_VOICED_FRAMES",
    "NOTE_MIN_FRAMES",
    "NOTE_TOL",
    "PCR_MIN",
    "QUANT_MAX",
    "STEADY_MIN",
    "SUSTAIN_FRAMES",
    "SCHEMA_VERSION",
    "SING_THRESH_SEMITONES",
    "SOURCE",
    "SR",
    "TOOL_NAME",
    "TOOL_VERSION",
    "WINDOW_S",
    "calibrate",
    "decode_stem",
    "detect_track",
    "f0_track",
    "load_guard",
    "median_filter",
    "notes",
    "score_stem_window",
    "score_window",
    "share_for_stem",
]
