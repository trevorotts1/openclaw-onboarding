"""Agent Studio commands for WF03 to register on the main CLI.

WF03 owns ``gohighlevel_cli.py``.  This module is the whole contribution: WF03
adds

    from cli_anything.gohighlevel import agent_studio_commands
    cli.add_command(agent_studio_commands.studio)

and nothing else.  Every verb is default-deny: the frozen capability gate
refuses until a recorded capability exists for the operation and tenant, and a
disabled call still returns a receipt.

Exit codes follow the existing workflow verbs: 0 ok, 1 refused/error,
3 unknown outcome (reconcile before any retry).
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

import click

from cli_anything.gohighlevel.public.agent_studio import (
    AgentStudioAdapter,
    ExecutionSession,
)
from cli_anything.gohighlevel.public.result import Status

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_UNKNOWN = 3


# ---------------------------------------------------------------------------
# adapter construction and shared helpers
# ---------------------------------------------------------------------------


def load_studio_adapter(
    location_id: str,
    *,
    env: Mapping[str, str] | None = None,
    transport: Any = None,
    capability: Any = None,
) -> tuple[AgentStudioAdapter | None, str]:
    """Build ``AgentStudioAdapter`` over the frozen public adapter.

    Returns ``(adapter, reason)``.  ``adapter`` is None when the public
    credential class cannot be resolved.  The gate is default-deny, so building
    the adapter can never send a request on its own.
    """

    try:
        from cli_anything.gohighlevel.public.adapter import PublicGhlAdapter
        from cli_anything.gohighlevel.public.auth import AuthKind, resolve_auth
    except Exception as exc:  # noqa: BLE001
        return None, "public Studio package unavailable: %s" % type(exc).__name__
    try:
        auth = resolve_auth(
            kind=AuthKind.location_pit, location_id=location_id, env=env
        )
    except Exception as exc:  # noqa: BLE001
        return None, "public credential unavailable: %s" % type(exc).__name__
    public = PublicGhlAdapter(auth=auth, transport=transport, capability=capability)
    return (
        AgentStudioAdapter(public=public),
        "public adapter built; gate is default-deny",
    )


def _location(ctx: click.Context, override: str | None = None) -> str:
    value = str(
        override
        or (ctx.obj or {}).get("location_id")
        or os.environ.get("GHL_LOCATION_ID", "")
    ).strip()
    if not value:
        click.echo(
            "Error: no location id. Pass --location-id, set GHL_LOCATION_ID, or "
            "run with the global option.",
            err=True,
        )
        raise SystemExit(EXIT_ERROR)
    return value


def _adapter(ctx: click.Context, override_location: str | None = None):
    location_id = _location(ctx, override_location)
    adapter, reason = load_studio_adapter(location_id)
    if adapter is None:
        click.echo("Error: " + reason, err=True)
        raise SystemExit(EXIT_ERROR)
    return adapter, location_id


def _tenant(location_id: str):
    from cli_anything.gohighlevel.public.auth import TenantBinding

    return TenantBinding(location_id=location_id, source="request")


def _approval(ref: str | None):
    """The existing approval seam; a missing approval stays missing (fail closed)."""

    from cli_anything.gohighlevel.public.adapter import ApprovalRef

    if ref and str(ref).strip():
        return ApprovalRef(ref=str(ref).strip())
    try:
        from cli_anything.gohighlevel.utils.workflow_builder import public_approval

        return public_approval()
    except Exception:  # noqa: BLE001 - absence is None, never an invented approval
        return None


def _command_errors(function):
    """Print a typed contract refusal instead of a traceback; exit 1."""

    import functools

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        from cli_anything.gohighlevel.public.errors import ContractViolation

        try:
            return function(*args, **kwargs)
        except ContractViolation as exc:
            click.echo(f"Error: {exc}", err=True)
            raise SystemExit(EXIT_ERROR)

    return wrapper


def _load_json(path: str, label: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        click.echo(f"Error: cannot read {label} {path}: {exc}", err=True)
        raise SystemExit(EXIT_ERROR)


def _emit(ctx: click.Context, result, label: str) -> None:
    """Print the receipt-backed outcome and set the exit code."""

    as_json = bool((ctx.obj or {}).get("json"))
    studio = dict((result.evidence or {}).get("agent_studio") or {})
    payload: dict[str, Any] = {
        "ok": result.status is Status.ok,
        "status": result.status.value,
        "operation_id": result.operation_id,
        "receipt_id": result.receipt_id,
        "status_detail": dict(studio),
    }
    if result.error:
        payload["error"] = dict(result.error)

    if as_json:
        click.echo(json.dumps(payload, indent=2, default=str))
    else:
        if label:
            click.echo(f"\n{label}")
            click.echo("-" * len(label))
        click.echo(f"status: {result.status.value}")
        click.echo(f"receipt: {result.receipt_id}")
        for key in (
            "agent_id",
            "staging_version_id",
            "version_id",
            "promoted_version_id",
            "previous_active_version_id",
            "execution_id",
            "output_validated",
            "tool_effects",
        ):
            if studio.get(key) is not None:
                click.echo(f"{key}: {studio[key]}")
        if result.error:
            click.echo(f"error: {result.error}", err=True)

    if result.status is Status.ok:
        return
    if result.status is Status.unknown_outcome:
        click.echo(
            "OUTCOME UNKNOWN: this write may have landed (receipt "
            f"{result.receipt_id}). Reconcile before any retry; do not repeat the "
            "write on another rail.",
            err=True,
        )
        raise SystemExit(EXIT_UNKNOWN)
    raise SystemExit(EXIT_ERROR)


# ---------------------------------------------------------------------------
# the command group
# ---------------------------------------------------------------------------


@click.group(name="studio")
def studio() -> None:
    """AI Agent Studio Flow Agents (staging, promotion, execution). Default-deny."""


@studio.command("create")
@click.option("--name", required=True, help="Approved agent name")
@click.option(
    "--version-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="JSON: the approved version-scoped graph document",
)
@click.option(
    "--metadata-file",
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="JSON: agent metadata (name/description/status). Graph fields refused.",
)
@click.option(
    "--allowed-tool",
    "allowed_tools",
    multiple=True,
    help="Allowlisted tool id a node may declare. Repeatable; empty means no "
    "node may declare a tool.",
)
@click.option("--approval-ref", default=None, help="Approval record reference")
@click.option("--location-id", "location_override", default=None)
@click.pass_context
@_command_errors
def studio_create(
    ctx: click.Context,
    name: str,
    version_file: str,
    metadata_file: str | None,
    allowed_tools: tuple[str, ...],
    approval_ref: str | None,
    location_override: str | None,
) -> None:
    """Create a Flow Agent. The created version is STAGING."""
    adapter, location_id = _adapter(ctx, location_override)
    version = _load_json(version_file, "version file")
    metadata = _load_json(metadata_file, "metadata file") if metadata_file else None
    result = adapter.create_agent(
        tenant=_tenant(location_id),
        name=name,
        version=version,
        approval=_approval(approval_ref),
        metadata=metadata,
        allowed_tools=list(allowed_tools),
    )
    _emit(ctx, result, "Agent Studio · create")


@studio.command("read")
@click.option("--agent-id", required=True)
@click.option("--location-id", "location_override", default=None)
@click.pass_context
@_command_errors
def studio_read(
    ctx: click.Context, agent_id: str, location_override: str | None
) -> None:
    """Read an agent and every version it carries."""
    adapter, location_id = _adapter(ctx, location_override)
    result, payload = adapter.read_agent_document(
        tenant=_tenant(location_id), agent_id=agent_id
    )
    if result.status is not Status.ok or payload is None:
        _emit(ctx, result, "Agent Studio · read")
        return
    if (ctx.obj or {}).get("json"):
        click.echo(json.dumps(payload, indent=2, default=str))
    else:
        click.echo(f"\nAgent {agent_id}")
        click.echo("-" * (6 + len(agent_id)))
        click.echo(json.dumps(payload, indent=2, default=str))
    click.echo(f"receipt: {result.receipt_id}")


@studio.command("update")
@click.option("--agent-id", required=True)
@click.option("--version-id", required=True)
@click.option(
    "--from-json",
    "intent_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="JSON: the approved intent merged into the CURRENT version",
)
@click.option(
    "--expected-version-file",
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="JSON: the version document the intent was reviewed against",
)
@click.option("--allow-deletions", is_flag=True, default=False)
@click.option("--allowed-tool", "allowed_tools", multiple=True)
@click.option("--approval-ref", default=None)
@click.option("--location-id", "location_override", default=None)
@click.pass_context
@_command_errors
def studio_update(
    ctx: click.Context,
    agent_id: str,
    version_id: str,
    intent_file: str,
    expected_version_file: str | None,
    allow_deletions: bool,
    allowed_tools: tuple[str, ...],
    approval_ref: str | None,
    location_override: str | None,
) -> None:
    """Patch one version, preserving every property not in the intent."""
    adapter, location_id = _adapter(ctx, location_override)
    intent = _load_json(intent_file, "intent file")
    expected = (
        _load_json(expected_version_file, "expected version file")
        if expected_version_file
        else None
    )
    result = adapter.update_version(
        tenant=_tenant(location_id),
        agent_id=agent_id,
        version_id=version_id,
        intent=intent,
        approval=_approval(approval_ref),
        expected_version=expected,
        allow_deletions=allow_deletions,
        allowed_tools=list(allowed_tools),
    )
    _emit(ctx, result, "Agent Studio · update")


@studio.command("promote")
@click.option("--agent-id", required=True)
@click.option("--version-id", required=True)
@click.option("--expected-active-version", default=None)
@click.option("--approval-ref", default=None)
@click.option("--location-id", "location_override", default=None)
@click.pass_context
@_command_errors
def studio_promote(
    ctx: click.Context,
    agent_id: str,
    version_id: str,
    expected_active_version: str | None,
    approval_ref: str | None,
    location_override: str | None,
) -> None:
    """Promote exactly the reviewed version to production."""
    adapter, location_id = _adapter(ctx, location_override)
    result = adapter.promote_version(
        tenant=_tenant(location_id),
        agent_id=agent_id,
        version_id=version_id,
        approval=_approval(approval_ref),
        expected_active_version=expected_active_version,
    )
    _emit(ctx, result, "Agent Studio · promote")


@studio.command("rollback")
@click.option("--agent-id", required=True)
@click.option("--to-version", default=None, help="Defaults to the recorded previous version")
@click.option("--approval-ref", default=None)
@click.option("--location-id", "location_override", default=None)
@click.pass_context
@_command_errors
def studio_rollback(
    ctx: click.Context,
    agent_id: str,
    to_version: str | None,
    approval_ref: str | None,
    location_override: str | None,
) -> None:
    """Roll back by promoting the previously active version."""
    adapter, location_id = _adapter(ctx, location_override)
    result = adapter.rollback(
        tenant=_tenant(location_id),
        agent_id=agent_id,
        approval=_approval(approval_ref),
        to_version_id=to_version,
    )
    _emit(ctx, result, "Agent Studio · rollback")


@studio.command("execute")
@click.option("--agent-id", required=True)
@click.option(
    "--payload-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="JSON: the documented execute request body",
)
@click.option(
    "--expect-file",
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="JSON: output fields the response must contain. Without it, ok is refused.",
)
@click.option("--contact-id", default=None)
@click.option("--thread-id", default=None)
@click.option("--version-policy", default="production", show_default=True)
@click.option("--approval-ref", default=None)
@click.option("--location-id", "location_override", default=None)
@click.pass_context
@_command_errors
def studio_execute(
    ctx: click.Context,
    agent_id: str,
    payload_file: str,
    expect_file: str | None,
    contact_id: str | None,
    thread_id: str | None,
    version_policy: str,
    approval_ref: str | None,
    location_override: str | None,
) -> None:
    """Execute the published production version and validate its output."""
    adapter, location_id = _adapter(ctx, location_override)
    payload = _load_json(payload_file, "payload file")
    expect = _load_json(expect_file, "expect file") if expect_file else None
    result = adapter.execute(
        tenant=_tenant(location_id),
        agent_id=agent_id,
        payload=payload,
        approval=_approval(approval_ref),
        output_expect=expect,
        contact_id=contact_id,
        thread_id=thread_id,
        version_policy=version_policy,
    )
    _emit(ctx, result, "Agent Studio · execute")


@studio.command("session")
@click.option("--execution-id", required=True)
@click.pass_context
@_command_errors
def studio_session(ctx: click.Context, execution_id: str) -> None:
    """Show the local binding of an execution id (location/agent/version/contact)."""
    adapter, _location_id = _adapter(ctx)
    session: ExecutionSession | None = adapter.session(execution_id)
    if session is None:
        click.echo(
            "Error: no bound session for that execution id in this process.",
            err=True,
        )
        raise SystemExit(EXIT_ERROR)
    click.echo(json.dumps(session.as_mapping(), indent=2, default=str))
