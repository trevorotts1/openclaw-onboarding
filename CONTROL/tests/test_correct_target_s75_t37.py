#!/usr/bin/env python3
"""S75-T37: correct-target incorporation, fixture only.

No git process, no network, no credential, no client data. Two healthy flavor
targets, one wrong one, and the local-only case this unit exists to name.
Run: python3 -I test_correct_target_s75_t37.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CONTROL = os.path.dirname(HERE)
if CONTROL not in sys.path:
    sys.path.insert(0, CONTROL)

import correct_target as CT  # noqa: E402

ONB = "openclaw-onboarding"
ONB_URLS = ("https://github.com/trevorotts1/openclaw-onboarding.git",
            "git@github.com:trevorotts1/openclaw-onboarding.git")
N999 = "999-setup"
N999_URLS = ("https://github.com/trevorotts1/999-setup.git",
             "git@github.com:trevorotts1/999-setup.git")


def sha(n):
    return f"{n:040x}"


BASE = sha(0xB0)
CANDIDATE = sha(0xC0)
MERGE = sha(0xEE)
MAIN_AFTER = sha(0xA1)
MAIN_LATER = sha(0xA2)
MERGE2 = sha(0xEF)
MAIN_AFTER_BOTH = sha(0xA3)
UNRELATED = sha(0x77)

PARENTS = {
    CANDIDATE: [BASE],
    MERGE: [CANDIDATE, BASE],
    MERGE2: [CANDIDATE, BASE],
    MAIN_AFTER: [MERGE],
    MAIN_LATER: [MAIN_AFTER],
    MAIN_AFTER_BOTH: [MAIN_AFTER, MERGE2],
}


class FakeGit:
    """Either remote is a local ancestry map plus its configured URLs."""

    def __init__(self, urls, remote=None, local=None):
        self.urls = dict(urls or {})
        self.remote = remote
        self.local = local

    def remote_urls(self, remote):
        if remote not in self.urls:
            raise KeyError(remote)
        return list(self.urls[remote])

    def remote_head(self, remote, branch):
        return self.remote

    def local_head(self, branch):
        return self.local

    def is_ancestor(self, ancestor, descendant):
        if ancestor == descendant:
            return True
        seen, stack = set(), [descendant]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            for parent in PARENTS.get(node, ()):
                if parent == ancestor:
                    return True
                stack.append(parent)
        return False


def onb(remote=MAIN_AFTER, local=MAIN_AFTER):
    return FakeGit({"origin": ONB_URLS}, remote, local)


def int999(remote=MAIN_AFTER, local=MAIN_AFTER):
    return FakeGit({"origin": N999_URLS}, remote, local)


def intended(repository=ONB, urls=ONB_URLS, branch="main"):
    return CT.IntendedTarget(repository, "origin", branch, urls)


def passing():
    return [{"name": "unit-suite", "outcome": "PASS", "cases": 41},
            {"name": "gate-8.5", "outcome": "PASS"}]


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="s75-t37-target-")
        self.journal = os.path.join(self.temp, "evidence", "landings.json")

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def prove(self, git=None, target=None, **overrides):
        kwargs = {
            "unit": "S75-T37",
            "candidate": CANDIDATE,
            "base": BASE,
            "merge_commit": MERGE,
            "checks": passing(),
            "observed_at": "2026-10-26T00:00:00Z",
        }
        kwargs.update(overrides)
        return CT.prove_landing(git or onb(), target or intended(), **kwargs)

    def refused(self, reason, git=None, target=None, **overrides):
        with self.assertRaises(CT.TargetRefused) as caught:
            self.prove(git=git, target=target, **overrides)
        self.assertEqual(caught.exception.reason, reason,
                         f"expected {reason}, got {caught.exception}")
        return caught.exception


class RemoteUrlIdentity(unittest.TestCase):
    def test_one_repository_has_one_identity_across_spellings(self):
        expected = "github.com/trevorotts1/openclaw-onboarding"
        for spelling in ("https://github.com/trevorotts1/openclaw-onboarding.git",
                         "https://github.com/trevorotts1/openclaw-onboarding/",
                         "ssh://git@github.com/trevorotts1/openclaw-onboarding.git",
                         "git@github.com:trevorotts1/openclaw-onboarding.git",
                         "github.com/trevorotts1/openclaw-onboarding"):
            self.assertEqual(CT.normalise_remote_url(spelling), expected, spelling)

    def test_two_repositories_never_share_an_identity(self):
        self.assertNotEqual(
            CT.normalise_remote_url(ONB_URLS[0]),
            CT.normalise_remote_url(N999_URLS[0]))

    def test_a_bare_name_is_not_a_witness(self):
        self.assertIsNone(CT.normalise_remote_url("openclaw-onboarding"))
        self.assertIsNone(CT.normalise_remote_url(""))
        self.assertIsNone(CT.normalise_remote_url(None))

    def test_an_intended_target_without_a_url_is_rejected(self):
        with self.assertRaises(ValueError):
            CT.IntendedTarget(ONB, accepted_remotes=())
        with self.assertRaises(ValueError):
            CT.IntendedTarget(ONB, accepted_remotes=("openclaw-onboarding",))


class CorrectTarget(Base):
    def test_landing_is_proven_on_the_intended_repository_and_remote_main(self):
        proof = self.prove()
        self.assertEqual(proof.unit, "S75-T37")
        self.assertEqual(proof.candidate, CANDIDATE)
        self.assertEqual(proof.base, BASE)
        self.assertEqual(proof.merge_commit, MERGE)
        self.assertEqual(proof.target.repository, ONB)
        self.assertEqual(proof.target.branch, "main")
        self.assertEqual(proof.remote_url,
                         "github.com/trevorotts1/openclaw-onboarding")
        self.assertEqual(proof.remote_head, MAIN_AFTER)
        self.assertEqual(proof.local_head, MAIN_AFTER)
        self.assertEqual(set(proof.clauses),
                         {"intended_repository", "remote_main_contains_merge",
                          "candidate_in_merge", "base_beneath_merge",
                          "checks_present_passing", "not_local_only"})
        self.assertTrue(all(proof.clauses.values()))

    def test_proof_names_the_full_target_so_it_cannot_float_to_another_repo(self):
        document = self.prove().as_dict()
        self.assertEqual(document["schema"], "s75.correct-target-proof/v1")
        self.assertEqual(document["target"]["repository"], ONB)
        self.assertEqual(document["target"]["remote"], "origin")
        self.assertEqual(document["target"]["branch"], "main")
        self.assertIn("github.com/trevorotts1/openclaw-onboarding",
                      document["target"]["accepted_remotes"])
        self.assertEqual(document["remote_url"],
                         "github.com/trevorotts1/openclaw-onboarding")

    def test_digest_is_the_landing_not_the_observation_time(self):
        first = self.prove(observed_at="2026-10-26T00:00:00Z")
        second = self.prove(observed_at="2026-10-26T06:00:00Z")
        self.assertEqual(first.digest, second.digest)

    def test_a_moved_remote_main_still_proves_the_same_landing(self):
        proof = self.prove(git=onb(remote=MAIN_LATER, local=MAIN_LATER))
        self.assertEqual(proof.remote_head, MAIN_LATER)
        self.assertEqual(proof.merge_commit, MERGE)


class WrongTarget(Base):
    def test_a_foreign_remote_url_is_refused_as_wrong_target(self):
        self.refused("wrong-target", git=int999())

    def test_the_repository_name_cannot_override_the_observed_url(self):
        # A transport that calls itself openclaw-onboarding but reads 999-setup.
        lying = FakeGit({"origin": N999_URLS}, MAIN_AFTER, MAIN_AFTER)
        self.refused("wrong-target", git=lying, target=intended())

    def test_an_unparseable_or_absent_remote_is_not_a_witness(self):
        self.refused("no-remote", git=FakeGit({"origin": ["not a url"]}))
        self.refused("no-remote", git=FakeGit({"upstream": ONB_URLS}))

    def test_wrong_target_is_refused_before_any_ancestry_is_examined(self):
        # Even a merge that is nowhere must report the target problem first.
        self.refused("wrong-target", git=FakeGit({"origin": N999_URLS}, None, None))


class LocalOnlyMerge(Base):
    def test_a_merge_in_local_history_but_not_remote_main_is_local_only(self):
        error = self.refused("local-only",
                             git=onb(remote=BASE, local=MAIN_AFTER))
        self.assertIn("local", str(error))

    def test_an_absent_remote_branch_is_local_only(self):
        self.refused("local-only", git=onb(remote=None, local=MAIN_AFTER))

    def test_a_merge_that_is_nowhere_is_not_a_landing(self):
        self.refused("merge-not-on-remote",
                     git=onb(remote=BASE, local=BASE))

    def test_local_only_and_wrong_target_are_distinguishable(self):
        wrong = CT.TargetRefused("wrong-target", "")
        local = CT.TargetRefused("local-only", "")
        self.assertNotEqual(wrong.reason, local.reason)
        self.assertNotEqual(str(wrong), str(local))

    def test_a_merge_that_does_not_contain_the_candidate_is_refused(self):
        self.refused("candidate-not-in-merge",
                     merge_commit=UNRELATED,
                     git=onb(remote=MAIN_AFTER, local=MAIN_AFTER))

    def test_a_base_that_is_not_beneath_the_merge_is_refused(self):
        self.refused("base-not-ancestor", base=UNRELATED)


class ChecksAreNotMoods(Base):
    def test_no_checks_is_not_a_proof(self):
        self.refused("no-checks", checks=[])

    def test_one_failed_check_refuses_the_landing(self):
        self.refused("checks-failed",
                     checks=[{"name": "unit-suite", "outcome": "PASS"},
                             {"name": "gate-8.5", "outcome": "FAIL"}])

    def test_an_outcome_that_is_not_pass_or_fail_is_refused(self):
        self.refused("proof-incomplete",
                     checks=[{"name": "unit-suite", "outcome": "probably"}])


class N999NeedsNoOnbFacet(Base):
    """The row's note: N999 need not wait for ONB fixture facets."""

    def test_n999_proves_on_its_own_transport_and_urls(self):
        proof = self.prove(git=int999(),
                           target=intended(N999, N999_URLS))
        self.assertEqual(proof.target.repository, N999)
        self.assertEqual(proof.remote_url,
                         "github.com/trevorotts1/999-setup")
        self.assertTrue(all(proof.clauses.values()))

    def test_an_onb_intent_cannot_be_proven_on_an_n999_transport(self):
        self.refused("wrong-target", git=int999(), target=intended())

    def test_an_n999_intent_cannot_be_proven_on_an_onb_transport(self):
        self.refused("wrong-target", git=onb(),
                     target=intended(N999, N999_URLS))


