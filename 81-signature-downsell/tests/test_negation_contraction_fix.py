"""Ruling S81-DEC-LEXRES-01 tests (2026-10-16): the contracted
negation false positive on the loss-of-purchase scan.

The round 3 re-review (review-partials-round3.md) recorded one
over-fire against N-2: "You won't lose what you bought with us."
returned D1-COPY-FALSE-LOSS-OF-PURCHASE. The mechanism: _norm
splits the contraction into "won t", so the plain-lose branch's
negation guard, two fixed-width lookbehinds for "never " and
"not ", never saw the negation, and a reassurance was flagged as
a false loss-of-purchase threat.

The fix is mechanism-level, in the loss-threat path only: the
loss scan feeds its patterns text whose "n't" ending was
expanded to " not" before normalization (_loss_scan_text), and
the threat-verb branches that carried no guard (take away,
remove/revoke, forfeit, cancel, delete/wipe/terminate/erase,
cut off) now carry the same never/not lookbehind pair, with the
object-first cut-off span tempered so it cannot cross a negation
word. No coverage list was widened: the D-3, D-8 and N-2
coverage tails are the owner-accepted limitation recorded in
references/terms-entitlement-review.md under the same ruling,
and the last class below pins that this fix left those verdicts
exactly as they were.

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


def page_with(text):
    page = copy.deepcopy(PAGE)
    page["sections"][0]["body"] += " " + text
    return page


class ContractedReassuranceTests(unittest.TestCase):
    # Every sentence here is a negated loss statement: a
    # reassurance, not a threat. Before the fix, all but four of
    # them returned the loss code (the probe reproduced each one).
    CONTRACTED = [
        "You won't lose what you bought with us.",
        "We won't take away what you purchased.",
        "You don't lose your purchase.",
        "We won't remove what you purchased.",
        "We won't delete what you bought.",
        "You won't forfeit what you bought.",
        "We won't cancel what you bought.",
        "Your access won't be cut off.",
        "Your bought program won't disappear from your account.",
        "You can't lose what you bought with us.",
        "We wouldn't remove what you purchased.",
        "We shouldn't take away what you bought.",
        "We didn't erase what you bought.",
        "It doesn't delete what you purchased.",
        "Your access isn't cut off if you decline.",
        "Your order won't be cancelled if you skip this.",
        "What you bought won't be revoked.",
    ]

    def test_contracted_family_carries_no_loss_code(self):
        for text in self.CONTRACTED:
            with self.subTest(text=text):
                self.assertNotIn(LOSS, vd.validate_copy(page_with(text)))

    def test_named_ruling_sentence_is_fully_clean(self):
        # The exact sentence the ruling names: before the fix it
        # returned the loss code; it must now return no codes at
        # all on the valid page.
        self.assertEqual(
            [], vd.validate_copy(page_with(
                "You won't lose what you bought with us.")))


class UncontractedThreatTests(unittest.TestCase):
    # The recorded threat forms that fired before the fix must
    # still fire: the guard only suppresses a threat verb whose
    # immediate predecessor is the negation itself.
    THREATS = [
        "We will delete what you bought.",
        "Decline and you lose what you bought.",
        "We will wipe what you purchased.",
        "Say no and your access gets cut off.",
        "Decline and we terminate what you purchased.",
        "Walk away and we will erase what you bought.",
        "Decline and your purchase is gone for good.",
        "Skip this and we will take away the access you already bought.",
        "We cancel what you bought.",
        "Decline and you forfeit what you bought.",
        "Say no and we cut off your access today.",
        "Turn it down and you will lose what you purchased.",
    ]

    def test_uncontracted_threats_still_fire(self):
        for text in self.THREATS:
            with self.subTest(text=text):
                self.assertIn(LOSS, vd.validate_copy(page_with(text)))


class NegationAndTruthfulControlTests(unittest.TestCase):
    CONTROLS = [
        "You never lose what you bought with us.",
        "Your bought program never disappears from your account.",
        "If you cancel, what you already bought stays yours until "
        "the paid period ends.",
        "If you stop a payment, access ends when the current paid "
        "period ends.",
        "You can cancel anytime before a renewal charge.",
    ]

    def test_controls_carry_no_loss_code(self):
        for text in self.CONTROLS:
            with self.subTest(text=text):
                self.assertNotIn(LOSS, vd.validate_copy(page_with(text)))

    def test_valid_fixture_stays_clean(self):
        self.assertEqual([], vd.validate_copy(copy.deepcopy(PAGE)))


class CoverageUntouchedTests(unittest.TestCase):
    # The ruling accepted the coverage boundary; it did not widen
    # it. These pins hold the recorded verdicts on both sides of
    # that boundary exactly as the round 3 re-review left them.
    def test_scarcity_recorded_verdicts_unchanged(self):
        for text in ("Seats are limited at this level.",
                     "Only a couple of spots remain at this price."):
            with self.subTest(text=text):
                self.assertIn(SCARCITY, vd.validate_copy(page_with(text)))
        for text in ("Capacity is limited for this cohort.",
                     "Registration is capped for this round.",
                     "The price goes back up on Monday at this rate.",
                     "Only while seats remain at this price."):
            with self.subTest(text=text):
                self.assertNotIn(SCARCITY, vd.validate_copy(page_with(text)))

    def test_private_label_recorded_verdicts_unchanged(self):
        self.assertIn(
            PRIVATE, vd.validate_copy(page_with(
                "Internal notes for the team.")))
        for text in ("Internal checklist for the launch team.",
                     "Confidential workbook, not for buyers."):
            with self.subTest(text=text):
                self.assertNotIn(PRIVATE, vd.validate_copy(page_with(text)))

    def test_loss_limitation_forms_still_escape(self):
        for text in ("Pass and we pull what you purchased.",
                     "Decline and your subscription gets cut off.",
                     "Decline and you will lose the access you "
                     "already paid for.",
                     "Say no and the course you bought gets wiped."):
            with self.subTest(text=text):
                self.assertNotIn(LOSS, vd.validate_copy(page_with(text)))


if __name__ == "__main__":
    unittest.main()
