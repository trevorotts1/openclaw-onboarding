#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_prompt.py -- model-aware prompt validator for Agnes Image 2.1 Flash.

Authority: Spec §5 (Prompt Policy), §10.5 (Agnes Image), §14 (Validators).

Validates prompt character count against BlackCEO house operating bands without
enforcing an invented vendor hard cap.

Rules:
- Vendor cap for Agnes Image 2.1 Flash is NOT_PUBLISHED.
- Prompts < 5,000 chars: thin stub (warn/info: house target floor is 5,000; short user
  prompts are not an error, expand them). Non-fatal (exit 0).
- Prompts 5,000 - 9,000 chars: target zone. Pass (exit 0).
- Prompts 9,000 - 19,000 chars: upper house band. Pass (exit 0).
- Prompts > 19,000 chars: above house preferred max (warn/info: exceeds 19K preferred
  headroom, but vendor cap is NOT_PUBLISHED; pass if user intent). Non-fatal (exit 0).
- Logo rule (--logo): requires I2I intent in prompt/context (exit 2 if logo mentioned without I2I).
- Style ref rule (--style-ref): requires style-reference-only directive verbatim (exit 2 if missing).

Exit codes:
  0 -- valid or soft-warning status
  2 -- hard violation (logo without I2I, missing style-ref directive)
  3 -- usage error / file read failure
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

SUPPORTED_MODELS = {"agnes-image-2.1-flash"}

HOUSE_MIN_CHARS = 5000
HOUSE_TARGET_CHARS = 9000
HOUSE_MAX_CHARS = 19000

STYLE_REF_DIRECTIVE = (
    "Use the attached images only as style reference for color grading, lighting, "
    "and composition -- do not copy their subjects, faces, or text."
)

LOGO_TOKENS = [
    "logo", "logomark", "wordmark", "brand mark", "brandmark",
    "monogram", "tagline lockup", "lockup",
    "brand icon", "brand image", "existing brand",
    "client's logo", "company logo",
]

