"""Typed agency operation: public sub-account (location) creation (WF05).

Document 1 section 7.2: the documented create-location operation is
``POST /locations``, Version ``2021-07-28``, scope ``locations.write``, executed
with an **Agency Token** and the agency ``companyId``.  It is NOT a location
operation: no location credential is ever accepted here, and no Command Center
company UUID or numeric relation number may travel as ``companyId``.

Frozen interface (WF05-CP01, source-code signature, consumed by WF03):

* :func:`resolve_agency_auth` -- the agency-token resolver, separate from
  ``public.auth.resolve_auth`` (which today refuses ``agency_pit`` loudly).
* :class:`AgencyAuthContext`, :func:`agency_headers`
* :class:`AgencyLocationSpec`, :func:`location_request_body`,
  :func:`guard_agency_company_id`
* :class:`PlanFact`, :class:`PlanFacts` -- per-tenant plan eligibility; an
  owner-supplied Agency Pro fact for one agency is never a global default.
* :class:`AgencyAdapter` with
  ``create_location(spec, *, approval, approval_verifier, idempotency_key,
  dry_run, timeout_s, attempt) -> OperationResult`` and ``reconcile(prior)``.
* :func:`route_decision` -- public agency rail preferred when credential, plan,
  approval and capability are valid; otherwise the *labelled* existing private
  create fallback (which this module never executes).

Registration and registry ownership stay outside this file: WF03 owns
``gohighlevel_cli.py`` registration, WF00 owns the shared ``operations.py`` row.
This module therefore carries one frozen local row and files change requests;
it does not fork a second dispatch authority.

Rules encoded (Document 1 sections 5.3-5.5, 7.1-7.2):

* Compile-only dry run performs no mutating network call.
* Plan eligibility is a per-tenant account fact.  Unknown is not eligible.
* A verified, unexpired ``automation_write`` approval names this exact action
  and object; a record with no verifier is refused (fail closed).
* A capability row must be enabled with write-canary evidence and bound to the
  agency company; otherwise the operation is refused before transport.
* Every write is read back (``GET /locations/{locationId}``): identity and name
  must match, or the outcome stays uncertain.  A create response without a
  native id is never reported as success.
* An unknown outcome is reconciled by re-reading the same native id; a missing
  id is never guessed.  No blind retry, no second rail.
"""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.parse import quote

from .adapter import _derive_status  # same package: one status vocabulary
from .auth import AGENCY_PIT_ALIASES, AuthKind, is_placeholder, make_secret_resolver
from .capability import Capability
from .errors import ContractViolation, CredentialMissing
from .idempotency import IdempotencyKey, IdempotencyLedger, canonical_intent
from .readback import ReadbackResult, ReadbackStatus
from .result import (
    ADAPTER_VERSION,
    OperationResult,
    Status,
    request_fingerprint_of,
    response_fingerprint,
)
from .transport import RequestsTransport, Transport, TransportResponse

#: Frozen operation row values (Document 1 section 7.2; official create-location
#: page).  The shared registry row is WF00's file; see the checkout change request.
OPERATION_ID = "locations.create"
OPERATION_METHOD = "POST"
OPERATION_PATH = "/locations"
OPERATION_SCOPES: tuple[str, ...] = ("locations.write",)
OPERATION_DOC_URL = (
    "https://marketplace.gohighlevel.com/docs/ghl/locations/create-location"
)
DOC_FETCH_DATE = "2026-11-08"


@dataclass(frozen=True)
class AgencyOperationRow:
    """This operation's OWN frozen row.

    The Version literal lives on the row (freeze 1.3 step 3: Version is a
    property of a row).  No module-level version constant exists, so the
    public package keeps its no-global-default guarantee; every call reads
    OPERATION.version.
    """

    operation_id: str = OPERATION_ID
    method: str = OPERATION_METHOD
    path_template: str = OPERATION_PATH
    version: str = "2021-07-28"
    scopes: tuple[str, ...] = OPERATION_SCOPES
    auth_kind: AuthKind = AuthKind.agency_pit
    tenant_binding: str = "body.companyId"
    write: bool = True
    approval_required: bool = True
    doc_url: str = OPERATION_DOC_URL
    doc_fetch_date: str = DOC_FETCH_DATE


OPERATION = AgencyOperationRow()

