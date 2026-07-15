#!/usr/bin/env python3
"""
tests/unit/persona-embedding-drift-probe.test.py
─────────────────────────────────────────────────────────────────────────────
A-U8 (Skill 6 v2, book-to-persona embeddings wiring) acceptance (d):
"the drift check flags a seeded disk-vs-index divergence as exactly one
operator card."

Proves shared-utils/persona_embedding_drift_probe.py::run_drift_check():

  1. A seeded disk-vs-index divergence (persona on disk, unindexed, no
     receipt) produces exactly ONE result dict with verdict='degraded' —
     never a flood of per-persona records — and exit code 1.
  2. A persona covered by an honest deferred receipt is NOT drift.
  3. A fully-accounted-for disk set is verdict='healthy', exit code 0.
  4. A missing personas dir is verdict='n/a', exit code 2 (not yet
     provisioned — not an error).
  5. The CLI is offline/hermetic — no network, no key needed.
  6. shared-utils/fleet_refresh_runner.py::step_persona_embedding_drift()
     wires the probe in as a NON-GATING advisory (never contains the
     substring "failed" in res.steps, even on a degraded verdict).

Run:
    python3 tests/unit/persona-embedding-drift-probe.test.py
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
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
_PROBE = _SHARED_UTILS / "persona_embedding_drift_probe.py"
assert _PROBE.is_file()

sys.path.insert(0, str(_SHARED_UTILS))
_spec = importlib.util.spec_from_file_location("persona_embedding_drift_probe", _PROBE)
probe = importlib.util.module_from_spec(_spec)
sys.modules["persona_embedding_drift_probe"] = probe
_spec.loader.exec_module(probe)


def _mk_persona(personas_dir: Path, slug: str) -> None:
    d = personas_dir / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "persona-blueprint.md").write_text(f"# {slug}\n\nBody.\n")


def _mk_deferred_receipt(personas_dir: Path, slug: str) -> None:
    (personas_dir / slug / "embedding-receipt.json").write_text(json.dumps({
        "persona_id": slug, "status": "deferred",
        "reason": "embedding: deferred (no key / key invalid)",
        "indexer_exit_code": 4, "timestamp": "2026-07-14T00:00:00",
    }))


def _mk_index_db(db_path: Path, indexed_slugs: list) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE embeddings (id TEXT PRIMARY KEY, file_path TEXT,
        chunk_index INTEGER, content TEXT, vector BLOB, last_updated REAL,
        provider TEXT, model TEXT, dim INTEGER)""")
    for i, slug in enumerate(indexed_slugs):
        conn.execute(
            "INSERT INTO embeddings VALUES (?,?,?,?,?,?,?,?,?)",
            (f"row{i}",
             f"/box/workspace/data/coaching-personas/personas/{slug}/persona-blueprint.md",
             0, "content", b"\x00" * 12288, 0.0, "gemini", "gemini-embedding-2", 3072))
    conn.commit()
    conn.close()


class TestRunDriftCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.personas_dir = self.base / "personas"
        self.personas_dir.mkdir()
        self.db_path = self.base / "gemini-index.sqlite"

    def tearDown(self):
        self.tmp.cleanup()

    def test_seeded_divergence_is_exactly_one_degraded_card(self):
        _mk_persona(self.personas_dir, "author-a")
        _mk_persona(self.personas_dir, "author-b")
        _mk_persona(self.personas_dir, "author-c")
        _mk_index_db(self.db_path, ["author-a"])
        # author-b and author-c: on disk, neither indexed nor deferred.
        result = probe.run_drift_check(personas_dir=self.personas_dir, db_path=self.db_path)
        # EXACTLY ONE result object (not a list) — this IS the "one card" proof.
        self.assertIsInstance(result, dict)
        self.assertEqual(result["verdict"], "degraded")
        self.assertEqual(result["missing_count"], 2)
        self.assertIn("author-b", result["missing_personas"])
        self.assertIn("author-c", result["missing_personas"])
        self.assertEqual(result["disk_count"], 3)
        self.assertEqual(result["indexed_count"], 1)

    def test_deferred_receipt_is_not_drift(self):
        _mk_persona(self.personas_dir, "author-a")
        _mk_deferred_receipt(self.personas_dir, "author-a")
        result = probe.run_drift_check(personas_dir=self.personas_dir, db_path=self.db_path)
        self.assertEqual(result["verdict"], "healthy")
        self.assertEqual(result["deferred_count"], 1)
        self.assertEqual(result["missing_count"], 0)

    def test_fully_accounted_is_healthy(self):
        _mk_persona(self.personas_dir, "author-a")
        _mk_index_db(self.db_path, ["author-a"])
        result = probe.run_drift_check(personas_dir=self.personas_dir, db_path=self.db_path)
        self.assertEqual(result["verdict"], "healthy")
        self.assertEqual(result["missing_count"], 0)

    def test_missing_personas_dir_is_na(self):
        result = probe.run_drift_check(
            personas_dir=self.base / "does-not-exist", db_path=self.db_path)
        self.assertEqual(result["verdict"], "n/a")

    def test_operator_side_only_flag_present(self):
        result = probe.run_drift_check(personas_dir=self.personas_dir, db_path=self.db_path)
        self.assertTrue(result["operator_side_only"])


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.personas_dir = self.base / "personas"
        self.personas_dir.mkdir()
        self.db_path = self.base / "gemini-index.sqlite"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self):
        return subprocess.run(
            [sys.executable, str(_PROBE),
             "--personas-dir", str(self.personas_dir),
             "--db", str(self.db_path), "--json"],
            capture_output=True, text=True, check=False)

    def test_cli_exit_0_on_healthy(self):
        _mk_persona(self.personas_dir, "author-a")
        _mk_index_db(self.db_path, ["author-a"])
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["verdict"], "healthy")

    def test_cli_exit_1_on_degraded_exactly_one_json_object(self):
        _mk_persona(self.personas_dir, "author-a")
        proc = self._run()
        self.assertEqual(proc.returncode, 1, proc.stderr)
        data = json.loads(proc.stdout)  # a single JSON object, not an array
        self.assertIsInstance(data, dict)
        self.assertEqual(data["verdict"], "degraded")

    def test_cli_exit_2_on_not_provisioned(self):
        proc = subprocess.run(
            [sys.executable, str(_PROBE),
             "--personas-dir", str(self.base / "nope"),
             "--db", str(self.db_path), "--json"],
            capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 2, proc.stderr)


class TestFleetRefreshRunnerWiring(unittest.TestCase):
    """Proves the 'scheduled ... on the operator's own box' half of A-U8:
    fleet_refresh_runner.py::step_persona_embedding_drift() calls the probe
    and records a NON-GATING advisory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        workspace = self.base / "workspace"
        (workspace / "data" / "coaching-personas" / "personas").mkdir(parents=True)
        self.workspace = workspace

        _runner_spec = importlib.util.spec_from_file_location(
            "fleet_refresh_runner", _SHARED_UTILS / "fleet_refresh_runner.py")
        self.runner = importlib.util.module_from_spec(_runner_spec)
        sys.modules["fleet_refresh_runner"] = self.runner
        _runner_spec.loader.exec_module(self.runner)

    def tearDown(self):
        self.tmp.cleanup()

    def test_step_records_degraded_advisory_never_containing_failed(self):
        personas_dir = self.workspace / "data" / "coaching-personas" / "personas"
        _mk_persona(personas_dir, "author-a")  # unindexed, unreceipted -> degraded

        res = self.runner.BoxResult(box="test-box", dry_run=False)
        paths = {"workspace": self.workspace}
        result = self.runner.step_persona_embedding_drift(paths, _SHARED_UTILS, res)

        self.assertEqual(result["verdict"], "degraded")
        self.assertIn("persona-embedding-drift", res.steps)
        recorded = res.steps["persona-embedding-drift"]
        self.assertTrue(recorded.startswith("degraded:"))
        self.assertNotIn("failed", recorded,
                         "the advisory must NEVER contain 'failed' — it must "
                         "not trip fleet_refresh_runner's has_failures check")

    def test_step_records_pass_on_healthy(self):
        personas_dir = self.workspace / "data" / "coaching-personas" / "personas"
        _mk_persona(personas_dir, "author-a")
        _mk_deferred_receipt(personas_dir, "author-a")

        res = self.runner.BoxResult(box="test-box", dry_run=False)
        paths = {"workspace": self.workspace}
        self.runner.step_persona_embedding_drift(paths, _SHARED_UTILS, res)
        self.assertEqual(res.steps["persona-embedding-drift"], "pass")


if __name__ == "__main__":
    unittest.main(verbosity=2)
