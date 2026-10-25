#!/usr/bin/env python3
"""Self-check for ordered post/reveal receipts and partial resume (PBB-119 T-25).

One test per acceptance clause, each with the refusal case and a control, so a
hollow pass is visible:

  TRUE PROVIDER RECEIPTS  only a provider post/comment object persisted through
                          the fenced outbox counts; a local-id echo, a blank id,
                          a wrong object kind, an unsupported status or a
                          comment with no receipted parent does not.
  APPROVED ORDER          manifest placement order and post-before-comments.
  RESUME MISSING ONLY     receipted items and possibly-sent effects are never
                          re-issued; a comment waits for its post receipt.
  NO ONE-MINUTE RULE      gaps of 0, 1, 5, 45, 59, 60, 61 and 240 seconds are all
                          accepted; only a comment before its post is refused.

Run: python3 -I shared-utils/receipts/test_publication_receipts.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import publication_receipts as receipts  # noqa: E402
from durable_store import DurableStore  # noqa: E402

TENANT = "tenant-alpha"
CYCLE = "cycle-2026-11"
MANIFEST_ID = "manifest-cycle-2026-11"
REVISION = "rev-a"
ACCOUNT = "acct-page-1"
BINDING = "bind-1"
CONTENT = "content-1"
# Each placement's approved slot; the contract guard compares it verbatim.
SCHEDULE = {
    "P-01": "2026-11-03T14:00:00Z",
    "P-02": "2026-11-10T14:00:00Z",
}


def _placement(placement_id, scheduled_at, status="APPROVED"):
    invalidated = status == "INVALIDATED"
    return {
        "placement_id": placement_id,
        "account_id": ACCOUNT,
        "account_binding_revision": BINDING,
        "channel": "FB_PUBLIC",
        "scheduled_at": scheduled_at,
        "timezone": "America/New_York",
        "content_revision": CONTENT,
        "cta_text": "Comment the keyword",
        "keyword": "PURPLE",
        "promised_item_version": "item-1",
        "bonus_asset_versions": ["bonus-1"],
        "conversation_policy_version": "policy-1",
        "allowed_spare_ids": [],
        "approval_status": status,
        "invalidated_at": "2026-10-24T09:00:00Z" if invalidated else None,
        "invalidated_reason": "owner withdrew the slot" if invalidated else None,
    }


def manifest(status="APPROVED", placements=None, revision=REVISION):
    placements = placements or [
        _placement("P-01", "2026-11-03T14:00:00Z"),
        _placement("P-02", "2026-11-10T14:00:00Z"),
    ]
    return {
        "schema_version": 1,
        "manifest_id": MANIFEST_ID,
        "tenant_id": TENANT,
        "campaign_cycle_id": CYCLE,
        "revision": revision,
        "status": status,
        "approved_by": "owner@example.test" if status != "DRAFT" else None,
        "approved_at": "2026-10-24T08:00:00Z" if status != "DRAFT" else None,
        "campaign_window": {"starts_on": "2026-11-01", "ends_on": "2026-11-30"},
        "placements": placements,
    }


def item(placement_id, purpose, n, suffix=None):
    suffix = suffix or purpose.lower().replace("_", "-")
    return {
        "action_id": "act-%s-%s-%d" % (placement_id, suffix, n),
        "logical_intent_key": "%s/%s/%s/%d" % (CYCLE, placement_id, suffix, n),
        "tenant_id": TENANT,
        "scope": "public_placement",
        "purpose": purpose,
        "placement_id": placement_id,
        "campaign_cycle_id": CYCLE,
        "approval_manifest_id": MANIFEST_ID,
        "approval_revision": REVISION,
        "account_id": ACCOUNT,
        "account_binding_revision": BINDING,
        "channel": "FB_PUBLIC",
        "scheduled_at": SCHEDULE.get(placement_id, "2026-11-03T14:00:00Z"),
        "timezone": "America/New_York",
        "content_revision": CONTENT,
        "cta_text": "Comment the keyword",
        "keyword": "PURPLE",
        "promised_item_version": "item-1",
        "bonus_asset_versions": ["bonus-1"],
        "conversation_policy_version": "policy-1",
        "allowed_spare_ids": [],
    }


def post_receipt(object_id="fb-post-900", **over):
    receipt = {
        "provider": "facebook",
        "provider_object_id": object_id,
        "kind": "post",
        "supported_status": "sent",
        "recorded_at": 1000.0,
    }
    receipt.update(over)
    return receipt


def comment_receipt(object_id="fb-comment-901", parent="fb-post-900", **over):
    receipt = {
        "provider": "facebook",
        "provider_object_id": object_id,
        "kind": "comment",
        "supported_status": "sent",
        "parent_provider_object_id": parent,
        "recorded_at": 1005.0,
    }
    receipt.update(over)
    return receipt


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pbb119-receipts-"))
        self.store = DurableStore(str(self.tmp / "store.sqlite"))
        self.manifest = manifest()
        self.manifest_path = str(self.tmp / "manifest.json")
        (self.tmp / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- durable helpers ---------------------------------------------------
    def admit(self, entry):
        row, _created = self.store.create_intent(
            logical_intent_key=entry["logical_intent_key"],
            idempotency_key=entry["logical_intent_key"] + ":idem",
            tenant_id=TENANT,
            scope="public_placement",
            purpose=entry["purpose"],
            content_sha256="content-sha-" + entry["logical_intent_key"],
        )
        return row

    def publish(self, entry, receipt, now=1000.0):
        row = self.admit(entry)
        self.store.queue(row["action_id"], now=now)
        claim = self.store.claim_for_dispatch(row["action_id"], "worker-1", now=now)
        self.assertIsNotNone(claim, "the test needs a dispatch lease")
        self.assertTrue(self.store.begin_attempt(row["action_id"], claim["fence"], "worker-1", now=now))
        return self.store.record_dispatch(row["action_id"], claim["fence"], receipt, now=now)

    def mark_unknown(self, entry, now=1000.0):
        row = self.admit(entry)
        self.store.queue(row["action_id"], now=now)
        claim = self.store.claim_for_dispatch(row["action_id"], "worker-1", now=now)
        self.assertTrue(self.store.begin_attempt(row["action_id"], claim["fence"], "worker-1", now=now))
        return self.store.mark_attempt_unknown(row["action_id"], claim["fence"], "no_verdict", now=now)

    def plan(self, items, manifest=None, path=None):
        return receipts.resume_plan(
            self.store,
            manifest if manifest is not None else self.manifest,
            items,
            path or self.manifest_path,
        )


ORDER_ITEMS = [
    item("P-02", "SCHEDULED_POST", 1, "post"),
    item("P-01", "REVEAL_COMMENT", 1, "reveal"),
    item("P-01", "SCHEDULED_POST", 1, "post"),
    item("P-02", "REVEAL_COMMENT", 1, "reveal"),
]


class ApprovedOrderTests(Base):
    def test_the_approved_order_follows_the_manifest_placement_order(self):
        ordered = receipts.approved_order(self.manifest, ORDER_ITEMS, self.manifest_path)
        keys = [e["key"] for e in ordered["order"]]
        self.assertEqual(
            keys,
            [
                item("P-01", "SCHEDULED_POST", 1, "post")["logical_intent_key"],
                item("P-01", "REVEAL_COMMENT", 1, "reveal")["logical_intent_key"],
                item("P-02", "SCHEDULED_POST", 1, "post")["logical_intent_key"],
                item("P-02", "REVEAL_COMMENT", 1, "reveal")["logical_intent_key"],
            ],
            "input order is not the authority: the approved manifest placement order is",
        )
        self.assertEqual(ordered["errors"], [], "a well-formed plan has no structural error")

    def test_an_unordered_list_is_normalised_to_post_first(self):
        unordered = [
            item("P-01", "REVEAL_COMMENT", 2, "reveal-b"),
            item("P-01", "REVEAL_COMMENT", 1, "reveal-a"),
            item("P-01", "SCHEDULED_POST", 1, "post"),
        ]
        ordered = receipts.approved_order(self.manifest, unordered, self.manifest_path)
        self.assertEqual(ordered["errors"], [])
        self.assertEqual(
            [e["key"] for e in ordered["order"]],
            [
                item("P-01", "SCHEDULED_POST", 1, "post")["logical_intent_key"],
                item("P-01", "REVEAL_COMMENT", 2, "reveal-b")["logical_intent_key"],
                item("P-01", "REVEAL_COMMENT", 1, "reveal-a")["logical_intent_key"],
            ],
            "the post is first; the caller's comment order is the approved content order",
        )

    def test_two_posts_in_one_placement_are_refused(self):
        bad = [
            item("P-01", "SCHEDULED_POST", 1, "post"),
            item("P-01", "SCHEDULED_POST", 2, "post-b"),
        ]
        plan = self.plan(bad)
        self.assertIn("$.order: placement 'P-01' has more than one scheduled post", plan["errors"])

    def test_comments_without_a_post_are_refused(self):
        bad = [item("P-01", "REVEAL_COMMENT", 1, "reveal")]
        plan = self.plan(bad)
        self.assertIn(
            "$.order: placement 'P-01' has comments but no scheduled post", plan["errors"]
        )

    def test_a_duplicate_item_is_refused(self):
        dup = item("P-01", "SCHEDULED_POST", 1, "post")
        with self.assertRaises(receipts.ReceiptError) as ctx:
            receipts.approved_order(self.manifest, [dup, dict(dup)], self.manifest_path)
        self.assertIn("duplicate item", str(ctx.exception))

    def test_an_unknown_placement_is_refused(self):
        stray = item("P-99", "SCHEDULED_POST", 1, "post")
        with self.assertRaises(receipts.ReceiptError) as ctx:
            receipts.approved_order(self.manifest, [stray], self.manifest_path)
        self.assertIn("is not in the approved manifest", str(ctx.exception))

    def test_a_draft_manifest_cannot_be_planned(self):
        with self.assertRaises(receipts.ReceiptError) as ctx:
            receipts.approved_order(manifest(status="DRAFT"), ORDER_ITEMS, self.manifest_path)
        self.assertIn("nothing may be published", str(ctx.exception))

    def test_an_invalidated_placement_is_never_resumed(self):
        partial = manifest(
            status="PARTIAL_INVALIDATED",
            placements=[
                _placement("P-01", "2026-11-03T14:00:00Z"),
                _placement("P-02", "2026-11-10T14:00:00Z", status="INVALIDATED"),
            ],
        )
        path = str(self.tmp / "partial.json")
        (self.tmp / "partial.json").write_text(json.dumps(partial), encoding="utf-8")
        self.admit(item("P-01", "SCHEDULED_POST", 1, "post"))
        self.admit(item("P-01", "REVEAL_COMMENT", 1, "reveal"))
        self.admit(item("P-02", "SCHEDULED_POST", 1, "post"))
        self.admit(item("P-02", "REVEAL_COMMENT", 1, "reveal"))
        plan = self.plan(ORDER_ITEMS, manifest=partial, path=path)
        self.assertTrue(plan["ok"], "an invalidated sibling is not a structural error")
        self.assertEqual(
            plan["resume"],
            [item("P-01", "SCHEDULED_POST", 1, "post")["logical_intent_key"]],
            "the approved placement continues; the invalidated one is never published",
        )
        self.assertEqual(
            plan["blocked"],
            [
                {
                    "item": item("P-01", "REVEAL_COMMENT", 1, "reveal")["logical_intent_key"],
                    "reason": "PARENT_POST_NOT_RECEIPTED",
                }
            ],
            "the approved reveal waits for the approved post receipt",
        )
        self.assertEqual(
            sorted(u["item"] for u in plan["unapproved"]),
            sorted(
                [
                    item("P-02", "SCHEDULED_POST", 1, "post")["logical_intent_key"],
                    item("P-02", "REVEAL_COMMENT", 1, "reveal")["logical_intent_key"],
                ]
            ),
        )
        self.assertIn("placement approval is 'INVALIDATED'", plan["unapproved"][0]["errors"][0])


class TrueReceiptTests(Base):
    def test_a_persisted_provider_post_receipt_is_true(self):
        entry = item("P-01", "SCHEDULED_POST", 1, "post")
        self.publish(entry, post_receipt())
        found = receipts.true_receipt(self.store, entry)
        self.assertIsNotNone(found, "a fenced provider receipt is publication evidence")
        self.assertEqual(found["provider_object_id"], "fb-post-900")
        self.assertEqual(receipts.validate_provider_receipt(entry, found), [])

    def test_a_receipt_that_was_never_persisted_does_not_count(self):
        entry = item("P-01", "SCHEDULED_POST", 1, "post")
        self.admit(entry)
        self.assertIsNone(receipts.true_receipt(self.store, entry))
        plan = self.plan([entry])
        self.assertEqual(plan["resume"], [entry["logical_intent_key"]])

    def test_a_receipt_echoing_the_local_action_id_is_not_a_provider_receipt(self):
        entry = item("P-01", "SCHEDULED_POST", 1, "post")
        echo = post_receipt(object_id=entry["action_id"])
        self.publish(entry, echo)
        errors = receipts.validate_provider_receipt(entry, echo)
        self.assertEqual(len(errors), 1)
        self.assertIn("echoes the local action_id", errors[0])
        self.assertIsNone(
            receipts.true_receipt(self.store, entry),
            "a local id persisted as a provider object is still not a provider receipt",
        )
        plan = self.plan([entry])
        self.assertEqual(plan["resume"], [], "the possibly-sent effect is not republished")
        self.assertEqual(
            plan["blocked"],
            [{"item": entry["logical_intent_key"], "reason": "EFFECT_WITHOUT_TRUE_RECEIPT"}],
        )

    def test_a_decorated_local_id_echo_is_not_a_provider_receipt(self):
        # The echo defence compares identities, not spellings: a local id padded
        # with a space or a format mark is still the local id.
        entry = item("P-01", "SCHEDULED_POST", 1, "post")
        entry["idempotency_key"] = "idem-P-01-post-1"
        for field in receipts.LOCAL_ID_FIELDS:
            local = entry[field]
            for decorated in (" " + local + " ", "​" + local, local + "﻿"):
                errors = receipts.validate_provider_receipt(
                    entry, post_receipt(object_id=decorated)
                )
                self.assertTrue(
                    any("echoes the local %s" % field in e for e in errors),
                    "a decorated echo of %s must refuse, got %r" % (field, errors),
                )
        reversed_entry = dict(entry)
        reversed_entry["action_id"] = " " + entry["action_id"] + " "
        self.assertTrue(
            any(
                "echoes the local action_id" in e
                for e in receipts.validate_provider_receipt(
                    reversed_entry, post_receipt(object_id=entry["action_id"])
                )
            ),
            "decoration on the local field must not hide the echo either",
        )

        echo = post_receipt(object_id=" " + entry["action_id"] + " ")
        self.publish(entry, echo)
        self.assertIsNone(
            receipts.true_receipt(self.store, entry),
            "a padded local id persisted as a provider object is still not a receipt",
        )
        self.assertEqual(
            receipts.validate_provider_receipt(entry, post_receipt(object_id="fb-post-7")), [],
            "control: a real provider id is still accepted",
        )

    def test_a_blank_provider_object_id_is_not_a_receipt(self):
        entry = item("P-01", "SCHEDULED_POST", 1, "post")
        for blank in ("", "   ", "​", "﻿", "​ ﻿　\t "):
            errors = receipts.validate_provider_receipt(entry, post_receipt(object_id=blank))
            self.assertTrue(
                any("provider_object_id" in e for e in errors),
                "blank object id %r must refuse, got %r" % (blank, errors),
            )
        self.assertEqual(
            receipts.validate_provider_receipt(entry, post_receipt(object_id="fb-post-1")), [],
            "control: a real provider id is still accepted",
        )

    def test_a_comment_receipt_must_name_the_receipted_post(self):
        parent = item("P-01", "SCHEDULED_POST", 1, "post")
        comment = item("P-01", "REVEAL_COMMENT", 1, "reveal")
        other = item("P-01", "REVEAL_COMMENT", 2, "reveal-b")
        self.publish(parent, post_receipt())
        self.publish(comment, comment_receipt(parent="fb-post-900"))
        self.assertIsNotNone(
            receipts.true_receipt(self.store, comment, expected_parent="fb-post-900")
        )

        wrong = comment_receipt(object_id="fb-comment-902", parent="fb-post-OTHER")
        errors = receipts.validate_provider_receipt(comment, wrong, expected_parent="fb-post-900")
        self.assertTrue(any("is not the receipted post" in e for e in errors), errors)

        self.publish(other, wrong)
        self.assertIsNone(
            receipts.true_receipt(self.store, other, expected_parent="fb-post-900"),
            "a comment persisted under another post is not this post's reveal",
        )
        plan = self.plan([parent, comment, other])
        self.assertEqual(plan["resume"], [], "an already-dispatch effect is not replayed")
        self.assertEqual(
            plan["blocked"],
            [{"item": other["logical_intent_key"], "reason": "EFFECT_WITHOUT_TRUE_RECEIPT"}],
        )

    def test_a_comment_receipt_without_a_parent_is_not_a_receipt(self):
        comment = item("P-01", "REVEAL_COMMENT", 1, "reveal")
        no_parent = comment_receipt()
        del no_parent["parent_provider_object_id"]
        errors = receipts.validate_provider_receipt(comment, no_parent)
        self.assertTrue(any("names the post it was published under" in e for e in errors))
        self.assertEqual(
            receipts.validate_provider_receipt(comment, comment_receipt()),
            [],
            "control: a comment receipt carrying its parent post is accepted",
        )

    def test_the_parent_compare_is_by_identity_not_spelling(self):
        # N1: a padded real provider id is a true receipt, so the parent compare
        # must use the same normaliser the echo compare uses, in both directions.
        comment = item("P-01", "REVEAL_COMMENT", 1, "reveal")
        for parent, expected in (
            ("fb-post-900", " fb-post-900 "),
            (" fb-post-900 ", "fb-post-900"),
            ("​fb-post-900", "fb-post-900﻿"),
        ):
            self.assertEqual(
                receipts.validate_provider_receipt(
                    comment, comment_receipt(parent=parent), expected_parent=expected
                ),
                [],
                "parent %r is the receipted post %r" % (parent, expected),
            )
        errors = receipts.validate_provider_receipt(
            comment, comment_receipt(parent=" fb-post-OTHER "), expected_parent=" fb-post-900 "
        )
        self.assertTrue(
            any("is not the receipted post" in e for e in errors),
            "control: a different post is still refused, got %r" % (errors,),
        )

    def test_a_local_id_echoed_as_the_parent_is_not_a_receipt(self):
        # N2: the parent field is a provider id too; a local id echoed into it,
        # decorated or not, is not the post the comment was published under.
        comment = item("P-01", "REVEAL_COMMENT", 1, "reveal")
        comment["idempotency_key"] = "idem-P-01-reveal-1"
        for field in receipts.LOCAL_ID_FIELDS:
            local = comment[field]
            for echo in (local, " " + local + " ", "​" + local):
                errors = receipts.validate_provider_receipt(comment, comment_receipt(parent=echo))
                self.assertTrue(
                    any(
                        "$.parent_provider_object_id" in e and "echoes the local %s" % field in e
                        for e in errors
                    ),
                    "a parent echoing %s as %r must refuse, got %r" % (field, echo, errors),
                )
        for not_a_string in (900, ["fb-post-900"], {"id": "fb-post-900"}):
            errors = receipts.validate_provider_receipt(
                comment, comment_receipt(parent=not_a_string)
            )
            self.assertTrue(
                any("$.parent_provider_object_id: must be a string" in e for e in errors),
                "a non-string parent %r must refuse, got %r" % (not_a_string, errors),
            )

        self.publish(comment, comment_receipt(parent=comment["action_id"]))
        self.assertIsNone(
            receipts.true_receipt(self.store, comment),
            "a comment whose parent echoes a local id is not publication evidence",
        )
        self.assertEqual(
            receipts.validate_provider_receipt(comment, comment_receipt(parent="fb-post-900")),
            [],
            "control: a real provider parent id is still accepted",
        )

    def test_a_non_publication_status_is_not_a_receipt(self):
        entry = item("P-01", "SCHEDULED_POST", 1, "post")
        for status in ("unknown", "failed_not_sent", "suppressed", None):
            errors = receipts.validate_provider_receipt(
                entry, post_receipt(supported_status=status)
            )
            self.assertTrue(
                any("is not publication evidence" in e for e in errors),
                "status %r must not count as publication, got %r" % (status, errors),
            )
        for status in receipts.PUBLISHED_STATUSES:
            self.assertEqual(
                receipts.validate_provider_receipt(entry, post_receipt(supported_status=status)),
                [],
                "control: published status %r is accepted" % (status,),
            )

    def test_a_comment_shaped_receipt_for_a_post_is_refused(self):
        entry = item("P-01", "SCHEDULED_POST", 1, "post")
        errors = receipts.validate_provider_receipt(entry, comment_receipt())
        self.assertTrue(
            any("a SCHEDULED_POST receipt is a post object" in e for e in errors), errors
        )


class ResumeTests(Base):
    def test_resume_returns_only_missing_items_in_approved_order(self):
        p1_post = item("P-01", "SCHEDULED_POST", 1, "post")
        p1_reveal = item("P-01", "REVEAL_COMMENT", 1, "reveal")
        p2_post = item("P-02", "SCHEDULED_POST", 1, "post")
        p2_reveal = item("P-02", "REVEAL_COMMENT", 1, "reveal")
        self.publish(p1_post, post_receipt())
        self.admit(p1_reveal)
        self.admit(p2_post)
        self.admit(p2_reveal)

        plan = self.plan(ORDER_ITEMS)
        self.assertEqual(plan["already_received"], [p1_post["logical_intent_key"]])
        self.assertEqual(
            plan["resume"],
            [p1_reveal["logical_intent_key"], p2_post["logical_intent_key"]],
            "approved order, missing only",
        )
        self.assertEqual(
            plan["blocked"],
            [{"item": p2_reveal["logical_intent_key"], "reason": "PARENT_POST_NOT_RECEIPTED"}],
            "P-02's reveal waits for P-02's post receipt",
        )

    def test_a_missing_comment_waits_for_its_post_receipt(self):
        p1_post = item("P-01", "SCHEDULED_POST", 1, "post")
        p1_reveal = item("P-01", "REVEAL_COMMENT", 1, "reveal")
        self.admit(p1_post)
        self.admit(p1_reveal)
        plan = self.plan([p1_post, p1_reveal])
        self.assertEqual(plan["resume"], [p1_post["logical_intent_key"]])
        self.assertEqual(
            plan["blocked"],
            [{"item": p1_reveal["logical_intent_key"], "reason": "PARENT_POST_NOT_RECEIPTED"}],
        )

    def test_resume_never_reissues_a_receipted_comment(self):
        p1_post = item("P-01", "SCHEDULED_POST", 1, "post")
        p1_reveal = item("P-01", "REVEAL_COMMENT", 1, "reveal")
        self.publish(p1_post, post_receipt())
        self.publish(p1_reveal, comment_receipt())
        plan = self.plan([p1_post, p1_reveal])
        self.assertEqual(plan["resume"], [])
        self.assertEqual(
            plan["already_received"],
            [p1_post["logical_intent_key"], p1_reveal["logical_intent_key"]],
        )

    def test_resume_is_stable_across_repeated_calls(self):
        p1_post = item("P-01", "SCHEDULED_POST", 1, "post")
        p1_reveal = item("P-01", "REVEAL_COMMENT", 1, "reveal")
        self.admit(p1_reveal)
        first = self.plan([p1_post, p1_reveal])
        second = self.plan([p1_post, p1_reveal])
        self.assertEqual(first, second, "resume is a plan, not a consume-once token")

    def test_resume_after_publishing_the_missing_comment(self):
        p1_post = item("P-01", "SCHEDULED_POST", 1, "post")
        p1_reveal = item("P-01", "REVEAL_COMMENT", 1, "reveal")
        self.publish(p1_post, post_receipt())
        self.publish(p1_reveal, comment_receipt())
        self.admit(p1_post)
        first = self.plan([p1_post, p1_reveal])
        self.assertEqual(first["resume"], [], "coverage control: nothing is missing here")

        extra = item("P-01", "BONUS_COMMENT", 1, "bonus")
        self.admit(extra)
        pending = self.plan([p1_post, p1_reveal, extra])
        self.assertEqual(pending["resume"], [extra["logical_intent_key"]])

        receipt = comment_receipt(object_id="fb-comment-777")
        row = self.store.action_by_intent(extra["logical_intent_key"])
        self.store.queue(row["action_id"], now=1010.0)
        claim = self.store.claim_for_dispatch(row["action_id"], "worker-2", now=1010.0)
        self.assertIsNotNone(claim)
        self.assertTrue(self.store.begin_attempt(row["action_id"], claim["fence"], "worker-2", now=1010.0))
        self.store.record_dispatch(row["action_id"], claim["fence"], receipt, now=1010.0)

        after = self.plan([p1_post, p1_reveal, extra])
        self.assertEqual(after["resume"], [], "the published comment is not resumed again")
        self.assertIn(extra["logical_intent_key"], after["already_received"])

    def test_an_in_flight_attempt_is_never_resumed(self):
        entry = item("P-01", "SCHEDULED_POST", 1, "post")
        row = self.admit(entry)
        self.assertEqual(
            self.plan([entry])["resume"],
            [entry["logical_intent_key"]],
            "control: an admitted item with no attempt is resumable",
        )

        self.store.queue(row["action_id"], now=1000.0)
        claim = self.store.claim_for_dispatch(row["action_id"], "worker-1", now=1000.0)
        self.assertIsNotNone(claim)
        self.assertTrue(
            self.store.begin_attempt(row["action_id"], claim["fence"], "worker-1", now=1000.0)
        )
        self.assertIsNotNone(
            self.store.unresolved_attempt(row["action_id"]), "the fixture needs an open attempt"
        )
        plan = self.plan([entry])
        self.assertEqual(plan["resume"], [], "a possibly-sent effect is never re-issued")
        self.assertEqual(
            plan["blocked"],
            [{"item": entry["logical_intent_key"], "reason": "ATTEMPT_IN_FLIGHT"}],
        )

        # Once reconciled with a true provider receipt it is received, not resumed.
        self.store.record_dispatch(row["action_id"], claim["fence"], post_receipt(), now=1001.0)
        after = self.plan([entry])
        self.assertEqual(after["resume"], [])
        self.assertEqual(after["already_received"], [entry["logical_intent_key"]])

    def test_a_padded_post_receipt_still_serves_its_missing_comment(self):
        # N1 end to end: the post is a true receipt with a padded provider id;
        # its comment must not be blocked forever by a spelling difference.
        p1_post = item("P-01", "SCHEDULED_POST", 1, "post")
        p1_reveal = item("P-01", "REVEAL_COMMENT", 1, "reveal")
        p1_bonus = item("P-01", "BONUS_COMMENT", 1, "bonus")
        self.publish(p1_post, post_receipt(object_id=" fb-post-900 "))
        self.publish(p1_reveal, comment_receipt(parent="fb-post-900"))
        self.admit(p1_bonus)
        plan = self.plan([p1_post, p1_reveal, p1_bonus])
        self.assertEqual(
            plan["already_received"],
            [p1_post["logical_intent_key"], p1_reveal["logical_intent_key"]],
            "the comment published under the padded post id is received",
        )
        self.assertEqual(plan["resume"], [p1_bonus["logical_intent_key"]], "missing only")
        self.assertEqual(plan["blocked"], [])

        other = item("P-02", "SCHEDULED_POST", 1, "post")
        other_reveal = item("P-02", "REVEAL_COMMENT", 1, "reveal")
        self.publish(other, post_receipt(object_id="fb-post-950"))
        self.publish(other_reveal, comment_receipt(object_id="fb-comment-951", parent=" fb-post-900 "))
        control = self.plan([other, other_reveal])
        self.assertEqual(
            control["blocked"],
            [{"item": other_reveal["logical_intent_key"], "reason": "EFFECT_WITHOUT_TRUE_RECEIPT"}],
            "control: a comment under a different post is still not this post's reveal",
        )

    def test_resume_excludes_a_possibly_sent_effect(self):
        entry = item("P-01", "SCHEDULED_POST", 1, "post")
        self.mark_unknown(entry)
        plan = self.plan([entry])
        self.assertEqual(plan["resume"], [], "an unknown effect is never replayed")
        self.assertEqual(plan["blocked"], [{"item": entry["logical_intent_key"], "reason": "STATE_UNKNOWN"}])

    def test_a_dispatched_effect_without_a_true_receipt_is_reconciled_not_resumed(self):
        entry = item("P-01", "SCHEDULED_POST", 1, "post")
        self.publish(entry, post_receipt(object_id=entry["action_id"]))
        plan = self.plan([entry])
        self.assertEqual(plan["resume"], [])
        self.assertEqual(
            plan["blocked"],
            [{"item": entry["logical_intent_key"], "reason": "EFFECT_WITHOUT_TRUE_RECEIPT"}],
        )

    def test_resume_excludes_a_never_admitted_item(self):
        entry = item("P-01", "SCHEDULED_POST", 1, "post")
        plan = self.plan([entry])
        self.assertEqual(plan["resume"], [])
        self.assertEqual(plan["blocked"], [{"item": entry["logical_intent_key"], "reason": "NOT_ADMITTED"}])

    def test_a_suppressed_item_is_not_resumed(self):
        entry = item("P-01", "SCHEDULED_POST", 1, "post")
        row = self.admit(entry)
        self.store.queue(row["action_id"])
        self.store.apply_gate_block(row["action_id"], "suppressed", "PUBLICATION_PAUSED")
        plan = self.plan([entry])
        self.assertEqual(plan["blocked"], [{"item": entry["logical_intent_key"], "reason": "SUPPRESSED"}])


class TimingTests(Base):
    def test_comments_seconds_apart_are_accepted(self):
        post = post_receipt(recorded_at=1000.0)
        for gap in (0, 1, 5, 45, 59, 60, 61, 240):
            errors = receipts.reveal_timing_errors(
                post, comment_receipt(recorded_at=1000.0 + gap)
            )
            self.assertEqual(
                errors, [],
                "a %ds gap is a legitimate ordered comment; no one-minute rule exists" % gap,
            )

    def test_a_comment_that_precedes_its_post_is_refused(self):
        post = post_receipt(recorded_at=1000.0)
        self.assertEqual(
            receipts.reveal_timing_errors(post, comment_receipt(recorded_at=999.0)),
            ["COMMENT_PRECEDES_POST"],
        )
        self.assertEqual(
            receipts.reveal_timing_errors(post, comment_receipt(recorded_at=1000.0)), [],
            "control: same-second publication is ordered, not early",
        )

    def test_timing_needs_a_receipted_parent_post(self):
        self.assertEqual(
            receipts.reveal_timing_errors(None, comment_receipt()),
            ["PARENT_POST_NOT_RECEIPTED"],
        )

    def test_a_non_numeric_timestamp_is_refused(self):
        post = post_receipt(recorded_at="2026-10-24T10:00:00Z")
        self.assertEqual(
            receipts.reveal_timing_errors(post, comment_receipt()),
            ["$.recorded_at: both receipts need a numeric provider timestamp"],
        )

    def test_a_bool_or_non_finite_timestamp_is_refused(self):
        # N4: float(True) == 1.0 and NaN compares false both ways.
        for bad in (True, False, float("nan"), float("inf"), "nan"):
            self.assertEqual(
                receipts.reveal_timing_errors(post_receipt(), comment_receipt(recorded_at=bad)),
                ["$.recorded_at: both receipts need a numeric provider timestamp"],
                "recorded_at %r is not a provider timestamp" % (bad,),
            )
        for good in (1005, 1005.5, "1005"):
            self.assertEqual(
                receipts.reveal_timing_errors(post_receipt(), comment_receipt(recorded_at=good)),
                [],
                "control: numeric timestamp %r is accepted" % (good,),
            )


class MalformedInputTests(Base):
    """N3: malformed plan input fails closed as the documented ReceiptError."""

    def test_a_non_object_plan_item_is_a_receipt_error(self):
        post = item("P-01", "SCHEDULED_POST", 1, "post")
        for bad in (None, "x", 5, ["P-01"]):
            with self.assertRaises(receipts.ReceiptError, msg="plan item %r" % (bad,)):
                self.plan([post, bad])
            with self.assertRaises(receipts.ReceiptError, msg="item_key %r" % (bad,)):
                receipts.item_key(bad)
            with self.assertRaises(receipts.ReceiptError, msg="true_receipt %r" % (bad,)):
                receipts.true_receipt(self.store, bad)
            errors = receipts.validate_provider_receipt(bad, post_receipt())
            self.assertTrue(
                any("a plan item must be an object" in e for e in errors),
                "validate_provider_receipt(%r) must name the malformed item, got %r" % (bad, errors),
            )

    def test_a_non_list_plan_or_unhashable_field_is_a_receipt_error(self):
        for bad in (None, 5):
            with self.assertRaises(receipts.ReceiptError, msg="items %r" % (bad,)):
                self.plan(bad)
        for field in ("purpose", "placement_id"):
            for value in ([], {}):
                entry = item("P-01", "SCHEDULED_POST", 1, "post")
                entry[field] = value
                with self.assertRaises(receipts.ReceiptError, msg="%s=%r" % (field, value)):
                    self.plan([entry])
        entry = item("P-01", "SCHEDULED_POST", 1, "post")
        entry["purpose"] = []
        self.assertTrue(
            any("has no post/comment receipt kind" in e
                for e in receipts.validate_provider_receipt(entry, post_receipt())),
        )

    def test_well_formed_input_is_still_planned(self):
        post = item("P-01", "SCHEDULED_POST", 1, "post")
        self.admit(post)
        self.assertEqual(self.plan([post])["resume"], [post["logical_intent_key"]])
        self.assertEqual(self.plan((post,))["resume"], [post["logical_intent_key"]],
                         "control: any sequence of item objects is a plan")


if __name__ == "__main__":
    unittest.main(verbosity=2)
