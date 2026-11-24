#!/usr/bin/env python3
"""The Cast Discovery completeness gate (N-123, U-SCRIPT half, section 3C.11).

Builds on ``beat_sheet.discovery`` (the who-is-seen field and the two-list
compare) and adds what the gate still needs on the beats side: the join that
removes repeats, the tier rule, the profile checks (two-sided family relations,
ages that fit them, no two people sharing a name, role or look), and one
``completeness_gate`` that must pass before any storyboard picture.

The Character Bible, the World Bible and the place build-out are U-STORY and
U-WORLD; ``world_defects`` is passed in from U-WORLD so the gate reports one
verdict. A missing person or place is created and locked by the run before a
shot uses them; this module finds and refuses, it never invents inside a shot.

Pure data checks. Stdlib only, no IO, no model call, no mutation.
"""
from __future__ import annotations

from .beat_sheet import _defect, _norm
from .discovery import NOBODY_ELSE, compare_lists, seen_field_defects

__all__ = [
    "NOBODY_ELSE",
    "TIERS",
    "check_arcs_against_beats",
    "completeness_gate",
    "join_discovery",
    "people_in_bible_defects",
    "tier_of",
    "tier_picture_requirements",
    "tier_picture_defects",
    "validate_profiles",
    "world_buildout_defects",
    "selftest",
]

TIERS = ("A", "B", "C")

_RECIPROCAL = {
    "mother": {"child", "son", "daughter"},
    "father": {"child", "son", "daughter"},
    "parent": {"child", "son", "daughter"},
    "child": {"mother", "father", "parent"},
    "son": {"mother", "father", "parent"},
    "daughter": {"mother", "father", "parent"},
}


def _people(items):
    out = []
    for item in items or []:
        if isinstance(item, str) and item.strip():
            out.append({"id": item.strip(), "name": item.strip()})
        elif isinstance(item, dict) and (item.get("id") or item.get("name")):
            out.append(dict(item))
    return out


def join_discovery(lists):
    """Join the lists and remove repeats: the same janitor in two beats is one."""
    merged = {}
    for people in lists or []:
        for person in _people(people):
            key = _norm(person.get("id") or person.get("name"))
            if key not in merged:
                merged[key] = dict(person)
            else:
                merged[key]["beats"] = sorted(
                    set(merged[key].get("beats") or []) | set(person.get("beats") or []))
    return list(merged.values())


def tier_of(person):
    """A main and supporting (lip-syncs or 3+ shots), B a clear face, C crowd."""
    if person.get("lipsync") or person.get("lip_syncs"):
        return "A"
    shots = person.get("shot_count", len(person.get("beats") or []))
    if isinstance(shots, int) and shots >= 3:
        return "A"
    if person.get("face_seen") or person.get("beats"):
        return "B"
    return "C"


def tier_picture_requirements(tier):
    """The locked pictures a tier needs before its shots (section 3C.11)."""
    return {
        "A": {"master": 1, "views": 3, "per_outfit": 1,
              "expression_sheets": "one per emotion carried"},
        "B": {"face": 1, "full_figure": 1, "extra_views": "per other side seen"},
        "C": {"crowd_reference": 1},
    }.get(tier, {})


def _beat_rows(beats):
    rows = beats.get("beats") if isinstance(beats, dict) else beats
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

def _beat_number(beat, index):
    return beat.get("beat_number", beat.get("beat_id", index))

def _seen_people(beat):
    """Everyone a viewer would see in this beat: cast ids and who-else-seen.

    Reads both spellings ``discovery._seen`` and ``_util.beat_cast`` accept, so
    the bible check agrees with the discovery check that ran before it.
    """
    names = set()
    for key in ("cast_ids", "who_else_seen"):
        value = beat.get(key)
        if isinstance(value, list):
            names.update(v for v in value if isinstance(v, str) and v.strip())
    who = beat.get("who") if isinstance(beat.get("who"), dict) else {}
    for key in ("on_screen", "characters", "singing", "listening"):
        value = who.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    names.add(item)
                elif isinstance(item, dict) and item.get("id"):
                    names.add(item["id"])
    for key in ("else_seen",):
        value = who.get(key)
        if isinstance(value, str) and value.strip():
            names.add(value)
        elif isinstance(value, list):
            names.update(v for v in value if isinstance(v, str) and v.strip())
    value = beat.get("who_else_seen")
    if isinstance(value, str) and value.strip():
        names.add(value)
    return {name for name in names if _norm(name) != _norm(NOBODY_ELSE)}

