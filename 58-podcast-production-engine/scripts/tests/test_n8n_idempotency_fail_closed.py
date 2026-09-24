#!/usr/bin/env python3
"""Static regression for the n8n idempotency-error safety boundary.

This does not claim exactly-once delivery: n8n Data Table get/upsert is not an
atomic claim.  It ensures lookup/write failures stop before Podbean: a lookup
failure cannot become an empty lookup, and a lost claim write cannot proceed
as unseen.
"""

import json
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / "config/n8n/podbean-publish.workflow.json"


class IdempotencyLookupSafetyTest(unittest.TestCase):
    def setUp(self):
        self.workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        self.nodes = {node["name"]: node for node in self.workflow["nodes"]}

    def test_lookup_error_stops_before_verdict(self):
        lookup = self.nodes["Idempotency  --  Lookup By Key"]
        self.assertEqual(lookup["onError"], "stopWorkflow")
        self.assertTrue(lookup["alwaysOutputData"], "successful no-match must still reach verdict")
        self.assertIn("NOT an atomic claim", lookup["notes"])

    def test_claim_write_errors_stop_before_podbean(self):
        for name in ("Idempotency  --  Upsert Row Received", "Idempotency  --  Mark In Flight"):
            node = self.nodes[name]
            self.assertEqual(node["onError"], "stopWorkflow", name)
            self.assertTrue(node["alwaysOutputData"], name)
            self.assertIn("FAIL-CLOSED", node["notes"], name)
            self.assertIn("NOT an atomic compare-and-set", node["notes"], name)

    def test_verdict_does_not_describe_lookup_error_as_an_empty_lookup(self):
        source = self.nodes["Idempotency  --  Determine Verdict"]["parameters"]["jsCode"]
        self.assertIn("fail-closed", source)
        self.assertNotIn("Fail-open on a genuine table-read error", source)
        self.assertIn("not an atomic compare-and-set", source)


if __name__ == "__main__":
    unittest.main()
