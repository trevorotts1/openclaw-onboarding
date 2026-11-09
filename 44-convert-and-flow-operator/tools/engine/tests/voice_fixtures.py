"""Focused offline fixtures for the WF27 native Voice AI lane.

Every fixture is synthetic and offline: ``FakeTransport`` replays scripted
responses and no token, location id, phone number, contact or transcript from a
real account appears here.  The wire-version literal below exists ONLY so the
happy-path tests can pass the pending-version guard; the shipped rows keep
``version=None`` because the evidence records no verified literal.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from typing import Any, Mapping, Sequence

_ENGINE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

from cli_anything.gohighlevel.public.adapter import PublicGhlAdapter
from cli_anything.gohighlevel.public.voice_ai import (
    GuardLimits,
    PhoneRouteState,
    VOICE_OPERATION_ROWS,
    VoiceAgentSpec,
    VoiceAiAdapter,
)
from tests._public_contract_fakes import (  # noqa: E402
    SYNTHETIC_CONTACT,
    SYNTHETIC_TENANT,
    FakeTransport,
    approval,
    enabled_gate,
    fake_auth,
    fake_tenant,
    issue_key,
    resp,
)
from cli_anything.gohighlevel.public.transport import TransportResponse  # noqa: E402

#: Synthetic only.  The frozen evidence records NO verified Version literal.
TEST_VERSION_LITERAL = "2021-04-15"


def verified_rows(version: str | None = TEST_VERSION_LITERAL) -> dict[str, Any]:
    """The requested voice rows with a test-only version (or the pending state)."""

    return {
        item.operation_id: replace(
            item,
            version=version,
            blocker=None if version is not None else item.blocker,
        )
        for item in VOICE_OPERATION_ROWS
    }


def voice_gate(*, tenant: str = SYNTHETIC_TENANT):
    return enabled_gate(list(verified_rows().values()), tenant=tenant)


def make_voice_adapter(
    responses: Sequence[TransportResponse] | None = None,
    *,
    version: str | None = TEST_VERSION_LITERAL,
    gate: Any = "enabled",
    guards: GuardLimits | None = None,
    tenant: str = SYNTHETIC_TENANT,
) -> tuple[VoiceAiAdapter, FakeTransport]:
    transport = FakeTransport(list(responses or []))
    operations: Mapping[str, Any] = (
        verified_rows(version) if version is not None else {r.operation_id: r for r in VOICE_OPERATION_ROWS}
    )
    capability = voice_gate(tenant=tenant) if gate == "enabled" else None
    public = PublicGhlAdapter(
        auth=fake_auth(location_id=tenant),
        operations=operations,  # type: ignore[arg-type]
        transport=transport,
        capability=capability,
    )
    return VoiceAiAdapter(public=public, operations=operations, guards=guards), transport


def agent_spec(**overrides: Any) -> VoiceAgentSpec:
    values: dict[str, Any] = {
        "name": "Front Desk",
        "business_name": "Synthetic Co",
        "language": "en-US",
        "timezone": "America/New_York",
        "operating_hours": {"mon": "09:00-17:00"},
        "escalation_destination": {"type": "transfer", "target_ref": "dest_operator"},
        "allowed_call_purposes": ("inbound_support", "booking"),
    }
    values.update(overrides)
    return VoiceAgentSpec(**values)


def agent_payload(agent_id: str = "agent_synthetic_1", name: str = "Front Desk") -> dict[str, Any]:
    return {"id": agent_id, "name": name, "locationId": SYNTHETIC_TENANT}


def agent_list_payload(agent_id: str = "agent_synthetic_1", name: str = "Front Desk") -> dict[str, Any]:
    return {"agents": [agent_payload(agent_id, name)]}


def call_payload(
    *,
    call_id: str = "call_synthetic_1",
    agent_id: str = "agent_synthetic_1",
    mode: str = "trial",
    action_refs: Sequence[str] = ("action_synthetic_1",),
) -> dict[str, Any]:
    return {
        "callId": call_id,
        "locationId": SYNTHETIC_TENANT,
        "agentId": agent_id,
        "contactId": SYNTHETIC_CONTACT,
        "direction": "inbound",
        "mode": mode,
        "startedAt": "2026-11-08T15:00:00-05:00",
        "durationSeconds": 42,
        "outcome": "booked",
        "actionRefs": list(action_refs),
    }


def bound_phone(agent_id: str = "agent_synthetic_1", *, verified: bool = False) -> PhoneRouteState:
    return PhoneRouteState(
        location_id=SYNTHETIC_TENANT,
        number_ref="number_ref_synthetic_1",
        agent_id=agent_id,
        inbound_route_ref="route_ref_synthetic_1",
        routing_verified=verified,
        observed=True,
        source="synthetic_fixture",
    )


def bounded_limits(**overrides: Any) -> GuardLimits:
    values: dict[str, Any] = {
        "max_test_calls": 2,
        "max_test_duration_s": 180,
        "max_cost_usd": 5.0,
        "max_retries": 0,
        "max_actions_per_test": 3,
        "allowed_destinations": ("dest_operator",),
        "allowed_calendars": ("cal_synthetic_1",),
    }
    values.update(overrides)
    return GuardLimits(**values)


__all__ = [
    "TEST_VERSION_LITERAL",
    "verified_rows",
    "voice_gate",
    "make_voice_adapter",
    "agent_spec",
    "agent_payload",
    "agent_list_payload",
    "call_payload",
    "bound_phone",
    "bounded_limits",
    "approval",
    "fake_tenant",
    "issue_key",
    "resp",
    "SYNTHETIC_TENANT",
    "SYNTHETIC_CONTACT",
]
