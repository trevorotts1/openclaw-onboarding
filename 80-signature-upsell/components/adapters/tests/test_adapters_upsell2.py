"""S80-05 - Upsell 2 production adapter tests (kept separate from U1 tests).

Verifies the shared canonical U2 page across BOTH entry paths
(from_upsell_1 and from_downsell_1), entry-context truth in the
acknowledgement blocks (a D1 buyer is never told they bought the full
U1 package), the eligibility gate (verified U1-or-D1 required; bump-only
and client-side claims rejected), already-owned / incompatible
suppression with no duplicate charge, recurring disclosure rendering,
and determinism against the stored expected bundles.

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
import upsell2_adapter

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

U2_COPY_ARTIFACT = "80-signature-upsell/fixtures/copy-upsell2-public.valid.json"
U2_COPY_PATH = SKILL_DIR / "fixtures" / "copy-upsell2-public.valid.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_u2(request, journey_name):
    copy_doc = load(U2_COPY_PATH)
    journey = load(FIXTURES / journey_name)
    return upsell2_adapter.build_bundle(
        request, copy_doc, journey,
        copy_sha256=common.sha256_file(U2_COPY_PATH),
        copy_artifact_path=U2_COPY_ARTIFACT,
    )


def build_via_u1():
    return build_u2(load(FIXTURES / "request-upsell2-from-upsell1.testonly.json"),
                    "journey-upsell2-from-upsell1.testonly.json")


def build_via_d1():
    return build_u2(load(SKILL_DIR / "fixtures" / "request-upsell2.testonly.json"),
                    "journey-upsell2-from-downsell1.testonly.json")


@unittest.skipUnless(jsonschema, "jsonschema not available")
class Upsell2SchemaTests(unittest.TestCase):
    def test_both_entry_requests_validate_against_request_schema(self):
        schema = load(SKILL_DIR / "schemas" / "upsell-request.schema.json")
        jsonschema.validate(load(FIXTURES / "request-upsell2-from-upsell1.testonly.json"), schema)
        jsonschema.validate(load(SKILL_DIR / "fixtures" / "request-upsell2.testonly.json"), schema)

    def test_already_owned_request_validates_against_request_schema(self):
        # Conformance repair: the adapters-local already-owned fixture
        # must satisfy the same repaired schema (D-06/D-07/D-08).
        schema = load(SKILL_DIR / "schemas" / "upsell-request.schema.json")
        jsonschema.validate(
            load(FIXTURES / "request-upsell2-already-owned.testonly.json"), schema)

    def test_both_entry_results_validate_against_result_schema(self):
        schema = load(SKILL_DIR / "schemas" / "upsell-result.schema.json")
        jsonschema.validate(build_via_u1()["result"], schema)
        jsonschema.validate(build_via_d1()["result"], schema)

    def test_client_claim_request_is_schema_invalid(self):
        schema = load(SKILL_DIR / "schemas" / "upsell-request.schema.json")
        bad = load(SKILL_DIR / "fixtures" / "request-neg-u2-client-claim.json")
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)


class Upsell2SharedPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.via_u1 = build_via_u1()
        cls.via_d1 = build_via_d1()

    def test_one_canonical_u2_page_and_product_mapping_for_both_paths(self):
        r1, r2 = self.via_u1["result"], self.via_d1["result"]
        self.assertEqual(r1["page_id"], "TEST-UPSELL_2")
        self.assertEqual(r1["page_id"], r2["page_id"])
        self.assertEqual(r1["approved_offer_mapping"], r2["approved_offer_mapping"])
        self.assertEqual({c["action_ref"] for c in r1["cta_map"]},
                         {c["action_ref"] for c in r2["cta_map"]})
        self.assertEqual(len(r1["cta_map"]), 8)

    def test_both_paths_eligible_with_matching_entry_context(self):
        c1 = self.via_u1["result"]["eligibility_check"]
        self.assertEqual(c1["verdict"], "eligible")
        self.assertEqual(c1["qualifying_purchase_slot"], "upsell_1")
        self.assertEqual(c1["entry_context"], "from_upsell_1")
        c2 = self.via_d1["result"]["eligibility_check"]
        self.assertEqual(c2["verdict"], "eligible")
        self.assertEqual(c2["qualifying_purchase_slot"], "downsell_1")
        self.assertEqual(c2["entry_context"], "from_downsell_1")

    def test_u2_routes_both_end_at_final_thank_you(self):
        for bundle in (self.via_u1, self.via_d1):
            plan = bundle["page_plan"]
            self.assertEqual(plan["success_route"]["target_role"], "thank_you")
            self.assertEqual(plan["success_route"]["target_page_id"], "TEST-THANK_YOU")
            self.assertEqual(plan["states"]["decline"]["target_role"], "thank_you")
            self.assertFalse(plan["states"]["decline"]["charges"])

    def test_recurring_disclosure_rendered_from_terms(self):
        text = self.via_d1["page_plan"]["disclosure"]["text"]
        self.assertIn("USD 47.00", text)
        self.assertIn("per month", text)
        self.assertIn("3 payments total", text)
        audit = self.via_d1["result"]["disclosure_audit"]
        self.assertTrue(audit["recurring_terms_disclosed"])
        self.assertEqual(audit["verdict"], "pending_native_binding")

    def test_deterministic_against_stored_expected_bundles(self):
        self.assertEqual(
            self.via_u1,
            load(FIXTURES / "expected-bundle-upsell2-from-upsell1.testonly.json"),
        )
        self.assertEqual(
            self.via_d1,
            load(FIXTURES / "expected-bundle-upsell2-from-downsell1.testonly.json"),
        )


class Upsell2AcknowledgementTruthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.via_u1 = build_via_u1()
        cls.via_d1 = build_via_d1()

    @staticmethod
    def ack_text(bundle):
        return " ".join(
            b["text"] for b in bundle["page_plan"]["acknowledgement_blocks"]
        )

    def test_d1_buyer_is_never_told_they_bought_the_full_u1_package(self):
        text = self.ack_text(self.via_d1)
        self.assertIn("Lite Start Pass", text)  # the actual verified D1 offer
        self.assertIn("downsell choice is confirmed", text)
        self.assertIn("instead of the full first-upgrade package", text)
        self.assertNotIn("Deep Work Library", text)  # the U1 offer name
        self.assertNotIn("first upgrade is confirmed", text)
        self.assertNotIn("Your first upgrade is confirmed", text)

    def test_u1_buyer_acknowledges_the_actual_u1_purchase(self):
        text = self.ack_text(self.via_u1)
        self.assertIn("first upgrade is confirmed", text)
        self.assertIn("Deep Work Library", text)
        self.assertNotIn("downsell choice", text)

    def test_base_block_is_truthful_on_both_paths(self):
        for bundle in (self.via_u1, self.via_d1):
            text = self.ack_text(bundle)
            self.assertIn("original purchase is confirmed", text)
            self.assertIn("stays yours either way", text)


class Upsell2EligibilityGateTests(unittest.TestCase):
    def test_bump_only_never_qualifies(self):
        bundle = build_u2(
            load(SKILL_DIR / "fixtures" / "request-neg-u2-bump-only.json"),
            "journey-upsell2-bump-only.testonly.json",
        )
        self.assertEqual(bundle["result"]["status"], "blocked")
        self.assertEqual(bundle["result"]["eligibility_check"]["verdict"],
                         "blocked_unverified")
        self.assertIsNone(
            bundle["result"]["eligibility_check"]["qualifying_purchase_slot"])
        self.assertFalse(bundle["page_plan"]["disposition"]["charge_action_emitted"])
        blockers = " ".join(bundle["result"]["blockers"])
        self.assertIn("bump alone never qualifies", blockers)

    def test_client_side_claim_fails_closed(self):
        bad = load(SKILL_DIR / "fixtures" / "request-neg-u2-client-claim.json")
        journey = load(FIXTURES / "journey-upsell2-client-claim.testonly.json")
        # The eligibility checker itself refuses client-side proof...
        check = upsell2_adapter.check_u2_eligibility(bad, journey)
        self.assertFalse(check["verified"])
        self.assertTrue(any("client" in p or "adapter source" in p
                            for p in check["problems"]))
        # ...and the adapter refuses to build a presentable page from it.
        with self.assertRaises(common.AdapterError):
            build_u2(bad, "journey-upsell2-client-claim.testonly.json")

    def test_entry_context_must_agree_with_verified_slot(self):
        request = load(FIXTURES / "request-upsell2-from-upsell1.testonly.json")
        request["entry_context"] = "from_downsell_1"  # journey proves U1, not D1
        bundle = build_u2(request, "journey-upsell2-from-upsell1.testonly.json")
        self.assertEqual(bundle["result"]["status"], "blocked")
        blockers = " ".join(bundle["result"]["blockers"])
        self.assertIn("entry_context", blockers)

    def test_u2_success_route_cannot_loop_to_itself(self):
        request = load(FIXTURES / "request-upsell2-from-upsell1.testonly.json")
        request["routes"]["on_payment_succeeded"] = {
            "target_role": "upsell_2", "target_page_id": "TEST-UPSELL_2"}
        with self.assertRaises(common.AdapterError):
            build_u2(request, "journey-upsell2-from-upsell1.testonly.json")


class Upsell2ConformanceRepairTests(unittest.TestCase):
    """Regression tests for the adapter conformance repair against the
    D-06/D-07/D-08-repaired sibling schemas: the qualifying purchase's
    verification_source must be an adapter source, must be the source
    the verified journey evidence was recorded under, and must never be
    a client-side claim; a declared action_binding must name this
    offer's guarded action."""

    def test_qualifying_verification_source_must_match_journey_record(self):
        request = load(FIXTURES / "request-upsell2-from-upsell1.testonly.json")
        # An adapter-enum source, but NOT the source the journey record
        # was recorded under (s44_event_adapter): mere assertion fails.
        request["eligibility"]["qualifying_purchase"]["verification_source"] = (
            "provider_event_readback"
        )
        bundle = build_u2(request, "journey-upsell2-from-upsell1.testonly.json")
        self.assertEqual(bundle["result"]["status"], "blocked")
        self.assertEqual(bundle["result"]["eligibility_check"]["verdict"],
                         "blocked_unverified")
        self.assertIn("verification_source",
                      " ".join(bundle["result"]["blockers"]))
        self.assertFalse(bundle["page_plan"]["disposition"]["charge_action_emitted"])

    def test_qualifying_without_verification_source_is_not_proof(self):
        request = load(FIXTURES / "request-upsell2-from-upsell1.testonly.json")
        del request["eligibility"]["qualifying_purchase"]["verification_source"]
        check = upsell2_adapter.check_u2_eligibility(
            request, load(FIXTURES / "journey-upsell2-from-upsell1.testonly.json"))
        self.assertFalse(check["verified"])
        self.assertTrue(any("verification_source" in p for p in check["problems"]))

    def test_qualifying_client_claim_evidence_ref_is_not_proof(self):
        request = load(FIXTURES / "request-upsell2-from-upsell1.testonly.json")
        request["eligibility"]["qualifying_purchase"]["evidence_ref"] = (
            "acceptedU1=true (client-side URL parameter)"
        )
        check = upsell2_adapter.check_u2_eligibility(
            request, load(FIXTURES / "journey-upsell2-from-upsell1.testonly.json"))
        self.assertFalse(check["verified"])
        self.assertTrue(any("client" in p for p in check["problems"]))

    def test_action_binding_mismatch_fails_closed(self):
        request = load(FIXTURES / "request-upsell2-from-upsell1.testonly.json")
        request["action_binding"]["expected_action_ref"] = (
            "native-one-click:SOME-OTHER-OFFER"
        )
        with self.assertRaises(common.AdapterError):
            build_u2(request, "journey-upsell2-from-upsell1.testonly.json")


