#!/usr/bin/env python3
"""S75-T36: incorporation proof, fixture only.

No git process, no network, no credential, no client data: the transport is a
local ancestry map. Run: python3 test_incorporation_proof_s75_t36.py
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CONTROL = os.path.dirname(HERE)
if CONTROL not in sys.path:
    sys.path.insert(0, CONTROL)

from incorporation_proof import (  # noqa: E402
    Check, ProofRefused, Target, is_sha40, proof_is_current,
    proofs_affected_by, refresh_proof, validate_proof, verify_incorporation,
)

ONB = "openclaw-onboarding"
N999 = "999-setup"


def sha(n):
    return f"{n:040x}"


BASE = sha(0xB0)
CANDIDATE = sha(0xC0)
MERGE = sha(0xEE)
MAIN_AFTER = sha(0xA1)
MAIN_LATER = sha(0xA2)


class FakeGit:
    """A local ancestry map. ``parents[child]`` lists the child's parents."""

    def __init__(self, target, parents=None, head=None):
        self.target = target
        self.parents = dict(parents or {})
        self._head = head

    def remote_head(self):
        return self._head

    def is_ancestor(self, ancestor, descendant):
        if ancestor == descendant:
            return True
        seen = set()
        stack = [descendant]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            for parent in self.parents.get(node, ()):
                if parent == ancestor:
                    return True
                stack.append(parent)
        return False


def landed_git(head=None):
    """candidate and base both sit beneath the merge, which sits beneath main."""
    parents = {
        CANDIDATE: [BASE],
        MERGE: [CANDIDATE, BASE],
        MAIN_AFTER: [MERGE],
        MAIN_LATER: [MAIN_AFTER],
    }
    return FakeGit(Target(ONB), parents, head if head is not None else MERGE)


def passing_checks():
    return [Check("unit-suite", "PASS", cases=31),
            Check("gate-8.5", "PASS")]


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="s75-t36-proof-")

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def verify(self, git=None, **overrides):
        kwargs = {
            "unit": "S75-T36",
            "candidate": CANDIDATE,
            "base": BASE,
            "merge_commit": MERGE,
            "checks": passing_checks(),
            "observed_at": "2026-10-25T20:00:00Z",
        }
        kwargs.update(overrides)
        return verify_incorporation(git or landed_git(), **kwargs)


class CorrectTarget(Base):
    def test_proof_correlates_candidate_base_checks_on_the_named_target(self):
        proof = self.verify()
        self.assertTrue(proof.incorporated)
        self.assertEqual(proof.candidate, CANDIDATE)
        self.assertEqual(proof.base, BASE)
        self.assertEqual(proof.merge_commit, MERGE)
        self.assertEqual([c.name for c in proof.checks],
                         ["unit-suite", "gate-8.5"])
        self.assertEqual(proof.checks[0].cases, 31)
        self.assertEqual(proof.target.repository, ONB)
        self.assertEqual(proof.remote_head, MERGE)
        self.assertTrue(proof_is_current(proof, MERGE))

    def test_proof_round_trips_through_its_on_disk_form(self):
        proof = self.verify()
        restored = validate_proof(proof.as_dict())
        self.assertEqual(restored.digest, proof.digest)
        self.assertEqual(restored.target.repository, ONB)
        self.assertEqual(len(restored.checks), 2)

    def test_digest_ignores_observation_time_so_identity_is_stable(self):
        first = self.verify(observed_at="2026-10-25T20:00:00Z")
        second = self.verify(observed_at="2026-10-25T23:59:00Z")
        self.assertEqual(first.digest, second.digest)
        refreshed = refresh_proof(landed_git(MAIN_AFTER), first, "2026-10-26T00:00:00Z")
        self.assertEqual(refreshed.candidate, first.candidate)
        self.assertEqual(refreshed.base, first.base)
        self.assertEqual(refreshed.refreshed_from, first.digest)


class BranchMerelyExists(Base):
    def test_merge_bypassing_remote_main_is_refused(self):
        git = landed_git(head=sha(0xFF))  # a head that does not contain the merge
        with self.assertRaises(ProofRefused) as caught:
            self.verify(git)
        self.assertEqual(caught.exception.reason, "merge-not-on-remote")

    def test_merge_that_does_not_contain_the_candidate_is_refused(self):
        parents = {MERGE: [BASE], MAIN_AFTER: [MERGE]}
        git = FakeGit(Target(ONB), parents, MERGE)
        with self.assertRaises(ProofRefused) as caught:
            self.verify(git)
        self.assertEqual(caught.exception.reason, "candidate-not-in-merge")

    def test_checks_that_ran_against_a_foreign_base_are_refused(self):
        other_base = sha(0xBA)
        parents = {CANDIDATE: [other_base], MERGE: [CANDIDATE, other_base],
                   MAIN_AFTER: [MERGE]}
        git = FakeGit(Target(ONB), parents, MERGE)
        with self.assertRaises(ProofRefused) as caught:
            self.verify(git, base=BASE)
        self.assertEqual(caught.exception.reason, "base-not-ancestor")


