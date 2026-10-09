"""DEL-16: the per-model test flag on every move, and where it must be set.

The camera guides disagree between models: one guide calls the jargon less
reliable than plain wording, another lists it as a primary control. So the
move vocabulary carries a per-model test flag and a move whose sources
dispute it may never ship with the flag cleared.

Run:  python3 tests/test_camera_vocabulary_rules/test_per_model_flag.py
stdlib only.
"""
import json
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL / "scripts"))

from camera_signatures import presets as presets_mod  # noqa: E402
from camera_signatures.rules import (  # noqa: E402
    DISPUTED_BETWEEN_MODELS,
    MODEL_TEST_FLAG,
    check_model_test_flag,
)

# The vocabulary data layer ships this path; when it is present the flag is
# checked there too. Absent is recorded, never a silent pass.
VOCABULARY = SKILL / "references" / "camera-vocabulary.json"


class FlagOnEveryShippedMove(unittest.TestCase):
    def test_every_preset_carries_the_flag(self):
        self.assertEqual(check_model_test_flag(), [])

    def test_the_flag_name_is_the_documented_one(self):
        self.assertEqual(MODEL_TEST_FLAG, "per_model_test")
        for p in presets_mod.PRESETS:
            self.assertIn(MODEL_TEST_FLAG, p, p["id"])

    def test_the_flag_is_a_real_boolean(self):
        for p in presets_mod.PRESETS:
            self.assertIsInstance(p[MODEL_TEST_FLAG], bool, p["id"])

    def test_at_least_one_move_is_flagged_and_one_is_not(self):
        # a flag that is always true, or always false, discriminates nothing
        flags = {p[MODEL_TEST_FLAG] for p in presets_mod.PRESETS}
        self.assertEqual(flags, {True, False},
                         "flag does not discriminate: %r" % flags)


class DisputedMovesMustBeFlagged(unittest.TestCase):
    def test_the_disputed_set_is_not_empty(self):
        self.assertTrue(DISPUTED_BETWEEN_MODELS)

    def test_a_disputed_move_with_a_cleared_flag_is_an_error(self):
        entry = {"id": "dolly_in", MODEL_TEST_FLAG: False}
        errs = check_model_test_flag([entry])
        self.assertIn("DISPUTED_MOVE_NOT_FLAGGED:dolly_in", errs)

    def test_a_disputed_move_that_is_flagged_is_clean(self):
        entry = {"id": "dolly_in", MODEL_TEST_FLAG: True}
        self.assertEqual(check_model_test_flag([entry]), [])

    def test_a_missing_flag_is_an_error(self):
        errs = check_model_test_flag([{"id": "pan"}])
        self.assertIn("MISSING_PER_MODEL_TEST_FLAG:pan", errs)

    def test_a_non_boolean_flag_is_an_error(self):
        errs = check_model_test_flag([{"id": "pan", MODEL_TEST_FLAG: "yes"}])
        self.assertIn("BAD_PER_MODEL_TEST_FLAG:pan", errs)

    def test_a_non_record_entry_is_an_error_not_a_crash(self):
        self.assertEqual(check_model_test_flag(["pan"]), ["BAD_ENTRY"])

    def test_every_disputed_dolly_preset_is_shipped_and_flagged(self):
        from camera_signatures import DOLLY_PRESET_IDS
        for mid in DOLLY_PRESET_IDS:
            if mid in DISPUTED_BETWEEN_MODELS:
                self.assertEqual(
                    check_model_test_flag([{"id": mid, MODEL_TEST_FLAG: False}]),
                    ["DISPUTED_MOVE_NOT_FLAGGED:%s" % mid])

    def test_the_undisputed_dolly_move_may_carry_a_cleared_flag(self):
        # no guide disputes lateral truck, so it is the library's control:
        # a move that is allowed to ship with the flag cleared.
        self.assertNotIn("lateral_truck", DISPUTED_BETWEEN_MODELS)
        self.assertEqual(
            check_model_test_flag(
                [{"id": "lateral_truck", MODEL_TEST_FLAG: False}]), [])

    def test_every_drone_preset_carries_the_flag(self):
        from camera_signatures import DRONE_PRESET_IDS
        for mid in DRONE_PRESET_IDS:
            entry = {"id": mid, MODEL_TEST_FLAG: True}
            self.assertEqual(check_model_test_flag([entry]), [], mid)


class VocabularyDataLayer(unittest.TestCase):
    """The flag is also checked against the shipped vocabulary, when present."""

    def test_vocabulary_moves_all_carry_the_flag(self):
        if not VOCABULARY.is_file():
            self.skipTest("camera-vocabulary.json not shipped in this tree")
        data = json.loads(VOCABULARY.read_text(encoding="utf-8"))
        moves = data.get("moves")
        self.assertIsInstance(moves, list)
        self.assertTrue(moves, "vocabulary has no moves")
        errs = []
        for m in moves:
            if MODEL_TEST_FLAG not in m:
                errs.append("MISSING_PER_MODEL_TEST_FLAG:%s" % m.get("id"))
            elif not isinstance(m[MODEL_TEST_FLAG], bool):
                errs.append("BAD_PER_MODEL_TEST_FLAG:%s" % m.get("id"))
        self.assertEqual(errs, [])

    def test_vocabulary_keeps_its_research_sections(self):
        if not VOCABULARY.is_file():
            self.skipTest("camera-vocabulary.json not shipped in this tree")
        data = json.loads(VOCABULARY.read_text(encoding="utf-8"))
        for key in ("meta", "angles", "shot_types", "moves", "lenses",
                    "apertures", "lens_looks", "grammar", "pacing",
                    "top_rules"):
            self.assertIn(key, data, key)


if __name__ == "__main__":
    unittest.main()
