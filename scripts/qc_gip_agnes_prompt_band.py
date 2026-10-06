#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qc_gip_agnes_prompt_band.py -- QC gate that checks image-prompt length against KIE
prompt rule 12 (owner order 2026-10-05) for GPT-image-2.5 and Agnes Image prompts.

This is a unified pre-commit / CI gate covering both scopes:
  1. Graphics department GIP prompts (GPT-image-2.5 T2I/I2I)
  2. Agnes skills 63/64 prompts (Agnes Image 2.1 Flash)

THE RULE (rule 12, 07-kie-setup/references/kie-common-rules.md):
  A descriptive image prompt is 95 to 100 percent of the model's maxLength, hard floor
  80 percent (rejected below), hard ceiling 100 percent (rejected above). The numbers are
  NOT kept here: this gate calls the shared enforcer shared-utils/kie_prompt_enforcer.py,
  which wraps `kie_live_adapter.py prompt-budget --check` (live schema, registry fallback).
  The rejection message names the exact characters to add or cut. A model with no known
  limit (Agnes is not a KIE model) is reported UNKNOWN and has no floor.

IMAGE-TO-IMAGE FOR LOGOS: When a prompt involves the client's LOGO or existing
brand image, use IMAGE-TO-IMAGE generation (provide the logo as reference image),
NOT text-to-image.

USAGE
    python3 scripts/qc_gip_agnes_prompt_band.py --self-test          # CI gate
    python3 scripts/qc_gip_agnes_prompt_band.py --file prompt.txt    # gate one prompt
    python3 scripts/qc_gip_agnes_prompt_band.py --file prompt.txt --logo  # logo+I2I check
    python3 scripts/qc_gip_agnes_prompt_band.py --file prompt.txt --style-ref  # style-ref check
    python3 scripts/qc_gip_agnes_prompt_band.py --dir <prompts_dir>  # gate a directory
    python3 scripts/qc_gip_agnes_prompt_band.py --file prompt.txt --json  # machine-readable output
    python3 scripts/qc_gip_agnes_prompt_band.py --file prompt.txt --model <KIE model id>  # default: the pinned GPT Image 2.5 text-to-image id

EXIT CODES
    0 -- all checks pass
    2 -- one or more prompts violate the band gate
    3 -- fail-closed (usage error, unreadable file)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _load_enforcer():
    """Find shared-utils/kie_prompt_enforcer.py (repo checkout or installed skills tree) and import it."""
    envd = os.environ.get("OPENCLAW_SKILLS_DIR")
    dirs = [p / "shared-utils" for p in Path(__file__).resolve().parents]
    dirs += ([Path(envd) / "shared-utils"] if envd else []) + [
        Path.home() / ".openclaw" / "skills" / "shared-utils", Path("/data/.openclaw/skills/shared-utils")]
    for d in dirs:
        if (d / "kie_prompt_enforcer.py").is_file():
            sys.path.insert(0, str(d))
            import kie_prompt_enforcer
            return kie_prompt_enforcer
    raise ImportError("shared-utils/kie_prompt_enforcer.py not found; install or update the onboarding skills")


KPE = _load_enforcer()

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

# The length band is not defined here: it is KIE prompt rule 12, enforced by the shared
# enforcer (limits from Skill 74 prompt-budget). Only the default model id is named.
DEFAULT_MODEL = "gpt-image-2-5-sunburst-text-to-image"

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


_CODES = {"BELOW_FLOOR": "AF-QC-PROMPT-FLOOR", "ABOVE_MAX": "AF-QC-PROMPT-CEILING",
          "ADAPTER_UNAVAILABLE": "AF-QC-PROMPT-BUDGET-UNAVAILABLE"}


def check_length(prompt_text: str, model: str = DEFAULT_MODEL) -> List[Tuple[str, str]]:
    """Check prompt length against rule 12 through the shared enforcer."""
    if not prompt_text.strip():
        return [("AF-QC-PROMPT-EMPTY", "prompt is empty / whitespace-only -- NOT submitted.")]
    v = KPE.check(model, prompt_text)
    return [] if v["ok"] else [(_CODES.get(v["status"], "AF-QC-PROMPT-BAND"), v["message"] + " -- NOT submitted.")]


