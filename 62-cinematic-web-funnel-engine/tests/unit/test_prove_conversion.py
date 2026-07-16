#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_prove_conversion.py — offline unit tests for scripts/prove_conversion.py
(Skill 62), the CWFE-MANIFEST.json py_symbol home for P12-CRM
(``prove_conversion.evaluate``, ``af_code`` AF-CWFE-P12-CRM).

NO NETWORK, NO ffmpeg, NO npm/next build. Every run_dir here is hand-built
(a minimal materialized-site stand-in plus a locked content-manifest and a
crm-integration receipt) so the gate's re-derivation logic — cta_map parse
parity with conversion-map.ts, receipt<->locked-content cross-checks,
required-capability coverage, UTM/success/error proof, and the secret scan —
is exercised deterministically and fast. The slow, real-toolchain end-to-end
coverage (real build_site materialization) lives in
``scripts/prove_conversion.py``'s own ``--self-test`` (spec 19.1 vs 19.2
scope split), driven by the e2e ConsolidatedPhaseProofSequenceTests.

Run with:
  python3 -m unittest discover -s 62-cinematic-web-funnel-engine/tests/unit -v
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
_SCRIPTS_DIR = _SKILL_DIR / "scripts"

for _p in (str(_SKILL_DIR), str(_SCRIPTS_DIR), str(_SCRIPTS_DIR / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import prove_conversion as pc  # noqa: E402
import resolve_content_engine as rce  # noqa: E402

_WIRING_STUBS = list(pc._REQUIRED_SITE_WIRING)


def _write_site(site_dir: Path, cta_map: Dict[str, Any]) -> None:
    """Minimal materialized-site stand-in: the required conversion wiring files
    as stubs plus a lib/site-data.generated.ts whose embedded ctaMap equals
    `cta_map` (the same file build_site.py generates)."""
    for rel in _WIRING_STUBS:
        p = site_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith("site-data.generated.ts"):
            continue
        p.write_text("// stub\n", encoding="utf-8")
    site_data = {"meta": {}, "scenes": [], "sections": [], "ctaMap": cta_map, "embed": {"allowedAncestors": []}}
    (site_dir / "lib" / "site-data.generated.ts").write_text(
        'import type { SiteData } from "@/components/types";\n\n'
        f"export const SITE_DATA: SiteData = {json.dumps(site_data, indent=2)};\n",
        encoding="utf-8",
    )


def _locked_content_manifest(cta_map: Dict[str, Any], conversion_requirements: Dict[str, bool]) -> Dict[str, Any]:
    fields: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "project_id": "unit-p12-project",
        "methodology_source": "cinematic-native",
        "source_skill": "62-cinematic-web-funnel-engine",
        "source_skill_version": "1.0.0",
        "page_profiles": [{"profile_id": "main", "sections": ["hero", "cta"]}],
        "section_order": ["hero", "cta"],
        "approved_copy_paths": ["/tmp/does-not-need-to-exist-for-p12.html"],
        "cta_map": cta_map,
        "offer_ledger": [{"offer_id": "o1", "kind": "booked-call", "price_usd": 0}],
        "conversion_requirements": conversion_requirements,
        "claims": [{"claim": "c", "truth_source": "t"}],
        "copy_qc_receipt": {"fixture": True},
        "created_at": "2026-07-15T00:00:00Z",
        "updated_at": "2026-07-15T00:00:00Z",
    }
    fields["content_hash"] = rce.compute_content_hash(fields)
    fields["locked"] = True
    return fields


def _good_receipt() -> Dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "project_id": "unit-p12-project",
        "crm": {
            "provider": "gohighlevel",
            "location_id": "loc-unit-abc123",
            "delegated_to": ["06-ghl-install-pages", "44-convert-and-flow-operator"],
            "secret_names": ["CWFE_GHL_WEBHOOK_URL"],
        },
        "conversion_actions": [
            {
                "cta_id": "lead-capture",
                "kind": "ghl-webhook",
                "env_var_name": "CWFE_GHL_WEBHOOK_URL",
                "required_fields": ["email"],
                "satisfies": ["form"],
                "ghl_resource": {"type": "workflow", "id": "wf-unit-1"},
            }
        ],
        "conversion_event_proof": {
            "mode": "approved-mock",
            "success": {
                "cta_id": "lead-capture",
                "submitted_fields": ["email"],
                "utm": {"utm_source": "ig", "utm_campaign": "unit"},
                "utm_propagated": True,
                "response_status": 200,
                "succeeded": True,
            },
            "error_state": {
                "cta_id": "lead-capture",
                "submitted_fields": [],
                "response_status": 400,
                "rejected": True,
            },
        },
        "cleanup": {"test_contact_id": None, "cleaned_up": True},
        "created_at": "2026-07-15T00:00:00Z",
        "updated_at": "2026-07-15T00:00:00Z",
    }


