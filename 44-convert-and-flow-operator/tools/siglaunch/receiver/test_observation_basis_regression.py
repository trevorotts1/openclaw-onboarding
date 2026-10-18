"""Regression tests for the layer-9 observation basis (MAIN ruling,
2026-10-18, option (a)).

The native internal-API workflow object — verified firsthand in A16
runs 7-8 against the export object, Tier-0 list/get, and the internal
listing — carries NO status field and NO trigger contents. Triggers
live in a separate trigger-bucket file (the object carries
triggersFilePath + isTriggerBucketMigrated); draft state is a property
of the object's draft-only construction (the builder has no publish
operation). The receipt contract's original checks assumed a
public-API-shaped export (top-level status "draft", embedded trigger
list) that the real internal object never had, so trigger_bound and
draft_state_recorded could never pass.

Under the ruling, the executor's normalization RECORDS the native
evidence verbatim into the readback and observes from it; the
receiver's trigger check accepts that recorded bucket evidence when
the export carries no explicit triggers list. These tests pin the
basis — and its fail-closed edges: a deleted object never derives
draft, an explicit native status always governs, an explicit drifted
trigger list is never papered over by bucket evidence, and absent
bucket evidence the trigger check still fails.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from caf_executor import CafExecutor, _normalize_export  # noqa: E402
from receiver import Receiver  # noqa: E402

WF_ID = "cd3e0990-dacd-417a-8d2d-855b51a1a7b4"
TRIGGERS_PATH = ("location/XCgFTEA1oDvsPnTqqgoB/workflow-triggers/"
                 + WF_ID + "/3")

DECLARED = {"mechanism": {"type": "contact_tag",
                          "tag": "email-engine:sequence-x"},
            "trigger": {"type": "contact_tag",
                        "tag": "email-engine:sequence-x"}}


def native_object(**overrides):
    """The real internal-API workflow object shape (run 8's export,
    field for field in the respects that matter here)."""
    obj = {
        "id": WF_ID,
        "_id": WF_ID,
        "name": "sequence-signature-launch-landing-10 (DRAFT)",
        "deleted": False,
        "creationSource": "builder",
        "version": 3,
        "dataVersion": 7,
        "allowMultiple": False,
        "triggersFilePath": TRIGGERS_PATH,
        "isTriggerBucketMigrated": True,
        "workflowData": {"templates": [{"id": "s1", "type": "email"}]},
    }
    obj.update(overrides)
    return obj


class NormalizeObservationTests(unittest.TestCase):

    def test_native_object_records_evidence_and_observes_draft(self):
        export = _normalize_export(native_object(), WF_ID)
        self.assertEqual(export["status"], "draft")
        self.assertEqual(export["status_evidence"], {
            "deleted": False, "creation_source": "builder",
            "version": 3, "data_version": 7})
        self.assertEqual(export["trigger_evidence"], {
            "triggers_file_path": TRIGGERS_PATH,
            "bucket_migrated": True})
        self.assertEqual(export["triggers"], [])
        self.assertEqual(export["id"], WF_ID)

    def test_deleted_object_never_derives_draft(self):
        export = _normalize_export(native_object(deleted=True), WF_ID)
        self.assertIsNone(export["status"])
        self.assertNotIn("status_evidence", export)

    def test_missing_deleted_field_never_derives_draft(self):
        obj = native_object()
        del obj["deleted"]
        export = _normalize_export(obj, WF_ID)
        self.assertIsNone(export["status"])
        self.assertNotIn("status_evidence", export)

    def test_explicit_native_status_governs(self):
        export = _normalize_export(
            native_object(status="published"), WF_ID)
        self.assertEqual(export["status"], "published")
        self.assertNotIn("status_evidence", export)

    def test_no_bucket_fields_no_trigger_evidence(self):
        obj = native_object()
        del obj["triggersFilePath"]
        del obj["isTriggerBucketMigrated"]
        export = _normalize_export(obj, WF_ID)
        self.assertNotIn("trigger_evidence", export)


class TriggerBoundObservationTests(unittest.TestCase):

    def test_bucket_evidence_observes_binding(self):
        export = _normalize_export(native_object(), WF_ID)
        self.assertTrue(Receiver._trigger_bound(DECLARED, export))

    def test_absent_evidence_still_fails(self):
        export = {"triggers": []}
        self.assertFalse(Receiver._trigger_bound(DECLARED, export))

    def test_bucket_not_migrated_still_fails(self):
        export = {"triggers": [],
                  "trigger_evidence": {
                      "triggers_file_path": TRIGGERS_PATH,
                      "bucket_migrated": False}}
        self.assertFalse(Receiver._trigger_bound(DECLARED, export))

    def test_explicit_matching_trigger_governs(self):
        export = {"triggers": [{"type": "contact_tag",
                                "tag": "email-engine:sequence-x"}]}
        self.assertTrue(Receiver._trigger_bound(DECLARED, export))

    def test_explicit_drifted_trigger_not_papered_over(self):
        export = {"triggers": [{"type": "form_submitted"}],
                  "trigger_evidence": {
                      "triggers_file_path": TRIGGERS_PATH,
                      "bucket_migrated": True}}
        self.assertFalse(Receiver._trigger_bound(DECLARED, export))


class FullStatsRecordingTests(unittest.TestCase):

    def test_build_records_full_stats(self):
        stats = {"workflows_created": 1, "steps_saved": 19,
                 "triggers_created": 1, "errors": [], "notes": [],
                 "start_time": 1.0, "end_time": 2.0, "api_calls": 7,
                 "workflow_ids": {"sequence-x": WF_ID},
                 "folder_id": "folder-0001"}

        def runner(argv, timeout):
            if "build" in argv:
                return (0, json.dumps(stats), "")
            if "export" in argv:
                out_path = argv[argv.index("--out") + 1]
                Path(out_path).write_text(json.dumps(native_object()))
                return (0, "", "")
            if argv[0] == "bash":
                return (0, json.dumps(
                    {"rubric": {"weighted_floor": 9.0}}), "")
            raise AssertionError(f"unexpected argv: {argv}")

        qc = tempfile.NamedTemporaryFile("w", suffix=".sh",
                                         delete=False)
        qc.write("#!/bin/bash\n")
        qc.close()
        executor = CafExecutor(caf_path="/tmp/caf", runner=runner,
                               qc_script=qc.name)
        result = executor.build(
            {"folder": "F", "sequence-x": {"name": "sequence-x"}})
        self.assertEqual(result["workflow_id"], WF_ID)
        self.assertEqual(result["stats"], stats)
        self.assertEqual(result["stats"]["triggers_created"], 1)
        self.assertEqual(result["export"]["status"], "draft")
        self.assertEqual(result["export"]["trigger_evidence"]
                         ["bucket_migrated"], True)


if __name__ == "__main__":
    unittest.main()
