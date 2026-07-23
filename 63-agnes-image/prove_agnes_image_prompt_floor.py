#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_agnes_image_prompt_floor.py -- deterministic prompt-band enforcement gate
for GPT-image-2 and Agnes Image 2.1 Flash image prompts.

THE RULE (decision GK-D2, extended to Agnes via skill 63/64):
  For image prompts generated for GPT-image-2 OR Agnes Image 2.1 Flash:
  NEVER BELOW 5,000 characters AND NEVER ABOVE 19,000 characters.
  Valid range: 5,000-19,000.
  Max API capacity is 25,000; 19,000 gives ~6,000 chars headroom.
  5,000 is the HARD FLOOR -- a prompt below 5,000 is a thin stub, NOT submitted.

IMAGE-TO-IMAGE FOR LOGOS: When a prompt involves the client's LOGO or existing
brand image, use IMAGE-TO-IMAGE generation (provide the logo as reference image),
NOT text-to-image. This gate flags a prompt that references a logo without
declaring image-to-image intent.

DIRECTIVE: Style-reference-only directive is MANDATORY whenever reference images
are attached for style (MODEL-SPECS section 4). This gate checks for it.

USAGE
    python3 prove_agnes_image_prompt_floor.py --self-test          # CI gate
    python3 prove_agnes_image_prompt_floor.py --file prompt.txt    # gate one prompt
    python3 prove_agnes_image_prompt_floor.py --file prompt.txt --logo --i2i  # logo+I2I check
    python3 prove_agnes_image_prompt_floor.py --dir <prompts_dir>  # gate a directory

EXIT CODES
    0 -- all checks pass
    2 -- one or more prompts violate the band gate
    3 -- fail-closed (usage error, unreadable file)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

# The SACRED band: 5,000-19,000 stripped characters.
AGNES_PROMPT_FLOOR = 5000
AGNES_PROMPT_CEILING = 19000
# Full API capacity (GPT-image-2 / Agnes): 25,000 chars.
AGNES_API_CAP = 25000

# Logo-related tokens -- a prompt containing any of these + NOT declaring I2I intent
# is a violation of the "image-to-image for logos" rule.
LOGO_TOKENS = [
    "logo", "logomark", "wordmark", "brand mark", "brandmark",
    "monogram", "tagline lockup", "lockup",
    "brand icon", "brand image", "existing brand",
    "client's logo", "company logo",
]

# Image-to-image intent tokens -- must be present when LOGO_TOKENS match.
I2I_INTENT_TOKENS = [
    "image-to-image", "img2img", "i2i",
    "extra_body.image", "input_urls", "image_input",
    "reference image", "reference the logo", "logo as reference",
    "use the attached", "style reference", "reference for",
    "provided logo", "attached logo", "supplied logo",
]

# Style-reference-only directive tokens (MANDATORY when refs attached for style).
STYLE_REF_ONLY_TOKENS = [
    "style reference only", "style-reference only", "style-reference-only",
    "only as style reference", "as style reference", "only for style reference",
    "do not copy their subjects", "do not copy their faces", "do not copy their text",
    "reference for color grading",
]

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'\-]+")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def check_length(prompt_text: str) -> List[Tuple[str, str]]:
    """Check prompt length against the 5,000-19,000 band."""
    stripped = prompt_text.strip()
    n = len(stripped)
    problems = []
    if not stripped:
        problems.append(("AF-AGNES-PROMPT-EMPTY",
                         "prompt is empty / whitespace-only -- NOT submitted."))
        return problems
    if n < AGNES_PROMPT_FLOOR:
        problems.append(("AF-AGNES-PROMPT-FLOOR",
                         f"prompt is {n} chars, UNDER the 5,000-char FLOOR. "
                         f"Too short for GPT-image-2 / Agnes Image -- a prompt "
                         f"below 5,000 chars is a thin stub, NOT submitted, "
                         f"NOT rendered. Re-author."))
    if n > AGNES_PROMPT_CEILING:
        problems.append(("AF-AGNES-PROMPT-CEILING",
                         f"prompt is {n} chars, OVER the 19,000-char MAX. "
                         f"The API accepts up to {AGNES_API_CAP}; the 19,000 cap "
                         f"preserves ~6,000 chars headroom. Trim and re-author."))
    return problems


def check_logo_i2i(prompt_text: str) -> List[Tuple[str, str]]:
    """Check: if the prompt references a logo/brand image, it MUST declare
    image-to-image intent."""
    text_lc = _norm(prompt_text)
    problems = []
    logo_hit = any(tok in text_lc for tok in LOGO_TOKENS)
    if not logo_hit:
        return problems
    i2i_hit = any(tok in text_lc for tok in I2I_INTENT_TOKENS)
    if not i2i_hit:
        problems.append(("AF-AGNES-LOGO-NOT-I2I",
                         "prompt references a logo / brand image but does NOT "
                         "declare image-to-image intent. When a prompt involves "
                         "the client's logo or existing brand image, use "
                         "IMAGE-TO-IMAGE generation (provide the logo as a "
                         "reference image via extra_body.image / input_urls), "
                         "NOT text-to-image."))
    return problems


