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
    validate_qc_receipt,
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

    def test_lease_with_no_expiry_is_unknown_not_stolen(self):
        """C1: no `expires` is unobserved, never 'expired' — a live lease is safe."""
        store = SharedStore()
        store.data["onb/main"] = {"owner": "w13-a"}
        result = target_owner(store, "onb/main", "w13-b", 1000)
        self.assertEqual(result["state"], UNKNOWN)
        self.assertEqual(result["reason"], "lease_expiry_unobserved")
        self.assertEqual(store.get("onb/main"), {"owner": "w13-a"})

    def test_malformed_expiry_is_unknown_never_raises(self):
        """C1: a string expiry is an unobserved clock, not an instant."""
        store = SharedStore()
        store.data["onb/main"] = {"owner": "w13-a", "expires": "soon"}
        result = target_owner(store, "onb/main", "w13-b", 1000)
        self.assertEqual(result["state"], UNKNOWN)
        self.assertEqual(result["reason"], "lease_expiry_malformed")
        self.assertEqual(store.get("onb/main")["owner"], "w13-a")

    def test_unobserved_owner_is_unknown_not_a_proven_lease(self):
        """C1: `None` is not an owner; str() must not invent one."""
        result = target_owner(SharedStore(), "onb/main", None, 1000)
        self.assertEqual(result["state"], UNKNOWN)
        self.assertEqual(result["reason"], "lease_owner_unobserved")

    def test_unobserved_key_is_unknown_not_a_proven_lease(self):
        """C1: `None` is not a key; str() must not invent one."""
        result = target_owner(SharedStore(), None, "w13", 1000)
        self.assertEqual(result["state"], UNKNOWN)
        self.assertEqual(result["reason"], "lease_key_unobserved")

    def test_malformed_clock_is_unknown_never_raises(self):
        """C1: `now` and `ttl` are observed seconds or the fact is unobserved."""
        for now, ttl in ((1000, "900"), ("now", 900), (1000, True)):
            with self.subTest((now, ttl)):
                result = target_owner(SharedStore(), "onb/main", "w13", now, ttl)
                self.assertEqual(result["state"], UNKNOWN)
                self.assertEqual(result["reason"], "lease_clock_unobserved")


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

    def test_unobserved_files_is_unknown_not_touches_nothing(self):
        """BC-02: an unobserved ``files`` list is UNKNOWN, never "touches nothing"."""
        report = evaluate_cohort([
            {"unit_id": "A", "sha": SHA_A},
            {"unit_id": "B", "sha": SHA_B, "files": ["x.py"]},
        ])
        self.assertEqual(report["state"], UNKNOWN)
        self.assertEqual(report["admit"], [])
        self.assertIn("unit_files_unobserved",
                      [e["reason"] for e in report["unknown"]])
        control = evaluate_cohort([
            {"unit_id": "A", "sha": SHA_A, "state": "green"},
            {"unit_id": "B", "sha": SHA_B, "files": ["x.py"], "state": "green"},
        ])
        self.assertEqual(control["state"], UNKNOWN)
        self.assertEqual([e["reason"] for e in control["unknown"]],
                         ["unit_files_unobserved"])

    def test_explicit_empty_files_still_admits(self):
        report = evaluate_cohort([
            {"unit_id": "A", "sha": SHA_A, "files": [], "state": "green"},
        ])
        self.assertEqual(report["state"], ADMITTED)

    def test_unobserved_state_is_unknown_not_green(self):
        """BC-07: a red unit with an unobserved state is never admitted."""
        report = evaluate_cohort([
            {"unit_id": "A", "sha": SHA_A, "files": ["a.py"]},
        ])
        self.assertEqual(report["state"], UNKNOWN)
        self.assertEqual(report["admit"], [])
        self.assertEqual(report["unknown"][0]["reason"], "unit_state_unobserved")

    def test_unobserved_cohort_is_unknown_never_admitted(self):
        for raw in (None, [], "units", {"A": {}}):
            with self.subTest(raw):
                report = evaluate_cohort(raw)
                self.assertEqual(report["state"], UNKNOWN)
                self.assertEqual(report["admit"], [])
                self.assertTrue(report["unknown"])

    def test_malformed_unit_records_render_unknown_never_raise(self):
        for raw in (["A"], [None], [{"unit_id": "A", "sha": SHA_A,
                                     "files": [], "state": "green",
                                     "schema": "additive"}],
                    [{"unit_id": "A", "sha": SHA_A, "files": 5,
                      "state": "green"}]):
            with self.subTest(raw):
                report = evaluate_cohort(raw)
                self.assertEqual(report["state"], UNKNOWN)
                self.assertTrue(report["unknown"])

    def test_string_combined_owner_never_collapses_a_shared_file(self):
        """C2: "AB" is one malformed owner, never two observed ones."""
        report = evaluate_cohort([
            unit("A", SHA_A, files=["x.py"]),
            unit("B", SHA_B, files=["x.py"]),
        ], combined_owner="AB")
        self.assertEqual(report["state"], UNKNOWN)
        self.assertEqual(report["admit"], [])
        self.assertEqual(report["combined_candidates"], [])
        self.assertIn("combined_owner_malformed",
                      [entry["reason"] for entry in report["unknown"]])
        self.assertEqual({entry["rule_id"] for entry in report["hold"]},
                         {RULE_SHARED_FILE})
        control = evaluate_cohort([
            unit("A", SHA_A, files=["x.py"]),
            unit("B", SHA_B, files=["x.py"]),
        ], combined_owner=["A", "B"])
        self.assertEqual(control["state"], ADMITTED)

    def test_string_already_landed_never_satisfies_a_dependency(self):
        """C2: "A" is one malformed landed id, never an observed landed set."""
        report = evaluate_cohort([unit("B", SHA_B, depends_on=["A"])],
                                 already_landed="A")
        self.assertEqual(report["state"], UNKNOWN)
        self.assertEqual(report["admit"], [])
        self.assertIn("already_landed_malformed",
                      [entry["reason"] for entry in report["unknown"]])
        control = evaluate_cohort([unit("B", SHA_B, depends_on=["A"])],
                                  already_landed=["A"])
        self.assertEqual(control["state"], ADMITTED)

    def test_string_publication_order_never_iterates_as_characters(self):
        """C2: a string order is malformed, never a list of repository names."""
        report = evaluate_cohort(
            [unit("consumer", SHA_B, repo="cc", depends_on_repos=["onb"])],
            repository="cc", publication_order="onbcc")
        self.assertEqual(report["state"], UNKNOWN)
        self.assertIn("publication_order_malformed",
                      [entry["reason"] for entry in report["unknown"]])
        self.assertEqual(report["cross_repo_order"], [])
        control = evaluate_cohort(
            [unit("consumer", SHA_B, repo="cc", depends_on_repos=["onb"])],
            repository="cc", publication_order=["onb", "cc"])
        self.assertEqual(control["state"], ADMITTED)

    def test_string_depends_on_repos_never_iterates_as_characters(self):
        """C2: "onb" is one malformed repo id, never three producer letters."""
        report = evaluate_cohort(
            [unit("consumer", SHA_B, repo="cc", depends_on_repos="onb")],
            repository="cc", publication_order=["cc", "onb"])
        self.assertEqual(report["state"], UNKNOWN)
        self.assertIn("unit_depends_on_repos_malformed",
                      [entry["reason"] for entry in report["unknown"]])
        self.assertEqual(report["admit"], [])


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

    def test_gate_without_any_sha_is_unknown_not_proven(self):
        """An 'exact' gate with no SHA on either side is not exact evidence."""
        result = exact_independent_gate(
            {"unit_id": "A"},
            {"verdict": "PASS", "reviewer": "sonnet-qc-1",
             "reviewer_route": INDEPENDENT_ROUTE,
             "checks": [{"name": "unit", "status": "pass"},
                        {"name": "integration", "status": "pass"}]})
        self.assertEqual(result["state"], UNKNOWN)
        self.assertTrue(result["reason"])

    def test_gate_with_non_hex_sha_is_unknown_not_proven(self):
        result = exact_independent_gate(unit("A", "zzz"), receipt("zzz"))
        self.assertEqual(result["state"], UNKNOWN)
        self.assertTrue(result["reason"])

    def test_gate_with_malformed_unit_record_renders_unknown(self):
        result = exact_independent_gate("A", receipt(SHA_A))
        self.assertEqual(result["state"], UNKNOWN)
        self.assertTrue(result["reason"])

    def test_gate_never_proves_on_zero_named_checks(self):
        """C3: the named-check law is never a caller-optional knob."""
        one = receipt(SHA_A, checks=[{"name": "unit", "status": "pass"}])
        for required in ((), None, [], "unit"):
            with self.subTest(required):
                result = exact_independent_gate(unit("A", SHA_A), one,
                                                required_checks=required)
                self.assertEqual(result["state"], UNKNOWN)
                self.assertEqual(result["reason"], "required_checks_unobserved")

    def test_gate_with_the_default_checks_still_proves(self):
        """C3 inverse: a real named-check list is unchanged by the guard."""
        result = exact_independent_gate(unit("A", SHA_A), receipt(SHA_A))
        self.assertEqual(result["state"], PROVEN)


