"""U88/GK-26 regression -- `caf social create-post` / `caf social posts`.

Found LIVE on the operator's own box, 2026-07-19, running the real GK-26
content->conversation loop end to end (never caught by any fixture/mock, since
`FixtureAdapters` in `35-social-media-planner/scripts/prove_content_conversation_loop.py`
never calls the real API by design -- this suite is what closes that blind spot):

  1. The original request body for `POST /social-media-posting/{loc}/posts`
     included a redundant `locationId` key and omitted `type`/`userId`/`media`
     -- the real API 422s with:
       ['property locationId should not exist', 'media must be an array with
        media objects or an empty array', 'Post Type must be one of the
        following values: - post, story, reel', 'type should not be empty',
        'userId must be a string', 'userId should not be empty']
  2. Omitting `--schedule` does NOT create a draft -- the real API PUBLISHES
     THE POST IMMEDIATELY AND PUBLICLY on the real connected account
     (confirmed live: a real post went live on a real Facebook page in ~17s).
     GHL's own DELETE endpoint for that already-published post returned
     `success:true` / `"Deleted Post"` but did NOT actually retract it --
     re-reading the same post repeatedly over 5+ minutes still showed
     `deleted:false`, `status:"published"`. This is now a fail-closed refusal
     (--status draft, --schedule, or --confirm-publish-now is required) so it
     can never happen silently again.
  3. `POST /social-media-posting/{loc}/posts/list` also 422s on a redundant
     `locationId` key, and requires `limit`/`skip` as NUMBER STRINGS, not
     JSON integers ("property X must be a number string").
  4. RE-RUN (2026-07-19, same day, U88/GK-26 leg-2 redo): the first fix's own
     `--schedule` path used the wrong field name (`scheduledAt`) -- the real
     API 422'd with 'property scheduledAt should not exist'. Sourced research
     (GHL's own marketplace API docs body-field list, cross-confirmed against
     a real third-party GHL integration app targeting this same endpoint)
     found the correct field is `scheduleDate`, AND a dedicated `status` body
     field (`draft` / `scheduled` / `published`) that is the real, documented
     mechanism for a genuinely non-publishing draft. `--status draft` is now
     the recommended safe path -- it satisfies the fail-closed gate on its
     own, sends no `scheduleDate`, and was independently read back live
     showing `"status": "draft"` (never published) before being deleted and
     re-confirmed gone.

Every test here uses mocks only -- NO live CRM is ever contacted (guarded by
the same socket-level connect guard `test_ecosystem_cli.py` uses).

Run:
    python3 -m pytest tools/engine/tests/test_u88_social_create_post.py -v
"""
from __future__ import annotations

import os
import socket
import sys
import unittest
from unittest.mock import patch

# ── Ensure engine root is on sys.path ─────────────────────────────────────────
_ENGINE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

# ── Network guard — any connect to leadconnectorhq.com is a hard FAIL ─────────
_BLOCKED_HOST = "leadconnectorhq.com"
_original_connect = socket.socket.connect


def _guarded_connect(self, address):
    if isinstance(address, tuple):
        host = address[0]
        if _BLOCKED_HOST in str(host):
            raise AssertionError(
                f"SAFETY FAILURE: live CRM host contacted: {host!r}. "
                "All tests must use mocks — no live API calls."
            )
    return _original_connect(self, address)


socket.socket.connect = _guarded_connect

LOC = "TESTLOCATION00000001"  # fake fixture location id (mock-only)
ACCOUNT_ID = "fakeoauth_TESTLOCATION00000001_1234567890_page"
POST_USER_ID = "fake-integration-user-id-0001"


def _approved_env():
    os.environ["GHL_API_KEY"] = "fake-pit-token"
    os.environ["GHL_LOCATION_ID"] = LOC
    os.environ["CAF_ALLOWED_LOCATION_IDS"] = LOC
    os.environ["CAF_APPROVAL_TOKEN"] = "test-approval"
    os.environ.pop("CAF_DRY_RUN", None)


def _clear_env():
    for k in ("GHL_API_KEY", "GHL_LOCATION_ID", "CAF_ALLOWED_LOCATION_IDS",
              "CAF_APPROVAL_TOKEN", "CAF_DRY_RUN", "CAF_DRAFT_ONLY"):
        os.environ.pop(k, None)


