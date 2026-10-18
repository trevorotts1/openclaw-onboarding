import copy
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "schema" / "selection-request.schema.json"

try:
    import jsonschema
except ImportError:  # pragma: no cover - environment without the package
    jsonschema = None

POLICY_ID = "kie-rule-12-band"

BASE_REQUIRED = [
    "schema_version", "tenant_id", "location_id", "launch_id", "revision",
    "request_id", "page_id", "page_role", "assigned_skill", "approval_ref",
    "input_hash", "brand_ref", "brand_hash", "route_graph_ref",
    "route_graph_hash", "offer_refs", "copy_profile", "checkout_targets",
    "allowed_write_target", "test_only",
]


def enriched_request():
    """A complete, valid enriched selection-request at schema 1.0: the
    document the S49 selection wrapper seam produces (the dispatch
    request's fields with copy_profile set to the profile const, plus
    checkout_targets enriched from native mapping rows)."""
    return {
        "schema_version": "1.0",
        "tenant_id": "TEST-TENANT",
        "location_id": "TEST-LOCATION",
        "launch_id": "TEST-LAUNCH",
        "revision": 1,
        "request_id": "TEST-TENANT:TEST-LAUNCH:rev1:product_selection:abc123",
        "page_id": "TEST-SELECTION-PAGE",
        "page_role": "product_selection",
        "assigned_skill": 78,
        "approval_ref": "TEST-APPROVAL",
        "input_hash": "a" * 64,
        "brand_ref": "TEST-BRAND",
        "brand_hash": "b" * 64,
        "route_graph_ref": "TEST-GRAPH",
        "route_graph_hash": "c" * 64,
        "offer_refs": ["MAIN-A", "MAIN-B"],
        "copy_profile": "signature-product-selection",
        "checkout_targets": [
            {"offer_id": "MAIN-A", "price_choice_id": "MAIN-A-USD",
             "native_product_id": "prod_test_a",
             "native_price_id": "price_test_a",
             "target_ref": "mappings:MAIN-A:prod_test_a:price_test_a"},
            {"offer_id": "MAIN-B", "price_choice_id": "MAIN-B-USD",
             "native_product_id": "prod_test_b",
             "native_price_id": "price_test_b",
             "target_ref": "mappings:MAIN-B:prod_test_b:price_test_b"},
        ],
        "allowed_write_target": "local_only",
        "test_only": True,
    }


def all_errors(validator, doc):
    """Every validation error, flattened through allOf context, so an
    assertion can find the error that names the actual defect."""
    flat = []

    def walk(err):
        flat.append(err)
        for sub in err.context:
            walk(sub)

    for err in validator.iter_errors(doc):
        walk(err)
    return flat


def names_policy(errs):
    """An error names the policy field when the field appears in its
    message or at the end of its absolute path (jsonschema puts the
    property name in the path for type and length violations, and in
    the message for required and pair-rule violations)."""
    for e in errs:
        if "prompt_policy_id" in (e.message or ""):
            return True
        path = list(e.absolute_path)
        if path and path[-1] == "prompt_policy_id":
            return True
    return False


@unittest.skipIf(jsonschema is None,
                 "SKIP-NAMED: jsonschema package not installed; the "
                 "profile cases in this module cannot run here")
