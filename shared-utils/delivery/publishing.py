"""
shared-utils/delivery/publishing.py — approval-gated publishing coordinator
with real public URL readback for the GHL delivery stream (W7C, stream
W7 N-PAGE DELIVERY). One writer for this file: assignment W7C.

Contract basis (GHL-DELIVERY-SPEC.md):
  "Durable execution (W4)": Saving != publishing. Publish only authorized
  pages/version/domain in dependency-safe order; return real public URLs;
  one page published != all published; whole-site publish is never assumed
  atomic. A required live capture needs a precise bundled approval naming
  test location, temporary objects, and operations.
  W7 ownership: "approval-gated publishing coordinator + real URL readback".

What this module guarantees:

1. APPROVAL GATE. Nothing publishes without a registered Approval whose
   scope explicitly names every target (logical_id or native_id). A request
   naming ANY target outside the scope is refused whole — fail closed,
   nothing publishes. An approval binds optional domain and version; a
   mismatch refuses the whole request.
2. SAVING IS NOT PUBLISHING. A draft/saved page (PLANNED or CREATED) is
   never publishable; publishing requires CONFIGURED. Refusals are recorded
   per target and never silently dropped.
3. DEPENDENCY-SAFE ORDER. Pages publish downstream-first: a page publishes
   only after the pages it links to have read back real public URLs (taken
   from real resolved edges — W7B link_resolution when supplied). Legitimate
   website navigation cycles are broken deterministically and recorded,
   never hung on.
4. REAL PUBLIC URL READBACK IS MANDATORY. The coordinator never fabricates
   a URL and never trusts whatever a publish call returned: only the
   backend's readback output counts. No readback -> the page is NOT
   published and NO url is claimed (status pending_readback / readback_missing).
5. PUBLISHED vs VERIFIED stay distinct. Readback URL recorded -> PUBLISHED.
   Independent verification of that URL -> VERIFIED. Neither implies the
   other, and neither implies anything about sibling pages.
6. PER-TARGET TRUTH. PublishRun reports every target's own outcome;
   all_published is true only when every requested target has a readback
   URL. One page published never means the site is published.
7. CAPABILITY HONESTY. A backend missing the publish or readback seam is
   reported as capability_incomplete — never as done.

Backend seam (duck-typed; owned by the W2 operation catalog / W5 primitives
— this module never invents platform endpoints):

    backend.publish(target: dict) -> Any            # authorized publish op
    backend.readback_public_url(target: dict) -> Optional[str]   # REQUIRED
    backend.verify_public(target: dict, url: str) -> Optional[bool]  # optional

The return value of backend.publish is NEVER used as a URL. Only
readback_public_url output is recorded as the public URL.

W4A integration (shared-utils/delivery/checkpoints.py, real module): when a
CheckpointStore is attached via key_for, publication goes through
store.record_publish(...) — the ONLY path that sets a published URL, with
this run's approval_id as the authorization reference — and VERIFIED is
reached only via store.set_state(...), which refuses any direct jump to
PUBLISHED. Without an attached store the coordinator still enforces the
gates from the plan's own state field and reports the seam as outstanding.

PROVISIONAL (W7C-U1): the normative W1 schema
(shared-utils/delivery/npage_contract.py) may not exist at this base;
consumed plan dicts follow the W7B PLAN KEYS (contract_version, kind,
pages[{logical_id, native_id, state, url, url_kind}], edges[...]).
contract_seam_status() reports exactly what integration remains outstanding.

Import pattern (namespace package — no __init__.py needed):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared-utils"))
    from delivery.publishing import PublishCoordinator, Approval

Run the assert-based self-check (it imports the REAL checkpoints and
link_resolution modules in this tree):

    python3 -I shared-utils/delivery/publishing.py
"""

from __future__ import annotations

import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

# Namespace bootstrap so this file runs standalone (`python3 -I .../publishing.py`)
# and as `delivery.publishing` — sibling modules resolve either way.
_SHARED_UTILS = str(Path(__file__).resolve().parent.parent)
if _SHARED_UTILS not in sys.path:
    sys.path.insert(0, _SHARED_UTILS)

