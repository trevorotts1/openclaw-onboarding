#!/usr/bin/env python3
"""S75-T39: per-repository facet dispatch, fixture only.

Deterministic, no network, no credential, no client data. Every path used here
is a synthetic directory under a temporary root. Run:
    python3 test_facet_dispatch_s75_t39.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from hygiene import facet_dispatch as FD  # noqa: E402

ONB_EVENT = {"repo": "ONB", "event_id": "evt-onb-001",
             "kind": "REMOTE_INCORPORATION"}
N999_EVENT = {"repo": "N999", "event_id": "evt-n999-001",
              "kind": "REMOTE_INCORPORATION"}


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="s75-t39-")
        self.disposable = os.path.join(self.temp, "disposable")
        self.store = os.path.join(self.temp, "evidence", "hygiene", "receipts")
        os.makedirs(self.disposable)
        os.makedirs(self.store)

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def item(self, klass="TEMP_OUTPUT", path=None, **proofs):
        return {
            "resource_id": "res-fixture-1",
            "class": klass,
            "path": path or os.path.join(self.disposable, "work"),
            "proofs": proofs,
        }

    def full_proofs(self, klass):
        return {name: "fixture:" + name for name in FD.REQUIRED_PROOFS[klass]}


class DispatchScopesToEventRepository(Base):
    def test_action_carries_exactly_one_repository(self):
        action = FD.dispatch_event(ONB_EVENT)
        self.assertEqual(action["repo"], "ONB")
        self.assertEqual(action["state"], "QUEUED")
        self.assertEqual(action["event_id"], "evt-onb-001")

    def test_onb_event_creates_no_n999_or_cc_action(self):
        actions = [FD.dispatch_event(ONB_EVENT)]
        self.assertEqual([a["repo"] for a in actions], ["ONB"])
        self.assertNotIn("N999", json.dumps(actions))
        self.assertNotIn("CC", json.dumps(actions))

    def test_sibling_facets_are_independent(self):
        onb = FD.dispatch_event(ONB_EVENT)
        n999 = FD.dispatch_event(N999_EVENT)
        self.assertNotEqual(onb["action_id"], n999["action_id"])
        self.assertEqual([onb["repo"], n999["repo"]], ["ONB", "N999"])

    def test_redelivered_event_is_the_same_action(self):
        first = FD.dispatch_event(ONB_EVENT)
        again = FD.dispatch_event(ONB_EVENT, existing=[first])
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["action_id"], first["action_id"])

    def test_distinct_event_same_repo_starts_distinct_action(self):
        first = FD.dispatch_event(ONB_EVENT)
        second = FD.dispatch_event(dict(ONB_EVENT, event_id="evt-onb-002"),
                                   existing=[first])
        self.assertFalse(second["duplicate"])
        self.assertNotEqual(first["action_id"], second["action_id"])

    def test_same_event_id_in_two_repos_does_not_collide(self):
        onb = FD.dispatch_event(dict(ONB_EVENT, event_id="evt-shared"))
        n999 = FD.dispatch_event(dict(N999_EVENT, event_id="evt-shared"),
                                 existing=[onb])
        self.assertFalse(n999["duplicate"])
        self.assertEqual(n999["repo"], "N999")
        self.assertNotEqual(n999["action_id"], onb["action_id"])

    def test_checked_no_change_event_is_a_facet_too(self):
        action = FD.dispatch_event(dict(ONB_EVENT, kind="CHECKED_NO_CHANGE"))
        self.assertEqual(action["kind"], "CHECKED_NO_CHANGE")


class NoGlobalSweep(Base):
    def test_multi_repo_event_is_refused(self):
        with self.assertRaises(FD.GlobalSweepRefused):
            FD.dispatch_event({"repo": ["ONB", "N999"], "event_id": "evt-1"})
        with self.assertRaises(FD.GlobalSweepRefused):
            FD.dispatch_event({"repos": ["ONB", "N999"], "event_id": "evt-1"})

    def test_wildcard_repo_is_refused(self):
        for repo in ("*", "ALL", "onb,n999", "ONB|N999", "ONB N999"):
            with self.assertRaises(FD.GlobalSweepRefused):
                FD.dispatch_event({"repo": repo, "event_id": "evt-1"})

    def test_sweep_action_set_is_refused(self):
        actions = [FD.dispatch_event(ONB_EVENT), FD.dispatch_event(N999_EVENT)]
        with self.assertRaises(FD.GlobalSweepRefused):
            FD.assert_single_facet(actions)

    def test_single_repo_action_set_passes(self):
        actions = [FD.dispatch_event(ONB_EVENT),
                   FD.dispatch_event(dict(ONB_EVENT, event_id="evt-onb-002"))]
        self.assertTrue(FD.assert_single_facet(actions))

    def test_unknown_repo_alias_is_not_silently_accepted(self):
        with self.assertRaises(FD.EventRefused):
            FD.dispatch_event({"repo": "SOMEWHERE", "event_id": "evt-1"})


class ProofsPrecedeRemoval(Base):
    def test_complete_class_proofs_authorize_removal(self):
        for klass in FD.REQUIRED_PROOFS:
            receipt = FD.authorize_removal(
                self.item(klass, **self.full_proofs(klass)), [self.disposable])
            self.assertEqual(receipt["disposition"], "REMOVED")
            self.assertEqual(receipt["class"], klass)

    def test_each_class_is_refused_for_its_own_missing_proof(self):
        for klass, names in FD.REQUIRED_PROOFS.items():
            for missing in names:
                proofs = self.full_proofs(klass)
                proofs.pop(missing)
                with self.assertRaises(FD.ProofMissing) as caught:
                    FD.authorize_removal(self.item(klass, **proofs),
                                         [self.disposable])
                self.assertIn(missing, str(caught.exception))

    def test_proof_sets_are_class_specific(self):
        self.assertNotEqual(FD.REQUIRED_PROOFS["TEMP_OUTPUT"],
                            FD.REQUIRED_PROOFS["DELIVERED_BRANCH"])
        temp = self.item("TEMP_OUTPUT", **self.full_proofs("TEMP_OUTPUT"))
        branch = self.item("DELIVERED_BRANCH",
                           **self.full_proofs("DELIVERED_BRANCH"))
        self.assertTrue(FD.authorize_removal(branch, [self.disposable]))
        # a temp directory's proofs are not a delivered branch's proofs
        with self.assertRaises(FD.ProofMissing):
            FD.authorize_removal(dict(temp, **{"class": "DELIVERED_BRANCH"}),
                                 [self.disposable])

    def test_protected_class_is_never_removable(self):
        for klass in FD.PROTECTED_CLASSES:
            with self.assertRaises(FD.ProtectedResource):
                FD.authorize_removal(
                    self.item(klass, **{name: "fixture" for name in
                                        ("ownership", "preservation",
                                         "consumers", "approval")}),
                    [self.disposable])

    def test_path_outside_owned_roots_is_refused(self):
        outside = os.path.join(self.temp, "someone-elses-work")
        os.makedirs(outside)
        with self.assertRaises(FD.DispositionRefused):
            FD.authorize_removal(
                self.item("TEMP_OUTPUT", path=outside,
                          **self.full_proofs("TEMP_OUTPUT")),
                [self.disposable])

    def test_traversal_escape_is_refused(self):
        escape = os.path.join(self.disposable, "..", "someone-elses-work")
        with self.assertRaises(FD.DispositionRefused):
            FD.authorize_removal(
                self.item("TEMP_OUTPUT", path=escape,
                          **self.full_proofs("TEMP_OUTPUT")),
                [self.disposable])

    def test_unknown_class_is_refused(self):
        with self.assertRaises(FD.DispositionRefused):
            FD.authorize_removal(self.item("MYSTERY", ownership="x"),
                                 [self.disposable])


class CompactReceiptsOutsideDisposablePaths(Base):
    def receipt(self, **extra):
        body = {"schema": FD.SCHEMA, "repo": "ONB", "event_id": "evt-onb-001",
                "resource_id": "res-fixture-1", "disposition": "REMOVED"}
        body.update(extra)
        return body

    def test_receipt_lands_outside_the_disposable_root(self):
        path = FD.record_receipt(self.store, [self.disposable], self.receipt())
        self.assertTrue(path.startswith(os.path.realpath(self.store)))

    def test_receipt_store_inside_disposable_root_is_refused(self):
        inside = os.path.join(self.disposable, "receipts")
        with self.assertRaises(FD.ReceiptRefused):
            FD.record_receipt(inside, [self.disposable], self.receipt())
        with self.assertRaises(FD.ReceiptRefused):
            FD.record_receipt(self.disposable, [self.disposable], self.receipt())

    def test_oversized_receipt_is_refused(self):
        bloated = self.receipt(blob="x" * (FD.MAX_RECEIPT_BYTES + 1))
        with self.assertRaises(FD.ReceiptRefused):
            FD.record_receipt(self.store, [self.disposable], bloated)

    def test_receipt_survives_removal_of_the_disposable_path(self):
        work = os.path.join(self.disposable, "work")
        os.makedirs(work)
        receipt = FD.authorize_removal(
            self.item("TEMP_OUTPUT", path=work,
                      **self.full_proofs("TEMP_OUTPUT")),
            [self.disposable])
        receipt.update({"repo": "ONB", "event_id": "evt-onb-001"})
        path = FD.record_receipt(self.store, [self.disposable], receipt)
        shutil.rmtree(work)
        with open(path, encoding="utf-8") as handle:
            reread = json.load(handle)
        self.assertEqual(reread["resource_id"], "res-fixture-1")
        self.assertEqual(reread["disposition"], "REMOVED")

    def test_same_event_writes_the_same_receipt_path(self):
        a = FD.receipt_path(self.store, "ONB", "evt-onb-001")
        b = FD.receipt_path(self.store, "ONB", "evt-onb-001")
        c = FD.receipt_path(self.store, "N999", "evt-onb-001")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


if __name__ == "__main__":
    unittest.main(verbosity=2)
