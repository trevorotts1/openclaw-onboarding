"""Skill 82 renderer tests: billing by type (DTY-17), the five twin sections
(DTY-24), honest headlines (DTY-32) and currency exponents (DTY-33).

Self-contained: hand-authored TEST ONLY data, no packet reference needed.
Stdlib unittest only.
"""

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_thank_you as rt  # noqa: E402
from render_thank_you import format_amount, render_thank_you  # noqa: E402
from stamped_resolver import resolve_order_view  # noqa: E402

REPO_ROOT = SKILL_DIR.parent
TWIN = json.loads((REPO_ROOT / "71-blackceo-signature-page" / "references"
                   / "copy-specs" / "thank-you-v1.json").read_text(encoding="utf-8"))
ADAPTER_COMMON = (REPO_ROOT / "80-signature-upsell" / "components" / "adapters"
                  / "adapter_common.py")

BRAND = {"brand_name": "TEST ONLY BRAND",
         "support": {"label": "Contact TEST ONLY support", "email": "support@example.test"},
         "manage_purchase_url": "https://example.test/manage"}
IDENTITY = {"tenant_id": "T", "location_id": "L", "launch_id": "LA"}
ONE_TIME = {"billing_type": "one_time", "recurring_interval": None, "schedule": [],
            "terms_source": "TEST-ONLY"}


def item(offer_id="MAIN-A", slot="main", amount=9700, currency="USD",
         status="paid", billing=None):
    return {"offer_id": offer_id, "slot": slot, "display_name": f"TEST ONLY {offer_id}",
            "amount_minor": amount, "currency": currency, "display_status": status,
            "entitlement_ids": [f"ent-{offer_id}"], "native_line_ref": f"LINE-{offer_id}",
            "event_id": f"EVT-{offer_id}", "billing": billing or dict(ONE_TIME)}


def view(items, access=None):
    """A hand-built order view in the shape the resolver emits."""
    paid = [i for i in items if i["display_status"] == "paid"]
    return {
        "order_number": "TEST-ORDER-0001",
        "confirmation": {"status": "confirmed", "all_set": True,
                         "headline": "You are all set. Your purchase is confirmed."},
        "items": items,
        "totals": {"currency": items[0]["currency"],
                   "paid_total_minor": sum(i["amount_minor"] for i in paid),
                   "pending_total_minor": 0},
        "access_blocks": access if access is not None else [
            {"entitlement_id": f"ent-{i['offer_id']}", "offer_id": i["offer_id"],
             "slot": i["slot"], "next_action": "access",
             "delivery_url": f"https://example.test/access/{i['offer_id']}",
             "fulfillment_state": "granted"} for i in paid],
        "ctas": [{"classification": "support", "label": "Contact support",
                  "offer_id": None, "entitlement_id": None},
                 {"classification": "manage_purchase", "label": "Manage your purchase",
                  "offer_id": None, "entitlement_id": None}],
        "pending_items": [], "failed_items": [],
    }


def billing_cell(html_out, offer_id="MAIN-A"):
    row = html_out.split(f"TEST ONLY {offer_id}</th>")[1].split("</tr>")[0]
    return re.findall(r"<td>(.*?)</td>", row)[1]


def resolved(statuses, granted):
    """The real resolver over a hand-authored snapshot (statuses: offer -> status)."""
    lines, ids = [], []
    for n, (offer_id, slot) in enumerate([("MAIN-A", "main"), ("U1", "upsell_1")], 1):
        ids.append(f"EVT-{n}")
        lines.append({"native_line_ref": f"LINE-{offer_id}", "event_id": f"EVT-{n}",
                      "offer_id": offer_id, "slot": slot, "display_name": f"TEST ONLY {offer_id}",
                      "currency": "USD", "amount_minor": 9700,
                      "entitlement_ids": [f"ent-{offer_id}"],
                      "payment_status": statuses.get(offer_id, "succeeded"),
                      "billing": dict(ONE_TIME)})
    snapshot = {"schema_version": "1.0", **IDENTITY, "revision": "r1",
                "source": "verified_normalized_purchase_snapshot", "verified": True,
                "provider": "TEST-ONLY", "native_order_ref": "TEST-ORDER-0001",
                "native_transaction_ref": "TEST-TXN-1", "journey_id": "J1",
                "event_ids": ids, "line_items": lines, "evidence_ref": "TEST-ONLY",
                "test_only": True}
    fulfillment = {f"ent-{o}": {"state": "granted", "delivery_url": f"https://example.test/{o}",
                                "next_action": "access"} if o in granted
                   else {"state": "pending", "delivery_url": None, "next_action": None}
                   for o in ("MAIN-A", "U1")}
    return resolve_order_view(snapshot, fulfillment, expected_identity=IDENTITY)


