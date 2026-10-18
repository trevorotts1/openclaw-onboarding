"""S71-02b: entitlement id prefix must not carry a set match.

Proven defect (baseline blob 24dcf86db71b7ab66b7245ef2bbf3170b395898b):
_entitlement_sets_match treated two equal-length id lists as one set
under renamed ids whenever every id token-matched a distinct id at
Jaccard >= 0.5. The content tokens of golden-daybreak-u1 and
golden-daybreak-d1 are {golden, daybreak, u1} and {golden, daybreak,
d1}; the shared record prefix golden-daybreak supplies two of three
tokens on each side, the Jaccard is exactly 0.5, and two distinct
products were reported as one entitlement renamed -- so
validate_offer_difference emitted D1-OFFER-IDENTICAL-PROMISE from the
same_entitlements conjunct.

The cure discounts the tokens both ids share (the record/launch
prefix) before comparing, so only distinguishing tokens can carry a
match. A genuine rename still matches when the distinguishing token
sets agree after stemming, synonym folding and token-order
normalisation.

Both directions are pinned below, and the second direction is the
class control: it proves the cure discriminates rather than merely
lowering every score.
"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validators"))
import validate_downsell as vd  # noqa: E402

IDENT = "D1-OFFER-IDENTICAL-PROMISE"

U1_ENTITLEMENT = "golden-daybreak-u1"
D1_ENTITLEMENT = "golden-daybreak-d1"

# U1 carries three deliverables, D1 two, so the deliverable tiers
# (same_deliverables, shape, partial, feature) are all false by count
# and the entitlement conjunct is the only one that can emit.
U1_DELIVERABLES = ["Twelve-week flagship implementation programme",
                   "Weekly live build reviews with the founder",
                   "Private operator peer network"]
D1_DELIVERABLES = ["Four-week starter implementation sprint",
                   "Two group onboarding calls"]


def offer(slot, oid, entitlements, deliverables, amount, excludes,
          kind=None):
    out = {"offer_id": oid, "slot": slot,
           "entitlement_ids": list(entitlements),
           "deliverables": list(deliverables),
           "excludes": list(excludes), "requires": [],
           "prices": [{"amount_minor": amount, "schedule": []}]}
    if kind:
        out["difference_kind"] = kind
        out["rationale"] = ("Smaller commitment for visitors who declined "
                            "the full upgrade on commitment size.")
    return out


def u1_offer(entitlements=None):
    return offer("upsell_1", "U1",
                 [U1_ENTITLEMENT] if entitlements is None else entitlements,
                 U1_DELIVERABLES, 29700, ["D1"])


def d1_offer(entitlements=None):
    return offer("downsell_1", "D1",
                 [D1_ENTITLEMENT] if entitlements is None else entitlements,
                 D1_DELIVERABLES, 9700, ["U1"], kind="reduced_scope")


class SharedPrefixRegressionTests(unittest.TestCase):
    """(a) The recorded defect: distinct offers under one record prefix."""

    def test_prefix_pair_is_not_one_renamed_set(self):
        self.assertFalse(vd._entitlement_sets_match(
            [U1_ENTITLEMENT], [D1_ENTITLEMENT]))

    def test_distinct_offers_do_not_emit_identical_promise(self):
        violations = vd.validate_offer_difference(
            u1_offer(), d1_offer())
        self.assertNotIn(IDENT, violations)
        self.assertEqual(violations, [])

    def test_only_the_entitlement_conjunct_differs(self):
        """Guards the isolation above: the deliverable tiers stay false,
        so the assertion really pins the entitlement conjunct."""
        d1, u1 = d1_offer(), u1_offer()
        de, ue = d1["entitlement_ids"], u1["entitlement_ids"]
        dd, ud = d1["deliverables"], u1["deliverables"]
        td, tu = vd._full_obligation(d1), vd._full_obligation(u1)
        self.assertFalse(vd._deliverables_paraphrase_match(dd, ud))
        self.assertFalse(vd._deliverables_shape_match(dd, ud, de, ue, td, tu))
        self.assertFalse(vd._deliverables_partial_paraphrase_match(
            dd, ud, de, ue, td, tu))
        self.assertFalse(vd._deliverables_feature_paraphrase_match(
            dd, ud, de, ue, td, tu))

    def test_shared_prefix_still_matches_on_the_other_side(self):
        """Mirror of the defect pair: prefix plus a shared distinguishing
        token set is still one id renamed."""
        self.assertTrue(vd._entitlement_sets_match(
            ["golden-daybreak-core"], ["daybreak-golden-core"]))


class GenuineRenameControlTests(unittest.TestCase):
    """(b) Class control: D-13 detection must still work."""

    def test_renamed_ids_without_record_prefix_match(self):
        self.assertTrue(vd._entitlement_sets_match(
            ["daybreak-fasttrack"], ["fasttrack-daybreak"]))

    def test_renamed_ids_still_emit_identical_promise(self):
        self.assertIn(IDENT, vd.validate_offer_difference(
            u1_offer(["daybreak-fasttrack"]),
            d1_offer(["fasttrack-daybreak"])))

    def test_stem_and_synonym_folding_still_match(self):
        self.assertTrue(vd._entitlement_sets_match(
            ["training-sessions"], ["session-training"]))

    def test_distinguishing_token_keeps_ids_apart(self):
        self.assertFalse(vd._entitlement_sets_match(
            ["extra-lite"], ["extra-full"]))
        self.assertFalse(vd._entitlement_sets_match(
            ["golden-daybreak-u1-bonus"], ["golden-daybreak-d1-bonus"]))

    def test_exact_same_id_still_matches_by_identity(self):
        self.assertIn(IDENT, vd.validate_offer_difference(
            u1_offer(["golden-daybreak-u1"]),
            d1_offer(["golden-daybreak-u1"])))


if __name__ == "__main__":
    unittest.main()
