#!/usr/bin/env python3
"""cast_discovery.py: everyone and every place found before the storyboard (N-123, section 3C.11). Stdlib only.

After the Story Beats pass their gate, and before any storyboard picture:
one list of everyone a viewer would see, beat by beat ("Who would a viewer
see here, even for a second?"), and a second list made cold on a different
model. A person on one list and not the other is settled before the gate. Every
person gets a tier and a profile; every place the beats name is built out in
the World Bible. The completeness gate refuses a storyboard until the lists
agree, the profiles agree with the beats and every place is built out.

Codes: CAST_DISCOVERY_INCOMPLETE, CAST_NOT_IN_BIBLE (from cast_lock),
WORLD_BUILDOUT_INCOMPLETE, LOCATION_NOT_IN_WORLD_BIBLE, PROFILE_OFF_BEAT,
RELATION_CONFLICT.

Stdlib only, no IO, no provider call.
"""
from __future__ import annotations

try:
    from character_bible.cast_lock import CAST_NOT_IN_BIBLE, cast_ids
except ImportError:                                   # imported beside the module
    from cast_lock import CAST_NOT_IN_BIBLE, cast_ids

SCHEMA_VERSION = "blackceo.cast-discovery/v1"

CAST_DISCOVERY_INCOMPLETE = "CAST_DISCOVERY_INCOMPLETE"
WORLD_BUILDOUT_INCOMPLETE = "WORLD_BUILDOUT_INCOMPLETE"
LOCATION_NOT_IN_WORLD_BIBLE = "LOCATION_NOT_IN_WORLD_BIBLE"
PROFILE_OFF_BEAT = "PROFILE_OFF_BEAT"
RELATION_CONFLICT = "RELATION_CONFLICT"


def _defect(code, detail, **extra):
    out = {"code": code, "detail": detail}
    out.update(extra)
    return out


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _packet(findings):
    return {"schema_version": SCHEMA_VERSION,
            "outcome": "pass" if not findings else "fail",
            "findings": findings,
            "codes": sorted({f["code"] for f in findings})}


def _beat_people(beat):
    out = []
    for key in ("cast_ids", "characters", "who_would_a_viewer_see", "who"):
        raw = beat.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            cid = item.get("character_id") if isinstance(item, dict) else item
            if _text(cid):
                out.append(cid)
    return out


def discover_lists(beats):
    """The discovery list per beat, and the beats that say nobody else is seen."""
    listed, empty = {}, []
    for beat in beats or []:
        if not isinstance(beat, dict):
            continue
        beat_id = beat.get("beat_id") or beat.get("beat_number")
        people = _beat_people(beat)
        if people:
            listed[beat_id] = people
        elif beat.get("nobody_else_seen") is True:
            empty.append(beat_id)
    return {"listed": listed, "nobody_else_seen": empty}


def compare_discovery(primary, cold):
    """Differences between the discovery list and the cold reader's list.

    Both are {beat_id: [character_id]}. Returns [{"beat_id", "only_in"}] with
    the ids each list alone names, so a difference is settled, never ignored.
    """
    out = []
    for beat_id in sorted(set(primary) | set(cold), key=str):
        a = set(primary.get(beat_id) or [])
        b = set(cold.get(beat_id) or [])
        for cid in sorted(a - b):
            out.append({"beat_id": beat_id, "character_id": cid, "only_in": "primary"})
        for cid in sorted(b - a):
            out.append({"beat_id": beat_id, "character_id": cid, "only_in": "cold"})
    return out


def check_discovery(beats, manifest, cold=None):
    """Everyone is found: each beat lists who is seen or says nobody else is;
    every person listed has a cast entry; the two discovery lists agree."""
    findings = []
    known = set(cast_ids(manifest))
    lists = discover_lists(beats)
    for beat in beats or []:
        if not isinstance(beat, dict):
            continue
        beat_id = beat.get("beat_id") or beat.get("beat_number")
        if beat_id not in lists["listed"] and beat_id not in lists["nobody_else_seen"]:
            findings.append(_defect(
                CAST_DISCOVERY_INCOMPLETE,
                "beat %r neither lists who is seen nor says nobody else is"
                % (beat_id,), beat_id=beat_id))
    for beat_id, people in lists["listed"].items():
        for cid in people:
            if cid not in known:
                findings.append(_defect(CAST_NOT_IN_BIBLE,
                                        "beat %r names a person with no cast entry"
                                        % (beat_id,), beat_id=beat_id,
                                        character_id=cid))
    if isinstance(cold, dict):
        for row in compare_discovery(lists["listed"], cold):
            findings.append(_defect(
                CAST_DISCOVERY_INCOMPLETE,
                "cold reader differs on beat %r: %s only in the %s list"
                % (row["beat_id"], row["character_id"], row["only_in"]),
                beat_id=row["beat_id"], character_id=row["character_id"]))
    return _packet(findings)


def _locations(world):
    if not isinstance(world, dict):
        return {}
    out = {}
    for loc in world.get("locations") or []:
        if isinstance(loc, dict) and _text(loc.get("location_id")):
            out[loc["location_id"]] = loc
    return out


