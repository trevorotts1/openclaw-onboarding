"""Issue 69 (D-B): the 78 and 79 docs describe the REALISED route, per_offer_instances,
and label post-selection as fixture-only. Reads the docs as text; fails if either drifts."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
S78, S79 = ROOT / "78-signature-product-selection", ROOT / "79-signature-order-form"


class SkillMdModeTests(unittest.TestCase):
    def test_78_skill_md_names_the_realised_route(self):
        t = (S78 / "SKILL.md").read_text()
        self.assertIn("per_offer_instances", t)
        self.assertIn("selection_ref` is always null", t)
        self.assertNotIn("Post-selection mode", t)

    def test_79_skill_md_names_the_realised_route_and_labels_post_selection(self):
        t = (S79 / "SKILL.md").read_text()
        self.assertIn("per_offer_instances", t)
        line = next(l for l in t.splitlines() if l.startswith("2. Post-selection mode"))
        self.assertIn("FIXTURE-ONLY", line)
        self.assertIn("FIXTURE-ONLY", (S79 / "references/components/README.md").read_text())

    def test_78_manifest_excludes_post_selection_code_from_the_done_claim(self):
        not_counted = json.loads((S78 / "runtime-manifest.json").read_text())["done_claim"]["not_counted"]
        for f in ("79-signature-order-form/scripts/selection_flow.py",
                  "79-signature-order-form/references/components/post-selection-checkout.html",
                  "scripts/selection_session.py"):
            self.assertIn(f, not_counted)
            self.assertTrue((ROOT / f).is_file() if f.startswith("79-") else (S78 / f).is_file(), f)

    def test_the_ruling_the_docs_cite_exists(self):
        t = (ROOT / "83-black-friday-launcher" / "DECISIONS-PENDING.md").read_text()
        self.assertIn("per_offer_instances", t)


if __name__ == "__main__":
    unittest.main()
