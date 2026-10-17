"""Matched-pair trial result-extension tests (gap G18 residual).

fixtures/README.md states the page fixture and the result fixture are
NOT a matched pair: the page fixture is a $1 trial with a $27/month
renewal, while valid-downsell-result.json is a $37 one-time offer whose
disclosure audit describes only its own offer. This suite pins the
ADDITIONAL fixture that IS derived for the page fixture's trial:

  fixtures/valid-downsell-result-trial-matched.json

Derivation (fixtures/README.md, final bullet): a result extension for
the page trial requires billing_type trial, due_now_minor 100,
renewal_amount_minor 2700, a renewal date or rule, and
cancellation_terms_present true. Every amount here is DERIVED from the
page fixture (approved_amounts_minor and its public surfaces), never
hard-coded independently, and neither existing fixture is altered.
Run: python3 -m unittest discover -s tests -v
"""
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

PAGE_FILE = json.loads(
    (ROOT / "fixtures" / "valid-downsell-page.json").read_text()
)
PAGE = PAGE_FILE["page"]
ONETIME_FILE = json.loads(
    (ROOT / "fixtures" / "valid-downsell-result.json").read_text()
)
ONETIME = ONETIME_FILE["downsell_result_extension"]
MATCHED_FILE = json.loads(
    (ROOT / "fixtures" / "valid-downsell-result-trial-matched.json").read_text()
)
MATCHED = MATCHED_FILE["downsell_result_extension"]
SCHEMA = json.loads(
    (ROOT / "schemas" / "downsell-result-extension.schema.json").read_text()
)
CANONICAL_U2 = MATCHED["route_result"]["canonical_u2_page_id"]


def page_surface_text(page):
    out = []
    for s in page.get("sections") or []:
        out.append(s.get("heading") or "")
        out.append(s.get("body") or "")
        out.append((s.get("cta") or {}).get("label") or "")
        out.extend(s.get("missed_out_items") or [])
    out.append((page.get("decline_action") or {}).get("label") or "")
    return " ".join(out)


def schema_errors(ext):
    if not HAVE_JSONSCHEMA:
        return []
    validator = jsonschema.Draft202012Validator(SCHEMA)
    return list(validator.iter_errors(ext))


class TestMatchedPairTrialResult(unittest.TestCase):
    def test_matched_fixture_is_test_only_and_additional(self):
        self.assertIs(MATCHED_FILE["test_only"], True)
        self.assertIn("MATCHED", MATCHED_FILE["fixture_kind"])
        # The original pair is untouched and still NOT a pair.
        self.assertEqual(ONETIME["disclosure_audit"]["billing_type"], "one_time")
        self.assertEqual(ONETIME["disclosure_audit"]["due_now_minor"], 3700)
        self.assertEqual(PAGE["approved_amounts_minor"], [100, 2700])

    def test_matched_fixture_passes_semantic_validator(self):
        self.assertEqual(
            vd.validate_result_extension(
                MATCHED, canonical_u2_page_id=CANONICAL_U2
            ),
            [],
        )

    @unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
    def test_matched_fixture_validates_against_schema(self):
        self.assertEqual(schema_errors(MATCHED), [])

    def test_disclosure_derives_from_page_fixture(self):
        approved = PAGE["approved_amounts_minor"]
        audit = MATCHED["disclosure_audit"]
        # README derivation, with amounts taken from the page fixture.
        self.assertEqual(audit["billing_type"], "trial")
        self.assertEqual(audit["due_now_minor"], approved[0])
        self.assertEqual(audit["due_now_minor"], 100)
        self.assertEqual(audit["renewal_amount_minor"], approved[1])
        self.assertEqual(audit["renewal_amount_minor"], 2700)
        self.assertIs(audit["cancellation_terms_present"], True)
        self.assertTrue(audit["renewal_date_or_rule"])

    def test_disclosure_terms_appear_on_page_surfaces(self):
        surfaces = page_surface_text(PAGE)
        lower = surfaces.lower()
        audit = MATCHED["disclosure_audit"]
        # $1 due now / $27 per month / day-31 first renewal are stated
        # on the page itself, so the audit is the page's disclosure.
        self.assertIn("$1", surfaces)
        self.assertIn("$27", surfaces)
        self.assertIn("per month", lower)
        self.assertIn("30 days", lower)
        self.assertIn("day 31", lower)
        self.assertIn("day 31", audit["renewal_date_or_rule"].lower())
        self.assertIn("monthly", audit["renewal_date_or_rule"].lower())
        self.assertIn("cancel anytime", lower)

    def test_actions_match_page_fixture(self):
        page_refs = {
            (s.get("cta") or {}).get("action_ref")
            for s in PAGE["sections"]
        }
        self.assertEqual(page_refs, {"native-d1-action"})
        self.assertEqual(
            [c["section"] for c in MATCHED["cta_map"]], [1, 2, 3, 4, 5, 6, 7, 8]
        )
        self.assertEqual(
            {c["action_ref"] for c in MATCHED["cta_map"]}, page_refs
        )
        self.assertEqual(
            MATCHED["decline_action_ref"],
            PAGE["decline_action"]["action_ref"],
        )
        self.assertNotIn(
            MATCHED["decline_action_ref"],
            {c["action_ref"] for c in MATCHED["cta_map"]},
        )

    def test_matched_disclosure_is_not_the_onetime_audit(self):
        # The dangerous misreading this fixture exists to prevent:
        # reading the $37 one-time audit as the trial's disclosure.
        audit = MATCHED["disclosure_audit"]
        other = ONETIME["disclosure_audit"]
        self.assertNotEqual(audit["billing_type"], other["billing_type"])
        self.assertNotEqual(audit["due_now_minor"], other["due_now_minor"])
        self.assertIsNotNone(audit["renewal_amount_minor"])
        self.assertIsNone(other["renewal_amount_minor"])

    def test_missing_renewal_terms_rejected(self):
        ext = copy.deepcopy(MATCHED)
        ext["disclosure_audit"]["renewal_amount_minor"] = None
        ext["disclosure_audit"]["renewal_date_or_rule"] = None
        ext["disclosure_audit"]["cancellation_terms_present"] = False
        v = vd.validate_result_extension(ext)
        self.assertIn("D1-RESULT-DISCLOSURE-RENEWAL-AMOUNT-MISSING", v)
        self.assertIn("D1-RESULT-DISCLOSURE-RENEWAL-DATE-MISSING", v)
        self.assertIn("D1-RESULT-DISCLOSURE-CANCELLATION-MISSING", v)
        if HAVE_JSONSCHEMA:
            self.assertTrue(schema_errors(ext))

    def test_onetime_amounts_fail_the_derivation(self):
        # Substituting the one-time fixture's $37 into the trial audit
        # must break the page-derived amounts pinned above.
        ext = copy.deepcopy(MATCHED)
        ext["disclosure_audit"]["due_now_minor"] = 3700
        approved = PAGE["approved_amounts_minor"]
        self.assertNotEqual(
            ext["disclosure_audit"]["due_now_minor"], approved[0]
        )


if __name__ == "__main__":
    unittest.main()
