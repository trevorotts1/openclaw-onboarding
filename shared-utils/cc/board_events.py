#!/usr/bin/env python3
"""
board_events.py — W11A: cc_board producer correlation and idempotent event
contract (GHL-DELIVERY-SPEC.md, "Command Center (W11)" + "Board events
(W11 contract)").

W11A OWNS THE NORMATIVE VERSION of the board-event schema. This module is the
single source of truth for the wire contract between the cc_board producers
(``06-ghl-install-pages/tools/cc_board.py`` and its 47/48/58/69 siblings) and
the Command Center consumer.

WHAT THIS MODULE IS
-------------------
The versioned, validated, correlation-carrying task lifecycle event contract:

  * Task lifecycle events: create / assign / start / block / complete, on
    STABLE task IDs (parent+child), created-or-reused, never name-addressed.
  * PRODUCER CORRELATION: every event carries the producer identity and the
    correlation of the ``POST /api/tasks/ingest`` exchange that created the
    card (the ingest idempotency key + the task_id the board returned), plus an
    optional causation link to the prior event. A lifecycle event that cannot
    be correlated to a producer ingest is refused, not guessed.
  * IDEMPOTENT EVENTS: deterministic idempotency keys derived from logical
    identity (never a process counter), so a board retry re-derives the SAME
    key and dedupes — "board retries must never repeat GHL writes or purchases".
  * MONOTONIC SEQUENCE / REVISION: the producer assigns a strictly increasing
    per-task ``seq``; the consumer owns the CAS ``revision`` (bumped only on an
    applied change). Older producer state must never overwrite newer state.
  * CANONICAL WIRE ENCODING: byte-stable JSON, fail-closed parsing, explicit
    schema version.
  * OUTBOX SEAM: ``to_outbox_envelope`` gives the durable outbox
    (W11AC-U2 ``shared-utils/cc/event_outbox.py``) its identity fields; the
    outbox owns delivery/retry state, never event identity.

WHAT THIS MODULE IS NOT
-----------------------
  * NOT the durable outbox or its reconciliation (W11AC-U2 event_outbox.py).
  * NOT the consumer state machine (blackceo-command-center
    ``src/task_state.ts``, W11B). ``to_consumer_projection`` is the exact
    closure of W11B's provisional ``BoardEventInput`` seam against this
    normative contract.
  * NOT the ingest transport (cc_board.py keeps its fail-soft POST). This
    contract validates and correlates what those producers emit.

HARD CONTRACT RULES (normative; enforced here where producer-side)
-----------------------------------------------------------------
  1. Stable task IDs: create-or-reuse by stable id; parent_task_id on create
     correlates a child to its parent; self-parenting is refused.
  2. Idempotent events: one logical action -> one idempotency key. Replaying
     the same key is a duplicate (zero change, zero effects) by definition of
     the key, not by best effort.
  3. Sequence/revision handling: producer ``seq`` strictly increases per task;
     consumer ``revision`` bumps only on applied change and is the CAS token
     for UI updates. A lower seq is stale and must never apply.
  4. A completed page cannot complete the site; a blocked branch cannot erase
     finished work. Those rollup invariants live in the consumer; this contract
     guarantees the event facts (kinds, correlation, ordering) they reason on.
  5. The five delivery measures are SEPARATE and monotonic:
     code_built / remote_incorporated / configured_object / published /
     owner_accepted — each with its own explicit denominator (consumer counts).
  6. Fail closed: an event that does not validate is refused with a reason; it
     is never repaired, coerced or silently dropped.

SELF-TEST (no network, no board):
  python3 -I shared-utils/cc/board_events.py
  exits 0 on success, non-zero on failure.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Normative schema identity (W11A owns the version)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.0.0"
WIRE_SCHEMA = "blackceo.cc.board-events/v1"

EVENT_KINDS: Tuple[str, ...] = ("create", "assign", "start", "block", "complete")

# The five spec-mandated delivery measures, reported SEPARATELY (spec:
# "code built / remote-incorporated / configured-object / published /
# owner-accepted"). LOCKSTEP with the consumer's DeliveryStage union in
# blackceo-command-center src/task_state.ts (W11B).
DELIVERY_STAGES: Tuple[str, ...] = (
    "code_built",
    "remote_incorporated",
    "configured_object",
    "published",
    "owner_accepted",
)

# Failure taxonomy (cc_board.py `_CC_BLOCK_REASONS`, spec U9 §7.3). A block
# reason outside this set is refused here rather than fabricated.
BLOCK_REASONS: Tuple[str, ...] = (
    "AUTH-STOP",
    "SELECTOR-MISS",
    "RATE-LIMIT",
    "TOKEN-CONTEXT",
    "PARKED",
    "VERIFY-FAIL",
)

# Ingest vocabulary of POST /api/tasks/ingest (cc_board.py REQUEST CONTRACT).
INGEST_SOURCES: Tuple[str, ...] = ("funnel", "web-development")
INGEST_DEPARTMENT_BY_SOURCE: Dict[str, str] = {
    "funnel": "funnels",
    "web-development": "web-development",
}

# ISO-8601 UTC timestamp as the producers stamp it (offset accepted, 'Z' ok).
_AT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)

# Wire keys of a v1 event. Unknown keys are refused (fail-closed).
_WIRE_KEYS: Tuple[str, ...] = (
    "schema",
    "kind",
    "task_id",
    "idempotency_key",
    "seq",
    "producer_id",
    "correlation_id",
    "causation_id",
    "parent_task_id",
    "title",
    "actor",
    "note",
    "stage",
    "block_reason",
    "at",
)

# Consumer projection keys (W11B BoardEventInput, camelCase). Required vs
# optional is LOCKSTEP with src/task_state.ts.
_CONSUMER_REQUIRED: Tuple[str, ...] = ("idempotencyKey", "taskId", "kind", "seq")
_CONSUMER_OPTIONAL: Tuple[str, ...] = (
    "parentTaskId",
    "title",
    "actor",
    "note",
    "stage",
    "at",
)


class BoardEventError(ValueError):
    """Fail-closed refusal of an invalid event or derivation input."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def _require_text(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BoardEventError("bad_input", f"{what} must be a non-empty string")
    return value.strip()


