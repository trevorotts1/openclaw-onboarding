"""capabilities family commands (owner WF01). Registered by WF03.

This family has no HTTP operation of its own: a capability is a property of a
frozen registry row, not an endpoint. Every answer here is read from
``public.operations`` -- the contract declarations (``capability_map``) and, for
one tenant, the default-deny ``CapabilityGate``. Nothing is invented: a row
absent from the registry is reported absent, and the gate's answer for an
unlisted row is a denial with its own reason.
"""
from __future__ import annotations

import json

import click

from ..public.capability import CapabilityGate
from ..public.operations import OPERATIONS, capability_map

FAMILY = "capabilities"
OWNER = "WF01"

def _emit(ctx: click.Context, payload) -> None:
    """Registry contracts are structures, not tables: always JSON."""
    click.echo(json.dumps(payload, indent=2, default=str))

@click.group(name=FAMILY, help="%s family commands (%s). Registry declarations "
                              "and the default-deny capability answer."
                              % (FAMILY, OWNER))
def capabilities() -> None:
    """Capability declarations and gate answers for the frozen registry."""

@capabilities.command(name="catalog")
@click.option("--route-class", default=None,
              help="Only rows declaring this route_class.")
@click.pass_context
def catalog(ctx: click.Context, route_class: str | None) -> None:
    """Every frozen row's declared capability, one entry per operation."""
    mapping = capability_map()
    if route_class:
        mapping = {k: v for k, v in mapping.items() if v.get("routeClass") == route_class}
    _emit(ctx, {"rows": len(mapping), "operations": mapping})

@capabilities.command(name="show")
@click.argument("operation_id")
@click.pass_context
def show(ctx: click.Context, operation_id: str) -> None:
    """One frozen row's full shared contract, plus the gate answer if a tenant is bound."""
    row = OPERATIONS.get(operation_id)
    if row is None:
        click.echo(
            "Error: the frozen registry has no row for %r. Nothing is invented "
            "here; name the row with its owner workflow and file a change "
            "request against WF00." % (operation_id,),
            err=True,
        )
        ctx.exit(1)
    payload: dict = {"contract": row.as_contract()}
    location_id = ctx.obj.get("location_id")
    if location_id:
        payload["gate"] = _gate_payload(str(location_id), operation_id)
    else:
        payload["gate"] = {
            "tenant": None,
            "answer": "unbound",
            "reason": "no tenant bound; pass --location-id for this tenant's answer",
        }
    _emit(ctx, payload)
    ctx.exit(0)

@capabilities.command(name="gate")
@click.argument("operation_id")
@click.pass_context
def gate(ctx: click.Context, operation_id: str) -> None:
    """The default-deny gate answer for one operation and this tenant."""
    if operation_id not in OPERATIONS:
        click.echo(
            "Error: the frozen registry has no row for %r." % (operation_id,), err=True
        )
        ctx.exit(1)
    location_id = ctx.obj.get("location_id")
    if not location_id:
        click.echo(
            "Error: no location id. Pass --location-id or set GHL_LOCATION_ID.",
            err=True,
        )
        ctx.exit(1)
    payload = _gate_payload(str(location_id), operation_id)
    _emit(ctx, payload)
    ctx.exit(0 if payload["enabled"] else 1)

def _gate_payload(location_id: str, operation_id: str) -> dict:
    capability = CapabilityGate(tenant=location_id).get(operation_id)
    blocked = capability.activation_blocked
    return {
        "tenant": location_id,
        "operation_id": operation_id,
        "enabled": bool(capability.enabled),
        "activation": capability.activation,
        "blocked_reason": None if blocked is None else getattr(blocked, "reason", None),
        "blocked_owner": None if blocked is None else getattr(blocked, "owner", None),
        "unblock": None if blocked is None else getattr(blocked, "unblock", None),
    }

def build() -> click.Group:
    return capabilities

def register(cli) -> None:
    cli.add_command(capabilities)
