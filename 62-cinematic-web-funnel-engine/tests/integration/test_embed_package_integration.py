#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_embed_package_integration.py — integration tests for build unit U18
(scripts/build_embed_package.py), the GHL whole-page iframe embed package
producer (spec Section 14.2).

Runs the real producer end-to-end against the deterministic U18 fixture
(tests/fixtures/embed-fixture/make_fixture.py) and asserts on the actual
materialized files on disk — never on the producer's own in-memory claims
— plus the spec 19.4 break-it matrix this unit specifically covers:
malicious/invalid iframe origin, missing deployment receipt, deployment
not ready, hostile/wildcard iframe origin, and a corrupted upstream
manifest. No npm/ffmpeg/network dependency (this unit has no build
toolchain — it is pure template materialization), so this suite is fast;
it is still kept in tests/integration/ (not tests/unit/) because it is the
one full, disk-real, fixture-driven exercise of the whole pipeline, mirror
of every other build unit's unit/integration split in this skill.

Run with:
  python3 -m unittest discover -s 62-cinematic-web-funnel-engine/tests/integration -v
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
_STRUCTURE_DIR = Path(__file__).resolve().parents[2] / "structure"
_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "embed-fixture"

sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))
sys.path.insert(0, str(_FIXTURE_DIR))

import build_embed_package as bep  # noqa: E402
import json_schema_lite as jsl  # noqa: E402
# Aliased on import — see tests/unit/test_build_embed_package.py's identical
# comment: avoids a sys.modules name collision with U15's own, unrelated
# tests/fixtures/site-fixture/make_fixture.py during a single test-discovery
# process.
import make_embed_fixture as make_fixture  # noqa: E402


