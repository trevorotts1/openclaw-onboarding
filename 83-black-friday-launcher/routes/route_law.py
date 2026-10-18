"""Canonical verified-payment route law for the Launcher (LAUNCH-02).

The graph is NOT re-derived here: it is compiled by the real Skill 49
compiler. This module encodes the contract as executable invariants over
that compiled graph and the compiler's own runtime resolver, so a graph
that drifts from doc 02 section 4 fails by name instead of passing quietly.

Buyer-time navigation (`navigate`) is deliberately separate from build-time
page generation (`build_time.py`). Build-time never calls this module's
navigation functions.
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, Iterable, List, Optional

import substrate

PAGE_ROLES = (
    "landing",
    "product_selection",
    "checkout",
    "upsell_1",
    "downsell_1",
    "upsell_2",
    "thank_you",
)
PURCHASE_STAGES = ("checkout", "upsell_1", "downsell_1", "upsell_2")
ENTRY_EVENTS = ("interest_submitted", "selection_validated")
STAY_EVENTS = ("payment_pending", "payment_failed", "requires_customer_action")
PAID_GUARD = {
    "checkout": "verified_main_payment",
    "upsell_1": "verified_u1_payment",
    "downsell_1": "verified_d1_payment",
    "upsell_2": "verified_u2_payment",
}
DECLINE_GUARD = "no_charge_decline"
CONTACT_GUARD = "verified_native_contact_submit"
SELECTION_GUARD = "allowlisted_offer_price"


class RouteInvariantError(ValueError):
    """A transition, node or edge the canonical contract does not allow."""


def compile_route(launch: Dict[str, Any]) -> Dict[str, Any]:
    """Compile + serialize with the real compiler; return graph and hash."""
    compiler = substrate.compiler()
    graph = compiler.compile_route(launch)
    raw = compiler.serialize_graph(graph)
    return {
        "graph": graph,
        "bytes": raw,
        "route_graph_hash": compiler.graph_hash(graph),
    }


def _page_id(launch_id: str, role: str) -> str:
    return substrate.compiler().page_id(launch_id, role)


def _extras(launch: Dict[str, Any]) -> tuple[bool, bool, bool]:
    extras = launch.get("extras") or {}
    return (
        extras.get("upsell_1") is True,
        extras.get("downsell_1") is True,
        extras.get("upsell_2") is True,
    )


def _edges(graph: Dict[str, Any]) -> List[Dict[str, str]]:
    return [dict(edge) for edge in graph.get("edges", [])]


def _edge_key(edge: Dict[str, str]) -> tuple:
    return (edge.get("from"), edge.get("event"), edge.get("to"), edge.get("guard"))


def _expected_edges(launch: Dict[str, Any]) -> List[tuple]:
    """Doc 02 section 4 edge set, in the contract's own vocabulary."""
    lid = launch["launch_id"]
    u1, d1, u2 = _extras(launch)
    mode = launch.get("journey_mode")
    pid = lambda role: _page_id(lid, role)  # noqa: E731
    edges: List[tuple] = []
    if mode == "multiple_options":
        edges.append((pid("landing"), "interest_submitted",
                      pid("product_selection"), CONTACT_GUARD))
        edges.append((pid("product_selection"), "selection_validated",
                      pid("checkout"), SELECTION_GUARD))
    else:
        edges.append((pid("landing"), "interest_submitted",
                      pid("checkout"), CONTACT_GUARD))
    edges.append((pid("checkout"), "payment_succeeded",
                  pid("upsell_1") if u1 else pid("thank_you"),
                  PAID_GUARD["checkout"]))
    if u1:
        edges.append((pid("upsell_1"), "payment_succeeded",
                      pid("upsell_2") if u2 else pid("thank_you"),
                      PAID_GUARD["upsell_1"]))
        edges.append((pid("upsell_1"), "explicit_decline",
                      pid("downsell_1") if d1 else pid("thank_you"),
                      DECLINE_GUARD))
    if d1:
        edges.append((pid("downsell_1"), "payment_succeeded",
                      pid("upsell_2") if u2 else pid("thank_you"),
                      PAID_GUARD["downsell_1"]))
        edges.append((pid("downsell_1"), "explicit_decline",
                      pid("thank_you"), DECLINE_GUARD))
    if u2:
        edges.append((pid("upsell_2"), "payment_succeeded",
                      pid("thank_you"), PAID_GUARD["upsell_2"]))
        edges.append((pid("upsell_2"), "explicit_decline",
                      pid("thank_you"), DECLINE_GUARD))
    return edges


