"""Lane F regression tests: one or more per gap lane C proved
(GAP-1..GAP-5), run against the packaged receiver 0.2 build with
lane C's fixtures (vendored under tools/siglaunch/fixtures/).
Recording-fake executors only; nothing live; fixtures are never
live proof.
"""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "store"))
from receiver import (EXIT_BLOCKED, EXIT_OK, EXIT_VALIDATION, Receiver,
                      judge_receipt, plan_hash)
from store import Store

# Packaged layout: the fixture pair is vendored at
# tools/siglaunch/fixtures/ (in the room layout the same tests
# resolve rooms/S44/fixtures/ via parent.parent.parent).
FIXTURES = Path(__file__).parent.parent / "fixtures"
FAKE_LOCATION = "loc-fixture-0001"


class RecordingFake:
    def __init__(self):
        self.build_calls = []

    def probe(self):
        return {"token_state": "healthy", "access_tier_used": "tier0"}

    def dependencies_present(self, location_id, workflow):
        return []

    def snapshot(self, location_id, slug):
        return True

    def build(self, builder_plan):
        self.build_calls.append(copy.deepcopy(builder_plan))
        slug = next(k for k in builder_plan if k != "folder")
        return {
            "exit_code": 0, "workflow_id": "wf-" + slug, "errors": [],
            "notes": [],
            "export": {
                "id": "wf-" + slug, "status": "draft",
                "triggers": [{"id": "t1", "type": "contact_tag"}],
                "steps": [{"id": "s1"}, {"id": "s2"}],
                "allowMultiple": True,
            },
            "qc_exit_code": 0, "rubric": 9.1,
        }


class EchoFake(RecordingFake):
    """Echoes the declared contract back as the export (lane C's
    EchoFake): trigger type = mechanism type, steps = expected_steps,
    allowMultiple = allow_multiple."""

    def __init__(self, declared):
        super().__init__()
        self.declared = {w.get("slug"): w for w in declared}

    def build(self, builder_plan):
        self.build_calls.append(copy.deepcopy(builder_plan))
        slug = next(k for k in builder_plan if k != "folder")
        decl = self.declared[slug]
        mech = decl.get("mechanism", {})
        return {
            "exit_code": 0, "workflow_id": "wf-" + slug, "errors": [],
            "notes": [],
            "export": {
                "id": "wf-" + slug, "status": "draft",
                "triggers": [{"id": "t1", "type": mech.get(
                    "type", "contact_tag")}],
                "steps": [{"id": f"s{i}"}
                          for i in range(decl.get("expected_steps", 0))],
                "allowMultiple": decl.get("allow_multiple", False),
            },
            "qc_exit_code": 0, "rubric": 9.1,
        }


# ── lane C fixture construction (same shapes as lane-c/dryrun.py) ────
HANDOFF_BYTES = (FIXTURES / "automation-handoff.json").read_bytes()
HANDOFF = json.loads(HANDOFF_BYTES)
HANDOFF_SHA256 = hashlib.sha256(HANDOFF_BYTES).hexdigest()
FORMS = {f["role"]: f["form_id"] for f in HANDOFF["forms"]}

R71H_PLAN = {
    "folder": "Signature Launch Fixture",
    "optin-nurture": {"name": "Fixture Opt-In Nurture",
                      "tag": "siglaunch-fixture-optin"},
    "purchase-fulfillment": {"name": "Fixture Purchase Fulfillment",
                             "tag": "siglaunch-fixture-verified-purchase"},
}
R71H_WORKFLOWS = [
    {"slug": "optin-nurture", "expected_steps": 2, "allow_multiple": True,
     "origin": {"type": "form_submitted", "form_id": FORMS["opt_in"]},
     "mechanism": {"type": "contact_tag",
                   "tag": "siglaunch-fixture-optin"}},
    {"slug": "purchase-fulfillment", "expected_steps": 2,
     "allow_multiple": True,
     "origin": {"type": "form_submitted", "form_id": FORMS["order_form"]},
     "mechanism": {"type": "contact_tag",
                   "tag": "siglaunch-fixture-verified-purchase"}},
    {"form_id": FORMS["booking"],
     "no_workflow_reason": "booking step is covered by the Skill 38 "
                           "conversational playbook in this fixture; "
                           "no workflow is built for it"},
]

S50_PLAN = json.loads((FIXTURES / "s50-email-plan.json").read_text())["plan"]


