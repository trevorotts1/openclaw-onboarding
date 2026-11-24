#!/usr/bin/env python3
"""world_bible: the World Bible of plan section 3M.4 (N-121).

One entry per place in the lock file, plus the story clock. The record answers
the four things the old location bible could not:

* **size, in numbers** -- width, depth (and height where it matters), so a
  shot's action can fit a room rather than an adjective;
* **a layout map** with fixed sides, doors and what leads where, and the fixed
  things (fridge, window, clock, pew rows, loft tiers);
* **set pieces** -- the things that make this room and no other room;
* **crowd states** -- for each state the story uses, a count range, the crowd
  reference picture drawn for it, and the sentence a prompt carries instead of
  the blanket "no extra people" line. That line survives only for an empty
  room: ``NO_EXTRA_PEOPLE_LINE`` is emitted by ``crowd_prompt_lines()`` only
  when the state's count is zero.

The story clock: every beat names its place, crowd state and time; a clock
entry never runs backwards within a day, and a later day may start earlier.

``continuity_questions()`` returns the world-continuity check questions as
data (``continuity_questions.json``), which the clip checks read; each has a
fixed code and a default level, with the MAJOR escalation stated beside it.
The level helpers below apply the numeric part of the 3M.4 table to an
observed count.

Standard library only, no IO on import (the questions are loaded lazily on
first use), no provider or network call.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re

BIBLE_SCHEMA_VERSION = "1.0.0"
BIBLE_KIND = "world_bible"

#: The blanket line that emptied every room (skill 75's H3 template carried it
#: as a fixed negative). It is sent ONLY for a shot whose crowd state is empty.
NO_EXTRA_PEOPLE_LINE = "no extra people beyond those named"

#: Refusal codes this unit raises before spend (3C.10 part 1, world side).
CODE_LOCATION_NOT_IN_BIBLE = "LOCATION_NOT_IN_WORLD_BIBLE"
CODE_WORLD_REFERENCE_MISSING = "WORLD_REFERENCE_MISSING"
CODE_UNNAMED_PLACE_IN_PROMPT = "UNNAMED_PLACE_IN_PROMPT"
CODE_BUILDOUT_INCOMPLETE = "WORLD_BUILDOUT_INCOMPLETE"

#: Codes of the world-continuity check (3M.4). The clip checks read them from
#: ``continuity_questions()``; they are named here so code can compare them.
CROWD_MISMATCH = "CROWD_MISMATCH"
CHOIR_COUNT_MISMATCH = "CHOIR_COUNT_MISMATCH"
PLACE_MISMATCH = "PLACE_MISMATCH"
SET_PIECE_MISSING = "SET_PIECE_MISSING"
LIGHT_OFF_CLOCK = "LIGHT_OFF_CLOCK"

#: A day's order; the clock may move forward, never back within one day.
TIME_OF_DAY_ORDER = ("dawn", "morning", "midday", "afternoon", "sunset",
                     "evening", "night")
TIME_OF_DAY_ALIASES = {
    "sunrise": "dawn", "early_morning": "dawn", "morning": "morning",
    "late_morning": "morning", "noon": "midday", "mid_day": "midday",
    "midday": "midday", "afternoon": "afternoon", "late_afternoon": "afternoon",
    "golden_hour": "sunset", "sunset": "sunset", "dusk": "sunset",
    "twilight": "sunset", "evening": "evening", "night": "night",
    "nighttime": "night", "midnight": "night",
}

LOCATION_ID_RE = re.compile(r"^loc_[A-Za-z0-9][A-Za-z0-9_.-]*$")

#: Place words a prompt uses to describe a room in prose. A job whose text
#: holds one of these and carries no place id is ``UNNAMED_PLACE_IN_PROMPT``.
PLACE_WORDS = (
    "church", "chapel", "sanctuary", "loft", "vestry", "kitchen", "office",
    "porch", "doorway", "hall", "street", "room", "house", "yard", "steps",
    "store", "restaurant", "school", "classroom", "stage", "garden", "garage",
)

_QUESTIONS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "continuity_questions.json")
_QUESTIONS = None


class WorldBibleError(ValueError):
    """Raised when the World Bible refuses a record or a job."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _nonempty(value):
    return isinstance(value, str) and value.strip() != ""


def _nonempty_str_list(value):
    return (isinstance(value, list) and len(value) > 0
            and all(_nonempty(v) for v in value))


def _positive_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0)


def _count(value):
    return (isinstance(value, int) and not isinstance(value, bool) and value >= 0)


