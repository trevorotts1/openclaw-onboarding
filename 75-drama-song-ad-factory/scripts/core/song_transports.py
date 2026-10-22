#!/usr/bin/env python3
"""song_transports: the PRODUCTION measure/save transports for song_choices.

Why this module exists
----------------------
``song_choices.cmd_generate`` correctly refuses an empty ``measure`` or
``save`` transport -- a take judged on no measurements, or a hook gate that
never ran, is the silent no-op that guard exists to reject. But nothing in the
tree supplied real ones, so ``song_choices.py generate`` (the command the
stage runbook hands agents) refused every run with "the production run needs a
real measure transport" and the music stage could never finish on a clean
install.

This module fills that gap with measurements taken from the audio itself:

  * ``make_measure(take)`` -> the measured fields ``judge_take`` reads
  * ``make_save(run_dir)`` -> every paid take's audio/measurements, kept
  * ``make_timings``      -> the ONE word-timing step (audio_c3.lyric_timing)
  * ``build_pace_plan``   -> the two mandatory, distinct pace seams

Everything is measured off the decoded waveform with numpy + ffmpeg, through
the skill's own load governor. Nothing is inferred from section labels, and a
measurement that cannot be taken is reported as MISSING (which blocks a PASS
rather than granting one).

stdlib + numpy + ffmpeg only. No network, no spend.
"""
from __future__ import annotations

import json
import os
import shutil
import sys

_CORE = os.path.dirname(os.path.abspath(__file__))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import load_governor as _LG  # noqa: E402

TOOL_NAME = "song_transports"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.song-transports/v1"

SR = 16000          # decode rate, the same the singing detector decodes at
HOP_S = 0.05        # onset/rms hop


class TransportError(RuntimeError):
    """A measurement that could not be taken. Never a pass."""


# ---------------------------------------------------------------- decode ---
def _ffmpeg():
    return os.environ.get("DSAF_FFMPEG") or "ffmpeg"


