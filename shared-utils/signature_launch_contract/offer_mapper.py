"""One canonical offer mapper: answers file -> launch record 1.2 -> Skill 78 plan -> Skill 79 checkout request.

The canonical offer is the Skill 49 launch record offer (schema 1.2: already hashed and approval-bound).
Every other view is generated from it here, never re-typed by a consumer, so a fact cannot be dropped or
renamed on a hop:

  answers_to_record(answers_doc, ...)          client-intake-answers/v1 -> launch record 1.2
  record_to_plan(record)                       record -> Skill 78 selection plan (78's own builder)
  record_to_checkout_request(record, id, ...)  record -> Skill 79 checkout_request (schema-valid)
  verify_provenance(answers_doc, offers)       refuse any offer whose provenance does not resolve
  resolve_offer(answers_doc, source_ref, ...)  the canonical offer a consumer's source_ref names (83 intake)

Provenance is never a constant. Each offer's source_ref is ``answers-file:<answer key>[<index>]`` (the
engine's own convention) and resolves to one entry of the answers file. The price's approval_status and the
offer's source_kind come from that entry's status: provided -> provided/owner; suggested or
default_to_confirm -> recommended_unapproved/recommendation; unknown -> refused.

Billing, exclusions and native ids are read from the answers entry (price.billing_type, exclusions,
native_product_id, native_price_id) or the client's billing answer. When billing is stated nowhere the
price is one_time AND a ``billing_not_stated`` line is returned for the client to confirm.

Stdlib only; Skill 78 is loaded from this repository on demand. Raises MapperError (stable ``code``).
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "1.2"
ANSWERS_SCHEMA = "client-intake-answers/v1"
REPO = Path(__file__).resolve().parents[2]
SLOTS = ("bump", "upsell_1", "downsell_1", "upsell_2")
REF = re.compile(r"^answers-file:([A-Za-z0-9_.]+)(?:\[(\d+)\])?$")
CHECKOUT_CONTEXT = ("approved_plan_hash", "brand_revision", "terms_ref", "native_capability_evidence_ref",
                    "successful_payment_next_route", "fulfillment_mapping_ref", "consent_ref",
                    "failed_pending_requirements")
_IMAGE_PROVIDER = {"connected": "kie", "none": "other_explicit"}  # same mapping as client_intake.to_launch_known


class MapperError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# The billing vocabulary and the record -> Skill 79 translation live in billing.py (one table, every importer).
_billing_vocab = _load("signature_launch_billing", Path(__file__).resolve().parent / "billing.py")
BILLING_TYPES = _billing_vocab.BILLING_TYPES
CHECKOUT_BILLING = _billing_vocab.CHECKOUT_BILLING


def _engine():
    return _load("client_intake_engine", REPO / "shared-utils" / "client_intake" / "engine.py")


def _78():
    # repo tree keeps Skill 78 at 78-signature-product-selection; a 999 install at .claude/skills/signature-product-selection
    d = next((p for p in (REPO / "78-signature-product-selection",
                          REPO / ".claude" / "skills" / "signature-product-selection") if p.is_dir()),
             REPO / "78-signature-product-selection")
    build = _load("build_selection_plan", d / "scripts" / "build_selection_plan.py")
    return build, sys.modules["selection_core"]


def currency_exponent(currency: str) -> int:
    """The currency's ISO 4217 minor-unit exponent. Skill 78 owns the table; this is the one door to it."""
    return _78()[1].currency_exponent(currency)


def format_money(amount_minor: int, currency: str) -> str:
    """An amount as a buyer reads it, with the currency's own exponent and symbol (Skill 78's rule)."""
    return _78()[1].format_money(amount_minor, currency)


