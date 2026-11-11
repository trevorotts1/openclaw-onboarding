"""Issue 15: SOP-07 (the master orchestrator's funnel SOP) sends a Black Friday request to Skill 83.

SOP-07 is a declared dependency of Skill 83 (a `sop` row with a read receipt), and Skill 83 reads it, but
its own routing used to know nothing of Skill 83: a seasonal sale launch was only reachable through the
department-map intent triggers. The SOP text now names the skill's slug, and the slug must be a real
map entry, so the route cannot point at nothing.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import dependencies  # noqa: E402

REPO = SKILL_ROOT.parent
SOP_07 = REPO / "23-ai-workforce-blueprint" / "master-orchestrator-dept" / "SOP-07-Full-Funnel-Build-Orchestration.md"
SLUG = "black-friday-launcher"


class Sop07RoutingTests(unittest.TestCase):
    def test_step_1_names_the_launcher_for_a_seasonal_sale_launch(self):
        step_1 = SOP_07.read_text(encoding="utf-8").split("## Step 1", 1)[1].split("## Step 2", 1)[0]
        self.assertIn(SLUG, step_1)
        self.assertIn("83-black-friday-launcher", step_1)
        self.assertIn("Black Friday", step_1)
        self.assertIn("do NOT create the parent funnel epic", step_1)

    def test_the_slug_is_a_real_department_map_entry_with_intent_triggers(self):
        skills = json.loads((REPO / "23-ai-workforce-blueprint" / "skill-department-map.json").read_text(encoding="utf-8"))["skills"]
        entry = next(s for s in skills if s.get("slug") == SLUG)
        self.assertTrue(entry["intent_triggers"])
        self.assertTrue(entry["departments"])

    def test_the_sop_stays_a_declared_dependency_with_a_receipt_on_its_current_bytes(self):
        row = next(e for e in dependencies.load_manifest()["entries"]
                   if e["kind"] == "sop" and e["ref"].endswith("SOP-07-Full-Funnel-Build-Orchestration.md"))
        self.assertEqual(dependencies._present(row, dependencies._repo_root())["status"], "present")


if __name__ == "__main__":
    unittest.main()
