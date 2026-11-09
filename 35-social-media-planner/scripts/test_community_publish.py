#!/usr/bin/env python3
"""test_community_publish.py — WF11 focused tests for the Skill 35 Community
publishing consumer.

Every provider call is a controlled fake. No network, no live GoHighLevel, no
owner notification. The fake adapter implements exactly the WF10 surface this
consumer requires, so a passing test proves the CONSUMER, not the provider.

Acceptance coverage:
  A14 — Community account/member mappings, scopes, private-channel eligibility
        and notifications are correct (CommunityTestA14*).
  A15 — Scheduled/published/comment attachment states are accurately
        represented (CommunityTestA15*).

Run:  python3 35-social-media-planner/scripts/test_community_publish.py
Exit: 0 = the consumer contract holds.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE = HERE / "community_publish.py"


def _load():
    spec = importlib.util.spec_from_file_location("community_publish", MODULE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["community_publish"] = mod
    spec.loader.exec_module(mod)
    return mod


cp = _load()

# ---------------------------------------------------------------------------
# fake WF10 adapter — fake-only, never a live call
# ---------------------------------------------------------------------------
class FakeAdapter:
    """Implements the frozen WF10 surface with controlled, inspectable data."""

    def __init__(self, accounts, members, validations=None, create_status="published",
                 read_status=None, post_url="https://example.invalid/p/1"):
        self.accounts_payload = accounts
        self.members = members                  # {account_id: [rows]}
        self.validations = validations or {}    # {contact_id: bool}
        self.create_status = create_status
        self.read_status = read_status
        self.post_url = post_url
        self.calls = []

    def list_accounts(self, location_id):
        self.calls.append(("list_accounts", location_id))
        return self.accounts_payload

    def list_community_members(self, location_id, account_id, cursor=None):
        self.calls.append(("list_community_members", account_id, cursor))
        rows = self.members.get(account_id, [])
        # two pages for account "acct-A" so pagination is exercised
        if account_id == "acct-A" and cursor is None and len(rows) > 1:
            return {"results": {"users": rows[:1]}, "nextCursor": "p2"}
        if cursor == "p2":
            return {"results": {"users": rows[1:]} , "nextCursor": None}
        return {"results": {"users": rows}, "nextCursor": None}

    def validate_community_author(self, location_id, group_id, contact_id):
        self.calls.append(("validate_community_author", group_id, contact_id))
        return {"valid": self.validations.get(contact_id, True)}

    def create_post(self, location_id, payload):
        self.calls.append(("create_post", payload))
        return {"id": "post-1", "status": self.create_status, "url": self.post_url}

    def get_post(self, location_id, post_id):
        self.calls.append(("get_post", post_id))
        status = self.read_status or self.create_status
        return {"id": post_id, "status": status, "url": self.post_url}

    def create_comment(self, location_id, payload):
        self.calls.append(("create_comment", payload))
        return {"id": "comment-1"}


def accounts_payload(*accounts):
    return {"success": True, "results": {"accounts": list(accounts)}}


def community_account(account_id, name="Community", group_slug="my-group"):
    return {"id": account_id, "type": "community", "name": name,
            "platform": "community", "groupSlug": group_slug}


def base_task(**over):
    task = {
        "cycle_id": "cycle-1",
        "topic": "Week of launch",
        "title": "Approved discussion title",
        "caption": "Approved discussion content",
        "accounts": [{"channel": "community", "account_id": "acct-A"}],
    }
    task.update(over)
    return task


# ---------------------------------------------------------------------------
# A14 — accounts, members, eligibility, notifications
# ---------------------------------------------------------------------------
class CommunityTestA14AccountsMembers(unittest.TestCase):
    def setUp(self):
        self.table = cp.load_channel_table()

    def test_a14_correct_account_member_mapping(self):
        adapter = FakeAdapter(
            accounts_payload(community_account("acct-A")),
            {"acct-A": [{"contactId": "contact-1", "name": "Member One"},
                        {"contactId": "contact-2", "name": "Member Two"}]})
        receipt = cp.publish_community_task(
            adapter, location_id="loc-1", group_id="grp-1",
            task=base_task(), table=self.table)
        self.assertEqual(receipt["authors"][0]["contact_id"], "contact-1")
        payload = [c[1] for c in adapter.calls if c[0] == "create_post"][0]
        # account.id is stored, and the author is the member contactId
        self.assertEqual(payload["accountIds"], ["acct-A"])
        self.assertEqual(payload["communityPostDetails"]["postAsUser"]["acct-A"]["id"],
                         "contact-1")

    def test_a14_oauth_id_is_not_an_account_id(self):
        bad = {"success": True, "results": {"accounts": [
            {"oauthId": "oauth-9", "type": "community", "name": "Community"}]}}
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.community_accounts(bad)
        self.assertEqual(ctx.exception.code, "account_id_missing")

    def test_a14_staff_user_id_rejected(self):
        adapter = FakeAdapter(
            accounts_payload(community_account("acct-A")),
            {"acct-A": [{"contactId": "contact-1", "name": "Member One"}]})
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.publish_community_task(
                adapter, location_id="loc-1", group_id="grp-1",
                task=base_task(), table=self.table,
                selections={"acct-A": "staff-77"},
                staff_user_ids={"staff-77"})
        self.assertEqual(ctx.exception.code, "staff_id_rejected")
        self.assertFalse([c for c in adapter.calls if c[0] == "create_post"])

    def test_a14_two_private_channels_need_distinct_eligibility(self):
        adapter = FakeAdapter(
            accounts_payload(community_account("acct-A"), community_account("acct-B")),
            {"acct-A": [{"contactId": "contact-1", "name": "A Member"}],
             "acct-B": [{"contactId": "contact-2", "name": "B Member"}]})
        task = base_task(accounts=[{"channel": "community", "account_id": "acct-A"},
                                   {"channel": "community", "account_id": "acct-B"}])
        receipt = cp.publish_community_task(
            adapter, location_id="loc-1", group_id="grp-1", task=task, table=self.table)
        mapping = {a["account_id"]: a["contact_id"] for a in receipt["authors"]}
        self.assertEqual(mapping, {"acct-A": "contact-1", "acct-B": "contact-2"})
        payload = [c[1] for c in adapter.calls if c[0] == "create_post"][0]
        self.assertEqual(sorted(payload["communityPostDetails"]["postAsUser"]),
                         ["acct-A", "acct-B"])

    def test_a14_member_not_eligible_in_second_channel(self):
        adapter = FakeAdapter(
            accounts_payload(community_account("acct-A"), community_account("acct-B")),
            {"acct-A": [{"contactId": "contact-1", "name": "A Member"}],
             "acct-B": [{"contactId": "contact-2", "name": "B Member"}]})
        task = base_task(accounts=[{"channel": "community", "account_id": "acct-A"},
                                   {"channel": "community", "account_id": "acct-B"}])
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.publish_community_task(
                adapter, location_id="loc-1", group_id="grp-1", task=task,
                table=self.table, selections={"acct-B": "contact-1"})
        self.assertEqual(ctx.exception.code, "member_not_eligible_for_channel")

    def test_a14_author_revoked_after_scheduling(self):
        adapter = FakeAdapter(
            accounts_payload(community_account("acct-A")),
            {"acct-A": [{"contactId": "contact-1", "name": "Member One"}]},
            validations={"contact-1": False})
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.publish_community_task(
                adapter, location_id="loc-1", group_id="grp-1",
                task=base_task(), table=self.table)
        self.assertEqual(ctx.exception.code, "author_revoked")
        self.assertFalse([c for c in adapter.calls if c[0] == "create_post"])

    def test_a14_no_notification_without_approval(self):
        adapter = FakeAdapter(
            accounts_payload(community_account("acct-A")),
            {"acct-A": [{"contactId": "contact-1", "name": "Member One"}]})
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.publish_community_task(
                adapter, location_id="loc-1", group_id="grp-1",
                task=base_task(notify_all_group_members=True), table=self.table)
        self.assertEqual(ctx.exception.code, "broadcast_not_approved")
        # and it is off by default
        receipt = cp.publish_community_task(
            adapter, location_id="loc-1", group_id="grp-1",
            task=base_task(), table=self.table)
        self.assertTrue(receipt["post_id"])
        payload = [c[1] for c in adapter.calls if c[0] == "create_post"][0]
        self.assertFalse(payload["communityPostDetails"]["notifyAllGroupMembers"])

    def test_a14_group_id_required_and_slug_refused(self):
        adapter = FakeAdapter(
            accounts_payload(community_account("acct-A")),
            {"acct-A": [{"contactId": "contact-1", "name": "Member One"}]})
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.publish_community_task(
                adapter, location_id="loc-1", group_id="", task=base_task(),
                table=self.table)
        self.assertEqual(ctx.exception.code, "group_id_required")

    def test_a14_limits_title_caption_media(self):
        adapter = FakeAdapter(
            accounts_payload(community_account("acct-A")),
            {"acct-A": [{"contactId": "contact-1", "name": "Member One"}]})
        # title over 1,000
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.publish_community_task(
                adapter, location_id="loc-1", group_id="grp-1",
                task=base_task(title="t" * 1001), table=self.table)
        self.assertEqual(ctx.exception.code, "title_over_limit")
        # caption over 100,000
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.publish_community_task(
                adapter, location_id="loc-1", group_id="grp-1",
                task=base_task(caption="c" * 100001), table=self.table)
        self.assertEqual(ctx.exception.code, "caption_over_limit")
        # five media items
        media = [{"url": f"https://cdn.example.invalid/{i}.png", "type": "image"}
                 for i in range(5)]
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.publish_community_task(
                adapter, location_id="loc-1", group_id="grp-1",
                task=base_task(media=media), table=self.table)
        self.assertEqual(ctx.exception.code, "media_over_limit")
        # exactly four passes, and a bare URL string is refused
        ok = cp.publish_community_task(
            adapter, location_id="loc-1", group_id="grp-1",
            task=base_task(media=media[:4]), table=self.table)
        self.assertTrue(ok["post_id"])
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.publish_community_task(
                adapter, location_id="loc-1", group_id="grp-1",
                task=base_task(media=["https://cdn.example.invalid/x.png"]),
                table=self.table)
        self.assertEqual(ctx.exception.code, "media_item_shape")

    def test_a14_conversation_reply_refused_skill38_owns_it(self):
        adapter = FakeAdapter(
            accounts_payload(community_account("acct-A")),
            {"acct-A": [{"contactId": "contact-1", "name": "Member One"}]})
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.publish_community_task(
                adapter, location_id="loc-1", group_id="grp-1",
                task=base_task(intent="reply"), table=self.table)
        self.assertEqual(ctx.exception.code, "conversation_owned_by_skill_38")

    def test_a14_department_routing(self):
        self.assertEqual(cp.route_department(base_task(scope="inside_group")),
                         "community-builder")
        self.assertEqual(cp.route_department(base_task(scope="external")), "social-media")
        self.assertEqual(cp.route_department(base_task()), "social-media")


# ---------------------------------------------------------------------------
# A15 — lifecycle states, comments, attachments, idempotency, splitting
# ---------------------------------------------------------------------------
class CommunityTestA15LifecycleStates(unittest.TestCase):
    def setUp(self):
        self.table = cp.load_channel_table()
        self.adapter_kwargs = {
            "accounts": accounts_payload(community_account("acct-A")),
            "members": {"acct-A": [{"contactId": "contact-1", "name": "Member One"}]},
        }

    def test_a15_scheduled_is_not_published(self):
        adapter = FakeAdapter(**self.adapter_kwargs, create_status="scheduled",
                              read_status="scheduled")
        receipt = cp.publish_community_task(
            adapter, location_id="loc-1", group_id="grp-1", task=base_task(),
            table=self.table)
        self.assertEqual(receipt["state"], "scheduled")
        self.assertFalse(receipt["published"])

    def test_a15_published_with_readback_is_verified(self):
        adapter = FakeAdapter(**self.adapter_kwargs, create_status="published",
                              read_status="published")
        receipt = cp.publish_community_task(
            adapter, location_id="loc-1", group_id="grp-1", task=base_task(),
            table=self.table)
        self.assertEqual(receipt["state"], "published_verified")
        self.assertTrue(receipt["published"])
        self.assertEqual(receipt["readback"]["state"], "matched")

    def test_a15_published_without_readback_match_is_not_verified(self):
        adapter = FakeAdapter(**self.adapter_kwargs, create_status="published",
                              read_status="processing")
        receipt = cp.publish_community_task(
            adapter, location_id="loc-1", group_id="grp-1", task=base_task(),
            table=self.table)
        self.assertNotEqual(receipt["state"], "published_verified")
        self.assertFalse(receipt["published"])

    def test_a15_pending_moderation_is_not_success(self):
        adapter = FakeAdapter(**self.adapter_kwargs, create_status="pending_moderation",
                              read_status="pending_moderation")
        receipt = cp.publish_community_task(
            adapter, location_id="loc-1", group_id="grp-1", task=base_task(),
            table=self.table)
        self.assertEqual(receipt["state"], "pending_moderation")
        self.assertFalse(receipt["published"])

    def test_a15_duplicate_callback_does_not_duplicate_post(self):
        adapter = FakeAdapter(**self.adapter_kwargs, create_status="published")
        store = {}
        first = cp.publish_community_task(
            adapter, location_id="loc-1", group_id="grp-1", task=base_task(),
            table=self.table, receipt_store=store)
        second = cp.publish_community_task(
            adapter, location_id="loc-1", group_id="grp-1", task=base_task(),
            table=self.table, receipt_store=store)
        self.assertFalse(first.get("deduped", False))
        self.assertTrue(second["deduped"])
        self.assertEqual(second["post_id"], first["post_id"])
        self.assertEqual(len([c for c in adapter.calls if c[0] == "create_post"]), 1)

    def test_a15_comment_uses_internal_post_id_and_parent_thread(self):
        adapter = FakeAdapter(**self.adapter_kwargs)
        top = cp.publish_community_comment(
            adapter, location_id="loc-1", post_id="post-1", text="first",
            table=self.table)
        self.assertTrue(top["is_parent_thread"])
        reply = cp.publish_community_comment(
            adapter, location_id="loc-1", post_id="post-1", text="reply",
            parent_comment_id="comment-1", table=self.table)
        self.assertFalse(reply["is_parent_thread"])
        payload = [c[1] for c in adapter.calls if c[0] == "create_comment"]
        self.assertEqual(payload[0]["postId"], "post-1")
        self.assertEqual(payload[1]["commentId"], "comment-1")

    def test_a15_comment_limit_8000(self):
        adapter = FakeAdapter(**self.adapter_kwargs)
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.publish_community_comment(
                adapter, location_id="loc-1", post_id="post-1", text="x" * 8001,
                table=self.table)
        self.assertEqual(ctx.exception.code, "comment_over_limit")

    def test_a15_attachment_not_rendered_is_reported(self):
        adapter = FakeAdapter(**self.adapter_kwargs)
        receipt = cp.publish_community_comment(
            adapter, location_id="loc-1", post_id="post-1", text="see file",
            attach_url="https://cdn.example.invalid/doc.pdf", table=self.table)
        self.assertFalse(receipt["attachment_rendered"])
        self.assertTrue(receipt["attachment_warning"])
        self.assertIn("not rendered", receipt["attachment_warning"])

    def test_a15_cross_platform_split_keeps_community_caption(self):
        task = {
            "cycle_id": "cycle-2",
            "accounts": [
                {"channel": "community", "account_id": "acct-A"},
                {"channel": "x", "account_id": "acct-X"},
            ],
        }
        rows = cp.split_by_channel(self.table, task)
        kinds = [r["kind"] for r in rows]
        self.assertEqual(kinds, ["community", "external"])
        self.assertEqual(rows[0]["accounts"][0]["account_id"], "acct-A")
        # community accepts a caption X would reject — the split is what keeps it
        long_caption = "c" * 5000
        cp.preflight_channel_content(self.table, "community", title="t",
                                     caption=long_caption, media=[])
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.preflight_channel_content(self.table, "x", title=None,
                                         caption=long_caption, media=[])
        self.assertEqual(ctx.exception.code, "caption_over_limit")

    def test_a15_unmapped_channel_refused(self):
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.channel_limits(self.table, "myspace")
        self.assertEqual(ctx.exception.code, "channel_unmapped")

    def test_a15_resync_required_then_requery(self):
        adapter = FakeAdapter(**self.adapter_kwargs)
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.sync_then_requery(adapter, "loc-1", group_slug="brand-new-group")
        self.assertEqual(ctx.exception.code, "resync_step_required")

        class ResyncAdapter(FakeAdapter):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                self.resent = False

            def list_accounts(self, location_id):
                if self.resent:
                    return accounts_payload(
                        community_account("acct-A"),
                        community_account("acct-N", name="Brand New",
                                          group_slug="brand-new-group"))
                return self.accounts_payload

        ad = ResyncAdapter(accounts_payload(community_account("acct-A")),
                           self.adapter_kwargs["members"])
        out = cp.sync_then_requery(
            ad, "loc-1", group_slug="brand-new-group",
            run_resync=lambda loc: setattr(ad, "resent", True))
        self.assertTrue(out["resync_performed"])
        self.assertEqual(len(out["accounts"]), 2)

    def test_a15_missing_wf10_adapter_blocks_loudly(self):
        # The real adapter is not on this tree yet (assumed WF10-CP01).
        with self.assertRaises(cp.CommunityAdapterUnavailable) as ctx:
            cp.load_community_adapter(engine_root="/nonexistent/engine")
        self.assertIn("WF10-CP01", str(ctx.exception))

    def test_a15_incomplete_adapter_rejected(self):
        class Partial:
            def list_accounts(self, location_id):
                return []

        with self.assertRaises(cp.CommunityAdapterUnavailable) as ctx:
            cp.require_adapter(Partial())
        self.assertIn("create_post", str(ctx.exception))

    def test_a15_non_community_posting_unchanged(self):
        # External-only tasks never enter the Community builder.
        task = {"cycle_id": "c3", "accounts": [{"channel": "facebook", "account_id": "fb-1"}]}
        rows = cp.split_by_channel(self.table, task)
        self.assertEqual([r["kind"] for r in rows], ["external"])
        adapter = FakeAdapter(**self.adapter_kwargs)
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.publish_community_task(
                adapter, location_id="loc-1", group_id="grp-1", task=task,
                table=self.table)
        self.assertEqual(ctx.exception.code, "no_community_accounts")
        self.assertFalse([c for c in adapter.calls if c[0] == "create_post"])


class CommunityTestA14Entrypoint(unittest.TestCase):
    """The REAL cycle entrypoint reaches the consumer (not a library-only path)."""

    CURL_STUB = """#!/bin/sh
