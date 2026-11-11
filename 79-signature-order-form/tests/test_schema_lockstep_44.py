"""Issue 53: Skill 79's packet purchase-event schemas (1.0, 1.1, 1.2) are byte-identical
to Skill 44's normalizer copies. Reads Skill 44 files as data; edits nothing."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINE = ROOT / "79-signature-order-form" / "fixtures" / "packet" / "schemas"
THEIRS = ROOT / "44-convert-and-flow-operator" / "tools" / "siglaunch" / "normalizer"
NAMES = ("purchase-event.schema.json", "purchase-event.v1.1.schema.json", "purchase-event.v1.2.schema.json")


class SchemaLockstepTests(unittest.TestCase):
    def test_all_three_versions_are_byte_identical_to_skill_44(self):
        for n in NAMES:
            self.assertTrue((MINE / n).is_file(), n)
            self.assertTrue((THEIRS / n).is_file(), n)
            self.assertEqual((MINE / n).read_bytes(), (THEIRS / n).read_bytes(), f"{n} drifted from Skill 44")

    def test_a_drifted_copy_is_detected(self):
        a, b = (MINE / NAMES[2]).read_bytes(), (MINE / NAMES[2]).read_bytes() + b" "
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
