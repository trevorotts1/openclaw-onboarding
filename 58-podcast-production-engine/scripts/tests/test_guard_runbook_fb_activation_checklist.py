#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: guard-runbook-fb-activation-checklist
# -----------------------------------------------------------------------------
# Stdlib unittest only. No network, no live DB. Proves the grep-anchored gate's
# own self-test passes AND that it PASSES against the REAL podcast
# client-onboarding runbook (universal-sops/podcast-craft/
# SOP-PODCAST-02-CLIENT-ONBOARDING.md) on this checkout, so a runbook edit that
# silently drops the Facebook-ads activation checklist item is caught here
# rather than drifting into tribal knowledge (Skill 6 v2 unit U68 / GK-06).
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_guard_runbook_fb_activation_checklist.py
# =============================================================================
"""Tests for guard-runbook-fb-activation-checklist.py (U68 / GK-06)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_GUARD = _HERE.parent.parent / "guard-runbook-fb-activation-checklist.py"
_REPO_ROOT = _HERE.parent.parent.parent.parent
_RUNBOOK = _REPO_ROOT / "universal-sops" / "podcast-craft" / "SOP-PODCAST-02-CLIENT-ONBOARDING.md"


def _load_module():
    spec = importlib.util.spec_from_file_location("guard_runbook_fb_activation_checklist", str(_GUARD))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GUARD = _load_module()


class GuardSelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        self.assertEqual(GUARD.self_test(), 0)


class RealRunbookCarriesTheChecklistItem(unittest.TestCase):
    def test_runbook_file_exists(self):
        self.assertTrue(_RUNBOOK.is_file(), "runbook not found at %s" % _RUNBOOK)

    def test_audit_finds_zero_findings_against_the_real_runbook(self):
        text = _RUNBOOK.read_text(encoding="utf-8")
        findings = GUARD.audit(text)
        self.assertEqual(findings, [], "runbook missing the FB-activation checklist item: %s" % findings)

    def test_cli_exits_zero_against_the_real_runbook(self):
        result = subprocess.run(
            [sys.executable, str(_GUARD), "--runbook", str(_RUNBOOK)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cli_autofails_when_the_item_is_stripped(self):
        import tempfile
        text = _RUNBOOK.read_text(encoding="utf-8")
        stripped = text.replace("activate-podcast-fb-workflows.py", "some-other-script.py")
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write(stripped)
            tmp_path = fh.name
        try:
            result = subprocess.run(
                [sys.executable, str(_GUARD), "--runbook", tmp_path],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
