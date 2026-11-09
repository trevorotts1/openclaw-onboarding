#!/usr/bin/env python3
"""Tests for T-26 clause (d): the public and private answer duties are two
different permissions, read from the `- duty:` line a handoff carries, and an
unreadable duty is never permissive.

Run from the skill root:
    python3 -m pytest tools/tests/test_answer_duty.py -q
or directly:
    python3 tools/tests/test_answer_duty.py
"""

import sys
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from answer_duty import (  # noqa: E402
    CHANNEL_DM,
    CHANNEL_PUBLIC_COMMENT,
    CHANNEL_SMS,
    PRIVATE_ANSWER_DUTY,
    PUBLIC_ANSWER_DUTY,
    duty_from_log_text,
    outbound_channel_allowed,
)

PUBLIC_LOG = (
    "# Conversation log - author_555\n"
    "### Inbound - public comment (facebook) - 2026-10-25T00:00:00Z\n"
    "- source: Skill 35 comment-reader (synthetic handoff)\n"
    "- duty: public_answer\n"
    "- text: how do I book?\n"
)


class DutyReadTests(unittest.TestCase):
    def test_reads_the_stamped_duty(self):
        self.assertEqual(duty_from_log_text(PUBLIC_LOG), PUBLIC_ANSWER_DUTY)

    def test_a_trailing_annotation_still_parses(self):
        # The pre-T-26 line carried a parenthetical; a log already on disk must
        # not become unreadable (which would fail closed on a valid turn).
        self.assertEqual(
            duty_from_log_text("- duty: public_answer (answer in the thread)\n"),
            PUBLIC_ANSWER_DUTY)

    def test_no_duty_line_reads_as_none(self):
        self.assertIsNone(duty_from_log_text("- text: no duty here\n"))
        self.assertIsNone(duty_from_log_text(""))

    def test_the_last_turn_wins(self):
        # Append-only log: an older turn's duty must not license a newer one.
        two = ("- duty: private_answer\n- text: a\n"
               "- duty: public_answer\n- text: b\n")
        self.assertEqual(duty_from_log_text(two), PUBLIC_ANSWER_DUTY)


class GateBehaviourTests(unittest.TestCase):
    def test_public_duty_allows_only_the_public_thread(self):
        duty = duty_from_log_text(PUBLIC_LOG)
        self.assertTrue(outbound_channel_allowed(duty, CHANNEL_PUBLIC_COMMENT))
        self.assertFalse(outbound_channel_allowed(duty, CHANNEL_DM),
                         "a public-answer turn must not get an unsolicited DM")
        self.assertFalse(outbound_channel_allowed(duty, CHANNEL_SMS),
                         "a public-answer turn must never be answered by SMS")

    def test_private_duty_is_a_different_permission(self):
        # The inverse: the SAME gate permits DM for the private duty, so the two
        # duties are distinct behaviours rather than two names for one rule.
        self.assertTrue(outbound_channel_allowed(PRIVATE_ANSWER_DUTY, CHANNEL_DM))
        self.assertFalse(
            outbound_channel_allowed(PRIVATE_ANSWER_DUTY, CHANNEL_PUBLIC_COMMENT))

    def test_unknown_or_absent_duty_fails_closed(self):
        for duty in ("zzz-not-a-duty", "", None, "PUBLIC_ANSWER"):
            with self.subTest(duty=duty):
                for channel in (CHANNEL_PUBLIC_COMMENT, CHANNEL_DM, CHANNEL_SMS):
                    self.assertFalse(outbound_channel_allowed(duty, channel))


if __name__ == "__main__":
    unittest.main(verbosity=2)
