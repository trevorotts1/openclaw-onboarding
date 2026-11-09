"""Native HighLevel Voice AI adapter (WF27, revision 3.0 section 24).

Two providers are kept distinct and neither is claimed to be cheaper:

* ``ghl_native_voice`` -- HighLevel's own Voice AI agents/actions/call logs,
  reached only through the frozen public adapter (``PublicGhlAdapter.call``),
  which means the tenant capability gate is default-deny and every write needs
  an approval seam, an idempotency key and a read-back with a real expectation.
* ``self_hosted_skill38`` -- the existing Skill 38 STT -> brain -> TTS pipeline
  already documented in ``38-conversational-ai-system/protocols/
  voice-phone-protocol.md``.  This module never touches it; selecting it returns
  a handoff record and nothing else.

Frozen interface (checkpoint WF27-CP01): ``VoiceAgentSpec``, ``VoiceActionSpec``,
``PhoneRouteState``, ``CallLogQuery``, ``CallRecord``, ``GuardLimits``,
``ControlledTestPlan``, ``ControlledTestEvidence``, ``RouteRollback`` and the
operation-id table below.  Consume it from the checkpoint record rather than
re-deriving a second shape.

Operation rows and wire version: the exact HTTP contracts are the ones already
enumerated in ``29-ghl-convert-and-flow/references/voice-ai.md`` (verified
2026-08-03).  That reference deliberately records NO verified ``Version``
literal for any voice-ai operation, so every row here carries ``version=None``
and the blocker ``B-VERSION-UNVERIFIED``; a call refuses loudly with
``VoiceContractPending`` before transport until WF00 freezes the literal.  No
version is guessed and no request is sent with an invented one.

The agent is not a routed phone.  ``create_agent`` proves configuration only;
``inspect_phone_assignment`` reports the separate routing state honestly and
``plan_route_activation`` returns a handoff request, never an executed routing
change.  Nothing here buys a number, changes a plan, retries a write, dials a
destination, or lets caller speech mutate administrative state.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .adapter import ApprovalRef, PublicGhlAdapter
from .auth import AuthKind, TenantBinding, resolve_auth
from .errors import ContractViolation
from .operations import OPERATIONS
from .readback import ReadbackSpec
from .result import Status, canonical_json
from .transport import Transport

# ---------------------------------------------------------------------------
# operation ids, rows and the pending-version contract
# ---------------------------------------------------------------------------

VOICE_AI_DOCS = "https://marketplace.gohighlevel.com/docs/ghl/voice-ai/"
VOICE_AI_DOC_FETCH_DATE = "2026-08-03"
WIRE_VERSION_UNVERIFIED = "B-VERSION-UNVERIFIED"
WIRE_VERSION_UNBLOCK = (
    "freeze the per-operation Version literal for each voice-ai operation page "
    "(or an authorized describe_operation capture) in public/operations.py"
)

AGENTS_LIST = "voiceAi.agents.list"
AGENTS_GET = "voiceAi.agents.get"
AGENTS_CREATE = "voiceAi.agents.create"
AGENTS_UPDATE = "voiceAi.agents.update"
ACTIONS_GET = "voiceAi.actions.get"
ACTIONS_CREATE = "voiceAi.actions.create"
ACTIONS_UPDATE = "voiceAi.actions.update"
CALLS_LIST = "voiceAi.calls.list"
CALLS_GET = "voiceAi.calls.get"

VOICE_OPERATION_IDS: tuple[str, ...] = (
    AGENTS_LIST,
    AGENTS_GET,
    AGENTS_CREATE,
    AGENTS_UPDATE,
    ACTIONS_GET,
    ACTIONS_CREATE,
    ACTIONS_UPDATE,
    CALLS_LIST,
    CALLS_GET,
)

SCOPE_AGENTS_WRITE = "voice-ai-agents.write"
SCOPE_AGENTS_READ = "voice-ai-agents.readonly"
SCOPE_GOALS_WRITE = "voice-ai-agent-goals.write"
SCOPE_GOALS_READ = "voice-ai-agent-goals.readonly"
SCOPE_DASHBOARD_READ = "voice-ai-dashboard.readonly"

_AUTH = (AuthKind.location_pit, AuthKind.oauth)


@dataclass(frozen=True)
class VoiceOperationRow:
    """One requested operation row, shaped exactly like ``operations.OperationRow``.

    It is deliberately NOT installed into ``public/operations.py`` (WF00 owns
    that file).  ``voice_operations()`` merges these rows only where the shared
    registry has no row yet, so the shared registry always wins once WF00 lands.
    """

    operation_id: str
    method: str
    path_template: str
    tenant_binding: str
    write: bool
    scopes_candidate: tuple[str, ...]
    readback_plan: str | None = None
    approval_required: bool = False
    version: str | None = None
    version_alternates: tuple[str, ...] = ()
    documented_level: str = "D"
    route_class: str = "public_direct"
    auth_kinds: tuple[AuthKind, ...] = _AUTH
    doc_url: str | None = VOICE_AI_DOCS
    doc_fetch_date: str | None = VOICE_AI_DOC_FETCH_DATE
    blocker: str | None = WIRE_VERSION_UNVERIFIED
    required_query: tuple[str, ...] = ()
    query_enums: tuple[tuple[str, tuple[str, ...]], ...] = ()


VOICE_OPERATION_ROWS: tuple[VoiceOperationRow, ...] = (
    VoiceOperationRow(
        AGENTS_LIST, "GET", "/voice-ai/agents", "query.locationId", False,
        (SCOPE_AGENTS_READ,),
    ),
    VoiceOperationRow(
        AGENTS_GET, "GET", "/voice-ai/agents/{agentId}", "query.locationId", False,
        (SCOPE_AGENTS_READ,),
    ),
    VoiceOperationRow(
        AGENTS_CREATE, "POST", "/voice-ai/agents", "body.locationId", True,
        (SCOPE_AGENTS_WRITE,), readback_plan=AGENTS_LIST, approval_required=True,
    ),
    VoiceOperationRow(
        AGENTS_UPDATE, "PATCH", "/voice-ai/agents/{agentId}", "query.locationId", True,
        (SCOPE_AGENTS_WRITE,), readback_plan=AGENTS_GET, approval_required=True,
    ),
    VoiceOperationRow(
        ACTIONS_GET, "GET", "/voice-ai/actions/{actionId}", "query.locationId", False,
        (SCOPE_GOALS_READ,),
    ),
    VoiceOperationRow(
        ACTIONS_CREATE, "POST", "/voice-ai/actions", "body.locationId", True,
        (SCOPE_GOALS_WRITE,), readback_plan=ACTIONS_GET, approval_required=True,
    ),
    VoiceOperationRow(
        ACTIONS_UPDATE, "PUT", "/voice-ai/actions/{actionId}", "body.locationId", True,
        (SCOPE_GOALS_WRITE,), readback_plan=ACTIONS_GET, approval_required=True,
    ),
    VoiceOperationRow(
        CALLS_LIST, "GET", "/voice-ai/dashboard/call-logs", "query.locationId", False,
        (SCOPE_DASHBOARD_READ,),
    ),
    VoiceOperationRow(
        CALLS_GET, "GET", "/voice-ai/dashboard/call-logs/{callId}", "query.locationId",
        False, (SCOPE_DASHBOARD_READ,),
    ),
)


def voice_operations(shared: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Shared rows plus only the voice rows the shared registry does not have."""

    source = OPERATIONS if shared is None else shared
    merged: dict[str, Any] = {operation_id: source[operation_id] for operation_id in source}
    for row in VOICE_OPERATION_ROWS:
        merged.setdefault(row.operation_id, row)
    return merged


