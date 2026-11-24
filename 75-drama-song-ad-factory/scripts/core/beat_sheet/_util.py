"""beat_sheet._util: readers for the beat record and the script-row record.

One beat row (Story Beats) and one script row (the story script, plan 3F) share
two shapes. These helpers read both without assuming which of the two optional
spellings a caller used, and turn one finding into the repo's defect shape with
its section 3J level.

Stdlib only; pure functions over loaded dicts. No IO, no model call.
"""
from __future__ import annotations

from .beat_sheet import (
    MAJOR,
    MEDIUM,
    MINOR,
    TIME_OF_DAY_ALIASES,
    TIME_OF_DAY_ORDER,
    severity,
)


def finding(code, pointer, detail=None, **extra):
    """One finding: code, JSON pointer, section 3J level and item, and detail."""
    record = {"code": code, "pointer": pointer}
    record.update(severity(code))
    if detail:
        record["detail"] = detail
    record.update(extra)
    return record


def beats(record):
    """Beats from ``{"beats": [...]}`` or a bare list; dict rows only."""
    rows = record.get("beats") if isinstance(record, dict) else record
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def rows(script):
    """Script rows from ``{"rows": [...]}`` or a bare list; dict rows only."""
    data = script.get("rows") if isinstance(script, dict) else script
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def beat_by_number(record):
    return {beat.get("beat_number"): beat for beat in beats(record)}


def beat_place(beat):
    where = beat.get("where") if isinstance(beat.get("where"), dict) else beat
    return where.get("location_id")


def beat_time(beat):
    where = beat.get("where") if isinstance(beat.get("where"), dict) else beat
    return where.get("time_of_day")


def beat_cast(beat):
    who = beat.get("who") if isinstance(beat.get("who"), dict) else {}
    return {c for c in who.get("on_screen") or [] if isinstance(c, str) and c}


def line_texts(beat):
    out = []
    for line in beat.get("lyric_lines") or []:
        if isinstance(line, dict):
            text = line.get("text")
            if isinstance(text, str) and text.strip():
                out.append(text.strip())
        elif isinstance(line, str) and line.strip():
            out.append(line.strip())
    return out


def line_ids(beat):
    out = []
    for line in beat.get("lyric_lines") or []:
        if isinstance(line, dict) and isinstance(line.get("line_id"), str):
            out.append(line["line_id"])
    return out


def norm(value):
    return str(value or "").strip().lower()


def time_rank(value):
    key = norm(value)
    key = TIME_OF_DAY_ALIASES.get(key, key)
    return TIME_OF_DAY_ORDER.index(key) if key in TIME_OF_DAY_ORDER else None


def wardrobe(record):
    value = record.get("wardrobe") if isinstance(record, dict) else None
    return value if isinstance(value, dict) else {}


def row_people(row):
    names = set()
    for key in ("on_screen", "singing"):
        value = row.get(key)
        if isinstance(value, list):
            names.update(v for v in value if isinstance(v, str) and v)
    for key in ("who_sings", "singer"):
        value = row.get(key)
        if isinstance(value, str) and value:
            names.add(value)
    return names


def num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


__all__ = [
    "MAJOR", "MEDIUM", "MINOR", "finding", "beats", "rows", "beat_by_number",
    "beat_place", "beat_time", "beat_cast", "line_texts", "line_ids", "norm",
    "time_rank", "wardrobe", "row_people", "num",
]
