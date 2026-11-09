"""Community social contract tests (acceptance A14 and A15, WF10).

A14: connected account and member mappings, scopes, private-channel eligibility
and notification approval are correct.
A15: scheduled / published / comment-attachment states are represented honestly.

Every test is offline: ``FakeTransport`` replays scripted responses and records
the request, so the assertions read the exact URL, query and body that would
have crossed the seam.  Nothing here contacts GoHighLevel and no synthetic value
is presented as live evidence.
"""

from __future__ import annotations

import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    FakeTransport,
    SYNTHETIC_TENANT,
    approval,
    enabled_gate,
    fake_tenant,
    make_adapter,
    registry,
    resp,
    row,
)

from cli_anything.gohighlevel.public.auth import AuthKind  # noqa: E402
from cli_anything.gohighlevel.public.community_social import (  # noqa: E402
    ATTACHMENT_WARNING,
    AuthorMapping,
    COMMENT_TEXT_LIMIT,
    COMMUNITY_CAPTION_LIMIT,
    COMMUNITY_MEDIA_LIMIT,
    CommentPlan,
    CommunityAuthorRefused,
    CommunityMember,
    CommunityPreflightRefused,
    CommunitySocialAdapter,
    CommunitySocialGap,
    ConnectedAccount,
    TITLE_LIMIT,
    build_comment,
    build_community_post,
    lifecycle_for,
)
from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402
from cli_anything.gohighlevel.public.readback import ReadbackStatus  # noqa: E402
from cli_anything.gohighlevel.public.result import Status  # noqa: E402


def _rows():
    return (
        row(
            "social.accounts.list",
            method="GET",
            path_template="/social-media-posting/{locationId}/accounts",
            tenant_binding="path.locationId",
            scopes_candidate=("socialplanner/account.readonly",),
        ),
        row(
            "social.community.users.list",
            method="GET",
            path_template=(
                "/social-media-posting/{locationId}/community/accounts/"
                "{accountId}/users"
            ),
            tenant_binding="path.locationId",
            scopes_candidate=("socialplanner/oauth.readonly",),
        ),
        row(
            "social.community.group_users.validate",
            method="GET",
            path_template=(
                "/social-media-posting/{locationId}/community/groups/"
                "{groupId}/users/{contactId}/validate"
            ),
            tenant_binding="path.locationId",
            scopes_candidate=("socialplanner/account.readonly",),
        ),
        row(
            "social.posts.create",
            method="POST",
            path_template="/social-media-posting/{locationId}/posts",
            tenant_binding="path.locationId",
            write=True,
            approval_required=True,
            scopes_candidate=("socialplanner/post.write",),
        ),
        row(
            "social.posts.list",
            method="POST",
            path_template="/social-media-posting/{locationId}/posts/list",
            tenant_binding="path.locationId",
            scopes_candidate=("socialplanner/post.readonly",),
        ),
        row(
            "social.comments.community.create",
            method="POST",
            path_template="/social-media-posting/comments/community",
            tenant_binding="query.locationId",
            write=True,
            approval_required=True,
            scopes_candidate=("socialplanner/comments.write",),
        ),
        row(
            "social.comments.list",
            method="POST",
            path_template="/social-media-posting/comments/{platform}/list",
            tenant_binding="body.locationId",
        ),
    )


def _body_bytes(payload) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _account(
    account_id: str = "acct_community_1",
    *,
    platform: str = "community",
    oauth_id: str = "oauth-should-never-be-a-key",
    group_id: str | None = "grp_backend_1",
    name: str = "Community Channel",
) -> dict:
    payload = {
        "id": account_id,
        "platform": platform,
        "oauthId": oauth_id,
        "name": name,
    }
    if group_id is not None:
        payload["meta"] = {"groupId": group_id}
    return payload


def _account_object(**kwargs) -> ConnectedAccount:
    return ConnectedAccount.from_api(_account(**kwargs))


def _plan(caption: str = "Approved discussion content") -> object:
    authors = (AuthorMapping(account_id="acct_community_1", contact_id="contact_member_1", name="Member One"),)
    return build_community_post(
        accounts=(_account_object(),),
        authors=authors,
        title="Approved discussion title",
        caption=caption,
    )


class _Harness(unittest.TestCase):
    def adapter(self, transport: FakeTransport, *, rows=None):
        rows = tuple(rows if rows is not None else _rows())
        operations = registry(*rows)
        public = make_adapter(transport, operations, gate=enabled_gate(rows))
        return CommunitySocialAdapter(
            public=public, operations=operations, transport=transport
        )

    def tenant(self):
        return fake_tenant()


