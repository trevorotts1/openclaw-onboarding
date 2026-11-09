"""The fallback reads the owner registry rather than a private numeric copy."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("skill71_owner_cap_validator", ROOT / "scripts" / "validate_prompt.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
MODEL = "gpt-image-2-6/sunburst-text-to-image"


class OwnerCapFallbackTests(unittest.TestCase):
    def resolve(self, document):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.json"
            path.write_text(json.dumps(document))
            with patch.object(validator, "_image_owner_registry_path", return_value=path):
                return validator.cap_for_model(MODEL, {"models": [], "default": {"max_chars": 32000}})

    def test_exact_registry_value_governs_missing_local_policy(self):
        # A changed synthetic cap proves this is a read rather than a relocated literal.
        for maximum in (20000, 17321):
            result = self.resolve({"models": [{"canonical_model_id": MODEL,
                                              "owner_prompt_cap_chars": maximum}]})
            self.assertEqual(result["max_chars"], maximum)
            self.assertEqual(result["cap_status"], "OWNER_RULED")
            self.assertIn("owner_prompt_cap_chars", result["source"])

    def test_missing_invalid_or_duplicate_owner_cap_stays_unknown(self):
        cases = [
            {"models": []},
            {"models": [{"canonical_model_id": MODEL, "vendor_hard_cap_chars": 32000}]},
            {"models": [{"canonical_model_id": MODEL, "owner_prompt_cap_chars": True}]},
            {"models": [{"canonical_model_id": MODEL, "owner_prompt_cap_chars": "20000"}]},
            {"models": [{"canonical_model_id": MODEL, "owner_prompt_cap_chars": -1}]},
            {"models": [{"canonical_model_id": MODEL + "-unknown", "owner_prompt_cap_chars": 20000}]},
            {"models": [{"canonical_model_id": MODEL, "owner_prompt_cap_chars": 20000}] * 2},
            {"models": None},
        ]
        for document in cases:
            with self.subTest(document=document):
                result = self.resolve(document)
                self.assertIsNone(result["max_chars"])
                self.assertEqual(result["cap_status"], "UNKNOWN")

    def test_unavailable_registry_never_uses_vendor_default(self):
        with patch.object(validator, "_image_owner_registry_path", return_value=None):
            result = validator.cap_for_model(MODEL, {"models": [], "default": {"max_chars": 32000}})
        self.assertIsNone(result["max_chars"])

    def test_existing_explicit_policy_entry_is_preserved(self):
        entry = {"match": "gpt-image-2-6", "max_chars": 20000, "unit": "chars"}
        with patch.object(validator, "_image_owner_registry_path", side_effect=AssertionError("unexpected fallback")):
            self.assertIs(validator.cap_for_model(MODEL, {"models": [entry]}), entry)


if __name__ == "__main__":
    unittest.main()