APPROVAL_KIND = "automation_write"
APPROVAL_ACTION = "locations.create"

PUBLIC_RAIL = "public_agency"
PRIVATE_FALLBACK_RAIL = "private_fallback"
#: The label that must accompany the existing private create implementation.
PRIVATE_FALLBACK_NOTE = (
    "existing Skill 44 private create (Firebase/internal, --experimental) is the "
    "labelled fallback; the public Agency Token operation is the preferred route "
    "when credential, plan and approval are valid"
)

_RETIRED_OR_RELATION = re.compile(r"^\d+$")
_CC_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_PLACEHOLDER_SOURCES = frozenset({"unknown", "", "default", "guess"})


# ---------------------------------------------------------------------------
# Agency credential: a separate resolver, never the location one
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgencyAuthContext:
    """One agency credential class.  Location PITs are not accepted."""

    kind: AuthKind
    resolve_secret: Callable[[str], str]
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", AuthKind(self.kind))
        if self.kind is not AuthKind.agency_pit:
            raise ContractViolation(
                "agency_write_requires_agency_token",
                detail={"kind": self.kind.value},
            )
        if not callable(self.resolve_secret):
            raise ContractViolation("auth_resolver_invalid")
        if not isinstance(self.source, str) or ":" not in self.source:
            raise ContractViolation("auth_source_unreadable")


def resolve_agency_auth(
    *,
    env: Mapping[str, str] | None = None,
    resolve_secret: Callable[[str], str] | None = None,
) -> AgencyAuthContext:
    """Resolve the Agency Token through its OWN alias chain.

    Only ``public.auth.AGENCY_PIT_ALIASES`` are tried.  There is no fallback to
    ``LOCATION_PIT_ALIASES`` and no guessed variable name: a missing agency
    token is a typed ``CredentialMissing`` naming the aliases tried.
    """

    resolver = resolve_secret or make_secret_resolver(env)
    tried: list[str] = []
    for name in AGENCY_PIT_ALIASES:
        tried.append(name)
        try:
            value = resolver(name)
        except CredentialMissing:
            continue
        if is_placeholder(value):
            continue
        return AgencyAuthContext(
            kind=AuthKind.agency_pit,
            resolve_secret=resolver,
            source="env:" + name,
        )
    raise CredentialMissing(detail={"kind": AuthKind.agency_pit.value, "tried": tried})


def agency_secret_name(auth: AgencyAuthContext) -> str:
    label, _, name = str(auth.source).partition(":")
    if label != "env" or not name:
        raise ContractViolation("auth_source_unreadable", detail={"source": auth.source})
    return name


def agency_headers(auth: AgencyAuthContext) -> dict[str, str]:
    """Agency bearer header.  The value is resolved late and never recorded."""

    return {"Authorization": "Bearer " + auth.resolve_secret(agency_secret_name(auth))}


# ---------------------------------------------------------------------------
# Agency company identity and per-tenant plan fact
# ---------------------------------------------------------------------------


def guard_agency_company_id(value: Any, field: str = "agency_company_id") -> str:
    """Refuse a value that cannot be the GHL agency ``companyId``.

    Numeric-only is the relation-number shape; a canonical UUID is the Command
    Center company shape.  Neither may substitute for the GHL agency id.
    """

    if not isinstance(value, str) or not value.strip():
        raise ContractViolation("agency_company_id_missing", detail={"field": field})
    text = value.strip()
    if is_placeholder(text):
        raise ContractViolation("agency_company_id_placeholder", detail={"field": field})
    if _RETIRED_OR_RELATION.match(text):
        raise ContractViolation(
            "agency_company_id_is_relation_number", detail={"field": field}
        )
    if _CC_UUID.match(text):
        raise ContractViolation(
            "agency_company_id_is_command_center_uuid", detail={"field": field}
        )
    return text


@dataclass(frozen=True)
class PlanFact:
    """Plan eligibility for ONE agency company.

    ``agency_pro=None`` means unknown, and unknown is not eligible.  A fact is
    owner-supplied or tenant-verified; it is never inherited from another
    company, and never a global default.
    """

    agency_company_id: str
    agency_pro: bool | None
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "agency_company_id",
            guard_agency_company_id(self.agency_company_id),
        )
        if self.agency_pro is not None and not isinstance(self.agency_pro, bool):
            raise ContractViolation("plan_fact_invalid", detail={"field": "agency_pro"})
        if not isinstance(self.source, str) or not self.source.strip():
            raise ContractViolation("plan_fact_invalid", detail={"field": "source"})

    def eligible(self) -> bool:
        return self.agency_pro is True and self.source.strip().lower() not in _PLACEHOLDER_SOURCES


