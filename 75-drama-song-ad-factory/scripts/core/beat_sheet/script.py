"""beat_sheet.script: the story script written from the Story Beats (N-63).

Plan 3F.1 step 3. One writer per song section writes at the same time, one row
per lyric line, each keyed to its measured start and end and to its beat's
number. A script joins the sections in time order (``.spine.join_sections``).
The row may add camera detail and facial cues; it may not add, drop or move an
event, or change who is there, where they are, what they wear, or the direction
of the emotion. That is ``SCRIPT_OFF_BEAT`` and the row returns to its own
writer. The storyboard may add camera detail and may not add, drop or move an
event either.

Row shape (``beat_sheet.SCRIPT_ROW_FIELDS``): row_id, line_id, beat_number,
start_s, end_s, who_sings, singing, location_id, time_of_day, wardrobe,
on_screen, written_objects, lip_sync, emotion, intensity, facial_cues,
line_match.

Stdlib only; data in, verdicts out; no model call, no write.
"""
from __future__ import annotations

from ._util import (
    beat_by_number,
    beat_cast,
    beat_place,
    beat_time,
    finding,
    line_ids,
    line_texts,
    norm,
    num,
    row_people,
    rows,
    wardrobe,
)
from .spine import join_sections

SCRIPT_ROW_FIELDS = (
    "row_id", "line_id", "beat_number", "start_s", "end_s", "who_sings",
    "singing", "location_id", "time_of_day", "wardrobe", "on_screen",
    "written_objects", "lip_sync", "emotion", "intensity", "facial_cues",
    "line_match",
)

#: a row the story script may not change from its beat (3F.1)
FIXED_ON_SCRIPT = ("location_id", "time_of_day")


def section_rows(script):
    """Group rows by their ``section`` (a song section), preserving time order."""
    grouped = {}
    for row in rows(script):
        grouped.setdefault(row.get("section"), []).append(row)
    for section in grouped:
        grouped[section].sort(key=lambda r: num(r.get("start_s")) or 0.0)
    return grouped


def join_script(script, section_order=None):
    """The mechanical join: every section in time order, one writer per row."""
    return join_sections(rows(script), section_order=section_order)


def row_defects(row, beat, index=0):
    """One script row against its beat; every failure is SCRIPT_OFF_BEAT."""
    pointer = "/rows/%d" % index
    out = []
    for field in ("line_id", "beat_number"):
        if not row.get(field) and not isinstance(row.get(field), int):
            out.append(finding("SCRIPT_OFF_BEAT", pointer + "/" + field,
                               "a row carries its line id and its beat's number"))
    start, end = num(row.get("start_s")), num(row.get("end_s"))
    if start is None or end is None or end <= start:
        out.append(finding("SCRIPT_OFF_BEAT", pointer + "/start_s",
                           "the row keeps the measured start and end"))
    if beat is None:
        out.append(finding("SCRIPT_OFF_BEAT", pointer + "/beat_number",
                           "the row's beat is not in the Story Beats"))
        return out

    text = row.get("text") or row.get("line")
    if isinstance(text, str) and text.strip():
        if text.strip() not in line_texts(beat):
            out.append(finding("SCRIPT_OFF_BEAT", pointer + "/line",
                               "the row adds or moves a line its beat does not hold"))
    line_id = row.get("line_id")
    if isinstance(line_id, str) and line_ids(beat) and line_id not in line_ids(beat):
        out.append(finding("SCRIPT_OFF_BEAT", pointer + "/line_id",
                           "the row's line id is not in its beat"))

    place = row.get("location_id")
    if place is not None and beat_place(beat) and norm(place) != norm(beat_place(beat)):
        out.append(finding("SCRIPT_OFF_BEAT", pointer + "/location_id",
                           "the row moves the beat to another place"))
    time = row.get("time_of_day")
    if time is not None and beat_time(beat) and norm(time) != norm(beat_time(beat)):
        out.append(finding("SCRIPT_OFF_BEAT", pointer + "/time_of_day",
                           "the row moves the beat to another time of day"))

    beat_wear = wardrobe(beat)
    for character, outfit in wardrobe(row).items():
        if character in beat_wear and beat_wear[character] != outfit:
            out.append(finding("SCRIPT_OFF_BEAT", pointer + "/wardrobe/" + str(character),
                               "the row changes a wardrobe its beat fixed"))

    cast = beat_cast(beat)
    strangers = sorted(p for p in row_people(row) if cast and p not in cast)
    if strangers:
        out.append(finding("SCRIPT_OFF_BEAT", pointer + "/on_screen",
                           "the row puts people in the beat who are not there",
                           extra=tuple(strangers)))
    return out


