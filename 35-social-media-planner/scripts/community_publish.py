#!/usr/bin/env python3
"""community_publish.py — Skill 35 consumer of the WF10 Community social adapter.

WHY: Skill 35 publishes an approved content calendar. Before this module it had
no way to publish INSIDE a GHL Community group: the connected Social Planner
account list was treated as one flat set of external channels, an author was
never resolved per account, and a created record was indistinguishable from a
published post. A private group therefore either went unposted or received an
external marketing post with no member identity behind it.

WHAT this module owns (and does not own):

  * it is the CONSUMER. The provider calls live in the WF10 adapter
    (`public/community_social.py`). This module never issues HTTP and never
    duplicates a route. When the adapter is absent it fails loudly with
    `CommunityAdapterUnavailable` — it never reports a fabricated success.
  * per-account author selection. Every Community account in one request needs
    its OWN member mapping: a member eligible in channel A is not eligible in
    channel B. `account.id` is stored, never `oauthId`; the author is a member
    `contactId`, never a staff user id.
  * platform-specific request splitting. A Community destination is never
    merged into the same request as an external channel, so a 280-character
    channel can never truncate a 100,000-character Community caption.
  * honest receipts. A created record, an accepted schedule and a published
    post are three different states. Only a provider status that says so plus a
    successful readback yields `published_verified`.
  * the explicit re-sync step. A brand-new group/channel is not guessed from a
    slug: the operator runs one managed re-sync, then accounts are re-queried.

WHAT this module deliberately does NOT do: answer conversations. Skill 38 owns
every reply. `assert_not_conversation_reply` refuses a task that would make
Skill 35 and Skill 38 both answer the same turn.

Usage (library, or the CLI at the bottom):
  from community_publish import publish_calendar_task
  receipt = publish_calendar_task(task, adapter=adapter, location_id=loc,
                                  group_id=group)

Assumed interface checkpoint: WF10-CP01. See `ADAPTER_METHODS` below for the
exact call surface this module consumes. A published WF10-CP01 record under
contracts/ replaces this assumption; until then the fixture in
`scripts/test_community_publish.py` is the only adapter and it is fake-only.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
CHANNEL_TABLE_PATH = os.path.join(SKILL_DIR, "config", "community-channels.json")

#: The exact WF10 adapter surface this consumer requires. A checkpoint that
#: renames or removes one of these is a contract change with a migration note.
ADAPTER_METHODS = (
    "list_accounts",            # GET /social-media-posting/{locationId}/accounts
    "list_community_members",   # GET .../community/accounts/{accountId}/users
    "validate_community_author",  # GET .../community/groups/{groupId}/users/{contactId}/validate
    "create_post",              # POST /social-media-posting/{locationId}/posts
    "get_post",                 # existing documented Social Planner post read
    "create_comment",           # POST /social-media-posting/comments/community
)

#: Post lifecycle states from the implementation contract section 11.4. Only
#: PUBLISHED_STATES prove a post exists on the destination.
CREATED_STATES = ("submitted", "draft_saved", "scheduled", "publishing")
PUBLISHED_STATES = ("published", "published_verified")
PENDING_STATES = ("pending_moderation", "processing")


class CommunityAdapterUnavailable(RuntimeError):
    """The WF10 adapter is not installed. Never a silent success."""


class CommunityPublishError(RuntimeError):
    """A preflight or lifecycle refusal. Carries a machine-readable `code`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# capability table
# ---------------------------------------------------------------------------
def load_channel_table(path: str | None = None) -> dict:
    """Read the runtime channel capability table. Fail closed on a bad file."""
    p = path or CHANNEL_TABLE_PATH
    try:
        with open(p, encoding="utf-8") as fh:
            table = json.load(fh)
    except OSError as exc:
        raise CommunityPublishError(
            "channel_table_unreadable", f"cannot read {p}: {exc}") from exc
    except ValueError as exc:
        raise CommunityPublishError(
            "channel_table_invalid", f"{p} is not valid JSON: {exc}") from exc
    limits = table.get("limits")
    if not isinstance(limits, dict) or not limits:
        raise CommunityPublishError(
            "channel_table_invalid", f"{p} carries no limits map")
    return table


