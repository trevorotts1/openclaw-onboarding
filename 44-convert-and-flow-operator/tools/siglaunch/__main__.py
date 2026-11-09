"""python -m siglaunch run: one purchase event, normalizer -> processor.

The Black Friday 2026 purchase path is native GHL post-sale workflows
(processor.BLACK_FRIDAY_2026_PURCHASE_PATH). This runner only runs against
the in-memory fake executor until an owner-approved change flips
processor.PRODUCTION_ENTRY_ENABLED; any other executor is refused.

  python -m siglaunch run --event READBACK.json --catalog CATALOG.json \
      --db STORE.sqlite --executor fake

CATALOG.json: {"tenant_id", "location_id", "launch_id",
               "bindings": {native_product_ref: slot}, "purchase_tag"}
stdout: one JSON receipt {"ingest", "process", "fake_effects",
"active_entitlements"}. Exit 0 accepted/duplicate, 3 quarantined,
6 refused as a production entry.
"""
import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
for _sub in ("store", "normalizer", "processor"):
    sys.path.insert(0, str(_HERE / _sub))

import processor  # noqa: E402
from normalizer import LaunchContext, ingest  # noqa: E402
from store import Store  # noqa: E402

EXIT_QUARANTINED = 3


def run(args) -> int:
    if args.executor != "fake" and not processor.PRODUCTION_ENTRY_ENABLED:
        print("siglaunch run refused: the Black Friday 2026 purchase path is "
              f"{processor.BLACK_FRIDAY_2026_PURCHASE_PATH}; only "
              "--executor fake is available.", file=sys.stderr)
        return processor.EXIT_NOT_PRODUCTION
    if args.executor != "fake":  # flag flipped but no live executor is wired
        print("siglaunch run: live executor is not implemented.", file=sys.stderr)
        return 2
    readback = json.loads(Path(args.event).read_text())
    cat = json.loads(Path(args.catalog).read_text())
    ctx = LaunchContext(cat["tenant_id"], cat["location_id"], cat["launch_id"],
                        cat["bindings"])
    effects = []
    store = Store(args.db)
    status, payload = ingest(store, readback, ctx)
    out = {"ingest": status, "process": None, "fake_effects": effects}
    if status == "accepted":
        proc = processor.DurableProcessor(
            store, tag_applier=lambda ref, tag: effects.append(
                {"effect": "tag", "contact_ref": ref, "tag": tag}),
            purchase_tag=cat["purchase_tag"])
        event = payload["event"]
        out["process"] = proc.process(
            event, contact_ref=payload.get("contact_ref_context"))
        txn = event.get("native_transaction_ref") or event["native_order_ref"]
        for line in event["line_items"]:
            key = (event["tenant_id"], txn, line["native_line_ref"],
                   "initiate_fulfillment", "v1")
            proc.fulfill(key, lambda p, ln=line: effects.append(
                {"effect": "fulfill", "line_ref": ln["native_line_ref"]}))
    out["active_entitlements"] = sorted(store.active_entitlements(cat["tenant_id"]))
    print(json.dumps(out, default=str))
    return EXIT_QUARANTINED if status == "quarantined" else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m siglaunch")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="process one purchase event")
    r.add_argument("--event", required=True)
    r.add_argument("--catalog", required=True)
    r.add_argument("--db", required=True)
    r.add_argument("--executor", choices=("fake", "live"))
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