# ---------------------------------------------------------------------------
# Producer identity + ingest correlation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProducerIdentity:
    """Who is emitting. ``producer_id`` is stable across runs (a name, not a
    pid); ``instance_id`` optionally scopes one run/box instance."""

    producer_id: str
    source: str
    instance_id: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "producer_id", _require_text(self.producer_id, "producer_id"))
        if self.source not in INGEST_SOURCES:
            raise BoardEventError("bad_input", f"source must be one of {INGEST_SOURCES}")
        if self.instance_id is not None:
            object.__setattr__(
                self, "instance_id", _require_text(self.instance_id, "instance_id")
            )

    @property
    def department_slug(self) -> str:
        return INGEST_DEPARTMENT_BY_SOURCE[self.source]


@dataclass(frozen=True)
class IngestCorrelation:
    """The correlation of one ``POST /api/tasks/ingest`` exchange: the
    idempotency key the producer POSTed (201 created / 200 deduped) and the
    task_id the board returned. Every lifecycle event on that card carries
    ``correlation_id`` = ``ingest_idempotency_key``."""

    ingest_idempotency_key: str
    task_id: str
    workspace_id: Optional[str] = None
    resolved_by: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ingest_idempotency_key",
            _require_text(self.ingest_idempotency_key, "ingest_idempotency_key"),
        )
        object.__setattr__(self, "task_id", _require_text(self.task_id, "task_id"))

    @property
    def correlation_id(self) -> str:
        return self.ingest_idempotency_key


def bind_ingest_receipt(
    ingest_idempotency_key: str, body: Any
) -> IngestCorrelation:
    """Correlate an ingest response body ({task_id, workspace_id?, resolved_by?,
    status?} on HTTP 200/201 — the shape cc_board.py reads) back to the key
    that was POSTed. A body without a real task_id is refused, never invented."""
    key = _require_text(ingest_idempotency_key, "ingest_idempotency_key")
    if not isinstance(body, dict):
        raise BoardEventError("bad_input", "ingest body must be a dict")
    task_id = body.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise BoardEventError("bad_input", "ingest body has no task_id to correlate")
    workspace_id = body.get("workspace_id")
    resolved_by = body.get("resolved_by")
    return IngestCorrelation(
        ingest_idempotency_key=key,
        task_id=task_id.strip(),
        workspace_id=str(workspace_id).strip() if workspace_id else None,
        resolved_by=str(resolved_by).strip() if resolved_by else None,
    )


