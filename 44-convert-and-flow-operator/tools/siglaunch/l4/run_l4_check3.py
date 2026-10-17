"""S44 L4 check-3 clean re-run — buyer 2 pipeline, up to the send
claim. The send itself is executed by the operator through ONE
direct connector call (never through a subprocess), after this
script claims the action. run_l4_finish3.py then marks it done
against the native read-back and counts the messages.
"""
import json
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
from run_l4_pipeline import (LOC, TENANT, LAUNCH, TAG, tag_applier,
                             readback, line)

CONTACT2 = "Hf63k0vcefn3MNmlGYri"
INV_A2 = "6ad2388cd63d90c6ba4263bf"
TXN_A2 = "6ad238d157d447970c871671"
ITEM_A2 = "6ad2388cd63d90c6ba4263c0"


def main():
    results = {}
    db = Path(__file__).resolve().parent / "l4-store.sqlite"
    store = Store(str(db))
    ctx = LaunchContext(TENANT, LOC, LAUNCH, {ITEM_A2: "main"})
    proc = DurableProcessor(store, tag_applier=tag_applier,
                            purchase_tag=TAG)
    rb = readback(
        TXN_A2, "order_paid", "succeeded", INV_A2, TXN_A2,
        "2026-10-16T14:46:41.199Z",
        [line(ITEM_A2, "siglaunch-main", ITEM_A2, 4900,
              ["ent-main"])],
        "ghl list-transactions txn succeeded + get-invoice A2 paid")
    rb["contact_ref"] = CONTACT2
    status, payload = ingest(store, rb, ctx)
    results["ingest_A2"] = status
    results["process_A2"] = proc.process(
        payload["event"], contact_ref=CONTACT2)
    key = (TENANT, TXN_A2, ITEM_A2, "initiate_fulfillment", "v1")
    results["fulfill_A2"] = proc.fulfill(key, lambda payload: None)
    send_key = (TENANT, TXN_A2, "*", "send_confirmation", "v1")
    claimed = store.claim_action(send_key, {"channel": "email"})
    results["send_claim"] = (
        "claimed_fresh" if claimed is None else "already_existed")
    results["send_key"] = list(send_key)
    results["map_buyer2"] = build_fulfillment_map(
        store, TENANT, LAUNCH, CONTACT2)
    out = Path(__file__).resolve().parent / "l4-check3-results.json"
    out.write_text(json.dumps(results, indent=1, default=str))
    print(json.dumps(results, indent=1, default=str))


if __name__ == "__main__":
    main()