def channel_limits(table: Mapping, channel: str) -> dict:
    """Return one channel's limits, or refuse the unmapped channel by name."""
    limits = (table.get("limits") or {}).get(channel)
    if not isinstance(limits, dict):
        raise CommunityPublishError(
            "channel_unmapped",
            f"{channel!r} has no row in the runtime capability table; refusing to "
            "publish it with borrowed limits")
    return limits


# ---------------------------------------------------------------------------
# adapter binding
# ---------------------------------------------------------------------------
def load_community_adapter(engine_root: str | None = None) -> Any:
    """Import the WF10 adapter module, or fail loudly.

    Search order: an explicit engine root, then the repo-relative engine path,
    then a plain import (an installed package). A missing module raises
    CommunityAdapterUnavailable naming every location searched — the caller
    must never fall back to a home-grown HTTP call here.
    """
    import importlib

    candidates = []
    roots = [engine_root] if engine_root else []
    roots.append(os.path.join(SKILL_DIR, "..", "44-convert-and-flow-operator",
                              "tools", "engine"))
    for root in roots:
        if not root:
            continue
        cleaned = os.path.abspath(root)
        if cleaned not in sys.path:
            sys.path.insert(0, cleaned)
        candidates.append(
            os.path.join(cleaned, "cli_anything", "gohighlevel", "public",
                         "community_social.py"))
    for name in ("cli_anything.gohighlevel.public.community_social",
                 "community_social"):
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        missing = [m for m in ADAPTER_METHODS if not hasattr(module, m)]
        if missing:
            raise CommunityAdapterUnavailable(
                "WF10 adapter %r is present but incomplete; missing: %s"
                % (name, ", ".join(missing)))
        return module
    raise CommunityAdapterUnavailable(
        "WF10 Community adapter not available (assumed checkpoint WF10-CP01). "
        "Searched: %s. Skill 35 will not issue a provider call itself and will "
        "not report a post it did not create." % (", ".join(candidates) or "none"))


def require_adapter(adapter: Any) -> Any:
    """Validate an injected adapter against the frozen surface."""
    missing = [m for m in ADAPTER_METHODS if not hasattr(adapter, m)]
    if missing:
        raise CommunityAdapterUnavailable(
            "adapter %r does not implement the WF10 surface; missing: %s"
            % (adapter, ", ".join(missing)))
    return adapter


# ---------------------------------------------------------------------------
# accounts and authors
# ---------------------------------------------------------------------------
def community_accounts(accounts_payload: Any) -> list[dict]:
    """Return only the Community destinations from an accounts payload.

    The documented envelope is {"success":true,"results":{"accounts":[...]}}.
    A bare list is accepted. An unrecognised envelope is an ERROR, never an
    empty result — zero accounts and an unreadable envelope are different facts.
    """
    if isinstance(accounts_payload, list):
        rows = accounts_payload
    elif isinstance(accounts_payload, Mapping):
        results = accounts_payload.get("results")
        if isinstance(results, list):
            rows = results
        elif isinstance(results, Mapping) and isinstance(results.get("accounts"), list):
            rows = results["accounts"]
        elif isinstance(accounts_payload.get("accounts"), list):
            rows = accounts_payload["accounts"]
        else:
            raise CommunityPublishError(
                "accounts_envelope_unrecognised",
                "accounts payload is not the documented {'results':{'accounts':[]}} "
                "envelope and is not a bare list")
    else:
        raise CommunityPublishError(
            "accounts_envelope_unrecognised", "accounts payload is not JSON-shaped")

    out = []
    for account in rows:
        if not isinstance(account, Mapping):
            continue
        kind = str(account.get("type") or account.get("platform") or "").strip().lower()
        if kind not in ("community", "community_group"):
            continue
        account_id = str(account.get("id") or "").strip()
        if not account_id:
            # An oauthId is not an account id and must never be substituted.
            raise CommunityPublishError(
                "account_id_missing",
                "a Community account carries no account.id (an oauthId is not an "
                "account id); refusing to post")
        out.append(dict(account))
    return out


