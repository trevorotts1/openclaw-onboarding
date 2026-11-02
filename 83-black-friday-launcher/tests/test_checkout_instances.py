"""CHK-10 / CHK-12: one native checkout instance per main price choice. Stdlib only."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import checkout_instances, intake, launch_bridge, route  # noqa: E402

FIXTURE = SKILL_ROOT / "fixtures" / "seven-figure-preneur" / "intake.json"

COMMERCIAL = {
    "terms_ref": "TEST-TERMS",
    "consent_ref": "TEST-CONSENT",
    "native_capability_evidence_ref": "TEST-CAP",
    "fulfillment_mapping_ref": "TEST-FULFILL",
    "failed_pending_requirements": {
        "failed_state_copy_ref": "TEST-FAILED-COPY",
        "pending_state_copy_ref": "TEST-PENDING-COPY",
        "retry_policy": "reconcile_native_records_first",
        "requires_customer_action_copy_ref": None,
    },
    "bump": {"component_id": "B1", "component_version": "0.1", "headline": "TEST ONLY",
             "benefit_explanation": "TEST ONLY", "quantity_policy": "fixed_1",
             "fulfillment_rule_ref": "TEST-RULE"},
}


def prepared(journey_mode: str):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["journey_mode"] = journey_mode
    normalized = intake.validate(payload)
    graph = route.compile_route(normalized)
    launch = launch_bridge.to_launch_record(normalized, graph, {"image_provider": "kie"})
    return normalized, graph, launch


class CheckoutInstanceTests(unittest.TestCase):
    def test_each_journey_mode_gets_one_accepted_instance_per_main(self):
        for mode in ("multiple_options", "folded_levels"):
            with self.subTest(mode=mode):
                normalized, graph, launch = prepared(mode)
                built = checkout_instances.build(normalized, graph, launch, COMMERCIAL)
                insts = built["instances"]
                self.assertEqual([i["main_offer_id"] for i in insts], ["MAIN-A", "MAIN-B", "MAIN-C"])
                self.assertEqual({i["checkout_mode"] for i in insts}, {"combined_single_offer"})
                self.assertEqual([i["validation"]["result"] for i in insts], ["accepted"] * 3)
                self.assertEqual(len({i["page_id"] for i in insts}), 3)
                self.assertEqual(built["violations"], [])

    def test_bump_applicability_is_per_level(self):
        # the fixture bump is included_in MAIN-B and MAIN-C: only MAIN-A sells it
        normalized, graph, launch = prepared("folded_levels")
        insts = checkout_instances.build(normalized, graph, launch, COMMERCIAL)["instances"]
        self.assertEqual([i["bump_applies"] for i in insts], [True, False, False])
        self.assertEqual(insts[0]["request"]["bump"]["applicable_main_offer_ids"], ["MAIN-A"])
        self.assertIsNone(insts[1]["request"]["bump"])

    def test_multiple_options_binding_plan_references_every_instance(self):
        normalized, graph, launch = prepared("multiple_options")
        built = checkout_instances.build(normalized, graph, launch, COMMERCIAL)
        mapped = {m["offer_id"]: m["checkout_target_ref"] for m in built["binding_plan"]["mappings"]}
        self.assertEqual(mapped, {i["main_offer_id"]: i["checkout_target_ref"]
                                  for i in built["instances"]})
        self.assertEqual(built["binding_plan"]["route"], "per_offer_targets")

    def test_dispatch_rows_carry_main_offer_and_selection_ref_per_instance(self):
        normalized, graph, launch = prepared("multiple_options")
        built = checkout_instances.build(normalized, graph, launch, COMMERCIAL)
        rows = checkout_instances.dispatch_rows(launch, graph, built, copy_profile="standard",
                                                allowed_write_target="local_only")
        by_main = {m["offer_id"]: m["checkout_target_ref"] for m in built["binding_plan"]["mappings"]}
        self.assertEqual([r["main_offer_id"] for r in rows], ["MAIN-A", "MAIN-B", "MAIN-C"])
        self.assertEqual({r["selection_ref"] for r in rows}, {None})
        self.assertEqual({r["main_offer_id"]: r["checkout_target_ref"] for r in rows}, by_main)
        self.assertEqual(len({r["request_id"] for r in rows}), 3)
        self.assertEqual({r["page_role"] for r in rows}, {"checkout"})

    def test_missing_commercial_facts_are_rejected_never_defaulted(self):
        normalized, graph, launch = prepared("folded_levels")
        built = checkout_instances.build(normalized, graph, launch, {})
        self.assertEqual({i["validation"]["result"] for i in built["instances"]}, {"rejected"})
        self.assertIn("terms_ref", built["instances"][0]["missing"])
        self.assertTrue(built["violations"])

    def test_single_simple_is_one_instance_on_the_route_checkout_page(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["journey_mode"] = "single_simple"
        payload["offers"] = [o for o in payload["offers"] if o["offer_id"] != "MAIN-B"
                             and o["offer_id"] != "MAIN-C"]
        payload["offers"] = copy.deepcopy(payload["offers"])
        for o in payload["offers"]:
            o.pop("relationships", None)
        normalized = intake.validate(payload)
        graph = route.compile_route(normalized)
        launch = launch_bridge.to_launch_record(normalized, graph, {"image_provider": "kie"})
        built = checkout_instances.build(normalized, graph, launch, COMMERCIAL)
        checkout_page = next(n["page_id"] for n in graph["nodes"] if n["role"] == "checkout")
        self.assertEqual([i["page_id"] for i in built["instances"]], [checkout_page])
        self.assertIsNone(built["binding_plan"])
        self.assertEqual(built["violations"], [])


if __name__ == "__main__":
    unittest.main()