def _norm_time(label):
    return re.sub(r"[\s-]+", "_", str(label).strip().lower())


def time_of_day_index(label):
    """Position of a time-of-day label in the day, or raise ``WorldBibleError``."""
    norm = _norm_time(label)
    norm = TIME_OF_DAY_ALIASES.get(norm, norm)
    try:
        return TIME_OF_DAY_ORDER.index(norm)
    except ValueError:
        raise WorldBibleError([
            "%s: time of day %r is not one of %s (aliases %s)"
            % (CODE_BUILDOUT_INCOMPLETE, label, ", ".join(TIME_OF_DAY_ORDER),
               ", ".join(sorted(TIME_OF_DAY_ALIASES)))
        ]) from None


def _validate_count(entry, pointer, errors):
    count = entry.get("count")
    if not isinstance(count, dict):
        errors.append("%s.count is required: a min and a max" % pointer)
        return
    low, high = count.get("min"), count.get("max")
    if not _count(low):
        errors.append("%s.count.min must be an integer >= 0" % pointer)
    if not _count(high):
        errors.append("%s.count.max must be an integer >= 0" % pointer)
    if _count(low) and _count(high) and low > high:
        errors.append("%s.count.min %d is above count.max %d" % (pointer, low, high))


def _validate_choir(entry, pointer, errors, required):
    choir = entry.get("choir")
    if choir is None:
        if required:
            errors.append("%s.choir is required: this place has a choir, so every crowd "
                          "state carries its headcount" % pointer)
        return
    if not isinstance(choir, dict):
        errors.append("%s.choir must be an object with a count and, when the count is "
                      "above zero, where they stand" % pointer)
        return
    count = choir.get("count")
    if not _count(count) or count < 0:
        errors.append("%s.choir.count must be an integer >= 0" % pointer)
    elif count > 0 and not _nonempty(choir.get("where")):
        errors.append("%s.choir.where is required when the choir is present" % pointer)


def _validate_crowd_states(place, pointer, errors):
    states = place.get("crowd_states")
    if not isinstance(states, list) or not states:
        errors.append("%s.crowd_states is required: one state per crowd the story uses, "
                      "each with a count and a crowd reference picture" % pointer)
        return
    has_choir = place.get("has_choir") is True
    seen = set()
    for index, state in enumerate(states):
        where = "%s.crowd_states[%d]" % (pointer, index)
        if not isinstance(state, dict):
            errors.append("%s must be an object" % where)
            continue
        state_id = state.get("state_id")
        if not _nonempty(state_id):
            errors.append("%s.state_id is required" % where)
        elif state_id in seen:
            errors.append("%s.state_id %r is duplicated" % (where, state_id))
        else:
            seen.add(state_id)
        _validate_count(state, where, errors)
        if not _nonempty(state.get("reference_picture_id")):
            errors.append("%s.reference_picture_id is required: a crowd reference picture "
                          "per state" % where)
        if not _nonempty(state.get("crowd_line")):
            errors.append("%s.crowd_line is required: the sentence this state puts in a "
                          "prompt instead of the blanket line" % where)
        _validate_choir(state, where, errors, has_choir)


def _validate_time_variants(place, pointer, errors):
    variants = place.get("time_of_day_variants")
    if not isinstance(variants, list) or not variants:
        errors.append("%s.time_of_day_variants is required: one variant per time on the "
                      "story clock, made from the base wide" % pointer)
        return
    seen = set()
    for index, variant in enumerate(variants):
        where = "%s.time_of_day_variants[%d]" % (pointer, index)
        if not isinstance(variant, dict):
            errors.append("%s must be an object" % where)
            continue
        label = variant.get("time_of_day")
        if not _nonempty(label):
            errors.append("%s.time_of_day is required" % where)
        else:
            try:
                key = TIME_OF_DAY_ORDER[time_of_day_index(label)]
            except WorldBibleError:
                key = _norm_time(label)
            if key in seen:
                errors.append("%s.time_of_day %r is duplicated" % (where, label))
            seen.add(key)
        if not _nonempty(variant.get("reference_picture_id")):
            errors.append("%s.reference_picture_id is required" % where)


