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
                        did not exclude); there is no timer, and no second
                        opener within the opener claim's lease; survives a
                        restart.
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
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
TOOLS_DIR = REPO_ROOT / "38-conversational-ai-system" / "tools"
for p in (str(HERE), str(TOOLS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import route_adapter  # noqa: E402
from route_adapter import (  # noqa: E402
    ALLOW,
    BASIS_CONSENT_RECORD,
    BASIS_CROSS_CHANNEL_MESSAGE,
    BASIS_INBOUND_MESSAGE,
    BASIS_OUTBOUND_MESSAGE,
    BASIS_PLATFORM_ELIGIBILITY,
    CAP_COMMENT_PRIVATE_OPENER,
    CAP_COMMENT_PUBLIC_REPLY,
    CAP_DM_SEND,
    CHANNEL_IG_DM,
    CHANNEL_IG_PUBLIC,
    DEFAULT_OPENER_CLAIM_S,
    EVENT_COMMENT,
    EVENT_DIRECT,
    FB_ONLY_CAPABILITIES,
    InstagramAccount,
    InstagramCapability,
    InstagramCommentFilter,
    InstagramEvent,
    InstagramRouteError,
    InstagramRouteStore,
    OpenerState,
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
    R_CHANNEL_PURPOSE_MISMATCH,
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

def admitted_inbox(case, event, account=None):
    """A durable inbox that has REALLY admitted `event`, and the store itself.

    The proof of an inbound customer DM is the inbox ROW, so a probe or test
    that wants the window has to earn it the way production does: through
    `admit_instagram_event` against a live `inbox_events`. It returns the
    STORE (the thing the adapter re-reads), never the admission dict.
    """
    tmp = tempfile.TemporaryDirectory(prefix="ig-inbox-proof-")
    case.addCleanup(tmp.cleanup)
    store = DurableStore(str(Path(tmp.name) / "inbox.sqlite"))
    case.addCleanup(store.close)
    admission = admit_instagram_event(store, event,
                                      account=account or make_account())
    assert admission["admitted"] is True, admission
    return store


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
                                          account=make_account(),
                                          own_actor_ids=own_actor_ids)
        return self.routes.record_customer_interaction(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key=thread_key, provider_event_id=provider_event_id,
            account=make_account(),
            event=event, admission=admission, inbox=self.store,
            own_actor_ids=own_actor_ids, now=now)


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
        first = admit_instagram_event(store, event, account=make_account())
        second = admit_instagram_event(store, event, account=make_account())
        self.assertTrue(first["admitted"])
        self.assertFalse(second["admitted"])
        self.assertEqual(second["reason"], "duplicate")

    def test_own_and_outgoing_events_are_excluded(self):
        store = self.store_for_test()
        own = make_dm_event(actor_id="ourselves")
        result = admit_instagram_event(store, own, account=make_account(),
                                       own_actor_ids=("ourselves",))
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "excluded:own_actor")

        outgoing = make_comment_event(provider_event_id="evt-out-1",
                                      direction="outbound")
        result = admit_instagram_event(store, outgoing, account=make_account())
        self.assertFalse(result["admitted"])
        self.assertIn("excluded:direction", result["reason"])

    def test_the_bound_account_actor_is_excluded_with_no_caller_list(self):
        # Defect 4, the whole class: ownership used to be a hand-kept id set,
        # so an unchanged caller admitted our OWN outbound activity as if it
        # were a customer's. The authoritative account record now supplies it.
        store = self.store_for_test()
        account = make_account()
        ours = make_dm_event(actor_id=account.ig_user_id)
        result = admit_instagram_event(store, ours, account=account)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "excluded:own_actor")

    def test_a_bare_string_own_actor_ids_is_refused_before_the_inbox(self):
        # A bare string was read as its own characters, so our own actor
        # "ourselves" was ADMITTED as if it were a customer.
        store = self.store_for_test()
        own = make_dm_event(actor_id="ourselves")
        for bare in ("ourselves", b"ourselves", bytearray(b"ourselves")):
            with self.assertRaises(InstagramRouteError) as caught:
                admit_instagram_event(store, own, account=make_account(),
                                      own_actor_ids=bare)
            self.assertIn("own_actor_ids", str(caught.exception), bare)
        # Nothing reached the inbox: the first real admission is not a
        # duplicate, and our own actor is still excluded.
        result = admit_instagram_event(store, own, account=make_account(),
                                       own_actor_ids=("ourselves",))
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "excluded:own_actor")

    def test_every_real_collection_of_own_actor_ids_is_still_accepted(self):
        for i, ids in enumerate((["ourselves"], {"ourselves"},
                                 frozenset({"ourselves"}),
                                 (a for a in ("ourselves",)))):
            store = self.store_for_test()
            own = make_dm_event(provider_event_id="own-%d" % i,
                                actor_id="ourselves")
            customer = make_dm_event(provider_event_id="cust-%d" % i)
            ids = list(ids)
            self.assertEqual(admit_instagram_event(
                store, own, account=make_account(),
                own_actor_ids=ids)["reason"], "excluded:own_actor")
            self.assertTrue(admit_instagram_event(
                store, customer, account=make_account(),
                own_actor_ids=ids)["admitted"])

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

    def test_a_grant_that_is_not_a_bool_is_refused_at_construction(self):
        # granted="false" was truthy, so a string grant authorised a send.
        for bad in ("false", "False", "no", "0", "true", 1, 0, [1], [],
                    None, 1.0):
            with self.assertRaises(InstagramRouteError) as caught:
                InstagramCapability(CAP_DM_SEND, granted=bad)
            self.assertIn("granted", str(caught.exception), repr(bad))

    def test_a_bool_grant_is_still_accepted_both_ways(self):
        dm = make_dm_event()
        inbox = admitted_inbox(self, dm)
        granted = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_AI_REPLY,
            channel=CHANNEL_IG_DM, event=dm, inbox=inbox,
            capability=InstagramCapability(CAP_DM_SEND, granted=True))
        self.assertTrue(granted.allowed)
        self.assertTrue(InstagramCapability(CAP_DM_SEND).granted is True)
        refused = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_AI_REPLY,
            channel=CHANNEL_IG_DM, event=dm, inbox=inbox,
            capability=InstagramCapability(CAP_DM_SEND, granted=False))
        self.assertFalse(refused.allowed)
        self.assertEqual(refused.reason, R_CAPABILITY_NOT_GRANTED)

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
        dm = make_dm_event()
        verdict = evaluate_eligibility(
            account=self.account, purpose=PURPOSE_AI_REPLY,
            channel=CHANNEL_IG_DM, event=dm, inbox=admitted_inbox(self, dm),
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
        # Defect 3: one public method, one return type on every path.
        self.assertIsInstance(first, OpenerState)
        self.assertIsInstance(second, OpenerState)
        self.assertEqual(second.opener_action_id, "act-opener-1")
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
                      thread_key="thread-1", account=make_account(),
                      now=20.0)
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
        admission = admit_instagram_event(self.store, outbound,
                                          account=make_account())
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
                                          account=make_account(),
                                          own_actor_ids=("ourselves",))
        self.assertFalse(admission["admitted"])
        self.assert_refused(provider_event_id="dm-own-1", event=own,
                            admission=admission, own_actor_ids=("ourselves",))
        self.follow_up_is_still_ignored()

    def test_a_bare_string_own_actor_ids_never_un_suppresses(self):
        # A bare "ourselves" degraded to single characters: our own DM was
        # admitted, accepted as proof, and the follow-up DM SENT.
        own = make_dm_event(provider_event_id="dm-own-bare-1",
                            thread_key="thread-1", actor_id="ourselves")
        with self.assertRaises(InstagramRouteError) as caught:
            admit_instagram_event(self.store, own, account=make_account(),
                                  own_actor_ids="ourselves")
        self.assertIn("own_actor_ids", str(caught.exception))
        # Even handed a genuine admission of that DM, the record refuses the
        # bare string rather than reading it as letters.
        admission = admit_instagram_event(self.store, own,
                                          account=make_account())
        self.assertTrue(admission["admitted"])
        for bare in ("ourselves", b"ourselves", bytearray(b"ourselves")):
            with self.assertRaises(InstagramRouteError) as caught:
                self.routes.record_customer_interaction(
                    tenant_id="tenant-1", account_id="ig-acct-1",
                    thread_key="thread-1", provider_event_id="dm-own-bare-1",
                    account=make_account(),
                    event=own, admission=admission, own_actor_ids=bare,
                    now=20.0)
            self.assertIn("own_actor_ids", str(caught.exception), bare)
        self.follow_up_is_still_ignored()
        # And the follow-up DM never reaches the sender.
        action_id = self.intent("bare-own-follow", purpose=PURPOSE_AI_REPLY)
        log = []
        outcome = dispatch_instagram_action(
            self.store, account=self.account, route_store=self.routes,
            action_id=action_id, worker_id="worker-1",
            purpose=PURPOSE_AI_REPLY, channel=CHANNEL_IG_DM,
            thread_key="thread-1", event=make_dm_event(thread_key="thread-1"),
            capability=InstagramCapability(CAP_DM_SEND),
            consent_evaluator=allow_consent, sender=self.sender(log),
            now=60.0)
        self.assertEqual(outcome.status, "blocked")
        self.assertEqual(log, [])

    def test_a_customer_dm_with_a_real_own_actor_list_still_releases(self):
        # The inverse: a list (not a bare string) of our ids is accepted, and
        # a genuine customer's DM still ends the ignored opener.
        self.assertTrue(self.record_dm("dm-list-1", now=20.0,
                                       own_actor_ids=["ourselves"]))
        state = self.routes.opener_state("tenant-1", "ig-acct-1", "thread-1")
        self.assertTrue(state.customer_responded)

    def test_the_admission_of_another_event_is_not_proof(self):
        event = make_dm_event(provider_event_id="dm-mismatch-1",
                              thread_key="thread-1")
        other = admit_instagram_event(
            self.store, make_dm_event(provider_event_id="dm-other-1",
                                      thread_key="thread-1"),
            account=make_account())
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
        first = admit_instagram_event(self.store, comment, account=account)
        second = admit_instagram_event(self.store, comment, account=account)
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
                account=account, now=4000.0)

        # 6. The customer answers and the inbox ADMITS the DM: that proof
        #    ends the ignored-opener state.
        reply = make_dm_event(provider_event_id="dm-reply-1",
                              thread_key=comment.thread_key)
        admission = admit_instagram_event(self.store, reply, account=account)
        self.assertTrue(admission["admitted"])
        self.assertTrue(self.routes.record_customer_interaction(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key=comment.thread_key, provider_event_id="dm-reply-1",
            account=account,
            event=reply, admission=admission, inbox=self.store, now=4000.0))
        retry_id = self.intent("trace-follow-2", purpose=PURPOSE_CAPTURE_REMINDER)
        sent = dispatch_instagram_action(
            self.store, account=account, route_store=self.routes,
            action_id=retry_id, worker_id="worker-1",
            purpose=PURPOSE_CAPTURE_REMINDER, channel=CHANNEL_IG_DM,
            thread_key=comment.thread_key, event=reply,
            capability=InstagramCapability(CAP_DM_SEND),
            consent_evaluator=allow_consent,
            sender=send, now=5000.0)
        self.assertEqual(sent.status, "sent")
        self.assertEqual(log, [opener_id, retry_id])
        evidence = json.loads(self.store.gate_checks(retry_id)[0]["evidence_json"])
        self.assertTrue(evidence["inbound_dm_window"])


