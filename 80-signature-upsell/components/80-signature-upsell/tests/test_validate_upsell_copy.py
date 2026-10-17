#!/usr/bin/env python3
"""S80-01/02/03 test suite for 80-signature-upsell (TEST ONLY data throughout).

Run:  python3 -m unittest discover -s tests -v
Covers:
  - S80-01 profile derivation facts (8 sections, 1-7 retained, 8-11 excluded,
    12 -> new 8 with the approved heading pattern, CTA in every section).
  - S80-02 request/result schemas: valid U1 + U2 (both U2 entry paths),
    rejection of client-side-claim U2 and bump-only U2.
  - S80-03 validator: positive fixtures pass (exit 0), every negative fixture
    fails with its expected code (exit 2), malformed input fails closed (3).
  - Review repairs D-01..D-09: the independent review's five adversarial
    fixtures (fixtures/regression-fixtures-manifest.json) now fail with
    their named codes, and the schema escapes (qualifying-purchase source,
    entry-context/slot agreement, recurring terms, self-review claim)
    are rejected.
  - Re-review repairs R2-01/R2-02/R2-06 (+R2-07, R2-03/R2-04 morphology):
    external-only binding expectation with UNVERIFIED status, paraphrased
    unbound buy paths with an explicit decline model, structured-evidence
    requirements at both layers, action_binding required in the schema.
    R2-05 (concept rotation) remains a declared residual limit.
  - Closing re-review repairs R3-01/R3-02/R3-04 (+R3-03/R3-05 folds):
    manifest entry source_refs held to the structured-evidence standard,
    the decline exemption narrowed so it cannot shield a directive-family
    hit, the structured pattern applied to the request's remaining
    evidence fields, and QR/settle-up/payment-screen/email-link buy
    paths plus pause-enrolments scarcity folded into the families.
    The R3-05 'Meet Jordan' named-story variant remains a declared
    residual for substantive review, not pattern-chased.
  - Closing R3 re-review folds R4-01/R4-02 (both Low): subject-first
    inversions of the scarcity folds (pause/halt, closes, capacity
    fills, price rises) and the decline exemption tightened so an
    imperative direction ('go to the payment page') voids it - the
    exemption covers descriptive mentions only, never directions.
    R4-03/R4-04 remain declared paraphrase/proof residuals,
    rubric-carried, not pattern-chased (BUILD-NOTES Appendix D).
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
VALIDATOR = ROOT / "scripts" / "validate_upsell_copy.py"
sys.path.insert(0, str(ROOT / "scripts"))
import validate_upsell_copy as V  # noqa: E402

try:
    import jsonschema
except ImportError:  # schema tests are skipped loudly if the lib is absent
    jsonschema = None


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_validator(*args):
    return subprocess.run([sys.executable, str(VALIDATOR), *map(str, args)],
                          capture_output=True, text=True)


class ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = load(ROOT / "profiles" / "upsell-profile.json")

    def test_eight_sections_numbered_1_to_8(self):
        secs = self.profile["sections"]
        self.assertEqual(len(secs), 8)
        self.assertEqual([s["number"] for s in secs], list(range(1, 9)))

    def test_derivation_retains_1_to_7(self):
        d = self.profile["derivation"]
        self.assertEqual(d["retained_original_sections"], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual([s["derived_from_original_section"] for s in self.profile["sections"][:7]],
                         [1, 2, 3, 4, 5, 6, 7])

    def test_original_8_to_11_excluded(self):
        self.assertEqual(self.profile["derivation"]["excluded_original_sections"], [8, 9, 10, 11])

    def test_section_12_replaced_by_new_section_8(self):
        rep = self.profile["derivation"]["replaced_original_section"]
        self.assertEqual(rep["original_number"], 12)
        self.assertEqual(rep["new_number"], 8)
        self.assertEqual(rep["new_name_pattern"],
                         "7 Reasons To Commit To Your {inspiring_phrase} Future")
        sec8 = self.profile["sections"][7]
        self.assertEqual(sec8["derived_from_original_section"], 12)
        self.assertEqual(sec8["reasons_required"], 7)
        self.assertTrue(sec8["reasons_must_be_distinct"])

    def test_cta_in_every_section(self):
        self.assertTrue(all(s["cta_required"] for s in self.profile["sections"]))
        self.assertTrue(self.profile["cta_rule"]["cta_in_every_section"])

    def test_scarcity_only_from_verified_facts(self):
        rule = self.profile["scarcity_and_proof_rule"]
        self.assertIn("verified", rule["evidence_requirement"].lower())
        self.assertIn("invented countdown or timer", rule["forbidden"])


class ValidatorPositiveTests(unittest.TestCase):
    def test_public_u1_passes(self):
        # R2-01 harness conformance: the binding expectation is supplied from
        # OUTSIDE the copy document (assertion unchanged: exit 0), and the
        # report must show the binding as verified-external.
        r = run_validator(FIX / "copy-upsell1-public.valid.json",
                          "--expected-action-ref", "native-one-click:TEST-ONLY-U1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("binding_verification=verified_external", r.stdout)

    def test_public_u2_passes_and_is_distinct_from_u1(self):
        # R2-01: U2 exercises the --binding-manifest external expectation.
        r = run_validator(FIX / "copy-upsell2-public.valid.json",
                          "--compare", FIX / "copy-upsell1-public.valid.json",
                          "--binding-manifest", FIX / "binding-manifest.testonly.json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("binding_verification=verified_external", r.stdout)

    def test_owner_sample_private_authoring_passes(self):
        r = run_validator(FIX / "copy-owner-sample-upsell1.private.json",
                          "--expected-action-ref", "native-one-click:TEST-ONLY-SAMPLE-U1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_self_test_passes(self):
        r = run_validator("--self-test")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class ValidatorNegativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load(FIX / "negative-fixtures-manifest.json")["fixtures"]

    def test_every_negative_fixture_fails_with_expected_code(self):
        for entry in self.manifest:
            with self.subTest(fixture=entry["file"]):
                args = [FIX / entry["file"]]
                if entry["expected_code"] == "U80-U2-DISTINCT":
                    args += ["--compare", FIX / "copy-upsell1-public.valid.json"]
                r = run_validator(*args)
                self.assertEqual(r.returncode, entry["expected_exit"], r.stdout)
                self.assertIn(entry["expected_code"], r.stdout)

    def test_malformed_json_fails_closed(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("{not json")
            path = fh.name
        r = run_validator(path)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("FAIL-CLOSED", r.stderr)

    def test_missing_fields_fail_closed(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"instance": "upsell_1"}, fh)
            path = fh.name
        r = run_validator(path)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)

    def test_missing_file_fails_closed(self):
        r = run_validator(FIX / "does-not-exist.json")
        self.assertEqual(r.returncode, 3)

    def test_scarcity_allowed_only_with_verified_evidence(self):
        doc = load(FIX / "copy-neg-invented-scarcity.json")
        doc["verified_scarcity_evidence"] = [
            {"fact": "TEST ONLY verified deadline fact", "source_ref": "TEST-ONLY-evidence-ref"}]
        violations = V.validate_copy(doc, load(ROOT / "profiles" / "upsell-profile.json"), "t")
        self.assertNotIn("U80-INVENTED-SCARCITY", [x["code"] for x in violations])


@unittest.skipIf(jsonschema is None, "jsonschema not installed in this environment")
class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.req_schema = load(ROOT / "schemas" / "upsell-request.schema.json")
        cls.res_schema = load(ROOT / "schemas" / "upsell-result.schema.json")
        jsonschema.Draft202012Validator.check_schema(cls.req_schema)
        jsonschema.Draft202012Validator.check_schema(cls.res_schema)

    def assertValid(self, schema, doc):
        errs = list(jsonschema.Draft202012Validator(schema).iter_errors(doc))
        self.assertEqual(errs, [], "\n".join(str(e.message) for e in errs))

    def assertInvalid(self, schema, doc):
        errs = list(jsonschema.Draft202012Validator(schema).iter_errors(doc))
        self.assertTrue(errs, "expected schema rejection")

    def test_request_u1_valid(self):
        self.assertValid(self.req_schema, load(FIX / "request-upsell1.testonly.json"))

    def test_request_u2_from_downsell_valid(self):
        self.assertValid(self.req_schema, load(FIX / "request-upsell2.testonly.json"))

    def test_request_u2_from_upsell1_valid(self):
        doc = load(FIX / "request-upsell2.testonly.json")
        doc["entry_context"] = "from_upsell_1"
        doc["eligibility"]["qualifying_purchase"] = {
            "slot": "upsell_1", "status": "verified_succeeded",
            "verification_source": "native_purchase_ledger",
            "evidence_ref": "TEST-ONLY-u1-ledger-entry"}
        self.assertValid(self.req_schema, doc)

    def test_request_u2_client_side_claim_rejected(self):
        self.assertInvalid(self.req_schema, load(FIX / "request-neg-u2-client-claim.json"))

    def test_request_u2_bump_only_rejected(self):
        self.assertInvalid(self.req_schema, load(FIX / "request-neg-u2-bump-only.json"))

    def test_request_missing_disclosure_rejected(self):
        doc = load(FIX / "request-upsell1.testonly.json")
        del doc["disclosure"]
        self.assertInvalid(self.req_schema, doc)

    def test_request_float_amount_rejected(self):
        doc = load(FIX / "request-upsell1.testonly.json")
        doc["disclosure"]["amount_minor"] = 6750.5  # non-integral float: not authoritative minor units (doc 02 s.3)
        self.assertInvalid(self.req_schema, doc)

    def test_result_u1_and_u2_valid_and_separate(self):
        r1 = load(FIX / "result-upsell1.testonly.json")
        r2 = load(FIX / "result-upsell2.testonly.json")
        self.assertValid(self.res_schema, r1)
        self.assertValid(self.res_schema, r2)
        self.assertEqual(r1["instance"], "upsell_1")
        self.assertEqual(r2["instance"], "upsell_2")
        self.assertNotEqual(r1["page_id"], r2["page_id"])

    def test_result_cta_map_must_have_eight_entries(self):
        doc = load(FIX / "result-upsell1.testonly.json")
        doc["cta_map"] = doc["cta_map"][:7]
        self.assertInvalid(self.res_schema, doc)


class ReviewRegressionTests(unittest.TestCase):
    """Repairs for independent-review defects D-01..D-09 (review session
    e25cbf65-f0b0-4b31-8855-0b5411453764). Every adversarial fixture below
    ESCAPED (validator exit 0 / schema VALID) at review time; each must now
    fail with its named code / schema rejection."""

    @classmethod
    def setUpClass(cls):
        cls.profile = load(ROOT / "profiles" / "upsell-profile.json")
        cls.manifest = load(FIX / "regression-fixtures-manifest.json")["fixtures"]

    def test_every_review_adversarial_fixture_now_fails_with_expected_code(self):
        for entry in self.manifest:
            with self.subTest(fixture=entry["file"], defect=entry["defect"]):
                r = run_validator(FIX / entry["file"])
                self.assertEqual(r.returncode, entry["expected_exit"], r.stdout)
                self.assertIn(entry["expected_code"], r.stdout)

    def test_d03_cli_expected_ref_mismatch_fails(self):
        r = run_validator(FIX / "copy-upsell1-public.valid.json",
                          "--expected-action-ref", "native-one-click:TEST-ONLY-WRONG")
        self.assertEqual(r.returncode, 2)
        self.assertIn("U80-CTA-BINDING", r.stdout)

    def test_d03_cli_expected_ref_match_passes(self):
        r = run_validator(FIX / "copy-upsell1-public.valid.json",
                          "--expected-action-ref", "native-one-click:TEST-ONLY-U1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_d03_raw_url_action_ref_fails(self):
        doc = load(FIX / "copy-upsell1-public.valid.json")
        doc["accept_action_ref"] = "https://example.invalid/charge"
        doc["action_binding"]["expected_action_ref"] = "https://example.invalid/charge"
        for sec in doc["sections"]:
            sec["cta"]["action_ref"] = "https://example.invalid/charge"
        codes = [x["code"] for x in V.validate_copy(doc, self.profile, "t")]
        self.assertIn("U80-CTA-BINDING", codes)

    def test_d01_family_scarcity_allowed_with_verified_evidence(self):
        doc = load(FIX / "copy-regression-a3-offlist-scarcity.json")
        doc["verified_scarcity_evidence"] = [
            {"fact": "TEST ONLY verified deadline fact", "source_ref": "TEST-ONLY-evidence-ref"}]
        codes = [x["code"] for x in V.validate_copy(doc, self.profile, "t")]
        self.assertNotIn("U80-INVENTED-SCARCITY", codes)

    def test_d02_testimonial_allowed_only_with_verified_proof(self):
        doc = load(FIX / "copy-regression-a4-offlist-testimonial.json")
        doc["verified_proof_evidence"] = [
            {"fact": "TEST ONLY supplied testimonial record", "source_ref": "TEST-ONLY-proof-ref"}]
        codes = [x["code"] for x in V.validate_copy(doc, self.profile, "t")]
        self.assertNotIn("U80-INVENTED-TESTIMONIAL", codes)

    def test_d04_concept_signature_separates_paraphrase_from_distinct(self):
        groups = self.profile["reason_concept_groups"]["groups"]
        a1 = load(FIX / "copy-regression-a1-near-duplicate-reasons.json")
        a1_sigs = [V.concept_signature(r, groups) for r in a1["sections"][7]["reasons"]]
        pair = frozenset({"availability_access", "speed_progress"})
        self.assertGreaterEqual(
            sum(1 for s in a1_sigs if pair <= s), V.CONCEPT_PAIR_COLLAPSE_MIN)
        for name in ("copy-upsell1-public.valid.json",
                     "copy-upsell2-public.valid.json",
                     "copy-owner-sample-upsell1.private.json"):
            doc = load(FIX / name)
            codes = [x["code"] for x in V.validate_copy(doc, self.profile, "t")]
            self.assertNotIn("U80-REASON-DISTINCT", codes, name)


@unittest.skipIf(jsonschema is None, "jsonschema not installed in this environment")
class SchemaRepairTests(unittest.TestCase):
    """Schema-side repairs D-06, D-07, D-08 and the ADV-S5 low."""

    @classmethod
    def setUpClass(cls):
        cls.req_schema = load(ROOT / "schemas" / "upsell-request.schema.json")
        cls.res_schema = load(ROOT / "schemas" / "upsell-result.schema.json")

    def assertValid(self, schema, doc):
        errs = list(jsonschema.Draft202012Validator(schema).iter_errors(doc))
        self.assertEqual(errs, [], "\n".join(str(e.message) for e in errs))

    def assertInvalid(self, schema, doc):
        errs = list(jsonschema.Draft202012Validator(schema).iter_errors(doc))
        self.assertTrue(errs, "expected schema rejection")

    def test_d06_qualifying_purchase_without_source_rejected(self):
        self.assertInvalid(self.req_schema,
                            load(FIX / "request-neg-u2-qualifying-no-source.json"))

    def test_d06_qualifying_client_side_evidence_rejected(self):
        self.assertInvalid(self.req_schema,
                            load(FIX / "request-neg-u2-qualifying-client-evidence.json"))

    def test_d07_entry_context_must_match_qualifying_slot(self):
        self.assertInvalid(self.req_schema,
                            load(FIX / "request-neg-u2-entry-context-mismatch.json"))

    def test_d08_recurring_with_null_terms_rejected(self):
        self.assertInvalid(self.req_schema,
                            load(FIX / "request-neg-recurring-terms-null.json"))

    def test_d08_installment_with_terms_valid(self):
        doc = load(FIX / "request-upsell1.testonly.json")
        doc["disclosure"]["billing_type"] = "installment"
        doc["disclosure"]["recurring_terms"] = {
            "interval": "month", "interval_count": 1, "cycles": 3,
            "trial_amount_minor": None, "trial_period": None}
        self.assertValid(self.req_schema, doc)

    def test_d09_result_self_review_claim_rejected(self):
        self.assertInvalid(self.res_schema, load(FIX / "result-neg-self-review.json"))

    def test_request_action_binding_matches_copy_action_refs(self):
        for req_f, copy_f in (("request-upsell1.testonly.json", "copy-upsell1-public.valid.json"),
                              ("request-upsell2.testonly.json", "copy-upsell2-public.valid.json")):
            req = load(FIX / req_f)
            copy_doc = load(FIX / copy_f)
            self.assertEqual(req["action_binding"]["expected_action_ref"],
                             copy_doc["accept_action_ref"])
            self.assertEqual(copy_doc["action_binding"]["expected_action_ref"],
                             req["action_binding"]["expected_action_ref"])


class R2RepairTests(unittest.TestCase):
    """R2-01/R2-02/R2-06 (+R2-03/R2-04 morphology) repairs, per the
    independent re-review of S80-01/02/03. Regression fixtures rebuilt from
    the re-reviewer's attack constructions (fixtures/copy-r2-*.json)."""

    @classmethod
    def setUpClass(cls):
        cls.profile = load(ROOT / "profiles" / "upsell-profile.json")
        cls.manifest = load(FIX / "binding-manifest.testonly.json")

    @staticmethod
    def codes(violations):
        return [x["code"] for x in violations]

    # --- R2-01: external binding expectation ---
    def test_r2_01_self_authored_binding_is_unverified(self):
        doc = load(FIX / "copy-r2-self-authored-binding.json")
        report = V.validate_copy_report(doc, self.profile)
        self.assertEqual(report["binding_verification"], "unverified")
        self.assertIn("U80-CTA-BINDING-UNVERIFIED", self.codes(report["violations"]))

    def test_r2_01_external_cli_expectation_does_not_verify_an_invented_ref(self):
        doc = load(FIX / "copy-r2-self-authored-binding.json")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertIn("U80-CTA-BINDING", self.codes(v))

    def test_r2_01_allow_unverified_local_mode_records_status(self):
        doc = load(FIX / "copy-upsell1-public.valid.json")
        report = V.validate_copy_report(doc, self.profile, allow_unverified_binding=True)
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["binding_verification"], "unverified")
        r = run_validator(FIX / "copy-upsell1-public.valid.json", "--allow-unverified-binding")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("LIMITATION", r.stdout)
        self.assertIn("binding_verification=unverified", r.stdout)

    def test_r2_01_manifest_supplies_external_expectation(self):
        doc = load(FIX / "copy-upsell1-public.valid.json")
        report = V.validate_copy_report(doc, self.profile, binding_manifest=self.manifest)
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["binding_verification"], "verified_external")

    def test_r2_01_manifest_without_matching_entry_fails(self):
        doc = copy.deepcopy(load(FIX / "copy-upsell1-public.valid.json"))
        doc["copy_id"] = "TEST-ONLY-unlisted-copy"
        v = V.validate_copy(doc, self.profile, binding_manifest=self.manifest)
        self.assertIn("U80-CTA-BINDING", self.codes(v))

    def test_r2_01_malformed_manifest_fails_closed(self):
        doc = load(FIX / "copy-upsell1-public.valid.json")
        with self.assertRaises(V.FailClosed):
            V.validate_copy(doc, self.profile, binding_manifest=["not", "an", "object"])

    def test_r2_01_plain_cli_on_valid_copy_fails_closed_on_binding(self):
        r = run_validator(FIX / "copy-r2-self-authored-binding.json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("U80-CTA-BINDING-UNVERIFIED", r.stdout)

    # --- R2-02: unbound purchase-path paraphrases + decline model ---
    def test_r2_02_paraphrased_buy_path_rejected(self):
        doc = load(FIX / "copy-r2-unbound-cta-paraphrase.json")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertIn("U80-UNBOUND-CTA", self.codes(v))

    def test_r2_02_head_to_checkout_paraphrase_rejected(self):
        doc = copy.deepcopy(load(FIX / "copy-upsell1-public.valid.json"))
        doc["sections"][3]["body"] += (
            "\nHead to checkout to get yours before you leave this page.")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertIn("U80-UNBOUND-CTA", self.codes(v))

    def test_r2_02_decline_wording_alone_is_not_an_unbound_cta(self):
        # This sentence WOULD trip the payment-page-direction pattern
        # ('go' ... 'payment page') without the explicit decline model:
        # it models the decline path (no-thanks, no purchase direction),
        # which routes through the declared decline action.
        doc = copy.deepcopy(load(FIX / "copy-upsell1-public.valid.json"))
        doc["sections"][0]["body"] += (
            "\nTo go back without the upgrade, choose no thanks; the payment "
            "page is only for buyers who want the extra.")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertNotIn("U80-UNBOUND-CTA", self.codes(v))
        self.assertEqual(v, [])

    def test_r2_02_decline_wording_with_purchase_direction_not_exempt(self):
        doc = copy.deepcopy(load(FIX / "copy-upsell1-public.valid.json"))
        doc["sections"][0]["body"] += (
            "\nNo thanks is fine, but to buy, visit the payment page and "
            "complete your purchase there.")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertIn("U80-UNBOUND-CTA", self.codes(v))

    # --- R2-03 / R2-04: morphology folded into the pattern families ---
    def test_r2_03_scarcity_morphology_rejected(self):
        doc = load(FIX / "copy-r2-scarcity-morphology.json")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertIn("U80-INVENTED-SCARCITY", self.codes(v))

    def test_r2_04_collective_testimonial_rejected(self):
        doc = load(FIX / "copy-r2-testimonial-collective.json")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertIn("U80-INVENTED-TESTIMONIAL", self.codes(v))

    # --- R2-06: structured evidence at the validator layer ---
    def test_r2_06_self_asserted_evidence_rejected_and_clears_nothing(self):
        doc = load(FIX / "copy-r2-self-asserted-evidence.json")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        codes = self.codes(v)
        self.assertIn("U80-EVIDENCE-REF", codes)
        self.assertIn("U80-INVENTED-SCARCITY", codes)

    def test_r2_06_structured_evidence_still_clears(self):
        doc = copy.deepcopy(load(FIX / "copy-neg-invented-scarcity.json"))
        doc["verified_scarcity_evidence"] = [{
            "fact": "TEST ONLY: capacity deadline recorded in the launch ledger",
            "source_ref": "ledger:TEST-ONLY-launch-ledger-entry-1"}]
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertNotIn("U80-EVIDENCE-REF", self.codes(v))
        self.assertNotIn("U80-INVENTED-SCARCITY", self.codes(v))


class R2SchemaTests(unittest.TestCase):
    """R2-06 schema patterns + R2-07 action_binding required."""

    @classmethod
    def setUpClass(cls):
        if jsonschema is None:
            raise unittest.SkipTest("jsonschema not installed")
        cls.schema = load(ROOT / "schemas" / "upsell-request.schema.json")
        cls.validator = jsonschema.Draft202012Validator(cls.schema)

    def errors(self, req):
        return list(self.validator.iter_errors(req))

    def test_r2_07_action_binding_now_required(self):
        req = copy.deepcopy(load(FIX / "request-upsell1.testonly.json"))
        del req["action_binding"]
        self.assertTrue(self.errors(req),
                        "a request without action_binding must now be invalid (R2-07)")

    def test_r2_06_bare_assertion_evidence_ref_rejected(self):
        for bad in ("verified", "trust me"):
            req = copy.deepcopy(load(FIX / "request-upsell2.testonly.json"))
            req["eligibility"]["qualifying_purchase"]["evidence_ref"] = bad
            self.assertTrue(self.errors(req), f"evidence_ref {bad!r} must be invalid (R2-06)")

    def test_r2_06_provider_event_ref_client_claim_rejected(self):
        req = copy.deepcopy(load(FIX / "request-upsell2.testonly.json"))
        req["eligibility"]["qualifying_purchase"]["provider_event_ref"] = "acceptedU1=true"
        self.assertTrue(self.errors(req),
                        "provider_event_ref must carry the client-claim guard (R2-06)")

    def test_r2_06_structured_refs_still_validate(self):
        for good in ("ledger:TEST-ONLY-entry-1", "TEST-ONLY-ledger-entry",
                     "https://example.invalid/records/1"):
            req = copy.deepcopy(load(FIX / "request-upsell2.testonly.json"))
            req["eligibility"]["qualifying_purchase"]["evidence_ref"] = good
            self.assertEqual(self.errors(req), [],
                             f"structured evidence_ref {good!r} must stay valid")


class R3RepairTests(unittest.TestCase):
    """R3-01/R3-02 repairs + R3-03/R3-05 pattern folds, per the closing
    re-review of the R2 repairs (review session
    06e6b690-f02d-4f84-a94c-3ec58c12740e). Regression fixtures rebuilt
    from the re-reviewer's /tmp/s80r2close constructions
    (fixtures/copy-r3-*.json, fixtures/binding-manifest-r3-*.json)."""

    @classmethod
    def setUpClass(cls):
        cls.profile = load(ROOT / "profiles" / "upsell-profile.json")
        cls.manifest = load(FIX / "binding-manifest.testonly.json")
        cls.attack_copy = load(FIX / "copy-r2-self-authored-binding.json")
        cls.attack_manifest = load(FIX / "binding-manifest-r3-self-authored.testonly.json")

    @staticmethod
    def codes(violations):
        return [x["code"] for x in violations]

    # --- R3-01: manifest provenance held to the structured standard ---
    def test_r3_01_self_authored_manifest_no_longer_verifies(self):
        report = V.validate_copy_report(self.attack_copy, self.profile,
                                        binding_manifest=self.attack_manifest)
        self.assertNotEqual(report["binding_verification"], "verified_external")
        self.assertIn("U80-CTA-BINDING", self.codes(report["violations"]))

    def test_r3_01_cli_self_authored_manifest_rejected(self):
        r = run_validator(FIX / "copy-r2-self-authored-binding.json",
                          "--binding-manifest",
                          FIX / "binding-manifest-r3-self-authored.testonly.json")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("U80-CTA-BINDING", r.stdout)
        self.assertIn("BINDING VERIFICATION: unverified", r.stdout)

    def test_r3_01_shipped_manifest_structured_sources_still_verify(self):
        doc = load(FIX / "copy-upsell1-public.valid.json")
        report = V.validate_copy_report(doc, self.profile, binding_manifest=self.manifest)
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["binding_verification"], "verified_external")
        self.assertIn("request:TEST-REQ-U1", report["binding_source"])

    def test_r3_01_manifest_source_denylist_applies_to_structured_forms(self):
        doc = load(FIX / "copy-upsell1-public.valid.json")
        man = {"bindings": [{"copy_id": doc["copy_id"],
                             "expected_action_ref": "native-one-click:TEST-ONLY-U1",
                             "source_ref": "request:my own say-so"}]}
        entry, problem = V.lookup_binding_manifest(doc, man, self.profile)
        self.assertIsNone(entry)
        self.assertIn("R3-01", problem)

    def test_r3_01_manifest_separator_id_source_accepted(self):
        doc = load(FIX / "copy-upsell1-public.valid.json")
        man = {"bindings": [{"copy_id": doc["copy_id"],
                             "expected_action_ref": "native-one-click:TEST-ONLY-U1",
                             "source_ref": "S49-route-graph-entry-7"}]}
        entry, problem = V.lookup_binding_manifest(doc, man, self.profile)
        self.assertIsNotNone(entry)
        self.assertIsNone(problem)

    # --- R3-02: decline exemption cannot shield a purchase direction ---
    def test_r3_02_decline_smuggled_directive_rejected(self):
        doc = load(FIX / "copy-r3-decline-smuggled-cta.json")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertIn("U80-UNBOUND-CTA", self.codes(v))

    def test_r3_02_control_without_decline_prefix_also_rejected(self):
        doc = copy.deepcopy(load(FIX / "copy-upsell1-public.valid.json"))
        doc["sections"][1]["body"] += (
            "\nTap the enrolment link on the next screen to activate the upgrade instantly.")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertIn("U80-UNBOUND-CTA", self.codes(v))

    def test_r3_02_legitimate_decline_mention_still_exempt(self):
        # The re-reviewer's legitimate-decline control: decline wording
        # whose only pattern hit is the DESCRIPTIVE payment-page mention,
        # with no purchase verb, stays clean.
        doc = copy.deepcopy(load(FIX / "copy-upsell1-public.valid.json"))
        doc["sections"][0]["body"] += (
            "\nTo go back without the upgrade, choose no thanks; the payment "
            "page is only for buyers who want the extra.")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertEqual(v, [])

    def test_r3_02_decline_with_direction_and_purchase_verb_not_exempt(self):
        doc = copy.deepcopy(load(FIX / "copy-upsell1-public.valid.json"))
        doc["sections"][0]["body"] += (
            "\nSkip this offer if you prefer, or visit the payment page and pay there instead.")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertIn("U80-UNBOUND-CTA", self.codes(v))

    # --- R3-03: paraphrased buy paths folded into the families ---
    def test_r3_03_each_buy_path_rejected(self):
        sentences = {
            2: "\nScan the QR code at the bottom of this page to pay for the upgrade instantly.",
            3: "\nSettle up on the payment screen to activate the upgrade before you move on.",
            4: "\nUse the link in your confirmation email to pay for the upgrade on another screen.",
        }
        for idx, sentence in sentences.items():
            with self.subTest(section=idx + 1):
                doc = copy.deepcopy(load(FIX / "copy-upsell1-public.valid.json"))
                doc["sections"][idx]["body"] += sentence
                v = V.validate_copy(doc, self.profile,
                                    expected_action_ref="native-one-click:TEST-ONLY-U1")
                self.assertIn("U80-UNBOUND-CTA", self.codes(v))

    def test_r3_03_shipped_fixture_rejected(self):
        doc = load(FIX / "copy-r3-unbound-buy-paths.json")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertIn("U80-UNBOUND-CTA", self.codes(v))

    # --- R3-05: pause-enrolments scarcity fold ---
    def test_r3_05_pause_enrolments_rejected(self):
        doc = load(FIX / "copy-r3-scarcity-pause-enrolments.json")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertIn("U80-INVENTED-SCARCITY", self.codes(v))


