#!/usr/bin/env python3
"""T-43 onboarding cohort integration receipts.

Pins every acceptance clause from build.json T-43:
  * single shared target owner (a real distributed lease, never a local file);
  * shared-file / schema / dependency / cross-repository compatibility;
  * red-subset isolation (red plus true dependents only);
  * exact independent gates (no broad ALL_PASS);
  * named-repair remote content proof;
  * UNKNOWN-with-reason wherever the fact was not observed;
  * the four cleanup dispositions (classification only, no deletion);
  * supervisor takeover / merge-due with restart-preserved age (C-F15);
  * the onboarding-remote-merge-receipts artifact (C-43/C-F20).

Stdlib only, temporary local state only; no network, no remote mutation.
Run: python3 -m pytest tests/unit/test_onboarding_integration.py -q
"""
from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SHARED = _REPO_ROOT / "shared-utils"
assert _SHARED.is_dir(), "shared-utils missing: %s" % _SHARED
sys.path.insert(0, str(_SHARED))

from decision_engine_train import (  # noqa: E402
    ADMITTED,
    ARTIFACT,
    CONTRADICTED,
    HELD,
    INDEPENDENT_ROUTE,
    ONBOARDING_PR_REQUIRED_CHECKS,
    PROVEN,
    RULE_ADDITIVE_SCHEMA,
    RULE_BREAKING_WRITER,
    RULE_CROSS_REPO,
    RULE_DEPENDENCY,
    RULE_RED_SUBSET,
    RULE_SHARED_FILE,
    UNKNOWN,
    build_receipt,
    cleanup_disposition,
    evaluate_cohort,
    exact_independent_gate,
    load_state,
    merge_due,
    new_state,
    prove_named_repair,
    save_state,
    target_owner,
    verify_receipt,
)

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_R = "d" * 40
HEAD_BEFORE = "1" * 40
HEAD_AFTER = "2" * 40


def unit(uid, sha, **extra):
    record = {"unit_id": uid, "sha": sha, "files": [], "depends_on": [],
              "state": "green"}
    record.update(extra)
    return record


def receipt(sha, checks=None, route=INDEPENDENT_ROUTE, verdict="PASS"):
    return {"sha": sha, "verdict": verdict, "reviewer": "sonnet-qc-1",
            "reviewer_route": route,
            "checks": checks if checks is not None else [
                {"name": "unit", "status": "pass"},
                {"name": "integration", "status": "pass"},
            ]}


def passing_gate(uid, sha):
    return exact_independent_gate(unit(uid, sha), receipt(sha))


class SharedStore:
    """A shared coordinator: CAS is the only writer. distributed=True."""

    distributed = True

    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def compare_and_set(self, key, expected, value):
        if self.data.get(key) != expected:
            return False
        self.data[key] = value
        return True


class LocalFileStore(SharedStore):
    distributed = False


class TargetOwner(unittest.TestCase):
    """Clause: single shared target owner."""

    def test_no_backend_is_unknown_never_success(self):
        result = target_owner(None, "onb/main", "w13", 1000)
        self.assertEqual(result["state"], UNKNOWN)
        self.assertEqual(result["reason"], "no_shared_lease_backend")

    def test_local_file_is_not_distributed_exclusion(self):
        result = target_owner(LocalFileStore(), "onb/main", "w13", 1000)
        self.assertEqual(result["state"], UNKNOWN)
        self.assertEqual(result["reason"],
                         "local_file_is_not_distributed_exclusion")

    def test_two_clones_only_one_owns_the_target(self):
        store = SharedStore()
        first = target_owner(store, "onb/main", "w13-a", 1000)
        second = target_owner(store, "onb/main", "w13-b", 1000)
        self.assertEqual(first["state"], PROVEN)
        self.assertEqual(second["state"], HELD)
        self.assertTrue(second["reason"].startswith("lease_held_by_other"))
        self.assertEqual(store.get("onb/main")["owner"], "w13-a")

    def test_expired_lease_can_be_taken_over(self):
        store = SharedStore()
        target_owner(store, "onb/main", "w13-a", 1000, ttl=60)
        later = target_owner(store, "onb/main", "w13-b", 2000, ttl=60)
        self.assertEqual(later["state"], PROVEN)
        self.assertEqual(later["owner"], "w13-b")

    def test_lost_compare_and_set_is_held(self):
        class Racing(SharedStore):
            def compare_and_set(self, key, expected, value):
                self.data[key] = {"owner": "other", "acquired": 1,
                                  "expires": 10 ** 9}
                return False

        result = target_owner(Racing(), "onb/main", "w13", 1000)
        self.assertEqual(result["state"], HELD)
        self.assertEqual(result["reason"], "lease_compare_and_set_lost")

    def test_backend_exception_is_unknown(self):
        class Broken(SharedStore):
            def get(self, key):
                raise OSError("coordinator down")

        result = target_owner(Broken(), "onb/main", "w13", 1000)
        self.assertEqual(result["state"], UNKNOWN)
        self.assertTrue(result["reason"].startswith("lease_backend_error:"))


