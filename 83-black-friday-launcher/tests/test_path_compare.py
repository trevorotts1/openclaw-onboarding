"""FIX-06 instrument control: the shared path helper discriminates, in both directions.

One file in two spellings through a symlinked directory must compare equal; two different
directories must not. A helper that only ever answers "equal" would turn every path assertion
in this suite into a rubber stamp, so both directions are asserted here.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from path_compare import artifact_identity, canonical, same_path  # noqa: E402


class PathCompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.real = Path(self.tmp.name) / "real"
        self.real.mkdir()
        self.link = Path(self.tmp.name) / "link"
        try:
            os.symlink(self.real, self.link)
        except (OSError, NotImplementedError):
            self.skipTest("this filesystem does not support symlinks")

    def test_one_file_in_two_spellings_compares_equal(self):
        self.assertEqual(canonical(self.link / "a.json"), canonical(self.real / "a.json"))
        self.assertTrue(same_path(self.link / "a.json", self.real / "a.json"))

    def test_two_different_directories_do_not_compare_equal(self):
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        self.assertFalse(same_path(self.link / "a.json", other / "a.json"))

    def test_artifact_identity_collapses_spellings_and_keeps_a_different_file_distinct(self):
        rows = [{"path": str(self.link / "a.png"), "sha256": "1" * 64},
                {"path": str(self.real / "a.png"), "sha256": "1" * 64},
                {"path": str(Path(self.tmp.name) / "other" / "a.png"), "sha256": "1" * 64}]
        self.assertEqual(len(artifact_identity(rows)), 2)


if __name__ == "__main__":
    unittest.main()
