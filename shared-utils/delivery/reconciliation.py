"""
shared-utils/delivery/reconciliation.py — restart/reconciliation and safe
partial-failure handling for the GHL delivery stream (W4C, stream W4 DURABLE
EXECUTION).

One writer for this file: assignment W4C. Contract source:
GHL-DELIVERY-SPEC.md "Durable execution (W4)" and "Operation choice (W2)"
("reconcile uncertain results before retry"). Built on W4A's
shared-utils/delivery/checkpoints.py (its own single-writer file; this module
consumes only its public API).

What this module guarantees:

1. Durable intent BEFORE the uncertain call. `attempt()` records the PLANNED
   checkpoint (name/slug) and opens a pending op before the platform write
   runs. A crash mid-write leaves both behind: the intent record plus the
   unresolved op are the restart surface.
2. Uncertain writes are reconciled against AUTHORITATIVE state before any
   retry. `classify()` never guesses: exactly one candidate matching EVERY
   recorded identity attribute (name AND slug) -> confirmed; empty scope ->
   not_found; anything else (multiple exact matches, partial matches,
   name-only evidence, out-of-scope-only candidates, a failing lookup, a
   missing intent record) -> ambiguous/lookup-failed, the op lock stays, and
   retry stays refused until a definite outcome is proven.
3. Resume never duplicates pages, forms or products. `attempt()` on an
   already-confirmed key returns the record WITHOUT calling the write; a
   PLANNED intent is confirmed in place (never re-created); an object found
   by authoritative read before create is ADOPTED as PROVENANCE_REUSED, never
   created again.
4. Names are never identity. Confirmation requires name AND slug recorded on
   the intent and both exactly matched. Name-only evidence is rejected even
   when unique. A definite outcome may also be supplied directly
   (recovered write response, human confirmation) as an explicit native_id.
5. Partial failure stays safe. A write that raises leaves its op open and its
   intent durable; the next attempt is refused until reconciliation; an
   ambiguous or failed reconciliation keeps the lock (fail closed, never
   "probably fine").
6. No deletes. This module has no delete path at all. Successful assets are
   never removed on resume; dropping pure scratch stays in checkpoints'
   `drop_unconfirmed`.

PROVISIONAL integration seam (spec: authoritative state comes from the W2
operation catalog / read adapters, not yet at this base): the authoritative
reader is injected as `lookup(key) -> Iterable[PlatformObject]`. Lookup
failures are treated as UNKNOWN state (lock kept), never as absence.

Import pattern (from any script in the repo):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared-utils"))
    from delivery.reconciliation import Reconciler, DesiredObject

(shared-utils/delivery needs no __init__.py; it imports as a namespace
package. Run the assert-based self-check:

    python3 -I shared-utils/delivery/reconciliation.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

_SHARED_UTILS = Path(__file__).resolve().parent.parent
if str(_SHARED_UTILS) not in sys.path:
    sys.path.insert(0, str(_SHARED_UTILS))

from delivery.checkpoints import (  # noqa: E402 - path bootstrap above
    OP_DONE,
    OP_OPEN,
    OP_UNCERTAIN,
    PROVENANCE_REUSED,
    PROVENANCE_NEW_SCRATCH,
    STATE_PLANNED,
    Checkpoint,
    CheckpointError,
    CheckpointKey,
    CheckpointStore,
    PendingOperationError,
)

# --------------------------------------------------------------------------
# Outcomes. Ambiguous and lookup-failed are NOT resolutions: they leave the
# pending op unresolved on purpose so retry stays refused (fail closed).
# --------------------------------------------------------------------------
OUTCOME_CONFIRMED = "confirmed"
OUTCOME_NOT_FOUND = "not_found"
OUTCOME_AMBIGUOUS = "ambiguous"
OUTCOME_LOOKUP_FAILED = "lookup-failed"

# Plan actions (restart / resume surface).
ACTION_REUSE = "reuse"                    # confirmed: never write again
ACTION_RESUME_CREATE = "resume-create"    # PLANNED intent: attempt allowed
ACTION_CREATE_NEW = "create-new"          # no record, authoritative state clear
ACTION_ADOPTED = "adopted-reused"         # authoritative object adopted, not created
ACTION_BLOCKED = "blocked-pending"        # reconcile first
ACTION_AMBIGUOUS = "ambiguous-refused"    # reconcile refused; human/stronger evidence needed
ACTION_LOOKUP_FAILED = "lookup-failed"    # authoritative state unreachable


class ReconciliationError(CheckpointError):
    """Reconciliation contract violation (bad lookup data, no native ID from a
    create write, etc.)."""


def _require_text(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReconciliationError(f"{what} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class PlatformObject:
    """One object read from authoritative platform state.

    Scope fields (location/kind/parent) are optional: when present they must
    match the checkpoint key's or the object is out of scope and excluded.
    `native_id` is the platform's own identity. `name`/`slug` are attributes,
    never identity on their own.
    """

    native_id: str
    name: Optional[str] = None
    slug: Optional[str] = None
    parent: Optional[str] = None
    location: Optional[str] = None
    kind: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "native_id", _require_text(self.native_id, "native_id"))
        for attr in ("name", "slug", "parent", "location", "kind"):
            value = getattr(self, attr)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ReconciliationError(f"{attr} must be None or a non-empty string")

    def in_scope(self, key: CheckpointKey) -> bool:
        """True unless a declared scope field contradicts the key. A None
        field is 'unspecified', trusting the injected lookup's scoping."""
        if self.location is not None and self.location != key.location:
            return False
        if self.kind is not None and self.kind != key.kind:
            return False
        if self.parent is not None and self.parent != key.parent:
            return False
        return True


