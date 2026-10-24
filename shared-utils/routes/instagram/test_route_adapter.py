#!/usr/bin/env python3
"""Tests for PBB-118 / T-21: supported Instagram comment and direct routes.

Run from the repository root:
    python3 -m unittest discover -s shared-utils/routes/instagram -p 'test_route_adapter.py' -v
or directly:
    python3 shared-utils/routes/instagram/test_route_adapter.py

Every acceptance clause of the ledger record is pinned here, refusal cases
included:

  SEPARATE ACCOUNT      an Instagram binding is its own identity; a Facebook
                        page id never resolves one; two identity keys that
                        disagree are refused, never silently narrowed.
  SEPARATE FILTER       filters are Instagram- and account-scoped; a foreign
                        filter or a keywordless catch-all matches nothing.
  SEPARATE EVENT        only Instagram COMMENT and DIRECT are normalised;
                        Page comments/Messenger shapes are refused; duplicate,
                        outgoing and own-actor events have no second effect.
  SEPARATE ELIGIBILITY  a comment reply, a comment private opener and a DM
                        each carry their own basis; each route needs its own
                        granted Instagram capability; a comment is never a DM
                        window; outbound/cross-channel never refresh IG
                        eligibility; an FB capability is refused.
  IGNORED OPENER        once an opener is recorded, every follow-up DM is
                        suppressed until a VERIFIED inbound customer
                        interaction (an event the durable inbox admitted and
                        did not exclude); there is no timer and no second
                        opener; survives a restart.
  NO FB PARITY          FB-only capability names, FB filters and FB events
                        cannot produce Instagram eligibility.
  STOP / OWNER GATE     the upstream consent gate (global stop, human
                        ownership fence) decides every Instagram dispatch;
                        with no gate answer, or an answer that is not its
                        ALLOW, the route fails closed and never sends.
  FRESH GATE (C-F04)    STOP, rebind and window are decided on every
                        dispatch through outbound_gate.dispatch(); a blocked
                        attempt never sends and never records an opener.
  COMMENT TRACE (C-F08) comment -> opener -> ignored -> customer interaction
                        -> follow-up, with real durable rows and receipts.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
TOOLS_DIR = REPO_ROOT / "38-conversational-ai-system" / "tools"
for p in (str(HERE), str(TOOLS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from route_adapter import (  # noqa: E402
    ALLOW,
    BASIS_CROSS_CHANNEL_MESSAGE,
    BASIS_INBOUND_MESSAGE,
    BASIS_OUTBOUND_MESSAGE,
    CAP_COMMENT_PRIVATE_OPENER,
    CAP_COMMENT_PUBLIC_REPLY,
    CAP_DM_SEND,
    CHANNEL_IG_DM,
    CHANNEL_IG_PUBLIC,
    EVENT_COMMENT,
    EVENT_DIRECT,
    FB_ONLY_CAPABILITIES,
    InstagramAccount,
    InstagramCapability,
    InstagramCommentFilter,
    InstagramEvent,
    InstagramRouteError,
    InstagramRouteStore,
    PURPOSE_AI_REPLY,
    PURPOSE_CAPTURE_REMINDER,
    PURPOSE_COMMENT_PRIVATE_OPENER,
    PURPOSE_PUBLIC_REPLY,
    QUARANTINED,
    R_ACCOUNT_BINDING,
    R_ACCOUNT_FB,
    R_ACCOUNT_IDENTITY_CONFLICT,
    R_BASIS_NOT_REFRESHING,
    R_CAPABILITY_FB,
    R_CAPABILITY_MISSING,
    R_CAPABILITY_NOT_GRANTED,
    R_CONSENT_GATE_REQUIRED,
    R_EVENT_ACCOUNT_MISMATCH,
    R_EVENT_WRONG_KIND,
    R_FILTER_ACCOUNT_MISMATCH,
    R_FILTER_NOT_MATCHED,
    R_IGNORED_OPENER,
    R_NO_INBOUND_DM,
    R_OPENER_ALREADY_SENT,
    R_UNSUPPORTED_EVENT,
    R_UNVERIFIED_INTERACTION,
    admit_instagram_event,
    dispatch_instagram_action,
    evaluate_eligibility,
    make_gate_evaluator,
    match_filter,
    normalise_event,
    resolve_account,
)
from consent_gate import (  # noqa: E402
    ConsentStore,
    make_gate_evaluator as make_consent_evaluator,
)
from durable_store import DurableStore  # noqa: E402
from tenant_identity import TenantIdentity  # noqa: E402


def make_account(**over):
    values = dict(tenant_id="tenant-1", account_id="ig-acct-1",
                  ig_user_id="17841400000000001", binding_revision="bind-1")
    values.update(over)
    return InstagramAccount(**values)


def make_filter(**over):
    values = dict(filter_id="filter-1", account_id="ig-acct-1",
                  revision="frev-1", keywords=("billboard",),
                  match_mode="contains")
    values.update(over)
    return InstagramCommentFilter(**values)


def make_comment_event(**over):
    values = dict(provider="instagram", provider_event_id="evt-comment-1",
                  tenant_id="tenant-1", account_id="ig-acct-1",
                  kind=EVENT_COMMENT, direction="inbound",
                  actor_id="customer-1", text="billboard please",
                  thread_key="comment-1", comment_id="comment-1",
                  received_at=1000.0)
    values.update(over)
    return normalise_event(values)


def make_dm_event(**over):
    values = dict(provider="instagram", provider_event_id="evt-dm-1",
                  tenant_id="tenant-1", account_id="ig-acct-1",
                  kind=EVENT_DIRECT, direction="inbound",
                  actor_id="customer-1", text="send it",
                  thread_key="thread-1", received_at=1100.0)
    values.update(over)
    return normalise_event(values)

def allow_consent(_ctx):
    """The upstream consent gate's own ALLOW answer for a clear contact."""
    return {"verdict": ALLOW, "evidence": {"consent": "clear"}}


