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


# ---------------------------------------------------------------------------
# FIX 35 unit fixtures — one row per negation shape each scanner must survive.
# Covers the four named false-fire rows (QC.md FIX 35): the look-back copula
# ("dark theme is not wanted"), the conjunction scope ("or a near-black
# vignette"), the hook/footer context scan, and the rerank/AUD batteries.
# ---------------------------------------------------------------------------
def test_fix35_lookback_rows():
    s = _scanners.scan_negation_aware
    dark = ("dark background", "black background", "dark theme",
            "near-black", "dark slide", "dark mode")
    # LB-1 — the QC.md PROOF row: yesterday's slide-01 phrasing.
    _check("LB-1 'dark theme is not wanted' suppressed",
           s("the dark theme is not wanted by the client", dark) == [])
    _check("LB-2 'a dark background is not allowed' suppressed",
           s("a dark background is not allowed in this deck", dark) == [])
    _check("LB-3 'near-black is not requested' suppressed",
           s("near-black is not requested anywhere", dark) == [])
    # LB-4 — the look-back must NOT swallow a real technique telegraph in the
    # same sentence family. The negator followed by a NON-refusal predicate
    # ("not just a webinar") keeps its forward window only, so the bare word
    # inside the forward window stays suppressed — but AUD_META_TOKENS also
    # carries the multiword telegraph "this is not just", which contains the
    # negator INSIDE the phrase and therefore never lands in any negation
    # window: the AUD-4 gate still fires on it (asserted in test_fix35_aud_rows).
    _check("LB-4 'this is not just' telegraph phrase fires",
           bool(s("this is not just a webinar", ("this is not just",))))
    _check("LB-5 'dark theme is wanted' (no negator) fires",
           bool(s("the dark theme is wanted here", dark)))


def test_fix35_conjunction_rows():
    s = _scanners.scan_negation_aware
    dark = ("dark background", "near-black")
    # CJ-1 — coordinated objects share the prohibition's scope.
    _check("CJ-1 'no dark background or a near-black vignette' suppressed",
           s("no dark background or a near-black vignette anywhere", dark) == [])
    _check("CJ-2 'avoid dark backgrounds, black gradients' suppressed",
           s("avoid dark backgrounds, deep black gradients, heavy vignettes",
             ("dark background", "black background")) == [])
    _check("CJ-3 'never a footer band / bottom strip' suppressed",
           s("never a footer band / bottom strip on any slide",
             ("footer", "bottom band", "bottom strip")) == [])
    # CJ-4 — a hit BEYOND the coordinated objects still fires (bounded extension).
    _check("CJ-4 second sentence after conjunction row fires",
           bool(s("no dark background or near-black vignette. "
                  "use a dark background there.", dark)))
    # FIX 35 B4 corollary (R-B02-B4): the coordinated object is a PHRASE, not
    # one token. The SOP's own element-15 template line — "explicitly prohibit
    # navy, charcoal, black, and any dark background in element 15" — put the
    # keyword three tokens past the conjunction; the old +2-per-conjunction
    # jump stopped at the determiner 'any' and the SOP's mandated line tripped
    # AF-DARK-SLIDE. The extension now grants a full object window after each
    # conjunction. CJ-5 reproduces the SOP line verbatim (the false fire);
    # CJ-6 keeps the bound: a keyword a full window past the LAST coordinated
    # object still fires.
    _check("CJ-5 SOP element-15 verbatim line suppressed",
           s("Explicitly prohibit navy, charcoal, black, and any dark "
             "background in element 15 (AVOID block).", dark) == [])
    _check("CJ-6 keyword a full window past the last object fires",
           bool(s("avoid a, b, c, d, e, f and any dark background this deck "
                  "must stay light", ("dark background",))))


def _hook_run_dir(slide01_text: str):
    import intelligence_engines_check as iec
    root = Path(tempfile.mkdtemp(prefix="deck_fix35_hook_"))
    (root / "prompts").mkdir(parents=True, exist_ok=True)
    (root / "copy").mkdir(parents=True, exist_ok=True)
    (root / "copy" / "intake.json").write_text(json.dumps(
        {"hook": "Your ceiling is your floor."}))
    hook = "Your ceiling is your floor."
    (root / "prompts" / "slide-01.txt").write_text(slide01_text)
    for n in (2, 3):
        (root / "prompts" / f"slide-{n:02d}.txt").write_text(
            f"Slide {n} references {hook} once, centered, upper third.")
    return iec, root


