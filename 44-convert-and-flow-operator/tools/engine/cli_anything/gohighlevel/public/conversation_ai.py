"""Native GHL Conversation AI adapter - WF28.

WHY THIS EXISTS
---------------
GHL exposes a native Conversation AI agent beside the OpenClaw brain.  The two
are not interchangeable, and a location that runs both without an ownership
record replies twice to one person.  This adapter is the ONLY write path for the
native agent, and it is deliberately narrow:

* every call goes through ``PublicGhlAdapter`` (method, path, Version, auth
  class, tenant binding, approval seam, capability gate, idempotency
  fingerprint and mandatory read-back all come from the frozen adapter);
* the operation rows live in ``public/operations.py``, owned by WF00.  No row is
  invented here: when a required row is absent this module refuses loudly and
  names the checkpoint instead of guessing a path or a Version;
* a new agent is created in a NON-SENDING mode first.  ``off`` is the only
  accepted create mode; moving to ``suggestive`` or ``auto-pilot`` is a
  separate, approved update;
* an existing production primary agent is never switched here.  Any patch that
  names primary ownership is refused outright; that transition is a separate
  authorised step with its own approval and snapshot;
* a non-empty ``fullPrompt`` is the effective generation instruction instead of
  the separate personality/goal/instructions fields.  A write that would be
  shadowed by ``fullPrompt`` is refused (``prompt_ineffective``) and the
  effective prompt is what the caller verifies, not the saved text fields;
* the seven native channels are an explicit map.  LinkedIn, public comments and
  all-in-one labels are refused; WebChat and Live_Chat are distinct.

OWNERSHIP
---------
``38-conversational-ai-system/tools/responder_policy.py`` decides WHICH
component owns a channel.  This adapter only runs after a native verdict and
performs no ownership decision of its own beyond refusing an unsafe write.

Acceptance: B11 (responder side), B12, B17 (widget thread/responder seam uses
the same lease), IG-AI-04, IG-AI-05, IG-AI-08.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Tuple

from .adapter import ApprovalRef, PublicGhlAdapter
from .auth import TenantBinding
from .errors import ContractViolation
from .outbound_sender import CapturingTransport
from .readback import ReadbackSpec
from .result import canonical_json, fingerprint_bytes, redact_mapping

#: Native channel enumerations, transcribed from Document 1 §25.5 (the create
#: schema lists exactly these seven).  Kept identical to the Skill 38 policy
#: module; ``tests/test_conversation_ai.py`` asserts the two maps agree.
NATIVE_CHANNELS: Tuple[str, ...] = (
    "IG", "FB", "SMS", "WebChat", "WhatsApp", "Live_Chat", "Email",
)

NATIVE_MODES: Tuple[str, ...] = ("off", "suggestive", "auto-pilot")
CREATE_MODE = "off"

CHANNEL_MAP = {
    "sms": "SMS", "text": "SMS", "phone": "SMS",
    "email": "Email",
    "fb": "FB", "facebook": "FB", "facebook_dm": "FB", "messenger": "FB",
    "ig": "IG", "instagram": "IG", "instagram_dm": "IG",
    "whatsapp": "WhatsApp",
    "webchat": "WebChat", "web_chat": "WebChat", "web_chat_widget": "WebChat",
    "live_chat": "Live_Chat", "livechat": "Live_Chat", "live-chat": "Live_Chat",
}

UNSUPPORTED_CHANNELS = {
    "linkedin": "LinkedIn has no native Conversation AI channel enumeration",
    "fb_comment": "public Facebook comments are not a native conversation channel",
    "fb_comments": "public Facebook comments are not a native conversation channel",
    "facebook_comments": "public Facebook comments are not a native conversation channel",
    "instagram_comments": "public Instagram comments are not a native conversation channel",
    "all_in_one": "an all-in-one label is not a native channel; name the real destination",
    "all_in_one_chat": "an all-in-one label is not a native channel; name the real destination",
    "gmb": "Google Business Messages has no native Conversation AI channel",
    "tiktok": "TikTok has no native Conversation AI channel",
    "youtube": "YouTube has no native Conversation AI channel",
}

#: Required WF00 operation rows.  The ids are the contract names this laneto
#: consumes; WF00 owns the rows (method, exact path, per-operation Version,
#: scopes, read-back plan).  Absent row -> refuse, never guess.
LIST = "conversation_ai.agents.list"
GET = "conversation_ai.agents.get"
CREATE = "conversation_ai.agents.create"
UPDATE = "conversation_ai.agents.update"
REQUIRED_OPERATIONS: Tuple[str, ...] = (LIST, GET, CREATE, UPDATE)
OPERATIONS_CHECKPOINT = "WF00 operation rows for native Conversation AI"

#: Body fields transcribed from Document 1 §25.1/§25.5.  No other field is sent.
CREATE_FIELDS: Tuple[str, ...] = (
    "name", "channels", "mode", "fullPrompt", "personality", "goal",
    "instructions",
)
STRUCTURED_PROMPT_FIELDS: Tuple[str, ...] = ("personality", "goal", "instructions")
#: Any of these in an update means "switch who owns the agent", which this
#: adapter never does.
PRIMARY_FIELDS: Tuple[str, ...] = (
    "primary", "isPrimary", "is_primary", "primaryAgent", "primary_agent",
)

_PATH_PARAM = re.compile(r"\{([^{}]+)\}")


def native_channel_for(channel: Any) -> str:
    """Map one Skill 38 channel name to its exact native enumeration."""
    if not isinstance(channel, str) or not channel.strip():
        raise ContractViolation("conversation_channel_missing")
    key = channel.strip().lower()
    if key in UNSUPPORTED_CHANNELS:
        raise ContractViolation(
            "conversation_channel_unsupported",
            detail={"channel": key, "reason": UNSUPPORTED_CHANNELS[key]},
        )
    native = CHANNEL_MAP.get(key)
    if native is None:
        if key == "chat":
            raise ContractViolation(
                "conversation_channel_ambiguous",
                detail={"channel": key, "hint": "name webchat or live_chat"},
            )
        raise ContractViolation(
            "conversation_channel_unsupported",
            detail={"channel": key, "supported": list(CHANNEL_MAP)},
        )
    return native


def native_channels_for(channels: Sequence[Any]) -> Tuple[str, ...]:
    if isinstance(channels, (str, bytes)) or not isinstance(channels, Sequence):
        raise ContractViolation("conversation_channels_invalid")
    mapped: list[str] = []
    for channel in channels:
        native = native_channel_for(channel)
        if native not in mapped:
            mapped.append(native)
    if not mapped:
        raise ContractViolation("conversation_channels_empty")
    return tuple(mapped)


def effective_prompt(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve ``fullPrompt`` precedence over the structured prompt fields.

    A non-empty ``fullPrompt`` IS the generation instruction; the separate
    personality/goal/instructions fields are saved but do not affect a reply.
    """
    full = str(fields.get("fullPrompt") or "").strip()
    structured = {
        name: str(fields[name])
        for name in STRUCTURED_PROMPT_FIELDS
        if fields.get(name) not in (None, "")
    }
    if full:
        return {
            "source": "fullPrompt",
            "text": full,
            "shadowed_fields": sorted(structured),
        }
    if structured:
        text = "\n".join(
            "%s: %s" % (name, structured[name])
            for name in STRUCTURED_PROMPT_FIELDS
            if name in structured
        )
        return {"source": "structured_fields", "text": text, "shadowed_fields": []}
    return {"source": "none", "text": None, "shadowed_fields": []}


