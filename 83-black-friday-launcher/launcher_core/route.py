"""Route compilation and graph validation (doc 02 section 4).

Compilation is delegated to the real Skill 49 compiler
(`49-signature-funnel/scripts/compile_launch_route.py`) through
`routes.route_law`, so the package manifest, the launcher route model and the
route-invariant layer cannot drift into separate graph dialects. The intake is
mapped onto the compiler's approved-launch-record fields; `extras` are derived
from the offers the customer declared, never defaulted.

`validate_route` remains the launcher's own structural gate with its stable
autofail codes; `routes.route_law.graph_violations` is the stricter contract
layer that runs in assembly and fixtures.

`folded_levels` compiles landing -> checkout with N >= 2 main offers and no
product_selection node. Cross-sales are an offer relationship surfaced on the
thank-you page, never a route node. Council advice is a planning record carried
in the launch record, never a route node and never permission.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Set

from .constants import (
    CROSS_SALE_TEACHING_STATE,
    PENDING_FAILED_PAYMENT_BEHAVIOR,
    ROUTE_ROLES,
)

_ROUTES_DIR = Path(__file__).resolve().parent.parent / "routes"
if str(_ROUTES_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTES_DIR))

import route_law  # noqa: E402  (real compiler loader; needs its directory on sys.path)


class RouteError(Exception):
    """A route graph that cannot be walked. Carries a stable autofail code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def launch_record(intake: Dict[str, Any], council: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Map a validated intake onto the compiler's approved launch record.

    The record carries the entitlement decision and, when the planning step has
    run, the Council advice. Neither is a route node and neither changes the
    compiled graph.
    """
    roles = {offer["role"] for offer in intake["offers"]}
    record = {
        "tenant_id": intake["tenant_id"],
        "location_id": intake["location_id"],
        "launch_id": intake["launch_id"],
        "revision": intake["revision"],
        "journey_mode": intake["journey_mode"],
        "extras": {
            "upsell_1": "upsell_1" in roles,
            "downsell_1": "downsell_1" in roles,
            "upsell_2": "upsell_2" in roles,
        },
        "test_only": bool(intake.get("test_only", True)),
        "entitlement": {
            "basis": intake["entitlement"]["basis"],
            "requires_purchase": intake["entitlement"]["requires_purchase"],
            "billing": "none",
        },
        "cross_sales": {
            "relationships": [
                {"offer_id": offer["offer_id"], **offer["relationships"]}
                for offer in intake["offers"] if offer["relationships"]
            ],
            "teaching": {"state": CROSS_SALE_TEACHING_STATE},
            "route_node": False,
            "surface": "thank_you",
        },
    }
    if council is not None:
        record["council"] = council
    return record


def compile_route(intake: Dict[str, Any],
                  council: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Compile with the real Skill 49 compiler, then run the structural gate."""
    graph = route_law.compile_route(launch_record(intake, council))["graph"]
    validate_route(graph)
    return graph


def _sinks(nodes: List[Dict[str, Any]], edges: List[Dict[str, str]]) -> Set[str]:
    outgoing = {e["from"] for e in edges}
    return {n["page_id"] for n in nodes if n["page_id"] not in outgoing}


def _reachable(start: str, edges: List[Dict[str, str]]) -> Set[str]:
    seen: Set[str] = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(e["to"] for e in edges if e["from"] == cur)
    return seen


def validate_route(graph: Dict[str, Any]) -> None:
    """Raise RouteError on the first structural violation. All rules from doc 02 section 4."""
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if len(nodes) < 3:
        raise RouteError("AF-LAUNCH-ROUTE-NODES", "fewer than three route nodes")

    ids = [n.get("page_id") for n in nodes]
    if len(set(ids)) != len(ids):
        raise RouteError("AF-LAUNCH-ROUTE-NODES", "duplicate page_id in route nodes")
    for n in nodes:
        if n.get("role") not in ROUTE_ROLES:
            raise RouteError("AF-LAUNCH-ROUTE-NODES", f"unknown role {n.get('role')!r}")

    roles = [n["role"] for n in nodes]
    if roles.count("landing") != 1:
        raise RouteError("AF-LAUNCH-ROUTE-ENTRY", "exactly one landing entry is required")
    if roles.count("thank_you") != 1:
        raise RouteError("AF-LAUNCH-ROUTE-TERMINAL", "exactly one thank_you terminal is required")
    if roles.count("upsell_2") > 1:
        raise RouteError("AF-LAUNCH-ROUTE-U2", "one canonical upsell_2 instance only")

    landing = next(n["page_id"] for n in nodes if n["role"] == "landing")
    if any(e["from"] == landing for e in edges if e["event"] == "explicit_decline"):
        raise RouteError("AF-LAUNCH-ROUTE-ENTRY", "the landing entry has no decline branch")
    if any(e["to"] == landing for e in edges):
        raise RouteError("AF-LAUNCH-ROUTE-ENTRY", "the landing entry must have no incoming edge")

    for e in edges:
        if e.get("from") not in ids or e.get("to") not in ids:
            raise RouteError("AF-LAUNCH-ROUTE-REF", f"edge references an unknown node: {e!r}")
        if e.get("event") not in ("interest_submitted", "selection_validated",
                                  "payment_succeeded", "explicit_decline"):
            raise RouteError("AF-LAUNCH-ROUTE-EVENT", f"unknown edge event {e.get('event')!r}")
        if not str(e.get("guard") or "").strip():
            raise RouteError("AF-LAUNCH-ROUTE-GUARD", "every edge needs a guard id")

    reached = _reachable(landing, edges)
    for n in nodes:
        if n["page_id"] not in reached:
            raise RouteError("AF-LAUNCH-ROUTE-REACH",
                             f"enabled node {n['role']} is unreachable from the landing entry")

    # No cycle anywhere: the purchase progression is strictly forward.
    state: Dict[str, int] = {}

    def walk(node: str) -> None:
        state[node] = 1
        for e in edges:
            if e["from"] != node:
                continue
            nxt = e["to"]
            if state.get(nxt) == 1:
                raise RouteError("AF-LAUNCH-ROUTE-CYCLE", f"cycle through {nxt}")
            if state.get(nxt, 0) == 0:
                walk(nxt)
        state[node] = 2

    walk(landing)

    thank_you = next(n["page_id"] for n in nodes if n["role"] == "thank_you")
    sinks = _sinks(nodes, edges)
    if sinks != {thank_you}:
        others = sorted(s for s in sinks if s != thank_you)
        raise RouteError("AF-LAUNCH-ROUTE-TERMINAL",
                         f"every success/decline path must terminate at thank_you; "
                         f"non-terminating sink(s) {others!r}")
    if any(e["from"] == thank_you for e in edges):
        raise RouteError("AF-LAUNCH-ROUTE-TERMINAL", "thank_you must have no outgoing edge")

    # A purchase edge must exist for every enabled paid step, and only those.
    for role in ("checkout", "upsell_1", "downsell_1", "upsell_2"):
        if role in roles:
            page = next(n["page_id"] for n in nodes if n["role"] == role)
            if not any(e["from"] == page and e["event"] == "payment_succeeded" for e in edges):
                raise RouteError("AF-LAUNCH-ROUTE-OFFER",
                                 f"enabled {role} has no payment_succeeded edge to its offer")
    for e in edges:
        if e["event"] == "payment_succeeded":
            src_role = next(n["role"] for n in nodes if n["page_id"] == e["from"])
            if src_role not in ("checkout", "upsell_1", "downsell_1", "upsell_2"):
                raise RouteError("AF-LAUNCH-ROUTE-OFFER",
                                 f"payment_succeeded edge leaves non-purchase node {src_role}")

    if graph.get("pending_failed_payment_behavior") != PENDING_FAILED_PAYMENT_BEHAVIOR:
        raise RouteError("AF-LAUNCH-ROUTE-PAYMENT-ERROR",
                         "pending/failed payment must stay recoverable and grant no access")
