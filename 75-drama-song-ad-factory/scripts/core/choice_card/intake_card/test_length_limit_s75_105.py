#!/usr/bin/env python3
"""S75-105: the card never sells a length the song stage refuses.

The ceiling is read from ``prompt_limits.suno_caps()`` (the one cap table),
never typed in this file. Every purpose's LENGTH screen and the campaign's
EPISODE LENGTH screen must offer only durations at or under it, and the
duration registry itself stays unchanged.

Run: python3 -B scripts/core/choice_card/intake_card/test_length_limit_s75_105.py
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, CORE)

import prompt_limits  # noqa: E402
from choice_card.intake_card import intake_card as IC  # noqa: E402
from music_styles import music_styles as MS  # noqa: E402


def ceiling():
    """The longest song the song stage will make, from the cap table."""
    return prompt_limits.suno_caps()["duration"]["max_seconds"]


def offered_seconds(question):
    return [IC._vm().length_seconds(row[0]) for row in question["options"]]


class LengthLimit(unittest.TestCase):
    def test_the_cap_is_a_real_number(self):
        self.assertIsInstance(ceiling(), int)

    def test_no_purpose_offers_a_length_over_the_song_limit(self):
        cap = ceiling()
        for purpose in ("campaign", "testimonial", "lesson", "paid_ad", "short_post"):
            with self.subTest(purpose=purpose):
                secs = offered_seconds(IC._length_q(purpose))
                self.assertTrue(secs, purpose)
                self.assertEqual([s for s in secs if s > cap], [], purpose)

    def test_the_campaign_episode_length_stays_under_the_song_limit(self):
        cap = ceiling()
        secs = offered_seconds(IC._episode_length_q())
        self.assertTrue(secs)
        self.assertEqual([s for s in secs if s > cap], [])

    def test_exactly_the_registry_durations_over_the_limit_are_dropped(self):
        cap = ceiling()
        expected = [s for s in MS.CANONICAL_DURATION_S if s <= cap]
        self.assertEqual(offered_seconds(IC._length_q("campaign")), expected)
        self.assertEqual(offered_seconds(IC._episode_length_q()), expected)

    def test_the_duration_registry_is_unchanged(self):
        self.assertIn(600, MS.CANONICAL_DURATION_S)


if __name__ == "__main__":
    unittest.main()
