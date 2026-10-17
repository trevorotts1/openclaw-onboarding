"""Stdlib request-validator tests (package change candidate PC-2).

validators/validate_request.py enforces schemas/downsell-request
.schema.json with the standard library only. The pre-existing schema
suite (test_request_schema_fixture.py) silently skips when the
third-party jsonschema package is not installed; this suite never
skips and never imports jsonschema, so the request contract is
checked on every machine. Every mutation below names the exact
violation code it must produce; the valid fixture must produce none.
Run: python3 -m unittest discover -s tests -v
"""
import copy
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validators"))
from validate_request import validate_request  # noqa: E402

SCHEMA = json.loads(
    (ROOT / "schemas" / "downsell-request.schema.json").read_text()
)
VALID = json.loads(
    (ROOT / "fixtures" / "valid-downsell-request.json").read_text()
)
REQUIRED = SCHEMA["required"]


def fresh():
    return copy.deepcopy(VALID)


class TestValidRequest(unittest.TestCase):
    def test_valid_fixture_passes_clean(self):
        self.assertEqual(validate_request(fresh()), [])

    def test_schema_counts_match_the_recorded_contract(self):
        # 27 properties, 26 required; scarcity_evidence_ref is the
        # only optional field. If the schema changes, this test says
        # so out loud instead of the coverage silently drifting.
        self.assertEqual(len(SCHEMA["properties"]), 27)
        self.assertEqual(len(REQUIRED), 26)
        self.assertEqual(
            set(SCHEMA["properties"]) - set(REQUIRED),
            {"scarcity_evidence_ref"},
        )

    def test_optional_field_may_be_omitted(self):
        request = fresh()
        del request["scarcity_evidence_ref"]
        self.assertEqual(validate_request(request), [])

    def test_optional_field_may_carry_a_reference(self):
        request = fresh()
        request["scarcity_evidence_ref"] = "TEST-SCARCITY-EVIDENCE"
        self.assertEqual(validate_request(request), [])

    def test_native_ids_may_be_strings(self):
        request = fresh()
        request["native_product_id"] = "TEST-NATIVE-PRODUCT"
        request["native_price_id"] = "TEST-NATIVE-PRICE"
        self.assertEqual(validate_request(request), [])


class TestMissingRequiredFields(unittest.TestCase):
    def test_each_missing_required_field_fails_by_name(self):
        for field in REQUIRED:
            with self.subTest(field=field):
                request = fresh()
                del request[field]
                self.assertEqual(
                    validate_request(request),
                    [f"D1-REQUEST-MISSING-{field.upper()}"],
                )


class TestAdditionalProperties(unittest.TestCase):
    def test_offer_refs_is_rejected(self):
        # offer_refs is the page-request 1.0 field the D1 request
        # schema does not carry; additionalProperties is false.
        request = fresh()
        request["offer_refs"] = ["TEST-U1-OFFER", "TEST-D1-OFFER"]
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-UNEXPECTED-PROPERTY-OFFER_REFS"],
        )

    def test_any_unexpected_property_is_rejected(self):
        request = fresh()
        request["surprise_field"] = "x"
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-UNEXPECTED-PROPERTY-SURPRISE_FIELD"],
        )


class TestConstAndEnum(unittest.TestCase):
    def test_wrong_copy_profile_fails(self):
        request = fresh()
        request["copy_profile"] = "signature-downsell-v2"
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-COPY_PROFILE-CONST-MISMATCH"],
        )

    def test_wrong_assigned_skill_fails(self):
        request = fresh()
        request["assigned_skill"] = 82
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-ASSIGNED_SKILL-CONST-MISMATCH"],
        )

    def test_wrong_page_role_fails(self):
        request = fresh()
        request["page_role"] = "upsell_1"
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-PAGE_ROLE-CONST-MISMATCH"],
        )

    def test_wrong_decline_route_fails(self):
        request = fresh()
        request["decline_route"] = "checkout"
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-DECLINE_ROUTE-CONST-MISMATCH"],
        )

    def test_wrong_schema_version_fails(self):
        request = fresh()
        request["schema_version"] = "2.0"
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-SCHEMA_VERSION-CONST-MISMATCH"],
        )

    def test_difference_kind_outside_enum_fails(self):
        request = fresh()
        request["difference_kind"] = "same_price_smaller_font"
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-DIFFERENCE_KIND-NOT-IN-ENUM"],
        )

    def test_success_route_outside_enum_fails(self):
        request = fresh()
        request["success_route"] = "checkout"
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-SUCCESS_ROUTE-NOT-IN-ENUM"],
        )

    def test_allowed_write_target_outside_enum_fails(self):
        request = fresh()
        request["allowed_write_target"] = "anywhere"
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-ALLOWED_WRITE_TARGET-NOT-IN-ENUM"],
        )


