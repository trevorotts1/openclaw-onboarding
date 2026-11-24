#!/usr/bin/env python3
"""test_cast_discovery_n123.py: Cast Discovery and the completeness gate (N-123).

Done when: a beat that neither lists who is seen nor says nobody else is is
CAST_DISCOVERY_INCOMPLETE; a beat naming a person with no cast entry is
CAST_NOT_IN_BIBLE; a cold-reader difference is named; a place the beats name
with no World Bible entry is LOCATION_NOT_IN_WORLD_BIBLE; an unbuilt place is
WORLD_BUILDOUT_INCOMPLETE; a profile emotion that contradicts its beat is
PROFILE_OFF_BEAT; a one-sided relation or an impossible parent age is
RELATION_CONFLICT; and the gate passes a complete set.

Run: python3 scripts/core/character_bible/test_cast_discovery_n123.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from character_bible import cast_discovery as CD      # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


MANIFEST = {"cast": [{"character_id": "ava"}, {"character_id": "mother"},
                     {"character_id": "ruth"}]}

BEATS = [
    {"beat_id": 1, "cast_ids": ["ava"], "location_id": "kitchen",
     "emotion": "worry"},
    {"beat_id": 2, "cast_ids": ["ava", "mother"], "location_id": "church",
     "emotion": "hope"},
    {"beat_id": 3, "nobody_else_seen": True, "location_id": "street"},
]

WORLD = {"locations": [
    {"location_id": "kitchen", "layout_map": {"fridge": "north"}, "size": "3x4m",
     "set_pieces": ["clock"], "establishing_pictures": ["/w/kitchen.png"]},
    {"location_id": "church", "layout_map": {"door": "west"}, "size": "12x20m",
     "set_pieces": ["cross"], "establishing_pictures": ["/w/church.png"]},
]}

PROFILES = {
    "ava": {"age": 34, "emotion_by_beat": {1: "worry", 2: "hope"},
               "relations": [{"character_id": "mother", "relation": "child"}]},
    "mother": {"age": 67, "emotion_by_beat": {2: "hope"},
               "relations": [{"character_id": "ava", "relation": "mother"}]},
    "ruth": {},
}


def test_discovery():
    packet = CD.check_discovery(BEATS + [{"beat_id": 4}], MANIFEST)
    check("N123-1 a beat with no list and no nobody-else is refused",
          CD.CAST_DISCOVERY_INCOMPLETE in packet["codes"], packet)
    packet = CD.check_discovery([{"beat_id": 9, "cast_ids": ["janitor"]}], MANIFEST)
    check("N123-2 an unlocked person found by discovery is CAST_NOT_IN_BIBLE",
          CD.CAST_NOT_IN_BIBLE in packet["codes"], packet)
    cold = {1: ["ava"], 2: ["ava", "mother", "child"]}
    packet = CD.check_discovery([{"beat_id": 1, "cast_ids": ["ava"]},
                                 {"beat_id": 2, "cast_ids": ["ava", "mother"]}],
                                MANIFEST, cold=cold)
    check("N123-3 a cold-reader difference is named, not ignored",
          any(f.get("character_id") == "child" for f in packet["findings"]), packet)


def test_world():
    packet = CD.check_world_buildout(BEATS + [{"beat_id": 5, "location_id": "vestry"}],
                                     WORLD)
    check("N123-4 a place the beats name with no entry is refused",
          CD.LOCATION_NOT_IN_WORLD_BIBLE in packet["codes"], packet)
    bare = {"locations": [{"location_id": "kitchen"}]}
    packet = CD.check_world_buildout([{"beat_id": 1, "location_id": "kitchen"}], bare)
    check("N123-5 an unbuilt place is WORLD_BUILDOUT_INCOMPLETE",
          CD.WORLD_BUILDOUT_INCOMPLETE in packet["codes"], packet)


def test_profiles():
    bad = dict(PROFILES)
    bad["ava"] = dict(PROFILES["ava"], emotion_by_beat={1: "joy", 2: "hope"})
    packet = CD.check_profiles(bad, BEATS)
    check("N123-6 a profile emotion that contradicts its beat is refused",
          CD.PROFILE_OFF_BEAT in packet["codes"], packet)
    one_sided = dict(PROFILES)
    one_sided["mother"] = {"age": 67, "relations": []}
    packet = CD.check_profiles(one_sided, BEATS)
    check("N123-7 a one-sided relation is RELATION_CONFLICT",
          CD.RELATION_CONFLICT in packet["codes"], packet)
    bad_age = dict(PROFILES)
    bad_age["mother"] = {"age": 20, "relations": [{"character_id": "ava",
                                                    "relation": "mother"}]}
    bad_age["ava"] = dict(PROFILES["ava"],
                             relations=[{"character_id": "mother", "relation": "child"}])
    packet = CD.check_profiles(bad_age, BEATS)
    check("N123-8 a parent younger than the child is RELATION_CONFLICT",
          CD.RELATION_CONFLICT in packet["codes"], packet)


def test_gate_passes_when_complete():
    world = dict(WORLD)
    world["locations"] = list(WORLD["locations"]) + [
        {"location_id": "street", "layout_map": {"path": "east"}, "size": "5m",
         "set_pieces": ["lamp"], "establishing_pictures": ["/w/street.png"]}]
    packet = CD.completeness_gate(BEATS, MANIFEST, world, PROFILES)
    check("N123-9 the gate passes a complete discovery", packet["outcome"] == "pass",
          packet)


def test_run():
    test_discovery()
    test_world()
    test_profiles()
    test_gate_passes_when_complete()


if __name__ == "__main__":
    test_run()
    print("\n%s" % ("PASS 9/9" if not FAILS else "FAIL: %s" % ", ".join(FAILS)))
    sys.exit(1 if FAILS else 0)
