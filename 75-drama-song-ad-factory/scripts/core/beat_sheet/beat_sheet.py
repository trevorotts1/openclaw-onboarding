#!/usr/bin/env python3
"""beat_sheet.py: Story Beats, their gate, the story script and its checks.

Section 9.3 / N-115. The Story Beats are what happens, in order, decided before
any script row: ``storyboard/story-beats.json`` holds one row per beat with its
eleven fields, and the beats gate (eight checks) must pass before a single
script row is written. A later row that points at a beat carries that beat's
number; a row that adds, drops or moves an event, or changes who is there,
where they are, what they wear or the direction of the emotion, fails
``SCRIPT_OFF_BEAT``. A shot route whose cast or place is not its beat's fails
``SHOT_OFF_BEAT``.

The checks are data checks: pure functions, stdlib only, no IO, no model call,
no mutation of the input records. Severity follows section 3J: every finding
carries a level and, when MAJOR, the item number from the fixed MAJOR list.

The story script (this plan calls it the beat sheet) is one row per lyric line,
written from the beats by one writer per song section at the same time and
joined in time order by ``join_sections`` (N-63 / N-74).
"""
from __future__ import annotations

import hashlib
import json

SCHEMA_VERSION = "s75.beat-sheet.v1"
STORY_BEATS_SCHEMA_VERSION = "s75.story-beats.v1"
SPINE_SCHEMA_VERSION = "s75.story-spine.v1"

MAJOR = "MAJOR"
MEDIUM = "MEDIUM"
MINOR = "MINOR"

#: The Emotion Track's ten emotions, in the plan's order (section 3G.1).
EMOTIONS = (
    "pain", "worry", "exhaustion", "anger", "hope",
    "relief", "joy", "pride", "tenderness", "resolve",
)
INTENSITIES = (1, 2, 3)

#: The six facial cues every row must carry (section 3G.1).
FACIAL_CUES = ("eyes", "brows", "mouth", "smile", "teeth", "tears")

#: A beat carries eleven field groups (N-115 / the Story Beats section).
BEAT_FIELD_GROUPS = (
    ("beat_number", "name"),                 # 1  number and a five-word name
    ("start_s", "end_s", "lyric_lines"),     # 2  the lyric window
    ("who",),                                # 3  who, incl. who else is seen
    ("location_id", "time_of_day"),          # 4  where and when
    ("wardrobe",),                           # 5  what they wear
    ("entrances", "exits"),                  # 6  entrance and exit
    ("emotion_start", "emotion_end"),        # 7  the emotional arc
    ("change",),                             # 8  the change this beat delivers
    ("event",),                              # 9  the event the lyric names
    ("props_change",),                       # 10 props that change
    ("lip_sync_candidates",),                # 11 lip-sync candidates
)
BEAT_FIELDS = tuple(name for group in BEAT_FIELD_GROUPS for name in group)

#: The script row is one row per lyric line, keyed to its measured time and beat.
SCRIPT_ROW_FIELDS = (
    "row_id", "line_id", "beat_number", "start_s", "end_s", "who_sings",
    "singing", "location_id", "time_of_day", "wardrobe", "on_screen",
    "written_objects", "lip_sync", "emotion", "intensity", "facial_cues",
    "line_match",
)

#: Matches only against the beat it belongs to; never a fuzzy mapping.
LINE_MATCH_VERDICTS = ("MATCH", "WEAK", "MISMATCH")

#: Order of a story day. A beat that runs backwards is a logic break.
TIME_OF_DAY_ORDER = ("dawn", "morning", "midday", "afternoon", "evening", "night")
TIME_OF_DAY_ALIASES = {
    "sunrise": "dawn", "daybreak": "dawn", "early morning": "dawn",
    "day": "morning", "late morning": "morning",
    "noon": "midday", "lunch": "midday",
    "late afternoon": "afternoon",
    "dusk": "evening", "sunset": "evening", "twilight": "evening",
    "nighttime": "night", "late night": "night", "dark": "night",
}

