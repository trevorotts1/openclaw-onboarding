"""Knowledge Base lifecycle over the frozen public adapter (WF30).

The lifecycle is a set of SEPARATE checkpoints.  No later checkpoint is ever
inferred from an earlier one:

    inventory/limit -> knowledge base -> source preview/discovery -> crawl
    ingestion -> training/indexing -> agent attachment -> retrieval evaluation

File sources add their own checkpoints:

    local validation -> multipart upload accepted -> parser/ingestion pending
    (unknown until the platform exposes a status for that file) -> training -> attachment

Wire contract: the operation rows live in :mod:`public.operations` and are
owned by WF00.  This module never invents a path, a Version literal, a scope or
a body field: every call goes through ``PublicGhlOperation.call`` so the frozen
row, tenant binding, approval, reach-back and capability rules apply.  The
operation ids this module expects are declared in ``OPERATION_IDS`` and are the
subject of a WF00 change request; an absent row refuses loudly.

The public result envelope carries no response body (result.py 2.2), so this
module records the same transport responses the adapter already received and
parses IDs/statuses from them.  Recorded bytes never enter an envelope.

Multipart: the frozen public transport is JSON-only.  WF01 owns the extension.
Until that seam exists, an upload refuses with a named gap before any network
call; it NEVER base64-encodes file bytes into an invented JSON key and never
returns a fake success.  ``MultipartUploadRequest`` is the frozen payload
interface this lane hands to WF01.

Source content is DATA.  A fetched page or document cannot change admin
settings, approve sources or elevate an audience; only the operator-supplied
policy and capability gate do that.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

from .adapter import PublicGhlAdapter
from .auth import TenantBinding
from .errors import ContractViolation
from .idempotency import IdempotencyKey
from .readback import ReadbackSpec
from .result import OperationResult, Status
from .transport import Transport, TransportResponse

# ---------------------------------------------------------------------------
# operation ids (rows owned by WF00; exact vendor evidence in the change request)
# ---------------------------------------------------------------------------

OPERATION_IDS: dict[str, str] = {
    "list": "knowledge_bases.list",
    "get": "knowledge_bases.get",
    "create": "knowledge_bases.create",
    "update": "knowledge_bases.update",
    "delete": "knowledge_bases.delete",
    # crawler (discovery != crawling != training)
    "crawler.urls": "knowledge_bases.crawler.urls",
    "crawler.discover": "knowledge_bases.crawler.discover",
    "crawler.status": "knowledge_bases.crawler.status",
    "crawler.train": "knowledge_bases.crawler.train",
    "crawler.delete_urls": "knowledge_bases.crawler.delete_urls",
    # native FAQ knowledge sources
    "faqs.list": "knowledge_bases.faqs.list",
    "faqs.create": "knowledge_bases.faqs.create",
    "faqs.update": "knowledge_bases.faqs.update",
    "faqs.delete": "knowledge_bases.faqs.delete",
    # file sources: NO published contract in apps/knowledge-base.json (WF00 gap row)
    "file.upload": "knowledge_bases.sources.upload",
    # native Conversation AI agent attachment (WF28 family rows, shared interface)
    "agent.get": "conversation_ai.agents.get",
    "agent.update": "conversation_ai.agents.update",
}

#: Documented native limits/facts (vendor apps/knowledge-base.json, reviewed
#: 2026-11-08).  Revalidated by tests; a change is a contract change, not a
#: silent constant bump.
KB_PER_LOCATION_LIMIT = 15
KB_FILE_MAX_BYTES = 10 * 1024 * 1024
KB_FILE_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
KB_FILE_MAGIC: dict[str, bytes] = {
    ".pdf": b"%PDF-",
    ".doc": b"\xd0\xcf\x11\xe0",
    ".docx": b"PK\x03\x04",
}
CRAWLER_OPTIONS: tuple[str, ...] = ("Exact", "Path", "Domain")

#: Vendor crawler/ingestion status enum, split by meaning.  ``Training`` is a
#: separate checkpoint from ``Successful``; an accepted source is never trained.
CRAWLER_PENDING: frozenset[str] = frozenset({"Pending", "Processing"})
CRAWLER_TRAINING: frozenset[str] = frozenset({"Training"})
CRAWLER_COMPLETE: frozenset[str] = frozenset({"Successful", "Existing"})
CRAWLER_FAILED: frozenset[str] = frozenset({"Failed", "Cancelled", "Aborted", "Restricted"})

#: The five mandatory retrieval evaluations (Document 1 section 27.4).
REQUIRED_RETRIEVAL_KINDS: tuple[str, ...] = (
    "known_answer",
    "conflict",
    "outside_material",
    "stale_after_update",
    "cross_client",
)

# ---------------------------------------------------------------------------
# refusals (pre-transport, typed; never a fake success)
# ---------------------------------------------------------------------------

class KnowledgeBaseGap(ContractViolation):
    """A required contract is missing; the operation cannot run honestly."""

    rule = "knowledge_base_gap"


class KnowledgeBaseRefusal(ContractViolation):
    """Policy/validation refusal decided before transport."""

    rule = "knowledge_base_refused"

# ---------------------------------------------------------------------------
# lifecycle vocabulary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KnowledgeBaseSummary:
    id: str
    name: str
    location_id: str
    created_at: str | None = None


@dataclass(frozen=True)
class KnowledgeBaseInventory:
    items: tuple[KnowledgeBaseSummary, ...]
    active_count: int
    has_more: bool
    last_id: str | None
    limit: int | None

    def find_by_name(self, name: str) -> KnowledgeBaseSummary | None:
        wanted = _normalized_name(name)
        for item in self.items:
            if _normalized_name(item.name) == wanted:
                return item
        return None


@dataclass(frozen=True)
class CapacityDecision:
    action: str  # "reuse" | "create"
    reason: str
    existing_id: str | None = None
    active_count: int = 0
    limit: int = KB_PER_LOCATION_LIMIT


@dataclass(frozen=True)
class SourceDocument:
    """One approved business source.  ``approved`` is operator evidence."""

    source_id: str
    kind: str  # "url" | "file"
    uri: str
    fingerprint: str
    approved: bool = False
    option: str = "Exact"
    content_type: str | None = None
    byte_size: int | None = None
    owner_client_id: str | None = None
    audience: str | None = None
    update_policy: str | None = None


@dataclass(frozen=True)
class SourcePolicy:
    """Operator-supplied content-use policy (Skill 38 owns the policy text)."""

    approved_url_hosts: tuple[str, ...] = ()
    denied_path_markers: tuple[str, ...] = (
        ".git",
        ".env",
        "secrets",
        "credentials",
        "prompts",
        "agents.md",
        "claude.md",
        "skill.md",
    )
    allow_uris: tuple[str, ...] = ()

    def permits_uri(self, uri: str) -> bool:
        allowed = tuple(str(item) for item in self.allow_uris)
        return any(uri == entry or uri.startswith(entry) for entry in allowed)


@dataclass(frozen=True)
class SourceUpdatePlan:
    to_add: tuple[SourceDocument, ...]
    to_update: tuple[SourceDocument, ...]
    unchanged: tuple[SourceDocument, ...]
    missing_from_input: tuple[str, ...]

    @property
    def changed(self) -> tuple[SourceDocument, ...]:
        return self.to_add + self.to_update


@dataclass(frozen=True)
class RemovalImpact:
    knowledge_base_id: str
    source_id: str
    affected_agents: tuple[str, ...]
    requires_acknowledgement: bool
    deletion_performed: bool = False


@dataclass(frozen=True)
class IngestionJob:
    """A resumable vendor job.  Timeout is pending/unknown, never recreated."""

    operation_id: str
    knowledge_base_id: str
    stage: str  # "crawl" | "train"
    state: str  # pending | processing | training | complete | failed | pending_unknown
    vendor_status: str | None = None
    discovered_count: int | None = None
    trained_count: int | None = None
    attempts: int = 1
    resumable: bool = True
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MultipartUploadRequest:
    """Frozen payload interface handed to WF01's central multipart transport.

    The transport constructs the boundary and the body, binds the tenant
    credential, and hashes the actual bytes.  Authorization NEVER travels as a
    form field, and the token is never forwarded to an asset host.
    """

    operation_id: str
    tenant: str
    knowledge_base_id: str
    fields: Mapping[str, str]
    file_field: str
    filename: str
    content_type: str
    content: bytes
    content_sha256: str
    version: str | None = None
    timeout_s: float = 60.0


@dataclass(frozen=True)
class MultipartResponse:
    status: int | None
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""
    error_kind: str = "none"


class MultipartTransport:
    """Seam implemented by WF01 (protocol shape only, no implementation)."""

    def upload(self, request: MultipartUploadRequest) -> MultipartResponse:  # pragma: no cover
        raise KnowledgeBaseGap(
            "multipart_transport_not_implemented",
            detail={"owner": "WF01", "operation_id": request.operation_id},
        )


@dataclass(frozen=True)
class UploadAcceptance:
    """Upload acceptance is its own checkpoint; it is never 'trained'."""

    operation_id: str
    knowledge_base_id: str
    filename: str
    content_sha256: str
    byte_size: int
    content_type: str
    accepted: bool
    http_status: int | None
    upload_state: str  # accepted | refused | unknown_outcome
    ingestion_state: str = "pending_unknown"
    training_state: str = "not_started"
    attachment_state: str = "not_attached"
    provider_file_id: str | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KbCall:
    stage: str
    result: OperationResult
    body: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class AgentKnowledgeState:
    agent_id: str
    knowledge_base_ids: tuple[str, ...]
    call: KbCall


@dataclass(frozen=True)
class AttachmentOutcome:
    agent_id: str
    knowledge_base_id: str
    attached: bool
    previous_ids: tuple[str, ...]
    requested_ids: tuple[str, ...]
    verified: bool
    result: OperationResult | None
    state: str  # attached | detached | unchanged | refused | unknown_outcome


@dataclass(frozen=True)
class RetrievalCase:
    case_id: str
    kind: str
    question: str
    expected_source_id: str | None = None
    expected_answer_fragment: str | None = None
    conflict_source_id: str | None = None
    updated_source_id: str | None = None
    stale_source_id: str | None = None
    other_client_id: str | None = None


@dataclass(frozen=True)
class RetrievalAnswer:
    text: str
    cited_source_ids: tuple[str, ...] = ()
    cited_client_id: str | None = None
    conflict_reported: bool = False
    refused: bool = False


@dataclass(frozen=True)
class RetrievalCaseResult:
    case_id: str
    kind: str
    state: str  # verified | failed | not_run
    reason: str
    answer: RetrievalAnswer | None = None


@dataclass(frozen=True)
class RetrievalReport:
    state: str  # verified | failed | not_run
    results: tuple[RetrievalCaseResult, ...]
    knowledge_base_id: str
    agent_id: str | None
    knowledge_base_version: str | None
    source_fingerprints: Mapping[str, str]
    interrogator_used: bool
    reason: str = ""


@dataclass(frozen=True)
class KbReadiness:
    location_id: str
    knowledge_base_id: str
    agent_id: str | None
    inventory_verified: bool
    source_count: int
    crawl_state: str
    upload_state: str
    ingestion_state: str
    training_state: str
    attachment_state: str
    retrieval_state: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def ready_for_production(self) -> bool:
        """Every downstream checkpoint must be proved; upload is not training."""

        return (
            self.inventory_verified
            and self.training_state == "complete"
            and self.agent_id is not None
            and self.attachment_state == "attached"
            and self.retrieval_state == "verified"
        )

# ---------------------------------------------------------------------------
# transport recorder (same precedent as workflow_v4: the envelope has no body)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Record:
    method: str
    url: str
    version: str | None
    status: int | None
    error_kind: str
    body: bytes
    headers: Mapping[str, str]


class _RecordingTransport:
    """Keeps the response bytes the adapter already received."""

    def __init__(self, inner: Transport) -> None:
        if not callable(getattr(inner, "request", None)):
            raise ContractViolation("kb_transport_invalid")
        self._inner = inner
        self.records: list[_Record] = []

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
            _Record(
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
# pure helpers: parsing, validation, planning, evaluation
# ---------------------------------------------------------------------------

def _normalized_name(name: str) -> str:
    return str(name or "").strip().casefold()


def parse_inventory(
    body: Mapping[str, Any] | None,
) -> KnowledgeBaseInventory:
    """Parse the documented list envelope; a wrong shape is a contract defect."""

    if not isinstance(body, Mapping):
        raise ContractViolation("kb_inventory_body_missing")
    data = body.get("data") if isinstance(body.get("data"), Mapping) else body
    rows = data.get("knowledgeBases") if isinstance(data, Mapping) else None
    if not isinstance(rows, list):
        raise ContractViolation("kb_inventory_shape_invalid")
    items = tuple(
        KnowledgeBaseSummary(
            id=str(row.get("id")),
            name=str(row.get("name")),
            location_id=str(row.get("locationId", "")),
            created_at=row.get("createdAt"),
        )
        for row in rows
        if isinstance(row, Mapping) and row.get("id") and row.get("name")
    )
    if len(items) != len(rows):
        raise ContractViolation("kb_inventory_row_invalid")
    return KnowledgeBaseInventory(
        items=items,
        active_count=int(data.get("activeCount", len(items)) or 0),
        has_more=bool(data.get("hasMore", False)),
        last_id=data.get("lastKnowledgeBaseId"),
        limit=None if data.get("limit") is None else int(data.get("limit")),
    )


def choose_knowledge_base(
    inventory: KnowledgeBaseInventory,
    *,
    name: str,
    limit: int = KB_PER_LOCATION_LIMIT,
) -> CapacityDecision:
    """Reuse an exact matching name; refuse at the limit.  Never delete."""

    match = inventory.find_by_name(name)
    if match is not None:
        return CapacityDecision(
            action="reuse",
            reason="exact_name_match",
            existing_id=match.id,
            active_count=inventory.active_count,
            limit=limit,
        )
    if inventory.active_count >= limit:
        raise KnowledgeBaseRefusal(
            "kb_per_location_limit_reached",
            detail={
                "active_count": inventory.active_count,
                "limit": limit,
                "must_reuse": True,
                "delete_permitted": False,
            },
        )
    return CapacityDecision(
        action="create",
        reason="under_limit",
        active_count=inventory.active_count,
        limit=limit,
    )


def _host_allowed(host: str, allowed: tuple[str, ...]) -> bool:
    if not allowed:
        return True
    lowered = host.lower()
    return any(
        lowered == entry.lower() or lowered.endswith("." + entry.lower())
        for entry in allowed
    )


def _private_host(host: str) -> bool:
    lowered = host.lower()
    if lowered in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    match = re.match(r"^(\d{1,3})\.(\d{1,3})\.", lowered)
    if not match:
        return False
    first, second = int(match.group(1)), int(match.group(2))
    return (
        first == 10
        or (first == 192 and second == 168)
        or (first == 172 and 16 <= second <= 31)
        or (first == 169 and second == 254)
    )


def check_url_source(url: str, policy: SourcePolicy) -> str:
    """Validate an approved URL.  Returns the normalized URL."""

    parts = urlsplit(str(url))
    if parts.scheme != "https":
        raise KnowledgeBaseRefusal("kb_source_url_not_https", detail={"scheme": parts.scheme})
    if not parts.hostname:
        raise KnowledgeBaseRefusal("kb_source_url_host_missing")
    if parts.username or parts.password:
        raise KnowledgeBaseRefusal("kb_source_url_has_userinfo")
    if _private_host(parts.hostname):
        raise KnowledgeBaseRefusal("kb_source_url_private_host")
    if not _host_allowed(parts.hostname, policy.approved_url_hosts):
        raise KnowledgeBaseRefusal(
            "kb_source_url_host_not_approved",
            detail={"host": parts.hostname},
        )
    lowered = parts.path.lower()
    for marker in policy.denied_path_markers:
        if marker.lower() in lowered:
            raise KnowledgeBaseRefusal(
                "kb_source_path_denied",
                detail={"marker": marker},
            )
    return str(url)


def validate_file_source(
    path: str | Path,
    *,
    policy: SourcePolicy | None = None,
    max_bytes: int = KB_FILE_MAX_BYTES,
) -> tuple[SourceDocument, bytes]:
    """Validate a local file before upload; returns the document and bytes.

    Checks, in this order: regular file, documented extension, size limit,
    magic-byte agreement with the extension, sha256 fingerprint, denied path
    markers, and credential-shaped content.  Revalidation at upload time is the
    caller's responsibility (``revalidate_file_source``).
    """

    source_path = Path(path)
    if not source_path.is_file():
        raise KnowledgeBaseRefusal("kb_source_file_missing", detail={"name": source_path.name})
    extension = source_path.suffix.lower()
    if extension not in KB_FILE_TYPES:
        raise KnowledgeBaseRefusal(
            "kb_source_file_type_unsupported",
            detail={"extension": extension, "allowed": sorted(KB_FILE_TYPES)},
        )
    byte_size = source_path.stat().st_size
    if byte_size <= 0:
        raise KnowledgeBaseRefusal("kb_source_file_empty")
    if byte_size > int(max_bytes):
        raise KnowledgeBaseRefusal(
            "kb_source_file_too_large",
            detail={"byte_size": byte_size, "max_bytes": int(max_bytes)},
        )
    content = source_path.read_bytes()
    if not content.startswith(KB_FILE_MAGIC[extension]):
        raise KnowledgeBaseRefusal(
            "kb_source_file_content_mismatch",
            detail={"extension": extension},
        )
    effective = policy or SourcePolicy()
    lowered = str(source_path).lower()
    for marker in effective.denied_path_markers:
        if marker.lower() in lowered:
            raise KnowledgeBaseRefusal(
                "kb_source_path_denied",
                detail={"marker": marker},
            )
    _refuse_credential_content(content)
    document = SourceDocument(
        source_id="file:" + hashlib.sha256(content).hexdigest()[:16],
        kind="file",
        uri=str(source_path),
        fingerprint=hashlib.sha256(content).hexdigest(),
        approved=True,
        content_type=KB_FILE_TYPES[extension],
        byte_size=byte_size,
    )
    return document, content


def revalidate_file_source(
    document: SourceDocument,
    *,
    max_bytes: int = KB_FILE_MAX_BYTES,
) -> bytes:
    """Re-read and re-hash immediately before upload; a change refuses."""

    if document.kind != "file":
        raise KnowledgeBaseRefusal("kb_source_not_a_file", detail={"kind": document.kind})
    fresh, content = validate_file_source(document.uri, max_bytes=max_bytes)
    if fresh.fingerprint != document.fingerprint:
        raise KnowledgeBaseRefusal(
            "kb_source_changed_since_validation",
            detail={
                "validated": document.fingerprint,
                "current": fresh.fingerprint,
            },
        )
    return content


_CREDENTIAL_MARKERS: tuple[bytes, ...] = (
    b"BEGIN RSA PRIVATE KEY",
    b"BEGIN OPENSSH PRIVATE KEY",
    b"BEGIN EC PRIVATE KEY",
    b"BEGIN PRIVATE KEY",
    b"Authorization: Bearer ",
    b"GHL_API_KEY=",
    b"OPENAI_API_KEY=",
    b"ANTHROPIC_API_KEY=",
    b"AWS_SECRET_ACCESS_KEY=",
)


def _refuse_credential_content(content: bytes) -> None:
    for marker in _CREDENTIAL_MARKERS:
        if marker in content:
            raise KnowledgeBaseRefusal(
                "kb_source_contains_credential_material",
                detail={"marker": marker.decode("ascii", "replace")},
            )


def check_source_owner(
    document: SourceDocument, *, expected_client_id: str | None
) -> None:
    """Another client's data is never accepted as this tenant's knowledge."""

    if (
        expected_client_id
        and document.owner_client_id
        and str(document.owner_client_id) != str(expected_client_id)
    ):
        raise KnowledgeBaseRefusal(
            "kb_source_cross_client_refused",
            detail={"owner_recorded": True},
        )


def plan_source_updates(
    existing: Mapping[str, str],
    incoming: Sequence[SourceDocument],
) -> SourceUpdatePlan:
    """Update only changed material; preserve everything else."""

    additions: list[SourceDocument] = []
    updates: list[SourceDocument] = []
    unchanged: list[SourceDocument] = []
    incoming_by_source: dict[str, SourceDocument] = {}
    for document in incoming:
        if not document.approved:
            raise KnowledgeBaseRefusal(
                "kb_source_not_approved", detail={"source_id": document.source_id}
            )
        prior = incoming_by_source.get(document.source_id)
        if prior is not None and prior.fingerprint != document.fingerprint:
            raise KnowledgeBaseRefusal(
                "kb_source_duplicate_conflicting_fingerprint",
                detail={"source_id": document.source_id},
            )
        incoming_by_source[document.source_id] = document
        if document.source_id not in existing:
            additions.append(document)
        elif str(existing[document.source_id]) != document.fingerprint:
            updates.append(document)
        else:
            unchanged.append(document)
    missing = tuple(sorted(set(existing) - set(incoming_by_source)))
    return SourceUpdatePlan(
        to_add=tuple(additions),
        to_update=tuple(updates),
        unchanged=tuple(unchanged),
        missing_from_input=missing,
    )


def plan_source_removal(
    *,
    knowledge_base_id: str,
    source_id: str,
    agents_by_knowledge_base: Mapping[str, Sequence[str]],
    acknowledged_agents: Sequence[str] = (),
) -> RemovalImpact:
    """Show affected agents first; removal needs their acknowledgement.

    Reaching a knowledge-base limit is NEVER a reason to call this: the limit
    path refuses (``choose_knowledge_base``) instead of deleting.
    """

    affected = tuple(sorted(str(item) for item in agents_by_knowledge_base.get(knowledge_base_id, ())))
    acknowledged = tuple(sorted(str(item) for item in acknowledged_agents))
    if affected and affected != acknowledged:
        raise KnowledgeBaseRefusal(
            "kb_removal_requires_agent_acknowledgement",
            detail={"affected_agents": list(affected)},
        )
    return RemovalImpact(
        knowledge_base_id=knowledge_base_id,
        source_id=source_id,
        affected_agents=affected,
        requires_acknowledgement=bool(affected),
        deletion_performed=False,
    )


def evaluate_retrieval(
    cases: Sequence[RetrievalCase],
    *,
    interrogator: Callable[[RetrievalCase], RetrievalAnswer] | None = None,
    knowledge_base_id: str,
    agent_id: str | None,
    knowledge_base_version: str | None = None,
    source_fingerprints: Mapping[str, str] | None = None,
) -> RetrievalReport:
    """Evaluate the five mandatory retrieval cases.

    Without a real interrogator every case is ``not_run``: a mock is not live
    proof and this function never reports a pass it did not observe.
    """

    by_id: dict[str, RetrievalCase] = {}
    for case in cases:
        if case.kind not in REQUIRED_RETRIEVAL_KINDS:
            raise KnowledgeBaseRefusal(
                "retrieval_case_kind_unknown", detail={"kind": case.kind}
            )
        if case.case_id in by_id:
            raise KnowledgeBaseRefusal(
                "retrieval_case_duplicate", detail={"case_id": case.case_id}
            )
        by_id[case.case_id] = case
    missing = [kind for kind in REQUIRED_RETRIEVAL_KINDS if not any(c.kind == kind for c in cases)]
    if missing:
        raise KnowledgeBaseRefusal(
            "retrieval_cases_incomplete", detail={"missing_kinds": missing}
        )

    if interrogator is None:
        results = tuple(
            RetrievalCaseResult(
                case_id=case.case_id,
                kind=case.kind,
                state="not_run",
                reason="no_agent_interrogator_wired",
            )
            for case in cases
        )
        return RetrievalReport(
            state="not_run",
            results=results,
            knowledge_base_id=knowledge_base_id,
            agent_id=agent_id,
            knowledge_base_version=knowledge_base_version,
            source_fingerprints=dict(source_fingerprints or {}),
            interrogator_used=False,
            reason="no_agent_interrogator_wired",
        )

    results = []
    for case in cases:
        answer = interrogator(case)
        if not isinstance(answer, RetrievalAnswer):
            raise ContractViolation(
                "retrieval_answer_invalid", detail={"case_id": case.case_id}
            )
        state, reason = _judge_case(case, answer)
        results.append(
            RetrievalCaseResult(
                case_id=case.case_id,
                kind=case.kind,
                state=state,
                reason=reason,
                answer=answer,
            )
        )
    overall = "verified" if all(item.state == "verified" for item in results) else "failed"
    return RetrievalReport(
        state=overall,
        results=tuple(results),
        knowledge_base_id=knowledge_base_id,
        agent_id=agent_id,
        knowledge_base_version=knowledge_base_version,
        source_fingerprints=dict(source_fingerprints or {}),
        interrogator_used=True,
    )


def _judge_case(case: RetrievalCase, answer: RetrievalAnswer) -> tuple[str, str]:
    cited = tuple(str(item) for item in answer.cited_source_ids)
    if case.kind == "known_answer":
        if answer.refused:
            return "failed", "known_answer_refused"
        if case.expected_answer_fragment and (
            case.expected_answer_fragment.casefold() not in answer.text.casefold()
        ):
            return "failed", "known_answer_fragment_missing"
        if case.expected_source_id and case.expected_source_id not in cited:
            return "failed", "known_answer_source_not_cited"
        return "verified", "known_answer"
    if case.kind == "conflict":
        if not answer.conflict_reported:
            return "failed", "conflict_not_reported"
        if case.conflict_source_id and case.conflict_source_id not in cited:
            return "failed", "conflict_source_not_cited"
        return "verified", "conflict_reported"
    if case.kind == "outside_material":
        if not answer.refused:
            return "failed", "answered_outside_approved_material"
        if case.expected_source_id and case.expected_source_id in cited:
            return "failed", "outside_material_cited_approved_source"
        return "verified", "outside_material_refused"
    if case.kind == "stale_after_update":
        if case.stale_source_id and case.stale_source_id in cited:
            return "failed", "stale_source_still_cited"
        if case.updated_source_id and case.updated_source_id not in cited:
            return "failed", "updated_source_not_cited"
        return "verified", "updated_source_cited"
    if case.kind == "cross_client":
        if answer.cited_client_id and case.other_client_id and (
            str(answer.cited_client_id) == str(case.other_client_id)
        ):
            return "failed", "cross_client_leak"
        if not answer.refused:
            return "failed", "cross_client_not_refused"
        return "verified", "cross_client_refused"
    return "failed", "case_kind_unknown"

# ---------------------------------------------------------------------------
# the client
# ---------------------------------------------------------------------------

class KnowledgeBaseClient:
    """KB lifecycle over one frozen public adapter."""

    def __init__(
        self,
        *,
        public: PublicGhlAdapter,
        transport: Transport | None = None,
        multipart: MultipartTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(public, PublicGhlAdapter):
            raise ContractViolation("public_adapter_required")
        base: Transport | None = transport
        if base is None:
            base = getattr(public, "_transport", None)  # ponytail: see module note
        if base is None or not callable(getattr(base, "request", None)):
            raise ContractViolation("kb_transport_unavailable")
        recorder = base if isinstance(base, _RecordingTransport) else _RecordingTransport(base)
        if not isinstance(base, _RecordingTransport):
            try:
                public._transport = recorder  # ponytail: see module note
            except AttributeError:  # pragma: no cover - defensive
                raise ContractViolation("kb_transport_unbindable") from None
        self._public = public
        self._transport = recorder
        self._multipart = multipart
        self._sleep = sleep
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # -- inventory / capacity -------------------------------------------------

    def inventory(
        self,
        tenant: TenantBinding,
        *,
        query: str | None = None,
        limit: int | None = None,
        last_id: str | None = None,
    ) -> KbCall:
        params: dict[str, Any] = {}
        if query is not None:
            params["query"] = query
        if limit is not None:
            params["limit"] = int(limit)
        if last_id is not None:
            params["lastKnowledgeBaseId"] = last_id
        return self._invoke(
            stage="inventory",
            operation_id=OPERATION_IDS["list"],
            tenant=tenant,
            query=params,
        )

    def get(self, tenant: TenantBinding, knowledge_base_id: str) -> KbCall:
        return self._invoke(
            stage="inventory",
            operation_id=OPERATION_IDS["get"],
            tenant=tenant,
            path_params={"knowledgeBaseId": _required(knowledge_base_id, "knowledgeBaseId")},
        )

    def create(
        self,
        tenant: TenantBinding,
        *,
        name: str,
        description: str | None = None,
        approval: Any = None,
        idempotency_key: str | None = None,
    ) -> KbCall:
        body: dict[str, Any] = {"name": _required(name, "name")}
        if description is not None:
            body["description"] = str(description)
        # The created id is not knowable before the call, so the frozen
        # read-back plan is the list read (success envelope); this client then
        # re-reads the returned id and never treats a 201 alone as verified.
        readback = ReadbackSpec(
            operation_id=OPERATION_IDS["list"],
            query={},
            expect={"success": True},
            description="kb create envelope",
        )
        return self._invoke(
            stage="kb_created",
            operation_id=OPERATION_IDS["create"],
            tenant=tenant,
            body=body,
            write=True,
            approval=approval,
            readback=readback,
            idempotency_key=idempotency_key,
        )

    def update(
        self,
        tenant: TenantBinding,
        knowledge_base_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        approval: Any = None,
        idempotency_key: str | None = None,
    ) -> KbCall:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = str(name)
        if description is not None:
            body["description"] = str(description)
        if not body:
            raise KnowledgeBaseRefusal("kb_update_empty")
        return self._invoke(
            stage="kb_updated",
            operation_id=OPERATION_IDS["update"],
            tenant=tenant,
            path_params={"id": _required(knowledge_base_id, "id")},
            body=body,
            write=True,
            approval=approval,
            readback=self._kb_readback(knowledge_base_id),
            idempotency_key=idempotency_key,
        )

    def delete(
        self,
        tenant: TenantBinding,
        knowledge_base_id: str,
        *,
        agents_by_knowledge_base: Mapping[str, Sequence[str]] | None = None,
        acknowledged_agents: Sequence[str] = (),
        approval: Any = None,
        idempotency_key: str | None = None,
    ) -> KbCall:
        plan_source_removal(
            knowledge_base_id=knowledge_base_id,
            source_id="*",
            agents_by_knowledge_base=agents_by_knowledge_base or {},
            acknowledged_agents=acknowledged_agents,
        )
        return self._invoke(
            stage="kb_deleted",
            operation_id=OPERATION_IDS["delete"],
            tenant=tenant,
            path_params={"knowledgeBaseId": _required(knowledge_base_id, "knowledgeBaseId")},
            write=True,
            approval=approval,
            readback=ReadbackSpec(
                operation_id=OPERATION_IDS["list"],
                query={},
                expect={"success": True},
                description="kb delete envelope",
            ),
            idempotency_key=idempotency_key,
        )

    # -- crawler sources ------------------------------------------------------

    def discover_urls(
        self,
        tenant: TenantBinding,
        *,
        knowledge_base_id: str,
        url: str,
        option: str = "Exact",
        policy: SourcePolicy | None = None,
        approval: Any = None,
        idempotency_key: str | None = None,
    ) -> KbCall:
        if option not in CRAWLER_OPTIONS:
            raise KnowledgeBaseRefusal(
                "kb_crawler_option_invalid",
                detail={"option": option, "allowed": list(CRAWLER_OPTIONS)},
            )
        check_url_source(url, policy or SourcePolicy())
        return self._invoke(
            stage="source_discovered",
            operation_id=OPERATION_IDS["crawler.discover"],
            tenant=tenant,
            body={
                "url": str(url),
                "option": str(option),
                "knowledgeBaseId": _required(knowledge_base_id, "knowledgeBaseId"),
            },
            write=True,
            approval=approval,
            readback=self._kb_readback(knowledge_base_id),
            idempotency_key=idempotency_key,
        )

    def crawl_status(
        self,
        tenant: TenantBinding,
        *,
        knowledge_base_id: str,
        operation_id: str,
    ) -> KbCall:
        return self._invoke(
            stage="crawl_ingested",
            operation_id=OPERATION_IDS["crawler.status"],
            tenant=tenant,
            query={
                "knowledgeBaseId": _required(knowledge_base_id, "knowledgeBaseId"),
                "operationId": _required(operation_id, "operationId"),
            },
        )

    def trained_urls(
        self,
        tenant: TenantBinding,
        *,
        knowledge_base_id: str,
        page: int | None = None,
        page_length: int | None = None,
        query: str | None = None,
    ) -> KbCall:
        params: dict[str, Any] = {
            "knowledgeBaseId": _required(knowledge_base_id, "knowledgeBaseId")
        }
        if page is not None:
            params["page"] = int(page)
        if page_length is not None:
            params["pageLength"] = int(page_length)
        if query is not None:
            params["query"] = str(query)
        return self._invoke(
            stage="training_complete",
            operation_id=OPERATION_IDS["crawler.urls"],
            tenant=tenant,
            query=params,
        )

    def train_urls(
        self,
        tenant: TenantBinding,
        *,
        knowledge_base_id: str,
        operation_id: str,
        url_ids: Sequence[str],
        approval: Any = None,
        idempotency_key: str | None = None,
    ) -> KbCall:
        ids = [str(item) for item in url_ids if str(item).strip()]
        if not ids:
            raise KnowledgeBaseRefusal("kb_train_url_ids_missing")
        return self._invoke(
            stage="training_requested",
            operation_id=OPERATION_IDS["crawler.train"],
            tenant=tenant,
            body={
                "knowledgeBaseId": _required(knowledge_base_id, "knowledgeBaseId"),
                "operationId": _required(operation_id, "operationId"),
                "urlIds": ids,
            },
            write=True,
            approval=approval,
            readback=self._kb_readback(knowledge_base_id),
            idempotency_key=idempotency_key,
        )

    def delete_trained_urls(
        self,
        tenant: TenantBinding,
        *,
        knowledge_base_id: str,
        url_ids: Sequence[str],
        agents_by_knowledge_base: Mapping[str, Sequence[str]] | None = None,
        acknowledged_agents: Sequence[str] = (),
        approval: Any = None,
        idempotency_key: str | None = None,
    ) -> KbCall:
        ids = [str(item) for item in url_ids if str(item).strip()]
        if not ids:
            raise KnowledgeBaseRefusal("kb_delete_url_ids_missing")
        plan_source_removal(
            knowledge_base_id=knowledge_base_id,
            source_id=",".join(ids),
            agents_by_knowledge_base=agents_by_knowledge_base or {},
            acknowledged_agents=acknowledged_agents,
        )
        return self._invoke(
            stage="source_removed",
            operation_id=OPERATION_IDS["crawler.delete_urls"],
            tenant=tenant,
            body={
                "knowledgeBaseId": _required(knowledge_base_id, "knowledgeBaseId"),
                "urlIds": ids,
            },
            write=True,
            approval=approval,
            readback=self._kb_readback(knowledge_base_id),
            idempotency_key=idempotency_key,
        )

    # -- FAQs -----------------------------------------------------------------

    def list_faqs(
        self,
        tenant: TenantBinding,
        *,
        knowledge_base_id: str,
        limit: int | None = None,
        last_faq_id: str | None = None,
    ) -> KbCall:
        params: dict[str, Any] = {
            "knowledgeBaseId": _required(knowledge_base_id, "knowledgeBaseId")
        }
        if limit is not None:
            params["limit"] = int(limit)
        if last_faq_id is not None:
            params["lastFaqId"] = str(last_faq_id)
        return self._invoke(
            stage="source_preview",
            operation_id=OPERATION_IDS["faqs.list"],
            tenant=tenant,
            query=params,
        )

    def create_faq(
        self,
        tenant: TenantBinding,
        *,
        knowledge_base_id: str,
        question: str,
        answer: str,
        approval: Any = None,
        idempotency_key: str | None = None,
    ) -> KbCall:
        body = {
            "knowledgeBaseId": _required(knowledge_base_id, "knowledgeBaseId"),
            "question": _required(question, "question"),
            "answer": _required(answer, "answer"),
        }
        return self._invoke(
            stage="training_requested",
            operation_id=OPERATION_IDS["faqs.create"],
            tenant=tenant,
            body=body,
            write=True,
            approval=approval,
            readback=self._kb_readback(knowledge_base_id),
            idempotency_key=idempotency_key,
        )

    # -- file sources (multipart seam owned by WF01) --------------------------

    def upload_source_file(
        self,
        tenant: TenantBinding,
        *,
        knowledge_base_id: str,
        path: str | Path,
        policy: SourcePolicy | None = None,
        known_fingerprints: Mapping[str, str] | None = None,
        max_bytes: int = KB_FILE_MAX_BYTES,
    ) -> UploadAcceptance:
        document, content = validate_file_source(path, policy=policy, max_bytes=max_bytes)
        if self._row_exists(OPERATION_IDS["file.upload"]) is False:
            raise KnowledgeBaseGap(
                "file_upload_contract_unresolved",
                detail={
                    "operation_id": OPERATION_IDS["file.upload"],
                    "owner": "WF00",
                    "reason": (
                        "apps/knowledge-base.json publishes no file-source upload "
                        "operation; no path, media type or body field may be invented"
                    ),
                },
            )
        if self._multipart is None:
            raise KnowledgeBaseGap(
                "multipart_transport_unavailable",
                detail={
                    "operation_id": OPERATION_IDS["file.upload"],
                    "owner": "WF01",
                    "hint": "wire MultipartTransport (WF01) before uploading",
                },
            )
        # Revalidate at the moment of upload: a file that changed after approval
        # is refused rather than sent under an old fingerprint.
        content = revalidate_file_source(document, max_bytes=max_bytes)
        if known_fingerprints is not None:
            prior = known_fingerprints.get(document.source_id)
            if prior is not None and str(prior) == document.fingerprint:
                raise KnowledgeBaseRefusal(
                    "kb_source_unchanged_upload_refused",
                    detail={"source_id": document.source_id},
                )
        request = MultipartUploadRequest(
            operation_id=OPERATION_IDS["file.upload"],
            tenant=tenant.location_id,
            knowledge_base_id=_required(knowledge_base_id, "knowledgeBaseId"),
            fields={"knowledgeBaseId": str(knowledge_base_id)},
            file_field="file",
            filename=Path(path).name,
            content_type=document.content_type or "application/octet-stream",
            content=content,
            content_sha256=document.fingerprint,
            timeout_s=60.0,
        )
        response = self._multipart.upload(request)
        if not isinstance(response, MultipartResponse):
            raise ContractViolation("multipart_response_invalid")
        accepted = (
            response.error_kind == "none"
            and response.status is not None
            and 200 <= int(response.status) < 300
        )
        state = (
            "accepted"
            if accepted
            else "unknown_outcome"
            if response.error_kind != "none" or response.status is None or int(response.status) >= 500
            else "refused"
        )
        return UploadAcceptance(
            operation_id=OPERATION_IDS["file.upload"],
            knowledge_base_id=str(knowledge_base_id),
            filename=Path(path).name,
            content_sha256=document.fingerprint,
            byte_size=len(content),
            content_type=request.content_type,
            accepted=accepted,
            http_status=response.status,
            upload_state=state,
            provider_file_id=_provider_file_id(response.body),
            evidence={
                "error_kind": response.error_kind,
                "response_fingerprint": (
                    hashlib.sha256(response.body).hexdigest() if response.body else None
                ),
                "boundary_constructed_by": "transport",
                "authorization_in_fields": False,
            },
        )

    # -- bounded polling ------------------------------------------------------

    def poll_job(
        self,
        tenant: TenantBinding,
        *,
        knowledge_base_id: str,
        job: IngestionJob,
        max_polls: int = 8,
        interval_s: float = 0.0,
    ) -> IngestionJob:
        """Poll a vendor job by resumable id.  A timeout is pending/unknown."""

        if max_polls < 1:
            raise KnowledgeBaseRefusal("kb_poll_budget_invalid", detail={"max_polls": max_polls})
        attempts = 0
        current = job
        while attempts < max_polls:
            attempts += 1
            call = self.crawl_status(
                tenant,
                knowledge_base_id=knowledge_base_id,
                operation_id=job.operation_id,
            )
            if call.result.status is not Status.ok or not call.body:
                return _job_with(
                    current,
                    state="pending_unknown",
                    attempts=attempts,
                    detail={"reason": "status_unreadable", "rule": (call.result.error or {}).get("rule")},
                )
            parsed = _parse_job_status(call.body)
            state = _job_state(parsed["status"], stage=job.stage)
            current = _job_with(
                current,
                state=state,
                vendor_status=parsed["status"],
                discovered_count=parsed.get("discovered_count"),
                trained_count=parsed.get("trained_count"),
                attempts=attempts,
                resumable=state not in ("complete", "failed"),
            )
            if state in ("complete", "failed"):
                return current
            if interval_s:
                self._sleep(float(interval_s))
        return _job_with(
            current,
            state="pending_unknown",
            attempts=attempts,
            resumable=True,
            detail={"reason": "poll_budget_exhausted"},
        )

    # -- native agent attachment ---------------------------------------------

    def read_agent_knowledge(
        self, tenant: TenantBinding, *, agent_id: str
    ) -> AgentKnowledgeState:
        call = self._invoke(
            stage="agent_attachment",
            operation_id=OPERATION_IDS["agent.get"],
            tenant=tenant,
            path_params={"agentId": _required(agent_id, "agentId")},
        )
        if call.result.status is not Status.ok or not call.body:
            raise KnowledgeBaseRefusal(
                "agent_state_unread",
                detail={"rule": (call.result.error or {}).get("rule")},
            )
        ids = call.body.get("knowledgeBaseIds")
        if ids is None:
            ids = []
        if not isinstance(ids, list):
            raise ContractViolation("agent_knowledge_base_ids_invalid")
        return AgentKnowledgeState(
            agent_id=str(agent_id),
            knowledge_base_ids=tuple(str(item) for item in ids),
            call=call,
        )

    def attach_knowledge_base(
        self,
        tenant: TenantBinding,
        *,
        agent_id: str,
        knowledge_base_id: str,
        approval: Any = None,
        idempotency_key: str | None = None,
    ) -> AttachmentOutcome:
        return self._change_attachment(
            tenant,
            agent_id=agent_id,
            knowledge_base_id=knowledge_base_id,
            attach=True,
            approval=approval,
            idempotency_key=idempotency_key,
        )

    def detach_knowledge_base(
        self,
        tenant: TenantBinding,
        *,
        agent_id: str,
        knowledge_base_id: str,
        approval: Any = None,
        idempotency_key: str | None = None,
    ) -> AttachmentOutcome:
        return self._change_attachment(
            tenant,
            agent_id=agent_id,
            knowledge_base_id=knowledge_base_id,
            attach=False,
            approval=approval,
            idempotency_key=idempotency_key,
        )

    def _change_attachment(
        self,
        tenant: TenantBinding,
        *,
        agent_id: str,
        knowledge_base_id: str,
        attach: bool,
        approval: Any,
        idempotency_key: str | None,
    ) -> AttachmentOutcome:
        current = self.read_agent_knowledge(tenant, agent_id=agent_id)
        previous = current.knowledge_base_ids
        wanted = list(previous)
        if attach and knowledge_base_id not in wanted:
            wanted.append(knowledge_base_id)
        if not attach:
            wanted = [item for item in wanted if item != knowledge_base_id]
        if tuple(wanted) == previous:
            return AttachmentOutcome(
                agent_id=str(agent_id),
                knowledge_base_id=str(knowledge_base_id),
                attached=attach,
                previous_ids=previous,
                requested_ids=tuple(wanted),
                verified=True,
                result=None,
                state="unchanged",
            )
        call = self._invoke(
            stage="agent_attachment",
            operation_id=OPERATION_IDS["agent.update"],
            tenant=tenant,
            path_params={"agentId": _required(agent_id, "agentId")},
            body={"knowledgeBaseIds": wanted},
            write=True,
            approval=approval,
            readback=ReadbackSpec(
                operation_id=OPERATION_IDS["agent.get"],
                target_params={"agentId": str(agent_id)},
                expect={"id": str(agent_id)},
                description="agent attachment read-back",
            ),
            idempotency_key=idempotency_key,
        )
        state = "unknown_outcome"
        verified = False
        if call.result.status is Status.ok:
            try:
                after = self.read_agent_knowledge(tenant, agent_id=agent_id)
            except KnowledgeBaseRefusal:
                after = None
            if after is not None:
                verified = (knowledge_base_id in after.knowledge_base_ids) if attach else (
                    knowledge_base_id not in after.knowledge_base_ids
                )
                state = ("attached" if attach else "detached") if verified else "refused"
            else:
                state = "attached" if attach else "detached"
        else:
            state = "unknown_outcome" if call.result.status is Status.unknown_outcome else "refused"
        return AttachmentOutcome(
            agent_id=str(agent_id),
            knowledge_base_id=str(knowledge_base_id),
            attached=attach,
            previous_ids=previous,
            requested_ids=tuple(wanted),
            verified=verified,
            result=call.result,
            state=state,
        )

    # -- internals ------------------------------------------------------------

    def _kb_readback(self, knowledge_base_id: str) -> ReadbackSpec:
        return ReadbackSpec(
            operation_id=OPERATION_IDS["get"],
            target_params={"knowledgeBaseId": str(knowledge_base_id)},
            expect={"id": str(knowledge_base_id)},
            description="knowledge base read-back",
        )

    def _row_exists(self, operation_id: str) -> bool | None:
        resolver = getattr(self._public, "_resolve_row", None)
        if not callable(resolver):
            return None
        try:
            resolver(operation_id)
        except ContractViolation:
            return False
        return True

    def _invoke(
        self,
        *,
        stage: str,
        operation_id: str,
        tenant: TenantBinding,
        path_params: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        write: bool = False,
        approval: Any = None,
        readback: ReadbackSpec | None = None,
        idempotency_key: str | None = None,
    ) -> KbCall:
        start = len(self._transport.records)
        key = idempotency_key
        if write and key is None:
            key = IdempotencyKey.issue(operation_id).value
        try:
            result = self._public.call(
                operation_id=operation_id,
                tenant=tenant,
                path_params=dict(path_params or {}),
                query=dict(query or {}),
                body=dict(body or {}),
                idempotency_key=key,
                approval=approval,
                readback=readback if write else None,
            )
        except ContractViolation as caught:
            if caught.rule != "unknown_operation_id":
                raise
            raise KnowledgeBaseGap(
                "kb_operation_row_missing",
                detail={"operation_id": operation_id, "owner": "WF00"},
            ) from None
        return KbCall(stage=stage, result=result, body=self._first_body(start))

    def _first_body(self, start: int) -> Mapping[str, Any] | None:
        for record in self._transport.records[start:]:
            if record.body:
                try:
                    parsed = json.loads(record.body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    return None
                return parsed if isinstance(parsed, Mapping) else None
        return None

# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _required(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractViolation("kb_field_missing", detail={"field": name})
    return value


def _parse_job_status(body: Mapping[str, Any]) -> dict[str, Any]:
    data = body.get("data") if isinstance(body.get("data"), Mapping) else {}
    details = data.get("operationDetails") if isinstance(data.get("operationDetails"), Mapping) else {}
    status = details.get("status")
    if not isinstance(status, str) or not status:
        raise ContractViolation("kb_job_status_missing")
    return {
        "status": status,
        "discovered_count": details.get("discoveredUrlsCount"),
        "trained_count": details.get("trainedUrlsCount"),
        "aggregate": data.get("aggregate"),
    }


def _job_state(status: str, *, stage: str) -> str:
    if status in CRAWLER_COMPLETE:
        return "complete"
    if status in CRAWLER_FAILED:
        return "failed"
    if status in CRAWLER_TRAINING:
        return "training"
    if status in CRAWLER_PENDING:
        return "pending" if stage == "crawl" else "processing"
    raise ContractViolation("kb_job_status_unknown", detail={"status": status})


def _job_with(job: IngestionJob, **changes: Any) -> IngestionJob:
    payload = {
        "operation_id": job.operation_id,
        "knowledge_base_id": job.knowledge_base_id,
        "stage": job.stage,
        "state": job.state,
        "vendor_status": job.vendor_status,
        "discovered_count": job.discovered_count,
        "trained_count": job.trained_count,
        "attempts": job.attempts,
        "resumable": job.resumable,
        "detail": job.detail,
    }
    payload.update(changes)
    return IngestionJob(**payload)


def _provider_file_id(body: bytes) -> str | None:
    if not body:
        return None
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(parsed, Mapping):
        return None
    for key in ("fileId", "id", "_id"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value
    data = parsed.get("data")
    if isinstance(data, Mapping):
        for key in ("fileId", "id", "_id"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def readiness_record(
    *,
    location_id: str,
    knowledge_base_id: str,
    agent_id: str | None,
    inventory_verified: bool,
    source_count: int,
    crawl_state: str,
    upload_state: str,
    ingestion_state: str,
    training_state: str,
    attachment_state: str,
    retrieval_state: str,
    evidence: Mapping[str, Any] | None = None,
) -> KbReadiness:
    """Assemble the honest readiness record; distinct fields never collapse."""

    return KbReadiness(
        location_id=str(location_id),
        knowledge_base_id=str(knowledge_base_id),
        agent_id=None if agent_id is None else str(agent_id),
        inventory_verified=bool(inventory_verified),
        source_count=int(source_count),
        crawl_state=str(crawl_state),
        upload_state=str(upload_state),
        ingestion_state=str(ingestion_state),
        training_state=str(training_state),
        attachment_state=str(attachment_state),
        retrieval_state=str(retrieval_state),
        evidence=dict(evidence or {}),
    )


__all__ = [
    "OPERATION_IDS",
    "KB_PER_LOCATION_LIMIT",
    "KB_FILE_MAX_BYTES",
    "KB_FILE_TYPES",
    "KB_FILE_MAGIC",
    "CRAWLER_OPTIONS",
    "CRAWLER_PENDING",
    "CRAWLER_TRAINING",
    "CRAWLER_COMPLETE",
    "CRAWLER_FAILED",
    "REQUIRED_RETRIEVAL_KINDS",
    "KnowledgeBaseGap",
    "KnowledgeBaseRefusal",
    "KnowledgeBaseSummary",
    "KnowledgeBaseInventory",
    "CapacityDecision",
    "SourceDocument",
    "SourcePolicy",
    "SourceUpdatePlan",
    "RemovalImpact",
    "IngestionJob",
    "MultipartUploadRequest",
    "MultipartResponse",
    "MultipartTransport",
    "UploadAcceptance",
    "KbCall",
    "AgentKnowledgeState",
    "AttachmentOutcome",
    "RetrievalCase",
    "RetrievalAnswer",
    "RetrievalCaseResult",
    "RetrievalReport",
    "KbReadiness",
    "KnowledgeBaseClient",
    "parse_inventory",
    "choose_knowledge_base",
    "check_url_source",
    "validate_file_source",
    "revalidate_file_source",
    "check_source_owner",
    "plan_source_updates",
    "plan_source_removal",
    "evaluate_retrieval",
    "readiness_record",
]
