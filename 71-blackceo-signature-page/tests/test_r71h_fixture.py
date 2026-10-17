"""R71H joint dry-run fixture tests (S71-08 P3).

The committed fixture run at tests/fixtures/r71h-dry-run/run was built
by tests/fixtures/r71h-dry-run/build_fixture.py from fixture input
records, through the real stage gate under the shipped contract: the
ghl-install-test close emitted the hand-off and the dispatch envelope
and hash-locked the hand-off in state, and the publish-verify close
verified the hand-off against the locked hash.

These tests rebuild the fixture into a temporary directory with the
same builder and assert:
  - both gate closes pass on the rebuild (the builder raises if the
    gate refuses either close);
  - the rebuilt hand-off is byte-identical to the committed fixture
    hand-off (the derivation is deterministic), and its SHA-256
    equals the hash locked in the committed fixture's state and
    carried by the committed envelope;
  - the rebuilt envelope matches the committed envelope field for
    field except the minted request_id, whose format is asserted;
  - the committed fixture's publish fetch record records a pass
    verdict from the loopback fetch performed at build time;
  - the committed fixture leaves automation-wiring open (the state a
    real run waits in for Skill 44's receipt).

Synthetic fixture records only. No live GHL, no dispatch, no network
beyond the builder's loopback page server.
"""
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "r71h-dry-run"
COMMITTED_RUN = FIXTURE_DIR / "run"

_spec = importlib.util.spec_from_file_location(
    "r71h_build_fixture", FIXTURE_DIR / "build_fixture.py")
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class R71HFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = Path(tempfile.mkdtemp(prefix="r71h-fixture-"))
        cls.rebuilt = cls.td / "run"
        # Raises (failing the class) if either gate close refuses.
        cls.result = builder.build(cls.rebuilt)

    def test_rebuilt_handoff_byte_identical(self):
        committed = (COMMITTED_RUN / "handoff"
                     / "automation-handoff.json").read_bytes()
        rebuilt = (self.rebuilt / "handoff"
                   / "automation-handoff.json").read_bytes()
        self.assertEqual(rebuilt, committed)

    def test_hash_lock_matches_committed_records(self):
        digest = hashlib.sha256(
            (COMMITTED_RUN / "handoff"
             / "automation-handoff.json").read_bytes()).hexdigest()
        state = load_json(COMMITTED_RUN / "private" / "state.json")
        self.assertEqual(
            state["stages"]["ghl-install-test"]["handoff_sha256"],
            digest)
        envelope = load_json(COMMITTED_RUN / "handoff"
                             / "automation-request.json")
        self.assertEqual(envelope["handoff_sha256"], digest)
        record = load_json(COMMITTED_RUN / "handoff"
                           / "emission-record.json")
        self.assertEqual(record["handoff_sha256"], digest)
        self.assertEqual(record["handoff_origin"], "emitted")

    def test_rebuilt_envelope_matches_except_request_id(self):
        committed = load_json(COMMITTED_RUN / "handoff"
                              / "automation-request.json")
        rebuilt = load_json(self.rebuilt / "handoff"
                            / "automation-request.json")
        self.assertRegex(committed["request_id"], r"^gxo_[0-9a-f]{12}$")
        self.assertRegex(rebuilt["request_id"], r"^gxo_[0-9a-f]{12}$")
        committed.pop("request_id")
        rebuilt.pop("request_id")
        self.assertEqual(rebuilt, committed)
        # The exception entry and both mechanisms survive the rebuild.
        kinds = []
        for w in rebuilt["workflows"]:
            if "no_workflow_reason" in w:
                kinds.append("exception")
            else:
                kinds.append(w["mechanism"]["type"])
        self.assertEqual(sorted(kinds),
                         ["contact_tag", "exception", "native"])

    def test_committed_fixture_state(self):
        state = load_json(COMMITTED_RUN / "private" / "state.json")
        self.assertEqual(state["stages"]["ghl-install-test"]["status"],
                         "closed")
        self.assertEqual(state["stages"]["publish-verify"]["status"],
                         "closed")
        wiring = state["stages"].get("automation-wiring", {})
        self.assertNotEqual(wiring.get("status"), "closed")

    def test_committed_fetch_record_passed(self):
        record = load_json(COMMITTED_RUN / "publish-verify"
                           / "fetch-record.json")
        self.assertEqual(record["verdict"], "pass")
        self.assertEqual(record["status"], 200)
        self.assertTrue(record["url"].startswith("http://127.0.0.1:"))

    def test_rebuilt_publish_close_verified_the_hash(self):
        state = load_json(self.rebuilt / "private" / "state.json")
        self.assertEqual(state["stages"]["publish-verify"]["status"],
                         "closed")
        record = load_json(self.rebuilt / "publish-verify"
                           / "fetch-record.json")
        self.assertEqual(record["verdict"], "pass")


if __name__ == "__main__":
    unittest.main()
