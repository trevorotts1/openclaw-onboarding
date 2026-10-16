import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from selection_core import (  # noqa: E402
    Violation, build_selection, check_invocation, normalize_matrix,
    reject_query_authority, validate_binding, validate_catalog,
)
from build_selection_plan import SELF_TEST_LAUNCH, build_plan  # noqa: E402


def clone(obj):
    return json.loads(json.dumps(obj))


class InvocationTests(unittest.TestCase):
    def test_multiple_options_proceed(self):
        self.assertEqual(check_invocation(SELF_TEST_LAUNCH), "proceed")

    def test_single_simple_declines(self):
        launch = clone(SELF_TEST_LAUNCH)
        launch["journey_mode"] = "single_simple"
        launch["offers"] = launch["offers"][:1]
        self.assertEqual(check_invocation(launch), "decline_single_offer")
        self.assertEqual(build_plan(launch)["outcome"], "declined_single_offer")

    def test_one_offer_cannot_be_dressed_up(self):
        launch = clone(SELF_TEST_LAUNCH)
        launch["offers"] = launch["offers"][:1]
        self.assertEqual(check_invocation(launch), "decline_single_offer")


class CatalogTests(unittest.TestCase):
    def test_unknown_price_rejected_not_zero(self):
        launch = clone(SELF_TEST_LAUNCH)
        launch["offers"][0]["prices"][0]["amount_minor"] = None
        launch["offers"][0]["prices"][0]["approval_status"] = "unknown"
        with self.assertRaises(Violation) as ctx:
            validate_catalog(launch)
        self.assertEqual(ctx.exception.code, "S78-UNKNOWN-PRICE")

    def test_recommended_unapproved_price_not_publishable(self):
        launch = clone(SELF_TEST_LAUNCH)
        launch["offers"][0]["prices"][0]["approval_status"] = "recommended_unapproved"
        with self.assertRaises(Violation) as ctx:
            validate_catalog(launch)
        self.assertEqual(ctx.exception.code, "S78-UNAPPROVED-PRICE")

    def test_installment_schedule_must_sum_to_total(self):
        launch = clone(SELF_TEST_LAUNCH)
        price = launch["offers"][0]["prices"][0]
        price["billing_type"] = "installment"
        price["amount_minor"] = 10000
        price["schedule"] = [{"amount_minor": 5000, "due": "today"}, {"amount_minor": 4000, "due": "in 30 days"}]
        with self.assertRaises(Violation) as ctx:
            validate_catalog(launch)
        self.assertEqual(ctx.exception.code, "S78-INSTALLMENT-TOTAL-MISMATCH")
        price["schedule"][1]["amount_minor"] = 5000
        validate_catalog(launch)

    def test_five_options_supported(self):
        launch = clone(SELF_TEST_LAUNCH)
        for i in range(3, 6):
            offer = clone(launch["offers"][1])
            offer["offer_id"] = f"MAIN-{i}"
            offer["display_name"] = f"TEST ONLY {i}"
            offer["native_product_id"] = f"TEST-PROD-{i}"
            offer["prices"][0]["price_choice_id"] = f"MAIN-{i}-USD"
            offer["prices"][0]["native_price_id"] = f"TEST-PRICE-{i}"
            launch["offers"].append(offer)
        plan = build_plan(launch)
        self.assertEqual(len(plan["offers_in_order"]), 5)


class MatrixTests(unittest.TestCase):
    def test_unknown_is_never_included(self):
        matrix = normalize_matrix(SELF_TEST_LAUNCH)
        rows = {r["dimension_item"]: r["cells"] for r in matrix["rows"]}
        self.assertEqual(rows["Two private review sessions"]["MAIN-A"], "not_included")
        self.assertEqual(rows["Two private review sessions"]["MAIN-B"], "included")

    def test_exclusions_stay_material(self):
        matrix = normalize_matrix(SELF_TEST_LAUNCH)
        self.assertTrue(any(e["visibility"] == "material" for e in matrix["exclusions"]))


