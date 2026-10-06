#!/usr/bin/env python3
"""Write <run_dir>/intake.json, the intake stage artifact stage_gate.py reads.

image_engine is "kie" (default) or "agnes". stage_gate.py accepts the Agnes route on
image-generation-qc only when intake.json says "agnes" (references/kie-generation-route.md).
Exit 0 written, 2 invalid input.
"""
import argparse
import json
import sys
from pathlib import Path

ENGINES = ("kie", "agnes")


def build(a):
    return {"page_version": a.page_version, "brand_owner": a.brand_owner, "brand_file": a.brand_file,
            "creative_direction": a.creative_direction, "image_cap": a.image_cap,
            "image_engine": a.image_engine, "test_run": a.test_run}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("run_dir", type=Path)
    p.add_argument("--page-version", choices=["standard", "long-form"], required=True)
    p.add_argument("--brand-owner", required=True)
    p.add_argument("--brand-file", default="assets/brand/blackceo-brand.json")
    p.add_argument("--creative-direction", default=None)
    p.add_argument("--image-cap", type=int, required=True)
    p.add_argument("--image-engine", choices=ENGINES, default="kie")
    p.add_argument("--test-run", action="store_true")
    a = p.parse_args(argv)
    if a.image_cap < 0 or not a.run_dir.is_dir():
        print("FAIL: run_dir must exist and image_cap must be >= 0")
        return 2
    (a.run_dir / "intake.json").write_text(json.dumps(build(a), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {a.run_dir / 'intake.json'} (image_engine={a.image_engine})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
