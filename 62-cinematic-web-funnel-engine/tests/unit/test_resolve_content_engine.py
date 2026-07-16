#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_resolve_content_engine.py — unit tests for build unit U8
(scripts/resolve_content_engine.py): the P2-METHODOLOGY / P3-CONTENT router
mechanics, in isolation from the prove_content.py CLI gate (see
test_prove_content.py for the gate-level / subprocess / end-to-end coverage).

stdlib unittest only. Run with:
  python3 -m unittest discover -s 62-cinematic-web-funnel-engine/tests/unit -v
or directly:
  python3 62-cinematic-web-funnel-engine/tests/unit/test_resolve_content_engine.py -v

Covers, per the U8 directive:
  - registry-driven match scoring (names/keywords/signals weighted, anti_signal
    hard veto, deterministic priority tie-break) against the REAL shared
    06-ghl-install-pages/funnel-engines/registry.json — one source of truth,
    never a duplicated keyword list
  - every one of spec 7.2's six routing rules resolves to the correct
    methodology_source and is individually traceable via rule_applied
  - methodology-decision.json schema validation + round-trip read/write
  - content-manifest.json construction for the cinematic-native path
    (placeholder profile, and an operator-supplied override)
  - content-manifest.json construction for the delegated path (content-handoff
    consumption, never inlining copy text, sha256-hashing the consumed
    artifacts for the delegation receipt)
  - content_hash is a real, order-independent sha256 over content-bearing
    fields only, and verify_locked_manifest() catches tampering
  - finalize_and_save_content_manifest() refuses to overwrite an already
    locked content-manifest.json (manifest immutability at the storage layer)
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
_STRUCTURE_DIR = Path(__file__).resolve().parents[2] / "structure"
_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "fake-delegate-copy"
_REPO_ROOT = _SCRIPTS_DIR.parents[1]
sys.path.insert(0, str(_SCRIPTS_DIR))

import resolve_content_engine as rce  # noqa: E402
import state_engine as se  # noqa: E402


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

REAL_REGISTRY_PATH = str(_REPO_ROOT / "06-ghl-install-pages" / "funnel-engines" / "registry.json")


def _base_request(**overrides) -> dict:
    request = {
        "schema_version": "1.0.0",
        "project_id": "proj-u8-test",
        "requested_deliverable_type": "cinematic-landing-page",
        "requested_visual_treatment": "cinematic",
        "cinematic_intent": True,
        "existing_funnel_methodology_named": None,
        "offer_summary": "",
        "conversion_goal": "",
        "funnel_steps": None,
        "existing_copy_assets": [],
        "destination_platform": "vercel",
        "ghl_available": True,
        "conversion_requirements": {"form": True, "calendar": False, "payment": False},
        "request_text": "",
    }
    request.update(overrides)
    return request


def _write_fake_delegate_output(tmp_path: Path, *, skill: str, fixture_filename: str) -> Path:
    """Simulates a completed Skill 49 / Skill 56 run output directory: a real
    copy fragment file on disk, a fake PROCESS-CERTIFICATE.json, and a
    content-handoff.json whose approved_copy_paths point at the real fragment
    file by ABSOLUTE path — never inlined text. Returns the delegate dir."""
    delegate_dir = tmp_path / "delegate-run"
    copy_dir = delegate_dir / "pages"
    copy_dir.mkdir(parents=True)
    fragment_src = (_FIXTURES_DIR / fixture_filename).read_text(encoding="utf-8")
    fragment_path = copy_dir / fixture_filename
    fragment_path.write_text(fragment_src, encoding="utf-8")

    cert_path = delegate_dir / "PROCESS-CERTIFICATE.json"
    cert_path.write_text(json.dumps({"skill": skill, "certified_at": "2026-07-15T00:00:00Z", "signature": "fixture"}), encoding="utf-8")

    version_file = _REPO_ROOT / skill / "skill-version.txt"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "0.0.0-fixture"

    handoff = {
        "schema_version": "1.0.0",
        "source_skill": skill,
        "source_skill_version": version,
        "generated_at": "2026-07-15T00:00:00Z",
        "certificate_ref": {"path": str(cert_path.resolve()), "skill": skill},
        "page_profiles": [{"profile_id": "main", "sections": ["hero", "offer", "cta"]}],
        "section_order": ["hero", "offer", "cta"],
        "approved_copy_paths": [str(fragment_path.resolve())],
        "cta_map": {"hero": "Get Started"},
        "offer_ledger": [{"name": "Fixture Offer", "price": "0"}],
        "conversion_requirements": {"form": True, "calendar": False, "payment": False},
        "claims": [{"claim": "fixture claim", "truth_source": "fixture"}],
        "qc_receipt": {"score": 9.0, "notes": "fixture qc receipt"},
    }
    (delegate_dir / "content-handoff.json").write_text(json.dumps(handoff, indent=2), encoding="utf-8")
    return delegate_dir


class RegistryScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = rce.load_registry(REAL_REGISTRY_PATH)

    def test_registry_loads_both_delegate_engines(self):
        candidates = rce.score_delegate_engines("", self.registry)
        ids = sorted(c["engine_id"] for c in candidates)
        self.assertEqual(ids, ["sales-page-assets", "signature-funnel"])

    def test_strong_signature_funnel_name_hit_clears_threshold(self):
        corpus = "we want a signature funnel with upsell downsell and 12-section hero"
        candidates = rce.score_delegate_engines(corpus, self.registry)
        sf = next(c for c in candidates if c["engine_id"] == "signature-funnel")
        self.assertTrue(sf["cleared"], sf)
        self.assertGreaterEqual(sf["score"], sf["threshold"])
        self.assertIn("signature funnel", sf["matched"]["names"])

    def test_direct_response_signal_hits_clear_threshold(self):
        corpus = "direct response sales page with an order bump and a countdown timer, 8-section main page"
        candidates = rce.score_delegate_engines(corpus, self.registry)
        sp = next(c for c in candidates if c["engine_id"] == "sales-page-assets")
        self.assertTrue(sp["cleared"], sp)

    def test_single_loose_keyword_does_not_clear_threshold_alone(self):
        # A single generic keyword hit (weight 2) saturates to ~0.487, below
        # the registry's 0.55 default threshold — weak evidence must not
        # trigger delegation on its own.
        corpus = "vsl"
        candidates = rce.score_delegate_engines(corpus, self.registry)
        for c in candidates:
            if "vsl" in c["matched"]["keywords"] and not c["matched"]["names"] and not c["matched"]["signals"]:
                self.assertFalse(c["cleared"], c)

    def test_anti_signal_hard_vetoes_even_with_many_keyword_hits(self):
        # Loaded with many Skill-49 keyword hits AND its own anti_signal
        # ("vsl only") — the veto must force score to 0 regardless of the
        # positive hits.
        corpus = (
            "signature landing page, 12-section hero, big bold claim, big bold promise, "
            "3/5/7 step funnel, upsell downsell funnel, oversaturated signature look, vsl only"
        )
        candidates = rce.score_delegate_engines(corpus, self.registry)
        sf = next(c for c in candidates if c["engine_id"] == "signature-funnel")
        self.assertTrue(sf["matched"]["anti_signals"], "expected an anti_signal hit in this fixture corpus")
        self.assertEqual(sf["score"], 0.0)
        self.assertFalse(sf["cleared"])

    def test_no_hits_scores_zero_and_never_clears(self):
        candidates = rce.score_delegate_engines("a generic marketing page about widgets", self.registry)
        for c in candidates:
            self.assertEqual(c["score"], 0.0)
            self.assertFalse(c["cleared"])

    def test_priority_tie_break_is_deterministic(self):
        # Two synthetic delegate-id engines with an equal score but different
        # priority: the higher-priority engine must win the tie.
        registry = {
            "engines": [
                {
                    "id": "signature-funnel", "skill": "49-signature-funnel", "priority": 5,
                    "confidence_threshold": 0.1,
                    "match": {"names": ["widget page"], "keywords": [], "signals": [], "anti_signals": []},
                },
                {
                    "id": "sales-page-assets", "skill": "56-sales-page-assets", "priority": 20,
                    "confidence_threshold": 0.1,
                    "match": {"names": ["widget page"], "keywords": [], "signals": [], "anti_signals": []},
                },
            ]
        }
        candidates = rce.score_delegate_engines("widget page", registry)
        self.assertEqual(candidates[0]["score"], candidates[1]["score"])
        # Directly exercise the tie-break logic the way route() does:
        cleared = [c for c in candidates if c["cleared"]]
        winner = max(cleared, key=lambda c: (c["score"], c["priority"]))
        self.assertEqual(winner["engine_id"], "sales-page-assets")  # priority 20 beats priority 5


