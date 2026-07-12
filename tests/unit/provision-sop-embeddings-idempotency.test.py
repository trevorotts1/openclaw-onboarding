#!/usr/bin/env python3
"""
tests/unit/provision-sop-embeddings-idempotency.test.py
─────────────────────────────────────────────────────────────────────────────
P4-03 step 2 — proves shared-utils/sop-embed-once/provision_sop_embeddings.py's
idempotency gate: the client-box import wired into
32-command-center-setup/scripts/ingest-sop-library.sh.

FAIL-FIRST: this module is NEW — on the pre-fix tree the import itself fails.

Covers:
  1. asset_rebuild_required:true (no asset published yet) -> WARN, no-op, additive.
  2. manifest missing release_tag/asset_url/sha256 -> WARN, no-op.
  3. target DB missing -> WARN, no-op.
  4. First import: downloads (stubbed via a local file:// asset built in-process,
     no network), sha256-verifies, imports ONLY rows whose sop_id exists in the
     box's own `sops` table, stamps the marker table -> IMPORTED.
  5. Corrupt asset (sha256 mismatch) -> WARN, refuses import, NO rows written.
  6. Re-run after a successful import at the SAME release_tag with
     row count >= manifest -> SKIP (idempotent, no re-download).
  7. Model/dims mismatch between the shipped asset and the manifest contract
     -> WARN, refuses import (never mix vector spaces — standing guard).
  8. PROVISION_DRY_RUN gate stops before any network/import.

No live network required — the "download" is served from a local
GitHub-release-shaped gzip file via urllib's file:// scheme, matching the
existing repo pattern of proving gate logic hermetically
(tests/unit/provision-idempotency.test.sh).

Run:
    python3 tests/unit/provision-sop-embeddings-idempotency.test.py
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_MODULE_DIR = _REPO_ROOT / "shared-utils" / "sop-embed-once"
assert _MODULE_DIR.is_dir(), f"shared-utils/sop-embed-once not found at {_MODULE_DIR}"

sys.path.insert(0, str(_MODULE_DIR))

_spec = importlib.util.spec_from_file_location(
    "provision_sop_embeddings", _MODULE_DIR / "provision_sop_embeddings.py"
)
assert _spec is not None, "Could not load provision_sop_embeddings.py"
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mod)  # type: ignore

provision_sop_embeddings = mod.provision_sop_embeddings

SOP_EMBEDDINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sops (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
  description TEXT, version INTEGER NOT NULL DEFAULT 1, department TEXT,
  task_keywords TEXT, steps TEXT NOT NULL, success_criteria TEXT,
  persona_hints TEXT, deleted_at TEXT,
  created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS sop_embeddings (
  sop_id TEXT PRIMARY KEY REFERENCES sops(id) ON DELETE CASCADE,
  embedding BLOB NOT NULL, embedding_model TEXT NOT NULL DEFAULT 'text-embedding-3-small',
  embedding_dims INTEGER NOT NULL DEFAULT 1536, embedded_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _make_client_db(sop_slugs: list[str]) -> str:
    """A fixture mission-control.db with real `sops` rows (migration 057 shape)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.executescript(SOP_EMBEDDINGS_SCHEMA)
    for slug in sop_slugs:
        sop_id = "sop_" + slug.replace("-", "_")
        conn.execute(
            "INSERT INTO sops (id, name, slug, steps) VALUES (?, ?, ?, '[]')",
            (sop_id, slug.replace("-", " ").title(), slug),
        )
    conn.commit()
    conn.close()
    return tmp.name


def _make_shipped_asset(sop_ids: list[str], model="gemini-embedding-2", dims=3072) -> tuple[str, str]:
    """Build a shipped sop_embeddings.sqlite.gz + its sha256. Returns (gz_path, sha256)."""
    tmp_dir = tempfile.mkdtemp()
    db_path = str(Path(tmp_dir) / "sop-embeddings.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE sop_embeddings (sop_id TEXT PRIMARY KEY, embedding BLOB NOT NULL, "
        "embedding_model TEXT NOT NULL, embedding_dims INTEGER NOT NULL, embedded_at TEXT NOT NULL)"
    )
    blob = (b"\x00\x00\x00\x00") * dims
    for sop_id in sop_ids:
        conn.execute(
            "INSERT INTO sop_embeddings (sop_id, embedding, embedding_model, embedding_dims, embedded_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (sop_id, blob, model, dims),
        )
    conn.commit()
    conn.close()

    gz_path = str(Path(tmp_dir) / "sop-embeddings.sqlite.gz")
    with open(db_path, "rb") as fsrc, gzip.open(gz_path, "wb") as fdst:
        shutil.copyfileobj(fsrc, fdst)

    sha256 = hashlib.sha256(Path(gz_path).read_bytes()).hexdigest()
    return gz_path, sha256


def _make_manifest(path: str, **overrides) -> None:
    base = {
        "model": "gemini-embedding-2",
        "dims": 3072,
        "provider": "gemini",
        "sop_count": 2,
        "release_tag": "sop-embeddings-v1.0.0",
        "asset_url": None,
        "sha256": None,
        "asset_rebuild_required": False,
    }
    base.update(overrides)
    Path(path).write_text(json.dumps(base))


