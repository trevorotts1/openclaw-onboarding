"""Round 3 cure tests for the S81 partials (2026-10-16).

The round 2 re-review (review-partials-round2.md) confirmed D-13,
the prefix-USD and bucks forms, and the nested malformed prices
case FIXED, and kept exactly three items PARTIAL, each through the
same list-bound mechanism its defect named:

- D-3 scarcity: the plain limited predicate ("Seats are
  limited"), the "no longer" availability claim with an auxiliary
  inserted ("will no longer be available"), and the bare
  exhortation carrying its deadline ("Act fast, this deal ends
  soon"; "When it is gone, it is gone").
- D-8 private labels (minor): the internal document nouns outside
  the list (notes, paper, handbook), "confidential material", and
  the audience forms "company use only" and "house copy".
- N-2 loss threats: the ordinary verbs outside the list (delete,
  wipe, terminate, erase in the active voice), the plain
  lose-what-you-bought form, the cut-off forms, and "your
  purchase is gone".

This file pins the round 3 cure, which widens each family by
mechanism: the limited predicate anchored on offer subjects, the
no-longer claim with its auxiliaries, exhortation plus a deadline
in the same sentence, the internal document-noun class (people
doing the work, like internal coaches, are not document nouns and
stay clean), confidential plus content nouns, use-only and
not-for-outside audience forms, and the remaining loss verbs, all
still keyed to the bought object with the seller-subject cancel
discipline and the negation guard intact. Held-out variants
(wordings that appear in no review) are pinned beside each
governing set. Nothing here edits or weakens a pre-existing test.
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


def page_with(text, evidence=False):
    page = copy.deepcopy(PAGE)
    page["sections"][0]["body"] += " " + text
    if evidence:
        page["scarcity_evidence_ref"] = "evidence/capacity-note.txt"
    return page


class D3ScarcityRound3Tests(unittest.TestCase):
    GOVERNING = [
        "After Friday this bonus will no longer be available to new members.",
        "Enrollment is limited, so claim your seat.",
        "Seats are limited at this level.",
        "Space is limited in this cohort.",
        "Act fast, this deal ends soon.",
        "When it is gone, it is gone, so claim yours.",
    ]
    HELD_OUT = [
        "Membership is limited for this enrollment round.",
        "After Sunday the replay will no longer be offered at this price.",
        "Act now, this price ends at midnight.",
        "Once the seats are gone, they are gone until next year.",
        "Openings are limited this month.",
    ]

    def test_governing_variants_caught(self):
        for text in self.GOVERNING:
            with self.subTest(text=text):
                self.assertIn(SCARCITY, vd.validate_copy(page_with(text)))

    def test_held_out_variants_caught(self):
        for text in self.HELD_OUT:
            with self.subTest(text=text):
                self.assertIn(SCARCITY, vd.validate_copy(page_with(text)))

    def test_truthful_limited_word_not_flagged(self):
        for text in ("A limited warranty covers the venue equipment.",
                     "The workbook has a limited set of exercises."):
            with self.subTest(text=text):
                self.assertNotIn(SCARCITY, vd.validate_copy(page_with(text)))

    def test_limited_predicate_with_evidence_ref_passes(self):
        page = page_with("Seats are limited at this level.", evidence=True)
        self.assertNotIn(SCARCITY, vd.validate_copy(page))

    def test_valid_fixture_stays_clean(self):
        self.assertEqual([], vd.validate_copy(copy.deepcopy(PAGE)))


class D8PrivateLabelRound3Tests(unittest.TestCase):
    GOVERNING = [
        "Internal notes for the team.",
        "Internal paper for the team.",
        "Internal handbook for coaches.",
        "Confidential material, do not share.",
        "For company use only, not for clients.",
        "House copy, not for outside distribution.",
        "Working draft, internal working paper for the ops team.",
    ]
    HELD_OUT = [
        "Internal manual for new hires.",
        "Confidential content, not for students.",
        "For staff use only, keep off the public page.",
        "Internal file for the launch team.",
        "Internal packet for the spring launch.",
    ]

    def test_governing_variants_caught(self):
        for text in self.GOVERNING:
            with self.subTest(text=text):
                self.assertIn(PRIVATE, vd.validate_copy(page_with(text)))

    def test_held_out_variants_caught(self):
        for text in self.HELD_OUT:
            with self.subTest(text=text):
                self.assertIn(PRIVATE, vd.validate_copy(page_with(text)))

    def test_public_copy_controls_not_flagged(self):
        for text in ("This section explains your access.",
                     "Your payment details stay confidential with us.",
                     "This page is for members only.",
                     "Our confidentiality promise protects your purchase data."):
            with self.subTest(text=text):
                self.assertNotIn(PRIVATE, vd.validate_copy(page_with(text)))

    def test_internal_people_doing_work_not_flagged(self):
        # Judgment call pinned: "internal" labels a document, a
        # file-like artifact, an audience restriction or a
        # do-not-share marker. People doing the work are ordinary
        # public prose; people nouns are not in the document class.
        self.assertNotIn(
            PRIVATE,
            vd.validate_copy(page_with("Our internal coaches review every plan.")))


class N2LossThreatRound3Tests(unittest.TestCase):
    GOVERNING = [
        "We will delete what you bought.",
        "Decline and you lose what you bought.",
        "We will wipe what you purchased.",
        "Say no and your access gets cut off.",
        "Decline and we terminate what you purchased.",
        "Walk away and we will erase what you bought.",
        "Decline and your purchase is gone for good.",
    ]
    HELD_OUT = [
        "Pass and we will delete the course you purchased.",
        "Refuse and your order gets terminated.",
        "Say no and we cut off your access today.",
        "Turn it down and you will lose what you purchased.",
        "Skip this and your purchase is gone by morning.",
    ]

    def test_governing_variants_caught(self):
        for text in self.GOVERNING:
            with self.subTest(text=text):
                self.assertIn(LOSS, vd.validate_copy(page_with(text)))

    def test_held_out_variants_caught(self):
        for text in self.HELD_OUT:
            with self.subTest(text=text):
                self.assertIn(LOSS, vd.validate_copy(page_with(text)))

    def test_buyer_cancels_and_keeps_purchase_not_flagged(self):
        for text in (
                "If you cancel, what you already bought stays yours "
                "until the paid period ends.",
                "If you cancel, your access continues until the end "
                "of the paid period, and what you bought stays yours."):
            with self.subTest(text=text):
                self.assertNotIn(LOSS, vd.validate_copy(page_with(text)))

    def test_negated_forms_carry_no_loss_code(self):
        for text in ("Your bought program never disappears from your account.",
                     "You never lose what you bought with us."):
            with self.subTest(text=text):
                self.assertNotIn(LOSS, vd.validate_copy(page_with(text)))

    def test_truthful_access_ends_not_flagged(self):
        text = "If you stop a payment, access ends when the current paid period ends."
        self.assertNotIn(LOSS, vd.validate_copy(page_with(text)))


if __name__ == "__main__":
    unittest.main()
