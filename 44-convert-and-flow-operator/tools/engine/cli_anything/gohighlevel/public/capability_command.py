"""Capability probe command module (WF01).

Owner: WF01 (GHL-001). Registration in ``gohighlevel_cli.py`` belongs to WF03
(GHL-003); ``register()`` is the seam it calls.  Nothing here is registered by
this module itself.

Two rules shape this module:

* the beta probe is a READ.  ``GET /workflows/step-types?locationId=...&limit=1``
  with ``Version: v3`` is the documented first network check (Document 1
  section 4.3).  No write discovers enablement, ever;
* a disabled/unimplemented capability still returns a useful refusal receipt
  and makes zero writes (IG-ROUTE-10).  A refusal is a result, not a crash and
  not a silent success.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .auth import AuthContext, auth_headers
from .capability import (
    DEFAULT_FALLBACK_POLICY,
    WORKFLOW_BETA_ERROR_CODE,
    classify_failure,
)
from .errors import ContractViolation, CredentialMissing
from .result import canonical_json, redact_headers
from .transport import RequestsTransport, Transport

WORKFLOW_PROBE_OPERATION = "workflows.step_types.read"
WORKFLOW_STEP_TYPES_PATH = "/workflows/step-types"
#: The probe carries the Version of its own documented operation page
#: (Document 1 section 4.3 shows ``Version: v3`` for this read).  There is no
#: module-level version default: the value is a per-call parameter, and a
#: caller holding a registry row passes that row's literal instead.
PROBE_FAMILIES: frozenset[str] = frozenset({"workflows"})


@dataclass(frozen=True)
class ProbeResult:
    """A redacted, machine-readable probe result.  Never contains a token."""

    family: str
    tenant: str
    operation: str
    method: str
    http_status: int | None
    provider_code: str | None
    classification: str
    public_beta_state: str
    available_route: str
    credential_ref: str
    credential_fingerprint: str
    checked_at: str
    read_only: bool
    refused: bool
    refusal_reason: str | None
    response_headers: Mapping[str, str]
    last_error: str | None = None

    def as_document(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "tenant": self.tenant,
            "operation": self.operation,
            "method": self.method,
            "http_status": self.http_status,
            "provider_code": self.provider_code,
            "classification": self.classification,
            "public_beta_state": self.public_beta_state,
            "available_route": self.available_route,
            "credential_ref": self.credential_ref,
            "credential_fingerprint": self.credential_fingerprint,
            "checked_at": self.checked_at,
            "read_only": bool(self.read_only),
            "refused": bool(self.refused),
            "refusal_reason": self.refusal_reason,
            "response_headers": dict(self.response_headers),
            "last_error": self.last_error,
        }


def credential_fingerprint(auth: AuthContext) -> str:
    """A NON-SECRET fingerprint of the credential reference, never the value."""

    material = canonical_json(
        {"kind": auth.kind.value, "source": auth.source, "tenant": auth.location_id}
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def probe_workflow_family(
    *,
    tenant: str,
    auth: AuthContext,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
    version: str = "v3",
) -> ProbeResult:
    """The read-only beta probe for the Workflows family.

    One GET.  ``beta_not_enabled`` is recorded as such and the authorized
    private fallback is named; a 401 is never called a beta flag.
    """

    if not isinstance(tenant, str) or not tenant.strip():
        raise ContractViolation("tenant_required")
    if not isinstance(auth, AuthContext):
        raise ContractViolation("auth_required")
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    result_common = {
        "family": "workflows",
        "tenant": tenant,
        "operation": WORKFLOW_PROBE_OPERATION,
        "method": "GET",
        "credential_ref": auth.source,
        "credential_fingerprint": credential_fingerprint(auth),
        "checked_at": now.isoformat(),
        "read_only": True,
    }
    try:
        headers = auth_headers(auth)
    except CredentialMissing as missing:
        return ProbeResult(
            http_status=None,
            provider_code=None,
            classification="unauthorized",
            public_beta_state="unknown",
            available_route="none",
            refused=True,
            refusal_reason="credential_missing",
            response_headers={},
            last_error=missing.rule,
            **result_common,
        )

    caller = transport or RequestsTransport()
    response = caller.request(
        method="GET",
        url=WORKFLOW_STEP_TYPES_PATH,
        version=str(version),
        headers=headers,
        query={"limit": 1, "locationId": tenant},
        body=None,
        timeout_s=30.0,
    )
    classification = classify_failure(
        http_status=response.status if response.error_kind == "none" else None,
        body=response.body,
        transport_error=response.error_kind,
        write=False,
    )
    beta_state = {
        "ok": "enabled",
        "beta_not_enabled": "beta_not_enabled",
    }.get(classification.kind, "unknown")
    route = {
        "ok": "public_rest",
        "beta_not_enabled": "private_fallback",
        "rate_limited": "none",
        "unauthorized": "none",
        "missing_scope": "none",
        "wrong_role": "none",
        "forbidden": "none",
    }.get(classification.kind, "none")
    return ProbeResult(
        http_status=classification.http_status,
        provider_code=classification.provider_code,
        classification=classification.kind,
        public_beta_state=beta_state,
        available_route=route,
        refused=classification.kind != "ok",
        refusal_reason=None if classification.kind == "ok" else classification.kind,
        response_headers=redact_headers(response.headers),
        **result_common,
    )


def probe_family(
    *,
    family: str,
    tenant: str,
    auth: AuthContext,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
    version: str = "v3",
) -> ProbeResult:
    """Dispatch one family probe.  An unimplemented family refuses honestly."""

    text = str(family or "").strip().lower()
    if text in PROBE_FAMILIES:
        return probe_workflow_family(
            tenant=tenant, auth=auth, transport=transport, clock=clock, version=version
        )
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    return ProbeResult(
        family=text,
        tenant=str(tenant),
        operation=text + ".probe",
        method="GET",
        http_status=None,
        provider_code=None,
        classification="unavailable",
        public_beta_state="unknown",
        available_route="none",
        credential_ref=auth.source,
        credential_fingerprint=credential_fingerprint(auth),
        checked_at=now.isoformat(),
        read_only=True,
        refused=True,
        refusal_reason="probe_family_unimplemented",
        response_headers={},
    )


# ---------------------------------------------------------------------------
# CLI seam (WF03 registers this group in gohighlevel_cli.py)
# ---------------------------------------------------------------------------

def register(cli_group: Any) -> None:
    """Attach the ``capabilities`` group to an existing click group."""

    import click

    @click.group()
    def capabilities() -> None:
        """Capability evidence: read-only probes and route decisions."""

    @capabilities.command("probe")
    @click.option("--family", default="workflows", show_default=True)
    @click.option(
        "--read-only/--no-read-only",
        default=True,
        help="Only the read-only probe exists; --no-read-only is refused.",
    )
    @click.pass_context
    def probe(ctx: click.Context, family: str, read_only: bool) -> None:
        """Probe one operation family.  Writes are never used to discover access."""

        if not read_only:
            payload = {
                "refused": True,
                "refusal_reason": "write_probe_not_implemented",
                "writes": 0,
            }
            click.echo(canonical_json(payload), err=True)
            raise SystemExit(2)
        from .auth import resolve_auth, resolve_tenant_from_env

        obj = ctx.obj or {}
        tenant = obj.get("location_id") or resolve_tenant_from_env().location_id
        auth = resolve_auth(kind="location_pit", location_id=tenant)
        result = probe_family(family=family, tenant=tenant, auth=auth)
        document = result.as_document()
        if obj.get("json"):
            click.echo(canonical_json(document))
        else:
            click.echo(
                f"{document['family']} probe: {document['classification']} "
                f"(beta={document['public_beta_state']}, "
                f"route={document['available_route']})"
            )
        raise SystemExit(0 if not document["refused"] else 1)

    cli_group.add_command(capabilities)


__all__ = [
    "DEFAULT_FALLBACK_POLICY",
    "WORKFLOW_BETA_ERROR_CODE",
    "PROBE_FAMILIES",
    "ProbeResult",
    "credential_fingerprint",
    "probe_family",
    "probe_workflow_family",
    "register",
]
