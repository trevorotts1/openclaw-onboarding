"""Legacy alias map and explicit UNMAPPED table.

Frozen by evidence/W01/GU-004-CONTRACT-FREEZE.md section 4.

Nothing is dropped.  Every alias observed by the audit either resolves to a
target here, or appears in ``UNMAPPED`` with a reason.  A community MCP tool
name resolves to the caller's *intent* and its replacement operation id -- it
never makes the community transport a valid route.

``ghl-mcp`` is a real name collision and is resolved by context, not by string
matching:

* in ``mcp.servers`` it is the **official MCP connection name** and is
  preserved (``36-ghl-mcp-setup/INSTALL.md:325``);
* in ``systemd`` it is the **retired community service unit**
  (``36-ghl-mcp-setup/SKILL.md:132``) and must be stopped by retirement.

Calling ``resolve_service_alias("ghl-mcp")`` without ``context`` refuses.
Retirement code must never grep ``ghl-mcp`` and assume one meaning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .auth import AuthKind
from .errors import ContractViolation
from .operations import OPERATIONS

AliasKind = Literal[
    "operation",
    "auth_kind",
    "tenant",
    "file",
    "route",
    "service",
    "approval",
    "control",
    "collision",
]

TENANT_TARGET = "location_id"


@dataclass(frozen=True)
class AliasResolution:
    alias: str
    kind: AliasKind
    target: str | None
    note: str = ""


@dataclass(frozen=True)
class UnmappedAlias:
    alias: str
    category: str
    reason: str
    evidence: str


def _norm(alias: str) -> str:
    return alias.strip().lower()


# ---------------------------------------------------------------------------
# 4.1 Credential aliases -> auth class
# ---------------------------------------------------------------------------
_AUTH_ALIASES: dict[str, AuthKind] = {
    # location PIT
    "GOHIGHLEVEL_API_KEY": AuthKind.location_pit,
    "GHL_API_KEY": AuthKind.location_pit,
    "GHL_PIT": AuthKind.location_pit,
    "GHL_TOKEN": AuthKind.location_pit,
    "GHL_PRIVATE_INTEGRATION_TOKEN": AuthKind.location_pit,
    "PRIVATE_INTEGRATION_TOKEN": AuthKind.location_pit,
    "GHL_PRIVATE_TOKEN": AuthKind.location_pit,
    "PIT_TOKEN": AuthKind.location_pit,
    "GHL_PIT_TOKEN": AuthKind.location_pit,
    "GOHIGHLEVEL_LOCATION_PIT": AuthKind.location_pit,
    "GHL_LOCATION_PIT": AuthKind.location_pit,
    "GOHIGHLEVEL_PIT": AuthKind.location_pit,
    "GOHIGHLEVEL_CF_PIT": AuthKind.location_pit,
    "CONVERT_AND_FLOW_API_KEY": AuthKind.location_pit,
    "CONVERT_AND_FLOW_PIT": AuthKind.location_pit,
    "CONVERT_AND_FLOW_PRIVATE_INTEGRATION_TOKEN": AuthKind.location_pit,
    "CONVERTANDFLOW_API_KEY": AuthKind.location_pit,
    "CONVERTFLOW_API_KEY": AuthKind.location_pit,
    "PODCAST_ENGINE_GHL_PIT": AuthKind.location_pit,
    # Firebase refresh token
    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": AuthKind.firebase_internal,
    "CAF_FIREBASE_REFRESH_TOKEN": AuthKind.firebase_internal,
    "GHL_FIREBASE_REFRESH_TOKEN": AuthKind.firebase_internal,
}

# Highest-precedence *_FILE inputs (contents are the value).
_FILE_ALIASES: dict[str, str] = {
    "GHL_REFRESH_TOKEN_FILE": "firebase_internal",
    "GHL_LOCATION_PIT_FILE": "location_pit",
    "GHL_LOCATION_ID_FILE": TENANT_TARGET,
}

# ---------------------------------------------------------------------------
# 4.1 Location id (tenant binding)
# ---------------------------------------------------------------------------
_TENANT_ALIASES: tuple[str, ...] = (
    "GHL_LOCATION_ID",
    "GOHIGHLEVEL_LOCATION_ID",
    "GOHIGHLEVEL_ALLOWED_LOCATION_IDS",
    "CONVERT_AND_FLOW_LOCATION_ID",
    "convert_and_flow_location",
    "CAF_LOCATION_ID",
    "CAF_ALLOWED_LOCATION_IDS",
    "HIGHLEVEL_LOCATION_ID",
    "PODCAST_ENGINE_GHL_LOCATION_ID",
)

# ---------------------------------------------------------------------------
# 4.2 Community MCP tool names -> operation id (retired transport)
# ---------------------------------------------------------------------------
_COMMUNITY_TOOLS: dict[str, str] = {
    "ghl_list_products": "products.list",
    "ghl_get_product": "products.get",
    "ghl_create_product": "products.create",
    "ghl_update_product": "products.update",
    "ghl_delete_product": "products.delete",
    "ghl_create_price": "products.prices.create",
    "ghl_list_prices": "products.prices.list",
    "list_invoices": "invoices.list",
    "get_invoice": "invoices.get",
    "create_invoice": "invoices.create",
    "send_invoice": "invoices.send",
    "create_invoice_schedule": "invoices.schedules.create",
    "list_subscriptions": "subscriptions.list",
    "get_subscription_by_id": "subscriptions.get",
    "list_estimates": "estimates.list",
    "create_estimate": "estimates.create",
    "send_estimate": "estimates.send",
    "list_orders": "orders.list",
    "get_order_by_id": "orders.get",
    "list_transactions": "transactions.list",
    "get_transaction_by_id": "transactions.get",
    "record_order_payment": "orders.recordPayment",
    "list_coupons": "coupons.list",
    "get_coupon": "coupons.get",
    "create_coupon": "coupons.create",
    "update_coupon": "coupons.update",
    "delete_coupon": "coupons.delete",
    "ghl_list_workflows": "workflows.list",
    "ghl_get_workflow": "workflows.definition.read",
    "ghl_trigger_workflow": "workflows.enroll",
    "ghl_publish_workflow": "workflows.status.publish",
}

# Frozen fallbacks stated in section 4.2.  Never selected silently.
_FALLBACKS: dict[str, tuple[str, ...]] = {
    "ghl_get_workflow": ("workflows.private.get",),
    "ghl_publish_workflow": ("workflows.private.publish",),
}

# ---------------------------------------------------------------------------
# 4.3 Official MCP tool names -> operation id
# ---------------------------------------------------------------------------
_OFFICIAL_TOOLS: dict[str, str] = {
    "list_locations": "mcp.list_locations",
    "search_operations": "mcp.search_operations",
    "describe_operation": "mcp.describe_operation",
    "execute_operation": "mcp.execute_operation",
}

# ---------------------------------------------------------------------------
# 4.4 Routes, services, controls
# ---------------------------------------------------------------------------
_ROUTE_ALIASES: dict[str, str] = {
    "caf": "skill44_private",
    "convertandflow": "skill44_private",
    "ghl": "skill44_private",
}

_SERVICE_ALIASES: dict[str, str] = {
    "leadconnector": "official_mcp_client",
    "ghl-community-mcp": "retired_community_service",
}

_CONTROL_ALIASES: dict[str, str] = {
    "CAF_APPROVAL_TOKEN": "approval_ref",
    "CAF_DRY_RUN": "capability_disabled",
}

# The collision, named explicitly so no lane string-matches it.
NAME_COLLISIONS: dict[str, dict[str, str]] = {
    "ghl-mcp": {
        "mcp.servers": "official_mcp_connection",
        "systemd": "retired_community_service",
    }
}

# ---------------------------------------------------------------------------
# Resolved table
# ---------------------------------------------------------------------------
_RESOLVED: dict[str, AliasResolution] = {}


def _add(alias: str, kind: AliasKind, target: str, note: str = "") -> None:
    key = _norm(alias)
    if key in _RESOLVED:
        raise ContractViolation("alias_duplicate", detail={"alias": alias})
    _RESOLVED[key] = AliasResolution(alias=alias, kind=kind, target=target, note=note)


for _alias, _kind in _AUTH_ALIASES.items():
    _add(_alias, "auth_kind", _kind.value)
for _alias in _TENANT_ALIASES:
    _add(_alias, "tenant", TENANT_TARGET)
for _alias, _target in _FILE_ALIASES.items():
    _add(_alias, "file", _target)
for _alias, _target in _COMMUNITY_TOOLS.items():
    _add(_alias, "operation", _target, note="community_mcp_retired")
for _alias, _target in _OFFICIAL_TOOLS.items():
    _add(_alias, "operation", _target, note="official_mcp_tool")
for _alias, _target in _ROUTE_ALIASES.items():
    _add(_alias, "route", _target)
for _alias, _target in _SERVICE_ALIASES.items():
    _add(_alias, "service", _target)
for _alias, _target in _CONTROL_ALIASES.items():
    _add(_alias, "control", _target)
# ``ghl-mcp`` is deliberately absent from the flat table: it resolves only
# through ``resolve_service_alias(name, context=...)``.
_add("ghl-mcp", "collision", None, note="context_required")


# ---------------------------------------------------------------------------
# UNMAPPED (section 4.1 agency + GHL_LOC, 4.2, 4.3)
# ---------------------------------------------------------------------------
_UNMAPPED_ROWS: tuple[UnmappedAlias, ...] = (
    UnmappedAlias(
        "GOHIGHLEVEL_AGENCY_PIT", "credential",
        "agency PIT is never substituted for a location PIT; no operation in "
        "the freeze accepts agency auth.",
        "GU-004 section 4.1; 06-ghl-install-pages/tools/ghl_media.py:236-243",
    ),
    UnmappedAlias(
        "GOHIGHLEVEL_AGENCY_API_KEY", "credential",
        "agency PIT alias; read only to produce a fail-loud message.",
        "GU-004 section 4.1",
    ),
    UnmappedAlias(
        "GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT", "credential",
        "agency PIT alias; read only to produce a fail-loud message.",
        "GU-004 section 4.1",
    ),
    UnmappedAlias(
        "GHL_AGENCY_PIT", "credential",
        "agency PIT alias; read only to produce a fail-loud message.",
        "GU-004 section 4.1",
    ),
    UnmappedAlias(
        "GHL_LOC", "tenant",
        "installer-local shell variable, not an environment alias; mapping it "
        "would invent a resolution path.",
        "INSTALL.md:320; settle with a read of wire.sh at W07",
    ),
    UnmappedAlias(
        "ghl_create_product_collection", "community_tool",
        "no audited public operation row; not invented.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "ghl_list_product_collections", "community_tool",
        "no audited public operation row; not invented.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "ghl_list_inventory", "community_tool",
        "no audited public operation row; not invented.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "ghl_bulk_edit_products", "community_tool",
        "no audited public operation row; not invented.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "update_invoice", "community_tool",
        "no audited public operation row; settle with describe_operation.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "delete_invoice", "community_tool",
        "no audited public operation row; settle with describe_operation.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "view_invoice", "community_tool",
        "no audited public operation row.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "generate_invoice_number", "community_tool",
        "no audited public operation row.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "list_invoice_schedules", "community_tool",
        "only invoices.schedules.create is audited.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "get_invoice_schedule", "community_tool",
        "only invoices.schedules.create is audited.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "update_invoice_schedule", "community_tool",
        "only invoices.schedules.create is audited.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "update_saas_subscription", "community_tool",
        "no audited public operation row.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "rebilling_update", "community_tool",
        "no audited public operation row.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "create_invoice_from_estimate", "community_tool",
        "no audited public operation row.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "generate_estimate_number", "community_tool",
        "no audited public operation row.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "list_gateways", "community_tool",
        "no audited public operation row.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "create_voice_ai_agent", "community_tool",
        "Voice AI domain not audited; retirement only.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "update_voice_ai_agent", "community_tool",
        "Voice AI domain not audited; retirement only.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "list_voice_ai_agents", "community_tool",
        "Voice AI domain not audited; retirement only.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "get_voice_ai_call_log", "community_tool",
        "Voice AI domain not audited; retirement only.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "ghl_buy_phone_number", "community_tool",
        "Phone System domain not audited.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "ghl_list_phone_numbers", "community_tool",
        "Phone System domain not audited.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "update_phone_number", "community_tool",
        "Phone System domain not audited.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "ghl_get_call_recording", "community_tool",
        "Phone System domain not audited.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "update_call_forwarding", "community_tool",
        "Phone System domain not audited.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "ghl_create_agent", "community_tool",
        "Agent Studio not audited.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "ghl_update_agent", "community_tool",
        "Agent Studio not audited.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "ghl_deploy_agent", "community_tool",
        "Agent Studio not audited.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "ghl_list_agents", "community_tool",
        "Agent Studio not audited.",
        "GU-004 section 4.2",
    ),
    UnmappedAlias(
        "ghl_create_workflow", "community_tool",
        "internal wrapper documented as unverified; mapping it to V4 would "
        "launder an undocumented endpoint into a public contract.",
        "36-ghl-mcp-setup/INSTRUCTIONS.md:86",
    ),
    UnmappedAlias(
        "ghl_update_workflow_actions", "community_tool",
        "internal wrapper documented as unverified; mapping it to V4 would "
        "launder an undocumented endpoint into a public contract.",
        "36-ghl-mcp-setup/INSTRUCTIONS.md:86",
    ),
    UnmappedAlias(
        "search", "official_tool",
        "listed in the local SKILL.md but not on the official MCP page "
        "fetched 2026-10-18; unverified legacy name.",
        "36-ghl-mcp-setup/SKILL.md:39-42",
    ),
    UnmappedAlias(
        "fetch", "official_tool",
        "listed in the local SKILL.md but not on the official MCP page "
        "fetched 2026-10-18; unverified legacy name.",
        "36-ghl-mcp-setup/SKILL.md:39-42",
    ),
)

UNMAPPED: dict[str, UnmappedAlias] = {row.alias: row for row in _UNMAPPED_ROWS}
_UNMAPPED_BY_KEY: dict[str, UnmappedAlias] = {
    _norm(row.alias): row for row in _UNMAPPED_ROWS
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def lookup_alias(alias: str) -> AliasResolution | None:
    """Return a resolution, or ``None`` for unknown/unmapped aliases."""

    if not isinstance(alias, str) or not alias.strip():
        return None
    return _RESOLVED.get(_norm(alias))


def resolve_alias(alias: str) -> AliasResolution:
    if not isinstance(alias, str) or not alias.strip():
        raise ContractViolation("alias_invalid")
    resolution = _RESOLVED.get(_norm(alias))
    if resolution is not None:
        if resolution.kind == "collision":
            raise ContractViolation(
                "alias_collision_context_required",
                detail={"alias": alias, "contexts": sorted(NAME_COLLISIONS[_norm(alias)])},
            )
        return resolution
    unmapped = _UNMAPPED_BY_KEY.get(_norm(alias))
    if unmapped is not None:
        raise ContractViolation(
            "alias_unmapped",
            detail={"alias": alias, "category": unmapped.category, "reason": unmapped.reason},
        )
    raise ContractViolation("alias_unknown", detail={"alias": alias})


def resolve_operation_alias(alias: str) -> str:
    resolution = resolve_alias(alias)
    if resolution.kind != "operation" or resolution.target is None:
        raise ContractViolation(
            "alias_not_an_operation",
            detail={"alias": alias, "kind": resolution.kind},
        )
    return resolution.target


def resolve_credential_alias(alias: str) -> AuthKind:
    resolution = resolve_alias(alias)
    if resolution.kind not in ("auth_kind", "file") or resolution.target is None:
        raise ContractViolation(
            "alias_not_a_credential",
            detail={"alias": alias, "kind": resolution.kind},
        )
    try:
        return AuthKind(resolution.target)
    except ValueError:
        raise ContractViolation(
            "alias_file_target_not_auth",
            detail={"alias": alias, "target": resolution.target},
        ) from None


def resolve_tenant_alias(alias: str) -> str:
    resolution = resolve_alias(alias)
    if resolution.kind not in ("tenant", "file") or resolution.target != TENANT_TARGET:
        raise ContractViolation(
            "alias_not_a_tenant",
            detail={"alias": alias, "kind": resolution.kind},
        )
    return TENANT_TARGET


def fallbacks_for(alias: str) -> tuple[str, ...]:
    """Explicit fallbacks recorded in section 4.2; never auto-selected."""

    if not isinstance(alias, str):
        return ()
    for name, targets in _FALLBACKS.items():
        if _norm(name) == _norm(alias):
            return targets
    return ()


def resolve_service_alias(name: str, *, context: str) -> str:
    """Resolve a service/connection name that may be a known collision."""

    key = _norm(name)
    collision = NAME_COLLISIONS.get(key)
    if collision is not None:
        try:
            return collision[context]
        except KeyError:
            raise ContractViolation(
                "alias_collision_context_required",
                detail={"alias": name, "contexts": sorted(collision)},
            ) from None
    resolution = _RESOLVED.get(key)
    if resolution is not None and resolution.kind == "service" and resolution.target:
        return resolution.target
    raise ContractViolation("service_alias_unknown", detail={"alias": name})


def _validate() -> None:
    for key, resolution in _RESOLVED.items():
        if key in _UNMAPPED_BY_KEY:
            raise ContractViolation("alias_both_resolved_and_unmapped", detail={"alias": resolution.alias})
        if resolution.kind == "operation":
            if resolution.target not in OPERATIONS:
                raise ContractViolation(
                    "alias_target_not_in_registry",
                    detail={"alias": resolution.alias, "target": resolution.target},
                )
    for key, unmapped in _UNMAPPED_BY_KEY.items():
        if key in _RESOLVED:
            raise ContractViolation("alias_both_resolved_and_unmapped", detail={"alias": unmapped.alias})
        if not unmapped.reason.strip() or not unmapped.evidence.strip():
            raise ContractViolation("unmapped_alias_without_reason", detail={"alias": unmapped.alias})
    for target in _FALLBACKS.values():
        for operation_id in target:
            if operation_id not in OPERATIONS:
                raise ContractViolation(
                    "fallback_target_not_in_registry", detail={"target": operation_id}
                )


_validate()

__all__ = [
    "AliasResolution",
    "UnmappedAlias",
    "UNMAPPED",
    "NAME_COLLISIONS",
    "resolve_alias",
    "lookup_alias",
    "resolve_operation_alias",
    "resolve_credential_alias",
    "resolve_tenant_alias",
    "resolve_service_alias",
    "fallbacks_for",
]
