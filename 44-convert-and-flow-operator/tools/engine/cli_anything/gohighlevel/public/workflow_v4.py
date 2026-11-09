"""Public workflow adapter over the frozen public adapter (WF02).

Version-neutral and registry-driven.  The wire contract for every operation is
the registry row (``public/operations.py``); this module names internal surfaces
and resolves each one to a row at call time.  There is no literal wire version
here: a row change moves the adapter with it.

Registry ownership: ``public/operations.py`` is owned by WF00 (checkpoint
``WF00-CP01``).  When a surface this module implements has no row in the
registry it is using, the operation RAISES ``WorkflowRowMissing`` naming that
owner and checkpoint.  It never invents a method, path or Version, and it never
reports success without a row.  A caller that must exercise a surface before
the row lands injects an explicit registry (an honest fixture) into
``PublicGhlAdapter(operations=...)``; the production path still fails loudly.

Semantics that do not depend on the row:

* every write is capability-gated and default-deny, and a disabled call still
  returns a receipt;
* a definition update is a COMPLETE replacement that preserves unknown fields,
  triggers, nodes and edges, and carries the opaque revision exactly as read
  (fractional values kept; never cast, incremented or synthesised);
* an unapproved deletion is refused before transport;
* a published workflow is never silently moved to draft (409 is surfaced);
* a locally stale revision refuses with 422 before transport; a remote stale
  revision 422 triggers ONE re-read + reapply of the same approved intent;
* publish is an explicit, separately scoped operation;
* delete requires a deletion-scoped approval and exact object binding;
* restore is a fresh approved update from a snapshot plus the CURRENT revision
  (there is no documented restore endpoint, and none is invented);
* ambiguity is ``unknown_outcome`` and reconcile re-reads; it never re-writes.

Monitoring/log reads are delegated to WF25's ``workflow_monitoring`` module.
This module keeps the backward-compatible facade methods and refuses honestly
(``workflow_monitoring_module_missing``) when that module has not landed.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.parse import quote

from .adapter import ApprovalRef, PublicGhlAdapter
from .auth import TenantBinding
from .capability import ActivationBlock, Capability, CapabilityGate
from .errors import ContractViolation, ReconciliationRequired
from .idempotency import IdempotencyKey, canonical_intent
from .operations import OPERATIONS
from .readback import ReadbackSpec, ReadbackStatus
from .result import ADAPTER_VERSION, OperationResult, Status, canonical_json
from .transport import Transport, TransportResponse
from .workflow_v4_intent import (
    RevisionError,
    apply_intent,
    carry_revision,
    diff_definition,
    extract_definition,
    extract_revision,
    intent_from_snapshot,
    provider_step_id_map,
    revision_equals,
)

# ---------------------------------------------------------------------------
# internal surface -> frozen operation id
# ---------------------------------------------------------------------------

NONE: None = None

READ_OPERATION = "workflows.definition.read"
CREATE_OPERATION = "workflows.definition.create"
UPDATE_OPERATION = "workflows.definition.update"
STATUS_OPERATION = "workflows.status.publish"
DELETE_OPERATION = "workflows.definition.delete"
LIST_OPERATION = "workflows.list"
STEP_TYPES_OPERATION = "workflows.step_types.list"
VALIDATE_OPERATION = "workflows.definition.validate"
SEARCH_OPERATION = "workflows.search"
LOGS_LIST_OPERATION = "workflows.logs.list"
LOGS_AGGREGATE_OPERATION = "workflows.logs.aggregate"

OPERATION_MAP: dict[str, str | None] = {
    "definition.read": READ_OPERATION,
    # No documented operation to READ stored validation results; the validator
    # answer is the response of ``validation.validate`` itself.
    "validation.read": NONE,
    "validation.validate": VALIDATE_OPERATION,
    "step_types.list": STEP_TYPES_OPERATION,
    "search": SEARCH_OPERATION,
    "create": CREATE_OPERATION,
    "update": UPDATE_OPERATION,
    # Restore travels on the UPDATE contract: no dedicated endpoint exists.
    "restore": UPDATE_OPERATION,
    "status.read": READ_OPERATION,
    "status.change": STATUS_OPERATION,
    "delete": DELETE_OPERATION,
    "logs.list": LOGS_LIST_OPERATION,
    "logs.aggregate": LOGS_AGGREGATE_OPERATION,
}

#: Named gaps: surface -> (rule, what evidence would settle it).
GAP_RULES: dict[str, tuple[str, str]] = {
    "validation.read": (
        "workflow_validation_read_has_no_documented_operation",
        "an official operation page or an authorized describe_operation capture "
        "for reading stored validation results; until then the only validation "
        "evidence is the response of workflows.definition.validate",
    ),
}

_WRITE_KEYS: tuple[str, ...] = ("create", "update", "status.change", "delete")
#: Surfaces that ride an existing wire contract instead of owning a row:
#: ``restore`` is a fresh update from a snapshot, not a restore endpoint.
_ALIAS_SURFACES: dict[str, str] = {"restore": "update"}
_PATH_PARAM = re.compile(r"\{([^{}]+)\}")
_DOCUMENTED_STATUSES: frozenset[str] = frozenset({"draft", "published"})

#: Opaque continuation token names.  The adapter never invents a name: it
#: carries back the EXACT key it observed, so any documented spelling survives.
_CONTINUATION_KEYS: tuple[str, ...] = (
    "nextCursor",
    "cursor",
    "nextPage",
    "next",
    "pageToken",
    "startAfter",
    "after",
    "continuationToken",
)

_STEP_TYPE_KEYS: tuple[str, ...] = (
    "stepTypes",
    "step_types",
    "step-types",
    "data",
    "items",
    "results",
    "types",
)

#: Warning markers that mean an authored action did not survive as an action.
_NOOP_WARNING_MARKERS: tuple[str, ...] = (
    "converted_to_note",
    "converted to note",
    "unknown_action",
    "unknown action",
    "unsupported_action",
    "unsupported action",
    "action_noop",
    "noop_action",
    "action dropped",
    "action_dropped",
)

_STALE_MARKERS: tuple[str, ...] = (
    "stale_revision",
    "stale revision",
    "revision_mismatch",
    "revision mismatch",
    "version_conflict",
    "version conflict",
    "stale_version",
    "stale version",
)


class WorkflowGap(ContractViolation):
    """A surface has no documented operation.  Named, never invented."""

    rule = "workflow_operation_gap"


class WorkflowRowMissing(ContractViolation):
    """The registry has no row for a surface this adapter implements.

    Fail-loud by design: the alternative would be an invented endpoint.
    """

    rule = "workflow_operation_row_missing"


def _registry_row(registry: Any, operation_id: str) -> Any | None:
    getter = getattr(registry, "get", None)
    if callable(getter):
        row = getter(operation_id)
        if row is not None:
            return row
    try:
        return registry[operation_id]
    except (KeyError, TypeError):
        pass
    for name in ("require", "resolve", "lookup"):
        candidate = getattr(registry, name, None)
        if callable(candidate):
            try:
                return candidate(operation_id)
            except (KeyError, ContractViolation):
                return None
    return None


def validate_operation_map(registry: Any = OPERATIONS) -> list[str]:
    """Check every mapped row that EXISTS; return the missing operation ids.

    Missing rows are reported, not raised: a consumer decides whether the
    surface it is about to call may proceed.  Every present row must still
    agree with the map about read/write class.
    """

    missing: list[str] = []
    for key, operation_id in OPERATION_MAP.items():
        if operation_id is None:
            if key not in GAP_RULES:
                raise ContractViolation("workflow_gap_unnamed", operation_id=key)
            continue
        if key in GAP_RULES:
            raise ContractViolation("workflow_gap_has_row", operation_id=key)
        row = _registry_row(registry, operation_id)
        if row is None:
            missing.append(operation_id)
            continue
        target = _ALIAS_SURFACES.get(key, key)
        if bool(getattr(row, "write", False)) != (target in _WRITE_KEYS):
            raise ContractViolation(
                "workflow_row_write_mismatch",
                operation_id=operation_id,
                detail={"mapping": key},
            )
    return sorted(set(missing))


def _tenant_location(tenant: TenantBinding | str | None) -> str | None:
    if tenant is None:
        return None
    value = tenant.location_id if isinstance(tenant, TenantBinding) else str(tenant)
    value = value.strip()
    return value or None


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
    """Transport wrapper that keeps the last response for graph inspection."""

    def __init__(self, inner: Transport) -> None:
        if not callable(getattr(inner, "request", None)):
            raise ContractViolation("workflow_transport_invalid")
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


@dataclass(frozen=True)
class _PendingGraph:
    kind: str
    tenant: TenantBinding
    workflow_id: str | None
    name: str | None
    proposed: Mapping[str, Any] | None
    target_status: str | None
    attempt: int
    adapter_unknown: bool


class WorkflowV4Adapter:
    """Public workflow surface, disabled by default and registry-driven.

    Constructed over an existing ``PublicGhlAdapter``; every call goes through
    ``PublicGhlAdapter.call`` so the capability gate, tenant binding, approval
    and receipt rules are the shared ones.
    """

    def __init__(
        self,
        *,
        public: PublicGhlAdapter,
        transport: Transport | None = None,
        operations: Any = None,
    ) -> None:
        if not isinstance(public, PublicGhlAdapter):
            raise ContractViolation("public_adapter_required")
        base: Transport | None = transport
        if base is None:
            base = getattr(public, "_transport", None)  # ponytail: see module note
        if base is None or not callable(getattr(base, "request", None)):
            raise ContractViolation("workflow_transport_unavailable")
        if isinstance(base, RecordingTransport):
            recorder = base
        else:
            recorder = RecordingTransport(base)
            try:
                public._transport = recorder  # ponytail: see module note
            except AttributeError:  # pragma: no cover - defensive
                raise ContractViolation("workflow_transport_unbindable") from None
        self._public = public
        self._transport = recorder
        if operations is not None:
            self._operations = operations
        else:
            self._operations = getattr(public, "_operations", OPERATIONS)
        self._unreconciled: OperationResult | None = None
        self._pending_graph: dict[str, _PendingGraph] = {}
        self.step_type_catalog: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # registry and capability
    # ------------------------------------------------------------------

    def _row(self, operation_id: str) -> Any:
        row = _registry_row(self._operations, operation_id)
        if row is None:
            raise WorkflowRowMissing(
                "workflow_operation_row_missing",
                operation_id=operation_id,
                detail={
                    "owner": "WF00",
                    "checkpoint": "WF00-CP01",
                    "reason": (
                        "no registry row for this surface; the adapter refuses "
                        "to invent a method, path or wire version"
                    ),
                },
            )
        return row

    def operation_id(self, operation: str) -> str | None:
        return OPERATION_MAP.get(str(operation))

    def _require_operation(self, operation: str) -> str:
        key = str(operation)
        if key in GAP_RULES:
            rule, unblock = GAP_RULES[key]
            raise WorkflowGap(rule, operation_id=key, detail={"unblock": unblock})
        operation_id = OPERATION_MAP.get(key)
        if operation_id is None:
            raise WorkflowGap(
                "workflow_operation_gap_unnamed",
                operation_id=key,
                detail={"unblock": "name the operation and its frozen row"},
            )
        self._row(operation_id)
        return operation_id

    def capability(
        self, operation: str, *, tenant: TenantBinding | str | None = None
    ) -> Capability:
        """Capability for one surface.  A missing row is an explicit deny.

        It is NOT an exception here: routing callers must be able to ask and
        receive "denied, row missing".  The operation methods themselves raise
        ``WorkflowRowMissing`` before any transport.
        """

        key = str(operation)
        operation_id = OPERATION_MAP.get(key)
        if operation_id is None:
            return Capability(
                operation_id=key,
                activation_blocked=ActivationBlock(
                    reason="no operation row is mapped for this workflow surface",
                    owner="WF00",
                    unblock="publish the row under WF00-CP01",
                ),
            )
        if _registry_row(self._operations, operation_id) is None:
            return Capability(
                operation_id=operation_id,
                activation_blocked=ActivationBlock(
                    reason="operation row missing from the registry",
                    owner="WF00",
                    unblock="publish the row under WF00-CP01",
                ),
            )
        location_id = _tenant_location(tenant)
        if location_id is None:
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

    def read_definition(
        self, *, tenant: TenantBinding, workflow_id: str, attempt: int = 1
    ) -> OperationResult:
        return self._public.call(
            operation_id=self._require_operation("definition.read"),
            tenant=tenant,
            path_params={"workflowId": workflow_id},
            attempt=attempt,
        )

    def read_definition_document(
        self, *, tenant: TenantBinding, workflow_id: str, attempt: int = 1
    ) -> tuple[OperationResult, Any]:
        mark = len(self._transport)
        result = self.read_definition(
            tenant=tenant, workflow_id=workflow_id, attempt=attempt
        )
        if result.status is not Status.ok:
            return result, None
        return result, self._response_body(mark)

    def read_status(
        self, *, tenant: TenantBinding, workflow_id: str, attempt: int = 1
    ) -> OperationResult:
        result, payload = self.read_definition_document(
            tenant=tenant, workflow_id=workflow_id, attempt=attempt
        )
        if result.status is not Status.ok:
            return result
        status = _status_of(payload)
        return self._enrich(
            result,
            {
                "operation": "status.read",
                "workflow_id": workflow_id,
                "status": status,
                "status_present": status is not None,
            },
        )

    def read_validation(
        self, *, tenant: TenantBinding, workflow_id: str, attempt: int = 1
    ) -> OperationResult:
        """Named gap: no documented operation reads stored validation results."""

        raise WorkflowGap(
            GAP_RULES["validation.read"][0],
            operation_id="validation.read",
            detail={"unblock": GAP_RULES["validation.read"][1]},
        )

    # ------------------------------------------------------------------
    # step types, validation, search
    # ------------------------------------------------------------------

    def _step_type_page(
        self,
        tenant: TenantBinding,
        *,
        continuation: Mapping[str, Any] | None,
        attempt: int,
    ) -> tuple[OperationResult, Any, int]:
        mark = len(self._transport)
        result = self._public.call(
            operation_id=self._require_operation("step_types.list"),
            tenant=tenant,
            query=dict(continuation or {}) or None,
            attempt=attempt,
        )
        if result.status is not Status.ok:
            return result, None, mark
        return result, self._response_body(mark), mark

    def discovered_step_types(
        self,
        *,
        tenant: TenantBinding,
        attempt: int = 1,
        max_pages: int = 50,
        cache: bool = True,
    ) -> tuple[OperationResult, dict[str, Any]]:
        """Discover step types across EVERY page.

        Continuation tokens are carried back under the exact key observed and
        never reconstructed.  ``complete`` is True only when no continuation
        token remained; a token this adapter cannot carry leaves ``complete``
        False and names the unresolved shape.
        """

        if not isinstance(max_pages, int) or max_pages < 1:
            raise ContractViolation("step_type_page_budget_invalid")
        catalog: dict[str, Any] = {}
        asset_refs: list[dict[str, Any]] = []
        pages = 0
        continuation: dict[str, Any] | None = None
        unresolved: dict[str, Any] | None = None
        result: OperationResult | None = None
        while pages < max_pages:
            result, payload, _mark = self._step_type_page(
                tenant, continuation=continuation, attempt=attempt
            )
            pages += 1
            if result.status is not Status.ok:
                return result, self._catalog_evidence(
                    catalog,
                    asset_refs,
                    pages,
                    complete=False,
                    unresolved={"reason": "page_unreadable",
                                "status": result.status.value},
                )
            rows = _step_type_rows(payload)
            if rows is None:
                return result, self._catalog_evidence(
                    catalog,
                    asset_refs,
                    pages,
                    complete=False,
                    unresolved={"reason": "page_shape_unrecognized"},
                )
            for row in rows:
                identity = _step_type_identity(row)
                if identity is None:
                    continue
                catalog[identity] = row
                for ref in _asset_references(row, identity):
                    asset_refs.append(ref)
            token, shape = _continuation_token(payload)
            if token is None:
                if shape == "unresolved":
                    unresolved = {
                        "reason": "continuation_shape_unresolved",
                        "hint": "carry the observed opaque token forward verbatim",
                    }
                    break
                if cache:
                    self.step_type_catalog = dict(catalog)
                return result, self._catalog_evidence(
                    catalog, asset_refs, pages, complete=True, unresolved=None
                )
            continuation = token
        if result is None:  # pragma: no cover - max_pages >= 1
            raise ContractViolation("step_type_page_budget_invalid")
        return result, self._catalog_evidence(
            catalog,
            asset_refs,
            pages,
            complete=False,
            unresolved=unresolved or {"reason": "page_budget_exhausted"},
        )

    @staticmethod
    def _catalog_evidence(
        catalog: Mapping[str, Any],
        asset_refs: list[dict[str, Any]],
        pages: int,
        *,
        complete: bool,
        unresolved: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "step_types": dict(catalog),
            "count": len(catalog),
            "pages": pages,
            "complete": complete,
            "asset_references": list(asset_refs),
            "asset_reference_count": len(asset_refs),
            "unresolved": dict(unresolved or {}) or None,
            "identity_is_the_schema_key": True,
        }

    def validate_definition(
        self,
        *,
        tenant: TenantBinding,
        definition: Mapping[str, Any],
        approval: ApprovalRef | Mapping[str, Any] | str | None = None,
        step_types: Mapping[str, Any] | None = None,
        attempt: int = 1,
    ) -> OperationResult:
        """Vendor validator.  Never persists.

        HTTP 200 with ``valid:false`` is a FAILURE.  A missing ``valid`` field
        cannot be read as success.  A warning that an authored action became a
        note/no-op is a business failure, not a warning to ignore.
        """

        self._guard()
        key = "validation.validate"
        operation_id = self._require_operation(key)
        if not isinstance(definition, Mapping):
            raise ContractViolation("definition_invalid")
        if not self._enabled(operation_id, tenant):
            return self._disabled_result(
                key, tenant=tenant, attempt=attempt, body=dict(definition)
            )
        mark = len(self._transport)
        result = self._public.call(
            operation_id=operation_id,
            tenant=tenant,
            body=dict(definition),
            approval=approval,
            attempt=attempt,
        )
        if result.status is not Status.ok:
            return result
        payload = self._response_body(mark)
        body = _unwrap(payload)
        valid = body.get("valid") if isinstance(body, Mapping) else None
        if not isinstance(valid, bool):
            return self._refusal_from_result(
                result,
                key,
                tenant=tenant,
                status=Status.unavailable,
                rule="validation_result_missing",
                attempt=attempt,
                detail={"reason": "the validator returned no boolean 'valid' field"},
            )
        errors = _issue_list(body, "errors")
        warnings = _issue_list(body, "warnings")
        evidence: dict[str, Any] = {
            "operation": key,
            "valid": valid,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": [_issue_summary(item) for item in errors],
            "warnings": [_issue_summary(item) for item in warnings],
            "persisted": False,
        }
        noop = [item for item in warnings if _noop_warning(item)]
        if noop:
            return self._refusal_from_result(
                result,
                key,
                tenant=tenant,
                status=Status.validation_error,
                rule="unknown_action_noop_warning",
                attempt=attempt,
                detail={
                    "reason": "an authored action was reported as a note/no-op",
                    "warning_count": len(noop),
                    "warnings": [_issue_summary(item) for item in noop],
                },
            )
        builder_only = self._builder_only_missing(
            definition,
            step_types if step_types is not None else self.step_type_catalog,
        )
        if builder_only:
            return self._refusal_from_result(
                result,
                key,
                tenant=tenant,
                status=Status.validation_error,
                rule="builder_only_field_missing",
                attempt=attempt,
                detail={
                    "reason": (
                        "the schema marks fields builder-only: a 200 validation "
                        "does not waive the client-side proof"
                    ),
                    "missing": builder_only,
                },
            )
        if not valid:
            return self._refusal_from_result(
                result,
                key,
                tenant=tenant,
                status=Status.validation_error,
                rule="validation_failed",
                attempt=attempt,
                detail={
                    "reason": "the vendor validator rejected the definition",
                    "error_count": len(errors),
                    "errors": [_issue_summary(item) for item in errors],
                },
            )
        return self._enrich(result, evidence)

    def search_workflows(
        self,
        *,
        tenant: TenantBinding,
        body: Mapping[str, Any] | None = None,
        attempt: int = 1,
    ) -> OperationResult:
        """Search is a READ: no write approval and no idempotency key.

        It is documented to consume the workflow write quota; the receipt says
        so and records the read classification.
        """

        operation_id = self._require_operation("search")
        if body is not None and not isinstance(body, Mapping):
            raise ContractViolation("search_body_invalid")
        result = self._public.call(
            operation_id=operation_id,
            tenant=tenant,
            body=dict(body or {}),
            attempt=attempt,
        )
        return self._enrich(
            result,
            {
                "operation": "search",
                "read_operation": True,
                "consumes_write_quota": True,
                "write_class": "read",
            },
        )

    @staticmethod
    def _builder_only_missing(
        definition: Mapping[str, Any], step_types: Mapping[str, Any] | None
    ) -> list[dict[str, Any]]:
        if not step_types:
            return []
        missing: list[dict[str, Any]] = []
        for kind in ("actions", "triggers"):
            nodes = definition.get(kind)
            if not isinstance(nodes, (list, tuple)):
                continue
            for node in nodes:
                if not isinstance(node, Mapping):
                    continue
                identity = _step_type_identity(node)
                if identity is None or identity not in step_types:
                    continue
                schema = step_types[identity]
                if not isinstance(schema, Mapping):
                    continue
                if str(schema.get("requiredEnforcement") or "") != "builder-only":
                    continue
                for field in _required_schema_fields(schema):
                    if field not in node:
                        missing.append(
                            {"kind": kind, "step_type": identity, "field": field}
                        )
        return missing

    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------

    def create_workflow(
        self,
        *,
        tenant: TenantBinding,
        definition: Mapping[str, Any],
        approval: ApprovalRef | Mapping[str, Any] | str,
        folder: Mapping[str, Any] | None = None,
        attempt: int = 1,
        folder_path_max_depth: int | None = None,
        step_types: Mapping[str, Any] | None = None,
        resolved_asset_ids: tuple[str, ...] | list[str] | None = None,
    ) -> OperationResult:
        """Create a DRAFT; capture the provider-assigned workflow and step ids."""

        self._guard()
        key = "create"
        operation_id = self._require_operation(key)
        if not self._enabled(operation_id, tenant):
            return self._disabled_result(key, tenant=tenant, attempt=attempt)
        body = _create_body(
            definition, folder, folder_path_max_depth=folder_path_max_depth
        )
        unresolved_assets = _unresolved_assets(
            step_types if step_types is not None else self.step_type_catalog,
            body,
            tuple(resolved_asset_ids or ()),
        )
        if unresolved_assets:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.denied,
                rule="asset_reference_unresolved",
                attempt=attempt,
                body={"name": str(body.get("name") or "")},
                detail={
                    "reason": (
                        "a referenced asset id was not resolved before submit; "
                        "the provider is never asked to guess"
                    ),
                    "unresolved": unresolved_assets,
                },
            )

        readback = ReadbackSpec(
            operation_id=LIST_OPERATION,
            expect={"name": str(body["name"])},
            description="duplicate-create reconciliation by workflow name",
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
            name=str(body["name"]),
        )
        if result.status is not Status.ok:
            if not (
                result.status is Status.unknown_outcome
                and result.readback is not None
                and result.readback.result is ReadbackStatus.mismatch
            ):
                return result
            self._settle_adapter_pending(result)
            self._clear(result.receipt_id)
            result = replace(result, status=Status.ok, error=None)

        payload = self._response_body(mark)
        workflow_id = _field(payload, "workflowId") or _field(payload, "id")
        status = _field(payload, "status")
        if status is not None and status != "draft":
            return self._mark_unknown(
                result,
                kind=key,
                tenant=tenant,
                workflow_id=str(workflow_id) if workflow_id else None,
                rule="create_status_not_draft",
                detail={"documented_status": "draft", "observed": status},
                name=str(body["name"]),
                attempt=attempt,
            )

        listed, found, readable = self._find_workflow_by_name(
            tenant=tenant, name=str(body["name"]), attempt=attempt
        )
        if not readable:
            return self._mark_unknown(
                result,
                kind=key,
                tenant=tenant,
                workflow_id=str(workflow_id) if workflow_id else None,
                rule="create_readback_unreadable",
                detail={"read_status": listed.status.value},
                name=str(body["name"]),
                attempt=attempt,
            )
        if found is None:
            return self._mark_unknown(
                result,
                kind=key,
                tenant=tenant,
                workflow_id=str(workflow_id) if workflow_id else None,
                rule="create_readback_missing",
                detail={"readback": LIST_OPERATION},
                name=str(body["name"]),
                attempt=attempt,
            )
        workflow_id = _first(found.get("id"), found.get("_id")) or workflow_id
        id_map, map_status = self._provider_ids(
            tenant=tenant, workflow_id=workflow_id, authored=body, attempt=attempt
        )
        return self._enrich(
            result,
            {
                "operation": key,
                "workflow_id": workflow_id,
                "status": "draft",
                "readback": LIST_OPERATION,
                "readback_matched_by": "name",
                "provider_step_id_map": id_map,
                "provider_step_id_map_status": map_status,
            },
        )

    def _provider_ids(
        self,
        *,
        tenant: TenantBinding,
        workflow_id: Any,
        authored: Mapping[str, Any],
        attempt: int,
    ) -> tuple[dict[str, str], str]:
        """Translate authored step ids to provider ids from a fresh read.

        A provider that re-keys steps is only knowable from what it returned.
        An unmappable shape is recorded as ``unresolved``; it is never guessed.
        """

        if not isinstance(workflow_id, str) or not workflow_id:
            return {}, "unresolved_workflow_id"
        read_result, payload = self.read_definition_document(
            tenant=tenant, workflow_id=workflow_id, attempt=attempt
        )
        if read_result.status is not Status.ok:
            return {}, "unreadable_definition"
        returned = extract_definition(payload)
        if returned is None:
            return {}, "unreadable_definition"
        mapping, complete = provider_step_id_map(authored, returned)
        return mapping, "mapped" if complete else "partial"

    # ------------------------------------------------------------------
    # update (the frozen algorithm)
    # ------------------------------------------------------------------

    def update_definition(
        self,
        *,
        tenant: TenantBinding,
        workflow_id: str,
        intent: Any,
        approval: ApprovalRef | Mapping[str, Any] | str,
        expected_revision: Any,
        allow_deletions: bool = False,
        allow_draft_transition: bool = False,
        draft_transition_approval: ApprovalRef | Mapping[str, Any] | str | None = None,
        attempt: int = 1,
        realign_on_stale: bool = True,
    ) -> OperationResult:
        """Complete-replacement update driven by an approved intent."""

        self._guard()
        key = "update"
        operation_id = self._require_operation(key)
        path_params = {"workflowId": workflow_id}
        if not self._enabled(operation_id, tenant):
            return self._disabled_result(
                key, tenant=tenant, attempt=attempt, path_params=path_params
            )
        if expected_revision is None:
            raise ContractViolation(
                "expected_revision_required",
                operation_id=operation_id,
                detail={"reason": "the caller must echo the revision it read"},
            )

        prepared = self._prepare_update(
            key=key,
            operation_id=operation_id,
            tenant=tenant,
            workflow_id=workflow_id,
            path_params=path_params,
            intent=intent,
            approval=approval,
            expected_revision=expected_revision,
            allow_deletions=allow_deletions,
            allow_draft_transition=allow_draft_transition,
            draft_transition_approval=draft_transition_approval,
            attempt=attempt,
        )
        if isinstance(prepared, OperationResult):
            return prepared
        proposed, revision, status, read_receipt, readback, draft_transition = prepared

        write = self._write(
            operation_id,
            tenant=tenant,
            path_params=path_params,
            body=proposed,
            approval=approval,
            readback=readback,
            attempt=attempt,
            kind=key,
            workflow_id=workflow_id,
            proposed=proposed,
        )
        realigned = False
        realign_reads = 0
        if (
            write.status is Status.validation_error
            and realign_on_stale
            and self._stale_revision_response()
        ):
            # The DOCUMENTED 422 stale-revision branch: nothing was written, so
            # re-read the CURRENT graph and re-apply the SAME approved intent.
            # Bounded to one realignment; a second failure is surfaced.
            realign_reads += 1
            fresh, fresh_payload = self.read_definition_document(
                tenant=tenant, workflow_id=workflow_id, attempt=attempt
            )
            if fresh.status is not Status.ok:
                return fresh
            fresh_definition = extract_definition(fresh_payload)
            if fresh_definition is None:
                return self._refusal(
                    key,
                    tenant=tenant,
                    status=Status.unavailable,
                    rule="workflow_definition_unreadable",
                    attempt=attempt,
                    path_params=path_params,
                    detail={"source_read_receipt": fresh.receipt_id},
                )
            realigned_proposed = apply_intent(fresh_definition, intent)
            deletions = diff_definition(
                fresh_definition, realigned_proposed
            ).deletion_requests()
            if deletions and not (allow_deletions or _deletion_scope(approval)):
                return self._refusal(
                    key,
                    tenant=tenant,
                    status=Status.denied,
                    rule="deletion_requires_approval",
                    attempt=attempt,
                    path_params=path_params,
                    detail={
                        "reason": "the re-read graph would lose nodes",
                        "deletion_requests": [
                            {"kind": node.kind, "identity": node.identity}
                            for node in deletions
                        ],
                        "source_read_receipt": fresh.receipt_id,
                    },
                )
            try:
                fresh_revision = extract_revision(realigned_proposed)
            except RevisionError as exc:
                return self._refusal(
                    key,
                    tenant=tenant,
                    status=Status.validation_error,
                    rule=exc.rule,
                    attempt=attempt,
                    path_params=path_params,
                    detail={"reason": "revision_missing_or_invalid"},
                    documented_http_status=422,
                )
            carry_revision(realigned_proposed, fresh_revision)
            proposed = realigned_proposed
            revision = fresh_revision
            realigned = True
            # Same logical attempt: the rejected request provably wrote
            # nothing, and the shared adapter's max_attempts bound is about
            # retries after an ambiguous OUTCOME.  The realignment is recorded
            # separately in evidence, never hidden.
            write = self._write(
                operation_id,
                tenant=tenant,
                path_params=path_params,
                body=proposed,
                approval=approval,
                readback=readback,
                attempt=attempt,
                kind=key,
                workflow_id=workflow_id,
                proposed=proposed,
            )
            if write.status is Status.validation_error:
                return replace(
                    write,
                    error=dict(write.error or {}, rule="stale_revision_after_realign"),
                )
        if write.status is not Status.ok:
            return write

        verify, verify_payload = self.read_definition_document(
            tenant=tenant, workflow_id=workflow_id, attempt=attempt
        )
        if verify.status is not Status.ok:
            return self._mark_unknown(
                write,
                kind=key,
                tenant=tenant,
                workflow_id=workflow_id,
                rule="update_readback_unavailable",
                detail={"read_status": verify.status.value},
                proposed=proposed,
                attempt=attempt,
            )
        read_back = extract_definition(verify_payload)
        if read_back is None:
            return self._mark_unknown(
                write,
                kind=key,
                tenant=tenant,
                workflow_id=workflow_id,
                rule="update_readback_unreadable",
                detail={},
                proposed=proposed,
                attempt=attempt,
            )
        readback_diff = diff_definition(proposed, read_back)
        if not readback_diff.content_is_empty():
            return self._mark_unknown(
                write,
                kind=key,
                tenant=tenant,
                workflow_id=workflow_id,
                rule="update_readback_mismatch",
                detail={"readback_diff": readback_diff.as_evidence()},
                proposed=proposed,
                attempt=attempt,
            )

        try:
            revision_after = extract_revision(read_back)
        except RevisionError:
            revision_after = None
        return self._enrich(
            write,
            {
                "operation": key,
                "workflow_id": workflow_id,
                "revision_before": revision,
                "revision_after": revision_after,
                "status_before": status,
                "draft_transition_performed": draft_transition,
                "publish_authorized": False,
                "graph_fingerprint": _hash(proposed),
                "readback_diff": readback_diff.as_evidence(),
                "readback_verified": True,
                "source_read_receipt": read_receipt,
                "revision_realigned": realigned,
                "realign_reads": realign_reads,
            },
        )

    def _prepare_update(
        self,
        *,
        key: str,
        operation_id: str,
        tenant: TenantBinding,
        workflow_id: str,
        path_params: Mapping[str, str],
        intent: Any,
        approval: ApprovalRef | Mapping[str, Any] | str,
        expected_revision: Any,
        allow_deletions: bool,
        allow_draft_transition: bool,
        draft_transition_approval: ApprovalRef | Mapping[str, Any] | str | None,
        attempt: int,
    ) -> Any:
        read_result, payload = self.read_definition_document(
            tenant=tenant, workflow_id=workflow_id, attempt=attempt
        )
        if read_result.status is not Status.ok:
            return read_result
        definition = extract_definition(payload)
        if definition is None:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.unavailable,
                rule="workflow_definition_unreadable",
                attempt=attempt,
                path_params=path_params,
                detail={"source_read_receipt": read_result.receipt_id},
            )
        status = _status_of(payload)
        if status not in _DOCUMENTED_STATUSES:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.unavailable,
                rule="workflow_status_unreadable",
                attempt=attempt,
                path_params=path_params,
                detail={
                    "source_read_receipt": read_result.receipt_id,
                    "observed": status,
                },
            )
        try:
            revision_seen = extract_revision(definition)
        except RevisionError as exc:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.validation_error,
                rule=exc.rule,
                attempt=attempt,
                path_params=path_params,
                detail={
                    "reason": "revision_missing_or_invalid",
                    "source_read_receipt": read_result.receipt_id,
                },
                documented_http_status=422,
            )
        if not revision_equals(expected_revision, revision_seen):
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.validation_error,
                rule="stale_revision",
                attempt=attempt,
                path_params=path_params,
                detail={
                    "reason": "expected revision does not match the current read",
                    "source_read_receipt": read_result.receipt_id,
                },
                documented_http_status=422,
            )

        draft_transition = False
        if status == "published":
            if not allow_draft_transition:
                return self._refusal(
                    key,
                    tenant=tenant,
                    status=Status.conflict,
                    rule="workflow_published",
                    attempt=attempt,
                    path_params=path_params,
                    detail={
                        "hint": (
                            "no automatic unpublish: authorize a draft transition "
                            "with a separate approval, then update"
                        ),
                        "source_read_receipt": read_result.receipt_id,
                    },
                    documented_http_status=409,
                )
            if draft_transition_approval is None:
                raise ContractViolation(
                    "draft_transition_approval_required", operation_id=operation_id
                )
            transition = self.set_status(
                tenant=tenant,
                workflow_id=workflow_id,
                status="draft",
                approval=draft_transition_approval,
                attempt=attempt,
            )
            if transition.status is not Status.ok:
                return transition
            draft_transition = True
            read_result, payload = self.read_definition_document(
                tenant=tenant, workflow_id=workflow_id, attempt=attempt
            )
            if read_result.status is not Status.ok:
                return read_result
            definition = extract_definition(payload)
            if definition is None:
                return self._refusal(
                    key,
                    tenant=tenant,
                    status=Status.unavailable,
                    rule="workflow_definition_unreadable",
                    attempt=attempt,
                    path_params=path_params,
                    detail={"source_read_receipt": read_result.receipt_id},
                )

        proposed = apply_intent(definition, intent)
        deletions = diff_definition(definition, proposed).deletion_requests()
        if deletions and not (allow_deletions or _deletion_scope(approval)):
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.denied,
                rule="deletion_requires_approval",
                attempt=attempt,
                path_params=path_params,
                detail={
                    "reason": "the intent omits nodes present in the current graph",
                    "deletion_requests": [
                        {"kind": node.kind, "identity": node.identity}
                        for node in deletions
                    ],
                    "source_read_receipt": read_result.receipt_id,
                },
            )
        try:
            revision = extract_revision(proposed)
        except RevisionError as exc:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.validation_error,
                rule=exc.rule,
                attempt=attempt,
                path_params=path_params,
                detail={
                    "reason": "revision_missing_or_invalid",
                    "source_read_receipt": read_result.receipt_id,
                },
                documented_http_status=422,
            )
        carry_revision(proposed, revision)
        return (
            proposed,
            revision,
            status,
            read_result.receipt_id,
            _identity_readback(workflow_id),
            draft_transition,
        )

    def _stale_revision_response(self) -> bool:
        """True when the LAST recorded response names a stale revision.

        Nothing is inferred from the 422 alone: a generic validation error is
        not realigned, because re-sending it would be a blind retry.
        """

        if not self._transport.records:
            return False
        record = self._transport.records[-1]
        if record.status != 422 or not record.body:
            return False
        try:
            body = json.loads(record.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return False
        return _mentions_stale_revision(body)

    # ------------------------------------------------------------------
    # status change (publish / unpublish)
    # ------------------------------------------------------------------

    def set_status(
        self,
        *,
        tenant: TenantBinding,
        workflow_id: str,
        status: str,
        approval: ApprovalRef | Mapping[str, Any] | str,
        attempt: int = 1,
    ) -> OperationResult:
        self._guard()
        key = "status.change"
        operation_id = self._require_operation(key)
        path_params = {"workflowId": workflow_id}
        if not self._enabled(operation_id, tenant):
            return self._disabled_result(
                key,
                tenant=tenant,
                attempt=attempt,
                path_params=path_params,
                body={"status": status} if status in _DOCUMENTED_STATUSES else None,
            )
        if status not in _DOCUMENTED_STATUSES:
            raise ContractViolation(
                "status_literal_invalid",
                operation_id=operation_id,
                detail={"allowed": sorted(_DOCUMENTED_STATUSES)},
            )
        if status == "published" and not _publication_scope(approval):
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.denied,
                rule="publish_approval_not_publication_scoped",
                attempt=attempt,
                path_params=path_params,
                body={"status": status},
                detail={
                    "reason": (
                        "the recorded authorization does not name a publication "
                        "scope; a publication is never authorized by an approval "
                        "recorded for some other action"
                    ),
                    "required_scope": "publication",
                    "accepted_scope_forms": (
                        "an approval mapping whose scope is publication/publish/"
                        "live, or a ref carrying an explicit marker such as "
                        "scope:publication, publication-scoped, allow-publish or "
                        "approved_live_publication"
                    ),
                },
            )

        readback = _identity_readback(workflow_id, status=status)
        write = self._write(
            operation_id,
            tenant=tenant,
            path_params=path_params,
            body={"status": status},
            approval=approval,
            readback=readback,
            attempt=attempt,
            kind=key,
            workflow_id=workflow_id,
            target_status=status,
        )
        if write.status is not Status.ok:
            return write
        verify, payload = self.read_definition_document(
            tenant=tenant, workflow_id=workflow_id, attempt=attempt
        )
        observed = _status_of(payload) if verify.status is Status.ok else None
        if verify.status is not Status.ok or observed != status:
            return self._mark_unknown(
                write,
                kind=key,
                tenant=tenant,
                workflow_id=workflow_id,
                rule="status_readback_mismatch",
                detail={
                    "target_status": status,
                    "observed": observed,
                    "read_status": verify.status.value,
                },
                target_status=status,
                attempt=attempt,
            )
        revision_after = None
        definition = extract_definition(payload)
        if definition is not None:
            try:
                revision_after = extract_revision(definition)
            except RevisionError:
                revision_after = None
        return self._enrich(
            write,
            {
                "operation": key,
                "workflow_id": workflow_id,
                "status_after": observed,
                "revision_after": revision_after,
                "fresh_read_after_status_change": True,
                "observed_status": observed,
                "status_source": "fresh_read_after_status_change",
                "authorization_scope": "publication" if status == "published" else None,
                "publish_authorized": status == "published",
            },
        )

    def publish_workflow(
        self,
        *,
        tenant: TenantBinding,
        workflow_id: str,
        approval: ApprovalRef | Mapping[str, Any] | str,
        attempt: int = 1,
    ) -> OperationResult:
        return self.set_status(
            tenant=tenant,
            workflow_id=workflow_id,
            status="published",
            approval=approval,
            attempt=attempt,
        )

    def unpublish_workflow(
        self,
        *,
        tenant: TenantBinding,
        workflow_id: str,
        approval: ApprovalRef | Mapping[str, Any] | str,
        attempt: int = 1,
    ) -> OperationResult:
        return self.set_status(
            tenant=tenant,
            workflow_id=workflow_id,
            status="draft",
            approval=approval,
            attempt=attempt,
        )

    # ------------------------------------------------------------------
    # delete and restore
    # ------------------------------------------------------------------

    def delete_workflow(
        self,
        *,
        tenant: TenantBinding,
        workflow_id: str,
        approval: ApprovalRef | Mapping[str, Any] | str,
        attempt: int = 1,
    ) -> OperationResult:
        """Permanent delete: destructive approval and exact object binding."""

        self._guard()
        key = "delete"
        operation_id = self._require_operation(key)
        path_params = {"workflowId": workflow_id}
        if not self._enabled(operation_id, tenant):
            return self._disabled_result(
                key, tenant=tenant, attempt=attempt, path_params=path_params
            )
        if not _deletion_scope(approval):
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.denied,
                rule="delete_requires_destructive_approval",
                attempt=attempt,
                path_params=path_params,
                detail={
                    "reason": (
                        "a delete needs an approval explicitly scoped to deletion; "
                        "a generic approval never authorizes destruction"
                    ),
                    "required_scope": "deletion",
                    "bound_workflow_id": workflow_id,
                },
            )

        snapshot_result, payload = self.read_definition_document(
            tenant=tenant, workflow_id=workflow_id, attempt=attempt
        )
        if snapshot_result.status is not Status.ok:
            return snapshot_result
        definition = extract_definition(payload)
        if definition is None:
            return self._refusal(
                key,
                tenant=tenant,
                status=Status.unavailable,
                rule="delete_snapshot_unreadable",
                attempt=attempt,
                path_params=path_params,
                detail={"source_read_receipt": snapshot_result.receipt_id},
            )

        readback = _identity_readback(workflow_id)
        write = self._write(
            operation_id,
            tenant=tenant,
            path_params=path_params,
            body=None,
            approval=approval,
            readback=readback,
            attempt=attempt,
            kind=key,
            workflow_id=workflow_id,
        )
        if write.status is not Status.ok:
            if not (
                write.status is Status.unknown_outcome
                and write.readback is not None
                and write.readback.result is ReadbackStatus.absent
            ):
                return write
            if self._settle_adapter_pending(write).status is not Status.not_found:
                return write
            self._clear(write.receipt_id)
            write = replace(write, status=Status.ok, error=None)

        verify = self.read_definition(
            tenant=tenant, workflow_id=workflow_id, attempt=attempt
        )
        if verify.status is not Status.not_found:
            return self._mark_unknown(
                write,
                kind=key,
                tenant=tenant,
                workflow_id=workflow_id,
                rule=(
                    "delete_readback_still_present"
                    if verify.status is Status.ok
                    else "delete_readback_unavailable"
                ),
                detail={"read_status": verify.status.value},
                attempt=attempt,
            )
        return self._enrich(
            write,
            {
                "operation": key,
                "workflow_id": workflow_id,
                "deleted": True,
                "snapshot_fingerprint": _hash(definition),
                "readback": READ_OPERATION,
                "readback_status": "absent",
                "exact_binding": {"workflowId": workflow_id},
                "approval_scope": "deletion",
            },
        )

    def restore_workflow(
        self,
        *,
        tenant: TenantBinding,
        workflow_id: str,
        snapshot: Mapping[str, Any],
        approval: ApprovalRef | Mapping[str, Any] | str,
        allow_deletions: bool = False,
        attempt: int = 1,
    ) -> OperationResult:
        """Restore = a new approved UPDATE from a snapshot.

        The snapshot's historical revision is never replayed: the update reads
        the CURRENT definition, rebuilds the approved graph from it plus the
        snapshot intent, and writes with the fresh revision.  There is no
        documented restore endpoint and none is invented.
        """

        self._guard()
        if not isinstance(snapshot, Mapping):
            raise ContractViolation(
                "restore_snapshot_invalid", detail={"type": type(snapshot).__name__}
            )
        snapshot_definition = extract_definition(snapshot)
        if snapshot_definition is None and "definition" not in snapshot:
            snapshot_definition = snapshot
        if (
            not isinstance(snapshot_definition, Mapping)
            or not snapshot_definition
        ):
            raise ContractViolation("restore_snapshot_invalid")

        read_result, payload = self.read_definition_document(
            tenant=tenant, workflow_id=workflow_id, attempt=attempt
        )
        if read_result.status is not Status.ok:
            return read_result
        current = extract_definition(payload)
        if current is None:
            return self._refusal(
                "restore",
                tenant=tenant,
                status=Status.unavailable,
                rule="workflow_definition_unreadable",
                attempt=attempt,
                path_params={"workflowId": workflow_id},
                detail={"source_read_receipt": read_result.receipt_id},
            )
        try:
            fresh_revision = extract_revision(current)
        except RevisionError as exc:
            return self._refusal(
                "restore",
                tenant=tenant,
                status=Status.validation_error,
                rule=exc.rule,
                attempt=attempt,
                path_params={"workflowId": workflow_id},
                detail={
                    "reason": "revision_missing_or_invalid",
                    "source_read_receipt": read_result.receipt_id,
                },
                documented_http_status=422,
            )
        intent = intent_from_snapshot(current, snapshot_definition)
        result = self.update_definition(
            tenant=tenant,
            workflow_id=workflow_id,
            intent=intent,
            approval=approval,
            expected_revision=fresh_revision,
            allow_deletions=allow_deletions,
            attempt=attempt,
        )
        return self._enrich(
            result,
            {
                "restore": {
                    "mode": "approved_update_from_snapshot",
                    "snapshot_fingerprint": _hash(snapshot_definition),
                    "snapshot_revision": snapshot_definition.get("version"),
                    "replayed_snapshot_revision": False,
                    "fresh_revision": fresh_revision,
                }
            },
        )

    # ------------------------------------------------------------------
    # monitoring facades (WF25 owns the implementation)
    # ------------------------------------------------------------------

    def list_logs(
        self,
        *,
        tenant: TenantBinding,
        workflow_id: str,
        query: Mapping[str, Any] | None = None,
        attempt: int = 1,
    ) -> OperationResult:
        """Delegate to WF25's ``workflow_monitoring``; never a second impl."""

        return self._delegate_monitoring(
            "logs.list",
            tenant=tenant,
            workflow_id=workflow_id,
            query=query,
            attempt=attempt,
        )

    def aggregate_logs(
        self,
        *,
        tenant: TenantBinding,
        workflow_id: str,
        query: Mapping[str, Any] | None = None,
        attempt: int = 1,
    ) -> OperationResult:
        return self._delegate_monitoring(
            "logs.aggregate",
            tenant=tenant,
            workflow_id=workflow_id,
            query=query,
            attempt=attempt,
        )

    def _delegate_monitoring(
        self,
        surface: str,
        *,
        tenant: TenantBinding,
        workflow_id: str,
        query: Mapping[str, Any] | None,
        attempt: int,
    ) -> OperationResult:
        operation_id = OPERATION_MAP[surface]
        assert operation_id is not None  # mapped by construction
        try:
            from . import workflow_monitoring as monitoring  # local import
        except Exception:  # noqa: BLE001 - module has not landed yet
            tool = "list" if surface == "logs.list" else "aggregate"
            return self._policy_result(
                operation_id,
                tenant=tenant,
                status=Status.unavailable,
                rule="workflow_monitoring_module_missing",
                detail={
                    "owner": "WF25",
                    "surface": surface,
                    "reason": (
                        "workflow_monitoring has not landed; this facade does "
                        "not implement a second log reader"
                    ),
                    "delegated_tool": tool,
                    "workflow_id": workflow_id,
                    "query_keys": sorted(str(key) for key in dict(query or {})),
                },
                attempt=attempt,
            )
        callable_name = (
            "list_workflow_logs" if surface == "logs.list" else "aggregate_workflow_logs"
        )
        delegate: Callable[..., Any] | None = getattr(monitoring, callable_name, None)
        if not callable(delegate):
            return self._policy_result(
                operation_id,
                tenant=tenant,
                status=Status.unavailable,
                rule="workflow_monitoring_entrypoint_missing",
                detail={
                    "owner": "WF25",
                    "surface": surface,
                    "expected_callable": callable_name,
                },
                attempt=attempt,
            )
        result = delegate(
            adapter=self,
            tenant=tenant,
            workflow_id=workflow_id,
            query=dict(query or {}),
            attempt=attempt,
        )
        return self._enrich(result, {"operation": surface, "delegated_to": "WF25"})

    # ------------------------------------------------------------------
    # reconciliation (freeze 2.4)
    # ------------------------------------------------------------------

    def _guard(self) -> None:
        if self._unreconciled is not None:
            raise ReconciliationRequired(
                operation_id=self._unreconciled.operation_id,
                detail={
                    "receipt_id": self._unreconciled.receipt_id,
                    "rule": "workflow_write_unreconciled",
                },
            )

    def reconcile(self, prior: OperationResult) -> OperationResult:
        """Re-read the affected graph.  Never retries the write."""

        if not isinstance(prior, OperationResult):
            raise ContractViolation("reconcile_prior_invalid")
        blocked = self._unreconciled
        if blocked is None or prior.receipt_id != blocked.receipt_id:
            raise ContractViolation(
                "reconcile_unknown_receipt",
                detail={"receipt_id": getattr(prior, "receipt_id", None)},
            )
        pending = self._pending_graph.get(prior.receipt_id)
        if pending is None:  # pragma: no cover - defensive
            raise ContractViolation(
                "reconcile_context_missing",
                detail={"receipt_id": prior.receipt_id},
            )
        base = prior
        if pending.adapter_unknown:
            base = self._public.reconcile(prior)
            if base.status is Status.unavailable:
                return base
            if base.status is not Status.ok:
                self._clear(prior.receipt_id)
                return base

        status, rule, detail, readback_status = self._verify_pending(pending)
        evidence = dict(base.evidence)
        receipt_id = "gxo_res_" + secrets.token_hex(6)
        evidence["receipt_id"] = receipt_id
        evidence["finished_at"] = _now()
        evidence["reconciled_from"] = prior.receipt_id
        evidence["reconcile"] = True
        workflow_v4 = dict(evidence.get("workflow_v4") or {})
        workflow_v4.update(
            {
                "operation": pending.kind,
                "workflow_id": pending.workflow_id,
                "reconcile_status": status.value,
                "readback_status": readback_status,
            }
        )
        workflow_v4.update(dict(detail or {}))
        evidence["workflow_v4"] = workflow_v4
        error = None
        if status is not Status.ok:
            error = {"rule": rule or "reconcile_failed"}
            error.update(dict(detail or {}))
        result = replace(
            base, status=status, receipt_id=receipt_id, error=error, evidence=evidence
        )
        if status is not Status.unavailable:
            self._clear(prior.receipt_id)
        return result

    def _verify_pending(
        self, pending: _PendingGraph
    ) -> tuple[Status, str | None, Mapping[str, Any], str | None]:
        if pending.kind == "create":
            if not pending.name:
                return Status.unavailable, "create_name_unknown", {}, None
            listed, found, readable = self._find_workflow_by_name(
                tenant=pending.tenant, name=pending.name, attempt=pending.attempt
            )
            if listed.status is not Status.ok:
                return (
                    Status.unavailable,
                    "reconcile_read_unavailable",
                    {"read_status": listed.status.value},
                    None,
                )
            if not readable:
                return Status.unavailable, "reconcile_list_unreadable", {}, None
            if found is None:
                return (
                    Status.not_found,
                    "reconcile_not_created",
                    {"readback": LIST_OPERATION},
                    "absent",
                )
            return (
                Status.ok,
                None,
                {
                    "workflow_id": _first(found.get("id"), found.get("_id")),
                    "readback": LIST_OPERATION,
                },
                "verified",
            )

        if pending.kind in ("update", "status.change", "restore"):
            if not pending.workflow_id:
                return Status.unavailable, "reconcile_workflow_unknown", {}, None
            verify, payload = self.read_definition_document(
                tenant=pending.tenant,
                workflow_id=pending.workflow_id,
                attempt=pending.attempt,
            )
            if verify.status is Status.not_found:
                return Status.not_found, "reconcile_write_not_landed", {}, "absent"
            if verify.status is not Status.ok:
                return (
                    Status.unavailable,
                    "reconcile_read_unavailable",
                    {"read_status": verify.status.value},
                    None,
                )
            if pending.kind == "status.change":
                observed = _status_of(payload)
                if observed != pending.target_status:
                    return (
                        Status.conflict,
                        "reconcile_status_mismatch",
                        {"observed": observed, "target": pending.target_status},
                        "mismatch",
                    )
                return Status.ok, None, {"status": observed}, "verified"
            read_back = extract_definition(payload)
            if read_back is None:
                return (
                    Status.unavailable,
                    "reconcile_definition_unreadable",
                    {},
                    "unreadable",
                )
            if pending.proposed is None:  # pragma: no cover - defensive
                return Status.unavailable, "reconcile_graph_missing", {}, None
            readback_diff = diff_definition(pending.proposed, read_back)
            if not readback_diff.content_is_empty():
                return (
                    Status.conflict,
                    "reconcile_graph_mismatch",
                    {"readback_diff": readback_diff.as_evidence()},
                    "mismatch",
                )
            return (
                Status.ok,
                None,
                {"readback_diff": readback_diff.as_evidence()},
                "verified",
            )

        if pending.kind == "delete":
            if not pending.workflow_id:
                return Status.unavailable, "reconcile_workflow_unknown", {}, None
            verify = self.read_definition(
                tenant=pending.tenant,
                workflow_id=pending.workflow_id,
                attempt=pending.attempt,
            )
            if verify.status is Status.not_found:
                return Status.ok, None, {"deleted": True}, "absent"
            if verify.status is Status.ok:
                return Status.conflict, "reconcile_delete_not_landed", {}, "verified"
            return (
                Status.unavailable,
                "reconcile_read_unavailable",
                {"read_status": verify.status.value},
                None,
            )

        return Status.unavailable, "reconcile_kind_unknown", {}, None

    # ------------------------------------------------------------------
    # capability refusal and receipts
    # ------------------------------------------------------------------

    def _disabled_result(
        self,
        operation: str,
        *,
        tenant: TenantBinding,
        attempt: int,
        path_params: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> OperationResult:
        operation_id = self._require_operation(operation)
        capability = self._public.capability(operation_id, tenant=tenant.location_id)
        block = capability.activation_blocked
        return self._refusal(
            operation,
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
        operation: str,
        *,
        tenant: TenantBinding,
        status: Status,
        rule: str,
        attempt: int,
        path_params: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
        detail: Mapping[str, Any] | None = None,
        documented_http_status: int | None = None,
    ) -> OperationResult:
        """A pre-transport refusal with a real receipt."""

        operation_id = self._require_operation(operation)
        row = self._row(operation_id)
        resolved_path = _format_path(row.path_template, dict(path_params or {}))
        query = (
            {"locationId": tenant.location_id}
            if row.tenant_binding == "query.locationId"
            else {}
        )
        body_map = dict(body or {})
        fingerprint = canonical_intent(
            operation_id=operation_id,
            method=row.method,
            resolved_path=resolved_path,
            query=query,
            body=body_map,
            tenant=tenant.location_id,
            version=row.version,
        )
        return self._result_envelope(
            operation_id=operation_id,
            row=row,
            tenant=tenant,
            attempt=attempt,
            status=status,
            rule=rule,
            detail=detail,
            documented_http_status=documented_http_status,
            fingerprint=fingerprint,
            body_map=body_map,
            body=body,
            operation=operation,
            workflow_id=dict(path_params or {}).get("workflowId"),
        )

    def _refusal_from_result(
        self,
        prior: OperationResult,
        operation: str,
        *,
        tenant: TenantBinding,
        status: Status,
        rule: str,
        attempt: int,
        detail: Mapping[str, Any] | None = None,
    ) -> OperationResult:
        """Refuse a completed-but-unacceptable response with a NEW receipt."""

        evidence = dict(prior.evidence)
        receipt_id = "gxo_res_" + secrets.token_hex(6)
        evidence["receipt_id"] = receipt_id
        evidence["finished_at"] = _now()
        evidence["refused_after_transport"] = True
        workflow_v4 = dict(evidence.get("workflow_v4") or {})
        workflow_v4.update({"operation": operation, "refused": True})
        workflow_v4.update(dict(detail or {}))
        evidence["workflow_v4"] = workflow_v4
        error: dict[str, Any] = {"rule": rule}
        error.update(dict(detail or {}))
        return replace(
            prior, status=status, receipt_id=receipt_id, error=error, evidence=evidence
        )

    def _policy_result(
        self,
        operation_id: str,
        *,
        tenant: TenantBinding,
        status: Status,
        rule: str,
        detail: Mapping[str, Any] | None = None,
        attempt: int = 1,
    ) -> OperationResult:
        """An honest result for a surface with no row / no implementation."""

        fingerprint = hashlib.sha256(
            canonical_json(
                {
                    "operation_id": operation_id,
                    "tenant": tenant.location_id,
                    "rule": rule,
                    "detail": dict(detail or {}),
                }
            ).encode("utf-8")
        ).hexdigest()
        return self._result_envelope(
            operation_id=operation_id,
            row=None,
            tenant=tenant,
            attempt=attempt,
            status=status,
            rule=rule,
            detail=detail,
            documented_http_status=None,
            fingerprint=fingerprint,
            body_map={},
            body=None,
            operation=operation_id,
            workflow_id=None,
        )

    def _result_envelope(
        self,
        *,
        operation_id: str,
        row: Any,
        tenant: TenantBinding,
        attempt: int,
        status: Status,
        rule: str,
        detail: Mapping[str, Any] | None,
        documented_http_status: int | None,
        fingerprint: str,
        body_map: Mapping[str, Any],
        body: Mapping[str, Any] | None,
        operation: str,
        workflow_id: Any,
    ) -> OperationResult:
        receipt_id = "gxo_res_" + secrets.token_hex(6)
        timestamp = _now()
        auth = getattr(self._public, "_auth", None)  # ponytail: see module note
        auth_kind = getattr(getattr(auth, "kind", None), "value", "unavailable")
        auth_source = getattr(auth, "source", "unavailable")
        timeout_s = getattr(self._public, "_default_timeout_s", None)
        evidence: dict[str, Any] = {
            "operation_id": operation_id,
            "request_fingerprint": fingerprint,
            "http_status": None,
            "response_fingerprint": None,
            "tenant": tenant.location_id,
            "attempt": attempt,
            "readback": None,
            "receipt_id": receipt_id,
            "version_header": getattr(row, "version", None),
            "timeout_s": timeout_s,
            "adapter_version": ADAPTER_VERSION,
            "transport": "http",
            "auth_kind": auth_kind,
            "auth_source": auth_source,
            "doc_url": getattr(row, "doc_url", None),
            "doc_fetch_date": getattr(row, "doc_fetch_date", None),
            "request_bytes": len(canonical_json(dict(body_map)).encode("utf-8"))
            if body_map
            else 0,
            "started_at": timestamp,
            "finished_at": timestamp,
            "refused_before_transport": True,
            "route": "public_direct",
            "workflow_v4": {
                "operation": operation,
                "workflow_id": workflow_id,
                "reconcilable": False,
            },
        }
        if body is None:
            evidence["workflow_v4"]["body_fingerprint_basis"] = (
                "refused_before_body_built"
            )
        error: dict[str, Any] = {"rule": rule}
        if documented_http_status is not None:
            error["documented_http_status"] = documented_http_status
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
            version_header=getattr(row, "version", None),
            readback=None,
            adapter_version=ADAPTER_VERSION,
            transport="http",
            doc_url=getattr(row, "doc_url", None),
            evidence=evidence,
            error=error,
        )

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

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
        workflow_id: str | None = None,
        name: str | None = None,
        proposed: Mapping[str, Any] | None = None,
        target_status: str | None = None,
    ) -> OperationResult:
        result = self._public.call(
            operation_id=operation_id,
            tenant=tenant,
            path_params=dict(path_params or {}),
            body=body,
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
                workflow_id=workflow_id,
                name=name,
                proposed=proposed,
                target_status=target_status,
                adapter_unknown=True,
                attempt=attempt,
            )
        return result

    def _mark_unknown(
        self,
        result: OperationResult,
        *,
        kind: str,
        tenant: TenantBinding,
        workflow_id: str | None,
        rule: str,
        detail: Mapping[str, Any] | None = None,
        name: str | None = None,
        proposed: Mapping[str, Any] | None = None,
        target_status: str | None = None,
        attempt: int = 1,
    ) -> OperationResult:
        evidence = dict(result.evidence)
        workflow_v4 = dict(evidence.get("workflow_v4") or {})
        workflow_v4.update(
            {
                "operation": kind,
                "workflow_id": workflow_id,
                "reconcilable": True,
                "reconcile_rule": rule,
            }
        )
        if detail:
            workflow_v4["detail"] = dict(detail)
        evidence["workflow_v4"] = workflow_v4
        error: dict[str, Any] = {"rule": rule}
        error.update(dict(detail or {}))
        unknown = replace(
            result, status=Status.unknown_outcome, error=error, evidence=evidence
        )
        self._remember_unknown(
            unknown,
            kind=kind,
            tenant=tenant,
            workflow_id=workflow_id,
            name=name,
            proposed=proposed,
            target_status=target_status,
            adapter_unknown=False,
            attempt=attempt,
        )
        return unknown

    def _remember_unknown(
        self,
        result: OperationResult,
        *,
        kind: str,
        tenant: TenantBinding,
        workflow_id: str | None,
        name: str | None,
        proposed: Mapping[str, Any] | None,
        target_status: str | None,
        adapter_unknown: bool,
        attempt: int = 1,
    ) -> None:
        self._pending_graph[result.receipt_id] = _PendingGraph(
            kind=kind,
            tenant=tenant,
            workflow_id=workflow_id,
            name=name,
            proposed=proposed,
            target_status=target_status,
            attempt=attempt or result.attempt,
            adapter_unknown=adapter_unknown,
        )
        self._unreconciled = result

    def _clear(self, receipt_id: str) -> None:
        self._pending_graph.pop(receipt_id, None)
        self._unreconciled = None

    def _settle_adapter_pending(self, result: OperationResult) -> OperationResult:
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

    def _find_workflow_by_name(
        self, *, tenant: TenantBinding, name: str, attempt: int
    ) -> tuple[OperationResult, Mapping[str, Any] | None, bool]:
        mark = len(self._transport)
        result = self._public.call(
            operation_id=LIST_OPERATION, tenant=tenant, attempt=attempt
        )
        if result.status is not Status.ok:
            return result, None, False
        payload = self._response_body(mark)
        rows = _workflow_rows(payload)
        if rows is None:
            return result, None, False
        for row in rows:
            if isinstance(row, Mapping) and row.get("name") == name:
                return result, row, True
        return result, None, True

    def _enrich(
        self, result: OperationResult, workflow_v4: Mapping[str, Any]
    ) -> OperationResult:
        evidence = dict(result.evidence)
        merged = dict(evidence.get("workflow_v4") or {})
        merged.update(dict(workflow_v4))
        evidence["workflow_v4"] = merged
        evidence["finished_at"] = _now()
        return replace(result, evidence=evidence)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None and str(value).strip():
            return value
    return None


