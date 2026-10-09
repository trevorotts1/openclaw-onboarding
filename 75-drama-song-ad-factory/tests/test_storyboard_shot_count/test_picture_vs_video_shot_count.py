#!/usr/bin/env python3
"""PKG-06-U3 — DEL-15: the storyboard picture count stays a separate count
from the video shot count.

The storyboard draws its own pictures (8 at 60 s, 24 at 2 min, ~1 per 5 s
beyond, capped at 120). The video shot count is a different function of a
different input: ceil(length / the chosen model's max shot). These tests
prove the two are distinct surfaces that never mix: different signatures,
different values for the same ad, two separate card fields, and pictures
always at least as many as the shots they will be cut from.

Run: python3 tests/test_storyboard_shot_count/test_picture_vs_video_shot_count.py
(also collected by pytest). stdlib only, no network.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import os
import sys
import unittest

HERE = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.realpath(os.path.join(HERE, "..", ".."))
CORE = os.path.join(SKILL, "scripts", "core")
if CORE not in sys.path:
    sys.path.insert(0, CORE)
CALC_PATH = os.path.join(CORE, "catalog_calculator", "catalog_calculator.py")
CATALOG_PATH = os.path.join(CORE, "catalog_calculator", "extensions",
                            "fixtures", "catalog.json")

_spec = importlib.util.spec_from_file_location("pkg06u3_calc_counts", CALC_PATH)
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)

#: Every length the card menu offers (INSTRUCTIONS.md length row).
OFFERED_LENGTHS = (60, 90, 120, 180, 300, 600)


def approved_video_models():
    with open(CATALOG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    models = data.get("models", data)
    return [m for m in models
            if m.get("task") == "video" and m.get("status") == "APPROVED"
            and isinstance(m.get("max_shot_seconds"), int)]


def build_card(seconds, max_shot_seconds):
    """The card the calculator builds for one ad (all lines pre-priced)."""
    norm = {
        "main_characters": ["Character 1"],
        "length_seconds": seconds,
        "shapes": ["9:16"],
        "shape_count": 1,
        "model": None,
        "music_model": "ai-music-api/generate",
        "image_model": "google/imagen4-fast",
    }
    entry = {"id": "fixture/video", "max_shot_seconds": max_shot_seconds,
             "resolution": "768P"}
    lines = {part: {"credits": 1.0, "usd": 0.04}
             for part in ("video", "music", "image")}
    return cc._build_card(norm, entry, lines, True)


class TwoDifferentFunctions(unittest.TestCase):
    def test_video_shot_count_is_ceil_length_over_model_max(self):
        self.assertEqual(cc.video_shot_count(60, 15), 4)
        self.assertEqual(cc.video_shot_count(60, 10), 6)
        self.assertEqual(cc.video_shot_count(60, 8), 8)
        self.assertEqual(cc.video_shot_count(120, 8), 15)
        self.assertEqual(cc.video_shot_count(600, 30), 20)

    def test_video_shot_count_rejects_a_non_positive_max(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError, msg=repr(bad)):
                cc.video_shot_count(60, bad)

    def test_storyboard_count_takes_no_model_max_argument(self):
        params = inspect.signature(cc.shot_count).parameters
        self.assertEqual(list(params), ["length_seconds", "cap"])

    def test_same_ad_two_numbers(self):
        # 60 s on MiniMax (15 s max shot): 4 video shots, 8 storyboard
        # pictures. The larger one is the storyboard; never the reverse sum.
        self.assertEqual(cc.shot_count(60), 8)
        self.assertEqual(cc.video_shot_count(60, 15), 4)
        self.assertNotEqual(cc.shot_count(60), cc.video_shot_count(60, 15))


class CardKeepsThemApart(unittest.TestCase):
    def test_the_card_carries_both_counts_as_separate_fields(self):
        card = build_card(60, 15)
        self.assertIn("storyboard_pictures", card)
        self.assertIn("storyboard_picture_cap", card)
        self.assertIn("shots_per_shape", card)
        self.assertEqual(card["storyboard_pictures"], 8)
        self.assertEqual(card["shots_per_shape"], 4)
        self.assertNotEqual(card["storyboard_pictures"], card["shots_per_shape"])
        self.assertEqual(card["storyboard_picture_cap"], cc.storyboard_cap())

    def test_the_card_never_shows_a_sum_of_the_two(self):
        card = build_card(180, 15)   # 36 pictures + 12 shots = 48
        self.assertEqual(card["storyboard_pictures"], 36)
        self.assertEqual(card["shots_per_shape"], 12)
        summed = 36 + 12
        self.assertFalse([v for v in card.values() if v == summed],
                         "no card field may hold the conflated sum 48")

    def test_pictures_are_at_least_the_shots_for_every_offered_length(self):
        models = approved_video_models()
        self.assertTrue(models, "shipped catalog must carry video models")
        for seconds in OFFERED_LENGTHS:
            pictures = cc.shot_count(seconds)
            for model in models:
                shots = cc.video_shot_count(seconds,
                                            model["max_shot_seconds"])
                self.assertGreaterEqual(
                    pictures, shots,
                    (seconds, model["id"], pictures, shots))

    def test_on_the_longest_ad_the_two_counts_stay_distinct(self):
        # 10-minute ad on the 8-second model: 75 video shots vs 120 pictures.
        self.assertEqual(cc.video_shot_count(600, 8), 75)
        self.assertEqual(cc.shot_count(600), 120)
        card = build_card(600, 8)
        self.assertEqual(card["shots_per_shape"], 75)
        self.assertEqual(card["storyboard_pictures"], 120)


if __name__ == "__main__":
    unittest.main(verbosity=2)
