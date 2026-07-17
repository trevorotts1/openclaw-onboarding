#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_build_embed_package.py — unit tests for build unit U18
(scripts/build_embed_package.py), the GHL whole-page iframe embed package
producer (spec Section 14.2).

stdlib unittest only, offline, no network dependency — this module has no
npm/ffmpeg toolchain step (it is pure template materialization + file I/O),
so unlike U15's build_site.py there is no --skip-toolchain fast path to
reach for; every test here already runs the real build_embed_package().
tests/integration/test_embed_package_integration.py additionally exercises
the fixture end-to-end plus the full spec 19.4 break-it matrix.

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
_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "embed-fixture"

sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))
sys.path.insert(0, str(_FIXTURE_DIR))

import build_embed_package as bep  # noqa: E402
import json_schema_lite as jsl  # noqa: E402
# Aliased on import: tests/fixtures/site-fixture/ ships its OWN unrelated
# make_fixture.py for U15. Both fixture directories get inserted onto
# sys.path across a single `unittest discover` process, and Python caches
# imports by top-level module name — importing under the literal name
# "make_fixture" here would let whichever fixture's test module runs first
# silently shadow the other's module for every test that runs after it.
import make_embed_fixture as make_fixture  # noqa: E402


class TestSanitizeSlug(unittest.TestCase):
    def test_normal_slug_preserved(self) -> None:
        self.assertEqual(bep.sanitize_slug("acme-launch-2026"), "acme-launch-2026")

    def test_uppercase_and_spaces_normalized(self) -> None:
        self.assertEqual(bep.sanitize_slug("Acme Launch 2026"), "acme-launch-2026")

    def test_path_traversal_payload_cannot_survive(self) -> None:
        slug = bep.sanitize_slug("../../../etc/passwd")
        self.assertNotIn("..", slug)
        self.assertNotIn("/", slug)
        self.assertEqual(slug, "etc-passwd")

    def test_empty_input_raises(self) -> None:
        with self.assertRaises(bep.EmbedBuildError):
            bep.sanitize_slug("")

    def test_only_symbols_raises(self) -> None:
        with self.assertRaises(bep.EmbedBuildError):
            bep.sanitize_slug("!!!///???")


class TestValidateAncestorOrigin(unittest.TestCase):
    def test_valid_https_origin_normalized(self) -> None:
        self.assertEqual(
            bep.validate_ancestor_origin("https://Client.GoHighLevel.com"),
            "https://client.gohighlevel.com",
        )

    def test_valid_origin_with_port_preserved(self) -> None:
        self.assertEqual(
            bep.validate_ancestor_origin("https://client.example.com:8443"),
            "https://client.example.com:8443",
        )

    def test_wildcard_rejected(self) -> None:
        # spec 19.4 break-it case: "hostile iframe origin"
        with self.assertRaises(bep.EmbedBuildError):
            bep.validate_ancestor_origin("*")

    def test_empty_rejected(self) -> None:
        with self.assertRaises(bep.EmbedBuildError):
            bep.validate_ancestor_origin("")

    def test_null_string_rejected(self) -> None:
        with self.assertRaises(bep.EmbedBuildError):
            bep.validate_ancestor_origin("null")

    def test_http_scheme_rejected(self) -> None:
        with self.assertRaises(bep.EmbedBuildError):
            bep.validate_ancestor_origin("http://client.gohighlevel.com")

    def test_userinfo_rejected(self) -> None:
        with self.assertRaises(bep.EmbedBuildError):
            bep.validate_ancestor_origin("https://attacker@client.gohighlevel.com")

    def test_path_rejected(self) -> None:
        with self.assertRaises(bep.EmbedBuildError):
            bep.validate_ancestor_origin("https://client.gohighlevel.com/some/path")

    def test_query_rejected(self) -> None:
        with self.assertRaises(bep.EmbedBuildError):
            bep.validate_ancestor_origin("https://client.gohighlevel.com?x=1")

    def test_single_label_host_rejected(self) -> None:
        # no dot at all — refuses a bare hostname like "localhost"
        with self.assertRaises(bep.EmbedBuildError):
            bep.validate_ancestor_origin("https://localhost")

    def test_javascript_scheme_rejected(self) -> None:
        with self.assertRaises(bep.EmbedBuildError):
            bep.validate_ancestor_origin("javascript:alert(1)")

    def test_data_scheme_rejected(self) -> None:
        with self.assertRaises(bep.EmbedBuildError):
            bep.validate_ancestor_origin("data:text/html,<script>alert(1)</script>")


class TestValidateHttpsUrl(unittest.TestCase):
    def test_valid_url_with_path_preserved(self) -> None:
        url = "https://client.example.com/deep/path"
        self.assertEqual(bep.validate_https_url(url, field_name="test"), url)

    def test_empty_rejected(self) -> None:
        with self.assertRaises(bep.EmbedBuildError):
            bep.validate_https_url("", field_name="test")

    def test_http_rejected(self) -> None:
        with self.assertRaises(bep.EmbedBuildError):
            bep.validate_https_url("http://client.example.com", field_name="test")

    def test_invalid_host_rejected(self) -> None:
        with self.assertRaises(bep.EmbedBuildError):
            bep.validate_https_url("https://localhost", field_name="test")


