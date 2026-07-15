#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_build_site.py — unit tests for build unit U15 (scripts/build_site.py),
the P11-SITE-BUILD producer.

stdlib unittest only, offline, no network/npm/ffmpeg dependency (spec 19.1:
"path sanitization" is a named unit-test category; the real npm/ffmpeg-backed
end-to-end proof — including the fail-closed-on-a-broken-build requirement —
lives in tests/integration/test_site_build_integration.py per the spec 19.1 vs
19.2 split every other unit already follows).

Run with:
  python3 -m unittest discover -s 62-cinematic-web-funnel-engine/tests/unit -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
_STRUCTURE_DIR = Path(__file__).resolve().parents[2] / "structure"
_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "site-fixture"

sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))
sys.path.insert(0, str(_FIXTURE_DIR))

import build_site as bs  # noqa: E402
import json_schema_lite as jsl  # noqa: E402
import make_fixture  # noqa: E402


class TestSanitizeSlug(unittest.TestCase):
    def test_normal_slug_preserved(self) -> None:
        self.assertEqual(bs.sanitize_slug("acme-launch-2026"), "acme-launch-2026")

    def test_uppercase_and_spaces_normalized(self) -> None:
        self.assertEqual(bs.sanitize_slug("Acme Launch 2026"), "acme-launch-2026")

    def test_path_traversal_payload_cannot_survive(self) -> None:
        # spec 19.4 break-it case: "malicious client slug/path traversal".
        # The allowlist transform discards every '.' and '/' outright — no
        # traversal sequence can pass through it.
        slug = bs.sanitize_slug("../../../etc/passwd")
        self.assertNotIn("..", slug)
        self.assertNotIn("/", slug)
        self.assertEqual(slug, "etc-passwd")

    def test_absolute_path_payload_sanitized(self) -> None:
        slug = bs.sanitize_slug("/var/www/../../secrets")
        self.assertNotIn("/", slug)
        self.assertNotIn("..", slug)

    def test_empty_input_raises(self) -> None:
        with self.assertRaises(bs.SiteBuildError):
            bs.sanitize_slug("")

    def test_all_punctuation_input_raises(self) -> None:
        with self.assertRaises(bs.SiteBuildError):
            bs.sanitize_slug("../../../")

    def test_overlong_input_is_truncated_not_rejected(self) -> None:
        slug = bs.sanitize_slug("a" * 200)
        self.assertLessEqual(len(slug), 63)
        self.assertTrue(bs.SLUG_PATTERN.match(slug))

    def test_leading_digit_allowed(self) -> None:
        self.assertEqual(bs.sanitize_slug("2026-launch"), "2026-launch")


