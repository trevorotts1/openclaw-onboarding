#!/usr/bin/env python3
"""SOP library v3: builder contract + manifest pins (offline, no network).

The 145 department SOPs under role-library/<dept>/sops/ were never in the SOP
library asset boxes download. build_sop_library.py appends them to the V2
records, which it must carry VERBATIM (same slug => same sops.id on every box,
so an existing box upserts and never duplicates).

Run: python3 tests/unit/sop-library-v3-build.test.py
"""
import gzip
import hashlib
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
_ROLE_LIB = _REPO / "23-ai-workforce-blueprint" / "templates" / "role-library"
_LIB_MANIFEST = _REPO / "shared-utils" / "sop-library" / "SOP-LIBRARY-MANIFEST.json"
_EMB_MANIFEST = _REPO / "shared-utils" / "sop-embed-once" / "SOP-EMBEDDINGS-MANIFEST.json"
_PUBLISH_SH = _REPO / "shared-utils" / "sop-embed-once" / "build-and-publish.sh"

_spec = importlib.util.spec_from_file_location(
    "build_sop_library", _REPO / "shared-utils" / "sop-library" / "build_sop_library.py")
bsl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bsl)

V2_LINES = [
    json.dumps({"slug": "sales-closer-daily-pipeline-review", "name": "Sales: Pipeline", "steps": []}),
    json.dumps({"slug": "graphics-designer-weekly-audit", "name": "Graphics: Audit", "steps": []}),
]


def _fixture(tmp, sop_files, base_lines=V2_LINES):
    tmp = Path(tmp)
    base = tmp / "v2.jsonl.gz"
    base.write_bytes(gzip.compress(("\n".join(base_lines) + "\n").encode()))
    lib = tmp / "role-library"
    entries = []
    for dept, name, body in sop_files:
        p = lib / dept / "sops" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        entries.append({"slug": Path(name).stem, "dept": dept,
                        "path": f"templates/role-library/{dept}/sops/{name}"})
    lib.mkdir(exist_ok=True)
    (lib / "_index.json").write_text(json.dumps({"sops": entries}))
    return base, hashlib.sha256(base.read_bytes()).hexdigest(), lib, tmp / "out.jsonl.gz"


DIU = """# SOP-DIU-101 — Style Analysis

**Owner Role:** Style Analyst ("The Eye")

Turn source imagery into reusable style cards.

## Inputs
- Reference material
- Brief

## Procedure
1. Verify production status
2. Extract the 12 dimensions
"""


class BuilderContract(unittest.TestCase):
    def test_v2_verbatim_plus_one_record_per_dept_sop(self):
        with tempfile.TemporaryDirectory() as t:
            base, sha, lib, out = _fixture(t, [("graphics", "SOP-DIU-101.md", DIU)])
            s = bsl.build(base, sha, lib, out)
            lines = gzip.decompress(Path(out).read_bytes()).decode().splitlines()
            self.assertEqual(lines[:2], V2_LINES, "V2 records must be carried byte-for-byte")
            self.assertEqual((s["base_records"], s["new_records"], s["jsonl_record_count"]), (2, 1, 3))
            rec = json.loads(lines[2])
            self.assertEqual(rec["slug"], "graphics-sop-diu-101")
            self.assertEqual(rec["department"], "graphics")
            self.assertEqual(rec["source_role"], "style-analyst")
            self.assertEqual(rec["description"], "Turn source imagery into reusable style cards.")
            self.assertEqual([st["name"] for st in rec["steps"]], ["Inputs", "Procedure"])
            self.assertEqual(rec["steps"][1]["checklist"],
                             ["Verify production status", "Extract the 12 dimensions"])
            self.assertIn("/role-library/graphics/sops/SOP-DIU-101.md", rec["source_file_url"])

    def test_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as t:
            base, sha, lib, out = _fixture(t, [("graphics", "SOP-DIU-101.md", DIU)])
            a = bsl.build(base, sha, lib, out)["sha256"]
            b = bsl.build(base, sha, lib, out)["sha256"]
            self.assertEqual(a, b)

    def test_refuses_base_that_does_not_match_the_pin(self):
        with tempfile.TemporaryDirectory() as t:
            base, _, lib, out = _fixture(t, [("graphics", "SOP-DIU-101.md", DIU)])
            with self.assertRaises(SystemExit):
                bsl.build(base, "0" * 64, lib, out)

    def test_refuses_a_slug_that_would_overwrite_a_v2_row(self):
        with tempfile.TemporaryDirectory() as t:
            clash = [json.dumps({"slug": "graphics-sop-diu-101", "name": "x", "steps": []})]
            base, sha, lib, out = _fixture(t, [("graphics", "SOP-DIU-101.md", DIU)], clash)
            with self.assertRaises(SystemExit):
                bsl.build(base, sha, lib, out)

    def test_refuses_a_collision_under_the_embeddings_60_char_id_rule(self):
        long_v2 = "graphics-" + "x" * 70 + "-a"
        base_line = [json.dumps({"slug": long_v2, "name": "x", "steps": []})]
        stem = "x" * 70 + "-b"  # same first 60 chars after the dept prefix
        with tempfile.TemporaryDirectory() as t:
            base, sha, lib, out = _fixture(t, [("graphics", stem + ".md", DIU)], base_line)
            with self.assertRaises(SystemExit):
                bsl.build(base, sha, lib, out)


