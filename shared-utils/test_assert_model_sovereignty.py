#!/usr/bin/env python3
"""Unit tests for the SK2-16 canonical Anthropic detector in
assert_model_sovereignty.py. stdlib only.

  python3 -m unittest shared-utils/test_assert_model_sovereignty.py
  (or)  python3 shared-utils/test_assert_model_sovereignty.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from assert_model_sovereignty import is_anthropic_model, text_has_anthropic_model_id


class TestIsAnthropicModel(unittest.TestCase):
    def test_positive_ids(self):
        for m in [
            "anthropic/claude-3-5-sonnet",      # slash route
            "anthropic.claude-3",               # dot route
            "us.anthropic.claude-3-opus",       # bedrock/vertex dot route
            "openrouter/anthropic/claude-3",    # nested route
            "anthropic",                        # bare provider token
            "claude", "claude-5", "claude-fable-5", "Claude-3-Haiku",
            "opus", "sonnet", "haiku", "OPUS",  # bare families
        ]:
            self.assertTrue(is_anthropic_model(m), f"should flag {m!r}")

    def test_negative_ids(self):
        for m in [
            "ollama-cloud/qwen3-235b", "openrouter/deepseek/deepseek-r1",
            "gpt-4o-mini", "gemini-2.5-flash", "qwen3-vl:235b-cloud",
            "opusculum", "opusflow", "magnum-opusculum", "", None,
        ]:
            self.assertFalse(is_anthropic_model(m), f"should NOT flag {m!r}")


class TestTextScanner(unittest.TestCase):
    def test_documentation_not_flagged(self):
        # Compliance docs / prose that name the vendor while documenting removal
        # must NOT be treated as a sneaked id.
        for t in [
            "every resolved model id fails /anthropic|claude/i; no operator creds",
            "the source's sole Anthropic-Sonnet chain is removed per the client-path rule",
            "ZERO Anthropic ids (G-NOANTHROPIC / AF-AV-NOANTHROPIC).",
            "source hardcoded an Anthropic model chain via OpenRouter; re-pointed",
            "write a beautiful sonnet about ducks", "magnum opus",
        ]:
            self.assertFalse(text_has_anthropic_model_id(t), f"FP on {t[:40]!r}")

    def test_real_ids_in_text_flagged(self):
        for t in [
            '"model": "anthropic/claude-3-5-sonnet"',
            '"tierA": "anthropic.claude-3-opus"',
            "resolved to claude-3-5-sonnet in stage 4",
            '"m": "openrouter/anthropic/claude-3"',
            '"verifier": "us.anthropic.claude-opus-4-1"',
        ]:
            self.assertTrue(text_has_anthropic_model_id(t), f"MISS on {t[:40]!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