class TestSanitizeCopyFragment(unittest.TestCase):
    def test_plain_markup_passes_through(self) -> None:
        html = '<h1>Hello</h1><p>World</p><a href="#book">Book</a>'
        out = bs.sanitize_copy_fragment(html)
        self.assertIn("<h1>Hello</h1>", out)
        self.assertIn('href="#book"', out)

    def test_script_tag_stripped(self) -> None:
        html = '<div>safe<script>alert(1)</script>more</div>'
        out = bs.sanitize_copy_fragment(html)
        self.assertNotIn("<script", out)
        self.assertNotIn("alert(1)", out)
        self.assertIn("safe", out)
        self.assertIn("more", out)

    def test_style_tag_stripped(self) -> None:
        html = "<style>body{display:none}</style><p>text</p>"
        out = bs.sanitize_copy_fragment(html)
        self.assertNotIn("<style", out)
        self.assertIn("<p>text</p>", out)

    def test_event_handler_attribute_removed(self) -> None:
        html = '<button onclick="steal()">Click</button>'
        out = bs.sanitize_copy_fragment(html)
        self.assertNotIn("onclick", out)
        self.assertIn("<button", out)
        self.assertIn("Click", out)

    def test_javascript_href_neutralized(self) -> None:
        html = '<a href="javascript:alert(1)">link</a>'
        out = bs.sanitize_copy_fragment(html)
        self.assertNotIn("javascript:", out)

    def test_normal_href_preserved(self) -> None:
        html = '<a href="https://example.com/book">link</a>'
        out = bs.sanitize_copy_fragment(html)
        self.assertIn("https://example.com/book", out)

    def test_form_action_javascript_neutralized(self) -> None:
        html = '<form action="javascript:evil()"><input/></form>'
        out = bs.sanitize_copy_fragment(html)
        self.assertNotIn("javascript:", out)

    def test_attribute_value_quote_breakout_cannot_smuggle_event_handler(self) -> None:
        # QC U15 finding: a single-quoted source attribute whose value
        # contains a literal `"` was being re-serialized into a
        # double-quoted attribute WITHOUT escaping that embedded quote,
        # letting the value break out and append a live on*= handler that
        # the on*= strip (which only inspects attribute names HTMLParser
        # surfaced, never the re-serialized string) never sees.
        payload = '<a title=\'x" onmouseover="alert(document.cookie)\'>hover me</a>'
        out = bs.sanitize_copy_fragment(payload)
        # `onmouseover` may still appear as inert escaped text inside the
        # title value — what matters is that it is NOT a live attribute:
        # the embedded `"` must be escaped, not left to break the
        # name="value" wrapper open into a second, real attribute.
        self.assertNotIn('title="x" onmouseover="', out)
        self.assertNotIn(" onmouseover=\"alert", out)
        self.assertIn("title=\"x&quot; onmouseover=&quot;alert(document.cookie)\"", out)
        self.assertIn("hover me", out)

    def test_attribute_value_embedded_quote_is_escaped_not_dropped(self) -> None:
        # A benign value containing a double-quote must still round-trip
        # as inert text inside the attribute, not vanish or break parsing.
        html = '<span title=\'say "hi" now\'>x</span>'
        out = bs.sanitize_copy_fragment(html)
        self.assertIn("title=\"say &quot;hi&quot; now\"", out)


class TestScanPlaceholdersAndSecrets(unittest.TestCase):
    def _make_site_dir_with_generated(self, ts_source: str, extra_files: dict[str, str] | None = None) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="cwfe-scan-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        (tmp / "lib").mkdir(parents=True)
        (tmp / "lib" / "site-data.generated.ts").write_text(ts_source, encoding="utf-8")
        for name, content in (extra_files or {}).items():
            (tmp / name).write_text(content, encoding="utf-8")
        return tmp

    def test_clean_data_passes_both_scans(self) -> None:
        site_dir = self._make_site_dir_with_generated('export const SITE_DATA = { meta: { title: "Real Title" } };')
        ok_ph, matches_ph = bs.scan_placeholders(site_dir)
        ok_sec, matches_sec = bs.scan_secrets(site_dir)
        self.assertTrue(ok_ph, matches_ph)
        self.assertTrue(ok_sec, matches_sec)

    def test_lorem_ipsum_flagged(self) -> None:
        site_dir = self._make_site_dir_with_generated('export const SITE_DATA = { title: "Lorem Ipsum dolor" };')
        ok, matches = bs.scan_placeholders(site_dir)
        self.assertFalse(ok)
        self.assertTrue(matches)

    def test_todo_marker_flagged(self) -> None:
        site_dir = self._make_site_dir_with_generated('export const SITE_DATA = { title: "TODO: replace me" };')
        ok, matches = bs.scan_placeholders(site_dir)
        self.assertFalse(ok)

    def test_unreplaced_template_token_flagged(self) -> None:
        site_dir = self._make_site_dir_with_generated('export const SITE_DATA = { title: "{{project_name}}" };')
        ok, matches = bs.scan_placeholders(site_dir)
        self.assertFalse(ok)

    def test_ghl_pit_token_pattern_flagged(self) -> None:
        site_dir = self._make_site_dir_with_generated(
            'export const SITE_DATA = { note: "pit-abcdefghijklmnopqrstuvwx" };'
        )
        ok, matches = bs.scan_secrets(site_dir)
        self.assertFalse(ok, matches)

    def test_openai_style_secret_flagged(self) -> None:
        site_dir = self._make_site_dir_with_generated(
            'export const SITE_DATA = { note: "sk-abcdefghijklmnopqrstuvwxyz123456" };'
        )
        ok, matches = bs.scan_secrets(site_dir)
        self.assertFalse(ok, matches)

    def test_generic_api_key_literal_flagged(self) -> None:
        site_dir = self._make_site_dir_with_generated(
            'export const SITE_DATA = {};', extra_files={"package.json": '{"apiKey": "abcdefghijklmnop1234"}'}
        )
        ok, matches = bs.scan_secrets(site_dir)
        self.assertFalse(ok, matches)


