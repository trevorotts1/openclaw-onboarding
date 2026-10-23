"""
shared-utils/delivery/link_resolution.py — link/action/edge resolution for
the GHL delivery stream (W7B). One writer for this file: assignment W7B.

Resolves the delivery contract's logical links, actions and edges to the
native identities and real readback URLs created at runtime:

    resolve_delivery(plan)       -> bindings + resolved edges + per-edge results
    walk_navigation(resolution)  -> cycle-safe navigation walk (websites)
    contract_seam_status()       -> explicit upstream integration seam status

Contract basis (GHL-DELIVERY-SPEC.md, "Delivery contract (W1 owns the
normative versioned schema)" and W7 ownership "link/action/edge resolution"):

  - stable logical IDs + actual page nodes; identity is the logical_id /
    native_id, never name alone; pages may share a role with distinct identity
  - funnels: ordering + explicit accept/decline/submit/success/error edges
  - websites: menus/shared sections/general navigation (cycles legitimate)
  - bind actual URLs/actions after identities are allocated; return native
    IDs, links, per-operation results; never silently drop anything
  - states PLANNED -> CREATED -> CONFIGURED -> PUBLISHED -> VERIFIED are
    distinct; a real public URL exists only after publication (readback
    honesty: a URL is never fabricated for a page that has none)

PROVISIONAL (W7B-U1): the upstream W1 schema module
(shared-utils/delivery/npage_contract.py) may not exist yet. This module
consumes plain dicts under the PLAN KEYS below and exposes
contract_seam_status() so every caller can see exactly what integration
remains outstanding. Nothing here is presented as the W1 normative schema.

PLAN KEYS (plain dict / JSON):
{
  "contract_version": "1.0",
  "kind": "funnel" | "website",
  "pages": [ {"logical_id", "role"?, "name"?, "slug"?, "native_id"?,
              "url"?, "url_kind"?: "public" | "preview", "state"} ],
  "edges": [ {"edge_id", "source", "type", "component"?, "label"?,
              "target": {"logical_id": ...}
                      | {"native_id": ...}
                      | {"url": ..., "external": true} } ]
}

Edge types: accept, decline, submit, success, error, navigation, menu,
shared_section, next, back, custom. Unknown types fail closed — never guessed.
A URL target must declare "external": true; binding by name or bare URL alone
is rejected.

Per-edge resolution status:
  resolved         native identity AND readback URL bound
  pending_readback native identity bound, readback URL outstanding (never faked)
  unresolved       target cannot be bound yet (reason recorded)

Import pattern (namespace package — no __init__.py needed):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared-utils"))
    from delivery.link_resolution import resolve_delivery

Run the assert-based self-check:

    python3 -I shared-utils/delivery/link_resolution.py
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

EDGE_TYPES: Tuple[str, ...] = (
    "accept", "decline", "submit", "success", "error",
    "navigation", "menu", "shared_section", "next", "back", "custom",
)
NAV_EDGE_TYPES: Tuple[str, ...] = ("navigation", "menu", "shared_section", "next", "back")
STATES: Tuple[str, ...] = ("PLANNED", "CREATED", "CONFIGURED", "PUBLISHED", "VERIFIED")
PUBLIC_STATES: Tuple[str, ...] = ("PUBLISHED", "VERIFIED")


def _is_http_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _resolve_target(edge: Dict[str, Any], pages_by_logical: Dict[str, Dict[str, Any]],
                    pages_by_native: Dict[str, List[str]], errors: List[str],
                    edge_id: str) -> Optional[Dict[str, Any]]:
    """Resolve one edge target to native identity + readback URL. Fail closed."""
    target = edge.get("target")
    if not isinstance(target, dict):
        errors.append(f"edge {edge_id}: target must be a dict (logical_id, native_id, or external url)")
        return None

    if "logical_id" in target:
        logical = target.get("logical_id")
        page = pages_by_logical.get(logical) if isinstance(logical, str) else None
        if page is None:
            return {"status": "unresolved", "reason": f"target logical_id {logical!r} is not a planned page"}
        return _bind_page(page, logical)
    if "native_id" in target:
        native = target.get("native_id")
        owners = pages_by_native.get(native) if isinstance(native, str) else None
        if not owners:
            return {"status": "unresolved", "reason": f"target native_id {native!r} is not bound to any planned page"}
        if len(owners) > 1:
            errors.append(f"edge {edge_id}: native_id {native!r} bound to multiple pages — ambiguous, rejected")
            return {"status": "unresolved", "reason": f"native_id {native!r} ambiguous across pages {owners}"}
        logical = owners[0]
        return _bind_page(pages_by_logical[logical], logical)
    if "url" in target:
        if target.get("external") is not True:
            errors.append(f"edge {edge_id}: url target must declare \"external\": true — never bind by name/url alone")
            return None
        url = target.get("url")
        if not _is_http_url(url):
            errors.append(f"edge {edge_id}: external url must be http(s), got {url!r}")
            return None
        return {"status": "resolved", "external": True, "native_id": None,
                "url": url, "url_kind": "public", "reason": None}
    errors.append(f"edge {edge_id}: target must declare logical_id, native_id, or external url")
    return None


def _bind_page(page: Dict[str, Any], logical: str) -> Dict[str, Any]:
    native_id = page.get("native_id")
    url = page.get("url")
    if native_id and url:
        return {"status": "resolved", "external": False, "native_id": native_id,
                "url": url, "url_kind": page.get("url_kind") or "public",
                "reason": None, "target_logical_id": logical}
    if native_id:
        return {"status": "pending_readback", "external": False, "native_id": native_id,
                "url": None, "url_kind": None, "target_logical_id": logical,
                "reason": f"target page {logical!r} has native_id but no readback URL yet (state={page.get('state')!r})"}
    return {"status": "unresolved", "external": False, "native_id": None,
            "url": None, "url_kind": None, "target_logical_id": logical,
            "reason": f"target page {logical!r} has no native identity yet (state={page.get('state')!r})"}


def resolve_delivery(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve every link/action/edge in a plan to native ids and real URLs.

    Pure function: the input plan is never mutated. Everything unresolvable
    is reported (errors / unresolved) — never silently dropped.
    """
    errors: List[str] = []
    unresolved: List[Dict[str, Any]] = []
    resolved_edges: List[Dict[str, Any]] = []
    bindings: Dict[str, Dict[str, Any]] = {}

    if not isinstance(plan, dict):
        raise TypeError("plan must be a dict")
    kind = plan.get("kind")
    if kind not in ("funnel", "website"):
        errors.append(f"plan.kind must be 'funnel' or 'website', got {kind!r}")
    if not isinstance(plan.get("contract_version"), str) or not plan.get("contract_version"):
        errors.append("plan.contract_version is required (W1 schema identity, never assumed)")

    pages_by_logical: Dict[str, Dict[str, Any]] = {}
    pages_by_native: Dict[str, List[str]] = {}
    for page in plan.get("pages") or []:
        if not isinstance(page, dict):
            errors.append("plan.pages entries must be dicts")
            continue
        logical = page.get("logical_id")
        if not isinstance(logical, str) or not logical:
            errors.append(f"page missing logical_id — identity is never name alone (name={page.get('name')!r})")
            continue
        if logical in pages_by_logical:
            errors.append(f"duplicate logical_id {logical!r} — pages may share a role, never an identity")
            continue
        state = page.get("state")
        if state not in STATES:
            errors.append(f"page {logical!r}: state {state!r} not in {' -> '.join(STATES)}")
        url_kind = page.get("url_kind")
        if url_kind not in (None, "public", "preview"):
            errors.append(f"page {logical!r}: url_kind {url_kind!r} must be 'public', 'preview' or absent")
        url = page.get("url")
        if url is not None and not _is_http_url(url):
            errors.append(f"page {logical!r}: url must be an http(s) readback URL, got {url!r}")
        if url_kind == "public" and state not in PUBLIC_STATES:
            errors.append(f"page {logical!r}: public URL claimed before publication (state={state!r})")
        if state == "VERIFIED" and not url:
            errors.append(f"page {logical!r}: VERIFIED page missing readback URL")
        if url and not page.get("native_id"):
            errors.append(f"page {logical!r}: readback URL without native_id — unbound identity, rejected")
        native_id = page.get("native_id")
        if native_id:
            if not isinstance(native_id, str):
                errors.append(f"page {logical!r}: native_id must be a string")
            else:
                pages_by_native.setdefault(native_id, []).append(logical)
        pages_by_logical[logical] = page
        bindings[logical] = {
            "native_id": native_id, "url": url, "url_kind": url_kind,
            "state": state, "role": page.get("role"),
        }
    for native_id, owners in pages_by_native.items():
        if len(owners) > 1:
            errors.append(f"duplicate native_id {native_id!r} bound to pages {owners}")

    edge_types_by_source: Dict[str, Set[str]] = {}
    edge_count = 0
    for edge in plan.get("edges") or []:
        if not isinstance(edge, dict):
            errors.append("plan.edges entries must be dicts")
            continue
        edge_count += 1
        edge_id = edge.get("edge_id")
        if not isinstance(edge_id, str) or not edge_id:
            errors.append("edge missing edge_id — never name alone, edge dropped from resolution")
            continue
        etype = edge.get("type")
        if etype not in EDGE_TYPES:
            errors.append(f"edge {edge_id}: unknown edge type {etype!r} — never guessed")
            continue
        source = edge.get("source")
        if source not in pages_by_logical:
            errors.append(f"edge {edge_id}: source {source!r} is not a planned page")
            continue
        edge_types_by_source.setdefault(source, set()).add(etype)
        resolution = _resolve_target(edge, pages_by_logical, pages_by_native, errors, edge_id)
        if resolution is None:
            continue  # error already recorded
        entry = dict(edge)
        entry["resolution"] = resolution
        resolved_edges.append(entry)
        if resolution["status"] == "unresolved":
            unresolved.append({"edge_id": edge_id, "source": source,
                               "status": resolution["status"], "reason": resolution["reason"]})

    # Explicit edge sets: accept/decline and submit/success/error must be paired.
    for source, types in edge_types_by_source.items():
        if "submit" in types and not {"success", "error"} <= types:
            errors.append(f"page {source!r}: submit edge without explicit success/error edge")
        if {"success", "error"} & types and "submit" not in types:
            errors.append(f"page {source!r}: success/error edge without explicit submit edge")
        if "accept" in types and "decline" not in types:
            errors.append(f"page {source!r}: accept edge without explicit decline edge")
        if "decline" in types and "accept" not in types:
            errors.append(f"page {source!r}: decline edge without explicit accept edge")

    status_counts = {"resolved": 0, "pending_readback": 0, "unresolved": 0}
    for entry in resolved_edges:
        status_counts[entry["resolution"]["status"]] += 1
    return {
        "contract_version": plan.get("contract_version"),
        "kind": kind,
        "bindings": bindings,
        "resolved_edges": resolved_edges,
        "unresolved": unresolved,
        "errors": errors,
        "counts": {"pages": len(bindings), "edges": edge_count,
                   "errors": len(errors), **status_counts},
    }


