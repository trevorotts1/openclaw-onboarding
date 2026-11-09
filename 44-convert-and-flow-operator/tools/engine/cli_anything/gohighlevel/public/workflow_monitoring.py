"""Workflow log and statistics monitoring (WF25, Document 1 Section 22).

Reads under the documented ``workflows.logs`` permission.  The module owns
exactly four behaviours the contract makes non-negotiable:

* **Bounded windows.**  A query window is validated before any call: ordered,
  not in the future, inside the documented retention and at most the documented
  query width.  A larger eligible period is split into contiguous half-open
  windows so no count is overlapped.
* **Opaque cursors.**  A continuation value returned by the provider is carried
  back unchanged; it is never rebuilt, decoded or re-derived.  The non-date
  filters and the window are identical on every page of one window.
* **Stable-identity deduplication.**  Pages and windows may overlap; a record
  is counted once by its stable documented identity, never by arrival order.
* **Honest metrics.**  Aggregate output is labelled ``event_count``.  A
  same-window event ratio is never called cohort conversion, and a real cohort
  rate is only produced from an explicit enrollment cohort.  Builder rehearsals
  and controlled live executions remain separate evidence states, and an empty
  log result is never execution proof.

Contract constraints are versioned here (``CONTRACT_REVISION``) instead of
being hidden assumptions.  Where the upstream owner has not frozen a value --
the two operation rows, the window query parameter names, the cursor parameter,
and the documented aggregate-group limit -- this module fails loudly with a
named rule and the owning workflow, and never guesses a literal.

Nothing here starts a service: polling is a caller-driven bounded loop
(``MAX_PAGES_PER_SCAN``).  Persistent scheduled monitoring is a separately
installed runtime job; this module can only record its activation, never claim
it.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence

from .errors import ContractViolation
from .result import canonical_json, redact_mapping

__all__ = [
    "AGGREGATE_OPERATION_ID",
    "CONTRACT_REVISION",
    "DEFAULT_CONTRACT",
    "EVIDENCE_STATES",
    "LOG_OPERATION_ID",
    "LOG_RETENTION_DAYS",
    "MAX_PAGES_PER_SCAN",
    "MAX_QUERY_WINDOW_DAYS",
    "REQUIRED_OPERATIONS",
    "STATUS_BUCKETS",
    "AggregateScan",
    "GroupLimit",
    "MetricSummary",
    "MonitoringContract",
    "MonitoringContractBinding",
    "MonitoringScan",
    "Page",
    "QueryWindow",
    "RuntimeStatus",
    "WorkflowMonitoring",
    "classify_status",
    "cohort_completion_rate",
    "format_time",
    "parse_time",
    "read_aggregate",
    "read_page",
    "record_identity",
    "redact_event",
    "same_window_event_ratio",
    "scan",
]

#: Versioned contract constraints (Document 1 Section 22.1).  Revalidate
#: against the provider pages before changing any literal here.
CONTRACT_REVISION = "wf25-monitoring-2026-11-08"
MAX_QUERY_WINDOW_DAYS = 30
LOG_RETENTION_DAYS = 60
MAX_PAGES_PER_SCAN = 20

#: Operation ids WF25 consumes.  The rows are owned by WF00; until WF00 freezes
#: them a default binding refuses with ``monitoring_operation_rows_missing``.
LOG_OPERATION_ID = "workflows.logs"
AGGREGATE_OPERATION_ID = "workflows.logs.aggregate"
REQUIRED_OPERATIONS: tuple[str, ...] = (LOG_OPERATION_ID, AGGREGATE_OPERATION_ID)

#: The six runtime evidence states are independent facts, never one boolean.
EVIDENCE_STATES: tuple[str, ...] = (
    "definition_validated",
    "stored_definition_verified",
    "published_status_verified",
    "builder_rehearsal_verified",
    "controlled_live_execution_verified",
    "ongoing_monitoring_configured",
)

#: Status buckets.  A status outside every documented set lands in
#: ``unclassified``; every non-completed status is never collapsed into error.
STATUS_BUCKETS: Mapping[str, frozenset[str]] = {
    "completed": frozenset({"completed", "complete", "success", "succeeded", "sent", "executed"}),
    "waiting": frozenset(
        {"waiting", "pending", "queued", "scheduled", "in_progress", "in-progress", "processing"}
    ),
    "failed": frozenset({"failed", "failure", "error", "errored", "rejected", "bounced"}),
    "removed": frozenset({"removed", "deleted"}),
}

#: Fields a redacted event may keep.  The value of an id-shaped field other than
#: the log/event identity is replaced with ``<id>``; message bodies, names,
#: email addresses and phone numbers are dropped and only counted.
REDACTED_EVENT_FIELDS: tuple[str, ...] = (
    "logId",
    "eventId",
    "eventType",
    "status",
    "state",
    "stepId",
    "actionType",
    "errorCode",
    "occurredAt",
    "createdAt",
    "updatedAt",
)
_EVENT_IDENTITY_FIELDS = frozenset({"logId", "eventId"})

_RECORD_KEYS: tuple[str, ...] = ("logs", "events", "records", "data")
_CURSOR_CONTAINERS: tuple[str, ...] = ("meta", "pagination", "pageInfo")
_CURSOR_KEYS: tuple[str, ...] = ("nextCursor", "next_cursor", "cursor")
_RESERVED_FILTERS = frozenset({"workflowId", "workflow_id", "cursor", "nextCursor"})

_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _refuse(rule_name: str, **detail: Any) -> None:
    """One refusal shape: a machine rule plus non-secret detail names."""

    raise ContractViolation(rule_name, detail=detail)


# ---------------------------------------------------------------------------
# time and windows
# ---------------------------------------------------------------------------


def parse_time(value: "datetime | str", *, name: str = "time") -> datetime:
    """Parse an RFC3339 timestamp with an explicit offset; return UTC."""

    if isinstance(value, datetime):
        if value.tzinfo is None:
            _refuse("time_not_timezone_aware", field=name)
        return value.astimezone(timezone.utc)
    if not isinstance(value, str) or not _RFC3339.match(value.strip()):
        _refuse("time_format_invalid", field=name, required="RFC3339 with offset")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:  # pragma: no cover - regex already screened the shape
        _refuse("time_format_invalid", field=name, required="RFC3339 with offset")
    return parsed.astimezone(timezone.utc)


def format_time(value: datetime) -> str:
    """RFC3339 UTC literal used on the wire."""

    return parse_time(value, name="value").strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class QueryWindow:
    """One half-open ``[start, end)`` query window."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        start = parse_time(self.start, name="start")
        end = parse_time(self.end, name="end")
        if start >= end:
            _refuse("window_order_invalid")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    @property
    def days(self) -> float:
        return (self.end - self.start).total_seconds() / 86400.0

    def as_query(self, params: Sequence[str]) -> dict[str, str]:
        if len(tuple(params)) != 2:
            _refuse("monitoring_window_params_invalid", params=list(params))
        start_name, end_name = params
        return {str(start_name): format_time(self.start), str(end_name): format_time(self.end)}

    def as_mapping(self) -> dict[str, str]:
        return {"start": format_time(self.start), "end": format_time(self.end)}


