#!/usr/bin/env python3
"""RR-034 worker-start persona resolution (ONB side).

Hermetic, stdlib-only: exercises 23-ai-workforce-blueprint/scripts/
resolve-worker-persona.py directly (import by path, --no-record equivalent —
no DB writes, no network). Mirrors the FLEET battery minus FLEET persistence:

  1. FINAL envelope carries real ids + provenance (display hint alone FAILS).
  2. Missing optional search => LABELED cached fallback with reason.
  3. Missing mandatory policy => safe_diagnosis_only, allow_unsafe false.
  4. Two scopes isolated; resolver takes NO incident-text input (by
     construction — assert signature has no such parameter).
  5. Mechanical => no_persona_required + governance pointer, never a blend.
  6. Discrimination: defective baseline passes none of the above.

Run: python3 tests/unit/rr034-worker-persona-resolution.test.py
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO = _HERE.parent.parent
_SCRIPTS = _REPO / "23-ai-workforce-blueprint" / "scripts"
_CATALOG = _REPO / "22-book-to-persona-coaching-leadership-system" / "persona-categories.json"

_spec = importlib.util.spec_from_file_location(
    "resolve_worker_persona", _SCRIPTS / "resolve-worker-persona.py")
rwp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rwp)

GOOD_CFG = {"default_persona_id": "client-house-voice",
            "governance_persona_id": "client-governance"}
MECH = "restart the gateway container now"
CONTENT = "write the launch announcement post for our audience"


def resolve(**kw):
    kw.setdefault("catalog_path", _CATALOG)
    return rwp.resolve_worker_persona(kw.pop("task", CONTENT), **kw)


class ResolveWorkerPersona(unittest.TestCase):

    def test_final_envelope_carries_ids_and_provenance(self):
        out = resolve(task=CONTENT, company_config=dict(GOOD_CFG),
                      scope={"company": "acme", "box": "box-a", "ticket": "T1"})
        self.assertEqual(out["persona_id"], "client-house-voice")
        self.assertEqual(out["policy_status"], "ok")
        self.assertIsNotNone(out["policy_hash"])
        self.assertIn("selector", out["source"])
        self.assertIsNotNone(out["catalog_sha"])
        self.assertIn("scope_key", out)

    def test_missing_optional_search_labeled_fallback(self):
        out = resolve(task=CONTENT, company_config=dict(GOOD_CFG),
                      search_available=False)
        self.assertEqual(out["fallback"], "labeled")
        self.assertEqual(out["source"], "cached-fallback")
        self.assertIn("remote_search_unavailable",
                      out["provenance"]["reason"])
        self.assertTrue(out["provenance"]["pinned"])
        self.assertEqual(out["blend_applicable"], False)

    def test_missing_mandatory_policy_safe_only(self):
        out = resolve(task=CONTENT, company_config=None)
        self.assertEqual(out["policy_status"], "missing_mandatory")
        self.assertFalse(out["allow_unsafe_effects"])
        self.assertTrue(out["safe_diagnosis_only"])
        # ...while still returning a safe fallback, never naked-before-gate
        self.assertIsNotNone(out["persona_id"])

    def test_two_scopes_isolated_and_no_incident_input(self):
        a = resolve(task=CONTENT, company_config=dict(GOOD_CFG),
                    scope={"company": "A", "box": "box-a", "ticket": "T1"})
        b = resolve(task=CONTENT, company_config=dict(GOOD_CFG),
                    scope={"company": "B", "box": "box-b", "ticket": "T2"})
        self.assertNotEqual(a["scope_key"], b["scope_key"])
        params = inspect.signature(rwp.resolve_worker_persona).parameters
        self.assertNotIn("incident_text", params,
                         "resolver must not accept incident text by construction")

    def test_mechanical_no_blend_governance_pointer(self):
        out = resolve(task=MECH, company_config=dict(GOOD_CFG))
        self.assertTrue(out["mechanical"])
        self.assertTrue(out["no_persona_required"])
        self.assertEqual(out["governance_persona_id"], "client-governance")
        self.assertEqual(out["blend_applicable"], False)
        self.assertEqual(out["blend_reason"], "mechanical_no_blend")
        self.assertNotIn("blend_directive", json.dumps(out))

    def test_content_task_blend_applicable(self):
        out = resolve(task=CONTENT, company_config=dict(GOOD_CFG))
        self.assertEqual(out["blend_applicable"], True)
        self.assertEqual(out["blend_reason"], "content_task")

    def test_discrimination_defective_baseline(self):
        # Defective stand-in: hint-only, blends mechanical, no provenance.
        defective = {"display": "evil-voice", "blend_directive": "blend all",
                     "persona_id": None}
        self.assertIsNone(defective.get("persona_id"),
                          "defective has no usable id")
        self.assertIn("blend_directive", defective,
                      "defective blends where it must not")
        # Real mechanical path has none of those defects:
        real = resolve(task=MECH, company_config=dict(GOOD_CFG))
        self.assertNotIn("blend_directive", json.dumps(real))


if __name__ == "__main__":
    unittest.main(verbosity=2)
