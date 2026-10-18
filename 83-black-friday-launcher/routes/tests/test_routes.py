"""LAUNCH-02 route-invariant and adapter-wiring tests (stdlib unittest).

Run: python3 -I -m unittest discover -s <routes>/tests -v
Every assertion executes the real Skill 49/71/78/80/81/82 modules loaded by
path; none of them is stubbed.
"""
from __future__ import annotations

import copy
import inspect
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROUTES = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROUTES))

import adapters  # noqa: E402
import build_time  # noqa: E402
import route_law  # noqa: E402
import substrate  # noqa: E402


def make_launch_record(**overrides):
    record = {
        "tenant_id": "tenant-test",
        "location_id": "location-test",
        "launch_id": "L-test",
        "revision": 1,
        "journey_mode": "single_simple",
        "extras": {"upsell_1": True, "downsell_1": True, "upsell_2": True},
        "test_only": True,
    }
    record.update(overrides)
    return record


class GraphInvariantTests(unittest.TestCase):
    def test_canonical_graph_holds(self):
        record = make_launch_record()
        graph = route_law.compile_route(record)["graph"]
        self.assertEqual(route_law.graph_violations(record, graph), [])

    def test_multiple_options_graph_holds(self):
        record = make_launch_record(journey_mode="multiple_options")
        graph = route_law.compile_route(record)["graph"]
        self.assertEqual(route_law.graph_violations(record, graph), [])

    def test_checkout_decline_edge_is_refused(self):
        record = make_launch_record()
        graph = copy.deepcopy(route_law.compile_route(record)["graph"])
        graph["edges"].append({
            "from": "L-test-CHECKOUT", "event": "explicit_decline",
            "to": "L-test-THANK_YOU", "guard": "no_charge_decline"})
        violations = route_law.graph_violations(record, graph)
        self.assertTrue(any("checkout has no decline edge" in v
                            for v in violations), violations)

    def test_u1_must_follow_original_purchase(self):
        record = make_launch_record()
        graph = copy.deepcopy(route_law.compile_route(record)["graph"])
        for edge in graph["edges"]:
            if edge["from"] == "L-test-CHECKOUT" and \
                    edge["event"] == "payment_succeeded":
                edge["to"] = "L-test-THANK_YOU"
        violations = route_law.graph_violations(record, graph)
        self.assertTrue(any("U1 follows an original verified purchase" in v
                            for v in violations), violations)

    def test_d1_only_from_explicit_u1_decline(self):
        record = make_launch_record()
        graph = copy.deepcopy(route_law.compile_route(record)["graph"])
        for edge in graph["edges"]:
            if edge["to"] == "L-test-DOWNSELL_1":
                edge["from"] = "L-test-CHECKOUT"
                edge["event"] = "payment_succeeded"
                edge["guard"] = "verified_main_payment"
        violations = route_law.graph_violations(record, graph)
        self.assertTrue(any("D1 only on an explicit U1 decline" in v
                            for v in violations), violations)

    def test_u2_duplicate_entry_is_refused(self):
        record = make_launch_record()
        graph = copy.deepcopy(route_law.compile_route(record)["graph"])
        for edge in graph["edges"]:
            if edge["from"] == "L-test-DOWNSELL_1" and \
                    edge["event"] == "payment_succeeded":
                edge["to"] = "L-test-UPSELL_2_COPY"
        violations = route_law.graph_violations(record, graph)
        self.assertTrue(any("U2 must be reachable only" in v
                            for v in violations), violations)

    def test_paid_edge_guard_must_verify_payment(self):
        record = make_launch_record()
        graph = copy.deepcopy(route_law.compile_route(record)["graph"])
        for edge in graph["edges"]:
            if edge["from"] == "L-test-CHECKOUT" and \
                    edge["event"] == "payment_succeeded":
                edge["guard"] = "no_charge_decline"
        violations = route_law.graph_violations(record, graph)
        self.assertTrue(any("verified payment guard" in v
                            for v in violations), violations)

    def test_bump_cannot_be_a_route_node(self):
        record = make_launch_record()
        graph = copy.deepcopy(route_law.compile_route(record)["graph"])
        graph["nodes"].append({"page_id": "L-test-BUMP", "role": "bump"})
        violations = route_law.graph_violations(record, graph)
        self.assertTrue(any("bump" in v for v in violations), violations)

    def test_declared_hash_must_match_compiled_graph(self):
        record = make_launch_record(route_graph_hash="0" * 64)
        violations = route_law.graph_violations(record)
        self.assertTrue(any("declared route_graph_hash" in v
                            for v in violations), violations)


