#!/usr/bin/env python3
"""constraints.py -- S75-T25 duration, opener, lip-sync and route constraints.

Stdlib only. No provider call, no spend, no client write, no media file.

Contract sources (read-only):
  * MUSIC-AND-VIDEO-UX.md sections 2-3 (durations, 12 s opener, lip-sync math,
    MiniMax H3, exact client-selected routes).
  * S75-T03 contracts: the adapter consumes contract-shaped payloads; it does
    not require a generated client script or a live provider response.
  * ``suno_recipe.duration_registry`` owns the six durations -- this module
    re-exports it and keeps no second list.
  * ``kie_dispatch.model_lock`` owns the route allowlist -- imported lazily so
    importing this module needs no sqlite file and no price menu.

Spoken duration and visible lip-sync share are SEPARATE measurements.
``visible_lip_sync`` divides the union of visible articulating intervals by the
final picture runtime. ``spoken_audio_share`` divides measured spoken audio by
the same runtime and never counts toward the 35% cap.

Run: python3 tests/test_music_constraints_t25.py
"""
from __future__ import annotations

import math

try:                                                     # core/ on sys.path
    from suno_recipe import duration_registry as _DR
except ImportError:                                      # imported as core.music
    from ..suno_recipe import duration_registry as _DR

TOOL_NAME = "music_constraints"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.music-constraints/v1"
SOURCE = ("MUSIC-AND-VIDEO-UX.md sections 2-3; S75-T25/S75-A25; "
          "duration_registry; kie_dispatch.model_lock")

#: The six offered lengths, owned by the canonical registry.
DURATIONS_S = _DR.CANONICAL_DURATION_S

#: The first twelve seconds carry articulated spoken delivery.
SPOKEN_OPENER_S = 12.0

#: Visible lip-sync: share of FINAL PICTURE RUNTIME, from interval union.
LIPSYNC_TARGET_MIN = 0.25
LIPSYNC_TARGET_MAX = 0.30
LIPSYNC_HARD_CAP = 0.35

#: Delivery labels a word-fit block may carry.
DELIVERIES = ("spoken", "rap", "sung")

#: The eighteen frozen style IDs (SPEC section "Choices that must survive").
#: ponytail: contract default until the T18-T22 catalog lands; pass an explicit
#: catalog to bind_matrix and this tuple stops being read.
STYLE_IDS = (
    "soul-ballad", "rnb-flow", "soul-rise",
    "acoustic-pop", "folk-storytelling", "country-pop",
    "melodic-rap", "trap-rap", "pop-rap", "pop-rock",
    "reggaeton", "cinematic-orchestral-song", "musical-theater",
    "contemporary-gospel", "urban-gospel", "alternative-rnb",
    "afro-soul", "country-rap",
)

#: Display route -> canonical KIE id. Labels only; the id is what is locked.
ROUTE_LABELS = {
    "MiniMax H3": "minimax-h3/*",
    "MiniMax H3 768P": "minimax-h3/*",
}