def members_from_payload(members_payload: Any) -> tuple[list[dict], str | None]:
    """Normalise a member page into (rows, next_cursor)."""
    if isinstance(members_payload, list):
        return [dict(r) for r in members_payload if isinstance(r, Mapping)], None
    if not isinstance(members_payload, Mapping):
        raise CommunityPublishError(
            "members_envelope_unrecognised", "member payload is not JSON-shaped")
    results = members_payload.get("results")
    if isinstance(results, list):
        rows = results
    elif isinstance(results, Mapping):
        rows = results.get("users") or results.get("members") or []
    elif isinstance(members_payload.get("users"), list):
        rows = members_payload["users"]
    else:
        raise CommunityPublishError(
            "members_envelope_unrecognised",
            "member payload carries no users list and no bare results list")
    cursor = members_payload.get("nextCursor") or members_payload.get("next_cursor")
    return [dict(r) for r in rows if isinstance(r, Mapping)], (str(cursor) if cursor else None)


def select_author(
    members: Sequence[Mapping],
    *,
    explicit_contact_id: str | None = None,
    staff_user_ids: Iterable[str] = (),
) -> dict:
    """Choose the Community author for ONE account.

    Rules from the implementation contract section 11.3:
      * the author is a returned member `contactId`, never a staff user id;
      * membership is channel-specific, so the candidate list passed in is the
        only evidence accepted for this account;
      * an explicit choice must itself be an eligible member.
    """
    staff = {str(s) for s in staff_user_ids if s}
    eligible: list[dict] = []
    for row in members:
        contact_id = str(row.get("contactId") or row.get("contact_id") or "").strip()
        if not contact_id:
            continue
        if contact_id in staff:
            continue  # a staff user id is not an eligible Community member
        eligible.append({
            "contact_id": contact_id,
            "name": str(row.get("name") or row.get("displayName") or "").strip(),
        })
    if not eligible:
        raise CommunityPublishError(
            "no_eligible_member",
            "this account returned no eligible member contactId; an author can "
            "only be chosen from that channel's own member list")
    if explicit_contact_id:
        wanted = str(explicit_contact_id).strip()
        if wanted in staff:
            raise CommunityPublishError(
                "staff_id_rejected",
                f"{wanted!r} is a staff user id; a Community author must be a "
                "member contactId")
        for row in eligible:
            if row["contact_id"] == wanted:
                return row
        raise CommunityPublishError(
            "member_not_eligible_for_channel",
            f"{wanted!r} is not an eligible member of this channel; private-channel "
            "membership does not transfer between accounts")
    return eligible[0]


def resolve_account_authors(
    adapter: Any,
    location_id: str,
    accounts: Sequence[Mapping],
    *,
    selections: Mapping[str, str] | None = None,
    staff_user_ids: Iterable[str] = (),
) -> list[dict]:
    """Resolve one author per Community account, paginating each member list."""
    selections = dict(selections or {})
    resolved = []
    for account in accounts:
        account_id = str(account["id"])
        rows: list[dict] = []
        cursor = None
        pages = 0
        while True:
            page = adapter.list_community_members(location_id, account_id, cursor)
            page_rows, cursor = members_from_payload(page)
            rows.extend(page_rows)
            pages += 1
            if not cursor or pages >= 50:
                break
        author = select_author(
            rows,
            explicit_contact_id=selections.get(account_id),
            staff_user_ids=staff_user_ids,
        )
        resolved.append({
            "account_id": account_id,
            "contact_id": author["contact_id"],
            "name": author["name"],
            "platform": str(account.get("platform") or account.get("type") or ""),
        })
    return resolved