class _StoreCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="ig-t21-")
        self.addCleanup(self._tmp.cleanup)
        self.db = str(Path(self._tmp.name) / "outbox.sqlite")
        self.store = DurableStore(self.db)
        self.addCleanup(self.store.close)
        self.routes = InstagramRouteStore(self.db)
        self.addCleanup(self.routes.close)

    def intent(self, key, *, purpose, binding="bind-1", tenant="tenant-1",
               contact="contact-1"):
        row, _ = self.store.create_intent(
            logical_intent_key=key, idempotency_key=key + "-idem",
            tenant_id=tenant, scope="person_directed",
            canonical_contact_id=contact, content_sha256="sha-" + key,
            purpose=purpose, binding_revision=binding)
        self.store.queue(row["action_id"])
        return row["action_id"]

    @staticmethod
    def sender(log):
        def send(ctx):
            log.append(ctx["action_id"])
            return {"provider": "instagram", "provider_receipt_id":
                    "rcpt-" + ctx["action_id"]}
        return send

    def record_dm(self, provider_event_id, *, thread_key="thread-1",
                  now=None, own_actor_ids=(), **over):
        """Record one VERIFIED inbound customer DM: admitted first, then proof.

        Returns whatever record_customer_interaction returns, passing the
        event and the durable inbox admission it earned.
        """
        event = make_dm_event(provider_event_id=provider_event_id,
                              thread_key=thread_key, **over)
        admission = admit_instagram_event(self.store, event,
                                          own_actor_ids=own_actor_ids)
        return self.routes.record_customer_interaction(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key=thread_key, provider_event_id=provider_event_id,
            event=event, admission=admission, own_actor_ids=own_actor_ids,
            now=now)


class SeparateAccountTests(unittest.TestCase):
    def test_an_instagram_account_is_its_own_binding(self):
        account = make_account()
        self.assertEqual(account.platform, "IG")
        self.assertEqual(account.binding_revision, "bind-1")

    def test_a_facebook_page_id_never_resolves_an_instagram_account(self):
        with self.assertRaises(InstagramRouteError) as caught:
            resolve_account([make_account()], fb_page_id="page-999")
        self.assertIn(R_ACCOUNT_FB, str(caught.exception))

    def test_a_non_instagram_account_is_refused(self):
        with self.assertRaises(InstagramRouteError) as caught:
            make_account(platform="FB")
        self.assertIn(R_ACCOUNT_FB, str(caught.exception))

    def test_resolution_requires_exactly_one_instagram_identity(self):
        accounts = [make_account()]
        self.assertIs(resolve_account(accounts, account_id="ig-acct-1"),
                      accounts[0])
        self.assertIs(resolve_account(accounts, ig_user_id="17841400000000001"),
                      accounts[0])
        with self.assertRaises(InstagramRouteError):
            resolve_account(accounts, account_id="ig-acct-other")
        with self.assertRaises(InstagramRouteError):
            resolve_account(accounts)

    def test_two_identity_keys_that_agree_still_resolve(self):
        account = make_account()
        self.assertIs(resolve_account([account], account_id="ig-acct-1",
                                      ig_user_id="17841400000000001"), account)

    def test_two_identity_keys_that_disagree_are_refused(self):
        # One key alone used to win and the other was dropped silently.
        account = make_account()
        for kwargs in (dict(account_id="ig-acct-1",
                            ig_user_id="1784-DOES-NOT-MATCH"),
                       dict(account_id="ig-acct-other",
                            ig_user_id="17841400000000001")):
            with self.assertRaises(InstagramRouteError) as caught:
                resolve_account([account], **kwargs)
            self.assertIn(R_ACCOUNT_IDENTITY_CONFLICT, str(caught.exception),
                          kwargs)

    def test_conflicting_keys_never_pick_one_of_two_accounts(self):
        accounts = [make_account(),
                    make_account(account_id="ig-acct-2",
                                 ig_user_id="17841400000000002")]
        with self.assertRaises(InstagramRouteError):
            resolve_account(accounts, account_id="ig-acct-1",
                            ig_user_id="17841400000000002")


class SeparateFilterTests(unittest.TestCase):
    def test_filter_is_account_scoped(self):
        filter_ = make_filter()
        self.assertTrue(match_filter(filter_, "billboard please"))
        self.assertFalse(match_filter(filter_, "billboard please",
                                      account_id="ig-acct-2"))

    def test_facebook_filter_is_refused(self):
        with self.assertRaises(InstagramRouteError) as caught:
            make_filter(platform="FB")
        self.assertIn(R_ACCOUNT_FB, str(caught.exception))

    def test_exact_and_contains_modes_differ(self):
        exact = make_filter(match_mode="exact")
        self.assertTrue(match_filter(exact, "billboard"))
        self.assertFalse(match_filter(exact, "billboard please"))
        contains = make_filter(match_mode="contains")
        self.assertTrue(match_filter(contains, "billboard please"))

    def test_case_sensitivity_is_explicit(self):
        insensitive = make_filter(keywords=("BILLBOARD",))
        self.assertTrue(match_filter(insensitive, "billboard"))
        sensitive = make_filter(keywords=("BILLBOARD",), case_sensitive=True)
        self.assertFalse(match_filter(sensitive, "billboard"))
        self.assertTrue(match_filter(sensitive, "BILLBOARD"))

    def test_disabled_filter_matches_nothing(self):
        self.assertFalse(match_filter(make_filter(enabled=False), "billboard"))

    def test_a_keywordless_catch_all_is_refused(self):
        with self.assertRaises(InstagramRouteError):
            make_filter(keywords=())

    def test_blank_comment_matches_nothing(self):
        self.assertFalse(match_filter(make_filter(), "   "))
        self.assertFalse(match_filter(make_filter(), None))