def _format_path(template: str, values: Mapping[str, str]) -> str:
    path = str(template)
    for name in _PATH_PARAM.findall(path):
        if name not in values:
            raise ContractViolation(
                "path_params_mismatch", detail={"missing": [name]}
            )
        path = path.replace("{" + name + "}", quote(str(values[name]), safe=""))
    return path


def _field(payload: Any, name: str) -> Any:
    if not isinstance(payload, Mapping):
        return None
    if name in payload:
        return payload[name]
    data = payload.get("data")
    if isinstance(data, Mapping) and name in data:
        return data[name]
    return None


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, Mapping) and isinstance(payload.get("data"), Mapping):
        return payload["data"]
    return payload


def _status_of(payload: Any) -> Any:
    value = _field(payload, "status")
    return value if isinstance(value, str) else None


def _identity_readback(workflow_id: str, *, status: str | None = None) -> ReadbackSpec:
    expect: dict[str, Any] = {"workflowId": str(workflow_id)}
    if status is not None:
        expect["status"] = str(status)
    return ReadbackSpec(
        operation_id=READ_OPERATION,
        target_params={"workflowId": str(workflow_id)},
        expect=expect,
        description="the read-back must return this workflow id",
    )


def _step_type_rows(payload: Any) -> list[Any] | None:
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, Mapping):
        for key in _STEP_TYPE_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return list(value)
            if isinstance(value, Mapping):
                inner = value.get("stepTypes") or value.get("items")
                if isinstance(inner, list):
                    return list(inner)
    return None


