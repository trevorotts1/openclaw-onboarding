"""U-upsell-02 honesty tests for adapter_common (UPS-02, UPS-03, UPS-14, UPS-19
and the UPS-01 'no literal copy_validation pass' row).

Run: python3 -m pytest 80-signature-upsell/components/adapters/test_adapter_common_honesty.py -q
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ADAPTERS_DIR = Path(__file__).resolve().parent
SKILL_DIR = ADAPTERS_DIR.parent / "80-signature-upsell"
FIXTURES = ADAPTERS_DIR / "fixtures"
sys.path.insert(0, str(ADAPTERS_DIR))

import adapter_common as common  # noqa: E402
import upsell1_adapter  # noqa: E402
import upsell2_adapter  # noqa: E402

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

U1_COPY = SKILL_DIR / "fixtures" / "copy-upsell1-public.valid.json"
U1_COPY_ARTIFACT = "80-signature-upsell/fixtures/copy-upsell1-public.valid.json"
U1_BAD_COPY = SKILL_DIR / "fixtures" / "copy-regression-a3-offlist-scarcity.json"
U2_COPY = SKILL_DIR / "fixtures" / "copy-upsell2-public.valid.json"
U2_COPY_ARTIFACT = "80-signature-upsell/fixtures/copy-upsell2-public.valid.json"
MADE_UP_REF = "ledger:made-up-buyer-0001"
MADE_UP_REF_U1 = "ledger:made-up-u1-0001"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def u1_inputs(test_only=True, main_ref=None):
    request = load(SKILL_DIR / "fixtures" / "request-upsell1.testonly.json")
    journey = load(FIXTURES / "journey-main-only.testonly.json")
    if not test_only:
        request["test_only"] = False
    if main_ref:
        request["eligibility"]["original_purchase"]["evidence_ref"] = main_ref
        journey["verified_purchases"][0]["evidence_ref"] = main_ref
    return request, journey


def build_u1(request, journey, copy_path=U1_COPY, artifact=U1_COPY_ARTIFACT):
    return upsell1_adapter.build_bundle(
        request, load(U1_COPY), journey,
        copy_sha256=common.sha256_file(copy_path), copy_artifact_path=str(artifact),
    )


def u2_inputs(test_only=True, main_ref=None, qual_ref=None):
    request = load(FIXTURES / "request-upsell2-from-upsell1.testonly.json")
    journey = load(FIXTURES / "journey-upsell2-from-upsell1.testonly.json")
    if not test_only:
        request["test_only"] = False
    if main_ref:
        request["eligibility"]["original_purchase"]["evidence_ref"] = main_ref
        journey["verified_purchases"][0]["evidence_ref"] = main_ref
    if qual_ref:
        request["eligibility"]["qualifying_purchase"]["evidence_ref"] = qual_ref
        journey["verified_purchases"][1]["evidence_ref"] = qual_ref
    return request, journey


def build_u2(request, journey):
    return upsell2_adapter.build_bundle(
        request, load(U2_COPY), journey,
        copy_sha256=common.sha256_file(U2_COPY), copy_artifact_path=U2_COPY_ARTIFACT,
    )


class CopyValidationIsNeverALiteral(unittest.TestCase):
    """UPS-01 row: build_result has no literal copy_validation exit 0 / pass."""

    def test_valid_copy_records_the_real_validator_outcome(self):
        request, journey = u1_inputs()
        cv = build_u1(request, journey)["result"]["copy_validation"]
        self.assertEqual((cv["verdict"], cv["exit_code"]), ("pass", 0))
        self.assertEqual(cv, common.run_copy_validation(
            common.sha256_file(U1_COPY), U1_COPY_ARTIFACT, "native-one-click:TEST-ONLY-U1"))

    def test_violating_copy_is_recorded_as_violation_and_blocks(self):
        request, journey = u1_inputs()
        result = build_u1(request, journey, U1_BAD_COPY, U1_BAD_COPY)["result"]
        self.assertEqual(result["copy_validation"]["verdict"], "violation")
        self.assertEqual(result["copy_validation"]["exit_code"], 2)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("copy_validation violation", " ".join(result["blockers"]))

    def test_unresolvable_or_changed_copy_is_not_run_never_pass(self):
        request, journey = u1_inputs()
        result = build_u1(request, journey, artifact="no/such/copy.json")["result"]
        self.assertEqual(result["copy_validation"]["verdict"], "not_run")
        self.assertIn("not_run", " ".join(result["blockers"]))
        # recorded sha does not match the bytes found at the path
        cv = common.run_copy_validation("0" * 64, U1_COPY_ARTIFACT, "native-one-click:X")
        self.assertEqual(cv["verdict"], "not_run")

    def test_caller_supplied_real_outcome_is_passed_through(self):
        request, journey = u1_inputs()
        bundle = build_u1(request, journey)
        given = dict(bundle["result"]["copy_validation"], exit_code=2, verdict="violation")
        result = common.build_result(
            request=request, copy_sha256=given["copy_sha256"],
            copy_artifact_path=U1_COPY_ARTIFACT, cta_map=bundle["result"]["cta_map"],
            eligibility_check=bundle["result"]["eligibility_check"],
            disposition=bundle["page_plan"]["disposition"], test_outcomes=[],
            copy_validation=given,
        )
        self.assertEqual(result["copy_validation"], given)
        self.assertEqual(result["status"], "blocked")


class EligibilityIsDesignOnlyAtBuild(unittest.TestCase):
    """UPS-02: nothing at build time proves a purchase."""

    def test_u1_made_up_ref_on_real_launch_is_design_only_never_eligible(self):
        request, journey = u1_inputs(test_only=False, main_ref=MADE_UP_REF)
        result = build_u1(request, journey)["result"]
        self.assertEqual(result["eligibility_check"]["verdict"], common.DESIGN_ONLY_VERDICT)
        self.assertEqual(common.DESIGN_ONLY_VERDICT, "design_only/unverified_at_build")
        self.assertIn(common.DESIGN_ONLY_VERDICT, " ".join(result["blockers"]))
        self.assertFalse(result["test_only"])

    def test_u2_made_up_refs_on_real_launch_are_design_only_never_eligible(self):
        request, journey = u2_inputs(test_only=False, main_ref=MADE_UP_REF, qual_ref=MADE_UP_REF_U1)
        result = build_u2(request, journey)["result"]
        self.assertEqual(result["eligibility_check"]["verdict"], common.DESIGN_ONLY_VERDICT)

    def test_real_launch_journey_without_a_resolvable_ledger_ref_is_blocked(self):
        # bare id: structurally valid for the schema, but not a ledger reference
        request, journey = u1_inputs(test_only=False, main_ref="launch-ref-0001")
        result = build_u1(request, journey)["result"]
        self.assertEqual(result["eligibility_check"]["verdict"], "blocked_unverified")
        self.assertIn("resolvable ledger reference",
                      " ".join(common.original_purchase_check(request, journey)["problems"]))

    def test_no_real_launch_result_ever_says_eligible(self):
        for refs in (MADE_UP_REF, "ledger:x", "s44:evt/1", "native:order-1"):
            request, journey = u1_inputs(test_only=False, main_ref=refs)
            verdict = build_u1(request, journey)["result"]["eligibility_check"]["verdict"]
            self.assertNotEqual(verdict, "eligible", refs)


class MarkerGuardIsShared(unittest.TestCase):
    """UPS-03: marker strings are rejected for every prior purchase."""

    MARKERS = ("acceptedU1=true", "client-side parameter", "client_side_flag", "acceptedU1 = TRUE")

    def test_helper(self):
        for m in self.MARKERS:
            self.assertIsNotNone(common.client_claim_problem("x " + m, "t"), m)
        self.assertIsNone(common.client_claim_problem("ledger:order-1", "t"))
        self.assertIsNone(common.client_claim_problem(None, "t"))

    def test_u1_main_evidence_marker_is_blocked_unverified(self):
        for m in self.MARKERS:
            request, journey = u1_inputs(main_ref="TEST-ONLY-" + m)
            # the request is the visitor's claim; the journey carries the same text
            check = common.original_purchase_check(request, journey)
            self.assertFalse(check["verified"], m)
            self.assertIn("client-side claim", " ".join(check["problems"]), m)
            result = build_u1(request, journey)["result"]
            self.assertEqual(result["eligibility_check"]["verdict"], "blocked_unverified", m)
            self.assertEqual(result["status"], "blocked", m)

    def test_marker_only_in_journey_still_blocks_original_purchase(self):
        request, journey = u1_inputs()
        journey["verified_purchases"][0]["evidence_ref"] = "acceptedU1=true"
        request["eligibility"]["original_purchase"]["evidence_ref"] = "acceptedU1=true"
        self.assertFalse(common.original_purchase_check(request, journey)["verified"])

    def test_u2_main_evidence_marker_is_blocked_unverified(self):
        for m in self.MARKERS:
            ref = "TEST-ONLY-" + m
            request, journey = u2_inputs(main_ref=ref)
            check = upsell2_adapter.check_u2_eligibility(request, journey)
            self.assertFalse(check["verified"], m)
            result = build_u2(request, journey)["result"]
            self.assertEqual(result["eligibility_check"]["verdict"], "blocked_unverified", m)
            self.assertFalse(result["eligibility_check"]["original_purchase_verified"], m)


class RuntimeSchemaValidation(unittest.TestCase):
    """UPS-14: shipped schemas are applied to a real run, failing closed."""

    def test_request_with_an_extra_key_is_rejected(self):
        request, _ = u1_inputs()
        request["smuggled_field"] = "x"
        with self.assertRaisesRegex(common.AdapterError, "unexpected key 'smuggled_field'"):
            common.validate_request(request, "upsell_1")
        request, _ = u1_inputs()
        request["offer"]["extra_inner"] = 1
        with self.assertRaises(common.AdapterError):
            common.validate_request(request, "upsell_1")

    def test_request_bad_pattern_and_missing_required_are_rejected(self):
        request, _ = u1_inputs()
        request["location_id"] = 7
        with self.assertRaises(common.AdapterError):
            common.validate_request(request, "upsell_1")
        request, _ = u1_inputs(test_only=False)
        del request["action_binding"]
        with self.assertRaisesRegex(common.AdapterError, "action_binding"):
            common.validate_request(request, "upsell_1")

    def test_valid_request_still_passes(self):
        request, _ = u1_inputs()
        common.validate_request(request, "upsell_1")

    def test_result_missing_a_required_field_is_rejected(self):
        request, journey = u1_inputs()
        result = build_u1(request, journey)["result"]
        common.validate_against_schema(result, common.RESULT_SCHEMA_PATH, "result")
        for key in ("proof_class", "copy_validation", "eligibility_check"):
            broken = copy.deepcopy(result)
            del broken[key]
            with self.assertRaisesRegex(common.AdapterError, "missing required key '%s'" % key):
                common.validate_against_schema(broken, common.RESULT_SCHEMA_PATH, "result")
        extra = dict(result, rogue=1)
        with self.assertRaises(common.AdapterError):
            common.validate_against_schema(extra, common.RESULT_SCHEMA_PATH, "result")

    def test_unknown_schema_keyword_fails_closed(self):
        with self.assertRaises(common.AdapterError):
            common.schema_errors(1, {"multipleOf": 2})

    @unittest.skipUnless(jsonschema, "jsonschema not available")
    def test_stdlib_validator_agrees_with_jsonschema_on_every_fixture(self):
        req_schema = load(common.REQUEST_SCHEMA_PATH)
        res_schema = load(common.RESULT_SCHEMA_PATH)
        paths = sorted(list((SKILL_DIR / "fixtures").glob("request-*.json"))
                       + list(FIXTURES.glob("request-*.json")))
        self.assertGreater(len(paths), 8)
        for path in paths:
            doc = load(path)
            ours = bool(common.schema_errors(doc, req_schema))
            ref = not jsonschema.Draft202012Validator(req_schema).is_valid(doc)
            self.assertEqual(ours, ref, path.name)
        for path in sorted((SKILL_DIR / "fixtures").glob("result-*.json")):
            doc = load(path)
            ours = bool(common.schema_errors(doc, res_schema))
            ref = not jsonschema.Draft202012Validator(res_schema).is_valid(doc)
            self.assertEqual(ours, ref, path.name)


def _disc(billing, terms, amount=9700):
    return {"amount_minor": amount, "currency": "USD", "billing_type": billing,
            "recurring_terms": terms}


def _terms(**kw):
    base = {"interval": "month", "interval_count": 1, "cycles": None,
            "trial_amount_minor": None, "trial_period": None}
    base.update(kw)
    return base


class DisclosureGoldenStrings(unittest.TestCase):
    """UPS-19: due today, trial amount/period and first recurring charge."""

    PAY = "Charged to your original payment method when you accept."

    def test_one_time(self):
        self.assertEqual(
            common.render_disclosure(_disc("one_time", None)),
            "One-time charge of USD 97.00, charged to your original payment "
            "method when you accept. No further charges for this offer.")

    def test_recurring(self):
        self.assertEqual(
            common.render_disclosure(_disc("recurring", _terms())),
            "USD 97.00 today, then USD 97.00 per month until cancelled, charged "
            "to your original payment method when you accept.")

    def test_recurring_with_stated_first_charge_and_cycles(self):
        self.assertEqual(
            common.render_disclosure(_disc("recurring", _terms(cycles=3), 4700)),
            "USD 47.00 today, then USD 47.00 per month for 2 further payments "
            "(3 payments total), charged to your original payment method when "
            "you accept.")

    def test_installment(self):
        self.assertEqual(
            common.render_disclosure(_disc("installment", _terms(cycles=4), 2500)),
            "Due today: USD 25.00. Then USD 25.00 per month for 3 further payments "
            "(4 payments total). First recurring charge: 1 month after you accept. "
            + self.PAY)
        self.assertEqual(
            common.render_disclosure(_disc("installment", _terms(
                cycles=3, interval="week", interval_count=2,
                first_recurring_charge="2026-12-01"))),
            "Due today: USD 97.00. Then USD 97.00 every 2 weeks for 2 further payments "
            "(3 payments total). First recurring charge: 2026-12-01. " + self.PAY)

    def test_trial(self):
        text = common.render_disclosure(_disc("trial", _terms(
            trial_amount_minor=100, trial_period="7 days")))
        self.assertEqual(
            text,
            "Due today: USD 1.00 for a trial lasting 7 days. After the trial: "
            "USD 97.00 per month until cancelled. First recurring charge: when the "
            "trial ends (after 7 days). " + self.PAY)
        # the old text said USD 97.00 today AND USD 1.00 for the trial
        self.assertNotIn("USD 97.00 today", text)

    def test_trial_plus_recurring(self):
        self.assertEqual(
            common.render_disclosure(_disc("recurring", _terms(
                cycles=6, trial_amount_minor=0, trial_period="14 days",
                first_recurring_charge="2026-12-01"))),
            "Due today: USD 0.00 for a trial lasting 14 days. After the trial: "
            "USD 97.00 per month for 6 payments. First recurring charge: "
            "2026-12-01. " + self.PAY)

    def test_trial_and_installment_without_their_terms_are_refused(self):
        with self.assertRaises(common.AdapterError):
            common.render_disclosure(_disc("trial", _terms()))
        with self.assertRaises(common.AdapterError):
            common.render_disclosure(_disc("installment", _terms()))
        with self.assertRaises(common.AdapterError):
            common.render_disclosure(_disc("installment", _terms(cycles=1)))

    def test_request_schema_requires_the_terms_the_disclosure_states(self):
        request, _ = u1_inputs()
        request["disclosure"] = dict(request["disclosure"], billing_type="trial",
                                     recurring_terms=_terms())
        errs = common.schema_errors(request, load(common.REQUEST_SCHEMA_PATH))
        self.assertTrue(any("trial_amount_minor" in e for e in errs), errs)
        request["disclosure"]["billing_type"] = "installment"
        errs = common.schema_errors(request, load(common.REQUEST_SCHEMA_PATH))
        self.assertTrue(any("cycles" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
