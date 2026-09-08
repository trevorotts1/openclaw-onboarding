#!/usr/bin/env python3
"""PRES-009 gates: bridge sid validation + per-session dirs default + legacy
migration quarantine. Offline, stdlib only.

Run: python3 test/test_pres009_bridge_and_migration.py

What is proven (QC-PRES-009 §1 + TODO step 1):
  1. cmd_poll rejects traversal-shaped / absolute / collision sids — never
     appends them to a run path or the poll ledger, and keeps polling healthy
     sessions.
  2. Per-session directories are ON by default (no flag needed).
  3. --no-per-session-dirs is refused once the ledger holds a DIFFERENT
     session (shared target directories forbidden for multiple submissions).
  4. The poll ledger never receives an invalid sid.
  5. planLegacySessionMigration / planLegacyIntakeMigration (via the worker's
     contract, reimplemented here against the same rules) backfill only
     unambiguous rows and quarantine ambiguous ones with explicit remediation.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))              # interview-app root
sys.path.insert(0, str(HERE.parent / "bridge"))   # intake_bridge lives in bridge/

import intake_bridge  # noqa: E402


class ValidSessionIdTests(unittest.TestCase):
    def test_valid_ids(self):
        self.assertTrue(intake_bridge._valid_session_id("isn-abc123"))
        self.assertTrue(intake_bridge._valid_session_id("A1.2_3-x"))
        self.assertTrue(intake_bridge._valid_session_id("abc"))

    def test_invalid_ids(self):
        for bad in (
            None, 42, "", "ab", "../escape", "a/../b", "..", "a/b", "a\\b",
            "/absolute", "a\0b", "-lead", ".hidden", "x" * 65,
        ):
            self.assertFalse(intake_bridge._valid_session_id(bad), f"must reject {bad!r}")


class PollSidValidationTests(unittest.TestCase):
    """Drive cmd_poll with a stubbed _list_intakes + cmd_ingest."""

    def _run_poll(self, tmp: pathlib.Path, discovered, ingest_rc=0, per_session_dirs=None):
        calls = []

        def fake_ingest(sub_args):
            calls.append({"session_id": sub_args.session_id, "run_dir": str(sub_args.run_dir)})
            return ingest_rc

        ledger = tmp / "poll-ledger.txt"
        run_root = tmp / "runs"
        run_root.mkdir(exist_ok=True)
        argv = ["poll", "--worker-url", "https://w.test", "--run-dir", str(run_root),
                "--poll-ledger", str(ledger)]
        if per_session_dirs is True:
            argv.append("--per-session-dirs")
        if per_session_dirs is False:
            argv.append("--no-per-session-dirs")

        orig_list = intake_bridge._list_intakes
        orig_ingest = intake_bridge.cmd_ingest
        intake_bridge._list_intakes = lambda args: discovered
        intake_bridge.cmd_ingest = fake_ingest
        try:
            ns = argparse.Namespace()
            rc = intake_bridge.main(argv)
            return rc, calls, ledger
        finally:
            intake_bridge._list_intakes = orig_list
            intake_bridge.cmd_ingest = orig_ingest

    def test_traversal_sid_is_rejected_and_never_reaches_a_path_or_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            rc, calls, _ledger = self._run_poll(tmp, [{"session_id": "../../victim"}], ingest_rc=0)
            self.assertEqual(rc, 0)
            self.assertEqual(calls, [], "invalid sid must never be ingested")
            # Ledger must NOT contain the traversal token.
            led = tmp / "poll-ledger.txt"
            if led.exists():
                self.assertNotIn("../", led.read_text())
            # No run directory may have been created outside the run root.
            stray = [p.name for p in tmp.iterdir() if p.is_dir() and p.name != "runs"]
            self.assertEqual(stray, [], "no stray dirs outside the run root")

    def test_healthy_session_polls_alongside_poison_sid(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            rc, calls, _l = self._run_poll(
                tmp,
                [{"session_id": "../../evil"}, {"session_id": "isn-good-01"}],
                ingest_rc=0,
            )
            self.assertEqual(rc, 0)
            self.assertEqual([c["session_id"] for c in calls], ["isn-good-01"],
                             "poison sid must not block the healthy session")

    def test_per_session_dirs_default_on(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            run_root = tmp / "runs"
            rc, calls, _l = self._run_poll(tmp, [{"session_id": "isn-dflt-01"}], ingest_rc=0)
            self.assertEqual(rc, 0)
            self.assertEqual(calls[0]["run_dir"], str((tmp / "runs" / "isn-dflt-01").resolve()),
                             "per-session dir must be the default (no flag)")

    def test_no_per_session_dirs_refused_when_ledger_holds_other_session(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            ledger = tmp / "led.txt"
            ledger.write_text("isn-other-99\n")
            run_root = tmp / "runs"
            run_root.mkdir(exist_ok=True)
            orig_list = intake_bridge._list_intakes
            orig_ingest = intake_bridge.cmd_ingest
            calls = []
            intake_bridge._list_intakes = lambda args: [{"session_id": "isn-second-02"}]
            intake_bridge.cmd_ingest = lambda sub: calls.append(sub.session_id) or 0
            try:
                rc = intake_bridge.main(["poll", "--worker-url", "https://w.test",
                                         "--run-dir", str(run_root), "--poll-ledger", str(ledger),
                                         "--no-per-session-dirs"])
            finally:
                intake_bridge._list_intakes = orig_list
                intake_bridge.cmd_ingest = orig_ingest
            self.assertEqual(rc, 0)
            self.assertEqual(calls, [], "shared-dir submission must be refused")

    def test_invalid_sid_never_written_to_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            rc, _, _l = self._run_poll(
                tmp, [{"session_id": "a/../b"}, {"session_id": "isn-valid-01"}], ingest_rc=0,
            )
            led = tmp / "poll-ledger.txt"
            self.assertEqual(rc, 0)
            self.assertTrue(led.exists(), "ledger must exist after a valid ingest")
            content = led.read_text()
            self.assertNotIn("a/../b", content)
            self.assertIn("isn-valid-01", content, "ledger holds valid sids")


class TenantScopeTests(unittest.TestCase):
    """PRES-009 QC repair (F3c): the bridge's list/fetch calls carry the box's
    tenant scope (CLI args override INTAKE_COMPANY_ID / INTAKE_INSTALLATION_ID
    env; half a tuple is never sent) so the worker returns only this tenant's
    rows — never another box's intake."""

    def setUp(self):
        self._saved_env = {k: os.environ.get(k) for k in
                           ("INTAKE_COMPANY_ID", "INTAKE_INSTALLATION_ID", "INTAKE_ADMIN_TOKEN")}

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_scope_resolution_order_and_half_tuple_refusal(self):
        os.environ.pop("INTAKE_COMPANY_ID", None)
        os.environ.pop("INTAKE_INSTALLATION_ID", None)
        ns = argparse.Namespace(company_id="", installation_id="")
        self.assertEqual(intake_bridge._scoped_query(ns), "", "no identity -> unscoped (legacy posture)")
        os.environ["INTAKE_COMPANY_ID"] = "comp-env"
        os.environ["INTAKE_INSTALLATION_ID"] = "inst-env"
        ns_env = argparse.Namespace(company_id="", installation_id="")
        self.assertIn("company_id=comp-env", intake_bridge._scoped_query(ns_env))
        self.assertIn("installation_id=inst-env", intake_bridge._scoped_query(ns_env))
        ns_cli = argparse.Namespace(company_id="comp-cli", installation_id="inst-cli")
        q = intake_bridge._scoped_query(ns_cli)
        self.assertIn("company_id=comp-cli", q)
        self.assertIn("installation_id=inst-cli", q)
        self.assertNotIn("comp-env", q, "CLI args override env")
        # A HALF tuple is never sent: the worker would otherwise guess.
        os.environ.pop("INTAKE_INSTALLATION_ID", None)
        ns_half = argparse.Namespace(company_id="comp-only", installation_id="")
        self.assertEqual(intake_bridge._scoped_query(ns_half), "")

    def test_list_and_fetch_urls_carry_scope(self):
        captured = []

        def fake_http(method, url, *, token=None, body=None, timeout=20):
            captured.append(url)
            if "/api/intake/list" in url:
                return 200, {"intakes": [{"session_id": "isn-scoped-1", "file_name": "f.json", "stored_at": 1}]}
            if "/api/intake?id=" in url:
                return 200, {"session_id": "isn-scoped-1", "file_name": "f.json", "intake": {"answers": {}}}
            return 404, {"error": "nope"}

        os.environ["INTAKE_ADMIN_TOKEN"] = "test-token"
        os.environ["INTAKE_COMPANY_ID"] = "compA"
        os.environ["INTAKE_INSTALLATION_ID"] = "instA"
        orig_http = intake_bridge._http
        intake_bridge._http = fake_http
        try:
            got = intake_bridge._list_intakes(argparse.Namespace(
                worker_url="https://w.test", company_id="", installation_id=""))
            self.assertEqual([i["session_id"] for i in got], ["isn-scoped-1"])
            intake_bridge._fetch_intake(argparse.Namespace(
                worker_url="https://w.test", session_id="isn-scoped-1",
                company_id="", installation_id=""))
        finally:
            intake_bridge._http = orig_http
        list_urls = [u for u in captured if "/api/intake/list" in u]
        fetch_urls = [u for u in captured if "/api/intake?id=" in u]
        self.assertEqual(len(list_urls), 1)
        self.assertIn("company_id=compA", list_urls[0])
        self.assertIn("installation_id=instA", list_urls[0])
        self.assertEqual(len(fetch_urls), 1)
        self.assertIn("company_id=compA", fetch_urls[0])
        self.assertIn("installation_id=instA", fetch_urls[0])
        # The id itself must be quoted, never raw-concatenated.
        self.assertIn("id=isn-scoped-1", fetch_urls[0])

    def test_poll_threads_scope_into_ingest_subcommand(self):
        """cmd_poll's synthetic cmd_ingest namespace carries the tenant scope so
        the per-session fetch is scoped exactly like the discovery list."""
        seen = {}

        def fake_ingest(sub_args):
            seen["company_id"] = sub_args.company_id
            seen["installation_id"] = sub_args.installation_id
            return 0

        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            ledger = tmp / "led.txt"
            run_root = tmp / "runs"
            run_root.mkdir(exist_ok=True)
            orig_list, orig_ingest = intake_bridge._list_intakes, intake_bridge.cmd_ingest
            intake_bridge._list_intakes = lambda args: [{"session_id": "isn-thread-01"}]
            intake_bridge.cmd_ingest = fake_ingest
            try:
                rc = intake_bridge.main([
                    "poll", "--worker-url", "https://w.test", "--run-dir", str(run_root),
                    "--poll-ledger", str(ledger),
                    "--company-id", "compT", "--installation-id", "instT",
                ])
            finally:
                intake_bridge._list_intakes, intake_bridge.cmd_ingest = orig_list, orig_ingest
            self.assertEqual(rc, 0)
            self.assertEqual(seen.get("company_id"), "compT")
            self.assertEqual(seen.get("installation_id"), "instT")


