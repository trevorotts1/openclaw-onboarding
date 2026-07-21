#!/usr/bin/env python3
"""Regression suite for the podcast state machine's ledger linkage (T0-22).

The intake ledger is the atomic-claim mechanism; SQLite is the queryable source
of truth. `_resolve_ledger_file` returned None for BOTH "this job has no ledger"
and "this job's linkage is broken", `_sync_ledger` returned immediately on either,
and `cmd_advance` never looked at the outcome. So a missing, malformed or
unreadable job index produced no ledger update, no warning, and an advance that
reported success while the claim record was left behind.

These tests prove all three states, in both directions:

  * NOT CONFIGURED — no job index at all: a legitimate no-op, advance succeeds;
  * SYNCED — a healthy linkage: the ledger record is actually rewritten and the
    advance succeeds;
  * BROKEN — an index that exists but is malformed / carries no job_key / points
    at an unwritable ledger: a warning on stderr AND a non-zero advance.

Run:
    python3 tests/unit/podcast-state-ledger-linkage.test.py
    or: pytest tests/unit/podcast-state-ledger-linkage.test.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_STATE_PY = _REPO_ROOT / "58-podcast-production-engine" / "scripts" / "podcast_state.py"
assert _STATE_PY.is_file(), f"podcast_state.py not found at {_STATE_PY}"


def _load_module():
    spec = importlib.util.spec_from_file_location("podcast_state", _STATE_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["podcast_state"] = mod
    spec.loader.exec_module(mod)
    return mod


ps = _load_module()


class _Env:
    """Point the module's job-index and ledger directories at a scratch tree."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.index_dir = self.root / "jobindex"
        self.ledger_dir = self.root / "ledger"
        self.index_dir.mkdir(parents=True)
        self.ledger_dir.mkdir(parents=True)
        self._saved = {}

    def __enter__(self):
        # PODCAST_JOBINDEX_DIR / PODCAST_LEDGER_DIR are the same overrides a real
        # box uses (podcast_state.py:79-89), not a test-only seam.
        for var, val in (("PODCAST_JOBINDEX_DIR", str(self.index_dir)),
                         ("PODCAST_LEDGER_DIR", str(self.ledger_dir))):
            self._saved[var] = os.environ.get(var)
            os.environ[var] = val
        return self

    def __exit__(self, *exc):
        for var, val in self._saved.items():
            if val is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = val
        self.tmp.cleanup()
        return False

    def write_index(self, job_id: str, text: str):
        # The index file the module writes is "<job_id>.jobkey"
        # (podcast_state.py:710-711), not ".json".
        (self.index_dir / f"{job_id}.jobkey").write_text(text, encoding="utf-8")

    def write_ledger(self, job_key: str, record: dict):
        (self.ledger_dir / f"{job_key}.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8"
        )


class TestLedgerLinkageStates(unittest.TestCase):
    def test_no_index_is_not_configured_and_is_silent(self):
        with _Env():
            self.assertEqual(ps._sync_ledger("job-none", "rendering", "none"),
                             "not_configured")

    def test_healthy_linkage_syncs_and_actually_rewrites_the_record(self):
        with _Env() as env:
            env.write_index("job-ok", json.dumps(
                {"job_key": "key-ok", "ledger_dir": str(env.ledger_dir)}))
            env.write_ledger("key-ok", {"state": "claimed", "owner": "webhook-layer"})
            self.assertEqual(ps._sync_ledger("job-ok", "complete", "none"), "synced")
            record = json.loads((env.ledger_dir / "key-ok.json").read_text(encoding="utf-8"))
        self.assertEqual(record["sqlite_job_id"], "job-ok")
        self.assertNotEqual(record["state"], "claimed", "the ledger state was not mirrored")
        self.assertEqual(record["owner"], "webhook-layer",
                         "read-modify-write dropped a field the webhook layer owns")

    def test_malformed_index_is_broken_not_silent(self):
        with _Env() as env:
            env.write_index("job-bad", "{not json at all")
            self.assertEqual(ps._sync_ledger("job-bad", "rendering", "none"), "broken")

    def test_index_without_a_job_key_is_broken(self):
        with _Env() as env:
            env.write_index("job-nokey", json.dumps({"ledger_dir": str(env.ledger_dir)}))
            self.assertEqual(ps._sync_ledger("job-nokey", "rendering", "none"), "broken")

    def test_index_that_is_not_an_object_is_broken(self):
        with _Env() as env:
            env.write_index("job-list", json.dumps(["not", "an", "object"]))
            self.assertEqual(ps._sync_ledger("job-list", "rendering", "none"), "broken")

    def test_unwritable_ledger_destination_is_broken(self):
        with _Env() as env:
            locked = env.root / "locked"
            locked.mkdir()
            env.write_index("job-locked", json.dumps(
                {"job_key": "key-locked", "ledger_dir": str(locked)}))
            os.chmod(locked, 0o500)
            try:
                self.assertEqual(ps._sync_ledger("job-locked", "rendering", "none"),
                                 "broken")
            finally:
                os.chmod(locked, 0o700)

    def test_resolve_raises_a_typed_error_on_a_broken_linkage(self):
        with _Env() as env:
            env.write_index("job-typed", "{not json at all")
            with self.assertRaises(ps.LedgerLinkageError):
                ps._resolve_ledger_file("job-typed")

    def test_resolve_returns_none_when_nothing_is_configured(self):
        with _Env():
            self.assertIsNone(ps._resolve_ledger_file("job-absent"))


