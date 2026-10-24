"""Offline presentation/reply binding checks; no provider or delivery calls."""
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

CORE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CORE))
from storyboard_director import approval_runner as runner
from storyboard_director import approval_package as package
import state_store
from batch_mode.batch import STAGES


class StoryboardPresentationTest(unittest.TestCase):
    def setUp(self):
        transport = patch.object(runner.subprocess, "run", side_effect=AssertionError("external transport forbidden"))
        transport.start()
        self.addCleanup(transport.stop)
        self.temp = tempfile.TemporaryDirectory(prefix="s75-presented-storyboard-")
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "run"
        self.sb = self.run / "storyboard"
        self.sb.mkdir(parents=True)
        (self.run / "control").mkdir()
        self.shots, self.contracts, self.stills = [], {}, {}
        for n in (1, 2, 3):
            sid = "s" + str(n)
            self.shots.append({"shot_id": sid, "song_start": (n - 1) * 8,
                               "song_end": n * 8, "story_stage": "new-chapter", "location_id": "office"})
            self.contracts[sid] = {"lyric_text": "line " + str(n), "viewer_understanding": "a new choice",
                                   "character_action": "takes step " + str(n), "visible_emotion": "hope"}
            path = self.sb / (sid + ".png")
            path.write_bytes(b"synthetic local still " + str(n).encode())
            self.stills[sid] = str(path)
        self.write_sources()
        self.write(self.run / "control" / "card-receipt.json", {"storyboard_approval": True})
        with state_store.Store(self.run / "control" / "state.sqlite3") as store:
            store.init_run("run", [stage for stage, _ in STAGES])
        self.sent = []

    def write(self, path, value):
        Path(path).write_text(json.dumps(value), encoding="utf-8")

    def write_sources(self):
        for name, data in (("shot-list.json", {"shots": self.shots}),
                           ("contracts.json", self.contracts), ("stills.json", self.stills)):
            self.write(self.sb / name, data)

    def send(self, message, images):
        self.sent.append((message, [(n, Path(path).read_bytes()) for n, path in images]))

    def step(self, reply=None, send=None, **kw):
        return runner.run(str(self.run), send or self.send, reply=reply, **kw)

    def state(self):
        return json.loads((self.sb / "approval.json").read_text())

    def assert_stale_go_waits(self):
        count = len(self.sent)
        result = self.step("GO")
        self.assertEqual(result["action"], "waiting", result)
        self.assertEqual(result["reason_code"], "STORYBOARD_PRESENTATION_CHANGED", result)
        self.assertGreater(len(self.sent), count)
        self.assertFalse(runner.gate_open(str(self.run)))
        self.assertFalse((self.run / "control" / "continuation-queue.json").exists())
        self.assertEqual(self.step("yes")["action"], "approved")
        self.assertTrue(runner.gate_open(str(self.run)))

    def test_still_changed_after_presentation_cannot_use_the_old_go(self):
        self.step()
        Path(self.stills["s1"]).write_bytes(b"new unseen still")
        self.assert_stale_go_waits()

    def test_contract_changed_after_presentation_cannot_use_the_old_go(self):
        self.step()
        self.contracts["s1"]["character_action"] = "unseen action"
        self.write_sources()
        self.assert_stale_go_waits()

    def test_shot_identity_add_or_remove_reopens_presentation(self):
        for remove in (False, True):
            with self.subTest(remove=remove):
                (self.sb / "approval.json").unlink(missing_ok=True)
                self.step()
                before = copy.deepcopy(self.shots)
                if remove:
                    self.shots.pop()
                else:
                    extra = dict(self.shots[-1], shot_id="s4", song_start=24, song_end=32)
                    self.shots.append(extra)
                    self.contracts["s4"] = dict(self.contracts["s3"])
                    self.stills["s4"] = self.stills["s3"]
                self.write_sources()
                result = self.step("GO")
                self.assertEqual(result["action"], "waiting", result)
                self.assertFalse(runner.gate_open(str(self.run)))
                self.shots = before
                self.write_sources()

    def test_initial_send_cannot_capture_mutated_unseen_bytes_as_presented(self):
        expected = package.approval_entries(self.shots, self.contracts, self.stills)
        def mutate_after_delivery(message, images):
            self.send(message, images)
            Path(self.stills["s1"]).write_bytes(b"changed during delivery")
        self.step(send=mutate_after_delivery)
        self.assertEqual(self.state()["shots"]["s1"]["revision"], expected["s1"]["revision"])
        self.assert_stale_go_waits()

    def test_current_go_replay_preserves_approval_and_single_continuation(self):
        self.step()
        self.assertEqual(self.step("GO")["action"], "approved")
        state = (self.sb / "approval.json").read_bytes()
        queue = (self.run / "control" / "continuation-queue.json").read_bytes()
        count = len(self.sent)
        self.assertEqual(self.step("GO")["action"], "approved")
        self.assertEqual((self.sb / "approval.json").read_bytes(), state)
        self.assertEqual((self.run / "control" / "continuation-queue.json").read_bytes(), queue)
        self.assertEqual(len(self.sent), count)

    def test_changed_approved_replay_must_not_claim_approved(self):
        self.step()
        self.step("GO")
        Path(self.stills["s1"]).write_bytes(b"changed after approval")
        self.assertFalse(runner.gate_open(str(self.run)))
        result = self.step("GO")
        self.assertEqual(result["action"], "waiting", result)
        self.assertFalse(runner.gate_open(str(self.run)))

    def test_unbound_pending_and_bare_legacy_approved_represent_without_fabrication(self):
        for state in ("pending", "approved"):
            with self.subTest(state=state):
                self.write(self.sb / "approval.json", {"state": state, "choice": "yes"})
                self.assertFalse(runner.gate_open(str(self.run)))
                result = self.step("GO")
                self.assertEqual(result["action"], "waiting", result)
                self.assertEqual(result["reason_code"], "STORYBOARD_PRESENTATION_UNVERIFIED", result)
                self.assertEqual(self.state()["state"], "pending")
                self.assertFalse((self.run / "control" / "continuation-queue.json").exists())

    def test_verifiable_legacy_revision_map_remains_read_only_and_valid(self):
        self.step()
        self.step("GO")
        state = self.state()
        for row in state["shots"].values():
            row.pop("still_sha256", None)  # existing revision already binds the still bytes
        self.write(self.sb / "approval.json", state)
        before = (self.sb / "approval.json").read_bytes()
        self.assertTrue(runner.gate_open(str(self.run)))
        self.assertEqual(self.step("GO")["action"], "approved")
        self.assertEqual((self.sb / "approval.json").read_bytes(), before)

    def test_direct_approval_requires_a_reply_and_reads_saved_presentation(self):
        self.step()
        result = runner._approve(str(self.run), self.shots, self.contracts, self.stills, "yes", self.state())
        self.assertEqual(result["reason_code"], "STORYBOARD_APPROVAL_REPLY_REQUIRED")
        Path(self.stills["s1"]).write_bytes(b"new unseen direct-call still")
        override = dict(self.state(), shots=package.approval_entries(self.shots, self.contracts, self.stills))
        result = runner._approve(str(self.run), self.shots, self.contracts, self.stills,
                                 "yes", override, reply="GO")
        self.assertEqual(result["reason_code"], "STORYBOARD_PRESENTATION_CHANGED")
        self.assertFalse(runner.gate_open(str(self.run)))
        self.assertFalse((self.run / "control" / "continuation-queue.json").exists())

    def test_no_preference_auto_approves_current_package_without_delivery(self):
        self.write(self.run / "control" / "card-receipt.json", {"storyboard_approval": False})
        self.assertEqual(self.step()["action"], "approved")
        Path(self.stills["s1"]).write_bytes(b"updated automatic QC package")
        self.assertEqual(self.step()["action"], "approved")
        self.assertTrue(runner.gate_open(str(self.run)))
        self.assertEqual(self.sent, [])

    def test_named_revision_snapshot_is_taken_before_its_delivery(self):
        self.step()
        def make_still(sid, card):
            path = self.sb / (sid + "-revised.png")
            path.write_bytes(b"requested revision")
            return str(path)
        def mutate_after_delivery(message, images):
            self.send(message, images)
            Path(images[0][1]).write_bytes(b"unseen after named revision delivery")
        self.assertEqual(self.step("shot 2: change standing", send=mutate_after_delivery,
                                   make_still=make_still)["action"], "revised")
        self.assert_stale_go_waits()


if __name__ == "__main__":
    unittest.main()
