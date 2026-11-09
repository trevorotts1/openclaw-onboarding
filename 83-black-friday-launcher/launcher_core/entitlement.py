"""Entitlement declaration + fail-closed attestation gate.

The skill CARRIES the access rules as a declaration file; the run must carry an
attestation that names which rule applies, and the attestation is VERIFIED against
a source the worker cannot write: the client's own GHL contact record (tags) and,
for a purchase, the GHL order, both read through a GET-only transport
(shared-utils/ghl/contact_membership.py). evidence_ref is the contact id,
purchase_reference is the order id; a free-text string that does not resolve
there is refused. Nothing here charges, creates an entitlement or calls a billing
API. Unknown entitlement state, or no way to read the record, fails closed.

The owner's rules, exactly:

  Brand Management membership          qualifies, no new $497 purchase
  everyone else                        qualifies by purchase at $497
  School of AI membership alone        does not qualify
  ZHC alone                            does not qualify
  ZHC with Brand Management            qualifies, no new $497 purchase

A membership is not a purchase event, so a membership attestation never needs a
purchase reference. A purchase attestation must state the amount. The declared price is the owner's stated fact, not a
default: a purchase attestation that declares a different amount is refused.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict

from .constants import (
    ENTITLEMENT_BASES,
    ENTITLEMENT_DECLARATION,
    REPO_ROOT,
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

# What every result says about its own evidence: read back from the client's GHL
# contact record through a GET-only transport, never a string the caller wrote.
EVIDENCE_KIND = "ghl_contact_readback"
ATTESTATION_BOUNDARY = (
    "Verified by read-only GHL lookup: evidence_ref resolved to the client's contact "
    "record and its tags carry the declared membership tag(s); a purchase basis also "
    "resolved purchase_reference to a paid order on that contact at the declared "
    "price. attested_by is recorded, never trusted. No billing API is called."
)

# The only interview answer that counts as 'included'. Exact match, no prefix.
INCLUDED_CHOICE = "Yes, it is included"

_CM_NAME = "ghl_contact_membership"
# Test/orchestrator seam: a transport set here is used instead of the live env one.
_transport: Any = None


def set_transport(transport: Any) -> None:
    """Use this read-only transport for lookups (None restores the live default)."""
    global _transport
    _transport = transport


def _membership_module():
    """Load shared-utils/ghl/contact_membership.py once (stdlib only, by path)."""
    mod = sys.modules.get(_CM_NAME)
    if mod is None:
        path = REPO_ROOT / "shared-utils" / "ghl" / "contact_membership.py"
        if not path.is_file():
            _fail("AF-LAUNCH-ENTITLEMENT-UNVERIFIED", "contact_membership",
                  "the read-only GHL lookup is not present; entitlement cannot be verified")
        spec = importlib.util.spec_from_file_location(_CM_NAME, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[_CM_NAME] = mod
        spec.loader.exec_module(mod)
    return mod


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
    tags = declaration.get("membership_tags")
    if not isinstance(tags, dict):
        _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", "membership_tags",
              "the GHL tag(s) that prove each membership basis must be declared")
    for basis, (qualifies, requires_purchase) in EXPECTED_RULES.items():
        if qualifies and not requires_purchase:
            names = tags.get(basis)
            if (not isinstance(names, list) or not names
                    or not all(_nonempty(n) for n in names)):
                _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", f"membership_tags.{basis}",
                      "must be a non-empty list of tag names")
    verification = declaration.get("verification")
    if (not isinstance(verification, dict) or verification.get("read_only") is not True
            or verification.get("interview_choice") != INCLUDED_CHOICE
            or not isinstance(verification.get("order_paid_statuses"), list)
            or not verification["order_paid_statuses"]):
        _fail("AF-LAUNCH-ENTITLEMENT-DECLARATION", "verification",
              "must declare a read-only lookup, the exact interview choice and paid order statuses")
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


def _verify(declaration: Dict[str, Any], rule: Dict[str, Any], basis: str,
            evidence_ref: str, purchase_ref: Any, transport: Any) -> None:
    """Resolve the attestation in the client's GHL record. Raises on any miss."""
    cm = _membership_module()
    if transport is None:
        transport = _transport
    if transport is None:
        try:
            transport = cm.LiveReadTransport.from_env()
        except cm.LookupFailed as exc:
            _fail("AF-LAUNCH-ENTITLEMENT-UNVERIFIED", "entitlement_attestation",
                  f"no way to read the contact record: {exc.detail}")
    try:
        tags = cm.contact_tags(transport, evidence_ref)
        order = (cm.order_record(transport, purchase_ref.strip())
                 if rule["requires_purchase"] else None)
    except cm.LookupFailed as exc:
        code = ("AF-LAUNCH-ENTITLEMENT-EVIDENCE-UNRESOLVED" if exc.kind == "unresolved"
                else "AF-LAUNCH-ENTITLEMENT-UNVERIFIED")
        _fail(code, "entitlement_attestation.evidence_ref", exc.detail)
    if not rule["requires_purchase"]:
        needed = [n.strip().lower() for n in declaration["membership_tags"][basis]]
        absent = [n for n in needed if n not in tags]
        if absent:
            _fail("AF-LAUNCH-ENTITLEMENT-NOT-MEMBER", "entitlement_attestation.evidence_ref",
                  f"the contact record does not carry the declared tag(s) {absent!r}")
        return
    declared = declaration["purchase_price"]
    if order["contact_id"] != evidence_ref:
        _fail("AF-LAUNCH-ENTITLEMENT-PURCHASE-UNVERIFIED",
              "entitlement_attestation.purchase_reference",
              "the order does not belong to the evidence_ref contact")
    if order["status"] not in declaration["verification"]["order_paid_statuses"]:
        _fail("AF-LAUNCH-ENTITLEMENT-PURCHASE-UNVERIFIED",
              "entitlement_attestation.purchase_reference",
              f"order status {order['status']!r} is not a paid status")
    if (order["amount_minor"] != declared["amount_minor"]
            or order["currency"] != declared["currency"]):
        _fail("AF-LAUNCH-ENTITLEMENT-PRICE-CONTRADICTION",
              "entitlement_attestation.purchase_reference",
              "the order amount/currency does not match the owner-stated price")


def attest(attestation: Any, transport: Any = None) -> Dict[str, Any]:
    """Verify one attestation against the declaration AND the client's GHL record."""
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
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            _fail("AF-LAUNCH-ENTITLEMENT-ATTESTATION",
                  "entitlement_attestation.amount_minor",
                  f"{basis!r} requires the amount as a positive integer in minor units")
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
    _verify(declaration, rule, basis, attestation["evidence_ref"].strip(),
            purchase_ref, transport)
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
        "evidence_kind": EVIDENCE_KIND,
        "proves_purchase": bool(rule["requires_purchase"]),
        "attestation_boundary": ATTESTATION_BOUNDARY,
        "declaration": declaration_record(),
    }


def gate(attestation: Any, transport: Any = None) -> Dict[str, Any]:
    """The single build gate. Refuses every state the GHL record cannot prove."""
    return attest(attestation, transport)


def attest_from_interview(answer: Any, attestation: Any,
                          transport: Any = None) -> Dict[str, Any]:
    """Interview path: only the exact choice counts, and it still needs the lookup.

    'yes whatever', 'Yes', a prefix or a case change is never recorded as attested.
    """
    if answer != INCLUDED_CHOICE:
        _fail("AF-LAUNCH-ENTITLEMENT-INTERVIEW-CHOICE", "entitlement_interview",
              f"the only accepted answer is exactly {INCLUDED_CHOICE!r}")
    return gate(attestation, transport)