class _PatchedApiBase(unittest.TestCase):
    def setUp(self):
        _approved_env()

    def tearDown(self):
        _clear_env()

    def _invoke(self, args, post_return=None):
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli.api.post",
            return_value=post_return or {"success": True},
        ) as mock_post:
            runner = CliRunner()
            result = runner.invoke(cli, args)
        return result, mock_post


# ── (1)+(3): fixed body shapes ────────────────────────────────────────────────

class TestSocialCreatePostBodyShape(_PatchedApiBase):
    """The real 422 is reproduced by asserting the OLD shape is gone and the
    fields the real API demanded are present."""

    def test_confirm_publish_now_sends_required_fields_no_location_id(self):
        result, mock_post = self._invoke([
            "--json", "--location-id", LOC,
            "social", "create-post",
            "--account-id", ACCOUNT_ID,
            "--text", "hello world",
            "--post-user-id", POST_USER_ID,
            "--confirm-publish-now",
        ], post_return={"id": "post-1"})

        self.assertEqual(result.exit_code, 0, f"Exit code must be 0. Output: {result.output}")
        mock_post.assert_called_once()
        _path, kwargs = mock_post.call_args[0], mock_post.call_args[1]
        body = kwargs.get("data")
        self.assertNotIn("locationId", body, "locationId must NOT be in the body (real 422 cause)")
        self.assertEqual(body.get("type"), "post")
        self.assertEqual(body.get("media"), [])
        self.assertEqual(body.get("userId"), POST_USER_ID)
        self.assertEqual(body.get("accountIds"), [ACCOUNT_ID])
        self.assertEqual(body.get("summary"), "hello world")

    def test_media_url_becomes_media_objects(self):
        result, mock_post = self._invoke([
            "--json", "--location-id", LOC,
            "social", "create-post",
            "--account-id", ACCOUNT_ID,
            "--text", "hello",
            "--post-user-id", POST_USER_ID,
            "--media-url", "https://example.com/a.jpg",
            "--confirm-publish-now",
        ], post_return={"id": "post-2"})
        self.assertEqual(result.exit_code, 0, result.output)
        body = mock_post.call_args[1].get("data")
        self.assertEqual(body.get("media"), [{"url": "https://example.com/a.jpg", "type": "image"}])


class TestSocialPostsListBodyShape(_PatchedApiBase):
    def test_limit_skip_are_number_strings_and_no_location_id(self):
        result, mock_post = self._invoke([
            "--json", "--location-id", LOC,
            "social", "posts", "--limit", "7", "--offset", "3",
        ], post_return={"results": {"posts": []}})

        self.assertEqual(result.exit_code, 0, result.output)
        body = mock_post.call_args[1].get("data")
        self.assertNotIn("locationId", body, "locationId must NOT be in the body (real 422 cause)")
        self.assertEqual(body.get("limit"), "7")
        self.assertIsInstance(body.get("limit"), str)
        self.assertEqual(body.get("skip"), "3")
        self.assertIsInstance(body.get("skip"), str)


# ── (2): fail-closed refusal — the safety-critical regression ────────────────

class TestSocialCreatePostFailClosed(_PatchedApiBase):
    """Omitting --schedule used to silently publish immediately with no draft
    state and no reliable way to undo it (confirmed live). It must now be
    refused unless --confirm-publish-now is explicitly passed."""

    def test_no_schedule_no_confirm_is_refused_before_any_network_call(self):
        result, mock_post = self._invoke([
            "--location-id", LOC,
            "social", "create-post",
            "--account-id", ACCOUNT_ID,
            "--text", "hello world",
            "--post-user-id", POST_USER_ID,
        ])
        self.assertNotEqual(result.exit_code, 0,
                             "Missing --schedule/--confirm-publish-now must be refused")
        mock_post.assert_not_called()
        self.assertIn("REFUSED", result.output + (str(result.exception) or ""))

    def test_missing_post_user_id_is_refused_before_any_network_call(self):
        result, mock_post = self._invoke([
            "--location-id", LOC,
            "social", "create-post",
            "--account-id", ACCOUNT_ID,
            "--text", "hello world",
            "--confirm-publish-now",
        ])
        self.assertNotEqual(result.exit_code, 0,
                             "Missing --post-user-id must be refused")
        mock_post.assert_not_called()

    def test_confirm_publish_now_alone_is_accepted(self):
        """--confirm-publish-now with no --schedule is the explicit, intentional
        opt-in path and must proceed (this is the pre-existing, now-explicit,
        immediate-publish behavior — not a regression, a documented choice)."""
        result, mock_post = self._invoke([
            "--json", "--location-id", LOC,
            "social", "create-post",
            "--account-id", ACCOUNT_ID,
            "--text", "hello world",
            "--post-user-id", POST_USER_ID,
            "--confirm-publish-now",
        ], post_return={"id": "post-3"})
        self.assertEqual(result.exit_code, 0, result.output)
        mock_post.assert_called_once()


