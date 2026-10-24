#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""role_wrappers.py — Skill 49 role wrappers that consume ACTUAL delivery
results, never stubs.

Unit W9B-U1 (GHL-DELIVERY-SPEC.md, stream W9: "49 role wrappers consuming
real delivery results"). One wrapper per page_role of the ONE page-role
table (structure/funnel_structure.json page_role_map, Fix 15), each wrapper
instance-aware: downsell-2 is a repeated instance of downsell_1
(role_instance "downsell_2"), never an eighth role.

A wrapper consumes two actual inputs and binds them into one role record:

  * the role's page-result (schema page-result 1.0, the record shape
    scripts/collect_launch_receipts.py validates) — accepted ONLY when it
    echoes its page-request exactly (same request_id, input_hash, page_id,
    launch_id, revision, tenant, location and test_only); the collect
    module is the one echo authority and is loaded from scripts/, never
    re-spelled here, and
  * the delivery-contract page node (GHL-DELIVERY-SPEC.md "Delivery
    contract (W1 owns the normative versioned schema)": folder/container/
    page identities, name/slug, approved content, native components,
    product/price references, desired state, state) — consumed verbatim.

STUBS ARE REFUSED, NEVER CONSUMED. A result in the exact
dispatch_launch._simulated_executor test-double shape (no artifacts and no
native bindings) carries no delivery at all and is refused by name, and so
is a result explicitly marked simulated/stub. Every value the platform has
not produced yet is recorded in ``missing`` and the record carries
bound_complete=False: incomplete is reported as incomplete, never as done
(GHL-DELIVERY-SPEC.md: "A required disabled operation = capability
incomplete").

A wrapper never mints a value. It copies what the actual result and the
actual delivery node carry, and nothing else: no identity, no native
binding, no proof class, no state. States PLANNED -> CREATED -> CONFIGURED
-> PUBLISHED -> VERIFIED are carried verbatim and never promoted (saving is
not publishing; one page delivered is not the site delivered).

PROVISIONAL (W9B): the delivery nodes reach this module today from the
route adapters (shared-utils/signature_launch/route_adapters.py, unit
W1B-U1) or from an execution stream's saved state; that module is not on
this tree yet. load_route_adapters() is the seam and contract_status()
reports it honestly; delivery nodes are validated against the local
contract-record mirror here in the meantime. INTEGRATION_OUTSTANDING
records exactly what remains.

Deterministic, stdlib only, no network, no model. Never reads a secret.
Run the self-check: ``python3 -I 49-signature-funnel/role_wrappers.py``
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "ghl-delivery-role-wrapper/v0"

# --- delivery contract vocabulary (GHL-DELIVERY-SPEC.md "Delivery contract") ---
STATES = ("PLANNED", "CREATED", "CONFIGURED", "PUBLISHED", "VERIFIED")
DESIRED_STATES = ("draft", "published")

# The identity/binding fields a wrapper may bind ONLY from an actual
# delivery node (W5/W7/W8 fill them; a wrapper never invents one).
DELIVERY_IDENTITY_FIELDS = ("folder_identity", "container_identity",
                            "page_identity")
DELIVERY_BINDING_FIELDS = ("logical_id", "node_id", "page_type",
                           "page_role", "role_instance", "name", "slug",
                           "approved_content", "native_components",
                           "product_price_refs", "desired_state", "state")

# --- 49 role wrapper table -------------------------------------------------
# Provenance: 49-signature-funnel/launch-adapters.example.json (the S49-08
# consumer-adapter entries, one per page_role) and scripts/dispatch_launch.py
# ROLE_SKILL. The role VOCABULARY itself is never re-spelled here: it is read
# from structure/funnel_structure.json page_role_map at import and this table
# is refused at import if it disagrees, so the two can never drift apart.
# product_selection runs Skill 78's native emitter chain (plan builder, then
# emit_page_result.py) — the wrapper for that role consumes the chain's
# page-result like every other role.
ROLE_WRAPPERS = {
    "landing": {"wrapper": "landing_bridge.py", "skill": 71},
    "product_selection": {"wrapper": "78-signature-product-selection native emitter chain",
                          "skill": 78},
    "checkout": {"wrapper": "checkout_wrapper.py (design_only)", "skill": 79},
    "upsell_1": {"wrapper": "upsell_wrapper.py", "skill": 80},
    "downsell_1": {"wrapper": "downsell_wrapper.py", "skill": 81},
    "upsell_2": {"wrapper": "upsell_wrapper.py", "skill": 80},
    "thank_you": {"wrapper": "translate_thank_you_result.py", "skill": 82},
}

PAGE_ROLE_MAP_CONTRACT = "signature-funnel-page-role-map/v1"
PAGE_ROLE_MAP_FILE = (Path(__file__).resolve().parent
                      / "structure" / "funnel_structure.json")
RECEIPTS_FILE = (Path(__file__).resolve().parent / "scripts"
                 / "collect_launch_receipts.py")

# --- seams to the sibling units (PROVISIONAL) -------------------------------
INTEGRATION_OUTSTANDING = [
    "Bind delivery nodes to shared-utils/signature_launch/route_adapters.py "
    "(W1B-U1) through load_route_adapters() when it lands on this tree; "
    "until then nodes are checked against the local contract-record mirror "
    "(validate_delivery_node) and contract_status() says so.",
    "folder_identity/container_identity/page_identity and approved_content "
    "are filled by the execution streams (W5 primitives, W7 publishing, W9A "
    "composition); product_price_refs by W8. Wrappers bind them when the "
    "delivery node carries them and record them in `missing` until then — "
    "never stubbed, never invented.",
    "State progression beyond PLANNED is emitted by the execution streams "
    "(W4 checkpoints, W5 primitives, W7 publishing); a wrapper carries the "
    "node's state verbatim and never promotes it.",
]


class RoleWrapperError(ValueError):
    """A request, result or delivery node this wrapper refuses to consume."""


# --------------------------------------------------------------------------
# Vocabulary: the ONE page-role table (funnel_structure.json, Fix 15)
# --------------------------------------------------------------------------

def load_page_role_map() -> Dict[str, Any]:
    """Read and shape-check the ONE page_type -> page_role table."""
    try:
        doc = json.loads(PAGE_ROLE_MAP_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RoleWrapperError(
            f"cannot read the page-role map {PAGE_ROLE_MAP_FILE}: {exc}"
        ) from exc
    table = doc.get("page_role_map") if isinstance(doc, dict) else None
    if not isinstance(table, dict):
        raise RoleWrapperError(
            f"{PAGE_ROLE_MAP_FILE} carries no page_role_map block")
    if table.get("contract") != PAGE_ROLE_MAP_CONTRACT:
        raise RoleWrapperError(
            f"page_role_map contract is {table.get('contract')!r}, expected "
            f"{PAGE_ROLE_MAP_CONTRACT!r}")
    roles = table.get("page_roles")
    types = table.get("page_types")
    if (not isinstance(roles, list) or not roles
            or len(set(roles)) != len(roles)
            or not all(isinstance(r, str) and r for r in roles)):
        raise RoleWrapperError(
            "page_role_map.page_roles must be a non-empty list of unique "
            "page_role strings")
    if not isinstance(types, dict) or not types:
        raise RoleWrapperError("page_role_map.page_types must be a non-empty map")
    for page_type, row in types.items():
        if not isinstance(row, dict) or row.get("page_role") not in roles:
            raise RoleWrapperError(
                f"page_type {page_type!r} does not map onto a declared "
                "page_role")
    return table


PAGE_ROLE_MAP = load_page_role_map()
PAGE_ROLES = tuple(PAGE_ROLE_MAP["page_roles"])
PAGE_TYPE_TO_ROLE = {page_type: row["page_role"]
                     for page_type, row in PAGE_ROLE_MAP["page_types"].items()}
# Repeated role instances, per role: {"downsell_1": {"downsell_2"}, ...}.
# The instance vocabulary comes from the table rows, never from this file.
ALLOWED_INSTANCES = {role: {row.get("role_instance")
                            for row in PAGE_ROLE_MAP["page_types"].values()
                            if row["page_role"] == role
                            and row.get("role_instance")}
                     for role in PAGE_ROLES}

if set(ROLE_WRAPPERS) != set(PAGE_ROLES):
    raise RoleWrapperError(
        "role wrapper table and page_role_map.page_roles disagree: "
        f"{sorted(set(ROLE_WRAPPERS) ^ set(PAGE_ROLES))}")


# --------------------------------------------------------------------------
# Seams to the sibling units
# --------------------------------------------------------------------------

def load_receipts():
    """scripts/collect_launch_receipts.py — the one result-echo authority."""
    if not RECEIPTS_FILE.exists():
        raise RoleWrapperError(
            f"the page-result echo authority is missing at {RECEIPTS_FILE}; "
            "the echo rules cannot be guessed")
    spec = importlib.util.spec_from_file_location("collect_launch_receipts",
                                                  RECEIPTS_FILE)
    if spec is None or spec.loader is None:
        raise RoleWrapperError(f"cannot load {RECEIPTS_FILE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def route_adapters_path() -> Path:
    """Where the W1B route adapters are expected (shared-utils/)."""
    return (Path(__file__).resolve().parents[1] / "shared-utils"
            / "signature_launch" / "route_adapters.py")


def load_route_adapters():
    """The W1B route adapters, or None while they are not on this tree."""
    path = route_adapters_path()
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("route_adapters", path)
    if spec is None or spec.loader is None:
        raise RoleWrapperError(f"cannot load route adapters {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contract_status() -> Dict[str, Any]:
    """Honest seam status: which authority supplies delivery nodes today."""
    module = load_route_adapters()
    source = ("route_adapters" if module is not None
              else "GHL-DELIVERY-SPEC.md delivery-contract local mirror")
    return {"route_adapters_present": module is not None,
            "route_adapters_path": str(route_adapters_path()),
            "receipts_authority": str(RECEIPTS_FILE),
            "contract_source": source,
            "outstanding_integration": list(INTEGRATION_OUTSTANDING)}


# --------------------------------------------------------------------------
# Stub refusal
# --------------------------------------------------------------------------

def is_simulated_result(result: Any) -> bool:
    """True for a test double, never for an actual delivery result.

    Two shapes are refused: a result explicitly marked ``simulated`` or
    ``stub``, and the exact ``dispatch_launch._simulated_executor`` shape
    (status authored, zero artifacts, no native bindings, L0, no blockers,
    test_only). Both carry no delivery — a wrapper consumes actual results
    only, so either is refused by name rather than dressed up as one.
    """
    if not isinstance(result, dict):
        return False
    if result.get("simulated") is True or result.get("stub") is True:
        return True
    return (result.get("status") == "authored"
            and result.get("artifacts") == []
            and result.get("native_bindings_ref") is None
            and result.get("proof_class") == "L0"
            and result.get("blockers") == []
            and result.get("independent_review") is False
            and result.get("test_only") is True)


# --------------------------------------------------------------------------
# Delivery-contract page node (local mirror until W1B lands)
# --------------------------------------------------------------------------

def validate_delivery_node(node: Any) -> None:
    """Local mirror of the contract record rules; raises RoleWrapperError.

    W1B route_adapters.validate_page_node runs as well through the seam when
    that module is present; this mirror keeps the wrapper honest before the
    merge (close against the real contract fields, not against stubs).
    """
    if not isinstance(node, dict):
        raise RoleWrapperError(f"delivery node is not an object: {node!r}")
    for f in ("logical_id", "page_role", "state"):
        if f not in node:
            raise RoleWrapperError(f"delivery node missing {f!r}: {node!r}")
    if node["page_role"] not in PAGE_ROLES:
        raise RoleWrapperError(
            f"delivery node role {node['page_role']!r} is not one of "
            f"{list(PAGE_ROLES)}")
    if node["state"] not in STATES:
        raise RoleWrapperError(
            f"delivery node state {node['state']!r} is not one of {STATES}")
    if "desired_state" in node and node["desired_state"] not in DESIRED_STATES:
        raise RoleWrapperError(
            f"delivery node desired_state {node['desired_state']!r} is not "
            f"one of {DESIRED_STATES}")
    module = load_route_adapters()
    if module is not None:
        check = getattr(module, "validate_page_node", None)
        if callable(check):
            try:
                check(node)
            except Exception as exc:  # noqa: BLE001 — surface, never swallow
                raise RoleWrapperError(
                    f"route_adapters refused the delivery node: {exc}") from exc


# --------------------------------------------------------------------------
# The role wrapper
# --------------------------------------------------------------------------

_ECHO_FIELDS = ("request_id", "input_hash", "page_id", "launch_id",
                "revision", "tenant_id", "location_id")


class RoleWrapper:
    """One Skill 49 page_role wrapper: consumes actual delivery results."""

    def __init__(self, role: str):
        if role not in ROLE_WRAPPERS:
            raise RoleWrapperError(
                f"no role wrapper for {role!r}; roles are "
                f"{list(ROLE_WRAPPERS)}")
        self.role = role
        self.wrapper_name = ROLE_WRAPPERS[role]["wrapper"]
        self.skill = ROLE_WRAPPERS[role]["skill"]

    # -- request side ------------------------------------------------------

    def _check_request(self, request: Any) -> Dict[str, Any]:
        if not isinstance(request, dict):
            raise RoleWrapperError(f"request is not an object: {request!r}")
        missing = [f for f in _ECHO_FIELDS if f not in request]
        if missing:
            raise RoleWrapperError(
                f"page-request missing echo field(s) {missing}: {request!r}")
        if request.get("page_role") != self.role:
            raise RoleWrapperError(
                f"request page_role {request.get('page_role')!r} is not this "
                f"wrapper's role {self.role!r}")
        return request

    def _check_instance(self, role_instance: Optional[str]) -> None:
        if role_instance is None:
            return
        if role_instance not in ALLOWED_INSTANCES[self.role]:
            raise RoleWrapperError(
                f"role_instance {role_instance!r} is not a declared instance "
                f"of {self.role!r} ({sorted(ALLOWED_INSTANCES[self.role])})")

    # -- consumption -------------------------------------------------------

    def consume(self, request: Dict[str, Any], result: Any, *,
                delivery_node: Optional[Dict[str, Any]] = None,
                role_instance: Optional[str] = None,
                result_path: Optional[str] = None) -> Dict[str, Any]:
        """Bind ONE actual page-result (+ delivery node) into a role record.

        Refuses, by name: a stub/simulated result, a result that does not
        echo its request, a delivery node of another role. Records, never
        invents: values absent from both inputs land in ``missing`` and the
        record is bound_complete=False.
        """
        request = self._check_request(request)
        if is_simulated_result(result):
            raise RoleWrapperError(
                "refusing a simulated/stub result as a delivery result: it "
                "carries no artifacts and no native bindings (the "
                "dispatch_launch --simulate-executor test-double shape); a "
                "role wrapper consumes actual delivery results only")
        receipts = load_receipts()
        fails = receipts.validate_result(result, request)
        if fails:
            raise RoleWrapperError(
                "page-result failed receipt validation (collect rules): "
                + "; ".join(fails))
        if result["test_only"] != request.get("test_only", result["test_only"]):
            raise RoleWrapperError("result test_only disagrees with its request")

        binding: Optional[Dict[str, Any]] = None
        missing: List[str] = []
        if delivery_node is None:
            missing.append("delivery_node")
            missing.extend(DELIVERY_IDENTITY_FIELDS)
        else:
            validate_delivery_node(delivery_node)
            if delivery_node["page_role"] != self.role:
                raise RoleWrapperError(
                    f"delivery node role {delivery_node['page_role']!r} does "
                    f"not match request role {self.role!r}; a wrapper never "
                    "consumes another role's page")
            node_instance = delivery_node.get("role_instance")
            if role_instance is not None and node_instance != role_instance:
                raise RoleWrapperError(
                    f"delivery node role_instance {node_instance!r} does not "
                    f"match the wrapped instance {role_instance!r}")
            role_instance = role_instance or node_instance
            self._check_instance(role_instance)
            binding = {f: delivery_node.get(f)
                       for f in (DELIVERY_BINDING_FIELDS
                                 + DELIVERY_IDENTITY_FIELDS)
                       if f in delivery_node}
            for f in DELIVERY_IDENTITY_FIELDS:
                if not delivery_node.get(f):
                    missing.append(f)
        if role_instance is not None:
            self._check_instance(role_instance)
        if result.get("native_bindings_ref") is None:
            missing.append("native_bindings_ref")

        record = {
            "schema": SCHEMA,
            "role": self.role,
            "role_instance": role_instance,
            "page_id": request["page_id"],
            "logical_id": (binding or {}).get("logical_id"),
            "echo": {f: request[f] for f in _ECHO_FIELDS},
            "consumed": {
                "status": result["status"],
                "proof_class": result["proof_class"],
                "artifacts": list(result["artifacts"]),
                "native_bindings_ref": result["native_bindings_ref"],
                "author_session": result["author_session"],
                "reviewer_session": result["reviewer_session"],
                "independent_review": result["independent_review"],
                "blockers": list(result["blockers"]),
                "test_only": result["test_only"],
            },
            "delivery_binding": binding,
            # State is carried verbatim and never promoted: a wrapper does
            # not advance PLANNED -> CREATED -> ... -> VERIFIED and never
            # reads authored/verified result status as PUBLISHED.
            "state": (binding or {}).get("state"),
            "missing": missing,
            "bound_complete": not missing,
            "source": {"result_path": result_path,
                       "wrapper": self.wrapper_name,
                       "skill": self.skill},
        }
        return record


def wrapper_for(role: str) -> RoleWrapper:
    """The wrapper for one page_role of the ONE page-role table."""
    return RoleWrapper(role)


def wrapper_manifest() -> Dict[str, Any]:
    """What is wired, per role: wrapper entrypoint, skill, instance policy."""
    return {role: {"wrapper": spec["wrapper"], "skill": spec["skill"],
                   "role_instances": sorted(ALLOWED_INSTANCES[role]),
                   "page_types": sorted(pt for pt, row
                                        in PAGE_ROLE_MAP["page_types"].items()
                                        if row["page_role"] == role)}
            for role, spec in ROLE_WRAPPERS.items()}


# --------------------------------------------------------------------------
# Whole-dispatch consumption
# --------------------------------------------------------------------------

def wrap_all(requests: List[Dict[str, Any]],
             results: Dict[str, Any], *,
             delivery: Optional[Dict[str, Any]] = None,
             result_paths: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Consume one dispatch: every page-request against its actual result.

    ``results`` is keyed by request_id — the actual page-result files a
    consumer adapter wrote. A request with no result gets a
    ``not_reported`` record naming the gap (incomplete, never done). A
    result keyed to no request is refused: nothing is consumed on faith.
    ``delivery`` is an optional route document (W1B shape: ``pages`` list);
    nodes are matched by node_id == page_id and their role must match.
    """
    if not isinstance(results, dict):
        raise RoleWrapperError("results must be keyed by request_id")
    result_paths = result_paths or {}
    pages = (delivery or {}).get("pages") if delivery else None
    if delivery is not None and not isinstance(pages, list):
        raise RoleWrapperError("delivery doc carries no pages list")

    known = set()
    records: List[Dict[str, Any]] = []
    for request in requests:
        if not isinstance(request, dict) or "request_id" not in request:
            raise RoleWrapperError(f"bad page-request: {request!r}")
        rid = request["request_id"]
        known.add(rid)
        role = request.get("page_role")
        wrapper = wrapper_for(role)
        node = None
        if pages is not None:
            matches = [n for n in pages
                       if isinstance(n, dict) and n.get("node_id") == request.get("page_id")]
            if len(matches) > 1:
                raise RoleWrapperError(
                    f"ambiguous delivery nodes for page_id "
                    f"{request.get('page_id')!r}: refusing to pick one")
            node = matches[0] if matches else None
        if rid not in results:
            records.append({
                "schema": SCHEMA,
                "role": role,
                "role_instance": (node or {}).get("role_instance"),
                "page_id": request.get("page_id"),
                "logical_id": (node or {}).get("logical_id"),
                "echo": {f: request.get(f) for f in _ECHO_FIELDS},
                "consumed": None,
                "delivery_binding": None,
                "state": (node or {}).get("state"),
                "missing": ["result"],
                "bound_complete": False,
                "status": "not_reported",
                "source": {"result_path": None,
                           "wrapper": wrapper.wrapper_name,
                           "skill": wrapper.skill},
            })
            continue
        records.append(wrapper.consume(
            request, results[rid], delivery_node=node,
            role_instance=(node or {}).get("role_instance"),
            result_path=result_paths.get(rid)))

    extra = sorted(set(results) - known)
    if extra:
        raise RoleWrapperError(
            f"results keyed to no request are refused: {extra}")

    reported = [r["page_id"] for r in records if r.get("consumed") is not None]
    expected = [r.get("page_id") for r in records]
    return {
        "schema": SCHEMA,
        "records": records,
        "roles_expected": expected,
        "roles_reported": reported,
        "missing_roles": [p for p in expected if p not in reported],
        "bound_complete": all(r["bound_complete"] for r in records),
    }


# --------------------------------------------------------------------------
# Self-check (assert-based; run with python3 -I)
# --------------------------------------------------------------------------

_TALLY = 0


def _ck(cond: Any, label: str) -> None:
    global _TALLY
    assert cond, f"self-check failed: {label}"
    _TALLY += 1


def _request(role: str, page_id: str, **over: Any) -> Dict[str, Any]:
    req = {
        "schema_version": "1.0", "tenant_id": "t1", "location_id": "loc1",
        "launch_id": "L1", "revision": 3,
        "request_id": f"t1:L1:rev3:{role}:{page_id}",
        "page_id": page_id, "page_role": role,
        "assigned_skill": ROLE_WRAPPERS[role]["skill"],
        "approval_ref": "appr-1", "input_hash": "a" * 64,
        "brand_ref": "brand-1", "brand_hash": "b" * 64,
        "route_graph_ref": "rg-1", "route_graph_hash": "c" * 64,
        "offer_refs": ["o1"], "copy_profile": "standard",
        "allowed_write_target": "local_only", "test_only": True,
    }
    req.update(over)
    return req


def _result(req: Dict[str, Any], **over: Any) -> Dict[str, Any]:
    res = {
        "schema_version": "1.0", "tenant_id": req["tenant_id"],
        "location_id": req["location_id"], "launch_id": req["launch_id"],
        "revision": req["revision"], "request_id": req["request_id"],
        "input_hash": req["input_hash"], "page_id": req["page_id"],
        "status": "locally_verified",
        "artifacts": [{"path": f"{req['page_id']}/desktop-wireframe.pdf",
                       "sha256": "d" * 64}],
        "author_session": "sess-author", "reviewer_session": None,
        "independent_review": False, "proof_class": "L2", "blockers": [],
        "native_bindings_ref": "nbind-9", "test_only": req["test_only"],
    }
    res.update(over)
    return res


def _simulated(req: Dict[str, Any]) -> Dict[str, Any]:
    # byte-shape of dispatch_launch._simulated_executor's output
    return {"schema_version": "1.0", "tenant_id": req["tenant_id"],
            "location_id": req["location_id"], "launch_id": req["launch_id"],
            "revision": req["revision"], "request_id": req["request_id"],
            "input_hash": req["input_hash"], "page_id": req["page_id"],
            "status": "authored", "artifacts": [],
            "author_session": "sess-sim", "reviewer_session": None,
            "independent_review": False, "proof_class": "L0", "blockers": [],
            "native_bindings_ref": None, "test_only": True}


def _node(role: str, node_id: str, **over: Any) -> Dict[str, Any]:
    node = {
        "logical_id": f"pg-{node_id}", "node_id": node_id,
        "page_type": node_id, "page_role": role, "role_instance": None,
        "location": "ghl-test", "builder_type": "funnel",
        "intent": "hero_and_order_capture", "revision": 3, "approvals": [],
        "folder_identity": "f-1", "container_identity": "c-1",
        "page_identity": "p-1", "name": node_id.title(), "slug": node_id,
        "approved_content": {"ref": "copy-1"},
        "native_components": ["slot-1"], "product_price_refs": ["pp-1"],
        "desired_state": "draft", "state": "PLANNED", "order": 0,
    }
    node.update(over)
    return node


def _self_check() -> None:
    # -- vocabulary comes from the ONE table, never from this file ----------
    _ck(PAGE_ROLES == tuple(PAGE_ROLE_MAP["page_roles"]),
        "role vocabulary equals funnel_structure.json page_roles")
    _ck(set(PAGE_TYPE_TO_ROLE.values()) <= set(PAGE_ROLES),
        "every page_type maps onto a declared role")
    _ck(PAGE_TYPE_TO_ROLE["downsell-2"] == "downsell_1",
        "downsell-2 maps to role downsell_1")
    _ck("downsell_2" in ALLOWED_INSTANCES["downsell_1"],
        "downsell_2 is a declared instance of downsell_1")
    _ck(ALLOWED_INSTANCES["checkout"] == set(),
        "checkout has no extra instances")
    man = wrapper_manifest()
    _ck(sorted(man) == sorted(PAGE_ROLES), "a wrapper for every page_role")
    _ck(man["checkout"]["wrapper"].startswith("checkout_wrapper.py"),
        "checkout wrapper is the design-only adapter")
    _ck(man["landing"]["skill"] == 71 and man["thank_you"]["skill"] == 82,
        "wrapper table carries the dispatch role -> skill assignment")
    _ck(all(man[r]["page_types"] for r in man),
        "every role names its page_types from the table")

    # -- happy path: the record binds ACTUAL values verbatim ----------------
    req = _request("checkout", "checkout")
    res = _result(req)
    node = _node("checkout", "checkout")
    rec = RoleWrapper("checkout").consume(req, res, delivery_node=node,
                                          result_path="work/result-checkout.json")
    _ck(rec["schema"] == SCHEMA, "record carries the wrapper schema")
    _ck(rec["consumed"]["artifacts"] == res["artifacts"],
        "artifacts consumed verbatim from the actual result")
    _ck(rec["consumed"]["native_bindings_ref"] == "nbind-9",
        "native binding ref consumed verbatim")
    _ck(rec["consumed"]["status"] == "locally_verified"
        and rec["consumed"]["proof_class"] == "L2",
        "result status/proof carried, never rewritten")
    _ck(rec["echo"]["request_id"] == req["request_id"]
        and rec["echo"]["input_hash"] == req["input_hash"],
        "echo keys bound from the request")
    _ck(rec["delivery_binding"]["folder_identity"] == "f-1"
        and rec["delivery_binding"]["page_identity"] == "p-1",
        "delivery identities bound from the actual node")
    _ck(rec["delivery_binding"]["approved_content"] == {"ref": "copy-1"},
        "approved content bound verbatim")
    _ck(rec["logical_id"] == "pg-checkout", "logical id bound from the node")
    _ck(rec["state"] == "PLANNED", "state carried verbatim, never promoted")
    _ck(rec["missing"] == [], "fully bound: nothing missing")
    _ck(rec["bound_complete"] is True, "fully bound record is complete")
    _ck(rec["source"]["result_path"] == "work/result-checkout.json",
        "consumption source recorded")

    # -- stubs are refused by name ------------------------------------------
    sim = _simulated(req)
    _ck(is_simulated_result(sim) is True, "simulate-executor double detected")
    _ck(is_simulated_result(res) is False,
        "an actual result is not mistaken for a stub")
    _ck(is_simulated_result(_result(req, simulated=True)) is True,
        "explicitly marked simulated result detected")
    _ck(is_simulated_result(_result(req, stub=True)) is True,
        "explicitly marked stub result detected")

    def refuses(fn, label):
        try:
            fn()
        except RoleWrapperError:
            _ck(True, label)
        else:
            raise AssertionError(f"self-check failed: {label} (consumed it)")

    refuses(lambda: RoleWrapper("checkout").consume(req, sim),
            "simulated double refused as a delivery result")
    refuses(lambda: RoleWrapper("checkout").consume(req, dict(sim, simulated=False)),
            "artifact-free authored double refused (no delivery in it)")
    refuses(lambda: RoleWrapper("checkout").consume(
        req, _result(req, page_id="other")),
        "result that does not echo its request refused")
    refuses(lambda: RoleWrapper("checkout").consume(
        req, _result(req, artifacts=[{"path": "x"}])),
        "artifact without path/sha256 refused")
    refuses(lambda: RoleWrapper("checkout").consume(
        req, _result(req, independent_review=True, reviewer_session=None)),
        "independent_review without a reviewer refused")
    refuses(lambda: RoleWrapper("upsell_1").consume(req, res),
        "another role's request refused by this wrapper")
    refuses(lambda: RoleWrapper("slot_7"), "unknown role refused")
    refuses(lambda: RoleWrapper("checkout").consume(
        req, res, delivery_node=_node("upsell_1", "upsell")),
        "delivery node of another role refused")
    refuses(lambda: RoleWrapper("downsell_1").consume(
        _request("downsell_1", "downsell-2"), _result(_request("downsell_1", "downsell-2")),
        delivery_node=_node("downsell_1", "downsell-2",
                            role_instance="downsell_3")),
        "undeclared role instance refused")
    refuses(lambda: RoleWrapper("downsell_1").consume(
        _request("downsell_1", "downsell-2"), _result(_request("downsell_1", "downsell-2")),
        delivery_node=_node("downsell_1", "downsell-2",
                            role_instance="downsell_2"),
        role_instance="downsell_3"),
        "wrapped instance disagreeing with the node refused")
    refuses(lambda: RoleWrapper("checkout").consume(
        req, res, delivery_node=_node("checkout", "checkout", state="LIVE")),
        "unknown delivery state refused")

    # -- incomplete is reported incomplete, never done ----------------------
    bare = RoleWrapper("checkout").consume(req, res)
    _ck(bare["delivery_binding"] is None, "no node: no binding invented")
    _ck("delivery_node" in bare["missing"]
        and "page_identity" in bare["missing"],
        "absent node identities named in missing")
    _ck(bare["bound_complete"] is False, "absent node: incomplete")
    _ck(bare["state"] is None, "no node: state is None, never invented")

    partial = RoleWrapper("checkout").consume(
        req, res, delivery_node=_node("checkout", "checkout",
                                      page_identity=None))
    _ck(partial["missing"] == ["page_identity"],
        "the one absent identity is the one named")
    _ck(partial["bound_complete"] is False, "absent identity: incomplete")
    _ck(partial["delivery_binding"]["folder_identity"] == "f-1",
        "present identities still bound")

    nb = RoleWrapper("checkout").consume(
        req, _result(req, native_bindings_ref=None),
        delivery_node=_node("checkout", "checkout"))
    _ck("native_bindings_ref" in nb["missing"] and nb["bound_complete"] is False,
        "absent native bindings named, never stubbed")

    # -- repeated role instances share the role, never the identity ---------
    req1 = _request("downsell_1", "downsell")
    req2 = _request("downsell_1", "downsell-2")
    n1 = _node("downsell_1", "downsell")
    n2 = _node("downsell_1", "downsell-2", role_instance="downsell_2")
    r1 = RoleWrapper("downsell_1").consume(req1, _result(req1),
                                           delivery_node=n1)
    r2 = RoleWrapper("downsell_1").consume(req2, _result(req2),
                                           delivery_node=n2)
    _ck(r1["role"] == r2["role"] == "downsell_1", "one role across instances")
    _ck(r1["role_instance"] is None and r2["role_instance"] == "downsell_2",
        "instance discriminator carried from the node")
    _ck(r1["logical_id"] != r2["logical_id"], "distinct identity per instance")
    _ck(r1["page_id"] == "downsell" and r2["page_id"] == "downsell-2",
        "distinct page ids preserved")

    # -- whole-dispatch consumption -----------------------------------------
    req_ty = _request("thank_you", "thank-you")
    batch = wrap_all([req, req_ty],
                     {req["request_id"]: res},
                     delivery={"pages": [node, _node("thank_you", "thank-you",
                                                     order=1)]},
                     result_paths={req["request_id"]: "work/result-checkout.json"})
    _ck([r["page_id"] for r in batch["records"]] == ["checkout", "thank-you"],
        "records follow the request order")
    _ck(batch["records"][0]["bound_complete"] is True
        and batch["records"][0]["consumed"] is not None,
        "reported role consumed its actual result")
    ty = batch["records"][1]
    _ck(ty["consumed"] is None and ty["status"] == "not_reported",
        "missing result reported as not_reported, never as done")
    _ck(ty["missing"] == ["result"] and ty["bound_complete"] is False,
        "the gap is named")
    _ck(ty["state"] == "PLANNED", "node state still carried for a gap record")
    _ck(batch["missing_roles"] == ["thank-you"],
        "rollup names the unreported role")
    _ck(batch["bound_complete"] is False,
        "a batch with a gap is incomplete")
    _ck(batch["roles_expected"] == ["checkout", "thank-you"]
        and batch["roles_reported"] == ["checkout"],
        "expected/reported rollups are honest")

    full = wrap_all([req], {req["request_id"]: res},
                    delivery={"pages": [node]})
    _ck(full["bound_complete"] is True and full["missing_roles"] == [],
        "a fully bound batch reports complete")

    refuses(lambda: wrap_all([req], {req["request_id"]: res,
                                     "t1:L1:rev3:upsell_1:nope": res}),
            "a result keyed to no request is refused")
    refuses(lambda: wrap_all([req], [res]),
            "results must be keyed by request_id")
    refuses(lambda: wrap_all([req], {req["request_id"]: sim}),
            "a stub result anywhere in a batch refuses the batch")
    ambiguous = {"pages": [node, _node("checkout", "checkout",
                                       logical_id="pg-checkout-2")]}
    refuses(lambda: wrap_all([req], {req["request_id"]: res},
                             delivery=ambiguous),
            "ambiguous delivery nodes refused")

    # -- seam honesty -------------------------------------------------------
    status = contract_status()
    _ck(isinstance(status["route_adapters_present"], bool),
        "seam reports presence honestly")
    _ck(status["outstanding_integration"] == list(INTEGRATION_OUTSTANDING),
        "outstanding integration is recorded, not papered over")
    if status["route_adapters_present"]:
        _ck(status["contract_source"] == "route_adapters",
            "route_adapters is the node authority when present")
    else:
        _ck(status["contract_source"].endswith("local mirror"),
            "local mirror named while W1B is not on this tree")
        print(f"cross-check: SKIPPED (no route_adapters.py at "
              f"{status['route_adapters_path']}); delivery nodes validated "
              "against the local contract-record mirror on this tree")
    print(f"receipts authority: {status['receipts_authority']}")


if __name__ == "__main__":
    _self_check()
    print(f"OK role_wrappers self-check: {_TALLY} assertions")
