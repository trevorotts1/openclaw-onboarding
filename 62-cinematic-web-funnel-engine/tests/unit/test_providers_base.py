#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_providers_base.py — offline unit tests for providers/base.py (Skill 62, U4).

Covers:
  - MediaProvider is a real ABC (cannot instantiate directly; a subclass
    missing any abstract method also cannot instantiate; a complete subclass
    can).
  - ModelRegistry loading/validation: valid file loads, missing file /
    invalid JSON / missing required fields / duplicate model_id / bad status
    / a capability_tier referencing an unknown model_id all fail closed with
    the correct exception type.
  - The shipped model-registry.json validates and every capability_tier
    resolves exactly as spec §10.2's default policy prescribes.
  - resolve_tier() correctly fails closed on kie-bytedance-seedance-1.5-pro's
    unpriced state (Kie.ai docs state "pricing not listed") rather than
    silently proceeding — the concrete proof this unit exists to deliver:
    "prices/slugs resolved from the registry snapshot, never hardcoded."
  - slug_for()/price_for()/estimate() resolve values that live ONLY in the
    JSON file, proven by mutating a temp copy of the registry and observing
    the resolved values (and snapshot_id) change accordingly.

stdlib unittest only — no third-party test runner required.
Run: python3 -m unittest discover -s tests/unit -v
     (from the 62-cinematic-web-funnel-engine/ directory)
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from typing import List

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

from providers import base  # noqa: E402


REAL_REGISTRY_PATH = _SKILL_DIR / "providers" / "model-registry.json"


def _load_real_registry_dict() -> dict:
    with REAL_REGISTRY_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_fixture(tmp_path: Path, data: dict) -> Path:
    path = tmp_path
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# MediaProvider ABC contract
# ---------------------------------------------------------------------------


class CompleteFakeProvider(base.MediaProvider):
    """A minimal, fully-implemented fake — proves the interface is usable
    without any network access."""

    name = "fake"

    def upload_asset(self, request: base.AssetUploadRequest) -> str:
        return f"https://fake.example/{Path(request.path).name}"

    def generate_image(self, request: base.ImageGenerationRequest) -> base.TaskHandle:
        return base.TaskHandle(task_id="img-1", provider=self.name, model_id=request.model_id, status="queued")

    def generate_video(self, request: base.VideoGenerationRequest) -> base.TaskHandle:
        return base.TaskHandle(task_id="vid-1", provider=self.name, model_id=request.model_id, status="queued")

    def get_task(self, task_id: str) -> base.TaskHandle:
        return base.TaskHandle(task_id=task_id, provider=self.name, model_id="n/a", status="success")

    def cancel_task(self, task_id: str) -> bool:
        return True

    def download_results(self, task_id: str, destination: str) -> List[str]:
        return [f"{destination}/{task_id}.bin"]

    def estimate_cost(self, request):
        return base.CostEstimate(
            model_id=request.model_id,
            provider_model_slug="fake-slug",
            unit="usd_per_unit",
            unit_price=0.01,
            quantity=1,
            estimated_total=0.01,
            verified=True,
            registry_snapshot_id="deadbeef",
        )


class IncompleteFakeProvider(base.MediaProvider):
    """Missing every method except upload_asset — must not be instantiable."""

    name = "incomplete"

    def upload_asset(self, request):
        return "https://fake.example/x"


class MediaProviderContractTests(unittest.TestCase):
    def test_abstract_base_cannot_be_instantiated_directly(self) -> None:
        with self.assertRaises(TypeError):
            base.MediaProvider()  # type: ignore[abstract]

    def test_incomplete_subclass_cannot_be_instantiated(self) -> None:
        with self.assertRaises(TypeError):
            IncompleteFakeProvider()  # type: ignore[abstract]

    def test_complete_subclass_is_instantiable_and_usable(self) -> None:
        provider = CompleteFakeProvider()
        handle = provider.generate_video(
            base.VideoGenerationRequest(
                model_id="kie-bytedance-seedance-1.5-pro",
                prompt="a test prompt",
                duration_seconds=8,
            )
        )
        self.assertEqual(handle.status, "queued")
        self.assertEqual(handle.model_id, "kie-bytedance-seedance-1.5-pro")
        estimate = provider.estimate_cost(
            base.ImageGenerationRequest(model_id="kie-gpt-image-2-text-to-image", prompt="x")
        )
        self.assertTrue(estimate.verified)


