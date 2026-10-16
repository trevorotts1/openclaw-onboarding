"""MG-046: delivery receipt schema contract tests.

The delivery receipt is the status layer's own document
(references/delivery-receipt-schema.json, Draft 2020-12). These
tests pin the receipt's structural guarantees from the Python
side: a conformant receipt validates; a receipt whose production
status is a release word, whose approvals include a code-review
approval, whose missing_mandatory is non-empty, or whose artifact
carries no measured hash does not. The runtime's own validator
(runtime/src/status/receipt.ts) is exercised by run-status.ts;
this suite guards the shared schema file both sides read.
"""

import copy
import json
import os
import unittest

from jsonschema import Draft202012Validator

SKILL = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCHEMA_PATH = os.path.join(SKILL, "references", "delivery-receipt-schema.json")

SHA = "a" * 64


def valid_receipt():
    return {
        "schema_version": "1.0",
        "item": "MG-046",
        "job_id": "job-receipt-1",
        "company_id": "company-1",
        "task": {
            "task_id": "job-receipt-1",
            "origin": "own",
            "parent_job_id": None,
            "parent_task_id": None,
        },
        "mode": "powerpoint_graphic",
        "execution_context": "production",
        "diagnostic": False,
        "production_status": "DELIVERED",
        "release_status": None,
        "engine": "remotion",
        "export": {
            "profile": "h264_opaque",
            "route_kind": "engine_native",
            "confirmed_by": "baseline_contract",
        },
        "artifacts": [
            {"kind": "mp4", "path": "renders/final.mp4", "sha256": SHA, "bytes": 12345},
            {"kind": "poster", "path": "renders/poster.png", "sha256": SHA, "bytes": 678},
        ],
        "approvals": [
            {
                "kind": "production_approval",
                "gate": "delivery",
                "scope": "delivery",
                "approvalId": "appr-delivery-1",
                "decision": "approved",
                "subjectRevision": "rev-1",
                "authorityBasis": "policy=owner_or_existing_authorized_reviewer; actor=owner-1 (registry:owner)",
                "at": "2026-10-15T00:00:00.000Z",
            }
        ],
        "qc": {
            "verdict": "pass",
            "artifact_path": "renders/final.mp4",
            "artifact_sha256": SHA,
            "source": "test",
        },
        "recovery": {"cache_work_dir": None, "cache_job_key": None},
        "board": {"job_id": "job-receipt-1", "stage_slug": "motion-job-receipt-1"},
        "missing_mandatory": [],
        "delivered_at": "2026-10-15T00:00:00.000Z",
    }


def make_validator():
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        schema = json.load(fh)
    composed = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": "#/$defs/delivery_receipt",
    }
    Draft202012Validator.check_schema(composed)
    return Draft202012Validator(composed)


class DeliveryReceiptSchemaTests(unittest.TestCase):
    def setUp(self):
        self.validator = make_validator()

    def errors(self, doc):
        return list(self.validator.iter_errors(doc))

    def test_conformant_receipt_validates(self):
        self.assertEqual(self.errors(valid_receipt()), [])

    def test_insert_receipt_under_parent_task_validates(self):
        doc = valid_receipt()
        doc["task"] = {
            "task_id": "parent-task-1",
            "origin": "parent",
            "parent_job_id": "parent-job-1",
            "parent_task_id": "parent-task-1",
        }
        doc["board"] = {"job_id": "parent-job-1", "stage_slug": "motion-job-receipt-1"}
        self.assertEqual(self.errors(doc), [])

    def test_release_status_never_poses_as_production_status(self):
        doc = valid_receipt()
        doc["production_status"] = "RELEASED"
        self.assertNotEqual(self.errors(doc), [])

    def test_code_review_approval_is_structurally_excluded(self):
        doc = valid_receipt()
        bad = copy.deepcopy(doc["approvals"][0])
        bad["kind"] = "code_review_approval"
        doc["approvals"] = [bad]
        self.assertNotEqual(self.errors(doc), [])

    def test_non_empty_missing_mandatory_is_not_a_receipt(self):
        doc = valid_receipt()
        doc["missing_mandatory"] = ["poster"]
        self.assertNotEqual(self.errors(doc), [])

    def test_unmeasured_artifact_fails(self):
        doc = valid_receipt()
        doc["artifacts"] = [{"kind": "mp4", "path": "renders/final.mp4", "bytes": 10}]
        self.assertNotEqual(self.errors(doc), [])

    def test_failed_qc_verdict_fails(self):
        doc = valid_receipt()
        doc["qc"]["verdict"] = "fail"
        self.assertNotEqual(self.errors(doc), [])

    def test_unknown_top_level_key_fails(self):
        doc = valid_receipt()
        doc["code_review"] = {"approved_by": "someone"}
        self.assertNotEqual(self.errors(doc), [])


if __name__ == "__main__":
    unittest.main()
