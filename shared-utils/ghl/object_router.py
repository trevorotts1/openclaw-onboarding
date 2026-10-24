#!/usr/bin/env python3
"""shared-utils/ghl/object_router.py — GHL object-operation routing and
public-client registrations (stream W2, assignment W2-U1).

WHAT THIS IS
------------
The object-operation layer that binds three real sources together and routes
GHL object operations through them.  It invents nothing:

1. W2A's operation contracts — ``shared-utils/ghl/capability_inventory.py``.
   This module CONSUMES them (imports the transport ladder, exact op-class
   grants, readback and restriction rules).  No transport order, tier table,
   failure policy or endpoint is re-declared here.

2. The frozen public registry —
   ``44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/
   public/operations.py`` (one row per public operation id: method, path,
   Version, auth kinds, tenant binding, readback plan).  The public-client
   registrations below bind GHL object operations to those rows.

3. Skill 06's object router surface
   (``06-ghl-install-pages/tools/ghl_object_router.py``) — the rail matrix,
   fallback and failure classification stay there.  NO competing router: this
   module keeps no rail matrix and no failure policy; ordered transport
   selection is exactly ``capability_inventory.select_route`` (Authorized MCP
   first -> documented API adapter -> managed browser), and where a frozen row
   exists the called shape is the row's own method + path.

REGISTRATION STATUS (computed from the real sources, never asserted)
    routable    the frozen row carries the call (public_direct, JSON body,
                location_pit auth, not approval-gated; writes carry a frozen
                readback plan naming a read row) AND the W2A capability
                contract grants the exact op class AND the called shapes agree.
                An adapter-capable public-client path exists under an explicit
                tenant capability gate.  LIVE_PROOF_PENDING: no live call is
                claimed.
    declared    a real frozen row and/or W2A grant exists but the above is not
                fully satisfied.  A named gap with the exact reason.  Never a
                live route by declaration alone.
    incomplete  no frozen row and no W2A grant, or a W2A restriction marks the
                family incomplete.  Reported incomplete, never as done.

Runnable check:
    python3 shared-utils/ghl/object_router.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# The real W2A operation contracts.  Required: this module consumes them and
# never re-declares a capability, ladder or endpoint of its own.
import capability_inventory as contracts  # noqa: E402
from capability_inventory import (  # noqa: E402,F401
    Capability,
    OpClass,
    Support,
    UnsupportedOperation,
    READ_CLASSES,
    WRITE_CLASSES,
    require_route,
    select_route,
    supports,
)

ROUTER_VERSION = "w2-u1.v1"

# ── Frozen public registry discovery (same walk as ghl_public_client) ────────

ENGINE_ROOT_ENV = "GHL_PUBLIC_ENGINE_ROOT"


class RegistryUnavailable(RuntimeError):
    """The frozen public registry cannot be reached.  Never a silent pass."""


_FROZEN: Optional[Dict[str, Any]] = None


def _engine_root() -> str:
    env = os.environ.get(ENGINE_ROOT_ENV)
    if env:
        return env
    walk = _HERE
    for _ in range(8):
        candidate = os.path.join(
            walk, "44-convert-and-flow-operator", "tools", "engine"
        )
        if os.path.isdir(os.path.join(candidate, "cli_anything", "gohighlevel")):
            return candidate
        parent = os.path.dirname(walk)
        if parent == walk:
            break
        walk = parent
    raise RegistryUnavailable(
        "frozen public registry not found (44-convert-and-flow-operator/tools/"
        "engine); a registration is never validated against a missing source"
    )


def frozen_rows() -> Dict[str, Any]:
    """Import the frozen operation registry once. operation_id -> OperationRow."""
    global _FROZEN
    if _FROZEN is not None:
        return _FROZEN
    root = _engine_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from cli_anything.gohighlevel.public.operations import (  # noqa: E402
            OPERATIONS as _REGISTRY,
        )
    except Exception as exc:  # noqa: BLE001
        raise RegistryUnavailable(
            "frozen public registry import failed: %s" % exc
        ) from exc
    _FROZEN = {"registry": _REGISTRY}
    return _FROZEN


def frozen_row(operation_id: str) -> Optional[Any]:
    return frozen_rows()["registry"].get(str(operation_id))


# ── Registration model ──────────────────────────────────────────────────────

ROUTABLE = "routable"
DECLARED = "declared"
INCOMPLETE = "incomplete"

#: Rows whose documented body is multipart/form-data.  The frozen adapter
#: carries JSON bodies only (public/transport.py json.dumps); the exact gap
#: reason is the one ghl_route_gaps.py already records (_JSON_ONLY).
MULTIPART_ROWS: FrozenSet[str] = frozenset({"media.upload"})

#: W2A restrictions that mark a whole family incomplete.  Keys are registration
#: families; values are capability_inventory.RESTRICTIONS ids.  Validated
#: against the real restriction table by validate_registrations().
RESTRICTION_INCOMPLETE_FAMILIES: Dict[str, str] = {
    "products": "products_prices_undocumented_here",
}

#: Named shape adoptions: existing repo evidence that a caller adopted the
#: frozen row's shape for a W2A capability whose route string differs.
SHAPE_ADOPTIONS: Dict[str, str] = {
    "media.files.list": (
        "Skill 06 adopted the frozen media LIST shape "
        "(ghl_object_router.PUBLIC_OPERATION_ROUTES['media'].routed; "
        "ghl_media.list_media with required type): the shape adoption is "
        "existing repo evidence"
    ),
}

#: Divergence and doctrine notes appended verbatim to a registration's reason.
NOTES: Dict[str, str] = {
    "surveys.list": (
        "Skill 06 calls surveys.list today via ghl_public_client.list_surveys; "
        "the W2A catalog has no surveys capability contract yet — provisional, "
        "capability_inventory integration outstanding"
    ),
    "workflows.list": (
        "W2A restriction workflows_rest_read_only: REST read/list support "
        "never implies workflow create/edit"
    ),
    "conversations.messages.send": (
        "W2A constraint: never send live client communications without "
        "binding intent"
    ),
}


@dataclass(frozen=True)
class ObjectOperationRegistration:
    """One GHL object operation bound to its two real contract sources."""

    reg_id: str
    family: str
    op_classes: Tuple[OpClass, ...]
    capability_id: Optional[str]   # W2A capability contract (None = outstanding)
    public_operation_id: Optional[str]  # frozen registry row (None = never invented)

    # computed from the real sources at load; see classify()
    status: str = INCOMPLETE
    reason: str = ""


def _norm_shape(route: str) -> Tuple[str, str]:
    """Normalize "<VERB> <path>" to (VERB, path with {param} -> {})."""
    verb, _, path = str(route).strip().partition(" ")
    return verb.upper(), re.sub(r"\{[^}]*\}", "{}", path)


def _cap_index() -> Dict[str, Capability]:
    return {c.capability_id: c for c in contracts.OPERATIONS}


def _auth_has_location_pit(row: Any) -> bool:
    return any(getattr(k, "value", str(k)) == "location_pit" for k in row.auth_kinds)


def classify(reg: "ObjectOperationRegistration") -> Tuple[str, str]:
    """Compute (status, reason) from the real W2A contract + frozen row.

    Every downgrade names its exact source fact.  A missing source never
    upgrades a status.
    """
    notes = NOTES.get(reg.reg_id, "")
    if reg.public_operation_id is None:
        if reg.family in RESTRICTION_INCOMPLETE_FAMILIES:
            rid = RESTRICTION_INCOMPLETE_FAMILIES[reg.family]
            why = (
                "W2A restriction %s marks this family INCOMPLETE "
                "(reported incomplete, never as done); no frozen row either"
                % rid
            )
            return INCOMPLETE, (why + "; " + notes).strip("; ")
        why = (
            "no frozen public row for this operation (registry freeze "
            "recorded none): a public-client registration is never invented"
        )
        return INCOMPLETE, (why + "; " + notes).strip("; ")

    row = frozen_row(reg.public_operation_id)
    caps = _cap_index()
    cap = caps.get(reg.capability_id) if reg.capability_id else None
    failures: List[str] = []

    if reg.family in RESTRICTION_INCOMPLETE_FAMILIES:
        rid = RESTRICTION_INCOMPLETE_FAMILIES[reg.family]
        why = (
            "W2A restriction %s marks this family INCOMPLETE (no confirmed "
            "products/prices operation in the W2A catalog); reported "
            "incomplete, never as done" % rid
        )
        return INCOMPLETE, (why + "; " + notes).strip("; ")

    if row is None:
        failures.append(
            "frozen row %r is not in the registry (a registration never "
            "invents a row)" % reg.public_operation_id
        )
    else:
        if row.route_class != "public_direct":
            failures.append(
                "frozen row route_class=%s (blocker %s): not a public "
                "adapter path" % (row.route_class, row.blocker)
            )
        if reg.public_operation_id in MULTIPART_ROWS:
            failures.append(
                "multipart body; the frozen adapter carries JSON only "
                "(ghl_route_gaps _JSON_ONLY)"
            )
        if not _auth_has_location_pit(row):
            failures.append(
                "frozen row auth %s excludes location_pit: the PIT "
                "public-client path cannot carry it"
                % (tuple(getattr(k, "value", str(k)) for k in row.auth_kinds),)
            )
        if row.approval_required:
            failures.append(
                "approval-gated row: never an automatic route"
            )
        if row.write:
            plan = row.readback_plan
            if not plan:
                failures.append(
                    "write row declares no frozen readback plan "
                    "(every write refuses before transport without one)"
                )
            else:
                target = frozen_row(plan)
                if target is None:
                    failures.append(
                        "frozen readback plan %r has no row" % plan
                    )
                elif getattr(target, "write", False):
                    failures.append(
                        "frozen readback plan %r targets a write row" % plan
                    )

    if reg.capability_id is None:
        failures.append(
            "no W2A capability contract (capability_inventory has no "
            "%s row): provisional, integration outstanding" % (reg.reg_id,)
        )
    elif cap is None:
        failures.append(
            "W2A capability %r is not in capability_inventory.OPERATIONS"
            % reg.capability_id
        )
    else:
        for oc in reg.op_classes:
            if not supports(cap, oc):
                failures.append(
                    "W2A capability %r does not grant op class %s "
                    "(read/list never implies create/edit)"
                    % (reg.capability_id, oc.value)
                )
        if row is not None and reg.reg_id not in SHAPE_ADOPTIONS:
            cap_shape = _norm_shape(cap.route)
            row_shape = (str(row.method).upper(),
                         re.sub(r"\{[^}]*\}", "{}", str(row.path_template)))
            if cap_shape != row_shape:
                failures.append(
                    "called shapes disagree: W2A contract route %r vs frozen "
                    "row %r — unreconciled, never routed on a contradiction"
                    % (cap.route, "%s %s" % (row.method, row.path_template))
                )

    if failures:
        return DECLARED, "; ".join(failures) + (("; " + notes) if notes else "")

    plan = getattr(row, "readback_plan", None)
    proof = ("; frozen readback %s" % plan) if plan else ""
    return ROUTABLE, (
        "frozen row carries the call (%s %s, %s, location_pit%s); W2A "
        "contract %r grants %s; LIVE_PROOF_PENDING — no live call is claimed"
        % (
            row.method,
            row.path_template,
            row.version,
            proof,
            reg.capability_id,
            "+".join(oc.value for oc in reg.op_classes),
        )
        + (("; " + notes) if notes else "")
    )


# ── The extended registration table (GHL object operations) ─────────────────
# (reg_id, family, op_classes, capability_id, public_operation_id)
# capability_id binds a W2A capability contract; public_operation_id binds a
# frozen registry row.  Status and reason are COMPUTED from those sources.

_RAW: Tuple[Tuple[str, str, Tuple[OpClass, ...], Optional[str], Optional[str]], ...] = (
    # contacts
    ("contacts.search", "contacts", (OpClass.READ,), "contacts.search", "contacts.search"),
    ("contacts.get", "contacts", (OpClass.READ,), "contacts.get", "contacts.get"),
    ("contacts.list", "contacts", (OpClass.LIST,), "contacts.list", "contacts.list"),
    ("contacts.create", "contacts", (OpClass.CREATE,), "contacts.create", "contacts.create"),
    ("contacts.upsert", "contacts", (OpClass.CREATE, OpClass.EDIT), "contacts.upsert", "contacts.upsert"),
    ("contacts.update", "contacts", (OpClass.EDIT,), "contacts.update", "contacts.update"),
    ("contacts.delete", "contacts", (OpClass.DELETE,), None, "contacts.delete"),
    ("contacts.tags.add", "contacts", (OpClass.EDIT,), "contacts.add_tags", "contacts.tags.add"),
    ("contacts.tags.remove", "contacts", (OpClass.DELETE,), None, "contacts.tags.remove"),
    ("contacts.lookup", "contacts", (OpClass.READ,), None, "contacts.lookup"),
    # custom fields / values / tags
    ("custom_fields.list", "custom_fields", (OpClass.LIST,), None, "custom_fields.list"),
    ("custom_fields.get", "custom_fields", (OpClass.READ,), None, "custom_fields.get"),
    ("custom_fields.create", "custom_fields", (OpClass.CREATE,), None, "custom_fields.create"),
    ("custom_values.list", "custom_values", (OpClass.LIST,), None, "custom_values.list"),
    ("custom_values.create", "custom_values", (OpClass.CREATE,), None, "custom_values.create"),
    ("custom_values.update", "custom_values", (OpClass.EDIT,), None, "custom_values.update"),
    ("tags.list", "tags", (OpClass.LIST,), None, "tags.list"),
    ("tags.create", "tags", (OpClass.CREATE,), None, "tags.create"),
    # opportunities / pipelines
    ("opportunities.search", "opportunities", (OpClass.LIST,), "opportunities.search", "opportunities.search"),
    ("opportunities.get", "opportunities", (OpClass.READ,), None, "opportunities.get"),
    ("opportunities.create", "opportunities", (OpClass.CREATE,), "opportunities.create", "opportunities.create"),
    ("opportunities.update", "opportunities", (OpClass.EDIT,), "opportunities.update", "opportunities.update"),
    ("opportunities.delete", "opportunities", (OpClass.DELETE,), None, "opportunities.delete"),
    ("pipelines.list", "pipelines", (OpClass.LIST,), None, "pipelines.list"),
    ("pipelines.get", "pipelines", (OpClass.READ,), None, "pipelines.get"),
    ("pipelines.create", "pipelines", (OpClass.CREATE,), None, "pipelines.create"),
    ("pipelines.update", "pipelines", (OpClass.EDIT,), None, "pipelines.update"),
    ("pipelines.delete", "pipelines", (OpClass.DELETE,), None, "pipelines.delete"),
    # conversations
    ("conversations.messages.send", "conversations", (OpClass.EXECUTE,), "conversations.send_message", "conversations.messages.send"),
    ("conversations.search", "conversations", (OpClass.LIST,), None, "conversations.search"),
    # calendars
    ("calendars.list", "calendars", (OpClass.LIST,), "calendars.list", "calendars.list"),
    ("calendars.get", "calendars", (OpClass.READ,), None, "calendars.get"),
    ("calendars.create", "calendars", (OpClass.CREATE,), "calendars.create", "calendars.create"),
    ("calendars.free_slots", "calendars", (OpClass.READ,), "calendars.free_slots", "calendars.free_slots"),
    ("calendars.events.list", "calendars", (OpClass.LIST,), "calendars.events_list", "calendars.events.list"),
    ("appointments.create", "calendars", (OpClass.CREATE,), "calendars.book_appointment", "appointments.create"),
    ("events.delete", "calendars", (OpClass.DELETE,), None, "events.delete"),
    # workflows (REST read-only per W2A restriction workflows_rest_read_only)
    ("workflows.list", "workflows", (OpClass.LIST,), "workflows.get", "workflows.list"),
    ("workflows.enroll", "workflows", (OpClass.EXECUTE,), "workflows.enroll_contact", "workflows.enroll"),
    ("workflows.remove", "workflows", (OpClass.EXECUTE,), "workflows.unenroll_contact", "workflows.remove"),
    # locations
    ("locations.get", "locations", (OpClass.READ,), "locations.get", "locations.get"),
    ("locations.search", "locations", (OpClass.LIST,), "locations.search", None),
    # media / funnels / forms / surveys / products (extension of the existing
    # skill-06 registration surface, bound to the same frozen rows)
    ("media.files.list", "media", (OpClass.LIST,), "medias.list", "media.files.list"),
    ("media.upload", "media", (OpClass.CREATE,), "medias.upload", "media.upload"),
    ("funnels.list", "funnels", (OpClass.LIST,), "funnels.list", "funnels.list"),
    ("funnels.pages.list", "funnels", (OpClass.LIST,), "funnels.pages_list", "funnels.pages.list"),
    ("funnels.pages.count", "funnels", (OpClass.READ,), "funnels.pages_count", "funnels.pages.count"),
    ("forms.list", "forms", (OpClass.LIST,), None, "forms.list"),
    ("surveys.list", "surveys", (OpClass.LIST,), None, "surveys.list"),
    ("products.list", "products", (OpClass.LIST,), None, "products.list"),
    ("products.create", "products", (OpClass.CREATE,), None, "products.create"),
    ("products.prices.list", "products", (OpClass.LIST,), None, "products.prices.list"),
    ("products.prices.create", "products", (OpClass.CREATE,), None, "products.prices.create"),
)


def _build() -> Tuple[ObjectOperationRegistration, ...]:
    out: List[ObjectOperationRegistration] = []
    for reg_id, family, ocs, cap_id, pub_id in _RAW:
        reg = ObjectOperationRegistration(
            reg_id=reg_id, family=family, op_classes=ocs,
            capability_id=cap_id, public_operation_id=pub_id,
        )
        status, reason = classify(reg)
        out.append(ObjectOperationRegistration(
            reg_id=reg_id, family=family, op_classes=ocs,
            capability_id=cap_id, public_operation_id=pub_id,
            status=status, reason=reason,
        ))
    return tuple(out)


REGISTRATIONS: Tuple[ObjectOperationRegistration, ...] = _build()
_BY_ID: Dict[str, ObjectOperationRegistration] = {r.reg_id: r for r in REGISTRATIONS}


def registration(reg_id: str) -> ObjectOperationRegistration:
    """One registration by id (raises KeyError on unknown — never invented)."""
    return _BY_ID[str(reg_id)]


def object_router_registrations() -> Dict[str, Dict[str, List[str]]]:
    """Family view, the shape the skill-06 PUBLIC_OPERATION_ROUTES uses,
    extended for GHL object operations: routed/declared/incomplete id lists."""
    out: Dict[str, Dict[str, List[str]]] = {}
    for r in REGISTRATIONS:
        bucket = out.setdefault(
            r.family, {ROUTABLE: [], DECLARED: [], INCOMPLETE: []}
        )
        bucket[r.status].append(r.reg_id)
    for bucket in out.values():
        for key in bucket:
            bucket[key].sort()
    return dict(sorted(out.items()))


def public_client_registrations() -> List[Dict[str, Any]]:
    """Public-client registration rows for adoption (ghl_public_client surface).

    Every call-shape field is read from the frozen row — never typed here.
    """
    rows: List[Dict[str, Any]] = []
    for r in REGISTRATIONS:
        row = frozen_row(r.public_operation_id) if r.public_operation_id else None
        entry: Dict[str, Any] = {
            "operation_id": r.public_operation_id,
            "reg_id": r.reg_id,
            "family": r.family,
            "op_classes": tuple(oc.value for oc in r.op_classes),
            "capability_id": r.capability_id,
            "status": r.status,
            "reason": r.reason,
        }
        if row is not None:
            entry.update({
                "method": row.method,
                "path_template": row.path_template,
                "version": row.version,
                "tenant_binding": row.tenant_binding,
                "write": bool(row.write),
                "approval_required": bool(row.approval_required),
                "readback_plan": row.readback_plan,
                "auth_kinds": tuple(getattr(k, "value", str(k)) for k in row.auth_kinds),
                "blocker": row.blocker,
                "doc_url": row.doc_url,
            })
        rows.append(entry)
    return rows


# ── Routing: ordered transports from the W2A contracts (no local ordering) ──

@dataclass(frozen=True)
class RouteStep:
    capability: Capability
    transport: Any
    public_operation_id: Optional[str]
    public_status: Optional[str]


def route_operation(
    op_class: OpClass,
    *,
    resource: Optional[str] = None,
    surface: Optional[str] = None,
    dynamic_confirmed: bool = False,
) -> List[RouteStep]:
    """Ordered candidate transports for one op class, straight from
    capability_inventory.select_route (Authorized MCP -> API -> browser).

    Each step carries the public-client binding when one is registered.  The
    plan order is the W2A ladder — this module never re-orders it.
    """
    candidates = select_route(
        op_class, resource=resource, surface=surface,
        dynamic_confirmed=dynamic_confirmed,
    )
    plan: List[RouteStep] = []
    for cap in candidates:
        pub_id = None
        pub_status = None
        for r in REGISTRATIONS:
            if r.capability_id == cap.capability_id and op_class in r.op_classes:
                pub_id = r.public_operation_id
                pub_status = r.status
                break
        plan.append(RouteStep(cap, cap.transport, pub_id, pub_status))
    return plan


# ── Validation ──────────────────────────────────────────────────────────────

def validate_registrations() -> List[str]:
    """Invariant violations across the three real sources.  [] == honest."""
    problems: List[str] = []
    caps = _cap_index()
    seen: set = set()
    for r in REGISTRATIONS:
        if r.reg_id in seen:
            problems.append("duplicate registration id %s" % r.reg_id)
        seen.add(r.reg_id)
        if not r.op_classes:
            problems.append("%s: no op classes" % r.reg_id)
        if r.capability_id is not None and r.capability_id not in caps:
            problems.append(
                "%s: capability %r is not in capability_inventory.OPERATIONS"
                % (r.reg_id, r.capability_id)
            )
        if r.public_operation_id is not None:
            try:
                row = frozen_row(r.public_operation_id)
            except RegistryUnavailable as exc:
                problems.append(str(exc))
                row = None
            if row is None:
                problems.append(
                    "%s: frozen row %r does not exist (never invented)"
                    % (r.reg_id, r.public_operation_id)
                )
            elif r.status == ROUTABLE:
                # independent re-derivation of the routable bar
                ok = (
                    row.route_class == "public_direct"
                    and r.public_operation_id not in MULTIPART_ROWS
                    and _auth_has_location_pit(row)
                    and not row.approval_required
                    and (
                        not row.write
                        or (
                            row.readback_plan
                            and frozen_row(row.readback_plan) is not None
                            and not getattr(frozen_row(row.readback_plan), "write", True)
                        )
                    )
                )
                if not ok:
                    problems.append(
                        "%s: claims routable but the frozen row fails the "
                        "adapter-carryable bar" % r.reg_id
                    )
        elif r.status != INCOMPLETE:
            problems.append(
                "%s: no frozen row can never be more than incomplete" % r.reg_id
            )
        # status/price must be what the real sources compute
        want_status, want_reason = classify(r)
        if (r.status, r.reason) != (want_status, want_reason):
            problems.append(
                "%s: stored classification drifts from the source-computed one"
                % r.reg_id
            )
    for family, rid in RESTRICTION_INCOMPLETE_FAMILIES.items():
        if rid not in contracts.RESTRICTIONS:
            problems.append(
                "restriction %r (family %s) is not in capability_inventory."
                "RESTRICTIONS" % (rid, family)
            )
        for r in REGISTRATIONS:
            if r.family == family and r.status != INCOMPLETE:
                problems.append(
                    "%s: restricted family %s must be incomplete"
                    % (r.reg_id, family)
                )
    return problems


# ── Assert-based self-check (runnable: python3 shared-utils/ghl/object_router.py)

def self_check() -> None:
    # 1. Registrations are honest against the real sources.
    problems = validate_registrations()
    assert not problems, "registration violations: %s" % problems

    # 2. No competing ordering: the plan order is capability_inventory's.
    for oc, res in ((OpClass.READ, "contacts"), (OpClass.LIST, "calendars"),
                    (OpClass.LIST, "workflows"), (OpClass.CREATE, "contacts")):
        mine = [s.capability.capability_id for s in route_operation(oc, resource=res)]
        theirs = [c.capability_id for c in select_route(oc, resource=res)]
        assert mine == theirs, (oc, res, mine, theirs)

    # 3. Read/list never implies create/edit (W2A no_implication, consumed).
    for write in (OpClass.CREATE, OpClass.EDIT, OpClass.DELETE):
        assert select_route(write, resource="workflows",
                            dynamic_confirmed=False) == [], write
    for r in REGISTRATIONS:
        if r.family == "workflows":
            # EXECUTE here is contact enrollment only (W2A constraint), never
            # workflow create/edit/delete.
            assert not (set(r.op_classes) & {OpClass.CREATE, OpClass.EDIT,
                                             OpClass.DELETE}), r.reg_id

    # 4. Reads never route through the managed browser (W2A read_build_routing).
    for op in (OpClass.READ, OpClass.LIST):
        for step in route_operation(op, dynamic_confirmed=True):
            assert step.transport is not contracts.Transport.MANAGED_BROWSER, step

    # 5. products/prices: reported INCOMPLETE, never as done, never invented.
    for r in REGISTRATIONS:
        if r.family == "products":
            assert r.status == INCOMPLETE and "incomplete" in r.reason, r.reg_id

    # 6. The one shape adoption is the media LIST; everything routable agrees.
    for r in REGISTRATIONS:
        if r.status == ROUTABLE and r.public_operation_id:
            row = frozen_row(r.public_operation_id)
            if r.reg_id not in SHAPE_ADOPTIONS:
                cap = _cap_index()[r.capability_id]
                assert _norm_shape(cap.route) == (
                    str(row.method).upper(),
                    re.sub(r"\{[^}]*\}", "{}", str(row.path_template)),
                ), r.reg_id

    # 7. Every routed write carries a frozen readback plan naming a read row.
    for r in REGISTRATIONS:
        row = frozen_row(r.public_operation_id) if r.public_operation_id else None
        if r.status == ROUTABLE and row is not None and row.write:
            target = frozen_row(row.readback_plan)
            assert target is not None and not getattr(target, "write", True), r.reg_id

    # 8. No invented ids: every binding resolves in its own source.
    for r in REGISTRATIONS:
        if r.capability_id:
            assert r.capability_id in _cap_index(), r.reg_id
        if r.public_operation_id:
            assert frozen_row(r.public_operation_id) is not None, r.reg_id

    # 9. NEGATIVE CONTROLS — injected defects must be caught.
    bad = ObjectOperationRegistration(
        reg_id="neg.unknown_cap", family="contacts", op_classes=(OpClass.READ,),
        capability_id="contacts.nonexistent", public_operation_id="contacts.get",
    )
    problems = _validate_with(bad)
    assert any("contacts.nonexistent" in p for p in problems), problems

    bad_row = ObjectOperationRegistration(
        reg_id="neg.unknown_row", family="contacts", op_classes=(OpClass.READ,),
        capability_id="contacts.get", public_operation_id="contacts.nope",
    )
    problems = _validate_with(bad_row)
    assert any("contacts.nope" in p for p in problems), problems

    # classify() must not upgrade a write with no frozen readback plan
    status, reason = classify(ObjectOperationRegistration(
        reg_id="contacts.create", family="contacts", op_classes=(OpClass.CREATE,),
        capability_id="contacts.create", public_operation_id="contacts.create",
    ))
    assert status == DECLARED and "readback" in reason, (status, reason)

    # a restricted family never routes even with a real frozen row
    status, reason = classify(ObjectOperationRegistration(
        reg_id="products.list", family="products", op_classes=(OpClass.LIST,),
        capability_id=None, public_operation_id="products.list",
    ))
    assert status == INCOMPLETE and "INCOMPLETE" in reason, (status, reason)

    # 10. The extended table covers the GHL object families.
    families = {r.family for r in REGISTRATIONS}
    for required in ("contacts", "custom_fields", "custom_values", "tags",
                     "opportunities", "pipelines", "conversations", "calendars",
                     "workflows", "locations"):
        assert required in families, required
    assert any(r.status == ROUTABLE for r in REGISTRATIONS), "no routable rows"


def _validate_with(extra: ObjectOperationRegistration) -> List[str]:
    """validate_registrations over REGISTRATIONS + one injected row."""
    global REGISTRATIONS
    saved = REGISTRATIONS
    try:
        REGISTRATIONS = saved + (extra,)
        return validate_registrations()
    finally:
        REGISTRATIONS = saved


# ── CLI ─────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--registrations":
        print(json.dumps(public_client_registrations(), indent=2, default=str))
        return 0
    if args and args[0] == "--families":
        print(json.dumps(object_router_registrations(), indent=2))
        return 0
    try:
        self_check()
    except RegistryUnavailable as exc:
        print("[object_router] INCOMPLETE: %s" % exc, file=sys.stderr)
        return 2
    counts: Dict[str, int] = {}
    for r in REGISTRATIONS:
        counts[r.status] = counts.get(r.status, 0) + 1
    print("object_router self-check: PASS")
    print("  registrations: %d" % len(REGISTRATIONS))
    print("  status counts: %s" % dict(sorted(counts.items())))
    routable = sorted(r.reg_id for r in REGISTRATIONS if r.status == ROUTABLE)
    print("  routable: %s" % ", ".join(routable))
    return 0


if __name__ == "__main__":
    sys.exit(main())
