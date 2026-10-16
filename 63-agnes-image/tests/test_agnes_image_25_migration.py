"""Migration tests for the Agnes Image 2.5 Flash default (Skill 63, S63).

Run from the skill folder:
    python3 -m unittest discover -s tests -v

Offline only: no network, no provider call, no credentials.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


resolve_model = load("resolve_model", "resolve_model.py")
launch_policy = load("launch_prompt_policy", "launch_prompt_policy.py")
provider_receipt = load("provider_receipt", "provider_receipt.py")
response_persist = load("response_persist", "response_persist.py")
validate_payload = load("validate_payload", "validate_payload.py")

ALL_ELEMENTS = {"subject", "environment", "style", "lighting", "composition", "output"}
COMPLETE_SHORT = (
    "Subject: a founder portrait. Environment: bright studio, white backdrop. "
    "Style: editorial photography. Lighting: soft key light. Composition: "
    "head-and-shoulders, centered. Output: 2K, 3:4."
)


class ResolverTests(unittest.TestCase):
    def test_default_is_exact_image_25(self):
        r = resolve_model.resolve_model(None)
        self.assertEqual(r.model_id, "agnes-image-2.5-flash")
        self.assertEqual(r.role, "default")

    def test_generic_alias_to_default(self):
        self.assertEqual(resolve_model.resolve_model("agnes image").model_id,
                         "agnes-image-2.5-flash")

    def test_legacy_pin_preserved(self):
        r = resolve_model.resolve_model("agnes-image-2.1-flash")
        self.assertEqual(r.model_id, "agnes-image-2.1-flash")
        self.assertEqual(r.role, "legacy")

    def test_text_video_rejected(self):
        for bad in ("agnes-2.5-flash", "agnes-video-2.5-flash"):
            with self.assertRaises(resolve_model.ResolutionError):
                resolve_model.resolve_model(bad)

    def test_registry_roles(self):
        roles = resolve_model.registry_roles(SKILL / "models.json")
        self.assertEqual(roles["agnes-image-2.5-flash"], "default")
        self.assertEqual(roles["agnes-image-2.1-flash"], "legacy")


class PayloadValidatorTests(unittest.TestCase):
    def test_default_25_payload_valid(self):
        ok, code, errors, _ = validate_payload.validate_payload_data({
            "model": "agnes-image-2.5-flash", "prompt": "A scenic view",
            "size": "2K", "ratio": "16:9",
            "extra_body": {"response_format": "url"}})
        self.assertTrue(ok, errors)
        self.assertEqual(code, 0)

    def test_text_model_rejected(self):
        ok, code, errors, _ = validate_payload.validate_payload_data({
            "model": "agnes-2.5-flash", "prompt": "x", "size": "1K"})
        self.assertFalse(ok)
        self.assertEqual(code, 2)


class PolicyReceiptTests(unittest.TestCase):
    def test_complete_short_prompt_passes(self):
        res = launch_policy.evaluate_launch_policy(
            COMPLETE_SHORT, set(ALL_ELEMENTS), launch_policy.CapInfo("not_published"))
        self.assertTrue(res.valid, res.errors)

    def test_padding_fails_and_unknown_cap_stays_unknown(self):
        padded = " ".join(["the same filler sentence repeats here again now"] * 60)
        self.assertFalse(launch_policy.evaluate_launch_policy(
            padded, set(ALL_ELEMENTS), launch_policy.CapInfo("not_published")).valid)
        long_ok = launch_policy.evaluate_launch_policy(
            "x" * 25000, set(ALL_ELEMENTS), launch_policy.CapInfo("not_published"))
        self.assertTrue(long_ok.valid)

    def test_agnes_receipt_no_fake_task_id(self):
        receipt = provider_receipt.build_agnes_receipt(
            model_id="agnes-image-2.5-flash", prompt=COMPLETE_SHORT,
            output_bytes=b"fixture", dimensions="1728x2304", output_path="out/f.png")
        self.assertIsNone(receipt["task_id"])
        provider_receipt.validate_receipt(receipt)
        receipt["kie_task_id"] = "fake"
        with self.assertRaises(provider_receipt.ReceiptError):
            provider_receipt.validate_receipt(receipt)


class ResponsePersistTests(unittest.TestCase):
    def test_html_refused_and_png_saved(self):
        import struct, zlib
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">II", 2624, 1472) + b"\x08\x06\x00\x00\x00"
        ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data
        ihdr += struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
        png = sig + ihdr
        with tempfile.TemporaryDirectory() as td:
            saved = response_persist.persist_image(png, Path(td) / "a.png")
            self.assertEqual(saved.dimensions, "2624x1472")
            with self.assertRaises(response_persist.ResponseError):
                response_persist.persist_image(b"<html>error</html>", Path(td) / "b.png")


class F1FallbackTests(unittest.TestCase):
    def test_decodable_nonimage_b64_falls_back_to_url(self):
        import base64 as b64mod
        junk = b64mod.b64encode(b"not an image").decode()
        resp = {"data": [{"url": "https://example.test/x.png", "b64_json": junk}]}
        import struct, zlib
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">II", 64, 64) + b"\x08\x06\x00\x00\x00"
        ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data
        ihdr += struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
        png = sig + ihdr
        raw = response_persist.extract_image_bytes(resp, lambda url: png)
        self.assertEqual(raw, png)


class ScriptSelfTests(unittest.TestCase):
    def test_bundled_self_tests_pass(self):
        for script in ("validate_payload.py", "validate_prompt.py",
                       "normalize_alias.py"):
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / script), "--self-test"],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"{script}: {proc.stdout} {proc.stderr}")
        proc = subprocess.run(
            [sys.executable, str(SKILL / "prove_agnes_image_prompt_floor.py"), "--self-test"],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_models_json_parses(self):
        entries = json.loads((SKILL / "models.json").read_text())
        self.assertEqual(len(entries), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