def validate_place(place, pointer="place"):
    """Return the defects of one place entry; empty list means usable."""
    errors = []
    if not isinstance(place, dict):
        return ["%s must be an object" % pointer]
    loc_id = place.get("location_id")
    if not _nonempty(loc_id):
        errors.append("%s.location_id is required" % pointer)
    elif not LOCATION_ID_RE.match(loc_id):
        errors.append("%s.location_id %r must match loc_<slug>" % (pointer, loc_id))
    if not _nonempty(place.get("name")):
        errors.append("%s.name is required" % pointer)
    if not isinstance(place.get("locked"), bool):
        errors.append("%s.locked must be true or false" % pointer)

    size = place.get("size")
    if not isinstance(size, dict):
        errors.append("%s.size is required: the room's width and depth in numbers" % pointer)
    else:
        for key in ("width", "depth"):
            if not _positive_number(size.get(key)):
                errors.append("%s.size.%s must be a positive number" % (pointer, key))
        if "height" in size and not _positive_number(size.get("height")):
            errors.append("%s.size.height must be a positive number when given" % pointer)
        if size.get("unit") not in ("meters", "feet"):
            errors.append("%s.size.unit must be 'meters' or 'feet'" % pointer)

    layout = place.get("layout_map")
    if not isinstance(layout, dict):
        errors.append("%s.layout_map is required: fixed sides, doors and fixed things"
                      % pointer)
    else:
        if not _nonempty_str_list(layout.get("fixed_sides")):
            errors.append("%s.layout_map.fixed_sides is required" % pointer)
        doors = layout.get("doors")
        if not isinstance(doors, list) or not doors:
            errors.append("%s.layout_map.doors is required: every door and where it leads"
                          % pointer)
        else:
            for index, door in enumerate(doors):
                where = "%s.layout_map.doors[%d]" % (pointer, index)
                if not isinstance(door, dict):
                    errors.append("%s must be an object with a name and a leads_to" % where)
                    continue
                if not _nonempty(door.get("name")):
                    errors.append("%s.name is required" % where)
                if not _nonempty(door.get("leads_to")):
                    errors.append("%s.leads_to is required" % where)
        if not _nonempty_str_list(layout.get("fixed_things")):
            errors.append("%s.layout_map.fixed_things is required: the fridge, window, "
                          "clock, rows and tiers that stay put" % pointer)

    if not _nonempty_str_list(place.get("set_pieces")):
        errors.append("%s.set_pieces is required: the things that make this room and no "
                      "other room" % pointer)
    else:
        pieces = [p.strip().lower() for p in place["set_pieces"]]
        if len(set(pieces)) != len(pieces):
            errors.append("%s.set_pieces repeats a value" % pointer)

    pictures = place.get("establishing_pictures")
    if not isinstance(pictures, list) or not pictures:
        errors.append("%s.establishing_pictures is required: a wide per camera side the "
                      "storyboard uses" % pointer)
    else:
        for index, picture in enumerate(pictures):
            where = "%s.establishing_pictures[%d]" % (pointer, index)
            if not isinstance(picture, dict):
                errors.append("%s must be an object with a picture_id" % where)
                continue
            if not _nonempty(picture.get("picture_id")):
                errors.append("%s.picture_id is required" % where)

    _validate_crowd_states(place, pointer, errors)
    _validate_time_variants(place, pointer, errors)

    if not isinstance(place.get("has_choir"), bool):
        errors.append("%s.has_choir must be true or false" % pointer)
    return errors


def validate_bible(bible):
    """Return the defects of a World Bible record; empty list means usable."""
    errors = []
    if not isinstance(bible, dict):
        return ["World Bible record must be a JSON object"]
    if bible.get("schema_version") != BIBLE_SCHEMA_VERSION:
        errors.append("schema_version must be %r" % BIBLE_SCHEMA_VERSION)
    if bible.get("kind") != BIBLE_KIND:
        errors.append("kind must be %r" % BIBLE_KIND)
    if not isinstance(bible.get("revision"), int) or isinstance(
            bible.get("revision"), bool) or bible["revision"] < 1:
        errors.append("revision must be a positive integer")
    lock = bible.get("lock")
    if not isinstance(lock, dict) or not isinstance(lock.get("version"), int) or \
            isinstance(lock.get("version"), bool) or lock["version"] < 1:
        errors.append("lock.version must be a positive integer")
    places = bible.get("places")
    if not isinstance(places, list) or not places:
        errors.append("places must list at least one place")
    else:
        seen = set()
        for index, place in enumerate(places):
            pointer = "places[%d]" % index
            errors.extend(validate_place(place, pointer))
            if isinstance(place, dict) and _nonempty(place.get("location_id")):
                loc_id = place["location_id"]
                if loc_id in seen:
                    errors.append("%s.location_id %r is duplicated" % (pointer, loc_id))
                seen.add(loc_id)
    clock = bible.get("story_clock")
    if not isinstance(clock, list):
        errors.append("story_clock must be a list of beat times")
    else:
        errors.extend(story_clock_defects(bible))
    return errors


