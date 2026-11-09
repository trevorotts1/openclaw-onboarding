"""NFX-001: the launcher repairs in the sixteen-fix release (Document 3).

FIX-04  a paid-plan fallback that carries design_style, and a bridge read that tolerates its absence
FIX-05  the approval-bound plan_hash threaded through every paid image-plan call site
FIX-13  the image-plan path comparison canonicalises both sides and still refuses a different file
FIX-09  the dependencies report's exit status and readiness flag derive from one blocker set
FIX-12  the membership read-back is scoped to the BlackCEO-internal launch entry point

Fixtures only: no network, no paid call, no live account, nothing written outside a temp folder.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))
sys.path.insert(0, str(SKILL_ROOT / "fixtures"))
sys.path.insert(0, str(HERE))

from test_only_readback import paid_image_plan  # noqa: E402

from launcher_core import (cli, dependencies, entitlement, image_plan,  # noqa: E402
                           intake, launch_bridge, route)

import substrate  # noqa: E402  (routes/ is on sys.path above)

_SEAL = {}


def setUpModule():
    """Stub the front-door seal for this module only.

    The release pin covers launcher_core/*.py and the Skill 49 tree, so this unit's own edits make the
    front door refuse (``ABORT [HASH-PIN]``) until the release lane mints the one line. Document 3 §5
    records that as expected, not a defect. These tests exercise the repair logic, not the seal, so the
    seal is stubbed here; the production gate is untouched and a real dispatch still runs it."""
    _SEAL["patch"] = mock.patch.object(substrate, "front_door_check", lambda *a, **k: None)
    _SEAL["patch"].start()


def tearDownModule():
    _SEAL["patch"].stop()

FIXTURE = SKILL_ROOT / "fixtures" / "elevation" / "intake.json"
SIX_BLOCKERS = ["missing-tree-50-email-engine",
                "missing-shared-signature-launch-contract",
                "missing-shared-client-intake",
                "missing-skill-department-map",
                "registry-line-81",
                "registry-line-launcher"]


def _brand(root: Path) -> str:
    path = root / "brand.json"
    path.write_text(json.dumps({"palette_status": "provided"}), encoding="utf-8")
    return str(path)


def _intake(root: Path, **over) -> dict:
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    doc["image_plan"] = {"brand_file": _brand(root), "brand_owner": "TEST-ONLY Client"}
    doc.update(over)
    return doc


def _run_cli(*argv) -> tuple:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main([str(a) for a in argv])
    return rc, out.getvalue(), err.getvalue()


# --------------------------------------------------------------------------- FIX-04

class FallbackDesignStyleTests(unittest.TestCase):
    """The fallback producer carries design_style, and the bridge consumes both producers."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _resolved(self):
        return image_plan.resolve({"brand_file": _brand(self.root),
                                   "brand_owner": "TEST-ONLY Client", "design_style": "B"},
                                  test_only=True)[0]

    def test_the_fallback_inputs_carry_a_real_design_style_from_the_intake(self):
        doc = _intake(self.root)
        doc["image_plan"]["design_style"] = "B"
        normalized = intake.validate(doc)
        # no brand file for the bridge: the resolver refuses, so this is the fallback path
        doc["image_plan"].pop("brand_file")
        normalized = intake.validate(doc)
        inputs = cli._plan_inputs(normalized, test_only=True, plan_hash="a" * 64)
        self.assertEqual(inputs["design_style"], "B")
        self.assertTrue(inputs["design_style"].strip())

    def test_the_fallback_defaults_design_style_and_never_to_empty_string(self):
        doc = _intake(self.root)
        doc["image_plan"].pop("brand_file")
        doc["image_plan"].pop("design_style", None)
        inputs = cli._plan_inputs(intake.validate(doc), test_only=True, plan_hash="a" * 64)
        self.assertEqual(inputs["design_style"], image_plan.DEFAULT_DESIGN_STYLE)
        self.assertNotEqual(inputs["design_style"], "")

    def test_fallback_key_set_is_a_subset_of_the_preferred_key_set(self):
        doc = _intake(self.root)
        doc["image_plan"].pop("brand_file")
        fallback = cli._plan_inputs(intake.validate(doc), test_only=True, plan_hash="a" * 64)
        preferred = self._resolved()
        self.assertTrue(set(fallback) <= set(preferred),
                        sorted(set(fallback) - set(preferred)))

    def test_the_bridge_consumes_both_producer_shapes_without_raising(self):
        doc = _intake(self.root)
        normalized = intake.validate(doc)
        graph = route.compile_route(normalized)
        preferred = self._resolved()
        fallback = cli._plan_inputs(normalized, test_only=True, plan_hash="a" * 64)
        for name, inputs in (("preferred", preferred), ("fallback", fallback)):
            with self.subTest(path=name):
                launch = launch_bridge.to_launch_record(normalized, graph, inputs)
                refs = [r for r in launch["source_refs"]
                        if r.startswith(launch_bridge.STRUCTURE_PREFIX + "design_style=")]
                self.assertEqual(len(refs), 1, launch["source_refs"])
                self.assertTrue(refs[0].split("=", 1)[1].strip(), refs)

    def test_the_bridge_tolerates_an_input_mapping_that_omits_design_style(self):
        doc = _intake(self.root)
        normalized = intake.validate(doc)
        graph = route.compile_route(normalized)
        launch = launch_bridge.to_launch_record(normalized, graph, {"image_provider": "kie"})
        self.assertIn(f"{launch_bridge.STRUCTURE_PREFIX}design_style={image_plan.DEFAULT_DESIGN_STYLE}",
                      launch["source_refs"])


# --------------------------------------------------------------------------- FIX-05

class PlanHashThreadingTests(unittest.TestCase):
    """Every paid image-plan call site supplies a non-empty plan_hash; the refusal stays reachable."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_resolved_launch_threads_the_approval_bound_hash(self):
        doc = _intake(self.root)
        with mock.patch.object(image_plan, "resolve", wraps=image_plan.resolve) as spy:
            cli._resolved_launch(doc, plan_hash="a" * 64)
        self.assertEqual(spy.call_args.kwargs["plan_hash"], "a" * 64)

    def test_resolved_launch_has_no_plan_hash_default(self):
        with self.assertRaises(TypeError):
            cli._resolved_launch(_intake(self.root))  # type: ignore[call-arg]

    def test_cmd_plan_supplies_a_non_empty_hash_on_the_paid_path(self):
        doc = _intake(self.root, test_only=False)
        doc["image_plan"].update(paid_image_plan(9, "APPR-PAID"))
        path = self.root / "intake.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        with mock.patch.object(image_plan, "_verify_paid_budget", return_value=None), \
                mock.patch.object(image_plan, "resolve", wraps=image_plan.resolve) as spy:
            rc, _out, err = _run_cli("plan", "--intake", path)
        self.assertEqual(rc, 0, err)
        supplied = spy.call_args.kwargs["plan_hash"]
        self.assertTrue(isinstance(supplied, str) and supplied.strip(), supplied)

    def test_cmd_plan_requires_a_plan_hash_parameter(self):
        with self.assertRaises(TypeError):
            cli.cmd_plan(mock.Mock(intake=None, plan=None))  # type: ignore[call-arg]

    def test_the_bridge_call_site_passes_the_approval_bound_hash(self):
        doc = _intake(self.root)
        with mock.patch.object(launch_bridge, "resolve_launch",
                               wraps=launch_bridge.resolve_launch) as spy:
            with self.assertRaises(launch_bridge.BridgeError):
                launch_bridge.run(doc, self.root / "run", approval={"plan_hash": "f" * 64},
                                  client_identity_ref="c", worker_identity_ref="w")
        self.assertEqual(spy.call_args.kwargs["plan_hash"], "f" * 64)

    def test_an_empty_plan_hash_still_fires_the_approval_refusal(self):
        raw = {**paid_image_plan(9, "APPR-PAID"), "brand_owner": "TEST-ONLY Client"}
        with self.assertRaises(image_plan.ImagePlanError) as ctx:
            image_plan.resolve(raw, test_only=False, plan_hash="")
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-APPROVAL")
        self.assertIn("A paid run needs the plan hash your approval is bound to", str(ctx.exception))

    def test_an_explicitly_empty_hash_is_not_quietly_derived(self):
        doc = _intake(self.root)
        normalized = intake.validate(doc)
        graph = route.compile_route(normalized)
        with mock.patch.object(image_plan, "resolve", wraps=image_plan.resolve) as spy:
            launch_bridge.resolve_launch(normalized, graph, plan_hash="")
        self.assertEqual(spy.call_args.kwargs["plan_hash"], "")


# --------------------------------------------------------------------------- FIX-13

class CanonicalPathComparisonTests(unittest.TestCase):
    """One resolution routine on both sides: same file compares equal, a different file does not."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _config(self, recorded: str) -> Path:
        path = self.root / "bridge.json"
        path.write_text(json.dumps({"landing": {"image_inputs": recorded}}), encoding="utf-8")
        return path

    def _call(self, recorded: str, real: "Path | None" = None) -> dict:
        inputs = image_plan.resolve({"brand_file": _brand(self.root),
                                     "brand_owner": "TEST-ONLY Client"}, test_only=True)[0]
        dispatch = self.root / "dispatch"
        dispatch.mkdir(exist_ok=True)
        folder = real or self.root
        folder.mkdir(exist_ok=True)
        inputs_path = folder / "image_inputs.json"
        inputs_path.write_text("{}", encoding="utf-8")
        return launch_bridge._landing_bridge_config(
            {"bridge_config": str(self._config(recorded))}, dispatch, inputs, inputs_path)

    def test_instrument_control_one_file_two_spellings_compares_equal(self):
        real = self.root / "real"
        real.mkdir()
        link = self.root / "link"
        link.symlink_to(real, target_is_directory=True)
        self.assertTrue(launch_bridge._same_path(real / "image_inputs.json",
                                                 link / "image_inputs.json"))
        self.assertEqual(launch_bridge._canonical_path(link / "image_inputs.json"),
                         launch_bridge._canonical_path(real / "image_inputs.json"))

    def test_instrument_control_two_files_compare_unequal(self):
        (self.root / "one").mkdir()
        (self.root / "two").mkdir()
        self.assertFalse(launch_bridge._same_path(self.root / "one" / "image_inputs.json",
                                                  self.root / "two" / "image_inputs.json"))

    def test_a_symlinked_spelling_of_the_approved_file_is_admitted(self):
        real = self.root / "real"
        real.mkdir()
        link = self.root / "link"
        link.symlink_to(real, target_is_directory=True)
        self._call(str(link / "image_inputs.json"), real=real)
        written = json.loads((self.root / "dispatch" / "landing-bridge.json").read_text(encoding="utf-8"))
        self.assertEqual(written["landing"]["image_inputs"],
                         launch_bridge._canonical_path(real / "image_inputs.json"))

    def test_a_genuinely_different_path_is_still_refused_and_prints_two_canonical_paths(self):
        other = self.root / "other"
        other.mkdir()
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            self._call(str(other / "image_inputs.json"))
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-IMAGE-PLAN")
        message = str(ctx.exception)
        self.assertIn(launch_bridge._canonical_path(other / "image_inputs.json"), message)
        self.assertIn(launch_bridge._canonical_path(self.root / "image_inputs.json"), message)
        self.assertNotEqual(launch_bridge._canonical_path(other / "image_inputs.json"),
                            launch_bridge._canonical_path(self.root / "image_inputs.json"))


# --------------------------------------------------------------------------- FIX-09

def _dependency_report(blockers):
    entries = [{"id": b, "kind": "code", "ref": b, "required": True, "class": "required",
                "modes": ["plan"], "selected": True, "blocking": True, "why": "fixture",
                "status": "missing", "evidence": f"{b} is not present"} for b in blockers]
    entries.append({"id": "advisory-doc", "kind": "doc", "ref": "advisory", "required": False,
                    "class": "optional", "modes": ["plan"], "selected": False, "blocking": False,
                    "why": "fixture", "status": "missing", "evidence": "advisory only"})
    return {"target": "fixture", "mode": "plan", "harness": "fixture", "enabled_in_999": True,
            "would_enable": True, "seen_from": "fixture", "metadata": {"findings": []},
            "entries": entries, "present": [], "missing": list(blockers) + ["advisory-doc"],
            "unverifiable": [], "blockers": list(blockers),
            "closure": {"mode": "plan", "harness": "fixture", "declared_modes": ["plan"], "rows": [],
                        "required": list(blockers), "selected_conditional": [],
                        "unselected_optional": ["advisory-doc"], "not_in_this_mode": [],
                        "required_missing": list(blockers), "selected_missing": [],
                        "counts": {"entries": len(entries), "required": len(blockers),
                                   "selected_conditional": 0, "unselected_optional": 1}}}

class DependenciesExitStatusTests(unittest.TestCase):
    """Six blockers is the recorded Sonatta count; zero is the canonical control."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _run(self, blockers):
        with mock.patch.object(dependencies, "check", return_value=_dependency_report(blockers)):
            return _run_cli("dependencies", "--root", self.root)

    def test_six_blockers_exit_non_zero_and_name_every_blocker(self):
        rc, out, _err = self._run(SIX_BLOCKERS)
        self.assertNotEqual(rc, 0)
        self.assertIn("BLOCKING (6)", out)
        for blocker in SIX_BLOCKERS:
            self.assertIn(blocker, out)
        self.assertIn("enabled_in_999=False", out)

    def test_zero_blockers_exit_zero_and_report_ready(self):
        rc, out, _err = self._run([])
        self.assertEqual(rc, 0)
        self.assertIn("BLOCKING (0)", out)
        self.assertIn("enabled_in_999=True", out)

    def test_the_readiness_flag_and_the_exit_code_agree_in_both_cases(self):
        for blockers in (SIX_BLOCKERS, []):
            with self.subTest(blockers=len(blockers)):
                rc, out, _err = self._run(blockers)
                self.assertEqual(rc == 0, "enabled_in_999=True" in out)

    def test_advisory_entries_are_visible_and_never_change_the_exit_status(self):
        rc, out, _err = self._run([])
        self.assertEqual(rc, 0)
        self.assertIn("ADVISORY (1)", out)
        self.assertIn("advisory-doc", out)


# --------------------------------------------------------------------------- FIX-12

CM = entitlement._membership_module()

MEMBER = {"basis": "brand_management_membership", "evidence_ref": "c1", "attested_by": "agent"}
PURCHASE = {"basis": "purchase", "evidence_ref": "c1", "attested_by": "agent",
            "purchase_reference": "o1", "amount_minor": 49700, "currency": "USD"}


def _fake(contact_tags=("brand-management-member",), order_amount=497, order_contact="c1",
          order_status="completed"):
    return CM.StaticReadTransport({
        "/contacts/c1": {"contact": {"tags": list(contact_tags)}},
        "/payments/orders/o1": {"_id": "o1", "contactId": order_contact, "status": order_status,
                                "amount": order_amount, "currency": "USD"},
    })


class _NeverLooked:
    """A transport that fails the test if the client path consults it at all."""

    def request(self, *args, **kwargs):
        raise AssertionError("the account record was consulted on the client launch path")


class LaunchOriginScopingTests(unittest.TestCase):
    def setUp(self):
        self._saved = entitlement._transport
        entitlement.set_transport(None)
        self.addCleanup(entitlement.set_transport, None)

    def test_client_launch_with_no_membership_is_admitted(self):
        result = entitlement.gate(MEMBER, _fake(contact_tags=()))
        self.assertTrue(result["qualifies"])
        self.assertEqual(result["basis"], "brand_management_membership")

    def test_scope_proof_the_membership_lookup_never_runs_on_the_client_path(self):
        result = entitlement.gate(MEMBER, _NeverLooked())
        self.assertTrue(result["qualifies"])

    def test_internal_launch_by_a_non_member_is_still_refused(self):
        with self.assertRaises(entitlement.EntitlementError) as ctx:
            entitlement.internal_gate(MEMBER, _fake(contact_tags=()))
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ENTITLEMENT-NOT-MEMBER")

    def test_a_basis_outside_the_accepted_set_is_still_refused_on_the_client_path(self):
        for basis in ("school_of_ai_membership", "zhc"):
            with self.subTest(basis=basis):
                with self.assertRaises(entitlement.EntitlementError) as ctx:
                    entitlement.gate({**MEMBER, "basis": basis}, _fake())
                self.assertEqual(ctx.exception.code, "AF-LAUNCH-ENTITLEMENT-NOT-QUALIFIED")

    def test_a_qualifying_purchase_is_unchanged_on_the_client_path(self):
        self.assertTrue(entitlement.gate(PURCHASE, _fake())["proves_purchase"])
        with self.assertRaises(entitlement.EntitlementError) as ctx:
            entitlement.gate(PURCHASE, _fake(order_status="refunded"))
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ENTITLEMENT-PURCHASE-UNVERIFIED")

    def test_the_origin_argument_has_no_default_and_an_unknown_origin_is_refused(self):
        with self.assertRaises(TypeError):
            entitlement.attest(MEMBER, _fake())  # type: ignore[call-arg]
        with self.assertRaises(entitlement.EntitlementError) as ctx:
            entitlement.attest(MEMBER, _fake(), launch_origin="account_state")
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ENTITLEMENT-ORIGIN")


if __name__ == "__main__":
    unittest.main()