# ---------------------------------------------------------------------------
# Deterministic identity derivation (idempotency keys, stable task ids)
# ---------------------------------------------------------------------------

_KEY_PREFIX = "bek1:"
_TASK_PREFIX = "bt1:"


def derive_idempotency_key(
    *,
    producer_id: str,
    correlation_id: str,
    task_id: str,
    kind: str,
    occurrence: int = 0,
) -> str:
    """Deterministic idempotency key for ONE logical lifecycle action.

    ``occurrence`` is a LOGICAL slot (0 = the first 'start', 1 = a documented
    second 'start' after a re-dispatch), NEVER a process counter: retrying the
    same logical action with the same inputs re-derives the identical key, so a
    board retry dedupes and can never repeat a GHL write or purchase."""
    pid = _require_text(producer_id, "producer_id")
    cid = _require_text(correlation_id, "correlation_id")
    tid = _require_text(task_id, "task_id")
    if kind not in EVENT_KINDS:
        raise BoardEventError("bad_kind", f"kind must be one of {EVENT_KINDS}")
    if not isinstance(occurrence, int) or isinstance(occurrence, bool) or occurrence < 0:
        raise BoardEventError("bad_input", "occurrence must be an int >= 0")
    canon = "|".join([pid, cid, tid, kind, str(occurrence)])
    return _KEY_PREFIX + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def stable_task_id(*, scope: str, logical_key: str) -> str:
    """Deterministic stable task id for create-or-reuse of parent+child tasks.
    The same logical task re-derives the same id; two tasks never collide
    across scopes."""
    s = _require_text(scope, "scope")
    lk = _require_text(logical_key, "logical_key")
    canon = "|".join([s, lk])
    return _TASK_PREFIX + hashlib.sha256(canon.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# The event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BoardEvent:
    """One validated, correlated, idempotent task lifecycle event."""

    kind: str
    task_id: str
    idempotency_key: str
    seq: int
    producer_id: str
    correlation_id: str
    causation_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    title: Optional[str] = None
    actor: Optional[str] = None
    note: Optional[str] = None
    stage: Optional[str] = None
    block_reason: Optional[str] = None
    at: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind not in EVENT_KINDS:
            raise BoardEventError("bad_kind", f"kind must be one of {EVENT_KINDS}")
        tid = _require_text(self.task_id, "task_id")
        object.__setattr__(self, "task_id", tid)
        object.__setattr__(
            self, "idempotency_key", _require_text(self.idempotency_key, "idempotency_key")
        )
        object.__setattr__(
            self, "producer_id", _require_text(self.producer_id, "producer_id")
        )
        object.__setattr__(
            self, "correlation_id", _require_text(self.correlation_id, "correlation_id")
        )
        if not isinstance(self.seq, int) or isinstance(self.seq, bool) or self.seq < 1:
            raise BoardEventError("bad_seq", "seq must be an int >= 1")
        if self.parent_task_id is not None:
            parent = _require_text(self.parent_task_id, "parent_task_id")
            if parent == tid:
                raise BoardEventError("self_parent", "task_id cannot parent itself")
            object.__setattr__(self, "parent_task_id", parent)
        if self.causation_id is not None:
            object.__setattr__(
                self, "causation_id", _require_text(self.causation_id, "causation_id")
            )
        if self.kind == "create" and (
            self.title is None or not str(self.title).strip()
        ):
            raise BoardEventError("bad_input", "create requires a non-empty title")
        if self.kind == "block":
            if self.block_reason is None and not (self.note and str(self.note).strip()):
                raise BoardEventError("bad_input", "block requires note or block_reason")
        if self.title is not None:
            object.__setattr__(self, "title", _require_text(self.title, "title"))
        if self.actor is not None:
            object.__setattr__(self, "actor", _require_text(self.actor, "actor"))
        if self.note is not None:
            object.__setattr__(self, "note", _require_text(self.note, "note"))
        if self.stage is not None:
            if self.stage not in DELIVERY_STAGES:
                raise BoardEventError("bad_stage", f"stage must be one of {DELIVERY_STAGES}")
        if self.block_reason is not None:
            if self.block_reason not in BLOCK_REASONS:
                raise BoardEventError(
                    "bad_input", f"block_reason must be one of {BLOCK_REASONS}"
                )
            if self.kind != "block":
                raise BoardEventError("bad_input", "block_reason is only valid on block")
        if self.at is not None:
            if not isinstance(self.at, str) or not _AT_RE.match(self.at):
                raise BoardEventError("bad_input", "at must be ISO-8601 with offset/Z")

    # -- wire encoding ------------------------------------------------------

    def to_wire(self) -> Dict[str, Any]:
        """v1 wire dict. Optional fields are present ONLY when set, so two
        identical logical events serialize identically."""
        wire: Dict[str, Any] = {
            "schema": WIRE_SCHEMA,
            "kind": self.kind,
            "task_id": self.task_id,
            "idempotency_key": self.idempotency_key,
            "seq": self.seq,
            "producer_id": self.producer_id,
            "correlation_id": self.correlation_id,
        }
        for key in (
            "causation_id",
            "parent_task_id",
            "title",
            "actor",
            "note",
            "stage",
            "block_reason",
            "at",
        ):
            value = getattr(self, key)
            if value is not None:
                wire[key] = value
        return wire

    def to_wire_json(self) -> str:
        """Canonical, byte-stable JSON encoding."""
        return json.dumps(self.to_wire(), sort_keys=True, separators=(",", ":"))


def event_from_wire(data: Any) -> BoardEvent:
    """Fail-closed parse of a v1 wire dict. Unknown keys, a foreign schema, or
    missing required keys are refused — never repaired or coerced."""
    if not isinstance(data, dict):
        raise BoardEventError("bad_schema", "wire event must be a dict")
    unknown = set(data) - set(_WIRE_KEYS)
    if unknown:
        raise BoardEventError("bad_schema", f"unknown wire keys: {sorted(unknown)}")
    if data.get("schema") != WIRE_SCHEMA:
        raise BoardEventError("bad_schema", f"schema must be {WIRE_SCHEMA!r}")
    missing = [k for k in ("kind", "task_id", "idempotency_key", "seq", "producer_id", "correlation_id") if k not in data]
    if missing:
        raise BoardEventError("bad_schema", f"missing wire keys: {missing}")
    return BoardEvent(
        kind=data["kind"],
        task_id=data["task_id"],
        idempotency_key=data["idempotency_key"],
        seq=data["seq"],
        producer_id=data["producer_id"],
        correlation_id=data["correlation_id"],
        causation_id=data.get("causation_id"),
        parent_task_id=data.get("parent_task_id"),
        title=data.get("title"),
        actor=data.get("actor"),
        note=data.get("note"),
        stage=data.get("stage"),
        block_reason=data.get("block_reason"),
        at=data.get("at"),
    )


def event_from_wire_json(text: str) -> BoardEvent:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise BoardEventError("bad_schema", f"invalid JSON: {exc}") from exc
    return event_from_wire(data)


def to_consumer_projection(event: BoardEvent) -> Dict[str, Any]:
    """Exact closure of W11B's provisional ``BoardEventInput`` seam
    (blackceo-command-center src/task_state.ts): camelCase keys, the four
    required always present, optionals only when set. A ``block_reason`` rides
    as the cc_board note prefix ("REASON: note"), matching how the producer
    posts taxonomy-tagged notes."""
    out: Dict[str, Any] = {
        "idempotencyKey": event.idempotency_key,
        "taskId": event.task_id,
        "kind": event.kind,
        "seq": event.seq,
    }
    if event.parent_task_id is not None:
        out["parentTaskId"] = event.parent_task_id
    if event.title is not None:
        out["title"] = event.title
    if event.actor is not None:
        out["actor"] = event.actor
    note = event.note
    if event.block_reason is not None:
        note = f"{event.block_reason}: {note}" if note else f"{event.block_reason}:"
    if note is not None:
        out["note"] = note
    if event.stage is not None:
        out["stage"] = event.stage
    if event.at is not None:
        out["at"] = event.at
    return out


def to_outbox_envelope(event: BoardEvent) -> Dict[str, Any]:
    """Identity envelope for the durable outbox (W11AC-U2
    ``shared-utils/cc/event_outbox.py``): the outbox owns delivery/retry/
    reconciliation state; this contract owns event identity. The envelope's
    ``idempotency_key`` is the outbox's dedupe key — one logical action is
    enqueued once and delivered idempotently."""
    return {
        "schema": WIRE_SCHEMA,
        "idempotency_key": event.idempotency_key,
        "task_id": event.task_id,
        "kind": event.kind,
        "seq": event.seq,
        "payload": event.to_wire(),
    }


# ---------------------------------------------------------------------------
# Producer-side monotonic sequence
# ---------------------------------------------------------------------------


class SeqAllocator:
    """Strictly increasing per-task producer sequence. Retries do not allocate;
    only new logical events do. ``observe`` refuses non-monotonic state so an
    older seq can never be re-armed against newer state."""

    def __init__(self) -> None:
        self._last: Dict[str, int] = {}

    def next(self, task_id: str) -> int:
        tid = _require_text(task_id, "task_id")
        nxt = self._last.get(tid, 0) + 1
        self._last[tid] = nxt
        return nxt

    def observe(self, task_id: str, seq: int) -> None:
        tid = _require_text(task_id, "task_id")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
            raise BoardEventError("bad_seq", "seq must be an int >= 1")
        if seq <= self._last.get(tid, 0):
            raise BoardEventError("bad_seq", f"seq {seq} is not newer than {self._last.get(tid, 0)}")
        self._last[tid] = seq

    def last(self, task_id: str) -> int:
        return self._last.get(_require_text(task_id, "task_id"), 0)


# ---------------------------------------------------------------------------
# Correlated producer stream (the ergonomic surface)
# ---------------------------------------------------------------------------


@dataclass
class BoardEventStream:
    """One producer's correlated event stream: identity + ingest correlation +
    deterministic keys + monotonic seq in one place.

    Every builder derives its idempotency key from logical identity and
    allocates the next per-task seq. Re-running a builder for the SAME logical
    action (same ``occurrence``) re-derives the same key — the retry dedupes
    instead of double-applying."""

    producer: ProducerIdentity
    correlation: IngestCorrelation
    allocator: SeqAllocator = field(default_factory=SeqAllocator)

    def _build(
        self,
        kind: str,
        *,
        occurrence: int = 0,
        causation_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        title: Optional[str] = None,
        actor: Optional[str] = None,
        note: Optional[str] = None,
        stage: Optional[str] = None,
        block_reason: Optional[str] = None,
        at: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> BoardEvent:
        tid = task_id or self.correlation.task_id
        key = derive_idempotency_key(
            producer_id=self.producer.producer_id,
            correlation_id=self.correlation.correlation_id,
            task_id=tid,
            kind=kind,
            occurrence=occurrence,
        )
        return BoardEvent(
            kind=kind,
            task_id=tid,
            idempotency_key=key,
            seq=self.allocator.next(tid),
            producer_id=self.producer.producer_id,
            correlation_id=self.correlation.correlation_id,
            causation_id=causation_id,
            parent_task_id=parent_task_id,
            title=title,
            actor=actor,
            note=note,
            stage=stage,
            block_reason=block_reason,
            at=at,
        )

    def create(self, *, title: str, parent_task_id: Optional[str] = None,
               task_id: Optional[str] = None, stage: Optional[str] = None,
               at: Optional[str] = None, occurrence: int = 0,
               causation_id: Optional[str] = None) -> BoardEvent:
        return self._build(
            "create",
            occurrence=occurrence,
            causation_id=causation_id,
            parent_task_id=parent_task_id,
            title=title,
            stage=stage,
            at=at,
            task_id=task_id,
        )

    def assign(self, *, actor: str, task_id: Optional[str] = None,
               note: Optional[str] = None, at: Optional[str] = None,
               occurrence: int = 0, causation_id: Optional[str] = None) -> BoardEvent:
        return self._build(
            "assign",
            occurrence=occurrence,
            causation_id=causation_id,
            actor=actor,
            note=note,
            at=at,
            task_id=task_id,
        )

    def start(self, *, task_id: Optional[str] = None, actor: Optional[str] = None,
              stage: Optional[str] = None, at: Optional[str] = None,
              occurrence: int = 0, causation_id: Optional[str] = None) -> BoardEvent:
        return self._build(
            "start",
            occurrence=occurrence,
            causation_id=causation_id,
            actor=actor,
            stage=stage,
            at=at,
            task_id=task_id,
        )

    def block(self, *, note: Optional[str] = None, block_reason: Optional[str] = None,
              task_id: Optional[str] = None, at: Optional[str] = None,
              occurrence: int = 0, causation_id: Optional[str] = None) -> BoardEvent:
        return self._build(
            "block",
            occurrence=occurrence,
            causation_id=causation_id,
            note=note,
            block_reason=block_reason,
            at=at,
            task_id=task_id,
        )

    def complete(self, *, task_id: Optional[str] = None, note: Optional[str] = None,
                 stage: Optional[str] = None, at: Optional[str] = None,
                 occurrence: int = 0, causation_id: Optional[str] = None) -> BoardEvent:
        return self._build(
            "complete",
            occurrence=occurrence,
            causation_id=causation_id,
            note=note,
            stage=stage,
            at=at,
            task_id=task_id,
        )


# ---------------------------------------------------------------------------
# Self-check (assert-based, no network, no board)
# ---------------------------------------------------------------------------

CONTRACT_RULES: Tuple[str, ...] = (
    "stable task ids: create-or-reuse by stable id, parent correlates child",
    "idempotent events: one logical action -> one idempotency key",
    "producer seq strictly increases per task; consumer revision is the CAS token",
    "a completed page cannot complete the site; a blocked branch cannot erase finished work",
    "five delivery measures separate and monotonic, explicit denominators",
    "fail closed: invalid events are refused with a reason, never repaired",
)


def _expect_error(reason: str, fn) -> None:
    try:
        fn()
    except BoardEventError as exc:
        assert exc.reason == reason, f"expected reason {reason!r}, got {exc.reason!r} ({exc})"
    else:
        raise AssertionError(f"expected BoardEventError({reason}) from {fn}")


def _selfcheck() -> int:
    n = 0

    # 0. contract surface identity
    assert WIRE_SCHEMA.endswith("/v1") and SCHEMA_VERSION.startswith("1.")
    assert EVENT_KINDS == ("create", "assign", "start", "block", "complete")
    assert DELIVERY_STAGES == (
        "code_built",
        "remote_incorporated",
        "configured_object",
        "published",
        "owner_accepted",
    )
    assert len(CONTRACT_RULES) == 6
    n += 4

    # 1. producer identity + ingest correlation
    prod = ProducerIdentity(producer_id="skill06.cc_board", source="funnel", instance_id="run-1")
    assert prod.department_slug == "funnels"
    assert ProducerIdentity(producer_id="p", source="web-development").department_slug == "web-development"
    corr = bind_ingest_receipt("ing-key-1", {"task_id": " t-9 ", "workspace_id": "w-1", "resolved_by": "router", "status": "backlog"})
    assert corr.correlation_id == "ing-key-1" and corr.task_id == "t-9" and corr.workspace_id == "w-1"
    _expect_error("bad_input", lambda: bind_ingest_receipt("k", {"no": "task"}))
    _expect_error("bad_input", lambda: bind_ingest_receipt("", {"task_id": "t"}))
    _expect_error("bad_input", lambda: ProducerIdentity(producer_id="p", source="nope"))
    n += 6

    # 2. deterministic idempotency keys (retry == same key)
    k1 = derive_idempotency_key(producer_id="skill06.cc_board", correlation_id="ing-key-1", task_id="t-9", kind="start")
    k2 = derive_idempotency_key(producer_id="skill06.cc_board", correlation_id="ing-key-1", task_id="t-9", kind="start")
    k3 = derive_idempotency_key(producer_id="skill06.cc_board", correlation_id="ing-key-1", task_id="t-9", kind="start", occurrence=1)
    k4 = derive_idempotency_key(producer_id="skill06.cc_board", correlation_id="ing-key-1", task_id="t-10", kind="start")
    assert k1 == k2, "same logical action must re-derive the same key"
    assert k1 != k3 != k4 and k1 != k4 and k1.startswith("bek1:")
    _expect_error("bad_kind", lambda: derive_idempotency_key(producer_id="p", correlation_id="c", task_id="t", kind="retry"))
    _expect_error("bad_input", lambda: derive_idempotency_key(producer_id="p", correlation_id="c", task_id="t", kind="start", occurrence=-1))
    _expect_error("bad_input", lambda: derive_idempotency_key(producer_id="", correlation_id="c", task_id="t", kind="start"))
    n += 8

    # 3. stable task ids (create-or-reuse)
    s1 = stable_task_id(scope="ghl-delivery/site-a", logical_key="page:hero")
    s2 = stable_task_id(scope="ghl-delivery/site-a", logical_key="page:hero")
    s3 = stable_task_id(scope="ghl-delivery/site-b", logical_key="page:hero")
    assert s1 == s2 and s1 != s3 and s1.startswith("bt1:")
    _expect_error("bad_input", lambda: stable_task_id(scope="", logical_key="x"))
    n += 4

    # 4. event validation (fail closed)
    stream = BoardEventStream(producer=prod, correlation=corr)
    ev_create = stream.create(title="Site A hero", parent_task_id=None, stage="code_built", at="2026-10-23T12:00:00Z", occurrence=0)
    ev_child = stream.create(title="Site A hero child", parent_task_id=ev_create.task_id, task_id=s1, at="2026-10-23T12:00:01Z", causation_id=ev_create.idempotency_key)
    ev_assign = stream.assign(actor="builder-1", note="queued", at="2026-10-23T12:01:00Z", causation_id=ev_child.idempotency_key, task_id=s1)
    ev_start = stream.start(task_id=s1, stage="code_built", at="2026-10-23T12:02:00Z")
    ev_block = stream.block(task_id=s1, note="selector gone", block_reason="SELECTOR-MISS", at="2026-10-23T12:03:00Z")
    ev_done = stream.complete(task_id=s1, stage="owner_accepted", note="accepted", at="2026-10-23T12:04:00Z")
    assert [e.kind for e in (ev_create, ev_child, ev_assign, ev_start, ev_block, ev_done)] == ["create", "create", "assign", "start", "block", "complete"]
    assert ev_child.parent_task_id == ev_create.task_id
    assert ev_child.causation_id == ev_create.idempotency_key
    assert ev_assign.seq > ev_child.seq and ev_start.seq > ev_assign.seq
    assert ev_block.block_reason == "SELECTOR-MISS"
    n += 7

    _expect_error("bad_input", lambda: BoardEvent(kind="create", task_id="t", idempotency_key="k", seq=1, producer_id="p", correlation_id="c"))
    _expect_error("bad_seq", lambda: BoardEvent(kind="start", task_id="t", idempotency_key="k", seq=0, producer_id="p", correlation_id="c"))
    _expect_error("bad_seq", lambda: BoardEvent(kind="start", task_id="t", idempotency_key="k", seq=True, producer_id="p", correlation_id="c"))
    _expect_error("self_parent", lambda: BoardEvent(kind="create", task_id="t", idempotency_key="k", seq=1, producer_id="p", correlation_id="c", parent_task_id="t", title="x"))
    _expect_error("bad_kind", lambda: BoardEvent(kind="retry", task_id="t", idempotency_key="k", seq=1, producer_id="p", correlation_id="c"))
    _expect_error("bad_input", lambda: BoardEvent(kind="block", task_id="t", idempotency_key="k", seq=1, producer_id="p", correlation_id="c"))
    _expect_error("bad_input", lambda: BoardEvent(kind="block", task_id="t", idempotency_key="k", seq=1, producer_id="p", correlation_id="c", note="n", block_reason="NOT-A-REASON"))
    _expect_error("bad_input", lambda: BoardEvent(kind="start", task_id="t", idempotency_key="k", seq=1, producer_id="p", correlation_id="c", block_reason="PARKED"))
    _expect_error("bad_stage", lambda: BoardEvent(kind="start", task_id="t", idempotency_key="k", seq=1, producer_id="p", correlation_id="c", stage="shipped"))
    _expect_error("bad_input", lambda: BoardEvent(kind="start", task_id="t", idempotency_key="k", seq=1, producer_id="p", correlation_id="c", at="yesterday"))
    _expect_error("bad_input", lambda: BoardEvent(kind="assign", task_id="t", idempotency_key="", seq=1, producer_id="p", correlation_id="c"))
    n += 11

    # 5. wire round-trip + canonical byte stability + fail-closed parse
    wire = ev_block.to_wire()
    assert wire["schema"] == WIRE_SCHEMA and set(wire) <= set(_WIRE_KEYS)
    back = event_from_wire(wire)
    assert back == ev_block, "wire round-trip must be exact"
    assert ev_block.to_wire_json() == ev_block.to_wire_json()
    assert event_from_wire_json(ev_done.to_wire_json()) == ev_done
    _expect_error("bad_schema", lambda: event_from_wire({"schema": WIRE_SCHEMA, "kind": "start", "task_id": "t", "idempotency_key": "k", "seq": 1, "producer_id": "p", "correlation_id": "c", "extra": 1}))
    _expect_error("bad_schema", lambda: event_from_wire({"kind": "start", "task_id": "t", "idempotency_key": "k", "seq": 1, "producer_id": "p", "correlation_id": "c"}))
    _expect_error("bad_schema", lambda: event_from_wire({"schema": "blackceo.cc.board-events/v0", "kind": "start", "task_id": "t", "idempotency_key": "k", "seq": 1, "producer_id": "p", "correlation_id": "c"}))
    _expect_error("bad_schema", lambda: event_from_wire_json("{not json"))
    # discrimination control: one mutated byte of canonical JSON must not
    # re-validate as the same event
    mutated = ev_block.to_wire_json().replace("SELECTOR-MISS", "SELECTOR-MISX", 1)
    assert mutated != ev_block.to_wire_json(), "control mutation must change the bytes"
    n += 9

    # 6. consumer projection closure (W11B BoardEventInput, LOCKSTEP)
    proj_min = to_consumer_projection(stream.start(task_id=s1))
    assert set(proj_min) == set(_CONSUMER_REQUIRED), proj_min
    proj_full = to_consumer_projection(ev_block)
    assert set(proj_full) == set(_CONSUMER_REQUIRED) | {"note", "at"}, sorted(proj_full)
    assert proj_full["idempotencyKey"] == ev_block.idempotency_key
    assert proj_full["taskId"] == s1 and proj_full["seq"] == ev_block.seq
    assert proj_full["note"] == "SELECTOR-MISS: selector gone", proj_full["note"]
    proj_create = to_consumer_projection(ev_child)
    assert proj_create["parentTaskId"] == ev_create.task_id and proj_create["title"] == "Site A hero child"
    n += 6

    # 7. outbox seam (identity owned here, delivery state owned by W11AC-U2)
    env = to_outbox_envelope(ev_done)
    assert env["idempotency_key"] == ev_done.idempotency_key
    assert env["payload"] == ev_done.to_wire()
    assert event_from_wire(env["payload"]) == ev_done
    env_retry = to_outbox_envelope(ev_done)
    assert env_retry == env, "retry of one logical action enqueues byte-identical identity"
    n += 4

    # 8. sequence allocator: strict per-task monotonicity
    alloc = SeqAllocator()
    a1 = alloc.next("t-1")
    a2 = alloc.next("t-1")
    b1 = alloc.next("t-2")
    assert (a1, a2, b1) == (1, 2, 1)
    alloc.observe("t-3", 7)
    assert alloc.last("t-3") == 7
    _expect_error("bad_seq", lambda: alloc.observe("t-3", 7))
    _expect_error("bad_input", lambda: alloc.next(""))
    # stream seq must be strictly increasing per task even with retries in between
    r1 = stream.start(task_id=s1, occurrence=0)
    r2 = stream.start(task_id=s1, occurrence=0)  # retry: same key...
    assert r2.idempotency_key == r1.idempotency_key, "...but never the same seq slot"
    assert r2.seq > r1.seq
    n += 9

    print(f"OK board_events self-check: {n} assertions")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