# ---------------------------------------------------------------------------
# named refusals
# ---------------------------------------------------------------------------


class VoiceContractPending(ContractViolation):
    """The frozen row is not installable yet; refuse before transport."""

    rule = "voice_contract_pending"


class VoiceGuardRefusal(ContractViolation):
    """A controlled-test / activation / caller-input guard refused the action."""

    rule = "voice_guard_refusal"


# ---------------------------------------------------------------------------
# provider choice
# ---------------------------------------------------------------------------

PROVIDER_NATIVE = "ghl_native_voice"
PROVIDER_SELF_HOSTED = "self_hosted_skill38"
PROVIDERS: tuple[str, ...] = (PROVIDER_NATIVE, PROVIDER_SELF_HOSTED)


@dataclass(frozen=True)
class VoiceProviderChoice:
    provider: str
    reason: str
    #: Usage/price evidence for a cost comparison.  ``None`` means nobody has
    #: produced client-specific evidence, so this module makes no cost claim.
    price_evidence_ref: str | None = None

    def __post_init__(self) -> None:
        if self.provider not in PROVIDERS:
            raise ContractViolation(
                "voice_provider_unknown", detail={"provider": str(self.provider)}
            )
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ContractViolation("voice_provider_reason_missing")

    @property
    def native(self) -> bool:
        return self.provider == PROVIDER_NATIVE

    def as_evidence(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "reason": self.reason,
            "native": self.native,
            "cost_claim": (
                None if self.price_evidence_ref is None else "evidence_supplied"
            ),
            "price_evidence_ref": self.price_evidence_ref,
        }


def select_provider(provider: str, *, reason: str, price_evidence_ref: str | None = None) -> VoiceProviderChoice:
    """Explicit provider selection.  There is no implicit default."""

    text = str(provider or "").strip()
    if not text:
        raise ContractViolation("voice_provider_required")
    return VoiceProviderChoice(
        provider=text, reason=str(reason or ""), price_evidence_ref=price_evidence_ref
    )


# ---------------------------------------------------------------------------
# agent and action contracts
# ---------------------------------------------------------------------------

ALLOWED_CALL_PURPOSES: tuple[str, ...] = (
    "inbound_support",
    "booking",
    "qualification",
    "message_taking",
    "status_updates",
)

ALLOWED_ACTION_TYPES: tuple[str, ...] = (
    "booking",
    "transfer",
    "data_extraction",
    "workflow_activation",
    "knowledge_lookup",
    "custom",
)

_AGENT_RESERVED = frozenset(
    {
        "locationId",
        "name",
        "businessName",
        "language",
        "timezone",
        "operatingHours",
        "escalationDestination",
        "allowedCallPurposes",
        "knowledgeSourceIds",
        "voice",
    }
)
_ACTION_RESERVED = frozenset({"agentId", "locationId", "actionType", "parameters"})
_CUSTOM_FORBIDDEN_KEYS = frozenset(
    {"url", "endpoint", "webhook", "callback_url", "callbackUrl", "target_url"}
)


def _require_text(value: Any, rule: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractViolation(rule)
    return value.strip()


@dataclass(frozen=True)
class VoiceAgentSpec:
    """One native agent configuration.  Unknown valid fields are preserved."""

    name: str
    business_name: str
    language: str
    timezone: str
    operating_hours: Mapping[str, Any]
    escalation_destination: Mapping[str, Any]
    allowed_call_purposes: tuple[str, ...]
    knowledge_source_ids: tuple[str, ...] = ()
    voice: Mapping[str, Any] | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.name, "voice_agent_name_missing")
        _require_text(self.business_name, "voice_agent_business_missing")
        _require_text(self.language, "voice_agent_language_missing")
        try:
            ZoneInfo(_require_text(self.timezone, "voice_agent_timezone_missing"))
        except ZoneInfoNotFoundError:
            raise ContractViolation(
                "voice_agent_timezone_invalid", detail={"timezone": self.timezone}
            ) from None
        if not isinstance(self.operating_hours, Mapping) or not self.operating_hours:
            raise ContractViolation("voice_agent_hours_missing")
        if not isinstance(self.escalation_destination, Mapping):
            raise ContractViolation("voice_agent_escalation_missing")
        if not str(self.escalation_destination.get("type") or "").strip():
            raise ContractViolation("voice_agent_escalation_type_missing")
        if not str(self.escalation_destination.get("target_ref") or "").strip():
            raise ContractViolation("voice_agent_escalation_target_missing")
        for purpose in self.allowed_call_purposes:
            if purpose not in ALLOWED_CALL_PURPOSES:
                raise ContractViolation(
                    "voice_agent_purpose_unsupported", detail={"purpose": str(purpose)}
                )
        if not isinstance(self.knowledge_source_ids, tuple):
            raise ContractViolation("voice_agent_knowledge_ids_invalid")
        reserved = sorted(set(self.extra) & _AGENT_RESERVED)
        if reserved:
            raise ContractViolation(
                "voice_agent_reserved_field", detail={"fields": reserved}
            )

    def to_body(self, location_id: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "locationId": location_id,
            "name": self.name,
            "businessName": self.business_name,
            "language": self.language,
            "timezone": self.timezone,
            "operatingHours": dict(self.operating_hours),
            "escalationDestination": dict(self.escalation_destination),
            "allowedCallPurposes": list(self.allowed_call_purposes),
        }
        if self.knowledge_source_ids:
            body["knowledgeSourceIds"] = list(self.knowledge_source_ids)
        if self.voice is not None:
            body["voice"] = dict(self.voice)
        body.update(dict(self.extra))
        return body


@dataclass(frozen=True)
class VoiceActionSpec:
    """One supported action with an exact type and a bounded parameter mapping."""

    agent_id: str
    action_type: str
    parameters: Mapping[str, Any]
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.agent_id, "voice_action_agent_missing")
        if self.action_type not in ALLOWED_ACTION_TYPES:
            raise ContractViolation(
                "voice_action_type_unsupported", detail={"type": str(self.action_type)}
            )
        if not isinstance(self.parameters, Mapping):
            raise ContractViolation("voice_action_parameters_invalid")
        if self.action_type == "custom":
            forbidden = sorted(set(self.parameters) & _CUSTOM_FORBIDDEN_KEYS)
            if forbidden:
                raise ContractViolation(
                    "voice_action_unbounded_custom", detail={"fields": forbidden}
                )
            if self.parameters.get("restricted") is not True:
                raise ContractViolation("voice_action_custom_not_restricted")
        reserved = sorted(set(self.extra) & _ACTION_RESERVED)
        if reserved:
            raise ContractViolation(
                "voice_action_reserved_field", detail={"fields": reserved}
            )

    def to_body(self, location_id: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "locationId": location_id,
            "agentId": self.agent_id,
            "actionType": self.action_type,
            "parameters": dict(self.parameters),
        }
        body.update(dict(self.extra))
        return body


