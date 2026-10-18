"""Result-extension contract tests (S81-02 remainder).

The fixture must validate against schemas/downsell-result-extension.schema
.json (when jsonschema is available) AND pass the semantic validator
validate_result_extension. Each round-5 reviewer probe is a named test
here: the mutated result must be rejected by the semantic validator
and/or the schema."""
import copy
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validators"))
import validate_downsell as vd  # noqa: E402

try:
    import jsonschema
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

FIXTURE = json.loads(
    (ROOT / "fixtures" / "valid-downsell-result.json").read_text()
)["downsell_result_extension"]
SCHEMA = json.loads(
    (ROOT / "schemas" / "downsell-result-extension.schema.json").read_text()
)
CANONICAL_U2 = FIXTURE["route_result"]["canonical_u2_page_id"]


def schema_errors(ext):
    if not HAVE_JSONSCHEMA:
        return []
    validator = jsonschema.Draft202012Validator(SCHEMA)
    return list(validator.iter_errors(ext))


class TestResultExtension(unittest.TestCase):
    def test_fixture_passes_semantic_validator(self):
        self.assertEqual(
            vd.validate_result_extension(FIXTURE, canonical_u2_page_id=CANONICAL_U2),
            [],
        )

    @unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
    def test_fixture_validates_against_schema(self):
        self.assertEqual(schema_errors(FIXTURE), [])

    @unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
    def test_schema_itself_is_valid(self):
        jsonschema.Draft202012Validator.check_schema(SCHEMA)

    # --- round-5 probes: every one must now be rejected ---

    def test_probe1_d1_specific_duplicate_u2_id_rejected(self):
        ext = copy.deepcopy(FIXTURE)
        ext["route_result"]["canonical_u2_page_id"] = "downsell1-upsell2-copy"
        v = vd.validate_result_extension(ext, canonical_u2_page_id=CANONICAL_U2)
        self.assertIn("D1-RESULT-ROUTE-NONCANONICAL-U2-ID", v)

    def test_probe2_contradictory_route_result_rejected(self):
        ext = copy.deepcopy(FIXTURE)
        ext["route_result"]["success_target"] = "thank_you"  # id still set
        v = vd.validate_result_extension(ext, canonical_u2_page_id=CANONICAL_U2)
        self.assertIn("D1-RESULT-ROUTE-CONTRADICTORY-U2-ID", v)

    def test_probe2b_u2_target_without_canonical_id_rejected(self):
        ext = copy.deepcopy(FIXTURE)
        ext["route_result"]["canonical_u2_page_id"] = None
        v = vd.validate_result_extension(ext)
        self.assertIn("D1-RESULT-ROUTE-U2-TARGET-WITHOUT-CANONICAL-ID", v)

    def test_probe3_trial_without_renewal_disclosure_rejected(self):
        ext = copy.deepcopy(FIXTURE)
        ext["disclosure_audit"] = {
            "billing_type": "trial",
            "due_now_minor": 100,
            "renewal_amount_minor": None,
            "renewal_date_or_rule": None,
            "cancellation_terms_present": False,
        }
        v = vd.validate_result_extension(ext)
        self.assertIn("D1-RESULT-DISCLOSURE-RENEWAL-AMOUNT-MISSING", v)
        self.assertIn("D1-RESULT-DISCLOSURE-RENEWAL-DATE-MISSING", v)
        self.assertIn("D1-RESULT-DISCLOSURE-CANCELLATION-MISSING", v)
        if HAVE_JSONSCHEMA:
            self.assertTrue(schema_errors(ext), "schema must reject trial without renewal terms")

    def test_probe4_unrecorded_heading_normalization_rejected(self):
        ext = copy.deepcopy(FIXTURE)
        ext["heading_normalization"]["recorded"] = False
        v = vd.validate_result_extension(ext)
        self.assertIn("D1-RESULT-HEADING-NORMALIZATION-NOT-RECORDED", v)
        if HAVE_JSONSCHEMA:
            self.assertTrue(schema_errors(ext), "schema const must reject recorded=false")

    def test_probe5_section12_not_replaced_rejected(self):
        ext = copy.deepcopy(FIXTURE)
        for m in ext["source_profile_mapping"]:
            if m["derived_section"] == 8:
                m["original_sections"] = ["12"]
        v = vd.validate_result_extension(ext)
        self.assertIn("D1-RESULT-MAPPING-SECTION-8-NOT-REPLACED-12", v)

    def test_probe6_cta_map_missing_a_section_rejected(self):
        ext = copy.deepcopy(FIXTURE)
        ext["cta_map"][7]["section"] = 3  # section 8 absent, 3 duplicated
        v = vd.validate_result_extension(ext)
        self.assertIn("D1-RESULT-CTA-SECTIONS-NOT-1-TO-8", v)

    def test_probe7_degenerate_source_mapping_rejected(self):
        ext = copy.deepcopy(FIXTURE)
        for m in ext["source_profile_mapping"]:
            m["derived_section"] = 1
        v = vd.validate_result_extension(ext)
        self.assertIn("D1-RESULT-MAPPING-DERIVED-SECTIONS-NOT-1-TO-8", v)

    # --- the two hard defects from round 5 ---

    def test_ui_states_ref_required(self):
        ext = copy.deepcopy(FIXTURE)
        ext["ui_states_ref"] = ""
        v = vd.validate_result_extension(ext)
        self.assertIn("D1-RESULT-UI-STATES-REF-MISSING", v)
        if HAVE_JSONSCHEMA:
            self.assertTrue(schema_errors(ext))

    def test_refined_offer_description_required(self):
        ext = copy.deepcopy(FIXTURE)
        ext["refined_offer_description"] = "  "
        v = vd.validate_result_extension(ext)
        self.assertIn("D1-RESULT-REFINED-DESCRIPTION-MISSING", v)

    def test_cta_map_must_use_one_action(self):
        ext = copy.deepcopy(FIXTURE)
        ext["cta_map"][3]["action_ref"] = "some-other-action"
        v = vd.validate_result_extension(ext)
        self.assertIn("D1-RESULT-CTA-MULTIPLE-ACTIONS", v)

    def test_reduced_scope_must_name_u1_only_entitlements(self):
        ext = copy.deepcopy(FIXTURE)
        ext["difference_matrix"]["entitlements_u1_only"] = []
        v = vd.validate_result_extension(ext)
        self.assertIn("D1-RESULT-DIFFERENCE-REDUCED-SCOPE-UNPROVEN", v)


if __name__ == "__main__":
    unittest.main()
