#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_prove_content.py — unit + subprocess/end-to-end tests for build unit
U8's gate (scripts/prove_content.py), the CWFE-MANIFEST.json py_symbol home
for P2-METHODOLOGY (`evaluate_methodology`), P3-CONTENT (`evaluate_manifest`),
and the cross-cutting AF-CWFE-CONTENT-DUPLICATE check
(`assert_delegated_methodology`).

stdlib unittest only. Run with:
  python3 -m unittest discover -s 62-cinematic-web-funnel-engine/tests/unit -v
or directly:
  python3 62-cinematic-web-funnel-engine/tests/unit/test_prove_content.py -v

Covers, per the U8 directive:
  - evaluate_methodology()/evaluate_manifest() direct-call contract
    (Tuple[bool, str], matching every other phase gate's evaluate() shape)
  - the ONE gate script correctly serves BOTH P2 and P3 phase entries the
    orchestrator's CWFE-MANIFEST.json declares it for, driven purely by
    on-disk run_dir state — proven via TWO real subprocess invocations with
    the identical `--run-dir` argument, exactly as
    run_cinematic_web_funnel._run_phase_gate calls every gate
  - existing-funnel-selector (routing rule 3/5/6) correctly halts P3 without
    ever writing content-manifest.json — intentional non-PASS, not a defect
  - AF-CWFE-CONTENT-DUPLICATE fires for a copy path that resolves inside
    run_dir (locally authored) and is silent (no violation) for a genuinely
    external, delegated path
  - usage-error paths (missing methodology-request.json, missing
    CWFE_CONTENT_DELEGATE_DIR) exit 3 distinctly from a routing/content FAIL
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "fake-delegate-copy"
_REPO_ROOT = _SCRIPTS_DIR.parents[1]
sys.path.insert(0, str(_SCRIPTS_DIR))

import prove_content as pc  # noqa: E402
import resolve_content_engine as rce  # noqa: E402
import state_engine as se  # noqa: E402

PY = sys.executable or "python3"
GATE_PATH = _SCRIPTS_DIR / "prove_content.py"
REAL_REGISTRY_PATH = str(_REPO_ROOT / "06-ghl-install-pages" / "funnel-engines" / "registry.json")

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3


def _write_request(run_dir: Path, **overrides) -> Path:
    request = {
        "schema_version": "1.0.0",
        "project_id": "proj-u8-gate-test",
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
    path = run_dir / "methodology-request.json"
    path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    return path


def _write_fake_delegate_output(tmp_path: Path, *, skill: str, fixture_filename: str) -> Path:
    delegate_dir = tmp_path / "delegate-run"
    copy_dir = delegate_dir / "pages"
    copy_dir.mkdir(parents=True)
    fragment_src = (_FIXTURES_DIR / fixture_filename).read_text(encoding="utf-8")
    fragment_path = copy_dir / fixture_filename
    fragment_path.write_text(fragment_src, encoding="utf-8")

    cert_path = delegate_dir / "PROCESS-CERTIFICATE.json"
    cert_path.write_text(json.dumps({"skill": skill, "certified_at": "2026-07-15T00:00:00Z"}), encoding="utf-8")

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


class DirectCallGateTests(unittest.TestCase):
    """Direct-call (in-process) coverage of evaluate_methodology/evaluate_manifest."""

    def test_p2_usage_error_when_request_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            passed, detail = pc.evaluate_methodology(Path(tmp))
            self.assertFalse(passed)
            self.assertIn("USAGE ERROR", detail)

    def test_p2_pass_writes_methodology_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_request(run_dir, request_text="signature funnel with upsell downsell")
            os.environ["CWFE_REGISTRY_PATH"] = REAL_REGISTRY_PATH
            try:
                passed, detail = pc.evaluate_methodology(run_dir)
            finally:
                os.environ.pop("CWFE_REGISTRY_PATH", None)
            self.assertTrue(passed, detail)
            self.assertTrue((run_dir / "methodology-decision.json").is_file())
            self.assertIn("signature-funnel", detail)

    def test_p3_before_p2_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            passed, detail = pc.evaluate_manifest(Path(tmp))
            self.assertFalse(passed)
            self.assertIn("USAGE ERROR", detail)

    def test_p3_existing_funnel_selector_halts_without_writing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_request(run_dir, cinematic_intent=False, request_text="ordinary funnel")
            os.environ["CWFE_REGISTRY_PATH"] = REAL_REGISTRY_PATH
            try:
                p2_passed, _ = pc.evaluate_methodology(run_dir)
                self.assertTrue(p2_passed)
                p3_passed, p3_detail = pc.evaluate_manifest(run_dir)
            finally:
                os.environ.pop("CWFE_REGISTRY_PATH", None)
            self.assertFalse(p3_passed)
            self.assertIn("NO_ENGINE_MATCH_FALLTHROUGH", p3_detail)
            self.assertFalse((run_dir / "content-manifest.json").exists())

    def test_p3_cinematic_native_locks_content_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_request(run_dir, request_text="general cinematic scroll story page")
            os.environ["CWFE_REGISTRY_PATH"] = REAL_REGISTRY_PATH
            try:
                p2_passed, _ = pc.evaluate_methodology(run_dir)
                self.assertTrue(p2_passed)
                p3_passed, p3_detail = pc.evaluate_manifest(run_dir)
            finally:
                os.environ.pop("CWFE_REGISTRY_PATH", None)
            self.assertTrue(p3_passed, p3_detail)
            manifest_path = run_dir / "content-manifest.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(manifest["locked"])
            self.assertEqual(len(manifest["content_hash"]), 64)

    def test_p3_delegated_requires_delegate_dir_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_request(run_dir, request_text="signature funnel with upsell downsell")
            os.environ["CWFE_REGISTRY_PATH"] = REAL_REGISTRY_PATH
            try:
                p2_passed, _ = pc.evaluate_methodology(run_dir)
                self.assertTrue(p2_passed)
                os.environ.pop("CWFE_CONTENT_DELEGATE_DIR", None)
                p3_passed, p3_detail = pc.evaluate_manifest(run_dir)
            finally:
                os.environ.pop("CWFE_REGISTRY_PATH", None)
            self.assertFalse(p3_passed)
            self.assertIn("USAGE ERROR", p3_detail)
            self.assertIn("CWFE_CONTENT_DELEGATE_DIR", p3_detail)

    def test_p3_delegated_signature_funnel_locks_content_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            run_dir = tmp_path / "run"
            run_dir.mkdir()
            _write_request(run_dir, request_text="signature funnel with upsell downsell")
            delegate_dir = _write_fake_delegate_output(
                tmp_path, skill="49-signature-funnel", fixture_filename="signature-funnel-main.fragment.html"
            )
            os.environ["CWFE_REGISTRY_PATH"] = REAL_REGISTRY_PATH
            os.environ["CWFE_CONTENT_DELEGATE_DIR"] = str(delegate_dir)
            try:
                p2_passed, _ = pc.evaluate_methodology(run_dir)
                self.assertTrue(p2_passed)
                p3_passed, p3_detail = pc.evaluate_manifest(run_dir)
            finally:
                os.environ.pop("CWFE_REGISTRY_PATH", None)
                os.environ.pop("CWFE_CONTENT_DELEGATE_DIR", None)
            self.assertTrue(p3_passed, p3_detail)
            manifest = json.loads((run_dir / "content-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["methodology_source"], "signature-funnel")
            self.assertEqual(manifest["source_skill"], "49-signature-funnel")
            self.assertTrue(manifest["locked"])
            copy_path = Path(manifest["approved_copy_paths"][0])
            self.assertTrue(copy_path.is_file())
            # Delegated copy must live OUTSIDE run_dir — never locally authored.
            with self.assertRaises(ValueError):
                copy_path.resolve().relative_to(run_dir.resolve())


class ContentDuplicateViolationTests(unittest.TestCase):
    """AF-CWFE-CONTENT-DUPLICATE mechanics."""

    def test_no_violation_for_a_genuinely_external_delegated_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            run_dir = tmp_path / "run"
            run_dir.mkdir()
            delegate_dir = _write_fake_delegate_output(
                tmp_path, skill="49-signature-funnel", fixture_filename="signature-funnel-main.fragment.html"
            )
            handoff = json.loads((delegate_dir / "content-handoff.json").read_text(encoding="utf-8"))
            manifest_fields = {
                "methodology_source": "signature-funnel",
                "source_skill": "49-signature-funnel",
                "approved_copy_paths": handoff["approved_copy_paths"],
                "copy_qc_receipt": {"delegation": {"certificate_ref": handoff["certificate_ref"]}},
            }
            decision = {"methodology_source": "signature-funnel"}
            violations = pc.assert_delegated_methodology(manifest_fields, decision, run_dir=run_dir)
            self.assertEqual(violations, [])

    def test_violation_when_copy_path_resolves_inside_run_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            local_file = run_dir / "locally-authored.html"
            local_file.write_text("<p>authored inside run_dir, not delegated</p>", encoding="utf-8")
            manifest_fields = {
                "methodology_source": "signature-funnel",
                "source_skill": "49-signature-funnel",
                "approved_copy_paths": [str(local_file.resolve())],
                "copy_qc_receipt": {},
            }
            decision = {"methodology_source": "signature-funnel"}
            violations = pc.assert_delegated_methodology(manifest_fields, decision, run_dir=run_dir)
            self.assertTrue(any("INSIDE run_dir" in v for v in violations), violations)

    def test_violation_when_source_skill_mismatches_methodology_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            manifest_fields = {
                "methodology_source": "signature-funnel",
                "source_skill": "56-sales-page-assets",  # wrong skill for this methodology_source
                "approved_copy_paths": ["/nonexistent/path.html"],
                "copy_qc_receipt": {},
            }
            decision = {"methodology_source": "signature-funnel"}
            violations = pc.assert_delegated_methodology(manifest_fields, decision, run_dir=run_dir)
            self.assertTrue(any("does not match the expected delegate" in v for v in violations), violations)

    def test_violation_when_approved_copy_paths_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            manifest_fields = {
                "methodology_source": "sales-page-assets",
                "source_skill": "56-sales-page-assets",
                "approved_copy_paths": [],
                "copy_qc_receipt": {},
            }
            decision = {"methodology_source": "sales-page-assets"}
            violations = pc.assert_delegated_methodology(manifest_fields, decision, run_dir=run_dir)
            self.assertTrue(any("empty" in v for v in violations), violations)

    def test_vacuous_pass_for_cinematic_native_and_existing_funnel_selector(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            for source in ("cinematic-native", "existing-funnel-selector"):
                manifest_fields = {"methodology_source": source, "approved_copy_paths": []}
                violations = pc.assert_delegated_methodology(manifest_fields, {"methodology_source": source}, run_dir=run_dir)
                self.assertEqual(violations, [])

    def test_p3_end_to_end_rejects_locally_authored_copy_path(self):
        # Build a content-handoff.json whose approved_copy_paths deliberately
        # points INSIDE run_dir (simulating a delegate skill's output being
        # mishandled, or the router trying to author copy itself) and prove
        # the P3 gate fails closed with AF-CWFE-CONTENT-DUPLICATE rather than
        # silently locking a manifest that isn't really delegated.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            run_dir = tmp_path / "run"
            run_dir.mkdir()
            _write_request(run_dir, request_text="signature funnel with upsell downsell")

            delegate_dir = tmp_path / "delegate-run"
            delegate_dir.mkdir()
            bad_copy_path = run_dir / "locally-authored.html"
            bad_copy_path.write_text("<p>not really delegated</p>", encoding="utf-8")
            version_file = _REPO_ROOT / "49-signature-funnel" / "skill-version.txt"
            version = version_file.read_text(encoding="utf-8").strip()
            handoff = {
                "schema_version": "1.0.0",
                "source_skill": "49-signature-funnel",
                "source_skill_version": version,
                "generated_at": "2026-07-15T00:00:00Z",
                "certificate_ref": None,
                "page_profiles": [{"profile_id": "main", "sections": ["hero"]}],
                "section_order": ["hero"],
                "approved_copy_paths": [str(bad_copy_path.resolve())],
                "cta_map": {},
                "offer_ledger": [],
                "conversion_requirements": {"form": True, "calendar": False, "payment": False},
                "claims": [],
                "qc_receipt": {},
            }
            (delegate_dir / "content-handoff.json").write_text(json.dumps(handoff), encoding="utf-8")

            os.environ["CWFE_REGISTRY_PATH"] = REAL_REGISTRY_PATH
            os.environ["CWFE_CONTENT_DELEGATE_DIR"] = str(delegate_dir)
            try:
                p2_passed, _ = pc.evaluate_methodology(run_dir)
                self.assertTrue(p2_passed)
                p3_passed, p3_detail = pc.evaluate_manifest(run_dir)
            finally:
                os.environ.pop("CWFE_REGISTRY_PATH", None)
                os.environ.pop("CWFE_CONTENT_DELEGATE_DIR", None)
            self.assertFalse(p3_passed)
            self.assertIn("AF-CWFE-CONTENT-DUPLICATE", p3_detail)
            self.assertFalse((run_dir / "content-manifest.json").exists())


class SubprocessDualPhaseGateTests(unittest.TestCase):
    """Proves the design load-bearing claim: ONE gate script
    (scripts/prove_content.py), invoked TWICE with the identical
    `--run-dir <run_dir>` argument (exactly how
    run_cinematic_web_funnel._run_phase_gate calls every phase gate),
    correctly serves P2-METHODOLOGY on the first call and P3-CONTENT on the
    second — driven purely by on-disk run_dir state, never a CLI flag."""

    def _run(self, run_dir: Path, env: dict) -> subprocess.CompletedProcess:
        full_env = dict(os.environ)
        full_env.update(env)
        return subprocess.run(
            [PY, str(GATE_PATH), "--run-dir", str(run_dir)],
            capture_output=True, text=True, env=full_env,
        )

    def test_two_identical_invocations_run_p2_then_p3_cinematic_native(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_request(run_dir, request_text="general cinematic scroll story page")
            env = {"CWFE_REGISTRY_PATH": REAL_REGISTRY_PATH}

            first = self._run(run_dir, env)
            self.assertEqual(first.returncode, EXIT_OK, first.stderr)
            self.assertIn("P2-METHODOLOGY", first.stdout)
            self.assertTrue((run_dir / "methodology-decision.json").is_file())
            self.assertFalse((run_dir / "content-manifest.json").exists())

            second = self._run(run_dir, env)
            self.assertEqual(second.returncode, EXIT_OK, second.stderr)
            self.assertIn("P3-CONTENT", second.stdout)
            manifest_path = run_dir / "content-manifest.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(manifest["locked"])

    def test_two_identical_invocations_run_p2_then_p3_delegated(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            run_dir = tmp_path / "run"
            run_dir.mkdir()
            _write_request(run_dir, request_text="direct response sales page with order bump and countdown timer, 8-section main page")
            delegate_dir = _write_fake_delegate_output(
                tmp_path, skill="56-sales-page-assets", fixture_filename="sales-page-main.fragment.html"
            )
            env = {"CWFE_REGISTRY_PATH": REAL_REGISTRY_PATH, "CWFE_CONTENT_DELEGATE_DIR": str(delegate_dir)}

            first = self._run(run_dir, env)
            self.assertEqual(first.returncode, EXIT_OK, first.stderr)
            decision = json.loads((run_dir / "methodology-decision.json").read_text(encoding="utf-8"))
            self.assertEqual(decision["decision"]["methodology_source"], "sales-page-assets")

            second = self._run(run_dir, env)
            self.assertEqual(second.returncode, EXIT_OK, second.stderr)
            manifest = json.loads((run_dir / "content-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["methodology_source"], "sales-page-assets")
            self.assertEqual(manifest["source_skill"], "56-sales-page-assets")
            self.assertTrue(manifest["locked"])

    def test_two_identical_invocations_second_fails_closed_on_no_engine_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_request(run_dir, cinematic_intent=False, request_text="ordinary funnel")
            env = {"CWFE_REGISTRY_PATH": REAL_REGISTRY_PATH}

            first = self._run(run_dir, env)
            self.assertEqual(first.returncode, EXIT_OK, first.stderr)

            second = self._run(run_dir, env)
            self.assertEqual(second.returncode, EXIT_FAIL)
            self.assertIn("NO_ENGINE_MATCH_FALLTHROUGH", second.stderr)
            self.assertFalse((run_dir / "content-manifest.json").exists())

    def test_run_dir_missing_is_usage_error(self):
        result = subprocess.run(
            [PY, str(GATE_PATH), "--run-dir", "/nonexistent/run/dir"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, EXIT_USAGE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