# ---------------------------------------------------------------------------
# phone routing state and rollback
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhoneRouteState:
    """The separately-observed phone routing state.

    ``configured`` is "an agent is bound".  ``operationally_active`` is the
    stronger claim: the binding was observed AND the inbound route was verified.
    An unobserved state can never yield either success claim.
    """

    location_id: str
    number_ref: str | None = None
    agent_id: str | None = None
    inbound_route_ref: str | None = None
    routing_verified: bool = False
    observed: bool = False
    source: str = "not_read"
    pending_action: str | None = None

    @property
    def configured(self) -> bool:
        return self.observed and bool(self.agent_id)

    @property
    def operationally_active(self) -> bool:
        return self.configured and self.routing_verified

    @property
    def state(self) -> str:
        if not self.observed:
            return "unknown"
        if self.operationally_active:
            return "active"
        return "configured_not_active" if self.configured else "unassigned"

    def as_evidence(self) -> dict[str, Any]:
        return {
            "location_id": self.location_id,
            "state": self.state,
            "configured": self.configured,
            "operationally_active": self.operationally_active,
            "number_ref_present": bool(self.number_ref),
            "inbound_route_present": bool(self.inbound_route_ref),
            "routing_verified": bool(self.routing_verified),
            "observed": bool(self.observed),
            "source": self.source,
            "pending_action": self.pending_action,
        }

    @classmethod
    def unknown(cls, location_id: str) -> "PhoneRouteState":
        return cls(
            location_id=location_id,
            observed=False,
            source="not_read",
            pending_action=(
                "read the number's inbound voice route in the phone/routing "
                "owner's surface (never assumed from the agent id); record the "
                "before-route reference for rollback"
            ),
        )


@dataclass(frozen=True)
class RouteRollback:
    """The captured prior route that every activation must carry."""

    location_id: str
    agent_id: str
    number_ref: str
    previous_route_ref: str
    captured_at: str

    def __post_init__(self) -> None:
        for value, rule in (
            (self.location_id, "voice_rollback_location_missing"),
            (self.agent_id, "voice_rollback_agent_missing"),
            (self.number_ref, "voice_rollback_number_missing"),
            (self.previous_route_ref, "voice_rollback_reference_missing"),
            (self.captured_at, "voice_rollback_capture_time_missing"),
        ):
            _require_text(value, rule)


@dataclass(frozen=True)
class PhoneRouteHandoff:
    """A request for the routing owner, not an executed route change."""

    location_id: str
    agent_id: str
    number_ref: str
    rollback_ref: str
    requested_action: str
    executed: bool
    owner: str
    detail: str

    def as_evidence(self) -> dict[str, Any]:
        return {
            "location_id": self.location_id,
            "agent_id": self.agent_id,
            "number_ref_present": bool(self.number_ref),
            "rollback_ref": self.rollback_ref,
            "requested_action": self.requested_action,
            "executed": self.executed,
            "owner": self.owner,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# call logs -- Voice-specific timezone and 1-based pagination
# ---------------------------------------------------------------------------

CALL_MODES: tuple[str, ...] = ("trial", "live", "unknown")
MAX_CALL_WINDOW = timedelta(days=31)
MAX_PAGE_SIZE = 100


def _parse_iso(value: str, rule: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ContractViolation(rule, detail={"value": str(value)}) from None
    if parsed.tzinfo is None:
        raise ContractViolation(rule, detail={"value": str(value)})
    return parsed


@dataclass(frozen=True)
class CallLogQuery:
    """One bounded call-log query.

    ``timezone`` is mandatory and each boundary is interpreted in it.  The
    window is bounded and pagination is 1-based with a bounded page size --
    the Voice AI dashboard rules, not the workflow-log cursor rules.
    """

    timezone: str
    start: str
    end: str
    page: int = 1
    page_size: int = 50
    agent_id: str | None = None
    contact_id: str | None = None
    call_type: str | None = None
    action_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            ZoneInfo(_require_text(self.timezone, "voice_call_timezone_missing"))
        except ZoneInfoNotFoundError:
            raise ContractViolation(
                "voice_call_timezone_invalid", detail={"timezone": self.timezone}
            ) from None
        start = _parse_iso(self.start, "voice_call_start_invalid")
        end = _parse_iso(self.end, "voice_call_end_invalid")
        if end <= start:
            raise ContractViolation(
                "voice_call_window_invalid", detail={"reason": "end_not_after_start"}
            )
        if end - start > MAX_CALL_WINDOW:
            raise ContractViolation(
                "voice_call_window_unbounded",
                detail={"max_days": MAX_CALL_WINDOW.days},
            )
        if not isinstance(self.page, int) or self.page < 1:
            raise ContractViolation("voice_call_page_invalid")
        if not isinstance(self.page_size, int) or not (1 <= self.page_size <= MAX_PAGE_SIZE):
            raise ContractViolation(
                "voice_call_page_size_invalid", detail={"max": MAX_PAGE_SIZE}
            )
        if self.call_type is not None and self.call_type not in ("inbound", "outbound"):
            raise ContractViolation("voice_call_type_invalid")

    def to_query(self) -> dict[str, Any]:
        query: dict[str, Any] = {
            "timezone": self.timezone,
            "startDate": self.start,
            "endDate": self.end,
            "page": self.page,
            "pageSize": self.page_size,
        }
        if self.agent_id:
            query["agentId"] = self.agent_id
        if self.contact_id:
            query["contactId"] = self.contact_id
        if self.call_type:
            query["callType"] = self.call_type
        if self.action_types:
            query["actionTypes"] = list(self.action_types)
        return query


def _mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in CALL_MODES else "unknown"


@dataclass(frozen=True)
class CallRecord:
    """One call log record.  ``unknown`` mode is never usable as evidence."""

    call_id: str
    location_id: str
    agent_id: str | None
    contact_id: str | None
    direction: str | None
    mode: str
    started_at: str | None
    duration_s: float | None = None
    outcome: str | None = None
    action_refs: tuple[str, ...] = ()
    transcript_ref: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.call_id, "voice_call_id_missing")
        _require_text(self.location_id, "voice_call_location_missing")
        if self.mode not in CALL_MODES:
            raise ContractViolation("voice_call_mode_invalid")

    @property
    def trial(self) -> bool:
        return self.mode == "trial"

    def as_evidence(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "location_id": self.location_id,
            "agent_id": self.agent_id,
            "contact_id": self.contact_id,
            "direction": self.direction,
            "mode": self.mode,
            "started_at": self.started_at,
            "duration_s": self.duration_s,
            "outcome": self.outcome,
            "action_refs": list(self.action_refs),
            "transcript_ref_present": bool(self.transcript_ref),
        }


def call_record_from_payload(payload: Mapping[str, Any], *, location_id: str) -> CallRecord:
    """Translate one dashboard record without inventing a field.

    A payload with no explicit trial/live marker becomes ``unknown``; the caller
    may not treat it as controlled-test evidence.
    """

    def _first(*names: str) -> Any:
        for name in names:
            if name in payload and payload[name] is not None:
                return payload[name]
        return None

    actions = _first("actionRefs", "action_refs", "actions") or ()
    if isinstance(actions, (str, bytes)) or not isinstance(actions, Iterable):
        actions = ()
    return CallRecord(
        call_id=str(_first("callId", "call_id", "id") or ""),
        location_id=str(_first("locationId", "location_id") or location_id),
        agent_id=(
            None if _first("agentId", "agent_id") is None else str(_first("agentId", "agent_id"))
        ),
        contact_id=(
            None
            if _first("contactId", "contact_id") is None
            else str(_first("contactId", "contact_id"))
        ),
        direction=(
            None if _first("direction", "callType", "call_type") is None
            else str(_first("direction", "callType", "call_type"))
        ),
        mode=_mode(_first("mode", "callMode", "call_mode", "testMode", "test_mode")),
        started_at=(
            None if _first("startedAt", "started_at", "startTime") is None
            else str(_first("startedAt", "started_at", "startTime"))
        ),
        duration_s=(
            None
            if _first("durationSeconds", "duration_s", "duration") is None
            else float(_first("durationSeconds", "duration_s", "duration"))
        ),
        outcome=(
            None if _first("outcome", "callOutcome") is None else str(_first("outcome", "callOutcome"))
        ),
        action_refs=tuple(str(item) for item in actions),
        transcript_ref=(
            None
            if _first("transcriptRef", "transcript_ref", "transcriptId") is None
            else str(_first("transcriptRef", "transcript_ref", "transcriptId"))
        ),
    )


# ---------------------------------------------------------------------------
# controlled-test guards
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GuardLimits:
    """Bounded test exposure.  Defaults are intentionally small."""

    max_test_calls: int = 2
    max_test_duration_s: int = 180
    max_cost_usd: float = 5.0
    max_retries: int = 0
    max_actions_per_test: int = 3
    allowed_destinations: tuple[str, ...] = ()
    allowed_calendars: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.max_test_calls, int) or self.max_test_calls < 1:
            raise ContractViolation("voice_guard_max_calls_invalid")
        if not isinstance(self.max_test_duration_s, int) or self.max_test_duration_s < 1:
            raise ContractViolation("voice_guard_max_duration_invalid")
        if float(self.max_cost_usd) <= 0:
            raise ContractViolation("voice_guard_max_cost_invalid")
        if not isinstance(self.max_retries, int) or self.max_retries < 0:
            raise ContractViolation("voice_guard_max_retries_invalid")
        if not isinstance(self.max_actions_per_test, int) or self.max_actions_per_test < 0:
            raise ContractViolation("voice_guard_max_actions_invalid")
        for value in self.allowed_destinations + self.allowed_calendars:
            _require_text(value, "voice_guard_allowlist_entry_invalid")


