"""Entitlement-to-block resolver for Skill 82 (S82-03).

One authoritative resolver owns purchase truth for the terminal thank-you
page. Input is a VERIFIED normalized purchase snapshot for ONE journey
(packet purchase-event shape, extended per line item with payment_status,
display_name and billing terms) plus the S44 entitlement/fulfillment map.
Output is the order view (schemas/order-view.schema.json).

Rules enforced here (packet doc 12 sections 2, 3, 5, 6; doc 18 A13/A20):
- Nothing is built from URL/query claims, page-visit history, or email
  matching. Without a verified snapshot there is no view.
- Tenant/location/launch identity must match the expected identity.
- Duplicate event delivery is deduplicated by native line reference:
  an identical redelivery collapses; a conflicting one is an error.
- Display shows exactly the purchased items, with integer minor-unit
  amounts and per-item status separated (paid / pending / failed / ...).
- Access blocks are keyed to purchased entitlement IDs and S44
  fulfillment state; only paid items with granted fulfillment produce
  access blocks. A pending/failed extra never removes base access (A20).
- A pending item anywhere forbids the "You are all set" confirmation.
- A refunded / partially refunded item also forbids it (repair D-04):
  the receipt row stays, honestly labeled, with a refund confirmation
  status instead.
- U2 requires a paid U1 or D1 in the same journey (repair D-02), and an
  S44 next_action outside the approved classifications fails closed
  (repair D-05).
- The snapshot's top-level event_ids manifest must exactly match the
  event_id values on its (deduplicated) line items (observation O-01):
  provenance may neither over-claim events no line carries nor
  under-claim lines the manifest omits, and two distinct lines may not
  share one event_id.
- Raw payment credential fields anywhere in the input are rejected.
- S44's order-level entitlement version (the ev1 value of CR-S82-002
  item 5) is carried through to the view's `entitlement_version` field
  when S44 supplies one — on the fulfillment-map producer envelope or
  as the resolver's explicit version input — so the confirmation
  dedupe key (contract section 3) can be the ev1-based key the S44
  worker checks. Only a well-formed ev1 value is carried; any other
  shape fails closed, and a version supplied for a different
  tenant/launch than the verified snapshot is rejected. With no
  version supplied the view carries no such field and is identical to
  the pre-ev1 shape (gap I6).

Stdlib only. Deterministic: no clock, no randomness, no network.
"""

import copy
import re

SNAPSHOT_SOURCE = "verified_normalized_purchase_snapshot"

SLOT_ORDER = {"main": 0, "bump": 1, "upsell_1": 2, "downsell_1": 3, "upsell_2": 4}

# Approved thank-you CTA classifications (spec 12 section 7; no-pitch
# policy section 2). An S44 next_action outside this set is not a lawful
# thank-you action — the resolver fails closed on it (repair D-05).
ALLOWED_NEXT_ACTIONS = {
    "access",
    "download",
    "manage_purchase",
    "support",
    "schedule_included_service",
    "noncommercial_next_step",
}

# Payment statuses that mean money was given back. Such an item keeps its
# historical receipt row but is never "confirmed" (repair D-04).
REFUNDED_STATUSES = ("refunded", "partially_refunded")

# S44's order-level entitlement version (CR-S82-002 item 5): "ev1:" plus
# the lowercase sha256 hex of S44's canonical entitlement-book string.
# The prefix versions the canonicalization algorithm, so this exact
# shape is the only lawful version value; anything else is mismatched
# or forged and is never carried into a view.
ENTITLEMENT_VERSION_PATTERN = re.compile(r"^ev1:[0-9a-f]{64}$")

# Normalized display status per snapshot payment_status.
DISPLAY_STATUS = {
    "succeeded": "paid",
    "pending": "pending",
    "failed": "failed",
    "requires_customer_action": "requires_customer_action",
    "refunded": "refunded",
    "partially_refunded": "partially_refunded",
    "unknown": "unknown",
}

FORBIDDEN_KEYS = {
    "card_number", "cardnumber", "pan", "cvv", "cvc", "card_cvc",
    "card_expiry", "card_exp", "expiry", "password", "secret",
    "payment_token", "card_token",
}

