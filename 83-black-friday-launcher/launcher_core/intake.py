"""Validated launcher intake. Fail-closed; never invents a commercial fact.

Required inputs are limited to what the pages genuinely cannot be built without.
Nothing commercial defaults. A missing price is an error, never a free offer and
never zero. Prices and levels must be SUPPLIED or explicitly marked UNKNOWN; a
defaulted commercial fact fails the build by name.

There is NO account-entitlement question. The client is never asked whether they
are a member or bought a licence, and no page build is refused or deferred for
want of an answer. If a consumer needs the value it is 'unknown' and nothing
blocks on it. `entitlement_attestation` is still accepted from older callers so
their intakes keep validating, but it is never read.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlsplit

from . import image_plan
from .launch_plan import SCOPE_WAIVERS, launch_id_violation
from .constants import (
    JOURNEY_MODES,
    OFFER_RELATION_KEYS,
    OFFER_ROLES,
    REPO_ROOT,
    SCHEMA_VERSION,
    UNSUPPORTED_OFFER_ROLES,
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
    "checkout_terms": "the order form cannot show a guarantee, terms or consent line nobody approved",
    "answers_file": "the client's answers file (client-intake-answers/v1) is the sole price authority, DECISIONS-NEEDED[35]",
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
# activation carries the client's DESIRED end state and, for installation/publication, the
# recorded authority that already covers that page/location scope (F06).
# proposal_acceptance names the approval record that accepted any AI proposal in the answers file
# (the same transition Skill 49's approve() runs); without it the proposals stay proposals.
OPTIONAL_FIELDS = ("image_plan", "client_choices", "promotion", "activation",
                   "proposal_acceptance", "linked_destinations")

# Accepted from an older caller and NEVER read: the retirement of the account-entitlement
# question must not break an intake that a saved run already carries. It changes nothing.
LEGACY_IGNORED_FIELDS = ("entitlement_attestation",)

# What the normalized record says about the account. Nobody declared it and nobody was
# asked, so it is exactly this and no build consumes it as a permission.
ENTITLEMENT_UNKNOWN = {
    "state": "unknown",
    "basis": None,
    "qualifies": None,
    "requires_purchase": False,
    "billing": "none",
}

# F22: every launch-dependent destination is declared with its ownership kind. The
# keys are closed so an undeclared fact is refused, never carried silently.
LINKED_FIELDS = ("key", "kind", "url", "page_key", "adapter", "requirements",
                 "evidence", "purchase_route", "note")
LINKED_ADAPTER_FIELDS = ("role", "document_ref")

# F06: the four stages are separate facts. Local preparation is the default and is
# always allowed; installation and publication each need recorded authority and are
# never reachable from a test-only run. A package's achieved stage is decided by
# evidence at assembly, never by this declaration alone.
ACTIVATION_STATES = ("local_prepared", "draft_constructed", "installed", "published")
ACTIVATION_AUTHORITY_SCOPES = {"installed": "installation", "published": "publication"}

OFFER_REQUIRED = ("offer_id", "name", "role", "price", "delivery")
OFFER_OPTIONAL = ("level", "relationships", "checkout")
PRICE_REQUIRED = ("amount_minor", "currency")
PRICE_OPTIONAL = ("bounds_confirmed", "source_ref")

# Operational fields the intake forwards. Skill 49's dispatch knows three write targets;
# this skill ends at approved local files, so approved_live_publication (a separate approved
# step) is refused here. A JSON file never executes a workflow (contract section 7).
WRITE_TARGETS = ("local_only", "approved_test_location")
AUTOMATION_EXECUTIONS = ("not_requested",)
_LOCALE = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*")
_OFFER_ID = re.compile(r"[A-Za-z0-9_-]+")

# Price sanity: outside this range the client confirms the number (price.bounds_confirmed: true).
PRICE_MIN_MINOR = 100
PRICE_MAX_MINOR = 10_000_000

# One order, one payment, one currency. Anything that implies instalments or recurring billing
# is refused by name until the checkout contract can carry it.
PAYMENT_PLANS_UNSUPPORTED = "payment plans are not supported in this release"
_PAYMENT_PLAN_KEYS = ("installment", "installments", "payment_plan", "payment_plans",
                      "recurring", "subscription", "billing_interval", "billing_cycle")
CHECKOUT_OPTIONAL = ("billing_type", "schedule", "native_product_id", "native_price_id",
                     "headline", "benefit_explanation")
TERMS_FIELDS = ("guarantee_ref", "guarantee_text", "terms_ref", "terms_text",
                "consent_ref", "consent_text")
LEVELED_ROLES = ("upsell_1", "downsell_1", "upsell_2")

# Provenance prefixes that may NEVER be a default. A commercial fact is either
# supplied or explicitly unknown.
COMMERCIAL_ROOTS = ("offers", "level",
                    "cross_sales", "relationships", "checkout_terms")
# The shared answer-provenance vocabulary (shared-utils/client_intake/revision.py) applied
# to a price's approval status, so a consumer of offer_facts() reads the same five kinds the
# answer ledgers use instead of inventing a sixth.
_PROVENANCE_FOR_APPROVAL = {
    "provided": "confirmed_fact",
    "approved": "confirmed_fact",
    "recommended_unapproved": "ai_proposal",
    "unknown": "unresolved_capability",
}


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


def _refuse_payment_plans(field: str, block: Any) -> None:
    """Instalment and recurring answers are refused by name, wherever they appear."""
    if not isinstance(block, dict):
        return
    for key in block:
        if key in _PAYMENT_PLAN_KEYS and block[key] not in (None, False, [], {}, ""):
            _fail("AF-LAUNCH-INTAKE-PAYMENT-PLAN", f"{field}.{key}", PAYMENT_PLANS_UNSUPPORTED)
    if block.get("billing_type") not in (None, "one_time"):
        _fail("AF-LAUNCH-INTAKE-PAYMENT-PLAN", f"{field}.billing_type",
              f"{block['billing_type']!r}: {PAYMENT_PLANS_UNSUPPORTED}; only 'one_time' is accepted")
    if block.get("schedule") not in (None, []):
        _fail("AF-LAUNCH-INTAKE-PAYMENT-PLAN", f"{field}.schedule", PAYMENT_PLANS_UNSUPPORTED)


def _level_question(offer: Dict[str, Any]) -> str:
    return (f"What exactly does the buyer receive with {offer['name']!r} ({offer['role']})? "
            "Supply level.state 'supplied' with its name and every deliverable; "
            "nothing is invented for you.")


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


def _validate_checkout(index: int, offer: Dict[str, Any]) -> Dict[str, Any]:
    """Optional per-offer checkout facts. Native ids stay null until Skill 06 reads them back."""
    field = f"offers[{index}].checkout"
    raw = offer.get("checkout")
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        _fail("AF-LAUNCH-INTAKE-CHECKOUT", field, "must be an object")
    extra = set(raw) - set(CHECKOUT_OPTIONAL)
    if extra:
        _fail("AF-LAUNCH-INTAKE-CHECKOUT", field, f"undeclared field(s) {sorted(extra)!r}")
    clean: Dict[str, Any] = {"billing_type": "one_time", "schedule": []}
    for key in ("native_product_id", "native_price_id", "headline", "benefit_explanation"):
        value = raw.get(key)
        if value is not None and not _nonempty_str(value):
            _fail("AF-LAUNCH-INTAKE-CHECKOUT", f"{field}.{key}", "must be a non-empty string or absent")
        clean[key] = value.strip() if value is not None else None
    if (clean["headline"] is None) != (clean["benefit_explanation"] is None):
        _fail("AF-LAUNCH-INTAKE-CHECKOUT", field, "headline and benefit_explanation go together")
    if clean["headline"] is not None and offer["role"] != "bump":
        _fail("AF-LAUNCH-INTAKE-CHECKOUT", field, "headline/benefit_explanation belong to a bump offer")
    return clean


def _validate_delivery(index: int, offer: Dict[str, Any]) -> Dict[str, Any]:
    """Where each entitlement's buyer is sent: an https address the owner confirmed."""
    field = f"offers[{index}].delivery"
    raw = offer["delivery"]
    if not isinstance(raw, dict):
        _fail("AF-LAUNCH-INTAKE-DELIVERY", field, "must be an object")
    extra = set(raw) - {"destination", "owner_confirmed"}
    if extra:
        _fail("AF-LAUNCH-INTAKE-DELIVERY", field, f"undeclared field(s) {sorted(extra)!r}")
    destination = raw.get("destination")
    parts = urlsplit(destination) if _nonempty_str(destination) else None
    if (parts is None or parts.scheme != "https" or not parts.hostname
            or parts.username or parts.password or any(c.isspace() for c in destination.strip())):
        _fail("AF-LAUNCH-INTAKE-DELIVERY", f"{field}.destination",
              "must be an https address (no credentials, no spaces) where the buyer receives this offer")
    if raw.get("owner_confirmed") is not True:
        _fail("AF-LAUNCH-INTAKE-DELIVERY", f"{field}.owner_confirmed",
              "the owner must confirm this destination (true); it is never assumed")
    return {"destination": destination.strip(), "owner_confirmed": True}


