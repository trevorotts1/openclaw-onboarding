"""Widget command module (WF31).  WF03 registers :func:`register`.

The module owns no CLI file: ``gohighlevel_cli.py`` belongs to WF03.  It
exports one click group plus a registration function so the integration lane can
attach it with a single call.

Write commands run through the frozen public adapter with the operation rows
from WF00.  Until those rows land, the adapter refuses ``unknown_operation_id``
before transport -- the honest failure, never a guessed method/path/Version.

Embed commands are offline file transforms: they validate a captured embed,
plan a single installation and emit a rollback blob.  They never invent a script
URL or token.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import click

from . import chat_widgets as cw
from .auth import AuthKind, resolve_auth
from .capability import CapabilityGate
from .readback import ReadbackSpec
from .transport import RequestsTransport


def _ctx_location(ctx: click.Context) -> str:
    location = (ctx.obj or {}).get("location_id")
    if not location:
        raise click.ClickException(
            "location id required: pass --location-id or set GHL_LOCATION_ID"
        )
    return str(location)


def _build_adapter(location_id: str) -> tuple[Any, cw.CapturingTransport]:
    from .adapter import PublicGhlAdapter

    auth = resolve_auth(kind=AuthKind.location_pit, location_id=location_id)
    transport = cw.CapturingTransport(RequestsTransport())
    adapter = PublicGhlAdapter(
        auth=auth,
        transport=transport,
        capability=None,
        default_timeout_s=60.0,
    )
    return adapter, transport


def _emit(value: Any) -> None:
    click.echo(json.dumps(value, indent=2, sort_keys=True, default=str))


def _load_json(path: str) -> Any:
    try:
        return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except OSError as exc:
        raise click.ClickException(f"cannot read {path}: {exc}") from exc
    except ValueError as exc:
        raise click.ClickException(f"invalid JSON in {path}: {exc}") from exc


def _write_json(path: str, value: Any) -> None:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _receipt(result: Any) -> dict[str, Any]:
    return {
        "status": getattr(getattr(result, "status", None), "value", str(result.status)),
        "operation_id": getattr(result, "operation_id", None),
        "receipt_id": getattr(result, "receipt_id", None),
        "http_status": getattr(result, "http_status", None),
        "readback": getattr(getattr(result, "readback", None), "result", None),
        "error": getattr(result, "error", None),
        "evidence": {
            key: item
            for key, item in dict(getattr(result, "evidence", {}) or {}).items()
            if key
            in (
                "operation_id",
                "request_fingerprint",
                "response_fingerprint",
                "version_header",
                "tenant",
                "auth_kind",
                "auth_source",
                "doc_url",
                "doc_fetch_date",
            )
        },
    }


def _default_create_readback(location_id: str, name: str) -> ReadbackSpec:
    return ReadbackSpec(
        operation_id=cw.WIDGET_OPERATIONS["list"],
        query={"locationId": location_id},
        expect={"name": name},
        scan_nested=True,
        description="created widget appears in the location widget list by name",
    )


@click.group("widgets")
def widgets() -> None:
    """Native chat widgets: inventory, create, embed installation, proof."""


@widgets.command("list")
@click.option("--query-file", type=click.Path(), default=None)
@click.pass_context
def widgets_list(ctx: click.Context, query_file: str | None) -> None:
    """List widgets for the bound location."""
    location_id = _ctx_location(ctx)
    query = {"locationId": location_id}
    if query_file:
        extra = _load_json(query_file)
        if not isinstance(extra, Mapping):
            raise click.ClickException("query file must contain a JSON object")
        query.update(dict(extra))
    from .auth import TenantBinding

    adapter, transport = _build_adapter(location_id)
    public = cw.ChatWidgetsPublic(adapter, transport)
    tenant = TenantBinding(location_id=location_id, source="cli:widgets.list")
    records = public.list_widgets(tenant, query=query)
    _emit({"widgets": [record.as_dict() for record in records]})


@widgets.command("get")
@click.argument("widget_id")
@click.pass_context
def widgets_get(ctx: click.Context, widget_id: str) -> None:
    """Read one widget by its schema ``_id``."""
    location_id = _ctx_location(ctx)
    from .auth import TenantBinding

    adapter, transport = _build_adapter(location_id)
    public = cw.ChatWidgetsPublic(adapter, transport)
    tenant = TenantBinding(location_id=location_id, source="cli:widgets.get")
    _emit(
        public.get_widget(
            tenant, location_id=location_id, widget_id=widget_id
        ).as_dict()
    )


@widgets.command("create")
@click.option("--name", required=True)
@click.option("--chat-type", required=True, type=click.Choice(cw.CREATE_CHAT_TYPES))
@click.option(
    "--version",
    "config_version",
    required=True,
    type=int,
    help="Numeric widget configuration version (not the HTTP Version header).",
)
@click.option("--settings-file", type=click.Path(), default=None)
@click.option("--default/--no-default", default=None)
@click.option("--idempotency-key", required=True)
@click.option("--approval-ref", default=None)
@click.pass_context
def widgets_create(
    ctx: click.Context,
    name: str,
    chat_type: str,
    config_version: int,
    settings_file: str | None,
    default: bool | None,
    idempotency_key: str,
    approval_ref: str | None,
) -> None:
    """Create a widget.  Only liveChat/emailChat are write types."""
    location_id = _ctx_location(ctx)
    settings = _load_json(settings_file) if settings_file else None
    if settings is not None and not isinstance(settings, Mapping):
        raise click.ClickException("settings file must contain a JSON object")
    from .adapter import ApprovalRef
    from .auth import TenantBinding

    adapter, transport = _build_adapter(location_id)
    public = cw.ChatWidgetsPublic(adapter, transport)
    tenant = TenantBinding(location_id=location_id, source="cli:widgets.create")
    widget_id, result = public.create_widget(
        tenant,
        location_id=location_id,
        name=name,
        chat_type=chat_type,
        version=config_version,
        settings=settings,
        default=default,
        idempotency_key=idempotency_key,
        approval=ApprovalRef(approval_ref) if approval_ref else None,
        readback=_default_create_readback(location_id, name),
    )
    payload = {"widget_id": widget_id or None, "receipt": _receipt(result)}
    _emit(payload)
    if not widget_id:
        raise SystemExit(1)


@widgets.command("update")
@click.argument("widget_id")
@click.option("--name", default=None)
@click.option("--chat-type", default=None, type=click.Choice(cw.CREATE_CHAT_TYPES))
@click.option("--version", "config_version", default=None, type=int)
@click.option("--settings-file", type=click.Path(), default=None)
@click.option("--default/--no-default", default=None)
@click.option("--idempotency-key", required=True)
@click.option("--approval-ref", default=None)
@click.option("--readback-expect-json", required=True)
@click.pass_context
def widgets_update(
    ctx: click.Context,
    widget_id: str,
    name: str | None,
    chat_type: str | None,
    config_version: int | None,
    settings_file: str | None,
    default: bool | None,
    idempotency_key: str,
    approval_ref: str | None,
    readback_expect_json: str,
) -> None:
    """Update a widget with an explicit non-vacuous read-back expectation."""
    location_id = _ctx_location(ctx)
    settings = _load_json(settings_file) if settings_file else None
    if settings is not None and not isinstance(settings, Mapping):
        raise click.ClickException("settings file must contain a JSON object")
    try:
        expect = json.loads(readback_expect_json)
    except ValueError as exc:
        raise click.ClickException(f"readback expectation is not JSON: {exc}") from exc
    if not isinstance(expect, dict) or not expect:
        raise click.ClickException("readback expectation must be a non-empty JSON object")
    from .adapter import ApprovalRef
    from .auth import TenantBinding

    adapter, transport = _build_adapter(location_id)
    public = cw.ChatWidgetsPublic(adapter, transport)
    tenant = TenantBinding(location_id=location_id, source="cli:widgets.update")
    result = public.update_widget(
        tenant,
        location_id=location_id,
        widget_id=widget_id,
        idempotency_key=idempotency_key,
        chat_type=chat_type,
        version=config_version,
        name=name,
        settings=settings,
        default=default,
        approval=ApprovalRef(approval_ref) if approval_ref else None,
        readback=ReadbackSpec(
            operation_id=cw.WIDGET_OPERATIONS["get"],
            target_params={"locationId": location_id, "id": widget_id},
            expect=expect,
            scan_nested=True,
        ),
    )
    _emit(_receipt(result))
    if getattr(result.status, "value", str(result.status)) != "ok":
        raise SystemExit(1)


@widgets.command("embed-validate")
@click.option("--embed-file", required=True, type=click.Path())
def widgets_embed_validate(embed_file: str) -> None:
    """Validate a captured embed; never generates one."""
    instruction = cw.load_embed_instruction(_load_json(embed_file))
    _emit(instruction.as_dict())


@widgets.command("embed-plan")
@click.option("--embed-file", required=True, type=click.Path())
@click.option("--page-file", type=click.Path(), default=None)
@click.option("--global-file", type=click.Path(), default=None)
@click.option("--slot", type=click.Choice(cw.PAGE_EMBED_SLOTS), default="footerCode")
@click.option("--scope", type=click.Choice(("page", "global")), default="page")
@click.option("--out", required=True, type=click.Path())
@click.option("--rollback-out", required=True, type=click.Path())
def widgets_embed_plan(
    embed_file: str,
    page_file: str | None,
    global_file: str | None,
    slot: str,
    scope: str,
    out: str,
    rollback_out: str,
) -> None:
    """Plan one installation and emit the exact revert blob.

    A duplicate at global or page scope is refused before anything is written.
    """
    instruction = cw.load_embed_instruction(_load_json(embed_file))
    page_data = _load_json(page_file) if page_file else {}
    global_snippets = _load_json(global_file) if global_file else []
    if not isinstance(page_data, Mapping):
        raise click.ClickException("page file must contain a JSON object")
    if not isinstance(global_snippets, list):
        raise click.ClickException("global file must contain a JSON array of snippets")
    try:
        if scope == "global":
            updated_global, plan = cw.plan_global_install(
                global_snippets, instruction, page_data=page_data
            )
            output: dict[str, Any] = {
                "scope": "global",
                "global_snippets": updated_global,
                "page_data": plan.page_data,
                "install": plan.as_evidence(),
            }
        else:
            plan = cw.plan_page_install(
                page_data,
                instruction,
                global_snippets=global_snippets,
                slot=slot,
            )
            output = {
                "scope": "page",
                "page_data": plan.page_data,
                "install": plan.as_evidence(),
            }
    except cw.WidgetError as exc:
        raise click.ClickException(str(exc)) from exc
    _write_json(out, output)
    _write_json(rollback_out, plan.rollback_page_data)
    _emit({"out": out, "rollback_out": rollback_out, "install": plan.as_evidence()})


@widgets.command("verify-render")
@click.option("--widget-id", required=True)
@click.option("--checks-file", required=True, type=click.Path())
@click.option("--evidence-ref", required=True)
def widgets_verify_render(
    widget_id: str, checks_file: str, evidence_ref: str
) -> None:
    """Require every desktop/mobile/interference check with evidence."""
    checks = _load_json(checks_file)
    if not isinstance(checks, Mapping):
        raise click.ClickException("checks file must contain a JSON object")
    try:
        result = cw.evaluate_rendered_checks(
            widget_id, checks, evidence_ref=evidence_ref
        )
    except cw.WidgetError as exc:
        raise click.ClickException(str(exc)) from exc
    _emit(result.as_evidence())
    if not result.passed:
        raise SystemExit(1)


@widgets.command("verify-thread")
@click.option("--widget-id", required=True)
@click.option("--location-id", "evidence_location_id", required=True)
@click.option("--responder-kind", required=True, type=click.Choice(cw.RESPONDER_KINDS))
@click.option("--evidence-file", required=True, type=click.Path())
@click.option("--require-handoff", is_flag=True, default=False)
@click.option("--require-after-hours", is_flag=True, default=False)
def widgets_verify_thread(
    widget_id: str,
    evidence_location_id: str,
    responder_kind: str,
    evidence_file: str,
    require_handoff: bool,
    require_after_hours: bool,
) -> None:
    """Prove thread/inbox/responder separately from a visible bubble."""
    payload = _load_json(evidence_file)
    if not isinstance(payload, Mapping):
        raise click.ClickException("evidence file must contain a JSON object")
    try:
        messages = tuple(
            cw.MessageEvidence(
                direction=str(item["direction"]),
                body=str(item["body"]),
                message_id=str(item["message_id"]),
            )
            for item in payload.get("messages", ())
        )
        evidence = cw.ConversationEvidence(
            widget_id=str(payload.get("widget_id", "")),
            location_id=str(payload.get("location_id", "")),
            thread_id=str(payload.get("thread_id", "")),
            inbox_id=str(payload.get("inbox_id", "")),
            responder_kind=str(payload.get("responder_kind", "")),
            responder_id=str(payload.get("responder_id", "")),
            messages=messages,
            handoff_target=payload.get("handoff_target"),
            handoff_verified=bool(payload.get("handoff_verified")),
            after_hours_verified=bool(payload.get("after_hours_verified")),
            visible_bubble_observed=bool(payload.get("visible_bubble_observed")),
        )
        result = cw.verify_conversation_delivery(
            evidence,
            expected_widget_id=widget_id,
            expected_location_id=evidence_location_id,
            expected_responder_kind=responder_kind,
            require_handoff=require_handoff,
            require_after_hours=require_after_hours,
        )
    except (KeyError, TypeError, cw.WidgetError) as exc:
        raise click.ClickException(f"invalid evidence: {exc}") from exc
    _emit(result.as_evidence())
    if not result.passed:
        raise SystemExit(1)


def register(cli: click.Group) -> click.Group:
    """WF03 registration seam: attach the widgets group to the main CLI."""

    cli.add_command(widgets)
    return cli


__all__ = ["register", "widgets"]