def _step_type_identity(node: Any) -> str | None:
    if not isinstance(node, Mapping):
        return None
    for name in ("type", "key", "id", "slug", "name"):
        value = node.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _asset_references(node: Any, identity: str) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if not isinstance(node, Mapping):
        return refs
    value = node.get("assetReferences")
    if not isinstance(value, (list, tuple)):
        return refs
    for entry in value:
        if isinstance(entry, Mapping):
            refs.append(
                {
                    "step_type": identity,
                    "reference": {
                        str(key): str(item)
                        for key, item in entry.items()
                        if key in ("field", "type", "assetType", "required", "name")
                    },
                }
            )
        else:
            refs.append({"step_type": identity, "reference": {"type": str(entry)}})
    return refs


def _continuation_token(payload: Any) -> tuple[dict[str, Any] | None, str]:
    """Return ``(query, shape)`` for the next page.

    ``shape`` is ``"none"`` (no token), ``"token"`` (carry it back verbatim) or
    ``"unresolved"`` (a continuation is advertised in a shape this adapter
    cannot carry without inventing a request parameter).
    """

    if not isinstance(payload, Mapping):
        return None, "none"
    for key in _CONTINUATION_KEYS:
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            text = str(value).strip()
            if text:
                return {key: text}, "token"
        if value is None or value is False or value == "":
            continue
        return None, "unresolved"
    meta = payload.get("meta")
    if isinstance(meta, Mapping):
        for key in _CONTINUATION_KEYS:
            value = meta.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                if str(value).strip():
                    return None, "unresolved"
    return None, "none"


