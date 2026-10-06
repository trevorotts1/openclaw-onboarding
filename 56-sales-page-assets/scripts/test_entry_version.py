#!/usr/bin/env python3
"""test_entry_version.py - proves the Skill 56 entry shell version gate matches the
current v2 contract: it passes on the shipped skill-version.txt + SKILL.md pair
and fails closed on a genuinely incompatible major, a malformed value, and
frontmatter drift. Stdlib only, no network. Run: python3 test_entry_version.py"""
import shutil, subprocess, tempfile, unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ENTRY = "sales-page-assets-entry.sh"


def run(version, frontmatter=None):
    """Copy the entry shell + SKILL.md into a temp skill dir, set the version, run --check-version."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        shutil.copy(SKILL / ENTRY, d / ENTRY)
        fm = version if frontmatter is None else frontmatter
        (d / "SKILL.md").write_text("---\nname: t\nversion: %s\n---\nbody\n" % fm)
        (d / "skill-version.txt").write_text(version + "\n")
        p = subprocess.run(["bash", str(d / ENTRY), "--check-version"], capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr


class EntryVersionGate(unittest.TestCase):
    def test_shipped_version_passes(self):
        p = subprocess.run(["bash", str(SKILL / ENTRY), "--check-version"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_current_major_passes(self):
        self.assertEqual(run("v2.9.14")[0], 0)

    def test_old_major_fails(self):
        rc, out = run("v1.5.0")
        self.assertNotEqual(rc, 0)
        self.assertIn("expected major 2", out)

    def test_future_major_fails(self):
        self.assertNotEqual(run("v3.0.0")[0], 0)

    def test_malformed_fails(self):
        self.assertNotEqual(run("v2")[0], 0)
        self.assertNotEqual(run("v20.0.0")[0], 0)

    def test_frontmatter_drift_fails(self):
        rc, out = run("v2.0.1", frontmatter="v2.0.0")
        self.assertNotEqual(rc, 0)
        self.assertIn("drift", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