class SeparateEventTests(unittest.TestCase):
    def test_comment_and_direct_are_distinct_routes(self):
        comment = make_comment_event()
        direct = make_dm_event()
        self.assertEqual(comment.kind, EVENT_COMMENT)
        self.assertEqual(direct.kind, EVENT_DIRECT)
        self.assertNotEqual(comment.thread_key, direct.thread_key)

    def test_facebook_page_comment_is_refused(self):
        with self.assertRaises(InstagramRouteError) as caught:
            normalise_event({"provider": "facebook", "provider_event_id": "e",
                             "tenant_id": "tenant-1", "account_id": "ig-acct-1",
                             "kind": "PAGE_COMMENT", "direction": "inbound",
                             "actor_id": "customer-1", "text": "billboard",
                             "thread_key": "c", "received_at": 1})
        self.assertIn(R_UNSUPPORTED_EVENT, str(caught.exception))

    def test_messenger_kind_is_refused(self):
        with self.assertRaises(InstagramRouteError) as caught:
            normalise_event({"provider": "instagram",
                             "provider_event_id": "e", "tenant_id": "tenant-1",
                             "account_id": "ig-acct-1", "kind": "MESSENGER",
                             "direction": "inbound", "actor_id": "customer-1",
                             "text": "hi", "thread_key": "t",
                             "received_at": 1})
        self.assertIn(R_UNSUPPORTED_EVENT, str(caught.exception))

    def test_unknown_event_fields_are_refused(self):
        with self.assertRaises(InstagramRouteError):
            normalise_event({"provider": "instagram",
                             "provider_event_id": "e", "tenant_id": "tenant-1",
                             "account_id": "ig-acct-1", "kind": EVENT_COMMENT,
                             "direction": "inbound", "actor_id": "c",
                             "text": "x", "thread_key": "t", "received_at": 1,
                             "fb_page_id": "page-1"})

    def test_duplicate_event_is_admitted_once(self):
        event = make_comment_event()
        store = self.store_for_test()
        first = admit_instagram_event(store, event)
        second = admit_instagram_event(store, event)
        self.assertTrue(first["admitted"])
        self.assertFalse(second["admitted"])
        self.assertEqual(second["reason"], "duplicate")

    def test_own_and_outgoing_events_are_excluded(self):
        store = self.store_for_test()
        own = make_dm_event(actor_id="ourselves")
        result = admit_instagram_event(store, own, own_actor_ids=("ourselves",))
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "excluded:own_actor")

        outgoing = make_comment_event(provider_event_id="evt-out-1",
                                      direction="outbound")
        result = admit_instagram_event(store, outgoing)
        self.assertFalse(result["admitted"])
        self.assertIn("excluded:direction", result["reason"])

    def store_for_test(self):
        tmp = tempfile.TemporaryDirectory(prefix="ig-inbox-")
        self.addCleanup(tmp.cleanup)
        store = DurableStore(str(Path(tmp.name) / "inbox.sqlite"))
        self.addCleanup(store.close)
        return store


class SeparateEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.account = make_account()
        self.filter = make_filter()
        self.comment = make_comment_event()

    def test_comment_public_reply_is_eligible_on_its_own_basis(self):
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_PUBLIC_REPLY,
            channel=CHANNEL_IG_PUBLIC, event=self.comment,
            filter_=self.filter,
            capability=InstagramCapability(CAP_COMMENT_PUBLIC_REPLY))
        self.assertTrue(verdict.allowed)
        self.assertEqual(verdict.refreshed_by, BASIS_INBOUND_MESSAGE)
        self.assertFalse(verdict.inbound_dm_window)

    def test_public_reply_requires_the_comment_filter_to_match(self):
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_PUBLIC_REPLY,
            channel=CHANNEL_IG_PUBLIC,
            event=make_comment_event(text="unrelated"),
            filter_=self.filter,
            capability=InstagramCapability(CAP_COMMENT_PUBLIC_REPLY))
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.reason, R_FILTER_NOT_MATCHED)

    def test_foreign_account_filter_is_refused(self):
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_PUBLIC_REPLY,
            channel=CHANNEL_IG_PUBLIC, event=self.comment,
            filter_=make_filter(account_id="ig-acct-2"),
            capability=InstagramCapability(CAP_COMMENT_PUBLIC_REPLY))
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.reason, R_FILTER_ACCOUNT_MISMATCH)

    def test_event_from_another_account_is_refused(self):
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_PUBLIC_REPLY,
            channel=CHANNEL_IG_PUBLIC,
            event=make_comment_event(account_id="ig-acct-2"),
            filter_=self.filter,
            capability=InstagramCapability(CAP_COMMENT_PUBLIC_REPLY))
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.reason, R_EVENT_ACCOUNT_MISMATCH)

    def test_a_dm_event_cannot_authorize_a_comment_reply(self):
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_PUBLIC_REPLY,
            channel=CHANNEL_IG_PUBLIC, event=make_dm_event(),
            filter_=self.filter,
            capability=InstagramCapability(CAP_COMMENT_PUBLIC_REPLY))
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.reason, R_EVENT_WRONG_KIND)

    def test_a_public_reply_needs_its_own_capability(self):
        # No capability at all: a public reply used to be eligible anyway.
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_PUBLIC_REPLY,
            channel=CHANNEL_IG_PUBLIC, event=self.comment,
            filter_=self.filter)
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.reason, R_CAPABILITY_MISSING)

    def test_a_public_reply_does_not_borrow_the_opener_or_dm_capability(self):
        for name in (CAP_COMMENT_PRIVATE_OPENER, CAP_DM_SEND):
            verdict = evaluate_eligibility(
                account=self.account, purpose=PURPOSE_PUBLIC_REPLY,
                channel=CHANNEL_IG_PUBLIC, event=self.comment,
                filter_=self.filter, capability=InstagramCapability(name))
            self.assertFalse(verdict.allowed, name)
            self.assertEqual(verdict.reason, R_CAPABILITY_MISSING, name)

    def test_a_capability_that_is_not_granted_does_not_authorize(self):
        for purpose, channel, name, event in (
                (PURPOSE_PUBLIC_REPLY, CHANNEL_IG_PUBLIC,
                 CAP_COMMENT_PUBLIC_REPLY, self.comment),
                (PURPOSE_COMMENT_PRIVATE_OPENER, CHANNEL_IG_DM,
                 CAP_COMMENT_PRIVATE_OPENER, self.comment),
                (PURPOSE_AI_REPLY, CHANNEL_IG_DM, CAP_DM_SEND,
                 make_dm_event())):
            verdict = evaluate_eligibility(
                account=self.account, purpose=purpose, channel=channel,
                event=event, filter_=self.filter,
                capability=InstagramCapability(name, granted=False))
            self.assertFalse(verdict.allowed, name)
            self.assertEqual(verdict.reason, R_CAPABILITY_NOT_GRANTED, name)
            self.assertFalse(verdict.inbound_dm_window, name)

    def test_opener_requires_its_own_capability(self):
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_COMMENT_PRIVATE_OPENER,
            channel=CHANNEL_IG_DM, event=self.comment, filter_=self.filter,
            capability=InstagramCapability(CAP_DM_SEND))
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.reason, R_CAPABILITY_MISSING)

    def test_comment_alone_is_not_an_inbound_dm_window(self):
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_COMMENT_PRIVATE_OPENER,
            channel=CHANNEL_IG_DM, event=self.comment, filter_=self.filter,
            capability=InstagramCapability(CAP_COMMENT_PRIVATE_OPENER))
        self.assertTrue(verdict.allowed)
        self.assertFalse(verdict.inbound_dm_window)
        self.assertEqual(verdict.refreshed_by, BASIS_INBOUND_MESSAGE)

    def test_a_comment_does_not_authorize_a_follow_up_dm(self):
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_AI_REPLY,
            channel=CHANNEL_IG_DM, event=self.comment,
            capability=InstagramCapability(CAP_DM_SEND))
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.reason, R_NO_INBOUND_DM)

    def test_inbound_customer_dm_is_a_window(self):
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_AI_REPLY,
            channel=CHANNEL_IG_DM, event=make_dm_event(),
            capability=InstagramCapability(CAP_DM_SEND))
        self.assertTrue(verdict.allowed)
        self.assertTrue(verdict.inbound_dm_window)
        self.assertEqual(verdict.refreshed_by, BASIS_INBOUND_MESSAGE)

    def test_outbound_and_cross_channel_never_refresh_eligibility(self):
        for basis in (BASIS_OUTBOUND_MESSAGE, BASIS_CROSS_CHANNEL_MESSAGE):
            verdict = evaluate_eligibility(
                account=self.account, purpose=PURPOSE_AI_REPLY,
                channel=CHANNEL_IG_DM, event=make_dm_event(),
                capability=InstagramCapability(CAP_DM_SEND), basis=basis)
            self.assertFalse(verdict.allowed, basis)
            self.assertEqual(verdict.reason, R_BASIS_NOT_REFRESHING, basis)

    def test_refreshed_by_is_never_an_outbound_basis(self):
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_AI_REPLY,
            channel=CHANNEL_IG_DM, event=make_dm_event(),
            capability=InstagramCapability(CAP_DM_SEND))
        self.assertNotIn(verdict.refreshed_by,
                         (BASIS_OUTBOUND_MESSAGE, BASIS_CROSS_CHANNEL_MESSAGE))

    def test_channel_purpose_mismatch_is_refused(self):
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_PUBLIC_REPLY,
            channel=CHANNEL_IG_DM, event=self.comment, filter_=self.filter)
        self.assertFalse(verdict.allowed)


