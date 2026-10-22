import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._support import fixture  # noqa: E402
from tests.test_runtime_schema import OWNED, VALID_DOC, deep  # noqa: E402

from capability_control.config_stage import ConfigStage, canonical_digest  # noqa: E402
from capability_control.runtime_schema import RuntimeSchema  # noqa: E402


class TestConfigStage(unittest.TestCase):
    """Acceptance: schema-invalid configuration proposals are rejected before
    activation with the prior healthy configuration intact and unrelated
    settings unchanged."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="s75w04u2-cfg-")
        self.path = os.path.join(self.dir, "capability-config.json")
        self.cache_path = os.path.join(self.dir, "model-catalog.cache.json")
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(VALID_DOC, fh, indent=1, sort_keys=True)
        with open(self.cache_path, "w", encoding="utf-8") as fh:
            json.dump({"models": {}}, fh)
        self.stage = ConfigStage(self.path, RuntimeSchema.load(fixture("runtime-schema.snapshot.json")),
                                 owned_sections=OWNED, cache_paths=[self.cache_path])

    def file_bytes(self):
        with open(self.path, "rb") as fh:
            return fh.read()

    def test_schema_invalid_proposal_rejected_before_activation(self):
        before = self.file_bytes()
        bad = {"selectable_models": [{"model_id": "openrouter/xiaomi/mimo-v2.6-pro", "provider": "openrouter",
                                      "effort_ladder": ["low", "high", "max"]}]}  # unknown key
        result = self.stage.stage(bad)
        self.assertFalse(result.accepted)
        self.assertTrue(any("effort_ladder" in e.path for e in result.errors))
        # prior healthy configuration intact, byte-for-byte
        self.assertEqual(self.file_bytes(), before)

    def test_invalid_proposal_leaves_unrelated_settings_unchanged(self):
        before = self.file_bytes()
        result = self.stage.stage({"user_preferences": {"language": "fr"}})  # unowned
        self.assertFalse(result.accepted)
        self.assertEqual(self.file_bytes(), before)
        doc = json.loads(self.file_bytes())
        self.assertEqual(doc["user_preferences"], VALID_DOC["user_preferences"])
        self.assertEqual(doc["department_models"], VALID_DOC["department_models"])
        self.assertEqual(doc["credentials"], VALID_DOC["credentials"])
        self.assertEqual(doc["aliases"], VALID_DOC["aliases"])
        self.assertEqual(doc["heartbeat_policies"], VALID_DOC["heartbeat_policies"])

    def test_valid_proposal_applies_atomically_with_verified_reload(self):
        proposal = {"role_bindings": [{"role": "builder", "model_id": "openrouter/xiaomi/mimo-v2.6-pro",
                                       "requested_effort": "none"}]}
        staged = self.stage.stage(proposal)
        self.assertTrue(staged.accepted)
        applied = self.stage.apply(staged)
        self.assertTrue(applied.applied)
        self.assertTrue(applied.reload_verified)
        self.assertEqual(applied.digest, canonical_digest(self.stage.load()))
        doc = self.stage.load()
        self.assertEqual(doc["role_bindings"], proposal["role_bindings"])
        for section in ("department_models", "credentials", "aliases", "heartbeat_policies", "user_preferences"):
            self.assertEqual(doc[section], VALID_DOC[section], section)

    def test_failed_reload_rolls_back_to_previous_usable_configuration(self):
        before_digest = canonical_digest(self.stage.load())
        proposal = {"role_bindings": [{"role": "builder", "model_id": "openrouter/xiaomi/mimo-v2.6-pro"}]}
        staged = self.stage.stage(proposal)
        self.assertTrue(staged.accepted)

        def bad_read_back():
            return {"tampered": True}

        applied = self.stage.apply(staged, read_back=bad_read_back)
        self.assertFalse(applied.applied)
        self.assertTrue(applied.rolled_back)
        self.assertEqual(canonical_digest(self.stage.load()), before_digest)

    def test_unstaged_apply_refuses(self):
        from capability_control.config_stage import StageResult
        applied = self.stage.apply(StageResult(accepted=False))
        self.assertFalse(applied.applied)

    def test_refuses_cache_and_bundle_targets(self):
        proposal = {"role_bindings": []}
        staged = self.stage.stage(proposal)
        self.assertTrue(staged.accepted)
        cache_stage = ConfigStage(self.cache_path, RuntimeSchema.load(fixture("runtime-schema.snapshot.json")),
                                  owned_sections=OWNED, cache_paths=[self.cache_path])
        with self.assertRaises(PermissionError):
            cache_stage.apply(staged)


if __name__ == "__main__":
    unittest.main()
