"""S44 L4 resume 2 — evidence-driven completion after the send.

The confirmation send was executed directly (messageId
HPNQDDEmbG60s2SQIbKa, connector approval granted) after the
in-driver subprocess attempt failed on the approval flow. This
script FIRST verifies the send natively (message read-back by ID),
then marks the claimed store action done with that evidence, runs
the second-claim no-resend proof, and completes invoices B and C.
It never sends anything itself.
"""
import json
import subprocess
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent.parent
for sub in ("store", "normalizer", "processor", "fulfillment_map",
            "events"):
    sys.path.insert(0, str(WORK / sub))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from store import Store
from normalizer import LaunchContext, ingest
from processor import DurableProcessor
from fulfillment_map import build_fulfillment_map
from run_l4_pipeline import (LOC, TENANT, LAUNCH, CONTACT, TAG,
                             INV_B, ITEM_B, INV_C, TXN_C, ITEM_C,
                             TXN_A, tag_applier, readback, line)

GHL = "/opt/hatch/bin/ghl"
MSG_ID = "HPNQDDEmbG60s2SQIbKa"


def ghl_read(op, params):
    out = subprocess.run(
        [GHL, "execute-operation", "--operation-id", op,
         "--location-id", LOC, "--params-json", json.dumps(params)],
        capture_output=True, text=True, timeout=120)
    d = json.loads(out.stdout)
    if not d.get("ok"):
        raise RuntimeError(f"{op} failed: {out.stdout[:300]}")
    return json.loads(d["result"]["content"][0]["text"])["data"]


def main():
    results = {}
    # verify the send natively before touching the ledger: read the
    # buyer's conversation and count messages carrying this driver's
    # confirmation body. TRUTH FOUND 2026-10-16: TWO such messages
    # exist (wMjb8Fl3sTiYZERYQRXf 14:35:16Z, EHe6iQGiMuVCgBDJYIM4
    # 14:35:18Z) — the in-driver subprocess attempt and the direct
    # call both executed when the shared connector approval landed.
    # One logical claim, two native sends: an operator recovery
    # error, recorded here, not hidden. The ledger action is marked
    # done with BOTH message IDs as evidence.
    conv = ghl_read("get-messages", {
        "path": {"conversationId": "nhI38J61megvOyc59ODB"},
        "query": {"limit": 30}})
    msgs = conv.get("messages", {})
    if isinstance(msgs, dict):
        msgs = msgs.get("messages", [])
    mine = [m for m in msgs if isinstance(m, dict)
            and "Confirmation for S44 L4 clean purchase"
            in (m.get("body") or "")]
    results["confirmation_messages_native"] = [
        {"id": m.get("id"), "date": m.get("dateAdded"),
         "status": m.get("status")} for m in mine]
    results["check3_run1"] = (
        "DUPLICATED_BY_OPERATOR_RECOVERY: 1 claim, "
        f"{len(mine)} native sends")
    assert len(mine) == 2, results["confirmation_messages_native"]

    db = Path(__file__).resolve().parent / "l4-store.sqlite"
    store = Store(str(db))
    send_key = (TENANT, TXN_A, "*", "send_confirmation", "v1")
    action = store.get_action(send_key)
    results["send_action_state_before"] = action["state"]
    if action["state"] == "claimed":
        store.mark_action(
            send_key, "done",
            evidence_ref="ghl messages wMjb8Fl3sTiYZERYQRXf + "
                         "EHe6iQGiMuVCgBDJYIM4 (duplicated send, "
                         "see check3_run1)")
        results["send_marked"] = "done_with_native_evidence"
    claimed2 = store.claim_action(send_key, {"channel": "email"})
    results["send_second_path"] = (
        "already_claimed_no_second_send" if claimed2 is not None
        else "ERROR_second_claim_succeeded")
    results["active_at_resume2"] = sorted(
        store.active_entitlements(TENANT))

    ctx = LaunchContext(TENANT, LOC, LAUNCH, {
        "6ad22df3baae1b6f9b2d5675": "main",
        "6ad22df3baae1b6f9b2d5676": "bump",
        ITEM_B: "upsell_1", ITEM_C: "upsell_1"})
    proc = DurableProcessor(store, tag_applier=tag_applier,
                            purchase_tag=TAG)

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
