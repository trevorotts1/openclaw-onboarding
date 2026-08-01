#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: activate-podcast-fb-workflows.py unit tests
# -----------------------------------------------------------------------------
# Stdlib unittest only. No network.  Proves the workflow name matcher correctly
# handles exact matches, rejects prefix-only (substring) matches, and handles
# case/whitespace variants -- the three scenarios from R-25 (unit onb-14).
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_activate_podcast_fb_workflows.py
# =============================================================================
"""Deterministic tests for the workflow-name matcher in activate-podcast-fb-workflows.py."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "activate-podcast-fb-workflows.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "activate_podcast_fb_workflows", str(_SCRIPT)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ACT = _load_module()

_SAMPLE_ROWS = [
    {"id": "1", "name": "01a - Update Facebook audience"},
    {"id": "2", "name": "02-Fb Podcast Lead That DID NOT COMPLETE"},
    {"id": "3", "name": "02a-2nd Fb Podcast Interview"},
    {"id": "4", "name": "03-Podcast LeadForm Fb Ad"},
    {"id": "5", "name": "01a-fake-decoy-workflow-that-shares-prefix"},
]


class ExactMatchTests(unittest.TestCase):
    """Exact full-name match must return the correct row."""

    def test_exact_match_finds_correct_row(self):
        m = ACT._match_workflow(_SAMPLE_ROWS, "01a - Update Facebook audience")
        self.assertIsNotNone(m)
        self.assertEqual(m["id"], "1")

    def test_exact_match_does_not_hit_prefix_rival(self):
        m = ACT._match_workflow(_SAMPLE_ROWS, "01a - Update Facebook audience")
        self.assertIsNotNone(m)
        self.assertEqual(m["name"], "01a - Update Facebook audience")
        self.assertNotEqual(m["id"], "5")

    def test_exact_match_long_name(self):
        m = ACT._match_workflow(
            _SAMPLE_ROWS, "02-Fb Podcast Lead That DID NOT COMPLETE"
        )
        self.assertIsNotNone(m)
        self.assertEqual(m["id"], "2")


class PrefixRejectedTests(unittest.TestCase):
    """A name that is merely a prefix of a workflow name must NOT match."""

    def test_bare_prefix_rejected(self):
        m = ACT._match_workflow(_SAMPLE_ROWS, "01a")
        self.assertIsNone(m)

    def test_partial_name_rejected(self):
        m = ACT._match_workflow(_SAMPLE_ROWS, "01a -")
        self.assertIsNone(m)

    def test_substring_not_at_start_rejected(self):
        m = ACT._match_workflow(_SAMPLE_ROWS, "Fb Ad")
        self.assertIsNone(m)


class CaseAndWhitespaceTests(unittest.TestCase):
    """Case and leading/trailing whitespace must be normalized before comparison."""

    def test_lowercase_with_whitespace(self):
        m = ACT._match_workflow(_SAMPLE_ROWS, "  03-podcast leadform fb ad  ")
        self.assertIsNotNone(m)
        self.assertEqual(m["id"], "4")

    def test_uppercase_variant(self):
        m = ACT._match_workflow(_SAMPLE_ROWS, "02A-2ND FB PODCAST INTERVIEW")
        self.assertIsNotNone(m)
        self.assertEqual(m["id"], "3")

    def test_mixed_case_original(self):
        m = ACT._match_workflow(_SAMPLE_ROWS, "02a-2nd Fb Podcast Interview")
        self.assertIsNotNone(m)
        self.assertEqual(m["id"], "3")


class MissingTests(unittest.TestCase):
    """A name not in the list must return None."""

    def test_completely_missing(self):
        m = ACT._match_workflow(_SAMPLE_ROWS, "NON-EXISTENT WORKFLOW")
        self.assertIsNone(m)

    def test_empty_string(self):
        m = ACT._match_workflow(_SAMPLE_ROWS, "")
        self.assertIsNone(m, "empty string should not match anything")


class SelfTestCLITests(unittest.TestCase):
    """The --self-test flag must exit 0."""

    def test_self_test_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--self-test"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_self_test_output_shows_all_passed(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--self-test"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertIn("ALL ASSERTIONS PASSED", result.stdout)
