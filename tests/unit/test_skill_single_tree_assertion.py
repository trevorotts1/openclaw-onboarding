#!/usr/bin/env python3
"""Fixture tests for the FIX-11 step 5 single-root deployment assertion.

Locks scripts/assert-skill-single-tree.py, the repository half of FIX-10/FIX-11:
for every skill the release ships there must be exactly one installed tree and
its version must equal the released version; otherwise the deployment fails.

Every case is a synthetic fixture tree under a temporary directory. Nothing
here reads or writes a real box, a real install root or the operator's HOME.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "assert-skill-single-tree.py"
CANON = "83-black-friday-launcher"
SHADOW = "black-friday-launcher"


def make_skill(root, dirname, version):
    path = Path(root) / dirname
    path.mkdir(parents=True)
    if version is not None:
        (path / "skill-version.txt").write_text(version + "\n", encoding="utf-8")
    (path / "SKILL.md").write_text("# %s\n" % dirname, encoding="utf-8")
    return path


class SingleTreeAssertion(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "home"
        self.release = Path(self._tmp.name) / "release"
        self.skills = self.home / ".openclaw" / "skills"
        self.shadow = self.home / ".agents" / "skills"
        self.skills.mkdir(parents=True)
        self.release.mkdir(parents=True)
        make_skill(self.release, CANON, "0.2.20")

    def run_assertion(self, *extra):
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.home),
            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        }
        return subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--release", str(self.release)]
            + ["--root", str(self.skills)]
            + list(extra),
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )

    def snapshot(self):
        return sorted(
            str(p.relative_to(self.home))
            for p in self.home.rglob("*")
        )

    # --- acceptance case 1 ---------------------------------------------------
    def test_two_installed_trees_fail_naming_both_paths(self):
        canon = make_skill(self.skills, CANON, "0.2.20")
        shadow = make_skill(self.shadow, SHADOW, "0.2.17")
        before = self.snapshot()
        result = self.run_assertion()
        after = self.snapshot()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("DUPLICATE-INSTALLED-TREE", result.stdout)
        self.assertIn(str(canon), result.stdout)
        self.assertIn(str(shadow), result.stdout)
        self.assertIn("summary", result.stdout.lower())
        # read-only: the assertion never deletes, moves or creates anything.
        self.assertEqual(before, after)

    # --- acceptance case 2 ---------------------------------------------------
    def test_version_mismatch_fails_naming_both_versions(self):
        tree = make_skill(self.skills, CANON, "0.2.19")
        result = self.run_assertion()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("VERSION-MISMATCH", result.stdout)
        self.assertIn(str(tree), result.stdout)
        self.assertIn("installed=0.2.19", result.stdout)
        self.assertIn("release=0.2.20", result.stdout)

    # --- acceptance case 3 ---------------------------------------------------
    def test_single_tree_at_released_version_passes(self):
        make_skill(self.skills, CANON, "0.2.20")
        result = self.run_assertion()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK: 1 skills", result.stdout)
        self.assertNotIn("FAIL:", result.stdout)

    # --- negative controls ---------------------------------------------------
    def test_tooling_failure_is_never_a_pass(self):
        result = self.run_assertion("--release", str(Path(self._tmp.name) / "absent"))
        # --release given twice: argparse keeps the last one, the absent dir.
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("TOOLING-FAILURE", result.stderr)
        self.assertNotIn("OK:", result.stdout)

    def test_missing_installed_version_file_never_passes(self):
        tree = make_skill(self.skills, CANON, None)
        result = self.run_assertion()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("VERSION-MISMATCH", result.stdout)
        self.assertIn(str(tree), result.stdout)
        self.assertIn("<no skill-version.txt>", result.stdout)

    def test_only_filter_limits_scope(self):
        make_skill(self.release, "49-signature-funnel", "v2.1.38")
        make_skill(self.skills, CANON, "0.2.20")
        make_skill(self.shadow, SHADOW, "0.2.17")
        make_skill(self.skills, "49-signature-funnel", "v2.1.38")
        # Unfiltered: the duplicated Skill 83 fails.
        self.assertEqual(self.run_assertion().returncode, 1)
        # Filtered to Skill 49: one tree, released version, passes.
        result = self.run_assertion("--only", "49")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK: 1 skills", result.stdout)

    def test_skip_does_not_compare_version(self):
        make_skill(self.skills, CANON, "0.2.19")
        result = self.run_assertion("--skip", CANON)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SKIP: %s" % CANON, result.stdout)
        self.assertIn("skipped=1", result.stdout)
        self.assertNotIn("OK: 1 skills", result.stdout)

    def test_skip_never_excuses_a_duplicate_tree(self):
        make_skill(self.skills, CANON, "0.2.19")
        make_skill(self.shadow, SHADOW, "0.2.17")
        result = self.run_assertion("--skip", CANON)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("DUPLICATE-INSTALLED-TREE", result.stdout)

    def test_absent_shadow_is_the_healthy_case(self):
        make_skill(self.skills, CANON, "0.2.20")
        self.assertFalse(self.shadow.exists())
        result = self.run_assertion()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK: 1 skills", result.stdout)


if __name__ == "__main__":
    unittest.main()
