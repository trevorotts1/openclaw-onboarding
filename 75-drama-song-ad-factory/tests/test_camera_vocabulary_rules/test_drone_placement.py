"""DEL-16: drone shots sit on establishing or transition moments only.

Run:  python3 tests/test_camera_vocabulary_rules/test_drone_placement.py
stdlib only.
"""
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL / "scripts"))

from camera_signatures.rules import (  # noqa: E402
    DRONE_ALLOWED_PLACEMENTS,
    DRONE_MISPLACED,
    PLACEMENTS,
    UNKNOWN_PLACEMENT,
    check_drone_placement,
)


def shot(placement, move="drone_fly_in", sid="s1"):
    return {"shot_id": sid, "placement": placement, "moves": [move]}


class AllowedMoments(unittest.TestCase):
    def test_a_drone_opening_the_video_is_allowed(self):
        self.assertEqual(check_drone_placement([shot("video_start")]), [])

    def test_a_drone_opening_a_scene_is_allowed(self):
        self.assertEqual(check_drone_placement([shot("scene_start")]), [])

    def test_a_drone_on_a_transition_is_allowed(self):
        self.assertEqual(check_drone_placement([shot("transition")]), [])

    def test_the_allowed_set_is_exactly_the_establishing_and_transition_moments(self):
        self.assertEqual(
            set(DRONE_ALLOWED_PLACEMENTS),
            {"video_start", "scene_start", "scene_transition", "transition",
             "scene_end", "reveal"})


class ForbiddenMoments(unittest.TestCase):
    def test_a_drone_on_a_dialogue_close_up_is_refused(self):
        errs = check_drone_placement([shot("dialogue_close_up")])
        self.assertEqual(errs, ["%s:s1:dialogue_close_up" % DRONE_MISPLACED])

    def test_a_drone_on_a_closing_beat_is_refused(self):
        errs = check_drone_placement([shot("closing")])
        self.assertTrue(errs and errs[0].startswith(DRONE_MISPLACED))

    def test_a_drone_in_the_middle_of_a_scene_is_refused(self):
        errs = check_drone_placement([shot("mid_scene")])
        self.assertTrue(errs and errs[0].startswith(DRONE_MISPLACED))

    def test_an_unknown_placement_is_refused(self):
        errs = check_drone_placement([shot("rooftop")])
        self.assertEqual(errs, ["%s:s1:rooftop" % UNKNOWN_PLACEMENT])

    def test_a_missing_placement_is_refused(self):
        errs = check_drone_placement([{"shot_id": "s9", "moves": ["drone_orbit"]}])
        self.assertEqual(errs, ["%s:s9:None" % UNKNOWN_PLACEMENT])

    def test_one_bad_drone_among_good_ones_is_still_reported(self):
        errs = check_drone_placement([
            shot("scene_start", sid="ok"),
            shot("dialogue_close_up", sid="bad"),
        ])
        self.assertEqual(len(errs), 1)
        self.assertIn(":bad:", errs[0])

    def test_every_one_of_the_reported_errors_is_machine_stable(self):
        for err in check_drone_placement([shot("dialogue_close_up")]):
            self.assertTrue(err.startswith(DRONE_MISPLACED + ":"))
            self.assertTrue(err.endswith(":dialogue_close_up"))


class NonDroneShotsAreNotJudged(unittest.TestCase):
    def test_a_dolly_on_a_dialogue_close_up_is_fine(self):
        self.assertEqual(
            check_drone_placement([shot("dialogue_close_up", move="dolly_in")]),
            [])

    def test_a_static_shot_anywhere_is_fine(self):
        self.assertEqual(
            check_drone_placement([shot("closing", move="static")]), [])

    def test_a_non_dict_entry_is_skipped_not_crashed(self):
        self.assertEqual(check_drone_placement(["drone_fly_in", None]), [])


class PlacementVocabulary(unittest.TestCase):
    def test_the_placements_are_named(self):
        self.assertEqual(
            set(PLACEMENTS),
            {"video_start", "scene_start", "scene_transition", "transition",
             "scene_end", "reveal", "closing",
             "dialogue_close_up", "mid_scene"})

    def test_every_preset_placement_is_a_known_placement(self):
        import camera_signatures as cs
        for p in cs.PRESETS:
            for place in p["drop_at"]:
                self.assertIn(place, PLACEMENTS, p["id"])

    def test_the_dialogue_close_up_and_mid_scene_are_never_allowed_for_a_drone(self):
        for place in ("dialogue_close_up", "mid_scene", "closing"):
            self.assertNotIn(place, DRONE_ALLOWED_PLACEMENTS)


if __name__ == "__main__":
    unittest.main()
