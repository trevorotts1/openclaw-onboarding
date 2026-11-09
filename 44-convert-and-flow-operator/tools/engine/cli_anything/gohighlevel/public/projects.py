"""GHL Projects: availability, typed operations, CRUD, pagination and readback.

WF32 / GHL-032, contract BCM-GHL-HYBRID-2026-11-08 rev 3.0, Document 1 section 29.

The Projects surface is private-beta.  No Projects specification is checked into
this repository, and the public HighLevel OpenAPI repository carries no Projects
document (``apps/projects.json`` and ``apps/v3/projects.json`` both 404 on
2026-11-08).  Operation paths, per-operation ``Version`` headers, scope names and
wire field names are therefore UNRESOLVED in code.  They arrive only through a
discovery document (WF15 Skill 36 ``describe_operation`` evidence) or through the
explicit fixture catalog below, which is refused unless the caller opts in and is
stamped ``fixture`` on every outcome.

Behaviour that IS documented and implemented here, catalog-driven on the wire:

* credential bound to the location before transport; ``locationId`` is never
  sent for a token-derived binding;
* UI/Labs availability and API beta availability are separate facts and neither
  is inferred from the other;
* a created space's default list is discovered, never assumed or duplicated;
* task writes resolve a real list status (no guessed status, no derived
  ``statusGroup``), need a title and an approved ISO 8601 ``dueDate``, and accept
  at most one assignee (never a silent pick among several);
* subtasks use ``parentTaskId`` and inherit the parent's home list;
* adding a task to another list preserves identity and the home list is verified
  before and after;
* comments and structured recurrence go through their own operations (an RRULE
  string is refused);
* private-space membership removal uses the documented removal operation and is
  proved absent; omission from an additive update is never read as removal;
* every endpoint carries its own pagination style (cursor, search-after,
  skip/limit) with duplicate and missing-record detection;
* ``dueDate`` normalisation preserves timezone intent and refuses naive
  datetimes; past dates are refused rather than invented;
* parent deletion is impact-aware: it requires an authorization bound to the
  exact impact report fingerprint.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .adapter import ApprovalRef, PublicGhlAdapter
from .auth import AuthContext, AuthKind, TenantBinding
from .errors import ContractViolation
from .idempotency import IdempotencyKey
from .readback import ReadbackRegistry, ReadbackSpec
from .result import OperationResult, Status, canonical_json
from .transport import (
    DEFAULT_BASE_URL,
    RequestsTransport,
    Transport,
    TransportResponse,
)

PROJECTS_MODULE_VERSION = "wf32-0.1"
EVIDENCE_DISCOVERY = "discovery"
EVIDENCE_FIXTURE = "fixture"
PROJECT_AUTH_KINDS: tuple[AuthKind, ...] = (AuthKind.location_pit, AuthKind.oauth)

# ---------------------------------------------------------------------------
# operation ids (stable interface; the wire contract is catalog-supplied)
# ---------------------------------------------------------------------------

SPACE_CREATE = "projects.spaces.create"
SPACE_LIST = "projects.spaces.list"
SPACE_GET = "projects.spaces.get"
SPACE_DELETE = "projects.spaces.delete"
FOLDER_CREATE = "projects.folders.create"
LIST_CREATE = "projects.lists.create"
LIST_LIST = "projects.lists.list"
LIST_GET = "projects.lists.get"
LIST_STATUSES = "projects.lists.statuses.list"
LIST_DELETE = "projects.lists.delete"
TASK_CREATE = "projects.tasks.create"
TASK_GET = "projects.tasks.get"
TASK_LIST = "projects.tasks.list"
TASK_UPDATE = "projects.tasks.update"
TASK_ADD_TO_LIST = "projects.tasks.addToList"
COMMENT_CREATE = "projects.tasks.comments.create"
COMMENT_LIST = "projects.tasks.comments.list"
RECURRENCE_SET = "projects.tasks.recurrence.set"
MEMBER_LIST = "projects.spaces.members.list"
MEMBER_UPDATE = "projects.spaces.members.update"
MEMBER_REMOVE = "projects.spaces.members.remove"

REQUIRED_OPERATION_IDS: frozenset[str] = frozenset(
    {
        SPACE_CREATE,
        SPACE_LIST,
        SPACE_GET,
        SPACE_DELETE,
        FOLDER_CREATE,
        LIST_CREATE,
        LIST_LIST,
        LIST_GET,
        LIST_STATUSES,
        LIST_DELETE,
        TASK_CREATE,
        TASK_GET,
        TASK_LIST,
        TASK_UPDATE,
        TASK_ADD_TO_LIST,
        COMMENT_CREATE,
        COMMENT_LIST,
        RECURRENCE_SET,
        MEMBER_LIST,
        MEMBER_UPDATE,
        MEMBER_REMOVE,
    }
)


class LocationBinding(str, Enum):
    """How a credential's location reaches the request, if at all."""

    token_derived = "token_derived"
    path = "path"
    body = "body"
    query = "query"


_ADAPTER_BINDING = {
    LocationBinding.token_derived: "none",
    LocationBinding.path: "path.locationId",
    LocationBinding.body: "body.locationId",
    LocationBinding.query: "query.locationId",
}


class PaginationStyle(str, Enum):
    cursor = "cursor"
    search_after = "search_after"
    skip_limit = "skip_limit"


