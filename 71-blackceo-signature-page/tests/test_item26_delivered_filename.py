#!/usr/bin/env python3
"""Item 26 (Update Plan): delivered image filename convention unified
(proposal P6, ruled 2026-10-15, approved as proposed).

One convention: the manifest and inventory carry the three-digit
internal ID (IMG-001); delivered files carry the two-digit Image-NN.png
derived from it. Pins:
  (a) validate_image_manifest.delivered_filename derives the canonical
      delivered name (IMG-001 -> Image-01.png, IMG-012 -> Image-12.png,
      IMG-123 -> Image-123.png);
  (b) the filename-to-manifest mapping check passes a conforming entry
      and fails by name: the internal-ID form (IMG-001.png), the
      three-digit delivered form (Image-001.png), a wrong number
      (Image-02.png for IMG-001), and an asset/prompt file whose
      trailing number belongs to a different internal ID;
  (c) the SOP delivery text (Stage 9C) and the Stage 8 save text state
      the convention, the mapping, and the check;
  (d) references/artifact-contracts.md carries the convention section
      and its image-map example pairs id IMG-001 with filename
      Image-01.png;
  (e) references/kie-generation-route.md states the save naming and its
      receipt example uses the delivered name;
  (f) blast radius: the stage list is unchanged and the
      image-generation-qc per-file glob still matches by the Image-*
      form (the gate's numeric matching is unchanged).
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_image_manifest as vim  # noqa: E402


def entry(**overrides):
    base = {
        "id": "IMG-001",
        "source_passage": "Hero promise",
        "job": "Hero authority",
        "scene": "Specific hero scene",
        "people": "Fictional subject",
        "shot_plan": "Wide",
        "style_grade": "Page style",
        "text_mode": "no-generated-text",
        "references": [],
        "technical_plan": "Wide master",
        "prompt_file": "prompts/IMG-001.md",
        "asset_file": "generated/Image-01.png",
        "filename": "Image-01.png",
        "status": "ready",
        "qc_status": "passed",
    }
    base.update(overrides)
    return base


class DerivationPins(unittest.TestCase):
    def test_delivered_filename_derivation(self):
        self.assertEqual(vim.delivered_filename("IMG-001"), "Image-01.png")
        self.assertEqual(vim.delivered_filename("IMG-007"), "Image-07.png")
        self.assertEqual(vim.delivered_filename("IMG-012"), "Image-12.png")
        self.assertEqual(vim.delivered_filename("IMG-123"), "Image-123.png")
        self.assertIsNone(vim.delivered_filename("hero-image"))


class MappingCheckPins(unittest.TestCase):
    def test_conforming_manifest_passes(self):
        self.assertEqual(vim.validate({"images": [entry()]}), [])

    def test_internal_id_form_as_delivered_name_fails_by_name(self):
        errors = vim.validate({"images": [entry(filename="IMG-001.png")]})
        self.assertTrue(any("IMG-001.png" in e and "Image-01.png" in e
                            for e in errors), errors)

    def test_three_digit_delivered_form_fails_by_name(self):
        errors = vim.validate({"images": [entry(filename="Image-001.png")]})
        self.assertTrue(any("Image-001.png" in e and "Image-01.png" in e
                            for e in errors), errors)

    def test_wrong_number_fails_by_name(self):
        errors = vim.validate({"images": [entry(filename="Image-02.png")]})
        self.assertTrue(any("Image-02.png" in e for e in errors), errors)

    def test_asset_number_mismatch_fails_by_name(self):
        errors = vim.validate(
            {"images": [entry(asset_file="generated/Image-02.png")]})
        self.assertTrue(any("asset_file" in e and "IMG-001" in e
                            for e in errors), errors)

    def test_prompt_number_mismatch_fails_by_name(self):
        errors = vim.validate(
            {"images": [entry(prompt_file="prompts/IMG-002.md")]})
        self.assertTrue(any("prompt_file" in e for e in errors), errors)

    def test_second_entry_maps_to_its_own_id(self):
        e2 = entry(id="IMG-012", prompt_file="prompts/IMG-012.md",
                   asset_file="generated/Image-12.png",
                   filename="Image-12.png")
        self.assertEqual(vim.validate({"images": [entry(), e2]}), [])


class TextPins(unittest.TestCase):
    def test_sop_delivery_text_states_the_convention(self):
        sop = (ROOT / "references" /
               "BlackCEO-Signature-Landing-Page-Production-and-QC-SOP-v1.md"
               ).read_text(encoding="utf-8")
        stage9 = sop.split("## Stage 9")[1].split("## Stage 10")[0]
        self.assertIn("Image-01.png", stage9)
        self.assertIn("IMG-001", stage9)
        self.assertIn("Item 26", stage9)
        self.assertIn("validate_image_manifest.py", stage9)
        stage8 = sop.split("## Stage 8")[1].split("## Stage 9")[0]
        self.assertIn("Image-NN.png", stage8)
        self.assertIn("IMG-001", stage8)

    def test_artifact_contracts_carry_the_convention(self):
        text = (ROOT / "references" / "artifact-contracts.md").read_text(
            encoding="utf-8")
        self.assertIn("Delivered image filename convention "
                      "(Update Plan Item 26", text)
        self.assertIn('"id": "IMG-001"', text)
        self.assertIn('"filename": "Image-01.png"', text)
        self.assertNotIn('"filename": "IMG-001.png"', text)

    def test_kie_route_states_save_naming(self):
        text = (ROOT / "references" / "kie-generation-route.md").read_text(
            encoding="utf-8")
        self.assertIn("Save naming (Update Plan Item 26", text)
        self.assertIn("delivered_filename", text)
        self.assertIn('"image-generation-qc/Image-01.png"', text)
        self.assertNotIn("image-generation-qc/Image-001.png", text)


class BlastRadiusPins(unittest.TestCase):
    def test_stage_list_and_generation_glob_unchanged(self):
        contract = json.loads(
            (ROOT / "references" / "stage-contract.json").read_text(
                encoding="utf-8"))
        self.assertEqual(contract["stage_order"], [
            "intake", "copy", "font-action-plan", "desktop-wireframe",
            "mobile-tablet", "visual-mockup", "image-inventory-prompts",
            "image-generation-qc", "image-map-upload", "design-board", "final-mockups",
            "responsive-html", "ghl-install-test", "publish-verify",
            "automation-wiring"])
        spec = contract["stages"]["image-generation-qc"]
        self.assertEqual(spec["per_file_glob"],
                         "image-generation-qc/Image-*.png")


if __name__ == "__main__":
    unittest.main(verbosity=2)