class ReconcileOnce(Base):
    def test_first_reconcile_writes_exactly_one_landing(self):
        status, record, wrote = CT.reconcile_once(self.journal, self.prove())
        self.assertEqual(status, CT.RECONCILED)
        self.assertTrue(wrote)
        self.assertEqual(record["merge_commit"], MERGE)
        with open(self.journal, "r", encoding="utf-8") as handle:
            document = json.load(handle)
        self.assertEqual(document["schema"], "s75.landing-journal/v1")
        self.assertEqual(len(document["landings"]), 1)

    def test_repeated_reconcile_of_the_same_uncertain_merge_writes_nothing(self):
        CT.reconcile_once(self.journal, self.prove())
        with open(self.journal, "rb") as handle:
            before = handle.read()
        for attempt in range(3):
            status, record, wrote = CT.reconcile_once(self.journal, self.prove())
            self.assertEqual(status, CT.ALREADY_RECONCILED, f"attempt {attempt}")
            self.assertFalse(wrote)
            self.assertEqual(record["merge_commit"], MERGE)
        with open(self.journal, "rb") as handle:
            self.assertEqual(handle.read(), before,
                             "idempotent reconcile must not rewrite the journal")
        with open(self.journal, "r", encoding="utf-8") as handle:
            self.assertEqual(len(json.load(handle)["landings"]), 1)

    def test_a_different_landing_for_the_same_unit_is_refused_not_appended(self):
        CT.reconcile_once(self.journal, self.prove())
        with open(self.journal, "rb") as handle:
            before = handle.read()
        other = self.prove(git=onb(remote=MAIN_AFTER_BOTH, local=MAIN_AFTER_BOTH),
                           merge_commit=MERGE2)
        with self.assertRaises(CT.TargetRefused) as caught:
            CT.reconcile_once(self.journal, other)
        self.assertEqual(caught.exception.reason, "landing-conflict")
        with open(self.journal, "rb") as handle:
            self.assertEqual(handle.read(), before,
                             "a conflicting landing must leave the journal untouched")

    def test_a_landing_for_a_foreign_target_is_refused_into_this_journal(self):
        CT.reconcile_once(self.journal, self.prove())
        foreign = self.prove(git=int999(), target=intended(N999, N999_URLS))
        with self.assertRaises(CT.TargetRefused) as caught:
            CT.reconcile_once(self.journal, foreign)
        self.assertEqual(caught.exception.reason, "landing-conflict")

    def test_two_units_accumulate_two_distinct_landings(self):
        CT.reconcile_once(self.journal, self.prove())
        second = self.prove(unit="S75-T38")
        status, _record, wrote = CT.reconcile_once(self.journal, second)
        self.assertEqual(status, CT.RECONCILED)
        self.assertTrue(wrote)
        with open(self.journal, "r", encoding="utf-8") as handle:
            landings = json.load(handle)["landings"]
        self.assertEqual([row["unit"] for row in landings],
                         ["S75-T37", "S75-T38"])

    def test_a_malformed_journal_is_refused_rather_than_overwritten(self):
        os.makedirs(os.path.dirname(self.journal), exist_ok=True)
        with open(self.journal, "w", encoding="utf-8") as handle:
            handle.write("{ not json")
        with self.assertRaises(CT.TargetRefused) as caught:
            CT.reconcile_once(self.journal, self.prove())
        self.assertEqual(caught.exception.reason, "journal-malformed")
        with open(self.journal, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "{ not json")

    def test_a_claim_without_a_landing_proof_is_refused(self):
        with self.assertRaises(CT.TargetRefused) as caught:
            CT.reconcile_once(self.journal, {"unit": "S75-T37"})
        self.assertEqual(caught.exception.reason, "proof-incomplete")


if __name__ == "__main__":
    unittest.main(verbosity=2)