class BuyerRouteTests(unittest.TestCase):
    def setUp(self):
        self.record = make_launch_record()
        self.graph = route_law.compile_route(self.record)["graph"]

    def nav(self, stage, event, purchased, **kwargs):
        return route_law.navigate(self.graph, stage, event, purchased,
                                  **kwargs)

    def test_u1_follows_verified_original_purchase(self):
        result = self.nav("checkout", "payment_succeeded", {"MAIN"},
                          payment_verified=True)
        self.assertEqual(result["to_stage"], "upsell_1")

    def test_u1_refused_without_main_purchase(self):
        with self.assertRaises(route_law.RouteInvariantError):
            self.nav("checkout", "payment_succeeded", set(),
                     payment_verified=True)

    def test_unverified_success_claim_is_refused(self):
        with self.assertRaises(route_law.RouteInvariantError):
            self.nav("checkout", "payment_succeeded", {"MAIN"},
                     payment_verified=False)

    def test_entering_u1_without_purchase_is_refused(self):
        with self.assertRaises(route_law.RouteInvariantError):
            self.nav("upsell_1", "payment_pending", set())

    def test_d1_follows_explicit_u1_decline(self):
        result = self.nav("upsell_1", "explicit_decline", {"MAIN"})
        self.assertEqual(result["to_stage"], "downsell_1")

    def test_d1_entry_guard_refuses_every_non_decline(self):
        validate_downsell = substrate.s81_validate_downsell()
        base = {"main_purchased_verified": True, "u1_enabled": True,
                "d1_enabled": True, "u2_enabled": True, "u1_accepted": False}
        for event in ("payment_pending", "payment_failed",
                      "requires_customer_action", None):
            codes = validate_downsell.check_entry_guard(
                dict(base, u1_event=event))
            self.assertIn("D1-GUARD-NO-EXPLICIT-U1-DECLINE", codes, event)
        self.assertEqual(
            validate_downsell.check_entry_guard(
                dict(base, u1_event="explicit_decline")), [])
        self.assertIn(
            "D1-GUARD-U1-ALREADY-ACCEPTED",
            validate_downsell.check_entry_guard(
                dict(base, u1_event="explicit_decline", u1_accepted=True)))
        self.assertIn(
            "D1-GUARD-NO-VERIFIED-MAIN-PURCHASE",
            validate_downsell.check_entry_guard(
                {"main_purchased_verified": False,
                 "u1_event": "explicit_decline", "u1_enabled": True,
                 "d1_enabled": True, "u2_enabled": True}))
        self.assertIn(
            "D1-GUARD-D1-DISABLED",
            validate_downsell.check_entry_guard(
                dict(base, u1_event="explicit_decline", d1_enabled=False)))

    def test_u2_requires_verified_u1_or_d1_purchase(self):
        via_u1 = self.nav("upsell_2", "payment_succeeded", {"MAIN", "U1"},
                          payment_verified=True)
        self.assertEqual(via_u1["to_stage"], "thank_you")
        via_d1 = self.nav("upsell_2", "payment_succeeded", {"MAIN", "D1"},
                          payment_verified=True)
        self.assertEqual(via_d1["to_stage"], "thank_you")
        with self.assertRaises(route_law.RouteInvariantError):
            self.nav("upsell_2", "payment_succeeded", {"MAIN"},
                     payment_verified=True)
        with self.assertRaises(route_law.RouteInvariantError):
            self.nav("upsell_2", "payment_succeeded", {"MAIN", "U1"},
                     payment_verified=False)

    def test_bump_only_never_qualifies_for_u2(self):
        with self.assertRaises(route_law.RouteInvariantError):
            self.nav("upsell_2", "payment_succeeded", {"MAIN", "BUMP"},
                     payment_verified=True)
        with self.assertRaises(route_law.RouteInvariantError):
            self.nav("upsell_2", "payment_succeeded", {"BUMP"},
                     payment_verified=True)
        with self.assertRaises(route_law.RouteInvariantError):
            self.nav("checkout", "payment_succeeded", {"BUMP"},
                     payment_verified=True)

    def test_double_decline_cannot_reach_u2(self):
        after_d1_decline = self.nav("downsell_1", "explicit_decline",
                                    {"MAIN"})
        self.assertEqual(after_d1_decline["to_stage"], "thank_you")
        with self.assertRaises(route_law.RouteInvariantError):
            self.nav("upsell_2", "payment_succeeded", {"MAIN"},
                     payment_verified=True)

    def test_checkout_decline_is_not_a_route(self):
        with self.assertRaises(route_law.RouteInvariantError):
            self.nav("checkout", "explicit_decline", {"MAIN"})

    def test_pending_and_failed_payment_retain_state(self):
        cases = (
            ("checkout", {"MAIN"}),
            ("upsell_1", {"MAIN"}),
            ("downsell_1", {"MAIN"}),
            ("upsell_2", {"MAIN", "U1"}),
        )
        for stage, purchased in cases:
            for event in route_law.STAY_EVENTS:
                result = self.nav(stage, event, purchased,
                                  payment_verified=False)
                self.assertEqual(result["kind"], "stay_recoverable")
                self.assertEqual(result["to_stage"], stage)
                self.assertEqual(set(result["purchased_after"]), purchased)

    def test_abandonment_is_neither_decline_nor_purchase(self):
        result = self.nav("checkout", "tab_closed", {"MAIN"})
        self.assertEqual(result["kind"], "abandonment")
        self.assertEqual(result["to_stage"], "checkout")
        self.assertEqual(result["purchased_after"], ["MAIN"])
        self.assertFalse(any(edge["event"] in ("tab_closed", "abandoned")
                             for edge in self.graph["edges"]))

    def test_u1_and_d1_are_mutually_exclusive(self):
        with self.assertRaises(route_law.RouteInvariantError):
            self.nav("upsell_1", "payment_succeeded", {"MAIN", "D1"},
                     payment_verified=True)

    def test_u1_disabled_forces_d1_and_u2_off(self):
        with self.assertRaises(Exception):
            route_law.compile_route(
                make_launch_record(extras={"upsell_1": False, "downsell_1": True,
                               "upsell_2": True}))
        record = make_launch_record(extras={"upsell_1": False, "downsell_1": False,
                                "upsell_2": False})
        graph = route_law.compile_route(record)["graph"]
        roles = [node["role"] for node in graph["nodes"]]
        self.assertEqual(roles, ["landing", "checkout", "thank_you"])
        self.assertEqual(route_law.graph_violations(record, graph), [])

    def test_landing_navigation_matches_graph_only(self):
        result = self.nav("landing", "interest_submitted", set())
        self.assertEqual(result["to_stage"], "checkout")
        with self.assertRaises(route_law.RouteInvariantError):
            self.nav("landing", "payment_succeeded", set())

    def test_multiple_options_has_selection_page(self):
        record = make_launch_record(journey_mode="multiple_options")
        graph = route_law.compile_route(record)["graph"]
        first = route_law.navigate(graph, "landing", "interest_submitted", set())
        self.assertEqual(first["to_stage"], "product_selection")
        second = route_law.navigate(graph, "product_selection",
                                    "selection_validated", set())
        self.assertEqual(second["to_stage"], "checkout")