class Compatibility(unittest.TestCase):
    """Clause: shared-file/schema/dependency/cross-repo compatibility."""

    def test_separate_files_admit_in_deterministic_order(self):
        report = evaluate_cohort([
            unit("B", SHA_B, files=["b.py"]),
            unit("A", SHA_A, files=["a.py"]),
        ])
        self.assertEqual(report["state"], ADMITTED)
        self.assertEqual(report["order"], ["A", "B"])
        self.assertEqual([c["sha"] for c in report["candidates"]],
                         [SHA_A, SHA_B])

    def test_shared_file_holds_both_without_combined_owner(self):
        report = evaluate_cohort([
            unit("A", SHA_A, files=["schema.json"]),
            unit("B", SHA_B, files=["schema.json"]),
        ])
        self.assertEqual(report["state"], HELD)
        held = {entry["unit_id"]: entry["rule_id"] for entry in report["hold"]}
        self.assertEqual(held, {"A": RULE_SHARED_FILE, "B": RULE_SHARED_FILE})
        self.assertEqual(report["admit"], [])
        self.assertEqual(len(report["shared_files"]), 1)

    def test_shared_file_admitted_as_one_combined_candidate(self):
        report = evaluate_cohort([
            unit("A", SHA_A, files=["schema.json"]),
            unit("B", SHA_B, files=["schema.json"]),
        ], combined_owner=["A", "B"])
        self.assertEqual(report["state"], ADMITTED)
        self.assertEqual(report["combined_candidates"],
                         [{"files": ["schema.json"], "unit_ids": ["A", "B"]}])

    def test_additive_schema_without_reader_proof_holds(self):
        report = evaluate_cohort([
            unit("A", SHA_A, schema={"kind": "additive"}),
        ])
        self.assertEqual(report["state"], HELD)
        self.assertEqual(report["hold"][0]["rule_id"], RULE_ADDITIVE_SCHEMA)
        self.assertEqual(report["hold"][0]["reason"],
                         "tolerant_readers_unproved")

    def test_additive_schema_with_reader_trace_admits(self):
        report = evaluate_cohort([
            unit("A", SHA_A, schema={"kind": "additive",
                                     "tolerant_readers_proved": True,
                                     "reader_trace": ["old reader ignores field"]}),
        ])
        self.assertEqual(report["state"], ADMITTED)

    def test_breaking_writer_requires_manifest_checkpoint_and_disabled_switch(self):
        base = {"kind": "breaking"}
        no_manifest = evaluate_cohort([unit("A", SHA_A, schema=dict(base))])
        self.assertEqual(no_manifest["hold"][0]["rule_id"], RULE_BREAKING_WRITER)
        self.assertEqual(no_manifest["hold"][0]["reason"],
                         "protocol_manifest_missing")

        no_checkpoint = evaluate_cohort([unit("A", SHA_A, schema={
            "kind": "breaking", "protocol_version": "proto-2"})])
        self.assertEqual(no_checkpoint["hold"][0]["reason"],
                         "migration_checkpoint_missing")

        switch_on = evaluate_cohort([unit("A", SHA_A, schema={
            "kind": "breaking", "protocol_version": "proto-2",
            "migration_checkpoint": "ckpt-1", "writer_switch_enabled": True})])
        self.assertEqual(switch_on["hold"][0]["reason"],
                         "writer_switch_before_reader_proof")

        ready = evaluate_cohort([unit("A", SHA_A, schema={
            "kind": "breaking", "protocol_version": "proto-2",
            "migration_checkpoint": "ckpt-1", "writer_switch_enabled": False})])
        self.assertEqual(ready["state"], ADMITTED)

    def test_missing_dependency_contract_holds(self):
        report = evaluate_cohort([unit("B", SHA_B, depends_on=["A"])])
        self.assertEqual(report["state"], HELD)
        self.assertEqual(report["hold"][0]["rule_id"], RULE_DEPENDENCY)
        self.assertEqual(report["hold"][0]["reason"],
                         "dependency_contract_missing:A")

    def test_in_cohort_dependency_orders_producer_first(self):
        report = evaluate_cohort([
            unit("B", SHA_B, depends_on=["A"]),
            unit("A", SHA_A),
        ])
        self.assertEqual(report["state"], ADMITTED)
        self.assertEqual(report["order"], ["A", "B"])

    def test_accepted_landed_dependency_satisfies_contract(self):
        report = evaluate_cohort([unit("B", SHA_B, depends_on=["A"])],
                                 already_landed=["A"])
        self.assertEqual(report["state"], ADMITTED)

    def test_dependency_cycle_is_unknown(self):
        report = evaluate_cohort([
            unit("A", SHA_A, depends_on=["B"]),
            unit("B", SHA_B, depends_on=["A"]),
        ])
        self.assertEqual(report["state"], UNKNOWN)
        self.assertEqual(report["unknown"][0]["reason"], "dependency_cycle")

    def test_cross_repo_without_publication_order_holds(self):
        report = evaluate_cohort([
            unit("consumer", SHA_B, repo="cc", depends_on_repos=["onb"]),
        ], repository="cc")
        self.assertEqual(report["state"], HELD)
        self.assertEqual(report["hold"][0]["rule_id"], RULE_CROSS_REPO)
        self.assertEqual(report["hold"][0]["reason"],
                         "publication_order_unobserved")

    def test_cross_repo_wrong_order_holds(self):
        report = evaluate_cohort([
            unit("consumer", SHA_B, repo="cc", depends_on_repos=["onb"]),
        ], repository="cc", publication_order=["cc", "onb"])
        self.assertEqual(report["state"], HELD)
        self.assertEqual(report["hold"][0]["reason"],
                         "consumer_before_producer:onb")

    def test_cross_repo_correct_order_admits(self):
        report = evaluate_cohort([
            unit("consumer", SHA_B, repo="cc", depends_on_repos=["onb"]),
        ], repository="cc", publication_order=["onb", "cc"])
        self.assertEqual(report["state"], ADMITTED)

    def test_missing_candidate_sha_is_unknown(self):
        report = evaluate_cohort([unit("A", "")])
        self.assertEqual(report["state"], UNKNOWN)
        self.assertEqual(report["unknown"][0]["reason"],
                         "candidate_sha_unobserved")

    def test_duplicate_unit_id_is_unknown(self):
        report = evaluate_cohort([unit("A", SHA_A), unit("A", SHA_B)])
        self.assertEqual(report["state"], UNKNOWN)
        self.assertEqual(report["unknown"][0]["reason"], "duplicate_unit_id")


