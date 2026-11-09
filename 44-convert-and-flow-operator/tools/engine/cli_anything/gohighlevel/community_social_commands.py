"""Community commands for the GoHighLevel CLI (WF10).

WF03 owns ``gohighlevel_cli.py`` and registers this module:

    from cli_anything.gohighlevel.community_social_commands import register
    register(cli)

Everything in this module goes through ``CommunitySocialAdapter`` and therefore
through ``PublicGhlAdapter.call``: the operation row, tenant binding, auth
class, idempotency, approval, readback and capability gate are the frozen ones.
No command here publishes immediately, mixes platforms in one request, or uses
a staff user id as the Community author.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Mapping, Sequence

import click

from .public.adapter import ApprovalRef, PublicGhlAdapter
from .public.auth import (
    AuthKind,
    TenantBinding,
    resolve_auth,
    resolve_tenant_from_env,
)
from .public.community_social import (
    AuthorMapping,
    CommunitySocialAdapter,
    ConnectedAccount,
    build_comment,
    build_community_post,
)


def _emit(ctx: click.Context, payload: Any) -> None:
    if ctx.obj.get("json", False):
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    click.echo(json.dumps(payload, indent=2, default=str))


def _fail(message: str) -> None:
    click.echo(f"Error: {message}", err=True)
    sys.exit(1)


def _tenant(ctx: click.Context) -> TenantBinding:
    location_id = ctx.obj.get("location_id")
    if location_id:
        return TenantBinding(location_id=str(location_id), source="cli:--location-id")
    return resolve_tenant_from_env()


def _adapter(tenant: TenantBinding) -> CommunitySocialAdapter:
    auth = resolve_auth(kind=AuthKind.location_pit, location_id=tenant.location_id)
    return CommunitySocialAdapter(public=PublicGhlAdapter(auth=auth))


def _account_for(
    adapter: CommunitySocialAdapter, tenant: TenantBinding, account_id: str
) -> ConnectedAccount:
    result, accounts = adapter.list_community_accounts(tenant=tenant)
    if result.status.value != "ok":
        _fail(f"connected-account read did not succeed: {result.status.value}")
    for account in accounts:
        if account.account_id == account_id:
            return account
    _fail(
        f"{account_id} is not a connected Community channel account of this "
        "location; select one from `community accounts`"
    )
    raise AssertionError("unreachable")


def _author_from(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise click.BadParameter("expected account_id=contact_id")
    account_id, contact_id = value.split("=", 1)
    if not account_id.strip() or not contact_id.strip():
        raise click.BadParameter("expected account_id=contact_id")
    return account_id.strip(), contact_id.strip()


def _media_from(values: Sequence[str]) -> tuple[Mapping[str, str], ...]:
    media: list[Mapping[str, str]] = []
    for value in values:
        if "=" not in value:
            raise click.BadParameter("expected url=type")
        url, kind = value.split("=", 1)
        media.append({"url": url.strip(), "type": kind.strip()})
    return tuple(media)


@click.group()
@click.pass_context
def community(ctx: click.Context) -> None:
    """Community members, posts and comments (public Social Planner routes)."""


@community.command("accounts")
@click.pass_context
def community_accounts(ctx: click.Context) -> None:
    """List connected Community channel accounts."""

    try:
        tenant = _tenant(ctx)
        adapter = _adapter(tenant)
        result, accounts = adapter.list_community_accounts(tenant=tenant)
        _emit(
            ctx,
            {
                "status": result.status.value,
                "receipt_id": result.receipt_id,
                "accounts": [
                    {
                        "account_id": account.account_id,
                        "platform": account.platform,
                        "group_id": account.group_id,
                        "name": account.name,
                    }
                    for account in accounts
                ],
            },
        )
        if result.status.value != "ok":
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI surface
        _fail(str(exc))


@community.command("members")
@click.option("--account-id", required=True)
@click.option("--page", default=1, type=int)
@click.option("--limit", default=100, type=int)
@click.option("--all-pages", is_flag=True, default=False)
@click.pass_context
def community_members(
    ctx: click.Context, account_id: str, page: int, limit: int, all_pages: bool
) -> None:
    """List eligible author members for ONE Community channel account."""

    try:
        tenant = _tenant(ctx)
        adapter = _adapter(tenant)
        account = _account_for(adapter, tenant, account_id)
        pages = (
            list(adapter.iter_members(tenant=tenant, account=account, limit=limit))
            if all_pages
            else [adapter.list_members(tenant=tenant, account=account, page=page, limit=limit)[1]]
        )
        _emit(
            ctx,
            {
                "account_id": account.account_id,
                "group_id": account.group_id,
                "members": [
                    {
                        "contact_id": member.contact_id,
                        "name": member.name,
                        "page": page_result.page,
                    }
                    for page_result in pages
                    for member in page_result.members
                ],
            },
        )
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI surface
        _fail(str(exc))


@community.command("validate-author")
@click.option("--account-id", required=True)
@click.option("--contact-id", required=True)
@click.pass_context
def community_validate_author(
    ctx: click.Context, account_id: str, contact_id: str
) -> None:
    """Validate a stored author against the channel's observed group id."""

    try:
        tenant = _tenant(ctx)
        adapter = _adapter(tenant)
        account = _account_for(adapter, tenant, account_id)
        result, validation = adapter.validate_author(
            tenant=tenant, account=account, contact_id=contact_id
        )
        _emit(
            ctx,
            {
                "status": result.status.value,
                "receipt_id": result.receipt_id,
                "state": validation.state,
                "group_id": validation.group_id,
                "contact_id": validation.contact_id,
            },
        )
        if validation.state != "valid":
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI surface
        _fail(str(exc))


