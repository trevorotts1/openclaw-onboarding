"""End-to-end dry-run: Receiver + CafExecutor against recorded CLI
transcripts. Proves the whole dispatch pipeline (probe → snapshot →
build → read-back → QC → receipt → judge) composes, with no live
engine contact. Fixtures are transcripts, never labeled live proof.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "store"))
from caf_executor import CafExecutor
from receiver import EXIT_OK, Receiver, judge_receipt, plan_hash
from store import Store
from test_caf_executor import (BUILD_OK, DOCTOR_PASS, DOCTOR_TOKEN_WARN,
                               EXPORT_OK, QC_OK)


def full_script(doctor):
    def run(argv, timeout):
        if argv[1] == "doctor":
            return doctor
        if argv[1:3] == ["workflows", "build"]:
            return BUILD_OK
        if argv[1:3] == ["workflows", "export"]:
            return EXPORT_OK
        if argv[1:3] == ["workflows", "qc"]:
            return QC_OK
        raise AssertionError(f"unexpected argv {argv}")
    return run


def make_request():
    plan = {"_meta": {"deploy_mode": "draft-only"},
            "folder": "Signature Launch",
            "welcome": {"name": "Welcome", "tag": "email-engine:welcome"}}
    return {
        "request_id": "gxo_e2e000000001", "request_version": 1,
        "location_id": "LOC1", "launch_id": "LN1",
        "requesting_room": "S50", "deploy_mode": "draft-only",
        "approval": {"ref": "owner-batch-1", "plan_hash": plan_hash(plan)},
        "plan": plan,
        "workflows": [{"slug": "welcome", "expected_steps": 2,
                       "allow_multiple": True,
                       "trigger": {"type": "contact_tag"}}],
    }


class DryRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / "s44.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_dispatch_judges_verified(self):
        ex = CafExecutor(runner=full_script(DOCTOR_PASS),
                         snapshot_dir=self.tmp.name)
        rx = Receiver(self.store, ex, configured_location="LOC1")
        code, receipt = rx.dispatch(make_request())
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(receipt["status_claimed"], "verified")
        verdict = judge_receipt(receipt)
        self.assertEqual(verdict["overall"], "VERIFIED")
        self.assertEqual(receipt["execution"]["access_tier_used"],
                         "tier0-caf")
        # a snapshot file actually landed (AC20 evidence on disk)
        snaps = [p for p in Path(self.tmp.name).glob("LOC1-welcome-*.json")]
        self.assertEqual(len(snaps), 1)

    def test_dead_token_blocks_before_any_build(self):
        builds = []

        def run(argv, timeout):
            if argv[1] == "doctor":
                return DOCTOR_TOKEN_WARN
            builds.append(argv)
            return full_script(DOCTOR_PASS)(argv, timeout)

        ex = CafExecutor(runner=run, snapshot_dir=self.tmp.name)
        rx = Receiver(self.store, ex, configured_location="LOC1")
        code, receipt = rx.dispatch(make_request())
        self.assertNotEqual(code, EXIT_OK)
        self.assertEqual(receipt["status_claimed"], "blocked-auth")
        self.assertIn("absent-or-dead",
                      json.dumps(receipt))
        self.assertEqual(builds, [])  # nothing past the probe


if __name__ == "__main__":
    unittest.main()
