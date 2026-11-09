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
#: WF10's PostLifecycle names the in-flight state `pending_processing`; the
#: provider status literal is `processing`. Both are the same non-success fact.
PENDING_STATES = ("pending_moderation", "processing", "pending_processing")
#: Lifecycle values that come straight from a WF10 PostReceipt.
WF10_LIFECYCLES = tuple(sorted(
    set(CREATED_STATES) | set(PUBLISHED_STATES) | set(PENDING_STATES) | {"failed"}
))


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
#: The published WF10 module (WF10-CP01). Skill 35 never re-implements it.
WF10_MODULE_NAME = "cli_anything.gohighlevel.public.community_social"
#: The published surface this consumer binds to. Checked before any call so a
#: renamed or removed symbol is a loud failure, never a half-bound adapter.
WF10_SURFACE = (
    "CommunitySocialAdapter",   # the typed adapter class (not module functions)
    "ConnectedAccount",
    "AuthorMapping",
    "PlatformRequest",
    "CommentPlan",
    "build_community_post",
    "build_comment",
    "PostLifecycle",
    "OPERATION_IDS",
)

def _operation_short(operation_id: str) -> str:
    """The frozen key prefix for one operation id (GU-004 section 2.4)."""
    import re
    short = re.sub(r"[^a-z0-9]+", "-", str(operation_id or "").lower()).strip("-")
    short = re.sub(r"-{2,}", "-", short)[:32].strip("-")
    return short or "op"

def idempotency_key_for(operation_id: str, logical_key: str) -> str:
    """A valid, deterministic WF10 idempotency key for one logical operation.

    The adapter refuses any key outside ``gxo_<op-short>-<32 hex>``, so the
    consumer's stable logical identity is hashed into that format. The same
    logical operation therefore reuses the same key and a replay is deduped.
    """
    import hashlib
    digest = hashlib.sha256(str(logical_key or "").encode("utf-8")).hexdigest()[:32]
    return "gxo_%s-%s" % (_operation_short(operation_id), digest)

def wf10_surface_gaps(module: Any) -> list[str]:
    """Symbols the published WF10 module does not expose."""
    return [name for name in WF10_SURFACE if not hasattr(module, name)]

def import_wf10_module(engine_root: str | None = None) -> Any:
    """Import the published WF10 module, or fail loudly naming every path tried.

    An explicit ``engine_root`` means that root only: a caller that names a root
    is asking a question about THAT tree, so silently falling back to a sibling
    checkout would answer a different question. With no explicit root the
    repo-relative engine tree is searched, then a plain package import.
    """
    import importlib

    roots = ([engine_root] if engine_root
             else [os.path.join(SKILL_DIR, "..", "44-convert-and-flow-operator",
                                "tools", "engine")])
    searched = []
    for root in roots:
        cleaned = os.path.abspath(root)
        if cleaned not in sys.path:
            sys.path.insert(0, cleaned)
        searched.append(os.path.join(
            cleaned, "cli_anything", "gohighlevel", "public", "community_social.py"))
    names = [WF10_MODULE_NAME]
    if engine_root is None:
        names.append("community_social")
    root = os.path.abspath(engine_root) if engine_root else None
    for name in names:
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        # An explicit root is a question about THAT tree. A module already in
        # sys.modules from another checkout must not answer it.
        if root is not None:
            origin = os.path.abspath(str(getattr(module, "__file__", "") or ""))
            if not origin.startswith(root + os.sep):
                continue
        gaps = wf10_surface_gaps(module)
        if gaps:
            raise CommunityAdapterUnavailable(
                "WF10 adapter %r is present but does not expose the published "
                "surface; missing: %s" % (name, ", ".join(gaps)))
        return module
    raise CommunityAdapterUnavailable(
        "WF10 Community adapter not available (published checkpoint WF10-CP01). "
        "Searched: %s. Skill 35 will not issue a provider call itself and will "
        "not report a post it did not create." % ", ".join(searched))

def _public_modules(module: Any) -> tuple:
    """The WF10 package's own auth/adapter classes, imported from ITS tree."""
    from cli_anything.gohighlevel.public.adapter import (  # type: ignore
        ApprovalRef, PublicGhlAdapter)
    from cli_anything.gohighlevel.public.auth import (  # type: ignore
        AuthKind, TenantBinding, resolve_auth, resolve_tenant_from_env)
    del module  # the package import is the authority; the module only proves it
    return ApprovalRef, PublicGhlAdapter, AuthKind, TenantBinding, resolve_auth, resolve_tenant_from_env

