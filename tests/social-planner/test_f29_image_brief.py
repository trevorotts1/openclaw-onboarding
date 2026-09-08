#!/usr/bin/env python3
"""
test_f29_image_brief.py — F29 unified image briefs + finished-creative
verification (QC-F29).

Fixture-driven; no live model calls, no real OCR (the actual vision reviewer
sees the asset per F37; this validates the structured inputs/receipts). Covers:
  - the unified brief schema validates required fields (brand palette, logo
    rules, audience, composition, copy, approved assets, safe areas,
    destination dimensions) BEFORE prompt compilation;
  - wrong-brand art (palette drift, mark redrawn), misspelled text, and an
    invalid crop FAIL the delivered-asset visual QC;
  - one failed asset does NOT discard successful copy or other account assets
    (isolation with bounded regeneration cost/retries);
  - the preview references the approved revision; preview + original URLs
    recorded;
  - routing by capability, not a stale model name (Midjourney v6 gone from
    prompt 05; capability routing refuses non-text models for text assets).

Run:  python3 -m unittest discover -s tests/social-planner -p 'test_f*.py'
"""

import json
import os
import sys
import unittest

_ONB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SHARED = os.path.join(_ONB_ROOT, "shared-utils")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import social_image_brief as ib  # noqa: E402

GOOD_BRIEF = {
    "brand_palette": {"primary": "#0B3D2E", "accent": "#C9A24B"},
    "logo_rules": {"usage": "footer mark", "min_clear_space": "20px",
                   "references": [{"name": "client logo", "role": "identity",
                                   "instruction": "reproduce exactly; preserve geometry and colors"}]},
    "audience": "small business owners seeking pricing confidence",
    "composition": {"focal_message": "grow with confidence", "hierarchy": "subject first",
                    "framing": "centered", "whitespace": "generous", "ratio": "4:5"},
    "copy": {"on_image_text": "Grow With Confidence", "spelling_lock": True,
             "placement": "upper third", "hierarchy": "headline"},
    "approved_assets": ["asset-logo-1", "asset-product-1"],
    "safe_areas": {"platform_ratio": "4:5", "keep_in": "central 80%"},
    "destination_dimensions": {"platform": "instagram", "ratio": "4:5", "pixels": "1080x1350"},
}


def _asset(**over):
    asset = {
        "brief": GOOD_BRIEF,
        "delivered_dimensions": "1080x1350",
        "ocr_text": "Grow With Confidence",
        "palette_seen": ["#0B3D2E", "#C9A24B"],
        "logo_reproduced": True,
        "crop_respects_safe_areas": True,
        "preview_url": "https://preview.example/approved-r1.png",
        "original_url": "https://original.example/r1.png",
        "revision": "r1",
        "approved_revision": "r1",
    }
    asset.update(over)
    return asset


class TestUnifiedBriefSchema(unittest.TestCase):
    def test_complete_brief_validates(self):
        r = ib.validate_brief(GOOD_BRIEF)
        self.assertTrue(r["valid"], r["problems"])

    def test_each_required_field_fails_when_missing(self):
        for field in ("brand_palette", "logo_rules", "audience", "composition",
                      "copy", "approved_assets", "safe_areas",
                      "destination_dimensions"):
            broken = {k: v for k, v in GOOD_BRIEF.items() if k != field}
            r = ib.validate_brief(broken)
            self.assertFalse(r["valid"], field)
            codes = [p["detail"] for p in r["problems"]]
            self.assertTrue(any(field in d for d in codes), codes)

    def test_ad_hoc_palette_color_fails(self):
        broken = json.loads(json.dumps(GOOD_BRIEF))
        broken["brand_palette"]["primary"] = "deep green"
        r = ib.validate_brief(broken)
        self.assertFalse(r["valid"])
        self.assertTrue(any(p["code"] == "AF-BRIEF-PALETTE" for p in r["problems"]))

    def test_missing_spelling_lock_fails(self):
        broken = json.loads(json.dumps(GOOD_BRIEF))
        broken["copy"]["spelling_lock"] = False
        r = ib.validate_brief(broken)
        self.assertFalse(r["valid"])
        self.assertTrue(any(p["code"] == "AF-BRIEF-SPELLING-LOCK" for p in r["problems"]))

    def test_explicit_no_text_is_valid(self):
        brief = json.loads(json.dumps(GOOD_BRIEF))
        brief["copy"]["on_image_text"] = ""
        r = ib.validate_brief(brief)
        self.assertTrue(r["valid"], r["problems"])