def story_clock_defects(bible):
    """Every beat's time, in order, never running backwards within a day."""
    errors = []
    places = {}
    if isinstance(bible, dict):
        for place in bible.get("places") or []:
            if isinstance(place, dict) and _nonempty(place.get("location_id")):
                places[place["location_id"]] = place
    clock = bible.get("story_clock") if isinstance(bible, dict) else None
    if not isinstance(clock, list):
        return ["story_clock must be a list"]
    previous = None
    seen_beats = set()
    for index, entry in enumerate(clock):
        pointer = "story_clock[%d]" % index
        if not isinstance(entry, dict):
            errors.append("%s must be an object" % pointer)
            continue
        beat_id = entry.get("beat_id")
        if not _nonempty(beat_id):
            errors.append("%s.beat_id is required" % pointer)
        elif beat_id in seen_beats:
            errors.append("%s.beat_id %r is duplicated" % (pointer, beat_id))
        else:
            seen_beats.add(beat_id)
        loc_id = entry.get("place_id")
        place = places.get(loc_id)
        if not isinstance(place, dict):
            errors.append("%s.place_id %r is not a place in this Bible"
                          % (pointer, loc_id))
        state_id = entry.get("crowd_state_id")
        if not _nonempty(state_id):
            errors.append("%s.crowd_state_id is required: every beat names its place, "
                          "crowd state and time" % pointer)
        elif isinstance(place, dict) and state_for(place, state_id) is None:
            errors.append("%s.crowd_state_id %r is not a state of %r"
                          % (pointer, state_id, loc_id))
        label = entry.get("time_of_day")
        try:
            day_index = time_of_day_index(label)
        except WorldBibleError as exc:
            errors.extend(exc.errors)
            continue
        day = entry.get("day", 1)
        if not isinstance(day, int) or isinstance(day, bool) or day < 1:
            errors.append("%s.day must be a positive integer" % pointer)
            continue
        minute = entry.get("minute")
        if minute is not None and (not isinstance(minute, int)
                                   or isinstance(minute, bool) or minute < 0):
            errors.append("%s.minute must be a non-negative integer when given" % pointer)
        current = (day, day_index)
        if previous is not None:
            previous_day, previous_index = previous
            if day < previous_day:
                errors.append("%s.day %d runs backwards from day %d"
                              % (pointer, day, previous_day))
            elif day == previous_day and day_index < previous_index:
                errors.append("%s.time_of_day %r runs backwards within day %d"
                              % (pointer, label, day))
        previous = current
    return errors


def state_for(place, state_id):
    """The crowd state with this id in a place, or None."""
    if not isinstance(place, dict):
        return None
    for state in place.get("crowd_states") or []:
        if isinstance(state, dict) and state.get("state_id") == state_id:
            return state
    return None


#: 3M.4 rule 2: the scene kinds that default to a full room.
FULL_ROOM_SCENE_KINDS = ("service", "class", "meeting")


def default_crowd_state(place, scene_kind):
    """3M.4 rule 2: a service, a class or a meeting defaults to a full room.

    Returns the id of the place's own full crowd state (``full`` true, or the
    state named ``full``), so its count and its crowd reference picture come
    from the Bible. ``None`` when the kind is not one of those or the place has
    no full state: that is a build-out gap for the gate, never an empty room.
    """
    if not isinstance(place, dict):
        return None
    kind = re.sub(r"[\s-]+", "_", str(scene_kind or "").strip().lower())
    if kind not in FULL_ROOM_SCENE_KINDS:
        return None
    for state in place.get("crowd_states") or []:
        if not isinstance(state, dict):
            continue
        if state.get("full") is True or state.get("state_id") == "full":
            return state.get("state_id")
    return None


def is_empty_state(state):
    """True when this crowd state is an empty room (count max zero)."""
    if not isinstance(state, dict):
        return False
    count = state.get("count") or {}
    return count.get("max") == 0


