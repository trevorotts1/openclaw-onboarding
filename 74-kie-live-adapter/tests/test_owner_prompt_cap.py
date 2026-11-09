"""The owner prompt cap must live in the 74 registry and be derived, never restated.

LAND-001 #11 / fix plan A1-A2: a ``*-2-6`` route with no owner row silently falls
back to the vendor's 32,000. The cap is the owner ruling of 2026-11-08; it is read
from the policy owner (Skill 66), not typed twice.
"""
import json
import os
import sys
import tempfile
import unittest

from fakes import K

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import build_model_registry as B  # noqa: E402

REGISTRY = os.path.join(HERE, "..", "references", "kie-model-registry.json")
CAP = 20000


def _rows():
    with open(REGISTRY) as f:
        return [m for m in json.load(f)["models"]
                if str(m.get("id") or "").startswith("gpt-image-2-6/")]


class RegistryRows(unittest.TestCase):
    def test_every_gpt_image_2_6_row_declares_the_owner_cap(self):
        rows = _rows()
        self.assertTrue(rows, "no gpt-image-2-6 row found; the check cannot pass vacuously")
        for row in rows:
            self.assertEqual(row.get("owner_prompt_cap_chars"), CAP, row.get("id"))

    def test_no_vendor_32000_records_as_the_owner_cap(self):
        for row in _rows():
            self.assertNotEqual(row.get("owner_prompt_cap_chars"), 32000, row.get("id"))


class OwnerCapResolution(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = self._tmp.name
        os.makedirs(os.path.join(root, "66-kie-image"))
        with open(os.path.join(root, "66-kie-image", "models.json"), "w") as f:
            json.dump({"models": [{
                "canonical_model_id": "gpt-image-2-6/sunburst-text-to-image",
                "modality": "image",
                "owner_prompt_cap_chars": CAP,
            }]}, f)
        self._old = os.environ.get("KIE_POLICY_ROOT")
        os.environ["KIE_POLICY_ROOT"] = root
        self.addCleanup(self._restore)

    def _restore(self):
        if self._old is None:
            os.environ.pop("KIE_POLICY_ROOT", None)
        else:
            os.environ["KIE_POLICY_ROOT"] = self._old

    def test_exact_row_resolves(self):
        self.assertEqual(K.policy_owner_cap_family("gpt-image-2-6/sunburst-text-to-image"),
                         (CAP, "66-kie-image"))

    def test_sibling_route_inherits_the_family_cap(self):
        self.assertEqual(K.policy_owner_cap_family("gpt-image-2-6/flare-text-to-image"),
                         (CAP, "66-kie-image"))

    def test_unrelated_route_has_no_cap(self):
        self.assertEqual(K.policy_owner_cap_family("gpt-image-2/sunburst-text-to-image"), (None, None))

    def test_generator_emits_the_owner_cap(self):
        row = B.base_row("gpt-image-2-6/flare-text-to-image", {}, None)
        self.assertEqual(row.get("owner_prompt_cap_chars"), CAP)

    def test_generator_omits_the_key_when_no_owner_rules(self):
        row = B.base_row("gpt-image-2/sunburst-text-to-image", {}, None)
        self.assertNotIn("owner_prompt_cap_chars", row)


if __name__ == "__main__":
    unittest.main()