class RedSubset(unittest.TestCase):
    """Clause: red-subset isolation keeps unrelated green work moving."""

    def test_red_and_true_dependents_held_green_continues(self):
        report = evaluate_cohort([
            unit("red", SHA_R, state="red"),
            unit("dependent", SHA_B, depends_on=["red"]),
            unit("green", SHA_A),
        ])
        self.assertEqual(report["state"], HELD)
        self.assertEqual(report["admit"], ["green"])
        held = {(e["unit_id"], e["rule_id"]) for e in report["hold"]}
        self.assertEqual(held, {("red", RULE_RED_SUBSET),
                                ("dependent", RULE_RED_SUBSET)})
        self.assertEqual(report["red_subset"],
                         {"roots": ["red"], "held": ["dependent", "red"]})

    def test_red_without_dependents_holds_only_itself(self):
        report = evaluate_cohort([
            unit("red", SHA_R, state="red"),
            unit("green", SHA_A),
        ])
        self.assertEqual(report["admit"], ["green"])
        self.assertEqual([e["unit_id"] for e in report["hold"]], ["red"])


class ExactGates(unittest.TestCase):
    """Clause: exact independent gates, no broad ALL_PASS."""

    def test_exact_sha_independent_all_checks_proven(self):
        result = exact_independent_gate(unit("A", SHA_A), receipt(SHA_A))
        self.assertEqual(result["state"], PROVEN)
        self.assertEqual(result["reason"], "")

    def test_changed_sha_contradicts(self):
        result = exact_independent_gate(unit("A", SHA_A), receipt(SHA_B))
        self.assertEqual(result["state"], CONTRADICTED)
        self.assertEqual(result["reason"], "changed SHA loses eligibility")

    def test_train_route_cannot_approve(self):
        result = exact_independent_gate(
            unit("A", SHA_A), receipt(SHA_A, route="haiku-chain"))
        self.assertEqual(result["state"], CONTRADICTED)
        self.assertEqual(result["reason"], "qc reviewer is not sonnet-chain")

    def test_missing_receipt_is_unknown(self):
        result = exact_independent_gate(unit("A", SHA_A), None)
        self.assertEqual(result["state"], UNKNOWN)
        self.assertEqual(result["reason"], "qc_receipt_unobserved")

    def test_missing_required_check_is_unknown(self):
        result = exact_independent_gate(
            unit("A", SHA_A),
            receipt(SHA_A, checks=[{"name": "unit", "status": "pass"}]))
        self.assertEqual(result["state"], UNKNOWN)
        self.assertEqual(result["reason"], "required_check_unobserved:integration")

    def test_failed_required_check_contradicts(self):
        result = exact_independent_gate(
            unit("A", SHA_A),
            receipt(SHA_A, checks=[{"name": "unit", "status": "pass"},
                                   {"name": "integration", "status": "fail"}]))
        self.assertEqual(result["state"], CONTRADICTED)
        self.assertEqual(result["reason"], "required_check_failed:integration")

    def test_broad_all_pass_is_refused(self):
        result = exact_independent_gate(
            unit("A", SHA_A),
            receipt(SHA_A, checks=[{"name": "ALL_PASS", "status": "pass"}]))
        self.assertEqual(result["state"], CONTRADICTED)
        self.assertEqual(result["reason"],
                         "broad_all_pass_is_not_exact_evidence")

    def test_onboarding_required_contexts_are_pinned(self):
        self.assertEqual(len(ONBOARDING_PR_REQUIRED_CHECKS), 7)
        self.assertIn("QC static invariants", ONBOARDING_PR_REQUIRED_CHECKS)
        self.assertNotIn(
            "G1 — version file change requires a matching annotated tag (push to main)",
            ONBOARDING_PR_REQUIRED_CHECKS)
        checks = [{"name": name, "status": "pass"}
                  for name in ONBOARDING_PR_REQUIRED_CHECKS]
        proven = exact_independent_gate(
            unit("A", SHA_A), receipt(SHA_A, checks=checks),
            required_checks=ONBOARDING_PR_REQUIRED_CHECKS)
        self.assertEqual(proven["state"], PROVEN)
        missing = exact_independent_gate(
            unit("A", SHA_A), receipt(SHA_A, checks=checks[:-1]),
            required_checks=ONBOARDING_PR_REQUIRED_CHECKS)
        self.assertEqual(missing["state"], UNKNOWN)

    def test_no_check_results_is_unknown(self):
        result = exact_independent_gate(unit("A", SHA_A), receipt(SHA_A, checks=[]))
        self.assertEqual(result["state"], UNKNOWN)
        self.assertEqual(result["reason"], "required_check_results_unobserved")