class ManifestPins(unittest.TestCase):
    def setUp(self):
        self.lib = json.loads(_LIB_MANIFEST.read_text())
        self.emb = json.loads(_EMB_MANIFEST.read_text())

    def test_library_manifest_pins_v3(self):
        self.assertEqual(self.lib["release_tag"], "sop-library-v3.0.0")
        self.assertEqual(self.lib["asset"], "sops-library-v3.jsonl.gz")
        self.assertTrue(self.lib["asset_url"].endswith(
            f"/{self.lib['release_tag']}/{self.lib['asset']}"))
        self.assertEqual(len(self.lib["sha256"]), 64)
        # sha256(slug) ids + UNIQUE slug => one row per distinct slug.
        self.assertEqual(self.lib["canonical_sop_count"], self.lib["distinct_slug_count"])

    def test_v3_sample_slugs_are_real_department_sops(self):
        """The skip gate needs samples that EXIST (U079 shipped 10 that did not,
        so the gate never skipped). The v3 samples must map to real files."""
        inventory = {bsl.dept_sop_slug(d, p.stem) for d, p in bsl.dept_sop_files(_ROLE_LIB)}
        new = [s for s in self.lib["canonical_sample_slugs"] if s in inventory]
        self.assertGreaterEqual(len(new), 3, "need several v3-only samples so V2-only boxes re-ingest")
        self.assertGreaterEqual(len(self.lib["canonical_sample_slugs"]) - len(new), 3,
                                "need V2 samples too")

    def test_embeddings_built_from_the_pinned_library(self):
        self.assertEqual(self.emb["source_jsonl_release_tag"], self.lib["release_tag"])
        self.assertEqual((self.emb["model"], self.emb["dims"]), ("gemini-embedding-2", 3072))
        self.assertFalse(self.emb["asset_rebuild_required"])

    def test_dept_sop_inventory_matches_index(self):
        index = json.loads((_ROLE_LIB / "_index.json").read_text())
        self.assertEqual(len(bsl.dept_sop_files(_ROLE_LIB)), len(index["sops"]))


class PublishScript(unittest.TestCase):
    def setUp(self):
        self.sh = _PUBLISH_SH.read_text()

    def test_asset_release_never_takes_latest(self):
        self.assertRegex(self.sh, r"gh release create[^\n]*--latest=false")

    def test_library_pin_comes_from_the_library_manifest(self):
        self.assertIn("sop-library/SOP-LIBRARY-MANIFEST.json", self.sh)
        self.assertNotRegex(self.sh, r'^SOP_ASSET_NAME="sops-library-v2\.jsonl\.gz"$')
        self.assertIsNone(re.search(r'^DEFAULT_JSONL_TAG="v10\.13\.29"$', self.sh, re.M))


if __name__ == "__main__":
    unittest.main(verbosity=2)