class VerifiedInteractionGuardTests(_StoreCase):
    """Every refusal inside `_verified_inbound_interaction`, pinned one by one.

    PBB-319. The excluded-row guard (`decision_ref="excluded:..."`) had zero
    coverage: deleting it left the suite green at 69. A sweep of the whole
    module found the same hole on its siblings, because a later guard refused
    the same input for a different reason and hid the gap. Each test below
    therefore hands the validator ONE guard's shape at a time and asserts that
    guard's own message, so removing it cannot hide behind another refusal.
    """

    def setUp(self):
        super().setUp()
        self.routes.record_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", opener_action_id="act-opener", now=10.0)

    def record(self, **over):
        values = dict(tenant_id="tenant-1", account_id="ig-acct-1",
                      thread_key="thread-1", provider_event_id="evt-dm-1",
                      account=make_account(), now=20.0)
        values.update(over)
        return self.routes.record_customer_interaction(**values)

    def assert_refused_as(self, message, **over):
        with self.assertRaises(InstagramRouteError) as caught:
            self.record(**over)
        self.assertIn(R_UNVERIFIED_INTERACTION, str(caught.exception))
        self.assertIn(message, str(caught.exception))

    @staticmethod
    def inbox_row(provider_event_id="evt-dm-1", *, direction="inbound",
                  actor_id="customer-1", decision_ref=None,
                  tenant_id="tenant-1"):
        """The inbox's own row shape, handed to the adapter as its admission."""
        return {"admitted": True, "reason": "admitted",
                "row": {"provider_event_id": provider_event_id,
                        "tenant_id": tenant_id, "direction": direction,
                        "actor_id": actor_id, "decision_ref": decision_ref}}

    def test_the_event_must_describe_the_interaction_being_recorded(self):
        # Same event id, a different thread: the pair is not this interaction.
        other = make_dm_event(thread_key="thread-2")
        admission = admit_instagram_event(self.store, other,
                                          account=make_account())
        self.assert_refused_as("does not describe this interaction",
                               event=other, admission=admission)

    def test_an_outbound_event_is_never_proof(self):
        outbound = make_dm_event(direction="outbound")
        self.assert_refused_as("is not a customer's inbound message",
                               event=outbound, admission=self.inbox_row())

    def test_our_own_event_actor_is_never_proof(self):
        own = make_dm_event(actor_id="ourselves")
        admission = admit_instagram_event(self.store, own,
                                          account=make_account())
        self.assertTrue(admission["admitted"])
        self.assert_refused_as("is one of our own", event=own,
                               admission=admission,
                               own_actor_ids=("ourselves",))

    def test_an_admission_that_is_not_a_record_is_refused(self):
        self.assert_refused_as("no durable inbox admission was supplied",
                               event=make_dm_event(), admission=None)

    def test_an_inbox_that_did_not_admit_the_event_is_not_proof(self):
        admission = self.inbox_row()
        admission["admitted"] = False
        admission["reason"] = "not_admitted"
        self.assert_refused_as("the inbox did not admit this event",
                               event=make_dm_event(), admission=admission)

    def test_an_admission_without_a_row_is_refused(self):
        self.assert_refused_as(
            "carries no event row", event=make_dm_event(),
            admission={"admitted": True, "reason": "admitted", "row": None})

    def test_the_admission_must_name_this_very_event(self):
        # A real admission, for a different event id.
        other = admit_instagram_event(
            self.store, make_dm_event(provider_event_id="dm-other-row-1"),
            account=make_account())
        self.assert_refused_as("the admission belongs to another event",
                               event=make_dm_event(provider_event_id="dm-row-1"),
                               **{"provider_event_id": "dm-row-1"},
                               admission=other)

    def test_a_redelivered_outbound_row_is_never_proof(self):
        # A real duplicate: the inbox excluded the outbound row, then called
        # the redelivery "duplicate", which is the one reason that passes the
        # admitted/duplicate gate with an excluded row underneath it.
        outbound = make_dm_event(provider_event_id="dm-out-9",
                                 direction="outbound")
        admit_instagram_event(self.store, outbound, account=make_account())
        duplicate = admit_instagram_event(self.store, outbound,
                                          account=make_account())
        self.assertEqual(duplicate["reason"], "duplicate")
        self.assertEqual(duplicate["row"]["decision_ref"],
                         "excluded:direction=outbound")
        self.assert_refused_as("the inbox recorded direction",
                               event=make_dm_event(provider_event_id="dm-out-9"),
                               **{"provider_event_id": "dm-out-9"},
                               admission=duplicate)

    def test_a_redelivered_excluded_row_is_never_proof(self):
        # PBB-319 Defect 1. The excluded-row guard, pinned on a REAL duplicate
        # of a REAL excluded row. `own_actor_ids` is empty here, so the later
        # own-actor guard cannot stand in for it: only `decision_ref` refuses.
        own = make_dm_event(provider_event_id="dm-own-10", actor_id="ourselves")
        admit_instagram_event(self.store, own, account=make_account(),
                              own_actor_ids=("ourselves",))
        duplicate = admit_instagram_event(self.store, own,
                                          account=make_account(),
                                          own_actor_ids=("ourselves",))
        self.assertEqual(duplicate["reason"], "duplicate")
        self.assertEqual(duplicate["row"]["decision_ref"], "excluded:own_actor")
        self.assert_refused_as("the inbox excluded this event",
                               event=own, admission=duplicate,
                               **{"provider_event_id": "dm-own-10"})
        # Inverse: the excluded row never un-suppressed the thread.
        state = self.routes.opener_state("tenant-1", "ig-acct-1", "thread-1")
        self.assertFalse(state.customer_responded)

    def test_an_admission_row_recording_our_own_actor_is_not_proof(self):
        # The event is a customer's; the inbox row says the actor was ours.
        self.assert_refused_as(
            "the inbox recorded our own actor",
            event=make_dm_event(provider_event_id="dm-11"),
            **{"provider_event_id": "dm-11"},
            admission=self.inbox_row(provider_event_id="dm-11",
                                     actor_id="ourselves"),
            own_actor_ids=("ourselves",))

    def test_an_admitted_row_with_no_exclusion_still_ends_the_opener(self):
        # Inverse control: the guards above refuse shapes, not success. A real
        # admitted inbound customer DM still publishes its interaction.
        self.assertTrue(self.record_dm("dm-inverse-1", now=20.0))
        state = self.routes.opener_state("tenant-1", "ig-acct-1", "thread-1")
        self.assertTrue(state.customer_responded)


