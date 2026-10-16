"""S80-04 - Upsell 1 production adapter tests (kept separate from U2 tests).

Uses the sibling 80-signature-upsell fixtures as canonical inputs and
verifies: the upsell-result structure against the S80-02 result schema,
the 8-entry CTA map bound to the single guarded action placeholder, the
adjacent disclosure rendered from integer minor units, processing /
decline / failure state declarations, U1 eligibility (verified original
purchase only), and determinism against the stored expected bundle.

Run: python3 -m unittest discover -s tests -v   (from adapters/)
"""

import copy
import json
import sys
import unittest
from pathlib import Path

ADAPTERS_DIR = Path(__file__).resolve().parents[1]
WORK_DIR = ADAPTERS_DIR.parent
SKILL_DIR = WORK_DIR / "80-signature-upsell"
FIXTURES = ADAPTERS_DIR / "fixtures"
sys.path.insert(0, str(ADAPTERS_DIR))

import adapter_common as common
import upsell1_adapter

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

U1_COPY_ARTIFACT = "80-signature-upsell/fixtures/copy-upsell1-public.valid.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_u1(journey_name="journey-main-only.testonly.json", request=None):
    request = request or load(SKILL_DIR / "fixtures" / "request-upsell1.testonly.json")
    copy_doc = load(SKILL_DIR / "fixtures" / "copy-upsell1-public.valid.json")
    journey = load(FIXTURES / journey_name)
    return upsell1_adapter.build_bundle(
        request,
        copy_doc,
        journey,
        copy_sha256=common.sha256_file(SKILL_DIR / "fixtures" / "copy-upsell1-public.valid.json"),
        copy_artifact_path=U1_COPY_ARTIFACT,
    )


@unittest.skipUnless(jsonschema, "jsonschema not available")
class Upsell1SchemaTests(unittest.TestCase):
    def test_request_validates_against_sibling_request_schema(self):
        schema = load(SKILL_DIR / "schemas" / "upsell-request.schema.json")
        request = load(SKILL_DIR / "fixtures" / "request-upsell1.testonly.json")
        jsonschema.validate(request, schema)

    def test_result_validates_against_sibling_result_schema(self):
        schema = load(SKILL_DIR / "schemas" / "upsell-result.schema.json")
        jsonschema.validate(build_u1()["result"], schema)


class Upsell1BundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = build_u1()
        cls.result = cls.bundle["result"]
        cls.plan = cls.bundle["page_plan"]

    def test_identity_and_instance_kept_separate(self):
        self.assertEqual(self.result["instance"], "upsell_1")
        self.assertEqual(self.result["page_id"], "TEST-UPSELL_1")
        self.assertEqual(self.result["status"], "authored")
        self.assertEqual(self.result["proof_class"], "L1")
        self.assertFalse(self.result["independent_review"])

    def test_cta_map_eight_entries_one_guarded_action(self):
        cta_map = self.result["cta_map"]
        self.assertEqual(len(cta_map), 8)
        self.assertEqual([c["section_number"] for c in cta_map], list(range(1, 9)))
        # S80-06 binding integration: bundle CTAs bind the extra-offer
        # binding ref for the same offer (the copy/request layer keeps
        # declaring the native-one-click form; see adapter_common).
        self.assertEqual({c["action_ref"] for c in cta_map},
                         {"extra-offer-binding:TEST-ONLY-U1"})
        copy_doc = load(SKILL_DIR / "fixtures" / "copy-upsell1-public.valid.json")
        self.assertEqual([c["cta_text"] for c in cta_map],
                         [s["cta"]["text"] for s in copy_doc["sections"]])

    def test_native_action_is_pending_placeholder_never_invented(self):
        # S80-06: the binding integration now exists (verified_by /
        # status say so), but the native action itself is still not
        # provisioned - every native identifier stays null, never
        # invented, and the status names the S06 confirmation still owed.
        native = self.result["native_action"]
        self.assertIsNone(native["action_id"])
        self.assertIsNone(native["settings_ref"])
        self.assertIsNone(native["binding_screenshot_ref"])
        self.assertEqual(native["verified_by"], "s80_06_binding")
        self.assertEqual(self.plan["action_binding"]["status"],
                         "interface_conformant_pending_s06")
        self.assertEqual(self.plan["action_binding"]["kind"], "extra_offer_binding")
        self.assertEqual(self.plan["action_binding"]["action_ref"],
                         "extra-offer-binding:TEST-ONLY-U1")
        self.assertEqual(self.plan["action_binding"]["native_action_ref"],
                         "native-one-click:TEST-ONLY-U1")
        self.assertIsNone(self.plan["action_binding"]["action_id"])

    def test_disclosure_rendered_from_integer_minor_units(self):
        text = self.plan["disclosure"]["text"]
        self.assertIn("USD 67.00", text)
        self.assertIn("One-time charge", text)
        self.assertTrue(self.plan["disclosure"]["adjacent_to_cta"])
        self.assertEqual(self.plan["disclosure"]["amount_minor"], 6700)
        mapping = self.result["approved_offer_mapping"]
        self.assertEqual(mapping["amount_minor"], 6700)
        self.assertEqual(mapping["currency"], "USD")
        self.assertEqual(mapping["billing_type"], "one_time")
        audit = self.result["disclosure_audit"]
        self.assertEqual(audit["verdict"], "pending_native_binding")
        self.assertIsNone(audit["amount_matches_native"])
        self.assertTrue(any("USD 67.00" in n for n in audit["notes"]))

    def test_processing_decline_and_failure_states_declared(self):
        states = self.plan["states"]
        self.assertEqual(states["processing"]["repeat_click_while_pending"],
                         "ignored_by_single_flight_guard")
        self.assertTrue(states["decline"]["visible"])
        self.assertFalse(states["decline"]["charges"])
        self.assertEqual(states["decline"]["target_role"], "downsell_1")
        self.assertEqual(states["decline"]["target_page_id"], "TEST-DOWNSELL_1")
        failed = states["payment_pending_or_failed"]
        self.assertFalse(failed["is_acceptance"])
        self.assertFalse(failed["is_decline"])
        self.assertFalse(failed["grants_entitlement"])
        self.assertEqual(self.plan["success_route"]["target_role"], "upsell_2")
        self.assertEqual(self.plan["success_route"]["target_page_id"], "TEST-UPSELL_2")
        triggers = self.plan["action_binding"]["triggers_that_never_purchase"]
        self.assertEqual(set(triggers),
                         {"page_load", "scroll", "timer_expiry", "close_icon_click"})

    def test_eligibility_is_verified_original_purchase(self):
        check = self.result["eligibility_check"]
        self.assertTrue(check["original_purchase_verified"])
        self.assertIsNone(check["qualifying_purchase_slot"])
        self.assertEqual(check["verdict"], "eligible")
        self.assertEqual(self.plan["disposition"]["action"], "present_offer")

    def test_acknowledgement_only_after_verified_purchase(self):
        blocks = self.plan["acknowledgement_blocks"]
        self.assertEqual(len(blocks), 1)
        self.assertIn("original purchase is confirmed", blocks[0]["text"])
        self.assertIn("optional extra", blocks[0]["text"])

    def test_deterministic_against_stored_expected_bundle(self):
        expected = load(FIXTURES / "expected-bundle-upsell1.testonly.json")
        self.assertEqual(self.bundle, expected)


