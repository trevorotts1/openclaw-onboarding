"""L04 artifact proof and package validation (UL-008).

The launcher's package is only as good as the receipt that proves it. These
tests are synthetic-local: no network, no provider call, no live send. They
prove the acceptance this lane owns:

  * canonical launch-plan validation: cycles, unknown dependencies, unsupported
    schema versions and non-draft units fail closed;
  * calendar validation: IANA zones, DST-correct offsets, strict phase order;
  * typed per-unit receipts bound to tenant, location, launch, revision and the
    approved plan hash, each carrying artifact bytes, the request it answers
    and the lane that validated it;
  * authored / draft-installed / tested / live-verified proof stay separate, so
    a draft is never read as live;
  * zero-byte or tampered artifacts never recover a unit to done.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parent
BF_PLAN = REPO_ROOT / "shared-utils/signature_launch_contract/fixtures/black-friday.json"
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import (  # noqa: E402
    checks, council, intake, launch_plan, package, route,
)


_UNSET = object()


def base_intake(launch_id: str = "black-friday-2026") -> dict:
    return {
        "schema_version": "1.0",
        "tenant_id": "tenant-a",
        "location_id": "loc-a",
        "launch_id": launch_id,
        "revision": 1,
        "journey_mode": "single_simple",
        "brand": {"ref": "brand-a", "hash": "a" * 64},
        "copy_profile": "signature_12_section",
        "approval": {"ref": "approval-1", "hash": "b" * 64},
        "entitlement_attestation": {"basis": "purchase", "evidence_ref": "ev-1",
                                    "attested_by": "operator", "purchase_reference": "order-1"},
        "offers": [{"offer_id": "main-1", "name": "Launch", "role": "main",
                    "price": {"amount_minor": 49700, "currency": "USD"}}],
    }


def stub_council(_launch):
    return {"status": "advice_returned", "ready": True,
            "advice": {"recommendation": "stub"}, "advice_state": "returned"}


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


def plan_fixture() -> dict:
    return json.loads(BF_PLAN.read_text(encoding="utf-8"))


def all_delivered(plan: dict) -> dict:
    return {unit["id"]: {"state": "complete"} for unit in launch_plan.planned_units(plan)}


class _RunFixture(unittest.TestCase):
    """One assembled offline package in a temp run dir."""

    plan: dict | None = None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run"
        self.payload = base_intake()
        self.normalized = intake.validate(self.payload)
        self.advice = council.planning_step(self.normalized, runner=stub_council)
        self.graph = route.compile_route(self.normalized)
        self.pieces = pieces_for(self.run_dir, self.graph, self.normalized)
        self.plan = copy.deepcopy(self.plan) if self.plan else None
        self.out = self.assemble()

    def tearDown(self):
        self.tmp.cleanup()

    def assemble(self, pieces=None, plan=_UNSET):
        if plan is _UNSET:
            plan = self.plan
        kwargs = {"council": self.advice}
        if plan is not None:
            kwargs["launch_plan"] = plan
            kwargs["deliveries"] = all_delivered(plan)
        return package.assemble(self.run_dir, self.normalized, self.graph,
                                pieces or self.pieces, **kwargs)

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / "package-manifest.json"

    def read_manifest(self) -> dict:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def write_manifest(self, manifest: dict) -> None:
        self.manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                      encoding="utf-8")

    def read_receipt(self) -> dict:
        return json.loads((self.run_dir / "receipt.json").read_text(encoding="utf-8"))

    def write_receipt(self, receipt: dict) -> None:
        (self.run_dir / "receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@unittest.skipUnless(BF_PLAN.is_file(), "shared launch-plan contract fixture is not installed")
class CanonicalPlanTests(unittest.TestCase):
    def test_a_cycle_fails_closed(self):
        plan = plan_fixture()
        plan["pages"][0]["waits_for"] = [plan["pages"][1]["id"]]
        plan["pages"][1]["waits_for"] = [plan["pages"][0]["id"]]
        with self.assertRaises(launch_plan.LaunchPlanError) as ctx:
            launch_plan.planned_units(plan)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PLAN-CYCLE")

    def test_an_unknown_dependency_fails_closed(self):
        plan = plan_fixture()
        plan["automations"][0]["waits_for"] = ["unit_that_does_not_exist"]
        with self.assertRaises(launch_plan.LaunchPlanError) as ctx:
            launch_plan.planned_units(plan)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PLAN-DEPENDENCY")

    def test_an_unsupported_schema_version_fails_closed(self):
        plan = plan_fixture()
        plan["schema_version"] = "2.0.0"
        with self.assertRaises(launch_plan.LaunchPlanError) as ctx:
            launch_plan.planned_units(plan)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PLAN-SCHEMA")

    def test_a_non_draft_email_fails_closed(self):
        plan = plan_fixture()
        plan["email_sequences"][0]["draft_only"] = False
        with self.assertRaises(launch_plan.LaunchPlanError) as ctx:
            launch_plan.planned_units(plan)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PLAN-DRAFT")


@unittest.skipUnless(BF_PLAN.is_file(), "shared launch-plan contract fixture is not installed")
class CalendarValidatorTests(unittest.TestCase):
    def test_an_unknown_iana_zone_fails_closed(self):
        plan = plan_fixture()
        plan["launch_calendar"]["timezone"] = "Mars/Olympus_Mons"
        with self.assertRaises(launch_plan.LaunchPlanError) as ctx:
            launch_plan.black_friday_calendar(plan)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-CALENDAR-ZONE")

    def test_a_dst_wrong_offset_fails_closed(self):
        plan = plan_fixture()
        # 2026-07-01 in New York is EDT (-04:00); -05:00 is the winter offset.
        plan["launch_calendar"]["black_friday"]["teaser_at"] = "2026-07-01T09:00:00-05:00"
        with self.assertRaises(launch_plan.LaunchPlanError) as ctx:
            launch_plan.black_friday_calendar(plan)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-CALENDAR-OFFSET")

    def test_an_empty_open_window_fails_closed(self):
        plan = plan_fixture()
        plan["launch_calendar"]["doors_close_at"] = plan["launch_calendar"]["doors_open_at"]
        with self.assertRaises(launch_plan.LaunchPlanError) as ctx:
            launch_plan.black_friday_calendar(plan)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-CALENDAR-ORDER")

    def test_the_compiler_gets_aware_instants_and_data_violations(self):
        plan = plan_fixture()
        instants = launch_plan.calendar_instants(plan)
        self.assertEqual(set(instants), {"teaser", "countdown", "doors_open", "launch",
                                         "cyber_monday", "last_call", "doors_close"})
        self.assertTrue(all(value.tzinfo is not None for value in instants.values()))
        self.assertLess(instants["teaser"], instants["doors_open"])
        self.assertEqual(launch_plan.calendar_violations(plan), [])
        broken = copy.deepcopy(plan)
        broken["launch_calendar"]["timezone"] = "Nowhere/Nothing"
        self.assertEqual(launch_plan.calendar_violations(broken)[0]["code"],
                         "AF-LAUNCH-CALENDAR-ZONE")


class PageOnlyReceiptTests(_RunFixture):
    def test_the_receipt_is_typed_and_clean(self):
        receipt = self.read_receipt()
        self.assertEqual(receipt["schema_version"], package.RECEIPT_SCHEMA_VERSION)
        self.assertEqual(receipt["receipt_type"], package.RECEIPT_TYPE)
        self.assertEqual(receipt["approved_plan_hash"], self.payload["approval"]["hash"])
        self.assertEqual(checks.check_package(self.manifest_path, self.run_dir), [])
        self.assertEqual(len(receipt["units"]), 3)
        for row in receipt["units"]:
            for key in checks.IDENTITY_KEYS:
                self.assertEqual(row[key], self.payload[key])
            self.assertEqual(row["approved_plan_hash"], self.payload["approval"]["hash"])
            self.assertEqual(row["lane_validation"]["state"], "passed")
            self.assertTrue(row["artifacts"])
            for art in row["artifacts"]:
                self.assertGreater(art["size"], 0)
            self.assertEqual(row["request"]["request_id"], row["request"]["request_id"])

    def test_a_boolean_only_receipt_fails(self):
        receipt = self.read_receipt()
        receipt["units"] = [True, False, True]
        self.write_receipt(receipt)
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-RECEIPT-UNITS") for f in fails), fails)

    def test_an_unsupported_receipt_schema_fails(self):
        receipt = self.read_receipt()
        receipt["schema_version"] = "0.9"
        self.write_receipt(receipt)
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-RECEIPT-SCHEMA") for f in fails), fails)

    def test_a_receipt_bound_to_another_launch_fails(self):
        receipt = self.read_receipt()
        receipt["launch_id"] = "someone-elses-launch"
        self.write_receipt(receipt)
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-RECEIPT-BINDING") for f in fails), fails)

    def test_a_receipt_for_another_approved_plan_hash_fails(self):
        receipt = self.read_receipt()
        receipt["approved_plan_hash"] = "d" * 64
        self.write_receipt(receipt)
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-RECEIPT-BINDING") for f in fails), fails)

    def test_a_missing_artifact_fails(self):
        receipt = self.read_receipt()
        target = self.run_dir / receipt["units"][0]["artifacts"][0]["path"]
        target.unlink()
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-ARTIFACT-MISSING") for f in fails), fails)

    def test_a_tampered_artifact_fails_its_hash(self):
        receipt = self.read_receipt()
        target = self.run_dir / receipt["units"][0]["artifacts"][0]["path"]
        target.write_text("tampered\n", encoding="utf-8")
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-HASH") for f in fails), fails)

    def test_a_zero_byte_artifact_never_proves_a_unit(self):
        receipt = self.read_receipt()
        row = receipt["units"][0]
        target = self.run_dir / row["artifacts"][0]["path"]
        target.write_bytes(b"")
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-ARTIFACT-EMPTY") for f in fails), fails)
        report = checks.verify_package_receipt(self.run_dir)
        self.assertEqual(report["state"], "failed")
        self.assertEqual(report["units"][row["unit_id"]], "failed")

    def test_forged_live_proof_on_a_draft_fails(self):
        receipt = self.read_receipt()
        receipt["units"][0]["proof"]["live_verified"] = True
        self.write_receipt(receipt)
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-RECEIPT-PROOF") for f in fails), fails)

    def test_a_live_label_with_no_live_effects_fails(self):
        receipt = self.read_receipt()
        row = receipt["units"][0]
        row["status"] = "live_verified"
        row["proof"] = {"authored": True, "draft_installed": True,
                        "tested": True, "live_verified": True}
        self.write_receipt(receipt)
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-RECEIPT-LIVE") for f in fails), fails)

    def test_recovery_verifies_a_clean_package_and_refuses_a_deleted_artifact(self):
        report = checks.verify_package_receipt(self.run_dir)
        self.assertEqual(report["state"], "verified")
        self.assertEqual(report["artifacts_checked"], 3)
        receipt = self.read_receipt()
        (self.run_dir / receipt["units"][1]["artifacts"][0]["path"]).unlink()
        report = checks.verify_package_receipt(self.run_dir)
        self.assertEqual(report["state"], "failed")
        self.assertEqual(report["units"][receipt["units"][1]["unit_id"]], "failed")

    def test_recovery_reports_absence_not_success(self):
        (self.run_dir / "receipt.json").unlink()
        report = checks.verify_package_receipt(self.run_dir)
        self.assertEqual(report["state"], "absent")
        self.assertTrue(report["violations"])

    def test_the_receipt_schema_matches_the_enforcement(self):
        schema = json.loads((SKILL_ROOT / "receipt.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema_version"]["const"],
                         package.RECEIPT_SCHEMA_VERSION)
        self.assertEqual(schema["properties"]["receipt_type"]["const"], package.RECEIPT_TYPE)
        self.assertEqual(tuple(schema["definitions"]["unit_receipt"]["required"]),
                         checks.RECEIPT_UNIT_KEYS)


@unittest.skipUnless(BF_PLAN.is_file(), "shared launch-plan contract fixture is not installed")
class PlannedUnitReceiptTests(_RunFixture):
    def setUp(self):
        self.plan = plan_fixture()
        super().setUp()

    def test_every_planned_unit_carries_a_typed_receipt(self):
        receipt = self.read_receipt()
        planned = {unit["id"] for unit in launch_plan.planned_units(self.plan)}
        self.assertEqual({row["unit_id"] for row in receipt["units"]}, planned)
        self.assertEqual(checks.check_package(self.manifest_path, self.run_dir), [])

    def test_draft_units_are_never_draft_installed_or_live(self):
        receipt = self.read_receipt()
        for row in receipt["units"]:
            if row["unit_type"] in ("email", "text", "automation"):
                self.assertIs(row.get("draft_only"), True, row["unit_id"])
                self.assertEqual(row["proof"], {"authored": True, "draft_installed": False,
                                                "tested": False, "live_verified": False})

    def test_a_missing_planned_unit_receipt_fails(self):
        receipt = self.read_receipt()
        dropped = receipt["units"].pop(0)["unit_id"]
        self.write_receipt(receipt)
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(dropped in f and "typed receipt" in f for f in fails), fails)

    def test_a_non_draft_unit_receipt_fails(self):
        receipt = self.read_receipt()
        for row in receipt["units"]:
            if row["unit_type"] == "email":
                row["draft_only"] = False
                break
        self.write_receipt(receipt)
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-RECEIPT-DRAFT") for f in fails), fails)

    def test_a_probe_verdict_the_contract_does_not_reproduce_fails(self):
        manifest = self.read_manifest()
        manifest["checkout"]["validator"]["probe"] = {"result": "accepted"}
        self.write_manifest(manifest)
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-CHECKOUT-VALIDATOR") for f in fails), fails)

    def test_a_smuggled_schema_version_in_the_inner_envelope_fails(self):
        manifest = self.read_manifest()
        manifest["checkout"]["supplied"]["schema_version"] = "0.2-draft"
        self.write_manifest(manifest)
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-CHECKOUT-VALIDATOR") for f in fails), fails)


if __name__ == "__main__":
    unittest.main(verbosity=2)
