"""Purchase-event adapter for Skill 82 (S82-05, offline half).

Turns a stream of normalized purchase events (packet purchase-event
shape; see packet reference/schemas/purchase-event.schema.json) into
verified normalized purchase snapshots — ONE per native order — in
exactly the shape thank_you_resolver.resolve_order_view consumes. The
adapter is a producer of snapshots; the resolver remains the one owner
of purchase truth, and this module never reimplements its rules (line
merging reuses the resolver's own deduplicate_line_items).

Contract (references/native-order-summary-integration.md):

- Identity: every event in one call must share one tenant/location/
  launch identity; a mixed-tenant or mixed-launch stream is rejected.
  Grouping is by native_order_ref only. The adapter has NO email or
  contact-identity input, so purchases can never be grouped by a
  shared email address; two orders stay two snapshots.
- An initial order can carry main plus bump in ONE event; later extras
  (U1/D1/U2) arrive as further events under the same native order and
  are appended to that order's snapshot.
- Redelivery: an identical repeated event (same event_id, identical
  content) is deduplicated; the same event_id with different content
  raises. Line merging inherits the resolver's duplicate semantics.
- Per-line payment truth: a line's own payment_status (fixture
  extension; "status" accepted as its alias) wins over the event-level
  payment_status.
- Refunds: a refund_observed event does not redeliver its lines, it
  UPDATES them. Folded in stream order over the purchase line it
  names (same native order): when every immutable line field the
  packet schema asserts (offer_id, slot, currency, amount_minor,
  entitlement_ids) matches the purchased line exactly and the status
  moves along the refund path (succeeded -> refunded /
  partially_refunded, partially_refunded -> refunded /
  partially_refunded), the snapshot line takes the refund's status
  and the refund event becomes that line's provenance — the current-
  state shape the resolver's fixtures and repair D-04 already use. A
  refund naming a line this order has not yet purchased in the
  stream, a refund whose line disagrees with the purchase on any
  immutable field, or a refund over a line that was never paid fails
  closed: a refund never invents or rewrites a purchase. The packet
  event shape carries no refunded-amount field, so a partial refund
  is a status fold only; the line keeps its full purchase amount,
  and the resolver already excludes partially refunded money from
  the paid total.
- Provenance: each snapshot line carries its own event_id — the line's
  extension value when present, else the deterministic
  "<event_id>::<native_line_ref>" of its source event — and the
  snapshot's event_ids manifest is exactly those IDs, satisfying the
  resolver's O-01 provenance cross-check.
- Verified: a snapshot is marked verified only when every contributing
  event carries a non-empty evidence_ref and a provider. With
  require_live_evidence=True (production mode), test_only events,
  test-marked providers, and evidence-less events are refused
  outright, so test evidence can never be promoted into production.
- Accepted event versions: "1.0", "1.1" (CR-S44-001) and "1.2"
  (CR-S44-003, S49 ruling;
  shared-utils/signature_launch/domain/purchase-event.schema.json v1.2).
  ACCEPTANCE ONLY: this adapter never stamps "1.1" or "1.2" — a
  producer stamping the event is a separate, later step - and the
  snapshot it exports stays schema_version "1.0". "1.1" is accepted
  because older producers still emit it (44 normalizer stamps "1.1" at
  tools/siglaunch/normalizer/normalizer.py:180 whenever a contact_ref
  is present), so refusing it would drop valid traffic today. "1.1"
  adds OPTIONAL contact_ref
  (purchase-event.v1.1.schema.json:48). "1.2" adds OPTIONAL
  parent_order_ref (opaque provider order id of the initial order, or
  null; purchase-event.schema.json:56). That field is NOT an identity,
  NOT a grouping or grant key and NOT an exported snapshot property:
  grouping stays native_order_ref, dedupe stays event_id, and the
  snapshot never carries it. The field is version-scoped exactly as the
  schemas are: it is defined only by a "1.2" stamp and is refused on
  both "1.0" and "1.1" (neither schema declares it, and both set
  additionalProperties false at line 4). Any other version fails
  closed.

Stdlib only. Deterministic: no clock, no randomness, no network.
"""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thank_you_resolver import (  # noqa: E402
    SNAPSHOT_SOURCE,
    ResolverError,
    deduplicate_line_items,
)

