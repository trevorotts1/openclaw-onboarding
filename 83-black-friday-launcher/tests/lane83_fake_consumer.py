#!/usr/bin/env python3
"""A free stand-in for a page skill: answers one Skill 49 page request with typed, labeled design files.

Used only by the Lane 83 tests. It makes no network call and spends nothing. Usage (the adapter seam
substitutes {request} and {result}):

    lane83_fake_consumer.py <request.json> <result.json> <labels.py> [--omit KIND] [--provider stub|kie]
                            [--sleep SECONDS] [--instance downsell_2]
                            [--pages landing,sales]

The file names come from Skill 71's own deliverable_labels.py, so the tests prove the real labels, not
a copy of them.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f"
       b"\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00"
       b"\x00\x00IEND\xaeB`\x82")


def load_labels(path):
    spec = importlib.util.spec_from_file_location("lane83_labels", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("request")
    ap.add_argument("result")
    ap.add_argument("labels")
    ap.add_argument("--omit", action="append", default=[])
    ap.add_argument("--provider", default="stub")
    ap.add_argument("--sleep", type=float, default=0.0)
    ap.add_argument("--instance", default=None)
    ap.add_argument("--pages", default="", help="landing pages to draw in the one result (landing, sales)")
    args = ap.parse_args(argv)
    req = json.loads(Path(args.request).read_text(encoding="utf-8"))
    labels = load_labels(args.labels)
    time.sleep(args.sleep)

    pages = [args.instance or req["page_role"]]
    if req["page_role"] == "landing" and args.pages:  # the real landing bridge answers every planned page at once
        pages = [{"landing": "landing", "sales": "sales_page"}[k] for k in args.pages.split(",")]
    run = Path(args.result).parent / f"{pages[0]}-run"
    artifacts = []

    def put(kind, rel, data):
        if kind in args.omit:
            return
        path = run / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        artifacts.append({"path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
                          "kind": kind, "provider": args.provider})

    for role in pages:
        for device, wire_stage, mock_stage in (("desktop", "desktop-wireframe", "final-mockups"),
                                               ("mobile", "mobile-tablet", "final-mockups")):
            for n in (1, 2):
                put(f"wireframe_{device}_section",
                    f"{labels.folder(device, wire_stage)}/{labels.image_name(role, device, wire_stage, n, 2, 'hero')}", PNG)
                put(f"mockup_{device}_section",
                    f"{labels.folder(device, mock_stage)}/{labels.image_name(role, device, mock_stage, n, 2, 'hero')}", PNG)
            put(f"wireframe_{device}_pdf", f"review-pdfs/{labels.pdf_name(role, device, wire_stage)}", b"%PDF-1.4 wf\n")
            put(f"mockup_{device}_pdf", f"review-pdfs/{labels.pdf_name(role, device, mock_stage)}", b"%PDF-1.4 mk\n")
        put("board", f"review-pdfs/{labels.board_name(role, 'combined', 'final-mockups')}.png", PNG)

    result = {
        "schema_version": "1.0", "tenant_id": req["tenant_id"], "location_id": req["location_id"],
        "launch_id": req["launch_id"], "revision": req["revision"], "request_id": req["request_id"],
        "input_hash": req["input_hash"], "page_id": req["page_id"], "status": "authored",
        "artifacts": artifacts, "author_session": "lane83-fake-consumer", "reviewer_session": None,
        "independent_review": False, "proof_class": "L0", "blockers": [],
        "native_bindings_ref": None, "test_only": req["test_only"],
        "page_kind": req["page_role"], "role_instance": args.instance,
        "image_provider": args.provider,
    }
    Path(args.result).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