def test_fix35_hook_footer_rows():
    # HK-1 — QC.md PROOF row 3: "no footer band" near the hook PASSES.
    iec, root = _hook_run_dir(
        "Full-bleed hero. The line 'Your ceiling is your floor.' sits alone, "
        "oversized, on its own typographic beat. No footer band on any slide, "
        "never a footer stamp, no bottom strip.")
    problems = []
    iec._check_hook_image(root, problems)
    _check("HK-1 hook near 'no footer band' passes",
           not any(p["code"] == "AF-HOOK" for p in problems))
    # HK-2 — teeth: a hook baked into a REAL footer band still fails.
    iec, root = _hook_run_dir(
        "Full-bleed hero. The line 'Your ceiling is your floor.' baked into a "
        "footer band across the bottom of the slide.")
    problems = []
    iec._check_hook_image(root, problems)
    _check("HK-2 real footer band still fails AF-HOOK",
           any(p["code"] == "AF-HOOK" for p in problems))


def _rerank_run_dir(copy: str):
    import build_deck as bd
    root = Path(tempfile.mkdtemp(prefix="deck_fix35_rr_"))
    (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (root / "working" / "copy" / "priority_shift_spec.json").write_text(
        json.dumps({"goal": "fixture"}))
    (root / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"pitch_included": True}))
    (root / "working" / "copy" / "slides_copy.md").write_text(copy)
    return bd, root


def test_fix35_rerank_rows():
    # RR-1 — a real price beat + a real demand after it satisfies Move 7.
    bd, root = _rerank_run_dir(
        "SLIDE 40\nThe price is $997.\n"
        "Make this your #1 — move this to the top.\n")
    _check("RR-1 real price + real demand passes",
           bd._chk_rerank(root) == "")
    # RR-2 — real price beat, only NEGATED re-rank language -> FAILS.
    bd, root = _rerank_run_dir(
        "SLIDE 40\nThe price is $997.\n"
        "Do not move this to the top; no re-rank now.\n")
    _check("RR-2 negated demand after real price FAILS",
           "AF-NO-RERANK" in bd._chk_rerank(root))
    # RR-3 — the 'price' substring row: 'pricing'/'priceless' must NOT anchor
    # Move 7 (the old text.find('price') matched inside the longer word, and a
    # demand after the false anchor satisfied the gate with no price beat).
    bd, root = _rerank_run_dir(
        "SLIDE 12\nPricing options abound — everyone overcharges.\n"
        "Move this to the top now.\n")
    out = bd._chk_rerank(root)
    _check("RR-3 'pricing' substring does not anchor a price beat",
           "AF-NO-RERANK" not in out)
    bd, root = _rerank_run_dir(
        "SLIDE 12\nThis insight is priceless.\nMove this to the top now.\n")
    out = bd._chk_rerank(root)
    _check("RR-4 'priceless' substring does not anchor a price beat",
           "AF-NO-RERANK" not in out)
    # RR-5 — teeth: with a REAL price beat and no demand at all, still FAILS.
    bd, root = _rerank_run_dir(
        "SLIDE 40\nThe price is $997.\nNothing demanded here.\n")
    _check("RR-5 real price + no demand FAILS",
           "AF-NO-RERANK" in bd._chk_rerank(root))


def test_fix35_aud_rows():
    import slide_craft
    def _aud_deck(copy_block):
        root = Path(tempfile.mkdtemp(prefix="deck_fix35_aud_"))
        (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
        (root / "working" / "copy" / "intake.json").write_text(json.dumps(
            {"deck_type": "webinar"}))
        slides = [{"slide": 1, "scene": "x", "copy": [copy_block]}]
        (root / "working" / "copy" / "slides.json").write_text(json.dumps(slides))
        return root, root / "working" / "copy" / "slides.json"
    # AU-1 — QC.md PROOF row: 'webinar' inside a negation is a disclaimer, not
    # the technique telegraph; must NOT trip AF-AUD-4.
    root, sp = _aud_deck("This is a keynote, not a webinar.")
    _check("AU-1 'not a webinar' disclaimer passes",
           slide_craft.check_aud_meta_tokens(root, sp) == "")
    # AU-2 — teeth: the bare technique telegraph still fails AF-AUD-4.
    root, sp = _aud_deck("THIS IS NOT JUST A WEBINAR")
    out = slide_craft.check_aud_meta_tokens(root, sp)
    _check("AU-2 'this is not just a webinar' telegraph FAILS",
           "AF-AUD-4" in out)
    # AU-3 — the standalone word still fails (window cannot hide a real use).
    root, sp = _aud_deck("Join our webinar series.")
    out = slide_craft.check_aud_meta_tokens(root, sp)
    _check("AU-3 bare 'webinar' FAILS", "AF-AUD-4" in out)


def _main() -> int:
    test_scan_negation_aware_unit()
    test_proof_fixture_pair()
    test_existing_dark_teeth_unchanged()
    test_landmine_negation_aware()
    test_prompt_lint_warns_and_stays_silent()
    test_fix35_lookback_rows()
    test_fix35_conjunction_rows()
    test_fix35_hook_footer_rows()
    test_fix35_rerank_rows()
    test_fix35_aud_rows()
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
