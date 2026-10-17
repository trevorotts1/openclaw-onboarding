"""S44 L4 check 4 completion — runs the REAL normalizer/processor/store
refund path against the native refund executed in BCEO Client Sandbox.

Native refund facts (all read back firsthand 2026-10-16 ~11:27 EDT):
  - The refund was executed in the sandbox web UI (Payments >
    Transactions > transaction 6ad22f56f8acee4bc57a26c2 > Refund;
    modal amount 97.00 USD; toast "Refund request successfully
    processed"; the transaction's Refunds section records the refund
    as Succeeded at Oct 16 11:10 AM EDT). No refund operation exists
    in the connector/API surface.
  - list-transactions read-back (traceId ae3b4863-d9d5-4b47-b6ea-
    f3d5023096a4): transaction C status "refunded",
    amountRefunded 97 of 97, updatedAt 2026-10-16T15:10:22.096Z,
    liveMode false. Transaction A still "succeeded",
    amountRefunded 0.
  - get-invoice A (traceId 4c4b6165-4400-4251-b580-0ece350f4013):
    status "paid", amountPaid 66 — untouched by the refund.
  - get-invoice C (traceId 1e09c0fd-683a-4a2d-90c8-fbf6529f1341):
    invoice-level status remains "paid", amountPaid 97 — on this
    platform the refund is recorded on the transaction, not by
    flipping the invoice status. Disclosed as platform behavior.
  - get-contact buyer 1 (traceId 2d15f4ec-00cd-4de4-99ca-
    0ff6dbd6e081): tags still exactly ["s44-l4-verified-purchase"].

Event identity: the provider exposes no separate refund object ID
(the UI's Refunds entry shows a blank Ref Id), so the refund event's
provider_event_id is composed ONLY from provider-supplied fields:
the native transaction ID + the transaction's own updatedAt at the
refunded state. Deterministic: a redelivery of the same refunded
state yields the same identity and dedups; a later distinct refund
state (different updatedAt / amountRefunded) yields a different one.
"""
import json
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent.parent
for sub in ("store", "normalizer", "processor", "fulfillment_map",
            "events"):
    sys.path.insert(0, str(WORK / sub))

from store import Store
from normalizer import LaunchContext, ingest
from processor import DurableProcessor
from fulfillment_map import build_fulfillment_map

TENANT = "bceo-client-sandbox"
LOC = "XCgFTEA1oDvsPnTqqgoB"
LAUNCH = "signature-launch-l4"
CONTACT = "QzIXSs3mnrIuR4agE6R2"

INV_A = "6ad22df3baae1b6f9b2d5674"
ITEM_MAIN = "6ad22df3baae1b6f9b2d5675"
ITEM_BUMP = "6ad22df3baae1b6f9b2d5676"
INV_B = "6ad22ecd07479c1eab71d70f"
ITEM_B = "6ad22ecd07479c1eab71d710"
INV_C = "6ad22ed49e6698d9aff95154"
TXN_C = "6ad22f56f8acee4bc57a26c2"
ITEM_C = "6ad22ed49e6698d9aff95155"
REFUND_AT = "2026-10-16T15:10:22.096Z"
EV_BEFORE = ("ev1:e89acbc8f9bf257668fcc7144d6891676af3e6809aef326"
             "948dbf48b10d81c09")


def main():
    results = {}
    db = Path(__file__).resolve().parent / "l4-store.sqlite"
    store = Store(str(db))
    ctx = LaunchContext(TENANT, LOC, LAUNCH, {
        ITEM_MAIN: "main", ITEM_BUMP: "bump",
        ITEM_B: "upsell_1", ITEM_C: "upsell_1"})
    proc = DurableProcessor(store)

    results["active_before_refund"] = sorted(
        store.active_entitlements(TENANT))
    results["version_before_refund"] = store.entitlement_version(
        TENANT, LAUNCH, CONTACT)

    rb_refund = {
        "tenant_id": TENANT, "location_id": LOC,
        "launch_id": LAUNCH, "provider": "ghl",
        "provider_event_id": f"{TXN_C}:refund:{REFUND_AT}",
        "native_event_kind": "refund",
        "payment_status": "refunded",
        "native_order_ref": INV_C,
        "native_transaction_ref": TXN_C,
        "occurred_at": REFUND_AT,
        "received_at": "2026-10-16T15:29:00Z",
        "line_items": [{
            "native_line_ref": ITEM_C,
            "offer_id": "siglaunch-extra",
            "native_product_ref": ITEM_C, "currency": "USD",
            "amount_minor": 9700,
            "entitlement_ids": ["ent-extra"]}],
        "evidence_ref": (
            "ghl list-transactions traceId ae3b4863-d9d5-4b47-b6ea-"
            "f3d5023096a4: txn C status refunded amountRefunded 97; "
            "sandbox UI refund executed on txn C, Refunds section "
            "Succeeded 2026-10-16 11:10 AM EDT"),
        "test_only": True, "contact_ref": CONTACT}

    status, payload = ingest(store, rb_refund, ctx)
    results["ingest_refund"] = status
    res = proc.process(payload["event"],
                       contact_ref=payload["contact_ref_context"])
    results["process_refund"] = res

    # redelivery of the identical refund state must dedup, not
    # re-apply: ingest returns duplicate and process is never called
    status2, _ = ingest(store, rb_refund, ctx)
    results["ingest_refund_redelivery"] = status2

    results["active_after_refund"] = sorted(
        store.active_entitlements(TENANT))
    results["map_after_refund"] = build_fulfillment_map(
        store, TENANT, LAUNCH, CONTACT)
    results["version_after_refund"] = store.entitlement_version(
        TENANT, LAUNCH, CONTACT)
    results["version_changed"] = (
        results["version_after_refund"] != EV_BEFORE
        and results["version_before_refund"] == EV_BEFORE)

    out = Path(__file__).resolve().parent / "l4-refund-results.json"
    out.write_text(json.dumps(results, indent=1, default=str))
    print(json.dumps(results, indent=1, default=str))


if __name__ == "__main__":
    main()