class BuildTimeTests(unittest.TestCase):
    def test_build_plan_takes_no_buyer_state(self):
        params = list(inspect.signature(build_time.plan).parameters)
        self.assertEqual(params, ["launch"])

    def test_every_enabled_page_is_built(self):
        record = make_launch_record(journey_mode="multiple_options")
        plan = build_time.plan(record)
        expected = substrate.compiler().expected_roles(record)
        self.assertEqual([page["role"] for page in plan["pages"]], expected)
        for page in plan["pages"]:
            self.assertFalse(page["buyer_action_required"])
        self.assertNotIn("purchased", json.dumps(plan).lower())

    def test_build_plan_is_independent_of_customer_actions(self):
        record = make_launch_record()
        self.assertEqual(build_time.plan(record), build_time.plan(record))

    def test_checkout_build_entry_is_native_not_dispatch(self):
        plan = build_time.plan(make_launch_record())
        checkout = next(page for page in plan["pages"]
                        if page["role"] == "checkout")
        self.assertFalse(checkout["build_entry"]["dispatch_adapter"])


class AdapterWiringTests(unittest.TestCase):
    def make_inputs(self, tmp: Path):
        work = tmp / "work"
        work.mkdir()
        launch_path = tmp / "launch.json"
        launch_path.write_text(json.dumps(make_launch_record()), encoding="utf-8")
        bridge = tmp / "landing-bridge-config.json"
        bridge.write_text("{}", encoding="utf-8")
        copy = {}
        journey = {}
        enrichment = {}
        for role in ("upsell_1", "upsell_2", "downsell_1"):
            for mapping, name in ((copy, "copy"), (journey, "journey"),
                                  (enrichment, "enrichment")):
                path = tmp / f"{name}-{role}.json"
                path.write_text("{}", encoding="utf-8")
                mapping[role] = path
        return {
            "work_dir": work,
            "launch_record": launch_path,
            "bridge_config": bridge,
            "author_session": "session-test",
            "copy": copy,
            "journey": journey,
            "enrichment": enrichment,
        }

    def test_all_real_entry_points_match_contract_signatures(self):
        discrepancies = adapters.signature_discrepancies()
        # The only admissible discrepancy is a recorded missing runtime
        # dependency of the real Skill 79 validator, never a signature drift.
        import importlib.util

        if importlib.util.find_spec("jsonschema") is None:
            self.assertTrue(discrepancies, "the S79 validator cannot import "
                                           "without jsonschema; it must be reported")
            self.assertEqual([d["entry"] for d in discrepancies],
                             ["s79_validate_checkout.validate_request"])
            self.assertIn("jsonschema", discrepancies[0]["error"])
        else:
            self.assertEqual(discrepancies, [], discrepancies)

    def test_known_contract_discrepancies_are_recorded(self):
        ids = {item["id"] for item in adapters.CONTRACT_DISCREPANCIES}
        self.assertEqual(ids, {"D-01", "D-02", "D-03", "D-04", "D-05",
                               "D-06"})
        for item in adapters.CONTRACT_DISCREPANCIES:
            self.assertTrue(item["contract"] and item["observed"]
                            and item["resolution"])

    def test_config_binds_real_paths_and_no_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = self.make_inputs(Path(tmp))
            config = adapters.build_dispatch_config(**inputs)
            self.assertEqual(
                set(config["adapters"]),
                {"landing", "product_selection", "upsell_1", "upsell_2",
                 "downsell_1", "thank_you"})
            self.assertNotIn("checkout", config["adapters"])
            blob = json.dumps(config)
            self.assertNotIn("/path/to", blob)
            self.assertIsNone(re.search(r"<[^>]+>", blob))
            for role, spec in config["adapters"].items():
                for part in spec["command"]:
                    if part.endswith(".py"):
                        self.assertTrue(Path(part).is_file(), part)

    def test_config_refuses_placeholder_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = self.make_inputs(Path(tmp))
            inputs["launch_record"] = "/path/to/launch.json"
            with self.assertRaises(adapters.PlaceholderRefused):
                adapters.build_dispatch_config(**inputs)

    def test_config_refuses_placeholder_author_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = self.make_inputs(Path(tmp))
            inputs["author_session"] = "<dispatch run session id>"
            with self.assertRaises(adapters.PlaceholderRefused):
                adapters.build_dispatch_config(**inputs)

    def test_config_refuses_missing_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = self.make_inputs(Path(tmp))
            inputs["copy"].pop("downsell_1")
            with self.assertRaises(adapters.AdapterError):
                adapters.build_dispatch_config(**inputs)

    def test_checkout_and_bump_are_not_dispatch_adapters(self):
        for role in ("checkout", "bump"):
            with self.assertRaises(adapters.AdapterError):
                adapters.adapter_for(role)
        self.assertFalse(
            adapters.NATIVE_SURFACES["checkout"]["dispatch_adapter"])
        self.assertFalse(adapters.NATIVE_SURFACES["bump"]["route_node"])

    def test_dispatch_role_map_is_the_real_one(self):
        self.assertEqual(
            substrate.dispatch().ROLE_SKILL,
            {"landing": 71, "product_selection": 78, "checkout": 79,
             "upsell_1": 80, "downsell_1": 81, "upsell_2": 80,
             "thank_you": 82})