class Upsell1NegativeTests(unittest.TestCase):
    def test_client_side_claim_is_blocked_not_proof(self):
        request = load(SKILL_DIR / "fixtures" / "request-upsell1.testonly.json")
        request["eligibility"]["original_purchase"]["verification_source"] = (
            "client_side_parameter"
        )
        bundle = build_u1(request=request)
        self.assertEqual(bundle["result"]["status"], "blocked")
        self.assertEqual(bundle["result"]["eligibility_check"]["verdict"],
                         "blocked_unverified")
        self.assertEqual(bundle["page_plan"]["disposition"]["action"],
                         "block_unverified")
        self.assertFalse(bundle["page_plan"]["disposition"]["charge_action_emitted"])

    def test_action_binding_mismatch_fails_closed(self):
        # Conformance repair (D-03): the sibling U1 request declares an
        # action_binding for TEST-ONLY-U1; pointing it at another offer's
        # action must fail closed in validate_request.
        request = load(SKILL_DIR / "fixtures" / "request-upsell1.testonly.json")
        request["action_binding"]["expected_action_ref"] = (
            "native-one-click:SOME-OTHER-OFFER"
        )
        with self.assertRaises(common.AdapterError):
            build_u1(request=request)

    def test_missing_price_fails_closed(self):
        request = load(SKILL_DIR / "fixtures" / "request-upsell1.testonly.json")
        request["disclosure"]["amount_minor"] = None
        with self.assertRaises(common.AdapterError):
            build_u1(request=request)

    def test_float_price_rejected_no_float_money(self):
        request = load(SKILL_DIR / "fixtures" / "request-upsell1.testonly.json")
        request["disclosure"]["amount_minor"] = 67.00
        with self.assertRaises(common.AdapterError):
            build_u1(request=request)

    def test_already_owned_u1_is_suppressed_without_charge(self):
        journey = load(FIXTURES / "journey-main-only.testonly.json")
        journey["owned_entitlement_ids"] = ["TEST-ONLY-library"]
        request = load(SKILL_DIR / "fixtures" / "request-upsell1.testonly.json")
        copy_doc = load(SKILL_DIR / "fixtures" / "copy-upsell1-public.valid.json")
        bundle = upsell1_adapter.build_bundle(
            request, copy_doc, journey,
            copy_sha256=common.sha256_file(
                SKILL_DIR / "fixtures" / "copy-upsell1-public.valid.json"),
            copy_artifact_path=U1_COPY_ARTIFACT,
        )
        disposition = bundle["page_plan"]["disposition"]
        self.assertEqual(disposition["action"], "suppress_offer")
        self.assertEqual(disposition["reason"], "already_owned")
        self.assertFalse(disposition["charge_action_emitted"])
        self.assertEqual(bundle["result"]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
