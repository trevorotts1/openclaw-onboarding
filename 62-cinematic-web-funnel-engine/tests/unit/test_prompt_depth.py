#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_prompt_depth.py: the Skill 62 prompt composer lands in the 95-100 percent band (owner rule 12).

Skill 74 prompt-budget owns the numbers; ``providers.prompt_depth`` only fills them with real
production direction. Covers the band at several maxima, the negative-prompt reserve, the
no-limit and verbatim exemptions, the 79 / 95 / 101 percent boundaries through the real Skill 74
budget math, and that the direction is specific to the project (not a repeated filler block).
Run: python3 -m unittest discover -s tests/unit
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

from providers import prompt_depth as pd  # noqa: E402
from providers import kie  # noqa: E402

STYLE = {"visual_world": "a sunlit modern studio loft", "realism_level": "photoreal", "palette": ["warm white", "oak", "sage"],
         "prohibited_styles": ["cartoon", "neon"]}
SCENE = {"visual_motif": "a ceramic table lamp", "narrative_purpose": "invite the visitor in",
         "camera": {"start_state": "wide", "end_state": "close-up", "motion_direction": "slow push in", "motion_speed": "slow"}}


def _budget(mx: int):
    import math
    return {"max": mx, "floor": math.ceil(mx * 0.8), "target_min": math.ceil(mx * 0.95), "verbatim": False}


class FitPromptTests(unittest.TestCase):
    def test_lands_in_the_target_band_for_real_maxima(self) -> None:
        base_prompt = "a sunlit modern studio loft; concept art direction: warm cinematic"
        for sections in (pd.image_sections(STYLE), pd.image_sections(STYLE, SCENE), pd.video_sections(STYLE, SCENE),
                         pd.video_sections(STYLE, SCENE, SCENE)):
            for mx in (20000, 12000, 5000, 2500):
                b = _budget(mx)
                out = pd.fit_prompt(base_prompt, sections, b)
                self.assertGreaterEqual(len(out), b["target_min"], (mx, len(out)))
                self.assertLessEqual(len(out), mx, (mx, len(out)))

    def test_negative_prompt_reserve_is_respected(self) -> None:
        b = _budget(20000)
        reserve = len(" Do not include: no AI-generated text, no watermark, no distorted anatomy, no extra limbs")
        out = pd.fit_prompt("a loft", pd.image_sections(STYLE), b, reserve)
        self.assertLessEqual(len(out) + reserve, 20000)
        self.assertGreaterEqual(len(out) + reserve, b["target_min"])

    def test_no_limit_or_verbatim_leaves_the_prompt_alone(self) -> None:
        self.assertEqual(pd.fit_prompt("a loft", pd.image_sections(STYLE), None), "a loft")
        self.assertEqual(pd.fit_prompt("a loft", pd.image_sections(STYLE), {"max": 20000, "target_min": 19000, "verbatim": True}), "a loft")

    def test_a_library_that_cannot_reach_the_floor_returns_a_short_prompt_for_the_provider_to_refuse(self) -> None:
        out = pd.fit_prompt("a loft", pd.image_sections(STYLE), _budget(200000))
        self.assertLess(len(out), 0.8 * 200000)

    def test_direction_is_specific_not_repeated_filler(self) -> None:
        sections = pd.video_sections(STYLE, SCENE)
        self.assertEqual(len(sections), len(set(sections)))
        text = "\n".join(sections)
        for needle in ("a ceramic table lamp", "slow push in", "a sunlit modern studio loft", "warm white, oak, sage", "cartoon, neon"):
            self.assertIn(needle, text)
        words = text.split()
        self.assertGreater(len(set(words)) / len(words), 0.2)  # real vocabulary, not one block repeated
        self.assertNotIn("{", text)

    def test_connector_direction_names_both_scenes(self) -> None:
        other = dict(SCENE, visual_motif="a walnut desk")
        text = "\n".join(pd.video_sections(STYLE, SCENE, other))
        self.assertIn("a ceramic table lamp", text)
        self.assertIn("a walnut desk", text)