# ---------------------------------------------------------------------------
# ModelRegistry loading / validation
# ---------------------------------------------------------------------------


class RegistryLoadingTests(unittest.TestCase):
    def test_missing_file_raises_registry_file_error(self) -> None:
        with self.assertRaises(base.RegistryFileError):
            base.ModelRegistry("/nonexistent/path/model-registry.json")

    def test_invalid_json_raises_registry_file_error(self, ) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{ not valid json", encoding="utf-8")
            with self.assertRaises(base.RegistryFileError):
                base.ModelRegistry(bad)

    def test_non_object_top_level_raises_schema_error(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("[1, 2, 3]", encoding="utf-8")
            with self.assertRaises(base.RegistrySchemaError):
                base.ModelRegistry(bad)

    def test_missing_required_model_field_raises_schema_error(self) -> None:
        import tempfile

        data = _load_real_registry_dict()
        del data["models"][0]["price"]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_fixture(Path(tmp) / "reg.json", data)
            with self.assertRaises(base.RegistrySchemaError):
                base.ModelRegistry(path)

    def test_duplicate_model_id_raises_schema_error(self) -> None:
        import tempfile

        data = _load_real_registry_dict()
        dup = copy.deepcopy(data["models"][0])
        data["models"].append(dup)
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_fixture(Path(tmp) / "reg.json", data)
            with self.assertRaises(base.RegistrySchemaError):
                base.ModelRegistry(path)

    def test_invalid_status_raises_schema_error(self) -> None:
        import tempfile

        data = _load_real_registry_dict()
        data["models"][0]["status"] = "totally-not-a-real-status"
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_fixture(Path(tmp) / "reg.json", data)
            with self.assertRaises(base.RegistrySchemaError):
                base.ModelRegistry(path)

    def test_tier_referencing_unknown_model_id_raises_schema_error(self) -> None:
        import tempfile

        data = _load_real_registry_dict()
        data["capability_tiers"]["concept_image"]["candidates"] = ["nonexistent-model-id"]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_fixture(Path(tmp) / "reg.json", data)
            with self.assertRaises(base.RegistrySchemaError):
                base.ModelRegistry(path)

    def test_empty_capabilities_array_raises_schema_error(self) -> None:
        import tempfile

        data = _load_real_registry_dict()
        data["models"][0]["capabilities"] = []
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_fixture(Path(tmp) / "reg.json", data)
            with self.assertRaises(base.RegistrySchemaError):
                base.ModelRegistry(path)

    def test_real_registry_loads_and_validates(self) -> None:
        registry = base.ModelRegistry()
        self.assertEqual(len(registry.snapshot_id), 64)  # sha256 hex digest
        int(registry.snapshot_id, 16)  # raises ValueError if not hex
        self.assertGreaterEqual(len(registry.data["models"]), 1)

    def test_snapshot_id_is_deterministic_across_loads(self) -> None:
        a = base.ModelRegistry()
        b = base.ModelRegistry()
        self.assertEqual(a.snapshot_id, b.snapshot_id)


# ---------------------------------------------------------------------------
# Lookup / capability-tier resolution against the real shipped registry
# ---------------------------------------------------------------------------


class RegistryResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = base.ModelRegistry()

    def test_get_model_unknown_raises_model_not_found(self) -> None:
        with self.assertRaises(base.ModelNotFoundError):
            self.registry.get_model("does-not-exist")

    def test_get_model_known_returns_entry(self) -> None:
        entry = self.registry.get_model("kie-gpt-image-2-text-to-image")
        self.assertEqual(entry["provider_model_slug"], "gpt-image-2-text-to-image")

    def test_unknown_tier_raises_capability_tier_not_found(self) -> None:
        with self.assertRaises(base.CapabilityTierNotFoundError):
            self.registry.resolve_tier("not-a-real-tier")

    def test_list_models_filters_by_capability(self) -> None:
        video_models = self.registry.list_models(capability="image-to-video")
        ids = {m["model_id"] for m in video_models}
        self.assertIn("kie-bytedance-seedance-1.5-pro", ids)
        self.assertIn("kie-gemini-omni-video", ids)
        self.assertNotIn("kie-gpt-image-2-text-to-image", ids)

    def test_list_models_filters_by_status_active(self) -> None:
        for entry in self.registry.list_models(status="active"):
            self.assertEqual(entry["status"], "active")

    def test_concept_image_tier_resolves_to_text_to_image(self) -> None:
        entry = self.registry.resolve_default("concept_image")
        self.assertEqual(entry["model_id"], "kie-gpt-image-2-text-to-image")
        self.assertIn("text-to-image", entry["capabilities"])

    def test_production_scene_image_tier_resolves_to_image_to_image(self) -> None:
        entry = self.registry.resolve_default("production_scene_image")
        self.assertEqual(entry["model_id"], "kie-gpt-image-2-image-to-image")
        self.assertIn("image-to-image", entry["capabilities"])

    def test_premium_override_tier_resolves_and_requires_explicit_approval(self) -> None:
        tiers = self.registry.data["capability_tiers"]
        self.assertTrue(tiers["premium_photoreal_override"]["requires_explicit_approval"])
        candidates = self.registry.resolve_tier("premium_photoreal_override")
        ids = {c["model_id"] for c in candidates}
        self.assertEqual(ids, {"kie-veo3-fast", "kie-veo3-quality"})

    def test_draft_motion_tier_fails_closed_on_unpriced_seedance(self) -> None:
        """This is the central proof for this unit: Kie.ai's own docs say
        Seedance 1.5 Pro pricing is not listed, so the registry records
        amount=null for it — and resolve_tier() with its default
        require_priced=True must refuse to hand back an unpriced model
        rather than let a caller assume a price exists."""
        with self.assertRaises(base.NoActiveCandidateError):
            self.registry.resolve_tier("draft_motion")

    def test_draft_motion_tier_resolves_when_price_not_required(self) -> None:
        candidates = self.registry.resolve_tier("draft_motion", require_priced=False)
        self.assertEqual(candidates[0]["model_id"], "kie-bytedance-seedance-1.5-pro")

    def test_final_connected_motion_tier_also_fails_closed_on_unpriced_seedance(self) -> None:
        with self.assertRaises(base.NoActiveCandidateError):
            self.registry.resolve_tier("final_connected_motion")


# ---------------------------------------------------------------------------
# slug_for / price_for / estimate — the "never hardcoded" contract
# ---------------------------------------------------------------------------


class SlugAndPriceResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = base.ModelRegistry()

    def test_slug_for_returns_provider_wire_slug_not_registry_id(self) -> None:
        slug = self.registry.slug_for("kie-bytedance-seedance-1.5-pro")
        self.assertEqual(slug, "bytedance/seedance-1.5-pro")
        self.assertNotEqual(slug, "kie-bytedance-seedance-1.5-pro")

    def test_slug_for_veo3_variants(self) -> None:
        self.assertEqual(self.registry.slug_for("kie-veo3-fast"), "veo3_fast")
        self.assertEqual(self.registry.slug_for("kie-veo3-quality"), "veo3")

    def test_price_for_resolution_keyed_amount(self) -> None:
        # gpt-image-2 pricing is unverified in the registry, so strict=False
        # is required to inspect the resolved-but-unverified amount.
        price_2k = self.registry.price_for(
            "kie-gpt-image-2-text-to-image", resolution="2K", strict=False
        )
        price_1080 = self.registry.price_for(
            "kie-gpt-image-2-text-to-image", resolution="1080p", strict=False
        )
        self.assertEqual(price_2k["resolved_amount"], 0.05)
        self.assertEqual(price_1080["resolved_amount"], 0.03)

    def test_price_for_strict_raises_on_unverified_price(self) -> None:
        # gpt-image-2 has an amount but price.verified is False (fleet
        # internal estimate, not a confirmed Kie.ai published price).
        with self.assertRaises(base.UnpricedModelError):
            self.registry.price_for("kie-gpt-image-2-text-to-image", resolution="2K", strict=True)

    def test_price_for_strict_raises_on_null_amount(self) -> None:
        with self.assertRaises(base.UnpricedModelError):
            self.registry.price_for("kie-bytedance-seedance-1.5-pro", strict=True)

    def test_price_for_strict_succeeds_on_verified_veo3(self) -> None:
        price = self.registry.price_for("kie-veo3-fast", strict=True)
        self.assertEqual(price["resolved_amount"], 0.40)
        self.assertTrue(price["verified"])

    def test_estimate_verified_model_computes_total_and_stamps_snapshot(self) -> None:
        estimate = self.registry.estimate("kie-veo3-fast", quantity=2)
        self.assertEqual(estimate.unit_price, 0.40)
        self.assertEqual(estimate.estimated_total, 0.80)
        self.assertTrue(estimate.verified)
        self.assertEqual(estimate.registry_snapshot_id, self.registry.snapshot_id)

    def test_estimate_unpriced_model_returns_none_total_not_an_exception(self) -> None:
        estimate = self.registry.estimate("kie-bytedance-seedance-1.5-pro", quantity=8)
        self.assertIsNone(estimate.estimated_total)
        self.assertIsNone(estimate.unit_price)
        self.assertFalse(estimate.verified)
        self.assertIn("no verified price", estimate.note.lower())

    def test_estimate_unverified_priced_model_with_strict_false_computes_total(self) -> None:
        estimate = self.registry.estimate(
            "kie-gpt-image-2-text-to-image", quantity=3, resolution="2K", strict=False
        )
        self.assertEqual(estimate.unit_price, 0.05)
        self.assertEqual(estimate.estimated_total, 0.15)
        self.assertFalse(estimate.verified)  # honestly flagged, not silently trusted


# ---------------------------------------------------------------------------
# Proof that resolution comes from the FILE, never a Python-side constant
# ---------------------------------------------------------------------------


class NeverHardcodedProofTests(unittest.TestCase):
    """Mutates a temp copy of the real registry and shows the resolved slug,
    price, and snapshot_id all change accordingly — if any value were
    hardcoded in base.py instead of read from the file, these would not
    move."""

    def test_mutating_a_copy_changes_resolved_slug_and_snapshot(self) -> None:
        import tempfile

        original = base.ModelRegistry()
        original_slug = original.slug_for("kie-veo3-fast")

        data = _load_real_registry_dict()
        for entry in data["models"]:
            if entry["model_id"] == "kie-veo3-fast":
                entry["provider_model_slug"] = "veo3_fast_MUTATED_FOR_TEST"

        with tempfile.TemporaryDirectory() as tmp:
            path = _write_fixture(Path(tmp) / "reg.json", data)
            mutated = base.ModelRegistry(path)
            mutated_slug = mutated.slug_for("kie-veo3-fast")

        self.assertEqual(original_slug, "veo3_fast")
        self.assertEqual(mutated_slug, "veo3_fast_MUTATED_FOR_TEST")
        self.assertNotEqual(mutated_slug, original_slug)
        self.assertNotEqual(mutated.snapshot_id, original.snapshot_id)

    def test_mutating_a_copy_changes_resolved_price(self) -> None:
        import tempfile

        data = _load_real_registry_dict()
        for entry in data["models"]:
            if entry["model_id"] == "kie-veo3-fast":
                entry["price"]["amount"] = 9.99

        with tempfile.TemporaryDirectory() as tmp:
            path = _write_fixture(Path(tmp) / "reg.json", data)
            mutated = base.ModelRegistry(path)
            price = mutated.price_for("kie-veo3-fast", strict=True)

        self.assertEqual(price["resolved_amount"], 9.99)

    def test_marking_a_model_deprecated_blocks_slug_resolution_by_default(self) -> None:
        import tempfile

        data = _load_real_registry_dict()
        for entry in data["models"]:
            if entry["model_id"] == "kie-veo3-fast":
                entry["status"] = "deprecated"
        # remove it from the premium tier's candidates so tier validation
        # (which forbids deprecated-only tiers implicitly via resolve_tier,
        # not via validate()) still passes structurally.
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_fixture(Path(tmp) / "reg.json", data)
            mutated = base.ModelRegistry(path)
            with self.assertRaises(base.DeprecatedModelError):
                mutated.slug_for("kie-veo3-fast")
            # explicit opt-in still works
            self.assertEqual(
                mutated.slug_for("kie-veo3-fast", allow_deprecated=True), "veo3_fast"
            )
            # and resolve_tier silently excludes it from premium tier now
            candidates = mutated.resolve_tier("premium_photoreal_override")
            ids = {c["model_id"] for c in candidates}
            self.assertNotIn("kie-veo3-fast", ids)
            self.assertIn("kie-veo3-quality", ids)


if __name__ == "__main__":
    unittest.main()