# ---------------------------------------------------------------- answers -> offers
def _answer_items(doc: Mapping[str, Any]) -> List[Tuple[str, str, Optional[int], Dict[str, Any]]]:
    """[(slot, answers key, list index, item)] for every offer the answers file describes."""
    if doc.get("schema") != ANSWERS_SCHEMA:
        raise MapperError("AF-OFFER-ANSWERS-SCHEMA", f"expected {ANSWERS_SCHEMA}")
    ans = doc["answers"]
    val = lambda k: (ans.get(k) or {}).get("value")  # noqa: E731
    out: List[Tuple[str, str, Optional[int], Dict[str, Any]]] = []
    if val("packages"):
        out += [("main", "packages", i, p) for i, p in enumerate(val("packages"))]
    elif val("price") is not None:
        out.append(("main", "price", None, {"display_name": val("offer_name"), "price": val("price"),
                                            "deliverables": val("deliverables") or []}))
    else:
        raise MapperError("AF-OFFER-NO-MAIN", "the answers file has neither packages nor a price for the main offer")
    for slot in SLOTS:
        v = val(slot)
        if v in (None, "none"):
            continue
        if not isinstance(v, dict):
            raise MapperError("AF-OFFER-SHAPE", f"{slot} is not an offer with a name and a price: {v!r}")
        out.append((slot, slot, None, v))
    return out


def _billing(doc: Mapping[str, Any], price: Mapping[str, Any], where: str, to_confirm: List[Dict[str, str]]) -> str:
    own = price.get("billing_type")
    if own is not None:
        if own not in BILLING_TYPES:
            raise MapperError("AF-OFFER-BILLING", f"{where} billing_type {own!r} is not one of {BILLING_TYPES}")
        return own
    b = doc["answers"].get("billing")
    key = _engine()._billing_key(b["value"]) if b and b.get("status") != "unknown" else None
    if key:
        return key
    to_confirm.append({"field": f"billing:{where}", "reason": "billing_not_stated: no billing type was given for this "
                       "price, so it is treated as one payment.", "how_to_change": "Tell me how this offer is billed "
                       "(all at once, monthly, or in parts) and I will update it."})
    return "one_time"


def answers_to_offers(doc: Mapping[str, Any], *, test_only: bool = True) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """(launch record 1.2 offers, to_confirm lines). Refuses a price with no amount or an unknown status."""
    state, to_confirm, offers = _engine()._STATE, [], []
    items = _answer_items(doc)
    by_slot = {slot: None for slot in SLOTS}
    for slot, key, i, item in items:
        oid = item.get("offer_id") or (f"MAIN-{i + 1 if i is not None else 1}" if slot == "main" else slot.upper())
        if slot in by_slot:
            by_slot[slot] = oid
        offers.append((slot, key, i, item, oid))
    out = []
    for slot, key, i, item, oid in offers:
        where = f"{key}[{i}]" if i is not None else key
        status = doc["answers"][key]["status"]
        if state[status] == "unknown":
            raise MapperError("AF-OFFER-PRICE-UNKNOWN", f"{where}: the client has not given this price")
        price = item.get("price")
        amount = price.get("amount_minor") if isinstance(price, dict) else None
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise MapperError("AF-OFFER-PRICE-UNKNOWN", f"{where}: price has no whole-number amount_minor")
        if not re.fullmatch(r"[A-Z]{3}", str(price.get("currency"))):
            raise MapperError("AF-OFFER-PRICE-CURRENCY", f"{where}: price currency is not a 3-letter code")
        name = item.get("display_name")
        if not isinstance(name, str) or not name.strip():
            raise MapperError("AF-OFFER-NAME", f"{where}: the offer has no name")
        excludes = ([by_slot["downsell_1"]] if slot == "upsell_1" and by_slot["downsell_1"] else
                    [by_slot["upsell_1"]] if slot == "downsell_1" and by_slot["upsell_1"] else [])
        s = state[status]
        out.append({
            "offer_id": oid, "slot": slot, "display_name": name,
            "deliverables": list(item.get("deliverables") or []),
            "exclusions": list(item.get("exclusions") or []),
            "entitlement_ids": list(item.get("entitlement_ids") or [oid.lower()]),
            "requires": [], "excludes": excludes,
            "native_product_id": item.get("native_product_id"),
            "prices": [{
                "price_choice_id": f"{oid}-{price['currency']}", "currency": price["currency"],
                "amount_minor": amount, "billing_type": _billing(doc, price, where, to_confirm),
                "native_price_id": price.get("native_price_id"), "schedule": list(price.get("schedule") or []),
                "approval_status": s,
            }],
            "source_kind": "owner" if s == "provided" else "recommendation",
            "source_ref": f"answers-file:{where}",
            "test_only": test_only,
        })
    return out, to_confirm


