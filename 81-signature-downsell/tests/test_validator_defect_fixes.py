"""Defect-fix tests for independent lane 5 findings D-1 to D-15 (2026-10-16).

Each test is named for its defect id and reproduces the lane 5 probe input:
the mutated input must now be rejected. Passing controls are included where
a fix could over-fire, so the tightening cannot silently reject valid input.
Nothing here weakens an existing check.
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
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

PAGE = json.loads((ROOT / "fixtures" / "valid-downsell-page.json").read_text())["page"]
EXT = json.loads(
    (ROOT / "fixtures" / "valid-downsell-result.json").read_text()
)["downsell_result_extension"]
SCHEMA = json.loads(
    (ROOT / "schemas" / "downsell-result-extension.schema.json").read_text()
)

U1 = {"offer_id": "U1", "slot": "upsell_1", "entitlement_ids": ["extra-full"],
      "deliverables": ["A", "B", "C"], "excludes": ["D1"], "requires": [],
      "prices": [{"amount_minor": 6700, "schedule": []}]}
D1 = {"offer_id": "D1", "slot": "downsell_1", "entitlement_ids": ["extra-lite"],
      "deliverables": ["A", "B"], "excludes": ["U1"], "requires": [],
      "difference_kind": "reduced_scope",
      "rationale": "Same core, smaller scope for visitors who declined the full upgrade on commitment size.",
      "prices": [{"amount_minor": 3700, "schedule": []}]}


def schema_errors(ext):
    validator = jsonschema.Draft202012Validator(SCHEMA)
    return list(validator.iter_errors(ext))


def scrubbed_page():
    """Valid page with every example amount scrubbed and none approved, so
    a price-leak verdict can only come from the text a test adds."""
    p = copy.deepcopy(PAGE)
    p["approved_amounts_minor"] = []
    for s in p["sections"]:
        s["body"] = s["body"].replace("$1", "").replace("$27", "")
        s["cta"]["label"] = s["cta"]["label"].replace("$1", "")
    return p


class DefectFixTests(unittest.TestCase):

    def test_d01_installment_split_not_lower_total(self):
        d = copy.deepcopy(D1)
        d["difference_kind"] = "lower_total_price"
        d["prices"] = [{"amount_minor": 100, "schedule": []},
                       {"amount_minor": 6600, "schedule": []}]
        self.assertIn("D1-OFFER-LOWER-TOTAL-NOT-PROVEN",
                      vd.validate_offer_difference(U1, d))

    def test_d01_genuinely_lower_multi_entry_total_passes(self):
        d = copy.deepcopy(D1)
        d["difference_kind"] = "lower_total_price"
        d["prices"] = [{"amount_minor": 100, "schedule": []},
                       {"amount_minor": 3000, "schedule": []}]
        self.assertEqual(vd.validate_offer_difference(U1, d), [])

    def test_d02_validators_never_raise(self):
        d = copy.deepcopy(D1)
        d["difference_kind"] = "lower_total_price"
        d["prices"] = [{"amount_minor": None, "schedule": [{"due": "now"}]}]
        v = vd.validate_offer_difference(U1, d)
        self.assertIn("D1-OFFER-LOWER-TOTAL-NOT-PROVEN", v)
        v = vd.validate_copy(None)
        self.assertIn("D1-COPY-SECTION-COUNT", v)
        self.assertIn("D1-COPY-MISSING-DECLINE-ACTION", v)
        v = vd.check_entry_guard(None)
        self.assertIn("D1-GUARD-NO-VERIFIED-MAIN-PURCHASE", v)
        self.assertIsInstance(vd.validate_copy("junk"), list)
        self.assertIsInstance(vd.validate_offer_difference(None, None), list)
        self.assertIsInstance(vd.validate_trial_disclosure(None, None), list)
        self.assertIsInstance(vd.validate_result_extension(None), list)
        self.assertIsInstance(vd.check_entry_guard([1, 2]), list)

    def test_d03_fake_scarcity_phrasing_variants(self):
        for text in ("Hurry, only a few spots left at this price.",
                     "This is your last chance to join at this level.",
                     "Doors close at midnight tonight, do not wait.",
                     "The price goes up tomorrow, act now."):
            p = copy.deepcopy(PAGE)
            p["sections"][0]["body"] += " " + text
            self.assertIn("D1-COPY-FAKE-SCARCITY", vd.validate_copy(p), text)

    def test_d03_scarcity_with_real_evidence_ref_passes(self):
        p = copy.deepcopy(PAGE)
        p["scarcity_evidence_ref"] = "evidence/deadline-2026-10-31.txt"
        p["sections"][0]["body"] += " This is your last chance to join at this level."
        self.assertEqual(vd.validate_copy(p), [])

    def test_d04_decline_action_needs_action_ref(self):
        p = copy.deepcopy(PAGE)
        p["decline_action"] = {"label": "No thanks, continue with my current order"}
        self.assertIn("D1-COPY-MISSING-DECLINE-ACTION", vd.validate_copy(p))
        p = copy.deepcopy(PAGE)
        p["decline_action"] = {"label": "No thanks", "action_ref": "  "}
        self.assertIn("D1-COPY-MISSING-DECLINE-ACTION", vd.validate_copy(p))

    def test_d05_whitespace_disclosure_counts_as_missing(self):
        d = copy.deepcopy(D1)
        d["prices"] = [{"billing_type": "trial", "amount_minor": 100,
                        "schedule": [{"amount_minor": 2700, "due": "day 31"}]}]
        disc = {"due_now_minor": 100, "trial_length": "30 days",
                "renewal_amount_minor": 2700, "renewal_date_or_rule": "day 31",
                "interval": "monthly", "cancellation_terms": " ",
                "access_implications": " "}
        v = vd.validate_trial_disclosure(d, disc)
        self.assertIn("D1-DISCLOSURE-MISSING-CANCELLATION_TERMS", v)
        self.assertIn("D1-DISCLOSURE-MISSING-ACCESS_IMPLICATIONS", v)

    def test_d06_decline_ref_must_not_equal_purchase_ref(self):
        ext = copy.deepcopy(EXT)
        ext["decline_action_ref"] = "native-d1-action"
        v = vd.validate_result_extension(ext)
        self.assertIn("D1-RESULT-DECLINE-ACTION-IS-PURCHASE-ACTION", v)
        # JSON Schema cannot compare two property values, so the schema
        # alone cannot express this rule; the semantic validator above is
        # the enforcing layer and the schema description records that.
        if HAVE_JSONSCHEMA:
            self.assertEqual(schema_errors(ext), [])

    def test_d07_loss_of_purchase_threat_in_any_section(self):
        p = copy.deepcopy(PAGE)
        p["sections"][0]["body"] += (
            " Act now, because you will lose your original purchase "
            "if you pass on this.")
        self.assertIn("D1-COPY-FALSE-LOSS-OF-PURCHASE", vd.validate_copy(p))

    def test_d08_private_label_variants(self):
        p = copy.deepcopy(PAGE)
        p["sections"][0]["body"] = (
            "Internal use only. Section 3 overview. " + p["sections"][0]["body"])
        self.assertIn("D1-COPY-PRIVATE-LABEL-LEAK", vd.validate_copy(p))
        p = copy.deepcopy(PAGE)
        p["sections"][1]["body"] += " As covered in Section 3 of the plan."
        self.assertIn("D1-COPY-PRIVATE-LABEL-LEAK", vd.validate_copy(p))

    def test_d09_example_prices_in_words_and_odd_formats(self):
        self.assertNotIn("D1-COPY-EXAMPLE-PRICE-LEAK",
                         vd.validate_copy(scrubbed_page()))
        p = scrubbed_page()
        p["sections"][0]["body"] += " That is twenty-seven dollars a month."
        self.assertIn("D1-COPY-EXAMPLE-PRICE-LEAK", vd.validate_copy(p))
        p = scrubbed_page()
        p["sections"][0]["cta"]["label"] = "Join for $ 27 now"
        self.assertIn("D1-COPY-EXAMPLE-PRICE-LEAK", vd.validate_copy(p))
        p = scrubbed_page()
        p["sections"][0]["body"] += " Yours for 27 USD monthly."
        self.assertIn("D1-COPY-EXAMPLE-PRICE-LEAK", vd.validate_copy(p))
        p = scrubbed_page()
        p["sections"][0]["body"] += " A one dollar trial starts today."
        self.assertIn("D1-COPY-EXAMPLE-PRICE-LEAK", vd.validate_copy(p))

    def test_d10_installment_disclosure_required(self):
        d = copy.deepcopy(D1)
        d["prices"] = [{"billing_type": "installment", "amount_minor": 100,
                        "schedule": [{"amount_minor": 3300, "due": "month 2"},
                                     {"amount_minor": 3300, "due": "month 3"}]}]
        v = vd.validate_trial_disclosure(d, {})
        self.assertIn("D1-DISCLOSURE-MISSING-DUE_NOW_MINOR", v)
        self.assertIn("D1-DISCLOSURE-MISSING-CANCELLATION_TERMS", v)
        full = {"due_now_minor": 100, "trial_length": "3 monthly payments",
                "renewal_amount_minor": 3300,
                "renewal_date_or_rule": "final payment month 3",
                "interval": "monthly", "cancellation_terms": "cancel anytime",
                "access_implications": "access ends if a payment fails"}
        self.assertEqual(vd.validate_trial_disclosure(d, full), [])

    def test_d10_installment_result_extension_disclosure(self):
        ext = copy.deepcopy(EXT)
        ext["disclosure_audit"] = {
            "billing_type": "installment", "due_now_minor": None,
            "renewal_amount_minor": None, "renewal_date_or_rule": None,
            "cancellation_terms_present": False}
        v = vd.validate_result_extension(ext)
        self.assertIn("D1-RESULT-DISCLOSURE-DUE-NOW-MISSING", v)
        self.assertIn("D1-RESULT-DISCLOSURE-RENEWAL-AMOUNT-MISSING", v)
        self.assertIn("D1-RESULT-DISCLOSURE-CANCELLATION-MISSING", v)
        if HAVE_JSONSCHEMA:
            self.assertTrue(schema_errors(ext),
                            "schema must reject installment without disclosure")

    def test_d11_pains_subset_is_not_distinct(self):
        p = copy.deepcopy(PAGE)
        tokens = [f"tok{i:02d}" for i in range(20)]
        p["sections"][1]["body"] = " ".join(tokens)
        p["sections"][2]["body"] = " ".join(tokens[:17])
        self.assertIn("D1-COPY-PAINS-NOT-DISTINCT", vd.validate_copy(p))

    def test_d12_whitespace_scarcity_evidence_ref(self):
        p = copy.deepcopy(PAGE)
        p["scarcity_evidence_ref"] = " "
        p["sections"][0]["body"] += " This is a one time only offer, never again!"
        self.assertIn("D1-COPY-FAKE-SCARCITY", vd.validate_copy(p))

    def test_d13_reworded_deliverables_still_identical_promise(self):
        u1 = copy.deepcopy(U1)
        u1["deliverables"] = ["Weekly live training sessions",
                               "Private community access",
                               "Founder feedback reviews"]
        d = copy.deepcopy(D1)
        d["deliverables"] = ["Live training sessions every week",
                             "Access to the private community",
                             "Reviews and feedback from the founder"]
        d["entitlement_ids"] = ["renamed-only"]
        d["prices"] = [{"amount_minor": 999, "schedule": []}]
        self.assertIn("D1-OFFER-IDENTICAL-PROMISE",
                      vd.validate_offer_difference(u1, d))

    def test_d13_genuine_reduced_scope_still_passes(self):
        u1 = copy.deepcopy(U1)
        u1["deliverables"] = ["Weekly live training sessions",
                               "Private community access",
                               "Founder feedback reviews"]
        d = copy.deepcopy(D1)
        d["deliverables"] = ["Live training sessions every week"]
        self.assertEqual(vd.validate_offer_difference(u1, d), [])

    def test_d14_changed_access_terms_needs_a_difference(self):
        d = copy.deepcopy(D1)
        d["difference_kind"] = "changed_access_terms"
        d["deliverables"] = ["A", "B", "C"]
        d["entitlement_ids"] = ["extra-full"]
        d["prices"] = [{"amount_minor": 6700, "schedule": []}]
        self.assertIn("D1-OFFER-ACCESS-CHANGE-UNPROVEN",
                      vd.validate_offer_difference(U1, d))

    def test_d14_recorded_access_terms_difference_passes(self):
        d = copy.deepcopy(D1)
        d["difference_kind"] = "changed_access_terms"
        d["deliverables"] = ["A", "B", "C"]
        d["entitlement_ids"] = ["extra-full"]
        d["prices"] = [{"amount_minor": 6700, "schedule": []}]
        d["access_terms"] = "Self-paced access for 90 days, no live sessions."
        self.assertEqual(vd.validate_offer_difference(U1, d), [])

    def test_d15_trial_renewal_unverifiable_without_schedule(self):
        d = copy.deepcopy(D1)
        d["prices"] = [{"billing_type": "trial", "amount_minor": 100,
                        "schedule": []}]
        disc = {"due_now_minor": 100, "trial_length": "30 days",
                "renewal_amount_minor": 999999,
                "renewal_date_or_rule": "day 31", "interval": "monthly",
                "cancellation_terms": "cancel anytime",
                "access_implications": "access ends at period end"}
        self.assertIn("D1-DISCLOSURE-RENEWAL-UNVERIFIABLE",
                      vd.validate_trial_disclosure(d, disc))

    def test_d15_trial_renewal_checked_against_schedule(self):
        d = copy.deepcopy(D1)
        d["prices"] = [{"billing_type": "trial", "amount_minor": 100,
                        "schedule": [{"amount_minor": 2700, "due": "day 31"}]}]
        disc = {"due_now_minor": 100, "trial_length": "30 days",
                "renewal_amount_minor": 2700,
                "renewal_date_or_rule": "day 31", "interval": "monthly",
                "cancellation_terms": "cancel anytime",
                "access_implications": "access ends at period end"}
        self.assertEqual(vd.validate_trial_disclosure(d, disc), [])


if __name__ == "__main__":
    unittest.main()
