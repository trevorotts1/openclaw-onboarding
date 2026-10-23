#!/usr/bin/env python3
"""Delivery graph validation (stream W1, assignment W1C-U1).

Separates the two edge regimes of the GHL delivery contract
(GHL-DELIVERY-SPEC.md, "Delivery contract (W1 owns the normative versioned
schema)"):

  * Website navigation -- menus, shared sections, general navigation.
    Cycles are legitimate (home -> about -> home is a real menu, not a defect).
    Navigation cycles are NEVER reported as violations.
  * Commerce progression -- explicit accept/decline/submit/success/error edges.
    Ordered. A cycle here is a real defect. Menus can never substitute for an
    explicit commerce edge: outcome reachability is computed on commerce edges
    ONLY, so a funnel step wired to its confirmation page by a menu link fails.

The two regimes are disjoint by construction: an edge's kind determines its
class exactly once (EdgeKind.is_commerce / is_navigation), and raw records with
an unknown edge or node kind are rejected at the seam instead of being guessed
into a class. Administrative folders/containers are metadata on nodes and
NEVER generate navigation hierarchy or nested URL paths: every edge comes from
the record's explicit edge list ("Administrative folders != navigation
hierarchy != nested URL paths").

Rules (violation codes):
  dangling_endpoint            edge endpoint is not a declared logical ID
  commerce_cycle               cycle among commerce edges (ordering violation)
  commerce_edge_backward       commerce edge violates declared funnel order
  missing_required_outcome     commerce step lacks explicit outcome edges
  commerce_outcome_unreachable commerce step cannot reach a terminal outcome
                               (CONFIRMATION/ERROR_PAGE) via commerce edges only

Provisional outcome requirements (recorded as such until W1A/W8 confirm):
  OFFER    -> accept, decline        (upsell/downsell/bump decision)
  CHECKOUT -> submit, success, error (native checkout / order form)
  FORM     -> submit                 (native form/survey submission)

Integration seam (PROVISIONAL unit): graph_from_contract(record) is the single
seam to W1A's normative schema module shared-utils/delivery/npage_contract.py.
That module does not exist at this head (checked: repo tree and every lane
worktree, 2026-10-23), so the seam consumes the normative field names from
GHL-DELIVERY-SPEC.md directly: nodes carry logical_id/kind/role/state/order/
container identity, edges carry from/to/kind. When npage_contract.py lands,
only graph_from_contract needs reconciling to its record type; the rules below
operate on DeliveryGraph and stay. Outstanding integration is recorded in the
W1C-U1 build evidence alongside this docstring.

Runnable check (assert-based self-check):
    python3 -I shared-utils/delivery/graph_validation.py
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set


class EdgeKind(Enum):
    """The complete edge vocabulary of the delivery contract. One kind maps to
    exactly one regime; nothing is inferred or dual-classed."""

    # Website navigation (cycles legitimate)
    MENU = "menu"
    SHARED_SECTION = "shared_section"
    NAV = "nav"
    # Commerce progression (explicit, ordered)
    ACCEPT = "accept"
    DECLINE = "decline"
    SUBMIT = "submit"
    SUCCESS = "success"
    ERROR = "error"

    @property
    def is_commerce(self) -> bool:
        return self in COMMERCE_KINDS

    @property
    def is_navigation(self) -> bool:
        return self in NAV_KINDS


NAV_KINDS = frozenset({EdgeKind.MENU, EdgeKind.SHARED_SECTION, EdgeKind.NAV})
COMMERCE_KINDS = frozenset(
    {EdgeKind.ACCEPT, EdgeKind.DECLINE, EdgeKind.SUBMIT, EdgeKind.SUCCESS, EdgeKind.ERROR}
)


class NodeKind(Enum):
    """Page node kinds relevant to edge obligations."""

    PAGE = "page"                      # ordinary website page
    OFFER = "offer"                    # upsell / downsell / order bump decision
    CHECKOUT = "checkout"              # native checkout / order form
    FORM = "form"                      # native form / survey
    CONFIRMATION = "confirmation"      # success target
    ERROR_PAGE = "error_page"          # error target


COMMERCE_STEP_KINDS = frozenset({NodeKind.OFFER, NodeKind.CHECKOUT, NodeKind.FORM})
TERMINAL_KINDS = frozenset({NodeKind.CONFIRMATION, NodeKind.ERROR_PAGE})
REQUIRED_OUTCOMES: Dict[NodeKind, frozenset] = {
    NodeKind.OFFER: frozenset({EdgeKind.ACCEPT, EdgeKind.DECLINE}),
    NodeKind.CHECKOUT: frozenset({EdgeKind.SUBMIT, EdgeKind.SUCCESS, EdgeKind.ERROR}),
    NodeKind.FORM: frozenset({EdgeKind.SUBMIT}),
}


class LifecycleState(Enum):
    """Distinct delivery states. Distinctness is preserved, never collapsed."""

    PLANNED = "planned"
    CREATED = "created"
    CONFIGURED = "configured"
    PUBLISHED = "published"
    VERIFIED = "verified"


class GraphShapeError(ValueError):
    """The raw record is not a well-formed contract record (unknown kind,
    duplicate logical ID, malformed edge). Rejected at the seam, never guessed."""


class GraphValidationError(ValueError):
    """Raised by assert_valid; carries every violation found."""

    def __init__(self, violations: Sequence["Violation"]):
        self.violations = list(violations)
        super().__init__("; ".join(f"{v.code}: {v.message}" for v in self.violations))


@dataclass(frozen=True)
class Node:
    logical_id: str
    kind: NodeKind
    role: Optional[str] = None        # pages may share a role with distinct identity
    state: Optional[LifecycleState] = None
    order: Optional[int] = None       # declared funnel ordering, if any
    container: Optional[str] = None   # admin folder/container identity: metadata only
    name: Optional[str] = None


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    kind: EdgeKind

    @property
    def is_commerce(self) -> bool:
        return self.kind.is_commerce

    @property
    def is_navigation(self) -> bool:
        return self.kind.is_navigation


@dataclass(frozen=True)
class Violation:
    code: str
    message: str


@dataclass
class DeliveryGraph:
    nodes: Dict[str, Node]
    edges: List[Edge]


# --------------------------------------------------------------------------
# Integration seam: raw contract record -> DeliveryGraph
# --------------------------------------------------------------------------

def graph_from_contract(record: Mapping) -> DeliveryGraph:
    """Parse a normative delivery-contract record into a DeliveryGraph.

    This is the single seam to W1A's shared-utils/delivery/npage_contract.py
    (not yet landed). Expected shape, per GHL-DELIVERY-SPEC.md::

        {
          "nodes": [{"logical_id": str, "kind": str, "role": str?, "state": str?,
                     "order": int?, "container": str?, "name": str?}, ...],
          "edges": [{"from": str, "to": str, "kind": str}, ...]
        }

    Edges are built ONLY from the explicit edge list; node container/folder
    identities never generate navigation hierarchy. Unknown kinds and duplicate
    logical IDs raise GraphShapeError.
    """
    if not isinstance(record, Mapping):
        raise GraphShapeError("record must be a mapping")
    raw_nodes = record.get("nodes", [])
    raw_edges = record.get("edges", [])
    if not isinstance(raw_nodes, Iterable) or isinstance(raw_nodes, (str, bytes)):
        raise GraphShapeError("record['nodes'] must be a list")
    if not isinstance(raw_edges, Iterable) or isinstance(raw_edges, (str, bytes)):
        raise GraphShapeError("record['edges'] must be a list")

    nodes: Dict[str, Node] = {}
    for raw in raw_nodes:
        if not isinstance(raw, Mapping):
            raise GraphShapeError(f"node entry must be a mapping: {raw!r}")
        logical_id = raw.get("logical_id")
        if not logical_id or not isinstance(logical_id, str):
            raise GraphShapeError(f"node missing logical_id: {raw!r}")
        if logical_id in nodes:
            raise GraphShapeError(f"duplicate logical_id {logical_id!r}")
        try:
            kind = NodeKind(raw.get("kind"))
        except ValueError:
            raise GraphShapeError(f"unknown node kind on {logical_id!r}: {raw.get('kind')!r}")
        state = raw.get("state")
        if state is not None:
            try:
                state = LifecycleState(state)
            except ValueError:
                raise GraphShapeError(f"unknown state on {logical_id!r}: {state!r}")
        order = raw.get("order")
        if order is not None and not isinstance(order, int):
            raise GraphShapeError(f"order must be an int on {logical_id!r}: {order!r}")
        nodes[logical_id] = Node(
            logical_id=logical_id,
            kind=kind,
            role=raw.get("role"),
            state=state,
            order=order,
            container=raw.get("container"),
            name=raw.get("name"),
        )

    edges: List[Edge] = []
    for raw in raw_edges:
        if not isinstance(raw, Mapping):
            raise GraphShapeError(f"edge entry must be a mapping: {raw!r}")
        try:
            kind = EdgeKind(raw.get("kind"))
        except ValueError:
            raise GraphShapeError(f"unknown edge kind: {raw.get('kind')!r}")
        edges.append(Edge(src=str(raw.get("from")), dst=str(raw.get("to")), kind=kind))
    return DeliveryGraph(nodes=nodes, edges=edges)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate_graph(graph: DeliveryGraph) -> List[Violation]:
    """Validate a delivery graph. Returns every violation; empty list is valid.

    Navigation edges are never inspected for cycles. Commerce edges are.
    """
    violations: List[Violation] = []

    # 1. Every endpoint resolves to a declared logical ID (both regimes).
    for edge in graph.edges:
        for end in (edge.src, edge.dst):
            if end not in graph.nodes:
                violations.append(Violation(
                    "dangling_endpoint",
                    f"{edge.kind.value} edge {edge.src!r}->{edge.dst!r} references "
                    f"undeclared logical ID {end!r}",
                ))

    # 2. Commerce edges respect declared funnel ordering (strictly forward).
    for edge in graph.edges:
        if not edge.is_commerce:
            continue
        src, dst = graph.nodes.get(edge.src), graph.nodes.get(edge.dst)
        if src and dst and src.order is not None and dst.order is not None:
            if dst.order <= src.order:
                violations.append(Violation(
                    "commerce_edge_backward",
                    f"{edge.kind.value} edge {edge.src!r}(order {src.order})->"
                    f"{edge.dst!r}(order {dst.order}) moves backward in funnel order",
                ))

    # 3. Commerce subgraph is acyclic; navigation cycles stay legitimate.
    violations.extend(_commerce_cycles(graph))

    # 4. Explicit outcome completeness per commerce step kind.
    out_kinds: Dict[str, Set[EdgeKind]] = {lid: set() for lid in graph.nodes}
    for edge in graph.edges:
        if edge.is_commerce and edge.src in out_kinds:
            out_kinds[edge.src].add(edge.kind)
    for lid, node in graph.nodes.items():
        required = REQUIRED_OUTCOMES.get(node.kind)
        if not required:
            continue
        missing = sorted(k.value for k in required - out_kinds.get(lid, set()))
        if missing:
            violations.append(Violation(
                "missing_required_outcome",
                f"{node.kind.value} node {lid!r} lacks explicit outcome edges: "
                f"{', '.join(missing)}",
            ))

    # 5. Every commerce step reaches a terminal outcome on commerce edges ONLY.
    #    A menu/shared-section/nav edge can never substitute for progression.
    commerce_targets: Dict[str, List[str]] = {lid: [] for lid in graph.nodes}
    for edge in graph.edges:
        if edge.is_commerce and edge.src in commerce_targets and edge.dst in graph.nodes:
            commerce_targets[edge.src].append(edge.dst)
    for lid, node in graph.nodes.items():
        if node.kind not in COMMERCE_STEP_KINDS:
            continue
        if not _reaches_terminal(lid, graph, commerce_targets):
            violations.append(Violation(
                "commerce_outcome_unreachable",
                f"commerce step {lid!r} reaches no {sorted(k.value for k in TERMINAL_KINDS)} "
                f"via commerce edges alone (navigation edges do not count)",
            ))

    return violations


def assert_valid(graph: DeliveryGraph) -> None:
    """Raise GraphValidationError listing every violation, or return None."""
    violations = validate_graph(graph)
    if violations:
        raise GraphValidationError(violations)


def _commerce_cycles(graph: DeliveryGraph) -> List[Violation]:
    """Report cycles formed by commerce edges only. Navigation cycles are
    legitimate by contract and are never inspected here."""
    succ: Dict[str, List[str]] = {lid: [] for lid in graph.nodes}
    for edge in graph.edges:
        if edge.is_commerce and edge.src in succ and edge.dst in graph.nodes:
            succ[edge.src].append(edge.dst)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {lid: WHITE for lid in graph.nodes}
    violations: List[Violation] = []
    for root in sorted(graph.nodes):
        if color[root] != WHITE:
            continue
        stack: List[tuple] = [(root, iter(succ[root]))]
        color[root] = GRAY
        path = [root]
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                if color[nxt] == GRAY:
                    cycle = path[path.index(nxt):] + [nxt]
                    violations.append(Violation(
                        "commerce_cycle",
                        "cycle in commerce progression: " + " -> ".join(cycle),
                    ))
                elif color[nxt] == WHITE:
                    color[nxt] = GRAY
                    path.append(nxt)
                    stack.append((nxt, iter(succ[nxt])))
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                path.pop()
                stack.pop()
    return violations


def _reaches_terminal(
    start: str, graph: DeliveryGraph, commerce_targets: Dict[str, List[str]]
) -> bool:
    seen: Set[str] = {start}
    queue = [start]
    while queue:
        node = queue.pop()
        if node != start and graph.nodes[node].kind in TERMINAL_KINDS:
            return True
        for nxt in commerce_targets.get(node, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


# --------------------------------------------------------------------------
# Assert-based self-check
# --------------------------------------------------------------------------

def _record(nodes: List[dict], edges: List[dict]) -> Mapping:
    return {"nodes": nodes, "edges": edges}


def _codes(graph: DeliveryGraph) -> Set[str]:
    return {v.code for v in validate_graph(graph)}


def self_check() -> None:
    # 1. Navigation cycles are legitimate: a real menu loop yields ZERO
    #    violations (the same shape with a commerce edge fails -- see 2).
    nav_cycle = graph_from_contract(_record(
        [
            {"logical_id": "home", "kind": "page", "role": "home", "state": "configured"},
            {"logical_id": "about", "kind": "page", "role": "about"},
            {"logical_id": "shared_footer", "kind": "page", "role": "shared-section"},
        ],
        [
            {"from": "home", "to": "about", "kind": "menu"},
            {"from": "about", "to": "home", "kind": "menu"},
            {"from": "home", "to": "shared_footer", "kind": "shared_section"},
            {"from": "shared_footer", "to": "home", "kind": "nav"},
            {"from": "about", "to": "about", "kind": "nav"},
        ],
    ))
    assert validate_graph(nav_cycle) == [], validate_graph(nav_cycle)

    # 2. Identical two-node shape with a commerce edge is a real defect.
    commerce_cycle = graph_from_contract(_record(
        [
            {"logical_id": "offer1", "kind": "offer", "order": 1},
            {"logical_id": "checkout", "kind": "checkout", "order": 2},
            {"logical_id": "confirm", "kind": "confirmation", "order": 3},
            {"logical_id": "err", "kind": "error_page", "order": 3},
        ],
        [
            {"from": "offer1", "to": "checkout", "kind": "accept"},
            {"from": "checkout", "to": "offer1", "kind": "decline"},
            {"from": "checkout", "to": "confirm", "kind": "success"},
            {"from": "checkout", "to": "err", "kind": "error"},
            {"from": "offer1", "to": "confirm", "kind": "decline"},
        ],
    ))
    assert "commerce_cycle" in _codes(commerce_cycle)

    # 3. Backward commerce edge violates declared funnel order.
    backward = graph_from_contract(_record(
        [
            {"logical_id": "offer1", "kind": "offer", "order": 1},
            {"logical_id": "checkout", "kind": "checkout", "order": 2},
            {"logical_id": "confirm", "kind": "confirmation", "order": 3},
            {"logical_id": "err", "kind": "error_page", "order": 3},
        ],
        [
            {"from": "offer1", "to": "checkout", "kind": "accept"},
            {"from": "checkout", "to": "offer1", "kind": "submit"},
            {"from": "checkout", "to": "confirm", "kind": "success"},
            {"from": "checkout", "to": "err", "kind": "error"},
            {"from": "offer1", "to": "confirm", "kind": "decline"},
        ],
    ))
    assert "commerce_edge_backward" in _codes(backward)

    # 4. Dangling endpoint is reported in both regimes.
    dangling = graph_from_contract(_record(
        [{"logical_id": "home", "kind": "page"}],
        [
            {"from": "home", "to": "ghost", "kind": "menu"},
            {"from": "home", "to": "phantom", "kind": "success"},
        ],
    ))
    assert len([v for v in validate_graph(dangling) if v.code == "dangling_endpoint"]) == 2

    # 5. The seam rejects what the contract does not define -- unknown edge
    #    kind, unknown node kind, unknown state, duplicate logical ID. Nothing
    #    is guessed into a regime.
    for bad in (
        _record([{"logical_id": "a", "kind": "page"}],
                [{"from": "a", "to": "a", "kind": "link"}]),
        _record([{"logical_id": "a", "kind": "wizard"}], []),
        _record([{"logical_id": "a", "kind": "page", "state": "live"}], []),
        _record([{"logical_id": "a", "kind": "page"}, {"logical_id": "a", "kind": "page"}], []),
    ):
        try:
            graph_from_contract(bad)
        except GraphShapeError:
            pass
        else:
            raise AssertionError(f"seam must reject malformed record: {bad}")

    # 6. Missing explicit outcomes: an offer without decline fails; the same
    #    offer with explicit accept+decline passes this rule.
    offer_missing = graph_from_contract(_record(
        [
            {"logical_id": "offer1", "kind": "offer", "order": 1},
            {"logical_id": "confirm", "kind": "confirmation", "order": 2},
        ],
        [{"from": "offer1", "to": "confirm", "kind": "accept"}],
    ))
    assert "missing_required_outcome" in _codes(offer_missing)

    # 7. Navigation can never substitute for commerce progression: the form is
    #    wired to its confirmation page by a MENU edge only -- still unreachable.
    nav_substitute = graph_from_contract(_record(
        [
            {"logical_id": "form1", "kind": "form", "order": 1},
            {"logical_id": "step2", "kind": "page", "order": 2},
            {"logical_id": "confirm", "kind": "confirmation", "order": 3},
        ],
        [
            {"from": "form1", "to": "step2", "kind": "submit"},
            {"from": "step2", "to": "confirm", "kind": "menu"},
        ],
    ))
    assert "commerce_outcome_unreachable" in _codes(nav_substitute)

    # 8. Pages may share a role with distinct identity -- never a violation.
    role_share = graph_from_contract(_record(
        [
            {"logical_id": "legal_a", "kind": "page", "role": "legal"},
            {"logical_id": "legal_b", "kind": "page", "role": "legal"},
        ],
        [],
    ))
    assert validate_graph(role_share) == []

    # 9. Administrative containers never generate nav hierarchy or URL paths:
    #    nested containers with NO explicit edges produce NO edges at all.
    containers = graph_from_contract(_record(
        [
            {"logical_id": "a", "kind": "page", "container": "folder/inner"},
            {"logical_id": "b", "kind": "page", "container": "folder/inner"},
        ],
        [],
    ))
    assert containers.edges == [], containers.edges
    assert validate_graph(containers) == []

    # 10. Full mixed record valid: website nav cycle + complete commerce
    #     progression with explicit accept/decline/submit/success/error edges.
    full = graph_from_contract(_record(
        [
            {"logical_id": "home", "kind": "page", "role": "home", "state": "configured",
             "container": "site-root"},
            {"logical_id": "about", "kind": "page", "role": "about", "container": "site-root"},
            {"logical_id": "offer1", "kind": "offer", "order": 1, "state": "planned"},
            {"logical_id": "checkout", "kind": "checkout", "order": 2, "state": "planned"},
            {"logical_id": "form1", "kind": "form", "order": 3, "state": "planned"},
            {"logical_id": "confirm", "kind": "confirmation", "order": 4},
            {"logical_id": "err", "kind": "error_page", "order": 4},
        ],
        [
            {"from": "home", "to": "about", "kind": "menu"},
            {"from": "about", "to": "home", "kind": "menu"},
            {"from": "home", "to": "offer1", "kind": "nav"},
            {"from": "offer1", "to": "checkout", "kind": "accept"},
            {"from": "offer1", "to": "confirm", "kind": "decline"},
            {"from": "checkout", "to": "form1", "kind": "submit"},
            {"from": "checkout", "to": "confirm", "kind": "success"},
            {"from": "checkout", "to": "err", "kind": "error"},
            {"from": "form1", "to": "confirm", "kind": "submit"},
            {"from": "confirm", "to": "home", "kind": "nav"},
        ],
    ))
    assert validate_graph(full) == [], validate_graph(full)
    assert_valid(full)  # convenience wrapper raises nothing on a valid graph

    # 11. assert_valid raises and lists every violation on an invalid graph.
    try:
        assert_valid(offer_missing)
    except GraphValidationError as exc:
        assert exc.violations and any(
            v.code == "missing_required_outcome" for v in exc.violations
        )
    else:
        raise AssertionError("assert_valid must refuse an incomplete offer")


if __name__ == "__main__":
    self_check()
    _sample = graph_from_contract(_record(
        [{"logical_id": "a", "kind": "page"}],
        [{"from": "a", "to": "a", "kind": "menu"}],
    ))
    print("graph_validation self-check: PASS")
    print(f"  edge regimes separated: {len(NAV_KINDS)} navigation kinds vs "
          f"{len(COMMERCE_KINDS)} commerce kinds")
    print("  navigation cycles: legitimate (never reported)")
    print("  commerce cycles: violation codes "
          f"{sorted({'commerce_cycle', 'commerce_edge_backward'})}")
    print(f"  provisional outcome requirements: "
          f"{ {k.value: sorted(x.value for x in v) for k, v in REQUIRED_OUTCOMES.items()} }")
