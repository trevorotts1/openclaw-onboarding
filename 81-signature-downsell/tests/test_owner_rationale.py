"""RFX-013: a recorded owner decision for a lower-total-price D1 that keeps U1's promise.

Spec 11 section 4 (references/offer-alternatives.md): "If D1 is equivalent to U1 at a lower
price with no approved rationale, STOP: flag for owner decision." The flag is
D1-OFFER-IDENTICAL-PROMISE. A difference-table row of kind lower_total_price may carry the owner's
recorded decision as owner_rationale (text, decided_by, ISO-8601 decided_at, and approval_ref or
decision_ref); only a COMPLETE block on that one kind lifts the flag. Every other check stands.
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

try:
    import jsonschema
except ImportError:
    jsonschema = None

IDENT = "D1-OFFER-IDENTICAL-PROMISE"
INCOMPLETE = "D1-OFFER-OWNER-RATIONALE-INCOMPLETE"
WRONG_KIND = "D1-OFFER-OWNER-RATIONALE-WRONG-KIND"
DELIVERABLES = ["Weekly live coaching call", "Private community access", "Template vault"]
OWNER = {"text": "TEST ONLY: owner keeps the full promise at a lower one-time total for decliners.",
         "decided_by": "TEST-OWNER", "decided_at": "2026-11-20T10:00:00-05:00",
         "approval_ref": "TEST-APPROVAL-D1-PRICE"}
U1 = {"offer_id": "U1", "slot": "upsell_1", "entitlement_ids": ["ent-full"],
      "deliverables": DELIVERABLES, "excludes": ["D1"],
      "prices": [{"amount_minor": 9700, "schedule": []}]}
# The measured defect: same deliverables as U1, genuinely lower total, kind lower_total_price.
D1 = {"offer_id": "D1", "slot": "downsell_1", "entitlement_ids": ["ent-lite"],
      "deliverables": list(DELIVERABLES), "excludes": ["U1"],
      "difference_kind": "lower_total_price",
      "rationale": "TEST ONLY: decliners object to the total, not the scope.",
      "prices": [{"amount_minor": 4700, "schedule": []}]}


def d1(**changes):
    d = copy.deepcopy(D1)
    d.update(changes)
    return d


class OfferDifferenceOwnerRationaleTests(unittest.TestCase):

    def test_identical_deliverables_without_owner_rationale_still_refused(self):
        self.assertEqual(vd.validate_offer_difference(U1, d1()), [IDENT])

    def test_identical_deliverables_with_complete_owner_rationale_passes(self):
        self.assertEqual(vd.validate_offer_difference(U1, d1(owner_rationale=OWNER)), [])

    def test_decision_ref_serves_in_place_of_approval_ref(self):
        block = {k: v for k, v in OWNER.items() if k != "approval_ref"}
        block["decision_ref"] = "TEST-DECISION-LOG-7"
        self.assertEqual(vd.validate_offer_difference(U1, d1(owner_rationale=block)), [])

    def test_every_incomplete_owner_rationale_refuses(self):
        no_ref = {k: v for k, v in OWNER.items() if k != "approval_ref"}
        cases = {"missing text": {k: v for k, v in OWNER.items() if k != "text"},
                 "blank text": dict(OWNER, text="   "),
                 "missing decided_by": {k: v for k, v in OWNER.items() if k != "decided_by"},
                 "blank decided_by": dict(OWNER, decided_by=""),
                 "missing decided_at": {k: v for k, v in OWNER.items() if k != "decided_at"},
                 "decided_at not a date": dict(OWNER, decided_at="last Tuesday"),
                 "no reference": no_ref,
                 "blank reference": dict(no_ref, approval_ref=" ", decision_ref=""),
                 "non-string reference": dict(no_ref, approval_ref=7),
                 "not an object": "owner said yes",
                 "null": None}
        for name, block in cases.items():
            with self.subTest(name):
                v = vd.validate_offer_difference(U1, d1(owner_rationale=block))
                self.assertIn(IDENT, v)
                self.assertIn(INCOMPLETE, v)

    def test_owner_rationale_never_lifts_a_reduced_scope_claim(self):
        v = vd.validate_offer_difference(
            U1, d1(difference_kind="reduced_scope", owner_rationale=OWNER))
        self.assertIn(IDENT, v)
        self.assertIn(WRONG_KIND, v)

    def test_owner_rationale_does_not_prove_a_lower_total(self):
        v = vd.validate_offer_difference(
            U1, d1(owner_rationale=OWNER, prices=[{"amount_minor": 9700, "schedule": []}]))
        self.assertEqual(v, ["D1-OFFER-LOWER-TOTAL-NOT-PROVEN"])

    def test_terms_change_masking_a_total_change_still_refused(self):
        v = vd.validate_offer_difference(U1, d1(difference_kind="changed_payment_terms"))
        self.assertEqual(v, ["D1-OFFER-TERMS-CHANGE-MASKS-TOTAL-CHANGE"])
        v = vd.validate_offer_difference(
            U1, d1(difference_kind="changed_payment_terms", owner_rationale=OWNER))
        self.assertIn("D1-OFFER-TERMS-CHANGE-MASKS-TOTAL-CHANGE", v)
        self.assertIn(WRONG_KIND, v)

    def test_other_refusals_still_fire_beside_a_complete_owner_rationale(self):
        bad = d1(owner_rationale=OWNER, slot="upsell_1", excludes=[], rationale=" ",
                 entitlements_removed_vs_u1=["ent-main"])
        v = vd.validate_offer_difference(dict(U1, excludes=[]), bad,
                                         {"entitlement_ids": ["ent-main"]})
        for code in ("D1-OFFER-WRONG-SLOT", "D1-OFFER-EXCLUDES-U1-MISSING",
                     "D1-OFFER-U1-EXCLUDES-D1-MISSING", "D1-OFFER-REMOVES-BASE-PURCHASE",
                     "D1-OFFER-RATIONALE-MISSING"):
            self.assertIn(code, v)

    def test_other_kinds_unchanged_without_owner_rationale(self):
        scoped = d1(difference_kind="reduced_scope", deliverables=DELIVERABLES[:1])
        self.assertEqual(vd.validate_offer_difference(U1, scoped), [])
        same_total = d1(difference_kind="changed_payment_terms",
                        prices=[{"amount_minor": 4700, "schedule": [{"amount_minor": 5000}]}])
        self.assertEqual(vd.validate_offer_difference(U1, same_total), [])
        self.assertIn("D1-OFFER-ACCESS-CHANGE-UNPROVEN", vd.validate_offer_difference(
            U1, d1(difference_kind="changed_access_terms", prices=U1["prices"],
                   entitlement_ids=U1["entitlement_ids"])))


EXT = json.loads((ROOT / "fixtures" / "valid-downsell-result.json").read_text())[
    "downsell_result_extension"]
SCHEMA = json.loads((ROOT / "schemas" / "downsell-result-extension.schema.json").read_text())


def ext_with(block, kind="lower_total_price"):
    e = copy.deepcopy(EXT)
    e["difference_matrix"].update(difference_kind=kind, owner_rationale=block)
    return e


class ResultExtensionShowsOwnerRationaleTests(unittest.TestCase):

    def test_complete_block_on_lower_total_price_is_accepted(self):
        self.assertEqual(vd.validate_result_extension(ext_with(OWNER)), [])

    def test_incomplete_block_is_refused(self):
        block = {k: v for k, v in OWNER.items() if k != "approval_ref"}
        self.assertIn("D1-RESULT-OWNER-RATIONALE-INCOMPLETE",
                      vd.validate_result_extension(ext_with(block)))

    def test_block_on_another_kind_is_refused(self):
        self.assertIn("D1-RESULT-OWNER-RATIONALE-WRONG-KIND",
                      vd.validate_result_extension(ext_with(OWNER, "changed_payment_terms")))

    def test_fixture_without_a_block_is_unchanged(self):
        self.assertEqual(vd.validate_result_extension(EXT), [])

    @unittest.skipIf(jsonschema is None, "jsonschema not installed")
    def test_schema_admits_the_block_and_rejects_unknown_keys(self):
        validator = jsonschema.Draft202012Validator(SCHEMA)
        self.assertEqual(list(validator.iter_errors(ext_with(OWNER))), [])
        self.assertTrue(list(validator.iter_errors(ext_with(dict(OWNER, note="x")))))
        self.assertTrue(list(validator.iter_errors(ext_with({"text": "x"}))))


if __name__ == "__main__":
    unittest.main()
