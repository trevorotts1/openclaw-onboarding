"""Page-document schema tests (PC-3 from the CR-S49-005 reply lane).

schemas/downsell-page.schema.json states the structural contract of
the D1 page document (the page object fixtures/valid-downsell-page.json
carries under its "page" member). Until now the page was contracted
only by the prose checks in validators/validate_downsell.py
(validate_copy); no schema stated its structure: exactly 8 sections in
the derived role order, one purchase CTA per section bound to the
single native D1 action, a separate decline action, the canonical
section 8 heading, and exactly 7 missed-out items in section 8.

Approach: the primary path validates with a real Draft 2020-12
validator (this room's environment ships the jsonschema library). If
jsonschema is ever unavailable, the tests do NOT skip: schema_errors
falls back to _stdlib_errors, a stdlib enforcement of the same
structural contract the schema file states, so the page structure is
checked in every environment and never silently skipped. (The older
request-schema suite skips without jsonschema; this suite deliberately
does not copy that pattern.)
Run: python3 -m unittest discover -s tests -v
"""
import copy
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

try:
    import jsonschema
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

PAGE_SCHEMA = json.loads(
    (ROOT / "schemas" / "downsell-page.schema.json").read_text()
)
PAGE_FILE = json.loads(
    (ROOT / "fixtures" / "valid-downsell-page.json").read_text()
)
PAGE = PAGE_FILE["page"]

SECTION_ROLES = [
    "big_bold_claim",
    "big_bold_pain_1",
    "big_bold_pain_2",
    "big_bold_pain_3",
    "big_bold_why",
    "big_bold_who",
    "big_bold_what",
    "when_time_runs_out",
]
PURCHASE_ACTION_REF = "native-d1-action"
DECLINE_ACTION_REF = "native-decline-d1"
CANONICAL_HEADING = "When Time Runs Out"


def _check_action(errs, action, where, expected_ref):
    if not isinstance(action, dict):
        errs.append(f"{where} is not an object")
        return
    if set(action) != {"action_ref", "label"}:
        errs.append(f"{where} fields are not exactly action_ref/label")
    if action.get("action_ref") != expected_ref:
        errs.append(f"{where}.action_ref is not {expected_ref}")
    label = action.get("label")
    if not isinstance(label, str) or len(label) < 1:
        errs.append(f"{where}.label is missing or empty")


def _stdlib_errors(page):
    """Stdlib enforcement of the same structural contract the schema
    states. Used only when jsonschema is unavailable, so the contract
    is enforced in every environment instead of silently skipped."""
    errs = []
    if not isinstance(page, dict):
        return ["page document is not an object"]
    allowed = {"approved_amounts_minor", "decline_action",
               "scarcity_evidence_ref", "sections"}
    for key in page:
        if key not in allowed:
            errs.append(f"unexpected page field: {key}")
    for key in ("approved_amounts_minor", "decline_action", "sections"):
        if key not in page:
            errs.append(f"missing required page field: {key}")
    amounts = page.get("approved_amounts_minor")
    if amounts is not None:
        if not isinstance(amounts, list) or not amounts:
            errs.append("approved_amounts_minor must be a non-empty array")
        elif any(isinstance(a, bool) or not isinstance(a, int) or a < 0
                 for a in amounts):
            errs.append("approved_amounts_minor entries must be "
                        "integers >= 0")
    if "scarcity_evidence_ref" in page:
        ref = page["scarcity_evidence_ref"]
        if ref is not None and not isinstance(ref, str):
            errs.append("scarcity_evidence_ref must be a string or null")
    if page.get("decline_action") is not None:
        _check_action(errs, page["decline_action"], "decline_action",
                      DECLINE_ACTION_REF)
    sections = page.get("sections")
    if sections is not None:
        if not isinstance(sections, list) or len(sections) != 8:
            errs.append("sections must be an array of exactly 8")
        else:
            for i, section in enumerate(sections):
                _check_section(errs, section, i)
    return errs