def _validate_terms(raw: Any) -> Dict[str, str]:
    """Guarantee, terms and consent: an approved reference AND the verbatim text, never invented."""
    if not isinstance(raw, dict):
        _fail("AF-LAUNCH-INTAKE-TERMS", "checkout_terms", "must be an object")
    for key in TERMS_FIELDS:
        if not _nonempty_str(raw.get(key)):
            _fail("AF-LAUNCH-INTAKE-TERMS", f"checkout_terms.{key}", "must be a non-empty string")
    extra = set(raw) - set(TERMS_FIELDS)
    if extra:
        _fail("AF-LAUNCH-INTAKE-TERMS", "checkout_terms", f"undeclared field(s) {sorted(extra)!r}")
    return {key: raw[key] for key in TERMS_FIELDS}  # text stays verbatim


PROMOTION_KEYS = {"kind", "limitations", "buyers", "followup", "seat_limit", "seat_limit_state", "source_refs"}
PROMOTION_KINDS = ("A discount", "A bonus", "A special bundle")


def _validate_promotion(raw: Any) -> Dict[str, Any]:
    """The client's promotion facts (kind, limits, seats). A fact record only: no page copy reads it this
    release (DECISIONS-NEEDED[37]); discount and scarcity claims stay forbidden by the claim scanner."""
    if not isinstance(raw, dict):
        _fail("AF-LAUNCH-INTAKE-PROMOTION", "promotion", "must be an object")
    extra = set(raw) - PROMOTION_KEYS
    if extra:
        _fail("AF-LAUNCH-INTAKE-PROMOTION", "promotion", f"undeclared field(s) {sorted(extra)!r}")
    if raw.get("kind") is not None and raw["kind"] not in PROMOTION_KINDS:
        _fail("AF-LAUNCH-INTAKE-PROMOTION", "promotion.kind", f"not one of {PROMOTION_KINDS!r}")
    for key in ("limitations", "buyers", "followup"):
        if raw.get(key) is not None and not isinstance(raw[key], str):
            _fail("AF-LAUNCH-INTAKE-PROMOTION", f"promotion.{key}", "must be text or null")
    seats = raw.get("seat_limit")
    if seats is not None and (isinstance(seats, bool) or not isinstance(seats, int) or seats <= 0):
        _fail("AF-LAUNCH-INTAKE-PROMOTION", "promotion.seat_limit", "must be a whole number above zero or null")
    state = raw.get("seat_limit_state")
    if state not in ("limited", "no_limit", "unknown") or (state == "limited") != (seats is not None):
        _fail("AF-LAUNCH-INTAKE-PROMOTION", "promotion.seat_limit_state",
              "must be limited (and only when seat_limit is set), no_limit or unknown")
    refs = raw.get("source_refs")
    if not (isinstance(refs, list) and refs and all(isinstance(r, str) and r.startswith("answers-file:bf_")
                                                    for r in refs)):
        _fail("AF-LAUNCH-INTAKE-PROMOTION", "promotion.source_refs",
              "must be a non-empty list of answers-file:bf_* refs")
    return {key: raw.get(key) for key in sorted(PROMOTION_KEYS)}


