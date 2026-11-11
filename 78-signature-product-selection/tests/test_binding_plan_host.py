"""Issue 31 (WP-17b): validate_selection_binding.py has a host.

emit_binding_plan.emit_plan (which Skill 83 checkout_instances.build calls for
every per-offer checkout set) runs the checkout-time binding validator over each
mapping it emits, so a plan the validator would refuse is never returned.
"""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

import emit_binding_plan  # noqa: E402
from build_selection_plan import SELF_TEST_LAUNCH  # noqa: E402
from emit_binding_plan import SELF_TEST_TARGETS, emit_plan  # noqa: E402
from selection_core import Violation  # noqa: E402
import validate_selection_binding  # noqa: E402
from validate_selection_binding import validate_plan  # noqa: E402


def plan():
    return emit_plan(SELF_TEST_LAUNCH, SELF_TEST_TARGETS, route="per_offer_targets")


class ValidatePlanTests(unittest.TestCase):
    def test_a_plan_emitted_from_the_catalog_passes(self):
        validate_plan(plan(), SELF_TEST_LAUNCH)

    def test_every_tamper_is_refused_by_its_own_code(self):
        def header(key, value):
            return lambda p: p.update({key: value})

        def mapping(key, value):
            return lambda p: p["mappings"][0].update({key: value})

        cases = [
            ("tenant", header("tenant_id", "OTHER-TENANT"), "S78-SELECTION-TENANT-MISMATCH"),
            ("location", header("location_id", "OTHER-LOC"), "S78-SELECTION-TENANT-MISMATCH"),
            ("launch", header("launch_id", "OTHER-LAUNCH"), "S78-SELECTION-TENANT-MISMATCH"),
            ("revision", header("revision", 99), "S78-SELECTION-STALE-REVISION"),
            ("amount", mapping("amount_minor", 1), "S78-SELECTION-PRICE-DRIFT"),
            ("currency", mapping("currency", "EUR"), "S78-SELECTION-PRICE-DRIFT"),
            ("native price", mapping("native_price_id", "FORGED"), "S78-SELECTION-PRICE-DRIFT"),
            ("native product", mapping("native_product_id", "FORGED"), "S78-SELECTION-PRICE-DRIFT"),
            ("price choice", mapping("price_choice_id", "NO-SUCH-PRICE"), "S78-SELECTION-PRICE-DRIFT"),
            ("offer", mapping("offer_id", "NO-SUCH-OFFER"), "S78-SELECTION-UNKNOWN-OFFER"),
        ]
        for label, mutate, code in cases:
            with self.subTest(label):
                bad = copy.deepcopy(plan())
                mutate(bad)
                with self.assertRaises(Violation) as ctx:
                    validate_plan(bad, SELF_TEST_LAUNCH)
                self.assertEqual(ctx.exception.code, code)

    def test_a_plan_that_validates_nothing_is_refused(self):
        good = plan()["mappings"]
        for mappings in ([], None, good + ["not-a-mapping"], good + [None]):
            with self.subTest(mappings=mappings):
                bad = dict(plan(), mappings=mappings)
                with self.assertRaises(Violation) as ctx:
                    validate_plan(bad, SELF_TEST_LAUNCH)
                self.assertEqual(ctx.exception.code, "S78-BINDING-INCOMPLETE")

    def test_a_tamper_in_any_mapping_is_refused_not_only_the_first(self):
        # every mapping is validated: tamper the LAST one (and a middle one when there is one)
        count = len(plan()["mappings"])
        self.assertGreater(count, 1, "the catalog plan needs several mappings for this test")
        for index in sorted({1, count - 1}):
            for key, value, code in [("amount_minor", 1, "S78-SELECTION-PRICE-DRIFT"),
                                     ("native_price_id", "FORGED", "S78-SELECTION-PRICE-DRIFT"),
                                     ("offer_id", "NO-SUCH-OFFER", "S78-SELECTION-UNKNOWN-OFFER")]:
                with self.subTest(index=index, key=key):
                    bad = copy.deepcopy(plan())
                    bad["mappings"][index][key] = value
                    with self.assertRaises(Violation) as ctx:
                        validate_plan(bad, SELF_TEST_LAUNCH)
                    self.assertEqual(ctx.exception.code, code)

    def test_a_revision_that_is_not_an_int_is_stale_not_the_current_one(self):
        # SELF_TEST_LAUNCH is at revision 1: "1", 1.0 and True must not be read as that revision
        self.assertEqual(SELF_TEST_LAUNCH["revision"], 1)
        for revision in ("1", 1.0, True, None, [1]):
            with self.subTest(revision=revision):
                bad = dict(plan(), revision=revision)
                with self.assertRaises(Violation) as ctx:
                    validate_plan(bad, SELF_TEST_LAUNCH)
                self.assertEqual(ctx.exception.code, "S78-SELECTION-STALE-REVISION")

    def test_a_mappings_value_that_is_not_a_list_is_refused_even_when_it_holds_mappings(self):
        bad = dict(plan(), mappings=tuple(plan()["mappings"]))
        with self.assertRaises(Violation) as ctx:
            validate_plan(bad, SELF_TEST_LAUNCH)
        self.assertEqual(ctx.exception.code, "S78-BINDING-INCOMPLETE")

    def test_validate_plan_hands_every_mapping_and_the_verifier_to_validate_binding(self):
        verifier = lambda record: True  # noqa: E731
        good = plan()
        with mock.patch.object(validate_selection_binding, "validate_binding") as spy:
            validate_plan(good, SELF_TEST_LAUNCH, approval_verifier=verifier)
        self.assertEqual(spy.call_count, len(good["mappings"]))
        for call, m in zip(spy.call_args_list, good["mappings"]):
            self.assertIs(call.kwargs.get("approval_verifier"), verifier)
            self.assertEqual(call.args[0]["offer_id"], m["offer_id"])
            self.assertEqual(call.args[1], SELF_TEST_LAUNCH)

    def test_a_price_no_longer_approved_is_refused(self):
        launch = copy.deepcopy(SELF_TEST_LAUNCH)
        good = emit_plan(launch, SELF_TEST_TARGETS, route="per_offer_targets")
        launch["offers"][0]["prices"][0]["approval_status"] = "unknown"
        with self.assertRaises(Violation):
            validate_plan(good, launch)


