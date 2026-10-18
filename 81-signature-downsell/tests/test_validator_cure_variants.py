"""Variant tests for the cure of the v0.3 independent re-review FAIL.

The re-review standard: a fix that only catches the original probe
wording is not a fix. Each test below attacks the defect mechanism with
wording that differs from both the lane 5 probes and the re-review's
own escaping variants, and passing controls pin the over-firing edge.
Defects covered: D-9 (extra formats beyond test_d9_price_format_cure),
D-3, D-6/N-1, D-8, D-13, plus new findings N-2 and N-3.
Nothing here edits or weakens any pre-existing test.
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
LEAK = "D1-COPY-EXAMPLE-PRICE-LEAK"
SCARCITY = "D1-COPY-FAKE-SCARCITY"
PRIVATE = "D1-COPY-PRIVATE-LABEL-LEAK"

U1 = {"offer_id": "U1", "slot": "upsell_1", "entitlement_ids": ["extra-full"],
      "deliverables": ["Weekly live training sessions",
                       "Private community access",
                       "Founder feedback reviews"],
      "excludes": ["D1"], "requires": [],
      "prices": [{"amount_minor": 6700, "schedule": []}]}
D1 = {"offer_id": "D1", "slot": "downsell_1", "entitlement_ids": ["extra-lite"],
      "deliverables": ["A", "B"], "excludes": ["U1"], "requires": [],
      "difference_kind": "reduced_scope",
      "rationale": "Same core, smaller scope for visitors who declined "
                   "the full upgrade on commitment size.",
      "prices": [{"amount_minor": 3700, "schedule": []}]}


def body_with(text):
    p = copy.deepcopy(PAGE)
    p["sections"][0]["body"] += " " + text
    return p


def scrubbed():
    p = copy.deepcopy(PAGE)
    p["approved_amounts_minor"] = []
    for s in p["sections"]:
        s["body"] = s["body"].replace("$1", "").replace("$27", "")
        s["cta"]["label"] = s["cta"]["label"].replace("$1", "")
    return p


class D9MoreVariantTests(unittest.TestCase):
    def test_spaced_dollar_sign_with_cents_caught(self):
        p = scrubbed()
        p["sections"][0]["cta"]["label"] = "Join for $ 27.00 now"
        self.assertIn(LEAK, vd.validate_copy(p))

    def test_cents_with_dollar_word_caught(self):
        p = scrubbed()
        p["sections"][0]["body"] += " That is 27.00 dollars today."
        self.assertIn(LEAK, vd.validate_copy(p))

    def test_hyphenated_plural_dollars_caught(self):
        p = scrubbed()
        p["sections"][0]["body"] += " A 997-dollars bundle was the example."
        self.assertIn(LEAK, vd.validate_copy(p))

    def test_longer_amount_270_not_flagged(self):
        p = scrubbed()
        p["sections"][0]["cta"]["label"] = "Join for $270 now"
        self.assertEqual(vd.validate_copy(p), [])

    def test_nonzero_cents_2799_not_flagged(self):
        p = scrubbed()
        p["sections"][0]["cta"]["label"] = "Join for $27.99 now"
        self.assertEqual(vd.validate_copy(p), [])


class D3ScarcityVariantTests(unittest.TestCase):
    ESCAPES = (
        # The four re-review escapes, verbatim.
        "Only a couple of spots remain at this price.",
        "Enrollment closes Friday, do not wait.",
        "Prices rise on Monday, join today.",
        "Selling out fast, grab yours before they are gone.",
        # Fresh variants in the same families, different wording.
        "Only two spots are left in this round.",
        "Registration is closing tonight.",
        "Seats are filling fast, claim yours.",
        "We are running out of places at this level.",
        "The enrollment window is closing this week.",
        "Price increases at the end of the month.",
        "A couple of seats are still open at this level.",
        "This round is almost full, act soon.",
    )

    def test_all_variants_caught_without_evidence(self):
        for text in self.ESCAPES:
            self.assertIn(SCARCITY, vd.validate_copy(body_with(text)), text)

    def test_same_claim_with_real_evidence_ref_passes(self):
        p = body_with("Only a couple of spots remain at this price.")
        p["scarcity_evidence_ref"] = "evidence/cap-2026-10-31.txt"
        self.assertEqual(vd.validate_copy(p), [])

    def test_valid_page_still_clean(self):
        self.assertEqual(vd.validate_copy(copy.deepcopy(PAGE)), [])


class D6PageSurfaceTests(unittest.TestCase):
    CODE = "D1-COPY-DECLINE-ACTION-IS-PURCHASE-ACTION"

    def test_decline_ref_equal_to_purchase_ref_rejected(self):
        p = copy.deepcopy(PAGE)
        p["decline_action"]["action_ref"] = "native-d1-action"
        self.assertIn(self.CODE, vd.validate_copy(p))

    def test_padded_decline_ref_still_rejected(self):
        p = copy.deepcopy(PAGE)
        p["decline_action"]["action_ref"] = " native-d1-action "
        self.assertIn(self.CODE, vd.validate_copy(p))

    def test_distinct_decline_ref_still_passes(self):
        self.assertEqual(vd.validate_copy(copy.deepcopy(PAGE)), [])


class D8PrivateLabelVariantTests(unittest.TestCase):
    def test_internal_review_only_caught(self):
        self.assertIn(PRIVATE, vd.validate_copy(
            body_with("For internal review only, do not share.")))

    def test_no_space_section_number_caught(self):
        self.assertIn(PRIVATE, vd.validate_copy(
            body_with("As shown in Section3 of the plan.")))

    def test_no_space_two_digit_section_caught(self):
        self.assertIn(PRIVATE, vd.validate_copy(
            body_with("See Section12 for the mapping.")))

    def test_hyphenated_internal_review_caught(self):
        self.assertIn(PRIVATE, vd.validate_copy(
            body_with("Internal-review draft, not for clients.")))


class D13SynonymParaphraseTests(unittest.TestCase):
    CODE = "D1-OFFER-IDENTICAL-PROMISE"

    def offer(self, deliverables, entitlements, amount=999):
        d = copy.deepcopy(D1)
        d["deliverables"] = deliverables
        d["entitlement_ids"] = entitlements
        d["prices"] = [{"amount_minor": amount, "schedule": []}]
        return d

    def test_rereview_synonym_paraphrase_caught(self):
        d = self.offer(
            ["Live weekly coaching workshops",
             "Members only group entry",
             "Founder critique sessions"], ["renamed-x"])
        self.assertIn(self.CODE, vd.validate_offer_difference(U1, d))

    def test_fresh_synonym_paraphrase_caught(self):
        d = self.offer(
            ["Live instruction every week",
             "Exclusive members forum access",
             "Personal critiques from the founder"], ["renamed-y"])
        self.assertIn(self.CODE, vd.validate_offer_difference(U1, d))

    def test_third_paraphrase_wording_caught(self):
        d = self.offer(
            ["Live coaching calls each week",
             "Private group entry for members",
             "Feedback reviews from the founder"], ["renamed-z"])
        self.assertIn(self.CODE, vd.validate_offer_difference(U1, d))

    def test_same_shape_weak_contact_paraphrase_caught(self):
        # Same shape, lower price, every item keeps only a weak content
        # anchor: the shape tier flags it for owner decision (spec 11 s.4).
        d = self.offer(
            ["Live expert gatherings every week",
             "Private forum entry",
             "Founder session critiques"], ["renamed-w"])
        self.assertIn(self.CODE, vd.validate_offer_difference(U1, d))

    def test_genuine_reduced_scope_fewer_deliverables_passes(self):
        d = self.offer(["Live training sessions every week"], ["extra-lite"])
        self.assertEqual(vd.validate_offer_difference(U1, d), [])

    def test_genuinely_different_offer_same_count_passes(self):
        # Same shape but a different promise: some deliverables share no
        # content token with any U1 deliverable, so neither tier fires.
        d = self.offer(
            ["Beginner guitar lesson library",
             "Monthly recipe newsletter",
             "Home workout video archive"], ["music-lite"])
        self.assertEqual(vd.validate_offer_difference(U1, d), [])

    def test_base_reduced_scope_still_passes(self):
        self.assertEqual(vd.validate_offer_difference(U1, copy.deepcopy(D1)),
                         [])


class N2LossThreatVariantTests(unittest.TestCase):
    def test_take_away_access_threat_caught(self):
        self.assertIn("D1-COPY-FALSE-LOSS-OF-PURCHASE", vd.validate_copy(
            body_with("Skip this and we will take away the access "
                      "you already bought.")))

    def test_revoke_access_threat_caught(self):
        self.assertIn("D1-COPY-FALSE-LOSS-OF-PURCHASE", vd.validate_copy(
            body_with("Pass now and we revoke your access "
                      "to the program.")))


class N3EvidenceRefVariantTests(unittest.TestCase):
    def test_integer_zero_evidence_ref_counts_as_missing(self):
        p = body_with("This is a one time only offer, never again!")
        p["scarcity_evidence_ref"] = 0
        self.assertIn(SCARCITY, vd.validate_copy(p))

    def test_false_evidence_ref_counts_as_missing(self):
        p = body_with("This is a one time only offer, never again!")
        p["scarcity_evidence_ref"] = False
        self.assertIn(SCARCITY, vd.validate_copy(p))


if __name__ == "__main__":
    unittest.main()