class Upsell2SuppressionTests(unittest.TestCase):
    def test_already_owned_routes_to_thank_you_without_charge(self):
        bundle = build_u2(
            load(FIXTURES / "request-upsell2-already-owned.testonly.json"),
            "journey-upsell2-already-owned.testonly.json",
        )
        disposition = bundle["page_plan"]["disposition"]
        self.assertEqual(disposition["action"], "route_to_final_thank_you")
        self.assertEqual(disposition["reason"], "already_owned")
        self.assertEqual(disposition["safe_route"], "thank_you")
        self.assertFalse(disposition["charge_action_emitted"])
        self.assertEqual(bundle["result"]["status"], "blocked")
        self.assertIn("already_owned", " ".join(bundle["result"]["blockers"]))

    def test_incompatible_entitlement_routes_to_thank_you_without_charge(self):
        bundle = build_u2(
            load(FIXTURES / "request-upsell2-from-upsell1.testonly.json"),
            "journey-upsell2-incompatible.testonly.json",
        )
        disposition = bundle["page_plan"]["disposition"]
        self.assertEqual(disposition["action"], "route_to_final_thank_you")
        self.assertEqual(disposition["reason"], "incompatible_entitlement")
        self.assertFalse(disposition["charge_action_emitted"])


_DROP = object()  # variant() sentinel: remove the key entirely

