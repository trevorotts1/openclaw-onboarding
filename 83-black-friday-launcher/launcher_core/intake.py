"""Validated launcher intake. Fail-closed; never invents a commercial fact.

Required inputs are limited to what the pages genuinely cannot be built without.
Nothing commercial defaults. A missing price is an error, never a free offer and
never zero. Prices, levels and entitlements must be SUPPLIED or explicitly
marked UNKNOWN; a defaulted commercial fact fails the build by name.

The entitlement attestation is verified against the declaration the skill
carries. Unknown or unqualified entitlement state fails closed.
"""

from __future__ import annotations

from typing import Any, Dict, List

from . import entitlement, image_plan
from .constants import (
    JOURNEY_MODES,
    OFFER_RELATION_KEYS,
    OFFER_ROLES,
    SCHEMA_VERSION,
)

# field -> why the pages cannot be built without it. No product decision here.
REQUIRED_FIELDS = {
    "schema_version": "launch record schema version",
    "tenant_id": "route graph and page requests are tenant-scoped",
    "location_id": "route graph and page requests are location-scoped",
    "launch_id": "every page request names the launch",
    "revision": "stale-revision detection at checkout",
    "journey_mode": "decides whether a product_selection page exists; defaulting would invent an offer shape",
    "brand": "page-request requires brand ref + hash; a page cannot be styled without it",
    "copy_profile": "page-request requires it; copy cannot be generated without it",
    "approval": "contract section 9 approval reference + subject hash before any build",
    "offers": "checkout cannot bind a price it was never given; inventing one is forbidden",
    "entitlement_attestation": "no build without an attested entitlement basis; unknown state fails closed",
}

# field -> operational default only. Nothing here changes an offer, a level,
# a price, an entitlement, or the route shape.
PERMITTED_DEFAULTS = {
    "test_only": ("test_only", True, "offline build; a live run must supply false"),
    "allowed_write_target": ("allowed_write_target", "local_only",
                             "publication carries its own approval type"),
    "locale": ("locale", "en", "presentation locale, not a commercial fact"),
    "automation_execution": ("automation_execution", "not_requested",
                             "contract section 7: a JSON file does not execute a workflow"),
}

# Optional intake blocks. image_plan carries the picture choices (style, brand file, owner, spend
# cap, provider); it is shape-checked here and resolved, with flagged defaults, only at dispatch.
OPTIONAL_FIELDS = ("image_plan",)

OFFER_REQUIRED = ("offer_id", "name", "role", "price")
OFFER_OPTIONAL = ("level", "relationships")
PRICE_REQUIRED = ("amount_minor", "currency")

# Provenance prefixes that may NEVER be a default. A commercial fact is either
# supplied or explicitly unknown.
COMMERCIAL_ROOTS = ("offers", "entitlement_attestation", "level",
                    "cross_sales", "relationships")


class IntakeError(Exception):
    """A launch intake that cannot be built. Carries a stable autofail code."""

    def __init__(self, code: str, field: str, detail: str) -> None:
        super().__init__(f"{code}: {field}: {detail}")
        self.code = code
        self.field = field
        self.detail = detail


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _fail(code: str, field: str, detail: str) -> None:
    raise IntakeError(code, field, detail)


def _validate_level(index: int, offer: Dict[str, Any]) -> Dict[str, Any]:
    """A level is SUPPLIED (name + deliverables) or explicitly UNKNOWN. Never a default."""
    field = f"offers[{index}].level"
    level = offer.get("level")
    if level is None:
        return {"state": "unknown"}
    if not isinstance(level, dict):
        _fail("AF-LAUNCH-INTAKE-LEVEL", field, "must be an object")
    state = level.get("state")
    if state == "unknown":
        if set(level) != {"state"}:
            _fail("AF-LAUNCH-INTAKE-LEVEL", field,
                  f"an unknown level carries only 'state', got {sorted(level)!r}")
        return {"state": "unknown"}
    if state != "supplied":
        _fail("AF-LAUNCH-INTAKE-LEVEL", field,
              "state must be 'supplied' or 'unknown'; a level is never defaulted")
    extra = set(level) - {"state", "name", "deliverables"}
    if extra:
        _fail("AF-LAUNCH-INTAKE-LEVEL", field, f"undeclared field(s) {sorted(extra)!r}")
    if not _nonempty_str(level.get("name")):
        _fail("AF-LAUNCH-INTAKE-LEVEL", f"{field}.name", "must be a non-empty string")
    deliverables = level.get("deliverables")
    if not isinstance(deliverables, list) or not deliverables:
        _fail("AF-LAUNCH-INTAKE-LEVEL", f"{field}.deliverables",
              "at least one supplied deliverable is required")
    clean: List[str] = []
    for i, item in enumerate(deliverables):
        if not _nonempty_str(item):
            _fail("AF-LAUNCH-INTAKE-LEVEL", f"{field}.deliverables[{i}]",
                  "must be a non-empty string")
        clean.append(item.strip())
    return {"state": "supplied", "name": level["name"].strip(), "deliverables": clean}


