"""The installer-registration dependency accepts either directory convention.

999 links skills from CONTROL/bundled-skills.txt, so a bare slug is as valid as
a numbered directory. Both are accepted only when the SKILL.md frontmatter name
agrees with the directory slug; a mismatch is a finding, never a pass.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import dependencies  # noqa: E402

ENTRY = {
    "id": "installer-registration-launcher",
    "kind": "installer_registration",
    "ref": "83-black-friday-launcher/SKILL.md",
    "required": True,
}


def _tree(root: Path, directory: str, name: str) -> Path:
    skill = root / ".claude" / "skills" / directory
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: fixture\n---\n\n# fixture\n",
        encoding="utf-8")
    return root


class InstallerRegistrationConventionTests(unittest.TestCase):
    def test_bare_slug_with_matching_frontmatter_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(Path(tmp), "black-friday-launcher",
                         "black-friday-launcher")
            result = dependencies._present(ENTRY, root)
        self.assertEqual(result["status"], "present", result["evidence"])
        self.assertIn("numeric_prefix=False", result["evidence"])

    def test_bare_slug_with_mismatched_frontmatter_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(Path(tmp), "black-friday-launcher", "some-other-skill")
            result = dependencies._present(ENTRY, root)
        self.assertEqual(result["status"], "missing", result["evidence"])

    def test_numeric_directory_with_matching_frontmatter_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(Path(tmp), "83-black-friday-launcher",
                         "black-friday-launcher")
            result = dependencies._present(ENTRY, root)
        self.assertEqual(result["status"], "present", result["evidence"])
        self.assertIn("numeric_prefix=True", result["evidence"])

    def test_numeric_directory_with_mismatched_frontmatter_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(Path(tmp), "83-black-friday-launcher", "wrong-name")
            result = dependencies._present(ENTRY, root)
        self.assertEqual(result["status"], "missing", result["evidence"])

    def test_absent_skill_md_frontmatter_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / ".claude" / "skills" / "black-friday-launcher"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("# no frontmatter\n", encoding="utf-8")
            result = dependencies._present(ENTRY, Path(tmp))
        self.assertEqual(result["status"], "missing", result["evidence"])
        self.assertIn("frontmatter_name=None", result["evidence"])

    def test_the_real_repository_registers_the_skill(self):
        result = dependencies._present(ENTRY, dependencies._repo_root())
        self.assertEqual(result["status"], "present", result["evidence"])
        self.assertRegex(result["evidence"],
                         r"directory=(83-)?black-friday-launcher")
        self.assertIn("frontmatter_name='black-friday-launcher'",
                      result["evidence"])


if __name__ == "__main__":
    unittest.main()
