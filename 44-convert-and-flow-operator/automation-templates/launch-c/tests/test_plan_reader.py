"""launch-c plan reader checks. Run: python3 launch-c/tests/test_plan_reader.py"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAUNCH_C = HERE.parent
REPO = LAUNCH_C.parent.parent.parent
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


# Buildable template per family (Skill 49 TEMPLATE_BY_FAMILY; keys of _matcher/buildable-templates.json).
FAMILY_TEMPLATE = {
    "pre_launch": "launch-a/launch-a-prelaunch-window",
    "post_sale": "launch-b/launch-post-sale-purchase",
    "abandoned_checkout": "launch-b/abandoned-checkout-recovery",
}


def buildable_plan(source=PLAN_FIXTURE):
    """A temp copy of the contract fixture whose automation templates are manifest keys
    (its own ids predate the buildable manifest; the reader refuses those)."""
    plan = json.loads(Path(source).read_text())
    for item in plan["automations"]:
        item["template"] = FAMILY_TEMPLATE[item["family"]]
    path = Path(tempfile.mkdtemp()) / "plan.json"
    path.write_text(json.dumps(plan))
    return path


BUILDABLE_PLAN = buildable_plan()

# Fixed clock before every fixture date (doors_close_at is 2026-11-10): the reader's
# default is wall-clock now, which silently suppresses every send once the fixture passes.
FIXED_NOW = "2026-11-01T00:00:00-05:00"


def run_reader(build_plans, plan_path=BUILDABLE_PLAN, sequence_map=None):
    out = Path(tempfile.mkdtemp()) / "automation-builds.json"
    argv = ["--launch-plan", str(plan_path), "--out", str(out), "--now", FIXED_NOW]
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
        self.assertEqual(rc, 4)   # blocked builds exit 4 (output is still written)
        builds = by_id(doc)
        self.assertEqual(sorted(builds), ["auto_abandoned_checkout", "auto_post_sale", "auto_pre_launch"])
        # L07: an email-count mismatch is a REQUIRED-OUTPUT failure, so a build
        # whose bound plans do not match the launch plan's counts is blocked.
        self.assertEqual(builds["auto_pre_launch"]["state"], "blocked")
        self.assertIn("email_count:email_pre_launch",
                      builds["auto_pre_launch"]["blocked_by"])
        self.assertEqual(builds["auto_pre_launch"]["email_sequences"],
                         ["email_pre_launch", "email_main_launch", "email_doors_closing"])
        self.assertEqual(len(builds["auto_pre_launch"]["workflows"]), 3)
        self.assertEqual(builds["auto_post_sale"]["state"], "blocked")
        self.assertIn("email_welcome_access", builds["auto_post_sale"]["blocked_by"])
        self.assertIn("email_abandoned_checkout",
                      builds["auto_abandoned_checkout"]["blocked_by"])
        for build in builds.values():
            self.assertTrue(build["draft_only"])
            for workflow in build["workflows"]:
                self.assertEqual(workflow["status"], "draft")
        codes = {warning["code"] for warning in doc["warnings"]}
        self.assertIn("EMAIL-COUNT-MISMATCH", codes)

    def test_complete_builds_block_on_count_mismatch(self):
        rc, doc = run_reader([PRE, MAIN, DOORS, ABANDONED, WELCOME])
        self.assertEqual(rc, 4)
        builds = by_id(doc)
        self.assertEqual({b["state"] for b in builds.values()}, {"blocked"})
        self.assertEqual(doc["unused_build_plan_workflows"], [])
        self.assertEqual(doc["launch_id"], "elevation-2026-11")
        for build in builds.values():
            self.assertTrue(all(reason.startswith("email_count:")
                                for reason in build["blocked_by"]), build["blocked_by"])

    def test_complete_and_count_matching_builds_are_ready(self):
        plan = json.loads(BUILDABLE_PLAN.read_text())
        counts = {seq["id"]: seq["email_count"] for seq in plan["email_sequences"]}
        temp = Path(tempfile.mkdtemp())
        paths = []
        for seq_id, count in counts.items():
            templates = [
                {"id": "e%d" % index, "type": "email", "name": "Email %d" % index,
                 "attributes": {"subject": "s%d" % index, "body": "<p>b</p>",
                                "html": "<p>b</p>", "fromName": "n"}}
                for index in range(count)
            ]
            doc = {"folder": "F", "_meta": {
                       "sequence_id": seq_id,
                       "enrollment_conditions": plan_reader.DEFAULT_ENROLLMENT_CONDITIONS,
                       "lifecycle": plan_reader.DEFAULT_LIFECYCLE,
                       "sender_config_refs": plan_reader.DEFAULT_SENDER},
                   seq_id: {"name": seq_id, "status": "draft", "templates": templates}}
            path = temp / ("%s.json" % seq_id)
            path.write_text(json.dumps(doc))
            paths.append(path)
        rc, result = run_reader(paths)
        self.assertEqual(rc, 0)
        self.assertEqual({b["state"] for b in by_id(result).values()}, {"ready"})
        self.assertTrue(result["journal"]["stable_unit_keys"])

    def test_steps_pass_through_verbatim(self):
        rc, doc = run_reader([PRE])
        self.assertEqual(rc, 4)
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
        self.assertEqual(rc, 4)
        self.assertEqual(len(result["unused_build_plan_workflows"]), 1)
        self.assertEqual(result["unused_build_plan_workflows"][0]["build_plan"], str(detached))

        mapping = temp / "map.json"
        mapping.write_text(json.dumps({"email_pre_launch": str(detached)}))
        rc, result = run_reader([detached], sequence_map=mapping)
        self.assertEqual(rc, 4)
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
        plan = json.loads(BUILDABLE_PLAN.read_text())
        plan["automations"][0]["waits_for"] = ["auto_post_sale"]
        plan["automations"][1]["waits_for"] = ["auto_pre_launch"]
        cyclic = temp / "cyclic.json"
        cyclic.write_text(json.dumps(plan))
        rc, result = run_reader([PRE], plan_path=cyclic)
        self.assertEqual(rc, 2)
        self.assertIsNone(result)

    def test_text_set_without_approved_copy_blocks_the_build_that_elected_it(self):
        # Issue 3: the reader never builds an electing automation without Skill 50's SMS copy.
        # (Full text-set coverage: test_plan_reader_text_sets.py.)
        plan = json.loads(BUILDABLE_PLAN.read_text())
        plan["text_sets"] = [{
            "id": "text_abandoned_checkout", "kind": "abandoned_checkout", "messages": 2,
            "promotional": True, "draft_only": True, "opt_out_keyword": "STOP",
            "includes_reply_invitation": True,
            "send_window": {"start": "08:00", "end": "21:00", "timezone": "recipient_local"},
            "waits_for": ["page_checkout"]}]
        electing = next(a for a in plan["automations"] if a["id"] == "auto_abandoned_checkout")
        electing["waits_for"].append("text_abandoned_checkout")
        path = Path(tempfile.mkdtemp()) / "plan.json"
        path.write_text(json.dumps(plan))
        rc, doc = run_reader([ABANDONED, WELCOME], plan_path=path)
        build = next(b for b in doc["builds"] if b["id"] == "auto_abandoned_checkout")
        self.assertEqual(build["state"], "blocked")
        self.assertIn("text_set:text_abandoned_checkout copy", build["blocked_by"])
        self.assertEqual(rc, 4)

    def test_selftest(self):
        self.assertEqual(plan_reader.main(["--selftest"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
