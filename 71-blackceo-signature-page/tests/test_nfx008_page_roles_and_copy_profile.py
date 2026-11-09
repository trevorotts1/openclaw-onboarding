#!/usr/bin/env python3
"""NFX-008: FIX-07 (Skill 71 page roles) + FIX-14 (copy-profile and page-role key spelling).

FIX-07: the page-role vocabulary is the closed enum in
49-signature-funnel/schema/route-graph.schema.json, read at runtime and at test time; every
role the schema permits registers and validates, and a role it does not permit raises
PageRoleUnknown naming the token.

FIX-14: ONE normaliser (copy_forms.slug) serves both spelling boundaries; the registry key
sets are unchanged; a miss raises a named error quoting the value and nothing defaults.

No provider is called and no file outside references/ and 49-signature-funnel/schema/ is read.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parent
SCRIPTS = ROOT / "scripts"
SCHEMA = REPO / "49-signature-funnel" / "schema" / "route-graph.schema.json"
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


copy_forms = load("copy_forms")
page_role = load("page_role")
launch_context = load("launch_context")

# Document 3 FIX-07 names these seven, in this order. The test does not trust this tuple:
# test_the_schema_enumerates_exactly_the_seven_roles compares it with the schema read at run
# time, so an eighth role added to the schema fails until this test is updated with it.
DOCUMENTED_ROLES = ("landing", "product_selection", "checkout", "upsell_1", "downsell_1",
                    "upsell_2", "thank_you")


def schema_roles():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return tuple(schema["properties"]["nodes"]["items"]["properties"]["role"]["enum"])


class PageRoleTests(unittest.TestCase):
    def test_the_schema_enumerates_exactly_the_seven_roles(self):
        self.assertEqual(schema_roles(), DOCUMENTED_ROLES)
        # the runtime vocabulary is that same schema read, not a list held in page_role.py
        self.assertEqual(page_role.schema_page_roles(), schema_roles())

    def test_every_schema_role_registers(self):
        roles = schema_roles()  # read at test time; never a hand-maintained list
        self.assertEqual(len(roles), 7)
        self.assertEqual(page_role.registered_page_roles(), roles)

    def test_role_spellings_normalise_to_the_same_role(self):
        for given, canonical in (("product_selection", "product_selection"),
                                 ("product-selection", "product_selection"),
                                 ("Product Selection", "product_selection"),
                                 ("thank-you", "thank_you"),
                                 ("THANK_YOU", "thank_you")):
            with self.subTest(given=given):
                self.assertEqual(page_role.validate_page_role(given), canonical)

    def test_the_role_boundary_resolves_both_selections_to_one_form(self):
        self.assertEqual(page_role.role_form("product_selection"), "product-selection")
        self.assertEqual(page_role.role_form("product-selection"), "product-selection")
        self.assertEqual(page_role.role_form("thank_you"), "thank-you")
        self.assertIsNone(page_role.role_form("landing"))


def _role_case(role):
    def case(self):
        self.assertEqual(page_role.validate_page_role(role), role)
        self.assertEqual(page_role.register_page_role(role), role)
    case.__name__ = f"test_role_{role}_registers_and_validates"
    case.__doc__ = f"FIX-07: the schema role {role} registers and validates"
    return case


class SchemaRoleMatrix(unittest.TestCase):
    """Exactly eight cases: one per role read from the route-graph schema at test time, plus
    the literal `not_a_role` negative (Document 3 FIX-07 steps 4-5)."""

    def test_role_not_a_role_is_rejected_naming_the_token(self):
        with self.assertRaises(page_role.PageRoleUnknown) as ctx:
            page_role.register_page_role("not_a_role")
        self.assertIn(repr("not_a_role"), str(ctx.exception))


for _role in schema_roles():  # the schema, not a hand-maintained list
    setattr(SchemaRoleMatrix, f"test_role_{_role}_registers_and_validates", _role_case(_role))


class CopyProfileTests(unittest.TestCase):
    def test_both_spellings_resolve_to_the_same_non_empty_form(self):
        for under, hyphen, form in (("long_form", "long-form", "long-form"),
                                    ("product_selection", "product-selection", "product-selection")):
            with self.subTest(pair=(under, hyphen)):
                self.assertEqual(copy_forms.resolve_profile(under), form)
                self.assertEqual(copy_forms.resolve_profile(hyphen), form)
                self.assertTrue(form)

    def test_the_single_normaliser_serves_both_boundaries(self):
        self.assertEqual(copy_forms.slug("long_form"), copy_forms.slug("long-form"))
        self.assertEqual(copy_forms.slug("product_selection"), copy_forms.slug("product-selection"))
        self.assertEqual(copy_forms.norm("product-selection-v1"), "product-selection")

    def test_unrecognised_values_raise_a_named_error_quoting_the_value(self):
        with self.assertRaises(copy_forms.UnknownCopyProfile) as profile_ctx:
            copy_forms.resolve_profile("not_a_profile")
        self.assertIn(repr("not_a_profile"), str(profile_ctx.exception))
        with self.assertRaises(page_role.PageRoleUnknown) as role_ctx:
            page_role.role_form("not_a_role")
        self.assertIn(repr("not_a_role"), str(role_ctx.exception))

    def test_no_path_assigns_a_default_version(self):
        self.assertIsNone(copy_forms.norm("not_a_profile"))
        with self.assertRaises(copy_forms.UnknownCopyProfile):
            copy_forms.resolve_profile("not_a_profile")

    def test_registry_key_sets_are_unchanged(self):
        self.assertEqual(copy_forms.FORMS,
                         ("standard", "long-form", "product-selection", "thank-you",
                          "upsell", "checkout"))
        self.assertNotIn("long_form", copy_forms.FORMS)
        self.assertNotIn("product_selection", copy_forms.SPEC_FILES)
        self.assertEqual(page_role.copy_versions(),
                         ("standard", "long-form", "product-selection", "checkout",
                          "thank-you", "upsell"))

    def test_launch_context_has_one_registry_and_no_fallback(self):
        # The pre-fix module held a second table (COPY_PROFILE_VERSION) whose exact-key lookup
        # returned None for "long_form". FIX-14 removes it: the one registry resolves both.
        self.assertFalse(hasattr(launch_context, "COPY_PROFILE_VERSION"))
        self.assertEqual(copy_forms.resolve_profile("long_form"),
                         copy_forms.resolve_profile("long-form"))


if __name__ == "__main__":
    unittest.main()