# ---------------------------------------------------------------------------
# A14 -- accounts, members, eligibility, notifications
# ---------------------------------------------------------------------------


class ConnectedAccountTests(_Harness):
    def test_connected_account_uses_id_not_oauth_id(self):
        account = ConnectedAccount.from_api(_account())
        self.assertEqual(account.account_id, "acct_community_1")
        self.assertEqual(account.oauth_id, "oauth-should-never-be-a-key")
        self.assertEqual(account.group_id, "grp_backend_1")

    def test_account_missing_id_is_refused_even_with_oauth_id(self):
        payload = {"oauthId": "oauth-only", "platform": "community"}
        with self.assertRaises(CommunityPreflightRefused) as caught:
            ConnectedAccount.from_api(payload)
        self.assertEqual(caught.exception.rule, "account_id_missing")
        self.assertTrue(caught.exception.detail["oauth_id_present"])

    def test_connected_account_listing_filters_community_channels(self):
        transport = FakeTransport(
            [
                resp(
                    200,
                    _body_bytes(
                        {
                            "accounts": [
                                _account("acct_community_1"),
                                _account("acct_facebook_1", platform="facebook", group_id=None),
                            ]
                        }
                    ),
                )
            ]
        )
        adapter = self.adapter(transport)
        result, accounts = adapter.list_community_accounts(tenant=self.tenant())
        self.assertIs(result.status, Status.ok)
        self.assertEqual([item.account_id for item in accounts], ["acct_community_1"])


class MemberPaginationTests(_Harness):
    def test_member_pagination_is_per_channel_account(self):
        transport = FakeTransport(
            [
                resp(200, _body_bytes({"users": [
                    {"contactId": "contact_a", "name": "Member A"}
                ]})),
                resp(200, _body_bytes({"users": [
                    {"contactId": "contact_b", "name": "Member B"}
                ]})),
            ]
        )
        adapter = self.adapter(transport)
        account_a = _account_object(account_id="acct_a", group_id="grp_a")
        account_b = _account_object(account_id="acct_b", group_id="grp_b")

        _, page_a = adapter.list_members(tenant=self.tenant(), account=account_a)
        _, page_b = adapter.list_members(tenant=self.tenant(), account=account_b)

        self.assertIn("/community/accounts/acct_a/users", transport.requests[0]["url"])
        self.assertIn("/community/accounts/acct_b/users", transport.requests[1]["url"])
        self.assertEqual(page_a.members[0].account_id, "acct_a")
        self.assertEqual(page_b.members[0].account_id, "acct_b")
        # A member eligible in one private channel is never tagged to another.
        self.assertNotEqual(page_a.members[0].account_id, account_b.account_id)

    def test_member_with_staff_identity_is_refused(self):
        payload = {"contactId": "contact_x", "userType": "user", "name": "Staff User"}
        with self.assertRaises(CommunityAuthorRefused) as caught:
            CommunityMember.from_api(payload, account=_account_object())
        self.assertEqual(caught.exception.rule, "staff_identity_not_allowed")

    def test_member_without_contact_id_is_refused(self):
        with self.assertRaises(ContractViolation) as caught:
            CommunityMember.from_api({"userId": "user_1"}, account=_account_object())
        self.assertEqual(caught.exception.rule, "member_contact_id_missing")


