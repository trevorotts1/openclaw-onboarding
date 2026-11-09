"""Community social adapter: members, Community posts and comments (WF10).

Contract: Document 1 (BLACKCEO GHL Hybrid Implementation Spec v3.0) sections
3.3 and 11.1-11.6, plus the companion runbook assignment WF10.  Every request
goes through ``PublicGhlAdapter.call`` so the frozen operation row, tenant
binding, auth class, idempotency, approval, readback and capability gate stay
the ones the rest of Skill 44 uses.  This module adds no second dispatch
authority and never invents a version, a scope or a path.

Three Community routes that Document 1 section 11.2 names are frozen in
``public/operations.py`` by WF00-CP01 (WF00 owns that file).  The ids WF00
froze are the authority; this module's earlier assumed ids were reconciled to
them (WF11 integration, change request ``change-requests/wf11/2.md``):

    social.community.accounts.users.list
        GET /social-media-posting/{locationId}/community/accounts/{accountId}/users
        scope socialplanner/oauth.readonly
    social.community.authors.validate
        GET /social-media-posting/{locationId}/community/groups/{groupId}/users/{contactId}/validate
        scope socialplanner/account.readonly
    social.community.comments.create
        POST /social-media-posting/comments/community?locationId=...
        scope socialplanner/comments.write

Path, version, auth class, scope candidate, tenant binding (``query.locationId``
for the comment create) and readback are the frozen rows verbatim.  A row that
is missing at run time still raises ``CommunitySocialGap`` naming the exact
operation id — nothing here fakes a result.

Identity rules this module enforces (Document 1 sections 3.3 and 11.3):

* the channel account is ``account.id``; ``oauthId`` is never used as the key;
* the author is a Community member ``contactId``; a staff user id is refused;
* membership is validated with the observed backend group id
  (``account.meta.groupId``), never with the portal slug or the account id;
* Community content is sent in its own platform request so a second selected
  platform cannot truncate the Community caption.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Iterator, Mapping, Sequence

from .adapter import ApprovalRef, PublicGhlAdapter
from .auth import TenantBinding
from .errors import ContractViolation
from .idempotency import IdempotencyKey
from .operations import OPERATIONS
from .readback import ReadbackSpec, ReadbackStatus
from .result import OperationResult, Status
from .transport import Transport, TransportResponse

# ---------------------------------------------------------------------------
# contract constants
# ---------------------------------------------------------------------------

TITLE_LIMIT = 1_000
COMMUNITY_CAPTION_LIMIT = 100_000
COMMUNITY_MEDIA_LIMIT = 4
COMMENT_TEXT_LIMIT = 8_000

DEFAULT_MEMBER_PAGE_LIMIT = 100
MAX_MEMBER_PAGES = 50
#: Platform literal assumed for a connected Community channel account.  The
#: literal is configurable because the observed value is not settled by
#: Document 1; the default is the value the Social Planner Community rail is
#: expected to report and is named in WF10-CR01 as an open evidence item.
DEFAULT_COMMUNITY_PLATFORMS: tuple[str, ...] = ("community",)
COMMENT_PLATFORM = "community"
#: Comment attachment URLs are not rendered by the Community behavior because
#: of its bucket restriction (Document 1 section 11.5).  A plan therefore never
#: puts them in the request body and always reports them as not rendered.
ATTACHMENT_WARNING = (
    "external comment attachment URL(s) are not rendered by the Community "
    "behavior; the comment body carries text only. Use a proven native UI "
    "operation or an accessible resource link in the text."
)

#: Operation-id map.  Every id below is the row WF00 froze in
#: ``public/operations.py`` (WF00-CP01); WF00 owns the ids, this module only
#: consumes them.
OPERATION_IDS: dict[str, str] = {
    "accounts.list": "social.accounts.list",
    "members.list": "social.community.accounts.users.list",
    "members.validate": "social.community.authors.validate",
    "posts.create": "social.posts.create",
    "posts.list": "social.posts.list",
    "posts.get": "social.posts.get",
    "comments.create": "social.community.comments.create",
    "comments.list": "social.comments.list",
}

#: Empty by design: WF00-CP01 froze every Community row above.  A future id that
#: is written before its row lands belongs here so the gap detail can name the
#: documented contract instead of an empty string.
PENDING_OPERATION_ROWS: dict[str, str] = {}

#: Where a genuinely missing row is reported for change.
ROW_CHANGE_REQUEST = "change-requests/wf11/1.md"

#: Wire names Document 1 does not settle.  They are emitted as recorded here
#: and are listed in WF10-CR01 so WF00/WF01 can certify or correct them.  A
#: consumer must not treat them as certified by this module.
WIRE_ASSUMPTIONS: dict[str, str] = {
    "members.pagination": (
        "the member-list page cursor/limit names are not stated by Document 1 "
        "section 11.2; this module sends limit/page as query parameters"
    ),
    "comment.body": (
        "Document 1 section 11.5 pins isParentThread and notifyAllGroupMembers "
        "but not the remaining comment body names; this module sends postId, "
        "comment and parentCommentId"
    ),
    "comment.reply": (
        "a reply sets isParentThread=false plus parentCommentId; a top-level "
        "comment sets isParentThread=true and no parentCommentId"
    ),
    "post.status": (
        "requested lifecycle is the Social Planner status field draft|scheduled; "
        "no immediate-publish request is built by this module"
    ),
}


class CommunitySocialGap(ContractViolation):
    """A required Community operation row is not frozen yet."""

    rule = "community_operation_row_missing"


class CommunityPreflightRefused(ContractViolation):
    """The request cannot be built without guessing a documented fact."""

    rule = "community_preflight_refused"


class CommunityAuthorRefused(ContractViolation):
    """The stored author is not eligible for this Community channel."""

    rule = "community_author_refused"


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _required_text(value: Any, *, rule: str, detail: Mapping[str, Any] | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractViolation(rule, detail=dict(detail or {}))
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _nested_collection(payload: Any, *, depth: int = 2) -> list[Mapping[str, Any]]:
    """First non-empty list of mappings in the payload, at most ``depth`` deep.

    The documented Social Planner envelopes are not pinned by Document 1, so
    this reads the first list rather than guessing one envelope key.
    """

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if depth <= 0 or not isinstance(payload, Mapping):
        return []
    for value in payload.values():
        if isinstance(value, list):
            items = [item for item in value if isinstance(item, Mapping)]
            if items:
                return items
        elif isinstance(value, Mapping):
            nested = _nested_collection(value, depth=depth - 1)
            if nested:
                return nested
    return []


# ---------------------------------------------------------------------------
# connected accounts and members
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConnectedAccount:
    """One connected Social Planner account (a Community channel account)."""

    account_id: str
    platform: str
    oauth_id: str | None = None
    group_id: str | None = None
    name: str | None = None

    @classmethod
    def from_api(cls, payload: Any) -> "ConnectedAccount":
        body = _mapping(payload)
        account_id = body.get("id")
        oauth_id = body.get("oauthId")
        if not isinstance(account_id, str) or not account_id.strip():
            raise CommunityPreflightRefused(
                "account_id_missing",
                detail={
                    "oauth_id_present": isinstance(oauth_id, str) and bool(oauth_id),
                    "hint": (
                        "store account.id, never oauthId (Document 1 section 11.3)"
                    ),
                },
            )
        meta = _mapping(body.get("meta"))
        group_id = meta.get("groupId")
        name = body.get("name")
        return cls(
            account_id=account_id,
            platform=str(body.get("platform") or "").strip().lower(),
            oauth_id=oauth_id if isinstance(oauth_id, str) and oauth_id else None,
            group_id=group_id if isinstance(group_id, str) and group_id else None,
            name=name if isinstance(name, str) else None,
        )

    def is_community(self, platforms: Sequence[str]) -> bool:
        return self.platform in {str(item).lower() for item in platforms}


@dataclass(frozen=True)
class CommunityMember:
    """An eligible author: a Community member ``contactId`` of one channel."""

    account_id: str
    contact_id: str
    name: str | None = None
    group_id: str | None = None

    @classmethod
    def from_api(cls, payload: Any, *, account: ConnectedAccount) -> "CommunityMember":
        body = _mapping(payload)
        identity_fields = ("userType", "memberType", "role")
        for field in identity_fields:
            value = body.get(field)
            if isinstance(value, str) and value.strip().lower() in (
                "user",
                "staff",
                "team_member",
                "account_user",
            ):
                raise CommunityAuthorRefused(
                    "staff_identity_not_allowed",
                    detail={
                        "field": field,
                        "hint": "select a member contactId, not a staff user id",
                    },
                )
        contact_id = _required_text(
            body.get("contactId"), rule="member_contact_id_missing"
        )
        name = body.get("name")
        if not isinstance(name, str) or not name.strip():
            first = body.get("firstName") if isinstance(body.get("firstName"), str) else ""
            last = body.get("lastName") if isinstance(body.get("lastName"), str) else ""
            joined = (first + " " + last).strip()
            name = joined or None
        return cls(
            account_id=account.account_id,
            contact_id=contact_id,
            name=name,
            group_id=account.group_id,
        )


@dataclass(frozen=True)
class MemberPage:
    account_id: str
    page: int
    members: tuple[CommunityMember, ...]
    #: True when a full page came back.  The provider cursor is not pinned by
    #: Document 1, so a full page is the honest "maybe more" signal.
    has_more: bool


@dataclass(frozen=True)
class AuthorMapping:
    """The ``postAsUser`` entry for one Community account."""

    account_id: str
    contact_id: str
    name: str | None = None

    @classmethod
    def for_member(
        cls, account: ConnectedAccount, member: CommunityMember
    ) -> "AuthorMapping":
        if member.account_id != account.account_id:
            raise CommunityAuthorRefused(
                "member_belongs_to_another_channel",
                detail={
                    "account_id": account.account_id,
                    "member_account_id": member.account_id,
                },
            )
        return cls(
            account_id=account.account_id,
            contact_id=member.contact_id,
            name=member.name,
        )

    def as_post_as_user(self) -> dict[str, Any]:
        entry: dict[str, Any] = {"id": self.contact_id}
        if self.name:
            entry["name"] = self.name
        return {self.account_id: entry}


@dataclass(frozen=True)
class MembershipValidation:
    state: str  # "valid" | "invalid" | "unknown"
    group_id: str
    contact_id: str
    http_status: int | None
    receipt_id: str
    flags: Mapping[str, bool]


# ---------------------------------------------------------------------------
# post preflight and lifecycle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MediaItem:
    url: str
    type: str

    @classmethod
    def from_value(cls, value: Any) -> "MediaItem":
        body = _mapping(value)
        url = _required_text(body.get("url"), rule="media_url_missing")
        kind = _required_text(body.get("type"), rule="media_type_missing")
        return cls(url=url, type=kind)

    def as_wire(self) -> dict[str, str]:
        return {"url": self.url, "type": self.type}


@dataclass(frozen=True)
class PlatformRequest:
    """One platform-specific post request.

    Community content travels alone so another platform's caption limit can
    never truncate it (Document 1 section 11.3).
    """

    platform: str
    account_ids: tuple[str, ...]
    body: Mapping[str, Any]
    is_community: bool


@dataclass(frozen=True)
class CommunityPostPlan:
    title: str
    caption: str
    media: tuple[MediaItem, ...]
    status: str
    schedule_date: str | None
    notify_all_group_members: bool
    account_ids: tuple[str, ...]
    authors: tuple[AuthorMapping, ...]
    body: Mapping[str, Any]

    def platform_requests(
        self,
        *,
        other_platforms: Mapping[str, Sequence[str]] | None = None,
        other_caption: str | None = None,
    ) -> tuple[PlatformRequest, ...]:
        requests: list[PlatformRequest] = [
            PlatformRequest(
                platform=COMMENT_PLATFORM,
                account_ids=tuple(self.account_ids),
                body=dict(self.body),
                is_community=True,
            )
        ]
        for platform, account_ids in dict(other_platforms or {}).items():
            ids = tuple(str(item) for item in account_ids)
            if not ids:
                continue
            body: dict[str, Any] = {
                "accountIds": list(ids),
                "type": "post",
                "summary": self.caption if other_caption is None else str(other_caption),
                "media": [item.as_wire() for item in self.media],
                "status": self.status,
            }
            if self.schedule_date:
                body["scheduleDate"] = self.schedule_date
            requests.append(
                PlatformRequest(
                    platform=str(platform),
                    account_ids=ids,
                    body=body,
                    is_community=False,
                )
            )
        return tuple(requests)


class PostLifecycle(str, Enum):
    submitted = "submitted"
    draft_saved = "draft_saved"
    scheduled = "scheduled"
    publishing = "publishing"
    published_verified = "published_verified"
    failed = "failed"
    pending_moderation = "pending_moderation"
    pending_processing = "pending_processing"


@dataclass(frozen=True)
class PostReceipt:
    result: OperationResult
    lifecycle: PostLifecycle
    request: PlatformRequest
    deduplicated: bool = False

    @property
    def published(self) -> bool:
        return self.lifecycle is PostLifecycle.published_verified


def lifecycle_for(
    *,
    requested_status: str | None,
    result: OperationResult,
    read_status: str | None,
) -> PostLifecycle:
    """Map one create+readback outcome onto the documented lifecycle.

    A created record or an accepted schedule is never reported as a published
    post (Document 1 section 11.4).  ``published_verified`` additionally needs
    a verified readback and a published status on the read record.
    """

    if result.status is Status.unknown_outcome:
        return PostLifecycle.pending_processing
    if result.status is not Status.ok:
        return PostLifecycle.failed
    observed = (read_status or "").strip().lower()
    if observed == "published":
        verified = (
            result.readback is not None
            and result.readback.result is ReadbackStatus.verified
        )
        return PostLifecycle.published_verified if verified else PostLifecycle.publishing
    if observed in ("failed", "error"):
        return PostLifecycle.failed
    if observed in ("pending_moderation", "moderation", "pending_review"):
        return PostLifecycle.pending_moderation
    if observed in ("pending", "processing", "pending_processing"):
        return PostLifecycle.pending_processing
    if observed == "publishing":
        return PostLifecycle.publishing
    if observed == "draft":
        return PostLifecycle.draft_saved
    if observed == "scheduled":
        return PostLifecycle.scheduled
    if str(requested_status or "").lower() == "scheduled":
        return PostLifecycle.scheduled
    return PostLifecycle.draft_saved


def community_post_readback(caption: str, *, location_id: str) -> ReadbackSpec:
    """Default readback plan for a Community post create.

    The frozen ``social.posts.create`` row names ``social.posts.list`` as its
    readback plan, and the list row is a POST whose body the frozen readback
    runner does not send.  A readback that cannot be read degrades to
    ``unknown_outcome`` -- never to a false "verified".
    """

    return ReadbackSpec(
        operation_id=OPERATION_IDS["posts.list"],
        target_params={"locationId": str(location_id)},
        expect={"summary": str(caption)},
        scan_nested=True,
        description="the created Community post appears in the location post list",
    )


def build_community_post(
    *,
    accounts: Sequence[ConnectedAccount],
    authors: Sequence[AuthorMapping],
    title: Any,
    caption: Any,
    media: Sequence[Any] = (),
    status: str = "draft",
    schedule_date: str | None = None,
    notify_all_group_members: bool = False,
    broadcast_approved: bool = False,
) -> CommunityPostPlan:
    """Preflight one Community post and build its exact request body."""

    channel_accounts = tuple(accounts)
    if not channel_accounts:
        raise CommunityPreflightRefused("community_account_required")
    seen: set[str] = set()
    for account in channel_accounts:
        if not isinstance(account, ConnectedAccount):
            raise CommunityPreflightRefused("community_account_invalid")
        if account.account_id in seen:
            raise CommunityPreflightRefused(
                "community_account_duplicate", detail={"account_id": account.account_id}
            )
        seen.add(account.account_id)
        if not account.group_id:
            raise CommunityPreflightRefused(
                "group_id_unobserved",
                detail={
                    "account_id": account.account_id,
                    "unblock": (
                        "read account.meta.groupId from the connected-account "
                        "listing; the portal slug and account.id are not the "
                        "backend group id"
                    ),
                },
            )

    author_ids = {author.account_id for author in authors}
    missing = sorted(seen - author_ids)
    extra = sorted(author_ids - seen)
    if missing or extra:
        raise CommunityPreflightRefused(
            "author_mapping_incomplete",
            detail={"missing": missing, "extra": extra},
        )
    ordered_authors = tuple(
        next(author for author in authors if author.account_id == account_id)
        for account_id in (account.account_id for account in channel_accounts)
    )

    title_text = _required_text(title, rule="community_title_required").strip()
    if len(title_text) > TITLE_LIMIT:
        raise CommunityPreflightRefused(
            "community_title_too_long", detail={"limit": TITLE_LIMIT, "length": len(title_text)}
        )
    caption_text = _required_text(caption, rule="community_caption_required")
    if len(caption_text) > COMMUNITY_CAPTION_LIMIT:
        raise CommunityPreflightRefused(
            "community_caption_too_long",
            detail={"limit": COMMUNITY_CAPTION_LIMIT, "length": len(caption_text)},
        )

    media_items = tuple(MediaItem.from_value(item) for item in media)
    if len(media_items) > COMMUNITY_MEDIA_LIMIT:
        raise CommunityPreflightRefused(
            "community_media_too_many",
            detail={"limit": COMMUNITY_MEDIA_LIMIT, "count": len(media_items)},
        )

    requested = str(status or "").strip().lower()
    if requested not in ("draft", "scheduled"):
        raise CommunityPreflightRefused(
            "community_status_invalid",
            detail={"allowed": ["draft", "scheduled"]},
        )
    if requested == "draft" and schedule_date:
        raise CommunityPreflightRefused(
            "schedule_with_draft", detail={"hint": "use status=scheduled with a schedule_date"}
        )
    if requested == "scheduled":
        schedule_text = _required_text(
            schedule_date, rule="schedule_date_required"
        ).strip()
    else:
        schedule_text = None

    notify = bool(notify_all_group_members)
    if notify and not broadcast_approved:
        raise CommunityPreflightRefused(
            "notification_requires_approval",
            detail={
                "hint": (
                    "notifyAllGroupMembers must default to false; enabling it "
                    "needs explicit broadcast permission"
                )
            },
        )

    post_as_user: dict[str, Any] = {}
    for author in ordered_authors:
        post_as_user.update(author.as_post_as_user())

    details: dict[str, Any] = {
        "title": title_text,
        "notifyAllGroupMembers": notify,
        "postAsUser": post_as_user,
    }
    body: dict[str, Any] = {
        "accountIds": [account.account_id for account in channel_accounts],
        "type": "post",
        "summary": caption_text,
        "media": [item.as_wire() for item in media_items],
        "status": requested,
        "communityPostDetails": details,
    }
    if schedule_text:
        body["scheduleDate"] = schedule_text

    return CommunityPostPlan(
        title=title_text,
        caption=caption_text,
        media=media_items,
        status=requested,
        schedule_date=schedule_text,
        notify_all_group_members=notify,
        account_ids=tuple(account.account_id for account in channel_accounts),
        authors=ordered_authors,
        body=body,
    )


# ---------------------------------------------------------------------------
# comments
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommentPlan:
    post_id: str
    text: str
    is_parent_thread: bool
    parent_comment_id: str | None
    notify_all_group_members: bool
    attachments: tuple[str, ...]
    attachments_rendered: bool
    attachment_warning: str | None
    body: Mapping[str, Any]


@dataclass(frozen=True)
class CommentReceipt:
    result: OperationResult
    plan: CommentPlan
    attachments_rendered: bool = False


def build_comment(
    *,
    post_id: Any,
    text: Any,
    is_parent_thread: bool = True,
    parent_comment_id: str | None = None,
    notify_all_group_members: bool = False,
    broadcast_approved: bool = False,
    attachments: Sequence[str] = (),
) -> CommentPlan:
    """Preflight one Community comment or reply.

    ``post_id`` is the internal Social Planner post id returned by a Community
    create/read -- not a native platform post id.  ``isParentThread=true``
    targets the post; ``false`` targets an existing comment and needs its
    internal comment id.
    """

    internal_post_id = _required_text(post_id, rule="comment_post_id_required")
    text_value = _required_text(text, rule="comment_text_required")
    if len(text_value) > COMMENT_TEXT_LIMIT:
        raise CommunityPreflightRefused(
            "comment_text_too_long",
            detail={"limit": COMMENT_TEXT_LIMIT, "length": len(text_value)},
        )
    parent = str(is_parent_thread).lower() not in ("false", "0", "no")
    parent_id = parent_comment_id.strip() if isinstance(parent_comment_id, str) else None
    if parent and parent_id:
        raise CommunityPreflightRefused(
            "parent_thread_with_parent_comment",
            detail={"hint": "a top-level comment targets the post only"},
        )
    if not parent and not parent_id:
        raise CommunityPreflightRefused(
            "reply_without_parent_comment",
            detail={"hint": "isParentThread=false targets an internal comment id"},
        )
    notify = bool(notify_all_group_members)
    if notify and not broadcast_approved:
        raise CommunityPreflightRefused(
            "notification_requires_approval",
            detail={"hint": "Community comments default to no group notification"},
        )

    attachment_urls = tuple(
        str(item).strip() for item in attachments if str(item).strip()
    )
    body: dict[str, Any] = {
        "postId": internal_post_id,
        "comment": text_value,
        "isParentThread": parent,
        "notifyAllGroupMembers": notify,
    }
    if parent_id:
        body["parentCommentId"] = parent_id
    return CommentPlan(
        post_id=internal_post_id,
        text=text_value,
        is_parent_thread=parent,
        parent_comment_id=parent_id,
        notify_all_group_members=notify,
        attachments=attachment_urls,
        attachments_rendered=False,
        attachment_warning=ATTACHMENT_WARNING if attachment_urls else None,
        body=body,
    )


def comment_readback(plan: CommentPlan) -> ReadbackSpec:
    return ReadbackSpec(
        operation_id=OPERATION_IDS["comments.list"],
        target_params={"platform": COMMENT_PLATFORM},
        expect={"postId": plan.post_id},
        scan_nested=True,
        description="the comment appears in the Community comment list",
    )


# ---------------------------------------------------------------------------
# response recording (bodies never enter the result envelope)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Record:
    status: int | None
    body: bytes


class _Recorder:
    """Wrap the adapter's transport and keep response bytes for parsing.

    ``ponytail:`` the frozen result envelope carries no body, so parsing a list
    needs the same guarded wrapper ``workflow_v4`` uses.  Drop this class when
    the public adapter grows a body accessor.
    """

    def __init__(self, inner: Transport) -> None:
        if not callable(getattr(inner, "request", None)):
            raise ContractViolation("community_transport_invalid")
        self._inner = inner
        self.records: list[_Record] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        version: str | None,
        headers: Mapping[str, str],
        query: Mapping[str, object] | None,
        body: Mapping[str, object] | None,
        timeout_s: float,
    ) -> TransportResponse:
        response = self._inner.request(
            method=method,
            url=url,
            version=version,
            headers=headers,
            query=query,
            body=body,
            timeout_s=timeout_s,
        )
        self.records.append(
            _Record(status=response.status, body=response.body or b"")
        )
        return response

    def __len__(self) -> int:
        return len(self.records)


# ---------------------------------------------------------------------------
# the adapter
# ---------------------------------------------------------------------------


class CommunitySocialAdapter:
    """Typed member/post/comment surface for Skills 35, 6 and 44."""

    def __init__(
        self,
        *,
        public: PublicGhlAdapter,
        operations: Mapping[str, Any] = OPERATIONS,
        community_platforms: Sequence[str] = DEFAULT_COMMUNITY_PLATFORMS,
        transport: Transport | None = None,
    ) -> None:
        if not isinstance(public, PublicGhlAdapter):
            raise ContractViolation("public_adapter_required")
        base: Transport | None = transport
        if base is None:
            base = getattr(public, "_transport", None)  # ponytail: see _Recorder
        if base is None or not callable(getattr(base, "request", None)):
            raise ContractViolation("community_transport_unavailable")
        if isinstance(base, _Recorder):
            recorder = base
        else:
            recorder = _Recorder(base)
            try:
                public._transport = recorder  # ponytail: see _Recorder
            except AttributeError:  # pragma: no cover - defensive
                raise ContractViolation("community_transport_unbindable") from None
        self._public = public
        self._operations = operations
        self._recorder = recorder
        self._platforms = tuple(str(item).lower() for item in community_platforms)
        self._receipts: dict[tuple[str, str, str], PostReceipt] = {}

    # -- row resolution ---------------------------------------------------

    def _operation(self, key: str) -> str:
        operation_id = OPERATION_IDS[key]
        getter = getattr(self._operations, "get", None)
        row = getter(operation_id) if callable(getter) else None
        if row is None and not isinstance(self._operations, Mapping):
            row = None
        if row is None:
            try:
                row = self._operations[operation_id]  # type: ignore[index]
            except (KeyError, TypeError):
                row = None
        if row is None:
            raise CommunitySocialGap(
                "operation_row_missing",
                operation_id=operation_id,
                detail={
                    "owner": "WF00",
                    "change_request": ROW_CHANGE_REQUEST,
                    "contract": PENDING_OPERATION_ROWS.get(operation_id, ""),
                },
            )
        return operation_id

    # -- response parsing -------------------------------------------------

    def _body_since(self, mark: int) -> Any:
        for record in reversed(self._recorder.records[mark:]):
            if record.status is None or not (200 <= record.status < 300):
                continue
            try:
                return json.loads(record.body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return None
        return None

    # -- accounts ---------------------------------------------------------

    def list_connected_accounts(
        self, *, tenant: TenantBinding, attempt: int = 1
    ) -> tuple[OperationResult, tuple[ConnectedAccount, ...]]:
        operation_id = self._operation("accounts.list")
        mark = len(self._recorder)
        result = self._public.call(
            operation_id=operation_id,
            tenant=tenant,
            path_params={"locationId": tenant.location_id},
            attempt=attempt,
        )
        if result.status is not Status.ok:
            return result, ()
        payload = self._body_since(mark)
        accounts = tuple(
            ConnectedAccount.from_api(item) for item in _nested_collection(payload)
        )
        return result, accounts

    def list_community_accounts(
        self, *, tenant: TenantBinding, attempt: int = 1
    ) -> tuple[OperationResult, tuple[ConnectedAccount, ...]]:
        result, accounts = self.list_connected_accounts(tenant=tenant, attempt=attempt)
        if result.status is not Status.ok:
            return result, ()
        return result, tuple(
            account for account in accounts if account.is_community(self._platforms)
        )

    # -- members ----------------------------------------------------------

    def list_members(
        self,
        *,
        tenant: TenantBinding,
        account: ConnectedAccount,
        page: int = 1,
        limit: int = DEFAULT_MEMBER_PAGE_LIMIT,
        attempt: int = 1,
    ) -> tuple[OperationResult, MemberPage]:
        if not isinstance(account, ConnectedAccount):
            raise ContractViolation("community_account_invalid")
        if int(page) < 1 or int(limit) < 1:
            raise ContractViolation("community_member_page_invalid")
        operation_id = self._operation("members.list")
        mark = len(self._recorder)
        result = self._public.call(
            operation_id=operation_id,
            tenant=tenant,
            path_params={
                "locationId": tenant.location_id,
                "accountId": account.account_id,
            },
            query={"limit": str(int(limit)), "page": str(int(page))},
            attempt=attempt,
        )
        if result.status is not Status.ok:
            return result, MemberPage(
                account_id=account.account_id,
                page=int(page),
                members=(),
                has_more=False,
            )
        payload = self._body_since(mark)
        members = tuple(
            CommunityMember.from_api(item, account=account)
            for item in _nested_collection(payload)
        )
        return result, MemberPage(
            account_id=account.account_id,
            page=int(page),
            members=members,
            has_more=len(members) >= int(limit),
        )

    def iter_members(
        self,
        *,
        tenant: TenantBinding,
        account: ConnectedAccount,
        limit: int = DEFAULT_MEMBER_PAGE_LIMIT,
        max_pages: int = MAX_MEMBER_PAGES,
        attempt: int = 1,
    ) -> Iterator[MemberPage]:
        """Yield eligible members page by page for ONE channel account.

        Eligibility is channel-specific: a member returned for one account is
        never assumed eligible in another.
        """

        for page in range(1, int(max_pages) + 1):
            result, page_result = self.list_members(
                tenant=tenant,
                account=account,
                page=page,
                limit=limit,
                attempt=attempt,
            )
            if result.status is not Status.ok:
                return
            yield page_result
            if not page_result.has_more:
                return

    # -- membership validation --------------------------------------------

    def validate_author(
        self,
        *,
        tenant: TenantBinding,
        account: ConnectedAccount,
        contact_id: str,
        attempt: int = 1,
    ) -> tuple[OperationResult, MembershipValidation]:
        contact = _required_text(contact_id, rule="member_contact_id_missing")
        if not account.group_id:
            raise CommunityPreflightRefused(
                "group_id_unobserved",
                detail={
                    "account_id": account.account_id,
                    "unblock": (
                        "read account.meta.groupId; a portal slug or account.id "
                        "is not the backend group id"
                    ),
                },
            )
        operation_id = self._operation("members.validate")
        mark = len(self._recorder)
        result = self._public.call(
            operation_id=operation_id,
            tenant=tenant,
            path_params={
                "locationId": tenant.location_id,
                "groupId": account.group_id,
                "contactId": contact,
            },
            attempt=attempt,
        )
        payload = self._body_since(mark) if result.status is Status.ok else None
        flags: dict[str, bool] = {}
        body = _mapping(payload)
        for key in ("valid", "isValid", "isMember"):
            value = body.get(key)
            if isinstance(value, bool):
                flags[key] = value
        if any(value is True for value in flags.values()):
            state = "valid"
        elif flags and any(value is False for value in flags.values()):
            state = "invalid"
        else:
            state = "unknown"
        return result, MembershipValidation(
            state=state,
            group_id=account.group_id,
            contact_id=contact,
            http_status=result.http_status,
            receipt_id=result.receipt_id,
            flags=flags,
        )

    def require_valid_author(self, validation: MembershipValidation) -> None:
        if validation.state == "valid":
            return
        raise CommunityAuthorRefused(
            "author_not_eligible_for_channel",
            detail={
                "state": validation.state,
                "group_id": validation.group_id,
                "contact_id": validation.contact_id,
                "receipt_id": validation.receipt_id,
            },
        )

    # -- posts ------------------------------------------------------------

    def create_post(
        self,
        *,
        tenant: TenantBinding,
        request: PlatformRequest,
        approval: ApprovalRef | Mapping[str, Any] | str,
        idempotency_key: str | None = None,
        readback: ReadbackSpec | None = None,
        attempt: int = 1,
    ) -> PostReceipt:
        if not isinstance(request, PlatformRequest):
            raise ContractViolation("community_platform_request_invalid")
        operation_id = self._operation("posts.create")
        key = idempotency_key or IdempotencyKey.issue(operation_id).value
        dedupe = (tenant.location_id, operation_id, str(key))
        existing = self._receipts.get(dedupe)
        if existing is not None:
            return replace(existing, deduplicated=True)

        caption = str(request.body.get("summary") or "")
        spec = readback or community_post_readback(
            caption, location_id=tenant.location_id
        )
        mark = len(self._recorder)
        result = self._public.call(
            operation_id=operation_id,
            tenant=tenant,
            path_params={"locationId": tenant.location_id},
            body=dict(request.body),
            idempotency_key=key,
            approval=approval,
            readback=spec,
            attempt=attempt,
        )
        read_status = (
            _observed_post_status(self._body_since(mark), caption)
            if result.status is Status.ok
            else None
        )
        lifecycle = lifecycle_for(
            requested_status=str(request.body.get("status") or ""),
            result=result,
            read_status=read_status,
        )
        receipt = PostReceipt(result=result, lifecycle=lifecycle, request=request)
        if result.status in (Status.ok, Status.unknown_outcome):
            self._receipts[dedupe] = receipt
        return receipt

    def publish_plan(
        self,
        *,
        tenant: TenantBinding,
        plan: CommunityPostPlan,
        approval: ApprovalRef | Mapping[str, Any] | str,
        other_platforms: Mapping[str, Sequence[str]] | None = None,
        other_caption: str | None = None,
        attempt: int = 1,
    ) -> tuple[PostReceipt, ...]:
        receipts: list[PostReceipt] = []
        for request in plan.platform_requests(
            other_platforms=other_platforms, other_caption=other_caption
        ):
            receipts.append(
                self.create_post(
                    tenant=tenant,
                    request=request,
                    approval=approval,
                    attempt=attempt,
                )
            )
        return tuple(receipts)

    # -- comments ---------------------------------------------------------

    def create_comment(
        self,
        *,
        tenant: TenantBinding,
        plan: CommentPlan,
        approval: ApprovalRef | Mapping[str, Any] | str,
        idempotency_key: str | None = None,
        readback: ReadbackSpec | None = None,
        attempt: int = 1,
    ) -> CommentReceipt:
        if not isinstance(plan, CommentPlan):
            raise ContractViolation("community_comment_plan_invalid")
        operation_id = self._operation("comments.create")
        result = self._public.call(
            operation_id=operation_id,
            tenant=tenant,
            path_params={},
            query={},
            body=dict(plan.body),
            idempotency_key=idempotency_key or IdempotencyKey.issue(operation_id).value,
            approval=approval,
            readback=readback or comment_readback(plan),
            attempt=attempt,
        )
        return CommentReceipt(
            result=result, plan=plan, attachments_rendered=False
        )

    def list_comments(
        self,
        *,
        tenant: TenantBinding,
        post_id: str,
        limit: int = 20,
        offset: int = 0,
        attempt: int = 1,
    ) -> tuple[OperationResult, tuple[Mapping[str, Any], ...]]:
        internal_post_id = _required_text(post_id, rule="comment_post_id_required")
        operation_id = self._operation("comments.list")
        mark = len(self._recorder)
        result = self._public.call(
            operation_id=operation_id,
            tenant=tenant,
            path_params={"platform": COMMENT_PLATFORM},
            body={
                "postId": internal_post_id,
                "limit": str(int(limit)),
                "offset": str(int(offset)),
            },
            attempt=attempt,
        )
        if result.status is not Status.ok:
            return result, ()
        payload = self._body_since(mark)
        return result, tuple(_nested_collection(payload))


def _observed_post_status(payload: Any, caption: str) -> str | None:
    """The post status of the record whose summary matches this caption."""

    for item in _nested_collection(payload):
        summary = item.get("summary")
        if isinstance(summary, str) and summary == caption:
            status = item.get("status")
            if isinstance(status, str) and status.strip():
                return status.strip().lower()
    # A single unambiguous record may still carry the status; never guess a
    # status from a list that does not name this caption.
    items = _nested_collection(payload)
    if len(items) == 1:
        status = items[0].get("status")
        if isinstance(status, str) and status.strip():
            return status.strip().lower()
    return None


__all__ = [
    "ATTACHMENT_WARNING",
    "AuthorMapping",
    "COMMENT_PLATFORM",
    "COMMENT_TEXT_LIMIT",
    "COMMUNITY_CAPTION_LIMIT",
    "COMMUNITY_MEDIA_LIMIT",
    "CommentPlan",
    "CommentReceipt",
    "CommunityAuthorRefused",
    "CommunityMember",
    "CommunityPostPlan",
    "CommunityPreflightRefused",
    "CommunitySocialAdapter",
    "CommunitySocialGap",
    "ConnectedAccount",
    "DEFAULT_COMMUNITY_PLATFORMS",
    "MediaItem",
    "MemberPage",
    "MembershipValidation",
    "OPERATION_IDS",
    "PENDING_OPERATION_ROWS",
    "ROW_CHANGE_REQUEST",
    "PlatformRequest",
    "PostLifecycle",
    "PostReceipt",
    "TITLE_LIMIT",
    "WIRE_ASSUMPTIONS",
    "build_comment",
    "build_community_post",
    "comment_readback",
    "community_post_readback",
    "lifecycle_for",
]
