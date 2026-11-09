#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_prompt_depth.py: the Skill 62 prompt composer (owner rule 12 and owner intent).

Rule 12: a descriptive prompt lands in 95-100 percent of the model maximum, never under 80 percent
(Skill 74 prompt-budget owns the numbers). Intent: the length must make the output better, so it is
carried by SCENE-SPECIFIC direction (the planner's ``production_direction``), not by house rules repeated
in every prompt. Covers: the band at several maxima for every section type, the negative-prompt reserve,
the no-limit and verbatim exemptions, two different scenes sharing under 50 percent of their sentences,
no sentence repeated inside one prompt, no still-image wording in clip prompts, world-neutral examples,
and the 79 / 95 / 101 percent boundaries through a real KieProvider call and Skill 74's budget math.
Run: python3 -m unittest discover -s tests/unit
"""

from __future__ import annotations

import contextlib
import io
import math
import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_SKILL_DIR = Path(__file__).resolve().parent.parent.parent
for _p in (_SKILL_DIR, _SKILL_DIR / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import plan_visual_journey as pj  # noqa: E402
from providers import base, kie  # noqa: E402
from providers import prompt_depth as pd  # noqa: E402

STYLE = {"visual_world": "a salt flat observatory", "realism_level": "photoreal", "palette": ["white", "ochre", "steel blue"],
         "material_language": "salt crust and weathered steel", "lighting_logic": "low sun from camera left",
         "lens_family": "50mm prime", "composition_system": "rule of thirds", "prohibited_styles": ["cartoon", "neon"]}
SECTIONS = ["hero", "problem", "solution", "offer", "proof", "testimonial", "pricing", "guarantee", "faq", "urgency", "cta", "close", "footer"]


def scene(section: str, index: int = 0):
    prof = pj._section_profile(section, index)
    return {
        "scene_id": f"scene-{index + 1:02d}-{section}", "page_section": section,
        "narrative_purpose": prof["narrative_purpose"], "conversion_purpose": prof["conversion_purpose"],
        "visual_motif": prof["visual_motif"],
        "camera": {k: prof[k] for k in ("start_state", "end_state", "motion_direction", "motion_speed")},
        "duration_seconds": 8.0, "crop_rules": {"desktop": "16:9 full-bleed", "mobile": "9:16 crop-safe"},
        "production_direction": pj._section_direction(section, index),
    }


def budget(mx: int):
    return {"max": mx, "floor": math.ceil(mx * 0.8), "target_min": math.ceil(mx * 0.95), "verbatim": False}


def sentences(text: str):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")) if x.strip()]


def stills(i, sec):
    return pd.fit_prompt("base prompt " + sec, pd.image_sections(STYLE, scene(sec, i)), budget(20000))


def clips(i, sec):
    return pd.fit_prompt("base prompt " + sec, pd.video_sections(STYLE, scene(sec, i)), budget(20000))


class FitPromptTests(unittest.TestCase):
    def test_lands_in_the_target_band_for_every_section_type_and_real_maxima(self) -> None:
        for i, sec in enumerate(SECTIONS):
            for sections in (pd.image_sections(STYLE, scene(sec, i)), pd.video_sections(STYLE, scene(sec, i)),
                             pd.video_sections(STYLE, scene(sec, i), scene("cta", 3))):
                for mx in (20000, 12000, 5000, 2500):
                    b = budget(mx)
                    out = pd.fit_prompt("a short base prompt", sections, b)
                    self.assertGreaterEqual(len(out), b["target_min"], (sec, mx, len(out)))
                    self.assertLessEqual(len(out), mx, (sec, mx, len(out)))

    def test_negative_prompt_reserve_is_respected(self) -> None:
        b = budget(20000)
        reserve = len(" Do not include: no AI-generated text, no watermark, no distorted anatomy, no extra limbs")
        out = pd.fit_prompt("a scene", pd.image_sections(STYLE, scene("hero")), b, reserve)
        self.assertLessEqual(len(out) + reserve, 20000)
        self.assertGreaterEqual(len(out) + reserve, b["target_min"])

    def test_no_limit_or_verbatim_leaves_the_prompt_alone(self) -> None:
        secs = pd.image_sections(STYLE, scene("hero"))
        self.assertEqual(pd.fit_prompt("a loft", secs, None), "a loft")
        self.assertEqual(pd.fit_prompt("a loft", secs, {"max": 20000, "target_min": 19000, "verbatim": True}), "a loft")

    def test_a_library_that_cannot_reach_the_floor_returns_a_short_prompt_for_the_provider_to_refuse(self) -> None:
        out = pd.fit_prompt("a loft", pd.image_sections(STYLE, scene("hero")), budget(200000))
        self.assertLess(len(out), 0.8 * 200000)


class SceneSpecificLengthTests(unittest.TestCase):
    """The length is carried by what is true of each scene, not by repeated house rules."""

    def test_two_different_scenes_share_under_half_of_their_sentences(self) -> None:
        for make in (stills, clips):
            prompts = {sec: sentences(make(i, sec)) for i, sec in enumerate(SECTIONS)}
            keys = list(prompts)
            for a in range(len(keys)):
                for b in range(a + 1, len(keys)):
                    pa, pb = prompts[keys[a]], prompts[keys[b]]
                    shared = len(set(pa) & set(pb))
                    self.assertLess(shared / len(pa), 0.5, (make.__name__, keys[a], keys[b], shared, len(pa)))
                    self.assertLess(shared / len(pb), 0.5, (make.__name__, keys[a], keys[b], shared, len(pb)))

    def test_most_of_each_prompt_is_scene_specific_by_characters(self) -> None:
        for make in (stills, clips):
            a, b = sentences(make(0, "hero")), sentences(make(1, "problem"))
            shared = set(a) & set(b)
            share_chars = sum(len(x) for x in a if x in shared) / sum(len(x) for x in a)
            self.assertLess(share_chars, 0.5, (make.__name__, share_chars))

    def test_no_sentence_repeats_inside_one_prompt(self) -> None:
        for make in (stills, clips):
            for i, sec in enumerate(SECTIONS):
                s = sentences(make(i, sec))
                self.assertEqual(len(s), len(set(s)), (make.__name__, sec))
        connector = pd.fit_prompt("base", pd.video_sections(STYLE, scene("problem", 1), scene("solution", 2)), budget(20000))
        self.assertEqual(len(sentences(connector)), len(set(sentences(connector))))

    def test_direction_is_distinct_per_section_in_the_planner(self) -> None:
        for field in ("subject", "setting", "light", "materials", "motion", "camera_blocking", "mood", "continuity", "time_of_day"):
            values = [pj._section_direction(sec, i)[field] for i, sec in enumerate(SECTIONS)]
            self.assertEqual(len(values), len(set(values)), field)

    def test_the_scene_fields_really_appear_in_the_prompt(self) -> None:
        sc = scene("proof", 4)
        text = stills(4, "proof")
        for field in ("subject", "setting", "light", "materials", "mood", "continuity"):
            self.assertIn(sc["production_direction"][field], text, field)
        self.assertIn("16:9 full-bleed", text)
        self.assertIn(sc["narrative_purpose"], text)

    def test_a_planner_scene_without_direction_still_expands_with_neutral_defaults(self) -> None:
        sc = scene("hero")
        sc.pop("production_direction")
        out = pd.fit_prompt("base", pd.image_sections(STYLE, sc), budget(20000))
        self.assertGreaterEqual(len(out), 16000)  # the 80 percent floor is still met from the neutral defaults
        self.assertNotIn("{", out)


def _no_direction(sec: str, i: int):
    sc = scene(sec, i)
    sc.pop("production_direction")
    return sc


def _operator_direction(sec: str, i: int):
    """An operator-written direction: 60 to 90 characters per field."""
    sc = scene(sec, i)
    sc["production_direction"] = {k: v[:75].rsplit(" ", 1)[0] for k, v in sc["production_direction"].items()}
    return sc


def _four_word_direction(sec: str, i: int):
    """The shortest plausible direction: four words per field."""
    sc = scene(sec, i)
    sc["production_direction"] = {k: " ".join(v.split()[:4]) for k, v in sc["production_direction"].items()}
    return sc


MAXIMA = (20000, 12000, 8000, 5000, 2500, 1000)


class BandForEveryInputShapeTests(unittest.TestCase):
    """Rule 12 is a 95 to 100 percent target, not just the 80 percent floor, for ANY direction shape and ANY model maximum:
    a project-level still with no scene (concept board, anchor), a scene with no direction, concise 60 to 90 character
    operator direction, four-word direction, and full planner direction; stills and clips; six maxima."""

    def _check(self, sections, label):
        for mx in MAXIMA:
            with self.subTest(label=label, max=mx):
                b = budget(mx)
                out = pd.fit_prompt("base prompt text", sections, b)
                self.assertGreaterEqual(len(out), 0.95 * mx, (label, mx, len(out)))
                self.assertLessEqual(len(out), mx, (label, mx, len(out)))

    def test_stills_and_clips_reach_95_percent_without_a_scene(self) -> None:
        self._check(pd.image_sections(STYLE), "still, no scene")
        self._check(pd.video_sections(STYLE), "clip, no scene")

    def test_stills_and_clips_reach_95_percent_for_every_direction_shape(self) -> None:
        shapes = (("full", scene), ("none", _no_direction), ("concise", _operator_direction), ("four words", _four_word_direction))
        for name, make in shapes:
            for i, sec in enumerate(SECTIONS):
                self._check(pd.image_sections(STYLE, make(sec, i)), f"still, {name}, {sec}")
                self._check(pd.video_sections(STYLE, make(sec, i)), f"clip, {name}, {sec}")
                self._check(pd.video_sections(STYLE, make(sec, i), scene("cta", 3)), f"connector, {name}, {sec}")

    def test_the_project_level_anchor_uses_the_first_scene_of_the_plan(self) -> None:
        import generate_images as gi

        class FakeState:
            def exists(self, kind):
                return kind == "scene-plan"

            def load(self, kind):
                return {"scenes": [scene("hero", 0), scene("problem", 1)]}

        self.assertEqual(gi._anchor_scene(FakeState())["page_section"], "hero")

        class NoPlan:
            def exists(self, kind):
                return False

        self.assertIsNone(gi._anchor_scene(NoPlan()))


class MediumAndWorldTests(unittest.TestCase):
    def test_clip_prompts_never_say_image_and_still_prompts_never_say_clip(self) -> None:
        for i, sec in enumerate(SECTIONS):
            text = "\n".join(pd.video_sections(STYLE, scene(sec, i)) + pd.video_sections(STYLE, scene(sec, i), scene("cta", 3)))
            self.assertIsNone(re.search(r"\bimages?\b|\bimagery\b|\bphotograph|\bthumbnail", text, re.I), (sec, re.search(r"\bimages?\b|\bimagery\b|\bphotograph|\bthumbnail", text, re.I)))
            still = "\n".join(pd.image_sections(STYLE, scene(sec, i)))
            self.assertIsNone(re.search(r"\bclip\b|\bvideo\b", still, re.I), sec)

    def test_no_indoor_domestic_examples_in_an_outdoor_world(self) -> None:
        banned = re.compile(r"\b(drawer|light switch|coat|chair|cup|lamp|sofa|desk|furniture|kitchen|bedroom|room|window|shelf|shelves)\b", re.I)
        for i, sec in enumerate(SECTIONS):
            text = "\n".join(pd.image_sections(STYLE, scene(sec, i)) + pd.video_sections(STYLE, scene(sec, i)))
            self.assertIsNone(banned.search(text), (sec, banned.search(text)))

    def test_no_outdoor_wording_in_an_indoor_world(self) -> None:
        indoor = dict(STYLE, visual_world="a family bakery kitchen at the back of a shop", palette=["flour white", "copper", "walnut"],
                      material_language="stainless steel, flour dust and warm wood", lighting_logic="a warm overhead pendant with a window fill")
        banned = re.compile(r"\b(sky|skies|horizons?|vegetation|weather|foliage|clouds?|breeze|outdoors?)\b", re.I)
        for i, sec in enumerate(SECTIONS):
            text = "\n".join(pd.image_sections(indoor, scene(sec, i)) + pd.video_sections(indoor, scene(sec, i)) + pd.video_sections(indoor, scene(sec, i), scene("cta", 3)))
            self.assertIsNone(banned.search(text), (sec, banned.search(text)))

    def test_planner_defaults_respect_an_indoor_world(self) -> None:
        """The planner's defaults must not smuggle in a time of day or a place type that the world may not have."""
        banned = re.compile(r"\b(sunrise|sunsets?|architecture|landscapes?|daylight|dawn|dusk|midday|(?:mid-|late-)?(?:morning|afternoon)|skies|sky|horizons?)\b", re.I)
        indoor = dict(STYLE, visual_world="a family bakery kitchen at the back of a shop", lighting_logic="a warm overhead pendant")
        for i, sec in enumerate(SECTIONS + ["a custom section"]):
            direction = pj._section_direction(sec, i)
            self.assertIsNone(banned.search(" ".join(direction.values())), (sec, direction))
            sc = scene(sec, i)
            sc["production_direction"] = direction
            text = "\n".join(pd.image_sections(indoor, sc) + pd.video_sections(indoor, sc))
            self.assertIsNone(banned.search(text), (sec, banned.search(text)))

    def test_the_setting_is_not_pasted_more_than_twice_per_paragraph(self) -> None:
        for i, sec in enumerate(SECTIONS):
            sc = scene(sec, i)
            pdir = sc["production_direction"]
            for text in (stills(i, sec), clips(i, sec)):
                for paragraph in text.split("\n\n"):
                    self.assertLessEqual(paragraph.count(pdir["setting"]), 2, (sec, paragraph[:80]))
                    self.assertLessEqual(paragraph.count(pdir["subject"]), 3, (sec, paragraph[:80]))

    def test_connector_names_both_scenes(self) -> None:
        a, b = scene("problem", 1), scene("solution", 2)
        text = "\n".join(pd.video_sections(STYLE, a, b))
        self.assertIn(a["production_direction"]["subject"], text)
        self.assertIn(b["production_direction"]["subject"], text)
        self.assertIn(b["production_direction"]["light"], text)


class BoundariesThroughARealProviderTests(unittest.TestCase):
    """79 percent is refused with the characters to add, 95 passes, 101 is refused with the characters to cut: a real
    KieProvider call through the real Skill 74 prompt-budget math (20000 maximum from the fixture schema)."""

    def setUp(self) -> None:
        sys.path.insert(0, str(_SKILL_DIR / "scripts"))
        import generate_images as gi
        self.bodies = []

        class Spy(gi.FixtureKieTransport):
            def post_json(inner, url, **kw):  # noqa: N805
                if url.endswith("/createTask"):
                    self.bodies.append(kw["body"])
                return super().post_json(url, **kw)

        self.env = patch.dict(os.environ, {"KIE_API_KEY": "FIXTURE-KEY", "KIE_POLICY_ROOT": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        quiet = contextlib.redirect_stderr(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)
        self.provider = kie.KieProvider(transport=Spy())
        self.mid = "kie-gpt-image-2-5-sunburst-text-to-image"

    def go(self, n: int):
        return self.provider.generate_image(base.ImageGenerationRequest(model_id=self.mid, prompt="x" * n))

    def test_budget_numbers_come_from_skill74(self) -> None:
        b = self.provider.prompt_budget(self.mid)
        self.assertEqual((b["max"], b["floor"], b["target_min"]), (20000, 16000, 19000))

    def test_79_percent_refused_with_the_characters_to_add(self) -> None:
        with self.assertRaises(base.ProviderTaskError) as ctx:
            self.go(15800)
        self.assertIn("ADD at least 200", str(ctx.exception))
        self.assertEqual(self.bodies, [])

    def test_80_95_and_100_percent_pass(self) -> None:
        for n in (16000, 19000, 20000):
            self.go(n)
        self.assertEqual([len(b["input"]["prompt"]) for b in self.bodies], [16000, 19000, 20000])

    def test_101_percent_refused_with_the_characters_to_cut(self) -> None:
        with self.assertRaises(base.ProviderTaskError) as ctx:
            self.go(20200)
        self.assertIn("CUT exactly 200", str(ctx.exception))
        self.assertEqual(self.bodies, [])

    def test_the_real_pipeline_templates_are_refused_bare_and_accepted_expanded(self) -> None:
        import generate_images as gi
        import generate_videos as gv
        sc, nxt = scene("proof", 4), scene("cta", 5)
        bare = gi._scene_anchor_prompt(STYLE, sc)
        with self.assertRaises(base.ProviderTaskError):
            self.go_prompt(bare)
        full = pd.fit_prompt(bare, pd.image_sections(STYLE, sc), self.provider.prompt_budget(self.mid))
        self.go_prompt(full)
        self.assertTrue(19000 <= len(self.bodies[-1]["input"]["prompt"]) <= 20000)
        mid = "kie-bytedance-seedance-1.5-pro"
        for text, secs in ((gv._final_scene_prompt(STYLE, sc), pd.video_sections(STYLE, sc)),
                           (gv._connector_prompt(STYLE, sc, nxt), pd.video_sections(STYLE, sc, nxt))):
            mk = lambda p: self.provider.generate_video(base.VideoGenerationRequest(model_id=mid, prompt=p, duration_seconds=8))
            with self.assertRaises(base.ProviderTaskError):
                mk(text)
            mk(pd.fit_prompt(text, secs, self.provider.prompt_budget(mid)))
            self.assertTrue(19000 <= len(self.bodies[-1]["input"]["prompt"]) <= 20000)

    def go_prompt(self, p: str):
        return self.provider.generate_image(base.ImageGenerationRequest(model_id=self.mid, prompt=p))


if __name__ == "__main__":
    unittest.main()
