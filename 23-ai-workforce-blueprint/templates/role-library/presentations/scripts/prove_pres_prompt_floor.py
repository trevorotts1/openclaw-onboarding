#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_pres_prompt_floor.py — standalone, CI-runnable prover for the Presentations
shared image-prompt gate (prompt_gate.py).

The 9,000–18,000-char floor + structural-block + 8-class negative-block + spelling-lock +
density + demographic-landmine gate used to live ONLY inside the 8,753-line build_deck.py,
so it could not be unit-tested in isolation or wired as a CI ledger gate. This prover
imports the SAME shared prompt_gate module every image-API path now uses and exercises it
against fixtures + any on-disk prompt file/dir — so the floor can never be a length-only
rubber stamp and drift is caught in CI.

USAGE
    python3 prove_pres_prompt_floor.py --self-test         # fixture gate (CI + verify.sh)
    python3 prove_pres_prompt_floor.py <prompt.txt> [...]   # gate one or more prompt files
    python3 prove_pres_prompt_floor.py --dir <run_dir>      # gate every working/prompts/slide-*.txt

EXIT CODES
    0 — all checked prompts clear the gate (or all self-test cases behaved as expected)
    2 — one or more prompts VIOLATE the gate
    3 — usage / fail-closed (bad args, unreadable file, prompt_gate import failure)

Provenance: build_deck.py PROMPT_CHAR_FLOOR/CEILING + rich_prompt_quality_problems +
_missing_structural_blocks + FORBIDDEN_DEMOGRAPHIC_DEFAULTS, extracted verbatim into
prompt_gate.py and drift-pinned to build_deck.py by sync_check.py.
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
    import prompt_gate
except Exception as exc:  # noqa: BLE001 — a missing shared gate is fail-closed, never skip
    print(f"FAIL-CLOSED: cannot import the shared prompt_gate module: {exc}", file=sys.stderr)
    raise SystemExit(EXIT_FAILCLOSED)


# ---------------------------------------------------------------------------
# Fixtures for --self-test. Each is (label, prompt_text, copy, should_pass).
# The PASS fixture is a genuinely rich prompt that clears every teeth-check; the FAIL
# fixtures each trip exactly one class of gate so a regression that silently loosens the
# gate is caught.
# ---------------------------------------------------------------------------
def _rich_pass_prompt() -> str:
    """Build a prompt that clears the whole gate: >=9,000 chars of DISTINCT content, the
    [ARCHETYPE] block, an 8-class DO-NOT BLOCK, a spelling-lock, hex palette, type size,
    a composition token, and the verbatim copy baked in."""
    copy_line = "Stop Guessing. Start Closing."
    head = (
        "[ARCHETYPE: split-hero editorial]\n"
        "Composition: rule of thirds grid, headline in the upper-third safe margin, "
        "focal point in the right third. Palette anchored on brand hex #0A2540 with an "
        "accent of #F2B134. Headline typography set at 96pt bold, subhead at 42pt.\n"
        f'HEADLINE VERBATIM + SPELLING-LOCK: render this exact string letter-for-letter, '
        f'spelled exactly: "{copy_line}".\n'
    )
    # A long body of DISTINCT sentences so the distinct-word floor (220) is cleared without
    # paste-repetition. Each sentence introduces new vocabulary.
    vocab = (
        "photoreal cinematic boardroom dusk amber rim-light glass table reflection "
        "confident founder tailored charcoal suit poised gesture layered depth bokeh "
        "shallow aperture volumetric haze directional key soft fill practical sconces "
        "warm tungsten cool teal contrast graded editorial magazine cover luminous "
        "shadows crushed inky highlights specular skyline window twilight metropolitan "
        "architectural leading lines negative space breathing room typographic hierarchy "
        "kerning tracking baseline ligature counters serif humanist geometric grotesque "
        "palette saturation vibrance clarity texture grain filmic anamorphic flare"
    ).split()
    body_sentences = []
    for i in range(55):
        w = vocab[i % len(vocab)]
        body_sentences.append(
            f"Detail {i}: the {w} element is described with a distinct clause "
            f"number {i} carrying its own descriptive nuance about lighting palette "
            f"placement and mood so the prompt reads rich and specific throughout stage {i}."
        )
    do_not = (
        "\n\nDO-NOT BLOCK:\n"
        "Do not render any misspelled or garbled text; render every quoted letter-for-letter. "
        "Do not redraw, recolor, or reinterpret the logo or monogram. "
        "Do not include any placeholder, bracketed token, or TBD build note. "
        "Do not add presenter narration, stage direction, or webinar self-talk into the picture. "
        "Do not produce anatomical artifacts such as a fused hand, extra limb, or malformed fingers. "
        "Do not let a busy cluttered background compete behind any text zone; keep legible negative space. "
        "Do not lighten, ashen, or desaturate any deep skin tone; preserve skin-tone fidelity. "
        "Do not add a watermark, emoji, clipart, Calibri or Arial system default font, or any UI artifact.\n"
    )
    return head + " ".join(body_sentences) + do_not