def walk_navigation(resolution: Dict[str, Any], start: str) -> Dict[str, Any]:
    """Cycle-safe walk of navigation-family edges from a logical page.

    Websites legitimately have cycles (menus/shared sections/general
    navigation); a revisit is recorded, never iterated forever. Returns
    first-visit order, revisited targets, and how many edges were walked.
    """
    bindings = resolution.get("bindings") or {}
    if start not in bindings:
        raise ValueError(f"start {start!r} is not a planned page")
    adjacency: Dict[str, List[Optional[str]]] = {}
    for entry in resolution.get("resolved_edges") or []:
        if entry.get("type") not in NAV_EDGE_TYPES:
            continue
        res = entry.get("resolution") or {}
        target = None if res.get("external") else res.get("target_logical_id")
        adjacency.setdefault(entry.get("source"), []).append(target)

    order: List[str] = []
    revisits: List[str] = []
    visited: Set[str] = set()
    edges_walked = 0
    stack: List[Optional[str]] = [start]
    while stack:
        node = stack.pop()
        if node is None:  # external leaf (already reported by its edge)
            continue
        if node in visited:
            revisits.append(node)
            continue
        visited.add(node)
        order.append(node)
        for nxt in adjacency.get(node, []):
            edges_walked += 1
            stack.append(nxt)  # visited targets pop again as recorded revisits
    return {"order": order, "revisits": revisits, "edges_walked": edges_walked}