@dataclass(frozen=True)
class PaginationSpec:
    style: PaginationStyle
    limit: int = 50
    token_param: str | None = None
    token_field: str | None = None
    token_from_item: str | None = None
    limit_param: str = "limit"
    skip_param: str = "skip"
    total_field: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "style", PaginationStyle(self.style))
        if not isinstance(self.limit, int) or self.limit < 1:
            raise ContractViolation("projects_pagination_limit_invalid")
        if self.style in (PaginationStyle.cursor, PaginationStyle.search_after):
            if not self.token_param or not (self.token_field or self.token_from_item):
                raise ContractViolation(
                    "projects_pagination_token_unresolved",
                    detail={"style": self.style.value},
                )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PaginationSpec":
        allowed = {
            "style",
            "limit",
            "token_param",
            "token_field",
            "token_from_item",
            "limit_param",
            "skip_param",
            "total_field",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ContractViolation(
                "projects_pagination_unknown_field", detail={"fields": unknown}
            )
        return cls(**dict(value))


@dataclass(frozen=True)
class ProjectsOperation:
    """One Projects operation, fully described by evidence or by a fixture."""

    operation_id: str
    method: str
    path_template: str
    version: str | None
    write: bool = False
    approval_required: bool = False
    location_binding: LocationBinding = LocationBinding.token_derived
    evidence: str = EVIDENCE_FIXTURE
    doc_url: str | None = None
    doc_fetch_date: str | None = None
    scopes: tuple[str, ...] = ()
    path_sources: tuple[tuple[str, str], ...] = ()
    query_sources: tuple[tuple[str, str], ...] = ()
    body_fields: Mapping[str, str] = field(default_factory=dict)
    pagination: PaginationSpec | None = None
    collection_field: str | None = None
    id_field: str = "id"
    fields: Mapping[str, str] = field(default_factory=dict)
    readback_operation: str | None = None
    readback_path_sources: tuple[tuple[str, str], ...] = ()
    readback_query_sources: tuple[tuple[str, str], ...] = ()
    readback_expect: Mapping[str, str] = field(default_factory=dict)
    verify_operation: str | None = None
    verify_path_sources: tuple[tuple[str, str], ...] = ()
    verify_query_sources: tuple[tuple[str, str], ...] = ()
    default_field: str | None = None
    default_value: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "location_binding", LocationBinding(self.location_binding)
        )
        if not isinstance(self.operation_id, str) or not self.operation_id.strip():
            raise ContractViolation("projects_operation_id_missing")
        for name in ("method", "path_template"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ContractViolation(
                    "projects_operation_incomplete",
                    operation_id=self.operation_id,
                    detail={"field": name},
                )
        if self.version is not None and not isinstance(self.version, str):
            raise ContractViolation(
                "projects_version_invalid", operation_id=self.operation_id
            )
        if self.evidence not in (EVIDENCE_DISCOVERY, EVIDENCE_FIXTURE):
            raise ContractViolation(
                "projects_evidence_invalid", operation_id=self.operation_id
            )
        for label, sources in (
            ("path_sources", self.path_sources),
            ("query_sources", self.query_sources),
            ("readback_path_sources", self.readback_path_sources),
            ("readback_query_sources", self.readback_query_sources),
            ("verify_path_sources", self.verify_path_sources),
            ("verify_query_sources", self.verify_query_sources),
        ):
            for entry in sources:
                if (
                    not isinstance(entry, tuple)
                    or len(entry) != 2
                    or not all(isinstance(item, str) and item for item in entry)
                ):
                    raise ContractViolation(
                        "projects_source_invalid",
                        operation_id=self.operation_id,
                        detail={"field": label},
                    )
        names = _template_params(self.path_template)
        declared = {param for param, _ in self.path_sources}
        if names != declared:
            raise ContractViolation(
                "projects_path_sources_mismatch",
                operation_id=self.operation_id,
                detail={
                    "missing": sorted(names - declared),
                    "extra": sorted(declared - names),
                },
            )
        if self.pagination is not None and not self.collection_field:
            raise ContractViolation(
                "projects_collection_unresolved", operation_id=self.operation_id
            )
        if self.write and not self.readback_operation:
            raise ContractViolation(
                "projects_readback_unresolved", operation_id=self.operation_id
            )
        if self.write and self.readback_expect == {}:
            # A write's mandatory read-back must carry a real expectation; the
            # adapter refuses a vacuous plan and so does this catalog.
            raise ContractViolation(
                "projects_readback_unresolved",
                operation_id=self.operation_id,
                detail={"field": "readback_expect"},
            )
        if self.default_field is not None and self.default_value is None:
            raise ContractViolation(
                "projects_default_marker_invalid", operation_id=self.operation_id
            )
        if self.operation_id in _CREATE_OPERATIONS and not self.verify_operation:
            raise ContractViolation(
                "projects_verification_unresolved", operation_id=self.operation_id
            )

    def adapter_row(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "method": self.method,
            "path_template": self.path_template,
            "version": self.version,
            "write": bool(self.write),
            "approval_required": bool(self.approval_required),
            "route_class": "public_direct",
            "auth_kinds": PROJECT_AUTH_KINDS,
            "tenant_binding": _ADAPTER_BINDING[self.location_binding],
            "scopes_candidate": tuple(self.scopes),
            "doc_url": self.doc_url,
            "doc_fetch_date": self.doc_fetch_date,
            "required_query": (),
            "query_enums": (),
        }

    def as_interface(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "method": self.method,
            "path_template": self.path_template,
            "version": self.version,
            "write": self.write,
            "approval_required": self.approval_required,
            "location_binding": self.location_binding.value,
            "evidence": self.evidence,
            "pagination": (
                {"style": self.pagination.style.value}
                if self.pagination is not None
                else None
            ),
            "readback_operation": self.readback_operation,
            "verify_operation": self.verify_operation,
        }


_CREATE_OPERATIONS: frozenset[str] = frozenset(
    {SPACE_CREATE, LIST_CREATE, TASK_CREATE}
)


# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------


class ProjectsCatalog:
    """Operation table.  ``discovery`` is the only production evidence."""

    def __init__(
        self,
        operations: Iterable[ProjectsOperation],
        *,
        evidence: str,
        source: str,
    ) -> None:
        if evidence not in (EVIDENCE_DISCOVERY, EVIDENCE_FIXTURE):
            raise ContractViolation("projects_catalog_evidence_invalid")
        if not isinstance(source, str) or not source.strip():
            raise ContractViolation("projects_catalog_source_missing")
        if evidence == EVIDENCE_DISCOVERY and source == EVIDENCE_FIXTURE:
            raise ContractViolation("projects_catalog_source_invalid")
        table: dict[str, ProjectsOperation] = {}
        for row in operations:
            if not isinstance(row, ProjectsOperation):
                raise ContractViolation("projects_operation_invalid")
            if row.evidence != evidence:
                raise ContractViolation(
                    "projects_catalog_mixed_evidence",
                    operation_id=row.operation_id,
                )
            if row.operation_id in table:
                raise ContractViolation(
                    "projects_duplicate_operation", operation_id=row.operation_id
                )
            table[row.operation_id] = row
        missing = sorted(REQUIRED_OPERATION_IDS - set(table))
        if missing:
            raise ContractViolation(
                "projects_catalog_incomplete", detail={"missing": missing}
            )
        for row in table.values():
            for reference in (row.readback_operation, row.verify_operation):
                if reference is not None and reference not in table:
                    raise ContractViolation(
                        "projects_catalog_reference_unknown",
                        operation_id=row.operation_id,
                        detail={"reference": reference},
                    )
                if reference is not None and table[reference].write:
                    raise ContractViolation(
                        "projects_readback_targets_write",
                        operation_id=row.operation_id,
                        detail={"reference": reference},
                    )
        self._table = table
        self.evidence = evidence
        self.source = source

    @property
    def operation_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._table))

    def row(self, operation_id: str) -> ProjectsOperation:
        try:
            return self._table[str(operation_id)]
        except KeyError:
            raise ContractViolation(
                "projects_operation_unknown", detail={"operation_id": str(operation_id)}
            ) from None

    def has(self, operation_id: str) -> bool:
        return str(operation_id) in self._table

    def adapter_registry(self) -> dict[str, dict[str, Any]]:
        return {key: row.adapter_row() for key, row in self._table.items()}

    def as_interface(self) -> list[dict[str, Any]]:
        return [self._table[key].as_interface() for key in self.operation_ids]

    @classmethod
    def from_document(
        cls, document: Mapping[str, Any], *, source: str | None = None
    ) -> "ProjectsCatalog":
        if not isinstance(document, Mapping):
            raise ContractViolation("projects_discovery_invalid")
        evidence = str(document.get("evidence", EVIDENCE_DISCOVERY))
        rows_doc = document.get("operations")
        if not isinstance(rows_doc, Mapping) or not rows_doc:
            raise ContractViolation(
                "projects_discovery_incomplete", detail={"field": "operations"}
            )
        rows: list[ProjectsOperation] = []
        for operation_id, spec in rows_doc.items():
            if not isinstance(spec, Mapping):
                raise ContractViolation(
                    "projects_discovery_incomplete",
                    operation_id=str(operation_id),
                    detail={"field": "operation"},
                )
            missing = [
                name for name in ("method", "path_template", "version") if name not in spec
            ]
            if missing:
                raise ContractViolation(
                    "projects_discovery_incomplete",
                    operation_id=str(operation_id),
                    detail={"missing": missing},
                )
            pagination = spec.get("pagination")
            rows.append(
                ProjectsOperation(
                    operation_id=str(operation_id),
                    method=str(spec["method"]),
                    path_template=str(spec["path_template"]),
                    version=None if spec["version"] is None else str(spec["version"]),
                    write=bool(spec.get("write", False)),
                    approval_required=bool(spec.get("approval_required", False)),
                    location_binding=LocationBinding(
                        spec.get("location_binding", "token_derived")
                    ),
                    evidence=evidence,
                    doc_url=spec.get("doc_url"),
                    doc_fetch_date=spec.get("doc_fetch_date"),
                    scopes=tuple(spec.get("scopes") or ()),
                    path_sources=_pairs(spec.get("path_sources")),
                    query_sources=_pairs(spec.get("query_sources")),
                    body_fields=dict(spec.get("body_fields") or {}),
                    pagination=(
                        PaginationSpec.from_mapping(pagination)
                        if isinstance(pagination, Mapping)
                        else None
                    ),
                    collection_field=spec.get("collection_field"),
                    id_field=str(spec.get("id_field", "id")),
                    fields=dict(spec.get("fields") or {}),
                    readback_operation=spec.get("readback_operation"),
                    readback_path_sources=_pairs(spec.get("readback_path_sources")),
                    readback_query_sources=_pairs(spec.get("readback_query_sources")),
                    readback_expect=dict(spec.get("readback_expect") or {}),
                    verify_operation=spec.get("verify_operation"),
                    verify_path_sources=_pairs(spec.get("verify_path_sources")),
                    verify_query_sources=_pairs(spec.get("verify_query_sources")),
                    default_field=spec.get("default_field"),
                    default_value=spec.get("default_value"),
                )
            )
        return cls(
            rows,
            evidence=evidence,
            source=source or str(document.get("source") or "discovery"),
        )

    @classmethod
    def fixture(cls) -> "ProjectsCatalog":
        return cls(
            _fixture_operations(),
            evidence=EVIDENCE_FIXTURE,
            source="wf32-synthetic-fixture",
        )


