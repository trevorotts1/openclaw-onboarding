"""No-media regressions: intake preference versus current artifact approval."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

CORE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CORE))
from script_approval import approval_events as events
from script_approval import script_approval as approval
import production_process
from test_production_process import confirmed_run, complete_stage, write_json, run_hashes


class ReplyProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="s75-script-reply-")
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / "run"
        confirmed_run(self.run)
        self.doc = {"title": "A new chapter", "story": [["Act 1", ["Christine watches the clock."]]],
                    "sheet": [{"tag": "Verse", "lines": ["I choose a new chapter today"]}],
                    "lyrics": "I choose a new chapter today"}
        write_json(self.run / "creative" / "script.json", self.doc)
        self.present()

    def present(self):
        approval.request_approval(self.run, self.doc["title"], self.doc["story"], self.doc["sheet"],
                                  self.doc["lyrics"], maker="fixture-builder",
                                  context={"run_id": self.run.name, "conversation_id": "owner-chat"},
                                  message_id="presented-script")
        approval.mark_sent(self.run)

    def context(self, **over):
        rec = approval.record_for(self.run)
        context = {"source": "client", "source_ref": "new-owner-script-reply",
                   "presentation_ask_id": events.open_asks(rec)[-1]["ask_id"],
                   "run_id": self.run.name, "conversation_id": "owner-chat", "approved_by": "fixture-client",
                   "reply_to_message_id": "presented-script"}
        context.update(over)
        return context

    def reply(self, text, context):
        def no_edit(*args):
            raise AssertionError("A refused approval/preference must not mutate the script")
        return approval.handle_reply(self.run, text, self.doc["title"], self.doc["story"],
                                     self.doc["sheet"], self.doc["lyrics"], no_edit,
                                     lambda *args: [], context=context)

    def test_view_first_language_and_numeric_intake_choices_never_approve_artifacts(self):
        for text in ("yes, show me first", "Yes, show me the script first", "1", "option 1",
                     "I want to review the lyrics first", "approve after I see it"):
            with self.subTest(text=text):
                before = run_hashes(self.run)
                result = self.reply(text, self.context())
                self.assertEqual(result["reason_code"], "ARTIFACT_REPLY_IS_PREFERENCE", result)
                self.assertEqual(result["status"], "pending")
                self.assertEqual(events.decisions(approval.record_for(self.run)), [])
                self.assertEqual(run_hashes(self.run), before)
                self.assertEqual(events.interpret_reply(text, approval.record_for(self.run), self.context())["intent"], "preference")

    def test_modern_missing_assistant_reused_intake_and_foreign_context_refuse_without_writes(self):
        cases = (({}, "ARTIFACT_REPLY_CONTEXT_REQUIRED"),
                 (self.context(source="assistant"), "ARTIFACT_REPLY_SOURCE_INVALID"),
                 (self.context(source_ref="offline-owner-fixture:script"), "ARTIFACT_REPLY_INTAKE_REUSED"),
                 (self.context(presentation_ask_id="unseen-ask"), "ARTIFACT_REPLY_PRESENTATION_MISMATCH"),
                 (self.context(run_id="another-run"), "ARTIFACT_REPLY_SCOPE_MISMATCH"))
        for context, code in cases:
            with self.subTest(code=code):
                before = run_hashes(self.run)
                result = self.reply("I approve both", context)
                self.assertEqual(result["reason_code"], code, result)
                self.assertEqual(run_hashes(self.run), before)

    def test_explicit_yes_from_distinct_current_client_reply_approves_whole_package_once(self):
        context = self.context()
        result = self.reply("yes", context)
        self.assertEqual(result["status"], "approved", result)
        record = approval.record_for(self.run)
        self.assertEqual({e["kind"] for e in record["approvals"]}, {"script", "lyrics"})
        for event in record["approvals"]:
            self.assertEqual(event["source"], "client")
            self.assertEqual(event["source_ref"], context["source_ref"])
            self.assertEqual(event["presentation_ask_id"], context["presentation_ask_id"])
            self.assertEqual(event["reply_text"], "yes")
        # Intake also contains a generic yes recap. Its word hash alone must
        # not invalidate this distinct, presentation-bound artifact reply.
        proof = production_process._script_proof(self.run, self.run.name)
        self.assertTrue(proof["ok"], proof)
        repeated = self.reply("yes", context)
        self.assertTrue(repeated["duplicate"], repeated)
        self.assertEqual(len(events.decisions(approval.record_for(self.run))), 1)

    def test_current_presentation_identity_changes_with_revisions(self):
        old_context = self.context()
        old_id = old_context["presentation_ask_id"]
        self.doc["story"][0][1].append("A revised ending")
        write_json(self.run / "creative" / "script.json", self.doc)
        self.present()
        self.assertNotEqual(self.context()["presentation_ask_id"], old_id)
        before = run_hashes(self.run)
        refused = self.reply("I approve both", old_context)
        self.assertEqual(refused["reason_code"], "ARTIFACT_REPLY_PRESENTATION_MISMATCH")
        self.assertEqual(run_hashes(self.run), before)
        self.assertEqual(self.reply("I approve both", self.context())["status"], "approved")

    def test_on_disk_script_change_requires_a_new_presentation_before_any_decision(self):
        context = self.context()
        self.doc["story"][0][1].append("An unseen revised ending")
        write_json(self.run / "creative" / "script.json", self.doc)
        before = run_hashes(self.run)
        proof = approval.reply_provenance(self.run, context=context, reply="I approve both")
        self.assertEqual(proof["reason_code"], "ARTIFACT_REPLY_ARTIFACT_CHANGED", proof)
        result = self.reply("I approve both", context)
        self.assertEqual(result["reason_code"], "ARTIFACT_REPLY_ARTIFACT_CHANGED", result)
        self.assertEqual(run_hashes(self.run), before)
        self.assertEqual(events.decisions(approval.record_for(self.run)), [])

    def test_direct_modern_decision_writer_cannot_accept_missing_context(self):
        record = approval.record_for(self.run)
        before = copy.deepcopy(record)
        with self.assertRaises(ValueError):
            events.record_decision(record, ("script", "lyrics"), {})
        self.assertEqual(record, before)

    def legacy_decision(self, *, actor=True):
        record = approval.record_for(self.run)
        record.pop("reply_contract", None)  # reproduce the supported older event shape
        context = {"run_id": self.run.name, "conversation_id": "owner-chat",
                   "reply_to_message_id": "presented-script", "reply_text": "I approve both",
                   "reply_text_sha": hashlib.sha256(b"i approve both").hexdigest()}
        if actor:
            context["approved_by"] = "fixture-client"
        events.record_decision(record, ("script", "lyrics"), context)
        events.close_decided_asks(record, ("script", "lyrics"))
        events.project(record, approval.lyrics_sha(self.doc["lyrics"]))
        events.save_record(self.run, record)

    def test_existing_verifiable_legacy_artifact_decision_stays_readable_and_current(self):
        self.legacy_decision()
        before = run_hashes(self.run)
        proof = production_process._script_proof(self.run, self.run.name)
        self.assertTrue(proof["ok"], proof)
        self.assertIsNone(approval.check_script_approval(approval.record_for(self.run), self.doc["lyrics"]))
        self.assertEqual(run_hashes(self.run), before)

    def test_existing_contextless_decision_pauses_without_rewriting_approval_or_script(self):
        self.legacy_decision(actor=False)
        before = run_hashes(self.run)
        proof = production_process._script_proof(self.run, self.run.name)
        self.assertEqual(proof["reason_code"], "ARTIFACT_REPLY_PROVENANCE_UNVERIFIED", proof)
        self.assertEqual(run_hashes(self.run), before)

    def test_existing_translated_show_first_preference_is_not_legacy_artifact_approval(self):
        self.legacy_decision()
        record = approval.record_for(self.run)
        intake = json.loads((self.run / "control" / "intake-session.json").read_text())
        label = intake["answer_records"]["script"]["parsed"]["text"]
        self.assertTrue(events.is_preference_reply(label), label)
        for event in record["approvals"]:
            event.pop("reply_text", None)
            event["reply_text_sha"] = hashlib.sha256(label.strip().lower().encode("utf-8")).hexdigest()
        events.save_record(self.run, record)
        before = run_hashes(self.run)
        proof = production_process._script_proof(self.run, self.run.name)
        self.assertEqual(proof["reason_code"], "ARTIFACT_REPLY_IS_PREFERENCE", proof)
        self.assertEqual(run_hashes(self.run), before)


if __name__ == "__main__":
    unittest.main()