EVENT_TYPES = {
    "purchase_observed",
    "payment_updated",
    "refund_observed",
    "subscription_updated",
}

PAYMENT_STATUSES = {
    "pending",
    "succeeded",
    "failed",
    "requires_customer_action",
    "refunded",
    "partially_refunded",
    "unknown",
}

IDENTITY_KEYS = ("tenant_id", "location_id", "launch_id")

# Accepted purchase-event schema versions. "1.0" is the reviewed
# baseline; "1.1" is CR-S44-001 (still stamped by the 44 normalizer,
# normalizer.py:180); "1.2" is CR-S44-003 acceptance (see module
# docstring). Acceptance only: nothing here stamps a newer version.
ACCEPTED_SCHEMA_VERSIONS = ("1.0", "1.1", "1.2")

# The only version that defines parent_order_ref.
PARENT_ORDER_REF_VERSION = "1.2"

EVENT_REQUIRED = (
    "schema_version", "tenant_id", "location_id", "launch_id",
    "provider", "event_id", "event_type", "native_order_ref",
    "occurred_at", "received_at", "payment_status", "line_items",
    "evidence_ref", "test_only",
)

LINE_REQUIRED = (
    "native_line_ref", "offer_id", "slot", "currency",
    "amount_minor", "entitlement_ids",
)

DEFAULT_BILLING = {
    "billing_type": "one_time",
    "recurring_interval": None,
    "schedule": [],
    "terms_source": None,
}

# The immutable identity of a purchased line: the fields the packet
# purchase-event schema asserts for every line. A refund_observed
# event must restate them exactly to fold over the purchase; display
# name and billing terms are adapter-resolved presentation, not
# event-asserted identity, so the fold preserves the purchase's.
REFUND_IDENTITY_KEYS = (
    "offer_id", "slot", "currency", "amount_minor", "entitlement_ids",
)

# Lawful refund folds: (current line status, refund-reported status).
# A refund can only take money back from a line that captured it
# (succeeded) or extend an existing partial refund; a fully refunded
# line has nothing left to refund, and an unpaid line was never
# charged, so both fail closed rather than folding.
REFUND_TRANSITIONS = {
    ("succeeded", "refunded"),
    ("succeeded", "partially_refunded"),
    ("partially_refunded", "refunded"),
    ("partially_refunded", "partially_refunded"),
}


class AdapterError(ValueError):
    """Raised when no honest snapshot can be built from the stream."""


def _is_test_provider(provider):
    return isinstance(provider, str) and "TEST" in provider.upper()


def _canonical(event):
    return json.dumps(event, sort_keys=True, separators=(",", ":"))


def _require(mapping, key, where):
    if not isinstance(mapping, dict) or mapping.get(key) in (None, ""):
        raise AdapterError(f"missing_field: {where}.{key} is required")
    return mapping[key]


def _validate_parent_order_ref(event, where):
    """Validate the v1.2 parent_order_ref forms; never interpret the value.

    Allowed: absent, null, or a non-empty opaque string (schema type
    ["string", "null"], minLength 1). The value is opaque here — it is
    not resolved, not compared, not exported. The field is defined by
    the v1.2 schema ONLY (purchase-event.schema.json:56); neither
    purchase-event.v1.0.schema.json nor purchase-event.v1.1.schema.json
    declares it and both set additionalProperties false (line 4). So a
    "1.0" event carrying it is refused, and a "1.1" event carrying it
    is refused by exactly the same rule — 1.1 is not a 1.2 field
    carrier.
    """
    if "parent_order_ref" not in event:
        return
    if event["schema_version"] != PARENT_ORDER_REF_VERSION:
        raise AdapterError(
            f"invalid_parent_order_ref: {where}.parent_order_ref is defined "
            f"only by schema_version {PARENT_ORDER_REF_VERSION!r}; a "
            f"{event['schema_version']!r} event cannot carry it"
        )
    value = event["parent_order_ref"]
    if value is not None and (not isinstance(value, str) or value == ""):
        raise AdapterError(
            f"invalid_parent_order_ref: {where}.parent_order_ref must be an "
            "opaque non-empty string or null when present"
        )


