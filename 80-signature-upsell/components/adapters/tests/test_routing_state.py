"""S80-07 routing state tests.

Covers every doc 02 section 4 edge for upsell_1 / downsell_1 / upsell_2,
the recoverable-stay rules, the separately-recorded continue-without
decline, abandonment, the no-auto-purchase guard, the single-flight
payment guard, a differential check against the packet reference helper
(reference_contracts.resolve_after) for the events both define, and a
full cross-check of the extra-offer portion of all 64 packet acceptance
cases (visited page roles, purchased offers, integer-minor totals, and
the canonical U2 page ID).

Run: python3 -m unittest discover -s tests -v   (from adapters/)
"""

import json
import sys
import unittest
from pathlib import Path

ADAPTERS_DIR = Path(__file__).resolve().parents[1]
WORK_DIR = ADAPTERS_DIR.parent
PACKET_DIR = WORK_DIR.parents[2] / "packet"
sys.path.insert(0, str(ADAPTERS_DIR))
sys.path.insert(0, str(PACKET_DIR / "reference"))

import routing_state as rs
import reference_contracts as ref


def cfg(**kw):
    return rs.RouteConfig(**kw)


def state(stage, purchased=()):
    return rs.JourneyState(stage=stage, purchased=frozenset(purchased))


MAIN = {"MAIN-A"}


class ConfigTests(unittest.TestCase):
    def test_u1_disabled_with_d1_or_u2_enabled_rejected(self):
        with self.assertRaises(rs.RouteError):
            cfg(upsell_1=False, downsell_1=True, upsell_2=False)
        with self.assertRaises(rs.RouteError):
            cfg(upsell_1=False, downsell_1=False, upsell_2=True)

    def test_all_extras_disabled_is_valid(self):
        c = cfg(upsell_1=False, downsell_1=False, upsell_2=False)
        self.assertFalse(c.upsell_2)

    def test_non_boolean_flags_rejected(self):
        with self.assertRaises(rs.RouteError):
            cfg(upsell_1="yes")


class EdgeListTests(unittest.TestCase):
    def test_doc02_edges_present_when_all_enabled(self):
        got = {(e["from"], e["event"], e["to"]) for e in rs.edges(cfg())}
        expected = {
            ("checkout", "payment_succeeded", "upsell_1"),
            ("upsell_1", "payment_succeeded", "upsell_2"),
            ("upsell_1", "explicit_decline", "downsell_1"),
            ("downsell_1", "payment_succeeded", "upsell_2"),
            ("downsell_1", "explicit_decline", "thank_you"),
            ("upsell_2", "payment_succeeded", "thank_you"),
            ("upsell_2", "explicit_decline", "thank_you"),
        }
        self.assertTrue(expected <= got)
        # Recoverable stays for every extra stage and every stay event.
        for stage in ("upsell_1", "downsell_1", "upsell_2"):
            for ev in ("payment_pending", "payment_failed", "requires_customer_action"):
                self.assertIn((stage, ev, stage), got)

    def test_u2_disabled_creates_no_orphan_node(self):
        edge_list = rs.edges(cfg(upsell_2=False))
        self.assertFalse(any("upsell_2" in (e["from"], e["to"]) for e in edge_list))
        got = {(e["from"], e["event"], e["to"]) for e in edge_list}
        self.assertIn(("upsell_1", "payment_succeeded", "thank_you"), got)
        self.assertIn(("downsell_1", "payment_succeeded", "thank_you"), got)

    def test_all_extras_disabled_checkout_goes_straight_to_thank_you(self):
        got = {(e["from"], e["event"], e["to"]) for e in rs.edges(
            cfg(upsell_1=False, downsell_1=False, upsell_2=False)
        )}
        self.assertEqual(got, {("checkout", "payment_succeeded", "thank_you")})