def check_logo_i2i(prompt_text: str) -> List[Tuple[str, str]]:
    """Check: if the prompt references a logo/brand image, it MUST declare
    image-to-image intent."""
    text_lc = _norm(prompt_text)
    problems: List[Tuple[str, str]] = []
    logo_hit = any(tok in text_lc for tok in LOGO_TOKENS)
    if not logo_hit:
        return problems
    i2i_hit = any(tok in text_lc for tok in I2I_INTENT_TOKENS)
    if not i2i_hit:
        problems.append(("AF-QC-LOGO-NOT-I2I",
                         "prompt references a logo / brand image but does NOT "
                         "declare image-to-image intent. When a prompt involves "
                         "the client's logo or existing brand image, use "
                         "IMAGE-TO-IMAGE generation (provide the logo as a "
                         "reference image via extra_body.image / input_urls), "
                         "NOT text-to-image. A text-to-image model cannot render "
                         "a specific client's logo accurately and will invent a "
                         "lookalike instead."))
    return problems


def check_style_ref_directive(prompt_text: str,
                               style_ref_attached: bool) -> List[Tuple[str, str]]:
    """Check: if style reference images are attached, the style-reference-only
    directive MUST be present (MODEL-SPECS section 4)."""
    problems: List[Tuple[str, str]] = []
    if not style_ref_attached:
        return problems
    text_lc = _norm(prompt_text)
    if not any(tok in text_lc for tok in STYLE_REF_ONLY_TOKENS):
        problems.append(("AF-QC-STYLE-REF-DIRECTIVE",
                         "style reference images attached but the style-reference-only "
                         "directive is ABSENT (MODEL-SPECS section 4, MANDATORY for "
                         "GPT-Image 2.5 I2I / Agnes I2I). Add: 'Use the attached images "
                         "only as style reference for color grading, lighting, and "
                         "composition -- do not copy their subjects, faces, or text.'"))
    return problems


def gate_prompt(prompt_text: str, logo_check: bool = False,
                style_ref: bool = False, model: str = DEFAULT_MODEL) -> Tuple[bool, List[Tuple[str, str]]]:
    """Run all applicable gates. Returns (passed, list_of_problems)."""
    all_problems: List[Tuple[str, str]] = []
    all_problems.extend(check_length(prompt_text, model))
    if logo_check:
        all_problems.extend(check_logo_i2i(prompt_text))
    if style_ref:
        all_problems.extend(check_style_ref_directive(prompt_text, style_ref))
    return len(all_problems) == 0, all_problems


def _to_dict(problems: List[Tuple[str, str]], n_chars: int,
             passed: bool, filepath: str = "", model: str = DEFAULT_MODEL) -> Dict[str, Any]:
    """Convert gate results to a JSON-serializable dict."""
    return {
        "file": filepath,
        "chars": n_chars,
        "model": model,
        "band": "rule 12: 95-100 percent of the model maxLength, floor 80 percent (shared enforcer)",
        "passed": passed,
        "violations": [{"code": code, "message": msg} for code, msg in problems],
    }


# ---------------------------------------------------------------------------
# Self-test fixtures (CI gate)
# ---------------------------------------------------------------------------

