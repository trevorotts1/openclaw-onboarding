"""Round 2 cure tests for the S81 partials (2026-10-16).

The governing re-review of the partials cure (lane-review-partials-
cure-1850) kept D-3, D-8, D-13 and N-2 PARTIAL under fresh variants:
every recorded escape was rejected, but fresh ordinary phrasings
walked around the widened pattern lists through the same mechanisms.
This file pins the round 2 cure, which widens by named family
mechanism instead of by recorded sentence:

- D-3 scarcity: limited-time and limited-availability families, the
  miss-out exhortation when it carries a deadline in the same
  sentence, too-late and going-fast wording, small-count claims with
  or without "only", depletion and stock wording, availability
  deadlines, final-window claims, and explicit deadline windows.
- D-8 private labels: internal-audience markers, the abbreviated
  section reference, confidentiality and not-for-publication
  markers, and the wider framework-structure references.
- N-2 loss threats: forfeit, strip and withdraw verb families, the
  seller-subject cancel family, and the passive and object-first
  forms, all keyed to a bought-object phrase.
- D-13: a partial-paraphrase tier beside the shape tier. Same shape
  at a lower total, at least one deliverable matching at the
  paraphrase threshold (the anchor), and at least one deliverable
  out of token contact (the single reworded item) is flagged for
  owner decision under spec 11 section 4.
- Item 5 (secondary): the price scan covers the prefix-currency form
  ("USD 27") and the slang denomination ("27 bucks",
  "twenty-seven bucks").
- Item 6 (secondary): a nested malformed prices value returns
  D1-DISCLOSURE-MALFORMED-INPUT instead of a clean pass.

Held-out variants (wordings that appear in no review) are pinned
beside each governing set, and passing controls pin the over-firing
edges, including the truthful buyer-cancels flow. The disclosed
D-13 zero-token lexical residual is no longer a passing control:
the 2026-10-17 D-13 cure closed it, and the zero-token paraphrase
is now pinned as caught. Nothing here edits or weakens a
pre-existing test.
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

SCARCITY = "D1-COPY-FAKE-SCARCITY"
PRIVATE = "D1-COPY-PRIVATE-LABEL-LEAK"
LOSS = "D1-COPY-FALSE-LOSS-OF-PURCHASE"
LEAK = "D1-COPY-EXAMPLE-PRICE-LEAK"
IDENT = "D1-OFFER-IDENTICAL-PROMISE"
MALFORMED = "D1-DISCLOSURE-MALFORMED-INPUT"

U1V = {"offer_id": "U1", "slot": "upsell_1",
       "entitlement_ids": ["training-sessions", "private-community",
                           "founder-feedback"],
       "deliverables": ["Weekly live training sessions",
                        "Private community access",
                        "Founder feedback reviews"],
       "excludes": ["D1"], "requires": [],
       "prices": [{"amount_minor": 6700, "schedule": []}]}

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


def page_with_body(text, section=0):
    p = copy.deepcopy(PAGE)
    p["sections"][section]["body"] += " " + text
    return p


def scrubbed_page():
    """Valid page with every example amount scrubbed and none approved,
    so a price-leak verdict can only come from the text a test adds."""
    p = copy.deepcopy(PAGE)
    p["approved_amounts_minor"] = []
    for s in p["sections"]:
        s["body"] = s["body"].replace("$1", "").replace("$27", "")
        s["cta"]["label"] = s["cta"]["label"].replace("$1", "")
    return p


def d1_offer(deliverables, entitlements, amount=3700, kind="reduced_scope"):
    return {"offer_id": "D1", "slot": "downsell_1",
            "entitlement_ids": entitlements,
            "deliverables": deliverables,
            "excludes": ["U1"], "requires": [],
            "difference_kind": kind,
            "rationale": "Smaller commitment for visitors who declined.",
            "prices": [{"amount_minor": amount, "schedule": []}]}


class D3ScarcityRound2Tests(unittest.TestCase):
    """Governing re-review D-3: ten fresh common scarcity phrasings
    passed with no evidence ref after the first cure widened only the
    families the earlier review had named."""

    GOVERNING = (
        "Limited time offer, join now while you can.",
        "Do not miss out, join today.",
        "Grab yours before it is too late.",
        "Seats are going fast at this level.",
        "Availability is limited at this price.",
        "Just a handful of openings left.",
        "Spots are dwindling, act now.",
        "This will not be available tomorrow.",
        "Final hours to join at this level.",
        "Low stock at this tier, order soon.",
    )
    HELD_OUT = (
        "The joining window will not reopen after this week.",
        "This price is only guaranteed until Friday.",
        "Decide in the next 48 hours or this rate moves up.",
        "We are down to the last few spots at this tier.",
        "Your window to join at this rate is shrinking fast.",
    )

    def test_governing_variants_caught(self):
        for text in self.GOVERNING:
            with self.subTest(text=text):
                self.assertIn(SCARCITY, vd.validate_copy(page_with_body(text)))

    def test_held_out_variants_caught(self):
        for text in self.HELD_OUT:
            with self.subTest(text=text):
                self.assertIn(SCARCITY, vd.validate_copy(page_with_body(text)))

    def test_bare_miss_out_cta_language_not_flagged(self):
        # The valid fixture's own closing CTA reads "Do not miss out."
        # sentence-finally, with no deadline attached. That is the
        # room's ground truth for acceptable CTA language; the claim
        # fires only when a deadline is attached in the same sentence.
        self.assertEqual(vd.validate_copy(copy.deepcopy(PAGE)), [])

    def test_round2_family_with_evidence_ref_passes(self):
        p = page_with_body("Low stock at this tier, order soon.")
        p["scarcity_evidence_ref"] = "evidence/inventory-2026-10-16.txt"
        self.assertEqual(vd.validate_copy(p), [])

    def test_ordinary_copy_not_flagged(self):
        p = page_with_body(
            "The program runs all year and new members join every week "
            "for steady practice and support.")
        self.assertEqual(vd.validate_copy(p), [])


class D8PrivateLabelRound2Tests(unittest.TestCase):
    """Governing re-review D-8: seven of eight fresh close variants of
    the two pinned forms still passed after the first cure."""

    GOVERNING = (
        "For internal eyes only, do not share.",
        "Internal circulation only, do not distribute.",
        "See Sect 3 for the mapping.",
        "Confidential draft, not for publication.",
        "Framework chapter 3 overview follows.",
        "Staff only, keep this page internal.",
        "Internal memo for the team.",
    )
    HELD_OUT = (
        "Company eyes only, not for outside readers.",
        "See Sect. 12 for the full mapping.",
        "Framework unit 2 covers the onboarding flow.",
        "Internal playbook, never for client pages.",
    )

    def test_governing_variants_caught(self):
        for text in self.GOVERNING:
            with self.subTest(text=text):
                self.assertIn(PRIVATE, vd.validate_copy(page_with_body(text)))

    def test_held_out_variants_caught(self):
        for text in self.HELD_OUT:
            with self.subTest(text=text):
                self.assertIn(PRIVATE, vd.validate_copy(page_with_body(text)))

    def test_plain_section_word_not_flagged(self):
        p = page_with_body("This section explains your access.")
        self.assertEqual(vd.validate_copy(p), [])

    def test_confidentiality_assurance_not_flagged(self):
        # A privacy assurance to the buyer is public copy, not an
        # internal label: the word confidential alone does not fire.
        p = page_with_body(
            "Your payment details stay confidential with us.", section=6)
        self.assertEqual(vd.validate_copy(p), [])

    def test_members_only_restriction_not_flagged(self):
        p = page_with_body("This page is for members only.")
        self.assertEqual(vd.validate_copy(p), [])


class N2LossThreatRound2Tests(unittest.TestCase):
    """Governing re-review N-2: the forfeit, strip and cancel verb
    forms, and the object-first disappears form, passed the loss scan
    after the first cure added only the named take-away family."""

    GOVERNING = (
        "Decline and you forfeit the access you already bought.",
        "Skip this and we will strip the access you already purchased.",
        "Declining forfeits what you bought.",
        "Skip this and we cancel what you bought.",
        "Pass now and your bought program disappears from your account.",
    )
    HELD_OUT = (
        "Say no and we withdraw the access you already purchased.",
        "Pass on this and your purchase will be deleted.",
        "Decline today and the program you bought gets revoked.",
    )

    def test_governing_variants_caught(self):
        for text in self.GOVERNING:
            with self.subTest(text=text):
                self.assertIn(LOSS, vd.validate_copy(page_with_body(text)))

    def test_held_out_variants_caught(self):
        for text in self.HELD_OUT:
            with self.subTest(text=text):
                self.assertIn(LOSS, vd.validate_copy(page_with_body(text)))

    def test_buyer_cancels_and_keeps_purchase_not_flagged(self):
        # The truthful flow the spec requires: the buyer cancels a
        # renewal and keeps what was already bought. The cancel family
        # fires only with the seller as subject.
        p = page_with_body(
            "If you cancel, what you already bought stays yours until "
            "the paid period ends.", section=6)
        self.assertEqual(vd.validate_copy(p), [])

    def test_negated_disappears_carries_no_loss_code(self):
        # A negated loss statement is reassurance, not a threat, so
        # the loss code must not fire. (The word disappear on its own
        # remains a scarcity pattern from the original list, which the
        # governing review itself recorded; that is baseline behavior
        # outside this item.)
        p = page_with_body(
            "Your bought program never disappears from your account.")
        self.assertNotIn(LOSS, vd.validate_copy(p))


class D13PartialParaphraseRound2Tests(unittest.TestCase):
    """Governing re-review D-13: two fresh paraphrases escaped because
    one deliverable was reworded out of token contact, defeating the
    paraphrase tier and the shape tier at once. The round 2 cure adds
    the partial-paraphrase tier: anchor plus zero-contact item, same
    shape, lower total."""

    def test_paraphrase_a_reduced_scope_caught(self):
        d = d1_offer(
            ["Scheduled real-time instruction webinars",
             "Closed member circle admission",
             "Creator appraisal notes"], ["zz-1", "zz-2", "zz-3"])
        self.assertIn(IDENT, vd.validate_offer_difference(U1V, d))

    def test_paraphrase_a_lower_total_price_caught(self):
        d = d1_offer(
            ["Scheduled real-time instruction webinars",
             "Closed member circle admission",
             "Creator appraisal notes"], ["zz-1", "zz-2", "zz-3"],
            kind="lower_total_price")
        self.assertIn(IDENT, vd.validate_offer_difference(U1V, d))

    def test_paraphrase_b_reduced_scope_caught(self):
        d = d1_offer(
            ["Live weekly coaching workshops",
             "Members only group entry",
             "Personal appraisal from the creator"], ["q1", "q2", "q3"])
        self.assertIn(IDENT, vd.validate_offer_difference(U1V, d))

    def test_same_shape_full_contact_still_caught(self):
        # The pre-existing shape tier must keep firing: every item
        # keeps a weak content anchor and none reaches the paraphrase
        # threshold pairwise.
        self.assertIn(IDENT, vd.validate_offer_difference(
            U1S, copy.deepcopy(D1S)))

    def test_genuinely_different_offer_with_fold_contact_passes(self):
        # "Lesson" folds to "training", so the first item has weak
        # token contact with U1, but nothing reaches the paraphrase
        # threshold: there is no anchor item, so the new tier must not
        # fire on a genuinely different offer.
        d = d1_offer(
            ["Beginner guitar lesson library",
             "Monthly recipe newsletter",
             "Home workout video archive"], ["music-lite"], amount=999)
        self.assertEqual(vd.validate_offer_difference(U1V, d), [])

    def test_genuine_reduced_scope_passes(self):
        d = d1_offer(["Weekly live training sessions"], ["live-coaching"])
        self.assertEqual(vd.validate_offer_difference(U1V, d), [])

    def test_zero_token_paraphrase_now_caught_after_d13_cure(self):
        # CLAIM CORRECTION, placed beside the test as the original
        # pin required. The original pin
        # (test_zero_token_paraphrase_is_the_documented_residual)
        # read: "Pins current behavior for the residual the corrected
        # D-13 claim discloses: a paraphrase sharing no content token
        # with U1 anywhere has no anchor item and passes silently. Any
        # future semantic method that closes this must update this
        # test deliberately, with the claim correction beside it."
        # That future method has landed: the residual was cured on
        # 2026-10-17 by the D-13 cure's feature-paraphrase tier
        # (rooms/S81/build-lane-d13-cure-report.md), independently
        # reviewed PASS (rooms/S81/review-d13-cure-0340.md). The pin
        # now asserts the cured behavior at greater strength than the
        # original: the recorded residual pair and the cure's three
        # fresh zero-content-token pairs all return
        # D1-OFFER-IDENTICAL-PROMISE under both reduced_scope and
        # lower_total_price (the original pinned a silent pass for
        # the recorded pair under reduced_scope only).
        pairs = (
            ["Recurring interactive skill-building broadcasts",
             "Invitation-only peer hub",
             "Creator appraisal notes"],
            ["Ongoing interactive technique broadcasts",
             "Restricted insiders lounge",
             "Originator appraisal memos"],
            ["Continual participatory practice webcasts",
             "Vetted colleagues salon",
             "Producer appraisal notes"],
            ["Repeated real-time technique demonstrations",
             "Invite-only collaborators den",
             "Headliner grading notes"],
        )
        for deliverables in pairs:
            for kind in ("reduced_scope", "lower_total_price"):
                with self.subTest(first=deliverables[0], kind=kind):
                    d = d1_offer(deliverables, ["zz-1", "zz-2", "zz-3"],
                                 kind=kind)
                    self.assertIn(IDENT,
                                  vd.validate_offer_difference(U1V, d))


class D9DenominationRound2Tests(unittest.TestCase):
    """Item 5 (secondary): the governing re-review recorded, without
    scoring, that the prefix-currency forms and the slang denomination
    passed the price scan."""

    def _cta(self, label):
        p = scrubbed_page()
        p["sections"][0]["cta"]["label"] = label
        return p

    def _body(self, text):
        p = scrubbed_page()
        p["sections"][0]["body"] += " " + text
        return p

    def test_prefix_usd_caught(self):
        self.assertIn(LEAK, vd.validate_copy(self._cta("Join for USD 27 now")))

    def test_prefix_usd_cents_caught(self):
        self.assertIn(LEAK, vd.validate_copy(
            self._body("Pay USD 27.00 monthly.")))

    def test_prefix_usd_997_caught(self):
        self.assertIn(LEAK, vd.validate_copy(
            self._cta("Join for USD 997 now")))

    def test_bucks_digits_caught(self):
        self.assertIn(LEAK, vd.validate_copy(
            self._body("That is 27 bucks today.")))

    def test_bucks_one_dollar_caught(self):
        self.assertIn(LEAK, vd.validate_copy(
            self._body("A 1 buck trial starts today.")))

    def test_bucks_words_caught(self):
        self.assertIn(LEAK, vd.validate_copy(
            self._body("Yours for twenty-seven bucks.")))

    def test_prefix_usd_longer_amount_not_flagged(self):
        self.assertEqual(vd.validate_copy(self._cta("Join for USD 279 now")),
                         [])

    def test_bucks_longer_amount_not_flagged(self):
        self.assertEqual(vd.validate_copy(
            self._body("That is 279 bucks today.")), [])

    def test_bucks_nonzero_cents_not_flagged(self):
        self.assertEqual(vd.validate_copy(
            self._body("That is 27.50 bucks today.")), [])


class N4NestedMalformedRound2Tests(unittest.TestCase):
    """Item 6 (secondary): the governing re-review observed that a
    dict offer with a malformed nested prices value still returned a
    clean pass from validate_trial_disclosure."""

    def test_prices_string_is_malformed(self):
        self.assertIn(MALFORMED,
                      vd.validate_trial_disclosure({"prices": "junk"}, {}))

    def test_prices_non_dict_entry_is_malformed(self):
        self.assertIn(MALFORMED,
                      vd.validate_trial_disclosure({"prices": ["junk"]}, {}))

    def test_prices_dict_instead_of_list_is_malformed(self):
        self.assertIn(MALFORMED, vd.validate_trial_disclosure(
            {"prices": {"amount_minor": 100}}, {}))

    def test_absent_prices_unchanged(self):
        self.assertEqual(vd.validate_trial_disclosure({}, {}), [])

    def test_empty_prices_list_unchanged(self):
        self.assertEqual(vd.validate_trial_disclosure({"prices": []}, {}),
                         [])

    def test_wellformed_one_time_pair_unchanged(self):
        d = {"prices": [{"billing_type": "one_time", "amount_minor": 3700,
                         "schedule": []}]}
        self.assertEqual(vd.validate_trial_disclosure(d, {}), [])

    def test_wellformed_trial_pair_unchanged(self):
        d = {"prices": [{"billing_type": "trial", "amount_minor": 100,
                         "schedule": [{"amount_minor": 2700}]}]}
        disclosure = {"due_now_minor": 100, "trial_length": "30 days",
                      "renewal_amount_minor": 2700,
                      "renewal_date_or_rule": "day 31",
                      "interval": "monthly",
                      "cancellation_terms": "cancel anytime",
                      "access_implications": "access ends at period end"}
        self.assertEqual(vd.validate_trial_disclosure(d, disclosure), [])


if __name__ == "__main__":
    unittest.main()