class OpenerConcurrencyTests(_StoreCase):
    """Defect 2 (PBB-259): one opener per thread must hold when workers RUN AT ONCE.

    The sequential path was already solid. Under concurrency eligibility is
    read-then-act: four workers each read "no opener" and all four sent. The
    thread's one opener slot is now claimed by ONE conditional write in the
    durable store, before dispatch.
    """

    def _race(self, count):
        account = make_account()
        comment = make_comment_event()
        filter_ = make_filter()
        action_ids = [self.intent("conc-%d" % i,
                                  purpose=PURPOSE_COMMENT_PRIVATE_OPENER)
                      for i in range(count)]
        barrier = threading.Barrier(count)
        # All workers that reach the gate wait for each other, so each one has
        # read "no opener" before any of them records one. Timing alone would
        # hide the race. A worker that never dispatches (a claim loser) lets
        # the others through on timeout.
        at_gate = threading.Barrier(count, timeout=2.0)
        log = []
        lock = threading.Lock()

        def consent(ctx):
            try:
                at_gate.wait()
            except threading.BrokenBarrierError:
                pass
            return allow_consent(ctx)

        def worker(action_id):
            store = DurableStore(self.db)
            routes = InstagramRouteStore(self.db)
            try:
                def send(ctx):
                    with lock:
                        log.append(ctx["action_id"])
                    return {"provider": "instagram",
                            "provider_receipt_id": "rcpt-" + ctx["action_id"]}
                barrier.wait()
                return dispatch_instagram_action(
                    store, account=account, route_store=routes,
                    action_id=action_id, worker_id="worker-" + action_id,
                    purpose=PURPOSE_COMMENT_PRIVATE_OPENER,
                    channel=CHANNEL_IG_DM, thread_key=comment.thread_key,
                    event=comment, filter_=filter_,
                    capability=InstagramCapability(CAP_COMMENT_PRIVATE_OPENER),
                    consent_evaluator=consent, sender=send, now=1000.0)
            finally:
                routes.close()
                store.close()

        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [pool.submit(worker, a) for a in action_ids]
            outcomes = [f.result() for f in futures]
        return outcomes, log, comment

    def test_four_concurrent_openers_produce_exactly_one_send(self):
        outcomes, log, comment = self._race(4)
        self.assertEqual(len(log), 1, [o.status for o in outcomes])
        self.assertEqual([o.status for o in outcomes].count("sent"), 1,
                         [o.status for o in outcomes])
        state = self.routes.opener_state("tenant-1", "ig-acct-1",
                                         comment.thread_key)
        self.assertIsNotNone(state)
        self.assertEqual(state.opener_action_id, log[0])

    def test_every_losing_worker_sends_nothing_and_leaves_no_opener(self):
        outcomes, log, comment = self._race(4)
        losers = [o for o in outcomes if o.status != "sent"]
        self.assertEqual(len(losers), 3, [o.status for o in outcomes])
        for outcome in losers:
            self.assertEqual(outcome.status, "refused_race_loss")
            self.assertNotIn(outcome.action_id, log)
            # Still queued: a later retry is re-evaluated, never dropped.
            self.assertIn(self.store.get_action(outcome.action_id)["state"],
                          ("queued", "suppressed"))
        state = self.routes.opener_state("tenant-1", "ig-acct-1",
                                         comment.thread_key)
        self.assertEqual(state.opener_action_id, log[0])

    def test_the_claim_is_refused_once_an_opener_row_exists(self):
        self.routes.record_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", opener_action_id="act-opener", now=10.0)
        self.assertFalse(self.routes.claim_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", claim_token="tok", action_id="act-2",
            now=20.0))

    def test_a_released_claim_can_be_taken_again(self):
        self.assertTrue(self.routes.claim_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", claim_token="tok-1", action_id="act-1",
            now=10.0))
        self.assertFalse(self.routes.claim_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", claim_token="tok-2", action_id="act-2",
            now=11.0))
        self.assertTrue(self.routes.release_opener_claim(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", claim_token="tok-1", now=12.0))
        self.assertTrue(self.routes.claim_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", claim_token="tok-2", action_id="act-2",
            now=13.0))

    def test_an_expired_claim_is_taken_over_by_a_live_worker(self):
        # A crashed worker must not wedge the thread forever.
        self.assertTrue(self.routes.claim_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", claim_token="dead", action_id="act-1",
            now=10.0, lease_seconds=5.0))
        self.assertFalse(self.routes.claim_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", claim_token="live", action_id="act-2",
            now=14.0, lease_seconds=5.0))
        self.assertTrue(self.routes.claim_opener(
            tenant_id="tenant-1", account_id="ig-acct-1",
            thread_key="thread-1", claim_token="live", action_id="act-2",
            now=16.0, lease_seconds=5.0))


