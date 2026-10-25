#!/usr/bin/env python3
"""Skill 71 release version stamps must agree.

Finding 43: VERSION sat at 1.3.4 while skill-version.txt and SKILL.md were at
1.3.7, and scripts/install_local.py accepts the first valid stamp it finds, so a
split was invisible to every install and update path. This check reads all three
in-tree stamps and fails when any is missing, unreadable, not a dotted version,
or different from the others. Run directly or through tests/run_tests.py.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOTTED = re.compile(r"^\d+(?:\.\d+)+$")
STAMPS = ("VERSION", "skill-version.txt")


def skill_md_version(root=ROOT):
    """The `version:` line inside SKILL.md's YAML front matter, unquoted."""
    lines = (root / "SKILL.md").read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise AssertionError("SKILL.md has no front matter")
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("version:"):
            return line[len("version:"):].strip().strip("\"'")
    raise AssertionError("SKILL.md front matter has no version line")


def stamps(root=ROOT):
    found = {name: (root / name).read_text(encoding="utf-8").strip() for name in STAMPS}
    found["SKILL.md"] = skill_md_version(root)
    return found


class VersionLockstepTests(unittest.TestCase):
    def test_every_stamp_is_a_dotted_version(self):
        for name, value in stamps().items():
            self.assertRegex(value, DOTTED, f"{name} is {value!r}, not a dotted version")

    def test_all_three_stamps_agree(self):
        found = stamps()
        distinct = sorted(set(found.values()))
        self.assertEqual(
            len(distinct), 1,
            "release stamps disagree: " + ", ".join(f"{k}={v}" for k, v in sorted(found.items())),
        )

    def test_check_catches_a_split(self):
        """The check must fail on the packed 1.3.4/1.3.7 split, not pass vacuously."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text("---\nname: x\nversion: 1.3.7\n---\n", encoding="utf-8")
            (root / "skill-version.txt").write_text("1.3.7\n", encoding="utf-8")
            (root / "VERSION").write_text("1.3.4\n", encoding="utf-8")
            self.assertEqual(len(set(stamps(root).values())), 2)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
