#!/usr/bin/env python3
"""Offline gate for intake_writer.py — proves the app's submission assembles
into the dept-format intake.json + a completed intake_ledger.json.
Run: python3 test/test_intake_writer.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # repo layout: bridge/ sits next to test/
sys.path.insert(0, str(HERE.parent / "bridge"))  # repo layout: intake_writer lives in bridge/

import intake_writer as iw  # noqa: E402


class TestIntakeWriter(unittest.TestCase):
    def test_assembles_dept_format(self):
        raw = {
            "answers": {
                "offer_name": "The Momentum Method",
                "transformation_promise": "stuck -> unstoppable",
                "audience": "women entrepreneurs",
                "cta_action": "book a call",
                "tone": "Inspirational",
                "final_price": "$497",
                "speech_speed_preference": "default",
                "want_sales_checkout": "yes",
                "want_vsl_page": "no",
            }
        }
        intake = iw.assemble_intake(raw, run_id="R1")
        self.assertIs(intake["interview_confirmed"], True)
        self.assertEqual(intake["deck_type"], "webinar")
        self.assertEqual(intake["audience_mode"], "STANDARD")
        self.assertEqual(intake["deck_brief"]["OFFER_NAME"], "The Momentum Method")
        for f in iw.MANDATORY_PRE_CAPTURE:
            self.assertIn(f, intake["pre_presentation_capture"], f"missing {f}")

    def test_writes_intake_and_ledger(self):
        raw = {"answers": {"offer_name": "X", "tone": "Teacher", "want_sales_checkout": "yes"}}
        intake = iw.assemble_intake(raw, run_id="R2")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "runs" / "R2"
            ipath = iw.write_intake_file(run_dir, intake)
            lpath = iw.write_ledger(run_dir, intake)
            self.assertTrue(ipath.exists())
            self.assertTrue(lpath.exists())
            ledger = json.loads(lpath.read_text(encoding="utf-8"))
            self.assertEqual(ledger["status"], "complete")
            self.assertEqual(ledger["entries"]["offer_name"]["value"], "X")

    def test_passthrough_intake_shape_wins(self):
        shaped = {
            "intake": {
                "interview_confirmed": True,
                "deck_brief": {"OFFER_NAME": "Shaped"},
                "pre_presentation_capture": {"DARK_OK": False},
            }
        }
        intake = iw.assemble_intake(shaped)
        self.assertEqual(intake["deck_brief"]["OFFER_NAME"], "Shaped")
        self.assertEqual(intake["pre_presentation_capture"]["DARK_OK"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
