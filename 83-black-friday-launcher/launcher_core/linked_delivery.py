"""F22: linked delivery/access destinations are governed launch resources.

A launch does not end at the thank-you page. Buyers are sent to a members area, a
course, a booking page, a community or a partner site, and an access/login page may
be built by this launch. Before this module those destinations existed only as free
URLs inside offers, so a destination could be described without anyone owning it,
designing it, reviewing it or approving it — and a link could be "readiness".

This module makes every launch-dependent destination one entry of a resource
inventory with an explicit ownership kind:

  * ``new_build``               built by this launch. It needs a registered page role
                                (49-signature-funnel/structure/page_types.json) or a
                                documented adapter to one, and explicit brand, design,
                                copy, review and approval requirements. A page outside
                                the sales graph is not ungoverned HTML.
  * ``existing_client_owned``   a destination the client already owns and references.
  * ``third_party``             a destination a third party owns (course host, community).

An existing or third-party destination carries ownership/reference, access, link,
product, entitlement and fulfillment evidence; it is never rebuilt here and never
forced into a sales-page skeleton.

Resolution is deterministic: the same inputs produce the same ordered resource list
and the same fingerprint, so "which pages does this launch deliver" is answerable and
comparable. Blockers are returned with BOTH a plain client sentence + practical next
step and the operator-level detail, and one blocker never hides another.

A bump stays a checkout component (never a page), and a design-only second downsell
stays distinct from an approved purchase route until that route exists.

Stdlib only. No network, no model, no secret.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .constants import FUNNEL_SKILL_SLUG, skill_path

# The three ownership kinds. Anything else is refused by name.
KIND_NEW_BUILD = "new_build"
KIND_EXISTING = "existing_client_owned"
KIND_THIRD_PARTY = "third_party"
RESOURCE_KINDS = (KIND_NEW_BUILD, KIND_EXISTING, KIND_THIRD_PARTY)
EXTERNAL_KINDS = (KIND_EXISTING, KIND_THIRD_PARTY)

# What a newly built access/login/delivery page must state before it may be built.
NEW_BUILD_REQUIREMENTS = ("brand", "design", "copy", "review", "approval")

# What an existing or third-party destination must prove.
EXTERNAL_EVIDENCE = ("ownership_ref", "access", "link", "product", "entitlement",
                     "fulfillment")

# F08/F05: the four delivery facts stay explicit; a thank-you visit is not fulfillment.
FULFILLMENT_KINDS = ("free_lead_magnet", "purchased_product_or_service",
                     "community_access", "transaction_triggered_fulfillment")
THANK_YOU_IS_NOT_FULFILLMENT = (
    "a thank-you page visit is not proof of fulfillment: the delivery/download/access "
    "event or the native product grant is")

# Owner route law: a bump is a checkout component. It is never a page.
PROHIBITED_NEW_BUILD_PAGES = {
    "bump": "a bump is a checkout component, not a page (doc 02 section 4)",
}
# A second downsell is a design page, not an approved purchase route (yet).
DESIGN_ONLY_PAGES = {
    "downsell_2": ("a second downsell is design-only in this release: it is not an "
                   "approved purchase route until that route is implemented"),
}

PAGE_TYPES_REF = "structure/page_types.json"
RECORD_REL = "launch-resources.json"
RECORD_TYPE = "launcher.linked-delivery.v1"

# stable ordering of kinds in the inventory: what we build first, then what we link to
_KIND_ORDER = {KIND_NEW_BUILD: 0, KIND_EXISTING: 1, KIND_THIRD_PARTY: 2}


class LinkedDeliveryError(Exception):
    """A resource inventory that cannot be resolved. Carries a stable code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def registry_path() -> Path:
    """Skill 49's page-type registry: the one list of registered page roles."""
    return skill_path(FUNNEL_SKILL_SLUG, PAGE_TYPES_REF)


def registered_pages() -> Dict[str, Dict[str, Any]]:
    """page_key -> registered page entry. Unreadable registry is a named refusal.

    A newly built access/login/delivery page must resolve here (item 2): the page
    contract lives in Skill 49's data, not in a second list invented by this module.
    """
    path = registry_path()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LinkedDeliveryError(
            "AF-LAUNCH-LINKED-REGISTRY",
            f"the page-type registry {PAGE_TYPES_REF} cannot be read ({type(exc).__name__}); "
            "a newly built access page cannot be shown to have a registered role") from exc
    pages = doc.get("pages") if isinstance(doc, Mapping) else None
    if doc.get("contract") != "signature-funnel-page-types/v1" or not isinstance(pages, dict):
        raise LinkedDeliveryError(
            "AF-LAUNCH-LINKED-REGISTRY",
            f"{PAGE_TYPES_REF} is not signature-funnel-page-types/v1; a page role cannot be proved")
    return {key: dict(entry) for key, entry in pages.items() if isinstance(entry, Mapping)}