class NoFacebookParityTests(unittest.TestCase):
    def test_fb_only_capability_names_are_refused(self):
        for name in FB_ONLY_CAPABILITIES:
            with self.assertRaises(InstagramRouteError) as caught:
                InstagramCapability(name)
            self.assertIn(R_CAPABILITY_FB, str(caught.exception), name)

    def test_an_fb_platform_capability_is_refused(self):
        with self.assertRaises(InstagramRouteError):
            InstagramCapability(CAP_DM_SEND, platform="FB")

    def test_an_fb_filter_revision_cannot_enter_ig_eligibility(self):
        with self.assertRaises(InstagramRouteError):
            make_filter(platform="FB")

    def test_an_fb_event_cannot_produce_ig_eligibility(self):
        with self.assertRaises(InstagramRouteError):
            normalise_event({"provider": "facebook", "provider_event_id": "e",
                             "tenant_id": "tenant-1", "account_id": "ig-acct-1",
                             "kind": EVENT_COMMENT, "direction": "inbound",
                             "actor_id": "customer-1", "text": "billboard",
                             "thread_key": "c", "received_at": 1})


class IgnoredOpenerTests(_StoreCase):
    def setUp(self):
        super().setUp()
        self.account = make_account()
        self.filter = make_filter()
        self.comment = make_comment_event()

    def test_ignored_opener_blocks_every_follow_up_purpose(self):
        self.routes.record_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", opener_action_id="act-opener",
            comment_id="comment-1", now=2000.0)
        state = self.routes.opener_state("tenant-1", "ig-acct-1", "thread-1")
        for purpose in (PURPOSE_AI_REPLY, PURPOSE_CAPTURE_REMINDER):
            verdict = evaluate_eligibility(
                account=self.account, purpose=purpose, channel=CHANNEL_IG_DM,
                opener=state, capability=InstagramCapability(CAP_DM_SEND),
                now=3000.0)
            self.assertFalse(verdict.allowed, purpose)
            self.assertEqual(verdict.reason, R_IGNORED_OPENER, purpose)

    def test_there_is_no_timed_drip(self):
        self.routes.record_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", opener_action_id="act-opener", now=1.0)
        state = self.routes.opener_state("tenant-1", "ig-acct-1", "thread-1")
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_CAPTURE_REMINDER,
            channel=CHANNEL_IG_DM, opener=state,
            capability=InstagramCapability(CAP_DM_SEND), now=10 ** 9)
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.reason, R_IGNORED_OPENER)

    def test_customer_interaction_ends_the_ignored_state(self):
        self.routes.record_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", opener_action_id="act-opener", now=10.0)
        self.assertTrue(self.record_dm("dm-1", now=20.0))
        state = self.routes.opener_state("tenant-1", "ig-acct-1", "thread-1")
        self.assertTrue(state.customer_responded)
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_AI_REPLY,
            channel=CHANNEL_IG_DM, opener=state,
            capability=InstagramCapability(CAP_DM_SEND), now=30.0)
        self.assertTrue(verdict.allowed)
        self.assertTrue(verdict.inbound_dm_window)

    def test_a_thread_never_gets_a_second_opener(self):
        first, created = self.routes.record_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", opener_action_id="act-opener-1", now=10.0)
        self.assertTrue(created)
        second, created_again = self.routes.record_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", opener_action_id="act-opener-2", now=20.0)
        self.assertFalse(created_again)
        self.assertEqual(second["opener_action_id"], "act-opener-1")
        state = OpenerStateOf(self.routes)
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_COMMENT_PRIVATE_OPENER,
            channel=CHANNEL_IG_DM, event=self.comment, filter_=self.filter,
            capability=InstagramCapability(CAP_COMMENT_PRIVATE_OPENER),
            opener=state)
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.reason, R_OPENER_ALREADY_SENT)

    def test_duplicate_customer_interaction_has_one_effect(self):
        self.routes.record_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", opener_action_id="act-opener", now=10.0)
        self.assertTrue(self.record_dm("dm-1", now=20.0))
        self.assertFalse(self.record_dm("dm-1", now=30.0))

    def test_opener_state_survives_a_restart(self):
        self.routes.record_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", opener_action_id="act-opener", now=10.0)
        self.routes.close()
        reopened = InstagramRouteStore(self.db)
        self.addCleanup(reopened.close)
        state = reopened.opener_state("tenant-1", "ig-acct-1", "thread-1")
        self.assertIsNotNone(state)
        self.assertEqual(state.opener_action_id, "act-opener")
        self.assertFalse(state.customer_responded)


def OpenerStateOf(route_store):
    return route_store.opener_state("tenant-1", "ig-acct-1", "thread-1")

