#!/usr/bin/env python3
"""GHL folder/container/page primitive writer (stream W5, assignment W5A-U1).

Sole shared primitive writer for funnel AND website folders, containers and
pages. This module owns the create/reuse/update bindings (identity allocation
first, content second) that the W5 funnel adapter and W5 website adapter
consume. It consumes the REAL W2 operation contracts in this package
(capability_inventory.py, W2A-U1) and never invents an endpoint, payload or
selector:

  * Every operation carries a Capability object taken from
    capability_inventory.OPERATIONS via select_route. The route string is
    always the catalog's own route text -- no hand-authored route.
  * Read/list support never implies create/edit support: route selection is by
    exact op class. Folder create, and website container create, have NO
    verified write route in the inventory; they are reported as
    missing-capability capture requests ("capture the smallest missing
    authorized operation"), never as done, never with a guessed selector or an
    "enabled" flag.
  * Page content writes route to the gated managed browser builders
    (capability browser.page_content; Skill 06 build methods A/B/C: raw-code
    funnel/page, vercel-embed, website page). This in-browser operation is NOT
    a public API. Execution belongs to the gated builder layer (W2 recipe
    transport / W3 browser layer); this module plans, routes, sequences and
    verifies readback.
  * Read the record back after every write (CONTRACTS["readback"]). An
    uncertain outcome is reconciled via the verified read surface BEFORE any
    retry and is never blindly retried (CONTRACTS["uncertain_outcome"]).
    Bounded retries use the catalog's own bounds MAX_429_RETRIES /
    MAX_5XX_RETRIES. Retry pacing/sleeps belong to callers.
  * Administrative folders are NOT navigation hierarchy and NOT nested URL
    paths. Folder placement never derives nav_ref or url_path; those are
    explicit inputs only. Pages may share a role with distinct identity:
    logical_id is identity, role is not. Identity is persisted keyed by
    (location, kind, parent, logical id) -- never by name alone.
  * States PLANNED -> CREATED -> CONFIGURED are driven here. PUBLISHED and
    VERIFIED exist in the delivery contract but the publishing coordinator
    (W7) owns those transitions; this writer refuses them. There is no
    publish/delete/execute operation in this module at all.

Out of scope by ownership: funnel step ordering / accept-decline edges and
website menus (W1 delivery contract + W7), URL/action binding (W7
link_resolution), forms/surveys (W6), commerce (W8), actual transport
execution (W2 object_router / recipe_transport, W3 browser layer).

Runnable check (assert-based self-check, no network):
    python3 shared-utils/ghl/primitives.py
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

if __package__:
    from .capability_inventory import (
        MAX_429_RETRIES,
        MAX_5XX_RETRIES,
        OPERATIONS,
        READ_CLASSES,
        RESTRICTIONS,
        WRITE_CLASSES,
        Capability,
        OpClass,
        Support,
        Transport,
        select_route,
        supports,
        validate_inventory,
    )
else:  # script execution: python3 shared-utils/ghl/primitives.py
    from capability_inventory import (
        MAX_429_RETRIES,
        MAX_5XX_RETRIES,
        OPERATIONS,
        READ_CLASSES,
        RESTRICTIONS,
        WRITE_CLASSES,
        Capability,
        OpClass,
        Support,
        Transport,
        select_route,
        supports,
        validate_inventory,
    )


# --------------------------------------------------------------------------
# Identity and state model
# --------------------------------------------------------------------------


class BuilderType(Enum):
    FUNNEL = "funnel"
    WEBSITE = "website"


class PrimitiveKind(Enum):
    FOLDER = "folder"        # administrative grouping only: never nav, never URL
    CONTAINER = "container"  # a funnel or a website
    PAGE = "page"            # a funnel step/page or a website page


class DeliveryState(Enum):
    PLANNED = "planned"
    CREATED = "created"
    CONFIGURED = "configured"
    PUBLISHED = "published"   # W7 publishing coordinator only
    VERIFIED = "verified"     # W7 readback only


STATE_LADDER: Tuple[DeliveryState, ...] = (
    DeliveryState.PLANNED,
    DeliveryState.CREATED,
    DeliveryState.CONFIGURED,
)
W7_OWNED_STATES = frozenset({DeliveryState.PUBLISHED, DeliveryState.VERIFIED})

# Content keys an approved content package may carry. The writer copies only
# approved keys; it never synthesizes content.
ALLOWED_CONTENT_KEYS = frozenset({"html", "css", "embed", "assets", "native_slots"})
IDENTITY_KEYS = frozenset({"name", "slug"})
# Op classes this writer may emit: create/reuse/update + readback. EXECUTE
# (publish) and DELETE are not primitives here (W7 / explicit owner order).
WRITER_OP_CLASSES = frozenset({OpClass.CREATE, OpClass.EDIT, OpClass.READ, OpClass.LIST})


@dataclass(frozen=True)
class PrimitiveSpec:
    """One requested folder/container/page node.

    logical_id is the stable identity; role is descriptive and may repeat
    across distinct pages. parent_logical_id is ADMINISTRATIVE placement only.
    nav_ref / url_path are explicit inputs; folder placement never derives or
    fills them. parent_native_id names a parent that is NOT part of this spec
    batch (an already-existing container/folder).
    """

    logical_id: str
    kind: PrimitiveKind
    builder_type: BuilderType
    name: str
    slug: str = ""
    parent_logical_id: Optional[str] = None
    parent_native_id: Optional[str] = None
    role: str = ""
    intent: str = ""
    revision: int = 1
    approved_content: Optional[Mapping[str, str]] = None
    nav_ref: Optional[str] = None
    url_path: Optional[str] = None
    native_id_hint: Optional[str] = None  # explicit known native ID => update binding


@dataclass(frozen=True)
class ExistingObject:
    """One object already present on the platform, from a verified read."""

    kind: PrimitiveKind
    name: str
    native_id: str
    builder_type: BuilderType
    slug: str = ""
    parent_native_id: Optional[str] = None


@dataclass
class IdentityRecord:
    """Persisted identity, keyed by (location, kind, parent, logical id) --
    never by name alone."""

    logical_id: str
    kind: PrimitiveKind
    parent_logical_id: Optional[str]
    location: str
    native_id: Optional[str] = None
    state: DeliveryState = DeliveryState.PLANNED
    match_source: str = ""  # "native_id_hint" | "exact_match" | "created" | ""


def advance_state(current: DeliveryState, new: DeliveryState) -> DeliveryState:
    """Distinct states; strict ladder. PUBLISHED/VERIFIED are W7's, refused here."""
    if new in W7_OWNED_STATES:
        raise ValueError(
            f"state {new.value} is owned by the publishing coordinator (W7); "
            "this writer only drives planned/created/configured"
        )
    if new is current:
        return current
    order = {s: i for i, s in enumerate(STATE_LADDER)}
    if order[new] <= order[current]:
        raise ValueError(f"illegal state transition {current.value} -> {new.value}")
    return new


