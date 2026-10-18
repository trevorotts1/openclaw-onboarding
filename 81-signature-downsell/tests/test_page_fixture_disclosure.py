"""Page-fixture trial disclosure tests (gap G19 from lane review 7).

The page fixture's offer is a trial ($1 for 30 days, then $27 per
month), but validate_trial_disclosure was previously exercised only
with synthetic dicts, never against this fixture, and the fixture's
surfaces carried no cancellation wording and no renewal date or rule.

This suite applies validate_trial_disclosure to the page fixture: the
offer and every disclosure field are derived from the fixture itself
(approved_amounts_minor and the wording on its public surfaces), and
each disclosure value is first asserted to actually appear on those
surfaces. Spec 11 section 4 requires, for a trial: due-now, trial
length, renewal amount, renewal date or rule, interval, cancellation
terms, and access implications.
Run: python3 -m unittest discover -s tests -v
"""
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validators"))
from validate_downsell import validate_copy, validate_trial_disclosure  # noqa: E402

PAGE_FILE = json.loads(
    (ROOT / "fixtures" / "valid-downsell-page.json").read_text()
)
PAGE = PAGE_FILE["page"]


def surface_text(page):
    out = []
    for s in page.get("sections") or []:
        out.append(s.get("heading") or "")
        out.append(s.get("body") or "")
        cta = s.get("cta") or {}
        out.append(cta.get("label") or "")
        out.extend(s.get("missed_out_items") or [])
    d = page.get("decline_action") or {}
    out.append(d.get("label") or "")
    return " ".join(out)


class TestPageFixtureTrialDisclosure(unittest.TestCase):
    def setUp(self):
        self.surfaces = surface_text(PAGE)
        self.lower = self.surfaces.lower()
        approved = PAGE["approved_amounts_minor"]
        self.due_now = approved[0]
        self.renewal = approved[1]
        self.offer = {
            "offer_id": "D1",
            "slot": "downsell_1",
            "prices": [{
                "billing_type": "trial",
                "amount_minor": self.due_now,
                "schedule": [{"amount_minor": self.renewal}],
            }],
        }

    def test_fixture_still_passes_copy_validator(self):
        self.assertEqual(validate_copy(PAGE), [])

    def test_trial_price_and_period_on_surfaces(self):
        self.assertIn("$1", self.surfaces)
        self.assertIn("30 days", self.lower)
        self.assertIn("$27", self.surfaces)
        self.assertIn("per month", self.lower)

    def test_cancellation_wording_on_surfaces(self):
        self.assertIn("cancel anytime", self.lower)
        self.assertIn(
            "you can cancel anytime before a renewal charge "
            "to stop future charges",
            self.lower,
        )

    def test_renewal_date_or_rule_on_surfaces(self):
        self.assertIn("day 31", self.lower)
        self.assertIn("monthly", self.lower)

    def test_access_implications_on_surfaces(self):
        self.assertIn(
            "your access continues until the end of the trial "
            "or the current paid month",
            self.lower,
        )
        self.assertIn("you will not be charged again", self.lower)

    def test_page_fixture_passes_trial_disclosure_validator(self):
        disclosure = {
            "due_now_minor": self.due_now,
            "trial_length": "30 days",
            "renewal_amount_minor": self.renewal,
            "renewal_date_or_rule": "day 31",
            "interval": "monthly",
            "cancellation_terms": (
                "You can cancel anytime before a renewal charge "
                "to stop future charges."
            ),
            "access_implications": (
                "Access continues until the end of the trial or "
                "the current paid month, then membership access "
                "ends and you will not be charged again."
            ),
        }
        self.assertEqual(
            validate_trial_disclosure(self.offer, disclosure), []
        )

    def test_page_fixture_disclosure_without_cancellation_fails(self):
        # Negative control: the same fixture-derived disclosure with the
        # cancellation terms removed must be rejected, proving the pass
        # above is carried by the wording now on the fixture's surfaces.
        disclosure = {
            "due_now_minor": self.due_now,
            "trial_length": "30 days",
            "renewal_amount_minor": self.renewal,
            "renewal_date_or_rule": "day 31",
            "interval": "monthly",
            "cancellation_terms": "",
            "access_implications": "access ends at period end",
        }
        v = validate_trial_disclosure(self.offer, disclosure)
        self.assertIn("D1-DISCLOSURE-MISSING-CANCELLATION_TERMS", v)


if __name__ == "__main__":
    unittest.main()
