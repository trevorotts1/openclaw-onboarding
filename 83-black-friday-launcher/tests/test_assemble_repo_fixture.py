"""F7: a client package never references a repo fixture path.

A page result may list a repo fixture as an artifact (the downsell wrapper lists its --copy document;
test-mode runs point that at 81-signature-downsell/fixtures/valid-downsell-page.json). Assembly used to
lay each file out by its folder under the common parent of all the piece's sources, so the repo's own
directory names (tree-copy/81-signature-downsell/fixtures/...) became part of the delivered package.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from launcher_core import checks, intake, package, route  # noqa: E402
from launcher_core.constants import REPO_ROOT  # noqa: E402
from test_launcher_core import base_intake, make_pieces, stub_council  # noqa: E402

FIXTURE = REPO_ROOT / "81-signature-downsell" / "fixtures" / "valid-downsell-page.json"


class RepoFixtureNeverInPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "run"
        self.normalized = intake.validate(base_intake())
        self.graph = route.compile_route(self.normalized)
        self.pieces = make_pieces(self.run_dir, self.graph, self.normalized)
        self.assertTrue(FIXTURE.is_file(), FIXTURE)
        self.pieces["landing"]["artifacts"].append(
            {"path": str(FIXTURE), "sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest()})

    def test_test_only_package_lays_a_repo_fixture_out_without_repo_folders(self):
        out = package.assemble(self.run_dir, self.normalized, self.graph, self.pieces,
                               council_runner=stub_council)
        landing = next(p for p in out["manifest"]["pieces"] if p["role"] == "landing")
        paths = [a["path"] for a in landing["artifacts"]]
        self.assertEqual(len(paths), 2)
        for rel in paths:
            self.assertTrue((self.run_dir / rel).is_file(), rel)
            for repo_part in ("81-signature-downsell", "fixtures", REPO_ROOT.name):
                self.assertNotIn(repo_part, Path(rel).parts, rel)
        self.assertEqual(checks.check_package(self.run_dir / "package-manifest.json", self.run_dir), [])

    def test_a_repo_fixture_is_told_from_the_runs_own_file(self):
        # assemble refuses a client package (test_only false) that holds one: AF-LAUNCH-PKG-REPO-FIXTURE
        self.assertTrue(package._is_repo_fixture(FIXTURE, [self.run_dir]))
        self.assertFalse(package._is_repo_fixture(self.run_dir / "pieces" / "x.html", [self.run_dir]))
        self.assertFalse(package._is_repo_fixture(Path(self.tmp.name) / "fixtures" / "x.json", [self.run_dir]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