class IdentityLedger:
    """Allocate/reconcile identities first. Names never key a record."""

    def __init__(self) -> None:
        self._by_key: Dict[Tuple[str, str, str, str], IdentityRecord] = {}
        self._by_logical: Dict[str, IdentityRecord] = {}

    @staticmethod
    def _key(rec: IdentityRecord) -> Tuple[str, str, str, str]:
        return (rec.location, rec.kind.value, rec.parent_logical_id or "", rec.logical_id)

    def put(self, rec: IdentityRecord) -> None:
        key = self._key(rec)
        if key in self._by_key:
            raise ValueError(f"identity already recorded for key {key}")
        self._by_key[key] = rec
        self._by_logical[rec.logical_id] = rec

    def get(self, logical_id: str) -> Optional[IdentityRecord]:
        return self._by_logical.get(logical_id)

    def confirm(self, logical_id: str, native_id: str, state: DeliveryState, source: str) -> IdentityRecord:
        rec = self._by_logical[logical_id]
        if rec.native_id and rec.native_id != native_id:
            raise ValueError(
                f"{logical_id}: identity already confirmed as {rec.native_id!r}, "
                f"refusing to overwrite with {native_id!r}"
            )
        rec.native_id = native_id
        rec.state = advance_state(rec.state, state)
        rec.match_source = source
        return rec


# --------------------------------------------------------------------------
# Routing (consumes the real W2A contracts; no route is authored here)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteDecision:
    status: str  # "routed" | "dynamic_candidate" | "missing"
    capability: Optional[Capability]
    capture_request: str = ""  # smallest missing authorized operation to capture
    provenance: str = ""


def _resource_for(kind: PrimitiveKind, builder_type: BuilderType) -> Optional[str]:
    if kind is PrimitiveKind.PAGE:
        return "page"
    if kind is PrimitiveKind.CONTAINER and builder_type is BuilderType.FUNNEL:
        return "funnels"
    return None  # folders, and website containers: no catalog resource


def _surface_for(kind: PrimitiveKind, builder_type: BuilderType) -> str:
    if kind is PrimitiveKind.PAGE:
        return "page"
    return "funnel" if builder_type is BuilderType.FUNNEL else "page"


def _capture_request(kind: PrimitiveKind, builder_type: BuilderType, op_class: OpClass) -> Tuple[str, str]:
    """The smallest missing authorized operation to capture -- never a guessed
    selector or an 'enabled' flag (GHL-DELIVERY-SPEC.md Folders/pages/design)."""
    where = f"{builder_type.value} {kind.value}"
    provenance = (
        "shared-utils/ghl/capability_inventory.py (W2A-U1): no route with "
        f"resource match for {where} {op_class.value}"
    )
    if kind is PrimitiveKind.CONTAINER and builder_type is BuilderType.WEBSITE:
        provenance += "; " + RESTRICTIONS["funnel_page_content_no_public_api"][1]
    request = (
        f"capture the smallest missing authorized operation for {op_class.value} "
        f"of a {where}: one verified documented endpoint, or one captured "
        "gated-builder step with its gate id -- never a guessed selector, "
        "never an 'enabled' flag"
    )
    return request, provenance


def resolve_operation(
    op_class: OpClass,
    *,
    kind: PrimitiveKind,
    builder_type: BuilderType,
    dynamic_confirmed: bool = False,
) -> RouteDecision:
    """Exact-op-class route for one primitive operation.

    Static catalog routes first (the catalog already refuses to route
    READ/LIST to the managed browser), then a DISCOVERABLE dynamic surface
    only when the caller confirmed the true op class at runtime. Otherwise a
    capture request -- a missing capability is reported incomplete, never done.
    """
    resource = _resource_for(kind, builder_type)
    surface = _surface_for(kind, builder_type)
    if resource is None:
        static = []  # this object kind has NO catalog resource: never borrow
        # another resource's route (a folder create is not a calendar booking)
    else:
        static = select_route(op_class, resource=resource, surface=surface, dynamic_confirmed=False)
    if static:
        return RouteDecision("routed", static[0])
    if dynamic_confirmed:
        dynamic = [
            cap
            for cap in select_route(op_class, surface=surface, dynamic_confirmed=True)
            if cap.support is Support.DISCOVERABLE and cap.resource == "dynamic"
        ]
        if dynamic:
            cap = dynamic[0]
            return RouteDecision(
                "dynamic_candidate",
                cap,
                capture_request=(
                    "dynamic surface: confirm the true op class at runtime "
                    f"({cap.resolver}) before use; a read/list confirmation "
                    "never implies create/edit"
                ),
                provenance=cap.provenance,
            )
    request, provenance = _capture_request(kind, builder_type, op_class)
    return RouteDecision("missing", None, capture_request=request, provenance=provenance)