def _check_section(errs, section, i):
    where = f"sections[{i}]"
    closing = i == 7
    if not isinstance(section, dict):
        errs.append(f"{where} is not an object")
        return
    allowed = {"body", "cta", "heading", "role"}
    if closing:
        allowed.add("missed_out_items")
    for key in section:
        if key not in allowed:
            errs.append(f"{where} has unexpected field: {key}")
    for key in allowed:
        if key not in section:
            errs.append(f"{where} is missing required field: {key}")
    if section.get("role") != SECTION_ROLES[i]:
        errs.append(f"{where}.role is not {SECTION_ROLES[i]}")
    heading = section.get("heading")
    if not isinstance(heading, str) or len(heading) < 1:
        errs.append(f"{where}.heading is missing or empty")
    elif closing and heading != CANONICAL_HEADING:
        errs.append(f"{where}.heading is not the canonical heading")
    body = section.get("body")
    if not isinstance(body, str) or len(body) < 1:
        errs.append(f"{where}.body is missing or empty")
    if section.get("cta") is not None:
        _check_action(errs, section["cta"], f"{where}.cta",
                      PURCHASE_ACTION_REF)
    if closing:
        items = section.get("missed_out_items")
        if items is not None:
            if not isinstance(items, list) or len(items) != 7:
                errs.append(f"{where}.missed_out_items must be "
                            "exactly 7 items")
            elif any(not isinstance(x, str) or len(x) < 1
                     for x in items):
                errs.append(f"{where}.missed_out_items entries must "
                            "be non-empty strings")


def schema_errors(instance):
    if HAVE_JSONSCHEMA:
        validator = jsonschema.Draft202012Validator(PAGE_SCHEMA)
        return list(validator.iter_errors(instance))
    return _stdlib_errors(instance)


def mutated(change):
    page = copy.deepcopy(PAGE)
    change(page)
    return page


class TestPageSchema(unittest.TestCase):
    def test_page_schema_itself_is_valid(self):
        if HAVE_JSONSCHEMA:
            jsonschema.Draft202012Validator.check_schema(PAGE_SCHEMA)
        else:
            # No validator library: the schema must still declare the
            # Draft 2020-12 dialect this suite's fallback mirrors.
            self.assertEqual(
                PAGE_SCHEMA["$schema"],
                "https://json-schema.org/draft/2020-12/schema")

    def test_valid_page_fixture_validates_with_zero_errors(self):
        self.assertEqual(schema_errors(PAGE), [])

    def test_page_fixture_carries_contract_identity(self):
        self.assertEqual([s["role"] for s in PAGE["sections"]],
                         SECTION_ROLES)
        self.assertEqual(
            {s["cta"]["action_ref"] for s in PAGE["sections"]},
            {PURCHASE_ACTION_REF})
        self.assertEqual(PAGE["decline_action"]["action_ref"],
                         DECLINE_ACTION_REF)
        self.assertEqual(PAGE["sections"][7]["heading"],
                         CANONICAL_HEADING)
        self.assertEqual(
            len(PAGE["sections"][7]["missed_out_items"]), 7)

    def test_fixture_envelope_is_not_a_page_instance(self):
        self.assertTrue(
            schema_errors(PAGE_FILE),
            "the fixture envelope must not validate as a page document",
        )


class TestPageSchemaMutations(unittest.TestCase):
    """Each mutation breaks one structural rule the schema states and
    must produce errors under either validation engine."""

    def test_missing_section_fails(self):
        page = mutated(lambda p: p["sections"].pop(3))
        self.assertTrue(schema_errors(page))

    def test_sections_out_of_order_fail(self):
        def swap(p):
            p["sections"][1], p["sections"][2] = \
                p["sections"][2], p["sections"][1]
        self.assertTrue(schema_errors(mutated(swap)))

    def test_section_without_cta_fails(self):
        page = mutated(lambda p: p["sections"][0].pop("cta"))
        self.assertTrue(schema_errors(page))

    def test_cta_on_wrong_action_ref_fails(self):
        page = mutated(
            lambda p: p["sections"][2]["cta"].update(
                action_ref="native-other-action"))
        self.assertTrue(schema_errors(page))

    def test_decline_action_absent_fails(self):
        page = mutated(lambda p: p.pop("decline_action"))
        self.assertTrue(schema_errors(page))

    def test_section_8_prose_heading_fails(self):
        # The corpus prose form is a normalization event, never the
        # canonical emitted heading the schema states.
        page = mutated(
            lambda p: p["sections"][7].update(
                heading="When Times Run Out"))
        self.assertTrue(schema_errors(page))

    def test_missed_out_items_not_seven_fail(self):
        page = mutated(
            lambda p: p["sections"][7]["missed_out_items"].pop())
        self.assertTrue(schema_errors(page))


if __name__ == "__main__":
    unittest.main()