def people_in_bible_defects(beats, profiles=None, bible_ids=None):
    """CAST_NOT_IN_BIBLE: every person a beat shows has a bible entry.

    ``bible_ids`` is the Character Bible's own id list; ``profiles`` is the
    profile list Cast Discovery produced. When neither is supplied the check
    cannot run and fails closed (3J item 15) with an empty list, never a pass.
    """
    listed = {_norm(i) for i in (bible_ids or []) if isinstance(i, str)}
    for person in profiles or []:
        if isinstance(person, dict):
            listed.add(_norm(person.get("id") or person.get("name")))
    if not listed:
        return [_defect("CAST_NOT_IN_BIBLE", "/cast-bible",
                        "no Character Bible was supplied, so no person on the "
                        "beats can be shown to have an entry")]
    defects = []
    for index, beat in enumerate(_beat_rows(beats)):
        number = _beat_number(beat, index)
        for name in sorted(_seen_people(beat)):
            if _norm(name) not in listed:
                defects.append(_defect(
                    "CAST_NOT_IN_BIBLE", "/beats/%s/who" % number,
                    "%r is seen in beat %r and has no locked entry"
                    % (name, number)))
    return defects

def _places(beats):
    out = []
    for index, beat in enumerate(_beat_rows(beats)):
        where = beat.get("where") if isinstance(beat.get("where"), dict) else beat
        place = where.get("location_id") or beat.get("place_id")
        if isinstance(place, str) and place.strip():
            out.append((_beat_number(beat, index), place))
    return out

def world_buildout_defects(beats, world_bible=None):
    """WORLD_BUILDOUT_INCOMPLETE and LOCATION_NOT_IN_WORLD_BIBLE (3C.11 step 4).

    ``world_bible`` is U-WORLD's record: ``{place_id: {"layout": ...,
    "set_pieces": [...], "establishing": [...], "states": [...],
    "times": [...]}}``. A place the beats name with no entry is
    ``LOCATION_NOT_IN_WORLD_BIBLE``; an entry missing any part the beats use is
    ``WORLD_BUILDOUT_INCOMPLETE``. No bible at all fails closed.
    """
    places = _places(beats)
    if not places:
        return []
    if not isinstance(world_bible, dict) or not world_bible:
        return [_defect("LOCATION_NOT_IN_WORLD_BIBLE", "/world-bible",
                        "no World Bible was supplied, so no place on the beats "
                        "can be shown to exist")]
    defects = []
    reported = set()
    for number, place in places:
        entry = world_bible.get(place)
        if not isinstance(entry, dict):
            if place not in reported:
                reported.add(place)
                defects.append(_defect(
                    "LOCATION_NOT_IN_WORLD_BIBLE", "/world-bible/%s" % place,
                    "beat %r is in %r, which has no World Bible entry"
                    % (number, place)))
            continue
        for part in ("layout", "set_pieces", "establishing"):
            if not entry.get(part):
                defects.append(_defect(
                    "WORLD_BUILDOUT_INCOMPLETE", "/world-bible/%s/%s" % (place, part),
                    "%r has no %s" % (place, part)))
    return defects

def tier_picture_defects(tier, pictures):
    """CAST_NOT_IN_BIBLE: the locked pictures a tier calls for are present.

    Section 3C.11's gate row sends a missing profile *or* a missing tier picture
    to the same code; ``CAST_REFERENCE_MISSING`` belongs to the dispatcher,
    which refuses a job whose references are not attached.
    """
    # A tier C person is only ever a crowd; their crowd reference is a World
    # Bible picture (3M.4) checked by ``world_buildout_defects``, not a
    # per-person character picture.
    if tier == "C":
        return []
    need = tier_picture_requirements(tier)
    if not isinstance(pictures, dict):
        pictures = {}
    have = {str(name) for name in pictures if pictures.get(name)}
    missing = sorted(set(need) - have)
    if not missing:
        return []
    return [_defect("CAST_NOT_IN_BIBLE", "/tier-%s/pictures" % tier,
                    "tier %s is missing: %s" % (tier, ", ".join(missing)))]