class TestBrokenLinkageIsNotACleanAdvance(unittest.TestCase):
    """End to end through the real CLI: an advance whose claim record could not
    be reconciled must not be reported as a clean advance."""

    def _cli(self, env, db, *argv):
        e = dict(os.environ)
        e["PODCAST_JOBINDEX_DIR"] = str(env.index_dir)
        e["PODCAST_LEDGER_DIR"] = str(env.ledger_dir)
        return subprocess.run(
            [sys.executable, str(_STATE_PY), "--db-path", str(db), "--json", *argv],
            capture_output=True, text=True, timeout=120, env=e,
        )

    def _seed_job(self, env, db):
        payload = env.root / "payload.json"
        payload.write_text(json.dumps({"q1_answer": "a", "q2_answer": "b"}), encoding="utf-8")
        proc = self._cli(
            env, db, "create",
            "--client-id", "client-slug", "--location-id", "loc-slug",
            "--contact-id", "contact-slug", "--mode", "personal_podcast_style",
            "--style", "vulnerable", "--payload-file", str(payload),
            "--job-key", "key-e2e", "--ledger-dir", str(env.ledger_dir),
        )
        self.assertEqual(proc.returncode, 0, f"create failed: {proc.stderr}")
        return json.loads(proc.stdout)["job_id"]

    def test_a_healthy_advance_still_succeeds_and_reports_synced(self):
        with _Env() as env:
            db = env.root / "state.sqlite"
            job_id = self._seed_job(env, db)
            proc = self._cli(env, db, "advance", "--job-id", job_id,
                             "--to", "researching", "--force-waiver", "test")
        self.assertEqual(proc.returncode, 0, f"a healthy advance failed: {proc.stderr}")
        out = json.loads(proc.stdout)
        self.assertEqual(out["to"], "researching")
        self.assertEqual(out["ledger_sync"], "synced",
                         "a healthy linkage did not report synced")

    def test_a_broken_linkage_makes_the_advance_non_successful(self):
        with _Env() as env:
            db = env.root / "state.sqlite"
            job_id = self._seed_job(env, db)
            # Break the linkage the way a real box would: the index survives but
            # its contents no longer parse.
            env.write_index(job_id, "{not json at all")
            proc = self._cli(env, db, "advance", "--job-id", job_id,
                             "--to", "researching", "--force-waiver", "test")
        self.assertNotEqual(proc.returncode, 0,
                            "a broken ledger linkage still reported a clean advance")
        self.assertIn("ledger linkage broken", proc.stderr,
                      "the documented warning was not emitted")
        out = json.loads(proc.stdout)
        self.assertEqual(out["ledger_sync"], "broken",
                         "the emitted record did not say the ledger sync was broken")
        self.assertEqual(out["to"], "researching",
                         "the record must still report the transition that WAS committed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
