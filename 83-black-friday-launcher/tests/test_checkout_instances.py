"""CHK-10 / CHK-12: one native checkout instance per main price choice. Stdlib only."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

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


# TEST-ONLY: what the Skill 06 read-back supplies (never terms, consent or bump copy).
READBACK = {
    "native_capability_evidence_ref": COMMERCIAL["native_capability_evidence_ref"],
    "fulfillment_mapping_ref": COMMERCIAL["fulfillment_mapping_ref"],
    "failed_pending_requirements": COMMERCIAL["failed_pending_requirements"],
    "bump": {k: COMMERCIAL["bump"][k] for k in
             ("component_id", "component_version", "quantity_policy", "fulfillment_rule_ref")},
}


def with_terms(normalized):
    """TEST-ONLY intake terms and bump copy, injected after validate (independent of intake landing)."""
    out = copy.deepcopy(normalized)
    out["checkout_terms"] = {"terms_ref": "TEST-TERMS", "consent_ref": "TEST-CONSENT"}
    for o in out["offers"]:
        if o["role"] == "bump":
            o["checkout"] = {"headline": "TEST ONLY", "benefit_explanation": "TEST ONLY"}
    return out


def prepared(journey_mode: str):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["journey_mode"] = journey_mode
    normalized = intake.validate(payload)
    graph = route.compile_route(normalized)
    launch = launch_bridge.to_launch_record(normalized, graph, {"image_provider": "kie", "design_style": "A"})
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

    def test_record_takes_terms_from_intake_and_ids_from_readback(self):
        for mode in ("multiple_options", "folded_levels"):
            with self.subTest(mode=mode):
                normalized, graph, _ = prepared(mode)
                rec = checkout_instances.record(with_terms(normalized), graph, readback=READBACK)
                self.assertEqual([i["validation"]["result"] for i in rec["instances"]], ["accepted"] * 3)
                self.assertEqual(rec["realisation"], "per_offer_instances")
                self.assertEqual(rec["violations"], [])
                self.assertEqual(checkout_instances.replay_violations(rec), [])

    def test_record_without_readback_names_only_readback_facts(self):
        normalized, graph, _ = prepared("folded_levels")
        rec = checkout_instances.record(with_terms(normalized), graph)
        self.assertEqual({i["validation"]["result"] for i in rec["instances"]}, {"rejected"})
        self.assertEqual(rec["instances"][0]["missing"], ["failed_pending_requirements",
                         "fulfillment_mapping_ref", "native_capability_evidence_ref"])

    def test_readback_cannot_supply_intake_owned_terms(self):
        normalized, graph, _ = prepared("folded_levels")
        bad = [{**READBACK, "terms_ref": "X"},
               {**READBACK, "bump": {**READBACK["bump"], "headline": "X"}}]
        for rb in bad:
            with self.assertRaises(checkout_instances.CheckoutInstanceError) as ctx:
                checkout_instances.record(with_terms(normalized), graph, readback=rb)
            self.assertEqual(ctx.exception.code, "AF-LAUNCH-CHECKOUT-READBACK")

    def test_replay_catches_a_tampered_verdict(self):
        normalized, graph, _ = prepared("multiple_options")
        rec = checkout_instances.record(with_terms(normalized), graph, readback=READBACK)
        bad = copy.deepcopy(rec)
        del bad["instances"][0]["request"]["terms_ref"]  # verdict still says accepted
        self.assertTrue(any(v.startswith("AF-LAUNCH-CHECKOUT-REPLAY")
                            for v in checkout_instances.replay_violations(bad)))
        bad = copy.deepcopy(rec)
        bad["binding_plan"]["mappings"][0]["checkout_target_ref"] = "elsewhere"
        self.assertTrue(any(v.startswith("AF-LAUNCH-CHECKOUT-BINDING")
                            for v in checkout_instances.replay_violations(bad)))
        bad = copy.deepcopy(rec)
        del bad["instances"][1]["request"]["main_offer_id"]
        self.assertTrue(checkout_instances.replay_violations(bad))
        bad = copy.deepcopy(rec)
        del bad["instances"][1]["main_offer_id"]  # tampered manifest: named violation, no crash
        self.assertTrue(any(v.startswith("AF-LAUNCH-CHECKOUT-FIELD")
                            for v in checkout_instances.replay_violations(bad)))

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
        launch = launch_bridge.to_launch_record(normalized, graph, {"image_provider": "kie", "design_style": "A"})
        built = checkout_instances.build(normalized, graph, launch, COMMERCIAL)
        checkout_page = next(n["page_id"] for n in graph["nodes"] if n["role"] == "checkout")
        self.assertEqual([i["page_id"] for i in built["instances"]], [checkout_page])
        self.assertIsNone(built["binding_plan"])
        self.assertEqual(built["violations"], [])


class ValidationClockWiringTests(unittest.TestCase):
    """Skill 79's validator is handed the time exactly when the request is live, at build and at replay."""

    class Recorder:
        def __init__(self):
            self.calls = []

        def validate_request(self, *args):
            self.calls.append(args)

    def seen(self, test_only):
        normalized, graph, launch = prepared("multiple_options")
        recorder = self.Recorder()
        with mock.patch.object(checkout_instances.substrate, "s79_validate_checkout", return_value=recorder):
            native = {price["price_choice_id"]: {"native_product_id": "P-" + str(i), "native_price_id": "R-" + str(i)}
                      for i, price in enumerate(p for o in launch["offers"] for p in o["prices"])}
            built = checkout_instances.build(normalized, graph, dict(launch, test_only=test_only),
                                             dict(COMMERCIAL, native=native))
            built_calls, recorder.calls = list(recorder.calls), []
            checkout_instances.replay_violations({"instances": built["instances"], "binding_plan": built["binding_plan"]})
        return built_calls, recorder.calls

    def test_a_live_request_carries_the_clock_at_build_and_at_replay(self):
        for calls in self.seen(False):
            self.assertTrue(calls)
            for args in calls:
                self.assertEqual(len(args), 2)
                self.assertIsInstance(args[1], str)

    def test_a_practice_request_carries_no_clock_at_build_and_at_replay(self):
        for calls in self.seen(True):
            self.assertTrue(calls)
            for args in calls:
                self.assertEqual(len(args), 2)
                self.assertIsNone(args[1])


if __name__ == "__main__":
    unittest.main()
