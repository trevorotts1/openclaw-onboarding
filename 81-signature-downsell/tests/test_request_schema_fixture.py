"""Request-schema fixture tests (gap G17 from lane review 7).

schemas/downsell-request.schema.json previously had no fixture and no
test. This suite proves:
- fixtures/valid-downsell-request.json is a genuine instance of that
  schema and validates with zero errors;
- fixtures/valid-downsell-request-policy.json is the stored 1.1
  instance (the adoption map 1.5 dual-accept shape) and also
  validates with zero errors; the pair rule binding version and
  field is the stdlib validator's, not the schema's, by design;
- the request fixture carries the route-law identity fields the schema
  pins (role downsell_1, assigned_skill 81, decline_route thank_you,
  success_route upsell_2);
- the two pre-existing fixtures are NOT request instances: the page
  fixture and the result fixture belong to other contract objects, and
  validating either file, or either inner contract object, against the
  request schema produces errors.
Run: python3 -m unittest discover -s tests -v
"""
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

try:
    import jsonschema
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

REQUEST_SCHEMA = json.loads(
    (ROOT / "schemas" / "downsell-request.schema.json").read_text()
)
REQUEST = json.loads(
    (ROOT / "fixtures" / "valid-downsell-request.json").read_text()
)
REQUEST_POLICY = json.loads(
    (ROOT / "fixtures" / "valid-downsell-request-policy.json").read_text()
)
PAGE_FILE = json.loads(
    (ROOT / "fixtures" / "valid-downsell-page.json").read_text()
)
RESULT_FILE = json.loads(
    (ROOT / "fixtures" / "valid-downsell-result.json").read_text()
)


def schema_errors(instance):
    if not HAVE_JSONSCHEMA:
        return []
    validator = jsonschema.Draft202012Validator(REQUEST_SCHEMA)
    return list(validator.iter_errors(instance))


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
class TestRequestSchemaFixture(unittest.TestCase):
    def test_request_schema_itself_is_valid(self):
        jsonschema.Draft202012Validator.check_schema(REQUEST_SCHEMA)

    def test_valid_request_fixture_validates_with_zero_errors(self):
        self.assertEqual(schema_errors(REQUEST), [])

    def test_valid_policy_fixture_validates_with_zero_errors(self):
        # The adoption map 1.5 dual-accept shape: schema_version
        # "1.1" carrying the prompt-policy citation.
        self.assertEqual(schema_errors(REQUEST_POLICY), [])

    def test_policy_fixture_carries_the_pair(self):
        self.assertEqual(REQUEST_POLICY["schema_version"], "1.1")
        self.assertEqual(REQUEST_POLICY["prompt_policy_id"],
                         "kie-rule-12-band")

    def test_schema_alone_does_not_bind_the_pair(self):
        # By design (adoption map 1.5): the schema declares the
        # version enum and the optional field; the rule binding
        # them stands in validators/validate_request.py, because
        # the packaged schema's stdlib evaluator fails closed on
        # the conditional keywords an in-schema pair rule needs.
        # These two shapes therefore pass the raw schema and are
        # refused by validate_request (test_validate_request.py
        # pins those refusals). This test pins the allocation so
        # the schema cannot quietly grow a second, divergent pair
        # rule.
        one_one_without = dict(REQUEST)
        one_one_without["schema_version"] = "1.1"
        self.assertEqual(schema_errors(one_one_without), [])
        one_zero_with = dict(REQUEST)
        one_zero_with["prompt_policy_id"] = "kie-rule-12-band"
        self.assertEqual(schema_errors(one_zero_with), [])

    def test_request_fixture_carries_route_law_identity(self):
        self.assertEqual(REQUEST["page_role"], "downsell_1")
        self.assertEqual(REQUEST["assigned_skill"], 81)
        self.assertEqual(REQUEST["decline_route"], "thank_you")
        self.assertEqual(REQUEST["success_route"], "upsell_2")
        self.assertEqual(REQUEST["copy_profile"], "signature-downsell-v1")
        self.assertIs(REQUEST["test_only"], True)

    def test_page_fixture_file_is_not_a_request_instance(self):
        self.assertTrue(
            schema_errors(PAGE_FILE),
            "page fixture file must not validate as a downsell request",
        )

    def test_page_fixture_inner_page_is_not_a_request_instance(self):
        self.assertTrue(
            schema_errors(PAGE_FILE["page"]),
            "inner page object must not validate as a downsell request",
        )

    def test_result_fixture_file_is_not_a_request_instance(self):
        self.assertTrue(
            schema_errors(RESULT_FILE),
            "result fixture file must not validate as a downsell request",
        )

    def test_result_fixture_inner_extension_is_not_a_request_instance(self):
        self.assertTrue(
            schema_errors(RESULT_FILE["downsell_result_extension"]),
            "inner result extension must not validate as a downsell request",
        )


if __name__ == "__main__":
    unittest.main()