def graph_violations(launch: Dict[str, Any],
                     graph: Optional[Dict[str, Any]] = None) -> List[str]:
    """Every route invariant, each named. Empty list == the graph holds."""
    if graph is None:
        graph = compile_route(launch)["graph"]
    compiler = substrate.compiler()
    violations: List[str] = []
    lid = launch["launch_id"]
    u1, d1, u2 = _extras(launch)
    pid = lambda role: _page_id(lid, role)  # noqa: E731

    # 1. Node set and page ids are exactly the compiler's enabled roles.
    try:
        expected_roles = compiler.expected_roles(launch)
    except compiler.RouteError as exc:
        return [f"launch record cannot compile: {exc}"]
    nodes = graph.get("nodes", [])
    roles = [node.get("role") for node in nodes]
    if roles != expected_roles:
        violations.append(
            f"node roles {roles!r} differ from enabled roles {expected_roles!r}")
    expected_page_ids = [pid(role) for role in expected_roles]
    page_ids = [node.get("page_id") for node in nodes]
    if page_ids != expected_page_ids:
        violations.append(
            f"page ids {page_ids!r} differ from {expected_page_ids!r}")
    if len(set(page_ids)) != len(page_ids):
        violations.append("duplicate page_id node")
    if "bump" in roles:
        violations.append("bump must be a checkout component, never a route node")

    # 2. Edge set is exactly doc 02 section 4 with verified guards.
    actual = sorted(_edge_key(edge) for edge in _edges(graph))
    expected = sorted(_expected_edges(launch))
    if actual != expected:
        missing = [edge for edge in expected if edge not in actual]
        extra = [edge for edge in actual if edge not in expected]
        if missing:
            violations.append(f"missing contract edges: {missing!r}")
        if extra:
            violations.append(f"unexpected contract edges: {extra!r}")

    # 3. Named single-point invariants (each fails independently).
    by_source: Dict[tuple, List[Dict[str, str]]] = {}
    for edge in _edges(graph):
        by_source.setdefault((edge.get("from"), edge.get("event")), []).append(edge)

    def exactly_one(source: str, event: str, target: str, guard: str,
                    label: str) -> None:
        found = by_source.get((source, event), [])
        if len(found) != 1:
            violations.append(f"{label}: expected exactly one edge, found {len(found)}")
            return
        if (found[0].get("to"), found[0].get("guard")) != (target, guard):
            violations.append(
                f"{label}: expected {target!r}/{guard!r}, got "
                f"{found[0].get('to')!r}/{found[0].get('guard')!r}")

    exactly_one(pid("checkout"), "payment_succeeded",
                pid("upsell_1") if u1 else pid("thank_you"),
                PAID_GUARD["checkout"], "U1 follows an original verified purchase")
    if by_source.get((pid("checkout"), "explicit_decline")):
        violations.append("checkout has no decline edge; abandonment is not a route")
    if u1:
        exactly_one(pid("upsell_1"), "explicit_decline",
                    pid("downsell_1") if d1 else pid("thank_you"),
                    DECLINE_GUARD, "D1 only on an explicit U1 decline")
        exactly_one(pid("upsell_1"), "payment_succeeded",
                    pid("upsell_2") if u2 else pid("thank_you"),
                    PAID_GUARD["upsell_1"], "U1 paid edge")
    if d1:
        exactly_one(pid("downsell_1"), "payment_succeeded",
                    pid("upsell_2") if u2 else pid("thank_you"),
                    PAID_GUARD["downsell_1"], "D1 paid edge")
        exactly_one(pid("downsell_1"), "explicit_decline",
                    pid("thank_you"), DECLINE_GUARD, "D1 decline edge")
    if u2:
        # U2 only after a verified U1 or D1 purchase, one canonical node.
        u2_inbound = [
            edge for edge in _edges(graph)
            if edge.get("to") == pid("upsell_2")
        ]
        expected_inbound = []
        if u1:
            expected_inbound.append((pid("upsell_1"), "payment_succeeded",
                                     PAID_GUARD["upsell_1"]))
        if d1:
            expected_inbound.append((pid("downsell_1"), "payment_succeeded",
                                     PAID_GUARD["downsell_1"]))
        got_inbound = sorted((edge.get("from"), edge.get("event"),
                              edge.get("guard")) for edge in u2_inbound)
        if got_inbound != sorted(expected_inbound):
            violations.append(
                "U2 must be reachable only from a verified U1 or D1 purchase; "
                f"inbound edges are {got_inbound!r}")
    else:
        if any(edge.get("to") == pid("upsell_2") or
               edge.get("from") == pid("upsell_2") for edge in _edges(graph)):
            violations.append("upsell_2 is disabled but present in the graph")

    # 4. Every paid edge carries a verified_* guard; declines carry no-charge.
    for edge in _edges(graph):
        if edge.get("event") == "payment_succeeded" and not str(
                edge.get("guard", "")).startswith("verified_"):
            violations.append(
                f"paid edge {edge!r} does not name a verified payment guard")
        if edge.get("event") == "explicit_decline" and \
                edge.get("guard") != DECLINE_GUARD:
            violations.append(
                f"decline edge {edge!r} does not name {DECLINE_GUARD!r}")
        if edge.get("event") in ("tab_closed", "abandoned", "close"):
            violations.append(
                f"abandonment event {edge.get('event')!r} must never be an edge")

    # 5. Extras law, independent of the compiler's own guard.
    if not u1 and (d1 or u2):
        violations.append("U1 disabled requires D1 and U2 disabled")

    # 6. The stored hash is the hash of the exact emitted bytes.
    raw = compiler.serialize_graph(graph)
    if graph.get("schema_version") != compiler.SCHEMA_VERSION:
        violations.append(
            f"graph schema_version {graph.get('schema_version')!r} is not "
            f"{compiler.SCHEMA_VERSION!r}")
    if compiler.graph_hash(graph) != compiler.hashlib.sha256(raw).hexdigest():
        violations.append("graph hash does not match serialized graph bytes")
    declared = launch.get("route_graph_hash")
    if declared and declared != compiler.graph_hash(graph):
        violations.append(
            "declared route_graph_hash does not match the compiled graph")
    return violations


