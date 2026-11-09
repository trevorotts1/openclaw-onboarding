"""PRD-27: verify.sh must fail when runtime-manifest.json skill_version differs from skill-version.txt."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

VERIFY = Path(__file__).resolve().parent.parent / "verify.sh"


class ManifestLockstepTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        # Only verify.sh is copied (not tests/), so verify.sh cannot recurse into this test.
        shutil.copy(VERIFY, self.tmp / "verify.sh")
        (self.tmp / "SKILL.md").write_text("---\nversion: 1.0.0\n---\n")
        (self.tmp / "skill-version.txt").write_text("1.0.0\n")

    def _run(self, manifest_version):
        (self.tmp / "runtime-manifest.json").write_text(json.dumps({"skill_version": manifest_version}))
        return subprocess.run(["bash", str(self.tmp / "verify.sh")], capture_output=True, text=True,
                              env={**os.environ, "PYTHON": sys.executable})

    def test_match(self):
        r = self._run("1.0.0")
        self.assertIn("[PASS] runtime-manifest version lockstep 1.0.0", r.stdout)
        self.assertNotIn("[FAIL] runtime-manifest version drift", r.stdout)

    def test_drift(self):
        r = self._run("9.9.9")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("[FAIL] runtime-manifest version drift 9.9.9 != 1.0.0", r.stdout)


if __name__ == "__main__":
    unittest.main()
