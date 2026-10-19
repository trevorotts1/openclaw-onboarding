"""S44-05 path-safety proofs for stage_gate.py.

The pre-fix gate substituted {run_dir}/{brand}/{file} into a command
STRING and then shlex.split it (run_one_validator), so a run directory
containing a space became several argv entries and every path validator
failed with a usage error. These tests fail on that code and pass once
each substituted value is shell-quoted.
"""
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "stage_gate.py"
FIXTURE_RUN = ROOT / "tests" / "fixtures" / "r71h-dry-run" / "run"
PY = sys.executable
sys.path.insert(0, str(ROOT / "scripts"))
import stage_gate  # noqa: E402  (module import loads the real contract)

class SpacedPathTests(unittest.TestCase):
    def test_resolver_keeps_spaced_non_ascii_run_dir_as_one_argv(self):
        run = Path("/tmp/S44 space probe/café run")
        resolved, lines = stage_gate.resolve_brand_placeholder(
            "python3 scripts/validate_install.py {run_dir} install",
            run, "ghl-install-test", None)
        self.assertEqual(lines, [])
        parts = shlex.split(resolved)
        self.assertEqual(parts[2], str(run))
        self.assertEqual(parts[3], "install")

    def test_ghl_install_close_with_spaced_non_ascii_output_dir(self):
        # The recovery root itself contains spaces; keep that shape and
        # add non-ASCII so both classes are exercised by a real close.
        td = Path(tempfile.mkdtemp(prefix="s44 spaced "))
        self.addCleanup(shutil.rmtree, td, True)
        run = td / "run dir café"
        shutil.copytree(FIXTURE_RUN, run)
        env = dict(os.environ)
        env.update({"TMPDIR": str(td), "TMP": str(td), "TEMP": str(td),
                    "GHL_LOCATION_ID": "fixture-location-001"})
        proc = subprocess.run(
            [PY, str(GATE), "close", str(run), "ghl-install-test"],
            cwd=str(ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("CLOSED: stage ghl-install-test", proc.stdout)

if __name__ == "__main__":
    unittest.main()
