#!/usr/bin/env python3
"""funnel_adapter.py — funnel execution adapter (stream W5, assignment W5B-U1).

Execution adapter for FUNNEL page sets on the agreed primitive signatures
(W5A primitives.py) and the real upstream modules (W1A npage_contract.py,
W2A capability_inventory.py, W4A checkpoints.py). It turns one funnel
delivery document into identity allocations, content writes and a truthful
delivery result — nothing invented, nothing silently dropped:

  * Documents are the W1A normative PageSet (kind="funnel"). Websites are
    refused: the website adapter (W5C) owns them. Validation is the real
    validate_page_set (ordering + explicit accept/decline/submit/success/
    error edges; nothing is inferred from page roles).
  * Translation to W5A PrimitiveSpec is mechanical: admin folders become
    FOLDER specs (administrative grouping only — never navigation, never
    URL), the funnel becomes the CONTAINER spec (logical_id = set_id), and
    every page becomes a PAGE spec parented to that container. Parentage is
    folder -> container -> page only; a page's admin_folder_logical_id is an
    administrative namespace recorded as identity metadata, never converted
    into primitive parentage and never a source of nav_ref/url_path.
  * Identity allocation FIRST (W5A plan_primitives: read before create,
    exact-single-match reuse, ambiguous matches blocked — never the first
    row), content SECOND (execute_plan), and this adapter never binds URLs
    or actions (W7 link_resolution) and never publishes (W7 coordinator).
  * Every mutating operation runs through CheckpointingExecutor over a real
    W4A CheckpointStore: confirmed native IDs are persisted immediately,
    a create whose outcome is uncertain holds a pending-op lock until it is
    reconciled (reconcile_op: confirmed / not_found; ambiguous is refused),
    so a resume can never duplicate a page and a blind retry is impossible.
  * Missing write routes (funnel container create, admin folder create) are
    reported as capture requests with the catalog's own provenance text —
    capability incomplete, never done, never a guessed selector.

What this adapter does NOT do (owned elsewhere, by contract):
    publish/verify states (W7 publishing coordinator), URL/action/edge
    binding (W7B link_resolution), forms/surveys (W6), commerce (W8),
    page content composition (W9), transport execution itself (W2
    object_router/recipe_transport, W3 browser layer — injected here as the
    primitives Executor seam), website delivery (W5C).

Import pattern (from any script in the repo):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared-utils"))
    from ghl.funnel_adapter import FunnelAdapter

Runnable check (assert-based self-check, no network):
    python3 -I shared-utils/ghl/funnel_adapter.py
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

# Same bootstrap pattern as shared-utils/delivery/checkpoints.py.
if __package__:
    from . import primitives as prim
    from .capability_inventory import RESTRICTIONS
    from delivery import checkpoints as cps
    from delivery import npage_contract as npage
else:  # script execution: python3 -I shared-utils/ghl/funnel_adapter.py
    _HERE = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _HERE)
    sys.path.insert(0, os.path.join(_HERE, os.pardir, "delivery"))
    import primitives as prim
    from capability_inventory import RESTRICTIONS
    import checkpoints as cps
    import npage_contract as npage


class FunnelAdapterError(ValueError):
    """Funnel contract or execution violation (fail closed, never guess)."""


# --------------------------------------------------------------------------
# Document validation (the real W1A contract + the funnel-kind gate)
# --------------------------------------------------------------------------

def validate_funnel_doc(doc: npage.PageSet) -> List[str]:
    """Contract errors for a FUNNEL document. [] == valid.

    The kind gate is an error, not a fallback: this adapter executes funnels
    only, and a website document must go to the website adapter (W5C).
    """
    if not isinstance(doc, npage.PageSet):
        raise FunnelAdapterError("document must be a delivery.npage_contract.PageSet")
    if doc.kind != npage.SET_KIND_FUNNEL:
        raise FunnelAdapterError(
            f"funnel adapter executes funnels only (kind={doc.kind!r}); "
            "websites belong to the website adapter (W5C)"
        )
    errors = list(npage.validate_page_set(doc))
    folder_ids = {f.logical_id for f in doc.admin_folders}
    if doc.set_id in folder_ids:
        errors.append(
            f"set_id {doc.set_id!r} collides with an admin folder logical_id "
            "(administrative folders are a separate ID space)"
        )
    return errors


def _page_spec(doc: npage.PageSet, page: npage.PageNode) -> prim.PrimitiveSpec:
    """Mechanical page translation. url_path is the contract's explicit
    input; nav_ref stays absent (never derived)."""
    content: Optional[Dict[str, str]] = None
    if page.approved_content:
        extra = set(page.approved_content) - prim.ALLOWED_CONTENT_KEYS
        if extra:
            raise FunnelAdapterError(
                f"{page.logical_id}: unapproved content keys {sorted(extra)} "
                f"(approved keys are {sorted(prim.ALLOWED_CONTENT_KEYS)})"
            )
        not_str = [k for k, v in page.approved_content.items() if not isinstance(v, str)]
        if not_str:
            raise FunnelAdapterError(
                f"{page.logical_id}: approved content values must be strings: {not_str}"
            )
        content = dict(page.approved_content)
    revision = int(page.revision) if str(page.revision).isdigit() else 1
    return prim.PrimitiveSpec(
        logical_id=page.logical_id,
        kind=prim.PrimitiveKind.PAGE,
        builder_type=prim.BuilderType.FUNNEL,
        name=page.name,
        slug=page.slug,
        parent_logical_id=doc.set_id,
        role=page.role or "",
        intent=page.intent,
        revision=revision,
        approved_content=content,
        url_path=page.location.url_path,
        native_id_hint=page.identities.page_id or None,
    )


def funnel_specs(
    doc: npage.PageSet,
    *,
    container_native_id: Optional[str] = None,
    container_parent_logical_id: Optional[str] = None,
    container_parent_native_id: Optional[str] = None,
) -> List[prim.PrimitiveSpec]:
    """Translate a validated funnel PageSet into W5A PrimitiveSpecs.

    Container identity is the set_id. Its parent is EXPLICIT input only
    (a declared admin folder logical id, or an out-of-batch native id) —
    never derived from page placement.
    """
    if container_parent_logical_id and container_parent_native_id:
        raise FunnelAdapterError(
            "container_parent_logical_id and container_parent_native_id are "
            "exclusive (one parent identity source)"
        )
    if container_parent_logical_id:
        folder_ids = {f.logical_id for f in doc.admin_folders}
        if container_parent_logical_id not in folder_ids:
            raise FunnelAdapterError(
                f"container parent {container_parent_logical_id!r} is not a "
                "declared admin folder"
            )
    specs: List[prim.PrimitiveSpec] = []
    for f in doc.admin_folders:
        specs.append(
            prim.PrimitiveSpec(
                logical_id=f.logical_id,
                kind=prim.PrimitiveKind.FOLDER,
                builder_type=prim.BuilderType.FUNNEL,
                name=f.name,
                parent_logical_id=f.parent_logical_id,
                role="admin-folder",
                intent="administrative grouping only: never navigation, never URL",
            )
        )
    specs.append(
        prim.PrimitiveSpec(
            logical_id=doc.set_id,
            kind=prim.PrimitiveKind.CONTAINER,
            builder_type=prim.BuilderType.FUNNEL,
            name=doc.set_id,
            slug=doc.set_id,
            parent_logical_id=container_parent_logical_id,
            parent_native_id=container_parent_native_id,
            role="funnel-container",
            intent=f"funnel container for set {doc.set_id}",
            native_id_hint=container_native_id,
        )
    )
    specs.extend(_page_spec(doc, p) for p in doc.pages)
    try:
        prim.validate_specs(specs)
    except ValueError as exc:
        raise FunnelAdapterError(str(exc)) from exc
    return specs


# --------------------------------------------------------------------------
# Checkpointed transport wrapper (W4A store around the W2/W3 executor seam)
# --------------------------------------------------------------------------

class CheckpointingExecutor:
    """W4A checkpoint discipline around every mutating operation.

    Classification contract with the transport (W2 recipe_transport / W3
    browser layer): Outcome.UNCERTAIN means the effect is unknown and holds
    a pending-op lock on the key until reconciled; every other non-OK
    outcome (RATE_LIMITED, TRANSIENT_ERROR, REFUSED, ERROR) is a definite
    non-effect the transport is allowed to bound-retry, so the lock is
    released as not_found. A transport that cannot prove non-creation must
    return UNCERTAIN — that is the honest seam.

    Retry discipline: while any operation on the key is unresolved the next
    attempt is REFUSED with no transport call (plan_create "blocked-pending"
    / begin_op PendingOperationError), so a blind retry is impossible and a
    resume never duplicates a page.
    """

    def __init__(self, inner: prim.Executor, store: cps.CheckpointStore, location: str) -> None:
        self.inner = inner
        self.store = store
        self.location = location
        self.journal: List[dict] = []

    # -- helpers ---------------------------------------------------------
    def _key_for(self, op: prim.PrimitiveOp) -> cps.CheckpointKey:
        parent = (op.target or {}).get("parent_logical_id") or None
        return cps.CheckpointKey(self.location, op.kind.value, parent, op.logical_id)

    def _record(
        self,
        op: prim.PrimitiveOp,
        result: prim.OpResult,
        checkpoint: str,
        cp_op_id: str = "",
    ) -> None:
        self.journal.append(
            {
                "op_id": op.op_id,
                "cp_op_id": cp_op_id,
                "action": op.action,
                "logical_id": op.logical_id,
                "outcome": result.outcome.value,
                "native_id": result.native_id,
                "readback": dict(result.readback),
                "note": result.note,
                "checkpoint": checkpoint,
            }
        )

    # -- the seam --------------------------------------------------------
    def run(self, op: prim.PrimitiveOp) -> prim.OpResult:
        if op.action == "readback":
            # Reads are not mutations: no op lock, no duplicate risk.
            result = self.inner.run(op)
            self._record(op, result, "read")
            return result

        key = self._key_for(op)
        if op.action == "create":
            arm, existing = self.store.plan_create(key)
            if arm == "blocked-pending":
                result = prim.OpResult(
                    prim.Outcome.REFUSED,
                    note=(
                        f"{key.token()}: an unresolved operation holds this key; "
                        "reconcile before any retry (no transport call)"
                    ),
                )
                self._record(op, result, "blocked")
                return result
            if arm == "reuse" and existing is not None and existing.native_id:
                result = prim.OpResult(
                    prim.Outcome.REFUSED,
                    note=(
                        f"{key.token()}: already checkpointed as "
                        f"{existing.native_id}; duplicate create refused "
                        "(resume never duplicates pages)"
                    ),
                )
                self._record(op, result, "blocked")
                return result

        # Unique per store, deterministic per op: never reuse a checkpoint op id.
        n = sum(1 for i in self.store.ops if i.startswith(f"{op.op_id}#")) + 1
        cp_op_id = f"{op.op_id}#a{n}"
        try:
            self.store.begin_op(key, cp_op_id, action=op.action)
        except cps.CheckpointError as exc:
            result = prim.OpResult(prim.Outcome.REFUSED, note=str(exc))
            self._record(op, result, "blocked")
            return result

        result = self.inner.run(op)
        try:
            if result.outcome is prim.Outcome.OK and result.native_id and op.action == "create":
                # Confirmed native ID persisted immediately.
                self.store.complete_op(cp_op_id, native_id=result.native_id)
                self._record(op, result, "confirmed", cp_op_id)
            elif result.outcome is prim.Outcome.OK:
                try:
                    self.store.complete_op(cp_op_id)  # record exists from adopt/create
                    self._record(op, result, "completed", cp_op_id)
                except cps.UnknownCheckpointError:
                    # No record to close against yet: hold, never guess.
                    self._record(op, result, "held", cp_op_id)
            elif result.outcome is prim.Outcome.UNCERTAIN:
                # Unknown effect: pending-op lock until reconciled (W4C).
                self._record(op, result, "held", cp_op_id)
            else:
                # Definite non-effect per the classification contract.
                self.store.reconcile_op(cp_op_id, outcome="not_found")
                self._record(op, result, "released", cp_op_id)
        except cps.CheckpointError as exc:
            self._record(op, result, "held", cp_op_id)
            return prim.OpResult(
                prim.Outcome.REFUSED,
                native_id=result.native_id,
                readback=dict(result.readback),
                note=f"checkpoint refused: {exc}",
            )
        return result


# --------------------------------------------------------------------------
# Plan and report
# --------------------------------------------------------------------------

@dataclass
class FunnelPlan:
    """One planned funnel delivery: contract document + W5A build plan."""

    doc: npage.PageSet
    location: str
    build_plan: prim.BuildPlan
    container_logical_id: str
    ordering: Tuple[str, ...]  # explicit funnel ordering, carried for W7
    edges: Tuple[Tuple[str, str, str], ...]  # (from, to, kind), never inferred

    def allocation(self, logical_id: str) -> prim.Allocation:
        return self.build_plan.allocation(logical_id)


@dataclass
class FunnelExecutionReport:
    """Truthful delivery result: per-page rows, native IDs, restrictions."""

    plan: FunnelPlan
    result: npage.DeliveryResult
    rows: List[prim.ExecutionRow]
    counts: Dict[str, int]
    unresolved_ops: List[dict]
    incomplete: bool


_STATUS_TO_RESULT = {
    prim.Outcome.OK: npage.RESULT_OK,
    prim.Outcome.UNCERTAIN: npage.RESULT_UNCERTAIN,
    prim.Outcome.REFUSED: npage.RESULT_FAILED,
    prim.Outcome.ERROR: npage.RESULT_FAILED,
    prim.Outcome.RATE_LIMITED: npage.RESULT_FAILED,
    prim.Outcome.TRANSIENT_ERROR: npage.RESULT_FAILED,
}

_ROW_TO_STATE = {
    "created": npage.STATE_CREATED,
    "reused": npage.STATE_CREATED,
    "configured": npage.STATE_CONFIGURED,
}


class FunnelAdapter:
    """Funnel execution adapter over real upstream modules.

    location is the platform location/account key used for checkpoint
    identity; store is the W4A durable store; executor is the W2/W3
    transport seam (primitives.Executor). dynamic_confirmed is passed to
    route resolution exactly as W2A defines it (a caller-confirmed dynamic
    surface — a read/list confirmation never implies create/edit).
    """

    def __init__(
        self,
        location: str,
        store: cps.CheckpointStore,
        executor: prim.Executor,
        dynamic_confirmed: bool = False,
    ) -> None:
        if not location or not location.strip():
            raise FunnelAdapterError("location must be a non-empty string")
        self.location = location.strip()
        self.store = store
        self.executor = CheckpointingExecutor(executor, store, self.location)
        self.dynamic_confirmed = dynamic_confirmed

    # -- identity keys ---------------------------------------------------
    def _key(
        self, logical_id: str, kind: prim.PrimitiveKind, parent: Optional[str]
    ) -> cps.CheckpointKey:
        return cps.CheckpointKey(self.location, kind.value, parent, logical_id)

    def _key_for_spec(self, spec: prim.PrimitiveSpec) -> cps.CheckpointKey:
        return self._key(spec.logical_id, spec.kind, spec.parent_logical_id)

    # -- phase 1: validate + translate + allocate identities FIRST -------
    def prepare(
        self,
        doc: npage.PageSet,
        *,
        existing: Sequence[prim.ExistingObject] = (),
        container_native_id: Optional[str] = None,
        container_parent_logical_id: Optional[str] = None,
        container_parent_native_id: Optional[str] = None,
    ) -> FunnelPlan:
        errors = validate_funnel_doc(doc)
        if errors:
            raise FunnelAdapterError(
                "funnel document failed contract validation:\n" + "\n".join(errors)
            )
        specs = funnel_specs(
            doc,
            container_native_id=container_native_id,
            container_parent_logical_id=container_parent_logical_id,
            container_parent_native_id=container_parent_native_id,
        )

        # Read before create: confirmed checkpoint identities become explicit
        # update bindings (resume never duplicates).
        hinted: Dict[str, str] = {}
        for spec in specs:
            if spec.native_id_hint:
                continue
            cp = self.store.read(self._key_for_spec(spec))
            if cp is not None and cp.native_id:
                hinted[spec.logical_id] = cp.native_id
        if hinted:
            specs = [
                replace(spec, native_id_hint=hinted[spec.logical_id])
                if spec.logical_id in hinted
                else spec
                for spec in specs
            ]

        build = prim.plan_primitives(
            specs,
            location=self.location,
            existing=list(existing),
            dynamic_confirmed=self.dynamic_confirmed,
        )

        # Reused identities are adopted durably BEFORE any content write, and
        # a confirmed identity is never silently rebound.
        for alloc in build.allocations:
            if alloc.disposition is not prim.Disposition.REUSE or not alloc.native_id:
                continue
            spec = next(s for s in specs if s.logical_id == alloc.logical_id)
            key = self._key_for_spec(spec)
            cp = self.store.read(key)
            if cp is None:
                self.store.adopt(
                    key,
                    native_id=alloc.native_id,
                    name=spec.name,
                    slug=spec.slug or None,
                )
            elif cp.native_id and cp.native_id != alloc.native_id:
                raise FunnelAdapterError(
                    f"{alloc.logical_id}: checkpointed as {cp.native_id} but "
                    f"allocation matched {alloc.native_id}; refusing rebind"
                )

        return FunnelPlan(
            doc=doc,
            location=self.location,
            build_plan=build,
            container_logical_id=doc.set_id,
            ordering=tuple(doc.ordering),
            edges=tuple((e.from_logical_id, e.to_logical_id, e.kind) for e in doc.edges),
        )

    # -- phase 2: content SECOND, then report ---------------------------
    def execute(self, plan: FunnelPlan) -> FunnelExecutionReport:
        doc = plan.doc
        rep = prim.execute_plan(plan.build_plan, self.executor)

        native: Dict[str, str] = {
            r.logical_id: r.native_id for r in rep.rows if r.native_id
        }
        for alloc in plan.build_plan.allocations:
            if alloc.native_id and alloc.logical_id not in native:
                native[alloc.logical_id] = alloc.native_id

        # Durable states: CREATED lands via complete_op/adopt; CONFIGURED is
        # exactly one forward step after a confirmed content write. Saving is
        # never publishing — PUBLISHED/VERIFIED are W7's, refused by the store.
        for row in rep.rows:
            if row.status != "configured":
                continue
            spec = next(s for s in plan.build_plan.specs if s.logical_id == row.logical_id)
            key = self._key_for_spec(spec)
            cp = self.store.read(key)
            if cp is not None and cp.state == cps.STATE_CREATED:
                self.store.set_state(key, cps.STATE_CONFIGURED, cp.revision)

        # Reflect reality into the contract document (forward-only).
        for page in doc.pages:
            row = rep.row(page.logical_id)
            if page.identities.page_id is None and native.get(page.logical_id):
                page.identities.page_id = native[page.logical_id]
            if native.get(doc.set_id):
                page.identities.container_id = native[doc.set_id]
            folder_lid = page.location.admin_folder_logical_id
            if folder_lid and native.get(folder_lid):
                page.identities.folder_id = native[folder_lid]
            target = _ROW_TO_STATE.get(row.status)
            if target is None:
                continue
            if page.state == target:
                continue
            if target == npage.STATE_CREATED and page.state == npage.STATE_PLANNED:
                npage.advance_state(page, npage.STATE_CREATED)
            elif target == npage.STATE_CONFIGURED and page.state in (
                npage.STATE_PLANNED,
                npage.STATE_CREATED,
            ):
                if page.state == npage.STATE_PLANNED:
                    npage.advance_state(page, npage.STATE_CREATED)
                npage.advance_state(page, npage.STATE_CONFIGURED)

        # DeliveryResult: page rows exactly (check_no_dropped_pages scope).
        result = npage.DeliveryResult(set_id=doc.set_id)
        journal = self.executor.journal
        for page in doc.pages:
            row = rep.row(page.logical_id)
            ops = [
                npage.OperationResult(
                    operation=f"{j['action']}:{j['op_id']}",
                    status=_STATUS_TO_RESULT[prim.Outcome(j["outcome"])],
                    detail=j["note"],
                    native_id=j["native_id"] or None,
                    readback=dict(j["readback"]),
                )
                for j in journal
                if j["logical_id"] == page.logical_id
            ]
            if not ops:
                alloc = plan.build_plan.allocation(page.logical_id)
                detail = "; ".join(x for x in (row.note, alloc.capture_request) if x)
                if row.status == "reused":
                    ops = [
                        npage.OperationResult(
                            operation="reuse",
                            status=npage.RESULT_OK,
                            detail=detail or "exact match reused; no write needed",
                            native_id=row.native_id or None,
                        )
                    ]
                else:
                    ops = [
                        npage.OperationResult(
                            operation="allocate",
                            status=npage.RESULT_FAILED,
                            detail=detail or row.status,
                        )
                    ]
            result.page_results[page.logical_id] = ops

        # Native identities per logical id (None means not allocated).
        for page in doc.pages:
            folder_lid = page.location.admin_folder_logical_id
            result.native_ids[page.logical_id] = {
                "folder_id": native.get(folder_lid) if folder_lid else None,
                "container_id": native.get(doc.set_id),
                "page_id": native.get(page.logical_id),
            }
        result.native_ids[doc.set_id] = {"container_id": native.get(doc.set_id)}
        for f in doc.admin_folders:
            result.native_ids[f.logical_id] = {"folder_id": native.get(f.logical_id)}

        # Real platform restrictions, reported — never a dropped page.
        for alloc in plan.build_plan.missing:
            result.restrictions.append(
                f"{alloc.logical_id}: capability INCOMPLETE — {alloc.capture_request} "
                f"({alloc.provenance})"
            )
        wants_publish = [p.logical_id for p in doc.pages if p.desired_state == npage.DESIRED_PUBLISHED]
        if wants_publish:
            result.restrictions.append(
                f"desired_state=published on {wants_publish}: publication is owned by "
                "the W7 publishing coordinator (record_publish under an explicit "
                "authorization); this adapter never publishes (saving is never publishing)"
            )
        if any(j["action"] == "update" for j in journal):
            result.restrictions.append(RESTRICTIONS["funnel_page_content_no_public_api"][0])
        unresolved = [
            dict(op)
            for op in self.store.ops.values()
            if op["status"] in (cps.OP_OPEN, cps.OP_UNCERTAIN)
        ]
        for op in unresolved:
            result.restrictions.append(
                f"unresolved operation {op['op_id']} on {op['key']}: reconcile via "
                "checkpoints.reconcile_op before any retry (W4C)"
            )

        # Honesty gate: a page is never silently dropped.
        problems = npage.check_no_dropped_pages(doc, result)
        if problems:
            raise FunnelAdapterError(
                "delivery would drop pages:\n" + "\n".join(problems)
            )

        counts = rep.counts()
        incomplete = bool(plan.build_plan.missing) or bool(unresolved) or any(
            r.status.startswith("blocked_") or r.status == "uncertain_unreconciled"
            for r in rep.rows
        )
        counts["incomplete"] = incomplete
        return FunnelExecutionReport(
            plan=plan,
            result=result,
            rows=rep.rows,
            counts=counts,
            unresolved_ops=unresolved,
            incomplete=incomplete,
        )

    def run(self, doc: npage.PageSet, **prepare_kw) -> FunnelExecutionReport:
        """prepare + execute in one call."""
        return self.execute(self.prepare(doc, **prepare_kw))


# --------------------------------------------------------------------------
# Runnable check (assert-based self-check, no network)
# --------------------------------------------------------------------------

class RecordingExecutor:
    """Scripted transport for the self-check only. Counts every call so
    'exactly one create, never a blind retry' is testable."""

    def __init__(self, script: Optional[Mapping[Tuple[str, str], Callable]] = None) -> None:
        self.calls: List[prim.PrimitiveOp] = []
        self.script = dict(script or {})
        self.ids: Dict[str, str] = {}
        self._n = 0

    def calls_for(self, action: str, logical_id: Optional[str] = None) -> List[prim.PrimitiveOp]:
        return [
            op
            for op in self.calls
            if op.action == action and (logical_id is None or op.logical_id == logical_id)
        ]

    def run(self, op: prim.PrimitiveOp) -> prim.OpResult:
        self.calls.append(op)
        handler = self.script.get((op.action, op.logical_id))
        if handler is not None:
            return handler(op, self)
        if op.action == "readback":
            return prim.OpResult(
                prim.Outcome.OK,
                readback={"native_id": (op.payload or {}).get("native_id", "")},
            )
        self._n += 1
        native = self.ids.get(op.logical_id) or f"nat-{op.logical_id}-{self._n}"
        self.ids[op.logical_id] = native
        return prim.OpResult(
            prim.Outcome.OK,
            native_id=native,
            readback={"native_id": native},
        )


def _mk_doc(
    *,
    with_folder: bool = False,
    published_page: bool = True,
) -> npage.PageSet:
    pages = [
        npage.PageNode(
            logical_id="page-1",
            name="Page One",
            slug="page-1",
            builder_type="html",
            intent="first step",
            location=npage.PageLocation(
                url_path="/step-1",
                admin_folder_logical_id="af-1" if with_folder else None,
            ),
            approved_content={"html": "<h1>one</h1>"},
        ),
        npage.PageNode(
            logical_id="page-2",
            name="Page Two",
            slug="page-2",
            builder_type="html",
            intent="second step",
            location=npage.PageLocation(url_path="/step-2"),
            approved_content={"html": "<h1>two</h1>"},
        ),
        npage.PageNode(
            logical_id="page-3",
            name="Page Three",
            slug="page-3",
            builder_type="html",
            intent="final step",
            location=npage.PageLocation(url_path="/step-3"),
            approved_content={"html": "<h1>three</h1>"},
            desired_state=npage.DESIRED_PUBLISHED if published_page else npage.DESIRED_DRAFT,
        ),
    ]
    return npage.PageSet(
        set_id="elev-funnel",
        kind=npage.SET_KIND_FUNNEL,
        pages=pages,
        ordering=["page-1", "page-2", "page-3"],
        edges=[
            npage.Edge("page-1", "page-2", npage.EDGE_ACCEPT),
            npage.Edge("page-1", "page-3", npage.EDGE_DECLINE),
            npage.Edge("page-2", "page-3", npage.EDGE_SUBMIT),
            npage.Edge("page-3", "page-1", npage.EDGE_SUCCESS),
            npage.Edge("page-2", "page-1", npage.EDGE_ERROR),
        ],
        admin_folders=[npage.AdminFolder("af-1", "Campaign Folders")] if with_folder else [],
    )


def self_check() -> int:
    import shutil
    import tempfile

    checks = 0

    def ok(cond: bool, what: str) -> None:
        nonlocal checks
        assert cond, f"FAIL: {what}"
        checks += 1

    def raised(fn, exc, what: str) -> None:
        nonlocal checks
        try:
            fn()
        except exc:
            checks += 1
            return
        except Exception as other:  # noqa: BLE001 - self-check honesty
            raise AssertionError(
                f"FAIL: {what}: raised {type(other).__name__} not {exc.__name__}"
            )
        raise AssertionError(f"FAIL: {what}: nothing raised")

    td = tempfile.mkdtemp(prefix="operator-W5B-U1-")
    try:
        store_path = os.path.join(td, "checkpoints.json")

        # ---- kind gate + contract validation --------------------------
        website = _mk_doc()
        website.kind = npage.SET_KIND_WEBSITE
        raised(
            lambda: FunnelAdapter("acc1", cps.CheckpointStore(store_path), RecordingExecutor()).prepare(website),
            FunnelAdapterError,
            "website document refused by the funnel adapter",
        )
        try:
            FunnelAdapter("acc1", cps.CheckpointStore(store_path), RecordingExecutor()).prepare(website)
            raise AssertionError("FAIL: website kind gate did not fire")
        except FunnelAdapterError as exc:
            ok("website adapter" in str(exc), "kind-gate error names the website adapter")

        bad = _mk_doc()
        bad.ordering = ["page-1", "page-2"]
        errs = validate_funnel_doc(bad)
        ok(any("page-3" in e for e in errs), "ordering omits page-3 -> contract error")

        bad = _mk_doc()
        bad.edges = [npage.Edge("page-1", "page-2", "jump")]
        errs = validate_funnel_doc(bad)
        ok(any("kind" in e for e in errs), "bad edge kind -> contract error")

        bad = _mk_doc()
        bad.edges = [npage.Edge("page-1", "ghost", npage.EDGE_ACCEPT)]
        errs = validate_funnel_doc(bad)
        ok(any("ghost" in e for e in errs), "edge to unknown page -> contract error")

        bad = _mk_doc()
        bad.pages[0].approved_content = {"javascript": "alert(1)"}
        raised(
            lambda: funnel_specs(bad),
            FunnelAdapterError,
            "unapproved content key refused at translation",
        )

        # ---- happy path: existing funnel (hint), 3 pages --------------
        store = cps.CheckpointStore(store_path)
        ex = RecordingExecutor()
        adapter = FunnelAdapter("acc1", store, ex)
        doc = _mk_doc()
        rep = adapter.run(doc, container_native_id="fun-1")
        rows = {r.logical_id: r for r in rep.rows}
        ok(
            all(rows[f"page-{i}"].status == "configured" for i in (1, 2, 3)),
            "happy path: all pages configured",
        )
        creates = ex.calls_for("create")
        ok(len(creates) == 3, "happy path: exactly 3 create calls (pages only)")
        ok(
            [op.logical_id for op in creates] == ["page-1", "page-2", "page-3"],
            "happy path: creates follow explicit ordering",
        )
        ok(
            [op.logical_id for op in ex.calls_for("create", "elev-funnel")] == [],
            "happy path: container reused, no create for it",
        )
        ok(
            npage.check_no_dropped_pages(doc, rep.result) == [],
            "happy path: no page dropped",
        )
        ok(
            rep.result.native_ids["page-2"]["page_id"] == ex.ids["page-2"]
            and rep.result.native_ids["page-2"]["container_id"] == "fun-1",
            "happy path: native IDs recorded per page",
        )
        ok(
            len(rep.plan.edges) == 5
            and {k for _, _, k in rep.plan.edges} == set(npage.EDGE_KINDS),
            "happy path: all five explicit edge kinds carried for W7",
        )
        ok(
            rep.plan.ordering == ("page-1", "page-2", "page-3"),
            "happy path: ordering carried verbatim",
        )
        ok(
            all(
                cp.published_url is None
                for cp in store.list_checkpoints(location="acc1")
            ),
            "happy path: nothing published (saving is never publishing)",
        )
        ok(
            any("W7" in r and "publish" in r for r in rep.result.restrictions),
            "happy path: desired_state=published reported as W7-owned",
        )
        ok(
            any("public API" in r for r in rep.result.restrictions),
            "happy path: browser-executed content route reported honestly",
        )
        ok(
            all(doc.pages[i].state == npage.STATE_CONFIGURED for i in range(3)),
            "happy path: document states advanced to CONFIGURED",
        )
        ok(
            doc.pages[1].identities.page_id == ex.ids["page-2"]
            and doc.pages[1].identities.container_id == "fun-1",
            "happy path: identities reflected into the document",
        )
        ok(len(ex.calls_for("update")) == 3, "happy path: 3 content updates")
        ok(rep.incomplete is False, "happy path: complete")
        cps_rows = store.list_checkpoints(location="acc1")
        ok(
            len(cps_rows) == 4
            and all(r.state == cps.STATE_CONFIGURED or r.key.logical_id == "elev-funnel" for r in cps_rows),
            "happy path: 4 checkpoint records (container + 3 pages)",
        )
        reused_container = store.read(cps.CheckpointKey("acc1", "container", None, "elev-funnel"))
        ok(
            reused_container is not None
            and reused_container.provenance == cps.PROVENANCE_REUSED
            and reused_container.native_id == "fun-1",
            "happy path: container adopted as PROVENANCE_REUSED",
        )

        # ---- resume: same store, zero creates -------------------------
        ex2 = RecordingExecutor()
        rep2 = FunnelAdapter("acc1", store, ex2).run(_mk_doc())
        ok(len(ex2.calls_for("create")) == 0, "resume: zero creates (checkpointed identities)")
        ok(
            all(r.status == "configured" for r in rep2.rows if r.kind is prim.PrimitiveKind.PAGE),
            "resume: pages reused and configured",
        )
        ok(len(store.list_checkpoints(location="acc1")) == 4, "resume: no duplicate records")

        # ---- verified listing: single match reuse ---------------------
        store_b = cps.CheckpointStore(os.path.join(td, "b.json"))
        ex_b = RecordingExecutor()
        existing = [
            prim.ExistingObject(
                kind=prim.PrimitiveKind.PAGE,
                name="Page Two",
                native_id="nat-listed",
                builder_type=prim.BuilderType.FUNNEL,
                slug="page-2",
                parent_native_id="fun-1",
            )
        ]
        rep_b = FunnelAdapter("acc1", store_b, ex_b).run(_mk_doc(), container_native_id="fun-1", existing=existing)
        ok(
            rep_b.plan.allocation("page-2").disposition is prim.Disposition.REUSE
            and rep_b.plan.allocation("page-2").native_id == "nat-listed",
            "listing reuse: exact single match -> reuse, no create",
        )
        ok(len(ex_b.calls_for("create", "page-2")) == 0, "listing reuse: zero creates for page-2")
        ok(
            store_b.read(cps.CheckpointKey("acc1", "page", "elev-funnel", "page-2")).provenance
            == cps.PROVENANCE_REUSED,
            "listing reuse: adopted as PROVENANCE_REUSED",
        )

        # ---- ambiguous match blocks, never the first ------------------
        store_c = cps.CheckpointStore(os.path.join(td, "c.json"))
        ex_c = RecordingExecutor()
        ambiguous = [
            prim.ExistingObject(
                kind=prim.PrimitiveKind.PAGE,
                name="Page Two",
                native_id=f"nat-dup-{i}",
                builder_type=prim.BuilderType.FUNNEL,
                slug="page-2",
                parent_native_id="fun-1",
            )
            for i in (1, 2)
        ]
        rep_c = FunnelAdapter("acc1", store_c, ex_c).run(
            _mk_doc(), container_native_id="fun-1", existing=ambiguous
        )
        row_c = next(r for r in rep_c.rows if r.logical_id == "page-2")
        ok(row_c.status == "blocked_ambiguous", "ambiguous match -> blocked, not first row")
        ok(len(ex_c.calls_for("create", "page-2")) == 0, "ambiguous match -> zero create calls")
        ok(
            npage.check_no_dropped_pages(rep_c.plan.doc, rep_c.result) == [],
            "ambiguous match: page still has a result row",
        )

        # ---- missing write route: capture request, never done ---------
        store_d = cps.CheckpointStore(os.path.join(td, "d.json"))
        ex_d = RecordingExecutor()
        rep_d = FunnelAdapter("acc1", store_d, ex_d).run(_mk_doc())
        alloc_d = rep_d.plan.allocation("elev-funnel")
        ok(
            alloc_d.disposition is prim.Disposition.MISSING_CAPABILITY
            and "smallest missing authorized operation" in alloc_d.capture_request,
            "container create: missing route -> capture request (incomplete)",
        )
        ok(
            all(r.status == "blocked_blocked_parent" for r in rep_d.rows if r.kind is prim.PrimitiveKind.PAGE),
            "container blocked -> every page row blocked_parent",
        )
        ok(len(ex_d.calls) == 0, "container blocked -> zero transport calls")
        ok(rep_d.incomplete is True, "container blocked -> reported incomplete")
        ok(
            any("INCOMPLETE" in r for r in rep_d.result.restrictions),
            "capture request surfaced in restrictions",
        )
        ok(
            npage.check_no_dropped_pages(rep_d.plan.doc, rep_d.result) == [],
            "blocked funnel: pages still reported, never dropped",
        )

        # ---- dynamic surface is confirmed by the caller, never implied -
        store_e = cps.CheckpointStore(os.path.join(td, "e.json"))
        ex_e = RecordingExecutor()
        adapter_e = FunnelAdapter("acc1", store_e, ex_e, dynamic_confirmed=True)
        plan_e = adapter_e.prepare(_mk_doc())
        alloc_e = plan_e.allocation("elev-funnel")
        ok(
            alloc_e.disposition is prim.Disposition.MISSING_CAPABILITY,
            "dynamic surface: still incomplete until the true op class is captured",
        )

        # ---- uncertain outcome: no blind retry, lock held -------------
        store_f = cps.CheckpointStore(os.path.join(td, "f.json"))
        calls = {"n": 0}

        def uncertain_first(op, ex_):
            calls["n"] += 1
            if calls["n"] == 1:
                return prim.OpResult(prim.Outcome.UNCERTAIN, note="timeout; effect unknown")
            return prim.OpResult(
                prim.Outcome.OK, native_id="nat-page-1-x", readback={"native_id": "nat-page-1-x"}
            )

        ex_f = RecordingExecutor({("create", "page-1"): uncertain_first})
        rep_f = FunnelAdapter("acc1", store_f, ex_f).run(_mk_doc(), container_native_id="fun-1")
        row_f = next(r for r in rep_f.rows if r.logical_id == "page-1")
        ok(row_f.status == "uncertain_unreconciled", "uncertain create -> uncertain_unreconciled")
        ok(
            len(ex_f.calls_for("create", "page-1")) == 1,
            "uncertain create -> exactly one attempt (blind retry impossible)",
        )
        held_ops = [o for o in store_f.ops.values() if o["status"] in (cps.OP_OPEN, cps.OP_UNCERTAIN)]
        ok(len(held_ops) == 1, "uncertain create -> pending-op lock held for W4C")
        ok(rep_f.incomplete is True, "uncertain create -> incomplete")

        # resume while unresolved: refused with no transport call
        ex_f2 = RecordingExecutor()
        adapter_f2 = FunnelAdapter("acc1", store_f, ex_f2)
        rep_f2 = adapter_f2.run(_mk_doc(), container_native_id="fun-1")
        row_f2 = next(r for r in rep_f2.rows if r.logical_id == "page-1")
        ok(
            row_f2.status == "failed_refused"
            and len(ex_f2.calls_for("create", "page-1")) == 0,
            "unresolved op -> create refused without a transport call",
        )
        ok(
            any("reconcile" in (j["note"] or "") for j in adapter_f2.executor.journal if j["logical_id"] == "page-1"),
            "refusal names the reconcile step",
        )

        # ambiguous reconcile refused, lock kept
        raised(
            lambda: store_f.reconcile_op(held_ops[0]["op_id"], outcome="ambiguous"),
            cps.AmbiguousMatchError,
            "ambiguous reconcile refused",
        )

        # definite reconcile: confirmed identity persisted, then reuse
        store_f.reconcile_op(held_ops[0]["op_id"], outcome="confirmed", native_id="nat-page-1-x")
        ex_f3 = RecordingExecutor()
        rep_f3 = FunnelAdapter("acc1", store_f, ex_f3).run(_mk_doc(), container_native_id="fun-1")
        ok(
            len(ex_f3.calls_for("create")) == 0
            and next(r for r in rep_f3.rows if r.logical_id == "page-1").status == "configured",
            "after confirmed reconcile: reused, zero creates",
        )

        # ---- duplicate create refused at the seam ---------------------
        ex_g = RecordingExecutor()
        wrapper = CheckpointingExecutor(ex_g, store_f, "acc1")
        dup_op = prim.plan_primitives(
            funnel_specs(_mk_doc(), container_native_id="fun-1"),
            location="acc1",
        ).ops[0]
        result_g = wrapper.run(dup_op)
        ok(
            result_g.outcome is prim.Outcome.REFUSED
            and "duplicate create refused" in result_g.note
            and len(ex_g.calls) == 0,
            "checkpointed identity -> duplicate create refused, no transport call",
        )

        # ---- state discipline: publishing is W7's ---------------------
        page_key = cps.CheckpointKey("acc1", "page", "elev-funnel", "page-1")
        cp_page = store_f.read(page_key)
        raised(
            lambda: store_f.set_state(page_key, cps.STATE_PUBLISHED, cp_page.revision),
            cps.InvalidTransitionError,
            "PUBLISHED refused here (record_publish owns it)",
        )
        raised(
            lambda: store_f.set_state(page_key, cps.STATE_VERIFIED, cp_page.revision),
            cps.InvalidTransitionError,
            "VERIFIED refused here (W7 readback owns it)",
        )

        # ---- admin folder: capture request, explicit parentage --------
        store_h = cps.CheckpointStore(os.path.join(td, "h.json"))
        ex_h = RecordingExecutor()
        rep_h = FunnelAdapter("acc1", store_h, ex_h).run(
            _mk_doc(with_folder=True),
            container_native_id="fun-1",
            container_parent_native_id="fold-9",
        )
        alloc_h = rep_h.plan.allocation("af-1")
        ok(
            alloc_h.disposition is prim.Disposition.MISSING_CAPABILITY
            and "smallest missing authorized operation" in alloc_h.capture_request,
            "admin folder create: missing route -> capture request",
        )
        ok(
            all(r.status == "configured" for r in rep_h.rows if r.kind is prim.PrimitiveKind.PAGE),
            "folder missing does not block pages (parent native id supplied)",
        )
        folder_spec = next(
            s for s in rep_h.plan.build_plan.specs if s.logical_id == "af-1"
        )
        page_spec = next(
            s for s in rep_h.plan.build_plan.specs if s.logical_id == "page-1"
        )
        ok(
            folder_spec.nav_ref is None and folder_spec.url_path is None,
            "admin folder never derives nav_ref/url_path",
        )
        ok(
            page_spec.url_path == "/step-1" and page_spec.nav_ref is None,
            "page url_path is explicit contract input, nav never derived",
        )
        ok(
            page_spec.parent_logical_id == "elev-funnel"
            and folder_spec.parent_logical_id is None,
            "parentage is folder->container->page only",
        )

        # ---- definite error: failed row, never a dropped page ---------
        store_i = cps.CheckpointStore(os.path.join(td, "i.json"))
        ex_i = RecordingExecutor(
            {
                ("create", "page-2"): lambda op, ex_: prim.OpResult(
                    prim.Outcome.ERROR, note="platform refused the create"
                )
            }
        )
        rep_i = FunnelAdapter("acc1", store_i, ex_i).run(_mk_doc(), container_native_id="fun-1")
        row_i = next(r for r in rep_i.rows if r.logical_id == "page-2")
        ok(row_i.status == "failed_error", "definite error -> failed_error row")
        ok(
            npage.check_no_dropped_pages(rep_i.plan.doc, rep_i.result) == [],
            "failed create: page still has a result row",
        )
        ok(
            store_i.read(cps.CheckpointKey("acc1", "page", "elev-funnel", "page-2")) is None,
            "failed create: no identity persisted",
        )

    finally:
        shutil.rmtree(td, ignore_errors=True)

    return checks


def main(argv: List[str]) -> int:
    if argv and argv != ["--self-test"]:
        print("usage: funnel_adapter.py [--self-test]", file=sys.stderr)
        return 2
    checks = self_check()
    print(f"funnel_adapter self-check: OK ({checks} assertions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
