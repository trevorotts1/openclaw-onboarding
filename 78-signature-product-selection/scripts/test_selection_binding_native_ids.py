"""U-products-07: native ids in launch mode, 78 -> 79 adapter, approved
recommendations, decline of journey modes with no selection page."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "79-signature-order-form" / "scripts"))

from selection_core import (  # noqa: E402
    Violation, build_selection, check_invocation, validate_binding, validate_catalog,
)
from emit_binding_plan import emit_plan  # noqa: E402
from build_selection_plan import SELF_TEST_LAUNCH  # noqa: E402
from selection_flow import resolve_selection, selection_from_intent  # noqa: E402


def launch_mode(native=True, status="approved", ref="APPR-1", price_status="recommended_unapproved"):
    """A production (not test_only) launch record, as 49 writes it."""
    launch = json.loads(json.dumps(SELF_TEST_LAUNCH))
    launch.update(status=status, plan_approval_ref=ref, test_only=False)
    for offer in launch["offers"]:
        offer.pop("test_only", None)
        if not native:
            offer["native_product_id"] = None
        for price in offer["prices"]:
            price["approval_status"] = price_status
            if not native:
                price["native_price_id"] = None
    return launch


def targets_for(launch):
    return [
        {"offer_id": o["offer_id"], "price_choice_id": p["price_choice_id"],
         "native_product_id": o["native_product_id"], "native_price_id": p["native_price_id"],
         "target_ref": f"CHECKOUT-{o['offer_id']}"}
        for o in launch["offers"] for p in o["prices"]
    ]


def code_of(fn, *args, **kw):
    try:
        fn(*args, **kw)
    except Violation as v:
        return v.code
    return None


class NativeIdsAndHandoff(unittest.TestCase):
    def test_launch_selection_reaches_79_and_proceeds(self):
        launch = launch_mode()
        intent = build_selection(
            launch, offer_id="MAIN-B", price_choice_id="MAIN-B-USD",
            selected_at="2026-11-02T10:00:00Z", source_page_id="SEL-1", session_ref="opaque-1")
        validate_binding(intent, launch, expected_revision=1)
        sel = selection_from_intent(intent)
        decision = resolve_selection(
            sel, current_launch_revision=1, current_offer_revision=1,
            current_native_price_id="TEST-PRICE-B", current_amount_minor=19700, current_currency="USD",
            now="2026-11-02T10:05:00Z", expected_tenant_id=launch["tenant_id"],
            expected_location_id=launch["location_id"], expected_launch_id=launch["launch_id"])
        self.assertEqual((decision.action, decision.offer_id), ("proceed", "MAIN-B"))

    def test_null_ids_cannot_build_selection_or_binding_plan(self):
        launch = launch_mode(native=False)
        self.assertEqual(code_of(
            build_selection, launch, offer_id="MAIN-B", price_choice_id="MAIN-B-USD",
            selected_at="t", source_page_id="p", session_ref="s"), "S78-MISSING-NATIVE-MAPPING")
        self.assertEqual(code_of(emit_plan, launch, targets_for(launch), route="per_offer_targets"),
                         "S78-BINDING-INCOMPLETE")

    def test_blank_target_ids_refused_on_production(self):
        launch = launch_mode()
        targets = targets_for(launch)
        targets[0]["native_price_id"] = "  "
        # the catalog id still matches nothing blank: drift or incomplete, never a plan
        self.assertIn(code_of(emit_plan, launch, targets, route="per_offer_targets"),
                      ("S78-BINDING-INCOMPLETE", "S78-BINDING-TARGET-DRIFT"))

    def test_production_plan_with_ids_emits_and_test_only_may_be_null(self):
        launch = launch_mode()
        self.assertEqual(len(emit_plan(launch, targets_for(launch), route="per_offer_targets")["mappings"]), 2)
        test_launch = launch_mode(native=False, status="awaiting_plan_approval", ref=None, price_status="approved")
        test_launch["test_only"] = True
        self.assertEqual(len(emit_plan(test_launch, targets_for(test_launch), route="per_offer_targets")["mappings"]), 2)

    def test_adapter_refuses_foreign_or_unbound_intent(self):
        launch = launch_mode()
        intent = build_selection(
            launch, offer_id="MAIN-A", price_choice_id="MAIN-A-USD",
            selected_at="t", source_page_id="p", session_ref="s")
        with self.assertRaises(ValueError):
            selection_from_intent(dict(intent, native_price_id=None))
        with self.assertRaises(ValueError):
            selection_from_intent(dict(intent, kind="payment"))


class ApprovedRecommendation(unittest.TestCase):
    def test_plan_approval_covers_recommended_price(self):
        validate_catalog(launch_mode())  # approved + ref: passes
        validate_catalog(launch_mode(status="building"))

    def test_not_covered_without_approved_record_and_ref(self):
        for status, ref in (("awaiting_plan_approval", None), ("approved", None), ("approved", " ")):
            self.assertEqual(code_of(validate_catalog, launch_mode(status=status, ref=ref)),
                             "S78-UNAPPROVED-PRICE", (status, ref))

    def test_verifier_can_veto_the_ref(self):
        self.assertEqual(code_of(validate_catalog, launch_mode(), approval_verifier=lambda _l: False),
                         "S78-UNAPPROVED-PRICE")
        validate_catalog(launch_mode(), approval_verifier=lambda _l: True)

    def test_binding_rechecks_with_the_record(self):
        launch = launch_mode()
        intent = build_selection(launch, offer_id="MAIN-A", price_choice_id="MAIN-A-USD",
                                 selected_at="t", source_page_id="p", session_ref="s")
        launch["plan_approval_ref"] = None
        self.assertEqual(code_of(validate_binding, intent, launch, expected_revision=1), "S78-UNAPPROVED-PRICE")


class JourneyModes(unittest.TestCase):
    def three_mains(self, mode):
        launch = launch_mode()
        launch["journey_mode"] = mode
        extra = json.loads(json.dumps(launch["offers"][1]))
        extra.update(offer_id="MAIN-C", display_name="C")
        extra["prices"][0]["price_choice_id"] = "MAIN-C-USD"
        launch["offers"].append(extra)
        return launch

    def test_other_modes_decline(self):
        for mode in ("folded_levels", "free_entry"):
            launch = self.three_mains(mode)
            self.assertEqual(check_invocation(launch), "decline", mode)
            self.assertEqual(code_of(validate_catalog, launch), "S78-JOURNEY-MODE-DECLINE", mode)

    def test_supported_modes_proceed(self):
        for mode in ("multiple_options", "standalone_comparison"):
            self.assertEqual(check_invocation(self.three_mains(mode)), "proceed", mode)


if __name__ == "__main__":
    unittest.main()