class HostTests(unittest.TestCase):
    """emit_plan is the host: it calls the validator on what it is about to return."""

    def test_emit_plan_runs_validate_plan_on_the_plan_it_returns(self):
        with mock.patch.object(emit_binding_plan, "validate_plan", wraps=validate_plan) as spy:
            emitted = emit_plan(SELF_TEST_LAUNCH, SELF_TEST_TARGETS, route="per_offer_targets")
        spy.assert_called_once()
        args, kwargs = spy.call_args
        self.assertEqual(args[0], emitted)
        self.assertEqual(args[1], SELF_TEST_LAUNCH)

    def test_emit_plan_runs_it_for_the_platform_native_route_too(self):
        with mock.patch.object(emit_binding_plan, "validate_plan", wraps=validate_plan) as spy:
            emit_plan(SELF_TEST_LAUNCH, SELF_TEST_TARGETS, route="platform_native_selection")
        spy.assert_called_once()

    def test_a_validator_refusal_stops_the_plan(self):
        refusal = Violation("S78-SELECTION-PRICE-DRIFT", "drift found by the checkout-time validator")
        with mock.patch.object(emit_binding_plan, "validate_plan", side_effect=refusal):
            with self.assertRaises(Violation) as ctx:
                emit_plan(SELF_TEST_LAUNCH, SELF_TEST_TARGETS, route="per_offer_targets")
        self.assertEqual(ctx.exception.code, "S78-SELECTION-PRICE-DRIFT")

    def test_the_host_is_a_second_wall_behind_the_catalog_gate(self):
        # emit_plan's own catalog gate is neutralised here; the checkout-time validator it now hosts
        # still refuses a plan whose price is not approved, so a gap in the first wall is not a pass.
        launch = copy.deepcopy(SELF_TEST_LAUNCH)
        launch["offers"][0]["prices"][0]["approval_status"] = "unknown"
        with mock.patch.object(emit_binding_plan, "validate_catalog"):
            with self.assertRaises(Violation) as ctx:
                emit_plan(launch, SELF_TEST_TARGETS, route="per_offer_targets")
        self.assertEqual(ctx.exception.code, "S78-UNAPPROVED-PRICE")

    def test_the_approval_verifier_reaches_the_validator(self):
        launch = copy.deepcopy(SELF_TEST_LAUNCH)
        verifier = lambda record: True  # noqa: E731
        with mock.patch.object(emit_binding_plan, "validate_plan", wraps=validate_plan) as spy:
            emit_plan(launch, SELF_TEST_TARGETS, route="per_offer_targets", approval_verifier=verifier)
        self.assertIs(spy.call_args.kwargs.get("approval_verifier"), verifier)


class ManifestClaimTests(unittest.TestCase):
    def test_the_hosted_script_is_counted_and_the_unhosted_ones_are_not(self):
        claim = json.loads((SKILL / "runtime-manifest.json").read_text())["done_claim"]
        self.assertIn("scripts/validate_selection_binding.py", claim["counted"])
        self.assertNotIn("scripts/validate_selection_binding.py", claim["not_counted"])
        for unhosted in ("scripts/selection_runtime.py", "scripts/selection_session.py",
                         "scripts/selection_session_store.py"):
            self.assertIn(unhosted, claim["not_counted"])
        self.assertFalse(set(claim["counted"]) & set(claim["not_counted"]))

    def test_a_counted_script_that_is_not_a_chain_entry_is_imported_by_a_counted_host(self):
        # the hosted claim must stay true: emit_binding_plan.py (counted by its own entry point)
        # must still import and call validate_plan, or the manifest line is a lie.
        source = (SKILL / "scripts" / "emit_binding_plan.py").read_text()
        self.assertIn("from validate_selection_binding import validate_plan", source)
        self.assertIn("validate_plan(", source)


if __name__ == "__main__":
    unittest.main()
