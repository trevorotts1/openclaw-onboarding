#!/usr/bin/env python3
"""F1/F2 — the 50% planning contingency measured from the shot/cue manifest.

Run: python3 -m pytest -q scripts/core/test_budget_contingency_f1.py

Every test here fails on the old bare 20%: the rate is 0.50, the contingency is
computed from a manifest, and a missing manifest is a typed refusal, never a
silent percentage.
"""
import inspect
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import budget_contingency as BC  # noqa: E402


def test_one_rate_is_half():
    assert BC.RATE == BC.Decimal("0.50")
    assert BC.percent() == 50
    assert BC.label() == "50%"
    assert BC.multiplier() == BC.Decimal("1.50")


def test_hundred_dollars_becomes_a_hundred_fifty_envelope():
    assert BC.contingency(100) == 50.0
    assert BC.envelope(100) == 150.0


def test_fractional_contingency_rounds_half_up_to_the_cent():
    assert BC.contingency("0.01") == 0.01      # 0.005 -> 1 cent
    assert BC.envelope("0.01") == 0.02
    assert BC.contingency("0.03") == 0.02      # 0.015 -> 2 cents
    assert BC.contingency(1.25) == 0.63        # 0.625 -> 63 cents


def test_missing_manifest_is_a_typed_refusal_not_a_percentage():
    for manifest in (None, {}, {"shots": [], "cues": [{"cue_id": "song-1"}]},
                     {"shots": [{"shot_id": "s1", "seconds": 6}]},
                     {"shots": [{"shot_id": "s1"}], "cues": [{"cue_id": "c1"}]}):
        try:
            BC.measure(manifest, 100)
        except BC.ContingencyUnmeasured as exc:
            assert exc.code == BC.CODE == "CONTINGENCY_UNMEASURED", exc
        else:
            raise AssertionError("measure accepted an unmeasured manifest: %r"
                                 % (manifest,))


def test_carrying_an_unmeasured_basis_is_refused():
    for measured in (None, {}, {"basis": "invented", "shots": 1, "cues": 1},
                     {"basis": BC.BASIS, "shots": 0, "cues": 0}):
        try:
            BC.remeasure(measured, 100)
        except BC.ContingencyUnmeasured:
            pass
        else:
            raise AssertionError("remeasure accepted %r" % (measured,))


def test_measure_reads_the_manifest():
    manifest = {"projected": True,
                "shots": [{"shot_id": "s1", "seconds": 6},
                          {"shot_id": "s2", "seconds": 6}],
                "cues": [{"cue_id": "song-1"}]}
    got = BC.measure(manifest, 100)
    assert got == {"basis": "shot-cue-manifest", "rate": 0.5, "percent": 50,
                   "label": "50% planning allowance", "shots": 2, "cues": 1,
                   "baseline_usd": 100.0, "contingency_usd": 50.0,
                   "envelope_usd": 150.0, "projected": True}, got


def test_catalog_calculator_card_applies_half():
    from catalog_calculator import catalog_calculator as CC
    norm = {"length_seconds": 60, "shapes": ["9:16"], "shape_count": 1}
    entry = {"id": "m", "resolution": "768P", "max_shot_seconds": 6}
    lines = {"video": {"credits": 20000}, "music": {"credits": 0},
             "image": {"credits": 0}}
    card = CC._build_card(norm, entry, lines, True)
    assert card["price_usd"] == 100.0, card["price_usd"]
    assert card["retake_allowance_usd"] == 50.0      # was 20.0 on the old rate
    assert card["spending_limit_usd"] == 150.0       # was 120.0
    assert card["allowance"]["basis"] == BC.BASIS
    assert card["allowance"]["shots"] == 10          # 60 s / 6 s max shot
    assert card["allowance"]["cues"] == 1


def test_the_three_rate_aliases_are_the_one_source():
    from catalog_calculator import card_render as CR
    from catalog_calculator.extensions import price_extension as PE
    from batch_mode import batch as B
    assert CR.RETAKE_RATE == float(BC.RATE) == 0.5
    assert PE.RETAKE_RATE == float(BC.RATE) == 0.5
    assert B.RETAKE_ALLOWANCE == float(BC.RATE) == 0.5
    assert PE.retake_allowance(100) == 50.0


def test_batch_ceiling_is_the_envelope():
    from batch_mode import batch as B
    card = B.make_card({})
    card = B.set_books(card, [B.normalize_brief({"title": "T", "author": "A"})])
    out = B.price_batch(card, lambda book, fields: 1.25)
    assert out["price_status"] == "ok", out.get("reasons")
    assert out["price_usd"] == 1.88            # 1.25 + 0.63 contingent = 1.88
    assert out["books"][0]["ceiling_usd"] == 1.88
    assert out["allowance"]["basis"] == BC.BASIS
    assert B.approve_batch(out)["retake_allowance"] == 0.5


def test_agnes_plan_and_quota_use_half():
    import agnes_plan as AP
    from agnes_quota import agnes_quota as AQ
    assert AP.ALLOWANCE == 1.5
    assert AP.need(AP.segments(298), ["cartoon"])["allowance_seconds"] == 450
    default = inspect.signature(AQ.fits_today).parameters["allowance"].default
    assert default == 1.5, default


def test_client_facing_text_states_the_computed_rate():
    from choice_card.intake_card import intake_card as IC
    q = IC.spend_question(18.5)
    text = q["options"][0][1]
    assert "50%" in text and "20%" not in text, text
    line = IC._model_price_line("60 seconds")
    assert "50%" in line and "20%" not in line, line
