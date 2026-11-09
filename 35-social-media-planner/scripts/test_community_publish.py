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

    def tearDown(self):
        self.h.cleanup()

    def _run(self, *args):
        import subprocess

        env = {
            "HOME": self.home,
            "PATH": "%s/bin:/usr/bin:/bin" % self.home,
            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        }
        return subprocess.run(
            ["bash", str(self.script), "--community-task",
             str(HERE / "community-task.example.json"),
             "--community-group-id", "grp-1", *args],
            capture_output=True, text=True, timeout=120, env=env)

    def test_a14_entrypoint_check_mode_makes_no_provider_call(self):
        p = self._run()
        self.assertEqual(p.returncode, 0, f"STDOUT:{p.stdout}\nSTDERR:{p.stderr}")
        self.assertIn('"department": "community-builder"', p.stdout)
        self.assertIn("CHECK ONLY", p.stdout)

    def test_a14_entrypoint_blocks_loudly_without_wf10_adapter(self):
        p = self._run("--community-publish")
        self.assertEqual(p.returncode, 3,
                         f"expected a loud BLOCKED, got {p.returncode}\n"
                         f"STDOUT:{p.stdout}\nSTDERR:{p.stderr}")
        self.assertIn("BLOCKED", p.stderr)
        self.assertIn("WF10-CP01", p.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)