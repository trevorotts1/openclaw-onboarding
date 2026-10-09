"""DEL-16 tests for the droppable signature presets.

Run:  python3 tests/test_camera_vocabulary_rules/test_presets.py
  or: python3 -m unittest discover -s tests/test_camera_vocabulary_rules
stdlib only.
"""
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL / "scripts"))

import camera_signatures as cs  # noqa: E402

REQUIRED_FIELDS = (
    "id", "name", "family", "drop_at", "prompt_phrase", "emotion",
    "use_when", "ai_risk", "test_per_model", "one_move",
)
RISK_LEVELS = frozenset({"low", "medium", "high"})
FAMILIES = frozenset({"drone", "dolly"})


class EveryPresetIsComplete(unittest.TestCase):
    def test_library_is_not_empty_and_ids_unique(self):
        self.assertGreaterEqual(len(cs.PRESETS), 13)
        self.assertEqual(len(cs.PRESET_IDS), len(set(cs.PRESET_IDS)))

    def test_every_preset_carries_the_full_contract(self):
        for p in cs.PRESETS:
            for f in REQUIRED_FIELDS:
                self.assertIn(f, p, "%s missing %s" % (p.get("id"), f))
            self.assertTrue(p["id"])
            self.assertTrue(p["name"])
            self.assertTrue(p["prompt_phrase"].strip())
            self.assertTrue(p["emotion"].strip())
            self.assertTrue(p["use_when"].strip())
            self.assertIn(p["family"], FAMILIES)
            self.assertIn(p["ai_risk"]["level"], RISK_LEVELS)
            self.assertTrue(p["ai_risk"]["note"].strip())
            self.assertIs(p["one_move"], True)
            self.assertIsInstance(p["test_per_model"], bool)
            self.assertIsInstance(p["drop_at"], tuple)
            self.assertGreater(len(p["drop_at"]), 0)

    def test_drone_and_dolly_families_are_both_shipped(self):
        self.assertTrue(cs.DRONE_PRESET_IDS, "no drone presets")
        self.assertTrue(cs.DOLLY_PRESET_IDS, "no dolly presets")
        self.assertIn("drone_fly_in", cs.DRONE_PRESET_IDS)
        for pid in cs.DRONE_PRESET_IDS:
            self.assertEqual(cs.family(pid), "drone")
        for pid in cs.DOLLY_PRESET_IDS:
            self.assertEqual(cs.family(pid), "dolly")

    def test_family_lookup_falls_back_to_other(self):
        self.assertEqual(cs.family("not_a_move"), "other")
        self.assertEqual(cs.family(""), "other")
        self.assertEqual(cs.family(None), "other")

    def test_family_resolves_the_vocabulary_layers_sig_prefix(self):
        # references/camera-vocabulary.json ships its signature ids as
        # sig_<id>; a shot record may carry either spelling
        self.assertEqual(cs.family("sig_drone_fly_in"), "drone")
        self.assertEqual(cs.family("sig_lateral_truck"), "dolly")
        self.assertEqual(cs.family("sig_dolly_in"), "dolly")

    def test_family_recognises_a_plain_aerial_move_id(self):
        self.assertEqual(cs.family("drone_fly"), "drone")
        self.assertEqual(cs.family("aerial_reveal"), "drone")
        self.assertEqual(cs.family("truck"), "dolly")

    def test_family_does_not_overclaim(self):
        for mid in ("static", "pan", "tilt", "crane", "whip_pan", "zoom_in"):
            self.assertEqual(cs.family(mid), "other", mid)

    def test_every_drone_preset_drops_only_at_allowed_placements(self):
        for pid in cs.DRONE_PRESET_IDS:
            for place in cs.get_preset(pid)["drop_at"]:
                self.assertIn(
                    place, cs.DRONE_ALLOWED_PLACEMENTS,
                    "%s drops at %s" % (pid, place))

    def test_no_preset_drops_at_a_dialogue_close_up(self):
        for p in cs.PRESETS:
            self.assertNotIn("dialogue_close_up", p["drop_at"], p["id"])
            self.assertNotIn("mid_scene", p["drop_at"], p["id"])

    def test_no_drone_preset_drops_at_the_closing_beat(self):
        for pid in cs.DRONE_PRESET_IDS:
            self.assertNotIn("closing", cs.get_preset(pid)["drop_at"], pid)

    def test_a_drone_preset_drops_at_a_scene_transition(self):
        # the vocabulary data layer names this placement; a drone that
        # cannot bridge two scenes is only half a signature move
        self.assertIn("scene_transition",
                      cs.get_preset("aerial_reveal")["drop_at"])
        frag = cs.drop_preset("aerial_reveal", "scene_transition")
        self.assertEqual(frag["family"], "drone")


class DroppingPresets(unittest.TestCase):
    def test_every_preset_drops_at_every_placement_it_advertises(self):
        for p in cs.PRESETS:
            for place in p["drop_at"]:
                frag = cs.drop_preset(p["id"], place)
                self.assertEqual(frag["camera_move"], p["id"])
                self.assertEqual(frag["placement"], place)
                self.assertEqual(frag["moves"], [p["id"]])
                self.assertEqual(frag["prompt_phrase"], p["prompt_phrase"])

    def test_video_start_is_openable_with_a_drone_fly_in(self):
        frag = cs.drop_preset("drone_fly_in", "video_start")
        self.assertIn("drone fly-in", frag["prompt_phrase"])

    def test_scene_start_is_openable_with_a_drone_fly_in(self):
        frag = cs.drop_preset("drone_fly_in", "scene_start")
        self.assertEqual(frag["family"], "drone")

    def test_unknown_preset_fails_closed(self):
        with self.assertRaises(cs.UnknownPreset):
            cs.drop_preset("no_such_preset", "scene_start")

    def test_unknown_placement_fails_closed(self):
        with self.assertRaises(ValueError):
            cs.drop_preset("dolly_in", "rooftop")

    def test_drone_never_drops_on_a_dialogue_close_up(self):
        with self.assertRaises(ValueError) as ctx:
            cs.drop_preset("drone_fly_in", "dialogue_close_up")
        self.assertIn("establishing or transition", str(ctx.exception))

    def test_drone_never_drops_mid_scene(self):
        with self.assertRaises(ValueError):
            cs.drop_preset("aerial_reveal", "mid_scene")

    def test_preset_outside_its_own_drop_at_is_refused(self):
        with self.assertRaises(ValueError):
            cs.drop_preset("drone_fly_in", "transition")

    def test_dolly_preset_drops_on_a_closing_beat(self):
        frag = cs.drop_preset("dolly_out", "closing")
        self.assertEqual(frag["family"], "dolly")


if __name__ == "__main__":
    unittest.main()
