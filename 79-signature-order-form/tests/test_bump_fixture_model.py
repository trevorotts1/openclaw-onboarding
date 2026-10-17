"""S79 fixture tests: bump arithmetic (doc 02 s3, doc 09 s6) + route/payment
state rules (doc 02 s4, doc 09 s8, acceptance A04/A08/A09) against the
packet's 64 acceptance fixtures and the reference contract resolver.

L1 deterministic evidence only. These do NOT prove native GHL/payment
behavior (that is L3/L4, still pending).
"""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
SKILL_ROOT = HERE.parents[1]
PACKET_REF = SKILL_ROOT / "fixtures" / "packet"
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(PACKET_REF))

from bump_fixture_model import BumpConfig, BumpError, PriceChoice, initial_quote, set_bump_selected  # noqa: E402
from reference_contracts import Extras, resolve_after  # noqa: E402

LAUNCH = json.loads((PACKET_REF / "launch-example.json").read_text())
OFFERS = {o["offer_id"]: o for o in LAUNCH["offers"]}
CASES = json.loads((PACKET_REF / "acceptance-cases.json").read_text())["cases"]


def price_of(offer_id):
    p = OFFERS[offer_id]["prices"][0]
    return PriceChoice(p["price_choice_id"], p["currency"], p["amount_minor"], p["billing_type"])


def bump_config(**overrides):
    base = dict(
        component_id="TEST-BUMP-1",
        enabled=True,
        offer_id="BUMP",
        price=price_of("BUMP"),
        entitlement_ids=frozenset(OFFERS["BUMP"]["entitlement_ids"]),
        applicable_main_offer_ids=frozenset({"MAIN-A", "MAIN-B", "MAIN-C"}),
    )
    base.update(overrides)
    return BumpConfig(**base)


# Price table recomputed from the packet fixtures themselves (not hardcoded
# in the model): main + extras, so expected totals can be checked case by case.
PRICE_MINOR = {oid: o["prices"][0]["amount_minor"] for oid, o in OFFERS.items()}


