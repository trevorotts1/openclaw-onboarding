"""S81 route law pins for lane 7 gaps G1 to G12, run against the packet
reference contracts (imported read-only from the packet; the packet is never
modified). These tests pin reference behavior that lane 7 proved by probes
but no local fixture covered. Expected targets are computed independently
from doc 02 section 4 route law, never copied from the code under test.
G11 and G12 (processing lockout, unknown outcome reconciliation) are not
modeled by the reference: the reference rejects those event names as
unknown, which is pinned here as current contract behavior. The runtime
carriers live in the confirmed extra-offer interface contract (S49):
G12's carrier is carried by revision 2 section 8A.4 (SHA-256
07f6b75794a3a8e98aad02a94fb82bcdec78d1264b0a56fa3bda066484b3022f), so
the CR-S81-002 pin below is a real pin exercising the confirmed
operation through the package's adapter. G11's carrier is revision 2
section 8A.5 (the submission lockout operation and the
attempt-integrity carrier ruling at the same SHA-256), so the
CR-S81-001 pin below is likewise a real pin, un-skipped in the
follow-on cycle on the landing of the candidate carrying revision 2
(PR #2228, merged in train #2235 on main 9ccd6536): its disposition
was accepted under S81-DEC-G4-SUBDISP-01, and the pin exercises the
confirmed carrier (pending lockout, reconcile-before-retry, decline
never charges) through the package's adapter, not only the
reference's rejection of the event names.
Run with the rest of the suite: python3 -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

PACKET_REF = Path("/home/hatch/workspace/signature-launch/packet/reference")
sys.path.insert(0, str(PACKET_REF))
from reference_contracts import Extras, resolve_after, validate_graph  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "adapters"))
from shared_action_wrapper import (  # noqa: E402
    AdapterBindingError, DownsellActionAdapter)

BASE = frozenset(["MAIN-A"])
WITH_BUMP = frozenset(["MAIN-A", "BUMP"])
FAILURE_EVENTS = ("payment_failed", "payment_pending", "requires_customer_action")


class G1U1FailureDoesNotRouteToD1Tests(unittest.TestCase):
    def test_g1_u1_failed_or_pending_payment_stays_on_u1(self):
        f = Extras()
        for event in FAILURE_EVENTS:
            stage, bought = resolve_after("upsell_1", event, BASE, f)
            self.assertEqual(stage, "upsell_1")
            self.assertNotEqual(stage, "downsell_1")
            self.assertEqual(bought, BASE)


class G2UnverifiedPaymentTests(unittest.TestCase):
    def test_g2_unverified_payment_succeeded_raises_at_u1(self):
        f = Extras()
        with self.assertRaises(ValueError):
            resolve_after("upsell_1", "payment_succeeded", BASE, f, False)
        with self.assertRaises(ValueError):
            resolve_after("upsell_1", "payment_succeeded", BASE, f)

    def test_g2_unverified_payment_succeeded_raises_at_d1(self):
        f = Extras()
        with self.assertRaises(ValueError):
            resolve_after("downsell_1", "payment_succeeded", BASE, f, False)
        with self.assertRaises(ValueError):
            resolve_after("downsell_1", "payment_succeeded", BASE, f)

    def test_g2_unverified_payment_error_names_the_rule(self):
        f = Extras()
        with self.assertRaises(ValueError) as ctx:
            resolve_after("downsell_1", "payment_succeeded", BASE, f, False)
        self.assertIn("does not prove payment", str(ctx.exception))


class G3U1DisabledExtrasInvariantTests(unittest.TestCase):
    def test_g3_u1_disabled_with_d1_or_u2_enabled_raises(self):
        with self.assertRaises(ValueError):
            Extras(upsell_1=False, downsell_1=True, upsell_2=False)
        with self.assertRaises(ValueError):
            Extras(upsell_1=False, downsell_1=False, upsell_2=True)
        with self.assertRaises(ValueError):
            Extras(upsell_1=False, downsell_1=True, upsell_2=True)

    def test_g3_u1_disabled_with_d1_and_u2_disabled_constructs(self):
        f = Extras(upsell_1=False, downsell_1=False, upsell_2=False)
        self.assertFalse(f.upsell_1)
        self.assertFalse(f.downsell_1)
        self.assertFalse(f.upsell_2)


class G4MutualExclusionRouteLayerTests(unittest.TestCase):
    def test_g4_entering_d1_with_u1_purchased_raises(self):
        f = Extras()
        bought = frozenset(["MAIN-A", "U1"])
        with self.assertRaises(ValueError):
            resolve_after("downsell_1", "explicit_decline", bought, f)

    def test_g4_succeeding_at_u1_with_d1_purchased_raises(self):
        f = Extras()
        bought = frozenset(["MAIN-A", "D1"])
        with self.assertRaises(ValueError):
            resolve_after("upsell_1", "payment_succeeded", bought, f, True)


class G5U2EntryGuardTests(unittest.TestCase):
    def test_g5_u2_entry_with_main_only_purchase_raises_for_any_event(self):
        f = Extras()
        for event in ("explicit_decline", "payment_failed", "payment_succeeded"):
            with self.assertRaises(ValueError):
                resolve_after("upsell_2", event, BASE, f, True)

    def test_g5_u2_entry_after_both_declined_raises(self):
        f = Extras()
        stage, bought = resolve_after("upsell_1", "explicit_decline", BASE, f)
        stage, bought = resolve_after(stage, "explicit_decline", bought, f)
        self.assertEqual(stage, "thank_you")
        with self.assertRaises(ValueError):
            resolve_after("upsell_2", "explicit_decline", bought, f)


class G6BumpPreservationPaidBranchTests(unittest.TestCase):
    def test_g6_d1_paid_with_bump_u2_enabled_preserves_bump(self):
        f = Extras()
        stage, bought = resolve_after("downsell_1", "payment_succeeded", WITH_BUMP, f, True)
        self.assertEqual(stage, "upsell_2")
        self.assertEqual(bought, WITH_BUMP | {"D1"})

    def test_g6_d1_paid_with_bump_u2_disabled_preserves_bump(self):
        f = Extras(upsell_2=False)
        stage, bought = resolve_after("downsell_1", "payment_succeeded", WITH_BUMP, f, True)
        self.assertEqual(stage, "thank_you")
        self.assertEqual(bought, WITH_BUMP | {"D1"})


class G7FailureThenDeclineCompositionTests(unittest.TestCase):
    def test_g7_d1_failure_then_explicit_decline_goes_to_thank_you(self):
        f = Extras()
        stage, bought = resolve_after("downsell_1", "payment_failed", BASE, f)
        self.assertEqual(stage, "downsell_1")
        self.assertEqual(bought, BASE)
        stage, bought = resolve_after(stage, "explicit_decline", bought, f)
        self.assertEqual(stage, "thank_you")
        self.assertEqual(bought, BASE)

    def test_g7_u1_failure_then_explicit_decline_reaches_d1(self):
        f = Extras()
        stage, bought = resolve_after("upsell_1", "payment_failed", BASE, f)
        self.assertEqual(stage, "upsell_1")
        stage, bought = resolve_after(stage, "explicit_decline", bought, f)
        self.assertEqual(stage, "downsell_1")
        self.assertEqual(bought, BASE)


class G8NoMainPurchaseRouteLayerTests(unittest.TestCase):
    def test_g8_d1_without_main_purchase_raises_for_any_event(self):
        f = Extras()
        for purchased in (frozenset(), frozenset(["BUMP"])):
            for event in ("explicit_decline", "payment_failed", "payment_succeeded"):
                with self.assertRaises(ValueError):
                    resolve_after("downsell_1", event, purchased, f, True)


class G9ValidateGraphTests(unittest.TestCase):
    def valid_graph(self):
        return {
            "nodes": [
                {"page_id": "landing-1", "role": "landing"},
                {"page_id": "checkout-1", "role": "checkout"},
                {"page_id": "upsell-1", "role": "upsell_1"},
                {"page_id": "downsell-1", "role": "downsell_1"},
                {"page_id": "upsell-2", "role": "upsell_2"},
                {"page_id": "thanks-1", "role": "thank_you"},
            ],
            "edges": [
                {"from": "landing-1", "to": "checkout-1"},
                {"from": "checkout-1", "to": "upsell-1"},
                {"from": "upsell-1", "to": "downsell-1"},
                {"from": "upsell-1", "to": "upsell-2"},
                {"from": "downsell-1", "to": "upsell-2"},
                {"from": "downsell-1", "to": "thanks-1"},
                {"from": "upsell-2", "to": "thanks-1"},
            ],
        }

    def test_g9_valid_graph_passes(self):
        validate_graph(self.valid_graph())

    def test_g9_duplicate_u2_role_raises(self):
        graph = self.valid_graph()
        graph["nodes"].append({"page_id": "upsell-2-copy", "role": "upsell_2"})
        graph["edges"].append({"from": "downsell-1", "to": "upsell-2-copy"})
        graph["edges"].append({"from": "upsell-2-copy", "to": "thanks-1"})
        with self.assertRaises(ValueError):
            validate_graph(graph)

    def test_g9_cycle_raises(self):
        graph = {
            "nodes": [
                {"page_id": "landing-1", "role": "landing"},
                {"page_id": "checkout-1", "role": "checkout"},
                {"page_id": "thanks-1", "role": "thank_you"},
            ],
            "edges": [
                {"from": "landing-1", "to": "checkout-1"},
                {"from": "checkout-1", "to": "landing-1"},
                {"from": "checkout-1", "to": "thanks-1"},
            ],
        }
        with self.assertRaises(ValueError):
            validate_graph(graph)

    def test_g9_unreachable_enabled_node_raises(self):
        graph = self.valid_graph()
        graph["nodes"].append({"page_id": "orphan-1", "role": "checkout_alt"})
        graph["edges"].append({"from": "orphan-1", "to": "thanks-1"})
        with self.assertRaises(ValueError):
            validate_graph(graph)

    def test_g9_dangling_edge_raises(self):
        graph = self.valid_graph()
        graph["edges"].append({"from": "checkout-1", "to": "no-such-node"})
        with self.assertRaises(ValueError):
            validate_graph(graph)


class G10CheckoutDeclineTests(unittest.TestCase):
    def test_g10_checkout_explicit_decline_raises(self):
        f = Extras()
        with self.assertRaises(ValueError):
            resolve_after("checkout", "explicit_decline", BASE, f)


class G11G12UnmodeledEventRejectionTests(unittest.TestCase):
    def test_g11_processing_event_rejected_as_unknown_at_d1(self):
        f = Extras()
        with self.assertRaises(ValueError) as ctx:
            resolve_after("downsell_1", "processing", BASE, f)
        self.assertIn("Unknown event", str(ctx.exception))

    def test_g12_unknown_outcome_and_timeout_rejected_as_unknown_at_d1(self):
        f = Extras()
        for event in ("unknown_outcome", "timeout"):
            with self.assertRaises(ValueError) as ctx:
                resolve_after("downsell_1", event, BASE, f)
            self.assertIn("Unknown event", str(ctx.exception))

    def test_g11_g12_other_unmodeled_events_rejected_as_unknown_at_d1(self):
        f = Extras()
        for event in ("expired_or_unsupported_context", "abandoned"):
            with self.assertRaises(ValueError):
                resolve_after("downsell_1", event, BASE, f)

    def test_g11_CR_S81_001_processing_lockout(self):
        # CR-S81-001, confirmed by revision 2 section 8A.5 of the
        # extra-offer interface contract (S49; SHA-256
        # 07f6b75794a3a8e98aad02a94fb82bcdec78d1264b0a56fa3bda066484b3022f;
        # G-4 closed by the attempt-integrity carrier ruling recorded
        # in that section, accepted under S81-DEC-G4-SUBDISP-01; the
        # candidate carrying revision 2 landed as PR #2228 in train
        # #2235). The carrier is a named discipline of three legs,
        # and this pin exercises all three through the package's
        # adapter, whose row 2 submission point is MAPPED to the
        # section 8A.5 operation: (1) the pending lockout: one
        # attempt has exactly one submission path, and a repeat
        # submission while the attempt's outcome is pending
        # (submitting or pending_confirmation) is rejected before it
        # reaches the component, so one pending attempt can produce
        # at most one charge attempt and the standing attempt is
        # unaffected; (2) reconcile-before-retry: an unknown outcome
        # is carried as pending_confirmation with reconcile_required
        # set, no retry is accepted until reconciliation is
        # recorded, and a fresh submission is admitted only from a
        # recorded resolution; (3) decline never charges: invoking
        # decline performs no charge action in any attempt state.
        # No idempotency or deduplication key is named or coined
        # anywhere in this exercise: the carrier is the discipline,
        # per the section 8A.5 ruling. The acceptance-evidence
        # fixture named in section 8A.5 (two submissions during one
        # pending attempt producing exactly one charge attempt, from
        # the owning side) remains an outstanding evidence item
        # owned as the record states; this pin asserts the carrier
        # discipline at the adapter layer only and is not that
        # fixture.
        entry = {
            "main_purchased_verified": True,
            "u1_event": "explicit_decline",
            "u1_enabled": True,
            "d1_enabled": True,
            "u2_enabled": True,
            "u1_accepted": False,
        }
        ctx = {"downsell_offer_ref": "TEST-D1-OFFER"}

        class LockoutComponent:
            """Scripted shared-component double for the section 8A.5
            exercise: each submission returns the next scripted
            result (or raises it), reconcile returns its scripted
            result, and every submission context is recorded so the
            pin can prove what a repeat did and did not reach."""

            ALL_SUBMITTED = []

            def __init__(self, submit_results, reconcile_result=None):
                self.submit_calls = []
                self.reconcile_calls = []
                self._submit_results = list(submit_results)
                self.reconcile_result = reconcile_result

            def submit_purchase(self, context):
                self.submit_calls.append(context)
                LockoutComponent.ALL_SUBMITTED.append(context)
                result = self._submit_results.pop(0)
                if isinstance(result, Exception):
                    raise result
                return result

            def reconcile(self, attempt_ref):
                self.reconcile_calls.append(attempt_ref)
                return self.reconcile_result

        # Row 2 stands MAPPED to the confirmed operation.
        probe = DownsellActionAdapter(LockoutComponent([]))
        self.assertEqual(probe.binding_point_status("pending_lockout"),
                         "MAPPED")

        # Leg (1), pending_confirmation form: the repeat is rejected
        # by name, never reaches the component, and the standing
        # attempt is unaffected (a further repeat meets the same
        # rejection, and the one submission stands).
        comp = LockoutComponent([{"state": "pending_confirmation"}])
        adapter = DownsellActionAdapter(comp)
        out = adapter.submit_purchase(dict(ctx), dict(entry))
        self.assertEqual(out["state"], "pending")
        self.assertEqual(out["component_state"],
                         "pending_confirmation")
        for _ in range(2):
            with self.assertRaises(AdapterBindingError) as cm:
                adapter.submit_purchase(dict(ctx), dict(entry))
            self.assertEqual(cm.exception.code,
                             "D1-ADAPTER-REPEAT-ATTEMPT-LOCKED-OUT")
        self.assertEqual(len(comp.submit_calls), 1)

        # Leg (1), submitting form: the same rejection while the
        # attempt is still submitting (native state processing).
        comp = LockoutComponent([{"state": "submitting"}])
        adapter = DownsellActionAdapter(comp)
        out = adapter.submit_purchase(dict(ctx), dict(entry))
        self.assertEqual(out["state"], "processing")
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(ctx), dict(entry))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-REPEAT-ATTEMPT-LOCKED-OUT")
        self.assertEqual(len(comp.submit_calls), 1)

        # Leg (2): an unknown outcome blocks every retry until
        # reconciliation is recorded; the recorded resolution to
        # failed admits a fresh submission, which is a new attempt,
        # not a retry of the unknown one.
        comp = LockoutComponent(
            [TimeoutError("submission result unknown"),
             {"state": "failed"}],
            reconcile_result={"state": "failed"})
        adapter = DownsellActionAdapter(comp)
        out = adapter.submit_purchase(dict(ctx), dict(entry))
        self.assertEqual(out["state"], "pending")
        self.assertTrue(out["reconcile_required"])
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(ctx), dict(entry))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-RETRY-BLOCKED-RECONCILE-REQUIRED")
        self.assertEqual(len(comp.submit_calls), 1)
        resolved = adapter.reconcile()
        self.assertEqual(resolved["state"], "failed")
        self.assertTrue(resolved["reconciled"])
        fresh = adapter.submit_purchase(dict(ctx), dict(entry))
        self.assertEqual(fresh["state"], "failed")
        self.assertEqual(len(comp.submit_calls), 2)

        # Leg (3): decline never charges, in each attempt state.
        # No attempt in flight: decline reaches no purchase path.
        comp = LockoutComponent([{"state": "pending_confirmation"}])
        adapter = DownsellActionAdapter(comp)
        out = adapter.decline(dict(ctx))
        self.assertFalse(out["charge_attempted"])
        self.assertFalse(out["component_called"])
        self.assertEqual(comp.submit_calls, [])
        # Attempt pending: decline charges nothing and the standing
        # attempt's one submission remains the only one.
        adapter.submit_purchase(dict(ctx), dict(entry))
        out = adapter.decline(dict(ctx))
        self.assertFalse(out["charge_attempted"])
        self.assertTrue(out["base_order_preserved"])
        self.assertEqual(len(comp.submit_calls), 1)
        # Outcome unknown, reconciliation outstanding: decline still
        # charges nothing, and the reconciliation is still owed.
        comp = LockoutComponent(
            [TimeoutError("submission result unknown")])
        adapter = DownsellActionAdapter(comp)
        adapter.submit_purchase(dict(ctx), dict(entry))
        out = adapter.decline(dict(ctx))
        self.assertFalse(out["charge_attempted"])
        self.assertTrue(out["reconcile_still_required"])
        self.assertEqual(len(comp.submit_calls), 1)

        # No leg of the carrier names or coins a key: no submission
        # context in any exercise above carries one.
        self.assertTrue(LockoutComponent.ALL_SUBMITTED)
        for submitted in LockoutComponent.ALL_SUBMITTED:
            self.assertNotIn("idempotency_key", submitted)

    def test_g12_CR_S81_002_unknown_outcome_reconciliation(self):
        # CR-S81-002, confirmed by revision 2 section 8A.4 of the
        # extra-offer interface contract (S49; SHA-256
        # 07f6b75794a3a8e98aad02a94fb82bcdec78d1264b0a56fa3bda066484b3022f;
        # S06 text concurrence filed, G-5 closed). The confirmed
        # operation: an unknown outcome is carried as
        # pending_confirmation with reconcile_required set (there is
        # NO unknown_outcome state name); its inputs are the parent
        # order reference and the attempt reference; its outputs are
        # resolved paid (on verified native success), resolved
        # failed (when not paid), or still unknown; and no retry is
        # accepted until reconciliation is recorded. The double below
        # implements the confirmed operation's three outputs, and the
        # pin exercises them through the package's adapter, whose
        # reconcile() record shape follows shipped carrier
        # record_reconciliation(found_paid).
        entry = {
            "main_purchased_verified": True,
            "u1_event": "explicit_decline",
            "u1_enabled": True,
            "d1_enabled": True,
            "u2_enabled": True,
            "u1_accepted": False,
        }
        ctx = {"downsell_offer_ref": "TEST-D1-OFFER"}

        class ReconcileComponent:
            """Implements the confirmed section 8A.4 operation: every
            submission's outcome is unknown (timeout), and reconcile
            returns the scripted one of the three outputs."""

            def __init__(self, reconcile_result):
                self.submit_calls = 0
                self.reconcile_calls = []
                self.reconcile_result = reconcile_result

            def submit_purchase(self, context):
                self.submit_calls += 1
                raise TimeoutError("submission result unknown")

            def reconcile(self, attempt_ref):
                self.reconcile_calls.append(attempt_ref)
                return self.reconcile_result

        # Output (a): resolved paid on verified native success.
        comp = ReconcileComponent({
            "state": "paid", "native_transaction_ref": "TEST-TXN-9",
            "native_order_ref": "TEST-ORDER-9",
            "route_result": {"target": "thank_you"}})
        adapter = DownsellActionAdapter(comp)
        out = adapter.submit_purchase(dict(ctx), dict(entry))
        self.assertEqual(out["state"], "pending")
        self.assertEqual(out["component_state"], "pending_confirmation")
        self.assertTrue(out["reconcile_required"])
        self.assertNotIn("unknown_outcome", str(out))
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(ctx), dict(entry))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-RETRY-BLOCKED-RECONCILE-REQUIRED")
        self.assertEqual(comp.submit_calls, 1)
        resolved = adapter.reconcile()
        self.assertEqual(resolved["state"], "succeeded")
        self.assertEqual(resolved["native_transaction_ref"],
                         "TEST-TXN-9")
        self.assertTrue(resolved["reconciled"])
        self.assertFalse(resolved["reconcile_required"])

        # Output (b): resolved failed when not paid; the block lifts
        # and a fresh submission is accepted (and itself goes
        # unknown against this double, never blocked as a retry).
        comp = ReconcileComponent({"state": "failed"})
        adapter = DownsellActionAdapter(comp)
        adapter.submit_purchase(dict(ctx), dict(entry))
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(ctx), dict(entry))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-RETRY-BLOCKED-RECONCILE-REQUIRED")
        self.assertEqual(comp.submit_calls, 1)
        resolved = adapter.reconcile()
        self.assertEqual(resolved["state"], "failed")
        self.assertTrue(resolved["reconciled"])
        self.assertFalse(resolved["reconcile_required"])
        again = adapter.submit_purchase(dict(ctx), dict(entry))
        self.assertEqual(again["state"], "pending")
        self.assertTrue(again["reconcile_required"])
        self.assertEqual(comp.submit_calls, 2)

        # Output (c): still unknown; reconciliation records nothing
        # resolvable and the retry block stays in place.
        comp = ReconcileComponent({"state": "pending_confirmation"})
        adapter = DownsellActionAdapter(comp)
        adapter.submit_purchase(dict(ctx), dict(entry))
        resolved = adapter.reconcile()
        self.assertEqual(resolved["state"], "pending")
        self.assertFalse(resolved["reconciled"])
        self.assertTrue(resolved["reconcile_required"])
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(ctx), dict(entry))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-RETRY-BLOCKED-RECONCILE-REQUIRED")
        self.assertEqual(comp.submit_calls, 1)


if __name__ == "__main__":
    unittest.main()
