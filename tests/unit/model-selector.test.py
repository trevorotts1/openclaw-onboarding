#!/usr/bin/env python3
"""
Unit tests for the Intelligent Model Selector — shared-utils/select_model.py
(task-time selector + cascade + modality) and shared-utils/assert_model_sovereignty.py
(the AF-MODEL-SOVEREIGNTY gate).

Covers the four mandated invariants (PLAN.md §4–§7):
  1. CASCADE ORDER     — Ollama Cloud (T1) beats OpenRouter open-source (T2) beats free (T3)
  2. MODALITY MATCH    — a vision task MUST get a vision-capable model; text-only never eligible
  3. SOP OVERRIDE      — a valid SOP pin wins; an invalid SOP pin surfaces (never silent free)
  4. NO-MODEL REJECTED — the free sentinel / null / forbidden / wrong-modality is BLOCKED by the gate

Run:
    python3 tests/unit/model-selector.test.py
    or: pytest tests/unit/model-selector.test.py
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


sm = _load("select_model", "select_model.py")
gate = _load("assert_model_sovereignty", "assert_model_sovereignty.py")


# Representative client inventories used across tests.
INV_FULL = [
    "ollama/deepseek-v4-pro:cloud",      # T1 heavy text
    "ollama/kimi-k2.7:cloud",            # T1 heavy text (higher kimi version)
    "ollama/kimi-k2.6:cloud",            # T1 heavy text (lower kimi version)
    "ollama/qwen3-vl:235b-cloud",        # T1 vision
    "openrouter/deepseek/deepseek-v4-pro",  # T2 OSS heavy text
    "openrouter/free",                   # T3 free
]
INV_NO_VISION = [
    "ollama/deepseek-v4-pro:cloud",
    "openrouter/deepseek/deepseek-v4-pro",
    "openrouter/free",
]


class TestTierClassification(unittest.TestCase):
    def test_ollama_cloud_is_tier1(self):
        self.assertEqual(sm.tier_of_model("ollama/deepseek-v4-pro:cloud"), 1)
        # compound cloud tag (size + cloud) must still classify as T1
        self.assertEqual(sm.tier_of_model("ollama/qwen3-vl:235b-cloud"), 1)

    def test_openrouter_oss_is_tier2(self):
        self.assertEqual(sm.tier_of_model("openrouter/deepseek/deepseek-v4-pro"), 2)
        self.assertEqual(sm.tier_of_model("openrouter/moonshotai/kimi-k2.6"), 2)
        # gemma (open-weight) under google is OSS
        self.assertEqual(sm.tier_of_model("openrouter/google/gemma-3"), 2)

    def test_free_is_tier3(self):
        self.assertEqual(sm.tier_of_model("openrouter/free"), 3)
        self.assertEqual(sm.tier_of_model("openrouter/deepseek/deepseek-r1:free"), 3)

    def test_proprietary_openrouter_is_not_a_tier(self):
        # proprietary OpenRouter routes are NOT tier-2 open source (PLAN.md §2)
        self.assertEqual(sm.tier_of_model("openrouter/openai/gpt-5"), 0)
        self.assertEqual(sm.tier_of_model("openrouter/google/gemini-3.1-pro"), 0)


class TestCascadeOrder(unittest.TestCase):
    """Invariant 1: Ollama Cloud -> OpenRouter OSS -> free, in that exact order."""

    def test_tier1_beats_tier2_and_free(self):
        r = sm.select_task_model(task_text="analyze the strategy", inventory=INV_FULL)
        self.assertEqual(r["tier"], 1)
        self.assertTrue(r["model_id"].startswith("ollama/"))
        self.assertTrue(r["model_id"].endswith(":cloud"))

    def test_tier2_when_no_tier1(self):
        inv = ["openrouter/deepseek/deepseek-v4-pro", "openrouter/free"]
        r = sm.select_task_model(task_text="analyze the strategy", inventory=inv)
        self.assertEqual(r["tier"], 2)
        self.assertEqual(r["model_id"], "openrouter/deepseek/deepseek-v4-pro")

    def test_free_is_last_resort_only(self):
        # free is the ONLY thing in inventory -> it may resolve, but as tier 3
        r = sm.select_task_model(task_text="draft a short reply",
                                 inventory=["openrouter/free"])
        # the bare 'openrouter/free' sentinel is never inventory-valid for text
        # modality matching, so this surfaces as needs_owner_input rather than a
        # silent free default (the gate would reject 'openrouter/free' anyway).
        self.assertTrue(r["needs_owner_input"])
        self.assertIsNone(r["model_id"])

    def test_highest_version_within_tier(self):
        # kimi 2.7 must beat kimi 2.6 within tier 1 (existing version logic)
        inv = ["ollama/kimi-k2.6:cloud", "ollama/kimi-k2.7:cloud"]
        r = sm.select_task_model(task_text="analyze the strategy", inventory=inv)
        self.assertEqual(r["model_id"], "ollama/kimi-k2.7:cloud")


class TestOllamaCloudIdShapes(unittest.TestCase):
    """ISSUE-08: date-tagged, size-tagged and ollama-cloud/ prefixed ids.

    The chain patterns were anchored `^ollama/...(?::cloud)?$`, so every real
    fleet id (`ollama/deepseek-v4-pro:0813-cloud`, `ollama-cloud/kimi-k2.6:cloud`)
    matched NOTHING and every Ollama slot in every chain silently emptied. These
    assert the shapes the fleet actually runs.
    """

    def _version(self, entry, model_id):
        m = entry["pattern"].match(model_id)
        self.assertIsNotNone(m, "%s must match %s" % (entry["label"], model_id))
        return sm._parse_version(m.group(1))

    def test_date_tagged_deepseek_pro(self):
        self.assertEqual(
            self._version(sm.DEEPSEEK_PRO_OLLAMA, "ollama/deepseek-v4-pro:0813-cloud"), (4,))

    def test_date_tagged_kimi(self):
        self.assertEqual(
            self._version(sm.KIMI_OLLAMA, "ollama/kimi-k2.6:0711-cloud"), (2, 6))

    def test_date_tagged_deepseek_flash(self):
        self.assertEqual(
            self._version(sm.DEEPSEEK_FLASH_OLLAMA, "ollama/deepseek-v4-flash:0731-cloud"), (4,))

    def test_ollama_cloud_prefix_minimax(self):
        self.assertEqual(
            self._version(sm.MINIMAX_OLLAMA, "ollama-cloud/minimax-m3:cloud"), (3,))

    def test_ollama_cloud_prefix_kimi(self):
        self.assertEqual(
            self._version(sm.KIMI_OLLAMA, "ollama-cloud/kimi-k2.6:cloud"), (2, 6))

    def test_glm_on_ollama_cloud_has_a_slot(self):
        self.assertEqual(self._version(sm.GLM_OLLAMA, "ollama/glm-5.3:cloud"), (5, 3))
        self.assertIn(sm.GLM_OLLAMA, sm.CHAINS["mid"]["normal"])

    def test_size_tagged_cloud_tag_still_matches(self):
        # the pre-existing compound tag shape (`:235b-cloud`) must keep matching
        self.assertEqual(self._version(sm.MINIMAX_OLLAMA, "ollama/minimax-m3:235b-cloud"), (3,))

    def test_code_variant_is_not_the_kimi_chat_slot(self):
        # a family SUFFIX is a different model; it must never fill the Kimi slot
        self.assertIsNone(sm.KIMI_OLLAMA["pattern"].match("ollama/kimi-k2.7-code:cloud"))

    def test_highest_version_wins_across_tag_shapes(self):
        inv = ["ollama/kimi-k2.7:cloud", "ollama/kimi-k2.6:0711-cloud"]
        self.assertEqual(sm._best_match_in_position(inv, sm.KIMI_OLLAMA),
                         "ollama/kimi-k2.7:cloud")

    def test_ollama_glm_slot_never_claims_an_openrouter_glm_slug(self):
        # both slots are family `glm`; the Tier-1 slot must not claim the Tier-2
        # verified slug (that would mislabel an OpenRouter model as Ollama Cloud)
        inv = ["openrouter/z-ai/glm-5.3"]
        self.assertIsNone(sm._best_match_in_position(inv, sm.GLM_OLLAMA))
        self.assertEqual(sm._best_match_in_position(inv, sm.GLM_OPENROUTER),
                         "openrouter/z-ai/glm-5.3")

    def test_real_fleet_inventory_resolves_every_tier(self):
        inv = ["ollama/kimi-k2.6:0711-cloud", "ollama/deepseek-v4-pro:0813-cloud",
               "ollama/deepseek-v4-flash:0731-cloud", "ollama/minimax-m3:cloud",
               "ollama/glm-5.3:cloud", "ollama/kimi-k2.7-code:cloud"]
        heavy = sm._best_match_in_position(inv, sm.CHAINS["heavy"]["normal"][0])
        mid = sm._best_match_in_position(inv, sm.CHAINS["mid"]["normal"][0])
        fast = sm._best_match_in_position(inv, sm.CHAINS["fast"]["normal"][0])
        self.assertEqual(heavy, "ollama/deepseek-v4-pro:0813-cloud")
        self.assertEqual(mid, "ollama/minimax-m3:cloud")
        self.assertEqual(fast, "ollama/deepseek-v4-flash:0731-cloud")
        self.assertNotEqual(heavy, mid)   # HEAVY-WRITER and JUDGE stay independent


class TestModalityMatch(unittest.TestCase):
    """Invariant 2: vision task MUST get a vision model; text-only never eligible."""

    def test_vision_task_gets_vision_model(self):
        r = sm.select_task_model(
            task_text="look at this slide screenshot and do visual QC",
            inventory=INV_FULL,
        )
        self.assertEqual(r["required_modality"], "vision")
        self.assertEqual(r["model_id"], "ollama/qwen3-vl:235b-cloud")
        self.assertIn("vision", sm.capabilities_for_model(r["model_id"]))

    def test_vision_task_never_picks_textonly_even_if_higher_tier(self):
        # deepseek-pro (T1, text-only) sits "above" any vision model, but a
        # vision task must skip it entirely.
        r = sm.select_task_model(
            task_text="review the image for visual qc",
            inventory=INV_NO_VISION,   # no vision model present at all
        )
        self.assertTrue(r["needs_owner_input"])
        self.assertIsNone(r["model_id"])

    def test_image_generation_modality_inferred_and_required(self):
        inv = ["ollama/deepseek-v4-pro:cloud", "openrouter/flux/flux-1"]
        r = sm.select_task_model(task_text="generate an image of a logo", inventory=inv)
        self.assertEqual(r["required_modality"], "image_generation")
        self.assertIn("image_generation", sm.capabilities_for_model(r["model_id"]))

    def test_text_model_does_not_satisfy_vision(self):
        self.assertFalse(sm.model_has_modality("ollama/deepseek-v4-pro:cloud", "vision"))
        self.assertTrue(sm.model_has_modality("ollama/qwen3-vl:235b-cloud", "vision"))


class TestSopOverride(unittest.TestCase):
    """Invariant 3: SOP pin wins (when valid); invalid pin surfaces, never silent."""

    def test_valid_sop_pin_wins_over_selector(self):
        r = sm.select_task_model(
            task_text="analyze the strategy",            # would pick deepseek
            sop_model_pin="ollama/kimi-k2.7:cloud",
            inventory=INV_FULL,
        )
        self.assertEqual(r["modelSource"], "sop_pin")
        self.assertEqual(r["model_id"], "ollama/kimi-k2.7:cloud")

    def test_sop_pin_to_wrong_modality_is_rejected_not_silent(self):
        # pin a text-only model for a vision task -> must NOT silently honor it
        r = sm.select_task_model(
            task_text="do visual qc on this screenshot",
            sop_model_pin="ollama/deepseek-v4-pro:cloud",
            inventory=INV_FULL,
        )
        self.assertTrue(r["needs_owner_input"])
        self.assertEqual(r["modelSource"], "sop_pin_invalid")

    def test_sop_pin_to_forbidden_is_rejected(self):
        r = sm.select_task_model(
            task_text="draft a reply",
            sop_model_pin="anthropic/claude-opus",
            inventory=INV_FULL,
        )
        self.assertTrue(r["needs_owner_input"])
        self.assertEqual(r["modelSource"], "sop_pin_invalid")


class TestNoModelRejected(unittest.TestCase):
    """Invariant 4: the gate BLOCKS null / free / forbidden / wrong-modality."""

    def test_free_sentinel_blocked(self):
        v = gate.assert_model_sovereignty("openrouter/free", inventory=INV_FULL)
        self.assertFalse(v["ok"])
        self.assertEqual(v["code"], "FREE_DEFAULT")

    def test_null_blocked(self):
        v = gate.assert_model_sovereignty(None, inventory=INV_FULL)
        self.assertFalse(v["ok"])
        self.assertEqual(v["code"], "NULL_MODEL")

    def test_forbidden_blocked(self):
        v = gate.assert_model_sovereignty("anthropic/claude-opus", inventory=INV_FULL)
        self.assertFalse(v["ok"])
        self.assertEqual(v["code"], "FORBIDDEN")

    def test_not_in_inventory_blocked(self):
        v = gate.assert_model_sovereignty(
            "ollama/some-unknown-model:cloud", inventory=INV_FULL)
        self.assertFalse(v["ok"])
        self.assertEqual(v["code"], "NOT_IN_INVENTORY")

    def test_modality_mismatch_blocked(self):
        v = gate.assert_model_sovereignty(
            "ollama/deepseek-v4-pro:cloud", inventory=INV_FULL,
            required_modality="vision")
        self.assertFalse(v["ok"])
        self.assertEqual(v["code"], "MODALITY_MISMATCH")

    def test_sovereign_model_passes(self):
        v = gate.assert_model_sovereignty(
            "ollama/qwen3-vl:235b-cloud", inventory=INV_FULL,
            required_modality="vision")
        self.assertTrue(v["ok"])
        self.assertEqual(v["code"], "OK")
        self.assertEqual(v["tier"], 1)


class TestDeptDefaultLayer1(unittest.TestCase):
    """Layer-1 dept default (PLAN.md §3): modality-aware, never model-less/free."""

    def test_graphics_dept_gets_vision_model(self):
        r = sm.resolve_dept_default_model("graphics", inventory=INV_FULL)
        self.assertEqual(r["required_modality"], "vision")
        self.assertIn("vision", sm.capabilities_for_model(r["model_id"]))

    def test_ceo_dept_gets_heavy_text_tier1(self):
        r = sm.resolve_dept_default_model("ceo", inventory=INV_FULL)
        self.assertEqual(r["tier"], 1)
        self.assertFalse(r["needs_owner_input"])

    def test_unknown_dept_falls_to_safe_default_never_modelless(self):
        r = sm.resolve_dept_default_model("some-made-up-dept", inventory=INV_FULL)
        # default suitability is text+mid; must resolve to a real model, not free
        self.assertIsNotNone(r["model_id"])
        self.assertNotIn(r["model_id"], sm.FREE_SENTINELS)


class TestDifficultyClassifier(unittest.TestCase):
    def test_hard_medium_simple(self):
        self.assertEqual(sm.classify_difficulty("design the system architecture"), "hard")
        self.assertEqual(sm.classify_difficulty("classify this lead"), "simple")
        self.assertEqual(sm.classify_difficulty("write a quick note"), "medium")

    def test_long_input_forces_hard(self):
        self.assertEqual(sm.classify_difficulty("summarize", input_chars=60_000), "hard")


if __name__ == "__main__":
    unittest.main(verbosity=2)