class VerifiedInteractionTests(_StoreCase):
    """Only a VERIFIED inbound customer interaction ends the ignored opener."""

    def setUp(self):
        super().setUp()
        self.account = make_account()
        self.filter = make_filter()
        self.comment = make_comment_event()
        self.routes.record_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", opener_action_id="act-opener", now=10.0)

    def follow_up_is_still_ignored(self):
        state = self.routes.opener_state("tenant-1", "ig-acct-1", "thread-1")
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_AI_REPLY, channel=CHANNEL_IG_DM,
            event=make_dm_event(thread_key="thread-1"), opener=state,
            capability=InstagramCapability(CAP_DM_SEND), now=60.0)
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.reason, R_IGNORED_OPENER)

    def assert_refused(self, **over):
        values = dict(tenant_id="tenant-1", account_id="ig-acct-1",
                      thread_key="thread-1", now=20.0)
        values.update(over)
        with self.assertRaises(InstagramRouteError) as caught:
            self.routes.record_customer_interaction(**values)
        self.assertIn(R_UNVERIFIED_INTERACTION, str(caught.exception))

    def test_a_record_with_no_proof_at_all_is_refused(self):
        # The whole record was caller convention: any id un-suppressed the thread.
        self.assert_refused(provider_event_id="dm-1")
        self.follow_up_is_still_ignored()

    def test_a_dm_the_inbox_excluded_as_outbound_never_un_suppresses(self):
        outbound = make_dm_event(provider_event_id="dm-out-1",
                                 thread_key="thread-1", direction="outbound")
        admission = admit_instagram_event(self.store, outbound)
        self.assertFalse(admission["admitted"])
        self.assert_refused(provider_event_id="dm-out-1", event=outbound,
                            admission=admission)
        self.follow_up_is_still_ignored()

    def test_an_event_id_the_inbox_never_admitted_is_refused(self):
        event = make_dm_event(provider_event_id="dm-never-1",
                              thread_key="thread-1")
        self.assert_refused(provider_event_id="dm-never-1", event=event,
                            admission={"admitted": False,
                                       "reason": "not_found", "row": None})
        self.follow_up_is_still_ignored()

    def test_an_own_actor_event_never_un_suppresses(self):
        own = make_dm_event(provider_event_id="dm-own-1", thread_key="thread-1",
                            actor_id="ourselves")
        admission = admit_instagram_event(self.store, own,
                                          own_actor_ids=("ourselves",))
        self.assertFalse(admission["admitted"])
        self.assert_refused(provider_event_id="dm-own-1", event=own,
                            admission=admission, own_actor_ids=("ourselves",))
        self.follow_up_is_still_ignored()

    def test_the_admission_of_another_event_is_not_proof(self):
        event = make_dm_event(provider_event_id="dm-mismatch-1",
                              thread_key="thread-1")
        other = admit_instagram_event(
            self.store, make_dm_event(provider_event_id="dm-other-1",
                                      thread_key="thread-1"))
        self.assert_refused(provider_event_id="dm-mismatch-1", event=event,
                            admission=other)
        self.follow_up_is_still_ignored()

    def test_a_verified_inbound_dm_ends_the_ignored_opener(self):
        self.assertTrue(self.record_dm("dm-ok-1", now=20.0))
        state = self.routes.opener_state("tenant-1", "ig-acct-1", "thread-1")
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_AI_REPLY, channel=CHANNEL_IG_DM,
            event=make_dm_event(thread_key="thread-1"), opener=state,
            capability=InstagramCapability(CAP_DM_SEND), now=60.0)
        self.assertTrue(verdict.allowed)
        self.assertTrue(verdict.inbound_dm_window)

    def test_a_redelivered_dm_is_still_proof_of_the_same_interaction(self):
        self.assertTrue(self.record_dm("dm-redeliver-1", now=20.0))
        # The provider redelivers: the inbox calls it a duplicate, which is
        # proof the SAME event was admitted, and the row stays one.
        self.assertFalse(self.record_dm("dm-redeliver-1", now=30.0))