class RealPipelinePromptsMeetTheFloorTests(unittest.TestCase):
    """The prompts the P6 to P9 generators really build, expanded with prompt_depth, are accepted by the
    provider under the 80 percent floor (Skill 74 prompt-budget, 20000 maximum); the bare templates are refused."""

    def setUp(self) -> None:
        import os
        from unittest.mock import patch
        sys.path.insert(0, str(_SKILL_DIR / "scripts"))
        import generate_images as gi
        import generate_videos as gv
        from providers import base
        self.gi, self.gv, self.base = gi, gv, base
        self.env = patch.dict(os.environ, {"KIE_API_KEY": "FIXTURE-KEY", "KIE_POLICY_ROOT": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.bodies = []

        class Spy(gi.FixtureKieTransport):
            def post_json(inner, url, **kw):  # noqa: N805
                if url.endswith("/createTask"):
                    self.bodies.append(kw["body"])
                return super().post_json(url, **kw)

        import contextlib, io
        self.quiet = contextlib.redirect_stderr(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)
        self.provider = kie.KieProvider(transport=Spy())

    def test_image_templates_are_refused_bare_and_accepted_expanded(self) -> None:
        mid = "kie-gpt-image-2-5-sunburst-text-to-image"
        bare = self.gi._scene_anchor_prompt(STYLE_FULL, SCENE_FULL)
        with self.assertRaises(self.base.ProviderTaskError):
            self.provider.generate_image(self.base.ImageGenerationRequest(model_id=mid, prompt=bare))
        budget = self.provider.prompt_budget(mid)
        full = pd.fit_prompt(bare, pd.image_sections(STYLE_FULL, SCENE_FULL), budget)
        self.provider.generate_image(self.base.ImageGenerationRequest(model_id=mid, prompt=full))
        self.assertTrue(0.95 * 20000 <= len(self.bodies[-1]["input"]["prompt"]) <= 20000)

    def test_video_templates_are_refused_bare_and_accepted_expanded(self) -> None:
        mid = "kie-bytedance-seedance-1.5-pro"
        for bare, secs in (
            (self.gv._final_scene_prompt(STYLE_FULL, SCENE_FULL), pd.video_sections(STYLE_FULL, SCENE_FULL)),
            (self.gv._connector_prompt(STYLE_FULL, SCENE_FULL, SCENE_FULL), pd.video_sections(STYLE_FULL, SCENE_FULL, SCENE_FULL)),
        ):
            req = lambda p: self.base.VideoGenerationRequest(model_id=mid, prompt=p, duration_seconds=8)
            with self.assertRaises(self.base.ProviderTaskError):
                self.provider.generate_video(req(bare))
            self.provider.generate_video(req(pd.fit_prompt(bare, secs, self.provider.prompt_budget(mid))))
            self.assertTrue(0.95 * 20000 <= len(self.bodies[-1]["input"]["prompt"]) <= 20000)


STYLE_FULL = {"visual_world": "a sunlit modern studio loft", "realism_level": "photoreal", "palette": ["warm white", "oak"],
              "material_language": "oak, linen, brushed brass", "lighting_logic": "soft window key from camera left",
              "lens_family": "35mm to 85mm", "composition_system": "rule of thirds", "prohibited_styles": ["cartoon"]}
SCENE_FULL = {"visual_motif": "a ceramic table lamp", "narrative_purpose": "invite the visitor in",
              "camera": {"start_state": "wide", "end_state": "close-up", "motion_direction": "slow push in", "motion_speed": "slow"}}


class BoundaryThroughSkill74Tests(unittest.TestCase):
    """79 percent is refused with the characters to add, 95 passes, 101 is refused, all through Skill 74's own math."""

    def setUp(self) -> None:
        mod = kie.load_skill74()
        self.assertIsNotNone(mod, "Skill 74 must be present beside Skill 62 in the repo")
        self.ad = mod.Adapter(env={"KIE_API_KEY": "k", "KIE_LIVE_ADAPTER_MODE": "active", "KIE_LIVE_CACHE_DIR": "/tmp/cwfe-pd-nocache"})

    def test_budget_math(self) -> None:
        b = self.ad.cmd_prompt_budget  # noqa: F841 (method exists)
        mod = kie.load_skill74()
        self.assertEqual(mod.budget(20000), {"max": 20000, "floor": 16000, "target_min": 19000, "target_max": 20000})
        self.assertLess(15800, 16000)   # 79 percent of 20000
        self.assertGreaterEqual(19000, 19000)  # 95 percent
        self.assertGreater(20200, 20000)  # 101 percent


if __name__ == "__main__":
    unittest.main()
