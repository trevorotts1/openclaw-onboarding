"""S79-06 capability matrix fixture tests. L1 only: these prove the
decision model, never a real location's capabilities."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(HERE.parent))

from capability_matrix import (CapabilityError, LocationCapabilityRecord,  # noqa: E402
                               evaluate_capabilities)


def full_record(**overrides):
    base = dict(native_checkout_present=True, order_bump_supported=True,
                coupons_supported=True, tax_shipping_native=True,
                out_of_stock_signaling=True, main_offer_in_stock=True,
                bump_in_stock=True)
    base.update(overrides)
    return LocationCapabilityRecord(**base)


class CapabilityMatrixTests(unittest.TestCase):
    def test_all_verified_renders_with_bump_offered(self):
        d = evaluate_capabilities(full_record(), bump_configured=True, coupon_planned=True)
        self.assertEqual(d.verdict, "render")
        self.assertTrue(d.submission_allowed)
        self.assertEqual(d.bump_state, "offered_unchecked")
        self.assertEqual(d.features_off, ())

    def test_native_checkout_absent_or_unknown_fails_closed(self):
        for value in (False, None):
            d = evaluate_capabilities(full_record(native_checkout_present=value),
                                      bump_configured=True)
            self.assertEqual(d.verdict, "fail_closed", value)
            self.assertFalse(d.submission_allowed)

    def test_empty_record_fails_closed(self):
        d = evaluate_capabilities(LocationCapabilityRecord(), bump_configured=True)
        self.assertEqual(d.verdict, "fail_closed")

    def test_main_out_of_stock_blocks_submission(self):
        d = evaluate_capabilities(full_record(main_offer_in_stock=False),
                                  bump_configured=True)
        self.assertEqual(d.verdict, "fail_closed")
        self.assertFalse(d.submission_allowed)
        self.assertTrue(any("out of stock" in r for r in d.reasons))

    def test_fail_closed_reasons_include_degrade_reasons(self):
        # Regression (review defect CM-1): main out of stock AND bump out
        # of stock. Verdict stays fail_closed on the main failure, and the
        # reasons must surface BOTH the fail reason and the bump degrade
        # reason computed in the same pass, fail reasons first.
        d = evaluate_capabilities(
            full_record(main_offer_in_stock=False, bump_in_stock=False),
            bump_configured=True)
        self.assertEqual(d.verdict, "fail_closed")
        self.assertFalse(d.submission_allowed)
        self.assertEqual(d.bump_state, "disabled_unavailable")
        self.assertIn("order_bump", d.features_off)
        main_idx = next(i for i, r in enumerate(d.reasons)
                        if "main offer is out of stock" in r)
        bump_idx = next(i for i, r in enumerate(d.reasons)
                        if "bump is out of stock" in r)
        self.assertLess(main_idx, bump_idx)

    def test_main_stock_unknown_fails_closed(self):
        d = evaluate_capabilities(full_record(main_offer_in_stock=None),
                                  bump_configured=False)
        self.assertEqual(d.verdict, "fail_closed")

    def test_stock_values_without_signaling_are_not_evidence(self):
        d = evaluate_capabilities(full_record(out_of_stock_signaling=None),
                                  bump_configured=False)
        self.assertEqual(d.verdict, "fail_closed")

    def test_bump_unsupported_degrades_bump_only(self):
        d = evaluate_capabilities(full_record(order_bump_supported=False),
                                  bump_configured=True)
        self.assertEqual(d.verdict, "render_degraded")
        self.assertTrue(d.submission_allowed)
        self.assertIn("order_bump", d.features_off)
        self.assertEqual(d.bump_state, "disabled_unavailable")

    def test_bump_support_unknown_degrades_bump(self):
        d = evaluate_capabilities(full_record(order_bump_supported=None),
                                  bump_configured=True)
        self.assertEqual(d.verdict, "render_degraded")
        self.assertEqual(d.bump_state, "disabled_unavailable")

    def test_bump_out_of_stock_disables_only_the_bump(self):
        d = evaluate_capabilities(full_record(bump_in_stock=False), bump_configured=True)
        self.assertEqual(d.verdict, "render_degraded")
        self.assertTrue(d.submission_allowed)
        self.assertEqual(d.bump_state, "disabled_unavailable")
        self.assertNotIn("coupons", d.features_off)

    def test_bump_stock_unknown_disables_bump(self):
        d = evaluate_capabilities(full_record(bump_in_stock=None), bump_configured=True)
        self.assertEqual(d.verdict, "render_degraded")
        self.assertEqual(d.bump_state, "disabled_unavailable")

    def test_planned_coupon_unverified_turns_coupons_off(self):
        for value in (False, None):
            d = evaluate_capabilities(full_record(coupons_supported=value),
                                      bump_configured=False, coupon_planned=True)
            self.assertEqual(d.verdict, "render_degraded", value)
            self.assertIn("coupons", d.features_off)

    def test_unplanned_coupon_unknown_is_recorded_not_blocking(self):
        d = evaluate_capabilities(full_record(coupons_supported=None),
                                  bump_configured=False, coupon_planned=False)
        self.assertEqual(d.verdict, "render")
        self.assertIn("coupons_supported", d.unverified_unused)

    def test_tax_shipping_unverified_removes_authoritative_total(self):
        d = evaluate_capabilities(full_record(tax_shipping_native=None),
                                  bump_configured=False)
        self.assertEqual(d.verdict, "render_degraded")
        self.assertTrue(d.submission_allowed)
        self.assertIn("authoritative_total_display", d.features_off)

    def test_no_bump_configured_ignores_bump_support(self):
        d = evaluate_capabilities(full_record(order_bump_supported=False),
                                  bump_configured=False)
        self.assertEqual(d.verdict, "render")
        self.assertEqual(d.bump_state, "not_configured")

    def test_garbage_capability_value_rejected(self):
        with self.assertRaises(CapabilityError):
            LocationCapabilityRecord(native_checkout_present="yes")


if __name__ == "__main__":
    unittest.main(verbosity=2)
