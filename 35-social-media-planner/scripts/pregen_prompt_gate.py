#!/usr/bin/env python3
"""
pregen_prompt_gate.py — Skill 35 (social-media-planner) PRE-GENERATION prompt QC gate.

P3-05 root cause: Skill 35's ONLY prompt-level check was one generic post-generation
checklist line ("Image prompt is appropriate for the client's brand and target audience"),
evaluated AFTER a paid kie.ai call had already run. There was no PRE-generation gate, no
memory of why a prompt failed, and — because every Skill 35 deliverable carries a baked
text/headline overlay (playbook.md Section 18) while the model table (Section 8) only ever
named Nano Banana 2/Pro (not a text-rendering specialist) — the spelling-error retry loop
was blind to its own root cause (wrong model for the content type).

This module is the STOP-BEFORE-YOU-SPEND gate: it checks the ASSEMBLED PROMPT + its
declared metadata BEFORE any generation call, mirroring the Graphics department's
`diu_validator.py prompt-band` fail-closed shape exactly (same exit-code discipline, same
"a failed check is a hard stop, never a suggestion" posture):

  0 — every check clears. The prompt may be submitted for generation.
  2 — usage error (bad/missing CLI args, unreadable file). Fail-closed, never skip.
  3 — FORM failure (AF-SM-PROMPT-FORM): a required structural field is absent — ratio/pixel
      spec, brand colors, a merged avoid-list, the verbatim on-image copy (Section 18), or
      the mandatory brand-safety clause (playbook.md line ~1721). A prompt this thin is a
      stub, not a real prompt — it is NOT submitted, NOT generated.
  6 — QUALITY/ROUTING failure (AF-SM-MODEL-ROUTING / AF-SM-INPUT-QC-GATE): the prompt is
      structurally complete but (a) a text-overlay image is routed to a non-text-rendering
      model (Nano Banana 2/Pro) instead of Ideogram V3 DESIGN (playbook.md Section 8), or
      (b) a graphics-department-sourced asset has no SOP-GIP-02 QC receipt scoring >= 8.5.

USAGE
    python3 pregen_prompt_gate.py check \\
        --prompt-file working/prompts/day1-primary.txt \\
        --model ideogram-v3-design \\
        --platform instagram --ratio 4:5 --pixels 1080x1350 \\
        --text-overlay "Three Moves That Doubled Our Pipeline" \\
        --brand-colors "#0B3D2E,#F5EFE0,#C9A24B" \\
        --avoid-list-file working/compiled-negatives.txt

    # Graphics-department-sourced asset (input-quality gate, step 4i):
    python3 pregen_prompt_gate.py check ... --asset-source graphics-department \\
        --qc-receipt-file <job>/qc/image_qc_report.json

This module is STDLIB ONLY (no third-party deps), matching the fleet's Graphics/
Presentations gate scripts.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_FORM = 3
EXIT_QUALITY = 6

# Every ratio Skill 35 actually produces (playbook.md Section 7/8/9). A prompt declaring a
# ratio outside this set is a FORM failure — it does not match any real deliverable slot.
KNOWN_RATIOS = {"4:5", "2:3", "9:16", "16:9", "1:1"}

# Text-rendering-capable models (playbook.md Section 8 fix — routes every text-overlay
# deliverable to Ideogram V3 DESIGN per Skill 45's own documented routing rule,
# 45-design-intelligence-library/library/social-media-designs/_RULES.md).
TEXT_CAPABLE_MODELS = {"ideogram-v3-design", "ideogram/v3-text-to-image", "ideogram-v3"}
# Models that are explicitly NOT text-rendering specialists (playbook.md Section 8: PRIMARY /
# BACKUP for everything BEFORE this fix — now reserved for non-text imagery only).
NON_TEXT_MODELS = {"nano-banana-2", "nano-banana-pro"}

# The mandatory brand-safety clause, verbatim from playbook.md Section 18 rule 5. Matched
# case-insensitively; the three concepts must all be present (exact wording may vary slightly
# per client SOUL.md customization, but the three concepts are non-negotiable).
_BRAND_SAFETY_MARKERS = ("brand-appropriate", "no suggestive content")

_QC_RECEIPT_SCORE_KEYS = ("average", "score", "avg_score", "qc_score")
QC_RECEIPT_FLOOR = 8.5


class GateResult:
    def __init__(self) -> None:
        self.form_problems: list[str] = []
        self.quality_problems: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.form_problems and not self.quality_problems

    @property
    def exit_code(self) -> int:
        if self.form_problems:
            return EXIT_FORM
        if self.quality_problems:
            return EXIT_QUALITY
        return EXIT_OK


def _norm_ws(s: str) -> str:
    return " ".join(s.split())


def check_prompt(
    prompt_text: str,
    *,
    model: str,
    ratio: Optional[str],
    pixels: Optional[str],
    platform: Optional[str],
    text_overlay: Optional[str],
    brand_colors: Optional[str],
    avoid_list_text: Optional[str],
    asset_source: str,
    qc_receipt: Optional[dict],
) -> GateResult:
    """Pure function — no I/O, no subprocess. The CLI (`cmd_check`) does all file/arg
    handling and calls this. Easy to unit-test directly, mirrors diu_validator.py's
    band_problems() split (accumulate all problems, never short-circuit on the first)."""
    res = GateResult()
    prompt_lc = prompt_text.lower()
    model_norm = (model or "").strip().lower()

    # --- FORM (exit 3): required structural fields -------------------------------------
    if not (prompt_text or "").strip():
        res.form_problems.append(
            "AF-SM-PROMPT-FORM: prompt is empty — nothing to gate, nothing to generate.")

    if not ratio:
        res.form_problems.append(
            "AF-SM-PROMPT-FORM: no --ratio declared. Every Skill 35 image has an exact "
            "platform ratio (playbook.md Section 7/8/9) — a prompt without one cannot be "
            "routed to a placement.")
    elif ratio not in KNOWN_RATIOS:
        res.form_problems.append(
            f"AF-SM-PROMPT-FORM: --ratio {ratio!r} is not one of {sorted(KNOWN_RATIOS)} — "
            "not a real Skill 35 deliverable ratio (playbook.md Section 7/8/9).")

    if not pixels:
        res.form_problems.append(
            "AF-SM-PROMPT-FORM: no --pixels declared (e.g. 1080x1350). Pixel dimensions are "
            "a mandatory field on the QC Image Checklist (playbook.md Section 19).")

    if not (brand_colors or "").strip():
        res.form_problems.append(
            "AF-SM-PROMPT-FORM: no --brand-colors declared. playbook.md Section 18 rule 3 "
            "requires client brand colors pulled from the core .md files and applied to "
            "every image.")

    if not (avoid_list_text or "").strip():
        res.form_problems.append(
            "AF-SM-PROMPT-FORM: no merged negative/avoid-list supplied (--avoid-list-file). "
            "Step 7 of the P3-05 fix requires Skill 45's NEGATIVE-PROMPTING-SOP.md universal "
            "baseline + the social-media-designs _RULES.md category avoid-list to be loaded "
            "and merged into every prompt BEFORE it is written — an image prompt with no "
            "avoid-list carries no memory of prior failure classes.")

    if text_overlay:
        cn = _norm_ws(text_overlay)
        if cn and _norm_ws(prompt_text).find(cn) < 0:
            res.form_problems.append(
                f"AF-SM-PROMPT-FORM: the declared on-image text {text_overlay!r} (playbook.md "
                "Section 18) is NOT baked verbatim into the prompt body. kie.ai must bake the "
                "exact words in the same generation call — never defer text to a later overlay "
                "step (playbook.md Section 18 rule 1 + the WORDS-BAKED discipline).")

    if not any(marker in prompt_lc for marker in _BRAND_SAFETY_MARKERS):
        res.form_problems.append(
            "AF-SM-PROMPT-FORM: the mandatory brand-safety clause is absent. playbook.md "
            "Section 18 rule 5 requires every image prompt to explicitly include "
            "'brand-appropriate, appropriate for the client's audience, no suggestive "
            "content' — this is non-negotiable, not implied.")

    # --- QUALITY / ROUTING (exit 6): correct once FORM is complete ----------------------
    if text_overlay and model_norm in NON_TEXT_MODELS:
        res.quality_problems.append(
            f"AF-SM-MODEL-ROUTING: this prompt carries baked on-image text but is routed to "
            f"{model!r}, which is NOT a text-rendering specialist (playbook.md Section 8, "
            "pre-fix). Every text-overlay / quote-card / headline deliverable (i.e. every "
            "Section 18 image) MUST route to Ideogram V3 DESIGN per Skill 45's own routing "
            "rule (45-design-intelligence-library/library/social-media-designs/_RULES.md). "
            "Nano Banana 2/Pro is reserved for non-text imagery only.")
    elif text_overlay and model_norm not in TEXT_CAPABLE_MODELS:
        res.quality_problems.append(
            f"AF-SM-MODEL-ROUTING: unrecognized model {model!r} for a text-overlay prompt — "
            "expected one of " + ", ".join(sorted(TEXT_CAPABLE_MODELS)) + ".")

    if asset_source == "graphics-department":
        if qc_receipt is None:
            res.quality_problems.append(
                "AF-SM-INPUT-QC-GATE: --asset-source graphics-department but no "
                "--qc-receipt-file supplied. The planner REJECTS graphics-department assets "
                "lacking a SOP-GIP-02 QC receipt (P3-05 step 4i) instead of posting them.")
        else:
            score = None
            for k in _QC_RECEIPT_SCORE_KEYS:
                if k in qc_receipt:
                    try:
                        score = float(qc_receipt[k])
                    except (TypeError, ValueError):
                        score = None
                    break
            passed = bool(qc_receipt.get("pass", False))
            if score is None:
                res.quality_problems.append(
                    "AF-SM-INPUT-QC-GATE: qc-receipt-file has no numeric score field "
                    f"(expected one of {_QC_RECEIPT_SCORE_KEYS}) — cannot confirm the "
                    "SOP-GIP-02 >= 8.5 gate. Treated as ungated.")
            elif score < QC_RECEIPT_FLOOR or not passed:
                res.quality_problems.append(
                    f"AF-SM-INPUT-QC-GATE: SOP-GIP-02 receipt score {score} (pass={passed}) "
                    f"is under the {QC_RECEIPT_FLOOR} floor or not marked passed — this asset "
                    "is REJECTED, not posted (P3-05 step 4i).")

    return res


def _read_qc_receipt(path: Optional[str]) -> Optional[dict]:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return obj if isinstance(obj, dict) else None


def cmd_check(args: argparse.Namespace) -> int:
    prompt_path = Path(args.prompt_file)
    if not prompt_path.is_file():
        print(f"FATAL: --prompt-file not found: {prompt_path}", file=sys.stderr)
        return EXIT_USAGE
    prompt_text = prompt_path.read_text(encoding="utf-8")

    avoid_list_text = None
    if args.avoid_list_file:
        avp = Path(args.avoid_list_file)
        if not avp.is_file():
            print(f"FATAL: --avoid-list-file not found: {avp}", file=sys.stderr)
            return EXIT_USAGE
        avoid_list_text = avp.read_text(encoding="utf-8")

    qc_receipt = _read_qc_receipt(args.qc_receipt_file) if args.qc_receipt_file else None
    if args.qc_receipt_file and qc_receipt is None:
        print(f"FATAL: --qc-receipt-file could not be read/parsed as JSON: "
              f"{args.qc_receipt_file}", file=sys.stderr)
        return EXIT_USAGE

    result = check_prompt(
        prompt_text,
        model=args.model,
        ratio=args.ratio,
        pixels=args.pixels,
        platform=args.platform,
        text_overlay=args.text_overlay,
        brand_colors=args.brand_colors,
        avoid_list_text=avoid_list_text,
        asset_source=args.asset_source,
        qc_receipt=qc_receipt,
    )

    if result.ok:
        print(f"OK: prompt clears the Skill 35 pre-generation gate "
              f"(model={args.model}, ratio={args.ratio}, platform={args.platform}).")
        return EXIT_OK

    print("!" * 78, file=sys.stderr)
    if result.form_problems:
        print(f"FATAL AF-SM-PROMPT-FORM: prompt FAILS the pre-generation FORM gate — it is "
              f"NOT submitted, NOT generated. Fix the prompt, never generate.", file=sys.stderr)
        for msg in result.form_problems:
            print(f"  - {msg}", file=sys.stderr)
    if result.quality_problems:
        print(f"FATAL: prompt cleared FORM but has {len(result.quality_problems)} "
              f"quality/routing defect(s):", file=sys.stderr)
        for msg in result.quality_problems:
            print(f"  - {msg}", file=sys.stderr)
    print("!" * 78, file=sys.stderr)
    return result.exit_code


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Skill 35 pre-generation image-prompt QC gate (P3-05 step 9). Mirrors "
                    "diu_validator.py prompt-band's fail-closed exit-code discipline.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ck = sub.add_parser("check", help="gate one assembled prompt before generation")
    ck.add_argument("--prompt-file", required=True)
    ck.add_argument("--model", required=True,
                    help="e.g. ideogram-v3-design | nano-banana-2 | nano-banana-pro")
    ck.add_argument("--ratio", help="4:5 | 2:3 | 9:16 | 16:9 | 1:1")
    ck.add_argument("--pixels", help="e.g. 1080x1350")
    ck.add_argument("--platform", help="facebook | instagram | linkedin | pinterest | "
                                       "tiktok | youtube | blog | podcast_cover | thumbnail")
    ck.add_argument("--text-overlay", help="the exact on-image headline text, if any "
                                           "(playbook.md Section 18)")
    ck.add_argument("--brand-colors", help="comma-separated brand color list/hex codes")
    ck.add_argument("--avoid-list-file", help="path to the merged Skill-45 negative/avoid "
                                              "list for this prompt")
    ck.add_argument("--asset-source", default="internal-generated",
                    choices=["internal-generated", "graphics-department"],
                    help="internal-generated (Skill 35's own pipeline, default) or "
                         "graphics-department (an asset handed off from the Graphics "
                         "department — subject to the SOP-GIP-02 input-quality gate)")
    ck.add_argument("--qc-receipt-file", help="path to a SOP-GIP-02 image_qc_report.json "
                                              "(required when --asset-source is "
                                              "graphics-department)")
    ck.set_defaults(func=cmd_check)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
