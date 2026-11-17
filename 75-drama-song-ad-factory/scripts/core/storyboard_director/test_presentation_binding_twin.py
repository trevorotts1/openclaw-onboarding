"""Whole-package storyboard presentation binding for the Claude-Nine runner.

Synthetic local stills and a recording sender only; no provider or transport.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

CORE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CORE))
from storyboard_director import approval_runner as runner
from batch_mode.batch import STAGES
from state_store import Store


class TwinPresentationBinding(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="s75-twin-board-")
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "run"
        self.board = self.run / "storyboard"
        self.board.mkdir(parents=True)
        self.sent = []
        self.send = lambda message, images: self.sent.append((message, images))
        shots, contracts, stills = [], {}, {}
        for n in (1, 2):
            sid = "s%d" % n
            shots.append({"shot_id": sid, "song_start": (n - 1) * 8, "song_end": n * 8,
                          "story_stage": "new-chapter", "location_id": "office"})
            contracts[sid] = {"lyric_text": "line%d" % n, "viewer_understanding": "new step",
                              "character_action": "takes a step", "visible_emotion": "hope"}
            path = self.board / (sid + ".png")
            path.write_bytes(b"synthetic still" + bytes([n]))
            stills[sid] = str(path)
        for name, value in (("shot-list.json", {"shots": shots}), ("contracts.json", contracts),
                            ("stills.json", stills)):
            (self.board / name).write_text(json.dumps(value))
        (self.run / "control").mkdir()
        self.receipt = self.run / "control" / "card-receipt.json"
        self.receipt.write_text(json.dumps({"storyboard_approval": True}))
        with Store(self.run / "control" / "state.sqlite3") as store:
            store.init_run("run", [name for name, _ in STAGES])

    def test_whole_package_go_records_revision_bound_decision_and_resume_sends_nothing(self):
        self.assertEqual(runner.run(str(self.run), self.send)["action"], "waiting")
        state = json.loads((self.board / "approval.json").read_text())
        self.assertEqual(set(state["shots"]), {"s1", "s2"})
        self.assertEqual(len(self.sent[0][1]), 2)
        self.assertEqual(runner.run(str(self.run), self.send, reply="GO")["action"], "approved")
        self.assertTrue(runner.gate_open(str(self.run)))
        approved = json.loads((self.board / "approval.json").read_text())
        self.assertEqual(approved["decision"]["scope"], "whole-package")
        self.assertEqual(approved["decision"]["reply_text"], "GO")
        runner.run(str(self.run), self.send, reply="GO")
        self.assertEqual(len(self.sent), 1)
        (self.board / "s1.png").write_bytes(b"changed current still")
        self.assertFalse(runner.gate_open(str(self.run)))
        result = runner.run(str(self.run), self.send, reply="GO")
        self.assertEqual(result["reason_code"], "STORYBOARD_PRESENTATION_CHANGED")
        self.assertEqual(json.loads((self.board / "approval.json").read_text())["previous_approval"]["state"], "approved")
        self.assertEqual(runner.run(str(self.run), self.send, reply="GO")["action"], "approved")

    def test_changed_pending_asset_or_sender_time_change_never_becomes_approved(self):
        def changing_sender(message, images):
            self.send(message, images)
            (self.board / "s1.png").write_bytes(b"changed during send")
        runner.run(str(self.run), changing_sender)
        before = (self.board / "approval.json").read_bytes()
        result = runner.run(str(self.run), self.send, reply="GO")
        self.assertEqual(result["reason_code"], "STORYBOARD_PRESENTATION_CHANGED")
        current = json.loads((self.board / "approval.json").read_text())
        self.assertNotEqual(current["shots"]["s1"]["revision"], json.loads(before)["shots"]["s1"]["revision"])
        self.assertTrue(result["message_sent"])
        self.assertFalse((self.board / "gate.json").exists())
        self.assertEqual(runner.run(str(self.run), self.send, reply="GO")["action"], "approved")

    def test_unbound_legacy_approved_flag_is_retained_while_current_package_waits(self):
        path = self.board / "approval.json"
        path.write_text(json.dumps({"state": "approved", "choice": "yes", "at": 1}))
        before = path.read_bytes()
        self.assertFalse(runner.gate_open(str(self.run)))
        result = runner.run(str(self.run), self.send, reply="GO")
        self.assertEqual(result["reason_code"], "STORYBOARD_PRESENTATION_UNVERIFIED")
        current = json.loads(path.read_text())
        self.assertEqual(current["previous_approval"], json.loads(before))
        self.assertEqual(current["state"], "pending")
        self.assertEqual(len(self.sent), 1)
        self.assertFalse(runner.gate_open(str(self.run)))

    def test_declined_approval_still_binds_current_assets_without_sending(self):
        self.receipt.write_text(json.dumps({"storyboard_approval": False}))
        self.assertEqual(runner.run(str(self.run), self.send)["action"], "approved")
        self.assertTrue(runner.gate_open(str(self.run)))
        self.assertEqual(self.sent, [])
        (self.board / "s2.png").write_bytes(b"changed after explicit No")
        self.assertFalse(runner.gate_open(str(self.run)))
        self.assertEqual(runner.run(str(self.run), self.send)["action"], "approved")
        self.assertTrue(runner.gate_open(str(self.run)))
        self.assertNotIn("decision", json.loads((self.board / "approval.json").read_text()))
        self.assertEqual(self.sent, [])

    def test_named_revision_resends_only_that_shot_then_whole_package_go(self):
        runner.run(str(self.run), self.send)
        def remake(sid, card):
            path = self.board / (sid + "-revised.png")
            path.write_bytes(b"synthetic revised still")
            return str(path)
        result = runner.run(str(self.run), self.send, reply="shot 2: change stand up", make_still=remake)
        self.assertEqual(result["action"], "revised")
        self.assertEqual([n for n, path in self.sent[-1][1]], [2])
        self.assertFalse(runner.gate_open(str(self.run)))
        self.assertEqual(runner.run(str(self.run), self.send, reply="GO")["action"], "approved")
        self.assertTrue(runner.gate_open(str(self.run)))

    def test_still_changed_after_presentation_needs_a_fresh_whole_package_go(self):
        runner.run(str(self.run), self.send)
        (self.board / "s1.png").write_bytes(b"unseen replacement")
        result = runner.run(str(self.run), self.send, reply="GO")
        self.assertEqual(result["reason_code"], "STORYBOARD_PRESENTATION_CHANGED")
        self.assertFalse(runner.gate_open(str(self.run)))
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(runner.run(str(self.run), self.send, reply="GO")["action"], "approved")

    def test_contract_changed_after_presentation_is_shown_before_fresh_approval(self):
        runner.run(str(self.run), self.send)
        path = self.board / "contracts.json"
        contracts = json.loads(path.read_text())
        contracts["s1"]["character_action"] = "unseen different action"
        path.write_text(json.dumps(contracts))
        result = runner.run(str(self.run), self.send, reply="GO")
        self.assertEqual(result["reason_code"], "STORYBOARD_PRESENTATION_CHANGED")
        self.assertFalse((self.board / "gate.json").exists())
        self.assertIn("unseen different action", self.sent[-1][0])

    def test_added_or_removed_shot_identity_reopens_the_whole_presentation(self):
        paths = [self.board / name for name in ("shot-list.json", "contracts.json", "stills.json")]
        originals = [p.read_bytes() for p in paths]
        for remove in (False, True):
            with self.subTest(remove=remove):
                for path, original in zip(paths, originals):
                    path.write_bytes(original)
                (self.board / "approval.json").unlink(missing_ok=True)
                runner.run(str(self.run), self.send)
                document, contracts, stills = [json.loads(path.read_text()) for path in paths]
                if remove:
                    document["shots"].pop()
                else:
                    document["shots"].append(dict(document["shots"][-1], shot_id="s3", song_start=16, song_end=24))
                    contracts["s3"] = dict(contracts["s2"])
                    stills["s3"] = stills["s2"]
                for path, value in zip(paths, (document, contracts, stills)):
                    path.write_text(json.dumps(value))
                result = runner.run(str(self.run), self.send, reply="GO")
                self.assertEqual(result["reason_code"], "STORYBOARD_PRESENTATION_CHANGED")
                self.assertFalse(runner.gate_open(str(self.run)))

    def test_verified_revision_only_legacy_map_is_preserved_without_invented_decision(self):
        runner.run(str(self.run), self.send)
        runner.run(str(self.run), self.send, reply="GO")
        path = self.board / "approval.json"
        state = json.loads(path.read_text())
        state.pop("decision")
        for row in state["shots"].values():
            row.pop("still_sha256")
        path.write_text(json.dumps(state))
        before = path.read_bytes()
        self.assertTrue(runner.gate_open(str(self.run)))
        self.assertEqual(runner.run(str(self.run), self.send, reply="GO")["action"], "approved")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(self.sent), 1)

    def test_direct_approval_requires_reply_and_ignores_supplied_fake_presentation(self):
        runner.run(str(self.run), self.send)
        shots, contracts, stills = runner._load(str(self.run))
        path = self.board / "approval.json"
        state = json.loads(path.read_text())
        result = runner._approve(str(self.run), shots, contracts, stills, "yes", state)
        self.assertEqual(result["reason_code"], "STORYBOARD_APPROVAL_REPLY_REQUIRED")
        (self.board / "s1.png").write_bytes(b"unseen direct call replacement")
        state["shots"] = runner.AP.approval_entries(shots, contracts, stills)
        result = runner._approve(str(self.run), shots, contracts, stills, "yes", state, reply="GO")
        self.assertEqual(result["reason_code"], "STORYBOARD_PRESENTATION_CHANGED")
        self.assertFalse((self.board / "gate.json").exists())

    def test_named_revision_snapshot_precedes_its_delivery(self):
        runner.run(str(self.run), self.send)
        def remake(sid, card):
            path = self.board / (sid + "-revised.png")
            path.write_bytes(b"requested revision")
            return str(path)
        def changing_sender(message, images):
            self.send(message, images)
            Path(images[0][1]).write_bytes(b"changed during named revision delivery")
        result = runner.run(str(self.run), changing_sender, reply="shot 2: change stand up", make_still=remake)
        self.assertEqual(result["action"], "revised")
        result = runner.run(str(self.run), self.send, reply="GO")
        self.assertEqual(result["reason_code"], "STORYBOARD_PRESENTATION_CHANGED")
        self.assertFalse(runner.gate_open(str(self.run)))


if __name__ == "__main__":
    unittest.main()