class TestDeriveOrigin(unittest.TestCase):
    def test_strips_path_and_lowercases_host(self) -> None:
        self.assertEqual(
            bep.derive_origin("https://Project-Name.vercel.app/some/path?x=1"),
            "https://project-name.vercel.app",
        )

    def test_preserves_port(self) -> None:
        self.assertEqual(bep.derive_origin("https://host.example.com:9443/x"), "https://host.example.com:9443")


class TestStaticChecks(unittest.TestCase):
    def test_nested_scroll_trap_detected(self) -> None:
        ok, hits = bep.check_no_nested_scroll_trap({"a.css": ".x { height: 100vh; }"})
        self.assertFalse(ok)
        self.assertIn("a.css", hits)

    def test_nested_scroll_trap_case_insensitive(self) -> None:
        ok, _ = bep.check_no_nested_scroll_trap({"a.css": ".x{HEIGHT:100VH}"})
        self.assertFalse(ok)

    def test_clean_css_passes(self) -> None:
        ok, hits = bep.check_no_nested_scroll_trap({"a.css": ".x { height: 800px; }"})
        self.assertTrue(ok)
        self.assertEqual(hits, [])

    def test_leftover_placeholder_detected(self) -> None:
        ok, hits = bep.check_no_leftover_placeholders({"a.html": "<p>__CWFE_IFRAME_SRC__</p>"})
        self.assertFalse(ok)
        self.assertTrue(hits)

    def test_no_leftover_placeholder_passes(self) -> None:
        ok, hits = bep.check_no_leftover_placeholders({"a.html": "<p>https://example.com</p>"})
        self.assertTrue(ok)
        self.assertEqual(hits, [])

    def test_secret_shaped_string_detected(self) -> None:
        ok, hits = bep.check_no_hardcoded_secrets({"a.js": 'var token = "pit-abcdefghij1234567890";'})
        self.assertFalse(ok)
        self.assertTrue(hits)

    def test_no_secret_passes(self) -> None:
        ok, hits = bep.check_no_hardcoded_secrets({"a.js": "var x = 1;"})
        self.assertTrue(ok)
        self.assertEqual(hits, [])

    def test_has_iframe_title_true(self) -> None:
        self.assertTrue(bep.check_has_iframe_title({"host-snippet.html": '<iframe title="My Title">'}, "My Title"))

    def test_has_iframe_title_false_when_missing(self) -> None:
        self.assertFalse(bep.check_has_iframe_title({"host-snippet.html": "<iframe>"}, "My Title"))

    def test_has_fallback_link_true(self) -> None:
        texts = {"host-snippet.html": '<a href="https://example.com/">go</a>'}
        self.assertTrue(bep.check_has_fallback_link(texts, "https://example.com/"))

    def test_has_fallback_link_false_when_missing(self) -> None:
        texts = {"host-snippet.html": "<a>go</a>"}
        self.assertFalse(bep.check_has_fallback_link(texts, "https://example.com/"))


class TestRenderTemplate(unittest.TestCase):
    def test_render_substitutes_all_tokens(self) -> None:
        text = bep._render(
            "iframe-fragment.html.tmpl",
            {
                "__CWFE_IFRAME_SRC__": "https://example.com",
                "__CWFE_IFRAME_TITLE__": "Example",
            },
        )
        self.assertIn("https://example.com", text)
        self.assertIn('title="Example"', text)
        self.assertNotIn("__CWFE_", text)

    def test_render_missing_template_raises(self) -> None:
        with self.assertRaises(bep.EmbedBuildError):
            bep._render("does-not-exist.tmpl", {})