@community.command("draft-post")
@click.option("--account-id", required=True, multiple=True)
@click.option("--author", required=True, multiple=True, help="account_id=contact_id")
@click.option("--title", required=True)
@click.option("--caption", required=True)
@click.option("--media", multiple=True, help="url=type (max 4)")
@click.option("--schedule", "schedule_date", default=None, help="ISO 8601")
@click.option("--notify-all", is_flag=True, default=False)
@click.option("--broadcast-approved", is_flag=True, default=False)
@click.option("--approval-ref", default=None)
@click.option("--idempotency-key", default=None)
@click.pass_context
def community_draft_post(
    ctx: click.Context,
    account_id: Sequence[str],
    author: Sequence[str],
    title: str,
    caption: str,
    media: Sequence[str],
    schedule_date: str | None,
    notify_all: bool,
    broadcast_approved: bool,
    approval_ref: str | None,
    idempotency_key: str | None,
) -> None:
    """Create a Community post as a draft, or schedule it (never immediate)."""

    try:
        tenant = _tenant(ctx)
        authors = dict(_author_from(item) for item in author)
        ids = [str(item) for item in account_id]
        missing = [item for item in ids if item not in authors]
        if missing:
            _fail(f"no --author mapping for account(s): {', '.join(missing)}")
        dry_run = bool(ctx.obj.get("dry_run", False))
        adapter = None if dry_run else _adapter(tenant)
        accounts: list[ConnectedAccount] = []
        for item in ids:
            if adapter is None:
                accounts.append(
                    ConnectedAccount(
                        account_id=item,
                        platform="community",
                        group_id="dry-run-unresolved-group",
                    )
                )
            else:
                accounts.append(_account_for(adapter, tenant, item))
        plan = build_community_post(
            accounts=accounts,
            authors=tuple(
                AuthorMapping(account_id=item, contact_id=authors[item]) for item in ids
            ),
            title=title,
            caption=caption,
            media=_media_from(media),
            status="scheduled" if schedule_date else "draft",
            schedule_date=schedule_date,
            notify_all_group_members=notify_all,
            broadcast_approved=broadcast_approved,
        )
        if dry_run:
            _emit(ctx, {"dry_run": True, "body": plan.body})
            return
        if not approval_ref:
            _fail("--approval-ref is required for a Community post write")
        receipt = adapter.create_post(
            tenant=tenant,
            request=plan.platform_requests()[0],
            approval=ApprovalRef(ref=approval_ref),
            idempotency_key=idempotency_key,
        )
        _emit(
            ctx,
            {
                "status": receipt.result.status.value,
                "receipt_id": receipt.result.receipt_id,
                "lifecycle": receipt.lifecycle.value,
                "deduplicated": receipt.deduplicated,
            },
        )
        if receipt.result.status.value != "ok":
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI surface
        _fail(str(exc))


@community.command("comment")
@click.option("--post-id", required=True, help="internal Social Planner post id")
@click.option("--text", required=True)
@click.option("--reply-to", "parent_comment_id", default=None,
              help="internal comment id; makes this a reply")
@click.option("--notify-all", is_flag=True, default=False)
@click.option("--broadcast-approved", is_flag=True, default=False)
@click.option("--attachment", "attachments", multiple=True)
@click.option("--approval-ref", default=None)
@click.option("--idempotency-key", default=None)
@click.pass_context
def community_comment(
    ctx: click.Context,
    post_id: str,
    text: str,
    parent_comment_id: str | None,
    notify_all: bool,
    broadcast_approved: bool,
    attachments: Sequence[str],
    approval_ref: str | None,
    idempotency_key: str | None,
) -> None:
    """Create a Community comment or reply on an internal post id."""

    try:
        tenant = _tenant(ctx)
        plan = build_comment(
            post_id=post_id,
            text=text,
            is_parent_thread=parent_comment_id is None,
            parent_comment_id=parent_comment_id,
            notify_all_group_members=notify_all,
            broadcast_approved=broadcast_approved,
            attachments=attachments,
        )
        if plan.attachment_warning:
            click.echo(plan.attachment_warning, err=True)
        if ctx.obj.get("dry_run", False):
            _emit(
                ctx,
                {
                    "dry_run": True,
                    "body": plan.body,
                    "attachments_rendered": plan.attachments_rendered,
                },
            )
            return
        if not approval_ref:
            _fail("--approval-ref is required for a Community comment write")
        adapter = _adapter(tenant)
        receipt = adapter.create_comment(
            tenant=tenant,
            plan=plan,
            approval=ApprovalRef(ref=approval_ref),
            idempotency_key=idempotency_key,
        )
        _emit(
            ctx,
            {
                "status": receipt.result.status.value,
                "receipt_id": receipt.result.receipt_id,
                "attachments_rendered": receipt.attachments_rendered,
                "attachment_warning": plan.attachment_warning,
            },
        )
        if receipt.result.status.value != "ok":
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI surface
        _fail(str(exc))


def register(cli: click.Group) -> None:
    """WF03 calls this once on the root CLI group."""

    cli.add_command(community)


__all__ = ["community", "register"]