# ── (4): --status draft / fixed --schedule field name — the 2026-07-19 leg-2 redo ─

class TestSocialCreatePostStatusDraft(_PatchedApiBase):
    """`--status draft` is the sourced, safe, non-publishing path (real API's own
    `status` field, docs example value `draft`). It must satisfy the fail-closed
    gate on its own -- no --schedule, no --confirm-publish-now required."""

    def test_status_draft_alone_is_accepted_and_sends_status_draft(self):
        result, mock_post = self._invoke([
            "--json", "--location-id", LOC,
            "social", "create-post",
            "--account-id", ACCOUNT_ID,
            "--text", "hello world",
            "--post-user-id", POST_USER_ID,
            "--status", "draft",
        ], post_return={"id": "post-draft-1"})
        self.assertEqual(result.exit_code, 0, result.output)
        mock_post.assert_called_once()
        body = mock_post.call_args[1].get("data")
        self.assertEqual(body.get("status"), "draft")
        self.assertNotIn("scheduleDate", body, "a draft must not carry a scheduleDate")

    def test_status_draft_does_not_require_schedule_or_confirm(self):
        result, mock_post = self._invoke([
            "--location-id", LOC,
            "social", "create-post",
            "--account-id", ACCOUNT_ID,
            "--text", "hello world",
            "--post-user-id", POST_USER_ID,
            "--status", "draft",
        ])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_post.assert_called_once()

    def test_schedule_sends_scheduleDate_not_scheduledAt_and_implies_status_scheduled(self):
        """FIX: the real API 422'd on `scheduledAt` ('property scheduledAt should not
        exist'). The correct field, sourced from GHL's own docs + a real third-party
        integration app, is `scheduleDate`."""
        result, mock_post = self._invoke([
            "--json", "--location-id", LOC,
            "social", "create-post",
            "--account-id", ACCOUNT_ID,
            "--text", "hello world",
            "--post-user-id", POST_USER_ID,
            "--schedule", "2027-01-01T12:00:00Z",
        ], post_return={"id": "post-sched-1"})
        self.assertEqual(result.exit_code, 0, result.output)
        body = mock_post.call_args[1].get("data")
        self.assertEqual(body.get("scheduleDate"), "2027-01-01T12:00:00Z")
        self.assertNotIn("scheduledAt", body, "the old, real-API-422ing field name must be gone")
        self.assertEqual(body.get("status"), "scheduled")

    def test_schedule_with_contradictory_status_is_refused(self):
        result, mock_post = self._invoke([
            "--location-id", LOC,
            "social", "create-post",
            "--account-id", ACCOUNT_ID,
            "--text", "hello world",
            "--post-user-id", POST_USER_ID,
            "--schedule", "2027-01-01T12:00:00Z",
            "--status", "draft",
        ])
        self.assertNotEqual(result.exit_code, 0,
                             "--schedule + --status draft is contradictory and must be refused")
        mock_post.assert_not_called()

    def test_no_status_no_schedule_no_confirm_is_still_refused(self):
        """The fail-closed gate now has three doors (draft / schedule / confirm) but
        must still refuse when none of the three is opened."""
        result, mock_post = self._invoke([
            "--location-id", LOC,
            "social", "create-post",
            "--account-id", ACCOUNT_ID,
            "--text", "hello world",
            "--post-user-id", POST_USER_ID,
        ])
        self.assertNotEqual(result.exit_code, 0)
        mock_post.assert_not_called()
        self.assertIn("REFUSED", result.output + (str(result.exception) or ""))


if __name__ == "__main__":
    unittest.main()
