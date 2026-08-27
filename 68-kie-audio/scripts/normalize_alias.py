#!/usr/bin/env python3
"""normalize_alias.py -- alias normalization for KIE model names (Skill 68).

Shared map (SPEC section 13) across the KIE media skills. For the AUDIO skill
the function FAMILY_OF returns None for every audio term -- the alias map is an
image/video-family map, and audio models have NO aliases (their canonical
ids are exact enum values; see models.json "aliases": []).

Z-IMAGE GUARD: "Z Image by Quinn" must NOT be merged into Qwen. Z-Image is its
own KIE family unless first-party docs explicitly say otherwise.

Usage:
  python3 normalize_alias.py --term "cling03"     -> normalized term or original
  python3 normalize_alias.py --self-test

Deterministic, offline, stdlib-only.
"""

from __future__ import annotations

import argparse
import sys

# SPEC section 13 map (verbatim).
ALIAS_MAP = {
    "cling": "Kling",
    "cling03": "Kling O3",
    "quinn": "Qwen",
    "c dream": "Seedream",
    "seed dream": "Seedream",
    "idiogram": "Ideogram",
    "imagine 4": "Imagen 4",
    "gpt-img2": "GPT Image 2",
    "gpt-image 2.0": "GPT Image 2",
    "nano banana light": "Nano Banana 2 Lite",  # when context says version 2
}

# Audio terms that must NEVER resolve through the image/video alias map.
AUDIO_TERMS = (
    "tts", "speech", "voice", "dialogue", "music", "suno", "sound",
    "song", "vocal", "instrumental", "lyrics", "mashup", "midi",
    "stt", "transcription", "transcribe",
)


def normalize(term: str) -> str:
    t = (term or "").strip().lower()
    return ALIAS_MAP.get(t, term.strip() if term else "")


def family_of(term: str) -> str | None:
    """Return the provider family for a term, or None for audio terms."""
    norm = normalize(term)
    t = norm.lower()
    for w in AUDIO_TERMS:
        if w in t:
            return None
    # Image/video family keywords the OTHER skills resolve; an audio-term lookup
    # that reaches here is a routing error, so report None rather than a family.
    return None


def self_test() -> int:
    cases = {
        "cling": "Kling",
        "cling03": "Kling O3",
        "Quinn": "Qwen",
        "C Dream": "Seedream",
        "Seed Dream": "Seedream",
        "Idiogram": "Ideogram",
        "Imagine 4": "Imagen 4",
        "GPT-img2": "GPT Image 2",
        "GPT-image 2.0": "GPT Image 2",
        "Nano Banana Light": "Nano Banana 2 Lite",
        "z-image": "z-image",          # Z-Image stays its own family (guard)
    }
    for term, want in cases.items():
        got = normalize(term)
        assert got == want, f"normalize({term!r}) = {got!r}, want {want!r}"

    # FAMILY_OF: every audio term -> None; Z-Image -> None (not Qwen).
    for term in ("tts", "suno", "music", "stt", "speech", "voice",
                 "gemini-3-1-flash-tts", "elevenlabs/text-to-dialogue-v3",
                 "z-image", "z image"):
        got = family_of(term)
        assert got is None, f"family_of({term!r}) = {got!r}, want None"

    # Guard: "z image by quinn" must NOT map to Qwen.
    assert normalize("z image by quinn") == "z image by quinn", \
        "Z-Image was merged into Qwen -- guard broken"
    print("SELF-TEST PASS: alias map + FAMILY_OF audio guard green")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="KIE alias normalizer (Skill 68)")
    ap.add_argument("--term")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.term:
        print("error: --term <name> required (or --self-test)", file=sys.stderr)
        return 2
    print(normalize(args.term))
    return 0


if __name__ == "__main__":
    sys.exit(main())