def _pairs(value: Any) -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    for entry in value or ():
        out.append((str(entry[0]), str(entry[1])))
    return tuple(out)


def _template_params(template: str) -> set[str]:
    names: set[str] = set()
    depth = 0
    start = 0
    for index, char in enumerate(template):
        if char == "{":
            depth += 1
            start = index + 1
        elif char == "}":
            if depth == 1:
                names.add(template[start:index])
            depth = max(0, depth - 1)
    return names


# ---------------------------------------------------------------------------
# availability (UI/Labs and API beta are independent)
# ---------------------------------------------------------------------------


class AvailabilityState(str, Enum):
    unknown = "unknown"
    available = "available"
    not_available = "not_available"
    forbidden = "forbidden"


DIMENSIONS = ("ui_labs", "api_beta")


@dataclass(frozen=True)
class AvailabilityEvidence:
    dimension: str
    state: AvailabilityState
    source: str
    reference: str
    checked_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", AvailabilityState(self.state))
        if self.dimension not in DIMENSIONS:
            raise ContractViolation(
                "projects_availability_dimension_invalid",
                detail={"dimension": self.dimension},
            )
        for name in ("source", "reference", "checked_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ContractViolation(
                    "projects_availability_evidence_incomplete",
                    detail={"dimension": self.dimension, "field": name},
                )
        if self.dimension == "api_beta" and self.source.strip().lower().startswith("ui"):
            # A UI/Labs observation can never stand in for an API entitlement.
            raise ContractViolation(
                "projects_api_availability_inferred_from_ui",
                detail={"source": self.source},
            )

    @classmethod
    def unknown(cls, dimension: str) -> "AvailabilityEvidence":
        return cls(
            dimension=dimension,
            state=AvailabilityState.unknown,
            source="not_checked",
            reference="wf32:no-check",
            checked_at="1970-01-01T00:00:00+00:00",
        )


@dataclass(frozen=True)
class ProjectsAvailability:
    ui_labs: AvailabilityEvidence
    api_beta: AvailabilityEvidence

    def __post_init__(self) -> None:
        if self.ui_labs.dimension != "ui_labs":
            raise ContractViolation("projects_availability_dimension_mixed")
        if self.api_beta.dimension != "api_beta":
            raise ContractViolation("projects_availability_dimension_mixed")

    @classmethod
    def unknown(cls) -> "ProjectsAvailability":
        return cls(
            ui_labs=AvailabilityEvidence.unknown("ui_labs"),
            api_beta=AvailabilityEvidence.unknown("api_beta"),
        )

    @classmethod
    def from_records(
        cls, *, ui_labs: AvailabilityEvidence, api_beta: AvailabilityEvidence
    ) -> "ProjectsAvailability":
        return cls(ui_labs=ui_labs, api_beta=api_beta)

    def require_ui(self) -> None:
        _require_available(self.ui_labs)

    def require_api(self) -> None:
        _require_available(self.api_beta)

    def as_mapping(self) -> dict[str, Any]:
        return {
            "ui_labs": _evidence_mapping(self.ui_labs),
            "api_beta": _evidence_mapping(self.api_beta),
            "independent": True,
        }


def _require_available(evidence: AvailabilityEvidence) -> None:
    if evidence.state is not AvailabilityState.available:
        raise ContractViolation(
            "projects_feature_unavailable",
            detail={
                "dimension": evidence.dimension,
                "state": evidence.state.value,
                "source": evidence.source,
                "reference": evidence.reference,
            },
        )


def _evidence_mapping(evidence: AvailabilityEvidence) -> dict[str, str]:
    return {
        "state": evidence.state.value,
        "source": evidence.source,
        "reference": evidence.reference,
        "checked_at": evidence.checked_at,
    }


def classify_denial(
    result: OperationResult, *, beta_error_code: str | None = None
) -> AvailabilityState:
    """Classify a refused call for the API-beta dimension only.

    Without an explicit beta marker the honest answer is ``forbidden`` (a real
    permission refusal), never ``not_available`` by guess.
    """

    if result.status is Status.ok:
        return AvailabilityState.available
    if result.status is not Status.denied:
        return AvailabilityState.unknown
    error = dict(result.error or {})
    codes = {
        str(value)
        for key, value in error.items()
        if key in ("code", "rule", "beta_code", "error_code")
    }
    if beta_error_code and beta_error_code in codes:
        return AvailabilityState.not_available
    return AvailabilityState.forbidden


# ---------------------------------------------------------------------------
# dates, assignees, impact authorization
# ---------------------------------------------------------------------------


def normalize_due_date(value: Any, *, today: date | None = None) -> str:
    """Accepted date inputs only; timezone intent is preserved.

    A date keeps date-only ISO form.  A datetime must carry an offset; a naive
    datetime is refused rather than guessed.  Past dates are refused: a due date
    is approved work, never filler.
    """

    if value is None or (isinstance(value, str) and not value.strip()):
        raise ContractViolation("projects_due_date_required")
    parsed: date | datetime
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        try:
            parsed = date.fromisoformat(text)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(
                    text[:-1] + "+00:00" if text.endswith("Z") else text
                )
            except ValueError:
                raise ContractViolation(
                    "projects_due_date_invalid", detail={"format": "iso-8601"}
                ) from None
    else:
        raise ContractViolation(
            "projects_due_date_invalid", detail={"type": type(value).__name__}
        )

    if isinstance(parsed, datetime):
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ContractViolation("projects_due_date_timezone_required")
        marker = parsed.date()
        text = parsed.isoformat()
    else:
        marker = parsed
        text = parsed.isoformat()
    current = today or datetime.now(timezone.utc).date()
    if marker < current:
        raise ContractViolation("projects_due_date_in_past", detail={"due_date": text})
    return text


def single_assignee(
    assignee_id: str | None, assignee_ids: Sequence[str] = ()
) -> str | None:
    """At most one assignee; several are refused, never silently chosen."""

    ids = [str(item) for item in assignee_ids if item]
    if assignee_id:
        if ids:
            raise ContractViolation("projects_multiple_assignees")
        return str(assignee_id)
    if len(ids) > 1:
        raise ContractViolation("projects_multiple_assignees", detail={"count": len(ids)})
    return ids[0] if ids else None


@dataclass(frozen=True)
class ImpactReport:
    operation_id: str
    target_id: str
    child_count: int
    child_ids: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True)