def validate_transfer_target(destination_ref: str, limits: GuardLimits) -> str:
    """A transfer target must be on the operator's tenant-bound allowlist."""

    text = _require_text(destination_ref, "voice_transfer_target_missing")
    if not limits.allowed_destinations:
        raise VoiceGuardRefusal(
            "voice_transfer_target_allowlist_missing",
            detail={"unblock": "record the operator-approved transfer destinations"},
        )
    if text not in limits.allowed_destinations:
        raise VoiceGuardRefusal(
            "voice_transfer_target_not_allowed", detail={"target_ref": text}
        )
    return text


def validate_calendar_target(calendar_id: str, limits: GuardLimits) -> str:
    """A booking/calendar target must be on the operator's allowlist."""

    text = _require_text(calendar_id, "voice_calendar_target_missing")
    if not limits.allowed_calendars:
        raise VoiceGuardRefusal(
            "voice_calendar_target_allowlist_missing",
            detail={"unblock": "record the operator-approved calendar ids"},
        )
    if text not in limits.allowed_calendars:
        raise VoiceGuardRefusal(
            "voice_calendar_target_not_allowed", detail={"calendar_id": text}
        )
    return text


BILLING_ACTIONS: tuple[str, ...] = (
    "purchase_number",
    "change_plan",
    "upgrade_plan",
    "downgrade_plan",
    "cancel_plan",
)


def refuse_billing_action(action: str) -> None:
    """No number purchase and no plan change exists on this surface."""

    text = str(action or "").strip()
    if text in BILLING_ACTIONS or not text:
        raise VoiceGuardRefusal(
            "voice_billing_action_forbidden", detail={"action": text or "missing"}
        )


@dataclass(frozen=True)
class ControlledTestPlan:
    plan_id: str
    location_id: str
    agent_id: str
    destination_ref: str
    expected_outcome: str
    estimated_duration_s: int
    estimated_cost_usd: float
    action_count: int
    test_call_index: int
    retries: int
    limits: GuardLimits

    def as_evidence(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "location_id": self.location_id,
            "agent_id": self.agent_id,
            "destination_ref": self.destination_ref,
            "expected_outcome": self.expected_outcome,
            "estimated_duration_s": self.estimated_duration_s,
            "estimated_cost_usd": self.estimated_cost_usd,
            "action_count": self.action_count,
            "test_call_index": self.test_call_index,
            "retries": self.retries,
            "max_test_calls": self.limits.max_test_calls,
            "max_duration_s": self.limits.max_test_duration_s,
            "max_cost_usd": self.limits.max_cost_usd,
        }