@dataclass(frozen=True)
class GroupLimit:
    """The aggregate group bound in force, and whether it is documented."""

    value: int
    verified: bool


@dataclass(frozen=True)
class MonitoringContract:
    """Versioned monitoring constraints; every literal is a contract decision."""

    revision: str = CONTRACT_REVISION
    max_window_days: int = MAX_QUERY_WINDOW_DAYS
    retention_days: int = LOG_RETENTION_DAYS
    aggregate_group_limit: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.revision, str) or not self.revision.strip():
            _refuse("contract_revision_invalid")
        for name in ("max_window_days", "retention_days"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                _refuse("contract_constraint_invalid", field=name)
        if self.aggregate_group_limit is not None:
            value = self.aggregate_group_limit
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                _refuse("contract_constraint_invalid", field="aggregate_group_limit")

    def windows(
        self,
        start: "datetime | str",
        end: "datetime | str",
        *,
        now: "datetime | str | None" = None,
    ) -> tuple[QueryWindow, ...]:
        """Validate one eligible period and split it into contiguous windows."""

        start_at = parse_time(start, name="start")
        end_at = parse_time(end, name="end")
        now_at = parse_time(now if now is not None else datetime.now(timezone.utc), name="now")
        if start_at >= end_at:
            _refuse("window_order_invalid")
        if end_at > now_at:
            _refuse("window_after_now")
        oldest = now_at - timedelta(days=self.retention_days)
        if start_at < oldest:
            _refuse("window_before_retention", retention_days=self.retention_days)

        step = timedelta(days=self.max_window_days)
        windows: list[QueryWindow] = []
        cursor = start_at
        while cursor < end_at:
            following = min(cursor + step, end_at)
            windows.append(QueryWindow(cursor, following))
            cursor = following
        if not windows:
            _refuse("window_plan_empty")
        for earlier, later in zip(windows, windows[1:]):
            if earlier.end != later.start:
                _refuse("window_plan_not_contiguous")
        if windows[0].start != start_at or windows[-1].end != end_at:
            _refuse("window_plan_incomplete")
        return tuple(windows)

    def group_limit(
        self, *, limit: int, declared_limit: int | None = None
    ) -> GroupLimit:
        """Validate an aggregate grouping bound without silently truncating."""

        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            _refuse("aggregate_group_limit_invalid", limit=limit)
        if self.aggregate_group_limit is not None:
            if limit > self.aggregate_group_limit:
                _refuse(
                    "aggregate_group_limit_exceeded",
                    limit=limit,
                    documented=self.aggregate_group_limit,
                )
            return GroupLimit(value=limit, verified=True)
        # The documented provider limit is not frozen yet, so the caller must
        # declare the bound it is enforcing and the result says it is unverified.
        if declared_limit is None:
            _refuse("aggregate_group_limit_unverified", owner="WF00")
        if not isinstance(declared_limit, int) or isinstance(declared_limit, bool) or declared_limit < 1:
            _refuse("aggregate_group_limit_invalid", declared=declared_limit)
        if limit > declared_limit:
            _refuse(
                "aggregate_group_limit_exceeded",
                limit=limit,
                declared=declared_limit,
            )
        return GroupLimit(value=limit, verified=False)


DEFAULT_CONTRACT = MonitoringContract()


# ---------------------------------------------------------------------------
# page reading (shape-tolerant, never a silent empty success)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Page:
    records: tuple[Mapping[str, Any], ...]
    next_cursor: str | None
    cursor_field: str | None = None


def read_page(body: Any) -> Page:
    """Read one log page, forwarding its cursor literally.

    An empty mapping is a legitimate empty page.  A non-empty mapping whose
    record collection and cursor cannot be identified is refused: a shape this
    module does not understand must never be reported as zero events.
    """

    if not isinstance(body, Mapping):
        _refuse("monitoring_page_shape_unknown", reason="not_a_mapping")

    records: tuple[Mapping[str, Any], ...] | None = None
    for key in _RECORD_KEYS:
        value = body.get(key)
        if isinstance(value, list):
            items = tuple(item for item in value if isinstance(item, Mapping))
            if len(items) != len(value):
                _refuse("monitoring_page_record_invalid", collection=str(key))
            records = items
            break

    cursors: dict[str, str] = {}
    for key in _CURSOR_KEYS:
        value = body.get(key)
        if value:
            cursors[key] = value
    for container in _CURSOR_CONTAINERS:
        inner = body.get(container)
        if isinstance(inner, Mapping):
            for key in _CURSOR_KEYS:
                value = inner.get(key)
                if value:
                    cursors[f"{container}.{key}"] = value
    distinct = set(cursors.values())
    if len(distinct) > 1:
        _refuse("cursor_ambiguous", fields=sorted(cursors))
    next_cursor = next(iter(distinct)) if distinct else None
    if next_cursor is not None and not isinstance(next_cursor, str):
        _refuse("cursor_invalid", cursor_type=type(next_cursor).__name__)
    cursor_field = sorted(cursors)[0] if cursors else None

    if records is None:
        if not body:
            return Page((), next_cursor, cursor_field)
        ignorable = set(_CURSOR_KEYS) | set(_CURSOR_CONTAINERS) | {"total", "count"}
        if set(body) <= ignorable:
            return Page((), next_cursor, cursor_field)
        _refuse(
            "monitoring_page_shape_unknown",
            reason="no_record_collection",
            keys=sorted(str(key) for key in body),
        )
    return Page(records, next_cursor, cursor_field)


def record_identity(record: Mapping[str, Any]) -> str:
    """Stable identity for deduplication; derived only when no id exists."""

    for key in ("logId", "eventId", "id"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
    digest = hashlib.sha256(canonical_json(dict(record)).encode("utf-8")).hexdigest()
    return "derived:" + digest


def classify_status(value: Any) -> str:
    """One documented bucket, or ``unclassified``; never a guessed error."""

    if not isinstance(value, str):
        return "unclassified"
    text = value.strip().lower()
    for bucket, documented in STATUS_BUCKETS.items():
        if text in documented:
            return bucket
    return "unclassified"


def redact_event(record: Mapping[str, Any]) -> dict[str, Any]:
    """A redacted event: safe scalar fields, no bodies, no customer PII."""

    kept: dict[str, Any] = {}
    withheld = 0
    for key, value in record.items():
        name = str(key)
        if name not in REDACTED_EVENT_FIELDS:
            withheld += 1
            continue
        if name in _EVENT_IDENTITY_FIELDS or not name.lower().endswith("id"):
            kept[name] = value
        else:
            kept[name] = "<id>"
    return {
        "identity": record_identity(record),
        "fields": kept,
        "withheld_field_count": withheld,
    }


# ---------------------------------------------------------------------------
# scan: pagination, windows, dedupe
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MonitoringScan:
    """The redacted log-scan result.  Counts are event counts, never cohorts."""

    workflow_id: str
    windows: tuple[QueryWindow, ...]
    pages_read: int
    events: tuple[Mapping[str, Any], ...]
    counts: Mapping[str, int]
    duplicates_dropped: int
    filters_fingerprint: str
    receipt_ids: tuple[str, ...]
    contract_revision: str = CONTRACT_REVISION
    metric_kind: Literal["event_count"] = "event_count"

    @property
    def empty(self) -> bool:
        return not self.events

    def summary(self) -> dict[str, Any]:
        return {
            "contract_revision": self.contract_revision,
            "workflow_id": self.workflow_id,
            "metric_kind": self.metric_kind,
            "label": "workflow_log_event_count",
            "cohort_conversion": None,
            "counts": dict(self.counts),
            "windows": [window.as_mapping() for window in self.windows],
            "pages_read": self.pages_read,
            "duplicates_dropped": self.duplicates_dropped,
            "filters_fingerprint": self.filters_fingerprint,
            "receipt_ids": list(self.receipt_ids),
            "empty": self.empty,
            "execution_proof": False,
            "note": (
                "Log-event counts for the requested windows. A same-window ratio "
                "is not cohort conversion; contacts may enter before the window."
            ),
        }


def scan(
    *,
    workflow_id: str,
    windows: Sequence[QueryWindow],
    fetch_page: Callable[[QueryWindow, "str | None", Mapping[str, Any]], Mapping[str, Any]],
    filters: Mapping[str, Any] | None = None,
    max_pages: int = MAX_PAGES_PER_SCAN,
    receipts: "list[str] | None" = None,
    contract_revision: str = CONTRACT_REVISION,
) -> MonitoringScan:
    """Follow every page of every window; deduplicate across boundaries.

    ``fetch_page(window, cursor, filters)`` returns the parsed provider body.
    ``cursor`` is exactly what the provider returned (``None`` on the first
    page); it is never reconstructed.  ``filters`` is passed unchanged to every
    page of every window -- only the window dates differ between windows.
    """

    if not isinstance(workflow_id, str) or not workflow_id.strip():
        _refuse("workflow_id_required")
    windows = tuple(windows)
    if not windows:
        _refuse("window_plan_empty")
    for window in windows:
        if not isinstance(window, QueryWindow):
            _refuse("window_invalid")
    if not callable(fetch_page):
        _refuse("fetch_page_required")
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages < 1:
        _refuse("polling_bound_invalid", max_pages=max_pages)
    if max_pages > MAX_PAGES_PER_SCAN:
        _refuse(
            "polling_bound_exceeded",
            max_pages=max_pages,
            max_allowed=MAX_PAGES_PER_SCAN,
        )

    base_filters = {str(key): value for key, value in dict(filters or {}).items()}
    reserved = sorted(set(base_filters) & _RESERVED_FILTERS)
    if reserved:
        _refuse("scan_filter_reserved", fields=reserved)
    fingerprint = hashlib.sha256(canonical_json(base_filters).encode("utf-8")).hexdigest()

    receipt_log = receipts if receipts is not None else []
    seen: set[str] = set()
    events: list[Mapping[str, Any]] = []
    counts: dict[str, int] = {bucket: 0 for bucket in STATUS_BUCKETS}
    counts["unclassified"] = 0
    duplicates = 0
    pages_read = 0
    previous_end: datetime | None = None

    for window in windows:
        if previous_end is not None and window.start != previous_end:
            _refuse("window_plan_not_contiguous")
        previous_end = window.end
        cursor: str | None = None
        while True:
            pages_read += 1
            if pages_read > max_pages:
                _refuse("polling_bound_exceeded", pages=pages_read, max_pages=max_pages)
            body = fetch_page(window, cursor, dict(base_filters))
            page = read_page(body)
            for record in page.records:
                identity = record_identity(record)
                if identity in seen:
                    duplicates += 1
                    continue
                seen.add(identity)
                counts[classify_status(record.get("status"))] += 1
                events.append(redact_event(record))
            if page.next_cursor is None:
                break
            if page.next_cursor == cursor:
                _refuse("cursor_not_advancing", cursor_field=page.cursor_field)
            cursor = page.next_cursor

    counts["total_events"] = len(events)
    return MonitoringScan(
        workflow_id=workflow_id.strip(),
        windows=windows,
        pages_read=pages_read,
        events=tuple(events),
        counts=counts,
        duplicates_dropped=duplicates,
        filters_fingerprint=fingerprint,
        receipt_ids=tuple(receipt_log),
        contract_revision=contract_revision,
    )


# ---------------------------------------------------------------------------
# aggregates and honest metrics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricSummary:
    """Aggregate output for one window.  Event counts, clearly labelled."""

    groups: tuple[Mapping[str, Any], ...]
    total_events: int
    group_limit: int
    group_limit_verified: bool
    contract_revision: str = CONTRACT_REVISION
    metric_kind: Literal["event_count"] = "event_count"

    def summary(self) -> dict[str, Any]:
        return {
            "contract_revision": self.contract_revision,
            "metric_kind": self.metric_kind,
            "label": "workflow_log_event_count",
            "definition": "number of log events in the window, grouped as requested",
            "groups": [dict(group) for group in self.groups],
            "total_events": self.total_events,
            "group_limit": self.group_limit,
            "group_limit_verified": self.group_limit_verified,
            "cohort_conversion": None,
            "is_cohort_conversion": False,
            "note": "Event counts are not cohort conversion.",
        }


@dataclass(frozen=True)
class AggregateScan:
    workflow_id: str
    group_by: tuple[str, ...]
    windows: tuple[QueryWindow, ...]
    metrics: tuple[MetricSummary, ...]
    receipt_ids: tuple[str, ...]
    contract_revision: str = CONTRACT_REVISION

    def summary(self) -> dict[str, Any]:
        first = self.metrics[0] if self.metrics else None
        return {
            "contract_revision": self.contract_revision,
            "workflow_id": self.workflow_id,
            "group_by": list(self.group_by),
            "metric_kind": "event_count",
            "label": "workflow_log_event_count",
            "per_window": [
                {"window": window.as_mapping(), "metrics": metric.summary()}
                for window, metric in zip(self.windows, self.metrics)
            ],
            "total_events": sum(metric.total_events for metric in self.metrics),
            "group_limit": None if first is None else first.group_limit,
            "group_limit_verified": None if first is None else first.group_limit_verified,
            "cohort_conversion": None,
            "is_cohort_conversion": False,
            "receipt_ids": list(self.receipt_ids),
            "note": (
                "Per-window event counts over non-overlapping windows. Never "
                "labelled as cohort conversion."
            ),
        }


def read_aggregate(body: Any, *, group_limit: GroupLimit) -> MetricSummary:
    """Read one aggregate page without guessing counts or truncating groups."""

    if not isinstance(body, Mapping):
        _refuse("aggregate_shape_unknown", reason="not_a_mapping")
    groups_body: Any = None
    for key in ("groups", "buckets", "data"):
        value = body.get(key)
        if isinstance(value, list):
            groups_body = value
            break
    if groups_body is None:
        if not body:
            groups_body = []
        else:
            _refuse(
                "aggregate_shape_unknown",
                reason="no_group_collection",
                keys=sorted(str(key) for key in body),
            )
    if not isinstance(groups_body, list):
        _refuse("aggregate_shape_unknown", reason="group_collection_not_a_list")
    if len(groups_body) > group_limit.value:
        _refuse(
            "aggregate_groups_exceed_limit",
            groups=len(groups_body),
            limit=group_limit.value,
        )
    for marker in ("truncated", "hasMore", "has_more"):
        if body.get(marker) is True:
            _refuse("aggregate_result_truncated", marker=marker)

    total = 0
    groups: list[Mapping[str, Any]] = []
    for item in groups_body:
        if not isinstance(item, Mapping):
            _refuse("aggregate_group_invalid")
        count = item.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            _refuse("aggregate_count_missing", reason="count must be a non-negative integer")
        total += count
        groups.append(redact_mapping(dict(item), redaction="ids-only"))
    return MetricSummary(
        groups=tuple(groups),
        total_events=total,
        group_limit=group_limit.value,
        group_limit_verified=group_limit.verified,
    )


def same_window_event_ratio(
    *, numerator_events: int, denominator_events: int
) -> dict[str, Any]:
    """A same-window event ratio, explicitly NOT cohort conversion."""

    for name, value in (
        ("numerator_events", numerator_events),
        ("denominator_events", denominator_events),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            _refuse("ratio_value_invalid", field=name)
    if denominator_events == 0:
        _refuse("ratio_denominator_zero")
    return {
        "ratio_kind": "same_window_event_ratio",
        "numerator": numerator_events,
        "denominator": denominator_events,
        "value": numerator_events / denominator_events,
        "is_cohort_conversion": False,
        "warning": (
            "Contacts may enter before the window and finish inside it, so a "
            "ratio above 1.0 is not automatically a platform defect. This is "
            "not cohort conversion."
        ),
    }


def cohort_completion_rate(
    *, cohort_contact_ids: Iterable[str], completed_contact_ids: Iterable[str]
) -> dict[str, Any]:
    """A real cohort rate; requires the explicit pre-window enrollment cohort."""

    cohort = {str(item) for item in cohort_contact_ids if str(item).strip()}
    completed = {str(item) for item in completed_contact_ids if str(item).strip()}
    if not cohort:
        _refuse("cohort_conversion_unavailable", reason="explicit_enrollment_cohort_required")
    inside = len(cohort & completed)
    return {
        "ratio_kind": "cohort_conversion",
        "cohort_size": len(cohort),
        "completed_in_cohort": inside,
        "value": inside / len(cohort),
        "is_cohort_conversion": True,
        "methodology": (
            "Contacts counted only when enrolled before the window opened; the "
            "enrollment cohort is an explicit input, never derived from a "
            "same-window aggregate."
        ),
    }


# ---------------------------------------------------------------------------
# runtime evidence states
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuntimeStatus:
    """Six independent evidence states; no state implies another."""

    definition_validated: bool = False
    stored_definition_verified: bool = False
    published_status_verified: bool = False
    builder_rehearsal_verified: bool = False
    controlled_live_execution_verified: bool = False
    ongoing_monitoring_configured: bool = False
    notes: tuple[str, ...] = ()

    def validate(
        self,
        *,
        scan: MonitoringScan | None = None,
        live_reference: Mapping[str, Any] | None = None,
        rehearsal_reference: Mapping[str, Any] | None = None,
        monitoring_job_id: str | None = None,
    ) -> None:
        if self.builder_rehearsal_verified:
            if not _has_values(rehearsal_reference):
                _refuse("rehearsal_reference_missing")
        if self.controlled_live_execution_verified:
            if not _has_values(live_reference):
                _refuse("live_execution_reference_missing")
            if scan is not None and scan.empty:
                _refuse("empty_logs_not_execution_proof")
        if self.ongoing_monitoring_configured:
            if not str(monitoring_job_id or "").strip():
                _refuse("monitoring_service_not_configured")

    def as_evidence(self) -> dict[str, Any]:
        return {
            "states": {name: bool(getattr(self, name)) for name in EVIDENCE_STATES},
            "counts_as_production": self.controlled_live_execution_verified,
            "builder_rehearsal_is_production": False,
            "notes": list(self.notes),
        }


def _has_values(reference: Mapping[str, Any] | None) -> bool:
    if not isinstance(reference, Mapping):
        return False
    return any(str(value).strip() for value in reference.values() if value is not None)


# ---------------------------------------------------------------------------
# adapter binding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MonitoringContractBinding:
    """How the two log operations are addressed.

    ``window_params`` and ``cursor_param`` are documented wire names frozen by
    WF00's operation row; when they are not frozen yet, use refuses loudly.
    """

    logs_operation_id: str = LOG_OPERATION_ID
    aggregate_operation_id: str = AGGREGATE_OPERATION_ID
    workflow_param: str = "workflowId"
    window_params: tuple[str, str] | None = None
    cursor_param: str | None = None

    @classmethod
    def from_operations(cls, operations: Mapping[str, Any] | None = None) -> "MonitoringContractBinding":
        if operations is None:
            from .operations import OPERATIONS

            operations = OPERATIONS
        missing = [operation for operation in REQUIRED_OPERATIONS if operation not in operations]
        if missing:
            _refuse(
                "monitoring_operation_rows_missing",
                missing=",".join(missing),
                owner="WF00",
            )
        return cls()

    def require_window_params(self) -> tuple[str, str]:
        if self.window_params is None:
            _refuse("monitoring_window_params_unverified", owner="WF00")
        if len(tuple(self.window_params)) != 2:
            _refuse("monitoring_window_params_invalid", params=list(self.window_params))
        return (str(self.window_params[0]), str(self.window_params[1]))


class _RecordingTransport:
    """Records the last real transport response so a read body stays in memory.

    The public adapter returns a receipt envelope, not a body.  WF01/WF02 have
    not published a body-access interface, so this wrapper reads the body from
    the same transport seam the adapter already uses.  The body is parsed
    immediately and never stored in evidence or a receipt.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.last: Any = None

    def request(self, **kwargs: Any) -> Any:
        response = self._inner.request(**kwargs)
        self.last = response
        return response


def _bind_recorder(public: Any) -> _RecordingTransport:
    transport = getattr(public, "_transport", None)
    if isinstance(transport, _RecordingTransport):
        return transport
    if transport is None or not callable(getattr(transport, "request", None)):
        _refuse("monitoring_transport_unavailable")
    recorder = _RecordingTransport(transport)
    try:
        public._transport = recorder
    except AttributeError:  # pragma: no cover - defensive
        _refuse("monitoring_transport_unbindable")
    return recorder


class WorkflowMonitoring:
    """Read-only monitoring over the frozen public adapter.

    Construction never sends a request.  Every call goes through
    ``PublicGhlAdapter.call`` so tenant binding, auth class, capability gate and
    receipts are the frozen ones.  A non-``ok`` envelope is refused as
    ``monitoring_call_not_ok`` — a denied or failed call never looks like an
    empty log page.
    """

    def __init__(
        self,
        *,
        public: Any,
        tenant: Any,
        binding: MonitoringContractBinding | None = None,
        operations: Mapping[str, Any] | None = None,
        contract: MonitoringContract | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if public is None or not callable(getattr(public, "call", None)):
            _refuse("monitoring_public_adapter_required")
        if tenant is None or not getattr(tenant, "location_id", None):
            _refuse("monitoring_tenant_required")
        self._public = public
        self._tenant = tenant
        self._binding = binding or MonitoringContractBinding.from_operations(operations)
        self._contract = contract or DEFAULT_CONTRACT
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._recorder = _bind_recorder(public)

    @property
    def binding(self) -> MonitoringContractBinding:
        return self._binding

    @property
    def contract(self) -> MonitoringContract:
        return self._contract

    # -- transport -------------------------------------------------------

    def _page(
        self,
        operation_id: str,
        *,
        workflow_id: str,
        window: QueryWindow,
        cursor: str | None,
        filters: Mapping[str, Any],
        receipts: list[str],
        extra_query: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        start_name, end_name = self._binding.require_window_params()
        query: dict[str, Any] = {
            start_name: format_time(window.start),
            end_name: format_time(window.end),
        }
        for key, value in dict(filters).items():
            query[str(key)] = value
        if extra_query:
            for key, value in dict(extra_query).items():
                query[str(key)] = value
        if cursor is not None:
            if not self._binding.cursor_param:
                _refuse("monitoring_cursor_param_unverified", owner="WF00")
            query[self._binding.cursor_param] = cursor

        result = self._public.call(
            operation_id=operation_id,
            tenant=self._tenant,
            path_params={self._binding.workflow_param: workflow_id},
            query=query,
        )
        status = getattr(result.status, "value", result.status)
        if status != "ok":
            error = dict(result.error or {})
            _refuse(
                "monitoring_call_not_ok",
                operation=operation_id,
                status=str(status),
                rule=str(error.get("rule", "unknown")),
            )
        receipts.append(str(result.receipt_id))

        response = self._recorder.last
        body = getattr(response, "body", b"") if response is not None else b""
        if not body:
            return {}
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _refuse("monitoring_page_not_json", operation=operation_id)
        if not isinstance(parsed, Mapping):
            _refuse("monitoring_page_shape_unknown", reason="not_a_mapping")
        return parsed

    # -- reads -----------------------------------------------------------

    def logs(
        self,
        *,
        workflow_id: str,
        start: "datetime | str",
        end: "datetime | str",
        filters: Mapping[str, Any] | None = None,
        max_pages: int = MAX_PAGES_PER_SCAN,
        now: "datetime | str | None" = None,
    ) -> MonitoringScan:
        windows = self._contract.windows(start, end, now=now or self._clock())
        receipts: list[str] = []

        def fetch_page(window: QueryWindow, cursor: str | None, page_filters: Mapping[str, Any]) -> Mapping[str, Any]:
            return self._page(
                self._binding.logs_operation_id,
                workflow_id=workflow_id,
                window=window,
                cursor=cursor,
                filters=page_filters,
                receipts=receipts,
            )

        return scan(
            workflow_id=workflow_id,
            windows=windows,
            fetch_page=fetch_page,
            filters=filters,
            max_pages=max_pages,
            receipts=receipts,
            contract_revision=self._contract.revision,
        )

    def aggregate(
        self,
        *,
        workflow_id: str,
        start: "datetime | str",
        end: "datetime | str",
        group_by: Sequence[str],
        limit: int,
        group_query: Mapping[str, Any],
        declared_limit: int | None = None,
        filters: Mapping[str, Any] | None = None,
        now: "datetime | str | None" = None,
    ) -> AggregateScan:
        groups = tuple(str(item) for item in group_by)
        if not groups or len(set(groups)) != len(groups):
            _refuse("aggregate_group_invalid", reason="group_by must be non-empty and distinct")
        if not isinstance(group_query, Mapping) or not group_query:
            # The documented grouping parameter names are part of the WF00 row.
            _refuse("aggregate_group_query_unverified", owner="WF00")
        bound = self._contract.group_limit(limit=limit, declared_limit=declared_limit)
        windows = self._contract.windows(start, end, now=now or self._clock())
        receipts: list[str] = []
        metrics: list[MetricSummary] = []
        for window in windows:
            body = self._page(
                self._binding.aggregate_operation_id,
                workflow_id=workflow_id,
                window=window,
                cursor=None,
                filters=filters or {},
                receipts=receipts,
                extra_query=group_query,
            )
            metrics.append(read_aggregate(body, group_limit=bound))
        return AggregateScan(
            workflow_id=workflow_id.strip(),
            group_by=groups,
            windows=windows,
            metrics=tuple(metrics),
            receipt_ids=tuple(receipts),
            contract_revision=self._contract.revision,
        )
