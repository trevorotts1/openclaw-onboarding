"""S44-05 stage-14 receipt-shape proofs.

Every assertion cites the field list in
71-blackceo-signature-page/references/artifact-contracts.md:656-667 and
automation-handoff.md:186-213. These tests fail on the pre-fix code:
the receiver emitted no `outcome`, no `form_exceptions`, no mechanism
alongside the trigger, no qc.checklist_complete / qc.wf_items, and
stage14_outcome did not exist.
"""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "store"))
from receiver import (EXIT_GATE, EXIT_OK, Receiver, plan_hash,
                      stage14_outcome)
from store import Store

HANDOFF = "5ea1502da48cf5c46317c865cfa06ef4f772cede6bba2026852a28809afb2325"

class FakeExecutor:
    """Healthy recording executor; the same surface the receiver tests use."""

    def probe(self):
        return {"token_state": "healthy", "access_tier_used": "tier0"}

    def dependencies_present(self, location_id, workflow):
        return []

    def snapshot(self, location_id, slug):
        return True

    def build(self, builder_plan):
        slug = next(k for k in builder_plan if k != "folder")
        return {
            "exit_code": 0, "workflow_id": "wf-" + slug, "errors": [],
            "notes": [],
            "export": {
                "id": "wf-" + slug, "status": "draft",
                "triggers": [{"id": "t1", "type": "contact_tag",
                              "tag": "sl-optin"}],
                "steps": [{"id": "s1"}, {"id": "s2"}],
                "allowMultiple": True,
            },
            "qc_exit_code": 0, "rubric": 9.1,
        }

def seam_request():
    plan = {
        "_meta": {"deploy_mode": "draft-only"},
        "folder": "FIXTURE / R71H Dry-Run",
        "optin": {"name": "Opt-In Follow-Up", "tag": "sl-optin"},
    }
    return {
        "request_id": "gxo_0123456789ab", "request_version": 2,
        "location_id": "LOC1", "launch_id": "LN1",
        "requesting_room": "S50", "deploy_mode": "draft-only",
        "approval": {"ref": "fixture-plan-approval-001",
                     "plan_hash": plan_hash(plan)},
        "handoff_sha256": HANDOFF,
        "plan": plan,
        "workflows": [
            {"slug": "optin", "expected_steps": 2, "allow_multiple": True,
             "origin": {"type": "form_submitted", "form_id": "FORM-1"},
             "mechanism": {"type": "contact_tag", "tag": "sl-optin"}},
            {"form_id": "FORM-3",
             "no_workflow_reason": "booking reminders owned by the calendar"},
        ],
    }

class Stage14OutcomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / "s44.db"))
        self.rx = Receiver(self.store, FakeExecutor(),
                           configured_location="LOC1")

    def tearDown(self):
        self.tmp.cleanup()

    def test_raw_receipt_carries_contract_fields(self):
        code, receipt = self.rx.dispatch(seam_request())
        self.assertEqual(code, EXIT_OK)
        # artifact-contracts.md:663-667
        self.assertEqual(receipt["outcome"], "accepted")
        self.assertEqual(receipt["request_id"], "gxo_0123456789ab")
        self.assertEqual(receipt["request_version"], 2)
        self.assertEqual(receipt["handoff_sha256"], HANDOFF)
        self.assertEqual(receipt["form_exceptions"][0]["form_id"], "FORM-3")
        # Not knowable receiver-side: explicitly absent, never "" or [].
        for key in ("conversational", "conversational_overrides",
                    "conversational_not_present", "ghl_pack_version"):
            self.assertIsNone(receipt[key], key)
        op = receipt["operations"][0]
        self.assertEqual(op["mechanism"], {"type": "contact_tag",
                                           "tag": "sl-optin"})
        # automation-handoff.md:196-204
        for key in ("checklist_instance", "checklist_complete", "wf_items"):
            self.assertIn(key, op["qc"])
            self.assertIsNone(op["qc"][key], key)

    def test_outcome_record_matches_contract_field_list(self):
        code, receipt = self.rx.dispatch(seam_request())
        outcome = stage14_outcome(seam_request(), code, receipt)
        # artifact-contracts.md:656-667 top-level field list
        for key in ("outcome", "request_id", "request_version",
                    "handoff_sha256", "workflows", "form_exceptions",
                    "conversational", "conversational_overrides",
                    "conversational_not_present", "ghl_pack_version"):
            self.assertIn(key, outcome, key)
        self.assertEqual(outcome["outcome"], "accepted")
        self.assertEqual(outcome["request_id"], "gxo_0123456789ab")
        self.assertEqual(outcome["request_version"], 2)
        self.assertEqual(outcome["handoff_sha256"], HANDOFF)
        wf = outcome["workflows"][0]
        # automation-handoff.md:186-204 per-workflow field list
        for key in ("workflow_id", "name", "trigger", "mechanism",
                    "build_method", "qc", "readback"):
            self.assertIn(key, wf, key)
        # flat trigger with the mechanism alongside, never nested
        self.assertEqual(wf["trigger"], {"type": "form_submitted",
                                         "form_id": "FORM-1"})
        self.assertEqual(wf["mechanism"], {"type": "contact_tag",
                                           "tag": "sl-optin"})
        self.assertEqual(wf["build_method"], "caf-cli")
        for key in ("script", "exit_code", "checklist_instance",
                    "checklist_complete", "wf_items"):
            self.assertIn(key, wf["qc"], key)
        self.assertEqual(wf["qc"]["script"], "qc-built-workflow.sh")
        self.assertEqual(wf["readback"], {"exists": True, "status": "draft"})
        # exceptions are top-level, not operations
        self.assertEqual(outcome["form_exceptions"],
                         [{"form_id": "FORM-3",
                           "no_workflow_reason":
                               "booking reminders owned by the calendar"}])
        self.assertEqual(len(outcome["workflows"]), 1)

    def test_unknowns_are_none_named_not_invented(self):
        code, receipt = self.rx.dispatch(seam_request())
        outcome = stage14_outcome(seam_request(), code, receipt)
        qc = outcome["workflows"][0]["qc"]
        self.assertIsNone(qc["checklist_instance"])
        self.assertIsNone(qc["checklist_complete"])
        self.assertIsNone(qc["wf_items"])
        self.assertIsNone(outcome["ghl_pack_version"])
        self.assertIsNone(outcome["conversational"])
        self.assertIsNot(outcome["conversational"], [])
        names = " ".join(outcome["unproducible"])
        for field in ("ghl_pack_version", "checklist_instance",
                      "checklist_complete", "wf_items"):
            self.assertIn(field, names)
        # No empty-string stand-ins anywhere in the record.
        self.assertNotIn('""', repr(outcome))

    def test_refusal_is_a_receipt_with_binding(self):
        req = seam_request()
        req["location_id"] = "OTHER"
        code, result = self.rx.dispatch(req)
        self.assertEqual(code, EXIT_GATE)
        # packet section 4 / artifact-contracts.md:664-666
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(result["request_id"], "gxo_0123456789ab")
        self.assertEqual(result["request_version"], 2)
        self.assertEqual(result["handoff_sha256"], HANDOFF)
        outcome = stage14_outcome(req, code, result)
        self.assertEqual(outcome["outcome"], "refused")
        self.assertEqual(outcome["refusal"]["code"], "WRONG_LOCATION")
        self.assertIn("configured location", outcome["refusal"]["reason"])
        self.assertIsNone(outcome["workflows"])

if __name__ == "__main__":
    unittest.main()