def _two_sided_relations(profiles):
    by_id = {_norm(p.get("id") or p.get("name")): p for p in profiles}
    defects = []
    for key, person in by_id.items():
        for relation in person.get("relations") or []:
            if not isinstance(relation, dict):
                continue
            other = _norm(relation.get("of") or relation.get("id"))
            kind = _norm(relation.get("kind"))
            target = by_id.get(other)
            if target is None:
                defects.append(_defect(
                    "RELATION_CONFLICT", "relations",
                    "%r names %r, who is not on the cast list"
                    % (person.get("name", key), other)))
                continue
            wanted = _RECIPROCAL.get(kind, {kind})
            reciprocal = any(
                _norm(r.get("kind")) in wanted
                and _norm(r.get("of") or r.get("id")) == key
                for r in target.get("relations") or [] if isinstance(r, dict))
            if not reciprocal:
                defects.append(_defect(
                    "RELATION_CONFLICT", "relations",
                    "%r's %r is not stated on %r's own profile"
                    % (person.get("name", key), kind, target.get("name", other))))
    return defects


def validate_profiles(profiles):
    """Two-sided relations, ages that fit them, and no two people alike."""
    defects = []
    if not isinstance(profiles, list):
        return [_defect("PROFILE_OFF_BEAT", "profiles", "profiles must be a list")]
    defects.extend(_two_sided_relations(profiles))
    seen_name, seen_role, seen_look = {}, {}, {}
    by_id = {_norm(p.get("id") or p.get("name")): p for p in profiles
             if isinstance(p, dict)}
    for person in profiles:
        if not isinstance(person, dict):
            defects.append(_defect("PROFILE_OFF_BEAT", "profiles",
                                   "one profile is not an object"))
            continue
        for field, store in (("name", seen_name), ("role", seen_role), ("look", seen_look)):
            value = _norm(person.get(field))
            if not value:
                continue
            if value in store:
                defects.append(_defect("CAST_LOOKALIKE", field,
                                       "%r and %r share a %s"
                                       % (store[value], person.get("name"), field)))
            else:
                store[value] = person.get("name")
        age = person.get("age")
        for relation in person.get("relations") or []:
            if not isinstance(relation, dict):
                continue
            other = by_id.get(_norm(relation.get("of") or relation.get("id")))
            if other and isinstance(age, int) and isinstance(other.get("age"), int):
                kind = _norm(relation.get("kind"))
                if kind in ("mother", "father", "parent") and age <= other.get("age"):
                    defects.append(_defect(
                        "RELATION_CONFLICT", "age",
                        "%r is a %s of %r but is not older"
                        % (person.get("name"), kind, other.get("name"))))
                if kind in ("child", "son", "daughter") and age >= other.get("age"):
                    defects.append(_defect(
                        "RELATION_CONFLICT", "age",
                        "%r is a %s of %r but is not younger"
                        % (person.get("name"), kind, other.get("name"))))
    return defects


def _emotion(value):
    if isinstance(value, dict):
        return (_norm(value.get("emotion")),
                value.get("intensity") if value.get("intensity") in (1, 2, 3) else None)
    return (_norm(value), None)