class CurrencyExponentTest(unittest.TestCase):
    def test_amounts_use_each_currencys_exponent(self):
        self.assertEqual(format_amount(5000, "JPY"), "JPY 5,000")
        self.assertEqual(format_amount(12500, "KWD"), "KWD 12.500")
        self.assertEqual(format_amount(9700, "USD"), "$97.00")
        self.assertEqual(format_amount(1234567, "EUR"), "€12,345.67")

    def test_unknown_currency_or_amount_is_refused(self):
        for bad in ("XYZ", "", None, "usd", "CLF"):
            with self.assertRaises(ValueError):
                format_amount(100, bad)
        for bad in (-1, 1.5, True, "100"):
            with self.assertRaises(ValueError):
                format_amount(bad, "USD")

    def test_receipt_prints_zero_and_three_decimal_launches(self):
        self.assertIn("JPY 5,000", render_thank_you(view([item(amount=5000, currency="JPY")]), BRAND))
        self.assertIn("KWD 12.500", render_thank_you(view([item(amount=12500, currency="KWD")]), BRAND))

    @unittest.skipUnless(ADAPTER_COMMON.is_file(), "80 adapter not in this checkout")
    def test_table_matches_the_80_adapter(self):
        spec = importlib.util.spec_from_file_location("adapter_common_80", ADAPTER_COMMON)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for code, exponent in module.MINOR_UNIT_EXPONENTS.items():
            self.assertEqual(rt._CURRENCY_EXPONENTS[code], exponent, code)


class BillingByTypeTest(unittest.TestCase):
    def _cell(self, billing):
        return billing_cell(render_thank_you(view([item(billing=billing)]), BRAND))

    def test_trial_with_dated_schedule_renders_its_terms(self):
        cell = self._cell({"billing_type": "trial", "recurring_interval": None,
                           "schedule": [{"due": "2026-12-28", "amount_minor": 2700}]})
        self.assertRegex(cell, r"^Trial.* then \$27\.00 on 2026-12-28$")
        self.assertNotIn("One-time", cell)

    def test_installments_render_every_dated_row_and_interval(self):
        cell = self._cell({"billing_type": "installment", "recurring_interval": "month",
                           "schedule": [{"due": "2026-12-28", "amount_minor": 2700},
                                        {"due": "2027-01-28", "amount_minor": 2700}]})
        self.assertEqual(cell, "Installments — every month ($27.00 on 2026-12-28; "
                               "$27.00 on 2027-01-28)")

    def test_recurring_rows_show_their_due_date(self):
        cell = self._cell({"billing_type": "recurring", "recurring_interval": "month",
                           "schedule": [{"due": "2026-12-28", "amount_minor": 2700}]})
        self.assertIn("$27.00 on 2026-12-28", cell)
        self.assertNotIn("Scheduled charge", cell)

    def test_absent_terms_are_refused_never_one_time(self):
        for billing_type in ("trial", "installment", "recurring", "trial_then_recurring", "mystery"):
            with self.subTest(billing_type=billing_type):
                cell = self._cell({"billing_type": billing_type, "recurring_interval": None,
                                   "schedule": []})
                self.assertEqual(cell, "terms unavailable - contact support")

    def test_a_row_without_a_date_or_label_is_refused(self):
        cell = self._cell({"billing_type": "installment", "recurring_interval": "month",
                           "schedule": [{"amount_minor": 2700}]})
        self.assertEqual(cell, "terms unavailable - contact support")

    def test_plain_one_time_is_unchanged(self):
        self.assertEqual(self._cell(dict(ONE_TIME)), "One-time charge")


