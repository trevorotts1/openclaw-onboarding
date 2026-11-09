"""S44-21 and CON-04: a delivered automation is a real Skill 44 build, and the launch plan
is the approved launch with the units a Black Friday launch is.

Before the fix a non-empty file plus three free-text strings (lane, contract, state) sealed
every automation as delivered, and a plan listing only pages reported 100% complete.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parent
BF_PLAN = REPO_ROOT / "shared-utils/signature_launch_contract/fixtures/black-friday.json"
CALENDAR_LAW = REPO_ROOT / "shared-utils/signature_launch_contract/calendar_law.py"

sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import constants, launch_plan  # noqa: E402
from launcher_core.check_rules import delivery_units as du  # noqa: E402

APPROVED = "b" * 64
GRAPH = {"workflowData": {"templates": [
    {"id": "n1", "type": "tag", "name": "Add tag", "parentKey": None, "next": "n2"},
    {"id": "n2", "type": "sms", "name": "Send SMS", "parentKey": "n1", "next": "n3"},
    {"id": "n3", "type": "end", "name": "End", "parentKey": "n2"},
]}}
ORPHANED = {"workflowData": {"templates": GRAPH["workflowData"]["templates"][:2]
                             + [{"id": "n9", "type": "end", "name": "Lost", "parentKey": None}]}}


def bound_plan() -> dict:
    plan = json.loads(BF_PLAN.read_text(encoding="utf-8"))
    plan.update(tenant_id="tenant-a", location_id="loc-a", revision=1, approved_plan_hash=APPROVED)
    return plan


def reader_hash(unit_id: str) -> str:
    return hashlib.sha256(f"reader:{unit_id}".encode()).hexdigest()


def with_skill44_builds(plan: dict, run_dir: Path, deliveries: dict) -> dict:
    """Swap each planned automation's delivery for a real Skill 44 build: the workflow export
    (artifact) plus the reader's automation-builds.json in the package root. Used by every
    test that assembles a full launch and expects `check` to pass."""
    builds = []
    for auto in plan.get("automations") or []:
        unit_id = auto["id"]
        body = {"workflow_id": f"wf-{unit_id}", "status": "draft", "produced_by": du.BUILD_COMMAND,
                "unit_key": f"{plan['launch_id']}/{unit_id}",
                "expected_graph_hash": reader_hash(unit_id), **GRAPH}
        rel = f"automations/{unit_id}.json"
        raw = write(Path(run_dir) / rel, body)
        deliveries[unit_id] = {**deliveries.get(unit_id, {"state": "complete"}),
                               "artifacts": [{"path": rel, "sha256": hashlib.sha256(raw).hexdigest(),
                                              "size": len(raw)}],
                               "lane_validation": {"lane": "S44", "contract": du.EXPORT_CONTRACT,
                                                   "state": "passed"}}
        builds.append({"id": unit_id, "state": "ready", "expected_graph_hash": reader_hash(unit_id)})
    write(Path(run_dir) / du.BUILDS_DOC, {"launch_id": plan["launch_id"], "builds": builds})
    return deliveries


def write(path: Path, data) -> bytes:
    raw = data if isinstance(data, bytes) else json.dumps(data, indent=2).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


@unittest.skipUnless(BF_PLAN.is_file(), "shared launch-plan contract fixture is not installed")
class DeliveryUnitsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.plan = bound_plan()
        self.intake = {"tenant_id": "tenant-a", "location_id": "loc-a", "launch_id": self.plan["launch_id"],
                       "revision": 1, "approval": {"ref": "approval-1", "hash": APPROVED}}
        self.automations = [a["id"] for a in self.plan["automations"]]

    def tearDown(self):
        self.tmp.cleanup()

    def export(self, unit_id, graph=GRAPH, **override) -> dict:
        body = {"workflow_id": f"wf-{unit_id}", "status": "draft", "produced_by": du.BUILD_COMMAND,
                "unit_key": f"{self.plan['launch_id']}/{unit_id}",
                "expected_graph_hash": reader_hash(unit_id), **graph, **override}
        rel = f"automations/{unit_id}.json"
        raw = write(self.root / rel, body)
        return {"unit_id": unit_id, "unit_type": "automation",
                "artifacts": [{"path": rel, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}],
                "lane_validation": {"lane": "S44", "contract": du.EXPORT_CONTRACT, "state": "passed"}}

    def package(self, plan=None, intake=None, rows=None) -> dict:
        """Write a package root and return its manifest; rows default to real Skill 44 builds."""
        plan = plan or self.plan
        rows = [self.export(u) for u in self.automations] if rows is None else rows
        write(self.root / "launch-plan.json", plan)
        write(self.root / "intake.json", intake or self.intake)
        write(self.root / du.BUILDS_DOC, {"launch_id": plan["launch_id"], "builds": [
            {"id": u, "state": "ready", "expected_graph_hash": reader_hash(u)} for u in self.automations]})
        write(self.root / "receipt.json", {"units": rows})
        return {"tenant_id": "tenant-a", "location_id": "loc-a", "launch_id": self.intake["launch_id"],
                "revision": 1, "approved_plan_hash": APPROVED,
                "intake": {"path": "intake.json"}, "launch_plan": {"plan": {"path": "launch-plan.json"}}}

    def check(self, manifest) -> list:
        return du.violations(manifest, self.root, SKILL_ROOT)

    # ---- S44-21: what counts as a delivered automation -------------------------------
    def test_real_skill44_builds_pass(self):
        self.assertEqual(self.check(self.package()), [])

    def test_a_non_empty_file_and_three_strings_is_not_a_delivered_automation(self):
        raw = write(self.root / "done.txt", b"done\n")
        fake = [{"unit_id": u, "unit_type": "automation",
                 "artifacts": [{"path": "done.txt", "sha256": hashlib.sha256(raw).hexdigest(), "size": 5}],
                 "lane_validation": {"lane": "s44", "contract": "x", "state": "passed"}}
                for u in self.automations]
        fails = self.check(self.package(rows=fake))
        self.assertEqual(len([f for f in fails if f.startswith(du.CODE_AUTOMATION)]), len(self.automations))

    def test_the_export_must_carry_the_readers_hash_a_draft_status_and_its_own_unit_key(self):
        unit = self.automations[0]
        for label, override in (("hash", {"expected_graph_hash": "f" * 64}),
                                ("status", {"status": "published"}),
                                ("unit_key", {"unit_key": "black-friday-2026/auto_other"}),
                                ("workflow_id", {"workflow_id": ""}),
                                ("builder", {"produced_by": "hand-written"})):
            with self.subTest(label):
                rows = [self.export(u, **(override if u == unit else {})) for u in self.automations]
                fails = self.check(self.package(rows=rows))
                self.assertEqual(len(fails), 1, fails)
                self.assertIn(unit, fails[0])

    def test_the_skill44_graph_validator_must_pass_the_export(self):
        unit = self.automations[0]
        rows = [self.export(u, graph=ORPHANED if u == unit else GRAPH) for u in self.automations]
        fails = self.check(self.package(rows=rows))
        self.assertEqual(len(fails), 1, fails)
        self.assertIn("graph validator refused", fails[0])

    def test_a_tampered_export_or_a_missing_reader_document_fails(self):
        manifest = self.package()
        (self.root / "automations" / f"{self.automations[0]}.json").write_bytes(b"{}")
        self.assertTrue(any("sha256" in f for f in self.check(manifest)))
        manifest = self.package()
        (self.root / du.BUILDS_DOC).unlink()
        self.assertEqual(len(self.check(manifest)), len(self.automations))

    def test_the_validator_is_found_in_a_deployed_layout_and_never_assumed_when_absent(self):
        # A 999 install has no 44- directory: the validator lives in .claude/skills/convert-and-flow-operator.
        deployed = Path(tempfile.mkdtemp(dir=self.root))
        (deployed / "shared-utils").mkdir()
        skill = deployed / ".claude" / "skills" / "convert-and-flow-operator"
        (skill / "tools").mkdir(parents=True)
        (skill / "SKILL.md").write_text("# fixture\n", encoding="utf-8")
        manifest = self.package()
        with mock.patch.object(constants, "REPO_ROOT", deployed):
            absent = self.check(manifest)  # fail closed, named: not installed
            shutil.copy(REPO_ROOT / du.VALIDATOR_REF, skill / "tools" / "validate_graph.py")
            found = self.check(manifest)
        self.assertEqual(len(absent), len(self.automations), absent)
        self.assertTrue(all("is not installed" in f for f in absent), absent)
        self.assertEqual(found, [])

    def test_the_rule_loads_the_way_the_check_rules_seam_loads_it(self):
        # U-launcher-core-02's seam loads every check_rules/*.py BY PATH under the name
        # launcher_core.check_rules.<stem>; the relative imports must resolve that way too.
        path = SKILL_ROOT / "launcher_core/check_rules/delivery_units.py"
        spec = importlib.util.spec_from_file_location("launcher_core.check_rules.delivery_units", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.violations(self.package(), self.root, SKILL_ROOT), [])
        thin = {**self.plan, "approved_plan_hash": "c" * 64}
        self.assertTrue(any(f.startswith("AF-LAUNCH-PLAN-BIND")
                            for f in module.violations(self.package(plan=thin), self.root, SKILL_ROOT)))

    # ---- CON-04: the plan is the approved launch, with the units a BF launch is ------
    def test_a_plan_that_differs_from_the_dispatched_launch_fails(self):
        for key, value in (("launch_id", "black-friday-2099"), ("tenant_id", "tenant-b"),
                           ("location_id", "loc-b"), ("revision", 2), ("approved_plan_hash", "c" * 64)):
            with self.subTest(key):
                plan = {**self.plan, key: value}
                fails = self.check(self.package(plan=plan))
                self.assertTrue(any(f.startswith("AF-LAUNCH-PLAN-BIND") and key in f for f in fails), fails)

    def test_a_plan_with_no_binding_fields_fails(self):
        plan = {k: v for k, v in self.plan.items() if k not in ("tenant_id", "approved_plan_hash")}
        fails = self.check(self.package(plan=plan))
        self.assertTrue(any("tenant_id" in f for f in fails) and any("approved_plan_hash" in f for f in fails))

    def test_zero_email_or_zero_automation_units_fails_without_a_recorded_choice(self):
        for sections in (("email_sequences",), ("automations",), ("email_sequences", "automations")):
            with self.subTest(sections):
                plan = {**self.plan, **{s: [] for s in sections}}
                plan["automations"] = [] if "automations" in sections else [
                    {**a, "waits_for": []} for a in self.plan["automations"]]
                plan["pages"] = copy.deepcopy(self.plan["pages"])
                fails = self.check(self.package(plan=plan, rows=[]))
                self.assertTrue(any(f.startswith("AF-LAUNCH-PLAN-SCOPE") for f in fails), fails)

    def test_a_choice_the_intake_recorded_waives_only_what_it_names(self):
        plan = {**self.plan, "automations": []}
        plan["text_sets"] = [{**t, "waits_for": [w for w in t.get("waits_for", []) if not w.startswith("auto_")]}
                             for t in plan["text_sets"]]
        scoped = lambda intake: [f for f in self.check(self.package(plan=plan, intake=intake, rows=[]))
                                 if f.startswith("AF-LAUNCH-PLAN-SCOPE")]
        self.assertTrue(scoped(self.intake))
        self.assertEqual(scoped({**self.intake, "client_choices": ["email_only"]}), [])
        self.assertTrue(scoped({**self.intake, "client_choices": ["no_email_sequences"]}))

    def test_assemble_time_record_refuses_by_name(self):
        thin = {**self.plan, "email_sequences": [], "automations": []}
        thin["text_sets"] = [{**t, "waits_for": []} for t in self.plan["text_sets"]]
        for plan, intake, code in (
                (thin, None, "AF-LAUNCH-PLAN-SCOPE"),
                (thin, self.intake, "AF-LAUNCH-PLAN-SCOPE"),
                ({**self.plan, "approved_plan_hash": "c" * 64}, self.intake, "AF-LAUNCH-PLAN-BIND"),
                ({**self.plan, "tenant_id": "tenant-b"}, self.intake, "AF-LAUNCH-PLAN-BIND")):
            with self.subTest(code=code):
                with self.assertRaises(launch_plan.LaunchPlanError) as ctx:
                    launch_plan.record(plan, {}, intake)
                self.assertEqual(ctx.exception.code, code)
        record = launch_plan.record(self.plan, {}, self.intake)  # bound plan: refuses only on delivery
        self.assertFalse(record["completeness"]["complete"])


@unittest.skipUnless(BF_PLAN.is_file() and CALENDAR_LAW.is_file(), "shared calendar law is not installed")
class SharedCalendarLawTests(unittest.TestCase):
    def test_launch_plan_judges_the_calendar_by_the_shared_law(self):
        self.assertIsNotNone(launch_plan._calendar_law())
        plan = bound_plan()
        self.assertTrue(launch_plan.black_friday_calendar(plan))
        for key, value in (("teaser_at", plan["launch_calendar"]["black_friday"]["countdown_at"]),
                           ("last_call_at", plan["launch_calendar"]["doors_close_at"])):
            with self.subTest(key):
                broken = copy.deepcopy(plan)
                broken["launch_calendar"]["black_friday"][key] = value  # teaser == countdown; last call == close
                with self.assertRaises(launch_plan.LaunchPlanError) as ctx:
                    launch_plan.black_friday_calendar(broken)
                self.assertEqual(ctx.exception.code, "AF-LAUNCH-CALENDAR-ORDER")


if __name__ == "__main__":
    unittest.main(verbosity=2)
