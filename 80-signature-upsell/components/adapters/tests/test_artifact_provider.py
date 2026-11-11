"""Issue 16 (harmony review): Skill 80's result artifacts carry `provider`.

Skill 83's stub rule (`_provider_of` in launcher_core/page_designs.py) reads
`artifact["provider"]`. Skill 80's artifacts carried none, so placeholder
pictures could not be named on an upsell page (UPS-23). `produce.py` now takes
`--image-provider stub|kie` and stamps it on every artifact of the result; the
result schema allows exactly those two values and nothing else.

Run: python3 -m unittest discover -s tests -v   (from adapters/)
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ADAPTERS_DIR = Path(__file__).resolve().parents[1]
WORK_DIR = ADAPTERS_DIR.parent
SKILL_DIR = WORK_DIR / "80-signature-upsell"
FIXTURES = ADAPTERS_DIR / "fixtures"
sys.path.insert(0, str(ADAPTERS_DIR))

import adapter_common as common
import produce
import upsell1_adapter
import upsell2_adapter

COPY1 = SKILL_DIR / "fixtures" / "copy-upsell1-public.valid.json"
REQUEST1 = SKILL_DIR / "fixtures" / "request-upsell1.testonly.json"
JOURNEY1 = FIXTURES / "journey-main-only.testonly.json"
RESULT_SCHEMA = SKILL_DIR / "schemas" / "upsell-result.schema.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_u1(**extra):
    return upsell1_adapter.build_bundle(
        load(REQUEST1), load(COPY1), load(JOURNEY1),
        copy_sha256=common.sha256_file(COPY1),
        copy_artifact_path="80-signature-upsell/fixtures/copy-upsell1-public.valid.json",
        **extra)


def build_u2(**extra):
    request = load(SKILL_DIR / "fixtures" / "request-upsell2.testonly.json")
    copy_path = SKILL_DIR / "fixtures" / "copy-upsell2-public.valid.json"
    journey = load(FIXTURES / "journey-upsell2-from-upsell1.testonly.json")
    return upsell2_adapter.build_bundle(
        request, load(copy_path), journey,
        copy_sha256=common.sha256_file(copy_path),
        copy_artifact_path="80-signature-upsell/fixtures/copy-upsell2-public.valid.json",
        **extra)


class ArtifactProviderTests(unittest.TestCase):
    def test_u1_artifacts_carry_the_named_provider(self):
        for provider in ("stub", "kie"):
            artifacts = build_u1(image_provider=provider)["result"]["artifacts"]
            self.assertTrue(artifacts)
            self.assertEqual({a.get("provider") for a in artifacts}, {provider})

    def test_u2_artifacts_carry_the_named_provider(self):
        for provider in ("stub", "kie"):
            artifacts = build_u2(image_provider=provider)["result"]["artifacts"]
            self.assertTrue(artifacts)
            self.assertEqual({a.get("provider") for a in artifacts}, {provider})

    def test_result_with_provider_validates_against_the_shipped_schema(self):
        result = build_u1(image_provider="stub")["result"]
        self.assertEqual(common.schema_errors(result, load(RESULT_SCHEMA)), [])

    def test_provider_is_never_invented_when_none_is_named(self):
        # No image provider named: the artifact says nothing (Skill 83 then
        # reports the provider as unknown on a live package) - it is never
        # defaulted to a flattering value.
        for build in (build_u1, build_u2):
            for art in build()["result"]["artifacts"]:
                self.assertNotIn("provider", art)

    def test_unknown_provider_is_refused_by_the_builder(self):
        with self.assertRaises(common.AdapterError):
            build_u1(image_provider="midjourney")

    def test_schema_refuses_an_unknown_provider_value(self):
        result = build_u1(image_provider="stub")["result"]
        result["artifacts"][0]["provider"] = "midjourney"
        self.assertTrue(common.schema_errors(result, load(RESULT_SCHEMA)))

    def test_schema_still_refuses_other_extra_artifact_keys(self):
        result = build_u1()["result"]
        result["artifacts"][0]["surprise"] = 1
        self.assertTrue(common.schema_errors(result, load(RESULT_SCHEMA)))


class ProduceCliProviderTests(unittest.TestCase):
    def _run(self, *extra):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle.json"
            proc = subprocess.run(
                [sys.executable, str(ADAPTERS_DIR / "produce.py"),
                 "--instance", "upsell_1", "--request", str(REQUEST1),
                 "--copy", str(COPY1), "--journey", str(JOURNEY1),
                 "--copy-artifact-path",
                 "80-signature-upsell/fixtures/copy-upsell1-public.valid.json",
                 "--out", str(out), *extra],
                capture_output=True, text=True)
            bundle = load(out) if out.is_file() else None
        return proc, bundle

    def test_cli_stamps_the_provider(self):
        proc, bundle = self._run("--image-provider", "kie")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual({a["provider"] for a in bundle["result"]["artifacts"]},
                         {"kie"})

    def test_cli_without_the_flag_adds_no_provider(self):
        proc, bundle = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(all("provider" not in a
                            for a in bundle["result"]["artifacts"]))

    def test_cli_refuses_an_unknown_provider_and_writes_nothing(self):
        proc, bundle = self._run("--image-provider", "midjourney")
        self.assertEqual(proc.returncode, 2)
        self.assertIsNone(bundle)


class UnknownProviderEnforcementLayerTests(unittest.TestCase):
    """One test per layer, so removing any single layer is caught."""

    def test_image_providers_is_exactly_stub_and_kie(self):
        self.assertEqual(common.IMAGE_PROVIDERS, ("stub", "kie"))

    def _build_result(self, provider):
        request = load(REQUEST1)
        # Schema validation stubbed out: only the tuple check in build_result
        # can refuse the provider here.
        with mock.patch.object(common, "validate_against_schema"):
            return common.build_result(
                request=request, copy_sha256="0" * 64, copy_artifact_path="c.json",
                cta_map=[], eligibility_check={"verdict": "ineligible"},
                disposition={"action": "present_offer", "reason": "x"},
                test_outcomes=[], copy_validation={"verdict": "pass"},
                image_provider=provider)

    def test_build_result_refuses_unknown_provider_without_the_schema(self):
        self.assertEqual(
            self._build_result("stub")["artifacts"][0]["provider"], "stub")
        with self.assertRaises(common.AdapterError) as ctx:
            self._build_result("bogus")
        self.assertIn("image_provider", str(ctx.exception))

    def test_build_result_refuses_an_empty_provider(self):
        # "" is not "none named": it must be refused, never silently dropped.
        with self.assertRaises(common.AdapterError):
            self._build_result("")

    def test_schema_enum_is_exactly_the_builder_vocabulary(self):
        schema = load(RESULT_SCHEMA)
        artifact = schema["properties"]["artifacts"]["items"]
        self.assertEqual(artifact["properties"]["provider"]["enum"],
                         list(common.IMAGE_PROVIDERS))

    def test_argparse_exits_2_before_any_adapter_code_runs(self):
        boom = AssertionError("adapter code ran")
        with mock.patch.object(common, "load_json", side_effect=boom), \
                mock.patch.object(upsell1_adapter, "build_bundle", side_effect=boom), \
                mock.patch.object(upsell2_adapter, "build_bundle", side_effect=boom), \
                mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit) as ctx:
                produce.main([
                    "--instance", "upsell_1", "--request", "r", "--copy", "c",
                    "--journey", "j", "--out", "o", "--image-provider", "bogus"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
