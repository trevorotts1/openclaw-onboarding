#!/usr/bin/env python3
"""WF24-CP01 - reconciled public funnel read route contract.

WHAT THIS IS
------------
The frozen interface for the three documented funnel READ operations, shared by
every surface that must agree on them: the shared capability inventory
(``capability_inventory.py``), the shared object router (``object_router.py``),
the Skill 6 public-client bridge (``06-ghl-install-pages/tools/ghl_public_client.py``)
and the existing read implementation (``06-ghl-install-pages/tools/ghl_funnels_read.py``).

This module owns NO transport, NO credential handling, NO retry policy and NO
authorization decision. It is a data contract plus a query builder. The central
operation registry (``public/operations.py``) is owned by WF00; WF24 publishes
this interface so WF00 can correct its stale funnel rows to exactly these
shapes and so every consumer can build against one declaration.

RECONCILED SHAPES (Document 1 section 21.3)
-------------------------------------------
    list funnels     GET /funnels/funnel/list   locationId, offset, limit (query)
    list pages       GET /funnels/page          locationId, funnelId, limit, offset (query)
    count pages      GET /funnels/page/count    locationId, funnelId (query)

The older frozen-registry shapes (``GET /funnels/``,
``GET /funnels/{funnelId}/pages``, ``GET /funnels/{funnelId}/pages/count``) are
recorded in ``OBSOLETE_FROZEN_SHAPES`` as audit anchors only. They are never
emitted by a caller.

HONEST UNRESOLVED FIELDS
------------------------
The literal ``Version`` header value, the required Private Integration Token
scope name, the pages/count response-envelope keys and the page item/status
vocabulary are NOT settled by the documentation capture. They stay explicit as
``unresolved`` (and ``version_state`` / ``scope_state``) instead of being
guessed. ``2023-02-21`` is the documentation version label the capture records
for GET /funnels/page; it is labeled UNVERIFIED, never asserted as a live
header contract.

READS ONLY
----------
These are reads. No funnel/page create, edit, publish or delete route is
inferred from them. Skill 6 keeps the managed construction rails.

Runnable check:
    python3 -I shared-utils/ghl/funnel_read_contract.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

CONTRACT_ID = "WF24-CP01"
CONTRACT_REVISION = "wf24-cp01.v1"
OWNER_WORKFLOW = "WF24"
CENTRAL_REGISTRY_OWNER = "WF00"


@dataclass(frozen=True)
class QueryParam:
    """One query parameter: exact name, placement and presence rule."""

    name: str
    required: bool
    value_kind: str = "string"
    placement: str = "query"
    note: str = ""

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "name": self.name,
            "required": self.required,
            "value_kind": self.value_kind,
            "placement": self.placement,
        }
        if self.note:
            out["note"] = self.note
        return out


@dataclass(frozen=True)
class FunnelReadContract:
    """One reconciled funnel read operation."""

    operation_id: str
    capability_id: str
    method: str
    path: str
    query: Tuple[QueryParam, ...]
    version_header: Optional[str]
    version_state: str
    scope_state: str
    response_shape: str
    pagination: str
    total_field: Optional[str]
    unresolved: Tuple[str, ...] = ()
    docs: str = ""

    def required_query(self) -> Tuple[str, ...]:
        return tuple(p.name for p in self.query if p.required)

    def optional_query(self) -> Tuple[str, ...]:
        return tuple(p.name for p in self.query if not p.required)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "capability_id": self.capability_id,
            "method": self.method,
            "path": self.path,
            "query": [p.as_dict() for p in self.query],
            "required_query": list(self.required_query()),
            "optional_query": list(self.optional_query()),
            "version_header": self.version_header,
            "version_state": self.version_state,
            "scope_state": self.scope_state,
            "response_shape": self.response_shape,
            "pagination": self.pagination,
            "total_field": self.total_field,
            "unresolved": list(self.unresolved),
            "docs": self.docs,
        }


PAGINATION_OFFSET_TOTAL = "offset_limit_with_reported_total"
PAGINATION_OFFSET_SHORT_PAGE = "offset_limit_short_page_end"
PAGINATION_NONE = "none"

DOCS_LIST = "https://marketplace.gohighlevel.com/docs/ghl/funnels/get-funnels/"
DOCS_PAGES = "https://marketplace.gohighlevel.com/docs/ghl/funnels/get-pages-by-funnel-id/index.html"
DOCS_COUNT = "https://marketplace.gohighlevel.com/docs/ghl/funnels/get-pages-count-by-funnel-id/index.html"

_CONTRACTS: Tuple[FunnelReadContract, ...] = (
    FunnelReadContract(
        operation_id="funnels.list",
        capability_id="funnels.list",
        method="GET",
        path="/funnels/funnel/list",
        query=(
            QueryParam("locationId", True),
            QueryParam("offset", True, value_kind="int"),
            QueryParam("limit", True, value_kind="int"),
            QueryParam("type", False, note="optional filter"),
            QueryParam("category", False, note="optional filter"),
            QueryParam("parentId", False, note="optional filter"),
            QueryParam("name", False, note="optional filter"),
        ),
        version_header="2023-02-21",
        version_state="unverified",
        scope_state="unverified",
        response_shape=(
            "object {funnels: [funnel], count: integer, traceId: string}; "
            "count is the reported total"
        ),
        pagination=PAGINATION_OFFSET_TOTAL,
        total_field="count",
        unresolved=(
            "literal Version header value (2023-02-21 is a documentation label, unverified)",
            "required Private Integration Token scope name",
            "funnel item field schema",
        ),
        docs=DOCS_LIST,
    ),
    FunnelReadContract(
        operation_id="funnels.pages.list",
        capability_id="funnels.pages_list",
        method="GET",
        path="/funnels/page",
        query=(
            QueryParam("locationId", True),
            QueryParam("funnelId", True),
            QueryParam("limit", True, value_kind="int"),
            QueryParam("offset", True, value_kind="int"),
            QueryParam("name", False, note="optional filter"),
        ),
        version_header="2023-02-21",
        version_state="unverified",
        scope_state="unverified",
        response_shape=(
            "object carrying a page list under one of ('pages', 'funnelPages', "
            "'data', 'steps') or a bare JSON list; envelope key unverified"
        ),
        pagination=PAGINATION_OFFSET_SHORT_PAGE,
        total_field=None,
        unresolved=(
            "literal Version header value (2023-02-21 is a documentation label, unverified)",
            "required Private Integration Token scope name",
            "pages response-envelope key",
            "page item field schema",
            "page status vocabulary",
        ),
        docs=DOCS_PAGES,
    ),
    FunnelReadContract(
        operation_id="funnels.pages.count",
        capability_id="funnels.pages_count",
        method="GET",
        path="/funnels/page/count",
        query=(
            QueryParam("locationId", True),
            QueryParam("funnelId", True),
        ),
        version_header="2023-02-21",
        version_state="unverified",
        scope_state="unverified",
        response_shape=(
            "object carrying the total under one of ('count', 'total', "
            "'totalCount') or a bare integer; key unverified"
        ),
        pagination=PAGINATION_NONE,
        total_field="count (candidate key, unverified)",
        unresolved=(
            "literal Version header value (2023-02-21 is a documentation label, unverified)",
            "required Private Integration Token scope name",
            "count response-envelope key",
        ),
        docs=DOCS_COUNT,
    ),
)

_BY_OPERATION: Dict[str, FunnelReadContract] = {
    c.operation_id: c for c in _CONTRACTS
}

#: Older frozen-registry shapes, kept only as audit anchors. Never emitted.
OBSOLETE_FROZEN_SHAPES: Dict[str, str] = {
    "funnels.list": "GET /funnels/",
    "funnels.pages.list": "GET /funnels/{funnelId}/pages",
    "funnels.pages.count": "GET /funnels/{funnelId}/pages/count",
}


def operations() -> Tuple[FunnelReadContract, ...]:
    """Every reconciled funnel read contract, in stable order."""
    return _CONTRACTS


def contract(operation_id: str) -> FunnelReadContract:
    """One contract by operation id (KeyError on an unknown id, never guessed)."""
    return _BY_OPERATION[str(operation_id)]


def page_count_contract() -> FunnelReadContract:
    return contract("funnels.pages.count")


def build_query(
    operation_id: str,
    *,
    strict: bool = True,
    **values: Any,
) -> Dict[str, Any]:
    """Validate placement and return the exact query mapping for one read.

    Order is the contract order (locationId/funnelId identify the target and
    come before pagination), which keeps request receipts deterministic.
    Unknown names, missing required names, wrong value kinds and non-query
    placements raise ``ValueError`` BEFORE any transport is constructed.
    """
    spec = contract(operation_id)
    declared = {p.name: p for p in spec.query}
    if strict:
        unknown = sorted(set(values) - set(declared))
        if unknown:
            raise ValueError(
                f"{operation_id}: unknown query parameter(s) {unknown}; "
                f"declared: {sorted(declared)}"
            )
    out: Dict[str, Any] = {}
    for param in spec.query:
        value = values.get(param.name)
        if value is None or (isinstance(value, str) and not value.strip()):
            if param.required:
                raise ValueError(
                    f"{operation_id}: required query parameter {param.name!r} "
                    "is missing or empty"
                )
            continue
        if param.placement != "query":
            raise ValueError(
                f"{operation_id}: {param.name!r} is not query-placed "
                f"(placement={param.placement!r}); refusing a mixed request shape"
            )
        if param.value_kind == "int":
            try:
                ivalue = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{operation_id}: query parameter {param.name!r} must be an "
                    f"integer (got {value!r})"
                ) from exc
            if isinstance(value, bool) or ivalue < 0:
                raise ValueError(
                    f"{operation_id}: query parameter {param.name!r} must be a "
                    f"non-negative integer (got {value!r})"
                )
            out[param.name] = ivalue
        else:
            out[param.name] = str(value)
    return out


def as_dict() -> Dict[str, Any]:
    """The full frozen interface, JSON-serializable (WF24-CP01 record body)."""
    return {
        "contract_id": CONTRACT_ID,
        "contract_revision": CONTRACT_REVISION,
        "owner_workflow": OWNER_WORKFLOW,
        "central_registry_owner": CENTRAL_REGISTRY_OWNER,
        "reads_only": True,
        "operations": [c.as_dict() for c in _CONTRACTS],
        "obsolete_frozen_shapes": dict(OBSOLETE_FROZEN_SHAPES),
    }


def self_check() -> None:
    # 1. The three reconciled paths, no obsolete shape, no invented write.
    paths = {c.operation_id: c.path for c in _CONTRACTS}
    assert paths == {
        "funnels.list": "/funnels/funnel/list",
        "funnels.pages.list": "/funnels/page",
        "funnels.pages.count": "/funnels/page/count",
    }, paths
    for op, old in OBSOLETE_FROZEN_SHAPES.items():
        assert contract(op).path != old.split(" ", 1)[1], (op, old)
        assert contract(op).method == "GET"
    assert all(c.method == "GET" for c in _CONTRACTS)

    # 2. Required query placement is exact and identifies the target first.
    assert contract("funnels.list").required_query() == ("locationId", "offset", "limit")
    assert contract("funnels.pages.list").required_query() == (
        "locationId", "funnelId", "limit", "offset",
    )
    assert contract("funnels.pages.count").required_query() == ("locationId", "funnelId")

    # 3. The builder refuses a mixed/old shape before transport.
    q = build_query(
        "funnels.pages.count", locationId="loc-1", funnelId="fun-1"
    )
    assert q == {"locationId": "loc-1", "funnelId": "fun-1"}, q
    try:
        build_query("funnels.pages.list", locationId="loc-1", offset=0, limit=10)
    except ValueError as exc:
        assert "funnelId" in str(exc)
    else:
        raise AssertionError("missing funnelId must raise")
    try:
        build_query("funnels.list", locationId="loc-1", offset=0, limit=10, funnelId="f")
    except ValueError as exc:
        assert "unknown query parameter" in str(exc)
    else:
        raise AssertionError("cross-endpoint parameter must raise")

    # 4. Version/scope stay explicit and unresolved, never globally upgraded.
    for c in _CONTRACTS:
        assert c.version_state == "unverified"
        assert c.scope_state == "unverified"
        assert any("Version" in u for u in c.unresolved)
        assert any("scope" in u for u in c.unresolved)


if __name__ == "__main__":
    self_check()
    print("funnel_read_contract self-check: PASS")
    print("  contract: %s (%s)" % (CONTRACT_ID, CONTRACT_REVISION))
    for c in _CONTRACTS:
        print("  %-22s %s %s" % (c.operation_id, c.method, c.path))
