"""Issue 44: the per-offer route accepts every journey mode, stated by the caller, never by rewriting the record.

Skill 83 used to call `emit_plan(dict(launch, journey_mode="multiple_options"), ...)` to get past
S78-JOURNEY-MODE-DECLINE for `folded_levels`. Now the caller states `route="per_offer_targets"` (no selection
page is built) and Skill 78 accepts any journey mode for that route; the selection-page route still declines.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_selection_plan import SELF_TEST_LAUNCH  # noqa: E402
from emit_binding_plan import SELF_TEST_TARGETS, emit_plan  # noqa: E402
from selection_core import V_JOURNEY_MODE, Violation, check_invocation, validate_catalog  # noqa: E402


def launch_in(mode):
    launch = {**SELF_TEST_LAUNCH, "journey_mode": mode}
    return launch


class PerOfferRouteJourneyTests(unittest.TestCase):
    def test_folded_levels_proceeds_for_per_offer_targets_and_declines_for_a_selection_page(self):
        launch = launch_in("folded_levels")
        self.assertEqual(check_invocation(launch, route="per_offer_targets"), "proceed")
        self.assertEqual(check_invocation(launch), "decline")
        self.assertEqual(check_invocation(launch, route="platform_native_selection"), "decline")

    def test_every_journey_mode_proceeds_for_the_per_offer_route_with_several_mains(self):
        for mode in ("multiple_options", "folded_levels", "free_entry", "standalone_comparison"):
            with self.subTest(mode=mode):
                self.assertEqual(check_invocation(launch_in(mode), route="per_offer_targets"), "proceed")

    def test_a_single_main_still_declines_whatever_the_route(self):
        launch = launch_in("folded_levels")
        launch["offers"] = launch["offers"][:1]
        self.assertEqual(check_invocation(launch, route="per_offer_targets"), "decline_single_offer")

    def test_the_catalog_check_takes_the_same_route_fact(self):
        launch = launch_in("folded_levels")
        with self.assertRaises(Violation) as ctx:
            validate_catalog(launch)
        self.assertEqual(ctx.exception.code, V_JOURNEY_MODE)
        validate_catalog(launch, route="per_offer_targets")  # no selection page, no decline

    def test_emit_plan_plans_the_unmodified_folded_levels_launch(self):
        launch = launch_in("folded_levels")
        plan = emit_plan(launch, SELF_TEST_TARGETS, route="per_offer_targets")
        self.assertEqual(plan["route"], "per_offer_targets")
        self.assertEqual(launch["journey_mode"], "folded_levels")  # the record was not rewritten to fit
        with self.assertRaises(Violation):
            emit_plan(launch, SELF_TEST_TARGETS, route="platform_native_selection")


if __name__ == "__main__":
    unittest.main()