def _validate_relationships(index: int, offer: Dict[str, Any]) -> Dict[str, List[str]]:
    """Cross-sale surface: offers relate to offers. Never a route node."""
    field = f"offers[{index}].relationships"
    raw = offer.get("relationships")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        _fail("AF-LAUNCH-INTAKE-RELATION", field, "must be an object")
    extra = set(raw) - set(OFFER_RELATION_KEYS)
    if extra:
        _fail("AF-LAUNCH-INTAKE-RELATION", field,
              f"undeclared relation(s) {sorted(extra)!r}; "
              f"the model is {list(OFFER_RELATION_KEYS)!r}")
    clean: Dict[str, List[str]] = {}
    for key, values in raw.items():
        if not isinstance(values, list) or not values:
            _fail("AF-LAUNCH-INTAKE-RELATION", f"{field}.{key}",
                  "must be a non-empty list of offer ids")
        seen: List[str] = []
        for i, value in enumerate(values):
            if not _nonempty_str(value):
                _fail("AF-LAUNCH-INTAKE-RELATION", f"{field}.{key}[{i}]",
                      "must be a non-empty string")
            if value.strip() in seen:
                _fail("AF-LAUNCH-INTAKE-RELATION", f"{field}.{key}",
                      f"duplicate target {value.strip()!r}")
            seen.append(value.strip())
        clean[key] = seen
    return clean


def _validate_offer(index: int, offer: Any) -> Dict[str, Any]:
    field = f"offers[{index}]"
    if not isinstance(offer, dict):
        _fail("AF-LAUNCH-INTAKE-OFFER", field, "must be an object")
    for key in OFFER_REQUIRED:
        if key not in offer:
            _fail("AF-LAUNCH-INTAKE-OFFER", f"{field}.{key}", "missing")
    for key in ("offer_id", "name"):
        if not _nonempty_str(offer[key]):
            _fail("AF-LAUNCH-INTAKE-OFFER", f"{field}.{key}", "must be a non-empty string")
    role = offer["role"]
    if role not in OFFER_ROLES:
        _fail("AF-LAUNCH-INTAKE-OFFER", f"{field}.role", f"not one of {OFFER_ROLES!r}")
    price = offer["price"]
    if not isinstance(price, dict):
        _fail("AF-LAUNCH-INTAKE-PRICE", f"{field}.price", "must be an object")
    for key in PRICE_REQUIRED:
        if key not in price:
            _fail("AF-LAUNCH-INTAKE-PRICE", f"{field}.price.{key}", "missing; unknown is not zero")
    amount = price["amount_minor"]
    if isinstance(amount, bool) or not isinstance(amount, int):
        _fail("AF-LAUNCH-INTAKE-PRICE", f"{field}.price.amount_minor",
              "must be integer minor units, not floating point")
    if amount <= 0:
        _fail("AF-LAUNCH-INTAKE-PRICE", f"{field}.price.amount_minor",
              "must be positive; an unknown or zero price may not be invented here")
    currency = price["currency"]
    if not _nonempty_str(currency) or len(currency) != 3 or not currency.isupper():
        _fail("AF-LAUNCH-INTAKE-PRICE", f"{field}.price.currency",
              "must be a 3-letter uppercase currency code")
    extra = set(offer) - set(OFFER_REQUIRED) - set(OFFER_OPTIONAL)
    if extra:
        _fail("AF-LAUNCH-INTAKE-UNKNOWN", field,
              f"undeclared offer field(s) {sorted(extra)!r}; add them to intake.py deliberately")
    return {
        "offer_id": offer["offer_id"].strip(),
        "name": offer["name"].strip(),
        "role": role,
        "price": {"amount_minor": amount, "currency": currency},
        "level": _validate_level(index, offer),
        "relationships": _validate_relationships(index, offer),
    }


