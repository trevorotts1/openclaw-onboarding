#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_browser_qc_integration.py — integration tests for build unit U19
(scripts/run_browser_qc.py), the P13-BROWSER-QC phase.

Spec Section 19.3 (E2E tests) names "reduced motion", "rapid scroll and
reverse scroll", "direct hosted mode" against "a deterministic fixture
site" driven by Playwright. This module does the real thing: a genuine
`next build` + `next start` production server (reusing the same
deterministic U15 fixture every other integration suite in this skill
uses) and a real headless Chromium session for every category
(desktop/mobile/reduced-motion/accessibility/performance).

SLOW — requires network (npm install), a real Node/npm toolchain, Playwright
Chromium (`python3 -m playwright install chromium`), and binds a real local
TCP port. Kept out of tests/unit/ deliberately, same split every other
build unit in this skill uses.

Run with:
  python3 -m unittest discover -s 62-cinematic-web-funnel-engine/tests/integration -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "site-fixture"

sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))
sys.path.insert(0, str(_FIXTURE_DIR))

import build_site as bs  # noqa: E402
import run_browser_qc as rbq  # noqa: E402

TOOLCHAIN_TIMEOUT_SECONDS = 300


def _skip_if_no_playwright() -> None:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        raise unittest.SkipTest(
            "playwright Python package (or its Chromium browser) is not installed in this environment — "
            "run `pip install playwright && python3 -m playwright install chromium`"
        )


class TestRealBrowserQcAgainstFixtureSite(unittest.TestCase):
    """One shared real build + one shared real evaluate() run for the whole
    class — a fresh `next build`/`next start`/browser-launch cycle per test
    method would make this suite unnecessarily slow without adding
    coverage, same rationale test_site_build_integration.py already uses."""

    @classmethod
    def setUpClass(cls) -> None:
        _skip_if_no_playwright()
        cls._tmp = tempfile.TemporaryDirectory(prefix="cwfe-browser-qc-integration-")
        cls.run_dir = Path(cls._tmp.name) / "run"
        rbq._patched_fixture_run_dir(cls.run_dir)
        cls.build_result = bs.build_site(cls.run_dir, skip_toolchain=False, toolchain_timeout=TOOLCHAIN_TIMEOUT_SECONDS)
        assert cls.build_result.receipt["status"] == "pass", "precondition: fixture must build clean before browser QC"
        cls.passed, cls.detail = rbq.evaluate(cls.run_dir)
        cls.report = json.loads((cls.run_dir / "browser-qc-report.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_overall_pass(self) -> None:
        self.assertTrue(self.passed, self.detail)
        self.assertEqual(self.report["overall_status"], "pass")

    def test_report_written_and_schema_valid(self) -> None:
        import json_schema_lite as jsl

        schema = json.loads((rbq._STRUCTURE_DIR / "browser-qc-report.schema.json").read_text(encoding="utf-8"))
        errors = jsl.validate(self.report, schema)
        self.assertEqual(errors, [], errors)

    def test_desktop_category_passes_with_no_console_errors(self) -> None:
        desktop = self.report["categories"]["desktop"]
        self.assertTrue(desktop["passed"], desktop["violations"])

    def test_skip_link_focus_hardening_is_verified_live(self) -> None:
        # The U19 template hardening (tabIndex={-1} on #cwfe-conversion-start)
        # is exercised by _check_desktop's Tab+Enter sequence; a real pass
        # here proves the fix works against the real built+served site, not
        # just against source code.
        desktop = self.report["categories"]["desktop"]
        skip_link_violations = [v for v in desktop["violations"] if "skip link" in v.lower() or "skip the link" in v.lower()]
        self.assertEqual(skip_link_violations, [])

    def test_mobile_category_passes_no_horizontal_overflow(self) -> None:
        mobile = self.report["categories"]["mobile"]
        self.assertTrue(mobile["passed"], mobile["violations"])

    def test_reduced_motion_category_mounts_zero_videos(self) -> None:
        reduced = self.report["categories"]["reduced_motion"]
        self.assertTrue(reduced["passed"], reduced["violations"])

    def test_accessibility_category_passes(self) -> None:
        a11y = self.report["categories"]["accessibility"]
        self.assertTrue(a11y["passed"], a11y["violations"])

    def test_performance_category_passes_and_records_lcp_substitution(self) -> None:
        perf = self.report["categories"]["performance"]
        self.assertTrue(perf["passed"], perf["violations"])
        self.assertIn(perf["lcp_status"], ("observed", "unavailable_in_headless_harness_fcp_used"))
        self.assertGreater(perf["measurements"]["first_contentful_paint_ms"], 0)

    def test_max_mounted_videos_matches_derived_neighbor_radius_budget(self) -> None:
        perf = self.report["categories"]["performance"]
        mount_radius = rbq._neighbor_mount_radius(Path(self.report["site_dir"]))
        expected_budget = 2 * mount_radius + 1
        self.assertEqual(perf["budgets"]["max_mounted_video_elements"], expected_budget)
        self.assertLessEqual(perf["measurements"]["max_mounted_video_elements"], expected_budget)


class TestBrowserQcModuleSelfTest(unittest.TestCase):
    """Runs the module's own `_self_test()` — the fail-closed break-it
    proofs (missing viewport meta, video missing aria-hidden, missing
    receipt, nonexistent site_dir, and restore-to-clean) documented in the
    module's docstring. One real build, several cheap server restarts
    against mutated static HTML (no rebuild needed per mutation — see
    `_self_test`'s own comments for why that's a valid, real proof)."""

    def test_self_test_passes(self) -> None:
        _skip_if_no_playwright()
        self.assertTrue(rbq._self_test())


if __name__ == "__main__":
    unittest.main()
