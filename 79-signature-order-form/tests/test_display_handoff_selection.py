"""Batch #3 fixture tests: S79-02 display, S79-08 handoff, S79-04 selection.
L1 deterministic evidence only."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(HERE.parent))

from quote_display import DisplayError, DisplayPrice, audit_display, build_billing_display, format_minor  # noqa: E402
from purchase_event import EntitlementGrantor, HandoffError, build_automation_request, build_purchase_event  # noqa: E402
from purchase_state import PurchaseAttempt  # noqa: E402
from selection_flow import Selection, resolve_selection  # noqa: E402


def paid_attempt():
    a = PurchaseAttempt()
    a.apply("begin_validation")
    a.apply("submit")
    a.apply("native_paid_verified")
    return a


MAIN_LINE = {"native_line_ref": "TEST-LINE-MAIN", "offer_id": "MAIN-A", "slot": "main",
             "currency": "USD", "amount_minor": 9700, "entitlement_ids": ["base-a"]}
BUMP_LINE = {"native_line_ref": "TEST-LINE-BUMP", "offer_id": "BUMP", "slot": "bump",
             "currency": "USD", "amount_minor": 2700, "entitlement_ids": ["workbook"]}


def make_event(attempt=None, lines=None):
    return build_purchase_event(
        attempt=attempt or paid_attempt(), tenant_id="TEST-TENANT",
        location_id="TEST-LOCATION", launch_id="TEST-LAUNCH",
        native_order_ref="TEST-ORDER-1", native_transaction_ref="TEST-TXN-1",
        occurred_at="2026-10-15T16:00:00Z", received_at="2026-10-15T16:00:05Z",
        evidence_ref="TEST-EVIDENCE", line_items=lines or [MAIN_LINE, BUMP_LINE])


class DisplayTests(unittest.TestCase):
    def test_format_by_currency_exponent(self):
        self.assertEqual(format_minor(12400, "USD", 2), "USD 124.00")
        self.assertEqual(format_minor(12400, "JPY", 0), "JPY 12,400")
        self.assertEqual(format_minor(12400, "KWD", 3), "KWD 12.400")
        self.assertEqual(format_minor(5, "USD", 2), "USD 0.05")
        with self.assertRaises(DisplayError):
            format_minor(12.5, "USD", 2)

    def test_unverified_price_cannot_be_displayed(self):
        with self.assertRaises(DisplayError):
            DisplayPrice("MAIN-A", "USD", 2, 9700, source_verified=False)

    def test_display_due_now_includes_selected_bump_only(self):
        main = DisplayPrice("MAIN-A", "USD", 2, 9700, source_verified=True)
        bump = DisplayPrice("BUMP", "USD", 2, 2700, source_verified=True)
        d = build_billing_display(main, bump, True)
        self.assertEqual(d.due_now_formatted, "USD 124.00")
        d2 = build_billing_display(main, bump, False)
        self.assertEqual(d2.due_now_formatted, "USD 97.00")
        self.assertEqual(len(d2.lines), 1)

    def test_recurring_and_trial_disclosures_required_and_shown(self):
        with self.assertRaises(DisplayError):
            DisplayPrice("MAIN-R", "USD", 2, 2900, billing_type="recurring", source_verified=True)
        rec = DisplayPrice("MAIN-R", "USD", 2, 2900, billing_type="recurring",
                           recurring_interval="month", source_verified=True)
        d = build_billing_display(rec, None, False)
        self.assertIn("recurring:month", d.disclosures)
        trial = DisplayPrice("MAIN-T", "USD", 2, 4900, billing_type="trial_then_recurring",
                             recurring_interval="month", trial_period="14d", source_verified=True)
        self.assertIn("trial:14d", build_billing_display(trial, None, False).disclosures)

    def test_audit_catches_wrong_displayed_total(self):
        main = DisplayPrice("MAIN-A", "USD", 2, 9700, source_verified=True)
        bump = DisplayPrice("BUMP", "USD", 2, 2700, source_verified=True)
        good = build_billing_display(main, bump, True)
        self.assertEqual(audit_display(good, main, bump, True), [])
        tampered = build_billing_display(main, bump, False)  # bump omitted from display
        mismatches = audit_display(tampered, main, bump, True)
        self.assertTrue(mismatches)


class HandoffTests(unittest.TestCase):
    def test_event_requires_paid_attempt(self):
        a = PurchaseAttempt()
        with self.assertRaises(HandoffError):
            make_event(attempt=a)
        a.apply("begin_validation")
        a.apply("submit")
        a.apply("native_failed")
        with self.assertRaises(HandoffError):
            make_event(attempt=a)

    def test_main_plus_bump_one_event_grants_each_exactly_once(self):
        event = make_event()
        grantor = EntitlementGrantor()
        first = grantor.apply(event)
        self.assertEqual(sorted(first), ["base-a", "workbook"])
        second = grantor.apply(event)  # duplicate delivery of the same event
        self.assertEqual(second, [])
        self.assertEqual(len(grantor.grant_log), 2)

    def test_unpaid_or_forged_event_grants_nothing(self):
        event = make_event()
        forged = {**event, "payment_status": "pending"}
        with self.assertRaises(HandoffError):
            EntitlementGrantor().apply(forged)

    def test_event_validates_against_packet_schema_and_request_shape(self):
        event = make_event()
        req = build_automation_request(event=event, checkout_result_ref="TEST-RESULT")
        self.assertTrue(req["approved_behavior"]["grant_each_entitlement_exactly_once"])
        self.assertNotIn("secret", str(req).lower())
        with self.assertRaises(HandoffError):
            make_event(lines=[BUMP_LINE])  # no main line

    def test_base_only_event_when_bump_not_selected(self):
        event = make_event(lines=[MAIN_LINE])
        self.assertEqual(EntitlementGrantor().apply(event), ["base-a"])


def sel(**kw):
    base = dict(offer_id="MAIN-B", native_price_id="TEST-PRICE-B", amount_minor=19700,
                currency="USD", quantity=1, launch_revision=3, offer_revision=2,
                expires_at="2026-10-16T00:00:00Z")
    base.update(kw)
    return Selection(**base)


CURRENT = dict(current_launch_revision=3, current_offer_revision=2,
               current_native_price_id="TEST-PRICE-B", current_amount_minor=19700,
               current_currency="USD", now="2026-10-15T12:00:00Z",
               expected_tenant_id="", expected_location_id="", expected_launch_id="")


class SelectionTests(unittest.TestCase):
    def test_valid_selection_proceeds(self):
        d = resolve_selection(sel(), **CURRENT)
        self.assertEqual(d.action, "proceed")

    def test_missing_selection_is_recovery_never_default(self):
        d = resolve_selection(None, **CURRENT)
        self.assertEqual(d.action, "recovery_choice")
        self.assertIsNone(d.offer_id)

    def test_expired_selection_is_recovery(self):
        d = resolve_selection(sel(), **{**CURRENT, "now": "2026-10-17T00:00:00Z"})
        self.assertEqual(d.action, "recovery_choice")

    def test_stale_revision_requires_reconfirmation(self):
        d = resolve_selection(sel(offer_revision=1), **CURRENT)
        self.assertEqual(d.action, "reconfirm_changed_offer")
        d2 = resolve_selection(sel(launch_revision=2), **CURRENT)
        self.assertEqual(d2.action, "reconfirm_changed_offer")

    def test_changed_price_binding_requires_reconfirmation(self):
        d = resolve_selection(sel(), **{**CURRENT, "current_amount_minor": 21700})
        self.assertEqual(d.action, "reconfirm_changed_offer")
        d2 = resolve_selection(sel(), **{**CURRENT, "current_native_price_id": "OTHER-PRICE"})
        self.assertEqual(d2.action, "reconfirm_changed_offer")


if __name__ == "__main__":
    unittest.main(verbosity=2)
