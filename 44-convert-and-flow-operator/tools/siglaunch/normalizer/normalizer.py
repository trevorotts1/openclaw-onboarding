"""S44-04 production normalizer (DESIGN-S44-04-v1.md).

Converts a native order/transaction read-back into the canonical
purchase-event envelope, or into a QUARANTINE record — the only response
to ambiguity. Unlike the L1 reference (events.py, which raises), this
module returns quarantine as data and persists it as a visible review
item in the durable store; nothing quarantined grants, tags, enrolls,
or sends.

Rules enforced here (design sections 3-8):
- slot comes ONLY from verified bindings; the native submission label
  is never read (it says 'Upsell' for U1, D1 and U2 alike);
- payment_status comes ONLY from the verified native transaction
  status; a submission without a transaction status is `unknown`,
  which never grants; a status outside the schema enum quarantines,
  never coerces;
- identity is the verified provider event id within tenant; absent or
  empty quarantines; transaction refs are never synthesized;
- tenant/location/launch must match the launch context the bindings
  came from, or the event quarantines (tenant_mismatch);
- cancellation / access-change kinds are NOT mapped yet (the adapter
  addendum owns that mapping) — they quarantine as unmapped_event_kind
  rather than ride an improvised mapping;
- contact_ref (schema v1.1, CR-S44-001 ruling): emitted only when the
  read-back supplies the opaque native contact ID AND a v1.1 schema is
  configured; otherwise it travels in processing context and the event
  stamps 1.0. Never derived from a name or email.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import jsonschema

# Staging note: the schema is vendored beside this module (copied from
# packet/reference/schemas/purchase-event.schema.json) so the staged
# tree is self-contained; the work-tree original resolved it from the
# packet by a parents[4] relative path.
_PACKET_SCHEMA = (Path(__file__).resolve().parent
                  / "purchase-event.schema.json")
_SCHEMA_V10 = json.loads(_PACKET_SCHEMA.read_text())

# Schema v1.1 switch (CR-S44-001): the v1.1 schema is vendored beside
# this module too (byte copy of shared-utils/signature_launch/domain/
# purchase-event.schema.json on main). It is loaded once here and
# wired into ingest() as the default schema_v11, so the production
# pipeline stamps 1.1 and carries contact_ref whenever a read-back
# supplies it. Direct normalize() callers keep the explicit-injection
# contract: no schema_v11 passed, no 1.1 stamp (context only).
_V11_SCHEMA_PATH = (Path(__file__).resolve().parent
                    / "purchase-event.v1.1.schema.json")
_SCHEMA_V11 = (json.loads(_V11_SCHEMA_PATH.read_text())
               if _V11_SCHEMA_PATH.exists() else None)

PAYMENT_STATUSES = {"pending", "succeeded", "failed",
                    "requires_customer_action", "refunded",
                    "partially_refunded", "unknown"}
EVENT_TYPES = {"purchase_observed", "payment_updated", "refund_observed",
               "subscription_updated"}

# native read-back kind -> envelope event_type. Cancellation and access
# change are deliberately ABSENT: underdetermined by the sources, fixed
# by the adapter addendum, quarantined until then (design section 4).
KIND_MAP = {
    "order_paid": "purchase_observed",
    "purchase": "purchase_observed",
    "payment_updated": "payment_updated",
    "refund": "refund_observed",
    "subscription": "subscription_updated",
    "subscription_renewal": "subscription_updated",
}
UNMAPPED_KINDS = {"cancellation", "access_change"}


class LaunchContext:
    def __init__(self, tenant_id: str, location_id: str, launch_id: str,
                 bindings: dict[str, str]):
        self.tenant_id = tenant_id
        self.location_id = location_id
        self.launch_id = launch_id
        self.bindings = bindings


def _quarantine(reason_code: str, detail: str, readback: dict) -> dict:
    return {"quarantine": {
        "reason_code": reason_code,
        "detail": detail,
        "evidence_ref": readback.get("evidence_ref"),
        "readback": readback,
    }}


def normalize(readback: dict, ctx: LaunchContext,
              schema_v11: Optional[dict] = None) -> dict:
    """Return {"event": envelope, "contact_ref_context": str|None} or
    {"quarantine": {...}}. Never raises for ambiguity."""
    # tenant integrity first: the read-back must belong to the launch
    # context whose bindings would resolve its slots
    for field, expected in (("tenant_id", ctx.tenant_id),
                            ("location_id", ctx.location_id),
                            ("launch_id", ctx.launch_id)):
        if readback.get(field) != expected:
            return _quarantine(
                "tenant_mismatch",
                f"read-back {field}={readback.get(field)!r} does not match "
                f"the launch context {expected!r}", readback)
    # verified provider event identity is the dedup anchor; absent = stop
    if not readback.get("provider_event_id"):
        return _quarantine("no_verified_event_identity",
                           "read-back carries no provider_event_id",
                           readback)
    # event kind: explicit schema event_type wins; else the kind map;
    # cancellation/access-change and unknown kinds quarantine
    event_type = readback.get("event_type")
    if event_type is not None and event_type not in EVENT_TYPES:
        return _quarantine("unmapped_event_kind",
                           f"event_type {event_type!r} is outside the "
                           "schema enum; never coerced", readback)
    if event_type is None:
        kind = readback.get("native_event_kind")
        if kind in UNMAPPED_KINDS or kind not in KIND_MAP:
            return _quarantine(
                "unmapped_event_kind",
                f"native kind {kind!r} has no settled envelope mapping "
                "(adapter addendum owns it)", readback)
        event_type = KIND_MAP[kind]
    # payment truth: only the verified transaction status; a bare
    # submission is `unknown`; an out-of-enum value quarantines
    status = readback.get("payment_status")
    if status is None:
        status = "unknown"
    elif status not in PAYMENT_STATUSES:
        return _quarantine("schema_invalid",
                           f"payment_status {status!r} is outside the "
                           "schema enum; never coerced", readback)
    # lines: all of them, every time; one unmapped product quarantines
    # the whole event (partial normalization would drop lines silently)
    lines = []
    for item in readback.get("line_items", []):
        slot = ctx.bindings.get(item.get("native_product_ref"))
        if slot is None:
            return _quarantine(
                "unmapped_native_product",
                f"no verified binding for native product "
                f"{item.get('native_product_ref')!r} in this launch",
                readback)
        lines.append({
            "native_line_ref": item["native_line_ref"],
            "offer_id": item["offer_id"],
            "slot": slot,
            "currency": item["currency"],
            "amount_minor": int(item["amount_minor"]),
            "entitlement_ids": list(item["entitlement_ids"]),
        })
    contact_ref = readback.get("contact_ref")
    event = {
        "schema_version": "1.0",
        "tenant_id": ctx.tenant_id,
        "location_id": ctx.location_id,
        "launch_id": ctx.launch_id,
        "provider": readback["provider"],
        "event_id": readback["provider_event_id"],
        "event_type": event_type,
        "native_order_ref": readback["native_order_ref"],
        # never synthesized: absent stays null, the action key falls
        # back to the order ref downstream
        "native_transaction_ref": readback.get("native_transaction_ref"),
        "occurred_at": readback["occurred_at"],
        "received_at": readback["received_at"],
        "payment_status": status,
        "line_items": lines,
        "evidence_ref": readback["evidence_ref"],
        "test_only": bool(readback.get("test_only", False)),
    }
    schema = _SCHEMA_V10
    if contact_ref and schema_v11 is not None:
        event["contact_ref"] = contact_ref
        event["schema_version"] = "1.1"
        schema = schema_v11
    try:
        jsonschema.validate(event, schema)
    except jsonschema.ValidationError as e:
        return _quarantine("schema_invalid",
                           f"normalized envelope failed validation: "
                           f"{e.message}", readback)
    return {"event": event,
            "contact_ref_context": contact_ref}


def ingest(store, readback: dict, ctx: LaunchContext,
           schema_v11: Optional[dict] = None) -> tuple[str, dict]:
    """Pipeline glue (design section 1): normalize, then record-if-unseen
    in the durable inbox, or persist the quarantine as a review item.
    Returns ("accepted"|"duplicate"|"quarantined", payload)."""
    if schema_v11 is None:
        schema_v11 = _SCHEMA_V11  # the vendored v1.1 wiring (above)
    result = normalize(readback, ctx, schema_v11=schema_v11)
    if "quarantine" in result:
        q = result["quarantine"]
        qid = store.add_quarantine(
            ctx.tenant_id, readback.get("location_id"),
            readback.get("launch_id"), q["reason_code"], q["detail"],
            q["evidence_ref"], readback, readback.get("received_at", ""))
        return "quarantined", {"quarantine_id": qid, **q}
    event = result["event"]
    seen = store.record_event_if_unseen(
        event["tenant_id"], event["provider"], event["event_id"], event)
    return ("accepted" if seen else "duplicate"), result