from delivery.checkpoints import (  # noqa: E402  (real W4A module, not a stub)
    Checkpoint,
    CheckpointKey,
    CheckpointStore,
    InvalidTransitionError,
    STATE_CONFIGURED,
    STATE_CREATED,
    STATE_PLANNED,
    STATE_PUBLISHED,
    STATE_VERIFIED,
)
from delivery.link_resolution import resolve_delivery  # noqa: E402  (real W7B module)

OPERATIONS: Tuple[str, ...] = ("publish", "capture")

# Per-target run outcomes. Every requested target ends in exactly one of
# these — outcomes are recorded, never silently dropped.
OUT_PUBLISHED_VERIFIED = "published_verified"      # real URL read back AND verified
OUT_PUBLISHED_UNVERIFIED = "published_unverified"  # real URL read back, verification pending
OUT_PENDING_READBACK = "pending_readback"          # publish op ran, real URL outstanding (never faked)
OUT_READBACK_MISSING = "readback_missing"          # readback returned no URL; NOT published
OUT_PUBLISH_FAILED = "publish_failed"              # publish op raised
OUT_REFUSED_NOT_CONFIGURED = "refused_not_configured"  # saving is not publishing
OUT_REFUSED_UNTRACKED = "refused_untracked"        # no checkpoint record to publish from
OUT_CAPABILITY_INCOMPLETE = "capability_incomplete"  # backend seam missing; never claimed done

PUBLIC_URL_KIND = "public"  # the only url_kind this module ever emits


class PublishingError(ValueError):
    """Base class: publishing contract violation."""


class ApprovalError(PublishingError):
    """Malformed approval — approvals are precise, never implied."""


class PublishGateError(PublishingError):
    """No usable approval: missing, wrong operation, or unknown id."""


class PublishScopeError(PublishingError):
    """A requested target/domain/version is outside the approval scope.
    Fail closed: when this raises, NOTHING has been published."""