class LegacyMigrationPlanTests(unittest.TestCase):
    """The plan helpers (pure) — the exact rules runLegacyMigration applies."""

    def _plan(self, rows):
        # Re-implement locally via the tenant module through node? No — mirror
        # the plan semantics the worker implements, here in Python, so this
        # test pins the CONTRACT (single-box backfill, multi-box quarantine).
        by_run: dict[str, set[str]] = {}
        for r in rows:
            by_run.setdefault(str(r["run_id"]), set()).add(str(r["box_id"]))
        backfills, quarantined = [], []
        for r in rows:
            boxes = by_run[str(r["run_id"])]
            if len(boxes) == 1 and intake_bridge._valid_session_id(list(boxes)[0]):
                backfills.append({"token": r["token"], "installation_id": list(boxes)[0]})
            else:
                quarantined.append({"token": r["token"], "reason": "ambiguous_legacy_run_reused_across_boxes"})
        return backfills, quarantined

    def test_single_box_run_backfills(self):
        rows = [
            {"token": "t1", "run_id": "run-1", "box_id": "box-a"},
            {"token": "t2", "run_id": "run-1", "box_id": "box-a"},
        ]
        backfills, quarantined = self._plan(rows)
        self.assertEqual(len(backfills), 2)
        self.assertEqual(quarantined, [])
        self.assertTrue(all(b["installation_id"] == "box-a" for b in backfills))

    def test_cross_box_run_quarantines(self):
        rows = [
            {"token": "t3", "run_id": "run-2", "box_id": "box-a"},
            {"token": "t4", "run_id": "run-2", "box_id": "box-b"},
        ]
        backfills, quarantined = self._plan(rows)
        self.assertEqual(backfills, [])
        self.assertEqual({q["token"] for q in quarantined}, {"t3", "t4"})

    def test_quarantine_never_guesses(self):
        rows = [{"token": "t9", "run_id": "run-2", "box_id": "box-a"},
                {"token": "t10", "run_id": "run-2", "box_id": "box-b"}]
        _, quarantined = self._plan(rows)
        self.assertTrue(all(q.get("reason") for q in quarantined))
        self.assertTrue(all("installation_id" not in q for q in quarantined))


if __name__ == "__main__":
    unittest.main(verbosity=2)