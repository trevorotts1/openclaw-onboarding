#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_agnes_image_prompt_floor.py -- deterministic prompt-band quality gate
for Agnes Image 2.1 Flash image prompts.

Authority: Spec §5 (Prompt Policy), §10.5 (Agnes Image), §14 (Validators).

PROMPT POLICY:
  Agnes vendor documentation does NOT publish a hard prompt character limit.
  House operating policy targets:
  - 5,000 chars: house target floor (prompts below are thin stubs; expand them).
  - 9,000 chars: house normal target.
  - 19,000 chars: house preferred max headroom.
  No hard rejection occurs on length alone because vendor cap is NOT_PUBLISHED.

IMAGE-TO-IMAGE FOR LOGOS (MANDATORY):
  When a prompt involves a client's LOGO or existing brand mark, image-to-image
  generation MUST be used (providing the logo as a reference image), NOT text-to-image.

STYLE-REFERENCE-ONLY DIRECTIVE (MANDATORY):
  When style reference images are attached, the style-reference-only directive is
  MANDATORY: "Use the attached images only as style reference for color grading,
  lighting, and composition -- do not copy their subjects, faces, or text."

USAGE:
    python3 prove_agnes_image_prompt_floor.py --self-test          # CI gate
    python3 prove_agnes_image_prompt_floor.py --file prompt.txt    # check prompt
    python3 prove_agnes_image_prompt_floor.py --file prompt.txt --logo    # logo check
    python3 prove_agnes_image_prompt_floor.py --file prompt.txt --style-ref # style ref check
    python3 prove_agnes_image_prompt_floor.py --dir <prompts_dir>  # check directory

EXIT CODES:
    0 -- all checks pass (or non-fatal band advisory)
    2 -- hard violation (logo without I2I intent, or missing style-ref directive)
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

