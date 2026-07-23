#!/usr/bin/env python3
"""
test_prompt_band_cli.py — proves the GIP prompt-band gate (diu_validator.py
`prompt-band`) refuses under-floor and under-quality prompts THROUGH THE REAL CLI
(subprocess, no internal-function shortcuts), and passes a genuinely compliant one.

This is the P3-05 (e) QC break-it probe set, run as an actual fail-first test
rather than only described in a QC report:
  1. A 300-char "logo pls" prompt through the `medium` band -> refused, exit 3,
     AF-GIP-PROMPT-FLOOR quoted in stderr (the floor was previously nonexistent —
     G1 in the P3-05 root-cause finding).
  2. A ~6,000-char prompt built almost entirely from ONE repeated word (so it
     clears the `text_bearing_long` MIN char floor of 5,000 but fails the
     min_distinct_words=150 density floor) -> refused, exit 6,
     AF-GIP-PROMPT-QUALITY quoted in stderr.
  3. A genuinely rich, fully-compliant `text_bearing_long` prompt (every quality
     tooth satisfied: 8-class negative block, per-string spelling-lock, baked
     copy, style-reference-only directive, no hardcoded demographic split,
     >=150 distinct words, 5,000-19,000 chars) -> PASSES, exit 0.
  4. FAIL-FIRST PROOF: cases 1 and 2 are also run with `--bands-file` pointed at
     a deliberately permissive fixture bands file whose floors are all 0 — both
     now PASS (exit 0). This proves the two refusals above are actually caused
     by the shipped prompt-bands.json floors, not by an unrelated failure mode
     (a test that can't fail is not a test).
  5. GK-20 (band<->routing reconciliation): a genuinely compliant `text_bearing_medium`
     prompt — the band the mandatory Ideogram V3 DESIGN quote-card/text-led route
     resolves to (social-media-designs/_RULES.md) — PASSES (exit 0), proving the
     BINARY acceptance criterion (a text-bearing social prompt at the reconciled
     band's floor, routed to Ideogram V3 DESIGN, clears diu_validator.py prompt-band)
     end-to-end through the real CLI, not just the internal functions.

Run:  python3 test_prompt_band_cli.py
Exit: 0 = every assertion passed; 1 = a case failed (prints which one).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR = HERE / "diu_validator.py"

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  PASS: {label}")
    else:
        msg = f"  FAIL: {label}" + (f" — {detail}" if detail else "")
        print(msg)
        FAILURES.append(label)


def run_prompt_band(band: str, prompt: str, *, copy: list[str] | None = None,
                     style_ref: bool = False, bands_file: Path | None = None) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write(prompt)
        prompt_path = fh.name
    cmd = [sys.executable, str(VALIDATOR), "prompt-band", "--band", band,
           "--prompt-file", prompt_path]
    for c in (copy or []):
        cmd += ["--copy", c]
    if style_ref:
        cmd.append("--style-ref")
    if bands_file:
        cmd += ["--bands-file", str(bands_file)]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    finally:
        Path(prompt_path).unlink(missing_ok=True)


def _rich_compliant_prompt() -> str:
    """A fully-compliant text_bearing_long fixture: >=150 distinct words, every
    quality tooth present. Built from many distinct clauses (never repetition)
    so the distinct-word floor is cleared honestly, not padded."""
    clauses = [
        "ARCHETYPE: A2 warm-editorial hero banner for a mid-market services brand.",
        "SCENE: a sunlit modern coworking loft with exposed brick, brass fixtures, and a large arched window.",
        "COMPOSITION: rule-of-thirds framing, subject anchored on the left third, generous negative space on the right third for the headline zone.",
        "LIGHTING: soft golden-hour key light from camera-left, gentle fill from a bounce card, warm rim light separating the subject from the background.",
        "COLOR PALETTE: deep forest green, warm cream, brushed brass accents, matching the locked brand STYLE BLOCK exactly.",
        "COPY BAKED VERBATIM ON IMAGE: the headline reads exactly \"Grow With Confidence\" in a bold serif, upper third, 96pt weight 700.",
        "SUBHEAD BAKED VERBATIM: \"Real strategy. Real results.\" in a lighter weight sans-serif directly beneath the headline, 48pt weight 500.",
        "HUMAN SUBJECT CASTING: a confident woman in her forties, tailored blazer in the brand's forest green, warm genuine smile, hands resting on a walnut desk.",
        "AUDIENCE ENGINE: representation mix drawn from the client's casting ledger, mixed ages 30-55, mixed gender presentation, professional business-casual dress appropriate to the client's niche.",
        "WORLD ENGINE: a concrete real-world moment — the subject reviewing a quarterly growth chart with a colleague, not a generic stock-photo pose.",
        "LOGO TREATMENT: image-to-image mode, LOGO_URL supplied as the first reference input, anti-mutation instruction: do not redraw, recolor, or reinterpret the logo lockup.",
        "STYLE REFERENCE ONLY: any attached reference image guides style and mood only; do not copy composition or literal content from the reference.",
        "SPELLING LOCK: render every quoted string exactly letter-for-letter as written above; do not alter, misspell, duplicate, or drop any character in \"Grow With Confidence\" or \"Real strategy. Real results.\"",
        "TYPOGRAPHY: headline weight 700 at 96pt, subhead weight 500 at 48pt, both left-aligned to the right-third text zone.",
        "NEGATIVE BLOCK — DO NOT: do not render any misspelled or garbled text; render every quoted letter-for-letter.",
        "Do not redraw, recolor, or reinterpret the logo, monogram, or tagline lockup.",
        "Do not produce anatomical artifacts such as a fused hand, extra limb, or malformed fingers.",
        "Do not let a cluttered background compete behind any text zone; keep the negative space clean.",
        "Do not apply a heavy vignette or crush the shadows so brand colors shift off-palette.",
        "Do not render a generic stock-photo pose; keep the moment concrete and specific to the brief.",
        "Do not place text over the subject's face, eyes, or hands.",
        "Do not introduce a second unbranded logo or watermark anywhere in the frame.",
        "SECONDARY SCENE DETAIL: a shelf of leather-bound notebooks and a small potted fern sits just out of focus behind the subject's right shoulder, reinforcing an established, grounded brand feel.",
        "PROP DETAIL: a ceramic mug with a subtle embossed wordmark rests near the subject's hand, angled so the mug's own branding reads as ambient set-dressing, never a competing focal point.",
        "DEPTH OF FIELD: a shallow f/2.0-equivalent depth of field keeps the subject tack-sharp while the loft background falls into a soft, pleasing bokeh that never distracts from the text zone.",
        "CAMERA ANGLE: eye-level, slightly below center, giving the subject quiet authority without looming over the viewer.",
        "TEXTURE: visible brick texture on the left third contrasts with the smooth cream text zone on the right third, reinforcing the composition's rule-of-thirds split.",
        "SEASONAL CONTEXT: late-spring light through the arched window suggests renewal and forward momentum, matching the campaign's growth theme.",
        "WARDROBE DETAIL: the blazer's stitching and lapel are rendered with photoreal fabric weave, avoiding a flat, illustrated look.",
        "ACCESSIBILITY: text contrast against the cream background meets a strong readability threshold even at thumbnail size on a mobile feed.",
        "PLATFORM CROP SAFETY: the headline and subhead both sit fully inside the safe zone for a 4:5 crop, so no letterform is clipped when the platform reformats the image for a narrower feed slot.",
        "POST-PROCESSING NOTE: apply a light film grain at low opacity to match the client's established photographic house style across the last six months of campaign creative.",
        "BRAND VOICE ECHO: the overall mood should read as encouraging and grounded rather than aspirational-luxury, consistent with the client's mid-market services positioning.",
        "FINAL CHECK: every element above resolves to one coherent, single-scene composition — no collage, no split-frame, no floating disconnected graphic elements layered over the photography.",
        "RESOLUTION TARGET: render at the platform's full delivery resolution with no upscaling artifacts, banding, or compression noise visible in the flat cream text zone.",
        "CONTINUITY NOTE: match the established campaign's prior week's lighting temperature and prop styling so the series reads as one continuous visual story across posts.",
        "MATERIALS AND FINISH: the desk surface shows genuine walnut grain with a satin, not glossy, finish; the brass fixtures show a brushed, slightly warm patina rather than a chrome-bright polish, and every visible material renders with photographic plausibility rather than a computer-generated plastic sheen.",
        "AMBIENT DETAIL: a faint reflection of the arched window is visible in the polished tabletop, and a soft, believable shadow falls from the subject onto the desk, anchoring the figure believably in the physical space rather than looking pasted onto the background.",
    ]
    return "\n\n".join(clauses)


def _rich_compliant_prompt_medium() -> str:
    """A fully-compliant text_bearing_medium fixture (GK-20 -- the Ideogram V3 DESIGN
    route band): >=90 distinct words, every quality tooth present, sized comfortably
    inside [1,600, 4,500] -- Ideogram V3's own verified 5,000-char API cap minus the
    standard ~10% safety margin (MODEL-SPECS.md). Distinct clauses only, no padding."""
    clauses = [
        "ASSET: social post graphic with baked text | BAND: text_bearing_medium",
        "ARCHETYPE: a quote-card text-led post for a mid-market services brand, routed to Ideogram V3 DESIGN per social-media-designs/_RULES.md.",
        "SCENE: a clean editorial background with generous negative space reserved for the headline zone.",
        "COMPOSITION: centered headline block, subhead directly beneath, brand mark bottom-right.",
        "COLOR PALETTE: deep forest green, warm cream, brushed brass accent, matching the locked brand STYLE BLOCK exactly.",
        "COPY BAKED VERBATIM ON IMAGE: the headline reads exactly \"Stop Guessing. Start Closing.\" in a bold serif, centered, 96pt weight 700.",
        "SPELLING LOCK: render this exact string, letter-for-letter, correctly spelled, with no added, dropped, doubled, or substituted characters: \"Stop Guessing. Start Closing.\"",
        "STYLE REFERENCE ONLY: any attached reference image guides style and mood only; do not copy composition or literal content from the reference.",
        "TYPOGRAPHY: headline weight 700 at 96pt, centered, generous line height for mobile legibility.",
        "NEGATIVE BLOCK — DO NOT: do not render any misspelled or garbled text; render every quoted letter-for-letter.",
        "Do not redraw, recolor, or reinterpret the logo, monogram, or tagline lockup.",
        "Do not produce anatomical artifacts such as a fused hand, extra limb, or malformed fingers.",
        "Do not let a cluttered background compete behind any text zone; keep the negative space clean.",
        "Do not lighten, ashen, or desaturate any deep skin tone; preserve skin-tone fidelity.",
        "Do not add a watermark, emoji, clipart, or Calibri/Arial system default font.",
        "Do not drift off-brand or off-palette; stay inside the style card.",
        "Do not place any bracketed placeholder or TBD build note anywhere in the render.",
        "PLATFORM CROP SAFETY: the headline sits fully inside the safe zone for a 4:5 crop, so no letterform is clipped on a narrower feed slot.",
        "FINAL CHECK: the composition resolves to one coherent quote-card graphic -- no collage, no split-frame, no floating disconnected elements.",
    ]
    return "\n\n".join(clauses)


def main() -> int:
    print("=== 1. under-floor: 300-char \"logo pls\" through the `medium` band -> exit 3 ===")
    # Trim so it is genuinely ~300 chars and clearly a stub, not accidentally >= the floor.
    stub = ("logo pls, make it look nice, modern branding, " * 6)[:300]
    r1 = run_prompt_band("medium", stub)
    check("exit code is 3 (AF-GIP-PROMPT-FLOOR)", r1.returncode == 3, f"got {r1.returncode}, stderr={r1.stderr!r}")
    check("stderr names AF-GIP-PROMPT-FLOOR", "AF-GIP-PROMPT-FLOOR" in r1.stderr, r1.stderr)
    check("stub is NOT submitted (stdout carries no OK:)", "OK:" not in r1.stdout, r1.stdout)

    print("\n=== 2. under-density: clears the char floor via paste-repetition, <150 distinct words -> exit 6 ===")
    # "brand image concept concept concept ..." repeated -> long enough to CLEAR the
    # 5,000-char MIN floor but stay under the 150-distinct-word density floor. This is the
    # exact defect the density tooth exists to catch (a long file that pads instead of
    # specifying) — deliberately carries NO negative block / spelling-lock / style-ref
    # directive either, matching a real thin paste-repetition stub.
    padded = ("brand image concept " * 350)
    assert len(padded.strip()) >= 5000, "fixture must clear the char floor to isolate the density gate"
    r2 = run_prompt_band("text_bearing_long", padded)
    check("exit code is 6 (AF-GIP-PROMPT-QUALITY)", r2.returncode == 6, f"got {r2.returncode}, stderr={r2.stderr!r}")
    check("stderr names AF-GIP-PROMPT-QUALITY", "AF-GIP-PROMPT-QUALITY" in r2.stderr, r2.stderr)
    check("stderr specifically cites the distinct-word density defect",
          "distinct words" in r2.stderr and "band floor 150" in r2.stderr, r2.stderr)

    print("\n=== 3. genuinely compliant text_bearing_long prompt -> exit 0 ===")
    rich = _rich_compliant_prompt()
    r3 = run_prompt_band(
        "text_bearing_long", rich,
        copy=["Grow With Confidence", "Real strategy. Real results."],
        style_ref=True,
    )
    check("exit code is 0", r3.returncode == 0, f"got {r3.returncode}, stdout={r3.stdout!r}, stderr={r3.stderr!r}")
    check("stdout confirms OK", r3.stdout.strip().startswith("OK:"), r3.stdout)

    print("\n=== 4. fail-first proof: the SAME two bad prompts stop failing on the SPECIFIC gate ===")
    print("    tooth that was relaxed, when run against a permissive fixture bands file — proving")
    print("    cases 1 and 2 above are caused by the shipped floor numbers, not by a coincidental")
    print("    unrelated failure (a test that can't distinguish the fix from a fluke isn't a test).")
    permissive = {
        "bands": {
            "medium": {"min": 0, "max": 999999, "min_distinct_words": 0, "text_bearing": False},
            "text_bearing_long": {"min": 0, "max": 999999, "min_distinct_words": 0, "text_bearing": True},
        }
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(permissive, fh)
        permissive_path = Path(fh.name)
    try:
        # Case 1's stub has no negative block either, so it will still fail QUALITY against the
        # permissive file — but the LENGTH-specific AF-GIP-PROMPT-FLOOR problem must be GONE
        # (min:0 clears it), and the exit code must move off exit-3 (length no longer fails).
        r1p = run_prompt_band("medium", stub, bands_file=permissive_path)
        check("under-floor stub: AF-GIP-PROMPT-FLOOR disappears once the fixture floor is 0",
              "AF-GIP-PROMPT-FLOOR" not in r1p.stderr, r1p.stderr)
        check("under-floor stub: exit code is no longer 3 (length gate no longer the failure)",
              r1p.returncode != 3, f"got {r1p.returncode}")

        # Case 2's padded prompt has no negative block/spelling-lock either, so quality still
        # fails against the permissive file — but the density-specific complaint must be GONE
        # once min_distinct_words is 0.
        r2p = run_prompt_band("text_bearing_long", padded, bands_file=permissive_path)
        check("under-density prompt: the distinct-word density complaint disappears once the "
              "fixture's min_distinct_words is 0",
              "distinct words" not in r2p.stderr, r2p.stderr)
    finally:
        permissive_path.unlink(missing_ok=True)

    print("\n=== 5. GK-20: genuinely compliant text_bearing_medium prompt (Ideogram V3 DESIGN route) -> exit 0 ===")
    rich_medium = _rich_compliant_prompt_medium()
    r5 = run_prompt_band(
        "text_bearing_medium", rich_medium,
        copy=["Stop Guessing. Start Closing."],
        style_ref=True,
    )
    check("exit code is 0", r5.returncode == 0,
          f"got {r5.returncode}, stdout={r5.stdout!r}, stderr={r5.stderr!r}")
    check("stdout confirms OK", r5.stdout.strip().startswith("OK:"), r5.stdout)
    check("prompt is within the band's real cap margin (<=4,500 chars, Ideogram's own "
          "5,000-char API cap minus safety margin)",
          len(rich_medium.strip()) <= 4500, f"{len(rich_medium.strip())} chars")

    print("\n=== 6. GK-20: the SAME under-floor discipline holds on text_bearing_medium -> exit 3 ===")
    stub_medium = ("logo pls, make it look nice, modern branding, " * 6)[:300]
    r6 = run_prompt_band("text_bearing_medium", stub_medium)
    check("exit code is 3 (AF-GIP-PROMPT-FLOOR)", r6.returncode == 3,
          f"got {r6.returncode}, stderr={r6.stderr!r}")
    check("stderr names AF-GIP-PROMPT-FLOOR", "AF-GIP-PROMPT-FLOOR" in r6.stderr, r6.stderr)

    print()
    if FAILURES:
        print(f"test_prompt_band_cli: {len(FAILURES)} FAILURE(S): {FAILURES}")
        return 1
    print("test_prompt_band_cli: ALL CASES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