class NamedRepair(unittest.TestCase):
    """Clause: named repair remote content proof."""

    def test_ancestry_proves_the_repair(self):
        result = prove_named_repair(
            {"repair_id": "R1", "sha": SHA_R},
            {"remote": "origin", "target_ref": "refs/heads/main",
             "observed_head": HEAD_AFTER, "method": "ancestry",
             "contains_sha": True})
        self.assertEqual(result["state"], PROVEN)
        self.assertEqual(result["reason"], "repair_in_target_ancestry")

    def test_absent_from_ancestry_contradicts(self):
        result = prove_named_repair(
            {"repair_id": "R1", "sha": SHA_R},
            {"remote": "origin", "target_ref": "refs/heads/main",
             "observed_head": HEAD_AFTER, "method": "ancestry",
             "contains_sha": False})
        self.assertEqual(result["state"], CONTRADICTED)
        self.assertEqual(result["reason"], "repair_absent_from_target_ancestry")

    def test_unobserved_ancestry_is_unknown(self):
        result = prove_named_repair(
            {"repair_id": "R1", "sha": SHA_R},
            {"remote": "origin", "target_ref": "refs/heads/main",
             "observed_head": HEAD_AFTER, "method": "ancestry"})
        self.assertEqual(result["state"], UNKNOWN)
        self.assertEqual(result["reason"], "ancestry_unobserved")

    def test_content_equivalence_proves_squash_merge(self):
        result = prove_named_repair(
            {"repair_id": "R1", "sha": SHA_R,
             "files": {"a.py": "blob-a"}},
            {"remote": "origin", "target_ref": "refs/heads/main",
             "observed_head": HEAD_AFTER, "method": "content_equivalence",
             "tree": {"a.py": "blob-a"}})
        self.assertEqual(result["state"], PROVEN)
        self.assertEqual(result["reason"], "remote_content_equivalence")

    def test_partial_tree_is_unknown_not_success(self):
        result = prove_named_repair(
            {"repair_id": "R1", "sha": SHA_R,
             "files": {"a.py": "blob-a", "b.py": "blob-b"}},
            {"remote": "origin", "target_ref": "refs/heads/main",
             "observed_head": HEAD_AFTER, "method": "content_equivalence",
             "tree": {"a.py": "blob-a"}})
        self.assertEqual(result["state"], UNKNOWN)
        self.assertEqual(result["reason"], "content_partially_observed:b.py")

    def test_different_content_contradicts(self):
        result = prove_named_repair(
            {"repair_id": "R1", "sha": SHA_R, "files": {"a.py": "blob-a"}},
            {"remote": "origin", "target_ref": "refs/heads/main",
             "observed_head": HEAD_AFTER, "method": "squash",
             "tree": {"a.py": "other"}})
        self.assertEqual(result["state"], CONTRADICTED)
        self.assertEqual(result["reason"], "remote_content_differs:a.py")

    def test_unobserved_remote_is_unknown(self):
        result = prove_named_repair(
            {"repair_id": "R1", "sha": SHA_R}, None)
        self.assertEqual(result["state"], UNKNOWN)
        self.assertEqual(result["reason"], "remote_content_unobserved")

    def test_prior_baseline_merge_is_never_repair_proof(self):
        result = prove_named_repair(
            {"repair_id": "R1", "sha": SHA_R},
            {"remote": "origin", "target_ref": "refs/heads/main",
             "observed_head": HEAD_AFTER, "method": "baseline_only"})
        self.assertEqual(result["state"], UNKNOWN)
        self.assertEqual(result["reason"],
                         "prior_baseline_merge_is_not_repair_proof")

    def test_unknown_method_is_unknown(self):
        result = prove_named_repair(
            {"repair_id": "R1", "sha": SHA_R},
            {"remote": "origin", "target_ref": "refs/heads/main",
             "observed_head": HEAD_AFTER, "method": "vibes"})
        self.assertEqual(result["state"], UNKNOWN)
        self.assertEqual(result["reason"], "proof_method_unobserved")

    def test_malformed_repair_sha_is_unknown(self):
        result = prove_named_repair(
            {"repair_id": "R1", "sha": "not-a-sha"},
            {"remote": "origin", "target_ref": "refs/heads/main",
             "observed_head": HEAD_AFTER, "method": "ancestry",
             "contains_sha": True})
        self.assertEqual(result["state"], UNKNOWN)
        self.assertEqual(result["reason"], "repair_sha_not_exact_40_hex")