class SelectionRequestProfileTests(unittest.TestCase):
    """Adoption map section 1.2: the selection-request profile in
    dual-accept form. What is proven:

    1. The four pair cases against the revised profile: a 1.0 request
       without prompt_policy_id validates; a 1.1 request carrying it
       validates; a 1.0 request carrying it is refused; a 1.1 request
       without it is refused.
    2. An enriched selection-request built from a 1.1 dispatch request
       (the wrapper seam's enrichment steps applied to the data: copy,
       profile copy_profile, checkout_targets added, citation kept)
       validates against the revised profile. This is the acceptance
       shape the map's section 1.2 readiness evidence names.
    3. Malformed 1.1 shapes fail with errors naming the defect: empty
       or null or non-string id, unknown schema_version, a selector
       shaped extra key refused by additionalProperties.
    4. The rest of the profile did not move: the required list is
       byte-identical in membership, additionalProperties stays false,
       the role, skill, and copy_profile consts stand, and
       checkout_targets stays required at 1.1.
    5. A deliberate non-case, pinned so it is never misread: a
       non-empty id string that names no registry entry still passes
       THIS profile. The schema keeps the id an open string by Q12
       design (the registry is the minting authority and can gain
       entries); refusing an unknown id is a registry-layer act at
       dispatch and aggregation, not a profile act. See the candidate
       record PPY2-ADOPTION-12 for the layer analysis.
    """

    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(PROFILE.read_text())
        cls.validator = jsonschema.Draft202012Validator(cls.schema)

    def errors(self, doc):
        return all_errors(self.validator, doc)

    def assertValid(self, doc):
        errs = self.errors(doc)
        self.assertEqual(errs, [],
                         f"expected valid, got: {[e.message for e in errs]}")

    def assertInvalid(self, doc, must_name_policy=False):
        errs = self.errors(doc)
        self.assertNotEqual(errs, [], "expected the document to be refused")
        if must_name_policy:
            self.assertTrue(
                names_policy(errs),
                f"no error names prompt_policy_id: "
                f"{[e.message for e in errs]}")
        return errs

    # The four pair cases (map section 1.2 readiness evidence).
    def test_10_without_field_valid(self):
        self.assertValid(enriched_request())

    def test_11_with_field_valid(self):
        doc = enriched_request()
        doc["schema_version"] = "1.1"
        doc["prompt_policy_id"] = POLICY_ID
        self.assertValid(doc)

    def test_10_with_field_refused(self):
        doc = enriched_request()
        doc["prompt_policy_id"] = POLICY_ID
        self.assertInvalid(doc, must_name_policy=True)

    def test_11_without_field_refused(self):
        doc = enriched_request()
        doc["schema_version"] = "1.1"
        self.assertInvalid(doc, must_name_policy=True)

    # The enriched-from-dispatch acceptance shape.
    def test_enriched_from_11_dispatch_request_valid(self):
        dispatch_request = enriched_request()
        dispatch_request["schema_version"] = "1.1"
        dispatch_request["prompt_policy_id"] = POLICY_ID
        dispatch_request["copy_profile"] = "signature-launch-page-request"
        del dispatch_request["checkout_targets"]
        # The seam's enrichment steps, applied to the data exactly as
        # the wrapper performs them: copy the request, set the profile
        # copy_profile, add checkout_targets from mapping rows. The
        # citation rides the copy; dropping it would fail case 4 above.
        enriched = copy.deepcopy(dispatch_request)
        enriched["copy_profile"] = "signature-product-selection"
        enriched["checkout_targets"] = enriched_request()["checkout_targets"]
        self.assertEqual(enriched["prompt_policy_id"], POLICY_ID)
        self.assertValid(enriched)

    # Malformed shapes.
    def test_empty_string_id_refused(self):
        doc = enriched_request()
        doc["schema_version"] = "1.1"
        doc["prompt_policy_id"] = ""
        self.assertInvalid(doc, must_name_policy=True)

    def test_null_id_refused(self):
        doc = enriched_request()
        doc["schema_version"] = "1.1"
        doc["prompt_policy_id"] = None
        self.assertInvalid(doc, must_name_policy=True)

    def test_nonstring_id_refused(self):
        for bad in (12, ["kie-rule-12-band"], {"policy_id": POLICY_ID}):
            doc = enriched_request()
            doc["schema_version"] = "1.1"
            doc["prompt_policy_id"] = bad
            with self.subTest(bad=bad):
                self.assertInvalid(doc, must_name_policy=True)

    def test_unknown_schema_version_refused(self):
        for bad in ("1.2", "2.0", 1.1):
            doc = enriched_request()
            doc["schema_version"] = bad
            with self.subTest(bad=bad):
                self.assertInvalid(doc)

    def test_selector_shaped_extra_key_refused(self):
        doc = enriched_request()
        doc["schema_version"] = "1.1"
        doc["prompt_policy_id"] = POLICY_ID
        doc["prompt_policy_selection"] = POLICY_ID
        errs = self.assertInvalid(doc)
        self.assertTrue(any("prompt_policy_selection" in (e.message or "")
                            for e in errs))

    def test_11_still_requires_checkout_targets(self):
        doc = enriched_request()
        doc["schema_version"] = "1.1"
        doc["prompt_policy_id"] = POLICY_ID
        del doc["checkout_targets"]
        errs = self.assertInvalid(doc)
        self.assertTrue(any("checkout_targets" in (e.message or "")
                            for e in errs))

    # The pinned non-case (item 5 of the class docstring).
    def test_unknown_id_string_passes_the_profile(self):
        doc = enriched_request()
        doc["schema_version"] = "1.1"
        doc["prompt_policy_id"] = "no-such-policy-registered"
        self.assertValid(doc)

    # Surgical-scope invariants on the schema document itself.
    def test_profile_invariants_unchanged(self):
        self.assertIs(self.schema["additionalProperties"], False)
        self.assertEqual(sorted(self.schema["required"]),
                         sorted(BASE_REQUIRED))
        self.assertNotIn("prompt_policy_id", self.schema["required"])
        props = self.schema["properties"]
        self.assertEqual(props["page_role"], {"const": "product_selection"})
        self.assertEqual(props["assigned_skill"], {"const": 78})
        self.assertEqual(props["copy_profile"],
                         {"const": "signature-product-selection"})
        self.assertEqual(props["schema_version"], {"enum": ["1.0", "1.1"]})
        field = props["prompt_policy_id"]
        self.assertEqual(field["type"], "string")
        self.assertEqual(field["minLength"], 1)


if __name__ == "__main__":
    unittest.main()
