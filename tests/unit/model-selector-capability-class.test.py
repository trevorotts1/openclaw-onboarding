#!/usr/bin/env python3
"""
Unit tests for the Capability-Class Model-Selection Framework layer.

Covers the NEW layer that sits ABOVE the existing select_model.py tier system:
  - shared-utils/model_selector.py :: infer_class
        capability-class inference (HEAVY-REASONING / WRITING / JUDGMENT /
        MECHANICAL / CONVERSATIONAL / GENERATION) + VISION additive flag, across
        the three inference layers (explicit override / keyword / dept backstop)
        and the generation-pipeline short-circuit.
  - shared-utils/model_selector.py :: resolve_model_for_role
        full resolution: GENERATION roles return a fixed pipeline (NO LLM);
        text/vision roles resolve a concrete model from a passed inventory via
        select_model.py's cascade; missing inventory surfaces needs_owner_input.
  - shared-utils/select_model.py :: capabilities_for_model
        the HARDENED unknown-generation gate — an UNKNOWN model id whose name
        carries a generation hint (image|img|flux|sora|dalle|diffusion|video|
        veo|tts|whisper|audio-gen|gpt-image) must report text_ok=False so it can
        NEVER be selected for an LLM role.

Run:
    python3 tests/unit/model-selector-capability-class.test.py
    or: pytest tests/unit/model-selector-capability-class.test.py
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate shared-utils (works from any cwd inside the repo)
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent            # tests/unit/
_REPO_ROOT = _HERE.parent.parent         # repo root
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
assert _SHARED_UTILS.is_dir(), f"shared-utils not found at {_SHARED_UTILS}"
sys.path.insert(0, str(_SHARED_UTILS))


def _load(modname, filename):
    spec = importlib.util.spec_from_file_location(modname, _SHARED_UTILS / filename)
    assert spec is not None and spec.loader is not None, f"cannot load {filename}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


ms = _load("model_selector", "model_selector.py")
sm = _load("select_model", "select_model.py")


# Representative client inventory (mirrors model_selector.TREVOR_LINEUP shape).
INV_FULL = [
    "ollama/deepseek-v4-pro:cloud",          # T1 heavy text
    "ollama/kimi-k2.6:cloud",                # T1 heavy text
    "ollama/minimax-m1:cloud",               # T1 mid text
    "ollama/deepseek-v4-flash:cloud",        # T1 fast text
    "openrouter/qwen/qwen3-vl:235b",         # T2 vision
    "openrouter/z-ai/glm-4.5",               # T2 mid text
    "openrouter/free",                       # T3 free
]
INV_NO_VISION = [
    "ollama/deepseek-v4-pro:cloud",
    "ollama/deepseek-v4-flash:cloud",
    "openrouter/free",
]


# ---------------------------------------------------------------------------
# infer_class — capability-class inference (the NEW layer's brain)
# ---------------------------------------------------------------------------
class TestInferClass(unittest.TestCase):
    def test_explicit_override_heavy(self):
        info = ms.infer_class("master-orchestrator", "master-orchestrator")
        self.assertEqual(info["capability_class"], ms.CLASS_HEAVY)
        self.assertEqual(info["inference_layer"], "explicit_override")
        self.assertEqual(info["purpose_tier"], "heavy")

    def test_explicit_override_strips_role_prefix(self):
        # the ROLE-- prefix must be normalized away before override lookup
        info = ms.infer_class("ROLE--style-analyst", "graphics")
        self.assertEqual(info["capability_class"], ms.CLASS_HEAVY)

    def test_keyword_writing(self):
        info = ms.infer_class("sop-writer", "audio")
        self.assertEqual(info["capability_class"], ms.CLASS_WRITING)
        self.assertEqual(info["purpose_tier"], "mid")

    def test_keyword_judgment(self):
        info = ms.infer_class("qc-specialist-audio", "audio")
        self.assertEqual(info["capability_class"], ms.CLASS_JUDGMENT)

    def test_keyword_mechanical(self):
        info = ms.infer_class("transcription-specialist", "audio")
        self.assertEqual(info["capability_class"], ms.CLASS_MECHANICAL)
        self.assertEqual(info["purpose_tier"], "fast")

    def test_keyword_conversational(self):
        info = ms.infer_class("appointment-setter", "sales")
        self.assertEqual(info["capability_class"], ms.CLASS_CONVERSATIONAL)

    def test_generation_pipeline_shortcircuits_to_no_llm(self):
        info = ms.infer_class("ai-image-generator-specialist", "graphics")
        self.assertEqual(info["capability_class"], ms.CLASS_GENERATION)
        # GENERATION carries NO LLM tier and a fixed pipeline target
        self.assertIsNone(info["purpose_tier"])
        self.assertTrue(info["generation_pipeline"])
        self.assertEqual(info["inference_layer"], "generation_pipeline")
        # GENERATION never carries a vision flag (it is an output, not input)
        self.assertFalse(info["vision_flag"])

    def test_vision_flag_on_graphics_role(self):
        info = ms.infer_class("fidelity-tester", "graphics")
        self.assertTrue(info["vision_flag"])
        self.assertEqual(info["required_modality"], "vision")

    def test_dept_backstop_when_no_match(self):
        # a slug that hits neither an override nor a keyword rule falls to the
        # dept backstop — but ALWAYS resolves to a real class (no blind default).
        info = ms.infer_class("zzz-unmatched-role", "marketing")
        self.assertIn(info["capability_class"], (
            ms.CLASS_HEAVY, ms.CLASS_WRITING, ms.CLASS_JUDGMENT,
            ms.CLASS_MECHANICAL, ms.CLASS_CONVERSATIONAL,
        ))
        self.assertEqual(info["inference_layer"], "dept_backstop")


# ---------------------------------------------------------------------------
# resolve_model_for_role — full resolution (class -> concrete model)
# ---------------------------------------------------------------------------
class TestResolveModelForRole(unittest.TestCase):
    def test_generation_role_returns_pipeline_not_llm(self):
        r = ms.resolve_model_for_role(
            "ai-image-generator-specialist", "graphics", inventory=INV_FULL)
        self.assertEqual(r["capability_class"], ms.CLASS_GENERATION)
        # the resolved target is the fixed pipeline, NOT any LLM in inventory
        self.assertEqual(r["model_id"], r["generation_pipeline"])
        self.assertTrue(r["model_id"])
        # it must not be one of the text LLMs in inventory
        self.assertNotIn(r["model_id"], INV_FULL)

    def test_heavy_role_resolves_tier1_text_model(self):
        r = ms.resolve_model_for_role(
            "master-orchestrator", "master-orchestrator", inventory=INV_FULL)
        self.assertEqual(r["capability_class"], ms.CLASS_HEAVY)
        self.assertTrue(r["model_id"])
        # a HEAVY text role must resolve to a real LLM (text-capable), not a
        # generation pipeline and not the free sentinel.
        self.assertIn("text", sm.capabilities_for_model(r["model_id"]))
        self.assertNotIn(r["model_id"], sm.FREE_SENTINELS)

    def test_vision_role_resolves_vision_model(self):
        r = ms.resolve_model_for_role(
            "fidelity-tester", "graphics", inventory=INV_FULL)
        self.assertTrue(r["vision_flag"])
        self.assertEqual(r["required_modality"], "vision")
        self.assertTrue(r["model_id"])
        self.assertIn("vision", sm.capabilities_for_model(r["model_id"]))

    def test_vision_role_surfaces_owner_input_when_no_vision_model(self):
        # text-only inventory + a vision role => never silently pick a text
        # model; surface needs_owner_input instead.
        r = ms.resolve_model_for_role(
            "fidelity-tester", "graphics", inventory=INV_NO_VISION)
        self.assertTrue(r["needs_owner_input"])
        self.assertIsNone(r["model_id"])

    def test_mechanical_role_resolves_fast_text_model(self):
        r = ms.resolve_model_for_role(
            "transcription-specialist", "audio", inventory=INV_FULL)
        self.assertEqual(r["capability_class"], ms.CLASS_MECHANICAL)
        self.assertTrue(r["model_id"])
        self.assertIn("text", sm.capabilities_for_model(r["model_id"]))


# ---------------------------------------------------------------------------
# capabilities_for_model — the HARDENED unknown-generation gate (Task 2)
# ---------------------------------------------------------------------------
class TestUnknownGenerationGate(unittest.TestCase):
    """An UNKNOWN model id with a generation hint must report text_ok=False."""

    # Adversarial cases: brand-new generation models matching no known family.
    UNKNOWN_GENERATION_IDS = [
        "replicate/flux-pro-1.1",        # flux -> image_generation
        "fal/sora-2-hd",                 # sora -> video_generation
        "somevendor/img-gen-xl",         # img -> image_generation
        "newco/awesome-image-maker",     # image -> image_generation
        "labs/stable-diffusion-xl-turbo-experimental",  # diffusion -> image
        "vendor/veo-4-ultra",            # veo -> video_generation
        "x/dalle-4-preview",             # dalle -> image_generation
        "y/whisper-large-v4",            # whisper -> audio_transcription
        "z/super-tts-engine",            # tts -> audio_generation
        "q/audio-gen-pro",               # audio-gen -> audio_generation
        "openai/gpt-image-99",           # gpt-image -> image_generation
    ]

    def test_unknown_generation_ids_are_never_text(self):
        for mid in self.UNKNOWN_GENERATION_IDS:
            caps = sm.capabilities_for_model(mid)
            self.assertNotIn(
                "text", caps,
                f"{mid!r} matched no family yet reported text_ok=True: {caps}")
            # model_has_modality(..., 'text') must be False -> ineligible as LLM
            self.assertFalse(
                sm.model_has_modality(mid, "text"),
                f"{mid!r} must not satisfy a text modality requirement")

    def test_unknown_generation_ids_report_a_generation_modality(self):
        # each must report its OUTPUT modality (so it can still be selected for
        # the matching generation task, just never for a text LLM role).
        expected = {
            "replicate/flux-pro-1.1": "image_generation",
            "fal/sora-2-hd": "video_generation",
            "y/whisper-large-v4": "audio_transcription",
            "z/super-tts-engine": "audio_generation",
        }
        for mid, modality in expected.items():
            caps = sm.capabilities_for_model(mid)
            self.assertIn(modality, caps, f"{mid!r} -> {caps} missing {modality}")

    def test_unknown_generation_model_never_selected_for_text_role(self):
        # END-TO-END: a HEAVY text role with ONLY an unknown image model present
        # must NOT pick it — it surfaces needs_owner_input instead of an LLM
        # backed by an image generator.
        r = ms.resolve_model_for_role(
            "master-orchestrator", "master-orchestrator",
            inventory=["somevendor/img-gen-xl"])
        self.assertNotEqual(r["model_id"], "somevendor/img-gen-xl")
        self.assertTrue(r["needs_owner_input"])
        self.assertIsNone(r["model_id"])

    def test_recognized_text_models_unaffected(self):
        # the gate must NOT disturb recognized text LLMs.
        for mid in ("ollama/deepseek-v4-pro:cloud",
                    "ollama/kimi-k2.6:cloud",
                    "openrouter/z-ai/glm-4.5"):
            self.assertIn("text", sm.capabilities_for_model(mid),
                          f"{mid!r} lost its text capability")
            self.assertTrue(sm.model_has_modality(mid, "text"))

    def test_known_generation_families_still_classified(self):
        # known families (gpt-image, flux, veo, whisper, tts) keep their declared
        # capabilities and remain non-text.
        self.assertIn("image_generation", sm.capabilities_for_model("kie-ai/gpt-image-2"))
        self.assertIn("video_generation", sm.capabilities_for_model("google/veo-3"))
        self.assertIn("audio_transcription", sm.capabilities_for_model("openai/whisper-3"))
        self.assertFalse(sm.model_has_modality("kie-ai/gpt-image-2", "text"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
