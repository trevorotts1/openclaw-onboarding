"""V4 workflow adapter over the frozen public adapter.

Frozen by the GHL modernization contract ledger, 2026-10-18 (GU-004 sections
1.1, 2.4, 3.2 rule 4 and 5.7, plus the workflows family record WF-04 .. WF-09).
V4 scope and Version come from the official workflows operation page
https://marketplace.gohighlevel.com/docs/ghl/workflows/<operation-slug>/.

Every V4 operation is capability-gated and default-deny.  No write can reach
transport while its capability row is disabled, and a disabled call still
returns a receipt.  There is no route switch: this module never imports the
Skill44 private client, never falls back to a browser transport, and never
retries by itself.

Required algorithm for a definition update (freeze 2.4):

    authorized draft transition when needed
    -> read the CURRENT COMPLETE definition
    -> apply the approved intent
    -> write the COMPLETE preserved graph with the exact opaque revision
    -> read back the affected graph
    -> emit receipt evidence

Publish (``workflows.status.publish``) is a separate authorization.  It is
never automatic, and a published workflow is never silently demoted: a 409 or
a published read produces a conflict, not an unpublish.

Gaps: the freeze has no row for a validation read or for restore.  Both are
recorded as ``NONE`` below and raise a named ``WorkflowGap`` instead of an
invented endpoint.

The frozen result envelope carries no response body (result.py 2.2), so this
module reads the graph through a recording wrapper around the same transport
the public adapter uses.  Recorded bytes stay in memory; they never enter an
envelope.  ``ponytail`` -- the public adapter has no transport accessor; if W04
adds one, drop the guarded private fallback in ``__init__``.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import quote

from .adapter import ApprovalRef, PublicGhlAdapter
from .auth import TenantBinding
from .capability import Capability
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
    revision_equals,
)

# ---------------------------------------------------------------------------
# operation map (freeze 5.7).  ``NONE`` is the freeze's "no row" marker.
# ---------------------------------------------------------------------------

NONE: None = None

READ_OPERATION = "workflows.definition.read"
CREATE_OPERATION = "workflows.definition.create"
UPDATE_OPERATION = "workflows.definition.update"
STATUS_OPERATION = "workflows.status.publish"
DELETE_OPERATION = "workflows.definition.delete"
LIST_OPERATION = "workflows.list"

OPERATION_MAP: dict[str, str | None] = {
    "definition.read": READ_OPERATION,
    "validation.read": NONE,
    "create": CREATE_OPERATION,
    "update": UPDATE_OPERATION,
    "status.read": READ_OPERATION,
    "status.change": STATUS_OPERATION,
    "delete": DELETE_OPERATION,
    "restore": NONE,
}

# Named gaps: rule code -> (what is missing, evidence that would settle it).
GAP_RULES: dict[str, tuple[str, str]] = {
    "validation.read": (
        "workflow_validation_read_has_no_documented_operation",
        "an official production or staging operation page for a definition "
        "validation read, or an authorized describe_operation capture; until "
        "then the only validation evidence is the warnings[] returned by "
        "definition.read and the 422 on update",
    ),
    "restore": (
        "workflow_restore_has_no_documented_operation",
        "an official operation page or an authorized describe_operation "
        "capture; freeze 5.7 records workflows.restore as a capability gap "
        "(B-RESTORE-NONE) and restore is a fresh approved update, never a "
        "stale-wire replay",
    ),
}

_WRITE_KEYS: tuple[str, ...] = ("create", "update", "status.change", "delete", "restore")
_PATH_PARAM = re.compile(r"\{([^{}]+)\}")
_DOCUMENTED_STATUSES: frozenset[str] = frozenset({"draft", "published"})


class WorkflowGap(ContractViolation):
    """A V4 operation has no frozen row.  Named, never invented."""

    rule = "workflow_operation_gap"


def _validate_operation_map() -> None:
    for key, operation_id in OPERATION_MAP.items():
        is_write = key in _WRITE_KEYS
        if operation_id is None:
            if key not in GAP_RULES:
                raise ContractViolation("v4_gap_unnamed", operation_id=key)
            continue
        if key in GAP_RULES:
            raise ContractViolation("v4_gap_has_row", operation_id=key)
        if operation_id not in OPERATIONS:
            raise ContractViolation(
                "v4_row_missing",
                operation_id=operation_id,
                detail={"mapping": key},
            )
        row = OPERATIONS[operation_id]
        if bool(row.write) != is_write:
            raise ContractViolation(
                "v4_row_write_mismatch",
                operation_id=operation_id,
                detail={"mapping": key},
            )
        if row.version != "v4":
            raise ContractViolation(
                "v4_row_version_mismatch",
                operation_id=operation_id,
                detail={"version": row.version},
            )


_validate_operation_map()


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


# ---------------------------------------------------------------------------
# the adapter
# ---------------------------------------------------------------------------


class WorkflowV4Adapter:
    """V4 definition/publish/delete surface, disabled by default.

    Constructed over an existing ``PublicGhlAdapter``; every call goes through
    ``PublicGhlAdapter.call`` so the capability gate, tenant binding, approval
    and receipt rules are the frozen ones.
    """

    def __init__(
        self, *, public: PublicGhlAdapter, transport: Transport | None = None
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
        self._unreconciled: OperationResult | None = None
        self._pending_graph: dict[str, _PendingGraph] = {}

    # ------------------------------------------------------------------
    # operation map and capability
    # ------------------------------------------------------------------

    def _require_operation(self, operation: str) -> str:
        key = str(operation)
        if key in GAP_RULES:
            rule, unblock = GAP_RULES[key]
            raise WorkflowGap(
                rule,
                operation_id=key,
                detail={"unblock": unblock},
            )
        operation_id = OPERATION_MAP.get(key)
        if operation_id is None:
            raise WorkflowGap(
                "workflow_operation_gap_unnamed",
                operation_id=key,
                detail={"unblock": "name the operation and its frozen row"},
            )
        return operation_id

    def capability(self, operation: str) -> Capability:
        return self._public.capability(self._require_operation(operation))

    def _enabled(self, operation_id: str) -> bool:
        return bool(self._public.capability(operation_id).enabled)

    # ------------------------------------------------------------------
    # reads
    # ------------------------------------------------------------------

    def read_definition(
        self,
        *,
        tenant: TenantBinding,
        workflow_id: str,
        attempt: int = 1,
    ) -> OperationResult:
        """Read the current definition (capability-gated; no body in envelope)."""

        return self._public.call(
            operation_id=self._require_operation("definition.read"),
            tenant=tenant,
            path_params={"workflowId": workflow_id},
            attempt=attempt,
        )

    def read_definition_document(
        self,
        *,
        tenant: TenantBinding,
        workflow_id: str,
        attempt: int = 1,
    ) -> tuple[OperationResult, Any]:
        """Read the definition and return ``(envelope, parsed payload)``.

        The payload is in-memory only; it is never placed in evidence.  It is
        ``None`` whenever the envelope is not ``ok`` or the body is unreadable.
        """

        mark = len(self._transport)
        result = self.read_definition(
            tenant=tenant, workflow_id=workflow_id, attempt=attempt
        )
        if result.status is not Status.ok:
            return result, None
        return result, self._response_body(mark)

    def read_status(
        self,
        *,
        tenant: TenantBinding,
        workflow_id: str,
        attempt: int = 1,
    ) -> OperationResult:
        """Read current status; the definition read returns ``status`` too."""

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
        """Named gap: no documented validation-read operation exists."""

        raise WorkflowGap(
            GAP_RULES["validation.read"][0],
            operation_id="validation.read",
            detail={"unblock": GAP_RULES["validation.read"][1]},
        )

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
    ) -> OperationResult:
        """Create a workflow.  Always draft; duplicate create is reconciled by
        a ``GET /workflows/`` name search, never by a blind retry."""

        self._guard()
        key = "create"
        operation_id = self._require_operation(key)
        if not self._enabled(operation_id):
            return self._disabled_result(key, tenant=tenant, attempt=attempt)
        body = _create_body(definition, folder)

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
            # The frozen read-back matcher is shallow (root, or one level
            # under ``data``), while the documented list envelopes carry the
            # rows under ``workflows`` or as a bare array -- deeper than it
            # can see.  A landed create therefore reads as ``mismatch`` on
            # those shapes.  The name search below is the shape-tolerant
            # authority for exactly this check (GU-003 WF-05: duplicate
            # create reconciles by name search), so it decides -- never the
            # shallow verdict, and never in the create's favour on its own:
            # if the name is absent there the outcome is still unknown.
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
        return self._enrich(
            result,
            {
                "operation": key,
                "workflow_id": _first(found.get("id"), found.get("_id")),
                "status": "draft",
                "readback": LIST_OPERATION,
                "readback_matched_by": "name",
            },
        )

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
    ) -> OperationResult:
        """Complete-replacement update driven by an approved intent.

        ``expected_revision`` is REQUIRED and is an exact opaque value: the
        caller must echo the revision it actually read (the shipped CLI passes
        ``extract_revision`` of the payload it already holds), so the 422
        ``stale_revision`` branch is reachable from every caller.  Omitting it
        is a ``ContractViolation`` raised before any transport call; a mismatch
        refuses before transport.

        A graph whose application would DELETE any node also refuses before
        transport unless ``allow_deletions`` is set (see
        ``_deletion_scope``): omission must never read as an approved removal.

        A published workflow refuses with conflict unless
        ``allow_draft_transition`` plus a separate ``draft_transition_approval``
        authorize the draft move.  Publish is never triggered here.
        """

        self._guard()
        key = "update"
        operation_id = self._require_operation(key)
        path_params = {"workflowId": workflow_id}
        if not self._enabled(operation_id):
            return self._disabled_result(
                key, tenant=tenant, attempt=attempt, path_params=path_params
            )
        # MAJOR C: a missing revision is a contract break, not a default.  The
        # gate answers first so a disabled capability still refuses as itself.
        if expected_revision is None:
            raise ContractViolation(
                "expected_revision_required",
                operation_id=operation_id,
                detail={"reason": "the caller must echo the revision it read"},
            )

        # 1. current complete definition and status
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

        # 2. revision discipline -- decided on the revision the CALLER read,
        #    i.e. before any status change can move it.  This is what makes the
        #    documented 422 branch reachable from the shipped verb.
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
            # A status change advances the revision: fresh read before any write.
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

        # 3. apply the approved intent to the complete graph
        proposed = apply_intent(definition, intent)

        # 4. deletion scope -- decided HERE, after the apply and BEFORE the
        #    write, so an omitted node is refused at the decision point instead
        #    of being applied first.  Omission is never an approved removal.
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

        # 5. the write carries the CURRENT system-owned revision: a draft
        #    transition above already advanced it past the caller's echo, so
        #    re-extract it from the graph that is actually being written.
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

        # 6. write the complete preserved graph with the exact revision
        readback = _identity_readback(workflow_id)
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
        if write.status is not Status.ok:
            return write

        # 5. read back the affected graph
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
            },
        )

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
        """Change status.  The only literals are the documented ``published``
        and ``draft``.  The status change advances the revision, so a fresh
        read follows it before any further write."""

        self._guard()
        key = "status.change"
        operation_id = self._require_operation(key)
        path_params = {"workflowId": workflow_id}
        if not self._enabled(operation_id):
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

        # The status change is the one write whose result is carried at the
        # root of the definition read (GU-003 WF-07: ``workflowId``,
        # ``status``), so the read-back asserts the write is reflected too.
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

        # Fresh read: the revision moved, so nothing may write until we see it.
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
        """Separate authorization; never called automatically."""

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
        """Explicit status change to ``draft``."""

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
        """Permanent delete, explicit intent only.

        A fresh snapshot is taken and fingerprinted before the call.  The
        delete is proven by a follow-up definition read returning 404.
        """

        self._guard()
        key = "delete"
        operation_id = self._require_operation(key)
        path_params = {"workflowId": workflow_id}
        if not self._enabled(operation_id):
            return self._disabled_result(
                key, tenant=tenant, attempt=attempt, path_params=path_params
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

        # A delete's read-back is inverted: 404 answers ``absent`` BEFORE the
        # expectation is consulted, so ``verified`` would mean the workflow
        # SURVIVED, and ``absent`` is the proof it is gone -- the same 404 the
        # follow-up definition read demands.  The adapter maps every
        # non-verified read-back to ``unknown_outcome``; for this operation
        # only, ``absent`` is the success signal.  Any other verdict stands:
        # ``mismatch`` (some other document came back) and ``unreadable``
        # (nothing was proven) are never a delete.
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
            # Settle the adapter's pending row through the same read-back row
            # (reconcile re-reads; it never re-issues the DELETE).  The
            # follow-up definition read below stays the authority on whether
            # the workflow is really gone.
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
            },
        )

    def restore_workflow(
        self, *, tenant: TenantBinding, workflow_id: str, attempt: int = 1
    ) -> OperationResult:
        """Named gap: no documented restore operation (freeze B-RESTORE-NONE)."""

        raise WorkflowGap(
            GAP_RULES["restore"][0],
            operation_id="restore",
            detail={"unblock": GAP_RULES["restore"][1]},
        )

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

        if pending.kind in ("update", "status.change"):
            if not pending.workflow_id:
                return (
                    Status.unavailable,
                    "reconcile_workflow_unknown",
                    {},
                    None,
                )
            verify, payload = self.read_definition_document(
                tenant=pending.tenant,
                workflow_id=pending.workflow_id,
                attempt=pending.attempt,
            )
            if verify.status is Status.not_found:
                return (
                    Status.not_found,
                    "reconcile_write_not_landed",
                    {},
                    "absent",
                )
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
                return (
                    Status.unavailable,
                    "reconcile_graph_missing",
                    {},
                    None,
                )
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
                return (
                    Status.unavailable,
                    "reconcile_workflow_unknown",
                    {},
                    None,
                )
            verify = self.read_definition(
                tenant=pending.tenant,
                workflow_id=pending.workflow_id,
                attempt=pending.attempt,
            )
            if verify.status is Status.not_found:
                return Status.ok, None, {"deleted": True}, "absent"
            if verify.status is Status.ok:
                return (
                    Status.conflict,
                    "reconcile_delete_not_landed",
                    {},
                    "verified",
                )
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
        capability = self._public.capability(operation_id)
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
        """A pre-transport refusal with a real receipt (freeze 3.2 rule 7)."""

        operation_id = self._require_operation(operation)
        row = OPERATIONS[operation_id]
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
            "version_header": row.version,
            "timeout_s": timeout_s,
            "adapter_version": ADAPTER_VERSION,
            "transport": "http",
            "auth_kind": auth_kind,
            "auth_source": auth_source,
            "doc_url": row.doc_url,
            "doc_fetch_date": row.doc_fetch_date,
            "request_bytes": len(canonical_json(body_map).encode("utf-8"))
            if body_map
            else 0,
            "started_at": timestamp,
            "finished_at": timestamp,
            "refused_before_transport": True,
            "route": "public_direct",
            "workflow_v4": {
                "operation": operation,
                "workflow_id": dict(path_params or {}).get("workflowId"),
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
            version_header=row.version,
            readback=None,
            adapter_version=ADAPTER_VERSION,
            transport="http",
            doc_url=row.doc_url,
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
        """Free the adapter's pending row for a write whose read-back verdict
        this operation overrides.

        The adapter holds an unknown-outcome write until ``reconcile()`` frees
        it, and ``reconcile()`` re-reads through the same read-back row -- it
        never re-issues the write.  Its verdict is the caller's to interpret,
        so it is returned; only the side effect (the pending row) is wanted
        here.
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
    import hashlib

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