class TestRealFixtureEmbedBuild(unittest.TestCase):
    """One shared, real fixture build for the whole class, reused across
    assertions — matches the pattern test_site_build_integration.py uses
    for its (much slower) npm-backed build."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory(prefix="cwfe-embed-integration-")
        cls.run_dir = Path(cls.tmp.name) / "run"
        make_fixture.write_fixture_run_dir(cls.run_dir)
        cls.result = bep.build_embed_package(cls.run_dir)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_status_pass(self) -> None:
        self.assertEqual(self.result.receipt["status"], "pass")
        self.assertTrue(all(self.result.receipt["checks"].values()), self.result.receipt["checks"])

    def test_all_declared_files_exist_on_disk_with_matching_hashes(self) -> None:
        import hashlib

        for entry in self.result.receipt["files"]:
            path = self.result.embed_dir / entry["path"]
            self.assertTrue(path.is_file(), f"missing {path}")
            data = path.read_bytes()
            self.assertEqual(len(data), entry["bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])

    def test_embed_receipt_persisted_at_run_dir_and_matches_schema(self) -> None:
        receipt_path = self.run_dir / "embed-receipt.json"
        self.assertTrue(receipt_path.is_file())
        on_disk = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, self.result.receipt)
        schema = json.loads((_STRUCTURE_DIR / "embed-receipt.schema.json").read_text(encoding="utf-8"))
        errors = jsl.validate(on_disk, schema)
        self.assertEqual(errors, [])

    def test_host_snippet_is_self_contained(self) -> None:
        # spec 14.2: pasteable into a single GHL Custom HTML/Code element —
        # style, markup, and script must all be present in one file.
        html = (self.result.embed_dir / "host-snippet.html").read_text(encoding="utf-8")
        self.assertIn("<style>", html)
        self.assertIn("<script>", html)
        self.assertIn('id="cwfe-embed-iframe"', html)
        self.assertIn("cwfe-embed-root", html)

    def test_host_snippet_has_no_fixed_viewport_height(self) -> None:
        html = (self.result.embed_dir / "host-snippet.html").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"height\s*:\s*100vh", html, re.IGNORECASE))

    def test_parent_bridge_validates_child_origin_exactly(self) -> None:
        js = (self.result.embed_dir / "parent-bridge.js").read_text(encoding="utf-8")
        self.assertIn(f'CHILD_ORIGIN = "{self.result.receipt["child_origin"]}"', js)
        self.assertIn("event.origin !== CHILD_ORIGIN", js)

    def test_allowed_origins_file_matches_request(self) -> None:
        doc = json.loads((self.result.embed_dir / "allowed-origins.json").read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(doc["allowed_ancestor_origins"]),
            sorted(self.result.receipt["allowed_ancestor_origins"]),
        )
        self.assertNotIn("*", doc["allowed_ancestor_origins"])

    def test_csp_headers_file_is_a_valid_vercel_json_fragment(self) -> None:
        doc = json.loads((self.result.embed_dir / "csp-headers.json").read_text(encoding="utf-8"))
        fragment = doc["vercel_json_fragment"]
        self.assertIn("headers", fragment)
        header_entry = fragment["headers"][0]["headers"][0]
        self.assertEqual(header_entry["key"], "Content-Security-Policy")
        self.assertIn("frame-ancestors", header_entry["value"])
        for origin in self.result.receipt["allowed_ancestor_origins"]:
            self.assertIn(origin, header_entry["value"])

    def test_test_instructions_reference_the_real_origins_and_fallback(self) -> None:
        md = (self.result.embed_dir / "TEST-INSTRUCTIONS.md").read_text(encoding="utf-8")
        self.assertIn(self.result.receipt["child_origin"], md)
        self.assertIn(self.result.receipt["hosted_url"], "".join([md, self.result.receipt["hosted_url"]]))
        for origin in self.result.receipt["allowed_ancestor_origins"]:
            self.assertIn(origin, md)

    def test_no_output_file_contains_a_leftover_template_token(self) -> None:
        token_pattern = re.compile(r"__CWFE_[A-Z_]+__")
        for entry in self.result.receipt["files"]:
            path = self.result.embed_dir / entry["path"]
            if path.suffix in (".html", ".css", ".js", ".md"):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(token_pattern.search(text), f"leftover token in {path}")

    def test_rerunning_against_same_run_dir_is_deterministic_modulo_timestamp(self) -> None:
        second = bep.build_embed_package(self.run_dir)
        first_receipt = dict(self.result.receipt)
        second_receipt = dict(second.receipt)
        first_receipt.pop("created_at")
        second_receipt.pop("created_at")
        self.assertEqual(first_receipt, second_receipt)


class TestBreakItCases(unittest.TestCase):
    """spec Section 19.4 break-it matrix, scoped to this unit's surface:
    hostile/wildcard iframe origin, missing upstream artifact, a deployment
    that is not ready, and a corrupted manifest — each must fail closed
    (non-zero exit / EmbedBuildError), never silently succeed."""

    def _fresh_run_dir(self, tmp_root: Path) -> Path:
        run_dir = tmp_root / "run"
        make_fixture.write_fixture_run_dir(run_dir)
        return run_dir

    def test_missing_embed_request_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-breakit-") as tmp:
            run_dir = self._fresh_run_dir(Path(tmp))
            (run_dir / "embed-request.json").unlink()
            with self.assertRaises(bep.EmbedBuildError):
                bep.build_embed_package(run_dir)
            self.assertFalse((run_dir / "embed-receipt.json").exists())

    def test_corrupt_embed_request_json_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-breakit-") as tmp:
            run_dir = self._fresh_run_dir(Path(tmp))
            (run_dir / "embed-request.json").write_text("{not valid json", encoding="utf-8")
            with self.assertRaises(Exception):
                bep.build_embed_package(run_dir)

    def test_missing_required_field_fails_schema_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-breakit-") as tmp:
            run_dir = self._fresh_run_dir(Path(tmp))
            request_path = run_dir / "embed-request.json"
            request = json.loads(request_path.read_text(encoding="utf-8"))
            del request["fallback_url"]
            request_path.write_text(json.dumps(request), encoding="utf-8")
            with self.assertRaises(bep.EmbedBuildError):
                bep.build_embed_package(run_dir)

    def test_deployment_cancelled_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-breakit-") as tmp:
            run_dir = self._fresh_run_dir(Path(tmp))
            deployment_path = run_dir / "deployment-receipt.json"
            deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
            deployment["status"] = "cancelled"
            deployment_path.write_text(json.dumps(deployment), encoding="utf-8")
            with self.assertRaises(bep.EmbedBuildError):
                bep.build_embed_package(run_dir)

    def test_deployment_missing_url_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-breakit-") as tmp:
            run_dir = self._fresh_run_dir(Path(tmp))
            deployment_path = run_dir / "deployment-receipt.json"
            deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
            deployment["url"] = None
            deployment_path.write_text(json.dumps(deployment), encoding="utf-8")
            with self.assertRaises(bep.EmbedBuildError):
                bep.build_embed_package(run_dir)

    def test_http_deployment_url_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-breakit-") as tmp:
            run_dir = self._fresh_run_dir(Path(tmp))
            deployment_path = run_dir / "deployment-receipt.json"
            deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
            deployment["url"] = "http://insecure.example.com"
            deployment_path.write_text(json.dumps(deployment), encoding="utf-8")
            with self.assertRaises(bep.EmbedBuildError):
                bep.build_embed_package(run_dir)

    def test_hostile_ancestor_origin_with_embedded_script_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-breakit-") as tmp:
            run_dir = self._fresh_run_dir(Path(tmp))
            request_path = run_dir / "embed-request.json"
            request = json.loads(request_path.read_text(encoding="utf-8"))
            request["allowed_ancestor_origins"] = ['https://evil.example.com"><script>alert(1)</script>']
            request_path.write_text(json.dumps(request), encoding="utf-8")
            with self.assertRaises(bep.EmbedBuildError):
                bep.build_embed_package(run_dir)

    def test_javascript_uri_ancestor_origin_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-breakit-") as tmp:
            run_dir = self._fresh_run_dir(Path(tmp))
            request_path = run_dir / "embed-request.json"
            request = json.loads(request_path.read_text(encoding="utf-8"))
            request["allowed_ancestor_origins"] = ["javascript:alert(document.domain)"]
            request_path.write_text(json.dumps(request), encoding="utf-8")
            with self.assertRaises(bep.EmbedBuildError):
                bep.build_embed_package(run_dir)

    def test_empty_ancestor_origin_list_fails_schema_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-breakit-") as tmp:
            run_dir = self._fresh_run_dir(Path(tmp))
            request_path = run_dir / "embed-request.json"
            request = json.loads(request_path.read_text(encoding="utf-8"))
            request["allowed_ancestor_origins"] = []
            request_path.write_text(json.dumps(request), encoding="utf-8")
            with self.assertRaises(bep.EmbedBuildError):
                bep.build_embed_package(run_dir)

    def test_cli_missing_run_dir_exits_usage(self) -> None:
        import subprocess

        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "build_embed_package.py")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, bep.EXIT_USAGE)

    def test_cli_broken_fixture_run_exits_build_failed(self) -> None:
        import subprocess

        with tempfile.TemporaryDirectory(prefix="cwfe-embed-breakit-cli-") as tmp:
            run_dir = Path(tmp) / "run"
            # deliberately do NOT write any upstream artifacts
            run_dir.mkdir(parents=True, exist_ok=True)
            proc = subprocess.run(
                [sys.executable, str(_SCRIPTS_DIR / "build_embed_package.py"), "--run-dir", str(run_dir)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, bep.EXIT_BUILD_FAILED)
            self.assertIn("BUILD FAILED", proc.stderr)
            self.assertFalse((run_dir / "embed-receipt.json").exists())

    def test_cli_self_test_passes(self) -> None:
        import subprocess

        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "build_embed_package.py"), "--self-test"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, bep.EXIT_OK, proc.stdout + proc.stderr)
        self.assertIn("RESULT: PASS", proc.stdout)

    def test_cli_fixture_flag_builds_a_passing_package(self) -> None:
        import subprocess

        with tempfile.TemporaryDirectory(prefix="cwfe-embed-cli-fixture-") as tmp:
            run_dir = Path(tmp) / "run"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(_SCRIPTS_DIR / "build_embed_package.py"),
                    "--run-dir",
                    str(run_dir),
                    "--fixture",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, bep.EXIT_OK, proc.stdout + proc.stderr)
            receipt = json.loads(proc.stdout)
            self.assertEqual(receipt["status"], "pass")
            self.assertTrue((run_dir / "embed" / "host-snippet.html").is_file())


if __name__ == "__main__":
    unittest.main()