def readback_route(kind: PrimitiveKind, builder_type: BuilderType) -> Optional[Capability]:
    """Verified read surface used to reconcile a write. None => only
    executor-provided readback, and an uncertain result cannot be
    independently reconciled (reported as such, never glossed over)."""
    if builder_type is not BuilderType.FUNNEL:
        return None  # website surfaces: no verified read route in the catalog
    if kind in (PrimitiveKind.PAGE, PrimitiveKind.CONTAINER):
        routes = select_route(OpClass.LIST, resource="funnels", surface="funnel")
        return routes[0] if routes else None
    return None  # folders: no verified read route in the catalog


# --------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PrimitiveOp:
    """One sequenced operation. The capability must be identity-present in
    capability_inventory.OPERATIONS -- a fabricated capability is refused."""

    op_id: str
    action: str  # "create" | "update" | "readback"
    op_class: OpClass
    capability: Capability
    logical_id: str
    kind: PrimitiveKind
    builder_type: BuilderType
    target: Mapping[str, str]  # location/kind/parent/name keys for the receipt
    payload: Mapping[str, str] = field(default_factory=dict)
    readback_required: bool = True


class Outcome(Enum):
    OK = "ok"
    UNCERTAIN = "uncertain"
    REFUSED = "refused"
    RATE_LIMITED = "rate_limited"
    TRANSIENT_ERROR = "transient_error"
    ERROR = "error"


@dataclass(frozen=True)
class OpResult:
    outcome: Outcome
    native_id: str = ""
    readback: Mapping[str, str] = field(default_factory=dict)
    note: str = ""


class Executor(Protocol):
    """Transport seam owned by W2/W3 adapters. run() executes exactly one op."""

    def run(self, op: PrimitiveOp) -> OpResult: ...


def validate_op(op: PrimitiveOp) -> None:
    """Refuse fabricated capabilities, mis-matched op classes, invented
    payloads and publish/delete masquerading as primitives."""
    if op.op_class not in WRITER_OP_CLASSES:
        raise ValueError(f"op {op.op_id}: {op.op_class.value} is not a primitive write/read here")
    if not any(cap is op.capability for cap in OPERATIONS):
        raise ValueError(
            f"op {op.op_id}: capability {op.capability.capability_id!r} is not "
            "identity-present in capability_inventory.OPERATIONS (no invented routes)"
        )
    if not supports(op.capability, op.op_class):
        raise ValueError(
            f"op {op.op_id}: {op.capability.capability_id} does not carry "
            f"{op.op_class.value} (read/list never implies create/edit)"
        )
    if op.op_class in READ_CLASSES and op.capability.transport is Transport.MANAGED_BROWSER:
        raise ValueError(f"op {op.op_id}: read/list must never route to the managed browser")
    if op.op_class in WRITE_CLASSES and not op.readback_required:
        raise ValueError(f"op {op.op_id}: writes require readback (CONTRACTS['readback'])")
    if op.action == "create":
        extra = set(op.payload) - IDENTITY_KEYS
        if extra:
            raise ValueError(f"op {op.op_id}: create payload carries non-identity keys {sorted(extra)}")
    elif op.action == "update":
        extra = set(op.payload) - ALLOWED_CONTENT_KEYS
        if extra:
            raise ValueError(f"op {op.op_id}: update payload carries non-content keys {sorted(extra)}")
    for forbidden in ("nav_ref", "url_path"):
        if forbidden in op.payload or forbidden in op.target:
            raise ValueError(
                f"op {op.op_id}: {forbidden} is explicit input only -- never "
                "derived from administrative folder placement"
            )


# --------------------------------------------------------------------------
# Validation and planning
# --------------------------------------------------------------------------


class Disposition(Enum):
    REUSE = "reuse"
    CREATE = "create"
    AMBIGUOUS = "ambiguous"
    MISSING_CAPABILITY = "missing_capability"
    BLOCKED_PARENT = "blocked_parent"


@dataclass(frozen=True)
class Allocation:
    logical_id: str
    disposition: Disposition
    native_id: str = ""
    match_source: str = ""
    reason: str = ""
    capture_request: str = ""
    provenance: str = ""


@dataclass
class BuildPlan:
    location: str
    allocations: List[Allocation]
    ops: List[PrimitiveOp]
    ledger: IdentityLedger
    missing: List[Allocation]  # capture requests: incomplete, never done
    specs: List[PrimitiveSpec]

    def allocation(self, logical_id: str) -> Allocation:
        for row in self.allocations:
            if row.logical_id == logical_id:
                return row
        raise KeyError(logical_id)


_ParentRules = {
    PrimitiveKind.PAGE: (PrimitiveKind.CONTAINER,),
    PrimitiveKind.CONTAINER: (PrimitiveKind.FOLDER, None),
    PrimitiveKind.FOLDER: (PrimitiveKind.FOLDER, None),
}


def validate_specs(specs: Sequence[PrimitiveSpec]) -> None:
    seen: Dict[str, PrimitiveSpec] = {}
    for spec in specs:
        if not spec.logical_id or not spec.name:
            raise ValueError(f"spec {spec.logical_id!r}: logical_id and name are required")
        if spec.logical_id in seen:
            raise ValueError(f"duplicate logical_id {spec.logical_id!r} (identity is logical_id)")
        seen[spec.logical_id] = spec
        if spec.approved_content is not None:
            if spec.kind is not PrimitiveKind.PAGE:
                raise ValueError(f"{spec.logical_id}: only pages carry approved content")
            extra = set(spec.approved_content) - ALLOWED_CONTENT_KEYS
            if extra:
                raise ValueError(f"{spec.logical_id}: unapproved content keys {sorted(extra)}")
        if spec.parent_logical_id and spec.parent_native_id:
            raise ValueError(
                f"{spec.logical_id}: parent_logical_id and parent_native_id are "
                "exclusive (one parent identity source)"
            )
    for spec in specs:
        parent: Optional[PrimitiveSpec] = seen.get(spec.parent_logical_id) if spec.parent_logical_id else None
        if spec.parent_logical_id and parent is None and not spec.parent_native_id:
            raise ValueError(
                f"{spec.logical_id}: parent {spec.parent_logical_id!r} is not in "
                "this batch and no parent_native_id was supplied"
            )
        if parent is not None:
            if parent.kind not in _ParentRules[spec.kind]:
                raise ValueError(
                    f"{spec.logical_id}: a {spec.kind.value} cannot be parented "
                    f"to a {parent.kind.value}"
                )
            if parent.builder_type is not spec.builder_type:
                raise ValueError(
                    f"{spec.logical_id}: builder_type {spec.builder_type.value} "
                    f"does not match parent {parent.logical_id} "
                    f"({parent.builder_type.value})"
                )
    # cycle guard
    for spec in specs:
        walk, cur = {spec.logical_id}, spec
        while cur.parent_logical_id and cur.parent_logical_id in seen:
            cur = seen[cur.parent_logical_id]
            if cur.logical_id in walk:
                raise ValueError(f"parent cycle involving {spec.logical_id!r}")
            walk.add(cur.logical_id)


