"""Issue 1 (83 side) and issue 33: every enforcement line of the lane-delivery and QC law, one clause at a time.

``test_lane_receipts`` and ``test_delivery_units`` prove the laws through a whole assembled package, which is
slow. These tests call each rule directly, so a mutation sweep that flips any single clause of the contract
allow-list, the email re-check, the check-time loop or the per-build QC fields is killed in seconds. The
contract ids and the validator path are literals here on purpose (a wrong constant in the rule cannot hide).
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import lane83_stand_in_validate_delivery as stand_in  # noqa: E402
from launcher_core import constants  # noqa: E402
from launcher_core.check_rules import delivery_units as du  # noqa: E402
from test_delivery_units import (ABSENT, APPROVED, EMAIL_VALIDATOR_PATH,  # noqa: E402
                                 LANE_CONTRACT_IDS, bound_plan, install_stand_in_validator, qc_result, write)

CODE = "AF-LAUNCH-PKG-RECEIPT-LANE"
EMAIL, TEXT, AUTO = (LANE_CONTRACT_IDS[k] for k in ("email", "text", "automation"))
EXPECTED = {"email": EMAIL, "text": TEXT, "automation": AUTO, "page": None, "conversation_ai": None}
LANE = {"lane": "L", "state": "passed"}


class ContractAllowListTests(unittest.TestCase):
    def test_each_unit_type_accepts_exactly_its_producers_contract(self):
        for unit_type, expected in EXPECTED.items():
            for contract in (EMAIL, TEXT, AUTO, "x", "", None):
                with self.subTest(unit_type=unit_type, contract=contract):
                    fails = du.lane_contract_violations("u1", unit_type, {**LANE, "contract": contract})
                    if contract is not None and contract == expected:
                        self.assertEqual(fails, [])
                    else:
                        self.assertEqual(len(fails), 1, fails)
                        self.assertTrue(fails[0].startswith(f"{CODE}: unit 'u1'"), fails)

    def test_a_lane_with_no_contract_is_named_as_having_none(self):
        for lane in (None, {}, {"lane": "L", "state": "passed"}, {"contract": None}, "passed"):
            with self.subTest(lane=lane):
                fails = du.lane_contract_violations("u1", "email", lane)
                self.assertEqual(len(fails), 1, fails)
                self.assertIn(f"lane_validation contract None is not {EMAIL!r}", fails[0])

    def test_the_lane_document_of_a_bare_row_is_the_bare_document(self):
        self.assertEqual(du.lane_document("u1", {}), {"state": "complete", "unit": "u1", "artifacts": None,
                                                      "lane_validation": None, "request": None})

    def test_a_missing_or_malformed_lane_validation_is_a_refusal_not_a_crash(self):
        for unit_type in EXPECTED:
            for lane in (None, "passed", [], 7, {}):
                with self.subTest(unit_type=unit_type, lane=lane):
                    self.assertEqual(len(du.lane_contract_violations("u1", unit_type, lane)), 1)

    def test_the_allow_list_names_the_producers_contract_and_no_producer_is_said_so(self):
        for unit_type in ("email", "text", "automation"):
            fails = du.lane_contract_violations("u1", unit_type, {**LANE, "contract": "x"})
            self.assertIn(repr(EXPECTED[unit_type]), fails[0])
            self.assertNotIn("no producer yet", fails[0])
        for unit_type in ("page", "conversation_ai", "other"):
            fails = du.lane_contract_violations("u1", unit_type, {**LANE, "contract": "x"})
            self.assertIn("no producer yet", fails[0])

    def test_the_table_is_exactly_the_spec_table(self):
        self.assertEqual((du.CODE_LANE, du.CODE_PLAN, du.CODE_AUTOMATION),
                         (CODE, "AF-LAUNCH-UNIT-PLAN", "AF-LAUNCH-UNIT-AUTOMATION"))
        self.assertEqual(du.LANE_CONTRACTS, {"email": (EMAIL,), "text": (TEXT,), "automation": (AUTO,),
                                             "page": (), "conversation_ai": ()})


class EmailRecheckTests(unittest.TestCase):
    """Skill 50's validate_delivery.py --check, run by path from the package folder."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "pkg"
        self.root.mkdir()
        raw = b"<html>email</html>\n"
        (self.root / "e.html").write_bytes(raw)
        self.arts = [{"path": "e.html", "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}]
        self.doc = {"state": "complete", "unit": "email_a", "artifacts": self.arts, "request": {"x": 1},
                    "lane_validation": {**LANE, "contract": EMAIL, "certificate_sha256": stand_in.certificate(self.arts)}}

    def leftovers(self):
        return sorted(p.name for p in self.root.glob(".lane-check-*"))

    def use_validator(self, path):
        real = constants.resolve_ref
        patcher = mock.patch.object(constants, "resolve_ref",
                                    lambda rel, root=None: path if rel == EMAIL_VALIDATOR_PATH else real(rel, root))
        patcher.start()
        self.addCleanup(patcher.stop)

    def script(self, body):
        path = Path(self.tmp.name) / "validator.py"
        path.write_text(body, encoding="utf-8")
        self.use_validator(path)
        return path

    def test_the_stand_in_accepts_a_good_document_and_refuses_each_break(self):
        install_stand_in_validator(self)
        self.assertEqual(du.email_delivery_violations("email_a", self.doc, self.root), [])
        self.assertEqual(self.leftovers(), [])
        bad = copy.deepcopy(self.doc)
        bad["lane_validation"]["certificate_sha256"] = "0" * 64
        fails = du.email_delivery_violations("email_a", bad, self.root)
        self.assertEqual(len(fails), 1)
        self.assertTrue(fails[0].startswith(CODE) and "email_a" in fails[0] and "refused the receipt (exit 1)" in fails[0])
        self.assertEqual(self.leftovers(), [])
        (self.root / "e.html").write_bytes(b"changed\n")
        self.assertEqual(len(du.email_delivery_violations("email_a", self.doc, self.root)), 1)

    def test_every_non_zero_exit_status_is_a_refusal(self):
        for status in (1, 2, 3, 100, 255):
            with self.subTest(status=status):
                self.script(f"import sys\nsys.exit({status})\n")
                fails = du.email_delivery_violations("email_a", self.doc, self.root)
                self.assertEqual(len(fails), 1, fails)
                self.assertIn(f"(exit {status})", fails[0])
                self.assertEqual(self.leftovers(), [])

    def test_the_validator_is_run_isolated_with_check_from_the_package_folder_on_the_document(self):
        log = self.root / "probe.json"
        self.script(
            "import json, os, sys\n"
            f"doc = json.load(open(sys.argv[2]))\n"
            f"json.dump({{'argv1': sys.argv[1], 'argc': len(sys.argv), 'isolated': sys.flags.isolated, "
            f"'cwd': os.path.realpath(os.getcwd()), 'dir': os.path.realpath(os.path.dirname(os.path.abspath(sys.argv[2]))), "
            f"'name': os.path.basename(sys.argv[2]), 'doc': doc}}, open({str(log)!r}, 'w'))\n")
        self.assertEqual(du.email_delivery_violations("email_a", self.doc, self.root), [])
        seen = json.loads(log.read_text(encoding="utf-8"))
        root = str(self.root.resolve())
        self.assertEqual((seen["argv1"], seen["argc"], seen["isolated"]), ("--check", 3, 1))
        self.assertEqual(seen["cwd"], root)
        self.assertEqual(seen["dir"], root)
        self.assertTrue(seen["name"].startswith(".lane-check-") and seen["name"].endswith(".json"))
        self.assertEqual(seen["doc"], self.doc)
        self.assertEqual(self.leftovers(), [])

    def test_a_validator_that_never_returns_or_cannot_start_is_a_refusal(self):
        install_stand_in_validator(self)
        for exc in (OSError("no interpreter"), ValueError("bad"), subprocess.TimeoutExpired("v", 1),
                    subprocess.SubprocessError("boom")):
            with self.subTest(exc=type(exc).__name__):
                with mock.patch.object(du.subprocess, "run", side_effect=exc):
                    fails = du.email_delivery_violations("email_a", self.doc, self.root)
                self.assertEqual(len(fails), 1, fails)
                self.assertIn("could not run", fails[0])
                self.assertEqual(self.leftovers(), [])

    def test_the_timeout_is_passed_and_bounded(self):
        install_stand_in_validator(self)
        real = subprocess.run
        seen = {}

        def spy(*args, **kwargs):
            seen.update(kwargs)
            return real(*args, **kwargs)

        with mock.patch.object(du.subprocess, "run", spy):
            du.email_delivery_violations("email_a", self.doc, self.root)
        self.assertEqual(seen["timeout"], du.VALIDATOR_TIMEOUT_S)
        self.assertEqual(Path(seen["cwd"]).resolve(), self.root.resolve())
        self.assertTrue(seen["capture_output"])

    def test_an_unwritable_package_folder_is_a_refusal(self):
        install_stand_in_validator(self)
        with mock.patch.object(du.tempfile, "mkstemp", side_effect=OSError("read-only")):
            fails = du.email_delivery_violations("email_a", self.doc, self.root)
        self.assertEqual(len(fails), 1)
        self.assertIn("not writable", fails[0])

    def test_an_absent_validator_is_a_refusal_in_both_ways_it_can_be_absent(self):
        real = constants.resolve_ref

        def gone(rel, root=None):
            if rel == EMAIL_VALIDATOR_PATH:
                raise constants.SkillResolutionError("no email-engine tree")
            return real(rel, root)

        with mock.patch.object(constants, "resolve_ref", gone):
            fails = du.email_delivery_violations("email_a", self.doc, self.root)
        self.assertEqual(len(fails), 1)
        self.assertIn("is not installed", fails[0])
        self.use_validator(Path(self.tmp.name) / "nowhere" / "validate_delivery.py")
        fails = du.email_delivery_violations("email_a", self.doc, self.root)
        self.assertEqual(len(fails), 1)
        self.assertIn("is not installed", fails[0])
        self.assertEqual(self.leftovers(), [])

    def test_the_temporary_document_is_removed_even_when_the_validator_fails(self):
        self.script("import sys\nsys.exit(4)\n")
        du.email_delivery_violations("email_a", self.doc, self.root)
        self.assertEqual(self.leftovers(), [])

    def test_the_lane_document_carries_the_rows_own_artifacts_validation_and_request(self):
        row = {"artifacts": self.arts, "lane_validation": self.doc["lane_validation"], "request": {"x": 1},
               "unit_id": "ignored"}
        self.assertEqual(du.lane_document("email_a", row), self.doc)

    def test_the_row_law_runs_the_recheck_for_email_only_and_only_after_the_contract_holds(self):
        install_stand_in_validator(self)
        row = {"artifacts": self.arts, "lane_validation": self.doc["lane_validation"], "request": {}}
        self.assertEqual(du.row_lane_violations("email_a", "email", row, self.root), [])
        broken = {**row, "lane_validation": {**row["lane_validation"], "certificate_sha256": "0" * 64}}
        self.assertEqual(len(du.row_lane_violations("email_a", "email", broken, self.root)), 1)
        wrong = {**row, "lane_validation": {**row["lane_validation"], "contract": TEXT}}
        with mock.patch.object(du, "email_delivery_violations", side_effect=AssertionError("must not run")):
            fails = du.row_lane_violations("email_a", "email", wrong, self.root)
            self.assertEqual(len(fails), 1)
            self.assertIn(repr(EMAIL), fails[0])
            text_row = {**row, "lane_validation": {**LANE, "contract": TEXT}}
            self.assertEqual(du.row_lane_violations("text_a", "text", text_row, self.root), [])
            email_on_text = {**row, "lane_validation": {**LANE, "contract": EMAIL}}
            self.assertEqual(len(du.row_lane_violations("text_a", "text", email_on_text, self.root)), 1)


class CheckTimeLoopTests(unittest.TestCase):
    """du.violations on a sealed package: which receipt rows the lane law judges."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        install_stand_in_validator(self)
        self.root = Path(self.tmp.name)
        self.plan = bound_plan()
        self.intake = {"tenant_id": "tenant-a", "location_id": "loc-a", "launch_id": self.plan["launch_id"],
                       "revision": 1, "approval": {"ref": "approval-1", "hash": APPROVED}}
        raw = write(self.root / "lane" / "a.html", b"<html>a</html>\n")
        self.arts = [{"path": "lane/a.html", "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}]

    def row(self, unit_id, unit_type, contract, **more):
        lane = {**LANE, "contract": contract}
        if unit_type == "email":
            lane["certificate_sha256"] = stand_in.certificate(self.arts)
        return {"unit_id": unit_id, "unit_type": unit_type, "artifacts": self.arts, "lane_validation": lane,
                "request": {}, **more}

    def manifest(self, rows, plan=None):
        plan = plan or self.plan
        write(self.root / "launch-plan.json", plan)
        write(self.root / "intake.json", self.intake)
        write(self.root / du.BUILDS_DOC, {"launch_id": plan["launch_id"], "builds": []})
        write(self.root / "receipt.json", {"units": rows})
        return {"tenant_id": "tenant-a", "location_id": "loc-a", "launch_id": plan["launch_id"], "revision": 1,
                "approved_plan_hash": APPROVED, "intake": {"path": "intake.json"},
                "launch_plan": {"plan": {"path": "launch-plan.json"}}}

    def lane_fails(self, rows, plan=None):
        return [f for f in du.violations(self.manifest(rows, plan), self.root, SKILL_ROOT) if f.startswith(CODE)]

    def no_automation_plan(self):
        plan = copy.deepcopy(self.plan)
        plan["automations"] = []
        plan["text_sets"] = [{**t, "waits_for": [w for w in t.get("waits_for", []) if not w.startswith("auto_")]}
                             for t in plan["text_sets"]]
        return plan

    def test_the_producers_own_rows_are_clean(self):
        rows = [self.row("email_pre_launch", "email", EMAIL), self.row("text_doors_open", "text", TEXT)]
        self.assertEqual(self.lane_fails(rows), [])

    def test_a_typed_contract_on_an_email_or_a_text_row_is_named(self):
        for unit_id, unit_type, bad in (("email_pre_launch", "email", "typed"), ("email_pre_launch", "email", TEXT),
                                        ("text_doors_open", "text", "typed"), ("text_doors_open", "text", EMAIL)):
            with self.subTest(unit_id=unit_id, contract=bad):
                fails = self.lane_fails([self.row(unit_id, unit_type, bad)])
                self.assertEqual(len(fails), 1, fails)
                self.assertIn(unit_id, fails[0])

    def test_an_email_row_the_validator_refuses_is_named(self):
        row = self.row("email_pre_launch", "email", EMAIL)
        row["lane_validation"]["certificate_sha256"] = "0" * 64
        fails = self.lane_fails([row])
        self.assertEqual(len(fails), 1)
        self.assertIn("refused the receipt", fails[0])

    def test_the_text_row_is_not_re_run_through_the_email_validator(self):
        with mock.patch.object(du, "email_delivery_violations", side_effect=AssertionError("email only")):
            self.assertEqual(self.lane_fails([self.row("text_doors_open", "text", TEXT)]), [])

    def test_a_page_another_lane_declared_is_refused_whatever_it_carries(self):
        for contract in (TEXT, EMAIL, AUTO, "typed"):
            with self.subTest(contract=contract):
                fails = self.lane_fails([self.row("page_sales", "page", contract, delivery="declared")])
                self.assertEqual(len(fails), 1, fails)
                self.assertIn("page_sales", fails[0])
                self.assertIn("no producer yet", fails[0])

    def test_a_page_the_launcher_built_is_not_judged_by_the_lane_law(self):
        for marker in ({}, {"delivery": "launcher"}, {"delivery": None}):
            with self.subTest(marker=marker):
                self.assertEqual(self.lane_fails([self.row("page_sales", "page", "typed", **marker)]), [])

    def test_a_conversation_ai_row_is_refused_whatever_it_carries(self):
        plan = copy.deepcopy(self.plan)
        plan["conversation_ai"] = {"requested": True, "mode": "faq", "channels": ["sms"]}
        for contract in (EMAIL, TEXT, AUTO, "typed"):
            with self.subTest(contract=contract):
                fails = self.lane_fails([self.row("conversation_ai", "conversation_ai", contract)], plan)
                self.assertEqual(len(fails), 1, fails)
                self.assertIn("conversation_ai", fails[0])
                self.assertIn("no producer yet", fails[0])

    def test_lane_units_are_judged_when_the_plan_has_no_automation(self):
        plan = self.no_automation_plan()
        fails = self.lane_fails([self.row("email_pre_launch", "email", "typed")], plan)
        self.assertEqual(len(fails), 1, fails)
        self.assertIn("email_pre_launch", fails[0])

    def test_automations_are_judged_when_the_plan_has_nothing_but_automations(self):
        plan = copy.deepcopy(self.plan)
        for section in ("pages", "email_sequences", "text_sets"):
            plan[section] = []
        for automation in plan["automations"]:
            automation["waits_for"] = []
        fails = du.violations(self.manifest([], plan), self.root, SKILL_ROOT)
        named = [f for f in fails if f.startswith(du.CODE_AUTOMATION)]
        self.assertEqual(len(named), len(plan["automations"]), fails)

    def test_a_planned_unit_with_no_row_or_a_row_that_is_not_an_object_is_not_this_rules_to_name(self):
        self.assertEqual(self.lane_fails([]), [])
        manifest = self.manifest([])
        write(self.root / "receipt.json", {"units": ["email_pre_launch", None, 4]})
        self.assertEqual([f for f in du.violations(manifest, self.root, SKILL_ROOT) if f.startswith(CODE)], [])

    def test_every_lane_row_is_judged_and_all_failures_are_returned(self):
        rows = [self.row("email_pre_launch", "email", "typed"), self.row("email_main_launch", "email", "typed"),
                self.row("text_doors_open", "text", "typed"), self.row("text_last_call", "text", "typed"),
                self.row("page_sales", "page", "typed", delivery="declared")]
        fails = self.lane_fails(rows)
        self.assertEqual(len(fails), 5, fails)


class QcFieldTests(unittest.TestCase):
    """du.qc_violations: the saved qc-<workflow_id>.json must be the passing result for exactly this workflow."""

    WF = "wf-1"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def artifact(self, doc=None, rel="qc-wf-1.json", raw=None, **art):
        if raw is None:
            raw = json.dumps(doc if doc is not None else qc_result(self.WF)).encode()
        write(self.root / rel, raw)
        return {"path": rel, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw), **art}

    def judge(self, artifacts):
        return du.qc_violations("unit X", self.WF, artifacts, self.root)

    def test_the_passing_result_is_clean(self):
        self.assertEqual(self.judge([self.artifact()]), [])

    def test_extra_keys_and_a_nested_folder_do_not_matter(self):
        self.assertEqual(self.judge([self.artifact(qc_result(self.WF, extra="x"), rel="deep/er/qc-wf-1.json")]), [])

    def test_each_failing_field_is_named_alone(self):
        cases = {
            "workflow_id": [{"workflow_id": "wf-other"}, {"workflow_id": ABSENT}, {"workflow_id": ""},
                            {"workflow_id": None}, {"workflow_id": "WF-1"}],
            "exit_code": [{"exit_code": 1}, {"exit_code": 2}, {"exit_code": -1}, {"exit_code": ABSENT},
                          {"exit_code": None}, {"exit_code": True}, {"exit_code": False}, {"exit_code": "0"},
                          {"exit_code": 0.0}],
            "exit_gate": [{"exit_gate": "FAIL"}, {"exit_gate": "UNGRADED"}, {"exit_gate": ABSENT},
                          {"exit_gate": "pass"}, {"exit_gate": None}, {"exit_gate": True}],
            "overall_mechanical": [{"overall_mechanical": "FAIL"}, {"overall_mechanical": ABSENT},
                                   {"overall_mechanical": "pass"}, {"overall_mechanical": None}],
            "plan_mode_gate.status": [{"plan_mode_gate": {"status": "FAIL"}}, {"plan_mode_gate": {}},
                                      {"plan_mode_gate": None}, {"plan_mode_gate": ABSENT},
                                      {"plan_mode_gate": "PASS"}, {"plan_mode_gate": ["PASS"]},
                                      {"plan_mode_gate": {"status": "pass"}}, {"plan_mode_gate": {"status": None}}],
        }
        for field, overrides in cases.items():
            for override in overrides:
                with self.subTest(field=field, override=override):
                    fails = self.judge([self.artifact(qc_result(self.WF, **override))])
                    self.assertEqual(len(fails), 1, fails)
                    self.assertIn("QC did not pass", fails[0])
                    self.assertIn(field, fails[0])
                    others = {"workflow_id", "exit_code", "exit_gate", "overall_mechanical",
                              "plan_mode_gate.status"} - {field}
                    self.assertFalse([o for o in others if o in fails[0]], fails[0])

    def test_a_gate_that_is_not_an_object_is_named_by_what_it_was(self):
        for override, said in (({"plan_mode_gate": ABSENT}, "plan_mode_gate.status is None"),
                               ({"plan_mode_gate": "PASS"}, "plan_mode_gate.status is 'PASS'"),
                               ({"plan_mode_gate": ["PASS"]}, "plan_mode_gate.status is ['PASS']"),
                               ({"plan_mode_gate": {}}, "plan_mode_gate.status is None"),
                               ({"plan_mode_gate": {"status": "FAIL"}}, "plan_mode_gate.status is 'FAIL'")):
            with self.subTest(override=override):
                fails = self.judge([self.artifact(qc_result(self.WF, **override))])
                self.assertEqual(len(fails), 1, fails)
                self.assertIn(said, fails[0])

    def test_each_refusal_says_what_the_field_was_and_what_it_must_be(self):
        for key, want in (("workflow_id", None), ("exit_code", 0), ("exit_gate", "PASS"), ("overall_mechanical", "PASS")):
            with self.subTest(key=key, how="absent"):
                fails = self.judge([self.artifact(qc_result(self.WF, **{key: ABSENT}))])
                self.assertEqual(len(fails), 1, fails)
                self.assertIn(f"{key} is None", fails[0])
        for override, said in (({"workflow_id": "wf-z"}, "workflow_id is 'wf-z', not 'wf-1'"),
                               ({"exit_code": 1}, "exit_code is 1, not 0"),
                               ({"exit_gate": "FAIL"}, "exit_gate is 'FAIL', not 'PASS'"),
                               ({"overall_mechanical": "FAIL"}, "overall_mechanical is 'FAIL', not 'PASS'")):
            with self.subTest(override=override):
                fails = self.judge([self.artifact(qc_result(self.WF, **override))])
                self.assertIn(said, fails[0])

    def test_everything_wrong_at_once_names_every_field(self):
        fails = self.judge([self.artifact({"workflow_id": "wf-z", "exit_code": 9, "exit_gate": "FAIL",
                                           "overall_mechanical": "FAIL", "plan_mode_gate": {"status": "FAIL"}})])
        self.assertEqual(len(fails), 1)
        for field in ("workflow_id", "exit_code", "exit_gate", "overall_mechanical", "plan_mode_gate.status"):
            self.assertIn(field, fails[0])
        self.assertEqual(fails[0].count("; "), 4, fails[0])

    def test_a_missing_result_or_one_named_for_another_workflow_is_refused(self):
        for artifacts in ([], [self.artifact(rel="qc-wf-other.json")], [self.artifact(rel="qc-wf-1.txt")],
                          [self.artifact(rel="xqc-wf-1.json")]):
            with self.subTest(artifacts=[a["path"] for a in artifacts]):
                fails = self.judge(artifacts)
                self.assertEqual(len(fails), 1, fails)
                self.assertIn("carries no qc-wf-1.json artifact", fails[0])

    def test_artifact_rows_that_are_not_objects_or_have_no_path_are_skipped_not_crashed_on(self):
        self.assertEqual(self.judge([None, "x", {"path": 5}, {"nopath": 1}, self.artifact()]), [])
        self.assertIn("carries no", self.judge([None, "x", {"path": 5}])[0])

    def test_a_result_outside_the_package_or_absent_on_disk_is_refused(self):
        outside = self.root.parent / "qc-wf-1.json"
        raw = json.dumps(qc_result(self.WF)).encode()
        outside.write_bytes(raw)
        self.addCleanup(lambda: outside.unlink() if outside.exists() else None)
        sha = hashlib.sha256(raw).hexdigest()
        for path in ("../qc-wf-1.json", str(outside), "gone/qc-wf-1.json"):
            with self.subTest(path=path):
                fails = self.judge([{"path": path, "sha256": sha}])
                self.assertEqual(len(fails), 1, fails)
                self.assertIn("does not resolve inside the package", fails[0])

    def test_an_absolute_path_is_refused_even_when_the_file_is_inside_the_package_and_its_hash_matches(self):
        art = self.artifact()
        absolute = str((self.root / art["path"]).resolve())
        self.assertTrue(Path(absolute).is_file())
        fails = self.judge([{**art, "path": absolute}])
        self.assertEqual(len(fails), 1, fails)
        self.assertIn("does not resolve inside the package", fails[0])

    def test_a_result_whose_bytes_do_not_match_its_recorded_hash_is_refused(self):
        for sha in ("0" * 64, None, 7, ""):
            with self.subTest(sha=sha):
                art = self.artifact()
                art["sha256"] = sha
                fails = self.judge([art])
                self.assertEqual(len(fails), 1, fails)
                self.assertIn("sha256", fails[0])

    def test_an_artifact_entry_with_no_sha256_key_or_a_non_string_one_is_refused_by_qc_violations_itself(self):
        # package.py and checks.py also demand a 64-hex sha256, but qc_violations must not lean on them.
        good = self.artifact()
        del_key = {k: v for k, v in good.items() if k != "sha256"}
        cases = {"no key": del_key, "None": {**good, "sha256": None}, "int": {**good, "sha256": 7},
                 "list": {**good, "sha256": [good["sha256"]]}, "dict": {**good, "sha256": {"v": good["sha256"]}},
                 "bool": {**good, "sha256": True}, "bytes": {**good, "sha256": good["sha256"].encode()},
                 "uppercase": {**good, "sha256": good["sha256"].upper()}}
        self.assertEqual(self.judge([good]), [])
        for label, art in cases.items():
            with self.subTest(sha256=label):
                fails = self.judge([art])
                self.assertEqual(len(fails), 1, fails)
                self.assertIn("does not match its recorded sha256", fails[0])

    def test_a_result_that_is_not_a_json_object_is_refused(self):
        for raw, word in ((b"not json", "is not JSON"), (b"[1]", "not the QC script's JSON object"),
                          (b"\"PASS\"", "not the QC script's JSON object"), (b"7", "not the QC script's JSON object"),
                          (b"\xff\xfe", "is not JSON")):
            with self.subTest(raw=raw):
                fails = self.judge([self.artifact(raw=raw)])
                self.assertEqual(len(fails), 1, fails)
                self.assertIn(word, fails[0])

    def test_the_required_values_are_the_spec_values(self):
        self.assertEqual(du.QC_REQUIRED, (("exit_code", 0), ("exit_gate", "PASS"), ("overall_mechanical", "PASS")))
        self.assertEqual(du.QC_ARTIFACT, "qc-{workflow_id}.json")


class AutomationQcWiringTests(unittest.TestCase):
    """automation_violations ends in the QC law for the export's own workflow id."""

    def test_the_qc_result_is_judged_for_the_exports_workflow_not_the_units_id(self):
        with mock.patch.object(du, "qc_violations", return_value=["QC-SENTINEL"]) as judge:
            from test_delivery_units import DeliveryUnitsTests
            case = DeliveryUnitsTests("test_real_skill44_builds_pass")
            case.setUp()
            self.addCleanup(case.tearDown)
            unit = case.automations[0]
            fails = case.check(case.package())
        self.assertEqual(fails.count("QC-SENTINEL"), len(case.automations))
        args = judge.call_args_list[0].args
        self.assertEqual(args[1], f"wf-{unit}")
        self.assertIn(unit, args[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