def check_arcs_against_beats(profiles, beats):
    """PROFILE_OFF_BEAT: a profile's emotional arc must agree with the beats.

    Each profile may carry ``emotional_arc`` as ``{beat_number: emotion}`` (or
    ``{beat_number: {emotion, intensity}}``). Every entry must be a beat the
    person is in, and the emotion must be one of the beat's two gateway
    emotions (arc start or arc end). An entry for a beat the person is not in
    is off-beat by definition.
    """
    rows = beats.get("beats") if isinstance(beats, dict) else beats
    by_number = {}
    for i, beat in enumerate(rows or []):
        if not isinstance(beat, dict):
            continue
        number = beat.get("beat_number", beat.get("beat_id", i))
        by_number[str(number)] = beat

    def _in_beat(key, person):
        beat = by_number.get(str(key))
        if beat is None:
            return None
        who = beat.get("who") if isinstance(beat.get("who"), dict) else {}
        cast = {_norm(c) for c in (beat.get("cast_ids") or who.get("on_screen")
                                   or who.get("characters") or []) if c}
        return not cast or _norm(person.get("id") or person.get("name")) in cast

    defects = []
    for person in profiles or []:
        if not isinstance(person, dict):
            continue
        name = person.get("name") or person.get("id")
        for key, value in (person.get("emotional_arc") or {}).items():
            beat = by_number.get(str(key))
            if beat is None:
                defects.append(_defect("PROFILE_OFF_BEAT", "emotional_arc",
                                       "%r's arc names beat %r, which does not exist"
                                       % (name, key)))
                continue
            if _in_beat(key, person) is False:
                defects.append(_defect("PROFILE_OFF_BEAT", "emotional_arc",
                                       "%r's arc names beat %r, where %r is not seen"
                                       % (name, key, name)))
                continue
            emotion, _ = _emotion(value)
            allowed = {_emotion(beat.get("emotion_start"))[0],
                       _emotion(beat.get("emotion_end"))[0]}
            allowed.discard("")
            if allowed and emotion not in allowed:
                defects.append(_defect(
                    "PROFILE_OFF_BEAT", "emotional_arc",
                    "%r is %r at beat %r; the beat runs %s"
                    % (name, emotion, key, " to ".join(sorted(allowed)))))
    return defects


def completeness_gate(beats, section_lists=None, cold_reader=None,
                      profiles=None, world_defects=None, world_bible=None,
                      bible_ids=None):
    """One gate before any storyboard picture: everyone found and profiled.

    The five rows of the section 3C.11 gate, in order:

      everyone is found                  CAST_DISCOVERY_INCOMPLETE
      everyone is in the Character Bible CAST_NOT_IN_BIBLE, CAST_REFERENCE_MISSING
      every place is built out           WORLD_BUILDOUT_INCOMPLETE,
                                         LOCATION_NOT_IN_WORLD_BIBLE
      the profiles agree with the beats  PROFILE_OFF_BEAT, RELATION_CONFLICT

    A part whose input was not supplied cannot run, and a check that cannot run
    fails closed (3J item 15): ``people_in_bible_defects`` and
    ``world_buildout_defects`` report a refusal rather than a pass when the
    bible they need is absent.
    """
    defects = list(seen_field_defects(beats))
    if section_lists is not None and cold_reader is not None:
        defects.extend(compare_lists(section_lists, cold_reader)["defects"])
    if profiles is not None or bible_ids is not None:
        defects.extend(people_in_bible_defects(beats, profiles=profiles,
                                               bible_ids=bible_ids))
    if profiles is not None:
        defects.extend(validate_profiles(profiles))
        defects.extend(check_arcs_against_beats(profiles, beats))
        for person in profiles:
            if isinstance(person, dict) and person.get("pictures") is not None:
                defects.extend(tier_picture_defects(
                    tier_of(person), person.get("pictures")))
    if world_bible is not None:
        defects.extend(world_buildout_defects(beats, world_bible=world_bible))
    defects.extend(world_defects or [])
    return {"gate": "cast_discovery", "passed": not defects,
            "defects": defects, "codes": sorted({d["code"] for d in defects})}


