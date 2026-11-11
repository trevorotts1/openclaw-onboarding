"""Issues 70, 71 and 44 at Skill 83's checkout instances.

70  one billing translation: `trial` -> `trial_then_recurring` in the Skill 79 request, `installment` refused by name
71  the plan approval behind a recommended price is verified by the shared verifier on a live launch (not by shape)
44  Skill 78 judges the launch as it is: folded_levels is never rewritten to multiple_options
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "fixtures"))

from launcher_core import checkout_instances, image_plan, intake, launch_bridge, route  # noqa: E402
from test_checkout_instances import COMMERCIAL, FIXTURE, prepared  # noqa: E402


def with_billing(launch, billing_type):
    out = copy.deepcopy(launch)
    for offer in out["offers"]:
        if offer["slot"] == "main":
            for price in offer["prices"]:
                price["billing_type"] = billing_type
    return out


def go_live(launch, status="recommended_unapproved"):
    """A live, approved launch whose main prices are recommendations the plan approval covers."""
    out = copy.deepcopy(launch)
    out.update(test_only=False, status="approved", plan_approval_ref="APPROVAL-REF")
    for offer in out["offers"]:
        for price in offer["prices"]:
            price["approval_status"] = status
    return out


NATIVE = {f"MAIN-{x}-USD": {"native_product_id": f"prod-{x}", "native_price_id": f"price-{x}"} for x in "ABC"}


def single_prepared():
    """One main offer: one instance on the route's checkout page, no Skill 78 binding plan to judge terms."""
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["journey_mode"] = "single_simple"
    payload["offers"] = [o for o in payload["offers"] if o["offer_id"] not in ("MAIN-B", "MAIN-C")]
    for o in payload["offers"]:
        o.pop("relationships", None)
    normalized = intake.validate(payload)
    graph = route.compile_route(normalized)
    return normalized, graph, launch_bridge.to_launch_record(normalized, graph, {"image_provider": "kie",
                                                                                 "design_style": "A"})


class BillingTranslationTests(unittest.TestCase):
    def test_trial_becomes_trial_then_recurring_in_the_79_request(self):
        normalized, graph, launch = single_prepared()
        built = checkout_instances.build(normalized, graph, with_billing(launch, "trial"), COMMERCIAL)
        self.assertEqual({i["request"]["main_price"]["billing_type"] for i in built["instances"]},
                         {"trial_then_recurring"})

    def test_one_time_and_recurring_pass_through_the_shared_table(self):
        normalized, graph, launch = single_prepared()
        for billing in ("one_time", "recurring"):
            built = checkout_instances.build(normalized, graph, with_billing(launch, billing), COMMERCIAL)
            self.assertEqual({i["request"]["main_price"]["billing_type"] for i in built["instances"]}, {billing})

    def test_installment_is_refused_by_name_never_shown_as_another_type(self):
        normalized, graph, launch = single_prepared()
        with self.assertRaises(checkout_instances.CheckoutInstanceError) as ctx:
            checkout_instances.build(normalized, graph, with_billing(launch, "installment"), COMMERCIAL)
        self.assertEqual(ctx.exception.code, "AF-CHECKOUT-BILLING")


class JourneyModeIsNeverRewrittenTests(unittest.TestCase):
    def test_78_is_handed_the_launch_exactly_as_it_is(self):
        seen = {}

        class Fake:
            @staticmethod
            def emit_plan(launch, targets, *, route, allowlist=None, approval_verifier=None):
                seen.update(mode=launch["journey_mode"], route=route, verifier=approval_verifier)
                return {"route": route, "mappings": [{"offer_id": t["offer_id"], "price_choice_id": t["price_choice_id"],
                                                      "checkout_target_ref": t["target_ref"]} for t in targets]}

        normalized, graph, launch = prepared("folded_levels")
        with mock.patch.object(checkout_instances, "_s78", lambda name: Fake):
            checkout_instances.build(normalized, graph, launch, COMMERCIAL)
        self.assertEqual(seen["mode"], "folded_levels")
        self.assertEqual(seen["route"], "per_offer_targets")

    def test_78_accepts_folded_levels_for_the_per_offer_route(self):
        normalized, graph, launch = prepared("folded_levels")
        built = checkout_instances.build(normalized, graph, launch, COMMERCIAL)
        self.assertEqual(built["binding_plan"]["route"], "per_offer_targets")
        self.assertEqual(built["violations"], [])


class PlanApprovalVerifierTests(unittest.TestCase):
    def verify_stub(self, accepts=True):
        calls = []

        def verify(*args, **kwargs):
            calls.append((args, kwargs))
            if not accepts:
                raise RuntimeError("APPROVAL-NOT-FOUND")
            return {"ok": True}
        return verify, calls

    def test_a_practice_launch_stays_shape_only(self):
        normalized, _, launch = prepared("multiple_options")
        self.assertIsNone(checkout_instances._plan_approval_verifier(normalized, launch))

    def test_a_live_launch_gets_the_shared_verifier_on_its_plan_approval(self):
        normalized, _, launch = prepared("multiple_options")
        verify, calls = self.verify_stub()
        with mock.patch.object(image_plan, "_approval_verify", lambda: verify):
            verifier = checkout_instances._plan_approval_verifier(normalized, go_live(launch))
            self.assertTrue(verifier({}))
        args, kwargs = calls[0]
        self.assertEqual(args, ("APPROVAL-REF", "launch_plan_build", normalized["approval"]["hash"],
                                ["launch_plan_build"]))
        self.assertEqual(kwargs, {"test_only": False})

    def test_a_ref_that_does_not_verify_or_a_missing_verifier_covers_nothing(self):
        normalized, _, launch = prepared("multiple_options")
        verify, _ = self.verify_stub(accepts=False)
        with mock.patch.object(image_plan, "_approval_verify", lambda: verify):
            self.assertFalse(checkout_instances._plan_approval_verifier(normalized, go_live(launch))({}))
        with mock.patch.object(image_plan, "_approval_verify", side_effect=image_plan.ImagePlanError(
                "AF-LAUNCH-IMAGE-PLAN-APPROVAL", "x", "not installed")):
            self.assertFalse(checkout_instances._plan_approval_verifier(normalized, go_live(launch))({}))

    def test_a_recommended_price_is_planned_only_when_the_approval_verifies(self):
        normalized, graph, launch = prepared("multiple_options")
        live = go_live(launch)
        commercial = dict(COMMERCIAL, native=NATIVE)
        verify, calls = self.verify_stub(accepts=True)
        with mock.patch.object(image_plan, "_approval_verify", lambda: verify):
            built = checkout_instances.build(normalized, graph, live, commercial)
        self.assertEqual(built["binding_plan"]["route"], "per_offer_targets")
        self.assertTrue(calls, "the live launch's recommended prices went to the shared verifier")
        verify, _ = self.verify_stub(accepts=False)
        with mock.patch.object(image_plan, "_approval_verify", lambda: verify):
            with self.assertRaises(checkout_instances.CheckoutInstanceError) as ctx:
                checkout_instances.build(normalized, graph, live, commercial)
        self.assertIn("approved", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