def _depth(spec: PrimitiveSpec, by_id: Mapping[str, PrimitiveSpec]) -> int:
    d, cur = 0, spec
    while cur.parent_logical_id and cur.parent_logical_id in by_id:
        cur = by_id[cur.parent_logical_id]
        d += 1
    return d


def index_existing(existing: Iterable[ExistingObject]) -> Dict[Tuple[str, Optional[str], str], List[ExistingObject]]:
    index: Dict[Tuple[str, Optional[str], str], List[ExistingObject]] = {}
    for obj in existing:
        index.setdefault((obj.kind.value, obj.parent_native_id, obj.name), []).append(obj)
    return index


def plan_primitives(
    specs: Sequence[PrimitiveSpec],
    *,
    location: str,
    existing: Sequence[ExistingObject] = (),
    dynamic_confirmed: bool = False,
) -> BuildPlan:
    """Identity allocation FIRST (read before create), then content ops.

    Reuse on an exact single match; refuse ambiguous matches (never the first
    row); report missing write routes as capture requests. Every spec gets
    exactly one allocation row -- nothing is silently dropped.
    """
    validate_specs(specs)
    by_id = {s.logical_id: s for s in specs}
    ordered = sorted(specs, key=lambda s: (_depth(s, by_id), s.logical_id))
    index = index_existing(existing)
    ledger = IdentityLedger()
    allocations: List[Allocation] = []
    ops: List[PrimitiveOp] = []
    missing: List[Allocation] = []
    op_seq = 0

    def parent_native_of(spec: PrimitiveSpec) -> Optional[str]:
        if spec.parent_native_id:
            return spec.parent_native_id
        if spec.parent_logical_id:
            rec = ledger.get(spec.parent_logical_id)
            return rec.native_id if rec else None
        return None

    for spec in ordered:
        ledger.put(
            IdentityRecord(
                logical_id=spec.logical_id,
                kind=spec.kind,
                parent_logical_id=spec.parent_logical_id,
                location=location,
            )
        )

    for spec in ordered:
        # --- blocked by an unresolved parent? ---
        if spec.parent_logical_id:
            parent_alloc = next(a for a in allocations if a.logical_id == spec.parent_logical_id)
            if parent_alloc.disposition in (
                Disposition.AMBIGUOUS,
                Disposition.MISSING_CAPABILITY,
                Disposition.BLOCKED_PARENT,
            ):
                row = Allocation(
                    spec.logical_id,
                    Disposition.BLOCKED_PARENT,
                    reason=(
                        f"parent {spec.parent_logical_id} is "
                        f"{parent_alloc.disposition.value}; child cannot be "
                        "bound or created"
                    ),
                )
                allocations.append(row)
                continue

        # --- explicit identity: update binding ---
        if spec.native_id_hint:
            row = Allocation(
                spec.logical_id,
                Disposition.REUSE,
                native_id=spec.native_id_hint,
                match_source="native_id_hint",
                reason="explicit native ID supplied: update binding",
            )
            allocations.append(row)
            ledger.confirm(spec.logical_id, spec.native_id_hint, DeliveryState.CREATED, "native_id_hint")
            if spec.approved_content:
                ops.append(_content_op(spec, location, parent_native_of(spec), f"op-{op_seq:03d}"))
                op_seq += 1
            continue

        # --- read before create: reconcile against verified listings ---
        candidates = []
        if not (spec.parent_logical_id and parent_native_of(spec) is None):
            candidates = [
                obj
                for obj in index.get((spec.kind.value, parent_native_of(spec), spec.name), [])
                if not (spec.slug and obj.slug and obj.slug != spec.slug)
            ]
        if len(candidates) > 1:
            row = Allocation(
                spec.logical_id,
                Disposition.AMBIGUOUS,
                reason=(
                    f"{len(candidates)} existing {spec.kind.value} objects match "
                    f"name {spec.name!r}; ambiguous match refused (never the first)"
                ),
            )
            allocations.append(row)
            continue
        if len(candidates) == 1:
            obj = candidates[0]
            row = Allocation(
                spec.logical_id,
                Disposition.REUSE,
                native_id=obj.native_id,
                match_source="exact_match",
                reason="exact single match on verified listing: reuse, no create",
            )
            allocations.append(row)
            ledger.confirm(spec.logical_id, obj.native_id, DeliveryState.CREATED, "exact_match")
            if spec.approved_content:
                ops.append(_content_op(spec, location, parent_native_of(spec), f"op-{op_seq:03d}"))
                op_seq += 1
            continue

        # --- no match: create needs a verified write route ---
        decision = resolve_operation(
            OpClass.CREATE,
            kind=spec.kind,
            builder_type=spec.builder_type,
            dynamic_confirmed=dynamic_confirmed,
        )
        if decision.status == "missing":
            row = Allocation(
                spec.logical_id,
                Disposition.MISSING_CAPABILITY,
                reason="no verified write route; capability incomplete, never done",
                capture_request=decision.capture_request,
                provenance=decision.provenance,
            )
            allocations.append(row)
            missing.append(row)
            continue
        row = Allocation(
            spec.logical_id,
            Disposition.CREATE,
            match_source=decision.status,
            reason=(
                "write route resolved via capability_inventory"
                if decision.status == "routed"
                else "dynamic candidate route: runtime op-class confirmation required"
            ),
            capture_request=decision.capture_request,
            provenance=decision.provenance,
        )
        allocations.append(row)
        assert decision.capability is not None
        op_seq += 1
        ops.append(
            PrimitiveOp(
                op_id=f"op-{op_seq:03d}",
                action="create",
                op_class=OpClass.CREATE,
                capability=decision.capability,
                logical_id=spec.logical_id,
                kind=spec.kind,
                builder_type=spec.builder_type,
                target={
                    "location": location,
                    "kind": spec.kind.value,
                    "parent_logical_id": spec.parent_logical_id or "",
                    "parent_native_id": parent_native_of(spec) or "",
                    "name": spec.name,
                },
                payload={k: v for k, v in (("name", spec.name), ("slug", spec.slug)) if v},
            )
        )
        if spec.approved_content:
            op_seq += 1
            ops.append(_content_op(spec, location, parent_native_of(spec), f"op-{op_seq:03d}"))

    for op in ops:
        validate_op(op)
    return BuildPlan(
        location=location,
        allocations=allocations,
        ops=ops,
        ledger=ledger,
        missing=missing,
        specs=list(specs),
    )


