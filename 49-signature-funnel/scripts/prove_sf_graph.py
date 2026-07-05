#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sf_graph.py — fail-closed P6-COMPOSE gate for the Signature Funnel step graph.

FIX-XC-03a: P6-COMPOSE was an unconditional no-op (`_delegation_seam(..., None, ...)`
returned True with zero artifact) — a certificate could mint with no funnel graph at all.
This prover requires a real `funnel_graph.json` and validates it against MASTERDOC §3
(the 3/5/7 matrix + accept/decline branching) using the SAME source of truth the copy gate
uses: `structure/funnel_structure.json` -> `funnel_matrix`.

WHAT IT PROVES (all fail-closed; an unreadable/absent graph FAILS):
  * funnel_type == signature_funnel (when declared).                  -> AF-FUN-GRAPH-TYPE
  * funnel_size in {3,5,7} and node id set == funnel_matrix[size].     -> AF-FUN-GRAPH-SIZE / -NODES
  * every edge {from,to,on} references known nodes; on in the legal
    label set {proceed, accept, decline}.                             -> AF-FUN-GRAPH-EDGE
  * thank-you is the UNIQUE terminal (no outgoing); every other node
    has >= 1 outgoing edge (no non-terminal dead end).                -> AF-FUN-GRAPH-TERMINAL
  * every upsell node (upsell / upsell-2) carries BOTH an `accept` and
    a `decline` edge (the one-click branch).                          -> AF-FUN-GRAPH-BRANCH
  * forward reachability: every node reachable from `main`; and every
    node can reach `thank-you` (no path escapes the terminal).        -> AF-FUN-GRAPH-REACH

stdlib only. Exit 0 = pass, exit 2 = violation, exit 3 = usage / fail-closed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

FUNNEL_TYPE = "signature_funnel"
VALID_SIZES = (3, 5, 7)

ENTRY_NODE = "main"
TERMINAL_NODE = "thank-you"
UPSELL_NODES = ("upsell", "upsell-2")
DOWNSELL_NODES = ("downsell", "downsell-2")
LEGAL_EDGE_LABELS = ("proceed", "accept", "decline")

# profile key -> the short derived-page label used at P8 (U1/D1/U2/D2/TY).
DERIVED_LABELS = {
    "upsell": "U1",
    "downsell": "D1",
    "upsell-2": "U2",
    "downsell-2": "D2",
    "thank-you": "TY",
}
# pages that are NOT "derived" (the entry page + the 7-step order page).
_NON_DERIVED = {"main", "checkout"}


# ---------------------------------------------------------------------------
# The 3/5/7 matrix — single source of truth = structure/funnel_structure.json.
# ---------------------------------------------------------------------------
def _default_structure_path() -> Path:
    return Path(__file__).resolve().parent.parent / "structure" / "funnel_structure.json"


def _load_matrix(structure_path: Optional[Path] = None) -> Dict[str, List[str]]:
    path = structure_path or _default_structure_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    matrix = data.get("funnel_matrix") or {}
    out: Dict[str, List[str]] = {}
    for k, v in matrix.items():
        if isinstance(v, list):
            out[str(k)] = [str(x) for x in v]
    if not out:
        raise ValueError(f"funnel_matrix missing/empty in {path}")
    return out


def funnel_pages(size: int, structure_path: Optional[Path] = None) -> List[str]:
    """Ordered profile keys for a funnel size (all pages, incl. main/checkout)."""
    matrix = _load_matrix(structure_path)
    key = str(size)
    if key not in matrix:
        raise ValueError(f"funnel_size {size!r} not in matrix {sorted(matrix)}")
    return list(matrix[key])


def derived_pages(size: int, structure_path: Optional[Path] = None) -> List[str]:
    """The derived pages (everything past main/checkout) — the P8 ledger set."""
    return [p for p in funnel_pages(size, structure_path) if p not in _NON_DERIVED]