class ExactShaLaw(unittest.TestCase):
    """Clause: the exact-SHA law is enforced, never a None == None pass."""

    def test_missing_sha_on_both_sides_loses_eligibility(self):
        entry = {"unit_id": "A", "sha": None,
                 "qc_receipt": {"sha": None, "verdict": "PASS",
                                "reviewer": "sonnet-qc-1",
                                "reviewer_route": INDEPENDENT_ROUTE}}
        ok, reason = validate_qc_receipt(entry)
        self.assertFalse(ok)
        self.assertTrue(reason)

    def test_empty_sha_on_both_sides_loses_eligibility(self):
        entry = {"unit_id": "A", "sha": "",
                 "qc_receipt": {"sha": "", "verdict": "PASS",
                                "reviewer": "sonnet-qc-1",
                                "reviewer_route": INDEPENDENT_ROUTE}}
        ok, reason = validate_qc_receipt(entry)
        self.assertFalse(ok)
        self.assertTrue(reason)


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

    def test_malformed_state_store_renders_unknown_never_raises(self):
        result = merge_due({"merge_due": []}, "onb", 1000)
        self.assertEqual(result["state"], UNKNOWN)
        self.assertFalse(result["due"])
        self.assertTrue(result["reason"])

    def test_malformed_parameters_render_unknown_never_raise(self):
        """C5: the clock and the busy window are observed seconds or UNKNOWN."""
        for now, kw in ((1000, {"busy_until": "x"}),
                        ("not-a-number", {}),
                        (1000, {"sweep_interval": "hourly"}),
                        (1000, {"sweep_interval": 0})):
            with self.subTest((now, kw)):
                result = merge_due({"merge_due": {}}, "onb", now, **kw)
                self.assertEqual(result["state"], UNKNOWN)
                self.assertFalse(result["due"])

    def test_malformed_persisted_sweep_renders_unknown_never_raises(self):
        """C5: a stored string sweep is an unobserved clock, not an instant."""
        result = merge_due({"merge_due": {"onb": {"last_sweep": "yesterday"}}},
                           "onb", 1000)
        self.assertEqual(result["state"], UNKNOWN)
        self.assertFalse(result["due"])

    def test_observed_sweep_schedule_is_unchanged(self):
        """C5 inverse: real numbers still schedule exactly as before."""
        state = {}
        first = merge_due(state, "onb", 1000)
        self.assertEqual(first["state"], PROVEN)
        self.assertTrue(first["due"])
        self.assertEqual(first["next_check"], 1000)
        busy = merge_due(state, "onb", 2000, busy_until=5000)
        self.assertEqual(busy["next_check"], 2600)


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

    def test_malformed_consumers_is_unknown_never_eligible(self):
        """A consumer string iterates as chars; that is UNKNOWN, not a green light."""
        result = cleanup_disposition({
            "id": "x", "resource_type": "disposable_scratch",
            "consumers": "nobody", "has_unique_unmerged_work": False})
        self.assertEqual(result["disposition"], UNKNOWN)
        self.assertEqual(result["reason"], "consumer_state_unobserved")

    def test_unrecognised_consumer_state_is_unknown(self):
        result = cleanup_disposition({
            "id": "x", "resource_type": "disposable_scratch",
            "consumers": [{"id": "checker"}],
            "has_unique_unmerged_work": False})
        self.assertEqual(result["disposition"], UNKNOWN)
        self.assertEqual(result["reason"], "consumer_state_unobserved")


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

    def test_deferred_cleanup_blocks_a_proven_receipt(self):
        owner, cohort, gates = self._proven_parts()
        receipt_doc = build_receipt(
            owner=owner, target={"remote": "origin", "before": HEAD_BEFORE,
                                 "after": HEAD_AFTER},
            cohort=cohort, gates=gates,
            proof={"state": PROVEN, "reason": "target_head_observed"},
            cleanup=[{"id": "c", "disposition": "deferred",
                      "reason": "consumer_active:checker"}])
        self.assertEqual(receipt_doc["state"], UNKNOWN)
        self.assertTrue([r for r in receipt_doc["reasons"]
                         if r.startswith("cleanup:c:")])

    def test_verify_receipt_rejects_proven_with_a_deferred_cleanup(self):
        forged = {"artifact": ARTIFACT, "state": PROVEN, "reasons": [],
                  "owner": {"state": PROVEN},
                  "target": {"remote": "origin", "before": "1", "after": "2"},
                  "candidates": [{"unit_id": "A", "sha": SHA_A}],
                  "cohort": {"admit": ["A"], "hold": [], "unknown": []},
                  "gates": [{"unit_id": "A", "state": PROVEN}],
                  "cleanup": [{"id": "c", "disposition": "deferred",
                               "reason": "consumer_active:checker"}],
                  "proof": {"state": PROVEN}}
        ok, reason = verify_receipt(forged)
        self.assertFalse(ok)
        self.assertEqual(reason, "proven receipt carries a deferred cleanup")

    def test_verify_receipt_rejects_candidates_without_exact_sha(self):
        forged = {"artifact": ARTIFACT, "state": PROVEN, "reasons": [],
                  "owner": {"state": PROVEN},
                  "target": {"remote": "origin", "before": "1", "after": "2"},
                  "candidates": [{"unit_id": "A", "sha": None}],
                  "cohort": {"admit": ["A"], "hold": [], "unknown": []},
                  "gates": [{"unit_id": "A", "state": PROVEN}],
                  "proof": {"state": PROVEN}}
        ok, reason = verify_receipt(forged)
        self.assertFalse(ok)
        self.assertTrue(reason)

    def test_build_receipt_refuses_candidates_without_exact_sha(self):
        owner, cohort, gates = self._proven_parts()
        cohort = dict(cohort)
        cohort["candidates"] = [{"unit_id": "A", "sha": None},
                                {"unit_id": "B", "sha": "zzz"}]
        receipt_doc = build_receipt(
            owner=owner, target={"remote": "origin", "before": HEAD_BEFORE,
                                 "after": HEAD_AFTER},
            cohort=cohort, gates=gates,
            proof={"state": PROVEN, "reason": "target_head_observed"})
        self.assertNotEqual(receipt_doc["state"], PROVEN)
        self.assertTrue([r for r in receipt_doc["reasons"]
                         if r.startswith("candidate_sha")])

    def test_malformed_receipt_inputs_render_unknown_never_raise(self):
        receipt_doc = build_receipt(owner="x", target={}, cohort={},
                                    gates="x", named_repairs="y",
                                    cleanup="z", proof={})
        self.assertEqual(receipt_doc["state"], UNKNOWN)
        self.assertTrue(receipt_doc["reasons"])

    def test_verify_receipt_rejects_malformed_collections_never_raises(self):
        """C7: a malformed collection is a shape failure, never an exception."""
        base = {"artifact": ARTIFACT, "state": PROVEN, "reasons": [],
                "owner": {"state": PROVEN},
                "target": {"remote": "origin", "before": "1", "after": "2"},
                "candidates": [{"unit_id": "A", "sha": SHA_A}],
                "cohort": {"admit": ["A"], "hold": [], "unknown": []},
                "gates": [{"unit_id": "A", "state": PROVEN}],
                "named_repairs": [], "cleanup": [], "proof": {"state": PROVEN}}
        for field, bad in (("cleanup", "z"), ("gates", "x"),
                           ("named_repairs", "y"), ("candidates", "w"),
                           ("cleanup", ["not-a-record"]), ("gates", ["junk"]),
                           ("named_repairs", ["junk"]), ("proof", "p")):
            with self.subTest((field, bad)):
                forged = dict(base)
                forged[field] = bad
                ok, reason = verify_receipt(forged)
                self.assertFalse(ok)
                self.assertTrue(reason)

    def test_verify_receipt_accepts_the_honest_receipt(self):
        """C7 inverse: the well-formed PROVEN receipt still verifies."""
        owner, cohort, gates = self._proven_parts()
        receipt_doc = build_receipt(
            owner=owner, target={"remote": "origin", "before": HEAD_BEFORE,
                                 "after": HEAD_AFTER},
            cohort=cohort, gates=gates,
            proof={"state": PROVEN, "reason": "target_head_observed"})
        ok, reason = verify_receipt(receipt_doc)
        self.assertTrue(ok, reason)


