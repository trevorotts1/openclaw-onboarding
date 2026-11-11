"""Skills 44 and 50 produce no visual design, so they do not read Skill 45 (issue 24).

The review asked whether either skill consults the Design Intelligence Library. Neither does, on
purpose: the email and workflow rails carry approved copy, not imagery. This keeps that a stated
boundary instead of an accident: each SKILL.md says so in one sentence, and no code, data or
script of either skill (outside tests) references Skill 45. A skill that starts to need a design
card has to change this test and the sentence together.

Run from the repository root:
    python3 -m pytest 50-email-engine/tests/test_skill_45_boundary.py -q
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ("44-convert-and-flow-operator", "50-email-engine")
SENTENCE = "produces no visual design and does not read Skill 45"
REFERENCE = re.compile(r"skill[ -]45|45-design|design[-_ ]intelligence", re.I)
SCANNED = {".md", ".py", ".json", ".sh"}
SKIP_DIRS = {"tests", "node_modules", "__pycache__", ".git", "working"}


class Skill45Boundary(unittest.TestCase):
    def test_each_skill_md_states_the_boundary(self):
        for skill in SKILLS:
            text = (ROOT / skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn(SENTENCE, " ".join(text.split()), f"{skill}/SKILL.md lost the Skill 45 boundary sentence")

    def test_nothing_else_in_either_skill_references_skill_45(self):
        hits = []
        for skill in SKILLS:
            for path in (ROOT / skill).rglob("*"):
                rel = path.relative_to(ROOT / skill)
                if (path.suffix not in SCANNED or not path.is_file() or SKIP_DIRS & set(rel.parts)
                        or rel == Path("SKILL.md") or path.name.startswith("test_")):
                    continue
                for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if REFERENCE.search(line):
                        hits.append(f"{skill}/{rel}:{number}: {line.strip()[:100]}")
        self.assertEqual(hits, [], "a skill that reads Skill 45 must change SKILL.md and this test together:\n"
                         + "\n".join(hits[:20]))


if __name__ == "__main__":
    unittest.main()
