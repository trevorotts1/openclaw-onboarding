"""CHK-06 / CHK-07 / CHK-25 / CHK-27: production-bound checkout validation,
tz-aware mapping expiry, recurring due-now, test-only purchase fixtures."""
import copy
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from quote_display import DisplayError, DisplayPrice, build_billing_display  # noqa: E402
from validate_checkout import CheckoutValidationError, validate_request  # noqa: E402

NOW = "2026-11-02T01:00:00Z"


def price(**kw):
    p = dict(price_choice_id="p", currency="USD", currency_exponent=2, amount_minor=9700,
             billing_type="one_time", native_product_id="prod_1", native_price_id="price_1",
             approval_status="approved", price_mapping_expires_at="2027-01-01T00:00:00Z")
    p.update(kw)
    return p


def bump(**kw):
    b = dict(component_id="c", component_version="1", enabled=True, offer_id="B",
             applicable_main_offer_ids=["M"], entitlement_ids=["EB"], headline="h",
             benefit_explanation="b", price=price(price_choice_id="bp", amount_minor=2700,
                                                  native_product_id="bprod_1", native_price_id="bprice_1"),
             default_selected=False, quantity_policy="fixed_1", fulfillment_rule_ref="f",
             native_product_id="bprod", native_price_id="bprice", price_mapping_expires_at=None)
    b.update(kw)
    return b


BASE = dict(
    tenant_id="t", location_id="l", launch_id="L", launch_revision=1, launch_plan_approval_ref="a",
    approved_plan_hash="h", checkout_mode="combined_single_offer", main_offer_id="M", main_price=price(),
    quantity=1, selection_ref=None, main_entitlement_ids=["EM"], previously_purchased_entitlement_ids=[],
    bump=bump(), brand_ref="b", brand_revision="r", terms_ref="t", native_capability_evidence_ref="n",
    successful_payment_next_route="r", fulfillment_mapping_ref="f", test_only=False, consent_ref="c",
    failed_pending_requirements={"failed_state_copy_ref": "x", "pending_state_copy_ref": "y",
                                 "retry_policy": "reconcile_native_records_first"})


def check(mutate, now=NOW):
    request = copy.deepcopy(BASE)
    mutate(request)
    validate_request(request, now=now)


def _post_selection(r):
    r.update(checkout_mode="post_selection", selection_ref="s")


MUTATIONS = {
    "main amount 0": lambda r: r["main_price"].update(amount_minor=0),
    "bump amount 0": lambda r: r["bump"]["price"].update(amount_minor=0),
    "main unapproved": lambda r: r["main_price"].update(approval_status="recommended_unapproved"),
    "bump unapproved": lambda r: r["bump"]["price"].update(approval_status="recommended_unapproved"),
    "main test_only status": lambda r: r["main_price"].update(approval_status="test_only"),
    "bump EUR": lambda r: r["bump"]["price"].update(currency="EUR"),
    "bump exponent": lambda r: r["bump"]["price"].update(currency_exponent=3),
    "bump not applicable": lambda r: r["bump"].update(applicable_main_offer_ids=["OTHER"]),
    "bump entitlement in main": lambda r: r["bump"].update(entitlement_ids=["EM"]),
    "bump previously purchased": lambda r: r.update(previously_purchased_entitlement_ids=["EB"]),
    "bump price native null": lambda r: r["bump"]["price"].update(native_product_id=None, native_price_id=None),
    "bump offer is main": lambda r: r["bump"].update(offer_id="M"),
    "recurring no interval": lambda r: r["main_price"].update(billing_type="recurring"),
    "trial no trial_period": lambda r: r["main_price"].update(billing_type="trial_then_recurring",
                                                              recurring_interval="month"),
    "due now over amount": lambda r: r["main_price"].update(amount_due_now_minor=99999),
    "whitespace native ids": lambda r: r["main_price"].update(native_product_id="  ", native_price_id=" "),
    "empty main entitlements": lambda r: r.update(main_entitlement_ids=[]),
    "post_selection no revision": _post_selection,
    # CHK-07 expiry rows
    "expired with offset": lambda r: r["main_price"].update(price_mapping_expires_at="2026-11-02T05:00:00+05:00"),
    "expiry junk": lambda r: r["main_price"].update(price_mapping_expires_at="never"),
    "expiry naive": lambda r: r["main_price"].update(price_mapping_expires_at="2030-01-01T00:00:00"),
    "bump expired": lambda r: r["bump"]["price"].update(price_mapping_expires_at="2026-10-01T00:00:00Z"),
}


