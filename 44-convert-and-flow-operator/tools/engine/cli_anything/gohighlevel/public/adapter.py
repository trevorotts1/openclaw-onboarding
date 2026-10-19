"""The only public-REST entry point.

Frozen by the GHL modernization contract ledger, 2026-10-18 (GU-004 sections
1.2-1.4, 2.3-2.4, 3.2 rule 7). Operation scope and the per-operation Version come
from the official operation page https://marketplace.gohighlevel.com/docs/ghl/<module>/<operation-slug>/.

Binding order before any network call: operation row, path params, tenant
binding, auth class, idempotency, approval, readback plan, capability gate.
Nothing here supplies a default version: the version travels per operation from
the registry row.  Nothing here retries: a retry is a new ``call`` and is
refused while an unreconciled ``unknown_outcome`` exists.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote

from .auth import AuthContext, AuthKind, TenantBinding, auth_headers
from .capability import (
    DEFAULT_BLOCK,
    ActivationBlock,
    Capability,
    CapabilityGate,
    load_capability_record,
)
from .errors import ContractViolation, CredentialMissing, ReconciliationRequired
from .idempotency import IdempotencyKey, IdempotencyLedger, canonical_intent
from .readback import (
    READBACKS,
    ReadbackRegistry,
    ReadbackResult,
    ReadbackSpec,
    ReadbackStatus,
    evaluate_readback,
)
from .result import (
    ADAPTER_VERSION,
    OperationResult,
    Status,
    canonical_json,
    redact_headers,
    response_fingerprint,
)
from .transport import RequestsTransport, Transport, TransportResponse

try:  # registry lane provides the frozen rows
    from .operations import OPERATIONS, OperationRegistry
except ModuleNotFoundError as _missing:  # pragma: no cover - pre-merge bridge
    if not str(_missing.name or "").endswith("operations"):
        raise
    # The registry module has not landed yet.  Every operation id is unknown,
    # which refuses loudly; no row is ever guessed and no version is invented.
    OPERATIONS: Mapping[str, Any] = {}
    OperationRegistry = Mapping  # type: ignore[assignment,misc]

_PATH_PARAM = re.compile(r"\{([^{}]+)\}")
_MISSING = object()
_APPROVAL_RECORD = "approval_record"
_APPROVAL_TOKEN = "gate_token"
_PENDING_LIMIT = 1024
_GATE_SKIPPED_ROUTES = frozenset({"skill44_private"})


@dataclass(frozen=True)
class ApprovalRef:
    """Existing seam vocabulary; the value is never recorded."""

    ref: str
    kind: str = _APPROVAL_RECORD

    def __post_init__(self) -> None:
        if self.kind not in (_APPROVAL_RECORD, _APPROVAL_TOKEN):
            raise ContractViolation("approval_kind_invalid")
        if not isinstance(self.ref, str) or not self.ref.strip():
            raise ContractViolation("approval_invalid", detail={"reason": "empty_ref"})


@dataclass(frozen=True)
class _PendingWrite:
    operation_id: str
    receipt_id: str
    request_fingerprint: str
    idempotency_key: str | None
    tenant: TenantBinding
    readback_spec: ReadbackSpec
    attempt: int
    version: str | None
    doc_url: str | None
    doc_fetch_date: str | None


class _Refusal(Exception):
    def __init__(
        self,
        rule: str,
        status: Status = Status.denied,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        self.rule = rule
        self.status = status
        self.detail = dict(detail or {})
        super().__init__(rule)


class PublicGhlAdapter:
    def __init__(
        self,
        *,
        auth: AuthContext,
        operations: "OperationRegistry" = OPERATIONS,
        transport: Transport | None = None,
        capability: CapabilityGate | None = None,
        capability_record: str | Path | None = None,
        readbacks: ReadbackRegistry = READBACKS,
        default_timeout_s: float = 30.0,
        max_attempts: int = 1,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if auth is None:
            raise ContractViolation("auth_required")
        if not isinstance(auth, AuthContext):
            raise ContractViolation("auth_invalid")
        if not isinstance(max_attempts, int) or max_attempts < 1:
            raise ContractViolation("max_attempts_invalid")
        if float(default_timeout_s) <= 0:
            raise ContractViolation("timeout_invalid")

        self._auth = auth
        self._operations = operations
        self._transport: Transport = transport if transport is not None else RequestsTransport()
        # An explicit gate always wins.  Otherwise the checked-in capability
        # record is loaded per call tenant; no file still means default-deny.
        self._capability = capability
        self._capability_record = capability_record
        self._record_gates: dict[str, CapabilityGate] = {}
        self._readbacks = readbacks if readbacks is not None else ReadbackRegistry()
        self._default_timeout_s = float(default_timeout_s)
        self._max_attempts = int(max_attempts)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._ledger = IdempotencyLedger()
        self._pending: dict[str, _PendingWrite] = {}
        self._pending_by_key: dict[tuple[str, str], _PendingWrite] = {}

    # ------------------------------------------------------------------
    # public surface
    # ------------------------------------------------------------------

    def call(
        self,
        *,
        operation_id: str,
        tenant: TenantBinding,
        path_params: Mapping[str, str] | None = None,
        query: Mapping[str, object] | None = None,
        body: Mapping[str, object] | None = None,
        idempotency_key: str | None = None,
        approval: ApprovalRef | Mapping[str, Any] | str | None = None,
        readback: ReadbackSpec | None = None,
        timeout_s: float | None = None,
        attempt: int = 1,
    ) -> OperationResult:
        started = self._clock()

        if not isinstance(tenant, TenantBinding):
            raise ContractViolation("tenant_required")
        if not isinstance(attempt, int) or attempt < 1:
            raise ContractViolation("attempt_invalid")
        timeout = (
            self._default_timeout_s if timeout_s is None else float(timeout_s)
        )
        if timeout <= 0:
            raise ContractViolation("timeout_invalid")

        row = self._resolve_row(operation_id)
        method = _row_attr(row, "method")
        template = _row_attr(row, "path_template")
        version = _row_attr(row, "version", _MISSING)
        write = bool(_row_attr(row, "write", False))
        approval_required = bool(_row_attr(row, "approval_required", False))
        route_class = _row_attr(row, "route_class")
        doc_url = _row_attr(row, "doc_url")
        doc_fetch_date = _row_attr(row, "doc_fetch_date")
        auth_kinds = tuple(_row_attr(row, "auth_kinds") or ())
        binding = _row_attr(row, "tenant_binding", "none")
        scopes = tuple(_row_attr(row, "scopes_candidate") or ())

        if not isinstance(method, str) or not method.strip():
            raise ContractViolation("row_method_missing", operation_id=operation_id)
        if not isinstance(template, str) or not template.strip():
            raise ContractViolation("row_path_missing", operation_id=operation_id)
        if version is _MISSING:
            raise ContractViolation("row_version_missing", operation_id=operation_id)
        if version is not None and not isinstance(version, str):
            raise ContractViolation("row_version_invalid", operation_id=operation_id)

        names = _PATH_PARAM.findall(template)
        provided = dict(path_params or {})
        missing = sorted(set(names) - set(provided))
        extra = sorted(set(provided) - set(names))
        if missing or extra:
            raise ContractViolation(
                "path_params_mismatch",
                operation_id=operation_id,
                detail={"missing": missing, "extra": extra},
            )
        path_values: dict[str, str] = {}
        for name in names:
            value = provided[name]
            if not isinstance(value, str) or not value:
                raise ContractViolation(
                    "path_param_invalid",
                    operation_id=operation_id,
                    detail={"name": name},
                )
            path_values[name] = value

        query_map: dict[str, Any] = dict(query or {})
        body_map: dict[str, Any] = dict(body or {})
        receipt_id = "gxo_res_" + secrets.token_hex(6)
        fingerprint_box = {"value": ""}
        request_bytes = (
            len(canonical_json(body_map).encode("utf-8")) if body_map else 0
        )

        refusal: _Refusal | None = None
        try:
            _apply_tenant_binding(
                binding,
                tenant.location_id,
                path_values,
                query_map,
                body_map,
            )
        except _Refusal as caught:
            refusal = caught

        resolved_path = _format_path(template, path_values)
        fingerprint_box["value"] = canonical_intent(
            operation_id=operation_id,
            method=method,
            resolved_path=resolved_path,
            query=query_map,
            body=body_map,
            tenant=tenant.location_id,
            version=version,
        )

        def finish(
            status: Status,
            *,
            error: Mapping[str, Any] | None = None,
            http_status: int | None = None,
            response_fp: str | None = None,
            readback_result: ReadbackResult | None = None,
            extra: Mapping[str, Any] | None = None,
        ) -> OperationResult:
            finished = self._clock()
            evidence: dict[str, Any] = {
                "operation_id": operation_id,
                "request_fingerprint": fingerprint_box["value"],
                "http_status": http_status,
                "response_fingerprint": response_fp,
                "tenant": tenant.location_id,
                "attempt": attempt,
                "readback": (
                    readback_result.result.value if readback_result else None
                ),
                "receipt_id": receipt_id,
                "version_header": version,
                "timeout_s": timeout,
                "adapter_version": ADAPTER_VERSION,
                "transport": "http",
                "auth_kind": self._auth.kind.value,
                "auth_source": self._auth.source,
                "doc_url": doc_url,
                "doc_fetch_date": doc_fetch_date,
                "request_bytes": request_bytes,
                "started_at": started.isoformat(),
                "finished_at": finished.isoformat(),
            }
            if extra:
                evidence.update(dict(extra))
            return OperationResult(
                status=status,
                operation_id=operation_id,
                receipt_id=receipt_id,
                request_fingerprint=fingerprint_box["value"],
                http_status=http_status,
                response_fingerprint=response_fp,
                tenant=tenant.location_id,
                attempt=attempt,
                version_header=version,
                readback=readback_result,
                adapter_version=ADAPTER_VERSION,
                transport="http",
                doc_url=doc_url,
                evidence=evidence,
                error=error,
            )

        if refusal is not None:
            return finish(
                refusal.status,
                error={"rule": refusal.rule, **refusal.detail},
                extra={"refused_before_transport": True},
            )

        # 4. auth context -- the four credential classes never substitute.
        allowed = [kind.value if hasattr(kind, "value") else str(kind) for kind in auth_kinds]
        if not auth_kinds or self._auth.kind.value not in allowed:
            return finish(
                Status.denied,
                error={
                    "rule": "auth_kind_not_allowed",
                    "auth_kind": self._auth.kind.value,
                    "allowed": allowed,
                },
                extra={"refused_before_transport": True},
            )

        # 5. tenant binding -- co-mingling refusal.
        if (
            self._auth.kind is AuthKind.location_pit
            and self._auth.location_id != tenant.location_id
        ):
            return finish(
                Status.denied,
                error={
                    "rule": "tenant_mismatch",
                    "hint": "tenant binding must equal the bound location",
                },
                extra={"refused_before_transport": True},
            )

        # 6. idempotency.
        key: IdempotencyKey | None = None
        if write:
            if idempotency_key is None or not str(idempotency_key).strip():
                raise ContractViolation(
                    "idempotency_key_required",
                    operation_id=operation_id,
                    detail={"write": True},
                )
            key = IdempotencyKey.parse(str(idempotency_key))
            pending = self._pending_by_key.get((operation_id, key.value))
            if pending is not None:
                raise ReconciliationRequired(
                    operation_id=operation_id,
                    detail={
                        "receipt_id": pending.receipt_id,
                        "idempotency_key": key.value,
                    },
                )
            # A fresh key must not walk past an unreconciled write: block on
            # the canonical request fingerprint too, same operation and tenant.
            for held in self._pending.values():
                if (
                    held.operation_id == operation_id
                    and held.tenant.location_id == tenant.location_id
                    and held.request_fingerprint == fingerprint_box["value"]
                ):
                    return finish(
                        Status.denied,
                        error={
                            "rule": "unreconciled_intent_exists",
                            "receipt_id": held.receipt_id,
                            "pending": len(self._pending),
                        },
                        extra={"refused_before_transport": True},
                    )
            if len(self._pending) >= _PENDING_LIMIT:
                # Never evict an unreconciled write to make room: reconciliation
                # is the only way space is freed, so refuse before transport.
                return finish(
                    Status.unavailable,
                    error={
                        "rule": "reconciliation_store_full",
                        "pending": len(self._pending),
                        "limit": _PENDING_LIMIT,
                    },
                    extra={"refused_before_transport": True},
                )
            seen = self._ledger.lookup(key.value)
            if seen is not None and seen != fingerprint_box["value"]:
                return finish(
                    Status.conflict,
                    error={"rule": "idempotency_key_reuse"},
                    extra={"refused_before_transport": True},
                )
            if attempt > self._max_attempts:
                raise ContractViolation(
                    "max_attempts_exceeded",
                    operation_id=operation_id,
                    detail={"attempt": attempt, "max_attempts": self._max_attempts},
                )
        else:
            if idempotency_key is not None:
                raise ContractViolation(
                    "idempotency_key_not_allowed_for_read",
                    operation_id=operation_id,
                )

        # approval.
        approval_kind = _approval_kind(approval)
        if approval_required and approval_kind is None:
            raise ContractViolation("approval_required", operation_id=operation_id)

        # 8. readback plan -- every write needs one, always before transport.
        spec: ReadbackSpec | None = None
        if write:
            plan = (
                self._readbacks.get(operation_id)
                if self._readbacks is not None
                else None
            )
            if readback is None and plan is None:
                raise ContractViolation(
                    "readback_required", operation_id=operation_id
                )
            spec = readback if readback is not None else plan
            if not isinstance(spec, ReadbackSpec):
                raise ContractViolation(
                    "readback_invalid", operation_id=operation_id
                )
            # BLOCKER 1: a read-back may only re-READ.  A spec pointing at a
            # write row would make reconcile() re-issue the same mutating
            # request, so the target row must be a read row.  The write row's
            # declared plan, when present, must be the spec that runs.
            target_row = self._resolve_row(spec.operation_id)
            if bool(_row_attr(target_row, "write", False)):
                raise ContractViolation(
                    "readback_invalid",
                    operation_id=operation_id,
                    detail={
                        "reason": "readback_targets_a_write",
                        "readback": spec.operation_id,
                    },
                )
            if plan is not None and plan.operation_id != spec.operation_id:
                raise ContractViolation(
                    "readback_plan_mismatch",
                    operation_id=operation_id,
                    detail={"plan": plan.operation_id, "call": spec.operation_id},
                )
            # MAJOR 5: a spec with no expectation verifies any 2xx, which is
            # zero verification.  No write crosses transport on it.
            if not spec.expect:
                raise ContractViolation(
                    "readback_vacuous",
                    operation_id=operation_id,
                    detail={"readback": spec.operation_id},
                )
        elif readback is not None:
            raise ContractViolation(
                "readback_not_allowed_for_read", operation_id=operation_id
            )

        # 3.2 rule 7 -- the gate refuses before transport, with a receipt.
        capability_evidence: dict[str, Any] | None = None
        if not _gate_skips(route_class):
            gate = self._gate_for(tenant.location_id)
            capability = gate.get(operation_id)
            # MAJOR 4: a gate (or the capability record itself) authorized for
            # one tenant never authorizes a call for another.
            gate_tenant = gate.tenant
            record_tenant = getattr(capability, "tenant", None)
            wrong_tenant = next(
                (
                    bound
                    for bound in (record_tenant, gate_tenant)
                    if bound is not None and bound != tenant.location_id
                ),
                None,
            )
            if wrong_tenant is not None:
                return finish(
                    Status.denied,
                    error={
                        "rule": "capability_tenant_mismatch",
                        "operation_id": operation_id,
                        "hint": (
                            "the capability is bound to another tenant"
                        ),
                    },
                    extra={
                        "refused_before_transport": True,
                        "capability": {
                            "operation_id": operation_id,
                            "enabled": capability.enabled,
                        },
                    },
                )
            # BLOCKER 3: a write needs canary evidence, not just enablement.
            admitted = (
                capability.write_ready() if write else capability.enabled
            )
            if not admitted:
                block = capability.activation_blocked or DEFAULT_BLOCK
                return finish(
                    Status.denied,
                    error={
                        "rule": "capability_disabled",
                        "operation_id": operation_id,
                        "reason": block.reason,
                        "owner": block.owner,
                        "unblock": block.unblock,
                    },
                    extra={
                        "refused_before_transport": True,
                        "capability": {
                            "operation_id": operation_id,
                            "enabled": False,
                        },
                    },
                )
            # Enabled by record is not verified by tenant: the receipt says
            # which state authorized the dispatch and never upgrades it.
            capability_evidence = _capability_evidence(capability)

        headers = auth_headers(self._auth)
        if key is not None:
            self._ledger.record(key.value, fingerprint_box["value"])

        # BLOCKER 2: transport.py classifies only the failures it knows.  Any
        # other exception (http.client.IncompleteRead, HTTPException,
        # ValueError, a broken fake) must not escape call() with no receipt and
        # no pending record -- that is how the same key got retried.  An
        # unclassified failure is an unknown outcome, mapped through the normal
        # finish path below, and the write is remembered for reconcile().
        transport_exception: str | None = None
        try:
            response = self._transport.request(
                method=method,
                url=resolved_path,
                version=version,
                headers=headers,
                query=query_map or None,
                body=body_map or None,
                timeout_s=timeout,
            )
        except Exception as caught:  # noqa: BLE001 - the blocker is exactly here
            transport_exception = type(caught).__name__
            response = TransportResponse(
                status=None,
                headers={},
                body=b"",
                error_kind="unknown",
                elapsed_s=None,
            )

        http_status: int | None
        if response.error_kind == "none":
            http_status = response.status
            response_fp = response_fingerprint(response.body)
        else:
            http_status = None
            response_fp = None

        status = _derive_status(
            http_status=http_status,
            error_kind=response.error_kind,
            write=write,
        )

        readback_result: ReadbackResult | None = None
        if write:
            assert spec is not None  # validated above
            if status is Status.ok:
                readback_result, _ = self._run_readback(
                    spec, tenant=tenant, attempt=attempt
                )
                if readback_result.result is not ReadbackStatus.verified:
                    status = Status.unknown_outcome
            else:
                readback_result = ReadbackResult(
                    result=ReadbackStatus.unreadable,
                    operation_id=spec.operation_id,
                    attempt=attempt,
                    detail={
                        "reason": "not_performed",
                        "http_status": http_status,
                    },
                    evidence={},
                )

        error = _error_for(
            status,
            http_status=http_status,
            error_kind=response.error_kind,
            scopes=scopes,
            readback_result=readback_result,
        )

        extra: dict[str, Any] = {
            "response_headers": redact_headers(response.headers),
            "elapsed_s": response.elapsed_s,
        }
        if capability_evidence is not None:
            # ``activation`` is the record state, not this call's outcome.  A
            # 200 is surfaced as observed, never written back as VERIFIED.
            capability_evidence["observed_http_status"] = http_status
            extra["capability"] = capability_evidence
        if transport_exception is not None:
            # The class name only: an exception object can carry payload.
            extra["transport_exception"] = transport_exception
        if approval_kind is not None:
            # Intensity only: which seam was used, never the value.
            extra["approval"] = {"present": True, "kind": approval_kind}

        result = finish(
            status,
            error=error,
            http_status=http_status,
            response_fp=response_fp,
            readback_result=readback_result,
            extra=extra,
        )

        if write and status is Status.unknown_outcome:
            self._remember(
                _PendingWrite(
                    operation_id=operation_id,
                    receipt_id=receipt_id,
                    request_fingerprint=fingerprint_box["value"],
                    idempotency_key=key.value if key is not None else None,
                    tenant=tenant,
                    readback_spec=spec,  # type: ignore[arg-type]
                    attempt=attempt,
                    version=version,
                    doc_url=doc_url,
                    doc_fetch_date=doc_fetch_date,
                )
            )

        return result

    def reconcile(self, prior: OperationResult) -> OperationResult:
        """Re-read through the same operation's declared readback row."""

        started = self._clock()
        if not isinstance(prior, OperationResult):
            raise ContractViolation("reconcile_prior_invalid")
        if prior.status is not Status.unknown_outcome:
            raise ContractViolation(
                "reconcile_requires_unknown_outcome",
                operation_id=prior.operation_id,
                detail={"status": prior.status.value},
            )
        pending = self._pending.get(prior.receipt_id)
        if pending is None:
            raise ContractViolation(
                "reconcile_unknown_receipt",
                operation_id=prior.operation_id,
                detail={"receipt_id": prior.receipt_id},
            )

        readback_result, readback_http = self._run_readback(
            pending.readback_spec,
            tenant=pending.tenant,
            attempt=pending.attempt,
        )
        status = {
            ReadbackStatus.verified: Status.ok,
            ReadbackStatus.absent: Status.not_found,
            ReadbackStatus.mismatch: Status.conflict,
            ReadbackStatus.unreadable: Status.unavailable,
        }[readback_result.result]

        if readback_result.result is not ReadbackStatus.unreadable:
            self._forget(pending)

        finished = self._clock()
        receipt_id = "gxo_res_" + secrets.token_hex(6)
        evidence: dict[str, Any] = {
            "operation_id": pending.operation_id,
            "request_fingerprint": pending.request_fingerprint,
            "http_status": readback_http,
            "response_fingerprint": readback_result.detail.get(
                "response_fingerprint"
            ),
            "tenant": pending.tenant.location_id,
            "attempt": pending.attempt,
            "readback": readback_result.result.value,
            "receipt_id": receipt_id,
            "version_header": pending.version,
            "timeout_s": self._default_timeout_s,
            "adapter_version": ADAPTER_VERSION,
            "transport": "http",
            "auth_kind": self._auth.kind.value,
            "auth_source": self._auth.source,
            "doc_url": pending.doc_url,
            "doc_fetch_date": pending.doc_fetch_date,
            "request_bytes": 0,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "reconciled_from": prior.receipt_id,
            "reconcile": True,
        }
        error = (
            None
            if status is Status.ok
            else {"rule": "reconcile_" + readback_result.result.value}
        )
        return OperationResult(
            status=status,
            operation_id=pending.operation_id,
            receipt_id=receipt_id,
            request_fingerprint=pending.request_fingerprint,
            http_status=readback_http,
            response_fingerprint=readback_result.detail.get("response_fingerprint"),
            tenant=pending.tenant.location_id,
            attempt=pending.attempt,
            version_header=pending.version,
            readback=readback_result,
            adapter_version=ADAPTER_VERSION,
            transport="http",
            doc_url=pending.doc_url,
            evidence=evidence,
            error=error,
        )

    def capability(
        self, operation_id: str, *, tenant: str | None = None
    ) -> Capability:
        row = self._resolve_row(operation_id)
        if _gate_skips(_row_attr(row, "route_class")):
            return Capability(
                operation_id=str(operation_id),
                enabled=False,
                activation_blocked=ActivationBlock(
                    reason=(
                        "not governed by the public capability gate; the "
                        "skill44_private rail owns its own surfaces"
                    ),
                    owner="W06",
                    unblock="n/a",
                ),
            )
        if tenant is not None:
            return self._gate_for(str(tenant)).get(operation_id)
        if self._capability is not None:
            return self._capability.get(operation_id)
        if len(self._record_gates) == 1:
            return next(iter(self._record_gates.values())).get(operation_id)
        # No tenant and no single loaded record: the honest answer is deny.
        return CapabilityGate().get(operation_id)

    def _gate_for(self, tenant: str) -> CapabilityGate:
        """Explicit gate, else the checked-in record bound to this tenant."""

        if self._capability is not None:
            return self._capability
        gate = self._record_gates.get(tenant)
        if gate is None:
            gate = load_capability_record(
                tenant=tenant, path=self._capability_record
            )
            self._record_gates[tenant] = gate
        return gate

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _resolve_row(self, operation_id: str) -> Any:
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ContractViolation("operation_id_invalid")
        registry = self._operations
        row: Any = None
        getter = getattr(registry, "get", None)
        if callable(getter):
            row = getter(operation_id)
        if row is None:
            try:
                row = registry[operation_id]  # type: ignore[index]
            except (KeyError, TypeError):
                row = None
        if row is None:
            for name in ("require", "resolve", "lookup"):
                candidate = getattr(registry, name, None)
                if callable(candidate):
                    try:
                        row = candidate(operation_id)
                    except KeyError:
                        row = None
                    break
        if row is None:
            raise ContractViolation(
                "unknown_operation_id", operation_id=operation_id
            )
        return row

    def _run_readback(
        self,
        spec: ReadbackSpec,
        *,
        tenant: TenantBinding,
        attempt: int,
    ) -> tuple[ReadbackResult, int | None]:
        try:
            row = self._resolve_row(spec.operation_id)
        except ContractViolation:
            return (
                ReadbackResult(
                    result=ReadbackStatus.unreadable,
                    operation_id=spec.operation_id,
                    attempt=attempt,
                    detail={"reason": "readback_operation_unknown"},
                    evidence={},
                ),
                None,
            )

        method = _row_attr(row, "method")
        template = _row_attr(row, "path_template")
        version = _row_attr(row, "version", None)
        binding = _row_attr(row, "tenant_binding", "none")
        params = {str(k): str(v) for k, v in dict(spec.target_params or {}).items()}
        query_map: dict[str, Any] = dict(spec.query or {})
        body_map: dict[str, Any] = {}

        names = _PATH_PARAM.findall(template or "")
        if set(names) != set(params):
            return (
                ReadbackResult(
                    result=ReadbackStatus.unreadable,
                    operation_id=spec.operation_id,
                    attempt=attempt,
                    detail={"reason": "readback_target_mismatch"},
                    evidence={},
                ),
                None,
            )
        try:
            _apply_tenant_binding(
                binding, tenant.location_id, params, query_map, body_map
            )
        except _Refusal:
            return (
                ReadbackResult(
                    result=ReadbackStatus.unreadable,
                    operation_id=spec.operation_id,
                    attempt=attempt,
                    detail={"reason": "readback_tenant_conflict"},
                    evidence={},
                ),
                None,
            )

        if not isinstance(method, str) or not method.strip():
            return (
                ReadbackResult(
                    result=ReadbackStatus.unreadable,
                    operation_id=spec.operation_id,
                    attempt=attempt,
                    detail={"reason": "readback_row_invalid"},
                    evidence={},
                ),
                None,
            )

        path = _format_path(template, params)
        try:
            headers = auth_headers(self._auth)
        except CredentialMissing:
            return (
                ReadbackResult(
                    result=ReadbackStatus.unreadable,
                    operation_id=spec.operation_id,
                    attempt=attempt,
                    detail={"reason": "credential_missing"},
                    evidence={},
                ),
                None,
            )

        # BLOCKER 2: an unexpected exception anywhere in the read-back must
        # degrade to unreadable, never escape a call or a reconcile().
        try:
            response: TransportResponse = self._transport.request(
                method=method,
                url=path,
                version=version,
                headers=headers,
                query=query_map or None,
                body=body_map or None,
                timeout_s=self._default_timeout_s,
            )

            parsed: Any = None
            if (
                response.error_kind == "none"
                and response.status is not None
                and 200 <= response.status < 300
                and response.body
            ):
                try:
                    parsed = json.loads(response.body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    parsed = None

            outcome = evaluate_readback(
                spec,
                http_status=(
                    response.status if response.error_kind == "none" else None
                ),
                parsed_body=parsed,
                transport_error=response.error_kind,
            )
            detail = {
                "http_status": response.status,
                "error_kind": response.error_kind,
                "response_fingerprint": response_fingerprint(response.body),
            }
            http_status = (
                response.status if response.error_kind == "none" else None
            )
        except Exception:  # noqa: BLE001 - a readback must never crash a call
            return (
                ReadbackResult(
                    result=ReadbackStatus.unreadable,
                    operation_id=spec.operation_id,
                    attempt=attempt,
                    detail={"reason": "readback_transport_error"},
                    evidence={},
                ),
                None,
            )

        return (
            ReadbackResult(
                result=outcome,
                operation_id=spec.operation_id,
                attempt=attempt,
                detail=detail,
                evidence={"readback_method": method, "readback_path": path},
            ),
            http_status,
        )

    def _remember(self, pending: _PendingWrite) -> None:
        # Reconciliation is the only way space is freed: an unreconciled write
        # is an unknown-outcome write, and forgetting it would let a later call
        # double-write.  The caller refuses before transport when the bound is
        # reached, so this is defensive, never a silent eviction.
        if len(self._pending) >= _PENDING_LIMIT:  # pragma: no cover - guarded
            raise ContractViolation(
                "reconciliation_store_full",
                operation_id=pending.operation_id,
                detail={"pending": len(self._pending)},
            )
        self._pending[pending.receipt_id] = pending
        if pending.idempotency_key:
            self._pending_by_key[
                (pending.operation_id, pending.idempotency_key)
            ] = pending

    def _forget(self, pending: _PendingWrite) -> None:
        self._pending.pop(pending.receipt_id, None)
        if pending.idempotency_key:
            self._pending_by_key.pop(
                (pending.operation_id, pending.idempotency_key), None
            )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _row_attr(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def _gate_skips(route_class: Any) -> bool:
    text = route_class.value if hasattr(route_class, "value") else route_class
    return str(text) in _GATE_SKIPPED_ROUTES


def _capability_evidence(capability: Capability) -> dict[str, Any]:
    """The descriptor's honest state; never a claim of tenant capability."""

    return {
        "operation_id": capability.operation_id,
        "enabled": bool(capability.enabled),
        "activation": capability.activation,
        "tenant_verified": capability.tenant_verified(),
        "provisional": bool(capability.provisional),
    }


def _format_path(template: str, values: Mapping[str, str]) -> str:
    path = template
    for name in _PATH_PARAM.findall(template):
        path = path.replace("{" + name + "}", quote(str(values[name]), safe=""))
    if not path.startswith("/"):
        path = "/" + path
    return path


def _apply_tenant_binding(
    binding: Any,
    location_id: str,
    path_values: dict[str, str],
    query: dict[str, Any],
    body: dict[str, Any],
) -> None:
    text = binding.value if hasattr(binding, "value") else binding

    if text in ("none", "implicit-pit", None, ""):
        return
    if text == "body.locationId":
        _inject(body, "locationId", location_id, "body")
        return
    if text == "query.locationId":
        _inject(query, "locationId", location_id, "query")
        return
    if text == "path.locationId":
        if "locationId" not in path_values:
            raise _Refusal("tenant_path_missing")
        if path_values["locationId"] != location_id:
            raise _Refusal(
                "tenant_mismatch", detail={"field": "path.locationId"}
            )
        return
    if text == "body.altId+altType=location":
        _inject(body, "altId", location_id, "body")
        _inject(body, "altType", "location", "body")
        return
    if text in ("query.altId+altType", "query.altId+altType=location"):
        _inject(query, "altId", location_id, "query")
        _inject(query, "altType", "location", "query")
        return
    if isinstance(text, str) and text.startswith("path."):
        # The identifier travels in its own path parameter; the frozen literal
        # list does not define an injection for it.
        return
    raise _Refusal(
        "unknown_tenant_binding", detail={"binding": str(text)}
    )


def _inject(
    target: dict[str, Any], key: str, value: str, where: str
) -> None:
    existing = target.get(key)
    if existing is not None and str(existing) != str(value):
        raise _Refusal("tenant_mismatch", detail={"field": f"{where}.{key}"})
    target[key] = value


def _approval_kind(
    approval: ApprovalRef | Mapping[str, Any] | str | None,
) -> str | None:
    if approval is None:
        return None
    if isinstance(approval, ApprovalRef):
        return approval.kind
    if isinstance(approval, Mapping):
        if not approval.get("ref"):
            raise ContractViolation(
                "approval_invalid", detail={"reason": "missing_ref"}
            )
        kind = str(approval.get("kind", _APPROVAL_RECORD))
    elif isinstance(approval, str):
        if not approval.strip():
            raise ContractViolation(
                "approval_invalid", detail={"reason": "empty_ref"}
            )
        kind = _APPROVAL_RECORD
    else:
        raise ContractViolation(
            "approval_invalid", detail={"reason": "unsupported_type"}
        )
    if kind not in (_APPROVAL_RECORD, _APPROVAL_TOKEN):
        raise ContractViolation("approval_kind_invalid", detail={"kind": kind})
    return kind


def _derive_status(
    *, http_status: int | None, error_kind: str, write: bool
) -> Status:
    if error_kind != "none":
        return Status.unknown_outcome if write else Status.unavailable
    if http_status is None:
        return Status.unknown_outcome if write else Status.unavailable
    if http_status in (401, 403):
        return Status.denied
    if http_status == 404:
        return Status.not_found
    if http_status == 409:
        return Status.conflict
    if http_status in (400, 422):
        return Status.validation_error
    if http_status == 429:
        return Status.rate_limited
    if 500 <= http_status <= 599:
        return Status.unknown_outcome if write else Status.unavailable
    if 200 <= http_status <= 299:
        return Status.ok
    return Status.unknown_outcome if write else Status.unavailable


def _error_for(
    status: Status,
    *,
    http_status: int | None,
    error_kind: str,
    scopes: tuple[str, ...],
    readback_result: ReadbackResult | None,
) -> Mapping[str, Any] | None:
    if status is Status.ok:
        return None
    if error_kind != "none":
        return {"rule": "transport_" + error_kind}
    if http_status is None:
        return {"rule": "no_response"}
    if http_status in (401, 403):
        error: dict[str, Any] = {"rule": "permission_denied"}
        if scopes:
            error["scopes_candidate"] = list(scopes)
            error["hint"] = "scope candidate only; never asserted as proven"
        return error
    if http_status == 404:
        return {"rule": "not_found"}
    if http_status == 409:
        return {"rule": "conflict"}
    if http_status in (400, 422):
        return {"rule": "validation_error"}
    if http_status == 429:
        return {"rule": "rate_limited"}
    if 500 <= http_status <= 599:
        return {"rule": "upstream_error", "http_status": http_status}
    if readback_result is not None and readback_result.result is not ReadbackStatus.verified:
        return {"rule": "readback_" + readback_result.result.value}
    return {"rule": "unexpected_http_status", "http_status": http_status}