def script_defects(script, beats_record, lyric_lines=None):
    """The whole story script against the beats and the measured song (N-63)."""
    script_rows = rows(script)
    if not script_rows:
        return [finding("SCRIPT_OFF_BEAT", "/rows", "no script rows were written")]
    by_number = beat_by_number(beats_record)
    out = []
    seen = set()
    for index, row in enumerate(script_rows):
        row_id = row.get("row_id") or row.get("line_id")
        if row_id in seen:
            out.append(finding("JOIN_DUPLICATE_ROW", "/rows/%d" % index,
                               "two writers produced one row"))
        seen.add(row_id)
        out.extend(row_defects(row, by_number.get(row.get("beat_number")), index))

    out.extend(event_defects(script_rows, beats_record))

    for beat in beats_record.get("beats") if isinstance(beats_record, dict) else beats_record or []:
        if not isinstance(beat, dict):
            continue
        if not any(row.get("beat_number") == beat.get("beat_number")
                   for row in script_rows):
            out.append(finding("SCRIPT_OFF_BEAT", "/rows",
                               "beat %s has no script row"
                               % beat.get("beat_number"),
                               beat=beat.get("beat_number")))
    if lyric_lines:
        homed = {row.get("line_id") for row in script_rows}
        for line in lyric_lines:
            line_id = line.get("line_id") if isinstance(line, dict) else line
            if line_id not in homed:
                out.append(finding("SCRIPT_OFF_BEAT", "/rows",
                                   "measured line has no script row",
                                   line_id=line_id))
    return out


def event_defects(script_rows, beats_record):
    """One event, on its own lyric, once (3F.2)."""
    out = []
    beats = beats_record.get("beats") if isinstance(beats_record, dict) \
        else beats_record or []
    for beat in beats:
        if not isinstance(beat, dict):
            continue
        event = beat.get("event")
        if not isinstance(event, dict) or not event.get("kind"):
            continue
        kind = str(event.get("kind"))
        hits = [row for row in script_rows
                if isinstance(row.get("event"), dict)
                and str(row.get("event").get("kind")) == kind]
        if len(hits) != 1:
            out.append(finding("EVENT_REPEATED", "/rows",
                               "the event %r is on %d script rows" % (kind, len(hits)),
                               event_kind=kind))
            continue
        want = event.get("line")
        have = hits[0].get("text") or hits[0].get("line")
        if want and have and want.strip() != have.strip():
            out.append(finding("EVENT_OFF_LYRIC", "/rows",
                               "the event %r left the line that names it" % kind,
                               event_kind=kind))
    return out


def storyboard_defects(storyboard, script):
    """The storyboard may add camera detail and never an event (3F.1)."""
    out = []
    counts = {}
    for row in rows(script):
        event = row.get("event")
        if isinstance(event, dict) and event.get("kind"):
            counts[str(event["kind"])] = counts.get(str(event["kind"]), 0) + 1
    shots = storyboard.get("shots") if isinstance(storyboard, dict) else None
    for index, shot in enumerate([s for s in shots if isinstance(s, dict)]
                                 if isinstance(shots, list) else []):
        event = shot.get("event")
        if isinstance(event, dict) and event.get("kind"):
            kind = str(event["kind"])
            if kind not in counts:
                out.append(finding("SCRIPT_OFF_BEAT", "/shots/%d/event" % index,
                                   "the storyboard adds the event %r" % kind))
            else:
                counts[kind] = counts[kind] - 1
    for kind, remaining in counts.items():
        if remaining > 0:
            out.append(finding("SCRIPT_OFF_BEAT", "/shots",
                               "the storyboard drops the event %r" % kind))
    return out


def check_script(script, beats_record, lyric_lines=None, section_order=None):
    """Result envelope: the joined script and every row finding (N-63)."""
    joined = join_script(script, section_order=section_order)
    defects = list(joined["defects"]) + script_defects(script, beats_record,
                                                       lyric_lines=lyric_lines)
    return {"ok": not any(d.get("level") == "MAJOR" for d in defects),
            "row_count": len(rows(script)), "rows": joined["rows"],
            "defects": defects}


def _selfcheck():
    beat = {
        "beat_number": 1, "name": "she opens the letter",
        "start_s": 0.0, "end_s": 8.0,
        "lyric_lines": [{"line_id": "l1", "text": "line one"}],
        "who": {"on_screen": ["c1"], "singing": ["c1"], "else_seen": "nobody else"},
        "location_id": "kitchen", "time_of_day": "morning",
        "wardrobe": {"c1": "w1"}, "entrances": [], "exits": [],
        "emotion_start": {"emotion": "worry", "intensity": 2},
        "emotion_end": {"emotion": "resolve", "intensity": 2},
        "change": "a decision",
        "event": {"kind": "letter", "line": "line one"},
        "props_change": [], "lip_sync_candidates": [{"line_id": "l1"}],
    }
    cues = {"eyes": "steady", "brows": "set", "mouth": "firm",
            "smile": "no", "teeth": "no", "tears": "none"}
    row = {"row_id": "r1", "line_id": "l1", "beat_number": 1,
           "start_s": 0.0, "end_s": 8.0, "line": "line one", "who_sings": "c1",
           "on_screen": ["c1"], "location_id": "kitchen", "time_of_day": "morning",
           "wardrobe": {"c1": "w1"}, "lip_sync": True, "emotion": "resolve",
           "intensity": 2, "facial_cues": cues, "event": {"kind": "letter"}}
    ok = check_script({"rows": [row]}, {"beats": [beat]})
    assert ok["ok"], ok["defects"]
    moved = dict(row, location_id="church")
    assert any(d["code"] == "SCRIPT_OFF_BEAT"
               for d in check_script({"rows": [moved]}, {"beats": [beat]})["defects"])


if __name__ == "__main__":
    _selfcheck()
    print("beat_sheet.script selfcheck: OK")
