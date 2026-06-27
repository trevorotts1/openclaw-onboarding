#!/usr/bin/env python3
"""Unit tests for shared-utils/persona_crosswalk.py — the D5 persona-vocabulary reconciliation.

Locks down the closure: every funnel + automation template persona ref resolves to a REAL
canonical persona-categories.json id (0 unresolved), every crosswalk target is itself canonical,
and the short template slugs map to the personas a human would expect. This is the drift guard:
if a new template adds an un-mappable persona slug, this test (and the CI drift gate) fails.

Run:
    python3 tests/unit/persona-crosswalk.test.py
    or: pytest tests/unit/persona-crosswalk.test.py
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED = _REPO_ROOT / "shared-utils"
sys.path.insert(0, str(_SHARED))

_spec = importlib.util.spec_from_file_location("persona_crosswalk", _SHARED / "persona_crosswalk.py")
pc = importlib.util.module_from_spec(_spec)
sys.modules["persona_crosswalk"] = pc
_spec.loader.exec_module(pc)


class TestPersonaCrosswalk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = pc.scan()
        cls.canonical = set(cls.res["canonical"])
        cls.crosswalk = pc.load_crosswalk()

    def test_zero_unresolved_refs_across_all_templates(self):
        unresolved = [r for r in self.res["rows"] if not r["ok"]]
        self.assertEqual(unresolved, [], f"unresolved persona refs: {unresolved[:5]}")
        self.assertEqual(self.res["counts"]["unresolved"], 0)

    def test_expected_library_sizes(self):
        c = self.res["counts"]
        self.assertEqual(c["funnel_templates"], 38)
        self.assertEqual(c["automation_templates"], 28)
        self.assertGreater(c["refs"], 100)      # ~181 persona refs across the two libraries

    def test_every_crosswalk_target_is_canonical(self):
        self.assertEqual(self.res["bad_targets"], [])
        for tgt in self.crosswalk["slug_map"].values():
            self.assertIn(tgt, self.canonical, tgt)
        for _, tgt in self.crosswalk["patterns"]:
            self.assertIn(tgt, self.canonical, tgt)

    def test_known_slug_resolutions(self):
        cases = {
            "funnel-architect": "brunson-marketing-secrets-blackbook",
            "copy-closer": "edwards-copywriting-secrets",
            "story-brander": "miller-building-storybrand",
            "traffic-strategist": "russell-brunson-traffic-secrets",
            "storybrand-sb7": "miller-building-storybrand",
        }
        for slug, expected in cases.items():
            target, how = pc.resolve(slug, self.canonical, self.crosswalk)
            self.assertEqual(target, expected, f"{slug} -> {target} ({how})")

    def test_freetext_book_descriptions_resolve(self):
        cases = [
            ("Russell Brunson — Traffic Secrets persona (The Traffic Strategist): Dream 100",
             "russell-brunson-traffic-secrets"),
            ("Network Marketing Secrets (Epiphany Bridge Script)", "brunson-network-marketing-secrets"),
            ("Lead Funnels Swipe File — Follow-Up Funnels", "russell-brunson-lead-funnels"),
            ("The Funnel Hacker's Cookbook (Russell Brunson)", "russell-brunson-the-funnel-hackers-cookbook"),
            ("Copywriting Secrets (Jim Edwards)", "edwards-copywriting-secrets"),
        ]
        for ref, expected in cases:
            target, how = pc.resolve(ref, self.canonical, self.crosswalk)
            self.assertEqual(target, expected, f"{ref!r} -> {target} ({how})")

    def test_canonical_ids_resolve_to_themselves(self):
        for cid in ("russell-brunson-lead-funnels", "edwards-copywriting-secrets",
                    "miller-building-storybrand", "brunson-marketing-secrets-blackbook"):
            target, how = pc.resolve(cid, self.canonical, self.crosswalk)
            self.assertEqual(target, cid)
            self.assertEqual(how, "canonical-id")


if __name__ == "__main__":
    unittest.main(verbosity=2)