class TestResolveSceneMedia(unittest.TestCase):
    def _scene_plan(self, scene_ids: list[str]) -> dict:
        return {"scenes": [{"scene_id": sid} for sid in scene_ids]}

    def test_missing_media_raises_with_scene_names(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="cwfe-media-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        with self.assertRaises(bs.SiteBuildError) as ctx:
            bs.resolve_scene_media(self._scene_plan(["hero", "cta"]), tmp)
        self.assertIn("hero", str(ctx.exception))
        self.assertIn("cta", str(ctx.exception))

    def test_zero_byte_media_raises(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="cwfe-media-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        (tmp / "hero.mp4").write_bytes(b"")
        (tmp / "hero.jpg").write_bytes(b"")
        with self.assertRaises(bs.SiteBuildError) as ctx:
            bs.resolve_scene_media(self._scene_plan(["hero"]), tmp)
        self.assertIn("zero-byte", str(ctx.exception))

    def test_valid_media_resolves_with_correct_hashes(self) -> None:
        import hashlib

        tmp = Path(tempfile.mkdtemp(prefix="cwfe-media-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        video_bytes = b"fake-mp4-bytes"
        poster_bytes = b"fake-jpg-bytes"
        (tmp / "hero.mp4").write_bytes(video_bytes)
        (tmp / "hero.jpg").write_bytes(poster_bytes)
        resolved = bs.resolve_scene_media(self._scene_plan(["hero"]), tmp)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].video_sha256, hashlib.sha256(video_bytes).hexdigest())
        self.assertEqual(resolved[0].poster_sha256, hashlib.sha256(poster_bytes).hexdigest())
        self.assertEqual(resolved[0].video_bytes, len(video_bytes))

    def test_missing_media_dir_raises(self) -> None:
        with self.assertRaises(bs.SiteBuildError):
            bs.resolve_scene_media(self._scene_plan(["hero"]), Path("/nonexistent/does/not/exist"))


class TestLoadLockedContentManifest(unittest.TestCase):
    def test_unlocked_manifest_rejected(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="cwfe-manifest-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        fields = make_fixture.build_content_manifest()
        fields["locked"] = False
        (tmp / "content-manifest.json").write_text(json.dumps(fields), encoding="utf-8")
        with self.assertRaises(bs.SiteBuildError) as ctx:
            bs.load_locked_content_manifest(tmp)
        self.assertIn("lock", str(ctx.exception).lower())

    def test_tampered_content_hash_rejected(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="cwfe-manifest-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        fields = make_fixture.build_content_manifest()
        fields["cta_map"] = {"tampered": True}  # content-bearing field changed post-hash
        (tmp / "content-manifest.json").write_text(json.dumps(fields), encoding="utf-8")
        with self.assertRaises(bs.SiteBuildError) as ctx:
            bs.load_locked_content_manifest(tmp)
        self.assertIn("hash", str(ctx.exception).lower())

    def test_missing_manifest_raises(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="cwfe-manifest-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        with self.assertRaises(bs.SiteBuildError):
            bs.load_locked_content_manifest(tmp)

    def test_valid_locked_manifest_loads(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="cwfe-manifest-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        fields = make_fixture.build_content_manifest()
        (tmp / "content-manifest.json").write_text(json.dumps(fields), encoding="utf-8")
        loaded = bs.load_locked_content_manifest(tmp)
        self.assertEqual(loaded["project_id"], "u15-fixture-site")


class TestReadCopySections(unittest.TestCase):
    def test_mismatched_array_lengths_raise(self) -> None:
        manifest = {"section_order": ["a", "b"], "approved_copy_paths": ["/only/one"]}
        with self.assertRaises(bs.SiteBuildError):
            bs.read_copy_sections(manifest)

    def test_missing_fragment_file_raises(self) -> None:
        manifest = {"section_order": ["a"], "approved_copy_paths": ["/definitely/not/a/real/path.html"]}
        with self.assertRaises(bs.SiteBuildError):
            bs.read_copy_sections(manifest)

    def test_real_fixture_fragments_read_and_sanitize(self) -> None:
        manifest = make_fixture.build_content_manifest()
        sections = bs.read_copy_sections(manifest)
        self.assertEqual([s["id"] for s in sections], ["hero", "proof", "cta"])
        self.assertIn("Book Your Strategy Call", sections[0]["html"])


class TestMaterializeTemplateOffline(unittest.TestCase):
    """Covers the materialization + data-generation + check logic without
    ever invoking npm/node (spec 19.1 unit-test scope)."""

    def test_skip_toolchain_writes_failed_receipt_with_ran_false_steps(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-build-site-offline-") as tmp:
            run_dir = Path(tmp) / "run"
            make_fixture.write_fixture_run_dir(run_dir)
            with self.assertRaises(bs.SiteBuildError):
                # skip_toolchain=True means install/lint/typecheck/build never
                # run, so toolchain_ok is vacuously true (skip=True), but we
                # still exercise the full materialization path and prove the
                # receipt records ran=False for every step.
                bs.build_site(run_dir, skip_toolchain=True)
            receipt_path = run_dir / "build-receipt.json"
            self.assertTrue(receipt_path.is_file())
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            for step in ("install", "lint", "typecheck", "build"):
                self.assertFalse(receipt["steps"][step]["ran"])
            # Materialization itself (not the toolchain) must have fully
            # succeeded: routes present, media copied, data file written.
            self.assertEqual(receipt["routes"], ["app/layout.tsx", "app/page.tsx"])
            self.assertTrue(receipt["checks"]["media_references_resolve"])
            site_dir = Path(receipt["site_dir"])
            self.assertTrue((site_dir / "lib" / "site-data.generated.ts").is_file())
            self.assertTrue((site_dir / "public" / "media" / "hero-open.mp4").is_file())
            self.assertTrue((site_dir / "components" / "ScrollScrubEngine.tsx").is_file())

    def test_skip_toolchain_receipt_is_schema_valid(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-build-site-offline-") as tmp:
            run_dir = Path(tmp) / "run"
            make_fixture.write_fixture_run_dir(run_dir)
            with self.assertRaises(bs.SiteBuildError):
                bs.build_site(run_dir, skip_toolchain=True)
            receipt = json.loads((run_dir / "build-receipt.json").read_text(encoding="utf-8"))
            schema = json.loads((_STRUCTURE_DIR / "build-receipt.schema.json").read_text(encoding="utf-8"))
            errors = jsl.validate(receipt, schema)
            self.assertEqual(errors, [])

    def test_malicious_project_slug_override_sanitized_not_rejected_outright(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-build-site-offline-") as tmp:
            run_dir = Path(tmp) / "run"
            make_fixture.write_fixture_run_dir(run_dir)
            with self.assertRaises(bs.SiteBuildError):
                bs.build_site(run_dir, project_slug="../../../etc/passwd", skip_toolchain=True)
            receipt = json.loads((run_dir / "build-receipt.json").read_text(encoding="utf-8"))
            self.assertNotIn("..", receipt["project_slug"])
            self.assertNotIn("/", receipt["project_slug"])

    def test_dir_hash_is_deterministic_across_two_materializations(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-build-site-offline-") as tmp:
            run_dir1 = Path(tmp) / "run1"
            run_dir2 = Path(tmp) / "run2"
            make_fixture.write_fixture_run_dir(run_dir1)
            make_fixture.write_fixture_run_dir(run_dir2)
            with self.assertRaises(bs.SiteBuildError):
                bs.build_site(run_dir1, skip_toolchain=True)
            with self.assertRaises(bs.SiteBuildError):
                bs.build_site(run_dir2, skip_toolchain=True)
            r1 = json.loads((run_dir1 / "build-receipt.json").read_text(encoding="utf-8"))
            r2 = json.loads((run_dir2 / "build-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(r1["template_source"], r2["template_source"])


class TestBuildReceiptSchemaFile(unittest.TestCase):
    def test_schema_file_is_valid_json(self) -> None:
        schema = json.loads((_STRUCTURE_DIR / "build-receipt.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["required"][0], "schema_version")


if __name__ == "__main__":
    unittest.main()
