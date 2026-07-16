#!/usr/bin/env python3
"""Regression guard for U59/JM-U55's U55a — the operator-box proof that the
Devil's Advocate generator (shared-utils/devils-advocate.py) runs clean for
all five triggers and degrades honestly with no LLM available.

This is the ONGOING CI lock behind the point-in-time evidence captured at
ledgers/evidence/U59-JM-U55/ (out-<trigger>.json / err-<trigger>.txt /
exitcode-<trigger>.txt, one operator-box run, this pass). The evidence folder
is the record of what happened once; this file is what keeps proving it holds
on every future commit.

Proves:
  * All five trigger types the CLI accepts (`--trigger` argparse choices)
    produce schema-valid JSON via generate_challenge() -- the same seven keys
    the bridge's build_payload() and the CC-side U55c route both depend on.
  * The template-only fallback (_fallback_response) is well-formed and
    parses into the same seven-key schema as the LLM-backed branch would --
    the two response shapes must never diverge (a divergence would silently
    break the bridge/board for every no-LLM-configured box).
  * The captured evidence JSON files on disk (this pass's real operator-box
    run) are schema-valid and self-consistent with the trigger that produced
    them -- byte-checked, not eyeballed.
  * generate_challenge() never raises for any of the five triggers, matching
    every captured evidence exitcode-<t>.txt == "0".

Run:
    python3 tests/unit/u59-devils-advocate-generator-proof.test.py
    or: pytest tests/unit/u59-devils-advocate-generator-proof.test.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED = _REPO_ROOT / "shared-utils"
_EVIDENCE_DIR = _REPO_ROOT / "ledgers" / "evidence" / "U59-JM-U55"
assert _SHARED.is_dir(), f"shared-utils not found at {_SHARED}"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), _SHARED / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name.replace("-", "_")] = mod
    spec.loader.exec_module(mod)
    return mod


generator = _load("devils-advocate")

TRIGGERS = (
    "critical_task",
    "strategic_decision",
    "consecutive_approval",
    "kpi_swing",
    "sensitive_dept",
)

_REQUIRED_KEYS = {
    "trigger_type", "challenge", "specific_concern",
    "assumptions", "severity", "confidence", "raw_response",
}


def _assert_schema_valid(testcase: unittest.TestCase, result: dict, expected_trigger: str) -> None:
    missing = _REQUIRED_KEYS - set(result.keys())
    testcase.assertFalse(missing, f"missing keys for {expected_trigger}: {missing}")
    testcase.assertEqual(result["trigger_type"], expected_trigger)
    testcase.assertIn(result["severity"], ("low", "medium", "high"))
    testcase.assertIsInstance(result["confidence"], float)
    testcase.assertGreaterEqual(result["confidence"], 0.0)
    testcase.assertLessEqual(result["confidence"], 1.0)
    testcase.assertTrue(result["challenge"].strip(), "challenge text must be non-empty")
    testcase.assertTrue(result["specific_concern"].strip(), "specific_concern text must be non-empty")


class TestAllFiveTriggersGreen(unittest.TestCase):
    """U55a binary acceptance, live: 'If ANY trigger fails, fix the generator
    FIRST.' Re-proven fresh on every run, not just the one-time evidence
    capture."""

    def test_each_trigger_produces_schema_valid_output(self):
        for trigger in TRIGGERS:
            with self.subTest(trigger=trigger):
                context = {"task_id": f"proof-{trigger}", "title": f"Fixture for {trigger}", "department": "marketing"}
                result = generator.generate_challenge(trigger, context)
                _assert_schema_valid(self, result, trigger)

    def test_no_trigger_raises(self):
        for trigger in TRIGGERS:
            with self.subTest(trigger=trigger):
                try:
                    generator.generate_challenge(trigger, {"title": "x"})
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"trigger {trigger!r} raised unexpectedly: {exc}")

    def test_missing_title_degrades_to_unknown_task_not_a_crash(self):
        # RUNBOOK-documented contexts always carry a title, but the generator
        # must never crash on a minimal/malformed context -- degrade honestly.
        result = generator.generate_challenge("critical_task", {})
        _assert_schema_valid(self, result, "critical_task")
        self.assertIn("(unknown task)", result["challenge"])


class TestFallbackResponseShape(unittest.TestCase):
    """The no-LLM template fallback must parse into the exact same schema the
    LLM-backed branch would -- verified this pass to be the path every
    trigger actually takes on this box (see the evidence README)."""

    def test_fallback_response_is_well_formed_markdown_sections(self):
        raw = generator._fallback_response("kpi_swing", {"title": "Fixture task"})
        for heading in ("## Challenge", "## Specific Concern", "## What Would Have to Be True",
                        "## Severity", "## Confidence"):
            self.assertIn(heading, raw)

    def test_fallback_parses_into_full_schema_via_the_real_parser(self):
        # Exercises generate_challenge()'s own section parser against the
        # fallback's raw text, the exact code path this box's five evidence
        # runs took (SELECT_MODEL_AVAILABLE=False on this tree -- see the
        # evidence README's root-cause note).
        result = generator.generate_challenge("kpi_swing", {"title": "Fixture task"})
        _assert_schema_valid(self, result, "kpi_swing")
        self.assertIn("no LLM model was available", result["specific_concern"])
        self.assertEqual(result["severity"], "medium")
        self.assertEqual(result["confidence"], 0.5)

    def test_fallback_task_title_fallback_chain(self):
        # context.get("title") or context.get("task_title") or "(unknown task)"
        self.assertIn("Exact Title", generator._fallback_response("critical_task", {"title": "Exact Title"}))
        self.assertIn("Alt Title", generator._fallback_response("critical_task", {"task_title": "Alt Title"}))
        self.assertIn("(unknown task)", generator._fallback_response("critical_task", {}))


@unittest.skipUnless(_EVIDENCE_DIR.is_dir(), f"evidence dir not present at {_EVIDENCE_DIR}")
class TestCapturedEvidenceOnDisk(unittest.TestCase):
    """Byte-checks the operator-box evidence capture itself (not the live
    generator) -- proves the recorded artifact is internally consistent, so a
    future reader trusts the evidence folder without re-running anything."""

    def test_every_trigger_has_a_zero_exitcode_file(self):
        for trigger in TRIGGERS:
            path = _EVIDENCE_DIR / f"exitcode-{trigger}.txt"
            self.assertTrue(path.is_file(), f"missing {path}")
            content = path.read_text().strip()
            self.assertIn("exit=0", content, f"{trigger} evidence exitcode file does not record exit=0: {content!r}")

    def test_every_trigger_output_json_is_schema_valid(self):
        for trigger in TRIGGERS:
            path = _EVIDENCE_DIR / f"out-{trigger}.json"
            self.assertTrue(path.is_file(), f"missing {path}")
            result = json.loads(path.read_text())
            _assert_schema_valid(self, result, trigger)

    def test_every_context_fixture_is_valid_json_with_a_title(self):
        for trigger in TRIGGERS:
            path = _EVIDENCE_DIR / f"ctx-{trigger}.json"
            self.assertTrue(path.is_file(), f"missing {path}")
            ctx = json.loads(path.read_text())
            self.assertTrue(ctx.get("title"), f"{trigger} fixture context missing a title")


if __name__ == "__main__":
    unittest.main(verbosity=2)
