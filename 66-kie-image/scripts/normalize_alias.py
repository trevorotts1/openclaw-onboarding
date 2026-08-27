#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""normalize_alias.py -- normalizes speech-to-text/transcription aliases to KIE Image family names.

Authority: Spec 13 (Alias Normalization). The map below exists so transcription
errors ("Quinn", "C Dream", "Idiogram") do not create nonexistent models.

Z-IMAGE GUARD: Z-Image is its own KIE family. The owner may say "Z Image by
Quinn" -- that must NEVER resolve into the Qwen family. FAMILY_OF["z image"]
points only at "z-image"; nothing in ALIAS_MAP maps to "qwen" from a z-image
token, and "z image"/"z-image" tokens resolve to the z-image family only.
"""

from __future__ import annotations

import argparse
import sys

# Transcription alias -> normalized family name (spec 13, image-relevant rows).
ALIAS_MAP = {
    "quinn": "qwen",
    "quinn image 3.0": "qwen",
    "c dream": "seedream",
    "seed dream": "seedream",
    "idiogram": "ideogram",
    "imagine 4": "imagen 4",
    "gpt-img2": "gpt image 2",
    "gpt-image 2.0": "gpt image 2",
    "nano banana light": "nano banana 2 lite",
    # Z-Image stays its own family -- never funneled into qwen.
    "z image": "z image",
    "z-image": "z image",
}

# Family name -> canonical KIE Market model IDs (registry models.json).
FAMILY_OF = {
    "gpt image 2": [
        "gpt-image-2-text-to-image",
        "gpt-image-2-image-to-image",
    ],
    "qwen": [
        "qwen3/text-to-image",
        "qwen3-pro/text-to-image",
        "qwen3/image-to-image",
        "qwen3-pro/image-to-image",
    ],
    "seedream": [
        "seedream/5-pro-text-to-image",
        "seedream/5-pro-image-to-image",
        "seedream/5-pro-layer-decomposition",
        "seedream/5-lite-text-to-image",
        "seedream/5-lite-image-to-image",
        "seedream/4.5-text-to-image",
        "seedream/4-5-edit",
    ],
    "nano banana 2": ["nano-banana-2"],
    "nano banana 2 lite": ["nano-banana-2-lite"],
    "nano banana pro": ["nano-banana-pro"],
    "nano banana legacy": ["google/nano-banana"],
    "wan 2.7": ["wan/2-7-image", "wan/2-7-image-pro"],
    "flux.2": [
        "flux-2/pro-text-to-image",
        "flux-2/pro-image-to-image",
        "flux-2/flex-text-to-image",
        "flux-2/flex-image-to-image",
    ],
    "z image": ["z-image"],
    "ideogram": [
        "ideogram/v3-text-to-image",
        "ideogram/v3-edit",
        "ideogram/v3-remix",
    ],
    "imagen 4": [
        "google/imagen4-fast",
        "google/imagen4",
        "google/imagen4-ultra",
    ],
}


def normalize_alias(s: str) -> str | None:
    """Return the normalized family name for an alias, or None when unknown.

    Case/whitespace-insensitive. Unknown input returns None (unknown must not
    fabricate a model).
    """
    if not isinstance(s, str):
        return None
    cleaned = " ".join(s.strip().lower().split())
    if not cleaned:
        return None
    return ALIAS_MAP.get(cleaned)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Normalize KIE Image model alias to family name.")
    parser.add_argument("model_name", nargs="?", help="Model alias or family name to normalize.")
    parser.add_argument("--self-test", action="store_true", help="Run self-test.")
    args = parser.parse_args(argv)

    if args.self_test:
        assert normalize_alias("quinn") == "qwen"
        assert normalize_alias("Quinn") == "qwen"
        assert normalize_alias("c dream") == "seedream"
        assert normalize_alias("Seed Dream") == "seedream"
        assert normalize_alias("idiogram") == "ideogram"
        assert normalize_alias("Idiogram") == "ideogram"
        assert normalize_alias("imagine 4") == "imagen 4"
        assert normalize_alias("gpt-img2") == "gpt image 2"
        assert normalize_alias("GPT-image 2.0") == "gpt image 2"
        assert normalize_alias("nano banana light") == "nano banana 2 lite"
        # Z-Image guard: "z image" must NOT resolve into qwen.
        assert normalize_alias("z image") == "z image"
        assert normalize_alias("z-image") == "z image"
        assert normalize_alias("z image") != "qwen"
        assert "z image" not in [k for k, v in FAMILY_OF.items() if "qwen3" in str(v)]
        # every family maps to at least one real canonical id
        for fam, ids in FAMILY_OF.items():
            assert ids, "FAMILY_OF[%r] is empty" % fam
        # unknown input returns None (never fabricate)
        assert normalize_alias("nonsense model") is None
        assert normalize_alias("") is None
        assert normalize_alias("   ") is None
        print("normalize_alias.py --self-test: PASS")
        return 0

    if not args.model_name:
        parser.print_usage(sys.stderr)
        return 1

    fam = normalize_alias(args.model_name)
    if fam is None:
        # also accept an already-canonical family name or model id pass-through
        cleaned = " ".join(args.model_name.strip().lower().split())
        if cleaned in FAMILY_OF:
            fam = cleaned
        else:
            print("UNKNOWN", file=sys.stderr)
            return 1
    print(fam)
    return 0


if __name__ == "__main__":
    sys.exit(main())