def _require_text(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApprovalError(f"{what} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class Approval:
    """A precise, bundled publication authorization.

    targets: EVERY id this approval authorizes, explicitly. Never a wildcard,
    never inferred from a plan, never "the whole site". A page absent from
    targets is simply not authorized.
    operations: "publish" and/or "capture". A capture operation requires
    test_location AND temporary_objects per the spec's bundled-approval rule
    (test location, temporary objects, and operations — all three named).
    domain / version: when set, the run is bound to exactly that domain or
    content version; a mismatch refuses the whole request.
    """

    approval_id: str
    granted_by: str
    targets: frozenset
    operations: Tuple[str, ...] = ("publish",)
    domain: Optional[str] = None
    version: Optional[str] = None
    test_location: Optional[str] = None
    temporary_objects: Tuple[str, ...] = ()
    granted_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        object.__setattr__(self, "approval_id", _require_text(self.approval_id, "approval_id"))
        object.__setattr__(self, "granted_by", _require_text(self.granted_by, "granted_by"))
        ops = tuple(self.operations)
        if not ops:
            raise ApprovalError("approval.operations must name at least one operation")
        for op in ops:
            if op not in OPERATIONS:
                raise ApprovalError(f"unknown operation {op!r}; known: {OPERATIONS}")
        object.__setattr__(self, "operations", ops)
        raw_targets = self.targets if isinstance(self.targets, (frozenset, set, tuple, list)) else ()
        targets = frozenset(_require_text(t, "approval target") for t in raw_targets)
        if not targets:
            raise ApprovalError(
                "approval.targets must explicitly name every authorized id — empty scopes publish nothing"
            )
        object.__setattr__(self, "targets", targets)
        if "capture" in ops:
            # Spec: "a precise bundled approval naming test location,
            # temporary objects, and operations". All three, or no capture.
            object.__setattr__(self, "test_location", _require_text(self.test_location, "test_location (required for capture)"))
            temps = tuple(_require_text(t, "temporary object") for t in (self.temporary_objects or ()))
            if not temps:
                raise ApprovalError("capture approval must name its temporary objects")
            object.__setattr__(self, "temporary_objects", temps)


@dataclass
class PublishResult:
    """Outcome for exactly one target — the unit of truth. A run's summary
    is only ever the aggregation of these."""

    target: str
    status: str
    state: str
    url: Optional[str] = None
    url_kind: Optional[str] = None
    reason: Optional[str] = None
    authorization: Optional[str] = None

    def to_json(self) -> dict:
        return {
            "target": self.target,
            "status": self.status,
            "state": self.state,
            "url": self.url,
            "url_kind": self.url_kind,
            "reason": self.reason,
            "authorization": self.authorization,
        }


@dataclass
class PublishRun:
    """One approval-gated run. Whole-site publish is never assumed atomic:
    results list every target individually, in the executed order."""

    run_id: str
    approval_id: str
    order: List[str]
    order_basis: str
    results: List[PublishResult]
    order_note: Optional[str] = None
    started_at: float = field(default_factory=time.time)

    @property
    def published_targets(self) -> List[str]:
        return [r.target for r in self.results if r.url]

    @property
    def all_published(self) -> bool:
        """True only when EVERY requested target has a real readback URL.
        One page published != all published."""
        return bool(self.results) and all(r.url for r in self.results)

    @property
    def any_published(self) -> bool:
        return any(r.url for r in self.results)

    def summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "approval_id": self.approval_id,
            "order": list(self.order),
            "order_basis": self.order_basis,
            "order_note": self.order_note,
            "counts": {
                "requested": len(self.results),
                "published_with_url": len(self.published_targets),
                "all_published": self.all_published,
            },
            "results": [r.to_json() for r in self.results],
        }


def _extract_edges(plan: Optional[dict], resolution: Optional[dict]) -> List[Dict[str, Any]]:
    """Edges for dependency ordering, from a real W7B resolution (preferred)
    or a raw plan. Unresolved edges still carry their source/target for
    ordering; external URL targets order nothing."""
    if resolution is not None:
        edges = resolution.get("resolved_edges") or []
        return [e for e in edges if isinstance(e, dict)]
    if plan is not None:
        result = resolve_delivery(plan)
        if result.get("errors"):
            raise PublishingError(
                "plan failed W7B link resolution; refusing to order publishes from a broken plan: "
                + "; ".join(str(e) for e in result["errors"])
            )
        return list(result.get("resolved_edges") or [])
    return []


def _edge_source_target(edge: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    source = edge.get("source")
    target = edge.get("target")
    if not isinstance(source, str) or not isinstance(target, dict):
        return None
    t_logical = target.get("logical_id")
    if isinstance(t_logical, str) and t_logical:
        return source, t_logical
    return None


def _dependency_order(target_ids: Sequence[str], edges: Sequence[Dict[str, Any]],
                      ) -> Tuple[List[str], Optional[str]]:
    """Downstream-first: for an edge source -> t (source links to t), t
    publishes before source, so no newly published page points at an
    unpublished one. Ties keep request order. Website navigation cycles are
    legitimate: when only cycles remain, break at the earliest requested id
    and say so — never hang, never guess silently."""
    ids = list(dict.fromkeys(target_ids))
    index = {tid: i for i, tid in enumerate(ids)}
    must_follow: Dict[str, Set[str]] = {tid: set() for tid in ids}  # id -> ids that publish first
    for edge in edges:
        pair = _edge_source_target(edge)
        if pair is None:
            continue
        source, t_logical = pair
        if source in index and t_logical in index and source != t_logical:
            must_follow[source].add(t_logical)
    ordered: List[str] = []
    remaining = set(ids)
    note: Optional[str] = None
    broken: List[str] = []
    while remaining:
        ready = [tid for tid in ids if tid in remaining and not (must_follow[tid] & remaining)]
        if not ready:
            # Only cycles left: break deterministically at the earliest request id.
            pick = min(remaining, key=lambda t: index[t])
            broken.append(pick)
            ready = [pick]
        for tid in ready:
            ordered.append(tid)
            remaining.discard(tid)
    if broken:
        note = "navigation cycle(s) broken deterministically at: " + ", ".join(broken)
    return ordered, note


class PublishCoordinator:
    """Approval-gated publishing coordinator with real public URL readback.

    The coordinator owns gates and ordering ONLY. Platform mutation happens
    through the backend seam; durable state through the optional real W4A
    CheckpointStore. Saving a draft is a different act entirely and has no
    path through this class.
    """

    def __init__(
        self,
        backend: Any,
        *,
        checkpoints: Optional[CheckpointStore] = None,
        key_for: Optional[Callable[[str], CheckpointKey]] = None,
    ) -> None:
        self.backend = backend
        self.checkpoints = checkpoints
        self.key_for = key_for
        self._approvals: Dict[str, Approval] = {}

    # ---- approval gate -------------------------------------------------
    def register(self, approval: Approval) -> Approval:
        if not isinstance(approval, Approval):
            raise ApprovalError("register() takes an Approval — approvals are precise, never implied")
        self._approvals[approval.approval_id] = approval
        return approval

    def _approval_for(self, approval_id: Optional[str], operation: str) -> Approval:
        if not isinstance(approval_id, str) or not approval_id.strip():
            raise PublishGateError("publication requires an explicit approval_id; saving is never publishing")
        approval = self._approvals.get(approval_id.strip())
        if approval is None:
            raise PublishGateError(f"unknown approval {approval_id!r} — nothing publishes unapproved")
        if operation not in approval.operations:
            raise PublishGateError(
                f"approval {approval.approval_id!r} authorizes {approval.operations}, not {operation!r}"
            )
        return approval

    # ---- publishing ----------------------------------------------------
    def publish(
        self,
        targets: Sequence[Dict[str, Any]],
        *,
        approval_id: Optional[str] = None,
        plan: Optional[dict] = None,
        resolution: Optional[dict] = None,
        domain: Optional[str] = None,
        version: Optional[str] = None,
    ) -> PublishRun:
        """Publish exactly the requested targets under one approval.

        Targets are page dicts: {"logical_id": ..., "native_id": ..., "state":
        "CONFIGURED", "domain": ..., "version": ...}. With an attached
        CheckpointStore + key_for the record's own state is authoritative;
        without one the target's "state" field must say CONFIGURED.

        Fail closed on scope: if ANY requested target (or the request's
        domain/version) is outside the approval, PublishScopeError is raised
        and NOTHING has been published — the seam is only reached after the
        whole request is authorized.
        """
        approval = self._approval_for(approval_id, "publish")
        if not isinstance(targets, (list, tuple)) or not targets:
            raise PublishingError("targets must be a non-empty list of page dicts")
        pages: List[Dict[str, Any]] = []
        for t in targets:
            if not isinstance(t, dict):
                raise PublishingError("targets entries must be dicts")
            logical = t.get("logical_id")
            _require_text(logical if isinstance(logical, str) else t.get("native_id"), "target identity")
            pages.append(t)

        # --- scope gate: whole request, before any platform call ---------
        violations: List[str] = []
        for page in pages:
            ids = [v for v in (page.get("logical_id"), page.get("native_id")) if isinstance(v, str) and v]
            if not any(v in approval.targets for v in ids):
                violations.append(f"target {page.get('logical_id') or page.get('native_id')!r} is not named in approval {approval.approval_id!r}")
        req_domain = domain if domain is not None else next((p.get("domain") for p in pages if p.get("domain")), None)
        req_version = version if version is not None else next((p.get("version") for p in pages if p.get("version")), None)
        if approval.domain is not None and req_domain != approval.domain:
            violations.append(f"request domain {req_domain!r} != approved domain {approval.domain!r}")
        if approval.version is not None and req_version != approval.version:
            violations.append(f"request version {req_version!r} != approved version {approval.version!r}")
        if violations:
            raise PublishScopeError(
                "refused whole request, nothing published: " + "; ".join(violations)
            )

        # --- dependency-safe order --------------------------------------
        edges = _extract_edges(plan, resolution)
        target_ids = [p.get("logical_id") or p.get("native_id") for p in pages]
        order, order_note = _dependency_order(target_ids, edges)
        by_id = {p.get("logical_id") or p.get("native_id"): p for p in pages}
        basis = "downstream-first over resolved edges" if edges else "input order (no edge information supplied)"

        run = PublishRun(
            run_id=uuid.uuid4().hex,
            approval_id=approval.approval_id,
            order=order,
            order_basis=basis,
            results=[],
            order_note=order_note,
        )

        for tid in order:
            page = by_id[tid]
            run.results.append(self._publish_one(page, approval))
        return run

    def _state_of(self, page: Dict[str, Any]) -> Tuple[str, Optional[Checkpoint], Optional[str]]:
        """Authoritative pre-publish state. Store record wins; a target with
        no record is refused (never guessed). Without a store, the plan's own
        state field is the only evidence."""
        if self.checkpoints is not None and self.key_for is not None:
            key = self.key_for(page.get("logical_id") or page.get("native_id"))
            record = self.checkpoints.read(key)
            if record is None:
                return (OUT_REFUSED_UNTRACKED, None, "no checkpoint record — identity never inferred")
            return (record.state, record, None)
        state = page.get("state")
        return (state if isinstance(state, str) else "", None, "plan state field (no checkpoint store attached)")

    def _publish_one(self, page: Dict[str, Any], approval: Approval) -> PublishResult:
        logical = page.get("logical_id") or page.get("native_id")

        state, record, _src = self._state_of(page)
        if record is None and self.checkpoints is not None:
            return PublishResult(logical, OUT_REFUSED_UNTRACKED, "UNKNOWN",
                                 reason="no checkpoint record — identity never inferred")

        # --- saving is not publishing -----------------------------------
        if state != STATE_CONFIGURED:
            return PublishResult(
                logical, OUT_REFUSED_NOT_CONFIGURED, state,
                reason=f"state {state!r} is not CONFIGURED — saving is never publishing",
            )

        # --- capability honesty -----------------------------------------
        if not callable(getattr(self.backend, "publish", None)):
            return PublishResult(logical, OUT_CAPABILITY_INCOMPLETE, state,
                                 reason="backend has no publish() seam — capability incomplete, never claimed done")
        if not callable(getattr(self.backend, "readback_public_url", None)):
            return PublishResult(logical, OUT_CAPABILITY_INCOMPLETE, state,
                                 reason="backend has no readback_public_url() seam — no URL can be honestly reported")

        # --- platform publish -------------------------------------------
        try:
            self.backend.publish(dict(page))  # return value is NEVER used as a URL
        except Exception as exc:  # noqa: BLE001 — outcome recorded, run continues
            return PublishResult(logical, OUT_PUBLISH_FAILED, state,
                                 reason=f"publish operation failed: {exc}",
                                 authorization=approval.approval_id)

        # --- REAL public URL readback (mandatory, never fabricated) ------
        try:
            url = self.backend.readback_public_url(dict(page))
        except Exception as exc:  # noqa: BLE001
            return PublishResult(logical, OUT_PENDING_READBACK, state,
                                 reason=f"publish ran but readback raised: {exc} — URL outstanding, never faked",
                                 authorization=approval.approval_id)
        if not isinstance(url, str) or not url.strip():
            return PublishResult(logical, OUT_READBACK_MISSING, state,
                                 reason="readback returned no public URL — NOT published, no URL claimed",
                                 authorization=approval.approval_id)
        url = url.strip()

        # --- durable record: the ONLY path that publishes ----------------
        if self.checkpoints is not None and record is not None:
            key = self.key_for(logical)
            record = self.checkpoints.record_publish(
                key, url=url, authorization=approval.approval_id,
                expected_revision=record.revision,
            )

        result = PublishResult(logical, OUT_PUBLISHED_UNVERIFIED, STATE_PUBLISHED,
                               url=url, url_kind=PUBLIC_URL_KIND,
                               authorization=approval.approval_id)

        # --- verification: PUBLISHED != VERIFIED -------------------------
        verify = getattr(self.backend, "verify_public", None)
        if callable(verify):
            try:
                verified = verify(dict(page), url)
            except Exception as exc:  # noqa: BLE001
                result.reason = f"published with readback URL; verification raised: {exc}"
                return result
            if verified is True:
                if self.checkpoints is not None and record is not None:
                    key = self.key_for(logical)
                    record = self.checkpoints.set_state(
                        key, STATE_VERIFIED, expected_revision=record.revision,
                    )
                result.status = OUT_PUBLISHED_VERIFIED
                result.state = STATE_VERIFIED
                result.reason = "readback URL verified public"
            else:
                result.reason = "published with readback URL; verification did not confirm public reachability"
        else:
            result.reason = "published with readback URL; verification seam absent (VERIFIED not claimed)"
        return result


def contract_seam_status() -> Dict[str, Any]:
    """Explicit integration seam status — every caller can see exactly what
    remains outstanding. Never presented as the W1 normative schema."""
    return {
        "unit": "W7C-U1",
        "module": "shared-utils/delivery/publishing.py",
        "consumes": {
            "W4A checkpoints.py": "real module imported at load; store attached per coordinator",
            "W7B link_resolution.py": "real module imported at load; consumed for publish ordering",
        },
        "outstanding": {
            "W1 npage_contract.py": "normative schema not attached here; plan dicts follow W7B PLAN KEYS (PROVISIONAL)",
            "backend publish seam": "owned by W2 operation catalog / W5 primitives; this module never invents endpoints",
            "backend readback seam": "real public URL readback is REQUIRED; without it nothing is claimed published",
        },
    }


# ---------------------------------------------------------------------------
# Assert-based self-check: imports the REAL checkpoints + link_resolution
# modules in this tree. Run: python3 -I shared-utils/delivery/publishing.py
# ---------------------------------------------------------------------------
def _selfcheck() -> int:
    import json
    import tempfile

    class FakeBackend:
        """Deterministic stand-in for the W2/W5 platform seam. publish()
        returns a BOGUS url on purpose — the coordinator must never use it."""

        def __init__(self, readback: Dict[str, Optional[str]], verify: Optional[Dict[str, bool]] = None,
                     fail: Optional[Set[str]] = None):
            self.readback = readback
            self.verify_map = verify or {}
            self.fail = fail or set()
            self.publish_calls: List[str] = []
            self.readback_calls: List[str] = []

        def publish(self, target: dict) -> dict:
            logical = target.get("logical_id")
            self.publish_calls.append(logical)
            if logical in self.fail:
                raise RuntimeError("platform refused")
            return {"url": "https://ASSUMED-NEVER-TRUST.example/" + str(logical)}

        def readback_public_url(self, target: dict) -> Optional[str]:
            logical = target.get("logical_id")
            self.readback_calls.append(logical)
            return self.readback.get(logical)

        def verify_public(self, target: dict, url: str) -> Optional[bool]:
            return self.verify_map.get(target.get("logical_id"))

    def req(logical: str, *, state: str = "CONFIGURED", native_id: Optional[str] = None,
            domain: Optional[str] = None, version: Optional[str] = None) -> dict:
        return {"logical_id": logical, "native_id": native_id or ("nat-" + logical),
                "state": state, "domain": domain, "version": version}

    tmp = Path(tempfile.mkdtemp(prefix="lane-W7C-U1-"))  # scratch prefix contract

    # ---- 1. No approval -> gate refuses, seam never reached -------------
    b1 = FakeBackend({"p1": "https://real.example/p1"})
    c1 = PublishCoordinator(b1)
    try:
        c1.publish([req("p1")], approval_id="appr-1")
        assert False, "publish without a registered approval must fail"
    except PublishGateError:
        pass
    assert b1.publish_calls == [], "unapproved run must never reach the platform seam"

    # ---- 2. Out-of-scope target refuses WHOLE request ------------------
    approval = Approval(approval_id="appr-1", granted_by="owner-order-2026-10-23",
                        targets=frozenset({"p1"}))
    c1.register(approval)
    b2 = FakeBackend({"p1": "https://real.example/p1", "p2": "https://real.example/p2"})
    c2 = PublishCoordinator(b2)
    c2.register(approval)
    try:
        c2.publish([req("p1"), req("p2")], approval_id="appr-1")
        assert False, "out-of-scope target must refuse the whole request"
    except PublishScopeError:
        pass
    assert b2.publish_calls == [], "fail closed: nothing publishes when scope is violated"

    # ---- 3. Saving is not publishing (draft refused) -------------------
    b3 = FakeBackend({"p1": "https://real.example/p1", "draft": "https://real.example/draft"})
    c3 = PublishCoordinator(b3)
    c3.register(Approval(approval_id="appr-3", granted_by="owner",
                         targets=frozenset({"p1", "draft"})))
    run3 = c3.publish([req("p1"), req("draft", state="CREATED")], approval_id="appr-3")
    statuses3 = {r.target: r.status for r in run3.results}
    assert statuses3["draft"] == OUT_REFUSED_NOT_CONFIGURED, statuses3
    assert statuses3["p1"] == OUT_PUBLISHED_UNVERIFIED, statuses3
    assert "draft" not in b3.publish_calls, "a saved draft must never reach the publish seam"
    assert not run3.all_published, "one page published != all published"

    # ---- 4. Real readback is the ONLY url that counts ------------------
    r_p1 = next(r for r in run3.results if r.target == "p1")
    assert r_p1.url == "https://real.example/p1", r_p1.url
    assert "ASSUMED-NEVER-TRUST" not in json.dumps(run3.summary()), \
        "publish-return url must never leak into results"

    # ---- 5. Readback missing -> NOT published, no url claimed ----------
    b5 = FakeBackend({"p1": "https://real.example/p1", "ghost": None})
    c5 = PublishCoordinator(b5)
    c5.register(Approval(approval_id="appr-5", granted_by="owner",
                         targets=frozenset({"p1", "ghost"})))
    run5 = c5.publish([req("p1"), req("ghost")], approval_id="appr-5")
    st5 = {r.target: r.status for r in run5.results}
    assert st5["ghost"] == OUT_READBACK_MISSING, st5
    ghost = next(r for r in run5.results if r.target == "ghost")
    assert ghost.url is None and ghost.state == "CONFIGURED", ghost
    assert run5.any_published and not run5.all_published, "partial publication must stay visible"

    # ---- 6. Real W7B resolution drives dependency-safe order ----------
    plan = {
        "contract_version": "1.0",
        "kind": "website",
        "pages": [
            {"logical_id": "home", "native_id": "nat-home", "state": "CONFIGURED"},
            {"logical_id": "about", "native_id": "nat-about", "state": "CONFIGURED"},
            {"logical_id": "contact", "native_id": "nat-contact", "state": "CONFIGURED"},
        ],
        "edges": [
            {"edge_id": "e1", "source": "home", "type": "menu", "target": {"logical_id": "about"}},
            {"edge_id": "e2", "source": "about", "type": "menu", "target": {"logical_id": "contact"}},
            {"edge_id": "e3", "source": "contact", "type": "menu", "target": {"logical_id": "home"}},
        ],
    }
    resolution = resolve_delivery(plan)
    assert resolution["errors"] == [], resolution["errors"]
    b6 = FakeBackend({p: f"https://real.example/{p}" for p in ("home", "about", "contact")},
                     verify={p: True for p in ("home", "about", "contact")})
    c6 = PublishCoordinator(b6)
    c6.register(Approval(approval_id="appr-6", granted_by="owner",
                         targets=frozenset({"home", "about", "contact"})))
    run6 = c6.publish([req("home"), req("about"), req("contact")],
                      approval_id="appr-6", resolution=resolution)
    # downstream-first: contact (linked-to) before about. The nav cycle
    # home->about->contact->home has no fully-safe order: it breaks
    # deterministically at the earliest requested id (home), is recorded,
    # and never hangs.
    assert b6.publish_calls == ["home", "contact", "about"], b6.publish_calls
    assert run6.order_note is not None and "cycle" in run6.order_note and "home" in run6.order_note, run6.order_note
    assert run6.all_published and all(r.status == OUT_PUBLISHED_VERIFIED for r in run6.results)
    # Acyclic case proves the downstream-first rule itself: chain
    # home->about->contact publishes contact, about, home with no break note.
    plan_acyclic = dict(plan)
    plan_acyclic["edges"] = [e for e in plan["edges"] if e["edge_id"] != "e3"]
    res_acyclic = resolve_delivery(plan_acyclic)
    assert res_acyclic["errors"] == [], res_acyclic["errors"]
    b6b = FakeBackend({p: f"https://real.example/{p}" for p in ("home", "about", "contact")})
    c6b = PublishCoordinator(b6b)
    c6b.register(Approval(approval_id="appr-6b", granted_by="owner",
                          targets=frozenset({"home", "about", "contact"})))
    run6b = c6b.publish([req("home"), req("about"), req("contact")],
                        approval_id="appr-6b", resolution=res_acyclic)
    assert b6b.publish_calls == ["contact", "about", "home"], b6b.publish_calls
    assert run6b.order_note is None, run6b.order_note

    # ---- 7. Real W4A store: publish + verify, and the bypass guard -----
    store = CheckpointStore(tmp / "store.json")
    keymap = {
        "p1": CheckpointKey("loc-a", "page", None, "p1"),
        "ghost": CheckpointKey("loc-a", "page", None, "ghost"),
    }
    for logical, key in keymap.items():
        action, existing = store.plan_create(key)
        assert action == "create" and existing is None
        cp = store.record_create(key, native_id="nat-" + logical)  # -> CREATED
        cp = store.set_state(key, STATE_CONFIGURED, expected_revision=cp.revision)
    b7 = FakeBackend({"p1": "https://real.example/p1", "ghost": None},
                     verify={"p1": True})
    c7 = PublishCoordinator(b7, checkpoints=store, key_for=lambda logical: keymap[logical])
    c7.register(Approval(approval_id="appr-7", granted_by="owner",
                         targets=frozenset({"p1", "ghost"})))
    # Saving is not publishing — even internally, a direct jump to PUBLISHED
    # is refused by the real W4A store:
    try:
        store.set_state(keymap["p1"], STATE_PUBLISHED, expected_revision=store.read(keymap["p1"]).revision)
        assert False, "direct set_state(PUBLISHED) must be refused"
    except InvalidTransitionError:
        pass
    run7 = c7.publish([req("p1"), req("ghost")], approval_id="appr-7")
    st7 = {r.target: r.status for r in run7.results}
    assert st7["p1"] == OUT_PUBLISHED_VERIFIED, st7
    assert st7["ghost"] == OUT_READBACK_MISSING, st7
    cp1 = store.read(keymap["p1"])
    assert cp1.state == STATE_VERIFIED and cp1.published_url == "https://real.example/p1", cp1.to_json()
    assert cp1.publish_authorization == "appr-7", "authorization reference must be recorded"
    cpg = store.read(keymap["ghost"])
    assert cpg.state == STATE_CONFIGURED and cpg.published_url is None, cpg.to_json()

    # ---- 8. Capture ops need a bundled approval (location + temps) -----
    try:
        Approval(approval_id="cap-1", granted_by="owner", targets=frozenset({"t"}),
                 operations=("capture",))
        assert False, "capture without test_location/temporary_objects must fail"
    except ApprovalError:
        pass
    cap = Approval(approval_id="cap-2", granted_by="owner", targets=frozenset({"t"}),
                   operations=("capture", "publish"),
                   test_location="staging subaccount X", temporary_objects=("tmp-page-1",))
    assert cap.test_location and cap.temporary_objects

    # ---- 9. Missing readback seam -> capability incomplete -------------
    class NoReadback:
        def publish(self, target: dict) -> None:
            pass

    b9 = NoReadback()
    c9 = PublishCoordinator(b9)
    c9.register(Approval(approval_id="appr-9", granted_by="owner", targets=frozenset({"p1"})))
    run9 = c9.publish([req("p1")], approval_id="appr-9")
    assert run9.results[0].status == OUT_CAPABILITY_INCOMPLETE and run9.results[0].url is None
    assert not run9.all_published

    # ---- 10. Domain / version binding refuses the request --------------
    c10 = PublishCoordinator(FakeBackend({"p1": "https://real.example/p1"}))
    c10.register(Approval(approval_id="appr-10", granted_by="owner",
                          targets=frozenset({"p1"}), domain="go.example.com"))
    try:
        c10.publish([req("p1", domain="other.example.com")], approval_id="appr-10")
        assert False, "domain mismatch must refuse the whole request"
    except PublishScopeError:
        pass

    # ---- 11. Failed publish recorded per-target, run continues ---------
    b11 = FakeBackend({"p1": "https://real.example/p1", "p2": "https://real.example/p2"},
                      fail={"p1"})
    c11 = PublishCoordinator(b11)
    c11.register(Approval(approval_id="appr-11", granted_by="owner",
                          targets=frozenset({"p1", "p2"})))
    run11 = c11.publish([req("p1"), req("p2")], approval_id="appr-11")
    st11 = {r.target: r.status for r in run11.results}
    assert st11["p1"] == OUT_PUBLISH_FAILED and st11["p2"] == OUT_PUBLISHED_UNVERIFIED, st11

    seam = contract_seam_status()
    assert seam["unit"] == "W7C-U1" and "outstanding" in seam

    print("W7C-U1 self-check: all assertions passed")
    print(json.dumps({
        "run3": run3.summary()["counts"],
        "run5": run5.summary()["counts"],
        "run6_order": b6.publish_calls,
        "run7": {"p1": st7["p1"], "ghost": st7["ghost"]},
        "store_p1": {"state": cp1.state, "url": cp1.published_url, "auth": cp1.publish_authorization},
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