def r71h_request(include_sha=True, include_except=True, workflows=None):
    req = {
        "request_id": "gxo_1a2b3c4d5e6f", "request_version": 1,
        "location_id": HANDOFF["location_id"],
        "launch_id": HANDOFF["launch_id"],
        "requesting_room": "S71", "deploy_mode": "draft-only",
        "approval": {"ref": "lane-f-fixture",
                     "plan_hash": plan_hash(R71H_PLAN)},
        "plan": copy.deepcopy(R71H_PLAN),
        "workflows": copy.deepcopy(
            workflows if workflows is not None
            else (R71H_WORKFLOWS if include_except else R71H_WORKFLOWS[:2])),
    }
    if include_sha:
        req["handoff_sha256"] = HANDOFF_SHA256
    return req


def s50_request(plan):
    return {
        "request_id": "gxo_5a50f17e57ed", "request_version": 1,
        "location_id": FAKE_LOCATION, "launch_id": "launch-fixture-0001",
        "requesting_room": "S50", "deploy_mode": "draft-only",
        "approval": {"ref": "lane-f-fixture",
                     "plan_hash": plan_hash(plan)},
        "plan": plan,
        "workflows": [
            {"slug": "welcome", "expected_steps": 2,
             "allow_multiple": True,
             "trigger": {"type": "contact_tag",
                         "tag": "email-engine:fixture-welcome"}},
            {"slug": "nurture", "expected_steps": 2,
             "allow_multiple": True,
             "trigger": {"type": "contact_tag",
                         "tag": "email-engine:fixture-nurture"}},
        ],
    }


class LaneFBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / "s44.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def receiver(self, fake):
        return Receiver(self.store, fake,
                        configured_location=FAKE_LOCATION)


class Gap1Tests(LaneFBase):
    def test_r1_packet_envelope_accepted_and_hash_echoed(self):
        fake = RecordingFake()
        code, receipt = self.receiver(fake).dispatch(r71h_request())
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(receipt["handoff_sha256"], HANDOFF_SHA256)
        self.assertEqual(receipt["status_claimed"], "verified")
        self.assertEqual(len(fake.build_calls), 2)
        self.assertEqual(judge_receipt(receipt)["overall"], "VERIFIED")

    def test_malformed_handoff_hash_refused(self):
        fake = RecordingFake()
        req = r71h_request()
        req["handoff_sha256"] = "not-a-sha"
        code, refusal = self.receiver(fake).dispatch(req)
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertEqual(refusal["refused"], "HANDOFF_HASH_INVALID")
        self.assertEqual(fake.build_calls, [])
        self.assertIsNone(self.store.get_request("gxo_1a2b3c4d5e6f"))


class Gap2Tests(LaneFBase):
    def test_r2_exception_entry_recorded_not_crash(self):
        fake = RecordingFake()
        code, receipt = self.receiver(fake).dispatch(
            r71h_request(include_sha=False))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(receipt["status_claimed"], "verified")
        ops = {op["slug"]: op for op in receipt["operations"]}
        exc = ops[FORMS["booking"]]
        self.assertEqual(exc["status_claimed"], "skipped")
        self.assertIn("Skill 38", exc["no_workflow_reason"])
        self.assertIsNone(exc["workflow_id"])
        verdicts = judge_receipt(receipt)
        self.assertEqual(verdicts["operations"][FORMS["booking"]],
                         "SKIPPED")
        self.assertEqual(verdicts["overall"], "VERIFIED")
        # the receipt (with the recorded exception) is durable
        stored = self.store.get_request("gxo_1a2b3c4d5e6f")
        self.assertIsNotNone(stored["receipt"])

    def test_entry_with_neither_slug_nor_reason_refused_not_crash(self):
        fake = RecordingFake()
        workflows = R71H_WORKFLOWS[:2] + [{"form_id": FORMS["booking"]}]
        code, refusal = self.receiver(fake).dispatch(
            r71h_request(workflows=workflows))
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertEqual(refusal["refused"], "PLAN_INVALID")
        self.assertIn("neither 'slug' nor 'no_workflow_reason'",
                      refusal["detail"])
        self.assertEqual(fake.build_calls, [])

    def test_non_string_reason_refused_not_crash(self):
        fake = RecordingFake()
        workflows = R71H_WORKFLOWS[:2] + [
            {"form_id": FORMS["booking"], "no_workflow_reason": 42}]
        code, refusal = self.receiver(fake).dispatch(
            r71h_request(workflows=workflows))
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertEqual(refusal["refused"], "PLAN_INVALID")
        self.assertEqual(fake.build_calls, [])


