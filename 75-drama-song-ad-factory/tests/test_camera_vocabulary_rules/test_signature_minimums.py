"""DEL-16: the two-minute drone and dolly minimums, with the client decline.

Run:  python3 tests/test_camera_vocabulary_rules/test_signature_minimums.py
stdlib only.
"""
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL / "scripts"))

from camera_signatures.rules import (  # noqa: E402
    MIN_DOLLY_SHOTS,
    MIN_DRONE_SHOTS,
    MISSING_DOLLY_SHOT,
    MISSING_DRONE_SHOT,
    TWO_MINUTE_SECONDS,
    check_signature_minimums,
)


def shots(*moves):
    """Shot records carrying one move each."""
    return [{"shot_id": "s%d" % (i + 1), "moves": [m]} for i, m in enumerate(moves)]


class ConstantsMatchTheOrder(unittest.TestCase):
    def test_threshold_is_two_minutes(self):
        self.assertEqual(TWO_MINUTE_SECONDS, 120)
        self.assertEqual(MIN_DRONE_SHOTS, 1)
        self.assertEqual(MIN_DOLLY_SHOTS, 2)


class AtLeastTwoMinutes(unittest.TestCase):
    def test_empty_plan_at_two_minutes_fails_both_minimums(self):
        errs = check_signature_minimums(120, [])
        self.assertIn(MISSING_DRONE_SHOT, errs)
        self.assertIn(MISSING_DOLLY_SHOT, errs)

    def test_one_dolly_is_not_enough(self):
        errs = check_signature_minimums(180, shots("dolly_in"))
        self.assertIn(MISSING_DRONE_SHOT, errs)
        self.assertIn(MISSING_DOLLY_SHOT, errs)

    def test_one_drone_and_one_dolly_still_miss_the_dolly_floor(self):
        errs = check_signature_minimums(
            130, shots("drone_fly_in", "dolly_in"))
        self.assertNotIn(MISSING_DRONE_SHOT, errs)
        self.assertIn(MISSING_DOLLY_SHOT, errs)

    def test_one_drone_and_two_dollies_passes(self):
        errs = check_signature_minimums(
            120, shots("drone_fly_in", "dolly_in", "dolly_out"))
        self.assertEqual(errs, [])

    def test_a_long_video_passes_the_same_way(self):
        errs = check_signature_minimums(
            600, shots("drone_fly_over", "dolly_in", "lateral_truck"))
        self.assertEqual(errs, [])

    def test_an_aerial_angle_counts_as_the_drone_slot(self):
        # the order says "at least one drone OR aerial shot"
        errs = check_signature_minimums(
            240, shots("aerial_reveal", "dolly_in", "dolly_out"))
        self.assertEqual(errs, [])

    def test_non_signature_moves_do_not_count(self):
        errs = check_signature_minimums(
            150, shots("static", "zoom_in", "pan", "crane"))
        self.assertIn(MISSING_DRONE_SHOT, errs)
        self.assertIn(MISSING_DOLLY_SHOT, errs)

    def test_bare_move_ids_and_clip_records_are_both_accepted(self):
        self.assertEqual(
            check_signature_minimums(
                150, ["drone_fly_in", "dolly_in", "dolly_out"]), [])
        self.assertEqual(
            check_signature_minimums(
                150, [{"clip_id": "c1", "move": "drone_fly_in"},
                      {"clip_id": "c2", "moves": ["dolly_in"]},
                      {"clip_id": "c3", "moves": ["dolly_out"]}]), [])


class UnderTwoMinutes(unittest.TestCase):
    def test_a_one_minute_video_is_not_held_to_the_minimums(self):
        self.assertEqual(check_signature_minimums(60, []), [])
        self.assertEqual(check_signature_minimums(59, shots("static")), [])
        self.assertEqual(check_signature_minimums(119, shots("pan")), [])

    def test_the_boundary_is_inclusive(self):
        # 120 seconds IS two minutes, so the rule applies there
        self.assertIn(MISSING_DRONE_SHOT, check_signature_minimums(120, []))
        self.assertEqual(check_signature_minimums(119.99, []), [])

    def test_a_non_numeric_duration_never_fires_the_rule(self):
        self.assertEqual(check_signature_minimums(None, []), [])
        self.assertEqual(check_signature_minimums("120", []), [])
        self.assertEqual(check_signature_minimums(True, []), [])


class ClientDeclines(unittest.TestCase):
    def test_decline_releases_both_minimums(self):
        errs = check_signature_minimums(300, [], client_declined=True)
        self.assertEqual(errs, [])

    def test_decline_beats_a_half_filled_plan(self):
        errs = check_signature_minimums(
            300, shots("static"), client_declined=True)
        self.assertEqual(errs, [])

    def test_a_decline_on_a_short_video_changes_nothing(self):
        self.assertEqual(
            check_signature_minimums(60, [], client_declined=True), [])

    def test_without_the_decline_the_rule_still_bites(self):
        self.assertIn(
            MISSING_DRONE_SHOT, check_signature_minimums(300, []))


if __name__ == "__main__":
    unittest.main()
