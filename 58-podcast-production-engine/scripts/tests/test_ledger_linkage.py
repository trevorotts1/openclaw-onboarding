#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: ledger-linkage advance guard (U030)
# -----------------------------------------------------------------------------
# Stdlib unittest only. No network, no live DB: a throwaway file DB for the CLI
# end-to-end and env-pinned jobindex/ledger dirs for the unit tests. Proves the
# T0-22 fix: a job index that EXISTS but is malformed, unreadable, or missing
# its job_key is a BROKEN LINKAGE — loud (stderr warning) and advance-fatal
# (non-zero exit) — while a job with NO index is "not configured" and advances
# normally. Before the fix both cases returned None, emitted nothing, and the
# advance reported success while the intake ledger (the atomic-claim mechanism)
# was never updated.
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_ledger_linkage.py
# =============================================================================
"""Deterministic tests for the ledger-linkage advance guard (U030 / T0-22)."""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
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


class LedgerLinkageUnitTests(unittest.TestCase):
    """_sync_ledger / _resolve_ledger_file with env-pinned jobindex + ledger dirs."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="podcast-u030-")
        self.jobindex = os.path.join(self.tmp, "jobindex")
        self.ledger = os.path.join(self.tmp, "ledger")
        os.makedirs(self.jobindex, mode=0o700)
        os.makedirs(self.ledger, mode=0o700)
        self._env = mock.patch.dict(os.environ, {
            "PODCAST_JOBINDEX_DIR": self.jobindex,
            "PODCAST_LEDGER_DIR": self.ledger,
        })
        self._env.start()
        self.addCleanup(self._env.stop)

    def _write_jobindex(self, job_id, content):
        path = os.path.join(self.jobindex, job_id + ".jobkey")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    # -- AC2: a malformed job index is LOUD, not silent ---------------------
    def test_malformed_job_index_returns_broken_with_warning(self):
        self._write_jobindex("j1", "{not valid json")
        with mock.patch("sys.stderr") as err:
            result = PS._sync_ledger("j1", "writing", "none")
        self.assertEqual(result, "broken")
        warning = "".join(c.args[0] for c in err.write.call_args_list)
        self.assertIn("ledger linkage broken", warning)
        self.assertIn("j1", warning)

    def test_job_index_without_job_key_returns_broken_with_warning(self):
        self._write_jobindex("j2", json.dumps({"ledger_dir": self.ledger}))
        with mock.patch("sys.stderr") as err:
            result = PS._sync_ledger("j2", "writing", "none")
        self.assertEqual(result, "broken")
        warning = "".join(c.args[0] for c in err.write.call_args_list)
        self.assertIn("no job_key", warning)

    def test_unreadable_job_index_returns_broken_with_warning(self):
        # A directory at the jobindex path: exists, but cannot be read as a file.
        os.makedirs(os.path.join(self.jobindex, "j3.jobkey"))
        with mock.patch("sys.stderr") as err:
            result = PS._sync_ledger("j3", "writing", "none")
        self.assertEqual(result, "broken")
        warning = "".join(c.args[0] for c in err.write.call_args_list)
        self.assertIn("could not be read or parsed", warning)

    # -- AC4: not-configured is NOT broken ----------------------------------
    def test_missing_job_index_is_not_configured_and_silent(self):
        with mock.patch("sys.stderr") as err:
            result = PS._sync_ledger("never-intaken", "writing", "none")
        self.assertEqual(result, "not_configured")
        self.assertEqual(err.write.call_args_list, [])

    # -- a healthy linkage still syncs --------------------------------------
    def test_valid_linkage_syncs_the_ledger_record(self):
        self._write_jobindex("j4", json.dumps({"job_key": "k4", "ledger_dir": self.ledger}))
        result = PS._sync_ledger("j4", "writing", "none")
        self.assertEqual(result, "synced")
        with open(os.path.join(self.ledger, "k4.json"), encoding="utf-8") as fh:
            record = json.load(fh)
        self.assertEqual(record["sqlite_job_id"], "j4")


class LedgerLinkageCliEndToEnd(unittest.TestCase):
    """AC3 + AC4 through the real CLI: advance must be non-successful on a
    broken linkage and successful when no ledger is configured."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="podcast-u030-cli-")
        self.db = os.path.join(self.tmp, "state.db")
        self.payload = os.path.join(self.tmp, "payload.json")
        with open(self.payload, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"preset": "interview"}))
        self.env = dict(os.environ)
        self.env["PODCAST_DB_PATH"] = self.db
        self.env["PODCAST_JOBINDEX_DIR"] = os.path.join(self.tmp, "jobindex")
        self.env["PODCAST_LEDGER_DIR"] = os.path.join(self.tmp, "ledger")

    def _ps(self, *args):
        return subprocess.run([sys.executable, str(_SCRIPT), *args],
                              capture_output=True, text=True, timeout=30, env=self.env)

    def _create(self, job_key=None):
        argv = ["create", "--client-id", "c", "--location-id", "l", "--contact-id", "ct",
                "--mode", "interview_style_podcast", "--style", "vulnerable",
                "--payload-file", self.payload]
        if job_key:
            argv += ["--job-key", job_key]
        created = self._ps(*argv)
        self.assertEqual(created.returncode, 0, created.stderr)
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute("SELECT job_id FROM podcast_jobs").fetchone()[0]
        finally:
            conn.close()

    def test_advance_fails_loud_on_broken_linkage(self):
        jid = self._create(job_key="k-broken")
        # Corrupt the job index the intake layer wrote: the linkage now exists
        # but cannot be resolved.
        idx = os.path.join(self.env["PODCAST_JOBINDEX_DIR"], jid + ".jobkey")
        with open(idx, "w", encoding="utf-8") as fh:
            fh.write("{corrupt")

        adv = self._ps("advance", "--job-id", jid, "--to", "researching")
        # AC3: the advance is NON-successful (LedgerLinkageError -> exit 1).
        self.assertEqual(adv.returncode, 1, adv.stdout + adv.stderr)
        self.assertIn("ledger", adv.stderr.lower())
        # The honest report: the SQLite transition committed, the advance did not.
        self.assertIn("ledger_sync=broken", adv.stdout)
        status = sqlite3.connect(self.db).execute(
            "SELECT status FROM podcast_jobs WHERE job_id = ?", (jid,)).fetchone()[0]
        self.assertEqual(status, "researching")  # committed, reported honestly

    def test_advance_succeeds_when_no_ledger_configured(self):
        # No --job-key: the job never came through the webhook intake layer, so
        # there is no job index and nothing to sync. AC4: not-configured is not
        # broken — the advance succeeds.
        jid = self._create()
        adv = self._ps("advance", "--job-id", jid, "--to", "researching")
        self.assertEqual(adv.returncode, 0, adv.stderr)
        self.assertIn("ledger_sync=not_configured", adv.stdout)

    def test_advance_succeeds_on_healthy_linkage(self):
        jid = self._create(job_key="k-healthy")
        adv = self._ps("advance", "--job-id", jid, "--to", "researching")
        self.assertEqual(adv.returncode, 0, adv.stderr)
        self.assertIn("ledger_sync=synced", adv.stdout)
        with open(os.path.join(self.env["PODCAST_LEDGER_DIR"], "k-healthy.json"),
                  encoding="utf-8") as fh:
            record = json.load(fh)
        self.assertEqual(record["sqlite_job_id"], jid)


if __name__ == "__main__":
    unittest.main()