class Gap3Tests(LaneFBase):
    def test_r3_echo_executor_verifies_with_exit_ok(self):
        req = r71h_request(include_sha=False, include_except=False)
        fake = EchoFake(req["workflows"])
        code, receipt = self.receiver(fake).dispatch(req)
        self.assertEqual(code, EXIT_OK)  # was EXIT_BLOCKED (5) pre-fix
        self.assertNotEqual(code, EXIT_BLOCKED)
        self.assertEqual(receipt["status_claimed"], "verified")
        self.assertEqual(judge_receipt(receipt)["overall"], "VERIFIED")
        for op in receipt["operations"]:
            checks = {c["name"]: c["ok"] for c in op["expect"]}
            self.assertTrue(checks["trigger_bound"], op["slug"])
            # origin + mechanism echoed side by side, verbatim
            self.assertEqual(op["trigger"]["origin"]["type"],
                             "form_submitted")
            self.assertEqual(op["trigger"]["mechanism"]["type"],
                             "contact_tag")

    def test_origin_wrong_type_refused_before_build(self):
        workflows = copy.deepcopy(R71H_WORKFLOWS[:2])
        workflows[0]["origin"] = {"type": "form_viewed",
                                  "form_id": FORMS["opt_in"]}
        fake = RecordingFake()
        code, refusal = self.receiver(fake).dispatch(
            r71h_request(workflows=workflows))
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertEqual(refusal["refused"], "PLAN_INVALID")
        self.assertEqual(fake.build_calls, [])

    def test_origin_missing_form_id_refused(self):
        workflows = copy.deepcopy(R71H_WORKFLOWS[:2])
        workflows[0]["origin"] = {"type": "form_submitted"}
        fake = RecordingFake()
        code, refusal = self.receiver(fake).dispatch(
            r71h_request(workflows=workflows))
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertEqual(refusal["refused"], "PLAN_INVALID")
        self.assertEqual(fake.build_calls, [])

    def test_contact_tag_mechanism_without_tag_refused(self):
        workflows = copy.deepcopy(R71H_WORKFLOWS[:2])
        workflows[0]["mechanism"] = {"type": "contact_tag"}
        fake = RecordingFake()
        code, refusal = self.receiver(fake).dispatch(
            r71h_request(workflows=workflows))
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertEqual(refusal["refused"], "PLAN_INVALID")
        self.assertEqual(fake.build_calls, [])

    def test_native_mechanism_requires_tier4_method(self):
        workflows = copy.deepcopy(R71H_WORKFLOWS[:2])
        workflows[0]["mechanism"] = {"type": "native"}
        fake = RecordingFake()
        code, refusal = self.receiver(fake).dispatch(
            r71h_request(workflows=workflows))
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertEqual(refusal["refused"], "PLAN_INVALID")

    def test_native_mechanism_builds_and_records_tier4(self):
        workflows = [{
            "slug": "optin-nurture", "expected_steps": 2,
            "allow_multiple": True,
            "origin": {"type": "form_submitted",
                       "form_id": FORMS["opt_in"]},
            "mechanism": {"type": "native",
                          "build_method": "tier4-browser-backstop"},
        }]
        plan = {"folder": "Signature Launch Fixture",
                "optin-nurture": R71H_PLAN["optin-nurture"]}

        class NativeFake(RecordingFake):
            def build(self, builder_plan):
                self.build_calls.append(copy.deepcopy(builder_plan))
                return {
                    "exit_code": 0, "workflow_id": "wf-native",
                    "errors": [], "notes": [],
                    "export": {
                        "id": "wf-native", "status": "draft",
                        "triggers": [{"id": "t1",
                                      "type": "form_submitted"}],
                        "steps": [{"id": "s1"}, {"id": "s2"}],
                        "allowMultiple": True},
                    "qc_exit_code": 0, "rubric": 9.0}

        req = r71h_request(include_sha=False, workflows=workflows)
        req["plan"] = plan
        req["approval"]["plan_hash"] = plan_hash(plan)
        fake = NativeFake()
        code, receipt = self.receiver(fake).dispatch(req)
        self.assertEqual(code, EXIT_OK)
        op = receipt["operations"][0]
        self.assertEqual(op["status_claimed"], "created")
        self.assertEqual(op["build_method"], "tier4-browser-backstop")
        checks = {c["name"]: c["ok"] for c in op["expect"]}
        self.assertTrue(checks["trigger_bound"])

    def test_verbatim_tag_drift_fails_trigger_bound(self):
        class DriftFake(RecordingFake):
            def build(self, builder_plan):
                self.build_calls.append(copy.deepcopy(builder_plan))
                slug = next(k for k in builder_plan if k != "folder")
                return {
                    "exit_code": 0, "workflow_id": "wf-" + slug,
                    "errors": [], "notes": [],
                    "export": {
                        "id": "wf-" + slug, "status": "draft",
                        "triggers": [{"id": "t1", "type": "contact_tag",
                                      "tag": "Siglaunch-Fixture-Optin"}],
                        "steps": [{"id": "s1"}, {"id": "s2"}],
                        "allowMultiple": True},
                    "qc_exit_code": 0, "rubric": 9.1}

        req = r71h_request(include_sha=False, include_except=False)
        fake = DriftFake()
        code, receipt = self.receiver(fake).dispatch(req)
        self.assertEqual(code, EXIT_VALIDATION)  # judge failure, not 5
        op = receipt["operations"][0]
        checks = {c["name"]: c["ok"] for c in op["expect"]}
        self.assertFalse(checks["trigger_bound"])