class FreshGateTests(_StoreCase):
    def setUp(self):
        super().setUp()
        self.account = make_account()
        self.filter = make_filter()
        self.comment = make_comment_event()

    def opener_dispatch(self, action_id, *, consent=allow_consent,
                        thread="comment-1"):
        log = []
        outcome = dispatch_instagram_action(
            self.store, account=self.account, route_store=self.routes,
            action_id=action_id, worker_id="worker-1",
            purpose=PURPOSE_COMMENT_PRIVATE_OPENER, channel=CHANNEL_IG_DM,
            thread_key=thread, event=self.comment, filter_=self.filter,
            capability=InstagramCapability(CAP_COMMENT_PRIVATE_OPENER),
            consent_evaluator=consent, sender=self.sender(log), now=1000.0)
        return outcome, log

    def test_stop_suppresses_and_the_sender_is_never_called(self):
        action_id = self.intent("stop-1", purpose=PURPOSE_COMMENT_PRIVATE_OPENER)

        def consent(_ctx):
            return {"verdict": "SUPPRESSED",
                    "evidence": {"reason": "consent:global_stop"}}

        outcome, log = self.opener_dispatch(action_id, consent=consent)
        self.assertEqual(outcome.status, "blocked")
        self.assertEqual(log, [])
        self.assertEqual(self.store.get_action(action_id)["state"], "suppressed")
        self.assertIsNone(self.routes.opener_state(
            "tenant-1", "ig-acct-1", "comment-1"))

    def real_consent(self):
        """The REAL upstream consent gate (T-12/T-18), one IG contact."""
        identity = TenantIdentity(str(Path(self._tmp.name) / "identity.sqlite"))
        identity.register_tenant("tenant-1")
        contact = identity.bind("tenant-1", [("ig_psid", "customer-1", True)])
        consent = ConsentStore(identity)
        return consent, contact, make_consent_evaluator(consent)

    def test_the_consent_gate_is_not_optional_on_this_route(self):
        # No gate answer at all is not permission: this used to send.
        action_id = self.intent("no-consent-1",
                                purpose=PURPOSE_COMMENT_PRIVATE_OPENER)
        outcome, log = self.opener_dispatch(action_id, consent=None)
        self.assertEqual(outcome.status, "blocked")
        self.assertEqual(outcome.verdict, "SUPPRESSED")
        self.assertEqual(log, [])
        self.assertEqual(self.store.get_action(action_id)["state"], "suppressed")
        self.assertIsNone(self.routes.opener_state(
            "tenant-1", "ig-acct-1", "comment-1"))
        evidence = json.loads(self.store.gate_checks(action_id)[0]["evidence_json"])
        self.assertEqual(evidence["reason"], R_CONSENT_GATE_REQUIRED)

    def test_an_answer_that_is_not_the_gates_allow_fails_closed(self):
        for i, answer in enumerate((None, "ALLOW", True, {}, {"evidence": {}},
                                    {"verdict": "MAYBE"})):
            action_id = self.intent("bad-consent-%d" % i,
                                    purpose=PURPOSE_COMMENT_PRIVATE_OPENER)
            outcome, log = self.opener_dispatch(
                action_id, consent=lambda _ctx, answer=answer: answer)
            self.assertEqual(outcome.status, "blocked", answer)
            self.assertEqual(log, [], answer)
            self.assertIsNone(self.routes.opener_state(
                "tenant-1", "ig-acct-1", "comment-1"), answer)

    def test_the_upstream_global_stop_suppresses_this_route(self):
        consent, contact, evaluator = self.real_consent()
        consent.global_stop("tenant-1", contact)
        action_id = self.intent("real-stop-1",
                                purpose=PURPOSE_COMMENT_PRIVATE_OPENER,
                                contact=contact)
        outcome, log = self.opener_dispatch(action_id, consent=evaluator)
        self.assertEqual(outcome.status, "blocked")
        self.assertEqual(log, [])
        self.assertEqual(self.store.get_action(action_id)["state"], "suppressed")
        self.assertIsNone(self.routes.opener_state(
            "tenant-1", "ig-acct-1", "comment-1"))
        evidence = json.loads(self.store.gate_checks(action_id)[0]["evidence_json"])
        self.assertEqual(evidence["reason"], "consent:global_stop")

    def test_the_human_owner_fence_holds_until_it_is_released(self):
        consent, contact, evaluator = self.real_consent()
        consent.human_takeover("tenant-1", contact, actor="jill")
        fenced = self.intent("real-fence-1",
                             purpose=PURPOSE_COMMENT_PRIVATE_OPENER,
                             contact=contact)
        outcome, log = self.opener_dispatch(fenced, consent=evaluator)
        self.assertEqual(outcome.status, "blocked")
        self.assertEqual(log, [])
        self.assertEqual(self.store.get_action(fenced)["state"], "suppressed")
        evidence = json.loads(self.store.gate_checks(fenced)[0]["evidence_json"])
        self.assertEqual(evidence["reason"], "consent:human_owned")
        # The owner releases: the same route sends again.
        consent.human_release("tenant-1", contact, actor="jill")
        released = self.intent("real-fence-2",
                               purpose=PURPOSE_COMMENT_PRIVATE_OPENER,
                               contact=contact)
        outcome, log = self.opener_dispatch(released, consent=evaluator)
        self.assertEqual(outcome.status, "sent")
        self.assertEqual(log, [released])

    def test_a_changed_binding_quarantines_instead_of_rerouting(self):
        action_id = self.intent("rebind-1",
                                purpose=PURPOSE_COMMENT_PRIVATE_OPENER,
                                binding="bind-old")
        outcome, log = self.opener_dispatch(action_id)
        self.assertEqual(outcome.status, "blocked")
        self.assertEqual(outcome.verdict, QUARANTINED)
        self.assertEqual(log, [])
        self.assertEqual(self.store.get_action(action_id)["state"], "quarantined")
        checks = self.store.gate_checks(action_id)
        self.assertEqual(json.loads(checks[0]["evidence_json"])["reason"],
                         R_ACCOUNT_BINDING)

    def test_window_is_recomputed_on_every_dispatch(self):
        action_id = self.intent("window-1", purpose=PURPOSE_AI_REPLY)
        # The opener lands after the action was queued, before dispatch.
        self.routes.record_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="comment-1", opener_action_id="act-opener", now=500.0)
        log = []
        outcome = dispatch_instagram_action(
            self.store, account=self.account, route_store=self.routes,
            action_id=action_id, worker_id="worker-1",
            purpose=PURPOSE_AI_REPLY, channel=CHANNEL_IG_DM,
            thread_key="comment-1", event=make_dm_event(),
            capability=InstagramCapability(CAP_DM_SEND),
            consent_evaluator=allow_consent,
            sender=self.sender(log), now=1000.0)
        self.assertEqual(outcome.status, "blocked")
        self.assertEqual(outcome.verdict, "SUPPRESSED")
        self.assertEqual(log, [])
        checks = self.store.gate_checks(action_id)
        self.assertEqual(json.loads(checks[0]["evidence_json"])["reason"],
                         R_IGNORED_OPENER)

    def test_an_allowed_opener_sends_once_and_is_recorded(self):
        action_id = self.intent("allow-1",
                                purpose=PURPOSE_COMMENT_PRIVATE_OPENER)
        outcome, log = self.opener_dispatch(action_id)
        self.assertEqual(outcome.status, "sent")
        self.assertEqual(log, [action_id])
        state = self.routes.opener_state("tenant-1", "ig-acct-1", "comment-1")
        self.assertIsNotNone(state)
        self.assertEqual(state.opener_action_id, action_id)

    def test_the_gate_record_carries_the_ig_eligibility_facts(self):
        action_id = self.intent("facts-1",
                                purpose=PURPOSE_COMMENT_PRIVATE_OPENER)
        self.opener_dispatch(action_id)
        evidence = json.loads(self.store.gate_checks(action_id)[0]["evidence_json"])
        self.assertEqual(evidence["purpose"], PURPOSE_COMMENT_PRIVATE_OPENER)
        self.assertEqual(evidence["channel"], CHANNEL_IG_DM)
        self.assertFalse(evidence["inbound_dm_window"])
        self.assertEqual(evidence["eligibility_refreshed_by"],
                         BASIS_INBOUND_MESSAGE)

    def test_a_provider_exception_records_no_opener(self):
        action_id = self.intent("fail-1",
                                purpose=PURPOSE_COMMENT_PRIVATE_OPENER)

        def failing(_ctx):
            raise RuntimeError("provider down")

        outcome = dispatch_instagram_action(
            self.store, account=self.account, route_store=self.routes,
            action_id=action_id, worker_id="worker-1",
            purpose=PURPOSE_COMMENT_PRIVATE_OPENER, channel=CHANNEL_IG_DM,
            thread_key="comment-1", event=self.comment, filter_=self.filter,
            capability=InstagramCapability(CAP_COMMENT_PRIVATE_OPENER),
            consent_evaluator=allow_consent,
            sender=failing, now=1000.0)
        self.assertEqual(outcome.status, "send_error")
        self.assertIsNone(self.routes.opener_state(
            "tenant-1", "ig-acct-1", "comment-1"))