class ChecksAreEvidence(Base):
    def test_a_proof_with_no_checks_is_refused(self):
        with self.assertRaises(ProofRefused) as caught:
            self.verify(checks=[])
        self.assertEqual(caught.exception.reason, "no-checks")

    def test_a_failing_check_is_refused_and_named(self):
        with self.assertRaises(ProofRefused) as caught:
            self.verify(checks=[Check("unit-suite", "PASS"),
                                Check("gate-8.5", "FAIL")])
        self.assertEqual(caught.exception.reason, "checks-failed")
        self.assertIn("gate-8.5", caught.exception.detail)

    def test_an_outcome_that_is_not_a_verdict_is_not_a_check(self):
        with self.assertRaises(ValueError):
            Check("unit-suite", "probably-fine")

    def test_malformed_shas_are_refused_by_field(self):
        for field, bad, reason in (
                ("candidate", "C0FFEE", "candidate-sha"),
                ("base", "", "base-sha"),
                ("merge_commit", "z" * 40, "merge-sha")):
            with self.subTest(field=field):
                with self.assertRaises(ProofRefused) as caught:
                    self.verify(**{field: bad})
                self.assertEqual(caught.exception.reason, reason)

    def test_sha_predicate_accepts_only_lowercase_forty_hex(self):
        self.assertTrue(is_sha40(BASE))
        self.assertFalse(is_sha40(BASE.upper()))
        self.assertFalse(is_sha40(BASE[:39]))


class WrongTarget(Base):
    def test_a_proof_from_another_repository_never_satisfies_this_one(self):
        proof = self.verify()
        other = FakeGit(Target(N999), landed_git().parents, MERGE)
        with self.assertRaises(ProofRefused) as caught:
            refresh_proof(other, proof, "2026-10-26T00:00:00Z")
        self.assertEqual(caught.exception.reason, "wrong-target")
        self.assertIn(ONB, caught.exception.detail)

    def test_a_transport_without_a_target_identity_is_refused(self):
        class Anonymous:
            def remote_head(self):
                return MERGE

            def is_ancestor(self, ancestor, descendant):
                return True

        with self.assertRaises(ProofRefused) as caught:
            verify_incorporation(Anonymous(), unit="S75-T36",
                                 candidate=CANDIDATE, base=BASE,
                                 merge_commit=MERGE, checks=passing_checks())
        self.assertEqual(caught.exception.reason, "wrong-target")

    def test_a_record_that_does_not_claim_a_landing_is_not_evidence(self):
        document = self.verify().as_dict()
        document["incorporated"] = False
        with self.assertRaises(ProofRefused) as caught:
            validate_proof(document)
        self.assertEqual(caught.exception.reason, "not-incorporated")

    def test_an_incomplete_record_is_refused(self):
        document = self.verify().as_dict()
        document.pop("checks")
        with self.assertRaises(ProofRefused) as caught:
            validate_proof(document)
        self.assertEqual(caught.exception.reason, "proof-incomplete")
        self.assertIn("checks", caught.exception.detail)


class MovingMain(Base):
    def test_a_moved_branch_makes_the_proof_stale_not_wrong(self):
        proof = self.verify()
        self.assertTrue(proof_is_current(proof, MERGE))
        self.assertFalse(proof_is_current(proof, MAIN_AFTER))

    def test_refresh_reproves_against_the_new_head_and_keeps_the_old_digest(self):
        proof = self.verify()
        refreshed = refresh_proof(landed_git(MAIN_AFTER), proof,
                                  "2026-10-26T00:00:00Z")
        self.assertEqual(refreshed.remote_head, MAIN_AFTER)
        self.assertNotEqual(refreshed.remote_head, proof.remote_head)
        self.assertEqual(refreshed.refreshed_from, proof.digest)
        self.assertTrue(proof_is_current(refreshed, MAIN_AFTER))
        self.assertEqual(refreshed.digest, validate_proof(refreshed.as_dict()).digest)

    def test_refresh_refuses_when_the_landing_left_the_branch(self):
        proof = self.verify()
        rewritten = FakeGit(Target(ONB), {MAIN_LATER: [sha(0x99)]}, MAIN_LATER)
        with self.assertRaises(ProofRefused) as caught:
            refresh_proof(rewritten, proof)
        self.assertEqual(caught.exception.reason, "merge-not-on-remote")

    def test_only_proofs_whose_own_target_moved_are_affected(self):
        onb = self.verify()
        n999 = verify_incorporation(
            FakeGit(Target(N999), landed_git().parents, MERGE),
            unit="S75-T37", candidate=CANDIDATE, base=BASE,
            merge_commit=MERGE, checks=passing_checks())
        affected = proofs_affected_by([onb, n999], {ONB: MAIN_AFTER})
        self.assertEqual([p.target.repository for p in affected], [ONB])
        self.assertEqual(proofs_affected_by([onb, n999], {ONB: MERGE}), [])
        self.assertEqual(proofs_affected_by([onb], {}), [])

    def test_same_landing_ignores_base_and_checks_but_not_the_merge_commit(self):
        first = self.verify()
        same = self.verify(checks=[Check("other-gate", "PASS")])
        self.assertTrue(first.same_landing(same))
        moved = verify_incorporation(landed_git(MAIN_AFTER), unit="S75-T36",
                                     candidate=CANDIDATE, base=BASE,
                                     merge_commit=MAIN_AFTER,
                                     checks=passing_checks())
        self.assertFalse(first.same_landing(moved))

    def test_refused_verification_leaves_no_proof_behind(self):
        git = landed_git(head=sha(0xFF))
        with self.assertRaises(ProofRefused):
            self.verify(git)
        self.assertEqual(os.listdir(self.temp), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