def selftest():
    record = {"beats": [
        {"beat_number": 1, "who": {"else_seen": NOBODY_ELSE}},
        {"beat_number": 2, "who_else_seen": ["cashier"]},
    ]}
    assert completeness_gate(record)["passed"], completeness_gate(record)

    broken = {"beats": [{"beat_number": 1}]}
    assert "CAST_DISCOVERY_INCOMPLETE" in completeness_gate(broken)["codes"]

    disagree = completeness_gate(record, section_lists=["cashier"], cold_reader=["driver"])
    assert not disagree["passed"]

    joined = join_discovery([["janitor"], ["janitor", "cook"]])
    assert len(joined) == 2

    profiles = [
        {"id": "mother", "name": "Ruth", "age": 68, "look": "grey braid",
         "relations": [{"kind": "mother", "of": "lead"}]},
        {"id": "lead", "name": "Ava", "age": 34, "look": "short curls",
         "relations": [{"kind": "daughter", "of": "mother"}]},
    ]
    assert validate_profiles(profiles) == []
    older = [dict(profiles[0], age=30), dict(profiles[1])]
    assert "RELATION_CONFLICT" in {d["code"] for d in validate_profiles(older)}
    twins = [dict(profiles[0]), dict(profiles[1], name="Ruth")]
    assert "CAST_LOOKALIKE" in {d["code"] for d in validate_profiles(twins)}

    assert tier_of({"lipsync": True}) == "A"
    assert tier_of({"beats": [1]}) == "B"
    assert tier_of({}) == "C"

    arc_beats = {"beats": [{"beat_number": 1, "cast_ids": ["lead"],
                            "emotion_start": {"emotion": "worry", "intensity": 2},
                            "emotion_end": {"emotion": "resolve", "intensity": 2}}]}
    off = [{"id": "lead", "name": "Ava", "emotional_arc": {"1": "pain"}}]
    assert "PROFILE_OFF_BEAT" in {d["code"] for d in
                                  check_arcs_against_beats(off, arc_beats)}
    on = [{"id": "lead", "name": "Ava", "emotional_arc": {"1": "resolve"}}]
    assert check_arcs_against_beats(on, arc_beats) == []

    # N-123: every person a beat shows has a bible entry (CAST_NOT_IN_BIBLE),
    # and a gate given no bible at all fails closed rather than passing.
    assert people_in_bible_defects(record, profiles=[{"id": "cashier"}]) == []
    missing_person = people_in_bible_defects(record, profiles=[{"id": "lead"}])
    assert [d["code"] for d in missing_person] == ["CAST_NOT_IN_BIBLE"]
    closed = people_in_bible_defects(record, profiles=[])
    assert closed and closed[0]["code"] == "CAST_NOT_IN_BIBLE"

    # N-123: every place built out; a nameless place and a thin entry refuse.
    home_beats = {"beats": [{"beat_number": 1,
                             "where": {"location_id": "home"}}]}
    full = {"home": {"layout": "plan", "set_pieces": ["stove"],
                     "establishing": ["wide"]}}
    assert world_buildout_defects(home_beats, world_bible=full) == []
    no_place = world_buildout_defects(home_beats, world_bible={})
    assert [d["code"] for d in no_place] == ["LOCATION_NOT_IN_WORLD_BIBLE"]
    thin = {"home": {"layout": "plan"}}
    assert [d["code"] for d in
            world_buildout_defects(home_beats, world_bible=thin)] == \
        ["WORLD_BUILDOUT_INCOMPLETE", "WORLD_BUILDOUT_INCOMPLETE"]

    # N-123: a tier's locked pictures; tier B needs a face, a full figure and
    # one more view for each other side it is seen from.
    tier_b = {"face": "f.png", "full_figure": "b.png", "extra_views": "v.png"}
    assert tier_picture_defects("B", tier_b) == []
    assert [d["code"] for d in
            tier_picture_defects("B", {"face": "f.png"})] == ["CAST_NOT_IN_BIBLE"]
    assert tier_picture_defects("C", {}) == []

    # The whole gate reports the new codes in one verdict.
    verdict = completeness_gate(record, profiles=[{"id": "lead"}],
                                world_bible={})
    assert "CAST_NOT_IN_BIBLE" in verdict["codes"], verdict
    assert "LOCATION_NOT_IN_WORLD_BIBLE" not in verdict["codes"], verdict
    return True


if __name__ == "__main__":  # pragma: no cover
    assert selftest()
    print("cast_completeness selftest OK")
