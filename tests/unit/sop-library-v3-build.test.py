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
import sqlite3
import sys
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


_EMBED_DIR = _REPO / "shared-utils" / "sop-embed-once"
_rspec = importlib.util.spec_from_file_location("role_library_vectors", _EMBED_DIR / "role_library_vectors.py")
rlv = importlib.util.module_from_spec(_rspec)
sys.path.insert(0, str(_EMBED_DIR))
_rspec.loader.exec_module(rlv)
_pspec = importlib.util.spec_from_file_location("provision_sop_embeddings", _EMBED_DIR / "provision_sop_embeddings.py")
prov = importlib.util.module_from_spec(_pspec)
_pspec.loader.exec_module(prov)

# Golden embed texts produced by the Command Center's own TypeScript
# (parseRoleHowTo + buildSOPEmbedText, blackceo-command-center main, 2026-09-23).
GOLDEN = [
    ("sales", "appointment-setter",
     "# Appointment Setter How-To\n\nBook qualified calls for the team.\n\n## 9. SOPs\n\n"
     "### SOP 9.1 Qualify the lead\nConfirm budget.\n\n### SOP 9.2: Book the appointment\nOffer two slots.\n",
     "Appointment Setter How-To | Book qualified calls for the team. | "
     "appointment-setter,sales,appointment,setter | 1. Qualify the lead; 2. Book the appointment"),
    ("billing", "devils-advocate",
     "> note\n# Devil's Advocate\n\n- Challenge every plan.\n\n## 9 things to know\nx\n\n"
     "## Stress-test the plan\ny\n\n## Devil's Advocate\nz\n",
     "Devil's Advocate | Challenge every plan. | devils-advocate,billing,devils,advocate | "
     "1. 9 things to know; 2. Stress-test the plan"),
    ("engineering", "qc-specialist", "Plain text with no headings at all.\r\nSecond line.\r\n",
     "Qc Specialist | Plain text with no headings at all. | qc-specialist,engineering,specialist | "
     "Follow qc-specialist how-to"),
]


def _vec(n=3072, v=0.5):
    return [v] * n


class RoleLibraryVectors(unittest.TestCase):
    def test_parser_matches_the_command_center_byte_for_byte(self):
        from embed_sop_library import build_sop_embed_text
        for dept, role, md, want in GOLDEN:
            rec = rlv.parse_role_howto(md, dept, role)
            self.assertEqual(rec["slug"], f"role-library:{dept}/{role}")
            self.assertEqual(build_sop_embed_text(rec), want)

    def test_aliases_cover_the_folder_names_boxes_use(self):
        e = {"slug": "devils-advocate--billing", "dept": "billing", "title": "Devil's Advocate"}
        self.assertEqual(rlv.role_slug_aliases(e, lambda t: "devil-s-advocate"),
                         {"devils-advocate--billing", "devils-advocate-billing",
                          "devil-s-advocate", "devils-advocate"})

    def test_embed_is_hash_skipped_and_retired_aliases_are_dropped(self):
        conn = sqlite3.connect(":memory:")
        recs = [rlv.parse_role_howto(md, d, r) for d, r, md, _ in GOLDEN]
        calls = []
        fake = lambda t: calls.append(t) or _vec()  # noqa: E731
        self.assertEqual(rlv.embed_roles(conn, recs, embed_fn=fake)["embedded"], 3)
        again = rlv.embed_roles(conn, recs[:2], embed_fn=fake)
        self.assertEqual((again["embedded"], again["skipped_unchanged"], again["removed_stale"]), (0, 2, 1))
        self.assertEqual(len(calls), 3)
        self.assertTrue(rlv.verify(conn, "gemini-embedding-2", 3072)[0])


class ProvisionRoleRowsBySlug(unittest.TestCase):
    """importRoleLibrary() rows have random ids: the shipped vector must land on the
    LOCAL sops.id by exact slug, and a converge that adds role rows re-arms it."""

    def _asset(self, tmp):
        shipped = Path(tmp) / "shipped.sqlite"
        c = sqlite3.connect(shipped)
        c.executescript(
            "CREATE TABLE sop_embeddings (sop_id TEXT PRIMARY KEY, embedding BLOB, embedding_model TEXT,"
            " embedding_dims INTEGER, embedded_at TEXT, source_content_md5 TEXT);" + rlv.SCHEMA_SQL)
        blob = bytes(3072 * 4)
        c.execute("INSERT INTO sop_embeddings VALUES ('sop_lib_one', ?, 'gemini-embedding-2', 3072, 'now', 'x')", (blob,))
        for slug in ("role-library:sales/appointment-setter", "role-library:billing/devils-advocate"):
            c.execute("INSERT INTO role_library_embeddings VALUES (?, ?, 'gemini-embedding-2', 3072, 'now', 'x')",
                      (slug, blob))
        c.commit(); c.close()
        gz = Path(tmp) / "sop-embeddings.sqlite.gz"
        gz.write_bytes(gzip.compress(shipped.read_bytes()))
        manifest = Path(tmp) / "m.json"
        manifest.write_text(json.dumps({
            "release_tag": "t1", "asset_url": gz.as_uri(), "sha256": hashlib.sha256(gz.read_bytes()).hexdigest(),
            "sop_count": 1, "role_library_count": 2, "model": "gemini-embedding-2", "dims": 3072}))
        return manifest

    def _box(self, tmp):
        db = Path(tmp) / "mc.db"
        c = sqlite3.connect(db)
        c.executescript(
            "CREATE TABLE sops (id TEXT PRIMARY KEY, slug TEXT UNIQUE, source TEXT, deleted_at TEXT);"
            "CREATE TABLE sop_embeddings (sop_id TEXT PRIMARY KEY, embedding BLOB NOT NULL,"
            " embedding_model TEXT NOT NULL, embedding_dims INTEGER NOT NULL, embedded_at TEXT NOT NULL);"
            "INSERT INTO sops VALUES ('sop_lib_one', 'lib-one', NULL, NULL);"
            "INSERT INTO sops VALUES ('uuid-1', 'role-library:sales/appointment-setter', 'role-library', NULL);"
            "INSERT INTO sops VALUES ('uuid-9', 'role-library:sales/custom-role', 'role-library', NULL);")
        c.commit(); c.close()
        return db

    def test_role_rows_get_vectors_by_exact_slug_and_rearm_on_new_rows(self):
        with tempfile.TemporaryDirectory() as t:
            manifest, db = self._asset(t), self._box(t)
            first = prov.provision_sop_embeddings(str(manifest), str(db), dry_run=False)
            self.assertEqual(first["status"], "IMPORTED", first)
            c = sqlite3.connect(db)
            have = {r[0] for r in c.execute("SELECT sop_id FROM sop_embeddings")}
            self.assertEqual(have, {"sop_lib_one", "uuid-1"}, "custom role with no shipped slug stays unembedded")
            c.close()

            self.assertEqual(prov.provision_sop_embeddings(str(manifest), str(db), dry_run=False)["status"], "SKIP")

            c = sqlite3.connect(db)  # a later converge adds a library role row
            c.execute("INSERT INTO sops VALUES ('uuid-2', 'role-library:billing/devils-advocate', 'role-library', NULL)")
            c.commit(); c.close()
            third = prov.provision_sop_embeddings(str(manifest), str(db), dry_run=False)
            self.assertEqual(third["status"], "IMPORTED", "new role rows must re-arm provisioning")
            c = sqlite3.connect(db)
            self.assertIn("uuid-2", {r[0] for r in c.execute("SELECT sop_id FROM sop_embeddings")})
            c.close()


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