def _self_test() -> int:
    fixtures = []

    rich = _rich_pass_prompt()
    fixtures.append(("rich-pass", rich, "Stop Guessing. Start Closing.", True))

    fixtures.append(("thin-stub", "a short prompt with no spec", None, False))
    fixtures.append(("whitespace-only", "   \n   \t  ", None, False))

    # Long enough but missing structural blocks + quality teeth.
    padded = ("word " * 4000)  # ~20k chars but few distinct words, no blocks
    fixtures.append(("padded-no-structure", padded, None, False))

    # Rich body but a demographic landmine smuggled in.
    landmined = rich + "\nUse the default 60/30/10 demographic mix for the audience."
    fixtures.append(("demographic-landmine", landmined, "Stop Guessing. Start Closing.", False))

    # Rich body but the dead endpoint fragment present.
    dead = rich + "\nfetch " + prompt_gate.DEAD_ENDPOINT_FRAGMENT
    fixtures.append(("dead-endpoint", dead, "Stop Guessing. Start Closing.", False))

    failures: List[str] = []
    for label, text, copy, should_pass in fixtures:
        problems = prompt_gate.prompt_problems(text, copy)
        passed = not problems
        if passed != should_pass:
            failures.append(
                f"[{label}] expected {'PASS' if should_pass else 'FAIL'} but got "
                f"{'PASS' if passed else 'FAIL'}"
                + (f" — problems: {problems}" if problems else ""))
        else:
            verdict = "PASS" if passed else "FAIL(as expected)"
            print(f"  {label:24s} -> {verdict}")

    # The pin + mode-consistency + aspect helpers are covered by prompt_gate's own
    # self-test; run it too so this prover is the single CI entry point.
    pg_rc = prompt_gate._self_test()
    if pg_rc != 0:
        failures.append("prompt_gate._self_test() failed")

    if failures:
        print("\nSELF-TEST FAILURES:", file=sys.stderr)
        for f in failures:
            print("  - " + f, file=sys.stderr)
        return EXIT_VIOLATION
    print("\nprove_pres_prompt_floor --self-test: ALL FIXTURES BEHAVED AS EXPECTED")
    return EXIT_OK


def _gate_files(paths: List[Path]) -> int:
    any_violation = False
    checked = 0
    for p in paths:
        try:
            text = p.read_text(errors="replace")
        except OSError as exc:
            print(f"FAIL-CLOSED: cannot read {p}: {exc}", file=sys.stderr)
            return EXIT_FAILCLOSED
        checked += 1
        problems = prompt_gate.prompt_problems(text)
        if problems:
            any_violation = True
            print(f"VIOLATION {p} ({len(text.strip())} chars):", file=sys.stderr)
            for prob in problems:
                print("   - " + prob, file=sys.stderr)
        else:
            print(f"OK {p} ({len(text.strip())} chars) — clears the shared prompt gate")
    if checked == 0:
        print("FAIL-CLOSED: no prompt files to check", file=sys.stderr)
        return EXIT_FAILCLOSED
    return EXIT_VIOLATION if any_violation else EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prove the shared Presentations image-prompt gate.")
    ap.add_argument("prompts", nargs="*", help="prompt .txt file(s) to gate")
    ap.add_argument("--self-test", action="store_true", help="run the fixture gate (CI)")
    ap.add_argument("--dir", help="gate every working/prompts/slide-*.txt under this run dir")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    paths: List[Path] = []
    if args.dir:
        run_dir = Path(args.dir)
        prompts_dir = run_dir / "working" / "prompts"
        if not prompts_dir.is_dir():
            print(f"FAIL-CLOSED: {prompts_dir} is not a directory", file=sys.stderr)
            return EXIT_FAILCLOSED
        paths.extend(sorted(prompts_dir.glob("slide-*.txt")))
    paths.extend(Path(p) for p in args.prompts)

    if not paths:
        ap.print_usage(sys.stderr)
        print("FAIL-CLOSED: pass --self-test, one or more prompt files, or --dir <run_dir>",
              file=sys.stderr)
        return EXIT_FAILCLOSED

    return _gate_files(paths)


if __name__ == "__main__":
    raise SystemExit(main())