class MembershipValidationTests(_Harness):
    def test_membership_validation_uses_observed_group_id(self):
        transport = FakeTransport([resp(200, _body_bytes({"valid": True}))])
        adapter = self.adapter(transport)
        account = _account_object()
        result, validation = adapter.validate_author(
            tenant=self.tenant(), account=account, contact_id="contact_member_1"
        )
        self.assertIs(result.status, Status.ok)
        self.assertEqual(validation.state, "valid")
        url = transport.requests[0]["url"]
        self.assertIn(
            "/community/groups/grp_backend_1/users/contact_member_1/validate", url
        )
        self.assertNotIn(account.account_id, url)
        self.assertNotIn("slug", url)

    def test_validation_without_group_id_fails_loudly(self):
        transport = FakeTransport([])
        adapter = self.adapter(transport)
        account = _account_object(group_id=None)
        with self.assertRaises(CommunityPreflightRefused) as caught:
            adapter.validate_author(
                tenant=self.tenant(), account=account, contact_id="contact_member_1"
            )
        self.assertEqual(caught.exception.rule, "group_id_unobserved")
        self.assertEqual(transport.call_count, 0)

    def test_two_channels_validate_against_their_own_group(self):
        transport = FakeTransport(
            [
                resp(200, _body_bytes({"valid": True})),
                resp(200, _body_bytes({"valid": False})),
            ]
        )
        adapter = self.adapter(transport)
        first = _account_object(account_id="acct_a", group_id="grp_a")
        second = _account_object(account_id="acct_b", group_id="grp_b")
        _, validation_a = adapter.validate_author(
            tenant=self.tenant(), account=first, contact_id="contact_member_1"
        )
        _, validation_b = adapter.validate_author(
            tenant=self.tenant(), account=second, contact_id="contact_member_1"
        )
        self.assertIn("/groups/grp_a/", transport.requests[0]["url"])
        self.assertIn("/groups/grp_b/", transport.requests[1]["url"])
        self.assertEqual(validation_a.state, "valid")
        self.assertEqual(validation_b.state, "invalid")
        with self.assertRaises(CommunityAuthorRefused):
            adapter.require_valid_author(validation_b)


class PostPreflightTests(_Harness):
    def test_post_mapping_keys_are_account_ids_with_member_contact_ids(self):
        plan = _plan()
        details = plan.body["communityPostDetails"]
        self.assertEqual(list(details["postAsUser"]), ["acct_community_1"])
        self.assertEqual(
            details["postAsUser"]["acct_community_1"]["id"], "contact_member_1"
        )
        self.assertNotIn("oauth-should-never-be-a-key", details["postAsUser"])
        self.assertNotIn("userId", plan.body)

    def test_every_account_needs_author_mapping(self):
        with self.assertRaises(CommunityPreflightRefused) as caught:
            build_community_post(
                accounts=(_account_object(),),
                authors=(),
                title="Title",
                caption="Caption",
            )
        self.assertEqual(caught.exception.rule, "author_mapping_incomplete")

    def test_notification_defaults_false_and_requires_approval(self):
        self.assertFalse(_plan().notify_all_group_members)
        with self.assertRaises(CommunityPreflightRefused) as caught:
            build_community_post(
                accounts=(_account_object(),),
                authors=(AuthorMapping("acct_community_1", "contact_member_1"),),
                title="Title",
                caption="Caption",
                notify_all_group_members=True,
            )
        self.assertEqual(caught.exception.rule, "notification_requires_approval")
        approved = build_community_post(
            accounts=(_account_object(),),
            authors=(AuthorMapping("acct_community_1", "contact_member_1"),),
            title="Title",
            caption="Caption",
            notify_all_group_members=True,
            broadcast_approved=True,
        )
        self.assertTrue(approved.body["communityPostDetails"]["notifyAllGroupMembers"])

    def test_preflight_limits(self):
        authors = (AuthorMapping("acct_community_1", "contact_member_1"),)
        with self.assertRaises(CommunityPreflightRefused) as title_caught:
            build_community_post(
                accounts=(_account_object(),),
                authors=authors,
                title="t" * (TITLE_LIMIT + 1),
                caption="Caption",
            )
        self.assertEqual(title_caught.exception.rule, "community_title_too_long")

        with self.assertRaises(CommunityPreflightRefused) as caption_caught:
            build_community_post(
                accounts=(_account_object(),),
                authors=authors,
                title="Title",
                caption="c" * (COMMUNITY_CAPTION_LIMIT + 1),
            )
        self.assertEqual(caption_caught.exception.rule, "community_caption_too_long")

        media = tuple(
            {"url": f"https://cdn.example.test/{index}.png", "type": "image"}
            for index in range(COMMUNITY_MEDIA_LIMIT + 1)
        )
        with self.assertRaises(CommunityPreflightRefused) as media_caught:
            build_community_post(
                accounts=(_account_object(),),
                authors=authors,
                title="Title",
                caption="Caption",
                media=media,
            )
        self.assertEqual(media_caught.exception.rule, "community_media_too_many")

        exact = build_community_post(
            accounts=(_account_object(),),
            authors=authors,
            title="t" * TITLE_LIMIT,
            caption="c" * COMMUNITY_CAPTION_LIMIT,
            media=media[:COMMUNITY_MEDIA_LIMIT],
        )
        self.assertEqual(len(exact.body["media"]), COMMUNITY_MEDIA_LIMIT)
        self.assertEqual(set(exact.body["media"][0]), {"url", "type"})

    def test_cross_platform_split_keeps_community_caption(self):
        long_caption = "c" * COMMUNITY_CAPTION_LIMIT
        plan = _plan(caption=long_caption)
        requests = plan.platform_requests(
            other_platforms={"facebook": ["acct_facebook_1"]},
            other_caption="short caption",
        )
        community_request, other_request = requests
        self.assertTrue(community_request.is_community)
        self.assertEqual(community_request.body["summary"], long_caption)
        self.assertIn("communityPostDetails", community_request.body)
        self.assertNotIn("acct_facebook_1", community_request.account_ids)
        self.assertFalse(other_request.is_community)
        self.assertEqual(other_request.body["summary"], "short caption")
        self.assertNotIn("communityPostDetails", other_request.body)
        self.assertNotIn("title", other_request.body)

    def test_missing_operation_row_fails_loudly_with_change_request(self):
        transport = FakeTransport([])
        rows = tuple(
            item for item in _rows() if item.operation_id != "social.community.users.list"
        )
        operations = registry(*rows)
        public = make_adapter(transport, operations, gate=enabled_gate(rows))
        adapter = CommunitySocialAdapter(
            public=public, operations=operations, transport=transport
        )
        with self.assertRaises(CommunitySocialGap) as caught:
            adapter.list_members(tenant=self.tenant(), account=_account_object())
        self.assertEqual(caught.exception.operation_id, "social.community.users.list")
        self.assertEqual(
            caught.exception.detail["change_request"],
            "lanes/GHL-010-lane/change-requests/1.md",
        )
        self.assertEqual(transport.call_count, 0)