def _blocker(code: str, client_message: str, next_step: str, operator_detail: str,
             resource: str) -> Dict[str, str]:
    """One blocker, stated twice: what the client hears and what the operator sees."""
    return {"code": code, "resource": resource, "client_message": client_message,
            "next_step": next_step, "operator_detail": operator_detail}


def _requirements_problems(entry: Mapping[str, Any], key: str) -> List[Dict[str, str]]:
    requirements = entry.get("requirements")
    out: List[Dict[str, str]] = []
    if not isinstance(requirements, Mapping):
        return [_blocker(
            "AF-LAUNCH-LINKED-REQUIREMENT",
            f"The page {key!r} would be built by this launch, so it needs its brand, "
            "design, copy, review and approval spelled out first.",
            "Record those five facts for it, or point it at a page role this launch already builds.",
            f"new_build {key!r} states no requirements object; expected {list(NEW_BUILD_REQUIREMENTS)}",
            key)]
    for name in NEW_BUILD_REQUIREMENTS:
        if not _nonempty(requirements.get(name)):
            out.append(_blocker(
                "AF-LAUNCH-LINKED-REQUIREMENT",
                f"The page {key!r} is missing its {name} requirement, so it cannot be built as a "
                "governed page yet.",
                f"Record the {name} evidence for {key!r} (a reference, not a promise).",
                f"new_build {key!r} requirement {name!r} is missing or empty",
                key))
    return out


def _evidence_problems(entry: Mapping[str, Any], key: str) -> List[Dict[str, str]]:
    evidence = entry.get("evidence")
    out: List[Dict[str, str]] = []
    if not isinstance(evidence, Mapping):
        return [_blocker(
            "AF-LAUNCH-LINKED-EVIDENCE",
            f"The destination {key!r} already exists, so this launch needs its owner, access, "
            "link, product, entitlement and fulfillment facts before relying on it.",
            "Supply those six facts for it (they are references to records, not free text).",
            f"external {key!r} states no evidence object; expected {list(EXTERNAL_EVIDENCE)}",
            key)]
    for name in EXTERNAL_EVIDENCE:
        value = evidence.get(name)
        if not _nonempty(value):
            out.append(_blocker(
                "AF-LAUNCH-LINKED-EVIDENCE",
                f"The destination {key!r} is missing its {name} evidence.",
                f"Record the {name} for {key!r}.",
                f"external {key!r} evidence {name!r} is missing or empty",
                key))
    return out