class HandoffTests(unittest.TestCase):
    def test_selection_preserves_native_mapping(self):
        sel = build_selection(SELF_TEST_LAUNCH, offer_id="MAIN-A", price_choice_id="MAIN-A-USD",
                              selected_at="2026-10-15T20:00:00Z", source_page_id="P", session_ref="opaque")
        validate_binding(sel, SELF_TEST_LAUNCH, expected_revision=1)
        self.assertEqual((sel["native_product_id"], sel["native_price_id"]), ("TEST-PROD-A", "TEST-PRICE-A"))

    def test_missing_native_mapping_blocks_handoff(self):
        launch = clone(SELF_TEST_LAUNCH)
        launch["offers"][0]["native_product_id"] = None
        with self.assertRaises(Violation) as ctx:
            build_selection(launch, offer_id="MAIN-A", price_choice_id="MAIN-A-USD",
                            selected_at="2026-10-15T20:00:00Z", source_page_id="P", session_ref="opaque")
        self.assertEqual(ctx.exception.code, "S78-MISSING-NATIVE-MAPPING")

    def test_query_price_is_not_authority(self):
        with self.assertRaises(Violation):
            reject_query_authority({"vip": "true"})

    def test_packet_fixture_shape(self):
        # The packet launch-example has three mains but unapproved prices and
        # no native mappings: the plan builder must refuse, never publish.
        # Location-independent resolution (CR-INT-S78-001): an explicit
        # S78_PACKET_ROOT override wins; otherwise walk ancestors looking for
        # the project packet; otherwise fall back to the vendored copy of the
        # packet example inside this skill's fixtures. The test asserts in
        # every layout - it never errors on a missing packet and never
        # silently passes (the attempt-1 defect was a silent no-op).
        import os
        packet = None
        override = os.environ.get("S78_PACKET_ROOT")
        if override:
            candidate = Path(override) / "reference" / "launch-example.json"
            if candidate.exists():
                packet = candidate
        if packet is None:
            for parent in Path(__file__).resolve().parents:
                candidate = parent / "packet" / "reference" / "launch-example.json"
                if candidate.exists():
                    packet = candidate
                    break
        if packet is None:
            packet = ROOT / "fixtures" / "packet-shape" / "launch.json"
        self.assertTrue(packet.exists(), f"no packet fixture resolvable (last tried {packet})")
        launch = json.loads(packet.read_text())
        with self.assertRaises(Violation) as ctx:
            build_plan(launch)
        self.assertEqual(ctx.exception.code, "S78-UNAPPROVED-PRICE")

    def test_offer_with_no_prices_is_not_publishable(self):
        launch = clone(SELF_TEST_LAUNCH)
        launch["offers"][0]["prices"] = []
        with self.assertRaises(Violation) as ctx:
            validate_catalog(launch)
        self.assertEqual(ctx.exception.code, "S78-UNKNOWN-PRICE")

    def test_negative_amount_rejected(self):
        launch = clone(SELF_TEST_LAUNCH)
        launch["offers"][0]["prices"][0]["amount_minor"] = -500
        with self.assertRaises(Violation) as ctx:
            validate_catalog(launch)
        self.assertEqual(ctx.exception.code, "S78-INVALID-AMOUNT")

    def test_build_selection_checks_approval_itself(self):
        launch = clone(SELF_TEST_LAUNCH)
        launch["offers"][0]["prices"][0]["approval_status"] = "recommended_unapproved"
        with self.assertRaises(Violation) as ctx:
            build_selection(launch, offer_id="MAIN-A", price_choice_id="MAIN-A-USD",
                            selected_at="2026-10-15T20:00:00Z", source_page_id="P", session_ref="opaque")
        self.assertEqual(ctx.exception.code, "S78-UNAPPROVED-PRICE")

    def test_binding_checks_location(self):
        sel = build_selection(SELF_TEST_LAUNCH, offer_id="MAIN-A", price_choice_id="MAIN-A-USD",
                              selected_at="2026-10-15T20:00:00Z", source_page_id="P", session_ref="opaque")
        sel["location_id"] = "SOMEWHERE-ELSE"
        with self.assertRaises(Violation) as ctx:
            validate_binding(sel, SELF_TEST_LAUNCH, expected_revision=1)
        self.assertEqual(ctx.exception.code, "S78-SELECTION-TENANT-MISMATCH")

    def test_currency_exponents(self):
        from selection_core import format_money
        self.assertEqual(format_money(9700, "JPY"), "¥9,700")
        self.assertEqual(format_money(9700, "USD"), "$97.00")
        self.assertEqual(format_money(12345, "KWD"), "KWD 12.345")

    def test_conditional_matrix_state_carries_condition(self):
        launch = clone(SELF_TEST_LAUNCH)
        launch["offers"][0]["conditional_deliverables"] = [
            {"item": "Group coaching calls", "condition": "when a cohort is running"}]
        launch["offers"][1]["deliverables"].append("Group coaching calls")
        matrix = normalize_matrix(launch)
        rows = {r["dimension_item"]: r for r in matrix["rows"]}
        row = rows["Group coaching calls"]
        self.assertEqual(row["cells"]["MAIN-A"], "conditional")
        self.assertEqual(row["notes"]["MAIN-A"], "when a cohort is running")
        self.assertEqual(row["cells"]["MAIN-B"], "included")

    def test_recurring_requires_interval(self):
        launch = clone(SELF_TEST_LAUNCH)
        price = launch["offers"][0]["prices"][0]
        price["billing_type"] = "recurring"
        with self.assertRaises(Violation) as ctx:
            validate_catalog(launch)
        self.assertEqual(ctx.exception.code, "S78-RECURRING-INTERVAL-MISSING")
        price["recurring_interval"] = "month"
        validate_catalog(launch)

    def test_trial_requires_terms(self):
        launch = clone(SELF_TEST_LAUNCH)
        price = launch["offers"][0]["prices"][0]
        price["billing_type"] = "trial"
        with self.assertRaises(Violation) as ctx:
            validate_catalog(launch)
        self.assertEqual(ctx.exception.code, "S78-TRIAL-TERMS-MISSING")
        price["trial_terms"] = "14 days, then the full package price"
        validate_catalog(launch)

    def test_asset_descriptor_without_owner_is_not_packaged(self):
        launch = clone(SELF_TEST_LAUNCH)
        launch["assets"] = [{"name": "selection.css"}]
        with self.assertRaises(Violation) as ctx:
            build_plan(launch)
        self.assertEqual(ctx.exception.code, "S78-ASSET-PROVENANCE")
        launch["assets"] = [{"name": "selection.css", "owner": "S78"}]
        plan = build_plan(launch)
        self.assertEqual(len(plan["asset_list"]), 1)


if __name__ == "__main__":
    unittest.main()