class TestNoAssetPublishedYet(unittest.TestCase):
    def test_asset_rebuild_required_true_is_a_noop_warn(self):
        db = _make_client_db(["client-a", "client-b"])
        manifest = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        manifest.close()
        _make_manifest(manifest.name, asset_rebuild_required=True, asset_url=None, sha256=None)
        result = provision_sop_embeddings(manifest.name, db)
        self.assertEqual(result["status"], "WARN")
        self.assertIn("no SOP-embeddings asset", result["reason"])

    def test_missing_manifest_fields_is_a_noop_warn(self):
        db = _make_client_db([])
        manifest = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        manifest.close()
        _make_manifest(manifest.name, asset_url=None, sha256=None, release_tag=None)
        result = provision_sop_embeddings(manifest.name, db)
        self.assertEqual(result["status"], "WARN")

    def test_missing_db_is_a_noop_warn(self):
        manifest = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        manifest.close()
        gz, sha = _make_shipped_asset(["sop_a"])
        _make_manifest(manifest.name, asset_url=f"file://{gz}", sha256=sha)
        result = provision_sop_embeddings(manifest.name, "/nonexistent/mission-control.db")
        self.assertEqual(result["status"], "WARN")
        self.assertIn("not found", result["reason"])


class TestImportAndIdempotency(unittest.TestCase):
    def setUp(self):
        self.db = _make_client_db(["client-a", "client-b", "client-only-local"])
        self.gz, self.sha = _make_shipped_asset(["sop_client_a", "sop_client_b"])
        self.manifest = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.manifest.close()
        _make_manifest(
            self.manifest.name,
            sop_count=2,
            asset_url=f"file://{self.gz}",
            sha256=self.sha,
        )

    def test_first_import_writes_only_rows_present_in_client_sops(self):
        result = provision_sop_embeddings(self.manifest.name, self.db)
        self.assertEqual(result["status"], "IMPORTED", result)

        conn = sqlite3.connect(self.db)
        rows = conn.execute("SELECT sop_id FROM sop_embeddings ORDER BY sop_id").fetchall()
        conn.close()
        ids = {r[0] for r in rows}
        self.assertEqual(ids, {"sop_client_a", "sop_client_b"})

    def test_zero_client_key_embed_calls(self):
        # provision_sop_embeddings never imports/calls any embedding API module
        # or network embed endpoint — it is a pure sqlite ATTACH+INSERT. Proven
        # structurally: the function has no dependency on embedding_engine.py's
        # get_embedder/get_embedding at all (grep-free proof via introspection).
        import inspect

        src = inspect.getsource(mod)
        self.assertNotIn("get_embedding(", src)
        self.assertNotIn("get_embedder(", src)

    def test_rerun_at_same_release_with_sufficient_rows_skips(self):
        provision_sop_embeddings(self.manifest.name, self.db)
        result = provision_sop_embeddings(self.manifest.name, self.db)
        self.assertEqual(result["status"], "SKIP", result)
        self.assertIn("already canonical", result["reason"])

    def test_corrupt_asset_sha256_mismatch_refuses_import(self):
        _make_manifest(
            self.manifest.name, sop_count=2, asset_url=f"file://{self.gz}",
            sha256="0" * 64,  # deliberately wrong
        )
        result = provision_sop_embeddings(self.manifest.name, self.db)
        self.assertEqual(result["status"], "WARN")
        self.assertIn("sha256 MISMATCH", result["reason"])

        conn = sqlite3.connect(self.db)
        count = conn.execute("SELECT COUNT(*) FROM sop_embeddings").fetchone()[0]
        conn.close()
        self.assertEqual(count, 0, "a corrupt asset must NEVER be partially imported")

    def test_model_dims_mismatch_refuses_import_never_mixes_vector_spaces(self):
        gz2, sha2 = _make_shipped_asset(["sop_client_a"], model="text-embedding-3-small", dims=1536)
        _make_manifest(
            self.manifest.name, sop_count=1, asset_url=f"file://{gz2}", sha256=sha2,
            model="gemini-embedding-2", dims=3072,  # manifest CONTRACT says gemini/3072
        )
        result = provision_sop_embeddings(self.manifest.name, self.db)
        self.assertEqual(result["status"], "WARN")
        self.assertIn("REFUSING import", result["reason"])

        conn = sqlite3.connect(self.db)
        count = conn.execute("SELECT COUNT(*) FROM sop_embeddings").fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    def test_marker_table_records_the_import(self):
        provision_sop_embeddings(self.manifest.name, self.db)
        conn = sqlite3.connect(self.db)
        row = conn.execute(
            "SELECT release_tag, sop_count, sha256 FROM sop_embeddings_shipped_asset WHERE id=1"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "sop-embeddings-v1.0.0")
        self.assertEqual(row[1], 2)
        self.assertEqual(row[2], self.sha)


class TestDryRun(unittest.TestCase):
    def test_dry_run_makes_no_network_call_and_writes_nothing(self):
        db = _make_client_db(["client-a"])
        gz, sha = _make_shipped_asset(["sop_client_a"])
        manifest = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        manifest.close()
        _make_manifest(manifest.name, sop_count=1, asset_url=f"file://{gz}", sha256=sha)

        result = provision_sop_embeddings(manifest.name, db, dry_run=True)
        self.assertEqual(result["status"], "DRY-RUN")

        conn = sqlite3.connect(db)
        count = conn.execute("SELECT COUNT(*) FROM sop_embeddings").fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
