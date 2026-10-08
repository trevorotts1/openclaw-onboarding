"""Skill 75 must never pin a model and must state that the user's choice wins."""
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
PIN = re.compile(r"fable|opus-chain|sonnet-chain|haiku-chain|ANTHROPIC_DEFAULT_\w+_MODEL", re.I)


class ModelChoice(unittest.TestCase):
    def test_skill_md_states_user_choice_wins(self):
        t = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("the user's choice wins", t)
        self.assertIn("never silently swap", t.lower().replace("silently swap in", "silently swap"))
        self.assertIn("fail silently", t)

    def test_no_model_pin_in_skill_docs(self):
        for f in [SKILL / "SKILL.md", *SKILL.glob("adapters/*/README.md"), *SKILL.glob("references/*.md")]:
            self.assertIsNone(PIN.search(f.read_text(encoding="utf-8")), str(f))


if __name__ == "__main__":
    unittest.main()
