#!/usr/bin/env python3
"""test_picture_faces_n117.py: only the singers are in a lip-sync picture.

Row N-117 (section 3N.3): every lip-sync picture names each face, its role in
the piece (lead or backing) and its place from left to right, and a person who
is silent in the piece is not in the picture at all.

Run: python3 scripts/core/storyboard/test_picture_faces_n117.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import storyboard.lipsync_map as M                          # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# The Voice Map: lead alone at 10-18 s, the backing singers at 40-48 s.
VOICE_MAP = [
    {"start_s": 0.0, "end_s": 20.0, "singers": ["ava"], "role": "lead"},
    {"start_s": 40.0, "end_s": 48.0, "singers": ["kay", "moe"], "role": "backing"},
]


def codes(rows):
    return sorted({f["code"] for f in M.check_picture_faces(rows, VOICE_MAP)})


# A lead picture shows only the lead: it passes.
lead = [{"shot_id": "T1", "song_start": 10.0, "song_end": 18.0,
         "route": "omnihuman",
         "picture_faces": [{"character": "Ava", "role": "lead", "place": 0}]}]


def test_run():
    check("N-117 a lead picture with only the lead passes", codes(lead) == [],
          codes(lead))

    # A backing picture shows the backing singers, not the lead.
    choir = [{"shot_id": "T2", "song_start": 40.0, "song_end": 48.0,
              "route": "omnihuman",
              "picture_faces": [{"character": "kay", "role": "backing", "place": 0},
                                {"character": "moe", "role": "backing", "place": 1}]}]
    check("N-117 a backing picture with the two singers passes", codes(choir) == [],
          codes(choir))

    # The lead mouthing through a backing stretch is the defect this closes.
    wrong = [{"shot_id": "T2", "song_start": 40.0, "song_end": 48.0,
              "route": "omnihuman",
              "picture_faces": [{"character": "ava", "role": "lead", "place": 0}]}]
    check("N-117 the lead shown through a backing stretch is refused",
          codes(wrong) == ["LIPSYNC_WRONG_FACES"], codes(wrong))

    # A silent extra in the frame is refused: only singers are in the picture.
    extra = [{"shot_id": "T3", "song_start": 10.0, "song_end": 18.0,
              "route": "omnihuman",
              "picture_faces": [{"character": "ava", "role": "lead", "place": 0},
                                {"character": "ben", "role": "backing", "place": 1}]}]
    check("N-117 a silent person in the picture is refused",
          codes(extra) == ["LIPSYNC_WRONG_FACES"], codes(extra))

    # A picture with no face record is refused, never passed.
    bare = [{"shot_id": "T4", "song_start": 10.0, "song_end": 18.0,
             "route": "omnihuman"}]
    check("N-117 a picture with no face record is refused",
          codes(bare) == ["LIPSYNC_PICTURE_RECORD_INCOMPLETE"], codes(bare))

    # Places must run 0..n-1 left to right.
    gappy = [{"shot_id": "T5", "song_start": 40.0, "song_end": 48.0,
              "route": "omnihuman",
              "picture_faces": [{"character": "kay", "role": "backing", "place": 0},
                                {"character": "moe", "role": "backing", "place": 2}]}]
    check("N-117 face places must run left to right with no gap",
          codes(gappy) == ["LIPSYNC_PICTURE_RECORD_INCOMPLETE"], codes(gappy))

    # A role outside lead/backing is not a valid record.
    badrole = [{"shot_id": "T6", "song_start": 10.0, "song_end": 18.0,
                "route": "omnihuman",
                "picture_faces": [{"character": "ava", "role": "choir", "place": 0}]}]
    check("N-117 a face role outside lead/backing is refused",
          codes(badrole) == ["LIPSYNC_PICTURE_RECORD_INCOMPLETE"], codes(badrole))

    # A story shot is not a lip-sync picture and is not checked here.
    story = [{"shot_id": "T7", "song_start": 10.0, "song_end": 18.0,
              "route": "h3_start_end", "character_ids": ["ava", "ben"]}]
    check("N-117 a story shot is not a lip-sync picture", codes(story) == [],
          codes(story))

    assert not FAILS, FAILS


if __name__ == "__main__":
    test_run()
    print()
    print("FAILED: %d" % len(FAILS) if FAILS else "PASS: all checks")
    sys.exit(1 if FAILS else 0)
