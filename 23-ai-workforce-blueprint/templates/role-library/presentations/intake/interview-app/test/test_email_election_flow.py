"""test_email_election_flow.py -- the Item 33c Skill 50 email election,
end to end (the B21 waiver pattern applied to the third upsell branch).

WHAT THIS PINS:
  - the hosted payload mints want_email_sequences + its conditional
    declined-reason follow-up in the curated set, in lockstep (toggle then
    follow-up), storing at pre_presentation_capture.*;
  - hosted flat answers round-trip through intake_writer.assemble_intake
    into the nested pre_presentation_capture home byte-for-byte (the
    PRES-006 fix), and the written intake.json resolves at the delivery
    gate (scripts/email_followup.resolve_email_gate) to "prepare" on a yes
    and "waived" on a no + reason, quoting the client's exact words;
  - completeness: the toggle itself is a required canonical field, so an
    intake that never answers the election fails write_intake_file naming
    pre_presentation_capture.WANT_EMAIL_SEQUENCES; the CONDITIONAL reason
    is not a flat-required field (a writer-level block would contradict the
    pinned flat set) -- completeness for the reason is enforced where the
    department enforces it for every branch: the delivery gate fails closed
    AF-EMAIL-WAIVER-MISSING when a "no" carries no reason;
  - the ledger carries both answers under their question ids;
  - legacy migration moves deck_brief.* / flat-filed email values home
    byte-for-byte and refuses contradictions, like every other field.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_APP_DIR = _HERE.parents[1]                       # intake/interview-app
_PRESENTATIONS = _HERE.parents[3]                 # role-library/presentations
for _p in (_APP_DIR / "bridge", _APP_DIR / "payload", _PRESENTATIONS / "scripts"):
    sys.path.insert(0, str(_p))

import build_questions_payload as bqp   # noqa: E402
import intake_writer as iw              # noqa: E402
import email_followup as ef             # noqa: E402

REASON = "We run our own email list already."
_WRITTEN_INTAKE = Path("working") / "copy" / "intake.json"


def _complete_answers(**overrides):
    answers = {
        "presentation_type": "signature",
        "offer_name": "The Big Offer",
        "named_methodology": "The Method",
        "transformation_promise": "From stuck to booked",
        "time_to_result": "90 days",
        "audience": "Coaches",
        "cta_action": "Book a call",
        "brand_primary": "#123456",
        "image_links": "none",
        "tone": "Bold",
        "final_price": "$5,000",
        "speech_speed_preference": "conversational ~150 wpm",
        "want_sales_checkout": "yes",
        "want_vsl_page": "yes",
        "want_email_sequences": "no",
        "email_sequences_declined_reason": REASON,
    }
    answers.update(overrides)
    return answers


def _assemble(answers):
    return iw.assemble_intake({"answers": answers}, run_id="RUNTEST")


def _build_payload():
    std_path = _PRESENTATIONS / "intake" / "deck-intake-questions.json"
    ups_path = _PRESENTATIONS / "intake" / "upsell-questions.json"
    std = json.loads(std_path.read_text(encoding="utf-8"))
    questions = list(std.get("questions", []))
    if ups_path.is_file():
        questions += json.loads(ups_path.read_text(encoding="utf-8")).get("questions", [])
    questions += list(bqp.APP_ONLY_QUESTIONS.values())
    return bqp.build_curated_payload("RUNTEST", {"questions": questions},
                                     bqp.DEFAULT_CURATED, std.get("storeTarget"))


class TestPayloadMintsThePair(unittest.TestCase):
    def test_pair_present_in_lockstep(self):
        payload = _build_payload()
        ids = [q["id"] for q in payload["questions"]]
        self.assertIn("want_email_sequences", ids)
        self.assertIn("email_sequences_declined_reason", ids)
        self.assertEqual(ids.index("email_sequences_declined_reason"),
                         ids.index("want_email_sequences") + 1)
        by_id = {q["id"]: q for q in payload["questions"]}
        toggle = by_id["want_email_sequences"]
        self.assertEqual(toggle["storeOn"],
                         "pre_presentation_capture.WANT_EMAIL_SEQUENCES")
        self.assertEqual(toggle["default"], "no")
        reason = by_id["email_sequences_declined_reason"]
        self.assertEqual(reason["storeOn"],
                         "pre_presentation_capture.EMAIL_SEQUENCES_DECLINED_REASON")
        self.assertEqual(reason["conditional_on"],
                         {"id": "want_email_sequences", "equals": "no"})
        self.assertTrue(reason["required"])


class TestHostedRoundTrip(unittest.TestCase):
    def test_yes_round_trips_to_the_nested_home_and_prepares(self):
        answers = _complete_answers(want_email_sequences="yes")
        answers.pop("email_sequences_declined_reason")
        intake = _assemble(answers)
        pre = intake["pre_presentation_capture"]
        self.assertEqual(pre["WANT_EMAIL_SEQUENCES"], "yes")
        # The chat-path flat shape must NOT appear.
        self.assertNotIn("want_email_sequences", intake)
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            iw.write_intake_file(run_dir, intake)
            written = json.loads(
                (run_dir / _WRITTEN_INTAKE).read_text(encoding="utf-8"))
            gate = ef.resolve_email_gate(written)
            self.assertEqual(gate["decision"], "prepare")

    def test_no_with_reason_resolves_waived_with_verbatim_quote(self):
        intake = _assemble(_complete_answers())
        pre = intake["pre_presentation_capture"]
        self.assertEqual(pre["WANT_EMAIL_SEQUENCES"], "no")
        # Byte-for-byte at the nested home: no strip, no summary, no case fold.
        self.assertEqual(pre["EMAIL_SEQUENCES_DECLINED_REASON"], REASON)
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            iw.write_intake_file(run_dir, intake)
            written = json.loads(
                (run_dir / _WRITTEN_INTAKE).read_text(encoding="utf-8"))
            gate = ef.resolve_email_gate(written)
            self.assertEqual(gate["decision"], "waived")
            self.assertEqual(gate["quote"], REASON)

    def test_ledger_carries_both_answers(self):
        intake = _assemble(_complete_answers())
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            ledger_path = iw.write_ledger(run_dir, intake)
            entries = json.loads(
                ledger_path.read_text(encoding="utf-8"))["entries"]
            self.assertEqual(entries["want_email_sequences"]["value"], "no")
            self.assertEqual(
                entries["email_sequences_declined_reason"]["value"], REASON)


class TestFailClosed(unittest.TestCase):
    def test_no_without_reason_fails_closed_at_the_gate(self):
        answers = _complete_answers()
        answers.pop("email_sequences_declined_reason")
        intake = _assemble(answers)
        # The writer stores what it was given (the reason is conditional,
        # never flat-required); the GATE is the fail-closed point.
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            iw.write_intake_file(run_dir, intake)
            gate = ef.resolve_email_gate(json.loads(
                (run_dir / _WRITTEN_INTAKE).read_text(encoding="utf-8")))
            self.assertEqual(gate["decision"], "fail_closed")
            self.assertIn("AF-EMAIL-WAIVER-MISSING", gate["detail"])

    def test_blank_reason_fails_closed_at_the_gate(self):
        intake = _assemble(
            _complete_answers(email_sequences_declined_reason="   "))
        gate = ef.resolve_email_gate(intake)
        self.assertEqual(gate["decision"], "fail_closed")
        self.assertIn("AF-EMAIL-WAIVER-MISSING", gate["detail"])

    def test_absent_toggle_is_incomplete_at_the_writer(self):
        answers = _complete_answers()
        answers.pop("want_email_sequences")
        intake = _assemble(answers)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(iw.IntakeIncompleteError) as cm:
                iw.write_intake_file(Path(td), intake)
            self.assertIn("pre_presentation_capture.WANT_EMAIL_SEQUENCES",
                          str(cm.exception))

    def test_absent_toggle_defers_at_the_gate(self):
        self.assertEqual(ef.resolve_email_gate({})["decision"], "defer")


class TestLegacyMigration(unittest.TestCase):
    def test_deck_brief_filed_values_move_home_verbatim(self):
        legacy = {
            "schema_version": 1,
            "run_id": "OLD",
            "deck_brief": {
                "WANT_EMAIL_SEQUENCES": "no",
                "EMAIL_SEQUENCES_DECLINED_REASON": REASON,
            },
        }
        migrated = iw.migrate_intake(legacy)
        pre = migrated["pre_presentation_capture"]
        self.assertEqual(pre["WANT_EMAIL_SEQUENCES"], "no")
        self.assertEqual(pre["EMAIL_SEQUENCES_DECLINED_REASON"], REASON)
        self.assertNotIn("WANT_EMAIL_SEQUENCES", migrated["deck_brief"])

    def test_flat_top_level_value_moves_home(self):
        legacy = {"schema_version": 1, "run_id": "OLD",
                  "WANT_EMAIL_SEQUENCES": "yes"}
        migrated = iw.migrate_intake(legacy)
        self.assertEqual(
            migrated["pre_presentation_capture"]["WANT_EMAIL_SEQUENCES"],
            "yes")

    def test_contradiction_refuses(self):
        legacy = {
            "schema_version": 1,
            "run_id": "OLD",
            "pre_presentation_capture": {"WANT_EMAIL_SEQUENCES": "yes"},
            "deck_brief": {"WANT_EMAIL_SEQUENCES": "no"},
        }
        with self.assertRaises(iw.ContractMigrationError):
            iw.migrate_intake(legacy)


if __name__ == "__main__":
    unittest.main()