class PlanFacts:
    """Explicit per-tenant plan facts.  Missing means unknown, never eligible."""

    def __init__(self, facts: Mapping[str, PlanFact] | None = None) -> None:
        self._facts: dict[str, PlanFact] = {}
        for key, fact in dict(facts or {}).items():
            if not isinstance(fact, PlanFact):
                raise ContractViolation("plan_fact_invalid")
            if fact.agency_company_id != guard_agency_company_id(str(key)):
                raise ContractViolation("plan_fact_key_mismatch")
            self._facts[fact.agency_company_id] = fact

    def for_company(self, agency_company_id: str) -> PlanFact:
        company = guard_agency_company_id(agency_company_id)
        known = self._facts.get(company)
        if known is not None:
            return known
        return PlanFact(company, None, "unknown")


# ---------------------------------------------------------------------------
# Request compilation (one builder)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgencyLocationSpec:
    """Approved values for one sub-account create.  No invented fields."""

    name: str
    agency_company_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ContractViolation("location_name_missing")
        object.__setattr__(
            self,
            "agency_company_id",
            guard_agency_company_id(self.agency_company_id),
        )


def location_request_body(spec: AgencyLocationSpec) -> dict[str, str]:
    """The ONLY builder of the documented create-location body.

    Exactly ``name`` and ``companyId``.  No ``locationId`` can appear: an agency
    create has no target location and must not borrow one.
    """

    if not isinstance(spec, AgencyLocationSpec):
        raise ContractViolation("location_spec_invalid")
    return {"name": spec.name.strip(), "companyId": spec.agency_company_id}


def approval_object_key(spec: AgencyLocationSpec) -> str:
    return "agency:" + spec.agency_company_id + ":" + spec.name.strip()


def require_agency_approval(
    approval: Mapping[str, Any] | None,
    verifier: Callable[[Mapping[str, Any]], bool] | None,
    *,
    spec: AgencyLocationSpec,
    now: float | None = None,
) -> None:
    """Refuse unless an unexpired, verified ``automation_write`` record names
    this exact agency create.  No verifier means no write (fail closed)."""

    if not isinstance(approval, Mapping) or approval.get("kind") != APPROVAL_KIND:
        raise ContractViolation(
            "approval_required", operation_id=OPERATION_ID, detail={"kind": APPROVAL_KIND}
        )
    if approval.get("action") != APPROVAL_ACTION:
        raise ContractViolation("approval_mismatch", detail={"field": "action"})
    if approval.get("object_key") != approval_object_key(spec):
        raise ContractViolation("approval_mismatch", detail={"field": "object_key"})
    for field in ("plan_sha256", "approver"):
        if approval.get(field) in (None, ""):
            raise ContractViolation("approval_required", detail={"field": field})
    expiry = approval.get("expiry")
    import time as _time

    if (
        isinstance(expiry, bool)
        or not isinstance(expiry, (int, float))
        or expiry <= (now if now is not None else _time.time())
    ):
        raise ContractViolation("approval_expired")
    if verifier is None or verifier(approval) is not True:
        raise ContractViolation("approval_unverified")


# ---------------------------------------------------------------------------
# Routing decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteDecision:
    rail: str
    reason: str
    request: Mapping[str, Any] | None

    @property
    def public(self) -> bool:
        return self.rail == PUBLIC_RAIL


