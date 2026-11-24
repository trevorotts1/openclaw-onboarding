#!/usr/bin/env python3
"""The story script written from the Story Beats (N-63, section 3F.1).

One writer per song section writes at the same time, one row per lyric line,
keyed to its measured start and end and to its beat's number. The rows exist
before any picture. ``script.join_script`` joins the sections in time order and
``script.script_defects`` is the one owner of the SCRIPT_OFF_BEAT checks; this
module only writes rows, in the row shape ``script.SCRIPT_ROW_FIELDS`` names.

Stdlib only; data in, rows out; no model call, no write.
"""
from __future__ import annotations

from ._util import norm
from .script import SCRIPT_ROW_FIELDS, join_script

__all__ = [
    "SCRIPT_ROW_FIELDS",
    "selftest",
    "song_lines",
    "write_script",
    "write_section",
]

def _num(value):
    return float(value) if isinstance(value, (int, float)) \
        and not isinstance(value, bool) else None

def song_lines(song):
    """Normalise the measured song to ``[{"line_id","text","start_s","end_s"}]``."""
    lines = song.get("lines") if isinstance(song, dict) else song
    if not isinstance(lines, list):
        raise ValueError("song must be a list of measured lines")
    out = []
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise ValueError("song line %d is not an object" % index)
        out.append({
            "line_id": line.get("line_id", line.get("index", index)),
            "text": line.get("text", ""),
            "start_s": _num(line.get("start_s", line.get("start"))),
            "end_s": _num(line.get("end_s", line.get("end"))),
        })
    return out

def _measured(line, lines):
    wanted = norm(line.get("text"))
    for measured in lines:
        if norm(measured["text"]) == wanted:
            return measured
    return None

def _lip_candidate(line, beat):
    for candidate in beat.get("lip_sync_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("line_id") == line.get("line_id") \
                or norm(candidate.get("sentence")) == norm(line.get("text")):
            return candidate
    return None

def write_section(beat, lines, writer_id, *, emotion_fill=None):
    """One row per lyric line of one beat, in measured order."""
    who = beat.get("who") if isinstance(beat.get("who"), dict) else {}
    start_tag = beat.get("emotion_start") if isinstance(beat.get("emotion_start"), dict) else {}
    end_tag = beat.get("emotion_end") if isinstance(beat.get("emotion_end"), dict) else {}
    cues = emotion_fill or {}
    rows = []
    beat_lines = beat.get("lyric_lines") or []
    for index, line in enumerate(beat_lines):
        if isinstance(line, str):
            line = {"text": line}
        measured = _measured(line, lines) or {}
        candidate = _lip_candidate(line, beat)
        tag = end_tag if index == len(beat_lines) - 1 else start_tag
        line_id = line.get("line_id", measured.get("line_id", index))
        singing = [c for c in who.get("singing") or [] if c]
        rows.append({
            "row_id": "b%s-%s" % (beat.get("beat_number"), line_id),
            "line_id": line_id,
            "beat_number": beat.get("beat_number"),
            "start_s": measured.get("start_s", beat.get("start_s")),
            "end_s": measured.get("end_s", beat.get("end_s")),
            "who_sings": (candidate or {}).get("voice_id")
            or (singing[0] if singing else None),
            "singing": singing,
            "location_id": beat.get("location_id"),
            "time_of_day": beat.get("time_of_day"),
            "wardrobe": dict(beat.get("wardrobe") or {}),
            "on_screen": [c for c in who.get("on_screen") or [] if c],
            "written_objects": [],
            "lip_sync": candidate is not None,
            "emotion": tag.get("emotion"),
            "intensity": tag.get("intensity"),
            "facial_cues": cues.get(line_id, cues.get(norm(line.get("text")), {})),
            "line_match": None,
        })
    return rows

def write_script(beats, song, writers_by_section=None, *, emotion_fill=None,
                 section_order=None):
    """One writer per song section, then the one mechanical join in time order."""
    lines = song_lines(song)
    beat_rows = beats.get("beats") if isinstance(beats, dict) else beats
    if not isinstance(beat_rows, list):
        raise ValueError("beats must be a list or {'beats': [...]}")
    rows = []
    for index, beat in enumerate(beat_rows):
        if not isinstance(beat, dict):
            raise ValueError("beat %d is not an object" % index)
        section = beat.get("section")
        writer = ((writers_by_section or {}).get(section) if section else None) \
            or beat.get("writer_id") or "section-%s" % (section or index)
        rows.extend(write_section(beat, lines, writer, emotion_fill=emotion_fill))
    return join_script({"rows": rows}, section_order=section_order)["rows"]

def selftest():
    beats = {"beats": [{
        "beat_number": 1, "name": "kitchen at first light",
        "start_s": 0.0, "end_s": 10.0,
        "lyric_lines": [{"line_id": "l1", "text": "I rise"},
                        {"line_id": "l2", "text": "I try"}],
        "who": {"on_screen": ["lead"], "singing": ["lead"], "listening": [],
                "else_seen": "nobody else is seen here"},
        "location_id": "kitchen", "time_of_day": "dawn",
        "wardrobe": {"lead": "w1"}, "entrances": [], "exits": [],
        "emotion_start": {"emotion": "worry", "intensity": 2},
        "emotion_end": {"emotion": "resolve", "intensity": 2},
        "change": "she gets up", "event": None,
        "lip_sync_candidates": [{"line_id": "l1", "voice_id": "lead"}],
    }]}
    song = {"lines": [
        {"line_id": "l1", "text": "I rise", "start_s": 0.0, "end_s": 4.0},
        {"line_id": "l2", "text": "I try", "start_s": 4.0, "end_s": 10.0},
    ]}
    cues = {"eyes": "level", "brows": "set", "mouth": "firm",
            "smile": "no", "teeth": "no", "tears": "none"}
    rows = write_script(beats, song, emotion_fill={"l1": cues, "l2": cues})
    assert len(rows) == 2, rows
    assert [r["row_id"] for r in rows] == ["b1-l1", "b1-l2"]
    assert rows[0]["start_s"] == 0.0 and rows[0]["who_sings"] == "lead"
    assert rows[0]["lip_sync"] is True and rows[1]["lip_sync"] is False
    assert rows[1]["emotion"] == "resolve" and rows[1]["facial_cues"] == cues
    return True

if __name__ == "__main__":  # pragma: no cover
    assert selftest()
    print("story_script selftest OK")