class Wf10CommunityAdapter:
    """The consumer seam, implemented over the published WF10 adapter.

    Skill 35 keeps its own request splitting, author selection and receipt
    vocabulary. This class translates between that seam and the typed WF10
    surface, so every provider call — row, tenant binding, auth class,
    idempotency, approval, readback, capability gate — stays WF10's.
    """

    def __init__(self, module: Any, adapter: Any, tenant: Any, *,
                 approval: Any = None) -> None:
        self.module = module
        self.adapter = adapter
        self.tenant = tenant
        self.approval = approval
        self._accounts: dict[str, Any] = {}

    # -- accounts --------------------------------------------------------
    def _refresh_accounts(self) -> list:
        result, accounts = self.adapter.list_community_accounts(tenant=self.tenant)
        if result.status.value != "ok":
            raise CommunityPublishError(
                "accounts_read_failed",
                "the Community connected-account read did not succeed (%s, "
                "receipt %s); it is not an empty account list"
                % (result.status.value, result.receipt_id))
        self._accounts = {account.account_id: account for account in accounts}
        return list(self._accounts.values())

    @staticmethod
    def _account_row(account: Any) -> dict:
        row = {
            "id": account.account_id,
            "platform": account.platform,
            "type": account.platform,
            "name": account.name or "",
            "kind": "community",
        }
        if account.group_id:
            row["groupId"] = account.group_id
        if account.oauth_id:
            row["oauthId"] = account.oauth_id
        return row

    def list_accounts(self, location_id: str | None = None,
                      cursor: str | None = None) -> dict:
        accounts = self._refresh_accounts()
        return {"success": True,
                "results": {"accounts": [self._account_row(a) for a in accounts]}}

    def _account(self, account_id: str) -> Any:
        wanted = str(account_id or "").strip()
        if wanted not in self._accounts:
            self._refresh_accounts()
        if wanted not in self._accounts:
            raise CommunityPublishError(
                "account_not_connected",
                "%r is not a connected Community channel account of this "
                "location; select one from the connected-account listing — an "
                "account id is never derived from a group slug" % wanted)
        return self._accounts[wanted]

    def require_observed_group(self, group_id: str) -> None:
        """Refuse a group id no connected account reports."""
        self._account_for_group(group_id)

    def _account_for_group(self, group_id: str) -> Any:
        wanted = str(group_id or "").strip()
        if not wanted:
            raise CommunityPublishError(
                "group_id_required",
                "a Community write needs the observed backend group id; a group "
                "slug is not interchangeable with it")
        if not self._accounts:
            self._refresh_accounts()
        matches = [a for a in self._accounts.values() if a.group_id == wanted]
        if not matches:
            self._refresh_accounts()
            matches = [a for a in self._accounts.values() if a.group_id == wanted]
        if not matches:
            raise CommunityPublishError(
                "group_id_unobserved",
                "no connected Community account reports backend group id %r; "
                "read account.meta.groupId from the connected-account listing "
                "and re-sync the channel before publishing" % wanted)
        return matches[0]

    # -- members ---------------------------------------------------------
    def list_community_members(self, location_id: str, account_id: str,
                               cursor: str | None = None) -> dict:
        account = self._account(account_id)
        page = int(cursor) if str(cursor or "").strip() else 1
        result, page_result = self.adapter.list_members(
            tenant=self.tenant, account=account, page=page)
        if result.status.value != "ok":
            raise CommunityPublishError(
                "members_read_failed",
                "the member list for account %s did not succeed (%s, receipt %s)"
                % (account_id, result.status.value, result.receipt_id))
        rows = [{"contactId": member.contact_id, "name": member.name or ""}
                for member in page_result.members]
        return {"results": {"users": rows},
                "nextCursor": (str(page + 1) if page_result.has_more else None)}

    def validate_community_author(self, location_id: str, group_id: str,
                                  contact_id: str) -> dict:
        account = self._account_for_group(group_id)
        result, validation = self.adapter.validate_author(
            tenant=self.tenant, account=account, contact_id=contact_id)
        return {"valid": validation.state == "valid",
                "state": validation.state,
                "group_id": validation.group_id,
                "contact_id": validation.contact_id,
                "provider_status": result.status.value,
                "http_status": validation.http_status,
                "receipt_id": validation.receipt_id}

    # -- writes ----------------------------------------------------------
    def _require_approval(self) -> Any:
        if self.approval is None:
            raise CommunityPublishError(
                "approval_required",
                "the WF10 write seam needs an approval reference; pass the "
                "Purple approval manifest (--approval-ref) so the adapter "
                "records who approved this publication")
        return self.approval

    def create_post(self, location_id: str, payload: Mapping) -> dict:
        approval = self._require_approval()
        account_ids = [str(item) for item in payload.get("accountIds") or ()]
        if not account_ids:
            raise CommunityPublishError(
                "no_community_accounts", "the request names no account id")
        accounts = [self._account(account_id) for account_id in account_ids]
        details = payload.get("communityPostDetails") or {}
        post_as_user = details.get("postAsUser") or {}
        authors = []
        for account_id in account_ids:
            entry = post_as_user.get(account_id) or {}
            contact = str(entry.get("id") or "").strip()
            if not contact:
                raise CommunityPublishError(
                    "author_missing",
                    "account %s carries no member contactId; every Community "
                    "account needs its own author mapping" % account_id)
            authors.append(self.module.AuthorMapping(
                account_id=account_id, contact_id=contact,
                name=str(entry.get("name") or "") or None))
        plan = self.module.build_community_post(
            accounts=accounts,
            authors=authors,
            title=details.get("title"),
            caption=payload.get("summary"),
            media=payload.get("media") or (),
            status=str(payload.get("status") or "draft"),
            schedule_date=payload.get("scheduledAt") or payload.get("scheduleDate"),
            notify_all_group_members=bool(details.get("notifyAllGroupMembers")),
            broadcast_approved=bool(payload.get("broadcast_approved")))
        community = [r for r in plan.platform_requests() if r.is_community]
        receipt = self.adapter.create_post(
            tenant=self.tenant, request=community[0], approval=approval,
            idempotency_key=idempotency_key_for(
                self.module.OPERATION_IDS["posts.create"],
                str(payload.get("idempotency_key") or "")))
        return {"id": None,
                "status": None,
                "lifecycle": receipt.lifecycle.value,
                "receipt_id": receipt.result.receipt_id,
                "http_status": receipt.result.http_status,
                "deduplicated": receipt.deduplicated,
                # The published WF10 receipt carries the lifecycle and the
                # receipt id, not the created provider post id. Named here so a
                # caller never receives a fabricated one.
                "post_id_gap": "post_id_not_exposed_by_wf10_cp01"}

    def get_post(self, location_id: str, post_id: str) -> dict:
        """Read a post back. The published WF10 surface exposes no post read.

        `create_post` already judged the readback and returned a lifecycle, so
        the consumer never needs a second read. A caller that asks anyway gets a
        named gap instead of a value this adapter cannot prove.
        """
        raise CommunityPublishError(
            "post_read_unavailable",
            "the published WF10-CP01 surface (CommunitySocialAdapter) exposes no "
            "single-post read; the create receipt's lifecycle is the readback. "
            "Recorded as change-requests/wf11/2.md")

    def create_comment(self, location_id: str, payload: Mapping) -> dict:
        approval = self._require_approval()
        attach = str(payload.get("attachmentUrl") or "").strip()
        plan = self.module.build_comment(
            post_id=payload.get("postId"),
            text=payload.get("text"),
            is_parent_thread=bool(payload.get("isParentThread", True)),
            parent_comment_id=payload.get("commentId"),
            notify_all_group_members=bool(payload.get("notifyAllGroupMembers")),
            broadcast_approved=bool(payload.get("broadcast_approved")),
            attachments=(attach,) if attach else ())
        receipt = self.adapter.create_comment(
            tenant=self.tenant, plan=plan, approval=approval,
            idempotency_key=idempotency_key_for(
                self.module.OPERATION_IDS["comments.create"],
                str(payload.get("idempotency_key") or "")))
        return {"id": None,
                "provider_status": receipt.result.status.value,
                "receipt_id": receipt.result.receipt_id,
                "http_status": receipt.result.http_status,
                "attachments_rendered": receipt.attachments_rendered,
                "comment_id_gap": "comment_id_not_exposed_by_wf10_cp01"}

