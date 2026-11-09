#!/usr/bin/env python3
"""F16 S2 on Skill 71's intake: an accepted recommendation is not a client choice, a missing
palette status is unknown, and a brand file that is not the plan's is refused.

Free: no network, no model, no paid call.
Run: python3 71-blackceo-signature-page/tests/test_f16_intake_provenance.py
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def answers(design_style_entry, extra=None):
    doc = {"schema": "client-intake-answers/v1", "meta": {"mode": "launch"}, "answers": {
        "business_name": {"value": "TEST-ONLY Client", "status": "provided", "source": "client"},
        "copy_profile": {"value": "standard", "status": "provided", "source": "client"},
        "image_cap": {"value": 12, "status": "provided", "source": "client"},
        "design_style": design_style_entry,
    }, "to_confirm": []}
    doc["answers"].update(extra or {})
    return doc


class IntakeProvenanceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = Path(self._tmp.name)

    def write_answers(self, doc, name="answers.json"):
        path = self.run_dir / name
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def intake(self, doc, *extra):
        path = self.write_answers(doc)
        return subprocess.run([PY, str(ROOT / "scripts" / "write_intake.py"), str(self.run_dir),
                               "--answers-file", str(path), "--page-kind", "sales", *extra],
                              capture_output=True, text=True)

    def read_intake(self):
        return json.loads((self.run_dir / "intake.json").read_text())

    def test_an_accepted_recommendation_is_not_recorded_as_a_client_choice(self):
        r = self.intake(answers({"value": "C", "status": "provided", "source": "client",
                                 "accepted_proposal": True}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.read_intake()["design_style_source"], "recommended_accepted")

    def test_an_ordinary_provided_answer_is_the_clients_own_choice(self):
        r = self.intake(answers({"value": "B", "status": "provided", "source": "client"}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.read_intake()["design_style_source"], "client_choice")

    def test_a_proposal_is_still_refused_on_a_production_run(self):
        r = self.intake(answers({"value": "A", "status": "default_to_confirm", "source": "safe-default"}))
        self.assertEqual(r.returncode, 2)
        self.assertIn("REFUSED", r.stdout + r.stderr)

    def test_a_brand_file_with_no_palette_status_records_unknown(self):
        brand = self.run_dir / "brand"
        brand.mkdir()
        (brand / "client-brand.json").write_text(json.dumps({"brand_id": "test-only-client"}),
                                                 encoding="utf-8")
        r = self.intake(answers({"value": "B", "status": "provided", "source": "client"}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.read_intake()["palette_status"], "unknown")

    def test_a_brand_file_that_is_not_the_plans_is_refused(self):
        brand = self.run_dir / "brand"
        brand.mkdir()
        (brand / "client-brand.json").write_text(json.dumps({"palette_status": "provided"}),
                                                 encoding="utf-8")
        r = self.intake(answers({"value": "B", "status": "provided", "source": "client"}),
                        "--brand-sha256", "0" * 64)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("not the one the plan was built from", r.stdout + r.stderr)

    def test_the_plans_brand_hash_is_recorded_when_it_matches(self):
        brand = self.run_dir / "brand"
        brand.mkdir()
        path = brand / "client-brand.json"
        path.write_text(json.dumps({"palette_status": "provided"}), encoding="utf-8")
        import hashlib
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        r = self.intake(answers({"value": "B", "status": "provided", "source": "client"}),
                        "--brand-sha256", digest)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        wrote = self.read_intake()
        self.assertEqual(wrote["brand_sha256"], digest)
        self.assertEqual(wrote["brand_record_state"], "verified")


if __name__ == "__main__":
    unittest.main(verbosity=2)
