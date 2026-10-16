"""Selection core for Skill 78 (Signature Product Selection).

Stdlib-only, deterministic, fail-closed. Implements the parts of packet docs
02 (sections 3 and 5) and 08 (sections 4, 6, 7) that are pure catalog logic:

- invocation boundary: multiple meaningful main offers only
- offer normalization into a comparison matrix (included / limited /
  not_included states, plus material exclusions carried separately)
- recommendation discipline: an explicit approved reason, never invented
  popularity / best-seller / savings claims
- selection.json intent construction (never payment evidence)
- binding validation: the native product/price mapping chosen at selection
  is exactly the mapping handed to Skill 79 checkout (acceptance A05)
- currency-exponent-aware money formatting (doc 02 section 3: never
  hardcode two decimal places for every currency)

No network, no secrets, no payment behavior lives here.

Cure history: S78-09 independent review (2026-10-15) FAIL cure pass. Fixed:
zero/three-decimal currency rendering, offers with no price choices,
negative amounts, approval status enforced inside build_selection and
validate_binding (not only when a caller ran validate_catalog first),
per-claim evidence (a document-level reference no longer exempts claims),
location_id checked at binding, limited matrix state actually produced.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

SCHEMA_VERSION = "1.0"

# Violation codes (distinct, machine-checkable; mirrors house AF-* style).
V_SINGLE_OFFER = "S78-SINGLE-OFFER-DECLINE"
V_NO_MAIN_OFFERS = "S78-NO-MAIN-OFFERS"
V_UNKNOWN_PRICE = "S78-UNKNOWN-PRICE"
V_UNAPPROVED_PRICE = "S78-UNAPPROVED-PRICE"
V_INVALID_AMOUNT = "S78-INVALID-AMOUNT"
V_DUPLICATE_OFFER = "S78-DUPLICATE-OFFER-ID"
V_UNPROVEN_CLAIM = "S78-UNPROVEN-CLAIM"
V_RECOMMENDATION_UNAPPROVED = "S78-RECOMMENDATION-UNAPPROVED"
V_INSTALLMENT_TOTAL = "S78-INSTALLMENT-TOTAL-MISMATCH"
V_MISSING_NATIVE_MAPPING = "S78-MISSING-NATIVE-MAPPING"
V_SELECTION_UNKNOWN_OFFER = "S78-SELECTION-UNKNOWN-OFFER"
V_SELECTION_PRICE_DRIFT = "S78-SELECTION-PRICE-DRIFT"
V_SELECTION_TENANT = "S78-SELECTION-TENANT-MISMATCH"
V_SELECTION_STALE = "S78-SELECTION-STALE-REVISION"
V_QUERY_AUTHORITY = "S78-QUERY-PRICE-AUTHORITY"
V_TEST_ONLY_LEAK = "S78-TEST-ONLY-IN-PRODUCTION"
V_RECURRING_INTERVAL = "S78-RECURRING-INTERVAL-MISSING"
V_TRIAL_TERMS = "S78-TRIAL-TERMS-MISSING"
V_ASSET_PROVENANCE = "S78-ASSET-PROVENANCE"

UNPROVEN_CLAIM_PATTERNS = [
    r"\bmost popular\b",
    r"\bbest ?seller\b",
    r"\bbest value\b",
    r"\byou save\b",
    r"\bsave \$?\d",
    r"\b\d+\s?%\s?off\b",
    r"\blimited time\b",
    r"\bonly \d+ (spots|seats|left)\b",
]

APPROVED_STATUSES = ("approved", "provided")

# ISO 4217 minor-unit exponents for the currencies that differ from 2.
# Doc 02 section 3: do not hardcode two decimal places for every currency.
ZERO_DECIMAL_CURRENCIES = {
    "BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG",
    "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF",
}
THREE_DECIMAL_CURRENCIES = {"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"}

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}


def currency_exponent(currency: str) -> int:
    code = (currency or "").upper()
    if code in ZERO_DECIMAL_CURRENCIES:
        return 0
    if code in THREE_DECIMAL_CURRENCIES:
        return 3
    return 2


def format_money(amount_minor: int, currency: str) -> str:
    """Format integer minor units with the currency's own exponent.
    Integer math only; the processor's quote remains authoritative."""
    exp = currency_exponent(currency)
    sign = CURRENCY_SYMBOLS.get((currency or "").upper(), (currency or "").upper() + " ")
    amount = int(amount_minor)
    if exp == 0:
        return f"{sign}{amount:,}"
    scale = 10 ** exp
    whole, frac = divmod(amount, scale)
    return f"{sign}{whole:,}.{frac:0{exp}d}"


