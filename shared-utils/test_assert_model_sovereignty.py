#!/usr/bin/env python3
"""Unit tests for the retired Anthropic detector in assert_model_sovereignty.py and
for the empty FORBIDDEN_PREFIXES. There is NO rule against Anthropic / Claude models
(Trevor order 2026-10-29): every detector answers False and the gate never blocks a
model for its vendor. stdlib only.

  python3 -m unittest shared-utils/test_assert_model_sovereignty.py
  (or)  python3 shared-utils/test_assert_model_sovereignty.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from assert_model_sovereignty import (assert_model_sovereignty, is_anthropic_model,
                                      text_has_anthropic_model_id)
import select_model as sm

FAMILY_IDS = [
    "anthropic/claude-3-5-sonnet", "anthropic.claude-3", "us.anthropic.claude-3-opus",
    "openrouter/anthropic/claude-3", "anthropic", "claude", "claude-5", "Claude-3-Haiku",
    "opus", "sonnet", "haiku",
]


class TestNoAnthropicRule(unittest.TestCase):
    def test_detector_never_flags(self):
        for m in FAMILY_IDS + ["ollama-cloud/qwen3-235b", "", None]:
            self.assertFalse(is_anthropic_model(m), f"must NOT flag {m!r}")

    def test_text_scanner_never_flags(self):
        for t in ['"model": "anthropic/claude-3-5-sonnet"', "resolved to claude-3-5-sonnet",
                  '"verifier": "us.anthropic.claude-opus-4-1"', "magnum opus"]:
            self.assertFalse(text_has_anthropic_model_id(t), f"must NOT flag {t[:40]!r}")

    def test_forbidden_prefixes_is_empty(self):
        self.assertEqual(sm.FORBIDDEN_PREFIXES, ())
        for m in FAMILY_IDS:
            self.assertFalse(sm._is_forbidden(m), f"must NOT forbid {m!r}")

    def test_gate_does_not_block_an_anthropic_family_model(self):
        for m in ("anthropic/claude-opus-5", "openrouter/anthropic/claude-haiku-4.5"):
            v = assert_model_sovereignty(m, inventory=[m])
            self.assertTrue(v["ok"], v)
            self.assertNotEqual(v["code"], "FORBIDDEN")

    def test_gate_still_blocks_the_free_sentinel(self):
        v = assert_model_sovereignty("openrouter/free", inventory=["openrouter/free"])
        self.assertFalse(v["ok"])
        self.assertEqual(v["code"], "FREE_DEFAULT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
