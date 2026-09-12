#!/usr/bin/env python3
"""
tests/unit/provision-sop-embeddings-hashed-id.test.py
─────────────────────────────────────────────────────────────────────────────
Regression battery — provision_sop_embeddings.py must IMPORT on a box whose
`sops.id` is a CONTENT HASH, and must never report success having written
nothing.

THE BUG (live client Mac mini, 2026-09-11)
    The import was a single statement:
        WHERE sop_id IN (SELECT id FROM main.sops)
    which assumes this box's `sops.id` IS the slug-derived spelling the shipped
    asset uses. On a box where `sops.id` is a content hash (`sop_<64 hex>`) the
    intersection is EMPTY — measured 0 of 2555 asset rows against 3415 local
    SOPs. Nothing was written, and the function still returned status
    "IMPORTED" with a message quoting the MANIFEST's row count, so the roll
    logged a green "imported 2555 rows" line over an embeddings table that
    never grew. Semantic SOP search silently degraded to keyword matching with
    nothing in any log to show for it.

WHY THE EXISTING BATTERY MISSED IT
    tests/unit/provision-sop-embeddings-idempotency.test.py's `_make_client_db`
    fixture builds `sop_id = "sop_" + slug.replace("-", "_")` — the slug form —
    so every case there exercised only the path where ids already match.
    This file builds the HASHED shape the defect needs.

FAIL-FIRST
    Against the pre-fix module: test_hashed_ids_actually_import fails with
    imported_rows == 0 / 0 rows in the table, and
    test_zero_match_reports_warn_not_success fails because the status is
    "IMPORTED". Post-fix both pass.

Run:
    python3 tests/unit/provision-sop-embeddings-hashed-id.test.py
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

_spec = importlib.util.spec_from_file_location(
    "provision_sop_embeddings", _MODULE_DIR / "provision_sop_embeddings.py"
)
assert _spec is not None, "Could not load provision_sop_embeddings.py"
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mod)  # type: ignore
provision_sop_embeddings = mod.provision_sop_embeddings

SCHEMA = """
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

# The manifest's own documented derivation.
def asset_id_for(slug: str) -> str:
    return "sop_" + slug.replace("-", "_")[:60]


def hashed_id_for(slug: str) -> str:
    """The shape a real client box carries: sop_ + 64 hex of a content hash."""
    return "sop_" + hashlib.sha256(slug.encode()).hexdigest()


def make_client_db(slugs, id_style="hashed") -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.executescript(SCHEMA)
    for slug in slugs:
        sid = hashed_id_for(slug) if id_style == "hashed" else asset_id_for(slug)
        conn.execute("INSERT INTO sops (id, name, slug, steps) VALUES (?,?,?,'[]')",
                     (sid, slug.replace("-", " ").title(), slug))
    conn.commit()
    conn.close()
    return tmp.name


def make_asset(sop_ids, model="gemini-embedding-2", dims=3072):
    d = tempfile.mkdtemp()
    dbp = str(Path(d) / "sop-embeddings.sqlite")
    conn = sqlite3.connect(dbp)
    conn.execute(
        "CREATE TABLE sop_embeddings (sop_id TEXT PRIMARY KEY, embedding BLOB NOT NULL, "
        "embedding_model TEXT NOT NULL, embedding_dims INTEGER NOT NULL, embedded_at TEXT NOT NULL)"
    )
    blob = b"\x00\x00\x00\x00" * dims
    for sid in sop_ids:
        conn.execute("INSERT INTO sop_embeddings VALUES (?,?,?,?,datetime('now'))",
                     (sid, blob, model, dims))
    conn.commit()
    conn.close()
    gz = str(Path(d) / "sop-embeddings.sqlite.gz")
    with open(dbp, "rb") as fs, gzip.open(gz, "wb") as fd:
        shutil.copyfileobj(fs, fd)
    return gz, hashlib.sha256(Path(gz).read_bytes()).hexdigest()


def make_manifest(path, gz, sha, count):
    Path(path).write_text(json.dumps({
        "model": "gemini-embedding-2", "dims": 3072, "provider": "gemini",
        "sop_count": count, "release_tag": "sop-embeddings-v1.0.0",
        "asset_url": Path(gz).as_uri(), "sha256": sha,
        "asset_rebuild_required": False,
    }))


def rows_in(db):
    c = sqlite3.connect(db)
    n = c.execute("SELECT COUNT(*) FROM sop_embeddings").fetchone()[0]
    c.close()
    return n


def marker_rows(db):
    c = sqlite3.connect(db)
    try:
        n = c.execute("SELECT COUNT(*) FROM sop_embeddings_shipped_asset").fetchone()[0]
    except sqlite3.Error:
        n = 0
    c.close()
    return n