def crowd_prompt_lines(place, state_id):
    """The lines a prompt carries for this place and crowd state.

    The blanket ``NO_EXTRA_PEOPLE_LINE`` is returned ONLY for an empty state.
    Any other state puts its own sentence in the prompt instead, so a service
    is described as a full room rather than emptied.
    """
    state = state_for(place, state_id)
    if state is None:
        raise WorldBibleError([
            "%s: crowd state %r is not in place %r; the state is created and locked "
            "before it is used" % (CODE_BUILDOUT_INCOMPLETE, state_id,
                                   (place or {}).get("location_id")
                                   if isinstance(place, dict) else None)
        ])
    line = state.get("crowd_line")
    if not _nonempty(line):
        raise WorldBibleError([
            "%s: crowd state %r in place %r has no crowd_line to send"
            % (CODE_BUILDOUT_INCOMPLETE, state_id,
               (place or {}).get("location_id"))
        ])
    lines = [line.strip()]
    if is_empty_state(state):
        lines.append(NO_EXTRA_PEOPLE_LINE)
    return lines


def crowd_mismatch_level(state, observed_count):
    """3M.4: MAJOR when the state is full and the room is empty or near empty;
    otherwise MEDIUM."""
    if not isinstance(state, dict) or not _count(observed_count):
        return "MEDIUM"
    full = state.get("full") is True or state.get("label") == "full"
    low = (state.get("count") or {}).get("min")
    if full and _count(low) and low > 0:
        near_empty = math.ceil(low / 2.0)
        if observed_count < near_empty:
            return "MAJOR"
    return "MEDIUM"


def choir_mismatch_level(state, observed_count):
    """3M.4: MEDIUM; MAJOR when the choir is under half or over double."""
    if not isinstance(state, dict) or not _count(observed_count):
        return "MEDIUM"
    choir = state.get("choir") or {}
    stated = choir.get("count")
    if not _count(stated) or stated == 0:
        return "MEDIUM"
    if observed_count < stated / 2.0 or observed_count > stated * 2.0:
        return "MAJOR"
    return "MEDIUM"


def continuity_questions():
    """The world-continuity check questions, as data the clip checks read.

    Loaded once from ``continuity_questions.json``; a copy is returned so a
    caller cannot edit the module's data in place.
    """
    global _QUESTIONS
    if _QUESTIONS is None:
        with open(_QUESTIONS_FILE, "r", encoding="utf-8") as handle:
            _QUESTIONS = json.load(handle)
    return json.loads(json.dumps(_QUESTIONS))


# ---------------------------------------------------------------------------
# The Bible Guard, world side (3C.10, N-122). Part 1 is the pre-spend check on
# every picture and clip job; part 3's create-and-lock runs here so a place is
# never invented inside a shot. Cast codes and the vision check belong to the
# cast units and the clip checks.
# ---------------------------------------------------------------------------

