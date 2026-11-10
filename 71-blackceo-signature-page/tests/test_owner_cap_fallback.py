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


class OwnerPolicySourceTests(unittest.TestCase):
    def test_named_policy_source_refuses_ambiguous_or_malformed_rows(self):
        spec = importlib.util.spec_from_file_location("owner_cap_executor", ROOT / "scripts" / "stage_executor.py")
        executor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(executor)
        source = {"file": "66-kie-image/models.json", "selector_field": "canonical_model_id",
                  "selector": MODEL, "field": "owner_prompt_cap_chars"}
        valid = {"canonical_model_id": MODEL, "owner_prompt_cap_chars": 17321}
        documents = [(dict(models=[valid]), 17321), (dict(models=[valid, valid]), None),
                     (dict(models=None), None), ([], None),
                     (dict(models=[dict(valid, owner_prompt_cap_chars=True)]), None),
                     (dict(models=[{"canonical_model_id": MODEL, "live_schema_cap_chars": 32000}]), None)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "66-kie-image").mkdir()
            path = root / "66-kie-image" / "models.json"
            for module in (validator, executor):
                with patch.object(module, "SKILL_ROOT", root / "71-blackceo-signature-page"):
                    for document, expected in documents:
                        with self.subTest(module=module.__name__, document=document):
                            path.write_text(json.dumps(document))
                            self.assertEqual(module._owner_cap_from(source), expected)


if __name__ == "__main__":
    unittest.main()