class NormaliseEventTrustBoundaryTests(unittest.TestCase):
    """Defect 5 (PBB-259): provider payloads leave as OUR error class.

    A malformed payload used to escape normalise_event() as a raw ValueError
    (`float("abc")`), TypeError (`float([])`, `sorted()` on mixed key types)
    or AttributeError. A caller that catches InstagramRouteError saw none of
    them.
    """

    @staticmethod
    def payload(**over):
        values = dict(provider="instagram", provider_event_id="evt-1",
                      tenant_id="tenant-1", account_id="ig-acct-1",
                      kind=EVENT_COMMENT, direction="inbound",
                      actor_id="customer-1", text="x",
                      thread_key="comment-1", received_at=1000.0)
        values.update(over)
        return values

    def test_malformed_provider_payloads_raise_the_domain_error(self):
        def with_extra(*extra):
            raw = self.payload()
            for key, value in extra:
                raw[key] = value
            return raw

        cases = [
            ("non-numeric timestamp",
             dict(self.payload(), received_at="not-a-number")),
            ("list timestamp", dict(self.payload(), received_at=[1000.0])),
            ("mapping timestamp", dict(self.payload(), received_at={"t": 1})),
            ("mixed-type unknown keys", with_extra((1, "x"), ("zzz", "y"))),
        ]
        for label, raw in cases:
            with self.assertRaises(InstagramRouteError, msg=label) as caught:
                normalise_event(raw)
            self.assertIn("bad_input", str(caught.exception), label)

    def test_a_bool_is_not_a_timestamp(self):
        with self.assertRaises(InstagramRouteError):
            normalise_event(self.payload(received_at=True))

    def test_a_valid_payload_still_normalises(self):
        event = normalise_event(self.payload())
        self.assertEqual(event.kind, EVENT_COMMENT)
        self.assertEqual(event.received_at, 1000.0)


class EligibilityBasisTests(unittest.TestCase):
    """Defect 7 (PBB-259): the ALLOW record asserts only the basis supplied.

    Every ALLOW used to report BASIS_INBOUND_MESSAGE even when the caller
    offered CONSENT_RECORD or PLATFORM_ELIGIBILITY. The gate record therefore
    asserted evidence the caller never offered.
    """

    def test_a_comment_allow_reports_the_offered_basis(self):
        for basis in (BASIS_INBOUND_MESSAGE, BASIS_CONSENT_RECORD,
                      BASIS_PLATFORM_ELIGIBILITY):
            verdict = evaluate_eligibility(
                account=make_account(), purpose=PURPOSE_PUBLIC_REPLY,
                channel=CHANNEL_IG_PUBLIC, event=make_comment_event(),
                filter_=make_filter(),
                capability=InstagramCapability(CAP_COMMENT_PUBLIC_REPLY),
                basis=basis)
            self.assertTrue(verdict.allowed, basis)
            self.assertEqual(verdict.basis, basis, basis)
            self.assertEqual(verdict.refreshed_by, basis, basis)
            self.assertEqual(verdict.as_gate_evidence()["basis"], basis, basis)

    def test_a_comment_allow_never_claims_an_unoffered_inbound_message(self):
        verdict = evaluate_eligibility(
            account=make_account(), purpose=PURPOSE_PUBLIC_REPLY,
            channel=CHANNEL_IG_PUBLIC, event=make_comment_event(),
            filter_=make_filter(),
            capability=InstagramCapability(CAP_COMMENT_PUBLIC_REPLY),
            basis=BASIS_CONSENT_RECORD)
        self.assertTrue(verdict.allowed)
        self.assertNotEqual(verdict.basis, BASIS_INBOUND_MESSAGE)
        self.assertNotEqual(verdict.refreshed_by, BASIS_INBOUND_MESSAGE)

    def test_an_opener_allow_reports_the_offered_basis(self):
        verdict = evaluate_eligibility(
            account=make_account(), purpose=PURPOSE_COMMENT_PRIVATE_OPENER,
            channel=CHANNEL_IG_DM, event=make_comment_event(),
            filter_=make_filter(),
            capability=InstagramCapability(CAP_COMMENT_PRIVATE_OPENER),
            basis=BASIS_PLATFORM_ELIGIBILITY)
        self.assertTrue(verdict.allowed)
        self.assertEqual(verdict.basis, BASIS_PLATFORM_ELIGIBILITY)
        self.assertEqual(verdict.refreshed_by, BASIS_PLATFORM_ELIGIBILITY)

    def test_a_dm_allow_reports_the_offered_basis(self):
        dm = make_dm_event()
        verdict = evaluate_eligibility(
            account=make_account(), purpose=PURPOSE_AI_REPLY,
            channel=CHANNEL_IG_DM, event=dm, inbox=admitted_inbox(self, dm),
            capability=InstagramCapability(CAP_DM_SEND),
            basis=BASIS_CONSENT_RECORD)
        self.assertTrue(verdict.allowed)
        self.assertEqual(verdict.basis, BASIS_CONSENT_RECORD)
        self.assertEqual(verdict.refreshed_by, BASIS_CONSENT_RECORD)

    def test_a_comment_refusal_also_reports_the_offered_basis(self):
        verdict = evaluate_eligibility(
            account=make_account(), purpose=PURPOSE_PUBLIC_REPLY,
            channel=CHANNEL_IG_PUBLIC, event=make_comment_event(),
            filter_=make_filter(),
            capability=InstagramCapability(CAP_COMMENT_PUBLIC_REPLY,
                                           granted=False),
            basis=BASIS_PLATFORM_ELIGIBILITY)
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.basis, BASIS_PLATFORM_ELIGIBILITY)