def _validate_activation(raw: Any, *, location_id: str, test_only: bool) -> Dict[str, Any]:
    """The client's desired end state, and the recorded authority it needs.

    Absent means ``local_prepared``: the historical local/test default is unchanged and
    nothing is installed or published. ``installed`` and ``published`` need an authority
    record whose scope matches the stage and whose location is this launch's own — the
    same recorded approval is carried forward, never asked for twice, and it can never
    authorize another location. A test-only run may not request either.
    """
    if raw is None:
        return {"desired_state": "local_prepared", "authority": None,
                "source": "default: local preparation; nothing is installed or published"}
    if not isinstance(raw, dict):
        _fail("AF-LAUNCH-INTAKE-ACTIVATION", "activation", "must be an object")
    extra = set(raw) - {"desired_state", "authority"}
    if extra:
        _fail("AF-LAUNCH-INTAKE-ACTIVATION", "activation",
              f"undeclared field(s) {sorted(extra)!r}")
    desired = raw.get("desired_state")
    if desired not in ACTIVATION_STATES:
        _fail("AF-LAUNCH-INTAKE-ACTIVATION", "activation.desired_state",
              f"must be one of {ACTIVATION_STATES!r}; a stage is never inferred")
    authority = raw.get("authority")
    if desired not in ACTIVATION_AUTHORITY_SCOPES:
        if authority is not None:
            _fail("AF-LAUNCH-INTAKE-ACTIVATION", "activation.authority",
                  f"{desired!r} is local/draft construction and carries no installation or "
                  "publication authority")
        return {"desired_state": desired, "authority": None, "source": "supplied"}
    if test_only:
        _fail("AF-LAUNCH-INTAKE-ACTIVATION", "activation.desired_state",
              f"{desired!r} needs a live (test_only false) run; a local/test package is "
              "never relabelled installed or live")
    if not isinstance(authority, dict):
        _fail("AF-LAUNCH-INTAKE-ACTIVATION", "activation.authority",
              f"{desired!r} needs the recorded authority that covers this page and location")
    extra = set(authority) - {"ref", "scope", "location_id"}
    if extra:
        _fail("AF-LAUNCH-INTAKE-ACTIVATION", "activation.authority",
              f"undeclared field(s) {sorted(extra)!r}")
    for key in ("ref", "scope", "location_id"):
        if not _nonempty_str(authority.get(key)):
            _fail("AF-LAUNCH-INTAKE-ACTIVATION", f"activation.authority.{key}",
                  "must be a non-empty string")
    want = ACTIVATION_AUTHORITY_SCOPES[desired]
    if authority["scope"] != want:
        _fail("AF-LAUNCH-INTAKE-ACTIVATION", "activation.authority.scope",
              f"{desired!r} needs scope {want!r}, got {authority['scope']!r}")
    if authority["location_id"].strip() != location_id.strip():
        _fail("AF-LAUNCH-INTAKE-ACTIVATION", "activation.authority.location_id",
              "the recorded authority covers only its own location, and this launch is "
              f"{location_id!r}")
    return {"desired_state": desired,
            "authority": {"ref": authority["ref"].strip(), "scope": want,
                          "location_id": location_id.strip()},
            "source": "supplied"}


