#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_launch_route.py — hermetic tests for the Signature Launch route
compiler + plan validator (Skill 49 launch mode, S49-02/S49-05/S49-06).

Run: python3 -m unittest test_launch_route   (from scripts/)
or:  python3 test_launch_route.py

No packet files, no network: fixtures are embedded. The full-profile fixture
mirrors the packet's reference example structure; equality with that example
is asserted modulo the page_id prefix (the schema leaves page_id free; this
skill's convention is launch_id-ROLE).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compile_launch_route as clr  # noqa: E402
import validate_launch_plan as vlp  # noqa: E402


def launch_fixture(mode="multiple_options", u1=True, d1=True, u2=True):
    return {"tenant_id": "TEST-TENANT", "location_id": "TEST-LOCATION",
            "launch_id": "TEST-LAUNCH", "revision": 1, "journey_mode": mode,
            "status": "awaiting_plan_approval", "brand_ref": "B",
            "brand_hash": "H", "route_graph_ref": "r", "route_graph_hash": "h",
            "plan_approval_ref": None, "offers": [],
            "extras": {"upsell_1": u1, "downsell_1": d1, "upsell_2": u2},
            "bump_enabled": False, "image_provider": "agnes",
            "source_refs": [], "test_only": True}


class CompileTests(unittest.TestCase):
    def test_full_profile_shape(self):
        g = clr.compile_route(launch_fixture())
        self.assertEqual([n["role"] for n in g["nodes"]],
                         ["landing", "product_selection", "checkout", "upsell_1",
                          "downsell_1", "upsell_2", "thank_you"])
        self.assertEqual(len(g["edges"]), 9)
        self.assertEqual(clr.validate_graph(g, launch_fixture()), [])

    def test_single_simple_has_no_selection_node(self):
        f = launch_fixture(mode="single_simple", u1=False, d1=False, u2=False)
        g = clr.compile_route(f)
        roles = [n["role"] for n in g["nodes"]]
        self.assertNotIn("product_selection", roles)
        self.assertEqual(clr.validate_graph(g, f), [])

    def test_one_canonical_u2_for_both_paths(self):
        g = clr.compile_route(launch_fixture())
        u2_ids = {n["page_id"] for n in g["nodes"] if n["role"] == "upsell_2"}
        self.assertEqual(len(u2_ids), 1)
        into_u2 = {e["from"] for e in g["edges"]
                   if e["to"] in u2_ids and e["event"] == "payment_succeeded"}
        self.assertEqual(len(into_u2), 2)  # from upsell_1 AND downsell_1

    def test_d1_decline_goes_to_thank_you(self):
        g = clr.compile_route(launch_fixture())
        role = {n["page_id"]: n["role"] for n in g["nodes"]}
        d1_decline = [e for e in g["edges"] if role[e["from"]] == "downsell_1"
                      and e["event"] == "explicit_decline"]
        self.assertEqual(role[d1_decline[0]["to"]], "thank_you")

    def test_u2_disabled_d1_paid_goes_to_thank_you(self):
        f = launch_fixture(u2=False)
        g = clr.compile_route(f)
        role = {n["page_id"]: n["role"] for n in g["nodes"]}
        d1_paid = [e for e in g["edges"] if role[e["from"]] == "downsell_1"
                   and e["event"] == "payment_succeeded"]
        self.assertEqual(role[d1_paid[0]["to"]], "thank_you")

    def test_deterministic_hash(self):
        f = launch_fixture()
        self.assertEqual(clr.graph_hash(clr.compile_route(f)),
                         clr.graph_hash(clr.compile_route(f)))

    def test_illegal_extras_refused(self):
        with self.assertRaises(clr.RouteError):
            clr.compile_route(launch_fixture(u1=False, d1=True, u2=False))

    def test_generated_cases_pass_all_profiles(self):
        for kwargs in ({}, {"mode": "single_simple", "u1": False, "d1": False,
                            "u2": False},
                       {"mode": "free_entry", "d1": False, "u2": False},
                       {"u2": False}):
            f = launch_fixture(**kwargs)
            u1, d1, u2 = clr._extras(f)
            self.assertEqual(
                clr.run_test_cases(clr.generate_test_cases(f), u1, d1, u2), [])


class ResolverLawTests(unittest.TestCase):
    def test_pending_never_traverses(self):
        for ev in ("payment_pending", "payment_failed",
                   "requires_customer_action"):
            to, after = clr.resolve_after("upsell_1", ev, frozenset({"MAIN"}),
                                          True, True, True)
            self.assertEqual((to, after), ("upsell_1", frozenset({"MAIN"})))

    def test_unverified_success_refused(self):
        with self.assertRaises(clr.RouteError):
            clr.resolve_after("checkout", "payment_succeeded",
                              frozenset({"MAIN"}), True, True, True,
                              payment_verified=False)

    def test_checkout_decline_refused(self):
        with self.assertRaises(clr.RouteError):
            clr.resolve_after("checkout", "explicit_decline",
                              frozenset({"MAIN"}), True, True, True)


class PlanValidatorTests(unittest.TestCase):
    def _offer(self, oid, slot, **kw):
        base = {"offer_id": oid, "slot": slot, "display_name": oid,
                "deliverables": ["x"], "exclusions": [],
                "entitlement_ids": [oid.lower()], "requires": [],
                "excludes": [], "native_product_id": None,
                "prices": [{"price_choice_id": f"{oid}-USD", "currency": "USD",
                            "amount_minor": 1000, "billing_type": "one_time",
                            "native_price_id": None, "schedule": [],
                            "terms_source": None,
                            "approval_status": "approved"}],
                "source_kind": "owner", "source_ref": "t", "test_only": True}
        base.update(kw)
        return base

    def test_unknown_is_never_zero(self):
        f = launch_fixture()
        f["status"] = "awaiting_plan_approval"
        o = self._offer("M", "main")
        o["prices"][0]["amount_minor"] = None
        o["prices"][0]["approval_status"] = "approved"
        f["offers"] = [o]
        self.assertNotEqual(vlp.validate_launch(f), [])

    def test_float_money_refused(self):
        f = launch_fixture()
        o = self._offer("M", "main")
        o["prices"][0]["amount_minor"] = 9.99
        f["offers"] = [o]
        self.assertNotEqual(vlp.validate_launch(f), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
