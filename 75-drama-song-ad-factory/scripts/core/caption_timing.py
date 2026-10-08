#!/usr/bin/env python3
"""F18: the caption and lyric checks consume F17's measured word timings.

Manual Part F F18. One transcription step (F17
``audio_c3/lyric_timing.provide_word_timings``) feeds both QC gates:

- the CAPTION check uses the measured timing to build its cues
  (``captions`` below -> ``protected_names.build_captions``), so cue start/end
  come from the tier that actually produced word timestamps (Suno alignedWords
  -> faster-whisper local -> client cloud STT), never from an invented clock;
- the LYRIC check uses the same words as its observed side: measured words
  cover every approved line with a real timestamp, and a lyric check with
  timing bound but zero measured words FAILS (it can never invent timing).

Fail-closed: ``binding(..., timing=)`` with a bad/failed timing result yields
no usable timing (``"unavailable"`` with the refusal code) and the caller's
check reports UNAVAILABLE, never a pass. ``source`` stays visible in the
receipt so a QC reviewer can see WHICH tier produced the timing.

Called WITHOUT a receipt, these entry points measure now: the dispatcher
comes from the argument or ``DRAMA75_TIMING_DISPATCHER``, and the track from
``DRAMA75_TIMING_TRACK`` / ``DRAMA75_STATE`` (a run that recorded its Suno
generation). ``DRAMA75_TIMING_OFF=1`` is the explicit off switch. A failure to
measure is an ``ok: False`` refusal, which the caption/lyric checks turn into
UNAVAILABLE — never a pass. The checks themselves accept a receipt (or a bare
word list) and do not reach for the transcription step on their own: a
text-only call keeps working exactly as before F18.

Stdlib only; no network of its own; tests mock every tier (zero paid calls).

Run: python3 core/test_caption_lyric_timing_f18.py
"""
from __future__ import annotations

import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import protected_names  # noqa: E402  cue building uses the sheet's own words

SUNO = "suno-timestamped-lyrics"
WHISPER = "faster-whisper-local"
CLOUD = "cloud-stt"
SOURCES = (SUNO, WHISPER, CLOUD)

_WORD_RE = protected_names._tokens  # same token rule as the caption checks


def unavailable(reason_code: str, detail: str = "") -> Dict[str, Any]:
    """A timing nobody may pass on. reason_code is machine-readable."""
    out = {"ok": False, "reason_code": reason_code}
    if detail:
        out["detail"] = detail
    return out


def words_of(timing: Any) -> List[Dict[str, Any]]:
    """Normalized measured words from any timing shape; [] when there are none.

    Accepts the F17 receipt (``timings.words``/``words``), the full
    ``provide_word_timings`` envelope (``ok``/``timings``), a bare word list,
    and a failure envelope (returns []). Never raises: a malformed entry is
    dropped rather than invented into a timestamp.
    """
    if not timing:
        return []
    if isinstance(timing, list):
        src_words = timing
    elif isinstance(timing, dict):
        inner = timing.get("timings") if isinstance(timing.get("timings"),
                                                    dict) else timing
        raw = inner.get("words")
        if not isinstance(raw, list):
            return []
        src_words = raw
    else:
        return []
    out: List[Dict[str, Any]] = []
    for w in src_words:
        if not isinstance(w, dict):
            continue
        try:
            s, e = float(w.get("start")), float(w.get("end"))
        except (TypeError, ValueError):
            continue
        if e + 1e-9 < s:
            continue
        out.append({"word": str(w.get("word", "")), "start": round(s, 3),
                    "end": round(e, 3)})
    return out


def source_of(timing: Any) -> str:
    """Which tier produced these words ("" when none is recorded)."""
    if not isinstance(timing, dict):
        return ""
    inner = timing.get("timings") if isinstance(timing.get("timings"),
                                                dict) else timing
    return str(inner.get("source") or "")


def is_unavailable(timing: Any) -> bool:
    """True when this is a refusal/unavailable marker, not a receipt."""
    return isinstance(timing, dict) and timing.get("ok") is False


def _refusal(bound: Any, fallback: str = "TIMING_UNUSABLE") -> Dict[str, Any]:
    """Extract a refusal from any failure envelope shape.

    ``provide_word_timings`` failures carry ``error_code``/``next_action``;
    local refusals carry ``reason_code``/``detail``. Both land in one
    ``unavailable()`` shape so the caption/lyric checks name the real reason.
    """
    b = bound if isinstance(bound, dict) else {}
    code = str(b.get("reason_code") or b.get("error_code") or fallback)
    detail = str(b.get("detail") or b.get("next_action") or "")
    return unavailable(code, detail)