class TransitionTests(unittest.TestCase):
    def test_u1_paid_reaches_same_u2(self):
        t = rs.resolve(state("upsell_1", MAIN), cfg(), "payment_succeeded",
                       payment_verified=True)
        self.assertEqual(t.to_stage, "upsell_2")
        self.assertEqual(t.to_page_id, "TEST-UPSELL_2")
        self.assertEqual(t.entry_context, "from_upsell_1")
        self.assertEqual(t.purchased_after, frozenset({"MAIN-A", "U1"}))

    def test_u1_decline_reaches_d1(self):
        t = rs.resolve(state("upsell_1", MAIN), cfg(), "explicit_decline")
        self.assertEqual(t.to_stage, "downsell_1")
        self.assertEqual(t.purchased_after, frozenset({"MAIN-A"}))

    def test_d1_paid_reaches_same_u2_page_id(self):
        via_u1 = rs.resolve(state("upsell_1", MAIN), cfg(), "payment_succeeded",
                            payment_verified=True)
        via_d1 = rs.resolve(state("downsell_1", MAIN), cfg(), "payment_succeeded",
                            payment_verified=True)
        self.assertEqual(via_d1.to_stage, "upsell_2")
        self.assertEqual(via_d1.to_page_id, via_u1.to_page_id)
        self.assertEqual(via_d1.entry_context, "from_downsell_1")
        self.assertEqual(via_d1.purchased_after, frozenset({"MAIN-A", "D1"}))

    def test_u2_paid_and_declined_both_reach_thank_you(self):
        qualified = state("upsell_2", {"MAIN-A", "U1"})
        paid = rs.resolve(qualified, cfg(), "payment_succeeded", payment_verified=True)
        self.assertEqual(paid.to_stage, "thank_you")
        self.assertEqual(paid.purchased_after, frozenset({"MAIN-A", "U1", "U2"}))
        declined = rs.resolve(qualified, cfg(), "explicit_decline")
        self.assertEqual(declined.to_stage, "thank_you")
        self.assertEqual(declined.purchased_after, frozenset({"MAIN-A", "U1"}))

    def test_u2_disabled_u1_paid_goes_to_thank_you(self):
        t = rs.resolve(state("upsell_1", MAIN), cfg(upsell_2=False),
                       "payment_succeeded", payment_verified=True)
        self.assertEqual(t.to_stage, "thank_you")

    def test_d1_disabled_u1_decline_goes_to_thank_you(self):
        t = rs.resolve(state("upsell_1", MAIN), cfg(downsell_1=False),
                       "explicit_decline")
        self.assertEqual(t.to_stage, "thank_you")

    def test_decline_both_cannot_reach_u2(self):
        s = state("upsell_1", MAIN)
        s = rs.resolve(s, cfg(), "explicit_decline").state
        self.assertEqual(s.stage, "downsell_1")
        s = rs.resolve(s, cfg(), "explicit_decline").state
        self.assertEqual(s.stage, "thank_you")
        self.assertNotIn("upsell_2", s.visited_stages())
        with self.assertRaises(rs.RouteError):
            rs.resolve(state("upsell_2", MAIN), cfg(), "explicit_decline")

    def test_bump_alone_does_not_qualify_for_u2(self):
        with self.assertRaises(rs.RouteError):
            rs.resolve(state("upsell_2", {"MAIN-A", "BUMP"}), cfg(),
                       "payment_succeeded", payment_verified=True)

    def test_direct_unqualified_u2_navigation_rejected(self):
        with self.assertRaises(rs.RouteError):
            rs.resolve(state("upsell_2", MAIN), cfg(), "explicit_decline")

    def test_extras_require_main_purchase(self):
        with self.assertRaises(rs.RouteError):
            rs.resolve(state("upsell_1", ()), cfg(), "explicit_decline")

    def test_unverified_success_is_an_error_not_a_transition(self):
        with self.assertRaises(rs.RouteError):
            rs.resolve(state("upsell_1", MAIN), cfg(), "payment_succeeded")

    def test_checkout_decline_is_not_a_paid_thank_you_path(self):
        with self.assertRaises(rs.RouteError):
            rs.resolve(state("checkout", MAIN), cfg(), "explicit_decline")

    def test_terminal_thank_you_rejects_events(self):
        with self.assertRaises(rs.RouteError):
            rs.resolve(state("thank_you", {"MAIN-A", "U1"}), cfg(), "explicit_decline")

    def test_unknown_event_rejected_without_inference(self):
        with self.assertRaises(rs.RouteError):
            rs.resolve(state("upsell_1", MAIN), cfg(), "scrolled_to_bottom")