U2_POLICY_FIXTURE = FIXTURES / "request-upsell2-from-upsell1-policy.testonly.json"
U2_REQUEST_VIA_U1 = FIXTURES / "request-upsell2-from-upsell1.testonly.json"
U2_REQUEST_VIA_D1 = SKILL_DIR / "fixtures" / "request-upsell2.testonly.json"


def variant_of(path, **changes):
    request = copy.deepcopy(load(path))
    for key, value in changes.items():
        if value is _DROP:
            request.pop(key, None)
        else:
            request[key] = value
    return request


@unittest.skipUnless(jsonschema, "jsonschema not available")
class Upsell2PromptPolicySchemaTests(unittest.TestCase):
    """Adoption map 1.4 pair cases at the schema layer, instance
    upsell_2, exercised on BOTH entry-path request fixtures."""

    @classmethod
    def setUpClass(cls):
        cls.schema = load(SKILL_DIR / "schemas" / "upsell-request.schema.json")

    def test_pair_cases_on_both_entry_paths(self):
        for path in (U2_REQUEST_VIA_U1, U2_REQUEST_VIA_D1):
            # 1.0 without the field: valid (the legacy shape).
            jsonschema.validate(load(path), self.schema)
            # 1.1 with the field: valid (the adoption delta).
            jsonschema.validate(
                variant_of(path, schema_version="1.1",
                           prompt_policy_id="kie-rule-12-band"),
                self.schema)
            # 1.0 carrying the field: refused.
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(
                    variant_of(path, prompt_policy_id="kie-rule-12-band"),
                    self.schema)
            # 1.1 without the field: refused.
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(
                    variant_of(path, schema_version="1.1"), self.schema)

    def test_stored_11_fixture_validates(self):
        jsonschema.validate(load(U2_POLICY_FIXTURE), self.schema)

    def test_11_empty_null_and_nonstring_ids_refused(self):
        for bad_id in ("", None, 11, {"policy_id": "kie-rule-12-band"}):
            bad = variant_of(U2_REQUEST_VIA_U1, schema_version="1.1",
                             prompt_policy_id=bad_id)
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(bad, self.schema)

    def test_unknown_versions_refused(self):
        for version in ("1.2", "2.0"):
            bad = variant_of(U2_REQUEST_VIA_U1, schema_version=version)
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(bad, self.schema)