class TestBuildEmbedPackage(unittest.TestCase):
    def test_fixture_build_passes_and_matches_schema(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-unit-") as tmp:
            run_dir = Path(tmp) / "run"
            make_fixture.write_fixture_run_dir(run_dir)
            result = bep.build_embed_package(run_dir)

            self.assertEqual(result.receipt["status"], "pass")
            self.assertTrue(all(result.receipt["checks"].values()))
            self.assertTrue((result.embed_dir / "host-snippet.html").is_file())
            self.assertTrue((result.embed_dir / "parent-bridge.js").is_file())
            self.assertTrue((result.embed_dir / "wrapper.css").is_file())
            self.assertTrue((result.embed_dir / "allowed-origins.json").is_file())
            self.assertTrue((result.embed_dir / "csp-headers.json").is_file())
            self.assertTrue((result.embed_dir / "TEST-INSTRUCTIONS.md").is_file())
            self.assertTrue((run_dir / "embed-receipt.json").is_file())

            schema = json.loads((_STRUCTURE_DIR / "embed-receipt.schema.json").read_text(encoding="utf-8"))
            errors = jsl.validate(result.receipt, schema)
            self.assertEqual(errors, [])

    def test_csp_header_contains_all_allowed_origins(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-unit-") as tmp:
            run_dir = Path(tmp) / "run"
            make_fixture.write_fixture_run_dir(run_dir)
            result = bep.build_embed_package(run_dir)
            csp_doc = json.loads((result.embed_dir / "csp-headers.json").read_text(encoding="utf-8"))
            csp_value = csp_doc["content_security_policy"]
            for origin in result.receipt["allowed_ancestor_origins"]:
                self.assertIn(origin, csp_value)

    def test_iframe_src_matches_deployment_url(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-unit-") as tmp:
            run_dir = Path(tmp) / "run"
            make_fixture.write_fixture_run_dir(run_dir)
            result = bep.build_embed_package(run_dir)
            host_html = (result.embed_dir / "host-snippet.html").read_text(encoding="utf-8")
            self.assertIn(f'src="{result.receipt["hosted_url"]}"', host_html)

    def test_html_attribute_quote_breakout_is_escaped(self) -> None:
        # A malicious/careless iframe_title/fallback_url containing a
        # double-quote or an inline <script> must not be able to break out
        # of the title="..."/href="..." attribute wrapper — the same class
        # of defect U15's QC pass found and fixed in
        # build_site.py's sanitize_copy_fragment().
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-unit-") as tmp:
            run_dir = Path(tmp) / "run"
            make_fixture.write_fixture_run_dir(run_dir)
            request_path = run_dir / "embed-request.json"
            request = json.loads(request_path.read_text(encoding="utf-8"))
            request["iframe_title"] = 'Evil" onmouseover="alert(1)'
            request_path.write_text(json.dumps(request), encoding="utf-8")

            result = bep.build_embed_package(run_dir)
            host_html = (result.embed_dir / "host-snippet.html").read_text(encoding="utf-8")
            self.assertNotIn('onmouseover="alert(1)"', host_html)
            self.assertIn("&quot;", host_html)
            self.assertEqual(result.receipt["status"], "pass")

    def test_self_embed_collision_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-unit-") as tmp:
            run_dir = Path(tmp) / "run"
            make_fixture.write_fixture_run_dir(run_dir)
            request_path = run_dir / "embed-request.json"
            request = json.loads(request_path.read_text(encoding="utf-8"))
            # deployment url host is "u18-fixture-project-preview.vercel.app"
            request["allowed_ancestor_origins"] = ["https://u18-fixture-project-preview.vercel.app"]
            request_path.write_text(json.dumps(request), encoding="utf-8")

            with self.assertRaises(bep.EmbedBuildError):
                bep.build_embed_package(run_dir)

    def test_missing_deployment_receipt_raises(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-unit-") as tmp:
            run_dir = Path(tmp) / "run"
            make_fixture.write_fixture_run_dir(run_dir)
            (run_dir / "deployment-receipt.json").unlink()
            with self.assertRaises(bep.EmbedBuildError):
                bep.build_embed_package(run_dir)

    def test_deployment_not_ready_raises(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-unit-") as tmp:
            run_dir = Path(tmp) / "run"
            make_fixture.write_fixture_run_dir(run_dir)
            deployment_path = run_dir / "deployment-receipt.json"
            deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
            deployment["status"] = "error"
            deployment_path.write_text(json.dumps(deployment), encoding="utf-8")
            with self.assertRaises(bep.EmbedBuildError):
                bep.build_embed_package(run_dir)

    def test_wildcard_ancestor_origin_raises(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-unit-") as tmp:
            run_dir = Path(tmp) / "run"
            make_fixture.write_fixture_run_dir(run_dir)
            request_path = run_dir / "embed-request.json"
            request = json.loads(request_path.read_text(encoding="utf-8"))
            request["allowed_ancestor_origins"] = ["*"]
            request_path.write_text(json.dumps(request), encoding="utf-8")
            with self.assertRaises(bep.EmbedBuildError):
                bep.build_embed_package(run_dir)

    def test_project_slug_override_applied(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-unit-") as tmp:
            run_dir = Path(tmp) / "run"
            make_fixture.write_fixture_run_dir(run_dir)
            result = bep.build_embed_package(run_dir, project_slug_override="Custom Override Slug")
            self.assertEqual(result.receipt["project_slug"], "custom-override-slug")

    def test_rebuild_overwrites_previous_output_cleanly(self) -> None:
        # A second build into the same embed_dir must not leave stale files
        # from a previous run behind (e.g. a renamed/removed template
        # output) — mirrors build_site.py's rebuild-clean behavior.
        with tempfile.TemporaryDirectory(prefix="cwfe-embed-unit-") as tmp:
            run_dir = Path(tmp) / "run"
            make_fixture.write_fixture_run_dir(run_dir)
            embed_dir = run_dir / "embed"
            embed_dir.mkdir(parents=True, exist_ok=True)
            stale_file = embed_dir / "stale-leftover.txt"
            stale_file.write_text("should be removed", encoding="utf-8")

            result = bep.build_embed_package(run_dir, embed_dir=embed_dir)
            self.assertFalse(stale_file.exists())
            self.assertEqual(result.receipt["status"], "pass")


if __name__ == "__main__":
    unittest.main()