class StayAndFailureTests(unittest.TestCase):
    def test_pending_failed_and_requires_action_stay_recoverable(self):
        for ev in ("payment_pending", "payment_failed", "requires_customer_action"):
            with self.subTest(event=ev):
                t = rs.resolve(state("upsell_1", MAIN), cfg(), ev)
                self.assertEqual(t.to_stage, "upsell_1")
                self.assertEqual(t.kind, "stay_recoverable")
                self.assertEqual(t.record["classification"],
                                 "neither_acceptance_nor_decline")
                self.assertEqual(t.purchased_after, frozenset({"MAIN-A"}))

    def test_failure_never_grants_u2_access(self):
        s = rs.resolve(state("upsell_1", MAIN), cfg(), "payment_failed").state
        self.assertEqual(s.stage, "upsell_1")
        with self.assertRaises(rs.RouteError):
            rs.resolve(state("upsell_2", s.purchased), cfg(), "explicit_decline")

    def test_continue_without_after_failure_is_a_separate_decline_record(self):
        s = state("upsell_1", MAIN)
        s = rs.resolve(s, cfg(), "payment_failed").state
        t = rs.resolve(s, cfg(), "continue_without_extra")
        self.assertEqual(t.to_stage, "downsell_1")
        self.assertEqual(t.kind, "recorded_decline")
        self.assertEqual(t.purchased_after, frozenset({"MAIN-A"}))
        kinds = [r["kind"] for r in t.state.history]
        self.assertEqual(kinds, ["stay_recoverable", "recorded_decline"])
        events = [r["event"] for r in t.state.history]
        self.assertEqual(events, ["payment_failed", "continue_without_extra"])

    def test_tab_closed_is_abandonment_not_decline(self):
        t = rs.resolve(state("downsell_1", MAIN), cfg(), "tab_closed")
        self.assertEqual(t.to_stage, "downsell_1")
        self.assertEqual(t.kind, "abandonment")
        self.assertEqual(t.record["classification"], "abandonment_not_decline")


class GuardTests(unittest.TestCase):
    def test_no_auto_purchase_triggers(self):
        for trigger in ("page_load", "scroll", "timer_expiry", "close_icon_click"):
            with self.subTest(trigger=trigger):
                with self.assertRaises(rs.RouteError):
                    rs.ensure_trigger_may_purchase(trigger)
        rs.ensure_trigger_may_purchase("cta_click")  # must not raise

    def test_single_flight_guard_blocks_double_click(self):
        guard = rs.PaymentAttemptGuard()
        guard.begin_attempt()
        with self.assertRaises(rs.RouteError):
            guard.begin_attempt()
        guard.release_attempt()
        guard.begin_attempt()  # recoverable after release
        guard.complete_attempt()
        self.assertEqual(guard.attempts, 2)

    def test_guard_rejects_auto_purchase_trigger(self):
        guard = rs.PaymentAttemptGuard()
        with self.assertRaises(rs.RouteError):
            guard.begin_attempt(trigger="timer_expiry")
        self.assertEqual(guard.state, rs.PaymentAttemptGuard.IDLE)


