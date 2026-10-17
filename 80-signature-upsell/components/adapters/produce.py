#!/usr/bin/env python3
"""CLI for the Skill 80 local production adapters (S80-04 / S80-05).

Usage:
    python3 produce.py --instance upsell_1 \
        --request <request.json> --copy <copy.json> --journey <journey.json> \
        --copy-artifact-path <path-as-recorded> --out <bundle.json>

Reads only local JSON fixtures. Writes one deterministic bundle
{"result": ..., "page_plan": ..., "native_binding": ...}. No network,
no charges: the S80-06 binding in the bundle is interface-conformant
at fixture level only, with native_action_id null pending S06.
TEST ONLY fixtures in, TEST ONLY bundles out.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import adapter_common as common
import upsell1_adapter
import upsell2_adapter


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Skill 80 local upsell adapter")
    parser.add_argument("--instance", choices=["upsell_1", "upsell_2"], required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--copy", required=True)
    parser.add_argument("--journey", required=True)
    parser.add_argument(
        "--copy-artifact-path",
        default=None,
        help="Path string recorded in result.artifacts (default: the --copy value).",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    request = common.load_json(args.request)
    copy_doc = common.load_json(args.copy)
    journey = common.load_json(args.journey)
    copy_sha256 = common.sha256_file(args.copy)
    artifact_path = args.copy_artifact_path or args.copy

    builder = (
        upsell1_adapter.build_bundle
        if args.instance == "upsell_1"
        else upsell2_adapter.build_bundle
    )
    bundle = builder(
        request,
        copy_doc,
        journey,
        copy_sha256=copy_sha256,
        copy_artifact_path=artifact_path,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    print(
        "wrote %s (instance=%s status=%s disposition=%s)"
        % (
            out_path,
            args.instance,
            bundle["result"]["status"],
            bundle["page_plan"]["disposition"]["action"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