class GuardCoverageTests(unittest.TestCase):
    """The remaining unpinned guards found by the PBB-319 sweep.

    One test per guard whose deletion left the 69-test suite green. Same rule
    as above: the assertion names the refusal, so a sibling guard that refuses
    the same input for another reason cannot mask the removal.
    """

    def route_store(self):
        tmp = tempfile.TemporaryDirectory(prefix="ig-t21-guard-")
        self.addCleanup(tmp.cleanup)
        store = InstagramRouteStore(str(Path(tmp.name) / "routes.sqlite"))
        self.addCleanup(store.close)
        return store

    def verdict(self, **over):
        values = dict(account=make_account(), purpose=PURPOSE_PUBLIC_REPLY,
                      channel=CHANNEL_IG_PUBLIC, event=make_comment_event(),
                      filter_=make_filter(),
                      capability=InstagramCapability(CAP_COMMENT_PUBLIC_REPLY))
        values.update(over)
        return evaluate_eligibility(**values)

    # ── constructor / normaliser input guards ────────────────────────────
    def test_an_event_platform_that_is_not_instagram_is_refused(self):
        with self.assertRaises(InstagramRouteError) as caught:
            InstagramEvent(provider="instagram", provider_event_id="e",
                           tenant_id="tenant-1", account_id="ig-acct-1",
                           kind=EVENT_COMMENT, direction="inbound",
                           actor_id="customer-1", text="hi",
                           thread_key="c1", received_at=1.0, platform="FB")
        self.assertIn(R_ACCOUNT_FB, str(caught.exception))

    def test_an_event_requires_its_identifiers(self):
        with self.assertRaises(InstagramRouteError) as caught:
            InstagramEvent(provider="instagram", provider_event_id="e",
                           tenant_id="tenant-1", account_id="ig-acct-1",
                           kind=EVENT_COMMENT, direction="inbound",
                           actor_id="", text="hi", thread_key="c1",
                           received_at=1.0)
        self.assertIn("actor_id", str(caught.exception))

    def test_an_event_direction_must_be_known(self):
        with self.assertRaises(InstagramRouteError) as caught:
            InstagramEvent(provider="instagram", provider_event_id="e",
                           tenant_id="tenant-1", account_id="ig-acct-1",
                           kind=EVENT_COMMENT, direction="sideways",
                           actor_id="customer-1", text="hi",
                           thread_key="c1", received_at=1.0)
        self.assertIn("direction", str(caught.exception))

    def test_an_event_text_must_be_a_string(self):
        with self.assertRaises(InstagramRouteError) as caught:
            InstagramEvent(provider="instagram", provider_event_id="e",
                           tenant_id="tenant-1", account_id="ig-acct-1",
                           kind=EVENT_COMMENT, direction="inbound",
                           actor_id="customer-1", text=123,
                           thread_key="c1", received_at=1.0)
        self.assertIn("text must be a string", str(caught.exception))

    def test_an_event_comment_id_must_be_an_id(self):
        with self.assertRaises(InstagramRouteError) as caught:
            InstagramEvent(provider="instagram", provider_event_id="e",
                           tenant_id="tenant-1", account_id="ig-acct-1",
                           kind=EVENT_COMMENT, direction="inbound",
                           actor_id="customer-1", text="hi",
                           thread_key="c1", received_at=1.0, comment_id="")
        self.assertIn("comment_id", str(caught.exception))

    def test_an_account_requires_its_identifiers(self):
        with self.assertRaises(InstagramRouteError) as caught:
            make_account(tenant_id="")
        self.assertIn("tenant_id", str(caught.exception))

    def test_a_capability_requires_its_name(self):
        with self.assertRaises(InstagramRouteError) as caught:
            InstagramCapability("")
        self.assertIn("name", str(caught.exception))

    def test_a_filter_match_mode_must_be_known(self):
        with self.assertRaises(InstagramRouteError) as caught:
            make_filter(match_mode="regex")
        self.assertIn("match_mode", str(caught.exception))

    def test_a_filter_keywords_must_be_a_tuple(self):
        with self.assertRaises(InstagramRouteError) as caught:
            make_filter(keywords=["billboard"])
        self.assertIn("keywords must be a tuple", str(caught.exception))

    def test_normalise_refuses_a_non_mapping(self):
        with self.assertRaises(InstagramRouteError) as caught:
            normalise_event(None)
        self.assertIn("event must be a dict", str(caught.exception))

    def test_resolve_refuses_a_foreign_account_entry(self):
        with self.assertRaises(InstagramRouteError) as caught:
            resolve_account([object()], account_id="ig-acct-1")
        self.assertIn("InstagramAccount", str(caught.exception))

    # ── eligibility guards ───────────────────────────────────────────────
    def test_eligibility_requires_an_instagram_account(self):
        with self.assertRaises(InstagramRouteError) as caught:
            self.verdict(account=object())
        self.assertIn("InstagramAccount", str(caught.exception))

    def test_an_unknown_basis_is_refused(self):
        with self.assertRaises(InstagramRouteError) as caught:
            self.verdict(basis="BOGUS_BASIS",
                         purpose=PURPOSE_AI_REPLY, channel=CHANNEL_IG_DM)
        self.assertIn("basis", str(caught.exception))

    def test_a_public_reply_purpose_on_the_dm_channel_is_refused(self):
        # `_route_for` refuses the pairing and eligibility denies it. Without
        # that guard the public-reply branch would ALLOW a DM-channel action.
        result = self.verdict(channel=CHANNEL_IG_DM)
        self.assertFalse(result.allowed)
        self.assertTrue(result.reason.startswith(R_CHANNEL_PURPOSE_MISMATCH),
                        result.reason)

    def test_a_comment_route_needs_a_comment_event(self):
        result = self.verdict(event=None)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, R_UNSUPPORTED_EVENT)

    def test_an_outbound_comment_event_is_not_a_comment_route(self):
        result = self.verdict(event=make_comment_event(direction="outbound"))
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, R_EVENT_WRONG_KIND)

    def test_a_comment_event_from_another_tenant_is_refused(self):
        result = self.verdict(event=make_comment_event(tenant_id="tenant-2"))
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, R_EVENT_ACCOUNT_MISMATCH)

    def test_a_comment_route_needs_a_filter(self):
        result = self.verdict(filter_=None)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, R_FILTER_NOT_MATCHED)

    # ── the inbound-DM window's own conjuncts ────────────────────────────
    def dm_verdict(self, **over):
        values = dict(account=make_account(), purpose=PURPOSE_AI_REPLY,
                      channel=CHANNEL_IG_DM,
                      capability=InstagramCapability(CAP_DM_SEND))
        values.update(over)
        return evaluate_eligibility(**values)

    def test_an_outbound_dm_never_opens_the_window(self):
        result = self.dm_verdict(event=make_dm_event(direction="outbound"))
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, R_NO_INBOUND_DM)

    def test_a_dm_on_another_account_never_opens_the_window(self):
        result = self.dm_verdict(event=make_dm_event(account_id="ig-acct-2"))
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, R_NO_INBOUND_DM)

    def test_a_dm_from_another_tenant_never_opens_the_window(self):
        result = self.dm_verdict(event=make_dm_event(tenant_id="tenant-2"))
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, R_NO_INBOUND_DM)

    # ── gate factory guards ──────────────────────────────────────────────
    def gate(self, **over):
        values = dict(account=make_account(), route_store=self.route_store(),
                      purpose=PURPOSE_AI_REPLY, channel=CHANNEL_IG_DM,
                      thread_key="thread-1")
        values.update(over)
        return make_gate_evaluator(**values)

    def test_the_gate_requires_an_instagram_account(self):
        with self.assertRaises(InstagramRouteError) as caught:
            self.gate(account=object())
        self.assertIn("InstagramAccount", str(caught.exception))

    def test_the_gate_requires_an_instagram_route_store(self):
        with self.assertRaises(InstagramRouteError) as caught:
            self.gate(route_store=object())
        self.assertIn("InstagramRouteStore", str(caught.exception))

    def test_the_gate_requires_a_callable_consent_evaluator(self):
        with self.assertRaises(InstagramRouteError) as caught:
            self.gate(consent_evaluator="not callable")
        self.assertIn("consent_evaluator", str(caught.exception))

    def test_the_gate_requires_a_thread_key(self):
        with self.assertRaises(InstagramRouteError) as caught:
            self.gate(thread_key="")
        self.assertIn("thread_key", str(caught.exception))

    def test_the_gate_refuses_a_channel_purpose_mismatch_at_construction(self):
        with self.assertRaises(InstagramRouteError) as caught:
            self.gate(purpose=PURPOSE_PUBLIC_REPLY, channel=CHANNEL_IG_DM)
        self.assertIn(R_CHANNEL_PURPOSE_MISMATCH, str(caught.exception))

    def test_a_supported_pairing_still_builds_a_gate(self):
        # Inverse control: the factory guards refuse bad pairings, not good ones.
        self.assertTrue(callable(self.gate()))


