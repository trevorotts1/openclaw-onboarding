#!/usr/bin/env python3
"""
tests/unit/persona-fleet-index-verify.test.py
─────────────────────────────────────────────────────────────────────────────
A-U8 (Skill 6 v2, book-to-persona embeddings wiring) acceptance (c):
"the publish script exits non-zero when neither an index entry nor a
deferred receipt exists."

Proves 22-.../pipeline/persona_fleet.py::index_verify() (and its CLI
`index-verify` subcommand, exercised via subprocess exactly as
publish-personas-to-fleet.sh calls it):

  1. A workspace persona present in the embeddings table of gemini-index.sqlite
     passes (indexed).
  2. A workspace persona with NO index row but an honest
     personas/<slug>/embedding-receipt.json (status='deferred') passes
     (deferred).
  3. A workspace persona with NEITHER an index row NOR a deferred receipt
     FAILS — exit code 7, named in stderr.
  4. A receipt whose status is NOT 'deferred' (e.g. a stray/garbage file)
     does NOT count as an excuse — still fails if unindexed.

Pure stdlib, offline, hermetic (mirrors persona_fleet.py's own design tenet).

Run:
    python3 tests/unit/persona-fleet-index-verify.test.py
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_PIPE = _REPO_ROOT / "22-book-to-persona-coaching-leadership-system" / "pipeline"
_PF = _PIPE / "persona_fleet.py"
assert _PF.is_file()

_spec = importlib.util.spec_from_file_location("persona_fleet", _PF)
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)


def _make_embeddings_db(db_path: Path, indexed_slugs: list) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE embeddings (
            id TEXT PRIMARY KEY, file_path TEXT, chunk_index INTEGER,
            content TEXT, vector BLOB, last_updated REAL,
            provider TEXT, model TEXT, dim INTEGER
        )
    """)
    for i, slug in enumerate(indexed_slugs):
        conn.execute(
            "INSERT INTO embeddings (id, file_path, chunk_index, content, "
            "vector, last_updated, provider, model, dim) VALUES (?,?,?,?,?,?,?,?,?)",
            (f"row{i}",
             f"/home/x/.openclaw/workspace/data/coaching-personas/personas/{slug}/persona-blueprint.md",
             0, "content", b"\x00" * 12288, 0.0, "gemini", "gemini-embedding-2", 3072))
    conn.commit()
    conn.close()


def _write_deferred_receipt(workspace: Path, slug: str, status: str = "deferred") -> None:
    d = workspace / "personas" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "embedding-receipt.json").write_text(json.dumps({
        "persona_id": slug, "status": status, "reason": "test fixture",
        "indexer_exit_code": 4, "timestamp": "2026-07-14T00:00:00",
    }))


class TestIndexVerifyPureFunction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name) / "workspace"
        (self.workspace / "personas").mkdir(parents=True)
        self.db_path = Path(self.tmp.name) / "gemini-index.sqlite"

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_indexed_passes(self):
        _make_embeddings_db(self.db_path, ["author-a", "author-b"])
        ok, missing, counts = pf.index_verify(
            self.workspace, self.db_path, ["author-a", "author-b"])
        self.assertTrue(ok)
        self.assertEqual(missing, [])
        self.assertEqual(counts["indexed_count"], 2)

    def test_deferred_receipt_covers_unindexed_persona(self):
        _make_embeddings_db(self.db_path, ["author-a"])
        _write_deferred_receipt(self.workspace, "author-b")
        ok, missing, counts = pf.index_verify(
            self.workspace, self.db_path, ["author-a", "author-b"])
        self.assertTrue(ok, f"deferred receipt must cover the gap; missing={missing}")
        self.assertEqual(counts["deferred_count"], 1)

    def test_unexplained_gap_fails(self):
        _make_embeddings_db(self.db_path, ["author-a"])
        # author-b: no index row, no receipt at all.
        ok, missing, counts = pf.index_verify(
            self.workspace, self.db_path, ["author-a", "author-b"])
        self.assertFalse(ok)
        self.assertEqual(missing, ["author-b"])

    def test_non_deferred_receipt_status_does_not_excuse(self):
        _make_embeddings_db(self.db_path, ["author-a"])
        _write_deferred_receipt(self.workspace, "author-b", status="indexed")
        ok, missing, counts = pf.index_verify(
            self.workspace, self.db_path, ["author-a", "author-b"])
        self.assertFalse(ok, "a receipt whose status != 'deferred' must NOT excuse a gap")
        self.assertEqual(missing, ["author-b"])

    def test_missing_db_treats_all_as_unindexed(self):
        # DB genuinely absent (never indexed anything on this box) — not an
        # error; every slug must then be covered by a deferred receipt.
        _write_deferred_receipt(self.workspace, "author-a")
        ok, missing, _ = pf.index_verify(self.workspace, self.db_path, ["author-a"])
        self.assertTrue(ok)


class TestIndexVerifyCLI(unittest.TestCase):
    """Exercises the actual `persona_fleet.py index-verify` CLI subprocess —
    exactly how publish-personas-to-fleet.sh invokes it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name) / "workspace"
        (self.workspace / "personas").mkdir(parents=True)
        self.db_path = Path(self.tmp.name) / "gemini-index.sqlite"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, slugs_csv: str):
        return subprocess.run(
            [sys.executable, str(_PF), "index-verify",
             "--workspace", str(self.workspace),
             "--db", str(self.db_path),
             "--slugs", slugs_csv],
            capture_output=True, text=True, check=False)

    def test_cli_exits_0_when_all_accounted(self):
        _make_embeddings_db(self.db_path, ["author-a"])
        proc = self._run("author-a")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_cli_exits_7_on_unexplained_gap(self):
        _make_embeddings_db(self.db_path, ["author-a"])
        proc = self._run("author-a,author-b")
        self.assertEqual(proc.returncode, 7, proc.stderr)
        self.assertIn("author-b", proc.stderr)
        self.assertIn("index-verify FAILED", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
