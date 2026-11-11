"""Issue 82 (Skill 83 side): SKILL.md does not describe the siglaunch receiver as something that builds.

`44-convert-and-flow-operator/tools/siglaunch/receiver.py` has `PRODUCTION_ENTRY_ENABLED = False`. The
launch automations are built through `caf workflows build --from-automation-build` after the plan
reader, and the build journal is the receipt. SKILL.md once said both things, in different places.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text(encoding="utf-8")
RECEIVER = Path(__file__).resolve().parents[2] / "44-convert-and-flow-operator" / "tools" / "siglaunch" / "receiver" / "receiver.py"


class SiglaunchReceiverWordingTests(unittest.TestCase):
    def test_the_code_really_keeps_the_receiver_off(self):
        if not RECEIVER.is_file():
            self.skipTest("Skill 44 is not beside this skill")
        self.assertRegex(RECEIVER.read_text(encoding="utf-8"), r"PRODUCTION_ENTRY_ENABLED\s*=\s*False")

    def test_skill_md_says_it_is_not_a_production_entry_and_names_the_real_build_path(self):
        self.assertIn("PRODUCTION_ENTRY_ENABLED = False", SKILL)
        self.assertIn("caf workflows build --from-automation-build", SKILL)
        self.assertIn("the receipt is the build journal", SKILL)

    def test_skill_md_never_says_the_receiver_builds_or_issues_receipts(self):
        flat = re.sub(r"\s+", " ", SKILL)
        for claim in ("is the pipeline that builds and receipts", "receiver issues its own receipt",
                      "receiver issues its own"):
            self.assertNotIn(claim, flat)


if __name__ == "__main__":
    unittest.main()