class DurableInboxProofTests(_StoreCase):
    """PBB-386 NEW-D1 / NEW-D2: the inbox ROW is the proof, never a dict.

    Both defects had one shape -- something the caller SAID stood in for
    something the durable store HOLDS. NEW-D1 let an `InstagramEvent` object
    authorise a direct send the inbox had never admitted; NEW-D2 let a
    hand-written `admission` dict release the ignored opener. Both are closed
    by the same rule, pinned here on both paths: the store is re-read, and a
    caller's dict is never authoritative.
    """

    def setUp(self):
        super().setUp()
        self.account = make_account()
        self.filter = make_filter()
        self.comment = make_comment_event()

    def inbox_rows(self):
        return self.store.counts()["inbox"]

    def send_ghost(self, event, *, thread="thread-ghost", store=None):
        action_id = self.intent("ghost-" + event.provider_event_id,
                                purpose=PURPOSE_AI_REPLY)
        log = []
        outcome = dispatch_instagram_action(
            store or self.store, account=self.account, route_store=self.routes,
            action_id=action_id, worker_id="worker-1", purpose=PURPOSE_AI_REPLY,
            channel=CHANNEL_IG_DM, thread_key=thread, event=event,
            capability=InstagramCapability(CAP_DM_SEND),
            consent_evaluator=allow_consent, sender=self.sender(log), now=2000.0)
        return outcome, log, action_id

    def test_a_direct_send_is_not_authorised_by_an_event_the_inbox_never_admitted(self):
        # NEW-D1. The durable store has never seen "ghost-dm-1".
        ghost = make_dm_event(provider_event_id="ghost-dm-1",
                              thread_key="thread-ghost")
        self.assertEqual(self.inbox_rows(), 0)
        outcome, log, action_id = self.send_ghost(ghost)
        self.assertNotEqual(outcome.status, "sent")
        self.assertEqual(log, [])
        self.assertEqual(self.inbox_rows(), 0)
        self.assertIn(self.store.get_action(action_id)["state"],
                      ("suppressed", "queued"))

    def test_the_same_object_on_the_record_path_is_still_refused(self):
        # The identical object must not be proof at dispatch and not-proof at
        # record: it is not proof anywhere.
        ghost = make_dm_event(provider_event_id="ghost-dm-1",
                              thread_key="thread-1")
        self.routes.record_opener(tenant_id="tenant-1", account_id="ig-acct-1",
                                  thread_key="thread-1",
                                  opener_action_id="opener-1", now=10.0)
        with self.assertRaises(InstagramRouteError) as caught:
            self.routes.record_customer_interaction(
                tenant_id="tenant-1", account_id="ig-acct-1",
                thread_key="thread-1", provider_event_id="ghost-dm-1",
                account=self.account, event=ghost, admission=None,
                inbox=self.store, now=30.0)
        self.assertIn(R_UNVERIFIED_INTERACTION, str(caught.exception))
        self.assertFalse(self.routes.opener_state(
            "tenant-1", "ig-acct-1", "thread-1").customer_responded)

    def test_an_admitted_dm_still_opens_the_window_and_sends(self):
        # Inverse: the fix narrows what counts as evidence, not what sends.
        reply = make_dm_event(provider_event_id="dm-window-1",
                              thread_key="thread-ghost")
        admission = admit_instagram_event(self.store, reply,
                                          account=self.account)
        self.assertTrue(admission["admitted"])
        outcome, log, action_id = self.send_ghost(reply)
        self.assertEqual(outcome.status, "sent")
        self.assertEqual(log, [action_id])
        self.assertEqual(self.inbox_rows(), 1)

    def test_a_hand_written_admission_dict_never_releases_the_ignored_opener(self):
        # NEW-D2. The dict is perfectly shaped and there is no row behind it.
        self.routes.record_opener(tenant_id="tenant-1", account_id="ig-acct-1",
                                  thread_key="thread-1",
                                  opener_action_id="opener-1", now=10.0)
        self.assertFalse(self.routes.opener_state(
            "tenant-1", "ig-acct-1", "thread-1").customer_responded)
        self.assertEqual(self.inbox_rows(), 0)
        forged = {"admitted": True, "reason": "admitted", "row": {
            "provider_event_id": "ghost-1", "tenant_id": "tenant-1",
            "account_id": "ig-acct-1", "thread_key": "thread-1",
            "direction": "inbound", "actor_id": "ghost-customer"}}
        with self.assertRaises(InstagramRouteError) as caught:
            self.routes.record_customer_interaction(
                tenant_id="tenant-1", account_id="ig-acct-1",
                thread_key="thread-1", provider_event_id="ghost-1",
                account=self.account,
                event=make_dm_event(provider_event_id="ghost-1"),
                admission=forged, inbox=self.store, now=20.0)
        self.assertIn("the durable inbox holds no row for this event",
                      str(caught.exception))
        self.assertFalse(self.routes.opener_state(
            "tenant-1", "ig-acct-1", "thread-1").customer_responded)

    def test_no_store_means_no_proof_at_all(self):
        # The record path cannot prove anything without the inbox to re-read,
        # even when the caller's dict is perfectly shaped.
        self.routes.record_opener(tenant_id="tenant-1", account_id="ig-acct-1",
                                  thread_key="thread-1",
                                  opener_action_id="opener-1", now=10.0)
        shaped = {"admitted": True, "reason": "admitted", "row": {
            "provider_event_id": "dm-nostore-1", "tenant_id": "tenant-1",
            "account_id": "ig-acct-1", "thread_key": "thread-1",
            "direction": "inbound", "actor_id": "customer-1"}}
        with self.assertRaises(InstagramRouteError) as caught:
            self.routes.record_customer_interaction(
                tenant_id="tenant-1", account_id="ig-acct-1",
                thread_key="thread-1", provider_event_id="dm-nostore-1",
                account=self.account,
                event=make_dm_event(provider_event_id="dm-nostore-1"),
                admission=shaped, now=30.0)
        self.assertIn("no durable inbox store was supplied",
                      str(caught.exception))
        self.assertFalse(self.routes.opener_state(
            "tenant-1", "ig-acct-1", "thread-1").customer_responded)

    def test_a_real_admitted_row_still_releases_the_opener(self):
        # Inverse: proof earns un-suppression, and only proof does.
        self.routes.record_opener(tenant_id="tenant-1", account_id="ig-acct-1",
                                  thread_key="thread-1",
                                  opener_action_id="opener-1", now=10.0)
        self.assertTrue(self.record_dm("dm-proof-1", now=20.0))
        self.assertTrue(self.routes.opener_state(
            "tenant-1", "ig-acct-1", "thread-1").customer_responded)

    def test_an_event_the_inbox_excluded_is_not_a_window_either(self):
        # The store is consulted for eligibility too, so an excluded row never
        # opens the DM window on the dispatch path.
        own = make_dm_event(provider_event_id="dm-own-window",
                            thread_key="thread-ghost", actor_id="ourselves")
        admission = admit_instagram_event(self.store, own,
                                          account=self.account,
                                          own_actor_ids=("ourselves",))
        self.assertEqual(admission["reason"], "excluded:own_actor")
        outcome, log, action_id = self.send_ghost(own)
        self.assertNotEqual(outcome.status, "sent")
        self.assertEqual(log, [])

