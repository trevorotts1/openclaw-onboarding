"""Agent Studio Flow Agent adapter over the frozen public adapter.

Scope (Document 1 section 26): Flow Agents only.  Managed Agents and every other
product whose name contains "Studio" are audited separately and are NOT modelled
here.  The deprecated ``/agent-studio/public-api/agents`` operations are never
used; only the current operations appear in ``OPERATION_IDS``.

Where the facts come from
-------------------------
``29-ghl-convert-and-flow/references/agent-studio.md`` (enumerated from
``apps/agent-studio.json``, verified 2026-08-03) records the endpoints, methods,
scopes, required query parameters and every Version as UNVERIFIED for these
operations.  ``DOCUMENTED_ROW_REQUESTS`` below is that transcription.  It is
DOCUMENTATION and a typed request to WF00 (which owns ``public/operations.py``);
it is never a dispatch authority.  Dispatch reads the frozen registry row the
``PublicGhlAdapter`` was constructed with, so this module carries no endpoint,
no Version header and no auth of its own.

Lifecycle enforced here (section 26.2 / 26.3 / 26.4)
---------------------------------------------------
1. create produces a STAGING version.  Create is proven by a read-back of the
   agent plus a unique name match; a 2xx alone is never business success.
2. update patches one version-scoped document.  Unknown/unmodified properties
   are preserved; a removal is refused unless the caller explicitly allows it;
   deprecated top-level graph fields on the agent envelope are refused.
3. every write validates references, reachability, tool allowlisting and
   tenant-bound resource ids BEFORE transport, and refuses with a receipt.
4. promotion promotes exactly the reviewed version id and reads the promoted
   identity back.  The previously active version is captured first; a promotion
   whose previous active version cannot be read is refused, because a rollback
   that cannot name its target is not a rollback.
5. execution runs only the published production version.  Staging execution has
   no documented mechanism in the source reference, so it is refused rather
   than assumed (IG-AI-06).  A 2xx execution is ``ok`` only when the caller
   supplied an expected output that actually matched.
6. an ``executionId`` is bound to location, agent, version policy, contact and
   thread.  A stored session replayed for another location, agent, contact or
   thread is refused before transport (IG-AI-07).

No write is retried here and no ambiguous write is repeated on another rail.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from .adapter import ApprovalRef, PublicGhlAdapter
from .auth import TenantBinding
from .agent_studio_graph import (
    VERSION_SCOPED_FIELDS,
    StudioGraphSchema,
    StudioVersionSchema,
    canonical,
    merge_version,
    select_version,
    validate_graph,
    version_by_id,
    version_id_of,
)
from .capability import Capability, CapabilityGate
from .errors import ContractViolation, ReconciliationRequired
from .idempotency import IdempotencyKey, canonical_intent
from .readback import ReadbackSpec, ReadbackStatus
from .result import ADAPTER_VERSION, OperationResult, Status, canonical_json
from .transport import Transport, TransportResponse

# ---------------------------------------------------------------------------
# operation ids (logical key -> frozen operation id).  WF00 owns the rows.
# ---------------------------------------------------------------------------

OPERATION_IDS: dict[str, str] = {
    "agent.list": "agentStudio.agents.list",
    "agent.create": "agentStudio.agents.create",
    "agent.read": "agentStudio.agents.read",
    "agent.metadata.update": "agentStudio.agents.metadata.update",
    "version.update": "agentStudio.versions.update",
    "version.promote": "agentStudio.versions.promote",
    "agent.execute": "agentStudio.agents.execute",
}

LIST_OPERATION = OPERATION_IDS["agent.list"]
CREATE_OPERATION = OPERATION_IDS["agent.create"]
READ_OPERATION = OPERATION_IDS["agent.read"]
METADATA_OPERATION = OPERATION_IDS["agent.metadata.update"]
VERSION_UPDATE_OPERATION = OPERATION_IDS["version.update"]
PROMOTE_OPERATION = OPERATION_IDS["version.promote"]
EXECUTE_OPERATION = OPERATION_IDS["agent.execute"]

#: The documented operation facts, transcribed from the source reference named
#: in the module docstring.  A typed request to WF00 -- NOT a dispatch table.
DOCUMENTED_ROW_REQUESTS: dict[str, dict[str, Any]] = {
    "agent.list": {
        "method": "GET",
        "path_template": "/agent-studio/agent",
        "write": False,
        "approval_required": False,
        "tenant_binding": "query.locationId",
        "required_query": ("locationId", "limit", "offset"),
        "scopes_candidate": ("agent-studio.readonly",),
    },
    "agent.create": {
        "method": "POST",
        "path_template": "/agent-studio/agent",
        "write": True,
        "approval_required": True,
        "tenant_binding": "body.locationId",
        "scopes_candidate": ("agent-studio.write",),
    },
    "agent.read": {
        "method": "GET",
        "path_template": "/agent-studio/agent/{agentId}",
        "write": False,
        "approval_required": False,
        "tenant_binding": "query.locationId",
        "required_query": ("locationId",),
        "scopes_candidate": ("agent-studio.readonly",),
    },
    "agent.metadata.update": {
        "method": "PATCH",
        "path_template": "/agent-studio/agent/{agentId}",
        "write": True,
        "approval_required": True,
        "tenant_binding": "none",
        "scopes_candidate": ("agent-studio.write",),
    },
    "version.update": {
        "method": "PATCH",
        "path_template": "/agent-studio/agent/versions/{versionId}",
        "write": True,
        "approval_required": True,
        "tenant_binding": "none",
        "scopes_candidate": ("agent-studio.write",),
    },
    "version.promote": {
        "method": "POST",
        "path_template": "/agent-studio/agent/versions/{versionId}/publish",
        "write": True,
        "approval_required": True,
        "tenant_binding": "none",
        "scopes_candidate": ("agent-studio.write",),
    },
    "agent.execute": {
        "method": "POST",
        "path_template": "/agent-studio/agent/{agentId}/execute",
        "write": True,
        "approval_required": True,
        "tenant_binding": "body.locationId",
        "scopes_candidate": ("agent-studio.write",),
    },
}

#: The Version literal is DELIBERATELY absent: the source records it as
#: UNVERIFIED for every studio operation, and this package may hold no global
#: version default (test_public_adapter_contract MAJOR 6c).  WF00 reads the
#: operation page and freezes the per-operation literal.  This blocker travels
#: on every studio row until then.
VERSION_BLOCKER = "B-STUDIO-VERSION-UNVERIFIED"
DOC_URL = "https://marketplace.gohighlevel.com/docs/ghl/agent-studio/"

#: Only these version policies may execute (IG-AI-06).
EXECUTION_VERSION_POLICIES: tuple[str, ...] = ("production",)

#: An execution request is CONTENT.  It can never assert an approval, a scope,
#: a role or a tool allowlist: those are administrative facts this process owns
#: (IG-AI-08).  A payload that claims one is refused, not silently forwarded.
PERMISSION_CLAIM_KEYS: tuple[str, ...] = (
    "admin_override",
    "adminoverride",
    "approval",
    "approval_ref",
    "approved",
    "permissions",
    "role",
    "scopes",
    "tool_allowlist",
    "toolallowlist",
)

_LIST_LIMIT = 100

__all__ = [
    "AgentStudioAdapter",
    "DOCUMENTED_ROW_REQUESTS",
    "DOC_URL",
    "EXECUTION_VERSION_POLICIES",
    "ExecutionSession",
    "OPERATION_IDS",
    "PromotionRecord",
    "RecordingTransport",
    "StudioGap",
    "StudioOperationRowMissing",
    "VERSION_BLOCKER",
    "session_mismatch",
]


class StudioGap(ContractViolation):
    """A Studio operation has no usable frozen row.  Named, never invented."""

    rule = "studio_operation_gap"


class StudioOperationRowMissing(StudioGap):
    """The registry does not carry the row this operation needs."""

    rule = "studio_operation_row_missing"


@dataclass(frozen=True)
class ExecutionSession:
    """One execution identity, bound to everything it may not cross."""

    execution_id: str
    location_id: str
    agent_id: str
    version_id: str | None
    version_policy: str
    contact_id: str | None
    thread_id: str | None

    def as_mapping(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "location_id": self.location_id,
            "agent_id": self.agent_id,
            "version_id": self.version_id,
            "version_policy": self.version_policy,
            "contact_id": self.contact_id,
            "thread_id": self.thread_id,
        }


@dataclass(frozen=True)
class PromotionRecord:
    location_id: str
    agent_id: str
    previous_version_id: str
    promoted_version_id: str
    receipt_id: str
    promoted_at: str


@dataclass(frozen=True)
class _PendingStudio:
    kind: str
    tenant: TenantBinding
    agent_id: str | None
    version_id: str | None
    attempt: int


class AgentStudioAdapter:
    """Flow Agent lifecycle over ``PublicGhlAdapter``; disabled by default.

    Every call goes through ``PublicGhlAdapter.call`` so the frozen capability
    gate, tenant binding, approval, idempotency and receipt rules are the
    frozen ones.  Rows are read from the registry the public adapter was
    constructed with -- one authority, no second dispatch table.
    """

    def __init__(
        self,
        *,
        public: PublicGhlAdapter,
        transport: Transport | None = None,
        graph_schema: StudioGraphSchema | None = None,
        version_schema: StudioVersionSchema | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(public, PublicGhlAdapter):
            raise ContractViolation("public_adapter_required")
        base: Transport | None = transport
        if base is None:
            base = getattr(public, "_transport", None)  # ponytail: see module note
        if base is None or not callable(getattr(base, "request", None)):
            raise ContractViolation("studio_transport_unavailable")
        if isinstance(base, RecordingTransport):
            recorder = base
        else:
            recorder = RecordingTransport(base)
            try:
                public._transport = recorder  # ponytail: see module note
            except AttributeError:  # pragma: no cover - defensive
                raise ContractViolation("studio_transport_unbindable") from None
        self._public = public
        self._transport = recorder
        self._graph_schema = graph_schema or StudioGraphSchema()
        self._version_schema = version_schema or StudioVersionSchema()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._pending: dict[str, _PendingStudio] = {}
        self._unreconciled: OperationResult | None = None
        self._sessions: dict[str, ExecutionSession] = {}
        self._promotions: dict[tuple[str, str], PromotionRecord] = {}

    # ------------------------------------------------------------------
    # operation map and capability
    # ------------------------------------------------------------------

    def _rows(self) -> Mapping[str, Any]:
        rows = getattr(self._public, "_operations", None)
        if not isinstance(rows, Mapping):
            raise StudioGap(
                "studio_registry_unavailable",
                detail={"owner": "WF00", "path": "public/operations.py"},
            )
        return rows

    def operation_id(self, key: str) -> str:
        logical = str(key)
        operation_id = OPERATION_IDS.get(logical)
        if operation_id is None:
            raise StudioGap(
                "studio_operation_not_modelled",
                operation_id=logical,
                detail={"modelled": sorted(OPERATION_IDS)},
            )
        if operation_id not in self._rows():
            raise StudioOperationRowMissing(
                "studio_operation_row_missing",
                operation_id=operation_id,
                detail={
                    "logical": logical,
                    "owner": "WF00",
                    "action": "add the typed row request from "
                    "DOCUMENTED_ROW_REQUESTS to public/operations.py",
                },
            )
        return operation_id

    def _row(self, key: str) -> Any:
        return self._rows()[self.operation_id(key)]

    def capability(
        self, key: str, *, tenant: TenantBinding | str | None = None
    ) -> Capability:
        operation_id = self.operation_id(key)
        location_id = _tenant_location(tenant)
        if location_id is None:
            # Unbound is deny: never borrow whichever gate loaded last.
            return CapabilityGate().get(operation_id)
        return self._public.capability(operation_id, tenant=location_id)

    def _enabled(self, operation_id: str, tenant: TenantBinding | str | None) -> bool:
        location_id = _tenant_location(tenant)
        if location_id is None:
            return False
        return bool(self._public.capability(operation_id, tenant=location_id).enabled)

    # ------------------------------------------------------------------
    # reads
    # ------------------------------------------------------------------

    def read_agent(
        self, *, tenant: TenantBinding, agent_id: str, attempt: int = 1
    ) -> OperationResult:
        return self._public.call(
            operation_id=self.operation_id("agent.read"),
            tenant=tenant,
            path_params={"agentId": _require_id(agent_id, "agent_id")},
            query={"locationId": tenant.location_id},
            attempt=attempt,
        )

    def read_agent_document(
        self, *, tenant: TenantBinding, agent_id: str, attempt: int = 1
    ) -> tuple[OperationResult, Any]:
        """Read the agent; the parsed payload stays in memory, never in evidence."""

        mark = len(self._transport)
        result = self.read_agent(tenant=tenant, agent_id=agent_id, attempt=attempt)
        if result.status is not Status.ok:
            return result, None
        return result, self._response_body(mark)

    def list_agents(
        self, *, tenant: TenantBinding, attempt: int = 1
    ) -> tuple[OperationResult, Any]:
        mark = len(self._transport)
        result = self._public.call(
            operation_id=self.operation_id("agent.list"),
            tenant=tenant,
            query={
                "locationId": tenant.location_id,
                "limit": _LIST_LIMIT,
                "offset": 0,
            },
            attempt=attempt,
        )
        if result.status is not Status.ok:
            return result, None
        return result, self._response_body(mark)

    # ------------------------------------------------------------------
    # create (always staging)
    # ------------------------------------------------------------------

    def create_agent(
        self,
        *,
        tenant: TenantBinding,
        name: str,
        version: Mapping[str, Any],
        approval: ApprovalRef | Mapping[str, Any] | str,
        metadata: Mapping[str, Any] | None = None,
        allowed_tools: Sequence[str] | None = None,
        attempt: int = 1,
    ) -> OperationResult:
        """Create a Flow Agent whose created version is STAGING."""

        self._guard()
        key = "agent.create"
        operation_id = self.operation_id(key)
        if not self._enabled(operation_id, tenant):
            return self._disabled_result(key, tenant=tenant, attempt=attempt)
        clean_name = _require_id(name, "name")
        if not isinstance(version, Mapping):
            validation = validate_graph(
                version,
                tenant_id=tenant.location_id,
                schema=self._graph_schema,
                allowed_tools=allowed_tools,
            )
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.validation_error,
                rule="studio_graph_invalid",
                attempt=attempt,
                body=None,
                detail={"graph": validation.as_evidence()},
            )

        extra = dict(metadata or {})
        deprecated = sorted(f for f in extra if f in VERSION_SCOPED_FIELDS)
        if deprecated:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.validation_error,
                rule="deprecated_top_level_graph_field",
                attempt=attempt,
                body=extra,
                detail={
                    "fields": deprecated,
                    "hint": "graph fields belong to the version-scoped document",
                },
            )
        validation = validate_graph(
            version,
            tenant_id=tenant.location_id,
            schema=self._graph_schema,
            allowed_tools=allowed_tools,
        )
        if not validation.valid:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.validation_error,
                rule="studio_graph_invalid",
                attempt=attempt,
                body=version,
                detail={"graph": validation.as_evidence()},
            )

        body: dict[str, Any] = {"name": clean_name}
        body.update(extra)
        body["version"] = dict(version)

        readback = ReadbackSpec(
            operation_id=LIST_OPERATION,
            query={
                "locationId": tenant.location_id,
                "limit": _LIST_LIMIT,
                "offset": 0,
            },
            expect={"locationId": tenant.location_id},
            scan_nested=True,
            description="create reconciliation: the location's agent list",
        )
        mark = len(self._transport)
        result = self._write(
            operation_id,
            tenant=tenant,
            path_params={},
            body=body,
            approval=approval,
            readback=readback,
            attempt=attempt,
            kind=key,
        )
        if result.status is not Status.ok:
            if not (
                result.status is Status.unknown_outcome
                and result.readback is not None
                and result.readback.result is ReadbackStatus.mismatch
            ):
                return result
            # The frozen matcher is shallow; the documented list envelope nests
            # its rows.  The shape-tolerant name search below decides, never the
            # shallow verdict, and never in the create's favour on its own.
            self._settle_adapter_pending(result)
            self._clear(result.receipt_id)
            result = replace(result, status=Status.ok, error=None)

        created = self._response_body(mark)
        agent_id = _first(created, ("agentId", "id", "agent_id"))
        listed, payload = self.list_agents(tenant=tenant, attempt=attempt)
        match, reason = _named_agent(payload, clean_name)
        if listed.status is not Status.ok or reason == "unreadable":
            return self._mark_unknown(
                result,
                kind=key,
                tenant=tenant,
                agent_id=agent_id,
                rule="create_readback_unreadable",
                version_id=None,
                detail={"read_status": listed.status.value},
                attempt=attempt,
            )
        if reason == "ambiguous":
            return self._mark_unknown(
                result,
                kind=key,
                tenant=tenant,
                agent_id=agent_id,
                rule="create_readback_ambiguous",
                version_id=None,
                detail={"name_matches": "more-than-one"},
                attempt=attempt,
            )
        if match is None:
            return self._mark_unknown(
                result,
                kind=key,
                tenant=tenant,
                agent_id=agent_id,
                rule="create_readback_missing",
                version_id=None,
                detail={"readback": LIST_OPERATION},
                attempt=attempt,
            )

        matched_id = _first(match, ("agentId", "id", "agent_id")) or agent_id
        staging, staging_reason = select_version(
            match,
            wanted=self._version_schema.staging_values,
            schema=self._version_schema,
        )
        staging_id = version_id_of(staging, self._version_schema) if staging else None
        if staging_id is None:
            # The agent exists but its staging version is unreadable.  That is
            # not a completed create; say so instead of asserting "staging".
            return self._mark_unknown(
                result,
                kind=key,
                tenant=tenant,
                agent_id=matched_id,
                rule="create_readback_no_staging_version",
                version_id=None,
                detail={"version_readback": staging_reason},
                attempt=attempt,
            )
        return self._enrich(
            result,
            {
                "operation": key,
                "agent_id": matched_id,
                "staging_version_id": staging_id,
                "status": "staging",
                "readback": LIST_OPERATION,
                "readback_matched_by": "name",
            },
        )

    # ------------------------------------------------------------------
    # update one version-scoped document
    # ------------------------------------------------------------------

    def update_version(
        self,
        *,
        tenant: TenantBinding,
        agent_id: str,
        version_id: str,
        intent: Mapping[str, Any],
        approval: ApprovalRef | Mapping[str, Any] | str,
        expected_version: Any = None,
        allow_deletions: bool = False,
        allowed_tools: Sequence[str] | None = None,
        attempt: int = 1,
    ) -> OperationResult:
        """Patch exactly one version, preserving everything not in the intent."""

        self._guard()
        key = "version.update"
        operation_id = self.operation_id(key)
        if not self._enabled(operation_id, tenant):
            return self._disabled_result(key, tenant=tenant, attempt=attempt)
        agent = _require_id(agent_id, "agent_id")
        version_key = _require_id(version_id, "version_id")
        if not isinstance(intent, Mapping):
            raise ContractViolation(
                "studio_intent_required", operation_id=operation_id
            )

        read_result, payload = self.read_agent_document(
            tenant=tenant, agent_id=agent, attempt=attempt
        )
        if read_result.status is not Status.ok:
            return self._refusal(
                key,
                tenant=tenant,
                status=read_result.status,
                rule="version_read_before_update_failed",
                attempt=attempt,
                path_params={"versionId": version_key},
                detail={
                    "read_status": read_result.status.value,
                    "receipt_id": read_result.receipt_id,
                },
            )
        current = version_by_id(payload, version_key, self._version_schema)
        if current is None:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.not_found,
                rule="version_not_present_in_readback",
                attempt=attempt,
                path_params={"versionId": version_key},
                detail={"agent_id": agent},
            )
        if expected_version is not None and canonical(dict(current)) != canonical(
            expected_version
        ):
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.conflict,
                rule="stale_version",
                attempt=attempt,
                path_params={"versionId": version_key},
                detail={"expected_present": True},
            )

        merged, removed = merge_version(
            current, intent, allow_deletions=allow_deletions
        )
        if removed and not allow_deletions:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.denied,
                rule="deletion_requires_approval",
                attempt=attempt,
                path_params={"versionId": version_key},
                body=merged,
                detail={"removed_paths": removed},
            )

        validation = validate_graph(
            merged,
            tenant_id=tenant.location_id,
            schema=self._graph_schema,
            allowed_tools=allowed_tools,
        )
        if not validation.valid:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.validation_error,
                rule="studio_graph_invalid",
                attempt=attempt,
                path_params={"versionId": version_key},
                body=merged,
                detail={"graph": validation.as_evidence()},
            )

        readback = ReadbackSpec(
            operation_id=READ_OPERATION,
            target_params={"agentId": agent},
            query={"locationId": tenant.location_id},
            expect={"locationId": tenant.location_id},
            scan_nested=True,
            description="version update: re-read the agent after the patch",
        )
        result = self._write(
            operation_id,
            tenant=tenant,
            path_params={"versionId": version_key},
            body=merged,
            approval=approval,
            readback=readback,
            attempt=attempt,
            kind=key,
        )
        if result.status is not Status.ok:
            return result
        return self._verify_version_landed(
            result,
            tenant=tenant,
            agent_id=agent,
            version_id=version_key,
            merged=merged,
            attempt=attempt,
        )

    # ------------------------------------------------------------------
    # promotion and rollback
    # ------------------------------------------------------------------

    def promote_version(
        self,
        *,
        tenant: TenantBinding,
        agent_id: str,
        version_id: str,
        approval: ApprovalRef | Mapping[str, Any] | str,
        expected_active_version: str | None = None,
        attempt: int = 1,
    ) -> OperationResult:
        """Promote exactly ``version_id`` and read the promoted identity back."""

        self._guard()
        key = "version.promote"
        operation_id = self.operation_id(key)
        if not self._enabled(operation_id, tenant):
            return self._disabled_result(key, tenant=tenant, attempt=attempt)
        agent = _require_id(agent_id, "agent_id")
        version_key = _require_id(version_id, "version_id")

        read_result, payload = self.read_agent_document(
            tenant=tenant, agent_id=agent, attempt=attempt
        )
        if read_result.status is not Status.ok:
            return self._refusal(
                key,
                tenant=tenant,
                status=read_result.status,
                rule="version_read_before_promotion_failed",
                attempt=attempt,
                path_params={"versionId": version_key},
                detail={
                    "read_status": read_result.status.value,
                    "receipt_id": read_result.receipt_id,
                },
            )
        if version_by_id(payload, version_key, self._version_schema) is None:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.not_found,
                rule="promotion_target_not_present",
                attempt=attempt,
                path_params={"versionId": version_key},
                detail={"agent_id": agent},
            )
        previous, previous_reason = select_version(
            payload,
            wanted=self._version_schema.production_values,
            schema=self._version_schema,
        )
        previous_id = version_id_of(previous, self._version_schema) if previous else None
        if previous_id is None:
            # No readable active version means a rollback could not name its
            # target.  Refuse instead of promoting into a blind state.
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.denied,
                rule="previous_active_version_unknown",
                attempt=attempt,
                path_params={"versionId": version_key},
                detail={"version_readback": previous_reason},
            )
        if previous_id == version_key:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.conflict,
                rule="version_already_production",
                attempt=attempt,
                path_params={"versionId": version_key},
                detail={"agent_id": agent},
            )
        if (
            expected_active_version is not None
            and str(expected_active_version) != previous_id
        ):
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.conflict,
                rule="stale_active_version",
                attempt=attempt,
                path_params={"versionId": version_key},
                detail={"expected_present": True},
            )

        readback = ReadbackSpec(
            operation_id=READ_OPERATION,
            target_params={"agentId": agent},
            query={"locationId": tenant.location_id},
            expect={"locationId": tenant.location_id},
            scan_nested=True,
            description="promotion: re-read the agent and its production version",
        )
        result = self._write(
            operation_id,
            tenant=tenant,
            path_params={"versionId": version_key},
            body=None,
            approval=approval,
            readback=readback,
            attempt=attempt,
            kind=key,
        )
        if result.status is not Status.ok:
            return result

        verify_result, verified = self.read_agent_document(
            tenant=tenant, agent_id=agent, attempt=attempt
        )
        if verify_result.status is not Status.ok:
            return self._mark_unknown(
                result,
                kind=key,
                tenant=tenant,
                agent_id=agent,
                version_id=version_key,
                rule="promotion_readback_failed",
                detail={"read_status": verify_result.status.value},
                attempt=attempt,
            )
        active, active_reason = select_version(
            verified,
            wanted=self._version_schema.production_values,
            schema=self._version_schema,
        )
        active_id = version_id_of(active, self._version_schema) if active else None
        if active_id != version_key:
            return self._mark_unknown(
                result,
                kind=key,
                tenant=tenant,
                agent_id=agent,
                version_id=version_key,
                rule="promoted_identity_mismatch",
                detail={
                    "version_readback": active_reason,
                    "identity_matches": False,
                },
                attempt=attempt,
            )

        self._promotions[(tenant.location_id, agent)] = PromotionRecord(
            location_id=tenant.location_id,
            agent_id=agent,
            previous_version_id=previous_id,
            promoted_version_id=version_key,
            receipt_id=result.receipt_id,
            promoted_at=self._clock().isoformat(),
        )
        return self._enrich(
            result,
            {
                "operation": key,
                "agent_id": agent,
                "promoted_version_id": version_key,
                "previous_active_version_id": previous_id,
                "promoted_identity_verified": True,
            },
        )

    def rollback(
        self,
        *,
        tenant: TenantBinding,
        agent_id: str,
        approval: ApprovalRef | Mapping[str, Any] | str,
        to_version_id: str | None = None,
        attempt: int = 1,
    ) -> OperationResult:
        """Roll back by promoting the recorded previous version.

        Never a status mutation and never a deletion.  Without a recorded
        previous version there is nothing verified to roll back to, so the
        request is refused rather than guessed.
        """

        self._guard()
        agent = _require_id(agent_id, "agent_id")
        record = self._promotions.get((tenant.location_id, agent))
        if record is None:
            return self._refusal(
                "version.promote",
                tenant=tenant,
                status=Status.denied,
                rule="rollback_without_recorded_previous_version",
                attempt=attempt,
                path_params={"versionId": to_version_id or "unknown"},
                detail={"agent_id": agent},
            )
        target = str(to_version_id or record.previous_version_id)
        if target != record.previous_version_id:
            return self._refusal(
                "version.promote",
                tenant=tenant,
                status=Status.denied,
                rule="rollback_target_not_recorded",
                attempt=attempt,
                path_params={"versionId": target},
                detail={"agent_id": agent},
            )
        return self.promote_version(
            tenant=tenant,
            agent_id=agent,
            version_id=target,
            approval=approval,
            attempt=attempt,
        )

    # ------------------------------------------------------------------
    # execution
    # ------------------------------------------------------------------

    def execute(
        self,
        *,
        tenant: TenantBinding,
        agent_id: str,
        payload: Mapping[str, Any],
        approval: ApprovalRef | Mapping[str, Any] | str,
        output_expect: Mapping[str, Any] | None = None,
        contact_id: str | None = None,
        thread_id: str | None = None,
        session: ExecutionSession | None = None,
        version_policy: str = "production",
        attempt: int = 1,
    ) -> OperationResult:
        """Execute the published production version only.

        ``ok`` requires an ``output_expect`` that actually matched the response.
        Downstream tool effects are reported as ``not_verified``: a 2xx is not
        proof that an intended action happened.
        """

        self._guard()
        key = "agent.execute"
        operation_id = self.operation_id(key)
        if not self._enabled(operation_id, tenant):
            return self._disabled_result(key, tenant=tenant, attempt=attempt)
        agent = _require_id(agent_id, "agent_id")
        policy = str(version_policy)
        if policy not in EXECUTION_VERSION_POLICIES:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.denied,
                rule="execution_version_policy_unsupported",
                attempt=attempt,
                path_params={"agentId": agent},
                body=payload,
                detail={
                    "policy": policy,
                    "supported": list(EXECUTION_VERSION_POLICIES),
                    "hint": "no unpublished/staging execution mechanism is "
                    "documented for Flow Agents",
                },
            )
        if not isinstance(payload, Mapping):
            raise ContractViolation(
                "studio_execution_payload_required", operation_id=operation_id
            )
        claimed = sorted(
            str(key)
            for key in payload
            if str(key).strip().lower() in PERMISSION_CLAIM_KEYS
        )
        if claimed:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.denied,
                rule="source_content_cannot_assert_permissions",
                attempt=attempt,
                path_params={"agentId": agent},
                body=payload,
                detail={
                    "fields": claimed,
                    "hint": "an execution request is content; grants, scopes, "
                    "roles and tool allowlists are administrative facts",
                },
            )

        read_result, document = self.read_agent_document(
            tenant=tenant, agent_id=agent, attempt=attempt
        )
        if read_result.status is not Status.ok:
            return self._refusal(
                key,
                tenant=tenant,
                status=read_result.status,
                rule="execution_precondition_read_failed",
                attempt=attempt,
                path_params={"agentId": agent},
                body=payload,
                detail={
                    "read_status": read_result.status.value,
                    "receipt_id": read_result.receipt_id,
                },
            )
        active, active_reason = select_version(
            document,
            wanted=self._version_schema.production_values,
            schema=self._version_schema,
        )
        version_id = version_id_of(active, self._version_schema) if active else None
        if version_id is None:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.denied,
                rule="execution_requires_published_version",
                attempt=attempt,
                path_params={"agentId": agent},
                body=payload,
                detail={"version_readback": active_reason},
            )

        if session is not None:
            mismatch = session_mismatch(
                session,
                tenant=tenant,
                agent_id=agent,
                version_policy=policy,
                version_id=version_id,
                contact_id=contact_id,
                thread_id=thread_id,
            )
            if mismatch is not None:
                return self._refusal(
                    key,
                    tenant=tenant,
                    status=Status.denied,
                    rule="execution_session_cross_bound",
                    attempt=attempt,
                    path_params={"agentId": agent},
                    body=payload,
                    detail={"crossed": mismatch, "session": session.as_mapping()},
                )

        readback = ReadbackSpec(
            operation_id=READ_OPERATION,
            target_params={"agentId": agent},
            query={"locationId": tenant.location_id},
            expect={"locationId": tenant.location_id},
            scan_nested=True,
            description="execution: the agent must still read back for this tenant",
        )
        mark = len(self._transport)
        result = self._write(
            operation_id,
            tenant=tenant,
            path_params={"agentId": agent},
            body=dict(payload),
            approval=approval,
            readback=readback,
            attempt=attempt,
            kind=key,
        )
        if result.status is not Status.ok:
            return result

        body = self._response_body(mark)
        execution_id = _first(body, self._version_schema.execution_id_keys)
        if execution_id is None:
            return self._mark_unknown(
                result,
                kind=key,
                tenant=tenant,
                agent_id=agent,
                version_id=version_id,
                rule="execution_id_absent",
                detail={"response_keys": _mapping_keys(body)},
                attempt=attempt,
            )
        if not output_expect:
            return self._mark_unknown(
                result,
                kind=key,
                tenant=tenant,
                agent_id=agent,
                version_id=version_id,
                rule="execution_output_not_validated",
                detail={"hint": "supply output_expect to prove the intended output"},
                attempt=attempt,
            )
        if not _subset_matches(output_expect, body):
            return self._mark_unknown(
                result,
                kind=key,
                tenant=tenant,
                agent_id=agent,
                version_id=version_id,
                rule="execution_output_mismatch",
                detail={"expected_keys": sorted(str(k) for k in output_expect)},
                attempt=attempt,
            )

        bound = ExecutionSession(
            execution_id=str(execution_id),
            location_id=tenant.location_id,
            agent_id=agent,
            version_id=version_id,
            version_policy=policy,
            contact_id=contact_id,
            thread_id=thread_id,
        )
        self._sessions[bound.execution_id] = bound
        return self._enrich(
            result,
            {
                "operation": key,
                "agent_id": agent,
                "version_id": version_id,
                "version_policy": policy,
                "execution_id": bound.execution_id,
                "session": bound.as_mapping(),
                "output_validated": True,
                "tool_effects": "not_verified",
            },
        )

    def session(self, execution_id: str) -> ExecutionSession | None:
        return self._sessions.get(str(execution_id))

    def reconcile(self, prior: OperationResult) -> OperationResult:
        """Delegate reconciliation to the frozen adapter, then clear the row."""

        if not isinstance(prior, OperationResult):
            raise ContractViolation("reconcile_prior_invalid")
        result = self._public.reconcile(prior)
        self._clear(prior.receipt_id)
        return result

    def pending_count(self) -> int:
        return len(self._pending)

    # ------------------------------------------------------------------
    # capability refusal and receipts
    # ------------------------------------------------------------------

    def _disabled_result(
        self,
        key: str,
        *,
        tenant: TenantBinding,
        attempt: int,
        path_params: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> OperationResult:
        operation_id = self.operation_id(key)
        capability = self._public.capability(operation_id, tenant=tenant.location_id)
        block = capability.activation_blocked
        return self._refusal(
            key,
            tenant=tenant,
            status=Status.denied,
            rule="capability_disabled",
            attempt=attempt,
            path_params=path_params,
            body=body,
            detail={
                "operation_id": operation_id,
                "reason": (
                    block.reason
                    if block is not None
                    else "capability record absent; the gate is default-deny"
                ),
                "owner": (
                    block.owner if block is not None else "operator (account authority)"
                ),
                "unblock": (
                    block.unblock
                    if block is not None
                    else "recorded capability evidence for (operation_id, tenant)"
                ),
                "capability_enabled": False,
            },
        )

    def _refusal(
        self,
        key: str,
        *,
        tenant: TenantBinding,
        status: Status,
        rule: str,
        attempt: int,
        path_params: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> OperationResult:
        """A pre-transport refusal with a real receipt (freeze 3.2 rule 7)."""

        operation_id = self.operation_id(key)
        row = self._row(key)
        resolved_path = _format_path(
            str(_row_attr(row, "path_template", "")), dict(path_params or {})
        )
        query = (
            {"locationId": tenant.location_id}
            if _row_attr(row, "tenant_binding") == "query.locationId"
            else {}
        )
        body_map = dict(body or {})
        fingerprint = canonical_intent(
            operation_id=operation_id,
            method=str(_row_attr(row, "method", "")),
            resolved_path=resolved_path,
            query=query,
            body=body_map,
            tenant=tenant.location_id,
            version=_row_attr(row, "version"),
        )
        receipt_id = "gxo_res_" + secrets.token_hex(6)
        timestamp = self._clock().isoformat()
        auth = getattr(self._public, "_auth", None)  # ponytail: see module note
        evidence: dict[str, Any] = {
            "operation_id": operation_id,
            "request_fingerprint": fingerprint,
            "http_status": None,
            "response_fingerprint": None,
            "tenant": tenant.location_id,
            "attempt": attempt,
            "readback": None,
            "receipt_id": receipt_id,
            "version_header": _row_attr(row, "version"),
            "timeout_s": getattr(self._public, "_default_timeout_s", None),
            "adapter_version": ADAPTER_VERSION,
            "transport": "http",
            "auth_kind": getattr(getattr(auth, "kind", None), "value", "unavailable"),
            "auth_source": getattr(auth, "source", "unavailable"),
            "doc_url": _row_attr(row, "doc_url"),
            "doc_fetch_date": _row_attr(row, "doc_fetch_date"),
            "request_bytes": (
                len(canonical_json(body_map).encode("utf-8")) if body_map else 0
            ),
            "started_at": timestamp,
            "finished_at": timestamp,
            "refused_before_transport": True,
            "route": "public_direct",
            "agent_studio": {
                "operation": key,
                "agent_id": dict(path_params or {}).get("agentId"),
                "version_id": dict(path_params or {}).get("versionId"),
                "reconcilable": False,
            },
        }
        error: dict[str, Any] = {"rule": rule}
        error.update(dict(detail or {}))
        return OperationResult(
            status=status,
            operation_id=operation_id,
            receipt_id=receipt_id,
            request_fingerprint=fingerprint,
            http_status=None,
            response_fingerprint=None,
            tenant=tenant.location_id,
            attempt=attempt,
            version_header=_row_attr(row, "version"),
            readback=None,
            adapter_version=ADAPTER_VERSION,
            transport="http",
            doc_url=_row_attr(row, "doc_url"),
            evidence=evidence,
            error=error,
        )

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _guard(self) -> None:
        if self._unreconciled is not None:
            raise ReconciliationRequired(
                operation_id=self._unreconciled.operation_id,
                detail={"receipt_id": self._unreconciled.receipt_id},
            )

    def _write(
        self,
        operation_id: str,
        *,
        tenant: TenantBinding,
        path_params: Mapping[str, str] | None,
        body: Mapping[str, Any] | None,
        approval: ApprovalRef | Mapping[str, Any] | str,
        readback: ReadbackSpec,
        attempt: int,
        kind: str,
    ) -> OperationResult:
        params = dict(path_params or {})
        result = self._public.call(
            operation_id=operation_id,
            tenant=tenant,
            path_params=params,
            body=dict(body) if body is not None else None,
            idempotency_key=IdempotencyKey.issue(operation_id).value,
            approval=approval,
            readback=readback,
            attempt=attempt,
        )
        if result.status is Status.unknown_outcome:
            self._remember_unknown(
                result,
                kind=kind,
                tenant=tenant,
                agent_id=params.get("agentId"),
                version_id=params.get("versionId"),
                attempt=attempt,
            )
        return result

    def _verify_version_landed(
        self,
        result: OperationResult,
        *,
        tenant: TenantBinding,
        agent_id: str,
        version_id: str,
        merged: Mapping[str, Any],
        attempt: int,
    ) -> OperationResult:
        verify_result, payload = self.read_agent_document(
            tenant=tenant, agent_id=agent_id, attempt=attempt
        )
        if verify_result.status is not Status.ok:
            return self._mark_unknown(
                result,
                kind="version.update",
                tenant=tenant,
                agent_id=agent_id,
                version_id=version_id,
                rule="version_readback_failed",
                detail={"read_status": verify_result.status.value},
                attempt=attempt,
            )
        landed = version_by_id(payload, version_id, self._version_schema)
        if landed is None:
            return self._mark_unknown(
                result,
                kind="version.update",
                tenant=tenant,
                agent_id=agent_id,
                version_id=version_id,
                rule="version_readback_missing",
                detail={"readback": READ_OPERATION},
                attempt=attempt,
            )
        mismatched = [
            str(key)
            for key, value in merged.items()
            if canonical(landed.get(key)) != canonical(value)
        ]
        if mismatched:
            return self._mark_unknown(
                result,
                kind="version.update",
                tenant=tenant,
                agent_id=agent_id,
                version_id=version_id,
                rule="version_readback_mismatch",
                detail={"fields": sorted(mismatched)},
                attempt=attempt,
            )
        return self._enrich(
            result,
            {
                "operation": "version.update",
                "agent_id": agent_id,
                "version_id": version_id,
                "readback": READ_OPERATION,
                "readback_matched": True,
            },
        )

    def _mark_unknown(
        self,
        result: OperationResult,
        *,
        kind: str,
        tenant: TenantBinding,
        agent_id: str | None,
        version_id: str | None,
        rule: str,
        detail: Mapping[str, Any] | None = None,
        attempt: int = 1,
    ) -> OperationResult:
        evidence = dict(result.evidence)
        studio = dict(evidence.get("agent_studio") or {})
        studio.update(
            {
                "operation": kind,
                "agent_id": agent_id,
                "version_id": version_id,
                "reconcilable": True,
                "reconcile_rule": rule,
            }
        )
        if detail:
            studio["detail"] = dict(detail)
        evidence["agent_studio"] = studio
        error: dict[str, Any] = {"rule": rule}
        error.update(dict(detail or {}))
        unknown = replace(
            result, status=Status.unknown_outcome, error=error, evidence=evidence
        )
        self._remember_unknown(
            unknown,
            kind=kind,
            tenant=tenant,
            agent_id=agent_id,
            version_id=version_id,
            attempt=attempt,
        )
        return unknown

    def _remember_unknown(
        self,
        result: OperationResult,
        *,
        kind: str,
        tenant: TenantBinding,
        agent_id: str | None,
        version_id: str | None,
        attempt: int,
    ) -> None:
        self._pending[result.receipt_id] = _PendingStudio(
            kind=kind,
            tenant=tenant,
            agent_id=agent_id,
            version_id=version_id,
            attempt=attempt or result.attempt,
        )
        self._unreconciled = result

    def _clear(self, receipt_id: str) -> None:
        self._pending.pop(receipt_id, None)
        self._unreconciled = None

    def _settle_adapter_pending(self, result: OperationResult) -> OperationResult:
        """Free the frozen adapter's pending row for a write this module settles.

        ``reconcile()`` re-reads through the same read-back row; it never
        re-issues the write.  Its verdict is the caller's to interpret, so only
        the side effect (the pending row) is wanted here.
        """

        return self._public.reconcile(result)

    def _response_body(self, mark: int) -> Any:
        records = self._transport.records
        if mark < 0 or mark >= len(records):
            return None
        record = records[mark]
        if record.error_kind != "none" or record.status is None:
            return None
        if not (200 <= record.status < 300) or not record.body:
            return None
        try:
            return json.loads(record.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def _enrich(
        self, result: OperationResult, studio: Mapping[str, Any]
    ) -> OperationResult:
        evidence = dict(result.evidence)
        merged = dict(evidence.get("agent_studio") or {})
        merged.update(dict(studio))
        evidence["agent_studio"] = merged
        evidence["finished_at"] = self._clock().isoformat()
        return replace(result, evidence=evidence)


# ---------------------------------------------------------------------------
# recording transport (bodies never reach the envelope)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransportRecord:
    method: str
    url: str
    version: str | None
    status: int | None
    error_kind: str
    body: bytes
    headers: Mapping[str, str]


class RecordingTransport:
    """Transport wrapper that keeps the last response for document inspection."""

    def __init__(self, inner: Transport) -> None:
        if not callable(getattr(inner, "request", None)):
            raise ContractViolation("studio_transport_invalid")
        self._inner = inner
        self.records: list[TransportRecord] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        version: str | None,
        headers: Mapping[str, str],
        query: Mapping[str, object] | None,
        body: Mapping[str, object] | None,
        timeout_s: float,
    ) -> TransportResponse:
        response = self._inner.request(
            method=method,
            url=url,
            version=version,
            headers=headers,
            query=query,
            body=body,
            timeout_s=timeout_s,
        )
        self.records.append(
            TransportRecord(
                method=str(method).upper(),
                url=str(url),
                version=version,
                status=response.status,
                error_kind=str(response.error_kind),
                body=response.body or b"",
                headers=dict(response.headers or {}),
            )
        )
        return response

    def __len__(self) -> int:
        return len(self.records)


# ---------------------------------------------------------------------------
# session isolation
# ---------------------------------------------------------------------------


def session_mismatch(
    session: ExecutionSession,
    *,
    tenant: TenantBinding,
    agent_id: str,
    version_policy: str,
    version_id: str | None,
    contact_id: str | None,
    thread_id: str | None,
) -> str | None:
    """Name the first binding a session cannot cross, or None when it fits."""

    if not isinstance(session, ExecutionSession):
        return "session_invalid"
    if session.location_id != tenant.location_id:
        return "location_id"
    if session.agent_id != agent_id:
        return "agent_id"
    if session.version_policy != version_policy:
        return "version_policy"
    if version_id is not None and session.version_id != version_id:
        return "version_id"
    if session.contact_id != contact_id:
        return "contact_id"
    if session.thread_id != thread_id:
        return "thread_id"
    return None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _row_attr(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def _tenant_location(tenant: TenantBinding | str | None) -> str | None:
    if tenant is None:
        return None
    value = tenant.location_id if isinstance(tenant, TenantBinding) else str(tenant)
    value = value.strip()
    return value or None


def _require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractViolation("studio_id_required", detail={"field": field})
    return value.strip()


def _format_path(template: str, values: Mapping[str, str]) -> str:
    path = str(template)
    cursor = 0
    while True:
        start = path.find("{", cursor)
        if start < 0:
            break
        end = path.find("}", start)
        if end < 0:
            break
        name = path[start + 1:end]
        path = path[:start] + str(values.get(name, "")) + path[end + 1:]
        cursor = start
    if not path.startswith("/"):
        path = "/" + path
    return path


def _first(payload: Any, keys: Sequence[str]) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _named_agent(payload: Any, name: str) -> tuple[Mapping[str, Any] | None, str]:
    """Shape-tolerant name search over the documented list envelope."""

    if not isinstance(payload, Mapping):
        return None, "unreadable"
    rows: Any = None
    for key in ("agents", "data", "items"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            inner = value.get("agents") or value.get("items")
            if isinstance(inner, (list, tuple)):
                rows = inner
                break
        elif isinstance(value, (list, tuple)):
            rows = value
            break
    if rows is None:
        return None, "unreadable"
    matches = [
        row for row in rows if isinstance(row, Mapping) and row.get("name") == name
    ]
    if not matches:
        return None, "absent"
    if len(matches) > 1:
        return None, "ambiguous"
    return matches[0], "selected"


def _mapping_keys(payload: Any) -> list[str]:
    if not isinstance(payload, Mapping):
        return []
    return sorted(str(key) for key in payload)


def _subset_matches(expect: Mapping[str, Any], payload: Any) -> bool:
    """Subset match at the root, one level under data/output/result, or flat."""

    if not isinstance(payload, Mapping):
        return False
    scopes: list[Mapping[str, Any]] = [payload]
    for key in ("data", "output", "result"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            scopes.append(value)
    for scope in scopes:
        if all(scope.get(str(key)) == value for key, value in expect.items()):
            return True
    return False
