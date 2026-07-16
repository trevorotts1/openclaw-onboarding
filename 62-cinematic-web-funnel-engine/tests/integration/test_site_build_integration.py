#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_site_build_integration.py — integration tests for build unit U15
(scripts/build_site.py + scripts/prove_site.py), the P11-SITE-BUILD phase.

Spec Section 19.2 (integration tests) names "Next.js project generation" as
its own category, distinct from the unit tests in
tests/unit/test_build_site.py and tests/unit/test_prove_site.py (which use
--skip-toolchain / --skip-toolchain-reverify to stay offline). This module
does the real thing: a genuine `npm install` (network), `next lint`, `tsc
--noEmit`, and `next build` (Turbopack) against the deterministic U15
fixture site (spec 19.3's "deterministic fixture site"; the fixture itself
also exercises spec 19.2's "actual FFmpeg fixture processing" via
tests/fixtures/site-fixture/make_fixture.py).

SLOW and requires network + a real Node/npm toolchain — kept out of
tests/unit/ deliberately, same split every other build unit in this skill
uses between fast offline unit coverage and slower integration coverage.

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
import prove_site as ps  # noqa: E402
import make_fixture  # noqa: E402

TOOLCHAIN_TIMEOUT_SECONDS = 300


class TestRealFixtureSiteBuild(unittest.TestCase):
    """One shared, real (network + npm) build for the whole class, reused
    across assertions — a fresh `npm install` per test method would make
    this suite unnecessarily slow without adding coverage."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="cwfe-site-build-integration-")
        cls.run_dir = Path(cls._tmp.name) / "run"
        make_fixture.write_fixture_run_dir(cls.run_dir)
        cls.result = bs.build_site(cls.run_dir, skip_toolchain=False, toolchain_timeout=TOOLCHAIN_TIMEOUT_SECONDS)
        cls.site_dir = cls.result.site_dir

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_receipt_status_pass(self) -> None:
        self.assertEqual(self.result.receipt["status"], "pass")

    def test_all_toolchain_steps_ran_and_succeeded(self) -> None:
        for step in ("install", "lint", "typecheck", "build"):
            self.assertTrue(self.result.receipt["steps"][step]["ran"], step)
            self.assertEqual(self.result.receipt["steps"][step]["exit_code"], 0, step)

    def test_production_build_artifact_exists(self) -> None:
        self.assertTrue((self.site_dir / ".next" / "BUILD_ID").is_file())

    def test_scene_media_copied_into_public(self) -> None:
        for scene_id in ("hero-open", "feature-dive", "cta-close"):
            self.assertTrue((self.site_dir / "public" / "media" / f"{scene_id}.mp4").is_file())
            self.assertTrue((self.site_dir / "public" / "media" / f"{scene_id}.jpg").is_file())

    def test_generated_data_module_typechecks_against_component_types(self) -> None:
        # tsc --noEmit already passed as part of the toolchain above; this
        # assertion pins WHY that's meaningful: SiteData's shape is enforced
        # end-to-end (site-data.generated.ts -> components/types.ts).
        data_ts = (self.site_dir / "lib" / "site-data.generated.ts").read_text(encoding="utf-8")
        self.assertIn("SiteData", data_ts)
        self.assertIn("hero-open.mp4", data_ts)

    def test_prove_site_gate_passes_with_full_independent_reverification(self) -> None:
        passed, detail = ps.evaluate(self.run_dir, skip_toolchain_reverify=False)
        self.assertTrue(passed, detail)


class TestProveSiteFailsClosedOnBrokenBuild(unittest.TestCase):
    """The directive's explicit requirement: 'prove_site.py must fail-closed
    on a broken build.' Builds the real fixture site once, then breaks it
    three DIFFERENT ways (each independently), re-running only prove_site.py
    (which reuses the already-installed node_modules — no re-install per
    case) and asserting FAIL every time, while build-receipt.json keeps
    claiming "pass" throughout (proving this gate never trusts that field)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="cwfe-site-build-broken-")
        cls.run_dir = Path(cls._tmp.name) / "run"
        make_fixture.write_fixture_run_dir(cls.run_dir)
        cls.result = bs.build_site(cls.run_dir, skip_toolchain=False, toolchain_timeout=TOOLCHAIN_TIMEOUT_SECONDS)
        cls.site_dir = cls.result.site_dir
        assert cls.result.receipt["status"] == "pass", "precondition: fixture must build clean before we break it"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _assert_receipt_still_claims_pass(self) -> None:
        receipt = json.loads((self.run_dir / "build-receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "pass", "test setup should not itself touch the receipt")

    def test_typescript_syntax_error_fails_closed(self) -> None:
        target = self.site_dir / "app" / "page.tsx"
        original = target.read_text(encoding="utf-8")
        try:
            target.write_text(original + "\nconst __broken = (;\n", encoding="utf-8")
            self._assert_receipt_still_claims_pass()
            passed, detail = ps.evaluate(self.run_dir, skip_toolchain_reverify=False)
            self.assertFalse(passed)
            self.assertTrue("lint" in detail or "typecheck" in detail or "build" in detail, detail)
        finally:
            target.write_text(original, encoding="utf-8")

    def test_unresolved_import_fails_closed(self) -> None:
        target = self.site_dir / "app" / "page.tsx"
        original = target.read_text(encoding="utf-8")
        try:
            target.write_text(
                'import { DoesNotExist } from "@/components/DoesNotExist";\n' + original, encoding="utf-8"
            )
            self._assert_receipt_still_claims_pass()
            passed, detail = ps.evaluate(self.run_dir, skip_toolchain_reverify=False)
            self.assertFalse(passed)
        finally:
            target.write_text(original, encoding="utf-8")

    def test_type_error_fails_closed(self) -> None:
        target = self.site_dir / "lib" / "site-data.generated.ts"
        original = target.read_text(encoding="utf-8")
        try:
            # architecture is typed as a specific string union in SiteData —
            # assigning a number is a real structural type error.
            broken = original.replace('"architecture":', '"architecture": 42, "__bogus":')
            target.write_text(broken, encoding="utf-8")
            self._assert_receipt_still_claims_pass()
            passed, detail = ps.evaluate(self.run_dir, skip_toolchain_reverify=False)
            self.assertFalse(passed)
        finally:
            target.write_text(original, encoding="utf-8")

    def test_deleted_scene_media_fails_closed_without_any_source_edit(self) -> None:
        video_path = self.site_dir / "public" / "media" / "hero-open.mp4"
        original = video_path.read_bytes()
        try:
            video_path.unlink()
            self._assert_receipt_still_claims_pass()
            passed, detail = ps.evaluate(self.run_dir, skip_toolchain_reverify=False)
            self.assertFalse(passed)
            self.assertIn("missing on disk", detail)
        finally:
            video_path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