def assert_route_law(launch: Dict[str, Any],
                     graph: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fail closed on the first named invariant set violation."""
    graph = graph if graph is not None else compile_route(launch)["graph"]
    violations = graph_violations(launch, graph)
    if violations:
        raise RouteInvariantError("; ".join(violations))
    return graph


def _role_page_map(graph: Dict[str, Any]) -> Dict[str, str]:
    return {node["role"]: node["page_id"] for node in graph.get("nodes", [])}


def _find_edge(graph: Dict[str, Any], source: str, event: str) -> Dict[str, str]:
    matches = [edge for edge in graph.get("edges", [])
               if edge.get("from") == source and edge.get("event") == event]
    if len(matches) != 1:
        raise RouteInvariantError(
            f"expected exactly one {event!r} edge from {source!r}, "
            f"found {len(matches)}")
    return matches[0]


def navigate(graph: Dict[str, Any], stage: str, event: str,
             purchased: Iterable[str], *, payment_verified: bool = False,
             u1: bool = True, d1: bool = True, u2: bool = True) -> Dict[str, Any]:
    """Buyer-time navigation over the compiled graph.

    Build-time callers never reach this function: it takes purchase state.
    Every advance must match a compiled edge; there is no inferred target.
    """
    role_to_page = _role_page_map(graph)
    purchased_set: FrozenSet[str] = frozenset(purchased)

    if stage in ("landing", "product_selection"):
        if event not in ENTRY_EVENTS:
            raise RouteInvariantError(
                f"event {event!r} is not an entry transition at {stage!r}")
        edge = _find_edge(graph, role_to_page[stage], event)
        target_role = next(
            (role for role, page in role_to_page.items() if page == edge["to"]),
            None)
        if target_role is None:
            raise RouteInvariantError(
                f"edge target {edge['to']!r} is not an enabled page")
        return {"kind": "navigation", "to_stage": target_role,
                "to_page_id": edge["to"], "purchased_after": sorted(purchased_set),
                "guard": edge["guard"]}

    if stage == "thank_you":
        raise RouteInvariantError("thank_you is terminal")

    if stage not in PURCHASE_STAGES:
        raise RouteInvariantError(f"unknown purchase stage {stage!r}")

    if event == "tab_closed":
        # Doc 02 section 4: closing a tab is abandonment, never a decline and
        # never a purchase. State and entitlements are retained.
        return {"kind": "abandonment", "to_stage": stage,
                "to_page_id": role_to_page[stage],
                "purchased_after": sorted(purchased_set), "guard": None}

    compiler = substrate.compiler()
    try:
        target_stage, purchased_after = compiler.resolve_after(
            stage, event, purchased_set, u1, d1, u2,
            payment_verified=payment_verified)
    except compiler.RouteError as exc:
        raise RouteInvariantError(str(exc)) from exc

    if event in STAY_EVENTS:
        return {"kind": "stay_recoverable", "to_stage": stage,
                "to_page_id": role_to_page[stage],
                "purchased_after": sorted(purchased_after), "guard": None}

    guard = PAID_GUARD[stage] if event == "payment_succeeded" else DECLINE_GUARD
    edge = _find_edge(graph, role_to_page[stage], event)
    target_page = role_to_page[target_stage]
    if edge["to"] != target_page or edge["guard"] != guard:
        raise RouteInvariantError(
            f"{stage}/{event}: resolver targets {target_page!r}/{guard!r}, "
            f"graph edge targets {edge['to']!r}/{edge['guard']!r}")
    return {"kind": "transition", "to_stage": target_stage,
            "to_page_id": target_page,
            "purchased_after": sorted(purchased_after), "guard": guard}