def _validate_event(event, index):
    where = f"events[{index}]"
    if not isinstance(event, dict):
        raise AdapterError(f"invalid_event: {where} is not an object")
    for key in EVENT_REQUIRED:
        _require(event, key, where)
    if event["schema_version"] not in ACCEPTED_SCHEMA_VERSIONS:
        raise AdapterError(
            f"unsupported_schema_version: {where} schema_version "
            f"{event['schema_version']!r} is not accepted (accepted: "
            f"{', '.join(ACCEPTED_SCHEMA_VERSIONS)})"
        )
    _validate_parent_order_ref(event, where)
    if event["event_type"] not in EVENT_TYPES:
        raise AdapterError(
            f"invalid_event_type: {where} event_type {event['event_type']!r} "
            "is not a normalized purchase event type"
        )
    if event["payment_status"] not in PAYMENT_STATUSES:
        raise AdapterError(
            f"invalid_payment_status: {where} payment_status "
            f"{event['payment_status']!r} is not a normalized status"
        )
    if not isinstance(event["test_only"], bool):
        raise AdapterError(f"invalid_test_only: {where}.test_only must be a boolean")
    lines = event["line_items"]
    if not isinstance(lines, list) or not lines:
        raise AdapterError(
            f"empty_event: {where} carries no line items; an event without "
            "purchased lines proves nothing"
        )
    for line in lines:
        for key in LINE_REQUIRED:
            _require(line, key, f"{where}.line_item")
        status = line.get("payment_status", line.get("status"))
        if status is not None and status not in PAYMENT_STATUSES:
            raise AdapterError(
                f"invalid_payment_status: line {line.get('native_line_ref')!r} "
                f"in {where} has status {status!r}"
            )


def _dedupe_events(events):
    """Collapse identical redeliveries by event_id; conflict raises."""
    by_id = {}
    order = []
    for event in events:
        event_id = event["event_id"]
        if event_id in by_id:
            if _canonical(by_id[event_id]) != _canonical(event):
                raise AdapterError(
                    f"conflicting_event_redelivery: event_id {event_id!r} "
                    "arrived twice with different content; refusing to "
                    "guess which delivery is true"
                )
            continue  # identical duplicate event delivery: deduped
        by_id[event_id] = event
        order.append(event_id)
    return [by_id[event_id] for event_id in order]


def _catalog_billing(offer):
    price = (offer.get("prices") or [{}])[0]
    return {
        "billing_type": price.get("billing_type", "one_time"),
        "recurring_interval": None,
        "schedule": price.get("schedule", []),
        "terms_source": price.get("terms_source"),
    }


def _transform_line(event, line, offer_catalog):
    offer_id = line["offer_id"]
    offer = (offer_catalog or {}).get(offer_id) or {}
    billing = line.get("billing")
    if billing is None and offer:
        billing = _catalog_billing(offer)
    return {
        "native_line_ref": line["native_line_ref"],
        # One event can carry several lines, but the resolver's O-01
        # provenance check requires one event_id PER LINE: keep the
        # line's own extension value when present, else derive the
        # deterministic per-line ID from its source event.
        "event_id": line.get("event_id")
        or f"{event['event_id']}::{line['native_line_ref']}",
        "offer_id": offer_id,
        "slot": line["slot"],
        "display_name": line.get("display_name")
        or offer.get("display_name")
        or offer_id,
        "currency": line["currency"],
        "amount_minor": line["amount_minor"],
        "entitlement_ids": list(line["entitlement_ids"]),
        # Per-line payment truth wins over the event-level status.
        "payment_status": line.get("payment_status")
        or line.get("status")
        or event["payment_status"],
        "billing": copy.deepcopy(billing) if billing is not None
        else copy.deepcopy(DEFAULT_BILLING),
    }


