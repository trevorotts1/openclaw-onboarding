#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_prompt.py -- model-aware prompt validator for Agnes Image 2.1 Flash.

Authority: SPEC.md "Build contract for detailed image prompts" (F32, program
social-planner-september-eighth); Spec §5 (Prompt Policy), §10.5 (Agnes Image),
§14 (Validators) for the general (non-social-planner) policy.

TWO bands, scoped (the F32 social-planner override does NOT change bands for
unrelated skills):

- GENERAL Agnes path (default): vendor cap for Agnes Image 2.1 Flash is
  NOT_PUBLISHED. Prompts < 5,000 chars: thin stub (warn, non-fatal). 5,000-9,000:
  target zone (pass). 9,000-19,000: upper house band (pass). > 19,000: above
  house preferred max (warn, non-fatal — vendor cap NOT_PUBLISHED).

- SOCIAL-PLANNER path (--scope social-planner): HARD house band 9,000-19,000
  stripped Unicode chars (NFC-normalized, trimmed — the F32 owner requirement).
  8,999 FAILS (exit 2), 9,000 passes, 19,000 passes, 19,001 FAILS (exit 2).
  The count is len(unicodedata.normalize("NFC", final).strip()); the payload
  hash is recorded. This mirrors shared-utils/social_prompt_policy.json +
  social_prompt_compiler.py, and the same boundary applies AFTER reference
  instructions and negatives are added — validate the FINAL payload.

- Logo rule (--logo): requires I2I intent in prompt/context (exit 2 if logo
  mentioned without I2I). CORRECTED (F32): an IDENTITY/logo reference PRESERVES
  the approved mark — the style-only do-not-copy directive must NOT be applied
  to it. Per-reference instructions, not global: --style-ref applies the
  style-only directive ONLY when the reference is style-only; --identity-ref
  requires the preserve-the-mark instruction instead.

- Style ref rule (--style-ref): requires the style-reference-only directive
  verbatim (exit 2 if missing) — for STYLE references only.

Exit codes:
  0 -- valid or soft-warning status
  2 -- hard violation (band violation on the social-planner path, logo without
       I2I, missing style-ref directive, identity-ref without preserve rule)
  3 -- usage error / file read failure
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Tuple

SUPPORTED_MODELS = {"agnes-image-2.1-flash"}

# GENERAL (non-social-planner) house band — unchanged by F32.
HOUSE_MIN_CHARS = 5000
HOUSE_TARGET_CHARS = 9000
HOUSE_MAX_CHARS = 19000

# SOCIAL-PLANNER scoped override (F32) — hard, fail-closed.
SOCIAL_MIN_CHARS = 9000
SOCIAL_MAX_CHARS = 19000

STYLE_REF_DIRECTIVE = (
    "Use the attached images only as style reference for color grading, lighting, "
    "and composition -- do not copy their subjects, faces, or text."
)

