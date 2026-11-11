#!/usr/bin/env python3
"""Refuse a Skill 74 default image model that is not GPT Image Sunburst at medium quality with a per-picture price.

X-97 (owner order 2026-11-10, repo rule N43). The pinned default (PINNED_DEFAULTS) must be:
  1. a gpt-image Sunburst model, id shaped gpt-image-<major>-<minor>/sunburst-<text|image>-to-image (slash, never flare);
  2. generated with DEFAULT_QUALITY "medium" when the caller names none, a member of the KIE `quality` enum;
  3. priced per picture for EVERY size tier (1K, 2K, 4K) at that quality in
     references/kie-default-price-evidence.json (KIE's published reference table; the model is billed by tokens).
A default with no such row is refused: an unknown price is not a picture price.

Usage: python3 scripts/check_default_image_model.py
Exit 0 = ok, 1 = defect (each named), 2 = the check could not run.
"""
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TIERS = ("1K", "2K", "4K")
ID_RE = re.compile(r"^gpt-image-\d+-\d+/sunburst-(?:text|image)-to-image$")


def load_adapter():
    spec = importlib.util.spec_from_file_location("kie_live_adapter_under_check", os.path.join(HERE, "kie_live_adapter.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check(k, evidence):
    """k: the adapter module, evidence: the parsed price evidence -> list of defect strings."""
    bad = []
    for cap, mid in sorted(k.PINNED_DEFAULTS.items()):
        if not ID_RE.match(mid):
            bad.append("default %s (%s) is not a gpt-image Sunburst model (slash form, never flare)" % (mid, cap))
        q = k.DEFAULT_QUALITY
        rows = (k.reference_table(evidence, mid) or {}).get(q) or {}
        missing = [t for t in TIERS if not isinstance(rows.get(t), (int, float)) or isinstance(rows.get(t), bool) or rows[t] <= 0]
        if missing:
            bad.append("default %s has no per-picture reference price at quality %s for %s" % (mid, q, "/".join(missing)))
    if k.DEFAULT_QUALITY != "medium":
        bad.append("default quality is %r, not medium" % (k.DEFAULT_QUALITY,))
    if k.DEFAULT_QUALITY not in k.QUALITY_ENUM:
        bad.append("default quality %r is not in the KIE quality enum %s" % (k.DEFAULT_QUALITY, "/".join(k.QUALITY_ENUM)))
    if k.KNOWN_DEFAULTS.get("gpt-image") != k.PINNED_DEFAULTS["Text to Image"]:
        bad.append("KNOWN_DEFAULTS gpt-image is not the pinned Sunburst text-to-image default")
    if (evidence.get("request_field") or {}).get("enum") != list(k.QUALITY_ENUM):
        bad.append("evidence quality enum differs from the adapter QUALITY_ENUM")
    return bad


def main():
    try:
        k = load_adapter()
        bad = check(k, k.load_price_evidence(strict=True))
    except Exception as exc:  # noqa: BLE001  (any failure to load or run is exit 2, never a pass)
        print("check_default_image_model: could not run: %s: %s" % (type(exc).__name__, exc))
        return 2
    for b in bad:
        print("DEFECT: " + b)
    if not bad:
        print("OK: default %s, quality %s, per-picture price for %s" % (
            k.PINNED_DEFAULT, k.DEFAULT_QUALITY, "/".join(TIERS)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
