"""Issue 72: the design marker is accepted only when the request's stage is "design".

At the design stage no purchase has happened. The original purchase (and a U2 qualifying purchase) is the
marker `design_marker`, which Skill 80's validate_request accepts only with stage == "design" and which
never reads as verified proof anywhere else.

Run: python3 -m unittest test_design_marker_stage   (from this directory)
"""

import copy
import json
import sys
import unittest
from pathlib import Path

ADAPTERS_DIR = Path(__file__).resolve().parent
SKILL_DIR = ADAPTERS_DIR.parent / "80-signature-upsell"
FIXTURES = ADAPTERS_DIR / "fixtures"
sys.path.insert(0, str(ADAPTERS_DIR))

import adapter_common as common  # noqa: E402
import upsell1_adapter  # noqa: E402
import upsell2_adapter  # noqa: E402

U1_COPY = SKILL_DIR / "fixtures" / "copy-upsell1-public.valid.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def u1_marker_request(stage="design"):
    request = load(SKILL_DIR / "fixtures" / "request-upsell1.testonly.json")
    request["eligibility"]["original_purchase"] = {"status": "design_marker"}
    if stage is not None:
        request["stage"] = stage
    return request


def u2_marker_request(stage="design"):
    request = load(FIXTURES / "request-upsell2-from-upsell1.testonly.json")
    request["eligibility"]["original_purchase"] = {"status": "design_marker"}
    request["eligibility"]["qualifying_purchase"] = {"slot": "upsell_1", "status": "design_marker"}
    if stage is not None:
        request["stage"] = stage
    return request