def _content_op(spec: PrimitiveSpec, location: str, parent_native: Optional[str], op_id: str) -> PrimitiveOp:
    decision = resolve_operation(OpClass.EDIT, kind=spec.kind, builder_type=spec.builder_type)
    if decision.status == "missing":
        raise ValueError(
            f"{spec.logical_id}: content update route missing -- "
            f"{decision.capture_request} (incomplete, never done)"
        )
    assert decision.capability is not None
    return PrimitiveOp(
        op_id=op_id,
        action="update",
        op_class=OpClass.EDIT,
        capability=decision.capability,
        logical_id=spec.logical_id,
        kind=spec.kind,
        builder_type=spec.builder_type,
        target={
            "location": location,
            "kind": spec.kind.value,
            "parent_logical_id": spec.parent_logical_id or "",
            "parent_native_id": parent_native or "",
            "name": spec.name,
        },
        payload=dict(spec.approved_content or {}),
    )


# --------------------------------------------------------------------------
# Execution (sequencing + readback + bounded retry; transports are injected)
# --------------------------------------------------------------------------


@dataclass
class ExecutionRow:
    logical_id: str
    kind: PrimitiveKind
    builder_type: BuilderType
    state: DeliveryState
    status: str  # "created" | "configured" | "reused" | "blocked_*" | "uncertain_unreconciled"
    native_id: str = ""
    note: str = ""
    op_results: List[OpResult] = field(default_factory=list)


@dataclass
class ExecutionReport:
    location: str
    rows: List[ExecutionRow]
    missing: List[Allocation]
    receipts: List[PrimitiveOp]

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for row in self.rows:
            out[row.status] = out.get(row.status, 0) + 1
        out["capture_requests_incomplete"] = len(self.missing)
        return out

    def row(self, logical_id: str) -> ExecutionRow:
        for r in self.rows:
            if r.logical_id == logical_id:
                return r
        raise KeyError(logical_id)


def _run_with_retry(executor: Executor, op: PrimitiveOp, results: List[OpResult]) -> OpResult:
    """Bounded retry per the catalog's own limits. RATE_LIMITED <=
    MAX_429_RETRIES retries; TRANSIENT_ERROR <= MAX_5XX_RETRIES retries.
    UNCERTAIN and REFUSED are never retried here -- uncertainty is reconciled
    by the caller before any retry is even considered."""
    result = executor.run(op)
    results.append(result)
    attempts = 0
    while result.outcome is Outcome.RATE_LIMITED and attempts < MAX_429_RETRIES:
        attempts += 1
        result = executor.run(op)
        results.append(result)
    if result.outcome is Outcome.TRANSIENT_ERROR:
        attempts = 0
        while result.outcome is Outcome.TRANSIENT_ERROR and attempts < MAX_5XX_RETRIES:
            attempts += 1
            result = executor.run(op)
            results.append(result)
    return result


def _reconcile(executor: Executor, op: PrimitiveOp, result: OpResult, results: List[OpResult]) -> Tuple[bool, str]:
    """Read the record back after a write. Returns (confirmed, source).
    Uncertain outcomes are reconciled against the verified read surface; a
    failed reconcile blocks the row -- never a blind retry."""
    read_cap = readback_route(op.kind, op.builder_type)
    if read_cap is None:
        if result.readback:
            return True, "executor_readback (no verified independent read route; outstanding)"
        return False, "no readback and no verified read route: uncertain, unreconciled"
    read_op = PrimitiveOp(
        op_id=f"{op.op_id}-readback",
        action="readback",
        op_class=OpClass.LIST,
        capability=read_cap,
        logical_id=op.logical_id,
        kind=op.kind,
        builder_type=op.builder_type,
        target=dict(op.target),
        payload={"native_id": result.native_id} if result.native_id else {},
        readback_required=False,
    )
    validate_op(read_op)
    read_result = executor.run(read_op)
    results.append(read_result)
    wanted = result.native_id
    observed = read_result.readback.get("native_id", "")
    if wanted and observed == wanted:
        return True, "platform_readback"
    return False, (
        f"uncertain outcome reconciled against {read_cap.capability_id}: "
        f"expected native_id {wanted!r}, observed {observed!r}; blocked, not retried"
    )


