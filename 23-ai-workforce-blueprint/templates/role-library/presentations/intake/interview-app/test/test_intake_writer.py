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
        # PRES-DEPT-FIX-REVIEW-2026-08-17.md Part 6 #3: deck_type must come
        # from the client's OWN presentation_type answer, never a hardcoded
        # default. This client answered "signature" -- proving the fix
        # writes what was actually asked for, not webinar.
        raw = {
            "answers": {
                "presentation_type": "signature",
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
        self.assertEqual(intake["deck_type"], "signature_presentation")
        self.assertNotEqual(intake["deck_type"], "webinar")
        self.assertEqual(intake["presentation_type"], "signature")
        self.assertEqual(intake["audience_mode"], "STANDARD")
        self.assertEqual(intake["deck_brief"]["OFFER_NAME"], "The Momentum Method")
        for f in iw.MANDATORY_PRE_CAPTURE:
            self.assertIn(f, intake["pre_presentation_capture"], f"missing {f}")

    def test_writes_intake_and_ledger(self):
        raw = {"answers": {"presentation_type": "from_scratch", "offer_name": "X",
                           "tone": "Teacher", "want_sales_checkout": "yes"}}
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

    def test_writes_transcript_gate_0b(self):
        """GATE 0b requires a real, non-trivial conversation trace."""
        raw = {"answers": {
            "offer_name": "The Momentum Method",
            "transformation_promise": "stuck -> unstoppable",
            "audience": "women entrepreneurs",
            "cta_action": "book a call",
            "tone": "Inspirational",
            "final_price": "$497",
            "want_sales_checkout": "yes",
            "presentation_type": "from_scratch",  # kept last: turns[0] below must stay offer_name
        }}
        intake = iw.assemble_intake(raw, run_id="R3")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "runs" / "R3"
            tpath = iw.write_transcript(run_dir, intake)
            self.assertTrue(tpath.exists())
            raw_bytes = tpath.read_bytes()
            self.assertGreaterEqual(len(raw_bytes), 200,
                                    "GATE 0b requires intake_transcript.json >= 200 bytes")
            tr = json.loads(raw_bytes.decode("utf-8"))
            self.assertTrue(tr["completed"])
            self.assertGreaterEqual(tr["turn_count"], 1)
            self.assertEqual(tr["turns"][0]["question_id"], "offer_name")
            self.assertEqual(tr["turns"][0]["answer"], "The Momentum Method")

    def test_write_transcript_refuses_to_overwrite_a_signed_driver_envelope(self):
        """FIX F21-SIBLING (2026-08-20): write_transcript() used to overwrite
        working/interview/intake_transcript.json unconditionally -- no
        read-first check at all. If a run dir already carries a SIGNED driver
        envelope (deck-intake-driver.py's turn-gate provenance record,
        format=='sp-intake-transcript-v1'), that is HIGHER-evidentiary-value
        provenance than this bridge's own synthetic Q&A transcript, and
        silently replacing it would be a real provenance loss. This proves
        the guard: raises, writes nothing, leaves the signed envelope intact."""
        raw = {"answers": {"offer_name": "X", "presentation_type": "from_scratch"}}
        intake = iw.assemble_intake(raw, run_id="R6")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "runs" / "R6"
            transcript_path = run_dir / "working" / "interview" / "intake_transcript.json"
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            signed_envelope = {
                "format": "sp-intake-transcript-v1",
                "driver": "deck-intake-driver.py",
                "qid_sequence": ["q1"],
                "turns": [{"role": "assistant", "text": "What is X?", "qid": "q1"},
                         {"role": "owner", "text": "Y", "qid": "q1"}],
                "driver_signature": "deadbeef",
            }
            transcript_path.write_text(json.dumps(signed_envelope), encoding="utf-8")

            with self.assertRaises(iw.SignedEnvelopePresentError):
                iw.write_transcript(run_dir, intake)

            # Nothing was overwritten -- the signed envelope survives byte-for-byte.
            reloaded = json.loads(transcript_path.read_text(encoding="utf-8"))
            self.assertEqual(reloaded, signed_envelope)

    def test_write_transcript_still_writes_normally_when_no_envelope_present(self):
        """Negative control: the guard must not block the normal case (no
        pre-existing transcript, or a pre-existing non-envelope transcript)."""
        raw = {"answers": {"offer_name": "X", "presentation_type": "from_scratch"}}
        intake = iw.assemble_intake(raw, run_id="R7")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "runs" / "R7"
            tpath = iw.write_transcript(run_dir, intake)
            self.assertTrue(tpath.exists())
            # Re-writing over its OWN prior (non-envelope) output must still work.
            tpath2 = iw.write_transcript(run_dir, intake)
            self.assertTrue(tpath2.exists())

    def test_fails_closed_when_deck_type_unanswered(self):
        """PRES-DEPT-FIX-REVIEW-2026-08-17.md Part 6 #3: assemble_intake()
        must not fabricate deck_type when presentation_type was never
        answered -- this is exactly the interview app's real question set
        today (it never asks presentation_type), so this is the common case,
        not an edge case."""
        raw = {"answers": {"offer_name": "X", "tone": "Teacher"}}  # no presentation_type
        with self.assertRaises(iw.UngroundedDeckTypeError):
            iw.assemble_intake(raw, run_id="R5")

    def test_fails_closed_on_unrecognized_deck_type_answer(self):
        raw = {"answers": {"offer_name": "X", "presentation_type": "keynote"}}
        with self.assertRaises(iw.UngroundedDeckTypeError):
            iw.assemble_intake(raw, run_id="R5b")

    def test_write_functions_fail_closed_on_ungrounded_intake(self):
        """The REAL production entry point -- intake_bridge.py's
        cmd_ingest(), the app's actual submit-trigger -- builds `intake`
        directly from the Worker payload and calls write_intake_file()/
        write_ledger() WITHOUT ever calling assemble_intake(). This proves
        the gate holds on that path too, not just the assemble_intake() one:
        a caller-claimed deck_type (exactly what the app frontend's own
        buildIntakePayload() hardcodes) must not survive when `answers` does
        not back it up, and NOTHING may be written to disk."""
        fabricated_intake = {
            "interview_confirmed": True,
            "deck_type": "webinar",               # caller-claimed, same shape as the bug
            "presentation_type": "from_scratch",   # caller-claimed, same shape as the bug
            "answers": {"offer_name": "X"},        # the client never answered presentation_type
        }
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "runs" / "R6"
            with self.assertRaises(iw.UngroundedDeckTypeError):
                iw.write_intake_file(run_dir, fabricated_intake)
            with self.assertRaises(iw.UngroundedDeckTypeError):
                iw.write_ledger(run_dir, fabricated_intake)
            self.assertFalse((run_dir / "working" / "copy" / "intake.json").exists())
            self.assertFalse((run_dir / "working" / "interview" / "intake_ledger.json").exists())

    def test_write_functions_correct_a_stale_claim_on_a_grounded_intake(self):
        """A legitimate, fully-answered intake still writes successfully
        (the fix must not break the working path) -- and a stale/wrong
        caller-supplied deck_type is corrected to match the real answer
        rather than trusted."""
        grounded_intake = {
            "interview_confirmed": True,
            "deck_type": "webinar",                # stale caller claim
            "presentation_type": "from_scratch",    # stale caller claim
            "answers": {"offer_name": "X", "presentation_type": "signature"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "runs" / "R7"
            ipath = iw.write_intake_file(run_dir, grounded_intake)
            lpath = iw.write_ledger(run_dir, grounded_intake)
            self.assertTrue(ipath.exists())
            self.assertTrue(lpath.exists())
            written = json.loads(ipath.read_text(encoding="utf-8"))
            self.assertEqual(written["deck_type"], "signature_presentation")
            self.assertNotEqual(written["deck_type"], "webinar")
            ledger = json.loads(lpath.read_text(encoding="utf-8"))
            self.assertEqual(ledger["status"], "complete")
            self.assertTrue(ledger["complete"])

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
