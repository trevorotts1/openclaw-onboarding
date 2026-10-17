"""TEST ONLY - unittest suite for the S80-06 extra-offer binding core.

Run from this directory:  python3 -m unittest test_binding -v
(or: python3 test_binding.py)

Proves the L1 interface behaviors of extra_offer_binding.py against the
TEST-ONLY fixture driver. Proves nothing about a real native location.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "adapters"))

from adapter_common import ADAPTER_VERIFICATION_SOURCES  # noqa: E402

import extra_offer_binding as b  # noqa: E402
from fixture_driver import FixtureDriver  # noqa: E402


def make_context(**overrides):
    fields = dict(
        tenant_ref="tenant:TEST-TENANT",
        location_ref="location:TEST-LOC",
        launch_ref="launch:TEST-LAUNCH/r1",
        launch_revision="rev:TEST-LAUNCH-R1",
        parent_order_ref="native:TEST-PARENT-ORDER",
        parent_verification_source="native_purchase_ledger",
        offer_id="TEST-OFFER-U1",
        native_product_ref="native:TEST-PRODUCT",
        native_price_ref="native:TEST-PRICE",
        capability_evidence_ref="native:TEST-CAPABILITY-EVIDENCE",
        amount_minor=6700,
        currency="USD",
        success_route_ref="route:TEST-SUCCESS",
        decline_route_ref="route:TEST-DECLINE",
        error_route_ref="route:TEST-ERROR",
        disclosure_terms_ref="catalog:TEST-OFFER-U1-DISCLOSURE",
        copy_refs=("request:TEST-REQ-U1/copy",),
    )
    fields.update(overrides)
    return b.BindingContext(**fields)


def make_parent():
    return {
        "order_ref": "native:TEST-PARENT-ORDER",
        "status": "paid",
        "entitlements": ["main_offer"],
        "amount_minor": 4900,
        "currency": "USD",
    }


def parent_bytes(parent) -> bytes:
    return json.dumps(parent, sort_keys=True).encode("utf-8")


class TestVocabularyAndTransitions(unittest.TestCase):
    def test_state_vocabulary_exact(self):
        self.assertEqual(
            b.PURCHASE_STATES,
            ("ready", "validating", "submitting", "pending_confirmation",
             "paid", "failed", "requires_customer_action", "cancelled"),
        )

    def test_transition_legality(self):
        self.assertTrue(b.can_transition("ready", "validating"))
        self.assertTrue(b.can_transition("submitting", "paid"))
        self.assertTrue(b.can_transition("pending_confirmation", "paid"))
        self.assertTrue(b.can_transition("failed", "validating"))
        self.assertFalse(b.can_transition("ready", "paid"))
        self.assertFalse(b.can_transition("paid", "failed"))
        self.assertFalse(b.can_transition("cancelled", "validating"))
        self.assertFalse(b.can_transition("pending_confirmation", "validating"))

    def test_illegal_transition_raises_on_binding(self):
        binding = b.ExtraOfferBinding(make_context())
        with self.assertRaises(b.BindingError):
            binding._transition("paid")
        self.assertEqual(binding.state, "ready")


class TestContextValidation(unittest.TestCase):
    def test_unverified_parent_source_rejected(self):
        for bad in ("client_side_claim", "acceptedU1_param", "", None):
            with self.assertRaises(b.BindingError):
                make_context(parent_verification_source=bad)

    def test_verified_sources_match_adapters_exactly(self):
        self.assertEqual(b.VERIFIED_SOURCES, ADAPTER_VERIFICATION_SOURCES)
        for source in ("native_purchase_ledger", "provider_event_readback",
                       "s44_event_adapter"):
            make_context(parent_verification_source=source)  # constructs

    def test_missing_or_unstructured_capability_evidence_rejected(self):
        for bad in (None, "", "   ", "yes", "verified"):
            with self.assertRaises(b.BindingError):
                make_context(capability_evidence_ref=bad)

    def test_recurring_requires_terms(self):
        with self.assertRaises(b.BindingError):
            make_context(billing_type="recurring")
        ctx = make_context(
            billing_type="recurring",
            recurring_terms={"interval": "month", "interval_count": 1, "cycles": 3},
        )
        self.assertEqual(ctx.billing_type, "recurring")

    def test_one_time_must_not_carry_recurring_terms(self):
        with self.assertRaises(b.BindingError):
            make_context(recurring_terms={"interval": "month"})

    def test_amount_and_currency_validated(self):
        with self.assertRaises(b.BindingError):
            make_context(amount_minor=True)
        with self.assertRaises(b.BindingError):
            make_context(amount_minor=-1)
        with self.assertRaises(b.BindingError):
            make_context(currency="usd")

    def test_u2_contexts_from_both_entry_paths_construct(self):
        for entry in ("from_upsell_1", "from_downsell_1"):
            ctx = make_context(entry_context=entry, offer_id="TEST-OFFER-U2")
            binding = b.ExtraOfferBinding(ctx)
            self.assertEqual(binding.context.entry_context, entry)
        with self.assertRaises(b.BindingError):
            make_context(entry_context="acceptedU1=true")


class TestPresentationDecision(unittest.TestCase):
    def test_capability_true_offers_one_click(self):
        decision = b.ExtraOfferBinding(make_context()).presentation_decision(True)
        self.assertTrue(decision.one_click_offered)
        self.assertFalse(decision.fallback_required)
        self.assertIsNone(decision.fallback)

    def test_capability_false_disables_with_fallback_recorded(self):
        decision = b.ExtraOfferBinding(make_context()).presentation_decision(False)
        self.assertFalse(decision.one_click_offered)
        self.assertEqual(decision.route, "one_click_disabled")
        self.assertTrue(decision.fallback_required)
        self.assertEqual(decision.fallback, b.FALLBACK_STANDARD_CHECKOUT)
        self.assertEqual(decision.open_question_ref, "S06-Q5")

    def test_capability_unknown_disables_with_fallback_recorded(self):
        decision = b.ExtraOfferBinding(make_context()).presentation_decision(None)
        self.assertFalse(decision.one_click_offered)
        self.assertTrue(decision.fallback_required)
        self.assertEqual(decision.fallback, b.FALLBACK_STANDARD_CHECKOUT)

    def test_accept_refused_after_disabled_presentation(self):
        binding = b.ExtraOfferBinding(make_context())
        binding.presentation_decision(None)
        with self.assertRaises(b.BindingError):
            binding.accept(FixtureDriver("paid_with_readback"))


class TestAcceptPaths(unittest.TestCase):
    def test_paid_requires_readback_confirmation(self):
        binding = b.ExtraOfferBinding(make_context())
        binding.presentation_decision(True)
        driver = FixtureDriver("paid_without_readback")
        outcome = binding.accept(driver)
        self.assertEqual(outcome.state, "pending_confirmation")
        self.assertNotEqual(binding.state, "paid")
        self.assertTrue(binding.unresolved)
        self.assertFalse(outcome.read_back_confirmed)
        self.assertEqual(len(driver.read_back_calls), 1)

    def test_paid_with_readback_settles_paid_on_success_route(self):
        binding = b.ExtraOfferBinding(make_context())
        binding.presentation_decision(True)
        outcome = binding.accept(FixtureDriver("paid_with_readback"))
        self.assertEqual(outcome.state, "paid")
        self.assertEqual(binding.state, "paid")
        self.assertTrue(outcome.read_back_confirmed)
        self.assertEqual(outcome.route_ref, "route:TEST-SUCCESS")
        self.assertEqual(outcome.native_txn_ref, "TEST-TXN-paid_with_readback")

    def test_double_accept_single_flight(self):
        binding = b.ExtraOfferBinding(make_context())
        binding.presentation_decision(True)
        inner_errors = []

        def reenter():
            try:
                binding.accept(FixtureDriver("paid_with_readback"))
            except b.BindingError as exc:  # expected: already submitting
                inner_errors.append(str(exc))

        outcome = binding.accept(FixtureDriver("paid_with_readback", on_invoke=reenter))
        self.assertEqual(outcome.state, "paid")
        self.assertEqual(len(inner_errors), 1)
        # And once paid, a further accept is refused (no duplicate charge).
        with self.assertRaises(b.BindingError):
            binding.accept(FixtureDriver("paid_with_readback"))

    def test_failed_outcome_is_known_and_retryable(self):
        binding = b.ExtraOfferBinding(make_context())
        binding.presentation_decision(True)
        first = binding.accept(FixtureDriver("failed"))
        self.assertEqual(first.state, "failed")
        self.assertEqual(first.failure_kind, "card_declined")
        self.assertEqual(first.route_ref, "route:TEST-ERROR")
        self.assertFalse(binding.unresolved)
        second = binding.accept(FixtureDriver("failed"))
        self.assertEqual(second.attempt_number, 2)
        self.assertEqual(second.state, "failed")

    def test_requires_customer_action_outcome(self):
        binding = b.ExtraOfferBinding(make_context())
        binding.presentation_decision(True)
        outcome = binding.accept(FixtureDriver("requires_customer_action"))
        self.assertEqual(outcome.state, "requires_customer_action")
        self.assertEqual(outcome.failure_kind, "authentication_required")
        self.assertFalse(binding.unresolved)

    def test_expired_cancelled_outcome(self):
        binding = b.ExtraOfferBinding(make_context())
        binding.presentation_decision(True)
        outcome = binding.accept(FixtureDriver("expired_cancelled"))
        self.assertEqual(outcome.state, "cancelled")
        self.assertEqual(outcome.failure_kind, "session_expired")

    def test_idempotency_key_deterministic(self):
        keys = []
        for _ in range(2):
            binding = b.ExtraOfferBinding(make_context())
            binding.presentation_decision(True)
            outcome = binding.accept(FixtureDriver("failed"))
            keys.append(outcome.idempotency_key)
        self.assertEqual(keys[0], keys[1])


class TestUnknownOutcomeDiscipline(unittest.TestCase):
    def test_unknown_outcome_blocks_retry_until_reconcile(self):
        binding = b.ExtraOfferBinding(make_context())
        binding.presentation_decision(True)
        outcome = binding.accept(FixtureDriver("invoke_raises_unknown"))
        self.assertEqual(outcome.state, "pending_confirmation")
        self.assertEqual(outcome.failure_kind, "unknown_outcome")
        self.assertTrue(binding.unresolved)
        with self.assertRaises(b.BindingError):
            binding.accept(FixtureDriver("paid_with_readback"))
        resolved = binding.reconcile(FixtureDriver("invoke_raises_unknown"))
        self.assertEqual(resolved.state, "paid")
        self.assertTrue(resolved.read_back_confirmed)
        self.assertEqual(binding.state, "paid")
        self.assertFalse(binding.unresolved)

    def test_reconcile_then_paid_path(self):
        binding = b.ExtraOfferBinding(make_context())
        binding.presentation_decision(True)
        driver = FixtureDriver("pending_then_paid")
        pending = binding.accept(driver)
        self.assertEqual(pending.state, "pending_confirmation")
        with self.assertRaises(b.BindingError):
            binding.accept(driver)
        resolved = binding.reconcile(driver)
        self.assertEqual(resolved.state, "paid")
        self.assertEqual(resolved.action, "reconcile")
        self.assertEqual(resolved.route_ref, "route:TEST-SUCCESS")
        self.assertEqual(binding.state, "paid")
        # Reconcile read back FIRST: read-back happened during reconcile.
        self.assertGreaterEqual(len(driver.read_back_calls), 1)

    def test_decline_refused_while_unresolved(self):
        binding = b.ExtraOfferBinding(make_context())
        binding.presentation_decision(True)
        binding.accept(FixtureDriver("pending_then_paid"))
        with self.assertRaises(b.BindingError):
            binding.decline()


class TestDecline(unittest.TestCase):
    def test_decline_is_routed_with_zero_driver_calls(self):
        driver = FixtureDriver("paid_with_readback")
        binding = b.ExtraOfferBinding(make_context())
        outcome = binding.decline()
        self.assertEqual(outcome.action, "decline")
        self.assertEqual(outcome.route_ref, "route:TEST-DECLINE")
        self.assertEqual(driver.total_calls, 0)
        self.assertEqual(binding.state, "ready")

    def test_accept_after_decline_raises(self):
        # F7 repair: decline is terminal for the binding instance, even
        # when one-click was offered for the presentation.
        driver = FixtureDriver("paid_with_readback")
        binding = b.ExtraOfferBinding(make_context())
        binding.presentation_decision(True)
        binding.decline()
        with self.assertRaises(b.BindingError):
            binding.accept(driver)
        self.assertEqual(driver.total_calls, 0)
        self.assertEqual(binding.state, "ready")

    def test_second_decline_raises(self):
        # F7 repair: a declined instance cannot be declined twice.
        binding = b.ExtraOfferBinding(make_context())
        binding.decline()
        with self.assertRaises(b.BindingError):
            binding.decline()
        self.assertEqual(len(binding.attempts), 1)


class TestNoRollback(unittest.TestCase):
    def _run_and_check(self, scenario, use_decline=False):
        parent = make_parent()
        before = parent_bytes(parent)
        binding = b.ExtraOfferBinding(make_context(), parent_purchase=parent)
        if use_decline:
            outcome = binding.decline()
        else:
            binding.presentation_decision(True)
            outcome = binding.accept(FixtureDriver(scenario))
        self.assertEqual(parent_bytes(parent), before)  # byte-identical
        self.assertTrue(outcome.parent_purchase_unaffected)
        self.assertEqual(outcome.parent_state_observed, make_parent())
        return outcome

    def test_parent_unaffected_after_accept_success(self):
        self._run_and_check("paid_with_readback")

    def test_parent_unaffected_after_accept_failure(self):
        self._run_and_check("failed")

    def test_parent_unaffected_after_decline(self):
        self._run_and_check(None, use_decline=True)

    def test_parent_unaffected_after_pending(self):
        self._run_and_check("pending_then_paid")

    def test_parent_unaffected_after_requires_action(self):
        self._run_and_check("requires_customer_action")

    def test_binding_exposes_no_parent_mutator(self):
        binding = b.ExtraOfferBinding(make_context(), parent_purchase=make_parent())
        public = [name for name in dir(binding) if not name.startswith("_")]
        self.assertEqual(
            sorted(public),
            ["accept", "attempts", "binding_record", "context", "decline",
             "presentation_decision", "reconcile", "state", "unresolved"],
        )


class TestOpenQuestionsAndRecord(unittest.TestCase):
    def test_open_questions_exact(self):
        self.assertEqual(
            b.OPEN_QUESTION_IDS,
            ["S06-Q1", "S06-Q2", "S06-Q3", "S06-Q4", "S06-Q5", "S06-Q6",
             "S44-Q7", "S44-Q8", "S49-Q9"],
        )
        owners = {q["id"]: q["owner"] for q in b.OPEN_QUESTIONS}
        self.assertEqual(owners["S44-Q7"], "S44")
        self.assertEqual(owners["S49-Q9"], "S49")
        self.assertTrue(all(q["status"] == "unresolved" for q in b.OPEN_QUESTIONS))
        self.assertTrue(all(q["text"] for q in b.OPEN_QUESTIONS))

    def test_binding_record_shape_exact(self):
        binding = b.ExtraOfferBinding(make_context())
        self.assertEqual(
            binding.binding_record(),
            {
                "kind": "extra_offer_binding",
                "interface_ref": "S79 extra_offer_interface.md DRAFT (fixture level)",
                "binding_status": "interface_conformant_pending_s06",
                "native_action_id": None,
                "capability_evidence_ref": "native:TEST-CAPABILITY-EVIDENCE",
                "open_questions": ["S06-Q1", "S06-Q2", "S06-Q3", "S06-Q4",
                                   "S06-Q5", "S06-Q6", "S44-Q7", "S44-Q8",
                                   "S49-Q9"],
            },
        )


class TestCapabilityGateEnforcement(unittest.TestCase):
    """F1 repair: the capability gate is binding-enforced, not
    caller-discipline. accept() must refuse when no presentation
    decision has been recorded at all."""

    def test_accept_without_presentation_decision_raises(self):
        driver = FixtureDriver("paid_with_readback")
        binding = b.ExtraOfferBinding(make_context())
        with self.assertRaises(b.BindingError):
            binding.accept(driver)
        self.assertEqual(driver.total_calls, 0)
        self.assertEqual(binding.state, "ready")
        self.assertEqual(binding.attempts, ())

    def test_accept_after_offered_decision_proceeds(self):
        binding = b.ExtraOfferBinding(make_context())
        binding.presentation_decision(True)
        outcome = binding.accept(FixtureDriver("paid_with_readback"))
        self.assertEqual(outcome.state, "paid")
        self.assertEqual(binding.state, "paid")


class TestSection3Fields(unittest.TestCase):
    """F2 repair: launch_revision, copy_refs, disclosure_terms_ref are
    carried and validated on BindingContext."""

    def test_launch_revision_distinct_and_required(self):
        ctx = make_context()
        self.assertEqual(ctx.launch_revision, "rev:TEST-LAUNCH-R1")
        self.assertNotEqual(ctx.launch_revision, ctx.launch_ref)
        with self.assertRaises(b.BindingError):
            make_context(launch_revision="")
        with self.assertRaises(b.BindingError):
            make_context(launch_revision="launch:TEST-LAUNCH/r1")

    def test_copy_refs_must_be_stated(self):
        fields = dict(
            tenant_ref="tenant:TEST-TENANT",
            location_ref="location:TEST-LOC",
            launch_ref="launch:TEST-LAUNCH/r1",
            launch_revision="rev:TEST-LAUNCH-R1",
            parent_order_ref="native:TEST-PARENT-ORDER",
            parent_verification_source="native_purchase_ledger",
            offer_id="TEST-OFFER-U1",
            native_product_ref="native:TEST-PRODUCT",
            native_price_ref="native:TEST-PRICE",
            capability_evidence_ref="native:TEST-CAPABILITY-EVIDENCE",
            amount_minor=6700,
            currency="USD",
            success_route_ref="route:TEST-SUCCESS",
            decline_route_ref="route:TEST-DECLINE",
            error_route_ref="route:TEST-ERROR",
            disclosure_terms_ref="catalog:TEST-OFFER-U1-DISCLOSURE",
        )
        with self.assertRaises(TypeError):
            b.BindingContext(**fields)  # copy_refs not stated at all
        ctx = b.BindingContext(copy_refs=(), **fields)
        self.assertEqual(ctx.copy_refs, ())
        ctx = b.BindingContext(copy_refs=("request:TEST/copy",), **fields)
        self.assertEqual(ctx.copy_refs, ("request:TEST/copy",))

    def test_copy_refs_entries_validated(self):
        with self.assertRaises(b.BindingError):
            make_context(copy_refs=("bareword",))
        with self.assertRaises(b.BindingError):
            make_context(copy_refs="request:TEST/copy")  # not a tuple
        ctx = make_context(copy_refs=())
        self.assertEqual(ctx.copy_refs, ())

    def test_disclosure_terms_ref_required_and_structured(self):
        ctx = make_context()
        self.assertEqual(ctx.disclosure_terms_ref,
                         "catalog:TEST-OFFER-U1-DISCLOSURE")
        for bad in (None, "", "yes"):
            with self.assertRaises(b.BindingError):
                make_context(disclosure_terms_ref=bad)


class TestCapabilityEvidenceScheme(unittest.TestCase):
    """F6 repair: capability_evidence_ref must carry a recognized
    scheme prefix; merely dashed/path-like strings are rejected."""

    def test_bare_dashed_or_path_strings_rejected(self):
        for bad in ("a-b", "TEST-CAPABILITY-EVIDENCE", "some/path"):
            with self.assertRaises(b.BindingError):
                make_context(capability_evidence_ref=bad)

    def test_recognized_scheme_prefixes_accepted(self):
        for good in ("native:TEST-EV", "ledger:TEST-EV",
                     "provider-event:TEST-EV", "s44:TEST-EV",
                     "catalog:TEST-EV", "request:TEST-EV", "graph:TEST-EV",
                     "https://example.test/evidence"):
            make_context(capability_evidence_ref=good)  # constructs


class TestGuardIsolation(unittest.TestCase):
    """F4 repair: the single-flight guard is isolated in test by
    injection; its refusal surfaces as routing_state.RouteError."""

    def test_injected_held_guard_surfaces_route_error(self):
        from routing_state import PaymentAttemptGuard, RouteError

        guard = PaymentAttemptGuard()
        guard.begin_attempt()  # an attempt is already in flight elsewhere
        binding = b.ExtraOfferBinding(make_context(), guard=guard)
        binding.presentation_decision(True)
        with self.assertRaises(RouteError):
            binding.accept(FixtureDriver("paid_with_readback"))
        self.assertEqual(binding.state, "ready")
        self.assertEqual(binding.attempts, ())
        guard.release_attempt()

    def test_default_construction_composes_own_guard(self):
        from routing_state import PaymentAttemptGuard

        binding = b.ExtraOfferBinding(make_context())
        self.assertIsInstance(binding._guard, PaymentAttemptGuard)
        self.assertEqual(binding._guard.state, PaymentAttemptGuard.IDLE)


class TestU2Flows(unittest.TestCase):
    """F5 repair: full U2 flows for EACH entry path (accept-through-
    read-back paid, and decline), offer TEST-OFFER-U2."""

    def _u2_binding(self, entry):
        ctx = make_context(
            offer_id="TEST-OFFER-U2",
            entry_context=entry,
            disclosure_terms_ref="catalog:TEST-OFFER-U2-DISCLOSURE",
        )
        return b.ExtraOfferBinding(ctx)

    def test_u2_accept_paid_from_upsell_1(self):
        binding = self._u2_binding("from_upsell_1")
        binding.presentation_decision(True)
        outcome = binding.accept(FixtureDriver("paid_with_readback"))
        self.assertEqual(outcome.state, "paid")
        self.assertTrue(outcome.read_back_confirmed)
        self.assertEqual(outcome.route_ref, "route:TEST-SUCCESS")
        self.assertEqual(outcome.native_txn_ref, "TEST-TXN-paid_with_readback")
        self.assertEqual(binding.state, "paid")
        self.assertEqual(binding.context.entry_context, "from_upsell_1")

    def test_u2_accept_paid_from_downsell_1(self):
        binding = self._u2_binding("from_downsell_1")
        binding.presentation_decision(True)
        outcome = binding.accept(FixtureDriver("paid_with_readback"))
        self.assertEqual(outcome.state, "paid")
        self.assertTrue(outcome.read_back_confirmed)
        self.assertEqual(outcome.route_ref, "route:TEST-SUCCESS")
        self.assertEqual(outcome.native_txn_ref, "TEST-TXN-paid_with_readback")
        self.assertEqual(binding.state, "paid")
        self.assertEqual(binding.context.entry_context, "from_downsell_1")

    def test_u2_decline_from_upsell_1(self):
        driver = FixtureDriver("paid_with_readback")
        binding = self._u2_binding("from_upsell_1")
        binding.presentation_decision(True)
        outcome = binding.decline()
        self.assertEqual(outcome.action, "decline")
        self.assertEqual(outcome.route_ref, "route:TEST-DECLINE")
        self.assertEqual(driver.total_calls, 0)
        self.assertEqual(binding.context.entry_context, "from_upsell_1")

    def test_u2_decline_from_downsell_1(self):
        driver = FixtureDriver("paid_with_readback")
        binding = self._u2_binding("from_downsell_1")
        binding.presentation_decision(True)
        outcome = binding.decline()
        self.assertEqual(outcome.action, "decline")
        self.assertEqual(outcome.route_ref, "route:TEST-DECLINE")
        self.assertEqual(driver.total_calls, 0)
        self.assertEqual(binding.context.entry_context, "from_downsell_1")


class TestReconcileSingleReadBack(unittest.TestCase):
    """F8 repair: a paid reconcile performs exactly ONE read-back - the
    read-back reconcile itself performed is the confirmation."""

    def test_paid_reconcile_performs_exactly_one_readback(self):
        binding = b.ExtraOfferBinding(make_context())
        binding.presentation_decision(True)
        driver = FixtureDriver("pending_then_paid")
        pending = binding.accept(driver)
        self.assertEqual(pending.state, "pending_confirmation")
        self.assertEqual(len(driver.read_back_calls), 0)
        resolved = binding.reconcile(driver)
        self.assertEqual(resolved.state, "paid")
        self.assertTrue(resolved.read_back_confirmed)
        self.assertEqual(len(driver.read_back_calls), 1)
        self.assertEqual(binding.state, "paid")


if __name__ == "__main__":
    unittest.main(verbosity=2)
