import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._support import fixture  # noqa: E402

from capability_control.runtime_schema import OwnedMerge, RuntimeSchema, assert_writable_target  # noqa: E402

OWNED = ["schema_version", "selectable_models", "allowlist", "provider_entries",
         "role_bindings", "scheduler_jobs", "cache_versions"]

VALID_DOC = {
    "schema_version": "1",
    "selectable_models": [
        {"model_id": "openrouter/xiaomi/mimo-v2.6-pro", "provider": "openrouter",
         "reasoning": True, "effort_selector": False, "tools": True,
         "source_revision": "rev1", "fetched_at": "2026-10-22T00:00:00+00:00",
         "refresh_path": "python3 -I tools/capture_fixtures.py --out fixtures/"},
    ],
    "allowlist": {"enabled": ["openrouter/xiaomi/mimo-v2.6-pro"], "disabled": []},
    "provider_entries": [{"entry_id": "providerThinking:openrouter", "provider": "openrouter", "thinking_mode": "high"}],
    "role_bindings": [{"role": "builder", "model_id": "openrouter/xiaomi/mimo-v2.6-pro", "requested_effort": "none"}],
    "scheduler_jobs": [{"job_id": "keepalive", "schedule": "*/15 * * * *", "model_id": "openrouter/xiaomi/mimo-v2.6-pro"}],
    "cache_versions": [{"cache_id": "model-catalog", "source_revision": "rev1",
                        "fetched_at": "2026-10-22T00:00:00+00:00",
                        "refresh_path": "python3 -I tools/capture_fixtures.py --out fixtures/"}],
    "department_models": {"video": {"model": "dept-video-model"}},
    "credentials": {"openrouter": {"ref": "keyring://openrouter"}},
    "aliases": {"mimo": "openrouter/xiaomi/mimo-v2.6-pro"},
    "heartbeat_policies": {"interval_s": 900},
    "user_preferences": {"language": "en"},
}


def deep(doc):
    import copy
    return copy.deepcopy(doc)


class TestRuntimeSchema(unittest.TestCase):
    def setUp(self):
        self.schema = RuntimeSchema.load(fixture("runtime-schema.snapshot.json"))

    def test_valid_doc_passes(self):
        self.assertEqual(self.schema.validate(VALID_DOC), [])

    def test_unknown_key_rejected(self):
        doc = deep(VALID_DOC)
        doc["effort_ladder_addon"] = {"mimo": ["low", "high", "max"]}
        errors = self.schema.validate(doc)
        self.assertTrue(any("unknown key" in e.message and "effort_ladder_addon" in e.path for e in errors))

    def test_wrong_type_rejected(self):
        doc = deep(VALID_DOC)
        doc["role_bindings"][0]["model_id"] = 42
        errors = self.schema.validate(doc)
        self.assertTrue(any("expected type string" in e.message for e in errors))

    def test_bad_enum_rejected(self):
        doc = deep(VALID_DOC)
        doc["role_bindings"][0]["requested_effort"] = "ultra"
        errors = self.schema.validate(doc)
        self.assertTrue(any("not in enum" in e.message for e in errors))

    def test_missing_required_rejected(self):
        doc = deep(VALID_DOC)
        del doc["role_bindings"][0]["role"]
        errors = self.schema.validate(doc)
        self.assertTrue(any("missing required key" in e.message for e in errors))

    def test_cache_rows_require_provenance(self):
        doc = deep(VALID_DOC)
        del doc["cache_versions"][0]["refresh_path"]
        errors = self.schema.validate(doc)
        self.assertTrue(any("missing required key 'refresh_path'" in e.message for e in errors))

    def test_merge_rejects_unowned_section(self):
        merge = OwnedMerge(owned_sections=OWNED)
        with self.assertRaises(ValueError):
            merge.merge(VALID_DOC, {"user_preferences": {"language": "fr"}})

    def test_merge_preserves_unrelated_sections(self):
        merge = OwnedMerge(owned_sections=OWNED)
        base = deep(VALID_DOC)
        proposal = {"role_bindings": [{"role": "qc", "model_id": "openrouter/z-ai/glm-5.3"}]}
        merged = merge.merge(base, proposal)
        for section in ("department_models", "credentials", "aliases", "heartbeat_policies", "user_preferences"):
            self.assertEqual(merged[section], VALID_DOC[section], section)
        self.assertEqual(merged["role_bindings"], proposal["role_bindings"])

    def test_guard_refuses_vendor_bundle_and_cache(self):
        with self.assertRaises(PermissionError):
            assert_writable_target("/opt/9router/app/.next-cli-build/server/chunks/8895.js", [])
        with self.assertRaises(PermissionError):
            assert_writable_target("/tmp/anything/patch.js", [])
        cache = "/tmp/s75w04u2-test-cache.json"
        with self.assertRaises(PermissionError):
            assert_writable_target(cache, [cache])
        assert_writable_target("/tmp/s75w04u2-test-config.json", [cache])  # plain config is fine


if __name__ == "__main__":
    unittest.main()