# ---------------------------------------------------------------------------
# payload building
# ---------------------------------------------------------------------------
def preflight_channel_content(
    table: Mapping,
    channel: str,
    *,
    title: str | None,
    caption: str,
    media: Sequence[Mapping],
) -> dict:
    """Enforce that channel's documented limits. Refuses; never truncates."""
    limits = channel_limits(table, channel)
    cap_max = int(limits.get("caption_max_chars") or 0)
    if cap_max and len(caption) > cap_max:
        raise CommunityPublishError(
            "caption_over_limit",
            f"{channel}: caption is {len(caption)} chars, limit {cap_max}")
    title_max = int(limits.get("title_max_chars") or 0)
    if title is not None and title_max and len(title) > title_max:
        raise CommunityPublishError(
            "title_over_limit",
            f"{channel}: title is {len(title)} chars, limit {title_max}")
    if limits.get("requires_community_details") and not (title or "").strip():
        raise CommunityPublishError(
            "title_required", f"{channel}: a Community post requires a title")
    media_max = int(limits.get("media_max_items") or 0)
    if media_max and len(media) > media_max:
        raise CommunityPublishError(
            "media_over_limit",
            f"{channel}: {len(media)} media item(s), limit {media_max}")
    for item in media:
        if not isinstance(item, Mapping) or not item.get("url") or not item.get("type"):
            raise CommunityPublishError(
                "media_item_shape",
                "each media entry must be a documented {url, type} object; a "
                "generic mediaUrls field is not accepted")
    return limits


def build_community_payload(
    *,
    authors: Sequence[Mapping],
    title: str,
    caption: str,
    media: Sequence[Mapping] = (),
    notify_all_group_members: bool = False,
    broadcast_approved: bool = False,
    status: str | None = None,
    scheduled_at: str | None = None,
) -> dict:
    """Build the documented Community post request.

    Every Community account in the request carries its own author mapping. A
    notification is never enabled without an explicit approval record.
    """
    if not authors:
        raise CommunityPublishError("no_author", "a Community post needs at least one author mapping")
    if notify_all_group_members and not broadcast_approved:
        raise CommunityPublishError(
            "broadcast_not_approved",
            "notifyAllGroupMembers requires explicit broadcast approval; a "
            "connected account is not permission to notify every member")
    post_as_user = {
        str(a["account_id"]): {"id": str(a["contact_id"]), "name": str(a.get("name") or "")}
        for a in authors
    }
    payload: dict[str, Any] = {
        "accountIds": [str(a["account_id"]) for a in authors],
        "type": "post",
        "summary": caption,
        "media": [
            {"url": str(m["url"]), "type": str(m["type"])} for m in media
        ],
        "communityPostDetails": {
            "title": title,
            "notifyAllGroupMembers": bool(notify_all_group_members),
            "postAsUser": post_as_user,
        },
    }
    if status:
        payload["status"] = status
    if scheduled_at:
        payload["scheduledAt"] = scheduled_at
    return payload


def split_by_channel(table: Mapping, task: Mapping) -> list[dict]:
    """Split one calendar task into per-channel requests.

    A Community destination is always its own request: its 100,000-character
    caption must never be cut down to a shorter co-selected channel's limit.
    External destinations keep their existing behaviour — this function does
    not invent a payload shape for them.
    """
    rows = []
    community = []
    external = []
    for account in task.get("accounts") or ():
        channel = str(account.get("channel") or account.get("platform") or "").strip().lower()
        if not channel:
            raise CommunityPublishError(
                "channel_missing", "every target account must name its channel")
        limits = channel_limits(table, channel)  # refuses an unmapped channel
        if limits.get("kind") == "community":
            community.append(dict(account))
        else:
            external.append(dict(account))
    if community:
        rows.append({"kind": "community", "channel": "community", "accounts": community})
    if external:
        rows.append({"kind": "external", "channel": "external", "accounts": external})
    if not rows:
        raise CommunityPublishError("no_accounts", "the task names no target accounts")
    return rows


