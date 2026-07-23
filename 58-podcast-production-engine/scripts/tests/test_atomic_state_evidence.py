#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: atomic state+evidence writes (U043)
# -----------------------------------------------------------------------------
# Stdlib unittest only. No network, no live DB. Proves:
#   1. _atomic_write uses temp-file + fsync + rename (data durable before the
#      directory entry is updated).
#   2. A crash/failure between the temp write and the rename leaves the
#      original file unchanged (no partial write, no torn file).
#   3. The ledger sync happens INSIDE the SQLite transaction: a broken ledger
#      linkage rolls back the state transition (roster never advances without
#      ledger evidence).
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_atomic_state_evidence.py
# =============================================================================
"""Deterministic tests for atomic state+evidence writes (U043)."""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "podcast_state.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("podcast_state", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PS = _load_module()


class TestAtomicWrite(unittest.TestCase):
    """_atomic_write must be temp-file + fsync + rename, never a partial write."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name

    def test_write_creates_file_with_exact_content(self):
        path = os.path.join(self.dir, "out.json")
        PS._atomic_write(path, '{"state": "received"}')
        with open(path, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), '{"state": "received"}')

    def test_write_overwrites_existing_file_atomically(self):
        path = os.path.join(self.dir, "out.json")
        PS._atomic_write(path, "original")
        PS._atomic_write(path, "updated")
        with open(path, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "updated")

    def test_fsync_called_before_rename(self):
        """The temp file must be fsynced before os.replace moves it into place.

        We patch os.fsync and os.replace to record call order. If rename ran
        before fsync, a crash could expose a zero-length / partial file at the
        final path."""
        path = os.path.join(self.dir, "out.json")
        order: list[str] = []

        real_fsync = os.fsync
        real_replace = os.replace

        def spy_fsync(fd):
            order.append("fsync")
            return real_fsync(fd)

        def spy_replace(src, dst):
            order.append("replace")
            return real_replace(src, dst)

        with mock.patch("os.fsync", side_effect=spy_fsync), \
             mock.patch("os.replace", side_effect=spy_replace):
            PS._atomic_write(path, "durable-content")

        self.assertIn("fsync", order, "os.fsync was never called")
        self.assertIn("replace", order, "os.replace was never called")
        self.assertLess(
            order.index("fsync"), order.index("replace"),
            f"fsync must precede rename; got order {order}",
        )

    def test_failure_before_rename_leaves_original_unchanged(self):
        """Simulate a crash after the temp write but before the rename: the
        original file must be byte-for-byte unchanged, and no temp file may
        leak at the final path."""
        path = os.path.join(self.dir, "out.json")
        PS._atomic_write(path, "original-content")

        real_replace = os.replace

        def exploding_replace(src, dst):
            # Simulate a crash / power loss right before the rename lands.
            raise OSError("simulated crash before rename")

        with mock.patch("os.replace", side_effect=exploding_replace):
            with self.assertRaises(OSError):
                PS._atomic_write(path, "new-content-that-should-not-land")

        # The original file is untouched.
        with open(path, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "original-content")

        # No torn temp file left at the final path.
        self.assertFalse(
            os.path.exists(path + ".tmp"),
            "a temp file must not survive at the final path",
        )
        # Restore is implicit (mock context), but keep real_replace referenced.
        self.assertIsNotNone(real_replace)

    def test_no_temp_files_leak_on_success(self):
        path = os.path.join(self.dir, "out.json")
        PS._atomic_write(path, "content")
        leftovers = [f for f in os.listdir(self.dir) if ".tmp." in f]
        self.assertEqual(leftovers, [], f"temp files leaked: {leftovers}")


class TestLedgerSyncInsideTransaction(unittest.TestCase):
    """A broken ledger linkage must roll back the state transition (U043).

    The roster (SQLite) must never advance without the ledger evidence landing
    in the same atomic unit of work."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.conn = PS.connect(self.db_path)
        self.addCleanup(self.conn.close)
        # Seed an active client + a job in 'received'.
        self.conn.execute(
            "INSERT INTO podcast_client_state (client_id, active) VALUES ('c1', 1)"
        )
        self.conn.execute(
            "INSERT INTO podcast_jobs "
            "(job_id, client_id, location_id, contact_id, submission_fingerprint, "
            " mode, style, status) "
            "VALUES ('pj_test', 'c1', 'loc', 'contact', 'fp', "
            " 'interview_style_podcast', 'vulnerable', 'received')"
        )

    def _args(self, **kw):
        base = dict(job_id="pj_test", json=True, db_path=self.db_path)
        base.update(kw)
        return type("Args", (), base)()

    def test_broken_ledger_rolls_back_advance(self):
        """If _sync_ledger returns 'broken', the advance must ROLLBACK: the job
        stays in 'received' and no transition event is persisted."""
        args = self._args(to="researching", note="go", cost_delta=0.0,
                          force_waiver=None)
        with mock.patch.object(PS, "_sync_ledger", return_value="broken"):
            with self.assertRaises(PS.LedgerLinkageError):
                PS.cmd_advance(self.conn, args)

        row = self.conn.execute(
            "SELECT status FROM podcast_jobs WHERE job_id = 'pj_test'"
        ).fetchone()
        self.assertEqual(
            row["status"], "received",
            "a broken ledger sync must roll back the state transition",
        )
        # No transition event may have been persisted.
        ev = self.conn.execute(
            "SELECT COUNT(*) AS n FROM podcast_job_events "
            "WHERE job_id = 'pj_test' AND to_status = 'researching'"
        ).fetchone()
        self.assertEqual(ev["n"], 0, "no event may survive a rolled-back advance")

    def test_synced_ledger_commits_advance(self):
        """A healthy ledger sync lets the advance commit normally."""
        args = self._args(to="researching", note="go", cost_delta=0.0,
                          force_waiver=None)
        with mock.patch.object(PS, "_sync_ledger", return_value="synced"):
            PS.cmd_advance(self.conn, args)

        row = self.conn.execute(
            "SELECT status FROM podcast_jobs WHERE job_id = 'pj_test'"
        ).fetchone()
        self.assertEqual(row["status"], "researching")

    def test_not_configured_ledger_still_commits(self):
        """A job with no ledger (never came through the webhook layer) is a
        legitimate no-op and must still advance."""
        args = self._args(to="researching", note="go", cost_delta=0.0,
                          force_waiver=None)
        with mock.patch.object(PS, "_sync_ledger", return_value="not_configured"):
            PS.cmd_advance(self.conn, args)

        row = self.conn.execute(
            "SELECT status FROM podcast_jobs WHERE job_id = 'pj_test'"
        ).fetchone()
        self.assertEqual(row["status"], "researching")

    def test_broken_ledger_rolls_back_fail(self):
        """The fail path is also atomic: a broken ledger leaves the job unfailed."""
        args = self._args(step="publish", error="boom")
        with mock.patch.object(PS, "_sync_ledger", return_value="broken"):
            with self.assertRaises(PS.LedgerLinkageError):
                PS.cmd_fail(self.conn, args)

        row = self.conn.execute(
            "SELECT status FROM podcast_jobs WHERE job_id = 'pj_test'"
        ).fetchone()
        self.assertEqual(row["status"], "received")


if __name__ == "__main__":
    unittest.main(verbosity=2)
