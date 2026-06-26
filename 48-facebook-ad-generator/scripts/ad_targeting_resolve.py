#!/usr/bin/env python3
"""
ad_targeting_resolve.py — resolve interests to real Meta entities, or flag-unverified.

Builds `working/checkpoints/s6-targeting.json` in PLAI's three-tier shape. For each
interest it tries to resolve a REAL Meta entity (a real audience id); if no
resolver/key exists it marks the entry `flagged_unverified` so the package can still
ship. It NEVER invents a meta_id — `_chk_targeting_real` fails any entry that is
neither resolved nor flagged. `_chk_targeting_shape` validates the 3-tier shape + a
per-group explanation.

Resolution path (pluggable):
  * a `resolver(name) -> meta_id|None` callable (the Perplexity-Pro research path
    plugs in here on a real box), else
  * the honest degrade: every interest -> flagged_unverified.

CLI:
    python3 ad_targeting_resolve.py --run-dir DIR --groups groups.json
        # groups.json: [ {"name","explanation","layer1":[names],"layer2":[...],"layer3":[...]} ]
"""

import argparse
import json
import os
import sys
from pathlib import Path


def _resolve_one(name: str, resolver=None) -> dict:
    """Return a resolved entry (real meta_id) or an honest flagged_unverified entry.
    NEVER fabricates a meta_id."""
    meta_id = None
    if resolver is not None:
        try:
            meta_id = resolver(name)
        except Exception:  # noqa: BLE001 — a resolver error degrades, never fabricates
            meta_id = None
    if meta_id:
        return {"name": name, "resolved": True, "meta_id": str(meta_id)}
    return {"name": name, "flagged_unverified": True}


def build(run_dir: Path, groups_spec: list, resolver=None) -> dict:
    """groups_spec: [{name, explanation, layer1:[names], layer2:[names], layer3:[names]}]."""
    out_groups = []
    for g in groups_spec:
        og = {"name": g.get("name", ""), "explanation": g.get("explanation", "")}
        for layer in ("layer1", "layer2", "layer3"):
            og[layer] = [_resolve_one(str(n), resolver) for n in (g.get(layer) or [])]
        out_groups.append(og)
    obj = {"groups": out_groups}
    p = run_dir / "working" / "checkpoints" / "s6-targeting.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    os.replace(tmp, p)
    # A human-readable brief alongside the machine file.
    md = ["# Targeting brief (PLAI three-tier)\n"]
    for og in out_groups:
        md.append(f"## {og['name']}\n\n_{og['explanation']}_\n")
        for layer in ("layer1", "layer2", "layer3"):
            names = ", ".join(
                f"{it['name']}" + (f" (meta:{it['meta_id']})" if it.get("resolved")
                                   else " (flagged-unverified)")
                for it in og[layer])
            md.append(f"- **{layer}:** {names}")
        md.append("")
    (run_dir / "working" / "checkpoints" / "s6-targeting-brief.md").write_text("\n".join(md))
    return obj


def main():
    ap = argparse.ArgumentParser(description="Resolve targeting interests (or flag).")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--groups", required=True, help="path to a groups.json spec")
    args = ap.parse_args()
    rd = Path(args.run_dir).resolve()
    spec = json.loads(Path(args.groups).read_text())
    obj = build(rd, spec, resolver=None)  # no resolver on this box -> honest degrade
    flagged = sum(1 for g in obj["groups"] for layer in ("layer1", "layer2", "layer3")
                  for it in g[layer] if it.get("flagged_unverified"))
    print(json.dumps({"groups": len(obj["groups"]), "flagged_unverified": flagged}, indent=2))


if __name__ == "__main__":
    main()