class WireframeMockupLayoutTest(unittest.TestCase):
    def test_wireframe_mockup_layout(self):
        """The built page carries the five sections of thank-you-v1.json, in order."""
        two = item("U1", "upsell_1", status="pending")
        html_out = render_thank_you(
            view([item(), two]) | {"pending_items": ["U1"]},
            dict(BRAND, hero_image={"src": "https://example.test/h.png"}))
        ids = re.findall(r'data-ty82-section="(\d)" data-ty82-section-name="([^"]*)"', html_out)
        self.assertEqual(ids, [(s["id"], rt._esc(s["name"])) for s in TWIN["sections"]])
        # section 4: 4 to 6 numbered steps
        steps = re.findall(r"<li>", html_out.split('class="ty82-steps"')[1].split("</ol>")[0])
        bounds = TWIN["sections"][3]["step_rules"]["step_count"]
        self.assertTrue(bounds["min"] <= len(steps) <= bounds["max"])
        # section 5: a signed close inside the cap, and no offer button anywhere
        note = re.search(r'ty82-close-note">(.*?)</p>', html_out).group(1)
        self.assertLessEqual(len(note), TWIN["sections"][4]["limits"][0]["max"])
        self.assertRegex(html_out, r'class="ty82-signature">TEST ONLY BRAND</p>')
        # section 3: icon cards, one image (the hero) on the whole page
        self.assertIn('<svg class="ty82-icon"', html_out)
        self.assertEqual(html_out.count("<figure"), TWIN["rules"]["max_images"])
        self.assertEqual(html_out.count("<img"), 1)

    def test_builtin_twin_values_match_the_file(self):
        self.assertEqual(rt._TWIN_FALLBACK["names"], {s["id"]: s["name"] for s in TWIN["sections"]})
        bounds = TWIN["sections"][3]["step_rules"]["step_count"]
        self.assertEqual(rt._TWIN_FALLBACK["steps"], (bounds["min"], bounds["max"]))
        self.assertEqual(rt._TWIN_FALLBACK["close_max"], TWIN["sections"][4]["limits"][0]["max"])
        self.assertEqual(rt._twin()["names"], rt._TWIN_FALLBACK["names"])

    def test_step_count_stays_in_bounds_for_every_state(self):
        failed = item("U1", "upsell_1", status="failed")
        pending = item("U2", "upsell_2", status="pending")
        for v in (view([item()]),
                  view([item(), failed, pending]) | {"pending_items": ["U2"], "failed_items": ["U1"]},
                  view([item(status="failed")], access=[]) | {"failed_items": ["MAIN-A"]}):
            count = render_thank_you(v, BRAND).split('class="ty82-steps"')[1].split("</ol>")[0].count("<li>")
            self.assertTrue(4 <= count <= 6, count)

    def test_oversize_closing_note_falls_back_to_the_default(self):
        html_out = render_thank_you(view([item()]), dict(BRAND, closing_note="x" * 171))
        self.assertNotIn("xxxx", html_out)


class HonestCopyTest(unittest.TestCase):
    def test_failed_main_never_claims_confirmed_purchases(self):
        v = resolved({"MAIN-A": "failed"}, granted={"U1"})
        self.assertIn("Your confirmed purchases", v["confirmation"]["headline"])  # resolver text
        html_out = render_thank_you(v, BRAND)
        self.assertNotIn("Your confirmed purchases", html_out)
        self.assertIn("main purchase did not go through", html_out)

    def test_pending_main_is_not_called_confirmed_either(self):
        html_out = render_thank_you(resolved({"MAIN-A": "pending"}, granted={"U1"}), BRAND)
        self.assertNotIn("Your confirmed purchases", html_out)

    def test_paid_main_keeps_the_resolver_headline(self):
        v = resolved({"U1": "failed"}, granted={"MAIN-A"})
        self.assertIn(v["confirmation"]["headline"].split(".")[0], render_thank_you(v, BRAND))

    def test_paid_item_without_access_says_access_is_being_prepared(self):
        html_out = render_thank_you(resolved({}, granted={"MAIN-A"}), BRAND)
        card = html_out.split("TEST ONLY U1</h3>")[1].split("</div>")[0]
        self.assertIn("paid, access being prepared", card)
        self.assertNotIn("<a ", card)




class DeliveryUrlSafetyTest(unittest.TestCase):
    """DTY-18: a delivery link renders only when it is an absolute https URL with a host."""

    def test_only_absolute_https_delivery_urls_are_linked(self):
        for bad in ("//attacker.example/phish", "/\\attacker.example", "http://example.test/a", "javascript:alert(1)",
                    "https://", "", None):
            self.assertIsNone(rt._https_access_url(bad), bad)
        self.assertEqual(rt._https_access_url(" https://example.test/a "), "https://example.test/a")

    def test_safe_url_refuses_protocol_relative_and_plain_http(self):
        self.assertEqual(rt._safe_url("//attacker.example/phish"), "#")
        self.assertEqual(rt._safe_url("http://example.test/a"), "#")
        self.assertEqual(rt._safe_url("https://example.test/a"), "https://example.test/a")


if __name__ == "__main__":
    unittest.main()