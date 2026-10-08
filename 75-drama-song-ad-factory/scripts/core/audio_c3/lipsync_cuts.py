#!/usr/bin/env python3
"""F3 lip-sync cuts from the one Suno track + multi-voice probe analyzer.

Owner order 2026-10-08, manual Part F item F3 (High; SWARM-PLAN W-F-U3).
stdlib only, zero paid calls of its own.

``cut_lipsync_lines(track_receipt, timing_map)`` builds the per-line cut plan
``{line_id: {start_s, end_s, source}}``. Every cut's ``source`` is the main
track's ``generation_id`` from ``track_receipt`` — a lip-sync clip may only
be cut from the one generation that makes the whole soundtrack (F1). The
vocal stem is the lip-sync clip's INPUT ONLY and never enters the final mix:
``stem_mix_role`` is always ``lipsync-input-only``, and any proposed mix
slot that places the stem elsewhere fails ``STEM_IN_FINAL_MIX``
(``refuse_stem_in_final_mix``). A lip-sync clip citing any other source id
fails ``LIPSYNC_SOURCE_MISMATCH`` (``verify_lipsync_clip_source``).

Multi-voice probing (the ONE permitted Suno multi-voice probe, executed
2026-10-08): multi-voice in one Suno generation is UNRELIABLE as the
primary mechanism — voice tags did not reliably hold the intended per-line
speaker cast across the two takes. The timestamped-lyrics path IS validated
for per-line timing. ``measure_distinct_voices`` is a pluggable analyzer:
the default stub returns 1 distinct voice / no male voice / method "stub".
A real analyzer runs only when the caller injects one AND names a track
path — this module never calls Suno, never loads a model, never spends.
NO fallback mechanism is built here; the F3 fallback is Trevor's decision.

Run: python3 core/audio_c3/test_lipsync_cuts_f3.py
"""
from __future__ import annotations

SCHEMA_VERSION = "blackceo.audio-c3/lipsync-cuts/v1"
TOOL_VERSION = "0.1.0"
TOOL_NAME = "lipsync_cuts"

#: The stem is the lip-sync clip's input and nothing else.
STEM_MIX_ROLE = "lipsync-input-only"

#: Fail reasons (receipt / exception codes).
STEM_IN_FINAL_MIX = "STEM_IN_FINAL_MIX"
LIPSYNC_SOURCE_MISMATCH = "LIPSYNC_SOURCE_MISMATCH"

#: Probe closeout note (evidence W-F-U3-F3-VERDICT.md, 2026-10-08):
#: multi-voice casting is not load-bearing; fallback stays Trevor's call.
MULTI_VOICE_NOTE = (
    "multi-voice in one Suno generation is UNRELIABLE as the primary "
    "mechanism (probe 2026-10-08: voice tags did not hold the intended "
    "per-line speaker cast); the timestamped-lyrics path is validated for "
    "timing; NO fallback is built — Trevor decides the fallback."
)

_TIME_KEYS = (("start_s", "end_s"), ("startS", "endS"),
              ("start", "end"), ("start_s", "duration_s"))


def _line_rows(timing_map):
    """Flatten a timing map into [{line_id, start_s, end_s}].

    Accepts either a bare list of line dicts or the section shape
    ``{"sections": [{"lyrics": [...]}]}``. Each line needs ``line_id`` and
    a start/end pair (seconds). Raises ValueError on bad shape or an
    unordered window (fail closed — never invent a cut).
    """
    if isinstance(timing_map, dict):
        rows = []
        for section in timing_map.get("sections") or []:
            if not isinstance(section, dict):
                raise ValueError("TIMING_MAP_INVALID:section not a dict")
            for entry in section.get("lyrics") or []:
                rows.append(entry)
        lines = rows
    elif isinstance(timing_map, list):
        lines = timing_map
    else:
        raise ValueError("TIMING_MAP_INVALID:expected list or sections dict")
    out = []
    for entry in lines:
        if not isinstance(entry, dict):
            raise ValueError("TIMING_MAP_INVALID:line is not a dict")
        line_id = entry.get("line_id")
        if not isinstance(line_id, str) or not line_id.strip():
            raise ValueError("TIMING_MAP_INVALID:line missing line_id")
        start = end = None
        for sk, ek in _TIME_KEYS:
            if sk in entry and ek in entry:
                start, end = float(entry[sk]), float(entry[ek])
                break
        if start is None:
            raise ValueError("TIMING_MAP_INVALID:line %r missing "
                             "start/end seconds" % line_id)
        if not start < end:
            raise ValueError("TIMING_MAP_WINDOW_BAD:%s window unordered"
                             % line_id)
        out.append({"line_id": line_id, "start_s": start, "end_s": end})
    return out