def route_decision(
    *,
    spec: AgencyLocationSpec,
    agency_credential_present: bool,
    plan_fact: PlanFact,
    approval: Mapping[str, Any] | None,
    capability: Capability | None,
) -> RouteDecision:
    """Choose the public agency rail or the labelled private fallback.

    Pure: performs no I/O.  The private fallback is returned with an explicit
    label and is never executed here.
    """

    if not agency_credential_present:
        return RouteDecision(PRIVATE_FALLBACK_RAIL, "agency_token_missing", None)
    if not plan_fact.eligible():
        return RouteDecision(
            PRIVATE_FALLBACK_RAIL,
            "agency_plan_not_eligible_for_tenant",
            None,
        )
    if not isinstance(approval, Mapping):
        return RouteDecision(PRIVATE_FALLBACK_RAIL, "approval_required", None)
    if capability is None or not capability.enabled or not capability.write_ready():
        return RouteDecision(PRIVATE_FALLBACK_RAIL, "capability_disabled", None)
    if capability.tenant not in (None, spec.agency_company_id):
        return RouteDecision(PRIVATE_FALLBACK_RAIL, "capability_tenant_mismatch", None)
    return RouteDecision(PUBLIC_RAIL, "public_agency_ready", location_request_body(spec))


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


def _location_id_from_body(body: Any) -> str:
    """Native location id from a create/read payload; "" when absent.

    The documented create answer nests the record under ``location``; a read
    answers the record directly.  Both ``id`` and ``_id`` are observed keys.
    Nothing is guessed when neither is present.
    """

    if not isinstance(body, Mapping):
        return ""
    record = body.get("location")
    candidates = [record] if isinstance(record, Mapping) else []
    candidates.append(body)
    for entry in candidates:
        for key in ("id", "_id", "locationId"):
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


