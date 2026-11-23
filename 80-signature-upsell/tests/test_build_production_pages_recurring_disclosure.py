"""RFX-012: a recurring upsell is disclosed from its recurring_interval.

Skill 83's intake carries a recurring price's cadence in ``recurring_interval``
and refuses any non-empty ``schedule``. The production builder used to refuse
every recurring price whose schedule was empty and never read the interval, so
a recurring upsell (8900 USD monthly) could never be built, and leaving it
one_time would print "One-time charge ... No further charges" beside copy that
says monthly. These tests pin the fix: the interval is phrased through the
shared billing vocabulary (``billing.price_per_interval``, "$89.00/month") with
renew-until-cancelled terms; a recurring price with no interval, an interval
outside the vocabulary and installment plans still refuse; one_time is
unchanged.

Run from the skill root:  python3 -m unittest discover -s tests
"""

import copy
import importlib.util
import json
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
bpp = _import("build_production_pages_recurring_under_test",
              PAGES / "build_production_pages.py")
compiler = _import("compile_launch_route_recurring_under_test",
                   REPO / "49-signature-funnel" / "scripts" / "compile_launch_route.py")


def _offer(billing_type, amount_minor=8900, interval=None, schedule=None):
    return {"amount_minor": amount_minor, "currency": "USD",
            "billing_type": billing_type, "recurring_interval": interval,
            "schedule": schedule or []}


class RecurringDisclosure(unittest.TestCase):
    def test_monthly_8900_is_phrased_per_interval_with_recurring_terms(self):
        text = bpp.disclosure_for("upsell_2", _offer("recurring", interval="month"))
        self.assertIn("$89.00/month", text)
        self.assertIn("until you cancel", text)
        self.assertIn("Cancel before a renewal", text)
        self.assertNotIn("One-time", text)
        self.assertNotIn("No further charges", text)

    def test_every_vocabulary_interval_is_phrased_by_the_shared_helper(self):
        for interval in ("week", "month", "quarter", "year"):
            text = bpp.disclosure_for("upsell_1", _offer("recurring", interval=interval))
            self.assertIn("$89.00/%s" % interval, text, interval)
            self.assertIn("every %s until you cancel" % interval, text, interval)

    def test_recurring_with_no_interval_and_no_schedule_refuses(self):
        for interval in (None, ""):
            with self.assertRaises(bpp.PageBuildError) as ctx:
                bpp.disclosure_for("upsell_2", _offer("recurring", interval=interval))
            self.assertIn("recurring_interval", str(ctx.exception))

    def test_interval_outside_the_vocabulary_refuses(self):
        with self.assertRaises(bpp.PageBuildError) as ctx:
            bpp.disclosure_for("upsell_2", _offer("recurring", interval="fortnight"))
        self.assertIn("AF-RECURRING-INTERVAL", str(ctx.exception))

    def test_installment_still_refuses(self):
        for kind in ("installment", "installments"):
            with self.assertRaises(bpp.PageBuildError):
                bpp.disclosure_for("upsell_2", _offer(kind, interval="month"))

    def test_one_time_is_unchanged(self):
        self.assertEqual(
            bpp.disclosure_for("upsell_1", _offer("one_time", amount_minor=6700)),
            "One-time charge of $67.00, charged to your original payment "
            "method when you accept. No further charges for this offer.")

    def test_explicit_schedule_path_is_unchanged(self):
        text = bpp.disclosure_for("upsell_2", _offer(
            "recurring", amount_minor=4700,
            schedule=[{"amount_minor": 4700, "due": "monthly, 3 total cycles"}]))
        self.assertEqual(text, "Recurring charge of $47.00 — monthly, 3 total cycles. "
                               "Charged to your original payment method when you "
                               "accept; cancel before a renewal to stop future charges.")


class RecurringUpsellBuild(unittest.TestCase):
    """The same through build(): the record price reaches the page and manifest."""

    def setUp(self):
        launch = _load(REPO / "49-signature-funnel" / "scripts" / "fixtures"
                       / "finalized-launch-record-signature-launch-l4.json")
        launch["u2_entry_context"] = "from_upsell_1"
        self.graph = compiler.compile_route(launch)
        self.launch = launch
        self.copies = {
            "upsell_1": _load(FIXTURES / "copy-upsell1-public.valid.json"),
            "upsell_2": _load(FIXTURES / "copy-upsell2-public.valid.json"),
        }
        self.d1 = _load(REPO / "81-signature-downsell" / "fixtures"
                        / "valid-downsell-page.json")

    def _with_u2_price(self, **fields):
        launch = copy.deepcopy(self.launch)
        for offer in launch["offers"]:
            if offer["slot"] == "upsell_2":
                price = offer["prices"][0]
                price.update(fields)
                for key in [k for k, v in fields.items() if v is None]:
                    price.pop(key)
        return launch

    def _build(self, launch):
        return bpp.build(launch, self.graph, FAMILY, self.copies, self.d1, {})

    def test_monthly_upsell_builds_with_the_recurring_disclosure(self):
        built = self._build(self._with_u2_price(
            amount_minor=8900, billing_type="recurring",
            recurring_interval="month", schedule=[]))
        u2 = next(p for p in built["manifest"]["pages"] if p["slot"] == "upsell_2")
        self.assertIn("$89.00/month", u2["disclosure"])
        self.assertIn("$89.00/month", built["pages"]["upsell_2"])
        self.assertNotIn("One-time charge", built["pages"]["upsell_2"])

    def test_monthly_upsell_without_an_interval_writes_nothing(self):
        with self.assertRaises(bpp.PageBuildError) as ctx:
            self._build(self._with_u2_price(
                amount_minor=8900, billing_type="recurring",
                recurring_interval=None, schedule=[]))
        self.assertIn("upsell_2", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
