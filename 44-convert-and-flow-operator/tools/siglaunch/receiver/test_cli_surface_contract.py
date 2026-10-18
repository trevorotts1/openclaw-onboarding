"""CLI surface contract: pins CafExecutor's assumptions to the REAL
caf --help output of the engine in this repo's worktree.

The adapter once called a surface that does not exist (`workflows
export --json --folder ...`, a `workflows qc` verb) and every dispatch
blocked on it. These tests run the read-only --help surfaces of the
actual installed CLI and fail if the ground shifts again: top-level
--json/--experimental placement, build's --from-plan, export's
--workflow-id/--out file contract, the absence of a qc verb, and the
skill-root qc-built-workflow.sh the QC leg derives from the caf path.

Skipped (not failed) when the engine worktree is absent on this VM.
"""
import subprocess
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_REL = ("ob", "44-convert-and-flow-operator", "tools", "engine", "caf")


def _find_caf():
    for anc in _HERE.parents:
        for cand in (anc.joinpath("worktree", *_REL),
                     anc.joinpath("rooms", "S44", "worktree", *_REL)):
            if cand.is_file():
                return cand
    return None


CAF_PATH = _find_caf()
QC_SCRIPT = (CAF_PATH.resolve().parents[2] / "qc-built-workflow.sh"
             if CAF_PATH else None)


def _help(*args):
    """Run one read-only --help surface; return combined output."""
    try:
        proc = subprocess.run([str(CAF_PATH), *args],
                              capture_output=True, text=True, timeout=60)
    except OSError:
        proc = subprocess.run(["bash", str(CAF_PATH), *args],
                              capture_output=True, text=True, timeout=60)
    return proc.stdout + "\n" + proc.stderr


@unittest.skipUnless(CAF_PATH is not None,
                     "engine worktree (tools/engine/caf) not present")
class CliSurfaceContractTests(unittest.TestCase):
    def test_top_level_options(self):
        text = _help("--help")
        self.assertIn("--json", text)
        self.assertIn("--experimental", text)

    def test_build_requires_from_plan(self):
        text = _help("workflows", "build", "--help")
        self.assertIn("--from-plan", text)

    def test_export_contract(self):
        text = _help("workflows", "export", "--help")
        self.assertIn("--workflow-id", text)
        self.assertIn("--out", text)
        self.assertNotIn("--folder", text)

    def test_no_qc_verb(self):
        text = _help("workflows", "--help")
        in_commands = False
        for line in text.splitlines():
            if line.strip().startswith("Commands:"):
                in_commands = True
                continue
            if in_commands:
                tokens = line.split()
                if tokens:
                    self.assertNotEqual(
                        tokens[0], "qc",
                        "a `workflows qc` verb appeared; the adapter's "
                        "QC leg (skill-root script) must be revisited")

    def test_list_command_exists(self):
        text = _help("workflows", "--help")
        self.assertIn("list", text)

    def test_qc_script_derivation(self):
        # The executor derives <skill root>/qc-built-workflow.sh as
        # parents[2] of the caf file; that file must actually exist.
        self.assertIsNotNone(QC_SCRIPT)
        self.assertTrue(QC_SCRIPT.is_file(),
                        f"QC script missing at derived path {QC_SCRIPT}")


if __name__ == "__main__":
    unittest.main()