def answers_to_record(doc: Mapping[str, Any], *, tenant_id: str, location_id: str, launch_id: str, revision: int,
                      brand_ref: str, brand_hash: str, route_graph_ref: str, route_graph_hash: str,
                      plan_approval_ref: Optional[str] = None, test_only: bool = True,
                      image_provider: Optional[str] = None) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """(launch record 1.2, to_confirm). The approval is carried, never minted: no plan_approval_ref means
    status awaiting_plan_approval."""
    offers, to_confirm = answers_to_offers(doc, test_only=test_only)
    ans = doc["answers"]
    roles = {o["slot"] for o in offers}
    mains = [o for o in offers if o["slot"] == "main"]
    mode = (ans.get("funnel_shape") or {}).get("value") or ("single_simple" if len(mains) == 1 else "multiple_options")
    provider = image_provider or (ans.get("image_provider") or {}).get("value")
    provider = _IMAGE_PROVIDER.get(provider, provider)
    if provider not in ("kie", "agnes", "other_explicit"):
        raise MapperError("AF-OFFER-IMAGE-PROVIDER", f"image provider {provider!r} is not known")
    return {
        "schema_version": SCHEMA_VERSION, "tenant_id": tenant_id, "location_id": location_id,
        "launch_id": launch_id, "revision": revision, "journey_mode": mode,
        "status": "approved" if plan_approval_ref else "awaiting_plan_approval",
        "brand_ref": brand_ref, "brand_hash": brand_hash,
        "route_graph_ref": route_graph_ref, "route_graph_hash": route_graph_hash,
        "plan_approval_ref": plan_approval_ref, "offers": offers,
        "extras": {s: s in roles for s in ("upsell_1", "downsell_1", "upsell_2")},
        "bump_enabled": "bump" in roles, "image_provider": provider,
        "source_refs": sorted({o["source_ref"] for o in offers}),
        "test_only": test_only,
    }, to_confirm


def resolve_offer(doc: Mapping[str, Any], source_ref: Any, *, slot: str, display_name: str, amount_minor: int,
                  currency: str, test_only: bool = True) -> Dict[str, Any]:
    """The canonical launch record offer that ``source_ref`` names in the answers file, for a consumer that holds
    its own copy of the offer (Skill 83 intake). Refuses a ref that does not resolve (AF-OFFER-SOURCE-REF) and a
    slot, name or price that is not what the answers entry says (AF-OFFER-PROVENANCE). Provenance, billing,
    exclusions and native ids are returned from the answers entry, never taken from the caller."""
    known = {o["source_ref"]: o for o in answers_to_offers(doc, test_only=test_only)[0]}
    if not isinstance(source_ref, str) or not REF.match(source_ref) or source_ref not in known:
        raise MapperError("AF-OFFER-SOURCE-REF", f"source_ref {source_ref!r} does not resolve to an entry in the "
                          "client's answers file")
    want = known[source_ref]
    p = want["prices"][0]
    for field, mine, theirs in (("slot", slot, want["slot"]), ("display_name", display_name, want["display_name"]),
                                ("price", (amount_minor, currency), (p["amount_minor"], p["currency"]))):
        if mine != theirs:
            raise MapperError("AF-OFFER-PROVENANCE", f"{field} {mine!r} is not what {source_ref} says ({theirs!r})")
    return want


def verify_provenance(doc: Mapping[str, Any], offers: Sequence[Mapping[str, Any]]) -> None:
    """Refuse an offer whose source_ref does not resolve to an answers entry, or whose name, price, status or
    source_kind is not what that entry says (a self-assigned 'approved'/'owner' is the forgery this catches)."""
    expected, _ = answers_to_offers(doc)
    known = {o["source_ref"]: o for o in expected}
    for o in offers:
        ref = o.get("source_ref")
        if not isinstance(ref, str) or not REF.match(ref) or ref not in known:
            raise MapperError("AF-OFFER-SOURCE-REF", f"offer {o.get('offer_id')!r}: source_ref {ref!r} does not "
                              "resolve to an entry in the client's answers file")
        want = known[ref]
        for field, mine, theirs in (
                ("display_name", o.get("display_name"), want["display_name"]), ("slot", o.get("slot"), want["slot"]),
                ("source_kind", o.get("source_kind"), want["source_kind"]),
                ("prices", [(p.get("amount_minor"), p.get("currency"), p.get("approval_status")) for p in o.get("prices") or []],
                 [(p["amount_minor"], p["currency"], p["approval_status"]) for p in want["prices"]])):
            if mine != theirs:
                raise MapperError("AF-OFFER-PROVENANCE", f"offer {o.get('offer_id')!r}: {field} {mine!r} is not what "
                                  f"{ref} says ({theirs!r})")


