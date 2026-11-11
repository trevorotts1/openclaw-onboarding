#!/usr/bin/env python3
"""Harmony issue 85: a page result carries the page_role of its request, in the schema and in the emitter.

The one canonical page-result schema (shared-utils/signature_launch/domain/, copied byte for byte into
Skill 49 and Skill 71) REQUIRES `page_role`, closed to the seven roles. Skill 71's emitter copies it
from the request and refuses to write a result for a request that has none.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
import test_page_result as fixture  # noqa: E402


class PageRoleEcho(unittest.TestCase):
    def test_every_emitted_result_echoes_the_requests_page_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = fixture.make_run(tmp, submission=fixture.VERIFIED_SUBMISSION)
            proc = fixture.run_writer(run)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(fixture.load(run, "page-result.json")["page_role"], "landing")

    def test_a_request_with_no_page_role_refuses_emission_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = fixture.make_run(tmp, submission=fixture.VERIFIED_SUBMISSION)
            request = json.loads((run / "page-request.json").read_text())
            del request["page_role"]
            (run / "page-request.json").write_text(json.dumps(request))
            proc = fixture.run_writer(run)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            # The emitter's own required-field guard speaks, not only the schema validator behind it.
            self.assertIn("page-request.json is missing 'page_role'", proc.stdout)
            self.assertFalse((run / "page-result.json").exists())
            self.assertFalse((run / "page-handoff.json").exists())

    def test_the_schema_requires_page_role_and_closes_it_to_the_seven_roles(self):
        doc = json.loads((HERE.parent / "references" / "page-result.schema.json").read_text())
        self.assertIn("page_role", doc["required"])
        self.assertEqual(doc["properties"]["page_role"]["enum"],
                         ["landing", "product_selection", "checkout", "upsell_1", "downsell_1", "upsell_2", "thank_you"])


if __name__ == "__main__":
    unittest.main()