def _fold_refund_update(existing, refund_line, refund_event):
    """Fold one refund_observed line over the purchase line it refunds.

    Returns the updated line: the purchase line with its payment
    status moved to the refund-reported status and its provenance
    moved to the refund event (the line's current state was set by
    the refund). Raises AdapterError when the refund does not name
    exactly this purchase or the status move is not a lawful refund.
    """
    ref = refund_line["native_line_ref"]
    for key in REFUND_IDENTITY_KEYS:
        if existing[key] != refund_line[key]:
            raise AdapterError(
                f"refund_mismatch: refund_observed event "
                f"{refund_event['event_id']!r} line {ref!r} disagrees "
                f"with the purchased line on {key} "
                f"({refund_line[key]!r} != {existing[key]!r}); refusing "
                "to guess purchase truth"
            )
    target = refund_line["payment_status"]
    current = existing["payment_status"]
    if (current, target) not in REFUND_TRANSITIONS:
        raise AdapterError(
            f"refund_not_applicable: refund_observed event "
            f"{refund_event['event_id']!r} reports status {target!r} "
            f"for native line {ref!r}, whose purchased status is "
            f"{current!r}; a refund can only fold over a paid or "
            "partially refunded purchase line"
        )
    folded = copy.deepcopy(existing)
    folded["payment_status"] = target
    folded["event_id"] = refund_line["event_id"]
    return folded


def _merge_order_lines(order_events, offer_catalog):
    """Transform one order's events into its deduplicated snapshot lines.

    Lines arrive in stream order. Non-refund lines accumulate and the
    resolver's own deduplicate_line_items keeps its exact semantics
    for them (identical redelivery collapses, conflicting redelivery
    raises). A refund_observed event instead folds over the line it
    refunds, replacing that line in place; a refund naming a line not
    yet purchased in this order's stream fails closed.
    """
    lines = []
    index = {}  # native_line_ref -> position in lines
    for event in order_events:
        for raw_line in event["line_items"]:
            line = _transform_line(event, raw_line, offer_catalog)
            ref = line["native_line_ref"]
            if event["event_type"] == "refund_observed":
                if ref not in index:
                    raise AdapterError(
                        f"refund_unknown_line: refund_observed event "
                        f"{event['event_id']!r} names native line "
                        f"{ref!r} of order "
                        f"{event['native_order_ref']!r}, but no "
                        "purchase line with that ref precedes it in "
                        "the stream; refusing to invent a purchase "
                        "to refund"
                    )
                lines[index[ref]] = _fold_refund_update(
                    lines[index[ref]], line, event)
                continue
            if ref not in index:
                index[ref] = len(lines)
            lines.append(line)
    try:
        return deduplicate_line_items(lines)
    except ResolverError as exc:
        raise AdapterError(str(exc)) from exc


