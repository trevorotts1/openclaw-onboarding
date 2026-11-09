"""Click command group for native Voice AI (WF27).

WF03 owns ``gohighlevel_cli.py``.  This module is the command surface it
registers, with a single line::

    from cli_anything.gohighlevel.public.voice_ai_commands import register
    register(cli)

Every command builds the typed adapter from ``voice_ai`` (default-deny) and
prints the operation envelope.  A refused or failed result exits non-zero, so a
disabled capability, an unverified wire version or a guard refusal can never
look like success.  Tests may inject ``ctx.obj["voice_adapter"]`` to exercise the
same command path against a fake transport.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

import click

from .adapter import ApprovalRef
from .auth import TenantBinding
from .errors import ContractViolation
from .voice_ai import (
    AGENTS_CREATE,
    ACTIONS_CREATE,
    CALL_MODES,
    CallLogQuery,
    CallRecord,
    ControlledTestEvidence,
    ControlledTestPlan,
    GuardLimits,
    PhoneRouteState,
    PROVIDERS,
    RouteRollback,
    Status,
    VoiceActionSpec,
    VoiceAgentSpec,
    VoiceAiAdapter,
    VoiceProviderChoice,
    load_voice_adapter,
    plan_controlled_test,
    plan_route_activation,
    plan_provisioning,
    refuse_billing_action,
    result_summary,
    screen_caller_input,
    select_provider,
    verify_controlled_test,
)

COMMANDS: tuple[str, ...] = (
    "voice providers",
    "voice agents list",
    "voice agents get",
    "voice agents create",
    "voice agents update",
    "voice actions create",
    "voice actions update",
    "voice calls list",
    "voice calls get",
    "voice phone status",
    "voice test plan",
    "voice test verify",
    "voice route handoff",
    "voice guards screen",
    "voice guard billing",
)


def _obj(ctx: click.Context) -> dict[str, Any]:
    return dict(ctx.obj or {})


def _tenant(ctx: click.Context) -> TenantBinding:
    obj = _obj(ctx)
    tenant = obj.get("voice_tenant")
    if isinstance(tenant, TenantBinding):
        return tenant
    location_id = obj.get("location_id") or os.environ.get("GHL_LOCATION_ID", "")
    if not str(location_id).strip():
        raise click.ClickException(
            "location id missing: pass --location-id on the ghl root command "
            "or set GHL_LOCATION_ID"
        )
    return TenantBinding(location_id=str(location_id), source="request")


def _adapter(ctx: click.Context) -> VoiceAiAdapter:
    injected = _obj(ctx).get("voice_adapter")
    if isinstance(injected, VoiceAiAdapter):
        return injected
    adapter, reason = load_voice_adapter(_tenant(ctx).location_id)
    if adapter is None:
        raise click.ClickException(reason)
    return adapter


def _approval() -> ApprovalRef | None:
    if os.environ.get("CAF_APPROVAL_TOKEN", "").strip():
        return ApprovalRef(ref="CAF_APPROVAL_TOKEN", kind="gate_token")
    return None


def _emit(ctx: click.Context, payload: Mapping[str, Any], *, ok: bool = True) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    click.echo(text, err=not ok)
    if not ok:
        raise click.exceptions.Exit(1)


def _emit_result(ctx: click.Context, result: Any, payload: Any = None) -> None:
    document = result_summary(result)
    if payload is not None:
        document["payload"] = payload
    _emit(ctx, document, ok=getattr(result.status, "value", "") == Status.ok.value)


def _load_json(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise click.ClickException("cannot read JSON %s: %s" % (path, type(exc).__name__)) from None
    if not isinstance(data, dict):
        raise click.ClickException("JSON %s must be an object" % path)
    return data


def _agent_spec(data: Mapping[str, Any]) -> VoiceAgentSpec:
    return VoiceAgentSpec(
        name=str(data.get("name") or ""),
        business_name=str(data.get("business_name") or ""),
        language=str(data.get("language") or ""),
        timezone=str(data.get("timezone") or ""),
        operating_hours=dict(data.get("operating_hours") or {}),
        escalation_destination=dict(data.get("escalation_destination") or {}),
        allowed_call_purposes=tuple(str(item) for item in (data.get("allowed_call_purposes") or ())),
        knowledge_source_ids=tuple(str(item) for item in (data.get("knowledge_source_ids") or ())),
        voice=dict(data["voice"]) if isinstance(data.get("voice"), dict) else None,
        extra=dict(data.get("extra") or {}),
    )


def _action_spec(data: Mapping[str, Any]) -> VoiceActionSpec:
    return VoiceActionSpec(
        agent_id=str(data.get("agent_id") or ""),
        action_type=str(data.get("action_type") or ""),
        parameters=dict(data.get("parameters") or {}),
        extra=dict(data.get("extra") or {}),
    )


def _limits(data: Mapping[str, Any] | None) -> GuardLimits:
    source = dict(data or {})
    return GuardLimits(
        max_test_calls=int(source.get("max_test_calls", 2)),
        max_test_duration_s=int(source.get("max_test_duration_s", 180)),
        max_cost_usd=float(source.get("max_cost_usd", 5.0)),
        max_retries=int(source.get("max_retries", 0)),
        max_actions_per_test=int(source.get("max_actions_per_test", 3)),
        allowed_destinations=tuple(str(x) for x in (source.get("allowed_destinations") or ())),
        allowed_calendars=tuple(str(x) for x in (source.get("allowed_calendars") or ())),
    )


def _plan_from_json(data: Mapping[str, Any]) -> ControlledTestPlan:
    return ControlledTestPlan(
        plan_id=str(data.get("plan_id") or ""),
        location_id=str(data.get("location_id") or ""),
        agent_id=str(data.get("agent_id") or ""),
        destination_ref=str(data.get("destination_ref") or ""),
        expected_outcome=str(data.get("expected_outcome") or ""),
        estimated_duration_s=int(data.get("estimated_duration_s") or 0),
        estimated_cost_usd=float(data.get("estimated_cost_usd") or 0),
        action_count=int(data.get("action_count") or 0),
        test_call_index=int(data.get("test_call_index") or 1),
        retries=int(data.get("retries") or 0),
        limits=_limits(
            {
                "max_test_calls": data.get("max_test_calls", 2),
                "max_test_duration_s": data.get("max_duration_s", 180),
                "max_cost_usd": data.get("max_cost_usd", 5.0),
                "max_retries": data.get("max_retries", 0),
                "max_actions_per_test": data.get("max_actions_per_test", 3),
            }
        ),
    )


def _evidence_from_json(location_id: str, data: Mapping[str, Any]) -> ControlledTestEvidence:
    call = data.get("call") or {}
    record = CallRecord(
        call_id=str(call.get("call_id") or ""),
        location_id=str(call.get("location_id") or location_id),
        agent_id=call.get("agent_id"),
        contact_id=call.get("contact_id"),
        direction=call.get("direction"),
        mode=str(call.get("mode") or "unknown"),
        started_at=call.get("started_at"),
        duration_s=call.get("duration_s"),
        outcome=call.get("outcome"),
        action_refs=tuple(str(item) for item in (call.get("action_refs") or ())),
        transcript_ref=call.get("transcript_ref"),
    )
    return ControlledTestEvidence(
        plan_id=str(data.get("plan_id") or ""),
        call=record,
        business_outcome=str(data.get("business_outcome") or ""),
        outcome_ref=str(data.get("outcome_ref") or ""),
    )


def _rollback_from_json(data: Mapping[str, Any]) -> RouteRollback:
    return RouteRollback(
        location_id=str(data.get("location_id") or ""),
        agent_id=str(data.get("agent_id") or ""),
        number_ref=str(data.get("number_ref") or ""),
        previous_route_ref=str(data.get("previous_route_ref") or ""),
        captured_at=str(data.get("captured_at") or ""),
    )


class VoiceGroup(click.Group):
    """Turn a typed refusal into a clean non-zero CLI error, never a success."""

    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except ContractViolation as exc:
            raise click.ClickException(str(exc)) from None


@click.group("voice", cls=VoiceGroup)
@click.pass_context
def voice(ctx: click.Context) -> None:
    """Native Voice AI agents, actions, call logs and controlled tests."""


@voice.command("providers")
@click.pass_context
def voice_providers(ctx: click.Context) -> None:
    """List the two distinct providers (no implicit default, no cost claim)."""

    _emit(
        ctx,
        {
            "providers": list(PROVIDERS),
            "default": None,
            "cost_claim": None,
            "note": (
                "provider is an explicit operator choice; native HighLevel "
                "Voice AI and the Skill 38 self-hosted pipeline are separate"
            ),
        },
    )


@voice.group("agents")
def agents_group() -> None:
    """Create, read and update native voice agents."""


@agents_group.command("list")
@click.option("--page", default=1, type=int, show_default=True)
@click.option("--page-size", default=50, type=int, show_default=True)
@click.pass_context
def agents_list(ctx: click.Context, page: int, page_size: int) -> None:
    result, payload = _adapter(ctx).list_agents(
        tenant=_tenant(ctx), page=page, page_size=page_size
    )
    _emit_result(ctx, result, payload)


@agents_group.command("get")
@click.option("--agent-id", required=True)
@click.pass_context
def agents_get(ctx: click.Context, agent_id: str) -> None:
    result, payload = _adapter(ctx).get_agent(tenant=_tenant(ctx), agent_id=agent_id)
    _emit_result(ctx, result, payload)


@agents_group.command("create")
@click.option("--spec", "spec_path", required=True, help="JSON agent spec file")
@click.option("--idempotency-key", required=True)
@click.pass_context
def agents_create(ctx: click.Context, spec_path: str, idempotency_key: str) -> None:
    result, payload = _adapter(ctx).create_agent(
        tenant=_tenant(ctx),
        spec=_agent_spec(_load_json(spec_path)),
        idempotency_key=idempotency_key,
        approval=_approval(),
    )
    _emit_result(ctx, result, payload)


@agents_group.command("update")
@click.option("--agent-id", required=True)
@click.option("--patch", "patch_path", required=True, help="JSON patch file")
@click.option("--idempotency-key", required=True)
@click.pass_context
def agents_update(ctx: click.Context, agent_id: str, patch_path: str, idempotency_key: str) -> None:
    result, payload = _adapter(ctx).update_agent(
        tenant=_tenant(ctx),
        agent_id=agent_id,
        patch=_load_json(patch_path),
        idempotency_key=idempotency_key,
        approval=_approval(),
    )
    _emit_result(ctx, result, payload)


@voice.group("actions")
def actions_group() -> None:
    """Create and update native voice agent actions."""


@actions_group.command("create")
@click.option("--spec", "spec_path", required=True, help="JSON action spec file")
@click.option("--idempotency-key", required=True)
@click.option("--action-readback-id", default=None)
@click.pass_context
def actions_create(
    ctx: click.Context, spec_path: str, idempotency_key: str, action_readback_id: str | None
) -> None:
    result, payload = _adapter(ctx).create_action(
        tenant=_tenant(ctx),
        spec=_action_spec(_load_json(spec_path)),
        idempotency_key=idempotency_key,
        approval=_approval(),
        action_readback_id=action_readback_id,
    )
    _emit_result(ctx, result, payload)


@actions_group.command("update")
@click.option("--action-id", required=True)
@click.option("--patch", "patch_path", required=True, help="JSON patch file")
@click.option("--idempotency-key", required=True)
@click.pass_context
def actions_update(ctx: click.Context, action_id: str, patch_path: str, idempotency_key: str) -> None:
    result, payload = _adapter(ctx).update_action(
        tenant=_tenant(ctx),
        action_id=action_id,
        patch=_load_json(patch_path),
        idempotency_key=idempotency_key,
        approval=_approval(),
    )
    _emit_result(ctx, result, payload)


@voice.group("calls")
def calls_group() -> None:
    """Read Voice AI call logs (bounded window, IANA timezone, 1-based pages)."""


@calls_group.command("list")
@click.option("--timezone", required=True)
@click.option("--start", required=True, help="ISO-8601 timestamp (timezone-aware)")
@click.option("--end", required=True, help="ISO-8601 timestamp (timezone-aware)")
@click.option("--agent-id", default=None)
@click.option("--contact-id", default=None)
@click.option("--call-type", default=None, type=click.Choice(["inbound", "outbound"]))
@click.option("--action-types", default=None, help="Comma-separated action types")
@click.option("--page", default=1, type=int, show_default=True)
@click.option("--page-size", default=50, type=int, show_default=True)
@click.pass_context
def calls_list(
    ctx: click.Context, timezone: str, start: str, end: str, agent_id: str | None,
    contact_id: str | None, call_type: str | None, action_types: str | None,
    page: int, page_size: int,
) -> None:
    query = CallLogQuery(
        timezone=timezone,
        start=start,
        end=end,
        page=page,
        page_size=page_size,
        agent_id=agent_id,
        contact_id=contact_id,
        call_type=call_type,
        action_types=tuple(
            item.strip() for item in (action_types or "").split(",") if item.strip()
        ),
    )
    result, calls = _adapter(ctx).list_call_logs(tenant=_tenant(ctx), query=query)
    _emit_result(ctx, result, {"calls": [call.as_evidence() for call in calls]})


@calls_group.command("get")
@click.option("--call-id", required=True)
@click.pass_context
def calls_get(ctx: click.Context, call_id: str) -> None:
    result, record = _adapter(ctx).get_call(tenant=_tenant(ctx), call_id=call_id)
    _emit_result(ctx, result, None if record is None else record.as_evidence())


@voice.group("phone")
def phone_group() -> None:
    """Inspect phone routing separately from agents."""


@phone_group.command("status")
@click.pass_context
def phone_status(ctx: click.Context) -> None:
    state = _adapter(ctx).inspect_phone_assignment(tenant=_tenant(ctx))
    _emit(
        ctx,
        {
            "phone": state.as_evidence(),
            "agent_is_not_a_routed_phone": True,
            "operationally_active": state.operationally_active,
        },
    )


@voice.group("test")
def test_group() -> None:
    """Controlled-test planning and evidence verification (no dialing)."""


@test_group.command("plan")
@click.option("--request", "request_path", required=True, help="JSON test request file")
@click.pass_context
def test_plan(ctx: click.Context, request_path: str) -> None:
    data = _load_json(request_path)
    adapter = _adapter(ctx)
    tenant = _tenant(ctx)
    plan = plan_controlled_test(
        tenant=tenant,
        agent_id=str(data.get("agent_id") or ""),
        destination_ref=str(data.get("destination_ref") or ""),
        expected_outcome=str(data.get("expected_outcome") or ""),
        estimated_duration_s=int(data.get("estimated_duration_s") or 0),
        estimated_cost_usd=float(data.get("estimated_cost_usd") or 0),
        action_count=int(data.get("action_count") or 0),
        phone=adapter.inspect_phone_assignment(tenant=tenant),
        limits=_limits(data.get("limits")),
        test_call_index=int(data.get("test_call_index") or 1),
        retries=int(data.get("retries") or 0),
    )
    _emit(ctx, plan.as_evidence())


@test_group.command("verify")
@click.option("--plan", "plan_path", required=True)
@click.option("--evidence", "evidence_path", required=True)
@click.pass_context
def test_verify(ctx: click.Context, plan_path: str, evidence_path: str) -> None:
    plan = _plan_from_json(_load_json(plan_path))
    evidence = _evidence_from_json(_tenant(ctx).location_id, _load_json(evidence_path))
    receipt = verify_controlled_test(plan, evidence)
    _emit(ctx, receipt.as_evidence())


@voice.group("route")
def route_group() -> None:
    """Phone route handoff with a mandatory rollback reference."""


@route_group.command("handoff")
@click.option("--plan", "plan_path", required=True)
@click.option("--rollback", "rollback_path", required=True)
@click.pass_context
def route_handoff(ctx: click.Context, plan_path: str, rollback_path: str) -> None:
    plan = _plan_from_json(_load_json(plan_path))
    rollback = _rollback_from_json(_load_json(rollback_path))
    handoff = plan_route_activation(plan=plan, rollback=rollback)
    _emit(ctx, handoff.as_evidence())


@voice.group("guards")
def guards_group() -> None:
    """Dry guards that never call the provider."""


@guards_group.command("screen")
@click.option("--text", required=True, help="Caller utterance to classify")
@click.pass_context
def guards_screen(ctx: click.Context, text: str) -> None:
    _emit(ctx, screen_caller_input(text).as_evidence())


@voice.command("guard-billing")
@click.option("--action", required=True)
@click.pass_context
def guard_billing(ctx: click.Context, action: str) -> None:
    refuse_billing_action(action)
    _emit(ctx, {"action": action, "forbidden": BILLING_FORBIDDEN_NOTE})


BILLING_FORBIDDEN_NOTE = "number purchase and plan changes are never available here"


def register(cli: click.Group) -> click.Group:
    """Attach the ``voice`` group.  This is the whole WF03 registration patch."""

    cli.add_command(voice)
    return cli


__all__ = ["voice", "register", "COMMANDS"]