def idempotency_key(logical_key: Any) -> str:
    """Deterministic adapter key for a durable logical key (gxo_<short>-<hex>)."""
    raw = str(logical_key or "").strip()
    if not raw:
        raise ContractViolation("idempotency_key_required")
    return "gxo_conv-ai-" + fingerprint_bytes(raw.encode("utf-8"))[:32]


@dataclass(frozen=True)
class AgentSpec:
    """The approved behaviour a caller wants the native agent to hold."""

    name: str
    channels: Sequence[str]
    mode: str = CREATE_MODE
    full_prompt: Optional[str] = None
    personality: Optional[str] = None
    goal: Optional[str] = None
    instructions: Optional[str] = None

    def fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "name": self.name,
            "channels": list(native_channels_for(self.channels)),
            "mode": self.mode,
        }
        if self.full_prompt is not None:
            fields["fullPrompt"] = self.full_prompt
        for name in STRUCTURED_PROMPT_FIELDS:
            value = getattr(self, name)
            if value is not None:
                fields[name] = value
        return fields


@dataclass(frozen=True)
class AgentChange:
    """One adapter outcome: the frozen envelope plus what this lane verified."""

    operation: Any
    agent_id: Optional[str]
    mode: str
    native_channels: Tuple[str, ...]
    effective_prompt: Mapping[str, Any]
    snapshot: Mapping[str, Any] | None = None
    snapshot_digest: str | None = None
    readback_expect: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return str(getattr(self.operation.status, "value", self.operation.status)) == "ok"