class TestWrongTypes(unittest.TestCase):
    def test_revision_as_string_fails(self):
        request = fresh()
        request["revision"] = "1"
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-REVISION-WRONG-TYPE"],
        )

    def test_revision_as_boolean_fails(self):
        # bool is an int subclass in Python; it is not a JSON integer.
        request = fresh()
        request["revision"] = True
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-REVISION-WRONG-TYPE"],
        )

    def test_revision_as_fraction_fails(self):
        request = fresh()
        request["revision"] = 1.5
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-REVISION-WRONG-TYPE"],
        )

    def test_test_only_as_integer_fails(self):
        request = fresh()
        request["test_only"] = 1
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-TEST_ONLY-WRONG-TYPE"],
        )

    def test_test_only_as_string_fails(self):
        request = fresh()
        request["test_only"] = "true"
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-TEST_ONLY-WRONG-TYPE"],
        )

    def test_string_field_as_integer_fails(self):
        request = fresh()
        request["tenant_id"] = 123
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-TENANT_ID-WRONG-TYPE"],
        )

    def test_nullable_field_as_integer_fails(self):
        request = fresh()
        request["native_product_id"] = 123
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-NATIVE_PRODUCT_ID-WRONG-TYPE"],
        )

    def test_optional_nullable_field_as_integer_fails(self):
        request = fresh()
        request["scarcity_evidence_ref"] = 123
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-SCARCITY_EVIDENCE_REF-WRONG-TYPE"],
        )


class TestStringAndNumberBounds(unittest.TestCase):
    def test_empty_required_string_fails_min_length(self):
        request = fresh()
        request["tenant_id"] = ""
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-TENANT_ID-TOO-SHORT"],
        )

    def test_revision_zero_fails_minimum(self):
        request = fresh()
        request["revision"] = 0
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-REVISION-BELOW-MINIMUM"],
        )

    def test_revision_negative_fails_minimum(self):
        request = fresh()
        request["revision"] = -3
        self.assertEqual(
            validate_request(request),
            ["D1-REQUEST-REVISION-BELOW-MINIMUM"],
        )


class TestMalformedInput(unittest.TestCase):
    def test_non_object_inputs_fail_closed_without_raising(self):
        for bad in (None, [], "request", 42, True):
            with self.subTest(bad=bad):
                self.assertEqual(
                    validate_request(bad),
                    ["D1-REQUEST-MALFORMED-INPUT"],
                )

    def test_empty_object_reports_every_required_field(self):
        codes = validate_request({})
        self.assertEqual(
            set(codes),
            {f"D1-REQUEST-MISSING-{field.upper()}" for field in REQUIRED},
        )


class TestFailClosedDesign(unittest.TestCase):
    def test_validator_source_has_no_third_party_schema_dependency(self):
        source = (ROOT / "validators" / "validate_request.py").read_text()
        self.assertNotIn("import jsonschema", source)
        self.assertNotIn("from jsonschema", source)

    def test_unsupported_schema_keyword_fails_closed(self):
        schema = copy.deepcopy(SCHEMA)
        schema["properties"]["tenant_id"]["pattern"] = "^TEST-"
        self.assertEqual(
            validate_request(fresh(), schema),
            ["D1-REQUEST-UNSUPPORTED-SCHEMA-CONSTRAINT-PATTERN"],
        )

    def test_unsupported_top_level_keyword_fails_closed(self):
        schema = copy.deepcopy(SCHEMA)
        schema["allOf"] = []
        self.assertEqual(
            validate_request(fresh(), schema),
            ["D1-REQUEST-UNSUPPORTED-SCHEMA-CONSTRAINT-ALLOF"],
        )


if __name__ == "__main__":
    unittest.main()