def _decode_mono(path, sr=SR):
    """Decode any audio file to a mono float32 numpy array at ``sr``."""
    import numpy as np
    if not os.path.isfile(path):
        raise TransportError("no audio at %r" % (path,))
    argv = [_ffmpeg(), "-v", "error", "-i", path, "-f", "s16le",
            "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(sr), "-"]
    try:
        proc = _LG.run_ffmpeg(argv, "song-transports-decode", capture_output=True)
    except FileNotFoundError as e:
        raise TransportError("FFMPEG_MISSING: %s" % e) from e
    if proc.returncode != 0:
        raise TransportError("ffmpeg decode failed: %s"
                             % (proc.stderr or b"").decode("utf-8", "replace")[:300])
    if not proc.stdout:
        raise TransportError("decoded zero bytes from %r" % (path,))
    return np.frombuffer(proc.stdout, dtype="<i2").astype("float32") / 32768.0


# ----------------------------------------------------------- measurement ---
def _db(x):
    import math
    return 20.0 * math.log10(max(float(x), 1e-9))


def rms_dbfs(seg):
    import numpy as np
    if len(seg) == 0:
        return -120.0
    return _db(float(np.sqrt(np.mean(np.square(seg)))))


def onset_rate_per_s(seg, sr=SR, hop_s=HOP_S):
    """Onsets per second from a short-time energy rise.

    An onset is a frame whose energy rises above the median POSITIVE rise of
    the same window -- a self-relative threshold, so the rate does not depend
    on the recording level. Steady material has no positive rises and scores
    0; a pulsed passage scores roughly one onset per pulse; a half-time passage
    scores about half what a busy one does, which is the comparison
    ``pace_change`` makes across its three windows. It is a rate, not a tempo,
    so it needs no beat tracker.
    """
    import numpy as np
    hop = max(1, int(hop_s * sr))
    n = len(seg) // hop
    if n < 3:
        return 0.0
    frames = np.square(seg[:n * hop]).reshape(n, hop).mean(axis=1)
    rise = np.diff(frames)
    positive = rise[rise > 0]
    if len(positive) < 3:
        return 0.0
    floor = float(np.median(positive))
    if floor <= 0:
        return 0.0
    onsets = int(np.sum(rise > floor))
    return round(onsets / (n * hop_s), 3)


def window_evidence(x, a, b, sr=SR):
    """The {onset_rate_per_s, rms_dbfs} pair pace_change reads, for [a, b]."""
    a_i, b_i = int(max(0.0, a) * sr), int(max(0.0, b) * sr)
    seg = x[a_i:b_i]
    if len(seg) < sr // 4:
        raise TransportError("window %.2f-%.2f s is too short to measure" % (a, b))
    return {"onset_rate_per_s": onset_rate_per_s(seg), "rms_dbfs": round(rms_dbfs(seg), 3)}


def music_under_speech_ratio(x, voice_seconds, sr=SR):
    """Music level under speech / music level under singing.

    Both sides use the same RMS measure, so the ratio is scale-free.
    ``voice_seconds`` is [(start, end, delivery)]. When either side has no
    measured seconds the ratio is None -- missing evidence, never a made-up 1.0.
    """
    import numpy as np

    def _level(kind):
        parts = [x[int(max(0, s) * sr):int(max(0, e) * sr)]
                 for s, e, d in voice_seconds if d == kind]
        parts = [p for p in parts if len(p)]
        if not parts:
            return None
        return float(np.sqrt(np.mean(np.square(np.concatenate(parts)))))

    spoken, sung = _level("spoken"), _level("sung")
    if spoken is None or sung is None or sung <= 0:
        return None
    return round(spoken / sung, 3)


def tail_rms_dbfs(x, tail_s=2.0, sr=SR):
    """RMS of the final ``tail_s`` seconds: the clean-ending gate's number."""
    n = int(max(1, tail_s * sr))
    return round(rms_dbfs(x[-n:]), 3)


# ---------------------------------------------------------------- segments ---
def segments_from_detector(rec, aligned_words=None):
    """Detector sung seconds -> the ``measured`` segments judge_take reads.

    Aligned words carry no delivery label: Suno returns where each word sits,
    not whether it was sung. Classifying them by their literal ``delivery``
    field (absent) defaulted EVERY word to "spoken", which made the aligned
    basis report a spoken share the detector never measured. A word is sung
    when its start falls inside a second the detector measured as sung -- that
    is the one authority on which seconds are voice-as-song.
    """
    sung_idx = rec.get("sung_seconds_indexes") or []
    runtime = float(rec.get("runtime_s") or 0)
    if runtime <= 0:
        raise TransportError("the detector reported no runtime")
    flags = [False] * int(round(runtime))
    for i in sung_idx:
        if 0 <= int(i) < len(flags):
            flags[int(i)] = True
    segs, start = [], 0
    cur = flags[0] if flags else False
    for i in range(1, len(flags)):
        if flags[i] != cur:
            segs.append({"delivery": "sung" if cur else "spoken",
                         "start": float(start), "end": float(i),
                         "source": "measured"})
            start, cur = i, flags[i]
    if flags:
        segs.append({"delivery": "sung" if cur else "spoken",
                     "start": float(start), "end": float(len(flags)),
                     "source": "measured"})
    if aligned_words:
        def _sung_at(t):
            i = int(t)
            return bool(flags[i]) if 0 <= i < len(flags) else False

        for w in aligned_words:
            if not isinstance(w, dict):
                continue
            s, e = w.get("startS"), w.get("endS")
            if s is None or e is None:
                continue
            declared = w.get("delivery")
            delivery = (declared if declared in ("sung", "spoken")
                        else ("sung" if _sung_at(s) else "spoken"))
            segs.append({"delivery": delivery,
                         "start": float(s), "end": float(e), "source": "aligned"})
    return segs


def first_sung_second(segs):
    src = [s for s in segs
           if s.get("source") == "measured" and s.get("delivery") == "sung"]
    return round(min((s["start"] for s in src), default=0.0), 2)


# ------------------------------------------------------------- word timing ---
def make_timings(run_dir, ledger=None, run_id=None, card_receipt=None):
    """The ONE word-timing step, wired with the run's own card receipt.

    Hook, hook_placement and song_contract cannot be measured without word
    timings. Tier 1 (Suno's alignedWords) is a PAID call through kie_dispatch,
    so it needs the same F15 card receipt every other paid job needs; a receipt
    read here is attached to the sub-call's request by ``lyric_timing`` itself.

    Returns a callable ``timings(take) -> {"words": [...]}``. A take with no
    Suno provenance, or a timing step that fails, yields no words -- the judge
    then records UNMEASURED, never a PASS.
    """
    def timings(take):
        """Never raises: a timing step that cannot run yields NO words.

        ``provide_word_timings`` itself never raises to a consumer, but the
        modules it reaches can (an uninitialised spend ledger, a missing
        adapter). A measurement that could not be taken is MISSING -- the
        judge records UNMEASURED, which blocks a PASS. It is never a crash
        that takes the whole music stage down with it.
        """
        core = os.path.dirname(os.path.abspath(__file__))
        if core not in sys.path:
            sys.path.insert(0, core)
        try:
            from audio_c3 import lyric_timing as LT      # noqa: PLC0415
            receipt = card_receipt
            if receipt is None:
                receipt = _card_receipt(run_dir)
            # audio_path travels too: tier 2 transcribes the take's own file
            # and a stripped path made every local timing run crash.
            track = {k: (take or {}).get(k) for k in ("task_id", "audio_id",
                                                      "callback_url",
                                                      "audio_path", "path")
                     if (take or {}).get(k)}
            env = LT.provide_word_timings(
                dict(track, save_dir=os.path.join(run_dir, "music", "word-timings")),
                ledger_db=ledger or os.path.join(run_dir, "spend.sqlite3"),
                run_id=run_id or (os.path.basename(os.path.abspath(run_dir)) or "run"),
                card_receipt=receipt)
        except Exception as e:                           # noqa: BLE001 - never a pass
            return {"words": [], "error": "%s: %s" % (type(e).__name__,
                                                      str(e)[:200])}
        if not env.get("ok"):
            return {"words": [], "error": env.get("error_code"),
                    "detail": env.get("next_action")}
        return {"words": (env.get("timings") or {}).get("words") or [],
                "receipt": env.get("timings")}
    return timings


def _card_receipt(run_dir):
    """The run's recorded card receipt, read without importing song_choices."""
    from song_choices.song_choices import _card_receipt as _read  # noqa: PLC0415
    return _read(run_dir)


# ------------------------------------------------------------ the measure ---
def make_measure(pace_plan=None, ffmpeg=None, timings=None):
    """Build the production ``measure(take)`` the song runner needs.

    ``take`` carries ``audio_path`` and may carry ``aligned_words``. Returns the
    measured-fields dict ``run_takes`` merges into the take. A take with no
    audio, or audio that cannot be measured, RAISES.

    ``timings`` is the ONE word-timing step (``make_timings``). When it is None
    and the take carries no aligned words, the measurement is still returned
    but ``aligned_words`` stays empty, which the judge reports as UNMEASURED
    rather than passing.
    """
    def measure(take):
        path = (take or {}).get("audio_path")
        if not path:
            raise TransportError("take carries no audio_path")
        if ffmpeg:
            os.environ.setdefault("DSAF_FFMPEG", ffmpeg)
        x = _decode_mono(path)
        if len(x) < SR:
            raise TransportError("audio shorter than one second")
        import singing_detector as SDet     # noqa: PLC0415
        rec = SDet.detect_track(path)
        words = list((take or {}).get("aligned_words") or [])
        take_errors = None
        if not words and timings is not None:
            try:
                got = timings(take)
                if isinstance(got, dict) and got.get("words"):
                    words = got["words"]
                elif isinstance(got, list):
                    words = got
                if isinstance(got, dict) and got.get("error") and not words:
                    take_errors = "word timings unavailable: %s" % got["error"]
            except Exception as e:          # noqa: BLE001 - never a silent pass
                take_errors = "word timings unavailable: %s: %s" % (
                    type(e).__name__, str(e)[:200])
                words = []
        segs = segments_from_detector(rec, words)
        out = {
            "segments": segs,
            "aligned_words": words,
            "duration_s": round(len(x) / float(SR), 2),
            "detector": "%s %s" % (rec.get("detector"), rec.get("detector_version")),
            "first_sung_s": first_sung_second(segs),
            "tail_rms_dbfs": tail_rms_dbfs(x),
            "music_under_speech_ratio": music_under_speech_ratio(
                x, [(s["start"], s["end"], s["delivery"]) for s in segs
                    if s.get("source") == "measured"]),
        }
        if take_errors:
            out["timings_error"] = take_errors
        order = pace_plan or {}
        if isinstance(order, dict) and order.get("boundary_s") is not None \
                and order.get("return_boundary_s") is not None:
            dur = out["duration_s"]
            b, r = float(order["boundary_s"]), float(order["return_boundary_s"])
            try:
                out["pace_before"] = window_evidence(x, 0.0, max(1.0, b - 0.5))
                out["pace_problem"] = window_evidence(x, b, min(r - 0.5, b + 12.0))
                out["pace_after"] = window_evidence(x, r, min(dur, r + 12.0))
            except TransportError as e:
                out["pace_error"] = str(e)
        return out
    return measure


# --------------------------------------------------------------- the save ---
def make_save(run_dir):
    """Build the production ``save(variant, take, receipt)``: every paid take is kept.

    ``one_variant`` calls it as ``save(variant, take, receipt)``; the signature
    takes all three so a caller may also pass ``save(take, receipt)``. The take
    is filed under its own variant so the three arrangements never overwrite
    each other's evidence.

    Writes ``<run>/music/takes/<variant>/take-NN/`` holding a copy of the
    audio, the measurements, the aligned words and the receipt. Called for
    EVERY take, accepted or not: a rejected paid take is evidence, not waste.
    """
    root = os.path.join(run_dir, "music", "takes")

    def save(variant, take=None, rcpt=None):
        if take is None and isinstance(variant, dict) and "audio_path" in variant:
            variant, take = None, variant          # tolerate save(take, rcpt)
        path = (take or {}).get("audio_path")
        if not path or not os.path.isfile(path):
            return None
        vid = str((variant or {}).get("id") or "take") if isinstance(variant, dict) else "take"
        base = os.path.join(root, vid)
        os.makedirs(base, exist_ok=True)
        n = len([d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))])
        dest = os.path.join(base, "take-%02d" % (n + 1))
        os.makedirs(dest, exist_ok=True)
        kept = os.path.join(dest, os.path.basename(path))
        if os.path.abspath(kept) != os.path.abspath(path):
            shutil.copyfile(path, kept)
        for name, payload in (("take-measurements.json", take or {}),
                              ("aligned-words.json", take.get("aligned_words") or []),
                              ("receipt.json", rcpt or {})):
            with open(os.path.join(dest, name), "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, sort_keys=True, default=str)
        return dest
    return save


# ------------------------------------------------------------ pace planner --
def build_pace_plan(delivered_s, drop_s, return_s, reason=None):
    """The two mandatory, DISTINCT pace seams the dispatch refuses without.

    ``drop_s`` and ``return_s`` come from the run's own story beats -- the
    moment the pain bottoms out and the moment the solution arrives -- never a
    fixed fraction of the runtime.
    """
    try:
        d, r = float(drop_s), float(return_s)
    except (TypeError, ValueError):
        raise TransportError("PACE_SEAM_MISSING: both seams must be numbers "
                             "(got %r, %r)" % (drop_s, return_s))
    if d <= 0 or r <= 0:
        raise TransportError("PACE_SEAM_MISSING: seams must be positive seconds")
    if abs(d - r) < 0.5:
        raise TransportError("PACE_SEAM_REUSED_BOUNDARY: the drop (%.2f s) and the "
                             "return (%.2f s) are the same moment" % (d, r))
    if d >= r:
        raise TransportError("PACE_ORDER_REVERSED: the drop (%.2f s) must precede "
                             "the return (%.2f s)" % (d, r))
    if r > delivered_s:
        raise TransportError("PACE_SEAM_OUT_OF_RANGE: the return (%.2f s) sits past "
                             "the delivered length (%.2f s)" % (r, delivered_s))
    return {"boundary_s": d, "return_boundary_s": r,
            "drop_anchor": "drop", "return_anchor": "return",
            "reason": reason or ("the pain bottoms out at %.1f s; the solution "
                                 "arrives at %.1f s" % (d, r))}


def pace_plan_from_beats(beat_seconds, delivered_s):
    """Derive the two seams from the approved story's own beat timings.

    The drop is ``lowest_point``; the return is ``the_turn`` -- the same two
    anchors the hook plan uses, so pace and hook cannot disagree about where
    the story turns.
    """
    drop = (beat_seconds or {}).get("lowest_point")
    ret = (beat_seconds or {}).get("the_turn")
    if drop is None or ret is None:
        raise TransportError("the story carries no lowest_point/the_turn timing; "
                             "the pace seams cannot be placed")
    return build_pace_plan(delivered_s, drop, ret)