for a in "$@"; do
  case "$a" in
    *leadconnectorhq.com*) exit 7 ;;
  esac
done
exec {real_curl} "$@"
"""

    def setUp(self):
        import shutil
        import tempfile

        self.h = tempfile.TemporaryDirectory()
        home = Path(self.h.name)
        oc = home / ".openclaw"
        (oc / "secrets").mkdir(parents=True, exist_ok=True)
        (oc / "config").mkdir(parents=True, exist_ok=True)
        for f in ("SOUL.md", "IDENTITY.md", "USER.md"):
            (oc / f).write_text(f"fixture {f}")
        (oc / "secrets" / ".env").write_text(
            "GOHIGHLEVEL_API_KEY=test-key\nGOHIGHLEVEL_LOCATION_ID=test-loc\n")
        (oc / "openclaw.json").write_text('{"agents": {"list": []}}\n')
        bindir = home / "bin"
        bindir.mkdir(parents=True, exist_ok=True)
        stub = bindir / "curl"
        stub.write_text(self.CURL_STUB.format(
            real_curl=shutil.which("curl") or "/usr/bin/curl"))
        stub.chmod(0o755)
        self.home = str(home)
        self.script = HERE / "run-publishing-cycle.sh"
        # A copy of this skill with NO sibling 44-convert-and-flow-operator tree.
        # It is the only way to ask "what does the entrypoint do when the WF10
        # adapter is genuinely absent?" once the adapter exists on this checkout.
        self.isolated = home / "skill35"
        shutil.copytree(HERE.parent, self.isolated,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.isolated_script = self.isolated / "scripts" / "run-publishing-cycle.sh"

    def tearDown(self):
        self.h.cleanup()

    def _run(self, *args, script=None, task=None):
        import subprocess

        env = {
            "HOME": self.home,
            "PATH": "%s/bin:/usr/bin:/bin" % self.home,
            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        }
        script = script or self.script
        task = task or (HERE / "community-task.example.json")
        return subprocess.run(
            ["bash", str(script), "--community-task", str(task),
             "--community-group-id", "grp-1", *args],
            capture_output=True, text=True, timeout=120, env=env)

    def test_a14_entrypoint_check_mode_makes_no_provider_call(self):
        p = self._run()
        self.assertEqual(p.returncode, 0, f"STDOUT:{p.stdout}\nSTDERR:{p.stderr}")
        self.assertIn('"department": "community-builder"', p.stdout)
        self.assertIn("CHECK ONLY", p.stdout)

    def test_a14_entrypoint_blocks_loudly_without_wf10_adapter(self):
        # Run the REAL entrypoint from a tree where the WF10 adapter does not
        # exist: the loud BLOCKED path, not a fabricated success and not the
        # live path this checkout would otherwise take.
        p = self._run("--community-publish", script=self.isolated_script,
                      task=self.isolated / "scripts" / "community-task.example.json")
        self.assertEqual(p.returncode, 3,
                         f"expected a loud BLOCKED, got {p.returncode}\n"
                         f"STDOUT:{p.stdout}\nSTDERR:{p.stderr}")
        self.assertIn("BLOCKED", p.stderr)
        self.assertIn("WF10-CP01", p.stderr)


# ---------------------------------------------------------------------------
# Integration: the consumer bound to the PUBLISHED WF10 adapter, driven through
# the FROZEN WF00-CP01 operation rows. This is what the WF00/WF10 unblocking
# bought: every call below resolves a real row and builds the real path, offline.
# ---------------------------------------------------------------------------
_ENGINE = HERE.parents[1] / "44-convert-and-flow-operator" / "tools" / "engine"
for _extra in (str(_ENGINE), str(_ENGINE / "tests")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from _public_contract_fakes import (  # noqa: E402
    SYNTHETIC_TENANT as _TENANT,
    FakeTransport as _FakeTransport,
    enabled_gate as _enabled_gate,
    fake_tenant as _fake_tenant,
    make_adapter as _make_adapter,
    resp as _resp,
)
from cli_anything.gohighlevel.public.adapter import ApprovalRef as _ApprovalRef  # noqa: E402
from cli_anything.gohighlevel.public.community_social import (  # noqa: E402
    CommunitySocialAdapter as _WF10Adapter,
    OPERATION_IDS as _WF10_OPERATION_IDS,
)
from cli_anything.gohighlevel.public.operations import (  # noqa: E402
    OPERATIONS as _FROZEN_OPERATIONS,
)

#: The three Community rows WF00-CP01 froze, with the facts this consumer needs.
_FROZEN_COMMUNITY_ROWS = {
    "social.community.accounts.users.list": (
        "GET",
        "/social-media-posting/{locationId}/community/accounts/{accountId}/users",
        "path.locationId",
        "socialplanner/oauth.readonly",
    ),
    "social.community.authors.validate": (
        "GET",
        "/social-media-posting/{locationId}/community/groups/{groupId}/users/"
        "{contactId}/validate",
        "path.locationId",
        "socialplanner/account.readonly",
    ),
    "social.community.comments.create": (
        "POST",
        "/social-media-posting/comments/community",
        "query.locationId",
        "socialplanner/comments.write",
    ),
}

def _row_attr(row, name):
    return getattr(row, name, None)

class CommunityTestWF10Integration(unittest.TestCase):
    """One real adapter, one real registry, zero network."""

    def _binding(self, responses, *, approval=True):
        transport = _FakeTransport(responses)
        rows = list(_FROZEN_OPERATIONS.values())
        public = _make_adapter(transport, _FROZEN_OPERATIONS,
                               gate=_enabled_gate(rows))
        adapter = _WF10Adapter(public=public, transport=transport)
        module = cp.import_wf10_module(str(_ENGINE))
        binding = cp.bind_community_adapter(
            module, adapter, _fake_tenant(),
            approval=_ApprovalRef(ref="approval-synthetic-wf11") if approval else None)
        return binding, transport

    @staticmethod
    def _accounts_body(group_id="grp-real-1"):
        return _resp(200, json.dumps({"accounts": [{
            "id": "acct-real", "platform": "community", "name": "Launch Group",
            "meta": {"groupId": group_id}}]}).encode())

    @staticmethod
    def _members_body():
        return _resp(200, json.dumps({"users": [
            {"contactId": "contact-real", "name": "Approved Member"}]}).encode())

    @staticmethod
    def _validate_body(valid=True):
        return _resp(200, json.dumps({"valid": valid}).encode())

    def _task(self, **over):
        task = {
            "cycle_id": "cycle-real-1",
            "topic": "Launch week",
            "title": "Approved discussion title",
            "caption": "Approved discussion content",
            "accounts": [{"channel": "community", "account_id": "acct-real"}],
        }
        task.update(over)
        return task

    # -- A14: rows, account/member mapping, request shapes ---------------
    def test_a14_every_consumer_operation_id_is_a_frozen_wf00_row(self):
        for key, operation_id in _WF10_OPERATION_IDS.items():
            self.assertIsNotNone(
                _FROZEN_OPERATIONS.get(operation_id),
                "consumer key %r needs %r and WF00 freezes no such row"
                % (key, operation_id))
        # The Community ids are the ones WF00 froze, not the earlier assumptions.
        self.assertEqual(_WF10_OPERATION_IDS["members.list"],
                         "social.community.accounts.users.list")
        self.assertEqual(_WF10_OPERATION_IDS["members.validate"],
                         "social.community.authors.validate")
        self.assertEqual(_WF10_OPERATION_IDS["comments.create"],
                         "social.community.comments.create")

    def test_a14_frozen_community_rows_carry_the_documented_facts(self):
        for operation_id, (method, path, tenant, scope) in _FROZEN_COMMUNITY_ROWS.items():
            row = _FROZEN_OPERATIONS.get(operation_id)
            self.assertIsNotNone(row, "%s is missing from WF00 operations.py" % operation_id)
            self.assertEqual(_row_attr(row, "method"), method, operation_id)
            self.assertEqual(_row_attr(row, "path_template"), path, operation_id)
            self.assertEqual(_row_attr(row, "tenant_binding"), tenant, operation_id)
            self.assertEqual(tuple(_row_attr(row, "scopes_candidate") or ()), (scope,),
                             operation_id)
            self.assertEqual(_row_attr(row, "write"), method != "GET", operation_id)

    def test_a14_real_module_exposes_the_published_surface(self):
        module = cp.import_wf10_module(str(_ENGINE))
        self.assertEqual(cp.wf10_surface_gaps(module), [])

    def test_a14_real_adapter_publishes_through_the_frozen_rows(self):
        caption = "Approved discussion content"
        binding, transport = self._binding([
            self._accounts_body(),
            self._members_body(),
            self._validate_body(),
            _resp(201, json.dumps({"id": "post-internal-1"}).encode()),
            _resp(200, json.dumps({"posts": [
                {"id": "post-internal-1", "status": "published", "summary": caption}
            ]}).encode()),
        ])
        receipt = cp.publish_community_task(
            binding, location_id=_TENANT, group_id="grp-real-1",
            task=self._task(status="scheduled", scheduled_at="2026-11-10T14:00:00Z"))

        seen = [(r["method"], r["url"]) for r in transport.requests]
        self.assertEqual(seen, [
            ("GET", "/social-media-posting/%s/accounts" % _TENANT),
            ("GET", "/social-media-posting/%s/community/accounts/acct-real/users" % _TENANT),
            ("GET", "/social-media-posting/%s/community/groups/grp-real-1/users/"
                    "contact-real/validate" % _TENANT),
            ("POST", "/social-media-posting/%s/posts" % _TENANT),
            ("POST", "/social-media-posting/%s/posts/list" % _TENANT),
        ])
        body = transport.requests[3]["body"]
        self.assertEqual(body["accountIds"], ["acct-real"])
        self.assertEqual(body["summary"], caption)
        self.assertEqual(body["status"], "scheduled")
        self.assertEqual(body["scheduleDate"], "2026-11-10T14:00:00Z")
        # account.id is the key; the author is the member's own contactId
        self.assertEqual(body["communityPostDetails"]["postAsUser"]["acct-real"]["id"],
                         "contact-real")
        self.assertEqual(receipt["state"], "published_verified")
        self.assertTrue(receipt["published"])
        self.assertIsNone(receipt["post_id"])
        self.assertEqual(receipt["post_id_gap"], "post_id_not_exposed_by_wf10_cp01")

    # -- A15: lifecycle honesty on the real adapter ----------------------
    def test_a15_real_adapter_scheduled_is_not_published(self):
        caption = "Approved discussion content"
        binding, transport = self._binding([
            self._accounts_body(),
            self._members_body(),
            self._validate_body(),
            _resp(201, json.dumps({"id": "post-internal-2"}).encode()),
            _resp(200, json.dumps({"posts": [
                {"id": "post-internal-2", "status": "scheduled", "summary": caption}
            ]}).encode()),
        ])
        receipt = cp.publish_community_task(
            binding, location_id=_TENANT, group_id="grp-real-1",
            task=self._task(status="scheduled", scheduled_at="2026-11-10T14:00:00Z"))
        self.assertEqual(receipt["state"], "scheduled")
        self.assertFalse(receipt["published"])
        self.assertEqual(len(transport.requests), 5)

    def test_a15_real_adapter_processing_readback_is_not_verified(self):
        caption = "Approved discussion content"
        binding, transport = self._binding([
            self._accounts_body(),
            self._members_body(),
            self._validate_body(),
            _resp(201, json.dumps({"id": "post-internal-3"}).encode()),
            _resp(200, json.dumps({"posts": [
                {"id": "post-internal-3", "status": "processing", "summary": caption}
            ]}).encode()),
        ])
        receipt = cp.publish_community_task(
            binding, location_id=_TENANT, group_id="grp-real-1", task=self._task())
        self.assertEqual(receipt["state"], "pending_processing")
        self.assertFalse(receipt["published"])

    def test_a14_real_adapter_refuses_a_write_without_an_approval_ref(self):
        binding, transport = self._binding([
            self._accounts_body(),
            self._members_body(),
            self._validate_body(),
        ], approval=False)
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.publish_community_task(
                binding, location_id=_TENANT, group_id="grp-real-1", task=self._task())
        self.assertEqual(ctx.exception.code, "approval_required")
        self.assertEqual([r for r in transport.requests
                          if r["method"] == "POST" and r["url"].endswith("/posts")], [])

    def test_a14_real_adapter_refuses_a_group_id_the_account_does_not_report(self):
        binding, transport = self._binding([self._accounts_body()])
        with self.assertRaises(cp.CommunityPublishError) as ctx:
            cp.publish_community_task(
                binding, location_id=_TENANT, group_id="grp-from-a-slug", task=self._task())
        self.assertEqual(ctx.exception.code, "group_id_unobserved")
        self.assertEqual(transport.requests[0]["method"], "GET")

    def test_a15_real_adapter_comment_uses_the_frozen_community_route(self):
        binding, transport = self._binding([
            _resp(200, json.dumps({"id": "comment-internal-1"}).encode()),
            _resp(200, json.dumps({"comments": [
                {"id": "comment-internal-1", "postId": "post-internal-1"}]}).encode()),
        ])
        receipt = cp.publish_community_comment(
            binding, location_id=_TENANT, post_id="post-internal-1", text="Thanks all")
        first = transport.requests[0]
        self.assertEqual(first["method"], "POST")
        self.assertEqual(first["url"], "/social-media-posting/comments/community")
        # Frozen row: the tenant rides in the query, not the path.
        self.assertEqual(first["query"], {"locationId": _TENANT})
        body = first["body"]
        self.assertEqual(body["postId"], "post-internal-1")
        self.assertEqual(body["comment"], "Thanks all")
        self.assertTrue(body["isParentThread"])
        self.assertEqual(receipt["state"], "submitted")
        self.assertIsNone(receipt["comment_id"])
        self.assertEqual(receipt["comment_id_gap"],
                         "comment_id_not_exposed_by_wf10_cp01")

if __name__ == "__main__":
    unittest.main(verbosity=2)
