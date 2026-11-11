#!/usr/bin/env python3
"""scripts/run_governed_stage.py: the one door a caller with its own production request uses to draw a stage
(harmony issues 2, 10 and 62).

  * A paid dispatch on a run whose gate has not closed the earlier stages is REFUSED by the admission call
    before the executor starts: no ledger row, no stage folder, no spend (issue 62 symptom: the paid
    provider used to reach the executor first and be refused there, with no admission record).
  * A kie dry run (--preflight) reaches `stage_gate.py check` and, on a prepared run, the check PASSES
    (issue 62 acceptance). "Prepared" here is a run whose contract has no prerequisite for the stage,
    via the gate's own STAGE_GATE_CONTRACT override; the real contract needs intake, copy and
    font-action-plan closed first, and a test shows the bare run is told so.
  * A stub run on an ungated directory is refused through the door too (AF-71-UNGATED, issue 10).

No paid API is called anywhere in this module.
"""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board_fixture as bf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOOR = ROOT / "scripts" / "run_governed_stage.py"
REQUEST = {
    "model": "STUB-NO-MODEL",
    "sections": [
        {"section_id": "hero", "section_name": "Hero", "copy": "New copy one.",
         "slots": [{"slot_id": "IMG-001", "aspect_ratio": "16:9", "art_direction": "Window light."}]},
        {"section_id": "proof", "section_name": "Proof", "copy": "New copy two.",
         "slots": [{"slot_id": "IMG-002", "aspect_ratio": "4:3", "art_direction": "Desk detail."}]},
    ],
}