class Violation(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _main_offers(launch: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    return [o for o in launch.get("offers", []) if o.get("slot") == "main"]


def check_invocation(launch: Mapping[str, Any]) -> str:
    """Return 'proceed' or 'decline_single_offer'. Raise Violation if the
    catalog itself is unusable. A single simple offer is always declined,
    whatever the journey mode claims; an explicitly requested standalone
    comparison (journey_mode 'standalone_comparison') proceeds on the same
    multiple-offer rule with its own approved brief."""
    mains = _main_offers(launch)
    mode = launch.get("journey_mode")
    if mode == "single_simple" or len(mains) == 1:
        return "decline_single_offer"
    if len(mains) == 0:
        raise Violation(V_NO_MAIN_OFFERS, "No main offers in catalog; nothing to select.")
    if len(mains) < 2:
        return "decline_single_offer"
    return "proceed"


def _check_price(price: Mapping[str, Any], offer_id: Any) -> None:
    status = price.get("approval_status")
    if status == "unknown" or price.get("amount_minor") is None:
        raise Violation(
            V_UNKNOWN_PRICE,
            f"Offer {offer_id!r} price {price.get('price_choice_id')!r} is unknown; "
            "unknown is never displayed as zero or free.",
        )
    if not isinstance(price.get("amount_minor"), int) or isinstance(price.get("amount_minor"), bool) or int(price["amount_minor"]) < 0:
        raise Violation(
            V_INVALID_AMOUNT,
            f"Offer {offer_id!r} price {price.get('price_choice_id')!r} amount_minor "
            f"{price.get('amount_minor')!r} is not a non-negative integer minor-unit amount.",
        )
    if status not in APPROVED_STATUSES:
        raise Violation(
            V_UNAPPROVED_PRICE,
            f"Offer {offer_id!r} price {price.get('price_choice_id')!r} approval_status "
            f"{status!r} is not approved for publication.",
        )
    schedule = price.get("schedule") or []
    if price.get("billing_type") == "installment" and schedule:
        total = sum(int(row["amount_minor"]) for row in schedule)
        if total != int(price["amount_minor"]):
            raise Violation(
                V_INSTALLMENT_TOTAL,
                f"Offer {offer_id!r} installment schedule sums to {total} minor units, "
                f"not the stated total {price['amount_minor']}; an installment "
                "amount must never be implied to be the total cost.",
            )
    if price.get("billing_type") == "recurring" and not schedule and not price.get("recurring_interval"):
        raise Violation(
            V_RECURRING_INTERVAL,
            f"Offer {offer_id!r} price {price.get('price_choice_id')!r} is recurring but "
            "carries neither a schedule nor a recurring_interval; the billing "
            "interval is material disclosure and must be stated (doc 02 s3).",
        )
    if price.get("billing_type") == "trial" and not price.get("trial_terms") and not price.get("terms_source"):
        raise Violation(
            V_TRIAL_TERMS,
            f"Offer {offer_id!r} price {price.get('price_choice_id')!r} is a trial but "
            "carries no trial_terms or terms_source; trial terms must be surfaced, "
            "never implied (doc 02 s3).",
        )


def validate_catalog(launch: Mapping[str, Any], *, production: bool = False) -> None:
    """Fail closed on any catalog fact that would make a comparison page lie."""
    seen = set()
    for offer in launch.get("offers", []):
        oid = offer.get("offer_id")
        if oid in seen:
            raise Violation(V_DUPLICATE_OFFER, f"Duplicate offer_id {oid!r}.")
        seen.add(oid)
        if production and offer.get("test_only"):
            raise Violation(V_TEST_ONLY_LEAK, f"Test-only offer {oid!r} in a production catalog.")
        if offer.get("slot") != "main":
            continue
        prices = offer.get("prices") or []
        if not prices:
            raise Violation(
                V_UNKNOWN_PRICE,
                f"Offer {oid!r} has no price choices; a selectable offer without "
                "an approved price cannot be published.",
            )
        for price in prices:
            _check_price(price, oid)


def validate_assets(launch: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Validate the launch catalog's asset list and return it for the plan.
    Catalog asset entries are descriptors with a non-empty name and owner
    (the packet launch contract shape). A bare string or a descriptor
    missing its owner is rejected: the plan never carries an asset nobody
    owns. Generated media additionally needs the full provenance record in
    references/asset-integration.md before S06 installs it; that record is
    verified at install time, not invented here."""
    assets = launch.get("assets") or []
    out = []
    for asset in assets:
        if not isinstance(asset, Mapping) or not asset.get("name") or not asset.get("owner"):
            raise Violation(
                V_ASSET_PROVENANCE,
                f"Asset entry {asset!r} is not a catalog asset descriptor with "
                "a name and an owner; the plan carries no unowned assets.",
            )
        out.append(dict(asset))
    return out


def scan_claims(text: str, *, claim_evidence: Optional[Mapping[str, str]] = None) -> None:
    """Reject unproven popularity/savings/scarcity claims in authored copy.

    A claim is exempt only when claim_evidence maps that exact claim phrase
    (lowercase, as it appears) to a non-empty evidence reference. A general
    or document-level reference exempts nothing: evidence must name the
    claim it supports."""
    evidence = {str(k).strip().lower(): v for k, v in (claim_evidence or {}).items()}
    low = text.lower()
    for pat in UNPROVEN_CLAIM_PATTERNS:
        for match in re.finditer(pat, low):
            phrase = match.group(0)
            if evidence.get(phrase):
                continue
            raise Violation(
                V_UNPROVEN_CLAIM,
                f"Unproven claim {phrase!r} with no claim-specific evidence reference supplied.",
            )


def normalize_matrix(launch: Mapping[str, Any]) -> Dict[str, Any]:
    """Build the comparison matrix from actual offer differences.

    Row states per offer: 'included' (the offer lists the item in
    deliverables), 'limited' (listed in limited_deliverables, with the
    limitation note carried on the row), 'conditional' (listed in
    conditional_deliverables, with the condition carried verbatim on the
    row), or 'not_included'. Dimension items may express any doc 08
    section 4 dimension (deliverables, access, duration, sessions,
    support, recordings, seats, service level, prerequisites) as entries
    in those lists. An unknown is never turned into 'included'. Material
    exclusions are carried as their own list with visibility 'material'.
    """
    mains = _main_offers(launch)
    items: List[str] = []
    for offer in mains:
        for item in offer.get("deliverables", []):
            if item not in items:
                items.append(item)
        for entry in offer.get("limited_deliverables", []) or []:
            name = entry.get("item") if isinstance(entry, Mapping) else entry
            if name and name not in items:
                items.append(name)
        for entry in offer.get("conditional_deliverables", []) or []:
            name = entry.get("item") if isinstance(entry, Mapping) else entry
            if name and name not in items:
                items.append(name)
    rows = []
    for item in items:
        cells = {}
        notes = {}
        for offer in mains:
            if item in offer.get("deliverables", []):
                cells[offer["offer_id"]] = "included"
                continue
            limited = next(
                (e for e in (offer.get("limited_deliverables", []) or [])
                 if (e.get("item") if isinstance(e, Mapping) else e) == item),
                None,
            )
            if limited is not None:
                cells[offer["offer_id"]] = "limited"
                if isinstance(limited, Mapping) and limited.get("note"):
                    notes[offer["offer_id"]] = limited["note"]
                continue
            conditional = next(
                (e for e in (offer.get("conditional_deliverables", []) or [])
                 if (e.get("item") if isinstance(e, Mapping) else e) == item),
                None,
            )
            if conditional is not None:
                cells[offer["offer_id"]] = "conditional"
                if isinstance(conditional, Mapping) and conditional.get("condition"):
                    notes[offer["offer_id"]] = conditional["condition"]
            else:
                cells[offer["offer_id"]] = "not_included"
        rows.append({"dimension_item": item, "cells": cells, "notes": notes})
    exclusion_rows = []
    for offer in mains:
        for ex in offer.get("exclusions", []):
            exclusion_rows.append({"offer_id": offer["offer_id"], "exclusion": ex, "visibility": "material"})
    return {
        "offer_ids_in_order": [o["offer_id"] for o in mains],
        "offer_names": {o["offer_id"]: o.get("display_name", o["offer_id"]) for o in mains},
        "rows": rows,
        "exclusions": exclusion_rows,
    }


def build_recommendation(launch: Mapping[str, Any], recommendation: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """A recommendation exists only with an explicit, audience-tied reason.
    Unapproved recommendations are returned flagged for client review and
    must not be published (doc 08 s4). Popularity or savings language inside
    the reason itself is claim-checked like any other copy."""
    if not recommendation:
        return None
    offer_id = recommendation.get("offer_id")
    reason = (recommendation.get("reason") or "").strip()
    if offer_id not in {o["offer_id"] for o in _main_offers(launch)}:
        raise Violation(V_SELECTION_UNKNOWN_OFFER, f"Recommended offer {offer_id!r} is not a main offer.")
    if not reason:
        raise Violation(V_RECOMMENDATION_UNAPPROVED, "Recommendation without an explicit reason is not allowed.")
    scan_claims(reason, claim_evidence=recommendation.get("claim_evidence") or {})
    return {
        "offer_id": offer_id,
        "reason": reason,
        "approved_for_publication": bool(recommendation.get("approved")),
        "placement": "published" if recommendation.get("approved") else "client_review_only",
    }


def build_selection(
    launch: Mapping[str, Any],
    *,
    offer_id: str,
    price_choice_id: str,
    quantity: int = 1,
    selected_at: str,
    source_page_id: str,
    session_ref: str,
) -> Dict[str, Any]:
    """Construct selection.json intent. Carries the approved native mapping
    verbatim; contains no amount authority of its own beyond the approved
    catalog snapshot, no contact identity, and no payment fields. The
    selected price itself is approval-checked here: a caller cannot skip
    catalog validation and still mint a selection for an unapproved price."""
    offer = next((o for o in _main_offers(launch) if o["offer_id"] == offer_id), None)
    if offer is None:
        raise Violation(V_SELECTION_UNKNOWN_OFFER, f"Selected offer {offer_id!r} is not an approved main offer.")
    price = next((p for p in offer.get("prices", []) if p["price_choice_id"] == price_choice_id), None)
    if price is None:
        raise Violation(V_SELECTION_PRICE_DRIFT, f"Price choice {price_choice_id!r} is not on offer {offer_id!r}.")
    _check_price(price, offer_id)
    if not offer.get("native_product_id") or not price.get("native_price_id"):
        raise Violation(
            V_MISSING_NATIVE_MAPPING,
            f"Offer {offer_id!r} / price {price_choice_id!r} has no verified native "
            "product/price mapping; selection cannot hand off to checkout (A05).",
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "selection_intent_not_payment_evidence",
        "tenant_id": launch["tenant_id"],
        "location_id": launch["location_id"],
        "launch_id": launch["launch_id"],
        "revision": launch["revision"],
        "offer_id": offer_id,
        "price_choice_id": price_choice_id,
        "native_product_id": offer["native_product_id"],
        "native_price_id": price["native_price_id"],
        "currency": price["currency"],
        "amount_minor_snapshot": price["amount_minor"],
        "billing_type": price["billing_type"],
        "schedule": price.get("schedule") or [],
        "quantity": quantity,
        "selected_at": selected_at,
        "source_page_id": source_page_id,
        "session_ref": session_ref,
    }


def validate_binding(selection: Mapping[str, Any], launch: Mapping[str, Any], *, expected_revision: int) -> None:
    """Revalidate a selection against the current approved catalog at
    checkout time (doc 02 s5, doc 08 s7). Tenant, location, and launch must
    all match; the current price must still be approved; any drift in
    mapping, amount, or currency requires fresh visitor confirmation."""
    if (
        selection.get("tenant_id") != launch.get("tenant_id")
        or selection.get("location_id") != launch.get("location_id")
        or selection.get("launch_id") != launch.get("launch_id")
    ):
        raise Violation(V_SELECTION_TENANT, "Selection tenant/location/launch does not match the checkout launch.")
    if int(selection.get("revision", -1)) != int(expected_revision) or int(launch["revision"]) != int(expected_revision):
        raise Violation(V_SELECTION_STALE, "Selection revision is stale; the visitor must confirm current terms.")
    offer = next((o for o in _main_offers(launch) if o["offer_id"] == selection.get("offer_id")), None)
    if offer is None:
        raise Violation(V_SELECTION_UNKNOWN_OFFER, "Selected offer no longer exists in the approved catalog.")
    price = next((p for p in offer.get("prices", []) if p["price_choice_id"] == selection.get("price_choice_id")), None)
    if price is None:
        raise Violation(V_SELECTION_PRICE_DRIFT, "Selected price choice no longer exists on the offer.")
    if price.get("approval_status") not in APPROVED_STATUSES:
        raise Violation(
            V_UNAPPROVED_PRICE,
            f"Selected price {selection.get('price_choice_id')!r} is no longer approved "
            f"(status {price.get('approval_status')!r}); it cannot proceed to checkout.",
        )
    if offer.get("native_product_id") != selection.get("native_product_id") or price.get("native_price_id") != selection.get("native_price_id"):
        raise Violation(V_SELECTION_PRICE_DRIFT, "Native product/price mapping drifted between selection and checkout.")
    if price.get("amount_minor") != selection.get("amount_minor_snapshot") or price.get("currency") != selection.get("currency"):
        raise Violation(
            V_SELECTION_PRICE_DRIFT,
            "Material terms changed since selection; display the new terms for "
            "confirmation, never charge a changed amount invisibly.",
        )


def reject_query_authority(query: Mapping[str, Any]) -> None:
    """A URL may carry an opaque session reference only. Any price, amount,
    or offer-authority key in a query string is rejected outright."""
    banned = {"price", "amount", "amount_minor", "vip", "offer", "offer_id", "price_id", "currency"}
    hits = banned & {str(k).lower() for k in query.keys()}
    if hits:
        raise Violation(V_QUERY_AUTHORITY, f"Query keys {sorted(hits)} attempt billing/access authority; rejected.")
