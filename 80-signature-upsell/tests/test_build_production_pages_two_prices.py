"""RFX-015: one upsell offer approved at two prices (monthly AND yearly) sells both on one page.

A membership approved at 8900 a month and 50000 a year used to be unsellable on one Upsell 2 page:
the builder read ``prices[0]`` and ``_require_identical_cta`` allowed exactly one guarded native
action. These tests pin the repair: two approved price choices render two guarded native accept
actions (one per choice, each with its own native price, action ref and exact disclosure), in the
order the copy's ``lead_price_choice_id`` names (default: the record's first price), with ONE
decline; three choices, an installment choice or two choices sharing a native price refuse;
a single-price offer renders exactly as before.

Run from the skill root:  python3 -m unittest discover -s tests
"""

import copy
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO = SKILL.parent
PAGES = SKILL / "components" / "pages"
FIXTURES = SKILL / "components" / "80-signature-upsell" / "fixtures"
FAMILY = "order_upsell_v2_funnel"


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _import(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(PAGES))
sys.path.insert(0, str(REPO / "49-signature-funnel" / "scripts"))
bpp = _import("build_production_pages_two_prices", PAGES / "build_production_pages.py")
compiler = _import("compile_launch_route_two_prices",
                   REPO / "49-signature-funnel" / "scripts" / "compile_launch_route.py")


def _price(pid, amount, interval, native, status="provided", billing="recurring"):
    return {"price_choice_id": pid, "currency": "USD", "amount_minor": amount,
            "billing_type": billing, "recurring_interval": interval,
            "native_price_id": native, "approval_status": status,
            "schedule": [{"amount_minor": amount, "due": f"every {interval} until cancelled"}]}


MONTH = _price("TEST-ONLY-U2-USD", 8900, "month", "TEST-ONLY-NP-MONTH")
YEAR = _price("TEST-ONLY-U2-USD-YEAR", 50000, "year", "TEST-ONLY-NP-YEAR")


