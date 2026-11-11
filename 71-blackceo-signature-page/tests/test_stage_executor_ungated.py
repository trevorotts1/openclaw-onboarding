#!/usr/bin/env python3
"""AF-71-UNGATED (harmony issue 10): a stub run on a run with no gate state is a test fixture only.

stage_executor.require_stage_start used to let a STUB run on a directory with no private/state.json
continue after printing a WARN line, so any caller (Skill 49's legacy funnel tool did) could draw
placeholder images without the stage gate ever being consulted. Now that branch needs BOTH the stub
provider AND the environment marker SKILL71_FIXTURE_RUN=1, which only test harnesses set
(tests/board_fixture.py sets it for this suite; no product script does). Outside it the run is
refused with AF-71-UNGATED before a single placeholder is written.

Fail-before / pass-after: on the pre-fix executor the first test below fails (the stub run succeeds).
No paid API is called anywhere in this module.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board_fixture as bf  # noqa: E402  (sets SKILL71_FIXTURE_RUN for this harness; removed per child below)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "stage_executor.py"
REQUEST = {
    "model": "STUB-NO-MODEL",
    "sections": [
        {"section_id": "hero", "section_name": "Hero", "copy": "New copy one.",
         "slots": [{"slot_id": "IMG-001", "aspect_ratio": "16:9", "art_direction": "Window light."}]},
    ],
}


class UngatedStubRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "run"
        bf.make_run(self.run_dir, base_request=REQUEST)

    def execute(self, marker, *extra):
        env = bf.subprocess_env()
        env.pop(bf.FIXTURE_MARKER, None)
        if marker is not None:
            env[bf.FIXTURE_MARKER] = marker
        return subprocess.run([sys.executable, str(SCRIPT), str(self.run_dir), *extra],
                              capture_output=True, text=True, env=env)

    def test_a_stub_run_on_an_ungated_directory_is_refused_without_the_marker(self):
        proc = self.execute(None, "--provider", "stub", "--stages", "desktop-wireframe")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("AF-71-UNGATED", proc.stdout)
        self.assertIn("SKILL71_FIXTURE_RUN", proc.stdout)
        self.assertFalse((self.run_dir / "desktop-wireframe").exists(), "a refused run writes no placeholder")

    def test_the_marker_must_be_exactly_1(self):
        for value in ("", "0", "true", "yes", "1 "):
            proc = self.execute(value, "--provider", "stub", "--stages", "desktop-wireframe")
            self.assertEqual(proc.returncode, 1, (value, proc.stdout + proc.stderr))
            self.assertIn("AF-71-UNGATED", proc.stdout, value)

    def test_the_refusal_binds_the_provider_not_only_the_marker(self):
        """Even with the marker, only the stub provider may run ungated: any other provider name is refused."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("stage_executor_provider_probe", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with mock.patch.dict(os.environ, {bf.FIXTURE_MARKER: "1"}):
            verdict = mod.require_stage_start(self.run_dir, "desktop-wireframe", "stub")
            self.assertEqual(verdict["status"], "ungated_fixture", "control: the stub provider passes with the marker")
            with self.assertRaises(mod.ExecutorError) as ctx:
                mod.require_stage_start(self.run_dir, "desktop-wireframe", "other-provider")
        self.assertIn("AF-71-UNGATED", str(ctx.exception))

    def test_with_the_marker_the_fixture_runs_and_says_so_loudly(self):
        proc = self.execute("1", "--provider", "stub", "--stages", "desktop-wireframe")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("UNGATED TEST FIXTURE", proc.stderr)
        self.assertIn("SKILL71_FIXTURE_RUN=1", proc.stderr)
        record = json.loads((self.run_dir / "desktop-wireframe" / "stage-executor-record.json").read_text())
        self.assertEqual(record["start_check"]["status"], "ungated_fixture")

    def test_a_gate_driven_run_is_held_to_the_gate_even_with_the_marker(self):
        (self.run_dir / "private").mkdir()
        (self.run_dir / "private" / "state.json").write_text(json.dumps({"stages": {}}))
        proc = self.execute("1", "--provider", "stub", "--stages", "desktop-wireframe")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("cannot start", proc.stdout)
        self.assertNotIn("AF-71-UNGATED", proc.stdout)  # the gate's own refusal, not the fixture rule
        self.assertFalse((self.run_dir / "desktop-wireframe").exists())

    def test_the_paid_route_is_never_a_fixture(self):
        env = bf.subprocess_env()
        env["KIE_API_KEY"] = "not-a-real-key"
        proc = subprocess.run([sys.executable, str(SCRIPT), str(self.run_dir), "--provider", "kie", "--allow-paid",
                               "--stages", "desktop-wireframe"], capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertNotIn("UNGATED TEST FIXTURE", proc.stderr)
        self.assertFalse((self.run_dir / "image-spend-ledger.json").exists(), "no money was reserved")

    def test_a_kie_run_with_no_gate_state_gets_the_gate_refusal_not_the_stub_fixture_message(self):
        """The paid provider is never an ungated fixture: with no private/state.json it is refused with the
        gate-driven text ("no provider call was made"), not the AF-71-UNGATED stub text meant for stub runs."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("stage_executor_kie_probe", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertFalse((self.run_dir / "private" / "state.json").exists())
        for env in ({bf.FIXTURE_MARKER: "1"}, {}):  # the harness marker does not change the paid route
            with mock.patch.dict(os.environ, env):
                with self.assertRaises(mod.ExecutorError) as ctx:
                    mod.require_stage_start(self.run_dir, "desktop-wireframe", "kie")
            text = str(ctx.exception)
            self.assertIn("cannot start", text)
            self.assertIn("no provider call was made", text)
            self.assertNotIn("AF-71-UNGATED", text)

    def test_the_item_path_has_the_same_rule(self):
        (self.run_dir / "image-inventory-prompts").mkdir()
        (self.run_dir / "image-inventory-prompts" / "IMG-007.txt").write_text("Prompt for the seventh image.")
        proc = self.execute(None, "--stage", "image-generation-qc", "--item", "IMG-007", "--provider", "stub")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("AF-71-UNGATED", proc.stdout)
        self.assertFalse((self.run_dir / "image-generation-qc").exists())

    def test_no_product_script_sets_the_marker(self):
        """The marker is the harness's, never a product script's: nothing under scripts/ assigns it."""
        offenders = []
        for path in (ROOT / "scripts").rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for n, line in enumerate(text.splitlines(), 1):
                if "SKILL71_FIXTURE_RUN" in line and ("environ[" in line and "=" in line.split("environ[", 1)[1]):
                    offenders.append(f"{path.name}:{n}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