def check_style_ref_directive(prompt_text: str, style_ref_attached: bool) -> List[Tuple[str, str]]:
    """Check: if style reference images are attached, the style-reference-only
    directive MUST be present (MODEL-SPECS section 4)."""
    problems = []
    if not style_ref_attached:
        return problems
    text_lc = _norm(prompt_text)
    if not any(tok in text_lc for tok in STYLE_REF_ONLY_TOKENS):
        problems.append(("AF-AGNES-STYLE-REF-DIRECTIVE",
                         "style reference images attached but the style-reference-only "
                         "directive is ABSENT (MODEL-SPECS section 4, MANDATORY for "
                         "GPT-Image 2 I2I / Agnes I2I). Add: 'Use the attached images "
                         "only as style reference for color grading, lighting, and "
                         "composition -- do not copy their subjects, faces, or text.'"))
    return problems


def gate_prompt(prompt_text: str, logo_check: bool = False,
                style_ref: bool = False) -> Tuple[bool, List[Tuple[str, str]]]:
    """Run all applicable gates. Returns (passed, list_of_problems)."""
    all_problems = []
    all_problems.extend(check_length(prompt_text))
    if logo_check:
        all_problems.extend(check_logo_i2i(prompt_text))
    if style_ref:
        all_problems.extend(check_style_ref_directive(prompt_text, style_ref))
    return len(all_problems) == 0, all_problems


# ---------------------------------------------------------------------------
# Self-test fixtures (CI gate)
# ---------------------------------------------------------------------------

def _rich_prompt(n_sentences: int = 40, with_style_ref: bool = True) -> str:
    """Build a prompt guaranteed to be >= 5,000 chars with distinct content.
    When with_style_ref=False, the style-reference directive is omitted (to test
    the logo-I2I gate without tripping on I2I tokens from the directive)."""
    vocab = (
        "photoreal cinematic boardroom dusk amber rim-light glass reflection "
        "confident founder tailored charcoal poised gesture layered depth bokeh "
        "shallow aperture volumetric haze directional key soft fill practical "
        "sconces warm tungsten cool teal contrast graded editorial magazine "
        "luminous shadows crushed inky highlights specular skyline window "
        "twilight metropolitan architectural leading lines negative space "
        "typographic hierarchy kerning tracking baseline ligature counters "
        "serif humanist geometric grotesque palette saturation vibrance "
        "clarity texture grain filmic anamorphic flare gradient duotone "
        "isometric vignette parallax silhouette chromatic aberration halftone"
    ).split()
    out = []
    for i in range(n_sentences):
        w = vocab[i % len(vocab)]
        out.append(
            f"Detail {i}: the {w} element is described with a distinct clause "
            f"number {i} carrying its own descriptive nuance about lighting "
            f"palette placement mood and surface fitness so the prompt reads "
            f"rich and specific throughout production stage {i}."
        )
    base = (
        "SCENE: A professional in a modern office at golden hour, cinematic "
        "lighting with warm amber tones, shallow depth of field, brand palette "
        "anchored on navy #0A2540 with a warm gold accent #F2B134.\n"
    )
    if with_style_ref:
        base += (
            "Use the attached images only as style reference for color grading, "
            "lighting, and composition -- do not copy their subjects, faces, or text.\n"
        )
    return base + " ".join(out)


