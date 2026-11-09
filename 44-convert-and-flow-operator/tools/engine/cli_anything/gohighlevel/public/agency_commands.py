"""Agency command module (WF05).  WF03 registers it; this file owns no CLI file.

Registration contract (WF05-CP01, consumed by WF03/GHL-003)::

    from cli_anything.gohighlevel.public.agency_commands import register
    register(cli, verify_approval=_verify_automation_write)

Options ``verify_approval`` (the existing Command Center approval verifier),
``capability_loader(agency_company_id) -> Capability | None`` and
``transport_factory() -> Transport`` are injected so the module never imports
the CLI (no cycle) and every test can run offline.  With no verifier the write
is refused: fail closed, no invented approval.

The private create stays where it is (``locations create --experimental``); this
module registers a NEW ``agency create-location`` verb beside it, and prints the
private route only as the explicitly labelled fallback.  It never runs both.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Mapping

import click

from .agency import (
    APPROVAL_ACTION,
    PRIVATE_FALLBACK_NOTE,
    AgencyAdapter,
    AgencyLocationSpec,
    PlanFact,
    PlanFacts,
    approval_object_key,
    result_summary,
    resolve_agency_auth,
    route_decision,
)
from .auth import CredentialMissing
from .capability import Capability
from .errors import ContractViolation


def _expiry_timestamp(record: Mapping[str, Any]) -> float:
    raw = record.get("expires_at")
    if raw in (None, ""):
        raise ContractViolation("approval_expired", detail={"field": "expires_at"})
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()


def _private_fallback_hint(company_id: str, name: str) -> str:
    return (
        "PRIVATE FALLBACK (labelled, not executed here): "
        "`ghl --experimental locations create --name %r --company-id %r` — %s."
        % (name, company_id, PRIVATE_FALLBACK_NOTE)
    )


def register(
    cli: click.Group,
    *,
    verify_approval: Callable[[str, str, str], Mapping[str, Any]] | None = None,
    capability_loader: Callable[[str], Capability | None] | None = None,
    transport_factory: Callable[[], Any] | None = None,
) -> click.Group:
    """Attach the ``agency`` group to an existing Click root.  Returns the group."""

    def _build_approval(
        approval_id: str | None, plan_sha256: str | None, spec: AgencyLocationSpec
    ) -> Mapping[str, Any]:
        if not approval_id or not plan_sha256:
            raise ContractViolation(
                "approval_required",
                detail={"hint": "--approval-id and --plan-sha256 are both required"},
            )
        if verify_approval is None:
            raise ContractViolation(
                "approval_unavailable",
                detail={"hint": "no approval authority verifier was wired by WF03"},
            )
        verified = verify_approval(approval_id, plan_sha256, APPROVAL_ACTION)
        if not isinstance(verified, Mapping) or verified.get("ok") is not True:
            raise ContractViolation("approval_unverified")
        return {
            "kind": "automation_write",
            "approval_id": approval_id,
            "action": APPROVAL_ACTION,
            "object_key": approval_object_key(spec),
            "plan_sha256": plan_sha256,
            "approver": verified.get("client_identity") or "",
            "expiry": _expiry_timestamp(verified),
        }

    def _reverify(record: Mapping[str, Any]) -> bool:
        if verify_approval is None:
            return False
        try:
            checked = verify_approval(
                str(record.get("approval_id")),
                str(record.get("plan_sha256")),
                APPROVAL_ACTION,
            )
        except Exception:  # noqa: BLE001 - fail closed on an unreachable authority
            return False
        return isinstance(checked, Mapping) and checked.get("ok") is True

    group = click.Group(
        name="agency",
        help="Agency-level operations (Agency Token). Public API preferred.",
    )

    @group.command("create-location")
    @click.option("--name", required=True, help="Sub-account (location) name")
    @click.option(
        "--agency-company-id",
        required=True,
        help="GHL agency companyId (never a relation number or a Command Center UUID)",
    )
    @click.option(
        "--agency-pro/--no-agency-pro",
        default=None,
        help="Owner-supplied Agency Pro fact for THIS agency company. Omit = unknown "
        "(not eligible); it is never inherited from another account.",
    )
    @click.option("--approval-id", default=None, help="Command Center automation_write id")
    @click.option("--plan-sha256", default=None, help="sha256 of the approved plan")
    @click.option(
        "--dry-run", is_flag=True, default=False, help="Compile and validate only"
    )
    @click.pass_context
    def create_location(
        ctx: click.Context,
        name: str,
        agency_company_id: str,
        agency_pro: bool | None,
        approval_id: str | None,
        plan_sha256: str | None,
        dry_run: bool,
    ) -> None:
        as_json = bool((ctx.obj or {}).get("json"))
        try:
            spec = AgencyLocationSpec(name=name, agency_company_id=agency_company_id)
            source = "unknown" if agency_pro is None else "owner_supplied"
            plan_fact = PlanFact(spec.agency_company_id, agency_pro, source)
            plan_facts = PlanFacts({spec.agency_company_id: plan_fact})
            try:
                auth = resolve_agency_auth()
                credential_present = True
            except CredentialMissing:
                auth = None
                credential_present = False
            capability = (
                capability_loader(spec.agency_company_id)
                if capability_loader is not None
                else None
            )
            approval = None
            if approval_id or plan_sha256:
                approval = _build_approval(approval_id, plan_sha256, spec)
            decision = route_decision(
                spec=spec,
                agency_credential_present=credential_present,
                plan_fact=plan_fact,
                approval=approval,
                capability=capability,
            )
            if not decision.public:
                click.echo(
                    "REFUSED before any network call: %s. %s"
                    % (
                        decision.reason,
                        _private_fallback_hint(spec.agency_company_id, spec.name),
                    ),
                    err=True,
                )
                raise SystemExit(1)
            approval = _build_approval(approval_id, plan_sha256, spec)
            adapter = AgencyAdapter(
                auth=auth,
                transport=transport_factory() if transport_factory else None,
                capability=capability,
                plan_facts=plan_facts,
            )
            result = adapter.create_location(
                spec,
                approval=approval,
                approval_verifier=_reverify,
                idempotency_key=_idempotency_key(spec),
                dry_run=bool(dry_run or (ctx.obj or {}).get("dry_run")),
            )
            summary = result_summary(result)
            click.echo(json.dumps(summary, indent=2, default=str))
            if result.status.value != "ok":
                click.echo(
                    _private_fallback_hint(spec.agency_company_id, spec.name), err=True
                )
                raise SystemExit(1)
            if as_json:
                return
        except ContractViolation as refusal:
            click.echo("REFUSED: %s" % refusal, err=True)
            raise SystemExit(2) from refusal

    cli.add_command(group)
    return group


def _idempotency_key(spec: AgencyLocationSpec) -> str:
    """Stable per (agency company, name) run key in the frozen gxo_ format."""

    import hashlib

    digest = hashlib.sha256(
        (spec.agency_company_id + "\n" + spec.name.strip()).encode("utf-8")
    ).hexdigest()
    return "gxo_locations-create-" + digest[:32]
