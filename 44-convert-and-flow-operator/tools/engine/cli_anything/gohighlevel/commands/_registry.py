"""Shared plumbing for family command modules (WF03).

A family module owns a set of FROZEN registry rows and nothing else. It never
declares an operation id, a method, a path, a Version or a scope of its own:
every one of those is read from ``public.operations.OPERATIONS`` when the
module is registered. If the registry has no row, the family has no command --
it is reported pending with its owning workflow id (``commands.FAMILIES``).

Route discipline is the CLI owner's (WF03, Document 1 s6.6):

* a row whose ``route_class`` is not ``public_direct`` is refused with its own
  named route class and blocker -- a family never substitutes a private or
  authoring route, and never constructs a private client;
* a ``public_direct`` row needs no ``--experimental`` because no private token
  is involved;
* ``--dry-run`` prints the frozen method/path/Version/payload and sends nothing.
"""
from __future__ import annotations

import json
import os
from typing import Any, Mapping, Sequence

import click

from ..public.operations import OperationRow, OPERATIONS

PUBLIC_ROUTE = "public_direct"

def rows_for(
    roots: Sequence[str], extra: Sequence[str] = ()
) -> tuple[OperationRow, ...]:
    """The frozen rows this family owns, in registry order.

    ``roots`` are operation-id prefixes; ``extra`` are exact ids that do not
    sit under one of the roots (e.g. ``workflows.search``). An id in ``extra``
    that the registry does not carry is a programming error, not a silent skip.
    """
    selected: dict[str, OperationRow] = {}
    for operation_id, row in OPERATIONS.items():
        if any(operation_id.startswith(root) for root in roots):
            selected[operation_id] = row
    for operation_id in extra:
        if operation_id not in OPERATIONS:
            raise KeyError("registry has no row for %r" % (operation_id,))
        selected[operation_id] = OPERATIONS[operation_id]
    return tuple(selected[key] for key in sorted(selected))

def command_name(operation_id: str) -> str:
    """CLI name for one row: the full operation id, dots as dashes.

    Keeping the full id (``workflows-logs-list``) rather than the bare tail
    keeps two rows in one family from colliding on a shared tail such as
    ``list``.
    """
    return operation_id.replace(".", "-")

def _plan(row: OperationRow, path_params: Mapping[str, str],
          query: Mapping[str, Any] | None, body: Mapping[str, Any] | None) -> dict:
    return {
        "dry_run": True,
        "operation_id": row.operation_id,
        "method": row.method,
        "path_template": row.path_template,
        "version": row.version,
        "write": row.write,
        "approval_class": row.resolved_approval_class,
        "availability": row.resolved_availability,
        "route_class": row.route_class,
        "blocker": row.blocker,
        "path_params": dict(path_params),
        "query": dict(query or {}),
        "body": body,
    }

def _emit(ctx: click.Context, payload: Mapping[str, Any]) -> None:
    click.echo(json.dumps(payload, indent=2, default=str))

def _adapter(location_id: str):
    """Build the frozen public adapter for one location.

    Construction is inert: the capability gate is default-deny and no request
    is sent until ``dispatch`` is called.
    """
    from ..public.adapter import PublicGhlAdapter
    from ..public.auth import AuthKind, resolve_auth

    auth = resolve_auth(kind=AuthKind.location_pit, location_id=location_id)
    return PublicGhlAdapter(auth=auth)

def invoke(
    ctx: click.Context,
    row: OperationRow,
    path_params: Mapping[str, str],
    query: Mapping[str, Any] | None,
    body: Mapping[str, Any] | None,
    approval_ref: str | None,
) -> None:
    """Dispatch ONE frozen row through the public adapter, or refuse and say why."""
    if row.route_class != PUBLIC_ROUTE:
        click.echo(
            "Error: %s is not a public operation (route_class=%s, blocker=%s). "
            "This family command has no other rail and does not substitute one."
            % (row.operation_id, row.route_class, row.blocker),
            err=True,
        )
        ctx.exit(1)

    plan = _plan(row, path_params, query, body)
    if ctx.obj.get("dry_run") or os.environ.get("CAF_DRY_RUN") == "true":
        _emit(ctx, plan)
        ctx.exit(0)

    location_id = ctx.obj.get("location_id")
    if not location_id:
        click.echo(
            "Error: no location id. Pass --location-id or set GHL_LOCATION_ID.",
            err=True,
        )
        ctx.exit(1)

    from ..public.adapter import ApprovalRef
    from ..public.auth import TenantBinding

    approval = ApprovalRef(ref=approval_ref, kind="gate_token") if approval_ref else None
    adapter = _adapter(str(location_id))
    result = adapter.dispatch(
        operation_id=row.operation_id,
        tenant=TenantBinding(location_id=str(location_id), source="request"),
        path_params=dict(path_params) or None,
        query=dict(query) if query else None,
        body=dict(body) if body else None,
        approval=approval,
    )
    _emit(ctx, {
        "operation_id": result.operation_id,
        "status": str(result.status),
        "receipt_id": result.receipt_id,
        "http_status": result.http_status,
        "version_header": result.version_header,
        "readback": None if result.readback is None else str(result.readback.status),
        "error": dict(result.error) if result.error else None,
        "evidence": dict(result.evidence),
    })
    ctx.exit(0 if str(result.status) == "ok" else 1)

def _command(row: OperationRow) -> click.Command:
    @click.command(name=command_name(row.operation_id),
                   help="%s %s (Version %s)%s"
                        % (row.method, row.path_template, row.version,
                           "" if not row.write else " [write]"))
    @click.option("--path-param", "path_params", multiple=True,
                  metavar="NAME=VALUE", help="Value for one {placeholder} in the path.")
    @click.option("--query-json", default=None, help="JSON object of query parameters.")
    @click.option("--body-json", default=None, help="JSON object of the request body.")
    @click.option("--approval-ref", default=None,
                  help="Approval seam name for a write (value is never recorded).")
    @click.pass_context
    def _run(ctx, path_params, query_json, body_json, approval_ref):
        params: dict[str, str] = {}
        for item in path_params:
            name, sep, value = item.partition("=")
            if not sep or not name.strip():
                raise click.BadParameter("expected NAME=VALUE, got %r" % (item,))
            params[name.strip()] = value
        invoke(ctx, row, params,
               json.loads(query_json) if query_json else None,
               json.loads(body_json) if body_json else None,
               approval_ref)

    return _run

def family_group(
    name: str,
    owner: str,
    roots: Sequence[str],
    extra: Sequence[str] = (),
    summary: str = "",
) -> click.Group:
    """Build the click group for one family from its frozen rows."""
    rows = rows_for(roots, extra)
    group = click.Group(
        name=name,
        help="%s family commands (%s). %s rows, all from the frozen registry."
             % (name, owner, len(rows)),
        short_help=summary or "%s commands" % name,
    )
    for row in rows:
        group.add_command(_command(row))
    return group

def register_group(cli: click.Group, group: click.Group) -> None:
    cli.add_command(group)
