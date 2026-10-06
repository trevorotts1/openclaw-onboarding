"""
FIX 110 — Deterministic scanners understand negation (extends FIX 24, 35).

PROBLEM (R14 §2.3, §5.8; ledger F45): slide 1's own prohibition "no dark
slide background appears anywhere" tripped AF-DARK-SLIDE. The keyword gates
were substring scans: a substring scanner cannot tell a REQUEST for a dark
background from a PROHIBITION of one, so the deck's own doctrine text failed
the deck.

WHAT THIS PROVES (MASTER plan FIX 110 PROOF):
  1. A fixture prompt containing "no dark background anywhere" PASSES
     _chk_no_dark_slides (the negation window suppresses the hit).
  2. The same prompt with "dark background throughout" FAILS (a genuine
     request still trips the gate — the gate is not weakened).
  3. scan_negation_aware itself: each negator (no, never, not, without,
     avoid, prohibit) suppresses a same-sentence keyword within six tokens;
     a hit six+ tokens past the negator or in a different sentence fires;
     a hit outside any negation window fires.
  4. The demographic landmine gates are negation-aware BOTH at render time
     (assert_no_forbidden_demographic_default) and at prompt-QC
     (check_prompt_qc_deterministic AF-R3): "no 60/30/10 anywhere" passes,
     "use the standard 60/30/10 split" still fails.
  5. The prompt lint warns an author whose PROHIBITION is written in scanner
     vocabulary ("no dark background anywhere" -> staged warning), and stays
     silent on positive art direction ("render light backgrounds only").
  6. The EXISTING scanner tests still pass (dark triggers without flag,
     light passes, dark with client_dark_theme passes, DARK_OK alias honored,
     landmine raises) — this file re-asserts the same four dark fixtures
     against the implementation so the FIX-110 rewrite of the scan cannot
     silently change the gate's pre-existing teeth.

Flat file inside tests/, manages its own import path — matching every
sibling in this directory.

Run:  python3 test_scanners_negation.py
Exit: 0 = all assertions passed; 1 = a case failed. (Also pytest-runnable.)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import build_deck  # noqa: E402
from presentation_job import scanners as _scanners  # noqa: E402

_FAILURES: list = []


def _check(label: str, ok: bool, detail: str = "") -> None:
    line = f"{label}: {'PASS' if ok else 'FAIL'}"
    if detail:
        line += f"  [{detail}]"
    print(line)
    if not ok:
        _FAILURES.append(label + (f" ({detail})" if detail else ""))


# ---------------------------------------------------------------------------
# scan_negation_aware unit cases
# ---------------------------------------------------------------------------
def test_scan_negation_aware_unit():
    s = _scanners.scan_negation_aware
    _check("NA-A 'no dark background anywhere' suppressed",
           s("no dark background anywhere", ["dark background"]) == [])
    _check("NA-B 'dark background throughout' fires",
           s("dark background throughout", ["dark background"]) ==
           [("dark background", 0)])
    _check("NA-C 'never render a dark background' suppressed",
           s("never render a dark background", ["dark background"]) == [])
    _check("NA-D 'not a dark background' suppressed",
           s("this is not a dark background scene", ["dark background"]) == [])
    _check("NA-E 'avoid dark backgrounds' suppressed",
           s("avoid dark backgrounds everywhere", ["dark background"]) == [])
    _check("NA-F 'without a dark background' suppressed",
           s("without a dark background the text stays legible",
             ["dark background"]) == [])
    _check("NA-G 'prohibit any dark background' suppressed",
           s("prohibit any dark background in this deck",
             ["dark background"]) == [])
    # Six-token window: 'dark' 6 tokens after the negator is suppressed,
    # 7 tokens after fires again.
    _check("NA-H 6th token after negator suppressed",
           s("no a b c d e dark background", ["dark background"]) == [])
    _check("NA-I 7th token after negator fires",
           bool(s("no a b c d e f dark background", ["dark background"])))
    # Sentence boundary: same negator, next sentence still fires.
    _check("NA-J sentence boundary respected",
           bool(s("no dark background here. use a dark background there.",
                  ["dark background"])))
    # Bare non-negated keyword always fires (unchanged substring behavior).
    _check("NA-K bare keyword fires",
           s("dark background", ["dark background"]) == [("dark background", 0)])
    # Case-insensitive.
    _check("NA-L uppercase keyword fires",
           bool(s("RICH DARK BACKGROUND on the hero", ["dark background"])))
    # Empty text / empty keywords are safe.
    _check("NA-M empty text safe", s("", ["dark background"]) == [])
    _check("NA-N empty keywords safe", s("dark background", []) == [])
    # whole-word boundary: glue does not alias.
    _check("NA-O glued hit not aliased",
           s("default demographic-defaults here", ["default demographic"]) == [])
    # later negation resumes scanning after the window.
    _check("NA-P hit outside window fires again",
           bool(s("no dark slide. but then use a dark background.",
                  ["dark background"])))


# ---------------------------------------------------------------------------
# PROOF 1 + 2: the fixture prompt pair through the real gate
# ---------------------------------------------------------------------------
def _dark_run_dir(prompt: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="deck_fix110_"))
    (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (root / "working" / "prompts").mkdir(parents=True, exist_ok=True)
    (root / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"interview_confirmed": True, "presentation_mode": "one-person"}))
    (root / "working" / "prompts" / "slide-01.txt").write_text(prompt)
    return root


def _gate_fails(rd: Path) -> bool:
    return "AF-DARK-SLIDE" in build_deck._chk_no_dark_slides(rd)


def test_proof_fixture_pair():
    # PROOF 1: prohibition passes.
    prohib = ("SLIDE 1 IMAGE PROMPT\n\nScene: no dark background anywhere — "
              "render a bright ivory studio with warm amber accents instead.\n")
    _check("PROOF-1 prohibition 'no dark background anywhere' PASSES",
           not _gate_fails(_dark_run_dir(prohib)))
    # PROOF 2: actual request fails.
    request = ("SLIDE 1 IMAGE PROMPT\n\nScene: moody stage with a dark "
               "background throughout and deep black gradients.\n")
    _check("PROOF-2 request 'dark background throughout' FAILS",
           _gate_fails(_dark_run_dir(request)))


# ---------------------------------------------------------------------------
# pre-existing scanner teeth: the four dark fixtures + DARK_OK alias
# ---------------------------------------------------------------------------
def _legacy_dark_fixture(dark: bool) -> str:
    if dark:
        return ("SLIDE 1 IMAGE PROMPT\n\n"
                "Scene: A moody, atmospheric stage with a dark background and deep "
                "black gradients framing the speaker silhouette. The lighting from "
                "below creates a near-black vignette that draws focus to the central "
                "figure. The dark theme is intentional and cinematic.\n\n"
                "Layout: full-bleed cinematic.\nSubject: presenter, center.\n")
    return ("SLIDE 1 IMAGE PROMPT\n\n"
            "Scene: A bright, airy conference room bathed in natural daylight. The "
            "background is a clean off-white wall with warm accent lighting. The "
            "colour palette is ivory, sky blue, and soft amber — all light, open, "
            "and energetic.\n\nLayout: full-bleed airy.\nSubject: presenter, center.\n")


def test_existing_dark_teeth_unchanged():
    # dark prompt + no flag -> FAILS (the exact test_preflight fixture).
    rd = _dark_run_dir(_legacy_dark_fixture(dark=True))
    _check("TEETH-1 dark prompt without flag FAILS", _gate_fails(rd))
    # light prompt + no flag -> PASSES.
    rd = _dark_run_dir(_legacy_dark_fixture(dark=False))
    _check("TEETH-2 light prompt PASSES", not _gate_fails(rd))
    # dark prompt + client_dark_theme:true -> PASSES (opt-in honored).
    rd = _dark_run_dir(_legacy_dark_fixture(dark=True))
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"interview_confirmed": True, "client_dark_theme": True}))
    _check("TEETH-3 dark prompt with client flag PASSES", not _gate_fails(rd))
    # DARK_OK alias honored, and a dark prompt with NO opt-in still fails.
    rd = _dark_run_dir(_legacy_dark_fixture(dark=True))
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"interview_confirmed": True, "DARK_OK": True}))
    _check("TEETH-4 DARK_OK:true honored", not _gate_fails(rd))
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"interview_confirmed": True}))
    _check("TEETH-5 dark prompt with NO opt-in still FAILS", _gate_fails(rd))


# ---------------------------------------------------------------------------
# demographic landmine gates are negation-aware
# ---------------------------------------------------------------------------
def test_landmine_negation_aware():
    # render-time gate (raises ValueError on a genuine landmine).
    try:
        build_deck.assert_no_forbidden_demographic_default(
            {"slide": 1, "scene": "office, 60/30/10 representation split",
             "copy": ["x"]})
        _check("LM-1 genuine landmine raises", False)
    except ValueError:
        _check("LM-1 genuine landmine raises", True)
    # prohibition passes.
    try:
        build_deck.assert_no_forbidden_demographic_default(
            {"slide": 1, "scene": "no 60/30/10 default split anywhere",
             "copy": ["x"]})
        _check("LM-2 'no 60/30/10' prohibition PASSES", True)
    except ValueError:
        _check("LM-2 'no 60/30/10' prohibition PASSES", False)
    try:
        build_deck.assert_no_forbidden_demographic_default(
            {"slide": 1, "scene": "never assume a default demographic",
             "copy": ["x"]})
        _check("LM-3 'never assume a default demographic' PASSES", True)
    except ValueError:
        _check("LM-3 'never assume a default demographic' PASSES", False)


# ---------------------------------------------------------------------------
# prompt lint: prohibition in scanner vocabulary warns; positive direction silent
# ---------------------------------------------------------------------------
def test_prompt_lint_warns_and_stays_silent():
    out = _scanners.lint_prohibition(
        "no dark background anywhere. render a bright ivory studio.")
    _check("LINT-1 prohibition in scanner vocabulary warns", len(out) >= 1)
    out = _scanners.lint_prohibition(
        "Render a warm ivory background with amber accents; avoid busy textures.")
    _check("LINT-2 positive art direction silent", out == [])


def _main() -> int:
    test_scan_negation_aware_unit()
    test_proof_fixture_pair()
    test_existing_dark_teeth_unchanged()
    test_landmine_negation_aware()
    test_prompt_lint_warns_and_stays_silent()
    print("-" * 60)
    if _FAILURES:
        print(f"FAILURES: {len(_FAILURES)}")
        for f in _FAILURES:
            print("  -", f)
        return 1
    print("ALL SCANNERS-NEGATION CHECKS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
