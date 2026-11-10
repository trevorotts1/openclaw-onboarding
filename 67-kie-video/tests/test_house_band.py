"""INST-001 #21: Skill 67 registry house band follows rule 12, not the retired 5,000/9,000/19,000.

Registry band = 16,000 / 19,000 / 20,000 (80 / 95 / 100 percent of the 20,000 owner cap, same as
Skill 66). Per model: 80 / 95 / 100 percent of vendor_hard_cap_chars, null when the cap is unknown.
"""
import json
import math
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "..", "models.json")) as f:
    DATA = json.load(f)


class HouseBand(unittest.TestCase):
    def test_registry_band_is_derived_from_the_owner_cap(self):
        self.assertEqual(DATA["registry_policy"]["house_band_chars"],
                         {"min": 16000, "target": 19000, "max": 20000})

    def test_per_model_band_is_80_95_100_percent_of_the_vendor_cap(self):
        capped = 0
        for m in DATA["models"]:
            cap = m.get("vendor_hard_cap_chars")
            got = (m["house_prompt_min_chars"], m["house_prompt_target_chars"], m["house_prompt_max_chars"])
            if isinstance(cap, int):
                capped += 1
                self.assertEqual(got, (math.ceil(cap * 0.80), math.ceil(cap * 0.95), cap),
                                 m["canonical_model_id"])
            else:
                self.assertEqual(got, (None, None, None), m["canonical_model_id"])
        self.assertTrue(capped, "no capped row found; test would pass vacuously")

    def test_20000_cap_rows_match_the_registry_band(self):
        band = DATA["registry_policy"]["house_band_chars"]
        rows = [m for m in DATA["models"] if m.get("vendor_hard_cap_chars") == 20000]
        self.assertTrue(rows, "no 20,000-cap row found; test would pass vacuously")
        for m in rows:
            self.assertEqual(
                (m["house_prompt_min_chars"], m["house_prompt_target_chars"], m["house_prompt_max_chars"]),
                (band["min"], band["target"], band["max"]), m["canonical_model_id"])


if __name__ == "__main__":
    unittest.main()