def plan_controlled_test(
    *,
    tenant: TenantBinding,
    agent_id: str,
    destination_ref: str,
    expected_outcome: str,
    estimated_duration_s: int,
    estimated_cost_usd: float,
    action_count: int,
    phone: PhoneRouteState,
    limits: GuardLimits,
    test_call_index: int = 1,
    retries: int = 0,
) -> ControlledTestPlan:
    """Budget-check one controlled test.  Refuses, never silently widens."""

    _require_text(agent_id, "voice_test_agent_missing")
    _require_text(expected_outcome, "voice_test_expected_outcome_missing")
    validate_transfer_target(destination_ref, limits)
    if not phone.observed or phone.agent_id != agent_id:
        raise VoiceGuardRefusal(
            "voice_test_requires_bound_agent",
            detail={"phone_state": phone.state},
        )
    if not (1 <= int(test_call_index) <= limits.max_test_calls):
        raise VoiceGuardRefusal(
            "voice_test_call_limit_exceeded",
            detail={"index": int(test_call_index), "max": limits.max_test_calls},
        )
    if int(estimated_duration_s) < 1 or int(estimated_duration_s) > limits.max_test_duration_s:
        raise VoiceGuardRefusal(
            "voice_test_duration_limit_exceeded",
            detail={"seconds": int(estimated_duration_s), "max": limits.max_test_duration_s},
        )
    if float(estimated_cost_usd) < 0 or float(estimated_cost_usd) > limits.max_cost_usd:
        raise VoiceGuardRefusal(
            "voice_test_cost_limit_exceeded",
            detail={"usd": float(estimated_cost_usd), "max": limits.max_cost_usd},
        )
    if int(action_count) < 0 or int(action_count) > limits.max_actions_per_test:
        raise VoiceGuardRefusal(
            "voice_test_action_limit_exceeded",
            detail={"actions": int(action_count), "max": limits.max_actions_per_test},
        )
    if int(retries) > limits.max_retries:
        raise VoiceGuardRefusal(
            "voice_test_retry_limit_exceeded",
            detail={"retries": int(retries), "max": limits.max_retries},
        )
    seed = {
        "tenant": tenant.location_id,
        "agent_id": agent_id,
        "destination_ref": destination_ref,
        "expected_outcome": expected_outcome,
        "index": int(test_call_index),
    }
    plan_id = "vtest_" + hashlib.sha256(canonical_json(seed).encode("utf-8")).hexdigest()[:16]
    return ControlledTestPlan(
        plan_id=plan_id,
        location_id=tenant.location_id,
        agent_id=agent_id,
        destination_ref=destination_ref,
        expected_outcome=expected_outcome,
        estimated_duration_s=int(estimated_duration_s),
        estimated_cost_usd=float(estimated_cost_usd),
        action_count=int(action_count),
        test_call_index=int(test_call_index),
        retries=int(retries),
        limits=limits,
    )


BUSINESS_OUTCOMES: tuple[str, ...] = (
    "booking_created",
    "transfer_delivered",
    "field_updated",
    "workflow_started",
    "knowledge_resolved",
)


@dataclass(frozen=True)
class ControlledTestEvidence:
    plan_id: str
    call: CallRecord
    business_outcome: str
    outcome_ref: str

    def __post_init__(self) -> None:
        _require_text(self.plan_id, "voice_test_plan_id_missing")
        if not isinstance(self.call, CallRecord):
            raise ContractViolation("voice_test_call_invalid")
        _require_text(self.business_outcome, "voice_test_business_outcome_missing")
        _require_text(self.outcome_ref, "voice_test_outcome_ref_missing")

    def as_evidence(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "call": self.call.as_evidence(),
            "business_outcome": self.business_outcome,
            "outcome_ref": self.outcome_ref,
        }


@dataclass(frozen=True)
class ControlledTestReceipt:
    verified: bool
    plan_id: str
    call_id: str
    agent_id: str | None
    contact_id: str | None
    business_outcome: str
    outcome_ref: str
    checks: tuple[str, ...]

    def as_evidence(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "plan_id": self.plan_id,
            "call_id": self.call_id,
            "agent_id": self.agent_id,
            "contact_id": self.contact_id,
            "business_outcome": self.business_outcome,
            "outcome_ref": self.outcome_ref,
            "checks": list(self.checks),
        }


def verify_controlled_test(
    plan: ControlledTestPlan, evidence: ControlledTestEvidence
) -> ControlledTestReceipt:
    """Bind one call to the agent, contact, action and business outcome."""

    if evidence.plan_id != plan.plan_id:
        raise VoiceGuardRefusal(
            "voice_test_plan_mismatch", detail={"expected": plan.plan_id}
        )
    call = evidence.call
    if call.mode != "trial":
        raise VoiceGuardRefusal(
            "voice_test_call_not_trial", detail={"mode": call.mode}
        )
    if call.location_id != plan.location_id:
        raise VoiceGuardRefusal(
            "voice_test_call_tenant_mismatch", detail={"expected": plan.location_id}
        )
    if call.agent_id != plan.agent_id:
        raise VoiceGuardRefusal(
            "voice_test_call_agent_mismatch", detail={"expected": plan.agent_id}
        )
    if not call.contact_id:
        raise VoiceGuardRefusal("voice_test_call_contact_missing")
    if evidence.business_outcome not in BUSINESS_OUTCOMES:
        raise VoiceGuardRefusal(
            "voice_test_business_outcome_unsupported",
            detail={"outcome": evidence.business_outcome},
        )
    if plan.action_count > 0 and not call.action_refs:
        raise VoiceGuardRefusal("voice_test_action_evidence_missing")
    return ControlledTestReceipt(
        verified=True,
        plan_id=plan.plan_id,
        call_id=call.call_id,
        agent_id=call.agent_id,
        contact_id=call.contact_id,
        business_outcome=evidence.business_outcome,
        outcome_ref=evidence.outcome_ref,
        checks=(
            "call_mode_trial",
            "tenant_bound",
            "agent_bound",
            "contact_bound",
            "action_evidence_present",
            "business_outcome_recorded",
        ),
    )


def plan_route_activation(
    *, plan: ControlledTestPlan, rollback: RouteRollback
) -> PhoneRouteHandoff:
    """Require a captured prior route and hand the change to the routing owner."""

    if rollback.location_id != plan.location_id:
        raise VoiceGuardRefusal("voice_rollback_tenant_mismatch")
    if rollback.agent_id != plan.agent_id:
        raise VoiceGuardRefusal("voice_rollback_agent_mismatch")
    return PhoneRouteHandoff(
        location_id=plan.location_id,
        agent_id=plan.agent_id,
        number_ref=rollback.number_ref,
        rollback_ref=rollback.previous_route_ref,
        requested_action="assign_inbound_route_to_agent",
        executed=False,
        owner="authorized phone/routing owner (number procurement owner)",
        detail=(
            "this adapter does not change routing; the owner applies the route "
            "and the rollback reference restores the prior route"
        ),
    )


# ---------------------------------------------------------------------------
# caller input is untrusted for administrative actions
# ---------------------------------------------------------------------------

_CALLER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "caller_requests_credential",
        re.compile(r"\b(api[ _-]?key|token|password|secret|credential)s?\b", re.I),
    ),
    (
        "caller_requests_agent_rewrite",
        re.compile(
            r"\b(change|update|rewrite|reprogram|modify|edit)\b[^\n]{0,40}\b(agent|prompt|instructions?|settings?|configuration)\b",
            re.I,
        ),
    ),
    (
        "caller_requests_routing_change",
        re.compile(
            r"\b(change|forward|redirect|re-?route|swap)\b[^\n]{0,40}\b(route|routing|number|phone)\b",
            re.I,
        ),
    ),
    ("caller_requests_arbitrary_url", re.compile(r"https?://|\bwww\.", re.I)),
    (
        "caller_requests_outbound_dial",
        re.compile(r"\b(call|dial|phone|ring)\b[^\n]{0,30}(\+?\d[\d\s().-]{6,})", re.I),
    ),
    (
        "caller_requests_billing_change",
        re.compile(
            r"\b(buy|purchase|upgrade|downgrade|cancel|change)\b[^\n]{0,30}\b(number|plan|subscription|billing)\b",
            re.I,
        ),
    ),
)


