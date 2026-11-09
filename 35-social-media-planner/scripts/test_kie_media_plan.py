#!/usr/bin/env python3
"""Offline tests for kie_media_plan.py (Skill 35 KIE media plan). No network."""
import json
import tempfile
import unittest
from pathlib import Path

import kie_media_plan as kmp

SUN = "gpt-image-2-5-sunburst-text-to-image"


def plan(image=None, video=None):
    with tempfile.TemporaryDirectory() as d:
        ip = vp = None
        if image is not None:
            ip = str(Path(d) / "image-model.json"); Path(ip).write_text(json.dumps(image))
        if video is not None:
            vp = str(Path(d) / "video-specs.json"); Path(vp).write_text(json.dumps(video))
        return kmp.build_plan(ip, vp, d, d)


class MediaPlanTests(unittest.TestCase):
    def test_no_config_defaults_to_sunburst(self):
        p = plan()
        self.assertEqual(p["image"]["text_to_image"], SUN)
        self.assertEqual(p["violations"], [])

    def test_non_gpt_image_models_are_ignored_and_reported(self):
        for bad in ("nano-banana-pro", "google/nano-banana", "midjourney-v7", "ideogram/v3-text-to-image",
                    "gpt-image-2-text-to-image", "gpt-image-1-5-text-to-image", "gpt-image-2-5-flare-text-to-image"):
            p = plan(image={"model": bad})
            self.assertEqual(p["image"]["text_to_image"], SUN, bad)
            self.assertEqual(len(p["violations"]), 1, bad)

    def test_newer_gpt_image_generation_is_accepted(self):
        p = plan(image={"image_model": "gpt-image-3-sunburst-text-to-image"})
        self.assertEqual(p["image"]["text_to_image"], "gpt-image-3-sunburst-text-to-image")
        self.assertEqual(p["image"]["image_to_image"], "gpt-image-3-sunburst-image-to-image")
        self.assertEqual(p["violations"], [])

    def test_nested_banned_models_are_found_at_any_depth(self):
        p = plan(video={"width": 1080, "clips": [{"engine": {"name": "OpenAI/Sora-2"}}]},
                 image={"model": SUN, "fallbacks": {"alt": ["Midjourney-v7"]}, "Ideogram": 1})
        got = sorted((v["file"], v["path"]) for v in p["violations"])
        self.assertEqual(got, [("image-model.json", "Ideogram"), ("image-model.json", "fallbacks.alt[0]"),
                               ("video-specs.json", "clips[0].engine.name")])
        self.assertEqual(p["image"]["text_to_image"], SUN)

    def test_sora_in_video_specs_is_reported_and_routed_to_67(self):
        p = plan(video={"video_model": "OpenAI/Sora-2"})
        self.assertEqual(p["video"]["owner"], "67-kie-video")
        self.assertEqual([v["file"] for v in p["violations"]], ["video-specs.json"])

    def test_plan_holds_no_price_or_length_numbers(self):
        blob = json.dumps(plan())
        for word in ("credits", "$", "9000", "19000", "20000"):
            self.assertNotIn(word, blob)

    def test_unreadable_config_is_noted_not_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "image-model.json"; f.write_text("{not json")
            p = kmp.build_plan(str(f), None, d, d)
            self.assertEqual(p["image"]["text_to_image"], SUN)
            self.assertIn("unreadable", p["image"]["config_note"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
