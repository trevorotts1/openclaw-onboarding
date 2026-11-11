"""Issue 19: DISPATCH.md says what the code does about the deliverable set.

It once said the page-types file's entries do not map to the check's kinds, so the check reports
`builtin`. They do map, and the check reports `file:`. The document is held to the code's answer.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import page_designs  # noqa: E402

DISPATCH = (SKILL_ROOT / "DISPATCH.md").read_text(encoding="utf-8")


class DispatchDocLockstepTests(unittest.TestCase):
    def test_the_deliverable_set_is_read_from_the_page_types_file(self):
        kinds, source = page_designs.load_page_types()
        self.assertTrue(source.startswith("file:"), source)
        self.assertTrue(kinds["*"], "the file names no default deliverable kind")

    def test_every_deliverable_id_in_the_file_maps_to_a_checked_kind(self):
        doc, _path = page_designs._page_types_doc()
        ids = {d["id"] for d in doc["deliverables"]}
        self.assertEqual(ids - set(page_designs._DELIVERABLE_KIND), set())
        self.assertEqual({page_designs._DELIVERABLE_KIND[i] for i in ids}, set(page_designs.load_page_types()[0]["*"]))

    def test_the_document_no_longer_claims_the_entries_do_not_map(self):
        self.assertNotIn("do not map to these kinds", DISPATCH)
        self.assertNotIn("reports\n`builtin` for every run", DISPATCH)
        self.assertNotIn("tracked as IMG-13", DISPATCH)
        self.assertIn("(source `file:`)", DISPATCH)
        self.assertIn("49-signature-funnel/structure/page_types.json", DISPATCH)


if __name__ == "__main__":
    unittest.main()