IDENTITY_KEYS = ("tenant_id", "location_id", "launch_id")


class ResolverError(ValueError):
    """Raised when no honest order view can be built from the input."""


def _scan_forbidden(obj, path="$"):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise ResolverError(
                    "forbidden_field: raw payment credential field "
                    f"'{key}' at {path} must never enter a thank-you request"
                )
            _scan_forbidden(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            _scan_forbidden(value, f"{path}[{i}]")


def _require(mapping, key, where):
    if not isinstance(mapping, dict) or mapping.get(key) in (None, ""):
        raise ResolverError(f"missing_field: {where}.{key} is required")
    return mapping[key]


def deduplicate_line_items(line_items):
    """Collapse identical duplicate deliveries by native_line_ref.

    A repeated event (same native line, identical content) is one purchase.
    The same native line arriving with different content is a conflict and
    is never silently merged.
    """
    by_ref = {}
    order = []
    for raw in line_items:
        line = copy.deepcopy(raw)
        ref = _require(line, "native_line_ref", "line_item")
        _require(line, "event_id", "line_item")
        _require(line, "offer_id", "line_item")
        if line.get("slot") not in SLOT_ORDER:
            raise ResolverError(f"invalid_slot: {line.get('slot')!r} on line {ref}")
        if line.get("payment_status") not in DISPLAY_STATUS:
            raise ResolverError(
                f"invalid_payment_status: {line.get('payment_status')!r} on line {ref}"
            )
        amount = line.get("amount_minor")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            raise ResolverError(f"invalid_amount_minor: {amount!r} on line {ref}")
        if ref in by_ref:
            if by_ref[ref] != line:
                raise ResolverError(
                    f"duplicate_conflict: native line {ref} redelivered with "
                    "different content; refusing to guess purchase truth"
                )
            continue  # identical duplicate event delivery: deduped
        by_ref[ref] = line
        order.append(ref)
    return [by_ref[ref] for ref in order]


def event_provenance_problem(snapshot, lines):
    """Cross-check the snapshot's event_ids manifest against its lines.

    Returns a named ``event_id_mismatch`` problem string, or None when
    the manifest exactly matches the event_id values on the
    (deduplicated) line items. Observation O-01: provenance event_ids
    used to be copied from the snapshot manifest without ever checking
    that list against the lines, so a snapshot whose manifest disagreed
    with its lines produced a view whose provenance over- or
    under-claimed. Failing closed here keeps provenance honest.

    An identical duplicate delivery never reaches this check as two
    lines: deduplicate_line_items has already collapsed it (same
    native_line_ref, identical content), so its single event_id appears
    exactly once in ``lines`` and once in an honest manifest.
    """
    line_event_ids = [line["event_id"] for line in lines]
    shared = sorted({e for e in line_event_ids if line_event_ids.count(e) > 1})
    if shared:
        return (
            f"event_id_mismatch: distinct line items share event_id(s) "
            f"{shared}; each purchased line must carry its own event_id"
        )
    manifest = snapshot.get("event_ids") if isinstance(snapshot, dict) else None
    if not isinstance(manifest, list):
        return (
            "event_id_mismatch: snapshot event_ids manifest is missing "
            "or not a list; provenance cannot be cross-checked against "
            "its line items"
        )
    repeated = sorted({e for e in manifest if manifest.count(e) > 1})
    if repeated:
        return (
            f"event_id_mismatch: snapshot event_ids manifest repeats "
            f"event_id(s) {repeated} that its line items carry only once"
        )
    line_set = set(line_event_ids)
    manifest_set = set(manifest)
    if manifest_set != line_set:
        return (
            "event_id_mismatch: snapshot event_ids manifest does not "
            f"match its line items (on_no_line={sorted(manifest_set - line_set)}, "
            f"missing_from_manifest={sorted(line_set - manifest_set)}); "
            "provenance must neither over- nor under-claim events"
        )
    return None


def check_event_provenance(snapshot, lines):
    """Fail closed (ResolverError) when the O-01 cross-check fails."""
    problem = event_provenance_problem(snapshot, lines)
    if problem is not None:
        raise ResolverError(problem)


def resolve_order_view(snapshot, fulfillment_map=None, expected_identity=None,
                       request_context=None, entitlement_version=None):
    """Build the order view from a verified purchase snapshot.

    snapshot: verified normalized purchase snapshot (see request schema).
    fulfillment_map: S44 entitlement state keyed by entitlement_id,
        {entitlement_id: {"state": "granted|pending|not_granted|revoked",
                          "delivery_url": str|None, "next_action": str|None}}.
        The S44 producer envelope shape is also accepted:
        {"tenant_id":..., "launch_id":..., "contact_ref":...,
         "entitlement_version": "ev1:...", "entitlements": <the map>};
        the inner entitlements dict is then the map and the envelope's
        order-level version is the incoming entitlement_version.
    expected_identity: {"tenant_id":..., "location_id":..., "launch_id":...}
        the identity this page instance is authorized to render for.
    request_context: accepted only to prove it is ignored as authority —
        query parameters never change the view; a context that tries to
        claim entitlements is rejected.
    entitlement_version: S44's order-level ev1 entitlement version for
        this buyer's entitlement state, when the caller supplies it
        directly; overrides the producer envelope's value when both are
        given. Carried through to the view only when well-formed.
    """
    fulfillment_map = fulfillment_map or {}

    # S44 producer envelope (CR-S82-002): the version rides at order
    # level on the envelope, never inside the bare map. A bare map can
    # never satisfy this shape — its values are entry objects, so an
    # "entitlements" entry would be an object (not the inner map dict
    # paired with a string version) and an "entitlement_version" entry
    # would be an object, not a string.
    envelope = None
    if (isinstance(fulfillment_map, dict)
            and isinstance(fulfillment_map.get("entitlements"), dict)
            and isinstance(fulfillment_map.get("entitlement_version"), str)):
        envelope = fulfillment_map
        fulfillment_map = envelope["entitlements"]
        if entitlement_version is None:
            entitlement_version = envelope["entitlement_version"]

    if request_context:
        claims = request_context.get("claimed_entitlement_ids") or []
        query = request_context.get("query_params") or {}
        authority_keys = {"vip", "entitlement", "entitlements", "offer",
                          "offer_id", "tier", "plan", "access"}
        bad_query = sorted(k for k in query if str(k).lower() in authority_keys)
        if claims or bad_query:
            raise ResolverError(
                "query_string_authority_rejected: URL/query claims "
                f"(claims={list(claims)}, params={bad_query}) are never "
                "authority for access or display"
            )

    if not isinstance(snapshot, dict):
        raise ResolverError(
            "unverified_snapshot: a verified normalized purchase snapshot "
            "is required; URL claims and page visits build nothing"
        )
    _scan_forbidden(snapshot)
    _scan_forbidden(fulfillment_map)
    if snapshot.get("source") != SNAPSHOT_SOURCE or snapshot.get("verified") is not True:
        raise ResolverError(
            "unverified_snapshot: snapshot must declare source "
            f"'{SNAPSHOT_SOURCE}' and verified=true"
        )
    if snapshot.get("schema_version") != "1.0":
        raise ResolverError("unsupported_schema_version: snapshot schema_version must be '1.0'")

    for key in IDENTITY_KEYS + ("revision", "native_order_ref", "journey_id"):
        _require(snapshot, key, "snapshot")

    if expected_identity:
        for key in IDENTITY_KEYS:
            expected = expected_identity.get(key)
            if expected is not None and snapshot.get(key) != expected:
                raise ResolverError(
                    f"identity_mismatch: snapshot {key}={snapshot.get(key)!r} "
                    f"does not match expected {expected!r} "
                    f"({'wrong_tenant' if key == 'tenant_id' else 'wrong_scope'})"
                )

    # Order-level entitlement version (gap I6): the ev1 value S44
    # computes over its entitlement book (CR-S82-002 item 5) is the
    # version component of the joint confirmation dedupe key (contract
    # section 3). An envelope naming a different tenant/launch than the
    # verified snapshot belongs to another buyer's state and is
    # rejected; a version that is not a well-formed ev1 value fails
    # closed here rather than poisoning the dedupe key — the schema
    # (order-view.schema.json) enforces the same shape on the view.
    if envelope is not None:
        for key in ("tenant_id", "launch_id"):
            named = envelope.get(key)
            if named is not None and named != snapshot.get(key):
                raise ResolverError(
                    f"identity_mismatch: fulfillment envelope {key}="
                    f"{named!r} does not match snapshot "
                    f"{snapshot.get(key)!r} (wrong_scope)"
                )
    if entitlement_version is not None:
        if (not isinstance(entitlement_version, str)
                or not ENTITLEMENT_VERSION_PATTERN.match(entitlement_version)):
            raise ResolverError(
                "invalid_entitlement_version: "
                f"{entitlement_version!r} is not a well-formed ev1 value "
                "('ev1:' + 64 lowercase hex); refusing to carry a "
                "mismatched or forged version into the view"
            )

    lines = deduplicate_line_items(snapshot.get("line_items") or [])
    if not lines:
        raise ResolverError(
            "empty_snapshot: no purchased line items; a direct URL without "
            "a purchase has no receipt to show"
        )
    # O-01: the manifest the provenance block will copy must be proven
    # against the deduplicated lines before anything is built from it.
    check_event_provenance(snapshot, lines)
    slots = [line["slot"] for line in lines]
    if "main" not in slots:
        raise ResolverError("missing_main: extras without a main purchase cannot resolve")
    if "upsell_1" in slots and "downsell_1" in slots:
        raise ResolverError("mutually_exclusive: U1 and D1 cannot both be purchased")
    if "upsell_2" in slots:
        # Qualification rule (repair D-02; doc 12 section 3, doc 02
        # section 4): U2 is reachable only after a SUCCESSFUL U1 or D1
        # purchase in this same journey. The resolver owns purchase
        # truth, so it fails closed here rather than trusting that an
        # upstream stage could never emit an unqualified U2.
        paid_slots = {line["slot"] for line in lines
                      if line["payment_status"] == "succeeded"}
        if not ({"upsell_1", "downsell_1"} & set(slots)):
            raise ResolverError(
                "u2_without_qualification: upsell_2 is present but neither "
                "upsell_1 nor downsell_1 was purchased in this journey; U2 "
                "requires a successful U1 or D1 purchase first"
            )
        if not ({"upsell_1", "downsell_1"} & paid_slots):
            raise ResolverError(
                "u2_without_qualification: upsell_2 is present but no PAID "
                "upsell_1 or downsell_1 purchase qualifies it in this journey"
            )

    currencies = {line["currency"] for line in lines}
    if len(currencies) != 1:
        raise ResolverError(f"mixed_currency: {sorted(currencies)} in one snapshot")
    currency = lines[0]["currency"]

    lines.sort(key=lambda l: (SLOT_ORDER[l["slot"]], l["native_line_ref"]))

    items = []
    access_blocks = []
    ctas = []
    pending_items, failed_items = [], []
    refunded_items, partially_refunded_items = [], []
    paid_total = 0
    pending_total = 0

    for line in lines:
        status = DISPLAY_STATUS[line["payment_status"]]
        item = {
            "offer_id": line["offer_id"],
            "slot": line["slot"],
            "display_name": line["display_name"],
            "amount_minor": line["amount_minor"],
            "currency": line["currency"],
            "display_status": status,
            "entitlement_ids": list(line["entitlement_ids"]),
            "native_line_ref": line["native_line_ref"],
            "event_id": line["event_id"],
            "billing": copy.deepcopy(line["billing"]),
        }
        items.append(item)
        if status == "paid":
            paid_total += line["amount_minor"]
        elif status in ("pending", "requires_customer_action", "unknown"):
            pending_items.append(line["offer_id"])
            pending_total += line["amount_minor"]
        elif status == "failed":
            failed_items.append(line["offer_id"])
        elif status == "refunded":
            refunded_items.append(line["offer_id"])
        elif status == "partially_refunded":
            partially_refunded_items.append(line["offer_id"])

        # Access blocks: purchased entitlement IDs + S44 fulfillment state.
        # Only paid items with granted fulfillment produce access. A failed
        # or pending extra simply yields no block — base blocks already
        # emitted stay untouched (A20).
        if status != "paid":
            continue
        for entitlement_id in line["entitlement_ids"]:
            entry = fulfillment_map.get(entitlement_id) or {}
            if entry.get("state") != "granted":
                continue
            action = entry.get("next_action") or "access"
            if action not in ALLOWED_NEXT_ACTIONS:
                # Fail closed (repair D-05): an unapproved S44 next_action
                # (e.g. a sales action like "buy_more") must never pass
                # through into a view unsanitized.
                raise ResolverError(
                    f"invalid_next_action: S44 fulfillment next_action "
                    f"{action!r} for entitlement {entitlement_id} is not an "
                    "approved thank-you action classification; failing closed"
                )
            block = {
                "entitlement_id": entitlement_id,
                "offer_id": line["offer_id"],
                "slot": line["slot"],
                "next_action": action,
                "delivery_url": entry.get("delivery_url"),
                "fulfillment_state": "granted",
            }
            access_blocks.append(block)
            ctas.append({
                "classification": action,
                "label": f"{action.replace('_', ' ').title()}: {line['display_name']}",
                "offer_id": line["offer_id"],
                "entitlement_id": entitlement_id,
                "initiates_new_charge": False,
            })

    if failed_items and pending_items:
        conf_status, all_set = "attention_required", False
        headline = ("Your confirmed purchases are shown below. Some items "
                    "need attention and are labeled individually.")
    elif pending_items:
        conf_status, all_set = "partially_pending", False
        headline = ("Your confirmed purchases are ready below. Items still "
                    "pending are labeled and are not confirmed yet.")
    elif failed_items:
        conf_status, all_set = "attention_required", False
        headline = ("Your confirmed purchases are ready below. A failed "
                    "item is labeled separately and does not affect them.")
    elif refunded_items:
        # Repair D-04: refunded money is not a confirmed purchase. The
        # item keeps its historical receipt row, honestly labeled, and
        # any still-paid items remain confirmed below — but the page
        # never claims "all set" over a refund.
        conf_status, all_set = "refund_applied", False
        headline = ("A refund was applied to this order, so it is not "
                    "fully confirmed. Each item below is labeled with "
                    "its current state, and items still in effect "
                    "remain confirmed.")
    elif partially_refunded_items:
        conf_status, all_set = "partially_refunded", False
        headline = ("Part of this order was refunded, so it is not "
                    "fully confirmed. Each item below is labeled with "
                    "its current state, and items still in effect "
                    "remain confirmed.")
    else:
        conf_status, all_set = "confirmed", True
        headline = "You are all set. Your purchase is confirmed."

    ctas.append({
        "classification": "support",
        "label": "Contact support",
        "offer_id": None,
        "entitlement_id": None,
        "initiates_new_charge": False,
    })
    ctas.append({
        "classification": "manage_purchase",
        "label": "Manage your purchase",
        "offer_id": None,
        "entitlement_id": None,
        "initiates_new_charge": False,
    })

    view = {
        "schema_version": "1.0",
        "tenant_id": snapshot["tenant_id"],
        "location_id": snapshot["location_id"],
        "launch_id": snapshot["launch_id"],
        "revision": snapshot["revision"],
        "order_ref": snapshot["native_order_ref"],
        "order_number": snapshot["native_order_ref"],
        "journey_id": snapshot["journey_id"],
        "confirmation": {
            "status": conf_status,
            "all_set": all_set,
            "headline": headline,
        },
        "items": items,
        "totals": {
            "currency": currency,
            "paid_total_minor": paid_total,
            "pending_total_minor": pending_total,
        },
        "access_blocks": access_blocks,
        "ctas": ctas,
        "pending_items": pending_items,
        "failed_items": failed_items,
        "recommendations": [],
        "provenance": {
            "source": SNAPSHOT_SOURCE,
            "built_from_verified_snapshot": True,
            "event_ids": list(snapshot.get("event_ids") or []),
        },
        "test_only": bool(snapshot.get("test_only", False)),
    }
    if entitlement_version is not None:
        # Carried through only when S44 supplied a well-formed ev1
        # value; when none was supplied the field stays absent, the
        # view is identical to the pre-ev1 shape, and the confirmation
        # observation derives its fingerprint fallback (gap I6).
        view["entitlement_version"] = entitlement_version
    return view