def _row_attr(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def _agent_payload(parsed: Any) -> Optional[dict[str, Any]]:
    """Find the agent object in a response envelope, without inventing fields."""
    if not isinstance(parsed, Mapping):
        return None
    for key in ("agent", "data"):
        value = parsed.get(key)
        if isinstance(value, Mapping) and value.get("id"):
            return dict(value)
    for key in ("agents", "data"):
        value = parsed.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping) and item.get("id"):
                    return dict(item)
    if parsed.get("id"):
        return dict(parsed)
    return None


class ConversationAiAdapter:
    """Native Conversation AI reads and narrow, gated writes for one tenant."""

    def __init__(
        self,
        adapter: PublicGhlAdapter,
        tenant: TenantBinding,
        *,
        operations: Any = None,
        transport: Any = None,
    ) -> None:
        if not isinstance(adapter, PublicGhlAdapter):
            raise ContractViolation("adapter_required")
        if not isinstance(tenant, TenantBinding):
            raise ContractViolation("tenant_required")
        self._adapter = adapter
        self.tenant = tenant
        self._operations = operations if operations is not None else _default_operations()
        self._verify_operations()
        self._capture = transport
        if self._capture is not None and not hasattr(self._capture, "last_response"):
            self._capture = CapturingTransport(self._capture)

    # -- reads -------------------------------------------------------------

    def inventory(self, *, query: Mapping[str, object] | None = None,
                  timeout_s: float | None = None) -> Any:
        return self._adapter.call(
            operation_id=LIST, tenant=self.tenant, query=query,
            timeout_s=timeout_s,
        )

    def read(self, agent_id: str, *, timeout_s: float | None = None) -> Any:
        return self._adapter.call(
            operation_id=GET, tenant=self.tenant,
            path_params=self._single_param(GET, agent_id),
            timeout_s=timeout_s,
        )

    def effective_prompt_of(self, agent_id: str) -> dict[str, Any]:
        """Read the agent and resolve the prompt GHL actually generates from."""
        result = self.read(agent_id)
        if str(getattr(result.status, "value", result.status)) != "ok":
            return {"source": "unreadable", "text": None, "shadowed_fields": []}
        agent = self._agent_from_last_response()
        if agent is None:
            return {"source": "unreadable", "text": None, "shadowed_fields": []}
        return effective_prompt(agent)

    # -- writes ------------------------------------------------------------

    def create(self, spec: AgentSpec, *, logical_key: str,
               approval: ApprovalRef | str | Mapping[str, Any] | None = None,
               snapshot_sink: Any = None,
               timeout_s: float | None = None) -> AgentChange:
        """Create a native agent in the non-sending mode, then read it back."""
        fields = spec.fields()
        if fields.get("mode") != CREATE_MODE:
            raise ContractViolation(
                "conversation_create_must_be_non_sending",
                operation_id=CREATE,
                detail={
                    "requested_mode": fields.get("mode"),
                    "required_mode": CREATE_MODE,
                    "hint": "create off, read back, then update with approval",
                },
            )
        if not isinstance(fields.get("name"), str) or not fields["name"].strip():
            raise ContractViolation("conversation_name_required", operation_id=CREATE)
        if self._capture is None:
            raise ContractViolation(
                "conversation_transport_capture_required",
                operation_id=CREATE,
                detail={"hint": "pass transport=CapturingTransport(...) so the created id can be read"},
            )
        body = {key: fields[key] for key in CREATE_FIELDS if key in fields}
        readback = ReadbackSpec(
            operation_id=LIST,
            query=None,
            expect={"name": spec.name},
            description="created native agent by name",
            scan_nested=True,
        )
        result = self._adapter.call(
            operation_id=CREATE, tenant=self.tenant, body=body,
            idempotency_key=idempotency_key(logical_key),
            approval=approval, readback=readback, timeout_s=timeout_s,
        )
        agent = self._agent_from_last_response()
        if agent is not None and snapshot_sink is not None:
            snapshot_sink(_snapshot_of(agent))
        agent_id = str(agent["id"]) if agent and agent.get("id") else None
        return AgentChange(
            operation=result,
            agent_id=agent_id,
            mode=str(body.get("mode")),
            native_channels=tuple(body.get("channels") or ()),
            effective_prompt=effective_prompt(body),
            snapshot=_snapshot_of(agent) if agent else None,
            snapshot_digest=_digest(agent) if agent else None,
            readback_expect={"name": spec.name},
        )

    def update(self, agent_id: str, patch: Mapping[str, Any], *,
               logical_key: str,
               approval: ApprovalRef | str | Mapping[str, Any] | None = None,
               timeout_s: float | None = None) -> AgentChange:
        """Patch one agent. The CURRENT agent is read first and snapshotted."""
        if not isinstance(patch, Mapping) or not patch:
            raise ContractViolation("conversation_patch_invalid", operation_id=UPDATE)
        for name in PRIMARY_FIELDS:
            if name in patch:
                raise ContractViolation(
                    "primary_switch_requires_separate_authorization",
                    operation_id=UPDATE,
                    detail={
                        "field": name,
                        "hint": "primary-agent ownership is a separate approved"
                                " transition; this adapter never switches it",
                    },
                )
        unknown = sorted(str(key) for key in patch if key not in CREATE_FIELDS)
        if unknown:
            raise ContractViolation(
                "conversation_field_unsupported",
                operation_id=UPDATE,
                detail={"fields": unknown},
            )

        current = self.read(agent_id, timeout_s=timeout_s)
        if str(getattr(current.status, "value", current.status)) != "ok":
            return AgentChange(
                operation=current, agent_id=agent_id, mode="unknown",
                native_channels=(), effective_prompt={
                    "source": "unreadable", "text": None, "shadowed_fields": []},
                readback_expect={},
            )
        agent = self._agent_from_last_response()
        if agent is None:
            raise ContractViolation(
                "conversation_agent_unreadable",
                operation_id=GET,
                detail={"agent_id": agent_id},
            )
        snapshot = _snapshot_of(agent)
        digest = _digest(agent)

        body: dict[str, Any] = {}
        if "name" in patch:
            name = patch["name"]
            if not isinstance(name, str) or not name.strip():
                raise ContractViolation("conversation_name_invalid", operation_id=UPDATE)
            body["name"] = name
        if "channels" in patch:
            body["channels"] = list(native_channels_for(patch["channels"]))
        merged = dict(agent)
        merged.update({key: value for key, value in patch.items()})

        mode = patch.get("mode", agent.get("mode"))
        if mode not in NATIVE_MODES:
            raise ContractViolation(
                "conversation_mode_invalid", operation_id=UPDATE,
                detail={"mode": mode, "allowed": list(NATIVE_MODES)},
            )
        if "mode" in patch and mode != agent.get("mode"):
            if mode != CREATE_MODE and approval is None:
                raise ContractViolation(
                    "approval_required", operation_id=UPDATE,
                    detail={"reason": "mode change to " + str(mode)},
                )
            body["mode"] = mode

        prompt_intent = [name for name in STRUCTURED_PROMPT_FIELDS if name in patch]
        if "fullPrompt" in patch:
            full = patch["fullPrompt"]
            if full is not None and not isinstance(full, str):
                raise ContractViolation("conversation_prompt_invalid", operation_id=UPDATE)
            body["fullPrompt"] = full if full is not None else ""
        for name in prompt_intent:
            value = patch[name]
            if value is not None and not isinstance(value, str):
                raise ContractViolation("conversation_prompt_invalid", operation_id=UPDATE)
            body[name] = value

        before_prompt = effective_prompt(agent)
        after_prompt = effective_prompt(merged)
        if after_prompt["source"] == "fullPrompt" and prompt_intent:
            shadowed = [name for name in prompt_intent
                        if after_prompt.get("shadowed_fields")]
            if shadowed:
                raise ContractViolation(
                    "prompt_ineffective",
                    operation_id=UPDATE,
                    detail={
                        "reason": "fullPrompt overrides the structured fields",
                        "shadowed_fields": shadowed,
                        "effective_field": "fullPrompt",
                    },
                )
        if "fullPrompt" in patch and prompt_intent:
            raise ContractViolation(
                "prompt_ineffective",
                operation_id=UPDATE,
                detail={"reason": "one update cannot set a prompt and its shadowed fields"},
            )

        if not body:
            raise ContractViolation(
                "conversation_patch_no_effect",
                operation_id=UPDATE,
                detail={"reason": "no supported field changes"},
            )

        readback = ReadbackSpec(
            operation_id=GET,
            target_params=self._single_param(GET, agent_id),
            expect={"mode": merged.get("mode")},
            description="native agent mode after update",
            scan_nested=True,
        )
        result = self._adapter.call(
            operation_id=UPDATE, tenant=self.tenant,
            path_params=self._single_param(UPDATE, agent_id),
            body=body, idempotency_key=idempotency_key(logical_key),
            approval=approval, readback=readback, timeout_s=timeout_s,
        )
        changed = self._agent_from_last_response()
        if changed is not None:
            after_prompt = effective_prompt(changed)
        return AgentChange(
            operation=result,
            agent_id=agent_id,
            mode=str(merged.get("mode")),
            native_channels=tuple(merged.get("channels") or ()),
            effective_prompt=after_prompt,
            snapshot=snapshot,
            snapshot_digest=digest,
            readback_expect={"mode": merged.get("mode")},
        )

    # -- internals ---------------------------------------------------------

    def _default_operations(self) -> Any:
        return _default_operations()

    def _verify_operations(self) -> None:
        missing = [name for name in REQUIRED_OPERATIONS if self._row(name) is None]
        if missing:
            raise ContractViolation(
                "conversation_operations_missing",
                detail={
                    "missing": missing,
                    "checkpoint": OPERATIONS_CHECKPOINT,
                    "hint": "public/operations.py is WF00's; no row is guessed here",
                },
            )

    def _row(self, operation_id: str) -> Any:
        registry = self._operations
        getter = getattr(registry, "get", None)
        if callable(getter):
            row = getter(operation_id)
            if row is not None:
                return row
        try:
            return registry[operation_id]
        except (KeyError, TypeError):
            return None

    def _single_param(self, operation_id: str, value: str) -> dict[str, str]:
        if not isinstance(value, str) or not value.strip():
            raise ContractViolation("conversation_agent_id_required",
                                    operation_id=operation_id)
        row = self._row(operation_id)
        template = _row_attr(row, "path_template") or ""
        names = _PATH_PARAM.findall(str(template))
        if len(names) != 1:
            raise ContractViolation(
                "conversation_path_ambiguous",
                operation_id=operation_id,
                detail={"template": str(template),
                        "hint": "the frozen row must name exactly one path parameter"},
            )
        return {names[0]: value.strip()}

    def _agent_from_last_response(self) -> Optional[dict[str, Any]]:
        if self._capture is None:
            return None
        response = getattr(self._capture, "last_response", None)
        body = getattr(response, "body", None) if response is not None else None
        if not body:
            return None
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None
        return _agent_payload(parsed)


def _default_operations() -> Any:
    from .operations import OPERATIONS

    return OPERATIONS


def _snapshot_of(agent: Mapping[str, Any]) -> dict[str, Any]:
    """The response-behaviour fields needed to roll a change back. No secrets."""
    fields = ("id", "name", "mode", "channels", "fullPrompt", "personality",
              "goal", "instructions", "status", "updatedAt")
    snapshot = {name: agent[name] for name in fields if name in agent}
    return redact_mapping(snapshot)


def _digest(agent: Mapping[str, Any] | None) -> str | None:
    if agent is None:
        return None
    return fingerprint_bytes(canonical_json(_snapshot_of(agent)).encode("utf-8"))


__all__ = [
    "CHANNEL_MAP",
    "CREATE",
    "CREATE_FIELDS",
    "ConversationAiAdapter",
    "AgentChange",
    "AgentSpec",
    "GET",
    "LIST",
    "NATIVE_CHANNELS",
    "NATIVE_MODES",
    "OPERATIONS_CHECKPOINT",
    "REQUIRED_OPERATIONS",
    "UNSUPPORTED_CHANNELS",
    "UPDATE",
    "effective_prompt",
    "idempotency_key",
    "native_channel_for",
    "native_channels_for",
]
