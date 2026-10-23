"""49 page-set/route adapters and repeated role instances over the delivery schema contract.

Unit W1B-U1 (GHL-DELIVERY-SPEC.md, stream W1). One job: adapt Skill 49's page
sets and funnel routes onto the W1 delivery schema contract record shape
(GHL-DELIVERY-SPEC.md, "Delivery contract (W1 owns the normative versioned
schema)") — stable logical IDs, actual page nodes (never a fixed role-slot
count), funnel ordering plus explicit accept/decline/submit/success/error
edges, states PLANNED -> CREATED -> CONFIGURED -> PUBLISHED -> VERIFIED.

Presets: the Signature 3/5/7 funnel presets live ONLY in this adapter layer,
as data (PRESET_MATRIX) plus the canonical branching law (preset_graph). A
delivery that brings its own page set is adapted unchanged — a preset is
never imposed on it.

Repeated role instances: pages may share one page_role with distinct identity
(funnel_structure.json page_role_map: page_type "downsell-2" is page_role
"downsell_1" with role_instance "downsell_2"). Logical IDs are allocated per
page node, not per role, so any number of instances of one role is legal.

PROVISIONAL (W1B): the upstream contract module
``shared-utils/delivery/npage_contract.py`` (W1A) does not exist yet. The
integration seam is load_npage_contract(); until the module lands, node/edge
records are built and validated against the local mirror of the normative
contract fields (validate_delivery). INTEGRATION_OUTSTANDING records exactly
what remains.

Provenance of the embedded 49 vocabulary (copied as adapter data; the skill
tree is not a runtime dependency, and the self-check re-proves equality with
the skill file when it is present beside shared-utils/):
  * PRESET_MATRIX      49-signature-funnel/structure/funnel_structure.json
                       funnel_matrix (MASTERDOC.md section 3)
  * PAGE_ROLE_MAP      the same file, page_role_map (Fix 15: ONE page_type ->
                       page_role table)
  * preset_graph       the branching law of 49-signature-funnel/scripts/
                       prove_sf_graph.py _valid_graph: "each upsell accept
                       jumps past its downsell, decline falls to it; each
                       downsell proceeds to the next offer; last offer ->
                       thank-you" (MASTERDOC section 3 Branching).
  * PENDING_BEHAVIOR   49-signature-funnel/scripts/compile_launch_route.py.

Deterministic, stdlib only, no network, no model. Never reads a secret.
Run the self-check: ``python3 -I shared-utils/signature_launch/route_adapters.py``
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "ghl-delivery-route-adapters/v0"

# --- delivery schema contract (GHL-DELIVERY-SPEC.md "Delivery contract") ---
STATES = ("PLANNED", "CREATED", "CONFIGURED", "PUBLISHED", "VERIFIED")
CONTRACT_EDGE_KINDS = ("accept", "decline", "submit", "success", "error")
DESIRED_STATES = ("draft", "published")
PENDING_BEHAVIOR = "retain_current_purchase_state_until_resolved_or_explicit_decline"

# --- 49 vocabulary (funnel_structure.json page_role_map / funnel_matrix) ---
PAGE_ROLES = ("landing", "product_selection", "checkout", "upsell_1",
              "downsell_1", "upsell_2", "thank_you")

# page_type -> (page_role, role_instance or None). The only page_type ->
# page_role table (Fix 15); downsell-2 is a REPEATED ROLE INSTANCE of
# downsell_1, not a ninth role.
PAGE_ROLE_MAP = {
    "main": ("landing", None),
    "product_selection": ("product_selection", None),
    "checkout": ("checkout", None),
    "upsell": ("upsell_1", None),
    "downsell": ("downsell_1", None),
    "upsell-2": ("upsell_2", None),
    "downsell-2": ("downsell_1", "downsell_2"),
    "thank-you": ("thank_you", None),
}

# Signature 3/5/7 presets — adapter data only, never imposed.
PRESET_MATRIX = {
    "3": ["main", "upsell", "thank-you"],
    "5": ["main", "upsell", "downsell", "upsell-2", "thank-you"],
    "7": ["main", "checkout", "upsell", "downsell", "upsell-2", "downsell-2",
          "thank-you"],
}

INTENT = {
    "landing": "hero_and_order_capture",
    "product_selection": "offer_selection",
    "checkout": "order_page_design_only_native_form",
    "upsell_1": "oto_offer",
    "upsell_2": "oto_offer",
    "downsell_1": "downsell_offer",
    "thank_you": "confirmation_no_pitch",
}

# Edge-kind adaptation: 49 label vocabularies -> contract edge kinds.
# "proceed" resolves by the SOURCE page's role family: the landing/selection
# submission carries to checkout (submit); the one payment capture is at
# checkout and every offer-page continuation resolves that purchase state
# (MASTERDOC section 3: "payment captured once at the order form"), so
# checkout and downsell continuations are success edges.
LABEL_KIND = {"accept": "accept", "decline": "decline"}
EVENT_KIND = {"interest_submitted": "submit", "selection_validated": "submit",
              "payment_succeeded": "success", "explicit_decline": "decline"}
PROCEED_KIND_BY_ROLE = {"landing": "submit", "product_selection": "submit",
                        "checkout": "success", "downsell_1": "success"}
PAYMENT_ROLES = ("checkout", "upsell_1", "upsell_2", "downsell_1")
TERMINAL_ROLE = "thank_you"

# Required contract record fields on every page node (spec: location, builder
# type, intent, revision, approvals, folder/container/page identities,
# name/slug, approved content, native components, product/price references,
# desired draft/publication state).
NODE_FIELDS = ("logical_id", "node_id", "page_type", "page_role",
               "role_instance", "location", "builder_type", "intent",
               "revision", "approvals", "folder_identity", "container_identity",
               "page_identity", "name", "slug", "approved_content",
               "native_components", "product_price_refs", "desired_state",
               "state", "order")

INTEGRATION_OUTSTANDING = [
    "Bind node/edge construction to shared-utils/delivery/npage_contract.py "
    "(W1A) when it lands; until then the GHL-DELIVERY-SPEC.md delivery-contract "
    "record shape is built and validated by this module's local mirror. "
    "load_npage_contract() is the seam; when the module exposes "
    "validate_page_node/validate_delivery they run on every record here.",
    "State progression beyond PLANNED (CREATED/CONFIGURED/PUBLISHED/VERIFIED) "
    "is emitted by the execution streams (W4 checkpoints, W5 primitives, W7 "
    "publishing); this adapter only allocates identities and routes.",
    "folder_identity/container_identity/page_identity and approved_content "
    "stay None until W5/W9 allocate and fill them; product_price_refs stay "
    "empty until W8 binds products/prices to native checkout components.",
]


class RouteAdapterError(ValueError):
    """A page set, route or contract record this adapter refuses to carry."""


# --------------------------------------------------------------------------
# Contract seam (PROVISIONAL): shared-utils/delivery/npage_contract.py (W1A)
# --------------------------------------------------------------------------

def npage_contract_path() -> Path:
    """Where the upstream contract module is expected (shared-utils/delivery/)."""
    return Path(__file__).resolve().parents[1] / "delivery" / "npage_contract.py"


def load_npage_contract():
    """The W1A contract module, or None while it does not exist (provisional)."""
    path = npage_contract_path()
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("npage_contract", path)
    if spec is None or spec.loader is None:
        raise RouteAdapterError(f"cannot load contract module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contract_status() -> Dict[str, Any]:
    """Honest seam status: which contract authority validates records today."""
    module = load_npage_contract()
    source = ("npage_contract" if module is not None
              else "GHL-DELIVERY-SPEC.md delivery-contract local mirror")
    return {"npage_contract_present": module is not None,
            "npage_contract_path": str(npage_contract_path()),
            "contract_source": source,
            "outstanding_integration": list(INTEGRATION_OUTSTANDING)}


# --------------------------------------------------------------------------
# Page nodes and logical IDs
# --------------------------------------------------------------------------

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _name(page_type: str) -> str:
    return page_type.replace("-", " ").title()


def _logical_id(node_id: str) -> str:
    """Stable logical ID per PAGE NODE — never per role, never a slot count."""
    return "pg-" + _slug(node_id)


def new_page_node(node_id: str, page_type: str, page_role: str,
                  role_instance: Optional[str], order: int, *,
                  location: str, builder_type: str = "funnel",
                  desired_state: str = "draft") -> Dict[str, Any]:
    """One delivery-contract page node at PLANNED (identities allocated first)."""
    if page_role not in PAGE_ROLES:
        raise RouteAdapterError(f"page_role {page_role!r} is not one of {list(PAGE_ROLES)}")
    if desired_state not in DESIRED_STATES:
        raise RouteAdapterError(f"desired_state {desired_state!r} is not one of {DESIRED_STATES}")
    node = {
        "logical_id": _logical_id(node_id),
        "node_id": node_id,
        "page_type": page_type,
        "page_role": page_role,
        "role_instance": role_instance,
        "location": location,
        "builder_type": builder_type,
        "intent": INTENT[page_role],
        "revision": 0,
        "approvals": [],
        "folder_identity": None,
        "container_identity": None,
        "page_identity": None,
        "name": _name(page_type),
        "slug": _slug(page_type),
        "approved_content": None,
        "native_components": [],
        "product_price_refs": [],
        "desired_state": desired_state,
        "state": STATES[0],
        "order": order,
    }
    return node


def validate_page_node(node: Dict[str, Any]) -> None:
    """Local mirror of the contract record rules; raises RouteAdapterError."""
    missing = [k for k in NODE_FIELDS if k not in node]
    if missing:
        raise RouteAdapterError(f"page node missing contract fields {missing}: {node!r}")
    if node["state"] not in STATES:
        raise RouteAdapterError(f"page node state {node['state']!r} is not one of {STATES}")
    if node["desired_state"] not in DESIRED_STATES:
        raise RouteAdapterError(f"page node desired_state {node['desired_state']!r} is not one of {DESIRED_STATES}")
    if node["page_role"] not in PAGE_ROLES:
        raise RouteAdapterError(f"page node role {node['page_role']!r} is not one of {list(PAGE_ROLES)}")
    if not isinstance(node["revision"], int) or node["revision"] < 0:
        raise RouteAdapterError(f"page node revision must be an int >= 0: {node['revision']!r}")
    if not isinstance(node["approvals"], list):
        raise RouteAdapterError("page node approvals must be a list")


# --------------------------------------------------------------------------
# Preset layer: the Signature 3/5/7 presets, through adapters only
# --------------------------------------------------------------------------

def preset_page_set(size: int) -> List[Dict[str, Any]]:
    """The canonical page set for a Signature preset (3, 5 or 7)."""
    entries = PRESET_MATRIX.get(str(size))
    if entries is None:
        raise RouteAdapterError(f"Signature preset {size!r} is not one of {sorted(PRESET_MATRIX)}")
    out = []
    for order, page_type in enumerate(entries):
        role, instance = PAGE_ROLE_MAP[page_type]
        out.append({"id": page_type, "page_type": page_type, "page_role": role,
                    "role_instance": instance, "order": order})
    return out


def preset_graph(size: int) -> Dict[str, Any]:
    """The canonical branch graph for a preset, from the matrix.

    Mirrors 49-signature-funnel/scripts/prove_sf_graph.py _valid_graph:
    "main -> (checkout ->) upsell chain; each upsell accept jumps past its
    downsell, decline falls to it; each downsell proceeds to the next offer;
    last offer -> thank-you."
    """
    entries = preset_page_set(size)
    node_ids = [e["id"] for e in entries]
    spine = [n for n in node_ids if n != "thank-you"]
    updown = {"upsell": "downsell", "upsell-2": "downsell-2"}
    edges: List[Dict[str, str]] = []

    def next_after(idx: int) -> str:
        return spine[idx + 1] if idx + 1 < len(spine) else "thank-you"

    for i, node in enumerate(spine):
        if node in updown:
            downsell = updown[node]
            if downsell in node_ids:
                d_idx = spine.index(downsell)
                edges.append({"from": node, "to": next_after(d_idx), "on": "accept"})
                edges.append({"from": node, "to": downsell, "on": "decline"})
            else:
                edges.append({"from": node, "to": next_after(i), "on": "accept"})
                edges.append({"from": node, "to": next_after(i), "on": "decline"})
        else:  # main / checkout / downsell
            edges.append({"from": node, "to": next_after(i), "on": "proceed"})
    return {"nodes": entries, "edges": edges}


def preset_route_adapters(size: int, *, location: str,
                          builder_type: str = "funnel",
                          desired_state: str = "draft") -> Dict[str, Any]:
    """Adapt one Signature preset (3/5/7) into the delivery schema contract."""
    graph = preset_graph(size)
    return adapt_page_set(graph["nodes"], graph["edges"], location=location,
                          builder_type=builder_type, desired_state=desired_state,
                          preset=int(size))


# --------------------------------------------------------------------------
# Adapter layer: any page set (with repeated role instances) -> contract doc
# --------------------------------------------------------------------------

def _edge_kind(edge: Dict[str, Any], role_of: Dict[str, str]) -> str:
    """Map one 49 edge vocabulary entry to a contract edge kind."""
    if "kind" in edge:
        kind = edge["kind"]
        if kind not in CONTRACT_EDGE_KINDS:
            raise RouteAdapterError(f"edge kind {kind!r} is not one of {CONTRACT_EDGE_KINDS}")
        return kind
    src_role = role_of[edge["from"]]
    if "on" in edge:
        label = edge["on"]
        if label in LABEL_KIND:
            return LABEL_KIND[label]
        if label == "proceed":
            if src_role not in PROCEED_KIND_BY_ROLE:
                raise RouteAdapterError(
                    f"no documented proceed semantics for role {src_role!r}; refusing to improvise")
            return PROCEED_KIND_BY_ROLE[src_role]
        raise RouteAdapterError(f"edge label {label!r} is not a 49 label")
    if "event" in edge:
        event = edge["event"]
        if event not in EVENT_KIND:
            raise RouteAdapterError(f"edge event {event!r} is not a 49 coordinator event")
        return EVENT_KIND[event]
    raise RouteAdapterError(f"edge carries none of kind/on/event: {edge!r}")


def adapt_page_set(entries: List[Dict[str, Any]], edges: List[Dict[str, Any]], *,
                   location: str, builder_type: str = "funnel",
                   desired_state: str = "draft",
                   preset: Optional[int] = None) -> Dict[str, Any]:
    """Adapt one page set + route list into the delivery schema contract doc.

    ``entries``: [{"id", "page_type", "page_role", "role_instance"?}, ...] in
    funnel order — any count of repeated role instances, each with its own id.
    ``edges``: 49 route edges {"from","to","on"|"event"|"kind"} between entry
    ids. ``preset`` records which Signature preset (3/5/7) the set came from;
    None means the set is the caller's own and NO preset is imposed.
    """
    if preset is not None and preset not in (3, 5, 7):
        raise RouteAdapterError(f"preset {preset!r} is not one of 3, 5, 7")
    nodes: List[Dict[str, Any]] = []
    role_of: Dict[str, str] = {}
    for order, entry in enumerate(entries):
        for key in ("id", "page_type", "page_role"):
            if key not in entry:
                raise RouteAdapterError(f"page set entry missing {key!r}: {entry!r}")
        node_id = entry["id"]
        if node_id in role_of:
            raise RouteAdapterError(f"duplicate page node id {node_id!r}; "
                                    f"repeated role instances need distinct ids")
        role_of[node_id] = entry["page_role"]
        nodes.append(new_page_node(
            node_id, entry["page_type"], entry["page_role"],
            entry.get("role_instance"), order,
            location=location, builder_type=builder_type,
            desired_state=desired_state))

    logical_of = {n["node_id"]: n["logical_id"] for n in nodes}
    out_edges: List[Dict[str, Any]] = []
    for edge in edges:
        for key in ("from", "to"):
            if edge.get(key) not in logical_of:
                raise RouteAdapterError(f"edge endpoint {edge.get(key)!r} is not a page node: {edge!r}")
        kind = _edge_kind(edge, role_of)
        src_role = role_of[edge["from"]]
        if kind == "decline" and src_role == "checkout":
            raise RouteAdapterError("checkout has no decline edge (abandonment is not a route)")
        out_edges.append({"from": logical_of[edge["from"]], "to": logical_of[edge["to"]],
                          "kind": kind, "source_label": edge.get("on", edge.get("event", kind))})
    # Explicit error edges on payment-touching pages: a pending/failed payment
    # never traverses a paid edge and is never a decline — it retains the
    # current purchase state (compile_launch_route.py PENDING_BEHAVIOR).
    for n in nodes:
        if n["page_role"] in PAYMENT_ROLES:
            out_edges.append({"from": n["logical_id"], "to": n["logical_id"],
                              "kind": "error", "source_label": "error",
                              "policy": PENDING_BEHAVIOR})

    doc = {
        "schema": SCHEMA,
        "contract_source": contract_status()["contract_source"],
        "location": location,
        "builder_type": builder_type,
        "preset": preset,
        "pages": nodes,
        "edges": out_edges,
        "ordering": [n["logical_id"] for n in nodes],
        "states": list(STATES),
        "outstanding_integration": list(INTEGRATION_OUTSTANDING),
    }
    validate_delivery(doc)
    return doc


def adapt_route_graph(graph: Dict[str, Any], *, location: str, **kw: Any) -> Dict[str, Any]:
    """Adapt a 49 route graph {"nodes","edges"} (preset or caller's own)."""
    return adapt_page_set(graph["nodes"], graph["edges"], location=location, **kw)


def validate_delivery(doc: Dict[str, Any]) -> None:
    """Contract-record validation over the whole doc (local mirror, W1A seam)."""
    if doc.get("schema") != SCHEMA:
        raise RouteAdapterError(f"not a {SCHEMA} document")
    pages = doc.get("pages")
    if not isinstance(pages, list) or not pages:
        raise RouteAdapterError("delivery doc carries no pages")
    seen = set()
    for node in pages:
        validate_page_node(node)
        if node["logical_id"] in seen:
            raise RouteAdapterError(f"duplicate logical_id {node['logical_id']!r}")
        seen.add(node["logical_id"])
    if doc.get("ordering") != [n["logical_id"] for n in pages]:
        raise RouteAdapterError("ordering does not match page node order")
    for edge in doc.get("edges", []):
        if edge.get("kind") not in CONTRACT_EDGE_KINDS:
            raise RouteAdapterError(f"edge kind {edge.get('kind')!r} is not one of {CONTRACT_EDGE_KINDS}")
        for key in ("from", "to"):
            if edge.get(key) not in seen:
                raise RouteAdapterError(f"edge endpoint {edge.get(key)!r} is not a page node: {edge!r}")
    role_of = {n["logical_id"]: n["page_role"] for n in pages}
    for edge in doc["edges"]:
        if edge["kind"] == "decline" and role_of[edge["from"]] == "checkout":
            raise RouteAdapterError("checkout has no decline edge (abandonment is not a route)")
        if role_of[edge["from"]] == TERMINAL_ROLE and edge["kind"] != "error":
            raise RouteAdapterError("the thank-you page must be terminal")
    # duck-typed W1A validation when the contract module is present
    module = load_npage_contract()
    if module is not None:
        check = getattr(module, "validate_page_node", None)
        if callable(check):
            for node in pages:
                check(node)


# --------------------------------------------------------------------------
# Self-check (assert-based; run with python3 -I)
# --------------------------------------------------------------------------

_TALLY = 0


def _ck(cond: Any, label: str) -> None:
    global _TALLY
    assert cond, f"self-check failed: {label}"
    _TALLY += 1


def _edges_by_source(doc: Dict[str, Any], logical_id: str) -> List[Dict[str, Any]]:
    return [e for e in doc["edges"] if e["from"] == logical_id and e["kind"] != "error"]


def _self_check() -> None:
    # -- presets expand to the exact matrix, order preserved -----------------
    for size, expected in PRESET_MATRIX.items():
        got = [e["page_type"] for e in preset_page_set(int(size))]
        _ck(got == expected, f"preset {size} page set matches funnel_matrix")

    # -- repeated role instance mapping (Fix 15) -----------------------------
    e7 = {e["page_type"]: e for e in preset_page_set(7)}
    _ck(e7["downsell-2"]["page_role"] == "downsell_1", "downsell-2 maps to role downsell_1")
    _ck(e7["downsell-2"]["role_instance"] == "downsell_2", "downsell-2 carries role_instance downsell_2")
    _ck(e7["upsell-2"]["page_role"] == "upsell_2", "upsell-2 is its own role")

    # -- preset 3 routing ----------------------------------------------------
    d3 = preset_route_adapters(3, location="ghl-test")
    li = {n["node_id"]: n["logical_id"] for n in d3["pages"]}
    _ck(d3["preset"] == 3, "preset recorded on the doc")
    _ck(d3["pages"][0]["node_id"] == "main", "preset 3 starts at main")
    m3 = _edges_by_source(d3, li["main"])
    _ck(m3 == [{"from": li["main"], "to": li["upsell"], "kind": "submit", "source_label": "proceed"}],
        "main proceeds to upsell as submit")
    u3 = _edges_by_source(d3, li["upsell"])
    _ck({(e["kind"], e["to"]) for e in u3} == {("accept", li["thank-you"]), ("decline", li["thank-you"])},
        "preset 3 upsell accept+decline both reach thank-you")

    # -- preset 5: accept jumps past the downsell, decline falls to it -------
    d5 = preset_route_adapters(5, location="ghl-test")
    li = {n["node_id"]: n["logical_id"] for n in d5["pages"]}
    u1 = {e["kind"]: e["to"] for e in _edges_by_source(d5, li["upsell"])}
    _ck(u1["accept"] == li["upsell-2"], "upsell accept jumps past downsell to upsell-2")
    _ck(u1["decline"] == li["downsell"], "upsell decline falls through to downsell")
    dn = _edges_by_source(d5, li["downsell"])
    _ck(dn[0]["to"] == li["upsell-2"] and dn[0]["kind"] == "success",
        "downsell proceeds to the next offer (success)")
    u2 = {e["kind"]: e["to"] for e in _edges_by_source(d5, li["upsell-2"])}
    _ck(u2["accept"] == li["thank-you"] and u2["decline"] == li["thank-you"],
        "preset 5 upsell-2 (no downsell-2) both ways to thank-you")

    # -- preset 7: the full chain with the repeated downsell instance --------
    d7 = preset_route_adapters(7, location="ghl-test")
    li = {n["node_id"]: n["logical_id"] for n in d7["pages"]}
    co = _edges_by_source(d7, li["checkout"])
    _ck(co == [{"from": li["checkout"], "to": li["upsell"], "kind": "success", "source_label": "proceed"}],
        "checkout continues on success (payment captured at the order form)")
    u2 = {e["kind"]: e["to"] for e in _edges_by_source(d7, li["upsell-2"])}
    _ck(u2["accept"] == li["thank-you"], "upsell-2 accept jumps past downsell-2 to thank-you")
    _ck(u2["decline"] == li["downsell-2"], "upsell-2 decline falls through to downsell-2")
    d2 = _edges_by_source(d7, li["downsell-2"])
    _ck(d2[0]["to"] == li["thank-you"], "downsell-2 proceeds to thank-you (last offer)")
    _ck(_edges_by_source(d7, li["thank-you"]) == [], "thank-you is terminal")

    # -- distinct identity for pages sharing a role --------------------------
    dn1 = next(n for n in d7["pages"] if n["node_id"] == "downsell")
    dn2 = next(n for n in d7["pages"] if n["node_id"] == "downsell-2")
    _ck(dn1["page_role"] == dn2["page_role"] == "downsell_1", "both downsells share the role")
    _ck(dn1["logical_id"] != dn2["logical_id"], "shared role, distinct logical IDs")
    _ck(len({n["logical_id"] for n in d7["pages"]}) == len(d7["pages"]), "logical IDs unique")
    _ck(d7["ordering"] == [n["logical_id"] for n in d7["pages"]], "ordering matches page order")

    # -- no dead ends on presets --------------------------------------------
    for doc in (d3, d5, d7):
        for n in doc["pages"]:
            if n["page_role"] != TERMINAL_ROLE:
                _ck(_edges_by_source(doc, n["logical_id"]), f"{n['node_id']} has an outgoing edge")

    # -- contract record shape ----------------------------------------------
    n0 = d7["pages"][0]
    _ck(all(k in n0 for k in NODE_FIELDS), "every contract record field present")
    _ck(n0["state"] == "PLANNED", "identities allocated first: state PLANNED")
    _ck(n0["revision"] == 0 and n0["approvals"] == [], "fresh node: revision 0, no approvals")
    _ck(n0["desired_state"] == "draft", "desired draft state by default")
    _ck({e["kind"] for e in d7["edges"]} <= set(CONTRACT_EDGE_KINDS), "edge kinds are contract kinds")
    err = [e for e in d7["edges"] if e["kind"] == "error"]
    _ck(all(e["from"] == e["to"] for e in err), "error edges retain the current node")
    _ck(all(e["policy"] == PENDING_BEHAVIOR for e in err), "error edges carry the pending policy")
    _ck(all(n["page_role"] in PAYMENT_ROLES for n in d7["pages"]
            if n["logical_id"] in {e["from"] for e in err}),
        "error edges only on payment-touching pages")

    # -- presets through adapters only: custom sets pass through untouched ---
    custom = [
        {"id": "hero", "page_type": "main", "page_role": "landing", "role_instance": None},
        {"id": "ds_a", "page_type": "downsell", "page_role": "downsell_1", "role_instance": "ds_a"},
        {"id": "ds_b", "page_type": "downsell", "page_role": "downsell_1", "role_instance": "ds_b"},
        {"id": "ds_c", "page_type": "downsell", "page_role": "downsell_1", "role_instance": "ds_c"},
        {"id": "ty", "page_type": "thank-you", "page_role": "thank_you", "role_instance": None},
    ]
    custom_edges = [
        {"from": "hero", "to": "ds_a", "on": "proceed"},
        {"from": "ds_a", "to": "ds_b", "on": "proceed"},
        {"from": "ds_b", "to": "ds_c", "on": "proceed"},
        {"from": "ds_c", "to": "ty", "on": "proceed"},
    ]
    dc = adapt_page_set(custom, custom_edges, location="ghl-test")
    _ck(dc["preset"] is None, "custom set carries no preset — never imposed")
    _ck([n["node_id"] for n in dc["pages"]] == [e["id"] for e in custom],
        "custom set passes through unchanged")
    _ck(len({n["logical_id"] for n in dc["pages"]}) == 5, "three repeated downsell instances, three IDs")
    _ck({n["page_role"] for n in dc["pages"] if n["role_instance"]} == {"downsell_1"},
        "repeated instances share one role")

    # -- coordinator event vocabulary adapts too -----------------------------
    de = adapt_page_set(
        [{"id": "landing", "page_type": "main", "page_role": "landing", "role_instance": None},
         {"id": "checkout", "page_type": "checkout", "page_role": "checkout", "role_instance": None}],
        [{"from": "landing", "to": "checkout", "event": "interest_submitted"},
         {"from": "checkout", "to": "checkout", "event": "payment_succeeded"}],
        location="ghl-test")
    _ck([e["kind"] for e in de["edges"] if e["kind"] != "error"] == ["submit", "success"],
        "coordinator events map to submit/success")

    # -- negative cases fail closed -----------------------------------------
    def refuses(fn, label):
        try:
            fn()
        except RouteAdapterError:
            _ck(True, label)
        else:
            raise AssertionError(f"self-check failed: {label} (accepted the violation)")

    refuses(lambda: preset_page_set(4), "preset 4 refused")
    refuses(lambda: adapt_page_set(
        [{"id": "a", "page_type": "main", "page_role": "slot_7", "role_instance": None}], [],
        location="x"), "unknown role refused")
    refuses(lambda: adapt_page_set(custom[:2] + custom[1:3], [], location="x"),
             "duplicate node id refused")
    refuses(lambda: adapt_page_set(
        [{"id": "a", "page_type": "main", "page_role": "landing", "role_instance": None},
         {"id": "b", "page_type": "checkout", "page_role": "checkout", "role_instance": None}],
        [{"from": "a", "to": "nope", "on": "proceed"}], location="x"),
        "edge to unknown node refused")
    refuses(lambda: adapt_page_set(
        [{"id": "a", "page_type": "main", "page_role": "landing", "role_instance": None}],
        [{"from": "a", "to": "a", "on": "improvise"}], location="x"),
        "unknown edge label refused")
    refuses(lambda: adapt_page_set(
        [{"id": "c", "page_type": "checkout", "page_role": "checkout", "role_instance": None},
         {"id": "t", "page_type": "thank-you", "page_role": "thank_you", "role_instance": None}],
        [{"from": "c", "to": "t", "on": "decline"}], location="x"),
        "checkout decline edge refused")

    # -- seam honesty + optional equality with the 49 skill source ----------
    status = contract_status()
    _ck(isinstance(status["npage_contract_present"], bool), "seam reports presence honestly")
    _ck(status["outstanding_integration"] == list(INTEGRATION_OUTSTANDING),
        "outstanding integration is recorded, not papered over")
    structure = (Path(__file__).resolve().parents[2] / "49-signature-funnel"
                 / "structure" / "funnel_structure.json")
    if structure.exists():
        import json
        doc = json.loads(structure.read_text(encoding="utf-8"))
        _ck(doc["funnel_matrix"]["3"] == PRESET_MATRIX["3"]
            and doc["funnel_matrix"]["5"] == PRESET_MATRIX["5"]
            and doc["funnel_matrix"]["7"] == PRESET_MATRIX["7"],
            "embedded preset matrix equals funnel_structure.json")
        table = doc["page_role_map"]["page_types"]
        for page_type, (role, instance) in PAGE_ROLE_MAP.items():
            _ck(table[page_type]["page_role"] == role
                and table[page_type].get("role_instance") == instance,
                f"page_role_map matches funnel_structure.json for {page_type}")
        print(f"cross-check: funnel_structure.json present at {structure} — presets equal")
    else:
        print(f"cross-check: SKIPPED (no funnel_structure.json at {structure}); "
              f"embedded constants unverified against the skill file on this tree")


if __name__ == "__main__":
    _self_check()
    print(f"OK route_adapters self-check: {_TALLY} assertions")