def execute_plan(plan: BuildPlan, executor: Executor) -> ExecutionReport:
    """Run planned ops parents-before-children. Every spec yields exactly one
    row. Saving is never publishing; nothing here publishes anything."""
    rows: List[ExecutionRow] = []
    receipts: List[PrimitiveOp] = []
    ops_by_logical: Dict[str, List[PrimitiveOp]] = {}
    for op in plan.ops:
        ops_by_logical.setdefault(op.logical_id, []).append(op)

    for alloc in plan.allocations:
        spec = next(s for s in plan.specs if s.logical_id == alloc.logical_id)
        results: List[OpResult] = []
        if alloc.disposition is Disposition.REUSE:
            plan.ledger.confirm(alloc.logical_id, alloc.native_id, DeliveryState.CREATED, alloc.match_source)
            state, status = DeliveryState.CREATED, "reused"
            note = alloc.reason
            native_id = alloc.native_id
        elif alloc.disposition is not Disposition.CREATE:
            rows.append(
                ExecutionRow(
                    logical_id=alloc.logical_id,
                    kind=spec.kind,
                    builder_type=spec.builder_type,
                    state=DeliveryState.PLANNED,
                    status=f"blocked_{alloc.disposition.value}",
                    note=alloc.reason,
                )
            )
            continue
        else:
            state, status, note, native_id = DeliveryState.PLANNED, "planned", "", ""

        for op in ops_by_logical.get(alloc.logical_id, []):
            # parent native id becomes known at run time (parents run first)
            parent_rec = plan.ledger.get(spec.parent_logical_id) if spec.parent_logical_id else None
            parent_native = spec.parent_native_id or (parent_rec.native_id if parent_rec else "")
            if parent_native and op.target.get("parent_native_id", "") != parent_native:
                op = replace(op, target={**dict(op.target), "parent_native_id": parent_native})
            validate_op(op)
            receipts.append(op)
            if op.action == "create":
                result = _run_with_retry(executor, op, results)
                if result.outcome is not Outcome.OK or not result.native_id:
                    status = "uncertain_unreconciled" if result.outcome is Outcome.UNCERTAIN else f"failed_{result.outcome.value}"
                    note = result.note or f"create did not confirm a native ID ({result.outcome.value})"
                    rows.append(
                        ExecutionRow(
                            logical_id=alloc.logical_id,
                            kind=spec.kind,
                            builder_type=spec.builder_type,
                            state=state,
                            status=status,
                            native_id=result.native_id,
                            note=note,
                            op_results=results,
                        )
                    )
                    break
                confirmed, source = _reconcile(executor, op, result, results)
                if not confirmed:
                    rows.append(
                        ExecutionRow(
                            logical_id=alloc.logical_id,
                            kind=spec.kind,
                            builder_type=spec.builder_type,
                            state=DeliveryState.PLANNED,
                            status="uncertain_unreconciled",
                            native_id=result.native_id,
                            note=source,
                            op_results=results,
                        )
                    )
                    break
                plan.ledger.confirm(alloc.logical_id, result.native_id, DeliveryState.CREATED, source)
                state, status, native_id = DeliveryState.CREATED, "created", result.native_id
                note = f"created; readback {source}"
            else:  # "update" content binding
                result = _run_with_retry(executor, op, results)
                if result.outcome is not Outcome.OK:
                    status = f"failed_{result.outcome.value}"
                    note = result.note or f"content update not confirmed ({result.outcome.value})"
                    break
                confirmed, source = _reconcile(executor, op, result, results)
                if not confirmed:
                    status = "uncertain_unreconciled"
                    note = source
                    break
                state = advance_state(state, DeliveryState.CONFIGURED)
                status = "configured"
                note = f"configured; readback {source}"
        else:
            rows.append(
                ExecutionRow(
                    logical_id=alloc.logical_id,
                    kind=spec.kind,
                    builder_type=spec.builder_type,
                    state=state,
                    status=status,
                    native_id=native_id,
                    note=note,
                    op_results=results,
                )
            )
            continue
        # row was appended inside the loop only on break paths; append here if not
        if not rows or rows[-1].logical_id != alloc.logical_id:
            rows.append(
                ExecutionRow(
                    logical_id=alloc.logical_id,
                    kind=spec.kind,
                    builder_type=spec.builder_type,
                    state=state,
                    status=status,
                    native_id=native_id,
                    note=note,
                    op_results=results,
                )
            )

    return ExecutionReport(
        location=plan.location,
        rows=rows,
        missing=list(plan.missing),
        receipts=receipts,
    )


# --------------------------------------------------------------------------
# Runnable check (assert-based self-check, no network)
# --------------------------------------------------------------------------


class FakeExecutor:
    """Scripted transport for the self-check. Counts every call so retry
    bounds are testable."""

    def __init__(
        self,
        script: Optional[Mapping[Tuple[str, str], Sequence[OpResult]]] = None,
        present_native_ids: Sequence[str] = (),
    ) -> None:
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.present = set(present_native_ids)
        self.calls: List[PrimitiveOp] = []

    def run(self, op: PrimitiveOp) -> OpResult:
        self.calls.append(op)
        if op.action == "readback":
            wanted = op.payload.get("native_id", "")
            if wanted and wanted in self.present:
                return OpResult(Outcome.OK, native_id=wanted, readback={"native_id": wanted})
            return OpResult(Outcome.OK, readback={})
        queue = self.script.get((op.action, op.logical_id))
        if queue:
            return queue.pop(0)
        return OpResult(Outcome.OK, native_id=f"native-{op.logical_id}", readback={"native_id": f"native-{op.logical_id}"})


def _page(logical_id: str, name: str, parent: str, **kw) -> PrimitiveSpec:
    return PrimitiveSpec(
        logical_id=logical_id,
        kind=PrimitiveKind.PAGE,
        builder_type=BuilderType.FUNNEL,
        name=name,
        parent_logical_id=parent,
        **kw,
    )


