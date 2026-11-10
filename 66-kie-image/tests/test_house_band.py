"""INST-001 #21 / plan A0: the registry-level house band follows the 20,000 owner cap.

min = 80 percent (hard floor), target = 95 percent, max = the cap. The old
5000/9000/19000 band is stale; 19,000 is correct only as the 95 percent target.
"""
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "..", "models.json")) as f:
    DATA = json.load(f)
CAP = 20000


class HouseBand(unittest.TestCase):
    def test_band_is_derived_from_the_owner_cap(self):
        band = DATA["registry_policy"]["house_band_chars"]
        self.assertEqual(band, {"min": CAP * 80 // 100, "target": CAP * 95 // 100, "max": CAP})

    def test_band_matches_the_owner_capped_rows(self):
        band = DATA["registry_policy"]["house_band_chars"]
        rows = [m for m in DATA["models"] if m.get("owner_prompt_cap_chars") == CAP]
        self.assertTrue(rows, "no owner-capped row found; test would pass vacuously")
        for m in rows:
            self.assertEqual(
                (m["house_prompt_min_chars"], m["house_prompt_target_chars"], m["house_prompt_max_chars"]),
                (band["min"], band["target"], band["max"]), m.get("canonical_model_id"))


if __name__ == "__main__":
    unittest.main()