@dataclass(frozen=True)
class CallerScreen:
    allowed: bool
    rules: tuple[str, ...]

    def as_evidence(self) -> dict[str, Any]:
        # The utterance itself is never echoed or stored here.
        return {"allowed": self.allowed, "rules": list(self.rules)}


def screen_caller_input(text: str) -> CallerScreen:
    """Screen speech for administrative intent.  Names only; never the words."""

    spoken = str(text or "")
    hits = tuple(rule for rule, pattern in _CALLER_PATTERNS if pattern.search(spoken))
    return CallerScreen(allowed=not hits, rules=hits)


def require_caller_safe(text: str) -> CallerScreen:
    screen = screen_caller_input(text)
    if not screen.allowed:
        raise VoiceGuardRefusal(
            "voice_caller_admin_action_refused",
            detail={"rules": list(screen.rules)},
        )
    return screen


# ---------------------------------------------------------------------------
# provisioning plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProvisioningPlan:
    location_id: str
    provider: str
    agent_step: str
    replacement_agent_id: str | None
    actions: tuple[VoiceActionSpec, ...]
    knowledge_source_ids: tuple[str, ...]
    steps: tuple[str, ...]

    def as_evidence(self) -> dict[str, Any]:
        return {
            "location_id": self.location_id,
            "provider": self.provider,
            "agent_step": self.agent_step,
            "replacement_agent_id": self.replacement_agent_id,
            "action_count": len(self.actions),
            "knowledge_source_count": len(self.knowledge_source_ids),
            "steps": list(self.steps),
            "phone_handoff_required": True,
            "controlled_test_required": True,
            "rollback_required": True,
        }


def plan_provisioning(
    *,
    tenant: TenantBinding,
    spec: VoiceAgentSpec,
    provider: VoiceProviderChoice,
    existing_agent_names: Sequence[tuple[str, str]] = (),
    actions: Sequence[VoiceActionSpec] = (),
    allow_replace: bool = False,
) -> ProvisioningPlan:
    """Build dependency-ordered steps; refuse an unapproved replacement.

    ``existing_agent_names`` is ``(agent_id, name)`` from a real inventory read.
    Duplicate display names remain distinct ids (A09's principle applied here).
    """

    if not provider.native:
        raise VoiceGuardRefusal(
            "voice_provider_not_native",
            detail={"provider": provider.provider, "hint": "use the Skill 38 handoff route"},
        )
    wanted = spec.name.strip().casefold()
    replacement = next(
        (agent_id for agent_id, name in existing_agent_names if str(name).strip().casefold() == wanted),
        None,
    )
    if replacement is not None and not allow_replace:
        raise VoiceGuardRefusal(
            "voice_agent_replacement_unapproved",
            detail={"existing_agent_id": replacement},
        )
    steps = (
        "inventory_agents_and_phone_route",
        "create_or_update_agent",
        "create_actions",
        "attach_actions_to_agent",
        "attach_knowledge_sources",
        "handoff_phone_assignment",
        "controlled_test",
        "activate_route_with_rollback",
    )
    return ProvisioningPlan(
        location_id=tenant.location_id,
        provider=provider.provider,
        agent_step="update_agent" if replacement else "create_agent",
        replacement_agent_id=replacement,
        actions=tuple(actions),
        knowledge_source_ids=tuple(spec.knowledge_source_ids),
        steps=steps,
    )


# ---------------------------------------------------------------------------
# the adapter
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class VoiceInventory:
    result: Any
    agents: tuple[tuple[str, str], ...]
    phone: PhoneRouteState

    def as_evidence(self) -> dict[str, Any]:
        return {
            "agent_count": len(self.agents),
            "agents": [{"agent_id": agent_id, "name": name} for agent_id, name in self.agents],
            "phone": self.phone.as_evidence(),
        }


