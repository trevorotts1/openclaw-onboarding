"""launch-c plan reader checks. Run: python3 launch-c/tests/test_plan_reader.py"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAUNCH_C = HERE.parent
REPO = LAUNCH_C.parent
FIXTURES = LAUNCH_C / "fixtures"
PLAN_FIXTURE = REPO / "shared-utils" / "signature_launch_contract" / "fixtures" / "elevation.json"

_spec = importlib.util.spec_from_file_location("plan_reader", LAUNCH_C / "plan_reader.py")
plan_reader = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plan_reader)

PRE = FIXTURES / "build-plan-pre-launch.json"
MAIN = FIXTURES / "build-plan-main-launch.json"
DOORS = FIXTURES / "build-plan-doors-closing.json"
ABANDONED = FIXTURES / "build-plan-abandoned-checkout.json"
WELCOME = FIXTURES / "build-plan-welcome-access.json"


def run_reader(build_plans, plan_path=PLAN_FIXTURE, sequence_map=None):
    out = Path(tempfile.mkdtemp()) / "automation-builds.json"
    argv = ["--launch-plan", str(plan_path), "--out", str(out)]
    for path in build_plans:
        argv += ["--build-plan", str(path)]
    if sequence_map:
        argv += ["--sequence-map", str(sequence_map)]
    rc = plan_reader.main(argv)
    doc = json.loads(out.read_text()) if out.exists() else None
    return rc, doc


def by_id(doc):
    return {build["id"]: build for build in doc["builds"]}


class PlanReaderTests(unittest.TestCase):
    def test_partial_builds_block_exactly_the_missing_sequences(self):
        rc, doc = run_reader([PRE, MAIN, DOORS])
        self.assertEqual(rc, 0)
        builds = by_id(doc)
        self.assertEqual(sorted(builds), ["auto_abandoned_checkout", "auto_post_sale", "auto_pre_launch"])
        self.assertEqual(builds["auto_pre_launch"]["state"], "ready")
        self.assertEqual(builds["auto_pre_launch"]["email_sequences"],
                         ["email_pre_launch", "email_main_launch", "email_doors_closing"])
        self.assertEqual(len(builds["auto_pre_launch"]["workflows"]), 3)
        self.assertEqual(builds["auto_post_sale"]["state"], "blocked")
        self.assertEqual(builds["auto_post_sale"]["blocked_by"], ["email_welcome_access"])
        self.assertEqual(builds["auto_abandoned_checkout"]["blocked_by"], ["email_abandoned_checkout"])
        for build in builds.values():
            self.assertTrue(build["draft_only"])
            for workflow in build["workflows"]:
                self.assertEqual(workflow["status"], "draft")
        codes = {warning["code"] for warning in doc["warnings"]}
        self.assertIn("EMAIL-COUNT-MISMATCH", codes)

    def test_complete_builds_are_all_ready(self):
        rc, doc = run_reader([PRE, MAIN, DOORS, ABANDONED, WELCOME])
        self.assertEqual(rc, 0)
        builds = by_id(doc)
        self.assertEqual({b["state"] for b in builds.values()}, {"ready"})
        self.assertEqual(doc["unused_build_plan_workflows"], [])
        self.assertEqual(doc["launch_id"], "elevation-2026-11")
        self.assertTrue(doc["draft_only"])

    def test_steps_pass_through_verbatim(self):
        rc, doc = run_reader([PRE])
        self.assertEqual(rc, 0)
        workflow = by_id(doc)["auto_pre_launch"]["workflows"][0]
        source = json.loads(PRE.read_text())["sequence-email-pre-launch"]["templates"]
        self.assertEqual(workflow["steps"], source)
        self.assertEqual((workflow["email_count"], workflow["wait_count"]), (2, 1))

    def test_unbound_build_plan_is_reported_not_dropped(self):
        temp = Path(tempfile.mkdtemp())
        detached = temp / "workflow.json"
        doc = json.loads(PRE.read_text())
        doc.pop("_meta")
        detached.write_text(json.dumps(doc))
        rc, result = run_reader([detached])
        self.assertEqual(rc, 0)
        self.assertEqual(len(result["unused_build_plan_workflows"]), 1)
        self.assertEqual(result["unused_build_plan_workflows"][0]["build_plan"], str(detached))

        mapping = temp / "map.json"
        mapping.write_text(json.dumps({"email_pre_launch": str(detached)}))
        rc, result = run_reader([detached], sequence_map=mapping)
        self.assertEqual(rc, 0)
        self.assertEqual(result["unused_build_plan_workflows"], [])
        self.assertEqual(by_id(result)["auto_pre_launch"]["state"], "blocked")
        self.assertEqual(by_id(result)["auto_pre_launch"]["workflows"][0]["key"],
                         "sequence-email-pre-launch")

    def test_published_workflow_is_refused(self):
        temp = Path(tempfile.mkdtemp())
        doc = json.loads(PRE.read_text())
        doc["sequence-email-pre-launch"]["status"] = "published"
        published = temp / "published.json"
        published.write_text(json.dumps(doc))
        rc, result = run_reader([published])
        self.assertEqual(rc, 2)
        self.assertIsNone(result)

    def test_credential_shaped_key_is_refused(self):
        temp = Path(tempfile.mkdtemp())
        doc = json.loads(PRE.read_text())
        doc["_meta"]["api_key"] = "redacted"
        dirty = temp / "dirty.json"
        dirty.write_text(json.dumps(doc))
        rc, result = run_reader([dirty])
        self.assertEqual(rc, 2)
        self.assertIsNone(result)

    def test_cycle_is_refused(self):
        temp = Path(tempfile.mkdtemp())
        plan = json.loads(PLAN_FIXTURE.read_text())
        plan["automations"][0]["waits_for"] = ["auto_post_sale"]
        plan["automations"][1]["waits_for"] = ["auto_pre_launch"]
        cyclic = temp / "cyclic.json"
        cyclic.write_text(json.dumps(plan))
        rc, result = run_reader([PRE], plan_path=cyclic)
        self.assertEqual(rc, 2)
        self.assertIsNone(result)

    def test_selftest(self):
        self.assertEqual(plan_reader.main(["--selftest"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
