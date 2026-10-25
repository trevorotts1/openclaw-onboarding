#!/usr/bin/env python3
"""S75-T36: atomic queue acknowledgement, fixture only.

No git process, no network, no credential, no client data. Run:
python3 test_queue_ack_s75_t36.py
"""
import hashlib
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

import queue_ack as QA  # noqa: E402
from incorporation_proof import (  # noqa: E402
    Check, Target, verify_incorporation,
)

ONB = "openclaw-onboarding"
N999 = "999-setup"


def sha(n):
    return f"{n:040x}"


BASE = sha(0xB0)
CANDIDATE = sha(0xC0)
MERGE = sha(0xEE)
MAIN_AFTER = sha(0xA1)
OTHER_MERGE = sha(0xEF)


class FakeGit:
    def __init__(self, target, parents=None, head=None):
        self.target = target
        self.parents = dict(parents or {})
        self._head = head

    def remote_head(self):
        return self._head

    def is_ancestor(self, ancestor, descendant):
        if ancestor == descendant:
            return True
        seen, stack = set(), [descendant]
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


PARENTS = {
    CANDIDATE: [BASE],
    MERGE: [CANDIDATE, BASE],
    OTHER_MERGE: [CANDIDATE, BASE],
    MAIN_AFTER: [MERGE],
}


def proof_for(repository=ONB, merge_commit=MERGE, candidate=CANDIDATE):
    """A well-formed proof for one landing: candidate and base beneath the merge."""
    parents = {candidate: [BASE], merge_commit: [candidate, BASE]}
    return verify_incorporation(
        FakeGit(Target(repository), parents, merge_commit),
        unit="S75-T36", candidate=candidate, base=BASE,
        merge_commit=merge_commit,
        checks=[Check("unit-suite", "PASS", cases=31)],
        observed_at="2026-10-25T20:00:00Z")


def digest_of(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="s75-t36-ack-")
        self.path = os.path.join(self.temp, "queue.json")
        self.store = QA.QueueStore(self.path, ONB)
        self.store.seed({
            "S75-T36": {"verdict": "PASS", "head_commit": CANDIDATE},
            "S75-T15": {"verdict": "PASS", "head_commit": sha(0xD1)},
            "S75-T11": {"verdict": "FAIL", "head_commit": sha(0xD2)},
            "S75-T99": {"verdict": "PASS", "head_commit": "not-a-sha"},
        })

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def raw(self):
        with open(self.path, "r", encoding="utf-8") as handle:
            return handle.read()

    def assert_untouched(self, before):
        self.assertEqual(self.raw(), before,
                         "a refused acknowledgement must not write a byte")


class AtomicAck(Base):
    def test_acknowledgement_carries_its_proof_in_one_record(self):
        before = self.raw()
        outcome = self.store.ack("S75-T36", proof_for(),
                                 observed_at="2026-10-25T20:05:00Z")
        self.assertEqual(outcome, QA.ACKNOWLEDGED)
        self.assertNotEqual(self.raw(), before)

        entry = self.store.entry("S75-T36")
        ack = entry["ack"]
        self.assertEqual(ack["state"], QA.ACKNOWLEDGED)
        self.assertEqual(ack["merge_commit"], MERGE)
        self.assertEqual(ack["candidate"], CANDIDATE)
        self.assertEqual(ack["ancestor_of_main"], "proven 2026-10-25T20:05:00Z")
        self.assertEqual(ack["proof"]["merge_commit"], MERGE)
        self.assertEqual(ack["proof_digest"], proof_for().digest)
        self.assertEqual(self.store.status("S75-T36"), QA.ACKNOWLEDGED)
        self.assertEqual(self.store.acknowledgement("S75-T36")["merge_commit"], MERGE)

    def test_an_acknowledged_entry_leaves_the_pending_set(self):
        self.assertIn("S75-T36", self.store.pending())
        self.store.ack("S75-T36", proof_for())
        self.assertNotIn("S75-T36", self.store.pending())
        self.assertIn("S75-T15", self.store.pending())

    def test_only_one_file_is_installed_and_no_temp_is_left_behind(self):
        self.store.ack("S75-T36", proof_for())
        leftovers = [n for n in os.listdir(self.temp) if ".tmp-" in n]
        self.assertEqual(leftovers, [])
        self.assertEqual(sorted(os.listdir(self.temp)), ["queue.json"])

    def test_the_store_is_valid_json_after_the_write(self):
        self.store.ack("S75-T36", proof_for())
        document = json.loads(self.raw())
        self.assertEqual(document["repository"], ONB)
        self.assertEqual(document["schema"], QA.ACK_SCHEMA)


class NeverHalfAcknowledged(Base):
    def test_a_record_that_does_not_claim_a_landing_writes_nothing(self):
        before = self.raw()
        document = proof_for().as_dict()
        document["incorporated"] = False
        with self.assertRaises(QA.AckRefused) as caught:
            self.store.ack("S75-T36", document)
        self.assertEqual(caught.exception.reason, "not-incorporated")
        self.assert_untouched(before)
        entry = self.store.entry("S75-T36")
        self.assertNotIn("merge_commit", entry)
        self.assertEqual(entry["ack"]["state"], QA.ACK_PENDING)

    def test_an_incomplete_proof_writes_nothing(self):
        before = self.raw()
        document = proof_for().as_dict()
        document.pop("remote_head")
        with self.assertRaises(QA.AckRefused) as caught:
            self.store.ack("S75-T36", document)
        self.assertEqual(caught.exception.reason, "not-incorporated")
        self.assert_untouched(before)

    def test_no_proof_writes_nothing(self):
        before = self.raw()
        with self.assertRaises(QA.AckRefused) as caught:
            self.store.ack("S75-T36", None)
        self.assertEqual(caught.exception.reason, "no-proof")
        self.assert_untouched(before)

    def test_an_unknown_unit_writes_nothing(self):
        before = self.raw()
        with self.assertRaises(QA.AckRefused) as caught:
            self.store.ack("S75-T00", proof_for())
        self.assertEqual(caught.exception.reason, "unknown-unit")
        self.assert_untouched(before)

    def test_a_non_pass_verdict_writes_nothing(self):
        before = self.raw()
        with self.assertRaises(QA.AckRefused) as caught:
            self.store.ack("S75-T11", proof_for(candidate=sha(0xD2)))
        self.assertEqual(caught.exception.reason, "not-pass")
        self.assert_untouched(before)

    def test_a_missing_reviewed_head_writes_nothing(self):
        before = self.raw()
        with self.assertRaises(QA.AckRefused) as caught:
            self.store.ack("S75-T99", proof_for())
        self.assertEqual(caught.exception.reason, "head-missing")
        self.assert_untouched(before)


