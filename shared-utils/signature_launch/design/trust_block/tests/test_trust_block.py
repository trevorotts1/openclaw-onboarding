"""Deterministic L1 tests for the trust/proof block (doc 16 s.1, s.8)."""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DESIGN = os.path.abspath(os.path.join(HERE, "..", ".."))


def _load(name, *relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(DESIGN, *relpath))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


trust = _load("sl_trust_block", "trust_block", "trust_block.py")

FULL_PROOF = {
    "testimonials": [
        {
            "quote": "TEST ONLY quote from a fixture graduate.",
            "attribution": "Fixture Person, Cohort 1",
            "source_ref": "TEST ONLY proof ledger entry 1",
        }
    ],
    "credentials": [
        {"label": "Fixture Credential", "detail": "Issued 2024",
         "source_ref": "TEST ONLY proof ledger entry 2"}
    ],
    "counts": [
        {"value": "250", "label": "fixture graduates",
         "source_ref": "TEST ONLY proof ledger entry 3"}
    ],
}


class AbsentState(unittest.TestCase):
    def test_none_proof_renders_absent_with_no_testimonial(self):
        result = trust.render_trust_block(None)
        self.assertEqual(result["state"], "absent")
        self.assertIn('data-state="absent"', result["html"])
        self.assertNotIn("sl-trust-testimonial", result["html"])
        self.assertNotIn("blockquote", result["html"])
        self.assertNotIn("sl-trust-count", result["html"])

    def test_empty_proof_renders_absent(self):
        result = trust.render_trust_block({"testimonials": [], "counts": []})
        self.assertEqual(result["state"], "absent")
        self.assertEqual(
            result["rendered"],
            {"testimonials": 0, "credentials": 0, "counts": 0},
        )

    def test_unsubstantiated_only_proof_renders_absent(self):
        result = trust.render_trust_block(
            {"testimonials": [{"quote": "Invented-sounding quote.",
                               "attribution": "Nobody"}]}
        )
        self.assertEqual(result["state"], "absent")
        self.assertNotIn("Invented-sounding quote.", result["html"])
        self.assertEqual(result["excluded_unsubstantiated"], 1)


class PresentState(unittest.TestCase):
    def test_supplied_proof_renders(self):
        result = trust.render_trust_block(FULL_PROOF)
        self.assertEqual(result["state"], "present")
        self.assertIn("TEST ONLY quote from a fixture graduate.", result["html"])
        self.assertIn("Fixture Person, Cohort 1", result["html"])
        self.assertIn("250", result["html"])
        self.assertIn("fixture graduates", result["html"])
        self.assertIn("Fixture Credential", result["html"])
        self.assertEqual(
            result["rendered"],
            {"testimonials": 1, "credentials": 1, "counts": 1},
        )
        self.assertEqual(result["excluded_unsubstantiated"], 0)

    def test_unsubstantiated_items_are_excluded_and_tallied(self):
        proof = {
            "testimonials": list(FULL_PROOF["testimonials"]) + [
                {"quote": "No source here.", "attribution": "Ghost"}
            ]
        }
        result = trust.render_trust_block(proof)
        self.assertEqual(result["state"], "present")
        self.assertNotIn("No source here.", result["html"])
        self.assertEqual(result["excluded_unsubstantiated"], 1)
        self.assertEqual(result["rendered"]["testimonials"], 1)

    def test_quotes_are_escaped(self):
        proof = {
            "testimonials": [
                {"quote": "<b>bold claim</b>", "attribution": "A & B",
                 "source_ref": "TEST ONLY ledger"}
            ]
        }
        result = trust.render_trust_block(proof)
        self.assertIn("&lt;b&gt;bold claim&lt;/b&gt;", result["html"])
        self.assertIn("A &amp; B", result["html"])
        self.assertNotIn("<b>bold claim</b>", result["html"])


if __name__ == "__main__":
    unittest.main()
