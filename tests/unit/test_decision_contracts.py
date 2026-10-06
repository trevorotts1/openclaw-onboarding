#!/usr/bin/env python3
"""D02 decision-contract tests (JEV spec 1.1, section 10; acceptance A26).

Proves, against the REAL schema.py implementation (no reimplemented logic):
  * envelope fixtures validate clean; canonical JSON is deterministic and
    byte-stable across key order / repeated runs (canonical extension
    roundtrip strategy);
  * bundle fixtures validate clean and preserve persona voice/topic/task
    parts/audience/goal/provenance round trip;
  * missing required fields, incompatible versions, non-finite floats,
    invalid enums, collapsed-mirror violations, and company mismatches fail;
  * unknown OPTIONAL extension fields survive validation + canonicalization
    (additive extensions preserved, never stripped).

Run: python3 tests/unit/test_decision_contracts.py
 or: pytest tests/unit/test_decision_contracts.py
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED = _REPO_ROOT / "shared-utils"
_CONTRACTS = _SHARED / "decision_engine" / "contracts"
_FIX = _CONTRACTS / "fixtures"
sys.path.insert(0, str(_SHARED))

_spec = importlib.util.spec_from_file_location(
    "decision_engine_contracts_schema", _CONTRACTS / "schema.py")
de = importlib.util.module_from_spec(_spec)
sys.modules["decision_engine_contracts_schema"] = de
_spec.loader.exec_module(de)


def _load(name: str) -> dict:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


class DecisionContracts(unittest.TestCase):
    def test_fixtures_exist(self):
        self.assertTrue((_FIX / "envelope_committed.json").exists())
        self.assertTrue((_FIX / "envelope_mechanical.json").exists())

    # ── valid paths ──────────────────────────────────────────────────
    def test_committed_envelope_validates(self):
        ok, errs = de.validate_envelope(_load("envelope_committed.json"))
        self.assertTrue(ok, f"committed fixture rejected: {errs}")

    def test_mechanical_envelope_validates(self):
        ok, errs = de.validate_envelope(_load("envelope_mechanical.json"))
        self.assertTrue(ok, f"mechanical fixture rejected: {errs}")

    def test_content_bundle_validates_standalone(self):
        bundle = _load("envelope_committed.json")["personaBundle"]
        ok, errs = de.validate_persona_bundle(bundle, company_id="fixture-co")
        self.assertTrue(ok, f"content bundle rejected: {errs}")

    def test_mechanical_bundle_validates_standalone(self):
        bundle = _load("envelope_mechanical.json")["personaBundle"]
        ok, errs = de.validate_persona_bundle(bundle, company_id="fixture-co")
        self.assertTrue(ok, f"mechanical bundle rejected: {errs}")

    # ── canonical roundtrip: explicit extension strategy ─────────────
    def test_canonical_json_deterministic_across_key_order(self):
        env = _load("envelope_committed.json")
        shuffled = dict(reversed(list(env.items())))
        raw_roundtrip = json.loads(de.canonical_envelope_json(env))
        ok, errs = de.validate_envelope(raw_roundtrip)
        self.assertTrue(ok, f"canonical output failed revalidation: {errs}")
        self.assertEqual(de.canonical_envelope_json(env),
                         de.canonical_envelope_json(shuffled))

    def test_unknown_optional_fields_preserved_not_stripped(self):
        env = _load("envelope_committed.json")
        env["x_future_optional"] = {"note": "additive extension"}
        env["personaBundle"]["x_bundle_future"] = "kept verbatim"
        ok, errs = de.validate_envelope(env)
        self.assertTrue(ok, f"additive extension rejected: {errs}")
        out = json.loads(de.canonical_envelope_json(env))
        self.assertEqual(out["x_future_optional"], {"note": "additive extension"})
        self.assertEqual(out["personaBundle"]["x_bundle_future"], "kept verbatim")

    # ── rejections ──────────────────────────────────────────────────
    def test_missing_required_envelope_field_rejected(self):
        env = _load("envelope_committed.json")
        del env["decisionId"]
        ok, errs = de.validate_envelope(env)
        self.assertFalse(ok)
        self.assertTrue(any("decisionId" in e for e in errs))

    def test_missing_required_bundle_field_rejected(self):
        env = _load("envelope_committed.json")
        del env["personaBundle"]["blend_directive"]
        ok, errs = de.validate_envelope(env)
        self.assertFalse(ok)
        self.assertTrue(any("blend_directive" in e for e in errs), errs)

    def test_incompatible_envelope_version_rejected(self):
        env = _load("envelope_committed.json")
        env["schemaVersion"] = "2.0"
        ok, errs = de.validate_envelope(env)
        self.assertFalse(ok)
        self.assertTrue(any("schemaVersion" in e for e in errs), errs)

    def test_incompatible_bundle_version_rejected(self):
        env = _load("envelope_committed.json")
        env["personaBundle"]["bundle_version"] = "2.0"
        ok, errs = de.validate_envelope(env)
        self.assertFalse(ok)
        self.assertTrue(any("bundle_version" in e for e in errs), errs)

    def test_nonfinite_float_rejected(self):
        env = _load("envelope_committed.json")
        env["elapsedMs"] = 5
        env["personaBundle"]["score"] = float("nan")
        ok, errs = de.validate_envelope(env)
        self.assertFalse(ok)
        self.assertTrue(any("non-finite" in e for e in errs), errs)

    def test_invalid_status_enum_rejected(self):
        env = _load("envelope_committed.json")
        env["status"] = "maybe"
        ok, errs = de.validate_envelope(env)
        self.assertFalse(ok)
        self.assertTrue(any("status" in e for e in errs), errs)

    def test_failed_without_fallback_reason_rejected(self):
        env = _load("envelope_committed.json")
        env["status"] = "failed"
        env["fallbackReason"] = None
        ok, errs = de.validate_envelope(env)
        self.assertFalse(ok)
        self.assertTrue(any("fallbackReason" in e for e in errs), errs)

    def test_company_mismatch_rejected(self):
        env = _load("envelope_committed.json")
        env["personaBundle"]["companyId"] = "other-co"
        ok, errs = de.validate_envelope(env)
        self.assertFalse(ok)
        self.assertTrue(any("company mismatch" in e for e in errs), errs)

    def test_collapsed_mirror_violation_rejected(self):
        env = _load("envelope_mechanical.json")
        env["personaBundle"] = _load("envelope_committed.json")["personaBundle"]
        env["personaBundle"]["persona_id"] = "wrong-persona"
        ok, errs = de.validate_envelope(env)
        self.assertFalse(ok)
        self.assertTrue(any("mirror" in e for e in errs), errs)

    def test_guardrail_stripped_rejected(self):
        env = _load("envelope_committed.json")
        env["personaBundle"]["blend_directive"] = "Write in a nice voice."
        ok, errs = de.validate_envelope(env)
        self.assertFalse(ok)
        self.assertTrue(any("guardrail" in e for e in errs), errs)

    def test_task_persona_cap_rejected(self):
        env = _load("envelope_committed.json")
        row = copy.deepcopy(env["personaBundle"]["task_personas"][0])
        env["personaBundle"]["task_personas"] = [
            dict(row, seq=i + 1) for i in range(11)]
        ok, errs = de.validate_envelope(env)
        self.assertFalse(ok)
        self.assertTrue(any("task_personas" in e for e in errs), errs)

    def test_validator_never_raises_on_garbage(self):
        for bad in (None, "x", 42, [], {"status": "committed"}):
            ok, errs = de.validate_envelope(bad)
            self.assertFalse(ok)
            self.assertTrue(errs)

    # ── preservation round trip (A26 core fields) ────────────────────
    def test_bundle_fields_survive_canonical_roundtrip(self):
        env = _load("envelope_committed.json")
        out = json.loads(de.canonical_envelope_json(env))
        b_in, b_out = env["personaBundle"], out["personaBundle"]
        for key in ("mode", "persona_id", "topic", "blend_directive",
                    "conversion_goal", "goal_source", "catalog_version",
                    "confirm_required", "task_personas"):
            self.assertEqual(b_out[key], b_in[key], f"bundle field {key} lost")
        self.assertEqual(b_out["voice"], b_in["voice"])
        self.assertEqual(b_out["resolved_audience"], b_in["resolved_audience"])
        self.assertEqual(b_out["resolved_goal"], b_in["resolved_goal"])
        self.assertEqual(b_out["rationale"], b_in["rationale"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