class CommentOpenerTraceTests(_StoreCase):
    """C-F08: the minimal comment -> opener -> customer interaction trace."""

    def test_the_full_supported_trace(self):
        account = make_account()
        filter_ = make_filter()
        comment = make_comment_event()
        log = []
        send = self.sender(log)

        # 1. The comment is admitted once, through the durable inbox.
        first = admit_instagram_event(self.store, comment)
        second = admit_instagram_event(self.store, comment)
        self.assertTrue(first["admitted"])
        self.assertFalse(second["admitted"])

        # 2. A public reply is eligible from the comment, the filter and
        #    its own granted capability.
        public = evaluate_eligibility(
            account=account, purpose=PURPOSE_PUBLIC_REPLY,
            channel=CHANNEL_IG_PUBLIC, event=comment, filter_=filter_,
            capability=InstagramCapability(CAP_COMMENT_PUBLIC_REPLY))
        self.assertTrue(public.allowed)

        # 3. One private opener is sent and recorded.
        opener_id = self.intent("trace-opener",
                                purpose=PURPOSE_COMMENT_PRIVATE_OPENER)
        outcome = dispatch_instagram_action(
            self.store, account=account, route_store=self.routes,
            action_id=opener_id, worker_id="worker-1",
            purpose=PURPOSE_COMMENT_PRIVATE_OPENER, channel=CHANNEL_IG_DM,
            thread_key=comment.thread_key, event=comment, filter_=filter_,
            capability=InstagramCapability(CAP_COMMENT_PRIVATE_OPENER),
            consent_evaluator=allow_consent,
            sender=send, now=2000.0)
        self.assertEqual(outcome.status, "sent")
        self.assertEqual(log, [opener_id])
        self.assertEqual(self.store.get_action(opener_id)["state"], "dispatched")

        # 4. The opener is ignored: a follow-up is blocked, nothing sent.
        follow_id = self.intent("trace-follow", purpose=PURPOSE_CAPTURE_REMINDER)
        blocked = dispatch_instagram_action(
            self.store, account=account, route_store=self.routes,
            action_id=follow_id, worker_id="worker-1",
            purpose=PURPOSE_CAPTURE_REMINDER, channel=CHANNEL_IG_DM,
            thread_key=comment.thread_key,
            capability=InstagramCapability(CAP_DM_SEND),
            consent_evaluator=allow_consent,
            sender=send, now=3000.0)
        self.assertEqual(blocked.status, "blocked")
        self.assertEqual(blocked.verdict, "SUPPRESSED")
        self.assertEqual(log, [opener_id])
        self.assertEqual(self.store.get_action(follow_id)["state"], "suppressed")

        # 5. A record with no proof never un-suppresses the thread.
        with self.assertRaises(InstagramRouteError):
            self.routes.record_customer_interaction(
                tenant_id="tenant-1", account_id="ig-acct-1",
                thread_key=comment.thread_key, provider_event_id="dm-reply-1",
                now=4000.0)

        # 6. The customer answers and the inbox ADMITS the DM: that proof
        #    ends the ignored-opener state.
        reply = make_dm_event(provider_event_id="dm-reply-1",
                              thread_key=comment.thread_key)
        admission = admit_instagram_event(self.store, reply)
        self.assertTrue(admission["admitted"])
        self.assertTrue(self.routes.record_customer_interaction(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key=comment.thread_key, provider_event_id="dm-reply-1",
            event=reply, admission=admission, now=4000.0))
        retry_id = self.intent("trace-follow-2", purpose=PURPOSE_CAPTURE_REMINDER)
        sent = dispatch_instagram_action(
            self.store, account=account, route_store=self.routes,
            action_id=retry_id, worker_id="worker-1",
            purpose=PURPOSE_CAPTURE_REMINDER, channel=CHANNEL_IG_DM,
            thread_key=comment.thread_key, event=make_dm_event(),
            capability=InstagramCapability(CAP_DM_SEND),
            consent_evaluator=allow_consent,
            sender=send, now=5000.0)
        self.assertEqual(sent.status, "sent")
        self.assertEqual(log, [opener_id, retry_id])
        evidence = json.loads(self.store.gate_checks(retry_id)[0]["evidence_json"])
        self.assertTrue(evidence["inbound_dm_window"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