def self_check() -> None:
    # 0. Instrument control: the W2A catalog itself is honest.
    assert validate_inventory() == [], "capability_inventory reports violations"

    # 1. Real-contract routing: page content create/edit -> gated browser builder.
    for bt in (BuilderType.FUNNEL, BuilderType.WEBSITE):
        for op_class in (OpClass.CREATE, OpClass.EDIT):
            d = resolve_operation(op_class, kind=PrimitiveKind.PAGE, builder_type=bt)
            assert d.status == "routed", (bt, d)
            assert d.capability is not None and d.capability.capability_id == "browser.page_content"
            assert d.capability.transport is Transport.MANAGED_BROWSER
            assert d.capability.resource == "page", "route must stay on the object's own resource"

    # 2. Read surface is REST, never the browser; readback route exists for funnel pages.
    read_d = resolve_operation(OpClass.LIST, kind=PrimitiveKind.CONTAINER, builder_type=BuilderType.FUNNEL)
    assert read_d.status == "routed" and read_d.capability is not None
    assert read_d.capability.transport is Transport.PUBLIC_REST
    assert readback_route(PrimitiveKind.PAGE, BuilderType.FUNNEL) is not None

    # 3. Honest gaps: folder create and website container create are capture
    #    requests -- incomplete, never done, never a guessed selector.
    for kind, bt in ((PrimitiveKind.FOLDER, BuilderType.FUNNEL), (PrimitiveKind.CONTAINER, BuilderType.WEBSITE)):
        d = resolve_operation(OpClass.CREATE, kind=kind, builder_type=bt)
        assert d.status == "missing", (kind, bt, d)
        assert "capture the smallest missing authorized operation" in d.capture_request
        assert "incomplete" not in d.capture_request  # the REQUEST is actionable; the state is reported elsewhere

    # 4. Plan: reuse on exact single match; no create op; identity allocated first.
    container = PrimitiveSpec("c1", PrimitiveKind.CONTAINER, BuilderType.FUNNEL, "Sales Funnel")
    page = _page("p1", "Optin", "c1", approved_content={"html": "<h1>hi</h1>"})
    existing = [ExistingObject(PrimitiveKind.PAGE, "Optin", "pg-77", BuilderType.FUNNEL, parent_native_id="ct-1")]
    plan = plan_primitives(
        [container, page],
        location="loc-1",
        existing=[ExistingObject(PrimitiveKind.CONTAINER, "Sales Funnel", "ct-1", BuilderType.FUNNEL)] + existing,
    )
    assert plan.allocation("c1").disposition is Disposition.REUSE
    assert plan.allocation("c1").native_id == "ct-1"
    assert plan.allocation("p1").disposition is Disposition.REUSE
    assert [op.action for op in plan.ops] == ["update"], plan.ops  # content only, no create
    # allocation rows cover every spec before any content op exists
    assert {a.logical_id for a in plan.allocations} == {"c1", "p1"}

    # 5. Ambiguity refused: never the first row; child blocked; nothing dropped.
    dup = [
        ExistingObject(PrimitiveKind.PAGE, "Optin", "pg-1", BuilderType.FUNNEL, parent_native_id="ct-1"),
        ExistingObject(PrimitiveKind.PAGE, "Optin", "pg-2", BuilderType.FUNNEL, parent_native_id="ct-1"),
    ]
    plan2 = plan_primitives(
        [container, page],
        location="loc-1",
        existing=[ExistingObject(PrimitiveKind.CONTAINER, "Sales Funnel", "ct-1", BuilderType.FUNNEL)] + dup,
    )
    assert plan2.allocation("p1").disposition is Disposition.AMBIGUOUS
    assert all(op.logical_id != "p1" for op in plan2.ops)

    # 6. Missing capability -> capture request row; execution still reports the
    #    spec (no silent drop) and never claims done.
    folder = PrimitiveSpec("f1", PrimitiveKind.FOLDER, BuilderType.FUNNEL, "Client Work")
    plan3 = plan_primitives([folder], location="loc-1")
    assert plan3.allocation("f1").disposition is Disposition.MISSING_CAPABILITY
    assert plan3.missing and "gated-builder step with its gate id" in plan3.missing[0].capture_request
    report3 = execute_plan(plan3, FakeExecutor())
    assert len(report3.rows) == 1 and report3.rows[0].status == "blocked_missing_capability"
    assert report3.rows[0].state is DeliveryState.PLANNED
    assert report3.counts()["capture_requests_incomplete"] == 1

    # 7. Execute happy path: reuse container, create page confirmed by platform
    #    readback, content configured after; parents before children; no
    #    publish op ever.
    plan4 = plan_primitives(
        [container, page],
        location="loc-1",
        existing=[ExistingObject(PrimitiveKind.CONTAINER, "Sales Funnel", "ct-1", BuilderType.FUNNEL)],
    )
    assert plan4.allocation("c1").disposition is Disposition.REUSE
    assert plan4.allocation("p1").disposition is Disposition.CREATE
    assert [op.action for op in plan4.ops] == ["create", "update"]
    assert [op.logical_id for op in plan4.ops] == ["p1", "p1"]
    assert len({op.op_id for op in plan4.ops}) == 2
    fake = FakeExecutor(present_native_ids=["native-p1"])
    report4 = execute_plan(plan4, fake)
    assert len(report4.rows) == 2  # one row per spec, none dropped
    assert report4.row("c1").state is DeliveryState.CREATED and report4.row("c1").status == "reused"
    assert report4.row("p1").state is DeliveryState.CONFIGURED
    assert report4.row("p1").native_id == "native-p1"
    assert all(op.op_class is not OpClass.EXECUTE for op in report4.receipts)
    # create payloads carry identity keys only; content payload keys are approved keys
    for op in report4.receipts:
        if op.action == "create":
            assert set(op.payload) <= {"name", "slug"}
        else:
            assert set(op.payload) <= ALLOWED_CONTENT_KEYS

    # 8. Uncertain outcome: create claims OK but the platform readback cannot
    #    find the object -> blocked unreconciled, NOT created, NOT retried.
    uncertain = FakeExecutor(
        script={("create", "p3"): [OpResult(Outcome.OK, native_id="ghost-1", readback={})]},
        present_native_ids=[],
    )
    plan5 = plan_primitives(
        [
            PrimitiveSpec("c9", PrimitiveKind.CONTAINER, BuilderType.FUNNEL, "Webinar"),
            _page("p3", "Register", "c9"),
        ],
        location="loc-1",
        existing=[ExistingObject(PrimitiveKind.CONTAINER, "Webinar", "ct-5", BuilderType.FUNNEL)],
    )
    assert plan5.allocation("c9").disposition is Disposition.REUSE
    report5 = execute_plan(plan5, uncertain)
    p3_row = report5.row("p3")
    assert p3_row.status == "uncertain_unreconciled" and p3_row.state is DeliveryState.PLANNED
    create_calls = [c for c in uncertain.calls if c.action == "create" and c.logical_id == "p3"]
    assert len(create_calls) == 1, "uncertain outcome must never be blindly retried"

    # 9. Bounded retry uses the catalog's own limits (429: MAX_429_RETRIES).
    flaky = FakeExecutor(
        script={
            ("create", "p8"): [
                OpResult(Outcome.RATE_LIMITED, note="429"),
                OpResult(Outcome.RATE_LIMITED, note="429"),
                OpResult(Outcome.OK, native_id="native-p8", readback={"native_id": "native-p8"}),
            ]
        },
        present_native_ids=["native-p8"],
    )
    plan6 = plan_primitives(
        [PrimitiveSpec("c2", PrimitiveKind.CONTAINER, BuilderType.FUNNEL, "Challenge"), _page("p8", "Day 1", "c2")],
        location="loc-1",
        existing=[ExistingObject(PrimitiveKind.CONTAINER, "Challenge", "ct-2", BuilderType.FUNNEL)],
    )
    report6 = execute_plan(plan6, flaky)
    assert report6.row("p8").status == "created"
    assert len([c for c in flaky.calls if c.action == "create"]) == 3 <= 1 + MAX_429_RETRIES
    stuck = FakeExecutor(
        script={("create", "p9"): [OpResult(Outcome.RATE_LIMITED, note="429")] * (1 + MAX_429_RETRIES)},
        present_native_ids=[],
    )
    plan7 = plan_primitives(
        [PrimitiveSpec("c3", PrimitiveKind.CONTAINER, BuilderType.FUNNEL, "Evergreen"), _page("p9", "Pitch", "c3")],
        location="loc-1",
        existing=[ExistingObject(PrimitiveKind.CONTAINER, "Evergreen", "ct-3", BuilderType.FUNNEL)],
    )
    report7 = execute_plan(plan7, stuck)
    assert report7.row("p9").status == "failed_rate_limited"
    assert len([c for c in stuck.calls if c.action == "create"]) == 1 + MAX_429_RETRIES

    # 10. States are distinct; this writer never reaches PUBLISHED/VERIFIED.
    assert len(DeliveryState) == 5 and len(STATE_LADDER) == 3
    try:
        advance_state(DeliveryState.CREATED, DeliveryState.PUBLISHED)
    except ValueError:
        pass
    else:
        raise AssertionError("PUBLISHED must be refused (W7 owns it)")

    # 11. Structural validation: duplicate identity and bad nesting refused.
    for bad in (
        [container, replace(container, name="Other")],
        [_page("p4", "A", "p5"), _page("p5", "B", "p4")],
        [_page("p6", "A", "c1", approved_content={"iframe_src": "x"})],
    ):
        try:
            validate_specs(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"validate_specs must refuse {bad}")

    # 12. Negative controls: fabricated capability and op-class mismatch are
    #     caught by op validation (injected defects must fail loudly).
    good_op = plan4.ops[0]
    ghost_cap = Capability(
        "ghost.create", Transport.PUBLIC_REST, "POST /invented/endpoint",
        frozenset({OpClass.CREATE}), Support.VERIFIED, "invented.md", resource="page",
        readback=True,
    )
    try:
        validate_op(replace(good_op, capability=ghost_cap))
    except ValueError:
        pass
    else:
        raise AssertionError("fabricated capability must be refused")
    read_cap = readback_route(PrimitiveKind.PAGE, BuilderType.FUNNEL)
    assert read_cap is not None
    try:
        validate_op(replace(good_op, capability=read_cap, op_class=OpClass.CREATE))
    except ValueError:
        pass
    else:
        raise AssertionError("read-class capability must refuse a create op")

    # 13. Administrative folder placement never derives nav/url.
    nav_spec = PrimitiveSpec(
        "p7", PrimitiveKind.PAGE, BuilderType.FUNNEL, "Thank You",
        parent_logical_id="c1", url_path=None, nav_ref=None,
    )
    plan8 = plan_primitives(
        [container, nav_spec],
        location="loc-1",
        existing=[ExistingObject(PrimitiveKind.CONTAINER, "Sales Funnel", "ct-1", BuilderType.FUNNEL)],
    )
    for op in plan8.ops:
        assert "url_path" not in op.payload and "nav_ref" not in op.payload
        assert "url_path" not in op.target and "nav_ref" not in op.target
    assert plan8.allocation("c1").disposition is Disposition.REUSE

    # 14. Duplicate identity in the ledger is refused (keyed by location/kind/
    #     parent/logical id -- never by name).
    led = IdentityLedger()
    rec = IdentityRecord("x1", PrimitiveKind.PAGE, "c1", "loc-1")
    led.put(rec)
    try:
        led.put(IdentityRecord("x1", PrimitiveKind.PAGE, "c1", "loc-1"))
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate identity key must be refused")


if __name__ == "__main__":
    self_check()
    print("primitives self-check: PASS")
    print(f"  contracts consumed from: capability_inventory (W2A-U1), "
          f"{len(OPERATIONS)} routes, bounds {MAX_429_RETRIES}/{MAX_5XX_RETRIES}")
    print("  page content writes route to: browser.page_content (managed browser, gated)")
    print("  folder create + website container create: capture requests (incomplete, never done)")