class AgencyAdapter:
    """The typed public agency operation reaching the real transport seam."""

    def __init__(
        self,
        *,
        auth: AgencyAuthContext,
        transport: Transport | None = None,
        capability: Capability | None = None,
        plan_facts: PlanFacts | None = None,
        default_timeout_s: float = 30.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(auth, AgencyAuthContext):
            raise ContractViolation("agency_write_requires_agency_token")
        if float(default_timeout_s) <= 0:
            raise ContractViolation("timeout_invalid")
        self._auth = auth
        self._transport: Transport = transport if transport is not None else RequestsTransport()
        self._capability = capability
        self._plans = plan_facts if plan_facts is not None else PlanFacts()
        self._timeout = float(default_timeout_s)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._ledger = IdempotencyLedger()
        self._pending: dict[str, tuple[str, AgencyLocationSpec, str]] = {}

    # -- public surface ---------------------------------------------------

    def create_location(
        self,
        spec: AgencyLocationSpec,
        *,
        approval: Mapping[str, Any] | None = None,
        approval_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
        idempotency_key: str | None = None,
        dry_run: bool = False,
        timeout_s: float | None = None,
        attempt: int = 1,
    ) -> OperationResult:
        if not isinstance(spec, AgencyLocationSpec):
            raise ContractViolation("location_spec_invalid")
        if not isinstance(attempt, int) or attempt < 1:
            raise ContractViolation("attempt_invalid")
        if idempotency_key is None or not str(idempotency_key).strip():
            raise ContractViolation(
                "idempotency_key_required",
                operation_id=OPERATION_ID,
                detail={"write": True},
            )
        key = IdempotencyKey.parse(str(idempotency_key))
        for receipt, (_, _, held_key) in self._pending.items():
            if held_key == key.value:
                raise ContractViolation(
                    "reconciliation_required",
                    operation_id=OPERATION_ID,
                    detail={"receipt_id": receipt, "idempotency_key": key.value},
                )

        started = self._clock()
        timeout = self._timeout if timeout_s is None else float(timeout_s)
        if timeout <= 0:
            raise ContractViolation("timeout_invalid")
        body = location_request_body(spec)
        fingerprint = canonical_intent(
            operation_id=OPERATION_ID,
            method=OPERATION_METHOD,
            resolved_path=OPERATION_PATH,
            query=None,
            body=body,
            tenant=spec.agency_company_id,
            version=OPERATION.version,
        )
        receipt_id = "gxo_agency_" + secrets.token_hex(6)
        plan_fact = self._plans.for_company(spec.agency_company_id)

        def finish(
            status: Status,
            *,
            error: Mapping[str, Any] | None = None,
            http_status: int | None = None,
            response_fp: str | None = None,
            readback: ReadbackResult | None = None,
            extra: Mapping[str, Any] | None = None,
        ) -> OperationResult:
            evidence: dict[str, Any] = {
                "operation_id": OPERATION_ID,
                "request_fingerprint": fingerprint,
                "http_status": http_status,
                "response_fingerprint": response_fp,
                "tenant": spec.agency_company_id,
                "attempt": attempt,
                "readback": readback.result.value if readback else None,
                "receipt_id": receipt_id,
                "version_header": OPERATION.version,
                "timeout_s": timeout,
                "adapter_version": ADAPTER_VERSION,
                "transport": "http",
                "auth_kind": self._auth.kind.value,
                "auth_source": self._auth.source,
                "doc_url": OPERATION_DOC_URL,
                "doc_fetch_date": DOC_FETCH_DATE,
                "request_bytes": len(str(body).encode("utf-8")),
                "started_at": started.isoformat(),
                "finished_at": self._clock().isoformat(),
                "agency_company_id": spec.agency_company_id,
                "rail": PUBLIC_RAIL,
                "fallback_rail": PRIVATE_FALLBACK_RAIL,
                "fallback_note": PRIVATE_FALLBACK_NOTE,
                "plan_fact": {
                    "agency_pro": plan_fact.agency_pro,
                    "source": plan_fact.source,
                    "eligible": plan_fact.eligible(),
                },
                "dry_run": bool(dry_run),
                "mutation_performed": False,
            }
            if extra:
                evidence.update(dict(extra))
            return OperationResult(
                status=status,
                operation_id=OPERATION_ID,
                receipt_id=receipt_id,
                request_fingerprint=fingerprint,
                http_status=http_status,
                response_fingerprint=response_fp,
                tenant=spec.agency_company_id,
                attempt=attempt,
                version_header=OPERATION.version,
                readback=readback,
                adapter_version=ADAPTER_VERSION,
                transport="http",
                doc_url=OPERATION_DOC_URL,
                evidence=evidence,
                error=error,
            )

        # 1. Per-tenant plan fact.  Unknown is not eligible.
        if not plan_fact.eligible():
            return finish(
                Status.denied,
                error={
                    "rule": "agency_plan_not_eligible_for_tenant",
                    "agency_pro": plan_fact.agency_pro,
                    "source": plan_fact.source,
                    "fallback": PRIVATE_FALLBACK_RAIL,
                },
                extra={"refused_before_transport": True},
            )

        # 2. Capability gate (write readiness includes canary evidence).
        capability_error = self._capability_error(spec)
        if capability_error is not None:
            return finish(
                Status.denied,
                error=capability_error,
                extra={"refused_before_transport": True},
            )

        # 3. Approval: verified, unexpired, bound to this exact object.
        require_agency_approval(approval, approval_verifier, spec=spec)

        # 4. Compile-only dry run: no mutating network call, nothing recorded.
        if dry_run:
            return finish(
                Status.ok,
                extra={
                    "dry_run": True,
                    "next_action": "dispatch",
                    "compiled_body_keys": sorted(body),
                },
            )

        seen = self._ledger.lookup(key.value)
        if seen is not None and seen != fingerprint:
            return finish(
                Status.conflict,
                error={"rule": "idempotency_key_reuse"},
                extra={"refused_before_transport": True},
            )
        self._ledger.record(key.value, fingerprint)

        # 5. One transport call.  No location credential, no locationId.
        transport_exception: str | None = None
        try:
            response: TransportResponse = self._transport.request(
                method=OPERATION_METHOD,
                url=OPERATION_PATH,
                version=OPERATION.version,
                headers=agency_headers(self._auth),
                query=None,
                body=body,
                timeout_s=timeout,
            )
        except Exception as caught:  # noqa: BLE001 - never escape without a receipt
            transport_exception = type(caught).__name__
            response = TransportResponse(None, {}, b"", "unknown", None)

        http_status = response.status if response.error_kind == "none" else None
        response_fp = response_fingerprint(response.body)
        status = _derive_status(
            http_status=http_status, error_kind=response.error_kind, write=True
        )
        parsed = _parse_body(response)

        readback: ReadbackResult | None = None
        native_id = ""
        if status is Status.ok:
            native_id = _location_id_from_body(parsed)
            if not native_id:
                status = Status.unknown_outcome
                status_rule = "create_response_missing_id"
            else:
                readback, readback_http = self._readback(
                    native_id, spec, timeout=timeout, attempt=attempt
                )
                http_status = readback_http if readback_http is not None else http_status
                if readback.result is ReadbackStatus.verified:
                    status = Status.ok
                elif readback.result is ReadbackStatus.absent:
                    status = Status.not_found
                else:
                    status = Status.unknown_outcome
                status_rule = "readback_" + readback.result.value
        else:
            status_rule = "http_or_transport_error"

        error: Mapping[str, Any] | None = None
        if status is not Status.ok:
            error = {"rule": status_rule}
            if transport_exception:
                error = {"rule": "transport_" + response.error_kind,
                         "transport_exception": transport_exception}
            elif http_status is not None:
                error = {**error, "http_status": http_status}
            if status is Status.unknown_outcome:
                self._pending[receipt_id] = (native_id, spec, key.value)

        return finish(
            status,
            error=error,
            http_status=http_status,
            response_fp=response_fp,
            readback=readback,
            extra={
                "native_location_id": native_id or None,
                "response_headers": dict(response.headers),
                "elapsed_s": response.elapsed_s,
                "mutation_performed": status in (Status.ok, Status.unknown_outcome),
            },
        )

    def reconcile(self, prior: OperationResult) -> OperationResult:
        """Re-read the same native location after an unknown outcome.

        A create that returned no native id cannot be guessed: reconciliation
        refuses rather than searching by a possibly duplicate name.
        """

        if not isinstance(prior, OperationResult):
            raise ContractViolation("reconcile_prior_invalid")
        if prior.status is not Status.unknown_outcome:
            raise ContractViolation(
                "reconcile_requires_unknown_outcome",
                operation_id=OPERATION_ID,
                detail={"status": prior.status.value},
            )
        held = self._pending.get(prior.receipt_id)
        if held is None:
            raise ContractViolation(
                "reconcile_unknown_receipt",
                operation_id=OPERATION_ID,
                detail={"receipt_id": prior.receipt_id},
            )
        native_id, spec, _key = held
        if not native_id:
            raise ContractViolation(
                "reconcile_requires_native_location_id",
                operation_id=OPERATION_ID,
                detail={"reason": "create_response_carried_no_id"},
            )
        readback, http_status = self._readback(
            native_id, spec, timeout=self._timeout, attempt=prior.attempt
        )
        status = {
            ReadbackStatus.verified: Status.ok,
            ReadbackStatus.absent: Status.not_found,
            ReadbackStatus.mismatch: Status.conflict,
            ReadbackStatus.unreadable: Status.unavailable,
        }[readback.result]
        if readback.result is not ReadbackStatus.unreadable:
            self._pending.pop(prior.receipt_id, None)
        receipt_id = "gxo_agency_res_" + secrets.token_hex(6)
        now = self._clock()
        evidence = dict(prior.evidence)
        evidence.update(
            {
                "receipt_id": receipt_id,
                "http_status": http_status,
                "readback": readback.result.value,
                "response_fingerprint": readback.detail.get("response_fingerprint"),
                "reconciled_from": prior.receipt_id,
                "reconcile": True,
                "finished_at": now.isoformat(),
            }
        )
        return OperationResult(
            status=status,
            operation_id=OPERATION_ID,
            receipt_id=receipt_id,
            request_fingerprint=prior.request_fingerprint,
            http_status=http_status,
            response_fingerprint=readback.detail.get("response_fingerprint"),
            tenant=spec.agency_company_id,
            attempt=prior.attempt,
            version_header=OPERATION.version,
            readback=readback,
            adapter_version=ADAPTER_VERSION,
            transport="http",
            doc_url=OPERATION_DOC_URL,
            evidence=evidence,
            error=None if status is Status.ok else {"rule": "reconcile_" + readback.result.value},
        )

    # -- internals --------------------------------------------------------

    def _capability_error(self, spec: AgencyLocationSpec) -> Mapping[str, Any] | None:
        capability = self._capability
        if not isinstance(capability, Capability):
            return {
                "rule": "capability_disabled",
                "operation_id": OPERATION_ID,
                "reason": "no capability record was supplied; the gate is default-deny",
                "fallback": PRIVATE_FALLBACK_RAIL,
            }
        if capability.operation_id != OPERATION_ID:
            raise ContractViolation(
                "capability_operation_mismatch",
                operation_id=OPERATION_ID,
                detail={"capability": capability.operation_id},
            )
        if capability.tenant not in (None, spec.agency_company_id):
            return {
                "rule": "capability_tenant_mismatch",
                "operation_id": OPERATION_ID,
                "fallback": PRIVATE_FALLBACK_RAIL,
            }
        if not capability.enabled or not capability.write_ready():
            block = capability.activation_blocked
            return {
                "rule": "capability_disabled",
                "operation_id": OPERATION_ID,
                "reason": block.reason if block else "capability is not write-ready",
                "fallback": PRIVATE_FALLBACK_RAIL,
            }
        return None

    def _readback(
        self,
        native_id: str,
        spec: AgencyLocationSpec,
        *,
        timeout: float,
        attempt: int,
    ) -> tuple[ReadbackResult, int | None]:
        path = "/locations/" + quote(native_id, safe="")
        try:
            response = self._transport.request(
                method="GET",
                url=path,
                version=OPERATION.version,
                headers=agency_headers(self._auth),
                query=None,
                body=None,
                timeout_s=timeout,
            )
        except Exception:  # noqa: BLE001 - a read failure is never a success
            return (
                ReadbackResult(
                    result=ReadbackStatus.unreadable,
                    operation_id="locations.get",
                    attempt=attempt,
                    detail={"reason": "readback_transport_error"},
                    evidence={"readback_path": path},
                ),
                None,
            )
        http_status = response.status if response.error_kind == "none" else None
        detail = {
            "http_status": http_status,
            "error_kind": response.error_kind,
            "response_fingerprint": response_fingerprint(response.body),
        }
        if response.error_kind != "none" or http_status is None:
            outcome = ReadbackStatus.unreadable
        elif http_status in (401, 403):
            outcome = ReadbackStatus.unreadable
        elif http_status == 404:
            outcome = ReadbackStatus.absent
        elif not (200 <= http_status < 300):
            outcome = ReadbackStatus.unreadable
        else:
            parsed = _parse_body(response)
            got_id = _location_id_from_body(parsed)
            record = parsed.get("location") if isinstance(parsed, Mapping) else None
            got_name = None
            if isinstance(record, Mapping):
                got_name = record.get("name")
            elif isinstance(parsed, Mapping):
                got_name = parsed.get("name")
            if got_id != native_id:
                outcome = ReadbackStatus.mismatch
            elif str(got_name or "") != spec.name.strip():
                outcome = ReadbackStatus.mismatch
            else:
                outcome = ReadbackStatus.verified
        return (
            ReadbackResult(
                result=outcome,
                operation_id="locations.get",
                attempt=attempt,
                detail=detail,
                evidence={
                    "readback_method": "GET",
                    "readback_path": path,
                    "tenant": spec.agency_company_id,
                },
            ),
            http_status,
        )


def _parse_body(response: TransportResponse) -> Any:
    import json

    if not response.body:
        return None
    try:
        return json.loads(response.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def result_summary(result: OperationResult) -> dict[str, Any]:
    """JSON-safe projection for a CLI.  Never includes a credential value."""

    return {
        "status": result.status.value,
        "operation_id": result.operation_id,
        "receipt_id": result.receipt_id,
        "http_status": result.http_status,
        "tenant": result.tenant,
        "version_header": result.version_header,
        "readback": result.readback.result.value if result.readback else None,
        "error": dict(result.error) if result.error else None,
        "native_location_id": result.evidence.get("native_location_id"),
        "rail": result.evidence.get("rail"),
        "fallback_rail": result.evidence.get("fallback_rail"),
        "fallback_note": result.evidence.get("fallback_note"),
        "dry_run": result.evidence.get("dry_run"),
        "mutation_performed": result.evidence.get("mutation_performed"),
    }


__all__ = [
    "OPERATION_ID",
    "OPERATION_METHOD",
    "OPERATION_PATH",
    "OPERATION.version",
    "OPERATION_SCOPES",
    "APPROVAL_KIND",
    "APPROVAL_ACTION",
    "PUBLIC_RAIL",
    "PRIVATE_FALLBACK_RAIL",
    "PRIVATE_FALLBACK_NOTE",
    "AgencyAuthContext",
    "resolve_agency_auth",
    "agency_headers",
    "guard_agency_company_id",
    "PlanFact",
    "PlanFacts",
    "AgencyLocationSpec",
    "location_request_body",
    "approval_object_key",
    "require_agency_approval",
    "RouteDecision",
    "route_decision",
    "AgencyAdapter",
    "result_summary",
]