#: Section 3J.1: only these codes are MAJOR, and each names its item number.
#: Everything not listed here is MEDIUM at most (section 3J).
_SEVERITY = {
    # item 8: lip-sync by the wrong singer, or on the wrong words
    "WRONG_SINGER": (MAJOR, 8),
    # item 9: a story-logic break
    "LINE_WITHOUT_BEAT": (MAJOR, 9),
    "BEAT_WINDOWS_OVERLAP": (MAJOR, 9),
    "BEAT_NO_CHANGE": (MAJOR, 9),
    "DOUBLE_ENTRANCE": (MAJOR, 9),
    "TIME_BACKWARD": (MAJOR, 9),
    "WARDROBE_MID_SCENE": (MAJOR, 9),
    "EMOTION_JUMP": (MAJOR, 9),
    "EVENT_REPEATED": (MAJOR, 9),
    "EVENT_OFF_LYRIC": (MAJOR, 9),
    "EVENT_UNDER_LIP_WINDOW": (MAJOR, 9),
    "HOOK_NOT_SUNG": (MAJOR, 9),
    "SCRIPT_OFF_BEAT": (MAJOR, 9),
    "PROFILE_OFF_BEAT": (MAJOR, 9),
    "RELATION_CONFLICT": (MAJOR, 9),
    # item 10: a lyric line with a MISMATCH verdict
    "MISMATCH": (MAJOR, 10),
    # item 11: a missing required scene or shot; a placeholder in the master
    "OPENING_MISSING": (MAJOR, 11),
    "SHOT_OFF_BEAT": (MAJOR, 11),
    "EMOTION_MISSING": (MAJOR, 11),
    "LINE_MATCH_MISSING": (MAJOR, 11),
    "BEAT_SCHEMA": (MAJOR, 11),
    "REVIEW_MISSING": (MAJOR, 11),
    "CAST_DISCOVERY_INCOMPLETE": (MAJOR, 11),
    "CAST_NOT_IN_BIBLE": (MAJOR, 11),
    "WORLD_BUILDOUT_INCOMPLETE": (MAJOR, 11),
    "LOCATION_NOT_IN_WORLD_BIBLE": (MAJOR, 11),
    # item 15: a check that could not run (fails closed)
    "VOICE_MAP_MISSING": (MAJOR, 15),
    "REVIEW_MODEL_SAME": (MAJOR, 15),
    "REVIEW_LOOP": (MAJOR, 15),
}

#: MEDIUM findings: they pass and are logged; they never stop a run.
_MEDIUM_CODES = (
    "WEAK", "TASTE_NOTE", "REVIEW_FINDING_OPEN", "WEAK_CAP_EXCEEDED",
    "BEAT_OUT_OF_ORDER", "TIME_UNKNOWN", "BEAT_NAME_LONG", "SCENE_UNKNOWN",
)


def severity(code):
    """Return {"level": ..., "item": ...} for one finding code (section 3J)."""
    if code in _SEVERITY:
        level, item = _SEVERITY[code]
        return {"level": level, "item": item}
    if code in _MEDIUM_CODES:
        return {"level": MEDIUM, "item": None}
    # Anything not on the MAJOR list is MEDIUM at most (section 3J).
    return {"level": MEDIUM, "item": None}


def artifact_digest(record):
    """Canonical sha256 for any JSON-able record (local, stdlib only)."""
    blob = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# --- small shared helpers -------------------------------------------------