def _required_schema_fields(schema: Mapping[str, Any]) -> list[str]:
    fields: list[str] = []
    raw = schema.get("fields")
    if isinstance(raw, (list, tuple)):
        for entry in raw:
            if not isinstance(entry, Mapping):
                continue
            if entry.get("required") is not True:
                continue
            name = entry.get("name") or entry.get("key")
            if isinstance(name, str) and name.strip():
                fields.append(name.strip())
    required = schema.get("requiredFields")
    if isinstance(required, (list, tuple)):
        for name in required:
            if isinstance(name, str) and name.strip():
                fields.append(name.strip())
    return sorted(set(fields))


def _issue_list(body: Any, name: str) -> list[Any]:
    if not isinstance(body, Mapping):
        return []
    value = body.get(name)
    return list(value) if isinstance(value, (list, tuple)) else []


def _issue_summary(item: Any) -> dict[str, Any]:
    if isinstance(item, Mapping):
        return {
            str(key): str(item[key])
            for key in ("code", "type", "path", "field", "message")
            if key in item and isinstance(item[key], (str, int, float))
        }
    return {"message": str(item)}


def _noop_warning(item: Any) -> bool:
    text = canonical_json(_issue_summary(item)).lower()
    return any(marker in text for marker in _NOOP_WARNING_MARKERS)