# ---------------------------------------------------------------------------
# A15 -- post lifecycle, comments, attachments
# ---------------------------------------------------------------------------


class PostLifecycleTests(_Harness):
    def _create(self, adapter, transport, *, list_payload, status="draft"):
        plan = build_community_post(
            accounts=(_account_object(),),
            authors=(AuthorMapping("acct_community_1", "contact_member_1"),),
            title="Title",
            caption="Caption",
            status=status,
            schedule_date="2026-11-09T15:00:00Z" if status == "scheduled" else None,
        )
        return adapter.create_post(
            tenant=self.tenant(),
            request=plan.platform_requests()[0],
            approval=approval(),
            readback=None,
        )

    def test_draft_and_scheduled_are_not_published(self):
        transport = FakeTransport(
            [
                resp(201, _body_bytes({"id": "post_1"})),
                resp(200, _body_bytes({"posts": [{"summary": "Caption", "status": "draft"}]})),
                resp(201, _body_bytes({"id": "post_2"})),
                resp(200, _body_bytes({"posts": [{"summary": "Caption", "status": "scheduled"}]})),
            ]
        )
        adapter = self.adapter(transport)
        draft = self._create(adapter, transport, list_payload=None)
        scheduled = self._create(
            adapter, transport, list_payload=None, status="scheduled"
        )
        self.assertEqual(draft.lifecycle.value, "draft_saved")
        self.assertEqual(scheduled.lifecycle.value, "scheduled")
        self.assertFalse(draft.published)
        self.assertFalse(scheduled.published)

    def test_published_requires_published_status_and_verified_readback(self):
        transport = FakeTransport(
            [
                resp(201, _body_bytes({"id": "post_1"})),
                resp(200, _body_bytes({"posts": [{"summary": "Caption", "status": "published"}]})),
            ]
        )
        adapter = self.adapter(transport)
        receipt = self._create(adapter, transport, list_payload=None)
        self.assertIs(receipt.result.status, Status.ok)
        self.assertIs(receipt.result.readback.result, ReadbackStatus.verified)
        self.assertEqual(receipt.lifecycle.value, "published_verified")
        self.assertTrue(receipt.published)

    def test_unverified_readback_is_never_published(self):
        transport = FakeTransport(
            [
                resp(201, _body_bytes({"id": "post_1"})),
                resp(200, _body_bytes({"posts": [{"summary": "A different post", "status": "published"}]})),
            ]
        )
        adapter = self.adapter(transport)
        receipt = self._create(adapter, transport, list_payload=None)
        self.assertIs(receipt.result.status, Status.unknown_outcome)
        self.assertEqual(receipt.lifecycle.value, "pending_processing")
        self.assertFalse(receipt.published)

    def test_rejected_create_is_failed(self):
        transport = FakeTransport([resp(422, _body_bytes({"message": "invalid"}))])
        adapter = self.adapter(transport)
        receipt = self._create(adapter, transport, list_payload=None)
        self.assertEqual(receipt.lifecycle.value, "failed")

    def test_duplicate_idempotency_key_does_not_duplicate_post(self):
        transport = FakeTransport(
            [
                resp(201, _body_bytes({"id": "post_1"})),
                resp(200, _body_bytes({"posts": [{"summary": "Caption", "status": "draft"}]})),
            ]
        )
        adapter = self.adapter(transport)
        plan = _plan()
        request = plan.platform_requests()[0]
        first = adapter.create_post(
            tenant=self.tenant(),
            request=request,
            approval=approval(),
            idempotency_key="gxo_social-posts-create-0123456789abcdef0123456789abcdef",
        )
        second = adapter.create_post(
            tenant=self.tenant(),
            request=request,
            approval=approval(),
            idempotency_key="gxo_social-posts-create-0123456789abcdef0123456789abcdef",
        )
        self.assertFalse(first.deduplicated)
        self.assertTrue(second.deduplicated)
        self.assertEqual(transport.call_count, 2)  # one create + one readback


