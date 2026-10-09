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

AMENDED (Trevor order 1150 part G amend, review item G2 = Appendix A of
the Suno singing root-cause review, 2026-10-08, doc 04):
the take series and the four receipt shares are measured by Appendix A's
own recipe -- score = voiced_per_s + held_per_s over a 4 s window centred
on t; a voiced second is sung (or rapped) when score >= A_SCORE_MIN (0.80);
single-second breath holes are bridged; a take has REAL singing only with
one sung stretch of >= MIN_REAL_SINGING_STRETCH_S (6 s). The pcr/quant/
steady rule above stays as the window-level classifier for the existing
controls; the Appendix A series decides the take verdict and the shares.
The recipe is the separated VOCAL stem only -- require_vocal_stem() refuses
an instrumental by name or explicit kind (instrumentals read as sung).

API:
  detect_track(stem_path)      -> per-second sung votes, sung_pct_of_runtime,
                                  sung_pct_of_voiced, confidence, method,
                                  Appendix A series (shares, stretches,
                                  take_verdict REAL_SINGING/NO_SINGING)
  share_for_stem(stem_path)    -> the four-way record receipts print (G5):
                                  {"sung_share","spoken_share","rap_share",
                                   "no_voice_share" (sum 1), "confidence",
                                   "method","detector","detector_version",
                                   "runtime_s", "share_source":"measured"}
                                  (+ append the take verdict fields)
  split_metered(record, s)     -> re-tag measured metered seconds as rap
  require_vocal_stem(path)     -> refuse an instrumental stem
  score_window(stem, a, b)     -> one window, for line-level QC
  calibrate(fixtures)          -> control scores + >= 90% classification

