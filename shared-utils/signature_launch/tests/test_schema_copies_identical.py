#!/usr/bin/env python3
"""Harmony issue 85: the page-request and page-result schemas exist as three copies, and the three agree.

The shared domain copy (shared-utils/signature_launch/domain/) is canonical. Skill 49 vendors a copy
(49-signature-funnel/scripts/vendor/) for its stdlib fallback validator and Skill 71 carries a copy
(71-blackceo-signature-page/references/) that its launch-context import and page-result emitter read.
Before, the three differed: 49's request copy was frozen at schema_version "1.0" with no
prompt_policy_id (so a 1.1 request failed a strict check against it), the shared copy was "1.1" only,
and the page-result copies disagreed on `page_role`. This test fails on any byte of drift.

Run: python3 shared-utils/signature_launch/tests/test_schema_copies_identical.py
"""
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CANONICAL = HERE.parent / "domain"
COPIES = {
    "page-request.schema.json": [
        REPO / "49-signature-funnel" / "scripts" / "vendor" / "page-request.schema.json",
        REPO / "71-blackceo-signature-page" / "references" / "page-request.schema.json",
    ],
    "page-result.schema.json": [
        REPO / "49-signature-funnel" / "scripts" / "vendor" / "page-result.schema.json",
        REPO / "71-blackceo-signature-page" / "references" / "page-result.schema.json",
    ],
}
PAGE_ROLES = ["landing", "product_selection", "checkout", "upsell_1", "downsell_1", "upsell_2", "thank_you"]


class SchemaCopiesIdentical(unittest.TestCase):
    def test_every_copy_is_byte_identical_to_the_canonical_shared_file(self):
        for name, copies in COPIES.items():
            canonical = (CANONICAL / name).read_bytes()
            for copy in copies:
                self.assertTrue(copy.is_file(), f"{copy} is missing")
                self.assertEqual(copy.read_bytes(), canonical,
                                 f"{copy.relative_to(REPO)} differs from {(CANONICAL / name).relative_to(REPO)}")

    def test_request_schema_carries_both_versions_and_an_optional_policy_id(self):
        doc = json.loads((CANONICAL / "page-request.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["properties"]["schema_version"]["enum"], ["1.0", "1.1"])
        self.assertIn("prompt_policy_id", doc["properties"])
        self.assertNotIn("prompt_policy_id", doc["required"], "a 1.0 request carries no policy id")
        self.assertEqual(doc["properties"]["page_role"]["enum"], PAGE_ROLES)
        # a 1.1 request must name its policy; the rule rides in allOf so 1.0 requests stay valid
        rule = next(c for c in doc["allOf"] if c["if"]["properties"]["schema_version"]["const"] == "1.1")
        self.assertEqual(rule["then"]["required"], ["prompt_policy_id"])

    def test_result_schema_requires_and_closes_page_role(self):
        doc = json.loads((CANONICAL / "page-result.schema.json").read_text(encoding="utf-8"))
        self.assertIn("page_role", doc["required"])
        self.assertEqual(doc["properties"]["page_role"]["enum"], PAGE_ROLES)

    def test_the_preserved_v1_0_request_schema_is_untouched_by_the_merge(self):
        doc = json.loads((CANONICAL / "page-request.v1.0.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["properties"]["schema_version"].get("const"), "1.0")


if __name__ == "__main__":
    unittest.main()