def binding(timing: Any = None) -> Dict[str, Any]:
    """Normalize what a caller hands the caption/lyric check into one receipt.

    - ``None`` + timing reachable = measure now (dispatcher from the argument
      or DRAMA75_TIMING_DISPATCHER), so the check consumes measured words.
    - ``None`` + DRAMA75_TIMING_OFF=1 = an explicit off switch -> unavailable
      TIMING_DISABLED (the check then reports UNAVAILABLE, never PASS).
    - ``None`` + nothing to dispatch with = unavailable TIMING_NOT_BOUND (the
      caller must bind a track/receipt; an unwired call is not a pass).
    - a receipt/failure envelope/wrapped envelope = passed through unchanged.
    """
    if isinstance(timing, dict):
        return timing
    if timing is not None:
        words = words_of(timing)
        if not words:
            return unavailable("TIMING_UNUSABLE",
                               "supplied timing carries no measured words")
        return {"ok": True, "timings": {"words": words,
                                        "source": source_of(timing)}}
    if os.environ.get("DRAMA75_TIMING_OFF", "") == "1":
        return unavailable("TIMING_DISABLED",
                           "DRAMA75_TIMING_OFF=1; measured timing not bound")
    return _measure_now()


def _dispatcher_from_env() -> Optional[Callable[..., Dict[str, Any]]]:
    """A dispatcher named by DRAMA75_TIMING_DISPATCHER: ``pkg.mod:attr``.

    The env value only NAMES code the operator already shipped; it never
    carries code. None when unset or unresolvable (the caller then reports
    TIMING_NOT_BOUND instead of inventing timing).
    """
    ref = os.environ.get("DRAMA75_TIMING_DISPATCHER", "")
    if not ref:
        return None
    mod, _, attr = ref.partition(":")
    if not mod or not attr:
        return None
    try:
        import importlib
        obj = getattr(importlib.import_module(mod), attr, None)
    except Exception:  # noqa: BLE001 - an unresolvable name is just "not bound"
        return None
    return obj if callable(obj) else None


def _measure_now() -> Dict[str, Any]:
    """Call the one transcription step for the track this run recorded."""
    fn = _timings_fn()
    if fn is None:
        return unavailable(
            "TIMING_NOT_BOUND",
            "no timing receipt bound and no track to measure (pass "
            "timing=, or set DRAMA75_TIMING_DISPATCHER)")
    dispatcher = _dispatcher_from_env()
    if dispatcher is None:
        return unavailable(
            "TIMING_NOT_BOUND",
            "DRAMA75_TIMING_DISPATCHER names no callable; a caption/lyric "
            "check never invents word timings")
    track = _recorded_track()
    if not track:
        return unavailable(
            "TIMING_NOT_BOUND",
            "no Suno track recorded for this run (task_id/audio_id); the "
            "measured timing step needs the generation this check judges")
    try:
        res = fn(track, dispatcher=dispatcher)
    except Exception as e:  # noqa: BLE001 - a crashing measure is a failure
        return unavailable("TIMING_MEASURE_FAILED", str(e)[:200])
    if not isinstance(res, dict):
        return unavailable("TIMING_MEASURE_FAILED", "no receipt returned")
    if res.get("ok"):
        return res
    return unavailable(str(res.get("error_code") or "TIMING_MEASURE_FAILED"),
                       str(res.get("next_action") or "")[:200])


def _timings_fn() -> Optional[Callable[..., Dict[str, Any]]]:
    """``audio_c3.lyric_timing.provide_word_timings``, imported lazily so a
    consumer never loads the transcription module to check plain text."""
    here = Path(__file__).resolve().parents[1]  # <skill>/scripts
    pkg = str(here)
    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    try:
        from audio_c3 import lyric_timing as LT  # type: ignore
    except Exception:  # noqa: BLE001 - missing module = not bound, not a pass
        return None
    return getattr(LT, "provide_word_timings", None)