class ConstraintError(ValueError):
    """Machine-readable refusal. A caller bug is BAD_INPUT, never a verdict."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message

def _num(value, name, allow_zero=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)) or float(value) < 0 \
            or (float(value) == 0 and not allow_zero):
        raise ConstraintError("BAD_INPUT", "%s must be a finite number %s 0, got %r"
                              % (name, ">=" if allow_zero else ">", value))
    return float(value)

# -- durations ---------------------------------------------------------------

def duration_seconds(selected):
    """The canonical seconds for a selection; anything else fails closed.

    The choice sets come from the registry, so a hand-written 45 or 601 can
    never reach dispatch by accident.
    """
    if isinstance(selected, bool):
        raise ConstraintError("BAD_DURATION", "%r is not one of %s"
                              % (selected, list(DURATIONS_S)))
    if isinstance(selected, str) and selected.strip().isdigit():
        selected = int(selected.strip())
    if selected not in DURATIONS_S:
        raise ConstraintError("BAD_DURATION", "%r is not one of %s"
                              % (selected, list(DURATIONS_S)))
    return int(selected)

def duration_row(seconds):
    """The registry row for one canonical duration."""
    return _DR.duration_row(duration_seconds(seconds))

# -- visible lip-sync (union of intervals) -----------------------------------

def union_duration(intervals):
    """Total seconds covered by the union of [start, end] intervals.

    Simultaneous faces are counted once, so two people talking over the same
    two seconds add two seconds, not four.
    """
    if not isinstance(intervals, (list, tuple)):
        raise ConstraintError("BAD_INPUT", "intervals must be a list of [start, end]")
    spans = []
    for item in intervals:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ConstraintError("BAD_INPUT", "interval must be [start, end], got %r"
                                  % (item,))
        start, end = _num(item[0], "start"), _num(item[1], "end")
        if end <= start:
            raise ConstraintError("BAD_INTERVAL", "interval end %r must exceed start %r"
                                  % (end, start))
        spans.append((start, end))
    spans.sort()
    total, cur_start, cur_end = 0.0, None, None
    for start, end in spans:
        if cur_end is None or start > cur_end:
            if cur_end is not None:
                total += cur_end - cur_start
            cur_start, cur_end = start, end
        elif end > cur_end:
            cur_end = end
    if cur_end is not None:
        total += cur_end - cur_start
    return round(total, 6)

def visible_lip_sync(intervals, final_runtime_s):
    """Measure visible lip-sync share of final picture runtime.

    ``intervals`` are measured visible articulating character intervals.
    Spoken audio over a location or a reaction cutaway contributes zero here.
    """
    runtime = _num(final_runtime_s, "final_runtime_s", allow_zero=False)
    visible = union_duration(intervals)
    if visible > runtime + 1e-9:
        raise ConstraintError(
            "BAD_INTERVAL", "visible articulation %.3fs exceeds final runtime %.3fs"
            % (visible, runtime))
    share = round(visible / runtime, 6)
    if share > LIPSYNC_HARD_CAP:
        status = "OVER_CAP"
    elif LIPSYNC_TARGET_MIN <= share <= LIPSYNC_TARGET_MAX:
        status = "IN_TARGET"
    else:
        status = "BELOW_TARGET"
    return {
        "kind": "visible_lip_sync",
        "basis": "union_of_visible_articulating_intervals/final_picture_runtime",
        "visible_seconds": visible,
        "final_runtime_s": runtime,
        "share": share,
        "status": status,
        "target_min": LIPSYNC_TARGET_MIN,
        "target_max": LIPSYNC_TARGET_MAX,
        "hard_cap": LIPSYNC_HARD_CAP,
    }

def assert_lipsync(intervals, final_runtime_s):
    """The measurement, refusing a share above the 35% hard cap.

    Below the 25% target is a flag, not a refusal: the cap is the only hard
    reject. An ineligible style must not acquire talking mouths to chase it.
    """
    result = visible_lip_sync(intervals, final_runtime_s)
    if result["status"] == "OVER_CAP":
        raise ConstraintError(
            "LIPSYNC_CAP_EXCEEDED",
            "visible lip-sync %.1f%% (%.3fs of %.3fs) exceeds the 35%% cap"
            % (100.0 * result["share"], result["visible_seconds"],
               result["final_runtime_s"]))
    return result

def spoken_audio_share(spoken_seconds, final_runtime_s):
    """Measured spoken AUDIO share. Never proves the visual cap.

    Kept a separate call with a separate basis so no caller can pass an audio
    ratio to ``assert_lipsync`` and call the picture compliant.
    """
    spoken = _num(spoken_seconds, "spoken_seconds")
    runtime = _num(final_runtime_s, "final_runtime_s", allow_zero=False)
    if spoken > runtime + 1e-9:
        raise ConstraintError("BAD_INPUT", "spoken %.3fs exceeds runtime %.3fs"
                              % (spoken, runtime))
    return {
        "kind": "spoken_audio",
        "basis": "measured_spoken_audio/final_picture_runtime",
        "spoken_seconds": spoken,
        "final_runtime_s": runtime,
        "share": round(spoken / runtime, 6),
        "counts_toward_lipsync_cap": False,
    }

# -- first twelve seconds ----------------------------------------------------

def check_opener(block, duration_s=None):
    """The first 12 s are articulated spoken words, starting at 0.0.

    ``block`` is the planned opening block:
    {delivery, start_s, end_s, words, articulated}. A wordless intro, an
    early sung line, a swallowed opener (articulated false) or a short block
    all fail closed with a named code.
    """
    if not isinstance(block, dict):
        raise ConstraintError("BAD_INPUT", "opener block must be a dict")
    delivery = block.get("delivery")
    if delivery != "spoken":
        raise ConstraintError("OPENER_NOT_SPOKEN",
                              "first 12 s must be spoken, got %r" % (delivery,))
    start = _num(block.get("start_s"), "start_s")
    end = _num(block.get("end_s"), "end_s")
    if start > 0.0:
        raise ConstraintError("OPENER_WORDLESS_INTRO",
                              "opening words start at %.3fs; no wordless intro" % start)
    if end - start < SPOKEN_OPENER_S:
        raise ConstraintError(
            "OPENER_TOO_SHORT",
            "opening spans %.3fs; the first %.0f s must be articulated speech"
            % (end - start, SPOKEN_OPENER_S))
    if block.get("articulated") is not True:
        raise ConstraintError("OPENER_NOT_ARTICULATED",
                              "opening delivery must be flagged articulated")
    words = block.get("words")
    if isinstance(words, bool) or not isinstance(words, int) or words <= 0:
        raise ConstraintError("OPENER_WORDLESS_INTRO",
                              "opening block carries no words (%r)" % (words,))
    if duration_s is not None:
        duration = duration_seconds(duration_s)
        if end > duration + 1e-9:
            raise ConstraintError("OPENER_EXCEEDS_DURATION",
                                  "opening ends at %.3fs past the %ss cut"
                                  % (end, duration))
    return {"ok": True, "spoken_opener_seconds": SPOKEN_OPENER_S,
            "start_s": start, "end_s": end, "words": words}

# -- routes ------------------------------------------------------------------

def _model_lock():
    try:                                                 # core/ on sys.path
        from kie_dispatch import model_lock
    except ImportError:                                  # imported as core.music
        from ..kie_dispatch import model_lock
    return model_lock

def canonical_route(route):
    """Exact selected route id; a display label maps to its locked KIE id.

    The label map is deliberately tiny: it exists so "MiniMax H3" and
    "MiniMax H3 768P" name the already locked family. Nothing else is
    normalized and nothing is upgraded to a newer or cheaper model.
    """
    if not isinstance(route, str) or not route.strip():
        raise ConstraintError("ROUTE_NOT_SELECTED", "a selected route is required")
    route = route.strip()
    return ROUTE_LABELS.get(route, route)

def assert_route(route):
    """Refuse a route off the price menu; return the preserved selection."""
    resolved = canonical_route(route)
    lock = _model_lock()
    try:
        lock.assert_allowed(resolved)
    except lock.ModelLockError as exc:
        raise ConstraintError("MODEL_NOT_ON_MENU", exc.message)
    return {"requested": route, "resolved": resolved, "substituted": False}

def assert_route_preserved(selected, effective):
    """Refuse a dispatch whose effective model differs from the selection."""
    want, got = canonical_route(selected), canonical_route(effective)
    if want != got:
        raise ConstraintError(
            "ROUTE_SUBSTITUTED",
            "selected route %r became %r; preserve the exact client route or stop"
            % (want, got))
    return {"requested": selected, "resolved": want, "substituted": False}

# -- the eighteen styles x six durations matrix ------------------------------

def bind_matrix(durations=None, style_ids=None, route="MiniMax H3"):
    """Bind every style x duration to its intended route and constraint set.

    The rows are the no-spend plan matrix: selecting a style must never change
    the cast, story, language, opener, route or duration. An unknown style or
    duration fails closed instead of silently binding to a default.
    """
    durations = [duration_seconds(d) for d in (durations or DURATIONS_S)]
    styles = list(style_ids or STYLE_IDS)
    bad = [s for s in styles
           if not isinstance(s, str) or not s or s != s.strip().lower()]
    if bad:
        raise ConstraintError("BAD_STYLE", "style ids must be stable lowercase ids: %r"
                              % (bad,))
    binding = assert_route(route)
    rows = []
    for style_id in styles:
        for seconds in durations:
            row = duration_row(seconds)
            rows.append({
                "style_id": style_id,
                "duration_s": seconds,
                "duration_label": row["label"],
                "route_requested": binding["requested"],
                "route": binding["resolved"],
                "spoken_opener_s": SPOKEN_OPENER_S,
                "lipsync_target": [LIPSYNC_TARGET_MIN, LIPSYNC_TARGET_MAX],
                "lipsync_cap": LIPSYNC_HARD_CAP,
            })
    return rows