SLUGS = ["marketing-campaign-launch", "sales-cold-outreach", "billing-failed-payment-recovery"]


class TestHashedIdBox(unittest.TestCase):
    """The defect: sops.id is a content hash, asset ships slug-derived ids."""

    def test_hashed_ids_actually_import(self):
        db = make_client_db(SLUGS, id_style="hashed")
        gz, sha = make_asset([asset_id_for(s) for s in SLUGS])
        man = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        make_manifest(man, gz, sha, len(SLUGS))

        self.assertEqual(rows_in(db), 0, "fixture should start empty")
        res = provision_sop_embeddings(man, db)

        self.assertEqual(res["status"], "IMPORTED", f"expected IMPORTED, got {res}")
        self.assertEqual(
            rows_in(db), len(SLUGS),
            "PRE-FIX FAILURE MODE: the import matched 0 rows on a hashed-id box "
            "because it compared the asset's slug-derived sop_id against sops.id "
            f"directly. Rows in table: {rows_in(db)}, expected {len(SLUGS)}. Detail: {res}",
        )
        self.assertEqual(res.get("imported_rows"), len(SLUGS))

    def test_embeddings_are_keyed_by_the_LOCAL_id(self):
        """A row must be reachable by joining sops.id — otherwise it is orphaned."""
        db = make_client_db(SLUGS, id_style="hashed")
        gz, sha = make_asset([asset_id_for(s) for s in SLUGS])
        man = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        make_manifest(man, gz, sha, len(SLUGS))
        provision_sop_embeddings(man, db)

        c = sqlite3.connect(db)
        joined = c.execute(
            "SELECT COUNT(*) FROM sops s JOIN sop_embeddings e ON e.sop_id = s.id"
        ).fetchone()[0]
        c.close()
        self.assertEqual(joined, len(SLUGS),
                         "every imported embedding must join back to its sops row")

    def test_reported_count_is_actual_not_manifest(self):
        """The asset covers 2 of 3 SOPs — the report must say 2, never the manifest's 3."""
        db = make_client_db(SLUGS, id_style="hashed")
        gz, sha = make_asset([asset_id_for(s) for s in SLUGS[:2]])
        man = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        make_manifest(man, gz, sha, 3)  # manifest overstates on purpose

        res = provision_sop_embeddings(man, db)
        self.assertEqual(res["status"], "IMPORTED")
        self.assertEqual(res.get("imported_rows"), 2, f"got {res}")
        self.assertIn("2", res["reason"])
        self.assertEqual(rows_in(db), 2)


class TestZeroMatchIsNotSuccess(unittest.TestCase):
    """A zero-row import must be loud, and must not stamp the marker."""

    def test_zero_match_reports_warn_not_success(self):
        db = make_client_db(SLUGS, id_style="hashed")
        # Asset for a completely unrelated library — nothing can match.
        gz, sha = make_asset(["sop_something_else_entirely", "sop_not_on_this_box"])
        man = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        make_manifest(man, gz, sha, 2)

        res = provision_sop_embeddings(man, db)
        self.assertEqual(
            res["status"], "WARN",
            "PRE-FIX FAILURE MODE: a zero-row import returned status IMPORTED and a "
            f"message quoting the manifest count, hiding the failure. Got: {res}",
        )
        self.assertEqual(res.get("imported_rows"), 0)
        self.assertEqual(rows_in(db), 0)
        self.assertEqual(marker_rows(db), 0,
                         "must NOT stamp the provisioned marker when nothing imported")


class TestSlugFormBoxStillWorks(unittest.TestCase):
    """No regression for a box whose sops.id already IS the slug-derived id."""

    def test_exact_id_match_path_unchanged(self):
        db = make_client_db(SLUGS, id_style="slug")
        gz, sha = make_asset([asset_id_for(s) for s in SLUGS])
        man = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        make_manifest(man, gz, sha, len(SLUGS))

        res = provision_sop_embeddings(man, db)
        self.assertEqual(res["status"], "IMPORTED", f"got {res}")
        self.assertEqual(rows_in(db), len(SLUGS))
        self.assertEqual(res.get("imported_rows"), len(SLUGS))

    def test_no_row_written_twice(self):
        """Both passes must never double-write the same local id."""
        db = make_client_db(SLUGS, id_style="slug")
        gz, sha = make_asset([asset_id_for(s) for s in SLUGS])
        man = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        make_manifest(man, gz, sha, len(SLUGS))
        res = provision_sop_embeddings(man, db)
        self.assertEqual(res.get("imported_rows"), len(SLUGS),
                         f"double-counted or double-wrote: {res}")


