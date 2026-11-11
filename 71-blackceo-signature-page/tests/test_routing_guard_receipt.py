#!/usr/bin/env python3
"""Harmony issue 42: the landing-page routing guard no longer accepts an identifier-less receipt.

Before: scripts/page_result.py accepted any non-empty receipt, a bare string included, "on presence
alone" (receipt_binding "no_identity_fields"), so a hand-written string authorized routing onward.
Now a verified-submission record routes only when its receipt carries `submission_id` or
`contact_id` (a non-empty string) and `source` equal to `native_form` or `api`; anything else is
refused with the named failure AF-71-ROUTE-RECEIPT, recorded in the handoff's routing basis and in
the page result's blockers. The run-identity contradiction rule is unchanged.
"""
import ast
import copy
import inspect
import json
import string
import sys
import textwrap
import uuid
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
import page_result  # noqa: E402
import test_page_result as fixture  # noqa: E402  the run builder the emission tests share

AF = "AF-71-ROUTE-RECEIPT"


def submission(receipt):
    return {"event": "interest_verified", "state": "verified", "receipt": receipt,
            "recorded_at": "2026-10-15T00:00:00+00:00"}


class RoutingGuardReceipt(unittest.TestCase):
    def emit(self, receipt):
        with tempfile.TemporaryDirectory() as tmp:
            run = fixture.make_run(tmp, submission=submission(receipt))
            proc = fixture.run_writer(run)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            result = fixture.assert_valid_result(run)
            return fixture.load(run, "page-handoff.json"), result

    def assertRefused(self, receipt, binding="unidentified"):
        handoff, result = self.emit(receipt)
        self.assertIs(handoff["routing"]["authorized"], False, handoff["routing"])
        self.assertIn(AF, handoff["routing"]["basis"])
        self.assertEqual(handoff["submission"]["receipt_binding"], binding, handoff["submission"])
        self.assertTrue(any(AF in b for b in result["blockers"]), result["blockers"])

    def assertAuthorized(self, receipt, binding):
        handoff, result = self.emit(receipt)
        self.assertIs(handoff["routing"]["authorized"], True, handoff["routing"])
        self.assertEqual(handoff["submission"]["receipt_binding"], binding, handoff["submission"])
        self.assertFalse(any(AF in b for b in result["blockers"]), result["blockers"])

    # refused
    def test_a_bare_string_receipt_is_refused(self):
        self.assertRefused("API-RECEIPT-TEST-1")

    def test_a_dict_with_no_submission_or_contact_id_is_refused(self):
        self.assertRefused({"form_id": "TEST-FORM-1", "source": "native_form"})

    def test_a_dict_with_an_id_and_no_source_is_refused(self):
        self.assertRefused({"contact_id": "TEST-CONTACT-1", "form_id": "TEST-FORM-1"})

    def test_a_source_outside_native_form_and_api_is_refused(self):
        self.assertRefused({"contact_id": "TEST-CONTACT-1", "source": "test fixture (TEST ONLY)"})
        self.assertRefused({"submission_id": "S-1", "source": "typed by hand"})

    def test_the_receipt_source_set_is_exactly_native_form_and_api(self):
        # Pins the closed set itself: widening it (say with "manual") must fail here,
        # not slip through because no listed bad source happens to be the added one.
        self.assertEqual(set(page_result.RECEIPT_SOURCES), {"native_form", "api"})
        self.assertEqual(len(page_result.RECEIPT_SOURCES), 2)
        request = {"tenant_id": "T", "launch_id": "L"}
        for source in ("manual", "test", "import", "webhook", "csv", "Api", "API", "native form",
                       "native_form ", "", None, 0, ["api"]):
            binding, problems = page_result.receipt_binding(
                request, {"submission_id": "SUB-1", "source": source})
            self.assertEqual(binding, "unidentified", source)
            self.assertTrue(any(AF in p for p in problems), (source, problems))
        for source in ("native_form", "api"):
            self.assertEqual(page_result.receipt_binding(
                request, {"submission_id": "SUB-1", "source": source}), ("identified", []))

    def test_receipt_binding_refuses_arbitrary_unlisted_sources_and_hard_codes_none(self):
        # Behaviour: a source the closed list does not name is refused whatever it is, not only the
        # named bad ones; 200 random strings plus fixed oddities, with either id field.
        request = {"tenant_id": "T", "launch_id": "L"}
        sources = [str(uuid.uuid4()) for _ in range(200)] + ["zzz", "ZZZ", "n/a", "manual2", " api", "api\n"]
        # every first letter/digit, so a prefix or startswith widening cannot hide behind a hex uuid
        sources += [c + str(uuid.uuid4()) for c in string.ascii_letters + string.digits]
        sources += [c * 3 for c in string.ascii_letters]
        for source in sources:
            for field in ("submission_id", "contact_id"):
                binding, problems = page_result.receipt_binding(request, {field: "ID-1", "source": source})
                self.assertEqual(binding, "unidentified", source)
                self.assertTrue(any(AF in p for p in problems), (source, problems))
        # Structure: receipt_binding compares no string literal against the source (or anything
        # else); a hard-coded extra accepted source (`source != "x"`, `in (*LIST, "x")`) would put
        # a str constant inside a Compare node.
        tree = ast.parse(textwrap.dedent(inspect.getsource(page_result.receipt_binding)))
        # (a key passed to a call, like receipt.get("source"), is a lookup, not a compared value)
        literals = []
        for cmp in (n for n in ast.walk(tree) if isinstance(n, ast.Compare)):
            keys = {id(a) for call in ast.walk(cmp) if isinstance(call, ast.Call) for a in call.args}
            literals += [c.value for c in ast.walk(cmp) if isinstance(c, ast.Constant)
                         and isinstance(c.value, str) and id(c) not in keys]
        self.assertEqual(literals, [], "a string literal is compared inside receipt_binding")
        self.assertTrue(any(isinstance(n, ast.Compare) and any(isinstance(o, ast.NotIn) for o in n.ops)
                            for n in ast.walk(tree)), "the source check must be a `not in RECEIPT_SOURCES`")

    def test_a_submission_with_no_receipt_records_the_binding_no_receipt(self):
        # No receipt means nothing was checked: the label stays "no_receipt" (never "identified" or
        # "unidentified"), and routing is not authorized because the submission is not verified.
        for receipt in (None, "", {}):
            handoff, _ = self.emit(receipt)
            self.assertEqual(handoff["submission"]["receipt_binding"], "no_receipt", receipt)
            self.assertIs(handoff["routing"]["authorized"], False, receipt)

    def test_the_receipt_id_field_set_is_exactly_submission_id_and_contact_id(self):
        # Pins the closed set itself: widening it (say with "request_id", which is also a run-identity
        # field) must fail here, not slip through because no listed field happens to be the added one.
        self.assertEqual(set(page_result.RECEIPT_ID_FIELDS), {"submission_id", "contact_id"})
        self.assertEqual(len(page_result.RECEIPT_ID_FIELDS), 2)
        request = {f: f"v-{f}" for f in page_result.RECEIPT_IDENTITY_FIELDS}
        for field in (*page_result.RECEIPT_IDENTITY_FIELDS, "id", "form_id", "receipt_id"):
            receipt = {field: request.get(field, "X"), "source": "api"}
            binding, problems = page_result.receipt_binding(request, receipt)
            self.assertEqual(binding, "unidentified", field)
            self.assertTrue(any(AF in p for p in problems), (field, problems))
        for field in ("submission_id", "contact_id"):
            self.assertEqual(page_result.receipt_binding(
                request, {field: "ID-1", "source": "api"}), ("identified", []))

    def test_an_empty_or_non_string_id_is_refused(self):
        self.assertRefused({"submission_id": "", "source": "api"})
        self.assertRefused({"contact_id": "   ", "source": "native_form"})
        self.assertRefused({"submission_id": 42, "source": "api"})

    def test_run_identity_fields_alone_are_not_a_submission_identifier(self):
        self.assertRefused({"tenant_id": "TEST-TENANT", "launch_id": "TEST-LAUNCH", "source": "api"})

    # accepted
    def test_a_submission_id_with_source_api_routes(self):
        self.assertAuthorized({"submission_id": "SUB-1", "source": "api"}, "identified")

    def test_a_contact_id_with_source_native_form_routes(self):
        self.assertAuthorized({"contact_id": "TEST-CONTACT-1", "source": "native_form"}, "identified")

    def test_a_matching_run_identity_is_still_bound(self):
        self.assertAuthorized({"contact_id": "TEST-CONTACT-9", "source": "native_form",
                               "tenant_id": "TEST-TENANT", "launch_id": "TEST-LAUNCH",
                               "request_id": "TEST-REQUEST-1"}, "bound")

    def test_another_runs_receipt_is_still_contradicted(self):
        handoff, result = self.emit({"contact_id": "OTHER-1", "source": "api", "tenant_id": "OTHER-TENANT"})
        self.assertIs(handoff["routing"]["authorized"], False)
        self.assertEqual(handoff["submission"]["receipt_binding"], "contradicted")
        self.assertTrue(any("not bound to this run" in b for b in result["blockers"]), result["blockers"])

    def test_the_shared_fixture_record_routes_so_the_other_emission_tests_exercise_a_real_receipt(self):
        receipt = fixture.VERIFIED_SUBMISSION["receipt"]
        binding, problems = page_result.receipt_binding({"tenant_id": "TEST-TENANT"}, receipt)
        self.assertEqual((binding, problems), ("identified", []))

    def test_receipt_binding_unit_contract(self):
        request = {"tenant_id": "T", "launch_id": "L"}
        self.assertEqual(page_result.receipt_binding(request, "x")[0], "unidentified")
        self.assertEqual(page_result.receipt_binding(request, None)[0], "unidentified")
        self.assertEqual(page_result.receipt_binding(request, {"contact_id": "c", "source": "api"})[0], "identified")
        self.assertEqual(page_result.receipt_binding(request, {"contact_id": "c", "source": "api",
                                                              "tenant_id": "T"})[0], "bound")
        self.assertEqual(page_result.receipt_binding(request, {"contact_id": "c", "source": "api",
                                                              "tenant_id": "Z"})[0], "contradicted")
        _, problems = page_result.receipt_binding(request, "x")
        self.assertTrue(all(AF in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
