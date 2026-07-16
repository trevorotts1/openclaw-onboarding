#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_run_browser_qc.py — unit tests for build unit U19's gate
(scripts/run_browser_qc.py), the CWFE-MANIFEST.json py_symbol home for
P13-BROWSER-QC (`run_browser_qc.evaluate`).

Fast/offline tests here exercise every piece of logic that does NOT require
a real browser or a real `next start` server: build-receipt.json loading/
validation, the mount-radius source-of-truth parser, the project-relative
media-budget derivation, server lifecycle helpers (port allocation,
precondition checks), and the CLI's usage-error paths. The real Playwright
+ Chromium + `next start` proof — including the module's own `--self-test`
break-it mutations — is tests/integration/test_browser_qc_integration.py,
mirroring the split every other browser/toolchain-touching unit in this
skill already uses (test_prove_site.py / test_site_build_integration.py).

Run with:
  python3 -m unittest discover -s 62-cinematic-web-funnel-engine/tests/unit -v
"""

from __future__ import annotations

import json
import subprocess
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
import make_fixture  # noqa: E402
import run_browser_qc as rbq  # noqa: E402


def _materialize_offline(run_dir: Path) -> Path:
    """Same offline-materialization trick test_prove_site.py uses: a real
    build-receipt.json + site_dir on disk without paying the real npm/build
    cost, for tests that only need the RECEIPT shape and the materialized
    components/ directory (e.g. useScrollScrub.ts for the mount-radius
    parser), not a running server."""
    make_fixture.write_fixture_run_dir(run_dir)
    try:
        bs.build_site(run_dir, skip_toolchain=True)
    except bs.SiteBuildError:
        pass
    return run_dir


class TestLoadBuildReceipt(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cwfe-browser-qc-unit-")
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = _materialize_offline(Path(self._tmp.name) / "run")
        self.receipt_path = self.run_dir / "build-receipt.json"
        self.receipt = json.loads(self.receipt_path.read_text(encoding="utf-8"))

    def test_missing_receipt_raises_clear_error(self) -> None:
        empty_dir = Path(self._tmp.name) / "no-receipt"
        empty_dir.mkdir()
        with self.assertRaises(rbq.BrowserQcError) as ctx:
            rbq._load_build_receipt(empty_dir)
        self.assertIn("build-receipt.json not found", str(ctx.exception))

    def test_malformed_json_raises_clear_error(self) -> None:
        self.receipt_path.write_text("{not valid json", encoding="utf-8")
        with self.assertRaises(rbq.BrowserQcError) as ctx:
            rbq._load_build_receipt(self.run_dir)
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_schema_invalid_receipt_raises_clear_error(self) -> None:
        broken = dict(self.receipt)
        del broken["scenes"]
        self.receipt_path.write_text(json.dumps(broken), encoding="utf-8")
        with self.assertRaises(rbq.BrowserQcError) as ctx:
            rbq._load_build_receipt(self.run_dir)
        self.assertIn("schema validation", str(ctx.exception))

    def test_offline_skip_toolchain_receipt_has_failed_status_and_is_rejected(self) -> None:
        # build_site() with skip_toolchain=True always writes status="failed"
        # (a skipped toolchain can never count as a pass, per build_site.py's
        # own docstring) — confirms run_browser_qc never treats a
        # not-actually-passing receipt as good enough to proceed.
        self.assertEqual(self.receipt["status"], "failed")
        with self.assertRaises(rbq.BrowserQcError) as ctx:
            rbq._load_build_receipt(self.run_dir)
        self.assertIn("not 'pass'", str(ctx.exception))

    def test_valid_pass_receipt_loads_cleanly(self) -> None:
        passing = dict(self.receipt)
        passing["status"] = "pass"
        self.receipt_path.write_text(json.dumps(passing), encoding="utf-8")
        loaded = rbq._load_build_receipt(self.run_dir)
        self.assertEqual(loaded["status"], "pass")


class TestNeighborMountRadius(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cwfe-browser-qc-mountradius-")
        self.addCleanup(self._tmp.cleanup)
        self.site_dir = Path(self._tmp.name) / "site"
        (self.site_dir / "components").mkdir(parents=True)

    def test_reads_real_constant_from_materialized_components_dir(self) -> None:
        real_source = (
            Path(__file__).resolve().parents[2] / "templates" / "components" / "useScrollScrub.ts"
        ).read_text(encoding="utf-8")
        (self.site_dir / "components" / "useScrollScrub.ts").write_text(real_source, encoding="utf-8")
        radius = rbq._neighbor_mount_radius(self.site_dir)
        self.assertEqual(radius, 1)  # NEIGHBOR_MOUNT_RADIUS = 1 in the real template as of U19

    def test_missing_file_fails_closed(self) -> None:
        with self.assertRaises(rbq.BrowserQcError) as ctx:
            rbq._neighbor_mount_radius(self.site_dir)
        self.assertIn("not found", str(ctx.exception))

    def test_missing_constant_in_file_fails_closed_rather_than_guessing(self) -> None:
        (self.site_dir / "components" / "useScrollScrub.ts").write_text(
            "export const SOMETHING_ELSE = 5;\n", encoding="utf-8"
        )
        with self.assertRaises(rbq.BrowserQcError) as ctx:
            rbq._neighbor_mount_radius(self.site_dir)
        self.assertIn("refusing to guess", str(ctx.exception))


class TestComputeMediaBudgets(unittest.TestCase):
    def test_derives_project_relative_budgets_from_receipt_scenes(self) -> None:
        receipt = {
            "scenes": [
                {"video_bytes": 1000, "poster_bytes": 100},
                {"video_bytes": 3000, "poster_bytes": 200},
                {"video_bytes": 500, "poster_bytes": 50},
            ]
        }
        initial_budget, total_budget = rbq._compute_media_budgets(receipt, mount_radius=1)
        # max single scene = 3000 + 200 = 3200; max_mounted = 2*1+1 = 3
        expected_initial = int(3 * 3200 * rbq.MEDIA_INITIAL_HEADROOM)
        expected_total = int((1100 + 3200 + 550) * rbq.MEDIA_TOTAL_HEADROOM)
        self.assertEqual(initial_budget, expected_initial)
        self.assertEqual(total_budget, expected_total)

    def test_no_scenes_fails_closed_rather_than_a_zero_budget(self) -> None:
        with self.assertRaises(rbq.BrowserQcError) as ctx:
            rbq._compute_media_budgets({"scenes": []}, mount_radius=1)
        self.assertIn("no scenes", str(ctx.exception))

    def test_larger_mount_radius_scales_the_initial_budget_up(self) -> None:
        receipt = {"scenes": [{"video_bytes": 1000, "poster_bytes": 0}]}
        b1, _ = rbq._compute_media_budgets(receipt, mount_radius=1)
        b2, _ = rbq._compute_media_budgets(receipt, mount_radius=2)
        self.assertGreater(b2, b1)


class TestServerLifecycleHelpers(unittest.TestCase):
    def test_find_free_port_returns_a_bindable_port(self) -> None:
        import socket

        port = rbq._find_free_port()
        self.assertGreater(port, 0)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))  # would raise OSError if genuinely unavailable

    def test_start_server_fails_closed_without_node_modules(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-browser-qc-server-") as tmp:
            site_dir = Path(tmp) / "site"
            site_dir.mkdir()
            with self.assertRaises(rbq.BrowserQcError) as ctx:
                rbq._start_server(site_dir, 39999, Path(tmp) / "server.log")
            self.assertIn("node_modules", str(ctx.exception))

    def test_start_server_fails_closed_without_next_build(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-browser-qc-server-") as tmp:
            site_dir = Path(tmp) / "site"
            (site_dir / "node_modules").mkdir(parents=True)
            with self.assertRaises(rbq.BrowserQcError) as ctx:
                rbq._start_server(site_dir, 39999, Path(tmp) / "server.log")
            self.assertIn(".next", str(ctx.exception))

    def test_wait_for_server_times_out_on_an_unreachable_port(self) -> None:
        with self.assertRaises(rbq.BrowserQcError) as ctx:
            rbq._wait_for_server("http://127.0.0.1:1/", timeout=0.6)
        self.assertIn("did not become ready", str(ctx.exception))


class TestEvaluateUsagePaths(unittest.TestCase):
    """evaluate()'s own precondition failures — no playwright/browser/server
    needed to reach these, since they all short-circuit before launching
    anything (schema/receipt/site_dir checks all happen first)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cwfe-browser-qc-evaluate-")
        self.addCleanup(self._tmp.cleanup)

    def test_missing_receipt(self) -> None:
        empty_dir = Path(self._tmp.name) / "no-receipt"
        empty_dir.mkdir()
        passed, detail = rbq.evaluate(empty_dir)
        self.assertFalse(passed)
        self.assertIn("build-receipt.json not found", detail)

    def test_receipt_with_nonexistent_site_dir(self) -> None:
        run_dir = _materialize_offline(Path(self._tmp.name) / "run")
        receipt_path = run_dir / "build-receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["status"] = "pass"
        receipt["site_dir"] = str(Path(self._tmp.name) / "does-not-exist")
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        passed, detail = rbq.evaluate(run_dir)
        self.assertFalse(passed)
        self.assertIn("does not exist on disk", detail)


