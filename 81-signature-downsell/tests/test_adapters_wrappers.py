"""S81-05 adapter wrappers: the shared action wrapper and the S06
install wrapper, reconciled against the confirmed binding map
(adapters/provisional-binding-map.md, replaced in place 2026-10-17:
6 MAPPED, 0 PARTIAL, 0 UNMAPPED against the confirmed S79/S06
contract, revision 1 as completed by revision 2 section 8A, SHA-256
07f6b75794a3a8e98aad02a94fb82bcdec78d1264b0a56fa3bda066484b3022f).

Pins: MAPPED points pass through (entry-guard eligibility per
CR-S81-003 / section 8A.1, honored allow and refusal alike; decline
recording per CR-S81-004 / section 8A.2, the record permanently
distinct from failed); the pending lockout point (row 2,
CR-S81-001) passes through to the confirmed section 8A.5 submission
operation: its disposition was accepted under
S81-DEC-G4-SUBDISP-01 and the staged wrapper edits executed in the
follow-on cycle on the landing of the candidate carrying revision 2
(PR #2228, train #2235), so the lockout pins below pin the
confirmed carrier discipline (a repeat while pending is rejected
before the submission point is invoked and never reaches the
component); decline carries no charge
and never calls the purchase point; an unknown outcome surfaces as
pending_confirmation with reconcile_required set, per the confirmed
section 8A.4 (no unknown_outcome state name exists), and blocks
retry until reconciliation is recorded (the cross-file pin lives in
test_d1_route_law_pins.py); a paid claim without native read-backs,
or without the section 8A.6 route-result output, is never admitted
as succeeded, and the succeeded route is sourced from that output,
never from the request (CR-S81-007).

Follow-on pins (review-s81-05-wrappers-0340.md defect D-b): the five
fail-closed branches that shipped without a pinning test are pinned
by name below, in FailClosedBranchPinTests and
InstallFailClosedPinTests: D1-ADAPTER-ROUTE-U2-WITHOUT-CANONICAL-ID,
D1-ADAPTER-MALFORMED-RESULT, D1-ADAPTER-UNKNOWN-POINT,
D1-INSTALL-U2-ID-MISSING, and D1-INSTALL-BUNDLE-UNIDENTIFIED. Each
pin carries a paired contrast showing the same call is admitted when
the missing piece is supplied, so the pin bites on the branch itself.

The component double below is a test fixture only: it records calls
and returns scripted results in the draft's section 4 vocabulary. It
is not a charge implementation and proves nothing about a live native
action. Run with the rest of the suite: python3 -m unittest discover
-s tests -v
"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "adapters"))
sys.path.insert(0, str(ROOT / "validators"))

import shared_action_wrapper  # noqa: E402
from shared_action_wrapper import (  # noqa: E402
    BINDING_POINTS, AdapterBindingError, DownsellActionAdapter)
from s06_install_wrapper import (  # noqa: E402
    InstallPlanError, build_install_plan)

FIXTURES = ROOT / "fixtures"

GOOD_ENTRY = {
    "main_purchased_verified": True,
    "u1_event": "explicit_decline",
    "u1_enabled": True,
    "d1_enabled": True,
    "u2_enabled": True,
    "u1_accepted": False,
}

PAID = {"state": "paid", "native_transaction_ref": "TEST-TXN-1",
        "native_order_ref": "TEST-ORDER-1",
        # The component's route-result output (revision 2 section
        # 8A.6): the route is sourced from here, never from the
        # request context.
        "route_result": {"target": "upsell_2",
                         "canonical_u2_page_id": "TEST-UPSELL_2",
                         "entry_context": "from_downsell_1"}}

CTX_U2 = {"downsell_offer_ref": "TEST-D1-OFFER", "success_route": "upsell_2",
          "canonical_u2_page_id": "TEST-UPSELL_2"}


class FakeComponent:
    """Scripted shared-component double. Records every call so tests
    can prove what the wrapper did and did not invoke."""

    def __init__(self, submit_results=(), read_value=None,
                 reconcile_value=None, disclosure_value=None,
                 eligibility_value=True):
        self.submit_calls = []
        self.read_calls = []
        self.reconcile_calls = []
        self.disclosure_calls = []
        self.confirm_calls = []
        self.decline_calls = []
        self._submit_results = list(submit_results)
        self.read_value = read_value
        self.reconcile_value = reconcile_value
        self.eligibility_value = eligibility_value
        self.disclosure_value = disclosure_value or {
            # The section 3 disclosure data set as audited by
            # revision 2 section 8A.7 (all seven criteria fields).
            "amount_due_now_minor": 3700, "currency": "USD",
            "billing_type": "one_time",
            "terms": "one-time charge, no renewal",
            "total_due_now_minor": 3700,
            "refund_policy_ref": "TEST-REFUND-POLICY",
            "cancellation_terms": "no recurring charge to cancel",
            "shown_before_authorization": True}

    @staticmethod
    def _next(value):
        if isinstance(value, Exception):
            raise value
        return value

    def submit_purchase(self, context):
        self.submit_calls.append(context)
        return self._next(self._submit_results.pop(0))

    def read_result(self, attempt_ref):
        self.read_calls.append(attempt_ref)
        return self._next(self.read_value)

    def reconcile(self, attempt_ref):
        self.reconcile_calls.append(attempt_ref)
        return self._next(self.reconcile_value)

    def price_disclosure(self, context):
        self.disclosure_calls.append(context)
        return self._next(self.disclosure_value)

    def confirm_entry_eligibility(self, entry_state):
        self.confirm_calls.append(entry_state)
        return self.eligibility_value

    def decline(self, context):
        self.decline_calls.append(context)
        # The confirmed decline result record (revision 2 section
        # 8A.2): outcome declined, the offer's identity, the parent
        # order's reference, the record that no charge was attempted,
        # and the route actually taken.
        return {"outcome": "declined",
                "offer_ref": context.get("downsell_offer_ref"),
                "parent_order_ref": "TEST-ORDER-1",
                "charge_attempted": False,
                "route": "thank_you"}


class BindingMapShapeTests(unittest.TestCase):
    def test_map_counts_match_the_confirmed_record(self):
        statuses = [p["status"] for p in BINDING_POINTS.values()]
        self.assertEqual(statuses.count("MAPPED"), 6)
        self.assertEqual(statuses.count("PARTIAL"), 0)
        self.assertEqual(statuses.count("UNMAPPED"), 0)
        # Row 2 moved on CR-S81-001's follow-on execution: MAPPED to
        # the confirmed submission operation (section 8A.5).
        self.assertEqual(BINDING_POINTS["pending_lockout"]["status"],
                         "MAPPED")
        self.assertEqual(BINDING_POINTS["pending_lockout"]["hook"],
                         "submit_purchase")


class MappedPassThroughTests(unittest.TestCase):
    def test_disclosure_passes_through(self):
        comp = FakeComponent()
        adapter = DownsellActionAdapter(comp)
        out = adapter.price_disclosure({"offer": "TEST-D1-OFFER"})
        self.assertEqual(out, comp.disclosure_value)
        self.assertEqual(len(comp.disclosure_calls), 1)

    def test_status_read_passes_through_and_translates_paid(self):
        comp = FakeComponent(read_value=dict(PAID))
        adapter = DownsellActionAdapter(comp)
        out = adapter.read_status("d1-attempt-1")
        self.assertEqual(out["state"], "succeeded")
        self.assertEqual(out["native_transaction_ref"], "TEST-TXN-1")
        # The route on a read comes from the result's own
        # route-result output (section 8A.6), component-confirmed.
        self.assertEqual(out["route"]["target"], "upsell_2")
        self.assertTrue(out["route_result_confirmed"])
        self.assertEqual(comp.read_calls, ["d1-attempt-1"])

    def test_reconcile_passes_through(self):
        comp = FakeComponent(reconcile_value={"state": "failed"})
        adapter = DownsellActionAdapter(comp)
        out = adapter.reconcile("d1-attempt-1")
        self.assertEqual(out["state"], "failed")
        self.assertTrue(out["reconciled"])
        self.assertEqual(comp.reconcile_calls, ["d1-attempt-1"])

    def test_succeeded_routes_to_same_canonical_u2(self):
        comp = FakeComponent(submit_results=[dict(PAID)])
        adapter = DownsellActionAdapter(comp)
        out = adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(out["state"], "succeeded")
        self.assertEqual(out["route"]["target"], "upsell_2")
        self.assertEqual(out["route"]["canonical_u2_page_id"],
                         "TEST-UPSELL_2")
        self.assertEqual(out["route"]["entry_context"],
                         "from_downsell_1")
        # CR-S81-007: the route is sourced from the component's
        # route-result output (revision 2 section 8A.6), so it IS
        # component-confirmed evidence.
        self.assertTrue(out["route_result_confirmed"])

    def test_entry_guard_passes_through_and_honors_allow(self):
        comp = FakeComponent(eligibility_value={
            "allowed": True, "failed_conditions": []})
        adapter = DownsellActionAdapter(comp)
        out = adapter.confirm_entry_eligibility(dict(GOOD_ENTRY))
        self.assertEqual(out, {"allowed": True, "failed_conditions": []})
        self.assertEqual(comp.confirm_calls, [dict(GOOD_ENTRY)])

    def test_entry_guard_honors_refusal_as_a_normal_outcome(self):
        # Revision 2 section 8A.1: refusal is a normal reported
        # outcome naming the failed condition(s), not an error. A
        # failed U1 payment expressly does not satisfy the decline
        # condition, so it is the refusal the component reports.
        refusal = {"allowed": False,
                   "failed_conditions": ["u1_event_not_explicit_decline"]}
        comp = FakeComponent(eligibility_value=refusal)
        adapter = DownsellActionAdapter(comp)
        bad_entry = dict(GOOD_ENTRY, u1_event="payment_failed")
        out = adapter.confirm_entry_eligibility(bad_entry)
        self.assertEqual(out, refusal)
        self.assertEqual(comp.confirm_calls, [bad_entry])

    def test_record_decline_passes_through(self):
        comp = FakeComponent()
        adapter = DownsellActionAdapter(comp)
        out = adapter.record_decline(dict(CTX_U2))
        self.assertEqual(out["outcome"], "declined")
        self.assertEqual(out["offer_ref"], "TEST-D1-OFFER")
        self.assertEqual(out["parent_order_ref"], "TEST-ORDER-1")
        self.assertFalse(out["charge_attempted"])
        self.assertEqual(out["route"], "thank_you")
        self.assertEqual(comp.decline_calls, [dict(CTX_U2)])

    def test_pending_lockout_point_passes_through_to_submit(self):
        # Row 2 (CR-S81-001, revision 2 section 8A.5): the point is
        # MAPPED to the confirmed submission operation, and invoking
        # the point passes through to the component's submit hook,
        # returning its result. Deliberately rewritten from the
        # staged fail-closed pin on the follow-on execution.
        comp = FakeComponent(
            submit_results=[{"state": "pending_confirmation"}])
        adapter = DownsellActionAdapter(comp)
        out = adapter.call_point("pending_lockout", dict(CTX_U2))
        self.assertEqual(out, {"state": "pending_confirmation"})
        self.assertEqual(comp.submit_calls, [dict(CTX_U2)])
        self.assertEqual(
            adapter.binding_point_status("pending_lockout"), "MAPPED")


class FailClosedPointTests(unittest.TestCase):
    def test_entry_guard_hook_missing_fails_closed(self):
        # Row 1 is MAPPED, but a component that does not expose the
        # confirmed hook fails closed; no substitute call is invented.
        class Bare:
            pass

        adapter = DownsellActionAdapter(Bare())
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.confirm_entry_eligibility(dict(GOOD_ENTRY))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-POINT-NOT-PROVIDED")

    def test_decline_hook_missing_fails_closed(self):
        class Bare:
            pass

        adapter = DownsellActionAdapter(Bare())
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.record_decline(dict(CTX_U2))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-POINT-NOT-PROVIDED")

    def test_abandonment_is_never_translated_to_a_decline(self):
        # CR-S81-005 (revision 2 section 8A.3): abandonment records
        # no outcome and no decline event may be fabricated from it;
        # a component state of "abandoned" has no D1 carrier and
        # fails closed rather than being relabeled explicit_decline.
        comp = FakeComponent(read_value={"state": "abandoned"})
        adapter = DownsellActionAdapter(comp)
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.read_status("d1-attempt-1")
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-UNRECOGNIZED-RESULT-STATE")

    def test_paid_without_native_readback_fails_closed(self):
        comp = FakeComponent(submit_results=[{"state": "paid"}])
        adapter = DownsellActionAdapter(comp)
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-PAID-WITHOUT-NATIVE-READBACK")

    def test_unrecognized_component_state_fails_closed(self):
        comp = FakeComponent(read_value={"state": "cancelled"})
        adapter = DownsellActionAdapter(comp)
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.read_status("d1-attempt-1")
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-UNRECOGNIZED-RESULT-STATE")

    def test_missing_hook_on_mapped_point_fails_closed(self):
        class Bare:
            pass

        adapter = DownsellActionAdapter(Bare())
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.price_disclosure({})
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-POINT-NOT-PROVIDED")


class DeclineTests(unittest.TestCase):
    def test_decline_never_charges_and_never_calls_purchase(self):
        comp = FakeComponent(submit_results=[dict(PAID)])
        adapter = DownsellActionAdapter(comp)
        out = adapter.decline(dict(CTX_U2))
        self.assertEqual(out["state"], "explicit_decline")
        self.assertEqual(out["route"], "thank_you")
        self.assertFalse(out["charge_attempted"])
        self.assertFalse(out["component_called"])
        self.assertTrue(out["base_order_preserved"])
        self.assertEqual(comp.submit_calls, [])
        self.assertEqual(comp.decline_calls, [])

    def test_failed_attempt_is_never_recorded_as_decline(self):
        comp = FakeComponent(submit_results=[{"state": "failed"},
                                             dict(PAID)])
        adapter = DownsellActionAdapter(comp)
        out = adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(out["state"], "failed")
        # A failure leaves the attempt closed and retry permitted; it
        # is not an acceptance and not a decline.
        out2 = adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(out2["state"], "succeeded")
        self.assertEqual(len(comp.submit_calls), 2)

    def test_decline_mid_attempt_and_reconcile_outstanding(self):
        # Step 3 matrix item 4: decline() with an attempt in flight
        # and with reconcile_required outstanding still charges
        # nothing, calls no purchase point, preserves the base
        # order, and routes to thank-you; with reconciliation
        # outstanding it also reports that the reconciliation is
        # still owed (declining does not clear it).
        comp = FakeComponent(
            submit_results=[{"state": "pending_confirmation"}])
        adapter = DownsellActionAdapter(comp)
        adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        out = adapter.decline(dict(CTX_U2))
        self.assertEqual(out["state"], "explicit_decline")
        self.assertEqual(out["route"], "thank_you")
        self.assertFalse(out["charge_attempted"])
        self.assertTrue(out["base_order_preserved"])
        self.assertNotIn("reconcile_still_required", out)
        self.assertEqual(len(comp.submit_calls), 1)

        comp2 = FakeComponent(
            submit_results=[TimeoutError("dropped connection")])
        adapter2 = DownsellActionAdapter(comp2)
        adapter2.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        out2 = adapter2.decline(dict(CTX_U2))
        self.assertEqual(out2["state"], "explicit_decline")
        self.assertEqual(out2["route"], "thank_you")
        self.assertFalse(out2["charge_attempted"])
        self.assertTrue(out2["base_order_preserved"])
        self.assertTrue(out2["reconcile_still_required"])
        self.assertEqual(len(comp2.submit_calls), 1)

    def test_confirmed_decline_record_is_distinct_from_failed(self):
        # CR-S81-004 (revision 2 section 8A.2): the decline result
        # record is permanently distinct from a failed attempt
        # record, and carries the express no-charge record with the
        # parent order reference.
        comp = FakeComponent(submit_results=[{"state": "failed"}])
        adapter = DownsellActionAdapter(comp)
        failed = adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(failed["state"], "failed")
        record = adapter.record_decline(dict(CTX_U2))
        self.assertEqual(record["outcome"], "declined")
        self.assertNotEqual(record["outcome"], failed["state"])
        self.assertFalse(record["charge_attempted"])
        self.assertEqual(record["parent_order_ref"], "TEST-ORDER-1")
        self.assertEqual(record["route"], "thank_you")


class RouteResultTests(unittest.TestCase):
    """CR-S81-007 (revision 2 section 8A.6): the paid route is
    sourced from the component's route-result output, never from the
    request; no output, or an output contradicting the plan, is a
    reported failure of the action."""

    def test_paid_without_route_result_fails_closed(self):
        paid = {"state": "paid",
                "native_transaction_ref": "TEST-TXN-1",
                "native_order_ref": "TEST-ORDER-1"}
        comp = FakeComponent(submit_results=[paid])
        adapter = DownsellActionAdapter(comp)
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-ROUTE-RESULT-MISSING")

    def test_route_result_contradicting_plan_fails_closed(self):
        variants = [
            # The plan enables the canonical U2 route; the output
            # routes to the final thank-you step instead.
            {"target": "thank_you"},
            # The output names a different U2 identity than the
            # plan's canonical U2 page.
            {"target": "upsell_2",
             "canonical_u2_page_id": "TEST-OTHER-U2",
             "entry_context": "from_downsell_1"},
            # The output names a target no D1 paid plan can contain.
            {"target": "upsell_1"},
        ]
        for route_result in variants:
            with self.subTest(route_result=route_result):
                paid = dict(PAID, route_result=route_result)
                comp = FakeComponent(submit_results=[paid])
                adapter = DownsellActionAdapter(comp)
                with self.assertRaises(AdapterBindingError) as cm:
                    adapter.submit_purchase(dict(CTX_U2),
                                            dict(GOOD_ENTRY))
                self.assertEqual(
                    cm.exception.code,
                    "D1-ADAPTER-ROUTE-RESULT-CONTRADICTS-PLAN")

    def test_paid_routes_to_thank_you_when_the_output_says_so(self):
        ctx = {"downsell_offer_ref": "TEST-D1-OFFER",
               "success_route": "thank_you"}
        paid = dict(PAID, route_result={"target": "thank_you"})
        comp = FakeComponent(submit_results=[paid])
        adapter = DownsellActionAdapter(comp)
        out = adapter.submit_purchase(ctx, dict(GOOD_ENTRY))
        self.assertEqual(out["state"], "succeeded")
        self.assertEqual(out["route"], {"target": "thank_you"})
        self.assertTrue(out["route_result_confirmed"])


class DisclosureAuditPinTests(unittest.TestCase):
    """CR-S81-008 (revision 2 section 8A.7): the disclosure surfaced
    through the wrapper carries every field the billing-display
    audit checks: (1) the amount due, (2) the currency, (3) the
    terms as bound, (4) a total that is not understated against the
    amount due, (5) the policy data, (6) the cancellation terms,
    (7) shown before authorization. Placement of the disclosure on
    the page is page-layer under the section 8A.7 ruling and is not
    pinned here; the audit result is an output of the action."""

    CRITERIA_FIELDS = ["amount_due_now_minor", "currency",
                       "billing_type", "terms", "total_due_now_minor",
                       "refund_policy_ref", "cancellation_terms",
                       "shown_before_authorization"]

    def test_surfaced_disclosure_carries_every_criterion_field(self):
        comp = FakeComponent()
        adapter = DownsellActionAdapter(comp)
        out = adapter.price_disclosure({"offer": "TEST-D1-OFFER"})
        for field in self.CRITERIA_FIELDS:
            self.assertIn(field, out)
        self.assertGreaterEqual(out["total_due_now_minor"],
                                out["amount_due_now_minor"])
        self.assertTrue(out["shown_before_authorization"])

    def test_a_missing_criterion_field_is_detectable(self):
        # The pin bites: remove any one criterion field and the
        # field check fails for exactly that field, so a disclosure
        # missing a field is never presented as audit-passing.
        comp = FakeComponent()
        full = comp.disclosure_value
        for field in self.CRITERIA_FIELDS:
            with self.subTest(missing=field):
                reduced = {k: v for k, v in full.items() if k != field}
                missing = [f for f in self.CRITERIA_FIELDS
                           if f not in reduced]
                self.assertEqual(missing, [field])


class LockoutAndReconcileRequiredTests(unittest.TestCase):
    def test_repeat_attempt_locks_out_while_pending(self):
        comp = FakeComponent(
            submit_results=[{"state": "pending_confirmation"}])
        adapter = DownsellActionAdapter(comp)
        out = adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(out["state"], "pending")
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-REPEAT-ATTEMPT-LOCKED-OUT")
        self.assertEqual(len(comp.submit_calls), 1)

    def test_repeat_attempt_locks_out_while_submitting(self):
        comp = FakeComponent(submit_results=[{"state": "submitting"}])
        adapter = DownsellActionAdapter(comp)
        out = adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(out["state"], "processing")
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-REPEAT-ATTEMPT-LOCKED-OUT")
        self.assertEqual(len(comp.submit_calls), 1)

    def test_timeout_surfaces_pending_confirmation_reconcile_required(self):
        # CR-S81-002 as answered by S79 (2026-10-17): the shipped
        # contract has NO unknown_outcome state name; an unknown
        # outcome rides as pending_confirmation + reconcile_required,
        # and retry is refused until reconciliation is recorded.
        comp = FakeComponent(
            submit_results=[TimeoutError("dropped connection"),
                            dict(PAID)],
            reconcile_value={"state": "failed"})
        adapter = DownsellActionAdapter(comp)
        out = adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(out["state"], "pending")
        self.assertEqual(out["component_state"], "pending_confirmation")
        self.assertTrue(out["reconcile_required"])
        self.assertTrue(out["retry_blocked"])
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-RETRY-BLOCKED-RECONCILE-REQUIRED")
        self.assertEqual(len(comp.submit_calls), 1)
        resolved = adapter.reconcile()
        self.assertEqual(resolved["state"], "failed")
        self.assertTrue(resolved["reconciled"])
        self.assertFalse(resolved["reconcile_required"])
        out2 = adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(out2["state"], "succeeded")
        self.assertEqual(len(comp.submit_calls), 2)

    def test_read_timeout_surfaces_reconcile_required(self):
        # Step 3 matrix item 2, read leg: a read that times out also
        # makes the attempt's outcome unknown, surfaced as
        # pending_confirmation + reconcile_required, and retry is
        # blocked until reconciliation is recorded.
        comp = FakeComponent(read_value=TimeoutError("read timed out"))
        adapter = DownsellActionAdapter(comp)
        out = adapter.read_status("d1-attempt-1")
        self.assertEqual(out["state"], "pending")
        self.assertEqual(out["component_state"], "pending_confirmation")
        self.assertTrue(out["reconcile_required"])
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-RETRY-BLOCKED-RECONCILE-REQUIRED")
        self.assertEqual(comp.submit_calls, [])

    def test_unresolved_reconciliation_keeps_the_block(self):
        comp = FakeComponent(
            submit_results=[TimeoutError("dropped connection")],
            reconcile_value=TimeoutError("still unreachable"))
        adapter = DownsellActionAdapter(comp)
        adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        out = adapter.reconcile()
        self.assertEqual(out["state"], "pending")
        self.assertEqual(out["component_state"], "pending_confirmation")
        self.assertFalse(out["reconciled"])
        self.assertTrue(out["reconcile_required"])
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-RETRY-BLOCKED-RECONCILE-REQUIRED")
        # A reconciliation that records nothing resolvable (the native
        # records still show the attempt in flight) also keeps it.
        comp.reconcile_value = {"state": "pending_confirmation"}
        out2 = adapter.reconcile()
        self.assertFalse(out2["reconciled"])
        self.assertTrue(out2["reconcile_required"])
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-RETRY-BLOCKED-RECONCILE-REQUIRED")

    def test_no_idempotency_key_is_coined_and_gap_label_retired(self):
        # CR-S81-001 as closed by revision 2 section 8A.5: where an
        # interface of this kind would name an idempotency key, the
        # contract names the attempt-integrity carrier instead, so
        # the wrapper coins no key and adds none to the caller's
        # context; and the staged gap label that stood open while
        # the follow-on edits were staged is retired: the wrapper
        # module no longer carries it, and the lockout refusal no
        # longer names it.
        self.assertFalse(hasattr(shared_action_wrapper,
                                 "IDEMPOTENCY_KEY_GAP"))
        comp = FakeComponent(submit_results=[dict(PAID)])
        adapter = DownsellActionAdapter(comp)
        adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertNotIn("idempotency_key", comp.submit_calls[0])
        comp2 = FakeComponent(
            submit_results=[{"state": "pending_confirmation"}])
        adapter2 = DownsellActionAdapter(comp2)
        adapter2.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        with self.assertRaises(AdapterBindingError) as cm:
            adapter2.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-REPEAT-ATTEMPT-LOCKED-OUT")
        self.assertNotIn("IDEMPOTENCY", str(cm.exception))

    def test_second_submit_after_success_is_refused(self):
        comp = FakeComponent(submit_results=[dict(PAID), dict(PAID)])
        adapter = DownsellActionAdapter(comp)
        adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-ALREADY-SUCCEEDED")
        self.assertEqual(len(comp.submit_calls), 1)


class EntryGuardTests(unittest.TestCase):
    def test_ineligible_entry_is_refused_without_component_call(self):
        comp = FakeComponent(submit_results=[dict(PAID)])
        adapter = DownsellActionAdapter(comp)
        bad_entry = dict(GOOD_ENTRY, u1_event="payment_failed")
        out = adapter.submit_purchase(dict(CTX_U2), bad_entry)
        self.assertEqual(out["state"], "refused")
        self.assertIn("D1-GUARD-NO-EXPLICIT-U1-DECLINE",
                      out["violations"])
        self.assertFalse(out["charge_attempted"])
        self.assertEqual(comp.submit_calls, [])


def _valid_request():
    return json.loads(
        (FIXTURES / "valid-downsell-request.json").read_text())


def _valid_binding():
    return {"native_product_id": "TEST-NATIVE-PRODUCT",
            "native_price_id": "TEST-NATIVE-PRICE"}


def _valid_bundle():
    return {"bundle_ref": "TEST-D1-BUNDLE",
            "action_refs": {"purchase_action_ref": "native-d1-action",
                            "decline_action_ref": "native-decline-d1"},
            "canonical_u2_page_id": "TEST-UPSELL_2"}


class InstallPlanTests(unittest.TestCase):
    def test_plan_builds_and_is_plan_only(self):
        plan = build_install_plan(_valid_request(), _valid_binding(),
                                  _valid_bundle())
        self.assertEqual(plan["plan_kind"], "s06-install-plan")
        self.assertTrue(plan["provisional"])
        self.assertFalse(plan["executes_install"])
        self.assertFalse(plan["network_calls"])
        self.assertEqual(plan["product_binding"]["binding_source"],
                         "caller_supplied")
        self.assertEqual(plan["product_binding"]["native_price_id"],
                         "TEST-NATIVE-PRICE")
        step_names = [s["step"] for s in plan["steps"]]
        self.assertEqual(step_names[-1], "read_back_binding")
        self.assertTrue(plan["binding_readback"]["required"])
        self.assertFalse(plan["binding_readback"]["recorded"])
        # CR-S81-009 as reconciled: the read-back carrier for extra
        # offers is CONFIRMED (revision 2 section 8A.8); recorded
        # stays False and the recordable result slot stays None,
        # because no install read-back exists for this package.
        self.assertEqual(plan["binding_readback"]["carrier_status"],
                         "CONFIRMED_R2_SECTION_8A.8_BINDING_READBACK")
        self.assertIsNone(plan["binding_readback"]["result"])
        readback_step = plan["steps"][-1]
        self.assertEqual(readback_step["carrier_status"],
                         "CONFIRMED_R2_SECTION_8A.8_BINDING_READBACK")
        self.assertIsNone(readback_step["result"])
        self.assertEqual(plan["routes"]["decline"], "thank_you")
        self.assertEqual(plan["routes"]["u2_entry_context"],
                         "from_downsell_1")

    def test_missing_binding_fails_closed(self):
        with self.assertRaises(InstallPlanError) as cm:
            build_install_plan(_valid_request(), {}, _valid_bundle())
        self.assertEqual(cm.exception.code, "D1-INSTALL-BINDING-MISSING")

    def test_binding_mismatch_fails_closed(self):
        request = _valid_request()
        request["native_product_id"] = "TEST-OTHER-PRODUCT"
        with self.assertRaises(InstallPlanError) as cm:
            build_install_plan(request, _valid_binding(), _valid_bundle())
        self.assertEqual(cm.exception.code, "D1-INSTALL-BINDING-MISMATCH")

    def test_live_target_is_refused(self):
        request = _valid_request()
        request["allowed_write_target"] = "approved_live_publication"
        with self.assertRaises(InstallPlanError) as cm:
            build_install_plan(request, _valid_binding(), _valid_bundle())
        self.assertEqual(cm.exception.code,
                         "D1-INSTALL-LIVE-TARGET-REFUSED")

    def test_decline_ref_equal_to_purchase_ref_fails_closed(self):
        bundle = _valid_bundle()
        bundle["action_refs"]["decline_action_ref"] = "native-d1-action"
        with self.assertRaises(InstallPlanError) as cm:
            build_install_plan(_valid_request(), _valid_binding(), bundle)
        self.assertEqual(cm.exception.code,
                         "D1-INSTALL-DECLINE-IS-PURCHASE-ACTION")

    def test_missing_request_field_fails_closed_by_name(self):
        request = _valid_request()
        del request["tenant_id"]
        with self.assertRaises(InstallPlanError) as cm:
            build_install_plan(request, _valid_binding(), _valid_bundle())
        self.assertEqual(cm.exception.code,
                         "D1-INSTALL-REQUEST-MISSING-FIELDS")
        self.assertIn("tenant_id", cm.exception.missing)

    def test_wrong_page_role_fails_closed(self):
        request = _valid_request()
        request["page_role"] = "upsell_1"
        with self.assertRaises(InstallPlanError) as cm:
            build_install_plan(request, _valid_binding(), _valid_bundle())
        self.assertEqual(cm.exception.code,
                         "D1-INSTALL-REQUEST-PAGE-ROLE")

    def test_request_fixture_is_not_mutated(self):
        request = _valid_request()
        snapshot = copy.deepcopy(request)
        build_install_plan(request, _valid_binding(), _valid_bundle())
        self.assertEqual(request, snapshot)


class FailClosedBranchPinTests(unittest.TestCase):
    """Pins for the fail-closed adapter branches review D-b found
    untested (review-s81-05-wrappers-0340.md). Every pin asserts the
    exact named code, and each carries a paired contrast showing the
    same call is admitted once the missing piece is supplied, so the
    pin bites on the branch itself, not on the surrounding flow."""

    def test_route_u2_without_canonical_id_fails_closed(self):
        # As reconciled (CR-S81-007): the canonical identity must
        # come from the component's route-result output (revision 2
        # section 8A.6). An output routing to upsell_2 without it
        # fails closed at admission.
        paid = dict(PAID, route_result={
            "target": "upsell_2", "entry_context": "from_downsell_1"})
        comp = FakeComponent(submit_results=[paid])
        adapter = DownsellActionAdapter(comp)
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-ROUTE-U2-WITHOUT-CANONICAL-ID")
        # The component DID return paid; the refusal is at admission.
        # The paid claim is not admitted as succeeded: the attempt is
        # still in flight, so a repeat is locked out, never admitted.
        self.assertEqual(len(comp.submit_calls), 1)
        with self.assertRaises(AdapterBindingError) as cm2:
            adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(cm2.exception.code,
                         "D1-ADAPTER-REPEAT-ATTEMPT-LOCKED-OUT")
        # Contrast (mutation check): the identical paid result whose
        # route-result output names the canonical id is admitted and
        # routes to that same U2, component-confirmed.
        comp2 = FakeComponent(submit_results=[dict(PAID)])
        adapter2 = DownsellActionAdapter(comp2)
        out = adapter2.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(out["state"], "succeeded")
        self.assertEqual(out["route"]["canonical_u2_page_id"],
                         "TEST-UPSELL_2")
        self.assertTrue(out["route_result_confirmed"])

    def test_route_u2_with_blank_canonical_id_fails_closed(self):
        for blank in ("", "   ", None):
            with self.subTest(canonical_u2_page_id=blank):
                paid = dict(PAID, route_result={
                    "target": "upsell_2",
                    "canonical_u2_page_id": blank,
                    "entry_context": "from_downsell_1"})
                comp = FakeComponent(submit_results=[paid])
                adapter = DownsellActionAdapter(comp)
                with self.assertRaises(AdapterBindingError) as cm:
                    adapter.submit_purchase(dict(CTX_U2),
                                            dict(GOOD_ENTRY))
                self.assertEqual(
                    cm.exception.code,
                    "D1-ADAPTER-ROUTE-U2-WITHOUT-CANONICAL-ID")

    def test_malformed_result_fails_closed_on_read(self):
        bad_results = [None, "paid", ["paid"], {}, {"state": None},
                       {"state": ""}, {"state": "   "}]
        for raw in bad_results:
            with self.subTest(raw=raw):
                comp = FakeComponent(read_value=raw)
                adapter = DownsellActionAdapter(comp)
                with self.assertRaises(AdapterBindingError) as cm:
                    adapter.read_status("d1-attempt-1")
                self.assertEqual(cm.exception.code,
                                 "D1-ADAPTER-MALFORMED-RESULT")
                # The component was consulted; nothing was admitted
                # from what it returned.
                self.assertEqual(comp.read_calls, ["d1-attempt-1"])

    def test_malformed_result_fails_closed_on_submit_and_reconcile(self):
        comp = FakeComponent(submit_results=[{"state": ""}])
        adapter = DownsellActionAdapter(comp)
        with self.assertRaises(AdapterBindingError) as cm:
            adapter.submit_purchase(dict(CTX_U2), dict(GOOD_ENTRY))
        self.assertEqual(cm.exception.code,
                         "D1-ADAPTER-MALFORMED-RESULT")

        comp2 = FakeComponent(reconcile_value={"unexpected": True})
        adapter2 = DownsellActionAdapter(comp2)
        with self.assertRaises(AdapterBindingError) as cm2:
            adapter2.reconcile("d1-attempt-1")
        self.assertEqual(cm2.exception.code,
                         "D1-ADAPTER-MALFORMED-RESULT")

    def test_unknown_point_fails_closed_by_name(self):
        comp = FakeComponent()
        adapter = DownsellActionAdapter(comp)
        for point in ("no_such_point", "verified_results", ""):
            with self.subTest(point=point):
                with self.assertRaises(AdapterBindingError) as cm:
                    adapter.call_point(point)
                self.assertEqual(cm.exception.code,
                                 "D1-ADAPTER-UNKNOWN-POINT")
                with self.assertRaises(AdapterBindingError) as cm2:
                    adapter.binding_point_status(point)
                self.assertEqual(cm2.exception.code,
                                 "D1-ADAPTER-UNKNOWN-POINT")
        # An unknown point never reaches the component at all.
        self.assertEqual(comp.submit_calls, [])
        self.assertEqual(comp.read_calls, [])
        self.assertEqual(comp.reconcile_calls, [])
        self.assertEqual(comp.disclosure_calls, [])
        self.assertEqual(comp.confirm_calls, [])
        self.assertEqual(comp.decline_calls, [])
        # Contrast: known points answer their status without raising.
        self.assertEqual(adapter.binding_point_status("disclosure"),
                         "MAPPED")
        self.assertEqual(adapter.binding_point_status("decline"),
                         "MAPPED")
        self.assertEqual(adapter.binding_point_status("pending_lockout"),
                         "MAPPED")


class InstallFailClosedPinTests(unittest.TestCase):
    """Pins for the two untested install-wrapper branches named in
    review D-b, with the same exact-code + paired-contrast discipline
    as FailClosedBranchPinTests."""

    def test_u2_id_missing_fails_closed(self):
        bundle = _valid_bundle()
        del bundle["canonical_u2_page_id"]
        with self.assertRaises(InstallPlanError) as cm:
            build_install_plan(_valid_request(), _valid_binding(),
                               bundle)
        self.assertEqual(cm.exception.code, "D1-INSTALL-U2-ID-MISSING")

    def test_u2_id_blank_fails_closed(self):
        for blank in ("", "   ", None):
            with self.subTest(canonical_u2_page_id=blank):
                bundle = _valid_bundle()
                bundle["canonical_u2_page_id"] = blank
                with self.assertRaises(InstallPlanError) as cm:
                    build_install_plan(_valid_request(),
                                       _valid_binding(), bundle)
                self.assertEqual(cm.exception.code,
                                 "D1-INSTALL-U2-ID-MISSING")
        # Contrast (mutation check): with the id supplied, the same
        # inputs build a plan carrying that exact id.
        plan = build_install_plan(_valid_request(), _valid_binding(),
                                  _valid_bundle())
        self.assertEqual(plan["routes"]["canonical_u2_page_id"],
                         "TEST-UPSELL_2")

    def test_u2_id_not_required_when_route_is_thank_you(self):
        # Specificity pin: the branch fires only for the upsell_2
        # route; a thank_you route plans fine with no U2 id at all.
        request = _valid_request()
        request["success_route"] = "thank_you"
        bundle = _valid_bundle()
        del bundle["canonical_u2_page_id"]
        plan = build_install_plan(request, _valid_binding(), bundle)
        self.assertEqual(plan["routes"]["success"], "thank_you")
        self.assertIsNone(plan["routes"]["canonical_u2_page_id"])

    def test_bundle_unidentified_fails_closed(self):
        action_refs = {"purchase_action_ref": "native-d1-action",
                       "decline_action_ref": "native-decline-d1"}
        bad_bundles = [
            # Neither bundle_ref nor content_hash present.
            {"action_refs": dict(action_refs),
             "canonical_u2_page_id": "TEST-UPSELL_2"},
            # Both present but blank.
            {"bundle_ref": "", "content_hash": "   ",
             "action_refs": dict(action_refs),
             "canonical_u2_page_id": "TEST-UPSELL_2"},
            # Both present but null.
            {"bundle_ref": None, "content_hash": None,
             "action_refs": dict(action_refs),
             "canonical_u2_page_id": "TEST-UPSELL_2"},
            # Empty bundle: identification is checked before the
            # action refs, so this names UNIDENTIFIED, not the
            # action-binding error.
            {},
        ]
        for bundle in bad_bundles:
            with self.subTest(bundle=bundle):
                with self.assertRaises(InstallPlanError) as cm:
                    build_install_plan(_valid_request(),
                                       _valid_binding(), bundle)
                self.assertEqual(cm.exception.code,
                                 "D1-INSTALL-BUNDLE-UNIDENTIFIED")

    def test_bundle_identified_by_content_hash_alone_builds(self):
        # Contrast (mutation check): a content_hash identifies the
        # bundle exactly as a bundle_ref does; identification is the
        # specific gate the pin above guards.
        bundle = _valid_bundle()
        bundle["content_hash"] = bundle.pop("bundle_ref")
        plan = build_install_plan(_valid_request(), _valid_binding(),
                                  bundle)
        self.assertEqual(plan["steps"][0]["bundle_ref"],
                         "TEST-D1-BUNDLE")


if __name__ == "__main__":
    unittest.main()