def cut_lipsync_lines(track_receipt, timing_map):
    """Per-line cut plan from the one track's vocal stem at line timestamps.

    Returns::

        {
          "stem_mix_role": "lipsync-input-only",
          "main_generation_id": <id>,
          "cuts": {line_id: {"start_s", "end_s", "source": <id>}},
        }

    Every cut's ``source`` equals ``track_receipt['generation_id']``. Raises
    ValueError when the receipt or any window is invalid — no cut is planned
    against a half-built map.
    """
    if not isinstance(track_receipt, dict):
        raise ValueError("TRACK_RECEIPT_INVALID:not a dict")
    generation_id = None
    soundtrack = track_receipt.get("soundtrack")
    if isinstance(soundtrack, dict):
        generation_id = soundtrack.get("primary_generation_id")
    if generation_id is None:
        generation_id = track_receipt.get("generation_id")
    if not isinstance(generation_id, str) or not generation_id.strip():
        raise ValueError("TRACK_RECEIPT_INVALID:missing generation id")
    cuts = {}
    for row in _line_rows(timing_map):
        cuts[row["line_id"]] = {
            "start_s": row["start_s"],
            "end_s": row["end_s"],
            "source": generation_id,
        }
    if not cuts:
        raise ValueError("TIMING_MAP_EMPTY:no lines to cut")
    return {
        "stem_mix_role": STEM_MIX_ROLE,
        "main_generation_id": generation_id,
        "cuts": cuts,
    }


def refuse_stem_in_final_mix(mix_slots):
    """Error list: stem used outside the lip-sync clip input fails closed.

    ``mix_slots`` is the proposed mix placement list; each slot is a dict
    naming the audio ``source`` and the slot ``role`` (or ``stem_mix_role``).
    A slot whose source is a vocal stem and whose role is anything other
    than ``lipsync-input-only`` earns ``STEM_IN_FINAL_MIX``. Empty list =
    every stem slot is lip-sync input only.
    """
    if mix_slots is None:
        return []
    if isinstance(mix_slots, dict) or not isinstance(mix_slots, (list, tuple)):
        return ["MIX_SLOTS_INVALID:expected a list"]
    errs = []
    for slot in mix_slots:
        if not isinstance(slot, dict):
            errs.append("MIX_SLOTS_INVALID:entry is not a dict")
            continue
        role = slot.get("stem_mix_role", slot.get("role"))
        kind = slot.get("kind") or slot.get("audio_kind") or ""
        is_stem = bool(slot.get("is_stem")) or kind in (
            "vocal-stem", "stem", "vocal_stem")
        if role == STEM_MIX_ROLE and not is_stem:
            # a declared lip-sync-input role on a non-stem slot is noise
            continue
        if is_stem and role != STEM_MIX_ROLE:
            errs.append(
                "%s:%r places the vocal stem in the mix (role %r); the stem "
                "is lip-sync clip input only"
                % (STEM_IN_FINAL_MIX, slot.get("slot", slot.get("name",
                                                                "?")), role))
    return errs


def verify_lipsync_clip_source(clip, main_generation_id):
    """Error list: a lip-sync clip must cite the main track id as source."""
    if not isinstance(clip, dict):
        return ["LIPSYNC_CLIP_INVALID:not a dict"]
    if not isinstance(main_generation_id, str) or not main_generation_id.strip():
        return ["TRACK_RECEIPT_INVALID:missing generation id"]
    source = clip.get("source") or clip.get("generation_id")
    if source != main_generation_id:
        return ["%s:clip cites %r, main track is %r"
                % (LIPSYNC_SOURCE_MISMATCH, source, main_generation_id)]
    return []


def measure_distinct_voices(track_path=None, analyzer=None):
    """Pluggable multi-voice analyzer. Default stub; no Suno call ever.

    Stub (no analyzer injected): 1 distinct voice, no male voice, method
    "stub", carrying ``MULTI_VOICE_NOTE``. A real analyzer runs only when
    the caller injects it AND names ``track_path`` (owner GO / named track);
    this module never downloads, never transcribes, never spends.
    """
    if analyzer is not None:
        if track_path is None or not str(track_path).strip():
            raise ValueError(
                "ANALYZER_REQUIRES_TRACK:the one real multi-voice probe runs "
                "only when the owner names a track (or says GO); pass "
                "track_path")
        result = analyzer(str(track_path))
        if not isinstance(result, dict):
            raise ValueError("ANALYZER_INVALID:analyzer returned non-dict")
        count = result.get("distinct_voice_count")
        if not isinstance(count, int) or count < 1:
            raise ValueError("ANALYZER_INVALID:distinct_voice_count must be "
                             "an int >= 1")
        male = result.get("male_voice_present")
        return {
            "distinct_voice_count": count,
            "male_voice_present": bool(male),
            "method": str(result.get("method") or "injected-analyzer"),
            "note": MULTI_VOICE_NOTE,
        }
    return {
        "distinct_voice_count": 1,
        "male_voice_present": False,
        "method": "stub",
        "note": MULTI_VOICE_NOTE,
    }