def bind_community_adapter(module: Any, adapter: Any, tenant: Any, *,
                           approval: Any = None) -> Wf10CommunityAdapter:
    """Bind an injected WF10 adapter instance (tests and callers that own auth)."""
    gaps = wf10_surface_gaps(module)
    if gaps:
        raise CommunityAdapterUnavailable(
            "WF10 module does not expose the published surface; missing: %s"
            % ", ".join(gaps))
    return Wf10CommunityAdapter(module, adapter, tenant, approval=approval)

def load_community_adapter(engine_root: str | None = None, *,
                           adapter: Any = None,
                           location_id: str | None = None,
                           approval_ref: str | None = None) -> Wf10CommunityAdapter:
    """Import WF10 and return the live, bound consumer adapter.

    With no injected ``adapter`` the live surface is constructed exactly as the
    WF10 command module constructs it (location PIT auth + the frozen registry).
    A missing token, tenant or published symbol raises
    ``CommunityAdapterUnavailable`` — the caller prints BLOCKED and publishes
    nothing.
    """
    module = import_wf10_module(engine_root)
    ApprovalRef, PublicGhlAdapter, AuthKind, TenantBinding, resolve_auth,         resolve_tenant_from_env = _public_modules(module)
    try:
        if location_id:
            tenant = TenantBinding(location_id=str(location_id),
                                   source="skill35:--location-id")
        else:
            tenant = resolve_tenant_from_env()
    except Exception as exc:  # noqa: BLE001 - no tenant is a loud block
        raise CommunityAdapterUnavailable(
            "WF10 adapter cannot bind a tenant: %s: %s. Set "
            "--location-id or GOHIGHLEVEL_LOCATION_ID." % (type(exc).__name__, exc)
        ) from exc
    if adapter is None:
        try:
            auth = resolve_auth(kind=AuthKind.location_pit,
                                location_id=tenant.location_id)
            adapter = module.CommunitySocialAdapter(
                public=PublicGhlAdapter(auth=auth))
        except Exception as exc:  # noqa: BLE001 - no auth is a loud block
            raise CommunityAdapterUnavailable(
                "WF10 adapter cannot bind auth for location %s: %s: %s"
                % (tenant.location_id, type(exc).__name__, exc)) from exc
    approval = None
    if approval_ref:
        approval = ApprovalRef(ref=str(approval_ref), kind="approval_record")
    return bind_community_adapter(module, adapter, tenant, approval=approval)