_GOOD_CTA_MAP = {
    "primary": {"kind": "external-link", "label": "Book", "href": "#book"},
    "lead-capture": {"kind": "ghl-webhook", "label": "Slot", "webhookEnvVar": "CWFE_GHL_WEBHOOK_URL", "requiredFields": ["email"]},
}


class ConversionMapParseParityTests(unittest.TestCase):
    """parse_conversion_action must mirror conversion-map.ts exactly."""

    def test_valid_ghl_webhook(self) -> None:
        action, reason = pc.parse_conversion_action(
            {"kind": "ghl-webhook", "label": "x", "webhookEnvVar": "CWFE_X", "requiredFields": ["email"]}
        )
        self.assertIsNone(reason)
        self.assertEqual(action["kind"], "ghl-webhook")
        self.assertEqual(pc._action_env_var(action), "CWFE_X")

    def test_valid_ghl_form_embed(self) -> None:
        action, reason = pc.parse_conversion_action({"kind": "ghl-form-embed", "label": "x", "embedUrlEnvVar": "CWFE_E"})
        self.assertIsNone(reason)
        self.assertEqual(pc._action_env_var(action), "CWFE_E")

    def test_valid_external_link(self) -> None:
        action, reason = pc.parse_conversion_action({"kind": "external-link", "label": "x", "href": "#y"})
        self.assertIsNone(reason)
        self.assertEqual(action["href"], "#y")

    def test_rejects_bad_kind(self) -> None:
        _, reason = pc.parse_conversion_action({"kind": "nope", "label": "x"})
        self.assertIn("kind", reason)

    def test_rejects_missing_label(self) -> None:
        _, reason = pc.parse_conversion_action({"kind": "external-link", "href": "#y"})
        self.assertIn("label", reason)

    def test_rejects_webhook_without_env_var(self) -> None:
        _, reason = pc.parse_conversion_action({"kind": "ghl-webhook", "label": "x"})
        self.assertIn("webhookEnvVar", reason)

    def test_rejects_form_embed_without_env_var(self) -> None:
        _, reason = pc.parse_conversion_action({"kind": "ghl-form-embed", "label": "x"})
        self.assertIn("embedUrlEnvVar", reason)

    def test_rejects_non_object(self) -> None:
        _, reason = pc.parse_conversion_action(["not", "an", "object"])
        self.assertIn("object", reason)

    def test_rejects_bad_required_fields(self) -> None:
        _, reason = pc.parse_conversion_action({"kind": "external-link", "label": "x", "href": "#y", "requiredFields": [1, 2]})
        self.assertIn("requiredFields", reason)

    def test_map_splits_valid_and_invalid(self) -> None:
        actions, errors = pc.parse_conversion_map(
            {"ok": {"kind": "external-link", "label": "x", "href": "#y"}, "bad": {"kind": "external-link", "label": "x"}}
        )
        self.assertIn("ok", actions)
        self.assertIn("bad", errors)


class SecretScanTests(unittest.TestCase):
    def test_flags_a_secret_value(self) -> None:
        findings = pc._secret_scan({"x": "sk-" + "a" * 32})
        self.assertTrue(findings)

    def test_clean_receipt_has_no_findings(self) -> None:
        self.assertEqual(pc._secret_scan(_good_receipt()), [])

    def test_finding_never_echoes_the_secret_value(self) -> None:
        secret = "sk-" + "b" * 40
        findings = pc._secret_scan({"leak": secret})
        self.assertTrue(findings)
        self.assertNotIn(secret, "; ".join(findings))


class ExtractSiteDataTests(unittest.TestCase):
    def test_extracts_embedded_cta_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            _write_site(site, _GOOD_CTA_MAP)
            reasons: list = []
            data = pc._extract_site_data(site, reasons)
            self.assertEqual(reasons, [])
            self.assertEqual(data["ctaMap"], _GOOD_CTA_MAP)

    def test_missing_file_reports_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reasons: list = []
            self.assertIsNone(pc._extract_site_data(Path(tmp), reasons))
            self.assertTrue(reasons)