# ---------------------------------------------------------------------------
# lifecycle and receipts
# ---------------------------------------------------------------------------
def receipt_state(provider_status: str | None, *, readback_ok: bool) -> str:
    """Map a provider status onto the documented lifecycle.

    A created record or an accepted schedule is NOT a published post.
    """
    status = str(provider_status or "").strip().lower()
    if status in PUBLISHED_STATES:
        return "published_verified" if readback_ok else "submitted"
    if status in CREATED_STATES:
        return status
    if status in PENDING_STATES:
        return status
    if status in ("failed", "error", "rejected"):
        return "failed"
    return "unknown_outcome"


def verify_post(adapter: Any, location_id: str, post_id: str, expected_state: str | None = None) -> dict:
    """Read the post back. A null permalink alone is not a failure."""
    read = adapter.get_post(location_id, post_id)
    if not isinstance(read, Mapping):
        return {"state": "unreadable", "checked_fields": []}
    status = str(read.get("status") or "").strip().lower()
    matched = str(read.get("id") or read.get("post_id") or "") == str(post_id)
    if expected_state and status:
        matched = matched and status == expected_state
    return {
        "state": "matched" if matched else "mismatched",
        "checked_fields": [f for f in ("id", "status") if read.get(f) is not None],
        "provider_status": status or None,
        "url": read.get("url"),
    }


def operation_key(location_id: str, group_id: str, task: Mapping) -> str:
    """Stable identity for one logical Community post.

    A duplicate callback, a retried worker or a repeated readback resolves to
    this key, so the same approved content never creates a second post.
    """
    return "community:%s:%s:%s" % (
        location_id, group_id, str(task.get("cycle_id") or task.get("topic") or ""))


def publish_community_task(
    adapter: Any,
    *,
    location_id: str,
    group_id: str,
    task: Mapping,
    table: Mapping | None = None,
    selections: Mapping[str, str] | None = None,
    staff_user_ids: Iterable[str] = (),
    broadcast_approved: bool = False,
    receipt_store: dict | None = None,
) -> dict:
    """Publish one approved Community calendar task and return its receipt.

    When a `receipt_store` is supplied, a replay of the same logical operation
    returns the recorded receipt and makes NO provider call.
    """
    require_adapter(adapter)
    table = table or load_channel_table()
    assert_not_conversation_reply(task)

    key = operation_key(location_id, group_id, task)
    if receipt_store is not None and key in receipt_store:
        recorded = dict(receipt_store[key])
        recorded["deduped"] = True
        return recorded

    if not str(group_id or "").strip():
        raise CommunityPublishError(
            "group_id_required",
            "a Community post needs the observed backend group id; a group slug "
            "is not interchangeable with it")

    accounts = [a for a in (task.get("accounts") or ())
                if str(a.get("channel") or a.get("platform") or "").lower()
                in ("community", "community_group")]
    if not accounts:
        raise CommunityPublishError(
            "no_community_accounts", "the task names no Community destination")
    # A calendar task may name the account as `account_id`; the resolver keys on
    # the provider's own `id`. Normalise once, refusing a row with neither.
    normalised = []
    for account in accounts:
        row = dict(account)
        account_id = str(row.get("id") or row.get("account_id") or "").strip()
        if not account_id:
            raise CommunityPublishError(
                "account_id_missing",
                "a Community target carries no account id; an oauthId is not an "
                "account id")
        row["id"] = account_id
        normalised.append(row)
    accounts = normalised

    title = str(task.get("title") or "")
    caption = str(task.get("caption") or "")
    media = list(task.get("media") or ())
    preflight_channel_content(table, "community", title=title, caption=caption, media=media)

    authors = resolve_account_authors(
        adapter, location_id, accounts,
        selections=selections, staff_user_ids=staff_user_ids)
    # Validate each stored author against the group's observed backend id before
    # scheduling: a member can lose access between selection and publication.
    for author in authors:
        check = adapter.validate_community_author(
            location_id, group_id, author["contact_id"])
        valid = bool(check.get("valid")) if isinstance(check, Mapping) else bool(check)
        if not valid:
            raise CommunityPublishError(
                "author_revoked",
                f"member {author['contact_id']} is no longer valid for group "
                f"{group_id}; capture the failure and repair under the approved "
                "author policy — never impersonate another member")

    payload = build_community_payload(
        authors=authors, title=title, caption=caption, media=media,
        notify_all_group_members=bool(task.get("notify_all_group_members")),
        broadcast_approved=broadcast_approved,
        status=task.get("status"), scheduled_at=task.get("scheduled_at"))

    created = adapter.create_post(location_id, payload)
    if not isinstance(created, Mapping):
        raise CommunityPublishError(
            "create_response_unrecognised", "the adapter returned no record object")
    post_id = str(created.get("id") or created.get("post_id") or "").strip()
    status = str(created.get("status") or "").strip().lower() or None
    if not post_id:
        receipt = {
            "state": "unknown_outcome",
            "operation": "community.post.create",
            "operation_key": key,
            "detail": "adapter returned a record with no post id; reconcile before retry",
            "authors": authors,
        }
        if receipt_store is not None:
            receipt_store[key] = dict(receipt)
        return receipt

    # The readback must agree with the status the create response claimed. A
    # create that says "published" while the read still says "processing" is
    # NOT a verified publication.
    readback = verify_post(adapter, location_id, post_id, expected_state=status)
    state = receipt_state(status, readback_ok=readback.get("state") == "matched")
    receipt = {
        "state": state,
        "operation": "community.post.create",
        "operation_key": key,
        "account_ids": [a["account_id"] for a in authors],
        "authors": authors,
        "post_id": post_id,
        "url": created.get("url") or readback.get("url"),
        "provider_status": status,
        "scheduled_at": task.get("scheduled_at"),
        "readback": readback,
        # A created record is never proof of publication on its own.
        "published": state == "published_verified",
    }
    if receipt_store is not None:
        receipt_store[key] = dict(receipt)
    return receipt