def _blank(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def _words(value):
    if not isinstance(value, str):
        return 0
    return len(value.replace("…", " ").replace(".", " ").split())


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _norm(value):
    return " ".join(str(value or "").split()).lower()


def _defect(code, pointer, detail=None, **extra):
    """One finding: code, level, MAJOR item number, exact pointer."""
    level = severity(code)
    out = {"code": code, "pointer": pointer,
           "level": level["level"], "item": level["item"]}
    if detail:
        out["detail"] = detail
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def _time_index(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _norm(value)
    if not text:
        return None
    text = TIME_OF_DAY_ALIASES.get(text, text)
    if text in TIME_OF_DAY_ORDER:
        return float(TIME_OF_DAY_ORDER.index(text))
    # "evening (day 2)" and similar qualified times keep their base word
    head = text.split("(", 1)[0].strip()
    head = TIME_OF_DAY_ALIASES.get(head, head)
    if head in TIME_OF_DAY_ORDER:
        return float(TIME_OF_DAY_ORDER.index(head)) + (
            1000.0 * max(0.0, float(_trailing_number(text) or 1) - 1))
    return None


def _trailing_number(text):
    digits = ""
    for char in reversed(text):
        if char.isdigit():
            digits = char + digits
        elif digits:
            break
    return int(digits) if digits else None


def _emotion_tag(value):
    """A tag is an object with a known emotion and an intensity of 1, 2 or 3."""
    if not isinstance(value, dict):
        return False
    if value.get("emotion") not in EMOTIONS:
        return False
    intensity = value.get("intensity")
    return isinstance(intensity, int) and not isinstance(intensity, bool) \
        and intensity in INTENSITIES


# --- N-115: Story Beats and the beats gate --------------------------------

def validate_beat(beat, pointer="/beats/0"):
    """Schema defects for one beat row: its eleven field groups must be real."""
    if not isinstance(beat, dict):
        return [_defect("BEAT_SCHEMA", pointer, "beat is not an object")]
    defects = []
    for field in BEAT_FIELDS:
        if field not in beat:
            defects.append(_defect("BEAT_SCHEMA", pointer + "/" + field, "missing field"))

    number = beat.get("beat_number")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        defects.append(_defect("BEAT_SCHEMA", pointer + "/beat_number",
                               "beat_number must be a positive integer"))

    name = beat.get("name")
    if _blank(name) or not isinstance(name, str):
        defects.append(_defect("BEAT_SCHEMA", pointer + "/name", "name is required"))
    elif _words(name) > 5:
        defects.append(_defect("BEAT_NAME_LONG", pointer + "/name",
                               "name must be five words or fewer"))

    start, end = _num(beat.get("start_s")), _num(beat.get("end_s"))
    if start is None or end is None or end <= start:
        defects.append(_defect("BEAT_SCHEMA", pointer + "/start_s",
                               "a beat needs numeric start_s < end_s"))
    lines = beat.get("lyric_lines")
    if not isinstance(lines, list) or not lines:
        defects.append(_defect("BEAT_SCHEMA", pointer + "/lyric_lines",
                               "a beat carries the lyric lines inside its window"))

    who = beat.get("who")
    if not isinstance(who, dict):
        defects.append(_defect("BEAT_SCHEMA", pointer + "/who", "who must be an object"))
    else:
        for key in ("on_screen", "singing", "listening", "else_seen"):
            if key not in who:
                defects.append(_defect("BEAT_SCHEMA", pointer + "/who/" + key,
                                       "who.else_seen names the ancillary people or says "
                                       "'nobody else is seen here'"))
        if not isinstance(who.get("on_screen") or [], list):
            defects.append(_defect("BEAT_SCHEMA", pointer + "/who/on_screen",
                                   "on_screen must be a list of character ids"))

    if _blank(beat.get("location_id")):
        defects.append(_defect("BEAT_SCHEMA", pointer + "/location_id",
                               "every beat names one place"))
    if _time_index(beat.get("time_of_day")) is None:
        defects.append(_defect("TIME_UNKNOWN", pointer + "/time_of_day",
                               "time_of_day is not on the story clock"))

    if not isinstance(beat.get("wardrobe"), dict):
        defects.append(_defect("BEAT_SCHEMA", pointer + "/wardrobe",
                               "wardrobe maps each character to a wardrobe id"))
    for field in ("entrances", "exits"):
        if not isinstance(beat.get(field), list):
            defects.append(_defect("BEAT_SCHEMA", pointer + "/" + field,
                                   "%s must be a list" % field))
    for field in ("emotion_start", "emotion_end"):
        if not _emotion_tag(beat.get(field)):
            defects.append(_defect("EMOTION_MISSING", pointer + "/" + field,
                                   "an emotion from the Emotion Track and intensity 1-3"))
    if _blank(beat.get("change")):
        defects.append(_defect("BEAT_NO_CHANGE", pointer + "/change",
                               "a beat with no change is not a beat"))
    event = beat.get("event")
    if event is not None and not isinstance(event, dict):
        defects.append(_defect("BEAT_SCHEMA", pointer + "/event",
                               "event is null or an object with kind and line"))
    if event is not None and isinstance(event, dict):
        if _blank(event.get("kind")):
            defects.append(_defect("BEAT_SCHEMA", pointer + "/event/kind",
                                   "an event names its kind"))
        if _blank(event.get("line")):
            defects.append(_defect("EVENT_OFF_LYRIC", pointer + "/event/line",
                                   "an event names the exact lyric line it happens on"))
    if not isinstance(beat.get("props_change") or [], list):
        defects.append(_defect("BEAT_SCHEMA", pointer + "/props_change",
                               "props_change must be a list"))
    if not isinstance(beat.get("lip_sync_candidates") or [], list):
        defects.append(_defect("BEAT_SCHEMA", pointer + "/lip_sync_candidates",
                               "lip_sync_candidates must be a list"))
    return defects


def _line_key(line):
    if isinstance(line, dict):
        return (_norm(line.get("line_id")), _norm(line.get("text")))
    return ("", _norm(line))


def _beat_line_keys(beat):
    keys = set()
    for line in beat.get("lyric_lines") or []:
        if isinstance(line, dict):
            key = _line_key(line)
            if key[0]:
                keys.add(key[0])
            if key[1]:
                keys.add(key[1])
        elif isinstance(line, str):
            keys.add(_norm(line))
    return keys


def _check_line_homes(beats, measured_lines):
    defects = []
    if not isinstance(measured_lines, list) or not measured_lines:
        return defects
    homes = {}
    for beat in beats:
        for key in _beat_line_keys(beat):
            homes.setdefault(key, []).append(beat.get("beat_number"))
    for line in measured_lines:
        key = _line_key(line)
        found = [homes.get(key[0]) or [], homes.get(key[1]) or []]
        count = max(len(found[0]), len(found[1]))
        if count == 0:
            defects.append(_defect("LINE_WITHOUT_BEAT", "/beats",
                                   "measured line has no home",
                                   line_id=(line or {}).get("line_id")))
        elif count > 1:
            defects.append(_defect("BEAT_WINDOWS_OVERLAP", "/beats",
                                   "measured line sits in more than one beat",
                                   line_id=(line or {}).get("line_id")))
    return defects


def _check_windows(beats):
    defects = []
    ordered = sorted(beats, key=lambda b: _num(b.get("start_s")) or 0.0)
    for index in range(1, len(ordered)):
        previous, current = ordered[index - 1], ordered[index]
        prev_end = _num(previous.get("end_s"))
        cur_start = _num(current.get("start_s"))
        if prev_end is None or cur_start is None:
            continue
        if cur_start < prev_end - 0.001:
            defects.append(_defect("BEAT_WINDOWS_OVERLAP", "/beats/%s" % current.get("beat_number"),
                                   "lyric windows overlap"))
        elif cur_start > prev_end + 0.001:
            defects.append(_defect("BEAT_WINDOWS_OVERLAP", "/beats/%s" % current.get("beat_number"),
                                   "lyric windows leave a gap no line fills"))
    return defects


def _state_signature(beat):
    who = beat.get("who") or {}
    return (
        _norm(beat.get("location_id")),
        _norm(beat.get("time_of_day")),
        tuple(sorted(_norm(c) for c in (who.get("on_screen") or []))),
        tuple(sorted((_norm(k), _norm(v)) for k, v in (beat.get("wardrobe") or {}).items())),
    )


def _check_changes(beats):
    defects = []
    previous = None
    for beat in beats:
        start = (beat.get("emotion_start") or {})
        end = (beat.get("emotion_end") or {})
        changed = start != end
        if not changed and beat.get("state_after") not in (None, "", [], {}):
            changed = True
        if not changed and previous is not None:
            changed = _state_signature(beat) != _state_signature(previous)
        if not changed:
            defects.append(_defect("BEAT_NO_CHANGE", "/beats/%s/change" % beat.get("beat_number"),
                                   "the state at the end is the state at the start"))
        previous = beat
    return defects


def _entries(beat, field):
    out = []
    for entry in beat.get(field) or []:
        if isinstance(entry, dict):
            char = _norm(entry.get("character_id") or entry.get("who"))
            place = _norm(entry.get("location_id") or beat.get("location_id"))
            if char:
                out.append((char, place))
        elif isinstance(entry, str) and entry.strip():
            out.append((_norm(entry), _norm(beat.get("location_id"))))
    return out


def _check_entrances(beats):
    defects = []
    inside = {}
    for beat in beats:
        for char, place in _entries(beat, "entrances"):
            key = (char, place)
            if inside.get(key):
                defects.append(_defect("DOUBLE_ENTRANCE",
                                       "/beats/%s/entrances" % beat.get("beat_number"),
                                       "a character enters a place twice with no exit",
                                       character_id=char, location_id=place))
            inside[key] = True
        for char, place in _entries(beat, "exits"):
            key = (char, place)
            if not inside.get(key):
                defects.append(_defect("DOUBLE_ENTRANCE",
                                       "/beats/%s/exits" % beat.get("beat_number"),
                                       "an exit with no entrance before it",
                                       character_id=char, location_id=place))
            inside[key] = False
    return defects


def _check_time(beats):
    defects = []
    prior = None
    for beat in beats:
        index = _time_index(beat.get("time_of_day"))
        if beat.get("flashback"):
            prior = index if index is not None else prior
            continue
        if index is None or prior is None:
            prior = index if index is not None else prior
            continue
        if index < prior:
            defects.append(_defect("TIME_BACKWARD",
                                   "/beats/%s/time_of_day" % beat.get("beat_number"),
                                   "time of day runs backwards"))
        prior = index
    return defects


def _check_wardrobe(beats):
    defects = []
    previous = None
    for beat in beats:
        if previous is not None:
            scene_changed = (_norm(beat.get("location_id")) != _norm(previous.get("location_id"))
                             or _norm(beat.get("time_of_day")) != _norm(previous.get("time_of_day"))
                             or bool(beat.get("flashback")))
            prior_wardrobe = previous.get("wardrobe") or {}
            for char, wardrobe in (beat.get("wardrobe") or {}).items():
                if not scene_changed and _norm(prior_wardrobe.get(char)) \
                        and _norm(prior_wardrobe.get(char)) != _norm(wardrobe):
                    defects.append(_defect("WARDROBE_MID_SCENE",
                                           "/beats/%s/wardrobe/%s" % (beat.get("beat_number"), char),
                                           "wardrobe changes inside one scene",
                                           character_id=char))
        previous = beat
    return defects


def _arc_explained(beat, previous_end):
    if beat.get("arc_bridge") not in (None, "", [], {}):
        return True
    change = _norm(beat.get("change"))
    previous = _norm((previous_end or {}).get("emotion"))
    current = _norm((beat.get("emotion_start") or {}).get("emotion"))
    return bool(previous and current and previous in change and current in change)


def _check_arc(beats):
    defects = []
    for index in range(1, len(beats)):
        previous_end = beats[index - 1].get("emotion_end") or {}
        current_start = beats[index].get("emotion_start") or {}
        if previous_end == current_start:
            continue
        if _arc_explained(beats[index], previous_end):
            continue
        defects.append(_defect("EMOTION_JUMP",
                               "/beats/%s/emotion_start" % beats[index].get("beat_number"),
                               "the arc jumps with no bridge and no reason in the change"))
    return defects


def _check_events(beats):
    defects = []
    seen = {}
    for beat in beats:
        event = beat.get("event")
        if not isinstance(event, dict) or _blank(event.get("kind")):
            continue
        kind = _norm(event.get("kind"))
        seen.setdefault(kind, []).append(beat.get("beat_number"))
        line = event.get("line")
        if not _blank(line) and _norm(line) not in _beat_line_keys(beat):
            defects.append(_defect("EVENT_OFF_LYRIC",
                                   "/beats/%s/event/line" % beat.get("beat_number"),
                                   "the event does not happen on one of this beat's lines",
                                   event_kind=kind))
    for kind, numbers in seen.items():
        if len(numbers) > 1:
            for number in numbers[1:]:
                defects.append(_defect("EVENT_REPEATED",
                                       "/beats/%s/event" % number,
                                       "an event the lyrics name happens once",
                                       event_kind=kind))
    return defects


def _has_lip_sync_between(beat, start_s, end_s):
    for candidate in beat.get("lip_sync_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        c_start = _num(candidate.get("start_s"))
        c_end = _num(candidate.get("end_s"))
        if c_start is None or c_end is None:
            continue
        if c_end > start_s and c_start < end_s:
            return True
    if (beat.get("who") or {}).get("singing"):
        b_start = _num(beat.get("start_s")) or 0.0
        b_end = _num(beat.get("end_s")) or 0.0
        return b_end > start_s and b_start < end_s
    return False


def _check_opening_and_hook(beats, hook_lines, opening_window_s):
    defects = []
    first = min(beats, key=lambda b: _num(b.get("start_s")) or 0.0) if beats else None
    if first is None or not _has_lip_sync_between(first, 0.0, opening_window_s):
        defects.append(_defect("OPENING_MISSING", "/beats",
                               "the opening passage carries a lip-synced talking or singing piece"))
    if hook_lines:
        for hook in hook_lines:
            key = _line_key(hook)
            found = False
            for beat in beats:
                if key[0] not in _beat_line_keys(beat) and key[1] not in _beat_line_keys(beat):
                    continue
                if (beat.get("who") or {}).get("singing") or beat.get("lip_sync_candidates"):
                    found = True
                    break
            if not found:
                defects.append(_defect("HOOK_NOT_SUNG", "/beats",
                                       "every hook line has someone shown singing it",
                                       line_id=(hook or {}).get("line_id") if isinstance(hook, dict) else None))
    return defects


def validate_story_beats(record, measured_lines=None, hook_lines=None,
                         opening_window_s=15.0):
    """The beats gate: schema, then the eight checks (N-115).

    Returns {"ok", "schema_version", "beat_count", "defects", "counts"}.
    Defects are ordered and each carries its section 3J level and item.
    """
    verdict = {"ok": False, "schema_version": STORY_BEATS_SCHEMA_VERSION,
               "beat_count": 0, "defects": [], "counts": {}}
    if not isinstance(record, dict) or not isinstance(record.get("beats"), list) \
            or not record.get("beats"):
        verdict["defects"] = [_defect("BEAT_SCHEMA", "/beats",
                                      "story-beats.json needs a non-empty beats list")]
        return verdict
    beats = record["beats"]
    verdict["beat_count"] = len(beats)

    defects = []
    for index, beat in enumerate(beats):
        defects.extend(validate_beat(beat, "/beats/%d" % index))
    numbers = [b.get("beat_number") for b in beats if isinstance(b, dict)]
    if len(set(numbers)) != len(numbers):
        defects.append(_defect("BEAT_SCHEMA", "/beats", "duplicate beat_number"))
    for index in range(1, len(beats)):
        a, b = beats[index - 1], beats[index]
        if (_num(a.get("start_s")) or 0.0) > (_num(b.get("start_s")) or 0.0):
            defects.append(_defect("BEAT_OUT_OF_ORDER", "/beats/%d" % index,
                                   "beats are written in song order"))

    good = [b for b in beats if isinstance(b, dict)]
    defects.extend(_check_line_homes(good, measured_lines))
    defects.extend(_check_windows(good))
    defects.extend(_check_changes(good))
    defects.extend(_check_entrances(good))
    defects.extend(_check_time(good))
    defects.extend(_check_wardrobe(good))
    defects.extend(_check_arc(good))
    defects.extend(_check_events(good))
    defects.extend(_check_opening_and_hook(good, hook_lines, opening_window_s))

    counts = {}
    for defect in defects:
        counts[defect["level"]] = counts.get(defect["level"], 0) + 1
    verdict["defects"] = defects
    verdict["counts"] = counts
    verdict["ok"] = not any(d["level"] == MAJOR for d in defects)
    return verdict


def story_beats_gate(*args, **kwargs):
    """Alias: the eight-check beats gate before any script row (N-115)."""
    return validate_story_beats(*args, **kwargs)


def shot_off_beat_defects(routes, beats_record):
    """SHOT_OFF_BEAT: a shot's cast or place must be its beat's (N-115)."""
    defects = []
    beats = {}
    for beat in (beats_record or {}).get("beats") or []:
        if isinstance(beat, dict):
            beats[beat.get("beat_number")] = beat
    for index, route in enumerate(routes or []):
        pointer = "/shot-routes/%d" % index
        if not isinstance(route, dict):
            defects.append(_defect("SHOT_OFF_BEAT", pointer, "route is not an object"))
            continue
        number = route.get("beat_number")
        beat = beats.get(number)
        if beat is None:
            defects.append(_defect("SHOT_OFF_BEAT", pointer + "/beat_number",
                                   "a shot route carries its beat's number"))
            continue
        if _norm(route.get("location_id")) and \
                _norm(route.get("location_id")) != _norm(beat.get("location_id")):
            defects.append(_defect("SHOT_OFF_BEAT", pointer + "/location_id",
                                   "the shot's place is not its beat's"))
        route_cast = {_norm(c) for c in route.get("cast_ids") or [] if c}
        beat_cast = {_norm(c) for c in (beat.get("who") or {}).get("on_screen") or [] if c}
        if route_cast and beat_cast and not route_cast.issubset(beat_cast):
            defects.append(_defect("SHOT_OFF_BEAT", pointer + "/cast_ids",
                                   "the shot's cast is not its beat's",
                                   extra=sorted(route_cast - beat_cast)))
    return defects
