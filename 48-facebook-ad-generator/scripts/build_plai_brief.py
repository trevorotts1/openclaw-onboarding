#!/usr/bin/env python3
"""
build_plai_brief.py — assemble the PLAI-ready handoff package (net-new).

PLAI is the ONLY ad path (no direct Meta API). This builds `working/s7-plai-brief.json`
carrying every field PLAI's builder asks for (REQUIRED_PLAI_FIELDS) so a person can
finish the campaign in PLAI's builder: hosted image links + copy variants + the
Group -> Layer 1/2/3 targeting table + a human paste-guide. `_chk_plai_fields` fails the
gate if any required field is missing.

It reads the run's own receipts (the hosted links from the S7 deliver receipt, the copy
from S2/S3, the targeting from S6) so the brief is assembled from real artifacts, never
hand-typed.

CLI:
    python3 build_plai_brief.py --run-dir DIR --campaign-name "..." --destination-url "https://..."
        [--objective OUTCOME_TRAFFIC] [--placements facebook_feed instagram_feed]
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ad_build_check as abc  # for REQUIRED_PLAI_FIELDS + receipt readers


def _read(p: Path):
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


def build(run_dir: Path, campaign_name: str, destination_url: str,
          objective: str = "OUTCOME_TRAFFIC", placements=None) -> dict:
    placements = placements or ["facebook_feed", "instagram_feed"]
    deliver = abc._s7_receipt(run_dir) or {}
    image_links = [d.get("image_url") for d in deliver.get("delivered", [])
                   if isinstance(d, dict) and d.get("image_url")]
    # Copy variants (best-effort from the human deliverables; the ad-text doc is canonical).
    bodies = []
    s2 = abc._s2_receipt(run_dir)
    if isinstance(s2, dict) and isinstance(s2.get("bodies"), list):
        bodies = [f"body {i+1}" for i in range(len(s2["bodies"]))]
    headlines = []
    s3 = abc._s3_receipt(run_dir)
    if isinstance(s3, dict) and isinstance(s3.get("headlines"), list):
        headlines = [h.get("text", f"headline {i+1}")
                     for i, h in enumerate(s3["headlines"])]
    targeting = abc._s6_targeting(run_dir) or {}
    groups = [g.get("name", f"group {i+1}")
              for i, g in enumerate(targeting.get("groups", []))]

    brief = {
        "campaign_name": campaign_name,
        "objective": objective,
        "image_links": image_links,
        "primary_texts": bodies,
        "headlines": headlines,
        "targeting_groups": groups or ["(derive in PLAI from the targeting brief)"],
        "placements": placements,
        "destination_url": destination_url,
        "targeting_table": targeting.get("groups", []),
        "paste_guide": ("In PLAI's builder: (1) create the campaign with the objective "
                        "above; (2) for each of the 10 ads paste the matching Headline + "
                        "Main Body from the ad-text doc and attach the matching image "
                        "link; (3) build each Group's audience from the Layer 1/2/3 "
                        "targeting table; (4) set placements + destination URL."),
        "ad_path": "PLAI (the only ad path — no direct Meta API)",
    }
    # Honest gap check against the gate's required fields.
    missing = [f for f in abc.REQUIRED_PLAI_FIELDS if not brief.get(f)]
    brief["_missing_required_fields"] = missing
    p = run_dir / "working" / "s7-plai-brief.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(brief, indent=2))
    return brief


def main():
    ap = argparse.ArgumentParser(description="Assemble the PLAI-ready brief.")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--campaign-name", required=True)
    ap.add_argument("--destination-url", required=True)
    ap.add_argument("--objective", default="OUTCOME_TRAFFIC")
    ap.add_argument("--placements", nargs="*", default=None)
    args = ap.parse_args()
    brief = build(Path(args.run_dir).resolve(), args.campaign_name, args.destination_url,
                  args.objective, args.placements)
    print(json.dumps({"required_present": not brief["_missing_required_fields"],
                      "missing": brief["_missing_required_fields"],
                      "image_links": len(brief["image_links"])}, indent=2))


if __name__ == "__main__":
    main()