class VoiceAiAdapter:
    """Typed native Voice AI surface over the frozen public adapter.

    Every HTTP call goes through ``PublicGhlAdapter.call``; this class adds the
    operation map, the pending-version refusal, the guards and the handoffs,
    and nothing else.
    """

    def __init__(
        self,
        *,
        public: PublicGhlAdapter,
        operations: Mapping[str, Any] | None = None,
        guards: GuardLimits | None = None,
        clock=None,
    ) -> None:
        if not isinstance(public, PublicGhlAdapter):
            raise ContractViolation("voice_public_adapter_required")
        self._public = public
        self._operations = dict(operations) if operations is not None else voice_operations()
        self._guards = guards or GuardLimits()
        self._clock = clock or _now
        # Reuse the recording transport already shipped with the workflow family
        # instead of forking a second response-body seam.
        from .workflow_v4 import RecordingTransport

        base: Transport = getattr(public, "_transport", None)
        if base is None or not callable(getattr(base, "request", None)):
            raise ContractViolation("voice_transport_unavailable")
        if isinstance(base, RecordingTransport):
            self._transport = base
        else:
            self._transport = RecordingTransport(base)
            public._transport = self._transport  # ponytail: public adapter has no accessor

    @property
    def guards(self) -> GuardLimits:
        return self._guards

    # -- internals -----------------------------------------------------

    def _row(self, operation_id: str) -> Any:
        row = self._operations.get(operation_id)
        if row is None:
            raise VoiceContractPending(
                "voice_operation_row_missing",
                operation_id=operation_id,
                detail={"unblock": "WF00 adds the voice-ai rows to public/operations.py"},
            )
        return row

    def _require_verified_version(self, operation_id: str) -> Any:
        row = self._row(operation_id)
        if getattr(row, "version", None) is None and (
            getattr(row, "blocker", None) == WIRE_VERSION_UNVERIFIED
        ):
            raise VoiceContractPending(
                "voice_wire_version_unverified",
                operation_id=operation_id,
                detail={
                    "doc_url": getattr(row, "doc_url", VOICE_AI_DOCS),
                    "blocker": WIRE_VERSION_UNVERIFIED,
                    "unblock": WIRE_VERSION_UNBLOCK,
                },
            )
        return row

    def _call(self, operation_id: str, **kwargs: Any):
        self._require_verified_version(operation_id)
        return self._public.call(operation_id=operation_id, **kwargs)

    def _payload_at(self, index: int) -> Any:
        records = getattr(self._transport, "records", [])
        if index < 0 or index >= len(records):
            return None
        body = records[index].body
        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def capability(self, operation_id: str, *, tenant: TenantBinding | str | None):
        self._require_verified_version(operation_id)
        location_id = (
            tenant.location_id if isinstance(tenant, TenantBinding) else str(tenant or "")
        ).strip()
        if not location_id:
            from .capability import CapabilityGate

            return CapabilityGate().get(operation_id)
        return self._public.capability(operation_id, tenant=location_id)

    # -- reads ---------------------------------------------------------

    def list_agents(
        self, *, tenant: TenantBinding, page: int = 1, page_size: int = 50, attempt: int = 1
    ):
        if not isinstance(page, int) or page < 1:
            raise ContractViolation("voice_agent_page_invalid")
        if not isinstance(page_size, int) or not (1 <= page_size <= MAX_PAGE_SIZE):
            raise ContractViolation("voice_agent_page_size_invalid")
        mark = len(getattr(self._transport, "records", []))
        result = self._call(
            AGENTS_LIST,
            tenant=tenant,
            query={"page": page, "pageSize": page_size},
            attempt=attempt,
        )
        payload = self._payload_at(mark) if result.status is Status.ok else None
        return result, payload

    def get_agent(self, *, tenant: TenantBinding, agent_id: str, attempt: int = 1):
        _require_text(agent_id, "voice_agent_id_missing")
        mark = len(getattr(self._transport, "records", []))
        result = self._call(
            AGENTS_GET, tenant=tenant, path_params={"agentId": agent_id}, attempt=attempt
        )
        return result, (self._payload_at(mark) if result.status is Status.ok else None)

    def get_action(self, *, tenant: TenantBinding, action_id: str, attempt: int = 1):
        _require_text(action_id, "voice_action_id_missing")
        mark = len(getattr(self._transport, "records", []))
        result = self._call(
            ACTIONS_GET, tenant=tenant, path_params={"actionId": action_id}, attempt=attempt
        )
        return result, (self._payload_at(mark) if result.status is Status.ok else None)

    # -- writes --------------------------------------------------------

    def create_agent(
        self,
        *,
        tenant: TenantBinding,
        spec: VoiceAgentSpec,
        idempotency_key: str,
        approval: ApprovalRef | Mapping[str, Any] | str | None = None,
        attempt: int = 1,
    ):
        """Create one agent, then read it back by name through the list row.

        The new id is not known before transport, so the mandatory read-back is
        the documented list read matched by name.  A shallow/mismatched list
        envelope is settled by a shape-tolerant name search -- never assumed.
        """

        mark = len(getattr(self._transport, "records", []))
        result = self._call(
            AGENTS_CREATE,
            tenant=tenant,
            body=spec.to_body(tenant.location_id),
            idempotency_key=idempotency_key,
            approval=approval,
            readback=ReadbackSpec(
                operation_id=AGENTS_LIST,
                query={"page": 1, "pageSize": 50},
                expect={"name": spec.name},
                scan_nested=True,
                description="duplicate-create reconciliation by agent name",
            ),
            attempt=attempt,
        )
        payload = self._payload_at(mark)
        if result.status is Status.ok:
            return self._enrich_agent(result, payload, spec.name), payload
        if not (
            result.status is Status.unknown_outcome
            and result.readback is not None
            and getattr(result.readback.result, "value", "") == "mismatch"
        ):
            return result, None
        # The read-back is shallow/short-circuit; settle the pending row, then
        # let the name search decide.  Exactly like the workflow create path.
        self._public.reconcile(result)
        listed, listed_payload = self.list_agents(tenant=tenant, attempt=attempt)
        found = _find_agent_by_name(listed_payload, spec.name) if listed.status is Status.ok else None
        if found is None:
            return result, None
        settled = replace(result, status=Status.ok, error=None)
        return self._enrich_agent(settled, found, spec.name), found

    def update_agent(
        self,
        *,
        tenant: TenantBinding,
        agent_id: str,
        patch: Mapping[str, Any],
        idempotency_key: str,
        approval: ApprovalRef | Mapping[str, Any] | str | None = None,
        attempt: int = 1,
    ):
        _require_text(agent_id, "voice_agent_id_missing")
        if not isinstance(patch, Mapping) or not patch:
            raise ContractViolation("voice_agent_patch_invalid")
        expect = {key: value for key, value in patch.items() if not isinstance(value, (Mapping, list, tuple))}
        if not expect:
            # A readback with no expectation is zero verification; pick the id.
            expect = {"id": agent_id}
        mark = len(getattr(self._transport, "records", []))
        result = self._call(
            AGENTS_UPDATE,
            tenant=tenant,
            path_params={"agentId": agent_id},
            body=dict(patch),
            idempotency_key=idempotency_key,
            approval=approval,
            readback=ReadbackSpec(
                operation_id=AGENTS_GET,
                target_params={"agentId": agent_id},
                expect=expect,
            ),
            attempt=attempt,
        )
        return result, (self._payload_at(mark) if result.status is Status.ok else None)

    def create_action(
        self,
        *,
        tenant: TenantBinding,
        spec: VoiceActionSpec,
        idempotency_key: str,
        approval: ApprovalRef | Mapping[str, Any] | str | None = None,
        action_readback_id: str | None = None,
        attempt: int = 1,
    ):
        """Create one action, read back by the id its create response returned.

        The voice-ai module documents no actions LIST/SEARCH row, so a created
        action can only be read back by id.  Until WF00/F-WF01 publishes a
        create-response read-back policy (or an actions list row), a caller that
        does not hold that id gets a loud ``VoiceContractPending`` and NO write
        is attempted.  ``action_readback_id`` is the id captured from the create
        response by the operator's two-step flow.
        """

        if spec.action_type == "transfer":
            validate_transfer_target(
                str(spec.parameters.get("destination_ref") or ""),
                self._guards,
            )
        if spec.action_type == "booking":
            validate_calendar_target(
                str(spec.parameters.get("calendar_id") or ""),
                self._guards,
            )
        target_id = str(action_readback_id or "").strip()
        if not target_id:
            raise VoiceContractPending(
                "voice_action_create_readback_pending",
                operation_id=ACTIONS_CREATE,
                detail={
                    "unblock": (
                        "an actions LIST/SEARCH row, or a WF01 provider "
                        "create-response read-back policy; the created id is "
                        "not knowable before transport"
                    ),
                    "doc_url": VOICE_AI_DOCS,
                },
            )
        mark = len(getattr(self._transport, "records", []))
        result = self._call(
            ACTIONS_CREATE,
            tenant=tenant,
            body=spec.to_body(tenant.location_id),
            idempotency_key=idempotency_key,
            approval=approval,
            readback=ReadbackSpec(
                operation_id=ACTIONS_GET,
                target_params={"actionId": target_id},
                expect={"actionType": spec.action_type},
            ),
            attempt=attempt,
        )
        return result, (self._payload_at(mark) if result.status is Status.ok else None)

    def update_action(
        self,
        *,
        tenant: TenantBinding,
        action_id: str,
        patch: Mapping[str, Any],
        idempotency_key: str,
        approval: ApprovalRef | Mapping[str, Any] | str | None = None,
        attempt: int = 1,
    ):
        _require_text(action_id, "voice_action_id_missing")
        if not isinstance(patch, Mapping) or not patch:
            raise ContractViolation("voice_action_patch_invalid")
        expect = {key: value for key, value in patch.items() if not isinstance(value, (Mapping, list, tuple))}
        if not expect:
            expect = {"id": action_id}
        mark = len(getattr(self._transport, "records", []))
        result = self._call(
            ACTIONS_UPDATE,
            tenant=tenant,
            path_params={"actionId": action_id},
            body=dict(patch),
            idempotency_key=idempotency_key,
            approval=approval,
            readback=ReadbackSpec(
                operation_id=ACTIONS_GET,
                target_params={"actionId": action_id},
                expect=expect,
            ),
            attempt=attempt,
        )
        return result, (self._payload_at(mark) if result.status is Status.ok else None)

    def _enrich_agent(self, result: Any, payload: Any, name: str) -> Any:
        evidence = dict(result.evidence)
        merged = dict(evidence.get("voice_ai") or {})
        merged.update(
            {
                "operation": "create_agent",
                "agent_name": name,
                "agent_id": _agent_identity(payload),
                "configured": True,
                "operationally_active": False,
                "readback": "voiceAi.agents.list",
                "readback_matched_by": "name",
            }
        )
        evidence["voice_ai"] = merged
        evidence["finished_at"] = self._clock()
        return replace(result, evidence=evidence)

    # -- inventory, phone, call logs -----------------------------------

    def inventory(self, *, tenant: TenantBinding) -> VoiceInventory:
        result, payload = self.list_agents(tenant=tenant)
        agents: list[tuple[str, str]] = []
        if result.status is Status.ok and isinstance(payload, Mapping):
            for row in payload.get("agents") or ():
                if isinstance(row, Mapping) and row.get("id") is not None:
                    agents.append((str(row["id"]), str(row.get("name") or "")))
        return VoiceInventory(
            result=result, agents=tuple(agents), phone=PhoneRouteState.unknown(tenant.location_id)
        )

    def inspect_phone_assignment(self, *, tenant: TenantBinding) -> PhoneRouteState:
        """Honest separate read: this lane has no documented routing read row.

        It therefore reports ``unknown`` with the exact pending action instead
        of inferring a route from an agent id.
        """

        return PhoneRouteState.unknown(tenant.location_id)

    def list_call_logs(self, *, tenant: TenantBinding, query: CallLogQuery, attempt: int = 1):
        mark = len(getattr(self._transport, "records", []))
        result = self._call(
            CALLS_LIST, tenant=tenant, query=query.to_query(), attempt=attempt
        )
        payload = self._payload_at(mark) if result.status is Status.ok else None
        calls: list[CallRecord] = []
        if isinstance(payload, Mapping):
            rows = payload.get("callLogs") or payload.get("calls") or payload.get("data") or ()
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, Mapping):
                        record = call_record_from_payload(row, location_id=tenant.location_id)
                        if record.call_id:
                            calls.append(record)
        return result, tuple(calls)

    def get_call(self, *, tenant: TenantBinding, call_id: str, attempt: int = 1):
        _require_text(call_id, "voice_call_id_missing")
        mark = len(getattr(self._transport, "records", []))
        result = self._call(
            CALLS_GET, tenant=tenant, path_params={"callId": call_id}, attempt=attempt
        )
        payload = self._payload_at(mark) if result.status is Status.ok else None
        record = (
            call_record_from_payload(payload, location_id=tenant.location_id)
            if isinstance(payload, Mapping)
            else None
        )
        return result, record