STYLE_REF_ONLY_TOKENS = [
    "style reference only", "style-reference only", "style-reference-only",
    "only as style reference", "as style reference", "only for style reference",
    "do not copy their subjects", "do not copy their faces", "do not copy their text",
    "reference for color grading",
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def check_length(prompt_text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Check prompt length against house target bands.
    Returns (band_status, advisories).
    Length is informational/advisory because vendor cap is NOT_PUBLISHED.
    """
    stripped = prompt_text.strip()
    n = len(stripped)
    advisories = []
    if not stripped:
        return "EMPTY", [("AF-AGNES-PROMPT-EMPTY", "prompt is empty / whitespace-only.")]

    if n < HOUSE_MIN_CHARS:
        band_status = "THIN_STUB"
        advisories.append((
            "AF-AGNES-PROMPT-THIN-STUB",
            f"prompt is {n} chars, below house target floor ({HOUSE_MIN_CHARS} chars). "
            "Short user prompt is not an error; expand it to production depth."
        ))
    elif n <= HOUSE_TARGET_CHARS:
        band_status = "TARGET_ZONE"
    elif n <= HOUSE_MAX_CHARS:
        band_status = "UPPER_BAND"
    else:
        band_status = "ABOVE_PREFERRED_MAX"
        advisories.append((
            "AF-AGNES-PROMPT-ABOVE-PREFERRED-MAX",
            f"prompt is {n} chars, above house preferred max ({HOUSE_MAX_CHARS} chars). "
            "Vendor cap is NOT_PUBLISHED; allowed if deliberate."
        ))

    return band_status, advisories


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
        problems.append((
            "AF-AGNES-LOGO-NOT-I2I",
            "prompt references a logo / brand image but does NOT declare image-to-image intent. "
            "When a prompt involves the client's logo or existing brand image, use "
            "IMAGE-TO-IMAGE generation (provide the logo as reference image via extra_body.image), "
            "NOT text-to-image."
        ))
    return problems


def check_style_ref_directive(prompt_text: str, style_ref_attached: bool) -> List[Tuple[str, str]]:
    """Check: if style reference images are attached, the style-reference-only
    directive MUST be present."""
    problems = []
    if not style_ref_attached:
        return problems
    text_lc = _norm(prompt_text)
    if not any(tok in text_lc for tok in STYLE_REF_ONLY_TOKENS):
        problems.append((
            "AF-AGNES-STYLE-REF-DIRECTIVE",
            "style reference images attached but the style-reference-only directive is ABSENT. "
            f"Add verbatim: '{STYLE_REF_DIRECTIVE}'"
        ))
    return problems


def gate_prompt(prompt_text: str, logo_check: bool = False,
                style_ref: bool = False) -> Tuple[bool, str, List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Run all applicable gates.
    Returns (is_valid, band_status, hard_violations, advisories).
    """
    hard_violations = []
    advisories = []

    band_status, len_advisories = check_length(prompt_text)
    if band_status == "EMPTY":
        hard_violations.extend(len_advisories)
    else:
        advisories.extend(len_advisories)

    if logo_check:
        hard_violations.extend(check_logo_i2i(prompt_text))
    if style_ref:
        hard_violations.extend(check_style_ref_directive(prompt_text, style_ref))

    is_valid = len(hard_violations) == 0
    return is_valid, band_status, hard_violations, advisories


# ---------------------------------------------------------------------------
# Self-test fixtures (CI gate)
# ---------------------------------------------------------------------------

def _rich_prompt(n_sentences: int = 40, with_style_ref: bool = True) -> str:
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
        base += f"{STYLE_REF_DIRECTIVE}\n"
    return base + " ".join(out)


def _self_test() -> int:
    failures: List[str] = []

    # --- LENGTH ADVISORY TESTS (Non-fatal) ---
    ok = _rich_prompt(40)
    passed, band, hard, adv = gate_prompt(ok)
    if not passed or band not in {"TARGET_ZONE", "UPPER_BAND"}:
        failures.append(f"[rich-pass] expected PASS in target band, got: {band}, hard={hard}")

    short = "A short prompt about a desk scene."
    passed, band, hard, adv = gate_prompt(short)
    if not passed or band != "THIN_STUB":
        failures.append(f"[under-floor] expected PASS with THIN_STUB status, got passed={passed}, band={band}")

    over = _rich_prompt(250)
    passed, band, hard, adv = gate_prompt(over)
    if not passed or band != "ABOVE_PREFERRED_MAX":
        failures.append(f"[over-ceiling] expected PASS with ABOVE_PREFERRED_MAX status, got passed={passed}, band={band}")

    passed, band, hard, adv = gate_prompt("   \n  \t ")
    if passed:
        failures.append("[empty] expected FAIL on empty prompt")

    # --- LOGO-TO-I2I TESTS ---
    body_no_sr = _rich_prompt(40, with_style_ref=False)
    logo_no_i2i = body_no_sr + "\nPlace the company logo in the top right corner."
    passed, band, hard, adv = gate_prompt(logo_no_i2i, logo_check=True)
    if passed:
        failures.append("[logo-no-i2i] expected FAIL but got PASS")

    logo_with_i2i = (
        body_no_sr +
        "\nUse image-to-image generation with the attached logo as a reference image via extra_body.image. "
        "Render the logo using the provided brand mark as a reference."
    )
    passed, band, hard, adv = gate_prompt(logo_with_i2i, logo_check=True)
    if not passed:
        failures.append(f"[logo-with-i2i] expected PASS but got: {hard}")

    passed, band, hard, adv = gate_prompt(body_no_sr, logo_check=True)
    if not passed:
        failures.append(f"[no-logo-ref] expected PASS but got: {hard}")

    # --- STYLE-REF-DIRECTIVE TESTS ---
    passed, band, hard, adv = gate_prompt(_rich_prompt(40, with_style_ref=True), style_ref=True)
    if not passed:
        failures.append(f"[style-ref-ok] expected PASS but got: {hard}")

    passed, band, hard, adv = gate_prompt(_rich_prompt(40, with_style_ref=False), style_ref=True)
    if passed:
        failures.append("[style-ref-missing] expected FAIL but got PASS")

    passed, band, hard, adv = gate_prompt(_rich_prompt(40, with_style_ref=False), style_ref=False)
    if not passed:
        failures.append(f"[style-ref-na] expected PASS but got: {hard}")

    if failures:
        print("\nSELF-TEST FAILURES:", file=sys.stderr)
        for f in failures:
            print("  - " + f, file=sys.stderr)
        return EXIT_VIOLATION
    print("prove_agnes_image_prompt_floor --self-test: ALL FIXTURES BEHAVED AS EXPECTED")
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
        passed, band_status, hard_violations, advisories = gate_prompt(
            text, logo_check=logo_check, style_ref=style_ref
        )
        if not passed:
            any_violation = True
            print(f"VIOLATION {p} ({n} stripped chars, status {band_status}):", file=sys.stderr)
            for code, msg in hard_violations:
                print(f"  - {code}: {msg}", file=sys.stderr)
        else:
            msg = f"OK {p} ({n} chars) -- status {band_status}"
            if logo_check:
                msg += " + logo/I2I PASS"
            if style_ref:
                msg += " + style-ref directive PASS"
            print(msg)
            for code, adv in advisories:
                print(f"  [advisory] {code}: {adv}")
    if checked == 0:
        print("FAIL-CLOSED: no prompt files to check", file=sys.stderr)
        return EXIT_FAILCLOSED
    return EXIT_VIOLATION if any_violation else EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Prove Agnes Image prompt policy and quality gates "
                    "(band status + logo-I2I rule + style-ref directive).")
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
