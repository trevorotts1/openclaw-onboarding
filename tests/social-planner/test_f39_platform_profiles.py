#!/usr/bin/env python3
"""
test_f39_platform_profiles.py — F39 versioned platform strategy profiles
(QC-F39).

Covers:
  - every discovered supported platform has a versioned capability/strategy
    profile with source URLs + checked_at recorded;
  - the profile version + checked_at are recorded in the content contract
    (provenance block);
  - stale-profile detection: checked_at older than the policy window triggers
    a refresh task while the LAST VERIFIED SAFE profile keeps serving (other
    channels never stop);
  - an unsupported native-only format resolves to the approved supported
    variant or an isolated unavailable mark — never a silent drop, never a
    block on other channels;
  - one theme yields VISIBLY DIFFERENT Instagram/TikTok/LinkedIn treatments;
  - prompt 16 consumes the selected profiles.

Run:  python3 -m unittest discover -s tests/social-planner -p 'test_f*.py'
"""

import datetime
import json
import os
import sys
import unittest

_ONB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SHARED = os.path.join(_ONB_ROOT, "shared-utils")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import social_platform_profiles as spp  # noqa: E402

_CAPS = os.path.join(_ONB_ROOT, "35-social-media-planner", "config",
                     "platform-capabilities.json")
_STRATEGIES = os.path.join(_ONB_ROOT, "35-social-media-planner", "references",
                           "platform-strategies")
SUPPORTED = ("instagram", "tiktok", "linkedin", "facebook", "pinterest", "x",
             "youtube", "google-business-profile", "threads")


class TestVersionedProfiles(unittest.TestCase):
    def test_every_supported_platform_has_profile(self):
        with open(_CAPS, encoding="utf-8") as f:
            caps = json.load(f)
        for pid in SUPPORTED:
            self.assertIn(pid, caps["profiles"], pid)
            p = caps["profiles"][pid]
            self.assertIn(p["profile_version"], p["checked_at"] or "x")  # dates present
            self.assertTrue(p["source_urls"], f"{pid} missing source URLs")
            self.assertRegex(p["checked_at"], r"^\d{4}-\d{2}-\d{2}$")

    def test_each_platform_has_markdown_strategy(self):
        for pid in SUPPORTED:
            path = os.path.join(_STRATEGIES, f"{pid}.md")
            self.assertTrue(os.path.isfile(path), path)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("checked_at", text)
            self.assertIn("Advertising lane", text)  # organic vs ads separated

    def test_organic_and_advertising_separated(self):
        with open(_CAPS, encoding="utf-8") as f:
            caps = json.load(f)
        for pid, p in caps["profiles"].items():
            self.assertIn("organic_guidance_summary", p, pid)
            self.assertIn("advertising_guidance_summary", p, pid)
            self.assertTrue(p["organic_guidance_summary"])
            self.assertTrue(p["advertising_guidance_summary"])


class TestProfileRecorded(unittest.TestCase):
    def test_version_recorded_in_contract(self):
        prof = spp.select_profile("instagram")
        block = spp.record_in_contract(prof)
        self.assertEqual(block["profile_platform"], "instagram")
        self.assertEqual(block["profile_version"], "2026-09-08")
        self.assertEqual(block["profile_checked_at"], "2026-09-08")
        self.assertTrue(block["profile_source_urls"])

    def test_all_supported_platforms_resolve(self):
        for pid in SUPPORTED:
            prof = spp.select_profile(pid)
            self.assertTrue(prof["found"], pid)
            self.assertFalse(prof["stale"], pid)  # checked today
            self.assertFalse(prof["actions"], pid)


class TestStaleProfileDetection(unittest.TestCase):
    def test_older_than_window_is_stale_with_refresh_action(self):
        # policy window is 45 days; 2026-09-08 + 46+ days = stale
        prof = spp.select_profile("instagram", now=datetime.datetime(2026, 11, 1))
        self.assertTrue(prof["stale"])
        self.assertTrue(any(a["type"] == "refresh_profile" for a in prof["actions"]))
        # last verified SAFE profile still serves its guidance
        self.assertTrue(prof["organic_guidance"])

    def test_within_window_not_stale(self):
        prof = spp.select_profile("instagram", now=datetime.datetime(2026, 10, 1))
        self.assertFalse(prof["stale"])

    def test_unparsable_checked_at_treated_stale(self):
        with open(_CAPS, encoding="utf-8") as f:
            caps = json.load(f)
        broken = json.loads(json.dumps(caps))
        broken["profiles"]["x"]["checked_at"] = "not-a-date"
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as t:
            json.dump(broken, t)
            path = t.name
        try:
            prof = spp.select_profile("x", now=None, ) if False else None
            prof = spp.load_profiles(path)
            stale = spp.profile_is_stale(broken["profiles"]["x"])
            self.assertTrue(stale)
        finally:
            os.unlink(path)


class TestUnsupportedFormat(unittest.TestCase):
    def test_unsupported_native_format_yields_variant(self):
        prof = spp.select_profile("linkedin")
        r = spp.resolve_format(prof, "document_carousel_pdf")
        self.assertFalse(r["supported"])
        self.assertEqual(r["approved_variant"], "post")
        self.assertIn("other channels continue", r["detail"])

    def test_threads_unsupported_platform_marks_unavailable(self):
        prof = spp.select_profile("threads")
        r = spp.resolve_format(prof, "post")
        self.assertFalse(r["supported"])
        self.assertTrue(r.get("unavailable"))
        self.assertIn("other channels continue", r["detail"])

    def test_supported_format_passes(self):
        prof = spp.select_profile("tiktok")
        r = spp.resolve_format(prof, "video")
        self.assertTrue(r["supported"])

    def test_unknown_platform_creates_adapter_task_not_block(self):
        r = spp.select_profile("bluesky")
        self.assertFalse(r["found"])
        self.assertTrue(any(a["type"] == "create_profile_task" for a in r["actions"]))
        self.assertTrue(r.get("needs_adapter"))


class TestOneThemeDifferentTreatments(unittest.TestCase):
    def test_ig_tiktok_linkedin_guidance_differs(self):
        guidance = {pid: spp.select_profile(pid)["organic_guidance"]
                    for pid in ("instagram", "tiktok", "linkedin")}
        self.assertNotEqual(guidance["instagram"], guidance["tiktok"])
        self.assertNotEqual(guidance["tiktok"], guidance["linkedin"])
        self.assertNotEqual(guidance["instagram"], guidance["linkedin"])

    def test_format_rules_differ_per_platform(self):
        rules = {pid: spp.select_profile(pid)["format_rules"]
                 for pid in ("instagram", "linkedin", "pinterest")}
        self.assertNotEqual(rules["instagram"], rules["linkedin"])
        self.assertNotEqual(rules["linkedin"], rules["pinterest"])


class TestPrompt16ConsumesProfiles(unittest.TestCase):
    def test_prompt_16_documents_profile_consumption(self):
        path = os.path.join(_ONB_ROOT, "57-social-media-in-a-box", "prompts",
                            "16-multi-platform-reformatter.md")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for needle in ("VERSIONED PLATFORM STRATEGY PROFILES",
                       "VISIBLY DIFFERENT", "platformStrategyProfiles",
                       "profile_version", "checked_at",
                       "approved SUPPORTED variant",
                       "block the other platforms"):
            self.assertIn(needle, text, needle)


if __name__ == "__main__":
    unittest.main()