I2I_INTENT_TOKENS = [
    "image-to-image", "img2img", "i2i",
    "extra_body.image", "input_urls", "image_input",
    "reference image", "reference the logo", "logo as reference",
    "use the attached", "style reference", "reference for",
    "provided logo", "attached logo", "supplied logo",
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def evaluate_prompt(prompt: str, model: str = "agnes-image-2.1-flash",
                    logo: bool = False, style_ref: bool = False) -> Dict[str, any]:
    if model not in SUPPORTED_MODELS:
        return {
            "valid": False,
            "exit_code": 2,
            "error": f"Unsupported model: '{model}'. Supported: {sorted(list(SUPPORTED_MODELS))}"
        }

    stripped = prompt.strip()
    char_count = len(stripped)

    if not stripped:
        return {
            "valid": False,
            "exit_code": 2,
            "error": "Prompt is empty or whitespace-only."
        }

    # Length band categorization (non-fatal, vendor cap is NOT_PUBLISHED)
    if char_count < HOUSE_MIN_CHARS:
        band_status = "THIN_STUB"
        length_note = (
            f"Prompt is {char_count} chars (below house target floor {HOUSE_MIN_CHARS}). "
            "Non-fatal: short user prompt is not an error, expand it."
        )
    elif char_count <= HOUSE_TARGET_CHARS:
        band_status = "TARGET_ZONE"
        length_note = f"Prompt is {char_count} chars (target zone 5,000-9,000)."
    elif char_count <= HOUSE_MAX_CHARS:
        band_status = "UPPER_BAND"
        length_note = f"Prompt is {char_count} chars (upper house band 9,000-19,000)."
    else:
        band_status = "ABOVE_PREFERRED_MAX"
        length_note = (
            f"Prompt is {char_count} chars (above house preferred max {HOUSE_MAX_CHARS}). "
            "Non-fatal: vendor cap NOT_PUBLISHED, allowed if intentional."
        )

    # Logo check
    text_lc = _norm(stripped)
    logo_hit = any(tok in text_lc for tok in LOGO_TOKENS)
    if logo or logo_hit:
        i2i_hit = any(tok in text_lc for tok in I2I_INTENT_TOKENS)
        if not i2i_hit:
            return {
                "valid": False,
                "exit_code": 2,
                "char_count": char_count,
                "band_status": band_status,
                "error": "Logo mentioned but image-to-image reference intent missing. Logo requests must use I2I."
            }

    # Style-ref check
    if style_ref:
        # Check directive present (normalized)
        directive_norm = _norm(STYLE_REF_DIRECTIVE)
        if directive_norm not in text_lc:
            return {
                "valid": False,
                "exit_code": 2,
                "char_count": char_count,
                "band_status": band_status,
                "error": f"Style reference attached but directive missing. Must include verbatim: '{STYLE_REF_DIRECTIVE}'"
            }

    return {
        "valid": True,
        "exit_code": 0,
        "model": model,
        "char_count": char_count,
        "band_status": band_status,
        "note": length_note
    }


def run_self_tests() -> int:
    fixtures = [
        # 1. Thin stub 300 chars -> exit 0, status THIN_STUB
        ("Stub " * 60, "agnes-image-2.1-flash", False, False, 0, "THIN_STUB"),
        # 2. 5012 chars -> exit 0, status TARGET_ZONE
        ("Word " * 1003, "agnes-image-2.1-flash", False, False, 0, "TARGET_ZONE"),
        # 3. 9000 chars -> exit 0, status TARGET_ZONE
        ("A" * 9000, "agnes-image-2.1-flash", False, False, 0, "TARGET_ZONE"),
        # 4. 18999 chars -> exit 0, status UPPER_BAND
        ("A" * 18999, "agnes-image-2.1-flash", False, False, 0, "UPPER_BAND"),
        # 5. Long 40K chars -> exit 0, status ABOVE_PREFERRED_MAX (warn-but-pass)
        ("A" * 40000, "agnes-image-2.1-flash", False, False, 0, "ABOVE_PREFERRED_MAX"),
        # 6. Logo without I2I -> exit 2
        ("Company logo on billboard. " * 200, "agnes-image-2.1-flash", True, False, 2, None),
        # 7. Style-ref missing directive -> exit 2
        ("A" * 6000, "agnes-image-2.1-flash", False, True, 2, None),
        # 8. Style-ref with directive -> exit 0
        (f"A scene. {STYLE_REF_DIRECTIVE} " + "A" * 6000, "agnes-image-2.1-flash", False, True, 0, "TARGET_ZONE"),
    ]

    failed = 0
    for idx, (p, m, l, s, expected_exit, expected_status) in enumerate(fixtures, 1):
        res = evaluate_prompt(p, model=m, logo=l, style_ref=s)
        actual_exit = res.get("exit_code")
        actual_status = res.get("band_status")
        if actual_exit != expected_exit or (expected_status and actual_status != expected_status):
            print(f"Self-test fixture {idx} FAILED: expected exit {expected_exit} status {expected_status}, got exit {actual_exit} status {actual_status} ({res})", file=sys.stderr)
            failed += 1

    if failed == 0:
        print("validate_prompt.py --self-test: PASS (all fixtures verified)")
        return 0
    return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate Agnes Image prompt.")
    parser.add_argument("--self-test", action="store_true", help="Run deterministic test fixtures.")
    parser.add_argument("--model", default="agnes-image-2.1-flash", help="Target model.")
    parser.add_argument("--file", help="Path to prompt text file.")
    parser.add_argument("--stdin", action="store_true", help="Read prompt from stdin.")
    parser.add_argument("--logo", action="store_true", help="Require logo I2I intent check.")
    parser.add_argument("--style-ref", action="store_true", help="Require style-reference-only directive.")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_tests()

    prompt_text = ""
    if args.file:
        p = Path(args.file)
        if not p.is_file():
            print(f"Error: file not found '{args.file}'", file=sys.stderr)
            return 3
        prompt_text = p.read_text(encoding="utf-8", errors="replace")
    elif args.stdin:
        prompt_text = sys.stdin.read()
    else:
        parser.print_usage(sys.stderr)
        return 3

    res = evaluate_prompt(prompt_text, model=args.model, logo=args.logo, style_ref=args.style_ref)
    print(json.dumps(res, indent=2))
    return res.get("exit_code", 0)


if __name__ == "__main__":
    sys.exit(main())