def contract_seam_status() -> Dict[str, Any]:
    """Explicit integration seam to the upstream W1 schema module.

    Records exactly what integration remains outstanding instead of
    pretending the normative schema is already wired in.
    """
    try:
        import npage_contract  # type: ignore  # W1 shared-utils/delivery/npage_contract.py
    except Exception as exc:  # noqa: BLE001 — absence is a reportable fact
        return {
            "npage_contract_importable": False,
            "detail": f"{type(exc).__name__}: {exc}",
            "outstanding": [
                "W1 shared-utils/delivery/npage_contract.py not importable — plan dicts are validated against PLAN KEYS in this module's docstring, not against the W1 normative schema",
                "when W1 lands: map its plan/edge/target key names onto PLAN KEYS here (single adapter point) and re-run the self-check",
            ],
        }
    return {
        "npage_contract_importable": True,
        "detail": getattr(npage_contract, "__file__", "<no __file__>"),
        "outstanding": [
            "adopt the W1 schema key names at the PLAN KEYS adapter point above, then re-run the self-check",
        ],
    }


# ---------------------------------------------------------------------------
# Assert-based self-check (the runnable check for W7B-U1).
#   python3 -I shared-utils/delivery/link_resolution.py
# ---------------------------------------------------------------------------
def _selfcheck() -> int:
    import copy

    passed = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal passed
        assert cond, "FAIL: " + label
        passed += 1
        print("PASS", label)

    def errors_of(plan: Dict[str, Any]) -> List[str]:
        return resolve_delivery(plan)["errors"]

    def has_error(errs: List[str], needle: str) -> bool:
        return any(needle in e for e in errs)

    # 1 — funnel plan: submit/success/error + accept/decline paired edges
    funnel = {
        "contract_version": "1.0",
        "kind": "funnel",
        "pages": [
            {"logical_id": "p_order", "role": "order", "name": "Order",
             "native_id": "ghl-page-1001", "url": "https://ex.com/f/order",
             "url_kind": "public", "state": "PUBLISHED"},
            {"logical_id": "p_upsell", "role": "upsell", "name": "Upsell",
             "native_id": "ghl-page-1002", "url": "https://ex.com/f/upsell",
             "url_kind": "public", "state": "PUBLISHED"},
            {"logical_id": "p_downsell", "role": "upsell", "name": "Downsell",
             "native_id": "ghl-page-1003", "url": "https://ex.com/f/downsell",
             "url_kind": "public", "state": "VERIFIED"},
            {"logical_id": "p_thanks", "role": "confirmation", "name": "Thanks",
             "native_id": "ghl-page-1004", "state": "CREATED"},
            {"logical_id": "p_draft", "role": "content", "name": "Draft",
             "state": "PLANNED"},
        ],
        "edges": [
            {"edge_id": "e1", "source": "p_order", "type": "submit",
             "component": "order-form", "target": {"logical_id": "p_upsell"}},
            {"edge_id": "e2", "source": "p_order", "type": "success",
             "component": "order-form", "target": {"logical_id": "p_thanks"}},
            {"edge_id": "e3", "source": "p_order", "type": "error",
             "component": "order-form", "target": {"logical_id": "p_order"}},
            {"edge_id": "e4", "source": "p_upsell", "type": "accept",
             "target": {"logical_id": "p_thanks"}},
            {"edge_id": "e5", "source": "p_upsell", "type": "decline",
             "target": {"logical_id": "p_downsell"}},
            {"edge_id": "e6", "source": "p_downsell", "type": "accept",
             "target": {"logical_id": "p_thanks"}},
            {"edge_id": "e7", "source": "p_downsell", "type": "decline",
             "target": {"logical_id": "p_thanks"}},
            {"edge_id": "e8", "source": "p_thanks", "type": "navigation",
             "target": {"logical_id": "p_draft"}},
            {"edge_id": "e9", "source": "p_order", "type": "navigation",
             "target": {"url": "https://support.ex.com", "external": True}},
        ],
    }
    before = copy.deepcopy(funnel)
    res = resolve_delivery(funnel)
    ok(funnel == before, "resolve_delivery never mutates the plan")
    ok(res["errors"] == [], f"funnel plan has no errors (got {res['errors']})")
    by_id = {e["edge_id"]: e for e in res["resolved_edges"]}
    ok(set(by_id) == {"e1", "e2", "e3", "e4", "e5", "e6", "e7", "e8", "e9"},
       "no edge silently dropped")
    ok(by_id["e1"]["resolution"]["status"] == "resolved"
       and by_id["e1"]["resolution"]["native_id"] == "ghl-page-1002"
       and by_id["e1"]["resolution"]["url"] == "https://ex.com/f/upsell",
       "submit edge resolved to target native id + readback URL")
    ok(by_id["e2"]["resolution"]["status"] == "pending_readback"
       and by_id["e2"]["resolution"]["native_id"] == "ghl-page-1004"
       and by_id["e2"]["resolution"]["url"] is None,
       "success edge pending_readback: native id bound, URL never faked")
    ok(by_id["e8"]["resolution"]["status"] == "unresolved"
       and "no native identity" in by_id["e8"]["resolution"]["reason"],
       "edge into uncreated page reports unresolved with reason")
    ok(by_id["e9"]["resolution"]["status"] == "resolved"
       and by_id["e9"]["resolution"]["external"] is True
       and by_id["e9"]["resolution"]["url"] == "https://support.ex.com",
       "external target passthrough with declared external: true")
    ok(res["bindings"]["p_upsell"]["native_id"] == "ghl-page-1002",
       "bindings map logical id -> native id")
    ok(res["bindings"]["p_upsell"]["role"] == res["bindings"]["p_downsell"]["role"] == "upsell",
       "pages may share a role")
    ok(res["bindings"]["p_upsell"]["native_id"] != res["bindings"]["p_downsell"]["native_id"],
       "shared role keeps distinct identity")
    ok(res["counts"] == {"pages": 5, "edges": 9, "errors": 0,
                        "resolved": 4, "pending_readback": 4, "unresolved": 1},
       f"counts exact (got {res['counts']})")
    ok(len(res["unresolved"]) == 1 and res["unresolved"][0]["edge_id"] == "e8",
       "unresolved list names exactly the unbindable edges")

    # 2 — fail-closed validation cases
    bad_base = {"contract_version": "1.0", "kind": "funnel",
                "pages": [{"logical_id": "p1", "state": "PUBLISHED",
                           "native_id": "n1", "url": "https://ex.com/1",
                           "url_kind": "public"}], "edges": []}

    def variant(**kw: Any) -> Dict[str, Any]:
        plan = copy.deepcopy(bad_base)
        plan.update(kw)
        return plan

    ok(has_error(errors_of(variant(kind="blog")), "plan.kind"), "bad plan.kind rejected")
    ok(has_error(errors_of(variant(contract_version=None)), "contract_version"),
       "missing contract_version rejected")
    ok(has_error(errors_of({"contract_version": "1.0", "kind": "funnel",
                            "pages": [{"name": "Home", "state": "PLANNED"}], "edges": []}),
                 "never name alone"), "page without logical_id rejected (never name alone)")
    ok(has_error(errors_of(variant(pages=bad_base["pages"] + [
        {"logical_id": "p1", "state": "PLANNED"}])), "duplicate logical_id"),
       "duplicate logical_id rejected")
    ok(has_error(errors_of(variant(pages=bad_base["pages"] + [
        {"logical_id": "p2", "state": "PLANNED", "native_id": "n1"}])), "duplicate native_id"),
       "duplicate native_id rejected")
    ok(has_error(errors_of(variant(pages=[
        {"logical_id": "p1", "state": "PLANNED", "url": "https://ex.com/1"}])),
        "without native_id"), "readback URL without native_id rejected")
    ok(has_error(errors_of(variant(pages=[
        {"logical_id": "p1", "state": "PLANNED", "native_id": "n1",
         "url": "https://ex.com/1", "url_kind": "public"}])),
        "before publication"), "public URL before publication rejected")
    ok(has_error(errors_of(variant(pages=[
        {"logical_id": "p1", "state": "VERIFIED", "native_id": "n1"}])),
        "VERIFIED page missing readback URL"), "VERIFIED without readback URL rejected")
    ok(has_error(errors_of(variant(pages=[
        {"logical_id": "p1", "state": "BROKEN", "native_id": "n1"}])),
        "not in PLANNED"), "unknown state rejected")
    ok(has_error(errors_of(variant(edges=[
        {"edge_id": "e1", "source": "p1", "type": "warp", "target": {"logical_id": "p1"}}])),
        "never guessed"), "unknown edge type rejected (never guessed)")
    ok(has_error(errors_of(variant(edges=[
        {"edge_id": "e1", "source": "pX", "type": "navigation", "target": {"logical_id": "p1"}}])),
        "not a planned page"), "edge from unknown source rejected")
    ok(has_error(errors_of(variant(edges=[
        {"edge_id": "e1", "source": "p1", "type": "navigation", "target": {"name": "About"}}])),
        "target must declare"), "name-only target rejected")
    ok(has_error(errors_of(variant(edges=[
        {"edge_id": "e1", "source": "p1", "type": "navigation", "target": {"url": "https://ex.com"}}])),
        "external\": true"), "bare url target without external declaration rejected")
    ok(has_error(errors_of(variant(edges=[
        {"edge_id": "e1", "source": "p1", "type": "navigation",
         "target": {"url": "javascript:alert(1)", "external": True}}])),
        "http(s)"), "non-http external url rejected")
    ok(has_error(errors_of(variant(edges=[
        {"edge_id": "e1", "source": "p1", "type": "submit", "target": {"logical_id": "p1"}}])),
        "without explicit success/error"), "submit without success/error edges rejected")
    ok(has_error(errors_of(variant(edges=[
        {"edge_id": "e1", "source": "p1", "type": "success", "target": {"logical_id": "p1"}}])),
        "without explicit submit"), "success/error without submit rejected")
    ok(has_error(errors_of(variant(edges=[
        {"edge_id": "e1", "source": "p1", "type": "accept", "target": {"logical_id": "p1"}}])),
        "without explicit decline"), "accept without decline rejected")
    ok(has_error(errors_of(variant(edges=[
        {"edge_id": "e1", "source": "p1", "type": "decline", "target": {"logical_id": "p1"}}])),
        "without explicit accept"), "decline without accept rejected")
    ok(has_error(errors_of(variant(edges=[
        {"source": "p1", "type": "navigation", "target": {"logical_id": "p1"}}])),
        "edge missing edge_id"), "edge without edge_id rejected (never name alone)")
    unk = resolve_delivery(variant(edges=[
        {"edge_id": "e1", "source": "p1", "type": "navigation", "target": {"logical_id": "p9"}}]))
    ok(any(u["edge_id"] == "e1" for u in unk["unresolved"])
       and has_error(unk["errors"], "not a planned page") is False,
       "unknown target logical id lands in unresolved with reason, not silent drop")
    amb = resolve_delivery(variant(pages=bad_base["pages"] + [
        {"logical_id": "p2", "state": "PLANNED", "native_id": "n2"}], edges=[
        {"edge_id": "e1", "source": "p1", "type": "navigation", "target": {"native_id": "nX"}}]))
    ok(any(u["edge_id"] == "e1" for u in amb["unresolved"]),
       "unknown native_id target lands in unresolved with reason")

    # 3 — website navigation with a legitimate menu cycle
    site = {
        "contract_version": "1.0",
        "kind": "website",
        "pages": [
            {"logical_id": "w_home", "role": "home", "state": "PUBLISHED",
             "native_id": "site-1", "url": "https://ex.com/", "url_kind": "public"},
            {"logical_id": "w_about", "role": "about", "state": "PUBLISHED",
             "native_id": "site-2", "url": "https://ex.com/about", "url_kind": "public"},
        ],
        "edges": [
            {"edge_id": "m1", "source": "w_home", "type": "menu", "target": {"logical_id": "w_about"}},
            {"edge_id": "m2", "source": "w_about", "type": "menu", "target": {"logical_id": "w_home"}},
        ],
    }
    sres = resolve_delivery(site)
    ok(sres["errors"] == [], f"website plan with menu cycle has no errors (got {sres['errors']})")
    walk = walk_navigation(sres, "w_home")
    ok(walk["order"] == ["w_home", "w_about"], f"cycle-safe walk first-visit order (got {walk['order']})")
    ok(walk["revisits"] == ["w_home"],
       f"menu cycle recorded as revisit, walk terminates (got {walk['revisits']})")
    ok(walk["edges_walked"] == 2, "walked exactly the two menu edges")
    try:
        walk_navigation(sres, "w_ghost")
        ok(False, "unknown walk start must raise")
    except ValueError:
        ok(True, "unknown walk start raises ValueError")

    # 4 — explicit upstream seam, never pretended as landed
    seam = contract_seam_status()
    ok(isinstance(seam.get("outstanding"), list) and len(seam["outstanding"]) >= 1,
       "contract_seam_status lists outstanding integration")
    ok("npage_contract_importable" in seam, "seam reports upstream import state")

    print(f"OK {passed} PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selfcheck())