class ThirdRepairProofTests(unittest.TestCase):
    """QC round 3: no unobserved fact becomes a name, a proof or a green light.

    Every case here was reproduced on the parent ``d32103b2f`` and on the
    reviewed commit ``7a965c7f4`` before this repair. The rule is the one
    this file already pins for ``consumers`` (see
    ``test_malformed_consumers_is_unknown_never_eligible``): a value read as
    a collection, an identity or a proof is observed, or the answer is
    ``UNKNOWN`` — never a ``str()``-coerced default.
    """

    def test_a_remote_merge_proof_id_that_is_no_receipt_is_no_proof(self):
        """D-1: a proof-id collection is observed, or there is no proof."""
        base = {"id": "m", "resource_type": "merged_worktree", "consumers": [],
                "has_unique_unmerged_work": False, "clean_state": "CLEAN"}
        for shape in ("junk", [""], [None], [7], 1, {"p": 1}, [], None):
            with self.subTest(shape):
                result = cleanup_disposition(
                    dict(base, remote_merge_proof_ids=shape))
                self.assertEqual(result["disposition"], UNKNOWN)
                self.assertNotEqual(result["reason"], "clean_merged_tree")
        control = cleanup_disposition(
            dict(base, remote_merge_proof_ids=["M-1"]))
        self.assertEqual((control["disposition"], control["reason"]),
                         ("eligible", "clean_merged_tree"))
        contrast = cleanup_disposition({
            "id": "x", "resource_type": "disposable_scratch",
            "consumers": "nobody", "has_unique_unmerged_work": False})
        self.assertEqual(contrast["disposition"], UNKNOWN)

    def test_an_unobserved_cleanup_id_is_never_a_record_id(self):
        """D-1: ``5`` is not a resource id, and str() must not invent one."""
        result = cleanup_disposition({
            "id": 5, "resource_type": "disposable_scratch",
            "consumers": [], "has_unique_unmerged_work": False})
        self.assertEqual(result["disposition"], UNKNOWN)
        self.assertEqual(result["id"], "")
        self.assertEqual(result["reason"], "resource_id_unobserved")

    def test_an_unobserved_file_entry_is_never_a_path(self):
        """D-2: ``str(f)`` on a ``None`` file entry invents ``'None'``."""
        for entry in ([None], [5], [{}], [[]], [False], [b"x"]):
            with self.subTest(entry):
                report = evaluate_cohort([
                    {"unit_id": "A", "sha": SHA_A, "files": entry,
                     "depends_on": [], "state": "green"}])
                self.assertEqual(report["state"], UNKNOWN)
                self.assertEqual([e["reason"] for e in report["unknown"]],
                                 ["unit_files_malformed"])
        control = evaluate_cohort([
            {"unit_id": "A", "sha": SHA_A, "files": ["a.py"],
             "depends_on": [], "state": "green"}])
        self.assertEqual(control["state"], ADMITTED)

    def test_an_unobserved_dependency_or_repo_entry_is_never_a_name(self):
        """D-2: a dependency id and a repository name are observed strings."""
        dep = evaluate_cohort([
            {"unit_id": "A", "sha": SHA_A, "files": ["a.py"],
             "depends_on": [None], "state": "green"}])
        self.assertEqual(dep["state"], UNKNOWN)
        self.assertEqual([e["reason"] for e in dep["unknown"]],
                         ["unit_depends_on_malformed"])
        repo = evaluate_cohort([
            {"unit_id": "A", "sha": SHA_A, "files": ["a.py"],
             "depends_on": [], "state": "green", "repo": 5}])
        self.assertEqual(repo["state"], UNKNOWN)
        self.assertEqual([e["reason"] for e in repo["unknown"]],
                         ["unit_repo_malformed"])
        control = evaluate_cohort([
            {"unit_id": "A", "sha": SHA_A, "files": ["a.py"],
             "depends_on": [], "state": "green", "repo": "cc"}])
        self.assertEqual(control["state"], ADMITTED)

    def test_an_unrecognised_unit_state_is_unknown_never_not_red(self):
        """D-3: a wrong-typed state is unobserved, not silently "not red"."""
        for state in ("", 5, True, [], {}, "RED", "red ", "greenish"):
            with self.subTest(state):
                report = evaluate_cohort([
                    {"unit_id": "A", "sha": SHA_A, "files": ["a.py"],
                     "depends_on": [], "state": state}])
                self.assertEqual(report["state"], UNKNOWN)
                self.assertEqual(report["admit"], [])
                self.assertEqual([e["reason"] for e in report["unknown"]],
                                 ["unit_state_malformed"])
        red = evaluate_cohort([unit("A", SHA_A, files=["a.py"], state="red")])
        self.assertEqual(red["state"], HELD)
        green = evaluate_cohort([unit("A", SHA_A, files=["a.py"])])
        self.assertEqual(green["state"], ADMITTED)

    def test_a_receipt_target_position_must_be_an_observed_object_id(self):
        """D-4: ``"zz"`` and ``1``/``2`` are not remote positions."""
        forged = {"artifact": ARTIFACT, "state": PROVEN, "reasons": [],
                  "owner": {"state": PROVEN},
                  "target": {"remote": "origin", "before": "zz", "after": "zz"},
                  "candidates": [{"unit_id": "A", "sha": SHA_A}],
                  "cohort": {"admit": ["A"], "hold": [], "unknown": []},
                  "gates": [{"unit_id": "A", "state": PROVEN}],
                  "named_repairs": [], "cleanup": [],
                  "proof": {"state": PROVEN}}
        ok, reason = verify_receipt(forged)
        self.assertFalse(ok)
        self.assertEqual(reason, "proven receipt lacks target before/after")
        ok, reason = verify_receipt(dict(forged, target={
            "remote": "o", "before": 1, "after": 2}))
        self.assertFalse(ok)
        self.assertEqual(reason, "proven receipt lacks target before/after")
        control = verify_receipt(dict(
            forged, target={"remote": "origin", "before": "1", "after": "2"},
            gates=[{"unit_id": "A", "state": UNKNOWN, "reason": "x"}]))
        self.assertEqual(control,
                         (False, "proven receipt carries a non-proven gate"))
        built = build_receipt(
            owner={"state": PROVEN},
            target={"remote": "origin", "before": "zz", "after": "zz"},
            cohort={"admit": ["A"], "order": ["A"], "hold": [], "unknown": [],
                    "candidates": [{"unit_id": "A", "sha": SHA_A}]},
            gates=[{"unit_id": "A", "state": PROVEN}],
            proof={"state": PROVEN, "reason": "target_head_observed"})
        self.assertEqual(built["state"], UNKNOWN)
        self.assertIn("target_before_unobserved", built["reasons"])
        self.assertIn("target_after_unobserved", built["reasons"])

    def test_a_named_repair_identity_and_blob_id_must_be_observed(self):
        """D-5: ``None == None`` is not content equivalence."""
        observation = {"remote": "origin", "target_ref": "refs/heads/main",
                       "observed_head": HEAD_AFTER, "method": "ancestry",
                       "contains_sha": True}
        for repair_id in (5, ["r"], True):
            with self.subTest(repair_id):
                result = prove_named_repair(
                    {"repair_id": repair_id, "sha": SHA_R}, observation)
                self.assertEqual(result["state"], UNKNOWN)
        for value in (9, ["r"], True):
            with self.subTest(value):
                ref = prove_named_repair(
                    {"repair_id": "R1", "sha": SHA_R},
                    dict(observation, target_ref=value))
                self.assertEqual(ref["state"], UNKNOWN)
                head = prove_named_repair(
                    {"repair_id": "R1", "sha": SHA_R},
                    dict(observation, observed_head=value))
                self.assertEqual(head["state"], UNKNOWN)
        nulls = prove_named_repair(
            {"repair_id": "R1", "sha": SHA_R, "files": {"a.py": None}},
            {"remote": "origin", "target_ref": "refs/heads/main",
             "observed_head": HEAD_AFTER, "method": "squash",
             "tree": {"a.py": None}})
        self.assertEqual(nulls["state"], UNKNOWN)
        self.assertEqual(nulls["reason"], "repair_content_malformed")
        control = prove_named_repair(
            {"repair_id": "R1", "sha": SHA_R, "files": {"a.py": "blob-a"}},
            {"remote": "origin", "target_ref": "refs/heads/main",
             "observed_head": HEAD_AFTER, "method": "squash",
             "tree": {"a.py": "blob-a"}})
        self.assertEqual(control["state"], PROVEN)

    def test_a_built_receipt_is_self_consistent_never_reasonless_unknown(self):
        """D-6: a fully proven input set is PROVEN, and an UNKNOWN names why."""
        cohort = {"admit": ["A"], "order": ["A"], "hold": [], "unknown": [],
                  "candidates": [{"unit_id": "A", "sha": SHA_A}]}
        built = build_receipt(
            owner={"state": PROVEN},
            target={"remote": "origin", "before": HEAD_BEFORE,
                    "after": HEAD_AFTER},
            cohort=cohort, gates=[{"unit_id": "A", "state": PROVEN}],
            proof={"state": PROVEN, "reason": "target_head_observed"})
        self.assertEqual(built["state"], PROVEN)
        self.assertEqual(built["reasons"], [])
        self.assertEqual(verify_receipt(built), (True, ""))
        unknown = build_receipt(
            owner={"state": PROVEN},
            target={"remote": "origin", "before": HEAD_BEFORE,
                    "after": HEAD_AFTER},
            cohort=cohort, gates=[{"unit_id": "A", "state": "JUNK"}],
            proof={"state": PROVEN, "reason": "target_head_observed"})
        self.assertEqual(unknown["state"], UNKNOWN)
        self.assertTrue(unknown["reasons"])
        self.assertEqual(verify_receipt(unknown), (True, ""))

    def test_an_unobserved_gate_identity_or_check_name_never_proves(self):
        """D-7: the identity and the check name a proof carries are observed."""
        for unit_id in (5, None, ["A"], True):
            with self.subTest(unit_id):
                result = exact_independent_gate(
                    {"unit_id": unit_id, "sha": SHA_A}, receipt(SHA_A))
                self.assertEqual(result["state"], UNKNOWN)
                self.assertEqual(result["reason"], "unit_id_unobserved")
        for bad in (receipt(SHA_A, checks=[{"name": None, "status": "pass"}]),
                    receipt(SHA_A, checks={None: "pass"}),
                    receipt(SHA_A, checks=[{"name": "unit", "status": 5}]),
                    receipt(SHA_A, checks=["junk"])):
            with self.subTest(bad["checks"]):
                result = exact_independent_gate(unit("A", SHA_A), bad)
                self.assertEqual(result["state"], UNKNOWN)
                self.assertEqual(result["reason"],
                                 "required_check_results_malformed")
        control = exact_independent_gate(unit("A", SHA_A), receipt(SHA_A))
        self.assertEqual(control["state"], PROVEN)


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