def _validate_offer(index: int, offer: Any) -> Dict[str, Any]:
    field = f"offers[{index}]"
    if not isinstance(offer, dict):
        _fail("AF-LAUNCH-INTAKE-OFFER", field, "must be an object")
    for block, name in ((offer, field), (offer.get("price"), f"{field}.price"),
                        (offer.get("checkout"), f"{field}.checkout")):
        _refuse_payment_plans(name, block)
    for key in OFFER_REQUIRED:
        if key not in offer:
            _fail("AF-LAUNCH-INTAKE-OFFER", f"{field}.{key}", "missing")
    for key in ("offer_id", "name"):
        if not _nonempty_str(offer[key]):
            _fail("AF-LAUNCH-INTAKE-OFFER", f"{field}.{key}", "must be a non-empty string")
    if not _OFFER_ID.fullmatch(offer["offer_id"].strip()):
        _fail("AF-LAUNCH-INTAKE-OFFER", f"{field}.offer_id", "must match [A-Za-z0-9_-]+")
    role = offer["role"]
    if role in UNSUPPORTED_OFFER_ROLES:
        _fail("AF-LAUNCH-INTAKE-OFFER", f"{field}.role", f"{role}: {UNSUPPORTED_OFFER_ROLES[role]}")
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
    extra_price = set(price) - set(PRICE_REQUIRED) - set(PRICE_OPTIONAL)
    if extra_price:
        _fail("AF-LAUNCH-INTAKE-PRICE", f"{field}.price", f"undeclared field(s) {sorted(extra_price)!r}")
    if not isinstance(price.get("bounds_confirmed", False), bool):
        _fail("AF-LAUNCH-INTAKE-PRICE", f"{field}.price.bounds_confirmed", "must be true or false")
    if not PRICE_MIN_MINOR <= amount <= PRICE_MAX_MINOR and price.get("bounds_confirmed") is not True:
        _fail("AF-LAUNCH-INTAKE-OFFER", f"{field}.price.amount_minor",
              f"{amount} is outside {PRICE_MIN_MINOR}..{PRICE_MAX_MINOR} minor units; "
              "ask the owner to confirm this price, then set price.bounds_confirmed true")
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
        "delivery": _validate_delivery(index, offer),
        "checkout": _validate_checkout(index, {**offer, "role": role}),
    }