def _declared(normalized: Mapping[str, Any]) -> List[Dict[str, Any]]:
    raw = normalized.get("linked_destinations") or []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _derived(normalized: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Owner-confirmed per-offer destinations, recorded from the intake itself.

    These are not declared resources: they are the destinations intake already proved
    (``owner_confirmed`` is required by intake). They are recorded as
    ``existing_client_owned`` with the intake as the ownership reference, so a launch
    that never declares a linked destination still has an honest inventory.
    """
    out: List[Dict[str, Any]] = []
    for offer in normalized.get("offers") or []:
        delivery = offer.get("delivery") or {}
        if not isinstance(delivery, Mapping) or not _nonempty(delivery.get("destination")):
            continue
        if delivery.get("owner_confirmed") is not True:
            continue  # intake already refuses this; never invent ownership
        offer_id = str(offer.get("offer_id"))
        out.append({
            "key": f"offer:{offer_id}",
            "kind": KIND_EXISTING,
            "url": delivery["destination"],
            "evidence": {
                "ownership_ref": f"intake:offers[{offer_id}].delivery.owner_confirmed",
                "access": "answers:access_delivery",
                "link": delivery["destination"],
                "product": f"offer:{offer_id}",
                "entitlement": offer_id.lower(),
                "fulfillment": "recorded in product-delivery.json (delivery kind + mode)",
            },
            "source": "intake",
        })
    return out


def resolve(normalized: Mapping[str, Any],
            page_set: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """The launch's resource inventory, its newest build pages, and every blocker.

    Returns ``{"resources", "pages", "blockers", "client_blockers",
    "operator_diagnostics", "fingerprint"}``. Deterministic: resources are sorted by
    (kind, key), pages by page_key, and the fingerprint is the sha256 of that
    canonical list — the same inputs give the same inventory every time.
    """
    registry = registered_pages()
    declared = _declared(normalized)
    resources: List[Dict[str, Any]] = []
    blockers: List[Dict[str, str]] = []
    seen: Dict[str, int] = {}

    for entry in declared:
        key = entry.get("key")
        if not _nonempty(key):
            blockers.append(_blocker(
                "AF-LAUNCH-LINKED-KEY",
                "One linked destination has no stable name, so it cannot be tracked.",
                "Give it a short key (letters, digits, dot, dash, colon).",
                f"declared resource without a key: {json.dumps(entry, sort_keys=True, default=str)}",
                "<declared>"))
            continue
        if key in seen:
            blockers.append(_blocker(
                "AF-LAUNCH-LINKED-KEY",
                f"The destination {key!r} is listed twice.",
                "Keep one entry per destination.",
                f"duplicate resource key {key!r}",
                key))
            continue
        seen[key] = len(resources)
        kind = entry.get("kind")
        if kind not in RESOURCE_KINDS:
            blockers.append(_blocker(
                "AF-LAUNCH-LINKED-KIND",
                f"One linked destination ({key!r}) is not marked as something we build, "
                "something the client owns, or something a third party owns.",
                "Mark it new_build, existing_client_owned or third_party.",
                f"resource {key!r} kind {kind!r} is not one of {list(RESOURCE_KINDS)}",
                key))
            continue
        resource: Dict[str, Any] = {"key": key, "kind": kind,
                                    "purchase_route": bool(entry.get("purchase_route"))}
        if kind == KIND_NEW_BUILD:
            page_key = entry.get("page_key")
            adapter = entry.get("adapter")
            role_source = None
            if _nonempty(page_key):
                role_source = "registered_page"
            elif isinstance(adapter, Mapping) and _nonempty(adapter.get("role")) \
                    and _nonempty(adapter.get("document_ref")):
                page_key, role_source = adapter["role"], "documented_adapter"
            if page_key is None:
                blockers.append(_blocker(
                    "AF-LAUNCH-LINKED-ROLE",
                    f"The page {key!r} would be built by this launch, but it is not one of the "
                    "page types the funnel knows, and no adapter to one was recorded.",
                    "Point it at a registered page type, or record the documented adapter.",
                    f"new_build {key!r} names no page_key and no adapter {{role, document_ref}}",
                    key))
                continue
            if page_key in PROHIBITED_NEW_BUILD_PAGES:
                blockers.append(_blocker(
                    "AF-LAUNCH-LINKED-BUMP",
                    "A bump is an add-on on the order form, not a page; it cannot be built as one.",
                    "Keep the bump on the order form; build its delivery destination as its own resource.",
                    f"new_build {key!r} claims page {page_key!r}: {PROHIBITED_NEW_BUILD_PAGES[page_key]}",
                    key))
                continue
            if page_key not in registry:
                blockers.append(_blocker(
                    "AF-LAUNCH-LINKED-ROLE",
                    f"The page type {page_key!r} does not exist in this funnel, so {key!r} cannot "
                    "be built from a contract we have.",
                    "Choose one of the registered page types, or record a documented adapter.",
                    f"new_build {key!r} page_key {page_key!r} is absent from {PAGE_TYPES_REF} "
                    f"(registered: {sorted(registry)})",
                    key))
                continue
            registered = registry[page_key]
            resource.update({
                "page_key": page_key,
                "role": registered.get("role"),
                "request_role": registered.get("request_role"),
                "label": registered.get("label"),
                "design_only": bool(registered.get("design_only")),
                "role_source": role_source,
                "requirements": dict(entry.get("requirements") or {})
                if isinstance(entry.get("requirements"), Mapping) else None,
                "adapter": dict(adapter) if isinstance(adapter, Mapping) else None,
            })
            blockers += _requirements_problems(entry, key)
            if page_key in DESIGN_ONLY_PAGES and entry.get("purchase_route"):
                blockers.append(_blocker(
                    "AF-LAUNCH-LINKED-PURCHASE-ROUTE",
                    f"Page {key!r} is listed as a purchase route, but {DESIGN_ONLY_PAGES[page_key]}.",
                    "Keep it as a design page, or leave it out of this launch's purchase route.",
                    f"new_build {key!r} page_key {page_key!r} is design-only but claims purchase_route",
                    key))
        else:
            url = entry.get("url")
            resource.update({"url": url, "evidence": dict(entry.get("evidence") or {})
                             if isinstance(entry.get("evidence"), Mapping) else None,
                             "source": "declared"})
            if not _nonempty(url) or not url.startswith("https://"):
                blockers.append(_blocker(
                    "AF-LAUNCH-LINKED-URL",
                    f"The destination {key!r} needs a real https address.",
                    "Record the https address buyers are actually sent to.",
                    f"external {key!r} url {url!r} is not an https address",
                    key))
            blockers += _evidence_problems(entry, key)
        resources.append(resource)

    # The derived destinations ride along, only when not already declared by key.
    for entry in _derived(normalized):
        if entry["key"] in seen:
            continue
        seen[entry["key"]] = len(resources)
        resources.append({"purchase_route": False, **entry})

    resources.sort(key=lambda r: (_KIND_ORDER.get(str(r.get("kind")), 9), str(r["key"])))
    pages = sorted((r for r in resources if r.get("kind") == KIND_NEW_BUILD),
                   key=lambda r: str(r.get("page_key")))
    inventory_fingerprint = hashlib.sha256(
        json.dumps(resources, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    client_blockers = [b["client_message"] for b in blockers]
    next_steps = [b["next_step"] for b in blockers]
    summary = {
        "state": "blocked" if blockers else "resolved",
        "counts": {"resources": len(resources),
                   "new_build": len(pages),
                   "external": sum(1 for r in resources if r.get("kind") in EXTERNAL_KINDS),
                   "blockers": len(blockers)},
        "client_blockers": client_blockers,
        "next_steps": next_steps,
        "operator_diagnostics": [b["operator_detail"] for b in blockers],
    }
    record = {
        "record_type": RECORD_TYPE,
        "launch_id": normalized.get("launch_id"),
        "tenant_id": normalized.get("tenant_id"),
        "location_id": normalized.get("location_id"),
        "revision": normalized.get("revision"),
        "resources": resources,
        "pages": [{"page_key": p.get("page_key"), "role": p.get("role"),
                   "request_role": p.get("request_role"), "label": p.get("label"),
                   "design_only": p.get("design_only"),
                   "role_source": p.get("role_source")} for p in pages],
        "blockers": blockers,
        "summary": summary,
        "fingerprint": inventory_fingerprint,
        "fulfillment": fulfillment_bindings(normalized),
        "not_fulfillment": THANK_YOU_IS_NOT_FULFILLMENT,
    }
    # page_set is accepted so a caller can prove the inventory against the design page
    # set it already planned; the comparison is recorded, never silently dropped.
    if isinstance(page_set, Mapping):
        planned = sorted(str(p.get("page_key")) for p in (page_set.get("pages") or [])
                         if isinstance(p, Mapping))
        record["design_page_set"] = {
            "pages": planned,
            "new_build_pages": [p.get("page_key") for p in pages],
            "outside_design_page_set": sorted(
                p.get("page_key") for p in pages
                if p.get("page_key") not in set(planned)),
        }
    return record


def blockers(normalized: Mapping[str, Any],
             page_set: Optional[Mapping[str, Any]] = None) -> List[str]:
    """Every blocker as one plain sentence, for a caller that only needs the refusal."""
    record = resolve(normalized, page_set)
    return [f"{b['code']}: {b['operator_detail']}" for b in record["blockers"]]


def assert_resolvable(normalized: Mapping[str, Any],
                      page_set: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Return the record, or raise on the first blocker (stable code preserved)."""
    record = resolve(normalized, page_set)
    if record["blockers"]:
        first = record["blockers"][0]
        raise LinkedDeliveryError(first["code"], first["operator_detail"])
    return record


def fulfillment_bindings(normalized: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """F08/F05: the four delivery facts, explicit per offer, never collapsed.

    ``kind`` is selected from the offer role/price and the client's own delivery
    answer. A free lead magnet (no priced offer in this release), a purchased product
    or service, community access and a transaction-triggered fulfillment are named
    separately; a thank-you visit is never one of them.
    """
    try:
        from . import delivery as delivery_module
        decision = delivery_module.decide(normalized)
    except Exception:  # noqa: BLE001 — an unreadable answers file is recorded, not guessed
        decision = {"kind": None, "state": "unknown", "source": None}
    out: List[Dict[str, Any]] = []
    for offer in normalized.get("offers") or []:
        role = offer.get("role")
        price = offer.get("price") or {}
        amount = price.get("amount_minor") if isinstance(price, Mapping) else None
        delivery_kind = decision.get("kind")
        free = role in ("free", "free_lead", "lead_magnet") or amount == 0
        # A free lead magnet is not triggered by a transaction; every priced offer is.
        kind = "free_lead_magnet" if free else "purchased_product_or_service"
        own = offer.get("delivery") if isinstance(offer.get("delivery"), Mapping) else {}
        # Community access is a real, separate fact. It is only ever asserted from a
        # recorded per-offer answer; absent one it stays unknown (None), never a
        # proven False that would claim the buyer has no community.
        community = own.get("community_access")
        if not isinstance(community, bool):
            community = True if own.get("community") is True else None
        out.append({
            "offer_id": offer.get("offer_id"),
            "kind": kind,
            "delivery_kind": delivery_kind,
            "delivery_kind_state": decision.get("state"),
            "community_access": community,
            "community_access_state": ("recorded" if community is not None
                                       else "not_recorded"),
            "transaction_triggered": not free,
            "evidence": {
                "purchase": "verified purchase snapshot at purchase time (Skill 82)",
                "grant": "native product/entitlement grant recorded by the checkout read-back",
                "excluded": "a thank-you page visit",
            },
            "kinds": list(FULFILLMENT_KINDS),
        })
    return out


def _load_map(map_path: Path) -> Dict[str, Any]:
    try:
        doc = json.loads(Path(map_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LinkedDeliveryError(
            "AF-LAUNCH-FULFILLMENT-MAP",
            f"the fulfillment map {map_path} cannot be read ({type(exc).__name__}); a map "
            "whose bytes cannot be read cannot authorize delivery") from exc
    if not isinstance(doc, dict):
        raise LinkedDeliveryError("AF-LAUNCH-FULFILLMENT-MAP",
                                  f"the fulfillment map {map_path} is not a JSON object")
    return doc


def verify_fulfillment_map(map_path: Path, *,
                           tenant_id: Any, launch_id: Any, revision: Any,
                           granted_entitlements: Sequence[str],
                           recorded_sha256: Optional[str] = None) -> Dict[str, Any]:
    """Bind the S44/F03/F05 fulfillment map to THIS launch before replaying its validator.

    A formerly valid same-path map must not authorize changed delivery facts, so the
    map's current bytes are hashed here (never trusted from a caller's string), and the
    map must carry the current tenant, launch, revision and a version, and may only
    name entitlements this launch actually grants. Returns
    ``{"map", "map_sha256", "version", "entitlements"}`` or raises by name.
    """
    path = Path(map_path)
    doc = _load_map(path)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if recorded_sha256 is not None and recorded_sha256 != actual:
        raise LinkedDeliveryError(
            "AF-LAUNCH-FULFILLMENT-MAP",
            f"the fulfillment map at {path} is {actual}, not the recorded {recorded_sha256}: "
            "a changed map is re-verified, never replayed under the old digest")
    version = doc.get("version") or doc.get("map_version") or doc.get("schema_version")
    if not _nonempty(version):
        raise LinkedDeliveryError(
            "AF-LAUNCH-FULFILLMENT-MAP",
            f"the fulfillment map at {path} carries no version; a map without a version "
            "cannot be evidence of current delivery facts")
    for name, want in (("tenant_id", tenant_id), ("launch_id", launch_id),
                       ("revision", revision)):
        if doc.get(name) != want:
            raise LinkedDeliveryError(
                "AF-LAUNCH-FULFILLMENT-MAP",
                f"the fulfillment map {name} is {doc.get(name)!r}, not this launch's {want!r}; "
                "a map for another tenant, launch or revision never authorizes delivery")
    named = doc.get("entitlements")
    if named is None:
        named = doc.get("entitlement_ids")
    # Skill 44 / Skill 82 use an entitlement-KEYED mapping (id -> state); a list of ids is
    # accepted too. A map that names no entitlement cannot bind a delivery decision.
    if isinstance(named, Mapping):
        named = sorted(str(k) for k in named)
    if not isinstance(named, list) or any(not isinstance(e, str) or not e for e in named):
        raise LinkedDeliveryError(
            "AF-LAUNCH-FULFILLMENT-MAP",
            "the fulfillment map names no entitlement list; exact purchased entitlements are "
            "what a delivery decision is bound to")
    granted = {str(e) for e in granted_entitlements}
    extra = sorted(set(named) - granted)
    if extra:
        raise LinkedDeliveryError(
            "AF-LAUNCH-FULFILLMENT-MAP",
            f"the fulfillment map names entitlement(s) this launch does not grant: {extra}; "
            "a stale map must not unlock delivery for products that were never sold")
    return {"map": doc, "map_sha256": actual, "version": str(version),
            "entitlements": sorted(set(named)), "path": str(path)}


def write_record(record: Mapping[str, Any], out_dir: Path) -> Path:
    """Write ``launch-resources.json`` into the run and return its path."""
    path = Path(out_dir) / RECORD_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