class ImpactAuthorization:
    report_fingerprint: str
    approved_by: str
    reference: str

    def __post_init__(self) -> None:
        for name in ("report_fingerprint", "approved_by", "reference"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ContractViolation(
                    "projects_impact_authorization_incomplete",
                    detail={"field": name},
                )


# ---------------------------------------------------------------------------
# results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectsObject:
    kind: str
    id: str
    data: Mapping[str, Any]
    result: OperationResult | None
    verified: bool
    verification: str


@dataclass(frozen=True)
class Page:
    operation_id: str
    records: tuple[Mapping[str, Any], ...]
    pages: int
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class _Recorded:
    url: str
    parsed: Any


class _RecordingTransport:
    """Wrap the transport to expose the primary response body to the service.

    The adapter returns fingerprints, not payloads.  The service snapshots the
    event count before each call, so event[index] is always that call's primary
    request; read-back requests follow it.
    """

    def __init__(self, inner: Transport) -> None:
        self._inner = inner
        self.events: list[_Recorded] = []

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
        parsed: Any = None
        if response.error_kind == "none" and response.body:
            try:
                parsed = json.loads(response.body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                parsed = None
        self.events.append(_Recorded(url=url, parsed=parsed))
        return response


# ---------------------------------------------------------------------------
# service
# ---------------------------------------------------------------------------


class ProjectsService:
    """Documented Projects behaviour over one bound tenant and one catalog."""

    def __init__(
        self,
        *,
        adapter: PublicGhlAdapter,
        catalog: ProjectsCatalog,
        tenant: TenantBinding,
        recorder: _RecordingTransport,
        clock: Any = None,
    ) -> None:
        self._adapter = adapter
        self._catalog = catalog
        self._tenant = tenant
        self._recorder = recorder
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # -- construction -----------------------------------------------------

    @classmethod
    def connect(
        cls,
        *,
        auth: AuthContext,
        tenant: TenantBinding,
        catalog: ProjectsCatalog,
        transport: Transport | None = None,
        gate: Any = None,
        readbacks: ReadbackRegistry | None = None,
        allow_fixture: bool = False,
        clock: Any = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> "ProjectsService":
        if not isinstance(auth, AuthContext):
            raise ContractViolation("projects_auth_invalid")
        if not isinstance(tenant, TenantBinding):
            raise ContractViolation("projects_tenant_required")
        # Credential bound to the location before transport.
        if auth.location_id is not None and auth.location_id != tenant.location_id:
            raise ContractViolation(
                "projects_tenant_not_bound",
                detail={"reason": "credential location differs from call tenant"},
            )
        if catalog.evidence == EVIDENCE_FIXTURE and not allow_fixture:
            raise ContractViolation(
                "projects_fixture_catalog_refused",
                detail={
                    "hint": (
                        "supply the WF15 Skill 36 discovery document, or pass "
                        "allow_fixture=True for an explicitly synthetic run"
                    )
                },
            )
        recorder = _RecordingTransport(
            transport if transport is not None else RequestsTransport(base_url=base_url)
        )
        adapter = PublicGhlAdapter(
            auth=auth,
            operations=catalog.adapter_registry(),
            transport=recorder,
            capability=gate,
            readbacks=readbacks if readbacks is not None else ReadbackRegistry(),
            clock=clock,
        )
        return cls(
            adapter=adapter,
            catalog=catalog,
            tenant=tenant,
            recorder=recorder,
            clock=clock,
        )

    @property
    def catalog(self) -> ProjectsCatalog:
        return self._catalog

    @property
    def fixture(self) -> bool:
        return self._catalog.evidence == EVIDENCE_FIXTURE

    # -- spaces -----------------------------------------------------------

    def create_space(
        self,
        name: str,
        *,
        description: str | None = None,
        private: bool | None = None,
        folder_id: str | None = None,
    ) -> ProjectsObject:
        if not isinstance(name, str) or not name.strip():
            raise ContractViolation("projects_space_name_required")
        concepts = {
            "name": name,
            "description": description,
            "private": private,
            "folder": folder_id,
        }
        result, payload = self._call(SPACE_CREATE, context={}, concepts=concepts)
        self._require_ok(result)
        space_id = self._created_id(payload, SPACE_CREATE)
        self._verify_created(SPACE_CREATE, space_id, context={})
        return ProjectsObject(
            kind="space",
            id=space_id,
            data=dict(payload or {}),
            result=result,
            verified=True,
            verification="read_by_id",
        )

    def list_spaces(self, *, limit: int | None = None) -> Page:
        return self.paginate(SPACE_LIST, context={}, limit=limit)

    def get_space(self, space_id: str) -> ProjectsObject:
        return self._read_object(SPACE_GET, "space", {"space_id": space_id})

    def discover_default_list(self, space_id: str) -> ProjectsObject | None:
        """Find the server-created default list; never create a duplicate.

        Zero lists means "none created"; more than one without a catalog-declared
        default marker is ambiguous and refused.
        """

        page = self.paginate(LIST_LIST, context={"space_id": space_id})
        row = self._catalog.row(LIST_LIST)
        records = list(page.records)
        if row.default_field:
            records = [
                record
                for record in records
                if (
                    str(record.get(row.default_field)).lower()
                    == str(row.default_value).lower()
                )
            ]
        if not records:
            return None
        if len(records) > 1:
            raise ContractViolation(
                "projects_default_list_ambiguous",
                detail={"space_id": space_id, "count": len(records)},
            )
        return ProjectsObject(
            kind="list",
            id=self._record_id(records[0], LIST_LIST),
            data=records[0],
            result=None,
            verified=True,
            verification="discovered",
        )

    # -- lists, folders, statuses ----------------------------------------

    def create_folder(self, space_id: str, name: str) -> ProjectsObject:
        if not isinstance(name, str) or not name.strip():
            raise ContractViolation("projects_folder_name_required")
        result, payload = self._call(
            FOLDER_CREATE,
            context={"space_id": space_id},
            concepts={"name": name},
        )
        self._require_ok(result)
        folder_id = self._created_id(payload, FOLDER_CREATE)
        row = self._catalog.row(FOLDER_CREATE)
        if row.verify_operation:
            self._verify_created(
                FOLDER_CREATE, folder_id, context={"space_id": space_id}
            )
        return ProjectsObject(
            kind="folder",
            id=folder_id,
            data=dict(payload or {}),
            result=result,
            verified=True,
            verification="read_by_id" if row.verify_operation else "adapter_readback",
        )

    def create_list(
        self,
        space_id: str,
        name: str,
        *,
        folder_id: str | None = None,
    ) -> ProjectsObject:
        if not isinstance(name, str) or not name.strip():
            raise ContractViolation("projects_list_name_required")
        result, payload = self._call(
            LIST_CREATE,
            context={"space_id": space_id},
            concepts={"name": name, "folder": folder_id},
        )
        self._require_ok(result)
        list_id = self._created_id(payload, LIST_CREATE)
        self._verify_created(LIST_CREATE, list_id, context={"space_id": space_id})
        return ProjectsObject(
            kind="list",
            id=list_id,
            data=dict(payload or {}),
            result=result,
            verified=True,
            verification="read_by_id",
        )

    def list_lists(self, space_id: str, *, limit: int | None = None) -> Page:
        return self.paginate(LIST_LIST, context={"space_id": space_id}, limit=limit)

    def list_statuses(self, list_id: str, *, limit: int | None = None) -> Page:
        return self.paginate(LIST_STATUSES, context={"list_id": list_id}, limit=limit)

    def resolve_status(self, list_id: str, wanted: str) -> str:
        """Resolve a real status id from the list's own statuses.

        Never derives ``statusGroup`` and never guesses a status value.
        """

        if not isinstance(wanted, str) or not wanted.strip():
            raise ContractViolation("projects_status_required")
        row = self._catalog.row(LIST_STATUSES)
        id_field = row.fields.get("id", "id")
        name_field = row.fields.get("name", "name")
        for record in self.list_statuses(list_id).records:
            if str(record.get(id_field)) == wanted:
                return wanted
            if str(record.get(name_field)) == wanted:
                return str(record.get(id_field))
        raise ContractViolation(
            "projects_status_not_in_list",
            detail={"list_id": list_id, "status": wanted},
        )

    # -- tasks ------------------------------------------------------------

    def create_task(
        self,
        title: str,
        due_date: Any,
        *,
        list_id: str,
        status: str | None = None,
        assignee_id: str | None = None,
        assignee_ids: Sequence[str] = (),
        parent_task_id: str | None = None,
        description: str | None = None,
        today: date | None = None,
    ) -> ProjectsObject:
        if not isinstance(title, str) or not title.strip():
            raise ContractViolation("projects_title_required")
        due = normalize_due_date(due_date, today=today or self._today())
        assignee = single_assignee(assignee_id, assignee_ids)
        status_id = self.resolve_status(list_id, status) if status is not None else None
        concepts = {
            "title": title,
            "dueDate": due,
            "status": status_id,
            "assignee": assignee,
            "parentTaskId": parent_task_id,
            "description": description,
        }
        result, payload = self._call(
            TASK_CREATE, context={"list_id": list_id}, concepts=concepts
        )
        self._require_ok(result)
        task_id = self._created_id(payload, TASK_CREATE)
        self._verify_created(TASK_CREATE, task_id, context={"list_id": list_id})
        return ProjectsObject(
            kind="task",
            id=task_id,
            data=dict(payload or {}),
            result=result,
            verified=True,
            verification="read_by_id",
        )

    def create_subtask(
        self,
        parent_task_id: str,
        title: str,
        due_date: Any,
        *,
        status: str | None = None,
        assignee_id: str | None = None,
        assignee_ids: Sequence[str] = (),
        description: str | None = None,
        today: date | None = None,
    ) -> ProjectsObject:
        parent = self.get_task(parent_task_id)
        home_list = self._home_list(parent)
        return self.create_task(
            title,
            due_date,
            list_id=home_list,
            status=status,
            assignee_id=assignee_id,
            assignee_ids=assignee_ids,
            parent_task_id=parent_task_id,
            description=description,
            today=today,
        )

    def get_task(self, task_id: str) -> ProjectsObject:
        return self._read_object(TASK_GET, "task", {"task_id": task_id})

    def list_tasks(self, list_id: str, *, limit: int | None = None) -> Page:
        return self.paginate(TASK_LIST, context={"list_id": list_id}, limit=limit)

    def add_task_to_list(self, task_id: str, list_id: str) -> ProjectsObject:
        """Add an existing task to another list; identity and home list hold."""

        before = self.get_task(task_id)
        home_before = self._home_list(before)
        result, payload = self._call(
            TASK_ADD_TO_LIST,
            context={"task_id": task_id},
            concepts={"list": list_id},
        )
        self._require_ok(result)
        after = self.get_task(task_id)
        if self._home_list(after) != home_before:
            raise ContractViolation(
                "projects_home_list_changed",
                detail={"task_id": task_id, "expected": home_before},
            )
        return ProjectsObject(
            kind="task",
            id=task_id,
            data=dict(after.data),
            result=result,
            verified=True,
            verification="home_list_preserved",
        )

    def add_comment(self, task_id: str, body: str) -> ProjectsObject:
        if not isinstance(body, str) or not body.strip():
            raise ContractViolation("projects_comment_body_required")
        result, payload = self._call(
            COMMENT_CREATE,
            context={"task_id": task_id},
            concepts={"comment": body},
        )
        self._require_ok(result)
        return ProjectsObject(
            kind="comment",
            id=self._optional_id(payload, COMMENT_CREATE),
            data=dict(payload or {}),
            result=result,
            verified=True,
            verification="adapter_readback",
        )

    def set_recurrence(self, task_id: str, recurrence: Mapping[str, Any]) -> ProjectsObject:
        if isinstance(recurrence, str):
            raise ContractViolation(
                "projects_rrule_forbidden",
                detail={"hint": "send the documented structured recurrence object"},
            )
        if not isinstance(recurrence, Mapping) or not recurrence:
            raise ContractViolation("projects_recurrence_invalid")
        result, payload = self._call(
            RECURRENCE_SET,
            context={"task_id": task_id},
            concepts={"recurrence": dict(recurrence)},
        )
        self._require_ok(result)
        return ProjectsObject(
            kind="task",
            id=task_id,
            data=dict(payload or {}),
            result=result,
            verified=True,
            verification="adapter_readback",
        )

    # -- members (private spaces) ----------------------------------------

    def list_members(self, space_id: str, *, limit: int | None = None) -> Page:
        return self.paginate(MEMBER_LIST, context={"space_id": space_id}, limit=limit)

    def add_members(self, space_id: str, member_ids: Sequence[str]) -> ProjectsObject:
        """Additive update only.  Omitting a member never revokes access."""

        ids = [str(item) for item in member_ids if item]
        if not ids:
            raise ContractViolation("projects_members_required")
        result, payload = self._call(
            MEMBER_UPDATE,
            context={"space_id": space_id},
            concepts={"members": ids},
        )
        self._require_ok(result)
        return ProjectsObject(
            kind="space",
            id=space_id,
            data=dict(payload or {}),
            result=result,
            verified=True,
            verification="adapter_readback",
        )

    def remove_member(
        self,
        space_id: str,
        member_id: str,
        *,
        approval: ApprovalRef | None = None,
    ) -> ProjectsObject:
        """Documented removal operation, then an explicit absence proof."""

        result, payload = self._call(
            MEMBER_REMOVE,
            context={"space_id": space_id, "member_id": member_id},
            approval=approval,
        )
        self._require_ok(result)
        row = self._catalog.row(MEMBER_LIST)
        id_field = row.fields.get("id", "id")
        still_present = [
            record
            for record in self.list_members(space_id).records
            if str(record.get(id_field)) == member_id
        ]
        if still_present:
            raise ContractViolation(
                "projects_member_still_present",
                detail={"space_id": space_id, "member_id": member_id},
            )
        return ProjectsObject(
            kind="space",
            id=space_id,
            data=dict(payload or {}),
            result=result,
            verified=True,
            verification="absence_proved",
        )

    # -- impact-aware parent deletion -------------------------------------

    def impact_report(self, list_id: str) -> ImpactReport:
        page = self.list_tasks(list_id)
        ids = tuple(sorted(self._record_id(record, TASK_LIST) for record in page.records))
        fingerprint = _impact_fingerprint(LIST_DELETE, list_id, ids)
        return ImpactReport(
            operation_id=LIST_DELETE,
            target_id=list_id,
            child_count=len(ids),
            child_ids=ids,
            fingerprint=fingerprint,
        )

    def delete_list(
        self,
        list_id: str,
        *,
        space_id: str,
        authorization: ImpactAuthorization | None = None,
    ) -> ProjectsObject:
        return self._delete_parent(
            LIST_DELETE,
            target_id=list_id,
            report=self.impact_report(list_id),
            context={"list_id": list_id, "space_id": space_id},
            authorization=authorization,
        )

    def impact_report_space(self, space_id: str) -> ImpactReport:
        page = self.list_lists(space_id)
        ids = tuple(sorted(self._record_id(record, LIST_LIST) for record in page.records))
        fingerprint = _impact_fingerprint(SPACE_DELETE, space_id, ids)
        return ImpactReport(
            operation_id=SPACE_DELETE,
            target_id=space_id,
            child_count=len(ids),
            child_ids=ids,
            fingerprint=fingerprint,
        )

    def delete_space(
        self,
        space_id: str,
        *,
        authorization: ImpactAuthorization | None = None,
    ) -> ProjectsObject:
        return self._delete_parent(
            SPACE_DELETE,
            target_id=space_id,
            report=self.impact_report_space(space_id),
            context={"space_id": space_id},
            authorization=authorization,
        )

    def _delete_parent(
        self,
        operation_id: str,
        *,
        target_id: str,
        report: ImpactReport,
        context: Mapping[str, str],
        authorization: ImpactAuthorization | None,
    ) -> ProjectsObject:
        row = self._catalog.row(operation_id)
        needs = row.approval_required or report.child_count > 0
        if needs and (
            authorization is None
            or authorization.report_fingerprint != report.fingerprint
        ):
            raise ContractViolation(
                "projects_impact_authorization_required",
                detail={
                    "operation_id": operation_id,
                    "target_id": target_id,
                    "child_count": report.child_count,
                    "report_fingerprint": report.fingerprint,
                },
            )
        approval = (
            ApprovalRef(ref=authorization.reference)
            if authorization is not None
            else None
        )
        result, payload = self._call(operation_id, context=context, approval=approval)
        self._require_ok(result)
        return ProjectsObject(
            kind="deleted",
            id=target_id,
            data=dict(payload or {}),
            result=result,
            verified=True,
            verification="adapter_readback",
        )

    # -- pagination -------------------------------------------------------

    def paginate(
        self,
        operation_id: str,
        *,
        context: Mapping[str, str],
        limit: int | None = None,
        max_pages: int = 100,
    ) -> Page:
        row = self._catalog.row(operation_id)
        spec = row.pagination
        if spec is None:
            raise ContractViolation(
                "projects_pagination_unresolved", operation_id=operation_id
            )
        if not isinstance(max_pages, int) or max_pages < 1:
            raise ContractViolation("projects_pagination_pages_invalid")
        size = int(limit or spec.limit)
        if size < 1:
            raise ContractViolation("projects_pagination_limit_invalid")

        records: list[Mapping[str, Any]] = []
        seen: set[str] = set()
        tokens: list[str] = []
        pages = 0
        token: str | None = None
        skip = 0
        total_seen: int | None = None

        while pages < max_pages:
            extra: dict[str, Any] = {spec.limit_param: size}
            if spec.style is PaginationStyle.skip_limit:
                extra[spec.skip_param] = skip
            elif token is not None:
                extra[str(spec.token_param)] = token

            result, payload = self._call(operation_id, context=context, query_extra=extra)
            self._require_ok(result)
            items = _extract(payload, row.collection_field or "")
            if not isinstance(items, list):
                raise ContractViolation(
                    "projects_collection_unresolved",
                    detail={"operation_id": operation_id},
                )
            pages += 1
            for item in items:
                if not isinstance(item, Mapping):
                    raise ContractViolation(
                        "projects_collection_item_invalid",
                        detail={"operation_id": operation_id},
                    )
                record_id = self._record_id(item, operation_id)
                if record_id in seen:
                    raise ContractViolation(
                        "projects_pagination_duplicate",
                        detail={"operation_id": operation_id, "id": record_id},
                    )
                seen.add(record_id)
                records.append(item)

            if spec.style is PaginationStyle.skip_limit:
                skip += size
                total = _extract(payload, spec.total_field) if spec.total_field else None
                if isinstance(total, int):
                    total_seen = total
                if len(items) < size:
                    break
                if isinstance(total, int) and len(records) >= total:
                    break
            else:
                next_token = (
                    _extract(payload, spec.token_field) if spec.token_field else None
                )
                if next_token in (None, "") and spec.token_from_item:
                    if items and isinstance(items[-1], Mapping):
                        next_token = _extract(items[-1], spec.token_from_item)
                if isinstance(next_token, int):
                    next_token = str(next_token)
                if not isinstance(next_token, str) or not next_token:
                    break
                if token is not None and next_token == token:
                    raise ContractViolation(
                        "projects_pagination_token_repeated",
                        detail={"operation_id": operation_id, "token": next_token},
                    )
                token = next_token
                tokens.append(next_token)
            if not items:
                break

        if pages >= max_pages:
            raise ContractViolation(
                "projects_pagination_page_limit",
                detail={"operation_id": operation_id, "max_pages": max_pages},
            )
        if spec.total_field and total_seen is not None and len(records) < total_seen:
            # The endpoint reported more records than it served: never report a
            # short page set as complete.
            raise ContractViolation(
                "projects_pagination_incomplete",
                detail={
                    "operation_id": operation_id,
                    "total": total_seen,
                    "received": len(records),
                },
            )
        return Page(
            operation_id=operation_id,
            records=tuple(records),
            pages=pages,
            tokens=tuple(tokens),
        )

    # -- internals --------------------------------------------------------

    def _call(
        self,
        operation_id: str,
        *,
        context: Mapping[str, str],
        concepts: Mapping[str, Any] | None = None,
        query_extra: Mapping[str, Any] | None = None,
        approval: ApprovalRef | None = None,
    ) -> tuple[OperationResult, Any]:
        row = self._catalog.row(operation_id)
        path_params = _parse_sources(row.path_sources, context, operation_id)
        query: dict[str, Any] = dict(query_extra or {})
        for param, key in row.query_sources:
            value = context.get(key)
            if value is None:
                raise ContractViolation(
                    "projects_query_source_missing",
                    operation_id=operation_id,
                    detail={"source": key},
                )
            query[param] = value
        body = self._body(row, concepts or {})
        if row.location_binding is LocationBinding.token_derived:
            _forbid_location_id(path_params, query, body, operation_id)

        spec: ReadbackSpec | None = None
        idempotency_key: str | None = None
        if row.write:
            # A create's read-back expectation may name a request concept (the
            # space name, for example) that is not a path/query source.
            sources = dict(context)
            for concept, value in (concepts or {}).items():
                if value is not None:
                    sources.setdefault(concept, value)
            spec = self._readback_spec(row, sources)
            idempotency_key = IdempotencyKey.issue(operation_id).value

        index = len(self._recorder.events)
        result = self._adapter.call(
            operation_id=operation_id,
            tenant=self._tenant,
            path_params=path_params,
            query=query or None,
            body=body or None,
            idempotency_key=idempotency_key,
            approval=approval,
            readback=spec,
        )
        parsed = (
            self._recorder.events[index].parsed
            if index < len(self._recorder.events)
            else None
        )
        return result, parsed

    def _body(self, row: ProjectsOperation, concepts: Mapping[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {}
        for concept, value in concepts.items():
            if value is None:
                continue
            wire = row.body_fields.get(concept)
            if not wire:
                raise ContractViolation(
                    "projects_body_field_unresolved",
                    operation_id=row.operation_id,
                    detail={"concept": concept},
                )
            body[wire] = value
        lowered = {str(key).lower() for key in body}
        if "statusgroup" in lowered:
            raise ContractViolation(
                "projects_status_group_forbidden", operation_id=row.operation_id
            )
        return body

    def _readback_spec(
        self, row: ProjectsOperation, context: Mapping[str, str]
    ) -> ReadbackSpec:
        assert row.readback_operation is not None  # enforced by the catalog
        target_params = _parse_sources(
            row.readback_path_sources, context, row.operation_id
        )
        query: dict[str, Any] = {}
        for param, key in row.readback_query_sources:
            value = context.get(key)
            if value is None:
                raise ContractViolation(
                    "projects_readback_source_missing",
                    operation_id=row.operation_id,
                    detail={"source": key},
                )
            query[param] = value
        expect: dict[str, Any] = {}
        for field_name, key in row.readback_expect.items():
            value = context.get(key)
            if value is None:
                raise ContractViolation(
                    "projects_readback_source_missing",
                    operation_id=row.operation_id,
                    detail={"field": field_name, "source": key},
                )
            expect[field_name] = value
        return ReadbackSpec(
            operation_id=row.readback_operation,
            target_params=target_params,
            query=query or None,
            expect=expect,
            description=f"readback for {row.operation_id}",
        )

    def _verify_created(
        self, operation_id: str, created_id: str, *, context: Mapping[str, str]
    ) -> None:
        row = self._catalog.row(operation_id)
        if not row.verify_operation:
            raise ContractViolation(
                "projects_verification_unresolved", operation_id=operation_id
            )
        verify_row = self._catalog.row(row.verify_operation)
        params: dict[str, str] = {}
        for param, key in row.verify_path_sources:
            if key == "id":
                params[param] = created_id
            else:
                value = context.get(key)
                if value is None:
                    raise ContractViolation(
                        "projects_verification_source_missing",
                        operation_id=operation_id,
                        detail={"source": key},
                    )
                params[param] = value
        index = len(self._recorder.events)
        result = self._adapter.call(
            operation_id=row.verify_operation,
            tenant=self._tenant,
            path_params=params,
        )
        if result.status is not Status.ok:
            raise ContractViolation(
                "projects_verification_failed",
                operation_id=operation_id,
                detail={"status": result.status.value, "read": row.verify_operation},
            )
        parsed = (
            self._recorder.events[index].parsed
            if index < len(self._recorder.events)
            else None
        )
        found = _extract(parsed, verify_row.id_field)
        if str(found) != str(created_id):
            raise ContractViolation(
                "projects_verification_mismatch",
                operation_id=operation_id,
                detail={"expected": created_id, "observed": found},
            )

    def _read_object(
        self, operation_id: str, kind: str, context: Mapping[str, str]
    ) -> ProjectsObject:
        result, payload = self._call(operation_id, context=context)
        self._require_ok(result)
        row = self._catalog.row(operation_id)
        record_id = _extract(payload, row.id_field)
        if record_id is None:
            raise ContractViolation("projects_object_id_missing", operation_id=operation_id)
        return ProjectsObject(
            kind=kind,
            id=str(record_id),
            data=dict(payload or {}),
            result=result,
            verified=True,
            verification="read",
        )

    def _home_list(self, task: ProjectsObject) -> str:
        row = self._catalog.row(TASK_GET)
        field_name = row.fields.get("home_list")
        if not field_name:
            raise ContractViolation(
                "projects_home_list_unresolved", detail={"operation_id": TASK_GET}
            )
        value = _extract(task.data, field_name)
        if value in (None, ""):
            raise ContractViolation("projects_home_list_missing", detail={"task_id": task.id})
        return str(value)

    def _created_id(self, payload: Any, operation_id: str) -> str:
        row = self._catalog.row(operation_id)
        value = _extract(payload, row.id_field)
        if value in (None, ""):
            raise ContractViolation("projects_create_id_missing", operation_id=operation_id)
        return str(value)

    def _optional_id(self, payload: Any, operation_id: str) -> str:
        row = self._catalog.row(operation_id)
        value = _extract(payload, row.id_field)
        return "" if value is None else str(value)

    def _record_id(self, record: Mapping[str, Any], operation_id: str) -> str:
        row = self._catalog.row(operation_id)
        value = _extract(record, row.id_field)
        if value in (None, ""):
            raise ContractViolation("projects_record_id_missing", operation_id=operation_id)
        return str(value)

    def _require_ok(self, result: OperationResult) -> None:
        if result.status is Status.ok:
            return
        raise ContractViolation(
            "projects_call_not_ok",
            operation_id=result.operation_id,
            detail={
                "status": result.status.value,
                "rule": (result.error or {}).get("rule"),
                "http_status": result.http_status,
            },
        )

    def _today(self) -> date:
        now = self._clock()
        if isinstance(now, datetime):
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            return now.date()
        return now


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _parse_sources(
    sources: Sequence[tuple[str, str]],
    context: Mapping[str, str],
    operation_id: str,
) -> dict[str, str]:
    params: dict[str, str] = {}
    for param, key in sources:
        value = context.get(key)
        if value is None:
            raise ContractViolation(
                "projects_path_source_missing",
                operation_id=operation_id,
                detail={"source": key},
            )
        params[param] = str(value)
    return params


def _forbid_location_id(
    path: Mapping[str, Any],
    query: Mapping[str, Any],
    body: Mapping[str, Any],
    operation_id: str,
) -> None:
    for label, mapping in (("path", path), ("query", query), ("body", body)):
        for key in mapping:
            if str(key).lower() == "locationid":
                raise ContractViolation(
                    "projects_location_id_not_allowed",
                    operation_id=operation_id,
                    detail={"where": label},
                )


def _extract(payload: Any, path: str | None) -> Any:
    if not path:
        return None
    value = payload
    for part in str(path).split("."):
        if isinstance(value, Mapping):
            if part not in value:
                return None
            value = value[part]
        else:
            return None
    return value


def _impact_fingerprint(operation_id: str, target_id: str, ids: Sequence[str]) -> str:
    payload = {
        "operation_id": operation_id,
        "target_id": target_id,
        "child_ids": list(ids),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# interface + synthetic fixtures (WF32-CP01 for WF33)
# ---------------------------------------------------------------------------


def projects_interface() -> dict[str, Any]:
    """Typed mapping/CRUD/readback interface for WF33 (frozen by checkpoint)."""

    return {
        "interface_version": 1,
        "module_version": PROJECTS_MODULE_VERSION,
        "module": "cli_anything.gohighlevel.public.projects",
        "credential_binding": {
            "location_binding": [item.value for item in LocationBinding],
            "rule": (
                "credential location equals call tenant before transport; "
                "token-derived bindings never send locationId"
            ),
        },
        "availability": {
            "dimensions": list(DIMENSIONS),
            "states": [item.value for item in AvailabilityState],
            "rule": "ui_labs and api_beta are separate facts; neither infers the other",
        },
        "pagination_styles": [item.value for item in PaginationStyle],
        "operations": ProjectsCatalog.fixture().as_interface(),
        "result": {
            "object": ["kind", "id", "data", "result", "verified", "verification"],
            "page": ["operation_id", "records", "pages", "tokens"],
        },
        "errors": [
            "projects_catalog_incomplete",
            "projects_fixture_catalog_refused",
            "projects_tenant_not_bound",
            "projects_location_id_not_allowed",
            "projects_feature_unavailable",
            "projects_default_list_ambiguous",
            "projects_due_date_required",
            "projects_due_date_invalid",
            "projects_due_date_timezone_required",
            "projects_due_date_in_past",
            "projects_status_not_in_list",
            "projects_status_group_forbidden",
            "projects_multiple_assignees",
            "projects_home_list_changed",
            "projects_rrule_forbidden",
            "projects_member_still_present",
            "projects_impact_authorization_required",
            "projects_pagination_duplicate",
            "projects_pagination_token_repeated",
            "projects_verification_failed",
            "projects_verification_mismatch",
        ],
        "discovery_document": {
            "evidence": "discovery",
            "operations": {
                "<operation_id>": {
                    "method": "REQUIRED",
                    "path_template": "REQUIRED",
                    "version": "REQUIRED",
                    "write": False,
                    "approval_required": False,
                    "location_binding": "token_derived",
                    "path_sources": [["param", "context_key"]],
                    "query_sources": [["param", "context_key"]],
                    "body_fields": {"concept": "wire_name"},
                    "pagination": {"style": "cursor|search_after|skip_limit"},
                    "collection_field": "dotted.field",
                    "readback_operation": "operation_id",
                    "verify_operation": "operation_id",
                }
            },
        },
    }


def synthetic_fixtures() -> dict[str, Any]:
    """Beta/permission/date fixtures published with WF32-CP01."""

    return {
        "fixture_version": 1,
        "evidence": EVIDENCE_FIXTURE,
        "availability": {
            "ui_labs": {
                "state": "available",
                "source": "labs_setting_capture",
                "reference": "fixture:projects-ui-labs",
                "checked_at": "2026-11-08T00:00:00+00:00",
            },
            "api_beta": {
                "state": "unknown",
                "source": "api_probe_not_run",
                "reference": "fixture:projects-api-beta",
                "checked_at": "2026-11-08T00:00:00+00:00",
            },
            "rule": "UI available never implies API beta",
        },
        "due_dates": {
            "approved_date": "2026-12-01",
            "approved_offset": "2026-12-01T17:30:00-05:00",
            "naive_datetime_refused": "2026-12-01T17:30:00",
            "past_refused": "2023-01-01",
        },
        "permissions": {
            "private_space_members": [
                {"id": "member_synthetic_1", "role": "owner"},
                {"id": "member_synthetic_2", "role": "member"},
            ],
            "rule": "removal only through the documented removal operation",
        },
        "catalog": ProjectsCatalog.fixture().as_interface(),
    }


__all__ = [
    "AvailabilityEvidence",
    "AvailabilityState",
    "ImpactAuthorization",
    "ImpactReport",
    "LocationBinding",
    "Page",
    "PaginationSpec",
    "PaginationStyle",
    "ProjectsAvailability",
    "ProjectsCatalog",
    "ProjectsObject",
    "ProjectsOperation",
    "ProjectsService",
    "classify_denial",
    "normalize_due_date",
    "projects_interface",
    "single_assignee",
    "synthetic_fixtures",
]


# ---------------------------------------------------------------------------
# fixture catalog (synthetic wire names; refused unless allow_fixture=True)
# ---------------------------------------------------------------------------


def _fixture_operations() -> tuple[ProjectsOperation, ...]:
    def op(
        operation_id: str,
        method: str,
        path: str,
        *,
        version: str = "fixture-v1",
        **kwargs: Any,
    ) -> ProjectsOperation:
        return ProjectsOperation(
            operation_id=operation_id,
            method=method,
            path_template=path,
            version=version,
            evidence=EVIDENCE_FIXTURE,
            **kwargs,
        )

    return (
        op(
            SPACE_CREATE,
            "POST",
            "/projects/_fixture/spaces",
            write=True,
            body_fields={
                "name": "name",
                "description": "description",
                "private": "isPrivate",
                "folder": "folderId",
            },
            readback_operation=SPACE_LIST,
            readback_expect={"name": "name"},
            verify_operation=SPACE_GET,
            verify_path_sources=(("spaceId", "id"),),
        ),
        op(
            SPACE_LIST,
            "GET",
            "/projects/_fixture/spaces",
            pagination=PaginationSpec(
                style=PaginationStyle.skip_limit,
                limit=2,
                skip_param="skip",
                limit_param="limit",
                total_field="total",
            ),
            collection_field="spaces",
        ),
        op(
            SPACE_GET,
            "GET",
            "/projects/_fixture/spaces/{spaceId}",
            path_sources=(("spaceId", "space_id"),),
        ),
        op(
            SPACE_DELETE,
            "DELETE",
            "/projects/_fixture/spaces/{spaceId}",
            write=True,
            approval_required=True,
            path_sources=(("spaceId", "space_id"),),
            readback_operation=SPACE_LIST,
            readback_expect={"spaceId": "space_id"},
        ),
        op(
            FOLDER_CREATE,
            "POST",
            "/projects/_fixture/spaces/{spaceId}/folders",
            write=True,
            path_sources=(("spaceId", "space_id"),),
            body_fields={"name": "name"},
            readback_operation=LIST_LIST,
            readback_path_sources=(("spaceId", "space_id"),),
            readback_expect={"spaceId": "space_id"},
        ),
        op(
            LIST_CREATE,
            "POST",
            "/projects/_fixture/spaces/{spaceId}/lists",
            write=True,
            path_sources=(("spaceId", "space_id"),),
            body_fields={"name": "name", "folder": "folderId"},
            readback_operation=LIST_LIST,
            readback_path_sources=(("spaceId", "space_id"),),
            readback_expect={"spaceId": "space_id"},
            verify_operation=LIST_GET,
            verify_path_sources=(("listId", "id"),),
        ),
        op(
            LIST_LIST,
            "GET",
            "/projects/_fixture/spaces/{spaceId}/lists",
            path_sources=(("spaceId", "space_id"),),
            pagination=PaginationSpec(
                style=PaginationStyle.cursor,
                limit=2,
                token_param="cursor",
                token_field="meta.nextCursor",
            ),
            collection_field="lists",
            default_field="isDefault",
            default_value="true",
        ),
        op(
            LIST_GET,
            "GET",
            "/projects/_fixture/lists/{listId}",
            path_sources=(("listId", "list_id"),),
            fields={"home_list": "spaceId"},
        ),
        op(
            LIST_STATUSES,
            "GET",
            "/projects/_fixture/lists/{listId}/statuses",
            path_sources=(("listId", "list_id"),),
            pagination=PaginationSpec(
                style=PaginationStyle.skip_limit,
                limit=2,
                total_field="total",
            ),
            collection_field="statuses",
            fields={"id": "id", "name": "name"},
        ),
        op(
            LIST_DELETE,
            "DELETE",
            "/projects/_fixture/lists/{listId}",
            write=True,
            approval_required=True,
            path_sources=(("listId", "list_id"),),
            readback_operation=LIST_LIST,
            readback_path_sources=(("spaceId", "space_id"),),
            readback_expect={"spaceId": "space_id"},
        ),
        op(
            TASK_CREATE,
            "POST",
            "/projects/_fixture/lists/{listId}/tasks",
            write=True,
            path_sources=(("listId", "list_id"),),
            body_fields={
                "title": "title",
                "dueDate": "dueDate",
                "status": "status",
                "assignee": "assigneeId",
                "parentTaskId": "parentTaskId",
                "description": "description",
            },
            readback_operation=TASK_LIST,
            readback_path_sources=(("listId", "list_id"),),
            readback_expect={"listId": "list_id"},
            verify_operation=TASK_GET,
            verify_path_sources=(("taskId", "id"),),
        ),
        op(
            TASK_GET,
            "GET",
            "/projects/_fixture/tasks/{taskId}",
            path_sources=(("taskId", "task_id"),),
            fields={"id": "id", "home_list": "listId"},
        ),
        op(
            TASK_LIST,
            "GET",
            "/projects/_fixture/lists/{listId}/tasks",
            path_sources=(("listId", "list_id"),),
            pagination=PaginationSpec(
                style=PaginationStyle.cursor,
                limit=2,
                token_param="cursor",
                token_field="meta.nextCursor",
            ),
            collection_field="tasks",
            fields={"id": "id", "home_list": "listId"},
        ),
        op(
            TASK_UPDATE,
            "PUT",
            "/projects/_fixture/tasks/{taskId}",
            write=True,
            path_sources=(("taskId", "task_id"),),
            body_fields={"title": "title", "dueDate": "dueDate", "status": "status"},
            readback_operation=TASK_GET,
            readback_path_sources=(("taskId", "task_id"),),
            readback_expect={"id": "task_id"},
        ),
        op(
            TASK_ADD_TO_LIST,
            "POST",
            "/projects/_fixture/tasks/{taskId}/lists",
            write=True,
            path_sources=(("taskId", "task_id"),),
            body_fields={"list": "listId"},
            readback_operation=TASK_GET,
            readback_path_sources=(("taskId", "task_id"),),
            readback_expect={"id": "task_id"},
            fields={"home_list": "listId"},
        ),
        op(
            COMMENT_CREATE,
            "POST",
            "/projects/_fixture/tasks/{taskId}/comments",
            write=True,
            path_sources=(("taskId", "task_id"),),
            body_fields={"comment": "body"},
            readback_operation=COMMENT_LIST,
            readback_path_sources=(("taskId", "task_id"),),
            readback_expect={"taskId": "task_id"},
        ),
        op(
            COMMENT_LIST,
            "GET",
            "/projects/_fixture/tasks/{taskId}/comments",
            path_sources=(("taskId", "task_id"),),
            pagination=PaginationSpec(
                style=PaginationStyle.skip_limit, limit=2, total_field="total"
            ),
            collection_field="comments",
        ),
        op(
            RECURRENCE_SET,
            "PUT",
            "/projects/_fixture/tasks/{taskId}/recurrence",
            write=True,
            path_sources=(("taskId", "task_id"),),
            body_fields={"recurrence": "recurrence"},
            readback_operation=TASK_GET,
            readback_path_sources=(("taskId", "task_id"),),
            readback_expect={"id": "task_id"},
        ),
        op(
            MEMBER_LIST,
            "GET",
            "/projects/_fixture/spaces/{spaceId}/members",
            path_sources=(("spaceId", "space_id"),),
            pagination=PaginationSpec(
                style=PaginationStyle.search_after,
                limit=2,
                token_param="searchAfter",
                token_from_item="searchAfter",
            ),
            collection_field="members",
            fields={"id": "id", "name": "name"},
        ),
        op(
            MEMBER_UPDATE,
            "PUT",
            "/projects/_fixture/spaces/{spaceId}/members",
            write=True,
            path_sources=(("spaceId", "space_id"),),
            body_fields={"members": "memberIds"},
            readback_operation=MEMBER_LIST,
            readback_path_sources=(("spaceId", "space_id"),),
            readback_expect={"spaceId": "space_id"},
        ),
        op(
            MEMBER_REMOVE,
            "DELETE",
            "/projects/_fixture/spaces/{spaceId}/members/{memberId}",
            write=True,
            approval_required=True,
            path_sources=(("spaceId", "space_id"), ("memberId", "member_id")),
            readback_operation=MEMBER_LIST,
            readback_path_sources=(("spaceId", "space_id"),),
            readback_expect={"spaceId": "space_id"},
        ),
    )