def _check_offer_set(offers: List[Dict[str, Any]], mode: str) -> None:
    """One funnel, one cart: a single currency and no two offers that collide."""
    currencies = sorted({o["price"]["currency"] for o in offers})
    if len(currencies) > 1:
        _fail("AF-LAUNCH-INTAKE-OFFER", "offers[*].price.currency",
              f"one funnel is one cart in one currency, found {currencies!r}")
    for what, key in (("offer id", lambda o: o["offer_id"].lower()),
                      ("display name", lambda o: o["name"].casefold())):
        seen: Dict[str, str] = {}
        for o in offers:
            k = key(o)
            if k in seen:
                _fail("AF-LAUNCH-INTAKE-OFFER", f"offers[{o['offer_id']}]",
                      f"duplicate {what} (case-insensitive) with {seen[k]!r}; "
                      "two offers would share one entitlement or one label")
            seen[k] = o["offer_id"]
    if mode == "multiple_options":
        by_price: Dict[int, List[Dict[str, Any]]] = {}
        for o in (o for o in offers if o["role"] == "main"):
            by_price.setdefault(o["price"]["amount_minor"], []).append(o)
        for amount, group in by_price.items():
            looks = {(o["level"].get("name"), tuple(o["level"].get("deliverables", ()))) for o in group}
            if len(group) > 1 and len(looks) < len(group):
                _fail("AF-LAUNCH-INTAKE-OFFER", "offers",
                      f"main offers share price {amount} and the same level; "
                      "distinct options need distinct prices or distinct levels")


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


ANSWERS_SCHEMA = "client-intake-answers/v1"
_SKILL_ROOT = Path(__file__).resolve().parents[1]


