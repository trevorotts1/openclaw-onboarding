"""S79-08 purchase-event handoff fixture (doc 09 sections 8 and 9, doc 02
section 8, doc 14 section 4, acceptance A09/A17/A20).

Builds the normalized purchase event and the purchase-automation-request
from a VERIFIED paid attempt only, and models the S44-side entitlement
grant at fixture level: one initial event can carry main plus bump line
items, each entitlement is granted exactly once per verified event/action
identity, a repeated delivery of the same event grants nothing twice, and
a forged or unpaid event grants nothing at all.

This is a contract fixture. The real S44 consumer must execute against
native records and return read-backs; nothing here talks to GHL.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

PACKET_EVENT_SCHEMA = (Path(__file__).resolve().parents[1] / "fixtures" / "packet"
                       / "schemas" / "purchase-event.schema.json")


class HandoffError(ValueError):
    pass


# Schema 1.2 acceptance (CR-S44-003): the packet reference now carries
# the 1.2 schema beside the 1.0 one, so both versions resolve. The 1.0
# file and what this fixture emits are unchanged — it still stamps 1.0.
# Unknown versions fail closed.
PACKET_EVENT_SCHEMA_V12 = (PACKET_EVENT_SCHEMA.parent
                           / "purchase-event.v1.2.schema.json")
_PACKET_EVENT_SCHEMAS = {
    "1.0": PACKET_EVENT_SCHEMA,
    "1.2": PACKET_EVENT_SCHEMA_V12,
}


def load_packet_event_schema(version: str) -> dict:
    """Resolve the packet purchase-event schema for a schema_version.
    An unknown, missing, or non-string version fails closed."""
    if not isinstance(version, str) or version not in _PACKET_EVENT_SCHEMAS:
        raise HandoffError(
            f"unsupported packet purchase-event schema_version {version!r}: "
            f"fail closed (installed schemas: "
            f"{sorted(_PACKET_EVENT_SCHEMAS)})")
    path = _PACKET_EVENT_SCHEMAS[version]
    if not path.exists():
        raise HandoffError(
            f"packet purchase-event schema {version} not found: {path}")
    return json.loads(path.read_text())


def validate_packet_event(event: dict) -> dict:
    """Validate an event against the packet schema for its stamped
    schema_version. 1.0 validates exactly as before; 1.2 is accepted
    with its optional parent_order_ref; an unknown, missing, or
    non-string version fails closed."""
    version = event.get("schema_version") if isinstance(event, dict) else None
    schema = load_packet_event_schema(version)
    jsonschema.validate(event, schema)
    return event


def build_purchase_event(*, attempt, tenant_id: str, location_id: str, launch_id: str,
                         native_order_ref: str, native_transaction_ref: str | None,
                         occurred_at: str, received_at: str, evidence_ref: str,
                         line_items: list, test_only: bool = True) -> dict:
    """`attempt` is a purchase_state.PurchaseAttempt. Only a paid attempt may
    emit a succeeded event; the caller supplies native line items read back
    from the native order, never amounts invented in the browser."""
    if attempt.state != "paid" or not attempt.can_traverse_paid_edge():
        raise HandoffError("only a verified paid attempt may emit a purchase event")
    if not line_items:
        raise HandoffError("a purchase event requires at least the main line item")
    slots = [li["slot"] for li in line_items]
    if slots.count("main") != 1:
        raise HandoffError("exactly one main line item is required")
    if slots.count("bump") > 1:
        raise HandoffError("at most one bump line item per initial event")
    event = {
        "schema_version": "1.0",
        "tenant_id": tenant_id,
        "location_id": location_id,
        "launch_id": launch_id,
        "provider": "convert_and_flow_native",
        "event_id": f"evt-{tenant_id}-{native_order_ref}",
        "event_type": "purchase_observed",
        "native_order_ref": native_order_ref,
        "native_transaction_ref": native_transaction_ref,
        "occurred_at": occurred_at,
        "received_at": received_at,
        "payment_status": "succeeded",
        "line_items": line_items,
        "evidence_ref": evidence_ref,
        "test_only": test_only,
    }
    try:
        validate_packet_event(event)
    except jsonschema.ValidationError as exc:
        raise HandoffError(f"event fails the packet purchase-event schema: {exc.message}") from exc
    return event


def build_automation_request(*, event: dict, checkout_result_ref: str) -> dict:
    """purchase-automation-request.json shape (doc 09 section 9): IDs and
    approved behavior only, no secrets."""
    return {
        "schema_version": "0.1-draft",
        "tenant_id": event["tenant_id"],
        "location_id": event["location_id"],
        "launch_id": event["launch_id"],
        "source_event_id": event["event_id"],
        "native_order_ref": event["native_order_ref"],
        "checkout_result_ref": checkout_result_ref,
        "line_items": event["line_items"],
        "approved_behavior": {
            "grant_each_entitlement_exactly_once": True,
            "initiate_fulfillment_without_waiting_for_upsell_chain": True,
            "suppress_obsolete_abandonment_after_purchase": True,
        },
        "test_only": event["test_only"],
    }


@dataclass
class EntitlementGrantor:
    """Fixture model of the S44 action ledger: dedupe by TENANT plus verified
    event identity plus action identity, never by contact alone (doc 02
    section 8, doc 14 section 5). Review defect C1: the original key omitted
    the tenant, so one tenant's grant could suppress another tenant's
    legitimate grant for the same entitlement."""
    granted: set = field(default_factory=set)  # {(tenant_id, event_id, entitlement_id)}
    grant_log: list = field(default_factory=list)

    def apply(self, event: dict) -> list:
        # Review defect C2: the granting boundary validates what it is
        # handed. A dict merely claiming `succeeded` grants nothing; the
        # event must satisfy the packet purchase-event schema (tenant,
        # location, order ref, evidence ref, line items) AND be succeeded.
        try:
            validate_packet_event(event)
        except jsonschema.ValidationError as exc:
            raise HandoffError(f"unvalidated event refused at the granting boundary: {exc.message}") from exc
        except HandoffError as exc:
            raise HandoffError(f"unvalidated event refused at the granting boundary: {exc}") from exc
        if event.get("event_type") != "purchase_observed":
            # Review defect N2: a refund_observed or payment_updated event
            # must never grant entitlements, even if it claims succeeded.
            raise HandoffError("entitlements are granted only from purchase_observed events")
        if event.get("payment_status") != "succeeded":
            raise HandoffError("entitlements are granted only from validated successful transactions")
        newly = []
        for line in event["line_items"]:
            for entitlement in line["entitlement_ids"]:
                key = (event["tenant_id"], event["event_id"], entitlement)
                if key in self.granted:
                    continue
                self.granted.add(key)
                self.grant_log.append(key)
                newly.append(entitlement)
        return newly
