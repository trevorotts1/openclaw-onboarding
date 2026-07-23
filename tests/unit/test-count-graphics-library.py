#!/usr/bin/env python3
"""Unit tests for U136 graphics library live counter."""

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "count-graphics-library.py"
assert SCRIPT.exists(), f"Script not found: {SCRIPT}"

spec = importlib.util.spec_from_file_location("count_graphics_library", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

count_cards = mod.count_cards
count_assets = mod.count_assets
atomic_write_json = mod.atomic_write_json
_utc_now = mod._utc_now


class TestCountGraphicsLibrary(unittest.TestCase):

    def setUp(self):
        self.tmp_root = Path(tempfile.mkdtemp(prefix="u136-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp_root, ignore_errors=True)

    def test_empty_library_returns_zero(self):
        lib = self.tmp_root / "empty"; lib.mkdir()
        self.assertEqual(count_cards(lib), 0)
        self.assertEqual(count_assets(lib), 0)

    def test_single_card_rules_excluded(self):
        lib = self.tmp_root / "lib"; lib.mkdir()
        cat = lib / "single-image-designs"; cat.mkdir()
        (cat / "SI-001_golden_style.md").write_text("# Card")
        (cat / "_RULES.md").write_text("# rules")
        self.assertEqual(count_cards(lib), 1)

    def test_system_prefixed_dirs_excluded(self):
        lib = self.tmp_root / "lib"; lib.mkdir()
        (lib / "_system").mkdir()
        (lib / "_system" / "sop.md").write_text("# sop")
        (lib / "_cache").mkdir()
        (lib / "_cache" / "meta.md").write_text("# meta")
        self.assertEqual(count_cards(lib), 0)

    def test_multiple_categories_multiple_cards(self):
        lib = self.tmp_root / "lib"; lib.mkdir()
        for cn in ("single-image-designs", "banner-designs", "book-cover-designs"):
            d = lib / cn; d.mkdir()
            (d / "_RULES.md").write_text("# rules")
            for i in range(1, 5):
                (d / f"card-{i}.md").write_text(f"# card {i}")
        self.assertEqual(count_cards(lib), 12)

    def test_asset_counting(self):
        lib = self.tmp_root / "lib"; lib.mkdir()
        (lib / "banner-designs").mkdir()
        (lib / "banner-designs" / "hero.png").write_text("png")
        (lib / "banner-designs" / "hero.jpg").write_text("jpg")
        (lib / "single-image-designs").mkdir()
        (lib / "single-image-designs" / "thumb.webp").write_text("webp")
        self.assertEqual(count_assets(lib), 3)
        self.assertEqual(count_cards(lib), 0)

    def test_atomic_write_round_trip(self):
        d = self.tmp_root / "out"; d.mkdir()
        f = d / "count.json"
        data = {"card_count": 42, "asset_count": 19000, "total": 19042,
                "last_counted_at": "2026-07-23T14:00:00Z",
                "library_root": "/test", "source_version": "1.0.0"}
        atomic_write_json(f, data)
        self.assertEqual(json.loads(f.read_text()), data)

    def test_unwritable_directory_raises(self):
        d = self.tmp_root / "bad"; d.mkdir(mode=0o444)
        with self.assertRaises((OSError, PermissionError)):
            atomic_write_json(d / "nope.json", {"test": True})

    def test_nonexistent_library_returns_zero(self):
        p = self.tmp_root / "ghost"
        self.assertEqual(count_cards(p), 0)
        self.assertEqual(count_assets(p), 0)

    def test_non_card_docs_excluded(self):
        lib = self.tmp_root / "lib"; lib.mkdir()
        (lib / "INDEX.md").write_text("# idx")
        (lib / "README.md").write_text("# readme")
        (lib / "DEPARTMENT-BUILD-BRIEF.md").write_text("# brief")
        (lib / "social-media-designs").mkdir()
        (lib / "social-media-designs" / "_RULES.md").write_text("# rules")
        (lib / "social-media-designs" / "SM-001.md").write_text("# card")
        self.assertEqual(count_cards(lib), 1)

    def test_timestamp_format(self):
        ts = _utc_now()
        import re
        self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_case_insensitive_extensions(self):
        lib = self.tmp_root / "lib"; lib.mkdir()
        (lib / "fb").mkdir()
        (lib / "fb" / "ad.PNG").write_text("png")
        (lib / "fb" / "ad.JPG").write_text("jpg")
        self.assertEqual(count_assets(lib), 2)

    def test_deeply_nested_assets_counted(self):
        lib = self.tmp_root / "lib"; lib.mkdir()
        n = lib / "ppt" / "theme" / "bg"
        n.mkdir(parents=True)
        (n / "a.png").write_text("a")
        (n / "b.png").write_text("b")
        self.assertEqual(count_assets(lib), 2)

    def test_total_invariant(self):
        lib = self.tmp_root / "lib"; lib.mkdir()
        (lib / "si").mkdir()
        (lib / "si" / "A.md").write_text("# a")
        (lib / "si" / "B.md").write_text("# b")
        (lib / "bn").mkdir()
        (lib / "bn" / "x.png").write_text("png")
        (lib / "bn" / "y.jpg").write_text("jpg")
        c = count_cards(lib); a = count_assets(lib)
        self.assertEqual(c + a, 4)

    def test_card_md_not_double_counted(self):
        lib = self.tmp_root / "lib"; lib.mkdir()
        (lib / "si").mkdir()
        (lib / "si" / "A.md").write_text("# card")
        (lib / "si" / "hero.png").write_text("png")
        self.assertEqual(count_cards(lib), 1)
        self.assertEqual(count_assets(lib), 1)

    def test_self_test_harness_passes(self):
        self.assertEqual(mod._run_self_tests(), 0)

    def test_script_version_exported(self):
        self.assertIsInstance(mod.SCRIPT_VERSION, str)
        self.assertTrue(len(mod.SCRIPT_VERSION) > 0)
        import re
        self.assertRegex(mod.SCRIPT_VERSION, r"^\d+\.\d+\.\d+$")

    def test_default_library_path(self):
        self.assertIn("45-design-intelligence-library", str(mod.DEFAULT_LIBRARY))

    def test_mutation_exclusion_removed_counts_former_excluded(self):
        """Mutation proof: removing exclusion causes _RULES.md to be counted."""
        lib = self.tmp_root / "lib"; lib.mkdir()
        (lib / "single-image-designs").mkdir()
        (lib / "single-image-designs" / "_RULES.md").write_text("# rules")
        (lib / "single-image-designs" / "SI-001.md").write_text("# card")
        self.assertEqual(count_cards(lib), 1, "Baseline: _RULES.md excluded")
        (lib / "single-image-designs" / "RULES.md").write_text("# rules")
        self.assertEqual(count_cards(lib), 2, "Mutation: RULES.md counted")


if __name__ == "__main__":
    unittest.main()