def place_slug(name):
    """The location id an undeclared place is created under: ``loc_<slug>``."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")
    if not slug:
        raise WorldBibleError(["a place needs a name before it can be created"])
    return "loc_" + slug


def place_index(bible):
    """{location_id: place} for every entry in the Bible."""
    if not isinstance(bible, dict):
        return {}
    return {
        place["location_id"]: place
        for place in bible.get("places") or []
        if isinstance(place, dict) and _nonempty(place.get("location_id"))
    }


def locked_place(bible, location_id):
    """The locked place with this id, or None. An unlocked entry is not usable."""
    place = place_index(bible).get(location_id)
    if isinstance(place, dict) and place.get("locked") is True:
        return place
    return None


def prompt_names_place(prompt):
    """True when the prompt describes a room in prose."""
    if not _nonempty(prompt):
        return False
    words = "|".join(re.escape(word) for word in PLACE_WORDS)
    return re.search(r"(?<![a-z0-9])(%s)(?![a-z0-9])" % words,
                     prompt.lower()) is not None


def _refusal(code, message, **extra):
    refusal = {"code": code, "message": message}
    refusal.update(extra)
    return refusal


def _time_variant(place, time_of_day):
    try:
        wanted = TIME_OF_DAY_ORDER[time_of_day_index(time_of_day)]
    except WorldBibleError:
        wanted = _norm_time(time_of_day)
    for variant in place.get("time_of_day_variants") or []:
        if not isinstance(variant, dict):
            continue
        try:
            key = TIME_OF_DAY_ORDER[time_of_day_index(variant.get("time_of_day"))]
        except WorldBibleError:
            key = _norm_time(variant.get("time_of_day"))
        if key == wanted:
            return variant
    return None


def spend_job_refusals(bible, job):
    """3C.10 part 1 for one picture or clip job; empty list means it may spend.

    ``job`` carries ``location_id``, ``crowd_state_id``, ``time_of_day``,
    ``reference_ids`` (the pictures attached to the request) and ``prompt``.
    The world side names three refusals:
    ``LOCATION_NOT_IN_WORLD_BIBLE``, ``WORLD_REFERENCE_MISSING`` and
    ``UNNAMED_PLACE_IN_PROMPT``.

    The same two questions the plan adds for a person --
    ``CAST_NOT_IN_BIBLE`` and ``CAST_REFERENCE_MISSING`` -- and
    ``UNNAMED_PERSON_IN_PROMPT`` are the cast units' half of the same guard.
    """
    refusals = []
    if not isinstance(job, dict):
        return [_refusal(CODE_LOCATION_NOT_IN_BIBLE, "job must be an object")]
    loc_id = job.get("location_id")
    place = locked_place(bible, loc_id) if _nonempty(loc_id) else None
    if place is None:
        if _nonempty(loc_id):
            refusals.append(_refusal(
                CODE_LOCATION_NOT_IN_BIBLE,
                "place %r has no locked World Bible entry; the place is created and "
                "locked before it is used" % loc_id, location_id=loc_id))
        else:
            refusals.append(_refusal(
                CODE_LOCATION_NOT_IN_BIBLE,
                "the job names no place; every picture and clip job names its place",
                location_id=None))
            if prompt_names_place(job.get("prompt")):
                refusals.append(_refusal(
                    CODE_UNNAMED_PLACE_IN_PROMPT,
                    "the job's text describes a room in words with no id behind them; "
                    "name the place id", location_id=None))
        return refusals

    state_id = job.get("crowd_state_id")
    state = state_for(place, state_id) if _nonempty(state_id) else None
    if state is None:
        refusals.append(_refusal(
            CODE_WORLD_REFERENCE_MISSING,
            "place %r has no crowd state %r in this beat; add and lock the state"
            % (loc_id, state_id), location_id=loc_id, crowd_state_id=state_id))

    attached = job.get("reference_ids")
    attached = set(attached) if isinstance(attached, (list, tuple, set)) else set()
    required = []
    if isinstance(state, dict):
        required.append((state.get("reference_picture_id"), "crowd state %r" % state_id))
    time_of_day = job.get("time_of_day")
    variant = _time_variant(place, time_of_day) if _nonempty(time_of_day) else None
    if variant is None:
        refusals.append(_refusal(
            CODE_WORLD_REFERENCE_MISSING,
            "place %r has no time-of-day variant for %r; the beat's light has no "
            "reference" % (loc_id, time_of_day),
            location_id=loc_id, time_of_day=time_of_day))
    else:
        required.append((variant.get("reference_picture_id"),
                         "time of day %r" % time_of_day))
    for picture_id, label in required:
        if not _nonempty(picture_id):
            refusals.append(_refusal(
                CODE_WORLD_REFERENCE_MISSING,
                "place %r has no reference picture for its %s" % (loc_id, label),
                location_id=loc_id))
        elif picture_id not in attached:
            refusals.append(_refusal(
                CODE_WORLD_REFERENCE_MISSING,
                "the %s reference %r of place %r is not attached to the job"
                % (label, picture_id, loc_id), location_id=loc_id,
                reference_picture_id=picture_id))
    return refusals


def assert_spend_job(bible, job):
    """Raise ``WorldBibleError`` when the job's place side is refused."""
    refusals = spend_job_refusals(bible, job)
    if refusals:
        raise WorldBibleError([refusal["message"] for refusal in refusals])


def _bumped(bible):
    record = copy.deepcopy(bible)
    lock = dict(record.get("lock") or {})
    lock["version"] = int(lock.get("version", 1)) + 1
    record["lock"] = lock
    return record


def create_place(bible, declaration):
    """Create and lock a place from its declaration; never invent it in a shot.

    The declaration is a complete place entry. It is validated before it is
    added, its ``locked`` flag is set true, and the lock version is raised so a
    headline promise is traceable to the entry it now covers.
    """
    if not isinstance(declaration, dict):
        raise WorldBibleError(["a place declaration must be an object"])
    places = place_index(bible)
    entry = copy.deepcopy(declaration)
    if not _nonempty(entry.get("location_id")):
        if not _nonempty(entry.get("name")):
            raise WorldBibleError(["a place declaration needs a location_id or a name"])
        entry["location_id"] = place_slug(entry["name"])
    loc_id = entry["location_id"]
    if loc_id in places:
        raise WorldBibleError([
            "%s: place %r already exists; complete_place() fills an entry, it does not "
            "duplicate one" % (CODE_BUILDOUT_INCOMPLETE, loc_id)])
    entry["locked"] = True
    errors = validate_place(entry, "places[new]")
    if errors:
        raise WorldBibleError(errors)
    record = _bumped(bible)
    record.setdefault("places", []).append(entry)
    return record