class TestLongSlugTruncation(unittest.TestCase):
    """The derivation truncates at 60 chars — long slugs must still match."""

    def test_slug_longer_than_60_chars(self):
        long_slug = "app-dev-cloud-infrastructure-specialist-monthly-cost-optimization-review-cycle"
        self.assertGreater(len(long_slug.replace("-", "_")), 60)
        db = make_client_db([long_slug], id_style="hashed")
        gz, sha = make_asset([asset_id_for(long_slug)])
        man = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        make_manifest(man, gz, sha, 1)

        res = provision_sop_embeddings(man, db)
        self.assertEqual(res["status"], "IMPORTED", f"got {res}")
        self.assertEqual(rows_in(db), 1, "60-char truncation must be applied identically")


class TestOrphanTableIsNotCoverage(unittest.TestCase):
    """The idempotency gate must measure COVERAGE, not raw row count.

    The defect leaves a box holding a FULL sop_embeddings table whose every row
    is an orphan — keyed to the asset's slug-derived ids while sops.id is a
    content hash, so not one row joins to a SOP. Counting rows, such a box reads
    `2555 >= 2555` and the gate SKIPs it on every roll, FOREVER; the repair can
    never reach it. Fleet sweep 2026-09-12 found 6 boxes stuck exactly here,
    each showing a "full" table with 82-100% of its SOPs unembedded.
    """

    def _orphaned_box(self):
        """A box whose embeddings are all orphans + a marker claiming success."""
        db = make_client_db(SLUGS, id_style="hashed")
        conn = sqlite3.connect(db)
        # Rows keyed to the ASSET's ids, which join to nothing on a hashed box.
        conn.execute("PRAGMA foreign_keys=OFF")
        blob = b"\x00\x00\x00\x00" * 3072
        for s in SLUGS:
            conn.execute(
                "INSERT INTO sop_embeddings VALUES (?,?,?,?,datetime('now'))",
                (asset_id_for(s), blob, "gemini-embedding-2", 3072))
        # The buggy run also stamped the marker despite importing nothing.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sop_embeddings_shipped_asset ("
            "id INTEGER PRIMARY KEY CHECK (id=1), release_tag TEXT NOT NULL, "
            "sop_count INTEGER NOT NULL, sha256 TEXT NOT NULL, "
            "imported_at TEXT NOT NULL DEFAULT (datetime('now')))")
        conn.execute(
            "INSERT OR REPLACE INTO sop_embeddings_shipped_asset "
            "(id, release_tag, sop_count, sha256) VALUES (1,'sop-embeddings-v1.0.0',?,'x')",
            (len(SLUGS),))
        conn.commit()
        conn.close()
        return db

    def test_full_but_orphaned_table_is_not_skipped(self):
        db = self._orphaned_box()
        # Sanity: rows exist, but coverage is zero.
        c = sqlite3.connect(db)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM sop_embeddings").fetchone()[0], len(SLUGS))
        covered = c.execute(
            "SELECT COUNT(*) FROM sops s WHERE EXISTS "
            "(SELECT 1 FROM sop_embeddings e WHERE e.sop_id = s.id)").fetchone()[0]
        c.close()
        self.assertEqual(covered, 0, "fixture must start fully orphaned")

        gz, sha = make_asset([asset_id_for(s) for s in SLUGS])
        man = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        make_manifest(man, gz, sha, len(SLUGS))

        res = provision_sop_embeddings(man, db)
        self.assertNotEqual(
            res["status"], "SKIP",
            "PRE-FIX FAILURE MODE: the gate counted raw rows, saw a full table, and "
            f"SKIPped a box where 100% of SOPs are unembedded — permanently. Got: {res}",
        )
        self.assertEqual(res["status"], "IMPORTED", f"got {res}")

        c = sqlite3.connect(db)
        covered = c.execute(
            "SELECT COUNT(*) FROM sops s WHERE EXISTS "
            "(SELECT 1 FROM sop_embeddings e WHERE e.sop_id = s.id)").fetchone()[0]
        c.close()
        self.assertEqual(covered, len(SLUGS), "every SOP must be covered after the repair")

    def test_genuinely_covered_box_still_skips(self):
        """No new noise: a properly covered box must still SKIP (no re-download)."""
        db = make_client_db(SLUGS, id_style="hashed")
        gz, sha = make_asset([asset_id_for(s) for s in SLUGS])
        man = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        make_manifest(man, gz, sha, len(SLUGS))

        first = provision_sop_embeddings(man, db)
        self.assertEqual(first["status"], "IMPORTED", f"setup import failed: {first}")

        second = provision_sop_embeddings(man, db)
        self.assertEqual(second["status"], "SKIP",
                         f"a covered box must skip rather than re-download: {second}")
        self.assertIn("covered", second["reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