# F32 corrected identity rule: an identity/logo reference PRESERVES the mark.
IDENTITY_REF_DIRECTIVE = (
    "Identity reference: reproduce this reference exactly -- preserve the "
    "approved mark's geometry, colors, proportions and wordmark spelling. Do not "
    "redraw, recolor, restyle or reinterpret it."
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


def count_social_chars(prompt: str) -> int:
    """THE F32 counting rule: len(unicodedata.normalize('NFC', final).strip())."""
    return len(unicodedata.normalize("NFC", prompt).strip())


def sha256_of(prompt: str) -> str:
    """Payload hash of the exact NFC-normalized, stripped transmitted string."""
    normalized = unicodedata.normalize("NFC", prompt).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def evaluate_prompt(prompt: str, model: str = "agnes-image-2.1-flash",
                    logo: bool = False, style_ref: bool = False,
                    identity_ref: bool = False,
                    scope: str = "general") -> Dict[str, any]:
    if model not in SUPPORTED_MODELS:
        return {
            "valid": False,
            "exit_code": 2,
            "error": f"Unsupported model: '{model}'. Supported: {sorted(list(SUPPORTED_MODELS))}"
        }

    if scope not in ("general", "social-planner"):
        return {
            "valid": False,
            "exit_code": 3,
            "error": f"Unknown scope '{scope}' — use 'general' or 'social-planner'."
        }

    stripped = prompt.strip()
    if not stripped:
        return {
            "valid": False,
            "exit_code": 2,
            "error": "Prompt is empty or whitespace-only."
        }

    social = scope == "social-planner"
    # The F32 social-planner count is NFC code points; the general band keeps
    # its historical raw-strip count.
    char_count = count_social_chars(prompt) if social else len(stripped)

    # Length band categorization
    if social:
        # HARD band 9,000-19,000 (fail-closed). The boundaries are exact:
        # 8,999 fails, 9,000 passes, 19,000 passes, 19,001 fails.
        if char_count < SOCIAL_MIN_CHARS:
            return {
                "valid": False, "exit_code": 2, "char_count": char_count,
                "scope": scope, "band_status": "BELOW_SOCIAL_FLOOR",
                "error": (f"AF-PROMPT-LENGTH: social-planner prompt is {char_count} "
                          f"stripped Unicode chars — below the house floor "
                          f"{SOCIAL_MIN_CHARS} ({SOCIAL_MIN_CHARS - 1} fails, "
                          f"{SOCIAL_MIN_CHARS} passes). Expand with useful visual "
                          "decisions via social_prompt_compiler.py — never padding.")
            }
        if char_count > SOCIAL_MAX_CHARS:
            return {
                "valid": False, "exit_code": 2, "char_count": char_count,
                "scope": scope, "band_status": "ABOVE_SOCIAL_CEILING",
                "error": (f"AF-PROMPT-LENGTH: social-planner prompt is {char_count} "
                          f"stripped Unicode chars — above the house ceiling "
                          f"{SOCIAL_MAX_CHARS} ({SOCIAL_MAX_CHARS + 1} fails, "
                          f"{SOCIAL_MAX_CHARS} passes). Condense without losing "
                          "required meaning — never truncate silently.")
            }
        band_status = "SOCIAL_BAND"
        length_note = (f"Prompt is {char_count} chars (social-planner house band "
                       f"{SOCIAL_MIN_CHARS}-{SOCIAL_MAX_CHARS}, hard fail-closed). "
                       "Semantic QC still required.")
    elif char_count < HOUSE_MIN_CHARS:
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

    # Logo check (I2I intent required when a logo is mentioned)
    text_lc = _norm(stripped)
    logo_hit = any(tok in text_lc for tok in LOGO_TOKENS)
    if logo or logo_hit:
        i2i_hit = any(tok in text_lc for tok in I2I_INTENT_TOKENS)
        if not i2i_hit:
            return {
                "valid": False,
                "exit_code": 2,
                "char_count": char_count,
                "scope": scope,
                "band_status": band_status,
                "error": "Logo mentioned but image-to-image reference intent missing. Logo requests must use I2I."
            }

    # Identity/logo REFERENCE (F32): must carry the preserve-the-mark rule —
    # and must NOT be given the style-only do-not-copy directive (the
    # corrected contradiction).
    if identity_ref:
        preserve_norm = _norm(IDENTITY_REF_DIRECTIVE.split("--", 1)[1]) if "--" in IDENTITY_REF_DIRECTIVE else _norm(IDENTITY_REF_DIRECTIVE)
        has_preserve = ("preserve" in text_lc and ("exactly" in text_lc or "redraw" in text_lc))
        has_style_only_on_identity = (
            ("style reference" in text_lc or "style-only" in text_lc)
            and "do not copy" in text_lc
            and ("logo" in text_lc or "identity" in text_lc)
        )
        if has_style_only_on_identity:
            return {
                "valid": False, "exit_code": 2, "char_count": char_count,
                "scope": scope, "band_status": band_status,
                "error": ("AF-PROMPT-CONFLICT: an identity/logo reference carries a "
                          "style-only do-not-copy directive. An identity/logo "
                          "reference PRESERVES the approved mark; style-only "
                          "directives belong on style references only "
                          "(per-reference instructions, never global).")
            }
        if not has_preserve:
            return {
                "valid": False, "exit_code": 2, "char_count": char_count,
                "scope": scope, "band_status": band_status,
                "error": ("Identity/logo reference attached but the "
                          "preserve-the-mark instruction is missing. Must state "
                          f"the preserve rule, e.g. '{IDENTITY_REF_DIRECTIVE}'")
            }

    # Style-ref check (style-only references)
    if style_ref:
        directive_norm = _norm(STYLE_REF_DIRECTIVE)
        if directive_norm not in text_lc:
            return {
                "valid": False,
                "exit_code": 2,
                "char_count": char_count,
                "scope": scope,
                "band_status": band_status,
                "error": f"Style reference attached but directive missing. Must include verbatim: '{STYLE_REF_DIRECTIVE}'"
            }

    result = {
        "valid": True,
        "exit_code": 0,
        "model": model,
        "scope": scope,
        "char_count": char_count,
        "band_status": band_status,
        "note": length_note
    }
    if social:
        # F32 spend receipt: hash + count recorded before spend.
        result["hash"] = sha256_of(prompt)
        result["count_rule"] = "len(unicodedata.normalize('NFC', final).strip())"
    return result


def run_self_tests() -> int:
    fixtures = [
        # 1. Thin stub 300 chars -> exit 0, status THIN_STUB (GENERAL scope)
        ("Stub " * 60, "agnes-image-2.1-flash", False, False, False, "general", 0, "THIN_STUB"),
        # 2. 5012 chars -> exit 0, status TARGET_ZONE
        ("Word " * 1003, "agnes-image-2.1-flash", False, False, False, "general", 0, "TARGET_ZONE"),
        # 3. 9000 chars -> exit 0, status TARGET_ZONE
        ("A" * 9000, "agnes-image-2.1-flash", False, False, False, "general", 0, "TARGET_ZONE"),
        # 4. 18999 chars -> exit 0, status UPPER_BAND
        ("A" * 18999, "agnes-image-2.1-flash", False, False, False, "general", 0, "UPPER_BAND"),
        # 5. Long 40K chars -> exit 0, status ABOVE_PREFERRED_MAX (warn-but-pass)
        ("A" * 40000, "agnes-image-2.1-flash", False, False, False, "general", 0, "ABOVE_PREFERRED_MAX"),
        # 6. Logo without I2I -> exit 2
        ("Company logo on billboard. " * 200, "agnes-image-2.1-flash", True, False, False, "general", 2, None),
        # 7. Style-ref missing directive -> exit 2
        ("A" * 6000, "agnes-image-2.1-flash", False, True, False, "general", 2, None),
        # 8. Style-ref with directive -> exit 0
        (f"A scene. {STYLE_REF_DIRECTIVE} " + "A" * 6000, "agnes-image-2.1-flash", False, True, False, "general", 0, "TARGET_ZONE"),
        # F32 social-planner scope:
        # 9. 8999 NFC chars -> FAIL (exit 2)
        ("A" * 8999, "agnes-image-2.1-flash", False, False, False, "social-planner", 2, None),
        # 10. 9000 NFC chars -> PASS
        ("A" * 9000, "agnes-image-2.1-flash", False, False, False, "social-planner", 0, "SOCIAL_BAND"),
        # 11. 19000 NFC chars -> PASS
        ("A" * 19000, "agnes-image-2.1-flash", False, False, False, "social-planner", 0, "SOCIAL_BAND"),
        # 12. 19001 NFC chars -> FAIL (exit 2)
        ("A" * 19001, "agnes-image-2.1-flash", False, False, False, "social-planner", 2, None),
        # 13. astral chars: 4500 emoji = 4500 code points (9000 UTF-16 units) -> FAIL on code points
        ("🦄" * 4500, "agnes-image-2.1-flash", False, False, False, "social-planner", 2, None),
    ]

    failed = 0
    for idx, (p, m, l, s, ident, scope, expected_exit, expected_status) in enumerate(fixtures, 1):
        res = evaluate_prompt(p, model=m, logo=l, style_ref=s, identity_ref=ident, scope=scope)
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
    parser.add_argument("--style-ref", action="store_true", help="Require style-reference-only directive (style-only references).")
    parser.add_argument("--identity-ref", action="store_true", help="Identity/logo reference: require the preserve-the-mark rule (F32 corrected logo rule).")
    parser.add_argument("--scope", default="general", choices=["general", "social-planner"],
                        help="general (default): legacy 5,000-floor band, warn-only. "
                             "social-planner: F32 scoped override, HARD 9,000-19,000 "
                             "NFC code points, fail-closed.")
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

    res = evaluate_prompt(prompt_text, model=args.model, logo=args.logo,
                          style_ref=args.style_ref, identity_ref=args.identity_ref,
                          scope=args.scope)
    print(json.dumps(res, indent=2))
    return res.get("exit_code", 0)


if __name__ == "__main__":
    sys.exit(main())