def _check_relationship_targets(offers: List[Dict[str, Any]]) -> None:
    known = {o["offer_id"] for o in offers}
    for offer in offers:
        for key, targets in offer["relationships"].items():
            for target in targets:
                if target == offer["offer_id"]:
                    _fail("AF-LAUNCH-INTAKE-RELATION",
                          f"offers[{offer['offer_id']}].relationships.{key}",
                          "an offer cannot relate to itself")
                if target not in known:
                    _fail("AF-LAUNCH-INTAKE-RELATION",
                          f"offers[{offer['offer_id']}].relationships.{key}",
                          f"unknown offer id {target!r}")


def assert_no_commercial_defaults(normalized: Dict[str, Any]) -> None:
    """Fail if a commercial fact arrived by default instead of supplied/unknown."""
    for field, provenance in (normalized.get("provenance") or {}).items():
        root = field.split("[", 1)[0].split(".", 1)[0]
        if root not in COMMERCIAL_ROOTS:
            continue
        if isinstance(provenance, str) and provenance.startswith("default:"):
            _fail("AF-LAUNCH-OFFER-DEFAULTED", field,
                  "a price, level or entitlement may never be defaulted; "
                  "supply it or mark it unknown")
        if provenance not in ("supplied", "unknown", "attested"):
            _fail("AF-LAUNCH-OFFER-DEFAULTED", field,
                  f"provenance {provenance!r} is not supplied/unknown/attested")


