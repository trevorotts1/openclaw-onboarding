#!/usr/bin/env python3
"""test_page_types_legend.py - proves structure/page_types.json explains itself.

Issue 93 (harmony review): every page entry carries ``design_only`` but the file's
``needs_legend`` never said what it means, so a reader could not tell "the role has no
production page by design" from "no production page exists yet". The legend now defines
every key a page entry uses and every ``needs`` value a deliverable uses, and this test
fails when a key or value is added without a definition (or the definition of
``design_only`` loses its meaning).
Stdlib only, no network. Run: python3 test_page_types_legend.py"""
import json
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
PAGE_TYPES = SKILL / "structure" / "page_types.json"


def load():
    return json.loads(PAGE_TYPES.read_text(encoding="utf-8"))


def undefined(doc):
    """Names used by an entry or deliverable that needs_legend does not define."""
    legend = doc.get("needs_legend") or {}
    used = {key for page in doc["pages"].values() for key in page}
    used |= {d["needs"] for d in doc["deliverables"]}
    return sorted(name for name in used
                  if not isinstance(legend.get(name), str) or not legend[name].strip())


class PageTypesLegend(unittest.TestCase):
    def test_every_key_and_needs_value_in_use_is_defined(self):
        self.assertEqual(undefined(load()), [])

    def test_design_only_is_defined_with_its_meaning(self):
        text = load()["needs_legend"]["design_only"]
        for phrase in ("no production page by design", "false", "produce"):
            self.assertIn(phrase, text)

    def test_design_only_values_are_booleans(self):
        for key, page in load()["pages"].items():
            self.assertIsInstance(page["design_only"], bool, key)

    def test_the_check_catches_an_undefined_key(self):
        # Control: the predicate must fire on a new, undefined key and on a
        # blank definition, or the first test proves nothing.
        doc = load()
        doc["pages"]["upsell_1"]["brand_new_flag"] = True
        self.assertEqual(undefined(doc), ["brand_new_flag"])
        doc = load()
        doc["needs_legend"]["design_only"] = "  "
        self.assertEqual(undefined(doc), ["design_only"])
        doc = load()
        del doc["needs_legend"]["design_only"]
        self.assertEqual(undefined(doc), ["design_only"])


if __name__ == "__main__":
    unittest.main()