class CommentTests(_Harness):
    def test_comment_uses_internal_post_id_and_parent_semantics(self):
        parent = build_comment(post_id="post_internal_1", text="Approved comment")
        self.assertTrue(parent.is_parent_thread)
        self.assertEqual(parent.body["postId"], "post_internal_1")
        self.assertNotIn("parentCommentId", parent.body)

        reply = build_comment(
            post_id="post_internal_1",
            text="Reply text",
            is_parent_thread=False,
            parent_comment_id="comment_internal_9",
        )
        self.assertFalse(reply.body["isParentThread"])
        self.assertEqual(reply.body["parentCommentId"], "comment_internal_9")

        with self.assertRaises(CommunityPreflightRefused):
            build_comment(post_id="p", text="t", is_parent_thread=False)
        with self.assertRaises(CommunityPreflightRefused):
            build_comment(
                post_id="p", text="t", is_parent_thread=True, parent_comment_id="c"
            )

    def test_comment_text_limit_and_notify_default(self):
        plan = build_comment(post_id="post_internal_1", text="x" * COMMENT_TEXT_LIMIT)
        self.assertFalse(plan.notify_all_group_members)
        self.assertFalse(plan.body["notifyAllGroupMembers"])
        with self.assertRaises(CommunityPreflightRefused) as caught:
            build_comment(post_id="post_internal_1", text="x" * (COMMENT_TEXT_LIMIT + 1))
        self.assertEqual(caught.exception.rule, "comment_text_too_long")
        with self.assertRaises(CommunityPreflightRefused):
            build_comment(
                post_id="post_internal_1", text="x", notify_all_group_members=True
            )

    def test_comment_attachment_not_rendered(self):
        plan = build_comment(
            post_id="post_internal_1",
            text="See attached",
            attachments=["https://cdn.example.test/file.pdf"],
        )
        self.assertFalse(plan.attachments_rendered)
        self.assertEqual(plan.attachment_warning, ATTACHMENT_WARNING)
        self.assertNotIn("attachments", plan.body)
        self.assertNotIn("https://cdn.example.test/file.pdf", json.dumps(plan.body))

    def test_comment_request_uses_query_tenant_and_internal_id(self):
        plan = build_comment(post_id="post_internal_1", text="Approved comment")
        transport = FakeTransport(
            [
                resp(201, _body_bytes({"id": "comment_1"})),
                resp(200, _body_bytes({"comments": [{"postId": "post_internal_1"}]})),
            ]
        )
        adapter = self.adapter(transport)
        receipt = adapter.create_comment(
            tenant=self.tenant(), plan=plan, approval=approval()
        )
        first = transport.requests[0]
        self.assertEqual(first["url"], "/social-media-posting/comments/community")
        self.assertEqual(first["query"], {"locationId": SYNTHETIC_TENANT})
        self.assertEqual(first["body"]["postId"], "post_internal_1")
        self.assertFalse(receipt.attachments_rendered)


class CommandRegistrationTests(unittest.TestCase):
    """WF03 owns the CLI file; this proves the registration seam WF10 ships."""

    def test_register_adds_community_group(self):
        import click

        from cli_anything.gohighlevel.community_social_commands import register

        root = click.Group("root")
        register(root)
        self.assertIn("community", root.commands)
        self.assertIn("draft-post", root.commands["community"].commands)
        self.assertIn("comment", root.commands["community"].commands)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