def _recorded_track() -> Dict[str, Any]:
    """The one track this run already recorded (state store, receipt, env).

    Every path is read-only and each is optional: a run with nothing recorded
    gets TIMING_NOT_BOUND rather than a fabricated generation id.
    """
    for key in ("DRAMA75_TIMING_TRACK", "DRAMA75_TRACK"):
        blob = os.environ.get(key, "")
        if blob:
            try:
                t = json.loads(blob)
            except ValueError:
                t = {}
            if isinstance(t, dict) and (t.get("task_id") or t.get("audio_id")):
                return t
    state_path = os.environ.get("DRAMA75_STATE", "")
    if state_path and Path(state_path).is_file():
        try:
            blob = json.loads(Path(state_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            blob = {}
        if isinstance(blob, dict):
            track = blob.get("track") or blob.get("song") or {}
            if isinstance(track, dict) and (track.get("task_id")
                                            or track.get("audio_id")):
                return track
            if blob.get("task_id") or blob.get("audio_id"):
                return blob
    return {}


def captions(sheet: Any, timing: Any = None) -> Tuple[List[Dict[str, Any]],
                                                      Dict[str, Any]]:
    """Caption cues from the approved sheet, TIMED by measured words.

    Returns ``(cues, receipt)``. Text is always the sheet's own (never the
    recognizer's wording); the measured words supply start/end only. The
    receipt names the timing source and word count so QC can see which tier
    measured it. Unavailable timing -> no cues and ``ok: False``: the caller
    reports UNAVAILABLE, it never builds a zero-duration clock.
    """
    if is_unavailable(timing):
        bound = timing
    else:
        bound = binding(timing)
    if not isinstance(bound, dict) or bound.get("ok") is False:
        return [], _refusal(bound)
    words = words_of(bound)
    if not words:
        return [], unavailable(
            "TIMING_NO_WORDS", "measured timing carries zero word timestamps")
    cues = protected_names.build_captions(sheet, words)
    src = source_of(bound)
    return cues, {"ok": True, "source": src, "words": len(words),
                  "cues": len(cues),
                  "source_known": bool(src)}


def lyric_words(timing: Any = None) -> Tuple[List[Dict[str, Any]],
                                              Dict[str, Any]]:
    """The lyric check's observed side: measured words, or a refusal.

    Returns ``(words, receipt)``. With timing bound but zero words the
    refusal is TIMING_NO_WORDS: a lyric check holding a timing receipt that
    measured nothing must not silently compare against text it never heard.
    """
    if is_unavailable(timing):
        bound = timing
    else:
        bound = binding(timing)
    if not isinstance(bound, dict) or bound.get("ok") is False:
        return [], _refusal(bound)
    words = words_of(bound)
    if not words:
        return [], unavailable(
            "TIMING_NO_WORDS", "measured timing carries zero word timestamps")
    return words, {"ok": True, "source": source_of(bound), "words": len(words),
                   "source_known": bool(source_of(bound))}


def lyric_observed(approved_lines: Any, timing: Any = None
                   ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """The lyric check's observed side, built from MEASURED words.

    Returns ``(observed_lines, receipt)`` where ``observed_lines`` is the
    ``diff_lyrics`` shape (``[{"line_id": ..., "text": ...}]``): measured
    words distributed onto the approved lines in order (the same want/got
    token walk ``protected_names`` uses for captions), plus one trailing
    ``line_id: ""`` entry carrying anything heard outside every line — ad-lib
    evidence, never silently dropped. A refusal comes back with
    ``observed_lines == []`` and ``ok: False``: no measured words means no
    lyric verdict may pass on timing it never heard.
    """
    words, receipt = lyric_words(timing)
    if not receipt.get("ok"):
        return [], dict(receipt)
    want: List[str] = []
    owner: List[int] = []
    ids: List[str] = []
    for i, ln in enumerate(approved_lines or []):
        text = ln.get("text", "") if isinstance(ln, dict) else str(ln)
        lid = ln.get("line_id", "") if isinstance(ln, dict) else ""
        if not _WORD_RE("\n".join(str(text).splitlines())):
            continue
        ids.append(lid)
        line_idx = len(ids) - 1
        for tok in _WORD_RE("\n".join(str(text).splitlines())):
            want.append(tok)
            owner.append(line_idx)
    got: List[str] = []
    for w in words:
        got.extend(_WORD_RE(str(w.get("word", ""))))
    got_owner: List[Optional[int]] = [None] * len(got)
    adlib: List[str] = []
    for tag, i1, i2, j1, j2 in protected_names._align(want, got):
        if tag == "equal":
            for k in range(i2 - i1):
                got_owner[j1 + k] = owner[i1 + k]
        elif tag == "replace":
            # heard SOMETHING over these approved tokens: it belongs to the
            # line(s) the span covers, and diff_lyrics judges it (a word the
            # sheet never approved surfaces as adlib damage).
            span_owners = owner[i1:i2] or ([owner[i1 - 1]] if i1 else [])
            for off, k in enumerate(range(j1, j2)):
                got_owner[k] = span_owners[min(off, len(span_owners) - 1)] \
                    if span_owners else None
        else:  # insert: heard with no approved counterpart
            adlib.extend(got[j1:j2])
    buckets: Dict[str, List[str]] = {}
    for tok, o in zip(got, got_owner):
        if o is None:
            buckets.setdefault("", []).append(tok)
            continue
        buckets.setdefault(ids[o], []).append(tok)
    observed = [{"line_id": lid, "text": " ".join(buckets[lid])}
                for lid in ids if buckets.get(lid)]
    if buckets.get(""):
        observed.append({"line_id": "", "text": " ".join(buckets[""])})
    observed_words = len(got)
    return observed, {"ok": True, "source": receipt.get("source"),
                      "words": observed_words,
                      "lines_covered": len([l for l in observed
                                            if l["line_id"]]),
                      "outside_line_words": len(adlib),
                      "source_known": bool(receipt.get("source"))}
