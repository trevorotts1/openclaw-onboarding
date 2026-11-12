"""Skill 49 owner approvals are collected in chat, by button or in Command Center (any one works).

Free: reads the skill's own docs and refusal strings; nothing calls Command Center.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ChatApprovalWording(unittest.TestCase):
    def test_skill_md_names_the_one_helper_every_kind_and_the_three_ways(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        start = text.index("## Owner approvals: in chat, by button, or in Command Center")
        section = text[start:text.index("## Delegation seams", start)]
        for needle in ("owner_approval.py", "chat-decision", "plan_build", "design_board", "paid_asset_budget",
                       "stub_render", "automation_write", "publish", "Code: <first 6 characters of",
                       "inline", "attached", "never records a yes itself"):
            self.assertIn(needle, section, needle)

    def test_refusals_do_not_send_the_owner_to_command_center_only(self):
        for name in ("dispatch_launch.py", "legacy_downsell_images.py", "prove_sf_build.py"):
            src = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertTrue("in chat" in src, name)

    def test_launch_mode_doc_says_approvals_reach_the_owner_in_chat(self):
        self.assertIn("Owner approvals reach the owner in chat", (ROOT / "LAUNCH_MODE.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
