#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_approve_paid_run.py — offline unit tests for scripts/approve_paid_run.py
(Skill 62, U7).

Covers:
  - approve() writes cap_usd/approved/approved_by/approved_at onto
    project-manifest.budget AND appends a matching approvals[] audit entry,
    AND keeps cost-ledger.budget_cap_usd/remaining_budget_usd in lockstep, in
    one atomic transaction.
  - is_approved() only returns True when the boolean flag AND the audit
    entry agree — a hand-edited budget.approved=True with no matching
    approvals[] entry is correctly rejected (this is what makes
    prove_budget.evaluate_approval()/evaluate_paid_call_preconditions()
    trustworthy).
  - fail-closed validation: non-positive cap, non-finite cap (NaN/inf), a cap
    set below already-recorded cumulative spend, an empty approver, and an
    approver value shaped like a leaked secret are all rejected before
    anything is written to disk.
  - re-approval (raising or lowering, within bounds, the cap) is fully
    supported and always requires a fresh explicit call.

stdlib unittest only.
Run: python3 -m unittest discover -s tests/unit -v
     (from the 62-cinematic-web-funnel-engine/ directory)
"""

from __future__ import annotations

import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))
if str(_SKILL_DIR / "scripts") not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR / "scripts"))

import approve_paid_run as apr  # noqa: E402
import state_engine as se  # noqa: E402


class ApprovePaidRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cwfe-approve-tests-"))
        self.state = se.ProjectState(self.tmp)
        self.state.create_project(
            project_id="proj-approve-tests",
            client_slug="acme",
            project_slug="launch",
            deliverable_type="cinematic-landing-page",
            budget_cap_usd=1.0,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_approve_writes_budget_fields_and_audit_entry(self) -> None:
        budget = apr.approve(self.tmp, cap_usd=7.5, approved_by="operator", note="initial cap")
        self.assertEqual(budget["cap_usd"], 7.5)
        self.assertTrue(budget["approved"])
        self.assertEqual(budget["approved_by"], "operator")
        self.assertIsNotNone(budget["approved_at"])

        manifest = self.state.load("project-manifest")
        approvals = [a for a in manifest["approvals"] if a["kind"] == "budget"]
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0]["cap_usd"], 7.5)
        self.assertEqual(approvals[0]["approved_by"], "operator")

    def test_approve_keeps_cost_ledger_cap_in_lockstep(self) -> None:
        apr.approve(self.tmp, cap_usd=3.25, approved_by="operator")
        ledger = self.state.load("cost-ledger")
        self.assertEqual(ledger["budget_cap_usd"], 3.25)
        self.assertEqual(ledger["remaining_budget_usd"], 3.25)

    def test_is_approved_false_before_any_approval(self) -> None:
        self.assertFalse(apr.is_approved(self.tmp))

    def test_is_approved_true_after_approval(self) -> None:
        apr.approve(self.tmp, cap_usd=2.0, approved_by="operator")
        self.assertTrue(apr.is_approved(self.tmp))

    def test_is_approved_false_when_flag_set_without_matching_audit_entry(self) -> None:
        # Simulate someone hand-editing budget.approved=True without going
        # through approve() — the audit-trail cross-check must catch it.
        manifest = self.state.load("project-manifest")
        manifest["budget"]["approved"] = True
        manifest["budget"]["approved_by"] = "someone"
        manifest["budget"]["approved_at"] = "2026-01-01T00:00:00Z"
        manifest["budget"]["cap_usd"] = 9.0
        self.state.save("project-manifest", manifest)
        self.assertFalse(apr.is_approved(self.tmp))

    def test_reapproval_raises_the_cap(self) -> None:
        apr.approve(self.tmp, cap_usd=2.0, approved_by="operator")
        apr.approve(self.tmp, cap_usd=9.0, approved_by="operator", note="raised after client OK")
        manifest = self.state.load("project-manifest")
        self.assertEqual(manifest["budget"]["cap_usd"], 9.0)
        budget_approvals = [a for a in manifest["approvals"] if a["kind"] == "budget"]
        self.assertEqual(len(budget_approvals), 2)

    def test_rejects_zero_cap(self) -> None:
        with self.assertRaises(apr.InvalidCapError):
            apr.approve(self.tmp, cap_usd=0.0, approved_by="operator")

    def test_rejects_negative_cap(self) -> None:
        with self.assertRaises(apr.InvalidCapError):
            apr.approve(self.tmp, cap_usd=-5.0, approved_by="operator")

    def test_rejects_nan_cap(self) -> None:
        with self.assertRaises(apr.InvalidCapError):
            apr.approve(self.tmp, cap_usd=float("nan"), approved_by="operator")

    def test_rejects_infinite_cap(self) -> None:
        with self.assertRaises(apr.InvalidCapError):
            apr.approve(self.tmp, cap_usd=math.inf, approved_by="operator")

    def test_rejects_non_numeric_cap(self) -> None:
        with self.assertRaises(apr.InvalidCapError):
            apr.approve(self.tmp, cap_usd="lots", approved_by="operator")  # type: ignore[arg-type]

    def test_rejects_cap_below_recorded_cumulative_spend(self) -> None:
        apr.approve(self.tmp, cap_usd=5.0, approved_by="operator")
        entry = self.state.begin_task(
            provider="kie",
            model="veo3_fast",
            operation="generate_video",
            params={"scene": "s1"},
            estimated_cost_usd=1.0,
        )
        self.state.transition_task(entry["task_id"], "submitted", provider_task_id="kie-x")
        self.state.transition_task(entry["task_id"], "in_progress")
        self.state.transition_task(entry["task_id"], "complete", actual_cost_usd=1.0)
        with self.assertRaises(apr.InvalidCapError):
            apr.approve(self.tmp, cap_usd=0.5, approved_by="operator")

    def test_rejects_empty_approver(self) -> None:
        with self.assertRaises(apr.InvalidApproverError):
            apr.approve(self.tmp, cap_usd=5.0, approved_by="")

    def test_rejects_whitespace_only_approver(self) -> None:
        with self.assertRaises(apr.InvalidApproverError):
            apr.approve(self.tmp, cap_usd=5.0, approved_by="   ")

    def test_rejects_approver_shaped_like_a_secret(self) -> None:
        with self.assertRaises(apr.InvalidApproverError):
            apr.approve(self.tmp, cap_usd=5.0, approved_by="pit-1234567890abcdef")

    def test_rejects_approver_containing_bearer_token(self) -> None:
        with self.assertRaises(apr.InvalidApproverError):
            apr.approve(self.tmp, cap_usd=5.0, approved_by="Bearer sk-abc123")

    def test_no_disk_write_on_rejected_approval(self) -> None:
        before = self.state.load("project-manifest")
        try:
            apr.approve(self.tmp, cap_usd=-1.0, approved_by="operator")
        except apr.InvalidCapError:
            pass
        after = self.state.load("project-manifest")
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