class ReferenceDifferentialTests(unittest.TestCase):
    """For every event both implementations define, behaviour must agree
    with reference_contracts.resolve_after (stage + purchased set)."""

    def scenarios(self):
        base = frozenset({"MAIN-A"})
        return [
            ("checkout", "payment_succeeded", base, ref.Extras(), True),
            ("checkout", "payment_succeeded", base, ref.Extras(False, False, False), True),
            ("upsell_1", "payment_succeeded", base, ref.Extras(), True),
            ("upsell_1", "payment_succeeded", base, ref.Extras(upsell_2=False), True),
            ("upsell_1", "explicit_decline", base, ref.Extras(), False),
            ("upsell_1", "explicit_decline", base, ref.Extras(downsell_1=False), False),
            ("downsell_1", "payment_succeeded", base, ref.Extras(), True),
            ("downsell_1", "explicit_decline", base, ref.Extras(), False),
            ("upsell_2", "payment_succeeded", frozenset({"MAIN-A", "U1"}), ref.Extras(), True),
            ("upsell_2", "explicit_decline", frozenset({"MAIN-A", "D1"}), ref.Extras(), False),
            ("upsell_1", "payment_failed", base, ref.Extras(), False),
            ("downsell_1", "payment_pending", base, ref.Extras(), False),
            ("upsell_2", "requires_customer_action", frozenset({"MAIN-A", "U1"}), ref.Extras(), False),
        ]

    def test_agreement_with_reference(self):
        for stage, event, bought, extras, verified in self.scenarios():
            with self.subTest(stage=stage, event=event, extras=extras):
                ref_stage, ref_bought = ref.resolve_after(
                    stage, event, bought, extras, verified
                )
                mine = rs.resolve(
                    state(stage, bought),
                    cfg(upsell_1=extras.upsell_1, downsell_1=extras.downsell_1,
                        upsell_2=extras.upsell_2),
                    event,
                    payment_verified=verified,
                )
                self.assertEqual(mine.to_stage, ref_stage)
                self.assertEqual(mine.purchased_after, ref_bought)


class Acceptance64CrossCheckTests(unittest.TestCase):
    """Replay the extra-offer portion of all 64 packet acceptance cases."""

    @classmethod
    def setUpClass(cls):
        doc = json.loads((PACKET_DIR / "reference" / "acceptance-cases.json").read_text())
        cls.cases = doc["cases"]
        launch = json.loads((PACKET_DIR / "reference" / "launch-example.json").read_text())
        cls.prices = {
            o["offer_id"]: o["prices"][0]["amount_minor"] for o in launch["offers"]
        }

    def test_all_64_cases(self):
        self.assertEqual(len(self.cases), 64)
        for case in self.cases:
            with self.subTest(case=case["case_id"]):
                self._run_case(case)

    def _run_case(self, case):
        config = cfg(upsell_2=case["u2_enabled"])
        bought = {case["main_offer"]}
        if case["bump_selected"]:
            bought.add("BUMP")
        s = state("checkout", bought)
        t = rs.resolve(s, config, "payment_succeeded", payment_verified=True)
        s = t.state
        self.assertEqual(s.stage, "upsell_1")

        label = case["decisions"]
        if label.startswith("u1_yes"):
            s = rs.resolve(s, config, "payment_succeeded",
                           payment_verified=True).state
        else:
            s = rs.resolve(s, config, "explicit_decline").state
            if s.stage == "downsell_1":
                ev = "payment_succeeded" if "d1_yes" in label else "explicit_decline"
                s = rs.resolve(s, config, ev,
                               payment_verified=(ev == "payment_succeeded")).state
        if s.stage == "upsell_2":
            t = rs.resolve(
                s, config,
                "payment_succeeded" if label.endswith("u2_yes") else "explicit_decline",
                payment_verified=label.endswith("u2_yes"),
            )
            # One canonical U2 page ID whenever U2 is actually visited.
            self.assertEqual(t.from_page_id, case["canonical_u2_page_id"])
            s = t.state

        self.assertEqual(s.stage, "thank_you")
        self.assertEqual(set(s.purchased), set(case["expected_purchased_offers"]))
        self.assertFalse({"U1", "D1"} <= set(s.purchased))

        visited = ["checkout"] + s.visited_stages()
        expected = case["expected_page_roles"]
        expected_tail = expected[expected.index("checkout"):]
        self.assertEqual(visited, expected_tail)
        if not case["u2_enabled"]:
            self.assertNotIn("upsell_2", visited)

        total = sum(self.prices[o] for o in s.purchased)
        self.assertEqual(total, case["expected_total_minor_test_usd"])


if __name__ == "__main__":
    unittest.main()
