"""DEL-16: one generated move per clip; whip pan is never one of them.

Run:  python3 tests/test_camera_vocabulary_rules/test_one_move_per_clip.py
stdlib only.
"""
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL / "scripts"))

from camera_signatures.rules import (  # noqa: E402
    CLIP_SECONDS_MAX,
    CLIP_TOO_LONG,
    EDIT_TRANSITION_MOVES,
    MAX_MOVES_PER_CLIP,
    REFUSED_AS_GENERATED_MOVE,
    TOO_MANY_MOVES,
    RefusedMove,
    check_generated_move,
    check_one_move_per_clip,
    require_generated_move,
)


class OneMovePerClip(unittest.TestCase):
    def test_the_limit_is_one(self):
        self.assertEqual(MAX_MOVES_PER_CLIP, 1)

    def test_a_single_move_passes(self):
        self.assertEqual(
            check_one_move_per_clip([{"clip_id": "c1", "moves": ["dolly_in"]}]),
            [])

    def test_a_static_clip_passes(self):
        self.assertEqual(
            check_one_move_per_clip([{"clip_id": "c1", "moves": ["static"]}]),
            [])

    def test_two_moves_in_one_clip_fail(self):
        errs = check_one_move_per_clip(
            [{"clip_id": "c1", "moves": ["dolly_in", "pan"]}])
        self.assertEqual(errs, ["%s:c1" % TOO_MANY_MOVES])

    def test_three_moves_in_one_clip_fail_once_not_thrice(self):
        errs = check_one_move_per_clip(
            [{"clip_id": "c1", "moves": ["pan", "tilt", "crane"]}])
        self.assertEqual(errs, ["%s:c1" % TOO_MANY_MOVES])

    def test_a_single_move_field_is_understood_too(self):
        self.assertEqual(
            check_one_move_per_clip([{"clip_id": "c1", "move": "dolly_out"}]),
            [])

    def test_the_bad_clip_is_named_and_the_good_one_is_not(self):
        errs = check_one_move_per_clip([
            {"clip_id": "good", "moves": ["dolly_in"]},
            {"clip_id": "bad", "moves": ["pan", "tilt"]},
        ])
        self.assertEqual(errs, ["%s:bad" % TOO_MANY_MOVES])
        self.assertNotIn("good", errs[0])

    def test_an_empty_plan_is_not_an_error(self):
        self.assertEqual(check_one_move_per_clip([]), [])

    def test_a_malformed_plan_fails_closed(self):
        self.assertEqual(check_one_move_per_clip("not a list"),
                         [TOO_MANY_MOVES])

    def test_a_clip_longer_than_six_seconds_is_reported(self):
        errs = check_one_move_per_clip(
            [{"clip_id": "c1", "moves": ["static"], "start": 0.0, "end": 9.0}])
        self.assertEqual(errs, ["%s:c1" % CLIP_TOO_LONG])
        self.assertEqual(CLIP_SECONDS_MAX, 6.0)

    def test_a_six_second_clip_is_fine(self):
        self.assertEqual(
            check_one_move_per_clip(
                [{"clip_id": "c1", "moves": ["static"],
                  "start": 0.0, "end": CLIP_SECONDS_MAX}]),
            [])


class WhipPanRefusal(unittest.TestCase):
    def test_whip_pan_is_not_a_single_generated_move(self):
        self.assertEqual(
            check_generated_move("whip_pan"),
            [REFUSED_AS_GENERATED_MOVE])

    def test_the_refusal_also_fires_through_the_plan_check(self):
        errs = check_one_move_per_clip(
            [{"clip_id": "c1", "moves": ["whip_pan"]}])
        self.assertIn("%s:c1" % REFUSED_AS_GENERATED_MOVE, errs)

    def test_whip_pan_inside_a_two_move_clip_reports_both_problems(self):
        errs = check_one_move_per_clip(
            [{"clip_id": "c1", "moves": ["whip_pan", "pan"]}])
        self.assertIn("%s:c1" % TOO_MANY_MOVES, errs)
        self.assertIn("%s:c1" % REFUSED_AS_GENERATED_MOVE, errs)

    def test_the_hard_stop_form_raises(self):
        with self.assertRaises(RefusedMove) as ctx:
            require_generated_move("whip_pan")
        self.assertIn("edit transition", str(ctx.exception))

    def test_the_hard_stop_form_passes_ordinary_moves_through(self):
        for m in ("dolly_in", "static", "drone_fly_in"):
            self.assertEqual(require_generated_move(m), m)

    def test_edit_transition_moves_are_whip_pan_and_nothing_else(self):
        self.assertEqual(set(EDIT_TRANSITION_MOVES), {"whip_pan"})

    def test_an_ordinary_move_is_never_refused(self):
        for m in ("dolly_in", "dolly_out", "drone_fly_in", "pan", "static"):
            self.assertEqual(check_generated_move(m), [])


if __name__ == "__main__":
    unittest.main()
