#!/usr/bin/env python3
"""Focused tests for the Story Beats gate and the story-script checks (U-SCRIPT).

N-115: the eleven beat fields, the eight-check beats gate, SCRIPT_OFF_BEAT and
SHOT_OFF_BEAT. Later rows add their own tests to this file.

Run: python3 -m pytest -q scripts/core/beat_sheet/test_beat_sheet.py
 or: python3 scripts/core/beat_sheet/test_beat_sheet.py
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))   # scripts/core: the beat_sheet package

import beat_sheet as B  # noqa: E402
from beat_sheet import spine as S  # noqa: E402


def _tag(emotion, intensity=2):
    return {"emotion": emotion, "intensity": intensity}


def _cues(smile="no", teeth="no"):
    return {"eyes": "level and steady", "brows": "set", "mouth": "firm",
            "smile": smile, "teeth": teeth, "tears": "none"}


def _beat(number, start, end, lines, **overrides):
    beat = {
        "beat_number": number,
        "name": "Beat %d" % number,
        "start_s": start,
        "end_s": end,
        "lyric_lines": [{"line_id": line, "text": "line %s words here" % line}
                        for line in lines],
        "who": {"on_screen": ["lead"], "singing": [], "listening": [],
                "else_seen": "nobody else is seen here"},
        "location_id": "home_kitchen",
        "time_of_day": "morning",
        "wardrobe": {"lead": "w_coat"},
        "entrances": [],
        "exits": [],
        "emotion_start": _tag("worry"),
        "emotion_end": _tag("pain"),
        "change": "She finds the bill and her face falls.",
        "event": None,
        "props_change": [],
        "lip_sync_candidates": [],
    }
    beat.update(overrides)
    return beat


def _valid_beats():
    return {
        "schema_version": B.STORY_BEATS_SCHEMA_VERSION,
        "beats": [
            _beat(1, 0.0, 20.0, ["L1", "L2", "L3", "L4"],
                  event={"kind": "bill_arrives", "line": "L2"},
                  lip_sync_candidates=[{"line_id": "L1", "start_s": 0.0, "end_s": 5.0}]),
            _beat(2, 20.0, 40.0, ["L5", "L6", "L7"],
                  emotion_start=_tag("pain"), emotion_end=_tag("resolve", 1),
                  change="She picks up the phone and decides to call.",
                  event={"kind": "phone_call", "line": "L6"}),
            _beat(3, 40.0, 60.0, ["L8", "L9", "L10"],
                  who={"on_screen": ["lead"], "singing": ["lead"], "listening": [],
                       "else_seen": "the choir in the loft"},
                  location_id="church", time_of_day="midday",
                  wardrobe={"lead": "w_dress"},
                  emotion_start=_tag("resolve", 1), emotion_end=_tag("hope", 1),
                  change="She walks into the church and the choir answers.",
                  entrances=[{"character_id": "lead", "location_id": "church"}],
                  lip_sync_candidates=[{"line_id": "L9", "start_s": 40.0, "end_s": 45.0}]),
            _beat(4, 60.0, 80.0, ["L11", "L12"],
                  who={"on_screen": ["lead"], "singing": ["lead"], "listening": [],
                       "else_seen": "the choir in the loft"},
                  location_id="church", time_of_day="midday",
                  wardrobe={"lead": "w_dress"},
                  emotion_start=_tag("hope", 1), emotion_end=_tag("joy"),
                  change="The choir answers her and she lifts her head."),
        ],
    }


def _measured(record):
    return [line for beat in record["beats"] for line in beat["lyric_lines"]]


def _codes(defects):
    return sorted({d["code"] for d in defects})


def _major(defects):
    return [d for d in defects if d["level"] == B.MAJOR]


def test_valid_beats_pass_the_eight_check_gate():
    verdict = B.validate_story_beats(_valid_beats(), measured_lines=_measured(_valid_beats()),
                                     hook_lines=["L9"])
    assert verdict["ok"] is True, verdict["defects"]
    assert verdict["beat_count"] == 4
    assert not _major(verdict["defects"])
    assert len(B.BEAT_FIELD_GROUPS) == 11


def test_every_beat_carries_all_eleven_field_groups():
    record = _valid_beats()
    del record["beats"][1]["change"]
    verdict = B.validate_story_beats(record)
    assert verdict["ok"] is False
    assert "BEAT_SCHEMA" in _codes(verdict["defects"])
    assert any(d["pointer"].endswith("/change") for d in verdict["defects"])


def test_measured_line_without_a_home_is_refused():
    record = _valid_beats()
    lines = _measured(record) + [{"line_id": "L99", "text": "orphan line"}]
    verdict = B.validate_story_beats(record, measured_lines=lines)
    assert "LINE_WITHOUT_BEAT" in _codes(verdict["defects"])


def test_overlapping_windows_are_refused():
    record = _valid_beats()
    record["beats"][1]["start_s"] = 10.0
    verdict = B.validate_story_beats(record)
    assert "BEAT_WINDOWS_OVERLAP" in _codes(verdict["defects"])


def test_double_entrance_is_a_major_story_break():
    record = _valid_beats()
    record["beats"][2]["entrances"] = [
        {"character_id": "lead", "location_id": "church"},
        {"character_id": "lead", "location_id": "church"},
    ]
    verdict = B.validate_story_beats(record, measured_lines=_measured(record))
    double = [d for d in verdict["defects"] if d["code"] == "DOUBLE_ENTRANCE"]
    assert double and double[0]["level"] == B.MAJOR and double[0]["item"] == 9


def test_time_running_backwards_is_refused():
    record = _valid_beats()
    record["beats"][3]["time_of_day"] = "dawn"
    record["beats"][3]["location_id"] = "church"
    verdict = B.validate_story_beats(record, measured_lines=_measured(record))
    assert "TIME_BACKWARD" in _codes(verdict["defects"])


def test_wardrobe_change_inside_a_scene_is_refused():
    record = _valid_beats()
    record["beats"][1]["wardrobe"] = {"lead": "w_other"}
    verdict = B.validate_story_beats(record, measured_lines=_measured(record))
    assert "WARDROBE_MID_SCENE" in _codes(verdict["defects"])


def test_repeated_event_and_event_off_its_lyric_are_refused():
    record = _valid_beats()
    record["beats"][1]["event"] = {"kind": "bill_arrives", "line": "L11"}
    verdict = B.validate_story_beats(record, measured_lines=_measured(record))
    codes = _codes(verdict["defects"])
    assert "EVENT_REPEATED" in codes
    assert "EVENT_OFF_LYRIC" in codes


def test_opening_missing_and_hook_not_sung_are_refused():
    record = _valid_beats()
    record["beats"][0]["lip_sync_candidates"] = []
    record["beats"][2]["who"]["singing"] = []
    record["beats"][2]["lip_sync_candidates"] = []
    verdict = B.validate_story_beats(record, measured_lines=_measured(record),
                                     hook_lines=["L9"])
    codes = _codes(verdict["defects"])
    assert "OPENING_MISSING" in codes
    assert "HOOK_NOT_SUNG" in codes


def test_shot_off_beat_refuses_a_route_from_another_beat():
    routes = [
        {"beat_number": 1, "location_id": "home_kitchen", "cast_ids": ["lead"]},
        {"beat_number": 2, "location_id": "church", "cast_ids": ["lead"]},
        {"beat_number": 99, "location_id": "home_kitchen", "cast_ids": ["lead"]},
    ]
    defects = B.shot_off_beat_defects(routes, _valid_beats())
    pointers = [d["pointer"] for d in defects]
    assert "/shot-routes/1/location_id" in pointers
    assert "/shot-routes/2/beat_number" in pointers
    assert all(d["code"] == "SHOT_OFF_BEAT" for d in defects)


def _spine(words=320):
    return {
        "schema_version": B.SPINE_SCHEMA_VERSION,
        "text": "word " * words,
        "cast": ["lead"],
        "places_in_order": ["scene_1", "scene_2"],
        "time_of_day_by_scene": {"scene_1": "morning", "scene_2": "midday"},
        "wardrobe_by_scene": {"scene_1": {"lead": "w_coat"},
                              "scene_2": {"lead": "w_dress"}},
        "arc": "worry sharpens to pain, then resolves into hope.",
    }


# --- N-74: the spine, the one joiner and the order ------------------------

def test_spine_of_300_to_500_words_passes():
    verdict = S.spine_gate(_spine(), cast_ids=["lead"],
                           scene_ids=["scene_1", "scene_2"])
    assert verdict["ok"] is True, verdict["defects"]
    assert S.validate_spine(_spine(299)) != []
    assert S.validate_spine(_spine(501)) != []


def test_spine_naming_a_cast_the_run_does_not_hold_is_refused():
    spine = _spine()
    spine["cast"] = ["lead", "ghost"]
    defects = S.validate_spine(spine, cast_ids=["lead"])
    assert any(d["code"] == "SPINE_CAST_DRIFT" for d in defects)


def test_no_script_row_is_allowed_before_the_beats_gate():
    bad = _valid_beats()
    del bad["beats"][0]["change"]
    verdict = S.gate_before_script(_spine(), bad, cast_ids=["lead"],
                                   scene_ids=["scene_1", "scene_2"])
    assert verdict["ok"] is False
    assert verdict["script_rows_allowed"] is False

    good = S.gate_before_script(_spine(), _valid_beats(), cast_ids=["lead"],
                                scene_ids=["scene_1", "scene_2"],
                                measured_lines=_measured(_valid_beats()),
                                hook_lines=["L9"])
    assert good["script_rows_allowed"] is True, good["defects"]


def test_the_joiner_sorts_sections_in_time_order_and_keeps_them_whole():
    rows = [
        {"row_id": "r2", "line_id": "L2", "start_s": 5.0, "section": "verse"},
        {"row_id": "r1", "line_id": "L1", "start_s": 0.0, "section": "verse"},
        {"row_id": "r3", "line_id": "L3", "start_s": 10.0, "section": "chorus"},
    ]
    joined = S.join_sections(rows, section_order=["verse", "chorus"])
    assert joined["ok"] is True
    assert [r["row_id"] for r in joined["rows"]] == ["r1", "r2", "r3"]
    assert [r["join_index"] for r in joined["rows"]] == [1, 2, 3]
    assert rows[0]["start_s"] == 5.0  # input never mutated


def test_two_writers_cannot_produce_one_row():
    rows = [{"row_id": "r1", "start_s": 0.0}, {"row_id": "r1", "start_s": 5.0}]
    joined = S.join_sections(rows)
    assert joined["ok"] is False
    assert any(d["code"] == "JOIN_DUPLICATE_ROW" for d in joined["defects"])


def test_a_failed_row_returns_to_its_own_writer():
    writers = {"verse": "writer-v", "chorus": "writer-c"}
    results = {
        "r1": {"ok": False, "section": "verse", "defects": [{"code": "X"}]},
        "r2": {"ok": True, "section": "chorus"},
        "r3": {"ok": False, "section": "chorus", "defects": [{"code": "Y"}]},
    }
    routed = S.route_failures(results, writers)
    assert [r["row_id"] for r in routed["writer-v"]] == ["r1"]
    assert [r["row_id"] for r in routed["writer-c"]] == ["r3"]


# --- Gate 2: one verdict from every story check (N-99, 3J.3) ---------------

def _gate_row(line_id="L1", beat=1, **overrides):
    row = {
        "row_id": "r" + line_id, "line_id": line_id, "beat_number": beat,
        "start_s": 0.0, "end_s": 8.0, "line": "line %s words here" % line_id,
        "who_sings": "lead", "singing": ["lead"], "on_screen": ["lead"],
        "location_id": "home_kitchen", "time_of_day": "morning",
        "wardrobe": {"lead": "w_coat"}, "lip_sync": True,
        "emotion": "worry", "intensity": 2, "facial_cues": _cues(),
        "line_match": "MATCH",
    }
    row.update(overrides)
    return row


def _one_beat_beats():
    return {"beats": [_beat(1, 0.0, 8.0, ["L1"], change="a choice is made",
                            emotion_start=_tag("worry"), emotion_end=_tag("pain"),
                            lip_sync_candidates=[{"line_id": "L1",
                                                  "start_s": 0.0, "end_s": 5.0}])]}


def _gate_spine():
    return _spine(words=320)


def _voice_map():
    return {"stretches": [{"start_s": 0.0, "end_s": 8.0, "voice_id": "lead"}]}


def test_story_gate_passes_a_clean_script():
    verdict = B.story_gate(_gate_spine(), _one_beat_beats(),
                           {"rows": [_gate_row()]},
                           cast_ids=["lead"], scene_ids=["scene_1", "scene_2"],
                           voice_map=_voice_map())
    assert verdict["script_rows_allowed"], verdict["defects"]
    assert verdict["ok"], [d for d in verdict["defects"] if d["level"] == B.MAJOR]
    assert verdict["counts"]["MAJOR"] == 0


def test_story_gate_blocks_the_pictures_on_a_mismatch_line():
    row = _gate_row(line_match="MISMATCH")
    verdict = B.story_gate(_gate_spine(), _one_beat_beats(), {"rows": [row]},
                           cast_ids=["lead"], scene_ids=["scene_1", "scene_2"],
                           voice_map=_voice_map())
    assert verdict["blocks_pictures"] is True
    assert verdict["ok"] is False
    assert any(d["code"] == "MISMATCH" and d["item"] == 10
               for d in verdict["defects"])


def test_no_script_row_runs_before_the_spine_holds():
    verdict = B.story_gate(_spine(words=20), _one_beat_beats(),
                           {"rows": [_gate_row()]},
                           cast_ids=["lead"], scene_ids=["scene_1", "scene_2"])
    assert verdict["script_rows_allowed"] is False
    assert verdict["row_count"] == 0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failures = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failures += 1
            print("FAIL %s: %s" % (test.__name__, exc))
        else:
            print("ok   %s" % test.__name__)
    print("%d passed, %d failed" % (len(tests) - failures, failures))
    sys.exit(1 if failures else 0)