No network, no provider, no spend, no paid call, no absolute operator path
in the module body (fixtures are passed in by the caller).
"""
from __future__ import annotations

import subprocess

import numpy as np

# Skill 75 load governor: every heavy local job goes through it (see load_governor/).
import os as _gos, sys as _gsys
_gcore = _gos.path.abspath(_gos.path.join(_gos.path.dirname(__file__), '..'))
if _gcore not in _gsys.path:
    _gsys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402

TOOL_NAME = "singing_detector"
TOOL_VERSION = "2.1.0"
METHOD = "pitch-stability+voicing+note-alignment"
SCHEMA_VERSION = "blackceo.singing-detector/v1"
SOURCE = ("Trevor order 2026-10-08 11:35 Part G G3; amended by "
          "TREVOR-ORDER-1150-partG-amend.md (review item G2: "
          "Appendix A recipe, take verdict, instrumental refusal)")

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
#: Short lines (under WINDOW_S) are judged by a second, shorter window pass.
SHORT_WINDOW_S = 4.0
#: pcr needed when the quantisation test cannot be measured (fewer than 3 big intervals).
SHORT_PCR_MIN = 0.85
HOP_S = 1.0
#: Voiced-frame floor for one window to score at all (20/100 ms).
MIN_VOICED_FRAMES = 20

# ---- Appendix A (TREVOR-ORDER-1150-partG-amend, review item G2) ------------
#: Appendix A recipe, the DECIDING rule for the take series and the shares:
#:   score = voiced_per_s + held_per_s over a 4 s window centred on t;
#:   held = frames inside steady stretches of >= 150 ms where every frame
#:   stays within 0.5 semitone of the stretch's running median.
#: A voiced second is sung (or rapped) when score >= A_SCORE_MIN.
A_SCORE_MIN = 0.80
A_WINDOW_BACK_S = 1.5      # 4 s window centred on t: [t-1.5, t+2.5]
A_WINDOW_FWD_S = 2.5
A_HELD_TOL = 0.5           # semitones inside one held stretch
A_HELD_MIN_FRAMES = 15     # 150 ms at the 10 ms hop
A_VOICED_FRAME_FRAC = 0.3  # a second is voiced when >= 30% of frames are loud
#: Take-level verdict (Appendix A step 7): real singing needs ONE sung
#: stretch this long. Same number as spoken_share's NO_REAL_SINGING_STRETCH_S.
MIN_REAL_SINGING_STRETCH_S = 6
VERDICT_REAL_SINGING = "REAL_SINGING"
VERDICT_NO_SINGING = "NO_SINGING"

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
        raw = _LG.run_ffmpeg(
            [ffmpeg, "-v", "error", "-threads", "4", "-i", str(stem_path),
             "-f", "s16le", "-ac", "1", "-ar", str(sr), "-"],
            "singing-detector-decode", capture_output=True, check=True).stdout
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
    # Fewer than 3 big intervals (a short line) cannot measure quantisation:
    # do not fail it on a made-up 0.25 against the 0.22 limit; demand a
    # stricter pitch-class concentration instead.
    quant = float(np.mean(np.abs(big - np.round(big)))) if len(big) > 2 else None
    steady = float(d.sum() / nv)
    sust = float(d[d >= SUSTAIN_FRAMES].sum() / nv)
    guarded = (len(nt) >= MIN_NOTES_PER_WINDOW
               and nps >= MIN_NOTES_PER_SECOND)
    quant_ok = (pcr >= SHORT_PCR_MIN) if quant is None else quant <= QUANT_MAX
    sung = bool(guarded and pcr >= PCR_MIN and quant_ok
                and steady >= STEADY_MIN)
    z.update(score=round(rng, 2), pcr=round(pcr, 3),
             quant=round(0.25 if quant is None else quant, 3), quant_measured=quant is not None,
             steady=round(steady, 3), sust=round(sust, 3),
             step=round(melodic_step(nt), 2), sung=sung)
    return z


def _runs(mask):
    """[(i, j), ...] over every True run of a bool array (half-open)."""
    out, i, n = [], 0, len(mask)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and mask[j + 1]:
            j += 1
        out.append((i, j + 1))
        i = j + 1
    return out


def yin_semitones_a(x, thr=0.15, sr=SR, hop=160, win=800,
                     fmin=70.0, fmax=900.0):
    """Appendix A's YIN front-end, verbatim (10 ms hop, 50 ms window,
    70-900 Hz, dip threshold 0.15 with a best-dip accept up to 0.35,
    parabolic refinement). Returns (semitones re 55 Hz with NaN unvoiced,
    rms per frame). The Appendix A series must run on THIS track: the
    module's own f0_track uses a finer interior gate and shorter window,
    and its series drifts off the published numbers (O3a 3 s vs 6 s)."""
    n = (len(x) - win) // hop
    tmin, tmax = int(sr / fmax), int(sr / fmin)
    st = np.full(max(n, 0), np.nan)
    rms = np.zeros(max(n, 0))
    for c0 in range(0, n, 4000):
        idx = np.arange(c0, min(n, c0 + 4000))
        fr = np.stack([x[i * hop:i * hop + win] for i in idx]).astype(np.float64)
        fr -= fr.mean(1, keepdims=True)
        rms[idx] = np.sqrt((fr ** 2).mean(1))
        ac = np.fft.irfft(np.abs(np.fft.rfft(fr, 2048, axis=1)) ** 2,
                          2048, axis=1)[:, :tmax + 2]
        eh = np.concatenate([np.zeros((len(idx), 1)), np.cumsum(fr ** 2, 1)], 1)
        t = np.arange(tmax + 2)
        d = eh[:, win - t] + (eh[:, -1:] - eh[:, t]) - 2 * ac
        d[:, 0] = 0
        cm = np.ones_like(d)
        cm[:, 1:] = d[:, 1:] / np.maximum(
            np.cumsum(d[:, 1:], 1) / np.arange(1, d.shape[1]), 1e-12)
        for j, i in enumerate(idx):
            row = cm[j, tmin:tmax]
            b = np.where(row < thr)[0]
            if len(b):
                k = b[0]
                while k + 1 < len(row) and row[k + 1] < row[k]:
                    k += 1
            else:
                k = int(row.argmin())
                if row[k] > 0.35:
                    continue
            k += tmin
            y0, y1, y2 = cm[j, k - 1], cm[j, k], cm[j, k + 1]
            dd = y0 - 2 * y1 + y2
            st[i] = 12 * np.log2(
                sr / (k + (0.5 * (y0 - y2) / dd if dd else 0)) / 55.0)
    return st, rms


def held_frames(seg):
    """Appendix A step 4 held count: frames inside steady stretches of at
    least A_HELD_MIN_FRAMES (150 ms) where every frame stays within
    A_HELD_TOL (0.5 semitone) of the stretch's running median. Octave
    jumps inside a voiced run are folded by 12 semitones toward the run
    median first (step 3). NaN frames close a run (unvoiced)."""
    seg = seg.copy()
    held = 0
    voiced = ~np.isnan(seg)
    for p, q in _runs(voiced):
        run = seg[p:q]
        m = np.median(run)
        run[run - m > 9] -= 12
        run[m - run > 9] += 12
        k = 0
        while k < len(run):
            e, vals = k, [run[k]]
            while e + 1 < len(run) and abs(run[e + 1] - np.median(vals)) <= A_HELD_TOL:
                e += 1
                vals.append(run[e])
            if e - k + 1 >= A_HELD_MIN_FRAMES:
                held += e - k + 1
            k = e + 1
    return held


def appendix_a_score(st, a, b, fps=100.0):
    """Appendix A score for [a, b): voiced_per_s + held_per_s.

    voiced_per_s = voiced frames / ALL frames in the window (seconds carry
    silence: a window of half voice can not reach 1.0 by voicing alone).
    held_per_s = held frames (held_frames) / all frames in the window.
    """
    seg = st[int(a * fps):int(b * fps)]
    total = len(seg)
    if total <= 0:
        return 0.0
    voiced = int((~np.isnan(seg)).sum())
    return (voiced + held_frames(seg)) / float(total)


def appendix_a_sung_seconds(st, rms, n, hop_s=HOP_S):
    """Per-second Appendix A series -> (sung, voiced) bool arrays.

    The loudness gate is Appendix A's own (step 2): a frame is loud when
    its RMS is at least 6% of the 95th-percentile RMS (about -24 dB). A
    second is VOICED when at least A_VOICED_FRAME_FRAC (30%) of its frames
    are loud. A voiced second is SUNG when its 4 s window score >=
    A_SCORE_MIN. Single-second holes between two sung seconds are bridged
    (breaths, step 6).
    """
    if len(rms):
        gate = max(float(np.percentile(rms, 95)) * 0.06, 1e-4)
    else:
        gate = 1e-4
    # Appendix A applies ITS gate to ITS OWN pitch track (step 2); the
    # caller passes yin_semitones_a()'s st/rms so the numbers reproduce.
    st_a = st.copy()
    st_a[rms < gate] = np.nan
    voiced = np.array([(rms[i * 100:(i + 1) * 100] >= gate).mean()
                       >= A_VOICED_FRAME_FRAC for i in range(n)])
    sung = np.zeros(n, bool)
    for i in range(n):
        if voiced[i] and appendix_a_score(
                st_a, max(0.0, i - A_WINDOW_BACK_S),
                min(float(n), i + A_WINDOW_FWD_S)) >= A_SCORE_MIN:
            sung[i] = True
    for i in range(1, n - 1):  # breaths
        if not sung[i] and sung[i - 1] and sung[i + 1]:
            sung[i] = True
    return sung, voiced


def sung_stretches(sung):
    """[[start_s, end_s], ...] from a per-second bool series."""
    return [[int(p), int(q)] for p, q in _runs(sung)]


def take_verdict(longest_stretch_s,
                 minimum_s=MIN_REAL_SINGING_STRETCH_S):
    """Appendix A step 7: REAL_SINGING only with one sung stretch >= 6 s."""
    ok = float(longest_stretch_s) + 1e-9 >= float(minimum_s)
    return VERDICT_REAL_SINGING if ok else VERDICT_NO_SINGING


_INSTRUMENTAL_MARKERS = ("instrumental", "no-vocal", "no_vocal", "karaoke")


class InstrumentalRefused(RuntimeError):
    """Raised when the stem handed in is (or names) an instrumental.

    Appendix A 5.1: the recipe is the separated VOCAL stem only -- piano
    and keys read as sung on instrumental stems (Chapter 5 instrumentals
    scored 53-83% "sung"). This refusal is fail-closed: an unknown or
    explicitly non-vocal stem kind never measures.
    """

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


_VOCAL_KINDS = ("vocal", "vocals", "vocal-stem", "vocal_stem", "lead-vocal",
                "lead_vocal", "lead-vocal-stem", "lead_vocal_stem")


def require_vocal_stem(stem_path, stem_kind=None):
    """Refuse an instrumental stem (Appendix A 5.1, the 'refuse if handed
    the instrumental' requirement).

    Two signals, both fail-closed: an explicit ``stem_kind`` that is not a
    vocal-stem kind raises INSTRUMENTAL_REFUSED, and a file name carrying
    an instrumental marker raises the same. None/unknown kinds pass only
    when the NAME is clean -- the caller knows which Suno separate-vocals
    file it downloaded (the `_0` vocal file).
    """
    if stem_kind is not None:
        kind = str(stem_kind).strip().lower()
        if kind and kind not in _VOCAL_KINDS:
            raise InstrumentalRefused(
                "INSTRUMENTAL_REFUSED",
                "stem kind %r is not a vocal stem; Appendix A measures the "
                "separated vocal stem only (instrumentals read as sung)"
                % (stem_kind,))
    name = str(stem_path).lower()
    for marker in _INSTRUMENTAL_MARKERS:
        if marker in name:
            raise InstrumentalRefused(
                "INSTRUMENTAL_REFUSED",
                "stem path names an instrumental (%r); Appendix A measures "
                "the separated vocal stem only" % (marker,))
    return True


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


@_LG.heavy("singing-detector")
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
    # short-line pass: a sung line under WINDOW_S is diluted in an 8 s window
    # of speech/silence; a 4 s window sung by EVERY short window over a
    # second also counts (strict: all agree, not half).
    if win > SHORT_WINDOW_S:
        v4, c4 = np.zeros(n), np.zeros(n)
        for a in np.arange(0, max(dur - SHORT_WINDOW_S, 0) + 1e-9, hop):
            r = score_window(st, a, min(a + SHORT_WINDOW_S, dur))
            lo, hi = int(a), min(int(a + SHORT_WINDOW_S), n)
            c4[lo:hi] += 1
            v4[lo:hi] += r["sung"]
        sung = sung | ((v4 == c4) & (c4 > 0) & voiced)
    sung_s = int(sung.sum())
    voiced_s = int(voiced.sum())
    # ---- Appendix A series (the take verdict + the four receipt shares) ----
    st_a, rms_a = yin_semitones_a(x)
    a_sung, a_voiced = appendix_a_sung_seconds(st_a, rms_a, n)
    a_sung_s = int(a_sung.sum())
    a_voiced_s = int(a_voiced.sum())
    stretches = sung_stretches(a_sung)
    longest = max([q - p for p, q in stretches], default=0)
    # four measured runtime shares (Appendix A step 8). Rap is metered
    # time; nothing here re-tags by lyric, so metred-from-tags is added by
    # the caller parsing 'rap' lines -- the residual is sung.
    no_voice_s = n - a_voiced_s
    a_spoken_s = a_voiced_s - a_sung_s
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
        # ---- Appendix A (order 1150 amend, review G2) ----
        "appendix_a_sung_s": a_sung_s,
        "appendix_a_voiced_s": a_voiced_s,
        "appendix_a_sung_share": round(a_sung_s / max(n, 1), 6),
        "appendix_a_spoken_share": round(a_spoken_s / max(n, 1), 6),
        "appendix_a_rap_share": 0.0,
        "appendix_a_no_voice_share": round(no_voice_s / max(n, 1), 6),
        "appendix_a_no_voice_s": int(no_voice_s),
        "appendix_a_sung_pct": round(100.0 * a_sung_s / max(n, 1), 1),
        "appendix_a_sung_pct_of_voiced": round(
            100.0 * a_sung_s / max(a_voiced_s, 1), 1),
        "sung_seconds_indexes": [int(i) for i in np.where(a_sung)[0]],
        "sung_stretches": stretches,
        "longest_sung_stretch_s": int(longest),
        "real_singing": take_verdict(longest) == VERDICT_REAL_SINGING,
        "take_verdict": take_verdict(longest),
    }


@_LG.heavy("singing-detector")
def share_for_stem(stem_path, ffmpeg="ffmpeg", stem_kind=None):
    """The record receipts print (G5): the MEASURED four-way share record.

    Amended (order 1150 part G amend, review G2/G8): the record carries the
    FOUR runtime shares from the Appendix A series -- sung, spoken, rap,
    no-voice -- which add up to 1, plus the detector name/version,
    confidence and runtime, so ``receipt_evidence.measured_share()``
    accepts it and the receipt can print measured seconds as well as
    percent. `labelled time` may never appear here -- this function has no
    lyric/label input at all, which is the whole point.

    Rap is 0.0 here: metered seconds are split onto rap by lyric tags
    AFTER measuring (Appendix A step 8 -- tags may only split metered time,
    they never assert singing), so the detector reports the residual as
    sung. The caller re-tags with ``split_metered(record, rap_seconds)``.

    Refuses an instrumental stem by name or explicit ``stem_kind``
    (Appendix A 5.1).
    """
    require_vocal_stem(stem_path, stem_kind=stem_kind)
    r = detect_track(stem_path, ffmpeg=ffmpeg)
    return {
        "sung_share": r["appendix_a_sung_share"],
        "spoken_share": r["appendix_a_spoken_share"],
        "rap_share": r["appendix_a_rap_share"],
        "no_voice_share": r["appendix_a_no_voice_share"],
        "sung_pct": r["appendix_a_sung_pct"],
        "sung_pct_of_voiced": r["appendix_a_sung_pct_of_voiced"],
        "spoken_pct": round(100.0 * r["appendix_a_spoken_share"], 1),
        "no_voice_pct": round(100.0 * r["appendix_a_no_voice_share"], 1),
        "sung_s": r["appendix_a_sung_s"],
        "spoken_s": r["appendix_a_voiced_s"] - r["appendix_a_sung_s"],
        "rap_s": 0,
        "no_voice_s": r["appendix_a_no_voice_s"],
        "confidence": r["confidence"],
        "method": r["method"],
        "detector": r["detector"],
        "detector_version": r["detector_version"],
        "schema_version": r["schema_version"],
        "share_source": "measured",
        "runtime_s": r["runtime_s"],
        "voiced_s": r["appendix_a_voiced_s"],
        "take_verdict": r["take_verdict"],
        "longest_sung_stretch_s": r["longest_sung_stretch_s"],
        "sung_stretches": r["sung_stretches"],
    }


def split_metered(record, rap_seconds):
    """Re-tag measured metered seconds as RAP (Appendix A step 8).

    Tags split METERED time between sung and rap; they never assert
    singing. ``rap_seconds`` is the metered time inside lines tagged rap
    (already measured sung-or-rap). Returns a copy of the record with the
    four shares still summing to 1.
    """
    rec = dict(record)
    rap_s = float(rap_seconds)
    sung_s = float(rec["sung_s"])
    if rap_s < 0 or rap_s > sung_s + 1e-6:
        raise ValueError("rap_seconds %.3f outside 0..%s" % (rap_s, sung_s))
    sung_s -= rap_s
    spoken_s = float(rec["spoken_s"])
    no_voice_s = float(rec["no_voice_s"])
    total = sung_s + spoken_s + rap_s + no_voice_s
    if total <= 0:
        raise ValueError("record carries no seconds to re-tag")
    for name, secs in (("sung", sung_s), ("spoken", spoken_s),
                       ("rap", rap_s), ("no_voice", no_voice_s)):
        rec["%s_s" % name] = round(secs, 3)
        rec["%s_share" % name] = round(secs / total, 6)
        rec["%s_pct" % name] = round(100.0 * secs / total, 1)
    return rec


@_LG.heavy("singing-detector")
def score_stem_window(stem_path, a, b, ffmpeg="ffmpeg"):
    """Line-level QC: one window of one stem.

    Carries BOTH rules: the pcr/quant/steady window classifier, and the
    Appendix A score for the same window (voiced_per_s + held_per_s,
    sung when >= A_SCORE_MIN) -- line-level output per the amend order.
    """
    x = decode_stem(stem_path, ffmpeg=ffmpeg)
    st, _rms, _gate = f0_track(x)
    out = score_window(st, a, b)
    a_score = appendix_a_score(st, a, b)
    out["appendix_a_score"] = round(a_score, 3)
    out["appendix_a_sung"] = bool(a_score >= A_SCORE_MIN)
    return out


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
    "A_HELD_MIN_FRAMES",
    "A_HELD_TOL",
    "A_SCORE_MIN",
    "A_VOICED_FRAME_FRAC",
    "A_WINDOW_BACK_S",
    "A_WINDOW_FWD_S",
    "HOP_S",
    "InstrumentalRefused",
    "LoadGuardError",
    "METHOD",
    "MIN_REAL_SINGING_STRETCH_S",
    "VERDICT_NO_SINGING",
    "VERDICT_REAL_SINGING",
    "appendix_a_score",
    "appendix_a_sung_seconds",
    "held_frames",
    "require_vocal_stem",
    "split_metered",
    "sung_stretches",
    "take_verdict",
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
