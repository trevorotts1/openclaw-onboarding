#!/usr/bin/env python3
"""spine.py: the story spine and the one joiner (N-74).

One agent writes the spine first, 300 to 500 words: the cast, the places in
order, the time of day per scene, each character's wardrobe per scene, and the
arc. The same agent then writes the Story Beats, and the beats gate must pass
before any script row is written. Section writers obey the spine; a script
joins the sections in time order (``join_sections``); a failed row returns to
its own writer (``route_failures``), never to someone else's.

Pure data checks. Stdlib only, no IO, no model call, no mutation of input.
"""
from __future__ import annotations

import copy

from .beat_sheet import MAJOR, _defect, validate_story_beats

SCHEMA_VERSION = "s75.story-spine.v1"

#: The spine is prose of this many words, no fewer and no more (N-74).
SPINE_MIN_WORDS = 300
SPINE_MAX_WORDS = 500


def _words(text):
    if not isinstance(text, str):
        return 0
    return len(text.split())


def validate_spine(spine, cast_ids=None, scene_ids=None):
    """Defects for one story spine, checked as data against the run's own lists.

    Returns a list of findings (empty when the spine holds). A spine that
    declares a cast or a scene order that the run does not hold is refused:
    every parallel writer obeys the spine, so the spine may not invent one.
    """
    if not isinstance(spine, dict):
        return [_defect("SPINE_SCHEMA", "/spine", "spine is not an object")]
    defects = []
    words = _words(spine.get("text"))
    if words < SPINE_MIN_WORDS or words > SPINE_MAX_WORDS:
        defects.append(_defect("SPINE_LENGTH", "/spine/text",
                               "the spine is 300 to 500 words", words=words))
    for field in ("cast", "places_in_order", "time_of_day_by_scene",
                  "wardrobe_by_scene", "arc"):
        value = spine.get(field)
        empty = (not value) if isinstance(value, (list, dict, str)) else value is None
        if empty:
            defects.append(_defect("SPINE_SCHEMA", "/spine/" + field,
                                   "the spine names its %s" % field))
    if cast_ids is not None and isinstance(spine.get("cast"), list):
        declared = {str(c) for c in spine["cast"]}
        expected = {str(c) for c in cast_ids}
        for missing in sorted(expected - declared):
            defects.append(_defect("SPINE_CAST_DRIFT", "/spine/cast",
                                   "every cast id is in the spine", character_id=missing))
        for extra in sorted(declared - expected):
            defects.append(_defect("SPINE_CAST_DRIFT", "/spine/cast",
                                   "the spine names no character the run does not hold",
                                   character_id=extra))
    if scene_ids is not None and isinstance(spine.get("places_in_order"), list):
        held = [str(s) for s in scene_ids]
        declared = [str(s) for s in spine["places_in_order"]]
        if held and declared != held:
            defects.append(_defect("SPINE_ORDER_DRIFT", "/spine/places_in_order",
                                   "the spine's order is the run's scene order",
                                   declared=declared, held=held))
    return defects


def spine_gate(spine, cast_ids=None, scene_ids=None):
    """Refuse any script row until the spine holds and the beats gate passes.

    ``spine`` alone is checked here; call ``gate_before_script`` to run both
    steps in order with the Story Beats.
    """
    defects = validate_spine(spine, cast_ids=cast_ids, scene_ids=scene_ids)
    return {"ok": not any(d["level"] == MAJOR for d in defects),
            "schema_version": SCHEMA_VERSION, "defects": defects}


def gate_before_script(spine, beats_record, cast_ids=None, scene_ids=None,
                       measured_lines=None, hook_lines=None):
    """N-74 order: the spine, then the beats gate. No script row before both pass."""
    spine_verdict = spine_gate(spine, cast_ids=cast_ids, scene_ids=scene_ids)
    beats_verdict = validate_story_beats(beats_record, measured_lines=measured_lines,
                                         hook_lines=hook_lines)
    ok = spine_verdict["ok"] and beats_verdict["ok"]
    return {
        "ok": ok,
        "schema_version": SCHEMA_VERSION,
        "spine": spine_verdict,
        "beats": beats_verdict,
        "defects": list(spine_verdict["defects"]) + list(beats_verdict["defects"]),
        "script_rows_allowed": ok,
    }


def join_sections(rows, section_order=None):
    """The one joiner: mechanical, in time order, never an agent's judgement.

    ``rows`` is every section writer's rows, in any order. The join sorts by
    the measured start time, then by the section's own order when two rows
    share a start. Rows are copied, never edited. A duplicate row id is
    refused because two writers would then own one row.
    """
    if not isinstance(rows, list):
        return {"ok": False, "rows": [],
                "defects": [_defect("JOIN_INPUT", "/rows", "rows must be a list")]}
    seen = {}
    defects = []
    ordered_sections = {name: index for index, name in enumerate(section_order or [])}

    def key(row):
        start = row.get("start_s")
        start = float(start) if isinstance(start, (int, float)) \
            and not isinstance(start, bool) else float("inf")
        section = ordered_sections.get(row.get("section"), len(ordered_sections))
        return (start, section)

    joined = []
    for row in rows:
        if not isinstance(row, dict):
            defects.append(_defect("JOIN_INPUT", "/rows", "row is not an object"))
            continue
        row_id = row.get("row_id") or row.get("line_id")
        if row_id in seen:
            defects.append(_defect("JOIN_DUPLICATE_ROW", "/rows/%s" % row_id,
                                   "two writers produced one row"))
            continue
        seen[row_id] = True
        joined.append(copy.deepcopy(row))
    joined.sort(key=key)
    for index, row in enumerate(joined, start=1):
        row["join_index"] = index
    return {"ok": not defects,
            "rows": joined, "defects": defects, "count": len(joined)}


def route_failures(row_results, writers_by_section):
    """A failed row returns to its own writer and to nobody else's."""
    by_writer = {}
    for row_id, result in (row_results or {}).items():
        if not isinstance(result, dict) or result.get("ok"):
            continue
        section = result.get("section")
        writer = (writers_by_section or {}).get(section)
        by_writer.setdefault(writer, []).append({
            "row_id": row_id,
            "section": section,
            "defects": result.get("defects") or [],
        })
    return by_writer
