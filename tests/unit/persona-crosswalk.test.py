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
import json
import subprocess
import sys
import tempfile
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


class TestCopyCraftPool(unittest.TestCase):
    """D5/B-D1 (RATIFIED 2026-07-14) — kills the old 5-surname copy-persona cap. Locks down the
    B-U4 acceptance: the pool exists, every member is canonical, and --validate fails closed when
    the pool is tampered with (fake member seeded, emptied, or the key deleted outright)."""

    @classmethod
    def setUpClass(cls):
        cls.res = pc.scan()
        cls.canonical = set(cls.res["canonical"])
        cls.crosswalk = pc.load_crosswalk()

    def test_pool_present_and_nonempty(self):
        pool = pc.load_copy_craft_pool(self.crosswalk)
        self.assertTrue(pool, "copy_craft_pool is missing or empty in persona-crosswalk.json")
        self.assertGreaterEqual(len(pool), 5, "pool should be >= the original 5 craft-discipline surnames")

    def test_pool_matches_scan_result(self):
        self.assertEqual(pc.load_copy_craft_pool(self.crosswalk), self.res["copy_craft_pool"])

    def test_every_pool_member_is_canonical(self):
        self.assertEqual(self.res["bad_pool_members"], [])
        pool = pc.load_copy_craft_pool(self.crosswalk)
        for pid in pool:
            self.assertIn(pid, self.canonical, f"copy_craft_pool member {pid!r} is not canonical")

    def test_pool_covers_the_original_five_craft_disciplines(self):
        # The old cap named bare surnames (bly, wiebe, miller, hormozi, cialdini); the pool must
        # cover a REAL canonical id for each — expanded to every book variant that surname covers.
        pool = set(pc.load_copy_craft_pool(self.crosswalk))
        expected_by_surname = {
            "bly": {"bly-copywriters-handbook"},
            "wiebe": {"wiebe-copy-hackers"},
            "miller": {"miller-building-storybrand", "miller-coach-builder", "miller-marketing-made-simple"},
            "hormozi": {"hormozi-100m-leads", "hormozi-100m-offers"},
            "cialdini": {"cialdini-influence", "cialdini-pre-suasion"},
        }
        for surname, ids in expected_by_surname.items():
            self.assertTrue(ids.issubset(pool), f"pool missing {surname} canonical id(s): {ids - pool}")

    def test_pool_covers_edwards_and_brunson_family(self):
        pool = set(pc.load_copy_craft_pool(self.crosswalk))
        self.assertIn("edwards-copywriting-secrets", pool)
        brunson_targets = {t for _, t in self.crosswalk["patterns"] if "brunson" in t}
        self.assertTrue(brunson_targets, "no brunson-family targets found in crosswalk patterns to compare against")
        self.assertTrue(brunson_targets.issubset(pool),
                         f"pool missing Brunson-family crosswalk target(s): {brunson_targets - pool}")

    def _run_validate(self, crosswalk_path: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(_SHARED / "persona_crosswalk.py"), "--validate",
             "--crosswalk", crosswalk_path],
            capture_output=True, text=True, cwd=str(_REPO_ROOT))

    def test_validate_exits_0_with_real_pool(self):
        cp = self._run_validate(str(_SHARED / "persona-crosswalk.json"))
        self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)
        self.assertIn("copy_craft_pool", cp.stdout)

    def test_validate_exits_nonzero_on_fake_pool_member(self):
        real = pc.load_crosswalk()
        real["copy_craft_pool"] = list(real["copy_craft_pool"]) + ["totally-fake-persona-id-xyz"]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(real, f)
            tmp_path = f.name
        try:
            cp = self._run_validate(tmp_path)
            self.assertNotEqual(cp.returncode, 0, "validate should fail on a fake pool member")
            self.assertIn("COPY-CRAFT POOL ERROR", cp.stdout)
            self.assertIn("totally-fake-persona-id-xyz", cp.stdout)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_validate_exits_nonzero_on_empty_pool(self):
        real = pc.load_crosswalk()
        real["copy_craft_pool"] = []
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(real, f)
            tmp_path = f.name
        try:
            cp = self._run_validate(tmp_path)
            self.assertNotEqual(cp.returncode, 0, "validate should fail on an empty pool")
            self.assertIn("COPY-CRAFT POOL ERROR", cp.stdout)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_validate_exits_nonzero_on_deleted_pool_key(self):
        real = pc.load_crosswalk()
        del real["copy_craft_pool"]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(real, f)
            tmp_path = f.name
        try:
            cp = self._run_validate(tmp_path)
            self.assertNotEqual(cp.returncode, 0, "validate should fail when the pool key is deleted outright")
            self.assertIn("COPY-CRAFT POOL ERROR", cp.stdout)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
