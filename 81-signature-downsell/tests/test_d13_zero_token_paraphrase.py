"""D-13 zero-content-token paraphrase cure tests (2026-10-17).

The residual, recorded in review-partials-round2.md (D-13 controls)
and negative-fixture-disposition.md section 4: a same-promise
paraphrase sharing NO content token with U1 anywhere ("Recurring
interactive skill-building broadcasts" / "Invitation-only peer hub" /
"Creator appraisal notes" against the established U1) returned no
violation, because every D-13 tier keys on content tokens: the
paraphrase tier needs every item at the threshold, the shape tier
needs every item in token contact, and the partial-paraphrase tier
needs at least one anchor item. The residual is expressly NOT covered
by ruling S81-DEC-LEXRES-01, which names the D-3, D-8 and N-2 wording
families only; this cure is confined to the D-13 comparison and
touches no D-3, D-8 or N-2 behavior.

The cure is a feature-paraphrase tier: when no D1 deliverable reaches
the paraphrase threshold against any U1 deliverable (lexical
invisibility, so the tier can only see pairs the lexical tiers
cannot), the tier compares structured promise features (cadence,
live event, gated access, named person, evaluation, material) item by
item under the same shape gates as the other structural tiers (same
deliverable count, same entitlement count, lower total), and flags a
full feature-signature match with D1-OFFER-IDENTICAL-PROMISE for
owner decision (spec 11 section 4).

This file deliberately supersedes the behavioral pin in
tests/test_partials_cure_round2.py
(test_zero_token_paraphrase_is_the_documented_residual), whose own
docstring states that a future semantic method closing the residual
must update that test deliberately, with the claim correction beside
it. The claim correction is this file plus the cure report at
rooms/S81/build-lane-d13-cure-report.md; the round 2 file itself is
outside this lane's write boundary and is left for its owner to
update.

Run: python3 -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validators"))
import validate_downsell as vd  # noqa: E402

IDENT = "D1-OFFER-IDENTICAL-PROMISE"

U1V = {"offer_id": "U1", "slot": "upsell_1",
       "entitlement_ids": ["training-sessions", "private-community",
                           "founder-feedback"],
       "deliverables": ["Weekly live training sessions",
                        "Private community access",
                        "Founder feedback reviews"],
       "excludes": ["D1"], "requires": [],
       "prices": [{"amount_minor": 6700, "schedule": []}]}

RECORDED_RESIDUAL = (
    ["Recurring interactive skill-building broadcasts",
     "Invitation-only peer hub",
     "Creator appraisal notes"], ["zz-1", "zz-2", "zz-3"])

FRESH_ESCAPES = [
    ("E1", ["Ongoing interactive technique broadcasts",
            "Restricted insiders lounge",
            "Originator appraisal memos"], ["e1-a", "e1-b", "e1-c"]),
    ("E2", ["Continual participatory practice webcasts",
            "Vetted colleagues salon",
            "Producer appraisal notes"], ["e2-a", "e2-b", "e2-c"]),
    ("E3", ["Repeated real-time technique demonstrations",
            "Invite-only collaborators den",
            "Headliner grading notes"], ["e3-a", "e3-b", "e3-c"]),
]


def d1_offer(deliverables, entitlements, amount=3700,
             kind="reduced_scope"):
    return {"offer_id": "D1", "slot": "downsell_1",
            "entitlement_ids": entitlements,
            "deliverables": deliverables,
            "excludes": ["U1"], "requires": [],
            "difference_kind": kind,
            "rationale": "Smaller commitment for visitors who declined.",
            "prices": [{"amount_minor": amount, "schedule": []}]}


class D13ZeroTokenEscapeTests(unittest.TestCase):
    """The recorded residual and three fresh same-promise paraphrases
    sharing no content token with U1 are now caught, under both
    scope/price claim kinds."""

    def assert_zero_contact(self, deliverables):
        u1_tokens = [vd._content_tokens(x) for x in U1V["deliverables"]]
        for item in deliverables:
            tokens = vd._content_tokens(item)
            for cand in u1_tokens:
                self.assertFalse(
                    tokens & cand,
                    f"{item!r} shares a content token with U1: "
                    f"{tokens & cand}")
                self.assertLess(vd._jaccard(tokens, cand), 0.4)

    def test_recorded_residual_is_zero_contact(self):
        self.assert_zero_contact(RECORDED_RESIDUAL[0])

    def test_recorded_residual_caught_reduced_scope(self):
        d = d1_offer(*RECORDED_RESIDUAL)
        self.assertIn(IDENT, vd.validate_offer_difference(U1V, d))

    def test_recorded_residual_caught_lower_total_price(self):
        d = d1_offer(*RECORDED_RESIDUAL, kind="lower_total_price")
        self.assertIn(IDENT, vd.validate_offer_difference(U1V, d))

    def test_fresh_escapes_are_zero_contact(self):
        for _name, deliverables, _ids in FRESH_ESCAPES:
            self.assert_zero_contact(deliverables)

    def test_fresh_escapes_caught_reduced_scope(self):
        for name, deliverables, ids in FRESH_ESCAPES:
            with self.subTest(pair=name):
                d = d1_offer(deliverables, ids)
                self.assertIn(IDENT, vd.validate_offer_difference(U1V, d))

    def test_fresh_escapes_caught_lower_total_price(self):
        for name, deliverables, ids in FRESH_ESCAPES:
            with self.subTest(pair=name):
                d = d1_offer(deliverables, ids, kind="lower_total_price")
                self.assertIn(IDENT, vd.validate_offer_difference(U1V, d))


class D13ZeroTokenControlTests(unittest.TestCase):
    """Genuinely different offers and the structural gates: the feature
    tier must not flag a different promise, and must stay silent when
    any of its shape gates is unmet."""

    def test_reviewer_different_offer_control_passes(self):
        # The round 2 re-review's own discriminating control: equal
        # counts, lower total, only weak fold contact ("lesson" folds
        # to "training"), and a wholly different feature signature.
        d = d1_offer(
            ["Beginner guitar lesson library",
             "Monthly recipe newsletter",
             "Home workout video archive"], ["g-1", "g-2", "g-3"],
            amount=999)
        self.assertEqual(vd.validate_offer_difference(U1V, d), [])

    def test_different_domain_offer_passes(self):
        d = d1_offer(
            ["Recorded piano masterclass vault",
             "Downloadable fingering chart pack",
             "Tuning reference audio set"], ["c2-a", "c2-b", "c2-c"],
            amount=2100)
        self.assertEqual(vd.validate_offer_difference(U1V, d), [])

    def test_same_domain_different_promise_passes(self):
        # Same broad topic as U1 (learning), genuinely different
        # promise: self-paced material and an email inbox instead of
        # live events, gated access and founder evaluation.
        d = d1_offer(
            ["Self-paced recorded curriculum",
             "Downloadable worksheet bundle",
             "Email question inbox with weekday replies"],
            ["c3-a", "c3-b", "c3-c"], amount=2900)
        self.assertEqual(vd.validate_offer_difference(U1V, d), [])

    def test_feature_match_under_terms_kind_not_flagged(self):
        # Changed payment terms is a legitimate difference kind (doc 02
        # section 3): the identical-promise tiers, the feature tier
        # included, judge only scope/price claims.
        d = d1_offer(*RECORDED_RESIDUAL, amount=6700,
                     kind="changed_payment_terms")
        self.assertNotIn(IDENT, vd.validate_offer_difference(U1V, d))

    def test_feature_match_at_equal_total_not_flagged(self):
        d = d1_offer(*RECORDED_RESIDUAL, amount=6700)
        self.assertNotIn(IDENT, vd.validate_offer_difference(U1V, d))

    def test_feature_match_with_fewer_entitlements_not_flagged(self):
        d = d1_offer(RECORDED_RESIDUAL[0], ["zz-1", "zz-2"])
        self.assertNotIn(IDENT, vd.validate_offer_difference(U1V, d))

    def test_genuine_reduced_scope_still_passes(self):
        d = d1_offer(["Weekly live training sessions"], ["live-coaching"])
        self.assertEqual(vd.validate_offer_difference(U1V, d), [])


class D13FeatureTierSeparationTests(unittest.TestCase):
    """The feature tier sees only what the lexical tiers cannot: when
    an anchor item exists, the tier itself stays silent and the older
    tiers do the flagging, so no verdict the lexical tiers reach is
    widened."""

    def test_tier_silent_when_anchor_exists(self):
        # Paraphrase A (round 2 governing probe): items in token
        # contact with an anchor at the threshold. The overall verdict
        # still fires, but the feature tier alone returns False.
        d1_items = ["Scheduled real-time instruction webinars",
                    "Closed member circle admission",
                    "Creator appraisal notes"]
        self.assertFalse(vd._deliverables_feature_paraphrase_match(
            d1_items, U1V["deliverables"], ["zz-1", "zz-2", "zz-3"],
            U1V["entitlement_ids"], 3700, 6700))
        d = d1_offer(d1_items, ["zz-1", "zz-2", "zz-3"])
        self.assertIn(IDENT, vd.validate_offer_difference(U1V, d))

    def test_promise_features_of_established_u1(self):
        self.assertEqual(
            vd._promise_features("Weekly live training sessions"),
            {"cadence", "live_event"})
        self.assertEqual(
            vd._promise_features("Private community access"),
            {"gated_access"})
        self.assertEqual(
            vd._promise_features("Founder feedback reviews"),
            {"person_led", "evaluation"})


if __name__ == "__main__":
    unittest.main()
