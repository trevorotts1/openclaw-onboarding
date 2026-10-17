"""Skill 81 validator tests, including the doc 18 section 6 derivation checks
and the spec 11 section 10 negative cases that are locally testable (L0/L1).
Run: python3 -m unittest discover -s tests -v
"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validators"))
from validate_downsell import (validate_copy, validate_offer_difference,
                               validate_trial_disclosure, check_entry_guard)

VALID = json.loads((ROOT / "fixtures" / "valid-downsell-page.json").read_text())["page"]


def fresh():
    return copy.deepcopy(VALID)


U1 = {"offer_id": "U1", "slot": "upsell_1", "entitlement_ids": ["extra-full"],
      "deliverables": ["A", "B", "C"], "excludes": ["D1"], "requires": [],
      "prices": [{"amount_minor": 6700, "schedule": []}]}
D1 = {"offer_id": "D1", "slot": "downsell_1", "entitlement_ids": ["extra-lite"],
      "deliverables": ["A", "B"], "excludes": ["U1"], "requires": [],
      "difference_kind": "reduced_scope", "rationale": "Same core, smaller scope for visitors who declined the full upgrade on commitment size.",
      "prices": [{"amount_minor": 3700, "schedule": []}]}


class CopyDerivationTests(unittest.TestCase):
    def test_valid_page_passes(self):
        self.assertEqual(validate_copy(fresh()), [])

    def test_exactly_eight_sections(self):
        p = fresh(); p["sections"] = p["sections"][:7]
        self.assertIn("D1-COPY-SECTION-COUNT", validate_copy(p))

    def test_cta_in_every_section(self):
        p = fresh(); p["sections"][5]["cta"] = None
        self.assertIn("D1-COPY-MISSING-CTA-S6", validate_copy(p))

    def test_all_ctas_same_action(self):
        p = fresh(); p["sections"][2]["cta"]["action_ref"] = "some-other-action"
        self.assertIn("D1-COPY-CTA-ACTION-DIVERGES", validate_copy(p))

    def test_no_reintroduction_of_original_8_to_11(self):
        p = fresh()
        p["sections"][3]["role"] = "benefit_1"
        self.assertIn("D1-COPY-ORIGINAL-8-11-REINTRODUCED", validate_copy(p))

    def test_seven_distinct_missed_items(self):
        p = fresh(); p["sections"][7]["missed_out_items"] = p["sections"][7]["missed_out_items"][:6]
        self.assertIn("D1-COPY-MISSED-COUNT-NOT-SEVEN", validate_copy(p))

    def test_duplicated_missed_items_rejected(self):
        p = fresh()
        items = p["sections"][7]["missed_out_items"]
        items[6] = items[0]
        self.assertIn("D1-COPY-MISSED-DUPLICATED", validate_copy(p))

    def test_sample_heading_is_canonical(self):
        p = fresh()
        self.assertEqual(p["sections"][7]["heading"], "When Time Runs Out")
        self.assertEqual(validate_copy(p), [])

    def test_prose_heading_needs_recorded_normalization(self):
        # Exact corpus prose string (capital T on Times), read firsthand in doc 20.
        p = fresh(); p["sections"][7]["heading"] = "When Times Run Out"
        self.assertIn("D1-COPY-HEADING-NORMALIZATION-REQUIRED", validate_copy(p))

    def test_canonical_heading_with_trailing_colon_passes(self):
        p = fresh(); p["sections"][7]["heading"] = "When Time Runs Out:"
        self.assertEqual(validate_copy(p), [])

    def test_malformed_cta_is_violation_not_crash(self):
        p = fresh(); p["sections"][0]["cta"] = {"label": "Buy now"}
        self.assertIn("D1-COPY-MISSING-CTA-S1", validate_copy(p))

    def test_duplicate_pains_rejected(self):
        p = fresh()
        p["sections"][2]["body"] = p["sections"][1]["body"]
        p["sections"][3]["body"] = p["sections"][1]["body"]
        self.assertIn("D1-COPY-PAINS-NOT-DISTINCT", validate_copy(p))

    def test_fake_scarcity_without_evidence_rejected(self):
        p = fresh()
        p["sections"][0]["body"] += " This offer vanishes in 10 minutes, one time only, never again!"
        self.assertIn("D1-COPY-FAKE-SCARCITY", validate_copy(p))

    def test_private_framework_label_rejected(self):
        p = fresh()
        p["sections"][0]["body"] = "Section 1: The Big Bold Claim framework step. " + p["sections"][0]["body"]
        self.assertIn("D1-COPY-PRIVATE-LABEL-LEAK", validate_copy(p))

    def test_example_price_in_cta_label_rejected(self):
        p = fresh(); p["approved_amounts_minor"] = []
        p["sections"][0]["cta"]["label"] = "Join for $27 now"
        self.assertIn("D1-COPY-EXAMPLE-PRICE-LEAK", validate_copy(p))

    def test_paraphrase_padded_missed_items_rejected(self):
        p = fresh()
        items = p["sections"][7]["missed_out_items"]
        items[6] = "Weekly trainings from top marketing experts that could accelerate your growth and results"
        items[0] = "Weekly trainings from top marketing experts that could accelerate your growth"
        self.assertIn("D1-COPY-MISSED-PARAPHRASE-DUPLICATE", validate_copy(p))

    def test_false_loss_of_purchase_rejected(self):
        p = fresh()
        p["sections"][7]["missed_out_items"][0] = "You will lose your original purchase and everything in it"
        self.assertIn("D1-COPY-FALSE-LOSS-OF-PURCHASE", validate_copy(p))

    def test_example_price_leak_rejected_when_unapproved(self):
        p = fresh(); p["approved_amounts_minor"] = []
        self.assertIn("D1-COPY-EXAMPLE-PRICE-LEAK", validate_copy(p))

    def test_missing_decline_action_rejected(self):
        p = fresh(); p["decline_action"] = None
        self.assertIn("D1-COPY-MISSING-DECLINE-ACTION", validate_copy(p))


class OfferDifferenceTests(unittest.TestCase):
    def test_reduced_scope_passes(self):
        self.assertEqual(validate_offer_difference(U1, copy.deepcopy(D1)), [])

    def test_identical_promise_rejected(self):
        d = copy.deepcopy(D1)
        d["entitlement_ids"] = ["extra-full"]; d["difference_kind"] = "reduced_scope"
        self.assertIn("D1-OFFER-IDENTICAL-PROMISE", validate_offer_difference(U1, d))

    def test_lower_installment_is_not_lower_total(self):
        d = copy.deepcopy(D1)
        d["difference_kind"] = "lower_total_price"
        d["prices"] = [{"amount_minor": None, "schedule": [
            {"amount_minor": 100, "due": "now"}, {"amount_minor": 6600, "due": "in 30 days"}]}]
        self.assertIn("D1-OFFER-LOWER-TOTAL-NOT-PROVEN", validate_offer_difference(U1, d))

    def test_terms_change_with_same_total_passes(self):
        d = copy.deepcopy(D1)
        d["difference_kind"] = "changed_payment_terms"
        d["prices"] = [{"amount_minor": None, "schedule": [
            {"amount_minor": 3350, "due": "now"}, {"amount_minor": 3350, "due": "in 30 days"}]}]
        self.assertEqual(validate_offer_difference(U1, d), [])

    def test_missing_rationale_flagged_for_owner(self):
        d = copy.deepcopy(D1); d["rationale"] = ""
        self.assertIn("D1-OFFER-RATIONALE-MISSING", validate_offer_difference(U1, d))

    def test_identical_deliverables_with_renamed_entitlements_rejected(self):
        d = copy.deepcopy(D1)
        d["deliverables"] = ["A", "B", "C"]
        d["entitlement_ids"] = ["renamed-1", "renamed-2"]
        self.assertIn("D1-OFFER-IDENTICAL-PROMISE", validate_offer_difference(U1, d))

    def test_missing_mutual_exclusion_rejected(self):
        d = copy.deepcopy(D1); d["excludes"] = []
        self.assertIn("D1-OFFER-EXCLUDES-U1-MISSING", validate_offer_difference(U1, d))

    def test_removing_base_purchase_rejected(self):
        base = {"offer_id": "MAIN-A", "entitlement_ids": ["base-a"]}
        d = copy.deepcopy(D1); d["entitlements_removed_vs_u1"] = ["base-a"]
        self.assertIn("D1-OFFER-REMOVES-BASE-PURCHASE",
                      validate_offer_difference(U1, d, base))


class DisclosureTests(unittest.TestCase):
    def test_trial_missing_renewal_rejected(self):
        d = copy.deepcopy(D1)
        d["prices"] = [{"billing_type": "trial", "amount_minor": 100, "schedule": []}]
        disc = {"due_now_minor": 100, "trial_length": "30 days"}
        v = validate_trial_disclosure(d, disc)
        self.assertIn("D1-DISCLOSURE-MISSING-RENEWAL_AMOUNT_MINOR", v)
        self.assertIn("D1-DISCLOSURE-MISSING-CANCELLATION_TERMS", v)

    def test_one_time_needs_no_trial_fields(self):
        d = copy.deepcopy(D1)
        d["prices"] = [{"billing_type": "one_time", "amount_minor": 3700, "schedule": []}]
        self.assertEqual(validate_trial_disclosure(d, {}), [])

    def test_disclosure_due_now_must_match_offer_price(self):
        d = copy.deepcopy(D1)
        d["prices"] = [{"billing_type": "trial", "amount_minor": 100, "schedule": []}]
        disc = {"due_now_minor": 200, "trial_length": "30 days",
                "renewal_amount_minor": 2700, "renewal_date_or_rule": "day 31",
                "interval": "monthly", "cancellation_terms": "cancel anytime",
                "access_implications": "access ends at period end"}
        self.assertIn("D1-DISCLOSURE-DUE-NOW-MISMATCH", validate_trial_disclosure(d, disc))


class EntryGuardTests(unittest.TestCase):
    BASE = {"main_purchased_verified": True, "u1_event": "explicit_decline",
            "u1_enabled": True, "d1_enabled": True, "u1_accepted": False}

    def test_eligible_decline_passes(self):
        self.assertEqual(check_entry_guard(dict(self.BASE)), [])

    def test_failed_u1_payment_is_not_a_decline(self):
        s = dict(self.BASE); s["u1_event"] = "payment_failed"
        self.assertIn("D1-GUARD-NO-EXPLICIT-U1-DECLINE", check_entry_guard(s))

    def test_pending_u1_payment_is_not_a_decline(self):
        s = dict(self.BASE); s["u1_event"] = "payment_pending"
        self.assertIn("D1-GUARD-NO-EXPLICIT-U1-DECLINE", check_entry_guard(s))

    def test_accepted_u1_is_mutually_exclusive(self):
        s = dict(self.BASE); s["u1_accepted"] = True
        self.assertIn("D1-GUARD-U1-ALREADY-ACCEPTED", check_entry_guard(s))

    def test_direct_access_without_main_purchase_refused(self):
        s = dict(self.BASE); s["main_purchased_verified"] = False
        self.assertIn("D1-GUARD-NO-VERIFIED-MAIN-PURCHASE", check_entry_guard(s))

    def test_d1_cannot_stay_enabled_without_u1(self):
        s = dict(self.BASE); s["u1_enabled"] = False
        self.assertIn("D1-GUARD-D1-ENABLED-WITHOUT-U1", check_entry_guard(s))

    def test_u2_cannot_stay_enabled_without_u1(self):
        s = dict(self.BASE); s["u1_enabled"] = False; s["u2_enabled"] = True
        self.assertIn("D1-GUARD-U2-ENABLED-WITHOUT-U1", check_entry_guard(s))


if __name__ == "__main__":
    unittest.main()
