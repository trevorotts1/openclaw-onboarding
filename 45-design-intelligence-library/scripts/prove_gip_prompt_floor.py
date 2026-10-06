#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_gip_prompt_floor.py — standalone, CI-runnable prover for the Graphics Image
Protocol (GIP) prompt-band gate (diu_validator.py prompt-band).

Graphics had MAX-only cap tiers and NO minimum floor anywhere: a one-line prompt could
reach the paid Kie.ai / GPT-Image 2.5 API unchallenged. FIX 1-A/1-B added per-asset-class
BANDS (prompt-bands.json). Since the owner order of 2026-10-05 (KIE prompt rule 12) a band
holds no length numbers: length is 95 to 100 percent of the model maxLength, floor 80
percent (AF-GIP-PROMPT-FLOOR), ceiling 100 percent (AF-DIU-PROMPT-CAP), enforced by the shared
enforcer shared-utils/kie_prompt_enforcer.py. The band keeps the length-INDEPENDENT quality gate
(AF-GIP-PROMPT-QUALITY): the 8-class negative block, a per-string spelling-lock + verbatim copy
on text-bearing bands, a distinct-word density floor, and the mandatory style-reference-only
directive.

This prover imports the SAME band functions diu_validator uses at runtime and exercises
them against fixtures — one genuinely rich PASS per band + one fixture per failure class —
so the floor can never become a length-only rubber stamp and a regression that silently
loosens a tooth is caught in CI (mirrors presentations' prove_pres_prompt_floor.py).

USAGE
    python3 prove_gip_prompt_floor.py --self-test          # fixture gate (CI + QC)
    python3 prove_gip_prompt_floor.py --band medium <p.txt> [--model ID]  # gate prompt files
    python3 prove_gip_prompt_floor.py --band text_bearing_long --dir <run_dir>

EXIT CODES
    0 — all checked prompts clear their band (or every self-test fixture behaved as expected)
    2 — one or more prompts VIOLATE their band gate
    3 — usage / fail-closed (bad args, unreadable file, diu_validator import failure)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

try:
    import diu_validator as dv
except Exception as exc:  # noqa: BLE001 — a missing gate module is fail-closed, never skip
    print(f"FAIL-CLOSED: cannot import diu_validator: {exc}", file=sys.stderr)
    raise SystemExit(EXIT_FAILCLOSED)


# ---------------------------------------------------------------------------
# Fixture builders — a rich, DISTINCT-word body so the density floor is cleared
# without paste-repetition (each numbered clause introduces new vocabulary).
# ---------------------------------------------------------------------------
_DO_NOT_BLOCK = (
    "\n\nDO-NOT BLOCK:\n"
    "Do not render any misspelled or garbled text; render every quoted letter-for-letter. "
    "Do not redraw, recolor, or reinterpret the logo, monogram, or tagline lockup. "
    "Do not produce anatomical artifacts such as a fused hand, extra limb, or malformed fingers. "
    "Do not let a busy, cluttered background compete behind any text zone; keep legible negative space. "
    "Do not leave any placeholder, bracketed token, or TBD build note visible in the render. "
    "Do not lighten, ashen, or desaturate any deep skin tone; preserve skin-tone fidelity. "
    "Do not add a watermark, emoji, clipart, or Calibri/Arial system default font. "
    "Do not drift off-brand or off-palette; stay inside the style card.\n"
)

# A negative block that still NAMES all 8 defect classes (garbled via "misspelled"/"garbled")
# but deliberately AVOIDS every spelling-lock marker token — so a fixture built with this block
# and no head spelling-lock genuinely trips the spelling-lock tooth (the head phrase is the only
# spelling-lock source). Mirrors the real distinction between the negative block and element 5.
_DO_NOT_BLOCK_NO_LOCK = (
    "\n\nDO-NOT BLOCK:\n"
    "Do not render any misspelled or garbled text on the image. "
    "Do not redraw, recolor, or reinterpret the logo, monogram, or tagline lockup. "
    "Do not produce anatomical artifacts such as a fused hand, extra limb, or malformed fingers. "
    "Do not let a busy, cluttered background compete behind any text zone; keep legible negative space. "
    "Do not leave any placeholder, bracketed token, or TBD build note visible in the render. "
    "Do not lighten, ashen, or desaturate any deep skin tone; preserve skin-tone fidelity. "
    "Do not add a watermark, emoji, clipart, or Calibri/Arial system default font. "
    "Do not drift off-brand or off-palette; stay inside the style card.\n"
)


def _distinct_body(n_sentences: int) -> str:
    vocab = (
        "photoreal cinematic boardroom dusk amber rim-light glass reflection confident founder "
        "tailored charcoal poised gesture layered depth bokeh shallow aperture volumetric haze "
        "directional key soft fill practical sconces warm tungsten cool teal contrast graded "
        "editorial magazine luminous shadows crushed inky highlights specular skyline window "
        "twilight metropolitan architectural leading lines negative space typographic hierarchy "
        "kerning tracking baseline ligature counters serif humanist geometric grotesque palette "
        "saturation vibrance clarity texture grain filmic anamorphic flare gradient duotone "
        "isometric vignette parallax silhouette gradient chromatic aberration halftone stipple"
    ).split()
    out = []
    for i in range(n_sentences):
        w = vocab[i % len(vocab)]
        out.append(
            f"Detail {i}: the {w} element is described with a distinct clause number {i} carrying "
            f"its own descriptive nuance about lighting palette placement mood and surface fitness "
            f"so the prompt reads rich and specific throughout production stage {i}."
        )
    return " ".join(out)


def _fit(head: str, tail: str, chars: int) -> str:
    """head + a distinct body + tail, sized to exactly `chars` stripped characters (the body is trimmed to fit)."""
    head, tail = head.lstrip(), tail.rstrip()
    room = chars - len(head) - len(tail)
    body = _distinct_body(room // 150 + 2)[:max(room, 0)]
    return head + body + tail


# Fixture sizes are percentages of the model max the band's first endpoint resolves to (Skill 74 registry
# snapshot, hermetic): GPT Image 2.5 = 20,000 for the text_bearing_long and visual_long bands, Seedream 4.5 = 3,000
# for the medium band.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import diu_validator as _dv  # noqa: E402  (the shared enforcer is reached through the validator)
GPT_MAX = _dv.KPE.budget_for("gpt-image-2-5-sunburst-text-to-image")["max"]
MEDIUM_MAX = _dv.KPE.budget_for("seedream/4.5-text-to-image")["max"] if _dv.KPE.budget_for("seedream/4.5-text-to-image") else 3000


def rich_text_bearing(copy_line: str = "Stop Guessing. Start Closing.",
                      with_spelling_lock: bool = True,
                      with_style_ref_only: bool = True,
                      do_not_block: str = _DO_NOT_BLOCK,
                      chars: int = GPT_MAX * 97 // 100) -> str:
    """A text_bearing_long PASS fixture: `chars` stripped characters (default 97 percent of the 20,000
    GPT Image 2.5 max), >=150 distinct words, the 8-class negative block, a spelling-lock, verbatim copy,
    and (optionally) the style-ref directive."""
    head = (
        "ASSET: ad creative | BAND: text_bearing_long\n"
        "Composition: rule of thirds grid, headline in the upper-third safe margin, focal point "
        "in the right third. Palette anchored on brand hex #0A2540 with an accent of #F2B134. "
        "Headline typography set at 96pt bold, subhead at 42pt.\n"
    )
    if with_spelling_lock:
        head += (f'TYPOGRAPHY + VERBATIM COPY: render this exact string, letter-for-letter, '
                 f'correctly spelled, with no added, dropped, doubled, or substituted characters: '
                 f'"{copy_line}".\n')
    else:
        head += f'HEADLINE COPY: "{copy_line}".\n'
    if with_style_ref_only:
        head += ("REFERENCE DIRECTIVE: use the attached images only as style reference for color "
                 "grading, lighting, and composition, do not copy their subjects, faces, or text.\n")
    return _fit(head, do_not_block, chars)


def rich_visual(chars: int = GPT_MAX * 97 // 100) -> str:
    """A visual_long PASS fixture (non-text-bearing: no spelling-lock required)."""
    head = (
        "ASSET: photoreal scene | BAND: visual_long\n"
        "Composition: rule of thirds, focal subject in the left third, brand hex #0A2540 grade.\n"
    )
    return _fit(head, _DO_NOT_BLOCK, chars)


def rich_medium(chars: int = MEDIUM_MAX * 97 // 100) -> str:
    """A medium PASS fixture (non-social specialty band, Seedream 4.5 endpoint, 3,000 max)."""
    head = (
        "ASSET: brand imagery | BAND: medium\n"
        "Composition: rule of thirds, focal subject in the left third, brand hex #0A2540 grade.\n"
    )
    return _fit(head, _DO_NOT_BLOCK, chars)


def _band(band_id: str):
    return dv._resolve_band(band_id, dv.load_bands())


def _self_test() -> int:
    failures: List[str] = []

    # (label, band_id, prompt_text, copy_val, style_ref, should_pass)
    fixtures = []

    tb = rich_text_bearing()
    fixtures.append(("text-bearing-rich-pass", "text_bearing_long", tb,
                     "Stop Guessing. Start Closing.", False, True))
    fixtures.append(("visual-rich-pass", "visual_long", rich_visual(), None, False, True))
    fixtures.append(("medium-rich-pass", "medium", rich_medium(), None, False, True))

    # --- Rule 12 length: 79 percent rejected, 95 and 100 percent pass, 101 percent rejected --------
    for label, pct, ok in (("79-percent", 79, False), ("95-percent", 95, True),
                           ("100-percent", 100, True), ("101-percent", 101, False)):
        fixtures.append((f"text-bearing-{label}", "text_bearing_long",
                         rich_text_bearing(chars=GPT_MAX * pct // 100),
                         "Stop Guessing. Start Closing.", False, ok))
        fixtures.append((f"medium-{label}", "medium", rich_medium(chars=MEDIUM_MAX * pct // 100), None, False, ok))
    # The retired house floors (5,000 / 9,000) no longer pass on a 20,000-char model.
    fixtures.append(("retired-9000-floor", "text_bearing_long", rich_text_bearing(chars=9000),
                     "Stop Guessing. Start Closing.", False, False))

    # Under the floor -> length fail.
    fixtures.append(("under-floor", "text_bearing_long", "a short prompt with no spec",
                     None, False, False))
    fixtures.append(("empty", "medium", "   \n  \t ", None, False, False))

    # Long enough + spelling-lock, but few DISTINCT words -> density (quality) fail.
    padded = ("ASSET: ad creative | BAND: text_bearing_long\n" + ("word " * 3880)).strip()
    padded = padded[:GPT_MAX * 97 // 100 - len(_DO_NOT_BLOCK)] + _DO_NOT_BLOCK
    fixtures.append(("padded-no-density", "text_bearing_long", padded, None, False, False))

    # Rich body but the negative block is stripped -> <6 classes (quality) fail.
    no_neg = rich_text_bearing(do_not_block="\n\nDo not make it ugly.\n")
    fixtures.append(("thin-negative-block", "text_bearing_long", no_neg,
                     "Stop Guessing. Start Closing.", False, False))

    # Text-bearing, rich, but NO spelling-lock directive -> quality fail. Uses the no-lock
    # negative block so the ONLY spelling-lock source (the head element-5 sentence) is absent.
    no_lock = rich_text_bearing(with_spelling_lock=False, do_not_block=_DO_NOT_BLOCK_NO_LOCK)
    fixtures.append(("no-spelling-lock", "text_bearing_long", no_lock,
                     "Stop Guessing. Start Closing.", False, False))

    # Text-bearing, rich, spelling-lock present, but the verbatim copy is NOT baked -> quality fail.
    fixtures.append(("copy-not-baked", "text_bearing_long", tb,
                     "A Totally Different Headline That Is Absent", False, False))

    # Style refs attached but NO style-reference-only directive -> quality fail.
    no_sr = rich_text_bearing(with_style_ref_only=False)
    fixtures.append(("style-ref-missing-directive", "text_bearing_long", no_sr,
                     "Stop Guessing. Start Closing.", True, False))

    # Rich body but a demographic landmine smuggled in -> AF-R3 (quality) fail.
    landmined = tb[:-40] + "\nUse the default 60/30/10 demographic mix for the audience."
    fixtures.append(("demographic-landmine", "text_bearing_long", landmined,
                     "Stop Guessing. Start Closing.", False, False))

    for label, band_id, text, copy, style_ref, should_pass in fixtures:
        band = _band(band_id)
        res = dv.band_problems(text, band, band_id, copy_val=copy, style_ref=style_ref)
        problems = res["length"] + res["quality"]
        passed = not problems
        if passed != should_pass:
            failures.append(
                f"[{label}] expected {'PASS' if should_pass else 'FAIL'} but got "
                f"{'PASS' if passed else 'FAIL'}"
                + (f"; problems: {problems}" if problems else ""))
        else:
            print(f"  {label:32s} -> {'PASS' if passed else 'FAIL(as expected)'}")
        # the rule 12 length fixtures must fail ON LENGTH (not on some unrelated quality tooth)
        if label.endswith(("79-percent", "101-percent")) or label == "retired-9000-floor":
            if not res["length"]:
                failures.append(f"[{label}] must be rejected by the LENGTH gate, got only: {problems}")

    # The exact-chars contract: the length message names the characters to add or cut.
    band = _band("text_bearing_long")
    low = dv.band_length_problems("x" * (GPT_MAX * 79 // 100), band, "text_bearing_long")
    if not any("ADD at least 200" in m for _, m in low):
        failures.append(f"79 percent rejection must name the exact chars to add (200): {low}")
    high = dv.band_length_problems("x" * (GPT_MAX * 101 // 100), band, "text_bearing_long")
    if not any(c == "AF-DIU-PROMPT-CAP" and "CUT exactly 200" in m for c, m in high):
        failures.append(f"101 percent rejection must name the exact chars to cut (200): {high}")

    # Assert the EXIT-CODE contract on the floor/cap vs quality distinction.
    if not dv.band_length_problems("tiny", band, "text_bearing_long"):
        failures.append("band_length_problems did not flag an under-floor prompt")
    qonly = _fit("ASSET x | BAND y\n", "", GPT_MAX * 97 // 100)  # in-band, dense, but no negative block/lock
    if dv.band_length_problems(qonly, band, "text_bearing_long"):
        failures.append("a length-OK prompt wrongly flagged a length problem (exit-code drift)")
    if not dv.band_quality_problems(qonly, band, "text_bearing_long"):
        failures.append("a quality-defective prompt cleared the quality gate")

    # GK-20 acceptance, read from the SAME prompt-bands.json diu_validator loads at runtime: no
    # text_bearing:true band lists nano-banana, no band holds a length number (rule 12 owns length), and
    # there is no Ideogram text-bearing band (Ideogram stays only on the non-social `medium` specialty band).
    all_bands = dv.load_bands()
    if "text_bearing_medium" in all_bands:
        failures.append("the text_bearing_medium Ideogram social band must not exist (owner order 2026-10-05)")
    for bid, b in all_bands.items():
        for key in ("min", "max"):
            if key in b:
                failures.append(f"{bid}: hard-coded {key} reintroduced in prompt-bands.json (rule 12 owns length)")
        endpoints = [str(e).lower() for e in (b.get("endpoints") or [])]
        if b.get("text_bearing"):
            if any("nano-banana" in e for e in endpoints):
                failures.append(f"GK-20 REGRESSION: text_bearing:true band {bid!r} lists a nano-banana endpoint "
                                f"({b.get('endpoints')}); Nano Banana is refused for text (AF-SM-MODEL-ROUTING)")
            if any("ideogram" in e for e in endpoints):
                failures.append(f"text_bearing:true band {bid!r} lists an Ideogram endpoint; Ideogram is not a social route")

    if failures:
        print("\nSELF-TEST FAILURES:", file=sys.stderr)
        for f in failures:
            print("  - " + f, file=sys.stderr)
        return EXIT_VIOLATION
    print("\nprove_gip_prompt_floor --self-test: ALL FIXTURES BEHAVED AS EXPECTED")
    return EXIT_OK


def _gate_files(band_id: str, paths: List[Path], copy_val=None, style_ref=False, model=None) -> int:
    try:
        band = _band(band_id)
    except (FileNotFoundError, ValueError) as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return EXIT_FAILCLOSED
    any_violation = False
    checked = 0
    for p in paths:
        try:
            text = p.read_text(errors="replace")
        except OSError as exc:
            print(f"FAIL-CLOSED: cannot read {p}: {exc}", file=sys.stderr)
            return EXIT_FAILCLOSED
        checked += 1
        res = dv.band_problems(text, band, band_id, copy_val=copy_val, style_ref=style_ref, model=model)
        problems = [f"{c}: {m}" for c, m in res["length"]] + res["quality"]
        if problems:
            any_violation = True
            print(f"VIOLATION {p} ({len(text.strip())} chars, band={band_id}):", file=sys.stderr)
            for prob in problems:
                print("   - " + prob, file=sys.stderr)
        else:
            print(f"OK {p} ({len(text.strip())} chars) — clears the {band_id} GIP band gate (rule 12)")
    if checked == 0:
        print("FAIL-CLOSED: no prompt files to check", file=sys.stderr)
        return EXIT_FAILCLOSED
    return EXIT_VIOLATION if any_violation else EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prove the Graphics Image Protocol prompt-band gate.")
    ap.add_argument("prompts", nargs="*", help="prompt .txt file(s) to gate")
    ap.add_argument("--self-test", action="store_true", help="run the fixture gate (CI)")
    ap.add_argument("--band", help="band id for file/dir mode (text_bearing_long | "
                                    "visual_long | medium | short_draft)")
    ap.add_argument("--model", help="KIE model id whose maxLength sets the length band "
                                    "(default: the band's first endpoint)")
    ap.add_argument("--copy", action="append", default=[], help="verbatim copy string (repeatable)")
    ap.add_argument("--style-ref", action="store_true", help="style refs attached")
    ap.add_argument("--dir", help="gate every working/prompts/*.txt under this run dir")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.band:
        ap.print_usage(sys.stderr)
        print("FAIL-CLOSED: --band is required in file/dir mode", file=sys.stderr)
        return EXIT_FAILCLOSED

    paths: List[Path] = []
    if args.dir:
        run_dir = Path(args.dir)
        prompts_dir = run_dir / "working" / "prompts"
        if not prompts_dir.is_dir():
            print(f"FAIL-CLOSED: {prompts_dir} is not a directory", file=sys.stderr)
            return EXIT_FAILCLOSED
        paths.extend(sorted(prompts_dir.glob("*.txt")))
    paths.extend(Path(p) for p in args.prompts)

    if not paths:
        ap.print_usage(sys.stderr)
        print("FAIL-CLOSED: pass --self-test, one or more prompt files, or --dir <run_dir>",
              file=sys.stderr)
        return EXIT_FAILCLOSED

    return _gate_files(args.band, paths, copy_val=(args.copy or None), style_ref=args.style_ref, model=args.model)


if __name__ == "__main__":
    raise SystemExit(main())