# ---------------------------------------------------------------------------
# Validation.
# ---------------------------------------------------------------------------
def verify(graph: Dict[str, Any],
           structure_path: Optional[Path] = None) -> Tuple[List[Tuple[str, str]], List[str]]:
    fails: List[Tuple[str, str]] = []
    notes: List[str] = []

    def fail(code: str, msg: str) -> None:
        fails.append((code, msg))

    if not isinstance(graph, dict):
        return [("AF-FUN-GRAPH-SIZE", "funnel graph is not a JSON object")], notes

    ftype = graph.get("funnel_type")
    if ftype is not None and ftype != FUNNEL_TYPE:
        fail("AF-FUN-GRAPH-TYPE", f"funnel_type is {ftype!r}, expected {FUNNEL_TYPE!r}")

    size = graph.get("funnel_size")
    if not isinstance(size, int) or size not in VALID_SIZES:
        return [("AF-FUN-GRAPH-SIZE",
                 f"funnel_size is {size!r}, must be one of {list(VALID_SIZES)}")] + fails, notes
    try:
        expected_nodes = funnel_pages(size, structure_path)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return [("AF-FUN-GRAPH-SIZE", f"cannot resolve the {size}-step matrix: {exc}")] + fails, notes

    raw_nodes = graph.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return [("AF-FUN-GRAPH-NODES", "graph carries no non-empty 'nodes' array")] + fails, notes
    node_ids: List[str] = []
    for n in raw_nodes:
        if isinstance(n, dict) and str(n.get("id", "")).strip():
            node_ids.append(str(n["id"]).strip())
        elif isinstance(n, str) and n.strip():
            node_ids.append(n.strip())
        else:
            fail("AF-FUN-GRAPH-NODES", f"a node entry is malformed: {n!r}")
    node_set: Set[str] = set(node_ids)
    if len(node_ids) != len(node_set):
        fail("AF-FUN-GRAPH-NODES", f"duplicate node id(s) in {node_ids}")
    if node_set != set(expected_nodes):
        missing = sorted(set(expected_nodes) - node_set)
        extra = sorted(node_set - set(expected_nodes))
        fail("AF-FUN-GRAPH-NODES",
             f"{size}-step node set mismatch vs MASTERDOC §3 — missing {missing}, unexpected {extra}")

    raw_edges = graph.get("edges")
    if not isinstance(raw_edges, list) or not raw_edges:
        return [("AF-FUN-GRAPH-EDGE", "graph carries no non-empty 'edges' array")] + fails, notes

    adjacency: Dict[str, List[Tuple[str, str]]] = {nid: [] for nid in node_set}
    for e in raw_edges:
        if not isinstance(e, dict):
            fail("AF-FUN-GRAPH-EDGE", f"an edge entry is not an object: {e!r}")
            continue
        src = str(e.get("from", "")).strip()
        dst = str(e.get("to", "")).strip()
        label = str(e.get("on", "proceed")).strip().lower()
        if src not in node_set:
            fail("AF-FUN-GRAPH-EDGE", f"edge from unknown node {src!r}")
            continue
        if dst not in node_set:
            fail("AF-FUN-GRAPH-EDGE", f"edge to unknown node {dst!r}")
            continue
        if label not in LEGAL_EDGE_LABELS:
            fail("AF-FUN-GRAPH-EDGE",
                 f"edge {src}->{dst} has illegal label {label!r} (allowed {list(LEGAL_EDGE_LABELS)})")
            continue
        adjacency[src].append((dst, label))

    # terminal + dead-end check
    if TERMINAL_NODE in node_set:
        if adjacency.get(TERMINAL_NODE):
            fail("AF-FUN-GRAPH-TERMINAL",
                 f"'{TERMINAL_NODE}' has outgoing edges — the thank-you page must be terminal")
        for nid in node_set:
            if nid != TERMINAL_NODE and not adjacency.get(nid):
                fail("AF-FUN-GRAPH-TERMINAL",
                     f"non-terminal node '{nid}' has no outgoing edge (dead end)")
    else:
        fail("AF-FUN-GRAPH-TERMINAL", f"the terminal '{TERMINAL_NODE}' node is absent")

    # one-click branch check: each upsell present must have accept AND decline
    for up in UPSELL_NODES:
        if up in node_set:
            labels = {lab for _, lab in adjacency.get(up, [])}
            for need in ("accept", "decline"):
                if need not in labels:
                    fail("AF-FUN-GRAPH-BRANCH",
                         f"upsell node '{up}' is missing its '{need}' edge (one-click branch)")

    # forward reachability from entry
    if ENTRY_NODE in node_set:
        seen: Set[str] = set()
        dq = deque([ENTRY_NODE])
        while dq:
            cur = dq.popleft()
            if cur in seen:
                continue
            seen.add(cur)
            for dst, _ in adjacency.get(cur, []):
                dq.append(dst)
        unreached = sorted(node_set - seen)
        if unreached:
            fail("AF-FUN-GRAPH-REACH", f"nodes unreachable from '{ENTRY_NODE}': {unreached}")
    else:
        fail("AF-FUN-GRAPH-REACH", f"the entry '{ENTRY_NODE}' node is absent")

    # terminal reachability: every node must be able to reach thank-you (reverse BFS)
    if TERMINAL_NODE in node_set:
        reverse: Dict[str, List[str]] = {nid: [] for nid in node_set}
        for src, outs in adjacency.items():
            for dst, _ in outs:
                reverse[dst].append(src)
        can_reach: Set[str] = set()
        dq = deque([TERMINAL_NODE])
        while dq:
            cur = dq.popleft()
            if cur in can_reach:
                continue
            can_reach.add(cur)
            for src in reverse.get(cur, []):
                dq.append(src)
        stranded = sorted(node_set - can_reach)
        if stranded:
            fail("AF-FUN-GRAPH-REACH",
                 f"nodes that cannot reach '{TERMINAL_NODE}': {stranded} — every path must terminate at thank-you")

    notes.append(f"validated {size}-step graph: {len(node_set)} nodes / {len(raw_edges)} edges "
                 f"vs MASTERDOC §3 matrix {expected_nodes}")
    return fails, notes


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------
def _load_json(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def _report(violations, notes) -> None:
    for note in notes:
        print(f"NOTE: {note}")
    if not violations:
        print("PASS: funnel step graph is valid vs MASTERDOC §3 (nodes, branching, reachability).")
        return
    print(f"FAIL: {len(violations)} funnel-graph violation(s) — P6-COMPOSE does not clear.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test fixtures — a VALID graph per size (must PASS) + violation fixtures.
# ---------------------------------------------------------------------------
def _valid_graph(size: int) -> Dict[str, Any]:
    """Build the canonical branch graph for a size straight from the matrix.
    main -> (checkout ->) upsell chain; each upsell accept jumps past its downsell,
    decline falls to it; each downsell proceeds to the next offer; last offer -> thank-you."""
    pages = funnel_pages(size)
    nodes = [{"id": p, "page_type": p} for p in pages]
    edges: List[Dict[str, str]] = []
    # linear "spine" order of offer pages (main, [checkout], upsell, [downsell], upsell-2, [downsell-2])
    spine = [p for p in pages if p != TERMINAL_NODE]

    def next_after(idx: int) -> str:
        return spine[idx + 1] if idx + 1 < len(spine) else TERMINAL_NODE

    for i, node in enumerate(spine):
        if node in UPSELL_NODES:
            downsell = "downsell" if node == "upsell" else "downsell-2"
            if downsell in pages:
                # accept jumps PAST the downsell; decline falls to the downsell
                d_idx = spine.index(downsell)
                edges.append({"from": node, "to": next_after(d_idx), "on": "accept"})
                edges.append({"from": node, "to": downsell, "on": "decline"})
            else:
                # no downsell for this upsell (e.g. 3-step / 5-step OTO2) -> both to next
                edges.append({"from": node, "to": next_after(i), "on": "accept"})
                edges.append({"from": node, "to": next_after(i), "on": "decline"})
        elif node in DOWNSELL_NODES:
            edges.append({"from": node, "to": next_after(i), "on": "proceed"})
        else:  # main / checkout
            edges.append({"from": node, "to": next_after(i), "on": "proceed"})
    return {"funnel_type": FUNNEL_TYPE, "funnel_size": size, "nodes": nodes, "edges": edges}


def _valid_derived_ledger(size: int) -> Dict[str, Any]:
    """The P8 derived-page ledger fixture (U1/D1/U2/D2/TY ids for the size)."""
    return {
        "funnel_type": FUNNEL_TYPE,
        "funnel_size": size,
        "derived_pages": [{"id": p, "label": DERIVED_LABELS[p]} for p in derived_pages(size)],
    }


def _violation_cases():
    def drop_node(g):
        g["nodes"] = [n for n in g["nodes"] if n["id"] != "upsell"]

    def bad_size(g):
        g["funnel_size"] = 4

    def ty_has_outgoing(g):
        g["edges"].append({"from": TERMINAL_NODE, "to": "main", "on": "proceed"})

    def upsell_no_decline(g):
        g["edges"] = [e for e in g["edges"] if not (e["from"] == "upsell" and e["on"] == "decline")]

    def unknown_node_edge(g):
        g["edges"].append({"from": "main", "to": "ghost-page", "on": "proceed"})

    def strand_downsell(g):
        # make downsell a non-terminal dead end (no outgoing) -> cannot reach thank-you
        g["edges"] = [e for e in g["edges"] if e["from"] != "downsell"]

    def _mk(size, fn):
        g = _valid_graph(size)
        fn(g)
        return g

    return [
        ("missing_node", "AF-FUN-GRAPH-NODES", lambda: _mk(5, drop_node)),
        ("bad_size", "AF-FUN-GRAPH-SIZE", lambda: _mk(5, bad_size)),
        ("terminal_not_terminal", "AF-FUN-GRAPH-TERMINAL", lambda: _mk(5, ty_has_outgoing)),
        ("upsell_missing_decline", "AF-FUN-GRAPH-BRANCH", lambda: _mk(5, upsell_no_decline)),
        ("edge_unknown_node", "AF-FUN-GRAPH-EDGE", lambda: _mk(5, unknown_node_edge)),
        ("downsell_dead_end", "AF-FUN-GRAPH-TERMINAL", lambda: _mk(7, strand_downsell)),
    ]


def run_self_test() -> int:
    ok = True
    for size in VALID_SIZES:
        v, _ = verify(_valid_graph(size))
        if v:
            ok = False
            print(f"SELF-TEST FAIL: valid {size}-step graph produced {len(v)} violation(s): {v}")
        else:
            print(f"SELF-TEST ok: valid {size}-step graph PASSES (0 violations).")
    cases = _violation_cases()
    caught = 0
    for name, expected, build in cases:
        vio, _ = verify(build())
        codes = {c for c, _ in vio}
        if not vio:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' produced NO violations (expected {expected}).")
        elif expected not in codes:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' -> {sorted(codes)} (expected {expected}).")
        else:
            caught += 1
            print(f"SELF-TEST ok: '{name}' -> nonzero, carries {expected}.")
    print(f"SELF-TEST FIXTURES: 3 valid-pass, {caught}/{len(cases)} violation-catch")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Fail-closed P6-COMPOSE gate: validate funnel_graph.json vs MASTERDOC §3 "
                    "(3/5/7 matrix + accept/decline branching). Exit 0 pass, 2 violation, 3 usage.")
    ap.add_argument("--graph", help="path to funnel_graph.json ('-' reads stdin)")
    ap.add_argument("graph_pos", nargs="?", help="optional positional graph path (equivalent to --graph)")
    ap.add_argument("--self-test", action="store_true",
                    help="construct a VALID graph per size (must PASS) + each VIOLATION fixture (must FAIL)")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()

    graph_path = args.graph or args.graph_pos
    if not graph_path:
        print("USAGE ERROR: pass --graph <funnel_graph.json> (or a positional path, or --self-test).")
        return EXIT_FAILCLOSED
    try:
        graph = _load_json(graph_path)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load funnel graph {graph_path!r}: {exc}")
        return EXIT_FAILCLOSED

    violations, notes = verify(graph)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