def _rich_prompt(chars: int = 19500, with_style_ref: bool = True) -> str:
    """Build a prompt of exactly `chars` stripped characters with distinct content."""
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
    for i in range(chars // 150 + 1):  # more than enough sentences; the result is trimmed to size
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
    return (base + " ".join(out))[:chars].strip().ljust(chars, ".")


def _self_test() -> int:
    failures: List[str] = []
    mx = 20000  # GPT Image 2.5 maxLength per Skill 74 prompt-budget; the fixtures are percentages of it

    def expect(name: str, chars: int, want_pass: bool, **kw) -> None:
        passed, probs = gate_prompt(_rich_prompt(chars, kw.pop("style", True)), **kw)
        if passed != want_pass:
            failures.append(f"[{name}] expected {'PASS' if want_pass else 'FAIL'} at {chars} chars but got: {probs}")

    # --- LENGTH TESTS (rule 12): 79 percent rejected, 95 and 100 percent pass, 101 percent rejected ---
    expect("79-percent", mx * 79 // 100, False)
    expect("95-percent", mx * 95 // 100, True)
    expect("100-percent", mx, True)
    expect("101-percent", mx * 101 // 100, False)
    _, probs = gate_prompt(_rich_prompt(mx * 79 // 100))
    if not any("ADD at least 200" in m for _, m in probs):
        failures.append(f"[79-percent-message] must name the exact chars to add (200): {probs}")
    _, probs = gate_prompt(_rich_prompt(mx * 101 // 100))
    if not any("CUT exactly 200" in m for _, m in probs):
        failures.append(f"[101-percent-message] must name the exact chars to cut (200): {probs}")
    passed, probs = gate_prompt("A short prompt about a desk scene.")
    if passed:
        failures.append("[under-floor] expected FAIL but got PASS")
    passed, probs = gate_prompt("   \n  \t ")
    if passed:
        failures.append("[empty] expected FAIL but got PASS")

    # --- LOGO-TO-I2I TESTS ---
    body_no_sr = _rich_prompt(mx * 95 // 100 - 200, with_style_ref=False)
    logo_no_i2i = body_no_sr + "\nPlace the company logo in the top right corner."
    passed, probs = gate_prompt(logo_no_i2i, logo_check=True)
    if passed:
        failures.append("[logo-no-i2i] expected FAIL but got PASS")

    logo_with_i2i = (body_no_sr +
                     "\nUse image-to-image generation with the attached logo as "
                     "a reference image via extra_body.image. Render the logo "
                     "using the provided brand mark as a reference.")
    logo_with_i2i += "." * (mx * 95 // 100 - len(logo_with_i2i.strip()))
    passed, probs = gate_prompt(logo_with_i2i, logo_check=True)
    if not passed:
        failures.append(f"[logo-with-i2i] expected PASS but got: {probs}")

    # --- STYLE-REF-DIRECTIVE TESTS ---
    passed, probs = gate_prompt(_rich_prompt(mx * 95 // 100, with_style_ref=True), style_ref=True)
    if not passed:
        failures.append(f"[style-ref-ok] expected PASS but got: {probs}")

    passed, probs = gate_prompt(_rich_prompt(mx * 95 // 100, with_style_ref=False), style_ref=True)
    if passed:
        failures.append("[style-ref-missing] expected FAIL but got PASS")

    if failures:
        print("\nSELF-TEST FAILURES:", file=sys.stderr)
        for f in failures:
            print("  - " + f, file=sys.stderr)
        return EXIT_VIOLATION
    print("\nqc_gip_agnes_prompt_band --self-test: ALL FIXTURES PASS")
    return EXIT_OK


def _gate_files(paths: List[Path], logo_check: bool = False,
                style_ref: bool = False, as_json: bool = False, model: str = DEFAULT_MODEL) -> int:
    any_violation = False
    checked = 0
    results: List[Dict[str, Any]] = []
    for p in paths:
        try:
            text = p.read_text(errors="replace")
        except OSError as exc:
            msg = f"FAIL-CLOSED: cannot read {p}: {exc}"
            if as_json:
                print(json.dumps({"error": msg}))
            else:
                print(msg, file=sys.stderr)
            return EXIT_FAILCLOSED
        checked += 1
        n = len(text.strip())
        passed, problems = gate_prompt(text, logo_check=logo_check,
                                       style_ref=style_ref, model=model)
        if not passed:
            any_violation = True
        if as_json:
            results.append(_to_dict(problems, n, passed, str(p), model))
        else:
            if not passed:
                print(f"VIOLATION {p} ({n} stripped chars):", file=sys.stderr)
                for code, msg in problems:
                    print(f"  - {code}: {msg}", file=sys.stderr)
            else:
                msg = f"OK {p} ({n} chars) -- within the rule 12 band for {model}"
                if logo_check:
                    msg += " + logo/I2I PASS"
                if style_ref:
                    msg += " + style-ref directive PASS"
                print(msg)
    if checked == 0:
        msg = "FAIL-CLOSED: no prompt files to check"
        if as_json:
            print(json.dumps({"error": msg}))
        else:
            print(msg, file=sys.stderr)
        return EXIT_FAILCLOSED
    if as_json:
        summary = {
            "checked": checked,
            "passed": sum(1 for r in results if r["passed"]),
            "failed": sum(1 for r in results if not r["passed"]),
            "model": model,
            "results": results,
        }
        print(json.dumps(summary, indent=2))
    return EXIT_VIOLATION if any_violation else EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="QC gate: enforce KIE prompt rule 12 (95-100 percent of the model max, "
                    "floor 80 percent) for GPT-image-2.5 and Agnes Image prompts, plus logo "
                    "image-to-image rule and style-reference-only directive.")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="KIE model id whose maxLength sets the band (default: %(default)s)")
    ap.add_argument("--self-test", action="store_true",
                    help="run the fixture gate (CI)")
    ap.add_argument("--file", action="append", default=[],
                    help="prompt file(s) to gate (repeatable)")
    ap.add_argument("--dir", help="gate every .txt under this directory")
    ap.add_argument("--logo", action="store_true",
                    help="enable logo -> image-to-image enforcement gate")
    ap.add_argument("--style-ref", action="store_true",
                    help="require the style-reference-only directive")
    ap.add_argument("--json", dest="as_json", action="store_true",
                    help="emit machine-readable JSON output")
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

    return _gate_files(paths, logo_check=args.logo, style_ref=args.style_ref,
                       as_json=args.as_json, model=args.model)


if __name__ == "__main__":
    raise SystemExit(main())