class Upsell2PromptPolicyAdapterTests(unittest.TestCase):
    """Adoption map 1.4 item 2: the runtime mirror's explicit pair check
    and the page-plan pass-through, instance upsell_2."""

    def test_11_via_u1_builds_and_carries_the_id_in_the_page_plan(self):
        bundle = build_u2(load(U2_POLICY_FIXTURE),
                          "journey-upsell2-from-upsell1.testonly.json")
        check = bundle["result"]["eligibility_check"]
        self.assertEqual(check["verdict"], "eligible")
        self.assertEqual(check["qualifying_purchase_slot"], "upsell_1")
        self.assertEqual(bundle["page_plan"]["prompt_policy_id"],
                         "kie-rule-12-band")
        # The result profile is unchanged: no policy field rides there.
        self.assertNotIn("prompt_policy_id", bundle["result"])

    def test_11_via_d1_builds_and_carries_the_id_in_the_page_plan(self):
        request = variant_of(U2_REQUEST_VIA_D1, schema_version="1.1",
                             prompt_policy_id="kie-rule-12-band")
        bundle = build_u2(request, "journey-upsell2-from-downsell1.testonly.json")
        check = bundle["result"]["eligibility_check"]
        self.assertEqual(check["verdict"], "eligible")
        self.assertEqual(check["qualifying_purchase_slot"], "downsell_1")
        self.assertEqual(bundle["page_plan"]["prompt_policy_id"],
                         "kie-rule-12-band")

    def test_11_bundle_matches_10_bundle_apart_from_the_plan_citation(self):
        bundle_10 = build_via_u1()
        bundle_11 = build_u2(load(U2_POLICY_FIXTURE),
                             "journey-upsell2-from-upsell1.testonly.json")
        self.assertEqual(bundle_11["result"], bundle_10["result"])
        self.assertEqual(bundle_11["native_binding"], bundle_10["native_binding"])
        plan_11 = dict(bundle_11["page_plan"])
        self.assertEqual(plan_11.pop("prompt_policy_id"), "kie-rule-12-band")
        self.assertEqual(plan_11, bundle_10["page_plan"])
        self.assertNotIn("prompt_policy_id", bundle_10["page_plan"])

    def test_11_without_field_fails_closed(self):
        with self.assertRaises(common.AdapterError):
            build_u2(variant_of(U2_REQUEST_VIA_U1, schema_version="1.1"),
                     "journey-upsell2-from-upsell1.testonly.json")

    def test_10_with_field_fails_closed(self):
        with self.assertRaises(common.AdapterError):
            build_u2(variant_of(U2_REQUEST_VIA_U1,
                                prompt_policy_id="kie-rule-12-band"),
                     "journey-upsell2-from-upsell1.testonly.json")

    def test_11_empty_null_and_nonstring_ids_fail_closed(self):
        for bad_id in ("", None, 11, {"policy_id": "kie-rule-12-band"}):
            with self.assertRaises(common.AdapterError):
                build_u2(variant_of(U2_REQUEST_VIA_U1, schema_version="1.1",
                                    prompt_policy_id=bad_id),
                         "journey-upsell2-from-upsell1.testonly.json")

    def test_unknown_versions_fail_closed(self):
        for version in ("1.2", "2.0"):
            with self.assertRaises(common.AdapterError):
                build_u2(variant_of(U2_REQUEST_VIA_U1, schema_version=version),
                         "journey-upsell2-from-upsell1.testonly.json")

    def test_unregistered_id_passes_the_adapter_pair_check(self):
        # Pinned open-string behavior (as in adoption 1.2 D-4): refusing
        # an unknown id is a registry-layer act at dispatch and at the
        # Q11 aggregator (map section 4 citation rule), not an adapter
        # act; this mirror enforces the pair rule and the field's shape.
        bundle = build_u2(
            variant_of(U2_REQUEST_VIA_U1, schema_version="1.1",
                       prompt_policy_id="an-unregistered-policy"),
            "journey-upsell2-from-upsell1.testonly.json")
        self.assertEqual(bundle["page_plan"]["prompt_policy_id"],
                         "an-unregistered-policy")


if __name__ == "__main__":
    unittest.main()
