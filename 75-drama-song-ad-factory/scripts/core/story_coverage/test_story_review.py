#!/usr/bin/env python3
"""story_coverage.story_review: the story-logic review contract (N-67).

Run: python3 75-drama-song-ad-factory/scripts/core/story_coverage/test_story_review.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from story_coverage import story_review as SR  # noqa: E402


def _beats():
    return {"beats": [
        {"beat_number": 1, "start_s": 0.0, "location_id": "kitchen",
         "time_of_day": "dawn"},
        {"beat_number": 2, "start_s": 6.0, "location_id": "church",
         "time_of_day": "morning"},
    ]}


def test_same_model_is_refused():
    out = SR.build_request(writer_model="a", reviewer_model="a", beats=_beats())
    assert out["outcome"] == "rejected"
    assert out["reason_code"] == "REVIEW_MODEL_NOT_DIFFERENT"


def test_request_reads_beats_then_script_and_lists_scene_changes():
    out = SR.build_request(writer_model="a", reviewer_model="b", beats=_beats())
    assert out["outcome"] == "ok"
    req = out["request"]
    assert req["reading_order"] == ["story_beats", "story_script"]
    assert req["scene_changes"][0]["from_beat"] == 1
    assert req["scene_changes"][0]["to_beat"] == 2


def test_review_is_once_plus_once_after_fixes():
    out = SR.build_request(writer_model="a", reviewer_model="b", beats=_beats(), run=3)
    assert out["reason_code"] == "REVIEW_BUDGET_EXCEEDED"
    assert SR.review_once({"runs": 2})["outcome"] == "rejected"


def test_every_finding_needs_a_resolution():
    req = SR.build_request(writer_model="a", reviewer_model="b", beats=_beats())["request"]
    bad = SR.record_result(req, [{"beat_number": 1, "code": "DOUBLE_ENTRANCE",
                                  "question": "where", "note": "x"}])
    assert bad["reason_code"] == "REVIEW_FINDING_UNRESOLVED"
    good = SR.record_result(req, [
        {"beat_number": 1, "code": "DOUBLE_ENTRANCE", "question": "where",
         "note": "x", "resolution": {"answered": "she stays in the kitchen"}},
    ])
    assert good["outcome"] == "ok"


def test_report_is_stored_with_the_approval_package():
    req = SR.build_request(writer_model="a", reviewer_model="b", beats=_beats())["request"]
    review = SR.record_result(req, [])
    package = SR.attach_to_approval_package({}, review)
    assert package["story_review"]["runs"][0]["run"] == 1
    assert "findings" in package["story_review"]["runs"][0]
