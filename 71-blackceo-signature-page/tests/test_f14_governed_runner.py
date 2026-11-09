#!/usr/bin/env python3
"""F14 (BLD-001): governed runner and artifact admission -- one discriminating
check per item, plus the four entry refusals.

Every check here FAILS on origin/main (the governed runner, the out-of-pipeline
detector and the admission seams do not exist there, and the 49 landing seam
accepts a zero-exit substitute as stage evidence) and PASSES on this head.

Run: python3 tests/test_f14_governed_runner.py
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
REPO = ROOT.parent
sys.path.insert(0, str(SCRIPTS))

import governed_runner  # noqa: E402
import out_of_pipeline  # noqa: E402

sys.path.insert(0, str(REPO / "49-signature-funnel" / "scripts"))
import admission_seam  # noqa: E402
import landing_bridge  # noqa: E402

PLAN = {
    "launch_id": "f14-governed-runner",
    "pages": [
        {"id": "page_a", "kind": "sales", "url": None, "waits_for": []},
        {"id": "page_b", "kind": "opt_in", "url": None, "waits_for": ["page_a"]},
    ],
    "email_sequences": [],
    "text_sets": [],
    "automations": [],
}

GATE_PASS = "import sys\nprint('PASS'); sys.exit(0)\n"
GATE_FAIL = "import sys\nprint('FAIL')\nprint('- intake is not closed')\nsys.exit(1)\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_root = Path(self.tmp.name) / "run"
        self.run_root.mkdir()
        (self.run_root / "intake.json").write_text(json.dumps(
            {"page_kind": "sales", "copy_version": "standard"}), encoding="utf-8")
        self._gate = governed_runner.GATE_PATH
        self.addCleanup(setattr, governed_runner, "GATE_PATH", self._gate)

    def fake_gate(self, body, name="gate.py"):
        path = Path(self.tmp.name) / name
        path.write_text(body, encoding="utf-8")
        governed_runner.GATE_PATH = path
        return path


class TestF14(Base):
    # ---- item 1 ---------------------------------------------------------
    def test_item01_work_plan_binds_contract_identity_inputs_outputs_prereqs_predicate(self):
        doc = governed_runner.work_plan(self.run_root)
        item = doc["items"][0]
        self.assertEqual(item["contract_version"], governed_runner.admission().CONTRACT_VERSION)
        self.assertTrue(doc["identity"]["run_key"].startswith("sha256:"))
        self.assertTrue(item["inputs"]["intake.json"].startswith("sha256:"))
        self.assertIn(item["operation"], ("author", "generate", "install", "publish",
                                          "wire", "publish_asset"))
        self.assertTrue(item["completion_predicate"]["requires"])
        wireframe = next(i for i in doc["items"] if i["stage"] == "desktop-wireframe")
        self.assertEqual(len(wireframe["prerequisites"]), 1)
        self.assertEqual(wireframe["prerequisites"][0]["requires"], "closed")
        self.assertEqual(wireframe["prerequisites"][0]["stage"], "font-action-plan")
        self.assertTrue(wireframe["expected_outputs"])
        self.assertTrue(doc["work_plan_hash"].startswith("sha256:"))

    # ---- item 2 + the four entry refusals -------------------------------
    def test_item02_one_admission_service_at_every_entry(self):
        self.fake_gate(GATE_PASS)
        for kind in ("entry", "resume", "checkpoint", "direct_executor"):
            decision = governed_runner.admit(self.run_root, kind=kind,
                                             authority="local")
            self.assertTrue(decision["admitted"], (kind, decision))
            self.assertFalse(decision["production_completion"])
        governor = json.loads((self.run_root / "private" / "governor.json").read_text())
        self.assertEqual(len(governor["admitted"]), 4)
        versions = {d["contract_version"] for d in governor["admitted"]}
        runs = {d["run_key"] for d in governor["admitted"]}
        self.assertEqual(len(versions), 1)
        self.assertEqual(len(runs), 1)

    def test_item02_refusal_entry_launch_with_a_failed_stage_check(self):
        gate = self.fake_gate(GATE_FAIL)
        with self.assertRaises(governed_runner.AdmissionRefused) as caught:
            governed_runner.admit(self.run_root, kind="entry",
                                  authority="paid_dispatch", stage="visual-mockup")
        self.assertEqual(caught.exception.decision["source"], "stage_gate")
        self.assertIn(str(gate), caught.exception.decision["stage_check"]["command"])
        # nothing was admitted, so nothing was written
        self.assertEqual(out_of_pipeline.scan(
            self.run_root, inputs=("intake.json",))["ungoverned"], [])

    def test_item02_refusal_resume_on_a_unit_whose_dependency_is_only_self_declared(self):
        self.fake_gate(GATE_PASS)
        record = {"schema": governed_runner.SCHEMA, "admitted": [], "refused": [],
                  "units": {"page_a": {"state": "done", "verified": False,
                                       "waits_for": [], "attempts": 1}}}
        (self.run_root / "private").mkdir(parents=True, exist_ok=True)
        (self.run_root / governed_runner.GOVERNOR_FILE).write_text(json.dumps(record))
        with self.assertRaises(governed_runner.AdmissionRefused) as caught:
            governed_runner.admit(self.run_root, kind="resume", authority="local",
                                  plan=PLAN, unit="page_b")
        self.assertEqual(caught.exception.decision["source"], "admission.admit_entry")
        self.assertIn("dependencies not verified complete",
                      caught.exception.decision["reason"])

    def test_item02_refusal_delegation_inherits_the_paid_dispatch_gate(self):
        self.fake_gate(GATE_FAIL)
        with self.assertRaises(governed_runner.AdmissionRefused) as caught:
            governed_runner.delegate(self.run_root, stage="visual-mockup",
                                     authority="paid_dispatch", owner="worker-1")
        self.assertEqual(caught.exception.decision["kind"], "delegation")
        self.assertEqual(caught.exception.decision["source"], "stage_gate")

    def test_item02_refusal_paid_dispatch_with_out_of_pipeline_output(self):
        self.fake_gate(GATE_PASS)
        (self.run_root / "site").mkdir()
        (self.run_root / "site" / "index.html").write_text("<p>by hand</p>",
                                                           encoding="utf-8")
        with self.assertRaises(governed_runner.AdmissionRefused) as caught:
            governed_runner.admit(self.run_root, kind="direct_executor",
                                  authority="paid_dispatch", stage="visual-mockup")
        self.assertEqual(caught.exception.decision["source"], "out_of_pipeline")
        self.assertIn("site/index.html", caught.exception.decision["reason"])

    # ---- item 3 ---------------------------------------------------------
    def test_item03_paid_dispatch_runs_the_existing_stage_check_before_work(self):
        gate = self.fake_gate(GATE_FAIL)
        with self.assertRaises(governed_runner.AdmissionRefused) as caught:
            governed_runner.admit(self.run_root, kind="direct_executor",
                                  authority="paid_dispatch", stage="mobile-tablet")
        check = caught.exception.decision["stage_check"]
        self.assertEqual(check["exit"], 1)
        self.assertIn(str(gate), check["command"])
        # the refusal happened before any producer wrote a byte
        self.assertEqual(list((self.run_root / "mobile-tablet").glob("*"))
                         if (self.run_root / "mobile-tablet").is_dir() else [], [])

    def test_item03_preview_never_refuses_and_never_completes(self):
        self.fake_gate(GATE_FAIL)
        decision = governed_runner.admit(self.run_root, kind="direct_executor",
                                         authority="preview", stage="visual-mockup")
        self.assertTrue(decision["admitted"])
        self.assertFalse(decision["production_completion"])

    # ---- item 4 ---------------------------------------------------------
    def test_item04_detector_compares_exact_paths_not_substrings(self):
        (self.run_root / "a").mkdir()
        (self.run_root / "a" / "page.html").write_text("one", encoding="utf-8")
        (self.run_root / "a" / "old-page.html").write_text("old", encoding="utf-8")
        out_of_pipeline.register(self.run_root, "a/page.html", stage="responsive-html")
        out_of_pipeline.close(self.run_root, "a/page.html", stage="responsive-html")
        # the substring really is present in the ungoverned name...
        self.assertIn("page.html", "old-page.html")
        result = out_of_pipeline.scan(self.run_root,
                                      receipts=[{"path": "a/page.html"}],
                                      inputs=("intake.json",))
        self.assertEqual([e["path"] for e in result["ungoverned"]], ["a/old-page.html"])
        with self.assertRaises(out_of_pipeline.OutOfPipeline) as caught:
            out_of_pipeline.require_governed(self.run_root, inputs=("intake.json",))
        self.assertIn("old-page.html", str(caught.exception))

    # ---- item 5 ---------------------------------------------------------
    def test_item05_registered_in_progress_is_not_ungoverned(self):
        out_of_pipeline.register(self.run_root, "final-mockups/board.png",
                                 stage="final-mockups")
        (self.run_root / "final-mockups").mkdir()
        (self.run_root / "final-mockups" / "board.png").write_bytes(b"partial")
        result = out_of_pipeline.scan(self.run_root, inputs=("intake.json",))
        self.assertEqual([e["path"] for e in result["registered_unfinished"]],
                         ["final-mockups/board.png"])
        self.assertEqual(result["ungoverned"], [])
        self.assertTrue(result["ok"])

    # ---- item 6 ---------------------------------------------------------
    def test_item06_unadmitted_output_is_unverified_and_excluded_but_preserved(self):
        (self.run_root / "site").mkdir()
        hand = self.run_root / "site" / "index.html"
        hand.write_text("<p>by hand</p>", encoding="utf-8")
        split = governed_runner.delivery(
            self.run_root, [{"path": "site/index.html", "sha256": "a" * 64}])
        self.assertEqual(split["admitted"], [])
        excluded = split["excluded"][0]
        self.assertFalse(excluded["verified"])
        for bucket in ("delivery", "progress_credit", "installation", "publication"):
            self.assertIn(bucket, excluded["excluded_from"])
        self.assertTrue(split["preserved"])
        self.assertTrue(hand.is_file())  # never auto-deleted

    # ---- item 7 ---------------------------------------------------------
    def test_item07_authoring_is_registered_validated_and_the_stage_closed(self):
        gate = self.fake_gate(GATE_PASS)
        (self.run_root / "copy").mkdir()
        (self.run_root / "copy" / "internal-manuscript.md").write_text(
            "A real manuscript.", encoding="utf-8")
        decision = governed_runner.admit_authoring(
            self.run_root, kind="copy", stage="copy",
            output="copy/internal-manuscript.md",
            validate=lambda raw: b"manuscript" in raw.lower())
        self.assertTrue(decision["authoring"]["validated"])
        self.assertEqual(decision["authoring"]["close"]["exit"], 0)
        self.assertIn(str(gate), decision["authoring"]["close"]["command"])
        registry = out_of_pipeline.load(self.run_root)
        self.assertEqual(registry["outputs"]["copy/internal-manuscript.md"]["state"],
                         "emitted")

    def test_item07_authoring_output_that_fails_validation_closes_nothing(self):
        self.fake_gate(GATE_PASS)
        (self.run_root / "copy").mkdir()
        (self.run_root / "copy" / "internal-manuscript.md").write_text(
            "short", encoding="utf-8")
        with self.assertRaises(governed_runner.AdmissionRefused):
            governed_runner.admit_authoring(
                self.run_root, kind="copy", stage="copy",
                output="copy/internal-manuscript.md", validate=lambda _raw: False)
        self.assertIsNone(out_of_pipeline.load(self.run_root)["outputs"]
                          ["copy/internal-manuscript.md"].get("sha256"))

    # ---- item 8 ---------------------------------------------------------
    def test_item08_instructions_resolved_once_and_injected(self):
        self.fake_gate(GATE_PASS)
        first = governed_runner.canonical_entry_instructions(self.run_root)
        second = governed_runner.canonical_entry_instructions(self.run_root)
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertTrue((self.run_root / governed_runner.INSTRUCTIONS_FILE).is_file())
        self.assertIn("verified evidence", first["text"])
        self.assertIn("forbids a worker from reading its dependencies", first["text"])
        delegated = governed_runner.delegate(self.run_root, stage="copy",
                                             owner="worker-1")
        self.assertEqual(delegated["instructions"]["sha256"], first["sha256"])
        scheduled = governed_runner.checkpoint(self.run_root, stage="copy")
        self.assertTrue(scheduled["admitted"])
        # the swarm brief carries them (delegated AND scheduled work)
        source = (SCRIPTS / "swarm_runner.py").read_text(encoding="utf-8")
        self.assertIn("self.canonical_instructions_text()", source)

    # ---- item 9 ---------------------------------------------------------
    def test_item09_blocked_unit_reports_a_blocker_and_refuses_a_draft_substitute(self):
        with self.assertRaises(governed_runner.AdmissionRefused):
            governed_runner.blocked(self.run_root, stage="copy", reason="")
        (self.run_root / "copy").mkdir()
        (self.run_root / "copy" / "public-copy.md").write_text(
            "a draft nobody registered", encoding="utf-8")
        entry = governed_runner.blocked(
            self.run_root, stage="copy", reason="client has not supplied the offer",
            blocker={"unit": "copy", "detail": "offer price missing"},
            independent=["page_b"])
        self.assertTrue(entry["blocked"])
        self.assertEqual(entry["blocker"]["reason"], "client has not supplied the offer")
        self.assertEqual(entry["alternatives_accepted"], 0)
        self.assertIn("copy/public-copy.md", entry["quarantined"])
        self.assertEqual(entry["continues"], ["page_b"])

    # ---- item 10 --------------------------------------------------------
    def _seam_cfg(self, gate_body):
        skill_root = Path(self.tmp.name) / "skill71"
        (skill_root / "scripts").mkdir(parents=True, exist_ok=True)
        (skill_root / "scripts" / "stage_gate.py").write_text(gate_body, encoding="utf-8")
        return {"skill_root": skill_root, "python": sys.executable,
                "pipeline_command": [sys.executable, "-c", "pass"], "draft": False}

    def test_item10_pipeline_command_cannot_substitute_a_zero_exit_for_stage_evidence(self):
        cfg = self._seam_cfg(GATE_FAIL)
        with self.assertRaises(landing_bridge.BridgeError):
            landing_bridge._pipeline_phase(cfg, self.run_root)
        # a draft records the substitute AND the canonical verdict, never the exit 0
        cfg["draft"] = True
        pipeline = landing_bridge._pipeline_phase(cfg, self.run_root)
        self.assertEqual(pipeline["exit"], 1)                 # canonical gate
        self.assertEqual(pipeline["substitute_exit"], 0)       # the fixture command
        self.assertTrue(pipeline["substituted"])
        self.assertEqual(pipeline["evidence_authority"], "canonical_stage_gate")
        # and with the gate closed, the seam still reports the canonical verdict
        good = landing_bridge._pipeline_phase(self._seam_cfg(GATE_PASS), self.run_root)
        self.assertEqual(good["exit"], 0)
        self.assertTrue(good["substituted"])

    # ---- item 11 --------------------------------------------------------
    def test_item11_conversation_work_admitted_only_against_the_selected_mode(self):
        page_only = governed_runner.admit_conversation(self.run_root)
        self.assertEqual(page_only["required"], False)
        self.assertTrue(page_only["admitted"])

        requested_no_mode = json.loads(json.dumps(PLAN))
        requested_no_mode["conversation_ai"] = {"requested": True, "mode": None}
        with self.assertRaises(governed_runner.AdmissionRefused):
            governed_runner.admit_conversation(self.run_root, requested_no_mode)

        complete = json.loads(json.dumps(PLAN))
        complete["automations"] = [{"id": "ai_reply", "family": "conversation_ai_reply"}]
        complete["conversation_ai"] = {"requested": True, "mode": "drafted",
                                      "channels": ["sms"]}
        with self.assertRaises(governed_runner.AdmissionRefused):
            governed_runner.admit_conversation(self.run_root, complete, channel="sms")
        admitted = governed_runner.admit_conversation(
            self.run_root, complete, channel="sms", authority="drafted")
        self.assertTrue(admitted["required"])
        self.assertEqual(admitted["units"], ["ai_reply"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
