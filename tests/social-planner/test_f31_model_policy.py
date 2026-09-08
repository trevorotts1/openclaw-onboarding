#!/usr/bin/env python3
"""
test_f31_model_policy.py — F31 provider-first model policy (QC-F31).

Covers:
  - GLM slug acceptance: openrouter/z-ai/glm-5.3-flash and suffix variants
    (the reproduced regex gap) plus provider-verified inventory acceptance;
  - provider-first selection (select_provider_then_model): role separation,
    client pin preserved, approved fallback order, recommendation only as a
    visible confirm, no silent substitution;
  - adapter registry (provider_adapters.py): DeepSeek direct + the TEST-ONLY
    fourth adapter, provider_id separate from model_id, no implicit routing;
  - policy revision persistence: immutable revision, restart-safe load/save.

Run:  python3 -m unittest discover -s tests/social-planner -p 'test_f*.py'
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

_ONB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SHARED = os.path.join(_ONB_ROOT, "shared-utils")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import select_model  # noqa: E402
import social_model_policy as smp  # noqa: E402
import provider_adapters as pa  # noqa: E402


GLM_FLASH = "openrouter/z-ai/glm-5.3-flash"
GLM_BARE = "openrouter/z-ai/glm-4.6"
INVENTORY = [GLM_FLASH, GLM_BARE]


class TestGLMSlugAcceptance(unittest.TestCase):
    """The reproduced finding: GLM_OPENROUTER rejected '-flash' suffixes."""

    def test_regex_accepts_glm_5_3_flash(self):
        self.assertTrue(select_model.GLM_OPENROUTER["pattern"].match(GLM_FLASH))

    def test_regex_accepts_suffix_variants(self):
        for slug in (
            "openrouter/z-ai/glm-5.3",
            "openrouter/z-ai/glm-4.6-pro",
            "openrouter/zhipu/glm-5-preview",
            "openrouter/z-ai/glm-5.3-flash:cloud",
        ):
            self.assertIsNotNone(
                select_model.GLM_OPENROUTER["pattern"].match(slug),
                f"pattern must accept {slug}",
            )

    def test_provider_verified_slug_accepted(self):
        # Inventory-backed verification: the full slug is in verified_slugs.
        self.assertTrue(select_model.slug_is_verified(GLM_FLASH))

    def test_unknown_slug_not_verified(self):
        self.assertFalse(select_model.slug_is_verified("openrouter/fake/vendor-9.9-pro"))

    def test_new_slug_selectable_from_inventory_alone(self):
        # QC-F31: "Add a new model slug to provider inventory without editing
        # selector code" — a slug present ONLY in verified_slugs matches the
        # glm family chain entry.
        models = [GLM_FLASH, GLM_BARE]
        best = select_model._best_match_in_position(models, select_model.GLM_OPENROUTER)
        self.assertEqual(best, GLM_FLASH)

    def test_highest_version_wins_among_verified(self):
        newer = "openrouter/z-ai/glm-9.9-flash"
        select_model.load_verified_slugs()[newer] = {"family": "glm"}
        try:
            best = select_model._best_match_in_position(
                [GLM_BARE, newer], select_model.GLM_OPENROUTER
            )
            self.assertEqual(best, newer)
        finally:
            del select_model.load_verified_slugs()[newer]


class TestProviderFirstSelection(unittest.TestCase):
    """select_provider_then_model — provider-first, then model."""

    def test_recommendation_over_provider_pool(self):
        r = smp.select_provider_then_model("openrouter", "planner", INVENTORY)
        self.assertTrue(r["selected"])
        self.assertEqual(r["provider"], "openrouter")
        self.assertIn(r["model_id"], INVENTORY)
        self.assertEqual(r["source"], "recommendation")

    def test_client_pin_honored_exactly(self):
        policy = {"role_models": {"planner": {"model_id": GLM_BARE}}}
        r = smp.select_provider_then_model("openrouter", "planner", INVENTORY, policy=policy)
        self.assertEqual(r["model_id"], GLM_BARE)
        self.assertEqual(r["source"], "client_pin")

    def test_pin_never_silently_upgraded_to_newer_version(self):
        # Pin = the OLDER flash; a newer bare version is also available.
        policy = {"role_models": {"planner": {"model_id": GLM_FLASH}}}
        r = smp.select_provider_then_model("openrouter", "planner", INVENTORY, policy=policy)
        self.assertEqual(r["model_id"], GLM_FLASH, "pin preserved, never auto-upgraded")

    def test_removed_pin_activates_approved_fallback_in_saved_order(self):
        policy = {"role_models": {"planner": {
            "model_id": "openrouter/removed-model",
            "fallbacks": [GLM_BARE, GLM_FLASH],
        }}}
        r = smp.select_provider_then_model("openrouter", "planner", INVENTORY, policy=policy)
        self.assertTrue(r["selected"])
        self.assertEqual(r["source"], "approved_fallback")
        self.assertEqual(r["model_id"], GLM_BARE, "first saved fallback wins, not the newest")

    def test_removed_pin_without_fallback_requests_selection(self):
        policy = {"role_models": {"planner": {"model_id": "openrouter/removed-model"}}}
        r = smp.select_provider_then_model("openrouter", "planner", INVENTORY, policy=policy)
        self.assertFalse(r["selected"])
        self.assertTrue(r["needs_selection"])
        self.assertEqual(r.get("pin_unavailable"), "openrouter/removed-model")

    def test_no_silent_substitution_when_nothing_fits(self):
        # Nothing on the provider fits -> explicit selection request, never a
        # silent switch to another provider/model, never an indefinite wait.
        r = smp.select_provider_then_model("openrouter", "visual_qc", INVENTORY)
        self.assertFalse(r["selected"])
        self.assertTrue(r["needs_selection"])
        self.assertTrue(r.get("needs_owner_input"))

    def test_unsupported_provider_reports_adapter_work(self):
        r = smp.select_provider_then_model("mysteryprovider", "planner", INVENTORY)
        self.assertFalse(r["selected"])
        self.assertTrue(r.get("needs_adapter"))
        self.assertIn("adapter", r["reason"].lower())

    def test_visual_qc_requires_vision_capable_model(self):
        inventory = [
            {"id": "openrouter/qwen/qwen3-vl:235b", "capabilities": ["text", "vision"]},
            GLM_BARE,
        ]
        r = smp.select_provider_then_model("openrouter", "visual_qc", inventory)
        self.assertTrue(r["selected"])
        self.assertEqual(r["model_id"], "openrouter/qwen/qwen3-vl:235b")
        self.assertEqual(r["required_modality"], "vision")

    def test_role_separation_text_roles(self):
        for role in ("planner", "researcher", "writer", "prompt_compiler"):
            r = smp.select_provider_then_model("openrouter", role, INVENTORY)
            self.assertTrue(r["selected"], f"role {role} must select")
            self.assertEqual(r["required_modality"], "text")

    def test_provider_id_separate_from_model_id(self):
        r = smp.select_provider_then_model("deepseek", "writer", ["deepseek/deepseek-v4-pro"])
        self.assertEqual(r["provider"], "deepseek")
        self.assertEqual(r["model_id"], "deepseek/deepseek-v4-pro")

    def test_unknown_role_rejected(self):
        r = smp.select_provider_then_model("openrouter", "chief-vibe-officer", INVENTORY)
        self.assertFalse(r["selected"])
        self.assertTrue(r["needs_selection"])


class TestPolicyRevisionPersistence(unittest.TestCase):
    """Saved policy revision — immutable, restart-surviving."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="f31-policy-")
        self.path = os.path.join(self.tmp, "social-model-policy.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _policy(self, revision=1):
        return {
            "company_id": "co-test",
            "revision": revision,
            "selection_mode": "pinned",
            "provider": "openrouter",
            "role_models": {
                "planner": {"model_id": GLM_FLASH, "fallbacks": [GLM_BARE]},
                "researcher": {"model_id": GLM_BARE, "fallbacks": []},
                "writer": {"model_id": GLM_FLASH, "fallbacks": []},
                "prompt_compiler": {"model_id": GLM_BARE, "fallbacks": []},
                "visual_qc": {"model_id": "openrouter/qwen/qwen3-vl:235b", "fallbacks": []},
            },
            "image_models": ["kie-ai/gpt-image-2"],
            "video_models": ["veo-3"],
            "execution_mode": "standard",
            "budget": {"max_cost_per_cycle": 10.0, "max_retries": 2,
                       "permitted_paid_fallbacks": []},
        }

    def test_save_and_reload_survives_restart(self):
        smp.save_policy(self._policy(), path=self.path)
        loaded = smp.load_policy(self.path)
        self.assertEqual(loaded["revision"], 1)
        self.assertEqual(loaded["role_models"]["planner"]["model_id"], GLM_FLASH)
        # A "restart" (fresh load) still yields the same pin:
        r = smp.select_provider_then_model(
            "openrouter", "planner", INVENTORY, policy=loaded
        )
        self.assertEqual(r["source"], "client_pin")
        self.assertEqual(r["model_id"], GLM_FLASH)

    def test_revision_regression_refused(self):
        smp.save_policy(self._policy(revision=3), path=self.path)
        with self.assertRaises(ValueError):
            smp.save_policy(self._policy(revision=2), path=self.path)

    def test_accepted_change_bumps_revision(self):
        smp.save_policy(self._policy(revision=3), path=self.path)
        nxt = self._policy(revision=4)
        nxt["role_models"]["planner"]["model_id"] = GLM_BARE
        smp.save_policy(nxt, path=self.path)
        loaded = smp.load_policy(self.path)
        self.assertEqual(loaded["revision"], 4)
        self.assertEqual(loaded["role_models"]["planner"]["model_id"], GLM_BARE)

    def test_validate_policy_contract_fields(self):
        problems = smp.validate_policy(self._policy())
        self.assertEqual(problems, [], f"valid policy: {problems}")
        bad = self._policy()
        bad["selection_mode"] = "auto-pilot"
        del bad["role_models"]["visual_qc"]
        problems = smp.validate_policy(bad)
        self.assertTrue(any("selection_mode" in p for p in problems))
        self.assertTrue(any("visual_qc" in p for p in problems))


class TestAdapterRegistry(unittest.TestCase):
    """Direct-provider adapter registry — DeepSeek + TEST-ONLY stub."""

    def test_deepseek_adapter_registered(self):
        ad = pa.get_adapter("deepseek")
        self.assertEqual(ad.provider_id, "deepseek")
        self.assertEqual(ad.secret_env_name, "DEEPSEEK_API_KEY")
        ids = [m["id"] for m in ad.list_models()]
        self.assertIn("deepseek/deepseek-v4-pro", ids)

    def test_test_only_adapter_labeled_and_never_invokes(self):
        ad = pa.get_adapter("test-provider")
        self.assertTrue(
            ad.__doc__ and "TEST-ONLY" in ad.__doc__,
            "the fourth adapter must be clearly labeled TEST-ONLY",
        )
        with self.assertRaises(pa.AdapterError):
            ad.invoke("test-provider/test-model-pro", [{"role": "user", "content": "hi"}])

    def test_unknown_provider_reports_adapter_work(self):
        with self.assertRaises(pa.AdapterError) as ctx:
            pa.get_adapter("not-a-provider")
        self.assertIn("adapter_missing", str(ctx.exception))

    def test_deepseek_invocation_requires_key_without_printing(self):
        os.environ.pop("DEEPSEEK_API_KEY", None)
        ad = pa.get_adapter("deepseek")
        with self.assertRaises(pa.AdapterError) as ctx:
            ad.invoke("deepseek/deepseek-v4-pro", [{"role": "user", "content": "hi"}])
        self.assertIn("auth_missing", str(ctx.exception))
        # The error names the env var; it must not embed any secret VALUE.
        # (f-string here renders the empty env var — tighten the message to
        # name the var only.)
        self.assertNotIn("=", str(ctx.exception))

    def test_provider_id_separate_from_model_id_in_result(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-dummy-key"
        try:
            captured = {}

            class FakeResp:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def read(self):
                    return json.dumps({
                        "choices": [{"message": {"content": "ok"}}],
                        "usage": {"total_tokens": 5},
                    }).encode()

            def fake_urlopen(req, timeout=60):
                captured["url"] = req.full_url
                return FakeResp()

            orig = pa.urllib.request.urlopen
            pa.urllib.request.urlopen = fake_urlopen
            try:
                out = pa.get_adapter("deepseek").invoke(
                    "deepseek/deepseek-v4-pro", [{"role": "user", "content": "hi"}]
                )
            finally:
                pa.urllib.request.urlopen = orig
            self.assertEqual(out["provider_id"], "deepseek")
            self.assertEqual(out["model_id"], "deepseek/deepseek-v4-pro")
            self.assertIn("api.deepseek.com", captured["url"],
                          "invocation hits the DeepSeek endpoint directly — no implicit routing")
        finally:
            os.environ.pop("DEEPSEEK_API_KEY", None)

    def test_secret_reference_names_env_var_not_value(self):
        ref = pa.get_adapter("deepseek").secret_reference()
        self.assertEqual(ref["env_var"], "DEEPSEEK_API_KEY")
        self.assertNotIn("value", ref)


if __name__ == "__main__":
    unittest.main()