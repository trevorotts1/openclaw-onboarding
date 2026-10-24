"""Real factory CLI replies bind a new client message to the displayed package.

All intake, Store, presentation, decision and stage admission paths are real.
Temporary runs only; no providers, media generation or client-send subprocesses.
"""
from contextlib import redirect_stdout
import hashlib
import importlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

CORE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CORE))
from intake_preflight import factory
from script_approval import approval_events as events
from script_approval import script_approval as approval
from test_production_process import confirmed_run, complete_stage, write_json, run_hashes


class FactoryScriptReplyProvenance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="factory-script-reply-")
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / "run"
        self.run_id = confirmed_run(self.run)
        for stage in ("research", "creative-strategy", "script-lyrics"):
            complete_stage(self.run, stage)
        shutil.copyfile(CORE / "story_arc" / "fixtures" / "valid.json", self.run / "creative" / "story.json")
        shutil.copyfile(CORE / "lyric_writer" / "fixtures" / "campaign.json", self.run / "creative" / "lyrics.json")
        self.doc = {"title": "The Climb", "story": [["The world", ["She runs a small shop."]]],
                    "sheet": [{"tag": "Intro", "lines": ["One closed door."]},
                              {"tag": "Hook 1", "lines": ["I am not sma-a-all", "I ne-ever wa-a-as"]}]}
        self.doc["lyrics"] = "\n".join(line for part in self.doc["sheet"] for line in part["lines"])
        write_json(self.run / "creative" / "script.json", self.doc)
        code, self.pending = self.cli("next", "--run-dir", str(self.run))
        self.assertEqual(code, 2, self.pending)
        self.assertEqual(self.pending["reason_code"], "SCRIPT_AWAITING_APPROVAL", self.pending)
        self.ask_id = self.pending["data"]["approval_context"]["asks"][-1]["ask_id"]

    def cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = factory.main(list(args))
        return code, json.loads(out.getvalue())

    def context_flags(self, **overrides):
        fields = {"reply-source": "client", "answer-source-ref": "new-client-script-reply",
                  "presentation-ask-id": self.ask_id, "run-id": self.run_id}
        fields.update(overrides)
        return [item for key, value in fields.items() if value is not None
                for item in ("--" + key, value)]

    def reply(self, text="I approve both", flags=None):
        return self.cli("script-reply", "--run-dir", str(self.run), "--reply", text,
                        *(self.context_flags() if flags is None else flags))

    def assert_read_only_refusal(self, code, *, text="I approve both", flags=None):
        before = run_hashes(self.run)
        # Resolve the actual consumer after fixture confirmation; other suites
        # may reload packages while exercising their own direct entrypoints.
        stage = importlib.import_module("script_approval.stage")
        with patch.object(stage, "run_stage", side_effect=AssertionError("refused reply reached a writer")) as trap:
            exit_code, result = self.reply(text, flags)
        self.assertEqual(exit_code, 2, result)
        self.assertEqual(result["reason_code"], code, result)
        self.assertEqual(result["outcome"], "waiting")
        self.assertEqual(result["data"]["delivered"], [])
        trap.assert_not_called()
        self.assertEqual(run_hashes(self.run), before)
        self.assertEqual(events.decisions(approval.record_for(self.run)), [])

    def test_pending_exposes_actual_whole_package_presentation_without_reply_defaults(self):
        context = self.pending["data"]["approval_context"]
        record = approval.record_for(self.run)
        self.assertEqual(context["run_id"], self.run_id)
        self.assertTrue(context["sent"])
        self.assertEqual(context["asks"], events.open_asks(record))
        self.assertEqual(context["artifacts"], record["artifacts"])
        self.assertEqual(set(context["asks"][-1]["kinds"]), {"script", "lyrics"})
        self.assertNotIn("source", context)
        self.assertNotIn("source_ref", context)
        self.assertIn("THE SONG LYRICS", "\n".join(self.pending["data"]["delivered"]))
        code, resumed = self.cli("next", "--run-dir", str(self.run))
        self.assertEqual(code, 2)
        self.assertEqual(resumed["data"]["approval_context"]["asks"], context["asks"])
        self.assertEqual(resumed["data"]["delivered"], [])

    def test_missing_foreign_assistant_and_reused_intake_context_never_reach_writers(self):
        cases = (([], "ARTIFACT_REPLY_CONTEXT_REQUIRED"),
                 (self.context_flags(**{"reply-source": None}), "ARTIFACT_REPLY_CONTEXT_REQUIRED"),
                 (self.context_flags(**{"answer-source-ref": None}), "ARTIFACT_REPLY_CONTEXT_REQUIRED"),
                 (self.context_flags(**{"presentation-ask-id": None}), "ARTIFACT_REPLY_CONTEXT_REQUIRED"),
                 (self.context_flags(**{"run-id": None}), "ARTIFACT_REPLY_CONTEXT_REQUIRED"),
                 (self.context_flags(**{"reply-source": "assistant"}), "ARTIFACT_REPLY_SOURCE_INVALID"),
                 (self.context_flags(**{"answer-source-ref": "offline-owner-fixture:script"}), "ARTIFACT_REPLY_INTAKE_REUSED"),
                 (self.context_flags(**{"run-id": "another-run"}), "ARTIFACT_REPLY_SCOPE_MISMATCH"),
                 (self.context_flags(**{"presentation-ask-id": "unseen-presentation"}), "ARTIFACT_REPLY_PRESENTATION_MISMATCH"))
        for flags, code in cases:
            with self.subTest(code=code):
                self.assert_read_only_refusal(code, flags=flags)

    def test_view_first_and_numeric_intake_options_are_not_current_artifact_approval(self):
        intake = json.loads((self.run / "control" / "intake-session.json").read_text())
        preference = intake["answer_records"]["script"]["parsed"]["text"]
        for raw in (preference, "yes, show me first", "1", "option 1"):
            with self.subTest(raw=raw):
                self.assert_read_only_refusal("ARTIFACT_REPLY_IS_PREFERENCE", text=raw)

    def test_explicit_new_client_reply_approves_current_whole_package_then_admits_music(self):
        code, accepted = self.reply()
        self.assertEqual(code, 0, accepted)
        self.assertEqual(accepted["reason_code"], "script-approved")
        record = approval.record_for(self.run)
        self.assertEqual({event["kind"] for event in record["approvals"]}, {"script", "lyrics"})
        for event in record["approvals"]:
            self.assertEqual(event["source"], "client")
            self.assertEqual(event["source_ref"], "new-client-script-reply")
            self.assertEqual(event["presentation_ask_id"], self.ask_id)
            self.assertEqual(event["run_id"], self.run_id)
            self.assertEqual(event["reply_text"], "I approve both")
        code, ready = self.cli("next", "--run-dir", str(self.run))
        self.assertEqual(code, 0, ready)
        self.assertEqual(ready["data"]["stage"], "music")
        self.assertTrue(ready["data"]["production_admitted"])
        self.assertIn("song_choices/song_choices.py generate", ready["data"]["command"])
        # An exact replay may acknowledge this same decision, without minting
        # another approval event or transferring approval to another revision.
        count = len(record["approvals"])
        code, repeated = self.reply()
        self.assertEqual(code, 0, repeated)
        self.assertEqual(len(approval.record_for(self.run)["approvals"]), count)

    def test_changed_disk_script_cannot_be_approved_under_an_old_presentation(self):
        self.doc["story"][0][1].append("A different ending.")
        write_json(self.run / "creative" / "script.json", self.doc)
        self.assert_read_only_refusal("ARTIFACT_REPLY_ARTIFACT_CHANGED")

    def test_represented_revision_refuses_old_ask_without_mutation(self):
        self.doc["story"][0][1].append("The new ending.")
        write_json(self.run / "creative" / "script.json", self.doc)
        approval.request_approval(self.run, self.doc["title"], self.doc["story"], self.doc["sheet"],
                                  self.doc["lyrics"], context={"run_id": self.run_id})
        approval.mark_sent(self.run)
        current = events.open_asks(approval.record_for(self.run))[-1]["ask_id"]
        self.assertNotEqual(current, self.ask_id)
        self.assert_read_only_refusal("ARTIFACT_REPLY_PRESENTATION_MISMATCH")
        code, approved = self.reply(flags=self.context_flags(**{"presentation-ask-id": current}))
        self.assertEqual(code, 0, approved)

    def test_verifiable_existing_legacy_whole_package_decision_remains_readable(self):
        # Reproduce the supported older event schema through its actual event
        # writer, retaining actor, run, origin and sent presentation revisions.
        approval.request_approval(self.run, self.doc["title"], self.doc["story"], self.doc["sheet"],
                                  self.doc["lyrics"],
                                  context={"run_id": self.run_id, "conversation_id": "offline-owner-conversation"},
                                  message_id="legacy-presentation")
        approval.mark_sent(self.run)
        record = approval.record_for(self.run)
        record.pop("reply_contract", None)
        context = {"run_id": self.run_id, "conversation_id": "offline-owner-conversation",
                   "approved_by": "fixture-client", "reply_to_message_id": "legacy-presentation",
                   "reply_text": "I approve both", "reply_text_sha": hashlib.sha256(b"i approve both").hexdigest()}
        events.record_decision(record, ("script", "lyrics"), context)
        events.close_decided_asks(record, ("script", "lyrics"))
        events.project(record, approval.lyrics_sha(self.doc["lyrics"]))
        events.save_record(self.run, record)
        before = run_hashes(self.run)
        code, ready = self.cli("next", "--run-dir", str(self.run))
        self.assertEqual(code, 0, ready)
        self.assertEqual(ready["data"]["stage"], "music")
        self.assertTrue(ready["data"]["production_admitted"])
        self.assertEqual(run_hashes(self.run), before)


if __name__ == "__main__":
    unittest.main()