class DesignMarkerStageTests(unittest.TestCase):
    def test_the_marker_is_refused_without_stage_design(self):
        for stage in (None, "install"):
            with self.subTest(stage=stage):
                with self.assertRaises(common.AdapterError) as ctx:
                    common.validate_request(u1_marker_request(stage), "upsell_1")
                self.assertIn("design_marker", str(ctx.exception))
                self.assertIn("'design'", str(ctx.exception))

    def test_the_marker_is_accepted_with_stage_design(self):
        common.validate_request(u1_marker_request("design"), "upsell_1")

    def test_an_unknown_stage_is_refused(self):
        with self.assertRaises(common.AdapterError):
            common.validate_request(u1_marker_request("live"), "upsell_1")

    def test_an_unknown_stage_is_refused_by_the_vocabulary_check_itself(self):
        """A verified-purchase request carries no marker, so the marker rule cannot be what refuses it."""
        base = load(SKILL_DIR / "fixtures" / "request-upsell1.testonly.json")
        for stage in ("design", "install"):
            common.validate_request(dict(base, stage=stage), "upsell_1")
        for stage in ("live", "bogus", ""):
            with self.subTest(stage=stage):
                with self.assertRaises(common.AdapterError) as ctx:
                    common.validate_request(dict(base, stage=stage), "upsell_1")
                self.assertIn("stage %r is not one of ['design', 'install']" % stage, str(ctx.exception))

    def test_a_qualifying_purchase_marker_is_refused_without_stage_design(self):
        """Only the qualifying purchase carries the marker here, so the original-purchase half of the rule
        cannot be what refuses it."""
        for stage in (None, "install"):
            with self.subTest(stage=stage):
                request = load(FIXTURES / "request-upsell2-from-upsell1.testonly.json")
                request["eligibility"]["qualifying_purchase"] = {"slot": "upsell_1", "status": "design_marker"}
                if stage:
                    request["stage"] = stage
                with self.assertRaises(common.AdapterError) as ctx:
                    common.validate_request(request, "upsell_2")
                self.assertIn("eligibility.qualifying_purchase", str(ctx.exception))

    def test_is_design_marker_needs_both_the_design_stage_and_the_marker_status(self):
        marker = {"status": "design_marker"}
        verified = {"status": "verified"}
        cases = [("design", marker, True), (None, marker, False), ("install", marker, False),
                 ("design", verified, False), ("design", None, False), ("install", verified, False)]
        for stage, orig, expected in cases:
            with self.subTest(stage=stage, original=orig):
                request = {"eligibility": {"original_purchase": orig}}
                if stage:
                    request["stage"] = stage
                self.assertIs(common.is_design_marker(request), expected)

    def test_a_marker_request_with_a_bad_eligibility_block_is_not_verified(self):
        request = u2_marker_request("design")
        request["eligibility"]["bogus_key"] = 1
        check = common.original_purchase_check(request, {})
        self.assertTrue(check["design_marker"])
        self.assertFalse(check["verified"])
        self.assertIn("unexpected key 'bogus_key'", " ".join(check["problems"]))
        launch = {"extras": {"upsell_1": True, "downsell_1": False}, "offers": []}
        u2 = upsell2_adapter.check_u2_eligibility(request, {}, launch)
        self.assertFalse(u2["verified"])
        self.assertIn("original purchase: ", " ".join(u2["problems"]))
        self.assertIn("unexpected key 'bogus_key'", " ".join(u2["problems"]))

    def test_u2_qualifying_marker_must_be_a_marker_for_an_entry_slot(self):
        launch = {"extras": {"upsell_1": True, "downsell_1": True}, "offers": []}
        not_marker = u2_marker_request("design")
        not_marker["eligibility"]["qualifying_purchase"] = {"slot": "upsell_1", "status": "verified"}
        bad = upsell2_adapter.check_u2_eligibility(not_marker, {}, launch)
        self.assertFalse(bad["verified"])
        self.assertIn("no design-marker qualifying purchase", " ".join(bad["problems"]))
        wrong_slot = u2_marker_request("design")
        wrong_slot["eligibility"]["qualifying_purchase"] = {"slot": "main", "status": "design_marker"}
        bad = upsell2_adapter.check_u2_eligibility(wrong_slot, {}, launch)
        self.assertFalse(bad["verified"])
        self.assertIn("'main' is not upsell_1/downsell_1", " ".join(bad["problems"]))
        # an unknown slot is refused by name even when the launch record is unreadable (no enabled-slot list)
        self.assertIn("is not upsell_1/downsell_1",
                      " ".join(upsell2_adapter.check_u2_eligibility(wrong_slot, {}, None)["problems"]))

    def test_original_purchase_check_reads_the_marker_as_unverified_proof(self):
        orig = common.original_purchase_check(u1_marker_request("design"), {})
        self.assertTrue(orig["design_marker"])
        self.assertIsNone(orig["record"])  # no purchase record exists or is asserted
        plain = common.original_purchase_check(load(SKILL_DIR / "fixtures" / "request-upsell1.testonly.json"),
                                               load(FIXTURES / "journey-main-only.testonly.json"))
        self.assertNotIn("design_marker", plain)

    def test_u1_bundle_at_design_is_a_design_only_page_that_is_presented(self):
        request = u1_marker_request("design")
        bundle = upsell1_adapter.build_bundle(
            request, load(U1_COPY), {"test_only": True, "verified_purchases": []},
            copy_sha256=common.sha256_file(U1_COPY),
            copy_artifact_path="80-signature-upsell/fixtures/copy-upsell1-public.valid.json")
        result = bundle["result"]
        self.assertEqual(bundle["page_plan"]["disposition"]["action"], "present_offer")
        self.assertEqual(result["eligibility_check"]["verdict"], common.DESIGN_ONLY_VERDICT)
        self.assertIn(common.DESIGN_ONLY_VERDICT, " ".join(result["blockers"]))

    def test_u2_marker_needs_an_enabled_slot_and_a_matching_entry_context(self):
        launch = {"extras": {"upsell_1": True, "downsell_1": False}, "offers": []}
        check = upsell2_adapter.check_u2_eligibility(u2_marker_request("design"), {}, launch)
        self.assertTrue(check["verified"], check["problems"])
        self.assertEqual(check["qualifying_slot"], "upsell_1")
        wrong_ctx = u2_marker_request("design")
        wrong_ctx["entry_context"] = "from_downsell_1"
        self.assertFalse(upsell2_adapter.check_u2_eligibility(wrong_ctx, {}, launch)["verified"])
        disabled = {"extras": {"upsell_1": False, "downsell_1": True}, "offers": []}
        bad = upsell2_adapter.check_u2_eligibility(u2_marker_request("design"), {}, disabled)
        self.assertFalse(bad["verified"])
        self.assertIn("not enabled", " ".join(bad["problems"]))

    def test_a_verified_purchase_request_is_unchanged_by_the_stage_field(self):
        request = load(SKILL_DIR / "fixtures" / "request-upsell1.testonly.json")
        before = common.original_purchase_check(request, load(FIXTURES / "journey-main-only.testonly.json"))
        request = copy.deepcopy(request)
        request["stage"] = "install"
        after = common.original_purchase_check(request, load(FIXTURES / "journey-main-only.testonly.json"))
        self.assertEqual((before["verified"], before["problems"]), (after["verified"], after["problems"]))
        self.assertTrue(after["verified"])


if __name__ == "__main__":
    unittest.main()