def _status_of(payload: Any) -> Any:
    value = _field(payload, "status")
    return value if isinstance(value, str) else None

def _identity_readback(
    workflow_id: str, *, status: str | None = None
) -> ReadbackSpec:
    """Read-back expectation for a write to ONE workflow.

    GU-003 WF-04/WF-07 document ``workflowId`` (and, for the status change,
    ``status``) as root fields of the definition read, so the read-back proves
    the read returned THIS workflow, never a stand-in.  The revision is not
    asserted here: it lives one level down (``definition.version``), deeper
    than the frozen shallow matcher reaches, and the verbs that write it
    already re-read the complete graph and diff it against what they wrote.
    """

    expect: dict[str, Any] = {"workflowId": str(workflow_id)}
    if status is not None:
        expect["status"] = str(status)
    return ReadbackSpec(
        operation_id=READ_OPERATION,
        target_params={"workflowId": str(workflow_id)},
        expect=expect,
        description="the read-back must return this workflow id",
    )


def _deletion_scope(approval: ApprovalRef | Mapping[str, Any] | str) -> bool:
    """True only for an approval that is explicitly deletion-scoped.

    The frozen ``ApprovalRef`` vocabulary has one ``ref`` and one ``kind`` and
    the adapter validates ``kind`` against it, so scope travels as text: an
    explicit ``scope`` key on a mapping, or a scope marker inside ``ref``.  A
    marker must be present -- an absent marker never authorises a removal, and
    a word that merely mentions "delete" (a delete-record ref) is not one.
    """

    ref: str = ""
    scope: str = ""
    if isinstance(approval, ApprovalRef):
        ref = str(approval.ref)
    elif isinstance(approval, Mapping):
        ref = str(approval.get("ref") or "")
        scope = str(approval.get("scope") or "")
    elif isinstance(approval, str):
        ref = approval
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


def _workflow_rows(payload: Any) -> list[Any] | None:
    """Workflow rows from the list payload, or ``None`` if unreadable.

    GU-003 records ``{workflows: []}`` and a bare array as observed shapes; the
    ``data`` envelope is tolerated because the rest of the adapter does.  An
    unrecognised shape is unreadable, never "empty".
    """

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


def _create_body(
    definition: Mapping[str, Any], folder: Mapping[str, Any] | None
) -> dict[str, Any]:
    if not isinstance(definition, Mapping):
        raise ContractViolation("definition_invalid")
    body = dict(definition)
    if "version" in body:
        # WF-05: the staging create body omits version; the server owns it.
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
        body.update(dict(folder))
    return body


__all__ = [
    "NONE",
    "OPERATION_MAP",
    "GAP_RULES",
    "WorkflowGap",
    "RecordingTransport",
    "TransportRecord",
    "WorkflowV4Adapter",
]