def _revision():
    """shared-utils/client_intake/revision.py, loaded once by path (stdlib only).

    The same file Skill 49's launch intake consumes: one proposal-acceptance transition and
    one revision reconciliation. Duplicating either rule here is the drift this avoids.
    """
    mod = sys.modules.get("client_intake_revision")
    if mod is not None:
        return mod
    path = REPO_ROOT / "shared-utils" / "client_intake" / "revision.py"
    if not path.is_file():
        _fail("AF-LAUNCH-INTAKE-PROVENANCE", "answers_file",
              "the shared revision module is not installed, so a revision cannot reconcile "
              "the offers it disabled")
    spec = importlib.util.spec_from_file_location("client_intake_revision", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["client_intake_revision"] = mod
    spec.loader.exec_module(mod)
    return mod


def _validate_proposal_acceptance(raw: Any) -> Dict[str, str]:
    """The approval record that accepted the answers file's AI proposals. Named, never assumed:
    an acceptance with no approval id would launder a suggestion into a fact."""
    field = "proposal_acceptance"
    if not isinstance(raw, dict):
        _fail("AF-LAUNCH-INTAKE-PROPOSAL", field, "must be an object naming the approval record")
    extra = set(raw) - {"ref", "hash"}
    if extra:
        _fail("AF-LAUNCH-INTAKE-PROPOSAL", field, f"undeclared field(s) {sorted(extra)!r}")
    for key in ("ref", "hash"):
        if not _nonempty_str(raw.get(key)):
            _fail("AF-LAUNCH-INTAKE-PROPOSAL", f"{field}.{key}",
                  "must be a non-empty string; a proposal is never accepted anonymously")
    return {"ref": raw["ref"].strip(), "hash": raw["hash"].strip()}


def _offer_mapper():
    """shared-utils/signature_launch_contract/offer_mapper.py, loaded once by path (stdlib only)."""
    mod = sys.modules.get("offer_mapper")
    if mod is not None:
        return mod
    path = REPO_ROOT / "shared-utils" / "signature_launch_contract" / "offer_mapper.py"
    if not path.is_file():
        _fail("AF-LAUNCH-INTAKE-PROVENANCE", "answers_file",
              "the shared offer mapper is not installed, so no price can be checked against the client's answers")
    spec = importlib.util.spec_from_file_location("offer_mapper", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["offer_mapper"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_answers(raw: Any):
    """The client's answers file: a relative path resolves against the Skill 83 root. Returns (path, doc)."""
    if not _nonempty_str(raw):
        _fail("AF-LAUNCH-INTAKE-PROVENANCE", "answers_file", "must be a path to the client's answers file")
    path = Path(raw)
    if not path.is_absolute():
        path = _SKILL_ROOT / path
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _fail("AF-LAUNCH-INTAKE-PROVENANCE", "answers_file",
              f"the answers file cannot be read as JSON ({type(exc).__name__})")
    if not isinstance(doc, dict) or doc.get("schema") != ANSWERS_SCHEMA:
        _fail("AF-LAUNCH-INTAKE-PROVENANCE", "answers_file", f"schema must be {ANSWERS_SCHEMA!r}")
    return path, doc


def _bind_provenance(raw_offers: List[Any], offers: List[Dict[str, Any]], answers_doc: Dict[str, Any],
                     test_only: bool) -> None:
    """Every price names an entry of the client's answers file; the canonical record rides on the offer."""
    om = _offer_mapper()
    for i, (raw, offer) in enumerate(zip(raw_offers, offers)):
        ref = (raw.get("price") or {}).get("source_ref")
        try:
            canon = om.resolve_offer(answers_doc, ref, slot=offer["role"], display_name=offer["name"],
                                     amount_minor=offer["price"]["amount_minor"],
                                     currency=offer["price"]["currency"], test_only=test_only)
        except om.MapperError as exc:
            _fail("AF-LAUNCH-INTAKE-PROVENANCE", f"offers[{i}].price.source_ref", exc.detail)
        stated = raw.get("checkout") or {}
        price0 = canon["prices"][0]
        for key, want in (("billing_type", price0.get("billing_type")),
                          ("native_product_id", canon.get("native_product_id")),
                          ("native_price_id", price0.get("native_price_id"))):
            if key in stated and stated[key] is not None and stated[key] != want:
                _fail("AF-LAUNCH-INTAKE-PROVENANCE", f"offers[{i}].checkout.{key}",
                      f"{stated[key]!r} is not what the client's answers say ({want!r})")
        offer["price"]["source_ref"] = ref
        offer["canonical"] = canon


def _validate_linked_destinations(raw: Any) -> List[Dict[str, Any]]:
    """F22: the declared delivery/access destinations, shape-checked and fail-closed.

    Completeness (a new page's five requirements, an external destination's six evidence
    facts) is enforced by ``linked_delivery.resolve`` with plain-language blockers; here
    the SHAPE is closed, so an unknown kind/key can never be carried as a fact.
    """
    if raw is None:
        return []
    from .linked_delivery import EXTERNAL_EVIDENCE, NEW_BUILD_REQUIREMENTS, RESOURCE_KINDS
    if not isinstance(raw, list):
        _fail("AF-LAUNCH-INTAKE-LINKED", "linked_destinations", "must be a list of destinations")
    out: List[Dict[str, Any]] = []
    seen = set()
    for i, item in enumerate(raw):
        field = f"linked_destinations[{i}]"
        if not isinstance(item, dict):
            _fail("AF-LAUNCH-INTAKE-LINKED", field, "must be an object")
        extra = set(item) - set(LINKED_FIELDS)
        if extra:
            _fail("AF-LAUNCH-INTAKE-UNKNOWN", field, f"undeclared field(s) {sorted(extra)!r}")
        key = item.get("key")
        if not _nonempty_str(key):
            _fail("AF-LAUNCH-INTAKE-LINKED", f"{field}.key", "must be a stable non-empty string")
        if key in seen:
            _fail("AF-LAUNCH-INTAKE-LINKED", f"{field}.key", f"duplicate destination key {key!r}")
        seen.add(key)
        kind = item.get("kind")
        if kind not in RESOURCE_KINDS:
            _fail("AF-LAUNCH-INTAKE-LINKED", f"{field}.kind", f"must be one of {list(RESOURCE_KINDS)}")
        if not isinstance(item.get("purchase_route", False), bool):
            _fail("AF-LAUNCH-INTAKE-LINKED", f"{field}.purchase_route", "must be true or false")
        if "page_key" in item and not _nonempty_str(item["page_key"]):
            _fail("AF-LAUNCH-INTAKE-LINKED", f"{field}.page_key", "must be a non-empty string")
        adapter = item.get("adapter")
        if adapter is not None:
            if not isinstance(adapter, dict) or set(adapter) != set(LINKED_ADAPTER_FIELDS):
                _fail("AF-LAUNCH-INTAKE-LINKED", f"{field}.adapter",
                      f"must be an object with exactly {list(LINKED_ADAPTER_FIELDS)}")
            for name in LINKED_ADAPTER_FIELDS:
                if not _nonempty_str(adapter[name]):
                    _fail("AF-LAUNCH-INTAKE-LINKED", f"{field}.adapter.{name}",
                          "must be a non-empty string")
        requirements = item.get("requirements")
        if requirements is not None:
            if not isinstance(requirements, dict):
                _fail("AF-LAUNCH-INTAKE-LINKED", f"{field}.requirements", "must be an object")
            extra = set(requirements) - set(NEW_BUILD_REQUIREMENTS)
            if extra:
                _fail("AF-LAUNCH-INTAKE-UNKNOWN", f"{field}.requirements",
                      f"undeclared requirement(s) {sorted(extra)!r}")
            for name, value in requirements.items():
                if not _nonempty_str(value):
                    _fail("AF-LAUNCH-INTAKE-LINKED", f"{field}.requirements.{name}",
                          "must be a non-empty evidence reference")
        evidence = item.get("evidence")
        if evidence is not None:
            if not isinstance(evidence, dict):
                _fail("AF-LAUNCH-INTAKE-LINKED", f"{field}.evidence", "must be an object")
            extra = set(evidence) - set(EXTERNAL_EVIDENCE)
            if extra:
                _fail("AF-LAUNCH-INTAKE-UNKNOWN", f"{field}.evidence",
                      f"undeclared evidence(s) {sorted(extra)!r}")
            for name, value in evidence.items():
                if not _nonempty_str(value):
                    _fail("AF-LAUNCH-INTAKE-LINKED", f"{field}.evidence.{name}",
                          "must be a non-empty reference")
        if kind in ("existing_client_owned", "third_party"):
            url = item.get("url")
            parts = urlsplit(url) if _nonempty_str(url) else None
            if (parts is None or parts.scheme != "https" or not parts.hostname
                    or parts.username or parts.password or any(c.isspace() for c in url.strip())):
                _fail("AF-LAUNCH-INTAKE-LINKED", f"{field}.url",
                      "an existing or third-party destination must be an https address "
                      "(no credentials, no spaces)")
        out.append(dict(item))
    return out


def validate(payload: Any) -> Dict[str, Any]:
    """Return a normalized launch intake or raise IntakeError. Fail-closed.

    The reconciliation report is available from validate_with_reconciliation(); this entry
    point keeps the normalized record's shape unchanged for every existing consumer.
    """
    return _validate(payload)[0]


def validate_with_reconciliation(payload: Any) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(normalized intake, reconciliation report) for a caller that must show what a revision
    disabled and which saved answers and offers were removed because of it."""
    return _validate(payload)


def _validate(payload: Any) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return (normalized launch intake, reconciliation report) or raise IntakeError. Fail-closed."""
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

    bad_id = launch_id_violation(payload["launch_id"].strip())
    if bad_id:
        _fail("AF-LAUNCH-INTAKE-SHAPE", "launch_id", bad_id)

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

    _refuse_payment_plans("<root>", payload)
    if "test_only" in payload and not isinstance(payload["test_only"], bool):
        _fail("AF-LAUNCH-INTAKE-TEST-ONLY", "test_only",
              "must be true or false; 0, null or '' never means live")
    if "allowed_write_target" in payload and payload["allowed_write_target"] not in WRITE_TARGETS:
        _fail("AF-LAUNCH-INTAKE-WRITE-TARGET", "allowed_write_target",
              f"not one of {WRITE_TARGETS!r}; publication is a separate approved step")
    if "automation_execution" in payload and payload["automation_execution"] not in AUTOMATION_EXECUTIONS:
        _fail("AF-LAUNCH-INTAKE-AUTOMATION", "automation_execution",
              f"not one of {AUTOMATION_EXECUTIONS!r}")
    if "locale" in payload and not (isinstance(payload["locale"], str)
                                    and _LOCALE.fullmatch(payload["locale"])):
        _fail("AF-LAUNCH-INTAKE-LOCALE", "locale", "must be a BCP-47 language tag such as 'en' or 'en-US'")
    checkout_terms = _validate_terms(payload["checkout_terms"])

    offers = payload["offers"]
    if not isinstance(offers, list) or not offers:
        _fail("AF-LAUNCH-INTAKE-OFFER", "offers", "at least one offer is required")
    answers_path, answers_doc = _load_answers(payload["answers_file"])
    rev = _revision()
    answers_ledger = answers_doc.get("answers") if isinstance(answers_doc.get("answers"), dict) else {}
    acceptance = (_validate_proposal_acceptance(payload["proposal_acceptance"])
                  if payload.get("proposal_acceptance") is not None else None)
    # ONE shared transition for an AI proposal the client accepted, and ONE shared
    # reconciliation for the answers a revision disabled. Both live in
    # shared-utils/client_intake/revision.py and are the same code Skill 49 runs. The
    # reconciliation runs on the RAW offers: a stale dependent offer is removed because its
    # parent is disabled, so it is never asked to satisfy a shape it will not be built from.
    #
    # A slot counts as DISABLED only on a POSITIVE record (the answers ledger marks it
    # not_applicable). Mere absence from this payload is not a disabling: a client who
    # supplied upsell_2 with no parent gets the named AF-LAUNCH-INTAKE-ROUTE refusal below,
    # never a silent deletion of the offer they asked for. Dropping it here would make the
    # route law unreachable and lose a supplied commercial fact, which this module's
    # contract forbids ("fail-closed; never invents a commercial fact").
    disabled = [slot for slot in ("upsell_1", "downsell_1", "upsell_2")
                if isinstance(answers_ledger.get(slot), dict)
                and rev.state_of(answers_ledger[slot]) == rev.NOT_APPLICABLE]
    reconciliation = rev.reconcile_launch(answers_ledger, revision=revision,
                                          offers=offers, answer_prefix="", disabled=disabled)
    if acceptance is not None:
        reconciliation["accepted_proposals"] = rev.accept_proposals(answers_ledger, acceptance)
    dropped = {row["slot"] for row in reconciliation["removed_offers"]}
    if dropped:
        # A revision that disables U1 removes the saved D1/U2 offers instead of letting the
        # route graph refuse the build ("U1 disabled requires D1 and U2 disabled") or, worse,
        # carrying them into a stale page set, follow-up emails and route nodes.
        offers = [o for o in offers if (o.get("role") if isinstance(o, dict) else None) not in dropped]
    clean_offers: List[Dict[str, Any]] = [_validate_offer(i, o) for i, o in enumerate(offers)]
    _bind_provenance(offers, clean_offers, answers_doc, payload.get("test_only", True) is not False)
    _check_relationship_targets(clean_offers)
    _check_offer_set(clean_offers, mode)

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

    for i, o in enumerate(clean_offers):
        if (o["role"] in LEVELED_ROLES or (o["role"] == "main" and mode != "single_simple")) \
                and o["level"]["state"] != "supplied":
            _fail("AF-LAUNCH-INTAKE-LEVEL", f"offers[{i}].level", _level_question(o))

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

    known = (set(REQUIRED_FIELDS) | set(PERMITTED_DEFAULTS) | set(OPTIONAL_FIELDS)
             | set(LEGACY_IGNORED_FIELDS))
    unknown = set(payload) - known
    if unknown:
        _fail("AF-LAUNCH-INTAKE-UNKNOWN", "<root>",
              f"undeclared field(s) {sorted(unknown)!r}; a new field must be declared required "
              "or a documented default, never accepted silently")
    choices = payload.get("client_choices", [])
    if (not isinstance(choices, list) or any(not isinstance(c, str) or c not in SCOPE_WAIVERS for c in choices)
            or len(set(choices)) != len(choices)):
        _fail("AF-LAUNCH-INTAKE-CHOICES", "client_choices",
              f"client_choices must be a list drawn from {sorted(SCOPE_WAIVERS)}; "
              "it records what the CLIENT chose to leave out of the launch")
    promotion = _validate_promotion(payload["promotion"]) if payload.get("promotion") is not None else None
    linked_destinations = _validate_linked_destinations(payload.get("linked_destinations"))
    activation = _validate_activation(
        payload.get("activation"), location_id=payload["location_id"].strip(),
        test_only=payload.get("test_only", True) is not False)

    provenance: Dict[str, str] = {k: "supplied" for k in payload}
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
        "checkout_terms": checkout_terms,
        "entitlement": dict(ENTITLEMENT_UNKNOWN),
        "answers_file": str(answers_path),
        "activation": activation,
    }
    if "activation" in payload:
        provenance["activation"] = "supplied"
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
    normalized["client_choices"] = list(choices)
    normalized["linked_destinations"] = linked_destinations
    if "linked_destinations" in payload:
        provenance["linked_destinations"] = "supplied"
    if promotion is not None:
        normalized["promotion"] = promotion
    normalized["provenance"] = provenance
    assert_no_commercial_defaults(normalized)
    return normalized, reconciliation


def offer_facts(normalized: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The commercial facts this build actually holds, with their provenance."""
    provenance = normalized.get("provenance") or {}
    facts: List[Dict[str, Any]] = []
    for i, offer in enumerate(normalized["offers"]):
        approval = ((offer.get("canonical") or {}).get("prices") or [{}])[0].get("approval_status")
        facts.append({
            "offer_id": offer["offer_id"],
            "role": offer["role"],
            "price": {
                "amount_minor": offer["price"]["amount_minor"],
                "currency": offer["price"]["currency"],
                "provenance": provenance.get(f"offers[{i}].price", "unknown"),
                "provenance_kind": _PROVENANCE_FOR_APPROVAL.get(approval, "unresolved_capability"),
            },
            "level": {
                "state": offer["level"]["state"],
                "provenance": provenance.get(f"offers[{i}].level", "unknown"),
            },
            "entitlement": {
                "state": "unknown",
                "basis": None,
                "provenance": "unknown",
            },
        })
    return facts
