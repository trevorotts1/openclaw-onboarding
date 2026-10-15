#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compile_launch_route.py — deterministic route compiler + validator for the
Signature Launch coordinator mode of Skill 49 (spec 06 S49-05; contracts doc 02 §5).

ONE SOURCE, THREE PRODUCTS. From one approved launch record this module derives:
  1. `route-graph.json`      — the machine route graph (route-graph.schema.json);
  2. a readable route table  — the same edges as human lines for the plan review;
  3. machine test cases      — the (stage, event, purchased) transitions the graph
                               promises, generated from the same compiled edges.

The graph hash recorded in the launch record is the SHA-256 of the exact file
bytes this compiler emits (the packet's own convention: the reference
launch-example's route_graph_hash is the SHA-256 of route-graph-example.json's
bytes). Serialization is therefore part of the contract: keys in schema order,
`json.dumps(..., indent=2)`, one trailing newline.

ROUTING LAW (doc 02 §5 — the owner's exact graph; no improvisation):
  landing -> (product_selection, only when journey_mode == multiple_options)
          -> checkout (the bump is a COMPONENT on checkout, never a node)
          -> payment_succeeded -> upsell_1 (or thank_you when U1 disabled)
  upsell_1 paid -> upsell_2 (or thank_you when U2 disabled)
  upsell_1 decline -> downsell_1 (or thank_you when D1 disabled)
  downsell_1 paid -> THE SAME canonical upsell_2 node (or thank_you)
  downsell_1 decline -> thank_you
  upsell_2 paid or decline -> thank_you
  U1 disabled REQUIRES D1 and U2 disabled. There is no second downsell.
  Pending/failed payment NEVER traverses a paid edge and is never a decline:
  it retains the current purchase state (see resolve_after).
  Checkout has NO decline edge: an abandoned initial checkout is not a route.

Deterministic, stdlib only, no network, no model. Exit 0 = ok, 2 = violation,
3 = usage / fail-closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

SCHEMA_VERSION = "1.0"
PENDING_BEHAVIOR = "retain_current_purchase_state_until_resolved_or_explicit_decline"

ROLES = ("landing", "product_selection", "checkout", "upsell_1", "downsell_1",
         "upsell_2", "thank_you")
EVENTS = ("interest_submitted", "selection_validated", "payment_succeeded",
          "explicit_decline")
PURCHASE_STAGES = ("checkout", "upsell_1", "downsell_1", "upsell_2")
SLOT_OF_STAGE = {"upsell_1": "U1", "downsell_1": "D1", "upsell_2": "U2"}
STAGE_OF_SLOT = {v: k for k, v in SLOT_OF_STAGE.items()}

# Guard vocabulary (packet route-graph-example.json). A payment_succeeded edge
# is only as trustworthy as its guard: every paid edge must name a verified_*
# guard; a decline edge must name the no-charge guard. The validator enforces it.
GUARD_MAIN_PAYMENT = "verified_main_payment"
GUARD_U1_PAYMENT = "verified_u1_payment"
GUARD_D1_PAYMENT = "verified_d1_payment"
GUARD_U2_PAYMENT = "verified_u2_payment"
GUARD_CONTACT_SUBMIT = "verified_native_contact_submit"
GUARD_SELECTION = "allowlisted_offer_price"
GUARD_NO_CHARGE_DECLINE = "no_charge_decline"


class RouteError(ValueError):
    """A launch record or graph violates the routing law (fail-closed)."""


# ---------------------------------------------------------------------------
# Compilation — launch record -> route graph.
# ---------------------------------------------------------------------------
def page_id(launch_id: str, role: str) -> str:
    return f"{launch_id}-{role.upper()}"


def _extras(launch: Dict[str, Any]) -> Tuple[bool, bool, bool]:
    ex = launch.get("extras")
    if not isinstance(ex, dict):
        raise RouteError("launch record carries no 'extras' object")
    vals = []
    for key in ("upsell_1", "downsell_1", "upsell_2"):
        v = ex.get(key)
        if type(v) is not bool:
            raise RouteError(f"extras.{key} must be a boolean, got {v!r}")
        vals.append(v)
    u1, d1, u2 = vals
    if not u1 and (d1 or u2):
        raise RouteError("U1 disabled requires D1 and U2 disabled "
                         "(this launch profile requires U1 for D1/U2 qualification)")
    return u1, d1, u2


def expected_roles(launch: Dict[str, Any]) -> List[str]:
    """The node role list, in route order, for this launch's mode + extras."""
    mode = launch.get("journey_mode")
    if mode not in ("single_simple", "multiple_options", "free_entry"):
        raise RouteError(f"journey_mode {mode!r} is not a launch mode")
    u1, d1, u2 = _extras(launch)
    roles = ["landing"]
    if mode == "multiple_options":
        roles.append("product_selection")
    roles.append("checkout")
    if u1:
        roles.append("upsell_1")
    if d1:
        roles.append("downsell_1")
    if u2:
        roles.append("upsell_2")
    roles.append("thank_you")
    return roles


def compile_route(launch: Dict[str, Any]) -> Dict[str, Any]:
    """Compile the route graph from an approved launch record. Pure + total:
    the same record always compiles to the same graph (and the same hash)."""
    for field in ("tenant_id", "location_id", "launch_id"):
        if not isinstance(launch.get(field), str) or not launch[field].strip():
            raise RouteError(f"launch record field {field!r} is missing/empty")
    revision = launch.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise RouteError(f"launch revision must be an integer >= 1, got {revision!r}")
    lid = launch["launch_id"]
    u1, d1, u2 = _extras(launch)
    roles = expected_roles(launch)

    def pid(role: str) -> str:
        return page_id(lid, role)

    def after_paid(stage: str) -> str:
        """Where a VERIFIED payment at `stage` routes (the owner's graph)."""
        if stage == "checkout":
            return pid("upsell_1") if u1 else pid("thank_you")
        if stage in ("upsell_1", "downsell_1"):
            return pid("upsell_2") if u2 else pid("thank_you")
        return pid("thank_you")  # upsell_2

    nodes = [{"page_id": pid(r), "role": r} for r in roles]
    edges: List[Dict[str, str]] = []

    def edge(frm: str, event: str, to: str, guard: str) -> None:
        edges.append({"from": frm, "event": event, "to": to, "guard": guard})

    # Entry path.
    if "product_selection" in roles:
        edge(pid("landing"), "interest_submitted", pid("product_selection"),
             GUARD_CONTACT_SUBMIT)
        edge(pid("product_selection"), "selection_validated", pid("checkout"),
             GUARD_SELECTION)
    else:
        edge(pid("landing"), "interest_submitted", pid("checkout"),
             GUARD_CONTACT_SUBMIT)

    # Checkout: a verified main payment only. NO decline edge (abandonment is
    # not a route and never reaches thank_you as a paid path).
    edge(pid("checkout"), "payment_succeeded", after_paid("checkout"),
         GUARD_MAIN_PAYMENT)

    if u1:
        edge(pid("upsell_1"), "payment_succeeded", after_paid("upsell_1"),
             GUARD_U1_PAYMENT)
        edge(pid("upsell_1"), "explicit_decline",
             pid("downsell_1") if d1 else pid("thank_you"), GUARD_NO_CHARGE_DECLINE)
    if d1:
        edge(pid("downsell_1"), "payment_succeeded", after_paid("downsell_1"),
             GUARD_D1_PAYMENT)
        edge(pid("downsell_1"), "explicit_decline", pid("thank_you"),
             GUARD_NO_CHARGE_DECLINE)
    if u2:
        edge(pid("upsell_2"), "payment_succeeded", pid("thank_you"),
             GUARD_U2_PAYMENT)
        edge(pid("upsell_2"), "explicit_decline", pid("thank_you"),
             GUARD_NO_CHARGE_DECLINE)

    return {
        "schema_version": SCHEMA_VERSION,
        "tenant_id": launch["tenant_id"],
        "location_id": launch["location_id"],
        "launch_id": lid,
        "revision": revision,
        "nodes": nodes,
        "edges": edges,
        "pending_failed_payment_behavior": PENDING_BEHAVIOR,
        "test_only": bool(launch.get("test_only", False)),
    }


# ---------------------------------------------------------------------------
# Serialization + hash — part of the contract (see module docstring).
# ---------------------------------------------------------------------------
def serialize_graph(graph: Dict[str, Any]) -> bytes:
    return (json.dumps(graph, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def graph_hash(graph: Dict[str, Any]) -> str:
    return hashlib.sha256(serialize_graph(graph)).hexdigest()


def route_table(graph: Dict[str, Any]) -> str:
    role_of = {n["page_id"]: n["role"] for n in graph.get("nodes", [])}
    lines = [f"Route table — launch {graph.get('launch_id')} rev {graph.get('revision')} "
             f"(graph hash {graph_hash(graph)[:16]}…)"]
    for e in graph.get("edges", []):
        lines.append(f"  {role_of.get(e['from'], e['from']):18s} "
                     f"--{e['event']} [{e['guard']}]--> "
                     f"{role_of.get(e['to'], e['to'])}")
    lines.append(f"  pending/failed payment: {graph.get('pending_failed_payment_behavior')}")
    lines.append("  checkout abandonment / tab close: no route (not a decline, not a sale)")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Validation — structural law + (optionally) agreement with the launch record.
# ---------------------------------------------------------------------------
def validate_graph(graph: Any, launch: Optional[Dict[str, Any]] = None) -> List[str]:
    """Return a list of violations (empty == valid). Never raises on bad input."""
    fails: List[str] = []

    def fail(msg: str) -> None:
        fails.append(msg)

    if not isinstance(graph, dict):
        return ["route graph is not a JSON object"]
    if graph.get("schema_version") != SCHEMA_VERSION:
        fail(f"schema_version is {graph.get('schema_version')!r}, expected {SCHEMA_VERSION!r}")
    if graph.get("pending_failed_payment_behavior") != PENDING_BEHAVIOR:
        fail("pending_failed_payment_behavior must be "
             f"{PENDING_BEHAVIOR!r} (pending/failed payment retains state)")
    for field in ("tenant_id", "location_id", "launch_id"):
        if not isinstance(graph.get(field), str) or not graph[field].strip():
            fail(f"graph field {field!r} is missing/empty")

    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or len(nodes) < 3:
        return fails + ["graph carries no non-empty 'nodes' array (>= 3 required)"]
    ids: List[str] = []
    roles: List[str] = []
    for n in nodes:
        if not isinstance(n, dict) or not isinstance(n.get("page_id"), str) \
                or not n["page_id"].strip():
            fail(f"a node entry is malformed: {n!r}")
            continue
        if n.get("role") not in ROLES:
            fail(f"node {n['page_id']!r} has unknown role {n.get('role')!r}")
            continue
        ids.append(n["page_id"])
        roles.append(n["role"])
    if len(set(ids)) != len(ids):
        fail("duplicate page_id (including a duplicate U2 node)")
    if len(set(roles)) != len(roles):
        fail("duplicate role (including a duplicate U2 role)")
    if roles.count("landing") != 1 or roles.count("thank_you") != 1:
        fail("exactly one landing and one thank_you node are required")
    if fails:
        return fails
    role_of = dict(zip(ids, roles))
    id_of_role = {r: i for i, r in zip(ids, roles)}

    edges = graph.get("edges")
    if not isinstance(edges, list) or not edges:
        return fails + ["graph carries no non-empty 'edges' array"]
    adjacency: Dict[str, List[str]] = {i: [] for i in ids}
    seen_pairs: Set[Tuple[str, str]] = set()
    edge_map: Dict[Tuple[str, str], str] = {}
    for e in edges:
        if not isinstance(e, dict):
            fail(f"an edge entry is not an object: {e!r}")
            continue
        frm, to, event, guard = e.get("from"), e.get("to"), e.get("event"), e.get("guard")
        if frm not in adjacency or to not in adjacency:
            fail(f"dangling edge {frm!r} -> {to!r}")
            continue
        if event not in EVENTS:
            fail(f"edge {frm}->{to} has unknown event {event!r}")
            continue
        if not isinstance(guard, str) or not guard.strip():
            fail(f"edge {frm}->{to} ({event}) names no guard")
            continue
        if (frm, event) in seen_pairs:
            fail(f"duplicate edge for ({role_of[frm]}, {event}) — routing must be deterministic")
        seen_pairs.add((frm, event))
        if event == "payment_succeeded":
            expected_guard = {"checkout": GUARD_MAIN_PAYMENT,
                              "upsell_1": GUARD_U1_PAYMENT,
                              "downsell_1": GUARD_D1_PAYMENT,
                              "upsell_2": GUARD_U2_PAYMENT}.get(role_of[frm])
            if expected_guard is not None and guard != expected_guard:
                fail(f"paid edge {role_of[frm]}->{role_of[to]} guard "
                     f"{guard!r} is not the owner's verified guard "
                     f"{expected_guard!r} — a click, a redirect, or a "
                     "near-miss guard name never proves payment")
        if role_of[frm] == "landing" and event == "interest_submitted" \
                and guard != GUARD_CONTACT_SUBMIT:
            fail(f"landing edge guard {guard!r} is not {GUARD_CONTACT_SUBMIT!r}")
        if role_of[frm] == "product_selection" \
                and event == "selection_validated" and guard != GUARD_SELECTION:
            fail(f"selection edge guard {guard!r} is not {GUARD_SELECTION!r}")
        edge_map[(role_of[frm], event)] = role_of[to]
        if event == "explicit_decline" and guard != GUARD_NO_CHARGE_DECLINE:
            fail(f"decline edge {role_of[frm]}->{role_of[to]} guard must be "
                 f"{GUARD_NO_CHARGE_DECLINE!r}")
        if role_of[frm] == "checkout" and event == "explicit_decline":
            fail("checkout carries an explicit_decline edge — abandoned initial "
                 "checkout is not a paid thank-you path")
        if role_of[frm] == "thank_you":
            fail("thank_you has an outgoing edge — it is the unique terminal")
        adjacency[frm].append(to)

    # Owner-graph target law (review D5): the graph's SHAPE is fixed by the
    # owner's route — a paid U1 or D1 routes to the ONE canonical U2 when U2
    # exists, and to thank_you only when it does not; declines follow the
    # same fixed map. Reachability alone cannot see a retargeted edge.
    def expect_target(frm_role: str, event: str, want: str) -> None:
        got = edge_map.get((frm_role, event))
        if got is not None and got != want:
            fail(f"{frm_role} --{event}--> routes to {got!r}; the owner's "
                 f"graph requires {want!r}")

    role_set = set(roles)
    expect_target("landing", "interest_submitted",
                  "product_selection" if "product_selection" in role_set
                  else "checkout")
    if "product_selection" in role_set:
        expect_target("product_selection", "selection_validated", "checkout")
    expect_target("checkout", "payment_succeeded",
                  "upsell_1" if "upsell_1" in role_set else "thank_you")
    if "upsell_1" in role_set:
        expect_target("upsell_1", "payment_succeeded",
                      "upsell_2" if "upsell_2" in role_set else "thank_you")
        expect_target("upsell_1", "explicit_decline",
                      "downsell_1" if "downsell_1" in role_set else "thank_you")
    if "downsell_1" in role_set:
        expect_target("downsell_1", "payment_succeeded",
                      "upsell_2" if "upsell_2" in role_set else "thank_you")
        expect_target("downsell_1", "explicit_decline", "thank_you")
    if "upsell_2" in role_set:
        expect_target("upsell_2", "payment_succeeded", "thank_you")
        expect_target("upsell_2", "explicit_decline", "thank_you")

    # Acyclicity + dead ends + reachability (ported law from the reference
    # contracts, extended with reverse reachability to the terminal).
    entry = id_of_role["landing"]
    terminal = id_of_role["thank_you"]
    seen: Set[str] = set()
    active: Set[str] = set()

    def visit(node: str) -> None:
        if node in active:
            fail("progression graph contains a cycle")
            return
        if node in seen:
            return
        active.add(node)
        if not adjacency[node] and node != terminal:
            fail(f"nonterminal dead end at role {role_of[node]!r}")
        for tgt in adjacency[node]:
            visit(tgt)
        active.discard(node)
        seen.add(node)

    visit(entry)
    if seen != set(ids):
        fail(f"unreachable enabled node(s): "
             f"{sorted(role_of[i] for i in set(ids) - seen)}")
    reverse: Dict[str, List[str]] = {i: [] for i in ids}
    for src, outs in adjacency.items():
        for dst in outs:
            reverse[dst].append(src)
    can_reach: Set[str] = set()
    stack = [terminal]
    while stack:
        cur = stack.pop()
        if cur in can_reach:
            continue
        can_reach.add(cur)
        stack.extend(reverse[cur])
    if can_reach != set(ids):
        fail(f"node(s) that cannot reach thank_you: "
             f"{sorted(role_of[i] for i in set(ids) - can_reach)}")

    # Owner-graph shape, independent of any launch record.
    def has_edge(frm_role: str, event: str) -> Optional[str]:
        frm = id_of_role.get(frm_role)
        if frm is None:
            return None
        for e in edges:
            if isinstance(e, dict) and e.get("from") == frm and e.get("event") == event:
                return role_of.get(e.get("to"))
        return None

    if "upsell_1" in roles:
        if has_edge("upsell_1", "payment_succeeded") not in ("upsell_2", "thank_you"):
            fail("upsell_1 paid must route to upsell_2 or thank_you")
        if has_edge("upsell_1", "explicit_decline") not in ("downsell_1", "thank_you"):
            fail("upsell_1 decline must route to downsell_1 or thank_you")
    if "downsell_1" in roles:
        if has_edge("downsell_1", "payment_succeeded") not in ("upsell_2", "thank_you"):
            fail("downsell_1 paid must route to the SAME upsell_2 or thank_you")
        if has_edge("downsell_1", "explicit_decline") != "thank_you":
            fail("downsell_1 decline must route directly to thank_you")
        if "upsell_1" not in roles:
            fail("downsell_1 present without upsell_1 (U1 disabled requires D1 disabled)")
    if "upsell_2" in roles:
        if "upsell_1" not in roles and "downsell_1" not in roles:
            fail("upsell_2 present with no upsell_1/downsell_1 path into it")
        for event in ("payment_succeeded", "explicit_decline"):
            if has_edge("upsell_2", event) != "thank_you":
                fail(f"upsell_2 {event} must route to thank_you")
    if "product_selection" in roles:
        if has_edge("landing", "interest_submitted") != "product_selection":
            fail("with a selection node, landing must route to product_selection")
        if has_edge("product_selection", "selection_validated") != "checkout":
            fail("product_selection must route to checkout on selection_validated")
    else:
        if has_edge("landing", "interest_submitted") != "checkout":
            fail("without a selection node, landing must route directly to checkout")

    # Agreement with the launch record, when supplied.
    if launch is not None:
        try:
            want_roles = expected_roles(launch)
        except RouteError as exc:
            fail(f"launch record itself is unroutable: {exc}")
        else:
            if sorted(roles) != sorted(want_roles):
                fail(f"graph roles {sorted(roles)} do not equal the roles the launch "
                     f"record compiles to {sorted(want_roles)}")
        for field in ("tenant_id", "location_id", "launch_id", "revision"):
            if graph.get(field) != launch.get(field):
                fail(f"graph {field} {graph.get(field)!r} != launch {field} "
                     f"{launch.get(field)!r}")
    return fails


# ---------------------------------------------------------------------------
# Transition resolution — the runtime law the generated test cases pin down.
# Mirrors the packet reference `resolve_after`, with purchased expressed as
# slot tokens: "MAIN" (any verified main purchase), "U1", "D1", "U2".
# ---------------------------------------------------------------------------
def resolve_after(stage: str, event: str, purchased: FrozenSet[str],
                  u1: bool, d1: bool, u2: bool,
                  payment_verified: bool = False) -> Tuple[str, FrozenSet[str]]:
    if stage not in PURCHASE_STAGES:
        raise RouteError("this resolver only models purchase-stage transitions")
    if stage != "checkout" and "MAIN" not in purchased:
        raise RouteError("a verified main purchase is required before extras")
    if stage == "upsell_1" and not u1:
        raise RouteError("U1 is disabled")
    if stage == "downsell_1" and (not d1 or "U1" in purchased):
        raise RouteError("D1 is disabled or incompatible with an accepted U1")
    if stage == "upsell_2" and (not u2 or not ({"U1", "D1"} & set(purchased))):
        raise RouteError("U2 requires enabled status and a successful U1 or D1")
    if event in ("payment_pending", "payment_failed", "requires_customer_action"):
        # NEVER a paid traversal, NEVER a decline: retain current state.
        return stage, purchased
    if event == "payment_succeeded":
        if not payment_verified:
            raise RouteError("a clicked button or redirect does not prove payment")
        if stage == "checkout":
            if "MAIN" not in purchased:
                raise RouteError("native main purchase evidence is missing at the "
                                 "moment payment success is claimed for checkout "
                                 "(the verified adapter records it atomically with "
                                 "the success event; an unrecorded claim is refused)")
            return ("upsell_1" if u1 else "thank_you"), purchased
        slot = SLOT_OF_STAGE[stage]
        updated = frozenset(set(purchased) | {slot})
        if {"U1", "D1"} <= set(updated):
            raise RouteError("U1 and D1 are mutually exclusive in this profile")
        target = "upsell_2" if stage in ("upsell_1", "downsell_1") and u2 else "thank_you"
        return target, updated
    if event == "explicit_decline":
        if stage == "checkout":
            raise RouteError("abandoned initial checkout is not a paid thank-you path")
        target = "downsell_1" if stage == "upsell_1" and d1 else "thank_you"
        return target, purchased
    raise RouteError("unknown event; do not infer a decline or success")


def generate_test_cases(launch: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Machine test cases generated from the SAME compilation as the graph:
    every promised transition, plus the negative law (pending/failed retention,
    unverified payment, checkout decline, U1/D1 exclusivity, U2 qualification)."""
    u1, d1, u2 = _extras(launch)
    cases: List[Dict[str, Any]] = []

    def ok(name: str, stage: str, event: str, before: Set[str], verified: bool,
           to: str, after: Set[str]) -> None:
        cases.append({"name": name, "stage": stage, "event": event,
                      "purchased_before": sorted(before),
                      "payment_verified": verified,
                      "expect": {"to": to, "purchased_after": sorted(after)}})

    def err(name: str, stage: str, event: str, before: Set[str], verified: bool) -> None:
        cases.append({"name": name, "stage": stage, "event": event,
                      "purchased_before": sorted(before),
                      "payment_verified": verified,
                      "expect": {"error": True}})

    main = {"MAIN"}
    # Checkout law.
    ok("checkout_paid_routes_onward", "checkout", "payment_succeeded", main, True,
       "upsell_1" if u1 else "thank_you", main)
    err("checkout_paid_without_main_evidence", "checkout", "payment_succeeded",
        set(), True)
    err("checkout_unverified_success_claim", "checkout", "payment_succeeded",
        main, False)
    err("checkout_decline_is_not_a_route", "checkout", "explicit_decline", main, False)
    for ev in ("payment_pending", "payment_failed", "requires_customer_action"):
        ok(f"checkout_{ev}_retains_state", "checkout", ev, main, False,
           "checkout", main)
    if u1:
        ok("u1_paid", "upsell_1", "payment_succeeded", main, True,
           "upsell_2" if u2 else "thank_you", main | {"U1"})
        err("u1_unverified_success_claim", "upsell_1", "payment_succeeded", main, False)
        ok("u1_pending_retains_state", "upsell_1", "payment_pending", main, False,
           "upsell_1", main)
        if d1:
            ok("u1_decline_to_d1", "upsell_1", "explicit_decline", main, False,
               "downsell_1", main)
            ok("d1_paid", "downsell_1", "payment_succeeded", main, True,
               "upsell_2" if u2 else "thank_you", main | {"D1"})
            ok("d1_decline_to_thank_you", "downsell_1", "explicit_decline", main,
               False, "thank_you", main)
            err("d1_after_u1_accepted_is_refused", "downsell_1", "payment_succeeded",
                main | {"U1"}, True)
        else:
            ok("u1_decline_to_thank_you_when_d1_disabled", "upsell_1",
               "explicit_decline", main, False, "thank_you", main)
    if u2:
        for via in (("U1",) if u1 else ()) + (("D1",) if d1 else ()):
            ok(f"u2_paid_via_{via.lower()}", "upsell_2", "payment_succeeded",
               main | {via}, True, "thank_you", main | {via, "U2"})
            ok(f"u2_decline_via_{via.lower()}", "upsell_2", "explicit_decline",
               main | {via}, False, "thank_you", main | {via})
        err("u2_without_u1_or_d1_is_refused", "upsell_2", "payment_succeeded",
            main, True)
    if u1:
        # An extra stage may not even HOLD state before a verified main
        # purchase — the resolver refuses the stage outright.
        err("u1_without_main_purchase", "upsell_1", "payment_pending", set(), False)
    return cases


def run_test_cases(cases: List[Dict[str, Any]], u1: bool, d1: bool,
                   u2: bool) -> List[str]:
    """Execute generated cases against resolve_after. Empty list == all pass."""
    failures: List[str] = []
    for c in cases:
        try:
            to, after = resolve_after(c["stage"], c["event"],
                                      frozenset(c["purchased_before"]), u1, d1, u2,
                                      payment_verified=c["payment_verified"])
            got: Dict[str, Any] = {"to": to, "purchased_after": sorted(after)}
        except RouteError:
            got = {"error": True}
        if got != c["expect"]:
            failures.append(f"case {c['name']}: expected {c['expect']}, got {got}")
    return failures


# ---------------------------------------------------------------------------
# IO + CLI.
# ---------------------------------------------------------------------------
def _load_json(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _self_test() -> int:
    ok = True

    def say(good: bool, msg: str) -> None:
        nonlocal ok
        ok = ok and good
        print(f"SELF-TEST {'ok' if good else 'FAIL'}: {msg}")

    base = {"tenant_id": "T", "location_id": "L", "launch_id": "TEST-LAUNCH",
            "revision": 1, "journey_mode": "multiple_options", "test_only": True}

    # Full profile == the packet's route-graph-example shape.
    full = dict(base, extras={"upsell_1": True, "downsell_1": True, "upsell_2": True})
    g = compile_route(full)
    say([n["role"] for n in g["nodes"]] ==
        ["landing", "product_selection", "checkout", "upsell_1", "downsell_1",
         "upsell_2", "thank_you"], "full profile compiles the 7 example roles in order")
    say(g["nodes"][1]["page_id"] == "TEST-LAUNCH-PRODUCT_SELECTION" and
        g["nodes"][5]["page_id"] == "TEST-LAUNCH-UPSELL_2",
        "page_id convention is launch_id-ROLE (schema leaves page_id free; the "
        "packet's hand-authored example uses a shorter TEST- prefix — graphs "
        "compare equal modulo that prefix)")
    say(validate_graph(g, full) == [], "compiled full graph validates clean")
    say(compile_route(full) == g and graph_hash(compile_route(full)) == graph_hash(g),
        "compilation is deterministic (same record -> same graph, same hash)")

    # single_simple: no selection node, no extras.
    simple = dict(base, journey_mode="single_simple",
                  extras={"upsell_1": False, "downsell_1": False, "upsell_2": False})
    gs = compile_route(simple)
    say([n["role"] for n in gs["nodes"]] == ["landing", "checkout", "thank_you"],
        "single_simple compiles with NO selection node and no extras")
    say(validate_graph(gs, simple) == [], "single_simple graph validates clean")

    # free_entry with U1 only.
    free = dict(base, journey_mode="free_entry",
                extras={"upsell_1": True, "downsell_1": False, "upsell_2": False})
    gf = compile_route(free)
    say([n["role"] for n in gf["nodes"]] ==
        ["landing", "checkout", "upsell_1", "thank_you"],
        "free_entry U1-only graph has no selection/D1/U2 nodes")
    say(validate_graph(gf, free) == [], "free_entry graph validates clean")

    # U2 disabled: D1 paid goes straight to thank_you.
    nou2 = dict(base, extras={"upsell_1": True, "downsell_1": True, "upsell_2": False})
    gn = compile_route(nou2)
    d1_paid = [e for e in gn["edges"] if e["from"].endswith("DOWNSELL_1")
               and e["event"] == "payment_succeeded"]
    say(len(d1_paid) == 1 and d1_paid[0]["to"].endswith("THANK_YOU"),
        "U2 disabled: D1 paid routes straight to thank_you")
    say(validate_graph(gn, nou2) == [], "U2-disabled graph validates clean")

    # Illegal extras are refused at compile time.
    try:
        compile_route(dict(base, extras={"upsell_1": False, "downsell_1": True,
                                         "upsell_2": False}))
        say(False, "U1 disabled + D1 enabled must refuse compilation")
    except RouteError:
        say(True, "U1 disabled + D1 enabled refuses compilation")

    # Validator catches the classic corruptions.
    import copy as _c
    bad = _c.deepcopy(g)
    bad["nodes"].append({"page_id": "TEST-LAUNCH-UPSELL_2B", "role": "upsell_2"})
    say(any("duplicate" in v for v in validate_graph(bad)),
        "validator catches a duplicate U2")
    bad = _c.deepcopy(g)
    bad["edges"] = [e for e in bad["edges"]
                    if not (e["from"].endswith("DOWNSELL_1")
                            and e["event"] == "explicit_decline")]
    say(validate_graph(bad) != [], "validator catches a missing D1 decline edge")
    bad = _c.deepcopy(g)
    for e in bad["edges"]:
        if e["event"] == "payment_succeeded":
            e["guard"] = "button_clicked"
    say(any("verified_" in v for v in validate_graph(bad)),
        "validator catches an unverified paid-edge guard")
    bad = _c.deepcopy(g)
    bad["edges"].append({"from": g["nodes"][2]["page_id"], "event": "explicit_decline",
                         "to": g["nodes"][-1]["page_id"],
                         "guard": GUARD_NO_CHARGE_DECLINE})
    say(any("checkout" in v for v in validate_graph(bad)),
        "validator catches a checkout decline edge")
    # Review probe G2 (D5): retargeted paid edges and near-miss guards.
    bad = _c.deepcopy(g)
    for e in bad["edges"]:
        if e["from"].endswith("UPSELL_1") and e["event"] == "payment_succeeded":
            e["to"] = g["nodes"][-1]["page_id"]
        if e["from"].endswith("DOWNSELL_1") and e["event"] == "payment_succeeded":
            e["to"] = g["nodes"][-1]["page_id"]
    say(any("owner's graph requires" in v for v in validate_graph(bad)),
        "validator catches U1/D1 paid edges retargeted away from the "
        "canonical U2 (D5)")
    bad = _c.deepcopy(g)
    for e in bad["edges"]:
        if e["from"].endswith("UPSELL_1") and e["event"] == "payment_succeeded":
            e["guard"] = "verified_banana"
    say(any("verified_u1_payment" in v for v in validate_graph(bad)),
        "validator catches a near-miss paid guard name (D5)")

    # Generated machine test cases all pass against the resolver, per profile.
    for label, launch in (("full", full), ("simple", simple), ("free", free),
                          ("nou2", nou2)):
        u1x, d1x, u2x = _extras(launch)
        cases = generate_test_cases(launch)
        fails = run_test_cases(cases, u1x, d1x, u2x)
        say(not fails, f"generated test cases pass for profile {label} "
                       f"({len(cases)} cases)" + (f": {fails}" if fails else ""))

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Deterministic Signature Launch route compiler + validator. "
                    "Exit 0 ok, 2 violation, 3 usage/fail-closed.")
    ap.add_argument("--launch", help="path to the launch record JSON")
    ap.add_argument("--graph", help="path to a route graph JSON to validate")
    ap.add_argument("--out", help="write the compiled route-graph.json here")
    ap.add_argument("--table-out", help="write the readable route table here")
    ap.add_argument("--cases-out", help="write the generated machine test cases here")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.launch and not args.graph:
        print("USAGE ERROR: pass --launch and/or --graph (or --self-test).")
        return EXIT_FAILCLOSED
    try:
        launch = _load_json(args.launch) if args.launch else None
        graph = _load_json(args.graph) if args.graph else None
    except (OSError, ValueError) as exc:
        print(f"USAGE/IO ERROR: cannot load input: {exc}")
        return EXIT_FAILCLOSED

    if launch is not None:
        try:
            compiled = compile_route(launch)
        except RouteError as exc:
            print(f"FAIL: launch record is unroutable: {exc}")
            return EXIT_VIOLATION
        if graph is None:
            graph = compiled
        if args.out:
            Path(args.out).write_bytes(serialize_graph(compiled))
            print(f"wrote {args.out} (graph hash {graph_hash(compiled)})")
        if args.table_out:
            Path(args.table_out).write_text(route_table(compiled), encoding="utf-8")
            print(f"wrote {args.table_out}")
        if args.cases_out:
            Path(args.cases_out).write_text(
                json.dumps(generate_test_cases(launch), indent=2) + "\n",
                encoding="utf-8")
            print(f"wrote {args.cases_out}")

    fails = validate_graph(graph, launch)
    if fails:
        print(f"FAIL: {len(fails)} route violation(s):")
        for f in fails:
            print(f"  - {f}")
        return EXIT_VIOLATION
    print(f"PASS: route graph valid ({len(graph['nodes'])} nodes, "
          f"{len(graph['edges'])} edges, hash {graph_hash(graph)}).")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