class CorrectTargetQueue(Base):
    def test_a_proof_from_another_repository_writes_nothing(self):
        before = self.raw()
        with self.assertRaises(QA.AckRefused) as caught:
            self.store.ack("S75-T36", proof_for(repository=N999))
        self.assertEqual(caught.exception.reason, "wrong-target")
        self.assertIn(ONB, caught.exception.detail)
        self.assert_untouched(before)

    def test_a_proof_for_a_different_candidate_writes_nothing(self):
        before = self.raw()
        with self.assertRaises(QA.AckRefused) as caught:
            self.store.ack("S75-T15", proof_for())
        self.assertEqual(caught.exception.reason, "candidate-mismatch")
        self.assert_untouched(before)

    def test_an_entry_belonging_to_another_store_writes_nothing(self):
        self.store.seed({"S75-T37": {"verdict": "PASS",
                                     "head_commit": CANDIDATE,
                                     "repository": N999}})
        before = self.raw()
        with self.assertRaises(QA.AckRefused) as caught:
            self.store.ack("S75-T37", proof_for())
        self.assertEqual(caught.exception.reason, "foreign-entry")
        self.assert_untouched(before)

    def test_a_malformed_store_is_refused_rather_than_overwritten(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        with self.assertRaises(QA.AckRefused) as caught:
            self.store.ack("S75-T36", proof_for())
        self.assertEqual(caught.exception.reason, "store-malformed")
        self.assertEqual(self.raw(), "{not json")


class IdempotentAndConflicting(Base):
    def test_re_acknowledging_the_same_landing_writes_nothing_and_stays_proven(self):
        self.store.ack("S75-T36", proof_for())
        settled = self.raw()
        outcome = self.store.ack("S75-T36", proof_for(merge_commit=MERGE))
        self.assertEqual(outcome, QA.ALREADY_ACKNOWLEDGED)
        self.assert_untouched(settled)
        self.assertEqual(self.store.acknowledgement("S75-T36")["merge_commit"], MERGE)

    def test_a_refreshed_proof_for_the_same_landing_is_still_idempotent(self):
        from incorporation_proof import refresh_proof
        first = proof_for()
        self.store.ack("S75-T36", first)
        settled = self.raw()
        refreshed = refresh_proof(FakeGit(Target(ONB), PARENTS, MAIN_AFTER),
                                  first, "2026-10-26T00:00:00Z")
        self.assertNotEqual(refreshed.remote_head, first.remote_head)
        self.assertEqual(self.store.ack("S75-T36", refreshed),
                         QA.ALREADY_ACKNOWLEDGED)
        self.assert_untouched(settled)

    def test_a_second_different_landing_is_refused_and_the_first_stands(self):
        self.store.ack("S75-T36", proof_for())
        settled = self.raw()
        with self.assertRaises(QA.AckRefused) as caught:
            self.store.ack("S75-T36", proof_for(merge_commit=OTHER_MERGE))
        self.assertEqual(caught.exception.reason, "ack-conflict")
        self.assert_untouched(settled)
        self.assertEqual(self.store.acknowledgement("S75-T36")["merge_commit"], MERGE)

    def test_an_unacknowledged_entry_reports_no_partial_record(self):
        self.assertIsNone(self.store.acknowledgement("S75-T36"))
        self.assertEqual(self.store.status("S75-T36"), QA.ACK_PENDING)


class NoCrossFlavorGate(Base):
    def test_onb_acknowledges_with_zero_n999_entries_present(self):
        self.assertIsNone(self.store.entry("S75-T37"))
        self.assertEqual(self.store.ack("S75-T36", proof_for()), QA.ACKNOWLEDGED)
        self.assertEqual(self.store.status("S75-T36"), QA.ACKNOWLEDGED)
        self.assertEqual([u for u in self.store.entries()
                          if u.startswith("S75-T3")], ["S75-T36"])

    def test_a_separate_n999_store_never_sees_onb_entries(self):
        n999 = QA.QueueStore(os.path.join(self.temp, "n999.json"), N999)
        n999.seed({"S75-T37": {"verdict": "PASS", "head_commit": CANDIDATE}})
        self.assertEqual(n999.ack("S75-T37", proof_for(repository=N999)),
                         QA.ACKNOWLEDGED)
        self.assertEqual(self.store.ack("S75-T36", proof_for()), QA.ACKNOWLEDGED)
        self.assertEqual(self.store.status("S75-T37"), QA.ACK_PENDING)
        self.assertEqual(n999.status("S75-T36"), QA.ACK_PENDING)


class RefusalReasonsAreAClosedSet(Base):
    def test_an_invented_reason_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            QA.AckRefused("probably-fine")
        self.assertEqual(len(QA.ACK_REASONS), len(set(QA.ACK_REASONS)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
