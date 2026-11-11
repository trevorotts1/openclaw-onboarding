"""Issue 45: the graph never asserts a guard that nothing enforces.

With no `selection_ref` the compiler emits the per-offer `offer_selected` edge guarded by `native_price_bound`,
never `allowlisted_offer_price`. A graph that does assert the allowlist guard (a record that carries a
`selection_ref`, or a hand-built graph) is judged below: the runtime check always runs, and no runtime is refused.

The `allowlisted_offer_price` guard on product_selection -> checkout tells a QC reader that the buyer's pick was
validated against an allowlist before checkout. In this release the only thing that enforces it is Skill 78's
per-offer binding plan (one native target per price choice) or a validated `selection_ref`. A package whose graph
asserts the guard with neither is refused by name (AF-LAUNCH-ROUTE-GUARD-NO-RUNTIME).
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROUTES = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROUTES.parent
sys.path.insert(0, str(ROUTES))
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "fixtures"))

import route_law  # noqa: E402
from test_routes import make_launch_record  # noqa: E402

PLAN = {"route": "per_offer_targets", "mappings": [{"offer_id": "A", "checkout_target_ref": "page-a"}]}


class SelectionGuardRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.record = make_launch_record(journey_mode="multiple_options", selection_ref="sel-1")
        self.graph = route_law.compile_route(self.record)["graph"]
        self.assertIn(route_law.SELECTION_GUARD, [e["guard"] for e in self.graph["edges"]])
        # the same record, once its selection_ref is gone, is the per-offer graph (the guard is only the
        # selection_ref's runtime); a hand-built graph can still assert it without one
        self.record = {k: v for k, v in self.record.items() if k != "selection_ref"}

    def test_the_selection_guard_with_no_runtime_is_refused_by_name(self):
        for runtime in ({}, {"selection_ref": None, "binding_plan": None}, {"selection_ref": "  "}):
            with self.subTest(runtime=runtime):
                fails = [f for f in route_law.graph_violations(self.record, self.graph, runtime=runtime)
                         if f.startswith("AF-LAUNCH-ROUTE-GUARD-NO-RUNTIME")]
                self.assertEqual(len(fails), 1, fails)
                self.assertIn("allowlisted_offer_price", fails[0])

    def test_a_selection_guard_graph_checked_with_no_runtime_is_refused(self):
        # runtime=None (the default) means NO runtime: it is refused, never skipped
        for kwargs in ({}, {"runtime": None}):
            with self.subTest(kwargs=kwargs):
                fails = route_law.graph_violations(self.record, self.graph, **kwargs)
                self.assertTrue(any(f.startswith("AF-LAUNCH-ROUTE-GUARD-NO-RUNTIME") for f in fails), fails)

    def test_a_binding_plan_that_maps_nothing_or_is_another_route_is_not_a_runtime(self):
        for plan in ({"route": "per_offer_targets", "mappings": []},
                     {"route": "platform_native_selection", "mappings": PLAN["mappings"]}, "per_offer_targets"):
            with self.subTest(plan=plan):
                self.assertTrue(any(f.startswith("AF-LAUNCH-ROUTE-GUARD-NO-RUNTIME") for f in
                                    route_law.graph_violations(self.record, self.graph, runtime={"binding_plan": plan})))

    def test_the_guard_passes_with_a_per_offer_binding_plan_or_a_selection_ref(self):
        for runtime in ({"binding_plan": PLAN}, {"selection_ref": "sel-1"}):
            self.assertEqual(route_law.selection_guard_violations(self.graph, **runtime), [])
        record = dict(self.record, selection_ref="sel-1")
        self.assertEqual(route_law.graph_violations(record, self.graph, runtime={"selection_ref": "sel-1"}), [])

    def test_a_graph_that_asserts_no_selection_guard_needs_no_runtime(self):
        record = make_launch_record(journey_mode="single_simple")
        graph = route_law.compile_route(record)["graph"]
        self.assertEqual(route_law.graph_violations(record, graph, runtime={}), [])

    def test_without_a_selection_ref_the_compiler_emits_the_per_offer_edge(self):
        graph = route_law.compile_route(copy.deepcopy(self.record))["graph"]
        edges = [e for e in graph["edges"] if e["from"].endswith("PRODUCT_SELECTION")]
        self.assertEqual([(e["event"], e["guard"]) for e in edges], [("offer_selected", "native_price_bound")])
        self.assertNotIn(route_law.SELECTION_GUARD, [e["guard"] for e in graph["edges"]])
        # it holds with no runtime at all: it asserts no guard that needs one
        self.assertEqual(route_law.graph_violations(self.record, graph), [])

    def test_a_record_with_a_selection_ref_compiles_to_the_allowlist_edge(self):
        record = dict(self.record, selection_ref="sel-1")
        graph = route_law.compile_route(record)["graph"]
        self.assertIn(("selection_validated", route_law.SELECTION_GUARD), [(e["event"], e["guard"]) for e in graph["edges"]])
        self.assertEqual(route_law.graph_violations(record, graph, runtime={"selection_ref": "sel-1"}), [])
        # the per-offer graph is not the graph that record compiles to
        per_offer = route_law.compile_route(self.record)["graph"]
        self.assertTrue(route_law.graph_violations(record, per_offer, runtime={"selection_ref": "sel-1"}))


if __name__ == "__main__":
    unittest.main()