class RoutingRuleTests(unittest.TestCase):
    def test_rule1_signature_funnel(self):
        request = _base_request(request_text="build me a signature funnel with upsell downsell branching")
        payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["decision"]["methodology_source"], "signature-funnel")
        self.assertEqual(payload["decision"]["rule_applied"], "rule-1-signature-funnel")
        self.assertIsNotNone(payload["delegation_receipt"])
        self.assertEqual(payload["delegation_receipt"]["target_skill"], "49-signature-funnel")
        self.assertTrue(payload["delegation_receipt"]["target_skill_version"])

    def test_rule2_direct_response(self):
        request = _base_request(
            request_text="direct response sales page with an order bump, countdown timer, high-ticket long form"
        )
        payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
        self.assertEqual(payload["decision"]["methodology_source"], "sales-page-assets")
        self.assertEqual(payload["decision"]["rule_applied"], "rule-2-direct-response")
        self.assertEqual(payload["delegation_receipt"]["target_skill"], "56-sales-page-assets")

    def test_rule3_ordinary_funnel_no_cinematic_intent(self):
        request = _base_request(cinematic_intent=False, request_text="just a normal funnel please")
        payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
        self.assertEqual(payload["decision"]["methodology_source"], "existing-funnel-selector")
        self.assertEqual(payload["decision"]["rule_applied"], "rule-3-ordinary-no-cinematic-intent")
        self.assertIsNone(payload["delegation_receipt"])

    def test_rule4_cinematic_native(self):
        request = _base_request(request_text="a general cinematic scroll page about our brand story")
        payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
        self.assertEqual(payload["decision"]["methodology_source"], "cinematic-native")
        self.assertEqual(payload["decision"]["rule_applied"], "rule-4-cinematic-native")
        self.assertIsNone(payload["delegation_receipt"])

    def test_rule5_video_only(self):
        request = _base_request(requested_deliverable_type="video-only", cinematic_intent=True)
        payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
        self.assertEqual(payload["decision"]["methodology_source"], "existing-funnel-selector")
        self.assertEqual(payload["decision"]["rule_applied"], "rule-5-video-only")

    def test_rule6_static_no_cinematic(self):
        request = _base_request(requested_deliverable_type="static-page", cinematic_intent=False)
        payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
        self.assertEqual(payload["decision"]["methodology_source"], "existing-funnel-selector")
        self.assertEqual(payload["decision"]["rule_applied"], "rule-6-static-no-cinematic")

    def test_decision_payload_is_schema_valid(self):
        request = _base_request(request_text="signature funnel please")
        payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
        errors = rce.validate_decision(payload)
        self.assertEqual(errors, [])

    def test_missing_registry_raises_usage_error(self):
        with self.assertRaises(rce.UsageError):
            rce.load_registry("/nonexistent/registry.json")


class MethodologyDecisionIOTests(unittest.TestCase):
    def test_write_and_read_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            request = _base_request(request_text="signature funnel please")
            payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
            out_path = rce.write_methodology_decision(payload, run_dir)
            self.assertTrue(out_path.is_file())
            reloaded = rce.read_methodology_decision(run_dir)
            self.assertEqual(reloaded["decision"]["methodology_source"], "signature-funnel")

    def test_read_missing_raises_file_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                rce.read_methodology_decision(Path(tmp))


class CinematicNativeManifestTests(unittest.TestCase):
    def test_placeholder_profile_when_no_override(self):
        request = _base_request(request_text="general cinematic story page")
        payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
        fields = rce.build_cinematic_native_manifest_fields("proj-u8-test", payload)
        self.assertEqual(fields["methodology_source"], "cinematic-native")
        self.assertEqual(fields["source_skill"], "62-cinematic-web-funnel-engine")
        self.assertTrue(fields["copy_qc_receipt"]["placeholder"])
        self.assertEqual(fields["approved_copy_paths"], [])
        # A fully finalized (hashed + locked) manifest built from this
        # placeholder profile must be schema-valid against U6's
        # content-manifest.schema.json — proves the cinematic-native path
        # produces a real, storable manifest, not just an in-memory shape.
        content_manifest_schema = json.loads((_STRUCTURE_DIR / "content-manifest.schema.json").read_text(encoding="utf-8"))
        candidate = {**fields, "content_hash": "0" * 64, "locked": True, "created_at": "x", "updated_at": "x"}
        errors = rce.jsl.validate(candidate, content_manifest_schema)
        self.assertEqual(errors, [])

    def test_override_profile_is_honored_and_not_marked_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            override_path = Path(tmp) / "native-profile.json"
            override_path.write_text(json.dumps({
                "page_profiles": [{"profile_id": "custom", "sections": ["a", "b"]}],
                "section_order": ["a", "b"],
            }), encoding="utf-8")
            request = _base_request(request_text="general cinematic story page")
            payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
            fields = rce.build_cinematic_native_manifest_fields(
                "proj-u8-test", payload, native_profile_path=str(override_path)
            )
            self.assertEqual(fields["page_profiles"][0]["profile_id"], "custom")
            self.assertFalse(fields["copy_qc_receipt"]["placeholder"])

    def test_existing_funnel_selector_raises_fallthrough(self):
        request = _base_request(cinematic_intent=False)
        payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
        with self.assertRaises(rce.NoEngineMatchFallthrough):
            rce.build_cinematic_native_manifest_fields("proj-u8-test", payload)