class R3SchemaTests(unittest.TestCase):
    """R3-04: structured pattern on the request's remaining evidence
    fields (factual_scarcity_evidence[].source_ref,
    payment_capability.evidence_ref)."""

    @classmethod
    def setUpClass(cls):
        if jsonschema is None:
            raise unittest.SkipTest("jsonschema not installed")
        cls.schema = load(ROOT / "schemas" / "upsell-request.schema.json")
        jsonschema.Draft202012Validator.check_schema(cls.schema)
        cls.validator = jsonschema.Draft202012Validator(cls.schema)

    def errors(self, req):
        return list(self.validator.iter_errors(req))

    def test_r3_04_factual_scarcity_source_ref_bare_assertion_rejected(self):
        for bad in ("trust me", "verified"):
            req = copy.deepcopy(load(FIX / "request-upsell1.testonly.json"))
            req["factual_scarcity_evidence"] = [
                {"fact": "TEST ONLY enrollment deadline fact", "source_ref": bad}]
            self.assertTrue(self.errors(req),
                            f"factual_scarcity_evidence source_ref {bad!r} must be invalid (R3-04)")

    def test_r3_04_factual_scarcity_source_ref_structured_valid(self):
        req = copy.deepcopy(load(FIX / "request-upsell1.testonly.json"))
        req["factual_scarcity_evidence"] = [
            {"fact": "TEST ONLY enrollment deadline fact",
             "source_ref": "ledger:TEST-ONLY-entry-1"}]
        self.assertEqual(self.errors(req), [])

    def test_r3_04_payment_capability_evidence_ref_bare_assertion_rejected(self):
        req = copy.deepcopy(load(FIX / "request-upsell1.testonly.json"))
        req["payment_capability"]["evidence_ref"] = "trust me"
        self.assertTrue(self.errors(req),
                        "payment_capability.evidence_ref must carry the structured pattern (R3-04)")

    def test_r3_04_payment_capability_evidence_ref_structured_or_null_valid(self):
        req = copy.deepcopy(load(FIX / "request-upsell1.testonly.json"))
        self.assertIsNone(req["payment_capability"]["evidence_ref"])
        self.assertEqual(self.errors(req), [])
        req["payment_capability"]["evidence_ref"] = "ledger:TEST-ONLY-capability-1"
        self.assertEqual(self.errors(req), [])


