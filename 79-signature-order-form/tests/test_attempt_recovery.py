"""S79-10 fixture cases: refresh/back-navigation, lost browser context,
duplicate submission after restore, corrupt serialized state.
Doc 09 sections 7, 8, 11; doc 18 section 4. L1 only."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(HERE.parent))

from attempt_recovery import RecoveredAttempt, RecoveryError, restore_attempt, serialize_attempt  # noqa: E402
from purchase_state import PurchaseAttempt, StateError  # noqa: E402


def attempt_in_flight():
    a = PurchaseAttempt()
    a.apply("begin_validation")
    a.apply("submit")
    return a


def attempt_pending():
    a = attempt_in_flight()
    a.apply("timeout_unknown_outcome")
    return a


def attempt_paid():
    a = attempt_in_flight()
    a.apply("native_paid_verified")
    return a


def roundtrip(attempt, order_ref="TEST-ORDER-1"):
    payload = serialize_attempt(attempt, order_ref=order_ref)
    return restore_attempt(json.loads(json.dumps(payload)))


class RefreshBackNavigationTests(unittest.TestCase):
    def test_restored_submitting_is_neither_paid_nor_failed(self):
        restored = roundtrip(attempt_in_flight())
        self.assertEqual(restored.state, "submitting")
        self.assertFalse(restored.can_traverse_paid_edge())
        self.assertEqual(restored.order_ref, "TEST-ORDER-1")

    def test_restored_pending_is_neither_paid_nor_failed(self):
        restored = roundtrip(attempt_pending())
        self.assertEqual(restored.state, "pending_confirmation")
        self.assertFalse(restored.can_traverse_paid_edge())

    def test_in_flight_restore_requires_reconciliation_before_paid_routing(self):
        restored = roundtrip(attempt_pending())
        self.assertTrue(restored.reconciliation_outstanding)
        with self.assertRaises(RecoveryError):
            restored.apply("native_paid_verified")
        self.assertEqual(restored.state, "pending_confirmation")

    def test_reconciliation_with_paid_found_completes_restored_attempt(self):
        restored = roundtrip(attempt_pending())
        self.assertEqual(restored.record_reconciliation(found_paid=True), "paid")
        self.assertFalse(restored.reconciliation_outstanding)
        self.assertTrue(restored.can_traverse_paid_edge())

    def test_reconciliation_with_not_paid_allows_retry(self):
        restored = roundtrip(attempt_pending())
        self.assertEqual(restored.record_reconciliation(found_paid=False), "failed")
        self.assertEqual(restored.apply("retry_after_reconciliation"), "ready")

    def test_reconciliation_with_not_paid_resolves_restored_submitting_to_failed(self):
        # Regression for review defect AR-1: mirrors
        # test_reconciliation_with_not_paid_allows_retry (the pending
        # restore). This replaces the former
        # test_restored_submitting_reconcile_not_paid_then_native_failure,
        # which encoded the asymmetry: it needed a separate native_failed
        # after the not-paid reconciliation because the attempt was left
        # in submitting with the hold lifted, still able to reach paid.
        restored = roundtrip(attempt_in_flight())
        self.assertEqual(restored.record_reconciliation(found_paid=False), "failed")
        self.assertEqual(restored.state, "failed")
        self.assertFalse(restored.reconciliation_outstanding)
        with self.assertRaises(StateError):
            restored.apply("native_paid_verified")
        self.assertFalse(restored.can_traverse_paid_edge())
        self.assertEqual(restored.apply("retry_after_reconciliation"), "ready")

    def test_native_failure_readback_resolves_restored_submitting_to_failed(self):
        # Coverage restored after the AR-1 fix replaced the former
        # submitting-reconcile test: a native failure read-back applied
        # directly to a restored submitting attempt. Per the module
        # docstring, native_failed is not a held event (only retry and
        # native_paid_verified wait for reconciliation), so the wrapper
        # delegates it to the live machine, which resolves submitting to
        # failed. The restore hold itself is NOT discharged by this path:
        # the machine clears the reconcile flag on a direct resolution
        # only from pending_confirmation (defect D-new1), so the wrapper
        # still reports the reconciliation outstanding and still holds
        # retry until the caller records the native-record check.
        restored = roundtrip(attempt_in_flight())
        self.assertTrue(restored.reconciliation_outstanding)
        self.assertEqual(restored.apply("native_failed"), "failed")
        self.assertEqual(restored.state, "failed")
        self.assertFalse(restored.can_traverse_paid_edge())
        self.assertTrue(restored.reconciliation_outstanding)
        with self.assertRaises(RecoveryError):
            restored.apply("retry_after_reconciliation")
        self.assertEqual(restored.record_reconciliation(found_paid=False), "failed")
        self.assertFalse(restored.reconciliation_outstanding)
        self.assertEqual(restored.apply("retry_after_reconciliation"), "ready")

    def test_restored_terminal_states_carry_no_hold(self):
        paid = roundtrip(attempt_paid())
        self.assertFalse(paid.reconciliation_outstanding)
        self.assertTrue(paid.can_traverse_paid_edge())
        failed_attempt = attempt_in_flight()
        failed_attempt.apply("native_failed")
        failed = roundtrip(failed_attempt)
        self.assertEqual(failed.state, "failed")
        self.assertFalse(failed.reconciliation_outstanding)
        self.assertEqual(failed.apply("retry_after_reconciliation"), "ready")

    def test_restored_ready_attempt_behaves_like_a_live_one(self):
        restored = roundtrip(PurchaseAttempt(), order_ref=None)
        self.assertEqual(restored.state, "ready")
        self.assertEqual(restored.apply("begin_validation"), "validating")


class SanctionedSurfaceTests(unittest.TestCase):
    def test_inner_attempt_is_not_part_of_the_public_surface(self):
        # Review defect AR-2: the reconcile-on-restore hold lives in the
        # wrapper, so the inner PurchaseAttempt must not be reachable
        # through a public attribute a consumer could drive directly.
        restored = roundtrip(attempt_in_flight())
        self.assertFalse(hasattr(restored, "attempt"))
        # The wrapper surface covers what consumers legitimately need.
        self.assertEqual(restored.state, "submitting")
        self.assertTrue(restored.reconciliation_outstanding)
        snapshot = restored.serialize()
        self.assertEqual(snapshot["state"], "submitting")
        self.assertEqual(snapshot["order_ref"], "TEST-ORDER-1")
        self.assertEqual(restore_attempt(snapshot).state, "submitting")


class LostBrowserContextTests(unittest.TestCase):
    def test_context_free_restore_is_fresh_ready_with_no_order(self):
        restored = restore_attempt(None)
        self.assertEqual(restored.state, "ready")
        self.assertIsNone(restored.order_ref)
        self.assertFalse(restored.can_traverse_paid_edge())

    def test_context_free_restore_cannot_claim_a_paid_order(self):
        restored = restore_attempt(None)
        # No transition available to a fresh attempt reaches paid without
        # the full live sequence, and there is no order to claim.
        with self.assertRaises(StateError):
            restored.apply("native_paid_verified")
        self.assertFalse(restored.can_traverse_paid_edge())
        self.assertIsNone(restored.order_ref)

    def test_order_ref_cannot_be_attached_after_restore(self):
        restored = restore_attempt(None)
        with self.assertRaises(Exception):
            restored.order_ref = "FORGED-ORDER"
        self.assertIsNone(restored.order_ref)


class DuplicateSubmissionAfterRestoreTests(unittest.TestCase):
    def test_duplicate_submit_rejected_from_restored_submitting(self):
        restored = roundtrip(attempt_in_flight())
        with self.assertRaises(StateError):
            restored.apply("submit")

    def test_duplicate_submit_rejected_from_restored_pending(self):
        restored = roundtrip(attempt_pending())
        with self.assertRaises(StateError):
            restored.apply("submit")


class CorruptSerializedStateTests(unittest.TestCase):
    def test_unknown_state_value_raises(self):
        payload = serialize_attempt(attempt_in_flight())
        payload["state"] = "charged_maybe"
        with self.assertRaises(RecoveryError):
            restore_attempt(payload)

    def test_paid_claim_without_verified_history_raises(self):
        payload = serialize_attempt(PurchaseAttempt())
        payload["state"] = "paid"  # history is empty; replay ends at ready
        with self.assertRaises(RecoveryError):
            restore_attempt(payload)

    def test_forged_history_transition_raises(self):
        payload = {"format": "s79.purchase_attempt/v1", "state": "paid",
                   "reconcile_required": False, "reconciled": False,
                   "order_ref": "FORGED",
                   "history": [["ready", "native_paid_verified", "paid"]]}
        with self.assertRaises(RecoveryError):
            restore_attempt(payload)

    def test_history_recording_a_wrong_result_state_raises(self):
        payload = serialize_attempt(attempt_in_flight())
        payload["history"][0][2] = "paid"
        with self.assertRaises(RecoveryError):
            restore_attempt(payload)

    def test_history_gap_raises(self):
        payload = serialize_attempt(attempt_pending())
        del payload["history"][1]  # remove the submit step
        with self.assertRaises(RecoveryError):
            restore_attempt(payload)

    def test_non_object_and_unknown_format_raise(self):
        with self.assertRaises(RecoveryError):
            restore_attempt("paid")
        with self.assertRaises(RecoveryError):
            restore_attempt({"format": "other/v9", "state": "ready", "history": []})

    def test_serialize_rejects_non_string_order_ref(self):
        with self.assertRaises(RecoveryError):
            serialize_attempt(PurchaseAttempt(), order_ref=12345)


if __name__ == "__main__":
    unittest.main(verbosity=2)