def comment_attachment_warning(table: Mapping | None = None) -> str:
    table = table or load_channel_table()
    limits = channel_limits(table, "community")
    if limits.get("attachment_urls_rendered") is False:
        return str(limits.get("attachment_note") or
                   "Community comment attachments are not rendered.")
    return ""


def publish_community_comment(
    adapter: Any,
    *,
    location_id: str,
    post_id: str,
    text: str,
    parent_comment_id: str | None = None,
    attach_url: str | None = None,
    notify_all_group_members: bool = False,
    broadcast_approved: bool = False,
    table: Mapping | None = None,
) -> dict:
    """Publish one Community comment.

    `post_id` is the INTERNAL post id from the create response, never a native
    platform id. `isParentThread` is true when the comment targets the post and
    false when it targets an existing comment.
    """
    require_adapter(adapter)
    table = table or load_channel_table()
    limits = channel_limits(table, "community")
    max_chars = int(limits.get("comment_max_chars") or 0)
    if max_chars and len(text) > max_chars:
        raise CommunityPublishError(
            "comment_over_limit", f"comment is {len(text)} chars, limit {max_chars}")
    if notify_all_group_members and not broadcast_approved:
        raise CommunityPublishError(
            "broadcast_not_approved",
            "notifyAllGroupMembers requires explicit broadcast approval")

    payload: dict[str, Any] = {
        "postId": str(post_id),
        "isParentThread": not bool(parent_comment_id),
        "text": text,
        "notifyAllGroupMembers": bool(notify_all_group_members),
    }
    if parent_comment_id:
        payload["commentId"] = str(parent_comment_id)
    if attach_url:
        payload["attachmentUrl"] = str(attach_url)
    created = adapter.create_comment(location_id, payload)
    comment_id = ""
    if isinstance(created, Mapping):
        comment_id = str(created.get("id") or created.get("comment_id") or "")

    warning = comment_attachment_warning(table) if attach_url else ""
    return {
        "state": "submitted" if comment_id else "unknown_outcome",
        "operation": "community.comment.create",
        "comment_id": comment_id or None,
        "is_parent_thread": payload["isParentThread"],
        # Never describe an unrendered attachment as attached.
        "attachment_rendered": bool(attach_url) and not warning,
        "attachment_warning": warning or None,
    }