class BumpArithmeticTests(unittest.TestCase):
    def test_default_unchecked_and_base_total_unchanged(self):
        q = initial_quote("MAIN-A", price_of("MAIN-A"), 1, frozenset({"base-a"}), bump_config())
        self.assertEqual(q.bump_state, "offered_unchecked")
        self.assertEqual(q.total_minor, 9700)
        self.assertEqual(q.line_items, ())

    def test_select_adds_incremental_line_and_total(self):
        cfg = bump_config()
        q = initial_quote("MAIN-A", price_of("MAIN-A"), 1, frozenset({"base-a"}), cfg)
        q2 = set_bump_selected(q, cfg, True)
        self.assertEqual(q2.line_items, (("BUMP", 2700),))
        self.assertEqual(q2.total_minor, 12400)

    def test_select_twice_is_idempotent_and_deselect_restores(self):
        cfg = bump_config()
        q = initial_quote("MAIN-B", price_of("MAIN-B"), 1, frozenset({"base-b"}), cfg)
        q = set_bump_selected(q, cfg, True)
        q = set_bump_selected(q, cfg, True)
        self.assertEqual(q.total_minor, 19700 + 2700)
        q = set_bump_selected(q, cfg, False)
        q = set_bump_selected(q, cfg, False)
        self.assertEqual(q.total_minor, 19700)
        self.assertEqual(q.bump_state, "offered_unchecked")

    def test_prechecked_config_rejected(self):
        with self.assertRaises(BumpError):
            bump_config(default_selected=True)

    def test_included_entitlement_suppresses_checkbox_and_charge(self):
        # A main tier whose entitlements already contain the bump's workbook.
        cfg = bump_config()
        q = initial_quote("MAIN-C", price_of("MAIN-C"), 1, frozenset({"base-c", "workbook"}), cfg)
        self.assertEqual(q.bump_state, "suppressed_included")
        self.assertEqual(q.total_minor, 29700)
        with self.assertRaises(BumpError):
            set_bump_selected(q, cfg, True)

    def test_inapplicable_main_offer_disables_bump_but_base_usable(self):
        cfg = bump_config(applicable_main_offer_ids=frozenset({"MAIN-A"}))
        q = initial_quote("MAIN-B", price_of("MAIN-B"), 1, frozenset({"base-b"}), cfg)
        self.assertEqual(q.bump_state, "disabled_unavailable")
        self.assertEqual(q.total_minor, 19700)

    def test_wrong_currency_rejected_at_quote_construction(self):
        # Review defect D3: mismatch must fail closed when the quote is
        # built, not only when the visitor toggles the bump.
        cfg = bump_config(price=PriceChoice("BUMP-EUR", "EUR", 2700))
        with self.assertRaises(BumpError):
            initial_quote("MAIN-A", price_of("MAIN-A"), 1, frozenset({"base-a"}), cfg)

    def test_zero_or_invalid_main_quantity_rejected(self):
        # Review defect D1: quantity 0 produced total 0 and still allowed a
        # bump charge against zero main units.
        cfg = bump_config()
        for bad in (0, -1, 1.5, True):
            with self.subTest(quantity=bad), self.assertRaises(BumpError):
                initial_quote("MAIN-A", price_of("MAIN-A"), bad, frozenset({"base-a"}), cfg)

    def test_quantity_policy_match_main(self):
        cfg = bump_config(quantity_policy="match_main_quantity")
        q = initial_quote("MAIN-A", price_of("MAIN-A"), 3, frozenset({"base-a"}), cfg)
        q = set_bump_selected(q, cfg, True)
        self.assertEqual(q.total_minor, 9700 * 3 + 2700 * 3)

    def test_recurring_bump_requires_disclosure(self):
        with self.assertRaises(BumpError):
            bump_config(price=PriceChoice("BUMP-REC", "USD", 900, "recurring"))
        ok = bump_config(price=PriceChoice("BUMP-REC", "USD", 900, "recurring"),
                         recurring_disclosure_required=True)
        self.assertEqual(ok.price.amount_minor, 900)

    def test_float_amount_rejected(self):
        with self.assertRaises(BumpError):
            PriceChoice("X", "USD", 27.0)  # type: ignore[arg-type]


class FixtureRouteAndTotalTests(unittest.TestCase):
    def test_all_64_fixture_totals_cross_check(self):
        """Cross-file fixture consistency check (review defect D2: this does
        NOT exercise the bump model 64 times; BumpArithmeticTests do that).
        For every packet case, expected_total = sum of expected purchased
        offers at fixture prices; bump contributes only when selected, and a
        bump-selected case's purchased set must include BUMP exactly once."""
        self.assertEqual(len(CASES), 64)
        for c in CASES:
            with self.subTest(case=c["case_id"]):
                expected = sum(PRICE_MINOR[o] for o in c["expected_purchased_offers"])
                self.assertEqual(expected, c["expected_total_minor_test_usd"])
                self.assertEqual("BUMP" in c["expected_purchased_offers"], c["bump_selected"])
                self.assertEqual(c["expected_purchased_offers"].count("BUMP"),
                                 1 if c["bump_selected"] else 0)

    def test_single_offer_cases_skip_product_selection(self):
        for c in CASES:
            if c["journey_mode"] == "single_simple":
                self.assertNotIn("product_selection", c["expected_page_roles"], c["case_id"])
            else:
                self.assertIn("product_selection", c["expected_page_roles"], c["case_id"])

    def test_failed_or_pending_checkout_never_traverses_paid_edge(self):
        extras = Extras()
        bought = frozenset({"MAIN-A"})
        for event in ("payment_failed", "payment_pending", "requires_customer_action"):
            with self.subTest(event=event):
                stage, after = resolve_after("checkout", event, bought, extras)
                # Reference resolver models checkout success only with verified
                # main evidence; failure/pending must not produce a paid move.
                # At checkout the helper returns the same stage for these events.
                self.assertEqual(stage, "checkout")
                self.assertEqual(after, bought)

    def test_unverified_success_claim_rejected(self):
        with self.assertRaises(ValueError):
            resolve_after("checkout", "payment_succeeded", frozenset({"MAIN-A"}), Extras(), False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