class DecidedBehaviorTests(unittest.TestCase):
    def test_folded_levels_compiles_with_no_selection_node(self):
        record = make_launch_record(journey_mode="folded_levels")
        graph = route_law.compile_route(record)["graph"]
        roles = [node["role"] for node in graph["nodes"]]
        self.assertEqual(roles, ["landing", "checkout", "upsell_1",
                                 "downsell_1", "upsell_2", "thank_you"])
        self.assertEqual(route_law.graph_violations(record, graph), [])
        first = route_law.navigate(graph, "landing", "interest_submitted", set())
        self.assertEqual(first["to_stage"], "checkout")

    def test_existing_journey_modes_are_unchanged(self):
        for mode, expected in (
                ("single_simple", ["landing", "checkout", "upsell_1",
                                   "downsell_1", "upsell_2", "thank_you"]),
                ("multiple_options", ["landing", "product_selection", "checkout",
                                      "upsell_1", "downsell_1", "upsell_2",
                                      "thank_you"])):
            record = make_launch_record(journey_mode=mode)
            graph = route_law.compile_route(record)["graph"]
            self.assertEqual([n["role"] for n in graph["nodes"]], expected)
            self.assertEqual(route_law.graph_violations(record, graph), [])

    def test_checkout_is_native_and_contract_bound(self):
        surface = adapters.NATIVE_SURFACES["checkout"]
        self.assertFalse(surface["dispatch_adapter"])
        self.assertTrue(surface["route_node"])
        self.assertTrue(surface["contract"].endswith("checkout.schema.json"))
        self.assertEqual(surface["validator_entry"], "validate_request")
        with self.assertRaises(adapters.AdapterError):
            adapters.adapter_for("checkout")

    def test_s79_validator_is_a_live_binding(self):
        module_path = substrate.source(
            "79-signature-order-form/scripts/validate_checkout.py")
        self.assertTrue(module_path.is_file())
        try:
            module = substrate.s79_validate_checkout()
        except ModuleNotFoundError as exc:
            # The S79 validator imports jsonschema. An isolated interpreter
            # hides user site-packages; the missing dependency is named here
            # and by the 999 dependency package, never silently ignored.
            self.assertIn("jsonschema", str(exc))
        else:
            self.assertTrue(callable(module.validate_request))

    def test_council_is_a_planning_record_never_a_route_node(self):
        record = make_launch_record(council={"step": "council_launch_planning",
                                 "blocks_build": False, "is_permission": False})
        graph = route_law.compile_route(record)["graph"]
        roles = [node["role"] for node in graph["nodes"]]
        self.assertNotIn("council", roles)
        plan = build_time.plan(record)
        self.assertEqual(plan["council"], record["council"])

    def test_cross_sales_are_a_relationship_never_a_route_node(self):
        record = make_launch_record(cross_sales={
            "relationships": [{"offer_id": "BUMP", "included_in": ["MAIN"]}],
            "teaching": {"state": "pending"}, "route_node": False,
            "surface": "thank_you"})
        graph = route_law.compile_route(record)["graph"]
        self.assertNotIn("cross_sale", [n["role"] for n in graph["nodes"]])
        plan = build_time.plan(record)
        thank_you = next(p for p in plan["pages"] if p["role"] == "thank_you")
        self.assertEqual(thank_you["cross_sales"]["teaching"]["state"], "pending")
        self.assertEqual(thank_you["cross_sales"]["route_node"], False)


if __name__ == "__main__":
    unittest.main()
