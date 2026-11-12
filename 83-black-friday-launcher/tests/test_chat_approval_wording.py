"""Chat approvals: no agent-facing or client-facing refusal says Command Center is the only place to approve,
and the Skill 83 docs tell the agent to deliver the review material into the chat.

Free: nothing here calls Command Center or a provider.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

from launcher_core import image_plan  # noqa: E402


class PaidBudgetRefusalWording(unittest.TestCase):
    def test_refused_budget_says_every_way_to_approve(self):
        def verify(*a, **k):
            raise RuntimeError("no record")

        with mock.patch.object(image_plan, "_approval_verify", lambda: verify):
            with self.assertRaises(image_plan.ImagePlanError) as ctx:
                image_plan._verify_paid_budget("apr_00000001", "a" * 64, 5000, "USD")
        text = str(ctx.exception)
        self.assertIn("right here", text)
        self.assertIn("button", text)
        self.assertIn("Command Center", text)
        self.assertNotIn("in Command Center by replying", text)


class DocsDeliverToChat(unittest.TestCase):
    def test_skill_and_dispatch_docs_deliver_review_material_into_chat(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        dispatch = (SKILL_ROOT / "DISPATCH.md").read_text(encoding="utf-8")
        for needle in ("chat-decision", "--deliver telegram", "Code: <first 6 characters of the request id>",
                       "Any of the three works", "design_board", "paid_asset_budget"):
            self.assertIn(needle, skill, needle)
        self.assertIn("--view-url", skill)
        self.assertIn("--kind design_board", dispatch)
        self.assertIn("into the client's chat", dispatch)
        # the old rule that a chat yes only re-sends a link is gone
        self.assertNotIn("only a trigger to resend the link", skill)
        self.assertNotIn("message --chat-said-approved", skill)

    def test_chat_stage_stop_message_points_at_the_chat_not_just_the_file(self):
        src = (SKILL_ROOT / "launcher_core" / "image_stages.py").read_text(encoding="utf-8")
        self.assertIn("IN CHAT", src)
        self.assertIn("--approval-id", src)


if __name__ == "__main__":
    unittest.main()
