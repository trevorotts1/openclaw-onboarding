#!/usr/bin/env python3
"""Unit tests for exemplar_injection.py — A-U9 (master unit U9): exemplar
convention + write-time injection, CALIBRATION-ONLY clause + injection
receipts. stdlib only.

  python3 -m unittest shared-utils/test_exemplar_injection.py
  (or)  python3 shared-utils/test_exemplar_injection.py
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exemplar_injection as exi  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SKILL6_DIR = os.path.join(_REPO, "06-ghl-install-pages")
_SKILL35_DIR = os.path.join(_REPO, "35-social-media-planner")


class TestDiscoverPacksAcceptanceA(unittest.TestCase):
    """(a) >=1 exemplar pack per funnel-template category (lead/buyer/event)
    + >=1 for Skill 35, each with all three required files."""

    def test_skill6_ships_a_complete_pack_per_category(self):
        for category in ("lead", "buyer", "event"):
            packs = exi.discover_packs(_SKILL6_DIR, deliverable_type=category)
            self.assertGreaterEqual(
                len(packs), 1, f"Skill 6 must ship >=1 exemplar pack for {category!r}")
            for pack in packs:
                self.assertTrue(os.path.isfile(pack["gold_output_path"]))
                self.assertTrue(os.path.isfile(pack["why_good_path"]))
                self.assertTrue(os.path.isfile(pack["provenance_path"]))
                self.assertEqual(pack["deliverable_type"], category)

    def test_skill35_ships_a_complete_pack(self):
        packs = exi.discover_packs(_SKILL35_DIR)
        self.assertGreaterEqual(len(packs), 1, "Skill 35 must ship >=1 exemplar pack")
        for pack in packs:
            self.assertTrue(os.path.isfile(pack["gold_output_path"]))
            self.assertTrue(os.path.isfile(pack["why_good_path"]))
            self.assertTrue(os.path.isfile(pack["provenance_path"]))

    def test_incomplete_pack_directory_is_never_surfaced(self):
        with tempfile.TemporaryDirectory() as td:
            pack_dir = os.path.join(td, "exemplars", "lead", "half-pack")
            os.makedirs(pack_dir)
            with open(os.path.join(pack_dir, "gold-output.md"), "w") as f:
                f.write("gold")
            # WHY-GOOD.md and provenance.json deliberately missing.
            packs = exi.discover_packs(td, deliverable_type="lead")
            self.assertEqual(packs, [], "a partial pack is never a pack")

    def test_content_hashes_are_real_sha256_of_the_shipped_files(self):
        import hashlib
        packs = exi.discover_packs(_SKILL6_DIR, deliverable_type="lead")
        self.assertGreaterEqual(len(packs), 1)
        pack = packs[0]
        with open(pack["gold_output_path"], "rb") as f:
            expected = "sha256:" + hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(pack["gold_output_hash"], expected)


class TestSelectExemplarsAcceptanceD(unittest.TestCase):
    """(d) prompts without an applicable pack degrade to today's behavior
    (no empty-injection block)."""

    def test_no_applicable_pack_returns_empty_list(self):
        self.assertEqual(
            exi.select_exemplars(_SKILL6_DIR, "no-such-deliverable-type"), [])

    def test_empty_deliverable_type_returns_empty_list(self):
        self.assertEqual(exi.select_exemplars(_SKILL6_DIR, ""), [])
        self.assertEqual(exi.select_exemplars(_SKILL6_DIR, None), [])

    def test_applicable_pack_is_selected_deterministically(self):
        a = exi.select_exemplars(_SKILL6_DIR, "lead")
        b = exi.select_exemplars(_SKILL6_DIR, "lead")
        self.assertEqual(a, b, "repeated calls with the same inputs must be stable")
        self.assertGreaterEqual(len(a), 1)
        self.assertLessEqual(len(a), 2, "spec: 1-2 exemplars per deliverable type")

    def test_register_filter_falls_back_to_full_pool_when_no_tagged_pack_matches(self):
        # None of the shipped initial packs tag a persona_register, so any
        # requested register must fall back to the full deliverable-type pool
        # rather than returning [] (a register ask must never suppress an
        # otherwise-applicable pack).
        with_register = exi.select_exemplars(
            _SKILL6_DIR, "lead", persona_register="hormozi-100m-offers")
        without_register = exi.select_exemplars(_SKILL6_DIR, "lead")
        self.assertEqual(with_register, without_register)


class TestBuildInjectionBlockAcceptanceD(unittest.TestCase):
    """(d) no empty-injection block; CALIBRATION-ONLY clause verbatim-
    adapted from the Skill-58 style-engines pattern."""

    def test_empty_packs_yields_none_not_an_empty_block(self):
        self.assertIsNone(exi.build_injection_block([]))

    def test_block_carries_calibration_only_language(self):
        packs = exi.select_exemplars(_SKILL6_DIR, "buyer")
        block = exi.build_injection_block(packs)
        self.assertIsNotNone(block)
        self.assertIn("CALIBRATION ONLY", block)
        self.assertIn("Never copy their wording", block)
        for p in packs:
            self.assertIn(p["exemplar_id"], block)

    def test_block_contains_the_actual_gold_output_text(self):
        packs = exi.select_exemplars(_SKILL6_DIR, "event")
        block = exi.build_injection_block(packs)
        with open(packs[0]["gold_output_path"], encoding="utf-8") as f:
            gold = f.read().strip()
        self.assertIn(gold.splitlines()[0], block)


class TestWriteInjectionReceiptAcceptanceB(unittest.TestCase):
    """(b) a fixture funnel copy job's evidence tree contains
    routing/exemplar-injection.json whose hashes match the shipped
    exemplars."""

    def test_receipt_hashes_match_shipped_exemplars(self):
        with tempfile.TemporaryDirectory() as td:
            packs = exi.select_exemplars(_SKILL6_DIR, "lead")
            exi.write_injection_receipt(td, packs, deliverable_type="lead", page="Optin")

            receipt_path = os.path.join(td, "routing", "exemplar-injection.json")
            self.assertTrue(os.path.isfile(receipt_path))
            with open(receipt_path, encoding="utf-8") as f:
                on_disk = json.load(f)

            self.assertEqual(len(on_disk["injections"]), 1)
            entry = on_disk["injections"][0]
            self.assertTrue(entry["injected"])
            self.assertEqual(entry["deliverable_type"], "lead")
            self.assertEqual(entry["page"], "Optin")
            self.assertGreaterEqual(len(entry["exemplars"]), 1)

            shipped_hashes = {p["gold_output_hash"] for p in packs}
            receipt_hashes = {e["content_hash"] for e in entry["exemplars"]}
            self.assertEqual(receipt_hashes, shipped_hashes)

    def test_receipt_accumulates_across_multiple_pages_never_clobbers(self):
        with tempfile.TemporaryDirectory() as td:
            lead_packs = exi.select_exemplars(_SKILL6_DIR, "lead")
            buyer_packs = exi.select_exemplars(_SKILL6_DIR, "buyer")
            exi.write_injection_receipt(td, lead_packs, deliverable_type="lead", page="Optin")
            exi.write_injection_receipt(td, buyer_packs, deliverable_type="buyer", page="Sales")

            receipt_path = os.path.join(td, "routing", "exemplar-injection.json")
            with open(receipt_path, encoding="utf-8") as f:
                on_disk = json.load(f)
            self.assertEqual(len(on_disk["injections"]), 2)
            self.assertEqual(on_disk["injections"][0]["page"], "Optin")
            self.assertEqual(on_disk["injections"][1]["page"], "Sales")

    def test_no_applicable_pack_still_writes_an_honest_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            exi.write_injection_receipt(
                td, [], deliverable_type="no-such-type", page="ThankYou")
            receipt_path = os.path.join(td, "routing", "exemplar-injection.json")
            self.assertTrue(os.path.isfile(receipt_path))
            with open(receipt_path, encoding="utf-8") as f:
                on_disk = json.load(f)
            entry = on_disk["injections"][0]
            self.assertFalse(entry["injected"])
            self.assertEqual(entry["exemplars"], [])


class TestLlmContentReviewAcceptanceC(unittest.TestCase):
    """(c) an LLM reviewer pass (never a name-grep) confirms zero
    client-identifying content in every pack."""

    def test_every_shipped_pack_carries_an_llm_content_review_receipt(self):
        all_packs = (
            exi.discover_packs(_SKILL6_DIR, deliverable_type="lead")
            + exi.discover_packs(_SKILL6_DIR, deliverable_type="buyer")
            + exi.discover_packs(_SKILL6_DIR, deliverable_type="event")
            + exi.discover_packs(_SKILL35_DIR)
        )
        self.assertGreaterEqual(len(all_packs), 4)
        for pack in all_packs:
            review = (pack["provenance"] or {}).get("llm_content_review")
            self.assertIsInstance(
                review, dict,
                f"{pack['exemplar_id']} provenance.json must carry an "
                "llm_content_review receipt")
            self.assertTrue(review.get("reviewed") is True)
            self.assertTrue(review.get("verdict"), "the receipt must state a verdict")
            method = review.get("method", "").lower()
            self.assertIn(
                "read", method,
                "the review method must describe an actual read, not a bare grep")
            self.assertTrue(pack["provenance"].get("anonymized") is True)


if __name__ == "__main__":
    unittest.main()