class Gap4Tests(LaneFBase):
    def test_stage14_fields_on_s50_receipt(self):
        fake = RecordingFake()
        code, receipt = self.receiver(fake).dispatch(
            s50_request(copy.deepcopy(S50_PLAN)))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(receipt["deploy_mode"], "draft-only")
        self.assertEqual(receipt["approval"]["ref"], "lane-f-fixture")
        self.assertEqual(receipt["approval"]["plan_hash"],
                         plan_hash(S50_PLAN))
        self.assertIn("handoff_sha256", receipt)
        self.assertIsNone(receipt["handoff_sha256"])
        for op in receipt["operations"]:
            self.assertTrue(op["name"].startswith("Fixture "))
            self.assertEqual(op["folder"], "Signature Launch Fixture")
            self.assertEqual(op["build_method"], "caf-cli")
            self.assertEqual(op["trigger"]["type"], "contact_tag")
            self.assertEqual(op["qc"]["script"], "qc-built-workflow.sh")
            self.assertEqual(op["qc"]["exit_code"], 0)
            self.assertEqual(op["qc"]["rubric"], 9.1)
            self.assertIn("checklist_instance", op["qc"])
            self.assertEqual(op["readback_summary"],
                             {"exists": True, "status": "draft"})

    def test_seam_receipt_names_unproducible_fields_in_notes(self):
        fake = RecordingFake()
        code, receipt = self.receiver(fake).dispatch(r71h_request())
        self.assertEqual(code, EXIT_OK)
        joined = " ".join(receipt["notes"])
        self.assertIn("conversational", joined)
        self.assertIn("ghl_pack_version", joined)
        self.assertIn("checklist_instance", joined)

    def test_failed_checks_exit_validation_not_blocked(self):
        class WrongStepsFake(RecordingFake):
            def build(self, builder_plan):
                out = super().build(builder_plan)
                out["export"]["steps"] = [{"id": "s1"}]  # 1 != expected 2
                return out

        fake = WrongStepsFake()
        code, receipt = self.receiver(fake).dispatch(
            s50_request(copy.deepcopy(S50_PLAN)))
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertNotEqual(code, EXIT_BLOCKED)
        self.assertNotEqual(receipt["status_claimed"], "verified")


class Gap5Tests(LaneFBase):
    def test_s3_versioned_meta_without_hashes_refused(self):
        plan = copy.deepcopy(S50_PLAN)
        del plan["_meta"]["content_hashes"]
        fake = RecordingFake()
        code, refusal = self.receiver(fake).dispatch(s50_request(plan))
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertEqual(refusal["refused"], "PLAN_INVALID")
        self.assertIn("content_hashes", refusal["detail"])
        self.assertEqual(fake.build_calls, [])
        self.assertIsNone(self.store.get_request("gxo_5a50f17e57ed"))

    def test_versioned_meta_with_hashes_dispatches(self):
        fake = RecordingFake()
        code, receipt = self.receiver(fake).dispatch(
            s50_request(copy.deepcopy(S50_PLAN)))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(judge_receipt(receipt)["overall"], "VERIFIED")

    def test_unversioned_meta_without_hashes_still_dispatches(self):
        # The scoping that keeps the pre-existing suites valid: a
        # minimal hand-written _meta (deploy_mode only, no
        # plan_version) is not an emitted plan and is not held to the
        # emitted-plan hash rule. See lane F REPORT.md GAP-5.
        plan = {"_meta": {"deploy_mode": "draft-only", "emitter": "s50"},
                "folder": "Signature Launch",
                "welcome": {"name": "Welcome",
                            "tag": "email-engine:fixture-welcome"},
                "nurture": {"name": "Nurture",
                            "tag": "email-engine:fixture-nurture"}}
        fake = RecordingFake()
        code, receipt = self.receiver(fake).dispatch(s50_request(plan))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(receipt["status_claimed"], "verified")

    def test_content_hashes_wrong_type_refused(self):
        plan = copy.deepcopy(S50_PLAN)
        plan["_meta"]["content_hashes"] = "not-an-object"
        fake = RecordingFake()
        code, refusal = self.receiver(fake).dispatch(s50_request(plan))
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertEqual(refusal["refused"], "PLAN_INVALID")
        self.assertEqual(fake.build_calls, [])


if __name__ == "__main__":
    unittest.main()
