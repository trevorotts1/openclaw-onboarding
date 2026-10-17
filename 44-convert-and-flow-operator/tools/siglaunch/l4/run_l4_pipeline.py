"""S44 L4 pipeline driver — runs S44's REAL normalizer/processor/store
against the REAL native objects created in BCEO Client Sandbox under
Trevor's 2026-10-16 test-payments ruling (sandbox only, test mode).

Native objects (all read back from the location before this run):
  buyer contact  QzIXSs3mnrIuR4agE6R2
  invoice A      6ad22df3baae1b6f9b2d5674  paid $66 (main $49 + bump $17)
  txn A          6ad22e7c4caebbd2beeb917e  succeeded, liveMode false
  invoice B      6ad22ecd07479c1eab71d70f  draft/unpaid $97 (extra)
  invoice C      6ad22ed49e6698d9aff95154  paid $97 (extra)
  txn C          6ad22f56f8acee4bc57a26c2  succeeded, liveMode false

Side effects of this driver, all inside the sandbox: the verified-
purchase tag is applied to the test buyer via the connector (the
processor's real tag applier), and ONE confirmation email is sent to
the test buyer via the connector (check 3's send effect, claimed
exactly once in the durable store).
"""
import json
import subprocess
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

LOC = "XCgFTEA1oDvsPnTqqgoB"
TENANT = "bceo-client-sandbox"
LAUNCH = "signature-launch-l4"
CONTACT = "QzIXSs3mnrIuR4agE6R2"
TAG = "s44-l4-verified-purchase"

INV_A = "6ad22df3baae1b6f9b2d5674"
TXN_A = "6ad22e7c4caebbd2beeb917e"
ITEM_MAIN = "6ad22df3baae1b6f9b2d5675"
ITEM_BUMP = "6ad22df3baae1b6f9b2d5676"
INV_B = "6ad22ecd07479c1eab71d70f"
ITEM_B = "6ad22ecd07479c1eab71d710"
INV_C = "6ad22ed49e6698d9aff95154"
TXN_C = "6ad22f56f8acee4bc57a26c2"
ITEM_C = "6ad22ed49e6698d9aff95155"

GHL = "/opt/hatch/bin/ghl"


def ghl_write(op, params, key, reason):
    out = subprocess.run(
        [GHL, "execute-operation", "--operation-id", op,
         "--location-id", LOC, "--idempotency-key", key,
         "--params-json", json.dumps(params), "--reason", reason],
        capture_output=True, text=True, timeout=120)
    d = json.loads(out.stdout)
    if not d.get("ok"):
        raise RuntimeError(f"{op} failed: {out.stdout[:400]}")
    return d


def tag_applier(contact_ref, tag):
    ghl_write("add-tags",
              {"path": {"contactId": contact_ref},
               "body": {"tags": [tag]}},
              f"s44-l4-tag-{contact_ref}",
              "S44 L4: apply verified-purchase tag to the sandbox "
              "test buyer (processor tag action)")


def send_confirmation(contact_ref):
    ghl_write("send-a-new-message",
              {"body": {
                  "type": "Email",
                  "contactId": contact_ref,
                  "emailTo": "s44-l4-buyer@example.com",
                  "subject": "S44 L4 TEST - purchase confirmation",
                  "message": "TEST ONLY (BCEO Client Sandbox). "
                             "Confirmation for S44 L4 clean "
                             "purchase, invoice " + INV_A + ".",
                  "html": "<p>TEST ONLY (BCEO Client Sandbox). "
                          "Confirmation for S44 L4 clean purchase, "
                          "invoice " + INV_A + ".</p>"}},
              f"s44-l4-send-{TXN_A}",
              "S44 L4 check 3: the pipeline's single confirmation "
              "send to the sandbox test buyer")


def line(item_id, offer, slot_product, amount, ents):
    return {"native_line_ref": item_id, "offer_id": offer,
            "native_product_ref": slot_product, "currency": "USD",
            "amount_minor": amount, "entitlement_ids": ents}


def readback(event_id, kind, status, order_ref, txn_ref, occurred,
             lines, evidence):
    rb = {"tenant_id": TENANT, "location_id": LOC,
          "launch_id": LAUNCH, "provider": "ghl",
          "provider_event_id": event_id, "native_event_kind": kind,
          "native_order_ref": order_ref,
          "native_transaction_ref": txn_ref,
          "occurred_at": occurred,
          "received_at": "2026-10-16T14:10:00Z",
          "line_items": lines, "evidence_ref": evidence,
          "test_only": True, "contact_ref": CONTACT}
    if status is not None:
        rb["payment_status"] = status
    return rb