def build_snapshots(events, journey_ids=None, offer_catalog=None,
                    revision=1, require_live_evidence=False):
    """Build one verified snapshot per native order from an event stream.

    events: list of normalized purchase events (packet shape).
    journey_ids: optional {native_order_ref: journey_id}; without it an
        event's journey_id extension wins, else a deterministic
        "journey:<native_order_ref>" is used.
    offer_catalog: optional {offer_id: offer} (launch-example shape)
        supplying display names / billing terms for lines that do not
        carry the fixture extension fields.
    revision: snapshot revision unless every contributing event agrees
        on its own revision extension.
    require_live_evidence: production mode — refuse test_only events,
        test-marked providers, and events without an evidence_ref.

    Returns {native_order_ref: snapshot}. Raises AdapterError when no
    honest snapshot can be built.
    """
    if not isinstance(events, list) or not events:
        raise AdapterError(
            "empty_stream: at least one normalized purchase event is required"
        )
    events = [copy.deepcopy(event) for event in events]
    for index, event in enumerate(events):
        _validate_event(event, index)

    identities = {tuple(event[key] for key in IDENTITY_KEYS) for event in events}
    if len(identities) != 1:
        raise AdapterError(
            "mixed_identity_stream: one adapter call covers exactly one "
            f"tenant/location/launch identity; got {sorted(identities)} — "
            "events are never sorted into the 'probably right' tenant"
        )
    tenant_id, location_id, launch_id = next(iter(identities))

    if require_live_evidence:
        for event in events:
            if event["test_only"] is True or _is_test_provider(event["provider"]):
                raise AdapterError(
                    "test_evidence_refused: require_live_evidence=True refuses "
                    f"test event {event['event_id']!r} (provider "
                    f"{event['provider']!r}); test evidence can never be "
                    "promoted into a production snapshot"
                )
            if not str(event["evidence_ref"]).strip():
                raise AdapterError(
                    "missing_evidence_ref: require_live_evidence=True refuses "
                    f"event {event['event_id']!r} without an evidence_ref"
                )

    events = _dedupe_events(events)

    by_order = {}
    for event in events:
        by_order.setdefault(event["native_order_ref"], []).append(event)

    snapshots = {}
    for order_ref, order_events in by_order.items():
        lines = _merge_order_lines(order_events, offer_catalog)

        revisions = {event["revision"] for event in order_events
                     if event.get("revision") is not None}
        if len(revisions) > 1:
            raise AdapterError(
                f"revision_conflict: events for order {order_ref!r} disagree "
                f"on revision {sorted(revisions)}"
            )
        snapshot_revision = revisions.pop() if revisions else revision

        journey_id = (journey_ids or {}).get(order_ref)
        if journey_id is None:
            journey_id = next(
                (event["journey_id"] for event in order_events
                 if event.get("journey_id")),
                f"journey:{order_ref}",
            )

        providers = {event["provider"] for event in order_events}
        evidence_refs = []
        for event in order_events:
            ref = str(event["evidence_ref"]).strip()
            if ref and ref not in evidence_refs:
                evidence_refs.append(ref)
        verified = all(
            str(event["evidence_ref"]).strip() for event in order_events
        ) and all(
            str(event["provider"]).strip() for event in order_events
        )

        snapshots[order_ref] = {
            "schema_version": "1.0",
            "tenant_id": tenant_id,
            "location_id": location_id,
            "launch_id": launch_id,
            "revision": snapshot_revision,
            "source": SNAPSHOT_SOURCE,
            "verified": verified,
            "provider": next(iter(providers)) if len(providers) == 1
            else ", ".join(sorted(providers)),
            "native_order_ref": order_ref,
            "native_transaction_ref": next(
                (event.get("native_transaction_ref") for event in order_events
                 if event.get("native_transaction_ref")),
                None,
            ),
            "journey_id": journey_id,
            "event_ids": [line["event_id"] for line in lines],
            "line_items": lines,
            "evidence_ref": "; ".join(evidence_refs),
            "test_only": any(
                event["test_only"] is True or _is_test_provider(event["provider"])
                for event in order_events
            ),
        }
    return snapshots


def build_snapshot(events, **kwargs):
    """Single-order convenience wrapper around build_snapshots."""
    snapshots = build_snapshots(events, **kwargs)
    if len(snapshots) != 1:
        raise AdapterError(
            "multiple_orders: stream covers "
            f"{sorted(snapshots)}; use build_snapshots for multi-order streams"
        )
    return next(iter(snapshots.values()))


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Build verified purchase snapshots from normalized "
        "purchase events (packet shape)."
    )
    parser.add_argument("--events", required=True,
                        help="JSON file holding a list of purchase events")
    parser.add_argument("--require-live-evidence", action="store_true",
                        help="production mode: refuse test/evidence-less events")
    args = parser.parse_args(argv)
    with open(args.events, encoding="utf-8") as fh:
        events = json.load(fh)
    try:
        snapshots = build_snapshots(
            events, require_live_evidence=args.require_live_evidence
        )
    except AdapterError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(snapshots, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