class ProductionRefusals(unittest.TestCase):
    def test_baseline_accepted(self):
        check(lambda r: None)

    def test_every_unsafe_row_is_refused(self):
        for name, mutate in MUTATIONS.items():
            with self.subTest(name), self.assertRaises(CheckoutValidationError):
                check(mutate)

    def test_production_requires_now(self):
        with self.assertRaises(CheckoutValidationError):
            check(lambda r: None, now=None)

    def test_post_selection_with_revision_accepted(self):
        check(lambda r: (_post_selection(r), r.update(selection_revision=1)))

    def test_recurring_with_interval_accepted(self):
        check(lambda r: r["main_price"].update(billing_type="recurring", recurring_interval="month"))

    def test_disabled_bump_not_checked(self):
        check(lambda r: r.update(bump=bump(enabled=False, applicable_main_offer_ids=["OTHER"],
                                           native_product_id=None, native_price_id=None)))

    def test_test_only_still_allows_fixture_shapes(self):
        def mutate(r):
            r.update(test_only=True)
            r["main_price"].update(amount_minor=0, approval_status="test_only",
                                   native_product_id=None, native_price_id=None)
        check(mutate, now=None)

    def test_test_only_junk_expiry_still_refused(self):
        with self.assertRaises(CheckoutValidationError):
            check(lambda r: (r.update(test_only=True),
                             r["main_price"].update(price_mapping_expires_at="never")), now=None)


class RecurringDisplay(unittest.TestCase):
    def test_recurring_without_trial_bills_full_amount_today(self):
        p = DisplayPrice("R", "USD", 2, 2900, billing_type="recurring", recurring_interval="month",
                         source_verified=True)
        self.assertEqual(p.amount_due_now_minor, 2900)
        self.assertEqual(build_billing_display(p, None, False).due_now_formatted, "USD 29.00")

    def test_trial_still_defers_first_charge(self):
        p = DisplayPrice("R", "USD", 2, 2900, billing_type="trial_then_recurring",
                         recurring_interval="month", trial_period="7d", source_verified=True)
        self.assertEqual(p.amount_due_now_minor, 0)

    def test_native_readback_is_the_proof_and_must_agree(self):
        rb = {"native_price_id": "price_1", "currency": "USD", "amount_minor": 9700}
        DisplayPrice("M", "USD", 2, 9700, native_readback=rb)  # no flag needed
        with self.assertRaises(DisplayError):
            DisplayPrice("M", "USD", 2, 100, native_readback=rb, source_verified=True)
        with self.assertRaises(DisplayError):
            DisplayPrice("M", "USD", 2, 9700)


class FixturePurchasePathIsTestOnly(unittest.TestCase):
    def _import(self, module):
        # `-c` code is not under tests/ or fixtures/, so the guard must refuse.
        return subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(SKILL_ROOT / 'scripts')!r}); import {module}"],
                              capture_output=True, text=True, cwd=str(SKILL_ROOT / "tests"))

    def test_import_outside_tests_raises(self):
        for module in ("purchase_state", "purchase_event"):
            with self.subTest(module):
                result = self._import(module)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("test-only fixture", result.stderr)

    def test_import_from_tests_works(self):
        import purchase_event  # noqa: F401
        import purchase_state  # noqa: F401


if __name__ == "__main__":
    unittest.main(verbosity=2)


def test_schema_title_is_not_a_draft():
    import json
    from pathlib import Path
    schema = json.loads((Path(__file__).resolve().parents[1] / "references" / "checkout.schema.json").read_text())
    assert "DRAFT v0.1" not in schema["title"]
