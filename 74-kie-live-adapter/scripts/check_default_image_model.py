#!/usr/bin/env python3
"""Refuse a Skill 74 default image model that is not priced PER PICTURE (X-97, owner order 2026-11-10).

The pinned fallback default (KNOWN_DEFAULTS) must be in KIE's catalog with a per-picture price unit
(per-image or per-job, the same pair Skill 83's image_plan accepts). A token-priced default makes every paid
run that names no model refuse, so it is refused here first.

Price evidence, first hit wins per model id: --catalog FILE (a live catalog.json, operator boxes), then
references/kie-default-price-evidence.json (rows copied verbatim from the live catalog), then the registry
snapshot. A default with no evidence at all is refused: an unknown price is not a picture price.

Usage: python3 scripts/check_default_image_model.py [--catalog catalog.json]
Exit 0 = ok, 1 = defect (each named), 2 = the check could not run.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)


def load_adapter():
    spec = importlib.util.spec_from_file_location("kie_live_adapter_under_check", os.path.join(HERE, "kie_live_adapter.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check(known_defaults, rows, adapter=None):
    """known_defaults {family: model id}, rows {model id: {"pricingDesc": text}} -> list of defect strings."""
    k = adapter or load_adapter()
    bad = []
    for family, mid in sorted(known_defaults.items()):
        if family not in k.PICTURE_PRICED_FAMILIES:
            continue
        if k.family_of(mid) != family:
            bad.append("%s default %s is not a %s model" % (family, mid, family))
            continue
        row = rows.get(mid)
        if row is None:
            bad.append("%s default %s has no price evidence (not in the catalog rows, evidence file or registry)" % (family, mid))
            continue
        unit = k.parse_pricing(row.get("pricingDesc"))["unit"]
        if unit not in k.PICTURE_PRICE_UNITS:
            bad.append("%s default %s is priced %s, not per picture (%s)" % (family, mid, unit, "/".join(k.PICTURE_PRICE_UNITS)))
    return bad


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_rows(catalog=None):
    rows = {}
    reg = os.path.join(SKILL, "references", "kie-model-registry.json")
    if os.path.isfile(reg):
        for m in _read(reg).get("models", []):
            rows[m["id"]] = {"pricingDesc": ((m.get("pricing") or {}).get("raw"))}
    ev = os.path.join(SKILL, "references", "kie-default-price-evidence.json")
    if os.path.isfile(ev):
        rows.update({m["model"]: m for m in _read(ev).get("rows", [])})
    if catalog:
        rows.update({m["model"]: m for m in _read(catalog).get("models", [])})
    return rows


def main(argv):
    catalog = argv[argv.index("--catalog") + 1] if "--catalog" in argv else None
    try:
        k = load_adapter()
        bad = check(k.KNOWN_DEFAULTS, load_rows(catalog), k)
    except (OSError, ValueError, KeyError, AttributeError) as exc:
        print("check_default_image_model: could not run: %s: %s" % (type(exc).__name__, exc))
        return 2
    for b in bad:
        print("DEFECT: " + b)
    if not bad:
        print("OK: every picture-family default is priced per picture (%s)" % ", ".join(
            "%s=%s" % kv for kv in sorted(k.KNOWN_DEFAULTS.items())))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