class MergeDue(unittest.TestCase):
    """Clause: supervisor takeover / merge due (C-F15)."""

    def test_busy_target_stays_due_and_rechecks_within_ten_minutes(self):
        state = {}
        result = merge_due(state, "onb", 1000, busy_until=5000)
        self.assertTrue(result["due"])
        self.assertEqual(result["next_check"], 1600)
        self.assertEqual(result["reason"], "target_busy_remains_due")

    def test_event_makes_owner_due_immediately(self):
        state = {}
        result = merge_due(state, "onb", 1000, new_events=True)
        self.assertTrue(result["due"])
        self.assertTrue(result["immediate"])
        self.assertEqual(result["next_check"], 1000)

    def test_backlog_sweep_is_at_most_hourly(self):
        state = {}
        first = merge_due(state, "onb", 1000)
        self.assertTrue(first["due"])
        second = merge_due(state, "onb", 2000)
        self.assertFalse(second["due"])
        self.assertEqual(second["next_check"], 1000 + 3600)
        third = merge_due(state, "onb", 4600)
        self.assertTrue(third["due"])

    def test_restart_preserves_first_due_age(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "train.json"
            state = new_state()
            first = merge_due(state, "onb", 1000)
            save_state(state, path)
            reread = load_state(str(path))
            later = merge_due(reread, "onb", 2000)
            self.assertEqual(later["first_due"], first["first_due"])
            self.assertFalse(later["due"])


class CleanupDispositions(unittest.TestCase):
    """Clause: the four cleanup dispositions (T-46 acts; this classifies)."""

    def test_disposable_scratch_is_eligible(self):
        result = cleanup_disposition({
            "id": "s", "resource_type": "disposable_scratch",
            "consumers": [], "has_unique_unmerged_work": False})
        self.assertEqual((result["disposition"], result["reason"]),
                         ("eligible", "disposable_scratch"))

    def test_clean_merged_tree_is_eligible(self):
        result = cleanup_disposition({
            "id": "m", "resource_type": "merged_worktree",
            "consumers": [], "has_unique_unmerged_work": False,
            "clean_state": "CLEAN", "remote_merge_proof_ids": ["M-1"]})
        self.assertEqual((result["disposition"], result["reason"]),
                         ("eligible", "clean_merged_tree"))

    def test_dirty_unique_work_is_deferred(self):
        result = cleanup_disposition({
            "id": "d", "resource_type": "merged_worktree",
            "consumers": [], "has_unique_unmerged_work": True,
            "clean_state": "DIRTY_UNIQUE", "remote_merge_proof_ids": []})
        self.assertEqual(result["disposition"], "deferred")
        self.assertEqual(result["reason"], "unique_unmerged_work_preserved")

    def test_active_consumer_is_deferred(self):
        result = cleanup_disposition({
            "id": "c", "resource_type": "disposable_scratch",
            "consumers": [{"id": "builder", "state": "released"},
                          {"id": "checker", "state": "active"}],
            "has_unique_unmerged_work": False})
        self.assertEqual(result["disposition"], "deferred")
        self.assertEqual(result["reason"], "consumer_active:checker")

    def test_unobserved_state_is_unknown(self):
        result = cleanup_disposition({"id": "x",
                                      "resource_type": "disposable_scratch"})
        self.assertEqual(result["disposition"], UNKNOWN)
        self.assertEqual(result["reason"], "consumer_state_unobserved")

    def test_merged_tree_without_remote_proof_is_unknown(self):
        result = cleanup_disposition({
            "id": "m", "resource_type": "merged_worktree",
            "consumers": [], "has_unique_unmerged_work": False,
            "clean_state": "CLEAN", "remote_merge_proof_ids": []})
        self.assertEqual(result["disposition"], UNKNOWN)
        self.assertEqual(result["reason"], "remote_merge_proof_unobserved")


class Receipts(unittest.TestCase):
    """Clause: onboarding-remote-merge-receipts never claims false success."""

    def _proven_parts(self):
        owner = target_owner(SharedStore(), "onb/main", "w13", 1000)
        cohort = evaluate_cohort([unit("A", SHA_A), unit("B", SHA_B)])
        gates = [passing_gate("A", SHA_A), passing_gate("B", SHA_B)]
        return owner, cohort, gates

    def test_proven_receipt(self):
        owner, cohort, gates = self._proven_parts()
        receipt_doc = build_receipt(
            owner=owner, target={"remote": "origin", "before": HEAD_BEFORE,
                                 "after": HEAD_AFTER},
            cohort=cohort, gates=gates,
            proof={"state": PROVEN, "reason": "target_head_observed"},
            cleanup=[{"id": "s", "disposition": "eligible",
                      "reason": "disposable_scratch"}])
        self.assertEqual(receipt_doc["state"], PROVEN)
        self.assertEqual(receipt_doc["artifact"], ARTIFACT)
        self.assertEqual(receipt_doc["reasons"], [])
        self.assertNotIn("ALL_PASS", str(receipt_doc))
        ok, reason = verify_receipt(receipt_doc)
        self.assertTrue(ok, reason)

    def test_unknown_remote_proof_forces_unknown(self):
        owner, cohort, gates = self._proven_parts()
        receipt_doc = build_receipt(
            owner=owner, target={"remote": "origin", "before": HEAD_BEFORE,
                                 "after": HEAD_AFTER},
            cohort=cohort, gates=gates,
            proof={"state": UNKNOWN, "reason": "remote_content_unobserved"})
        self.assertEqual(receipt_doc["state"], UNKNOWN)
        self.assertTrue(receipt_doc["reasons"])
        ok, reason = verify_receipt(receipt_doc)
        self.assertTrue(ok, reason)

    def test_unobserved_target_forces_unknown(self):
        owner, cohort, gates = self._proven_parts()
        receipt_doc = build_receipt(
            owner=owner, target={"remote": "", "before": "", "after": ""},
            cohort=cohort, gates=gates,
            proof={"state": PROVEN, "reason": "target_head_observed"})
        self.assertEqual(receipt_doc["state"], UNKNOWN)
        self.assertIn("remote_target_unobserved", receipt_doc["reasons"])

    def test_held_cohort_cannot_produce_a_proven_receipt(self):
        owner = target_owner(SharedStore(), "onb/main", "w13", 1000)
        cohort = evaluate_cohort([
            unit("A", SHA_A, files=["x"]), unit("B", SHA_B, files=["x"])])
        receipt_doc = build_receipt(
            owner=owner,
            target={"remote": "origin", "before": HEAD_BEFORE,
                    "after": HEAD_AFTER},
            cohort=cohort, gates=[],
            proof={"state": PROVEN, "reason": "target_head_observed"})
        self.assertNotEqual(receipt_doc["state"], PROVEN)

    def test_contradicted_gate_wins(self):
        owner, cohort, _gates = self._proven_parts()
        bad = exact_independent_gate(unit("A", SHA_A), receipt(SHA_B))
        receipt_doc = build_receipt(
            owner=owner, target={"remote": "origin", "before": HEAD_BEFORE,
                                 "after": HEAD_AFTER},
            cohort=cohort, gates=[bad],
            proof={"state": PROVEN, "reason": "target_head_observed"})
        self.assertEqual(receipt_doc["state"], CONTRADICTED)

    def test_named_repair_must_also_be_proven(self):
        owner, cohort, gates = self._proven_parts()
        unresolved = prove_named_repair({"repair_id": "R1", "sha": SHA_R}, None)
        receipt_doc = build_receipt(
            owner=owner, target={"remote": "origin", "before": HEAD_BEFORE,
                                 "after": HEAD_AFTER},
            cohort=cohort, gates=gates, named_repairs=[unresolved],
            proof={"state": PROVEN, "reason": "target_head_observed"})
        self.assertEqual(receipt_doc["state"], UNKNOWN)

    def test_verify_receipt_rejects_false_proven(self):
        forged = {"artifact": ARTIFACT, "state": PROVEN, "reasons": [],
                  "owner": {"state": PROVEN},
                  "target": {"remote": "origin", "before": "1", "after": "2"},
                  "candidates": [{"unit_id": "A", "sha": SHA_A}],
                  "cohort": {"admit": ["A"], "hold": [], "unknown": []},
                  "gates": [{"unit_id": "A", "state": UNKNOWN, "reason": "x"}],
                  "proof": {"state": PROVEN}}
        ok, reason = verify_receipt(forged)
        self.assertFalse(ok)
        self.assertEqual(reason, "proven receipt carries a non-proven gate")

    def test_verify_receipt_rejects_proven_with_a_held_cohort(self):
        forged = {"artifact": ARTIFACT, "state": PROVEN, "reasons": [],
                  "owner": {"state": PROVEN},
                  "target": {"remote": "origin", "before": "1", "after": "2"},
                  "candidates": [{"unit_id": "A", "sha": SHA_A}],
                  "cohort": {"admit": ["A"],
                             "hold": [{"unit_id": "B", "rule_id": "BC-02"}],
                             "unknown": []},
                  "gates": [{"unit_id": "A", "state": PROVEN}],
                  "proof": {"state": PROVEN}}
        ok, reason = verify_receipt(forged)
        self.assertFalse(ok)
        self.assertEqual(reason,
                         "proven receipt carries a non-admitted cohort")

    def test_verify_receipt_rejects_proven_with_unknown_cleanup(self):
        forged = {"artifact": ARTIFACT, "state": PROVEN, "reasons": [],
                  "owner": {"state": PROVEN},
                  "target": {"remote": "origin", "before": "1", "after": "2"},
                  "candidates": [{"unit_id": "A", "sha": SHA_A}],
                  "cohort": {"admit": ["A"], "hold": [], "unknown": []},
                  "gates": [{"unit_id": "A", "state": PROVEN}],
                  "cleanup": [{"id": "s", "disposition": UNKNOWN,
                               "reason": "consumer_state_unobserved"}],
                  "proof": {"state": PROVEN}}
        ok, reason = verify_receipt(forged)
        self.assertFalse(ok)
        self.assertEqual(reason, "proven receipt carries an unknown cleanup")

    def test_verify_receipt_requires_a_reason_for_unknown(self):
        ok, reason = verify_receipt({"artifact": ARTIFACT, "state": UNKNOWN,
                                     "reasons": []})
        self.assertFalse(ok)
        self.assertEqual(reason, "UNKNOWN receipt must name a reason")


class ReuseAndIsolation(unittest.TestCase):
    """Clause: reuse accepted upstream modules; no hidden side channels."""

    def test_integration_module_has_no_process_network_or_fs_mutation(self):
        source = (_SHARED / "decision_engine_train" / "integration.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        forbidden = {"subprocess", "socket", "requests", "urllib", "http",
                     "shutil", "os"}
        self.assertEqual(imported & forbidden, set())

    def test_integration_module_reuses_the_train_core(self):
        source = (_SHARED / "decision_engine_train" / "integration.py").read_text(
            encoding="utf-8")
        self.assertIn("from .train import", source)
        self.assertIn("isolate_failure", source)
        self.assertIn("validate_qc_receipt", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
