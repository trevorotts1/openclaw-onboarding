#!/usr/bin/env python3
"""GHL website execution adapter (stream W5, assignment W5C-U1).

Executes an approved WEBSITE page-set document (W1A npage_contract) through
the agreed W5A primitive signatures (primitives.py) on the real upstream
modules: W2-U2 recipe_transport (bounded transport, reconcile-before-retry,
never switch tools to bypass a denial) and W4A checkpoints (durable identity
keyed by location/kind/parent/logical id -- never by name). W2A
capability_inventory supplies every route; this adapter authors none.

Website semantics (GHL-DELIVERY-SPEC.md, delivery contract):
  * Menus, shared sections and general navigation are first-class website
    structure. Navigation cycles are LEGITIMATE (unlike funnel action edges);
    this adapter never applies a DAG check to website nav. The W1A validator
    owns the reference checks (menu items point at pages or external URLs,
    never at admin folders; shared sections and nav reference known pages).
  * Administrative folders are neither navigation hierarchy nor nested URL
    paths. Folder placement never derives nav_ref or url_path; those are
    explicit inputs only (url_path comes from the document's PageLocation,
    nav_ref only when the caller passes it).
  * Pages may share a role with distinct identity: logical_id is identity.
  * States PLANNED -> CREATED -> CONFIGURED only. PUBLISHED and VERIFIED are
    the W7 publishing coordinator's: saving is never publishing, a
    desired_state of "published" is recorded as pending W7 work, and nothing
    here publishes, deletes or executes anything. Whole-site publication is
    never assumed atomic and is out of scope entirely.
  * Identity allocation FIRST (read before create; reuse on an exact single
    match; ambiguous matches refused, never the first row), content SECOND,
    URL/action binding LAST (W7 link_resolution owns binding). Confirmed
    native IDs are persisted immediately into the checkpoint store so a
    resume never duplicates pages and reused business objects stay
    distinguishable from new scratch.
  * A missing write route is a capture request -- the smallest missing
    authorized operation to capture. It is reported as incomplete, never as
    done, never with a guessed selector or an "enabled" flag. Website
    container create and menu/shared-section/nav installation have NO
    verified write route in the catalog today; page create/edit routes to
    the gated managed browser builder (browser.page_content -- an in-browser
    operation, NOT a public API; execution needs the W3 managed-browser
    lease, whose gate this adapter never bypasses).
  * Website surfaces carry no verified independent read route: readback is
    executor-provided only, and an uncertain outcome is reconciled before
    any retry is considered -- never blindly retried.

Out of scope by ownership: funnel ordering/edges (W5B funnel adapter),
forms/surveys (W6), commerce (W8), URL/action binding and publication (W7),
content composition (W9), and the transport/browser execution itself
(W2/W3 -- injected here as an Executor seam).

Runnable check (assert-based self-check, no network):
    python3 shared-utils/ghl/website_adapter.py
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    from . import capability_inventory as ci
    from . import primitives as pr
    from . import recipe_transport as rt
    from ..delivery import checkpoints as ck
    from ..delivery import npage_contract as nc
except ImportError:  # script execution: python3 shared-utils/ghl/website_adapter.py
    _HERE = os.path.dirname(os.path.abspath(__file__))
    for _p in (_HERE, os.path.join(os.path.dirname(_HERE), "delivery")):
        if _p not in sys.path:
            sys.path.insert(0, _p)
    import capability_inventory as ci
    import primitives as pr
    import recipe_transport as rt
    import checkpoints as ck
    import npage_contract as nc


SITE_LOGICAL_ID = "site"
ADAPTER_VERSION = "w5c-u1.v1"

# The states this adapter may ever reach. PUBLISHED/VERIFIED are W7's.
_EXECUTABLE_STATES = (pr.DeliveryState.PLANNED, pr.DeliveryState.CREATED, pr.DeliveryState.CONFIGURED)


class WebsiteDocError(ValueError):
    """The document is not an executable website page set."""


# ---------------------------------------------------------------------------
# Document validation (website semantics; the W1A validator owns references)
# ---------------------------------------------------------------------------


def validate_website_document(doc: nc.PageSet) -> List[str]:
    """Return violations; [] means the document is executable here.

    Delegates reference/cycle semantics to the real W1A contract validator
    (nav cycles are legitimate there and here), then adds the adapter-level
    checks: it must BE a website, approved content keys must be keys the
    primitive writer may write, and the reserved site id must not collide.
    """
    if doc.kind != nc.SET_KIND_WEBSITE:
        raise WebsiteDocError(
            f"document kind {doc.kind!r} is not a website -- funnel execution "
            "belongs to the W5B funnel adapter (one adapter per builder type)"
        )
    errors: List[str] = list(nc.validate_page_set(doc))
    ids = {p.logical_id for p in doc.pages} | {f.logical_id for f in doc.admin_folders}
    if SITE_LOGICAL_ID in ids:
        errors.append(
            f"logical_id {SITE_LOGICAL_ID!r} is reserved for the website "
            "container (distinct identity)"
        )
    for p in doc.pages:
        extra = set(p.approved_content or {}) - pr.ALLOWED_CONTENT_KEYS
        if extra:
            errors.append(
                f"{p.logical_id}: approved_content carries keys the primitive "
                f"writer refuses {sorted(extra)} (allowed: {sorted(pr.ALLOWED_CONTENT_KEYS)})"
            )
        for k, v in (p.approved_content or {}).items():
            if not isinstance(v, str):
                errors.append(f"{p.logical_id}: approved_content[{k!r}] must be a string")
        try:
            int(p.revision)
        except (TypeError, ValueError):
            errors.append(f"{p.logical_id}: revision {p.revision!r} must be an integer tag")
    return errors


# ---------------------------------------------------------------------------
# Website -> primitive specs (the agreed W5A signatures)
# ---------------------------------------------------------------------------


def website_primitive_specs(
    doc: nc.PageSet,
    *,
    site_native_id: Optional[str] = None,
    nav_refs: Optional[Mapping[str, str]] = None,
) -> List[pr.PrimitiveSpec]:
    """Translate the website document into PrimitiveSpec nodes.

    Parenting is ADMINISTRATIVE only. url_path is copied from the document's
    PageLocation (an explicit input); nav_ref only from the caller's explicit
    map. Folder placement never derives either.
    """
    specs: List[pr.PrimitiveSpec] = []
    for f in doc.admin_folders:
        specs.append(
            pr.PrimitiveSpec(
                logical_id=f.logical_id,
                kind=pr.PrimitiveKind.FOLDER,
                builder_type=pr.BuilderType.WEBSITE,
                name=f.name,
                parent_logical_id=f.parent_logical_id,
            )
        )
    specs.append(
        pr.PrimitiveSpec(
            logical_id=SITE_LOGICAL_ID,
            kind=pr.PrimitiveKind.CONTAINER,
            builder_type=pr.BuilderType.WEBSITE,
            name=doc.set_id,
            slug=doc.set_id,
            native_id_hint=site_native_id,
        )
    )
    nav_refs = dict(nav_refs or {})
    for p in doc.pages:
        specs.append(
            pr.PrimitiveSpec(
                logical_id=p.logical_id,
                kind=pr.PrimitiveKind.PAGE,
                builder_type=pr.BuilderType.WEBSITE,
                name=p.name,
                slug=p.slug,
                parent_logical_id=SITE_LOGICAL_ID,
                role=p.role or "",
                intent=p.intent,
                revision=int(p.revision) if str(p.revision).lstrip("-").isdigit() else 1,
                approved_content=dict(p.approved_content) if p.approved_content else None,
                nav_ref=nav_refs.get(p.logical_id),
                url_path=p.location.url_path,
                native_id_hint=p.identities.page_id,
            )
        )
    return specs


# ---------------------------------------------------------------------------
# Website structure: menus, shared sections, general navigation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StructureBinding:
    """One website structure element (menu / shared section / nav edge).

    Installing structure has NO verified write route in the catalog today.
    The honest result is a capture request -- incomplete, never done, never a
    guessed selector. If a verified route is ever catalogued, the binding
    records it (route_available) and installation still needs its own
    captured payload semantics before this adapter will emit an operation.
    """

    structure_id: str
    structure_kind: str  # "menu" | "shared_section" | "nav"
    refs: Tuple[str, ...]
    status: str  # "capture_request" | "route_available"
    capture_request: str = ""
    provenance: str = ""
    capability_id: str = ""


def structure_bindings(doc: nc.PageSet) -> List[StructureBinding]:
    """Menus/shared sections/general navigation, referenced and honest.

    Cycles in nav are legitimate: edges are recorded as given, never
    topologically sorted, never cycle-checked.
    """
    decision = pr.resolve_operation(
        ci.OpClass.EDIT, kind=pr.PrimitiveKind.CONTAINER, builder_type=pr.BuilderType.WEBSITE
    )
    bindings: List[StructureBinding] = []
    for m in doc.menus:
        refs = tuple(i.page_logical_id or i.external_url or "" for i in m.items)
        bindings.append(_binding(f"menu:{m.logical_id}", "menu", refs, decision))
    for s in doc.shared_sections:
        bindings.append(
            _binding(f"shared_section:{s.logical_id}", "shared_section", tuple(s.page_logical_ids), decision)
        )
    for n in doc.nav:
        bindings.append(
            _binding(f"nav:{n.from_logical_id}->{n.to_logical_id}", "nav", (n.from_logical_id, n.to_logical_id), decision)
        )
    return bindings


def _binding(sid: str, kind: str, refs: Tuple[str, ...], decision: pr.RouteDecision) -> StructureBinding:
    if decision.status == "missing":
        return StructureBinding(
            structure_id=sid,
            structure_kind=kind,
            refs=refs,
            status="capture_request",
            capture_request=decision.capture_request,
            provenance=decision.provenance,
        )
    return StructureBinding(
        structure_id=sid,
        structure_kind=kind,
        refs=refs,
        status="route_available",
        provenance=decision.provenance,
        capability_id=decision.capability.capability_id if decision.capability else "",
    )


# ---------------------------------------------------------------------------
# Planning and execution
# ---------------------------------------------------------------------------


@dataclass
class WebsitePlan:
    doc: nc.PageSet
    location: str
    plan: pr.BuildPlan
    bindings: List[StructureBinding] = field(default_factory=list)
    nav_refs: Dict[str, str] = field(default_factory=dict)


@dataclass
class WebsiteDelivery:
    location: str
    delivery_result: nc.DeliveryResult
    rows: List[pr.ExecutionRow]
    receipts: List[pr.PrimitiveOp]
    bindings: List[StructureBinding]
    restrictions: List[str]
    contract_violations: List[str]
    checkpointed: List[str] = field(default_factory=list)


def plan_website(
    doc: nc.PageSet,
    *,
    location: str,
    existing: Sequence[pr.ExistingObject] = (),
    site_native_id: Optional[str] = None,
    nav_refs: Optional[Mapping[str, str]] = None,
    dynamic_confirmed: bool = False,
) -> WebsitePlan:
    """Identity allocation FIRST, then content ops -- via the W5A planner.

    existing is a verified listing (read before create). Website surfaces
    have no verified read route in the catalog, so callers usually supply
    checkpointed identities (see checkpointed_existing); an ambiguous match
    still blocks rather than guessing.
    """
    violations = validate_website_document(doc)
    if violations:
        raise WebsiteDocError("website document refused: " + "; ".join(violations))
    specs = website_primitive_specs(doc, site_native_id=site_native_id, nav_refs=nav_refs)
    built = pr.plan_primitives(
        specs,
        location=location,
        existing=list(existing),
        dynamic_confirmed=dynamic_confirmed,
    )
    return WebsitePlan(
        doc=doc,
        location=location,
        plan=built,
        bindings=structure_bindings(doc),
        nav_refs=dict(nav_refs or {}),
    )


def execute_website(
    wplan: WebsitePlan,
    executor: pr.Executor,
    *,
    store: Optional["ck.CheckpointStore"] = None,
) -> WebsiteDelivery:
    """Run the planned primitives parents-before-children and map real rows.

    Never publishes. Every page yields exactly one result row -- a missing
    capability is a reported restriction, never a silently dropped page.
    When a checkpoint store is supplied, confirmed identities are persisted
    immediately and reused objects are provenance-marked (reused vs
    new-scratch) so a resume never duplicates pages.
    """
    report = pr.execute_plan(wplan.plan, executor)
    doc = wplan.doc
    restrictions: List[str] = []

    page_ids = {p.logical_id for p in doc.pages}
    op_results: Dict[str, List[nc.OperationResult]] = {}
    native_ids: Dict[str, dict] = {}
    embeds: Dict[str, List[str]] = {}
    links: Dict[str, List[str]] = {}

    for row in report.rows:
        spec = next(s for s in wplan.plan.specs if s.logical_id == row.logical_id)
        results = op_results.setdefault(row.logical_id, [])
        for res in row.op_results:
            results.append(
                nc.OperationResult(
                    operation=f"primitive {spec.kind.value}",
                    status=_result_status(res.outcome),
                    detail=res.note,
                    native_id=res.native_id or None,
                    readback=dict(res.readback),
                )
            )
        if not results:
            results.append(
                nc.OperationResult(
                    operation=f"identity {spec.kind.value}",
                    status=_row_result_status(row.status),
                    detail=row.note or row.status,
                    native_id=row.native_id or None,
                )
            )
        if row.logical_id in page_ids:
            native_ids[row.logical_id] = {
                "page_id": row.native_id or None,
                "container_id": _native_of(wplan, SITE_LOGICAL_ID, report),
                "folder_id": _native_of(wplan, _folder_of(doc, row.logical_id), report),
            }
            content = spec.approved_content or {}
            if "embed" in content:
                embeds[row.logical_id] = [content["embed"]]
            # URL/action binding is LAST and belongs to W7 link_resolution:
            # links stay empty until real URLs are read back there.

    for alloc in report.missing:
        restrictions.append(
            f"{alloc.logical_id}: {alloc.capture_request} [{alloc.provenance}] "
            "-- capability incomplete, never done"
        )
    for b in wplan.bindings:
        if b.status == "capture_request":
            restrictions.append(
                f"{b.structure_id}: {b.capture_request} [{b.provenance}] "
                "-- capability incomplete, never done"
            )
    if any(p.desired_state == nc.DESIRED_PUBLISHED for p in doc.pages):
        restrictions.append(
            "desired_state=published is NOT executed here: the W7 publishing "
            "coordinator owns PUBLISHED/VERIFIED (saving is never publishing; "
            "publication is dependency-gated and never assumed atomic)"
        )
    restrictions.append(
        "website surfaces have no verified independent read route in the "
        "catalog: readback is executor-provided only (outstanding)"
    )
    restrictions.append(
        "URL/action binding is deferred to W7 link_resolution: no real public "
        "URL is claimed by this adapter"
    )

    delivery = nc.DeliveryResult(
        set_id=doc.set_id,
        page_results={k: v for k, v in op_results.items() if k in page_ids},
        native_ids=native_ids,
        embeds=embeds,
        links=links,
        restrictions=restrictions,
    )
    violations = nc.check_no_dropped_pages(doc, delivery)

    # states are distinct and capped: this adapter never reaches PUBLISHED
    for row in report.rows:
        if row.state not in _EXECUTABLE_STATES:
            raise AssertionError(f"illegal state escaped the primitive layer: {row.state}")

    checkpointed: List[str] = []
    if store is not None:
        checkpointed = _persist(store, wplan, report, restrictions)

    return WebsiteDelivery(
        location=wplan.location,
        delivery_result=delivery,
        rows=report.rows,
        receipts=report.receipts,
        bindings=wplan.bindings,
        restrictions=restrictions,
        contract_violations=violations,
        checkpointed=checkpointed,
    )


def _result_status(outcome: pr.Outcome) -> str:
    if outcome is pr.Outcome.OK:
        return nc.RESULT_OK
    if outcome is pr.Outcome.UNCERTAIN:
        return nc.RESULT_UNCERTAIN
    return nc.RESULT_FAILED


def _row_result_status(status: str) -> str:
    if status in ("created", "configured", "reused"):
        return nc.RESULT_OK
    if status == "uncertain_unreconciled":
        return nc.RESULT_UNCERTAIN
    return nc.RESULT_FAILED


def _native_of(wplan: WebsitePlan, logical_id: Optional[str], report: pr.ExecutionReport) -> Optional[str]:
    if not logical_id:
        return None
    try:
        row = report.row(logical_id)
    except KeyError:
        rec = wplan.plan.ledger.get(logical_id)
        return rec.native_id if rec else None
    return row.native_id or None


def _folder_of(doc: nc.PageSet, page_logical_id: str) -> Optional[str]:
    for p in doc.pages:
        if p.logical_id == page_logical_id:
            return p.location.admin_folder_logical_id
    return None


# ---------------------------------------------------------------------------
# Durable identity (W4A checkpoints): read before create, resume never dupes
# ---------------------------------------------------------------------------


def checkpointed_existing(
    store: "ck.CheckpointStore", location: str, doc: nc.PageSet
) -> Tuple[List[pr.ExistingObject], Dict[str, str]]:
    """(existing listing, native_id hints) from checkpointed identities.

    Reused as `existing`/`site_native_id`/PageNode hints on a re-plan, so a
    resume binds to the same native objects instead of creating duplicates.
    """
    existing: List[pr.ExistingObject] = []
    hints: Dict[str, str] = {}
    nodes: List[Tuple[str, pr.PrimitiveKind, Optional[str], str]] = []
    for f in doc.admin_folders:
        nodes.append((f.logical_id, pr.PrimitiveKind.FOLDER, f.parent_logical_id, f.name))
    nodes.append((SITE_LOGICAL_ID, pr.PrimitiveKind.CONTAINER, None, doc.set_id))
    for p in doc.pages:
        nodes.append((p.logical_id, pr.PrimitiveKind.PAGE, SITE_LOGICAL_ID, p.name))
    for logical_id, kind, parent, _name in nodes:
        cp = store.read(ck.CheckpointKey(location, kind.value, parent, logical_id))
        if cp is not None and cp.native_id:
            hints[logical_id] = cp.native_id
    for logical_id, kind, parent, name in nodes:
        if logical_id not in hints:
            continue
        existing.append(
            pr.ExistingObject(
                kind=kind,
                name=name,
                native_id=hints[logical_id],
                builder_type=pr.BuilderType.WEBSITE,
                parent_native_id=hints.get(parent) if parent else None,
            )
        )
    return existing, hints


def _persist(
    store: "ck.CheckpointStore",
    wplan: WebsitePlan,
    report: pr.ExecutionReport,
    restrictions: List[str],
) -> List[str]:
    """Persist confirmed identities immediately; never re-create a key."""
    saved: List[str] = []
    for row in report.rows:
        spec = next(s for s in wplan.plan.specs if s.logical_id == row.logical_id)
        key = ck.CheckpointKey(
            wplan.location, spec.kind.value, spec.parent_logical_id, spec.logical_id
        )
        plan_mode, _ = store.plan_create(key)
        if plan_mode == "blocked-pending":
            restrictions.append(
                f"{spec.logical_id}: checkpoint has an unresolved operation; "
                "not re-attempted (resume reconciles first)"
            )
            continue
        if plan_mode == "reuse":
            saved.append(key.token())  # already checkpointed: resume, no duplicate
            continue
        if row.status == "reused" and row.native_id:
            store.adopt(key, native_id=row.native_id, name=spec.name, slug=spec.slug)
            saved.append(key.token())
        elif row.native_id:
            cp = store.record_create(key, name=spec.name, slug=spec.slug, native_id=row.native_id)
            saved.append(key.token())
            if row.state is pr.DeliveryState.CONFIGURED and cp.state == ck.STATE_CREATED:
                store.set_state(key, ck.STATE_CONFIGURED, cp.revision)
        else:
            store.record_create(key, name=spec.name, slug=spec.slug)  # PLANNED until confirmed
            saved.append(key.token())
    return saved


# ---------------------------------------------------------------------------
# Transport seam: the real W2-U2 recipe transport behind the primitive
# Executor protocol. ONE retry authority (the runner's bounded, reconcile-
# before-retry budget) -- exhausted transport budgets are terminal here.
# ---------------------------------------------------------------------------


class RecipeExecutor:
    """Bridge PrimitiveOp -> recipe_transport.RecipeRunner.

    The runner re-selects the route from the same W2A catalog; a step that
    lands on a DIFFERENT capability than the primitive planned is refused
    (never switch tools to bypass a denial). Uncertain outcomes surface as
    UNCERTAIN for the primitive layer to reconcile -- never blind-retried.
    """

    def __init__(
        self,
        runner: "rt.RecipeRunner",
        *,
        native_id_of: Optional[Callable[["rt.StepRecord"], str]] = None,
    ) -> None:
        self._runner = runner
        self._native_id_of = native_id_of or _native_id_from_body
        self.calls: List[pr.PrimitiveOp] = []

    def run(self, op: pr.PrimitiveOp) -> pr.OpResult:
        self.calls.append(op)
        req = rt.OperationRequest(
            op_class=op.op_class,
            location=op.target.get("location", ""),
            target=op.target.get("name", ""),
            resource=op.capability.resource,
            surface=_surface_for(op),
            payload=dict(op.payload),
            expected=dict(op.payload) if op.action == "readback" else {},
        )
        try:
            rec = self._runner.run_step(req)
        except rt.RouteDenied as exc:
            return pr.OpResult(pr.Outcome.REFUSED, note=f"denied at transport: {exc}")
        except rt.RecipeError as exc:
            return pr.OpResult(pr.Outcome.ERROR, note=f"transport refused: {exc}")
        if rec.capability_id != op.capability.capability_id:
            return pr.OpResult(
                pr.Outcome.REFUSED,
                note=(
                    f"route switch refused: primitive planned "
                    f"{op.capability.capability_id}, transport selected {rec.capability_id} "
                    "-- never switch tools to bypass a denial"
                ),
            )
        body = rec.attempts[-1].body if rec.attempts else ""
        native_id = self._native_id_of(rec)
        readback = {"native_id": native_id} if native_id else {}
        if rec.final in (rt.FinalStatus.OK, rt.FinalStatus.OK_RECONCILED):
            return pr.OpResult(
                pr.Outcome.OK,
                native_id=native_id,
                readback=readback,
                note=f"transport {rec.final.value}; readback={rec.readback}",
            )
        if rec.final is rt.FinalStatus.OK_UNVERIFIED:
            return pr.OpResult(
                pr.Outcome.UNCERTAIN,
                native_id=native_id,
                readback=readback,
                note="transport completed but readback unverified -- reconcile before any retry",
            )
        if rec.final is rt.FinalStatus.UNRESOLVED:
            return pr.OpResult(
                pr.Outcome.UNCERTAIN,
                native_id=native_id,
                note="transport unresolved (uncertain outcome) -- reconcile before any retry",
            )
        # exhausted/terminal at the transport: its bounded retry budget is the
        # ONLY retry authority -- never re-run an exhausted operation here.
        return pr.OpResult(
            pr.Outcome.ERROR,
            note=(
                f"transport terminal: {rec.final.value} "
                f"(bounded at {1 + ci.MAX_429_RETRIES + ci.MAX_5XX_RETRIES} attempts; "
                "no second retry authority); body=" + body[:120]
            ),
        )


def _surface_for(op: pr.PrimitiveOp) -> str:
    """Mirror primitives' surface mapping so the runner re-selects the route
    under the SAME query the primitive planner used (route pinning)."""
    if op.kind is pr.PrimitiveKind.PAGE:
        return "page"
    return "funnel" if op.builder_type is pr.BuilderType.FUNNEL else "page"


def _native_id_from_body(rec: "rt.StepRecord") -> str:
    for att in reversed(rec.attempts):
        try:
            data = json.loads(att.body) if att.body else None
        except ValueError:
            continue
        if isinstance(data, dict):
            for key in ("native_id", "id"):
                value = data.get(key)
                if isinstance(value, str) and value:
                    return value
    return ""


# ---------------------------------------------------------------------------
# Runnable check (assert-based self-check; offline, no live calls)
# ---------------------------------------------------------------------------


def _page(lid: str, name: str, slug: str, path: str, **kw) -> nc.PageNode:
    return nc.PageNode(
        logical_id=lid,
        name=name,
        slug=slug,
        builder_type="html",
        intent=kw.pop("intent", "ordinary website page"),
        location=nc.PageLocation(url_path=path, **kw.pop("loc", {})),
        **kw,
    )


def self_check() -> None:
    # 0. Instrument control: the real upstream validator is honest.
    assert ci.validate_inventory() == [], "capability_inventory reports violations"

    # 1. Valid website document passes both validators (control).
    doc = nc.PageSet(
        set_id="elevation-site",
        kind=nc.SET_KIND_WEBSITE,
        pages=[
            _page("home", "Home", "home", "/", approved_content={"html": "<h1>hi</h1>"}),
            _page("about", "About", "about", "/about"),
            _page("contact", "Contact", "contact", "/contact"),
        ],
        menus=[nc.Menu(logical_id="main", name="Main", items=[
            nc.MenuItem(label="Home", page_logical_id="home"),
            nc.MenuItem(label="About", page_logical_id="about"),
            nc.MenuItem(label="Book", external_url="https://example.com/book"),
        ])],
        shared_sections=[nc.SharedSection(logical_id="footer", name="Footer", page_logical_ids=["home", "about"])],
        nav=[
            nc.NavEdge(from_logical_id="home", to_logical_id="about"),
            nc.NavEdge(from_logical_id="about", to_logical_id="contact"),
            # cycles are legitimate on websites:
            nc.NavEdge(from_logical_id="contact", to_logical_id="home"),
            nc.NavEdge(from_logical_id="about", to_logical_id="about"),
        ],
        admin_folders=[nc.AdminFolder(logical_id="web", name="Web", parent_logical_id=None)],
    )
    for p in doc.pages:
        p.location.admin_folder_logical_id = "web"
    assert validate_website_document(doc) == [], validate_website_document(doc)

    # 2. A funnel document is refused here (W5B owns funnels) -- and a nav
    #    cycle is NEVER a defect (contrast: the funnel DAG is W5B/W1 territory).
    funnel = nc.PageSet(set_id="sales-funnel", kind=nc.SET_KIND_FUNNEL, pages=list(doc.pages))
    try:
        validate_website_document(funnel)
    except WebsiteDocError:
        pass
    else:
        raise AssertionError("funnel document must be refused by the website adapter")
    cyclic = nc.PageSet(
        set_id="cycle-site", kind=nc.SET_KIND_WEBSITE,
        pages=[_page("a", "A", "a", "/a"), _page("b", "B", "b", "/b")],
        nav=[nc.NavEdge(from_logical_id="a", to_logical_id="b"), nc.NavEdge(from_logical_id="b", to_logical_id="a")],
    )
    assert validate_website_document(cyclic) == []
    cyclic_plan = plan_website(cyclic, location="loc-1")
    assert cyclic_plan.bindings and all(b.structure_kind == "nav" for b in cyclic_plan.bindings)

    # 3. Document validator (real W1A) catches what the adapter must not
    #    re-invent: dangling menu refs and folder-as-nav are refusals.
    bad = nc.PageSet(
        set_id="bad-site", kind=nc.SET_KIND_WEBSITE,
        pages=[_page("a", "A", "a", "/a")],
        menus=[nc.Menu(logical_id="m", name="M", items=[nc.MenuItem(label="X", page_logical_id="ghost")])],
        admin_folders=[nc.AdminFolder(logical_id="fold", name="Fold")],
        nav=[nc.NavEdge(from_logical_id="a", to_logical_id="fold")],
    )
    found = validate_website_document(bad)
    assert any("unknown page 'ghost'" in e for e in found), found
    assert any("admin folder" in e for e in found), found

    # 4. Identity allocation FIRST: website container create has NO verified
    #    write route -> capture request (incomplete, never done), and the page
    #    is blocked behind its parent, never silently dropped.
    wplan = plan_website(doc, location="loc-1")
    assert wplan.plan.allocation(SITE_LOGICAL_ID).disposition is pr.Disposition.MISSING_CAPABILITY
    assert "capture the smallest missing authorized operation" in wplan.plan.allocation(SITE_LOGICAL_ID).capture_request
    assert wplan.plan.allocation("home").disposition is pr.Disposition.BLOCKED_PARENT
    delivery = execute_website(wplan, pr.FakeExecutor())
    assert nc.check_no_dropped_pages(doc, delivery.delivery_result) == [], delivery.contract_violations
    assert set(delivery.delivery_result.page_results) == {"home", "about", "contact"}
    assert any("capability incomplete, never done" in r for r in delivery.restrictions)

    # 5. Update binding on an explicit native ID: the site container is reused
    #    (read before create), pages create via the GATED managed browser route,
    #    content configures after; state reaches CONFIGURED, never PUBLISHED.
    wplan2 = plan_website(doc, location="loc-1", site_native_id="site-77")
    assert wplan2.plan.allocation(SITE_LOGICAL_ID).disposition is pr.Disposition.REUSE
    assert wplan2.plan.allocation("home").disposition is pr.Disposition.CREATE
    page_ops = [op for op in wplan2.plan.ops if op.kind is pr.PrimitiveKind.PAGE]
    assert page_ops, "pages must plan real operations"
    assert all(op.capability.capability_id == "browser.page_content" for op in page_ops)
    assert all(op.capability.transport is ci.Transport.MANAGED_BROWSER for op in page_ops)
    fake = pr.FakeExecutor()
    delivery2 = execute_website(wplan2, fake)
    home = delivery2.delivery_result.page_results["home"]
    assert home and home[-1].status == nc.RESULT_OK
    assert delivery2.delivery_result.native_ids["home"]["page_id"] == "native-home"
    assert delivery2.delivery_result.native_ids["home"]["container_id"] == "site-77"
    row = next(r for r in delivery2.rows if r.logical_id == "home")
    assert row.state is pr.DeliveryState.CONFIGURED
    assert all(r.state in _EXECUTABLE_STATES for r in delivery2.rows)
    for op in delivery2.receipts:
        assert "url_path" not in op.payload and "nav_ref" not in op.payload
        assert "url_path" not in op.target and "nav_ref" not in op.target

    # 6. Explicit url_path flows from the document's PageLocation; nav_ref only
    #    from the caller (never derived from the administrative folder).
    spec_home = next(s for s in website_primitive_specs(doc) if s.logical_id == "home")
    assert spec_home.url_path == "/" and spec_home.nav_ref is None
    spec_nav = next(
        s for s in website_primitive_specs(doc, nav_refs={"home": "top"}) if s.logical_id == "home"
    )
    assert spec_nav.nav_ref == "top"
    spec_folder = next(s for s in website_primitive_specs(doc) if s.logical_id == "web")
    assert spec_folder.url_path is None and spec_folder.nav_ref is None

    # 7. Structure bindings: menus/shared sections/nav install has NO write
    #    route today -> capture requests, recorded as restrictions, and links
    #    stay empty until W7 binds real URLs. desired_state=published is never
    #    executed here.
    published = nc.PageSet(
        set_id="pub-site", kind=nc.SET_KIND_WEBSITE,
        pages=[_page("a", "A", "a", "/a", desired_state=nc.DESIRED_PUBLISHED)],
    )
    wplan3 = plan_website(published, location="loc-1", site_native_id="site-1")
    delivery3 = execute_website(wplan3, pr.FakeExecutor())
    assert any("W7 publishing coordinator owns PUBLISHED/VERIFIED" in r for r in delivery3.restrictions)
    assert delivery3.delivery_result.links == {}
    assert any(b.status == "capture_request" for b in wplan.bindings)
    assert all("never a guessed selector" in b.capture_request for b in wplan.bindings if b.status == "capture_request")

    # 8. Ambiguous reuse is refused (never the first row) -- via the real W5A
    #    planner -- and the page row reports the block instead of vanishing.
    dup = [
        pr.ExistingObject(pr.PrimitiveKind.CONTAINER, "elevation-site", "s1", pr.BuilderType.WEBSITE),
        pr.ExistingObject(pr.PrimitiveKind.CONTAINER, "elevation-site", "s2", pr.BuilderType.WEBSITE),
    ]
    wplan4 = plan_website(doc, location="loc-1", existing=dup)
    assert wplan4.plan.allocation(SITE_LOGICAL_ID).disposition is pr.Disposition.AMBIGUOUS
    delivery4 = execute_website(wplan4, pr.FakeExecutor())
    assert set(delivery4.delivery_result.page_results) == {"home", "about", "contact"}
    assert nc.check_no_dropped_pages(doc, delivery4.delivery_result) == []

    # 9. REAL upstream transport: the RecipeExecutor bridge runs the actual
    #    W2-U2 RecipeRunner over the gated browser capability, with readback.
    log: List[str] = []
    # allocations run parents-first then by logical id (about, contact, home):
    # one scripted result per planned page op, in execution order.
    scripted = rt.ScriptedExecutor(
        [
            rt.AttemptResult(status="ok", body='{"native_id": "pg-a"}'),
            rt.AttemptResult(status="ok", body='{"native_id": "pg-c"}'),
            rt.AttemptResult(status="ok", body='{"native_id": "pg-h"}'),
            rt.AttemptResult(status="ok", body='{"native_id": "pg-h"}'),
        ],
        log=log,
    )
    runner = rt.RecipeRunner(
        {ci.Transport.MANAGED_BROWSER: scripted},
        probe=rt.scripted_probe(log, [(rt.ReconcileVerdict.APPLIED, "readback confirmed")]),
        sleep=lambda _s: None,
    )
    bridge = RecipeExecutor(runner)
    page_plan = plan_website(doc, location="loc-1", site_native_id="site-77")
    delivery5 = execute_website(page_plan, bridge)
    assert delivery5.delivery_result.native_ids["home"]["page_id"] == "pg-h"
    assert delivery5.delivery_result.native_ids["about"]["page_id"] == "pg-a"
    assert delivery5.delivery_result.native_ids["contact"]["page_id"] == "pg-c"
    assert all("browser.page_content" in c for c in scripted.calls), scripted.calls
    home5 = next(r for r in delivery5.rows if r.logical_id == "home")
    assert home5.state is pr.DeliveryState.CONFIGURED and home5.native_id == "pg-h"
    assert nc.check_no_dropped_pages(doc, delivery5.delivery_result) == []

    # 10. ONE retry authority: transport-level rate-limit exhaustion is
    #     terminal at the bridge -- the primitive layer never re-runs an
    #     exhausted operation (no squared retry), and a denial is terminal.
    limited = rt.ScriptedExecutor([rt.AttemptResult(status="http_error", http_status=429, body="slow down")] * 4, log=log)
    runner2 = rt.RecipeRunner({ci.Transport.MANAGED_BROWSER: limited}, sleep=lambda _s: None)
    bridge2 = RecipeExecutor(runner2)
    solo = replace(
        next(s for s in website_primitive_specs(doc, site_native_id="site-77") if s.logical_id == "about"),
        parent_logical_id=None,
        parent_native_id="site-77",  # parent outside this batch, explicit native id
    )
    one = pr.plan_primitives([solo], location="loc-1")
    rep = pr.execute_plan(one, bridge2)
    assert rep.row("about").status == "failed_error", rep.row("about").status
    assert len(limited.calls) == 1 + ci.MAX_429_RETRIES, limited.calls
    denied = rt.ScriptedExecutor([rt.AttemptResult(status="http_error", http_status=401, body="expired")], log=log)
    runner3 = rt.RecipeRunner({ci.Transport.MANAGED_BROWSER: denied}, sleep=lambda _s: None)
    rep2 = pr.execute_plan(one, RecipeExecutor(runner3))
    assert rep2.row("about").status == "failed_refused", rep2.row("about").status
    assert len(denied.calls) == 1, "a denial is terminal -- never retried, never tool-switched"

    # 11. Route pinning: a transport step landing on a DIFFERENT capability is
    #     refused before the result is accepted (negative control: injected
    #     route drift must fail loudly, never pass silently).
    class _DriftRunner:
        def run_step(self, req: "rt.OperationRequest") -> "rt.StepRecord":
            return rt.StepRecord(
                op_class=req.op_class.value,
                resource=req.resource,
                location=req.location,
                target=req.target,
                capability_id="rest.some-other-route",
                route="POST /invented/endpoint",
                transport="public_rest",
                readback_required=False,
            )

    bad_op = one.ops[0]
    pin = RecipeExecutor(_DriftRunner()).run(bad_op)
    assert pin.outcome is pr.Outcome.REFUSED and "route switch refused" in pin.note

    # 12. Durable identity (real W4A store): confirmed IDs persist immediately;
    #     a resume re-plans against them WITHOUT duplicating, and reused
    #     business objects stay distinguishable from new scratch.
    import tempfile

    tmp = tempfile.mktemp(prefix="lane-W5C-U1-store-", suffix=".json")
    try:
        store = ck.CheckpointStore(tmp)
        wplan5 = plan_website(doc, location="loc-1", site_native_id="site-77")
        delivery6 = execute_website(wplan5, pr.FakeExecutor(), store=store)
        assert delivery6.checkpointed, "confirmed identities must persist"
        existing, hints = checkpointed_existing(store, "loc-1", doc)
        assert hints.get(SITE_LOGICAL_ID) == "site-77"
        assert hints.get("home") == "native-home"
        wplan6 = plan_website(doc, location="loc-1", site_native_id=hints.get(SITE_LOGICAL_ID), existing=existing)
        assert wplan6.plan.allocation(SITE_LOGICAL_ID).disposition is pr.Disposition.REUSE
        assert wplan6.plan.allocation("home").disposition is pr.Disposition.REUSE
        assert all(op.action != "create" for op in wplan6.plan.ops), "resume must never re-create"
        before = len(store.checkpoints)
        execute_website(wplan6, pr.FakeExecutor(), store=store)
        assert len(store.checkpoints) == before, "resume must not duplicate checkpoint rows"
        cp = store.read(ck.CheckpointKey("loc-1", "page", SITE_LOGICAL_ID, "home"))
        assert cp is not None and cp.native_id == "native-home"
        assert cp.provenance in (ck.PROVENANCE_REUSED, ck.PROVENANCE_NEW_SCRATCH)
    finally:
        for suffix in ("", ".tmp"):
            if os.path.exists(tmp + suffix):
                os.remove(tmp + suffix)

    # 13. Never-publish guard: PUBLISHED/VERIFIED are unreachable, and the
    #     checkpoint store refuses a PUBLISHED set_state even if asked.
    assert set(r.state for r in delivery2.rows) <= set(_EXECUTABLE_STATES)
    try:
        pr.advance_state(pr.DeliveryState.CREATED, pr.DeliveryState.PUBLISHED)
    except ValueError:
        pass
    else:
        raise AssertionError("PUBLISHED must be refused (W7 owns it)")

    # 14. Negative controls: a dropped page row and unapproved content keys are
    #     caught (injected defects must fail loudly, never pass silently).
    truncated = nc.DeliveryResult(set_id=doc.set_id, page_results={"home": [nc.OperationResult("create", nc.RESULT_OK)]})
    misses = nc.check_no_dropped_pages(doc, truncated)
    assert any("about" in e and "never silently dropped" in e for e in misses), misses
    poisoned = nc.PageSet(
        set_id="poison-site", kind=nc.SET_KIND_WEBSITE,
        pages=[_page("a", "A", "a", "/a", approved_content={"html": "<p>x</p>", "iframe_src": "evil"})],
    )
    found2 = validate_website_document(poisoned)
    assert any("iframe_src" in e for e in found2), found2


if __name__ == "__main__":
    self_check()
    print("website_adapter self-check: PASS")
    print(f"  consumed: primitives (W5A-U1), npage_contract (W1A-U1), "
          f"recipe_transport (W2-U2), checkpoints (W4A-U1); adapter {ADAPTER_VERSION}")
    print("  website container create + menu/shared-section/nav install: "
          "capture requests (incomplete, never done)")
    print("  page create/edit routes to: browser.page_content (gated managed browser)")
    print("  states stop at CONFIGURED; PUBLISHED/VERIFIED belong to W7 (never executed here)")
