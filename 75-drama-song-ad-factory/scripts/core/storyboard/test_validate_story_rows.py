#!/usr/bin/env python3
"""Tests for the storyboard row refusals (G-STORY-01/02/03, G-SPEAKER-01, N-14, N-22).

Run: python3 scripts/core/storyboard/test_validate_story_rows.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import storyboard.validate as V                          # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def codes(rows):
    return sorted({r["code"] for r in rows})


# G-STORY-01: the T17 row. Ava sings a hook line on a shot cast as the choir.
T17 = [{"shot_id": "T17", "song_start": 40.0, "song_end": 45.0,
        "speaker": "Ava", "characters": ["choir-member-1", "choir-member-2"],
        "lyric": "Hold the line, no more fear", "route": "h3_start_end"}]

T17_OK = [{"shot_id": "T17", "song_start": 40.0, "song_end": 45.0,
           "speaker": "choir", "characters": ["choir-member-1"],
           "lyric": "Hold the line, no more fear", "route": "h3_start_end",
           "label": "choir", "camera": "ensemble medium, mouths open, singing"}]


def test_g_story_01():
    rows = V.check_speaker_cast(T17)
    check("G-STORY-01 absent singer refused",
          codes(rows) == ["SPEAKER_NOT_IN_CAST"], rows)
    check("G-STORY-01 refusal names the shot", rows[0]["shot_id"] == "T17", rows)
    check("G-STORY-01 corrected row passes", V.check_speaker_cast(T17_OK) == [])
    # A voice-over direction is never a cast member and is always allowed here.
    vo = [{"shot_id": "V1", "speaker": "narrator-voiceover", "characters": ["Ava"]}]
    check("G-STORY-01 voice-over is a declared direction",
          V.check_speaker_cast(vo) == [], V.check_speaker_cast(vo))


def test_g_speaker_01():
    rows = [
        {"shot_id": "T17", "speaker": "choir", "route": "kling_lipsync",
         "lyric": "Hold the line, no more fear"},
        {"shot_id": "T21", "speaker": "instrumental", "lyric": "",
         "route": "h3_start_end"},
        {"shot_id": "T22", "speaker": "instrumental", "lyric": "a line",
         "route": "h3_start_end"},
        {"shot_id": "T27", "speaker": "narrator-voiceover", "route": "kling_lipsync",
         "lyric": "Go to example.com."},
    ]
    got = codes(V.check_speaker_labels(rows))
    check("G-SPEAKER-01 choir on a lip-sync route refused",
          "CHOIR_SPEAKER_LIPSYNC" in got, got)
    check("G-SPEAKER-01 instrumental carrying words refused",
          "INSTRUMENTAL_WITH_WORDS" in got, got)
    check("G-SPEAKER-01 voice-over on a lip-sync route refused",
          "VOICEOVER_LIPSYNC" in got, got)
    check("G-SPEAKER-01 corrected labels pass",
          V.check_speaker_labels(T17_OK) == [], V.check_speaker_labels(T17_OK))


def test_g_story_02_and_n_22():
    t27 = [{"shot_id": "T27", "route": "kling_lipsync", "lip_sync": True,
            "lyric": "Go to example.com.",
            "camera": "The spoken line plays over this shot and nobody lip-syncs it."}]
    rows = V.check_lipsync_contradiction(t27)
    check("G-STORY-02 T27 lip-sync route under 'nobody lip-syncs' refused",
          codes(rows) == ["LIPSYNC_CONTRADICTION"], rows)
    fixed = [dict(t27[0], route="h3_start_end", lip_sync=False)]
    check("G-STORY-02 aligned T27 row passes",
          V.check_lipsync_contradiction(fixed) == [])
    check("G-STORY-02 align_route corrects the row",
          V.align_route(t27[0])["route"] == "h3_start_end")

    both = V.check_contradiction_both_ways(
        [{"shot_id": "X1", "route": "h3_start_end", "lip_sync": False,
          "camera": "she sings the line on camera"}])
    check("N-22 a note saying she sings with no lip-sync route refused",
          codes(both) == ["LIPSYNC_CONTRADICTION"], both)


def test_g_story_03():
    t10 = [{"shot_id": "T10", "song_start": 47.0, "song_end": 52.0,
            "action_beats": ["phone close-up", "pullback", "smile",
                             "smile fade", "phone face-down", "blazer off",
                             "hair down"]}]
    rows = V.check_beat_density(t10)
    check("G-STORY-03 seven beats in five seconds refused",
          codes(rows) == ["BEAT_DENSITY_EXCEEDED"], rows)
    spread = [{"shot_id": "T10", "song_start": 47.0, "song_end": 55.0,
               "action_beats": ["phone close-up", "pullback", "smile fade"]}]
    check("G-STORY-03 re-spread beats pass", V.check_beat_density(spread) == [])

    # The beach phone must stay on screen for the whole "no breaks for me" line.
    short = [{"shot_id": "T10", "song_start": 49.5, "song_end": 53.0,
              "lyric_named_picture": "beach on the phone screen",
              "picture_start": 49.5, "picture_end": 51.5}]
    rows = V.check_lyric_picture_window(short, {"T10": (50.26, 52.06)})
    check("G-STORY-03 lyric picture cut short refused",
          codes(rows) == ["LYRIC_PICTURE_CUT_SHORT"], rows)
    held = [dict(short[0], picture_end=52.5)]
    check("G-STORY-03 held picture passes",
          V.check_lyric_picture_window(held, {"T10": (50.26, 52.06)}) == [])


def test_n_14_no_empty_room():
    rows = [{"shot_id": "S1", "crowd_state": "service",
             "prompt": "the room is empty, no crowd"}]
    check("N-14 emptying line on a full scene refused",
          codes(V.check_no_empty_room(rows)) == ["EMPTY_ROOM_ON_FULL_SCENE"])
    rows = [{"shot_id": "S1", "crowd_state": "empty",
             "prompt": "the room is empty"}]
    check("N-14 emptying line on an empty scene passes",
          V.check_no_empty_room(rows) == [])


def test_run():
    test_g_story_01()
    test_g_speaker_01()
    test_g_story_02_and_n_22()
    test_g_story_03()
    test_n_14_no_empty_room()


if __name__ == "__main__":
    test_run()
    print("\n%s" % ("PASS" if not FAILS else "FAIL: %s" % ", ".join(FAILS)))
    sys.exit(1 if FAILS else 0)
