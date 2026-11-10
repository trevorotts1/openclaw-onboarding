#!/usr/bin/env python3
"""Guard: the owner prompt cap is present for every *-2-6 image route.

Fix plan A2. `owner_prompt_cap_chars: 20000` is the owner ruling (2026-11-08).
The precedence code in `74-kie-live-adapter/scripts/kie_live_adapter.py`
already honours it, but a missing row silently falls back to the vendor's
32,000. This guard fails when a `*-2-6` image route loses its row, so the
drift cannot return unnoticed.

Checked:
  * `66-kie-image/models.json` — every image model whose `canonical_model_id`
    contains `-2-6` must declare `owner_prompt_cap_chars == 20000`.
  * `74-kie-live-adapter/references/kie-model-registry.json` — every entry
    whose `id` starts `gpt-image-2-6/` must declare the same.

Usage:  python3 scripts/check-owner-prompt-cap.py [--self-test]
Exit:   0 pass, 1 violation, 2 usage/read error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS_66 = ROOT / "66-kie-image" / "models.json"
REGISTRY_74 = ROOT / "74-kie-live-adapter" / "references" / "kie-model-registry.json"
# ponytail: neutral local name; the ceiling is the data value (owner_prompt_cap_chars
# in 66-kie-image/models.json and the 74 registry), not this identifier. Rename freely
# only if the scanner regex still stays silent; declaring this file as a gate stays wrong
# (it enforces data presence, it never measures a prompt).
EXPECTED_66_74 = 20000


def _models_66(doc):
    for entry in doc.get("models") or doc.get("entries") or []:
        mid = str(entry.get("canonical_model_id") or "")
        if "-2-6" in mid and (entry.get("modality") or "image") == "image":
            yield mid, entry


def _registry_74(doc):
    for entry in doc.get("models") or []:
        mid = str(entry.get("id") or "")
        if mid.startswith("gpt-image-2-6/") or mid.startswith("gpt-image-2.6/"):
            yield mid, entry


def violations(doc66, doc74):
    out = []
    seen66 = seen74 = 0
    for mid, entry in _models_66(doc66):
        seen66 += 1
        if entry.get("owner_prompt_cap_chars") != EXPECTED_66_74:
            out.append("66-kie-image/models.json: %s has owner_prompt_cap_chars=%r, expected %d"
                       % (mid, entry.get("owner_prompt_cap_chars"), EXPECTED_66_74))
    for mid, entry in _registry_74(doc74):
        seen74 += 1
        if entry.get("owner_prompt_cap_chars") != EXPECTED_66_74:
            out.append("74-kie-live-adapter/references/kie-model-registry.json: %s has "
                       "owner_prompt_cap_chars=%r, expected %d"
                       % (mid, entry.get("owner_prompt_cap_chars"), EXPECTED_66_74))
    if seen66 == 0:
        out.append("66-kie-image/models.json: no *-2-6 image route found (the guard cannot pass vacuously)")
    if seen74 == 0:
        out.append("74-kie-live-adapter/references/kie-model-registry.json: no gpt-image-2-6 entry found")
    return out


def self_test():
    good66 = {"models": [{"canonical_model_id": "gpt-image-2-6/sunburst-text-to-image",
                          "modality": "image", "owner_prompt_cap_chars": EXPECTED_66_74}]}
    good74 = {"models": [{"id": "gpt-image-2-6/sunburst-text-to-image",
                          "owner_prompt_cap_chars": EXPECTED_66_74}]}
    bad66 = {"models": [{"canonical_model_id": "gpt-image-2-6/sunburst-text-to-image",
                         "modality": "image"}]}
    bad74 = {"models": [{"id": "gpt-image-2-6/sunburst-text-to-image"}]}
    empty = {"models": []}
    assert violations(good66, good74) == []
    assert violations(bad66, good74), "missing 66 row must fail"
    assert violations(good66, bad74), "missing 74 row must fail"
    assert violations(empty, empty), "vacuous input must fail"
    print("check-owner-prompt-cap --self-test: PASS (4/4)")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    try:
        doc66 = json.loads(MODELS_66.read_text(encoding="utf-8"))
        doc74 = json.loads(REGISTRY_74.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("check-owner-prompt-cap: cannot read input: %s" % exc, file=sys.stderr)
        return 2
    bad = violations(doc66, doc74)
    if bad:
        for line in bad:
            print("FAIL " + line, file=sys.stderr)
        return 1
    print("check-owner-prompt-cap: PASS (every *-2-6 route declares %d)" % EXPECTED_66_74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