def _beat_place(beat):
    for key in ("location_id", "place", "where"):
        value = beat.get(key)
        if _text(value):
            return value
    return None


def check_world_buildout(beats, world):
    """Every place the beats name is built out: map, size, set pieces, pictures."""
    locations = _locations(world)
    findings = []
    seen = set()
    for beat in beats or []:
        if not isinstance(beat, dict):
            continue
        place = _beat_place(beat)
        if not place or place in seen:
            continue
        seen.add(place)
        loc = locations.get(place)
        if loc is None:
            findings.append(_defect(LOCATION_NOT_IN_WORLD_BIBLE,
                                    "beat names %r with no World Bible entry" % place,
                                    location_id=place))
            continue
        if not isinstance(loc.get("layout_map"), dict) and \
                not isinstance(loc.get("layout_map"), str):
            findings.append(_defect(WORLD_BUILDOUT_INCOMPLETE,
                                    "%r has no layout map" % place, location_id=place))
        if loc.get("size") in (None, "") and not loc.get("size_numbers"):
            findings.append(_defect(WORLD_BUILDOUT_INCOMPLETE,
                                    "%r has no size in numbers" % place,
                                    location_id=place))
        if not loc.get("set_pieces"):
            findings.append(_defect(WORLD_BUILDOUT_INCOMPLETE,
                                    "%r lists no set pieces" % place,
                                    location_id=place))
        if not loc.get("establishing_pictures") and not loc.get("reference_pictures"):
            findings.append(_defect(WORLD_BUILDOUT_INCOMPLETE,
                                    "%r has no establishing picture" % place,
                                    location_id=place))
    return _packet(findings)


def check_profiles(profiles, beats):
    """Each profile agrees with the beats; relations are two-sided and ages fit.

    profiles: {character_id: {"emotion_by_beat": {beat_id: emotion},
    "relations": [{"character_id", "relation", "age"}], "age": int}}
    """
    findings = []
    beat_emotion = {}
    for beat in beats or []:
        if not isinstance(beat, dict):
            continue
        beat_id = beat.get("beat_id") or beat.get("beat_number")
        emotion = beat.get("emotion") or beat.get("emotion_after")
        if _text(emotion):
            beat_emotion[beat_id] = _text(emotion).lower()
    profiles = profiles if isinstance(profiles, dict) else {}
    for cid, profile in sorted(profiles.items(), key=lambda kv: str(kv[0])):
        if not isinstance(profile, dict):
            continue
        for beat_id, expected in (profile.get("emotion_by_beat") or {}).items():
            if beat_id in beat_emotion and _text(expected).lower() != beat_emotion[beat_id]:
                findings.append(_defect(
                    PROFILE_OFF_BEAT,
                    "%s is %r at beat %r; the beat says %r"
                    % (cid, expected, beat_id, beat_emotion[beat_id]),
                    character_id=cid, beat_id=beat_id))
        for edge in profile.get("relations") or []:
            if not isinstance(edge, dict):
                continue
            target = edge.get("character_id")
            if not _text(target):
                findings.append(_defect(RELATION_CONFLICT,
                                        "%s has a relation with no character_id" % cid,
                                        character_id=cid))
                continue
            other = profiles.get(target)
            if not isinstance(other, dict):
                findings.append(_defect(RELATION_CONFLICT,
                                        "%s relates to %r, who is not on the cast"
                                        % (cid, target), character_id=cid))
                continue
            back = [e for e in (other.get("relations") or [])
                    if isinstance(e, dict) and e.get("character_id") == cid]
            if not back:
                findings.append(_defect(RELATION_CONFLICT,
                                        "relation %s -> %s is one-sided"
                                        % (cid, target), character_id=cid))
            mine, theirs = profile.get("age"), other.get("age")
            if isinstance(mine, int) and isinstance(theirs, int):
                relation = str(edge.get("relation") or "").lower()
                if relation in ("mother", "father", "parent") and not mine > theirs:
                    findings.append(_defect(
                        RELATION_CONFLICT,
                        "%s is %r's %s but is aged %r against %r"
                        % (cid, target, relation, mine, theirs),
                        character_id=cid))
    return _packet(findings)


def completeness_gate(beats, manifest, world, profiles, cold=None):
    """The gate that holds every storyboard picture until it passes."""
    findings = []
    findings.extend(check_discovery(beats, manifest, cold)["findings"])
    findings.extend(check_world_buildout(beats, world)["findings"])
    findings.extend(check_profiles(profiles, beats)["findings"])
    return _packet(findings)


__all__ = [
    "SCHEMA_VERSION", "CAST_DISCOVERY_INCOMPLETE", "WORLD_BUILDOUT_INCOMPLETE",
    "LOCATION_NOT_IN_WORLD_BIBLE", "PROFILE_OFF_BEAT", "RELATION_CONFLICT",
    "discover_lists", "compare_discovery", "check_discovery",
    "check_world_buildout", "check_profiles", "completeness_gate",
]
