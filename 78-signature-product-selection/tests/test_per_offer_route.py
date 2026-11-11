"""Issue 44: the `per_offer_targets` route is judged for what it is, so no consumer has to rewrite the launch.

Skill 78's journey-mode rule exists because a selection PAGE only exists for `multiple_options` (and an
explicitly requested standalone comparison). The `per_offer_targets` binding route builds no selection page:
it maps one native checkout target to each approved price choice. Skill 83 used to reach that route for a
`folded_levels` launch by rewriting the launch to `journey_mode="multiple_options"`, which defeats the rule.
Now the route is named at the boundary: any journey mode is legal for `per_offer_targets`, and the
selection-page route still declines.
"""
import copy
import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_selection_plan import SELF_TEST_LAUNCH, build_plan  # noqa: E402
from emit_binding_plan import SELF_TEST_TARGETS, emit_plan  # noqa: E402
from selection_core import Violation, check_invocation, validate_catalog  # noqa: E402
from selection_runtime import Runtime  # noqa: E402

ROUTE = "per_offer_targets"


def launch_in(mode):
    launch = copy.deepcopy(SELF_TEST_LAUNCH)
    launch["journey_mode"] = mode
    return launch


def code_of(fn, *args, **kw):
    try:
        fn(*args, **kw)
    except Violation as v:
        return v.code
    return None


class PerOfferRouteAcceptsAnyJourneyMode(unittest.TestCase):
    def test_folded_levels_proceeds_on_the_per_offer_route_and_declines_for_a_selection_page(self):
        launch = launch_in("folded_levels")
        self.assertEqual(check_invocation(launch, route=ROUTE), "proceed")
        self.assertEqual(check_invocation(launch), "decline")
        self.assertEqual(check_invocation(launch, route="platform_native_selection"), "decline")

    def test_every_non_single_mode_proceeds_per_offer_and_declines_for_a_selection_page(self):
        for mode in ("folded_levels", "free_entry", "tiered_ladder", "multiple_options", "standalone_comparison"):
            with self.subTest(mode):
                launch = launch_in(mode)
                self.assertEqual(check_invocation(launch, route=ROUTE), "proceed")
                self.assertEqual(check_invocation(launch), "proceed" if mode in (
                    "multiple_options", "standalone_comparison") else "decline")

    def test_a_single_offer_is_declined_on_every_route(self):
        single = dict(launch_in("folded_levels"), offers=SELF_TEST_LAUNCH["offers"][:1])
        self.assertEqual(check_invocation(single, route=ROUTE), "decline_single_offer")
        self.assertEqual(check_invocation(launch_in("single_simple"), route=ROUTE), "decline_single_offer")

    def test_no_main_offers_still_raises_on_the_per_offer_route(self):
        none = dict(launch_in("folded_levels"), offers=[])
        self.assertEqual(code_of(check_invocation, none, route=ROUTE), "S78-NO-MAIN-OFFERS")

    def test_catalog_validation_is_route_aware_too(self):
        launch = launch_in("folded_levels")
        self.assertEqual(code_of(validate_catalog, launch), "S78-JOURNEY-MODE-DECLINE")
        self.assertEqual(code_of(validate_catalog, launch, route="platform_native_selection"),
                         "S78-JOURNEY-MODE-DECLINE")
        validate_catalog(launch, route=ROUTE)  # no raise


class BindingPlanForAFoldedLaunch(unittest.TestCase):
    def test_per_offer_plan_is_emitted_for_folded_levels_without_touching_the_launch(self):
        launch = launch_in("folded_levels")
        before = json.dumps(launch, sort_keys=True)
        plan = emit_plan(launch, SELF_TEST_TARGETS, route=ROUTE)
        self.assertEqual(plan["route"], ROUTE)
        self.assertEqual(len(plan["mappings"]), 2)
        self.assertEqual(json.dumps(launch, sort_keys=True), before)

    def test_the_platform_selection_route_still_declines_folded_levels(self):
        self.assertEqual(code_of(emit_plan, launch_in("folded_levels"), SELF_TEST_TARGETS,
                                 route="platform_native_selection"), "S78-BINDING-INCOMPLETE")

    def test_a_single_offer_cannot_get_a_per_offer_plan(self):
        single = dict(launch_in("folded_levels"), offers=SELF_TEST_LAUNCH["offers"][:1])
        self.assertEqual(code_of(emit_plan, single, SELF_TEST_TARGETS[:1], route=ROUTE), "S78-BINDING-INCOMPLETE")

    def test_the_other_binding_refusals_still_fire_for_a_folded_launch(self):
        launch = launch_in("folded_levels")
        self.assertEqual(code_of(emit_plan, launch, SELF_TEST_TARGETS[:1], route=ROUTE), "S78-BINDING-INCOMPLETE")
        forged = [dict(SELF_TEST_TARGETS[0]), dict(SELF_TEST_TARGETS[1], native_price_id="FORGED")]
        self.assertEqual(code_of(emit_plan, launch, forged, route=ROUTE), "S78-BINDING-TARGET-DRIFT")

    def test_the_selection_page_builder_still_refuses_folded_levels(self):
        self.assertEqual(code_of(build_plan, launch_in("folded_levels")), "S78-JOURNEY-MODE-DECLINE")


class RuntimeEnvelope(unittest.TestCase):
    def test_runtime_binding_plan_action_accepts_folded_levels_per_offer(self):
        out = Runtime().handle({"action": "binding_plan", "launch": launch_in("folded_levels"),
                                "targets": SELF_TEST_TARGETS, "route": ROUTE})
        self.assertTrue(out["ok"], out)

    def test_runtime_invocation_action_is_route_aware(self):
        launch = launch_in("folded_levels")
        self.assertEqual(Runtime().handle({"action": "invocation", "launch": launch})["result"]["mode"], "decline")
        self.assertEqual(Runtime().handle({"action": "invocation", "launch": launch, "route": ROUTE})["result"]["mode"],
                         "proceed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
