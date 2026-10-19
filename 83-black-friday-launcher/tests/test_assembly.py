"""LAUNCH-02 assembly checks: one seam per choice, one route dialect, two fixtures."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = SKILL_ROOT / "fixtures"
ROUTES = SKILL_ROOT / "routes"
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(ROUTES))

from launcher_core import intake, route  # noqa: E402
from launcher_core.constants import DECIDED_IDS, SEAMS, SEAM_IDS  # noqa: E402
import build_time  # noqa: E402
import route_law  # noqa: E402
import substrate  # noqa: E402


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name / "intake.json").read_text(encoding="utf-8"))


class DecisionReconciliationTests(unittest.TestCase):
    def test_remaining_open_choices_have_unique_ids(self):
        self.assertEqual(len(SEAM_IDS), 2)
        self.assertEqual(len(set(SEAM_IDS)), 2)
        self.assertEqual(SEAM_IDS, tuple(s["id"] for s in SEAMS))

    def test_decided_choices_are_carried_by_code_and_unique(self):
        self.assertEqual(len(DECIDED_IDS), len(set(DECIDED_IDS)))
        self.assertEqual(set(DECIDED_IDS), {
            "entitlement_declaration_and_attestation",
            "council_included_in_launch_planning",
            "native_converted_and_flow_checkout_mapping",
            "verified_offer_facts_only",
            "folded_levels_journey_mode",
        })
        self.assertFalse(set(DECIDED_IDS) & set(SEAM_IDS))

    def test_registration_and_entry_name_only_canonical_ids(self):
        registration = json.loads(
            (SKILL_ROOT / "registration.json").read_text(encoding="utf-8"))
        self.assertEqual(tuple(registration["open_decisions"]), SEAM_IDS)
        metadata = json.loads(
            (SKILL_ROOT / "skill.json").read_text(encoding="utf-8"))
        self.assertEqual(tuple(metadata["open_decisions"]), SEAM_IDS)


class OneRouteDialectTests(unittest.TestCase):
    def test_launcher_route_is_the_real_compiler_graph(self):
        normalized = intake.validate(fixture("elevation"))
        graph = route.compile_route(normalized)
        record = route.launch_record(normalized)
        self.assertEqual(substrate.compiler().graph_hash(graph),
                         route_law.compile_route(record)["route_graph_hash"])
        self.assertEqual(route_law.graph_violations(record, graph), [])

    def test_launcher_route_uses_the_real_guard_vocabulary(self):
        graph = route.compile_route(intake.validate(fixture("elevation")))
        guards = {edge["guard"] for edge in graph["edges"]}
        self.assertIn("verified_main_payment", guards)
        self.assertIn("verified_native_contact_submit", guards)
        self.assertIn("allowlisted_offer_price", guards)
        self.assertNotIn("upsell_1_enabled", guards)


class ElevationFixtureTests(unittest.TestCase):
    def test_three_distinct_priced_levels_and_a_separate_selection_page(self):
        normalized = intake.validate(fixture("elevation"))
        mains = [o for o in normalized["offers"] if o["role"] == "main"]
        self.assertEqual(len(mains), 3)
        self.assertEqual(len({o["offer_id"] for o in mains}), 3)
        self.assertTrue(all(o["price"]["amount_minor"] > 0 for o in mains))
        graph = route.compile_route(normalized)
        self.assertIn("product_selection", [n["role"] for n in graph["nodes"]])

    def test_every_enabled_page_builds_with_no_customer_action(self):
        normalized = intake.validate(fixture("elevation"))
        record = route.launch_record(normalized)
        plan = build_time.plan(record)
        graph = route_law.compile_route(record)["graph"]
        self.assertEqual([p["role"] for p in plan["pages"]],
                         [n["role"] for n in graph["nodes"]])
        self.assertTrue(all(p["buyer_action_required"] is False
                            for p in plan["pages"]))
        checkout = next(p for p in plan["pages"] if p["role"] == "checkout")
        self.assertIs(checkout["build_entry"]["dispatch_adapter"], False)


class SevenFigurePreneurFixtureTests(unittest.TestCase):
    def test_three_distinct_offers_are_never_relabelled_single_or_no_price(self):
        payload = fixture("seven-figure-preneur")
        mains = [o for o in payload["offers"] if o["role"] == "main"]
        self.assertEqual(len(mains), 3)
        self.assertEqual(len({o["offer_id"] for o in mains}), 3)
        self.assertTrue(all(o["price"]["amount_minor"] > 0
                            for o in payload["offers"]))
        self.assertNotIn(payload["journey_mode"],
                         ("single_simple", "multiple_options"))

    def test_folded_shape_compiles_without_a_selection_page(self):
        payload = fixture("seven-figure-preneur")
        self.assertEqual(payload["journey_mode"], "folded_levels")
        normalized = intake.validate(payload)
        graph = route.compile_route(normalized)
        roles = [n["role"] for n in graph["nodes"]]
        self.assertNotIn("product_selection", roles)
        self.assertEqual(roles[0], "landing")
        self.assertEqual(roles[1], "checkout")
        record = route.launch_record(normalized)
        self.assertEqual(route_law.graph_violations(record, graph), [])
        self.assertEqual(substrate.compiler().expected_roles(record), roles)

    def test_folded_shape_is_supported_by_the_real_compiler(self):
        payload = fixture("seven-figure-preneur")
        graph = substrate.compiler().compile_route({
            "tenant_id": payload["tenant_id"],
            "location_id": payload["location_id"],
            "launch_id": payload["launch_id"],
            "revision": payload["revision"],
            "journey_mode": payload["journey_mode"],
            "extras": {"upsell_1": True, "downsell_1": True,
                       "upsell_2": True},
            "test_only": True,
        })
        self.assertNotIn("product_selection", [n["role"] for n in graph["nodes"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
