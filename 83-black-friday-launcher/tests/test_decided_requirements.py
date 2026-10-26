"""LAUNCH-02b decided-requirement checks. Stdlib only: python3 -m unittest.

Each owner decision gets executable proof, and each refusal path is exercised
so a green run cannot come from a bypassed gate.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import (  # noqa: E402
    checks, checkout, council, dependencies, entitlement, intake, package, route,
)
from launcher_core.constants import JOURNEY_MODES, SEAM_IDS  # noqa: E402


def base_intake(mode: str = "single_simple", basis: str = "purchase") -> dict:
    offers = [{"offer_id": "main-1", "name": "Launch", "role": "main",
               "price": {"amount_minor": 49700, "currency": "USD"}}]
    if mode in ("multiple_options", "folded_levels"):
        offers.append({"offer_id": "main-2", "name": "Launch Plus", "role": "main",
                       "price": {"amount_minor": 99700, "currency": "USD"}})
    attestation = {"basis": basis, "evidence_ref": "ev-1", "attested_by": "operator"}
    if basis == "purchase":
        attestation["purchase_reference"] = "order-1"
    return {
        "schema_version": "1.0",
        "tenant_id": "tenant-a",
        "location_id": "loc-a",
        "launch_id": "bf-2026",
        "revision": 1,
        "journey_mode": mode,
        "brand": {"ref": "brand-a", "hash": "a" * 64},
        "copy_profile": "signature_12_section",
        "approval": {"ref": "approval-1", "hash": "b" * 64},
        "entitlement_attestation": attestation,
        "offers": offers,
    }


def stub_council(_launch):
    return {"status": "advice_returned", "ready": True,
            "advice": {"recommendation": "stub"}, "advice_state": "returned"}


def not_ready(_launch):
    return {"status": "not_ready", "ready": False, "detail": "no route",
            "advice": None, "advice_state": "pending_live_session"}


def pieces_for(run_dir: Path, graph: dict, normalized: dict) -> dict:
    pieces = {}
    for node in graph["nodes"]:
        rel = f"pieces/{node['page_id']}/page.html"
        target = run_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"<html>{node['role']}</html>\n", encoding="utf-8")
        pieces[node["role"]] = {
            "schema_version": "1.0",
            "tenant_id": normalized["tenant_id"],
            "location_id": normalized["location_id"],
            "launch_id": normalized["launch_id"],
            "revision": normalized["revision"],
            "request_id": f"req-{node['page_id']}",
            "input_hash": "c" * 64,
            "page_id": node["page_id"],
            "status": "authored",
            "artifacts": [{"path": rel,
                           "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}],
            "author_session": "builder-1",
            "independent_review": False,
            "proof_class": "L0",
            "blockers": [],
            "native_bindings_ref": None,
            "test_only": True,
        }
    return pieces


class EntitlementGateTests(unittest.TestCase):
    def test_brand_management_membership_qualifies_without_a_purchase(self):
        result = intake.validate(base_intake(basis="brand_management_membership"))
        self.assertTrue(result["entitlement"]["qualifies"])
        self.assertFalse(result["entitlement"]["requires_purchase"])
        self.assertIsNone(result["entitlement"]["purchase_reference"])
        self.assertEqual(result["entitlement"]["billing"], "none")

    def test_zhc_with_brand_management_qualifies(self):
        result = intake.validate(base_intake(basis="zhc_with_brand_management"))
        self.assertTrue(result["entitlement"]["qualifies"])

    def test_school_of_ai_alone_does_not_qualify(self):
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(base_intake(basis="school_of_ai_membership"))
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ENTITLEMENT-NOT-QUALIFIED")

    def test_zhc_alone_does_not_qualify(self):
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(base_intake(basis="zhc"))
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ENTITLEMENT-NOT-QUALIFIED")

    def test_unknown_basis_fails_closed(self):
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(base_intake(basis="friend_of_the_founder"))
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ENTITLEMENT-UNKNOWN")

    def test_missing_attestation_fails_closed(self):
        payload = base_intake()
        del payload["entitlement_attestation"]
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-INTAKE-MISSING")
        self.assertEqual(ctx.exception.field, "entitlement_attestation")

    def test_purchase_without_a_reference_is_refused(self):
        payload = base_intake()
        del payload["entitlement_attestation"]["purchase_reference"]
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code,
                         "AF-LAUNCH-ENTITLEMENT-PURCHASE-UNVERIFIED")

    def test_membership_may_not_claim_a_purchase(self):
        payload = base_intake(basis="brand_management_membership")
        payload["entitlement_attestation"]["purchase_reference"] = "order-9"
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ENTITLEMENT-ATTESTATION")

    def test_a_contradicting_purchase_price_is_refused(self):
        payload = base_intake()
        payload["entitlement_attestation"].update(
            {"amount_minor": 100, "currency": "USD"})
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code,
                         "AF-LAUNCH-ENTITLEMENT-PRICE-CONTRADICTION")

    def test_declaration_is_carried_and_digested(self):
        declaration = entitlement.load_declaration()
        self.assertTrue(declaration["no_billing"])
        self.assertFalse(declaration["creates_entitlements"])
        record = entitlement.declaration_record()
        self.assertEqual(record["path"], "entitlement-declaration.json")
        self.assertEqual(len(record["sha256"]), 64)

    def test_a_silently_flipped_rule_is_caught(self):
        declaration = json.loads(entitlement.declaration_path().read_text(encoding="utf-8"))
        for rule in declaration["rules"]:
            if rule["basis"] == "brand_management_membership":
                rule["requires_purchase"] = True
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "entitlement-declaration.json"
            fake.write_text(json.dumps(declaration), encoding="utf-8")
            with mock.patch.object(entitlement, "declaration_path", return_value=fake):
                with self.assertRaises(entitlement.EntitlementError) as ctx:
                    entitlement.load_declaration()
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ENTITLEMENT-DECLARATION")

    def test_missing_declaration_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(entitlement, "declaration_path",
                                   return_value=Path(tmp) / "nope.json"):
                with self.assertRaises(entitlement.EntitlementError) as ctx:
                    entitlement.load_declaration()
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ENTITLEMENT-DECLARATION")

    def test_no_billing_api_is_imported_or_called(self):
        source = Path(entitlement.__file__).read_text(encoding="utf-8")
        for forbidden in ("stripe", "requests", "urllib", "subprocess", "charge("):
            self.assertNotIn(forbidden, source)


class CouncilPlanningTests(unittest.TestCase):
    def setUp(self):
        self.intake = intake.validate(base_intake())

    def test_stub_advice_is_recorded_and_never_permission(self):
        record = council.planning_step(self.intake, runner=stub_council)
        self.assertEqual(record["step"], "council_launch_planning")
        self.assertEqual(record["skill"], "council-of-wise-elders")
        self.assertEqual(record["status"], "advice_returned")
        self.assertEqual(record["advice_state"], "returned")
        self.assertIs(record["blocks_build"], False)
        self.assertIs(record["is_permission"], False)

    def test_not_ready_is_recorded_and_does_not_block(self):
        record = council.planning_step(self.intake, runner=not_ready)
        self.assertEqual(record["status"], "not_ready")
        self.assertIs(record["blocks_build"], False)

    def test_a_raising_runner_is_recorded_not_raised(self):
        def boom(_launch):
            raise RuntimeError("provider down")

        record = council.planning_step(self.intake, runner=boom)
        self.assertEqual(record["status"], "not_ready")
        self.assertIn("provider down", record["detail"])
        self.assertIs(record["blocks_build"], False)

    def test_garbage_runner_output_is_normalized(self):
        record = council.planning_step(self.intake, runner=lambda _l: "nope")
        self.assertEqual(record["status"], "not_ready")
        self.assertIs(record["blocks_build"], False)

    def test_a_not_ready_council_does_not_change_the_graph(self):
        graph_a = route.compile_route(self.intake,
                                      council.planning_step(self.intake, runner=not_ready))
        graph_b = route.compile_route(self.intake,
                                      council.planning_step(self.intake, runner=stub_council))
        self.assertEqual(graph_a, graph_b)

    def test_the_documented_entry_point_exists(self):
        self.assertEqual(council.entry_point().name, "doctor.mjs")
        self.assertTrue(council.entry_point().is_file(),
                        f"{council.entry_point()} is the documented Skill 77 path")

    def test_council_never_becomes_a_route_role(self):
        record = route.launch_record(self.intake,
                                     council.planning_step(self.intake, runner=stub_council))
        self.assertIn("council", record)
        graph = route.compile_route(self.intake)
        self.assertNotIn("council", [n["role"] for n in graph["nodes"]])


class CheckoutMappingTests(unittest.TestCase):
    def mapping(self, mode):
        normalized = intake.validate(base_intake(mode))
        graph = route.compile_route(normalized)
        return checkout.order_form_mapping(normalized, graph)

    def test_contract_is_the_real_s79_schema(self):
        contract = checkout.load_contract()
        self.assertIn("checkout_request", contract["$defs"])
        self.assertEqual(checkout.checkout_modes(contract),
                         ["combined_single_offer", "post_selection"])
        self.assertIn("main_price", checkout.required_fields(contract))

    def test_single_simple_uses_combined_mode(self):
        mapping = self.mapping("single_simple")
        self.assertEqual(mapping["checkout_mode"], "combined_single_offer")
        self.assertEqual(mapping["checkout_mode_state"], "resolved")
        self.assertEqual(mapping["supplied"]["main_offer_id"], "main-1")

    def test_multiple_options_uses_post_selection_mode(self):
        mapping = self.mapping("multiple_options")
        self.assertEqual(mapping["checkout_mode"], "post_selection")
        self.assertEqual(mapping["checkout_mode_state"], "resolved")

    def test_folded_levels_records_a_contract_gap_not_a_guess(self):
        mapping = self.mapping("folded_levels")
        self.assertIsNone(mapping["checkout_mode"])
        self.assertEqual(mapping["checkout_mode_state"], "contract_gap")
        self.assertNotIn("main_offer_id", mapping["supplied"])
        self.assertEqual(len(mapping["main_offers"]), 2)
        self.assertTrue(any("express neither" in n for n in mapping["notes"]))

    def test_unknown_fields_are_named_and_never_defaulted(self):
        mapping = self.mapping("single_simple")
        self.assertIn("fulfillment_mapping_ref", mapping["unknown"])
        self.assertIn("terms_ref", mapping["unknown"])
        self.assertNotIn("main_price", mapping["unknown"])

    def test_native_ids_are_explicit_null_not_invented(self):
        price = self.mapping("single_simple")["supplied"]["main_price"]
        self.assertIsNone(price["native_product_id"])
        self.assertIsNone(price["native_price_id"])
        self.assertIn("currency_exponent", price["unknown"])

    def test_the_real_s79_validator_is_bound(self):
        # jsonschema is the Launcher's own runtime requirement (requirements.txt),
        # so under the verification interpreter the validator must bind: an
        # "unavailable" state is a failure, never a recorded exception (L25-BF-40).
        mapping = self.mapping("single_simple")
        validator = mapping["validator"]
        self.assertEqual(validator["state"], "bound", validator)
        self.assertIn(validator["probe"]["result"], ("accepted", "rejected"))

    def test_the_mapping_is_derived_from_the_contract_file(self):
        mapping = self.mapping("single_simple")
        required = checkout.required_fields(checkout.load_contract())
        self.assertTrue(required)
        for name in required:
            self.assertTrue(name in mapping["supplied"]
                            or name in mapping["unknown"], name)

    def test_checkout_is_never_a_dispatch_adapter(self):
        mapping = self.mapping("single_simple")
        self.assertIs(mapping["dispatch_adapter"], False)
        self.assertEqual(mapping["route_node"], "checkout")


class OfferFactTests(unittest.TestCase):
    def test_zero_price_is_refused(self):
        payload = base_intake()
        payload["offers"][0]["price"]["amount_minor"] = 0
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-INTAKE-PRICE")

    def test_float_price_is_refused(self):
        payload = base_intake()
        payload["offers"][0]["price"]["amount_minor"] = 49.7
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-INTAKE-PRICE")

    def test_a_level_is_supplied_or_explicitly_unknown(self):
        payload = base_intake()
        payload["offers"][0]["level"] = {"state": "unknown"}
        self.assertEqual(intake.validate(payload)["offers"][0]["level"]["state"],
                         "unknown")
        payload["offers"][0]["level"] = {"state": "supplied", "name": "Level A",
                                         "deliverables": ["One call"]}
        self.assertEqual(intake.validate(payload)["offers"][0]["level"]["state"],
                         "supplied")

    def test_a_defaulted_level_is_refused(self):
        payload = base_intake()
        payload["offers"][0]["level"] = {"state": "default"}
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-INTAKE-LEVEL")

    def test_offer_facts_carry_provenance_not_defaults(self):
        normalized = intake.validate(base_intake())
        facts = intake.offer_facts(normalized)
        self.assertEqual(facts[0]["price"]["provenance"], "supplied")
        self.assertEqual(facts[0]["level"]["provenance"], "unknown")
        self.assertEqual(facts[0]["entitlement"]["provenance"], "attested")

    def test_operational_defaults_never_touch_commercial_facts(self):
        normalized = intake.validate(base_intake())
        for field, provenance in normalized["provenance"].items():
            root = field.split("[", 1)[0].split(".", 1)[0]
            if root in ("offers", "entitlement_attestation", "level"):
                self.assertFalse(provenance.startswith("default:"), field)


class FoldedLevelsTests(unittest.TestCase):
    def test_mode_is_declared(self):
        self.assertIn("folded_levels", JOURNEY_MODES)

    def test_folded_shape_has_no_selection_page(self):
        normalized = intake.validate(base_intake("folded_levels"))
        graph = route.compile_route(normalized)
        roles = [n["role"] for n in graph["nodes"]]
        self.assertEqual(roles, ["landing", "checkout", "thank_you"])
        self.assertFalse(any(e["event"] == "selection_validated"
                             for e in graph["edges"]))

    def test_folded_levels_keeps_distinct_offers(self):
        normalized = intake.validate(base_intake("folded_levels"))
        mains = [o for o in normalized["offers"] if o["role"] == "main"]
        self.assertEqual(len(mains), 2)
        self.assertEqual(len({o["offer_id"] for o in mains}), 2)

    def test_folded_levels_refuses_identical_levels(self):
        payload = base_intake("folded_levels")
        payload["offers"][1]["price"]["amount_minor"] = 49700
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-INTAKE-OFFER")

    def test_multiple_options_is_unchanged(self):
        graph = route.compile_route(intake.validate(base_intake("multiple_options")))
        self.assertEqual([n["role"] for n in graph["nodes"]],
                         ["landing", "product_selection", "checkout", "thank_you"])

    def test_single_simple_is_unchanged(self):
        graph = route.compile_route(intake.validate(base_intake("single_simple")))
        self.assertEqual([n["role"] for n in graph["nodes"]],
                         ["landing", "checkout", "thank_you"])


class CrossSaleTests(unittest.TestCase):
    def payload(self):
        p = base_intake("folded_levels")
        p["offers"][0]["relationships"] = {"complements": ["main-2"]}
        p["offers"].append({"offer_id": "bump-1", "name": "Bump", "role": "bump",
                            "price": {"amount_minor": 2700, "currency": "USD"},
                            "relationships": {"included_in": ["main-2"]}})
        return p

    def test_relationships_are_kept_and_surfaced_on_the_thank_you_page(self):
        normalized = intake.validate(self.payload())
        record = route.launch_record(normalized)
        self.assertEqual(record["cross_sales"]["teaching"]["state"], "pending")
        self.assertIs(record["cross_sales"]["route_node"], False)
        self.assertEqual(record["cross_sales"]["surface"], "thank_you")
        self.assertEqual(len(record["cross_sales"]["relationships"]), 2)

        sys.path.insert(0, str(SKILL_ROOT / "routes"))
        import build_time

        plan = build_time.plan(record)
        thank_you = next(p for p in plan["pages"] if p["role"] == "thank_you")
        self.assertEqual(thank_you["cross_sales"]["teaching"]["state"], "pending")
        self.assertNotIn("cross_sale", [n["role"] for n in
                                        route.compile_route(normalized)["nodes"]])

    def test_unknown_relation_kind_is_refused(self):
        payload = self.payload()
        payload["offers"][0]["relationships"]["upsells"] = ["main-2"]
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-INTAKE-RELATION")

    def test_unknown_relation_target_is_refused(self):
        payload = self.payload()
        payload["offers"][0]["relationships"]["complements"] = ["ghost"]
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-INTAKE-RELATION")

    def test_self_relation_is_refused(self):
        payload = self.payload()
        payload["offers"][0]["relationships"]["requires"] = ["main-1"]
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-INTAKE-RELATION")


class PackageRecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run"
        self.normalized = intake.validate(base_intake("folded_levels"))
        self.advice = council.planning_step(self.normalized, runner=stub_council)
        self.graph = route.compile_route(self.normalized, self.advice)
        self.pieces = pieces_for(self.run_dir, self.graph, self.normalized)
        self.out = package.assemble(self.run_dir, self.normalized, self.graph,
                                    self.pieces, council=self.advice)
        self.manifest_path = self.run_dir / "package-manifest.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_package_records_every_decided_requirement(self):
        manifest = self.out["manifest"]
        self.assertTrue(manifest["entitlement"]["qualifies"])
        self.assertEqual(manifest["entitlement"]["billing"], "none")
        self.assertEqual(manifest["council"]["status"], "advice_returned")
        self.assertIs(manifest["council"]["blocks_build"], False)
        self.assertEqual(manifest["checkout"]["dispatch_adapter"], False)
        self.assertTrue(manifest["offer_facts"])
        self.assertEqual(manifest["cross_sales"]["teaching"]["state"], "pending")
        self.assertIn("council-advice.json", self.out["receipt"]["council"]["advice_path"])

    def clean_package(self):
        """A clean package on a shape whose Skill 79 mode resolves."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run_dir = Path(tmp.name) / "run"
        normalized = intake.validate(base_intake("single_simple"))
        advice = council.planning_step(normalized, runner=stub_council)
        graph = route.compile_route(normalized, advice)
        pieces = pieces_for(run_dir, graph, normalized)
        out = package.assemble(run_dir, normalized, graph, pieces, council=advice)
        return run_dir, Path(out["manifest_path"])

    def test_a_resolved_mode_package_passes_every_check(self):
        # The clean-package guarantee, on a shape whose Skill 79 mode resolves.
        run_dir, manifest_path = self.clean_package()
        self.assertEqual(checks.check_package(manifest_path, run_dir), [])

    def test_an_unavailable_validator_at_replay_fails_the_build_check(self):
        # L25-BF-40: the probe's "bound" verdict is earned by replaying its
        # request through the real Skill 79 validator at check time. When the
        # validator cannot load then, the binding is unproved: an interpreter
        # without jsonschema must fail the package, never print PASS.
        run_dir, manifest_path = self.clean_package()
        self.assertEqual(checks.check_package(manifest_path, run_dir), [])
        with mock.patch.object(
                checks, "_replay_checkout",
                return_value=("unavailable", "jsonschema is not importable")):
            fails = checks.check_package(manifest_path, run_dir)
        self.assertEqual(len(fails), 1, fails)
        self.assertTrue(fails[0].startswith("AF-LAUNCH-CHECKOUT-VALIDATOR"), fails)
        self.assertIn("unavailable", fails[0])

    def test_the_cli_fails_closed_when_the_validator_cannot_load(self):
        # L25-BF-40 in the form the verifier reproduced it: the command, not
        # the helper. A bound manifest checked by an interpreter that cannot
        # import jsonschema must exit non-zero and name the violation; before
        # this fix it exited 0 and printed "PASS package complete". jsonschema
        # is shadowed by an importable stub that raises, so the fault is the
        # same on every machine, and the unshadowed run is the control that
        # proves the shadow — not a broken CLI — is why the check fails.
        run_dir, manifest_path = self.clean_package()
        shadow = tempfile.TemporaryDirectory()
        self.addCleanup(shadow.cleanup)
        stub = Path(shadow.name) / "jsonschema"
        stub.mkdir()
        (stub / "__init__.py").write_text(
            'raise ImportError("jsonschema is absent (simulated, L25-BF-40)")\n',
            encoding="utf-8")
        command = [sys.executable, "-m", "launcher_core.cli", "check",
                   "--manifest", str(manifest_path), "--root", str(run_dir)]

        def run(extra_path):
            env = dict(os.environ)
            parts = [extra_path] if extra_path else []
            if env.get("PYTHONPATH"):
                parts.append(env["PYTHONPATH"])
            if parts:
                env["PYTHONPATH"] = os.pathsep.join(parts)
            else:
                env.pop("PYTHONPATH", None)
            return subprocess.run(command, cwd=str(SKILL_ROOT), env=env,
                                  capture_output=True, text=True)

        control = run(None)
        self.assertEqual(control.returncode, 0, control.stdout + control.stderr)
        self.assertIn("PASS package complete", control.stdout)
        shadowed = run(shadow.name)
        output = shadowed.stdout + shadowed.stderr
        self.assertNotEqual(shadowed.returncode, 0, output)
        self.assertIn("AF-LAUNCH-CHECKOUT-VALIDATOR", output)
        self.assertNotIn("PASS package complete", shadowed.stdout)

    def test_the_folded_level_package_is_blocked_only_on_the_unresolved_mode(self):
        # folded_levels has no mode in the Skill 79 contract (L25-BF-41): the
        # package is otherwise clean, so the block must be exactly the one
        # contract gap — never a silent pass, never a second defect hiding it.
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertEqual([f.split(":")[0] for f in fails],
                         ["AF-LAUNCH-CHECKOUT-MODE"], fails)
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertIs(manifest["checkout"]["delivery_blocked"], True)

    def test_a_defaulted_price_fails_the_build_check(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["offer_facts"][0]["price"]["provenance"] = "default: guessed"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-OFFER-DEFAULTED") for f in fails), fails)

    def test_a_defaulted_level_fails_the_build_check(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["offer_facts"][0]["level"]["provenance"] = "default: assumed"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-OFFER-DEFAULTED") for f in fails), fails)

    def test_a_defaulted_entitlement_fails_the_build_check(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["offer_facts"][0]["entitlement"]["provenance"] = "default: assumed"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-OFFER-DEFAULTED") for f in fails), fails)

    def test_a_billing_entitlement_fails_the_build_check(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["entitlement"]["billing"] = "charged"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-ENTITLEMENT-BILLING") for f in fails), fails)

    def test_a_blocking_council_record_fails_the_build_check(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["council"]["blocks_build"] = True
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-COUNCIL") for f in fails), fails)

    def test_council_as_permission_fails_the_build_check(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["council"]["is_permission"] = True
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any("is_permission" in f for f in fails), fails)

    def test_a_dispatch_checkout_adapter_fails_the_build_check(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["checkout"]["dispatch_adapter"] = True
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-CHECKOUT") for f in fails), fails)

    def test_an_invented_teaching_state_fails_the_build_check(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["cross_sales"]["teaching"]["state"] = "supplied"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-CROSS-SALES") for f in fails), fails)

    def test_a_tampered_advice_record_fails_the_build_check(self):
        path = self.run_dir / "council-advice.json"
        path.write_text("{}\n", encoding="utf-8")
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-COUNCIL") for f in fails), fails)


class DependencyPackageTests(unittest.TestCase):
    def test_manifest_covers_every_named_dependency(self):
        manifest = dependencies.load_manifest()
        ids = {e["id"] for e in manifest["entries"]}
        for required in ("tree-49-signature-funnel",
                         "tree-78-signature-product-selection",
                         "tree-79-signature-order-form",
                         "tree-80-signature-upsell",
                         "shared-utils-signature-launch",
                         "registry-line-81",
                         "registry-line-82",
                         "registry-line-launcher",
                         "skill-number-assigned",
                         "department-map-entry-launcher",
                         "installer-registration-launcher"):
            self.assertIn(required, ids)

    def test_preflight_reports_enabled_from_registration_and_dependencies(self):
        manifest = dependencies.load_manifest()
        self.assertNotIn("enabled_in_999", manifest)
        report = dependencies.check()
        # jsonschema is the one blocker that depends on the running interpreter's
        # site-packages; verify.sh refuses to run without it (L25-BF-40).
        self.assertLessEqual(set(report["blockers"]), {"runtime-jsonschema"})
        self.assertIs(report["enabled_in_999"], report["would_enable"])

    def test_preflight_is_not_enabled_without_a_registered_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = dependencies.check(Path(tmp))
        self.assertIs(report["enabled_in_999"], False)

    def test_report_names_present_and_missing(self):
        report = dependencies.check()
        self.assertTrue(report["present"])
        self.assertIsInstance(report["missing"], list)
        for entry in report["entries"]:
            self.assertIn(entry["status"], ("present", "missing", "unverifiable"))
            self.assertTrue(entry["evidence"])

    def test_an_empty_root_reports_everything_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = dependencies.check(Path(tmp))
        # Root-scoped entries resolve against the checked-out tree and must all
        # be missing. Runtime packages are interpreter-level, so they report
        # what the running interpreter imports (verify.sh refuses to run without
        # jsonschema) and are the only entries an empty root may show present.
        runtime_present = ["runtime-jsonschema"] if (
            importlib.util.find_spec("jsonschema") is not None) else []
        self.assertEqual(report["present"], runtime_present)
        self.assertTrue(all(e["status"] == "missing" for e in report["entries"]
                            if e["id"] != "runtime-jsonschema"))
        self.assertTrue(report["missing"])
        self.assertFalse(report["would_enable"])

    def test_the_launcher_number_is_assigned(self):
        report = dependencies.check()
        entry = next(e for e in report["entries"]
                     if e["id"] == "skill-number-assigned")
        self.assertEqual(entry["status"], "present")
        self.assertIn("number_final=True", entry["evidence"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