def validate(payload: Any) -> Dict[str, Any]:
    """Return a normalized launch intake or raise IntakeError. Fail-closed."""
    if not isinstance(payload, dict):
        _fail("AF-LAUNCH-INTAKE-SHAPE", "<root>", "intake must be a JSON object")

    for key in REQUIRED_FIELDS:
        if key not in payload:
            _fail("AF-LAUNCH-INTAKE-MISSING", key, "required; no default exists")

    if payload["schema_version"] != SCHEMA_VERSION:
        _fail("AF-LAUNCH-INTAKE-SCHEMA", "schema_version", f"must be {SCHEMA_VERSION!r}")

    for key in ("tenant_id", "location_id", "launch_id"):
        if not _nonempty_str(payload[key]):
            _fail("AF-LAUNCH-INTAKE-MISSING", key, "must be a non-empty string")

    revision = payload["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        _fail("AF-LAUNCH-INTAKE-SHAPE", "revision", "must be an integer >= 1")

    mode = payload["journey_mode"]
    if mode not in JOURNEY_MODES:
        if mode == "free_entry":
            _fail("AF-LAUNCH-INTAKE-MODE",
                  "journey_mode",
                  "free_entry is an approval-gated contract mode not implemented in this build; "
                  "it may not be reached by omission or default")
        _fail("AF-LAUNCH-INTAKE-MODE", "journey_mode", f"not one of {JOURNEY_MODES!r}")

    for group, keys in (("brand", ("ref", "hash")), ("approval", ("ref", "hash"))):
        value = payload[group]
        if not isinstance(value, dict):
            _fail("AF-LAUNCH-INTAKE-SHAPE", group, "must be an object")
        for key in keys:
            if not _nonempty_str(value.get(key)):
                _fail("AF-LAUNCH-INTAKE-MISSING", f"{group}.{key}", "must be a non-empty string")
        extra = set(value) - set(keys)
        if extra:
            _fail("AF-LAUNCH-INTAKE-UNKNOWN", group, f"undeclared field(s) {sorted(extra)!r}")

    if not _nonempty_str(payload["copy_profile"]):
        _fail("AF-LAUNCH-INTAKE-MISSING", "copy_profile", "must be a non-empty string")

    offers = payload["offers"]
    if not isinstance(offers, list) or not offers:
        _fail("AF-LAUNCH-INTAKE-OFFER", "offers", "at least one offer is required")
    clean_offers: List[Dict[str, Any]] = [_validate_offer(i, o) for i, o in enumerate(offers)]
    _check_relationship_targets(clean_offers)

    mains = [o for o in clean_offers if o["role"] == "main"]
    if mode == "single_simple" and len(mains) != 1:
        _fail("AF-LAUNCH-INTAKE-OFFER", "offers",
              f"single_simple needs exactly one main offer, found {len(mains)}")
    if mode in ("multiple_options", "folded_levels") and len(mains) < 2:
        _fail("AF-LAUNCH-INTAKE-OFFER", "offers",
              f"{mode} needs at least two distinct main offers, found {len(mains)}")
    if mode == "folded_levels":
        if len({o["offer_id"] for o in mains}) != len(mains):
            _fail("AF-LAUNCH-INTAKE-OFFER", "offers",
                  "folded_levels needs distinct levels, never one offer relabelled")
        if len({o["price"]["amount_minor"] for o in mains}) != len(mains):
            _fail("AF-LAUNCH-INTAKE-OFFER", "offers",
                  "folded_levels needs distinct levels; identical prices imply one offer")

    for role in ("bump", "upsell_1", "downsell_1", "upsell_2"):
        count = sum(1 for o in clean_offers if o["role"] == role)
        if count > 1:
            _fail("AF-LAUNCH-INTAKE-OFFER", "offers", f"{role} may appear at most once, found {count}")

    roles = {o["role"] for o in clean_offers}
    if "upsell_2" in roles and not ({"upsell_1", "downsell_1"} & roles):
        _fail("AF-LAUNCH-INTAKE-ROUTE", "offers",
              "upsell_2 requires a successful upsell_1 or downsell_1 purchase in this profile")
    if "upsell_1" not in roles and ({"downsell_1", "upsell_2"} & roles):
        _fail("AF-LAUNCH-INTAKE-ROUTE", "offers",
              "when upsell_1 is disabled, downsell_1 and upsell_2 cannot remain enabled")

    try:
        entitled = entitlement.gate(payload["entitlement_attestation"])
    except entitlement.EntitlementError as exc:
        raise IntakeError(exc.code, exc.field, exc.detail) from exc

    known = set(REQUIRED_FIELDS) | set(PERMITTED_DEFAULTS) | set(OPTIONAL_FIELDS)
    unknown = set(payload) - known
    if unknown:
        _fail("AF-LAUNCH-INTAKE-UNKNOWN", "<root>",
              f"undeclared field(s) {sorted(unknown)!r}; a new field must be declared required "
              "or a documented default, never accepted silently")

    provenance: Dict[str, str] = {k: "supplied" for k in payload}
    provenance["entitlement_attestation"] = "attested"
    for i, offer in enumerate(clean_offers):
        provenance[f"offers[{i}].price"] = "supplied"
        provenance[f"offers[{i}].level"] = (
            "supplied" if offer["level"]["state"] == "supplied" else "unknown")
        if offer["relationships"]:
            provenance[f"offers[{i}].relationships"] = "supplied"

    normalized: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tenant_id": payload["tenant_id"].strip(),
        "location_id": payload["location_id"].strip(),
        "launch_id": payload["launch_id"].strip(),
        "revision": revision,
        "journey_mode": mode,
        "brand": {"ref": payload["brand"]["ref"].strip(), "hash": payload["brand"]["hash"].strip()},
        "copy_profile": payload["copy_profile"].strip(),
        "approval": {"ref": payload["approval"]["ref"].strip(),
                     "hash": payload["approval"]["hash"].strip()},
        "offers": clean_offers,
        "entitlement": entitled,
    }
    for name, (key, value, reason) in PERMITTED_DEFAULTS.items():
        if key in payload:
            normalized[key] = payload[key]
            provenance[key] = "supplied"
        else:
            normalized[key] = value
            provenance[key] = f"default: {reason}"
    try:
        normalized["image_plan"] = image_plan.validate_raw(payload.get("image_plan")) or None
    except image_plan.ImagePlanError as exc:
        raise IntakeError(exc.code, exc.field, exc.detail) from exc
    normalized["provenance"] = provenance
    assert_no_commercial_defaults(normalized)
    return normalized


def offer_facts(normalized: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The commercial facts this build actually holds, with their provenance."""
    provenance = normalized.get("provenance") or {}
    facts: List[Dict[str, Any]] = []
    for i, offer in enumerate(normalized["offers"]):
        facts.append({
            "offer_id": offer["offer_id"],
            "role": offer["role"],
            "price": {
                "amount_minor": offer["price"]["amount_minor"],
                "currency": offer["price"]["currency"],
                "provenance": provenance.get(f"offers[{i}].price", "unknown"),
            },
            "level": {
                "state": offer["level"]["state"],
                "provenance": provenance.get(f"offers[{i}].level", "unknown"),
            },
            "entitlement": {
                "state": "attested",
                "basis": normalized["entitlement"]["basis"],
                "provenance": provenance.get("entitlement_attestation", "unknown"),
            },
        })
    return facts