# ---------------------------------------------------------------- record -> 78 plan / 79 checkout
def record_to_plan(record: Mapping[str, Any], recommendation: Optional[Mapping[str, Any]] = None,
                   production: bool = False) -> Dict[str, Any]:
    """Skill 78's own plan builder over the record: one definition of the plan, no second copy here."""
    return _78()[0].build_plan(dict(record), recommendation, production=production)


def record_to_checkout_request(record: Mapping[str, Any], offer_id: str, *, checkout_mode: str,
                               price_choice_id: Optional[str] = None, quantity: int = 1,
                               selection_ref: Optional[str] = None, selection_revision: Optional[int] = None,
                               bump: Optional[Mapping[str, Any]] = None, **context: Any) -> Dict[str, Any]:
    """A Skill 79 checkout_request for one offer. ``context`` must carry every key in CHECKOUT_CONTEXT
    (hashes, refs and copy refs the record does not know); none is invented."""
    missing = [k for k in CHECKOUT_CONTEXT if context.get(k) in (None, "")]
    extra = sorted(set(context) - set(CHECKOUT_CONTEXT))
    if missing or extra:
        raise MapperError("AF-CHECKOUT-CONTEXT", f"missing {missing}, unexpected {extra}")
    if not record.get("plan_approval_ref"):
        raise MapperError("AF-CHECKOUT-UNAPPROVED", "the launch record carries no plan approval; nothing can be checked out")
    offer = next((o for o in record["offers"] if o["offer_id"] == offer_id), None)
    if offer is None:
        raise MapperError("AF-CHECKOUT-OFFER", f"offer {offer_id!r} is not in the launch record")
    prices = offer["prices"]
    price = next((p for p in prices if p["price_choice_id"] == price_choice_id), None) if price_choice_id else (
        prices[0] if len(prices) == 1 else None)
    if price is None:
        raise MapperError("AF-CHECKOUT-PRICE", f"offer {offer_id!r}: name one of {[p['price_choice_id'] for p in prices]}")
    billing = CHECKOUT_BILLING[price["billing_type"]]
    if billing is None:
        raise MapperError("AF-CHECKOUT-BILLING", f"Skill 79 has no checkout billing type for {price['billing_type']!r}; "
                          "refused rather than shown as something else")
    status = price["approval_status"]
    if status not in ("provided", "approved", "recommended_unapproved"):
        raise MapperError("AF-CHECKOUT-PRICE", f"price status {status!r} cannot go to checkout")
    main_price = {
        "price_choice_id": price["price_choice_id"], "currency": price["currency"],
        "currency_exponent": _78()[1].currency_exponent(price["currency"]), "amount_minor": price["amount_minor"],
        "billing_type": billing, "native_product_id": offer["native_product_id"],
        "native_price_id": price["native_price_id"],
        "approval_status": "recommended_unapproved" if status == "recommended_unapproved" else "approved",
    }
    if price["schedule"]:
        main_price["schedule"] = [{"sequence": n, **row} for n, row in enumerate(price["schedule"], 1)]
    return {
        "tenant_id": record["tenant_id"], "location_id": record["location_id"], "launch_id": record["launch_id"],
        "launch_revision": record["revision"], "launch_plan_approval_ref": record["plan_approval_ref"],
        "checkout_mode": checkout_mode, "main_offer_id": offer_id, "main_price": main_price, "quantity": quantity,
        "selection_ref": selection_ref, "selection_revision": selection_revision,
        "main_entitlement_ids": list(offer["entitlement_ids"]), "previously_purchased_entitlement_ids": [],
        "bump": dict(bump) if bump else None, "brand_ref": record["brand_ref"], "test_only": record["test_only"],
        **{k: context[k] for k in CHECKOUT_CONTEXT},
    }