class EvaluateTests(unittest.TestCase):
    def _build(self, tmp: Path, *, cta_map=None, requirements=None, receipt=None, site_cta_map=None) -> Path:
        cta_map = _GOOD_CTA_MAP if cta_map is None else cta_map
        requirements = {"form": True, "calendar": False, "payment": False} if requirements is None else requirements
        run_dir = tmp / "run"
        run_dir.mkdir()
        site_dir = run_dir / "site"
        _write_site(site_dir, site_cta_map if site_cta_map is not None else cta_map)
        (run_dir / "content-manifest.json").write_text(
            json.dumps(_locked_content_manifest(cta_map, requirements), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (run_dir / "build-receipt.json").write_text(json.dumps({"site_dir": str(site_dir)}), encoding="utf-8")
        (run_dir / "crm-integration-receipt.json").write_text(
            json.dumps(_good_receipt() if receipt is None else receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return run_dir

    def test_consistent_p12_passes_and_writes_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._build(Path(tmp))
            passed, detail = pc.evaluate(run_dir)
            self.assertTrue(passed, msg=detail)
            self.assertTrue((run_dir / "crm-integration-status.json").is_file())
            status = json.loads((run_dir / "crm-integration-status.json").read_text())
            self.assertTrue(status["passed"])
            self.assertEqual(status["af_code"], "AF-CWFE-P12-CRM")

    def test_missing_receipt_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._build(Path(tmp))
            (run_dir / "crm-integration-receipt.json").unlink()
            passed, detail = pc.evaluate(run_dir)
            self.assertFalse(passed)
            self.assertIn("crm-integration-receipt.json", detail)

    def test_missing_build_receipt_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._build(Path(tmp))
            (run_dir / "build-receipt.json").unlink()
            passed, detail = pc.evaluate(run_dir)
            self.assertFalse(passed)
            self.assertIn("P11-SITE-BUILD", detail)

    def test_secret_value_in_receipt_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = _good_receipt()
            receipt["conversion_actions"][0]["ghl_resource"]["id"] = "sk-" + "z" * 32
            run_dir = self._build(Path(tmp), receipt=receipt)
            passed, detail = pc.evaluate(run_dir)
            self.assertFalse(passed)
            self.assertIn("AF-CWFE-SECRET-LEAK", detail)

    def test_kind_mismatch_vs_locked_map_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = _good_receipt()
            receipt["conversion_actions"][0]["kind"] = "ghl-form-embed"
            run_dir = self._build(Path(tmp), receipt=receipt)
            passed, detail = pc.evaluate(run_dir)
            self.assertFalse(passed)
            self.assertIn("kind", detail)

    def test_env_var_name_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = _good_receipt()
            receipt["conversion_actions"][0]["env_var_name"] = "CWFE_WRONG"
            run_dir = self._build(Path(tmp), receipt=receipt)
            passed, detail = pc.evaluate(run_dir)
            self.assertFalse(passed)
            self.assertIn("env_var_name", detail)

    def test_uncovered_required_capability_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = _good_receipt()
            receipt["conversion_actions"][0]["satisfies"] = []
            run_dir = self._build(Path(tmp), receipt=receipt)
            passed, detail = pc.evaluate(run_dir)
            self.assertFalse(passed)
            self.assertIn("form", detail)

    def test_success_proof_without_utm_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = _good_receipt()
            receipt["conversion_event_proof"]["success"]["utm_propagated"] = False
            receipt["conversion_event_proof"]["success"]["utm"] = {}
            run_dir = self._build(Path(tmp), receipt=receipt)
            passed, detail = pc.evaluate(run_dir)
            self.assertFalse(passed)
            self.assertIn("UTM", detail)

    def test_weak_error_state_proof_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = _good_receipt()
            receipt["conversion_event_proof"]["error_state"]["submitted_fields"] = ["email"]
            run_dir = self._build(Path(tmp), receipt=receipt)
            passed, detail = pc.evaluate(run_dir)
            self.assertFalse(passed)
            self.assertIn("required field", detail)

    def test_success_on_external_link_cta_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = _good_receipt()
            receipt["conversion_event_proof"]["success"]["cta_id"] = "primary"
            run_dir = self._build(Path(tmp), receipt=receipt)
            passed, detail = pc.evaluate(run_dir)
            self.assertFalse(passed)
            self.assertIn("CRM", detail)

    def test_phantom_cta_absent_from_locked_map_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = _good_receipt()
            receipt["conversion_actions"].append(
                {"cta_id": "ghost", "kind": "ghl-webhook", "env_var_name": "CWFE_GHOST", "required_fields": [], "satisfies": [], "ghl_resource": {"type": "webhook", "id": "wh-ghost"}}
            )
            run_dir = self._build(Path(tmp), receipt=receipt)
            passed, detail = pc.evaluate(run_dir)
            self.assertFalse(passed)
            self.assertIn("not present in the locked", detail)

    def test_site_cta_map_drift_from_locked_content_fails_closed(self) -> None:
        drifted = copy.deepcopy(_GOOD_CTA_MAP)
        drifted["lead-capture"]["webhookEnvVar"] = "CWFE_DIFFERENT"
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._build(Path(tmp), site_cta_map=drifted)
            passed, detail = pc.evaluate(run_dir)
            self.assertFalse(passed)
            self.assertIn("ctaMap", detail)

    def test_missing_wiring_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._build(Path(tmp))
            site_dir = run_dir / "site"
            (site_dir / "app" / "api" / "conversion-event" / "route.ts").unlink()
            passed, detail = pc.evaluate(run_dir)
            self.assertFalse(passed)
            self.assertIn("conversion wiring missing", detail)

    def test_receipt_schema_is_valid_json_schema_lite(self) -> None:
        import json_schema_lite as jsl

        schema = json.loads((pc._SCHEMA_PATH).read_text(encoding="utf-8"))
        self.assertEqual(jsl.validate(_good_receipt(), schema), [])


if __name__ == "__main__":
    unittest.main()
