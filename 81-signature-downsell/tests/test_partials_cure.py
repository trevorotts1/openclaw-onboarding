"""Partials cure tests for the re-review of the validator fix lane
(2026-10-16): the five PARTIAL defects (D-3, D-6, D-8, D-9, D-13), the
new findings N-2, N-3, N-4, and the D-9 zero-cents residuals left open
by the D-9 cure's own re-review.

Each test reproduces the exact escape the re-review recorded (or the
residual its successor review recorded) and pins the cured behavior.
Passing controls are included wherever a cure could over-fire, so the
tightening cannot silently reject valid input. Nothing here weakens an
existing check and no existing test file is edited.
Run: python3 -m unittest discover -s tests -v
"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validators"))
import validate_downsell as vd  # noqa: E402

PAGE = json.loads((ROOT / "fixtures" / "valid-downsell-page.json").read_text())["page"]

U1V = {"offer_id": "U1", "slot": "upsell_1",
       "entitlement_ids": ["training-sessions", "private-community",
                           "founder-feedback"],
       "deliverables": ["Weekly live training sessions",
                        "Private community access",
                        "Founder feedback reviews"],
       "excludes": ["D1"], "requires": [],
       "prices": [{"amount_minor": 6700, "schedule": []}]}
D1V = {"offer_id": "D1", "slot": "downsell_1",
       "entitlement_ids": ["live-coaching", "founder-reviews",
                           "community-access"],
       "deliverables": ["Live weekly coaching workshops",
                        "Members only group entry",
                        "Founder critique sessions"],
       "excludes": ["U1"], "requires": [],
       "rationale": "Smaller commitment for visitors who declined the full upgrade.",
       "prices": [{"amount_minor": 3700, "schedule": []}]}

U1S = {"offer_id": "U1", "slot": "upsell_1",
       "entitlement_ids": ["u-alpha", "u-beta", "u-gamma"],
       "deliverables": ["Alpha onboarding program",
                        "Beta resource library",
                        "Gamma mentor network"],
       "excludes": ["D1"], "requires": [],
       "prices": [{"amount_minor": 6700, "schedule": []}]}
D1S = {"offer_id": "D1", "slot": "downsell_1",
       "entitlement_ids": ["d-one", "d-two", "d-three"],
       "deliverables": ["Alpha advanced practicum",
                        "Beta advanced practicum",
                        "Gamma advanced practicum"],
       "excludes": ["U1"], "requires": [],
       "difference_kind": "reduced_scope",
       "rationale": "Same headline areas, smaller commitment.",
       "prices": [{"amount_minor": 3700, "schedule": []}]}


def scrubbed_page():
    """Valid page with every example amount scrubbed and none approved,
    so a price-leak verdict can only come from the text a test adds."""
    p = copy.deepcopy(PAGE)
    p["approved_amounts_minor"] = []
    for s in p["sections"]:
        s["body"] = s["body"].replace("$1", "").replace("$27", "")
        s["cta"]["label"] = s["cta"]["label"].replace("$1", "")
    return p


def page_with_body(text, section=0):
    p = copy.deepcopy(PAGE)
    p["sections"][section]["body"] += " " + text
    return p


class D3ScarcityFamilyTests(unittest.TestCase):
    """Re-review D-3: four common scarcity phrasings passed with no
    evidence ref under v0.3. Each must now fire D1-COPY-FAKE-SCARCITY."""

    def test_couple_of_spots_remain(self):
        p = page_with_body("Only a couple of spots remain at this price.")
        self.assertIn("D1-COPY-FAKE-SCARCITY", vd.validate_copy(p))

    def test_enrollment_closes(self):
        p = page_with_body("Enrollment closes Friday, do not wait.")
        self.assertIn("D1-COPY-FAKE-SCARCITY", vd.validate_copy(p))

    def test_prices_rise(self):
        p = page_with_body("Prices rise on Monday, join today.")
        self.assertIn("D1-COPY-FAKE-SCARCITY", vd.validate_copy(p))

    def test_selling_out_fast(self):
        p = page_with_body("Selling out fast, grab yours before they are gone.")
        self.assertIn("D1-COPY-FAKE-SCARCITY", vd.validate_copy(p))

    def test_ordinary_enrollment_copy_not_flagged(self):
        p = page_with_body(
            "Enrollment is open to every buyer who wants structured "
            "support and steady weekly practice.")
        self.assertEqual(vd.validate_copy(p), [])

    def test_scarcity_with_real_evidence_ref_passes(self):
        p = page_with_body("Only a couple of spots remain at this price.")
        p["scarcity_evidence_ref"] = "evidence/deadline-2026-10-31.txt"
        self.assertEqual(vd.validate_copy(p), [])


class D6PageLayerDeclineRefTests(unittest.TestCase):
    """Re-review D-6 / N-1: validate_copy never compared the page's
    decline ref against the purchase CTA ref. The valid page fixture's
    decline ref is native-decline-d1; its CTA ref is native-d1-action."""

    def test_decline_ref_equal_to_purchase_ref_rejected(self):
        p = copy.deepcopy(PAGE)
        p["decline_action"]["action_ref"] = "native-d1-action"
        self.assertIn("D1-COPY-DECLINE-ACTION-IS-PURCHASE-ACTION",
                      vd.validate_copy(p))

    def test_decline_ref_whitespace_padded_still_rejected(self):
        p = copy.deepcopy(PAGE)
        p["decline_action"]["action_ref"] = " native-d1-action "
        self.assertIn("D1-COPY-DECLINE-ACTION-IS-PURCHASE-ACTION",
                      vd.validate_copy(p))

    def test_distinct_decline_ref_stays_clean(self):
        self.assertEqual(vd.validate_copy(copy.deepcopy(PAGE)), [])


class D8PrivateLabelVariantTests(unittest.TestCase):
    """Re-review D-8: two close private-label variants passed v0.3."""

    def test_internal_review_only_rejected(self):
        p = copy.deepcopy(PAGE)
        p["sections"][0]["body"] = (
            "For internal review only, do not share. "
            + p["sections"][0]["body"])
        self.assertIn("D1-COPY-PRIVATE-LABEL-LEAK", vd.validate_copy(p))

    def test_section3_no_space_rejected(self):
        p = page_with_body("As shown in Section3 of the plan.", section=1)
        self.assertIn("D1-COPY-PRIVATE-LABEL-LEAK", vd.validate_copy(p))

    def test_plain_section_word_not_flagged(self):
        p = page_with_body("This section explains your access.")
        self.assertEqual(vd.validate_copy(p), [])


class D13SynonymParaphraseTests(unittest.TestCase):
    """Re-review D-13: ordinary synonym substitution defeated the
    identical-promise check. Cured by content-token matching (stemmed,
    synonym-folded, filler-free) plus a same-shape lower-price tier
    that routes shape-identical lower-price offers to the
    identical-promise code for owner decision (spec 11 section 4)."""

    def test_synonym_paraphrase_reduced_scope_rejected(self):
        d = copy.deepcopy(D1V)
        d["difference_kind"] = "reduced_scope"
        self.assertIn("D1-OFFER-IDENTICAL-PROMISE",
                      vd.validate_offer_difference(U1V, d))

    def test_synonym_paraphrase_lower_total_price_rejected(self):
        d = copy.deepcopy(D1V)
        d["difference_kind"] = "lower_total_price"
        self.assertIn("D1-OFFER-IDENTICAL-PROMISE",
                      vd.validate_offer_difference(U1V, d))

    def test_same_shape_lower_price_flagged_for_owner(self):
        # Pairwise paraphrase similarity is below the matching
        # threshold, but the offer keeps U1's exact shape (same
        # deliverable count, same entitlement count) at a lower total
        # and every D1 deliverable still touches a U1 deliverable's
        # content, so it must not pass silently.
        self.assertIn("D1-OFFER-IDENTICAL-PROMISE",
                      vd.validate_offer_difference(U1S, copy.deepcopy(D1S)))

    def test_genuinely_different_offer_same_shape_passes(self):
        d = copy.deepcopy(D1S)
        d["deliverables"] = ["Zebra quantum xylophone",
                             "Pluto nebula telescope",
                             "Velvet hammer toolkit"]
        self.assertEqual(vd.validate_offer_difference(U1S, d), [])

    def test_genuine_reduced_scope_still_passes(self):
        d = copy.deepcopy(D1S)
        d["deliverables"] = ["Alpha onboarding program"]
        d["entitlement_ids"] = ["d-one"]
        self.assertEqual(vd.validate_offer_difference(U1S, d), [])


class N2LossOfPurchaseVocabularyTests(unittest.TestCase):
    """Re-review N-2: take-away and removal threats naming the purchase
    itself escaped the page-wide loss scan."""

    def test_take_away_access_you_already_bought(self):
        p = page_with_body("We will take away the access you already bought.")
        self.assertIn("D1-COPY-FALSE-LOSS-OF-PURCHASE", vd.validate_copy(p))

    def test_declining_removes_what_you_purchased(self):
        p = page_with_body("Declining removes what you purchased.")
        self.assertIn("D1-COPY-FALSE-LOSS-OF-PURCHASE", vd.validate_copy(p))

    def test_take_away_what_you_already_bought(self):
        p = page_with_body("Skip this and we will take away what you already bought.")
        self.assertIn("D1-COPY-FALSE-LOSS-OF-PURCHASE", vd.validate_copy(p))

    def test_removes_what_you_already_purchased(self):
        p = page_with_body("Passing removes what you already purchased today.")
        self.assertIn("D1-COPY-FALSE-LOSS-OF-PURCHASE", vd.validate_copy(p))

    def test_truthful_access_ends_wording_not_flagged(self):
        p = page_with_body(
            "If you stop a payment, access ends when the current paid "
            "period ends.", section=6)
        self.assertEqual(vd.validate_copy(p), [])


class N3NonStringEvidenceRefTests(unittest.TestCase):
    """Re-review N-3: a non-string falsy scarcity_evidence_ref counted
    as recorded evidence under v0.3."""

    def _page_with_ref(self, ref):
        p = page_with_body("This is a one time only offer, never again!")
        p["scarcity_evidence_ref"] = ref
        return p

    def test_integer_zero_evidence_ref_counts_as_missing(self):
        self.assertIn("D1-COPY-FAKE-SCARCITY",
                      vd.validate_copy(self._page_with_ref(0)))

    def test_boolean_false_evidence_ref_counts_as_missing(self):
        self.assertIn("D1-COPY-FAKE-SCARCITY",
                      vd.validate_copy(self._page_with_ref(False)))

    def test_real_string_evidence_ref_still_counts(self):
        p = self._page_with_ref("evidence/deadline-2026-10-31.txt")
        self.assertEqual(vd.validate_copy(p), [])


class N4MalformedDisclosureInputTests(unittest.TestCase):
    """Re-review N-4: validate_trial_disclosure(None, [1, 2]) returned
    a clean pass under v0.3. Wholly malformed top-level input is a
    violation, and the validator still never raises."""

    def test_none_offer_and_list_disclosure(self):
        self.assertIn("D1-DISCLOSURE-MALFORMED-INPUT",
                      vd.validate_trial_disclosure(None, [1, 2]))

    def test_both_arguments_none(self):
        self.assertIn("D1-DISCLOSURE-MALFORMED-INPUT",
                      vd.validate_trial_disclosure(None, None))

    def test_list_offer_and_dict_disclosure(self):
        self.assertIn("D1-DISCLOSURE-MALFORMED-INPUT",
                      vd.validate_trial_disclosure([1, 2], {}))

    def test_string_arguments(self):
        self.assertIn("D1-DISCLOSURE-MALFORMED-INPUT",
                      vd.validate_trial_disclosure("junk", "junk"))

    def test_wellformed_pair_unchanged(self):
        d = {"prices": [{"billing_type": "one_time", "amount_minor": 3700,
                         "schedule": []}]}
        self.assertEqual(vd.validate_trial_disclosure(d, {}), [])


class D9ZeroCentsResidualTests(unittest.TestCase):
    """D-9 residuals recorded by the D-9 cure re-review: the exact
    amount with a one-decimal or three-decimal zero-cents rendering
    still passed. The zero-cents part now accepts any run of zeros;
    nonzero cents remain genuinely different amounts."""

    def _page_with_cta(self, label):
        p = scrubbed_page()
        p["sections"][0]["cta"]["label"] = label
        return p

    def test_one_decimal_zero_cents_caught(self):
        p = self._page_with_cta("Join for $27.0 now")
        self.assertIn("D1-COPY-EXAMPLE-PRICE-LEAK", vd.validate_copy(p))

    def test_three_decimal_zero_cents_caught(self):
        p = self._page_with_cta("Join for $27.000 now")
        self.assertIn("D1-COPY-EXAMPLE-PRICE-LEAK", vd.validate_copy(p))

    def test_one_decimal_zero_cents_usd_caught(self):
        p = scrubbed_page()
        p["sections"][0]["body"] += " Pay 27.0 USD monthly."
        self.assertIn("D1-COPY-EXAMPLE-PRICE-LEAK", vd.validate_copy(p))

    def test_three_decimal_zero_cents_usd_caught(self):
        p = scrubbed_page()
        p["sections"][0]["body"] += " Pay 27.000 USD monthly."
        self.assertIn("D1-COPY-EXAMPLE-PRICE-LEAK", vd.validate_copy(p))

    def test_one_decimal_zero_cents_dollar_word_caught(self):
        p = scrubbed_page()
        p["sections"][0]["body"] += " That is 27.0 dollars a month."
        self.assertIn("D1-COPY-EXAMPLE-PRICE-LEAK", vd.validate_copy(p))

    def test_two_decimal_zero_cents_still_caught(self):
        p = self._page_with_cta("Join for $27.00 now")
        self.assertIn("D1-COPY-EXAMPLE-PRICE-LEAK", vd.validate_copy(p))

    def test_nonzero_cents_one_decimal_not_flagged(self):
        p = self._page_with_cta("Join for $27.5 now")
        self.assertEqual(vd.validate_copy(p), [])

    def test_nonzero_cents_two_decimals_not_flagged(self):
        p = self._page_with_cta("Join for $27.50 now")
        self.assertEqual(vd.validate_copy(p), [])

    def test_zero_then_nonzero_cents_not_flagged(self):
        p = self._page_with_cta("Join for $27.05 now")
        self.assertEqual(vd.validate_copy(p), [])

    def test_longer_amount_still_not_flagged(self):
        p = self._page_with_cta("Join for $279 now")
        self.assertEqual(vd.validate_copy(p), [])


if __name__ == "__main__":
    unittest.main()