def _self_test() -> int:
    failures: List[str] = []

    # --- LENGTH TESTS ---
    ok = _rich_prompt(40)
    passed, probs = gate_prompt(ok)
    if not passed:
        failures.append(f"[rich-pass] expected PASS but got: {probs}")

    short = "A short prompt about a desk scene."
    passed, probs = gate_prompt(short)
    if passed:
        failures.append("[under-floor] expected FAIL but got PASS")

    over = _rich_prompt(250)
    passed, probs = gate_prompt(over)
    if passed:
        failures.append("[over-ceiling] expected FAIL but got PASS")

    passed, probs = gate_prompt("   \n  \t ")
    if passed:
        failures.append("[empty] expected FAIL but got PASS")

    # --- LOGO-TO-I2I TESTS ---
    # Logo reference WITHOUT I2I intent -> should fail.
    # Use with_style_ref=False so the style-ref sentence does not
    # accidentally match I2I_INTENT_TOKENS.
    body_no_sr = _rich_prompt(40, with_style_ref=False)
    logo_no_i2i = body_no_sr + "\nPlace the company logo in the top right corner."
    passed, probs = gate_prompt(logo_no_i2i, logo_check=True)
    if passed:
        failures.append("[logo-no-i2i] expected FAIL but got PASS")

    # Logo reference WITH I2I intent -> should pass.
    logo_with_i2i = (body_no_sr +
                     "\nUse image-to-image generation with the attached logo as "
                     "a reference image via extra_body.image. Render the logo "
                     "using the provided brand mark as a reference.")
    passed, probs = gate_prompt(logo_with_i2i, logo_check=True)
    if not passed:
        failures.append(f"[logo-with-i2i] expected PASS but got: {probs}")

    # No logo reference, logo check enabled -> should pass.
    passed, probs = gate_prompt(body_no_sr, logo_check=True)
    if not passed:
        failures.append(f"[no-logo-ref] expected PASS but got: {probs}")

    # --- STYLE-REF-DIRECTIVE TESTS ---
    # Prompt WITH style-ref directive, style_ref=True -> should pass.
    passed, probs = gate_prompt(_rich_prompt(40, with_style_ref=True), style_ref=True)
    if not passed:
        failures.append(f"[style-ref-ok] expected PASS but got: {probs}")

    # Prompt WITHOUT style-ref directive, style_ref=True -> should fail.
    passed, probs = gate_prompt(_rich_prompt(40, with_style_ref=False),
                                style_ref=True)
    if passed:
        failures.append("[style-ref-missing] expected FAIL but got PASS")

    # Prompt WITHOUT style-ref directive, style_ref=False -> should pass.
    passed, probs = gate_prompt(_rich_prompt(40, with_style_ref=False),
                                style_ref=False)
    if not passed:
        failures.append(f"[style-ref-na] expected PASS but got: {probs}")

    if failures:
        print("\nSELF-TEST FAILURES:", file=sys.stderr)
        for f in failures:
            print("  - " + f, file=sys.stderr)
        return EXIT_VIOLATION
    print("\nprove_agnes_image_prompt_floor --self-test: ALL FIXTURES BEHAVED AS EXPECTED")
    return EXIT_OK


def _gate_files(paths: List[Path], logo_check: bool = False,
                style_ref: bool = False) -> int:
    any_violation = False
    checked = 0
    for p in paths:
        try:
            text = p.read_text(errors="replace")
        except OSError as exc:
            print(f"FAIL-CLOSED: cannot read {p}: {exc}", file=sys.stderr)
            return EXIT_FAILCLOSED
        checked += 1
        n = len(text.strip())
        passed, problems = gate_prompt(text, logo_check=logo_check,
                                       style_ref=style_ref)
        if not passed:
            any_violation = True
            print(f"VIOLATION {p} ({n} stripped chars):", file=sys.stderr)
            for code, msg in problems:
                print(f"  - {code}: {msg}", file=sys.stderr)
        else:
            msg = f"OK {p} ({n} chars) -- within 5,000-19,000 band"
            if logo_check:
                msg += " + logo/I2I PASS"
            if style_ref:
                msg += " + style-ref directive PASS"
            print(msg)
    if checked == 0:
        print("FAIL-CLOSED: no prompt files to check", file=sys.stderr)
        return EXIT_FAILCLOSED
    return EXIT_VIOLATION if any_violation else EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Prove the Agnes/GPT-image-2 prompt-band enforcement gate "
                    "(5,000-19,000 chars + logo-I2I rule + style-ref directive).")
    ap.add_argument("--self-test", action="store_true",
                    help="run the fixture gate (CI)")
    ap.add_argument("--file", action="append", default=[],
                    help="prompt file(s) to gate (repeatable)")
    ap.add_argument("--dir", help="gate every .txt under this directory")
    ap.add_argument("--logo", action="store_true",
                    help="enable logo -> image-to-image enforcement gate")
    ap.add_argument("--style-ref", action="store_true",
                    help="require the style-reference-only directive")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    paths: List[Path] = []
    if args.dir:
        d = Path(args.dir)
        if not d.is_dir():
            print(f"FAIL-CLOSED: {d} is not a directory", file=sys.stderr)
            return EXIT_FAILCLOSED
        paths.extend(sorted(d.glob("*.txt")))
    for f in args.file:
        p = Path(f)
        if not p.is_file():
            print(f"FAIL-CLOSED: {p} is not a file", file=sys.stderr)
            return EXIT_FAILCLOSED
        paths.append(p)

    if not paths:
        ap.print_usage(sys.stderr)
        print("FAIL-CLOSED: pass --self-test, --file <path>, or --dir <dir>",
              file=sys.stderr)
        return EXIT_FAILCLOSED

    return _gate_files(paths, logo_check=args.logo, style_ref=args.style_ref)


if __name__ == "__main__":
    raise SystemExit(main())
