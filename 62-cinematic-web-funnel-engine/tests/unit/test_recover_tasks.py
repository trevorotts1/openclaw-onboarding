#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_recover_tasks.py — unit + break-it test suite for build unit U12
(scripts/recover_tasks.py): idempotent task recovery/resume
(AF-CWFE-RESTART-DUPLICATE).

NO NETWORK. Every provider interaction goes through
recover_tasks.FakeRecoveryProvider (spec §19.2 "Kie adapter against mocked
API fixtures" extended to the recovery path) — providers.kie.RequestsTransport
is never instantiated by this suite.

stdlib unittest only. Run with:
  python3 -m unittest discover -s tests/unit -v
     (from the 62-cinematic-web-funnel-engine/ directory)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
_SCRIPTS_DIR = _SKILL_DIR / "scripts"
for p in (_SKILL_DIR, _SCRIPTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import recover_tasks as rt  # noqa: E402
import state_engine as se  # noqa: E402

PY = sys.executable or "python3"
SCRIPT = _SCRIPTS_DIR / "recover_tasks.py"


class RecoverTasksTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cwfe-recover-tasks-tests-"))
        self.state = se.ProjectState(self.tmp)
        self.state.create_project(
            project_id="proj-recover-tests", client_slug="acme", project_slug="launch",
            deliverable_type="cinematic-landing-page", budget_cap_usd=10.0,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _begin(self, scene_label: str):
        return self.state.begin_task(
            provider="kie", model="kie-bytedance-seedance-1.5-pro", operation="generate_video",
            params={"scene": scene_label}, estimated_cost_usd=0.2, seconds=4,
        )


class NoOpTests(RecoverTasksTestCase):
    def test_recover_is_a_clean_noop_with_no_cost_ledger_yet(self) -> None:
        tmp2 = Path(tempfile.mkdtemp(prefix="cwfe-recover-tasks-noledger-"))
        try:
            se.ProjectState(tmp2)  # no create_project() -- cost-ledger.json never created
            passed, detail = rt.recover_and_reconcile(tmp2, provider=rt.FakeRecoveryProvider({}))
            self.assertTrue(passed)
            self.assertIn("nothing to recover", detail)
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    def test_assert_no_duplicate_spend_passes_on_empty_ledger(self) -> None:
        passed, detail = rt.assert_no_duplicate_spend(self.tmp, fail_closed=False)
        self.assertTrue(passed)


class SafeToRequeueTests(RecoverTasksTestCase):
    def test_task_never_submitted_is_reconciled_to_failed(self) -> None:
        entry = self._begin("never-submitted")
        self.state.transition_task(entry["task_id"], "submitted")  # NO provider_task_id
        passed, detail = rt.recover_and_reconcile(self.tmp, provider=rt.FakeRecoveryProvider({}))
        self.assertTrue(passed)
        ledger = self.state.load("cost-ledger")
        reconciled = next(e for e in ledger["entries"] if e["task_id"] == entry["task_id"])
        self.assertEqual(reconciled["status"], "failed")
        self.assertIn("ever reached the provider", reconciled["retry_reason"])

    def test_freed_task_unblocks_a_fresh_retry_for_the_same_request(self) -> None:
        """The exact deadlock AF-CWFE-RESTART-DUPLICATE's recovery step must
        prevent: a request_hash stuck 'queued'/'submitted' forever would
        otherwise permanently block every future begin_task() for it."""
        params = {"scene": "deadlock-check"}
        entry = self.state.begin_task(
            provider="kie", model="kie-bytedance-seedance-1.5-pro", operation="generate_video",
            params=params, estimated_cost_usd=0.2, seconds=4,
        )
        self.state.transition_task(entry["task_id"], "submitted")  # no provider_task_id
        with self.assertRaises(se.IdempotencyViolation):
            self.state.begin_task(
                provider="kie", model="kie-bytedance-seedance-1.5-pro", operation="generate_video",
                params=params, estimated_cost_usd=0.2, seconds=4,
            )
        rt.recover_and_reconcile(self.tmp, provider=rt.FakeRecoveryProvider({}))
        # now that recovery freed it (status -> failed), a fresh begin_task for
        # the SAME params must succeed rather than raising IdempotencyViolation.
        fresh = self.state.begin_task(
            provider="kie", model="kie-bytedance-seedance-1.5-pro", operation="generate_video",
            params=params, estimated_cost_usd=0.2, seconds=4,
        )
        self.assertEqual(fresh["request_hash"], entry["request_hash"])
        self.assertNotEqual(fresh["task_id"], entry["task_id"])


class MustQueryProviderTests(RecoverTasksTestCase):
    def _submit(self, scene_label: str, provider_task_id: str):
        entry = self._begin(scene_label)
        self.state.transition_task(entry["task_id"], "submitted", provider_task_id=provider_task_id)
        self.state.transition_task(entry["task_id"], "in_progress")
        return entry

    def test_provider_success_downloads_and_completes(self) -> None:
        entry = self._submit("will-succeed", "kie-task-success")
        fake = rt.FakeRecoveryProvider({"kie-task-success": "success"})
        passed, detail = rt.recover_and_reconcile(self.tmp, provider=fake)
        self.assertTrue(passed)
        ledger = self.state.load("cost-ledger")
        reconciled = next(e for e in ledger["entries"] if e["task_id"] == entry["task_id"])
        self.assertEqual(reconciled["status"], "complete")
        self.assertEqual(reconciled["actual_cost_usd"], entry["estimated_cost_usd"])
        self.assertEqual(fake.download_calls, ["kie-task-success"])

    def test_provider_failed_transitions_to_failed(self) -> None:
        entry = self._submit("will-fail", "kie-task-failed")
        fake = rt.FakeRecoveryProvider({"kie-task-failed": "failed"})
        rt.recover_and_reconcile(self.tmp, provider=fake)
        ledger = self.state.load("cost-ledger")
        reconciled = next(e for e in ledger["entries"] if e["task_id"] == entry["task_id"])
        self.assertEqual(reconciled["status"], "failed")
        self.assertIn("kie-task-failed", reconciled["retry_reason"])

    def test_provider_cancelled_transitions_to_failed(self) -> None:
        entry = self._submit("was-cancelled", "kie-task-cancelled")
        fake = rt.FakeRecoveryProvider({"kie-task-cancelled": "cancelled"})
        rt.recover_and_reconcile(self.tmp, provider=fake)
        ledger = self.state.load("cost-ledger")
        reconciled = next(e for e in ledger["entries"] if e["task_id"] == entry["task_id"])
        self.assertEqual(reconciled["status"], "failed")

    def test_provider_still_processing_leaves_task_untouched(self) -> None:
        entry = self._submit("still-running", "kie-task-running")
        fake = rt.FakeRecoveryProvider({"kie-task-running": "processing"})
        rt.recover_and_reconcile(self.tmp, provider=fake)
        ledger = self.state.load("cost-ledger")
        reconciled = next(e for e in ledger["entries"] if e["task_id"] == entry["task_id"])
        self.assertEqual(reconciled["status"], "in_progress")

    def test_recovery_never_double_spends_on_repeated_calls(self) -> None:
        """The no-duplicate-spend proof: re-running recovery against an
        already-completed task must never re-download or re-charge it."""
        self._submit("only-once", "kie-task-once")
        fake = rt.FakeRecoveryProvider({"kie-task-once": "success"})
        rt.recover_and_reconcile(self.tmp, provider=fake)
        self.assertEqual(len(fake.download_calls), 1)
        # second pass: nothing left in-progress for this task, must not query/download again.
        fake2 = rt.FakeRecoveryProvider({"kie-task-once": "success"})
        rt.recover_and_reconcile(self.tmp, provider=fake2)
        self.assertEqual(fake2.get_task_calls, [])
        self.assertEqual(fake2.download_calls, [])


class RecoveryLogTests(RecoverTasksTestCase):
    def test_recovery_log_is_written_and_accumulates(self) -> None:
        self._submit_helper()
        log_path = self.tmp / rt.RECOVERY_LOG_FILENAME
        self.assertTrue(log_path.exists())
        first_len = len(json.loads(log_path.read_text(encoding="utf-8")))
        self.assertGreaterEqual(first_len, 1)
        rt.recover_and_reconcile(self.tmp, provider=rt.FakeRecoveryProvider({}))
        second_len = len(json.loads(log_path.read_text(encoding="utf-8")))
        self.assertEqual(second_len, first_len + 1)

    def _submit_helper(self):
        entry = self._begin("logged")
        self.state.transition_task(entry["task_id"], "submitted", provider_task_id="kie-task-logged")
        self.state.transition_task(entry["task_id"], "in_progress")
        rt.recover_and_reconcile(self.tmp, provider=rt.FakeRecoveryProvider({"kie-task-logged": "success"}))


class DuplicateSpendDetectionTests(RecoverTasksTestCase):
    def test_detects_fabricated_duplicate_active_entries(self) -> None:
        entry = self._begin("dup-check")
        self.state.transition_task(entry["task_id"], "submitted", provider_task_id="kie-task-dup")
        self.state.transition_task(entry["task_id"], "in_progress")

        ledger = self.state.load("cost-ledger")
        duplicate = dict(next(e for e in ledger["entries"] if e["task_id"] == entry["task_id"]))
        duplicate["task_id"] = "t-fabricated-dup"
        duplicate["provider_task_id"] = "kie-task-dup-2"
        ledger["entries"].append(duplicate)
        self.state.save("cost-ledger", ledger)

        passed, detail = rt.assert_no_duplicate_spend(self.tmp, fail_closed=False)
        self.assertFalse(passed)
        self.assertIn(entry["request_hash"], detail)

        with self.assertRaises(rt.DuplicateSpendDetected):
            rt.assert_no_duplicate_spend(self.tmp, fail_closed=True)

    def test_failed_and_complete_entries_for_the_same_hash_are_not_a_violation(self) -> None:
        """A FAILED historical attempt followed by a fresh COMPLETE retry for
        the same request_hash is the normal retry pattern, not a duplicate
        (only entries BOTH counted as active-or-complete simultaneously are a
        violation)."""
        params = {"scene": "retry-then-succeed"}
        entry1 = self.state.begin_task(
            provider="kie", model="kie-bytedance-seedance-1.5-pro", operation="generate_video",
            params=params, estimated_cost_usd=0.2, seconds=4,
        )
        self.state.transition_task(entry1["task_id"], "failed", retry_reason="fixture failure")
        entry2 = self.state.begin_task(
            provider="kie", model="kie-bytedance-seedance-1.5-pro", operation="generate_video",
            params=params, estimated_cost_usd=0.2, seconds=4,
        )
        self.state.transition_task(entry2["task_id"], "submitted", provider_task_id="kie-task-retry-ok")
        self.state.transition_task(entry2["task_id"], "in_progress")
        self.state.transition_task(entry2["task_id"], "complete", actual_cost_usd=0.2)

        passed, detail = rt.assert_no_duplicate_spend(self.tmp, fail_closed=False)
        self.assertTrue(passed, detail)


class CliTests(RecoverTasksTestCase):
    def test_usage_error_missing_run_dir(self) -> None:
        result = subprocess.run([PY, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, rt.EXIT_USAGE)

    def test_usage_error_nonexistent_run_dir(self) -> None:
        result = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", "/definitely/does/not/exist"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, rt.EXIT_USAGE)

    def test_recover_action_exits_ok_on_a_clean_project(self) -> None:
        result = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", str(self.tmp), "--action", "recover"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, rt.EXIT_OK, result.stderr)

    def test_assert_no_duplicate_spend_action_exits_ok_on_a_clean_project(self) -> None:
        result = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", str(self.tmp), "--action", "assert-no-duplicate-spend"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, rt.EXIT_OK, result.stderr)


class SelfTestTests(unittest.TestCase):
    def test_module_self_test_passes(self) -> None:
        self.assertEqual(rt.self_test(), 0)


if __name__ == "__main__":
    unittest.main()
