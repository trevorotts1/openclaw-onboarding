"""Issue 80 (harmony review): SKILL.md says one thing about the builder.

`80-signature-upsell/SKILL.md` used to say, in its frontmatter, that "there is
no production HTML builder" while its body (and the file system) ship
`components/pages/build_production_pages.py`. Skill 83 then repeated the
frontmatter's claim to the client. This test fails when the frontmatter and the
body disagree with each other or with the disk about the builder's existence,
and when the frontmatter still carries the stale denial.

Run from the skill root:  python3 -m unittest discover -s tests
"""

import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SKILL_MD = SKILL / "SKILL.md"
BUILDER_REL = "components/pages/build_production_pages.py"
BUILDER_NAME = "build_production_pages.py"
# A statement that the skill has NO production page/HTML builder.
DENIAL = re.compile(
    r"\bno\s+production\s+(?:html\s+|page\s+)?(?:page\s+)?(?:constructor|builder)\b",
    re.IGNORECASE)


def _split(text):
    match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.DOTALL)
    assert match, "SKILL.md has no frontmatter block"
    return match.group(1), match.group(2)


def _description(frontmatter):
    for line in frontmatter.splitlines():
        if line.startswith("description:"):
            return line[len("description:"):].strip()
    raise AssertionError("SKILL.md frontmatter has no description")


class SkillMdBuilderConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frontmatter, cls.body = _split(SKILL_MD.read_text(encoding="utf-8"))
        cls.description = _description(cls.frontmatter)
        cls.builder_exists = (SKILL / BUILDER_REL).is_file()

    def test_builder_exists_on_disk(self):
        self.assertTrue(self.builder_exists, f"{BUILDER_REL} is missing")

    def test_body_names_the_builder(self):
        self.assertIn(BUILDER_NAME, self.body)

    def test_frontmatter_names_the_builder(self):
        self.assertIn(BUILDER_NAME, self.description)

    def test_frontmatter_does_not_deny_the_builder(self):
        self.assertIsNone(
            DENIAL.search(self.description),
            "frontmatter says there is no production builder: "
            + self.description)

    def test_body_does_not_deny_the_builder(self):
        self.assertIsNone(DENIAL.search(self.body))

    def test_frontmatter_body_and_disk_agree(self):
        said_in_front = bool(DENIAL.search(self.description))
        said_in_body = bool(DENIAL.search(self.body))
        self.assertEqual(said_in_front, said_in_body)
        self.assertEqual(said_in_front, not self.builder_exists)

    def test_frontmatter_and_body_both_state_the_test_only_refusal(self):
        # The builder refuses test_only copy on a live launch (issue 4); both
        # the frontmatter and the body say so.
        claim = re.compile(r"marked\s+`?test_only`?\s+on\s+a\s+launch")
        flat = lambda t: re.sub(r"\s*\n>?\s*", " ", t)
        self.assertRegex(flat(self.description), claim)
        self.assertRegex(flat(self.body), claim)

    def test_denial_pattern_catches_the_original_wording(self):
        # Control: the matcher must fire on the sentence this test replaces.
        self.assertTrue(DENIAL.search(
            "U1 and U2 are design deliverables: there is no production HTML builder"))
        self.assertTrue(DENIAL.search("Skill 80 has no production page builder"))
        self.assertIsNone(DENIAL.search("it ships ONE production constructor"))


if __name__ == "__main__":
    unittest.main()