class GovernedStageDoor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "run"
        bf.make_run(self.run_dir, base_request=REQUEST)
        intake = json.loads((self.run_dir / "intake.json").read_text())
        intake.update(image_cap=4)
        (self.run_dir / "intake.json").write_text(json.dumps(intake))

    def door(self, *argv, marker="1", extra_env=None):
        env = bf.subprocess_env()
        env.pop(bf.FIXTURE_MARKER, None)
        if marker is not None:
            env[bf.FIXTURE_MARKER] = marker
        env.update(extra_env or {})
        return subprocess.run([sys.executable, str(DOOR), str(self.run_dir), "--request", "production-request.json",
                               *argv], capture_output=True, text=True, env=env)

    def prepared_contract_env(self):
        """The gate's own contract override: desktop-wireframe has no prerequisite (a prepared run)."""
        contract = json.loads((ROOT / "references" / "stage-contract.json").read_text())
        contract["stages"]["desktop-wireframe"]["depends_on"] = []
        path = Path(self.tmp.name) / "prepared-contract.json"
        path.write_text(json.dumps(contract))
        return {"STAGE_GATE_CONTRACT": str(path)}

    def test_a_paid_dispatch_on_an_unclosed_run_is_refused_before_anything_is_spent(self):
        proc = self.door("--stage", "desktop-wireframe", "--provider", "kie", "--allow-paid",
                         extra_env={"KIE_API_KEY": "not-a-real-key"})
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("REFUSED", proc.stdout)
        self.assertIn("canonical stage check refused", proc.stdout)
        self.assertFalse((self.run_dir / "image-spend-ledger.json").exists(), "no render was reserved")
        self.assertFalse((self.run_dir / "desktop-wireframe").exists())

    def test_a_kie_dry_run_reaches_the_gate_check_and_passes_on_a_prepared_run(self):
        proc = self.door("--stage", "desktop-wireframe", "--provider", "kie", "--preflight",
                         extra_env=self.prepared_contract_env())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("GATE desktop-wireframe: stage_gate.py check exit 0 (PASS)", proc.stdout)
        self.assertIn("PREFLIGHT desktop-wireframe section-01.png", proc.stdout)
        self.assertFalse((self.run_dir / "image-spend-ledger.json").exists(), "a dry run spends nothing")
        self.assertFalse((self.run_dir / "desktop-wireframe").exists(), "a dry run writes no image")

    def test_the_same_dry_run_on_the_real_contract_says_the_run_is_not_ready(self):
        proc = self.door("--stage", "desktop-wireframe", "--provider", "kie", "--preflight")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("GATE desktop-wireframe: stage_gate.py check exit 1 (stage not startable yet)", proc.stdout)
        self.assertFalse((self.run_dir / "image-spend-ledger.json").exists())

    def admitted_authorities(self):
        data = json.loads((self.run_dir / "private" / "governor.json").read_text())
        found = []

        def walk(node):
            if isinstance(node, dict):
                if node.get("kind") == "direct_executor" and "authority" in node:
                    found.append(node["authority"])
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(data)
        return found

    def test_the_admission_records_the_authority_the_request_carries(self):
        """A dry run is admitted as a preview: the record shows the authority asked for."""
        proc = self.door("--stage", "desktop-wireframe", "--provider", "kie", "--preflight",
                         extra_env=self.prepared_contract_env())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.admitted_authorities(), ["preview"])

    def test_a_stage_name_outside_the_canonical_list_is_a_usage_error(self):
        proc = self.door("--stage", "not-a-stage", "--provider", "stub")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("invalid choice", proc.stderr)

    def test_a_stub_run_on_an_ungated_directory_is_refused_through_the_door(self):
        proc = self.door("--stage", "desktop-wireframe", "--provider", "stub", marker=None)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("AF-71-UNGATED", proc.stdout)
        self.assertFalse((self.run_dir / "desktop-wireframe").exists())

    def test_with_the_harness_marker_the_stub_fixture_is_drawn(self):
        proc = self.door("--stage", "desktop-wireframe", "--provider", "stub")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue((self.run_dir / "desktop-wireframe" / "section-01.png").is_file())

    def test_the_admission_call_hands_the_gate_its_arguments_in_the_gates_order(self):
        """governed_runner built `check <stage> <run_dir>`; stage_gate wants `check <run_dir> <stage>`, so it
        read the stage as the run directory and exited 2 on every real call (a usage error, never a verdict)."""
        sys.path.insert(0, str(ROOT / "scripts"))
        import governed_runner
        rc, output, argv = governed_runner.stage_check(self.run_dir, "desktop-wireframe")
        self.assertEqual(rc, 1, output)  # the gate's own refusal: earlier stages are not closed
        self.assertIn("is not closed", output)
        self.assertEqual(argv[2:5], ["check", str(self.run_dir.resolve()), "desktop-wireframe"])

    def built_command(self, *argv):
        """Run the door in this process with the admission call and the child process spied; return the command
        the door builds for the executor (nothing is spawned, nothing is spent)."""
        sys.path.insert(0, str(ROOT / "scripts"))
        import run_governed_stage
        spy = mock.Mock(return_value=mock.Mock(returncode=0))
        with mock.patch.object(run_governed_stage.governed_runner, "admit", return_value={"stage_check": {"exit": 0}}), \
                mock.patch.object(run_governed_stage.subprocess, "run", spy), contextlib.redirect_stdout(io.StringIO()):
            rc = run_governed_stage.main([str(self.run_dir), "--request", "production-request.json",
                                          "--stage", "desktop-wireframe", *argv])
        self.assertEqual(rc, 0)
        spy.assert_called_once()
        return spy.call_args.args[0]

    def test_the_door_forwards_the_callers_provider_and_allow_paid_to_the_executor(self):
        cmd = self.built_command("--provider", "kie", "--allow-paid")
        self.assertEqual(cmd[cmd.index("--provider") + 1], "kie", "the caller's provider is not overridden")
        self.assertNotIn("stub", cmd, "the door must never force the offline stub")
        self.assertIn("--allow-paid", cmd)
        self.assertEqual(cmd[cmd.index("--stages") + 1], "desktop-wireframe")

    def test_the_door_adds_allow_paid_only_when_the_caller_gave_it(self):
        cmd = self.built_command("--provider", "kie")
        self.assertEqual(cmd[cmd.index("--provider") + 1], "kie")
        self.assertNotIn("--allow-paid", cmd)
        self.assertEqual(self.built_command("--provider", "stub")[-1], "stub")

    def authority(self, provider, allow_paid, preflight=False):
        sys.path.insert(0, str(ROOT / "scripts"))
        import run_governed_stage
        return run_governed_stage.authority_for(provider, allow_paid, preflight)

    def test_a_stub_run_without_allow_paid_is_admitted_as_local(self):
        """Only a real paid dispatch is an authoritative boundary; a free stub run is plain local work."""
        self.assertEqual(self.authority("stub", False), "local")
        self.assertEqual(self.authority("stub", True), "local", "the stub provider never spends, flag or not")

    def test_a_kie_run_without_allow_paid_is_not_a_paid_dispatch(self):
        """Without --allow-paid nothing is spent, so admission must not treat the run as a paid dispatch."""
        self.assertNotEqual(self.authority("kie", False), "paid_dispatch")
        self.assertEqual(self.authority("kie", False), "local")
        self.assertEqual(self.authority("kie", True), "paid_dispatch", "control: the flag is what makes it paid")
        self.assertEqual(self.authority("kie", True, preflight=True), "preview")

    def test_a_missing_request_file_is_a_usage_error(self):
        proc = subprocess.run([sys.executable, str(DOOR), str(self.run_dir), "--request", "nope.json",
                               "--stage", "desktop-wireframe", "--provider", "stub"],
                              capture_output=True, text=True, env=bf.subprocess_env())
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_the_door_adds_no_default_provider(self):
        proc = subprocess.run([sys.executable, str(DOOR), str(self.run_dir), "--request", "production-request.json",
                               "--stage", "desktop-wireframe"], capture_output=True, text=True,
                              env=bf.subprocess_env())
        self.assertEqual(proc.returncode, 2, "the caller must say stub or kie; nothing defaults")


if __name__ == "__main__":
    unittest.main(verbosity=2)