class OwnActorInputClassTests(_StoreCase):
    """PBB-386 OWNERSHIP-CLASS: the whole input class, not the cited examples.

    `_extra_own_actor_ids` refused only a bare string and then iterated
    whatever else arrived, so `3`, `None`, `1.5` and `object()` each escaped
    as a raw `TypeError`, and a DICT's KEYS became the own-actor set -- which
    excluded a real customer as one of us. Each shape below is handed to the
    boundary and judged on the ERROR CLASS, so a future narrower patch that
    closes only the named examples still fails here.
    """

    BAD_VALUES = (("int", 3), ("NoneType", None), ("float", 1.5),
                  ("dict", {"customer-7": "x"}), ("set-of-int", {3}),
                  ("list-of-int", [3]), ("object", object()),
                  ("bool", True), ("generator", (i for i in (1,))))

    def test_every_non_collection_refuses_as_the_domain_error(self):
        for label, value in self.BAD_VALUES:
            with self.subTest(value=label):
                with self.assertRaises(InstagramRouteError) as caught:
                    admit_instagram_event(
                        self.store,
                        make_dm_event(provider_event_id="own-" + label),
                        account=make_account(), own_actor_ids=value)
                self.assertIn("own_actor_ids", str(caught.exception))
                self.assertIn("bad_input", str(caught.exception))

    def test_the_record_path_refuses_the_same_shapes_the_same_way(self):
        for label, value in self.BAD_VALUES:
            with self.subTest(value=label):
                with self.assertRaises(InstagramRouteError) as caught:
                    self.routes.record_customer_interaction(
                        tenant_id="tenant-1", account_id="ig-acct-1",
                        thread_key="thread-1", provider_event_id="rec-" + label,
                        account=make_account(), admission=None,
                        own_actor_ids=value, now=20.0)
                self.assertIn("own_actor_ids", str(caught.exception))

    def test_a_dict_never_makes_a_real_customer_look_like_our_own_actor(self):
        # The named hole: a dict's KEYS were read as the own-actor set, so a
        # real customer was excluded as one of us. Now the dict cannot enter.
        with self.assertRaises(InstagramRouteError) as caught:
            admit_instagram_event(
                self.store,
                make_dm_event(provider_event_id="own-dictkeys",
                              actor_id="customer-7"),
                account=make_account(), own_actor_ids={"customer-7": "x"})
        self.assertIn("own_actor_ids", str(caught.exception))
        # And a customer is never excluded as our own actor on any accepted
        # shape either: the exclusion set is the account's own id plus extras.
        result = admit_instagram_event(
            self.store,
            make_dm_event(provider_event_id="own-customer-7",
                          actor_id="customer-7"),
            account=make_account(), own_actor_ids=["someone-else"])
        self.assertEqual(result["reason"], "admitted")
        self.assertIsNone(result["row"]["decision_ref"])

    def test_the_accepted_shapes_still_add_ids(self):
        account = make_account()
        for label, value in (("list", ["someone-else"]),
                             ("tuple", ("someone-else",)),
                             ("set", {"someone-else"}),
                             ("frozenset", frozenset({"someone-else"}))):
            with self.subTest(value=label):
                result = admit_instagram_event(
                    self.store,
                    make_dm_event(provider_event_id="own-ok-" + label),
                    account=account, own_actor_ids=value)
                self.assertEqual(result["reason"], "admitted", label)

    def test_a_member_that_is_not_an_id_is_refused_not_coerced(self):
        # str(3) would invent the actor id "3"; that is not a fix.
        for label, member in (("int-member", 3), ("none-member", None),
                              ("empty-string", ""), ("blank-string", "  ")):
            with self.subTest(member=label):
                with self.assertRaises(InstagramRouteError) as caught:
                    admit_instagram_event(
                        self.store,
                        make_dm_event(provider_event_id="own-m-" + label),
                        account=make_account(), own_actor_ids=[member])
                self.assertIn("bad_input", str(caught.exception))

    def test_our_own_authoritative_id_is_still_always_excluded(self):
        account = make_account()
        result = admit_instagram_event(
            self.store,
            make_dm_event(provider_event_id="own-authoritative",
                          actor_id=account.ig_user_id),
            account=account)
        self.assertEqual(result["reason"], "excluded:own_actor")