# ---------------------------------------------------------------------------
# helpers and the public-adapter factory
# ---------------------------------------------------------------------------


def _agent_rows(payload: Any) -> list[Any] | None:
    if not isinstance(payload, Mapping):
        return None
    for name in ("agents", "data", "items", "results"):
        rows = payload.get(name)
        if isinstance(rows, list):
            return rows
    return None


def _find_agent_by_name(payload: Any, name: str) -> Mapping[str, Any] | None:
    wanted = str(name).strip()
    for row in _agent_rows(payload) or ():
        if isinstance(row, Mapping) and str(row.get("name") or "").strip() == wanted:
            return row
    return None


def _agent_identity(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    for name in ("id", "_id", "agentId", "agent_id"):
        value = payload.get(name)
        if value is not None and str(value).strip():
            return str(value)
    return None


def load_voice_adapter(
    location_id: str,
    *,
    env: Mapping[str, str] | None = None,
    transport: Transport | None = None,
    capability: Any = None,
    operations: Mapping[str, Any] | None = None,
    guards: GuardLimits | None = None,
):
    """Build ``(VoiceAiAdapter | None, reason)``; default-deny when it exists."""

    try:
        auth = resolve_auth(kind=AuthKind.location_pit, location_id=location_id, env=env)
    except Exception as exc:  # noqa: BLE001 - credential absence is a named refusal
        return None, "public voice credential unavailable: %s" % type(exc).__name__
    public = PublicGhlAdapter(
        auth=auth, transport=transport, capability=capability
    )
    return (
        VoiceAiAdapter(public=public, operations=operations, guards=guards),
        "public adapter built; gate is default-deny",
    )


def result_summary(result: Any) -> dict[str, Any]:
    """A JSON-safe envelope summary for the CLI (no response body, no secret)."""

    readback = getattr(result, "readback", None)
    return {
        "status": getattr(getattr(result, "status", None), "value", None),
        "operation_id": result.operation_id,
        "receipt_id": result.receipt_id,
        "http_status": result.http_status,
        "tenant": result.tenant,
        "attempt": result.attempt,
        "version_header": result.version_header,
        "transport": result.transport,
        "readback": None if readback is None else getattr(readback.result, "value", None),
        "error": dict(result.error) if result.error else None,
        "evidence": dict(result.evidence),
    }


__all__ = [
    "AGENTS_LIST",
    "AGENTS_GET",
    "AGENTS_CREATE",
    "AGENTS_UPDATE",
    "ACTIONS_GET",
    "ACTIONS_CREATE",
    "ACTIONS_UPDATE",
    "CALLS_LIST",
    "CALLS_GET",
    "VOICE_OPERATION_IDS",
    "VOICE_OPERATION_ROWS",
    "WIRE_VERSION_UNVERIFIED",
    "WIRE_VERSION_UNBLOCK",
    "PROVIDER_NATIVE",
    "PROVIDER_SELF_HOSTED",
    "PROVIDERS",
    "VoiceProviderChoice",
    "select_provider",
    "VoiceAgentSpec",
    "VoiceActionSpec",
    "ALLOWED_ACTION_TYPES",
    "ALLOWED_CALL_PURPOSES",
    "PhoneRouteState",
    "RouteRollback",
    "PhoneRouteHandoff",
    "CallLogQuery",
    "CallRecord",
    "call_record_from_payload",
    "GuardLimits",
    "validate_transfer_target",
    "validate_calendar_target",
    "refuse_billing_action",
    "ControlledTestPlan",
    "plan_controlled_test",
    "ControlledTestEvidence",
    "ControlledTestReceipt",
    "verify_controlled_test",
    "plan_route_activation",
    "CallerScreen",
    "screen_caller_input",
    "require_caller_safe",
    "ProvisioningPlan",
    "plan_provisioning",
    "VoiceInventory",
    "VoiceAiAdapter",
    "VoiceContractPending",
    "VoiceGuardRefusal",
    "voice_operations",
    "load_voice_adapter",
    "result_summary",
]