class DelegatedManifestTests(unittest.TestCase):
    def test_signature_funnel_handoff_consumed_without_rewriting_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            delegate_dir = _write_fake_delegate_output(
                tmp_path, skill="49-signature-funnel", fixture_filename="signature-funnel-main.fragment.html"
            )
            request = _base_request(request_text="a signature funnel with upsell downsell branching")
            payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
            self.assertEqual(payload["decision"]["methodology_source"], "signature-funnel")

            fields = rce.build_delegated_manifest_fields("proj-u8-test", payload, delegate_dir)
            self.assertEqual(fields["source_skill"], "49-signature-funnel")
            self.assertEqual(len(fields["approved_copy_paths"]), 1)
            copy_path = Path(fields["approved_copy_paths"][0])
            self.assertTrue(copy_path.is_file())
            on_disk_text = copy_path.read_text(encoding="utf-8")
            fixture_text = (_FIXTURES_DIR / "signature-funnel-main.fragment.html").read_text(encoding="utf-8")
            self.assertEqual(on_disk_text, fixture_text)  # byte-identical: never rewritten
            hashes = fields["copy_qc_receipt"]["delegation"]["consumed_artifact_hashes"]
            self.assertEqual(len(hashes), 1)
            self.assertEqual(hashes[0]["sha256"], _sha256_hex(fixture_text.encode("utf-8")))

    def test_sales_page_assets_handoff_wrong_source_skill_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Handoff claims to be FROM Skill 56, but P2 decided Skill 49 —
            # this must be rejected as a content-duplicate style violation
            # before it is ever locked in.
            delegate_dir = _write_fake_delegate_output(
                tmp_path, skill="56-sales-page-assets", fixture_filename="sales-page-main.fragment.html"
            )
            request = _base_request(request_text="a signature funnel with upsell downsell branching")
            payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
            self.assertEqual(payload["decision"]["methodology_source"], "signature-funnel")
            with self.assertRaises(rce.ContentDuplicateViolation):
                rce.build_delegated_manifest_fields("proj-u8-test", payload, delegate_dir)

    def test_missing_content_handoff_raises_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            request = _base_request(request_text="a signature funnel with upsell downsell branching")
            payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
            with self.assertRaises(rce.UsageError):
                rce.build_delegated_manifest_fields("proj-u8-test", payload, Path(tmp))


class HashLockImmutabilityTests(unittest.TestCase):
    def test_content_hash_is_stable_and_order_independent(self):
        fields_a = {"a": 1, "b": {"x": 1, "y": 2}, "schema_version": "1.0.0"}
        fields_b = {"schema_version": "1.0.0", "b": {"y": 2, "x": 1}, "a": 1}
        self.assertEqual(rce.compute_content_hash(fields_a), rce.compute_content_hash(fields_b))

    def test_content_hash_excludes_lock_bookkeeping_fields(self):
        fields = {"a": 1}
        h1 = rce.compute_content_hash({**fields, "content_hash": "irrelevant", "locked": False, "created_at": "t1", "updated_at": "t1"})
        h2 = rce.compute_content_hash({**fields, "content_hash": "different", "locked": True, "created_at": "t2", "updated_at": "t2"})
        self.assertEqual(h1, h2)

    def test_content_hash_changes_when_content_changes(self):
        h1 = rce.compute_content_hash({"a": 1})
        h2 = rce.compute_content_hash({"a": 2})
        self.assertNotEqual(h1, h2)

    def test_verify_locked_manifest_detects_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            request = _base_request(request_text="general cinematic story page")
            payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
            fields = rce.build_cinematic_native_manifest_fields("proj-u8-test", payload)
            manifest = rce.finalize_and_save_content_manifest(run_dir, fields)
            ok, _ = rce.verify_locked_manifest(manifest)
            self.assertTrue(ok)

            tampered = dict(manifest)
            tampered["section_order"] = ["tampered"]
            ok2, detail = rce.verify_locked_manifest(tampered)
            self.assertFalse(ok2)
            self.assertIn("mismatch", detail)

    def test_finalize_refuses_to_overwrite_a_locked_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            request = _base_request(request_text="general cinematic story page")
            payload = rce.route(request, registry_path=REAL_REGISTRY_PATH)
            fields = rce.build_cinematic_native_manifest_fields("proj-u8-test", payload)
            rce.finalize_and_save_content_manifest(run_dir, fields)
            with self.assertRaises(se.StateEngineError):
                rce.finalize_and_save_content_manifest(run_dir, fields)


if __name__ == "__main__":
    unittest.main(verbosity=2)