class VersionBookkeepingTests(unittest.TestCase):
    """PBB-386 VERSION: the shipped marker is strictly above main and unique.

    The marker is compared remote-against-local by `check-updates.sh`, so a
    version at or below `origin/main`'s reads as "not newer" on every deployed
    box -- that is exactly the regression the PBB-364 review found (this
    branch shipped `v2.0.38` while `main` was at `v2.0.95`). These read
    `origin/main` itself and skip only when the checkout has no remote,
    exactly as the repo's own `BookkeepingTests` does.
    """

    @classmethod
    def setUpClass(cls):
        cls.git_ok = False
        try:
            probe = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "rev-parse", "--verify",
                 "origin/main"], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True)
        except OSError:
            return
        cls.git_ok = probe.returncode == 0

    def git(self, *argv):
        return subprocess.run(["git", "-C", str(REPO_ROOT)] + list(argv),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True)

    @staticmethod
    def marker():
        return (TOOLS_DIR.parent / "skill-version.txt").read_text(
            encoding="utf-8").strip()

    @staticmethod
    def number(text):
        return tuple(int(p) for p in text.lstrip("v").split("."))

    def test_the_shipped_version_is_strictly_above_main_s(self):
        if not self.git_ok:
            self.skipTest("no origin/main in this checkout to compare against")
        main = self.git("show",
                        "origin/main:38-conversational-ai-system/"
                        "skill-version.txt").stdout.strip()
        self.assertGreater(self.number(self.marker()), self.number(main),
                           "the shipped version must never be at or below main's")

    def test_the_shipped_version_is_not_already_on_main(self):
        # Bracketed token form: a bare number false-matches the presentations
        # skill's v22.0.3x..v22.0.8x as a substring.
        if not self.git_ok:
            self.skipTest("no origin/main in this checkout to compare against")
        token = self.marker().lstrip("v")
        for form in ("[%s]" % token, "v%s" % token):
            with self.subTest(form=form):
                found = self.git("grep", "--fixed-strings", form, "origin/main")
                self.assertEqual(found.stdout.strip(), "",
                                 "%s is already on origin/main" % form)

class OpenerClaimBoundTests(_StoreCase):
    """PBB-386 LEASE CEILING: the claim's bound is stated and it is real.

    A 1 s lease and a 2 s stall lets a second worker take the thread over and
    send a second opener. That is correct crash recovery, so the guarantee is
    a bounded one: one opener per thread FOR THE LIFE OF THE OPENER CLAIM.
    The tests below pin BOTH halves -- that the bound is held while the lease
    is alive, and that the sentence making the claim names the bound rather
    than asserting an absolute its own probe falsifies.
    """

    def test_the_default_claim_lease_is_the_documented_bound(self):
        self.assertEqual(DEFAULT_OPENER_CLAIM_S, 300.0)

    def test_the_no_second_opener_sentence_carries_its_bound(self):
        # A content assertion on our own module: an unqualified absolute is
        # falsified by the probe, so it must not be re-introduced.
        source = Path(route_adapter.__file__).read_text(encoding="utf-8")
        unqualified = [raw.strip() for raw in source.splitlines()
                       if "no second opener" in raw
                       and not re.search(r"(?i)\bleas(e|es|ed|ing)\b|"
                                         r"claim window|"
                                         r"for the life of the .{0,12}claim",
                                         raw)]
        self.assertEqual(unqualified, [])
        self.assertRegex(source, r"(?i)for the life of the .{0,12}claim")
        self.assertIn("DEFAULT_OPENER_CLAIM_S", source)

    def test_a_live_holder_inside_the_send_is_never_taken_over(self):
        # The bound is real, not decorative: while the lease is alive a second
        # worker is refused and calls the sender ZERO times.
        account = make_account()
        comment = make_comment_event()
        filter_ = make_filter()
        a_id = self.intent("bound-a", purpose=PURPOSE_COMMENT_PRIVATE_OPENER)
        b_id = self.intent("bound-b", purpose=PURPOSE_COMMENT_PRIVATE_OPENER)
        in_send = threading.Event()
        release = threading.Event()
        log = []
        lock = threading.Lock()

        def send_a(ctx):
            with lock:
                log.append(ctx["action_id"])
            in_send.set()
            release.wait(10.0)
            return {"provider": "instagram", "provider_receipt_id": "rcpt-a"}

        def run_a():
            store = DurableStore(self.db)
            routes = InstagramRouteStore(self.db)
            try:
                return dispatch_instagram_action(
                    store, account=account, route_store=routes, action_id=a_id,
                    worker_id="worker-a",
                    purpose=PURPOSE_COMMENT_PRIVATE_OPENER, channel=CHANNEL_IG_DM,
                    thread_key="thread-bound", event=comment, filter_=filter_,
                    capability=InstagramCapability(CAP_COMMENT_PRIVATE_OPENER),
                    consent_evaluator=allow_consent, sender=send_a, now=1000.0)
            finally:
                routes.close()
                store.close()

        thread = threading.Thread(target=run_a)
        thread.start()
        self.assertTrue(in_send.wait(10.0))
        try:
            outcome_b = dispatch_instagram_action(
                self.store, account=account, route_store=self.routes,
                action_id=b_id, worker_id="worker-b",
                purpose=PURPOSE_COMMENT_PRIVATE_OPENER, channel=CHANNEL_IG_DM,
                thread_key="thread-bound", event=comment, filter_=filter_,
                capability=InstagramCapability(CAP_COMMENT_PRIVATE_OPENER),
                consent_evaluator=allow_consent,
                sender=self.sender(log), now=1000.5)
        finally:
            release.set()
            thread.join(10.0)
        self.assertEqual(outcome_b.status, "refused_race_loss")
        self.assertEqual(log, [a_id])

    def test_a_holder_that_stalls_past_its_lease_may_be_taken_over(self):
        # The documented ceiling, pinned so nobody re-asserts the absolute.
        self.assertTrue(self.routes.claim_opener(
            tenant_id="tenant-1", account_id="ig-acct-1", thread_key="thread-1",
            claim_token="tok-dead", action_id="act-1", now=10.0,
            lease_seconds=1.0))
        self.assertFalse(self.routes.claim_opener(
            tenant_id="tenant-1", account_id="ig-acct-1", thread_key="thread-1",
            claim_token="tok-live", action_id="act-2", now=10.5,
            lease_seconds=1.0))
        self.assertTrue(self.routes.claim_opener(
            tenant_id="tenant-1", account_id="ig-acct-1", thread_key="thread-1",
            claim_token="tok-live", action_id="act-2", now=12.0,
            lease_seconds=1.0))

if __name__ == "__main__":
    unittest.main(verbosity=2)