@dataclass(frozen=True)
class Classification:
    """Result of matching one key's expected identity against authoritative
    state. `matched` lists candidate native_ids considered."""

    outcome: str
    native_id: Optional[str]
    matched: Tuple[str, ...]
    evidence: str


@dataclass(frozen=True)
class OpReconciliation:
    """What happened to one pending op during reconciliation."""

    op_id: str
    key_token: str
    outcome: str
    native_id: Optional[str]
    evidence: str


@dataclass(frozen=True)
class PlanItem:
    """Resume decision for one desired object."""

    key: CheckpointKey
    action: str
    native_id: Optional[str]
    provenance: Optional[str]
    detail: str


@dataclass(frozen=True)
class DesiredObject:
    """One object a run wants to exist. name+slug are the identity evidence
    used for authoritative matching; both are required to CONFIRM anything."""

    key: CheckpointKey
    name: str
    slug: str

    def __post_init__(self) -> None:
        _require_text(self.name, "name")
        _require_text(self.slug, "slug")


@dataclass
class RestartReport:
    reconciliations: List[OpReconciliation] = field(default_factory=list)
    items: List[PlanItem] = field(default_factory=list)


class Reconciler:
    """Restart/reconciliation engine over a W4A CheckpointStore.

    `lookup` is the authoritative reader: given a key it returns the platform
    objects living in that (location, kind, parent) scope. It is injected
    because the W2 read adapters are not at this base; anything it raises is
    treated as UNKNOWN state, never as absence.
    """

    def __init__(
        self,
        store: CheckpointStore,
        lookup: Callable[[CheckpointKey], Iterable[PlatformObject]],
    ) -> None:
        if not isinstance(store, CheckpointStore):
            raise ReconciliationError("store must be a CheckpointStore")
        if not callable(lookup):
            raise ReconciliationError("lookup must be callable")
        self.store = store
        self.lookup = lookup

    # ---- authoritative matching ----------------------------------------
    def classify(self, key: CheckpointKey, name: str, slug: str) -> Classification:
        """Match one intended identity against authoritative state. Never
        guesses: unique exact match on name AND slug confirms; empty scope is
        not_found; every other shape is ambiguous (fail closed)."""
        if not isinstance(key, CheckpointKey):
            raise ReconciliationError("key must be a CheckpointKey")
        _require_text(name, "name")
        _require_text(slug, "slug")
        try:
            raw = list(self.lookup(key))
            objects: List[PlatformObject] = []
            for item in raw:
                if not isinstance(item, PlatformObject):
                    raise ReconciliationError(
                        f"lookup returned {type(item).__name__}, expected PlatformObject"
                    )
                objects.append(item)
        except Exception as exc:  # noqa: BLE001 - authoritative state unknown, not empty
            return Classification(
                OUTCOME_LOOKUP_FAILED,
                None,
                (),
                f"authoritative lookup failed ({type(exc).__name__}: {exc}); state UNKNOWN, lock kept",
            )
        scoped = [obj for obj in objects if obj.in_scope(key)]
        if objects and not scoped:
            return Classification(
                OUTCOME_AMBIGUOUS,
                None,
                tuple(sorted(obj.native_id for obj in objects)),
                "lookup returned only out-of-scope objects; refusing to treat as absence",
            )
        if not scoped:
            return Classification(
                OUTCOME_NOT_FOUND,
                None,
                (),
                f"authoritative scope {key.location}/{key.kind}/{key.parent} is empty",
            )
        exact = [obj for obj in scoped if obj.name == name and obj.slug == slug]
        if len(exact) == 1:
            return Classification(
                OUTCOME_CONFIRMED,
                exact[0].native_id,
                (exact[0].native_id,),
                f"unique exact match on name+slug in scope ({len(scoped)} candidate(s))",
            )
        if len(exact) > 1:
            return Classification(
                OUTCOME_AMBIGUOUS,
                None,
                tuple(sorted(obj.native_id for obj in exact)),
                f"{len(exact)} exact name+slug matches; rejecting ambiguous match",
            )
        partial = [
            obj
            for obj in scoped
            if (obj.name == name) != (obj.slug == slug)
        ]
        if partial:
            return Classification(
                OUTCOME_AMBIGUOUS,
                None,
                tuple(sorted(obj.native_id for obj in partial)),
                "partial identity match (name or slug, not both); refusing to guess",
            )
        # Nothing matched at all. With name+slug evidence this is absence;
        # without it we cannot tell which object is ours.
        if name is None or slug is None:  # pragma: no cover - _require_text above
            return Classification(
                OUTCOME_AMBIGUOUS,
                None,
                tuple(sorted(obj.native_id for obj in scoped)),
                "insufficient identity evidence",
            )
        return Classification(
            OUTCOME_NOT_FOUND,
            None,
            (),
            f"no candidate matches name+slug ({len(scoped)} unrelated object(s) in scope)",
        )

    def classify_from_record(self, key: CheckpointKey) -> Classification:
        """Classify using the intent record's recorded name/slug. A record
        missing either attribute can never be CONFIRMED from state alone:
        names are never identity, and neither is a slug alone."""
        cp = self.store.read(key)
        if cp is None:
            return Classification(
                OUTCOME_AMBIGUOUS,
                None,
                (),
                "no intent record; cannot verify which object is ours",
            )
        if not cp.name or not cp.slug:
            # Empty authoritative scope is still a sound absence claim.
            probe = self._probe_scope(key)
            if probe.outcome == OUTCOME_LOOKUP_FAILED:
                return probe
            if probe.outcome == OUTCOME_NOT_FOUND:
                return probe
            return Classification(
                OUTCOME_AMBIGUOUS,
                None,
                probe.matched,
                "insufficient identity evidence (record lacks name AND slug); "
                "names are never identity — pass an explicit native_id to resolve",
            )
        return self.classify(key, cp.name, cp.slug)

    def _probe_scope(self, key: CheckpointKey) -> Classification:
        """Authoritative emptiness probe (identity-free)."""
        try:
            raw = list(self.lookup(key))
            objects = [item for item in raw if isinstance(item, PlatformObject)]
            if len(objects) != len(raw):
                raise ReconciliationError("lookup returned a non-PlatformObject")
        except Exception as exc:  # noqa: BLE001
            return Classification(
                OUTCOME_LOOKUP_FAILED,
                None,
                (),
                f"authoritative lookup failed ({type(exc).__name__}: {exc})",
            )
        scoped = [obj for obj in objects if obj.in_scope(key)]
        if not scoped:
            return Classification(OUTCOME_NOT_FOUND, None, (), "authoritative scope is empty")
        return Classification(
            OUTCOME_AMBIGUOUS,
            None,
            tuple(sorted(obj.native_id for obj in scoped)),
            "objects present in scope",
        )

    # ---- pending ops: reconcile before retry ---------------------------
    def reconcile_pending(
        self, *, now: Optional[float] = None, include_open: bool = False
    ) -> List[OpReconciliation]:
        """Reconcile pending ops against authoritative state.

        By default only ops past their deadline (surfaced by the store as
        uncertain). With include_open=True every unresolved op is swept —
        correct at process restart when no writes can be in flight (single
        writer per delivery run), premature mid-run.
        """
        if include_open:
            due = [
                dict(op)
                for op in self.store.ops.values()
                if op["status"] in (OP_OPEN, OP_UNCERTAIN)
            ]
        else:
            due = self.store.stale_ops(now=now)
        out: List[OpReconciliation] = []
        for op in due:
            out.append(self.reconcile_uncertain_op(op["op_id"]))
        return out

    def reconcile_uncertain_op(
        self, op_id: str, *, native_id: Optional[str] = None
    ) -> OpReconciliation:
        """Resolve one pending op. With an explicit `native_id` (recovered
        write response, human confirmation) that definite outcome is used;
        otherwise the intent record is matched against authoritative state.
        Ambiguous / lookup-failed outcomes leave the op unresolved: the lock
        stays and retry stays refused."""
        op = self.store.resolve_op(op_id)
        if op["status"] == OP_DONE:
            raise ReconciliationError(f"op {op_id} is already closed ({op['outcome']})")
        if native_id is not None:
            _require_text(native_id, "native_id")
            self.store.reconcile_op(op_id, outcome=OUTCOME_CONFIRMED, native_id=native_id)
            return OpReconciliation(
                op_id, op["key"], OUTCOME_CONFIRMED, native_id,
                "definite native_id supplied by caller",
            )
        key = self._key_for_op(op)
        verdict = self.classify_from_record(key)
        if verdict.outcome == OUTCOME_CONFIRMED:
            self.store.reconcile_op(
                op_id, outcome=OUTCOME_CONFIRMED, native_id=verdict.native_id
            )
        elif verdict.outcome == OUTCOME_NOT_FOUND:
            self.store.reconcile_op(op_id, outcome=OUTCOME_NOT_FOUND)
        # ambiguous / lookup-failed: deliberately NOT resolved.
        return OpReconciliation(
            op_id, op["key"], verdict.outcome, verdict.native_id, verdict.evidence
        )

    def _key_for_op(self, op: dict) -> CheckpointKey:
        """Recover the composite key for a pending op through its intent
        record. An op with no intent record has no provable identity and can
        never be confirmed from state (classify_from_record fails closed)."""
        token = op["key"]
        for cp in self.store.list_checkpoints():
            if cp.key.token() == token:
                return cp.key
        # No record: reconstruct the key so the lookup can still be scoped
        # and the emptiness probe can still prove not_found.
        location, kind, parent, logical_id = token.split("\x1f")
        return CheckpointKey(location, kind, None if parent == "-" else parent, logical_id)

    def ensure_retryable(self, key: CheckpointKey) -> None:
        """Refuse work on a key whose last write has no definite outcome.
        Reconcile against authoritative state first."""
        arm, _ = self.store.plan_create(key)
        if arm == "blocked-pending":
            raise PendingOperationError(
                f"uncertain write pending on {key.token()}; reconcile against "
                "authoritative state before any retry"
            )

    # ---- safe attempt (partial-failure handling) -----------------------
    def attempt(
        self,
        key: CheckpointKey,
        op_id: str,
        action: str,
        write_fn: Callable[[], Optional[str]],
        *,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        timeout_s: float = 120.0,
    ) -> Checkpoint:
        """Run one platform write with durable intent first, pending op
        around it, immediate ID persistence after it.

        - confirmed key -> returns the record, write_fn is NOT called
          (resume never duplicates pages/forms/products);
        - unresolved prior op -> PendingOperationError (reconcile first);
        - fresh key -> PLANNED intent recorded BEFORE the write runs;
        - write raises -> re-raised, op stays open + intent stays durable;
        - write returns no native_id on an unconfirmed record -> op stays
          open (outcome unknown), reconcile later;
        - write returns a native_id -> persisted immediately via the store.
        """
        _require_text(op_id, "op_id")
        _require_text(action, "action")
        if not callable(write_fn):
            raise ReconciliationError("write_fn must be callable")
        arm, existing = self.store.plan_create(key)
        if arm == "blocked-pending":
            self.ensure_retryable(key)  # always raises
        if existing is not None and existing.native_id is not None:
            return existing  # already confirmed: never write again
        if existing is None:
            self.store.record_create(key, name=name, slug=slug)  # intent BEFORE the call
        self.store.begin_op(key, op_id, action=action, timeout_s=timeout_s)
        result = write_fn()
        cp = self.store.read(key)
        if result is not None:
            _require_text(result, "write_fn result (native_id)")
            self.store.complete_op(op_id, native_id=result)
        else:
            if cp is None or cp.native_id is None:
                raise ReconciliationError(
                    f"write returned no native_id for unconfirmed {key.token()}; "
                    f"op {op_id} left open for reconciliation"
                )
            self.store.complete_op(op_id)
        return self.store.read(key)

    # ---- restart / resume plan ----------------------------------------
    def plan(self, desired: Sequence[DesiredObject]) -> List[PlanItem]:
        """Read-only resume plan. Reuse confirmed records, allow attempts for
        PLANNED intents, pre-check authoritative state before any NEW create
        (adopt a unique existing object rather than duplicating it)."""
        items: List[PlanItem] = []
        for want in desired:
            arm, cp = self.store.plan_create(want.key)
            if arm == ACTION_BLOCKED or arm == "blocked-pending":
                items.append(
                    PlanItem(want.key, ACTION_BLOCKED, cp.native_id if cp else None,
                             cp.provenance if cp else None,
                             "unresolved op: reconcile before retry")
                )
                continue
            if cp is not None and cp.native_id is not None:
                items.append(
                    PlanItem(want.key, ACTION_REUSE, cp.native_id, cp.provenance,
                             "confirmed; write will not be called")
                )
                continue
            if cp is not None:
                items.append(
                    PlanItem(want.key, ACTION_RESUME_CREATE, None, cp.provenance,
                             "PLANNED intent on file; attempt allowed")
                )
                continue
            verdict = self.classify(want.key, want.name, want.slug)
            if verdict.outcome == OUTCOME_NOT_FOUND:
                items.append(
                    PlanItem(want.key, ACTION_CREATE_NEW, None, PROVENANCE_NEW_SCRATCH,
                             "absent from authoritative state; create allowed")
                )
            elif verdict.outcome == OUTCOME_CONFIRMED:
                self.store.adopt(want.key, native_id=verdict.native_id,
                                 name=want.name, slug=want.slug)
                items.append(
                    PlanItem(want.key, ACTION_ADOPTED, verdict.native_id,
                             PROVENANCE_REUSED, verdict.evidence)
                )
            elif verdict.outcome == OUTCOME_LOOKUP_FAILED:
                items.append(
                    PlanItem(want.key, ACTION_LOOKUP_FAILED, None, None, verdict.evidence)
                )
            else:
                items.append(
                    PlanItem(want.key, ACTION_AMBIGUOUS, None, None, verdict.evidence)
                )
        return items

    def restart(
        self, desired: Sequence[DesiredObject], *, now: Optional[float] = None
    ) -> RestartReport:
        """One-call restart: sweep every unresolved op from the previous run
        (safe when no writes are in flight — single writer per delivery run),
        then plan the desired work. Resume never duplicates; every uncertain
        write meets authoritative state before any retry."""
        report = RestartReport()
        report.reconciliations = self.reconcile_pending(now=now, include_open=True)
        report.items = self.plan(desired)
        return report


