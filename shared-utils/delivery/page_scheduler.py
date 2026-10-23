#!/usr/bin/env python3
"""shared-utils/delivery/page_scheduler.py — batch scheduler + page-identity
allocation for arbitrary approved page counts (W7A, stream W7 N-PAGE DELIVERY).

Consumes the REAL upstream modules (never re-implements them):
  * shared-utils/ghl/recipe_transport.py (W2-U2) — every platform mutation is
    dispatched through RecipeRunner; reconcile-before-retry and bounded backoff
    live in the real runner. This scheduler adds the run-level rule on top:
    while a checkpoint operation on a key is open/uncertain, that page is never
    re-dispatched (a blind retry of an uncertain mutation never happens).
  * shared-utils/delivery/checkpoints.py (W4A) — composite identity
    (location, kind, parent, logical_id; never a name alone), read before
    create, immediate persistence of confirmed native IDs, CAS revisions,
    forward-only states PLANNED -> CREATED -> CONFIGURED -> PUBLISHED ->
    VERIFIED.

Contract points (GHL-DELIVERY-SPEC.md "Delivery contract", "Durable execution"):
  * Arbitrary approved page counts. 4/12/20 pages are examples, never caps;
    this module holds no fixed role-slot table. Pages may share a role with
    distinct identity (role is an attribute, logical_id is the identity).
  * Allocate/reconcile identities FIRST for every approved page, THEN content
    operations. URL/action binding is W7B (link_resolution.py) and
    approval-gated publishing is W7C (publishing.py) — saving is never
    publishing, so nothing here publishes, and no report implies a publish.
  * Never silently drop a page: every approved page appears in the report with
    an explicit status and the denominator is the approved count. A blocked or
    failed page never blocks its siblings and never leaves the report.
  * Resume without duplicating: re-running the same plan against the same
    store reuses checkpointed identities (zero create dispatches) and never
    deletes confirmed assets.

Runnable check (offline; the real modules are imported and exercised):
    python3 -I shared-utils/delivery/page_scheduler.py
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent))  # shared-utils/

from delivery import checkpoints as cp  # W4A, real module
from ghl import capability_inventory as ci  # W2A, real module
from ghl import recipe_transport as rt  # W2-U2, real module

# --------------------------------------------------------------------------
# Statuses — explicit, one per honest outcome. Report language, not state
# machine states (the state machine lives in checkpoints.py).
# --------------------------------------------------------------------------
ST_CREATED = "created"                          # create applied, native ID confirmed now
ST_CREATED_UNCONFIRMED = "created-unconfirmed"  # applied, no extractable native ID yet
ST_CREATED_UNVERIFIED = "created-unverified"    # applied per provider, readback unverified
ST_ADOPTED = "adopted"                          # pre-existing approved object, provenance reused
ST_REUSED = "reused"                            # already checkpointed (resume)
ST_CONFIGURED = "configured"
ST_CONFIGURED_UNVERIFIED = "configured-unverified"
ST_ALREADY_CONFIGURED = "already-configured"
ST_BEYOND_SCHEDULER = "beyond-scheduler"        # PUBLISHED/VERIFIED: W7C territory
ST_NOT_CREATED = "not-created"                  # configure skipped: identity not confirmed
ST_BLOCKED_PENDING = "blocked-pending-op"       # prior uncertain op on this key, still open
ST_UNRESOLVED = "unresolved-operator"           # this run left an uncertain outcome
ST_FAILED_DEFINITE = "failed-definite"
ST_FAILED_DENIED = "failed-denied-terminal"
ST_FAILED_RATE_LIMITED = "failed-rate-limited"
ST_FAILED_TRANSIENT = "failed-transient"
ST_READBACK_MISMATCH = "readback-mismatch-operator"
ST_NO_ROUTE = "no-route"                        # real platform restriction, reported as-is


class SchedulerError(ValueError):
    """Plan or scheduling contract violation."""


# --------------------------------------------------------------------------
# Plan: the approved page set. Count is whatever was approved.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class PageSpec:
    """One approved page node. `logical_id` is the stable identity; `name` and
    `role` are attributes only (roles may repeat across pages)."""

    logical_id: str
    name: str = ""
    role: str = "page"
    kind: str = "page"
    parent: Optional[str] = None  # logical_id of the owning node, or None
    slug: str = ""
    target: str = ""  # platform target (container/location native identity)
    resource: str = "page"  # W2A inventory resource for this node's ops
    surface: str = "page"
    create_payload: Dict[str, Any] = field(default_factory=dict)
    content_payload: Dict[str, Any] = field(default_factory=dict)
    native_id: Optional[str] = None  # pre-existing approved object -> adopt

    def key_for(self, location: str) -> "cp.CheckpointKey":
        return cp.CheckpointKey(location, self.kind, self.parent, self.logical_id)


@dataclass(frozen=True)
class ApprovedPlan:
    """The approved page set for one location. `approved_ref` names the
    approval that authorized this page count — the scheduler schedules exactly
    what was approved and never grows or shrinks the set."""

    location: str
    approved_ref: str
    pages: Tuple[PageSpec, ...]

    def __post_init__(self) -> None:
        if not (isinstance(self.location, str) and self.location.strip()):
            raise SchedulerError("plan location is required")
        if not (isinstance(self.approved_ref, str) and self.approved_ref.strip()):
            raise SchedulerError("plan approved_ref is required")
        object.__setattr__(self, "pages", tuple(self.pages))
        if not self.pages:
            raise SchedulerError("plan has no pages")
        seen: Dict[str, int] = {}
        for p in self.pages:
            if not isinstance(p, PageSpec):
                raise SchedulerError(f"not a PageSpec: {p!r}")
            seen[p.logical_id] = seen.get(p.logical_id, 0) + 1
            if not (isinstance(p.target, str) and p.target.strip()):
                raise SchedulerError(f"{p.logical_id}: target is required")
        dupes = sorted(lid for lid, n in seen.items() if n > 1)
        if dupes:
            raise SchedulerError(f"duplicate logical_id would drop pages silently: {dupes}")
        # Reuse the real checkpoint key validation (kind pattern etc.).
        for p in self.pages:
            p.key_for(self.location)
        self.allocation_order()  # parent cycles are invalid identities

    def allocation_order(self) -> List[PageSpec]:
        """Parent-first stable order: a page whose parent is in the plan is
        allocated after it. The only ordering this module imposes."""
        by_id = {p.logical_id: p for p in self.pages}
        out: List[PageSpec] = []
        seen: set = set()

        def emit(p: PageSpec, stack: Tuple[str, ...]) -> None:
            if p.logical_id in seen:
                return
            if p.logical_id in stack:
                raise SchedulerError(f"parent cycle: {' -> '.join(stack + (p.logical_id,))}")
            if p.parent is not None and p.parent in by_id:
                emit(by_id[p.parent], stack + (p.logical_id,))
            seen.add(p.logical_id)
            out.append(p)

        for p in self.pages:
            emit(p, ())
        return out


# --------------------------------------------------------------------------
# Reports: one outcome per approved page, always.
# --------------------------------------------------------------------------
@dataclass
class PageOutcome:
    logical_id: str
    status: str
    state: Optional[str]
    native_id: Optional[str]
    reason: str
    batch: int
    op_ids: List[str] = field(default_factory=list)
    ops: List[Any] = field(default_factory=list)  # rt.StepRecord evidence


@dataclass
class SchedulerReport:
    plan: ApprovedPlan
    phase: str
    outcomes: Dict[str, PageOutcome]
    batches: List[List[str]]

    @property
    def approved_count(self) -> int:
        return len(self.plan.pages)

    def accounted(self) -> bool:
        return set(self.outcomes) == {p.logical_id for p in self.plan.pages}

    def counts_by_status(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for o in self.outcomes.values():
            out[o.status] = out.get(o.status, 0) + 1
        return out

    def counts_by_state(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for o in self.outcomes.values():
            out[o.state or "no-record"] = out.get(o.state or "no-record", 0) + 1
        return out

    def operator_report(self) -> str:
        lines = [
            f"phase={self.phase} location={self.plan.location} "
            f"approved_ref={self.plan.approved_ref} approved={self.approved_count} "
            f"accounted={len(self.outcomes)}"
        ]
        for p in self.plan.allocation_order():
            o = self.outcomes[p.logical_id]
            lines.append(
                f"  {p.logical_id} [{p.role}] batch={o.batch} status={o.status} "
                f"state={o.state} native_id={o.native_id} reason={o.reason}"
            )
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Result capture: the runner's StepRecord carries route/location/target/
# readback evidence but not the response body data, so executors are wrapped
# to retain the last AttemptResult for native-ID extraction. The real runner
# still performs every dispatch.
# --------------------------------------------------------------------------
class _Capture:
    def __init__(self) -> None:
        self.last: Optional[rt.AttemptResult] = None


class _CapturingExecutor:
    def __init__(self, inner: Any, capture: _Capture):
        self._inner = inner
        self._capture = capture

    def dispatch(self, cap: "ci.Capability", req: "rt.OperationRequest") -> "rt.AttemptResult":
        out = self._inner.dispatch(cap, req)
        self._capture.last = out
        return out


# --------------------------------------------------------------------------
# The scheduler
# --------------------------------------------------------------------------
class PageBatchScheduler:
    """Batch scheduler over the real recipe transport and checkpoint store.

    Identity allocation runs first for the whole approved set; content
    operations run second. Dispatch happens in deterministic parent-first
    batches (`batch_size` groups dispatches only — it never changes counts,
    ordering guarantees or per-page outcomes)."""

    def __init__(
        self,
        store: "cp.CheckpointStore",
        executors: Dict["ci.Transport", Any],
        *,
        batch_size: int = 8,
        probe: Optional[Callable[..., Tuple["rt.ReconcileVerdict", str]]] = None,
        sleep: Callable[[float], None] = time.sleep,
        id_key: str = "id",
    ):
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
            raise SchedulerError("batch_size must be a positive int")
        self._store = store
        self._capture = _Capture()
        wrapped = {t: _CapturingExecutor(ex, self._capture) for t, ex in executors.items()}
        self._runner = rt.RecipeRunner(wrapped, probe=probe, sleep=sleep)
        self._batch_size = batch_size
        self._id_key = id_key
        self._op_seq = 0

    # -- public API --------------------------------------------------------

    def run(self, plan: ApprovedPlan) -> SchedulerReport:
        """Allocate/reconcile identities for EVERY approved page first, then
        content/configure. Returns one outcome per approved page."""
        alloc = self.allocate_identities(plan)
        conf = self.configure_pages(plan)
        outcomes: Dict[str, PageOutcome] = {}
        for lid, a in alloc.outcomes.items():
            c = conf.outcomes.get(lid)
            # A skipped configure ("not-created"/"blocked-pending-op") hides the
            # deeper truth from phase 1 — the allocation outcome is authoritative
            # there (failure, unresolved or unconfirmed identity).
            if c is not None and c.status not in (ST_NOT_CREATED, ST_BLOCKED_PENDING):
                outcomes[lid] = c
            else:
                outcomes[lid] = a
        return SchedulerReport(plan, "allocate+configure", outcomes, alloc.batches + conf.batches)

    def allocate_identities(self, plan: ApprovedPlan) -> SchedulerReport:
        """Phase 1: page-identity allocation for the whole approved set."""
        outcomes: Dict[str, PageOutcome] = {}
        batches: List[List[str]] = []
        for bi, chunk in enumerate(self._chunks(plan.allocation_order())):
            done: List[str] = []
            for page in chunk:
                outcomes[page.logical_id] = self._allocate_one(plan, page, bi)
                done.append(page.logical_id)
            batches.append(done)
        return SchedulerReport(plan, "allocate", outcomes, batches)

    def configure_pages(self, plan: ApprovedPlan) -> SchedulerReport:
        """Phase 2: content operations for pages whose identity is confirmed."""
        outcomes: Dict[str, PageOutcome] = {}
        batches: List[List[str]] = []
        for bi, chunk in enumerate(self._chunks(plan.allocation_order())):
            done: List[str] = []
            for page in chunk:
                outcomes[page.logical_id] = self._configure_one(plan, page, bi)
                done.append(page.logical_id)
            batches.append(done)
        return SchedulerReport(plan, "configure", outcomes, batches)

    def counts(self, plan: ApprovedPlan) -> Dict[str, int]:
        """Per-state counts with the approved denominator (W11AC board
        events: code built / configured-object / published counts stay
        separate — this reports configured-object states only)."""
        out: Dict[str, int] = {"approved": len(plan.pages)}
        for p in plan.pages:
            cp_rec = self._store.read(p.key_for(plan.location))
            state = cp_rec.state if cp_rec is not None else "no-record"
            out[state] = out.get(state, 0) + 1
        return out

    # -- phase 1: identity allocation ---------------------------------------

    def _allocate_one(self, plan: ApprovedPlan, page: PageSpec, batch: int) -> PageOutcome:
        key = page.key_for(plan.location)
        decision, existing = self._store.plan_create(key)

        if decision == "blocked-pending":
            return PageOutcome(
                page.logical_id, ST_BLOCKED_PENDING,
                existing.state if existing else None,
                existing.native_id if existing else None,
                "an operation on this identity lacks a definite outcome; "
                "reconcile before any retry",
                batch,
            )
        if decision == "reuse":
            return PageOutcome(
                page.logical_id, ST_REUSED, existing.state, existing.native_id,
                "already checkpointed; resume must never duplicate", batch,
            )
        if page.native_id:
            # Pre-existing approved object: adopt, never create.
            adopted = self._store.adopt(
                key, native_id=page.native_id,
                name=page.name or page.logical_id, slug=page.slug,
            )
            return PageOutcome(
                page.logical_id, ST_ADOPTED, adopted.state, adopted.native_id,
                f"provenance={adopted.provenance}", batch,
            )

        # Fresh create through the real recipe transport.
        op_id = self._next_op_id(key, "create")
        self._store.begin_op(key, op_id, action="create")
        req = rt.OperationRequest(
            op_class=ci.OpClass.CREATE,
            location=plan.location,
            target=page.target,
            resource=page.resource,
            surface=page.surface,
            payload=dict(page.create_payload),
        )
        self._capture.last = None
        try:
            step = self._runner.run_step(req)
        except rt.RouteDenied as exc:
            self._store.reconcile_op(op_id, outcome="not_found")
            return PageOutcome(
                page.logical_id, ST_FAILED_DENIED, None, None,
                "route denied -- terminal; never switch tools to bypass a denial",
                batch, [op_id], [exc.record] if exc.record else [],
            )
        except (rt.TransportUnavailable, rt.CredentialError, ci.UnsupportedOperation) as exc:
            self._store.reconcile_op(op_id, outcome="not_found")
            return PageOutcome(
                page.logical_id, ST_NO_ROUTE, None, None, str(exc), batch, [op_id],
            )
        out = self._capture.last
        native_id = self._extract_native_id(out)

        if step.final in (rt.FinalStatus.OK, rt.FinalStatus.OK_RECONCILED):
            if native_id:
                self._store.complete_op(op_id, native_id=native_id)  # persists immediately
                rec = self._store.read(key)
                return PageOutcome(
                    page.logical_id, ST_CREATED, rec.state, rec.native_id,
                    "native ID persisted immediately", batch, [op_id], [step],
                )
            self._store.record_create(key, name=page.name or page.logical_id, slug=page.slug,
                                      _resolving_op_id=op_id)
            self._store.complete_op(op_id)
            rec = self._store.read(key)
            return PageOutcome(
                page.logical_id, ST_CREATED_UNCONFIRMED, rec.state, rec.native_id,
                "applied but response carried no native ID; record stays PLANNED "
                "until confirm_native",
                batch, [op_id], [step],
            )
        if step.final is rt.FinalStatus.OK_UNVERIFIED:
            if native_id:
                self._store.complete_op(op_id, native_id=native_id)
            else:
                self._store.record_create(key, name=page.name or page.logical_id, slug=page.slug,
                                          _resolving_op_id=op_id)
                self._store.complete_op(op_id)
            rec = self._store.read(key)
            return PageOutcome(
                page.logical_id, ST_CREATED_UNVERIFIED, rec.state, rec.native_id,
                "provider reported applied; readback unverified", batch, [op_id], [step],
            )
        if step.final is rt.FinalStatus.UNRESOLVED:
            # Op stays open on purpose: the next run must see blocked-pending,
            # never re-dispatch. Reconciliation is the operator/W4C surface.
            return PageOutcome(
                page.logical_id, ST_UNRESOLVED, None, None,
                "uncertain outcome, reconcile inconclusive -- operator decision "
                "required; retry refused until a definite outcome",
                batch, [op_id], [step],
            )
        if step.final is rt.FinalStatus.FAILED_READBACK_MISMATCH:
            # The write claims success but readback disagrees: existence is
            # unknown, so the op lock is KEPT (ambiguous must stay refused).
            return PageOutcome(
                page.logical_id, ST_READBACK_MISMATCH, None, None,
                "readback mismatch -- outcome ambiguous, op left open for "
                "definite reconciliation",
                batch, [op_id], [step],
            )
        # Definite no-effect failures: release the lock (nothing was created).
        self._store.reconcile_op(op_id, outcome="not_found")
        status = {
            rt.FinalStatus.FAILED_DEFINITE: ST_FAILED_DEFINITE,
            rt.FinalStatus.FAILED_DENIED: ST_FAILED_DENIED,
            rt.FinalStatus.FAILED_RATE_LIMITED: ST_FAILED_RATE_LIMITED,
            rt.FinalStatus.FAILED_TRANSIENT: ST_FAILED_TRANSIENT,
        }.get(step.final, ST_FAILED_DEFINITE)
        return PageOutcome(
            page.logical_id, status, None, None,
            f"create not applied ({step.final.value}); no blind retry", batch, [op_id], [step],
        )

    # -- phase 2: content/configuration ------------------------------------

    def _configure_one(self, plan: ApprovedPlan, page: PageSpec, batch: int) -> PageOutcome:
        key = page.key_for(plan.location)
        decision, existing = self._store.plan_create(key)
        if decision == "blocked-pending":
            return PageOutcome(
                page.logical_id, ST_BLOCKED_PENDING,
                existing.state if existing else None,
                existing.native_id if existing else None,
                "an operation on this identity lacks a definite outcome", batch,
            )
        if decision == "create" or existing is None:
            return PageOutcome(
                page.logical_id, ST_NOT_CREATED, None, None,
                "no confirmed identity to configure", batch,
            )
        if existing.state in (cp.STATE_PUBLISHED, cp.STATE_VERIFIED):
            return PageOutcome(
                page.logical_id, ST_BEYOND_SCHEDULER, existing.state, existing.native_id,
                "publishing/verification are W7C; saving is never publishing", batch,
            )
        if existing.state == cp.STATE_CONFIGURED:
            return PageOutcome(
                page.logical_id, ST_ALREADY_CONFIGURED, existing.state, existing.native_id,
                "content already configured", batch,
            )
        if existing.state != cp.STATE_CREATED:
            return PageOutcome(
                page.logical_id, ST_NOT_CREATED, existing.state, existing.native_id,
                f"state {existing.state}: identity not confirmed as created", batch,
            )

        op_id = self._next_op_id(key, "configure")
        self._store.begin_op(key, op_id, action="configure")
        req = rt.OperationRequest(
            op_class=ci.OpClass.EDIT,
            location=plan.location,
            target=page.target,
            resource=page.resource,
            surface=page.surface,
            payload=dict(page.content_payload),
        )
        self._capture.last = None
        try:
            step = self._runner.run_step(req)
        except rt.RouteDenied as exc:
            self._store.reconcile_op(op_id, outcome="not_found")
            return PageOutcome(
                page.logical_id, ST_FAILED_DENIED, existing.state, existing.native_id,
                "route denied -- terminal; never switch tools to bypass a denial",
                batch, [op_id], [exc.record] if exc.record else [],
            )
        except (rt.TransportUnavailable, rt.CredentialError, ci.UnsupportedOperation) as exc:
            self._store.reconcile_op(op_id, outcome="not_found")
            return PageOutcome(
                page.logical_id, ST_NO_ROUTE, existing.state, existing.native_id,
                str(exc), batch, [op_id],
            )

        if step.final in (rt.FinalStatus.OK, rt.FinalStatus.OK_RECONCILED):
            self._store.complete_op(op_id)
            rec = self._store.set_state(key, cp.STATE_CONFIGURED, existing.revision)
            return PageOutcome(
                page.logical_id, ST_CONFIGURED, rec.state, rec.native_id,
                "content applied", batch, [op_id], [step],
            )
        if step.final is rt.FinalStatus.OK_UNVERIFIED:
            # Applied per provider but unverified: state does NOT advance.
            self._store.complete_op(op_id)
            rec = self._store.read(key)
            return PageOutcome(
                page.logical_id, ST_CONFIGURED_UNVERIFIED, rec.state, rec.native_id,
                "provider reported applied; readback unverified -- state held at "
                f"{rec.state}",
                batch, [op_id], [step],
            )
        if step.final is rt.FinalStatus.UNRESOLVED:
            return PageOutcome(
                page.logical_id, ST_UNRESOLVED, existing.state, existing.native_id,
                "uncertain outcome; op left open, retry refused until reconciled",
                batch, [op_id], [step],
            )
        if step.final is rt.FinalStatus.FAILED_READBACK_MISMATCH:
            return PageOutcome(
                page.logical_id, ST_READBACK_MISMATCH, existing.state, existing.native_id,
                "readback mismatch -- outcome ambiguous, op left open", batch, [op_id], [step],
            )
        self._store.reconcile_op(op_id, outcome="not_found")
        status = {
            rt.FinalStatus.FAILED_DEFINITE: ST_FAILED_DEFINITE,
            rt.FinalStatus.FAILED_DENIED: ST_FAILED_DENIED,
            rt.FinalStatus.FAILED_RATE_LIMITED: ST_FAILED_RATE_LIMITED,
            rt.FinalStatus.FAILED_TRANSIENT: ST_FAILED_TRANSIENT,
        }.get(step.final, ST_FAILED_DEFINITE)
        return PageOutcome(
            page.logical_id, status, existing.state, existing.native_id,
            f"content not applied ({step.final.value})", batch, [op_id], [step],
        )

    # -- internals ----------------------------------------------------------

    def _chunks(self, pages: Sequence[PageSpec]) -> List[List[PageSpec]]:
        return [list(pages[i:i + self._batch_size]) for i in range(0, len(pages), self._batch_size)]

    def _next_op_id(self, key: "cp.CheckpointKey", action: str) -> str:
        self._op_seq += 1
        return f"page-scheduler:{action}:{key.token()}:{time.time_ns()}:{self._op_seq}"

    def _extract_native_id(self, out: Optional[rt.AttemptResult]) -> Optional[str]:
        if out is None or not isinstance(out.data, dict):
            return None
        value = out.data.get(self._id_key)
        return value if isinstance(value, str) and value.strip() else None


# --------------------------------------------------------------------------
# Runnable check — offline, assert-based, real modules throughout.
# --------------------------------------------------------------------------
def _self_check() -> int:
    import tempfile

    n_asserts = 0

    def ok(cond: bool, what: str) -> None:
        nonlocal n_asserts
        n_asserts += 1
        if not cond:
            raise AssertionError(f"#{n_asserts} FAILED: {what}")

    def raised(fn, exc_type, what: str) -> None:
        nonlocal n_asserts
        n_asserts += 1
        try:
            fn()
        except exc_type:
            return
        except Exception as other:  # noqa: BLE001
            raise AssertionError(f"#{n_asserts} FAILED: {what}: wrong exception {other!r}")
        raise AssertionError(f"#{n_asserts} FAILED: {what}: no {exc_type.__name__} raised")

    def fresh_store() -> "cp.CheckpointStore":
        fd, path = tempfile.mkstemp(prefix="lane-W7A-U1-", suffix=".json", dir=tempfile.gettempdir())
        import os
        os.close(fd)
        os.unlink(path)  # CheckpointStore creates on first save
        return cp.CheckpointStore(path)

    def pages(n: int, **over) -> List[PageSpec]:
        return [
            PageSpec(logical_id=f"p{i:02d}", name=f"Page {i}", target="loc-1",
                     create_payload={"n": i}, content_payload={"body": i}, **over)
            for i in range(1, n + 1)
        ]

    def ok_result(nid: str) -> rt.AttemptResult:
        return rt.AttemptResult("ok", http_status=200, body='{"id":"%s"}' % nid,
                                data={"id": nid}, sent=True)

    # ---- A. plan validation --------------------------------------------
    raised(lambda: ApprovedPlan("loc", "appr-1", ()), SchedulerError, "empty plan refused")
    raised(lambda: ApprovedPlan("", "appr-1", tuple(pages(1))), SchedulerError, "empty location")
    raised(lambda: ApprovedPlan("loc", "", tuple(pages(1))), SchedulerError, "empty approved_ref")
    dupes = (PageSpec("p1", target="t"), PageSpec("p1", target="t"))
    raised(lambda: ApprovedPlan("loc", "appr-1", dupes), SchedulerError,
           "duplicate logical_id refused (silent-drop prevention)")
    raised(lambda: ApprovedPlan("loc", "appr-1", (PageSpec("p1", target=""),)), SchedulerError,
           "page without target refused")
    raised(lambda: ApprovedPlan("loc", "appr-1", (PageSpec("p1", target="t", kind="BAD-KIND"),)),
           cp.CheckpointError, "real CheckpointKey validation reused")
    cyc = (PageSpec("a", target="t", parent="b"), PageSpec("b", target="t", parent="a"))
    raised(lambda: ApprovedPlan("loc", "appr-1", cyc), SchedulerError, "parent cycle refused")

    # ---- B. arbitrary approved counts: 1 / 4 / 12 / 20 ------------------
    for n in (1, 4, 12, 20):
        store = fresh_store()
        log: List[str] = []
        ex = rt.ScriptedExecutor([ok_result(f"nat-{i}") for i in range(n)] +
                                 [ok_result("ignored") for _ in range(n)], log=log)
        sched = PageBatchScheduler(store, {ci.Transport.MANAGED_BROWSER: ex})
        plan = ApprovedPlan("loc", f"appr-{n}", tuple(pages(n)))
        rep = sched.run(plan)
        ok(rep.approved_count == n, f"n={n}: denominator is the approved count")
        ok(rep.accounted(), f"n={n}: every approved page has exactly one outcome")
        ok(len(rep.outcomes) == n, f"n={n}: no silent drops, no extras")
        ok(all(rep.outcomes[p.logical_id].status == ST_CONFIGURED for p in plan.pages),
           f"n={n}: all pages created then configured")
        ok(len(store.list_checkpoints()) == n, f"n={n}: n identities checkpointed")
        ok(all(store.read(p.key_for("loc")).state == cp.STATE_CONFIGURED for p in plan.pages),
           f"n={n}: states advanced to CONFIGURED")
        ok(len(log) == 2 * n, f"n={n}: exactly n create + n configure dispatches")
        ok(sched.counts(plan)["approved"] == n, f"n={n}: counts carry approved denominator")
        ok(sched.counts(plan).get(cp.STATE_CONFIGURED) == n, f"n={n}: counts by state honest")

    # ---- C. identity-first ordering + batching -------------------------
    store = fresh_store()
    log = []
    ex = rt.ScriptedExecutor([ok_result(f"nat-{i}") for i in (2, 1, 3)] +
                             [ok_result("x") for _ in range(3)], log=log)
    sched = PageBatchScheduler(store, {ci.Transport.MANAGED_BROWSER: ex}, batch_size=2)
    # child declared before its parent: allocation must still go parent-first
    ps = [PageSpec("child", target="t", parent="parent", create_payload={"i": 1}),
          PageSpec("parent", target="t", create_payload={"i": 2}),
          PageSpec("solo", target="t", create_payload={"i": 3})]
    plan = ApprovedPlan("loc", "appr-order", tuple(ps))
    rep = sched.run(plan)
    create_log = [ln for ln in log if "dispatch:" in ln][:3]
    ok(len(create_log) == 3, "C: three create dispatches")
    ok(rep.batches[0] == ["parent", "child"], "C: batch 1 is parent-first (parent, child)")
    ok(rep.batches[1] == ["solo"], "C: batch 2 holds the remainder")
    ok(store.read(ps[1].key_for("loc")).native_id == "nat-2",
       "C: parent created first (its payload dispatched first)")
    alloc_only = sched.allocate_identities(ApprovedPlan("loc", "appr-order", tuple(ps)))
    ok(all(o.status == ST_REUSED for o in alloc_only.outcomes.values()),
       "C: re-allocation reuses, never re-creates")

    # ---- D. resume: zero dispatches, no duplicates ---------------------
    log = []
    ex_none = rt.ScriptedExecutor([], log=log)  # any dispatch would raise
    sched2 = PageBatchScheduler(store, {ci.Transport.MANAGED_BROWSER: ex_none})
    rep2 = sched2.run(ApprovedPlan("loc", "appr-order", tuple(ps)))
    ok(log == [], "D: resume of a configured plan dispatches nothing")
    ok(all(o.status in (ST_ALREADY_CONFIGURED, ST_REUSED) for o in rep2.outcomes.values()),
       "D: resume statuses explicit")
    ok(len(store.list_checkpoints()) == 3, "D: resume duplicates nothing")

    # ---- E. adopt pre-existing identity --------------------------------
    store = fresh_store()
    log = []
    ex = rt.ScriptedExecutor([ok_result("x")], log=log)  # configure only
    sched = PageBatchScheduler(store, {ci.Transport.MANAGED_BROWSER: ex})
    plan = ApprovedPlan("loc", "appr-adopt", (PageSpec("live", target="t", native_id="nat-live"),))
    rep = sched.allocate_identities(plan)
    o = rep.outcomes["live"]
    ok(o.status == ST_ADOPTED and o.native_id == "nat-live", "E: pre-existing object adopted")
    ok(log == [], "E: adoption dispatches nothing")
    ok(store.read(plan.pages[0].key_for("loc")).provenance == cp.PROVENANCE_REUSED,
       "E: provenance=reused, distinct from new scratch")
    rep = sched.run(plan)
    ok(rep.outcomes["live"].status == ST_CONFIGURED, "E: adopted page configures normally")

    # ---- F. uncertain create: no blind retry, blocked until reconciled --
    store = fresh_store()
    log = []
    ex = rt.ScriptedExecutor([rt.AttemptResult("timeout", sent=None)], log=log)
    sched = PageBatchScheduler(store, {ci.Transport.MANAGED_BROWSER: ex})
    plan = ApprovedPlan("loc", "appr-unc", tuple(pages(1)))
    rep = sched.allocate_identities(plan)
    o = rep.outcomes["p01"]
    ok(o.status == ST_UNRESOLVED, "F: uncertain create -> unresolved-operator")
    ok(len(o.op_ids) == 1, "F: op id surfaced for reconciliation")
    op_id = o.op_ids[0]
    ok(store.resolve_op(op_id)["status"] == cp.OP_OPEN, "F: op left open (uncertain)")
    # second run must NOT re-dispatch the create
    log = []
    ex = rt.ScriptedExecutor([], log=log)
    sched = PageBatchScheduler(store, {ci.Transport.MANAGED_BROWSER: ex})
    rep = sched.allocate_identities(plan)
    ok(rep.outcomes["p01"].status == ST_BLOCKED_PENDING, "F: rerun sees blocked-pending")
    ok(log == [], "F: zero dispatches while an uncertain op is open")
    # ambiguous reconciliation is refused and keeps the lock
    raised(lambda: store.reconcile_op(op_id, outcome="ambiguous"), cp.AmbiguousMatchError,
           "F: ambiguous reconciliation refused")
    ok(store.resolve_op(op_id)["status"] == cp.OP_OPEN, "F: lock kept after ambiguous")
    # definite reconciliation (confirmed) frees the path
    store.reconcile_op(op_id, outcome="confirmed", native_id="nat-u")
    ok(store.read(plan.pages[0].key_for("loc")).native_id == "nat-u",
       "F: confirmed native ID persisted immediately")
    log = []
    ex = rt.ScriptedExecutor([ok_result("x")], log=log)  # configure only
    sched = PageBatchScheduler(store, {ci.Transport.MANAGED_BROWSER: ex})
    rep = sched.run(plan)
    ok(rep.outcomes["p01"].status == ST_CONFIGURED, "F: reconciled page continues to configured")
    ok(len(log) == 1, "F: only the configure dispatch ran (no re-create)")

    # ---- G. reconcile not_found -> fresh attempt allowed ---------------
    store = fresh_store()
    log = []
    ex = rt.ScriptedExecutor([rt.AttemptResult("timeout", sent=None)], log=log)
    sched = PageBatchScheduler(store, {ci.Transport.MANAGED_BROWSER: ex})
    plan = ApprovedPlan("loc", "appr-nf", tuple(pages(1)))
    rep = sched.allocate_identities(plan)
    op_id = rep.outcomes["p01"].op_ids[0]
    store.reconcile_op(op_id, outcome="not_found")
    log = []
    ex = rt.ScriptedExecutor([ok_result("nat-g"), ok_result("x")], log=log)
    sched = PageBatchScheduler(store, {ci.Transport.MANAGED_BROWSER: ex})
    rep = sched.run(plan)
    ok(rep.outcomes["p01"].status == ST_CONFIGURED, "G: proven-absent create retried once and lands")
    ok(len(log) == 2, "G: exactly one create + one configure after release")

    # ---- H. runner-level reconcile-before-retry (real transport rules) --
    store = fresh_store()
    log: List[str] = []
    ex = rt.ScriptedExecutor(
        [rt.AttemptResult("timeout", sent=None), ok_result("nat-h")], log=log)
    probe = rt.scripted_probe(log, [(rt.ReconcileVerdict.NOT_APPLIED, "absent on readback")])
    sched = PageBatchScheduler(store, {ci.Transport.MANAGED_BROWSER: ex}, probe=probe)
    plan = ApprovedPlan("loc", "appr-h", tuple(pages(1)))
    rep = sched.allocate_identities(plan)
    ok(rep.outcomes["p01"].status == ST_CREATED, "H: bounded retry after proven-absent succeeds")
    ok(len([ln for ln in log if ln.startswith("dispatch:")]) == 2, "H: two dispatches, one retry")
    ok(any(ln == "probe:reconcile" for ln in log), "H: reconcile probe ran before the retry")

    # ---- I. one page failing never drops its siblings ------------------
    store = fresh_store()
    log = []
    results = [ok_result("nat-1"), ok_result("nat-2"),
               rt.AttemptResult("http_error", http_status=400, body="rejected"),
               ok_result("nat-4"), ok_result("nat-5")] + [ok_result("x") for _ in range(4)]
    ex = rt.ScriptedExecutor(results, log=log)
    sched = PageBatchScheduler(store, {ci.Transport.MANAGED_BROWSER: ex})
    plan = ApprovedPlan("loc", "appr-mix", tuple(pages(5)))
    rep = sched.run(plan)
    ok(rep.accounted() and len(rep.outcomes) == 5, "I: all 5 approved pages reported")
    ok(rep.outcomes["p03"].status == ST_FAILED_DEFINITE, "I: failing page explicit")
    ok(rep.outcomes["p03"].state is None, "I: failed create leaves no record")
    ok(all(rep.outcomes[f"p0{i}"].status == ST_CONFIGURED for i in (1, 2, 4, 5)),
       "I: siblings unaffected by the failure")
    ok(len(store.list_checkpoints()) == 4, "I: four real identities, five accounted")

    # ---- J. denial is terminal for the route ---------------------------
    store = fresh_store()
    log = []
    ex = rt.ScriptedExecutor([rt.AttemptResult("http_error", http_status=403, body="denied")],
                             log=log)
    sched = PageBatchScheduler(store, {ci.Transport.MANAGED_BROWSER: ex})
    plan = ApprovedPlan("loc", "appr-den", tuple(pages(1)))
    rep = sched.allocate_identities(plan)
    ok(rep.outcomes["p01"].status == ST_FAILED_DENIED, "J: denial reported terminal")
    ok(len(log) == 1, "J: exactly one dispatch -- never switched tools after a denial")

    # ---- K. saving is never publishing ---------------------------------
    store = fresh_store()
    log = []
    ex = rt.ScriptedExecutor([ok_result(f"nat-{i}") for i in range(1, 5)] +
                             [ok_result("x") for _ in range(4)], log=log)
    sched = PageBatchScheduler(store, {ci.Transport.MANAGED_BROWSER: ex})
    plan = ApprovedPlan("loc", "appr-pub", tuple(pages(4)))
    rep = sched.run(plan)
    ok(not hasattr(PageBatchScheduler, "publish"), "K: scheduler exposes no publish API")
    for p in plan.pages:
        rec = store.read(p.key_for("loc"))
        ok(rec.published_url is None and rec.state != cp.STATE_PUBLISHED,
           f"K: {p.logical_id} not published by scheduling")

    # ---- L. create applied without extractable native ID ----------------
    store = fresh_store()
    log = []
    ex = rt.ScriptedExecutor([rt.AttemptResult("ok", http_status=200, body="{}", data={},
                                               sent=True)], log=log)
    sched = PageBatchScheduler(store, {ci.Transport.MANAGED_BROWSER: ex})
    plan = ApprovedPlan("loc", "appr-noid", tuple(pages(1)))
    rep = sched.allocate_identities(plan)
    ok(rep.outcomes["p01"].status == ST_CREATED_UNCONFIRMED,
       "L: applied-without-ID reported honestly")
    rec = store.read(plan.pages[0].key_for("loc"))
    ok(rec.state == cp.STATE_PLANNED and rec.native_id is None,
       "L: record stays PLANNED until confirm_native")
    log = []
    ex = rt.ScriptedExecutor([], log=log)
    sched = PageBatchScheduler(store, {ci.Transport.MANAGED_BROWSER: ex})
    rep = sched.configure_pages(plan)
    ok(rep.outcomes["p01"].status == ST_NOT_CREATED, "L: unconfirmed identity is not configured")
    ok(log == [], "L: no dispatch without a confirmed identity")

    print(f"self-check OK ({n_asserts} assertions)")
    return 0


if __name__ == "__main__":
    sys.exit(_self_check())