class TestDeliveredAssetVisualQC(unittest.TestCase):
    def test_wrong_brand_art_fails(self):
        # palette drifted AND mark not reproduced
        r = ib.validate_delivered_asset(_asset(palette_seen=["#FF00FF", "#00FF00"],
                                               logo_reproduced=False))
        codes = [p["code"] for p in r["problems"]]
        self.assertIn("AF-VQC-BRAND", codes)

    def test_misspelled_text_fails(self):
        r = ib.validate_delivered_asset(_asset(ocr_text="Grow With Confidnce"))
        codes = [p["code"] for p in r["problems"]]
        self.assertIn("AF-VQC-OCR", codes)

    def test_invalid_crop_fails(self):
        r = ib.validate_delivered_asset(_asset(crop_respects_safe_areas=False))
        self.assertTrue(any(p["code"] == "AF-VQC-CROP" for p in r["problems"]))

    def test_wrong_dimensions_fail(self):
        r = ib.validate_delivered_asset(_asset(delivered_dimensions="1080x1080"))
        self.assertTrue(any(p["code"] == "AF-VQC-DIMENSIONS" for p in r["problems"]))

    def test_text_in_no_text_image_fails(self):
        brief = json.loads(json.dumps(GOOD_BRIEF))
        brief["copy"]["on_image_text"] = ""
        r = ib.validate_delivered_asset(_asset(brief=brief, ocr_text="SURPRISE TEXT"))
        self.assertTrue(any(p["code"] == "AF-VQC-OCR" for p in r["problems"]))

    def test_healthy_asset_passes(self):
        r = ib.validate_delivered_asset(_asset())
        self.assertTrue(r["valid"], r["problems"])


class TestPreviewRevisionAndIsolation(unittest.TestCase):
    def test_preview_must_reference_approved_revision(self):
        r = ib.validate_delivered_asset(_asset(revision="r2"))
        self.assertTrue(any(p["code"] == "AF-VQC-REVISION" for p in r["problems"]))

    def test_missing_urls_fail_receipt(self):
        r = ib.validate_delivered_asset(_asset(preview_url="", original_url=""))
        self.assertTrue(any(p["code"] == "AF-VQC-RECEIPT" for p in r["problems"]))

    def test_one_failed_asset_does_not_discard_others(self):
        results = {
            "day1-image": {"valid": False, "problems": [{"code": "AF-VQC-OCR"}]},
            "day1-copy": {"valid": True},
            "day1-video": {"valid": True},
            "day2-image": {"valid": True},
        }
        iso = ib.isolate_and_retry(results, max_retries=2, max_cost_per_retry=0.12)
        self.assertIn("day1-copy", iso["healthy"])
        self.assertIn("day2-image", iso["healthy"])
        self.assertIn("day1-image", iso["failed"])
        self.assertFalse(iso["failed"]["day1-image"]["blocks_others"])
        self.assertTrue(iso["bounded"])
        regen = iso["failed"]["day1-image"]["regeneration"]
        self.assertEqual(regen["attempts_remaining"], 2)
        self.assertEqual(regen["max_cost_per_retry_usd"], 0.12)
        self.assertTrue(regen["expose_alternatives_for_approval"])

    def test_healthy_copy_survives_when_video_fails(self):
        results = {"copy": {"valid": True}, "video": {"valid": False, "problems": []}}
        iso = ib.isolate_and_retry(results)
        self.assertIn("copy", iso["healthy"])
        self.assertIn("video", iso["failed"])


class TestCapabilityRouting(unittest.TestCase):
    def test_prompt_05_dropped_midjourney(self):
        path = os.path.join(_ONB_ROOT, "57-social-media-in-a-box", "prompts",
                            "05-visual-prompt-architect.md")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        # the stale naming is gone from any ACTIVE instruction
        self.assertNotIn("You are a Midjourney Prompt Engineer", text)
        self.assertIn("CAPABILITY", text.upper())
        for field in ("brand_palette", "logo_rules", "audience", "composition",
                      "copy", "approved_assets", "safe_areas",
                      "destination_dimensions"):
            self.assertIn(field, text, field)

    def test_text_asset_never_routes_to_non_text_model(self):
        r = ib.route_by_capability("nano-banana-2", needs_text=True)
        self.assertFalse(r["routed"])

    def test_gpt_image2_and_agnes_eligible(self):
        for model in ("gpt-image-2-text-to-image", "agnes-image-2.1-flash"):
            r = ib.route_by_capability(model, needs_text=True)
            self.assertTrue(r["routed"], r)

    def test_no_text_needs_routes_freely(self):
        r = ib.route_by_capability("nano-banana-2", needs_text=False)
        self.assertTrue(r["routed"])


if __name__ == "__main__":
    unittest.main()