def create_place_stub(bible, name):
    """Create an UNLOCKED place entry from a beat's place name.

    A stub is a marker, not a usable place: ``spend_job_refusals`` refuses it
    as ``LOCATION_NOT_IN_WORLD_BIBLE`` until ``complete_place`` fills and locks
    it. This is the automatic fix when a beat names a place nobody built.
    """
    loc_id = place_slug(name)
    if loc_id in place_index(bible):
        return copy.deepcopy(bible), loc_id
    record = _bumped(bible)
    record.setdefault("places", []).append(
        {"location_id": loc_id, "name": str(name).strip(), "locked": False})
    return record, loc_id


def complete_place(bible, location_id, declaration):
    """Fill a stub from its declaration and lock it; raises on any defect."""
    places = place_index(bible)
    current = places.get(location_id)
    if not isinstance(current, dict):
        raise WorldBibleError([
            "%s: no place entry %r to complete; create it first"
            % (CODE_LOCATION_NOT_IN_BIBLE, location_id)])
    entry = copy.deepcopy(current)
    if isinstance(declaration, dict):
        entry.update(copy.deepcopy(declaration))
    entry["location_id"] = location_id
    entry["locked"] = True
    errors = validate_place(entry, "places[%s]" % location_id)
    if errors:
        raise WorldBibleError(errors)
    record = _bumped(bible)
    for index, place in enumerate(record["places"]):
        if isinstance(place, dict) and place.get("location_id") == location_id:
            record["places"][index] = entry
            break
    return record


def attach_variant(bible, location_id, *, picture_id, crowd_state_id=None,
                   time_of_day=None, derived_from=None):
    """Attach a reference picture to a crowd state or a time-of-day variant.

    Used by the fix path when a locked place lacks the variant a beat uses: if
    the variant does not exist it is made from the base wide (``derived_from``
    records that link). The lock version is raised.
    """
    if not _nonempty(picture_id):
        raise WorldBibleError(["attach_variant needs a picture_id"])
    if bool(crowd_state_id) == bool(time_of_day):
        raise WorldBibleError([
            "attach_variant takes exactly one of crowd_state_id or time_of_day"])
    record = _bumped(bible)
    place = place_index(record).get(location_id)
    if not isinstance(place, dict):
        raise WorldBibleError([
            "%s: no place entry %r to attach a reference to"
            % (CODE_LOCATION_NOT_IN_BIBLE, location_id)])
    if crowd_state_id:
        state = state_for(place, crowd_state_id)
        if state is None:
            raise WorldBibleError([
                "%s: place %r has no crowd state %r; create the state first"
                % (CODE_BUILDOUT_INCOMPLETE, location_id, crowd_state_id)])
        state["reference_picture_id"] = picture_id
        if derived_from:
            state["derived_from"] = derived_from
        return record
    variant = _time_variant(place, time_of_day)
    if variant is None:
        variant = {"time_of_day": time_of_day}
        place.setdefault("time_of_day_variants", []).append(variant)
    variant["reference_picture_id"] = picture_id
    if derived_from:
        variant["derived_from"] = derived_from
    return record


# ---------------------------------------------------------------------------
# Cast Discovery's place half and the completeness gate (3C.11, N-123). No
# storyboard picture is drawn until the gate passes; a missing place is
# created by the run rather than sent to a person.
# ---------------------------------------------------------------------------

def places_named_by_beats(beats):
    """{location_id or None: [beat_id, ...]} for every place the beats name.

    A beat's place is named by id (``location_id``) or in prose
    (``place_name``). Every named place must have an entry; a prose name with
    no id is the same failure, caught before anything is drawn.
    """
    named = {}
    for index, beat in enumerate(beats or []):
        if not isinstance(beat, dict):
            continue
        beat_id = beat.get("beat_id") or beat.get("scene_id") or "beat_%d" % index
        loc_id = beat.get("location_id")
        if _nonempty(loc_id):
            named.setdefault(loc_id, []).append(beat_id)
        elif _nonempty(beat.get("place_name")):
            named.setdefault(None, []).append(beat_id)
    return named