def _mentions_stale_revision(body: Any, _depth: int = 0) -> bool:
    if _depth > 4:
        return False
    if isinstance(body, Mapping):
        for key in ("code", "error", "rule", "type", "message", "detail", "errors"):
            value = body.get(key)
            if isinstance(value, str):
                lowered = value.lower().replace("-", "_").replace(" ", "_")
                if any(marker.replace(" ", "_") in lowered for marker in _STALE_MARKERS):
                    return True
            elif isinstance(value, Mapping):
                if _mentions_stale_revision(value, _depth + 1):
                    return True
            elif isinstance(value, list):
                if any(_mentions_stale_revision(item, _depth + 1) for item in value):
                    return True
    elif isinstance(body, list):
        return any(_mentions_stale_revision(item, _depth + 1) for item in body)
    return False


def _unresolved_assets(
    step_types: Mapping[str, Any] | None,
    body: Mapping[str, Any],
    resolved: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Asset ids the catalog references that the caller has not resolved."""

    if not step_types:
        return []
    resolved_set = {str(item) for item in resolved}
    missing: list[dict[str, Any]] = []
    for kind in ("actions", "triggers"):
        nodes = body.get(kind)
        if not isinstance(nodes, (list, tuple)):
            continue
        for node in nodes:
            identity = _step_type_identity(node)
            schema = step_types.get(identity) if identity else None
            if not isinstance(schema, Mapping):
                continue
            for ref in _asset_references(schema, str(identity)):
                field = ref["reference"].get("field")
                if not field:
                    continue
                value = node.get(field)
                if value is None:
                    missing.append(
                        {"step_type": identity, "field": field, "reason": "missing"}
                    )
                elif str(value) not in resolved_set:
                    missing.append(
                        {
                            "step_type": identity,
                            "field": field,
                            "reason": "unresolved_reference",
                        }
                    )
    return missing


def _create_body(
    definition: Mapping[str, Any],
    folder: Mapping[str, Any] | None,
    *,
    folder_path_max_depth: int | None = None,
) -> dict[str, Any]:
    if not isinstance(definition, Mapping):
        raise ContractViolation("definition_invalid")
    body = dict(definition)
    if "version" in body:
        raise ContractViolation("create_must_omit_revision")
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ContractViolation("create_name_required")
    if folder is not None:
        if not isinstance(folder, Mapping):
            raise ContractViolation("create_folder_invalid")
        allowed = frozenset({"folderName", "folderPath", "createFolderIfMissing"})
        unknown = sorted(str(key) for key in folder if str(key) not in allowed)
        if unknown:
            raise ContractViolation(
                "create_folder_field_unknown", detail={"fields": unknown}
            )
        has_name = "folderName" in folder
        has_path = "folderPath" in folder
        if has_name and has_path:
            raise ContractViolation(
                "folder_name_and_path_exclusive",
                detail={"fields": ["folderName", "folderPath"]},
            )
        flag = folder.get("createFolderIfMissing")
        if flag is not None and not isinstance(flag, bool):
            raise ContractViolation(
                "create_folder_if_missing_invalid",
                detail={"type": type(flag).__name__},
            )
        path = folder.get("folderPath")
        if path is not None:
            if not isinstance(path, str) or not path.strip():
                raise ContractViolation("folder_path_invalid")
            segments = [part for part in path.split("/") if part.strip()]
            if folder_path_max_depth is not None and (
                len(segments) > int(folder_path_max_depth)
            ):
                raise ContractViolation(
                    "folder_path_depth_exceeded",
                    detail={
                        "depth": len(segments),
                        "limit": int(folder_path_max_depth),
                    },
                )
        body.update(dict(folder))
    return body


def _workflow_rows(payload: Any) -> list[Any] | None:
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, Mapping):
        for key in ("workflows", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return list(value)
            if isinstance(value, Mapping):
                inner = value.get("workflows")
                if isinstance(inner, list):
                    return list(inner)
    return None


_PUBLICATION_SCOPE_VALUES = frozenset({"publication", "publish", "live"})
_PUBLICATION_MARKERS: tuple[str, ...] = (
    "publication-scoped",
    "publication_scoped",
    "scope:publication",
    "scope=publication",
    "scope:publish",
    "scope=publish",
    "scope:live",
    "scope=live",
    "allow-publication",
    "allow_publication",
    "allow-publish",
    "allow_publish",
    "approved_live_publication",
)


def _approval_text(
    approval: ApprovalRef | Mapping[str, Any] | str,
) -> tuple[str, str]:
    if isinstance(approval, ApprovalRef):
        return str(approval.ref), ""
    if isinstance(approval, Mapping):
        return str(approval.get("ref") or ""), str(approval.get("scope") or "")
    if isinstance(approval, str):
        return approval, ""
    return "", ""


def _publication_scope(approval: ApprovalRef | Mapping[str, Any] | str) -> bool:
    """True only for an approval that explicitly names a PUBLICATION scope."""

    ref, scope = _approval_text(approval)
    if scope.strip().lower().rstrip("s") in _PUBLICATION_SCOPE_VALUES:
        return True
    lowered = ref.lower()
    return any(marker in lowered for marker in _PUBLICATION_MARKERS)


def _deletion_scope(approval: ApprovalRef | Mapping[str, Any] | str) -> bool:
    """True only for an approval that is explicitly deletion-scoped."""

    ref, scope = _approval_text(approval)
    if scope.strip().lower().rstrip("s") == "deletion":
        return True
    lowered = ref.lower()
    return any(
        marker in lowered
        for marker in (
            "deletion-scoped",
            "deletion_scoped",
            "scope:deletion",
            "scope=deletion",
            "scope:delete",
            "scope=delete",
            "allow-deletion",
            "allow_deletion",
            "allow-delete",
            "allow_delete",
        )
    )


__all__ = [
    "NONE",
    "OPERATION_MAP",
    "GAP_RULES",
    "WorkflowGap",
    "WorkflowRowMissing",
    "RecordingTransport",
    "TransportRecord",
    "WorkflowV4Adapter",
    "validate_operation_map",
    "READ_OPERATION",
    "CREATE_OPERATION",
    "UPDATE_OPERATION",
    "STATUS_OPERATION",
    "DELETE_OPERATION",
    "LIST_OPERATION",
    "STEP_TYPES_OPERATION",
    "VALIDATE_OPERATION",
    "SEARCH_OPERATION",
    "LOGS_LIST_OPERATION",
    "LOGS_AGGREGATE_OPERATION",
]
