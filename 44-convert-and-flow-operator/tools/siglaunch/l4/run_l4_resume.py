"""S44 L4 resume — completes the interrupted 2026-10-16 driver run.

The first run (run_l4_pipeline.py) completed Purchase A fully
(grants, fulfillment, tag action all 'done' in the store) and died
at the send_confirmation claim when the exec session layer flaked.
Native verification before this resume: the buyer's conversation
holds NO message with this driver's subject — the send was never
performed, so executing it once here does not duplicate it.

This resume does NOT reprocess A (a redelivery must never reach
process()). It executes: the single claimed confirmation send, the
second-claim no-resend proof, Invoice B (unpaid extra), Invoice C
(extra purchased), fulfillment, maps, entitlement_version.
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
from run_l4_pipeline import (LOC, TENANT, LAUNCH, CONTACT, TAG,
                             INV_A, TXN_A, ITEM_MAIN, ITEM_BUMP,
                             INV_B, ITEM_B, INV_C, TXN_C, ITEM_C,
                             ghl_write, tag_applier, readback, line)

sys.path.insert(0, str(Path(__file__).resolve().parent))


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


def main():
    results = {}
    db = Path(__file__).resolve().parent / "l4-store.sqlite"
    store = Store(str(db))
    ctx = LaunchContext(TENANT, LOC, LAUNCH, {
        ITEM_MAIN: "main", ITEM_BUMP: "bump",
        ITEM_B: "upsell_1", ITEM_C: "upsell_1"})
    proc = DurableProcessor(store, tag_applier=tag_applier,
                            purchase_tag=TAG)
    results["active_at_resume"] = sorted(
        store.active_entitlements(TENANT))

    # ---- Check 3: execute the already-claimed send exactly once --
    send_key = (TENANT, TXN_A, "*", "send_confirmation", "v1")
    action = store.get_action(send_key)
    results["send_action_state_at_resume"] = action["state"]
    if action["state"] == "claimed":
        send_confirmation(CONTACT)
        store.mark_action(send_key, "done",
                          evidence_ref="ghl send-a-new-message "
                                       "subject 'S44 L4 TEST - "
                                       "purchase confirmation'")
        results["send_first_path"] = "claimed_then_sent_once"
    claimed2 = store.claim_action(send_key, {"channel": "email"})
    results["send_second_path"] = (
        "already_claimed_no_second_send" if claimed2 is not None
        else "ERROR_second_claim_succeeded")

    # ---- Invoice B: extra offer, payment never completed ---------
    rb_b = readback(
        INV_B, "purchase", None, INV_B, None, "2026-10-16T14:05:00Z",
        [line(ITEM_B, "siglaunch-extra", ITEM_B, 9700,
              ["ent-extra"])],
        "ghl get-invoice B status draft amountPaid 0; "
        "no transaction exists for B")
    status_b, payload_b = ingest(store, rb_b, ctx)
    results["ingest_B"] = status_b
    results["process_B"] = proc.process(
        payload_b["event"],
        contact_ref=payload_b["contact_ref_context"])
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
    results["process_C"] = proc.process(
        payload_c["event"],
        contact_ref=payload_c["contact_ref_context"])
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
