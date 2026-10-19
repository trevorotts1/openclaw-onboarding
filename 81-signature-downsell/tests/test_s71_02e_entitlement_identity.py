"""S71-02e: entitlement identity is the DECLARED identifier set.

Semantics proved in scratchpads/S71-02d (ENTITLEMENT-SEMANTICS.md and
entitlement_identity_reference.py): entitlement ids are opaque product
identifiers, not personal data (s82-contract-copy.md:111-112); the launch
schema declares them as non-empty strings with no naming, order or case
rule and no alias field (launch.v1.1.schema.json:109-115); the record's
entitlement mappings are the only vehicle for a declared rename
(02_SHARED_CONTRACTS_AND_ARCHITECTURE.md:39).

Cases below are built from the S71-02d adversarial matrix, not from the
old fixture expectations. Every case is deliverable-isolated: U1 carries
three deliverables and D1 carries one, so every deliverable tier is false
on its count gate and the ENTITLEMENT conjunct alone decides the emit.
test_deliverable_isolation() proves that isolation rather than assuming it.

A different spelling with no declared alias is a different product as far
as this tier can tell. That is the honest failure mode: a real copy is
still caught by the deliverable tiers (class C2), and the entitlement tier
is not asked to guess identity the contract gives it no evidence for.

Run: python3 -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validators"))
import validate_downsell as vd  # noqa: E402

IDENT = "D1-OFFER-IDENTICAL-PROMISE"

# Isolation by count: 3 deliverables versus 1. Every deliverable tier
# requires equal counts, so none of them can fire.
U1_DELIVERABLES = ["Twelve-week flagship implementation programme",
                   "Weekly live build reviews with the founder",
                   "Private operator peer network"]
D1_DELIVERABLES = ["Recordings archive only"]


def offer(slot, oid, entitlements, deliverables, amount, excludes, kind=None):
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


def u1_offer(entitlements):
    return offer("upsell_1", "U1", entitlements, U1_DELIVERABLES,
                 29700, ["D1"])


def d1_offer(entitlements):
    return offer("downsell_1", "D1", entitlements, D1_DELIVERABLES,
                 9700, ["U1"], kind="reduced_scope")


def emits(u1_ids, d1_ids, aliases=None):
    return IDENT in vd.validate_offer_difference(
        u1_offer(u1_ids), d1_offer(d1_ids), entitlement_aliases=aliases)


class DeliverableIsolationTests(unittest.TestCase):
    def test_deliverable_tiers_cannot_fire(self):
        de, ue = D1_DELIVERABLES, U1_DELIVERABLES
        dd, ud = de, ue
        td, tu = vd._full_obligation(d1_offer(["x"])), \
            vd._full_obligation(u1_offer(["x"]))
        self.assertFalse(vd._deliverables_paraphrase_match(dd, ud))
        self.assertFalse(vd._deliverables_shape_match(dd, ud, de, ue, td, tu))
        self.assertFalse(vd._deliverables_partial_paraphrase_match(
            dd, ud, de, ue, td, tu))
        self.assertFalse(vd._deliverables_feature_paraphrase_match(
            dd, ud, de, ue, td, tu))


class ClassAGenuinelyDistinctTests(unittest.TestCase):
    """Genuinely distinct offers: must NOT emit D1-OFFER-IDENTICAL-PROMISE."""

    def test_a1_golden_daybreak_u1_versus_d1(self):
        """The designated G-R5 pair: two products, two prices, two scopes
        (brief.json:17-18)."""
        self.assertFalse(vd._entitlement_sets_match(
            ["golden-daybreak-u1"], ["golden-daybreak-d1"]))
        self.assertFalse(emits(["golden-daybreak-u1"], ["golden-daybreak-d1"]))

    def test_a2_different_id_counts(self):
        self.assertFalse(emits(["golden-daybreak-u1", "golden-daybreak-community"],
                               ["golden-daybreak-d1"]))

    def test_a3_shared_record_prefix_unrelated_words(self):
        self.assertFalse(emits(["golden-daybreak-coaching"],
                               ["golden-daybreak-recordings"]))

    def test_a4_shared_record_prefix_different_tier_suffix(self):
        self.assertFalse(emits(["golden-daybreak-core"],
                               ["golden-daybreak-core-plus"]))

    def test_a5_one_shared_id_set_differs(self):
        """One common member is not set identity: the sets differ."""
        self.assertFalse(emits(["coaching", "community"],
                               ["coaching", "recordings"]))

    def test_a6_empty_versus_non_empty(self):
        self.assertFalse(emits([], ["extra-full"]))
        self.assertFalse(emits(["extra-full"], []))


class ClassBSameOfferRenamedTests(unittest.TestCase):
    """The same offer under renamed ids: MUST emit."""

    def test_b1_identical_ids_exactly(self):
        self.assertTrue(emits(["extra-full"], ["extra-full"]))

    def test_b2_equal_after_declared_alias(self):
        """The record declares the rename; that declaration is the only
        thing that makes two different strings one product."""
        aliases = {"live-coaching": "training-sessions"}
        self.assertTrue(vd._entitlement_sets_match(
            ["training-sessions"], ["live-coaching"], aliases))
        self.assertTrue(emits(["training-sessions"], ["live-coaching"], aliases))

    def test_b2_without_the_declaration_is_not_identity(self):
        self.assertFalse(emits(["training-sessions"], ["live-coaching"]))

    def test_b3_order_differences(self):
        self.assertTrue(emits(["a-1", "b-2", "c-3"], ["c-3", "b-2", "a-1"]))

    def test_b4_case_differences(self):
        self.assertTrue(emits(["Golden-DayBreak-Coaching"],
                              ["golden-daybreak-coaching"]))

    def test_b5_two_full_sets_equal_after_alias(self):
        aliases = {"live-coaching": "training-sessions",
                   "vip-access": "premium-access"}
        self.assertTrue(emits(["training-sessions", "premium-access"],
                              ["vip-access", "live-coaching"], aliases))


class ClassCControlTests(unittest.TestCase):
    def test_c1_unprovable_rename_stays_not_identical(self):
        """Different strings, no declared alias: the entitlement tier cannot
        prove a rename and does not invent one from spelling."""
        self.assertFalse(emits(["training-sessions"], ["live-coaching"]))
        self.assertFalse(vd._entitlement_sets_match(
            ["training-sessions"], ["live-coaching"]))

    def test_c2_deliverable_tier_still_fires(self):
        """The honest failure mode has a backstop: when the offers really
        are the same shape, identical deliverables still emit."""
        u1 = u1_offer(["training-sessions"])
        d1 = d1_offer(["live-coaching"])
        d1["deliverables"] = list(U1_DELIVERABLES)
        self.assertIn(IDENT, vd.validate_offer_difference(u1, d1))

    def test_c3_empty_both_sides_is_unprovable(self):
        self.assertFalse(vd._entitlement_sets_match([], []))
        self.assertFalse(emits([], []))

    def test_c4_malformed_whitespace_id_is_unprovable(self):
        """Schema minLength 1: a whitespace-only id is malformed."""
        self.assertFalse(vd._entitlement_sets_match(["x"], [" "]))
        self.assertFalse(emits(["x"], [" "]))

    def test_c5_prefix_alone_never_carries_a_match(self):
        self.assertFalse(vd._entitlement_sets_match(
            ["acme-records-u1"], ["acme-records-d1"]))
        self.assertTrue(vd._entitlement_sets_match(
            ["acme-records-core"], ["ACME-RECORDS-CORE"]))


if __name__ == "__main__":
    unittest.main()
