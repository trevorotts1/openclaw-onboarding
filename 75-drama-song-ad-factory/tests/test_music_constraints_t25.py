#!/usr/bin/env python3
"""S75-T25 focused checks: durations, opener, lip-sync, routes, word fit.

Stdlib only, no provider call, no spend, no client write. Fixtures supply every
number; nothing here contacts a service or reads a client run.

    python3 tests/test_music_constraints_t25.py
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "core"))

from music import constraints as C      # noqa: E402
from music import word_fit as W         # noqa: E402

FIXTURE = json.loads((pathlib.Path(__file__).resolve().parent
                      / "fixtures" / "duration_and_lipsync.json").read_text())


def _raises(code, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError as exc:
        assert getattr(exc, "code", None) == code, (code, exc)
        return exc
    raise AssertionError("expected %s" % code)


# -- durations ---------------------------------------------------------------

def test_six_canonical_durations_accepted():
    assert [C.duration_seconds(s) for s in FIXTURE["durations_s"]] == \
        [60, 90, 120, 180, 300, 600]
    assert C.DURATIONS_S == tuple(FIXTURE["durations_s"])


def test_off_registry_durations_rejected():
    for bad in FIXTURE["rejected_durations"]:
        _raises("BAD_DURATION", C.duration_seconds, bad)


# -- eighteen styles x six durations x route --------------------------------

def test_matrix_binds_every_style_and_duration():
    rows = C.bind_matrix(route=FIXTURE["route"])
    assert len(rows) == len(FIXTURE["style_ids"]) * len(FIXTURE["durations_s"]) == 108
    assert {r["style_id"] for r in rows} == set(FIXTURE["style_ids"])
    assert {r["duration_s"] for r in rows} == set(FIXTURE["durations_s"])
    for row in rows:
        assert row["route"] == FIXTURE["route_resolved"]
        assert row["route_requested"] == FIXTURE["route"]
        assert row["spoken_opener_s"] == 12.0
        assert row["lipsync_target"] == [0.25, 0.30]
        assert row["lipsync_cap"] == 0.35


def test_unknown_style_fails_closed():
    _raises("BAD_STYLE", C.bind_matrix, style_ids=["soul-ballad", "Not A Style"])


# -- first twelve seconds ----------------------------------------------------

def test_opener_accepted():
    result = C.check_opener(FIXTURE["opener"]["accepted"], duration_s=60)
    assert result["ok"] and result["spoken_opener_seconds"] == 12.0


def test_opener_short_rejected():
    _raises("OPENER_TOO_SHORT", C.check_opener, FIXTURE["opener"]["short"])


def test_opener_sung_rejected():
    _raises("OPENER_NOT_SPOKEN", C.check_opener, FIXTURE["opener"]["sung"])


def test_opener_wordless_intro_rejected():
    _raises("OPENER_WORDLESS_INTRO", C.check_opener,
            FIXTURE["opener"]["wordless_intro"])


def test_opener_swallowed_rejected():
    _raises("OPENER_NOT_ARTICULATED", C.check_opener,
            FIXTURE["opener"]["swallowed"])


# -- visible lip-sync: interval union arithmetic -----------------------------

def test_union_counts_simultaneous_faces_once():
    case = FIXTURE["lipsync"]["union"]
    assert C.union_duration(case["intervals"]) == case["expected_union_s"]
    measured = C.visible_lip_sync(case["intervals"], case["final_runtime_s"])
    assert measured["share"] == case["expected_share"]
    assert measured["status"] == "BELOW_TARGET"


def test_36_percent_visible_lip_sync_rejected_by_cap():
    case = FIXTURE["lipsync"]["cap_violation_36pct"]
    measured = C.visible_lip_sync(case["intervals"], case["final_runtime_s"])
    assert measured["share"] == case["expected_share"] == 0.36
    assert measured["status"] == "OVER_CAP"
    _raises("LIPSYNC_CAP_EXCEEDED", C.assert_lipsync,
            case["intervals"], case["final_runtime_s"])


def test_exact_35_percent_is_accepted():
    case = FIXTURE["lipsync"]["cap_exact_35pct_120s"]
    assert C.assert_lipsync(case["intervals"], case["final_runtime_s"])["share"] == 0.35
    _raises("LIPSYNC_CAP_EXCEEDED", C.assert_lipsync, [[0.0, 42.001]], 120)


def test_30_percent_is_in_target():
    case = FIXTURE["lipsync"]["at_target_30pct"]
    assert C.visible_lip_sync(case["intervals"], case["final_runtime_s"])["status"] \
        == "IN_TARGET"


# -- adversarial: spoken audio is not visible lip-sync ----------------------

def test_offscreen_speech_does_not_prove_visual_cap():
    case = FIXTURE["lipsync"]["adversarial_offscreen_speech"]
    visual = C.assert_lipsync(case["intervals"], case["final_runtime_s"])
    audio = C.spoken_audio_share(case["spoken_seconds"], case["final_runtime_s"])
    assert visual["share"] == case["expected_lipsync_share"] == 0.20
    assert audio["share"] == case["expected_spoken_share"] == 0.50
    assert audio["counts_toward_lipsync_cap"] is False
    assert visual["basis"] != audio["basis"]


def test_visible_sung_closeup_counts_even_when_audio_is_sung():
    case = FIXTURE["lipsync"]["adversarial_visible_sung_closeup"]
    visual = C.visible_lip_sync(case["intervals"], case["final_runtime_s"])
    audio = C.spoken_audio_share(case["spoken_seconds"], case["final_runtime_s"])
    assert visual["share"] == case["expected_lipsync_share"] == 0.30
    assert visual["status"] == "IN_TARGET"
    assert audio["share"] == case["expected_spoken_share"] == 0.20
    assert visual["share"] != audio["share"]


def test_spoken_duration_and_lipsync_are_separate_kinds():
    visual = C.visible_lip_sync([[0.0, 12.0]], 60)
    audio = C.spoken_audio_share(12.0, 60)
    assert visual["kind"] == "visible_lip_sync" and audio["kind"] == "spoken_audio"
    assert "spoken" not in visual["basis"]
    assert visual["final_runtime_s"] == audio["final_runtime_s"] == 60


# -- routes ------------------------------------------------------------------

def test_route_label_resolves_and_substitution_refused():
    assert C.assert_route(FIXTURE["route"])["resolved"] == FIXTURE["route_resolved"]
    C.assert_route_preserved("MiniMax H3", "minimax-h3/*")
    _raises("ROUTE_SUBSTITUTED", C.assert_route_preserved,
            "MiniMax H3", "hailuo/02-image-to-video-*")
    _raises("MODEL_NOT_ON_MENU", C.assert_route, "seedance-1.5-pro")
    _raises("ROUTE_NOT_SELECTED", C.assert_route, "")


# -- word fit per duration and style ----------------------------------------

def test_word_fit_accepts_plan_inside_available_vocal_time():
    case = FIXTURE["word_fit"]["fit"]
    result = W.fit(case["blocks"], case["duration_s"], case["style_id"],
                   case["instrumental_only_s"], case["breath_allowance_s"],
                   protected=case["protected"])
    assert result["available_vocal_seconds"] == 51.0
    assert result["status"] == "OK"
    assert result["planned_seconds"] <= result["available_vocal_seconds"]
    assert result["protected_words"] == ["free consultation"]


def test_word_fit_overflow_routes_to_review_and_keeps_protected_words():
    case = FIXTURE["word_fit"]["overflow"]
    result = W.fit(case["blocks"], case["duration_s"], case["style_id"],
                   case["instrumental_only_s"], case["breath_allowance_s"],
                   protected=["free consultation"])
    assert result["status"] == "OVERFLOW"
    assert result["excess_s"] > 0
    assert result["requires"] == "PACKAGE_REVISION_REVIEW"
    assert result["protected_words"] == ["free consultation"]
    assert "preserve protected" in result["proposed_edit"]


def test_word_fit_matrix_covers_every_style_and_duration():
    for style_id in FIXTURE["style_ids"]:
        rates = W.style_rates(style_id)
        for seconds in FIXTURE["durations_s"]:
            available = W.available_vocal_seconds(seconds)
            blocks = [
                {"delivery": "spoken", "words": 20, "pause_s": 0.5},
                {"delivery": "sung",
                 "words": int(available * 0.40 * rates["sung"]), "pause_s": 1.0},
            ]
            result = W.fit(blocks, seconds, style_id)
            assert result["status"] == "OK", (style_id, seconds, result)


def test_word_fit_rejects_empty_or_bad_blocks():
    _raises("BAD_INPUT", W.fit, [], 60, "soul-ballad")
    _raises("BAD_DELIVERY", W.fit,
            [{"delivery": "shouted", "words": 5}], 60, "soul-ballad")
    _raises("NO_VOCAL_TIME", W.available_vocal_seconds, 60, 55.0, 5.0)


def _run():
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print("PASS %s" % name)
    print("%d passed" % len(tests))
    return 0


if __name__ == "__main__":
    sys.exit(_run())
