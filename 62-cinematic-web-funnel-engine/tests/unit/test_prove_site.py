#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_prove_site.py — unit tests for build unit U15's gate
(scripts/prove_site.py), the CWFE-MANIFEST.json py_symbol home for
P11-SITE-BUILD (`prove_site.evaluate`).

Fast/offline tests here exercise the independent re-derivation logic
(routes, slug, media-hash cross-check, placeholder/secret re-scan) using
`--skip-toolchain-reverify` so they never shell out to npm (spec 19.1 scope).
The full, non-skipped, REAL npm install/lint/typecheck/build re-verification
— including the fail-closed-on-a-broken-build proof — is
tests/integration/test_site_build_integration.py (spec 19.2/19.4 scope),
mirroring prove_site.py's own `--self-test`.

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
import prove_site as ps  # noqa: E402
import make_fixture  # noqa: E402


def _materialize_offline(run_dir: Path) -> Path:
    """Builds the fixture site with --skip-toolchain (fast, no npm) so
    offline tests get a real materialized site_dir + build-receipt.json to
    probe, without paying the network/build cost. build_site() itself
    raises SiteBuildError in this mode (see test_build_site.py) because a
    skipped toolchain can never count as a genuine pass — that's expected
    and irrelevant here, we only want the receipt/site_dir it still writes
    on the way to raising."""
    make_fixture.write_fixture_run_dir(run_dir)
    try:
        bs.build_site(run_dir, skip_toolchain=True)
    except bs.SiteBuildError:
        pass
    return run_dir


class TestEvaluateOfflineChecks(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cwfe-prove-site-unit-")
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = _materialize_offline(Path(self._tmp.name) / "run")
        self.receipt_path = self.run_dir / "build-receipt.json"
        self.receipt = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        self.site_dir = Path(self.receipt["site_dir"])

    def test_missing_receipt_fails_with_clear_reason(self) -> None:
        empty_dir = Path(self._tmp.name) / "no-receipt-here"
        empty_dir.mkdir()
        passed, detail = ps.evaluate(empty_dir, skip_toolchain_reverify=True)
        self.assertFalse(passed)
        self.assertIn("build-receipt.json not found", detail)

    def test_intact_receipt_passes_non_toolchain_checks(self) -> None:
        passed, detail = ps.evaluate(self.run_dir, skip_toolchain_reverify=True)
        self.assertTrue(passed, detail)

    def test_missing_route_file_fails_closed(self) -> None:
        (self.site_dir / "app" / "page.tsx").unlink()
        passed, detail = ps.evaluate(self.run_dir, skip_toolchain_reverify=True)
        self.assertFalse(passed)
        self.assertIn("route file missing", detail)

    def test_tampered_video_hash_on_disk_detected(self) -> None:
        # Simulate media drift: the file on disk no longer matches what the
        # receipt recorded (e.g. a stray re-encode, or a doctored receipt).
        video_path = self.site_dir / "public" / "media" / "hero-open.mp4"
        original = video_path.read_bytes()
        video_path.write_bytes(original + b"tamper")
        passed, detail = ps.evaluate(self.run_dir, skip_toolchain_reverify=True)
        self.assertFalse(passed)
        self.assertIn("sha256 on disk", detail)

    def test_missing_scene_media_fails_closed(self) -> None:
        (self.site_dir / "public" / "media" / "cta-close.mp4").unlink()
        passed, detail = ps.evaluate(self.run_dir, skip_toolchain_reverify=True)
        self.assertFalse(passed)
        self.assertIn("missing on disk", detail)

    def test_slug_mismatch_detected(self) -> None:
        pkg_path = self.site_dir / "package.json"
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        pkg["name"] = "not-the-real-slug"
        pkg_path.write_text(json.dumps(pkg), encoding="utf-8")
        passed, detail = ps.evaluate(self.run_dir, skip_toolchain_reverify=True)
        self.assertFalse(passed)
        self.assertIn("does not match", detail)

    def test_injected_placeholder_in_generated_data_detected(self) -> None:
        data_path = self.site_dir / "lib" / "site-data.generated.ts"
        data_path.write_text(data_path.read_text(encoding="utf-8") + "\n// TODO: fix this later\n", encoding="utf-8")
        passed, detail = ps.evaluate(self.run_dir, skip_toolchain_reverify=True)
        self.assertFalse(passed)
        self.assertIn("placeholder", detail.lower())

    def test_injected_secret_in_generated_data_detected(self) -> None:
        data_path = self.site_dir / "lib" / "site-data.generated.ts"
        data_path.write_text(
            data_path.read_text(encoding="utf-8") + '\nconst leaked = "sk-abcdefghijklmnopqrstuvwxyz123456";\n',
            encoding="utf-8",
        )
        passed, detail = ps.evaluate(self.run_dir, skip_toolchain_reverify=True)
        self.assertFalse(passed)
        self.assertIn("secret", detail.lower())

    def test_malformed_receipt_json_fails_closed(self) -> None:
        self.receipt_path.write_text("{not valid json", encoding="utf-8")
        passed, detail = ps.evaluate(self.run_dir, skip_toolchain_reverify=True)
        self.assertFalse(passed)
        self.assertIn("not valid JSON", detail)

    def test_receipt_missing_required_field_fails_schema_validation(self) -> None:
        broken = dict(self.receipt)
        del broken["scenes"]
        self.receipt_path.write_text(json.dumps(broken), encoding="utf-8")
        passed, detail = ps.evaluate(self.run_dir, skip_toolchain_reverify=True)
        self.assertFalse(passed)
        self.assertIn("schema validation", detail)

    def test_receipt_claiming_pass_with_no_node_modules_fails_without_skip_flag(self) -> None:
        # Proves the gate does NOT trust a receipt's own claims: even though
        # this receipt exists and every other check passes, omitting
        # --skip-toolchain-reverify with no node_modules present must fail
        # closed rather than silently pass.
        passed, detail = ps.evaluate(self.run_dir, skip_toolchain_reverify=False)
        self.assertFalse(passed)
        self.assertIn("node_modules", detail)


class TestProveSiteCli(unittest.TestCase):
    def test_cli_run_dir_missing_receipt_exits_fail(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-prove-site-cli-") as tmp:
            proc = subprocess.run(
                [sys.executable, str(_SCRIPTS_DIR / "prove_site.py"), "--run-dir", tmp, "--skip-toolchain-reverify"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(proc.returncode, ps.EXIT_FAIL)
            self.assertIn("build-receipt.json not found", proc.stdout)

    def test_cli_usage_error_without_run_dir_or_self_test(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "prove_site.py")],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, ps.EXIT_USAGE)

    def test_cli_nonexistent_run_dir_is_usage_error(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "prove_site.py"), "--run-dir", "/definitely/not/a/real/dir"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, ps.EXIT_USAGE)

    def test_cli_pass_via_subprocess_matches_direct_evaluate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-prove-site-cli-") as tmp:
            run_dir = _materialize_offline(Path(tmp) / "run")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(_SCRIPTS_DIR / "prove_site.py"),
                    "--run-dir",
                    str(run_dir),
                    "--skip-toolchain-reverify",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(proc.returncode, ps.EXIT_OK, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