# ---------------------------------------------------------------------------
# re-sync and ownership guards
# ---------------------------------------------------------------------------
def resync_required(accounts: Sequence[Mapping], requested_group_slug: str | None) -> bool:
    """True when a new group/channel has no connected account yet.

    A slug is never converted into an account id: an account that is not in the
    connected list means the channel needs the managed re-sync step.
    """
    if not requested_group_slug:
        return False
    wanted = str(requested_group_slug).strip().lower()
    for account in accounts:
        slugs = {
            str(account.get("groupId") or "").strip().lower(),
            str(account.get("groupSlug") or account.get("slug") or "").strip().lower(),
            str(account.get("name") or "").strip().lower(),
        }
        if wanted and wanted in slugs:
            return False
    return True


def sync_then_requery(
    adapter: Any,
    location_id: str,
    *,
    group_slug: str | None = None,
    run_resync=None,
) -> dict:
    """Explicit re-sync step: connect/re-sync, THEN re-query accounts.

    Returns the observed post-resync account list plus what happened, so the
    caller can name the setup step instead of guessing an account id.
    """
    before = community_accounts(adapter.list_accounts(location_id))
    needs = resync_required(before, group_slug)
    if not needs:
        return {"resync_performed": False, "accounts": before,
                "reason": "channel already connected"}
    if run_resync is None:
        raise CommunityPublishError(
            "resync_step_required",
            "this group/channel is not connected in Social Planner yet. Run the "
            "managed connection/re-sync step first, then re-query accounts. An "
            "account id is never derived from a group slug.")
    run_resync(location_id)
    after = community_accounts(adapter.list_accounts(location_id))
    if resync_required(after, group_slug):
        raise CommunityPublishError(
            "resync_incomplete",
            "after the managed re-sync the requested channel still has no "
            "connected account; setup is not complete")
    return {"resync_performed": True, "accounts": after,
            "reason": "managed re-sync completed and accounts re-queried"}


def assert_not_conversation_reply(task: Mapping) -> None:
    """Skill 38 owns conversations. Refuse a task that would double-answer."""
    intent = str(task.get("intent") or "").strip().lower()
    if intent in ("reply", "conversation_reply", "answer_comment"):
        raise CommunityPublishError(
            "conversation_owned_by_skill_38",
            "an inbound Community reply belongs to Skill 38's single-responder "
            "pipeline; Skill 35 publishes approved content and never answers")


def route_department(task: Mapping) -> str:
    """Community Builder owns inside-group intent; Social Media executes."""
    scope = str(task.get("scope") or "").strip().lower()
    if scope in ("community", "inside_group", "group"):
        return "community-builder"
    return "social-media"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main(argv: Sequence[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Skill 35 Community publishing consumer (WF11).")
    ap.add_argument("--task", required=True, help="approved Community calendar task JSON file")
    ap.add_argument("--location-id", required=True)
    ap.add_argument("--group-id", required=True, help="observed backend group id")
    ap.add_argument("--engine-root", default=None)
    ap.add_argument("--check", action="store_true", help="validate only; no provider call")
    args = ap.parse_args(argv)

    try:
        table = load_channel_table()
        with open(args.task, encoding="utf-8") as fh:
            task = json.load(fh)
    except (OSError, ValueError, CommunityPublishError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.check:
        print(json.dumps({"ok": True, "department": route_department(task), "limits":
                          channel_limits(table, "community")}, indent=2))
        return 0
    try:
        adapter = load_community_adapter(args.engine_root)
    except CommunityAdapterUnavailable as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 3
    try:
        receipt = publish_community_task(
            adapter, location_id=args.location_id, group_id=args.group_id,
            task=task, table=table)
    except CommunityAdapterUnavailable as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 3
    except CommunityPublishError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4
    print(json.dumps(receipt, indent=2))
    return 0 if receipt.get("published") else 5


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
