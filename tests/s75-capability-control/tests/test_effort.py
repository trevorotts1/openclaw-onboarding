import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests._support  # noqa: E402,F401 - puts the skill-tree module on sys.path

from capability_control.effort import ModelCaps, plan_request, thinking_log_proof  # noqa: E402

# Live facts (2026-10-22, OpenRouter catalog + installed host /v1/models):
# xiaomi/mimo-v2.6-pro: reasoning WITHOUT an effort selector.
# z-ai/glm-5.3: reasoning WITH reasoning_effort.
MIMO = ModelCaps("openrouter/xiaomi/mimo-v2.6-pro", reasoning=True, effort_selector=False, tools=True)
GLM = ModelCaps("openrouter/z-ai/glm-5.3", reasoning=True, effort_selector=True, tools=True)
DEAF = ModelCaps("example/no-reasoning", reasoning=False, effort_selector=False)


class TestEffortHonesty(unittest.TestCase):
    """Acceptance: unsupported effort is never fabricated."""

    def test_required_effort_on_selectorless_model_is_refused_not_stripped(self):
        plan = plan_request(MIMO, "high", required=True)
        self.assertIsNone(plan.params)
        self.assertEqual(plan.refusal, "UNSUPPORTED_EFFORT: openrouter/xiaomi/mimo-v2.6-pro exposes reasoning but no effort selector")
        self.assertTrue(plan.fabricated)

    def test_optional_effort_on_selectorless_model_omits_param_and_claims_honestly(self):
        plan = plan_request(MIMO, "high", required=False)
        self.assertEqual(plan.params, {})
        self.assertEqual(plan.claim, "reasoning_without_effort_selector")
        self.assertFalse(plan.fabricated)

    def test_ui_ladder_cannot_create_provider_support(self):
        ladder = {"openrouter/xiaomi/mimo-v2.6-pro": ["low", "high", "max"], "default": "max"}
        for value in ("high", "max"):
            plan = plan_request(MIMO, value, required=True, ui_ladder=ladder)
            self.assertIsNone(plan.params, "UI ladder must never fabricate an effort parameter")
            self.assertTrue(plan.fabricated)
        plan = plan_request(MIMO, "max", required=False, ui_ladder=ladder)
        self.assertEqual(plan.params, {})

    def test_selector_model_sends_the_real_parameter(self):
        plan = plan_request(GLM, "high", required=True)
        self.assertEqual(plan.params, {"reasoning_effort": "high"})
        self.assertEqual(plan.claim, "reasoning_effort=high")
        self.assertIsNone(plan.refusal)

    def test_no_reasoning_model_refuses_effort(self):
        plan = plan_request(DEAF, "high", required=True)
        self.assertEqual(plan.refusal, "UNSUPPORTED_EFFORT")
        self.assertTrue(plan.fabricated)

    def test_generic_thinking_log_is_never_proof(self):
        proof = thinking_log_proof("runtime: thinking=max")
        self.assertFalse(proof["proves_model_parameter"])
        proof = thinking_log_proof("providerThinking.deepseek.mode=max")
        self.assertFalse(proof["proves_model_parameter"])


if __name__ == "__main__":
    unittest.main()
