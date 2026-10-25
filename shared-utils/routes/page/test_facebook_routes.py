#!/usr/bin/env python3
"""Acceptance proofs for the Page comment and Messenger route adapter (T-20).

Each test names the acceptance clause it pins:
  * separate public/opener/inbound eligibility (including refusal cases);
  * author exclusion by verified direction/actor;
  * keyword fallback with honest attribution;
  * comment-opener minimal customer interaction (F-08 / OPENER_ONLY_NO_DRIP);
  * ordinary-reader proof deferred (the adapter must not claim it).

Run: python3 shared-utils/routes/page/test_facebook_routes.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PAGE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PAGE_DIR))

import facebook_routes as routes  # noqa: E402

TOOLS_DIR = Path(__file__).resolve().parents[3] / "38-conversational-ai-system" / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from durable_store import DurableStore  # noqa: E402
from outbound_gate import ST_BLOCKED, ST_SENT, dispatch  # noqa: E402


def public_facts(**overrides):
    facts = {
        "channel": "FB_PUBLIC",
        "action_purpose": "PUBLIC_REPLY",
        "public_reply_permission": True,
        "account_binding_revision": "binding-7",
        "current_binding_revision": "binding-7",
    }
    facts.update(overrides)
    return facts


def opener_facts(**overrides):
    facts = {
        "channel": "FB_DM",
        "action_purpose": "COMMENT_PRIVATE_OPENER",
        "comment_event_id": "ev-comment-1",
        "comment_private_opener_permission": True,
        "inbound_dm_window": False,  # a comment is not an inbound DM window
        "account_binding_revision": "binding-7",
        "current_binding_revision": "binding-7",
    }
    facts.update(overrides)
    return facts


def inbound_facts(**overrides):
    facts = {
        "channel": "FB_DM",
        "action_purpose": "AI_REPLY",
        "inbound_message_id": "ev-msg-1",
        "inbound_dm_window": True,
        "eligibility_refreshed_by": "INBOUND_MESSAGE",
        "account_binding_revision": "binding-7",
        "current_binding_revision": "binding-7",
    }
    facts.update(overrides)
    return facts


class EligibilitySeparationTests(unittest.TestCase):
    """C-20 clause 1: public/opener/inbound eligibility are separate."""

    def verdict(self, route, facts):
        return routes.evaluate_eligibility(route, facts, now=1000.0)

    def test_public_reply_allows_without_any_dm_window(self):
        # No inbound_dm_window key at all: public transport needs none.
        out = self.verdict(routes.ROUTE_PUBLIC_REPLY, public_facts())
        self.assertEqual(out.verdict, "ALLOW")
        self.assertEqual(out.evidence["route"], routes.ROUTE_PUBLIC_REPLY)
        self.assertEqual(out.evidence["basis"], "PLATFORM_ELIGIBILITY")

    def test_public_reply_refuses_inbound_evidence_as_permission(self):
        # An inbound message + window is not a public-reply permission.
        out = self.verdict(routes.ROUTE_PUBLIC_REPLY,
                           public_facts(public_reply_permission=None,
                                        inbound_message_id="ev-msg-1",
                                        inbound_dm_window=True))
        self.assertEqual(out.verdict, "SUPPRESSED")
        self.assertEqual(out.evidence["reason"], "NO_PUBLIC_REPLY_PERMISSION")

    def test_opener_allows_from_comment_with_no_inbound_window(self):
        out = self.verdict(routes.ROUTE_COMMENT_PRIVATE_OPENER, opener_facts())
        self.assertEqual(out.verdict, "ALLOW")

    def test_opener_refuses_a_dm_window_without_the_comment(self):
        # A win-down alone never opens a private opener.
        out = self.verdict(routes.ROUTE_COMMENT_PRIVATE_OPENER,
                           opener_facts(comment_event_id=None,
                                        inbound_dm_window=True))
        self.assertEqual(out.verdict, "SUPPRESSED")
        self.assertEqual(out.evidence["reason"], "NO_COMMENT_EVENT")

    def test_opener_refuses_without_its_own_permission(self):
        out = self.verdict(routes.ROUTE_COMMENT_PRIVATE_OPENER,
                           opener_facts(comment_private_opener_permission=False))
        self.assertEqual(out.verdict, "SUPPRESSED")
        self.assertEqual(out.evidence["reason"],
                         "NO_COMMENT_OPENER_PERMISSION")

    def test_inbound_allows_inside_the_customer_window(self):
        out = self.verdict(routes.ROUTE_INBOUND_DM, inbound_facts())
        self.assertEqual(out.verdict, "ALLOW")
        self.assertEqual(out.evidence["basis"], "INBOUND_MESSAGE")

    def test_inbound_refuses_a_comment_alone(self):
        out = self.verdict(routes.ROUTE_INBOUND_DM,
                           inbound_facts(inbound_message_id=None,
                                         comment_event_id="ev-comment-1"))
        self.assertEqual(out.verdict, "SUPPRESSED")
        self.assertEqual(out.evidence["reason"], "NO_INBOUND_MESSAGE")

    def test_inbound_refuses_outbound_and_cross_channel_refresh(self):
        for basis in ("OUTBOUND_MESSAGE", "CROSS_CHANNEL_MESSAGE",
                      "CONSENT_RECORD", None):
            with self.subTest(basis=basis):
                out = self.verdict(routes.ROUTE_INBOUND_DM,
                                   inbound_facts(eligibility_refreshed_by=basis))
                self.assertEqual(out.verdict, "SUPPRESSED")
                self.assertEqual(out.evidence["reason"],
                                 "ELIGIBILITY_NOT_REFRESHED")

    def test_inbound_refuses_without_an_open_window(self):
        out = self.verdict(routes.ROUTE_INBOUND_DM,
                           inbound_facts(inbound_dm_window=False))
        self.assertEqual(out.verdict, "SUPPRESSED")
        self.assertEqual(out.evidence["reason"], "NO_INBOUND_DM_WINDOW")

    def test_each_route_refuses_another_routes_purpose(self):
        pairs = (
            (routes.ROUTE_PUBLIC_REPLY, "AI_REPLY"),
            (routes.ROUTE_COMMENT_PRIVATE_OPENER, "PUBLIC_REPLY"),
            (routes.ROUTE_INBOUND_DM, "COMMENT_PRIVATE_OPENER"),
        )
        for route, purpose in pairs:
            with self.subTest(route=route, purpose=purpose):
                facts = {"channel": routes.ROUTE_CHANNEL[route],
                         "action_purpose": purpose,
                         "public_reply_permission": True,
                         "comment_private_opener_permission": True,
                         "comment_event_id": "ev-c",
                         "inbound_message_id": "ev-m",
                         "inbound_dm_window": True,
                         "eligibility_refreshed_by": "INBOUND_MESSAGE"}
                out = self.verdict(route, facts)
                self.assertEqual(out.verdict, "SUPPRESSED")
                self.assertEqual(out.evidence["reason"],
                                 "PURPOSE_NOT_PERMITTED")

    def test_each_route_refuses_a_foreign_channel(self):
        cases = (
            (routes.ROUTE_PUBLIC_REPLY, public_facts(channel="FB_DM")),
            (routes.ROUTE_COMMENT_PRIVATE_OPENER, opener_facts(channel="FB_PUBLIC")),
            (routes.ROUTE_INBOUND_DM, inbound_facts(channel="IG_DM")),
        )
        for route, facts in cases:
            with self.subTest(route=route):
                out = self.verdict(route, facts)
                self.assertEqual(out.verdict, "SUPPRESSED")
                self.assertEqual(out.evidence["reason"], "UNSUPPORTED_CHANNEL")

    def test_changed_binding_quarantines_every_route(self):
        for route, facts in (
                (routes.ROUTE_PUBLIC_REPLY, public_facts()),
                (routes.ROUTE_COMMENT_PRIVATE_OPENER, opener_facts()),
                (routes.ROUTE_INBOUND_DM, inbound_facts())):
            with self.subTest(route=route):
                stale = dict(facts, current_binding_revision="binding-8")
                out = self.verdict(route, stale)
                self.assertEqual(out.verdict, "QUARANTINED")
                self.assertEqual(out.evidence["reason"], "BINDING_CHANGED")

    def test_unknown_route_is_a_programming_error_not_a_verdict(self):
        with self.assertRaises(routes.RouteError):
            self.verdict("PERSONAL_PROFILE", public_facts())


class AuthorExclusionTests(unittest.TestCase):
    """C-20 clause 2: exclude own events by verified identity."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fb-route-test-")
        self.store = DurableStore(str(Path(self.tmp.name) / "s.sqlite"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_own_outgoing_is_excluded(self):
        out = routes.admit_inbound(self.store, tenant_id="t1",
                                   provider_event_id="e1",
                                   actor_id="page-1",
                                   own_actor_ids=("page-1",),
                                   direction="outbound")
        self.assertFalse(out.admitted)
        self.assertEqual(out.reason, "excluded:direction=outbound")

    def test_own_actor_is_excluded_even_when_direction_says_inbound(self):
        out = routes.admit_inbound(self.store, tenant_id="t1",
                                   provider_event_id="e2", actor_id="page-1",
                                   own_actor_ids=("page-1",))
        self.assertFalse(out.admitted)
        self.assertEqual(out.reason, "excluded:own_actor")

    def test_a_real_reader_event_is_admitted_once(self):
        first = routes.admit_inbound(self.store, tenant_id="t1",
                                     provider_event_id="e3", actor_id="reader-9",
                                     own_actor_ids=("page-1",))
        self.assertTrue(first.admitted)
        again = routes.admit_inbound(self.store, tenant_id="t1",
                                     provider_event_id="e3", actor_id="reader-9",
                                     own_actor_ids=("page-1",))
        self.assertFalse(again.admitted)
        self.assertEqual(again.reason, "duplicate")

    def test_processed_event_can_then_be_decided(self):
        self.assertTrue(routes.admit_inbound(
            self.store, tenant_id="t1", provider_event_id="e4",
            actor_id="reader-9").admitted)
        self.assertTrue(self.store.claim_decision(
            provider="facebook", tenant_id="t1", provider_event_id="e4"))
        self.assertEqual(self.store.inbox_row(
            provider="facebook", tenant_id="t1",
            provider_event_id="e4")["state"], "deciding")


class KeywordFallbackTests(unittest.TestCase):
    """C-20 clause 3: keyword fallback; no invented attribution."""

    KEYWORDS = {"guide": "item-guide", "vault": "item-vault"}
    REFS = {"mme-ref-1": "item-guide"}

    def test_known_ref_routes_with_present_attribution(self):
        out = routes.resolve_entry(channel="FB_DM", ref="mme-ref-1",
                                   text="hello", ref_routes=self.REFS,
                                   keyword_routes=self.KEYWORDS)
        self.assertEqual(out.route, "item-guide")
        self.assertEqual(out.basis, routes.BASIS_REF)
        self.assertEqual(out.attribution, routes.ATTRIBUTION_PRESENT)

    def test_absent_ref_falls_back_to_the_typed_keyword(self):
        out = routes.resolve_entry(channel="FB_DM", ref=None, text="GUIDE",
                                   ref_routes=self.REFS,
                                   keyword_routes=self.KEYWORDS)
        self.assertEqual(out.route, "item-guide")
        self.assertEqual(out.basis, routes.BASIS_KEYWORD_FALLBACK)
        self.assertEqual(out.attribution, routes.ATTRIBUTION_ABSENT)

    def test_unknown_ref_is_honest_and_still_falls_back(self):
        out = routes.resolve_entry(channel="FB_DM", ref="mme-unknown",
                                   text="vault", ref_routes=self.REFS,
                                   keyword_routes=self.KEYWORDS)
        self.assertEqual(out.route, "item-vault")
        self.assertEqual(out.attribution, routes.ATTRIBUTION_UNRECOGNIZED)

    def test_no_ref_and_no_keyword_prompts_once_and_never_drips(self):
        out = routes.resolve_entry(channel="FB_DM", ref=None, text="hi there",
                                   ref_routes=self.REFS,
                                   keyword_routes=self.KEYWORDS)
        self.assertIsNone(out.route)
        self.assertEqual(out.basis, routes.BASIS_NONE)
        self.assertTrue(out.prompt_keyword)
        self.assertTrue(out.may_send)  # the keyword prompt is the only effect
        self.assertEqual(out.reason, "NO_ROUTE_EVIDENCE")

    def test_keyword_matching_normalises_case_space_and_punctuation(self):
        for text in ("  guide! ", "GUIDE.", "\tGuide\n", "G u i d e".replace(" ", "")):
            with self.subTest(text=text):
                out = routes.resolve_entry(channel="FB_DM", text=text,
                                           keyword_routes=self.KEYWORDS)
                self.assertEqual(out.route, "item-guide")

    def test_keyword_matching_is_not_a_substring_match(self):
        out = routes.resolve_entry(channel="FB_DM", text="GUIDED",
                                   keyword_routes=self.KEYWORDS)
        self.assertIsNone(out.route)
        self.assertTrue(out.prompt_keyword)

    def test_a_known_ref_beats_a_contradictory_keyword(self):
        # Handoff mistake: link attribution is not assumed from text.
        out = routes.resolve_entry(channel="FB_DM", ref="mme-ref-1",
                                   text="vault", ref_routes=self.REFS,
                                   keyword_routes=self.KEYWORDS)
        self.assertEqual(out.route, "item-guide")
        self.assertEqual(out.basis, routes.BASIS_REF)

    def test_empty_text_is_not_a_keyword_match(self):
        out = routes.resolve_entry(channel="FB_DM", text="!!!",
                                   keyword_routes=self.KEYWORDS)
        self.assertIsNone(out.route)
        self.assertTrue(out.prompt_keyword)


class CommentOpenerInteractionTests(unittest.TestCase):
    """C-F08 / F-08: comment-opener minimal customer interaction."""

    def test_comment_only_permits_one_opener_and_no_drip(self):
        out = routes.opener_decision(channel="FB_DM", comment_only=True,
                                     customer_reply=False)
        self.assertEqual(out.action, "OPENER_ONLY_NO_DRIP")
        self.assertTrue(out.allowed)

    def test_ig_dm_fixture_shape_is_the_same_rule(self):
        # fixtures/contract-traces.json F-08A: channel IG_DM, comment_only, no reply.
        out = routes.opener_decision(channel="IG_DM", comment_only=True,
                                     customer_reply=False)
        self.assertEqual(out.action, "OPENER_ONLY_NO_DRIP")

    def test_an_already_sent_opener_never_drips(self):
        out = routes.opener_decision(channel="FB_DM", comment_only=True,
                                     customer_reply=False, opener_sent=True)
        self.assertEqual(out.action, "NO_DRIP")
        self.assertFalse(out.allowed)

    def test_an_actual_customer_reply_enables_the_supported_path(self):
        out = routes.opener_decision(channel="FB_DM", comment_only=True,
                                     customer_reply=True)
        self.assertEqual(out.action, "SUPPORTED_PATH")
        self.assertTrue(out.allowed)

    def test_an_opener_without_a_comment_is_refused(self):
        out = routes.opener_decision(channel="FB_DM", comment_only=False,
                                     customer_reply=False)
        self.assertFalse(out.allowed)
        self.assertEqual(out.reason, "OPENER_REQUIRES_COMMENT")

    def test_non_bool_input_is_refused(self):
        with self.assertRaises(routes.RouteError):
            routes.opener_decision(channel="FB_DM", comment_only="yes",
                                   customer_reply=False)


class HonestProofTests(unittest.TestCase):
    """C-20 clause 4: ordinary-reader proof is deferred, never claimed."""

    def test_capability_record_says_the_reader_proof_is_deferred(self):
        status = routes.capability_status()
        self.assertEqual(status["ordinary_reader_proof"], "DEFERRED")
        self.assertEqual(status["public_monitoring"], "NOT_PROVEN")
        self.assertEqual(status["ref_attribution"], "NOT_PROVEN")

    def test_all_three_routes_are_reported_supported(self):
        status = routes.capability_status()
        for route in (routes.ROUTE_PUBLIC_REPLY,
                      routes.ROUTE_COMMENT_PRIVATE_OPENER,
                      routes.ROUTE_INBOUND_DM):
            self.assertEqual(status["routes"][route], "SUPPORTED")


class CommonGateIntegrationTests(unittest.TestCase):
    """C-F04 reuse: the verdict feeds the ONE existing T-12 gate, not a copy."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fb-route-gate-")
        self.store = DurableStore(str(Path(self.tmp.name) / "s.sqlite"))
        self.sent = []

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _action(self, key):
        row, _ = self.store.create_intent(
            logical_intent_key=key, idempotency_key=key + "-idem",
            tenant_id="t1", scope="person_directed",
            canonical_contact_id="c1", content_sha256="h",
            purpose="AI_REPLY")
        self.store.queue(row["action_id"])
        return row["action_id"]

    def _sender(self, ctx):
        self.sent.append(ctx["action_id"])
        return {"provider": "facebook", "provider_receipt_id": "r1",
                "supported_status": "accepted"}

    def test_refused_eligibility_blocks_the_existing_gate(self):
        aid = self._action("L-blocked")
        facts = inbound_facts(eligibility_refreshed_by="OUTBOUND_MESSAGE")
        out = dispatch(self.store,
                       lambda ctx: routes.evaluate_eligibility(
                           routes.ROUTE_INBOUND_DM, facts),
                       self._sender, aid, "w1")
        self.assertEqual(out.status, ST_BLOCKED)
        self.assertEqual(out.verdict, "SUPPRESSED")
        self.assertEqual(self.sent, [])
        self.assertEqual(self.store.get_action(aid)["state"], "suppressed")

    def test_allowed_eligibility_sends_exactly_once(self):
        aid = self._action("L-allowed")
        out = dispatch(self.store,
                       lambda ctx: routes.evaluate_eligibility(
                           routes.ROUTE_INBOUND_DM, inbound_facts()),
                       self._sender, aid, "w1")
        self.assertEqual(out.status, ST_SENT)
        self.assertEqual(self.sent, [aid])


class EverySendGateFactTests(unittest.TestCase):
    """C-F04 / F-04B, F-04C (PBB-142 repair): the STOP and owner facts in the
    adapter's own fact mapping are load-bearing.

    Before the repair the adapter read neither `global_stop` nor
    `owner_current`, so F-04B (a global STOP) and F-04C (an owner that is not
    current) both evaluated ALLOW and sent through the common gate.
    """

    def verdict(self, route, facts):
        return routes.evaluate_eligibility(route, facts, now=1000.0)

    def test_f04b_a_global_stop_suppresses_the_inbound_reply(self):
        out = self.verdict(routes.ROUTE_INBOUND_DM,
                           inbound_facts(global_stop=True))
        self.assertEqual(out.verdict, "SUPPRESSED")
        self.assertEqual(out.evidence["reason"], "GLOBAL_STOP")

    def test_a_global_stop_suppresses_every_route(self):
        for route, facts in ((routes.ROUTE_PUBLIC_REPLY, public_facts()),
                             (routes.ROUTE_COMMENT_PRIVATE_OPENER,
                              opener_facts()),
                             (routes.ROUTE_INBOUND_DM, inbound_facts())):
            with self.subTest(route=route):
                out = self.verdict(route, dict(facts, global_stop=True))
                self.assertEqual(out.verdict, "SUPPRESSED")
                self.assertEqual(out.evidence["reason"], "GLOBAL_STOP")

    def test_f04c_an_owner_that_is_not_current_suppresses_the_public_reply(self):
        out = self.verdict(routes.ROUTE_PUBLIC_REPLY,
                           public_facts(owner_current=False))
        self.assertEqual(out.verdict, "SUPPRESSED")
        self.assertEqual(out.evidence["reason"], "OWNER_NOT_CURRENT")

    def test_an_owner_that_is_not_current_suppresses_every_route(self):
        for route, facts in ((routes.ROUTE_PUBLIC_REPLY, public_facts()),
                             (routes.ROUTE_COMMENT_PRIVATE_OPENER,
                              opener_facts()),
                             (routes.ROUTE_INBOUND_DM, inbound_facts())):
            with self.subTest(route=route):
                out = self.verdict(route, dict(facts, owner_current=False))
                self.assertEqual(out.verdict, "SUPPRESSED")
                self.assertEqual(out.evidence["reason"], "OWNER_NOT_CURRENT")

    def test_no_stop_and_a_current_owner_still_allow(self):
        # F-04's own clear shape: the gate must not blanket-refuse.
        for route, facts in ((routes.ROUTE_PUBLIC_REPLY, public_facts()),
                             (routes.ROUTE_COMMENT_PRIVATE_OPENER,
                              opener_facts()),
                             (routes.ROUTE_INBOUND_DM, inbound_facts())):
            with self.subTest(route=route):
                out = self.verdict(
                    route, dict(facts, global_stop=False, owner_current=True))
                self.assertEqual(out.verdict, "ALLOW")

    def test_absent_stop_and_owner_facts_still_allow(self):
        # Facts that carry no STOP and no ownership claim are not a STOP.
        minimal = {
            routes.ROUTE_PUBLIC_REPLY: {
                "channel": "FB_PUBLIC", "action_purpose": "PUBLIC_REPLY",
                "public_reply_permission": True},
            routes.ROUTE_COMMENT_PRIVATE_OPENER: {
                "channel": "FB_DM",
                "action_purpose": "COMMENT_PRIVATE_OPENER",
                "comment_event_id": "ev-1",
                "comment_private_opener_permission": True},
            routes.ROUTE_INBOUND_DM: {
                "channel": "FB_DM", "action_purpose": "AI_REPLY",
                "inbound_message_id": "ev-2", "inbound_dm_window": True,
                "eligibility_refreshed_by": "PLATFORM_ELIGIBILITY"},
        }
        for route, facts in minimal.items():
            with self.subTest(route=route):
                self.assertEqual(self.verdict(route, facts).verdict, "ALLOW")

    def test_a_stop_beats_a_changed_binding(self):
        # A stopped send is never resurrected by a later binding reconcile, so
        # the terminal suppression wins over the quarantine.
        out = self.verdict(routes.ROUTE_INBOUND_DM,
                           inbound_facts(global_stop=True,
                                         current_binding_revision="binding-8"))
        self.assertEqual(out.verdict, "SUPPRESSED")
        self.assertEqual(out.evidence["reason"], "GLOBAL_STOP")

    def test_f04b_and_f04c_never_reach_the_sender(self):
        # The exact composition T-20 ships: routes.evaluate_eligibility feeding
        # outbound_gate.dispatch. Both fixtures must block with no send.
        cases = (
            ("F-04B", routes.ROUTE_INBOUND_DM,
             inbound_facts(global_stop=True), "AI_REPLY"),
            ("F-04C", routes.ROUTE_PUBLIC_REPLY,
             public_facts(owner_current=False), "PUBLIC_REPLY"),
        )
        for name, route, facts, purpose in cases:
            with self.subTest(fixture=name):
                with tempfile.TemporaryDirectory(prefix="fb-route-f04-") as d:
                    store = DurableStore(str(Path(d) / "s.sqlite"))
                    row, _ = store.create_intent(
                        logical_intent_key="K-" + name,
                        idempotency_key="I-" + name,
                        tenant_id="t1", scope="person_directed",
                        canonical_contact_id="c1", content_sha256="h",
                        purpose=purpose)
                    store.queue(row["action_id"])
                    sent = []
                    out = dispatch(
                        store,
                        lambda ctx, f=facts, r=route:
                            routes.evaluate_eligibility(r, f),
                        lambda ctx: sent.append(ctx["action_id"])
                        or {"provider": "facebook",
                            "provider_receipt_id": "r1",
                            "supported_status": "accepted"},
                        row["action_id"], "w1")
                    self.assertEqual(out.status, ST_BLOCKED)
                    self.assertEqual(out.verdict, "SUPPRESSED")
                    self.assertEqual(sent, [],
                                     "sender was called under a suppression")
                    self.assertEqual(store.get_action(row["action_id"])["state"],
                                     "suppressed")
                    store.close()


class OwnActorIdShapeTests(unittest.TestCase):
    """C-20 clause 2 (PBB-142 repair): own_actor_ids is typed, and a bare
    string is rejected instead of degrading to its own characters."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fb-route-own-")
        self.store = DurableStore(str(Path(self.tmp.name) / "s.sqlite"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_a_bare_string_own_actor_ids_is_rejected(self):
        with self.assertRaises(routes.RouteError):
            routes.admit_inbound(self.store, tenant_id="t1",
                                 provider_event_id="e-str", actor_id="page-1",
                                 own_actor_ids="page-1")

    def test_the_rejected_call_admits_nothing_and_writes_no_row(self):
        with self.assertRaises(routes.RouteError):
            routes.admit_inbound(self.store, tenant_id="t1",
                                 provider_event_id="e-str", actor_id="page-1",
                                 own_actor_ids="page-1")
        # If the rejected call had written anything this would read "duplicate".
        clean = routes.admit_inbound(self.store, tenant_id="t1",
                                     provider_event_id="e-str",
                                     actor_id="reader-9",
                                     own_actor_ids=("page-1",))
        self.assertTrue(clean.admitted)

    def test_a_collection_still_excludes_the_own_actor(self):
        out = routes.admit_inbound(self.store, tenant_id="t1",
                                   provider_event_id="e-list", actor_id="page-1",
                                   own_actor_ids=["page-1"])
        self.assertFalse(out.admitted)
        self.assertEqual(out.reason, "excluded:own_actor")


class BindingVerificationTests(unittest.TestCase):
    """C-F04 'rebind' (PBB-142 repair): a binding that cannot be checked is not
    a passing binding. Before the repair a stale binding with no current value
    evaluated ALLOW."""

    def test_a_stale_binding_with_no_current_value_quarantines(self):
        out = routes.evaluate_eligibility(
            routes.ROUTE_PUBLIC_REPLY,
            public_facts(current_binding_revision=None), now=1000.0)
        self.assertEqual(out.verdict, "QUARANTINED")
        self.assertEqual(out.evidence["account_binding_revision"], "binding-7")
        self.assertIsNone(out.evidence["current_binding_revision"])

    def test_that_quarantine_still_blocks_the_common_gate(self):
        with tempfile.TemporaryDirectory(prefix="fb-route-bind-") as d:
            store = DurableStore(str(Path(d) / "s.sqlite"))
            row, _ = store.create_intent(
                logical_intent_key="L-unverified",
                idempotency_key="L-unverified-idem",
                tenant_id="t1", scope="person_directed",
                canonical_contact_id="c1", content_sha256="h",
                purpose="AI_REPLY")
            store.queue(row["action_id"])
            sent = []
            out = dispatch(
                store,
                lambda ctx: routes.evaluate_eligibility(
                    routes.ROUTE_INBOUND_DM,
                    inbound_facts(current_binding_revision=None)),
                lambda ctx: sent.append(ctx["action_id"])
                or {"provider": "facebook", "provider_receipt_id": "r1",
                    "supported_status": "accepted"},
                row["action_id"], "w1")
            self.assertEqual(out.status, ST_BLOCKED)
            self.assertEqual(sent, [])
            self.assertIn(store.get_action(row["action_id"])["state"],
                          ("suppressed", "quarantined"))
            store.close()


class PermissionKeyIsTheGateTests(unittest.TestCase):
    """Defect 4 (PBB-186): ROUTE_PERMISSION_KEY was a dead constant.

    It named the one fact authorising each route and appeared in no other
    line, so the map and the gate could drift apart unnoticed. Before the
    repair `src.count("ROUTE_PERMISSION_KEY") == 1`.

    Before: fails (count is 1).  After: passes (the gate consumes the map).
    """

    def verdict(self, route, facts):
        return routes.evaluate_eligibility(route, facts, now=1000.0)

    def test_the_permission_map_is_reachable_from_the_gate(self):
        src = Path(routes.__file__).read_text()
        self.assertGreater(src.count("ROUTE_PERMISSION_KEY"), 1,
                           "ROUTE_PERMISSION_KEY defined but never referenced")

    def test_every_route_names_exactly_one_permission_key(self):
        self.assertEqual(
            set(routes.ROUTE_PERMISSION_KEY), set(routes.ROUTES))
        self.assertEqual(len(set(routes.ROUTE_PERMISSION_KEY.values())),
                         len(routes.ROUTES), "one key per route, never shared")
        # The gate's refusal wording is paired with the key in one place too.
        refused = getattr(routes, "ROUTE_PERMISSION_REFUSED", None)
        self.assertIsNotNone(refused,
                             "ROUTE_PERMISSION_REFUSED is missing")
        self.assertEqual(set(refused), set(routes.ROUTES))

    def test_the_map_naming_the_fact_is_what_the_gate_consumes(self):
        # Rename the mapped key in the fact payload: the route must then be
        # refused on that exact key, proving the gate reads the map and not a
        # private second spelling of the name.
        cases = (
            (routes.ROUTE_PUBLIC_REPLY, public_facts(),
             routes.ROUTE_PERMISSION_KEY[routes.ROUTE_PUBLIC_REPLY],
             "NO_PUBLIC_REPLY_PERMISSION"),
            (routes.ROUTE_COMMENT_PRIVATE_OPENER, opener_facts(),
             routes.ROUTE_PERMISSION_KEY[routes.ROUTE_COMMENT_PRIVATE_OPENER],
             "NO_COMMENT_OPENER_PERMISSION"),
            (routes.ROUTE_INBOUND_DM, inbound_facts(),
             routes.ROUTE_PERMISSION_KEY[routes.ROUTE_INBOUND_DM],
             "NO_INBOUND_DM_WINDOW"),
        )
        for route, facts, key, reason in cases:
            with self.subTest(route=route, key=key):
                renamed = {k: v for k, v in facts.items() if k != key}
                renamed[key + "_renamed"] = True
                out = self.verdict(route, renamed)
                self.assertEqual((out.verdict, out.evidence["reason"]),
                                 ("SUPPRESSED", reason))
                self.assertEqual(out.evidence.get("missing"), key)
                # And the unchanged payload still allows.
                self.assertEqual(self.verdict(route, facts).verdict, "ALLOW")

    def test_a_false_permission_still_refuses_on_the_mapped_reason(self):
        for route, facts, reason in (
                (routes.ROUTE_PUBLIC_REPLY, public_facts(
                    public_reply_permission=False),
                 "NO_PUBLIC_REPLY_PERMISSION"),
                (routes.ROUTE_COMMENT_PRIVATE_OPENER, opener_facts(
                    comment_private_opener_permission=0),
                 "NO_COMMENT_OPENER_PERMISSION"),
                (routes.ROUTE_INBOUND_DM, inbound_facts(inbound_dm_window="yes"),
                 "NO_INBOUND_DM_WINDOW")):
            with self.subTest(route=route):
                out = self.verdict(route, facts)
                self.assertEqual((out.verdict, out.evidence["reason"]),
                                 ("SUPPRESSED", reason))


class RefAttributionIsChannelBoundTests(unittest.TestCase):
    """Defect 5 (PBB-186): resolve_entry ignored its channel argument.

    `channel` was validated and then never read, so an IG_DM entry was
    credited with an m.me Messenger link:
      resolve_entry(channel="IG_DM", ref="mme-ref-1",
                    ref_routes={"mme-ref-1": "item-guide"})
      -> route='item-guide', basis='REF', attribution='PRESENT'
    SPEC ("never assume link attribution") forbids that.

    Before: fails (attribution is PRESENT).  After: passes (UNRECOGNIZED).
    """

    REFS = {"mme-ref-1": "item-guide"}

    def test_an_instagram_entry_is_not_credited_with_a_messenger_link(self):
        out = routes.resolve_entry(channel="IG_DM", ref="mme-ref-1",
                                   ref_routes=self.REFS)
        self.assertNotEqual(out.attribution, routes.ATTRIBUTION_PRESENT,
                            f"IG_DM entry attributed to an m.me ref: {out}")
        self.assertEqual(out.attribution, routes.ATTRIBUTION_UNRECOGNIZED)

    def test_a_foreign_channel_ref_falls_through_to_the_keyword(self):
        out = routes.resolve_entry(channel="IG_DM", ref="mme-ref-1",
                                   text="vault",
                                   ref_routes=self.REFS,
                                   keyword_routes={"vault": "item-vault"})
        self.assertEqual(out.route, "item-vault")
        self.assertEqual(out.basis, routes.BASIS_KEYWORD_FALLBACK)
        self.assertEqual(out.attribution, routes.ATTRIBUTION_UNRECOGNIZED)

    def test_messenger_itself_still_credits_the_ref(self):
        out = routes.resolve_entry(channel="FB_DM", ref="mme-ref-1",
                                   ref_routes=self.REFS)
        self.assertEqual((out.route, out.basis, out.attribution),
                         ("item-guide", routes.BASIS_REF,
                          routes.ATTRIBUTION_PRESENT))

    def test_every_non_messenger_channel_is_refused_the_attribution(self):
        for channel in ("IG_DM", "IG_COMMENT", "FB_PUBLIC", "SMS"):
            with self.subTest(channel=channel):
                out = routes.resolve_entry(channel=channel, ref="mme-ref-1",
                                           ref_routes=self.REFS)
                self.assertNotEqual(out.attribution,
                                    routes.ATTRIBUTION_PRESENT)

    def test_no_attribution_source_invented_on_a_foreign_channel(self):
        out = routes.resolve_entry(channel="IG_DM", ref="mme-ref-1",
                                   ref_routes=self.REFS)
        self.assertIsNone(out.route)
        self.assertTrue(out.prompt_keyword)  # the welcome is the only effect


class ApprovedKeywordTableTests(unittest.TestCase):
    """Defect 6 (PBB-186): keyword_routes keys were not normalised.

    Only the typed text was normalised, so the routing table's own spelling
    decided the contract. An approved keyword of "GUIDE" (or "Guide",
    " guide ", "guide!") never routed, and every reader got the "which keyword
    did you see" welcome. The approval schema allows any string with
    minLength 1.

    Before: fails (route is None).  After: passes (the key is indexed the
    same way the text is).
    """

    def test_an_approved_keyword_typed_verbatim_routes(self):
        for key in ("GUIDE", "Guide", " guide ", "guide!"):
            with self.subTest(key=key):
                out = routes.resolve_entry(channel="FB_DM", text=key,
                                           keyword_routes={key: "item-guide"})
                self.assertEqual(out.route, "item-guide",
                                 f"approved key {key!r} typed verbatim -> {out}")

    def test_typing_it_normalised_or_padded_also_routes(self):
        for text in ("guide", "GUIDE", "  Guide!  ", "G U I D E".replace(" ", "")):
            with self.subTest(text=text):
                out = routes.resolve_entry(channel="FB_DM", text=text,
                                           keyword_routes={"GUIDE": "item-guide"})
                self.assertEqual(out.route, "item-guide")

    def test_keys_that_only_differ_in_normalisable_form_agree(self):
        # "guide" and "GUIDE" normalise to one token and name the same item:
        # that is a duplicate approval, not a conflict, and it still routes.
        out = routes.resolve_entry(
            channel="FB_DM", text=" guide! ",
            keyword_routes={"guide": "item-guide", "GUIDE": "item-guide"})
        self.assertEqual(out.route, "item-guide")
        out = routes.resolve_entry(channel="FB_DM", text="  GUIDE ",
                                   keyword_routes={" guide ": "item-guide",
                                                   "Guide.": "item-guide"})
        self.assertEqual(out.route, "item-guide")

    def test_two_keys_collapsing_to_one_route_agree(self):
        out = routes.resolve_entry(channel="FB_DM", text="vault",
                                   keyword_routes={"vault": "item-vault",
                                                   "VAULT": "item-vault"})
        self.assertEqual(out.route, "item-vault")

    def test_two_approved_keys_that_collide_and_disagree_are_refused(self):
        # Silent last-writer-wins would pick one of two different promises.
        with self.assertRaises(routes.RouteError):
            routes.resolve_entry(
                channel="FB_DM", text="guide",
                keyword_routes={"GUIDE": "item-guide", "guide!": "item-other"})

    def test_a_key_that_normalises_to_nothing_is_refused(self):
        for bad in ("   ", "!!!"):
            with self.subTest(key=bad):
                with self.assertRaises(routes.RouteError):
                    routes.resolve_entry(channel="FB_DM", text="guide",
                                         keyword_routes={bad: "item-guide"})

    def test_non_string_keys_and_empty_routes_are_refused(self):
        with self.assertRaises(routes.RouteError):
            routes.resolve_entry(channel="FB_DM", text="guide",
                                 keyword_routes={1: "item-guide"})
        with self.assertRaises(routes.RouteError):
            routes.resolve_entry(channel="FB_DM", text="guide",
                                 keyword_routes={"guide": "  "})
        with self.assertRaises(routes.RouteError):
            routes.resolve_entry(channel="FB_DM", text="guide",
                                 keyword_routes=["guide"])

    def test_never_still_substring_matches_after_normalisation(self):
        out = routes.resolve_entry(channel="FB_DM", text="GUIDED",
                                   keyword_routes={"GUIDE": "item-guide"})
        self.assertIsNone(out.route)
        self.assertTrue(out.prompt_keyword)


class UnverifiableBindingTests(unittest.TestCase):
    """PROBE-MIRROR (PBB-186 'observed'): an action carrying a current
    revision but no account_binding_revision evaluated ALLOW. The
    outbound-action schema requires account_binding_revision, so there is
    nothing to verify and the binding is not a passing one.

    Before: fails (ALLOW).  After: passes (QUARANTINED / BINDING_UNVERIFIED).
    """

    def test_no_action_binding_to_check_quarantines(self):
        for route, facts in ((routes.ROUTE_PUBLIC_REPLY, public_facts()),
                             (routes.ROUTE_COMMENT_PRIVATE_OPENER,
                              opener_facts()),
                             (routes.ROUTE_INBOUND_DM, inbound_facts())):
            with self.subTest(route=route):
                unverified = {k: v for k, v in facts.items()
                              if k != "account_binding_revision"}
                out = routes.evaluate_eligibility(route, unverified,
                                                  now=1000.0)
                self.assertEqual(out.verdict, "QUARANTINED")
                self.assertEqual(out.evidence["reason"], "BINDING_UNVERIFIED")
                self.assertIsNone(
                    out.evidence["account_binding_revision"])
                self.assertEqual(out.evidence["current_binding_revision"],
                                 "binding-7")

    def test_a_quiet_thread_with_no_binding_at_all_still_sends(self):
        # No binding claim anywhere is not a failed check; only a claimed
        # current revision with nothing to compare is.
        for route, facts in ((routes.ROUTE_PUBLIC_REPLY, public_facts()),
                             (routes.ROUTE_COMMENT_PRIVATE_OPENER,
                              opener_facts()),
                             (routes.ROUTE_INBOUND_DM, inbound_facts())):
            with self.subTest(route=route):
                quiet = {k: v for k, v in facts.items()
                         if k not in ("account_binding_revision",
                                      "current_binding_revision")}
                out = routes.evaluate_eligibility(route, quiet, now=1000.0)
                self.assertEqual(out.verdict, "ALLOW")


class ApprovalTableChannelTests(unittest.TestCase):
    """The ref table is trimmed, the keyword table is normalised, and both are
    indexed the way the lookup compares -- so no approved spelling is lost."""

    def test_padded_ref_keys_still_match_a_trimmed_ref(self):
        out = routes.resolve_entry(channel="FB_DM", ref="mme-ref-1",
                                   ref_routes={"  mme-ref-1  ": "item-guide"})
        self.assertEqual(out.route, "item-guide")

    def test_an_empty_ref_table_falls_through_to_the_keyword(self):
        out = routes.resolve_entry(channel="FB_DM", ref="mme-ref-1",
                                   text="guide",
                                   keyword_routes={"GUIDE": "item-guide"})
        self.assertEqual(out.route, "item-guide")
        self.assertEqual(out.basis, routes.BASIS_KEYWORD_FALLBACK)


if __name__ == "__main__":
    unittest.main(verbosity=2)