def buildout_defects(bible, beats):
    """3C.11 step 5's place checks; empty list means the gate passes.

    Every place the beats name has a locked entry with its map, size, set
    pieces, establishing pictures and a variant for every time and crowd state
    the beats use. Each defect carries its code
    (``WORLD_BUILDOUT_INCOMPLETE`` or ``LOCATION_NOT_IN_WORLD_BIBLE``) and the
    beats it blocks, which is what the create-and-lock step reads.
    """
    defects = []
    index = place_index(bible)
    by_place = {}
    prose = []
    for beat_number, beat in enumerate(beats or []):
        if not isinstance(beat, dict):
            continue
        beat_id = beat.get("beat_id") or beat.get("scene_id") or "beat_%d" % beat_number
        loc_id = beat.get("location_id")
        if _nonempty(loc_id):
            by_place.setdefault(loc_id, []).append(beat)
        elif _nonempty(beat.get("place_name")):
            prose.append((beat_id, beat["place_name"]))
    for beat_id, name in prose:
        defects.append({
            "code": CODE_LOCATION_NOT_IN_BIBLE,
            "location_id": None,
            "beat_ids": [beat_id],
            "place_name": name,
            "message": "beat %r names place %r in prose with no place id; the place is "
                       "created from the beats and locked before it is used"
                       % (beat_id, name),
        })
    for loc_id, beats_here in sorted(by_place.items()):
        beat_ids = [b.get("beat_id") or b.get("scene_id") for b in beats_here]
        place = index.get(loc_id)
        if place is None:
            defects.append({
                "code": CODE_LOCATION_NOT_IN_BIBLE,
                "location_id": loc_id,
                "beat_ids": beat_ids,
                "message": "place %r is named by the beats and has no World Bible entry"
                           % loc_id,
            })
            continue
        if place.get("locked") is not True:
            defects.append({
                "code": CODE_BUILDOUT_INCOMPLETE,
                "location_id": loc_id,
                "beat_ids": beat_ids,
                "message": "place %r is stubbed but not locked; no storyboard picture is "
                           "drawn until its entry is built out and locked" % loc_id,
            })
            continue
        per_place = validate_place(place, "places[%s]" % loc_id)
        if per_place:
            defects.append({
                "code": CODE_BUILDOUT_INCOMPLETE,
                "location_id": loc_id,
                "beat_ids": beat_ids,
                "message": "; ".join(per_place),
            })
        for beat in beats_here:
            beat_id = beat.get("beat_id") or beat.get("scene_id")
            state_id = beat.get("crowd_state_id")
            if not _nonempty(state_id) or state_for(place, state_id) is None:
                defects.append({
                    "code": CODE_BUILDOUT_INCOMPLETE,
                    "location_id": loc_id,
                    "beat_ids": [beat_id],
                    "message": "beat %r uses crowd state %r in place %r and the state has "
                               "no variant" % (beat_id, state_id, loc_id),
                })
            label = beat.get("time_of_day")
            if not _nonempty(label) or _time_variant(place, label) is None:
                defects.append({
                    "code": CODE_BUILDOUT_INCOMPLETE,
                    "location_id": loc_id,
                    "beat_ids": [beat_id],
                    "message": "beat %r plays at %r in place %r and the entry has no "
                               "time-of-day variant for it" % (beat_id, label, loc_id),
                })
    return defects


def completeness_gate(bible, beats):
    """The gate verdict: ``{"passed": bool, "defects": [...], "fixes": [...]}``.

    ``fixes`` is the automatic fix list (3C.10 part 3): each prose place is
    created as a stub and completed from its beats' own fields; each missing
    crowd state or time-of-day variant is named for its picture. Nothing here
    asks a person anything.
    """
    defects = buildout_defects(bible, beats)
    fixes = []
    for defect in defects:
        if defect["code"] == CODE_LOCATION_NOT_IN_BIBLE and defect.get("place_name"):
            fixes.append({
                "action": "create_place",
                "name": defect["place_name"],
                "beat_ids": defect["beat_ids"],
            })
        elif defect["code"] == CODE_LOCATION_NOT_IN_BIBLE:
            fixes.append({
                "action": "complete_place",
                "location_id": defect["location_id"],
                "beat_ids": defect["beat_ids"],
            })
        else:
            fixes.append({
                "action": "build_out",
                "location_id": defect["location_id"],
                "beat_ids": defect["beat_ids"],
                "message": defect["message"],
            })
    return {"passed": not defects, "defects": defects, "fixes": fixes}

