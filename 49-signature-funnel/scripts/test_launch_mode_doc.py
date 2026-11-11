#!/usr/bin/env python3
"""test_launch_mode_doc.py - LAUNCH_MODE.md must not name a launch stage that no write target or
stage list represents (issue 48). Stdlib only. Run: python3 test_launch_mode_doc.py"""
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
DOC = (SKILL / "LAUNCH_MODE.md").read_text(encoding="utf-8")
# The four stage names the old DAG paragraph used that no code represents.
RETIRED = ("S44 provisioning", "S06 native install", "S44 workflow wiring",
           "integrated test", "activation approval")


def write_targets():
    src = (SKILL / "scripts" / "dispatch_launch.py").read_text(encoding="utf-8")
    m = re.search(r"^WRITE_TARGETS = \(([^)]*)\)", src, re.M)
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def skill83_stage_names():
    names = set()
    for f in (SKILL.parent / "83-black-friday-launcher" / "launcher_core").glob("*.py"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if re.match(r"\s*(?:\w+\s*=\s*)?(?:_?[A-Z_]*STAGES\w*)\s*=", line) or "STAGES" in line.split("=")[0]:
                names.update(re.findall(r'"([a-z][\w-]*)"', line))
    return names


class LaunchModeDoc(unittest.TestCase):
    def test_no_retired_stage_name(self):
        for name in RETIRED:
            self.assertNotIn(name, DOC)

    def test_dag_words_gone(self):
        self.assertNotIn("launch DAG", DOC)

    def test_every_backticked_stage_is_represented(self):
        para = DOC[DOC.index("What the launch chain enforces"):]
        allowed = write_targets() | skill83_stage_names() | {"waits_for", "dispatch_launch.WRITE_TARGETS"}
        for tok in re.findall(r"`([^`]+)`", para):
            self.assertIn(tok, allowed, f"LAUNCH_MODE.md names {tok!r}, which no write target or stage list represents")

    def test_all_write_targets_named(self):
        for t in write_targets():
            self.assertIn(f"`{t}`", DOC)


if __name__ == "__main__":
    unittest.main()