class TestReportSchema(unittest.TestCase):
    def test_schema_file_is_valid_json_and_self_consistent(self) -> None:
        import json_schema_lite as jsl

        schema = json.loads((rbq._STRUCTURE_DIR / "browser-qc-report.schema.json").read_text(encoding="utf-8"))
        sample = {
            "schema_version": "1.0.0",
            "project_id": "demo",
            "site_dir": "/tmp/x",
            "server_url": "http://127.0.0.1:1234/",
            "categories": {
                "desktop": {"passed": True, "violations": []},
                "mobile": {"passed": True, "violations": []},
                "reduced_motion": {"passed": True, "violations": []},
                "accessibility": {"passed": True, "violations": []},
                "performance": {
                    "passed": True,
                    "violations": [],
                    "measurements": {
                        "initial_js_bytes": 1,
                        "initial_media_bytes": 1,
                        "total_media_bytes_after_full_scroll": 1,
                        "first_contentful_paint_ms": 1.0,
                        "cumulative_layout_shift": 0.0,
                        "max_mounted_video_elements": 1,
                    },
                    "budgets": {
                        "initial_js_bytes": 1,
                        "initial_media_bytes": 1,
                        "total_media_bytes": 1,
                        "first_contentful_paint_ms": 1.0,
                        "cumulative_layout_shift": 0.1,
                        "max_mounted_video_elements": 3,
                    },
                    "lcp_status": "unavailable_in_headless_harness_fcp_used",
                },
            },
            "overall_status": "pass",
            "created_at": "2026-07-15T00:00:00Z",
        }
        errors = jsl.validate(sample, schema)
        self.assertEqual(errors, [])

    def test_schema_rejects_missing_category(self) -> None:
        import json_schema_lite as jsl

        schema = json.loads((rbq._STRUCTURE_DIR / "browser-qc-report.schema.json").read_text(encoding="utf-8"))
        sample = {
            "schema_version": "1.0.0",
            "project_id": "demo",
            "site_dir": "/tmp/x",
            "server_url": "http://127.0.0.1:1234/",
            "categories": {},
            "overall_status": "pass",
            "created_at": "2026-07-15T00:00:00Z",
        }
        errors = jsl.validate(sample, schema)
        self.assertTrue(errors)


class TestCli(unittest.TestCase):
    def test_cli_usage_error_without_run_dir_or_self_test(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "run_browser_qc.py")],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, rbq.EXIT_USAGE)

    def test_cli_nonexistent_run_dir_is_usage_error(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "run_browser_qc.py"), "--run-dir", "/definitely/not/a/real/dir"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, rbq.EXIT_USAGE)

    def test_cli_missing_receipt_exits_fail_not_usage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-browser-qc-cli-") as tmp:
            proc = subprocess.run(
                [sys.executable, str(_SCRIPTS_DIR / "run_browser_qc.py"), "--run-dir", tmp],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(proc.returncode, rbq.EXIT_FAIL)
            self.assertIn("build-receipt.json not found", proc.stdout)


if __name__ == "__main__":
    unittest.main()
