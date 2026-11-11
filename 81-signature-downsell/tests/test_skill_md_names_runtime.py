#!/usr/bin/env python3
"""Issue 92 (harmony review): SKILL.md names Skill 81's runtime.

Skill 81 ships libraries (validators and adapters), not a command. Its runtime
composition is Skill 49's ``downsell_wrapper.py``: the wrapper reads a request,
calls the validators here and writes the result. ``VALIDATOR-CONSUMERS.json``
and the wrapper's own header already say so; SKILL.md never did. This test
fails when SKILL.md stops naming the wrapper, when the named path does not
exist in the repository, or when SKILL.md omits any consumer that
``VALIDATOR-CONSUMERS.json`` declares.

Run: python3 -m unittest discover -s tests          (from this directory)
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SKILL_MD = ROOT / "SKILL.md"
RUNTIME = "49-signature-funnel/scripts/downsell_wrapper.py"


def consumer_paths():
    declared = json.loads(
        (ROOT / "VALIDATOR-CONSUMERS.json").read_text(encoding="utf-8"))
    return {c["path"] for entry in declared["pinned"].values()
            for c in entry["consumers"]}


class SkillMdNamesRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SKILL_MD.read_text(encoding="utf-8")

    def test_skill_md_names_the_wrapper_path(self):
        self.assertIn(RUNTIME, self.text,
                      "SKILL.md must name %s as the runtime composition" % RUNTIME)

    def test_the_named_runtime_exists_in_the_repository(self):
        self.assertTrue((REPO / RUNTIME).is_file(),
                        "%s is named by SKILL.md but missing" % RUNTIME)

    def test_the_runtime_is_the_declared_consumer(self):
        self.assertIn(RUNTIME, consumer_paths())

    def test_every_declared_consumer_is_named(self):
        for path in sorted(consumer_paths()):
            self.assertIn(path, self.text,
                          "VALIDATOR-CONSUMERS.json declares %s; SKILL.md must name it" % path)

    def test_skill_md_calls_the_wrapper_the_runtime_composition(self):
        # The paragraph must say the package is invoked through the wrapper,
        # not leave a reader to look for a command of its own.
        self.assertRegex(self.text, r"(?i)runtime composition")


if __name__ == "__main__":
    unittest.main()