class R4RepairTests(unittest.TestCase):
    """R4-01/R4-02 folds, per the closing re-review of the R3 repairs
    (work/review-S80-R3-rereview.md, reviewer session
    51f4357c-2e5a-4384-a0aa-eac20e87ceeb). Both defects were Low:
    subject-first inversions of the R3-05 scarcity fold escaped, and the
    decline exemption still shielded imperative directions spoken
    through the descriptive direction family. Regression fixtures
    rebuild the re-reviewer's FA-A / FA-B / FA-G constructions verbatim
    (fixtures/copy-r4-*.json)."""

    @classmethod
    def setUpClass(cls):
        cls.profile = load(ROOT / "profiles" / "upsell-profile.json")
        cls.u1 = load(FIX / "copy-upsell1-public.valid.json")

    @staticmethod
    def codes(violations):
        return [x["code"] for x in violations]

    def with_sentence(self, section_idx, sentence):
        doc = copy.deepcopy(self.u1)
        doc["sections"][section_idx]["body"] += sentence
        return V.validate_copy(doc, self.profile,
                               expected_action_ref="native-one-click:TEST-ONLY-U1")

    # --- R4-01: subject-first scarcity inversions ---
    def test_r4_01_shipped_fixture_rejected(self):
        doc = load(FIX / "copy-r4-scarcity-subject-first.json")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertIn("U80-INVENTED-SCARCITY", self.codes(v))
        self.assertEqual(set(self.codes(v)), {"U80-INVENTED-SCARCITY"})

    def test_r4_01_reviewer_constructions_rejected(self):
        for sentence in (
                "\nAdmissions halt on Sunday and reopen in the spring.",
                "\nEnrolment pauses after this weekend while we review the waiting list."):
            with self.subTest(sentence=sentence.strip()):
                v = self.with_sentence(0, sentence)
                self.assertIn("U80-INVENTED-SCARCITY", self.codes(v))

    def test_r4_01_subject_first_variants_rejected(self):
        for sentence in (
                "\nAdmissions are paused over the summer break.",
                "\nAdmissions close at the end of the month.",
                "\nPlaces are filling quickly this week.",
                "\nThe price is going up once this round ends."):
            with self.subTest(sentence=sentence.strip()):
                v = self.with_sentence(1, sentence)
                self.assertIn("U80-INVENTED-SCARCITY", self.codes(v))

    def test_r4_01_subject_first_scarcity_cleared_by_verified_evidence(self):
        # The fold widens DETECTION, not the evidence standard: a
        # subject-first scarcity claim backed by a structured verified
        # evidence entry clears, exactly like the verb-first forms.
        doc = copy.deepcopy(self.u1)
        doc["sections"][0]["body"] += (
            "\nAdmissions halt on Sunday and reopen in the spring.")
        doc["verified_scarcity_evidence"] = [{
            "fact": "TEST ONLY: admissions close Sunday per the launch ledger",
            "source_ref": "ledger:TEST-ONLY-launch-ledger-entry-9"}]
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertEqual(v, [])

    def test_r4_01_intake_process_mention_is_not_scarcity(self):
        # 'intake' is deliberately excluded from the subject nouns: it
        # names this build's own governed intake process (S49 intake),
        # so a process statement about it must not trip scarcity.
        v = self.with_sentence(
            1, "\nOur intake pauses over the public holiday and resumes the next working day.")
        self.assertEqual(v, [])

    # --- R4-02: decline exemption cannot shield an imperative ---
    def test_r4_02_shipped_fixture_rejected(self):
        doc = load(FIX / "copy-r4-decline-shielded-imperative.json")
        v = V.validate_copy(doc, self.profile,
                            expected_action_ref="native-one-click:TEST-ONLY-U1")
        self.assertIn("U80-UNBOUND-CTA", self.codes(v))
        self.assertEqual(set(self.codes(v)), {"U80-UNBOUND-CTA"})

    def test_r4_02_reviewer_constructions_rejected(self):
        for sentence in (
                "\nNo thanks is an option; go to the payment page.",
                "\nNo thanks, keep my current plan; head to the payment page whenever you are ready."):
            with self.subTest(sentence=sentence.strip()):
                v = self.with_sentence(0, sentence)
                self.assertIn("U80-UNBOUND-CTA", self.codes(v))

    def test_r4_02_imperative_variants_rejected(self):
        for sentence in (
                "\nNo thanks is fine; visit the payment page whenever you are ready.",
                "\nNo thanks, keep my current plan; proceed to the checkout page.",
                "\nSkip this offer if you prefer; navigate to the order page at any time.",
                "\nNot for me; go to the payment screen instead."):
            with self.subTest(sentence=sentence.strip()):
                v = self.with_sentence(0, sentence)
                self.assertIn("U80-UNBOUND-CTA", self.codes(v))

    def test_r4_02_legitimate_descriptive_decline_still_exempt(self):
        # The control that must stay green (the closing re-review's
        # legitimate decline control): a descriptive mention of the
        # payment page inside decline wording, with 'go' appearing only
        # in 'go back', which is not an imperative direction.
        v = self.with_sentence(
            0, "\nTo go back without the upgrade, choose no thanks; the payment "
               "page is only for buyers who want the extra.")
        self.assertEqual(v, [])

    def test_r4_02_decline_without_any_direction_still_clean(self):
        v = self.with_sentence(
            1, "\nIf now is not the moment, no thanks is completely fine and "
               "your core programme continues unchanged.")
        self.assertEqual(v, [])

    def test_r4_02_imperative_without_decline_wording_still_rejected(self):
        v = self.with_sentence(0, "\nGo to the payment page to finish joining.")
        self.assertIn("U80-UNBOUND-CTA", self.codes(v))


class PacketFixtureCrossCheckTests(unittest.TestCase):
    def test_reference_acceptance_cases_still_64(self):
        cases = load(Path.home() / "workspace/signature-launch/packet/reference/acceptance-cases.json")
        self.assertEqual(len(cases["cases"]), 64)


if __name__ == "__main__":
    unittest.main()
