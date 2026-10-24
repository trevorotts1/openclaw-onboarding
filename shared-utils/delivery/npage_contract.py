#!/usr/bin/env python3
"""npage_contract.py — versioned N-page delivery schema + compatibility contract (W1A-U1).

WHY THIS EXISTS
---------------
Every GHL delivery lane (route adapters, checkpoints, funnel/website adapters,
page scheduling, link resolution, publishing) must agree on ONE shape for a
delivered page set. This module is that normative contract: a versioned schema
for funnel AND website page sets built from stable logical IDs and actual page
nodes — never a fixed role-slot count. 4/12/20 pages are examples, not caps;
Signature 3/5/7 presets are preserved through adapters and never imposed here.

WHAT IT RECORDS (GHL-DELIVERY-SPEC.md, "Delivery contract (W1 owns the
normative versioned schema)"):
  * per page: location, builder type, intent, revision, approvals,
    folder/container/page identities, name/slug, approved content, native
    components, product/price references, desired draft/publication state
  * administrative folders are NOT the navigation hierarchy and NOT nested
    URL paths — three separate structures, three separate ID spaces
  * funnels: explicit ordering + explicit accept/decline/submit/success/error
    edges (nothing inferred from page roles)
  * websites: menus, shared sections, general navigation (cycles legitimate)
  * pages may share a role; identity is the logical ID, never the role
  * states PLANNED -> CREATED -> CONFIGURED -> PUBLISHED -> VERIFIED are
    distinct; transitions move forward only (saving is not publishing)
  * work order: allocate/reconcile identities FIRST, then content, then bind
    actual URLs/actions (enforced by check_phase_order)
  * delivery results carry native IDs, embeds, links, per-operation results;
    real platform restrictions are reported and pages are never silently
    dropped (check_no_dropped_pages)

VERSIONING / COMPATIBILITY CONTRACT
-----------------------------------
SCHEMA_VERSION is MAJOR.MINOR.PATCH.
  MAJOR   a field was removed, renamed, or changed meaning. A reader rejects
          documents of a different MAJOR ("incompatible").
  MINOR   additive only (new optional fields, new enum members). A reader
          accepts any document of its own MAJOR: MINOR <= its own is fully
          known ("ok"); MINOR > its own is read as a compatible subset —
          unknown additive fields are ignored, never an error
          ("ok-unknown-fields").
  PATCH   clarification only; no shape change.
A writer never downgrades a document's schema_version to please an older
reader; it reports the real platform restriction instead. Nothing here
silently drops a page.

USAGE
-----
    python3 shared-utils/delivery/npage_contract.py --self-test
    python3 shared-utils/delivery/npage_contract.py plan.json

Exit 0 = self-test passed / every document valid; 1 = validation errors
printed one per line; 2 = usage or I/O error. Stdlib only (repo convention).
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = "1.0.0"

SET_KIND_FUNNEL = "funnel"
SET_KIND_WEBSITE = "website"
SET_KINDS = (SET_KIND_FUNNEL, SET_KIND_WEBSITE)

# Distinct delivery states. Saving is not publishing: every state is its own
# fact and transitions move forward only.
STATE_PLANNED = "PLANNED"
STATE_CREATED = "CREATED"
STATE_CONFIGURED = "CONFIGURED"
STATE_PUBLISHED = "PUBLISHED"
STATE_VERIFIED = "VERIFIED"
PAGE_STATES = (
    STATE_PLANNED,
    STATE_CREATED,
    STATE_CONFIGURED,
    STATE_PUBLISHED,
    STATE_VERIFIED,
)
_RANK_STATE = {s: i for i, s in enumerate(PAGE_STATES)}

# Funnel action-edge kinds, explicit in the model — never inferred from roles.
EDGE_ACCEPT = "accept"
EDGE_DECLINE = "decline"
EDGE_SUBMIT = "submit"
EDGE_SUCCESS = "success"
EDGE_ERROR = "error"
EDGE_KINDS = (EDGE_ACCEPT, EDGE_DECLINE, EDGE_SUBMIT, EDGE_SUCCESS, EDGE_ERROR)

DESIRED_DRAFT = "draft"
DESIRED_PUBLISHED = "published"
DESIRED_STATES = (DESIRED_DRAFT, DESIRED_PUBLISHED)

RESULT_OK = "ok"
RESULT_FAILED = "failed"
RESULT_UNCERTAIN = "uncertain"
RESULT_STATUSES = (RESULT_OK, RESULT_FAILED, RESULT_UNCERTAIN)

COMPAT_OK = "ok"
COMPAT_UNKNOWN_FIELDS = "ok-unknown-fields"
COMPAT_INCOMPATIBLE = "incompatible"

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class ContractError(ValueError):
    """Raised when a document cannot be parsed into the contract at all."""


# ---------------------------------------------------------------------------
# Page nodes
# ---------------------------------------------------------------------------


@dataclass
class NativeIdentities:
    """Native GHL identities, allocated AFTER planning, reconciled on resume.

    None means "not allocated yet" — never invent a native ID.
    """

    folder_id: Optional[str] = None
    container_id: Optional[str] = None
    page_id: Optional[str] = None


@dataclass
class BoundRefs:
    """Actual URLs/actions read back from the platform, bound LAST.

    Planned url_path lives on the page node; this holds what really exists.
    """

    urls: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


@dataclass
class Approval:
    """One approval record: who approved which content revision, when."""

    approver: str
    content_revision: str
    approved_at: str  # ISO 8601 timestamp, truthful


@dataclass
class PageNode:
    """One actual page. N of these per set — never a fixed role-slot count."""

    logical_id: str  # stable identity; unique per set; never reused
    name: str
    slug: str
    builder_type: str  # e.g. "native-page", "html", "vercel-embed"
    intent: str  # what this page is for, in the owner's words
    location: "PageLocation"
    state: str = STATE_PLANNED
    role: Optional[str] = None  # MAY repeat across pages; never the identity
    revision: str = "0"  # content revision tag
    approvals: list[Approval] = field(default_factory=list)
    identities: NativeIdentities = field(default_factory=NativeIdentities)
    approved_content: dict = field(default_factory=dict)  # approved payload/ref
    native_components: list[str] = field(default_factory=list)  # e.g. order form
    product_price_refs: list[str] = field(default_factory=list)
    desired_state: str = DESIRED_DRAFT  # draft vs published, distinct from state
    bound: BoundRefs = field(default_factory=BoundRefs)


@dataclass
class PageLocation:
    """Placement of a page in the three DISTINCT structures.

    Administrative folders are not navigation and not nested URL paths.
    """

    admin_folder_logical_id: Optional[str] = None  # admin namespace
    url_path: str = "/"  # nested URL path namespace, unique per set


# ---------------------------------------------------------------------------
# Funnel ordering + action edges
# ---------------------------------------------------------------------------


@dataclass
class Edge:
    """Explicit funnel action edge: accept/decline/submit/success/error."""

    from_logical_id: str
    to_logical_id: str
    kind: str  # one of EDGE_KINDS


# ---------------------------------------------------------------------------
# Website menus, shared sections, general navigation
# ---------------------------------------------------------------------------


@dataclass
class MenuItem:
    label: str
    page_logical_id: Optional[str] = None  # exactly one of page/external_url
    external_url: Optional[str] = None


@dataclass
class Menu:
    logical_id: str
    name: str
    items: list[MenuItem] = field(default_factory=list)


@dataclass
class SharedSection:
    logical_id: str
    name: str
    page_logical_ids: list[str] = field(default_factory=list)  # pages using it


@dataclass
class NavEdge:
    """General website navigation. Cycles are legitimate here."""

    from_logical_id: str  # page logical_id
    to_logical_id: str  # page logical_id


# ---------------------------------------------------------------------------
# Administrative folders (own ID space, own tree)
# ---------------------------------------------------------------------------


@dataclass
class AdminFolder:
    logical_id: str
    name: str
    parent_logical_id: Optional[str] = None


# ---------------------------------------------------------------------------
# The page set document
# ---------------------------------------------------------------------------


@dataclass
class PageSet:
    """One delivered page set: a funnel OR a website, N pages."""

    set_id: str  # stable slug, e.g. "elevation-2026-11"
    kind: str  # SET_KINDS
    schema_version: str = SCHEMA_VERSION
    pages: list[PageNode] = field(default_factory=list)
    ordering: list[str] = field(default_factory=list)  # funnel: page logical_ids
    edges: list[Edge] = field(default_factory=list)  # funnel: action edges
    menus: list[Menu] = field(default_factory=list)  # website
    shared_sections: list[SharedSection] = field(default_factory=list)  # website
    nav: list[NavEdge] = field(default_factory=list)  # website, cycles fine
    admin_folders: list[AdminFolder] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Delivery results: native IDs, embeds, links, per-operation results
# ---------------------------------------------------------------------------


@dataclass
class OperationResult:
    """Result of ONE attempted operation. Uncertain stays uncertain."""

    operation: str
    status: str  # RESULT_STATUSES
    detail: str = ""
    native_id: Optional[str] = None
    readback: dict = field(default_factory=dict)


@dataclass
class DeliveryResult:
    """What the delivery actually produced, keyed by page logical_id."""

    set_id: str
    page_results: dict[str, list[OperationResult]] = field(default_factory=dict)
    native_ids: dict[str, dict] = field(default_factory=dict)
    embeds: dict[str, list[str]] = field(default_factory=dict)
    links: dict[str, list[str]] = field(default_factory=dict)
    restrictions: list[str] = field(default_factory=list)  # real platform limits


# ---------------------------------------------------------------------------
# Serialization (persistence/checkpoint friendly, stdlib only)
# ---------------------------------------------------------------------------


def page_set_to_dict(doc: PageSet) -> dict:
    return asdict(doc)


def page_set_from_dict(data: dict) -> PageSet:
    """Parse a dict into a PageSet. Raises ContractError on malformed shapes."""
    if not isinstance(data, dict):
        raise ContractError("document must be a dict")

    def _list(key: str) -> list:
        v = data.get(key, [])
        if not isinstance(v, list):
            raise ContractError(f"{key} must be a list")
        return v

    def _req_str(obj: dict, key: str, where: str) -> str:
        v = obj.get(key)
        if not isinstance(v, str) or not v:
            raise ContractError(f"{where}.{key} must be a non-empty string")
        return v

    def _opt_str(obj: dict, key: str) -> Optional[str]:
        v = obj.get(key)
        if v is not None and not isinstance(v, str):
            raise ContractError(f"{key} must be a string or null")
        return v

    pages: list[PageNode] = []
    for i, raw in enumerate(_list("pages")):
        where = f"pages[{i}]"
        if not isinstance(raw, dict):
            raise ContractError(f"{where} must be a dict")
        loc_raw = raw.get("location") or {}
        if not isinstance(loc_raw, dict):
            raise ContractError(f"{where}.location must be a dict")
        idn_raw = raw.get("identities") or {}
        bnd_raw = raw.get("bound") or {}
        approvals = []
        for j, a in enumerate(_list_of(raw, "approvals", where)):
            if not isinstance(a, dict):
                raise ContractError(f"{where}.approvals[{j}] must be a dict")
            approvals.append(
                Approval(
                    approver=_req_str(a, "approver", f"{where}.approvals[{j}]"),
                    content_revision=_req_str(
                        a, "content_revision", f"{where}.approvals[{j}]"
                    ),
                    approved_at=_req_str(a, "approved_at", f"{where}.approvals[{j}]"),
                )
            )
        pages.append(
            PageNode(
                logical_id=_req_str(raw, "logical_id", where),
                name=_req_str(raw, "name", where),
                slug=_req_str(raw, "slug", where),
                builder_type=_req_str(raw, "builder_type", where),
                intent=_req_str(raw, "intent", where),
                location=PageLocation(
                    admin_folder_logical_id=_opt_str(loc_raw, "admin_folder_logical_id"),
                    url_path=loc_raw.get("url_path", "/"),
                ),
                state=raw.get("state", STATE_PLANNED),
                role=_opt_str(raw, "role"),
                revision=str(raw.get("revision", "0")),
                approvals=approvals,
                identities=NativeIdentities(
                    folder_id=_opt_str(idn_raw, "folder_id"),
                    container_id=_opt_str(idn_raw, "container_id"),
                    page_id=_opt_str(idn_raw, "page_id"),
                ),
                approved_content=raw.get("approved_content") or {},
                native_components=list(raw.get("native_components") or []),
                product_price_refs=list(raw.get("product_price_refs") or []),
                desired_state=raw.get("desired_state", DESIRED_DRAFT),
                bound=BoundRefs(
                    urls=list(bnd_raw.get("urls") or []),
                    actions=list(bnd_raw.get("actions") or []),
                ),
            )
        )

    edges = []
    for i, raw in enumerate(_list("edges")):
        if not isinstance(raw, dict):
            raise ContractError(f"edges[{i}] must be a dict")
        edges.append(
            Edge(
                from_logical_id=_req_str(raw, "from_logical_id", f"edges[{i}]"),
                to_logical_id=_req_str(raw, "to_logical_id", f"edges[{i}]"),
                kind=_req_str(raw, "kind", f"edges[{i}]"),
            )
        )

    menus = []
    for i, raw in enumerate(_list("menus")):
        if not isinstance(raw, dict):
            raise ContractError(f"menus[{i}] must be a dict")
        items = []
        for j, it in enumerate(raw.get("items") or []):
            if not isinstance(it, dict):
                raise ContractError(f"menus[{i}].items[{j}] must be a dict")
            items.append(
                MenuItem(
                    label=_req_str(it, "label", f"menus[{i}].items[{j}]"),
                    page_logical_id=_opt_str(it, "page_logical_id"),
                    external_url=_opt_str(it, "external_url"),
                )
            )
        menus.append(
            Menu(
                logical_id=_req_str(raw, "logical_id", f"menus[{i}]"),
                name=_req_str(raw, "name", f"menus[{i}]"),
                items=items,
            )
        )

    sections = []
    for i, raw in enumerate(_list("shared_sections")):
        if not isinstance(raw, dict):
            raise ContractError(f"shared_sections[{i}] must be a dict")
        sections.append(
            SharedSection(
                logical_id=_req_str(raw, "logical_id", f"shared_sections[{i}]"),
                name=_req_str(raw, "name", f"shared_sections[{i}]"),
                page_logical_ids=list(raw.get("page_logical_ids") or []),
            )
        )

    nav = []
    for i, raw in enumerate(_list("nav")):
        if not isinstance(raw, dict):
            raise ContractError(f"nav[{i}] must be a dict")
        nav.append(
            NavEdge(
                from_logical_id=_req_str(raw, "from_logical_id", f"nav[{i}]"),
                to_logical_id=_req_str(raw, "to_logical_id", f"nav[{i}]"),
            )
        )

    folders = []
    for i, raw in enumerate(_list("admin_folders")):
        if not isinstance(raw, dict):
            raise ContractError(f"admin_folders[{i}] must be a dict")
        folders.append(
            AdminFolder(
                logical_id=_req_str(raw, "logical_id", f"admin_folders[{i}]"),
                name=_req_str(raw, "name", f"admin_folders[{i}]"),
                parent_logical_id=_opt_str(raw, "parent_logical_id"),
            )
        )

    return PageSet(
        set_id=_req_str(data, "set_id", "document"),
        kind=_req_str(data, "kind", "document"),
        schema_version=data.get("schema_version", SCHEMA_VERSION),
        pages=pages,
        ordering=list(data.get("ordering") or []),
        edges=edges,
        menus=menus,
        shared_sections=sections,
        nav=nav,
        admin_folders=folders,
    )


def _list_of(obj: dict, key: str, where: str) -> list:
    v = obj.get(key, [])
    if not isinstance(v, list):
        raise ContractError(f"{where}.{key} must be a list")
    return v


# ---------------------------------------------------------------------------
# Compatibility contract
# ---------------------------------------------------------------------------


def parse_version(version: str) -> tuple[int, int, int]:
    m = _VERSION_RE.match(version or "")
    if not m:
        raise ContractError(f"schema_version must be MAJOR.MINOR.PATCH: {version!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def check_compatibility(
    doc_version: str, reader_version: str = SCHEMA_VERSION
) -> tuple[str, str]:
    """Apply the compatibility contract. Returns (status, detail).

    Different MAJOR -> "incompatible". Same MAJOR, newer MINOR on the
    document -> "ok-unknown-fields" (additive fields ignored, never an error).
    Everything else -> "ok".
    """
    try:
        dmaj, dmin, _ = parse_version(doc_version)
        rmaj, rmin, _ = parse_version(reader_version)
    except ContractError as exc:
        return (COMPAT_INCOMPATIBLE, str(exc))
    if dmaj != rmaj:
        return (
            COMPAT_INCOMPATIBLE,
            f"major mismatch: document {doc_version} vs reader {reader_version}",
        )
    if dmin > rmin:
        return (
            COMPAT_UNKNOWN_FIELDS,
            f"document {doc_version} newer than reader {reader_version}; "
            "unknown additive fields ignored",
        )
    return (COMPAT_OK, f"document {doc_version} readable by {reader_version}")


# ---------------------------------------------------------------------------
# State machine + work-order (phase) enforcement
# ---------------------------------------------------------------------------


def advance_state(page: PageNode, new_state: str) -> None:
    """Move a page forward one or more states. Backward moves raise."""
    if new_state not in _RANK_STATE:
        raise ContractError(f"unknown state: {new_state!r}")
    if _RANK_STATE[new_state] <= _RANK_STATE[page.state]:
        raise ContractError(
            f"state transitions move forward only: {page.state} -> {new_state}"
        )
    page.state = new_state


def check_phase_order(doc: PageSet) -> list[str]:
    """Enforce: identities FIRST, then content, then bind URLs/actions."""
    errors: list[str] = []
    for p in doc.pages:
        st = _RANK_STATE.get(p.state, -1)
        if st < 0:
            errors.append(f"{p.logical_id}: unknown state {p.state!r}")
            continue
        if st >= _RANK_STATE[STATE_CREATED] and p.identities.page_id is None:
            errors.append(
                f"{p.logical_id}: state {p.state} requires an allocated native "
                "page id (allocate identities FIRST)"
            )
        if st >= _RANK_STATE[STATE_CONFIGURED] and not p.approved_content:
            errors.append(
                f"{p.logical_id}: state {p.state} requires approved content "
                "(content AFTER identities)"
            )
        if st >= _RANK_STATE[STATE_PUBLISHED] and not (p.bound.urls or p.bound.actions):
            errors.append(
                f"{p.logical_id}: state {p.state} requires bound URLs/actions "
                "(bind LAST)"
            )
        if st >= _RANK_STATE[STATE_PUBLISHED] and p.desired_state != DESIRED_PUBLISHED:
            errors.append(
                f"{p.logical_id}: state {p.state} contradicts desired_state "
                f"{p.desired_state!r} (saving is not publishing)"
            )
    return errors


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_page_set(doc: PageSet) -> list[str]:
    """Full contract validation. Returns [] when the document is valid."""
    errors: list[str] = []

    status, detail = check_compatibility(doc.schema_version)
    if status == COMPAT_INCOMPATIBLE:
        errors.append(f"schema_version: {detail}")

    if not _SLUG_RE.match(doc.set_id or ""):
        errors.append(f"set_id {doc.set_id!r} must match {_SLUG_RE.pattern}")
    if doc.kind not in SET_KINDS:
        errors.append(f"kind {doc.kind!r} must be one of {SET_KINDS}")

    # --- pages: unique stable logical IDs, N unconstrained -----------------
    if not doc.pages:
        errors.append("pages: at least one page node required")
    seen_ids: dict[str, str] = {}
    seen_paths: dict[str, str] = {}
    for p in doc.pages:
        if not _SLUG_RE.match(p.logical_id or ""):
            errors.append(f"logical_id {p.logical_id!r} must match {_SLUG_RE.pattern}")
        if p.logical_id in seen_ids:
            errors.append(f"duplicate logical_id {p.logical_id!r} (identity is the "
                          "logical ID, never the role)")
        seen_ids[p.logical_id] = p.logical_id
        if not _SLUG_RE.match(p.slug or ""):
            errors.append(f"{p.logical_id}: slug {p.slug!r} must match {_SLUG_RE.pattern}")
        if p.state not in _RANK_STATE:
            errors.append(f"{p.logical_id}: unknown state {p.state!r}")
        if p.desired_state not in DESIRED_STATES:
            errors.append(f"{p.logical_id}: desired_state {p.desired_state!r} must be "
                          f"one of {DESIRED_STATES}")
        if not p.location.url_path.startswith("/"):
            errors.append(f"{p.logical_id}: url_path must start with '/'")
        if p.location.url_path in seen_paths:
            errors.append(
                f"{p.logical_id}: url_path {p.location.url_path!r} already used by "
                f"{seen_paths[p.location.url_path]} (nested URL paths are unique)"
            )
        seen_paths[p.location.url_path] = p.logical_id
        # role MAY repeat across pages on purpose — deliberately no check here.

    # --- administrative folders: own ID space, acyclic tree ----------------
    folder_ids: set[str] = set()
    for f in doc.admin_folders:
        if f.logical_id in folder_ids:
            errors.append(f"duplicate admin folder logical_id {f.logical_id!r}")
        folder_ids.add(f.logical_id)
        if f.logical_id in seen_ids:
            errors.append(
                f"admin folder {f.logical_id!r} collides with a page logical_id "
                "(administrative folders are a separate ID space)"
            )
    for f in doc.admin_folders:
        if f.parent_logical_id is not None and f.parent_logical_id not in folder_ids:
            errors.append(
                f"admin folder {f.logical_id}: unknown parent {f.parent_logical_id!r}"
            )
    # folder-tree cycles are structural errors (unlike website nav cycles)
    for f in doc.admin_folders:
        seen_chain: set[str] = set()
        cur: Optional[AdminFolder] = f
        while cur is not None:
            if cur.logical_id in seen_chain:
                errors.append(f"admin folder cycle at {cur.logical_id!r}")
                break
            seen_chain.add(cur.logical_id)
            parent = cur.parent_logical_id
            cur = next((x for x in doc.admin_folders if x.logical_id == parent), None)

    page_ids = set(seen_ids)
    folder_only = folder_ids - page_ids

    # --- per-page admin folder references ---------------------------------
    for p in doc.pages:
        ref = p.location.admin_folder_logical_id
        if ref is not None and ref not in folder_ids:
            errors.append(f"{p.logical_id}: unknown admin folder {ref!r}")

    # --- funnels: ordering + explicit action edges -------------------------
    if doc.kind == SET_KIND_FUNNEL:
        if not doc.ordering:
            errors.append("funnel requires an explicit ordering")
        else:
            if len(doc.ordering) != len(set(doc.ordering)):
                errors.append("ordering contains duplicate logical_ids")
            unknown = [x for x in doc.ordering if x not in page_ids]
            if unknown:
                errors.append(f"ordering references unknown pages: {unknown}")
            missing = [x for x in page_ids if x not in doc.ordering]
            if missing:
                errors.append(f"ordering omits pages (never drop pages): {missing}")
        for e in doc.edges:
            if e.kind not in EDGE_KINDS:
                errors.append(
                    f"edge {e.from_logical_id}->{e.to_logical_id}: kind {e.kind!r} "
                    f"must be one of {EDGE_KINDS} (explicit kinds only)"
                )
            for end in (e.from_logical_id, e.to_logical_id):
                if end not in page_ids:
                    errors.append(
                        f"edge {e.from_logical_id}->{e.to_logical_id}: "
                        f"unknown page {end!r}"
                    )
        if doc.menus or doc.shared_sections or doc.nav:
            errors.append(
                "funnel document must not carry website menus/shared_sections/nav"
            )

    # --- websites: menus, shared sections, general nav (cycles fine) -------
    if doc.kind == SET_KIND_WEBSITE:
        if doc.ordering:
            errors.append("website document must not carry funnel ordering")
        if doc.edges:
            errors.append("website document must not carry funnel action edges")
        menu_ids: set[str] = set()
        for m in doc.menus:
            if m.logical_id in menu_ids:
                errors.append(f"duplicate menu logical_id {m.logical_id!r}")
            menu_ids.add(m.logical_id)
            for it in m.items:
                has_page = it.page_logical_id is not None
                has_ext = it.external_url is not None
                if has_page == has_ext:
                    errors.append(
                        f"menu {m.logical_id} item {it.label!r}: exactly one of "
                        "page_logical_id / external_url"
                    )
                if has_page and it.page_logical_id not in page_ids:
                    errors.append(
                        f"menu {m.logical_id} item {it.label!r}: unknown page "
                        f"{it.page_logical_id!r}"
                    )
                if has_page and it.page_logical_id in folder_only:
                    errors.append(
                        f"menu {m.logical_id} item {it.label!r}: target is an "
                        "admin folder — folders are not navigation"
                    )
        for s in doc.shared_sections:
            for ref in s.page_logical_ids:
                if ref not in page_ids:
                    errors.append(
                        f"shared_section {s.logical_id}: unknown page {ref!r}"
                    )
        for n in doc.nav:
            for end in (n.from_logical_id, n.to_logical_id):
                if end not in page_ids:
                    errors.append(
                        f"nav {n.from_logical_id}->{n.to_logical_id}: "
                        f"unknown page {end!r}"
                    )
                if end in folder_only:
                    errors.append(
                        f"nav {n.from_logical_id}->{n.to_logical_id}: target is an "
                        "admin folder — folders are not navigation"
                    )
        # nav cycles are legitimate; deliberately no cycle check here.

    # --- work order: identities first, content, then URL/action binding ----
    errors.extend(check_phase_order(doc))

    return errors


# ---------------------------------------------------------------------------
# Results: never silently drop pages
# ---------------------------------------------------------------------------


def check_no_dropped_pages(doc: PageSet, result: DeliveryResult) -> list[str]:
    """A page must appear as a result row — failed/uncertain, never absent.

    Real platform restrictions go in result.restrictions; they never excuse a
    missing page row.
    """
    errors: list[str] = []
    expected = {p.logical_id for p in doc.pages}
    got = set(result.page_results)
    for missing in sorted(expected - got):
        errors.append(
            f"{missing}: no result row (pages are never silently dropped; "
            "report the real platform restriction instead)"
        )
    for extra in sorted(got - expected):
        errors.append(f"{extra}: result row for a page not in the set")
    for lid, rows in result.page_results.items():
        if lid in expected and not rows:
            errors.append(f"{lid}: empty result row (no operation results recorded)")
        for r in rows:
            if r.status not in RESULT_STATUSES:
                errors.append(f"{lid}: unknown result status {r.status!r}")
    return errors


# ---------------------------------------------------------------------------
# Self-check (assert based) + CLI
# ---------------------------------------------------------------------------


def _mk_page(lid: str, **kw) -> PageNode:
    kw.setdefault("name", lid.replace("-", " ").title())
    kw.setdefault("slug", lid)
    kw.setdefault("builder_type", "native-page")
    kw.setdefault("intent", f"intent for {lid}")
    kw.setdefault("location", PageLocation(url_path=f"/{lid}"))
    return PageNode(logical_id=lid, **kw)


def _self_test() -> list:
    failures: list = []

    def check(label: str, cond: bool) -> None:
        if not cond:
            failures.append(f"self-test: {label}")

    # 1. Funnel of 4 pages (an example, not a cap) validates clean.
    funnel = PageSet(
        set_id="elevation-2026-11",
        kind=SET_KIND_FUNNEL,
        pages=[
            _mk_page("optin", role="lead-capture"),
            _mk_page("sales", role="sales"),
            _mk_page("checkout", role="checkout"),
            _mk_page("thanks", role="confirmation"),
        ],
        ordering=["optin", "sales", "checkout", "thanks"],
        edges=[
            Edge("optin", "sales", EDGE_SUBMIT),
            Edge("checkout", "thanks", EDGE_SUCCESS),
            Edge("checkout", "sales", EDGE_DECLINE),
        ],
    )
    check("4-page funnel valid", validate_page_set(funnel) == [])

    # 2. N is unconstrained: 20 pages and 2 pages both validate.
    big = PageSet(
        set_id="big-set",
        kind=SET_KIND_FUNNEL,
        pages=[_mk_page(f"p{i:02d}") for i in range(20)],
        ordering=[f"p{i:02d}" for i in range(20)],
    )
    check("20-page set valid (no cap)", validate_page_set(big) == [])
    small = PageSet(
        set_id="tiny-set",
        kind=SET_KIND_FUNNEL,
        pages=[_mk_page("a"), _mk_page("b")],
        ordering=["a", "b"],
    )
    check("2-page set valid (no floor on presets)", validate_page_set(small) == [])

    # 3. Pages may share a role with distinct identity.
    shared_role = PageSet(
        set_id="role-share",
        kind=SET_KIND_FUNNEL,
        pages=[
            _mk_page("upsell-1", role="upsell"),
            _mk_page("upsell-2", role="upsell"),
        ],
        ordering=["upsell-1", "upsell-2"],
    )
    check("shared role with distinct IDs valid", validate_page_set(shared_role) == [])

    # 4. Duplicate logical_id is rejected.
    dup = PageSet(
        set_id="dup-set",
        kind=SET_KIND_FUNNEL,
        pages=[_mk_page("same"), _mk_page("same")],
        ordering=["same"],
    )
    check("duplicate logical_id rejected", bool(validate_page_set(dup)))

    # 5. Ordering must cover every page (never drop pages) and nothing else.
    bad_order = PageSet(
        set_id="bad-order",
        kind=SET_KIND_FUNNEL,
        pages=[_mk_page("x"), _mk_page("y")],
        ordering=["x"],
    )
    check("incomplete ordering rejected", bool(validate_page_set(bad_order)))

    # 6. Edge endpoints and kinds are explicit and checked.
    bad_edge = PageSet(
        set_id="bad-edge",
        kind=SET_KIND_FUNNEL,
        pages=[_mk_page("x"), _mk_page("y")],
        ordering=["x", "y"],
        edges=[Edge("x", "ghost", "mystery")],
    )
    errs = validate_page_set(bad_edge)
    check("unknown edge endpoint rejected",
          any("unknown page 'ghost'" in e for e in errs))
    check("unknown edge kind rejected",
          any("'mystery'" in e for e in errs))

    # 7. Website with a navigation CYCLE validates (cycles legitimate).
    site = PageSet(
        set_id="cyclic-site",
        kind=SET_KIND_WEBSITE,
        pages=[_mk_page("home"), _mk_page("about"), _mk_page("blog")],
        nav=[
            NavEdge("home", "about"),
            NavEdge("about", "blog"),
            NavEdge("blog", "home"),  # cycle: legitimate
        ],
        menus=[
            Menu("main", "Main", [MenuItem("Home", page_logical_id="home"),
                                  MenuItem("Docs", external_url="https://ex.ample/d")])
        ],
        shared_sections=[SharedSection("hero", "Hero", ["home", "about"])],
        admin_folders=[AdminFolder("f-marketing", "Marketing")],
    )
    check("cyclic website nav valid", validate_page_set(site) == [])

    # 8. Structural mixing is rejected both ways.
    funnel_with_nav = PageSet(
        set_id="mixed-1",
        kind=SET_KIND_FUNNEL,
        pages=[_mk_page("x")],
        ordering=["x"],
        nav=[NavEdge("x", "x")],
    )
    check("funnel+nav mix rejected", bool(validate_page_set(funnel_with_nav)))
    site_with_ordering = PageSet(
        set_id="mixed-2",
        kind=SET_KIND_WEBSITE,
        pages=[_mk_page("x")],
        ordering=["x"],
    )
    check("website+ordering mix rejected", bool(validate_page_set(site_with_ordering)))

    # 9. Admin folders are NOT navigation and live in their own ID space.
    folder_nav = PageSet(
        set_id="folder-nav",
        kind=SET_KIND_WEBSITE,
        pages=[_mk_page("home")],
        nav=[NavEdge("home", "f-marketing")],
        admin_folders=[AdminFolder("f-marketing", "Marketing")],
    )
    errs = validate_page_set(folder_nav)
    check("nav->admin-folder rejected",
          any("folders are not navigation" in e for e in errs))
    folder_collision = PageSet(
        set_id="folder-collision",
        kind=SET_KIND_WEBSITE,
        pages=[_mk_page("home")],
        admin_folders=[AdminFolder("home", "Home")],
    )
    check("admin folder colliding with page ID rejected",
          bool(validate_page_set(folder_collision)))

    # 10. Nested URL paths are unique per set.
    path_clash = PageSet(
        set_id="path-clash",
        kind=SET_KIND_WEBSITE,
        pages=[_mk_page("a", location=PageLocation(url_path="/same")),
               _mk_page("b", location=PageLocation(url_path="/same"))],
    )
    check("url_path collision rejected", bool(validate_page_set(path_clash)))

    # 11. State transitions are forward only and states stay distinct.
    p = _mk_page("s1")
    advance_state(p, STATE_CREATED)
    check("forward transition allowed", p.state == STATE_CREATED)
    try:
        advance_state(p, STATE_PLANNED)
        check("backward transition rejected", False)
    except ContractError:
        check("backward transition rejected", True)

    # 12. Work order: identities first, then content, then bind URLs/actions.
    disorder = PageSet(
        set_id="disorder",
        kind=SET_KIND_WEBSITE,
        pages=[
            _mk_page("configured-no-id", state=STATE_CONFIGURED,
                     approved_content={"html": "<p>x</p>"}),
            _mk_page("published-no-bind", state=STATE_PUBLISHED,
                     identities=NativeIdentities(page_id="ghl-123"),
                     approved_content={"html": "<p>y</p>"},
                     desired_state=DESIRED_PUBLISHED),
        ],
    )
    errs = validate_page_set(disorder)
    check("content before identities rejected",
          any("allocate identities FIRST" in e for e in errs))
    check("publish before binding rejected",
          any("bind LAST" in e for e in errs))

    well_done = PageSet(
        set_id="well-done",
        kind=SET_KIND_WEBSITE,
        pages=[
            _mk_page("done", state=STATE_PUBLISHED,
                     identities=NativeIdentities(page_id="ghl-9"),
                     approved_content={"html": "<p>z</p>"},
                     desired_state=DESIRED_PUBLISHED,
                     bound=BoundRefs(urls=["https://ex.ample/done"])),
        ],
    )
    check("ordered lifecycle validates", validate_page_set(well_done) == [])

    # 13. Compatibility contract: major gates, newer minor tolerated.
    check("same version ok",
          check_compatibility("1.0.0")[0] == COMPAT_OK)
    check("older minor ok",
          check_compatibility("1.0.0", "1.2.0")[0] == COMPAT_OK)
    check("newer minor -> ok-unknown-fields",
          check_compatibility("1.7.0", "1.0.0")[0] == COMPAT_UNKNOWN_FIELDS)
    check("different major -> incompatible",
          check_compatibility("2.0.0")[0] == COMPAT_INCOMPATIBLE)
    check("malformed version -> incompatible",
          check_compatibility("1.0")[0] == COMPAT_INCOMPATIBLE)
    check("validate_page_set rejects wrong major",
          bool(validate_page_set(PageSet(
              set_id="v2-doc", kind=SET_KIND_WEBSITE,
              schema_version="2.0.0", pages=[_mk_page("x")]))))
    check("validate_page_set accepts newer minor",
          validate_page_set(PageSet(
              set_id="v17-doc", kind=SET_KIND_WEBSITE,
              schema_version="1.7.0", pages=[_mk_page("x")])) == [])

    # 14. Round-trip serialization preserves the document.
    rt = page_set_from_dict(page_set_to_dict(funnel))
    check("round-trip keeps set_id", rt.set_id == funnel.set_id)
    check("round-trip keeps page count (no drops)",
          len(rt.pages) == len(funnel.pages))
    check("round-trip keeps ordering", rt.ordering == funnel.ordering)

    # 15. Results: missing page rows are caught, restrictions never excuse them.
    ok_result = DeliveryResult(
        set_id="tiny-set",
        page_results={
            "a": [OperationResult("create-page", RESULT_OK, native_id="ghl-1")],
            "b": [OperationResult("create-page", RESULT_FAILED,
                                  detail="plan limit reached")],
        },
        restrictions=["account plan allows 2 pages per funnel"],
    )
    check("ok+failed rows cover the set",
          check_no_dropped_pages(small, ok_result) == [])
    dropped = DeliveryResult(set_id="tiny-set", page_results={"a": []})
    errs = check_no_dropped_pages(small, dropped)
    check("dropped page caught",
          any("never silently dropped" in e for e in errs))
    check("empty result row caught", any("empty result row" in e for e in errs))

    return failures


def main(argv: list) -> int:
    if len(argv) == 2 and argv[1] == "--self-test":
        failures = _self_test()
        if failures:
            for f in failures:
                print(f)
            return 1
        print("SELF-TEST OK: npage_contract.py all contract checks passed")
        return 0
    if len(argv) == 2 and not argv[1].startswith("-"):
        path = Path(argv[1])
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            doc = page_set_from_dict(data)
        except (OSError, json.JSONDecodeError, ContractError) as exc:
            print(f"error: {path}: {exc}")
            return 2
        errors = validate_page_set(doc)
        if errors:
            for e in errors:
                print(e)
            return 1
        print(f"VALID: {path} ({len(doc.pages)} pages, kind={doc.kind})")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
