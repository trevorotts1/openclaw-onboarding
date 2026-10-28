"""Entitlement declaration + fail-closed attestation gate.

The skill CARRIES the access rules as a declaration file; the run must carry an
attestation that names which rule applies. Nothing here charges, creates an
entitlement, reads a purchase from a platform, or calls a billing API. Unknown
entitlement state fails closed: a missing, unknown or unqualified basis never
builds.

The owner's rules, exactly:

  Brand Management membership          qualifies, no new $497 purchase
  everyone else                        qualifies by purchase at $497
  School of AI membership alone        does not qualify
  ZHC alone                            does not qualify
  ZHC with Brand Management            qualifies, no new $497 purchase

A membership is not a purchase event, so a membership attestation never needs a
purchase reference. The declared price is the owner's stated fact, not a
default: a purchase attestation that declares a different amount is refused.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

from .constants import (
    ENTITLEMENT_BASES,
    ENTITLEMENT_DECLARATION,
)

# basis -> (qualifies, requires_purchase). A silent edit to the declaration is
# caught here instead of quietly changing who may build.
EXPECTED_RULES = {
    "brand_management_membership": (True, False),
    "purchase": (True, True),
    "school_of_ai_membership": (False, False),
    "zhc": (False, False),
    "zhc_with_brand_management": (True, False),
}

ATTESTATION_KEYS = ("basis", "evidence_ref", "attested_by",
                    "purchase_reference", "amount_minor", "currency")
REQUIRED_ATTESTATION_KEYS = ("basis", "evidence_ref", "attested_by")


class EntitlementError(Exception):
    """An entitlement that cannot be attested. Carries a stable autofail code."""

    def __init__(self, code: str, field: str, detail: str) -> None:
        super().__init__(f"{code}: {field}: {detail}")
        self.code = code
        self.field = field
        self.detail = detail


def _fail(code: str, field: str, detail: str) -> None:
    raise EntitlementError(code, field, detail)


def _skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def declaration_path() -> Path:
    return _skill_root() / ENTITLEMENT_DECLARATION


def load_declaration() -> Dict[str, Any]:
    """Load and verify the carried declaration. Missing or altered == refused."""
    path = declaration_path()
    if not path.is_file():
        _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", ENTITLEMENT_DECLARATION,
              "the skill carries no entitlement declaration")
    try:
        declaration = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", ENTITLEMENT_DECLARATION,
              f"unreadable declaration ({exc})")
    if not isinstance(declaration, dict):
        _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", ENTITLEMENT_DECLARATION,
              "declaration must be a JSON object")
    if declaration.get("no_billing") is not True:
        _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", "no_billing",
              "must be true: this build charges nothing")
    for flag in ("creates_entitlements", "calls_billing_api"):
        if declaration.get(flag) is not False:
            _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", flag,
                  "must be false: this build creates nothing and calls no billing API")
    price = declaration.get("purchase_price")
    if not isinstance(price, dict):
        _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", "purchase_price",
              "the owner-stated price must be declared")
    amount = price.get("amount_minor")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", "purchase_price.amount_minor",
              "must be a positive integer in minor units")
    if not isinstance(price.get("currency"), str) or len(price["currency"]) != 3:
        _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", "purchase_price.currency",
              "must be a 3-letter currency code")
    rules = declaration.get("rules")
    if not isinstance(rules, list) or not rules:
        _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", "rules", "no rules declared")
    seen = {}
    for rule in rules:
        if not isinstance(rule, dict):
            _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", "rules", f"malformed rule {rule!r}")
        basis = rule.get("basis")
        if basis not in ENTITLEMENT_BASES:
            _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", "rules",
                  f"unknown basis {basis!r}")
        if basis in seen:
            _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", "rules",
                  f"duplicate basis {basis!r}")
        flags = (rule.get("qualifies"), rule.get("requires_purchase"))
        if flags != EXPECTED_RULES[basis]:
            _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", f"rules.{basis}",
                  f"declared {flags}, the owner decided {EXPECTED_RULES[basis]}")
        seen[basis] = rule
    missing = set(EXPECTED_RULES) - set(seen)
    if missing:
        _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", "rules",
              f"missing declared basis/bases {sorted(missing)!r}")
    return declaration


def declaration_record() -> Dict[str, Any]:
    path = declaration_path()
    data = path.read_bytes() if path.is_file() else b""
    return {"path": ENTITLEMENT_DECLARATION,
            "sha256": hashlib.sha256(data).hexdigest() if data else None}


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def attest(attestation: Any) -> Dict[str, Any]:
    """Verify one attestation against the carried declaration. Fail-closed."""
    declaration = load_declaration()
    if not isinstance(attestation, dict):
        _fail("AF-LAUNCH-ENTITLEMENT-ATTESTATION", "entitlement_attestation",
              "must be an object; an unknown entitlement state never builds")
    extra = set(attestation) - set(ATTESTATION_KEYS)
    if extra:
        _fail("AF-LAUNCH-ENTITLEMENT-ATTESTATION", "entitlement_attestation",
              f"undeclared field(s) {sorted(extra)!r}")
    for key in REQUIRED_ATTESTATION_KEYS:
        if not _nonempty(attestation.get(key)):
            _fail("AF-LAUNCH-ENTITLEMENT-ATTESTATION",
                  f"entitlement_attestation.{key}", "must be a non-empty string")
    basis = attestation["basis"].strip()
    if basis not in ENTITLEMENT_BASES:
        _fail("AF-LAUNCH-ENTITLEMENT-UNKNOWN",
              "entitlement_attestation.basis",
              f"{basis!r} is not a declared basis; unknown state fails closed")
    rule = next(r for r in declaration["rules"] if r["basis"] == basis)
    if not rule["qualifies"]:
        _fail("AF-LAUNCH-ENTITLEMENT-NOT-QUALIFIED",
              "entitlement_attestation.basis",
              f"{basis!r} does not qualify for this launch")
    purchase_ref = attestation.get("purchase_reference")
    amount = attestation.get("amount_minor")
    currency = attestation.get("currency")
    if rule["requires_purchase"]:
        if not _nonempty(purchase_ref):
            _fail("AF-LAUNCH-ENTITLEMENT-PURCHASE-UNVERIFIED",
                  "entitlement_attestation.purchase_reference",
                  f"{basis!r} requires a purchase reference")
        declared = declaration["purchase_price"]
        if amount is not None:
            if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
                _fail("AF-LAUNCH-ENTITLEMENT-ATTESTATION",
                      "entitlement_attestation.amount_minor",
                      "must be a positive integer in minor units")
            if amount != declared["amount_minor"]:
                _fail("AF-LAUNCH-ENTITLEMENT-PRICE-CONTRADICTION",
                      "entitlement_attestation.amount_minor",
                      f"{amount} contradicts the owner-stated "
                      f"{declared['amount_minor']}")
            if currency is not None and currency != declared["currency"]:
                _fail("AF-LAUNCH-ENTITLEMENT-PRICE-CONTRADICTION",
                      "entitlement_attestation.currency",
                      f"{currency!r} contradicts the owner-stated "
                      f"{declared['currency']!r}")
    elif purchase_ref is not None:
        _fail("AF-LAUNCH-ENTITLEMENT-ATTESTATION",
              "entitlement_attestation.purchase_reference",
              f"{basis!r} qualifies without a purchase; a membership is not a "
              "purchase event")
    return {
        "basis": basis,
        "qualifies": True,
        "requires_purchase": bool(rule["requires_purchase"]),
        "evidence_ref": attestation["evidence_ref"].strip(),
        "attested_by": attestation["attested_by"].strip(),
        "purchase_reference": purchase_ref.strip() if _nonempty(purchase_ref) else None,
        "amount_minor": amount,
        "currency": currency,
        "billing": "none",
        "declaration": declaration_record(),
    }


def gate(attestation: Any) -> Dict[str, Any]:
    """The single build gate. Refuses every state the declaration cannot prove."""
    return attest(attestation)