class TwoPriceChoicesOnOneUpsellPage(unittest.TestCase):
    def setUp(self):
        self.launch = _load(REPO / "49-signature-funnel" / "scripts" / "fixtures"
                            / "finalized-launch-record-signature-launch-l4.json")
        self.launch["u2_entry_context"] = "from_upsell_1"
        self.graph = compiler.compile_route(self.launch)
        self.copies = {"upsell_1": _load(FIXTURES / "copy-upsell1-public.valid.json"),
                       "upsell_2": _load(FIXTURES / "copy-upsell2-public.valid.json")}
        self.d1 = _load(REPO / "81-signature-downsell" / "fixtures" / "valid-downsell-page.json")

    def _with_u2_prices(self, *prices):
        launch = copy.deepcopy(self.launch)
        next(o for o in launch["offers"] if o["slot"] == "upsell_2")["prices"] = [
            copy.deepcopy(p) for p in prices]
        return launch

    def _build(self, launch, copies=None):
        return bpp.build(launch, self.graph, FAMILY, copies or self.copies, self.d1, {})

    @staticmethod
    def _u2(built):
        return built["pages"]["upsell_2"], next(
            r for r in built["manifest"]["pages"] if r["slot"] == "upsell_2")

    def test_monthly_and_yearly_render_two_guarded_accept_actions_and_one_decline(self):
        html, row = self._u2(self._build(self._with_u2_prices(MONTH, YEAR)))
        buttons = re.findall(r"<button([^>]*)>", html)
        self.assertEqual(len(buttons), 16, "eight sections, two accept actions each")
        self.assertTrue(all('data-native-action="one_click_purchase"' in b for b in buttons))
        self.assertTrue(all("href" not in b for b in buttons), "a purchase action never navigates")
        self.assertEqual(sorted(set(re.findall(r'data-price-id="([^"]+)"', html))),
                         ["TEST-ONLY-NP-MONTH", "TEST-ONLY-NP-YEAR"])
        self.assertEqual(sorted(set(re.findall(r'data-action-ref="([^"]+)"', html))),
                         ["native-one-click:TEST-ONLY-U2.TEST-ONLY-U2-USD",
                          "native-one-click:TEST-ONLY-U2.TEST-ONLY-U2-USD-YEAR"])
        self.assertEqual(html.count('class="decline"'), 1, "one decline, never one per price")
        self.assertEqual(html.count('data-charges="false"'), 1)
        self.assertEqual(html.count('id="primary-cta"'), 1, "one primary action")
        acts = row["accept_actions"]
        self.assertEqual([a["price_choice_id"] for a in acts],
                         ["TEST-ONLY-U2-USD", "TEST-ONLY-U2-USD-YEAR"], "lead defaults to the first price")
        self.assertIn("$89.00", acts[0]["disclosure"])
        self.assertIn("every month", acts[0]["disclosure"])
        self.assertIn("$500.00", acts[1]["disclosure"])
        self.assertIn("every year", acts[1]["disclosure"])
        self.assertNotIn("$500.00", acts[0]["disclosure"])
        for a in acts:  # each disclosure sits beside its own button, never the other price's
            self.assertIn(a["disclosure"], html)
        self.assertEqual((row["native_price_id"], row["disclosure"]),
                         (acts[0]["native_price_id"], acts[0]["disclosure"]))

    def test_the_copys_lead_field_puts_the_yearly_price_first(self):
        copies = copy.deepcopy(self.copies)
        copies["upsell_2"]["lead_price_choice_id"] = "TEST-ONLY-U2-USD-YEAR"
        html, row = self._u2(self._build(self._with_u2_prices(MONTH, YEAR), copies))
        self.assertEqual([a["price_choice_id"] for a in row["accept_actions"]],
                         ["TEST-ONLY-U2-USD-YEAR", "TEST-ONLY-U2-USD"])
        primary = re.search(r"<button([^>]*id=\"primary-cta\"[^>]*)>", html).group(1)
        self.assertIn('data-price-id="TEST-ONLY-NP-YEAR"', primary)
        self.assertEqual(row["native_price_id"], "TEST-ONLY-NP-YEAR")

    def test_a_lead_that_is_not_a_price_choice_refuses(self):
        copies = copy.deepcopy(self.copies)
        copies["upsell_2"]["lead_price_choice_id"] = "NOT-A-PRICE"
        with self.assertRaisesRegex(bpp.PageBuildError, "lead_price_choice_id"):
            self._build(self._with_u2_prices(MONTH, YEAR), copies)

    def test_three_price_choices_refuse(self):
        third = _price("TEST-ONLY-U2-USD-WEEK", 2900, "week", "TEST-ONLY-NP-WEEK")
        with self.assertRaisesRegex(bpp.PageBuildError, "at most 2"):
            self._build(self._with_u2_prices(MONTH, YEAR, third))

    def test_an_installment_choice_refuses(self):
        plan = _price("TEST-ONLY-U2-USD-PLAN", 25000, None, "TEST-ONLY-NP-PLAN", billing="installment")
        with self.assertRaisesRegex(bpp.PageBuildError, "installment"):
            self._build(self._with_u2_prices(MONTH, plan))

    def test_an_unapproved_choice_refuses(self):
        with self.assertRaisesRegex(bpp.PageBuildError, "only approved prices"):
            self._build(self._with_u2_prices(
                MONTH, dict(YEAR, approval_status="recommended_unapproved")))

    def test_two_choices_sharing_one_native_price_refuse(self):
        with self.assertRaisesRegex(bpp.PageBuildError, "never charge one price"):
            self._build(self._with_u2_prices(MONTH, dict(YEAR, native_price_id="TEST-ONLY-NP-MONTH")))

    def test_every_section_cta_must_still_name_the_one_declared_ref(self):
        copies = copy.deepcopy(self.copies)
        copies["upsell_2"]["sections"][3]["cta"]["action_ref"] = "native-one-click:OTHER"
        with self.assertRaisesRegex(bpp.PageBuildError, "exactly one guarded"):
            self._build(self._with_u2_prices(MONTH, YEAR), copies)

    def test_a_single_price_offer_is_unchanged(self):
        base = self._build(self.launch)
        html, row = self._u2(base)
        self.assertNotIn("accept_actions", row)
        self.assertNotIn("data-price-choice-id", html)
        self.assertEqual(html.count("<button"), 8)
        self.assertEqual(sorted(set(re.findall(r'data-action-ref="([^"]+)"', html))),
                         ["native-one-click:TEST-ONLY-U2"])
        # one-price offer with a lead field present: still one action, field ignored
        copies = copy.deepcopy(self.copies)
        copies["upsell_2"]["lead_price_choice_id"] = "TEST-ONLY-U2-USD"
        self.assertEqual(self._u2(self._build(self.launch, copies))[0], html)


if __name__ == "__main__":
    unittest.main()