# --------------------------------------------------------------------------
# Assert-based self-check. Run: python3 -I shared-utils/delivery/reconciliation.py
# --------------------------------------------------------------------------
def _self_check() -> int:
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
            raise AssertionError(f"FAIL: {what}: raised {type(other).__name__} not {exc.__name__}")
        raise AssertionError(f"FAIL: {what}: nothing raised")

    with tempfile.TemporaryDirectory(prefix="ghl-delivery-W4C-U1-") as td:
        path = Path(td) / "delivery-state.json"
        store = CheckpointStore(path)
        authoritative: Dict[str, List[PlatformObject]] = {}

        def lookup(key: CheckpointKey) -> List[PlatformObject]:
            return list(authoritative.get(key.token(), []))

        rec = Reconciler(store, lookup)
        raised(lambda: Reconciler(store, None), ReconciliationError, "lookup must be callable")

        page = DesiredObject(
            CheckpointKey("acc1/funnelA", "page", "home", "order"), "Order Page", "order-page"
        )
        form = DesiredObject(
            CheckpointKey("acc1/funnelA", "form", "home", "intake"), "Intake Form", "intake-form"
        )
        product = DesiredObject(
            CheckpointKey("acc1/funnelA", "product", None, "coaching"), "Coaching", "coaching"
        )

        # -- attempt: durable intent visible BEFORE the write runs --------
        seen_inside = {}

        def write_page():
            cp_inside = store.read(page.key)
            seen_inside["state"] = cp_inside.state
            seen_inside["op_status"] = store.resolve_op("op-p1")["status"]
            return "page_1001"

        cp = rec.attempt(page.key, "op-p1", "create", write_page,
                         name=page.name, slug=page.slug)
        ok(seen_inside["state"] == STATE_PLANNED, "intent PLANNED before the write ran")
        ok(seen_inside["op_status"] == OP_OPEN, "pending op open around the write")
        ok(cp.native_id == "page_1001" and cp.state == "CREATED",
           "native_id persisted immediately on success")
        ok(CheckpointStore(path).read(page.key).native_id == "page_1001",
           "confirmed ID durable across store reload")
        ok(store.resolve_op("op-p1")["status"] == OP_DONE, "op closed after definite success")

        # -- resume: confirmed key never re-writes (no duplicate) --------
        def boom():
            raise AssertionError("write must not be called for a confirmed key")

        cp = rec.attempt(page.key, "op-p1b", "create", boom, name=page.name, slug=page.slug)
        ok(cp.native_id == "page_1001", "confirmed key returns record without writing")

        # -- partial failure: write raises -> intent + op durable --------
        def timeout_write():
            # The write landed on the platform before the response was lost:
            # authoritative state gains the object, our store did not.
            authoritative.setdefault(form.key.token(), []).append(
                PlatformObject("form_77", form.name, form.slug)
            )
            raise TimeoutError("platform call timed out after creating the object")

        raised(lambda: rec.attempt(form.key, "op-f1", "create", timeout_write,
                                   name=form.name, slug=form.slug),
               TimeoutError, "write failure propagates to the caller")
        reopened = CheckpointStore(path)
        ok(reopened.read(form.key).state == STATE_PLANNED,
           "intent record survives the crash (durable before the call)")
        ok(reopened.resolve_op("op-f1")["status"] == OP_OPEN,
           "pending op survives the crash (restart surface)")
        arm, _ = reopened.plan_create(form.key)
        ok(arm == "blocked-pending", "plan blocks retry while outcome unknown")
        raised(lambda: rec.ensure_retryable(form.key), PendingOperationError,
               "ensure_retryable refuses retry before reconciliation")
        raised(lambda: rec.attempt(form.key, "op-f1b", "create", boom,
                                   name=form.name, slug=form.slug),
               PendingOperationError, "second attempt refused before reconciliation")

        # -- reconcile CONFIRMED against authoritative state --------------
        result = rec.reconcile_uncertain_op("op-f1")
        ok(result.outcome == OUTCOME_CONFIRMED and result.native_id == "form_77",
           "unique name+slug match confirms the uncertain write")
        ok(CheckpointStore(path).read(form.key).native_id == "form_77",
           "reconciled native_id persisted immediately")
        arm, _ = store.plan_create(form.key)
        ok(arm == "reuse", "lock released only after a definite outcome")
        cp = rec.attempt(form.key, "op-f1c", "create", boom, name=form.name, slug=form.slug)
        ok(cp.native_id == "form_77", "reconciled key resumes as reuse, no duplicate")

        # -- reconcile NOT_FOUND -> clean retry, record confirmed in place -
        def timeout_write2():
            raise TimeoutError("died before the write landed")

        raised(lambda: rec.attempt(product.key, "op-pr1", "create", timeout_write2,
                                   name=product.name, slug=product.slug),
               TimeoutError, "product write failure propagates")
        result = rec.reconcile_uncertain_op("op-pr1")
        ok(result.outcome == OUTCOME_NOT_FOUND, "empty authoritative scope proves absence")
        arm, _ = store.plan_create(product.key)
        ok(arm != "blocked-pending", "not_found releases the op lock for a clean retry")
        ok(rec.plan([product])[0].action == ACTION_RESUME_CREATE,
           "released PLANNED intent plans as resume-create (confirm in place, not a new record)")

        def write_product():
            return "prod_9"

        cp = rec.attempt(product.key, "op-pr2", "create", write_product,
                         name=product.name, slug=product.slug)
        ok(cp.native_id == "prod_9" and cp.provenance == PROVENANCE_NEW_SCRATCH,
           "retry confirms the SAME intent record (never a second record)")
        ok(len(store.list_checkpoints(location="acc1/funnelA")) == 3,
           "exactly three records: resume created no duplicates")

        # -- ambiguous: two exact matches -> refuse, lock stays -----------
        survey = DesiredObject(
            CheckpointKey("acc1/funnelA", "survey", "home", "intake"), "Intake", "intake"
        )
        raised(lambda: rec.attempt(survey.key, "op-s1", "create", timeout_write2,
                                   name=survey.name, slug=survey.slug),
               TimeoutError, "survey write failure propagates")
        authoritative[survey.key.token()] = [
            PlatformObject("survey_1", survey.name, survey.slug),
            PlatformObject("survey_2", survey.name, survey.slug),
        ]
        result = rec.reconcile_uncertain_op("op-s1")
        ok(result.outcome == OUTCOME_AMBIGUOUS, "two exact matches are rejected as ambiguous")
        ok(store.resolve_op("op-s1")["status"] != OP_DONE,
           "ambiguous outcome leaves the op unresolved (fail closed)")
        raised(lambda: rec.ensure_retryable(survey.key), PendingOperationError,
               "retry still refused after ambiguous reconciliation")
        raised(lambda: rec.attempt(survey.key, "op-s1b", "create", boom,
                                   name=survey.name, slug=survey.slug),
               PendingOperationError, "attempt refused while ambiguous")

        # -- partial match (name xor slug) is ambiguous, never not_found --
        verdict = rec.classify(
            survey.key, survey.name, "some-other-slug"
        )
        ok(verdict.outcome == OUTCOME_AMBIGUOUS and "partial" in verdict.evidence,
           "name-without-slug match is partial evidence, not absence")

        # -- name-only evidence is never identity ------------------------
        bare = CheckpointKey("acc1/funnelA", "page", "home", "bare")
        store.record_create(bare, name="Bare")  # no slug on purpose
        store.begin_op(bare, "op-b1", action="create", timeout_s=30)
        authoritative[bare.token()] = [PlatformObject("page_55", "Bare", "bare-slug")]
        result = rec.reconcile_uncertain_op("op-b1")
        ok(result.outcome == OUTCOME_AMBIGUOUS and "identity" in result.evidence,
           "name-only record can never be confirmed from state (names are never identity)")

        # -- explicit native_id is the escape hatch to a definite outcome -
        result = rec.reconcile_uncertain_op("op-b1", native_id="page_55")
        ok(result.outcome == OUTCOME_CONFIRMED and result.native_id == "page_55",
           "caller-supplied definite native_id resolves the op")
        ok(CheckpointStore(path).read(bare).native_id == "page_55",
           "explicit confirmation persisted immediately")

        # -- lookup failure = UNKNOWN state, never absence ---------------
        survey2 = DesiredObject(
            CheckpointKey("acc1/funnelA", "survey", "home", "followup"), "Follow-up", "follow-up"
        )
        raised(lambda: rec.attempt(survey2.key, "op-s2", "create", timeout_write2,
                                   name=survey2.name, slug=survey2.slug),
               TimeoutError, "second survey write failure propagates")

        def broken_lookup(key):
            raise ConnectionError("authoritative API unreachable")

        broken = Reconciler(store, broken_lookup)
        result = broken.reconcile_uncertain_op("op-s2")
        ok(result.outcome == OUTCOME_LOOKUP_FAILED,
           "failed lookup reports UNKNOWN, not not_found")
        ok(store.resolve_op("op-s2")["status"] != OP_DONE,
           "lookup failure keeps the lock (no blind retry)")

        # -- out-of-scope-only candidates refuse, not absence ------------
        page2 = DesiredObject(
            CheckpointKey("acc1/funnelB", "page", "home", "order"), "Order Page", "order-page"
        )
        raised(lambda: rec.attempt(page2.key, "op-p2", "create", timeout_write2,
                                   name=page2.name, slug=page2.slug),
               TimeoutError, "write failure propagates")
        authoritative[page2.key.token()] = [
            PlatformObject("page_9", page2.name, page2.slug, parent="other")
        ]
        result = rec.reconcile_uncertain_op("op-p2")
        ok(result.outcome == OUTCOME_AMBIGUOUS and "out-of-scope" in result.evidence,
           "out-of-scope-only candidates are refused, not treated as absence")

        # -- read-before-create at the platform: adopt, never duplicate ---
        adopt_key = DesiredObject(
            CheckpointKey("acc1/funnelA", "page", "home", "about"), "About", "about"
        )
        authoritative[adopt_key.key.token()] = [
            PlatformObject("page_300", adopt_key.name, adopt_key.slug)
        ]
        items = rec.plan([adopt_key])
        ok(items[0].action == ACTION_ADOPTED and items[0].native_id == "page_300",
           "unique pre-existing object is adopted, not re-created")
        ok(store.read(adopt_key.key).provenance == PROVENANCE_REUSED,
           "adoption is marked reused business object, never new scratch")

        # -- plan is read-only for absent keys ---------------------------
        fresh = DesiredObject(
            CheckpointKey("acc1/funnelA", "page", "home", "contact"), "Contact", "contact"
        )
        items = rec.plan([fresh])
        ok(items[0].action == ACTION_CREATE_NEW, "absent + clear state -> create-new")
        ok(store.read(fresh.key) is None, "plan alone writes nothing for absent keys")

        # -- ambiguous pre-existing candidates refuse creation -----------
        dup = DesiredObject(
            CheckpointKey("acc1/funnelA", "page", "home", "dup"), "Dup", "dup"
        )
        authoritative[dup.key.token()] = [
            PlatformObject("page_401", dup.name, dup.slug),
            PlatformObject("page_402", dup.name, dup.slug),
        ]
        items = rec.plan([dup])
        ok(items[0].action == ACTION_AMBIGUOUS and store.read(dup.key) is None,
           "ambiguous pre-existing candidates: creation refused, nothing written")

        # -- restart end-to-end over a partial batch ---------------------
        store2 = CheckpointStore(Path(td) / "restart-state.json")
        auth2: Dict[str, List[PlatformObject]] = {}
        rec2 = Reconciler(store2, lambda k: list(auth2.get(k.token(), [])))

        done = DesiredObject(CheckpointKey("r/run", "page", "root", "home"), "Home", "home")
        crashed = DesiredObject(CheckpointKey("r/run", "page", "root", "sales"), "Sales", "sales")
        untouched = DesiredObject(CheckpointKey("r/run", "page", "root", "faq"), "FAQ", "faq")
        stuck = DesiredObject(CheckpointKey("r/run", "form", "root", "lead"), "Lead", "lead")

        def quick_write(native):
            def _w():
                return native
            return _w

        rec2.attempt(done.key, "r-op1", "create", quick_write("pg_1"),
                     name=done.name, slug=done.slug)
        raised(lambda: rec2.attempt(crashed.key, "r-op2", "create", timeout_write2,
                                    name=crashed.name, slug=crashed.slug),
               TimeoutError, "crash mid-write")
        raised(lambda: rec2.attempt(stuck.key, "r-op4", "create", timeout_write2,
                                    name=stuck.name, slug=stuck.slug),
               TimeoutError, "second crash mid-write")
        auth2[crashed.key.token()] = [PlatformObject("pg_2", crashed.name, crashed.slug)]
        auth2[stuck.key.token()] = [
            PlatformObject("fm_1", stuck.name, stuck.slug),
            PlatformObject("fm_2", stuck.name, stuck.slug),
        ]

        report = rec2.restart([done, crashed, untouched, stuck])
        by_action = {item.key.logical_id: item.action for item in report.items}
        ok(by_action["home"] == ACTION_REUSE, "restart: finished work is reused")
        ok(by_action["sales"] == ACTION_REUSE,
           "restart: crashed write confirmed by authoritative read, then reused")
        ok(by_action["faq"] == ACTION_CREATE_NEW, "restart: untouched work is created")
        ok(by_action["lead"] == ACTION_BLOCKED,
           "restart: ambiguous write stays blocked, never duplicated")
        outcomes = {r.op_id: r.outcome for r in report.reconciliations}
        ok(outcomes.get("r-op2") == OUTCOME_CONFIRMED, "restart swept the crashed op")
        ok(outcomes.get("r-op4") == OUTCOME_AMBIGUOUS, "restart refused the ambiguous op")
        ok(store2.read(crashed.key).native_id == "pg_2",
           "restart persisted the recovered native_id immediately")
        ok(store2.resolve_op("r-op4")["status"] != OP_DONE,
           "ambiguous op remains unresolved after restart")
        ok(len(store2.list_checkpoints(location="r/run")) == 3,
           "restart produced exactly the expected records (no duplicates)")
        raised(lambda: rec2.ensure_retryable(stuck.key), PendingOperationError,
               "stuck key still refuses retry after restart")

    return checks


if __name__ == "__main__":
    n = _self_check()
    print(f"self-check OK ({n} assertions)")
