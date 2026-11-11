"""Issue 54: Skill 6 mirrors Skill 79's billing vocabulary by hand. Read Skill 6's tuple as TEXT
(never imported, never edited) and require it to equal order_bumps.BILLING_TYPES."""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "79-signature-order-form" / "scripts"))
SKILL6 = ROOT / "06-ghl-install-pages" / "tools" / "order_components.py"


def mirrored_tuple(source: str):
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "BILLING_TYPES" for t in node.targets):
            return ast.literal_eval(node.value)
    return None


class BillingVocabMirrorTests(unittest.TestCase):
    def test_skill_6_tuple_equals_skill_79_billing_types(self):
        from order_bumps import BILLING_TYPES
        self.assertEqual(mirrored_tuple(SKILL6.read_text()), tuple(BILLING_TYPES))

    def test_the_reader_detects_drift_and_absence(self):
        self.assertEqual(mirrored_tuple('BILLING_TYPES = ("a", "b")'), ("a", "b"))
        self.assertIsNone(mirrored_tuple("X = 1"))


if __name__ == "__main__":
    unittest.main()