def main():
    results = {}
    db = Path(__file__).resolve().parent / "l4-store.sqlite"
    if db.exists():
        db.unlink()
    store = Store(str(db))
    ctx = LaunchContext(TENANT, LOC, LAUNCH, {
        ITEM_MAIN: "main", ITEM_BUMP: "bump",
        ITEM_B: "upsell_1", ITEM_C: "upsell_1"})
    proc = DurableProcessor(store, tag_applier=tag_applier,
                            purchase_tag=TAG)

    # ---- Purchase A: clean purchase (main + bump), paid ----------
    rb_a = readback(
        TXN_A, "order_paid", "succeeded", INV_A, TXN_A,
        "2026-10-16T14:02:36.458Z",
        [line(ITEM_MAIN, "siglaunch-main", ITEM_MAIN, 4900,
              ["ent-main"]),
         line(ITEM_BUMP, "siglaunch-bump", ITEM_BUMP, 1700,
              ["ent-bump"])],
        "ghl list-transactions txn succeeded + get-invoice A paid")
    status_a, payload_a = ingest(store, rb_a, ctx)
    results["ingest_A"] = status_a
    res_a = proc.process(payload_a["event"],
                         contact_ref=payload_a["contact_ref_context"])
    results["process_A"] = res_a
    results["active_after_A"] = sorted(
        store.active_entitlements(TENANT))

    # fulfill both lines (access provisioning effect: internal) ----
    for item in (ITEM_MAIN, ITEM_BUMP):
        key = (TENANT, TXN_A, item, "initiate_fulfillment", "v1")
        results[f"fulfill_{item[-4:]}"] = proc.fulfill(
            key, lambda payload: None)
    map_a = build_fulfillment_map(store, TENANT, LAUNCH, CONTACT)
    results["map_after_A"] = map_a

    # ---- Check 3: confirmation send, claimed exactly once --------
    send_key = (TENANT, TXN_A, "*", "send_confirmation", "v1")
    claimed = store.claim_action(send_key, {"channel": "email"})
    if claimed is None:
        send_confirmation(CONTACT)
        store.mark_action(send_key, "done",
                          evidence_ref="ghl send-a-new-message")
        results["send_first_path"] = "claimed_and_sent"
    else:
        results["send_first_path"] = "already_claimed_no_send"
    # the thank-you page observation arrives second: same claim key
    claimed2 = store.claim_action(send_key, {"channel": "email"})
    results["send_second_path"] = (
        "already_claimed_no_second_send" if claimed2 is not None
        else "ERROR_second_claim_succeeded")

    # ---- Invoice B: extra offer, payment never completed ---------
    rb_b = readback(
        INV_B, "purchase", None, INV_B, None,
        "2026-10-16T14:05:00Z",
        [line(ITEM_B, "siglaunch-extra", ITEM_B, 9700,
              ["ent-extra"])],
        "ghl get-invoice B status draft amountPaid 0; "
        "no transaction exists for B")
    status_b, payload_b = ingest(store, rb_b, ctx)
    results["ingest_B"] = status_b
    res_b = proc.process(payload_b["event"],
                         contact_ref=payload_b["contact_ref_context"])
    results["process_B"] = res_b
    results["active_after_B"] = sorted(
        store.active_entitlements(TENANT))

    # ---- Invoice C: extra offer purchased ------------------------
    rb_c = readback(
        TXN_C, "order_paid", "succeeded", INV_C, TXN_C,
        "2026-10-16T14:06:14.774Z",
        [line(ITEM_C, "siglaunch-extra", ITEM_C, 9700,
              ["ent-extra"])],
        "ghl list-transactions txn succeeded + get-invoice C paid")
    status_c, payload_c = ingest(store, rb_c, ctx)
    results["ingest_C"] = status_c
    res_c = proc.process(payload_c["event"],
                         contact_ref=payload_c["contact_ref_context"])
    results["process_C"] = res_c
    key_c = (TENANT, TXN_C, ITEM_C, "initiate_fulfillment", "v1")
    results["fulfill_C"] = proc.fulfill(key_c, lambda payload: None)
    results["active_after_C"] = sorted(
        store.active_entitlements(TENANT))
    results["map_after_C"] = build_fulfillment_map(
        store, TENANT, LAUNCH, CONTACT)
    results["entitlement_version_after_C"] = store.entitlement_version(
        TENANT, LAUNCH, CONTACT)

    out = Path(__file__).resolve().parent / "l4-pipeline-results.json"
    out.write_text(json.dumps(results, indent=1, default=str))
    print(json.dumps(results, indent=1, default=str))


if __name__ == "__main__":
    main()
