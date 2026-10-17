"""Request-schema fixture tests (gap G17 from lane review 7).

schemas/downsell-request.schema.json previously had no fixture and no
test. This suite proves:
- fixtures/valid-downsell-request.json is a genuine instance of that
  schema and validates with zero errors;
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