def require_adapter(adapter: Any) -> Any:
    """Validate an injected adapter against the frozen consumer seam."""
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

    # Refuse a group id the connected account does not report BEFORE spending a
    # member read on it: a slug is not a backend group id.
    group_check = getattr(adapter, "require_observed_group", None)
    if callable(group_check):
        group_check(group_id)

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
    # Two facts the WF10 write seam reads and this consumer already proved.
    payload["broadcast_approved"] = bool(broadcast_approved)
    payload["idempotency_key"] = key

    created = adapter.create_post(location_id, payload)
    if not isinstance(created, Mapping):
        raise CommunityPublishError(
            "create_response_unrecognised", "the adapter returned no record object")
    post_id = str(created.get("id") or created.get("post_id") or "").strip()
    lifecycle = str(created.get("lifecycle") or "").strip().lower() or None
    status = lifecycle or str(created.get("status") or "").strip().lower() or None

    if lifecycle:
        # The WF10 receipt already judged create + readback and reported which
        # lifecycle fact it observed. A second local readback would re-ask the
        # same question through a surface that does not expose it.
        readback = {"state": "matched"
                    if lifecycle == "published_verified" else "not_required",
                    "source": "wf10_post_receipt",
                    "checked_fields": []}
        state = receipt_state(lifecycle, readback_ok=lifecycle == "published_verified")
    elif post_id:
        # The readback must agree with the status the create response claimed. A
        # create that says "published" while the read still says "processing" is
        # NOT a verified publication.
        readback = verify_post(adapter, location_id, post_id, expected_state=status)
        state = receipt_state(status, readback_ok=readback.get("state") == "matched")
    else:
        readback = {"state": "unavailable", "checked_fields": [],
                    "source": "no_create_record_and_no_post_id"}
        state = "unknown_outcome"

    receipt = {
        "state": state,
        "operation": "community.post.create",
        "operation_key": key,
        "account_ids": [a["account_id"] for a in authors],
        "authors": authors,
        # None is honest: the published WF10 receipt does not expose the created
        # provider post id. A caller that needs it reconciles against the
        # provider listing; Skill 35 never invents one.
        "post_id": post_id or None,
        "post_id_gap": created.get("post_id_gap"),
        "provider_receipt_id": created.get("receipt_id"),
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
        "broadcast_approved": bool(broadcast_approved),
    }
    if parent_comment_id:
        payload["commentId"] = str(parent_comment_id)
    if attach_url:
        payload["attachmentUrl"] = str(attach_url)
    created = adapter.create_comment(location_id, payload)
    comment_id = ""
    provider_status = None
    if isinstance(created, Mapping):
        comment_id = str(created.get("id") or created.get("comment_id") or "")
        provider_status = str(created.get("provider_status") or "").strip().lower() or None

    warning = comment_attachment_warning(table) if attach_url else ""
    if comment_id:
        state = "submitted"
    elif provider_status == "ok":
        # The provider accepted the comment; the published receipt carries no
        # comment id, so the outcome is accepted-but-unidentified, not unknown.
        state = "submitted"
    elif provider_status == "unknown_outcome":
        state = "unknown_outcome"
    elif provider_status:
        state = "failed"
    else:
        state = "unknown_outcome"
    return {
        "state": state,
        "operation": "community.comment.create",
        "comment_id": comment_id or None,
        "comment_id_gap": (created.get("comment_id_gap")
                           if isinstance(created, Mapping) else None),
        "provider_status": provider_status,
        "provider_receipt_id": (created.get("receipt_id")
                                if isinstance(created, Mapping) else None),
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
    ap.add_argument("--approval-ref", default=None,
                    help="approval record reference (the Purple approval manifest path)")
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
        adapter = load_community_adapter(
            args.engine_root, location_id=args.location_id,
            approval_ref=args.approval_ref)
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
