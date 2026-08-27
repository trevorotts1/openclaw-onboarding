#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""normalize_alias.py -- normalizes speech-to-text/transcription aliases to KIE Video family names.

Authority: Spec 13 (Alias Normalization) adapted for video families.
Maps transcription errors, abbreviations, and informal references to canonical
family keys or canonical model IDs.
"""

from __future__ import annotations

import argparse
import sys

# Transcription alias -> normalized family name or canonical model group
ALIAS_MAP = {
    # Kling variations
    "cling": "kling",
    "kling": "kling",
    "kling ai": "kling",
    "kling video": "kling",
    "kling 3": "kling-3.0",
    "kling 3.0": "kling-3.0",
    "kling3": "kling-3.0",
    "kling o3": "kling-3.0-omni",
    "kling-o3": "kling-3.0-omni",
    "kling 3 omni": "kling-3.0-omni",
    "kling 3.0 omni": "kling-3.0-omni",
    "kling omni": "kling-3.0-omni",
    "kling-omni": "kling-3.0-omni",
    "kling omni 3": "kling-3.0-omni",
    "kling omni 3.0": "kling-3.0-omni",
    "kling 2.6": "kling-2.6",
    "kling 2.6 motion": "kling-2.6",
    "kling 2.5": "kling",
    "kling 2.5 turbo": "kling",
    "kling turbo": "kling",
    # Wan variations
    "wan": "wan-2-7",
    "wan video": "wan-2-7",
    "wan 2.7": "wan-2-7",
    "wan2.7": "wan-2-7",
    "wan 2.7 video": "wan-2-7",
    "wan 3": "wan-3-0",
    "wan 3.0": "wan-3-0",
    "wan3": "wan-3-0",
    "wan 3 video": "wan-3-0",
    "wan 3.0 video": "wan-3-0",
    "wan 3 prime": "wan-3-0",
    "wan 3.0 prime": "wan-3-0",
    "wan 3.0 video prime": "wan-3-0",
    # Seedance / Bytedance variations
    "seedance": "bytedance",
    "seed dance": "bytedance",
    "sea dance": "bytedance",
    "bytedance video": "bytedance",
    "seedance 2.5": "bytedance",
    "seedance 2 mini": "bytedance",
    "seedance mini": "bytedance",
    # PixVerse variations
    "pixverse": "pixverse-v6",
    "pix verse": "pixverse-v6",
    "pixverse v6": "pixverse-v6",
    "pixverse 6": "pixverse-v6",
    # MiniMax variations
    "minimax": "minimax-h3",
    "mini max": "minimax-h3",
    "minimax h3": "minimax-h3",
    "minimax video": "minimax-h3",
    "hailuo": "minimax-h3",
    # HappyHorse variations
    "happyhorse": "happyhorse",
    "happy horse": "happyhorse",
    "happyhorse 1.1": "happyhorse-1-1",
    "happy horse 1.1": "happyhorse-1-1",
    # Gemini Omni video
    "gemini omni": "gemini-omni-video",
    "gemini video": "gemini-omni-video",
    "gemini omni video": "gemini-omni-video",
    # Runway variations
    "runway": "runway",
    "runway gen3": "runway",
    "runway gen 3": "runway",
    "runway video": "runway",
    # Veo variations
    "veo": "veo3",
    "veo3": "veo3",
    "veo 3": "veo3",
    "veo 3.1": "veo3",
    "veo fast": "veo3",
    "veo 3 fast": "veo3",
    "veo lite": "veo3",
    "veo 3 lite": "veo3",
}

# Family name -> canonical KIE Video model IDs (registry models.json).
FAMILY_OF = {
    "wan-3-0": [
        "wan/3-0-video",
        "wan/3-0-video-prime",
    ],
    "kling-3.0-omni": [
        "kling-3.0-omni/text-to-video",
        "kling-3.0-omni/image-to-video",
        "kling-3.0-omni/transformation",
        "kling-3.0-omni/reference-to-video",
    ],
    "kling-3.0": [
        "kling-3.0/video",
        "kling-3.0/motion-control",
    ],
    "kling-2.6": [
        "kling-2.6/motion-control",
    ],
    "kling": [
        "kling/v2-5-turbo-text-to-video-pro",
        "kling/v2-5-turbo-image-to-video-pro",
    ],
    "bytedance": [
        "bytedance/seedance-2-5",
        "bytedance/seedance-2-mini",
    ],
    "pixverse-v6": [
        "pixverse-v6/text-to-video",
        "pixverse-v6/image-to-video",
        "pixverse-v6/transition",
        "pixverse-v6/extend",
        "pixverse-v6/reference-to-video",
    ],
    "minimax-h3": [
        "minimax-h3/text-to-video",
        "minimax-h3/image-to-video",
        "minimax-h3/reference-to-video",
    ],
    "wan-2-7": [
        "wan/2-7-r2v",
        "wan/2-7-videoedit",
        "wan/2-7-text-to-video",
        "wan/2-7-image-to-video",
    ],
    "happyhorse-1-1": [
        "happyhorse-1-1/text-to-video",
        "happyhorse-1-1/image-to-video",
        "happyhorse-1-1/reference-to-video",
    ],
    "happyhorse": [
        "happyhorse/text-to-video",
        "happyhorse/image-to-video",
        "happyhorse/reference-to-video",
        "happyhorse/video-edit",
    ],
    "gemini-omni-video": [
        "gemini-omni-video",
    ],
    "runway": [
        "runway",
    ],
    "veo3": [
        "veo3",
        "veo3_fast",
        "veo3_lite",
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
    parser = argparse.ArgumentParser(description="Normalize KIE Video model alias to family name.")
    parser.add_argument("model_name", nargs="?", help="Model alias or family name to normalize.")
    parser.add_argument("--self-test", action="store_true", help="Run self-test.")
    args = parser.parse_args(argv)

    if args.self_test:
        assert normalize_alias("cling") == "kling"
        assert normalize_alias("Kling O3") == "kling-3.0-omni"
        assert normalize_alias("kling-o3") == "kling-3.0-omni"
        assert normalize_alias("kling 3.0 omni") == "kling-3.0-omni"
        assert normalize_alias("wan 3.0 video") == "wan-3-0"
        assert normalize_alias("Wan 3 Prime") == "wan-3-0"
        assert normalize_alias("seed dance") == "bytedance"
        assert normalize_alias("Seedance 2.5") == "bytedance"
        assert normalize_alias("pix verse") == "pixverse-v6"
        assert normalize_alias("mini max") == "minimax-h3"
        assert normalize_alias("hailuo") == "minimax-h3"
        assert normalize_alias("happy horse 1.1") == "happyhorse-1-1"
        assert normalize_alias("gemini omni") == "gemini-omni-video"
        assert normalize_alias("runway gen3") == "runway"
        assert normalize_alias("veo 3.1") == "veo3"
        # every family maps to at least one real canonical id
        for fam, ids in FAMILY_OF.items():
            assert ids, f"FAMILY_OF[{fam!r}] is empty"
        # unknown input returns None (never fabricate)
        assert normalize_alias("nonsense video model") is None
        assert normalize_alias("") is None
        assert normalize_alias("   ") is None
        print("normalize_alias.py --self-test: PASS")
        return 0

    if not args.model_name:
        parser.print_usage(sys.stderr)
        return 1

    fam = normalize_alias(args.model_name)
    if fam is None:
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
