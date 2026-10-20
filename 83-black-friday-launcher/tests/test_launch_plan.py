"""Black Friday calendar, planned-unit completeness, and the package/receipt law.

L1: Skill 83 adds the Black Friday calendar (teaser, countdown, doors open,
Cyber Monday, last call) from the shared U-CONTRACT launch plan.
L2: completeness fails when a planned email, text, automation or requested AI
is missing, and package/receipt assembly refuses to seal such a launch.
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


def plan_fixture() -> dict:
    return json.loads(BF_PLAN.read_text(encoding="utf-8"))


def base_intake() -> dict:
    return {
        "schema_version": "1.0",
        "tenant_id": "tenant-a",
        "location_id": "loc-a",
        "launch_id": "black-friday-2026",
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


def all_delivered(plan: dict, drop: str = "") -> dict:
    return {unit["id"]: {"state": "complete"}
            for unit in launch_plan.planned_units(plan) if unit["id"] != drop}


@unittest.skipUnless(BF_PLAN.is_file(), "shared launch-plan contract fixture is not installed")
class BlackFridayCalendarTests(unittest.TestCase):
    def test_calendar_carries_every_black_friday_phase_in_order(self):
        calendar = launch_plan.black_friday_calendar(plan_fixture())
        self.assertEqual([p["phase"] for p in calendar["phases"]],
                         ["teaser", "countdown", "doors_open", "cyber_monday",
                          "last_call", "doors_close"])
        self.assertEqual(calendar["black_friday_date"], "2026-11-27")
        self.assertEqual(calendar["timezone"], "America/New_York")

    def test_a_plan_without_the_black_friday_block_fails_closed(self):
        plan = plan_fixture()
        del plan["launch_calendar"]["black_friday"]
        with self.assertRaises(launch_plan.LaunchPlanError) as ctx:
            launch_plan.black_friday_calendar(plan)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-CALENDAR-MISSING")

    def test_a_deadline_that_moves_backwards_fails_closed(self):
        plan = plan_fixture()
        plan["launch_calendar"]["black_friday"]["last_call_at"] = "2026-12-02T20:00:00-05:00"
        with self.assertRaises(launch_plan.LaunchPlanError) as ctx:
            launch_plan.black_friday_calendar(plan)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-CALENDAR-ORDER")

    def test_a_zone_less_deadline_fails_closed(self):
        plan = plan_fixture()
        plan["launch_calendar"]["doors_open_at"] = "2026-11-27T00:00:00"
        with self.assertRaises(launch_plan.LaunchPlanError) as ctx:
            launch_plan.black_friday_calendar(plan)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-CALENDAR-TIME")


@unittest.skipUnless(BF_PLAN.is_file(), "shared launch-plan contract fixture is not installed")
class PlannedUnitCompletenessTests(unittest.TestCase):
    def test_every_planned_unit_is_listed(self):
        units = launch_plan.planned_units(plan_fixture())
        kinds = {u["type"] for u in units}
        self.assertEqual(kinds, {"page", "email", "text", "automation"})
        self.assertEqual(len(units), 25)  # 6 pages + 7 emails + 5 texts + 7 automations
        self.assertNotIn(launch_plan.AI_UNIT_ID, {u["id"] for u in units})

    def test_a_requested_conversation_ai_becomes_a_planned_unit(self):
        plan = plan_fixture()
        plan["conversation_ai"] = {"requested": True, "mode": "faq", "channels": ["sms"]}
        units = launch_plan.planned_units(plan)
        self.assertIn(launch_plan.AI_UNIT_ID, {u["id"] for u in units})
        self.assertEqual(len(units), 26)

    def test_complete_delivery_is_100_percent(self):
        plan = plan_fixture()
        result = launch_plan.completeness(plan, all_delivered(plan))
        self.assertTrue(result["complete"])
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["percentage"], 100)

    def test_a_missing_email_text_automation_or_requested_ai_fails(self):
        drops = {
            "email_doors_closing": "email",
            "text_last_call": "text",
            "auto_abandoned_checkout": "automation",
        }
        for unit_id, section in drops.items():
            with self.subTest(section=section):
                plan = plan_fixture()
                result = launch_plan.completeness(plan, all_delivered(plan, drop=unit_id))
                self.assertIn(unit_id, result["missing"])
                self.assertFalse(result["complete"])
                with self.assertRaises(launch_plan.LaunchPlanError) as ctx:
                    launch_plan.assert_complete(result)
                self.assertEqual(ctx.exception.code, "AF-LAUNCH-PLAN-MISSING")

        plan = plan_fixture()
        deliveries = all_delivered(plan)  # everything except the bot was delivered
        plan["conversation_ai"] = {"requested": True, "mode": "booking", "channels": ["sms"]}
        result = launch_plan.completeness(plan, deliveries)
        self.assertEqual(result["missing"], [launch_plan.AI_UNIT_ID])
        with self.assertRaises(launch_plan.LaunchPlanError):
            launch_plan.assert_complete(result)


@unittest.skipUnless(BF_PLAN.is_file(), "shared launch-plan contract fixture is not installed")
class PackagePlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run"
        self.normalized = intake.validate(base_intake())
        self.advice = council.planning_step(self.normalized, runner=stub_council)
        self.graph = route.compile_route(self.normalized, self.advice)
        self.pieces = pieces_for(self.run_dir, self.graph, self.normalized)
        self.plan = plan_fixture()

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_complete_plan_seals_the_package_and_receipt(self):
        out = package.assemble(self.run_dir, self.normalized, self.graph, self.pieces,
                               council=self.advice, launch_plan=self.plan,
                               deliveries=all_delivered(self.plan))
        manifest = out["manifest"]
        self.assertEqual(manifest["launch_plan"]["completeness"]["percentage"], 100)
        self.assertEqual(manifest["launch_plan"]["completeness"]["missing"], [])
        self.assertEqual(manifest["launch_calendar"]["black_friday_date"], "2026-11-27")
        self.assertEqual(out["receipt"]["launch_plan"]["completeness"]["percentage"], 100)
        self.assertTrue((self.run_dir / "launch-plan.json").is_file())
        self.assertTrue((self.run_dir / "launch-calendar.json").is_file())
        self.assertEqual(checks.check_package(Path(out["manifest_path"]), self.run_dir), [])

    def test_a_missing_planned_item_refuses_the_package(self):
        with self.assertRaises(package.PackageError) as ctx:
            package.assemble(self.run_dir, self.normalized, self.graph, self.pieces,
                             council=self.advice, launch_plan=self.plan,
                             deliveries=all_delivered(self.plan, drop="email_doors_closing"))
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PLAN-MISSING")
        self.assertIn("email_doors_closing", ctx.exception.detail)
        self.assertFalse((self.run_dir / "receipt.json").exists())

    def test_a_tampered_completeness_record_fails_the_check(self):
        out = package.assemble(self.run_dir, self.normalized, self.graph, self.pieces,
                               council=self.advice, launch_plan=self.plan,
                               deliveries=all_delivered(self.plan))
        manifest_path = Path(out["manifest_path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["launch_plan"]["completeness"]["units"] = [
            u for u in manifest["launch_plan"]["completeness"]["units"]
            if u["id"] != "text_last_call"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        fails = checks.check_package(manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-PLAN-MISSING") for f in fails), fails)

    def test_a_tampered_calendar_fails_the_check(self):
        out = package.assemble(self.run_dir, self.normalized, self.graph, self.pieces,
                               council=self.advice, launch_plan=self.plan,
                               deliveries=all_delivered(self.plan))
        calendar = self.run_dir / "launch-calendar.json"
        calendar.write_text("{}\n", encoding="utf-8")
        fails = checks.check_package(Path(out["manifest_path"]), self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-PLAN-CALENDAR") for f in fails), fails)

    def test_a_plan_for_another_launch_is_refused(self):
        plan = copy.deepcopy(self.plan)
        plan["launch_id"] = "some-other-launch"
        with self.assertRaises(package.PackageError) as ctx:
            package.assemble(self.run_dir, self.normalized, self.graph, self.pieces,
                             council=self.advice, launch_plan=plan,
                             deliveries=all_delivered(plan))
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PLAN-LAUNCH")


if __name__ == "__main__":
    unittest.main(verbosity=2)
