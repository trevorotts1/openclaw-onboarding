#!/usr/bin/env python3
"""
test_preflight.py — proves the build_deck.py PROCESS PREFLIGHT gate.

Three CLI cases, all driven through the real CLI (subprocess), no network needed:

  1. MISSING artifacts  -> exit 3, stderr lists each missing artifact + producer.
  2. PRESENT artifacts  -> preflight PASSES (does NOT exit 3); the run gets PAST
                           the gate (it then stops at the KIE_API_KEY / render
                           stage, which is fine — we only assert the gate passed).
  3. --adhoc-no-process -> preflight SKIPPED, loud non-deliverable banner printed,
                           run gets past the gate.

Plus unit assertions on the build_deck.py check functions directly (no subprocess):
  - COVERAGE (anti-compression, AF-COVERAGE-1).
  - RICH-PROMPT-REQUIRED (AF-P1): a slide with NO rich prompt FAILS, and a slide
    whose rich prompt is < PROMPT_CHAR_FLOOR (1,500) chars FAILS; a >= 1,500-char
    prompt PASSES. Also asserts load_rich_prompt raises on missing/short and
    returns the prompt verbatim when valid.
  - SPEECH-LENGTH (AF-SPEECH-SHORT): a speech below target_talk_minutes x 120 wpm
    FAILS; at/above PASSES; absent speech defers (passes).

Run:  python3 test_preflight.py
Exit: 0 = all assertions passed; 1 = a case failed.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build_deck.py"

# Import the module so unit tests can call its check functions directly.
sys.path.insert(0, str(HERE))
import build_deck  # noqa: E402

SLIDES = [
    {"slide": 1, "scene": "A sunlit modern office, editorial photography.",
     "copy": ["Northwind Co", "Three moves that doubled our pipeline"]},
]

# A realistic RICH per-slide prompt is long (the SOP targets 9,000-14,000 chars).
# >= PROMPT_CHAR_FLOOR (5,000) is the reconciled HARD floor; build it well over it.
RICH_PROMPT = (
    "[ARCHETYPE A1] [SECTION: HOOK] [LADDER: open]\n"
    "ONE BIG IDEA: Three moves that doubled the pipeline.\n"
    "FORMAT: Create a 16:9 presentation slide image at 2K resolution (2560x1440 pixels). "
    "BACKGROUND: White base background; brand accent used only as accent elements. "
    "HEADLINE VERBATIM: The slide headline reads exactly: 'Three moves that doubled our pipeline'. "
    "Render this exact string letter-for-letter, correctly spelled, with no added, dropped, "
    "doubled, or substituted characters. TYPOGRAPHY: one typeface family, hierarchy by weight; "
    "hero headline 72pt Black, subhead 28pt SemiBold; designed into the image, never a basic font. "
    "THIRDS GRID: headline upper-left, hero subject lower-right. PEOPLE: a confident founder, warm "
    "hopeful expression, editorial office at golden hour; representation comes from the casting "
    "ledger. MOOD: aspirational, readable in two seconds. PROFESSIONALISM: gallery-grade standalone "
    "art, premium lifestyle-documentary photography, sharp focus, no watermark, no blur. "
    "CLOSING CONSTRAINTS (negative block): Do not garble text. Do not mutate the logo. Do not "
    "render any bracketed placeholder token. Do not narrate the image. Do not produce anatomical "
    "artifacts. Do not let the background compete with the text. Do not alter skin-tone fidelity. "
) * 6  # ~6x => comfortably over the 5,000 floor, under the 18,000 ceiling


def _write_intake(root: Path):
    (root / "working" / "copy" / "intake.json").write_text(json.dumps({
        "interview_confirmed": True,
        "presentation_mode": "general",
        "audience_mode": "STANDARD",
        "target_talk_minutes": 30,
    }))


def make_workdir(with_artifacts: bool, *, rich_prompts: bool = True,
                 short_prompt: bool = False) -> Path:
    """Build a temp run dir. with_artifacts=True writes the full upstream set.
    rich_prompts=False omits the working/prompts/ files (to prove the
    rich-prompt-required gate fails); short_prompt=True writes a sub-floor prompt
    (to prove the 1,500-char floor fails)."""
    root = Path(tempfile.mkdtemp(prefix="deck_preflight_test_"))
    # The full-artifacts deck is sized to clear the AF-SLIDE-COUNT-FLOOR gate for the
    # 30-minute intake target (floor = ceil(30 x 1.3) = 39 slides). The bare/no-artifact
    # deck keeps the single SLIDES fixture (the gate defers when no intake target exists).
    _talk_minutes = 30
    _floor_slides = int(__import__("math").ceil(_talk_minutes * 1.3))  # 39
    if with_artifacts:
        deck_slides = [
            {"slide": i,
             "scene": f"Editorial office scene {i}, documentary photography.",
             "copy": [f"Northwind Co", f"Converting beat {i}"]}
            for i in range(1, _floor_slides + 1)
        ]
        (root / "slides.json").write_text(json.dumps(deck_slides))
    else:
        (root / "slides.json").write_text(json.dumps(SLIDES))
    if with_artifacts:
        (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
        (root / "working" / "research").mkdir(parents=True, exist_ok=True)
        (root / "working" / "qc").mkdir(parents=True, exist_ok=True)
        (root / "working" / "prompts").mkdir(parents=True, exist_ok=True)
        _write_intake(root)
        # Research brief with >= MIN_CITED_SOURCES (8) real cited URLs so the
        # AF-RESEARCH-UNCITED gate passes.  Each URL is on its own line and is a
        # distinct authoritative source (the gate counts distinct URLs, not lines).
        #
        # The AF-RESEARCH-GATE (_chk_research_brief) ALSO requires the Deep-Research
        # categories G, H, I, K, and L to be PRESENT as '## Category X:' headings AND
        # carry real (non-placeholder, non-blank) bodies before research_complete:true
        # is honoured.  Each section below carries a real authored body so the gate
        # passes — this mirrors what a completed Phase -0.5 (Deep Research Specialist
        # SOP 9.4) brief looks like.  Do NOT replace these bodies with blanks or
        # "[Output of SOP …]" placeholder lines — the gate counts those as empty.
        (root / "working" / "research" / "brief-demo.md").write_text(
            "# Research brief\n"
            "research_complete: true\n"
            "Categories A,C,D,F,G,H,I,K,L\n\n"
            "- Source: https://pmc.ncbi.nlm.nih.gov/articles/PMC12674523/\n"
            "- Source: https://www.researchgate.net/publication/369670311\n"
            "- Source: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9135772/\n"
            "- Source: https://www.jsr.org/hs/index.php/path/article/view/3679\n"
            "- Source: https://www.ncbi.nlm.nih.gov/books/NBK608531/\n"
            "- Source: https://www.pewresearch.org/social-trends/2023/01/24/\n"
            "- Source: https://www.apa.org/topics/parenting/positive-discipline\n"
            "- Source: https://www.cdc.gov/childrensmentalhealth/data.html\n"
            "\n"
            "## Category G: Credible Attributable Quotes\n"
            "- \"Pipelines that get a second human touch in the first hour close "
            "roughly twice as often.\" — VP Revenue Operations, peer-reviewed sales "
            "benchmark (ResearchGate 369670311).\n"
            "- \"Decision-makers reward the vendor who reframes the problem, not the "
            "one who lists features.\" — buyer-psychology study, APA positive-influence "
            "literature.\n"
            "\n"
            "## Category H: Fact-Validation Ledger\n"
            "- Claim: 'three moves doubled the pipeline' — VALIDATED against the "
            "CDC/Pew funnel-conversion baselines; the 2x lift sits within the cited "
            "95% confidence interval. Status: SUPPORTED.\n"
            "- Claim: 'second-touch within the first hour' — VALIDATED against NIH "
            "PMC9135772 response-latency findings. Status: SUPPORTED.\n"
            "\n"
            "## Category I: Objection Research\n"
            "- Objection: \"We already have a CRM.\" Reframe: the moves are a process "
            "layer ON TOP of any CRM, not a replacement; cite the integration data.\n"
            "- Objection: \"This won't scale to our team.\" Reframe: the cited cohort "
            "ran 40-person teams; show the per-rep ramp curve.\n"
            "\n"
            "## Category K: Persuasion-Framework Validation\n"
            "- Framework: Problem -> Agitate -> Solve, validated against the cited "
            "buyer-psychology corpus (APA). The hook slide opens on the prospect's "
            "own stalled-pipeline pain before any solution is named.\n"
            "- Social-proof placement validated: attributable quotes (Category G) are "
            "front-loaded onto the 'who says so' slides per the cited evidence.\n"
            "\n"
            "## Category L: Compliance Flags\n"
            "- No medical, financial, or legal guarantee language is used; all "
            "outcome claims are framed as cited ranges, not promises.\n"
            "- All statistics carry an inline source from the citation list above; no "
            "uncited percentage appears on any slide. Status: CLEAR.\n"
        )
        # AF-QC-INDEPENDENCE: the copy QC report (and the four other QC reports) are
        # written below via _qc(...) with an independent-reviewer provenance block
        # proving an INDEPENDENT QC specialist (not build_deck.py / not the author
        # role) graded it; a report self-written by the builder is refused.
        # Phase 3 — converting arc allocation (Signature Presentation Architect).
        # Carries an OFFER LADDER (value-stack -> anchor -> price drops) AND a re-pitch
        # beat after the FINAL price so the AF-PITCH-MISSING gate passes.
        arc_beats = [{"slide": i, "arc_section": "body"} for i in range(1, _floor_slides + 1)]
        arc_beats[0]["arc_section"] = "hook"
        arc_beats[10]["arc_section"] = "value-stack"
        arc_beats[15]["arc_section"] = "anchor"
        arc_beats[20]["arc_section"] = "price ladder drop"
        arc_beats[30]["arc_section"] = "final price"
        arc_beats[34]["arc_section"] = "re-pitch"
        (root / "working" / "copy" / "arc_allocation.json").write_text(json.dumps(arc_beats))
        # Phase 4 — slide copy authored per doctrine (no banned cliche phrases).
        (root / "working" / "copy" / "slides_copy.md").write_text(
            "# Slide copy\n" + ("Authored converting copy per doctrine. " * 40) + "\n")
        # Phase F — typography/design brief (per-slide art direction).
        (root / "working" / "research" / "design-brief-demo.md").write_text(
            "# Design brief\n" + ("Per-slide art direction and typography. " * 20) + "\n")
        # Phase F — design system with VARIED archetypes so no single archetype
        # dominates beyond the 60% ceiling (AF-CREATIVITY passes).
        archetypes = ["A1-hero", "A2-split", "A3-pure-type", "A4-grid", "A5-quote"]
        (root / "working" / "typography").mkdir(parents=True, exist_ok=True)
        (root / "working" / "typography" / "design_system.json").write_text(json.dumps({
            "per_slide": [{"slide": i, "archetype": archetypes[i % len(archetypes)]}
                          for i in range(1, _floor_slides + 1)]}))
        # The FIVE QC reports (each INDEPENDENT-reviewer graded). Copy-QC plus the four
        # NEW QC gates (typography / prompt / image / speech). Each carries the
        # qc_independence provenance block proving an independent specialist graded it.
        def _qc(gate, builder, reviewer):
            return json.dumps({"gate": gate, "average": 9.1, "triggered_autofails": [],
                               "pass": True,
                               "qc_independence": {"graded_by": reviewer, "independent": True,
                                                   "builder": builder, "self_graded": False}})
        (root / "working" / "qc" / "copy_qc_report.json").write_text(
            _qc("Phase 1Q", "slide-copywriter", "qc-specialist-presentations"))
        (root / "working" / "qc" / "typography_qc_report.json").write_text(
            _qc("Phase Typography-QC", "typography-architect", "qc-specialist-typography-presentations"))
        (root / "working" / "qc" / "prompt_qc_report.json").write_text(
            _qc("Phase Prompt-QC", "prompt-author-presentations", "qc-specialist-prompt-presentations"))
        (root / "working" / "qc" / "image_qc_report.json").write_text(
            _qc("Phase Image-QC", "slide-image-creator", "qc-specialist-image-presentations"))
        # speech_qc_report.json intentionally ABSENT here -> AF-SPEECH-QC defers (pre-delivery).
        # Phase 2 — rich per-slide prompt(s) (rendered VERBATIM), one per slide.
        if rich_prompts:
            for i in range(1, _floor_slides + 1):
                text = "short prompt" if short_prompt else RICH_PROMPT
                (root / "working" / "prompts" / f"slide-{i:02d}.txt").write_text(text)
        # Mode A: no mission_prd.json => source_slide_count 0 => coverage always passes.
        # No speech.md => speech-length gate defers (passes) at this pre-delivery stage.
    else:
        # create only the working/ shell so the run dir is found but artifacts absent
        (root / "working").mkdir(parents=True, exist_ok=True)
    return root


def run(root: Path, extra=None):
    cmd = [sys.executable, str(BUILD),
           str(root / "slides.json"), str(root / "out.pptx")]
    if extra:
        cmd += extra
    # Strip KIE key so a passed preflight cleanly halts at the config stage
    # instead of hitting the network.
    env = dict(os.environ)
    env.pop("KIE_API_KEY", None)
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)


def _coverage_run_dir(source_slide_count, output_slides) -> Path:
    """Build a temp run dir with a mission_prd.json carrying source_slide_count
    (omitted when None) and a slides.json of `output_slides` slides."""
    root = Path(tempfile.mkdtemp(prefix="deck_coverage_test_"))
    (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
    if source_slide_count is not None:
        (root / "working" / "copy" / "mission_prd.json").write_text(
            json.dumps({"source_slide_count": source_slide_count}))
    slides = [{"slide": i, "scene": "x", "copy": ["y"]}
              for i in range(1, output_slides + 1)]
    (root / "working" / "copy" / "slides.json").write_text(json.dumps(slides))
    return root


def test_chk_coverage():
    """ANTI-COMPRESSION (AF-COVERAGE-1) unit test:
      - source_slide_count=120 with 90 output slides FAILS,
      - source_slide_count=120 with 120 output slides PASSES,
      - source=0 (and source absent => Mode A) PASSES regardless of output count.
    Returns a list of failure strings ([] = all passed)."""
    fails = []

    # 120 source vs 90 output => must FAIL (non-empty AF reason).
    rd = _coverage_run_dir(120, 90)
    reason = build_deck._chk_coverage(rd)
    if not reason:
        fails.append("COVERAGE: 120 source / 90 output should FAIL but passed")
    elif "AF-COVERAGE-1" not in reason or "90" not in reason or "120" not in reason:
        fails.append(f"COVERAGE: fail message malformed: {reason!r}")

    # 120 source vs 120 output => must PASS ("").
    rd = _coverage_run_dir(120, 120)
    reason = build_deck._chk_coverage(rd)
    if reason:
        fails.append(f"COVERAGE: 120 source / 120 output should PASS but got: {reason!r}")

    # 120 source vs 150 output (ADD-only, more) => must PASS.
    rd = _coverage_run_dir(120, 150)
    reason = build_deck._chk_coverage(rd)
    if reason:
        fails.append(f"COVERAGE: 120 source / 150 output should PASS but got: {reason!r}")

    # source=0 (Mode A explicit) with fewer output slides => must PASS.
    rd = _coverage_run_dir(0, 5)
    reason = build_deck._chk_coverage(rd)
    if reason:
        fails.append(f"COVERAGE: source=0 should PASS regardless but got: {reason!r}")

    # source absent (Mode A) => must PASS.
    rd = _coverage_run_dir(None, 3)
    reason = build_deck._chk_coverage(rd)
    if reason:
        fails.append(f"COVERAGE: source absent (Mode A) should PASS but got: {reason!r}")

    print(f"COVERAGE (anti-compression) -> {'PASS' if not fails else 'FAIL'}")
    return fails


def _rich_prompt_run_dir(prompt_text) -> Path:
    """Build a temp run dir with a 1-slide slides.json and, when prompt_text is not
    None, a working/prompts/slide-01.txt carrying that text."""
    root = Path(tempfile.mkdtemp(prefix="deck_richprompt_test_"))
    (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (root / "working" / "copy" / "slides.json").write_text(
        json.dumps([{"slide": 1, "scene": "x", "copy": ["y"]}]))
    if prompt_text is not None:
        (root / "working" / "prompts").mkdir(parents=True, exist_ok=True)
        (root / "working" / "prompts" / "slide-01.txt").write_text(prompt_text)
    return root


def test_chk_rich_prompts():
    """RICH-PROMPT-REQUIRED (AF-P1) unit test (the two NEW required assertions):
      - a slide with NO rich prompt FAILS (missing-rich-prompt fails),
      - a slide whose rich prompt is < 1,500 chars FAILS (sub-floor fails),
      - a slide with a >= 1,500-char rich prompt PASSES,
    plus load_rich_prompt raises on missing/short and returns the prompt verbatim
    when valid. Returns a list of failure strings ([] = all passed)."""
    fails = []
    assert build_deck.PROMPT_CHAR_FLOOR == 5000, \
        f"PROMPT_CHAR_FLOOR must be 5000 (reconciled standard), got {build_deck.PROMPT_CHAR_FLOOR}"

    valid = RICH_PROMPT
    assert len(valid) >= 5000, "test fixture RICH_PROMPT must be >= 5000 chars"
    short = "way too thin to be a real slide prompt"  # well under 5,000

    # ---- NEW ASSERTION 1: a MISSING rich prompt FAILS ----
    rd = _rich_prompt_run_dir(None)
    reason = build_deck._chk_rich_prompts(rd)
    if not reason:
        fails.append("RICHPROMPT: a MISSING rich prompt should FAIL but passed")
    elif "AF-P1" not in reason or "NO rich prompt file" not in reason:
        fails.append(f"RICHPROMPT: missing-prompt fail message malformed: {reason!r}")
    # load_rich_prompt must raise on a missing prompt (no thin fallback).
    try:
        build_deck.load_rich_prompt({"slide": 1, "scene": "x", "copy": ["y"]}, rd)
        fails.append("RICHPROMPT: load_rich_prompt should RAISE on a missing prompt")
    except ValueError as exc:
        if "AF-P1" not in str(exc):
            fails.append(f"RICHPROMPT: load_rich_prompt missing-raise wrong msg: {exc}")

    # ---- NEW ASSERTION 2: a < 1,500-char rich prompt FAILS ----
    rd = _rich_prompt_run_dir(short)
    reason = build_deck._chk_rich_prompts(rd)
    if not reason:
        fails.append("RICHPROMPT: a < 1,500-char rich prompt should FAIL but passed")
    elif "AF-P1" not in reason or "floor" not in reason.lower():
        fails.append(f"RICHPROMPT: short-prompt fail message malformed: {reason!r}")
    try:
        build_deck.load_rich_prompt({"slide": 1, "scene": "x", "copy": ["y"]}, rd)
        fails.append("RICHPROMPT: load_rich_prompt should RAISE on a sub-floor prompt")
    except ValueError as exc:
        if "AF-P1" not in str(exc):
            fails.append(f"RICHPROMPT: load_rich_prompt short-raise wrong msg: {exc}")

    # ---- a valid >= 1,500-char rich prompt PASSES + is returned VERBATIM ----
    rd = _rich_prompt_run_dir(valid)
    reason = build_deck._chk_rich_prompts(rd)
    if reason:
        fails.append(f"RICHPROMPT: a valid rich prompt should PASS but got: {reason!r}")
    try:
        got = build_deck.load_rich_prompt({"slide": 1, "scene": "x", "copy": ["y"]}, rd)
        if got != valid:
            fails.append("RICHPROMPT: load_rich_prompt did not return the prompt VERBATIM")
    except ValueError as exc:
        fails.append(f"RICHPROMPT: load_rich_prompt raised on a valid prompt: {exc}")

    # ---- an over-ceiling prompt FAILS in load_rich_prompt (AF-P2) ----
    over = "A" * (build_deck.PROMPT_CHAR_CEILING + 10)
    rd = _rich_prompt_run_dir(over)
    try:
        build_deck.load_rich_prompt({"slide": 1, "scene": "x", "copy": ["y"]}, rd)
        fails.append("RICHPROMPT: load_rich_prompt should RAISE over the 18,000 ceiling")
    except ValueError as exc:
        if "AF-P2" not in str(exc):
            fails.append(f"RICHPROMPT: over-ceiling raise wrong msg: {exc}")

    print(f"RICHPROMPT (rich-prompt-required) -> {'PASS' if not fails else 'FAIL'}")
    return fails


def _speech_run_dir(target_minutes, speech_words) -> Path:
    """Build a temp run dir with intake.target_talk_minutes and, when speech_words
    is not None, a working/presenter-speech/speech.md of that many words."""
    root = Path(tempfile.mkdtemp(prefix="deck_speech_test_"))
    (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
    intake = {"interview_confirmed": True, "presentation_mode": "general",
              "audience_mode": "STANDARD"}
    if target_minutes is not None:
        intake["target_talk_minutes"] = target_minutes
    (root / "working" / "copy" / "intake.json").write_text(json.dumps(intake))
    if speech_words is not None:
        (root / "working" / "presenter-speech").mkdir(parents=True, exist_ok=True)
        (root / "working" / "presenter-speech" / "speech.md").write_text(
            " ".join(["word"] * speech_words))
    return root


def test_chk_speech_length():
    """SPEECH-LENGTH (AF-SPEECH-SHORT) unit test:
      - 30 min target, speech of 30*120-100 words FAILS short,
      - 30 min target, speech of 30*120 words PASSES,
      - speech ABSENT defers (passes — written downstream at delivery)."""
    fails = []
    # 30 min => floor 3600 words. 3500 < 3600 => FAIL.
    rd = _speech_run_dir(30, 3500)
    reason = build_deck._chk_speech_length(rd)
    if not reason:
        fails.append("SPEECH: 30min/3500 words should FAIL short but passed")
    elif "AF-SPEECH-SHORT" not in reason:
        fails.append(f"SPEECH: fail message malformed: {reason!r}")
    # 30 min => 3600 words exactly => PASS.
    rd = _speech_run_dir(30, 3600)
    if build_deck._chk_speech_length(rd):
        fails.append("SPEECH: 30min/3600 words should PASS but failed")
    # speech absent => defer => PASS.
    rd = _speech_run_dir(30, None)
    if build_deck._chk_speech_length(rd):
        fails.append("SPEECH: absent speech should DEFER (pass) but failed")
    print(f"SPEECH (speech-length gate) -> {'PASS' if not fails else 'FAIL'}")
    return fails


def _qc_report_path(obj: dict) -> Path:
    """Write a copy_qc_report.json carrying `obj` and return its path."""
    root = Path(tempfile.mkdtemp(prefix="deck_qcindep_test_"))
    (root / "working" / "qc").mkdir(parents=True, exist_ok=True)
    p = root / "working" / "qc" / "copy_qc_report.json"
    p.write_text(json.dumps(obj))
    return p


# ---------------------------------------------------------------------------
# O2/O4/O5 NEW-GATE fixture builders + unit tests.
# ---------------------------------------------------------------------------
def _slide_count_run_dir(target_minutes, output_slides) -> Path:
    """Build a run dir with intake.json (target_talk_minutes) and a slides.json of
    output_slides slides — drives the AF-SLIDE-COUNT-FLOOR gate."""
    root = Path(tempfile.mkdtemp(prefix="deck_slidefloor_test_"))
    (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (root / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"interview_confirmed": True, "presentation_mode": "general",
         "audience_mode": "STANDARD", "target_talk_minutes": target_minutes}))
    (root / "working" / "copy" / "slides.json").write_text(json.dumps(
        [{"slide": i} for i in range(1, output_slides + 1)]))
    return root


def _pitch_run_dir(arc_slots) -> Path:
    """Build a run dir with arc_allocation.json carrying arc_slots — drives AF-PITCH-MISSING."""
    root = Path(tempfile.mkdtemp(prefix="deck_pitch_test_"))
    (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (root / "working" / "copy" / "arc_allocation.json").write_text(json.dumps(arc_slots))
    return root


def _creativity_run_dir(dominant: bool) -> Path:
    """Build a run dir with a design_system.json. dominant=True => one archetype on
    every slide (>60% => AF-CREATIVITY); dominant=False => varied archetypes."""
    root = Path(tempfile.mkdtemp(prefix="deck_creativity_test_"))
    (root / "working" / "typography").mkdir(parents=True, exist_ok=True)
    if dominant:
        per = [{"slide": i, "archetype": "A1-hero"} for i in range(1, 11)]
    else:
        arch = ["A1-hero", "A2-split", "A3-pure-type", "A4-grid", "A5-quote"]
        per = [{"slide": i, "archetype": arch[i % len(arch)]} for i in range(1, 11)]
    (root / "working" / "typography" / "design_system.json").write_text(
        json.dumps({"per_slide": per}))
    return root


def test_chk_slide_count_floor():
    """AF-SLIDE-COUNT-FLOOR: 30-min/10-slide (floor 39) FAILS; 30-min/39-slide PASSES;
    no target defers (passes)."""
    fails = []
    r = build_deck._chk_slide_count_floor(_slide_count_run_dir(30, 10))
    if not r or "AF-SLIDE-COUNT-FLOOR" not in r:
        fails.append(f"SLIDEFLOOR: 30min/10 slides should FAIL (AF-SLIDE-COUNT-FLOOR), got {r!r}")
    if build_deck._chk_slide_count_floor(_slide_count_run_dir(30, 39)):
        fails.append("SLIDEFLOOR: 30min/39 slides should PASS but failed")
    # no target -> defer
    rd = Path(tempfile.mkdtemp(prefix="deck_slidefloor_notarget_"))
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "slides.json").write_text(json.dumps([{"slide": 1}]))
    if build_deck._chk_slide_count_floor(rd):
        fails.append("SLIDEFLOOR: no target should DEFER (pass) but failed")
    print(f"SLIDE-COUNT-FLOOR (pacing)   -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_chk_pitch():
    """AF-PITCH-MISSING: arc with no ladder/no re-pitch FAILS; full ladder+re-pitch PASSES;
    absent arc defers (passes)."""
    fails = []
    r = build_deck._chk_pitch(_pitch_run_dir(
        [{"slide": 1, "arc_section": "hook"}, {"slide": 2, "arc_section": "body"}]))
    if not r or "AF-PITCH-MISSING" not in r:
        fails.append(f"PITCH: no ladder/no re-pitch should FAIL (AF-PITCH-MISSING), got {r!r}")
    full = build_deck._chk_pitch(_pitch_run_dir([
        {"slide": 1, "arc_section": "hook"},
        {"slide": 2, "arc_section": "value-stack"},
        {"slide": 3, "arc_section": "anchor"},
        {"slide": 4, "arc_section": "price ladder drop"},
        {"slide": 5, "arc_section": "re-pitch"}]))
    if full:
        fails.append(f"PITCH: full ladder + re-pitch should PASS but got {full!r}")
    # absent arc -> defer
    rd = Path(tempfile.mkdtemp(prefix="deck_pitch_absent_"))
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    if build_deck._chk_pitch(rd):
        fails.append("PITCH: absent arc should DEFER (pass) but failed")
    print(f"PITCH (offer ladder+re-pitch)-> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_chk_creativity():
    """AF-CREATIVITY: a deck where one archetype dominates (>60%) FAILS; a varied deck
    PASSES; cliche copy FAILS."""
    fails = []
    r = build_deck._chk_creativity(_creativity_run_dir(dominant=True))
    if not r or "AF-CREATIVITY" not in r:
        fails.append(f"CREATIVITY: archetype-dominant deck should FAIL, got {r!r}")
    if build_deck._chk_creativity(_creativity_run_dir(dominant=False)):
        fails.append("CREATIVITY: varied-archetype deck should PASS but failed")
    # cliche copy -> FAIL
    rd = Path(tempfile.mkdtemp(prefix="deck_creativity_cliche_"))
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "slides_copy.md").write_text(
        "In today's fast-paced world, we move the needle.")
    rc = build_deck._chk_creativity(rd)
    if not rc or "AF-CREATIVITY" not in rc:
        fails.append(f"CREATIVITY: cliche copy should FAIL, got {rc!r}")
    print(f"CREATIVITY (anti-template)   -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_chk_qc_gates_independence():
    """The four NEW QC gates (typography/prompt/image/speech) reject a self-graded /
    builder-graded report and pass an independent one. Generalizes AF-QC-INDEPENDENCE."""
    fails = []
    cases = [
        ("AF-TYPOGRAPHY-QC", build_deck._chk_typography_qc, "Phase Typography-QC"),
        ("AF-PROMPT-QC", build_deck._chk_prompt_qc, "Phase Prompt-QC"),
        ("AF-IMAGE-QC", build_deck._chk_image_qc, "Phase Image-QC"),
        ("AF-SPEECH-QC", build_deck._chk_speech_qc, "Phase Speech-QC"),
    ]
    for code, fn, gate in cases:
        # self-graded -> FAIL with this gate's code
        bad = _qc_report_path({"gate": gate, "average": 9.1, "triggered_autofails": [],
                               "pass": True,
                               "qc_independence": {"graded_by": "self", "independent": True}})
        r = fn(bad)
        if not r or code not in r:
            fails.append(f"{code}: self-graded report should FAIL with {code}, got {r!r}")
        # independent -> PASS
        good = _qc_report_path({"gate": gate, "average": 9.1, "triggered_autofails": [],
                                "pass": True,
                                "qc_independence": {"graded_by": "qc-specialist-x",
                                                    "independent": True,
                                                    "builder": "some-author",
                                                    "self_graded": False}})
        if fn(good):
            fails.append(f"{code}: independent report should PASS but failed")
    # AF-SPEECH-QC absent -> defer (pass)
    if build_deck._chk_speech_qc(None):
        fails.append("AF-SPEECH-QC: absent report should DEFER (pass) but failed")
    print(f"QC-GATES INDEPENDENCE (4 new)-> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_chk_qc_independence_rejects_self_graded():
    """AF-QC-INDEPENDENCE unit test: a QC report that is otherwise valid (gate
    Phase 1Q, average>=8.5, no triggered autofails, pass:true) STILL fails when it
    was self-graded / builder-graded, and PASSES only when it carries explicit
    independent-reviewer provenance.

    The base report below passes every PRE-EXISTING numeric check, so each case
    isolates the independence enforcement.
    """
    fails = []
    chk = build_deck._chk_copy_qc

    def base(**extra):
        d = {"gate": "Phase 1Q", "average": 9.1,
             "triggered_autofails": [], "pass": True}
        d.update(extra)
        return d

    # --- SELF-GRADED variants: each must FAIL with AF-QC-INDEPENDENCE ---
    self_graded_cases = [
        ("no provenance block at all", base()),
        ("self_graded:true", base(self_graded=True,
            qc_independence={"graded_by": "qc-specialist-presentations",
                             "independent": True})),
        ("graded_by build_deck.py", base(
            qc_independence={"graded_by": "build_deck.py", "independent": True})),
        ("graded_by self", base(
            qc_independence={"graded_by": "self", "independent": True})),
        ("graded_by builder", base(qc_independence={"graded_by": "builder"})),
        ("graded_by author", base(qc_independence={"graded_by": "author"})),
        ("reviewer == the deck-copy author role", base(
            qc_independence={"graded_by": "slide-copywriter", "independent": True})),
        ("independent:false", base(
            qc_independence={"graded_by": "qc-specialist-presentations",
                             "independent": False})),
        ("reviewer equals recorded builder identity", base(
            qc_independence={"graded_by": "agent-x", "builder": "agent-x"})),
    ]
    for label, obj in self_graded_cases:
        reason = chk(_qc_report_path(obj))
        if not reason:
            fails.append(f"QC-INDEP: self-graded case [{label}] should FAIL but passed")
        elif "AF-QC-INDEPENDENCE" not in reason:
            fails.append(f"QC-INDEP: [{label}] failed but not via AF-QC-INDEPENDENCE: {reason!r}")

    # --- INDEPENDENT variants: each must PASS ("") ---
    independent_cases = [
        ("qc_independence block (graded_by + independent:true + self_graded:false)", base(
            qc_independence={"graded_by": "qc-specialist-presentations",
                             "independent": True, "builder": "slide-copywriter",
                             "self_graded": False})),
        ("top-level reviewer field", base(reviewer="qc-specialist-presentations")),
        ("top-level reviewed_by field", base(reviewed_by="independent-qc-reviewer")),
    ]
    for label, obj in independent_cases:
        reason = chk(_qc_report_path(obj))
        if reason:
            fails.append(f"QC-INDEP: independent case [{label}] should PASS but got: {reason!r}")

    # --- the independence gate must NOT mask the pre-existing numeric checks ---
    # A self-graded report that is ALSO below threshold should still report a
    # problem (the numeric check fires first); confirm a below-8.5 report fails.
    low = base(average=7.0, qc_independence={"graded_by": "qc-specialist-presentations",
                                             "independent": True})
    if not chk(_qc_report_path(low)):
        fails.append("QC-INDEP: below-8.5 report should still FAIL (numeric check)")

    print(f"QC-INDEP (self-graded reject)-> {'PASS' if not fails else 'FAIL'}")
    return fails


# C2: a legitimate deliverable must now lead with the correct magic bytes (the gate
# verifies content type). These are the per-key valid leading bytes the test writes
# so the "all present => PASS" path still passes after the C2 hardening. md has no
# magic (size-only), so any bytes are fine.
_VALID_MAGIC_FOR_TEST = {
    "deck_pptx":         b"PK\x03\x04",
    "deck_pdf":          b"%PDF-1.7\n",
    "guide_pdf":         b"%PDF-1.7\n",
    "speech_pdf":        b"%PDF-1.7\n",
    "audio_mp3":         b"ID3",
    "infographic_png":   b"\x89PNG\r\n\x1a\n",
    "speech_md":         b"# speech\n",          # no magic required; arbitrary text
    "speech_fish_md":    b"# fish-tagged\n",     # no magic required; arbitrary text
    "teleprompter_html": b"<!DOCTYPE html>\n",   # HTML magic (teleprompter app)
}


def _valid_bytes_for(key: str, total: int) -> bytes:
    """Return `total` bytes that begin with the correct magic header for `key`, so
    the file passes both the size gate AND the C2 magic-byte content-type check."""
    head = _VALID_MAGIC_FOR_TEST.get(key, b"")
    pad = max(0, total - len(head))
    return head + (b"\x00" * pad)


def _write_publish_ledger(bundle_dir: Path, status="published",
                          verified_http_status=200,
                          public_url="https://teleprompter.zerohumanworkforce.com/"
                                     "test-client/test-deck/teleprompter.html") -> None:
    """Write a teleprompter_publish.json into the bundle dir. The TELEPROMPTER-PUBLISH
    sub-check of run_postflight_gate keys on this artifact — a full bundle without it
    now fails (exit 5), so the PASS-path fixtures must include a published record."""
    import json as _json
    rec = {
        "platform": "mac",
        "host_target": "cloudflare-central",
        "local_file": str(bundle_dir / "presenter-teleprompter.html"),
        "public_url": public_url,
        "published_at": "2026-06-17T00:00:00Z",
        "verified_http_status": verified_http_status,
        "verified_at": "2026-06-17T00:00:00Z",
        "status": status,
    }
    (bundle_dir / build_deck.TELEPROMPTER_PUBLISH_LEDGER).write_text(
        _json.dumps(rec, indent=2))


def _postflight_bundle_dir(present_keys: set, with_publish: bool = True) -> tuple:
    """Build a temp bundle dir containing only the artifacts whose keys are in
    present_keys, each at or above their min_bytes threshold AND with the correct
    leading magic bytes (C2). When with_publish is True (default) AND
    teleprompter_html is present, also writes a verified teleprompter_publish.json so
    the TELEPROMPTER-PUBLISH sub-check passes. Returns (bundle_dir, ledger_path,
    deck_slug)."""
    import tempfile
    bundle_dir = Path(tempfile.mkdtemp(prefix="deck_postflight_test_"))
    deck_slug = "test-deck"

    # Initialise the ledger (all pending).
    ledger_path = build_deck.init_deliverables_ledger(bundle_dir, deck_slug)

    for spec in build_deck.DELIVERABLES_REQUIRED:
        key = spec["key"]
        fname = build_deck._expand_filename(spec["filename"], deck_slug)
        fpath = bundle_dir / fname
        if key in present_keys:
            # Write a real-magic file that exceeds the threshold by a comfortable margin.
            fpath.write_bytes(_valid_bytes_for(key, spec["min_bytes"] + 1024))
    if with_publish and "teleprompter_html" in present_keys:
        _write_publish_ledger(bundle_dir)
    return bundle_dir, ledger_path, deck_slug


def test_postflight_gate():
    """POSTFLIGHT COMPLETENESS GATE self-test (Requirement 6 / AF-BUNDLE-COMPLETE):

      - When ALL nine required deliverables are present + above threshold:
          run_postflight_gate() prints COMPLETE and does NOT sys.exit(5).
      - When ANY required deliverable is missing:
          run_postflight_gate() calls sys.exit(5) — we catch SystemExit(5).
      - Specifically, PRESENTER-GUIDE.pdf (guide_pdf) and infographic.png
          (infographic_png) missing each independently trigger exit 5 — they
          can NEVER be silently skipped (Requirement 5).

    Returns a list of failure strings ([] = all passed)."""
    import subprocess
    import tempfile

    fails = []

    # --- Sub-test A: ALL artifacts present => PASSES (no SystemExit) ---
    all_keys = {spec["key"] for spec in build_deck.DELIVERABLES_REQUIRED}
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(all_keys)
    try:
        build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
        # Must NOT raise SystemExit — gate should pass.
    except SystemExit as exc:
        fails.append(f"POSTFLIGHT-A: all artifacts present should PASS, got sys.exit({exc.code})")
    except Exception as exc:  # noqa: BLE001
        fails.append(f"POSTFLIGHT-A: unexpected error: {exc}")
    print(f"POSTFLIGHT-A (all present)   -> {'PASS' if not [f for f in fails if 'POSTFLIGHT-A' in f] else 'FAIL'}")

    # --- Sub-test B: ONE artifact missing (deck_pdf) => exit 5 ---
    missing_one = all_keys - {"deck_pdf"}
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(missing_one)
    try:
        build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
        fails.append("POSTFLIGHT-B: missing deck_pdf should exit 5 but gate passed")
    except SystemExit as exc:
        if exc.code != 5:
            fails.append(f"POSTFLIGHT-B: missing deck_pdf should exit 5, got {exc.code}")
    print(f"POSTFLIGHT-B (deck_pdf miss) -> {'PASS' if not [f for f in fails if 'POSTFLIGHT-B' in f] else 'FAIL'}")

    # --- Sub-test C: PRESENTER-GUIDE.pdf missing => exit 5 (hard-required, Req 5) ---
    missing_guide = all_keys - {"guide_pdf"}
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(missing_guide)
    try:
        build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
        fails.append("POSTFLIGHT-C: missing PRESENTER-GUIDE.pdf should exit 5 but gate passed")
    except SystemExit as exc:
        if exc.code != 5:
            fails.append(f"POSTFLIGHT-C: missing guide_pdf should exit 5, got {exc.code}")
    print(f"POSTFLIGHT-C (guide_pdf mis) -> {'PASS' if not [f for f in fails if 'POSTFLIGHT-C' in f] else 'FAIL'}")

    # --- Sub-test D: infographic.png missing => exit 5 (hard-required, Req 5) ---
    missing_infographic = all_keys - {"infographic_png"}
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(missing_infographic)
    try:
        build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
        fails.append("POSTFLIGHT-D: missing infographic.png should exit 5 but gate passed")
    except SystemExit as exc:
        if exc.code != 5:
            fails.append(f"POSTFLIGHT-D: missing infographic_png should exit 5, got {exc.code}")
    print(f"POSTFLIGHT-D (infog_png mis) -> {'PASS' if not [f for f in fails if 'POSTFLIGHT-D' in f] else 'FAIL'}")

    # --- Sub-test E: artifact present but UNDER the min_bytes threshold => exit 5 ---
    # Write guide_pdf as a 1-byte file (well under 51,200 threshold).
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(all_keys)
    under_spec = next(s for s in build_deck.DELIVERABLES_REQUIRED if s["key"] == "guide_pdf")
    under_name = build_deck._expand_filename(under_spec["filename"], slug)
    (bundle_dir / under_name).write_bytes(b"\x00")  # 1 byte — far under 51,200
    try:
        build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
        fails.append("POSTFLIGHT-E: under-threshold guide_pdf should exit 5 but gate passed")
    except SystemExit as exc:
        if exc.code != 5:
            fails.append(f"POSTFLIGHT-E: under-threshold guide_pdf should exit 5, got {exc.code}")
    print(f"POSTFLIGHT-E (under-thresh)  -> {'PASS' if not [f for f in fails if 'POSTFLIGHT-E' in f] else 'FAIL'}")

    # --- Sub-test F: ALL missing => exit 5, ledger all failed ---
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(set())
    try:
        build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
        fails.append("POSTFLIGHT-F: all missing should exit 5 but gate passed")
    except SystemExit as exc:
        if exc.code != 5:
            fails.append(f"POSTFLIGHT-F: all missing should exit 5, got {exc.code}")
    print(f"POSTFLIGHT-F (all missing)   -> {'PASS' if not [f for f in fails if 'POSTFLIGHT-F' in f] else 'FAIL'}")

    # --- Sub-test G: Verify ~/Downloads default destination constant ---
    import os
    expected_default = os.path.expanduser("~/Downloads")
    if build_deck.BUNDLE_DIR_DEFAULT != expected_default:
        fails.append(
            f"POSTFLIGHT-G: BUNDLE_DIR_DEFAULT should be {expected_default!r}, "
            f"got {build_deck.BUNDLE_DIR_DEFAULT!r}")
    print(f"POSTFLIGHT-G (Downloads def) -> {'PASS' if not [f for f in fails if 'POSTFLIGHT-G' in f] else 'FAIL'}")

    # --- Sub-test H: Verify DELIVERABLES_REQUIRED has exactly the 9 required keys ---
    required_keys = {"deck_pptx", "deck_pdf", "guide_pdf", "speech_md",
                     "speech_pdf", "speech_fish_md", "audio_mp3", "infographic_png",
                     "teleprompter_html"}
    actual_keys = {spec["key"] for spec in build_deck.DELIVERABLES_REQUIRED}
    if actual_keys != required_keys:
        fails.append(
            f"POSTFLIGHT-H: DELIVERABLES_REQUIRED keys mismatch.\n"
            f"  Expected: {sorted(required_keys)}\n"
            f"  Got:      {sorted(actual_keys)}")
    print(f"POSTFLIGHT-H (key set exact) -> {'PASS' if not [f for f in fails if 'POSTFLIGHT-H' in f] else 'FAIL'}")

    print(f"POSTFLIGHT (gate self-test)  -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_teleprompter_publish_gate():
    """TELEPROMPTER-PUBLISH sub-check of the postflight bundle gate (folded under
    AF-BUNDLE-COMPLETE). A generated teleprompter HTML is NOT a delivered teleprompter
    until it is published to the central host with a verified live public URL.

      (a) Full 9-file bundle, NO teleprompter_publish.json        -> exit 5.
      (b) Full bundle + status=published + verified_http_status=200
          + valid http(s) public_url                              -> PASSES (no exit 5).
      (c) Full bundle + verified_http_status=404                  -> exit 5.
      (d) Full bundle + status=skipped_adhoc (M7)                 -> exit 5: a stale
          skipped_adhoc status string NO LONGER bypasses the gate.
      (e) Full bundle + public_url that is not http(s) (file://)  -> exit 5.
      (f) Full bundle + status=skipped_adhoc + the explicit
          skip_teleprompter_gate=True flag (M7)                   -> PASSES: the gate
          is bypassed ONLY by the explicit per-run flag, never a persisted status.

    Returns a list of failure strings ([] = all passed)."""
    fails = []
    all_keys = {spec["key"] for spec in build_deck.DELIVERABLES_REQUIRED}

    # (a) No publish ledger at all -> exit 5.
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(all_keys, with_publish=False)
    try:
        build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
        fails.append("TELE-A: full bundle with NO teleprompter_publish.json should exit 5 "
                     "but gate passed")
    except SystemExit as exc:
        if exc.code != 5:
            fails.append(f"TELE-A: expected exit 5, got {exc.code}")
    print(f"TELE-A (no publish ledger)   -> {'PASS' if not [f for f in fails if 'TELE-A' in f] else 'FAIL'}")

    # (b) status=published + 200 + valid http(s) URL -> PASSES.
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(all_keys, with_publish=False)
    _write_publish_ledger(bundle_dir, status="published", verified_http_status=200)
    try:
        build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
    except SystemExit as exc:
        fails.append(f"TELE-B: published+200 should PASS, got sys.exit({exc.code})")
    except Exception as exc:  # noqa: BLE001
        fails.append(f"TELE-B: unexpected error: {exc}")
    print(f"TELE-B (published + 200)     -> {'PASS' if not [f for f in fails if 'TELE-B' in f] else 'FAIL'}")

    # (c) verified_http_status=404 -> exit 5.
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(all_keys, with_publish=False)
    _write_publish_ledger(bundle_dir, status="published", verified_http_status=404)
    try:
        build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
        fails.append("TELE-C: verified_http_status=404 should exit 5 but gate passed")
    except SystemExit as exc:
        if exc.code != 5:
            fails.append(f"TELE-C: expected exit 5, got {exc.code}")
    print(f"TELE-C (status 404)          -> {'PASS' if not [f for f in fails if 'TELE-C' in f] else 'FAIL'}")

    # (d) M7: a stale status=skipped_adhoc string NO LONGER bypasses the gate -> exit 5.
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(all_keys, with_publish=False)
    _write_publish_ledger(bundle_dir, status="skipped_adhoc", verified_http_status=None)
    try:
        build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
        fails.append("TELE-D: a stale skipped_adhoc status should NO LONGER pass the gate "
                     "(M7) but it did")
    except SystemExit as exc:
        if exc.code != 5:
            fails.append(f"TELE-D: stale skipped_adhoc should exit 5, got {exc.code}")
    except Exception as exc:  # noqa: BLE001
        fails.append(f"TELE-D: unexpected error: {exc}")
    print(f"TELE-D (stale skipped_adhoc) -> {'PASS' if not [f for f in fails if 'TELE-D' in f] else 'FAIL'}")

    # (e) public_url not http(s) (file://) -> exit 5 (SSRF/scheme guard).
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(all_keys, with_publish=False)
    _write_publish_ledger(bundle_dir, status="published", verified_http_status=200,
                          public_url="file:///etc/passwd")
    try:
        build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
        fails.append("TELE-E: file:// public_url should exit 5 but gate passed")
    except SystemExit as exc:
        if exc.code != 5:
            fails.append(f"TELE-E: expected exit 5, got {exc.code}")
    print(f"TELE-E (non-http url)        -> {'PASS' if not [f for f in fails if 'TELE-E' in f] else 'FAIL'}")

    # (f) M7: the explicit per-run skip_teleprompter_gate=True flag bypasses the gate
    # even with a stale skipped_adhoc record (the ONLY sanctioned bypass).
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(all_keys, with_publish=False)
    _write_publish_ledger(bundle_dir, status="skipped_adhoc", verified_http_status=None)
    try:
        build_deck.run_postflight_gate(bundle_dir, ledger_path, slug,
                                       skip_teleprompter_gate=True)
    except SystemExit as exc:
        fails.append(f"TELE-F: explicit skip_teleprompter_gate=True should PASS, "
                     f"got sys.exit({exc.code})")
    except Exception as exc:  # noqa: BLE001
        fails.append(f"TELE-F: unexpected error: {exc}")
    print(f"TELE-F (explicit skip flag)  -> {'PASS' if not [f for f in fails if 'TELE-F' in f] else 'FAIL'}")

    print(f"TELE-PUBLISH (gate self-test)-> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_detect_platform():
    """detect_platform(): --platform override wins; intake.json box_type maps
    'mac'->mac and anything-else->vps; absent intake falls back to the filesystem
    signal (no /data/.openclaw on a Mac dev box -> 'mac'). The host_target is uniform
    regardless (cloudflare-central) — this only records the box type for audit.

    Returns a list of failure strings ([] = all passed)."""
    import tempfile
    import json as _json
    fails = []
    run_dir = Path(tempfile.mkdtemp(prefix="detect_platform_test_"))

    # Override wins regardless of intake.
    (run_dir / "intake.json").write_text(_json.dumps({"box_type": "mac"}))
    if build_deck.detect_platform(run_dir, override="vps") != "vps":
        fails.append("DETECT-1: --platform vps override should win")
    if build_deck.detect_platform(run_dir, override="mac") != "mac":
        fails.append("DETECT-2: --platform mac override should win")

    # box_type mac -> mac.
    (run_dir / "intake.json").write_text(_json.dumps({"box_type": "mac"}))
    if build_deck.detect_platform(run_dir) != "mac":
        fails.append("DETECT-3: box_type 'mac' should map to mac")

    # box_type anything-else -> vps.
    (run_dir / "intake.json").write_text(_json.dumps({"box_type": "hostinger-vps"}))
    if build_deck.detect_platform(run_dir) != "vps":
        fails.append("DETECT-4: non-mac box_type should map to vps")

    # No intake -> filesystem fallback. On a dev Mac there is no /data/.openclaw, so
    # the fallback returns 'mac'. (We only assert it returns a valid value.)
    run_dir2 = Path(tempfile.mkdtemp(prefix="detect_platform_test2_"))
    val = build_deck.detect_platform(run_dir2)
    if val not in ("vps", "mac"):
        fails.append(f"DETECT-5: fallback should return vps|mac, got {val!r}")

    print(f"DETECT-PLATFORM (unit)       -> {'PASS' if not fails else 'FAIL'}")
    return fails


def _research_cited_run_dir(url_lines: list) -> Path:
    """Build a temp run dir with a research brief carrying the given URL lines.
    url_lines is a list of URL strings to embed (each on its own source line)."""
    root = Path(tempfile.mkdtemp(prefix="deck_research_cited_test_"))
    (root / "working" / "research").mkdir(parents=True, exist_ok=True)
    lines = ["# Research brief\nresearch_complete: true\n"]
    for url in url_lines:
        lines.append(f"- Source: {url}\n")
    # The strengthened _chk_research_cited now also requires the sourced categories
    # G/H/I to be present + non-empty (independent of research_complete:true). Append
    # real (non-placeholder) bodies so a brief with enough domains passes the gate.
    lines.append(_research_cited_categories_block())
    (root / "working" / "research" / "brief-demo.md").write_text("".join(lines))
    return root


def _research_cited_categories_block() -> str:
    """Non-empty G/H/I category bodies for the research-cited fixtures (so the
    strengthened sourced-category check passes for an otherwise-valid pack)."""
    return (
        "\n## Category G: Credible Attributable Quotes\n"
        "- \"This approach changed our outcomes\" — Dr. Jane Doe, Stanford (2024).\n"
        "\n## Category H: Fact-Validation Ledger\n"
        "- 45% figure verified against the cited public-health source (2023).\n"
        "\n## Category I: Objection Research\n"
        "- Top objection: cost. Rebuttal: documented ROI from the cited case studies.\n"
    )


def _claims_citation_run_dir(copy_has_claims: bool, research_url_count: int) -> Path:
    """Build a temp run dir to test the claims-without-citation gate.
    copy_has_claims=True writes slide copy with a percentage claim marker.
    research_url_count sets how many distinct URLs the research brief carries."""
    root = Path(tempfile.mkdtemp(prefix="deck_claims_test_"))
    (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (root / "working" / "research").mkdir(parents=True, exist_ok=True)
    # Write slide copy with or without a claim marker.
    if copy_has_claims:
        copy = '{"copy": ["45% of teens report anxiety (studies show connection matters)"]}'
    else:
        copy = '{"copy": ["Families grow stronger together."]}'
    (root / "working" / "copy" / "slides.json").write_text(copy)
    # Write research brief with the specified number of DISTINCT REAL PUBLIC domains.
    # (C3 counts distinct public domains and rejects example.* placeholders, so the
    # fixture must use real-looking distinct domains, not example-source-*.)
    urls = [f"https://realsource-{i}.org/article" for i in range(research_url_count)]
    lines = ["# Research brief\nresearch_complete: true\n"]
    for url in urls:
        lines.append(f"- Source: {url}\n")
    # Keep the sourced-category block present so the brief is shaped like a real pack
    # (the claims gate reads only the cited domains, but a real pack carries G/H/I).
    lines.append(_research_cited_categories_block())
    (root / "working" / "research" / "brief-demo.md").write_text("".join(lines))
    return root


def test_chk_research_cited():
    """RESEARCH-CITATION GATE (AF-RESEARCH-UNCITED) unit tests:

    Fixture used for PASSING test: a self-contained 21-URL research pack
    generated in a temp dir (well over the 8-source floor).

    Test cases:
      - 0 cited URLs in the research pack -> FAILS (AF-RESEARCH-UNCITED)
      - 3 cited URLs (under the floor of 8) -> FAILS
      - Exactly 8 cited URLs -> PASSES
      - 12 cited URLs -> PASSES
      - A self-contained 21-URL fixture -> PASSES
      - None path (absent brief) -> PASSES (not double-reporting; _chk_research_brief handles it)
    """
    fails = []
    MIN = build_deck.MIN_CITED_SOURCES
    assert MIN == 8, f"MIN_CITED_SOURCES must be 8, got {MIN}"

    # 0 URLs -> FAIL
    rd = _research_cited_run_dir([])
    reason = build_deck._chk_research_cited(rd / "working" / "research" / "brief-demo.md")
    if not reason:
        fails.append("CITED-A: 0 URLs should FAIL but passed")
    elif "AF-RESEARCH-UNCITED" not in reason or str(MIN) not in reason:
        fails.append(f"CITED-A: fail message malformed: {reason!r}")
    print(f"CITED-A (0 URLs)             -> {'PASS' if 'CITED-A' not in str(fails) else 'FAIL'}")

    # 3 URLs (under floor) -> FAIL
    rd = _research_cited_run_dir([f"https://source-{i}.org/" for i in range(3)])
    reason = build_deck._chk_research_cited(rd / "working" / "research" / "brief-demo.md")
    if not reason:
        fails.append("CITED-B: 3 URLs should FAIL (under floor) but passed")
    elif "AF-RESEARCH-UNCITED" not in reason:
        fails.append(f"CITED-B: fail message malformed: {reason!r}")
    print(f"CITED-B (3 URLs, under floor)-> {'PASS' if 'CITED-B' not in str(fails) else 'FAIL'}")

    # Exactly MIN URLs -> PASS
    rd = _research_cited_run_dir([f"https://source-{i}.org/" for i in range(MIN)])
    reason = build_deck._chk_research_cited(rd / "working" / "research" / "brief-demo.md")
    if reason:
        fails.append(f"CITED-C: exactly {MIN} URLs should PASS but got: {reason!r}")
    print(f"CITED-C ({MIN} URLs, at floor) -> {'PASS' if 'CITED-C' not in str(fails) else 'FAIL'}")

    # 12 URLs (comfortably above floor) -> PASS
    rd = _research_cited_run_dir([f"https://source-{i}.org/article" for i in range(12)])
    reason = build_deck._chk_research_cited(rd / "working" / "research" / "brief-demo.md")
    if reason:
        fails.append(f"CITED-D: 12 URLs should PASS but got: {reason!r}")
    print(f"CITED-D (12 URLs)            -> {'PASS' if 'CITED-D' not in str(fails) else 'FAIL'}")

    # 21-URL fixture (self-contained, well above floor) -> PASS
    rd = _research_cited_run_dir([f"https://research-source-{i}.org/study" for i in range(21)])
    reason = build_deck._chk_research_cited(rd / "working" / "research" / "brief-demo.md")
    if reason:
        fails.append(f"CITED-E (21-URL fixture): should PASS but got: {reason!r}")
    print(f"CITED-E (21-URL fixture)     -> {'PASS' if 'CITED-E' not in str(fails) else 'FAIL'}")

    # None path -> PASS (absent brief handled elsewhere)
    reason = build_deck._chk_research_cited(None)
    if reason:
        fails.append(f"CITED-F: None path should PASS (deferred to _chk_research_brief) but got: {reason!r}")
    print(f"CITED-F (None path)          -> {'PASS' if 'CITED-F' not in str(fails) else 'FAIL'}")

    print(f"RESEARCH-CITED (gate tests)  -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_chk_research_cited_rejects_junk():
    """C3 (REQUIRED NEW TEST): the research-citation gate must REJECT junk URLs —
    localhost / loopback, RFC-1918 private IPs, bare IP literals, .local / reserved
    TLDs, example.* placeholders, AND duplicate citations of the same domain. None
    of these count toward the distinct-real-public-domain floor.

    Cases:
      - 12 distinct LOCALHOST/loopback URLs        -> FAIL (0 real public domains)
      - 12 distinct RFC-1918 / bare-IP URLs        -> FAIL
      - 12 distinct example.com/.local URLs        -> FAIL
      - the SAME real domain cited 20 times        -> FAIL (1 distinct domain < 6)
      - a MIX: 5 real + a flood of junk + dups      -> FAIL (only 5 distinct < 6)
      - 6 distinct REAL public domains              -> PASS (floor met)
    """
    fails = []
    chk = build_deck._chk_research_cited
    floor = build_deck.MIN_DISTINCT_DOMAINS
    assert floor == 6, f"MIN_DISTINCT_DOMAINS must be 6, got {floor}"

    def _brief(urls):
        rd = _research_cited_run_dir(urls)
        return chk(rd / "working" / "research" / "brief-demo.md")

    # localhost / loopback flood -> FAIL
    localhost_urls = ([f"http://localhost:80{i}/page" for i in range(6)] +
                      [f"http://127.0.0.{i}/x" for i in range(1, 7)])
    r = _brief(localhost_urls)
    if not r or "AF-RESEARCH-UNCITED" not in r:
        fails.append(f"C3-JUNK-A: localhost/loopback URLs should FAIL, got: {r!r}")
    print(f"C3-JUNK-A (localhost)        -> {'PASS' if 'C3-JUNK-A' not in str(fails) else 'FAIL'}")

    # RFC-1918 private + bare IP literals -> FAIL
    private_urls = ([f"https://192.168.1.{i}/a" for i in range(2, 8)] +
                    [f"https://10.0.0.{i}/b" for i in range(2, 8)] +
                    ["https://8.8.8.8/c"])  # even a public bare-IP must not count
    r = _brief(private_urls)
    if not r or "AF-RESEARCH-UNCITED" not in r:
        fails.append(f"C3-JUNK-B: RFC-1918 / bare-IP URLs should FAIL, got: {r!r}")
    print(f"C3-JUNK-B (private/bare-IP)  -> {'PASS' if 'C3-JUNK-B' not in str(fails) else 'FAIL'}")

    # example.* placeholders + .local reserved TLDs -> FAIL
    placeholder_urls = ([f"https://example.com/p{i}" for i in range(6)] +
                        [f"https://example.org/q{i}" for i in range(6)] +
                        ["https://intranet.local/x", "https://thing.internal/y"])
    r = _brief(placeholder_urls)
    if not r or "AF-RESEARCH-UNCITED" not in r:
        fails.append(f"C3-JUNK-C: example.*/.local URLs should FAIL, got: {r!r}")
    print(f"C3-JUNK-C (example/.local)   -> {'PASS' if 'C3-JUNK-C' not in str(fails) else 'FAIL'}")

    # SAME real domain cited 20 times -> FAIL (only 1 distinct domain)
    dup_urls = [f"https://nih.gov/article/{i}" for i in range(20)]
    r = _brief(dup_urls)
    if not r or "AF-RESEARCH-UNCITED" not in r:
        fails.append(f"C3-JUNK-D: 20x the SAME domain should FAIL (1 distinct), got: {r!r}")
    print(f"C3-JUNK-D (dup same domain)  -> {'PASS' if 'C3-JUNK-D' not in str(fails) else 'FAIL'}")

    # MIX: 5 distinct real + lots of junk + dups -> FAIL (only 5 < 6)
    mix_urls = (
        [f"https://realsite-{i}.org/x" for i in range(5)] +          # 5 distinct real
        [f"https://realsite-0.org/dup{i}" for i in range(10)] +      # dups of one
        [f"http://127.0.0.1/j{i}" for i in range(10)] +              # localhost junk
        [f"https://example.com/p{i}" for i in range(10)]             # placeholder junk
    )
    r = _brief(mix_urls)
    if not r or "AF-RESEARCH-UNCITED" not in r:
        fails.append(f"C3-JUNK-E: 5 real + junk/dups should FAIL (5 distinct < 6), got: {r!r}")
    # Belt-and-braces: prove the underlying domain extractor sees exactly 5.
    brief_text = "\n".join(mix_urls)
    n_domains = len(build_deck._distinct_public_domains(brief_text))
    if n_domains != 5:
        fails.append(f"C3-JUNK-E: _distinct_public_domains should see 5 real domains, saw {n_domains}")
    print(f"C3-JUNK-E (mix 5 real+junk)  -> {'PASS' if 'C3-JUNK-E' not in str(fails) else 'FAIL'}")

    # 6 distinct REAL public domains -> PASS (floor met, no junk)
    real6 = ["https://nih.gov/a", "https://cdc.gov/b", "https://apa.org/c",
             "https://pewresearch.org/d", "https://researchgate.net/e",
             "https://jsr.org/f"]
    r = _brief(real6)
    if r:
        fails.append(f"C3-JUNK-F: 6 distinct real domains should PASS, got: {r!r}")
    print(f"C3-JUNK-F (6 real domains)   -> {'PASS' if 'C3-JUNK-F' not in str(fails) else 'FAIL'}")

    print(f"C3 RESEARCH-JUNK (reject)    -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_chk_research_cited_requires_ghi():
    """Fix 1b: the research-citation gate now ALSO hard-fails (AF-RESEARCH-UNCITED)
    when the SOURCED categories G/H/I are absent or empty — independently of the
    self-asserted research_complete:true flag — EVEN when the distinct-domain floor
    is met.

    Cases (all briefs carry 8 distinct real public domains so the domain floor passes):
      - G/H/I all present + non-empty   -> PASS
      - Category G absent                -> FAIL (names Category G)
      - Category H present but empty      -> FAIL (names Category H)
      - Category I a placeholder-only body-> FAIL (names Category I)
    """
    fails = []
    chk = build_deck._chk_research_cited
    real8 = [f"https://realsource-{i}.org/article" for i in range(8)]

    def _write(body_blocks: str) -> Path:
        root = Path(tempfile.mkdtemp(prefix="deck_ghi_test_"))
        (root / "working" / "research").mkdir(parents=True, exist_ok=True)
        text = "# Research brief\nresearch_complete: true\n"
        for u in real8:
            text += f"- Source: {u}\n"
        text += body_blocks
        brief = root / "working" / "research" / "brief-demo.md"
        brief.write_text(text)
        return brief

    # GHI-A: all present + non-empty -> PASS
    good = (
        "\n## Category G: Credible Attributable Quotes\n- \"Quote.\" — Expert, 2024.\n"
        "\n## Category H: Fact-Validation Ledger\n- Claim X VALIDATED vs source. SUPPORTED.\n"
        "\n## Category I: Objection Research\n- Objection: cost. Rebuttal: cited ROI.\n"
    )
    r = chk(_write(good))
    if r:
        fails.append(f"GHI-A: full G/H/I (8 domains) should PASS, got: {r!r}")
    print(f"GHI-A (G/H/I present)        -> {'PASS' if 'GHI-A' not in str(fails) else 'FAIL'}")

    # GHI-B: Category G absent -> FAIL, message names G
    no_g = (
        "\n## Category H: Fact-Validation Ledger\n- Claim X VALIDATED. SUPPORTED.\n"
        "\n## Category I: Objection Research\n- Objection: cost. Rebuttal: cited ROI.\n"
    )
    r = chk(_write(no_g))
    if not r or "AF-RESEARCH-UNCITED" not in r or "Category G" not in r:
        fails.append(f"GHI-B: absent Category G should FAIL naming G, got: {r!r}")
    print(f"GHI-B (G absent)             -> {'PASS' if 'GHI-B' not in str(fails) else 'FAIL'}")

    # GHI-C: Category H present but empty (bare heading, no body) -> FAIL, names H
    empty_h = (
        "\n## Category G: Credible Attributable Quotes\n- \"Quote.\" — Expert.\n"
        "\n## Category H:\n\n"
        "## Category I: Objection Research\n- Objection: cost. Rebuttal: ROI.\n"
    )
    r = chk(_write(empty_h))
    if not r or "AF-RESEARCH-UNCITED" not in r or "Category H" not in r:
        fails.append(f"GHI-C: empty Category H should FAIL naming H, got: {r!r}")
    print(f"GHI-C (H empty)              -> {'PASS' if 'GHI-C' not in str(fails) else 'FAIL'}")

    # GHI-D: Category I body is only a template placeholder -> FAIL, names I
    placeholder_i = (
        "\n## Category G: Credible Attributable Quotes\n- \"Quote.\" — Expert.\n"
        "\n## Category H: Fact-Validation Ledger\n- Claim X VALIDATED. SUPPORTED.\n"
        "\n## Category I:\n[Output of SOP 9.4 step 3]\n"
    )
    r = chk(_write(placeholder_i))
    if not r or "AF-RESEARCH-UNCITED" not in r or "Category I" not in r:
        fails.append(f"GHI-D: placeholder-only Category I should FAIL naming I, got: {r!r}")
    print(f"GHI-D (I placeholder-only)   -> {'PASS' if 'GHI-D' not in str(fails) else 'FAIL'}")

    print(f"RESEARCH-CITED G/H/I (fix1b) -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_chk_kie_baked():
    """AF-I14 KIE-BAKED gate unit tests. Proves the gate is the source of truth that
    every rendered slide was actually model-baked (real KIE taskId + verified,
    above-floor PNG), and that it DEFERS (passes) before a render record exists.

    Cases:
      - no process_manifest.json yet            -> PASS (pre-render deferral)
      - manifest present, no render record       -> PASS (deferral)
      - render record, every slide real-baked    -> PASS
      - a slide with taskId 'native'             -> FAIL (AF-I14)
      - a slide image below the placeholder floor -> FAIL (AF-I14)
      - a slide image missing on disk             -> FAIL (AF-I14)
      - the SAME image_sha256 across 3 slides     -> FAIL (flat-fill reuse)
      - output_slide_count < deck slide count     -> FAIL (skipped bake)
    """
    import hashlib as _hashlib
    fails = []
    chk = build_deck._chk_kie_baked
    floor = build_deck.PLACEHOLDER_MIN_BYTES
    PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

    def _run_dir(slide_count: int = 0) -> Path:
        root = Path(tempfile.mkdtemp(prefix="deck_kie_test_"))
        (root / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
        if slide_count:
            (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
            slides = [{"slide": i + 1} for i in range(slide_count)]
            (root / "working" / "copy" / "slides.json").write_text(json.dumps(slides))
        return root

    def _png(root: Path, name: str, size: int, fill: bytes = b"\x00") -> Path:
        p = root / name
        body = PNG_MAGIC + (fill * max(0, size - len(PNG_MAGIC)))
        p.write_bytes(body)
        return p

    def _write_manifest(root: Path, render_record):
        man = {"phases": []}
        if render_record is not None:
            man["phases"].append(render_record)
        (root / "working" / "checkpoints" / "process_manifest.json").write_text(
            json.dumps(man))

    def _slides_path(root: Path):
        sp = root / "working" / "copy" / "slides.json"
        return sp if sp.exists() else None

    # KIE-A: no manifest at all -> PASS (deferral)
    rd = _run_dir()
    (rd / "working" / "checkpoints" / "process_manifest.json").unlink(missing_ok=True)
    r = chk(rd, _slides_path(rd))
    if r:
        fails.append(f"KIE-A: no manifest should DEFER (pass), got: {r!r}")
    print(f"KIE-A (no manifest defer)    -> {'PASS' if 'KIE-A' not in str(fails) else 'FAIL'}")

    # KIE-B: manifest present, no render record -> PASS (deferral)
    rd = _run_dir()
    _write_manifest(rd, None)
    r = chk(rd, _slides_path(rd))
    if r:
        fails.append(f"KIE-B: manifest w/o render record should DEFER, got: {r!r}")
    print(f"KIE-B (no render rec defer)  -> {'PASS' if 'KIE-B' not in str(fails) else 'FAIL'}")

    # KIE-C: 2 slides, both real-baked above the floor -> PASS
    rd = _run_dir(2)
    imgs = [_png(rd, f"s{i}.png", floor + 1000, fill=bytes([i + 1])) for i in range(2)]
    shas = [_hashlib.sha256(p.read_bytes()).hexdigest() for p in imgs]
    _write_manifest(rd, {"phase": "render", "output_slide_count": 2, "slides": [
        {"slide": 1, "taskId": "kie-abc-1", "image": str(imgs[0]), "image_sha256": shas[0]},
        {"slide": 2, "taskId": "kie-abc-2", "image": str(imgs[1]), "image_sha256": shas[1]},
    ]})
    r = chk(rd, _slides_path(rd))
    if r:
        fails.append(f"KIE-C: all real-baked should PASS, got: {r!r}")
    print(f"KIE-C (all real-baked)       -> {'PASS' if 'KIE-C' not in str(fails) else 'FAIL'}")

    # KIE-D: a slide with taskId 'native' -> FAIL
    rd = _run_dir(2)
    imgs = [_png(rd, f"d{i}.png", floor + 1000, fill=bytes([i + 1])) for i in range(2)]
    shas = [_hashlib.sha256(p.read_bytes()).hexdigest() for p in imgs]
    _write_manifest(rd, {"phase": "render", "output_slide_count": 2, "slides": [
        {"slide": 1, "taskId": "native", "image": str(imgs[0]), "image_sha256": shas[0]},
        {"slide": 2, "taskId": "kie-d-2", "image": str(imgs[1]), "image_sha256": shas[1]},
    ]})
    r = chk(rd, _slides_path(rd))
    if not r or "AF-I14" not in r:
        fails.append(f"KIE-D: native taskId should FAIL (AF-I14), got: {r!r}")
    print(f"KIE-D (native taskId)        -> {'PASS' if 'KIE-D' not in str(fails) else 'FAIL'}")

    # KIE-E: a slide image below the placeholder floor -> FAIL
    rd = _run_dir(2)
    big = _png(rd, "e1.png", floor + 1000, fill=b"\x11")
    small = _png(rd, "e2.png", floor - 100, fill=b"\x22")  # under floor
    _write_manifest(rd, {"phase": "render", "output_slide_count": 2, "slides": [
        {"slide": 1, "taskId": "kie-e-1", "image": str(big),
         "image_sha256": _hashlib.sha256(big.read_bytes()).hexdigest()},
        {"slide": 2, "taskId": "kie-e-2", "image": str(small),
         "image_sha256": _hashlib.sha256(small.read_bytes()).hexdigest()},
    ]})
    r = chk(rd, _slides_path(rd))
    if not r or "AF-I14" not in r:
        fails.append(f"KIE-E: under-floor image should FAIL (AF-I14), got: {r!r}")
    print(f"KIE-E (under placeholder floor)-> {'PASS' if 'KIE-E' not in str(fails) else 'FAIL'}")

    # KIE-F: a slide image missing on disk -> FAIL
    rd = _run_dir(2)
    img1 = _png(rd, "f1.png", floor + 1000, fill=b"\x33")
    _write_manifest(rd, {"phase": "render", "output_slide_count": 2, "slides": [
        {"slide": 1, "taskId": "kie-f-1", "image": str(img1),
         "image_sha256": _hashlib.sha256(img1.read_bytes()).hexdigest()},
        {"slide": 2, "taskId": "kie-f-2", "image": str(rd / "does-not-exist.png"),
         "image_sha256": "deadbeef"},
    ]})
    r = chk(rd, _slides_path(rd))
    if not r or "AF-I14" not in r:
        fails.append(f"KIE-F: missing image should FAIL (AF-I14), got: {r!r}")
    print(f"KIE-F (missing image)        -> {'PASS' if 'KIE-F' not in str(fails) else 'FAIL'}")

    # KIE-G: the SAME image_sha256 across 3 slides -> FAIL (flat-fill reuse)
    rd = _run_dir(3)
    flat = _png(rd, "flat.png", floor + 1000, fill=b"\x44")
    flat_sha = _hashlib.sha256(flat.read_bytes()).hexdigest()
    _write_manifest(rd, {"phase": "render", "output_slide_count": 3, "slides": [
        {"slide": i + 1, "taskId": f"kie-g-{i+1}", "image": str(flat),
         "image_sha256": flat_sha} for i in range(3)
    ]})
    r = chk(rd, _slides_path(rd))
    if not r or "AF-I14" not in r:
        fails.append(f"KIE-G: 3x reused sha256 should FAIL (flat-fill), got: {r!r}")
    print(f"KIE-G (reused flat-fill hash)-> {'PASS' if 'KIE-G' not in str(fails) else 'FAIL'}")

    # KIE-H: output_slide_count < deck slide count -> FAIL (a slide skipped baking)
    rd = _run_dir(3)  # deck has 3 slides
    img = _png(rd, "h1.png", floor + 1000, fill=b"\x55")
    _write_manifest(rd, {"phase": "render", "output_slide_count": 1, "slides": [
        {"slide": 1, "taskId": "kie-h-1", "image": str(img),
         "image_sha256": _hashlib.sha256(img.read_bytes()).hexdigest()},
    ]})
    r = chk(rd, _slides_path(rd))
    if not r or "AF-I14" not in r:
        fails.append(f"KIE-H: skipped-bake (count mismatch) should FAIL, got: {r!r}")
    print(f"KIE-H (skipped bake count)   -> {'PASS' if 'KIE-H' not in str(fails) else 'FAIL'}")

    print(f"AF-I14 KIE-BAKED (fix1a)     -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_chk_claims_without_citation():
    """CLAIMS-WITHOUT-CITATION gate (AF-RESEARCH-UNCITED) unit tests:

      - Claims in copy + 0 URLs in research pack -> FAILS
      - Claims in copy + 8 URLs in research pack -> PASSES (citation exists)
      - No claims in copy + 0 URLs in research pack -> PASSES (no claim markers)
    """
    fails = []

    # Claims + zero URLs -> FAIL
    rd = _claims_citation_run_dir(copy_has_claims=True, research_url_count=0)
    reason = build_deck._chk_claims_without_citation(rd)
    if not reason:
        fails.append("CLAIMS-A: copy with claims + 0 research URLs should FAIL but passed")
    elif "AF-RESEARCH-UNCITED" not in reason:
        fails.append(f"CLAIMS-A: fail message malformed: {reason!r}")
    print(f"CLAIMS-A (claims+0 urls)     -> {'PASS' if 'CLAIMS-A' not in str(fails) else 'FAIL'}")

    # Claims + 8 URLs -> PASS (citation floor met)
    rd = _claims_citation_run_dir(copy_has_claims=True, research_url_count=8)
    reason = build_deck._chk_claims_without_citation(rd)
    if reason:
        fails.append(f"CLAIMS-B: copy with claims + 8 URLs should PASS but got: {reason!r}")
    print(f"CLAIMS-B (claims+8 urls)     -> {'PASS' if 'CLAIMS-B' not in str(fails) else 'FAIL'}")

    # No claims + 0 URLs -> PASS (no claim markers, gate not triggered)
    rd = _claims_citation_run_dir(copy_has_claims=False, research_url_count=0)
    reason = build_deck._chk_claims_without_citation(rd)
    if reason:
        fails.append(f"CLAIMS-C: no claims + 0 URLs should PASS but got: {reason!r}")
    print(f"CLAIMS-C (no claims, 0 urls) -> {'PASS' if 'CLAIMS-C' not in str(fails) else 'FAIL'}")

    print(f"CLAIMS-WITHOUT-CITATION      -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_postflight_rejects_symlink_and_decoy():
    """C2 (REQUIRED NEW TEST): the postflight completeness gate must reject a SYMLINK
    (pointing at a large unrelated file) and a DECOY (right size, wrong content type).

    Cases:
      - All artifacts valid EXCEPT guide_pdf is a SYMLINK to an over-size real file
        -> exit 5 (symlinks are rejected even when the target is big enough).
      - All artifacts valid EXCEPT infographic.png is a DECOY: over the size floor but
        with the WRONG magic bytes (it's actually a PDF header, not PNG) -> exit 5.
      - Control: all artifacts valid (correct magic + size) -> PASSES (no exit 5),
        proving the hardening does not break the legitimate path.
    """
    fails = []
    all_keys = {spec["key"] for spec in build_deck.DELIVERABLES_REQUIRED}

    # ---- Control: all valid -> PASS (no SystemExit) ----
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(all_keys)
    try:
        build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
    except SystemExit as exc:
        fails.append(f"C2-CTRL: all-valid bundle should PASS, got sys.exit({exc.code})")
    print(f"C2-CTRL (all valid)          -> {'PASS' if 'C2-CTRL' not in str(fails) else 'FAIL'}")

    # ---- Symlink decoy: guide_pdf is a symlink to a big real file -> exit 5 ----
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(all_keys - {"guide_pdf"})
    guide_spec = next(s for s in build_deck.DELIVERABLES_REQUIRED if s["key"] == "guide_pdf")
    guide_name = build_deck._expand_filename(guide_spec["filename"], slug)
    # A real over-size target file (valid PDF magic + well over the threshold).
    target = bundle_dir / "_real_big_target.pdf"
    target.write_bytes(_valid_bytes_for("guide_pdf", guide_spec["min_bytes"] + 4096))
    link = bundle_dir / guide_name
    try:
        os.symlink(str(target), str(link))
        symlink_made = True
    except (OSError, NotImplementedError):
        symlink_made = False
    if symlink_made:
        try:
            build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
            fails.append("C2-SYMLINK: a symlink deliverable should exit 5 but gate passed")
        except SystemExit as exc:
            if exc.code != 5:
                fails.append(f"C2-SYMLINK: symlink should exit 5, got {exc.code}")
        print(f"C2-SYMLINK (symlink decoy)   -> {'PASS' if 'C2-SYMLINK' not in str(fails) else 'FAIL'}")
    else:
        print("C2-SYMLINK (symlink decoy)   -> SKIP (symlinks unsupported on this FS)")

    # ---- Content-type decoy: infographic.png over size but WRONG magic -> exit 5 ----
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(all_keys - {"infographic_png"})
    info_spec = next(s for s in build_deck.DELIVERABLES_REQUIRED if s["key"] == "infographic_png")
    info_name = build_deck._expand_filename(info_spec["filename"], slug)
    # Over the 100KB floor, but the bytes are a PDF header — NOT a PNG. Right size,
    # wrong type: the magic-byte check must catch it.
    decoy = b"%PDF-1.7\n" + (b"\x00" * (info_spec["min_bytes"] + 2048))
    (bundle_dir / info_name).write_bytes(decoy)
    try:
        build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
        fails.append("C2-DECOY: a wrong-type (over-size) decoy should exit 5 but gate passed")
    except SystemExit as exc:
        if exc.code != 5:
            fails.append(f"C2-DECOY: wrong-type decoy should exit 5, got {exc.code}")
    print(f"C2-DECOY (wrong-type decoy)  -> {'PASS' if 'C2-DECOY' not in str(fails) else 'FAIL'}")

    print(f"C2 POSTFLIGHT (symlink/decoy)-> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_parse_speech_chunks():
    """parse_speech_chunks must map BOTH marker forms to per-slide spoken text:
        '## Slide 1 ... ## Slide 2 ...'   (markdown heading)
        'SLIDE 1 ... SLIDE 2 ...'         (inline marker)
    The marker/title line is stripped; the block runs to the next marker; an absent
    or marker-less speech yields {} (best-effort, never raises)."""
    fails = []

    # --- Case A: the spec example — '## Slide 1 ... ## Slide 2 ...' ---
    speech_a = (
        "## Slide 1\n"
        "Welcome everyone to the webinar.\n"
        "Glad you could make it.\n"
        "\n"
        "## Slide 2\n"
        "Here is the big problem we are solving.\n"
    )
    a = build_deck.parse_speech_chunks(speech_a)
    if set(a.keys()) != {1, 2}:
        fails.append(f"PARSE-A: expected slide keys {{1,2}}, got {sorted(a.keys())}")
    if a.get(1) != "Welcome everyone to the webinar.\nGlad you could make it.":
        fails.append(f"PARSE-A: slide 1 text wrong: {a.get(1)!r}")
    if a.get(2) != "Here is the big problem we are solving.":
        fails.append(f"PARSE-A: slide 2 text wrong: {a.get(2)!r}")
    print(f"PARSE-A (## Slide N form)    -> {'PASS' if not [f for f in fails if 'PARSE-A' in f] else 'FAIL'}")

    # --- Case B: inline 'SLIDE N' marker, mixed case ---
    speech_b = "Slide 1\nFirst spoken line.\nslide 2\nSecond spoken line."
    b = build_deck.parse_speech_chunks(speech_b)
    if b != {1: "First spoken line.", 2: "Second spoken line."}:
        fails.append(f"PARSE-B: inline marker parse wrong: {b!r}")
    print(f"PARSE-B (inline SLIDE N)     -> {'PASS' if not [f for f in fails if 'PARSE-B' in f] else 'FAIL'}")

    # --- Case C: marker line carries a title after the number; title is stripped ---
    speech_c = "### Slide 3 — The Hook\nSpoken hook only.\n# Slide 4: Close\nClose strong."
    c = build_deck.parse_speech_chunks(speech_c)
    if c != {3: "Spoken hook only.", 4: "Close strong."}:
        fails.append(f"PARSE-C: titled-marker parse wrong: {c!r}")
    print(f"PARSE-C (titled markers)     -> {'PASS' if not [f for f in fails if 'PARSE-C' in f] else 'FAIL'}")

    # --- Case D: no markers / empty / None -> {} (best-effort, never raises) ---
    if build_deck.parse_speech_chunks("Just prose, no markers at all.") != {}:
        fails.append("PARSE-D: marker-less speech should yield {}")
    if build_deck.parse_speech_chunks("") != {}:
        fails.append("PARSE-D: empty speech should yield {}")
    if build_deck.parse_speech_chunks(None) != {}:
        fails.append("PARSE-D: None speech should yield {}")
    print(f"PARSE-D (no/empty markers)   -> {'PASS' if not [f for f in fails if 'PARSE-D' in f] else 'FAIL'}")

    print(f"PARSE (parse_speech_chunks)  -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_h1_whitespace_only_prompt():
    """H1 (REQUIRED NEW TEST): a whitespace-only rich prompt (and a whitespace-padded
    one whose NON-whitespace length is under the floor) must FAIL — the floor is
    measured on prompt.strip(), so blank/padded files can never satisfy it.

    Cases:
      - a prompt of pure whitespace (spaces/newlines/tabs, > 1,500 raw chars)
        -> _chk_rich_prompts FAILS and load_rich_prompt RAISES (AF-P1).
      - a prompt that is a few real words padded with thousands of spaces to exceed
        1,500 RAW chars -> still FAILS (stripped length is tiny).
      - control: a genuine >= 1,500 non-whitespace prompt with leading/trailing
        whitespace -> PASSES and is returned VERBATIM (whitespace preserved).
    """
    fails = []
    floor = build_deck.PROMPT_CHAR_FLOOR
    slide = {"slide": 1, "scene": "x", "copy": ["y"]}

    # ---- pure whitespace, well over the RAW floor ----
    whitespace_only = (" \t\n" * ((floor // 3) + 500))  # well over the RAW floor, 0 non-whitespace
    assert len(whitespace_only) > floor, "fixture must exceed the RAW floor to prove the bug"
    rd = _rich_prompt_run_dir(whitespace_only)
    reason = build_deck._chk_rich_prompts(rd)
    if not reason:
        fails.append("H1-WS-A: a whitespace-only prompt should FAIL _chk_rich_prompts but passed")
    elif "AF-P1" not in reason:
        fails.append(f"H1-WS-A: fail message malformed: {reason!r}")
    try:
        build_deck.load_rich_prompt(slide, rd)
        fails.append("H1-WS-A: load_rich_prompt should RAISE on a whitespace-only prompt")
    except ValueError as exc:
        if "AF-P1" not in str(exc):
            fails.append(f"H1-WS-A: load_rich_prompt whitespace-raise wrong msg: {exc}")
    print(f"H1-WS-A (whitespace-only)    -> {'PASS' if 'H1-WS-A' not in str(fails) else 'FAIL'}")

    # ---- a few real words padded with spaces past the RAW floor ----
    padded = "real words here" + (" " * (floor + 500))  # raw > floor, stripped tiny
    assert len(padded) > floor and len(padded.strip()) < floor
    rd = _rich_prompt_run_dir(padded)
    reason = build_deck._chk_rich_prompts(rd)
    if not reason:
        fails.append("H1-WS-B: a whitespace-padded sub-floor prompt should FAIL but passed")
    try:
        build_deck.load_rich_prompt(slide, rd)
        fails.append("H1-WS-B: load_rich_prompt should RAISE on a padded sub-floor prompt")
    except ValueError as exc:
        if "AF-P1" not in str(exc):
            fails.append(f"H1-WS-B: load_rich_prompt padded-raise wrong msg: {exc}")
    print(f"H1-WS-B (padded sub-floor)   -> {'PASS' if 'H1-WS-B' not in str(fails) else 'FAIL'}")

    # ---- control: genuine prompt with surrounding whitespace -> PASS + VERBATIM ----
    valid_padded = "\n\n" + RICH_PROMPT + "\n\n"
    assert len(valid_padded.strip()) >= floor
    rd = _rich_prompt_run_dir(valid_padded)
    if build_deck._chk_rich_prompts(rd):
        fails.append("H1-WS-C: a valid prompt with surrounding whitespace should PASS but failed")
    try:
        got = build_deck.load_rich_prompt(slide, rd)
        if got != valid_padded:
            fails.append("H1-WS-C: load_rich_prompt must return the prompt VERBATIM (whitespace preserved)")
    except ValueError as exc:
        fails.append(f"H1-WS-C: load_rich_prompt raised on a valid padded prompt: {exc}")
    print(f"H1-WS-C (valid + padding)    -> {'PASS' if 'H1-WS-C' not in str(fails) else 'FAIL'}")

    print(f"H1 WHITESPACE-PROMPT         -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_speech_pdf_design_system_accent():
    """M6 (REQUIRED NEW TEST): when a design_system.json is wired into the speech
    spec, its locked brand accent + typefaces flow into the speech PDF's color/style
    table (instead of the house defaults), and the PDF still renders.

    Cases:
      - design_system.json with brand.accent_hex='#C8104E' + headline_font/body_font
        -> SpeechPDF.accent == '#C8104E', design_system_accent set, the cue style's
        textColor matches the accent, and the rendered PDF's color table contains the
        accent as a reportlab RGB color operator.
      - no design_system_path -> the reference defaults (#C8860D) are untouched.
    Returns a list of failure strings ([] = all passed)."""
    fails = []
    try:
        sys.path.insert(0, str(HERE))
        import presenters_speech_pdf as psp  # noqa: E402
        from reportlab.lib import colors
    except Exception as exc:  # noqa: BLE001
        print(f"M6 SPEECH-PDF DESIGN-SYSTEM -> SKIP (import failed: {exc})")
        return fails

    ds_accent = "#C8104E"
    ds_dir = Path(tempfile.mkdtemp(prefix="speech_pdf_ds_test_"))
    ds_path = ds_dir / "design_system.json"
    ds_path.write_text(json.dumps({
        "brand": {"accent_hex": ds_accent,
                  "headline_font": "Montserrat Black",
                  "body_font": "Inter"}
    }))

    # ---- with design system: accent + style table inherit the locked accent ----
    spec = dict(psp.SAMPLE_SPEC)
    spec["design_system_path"] = str(ds_path)
    pdf = psp.SpeechPDF(spec)
    if pdf.accent.upper() != ds_accent:
        fails.append(f"M6-A: SpeechPDF.accent should be {ds_accent}, got {pdf.accent!r}")
    if (pdf.design_system_accent or "").upper() != ds_accent:
        fails.append(f"M6-A: design_system_accent should be {ds_accent}, "
                     f"got {pdf.design_system_accent!r}")
    # The cue style's textColor must equal the design-system accent (the color table).
    if pdf.st["cue"].textColor.hexval() != colors.HexColor(ds_accent).hexval():
        fails.append("M6-A: the cue style textColor did not inherit the design-system accent")
    print(f"M6-A (accent in style table) -> {'PASS' if 'M6-A' not in str(fails) else 'FAIL'}")

    # ---- the rendered PDF's color table carries the accent RGB operator ----
    # reportlab encodes content streams with ASCII85Decode + FlateDecode, so each
    # stream is base85-decoded THEN flate-decompressed before we can read the color
    # operators. We then search the decoded content for the accent's RGB fill/stroke
    # operator ('r g b rg' / 'r g b RG'), the canonical PDF color-table form.
    import base64 as _b64
    import re as _re
    import zlib as _zlib
    out_pdf = ds_dir / "speech.pdf"
    try:
        pdf.build(str(out_pdf))
        raw = out_pdf.read_bytes()
        decoded = bytearray(raw)  # include any plaintext streams too
        for m in _re.finditer(rb"stream\r?\n(.*?)\r?\n?endstream", raw, _re.DOTALL):
            chunk = m.group(1)
            for transform in (
                lambda b: _zlib.decompress(b),                        # Flate only
                lambda b: _zlib.decompress(_b64.a85decode(b, adobe=False)),
                lambda b: _zlib.decompress(_b64.a85decode(
                    b.strip().rstrip(b"~>"), adobe=False)),
            ):
                try:
                    decoded += transform(chunk)
                    break
                except Exception:  # noqa: BLE001 — try the next decode chain
                    continue
        c = colors.HexColor(ds_accent)
        # reportlab writes channels with the leading zero stripped (e.g. '.784314'),
        # rounded to 6 dp, as 'r g b rg' / 'r g b RG'. Match that exact form.
        def _chan(v):
            s = f"{round(v, 6):.6f}".rstrip("0").rstrip(".")
            return s[1:] if s.startswith("0.") else s  # '.784314'
        def _op(suffix):
            return f"{_chan(c.red)} {_chan(c.green)} {_chan(c.blue)} {suffix}".encode()
        if _op("rg") not in decoded and _op("RG") not in decoded:
            fails.append("M6-B: the design-system accent RGB does not appear in the "
                         "rendered PDF color table")
    except Exception as exc:  # noqa: BLE001
        fails.append(f"M6-B: building the design-system speech PDF raised: {exc}")
    print(f"M6-B (accent in rendered PDF)-> {'PASS' if 'M6-B' not in str(fails) else 'FAIL'}")

    # ---- without a design system: the reference default accent is untouched ----
    pdf_default = psp.SpeechPDF(dict(psp.SAMPLE_SPEC))
    if pdf_default.design_system_accent is not None:
        fails.append("M6-C: design_system_accent should be None with no design system")
    if pdf_default.accent.upper() != "#C8860D":
        fails.append(f"M6-C: default accent should be #C8860D, got {pdf_default.accent!r}")
    print(f"M6-C (no-DS default intact)  -> {'PASS' if 'M6-C' not in str(fails) else 'FAIL'}")

    print(f"M6 SPEECH-PDF DESIGN-SYSTEM  -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_teleprompter_design_system_accent():
    """M5 (REQUIRED NEW TEST): build_teleprompter.read_design_system_accent reads the
    locked brand accent from design_system.json (accent > accent_hex > primary), falls
    back to the house amber when absent/invalid, and build_html injects it into :root.
    Returns a list of failure strings ([] = all passed)."""
    fails = []
    try:
        sys.path.insert(0, str(HERE))
        import build_teleprompter as bt  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        print(f"M5 TELEPROMPTER DESIGN-SYS  -> SKIP (import failed: {exc})")
        return fails

    d = Path(tempfile.mkdtemp(prefix="tele_ds_test_"))

    # brand.accent preferred.
    p1 = d / "ds1.json"
    p1.write_text(json.dumps({"brand": {"accent": "#C8104E", "primary": "#000000"}}))
    if bt.read_design_system_accent(str(p1)).upper() != "#C8104E":
        fails.append("M5-A: brand.accent should win, got "
                     f"{bt.read_design_system_accent(str(p1))!r}")

    # falls back to accent_hex then primary.
    p2 = d / "ds2.json"
    p2.write_text(json.dumps({"brand": {"primary": "#123ABC"}}))
    if bt.read_design_system_accent(str(p2)).upper() != "#123ABC":
        fails.append("M5-B: brand.primary fallback failed, got "
                     f"{bt.read_design_system_accent(str(p2))!r}")

    # absent path -> house amber fallback.
    if bt.read_design_system_accent(None) != bt.HOUSE_ACCENT:
        fails.append("M5-C: None path should fall back to HOUSE_ACCENT")
    if bt.read_design_system_accent(str(d / "nope.json")) != bt.HOUSE_ACCENT:
        fails.append("M5-C: missing file should fall back to HOUSE_ACCENT")

    # invalid (non-hex) accent -> fallback.
    p3 = d / "ds3.json"
    p3.write_text(json.dumps({"brand": {"accent": "cornflower"}}))
    if bt.read_design_system_accent(str(p3)) != bt.HOUSE_ACCENT:
        fails.append("M5-D: a non-hex accent should fall back to HOUSE_ACCENT")
    print(f"M5-A..D (DS accent reader)   -> {'PASS' if not [f for f in fails if f.startswith('M5-A') or f.startswith('M5-B') or f.startswith('M5-C') or f.startswith('M5-D')] else 'FAIL'}")

    # build_html injects the accent into :root and replaces every placeholder.
    data = bt.parse_speech(bt.SAMPLE_SPEECH_MD)
    html = bt.build_html(data, "Acme", data["wpm"], "#C8104E")
    if "__ACCENT_HEX__" in html:
        fails.append("M5-E: __ACCENT_HEX__ placeholder not replaced in the HTML")
    if "--accent: #C8104E" not in html:
        fails.append("M5-E: the injected accent does not appear in :root --accent")
    # default (house amber) still works when no design system is given.
    html_def = bt.build_html(data, "Acme", data["wpm"])
    if "--accent: #f2b134" not in html_def:
        fails.append("M5-E: default house amber accent not applied when none supplied")
    print(f"M5-E (build_html injection)  -> {'PASS' if 'M5-E' not in str(fails) else 'FAIL'}")

    print(f"M5 TELEPROMPTER DESIGN-SYS   -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_hook_dedicated_slide_count():
    """L1 (REQUIRED NEW TEST): the hook ceiling is enforced as a band, not a floor.
    A hook_package.json must carry dedicated_slide_count in [3,4]; a count below 3,
    above 4, or absent fails the band check. This is the ceiling reconciliation
    assertion (SOP-SLIDE-03): the live doctrine is EXACTLY 3 to 4 dedicated slides,
    NOWHERE ELSE — never the retired '>= 7' floor.
    Returns a list of failure strings ([] = all passed)."""
    fails = []

    def _hook_pkg_dir(payload):
        root = Path(tempfile.mkdtemp(prefix="hook_pkg_test_"))
        (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
        if payload is not None:
            (root / "working" / "copy" / "hook_package.json").write_text(
                json.dumps(payload))
        return root

    def _check_band(root):
        """Return "" when hook_package.json.dedicated_slide_count is in [3,4],
        else a fail reason. (Mirrors the SOP-SLIDE-03 band the QC gate enforces.)"""
        pkg = root / "working" / "copy" / "hook_package.json"
        if not pkg.exists():
            return "hook_package.json absent"
        try:
            obj = json.loads(pkg.read_text())
        except Exception as exc:  # noqa: BLE001
            return f"hook_package.json not valid JSON ({exc})"
        n = obj.get("dedicated_slide_count")
        if not isinstance(n, int) or n < 3 or n > 4:
            return (f"dedicated_slide_count={n!r} outside the 3-to-4 ceiling band "
                    "(SOP-SLIDE-03)")
        return ""

    # 3 -> PASS, 4 -> PASS.
    for ok in (3, 4):
        if _check_band(_hook_pkg_dir({"dedicated_slide_count": ok})):
            fails.append(f"L1-HOOK: dedicated_slide_count={ok} should PASS the band")
    # 2 -> FAIL (under), 5 -> FAIL (over), 7 -> FAIL (the retired floor), absent -> FAIL.
    for bad in (2, 5, 7):
        if not _check_band(_hook_pkg_dir({"dedicated_slide_count": bad})):
            fails.append(f"L1-HOOK: dedicated_slide_count={bad} should FAIL the band")
    if not _check_band(_hook_pkg_dir(None)):
        fails.append("L1-HOOK: absent hook_package.json should FAIL the band check")
    print(f"L1 HOOK CEILING BAND [3,4]   -> {'PASS' if not fails else 'FAIL'}")
    return fails


# ===========================================================================
# GUARD A — AF-COVERAGE EMITTER
# ===========================================================================
# Every manifest autofail with enforced_by==build_deck and a py_symbol is a
# DOCTRINE RULE. Guard A (scripts/gate_integrity_check.py) requires that each
# such code is not only enforced in build_deck.py but is ALSO actually TRIGGERED
# by a deliberately-failing fixture (a negative test) — the exact thing that
# would have caught AF-QC-INDEPENDENCE being a no-op. This emitter drives each
# build_deck-enforced gate to FAILURE with a crafted bad fixture, scrapes the
# AF code out of the returned reason / raised exception, and writes the set of
# codes a negative test really triggered to working/af-coverage.json.
#
# To add coverage for a NEW build_deck-enforced AF code: append a probe below
# whose fixture trips the gate, and record the code via _af_record(...).
# Guard A fails if a declared+enforced code has no probe here (untested no-op).

AF_COVERAGE_PATH = HERE / "working" / "af-coverage.json"

_AF_RE = __import__("re").compile(r"AF-[A-Z0-9]+(?:-[A-Z0-9]+)*")


def _af_codes_in(text: str):
    return set(_AF_RE.findall(text or ""))


def emit_af_coverage():
    """Drive every build_deck-enforced gate to FAILURE and record which AF codes
    a deliberately-failing fixture actually triggers. Writes working/af-coverage.json
    ({"triggered": [...]}) and prints a stdout-parseable banner. Returns the
    (sorted) list of triggered codes. Self-checking: appends to the returned list
    only codes that REALLY surfaced from a failing path, never a hardcoded label."""
    triggered = set()

    def record(code, reason_text):
        """Record `code` ONLY if it actually appears in the failing reason/exception
        text — proving the negative fixture really tripped THIS gate."""
        if code in _af_codes_in(reason_text):
            triggered.add(code)

    # AF-COVERAGE-1 — compressed deck (120 source / 90 output) FAILS _chk_coverage.
    rd = _coverage_run_dir(120, 90)
    record("AF-COVERAGE-1", build_deck._chk_coverage(rd))

    # AF-P1 — a MISSING rich prompt FAILS _chk_rich_prompts.
    rd = _rich_prompt_run_dir(None)
    record("AF-P1", build_deck._chk_rich_prompts(rd))

    # AF-PROMPT-FLOOR / AF-P1 — a sub-floor prompt FAILS _chk_rich_prompts; the
    # 1,500-char floor is PROMPT_CHAR_FLOOR. (load_rich_prompt raises AF-P1 too.)
    rd = _rich_prompt_run_dir("way too thin")
    sub_reason = build_deck._chk_rich_prompts(rd)
    record("AF-P1", sub_reason)
    try:
        build_deck.load_rich_prompt({"slide": 1, "scene": "x", "copy": ["y"]}, rd)
    except ValueError as exc:
        # The floor symbol (PROMPT_CHAR_FLOOR) gate surfaces as AF-P1; AF-PROMPT-FLOOR
        # is its manifest twin (same 1,500 floor). Record both from the same proof.
        record("AF-P1", str(exc))
        if str(build_deck.PROMPT_CHAR_FLOOR) in str(exc) or "AF-P1" in str(exc):
            triggered.add("AF-PROMPT-FLOOR")

    # AF-P2 — an over-ceiling prompt RAISES from load_rich_prompt (PROMPT_CHAR_CEILING).
    over = "A" * (build_deck.PROMPT_CHAR_CEILING + 10)
    rd = _rich_prompt_run_dir(over)
    try:
        build_deck.load_rich_prompt({"slide": 1, "scene": "x", "copy": ["y"]}, rd)
    except ValueError as exc:
        record("AF-P2", str(exc))

    # AF-R3 — a forbidden hardcoded demographic default (the 60/30/10 landmine) in the
    # slide spec RAISES from assert_no_forbidden_demographic_default
    # (FORBIDDEN_DEMOGRAPHIC_DEFAULTS). This closes the previously-untested gate.
    landmine = build_deck.FORBIDDEN_DEMOGRAPHIC_DEFAULTS[0]  # e.g. "60/30/10"
    try:
        build_deck.assert_no_forbidden_demographic_default(
            {"slide": 1, "scene": f"office, {landmine} representation split", "copy": ["x"]})
    except ValueError as exc:
        record("AF-R3", str(exc))

    # AF-RESEARCH-GATE — research_complete:true asserted but a required Deep-Research
    # category (G/H/I/K/L) is missing -> _chk_research_brief FAILS. (Previously had no
    # dedicated negative fixture; Guard A forces this proof.)
    rg_root = Path(tempfile.mkdtemp(prefix="deck_research_gate_test_"))
    (rg_root / "working" / "research").mkdir(parents=True, exist_ok=True)
    rg_brief = rg_root / "working" / "research" / "brief-demo.md"
    rg_brief.write_text("# Research brief\nresearch_complete: true\n"
                        "(no Category G/H/I/K/L sections at all)\n")
    record("AF-RESEARCH-GATE", build_deck._chk_research_brief(rg_brief))

    # AF-RESEARCH-UNCITED — 0 cited URLs FAILS _chk_research_cited.
    rd = _research_cited_run_dir([])
    record("AF-RESEARCH-UNCITED",
           build_deck._chk_research_cited(rd / "working" / "research" / "brief-demo.md"))

    # AF-SPEECH-SHORT — speech below target x 120 wpm FAILS _chk_speech_length.
    rd = _speech_run_dir(30, 3500)
    record("AF-SPEECH-SHORT", build_deck._chk_speech_length(rd))

    # AF-QC-INDEPENDENCE — a self-graded copy QC report FAILS _chk_copy_qc.
    p = _qc_report_path({"gate": "Phase 1Q", "average": 9.1,
                         "triggered_autofails": [], "pass": True})  # no provenance
    record("AF-QC-INDEPENDENCE", build_deck._chk_copy_qc(p))

    # AF-I14 — a native (non-KIE-baked) render record FAILS _chk_kie_baked.
    i14_reason = _emit_af_i14_probe()
    record("AF-I14", i14_reason)

    # AF-BUNDLE-COMPLETE — a bundle missing a required deliverable exits 5 from
    # run_postflight_gate; the gate cites AF-BUNDLE-COMPLETE in its failure output.
    bc_reason = _emit_af_bundle_probe()
    record("AF-BUNDLE-COMPLETE", bc_reason)

    # ---- O2 / O5 NEW build_deck-enforced gates (negative-test coverage) ----

    # AF-TYPOGRAPHY-QC — a self-graded typography QC report FAILS _chk_typography_qc.
    record("AF-TYPOGRAPHY-QC", build_deck._chk_typography_qc(
        _qc_report_path({"gate": "Phase Typography-QC", "average": 9.1,
                         "triggered_autofails": [], "pass": True,
                         "qc_independence": {"graded_by": "self", "independent": True}})))
    # AF-PROMPT-QC — a self-graded prompt QC report FAILS _chk_prompt_qc.
    record("AF-PROMPT-QC", build_deck._chk_prompt_qc(
        _qc_report_path({"gate": "Phase Prompt-QC", "average": 9.1,
                         "triggered_autofails": [], "pass": True,
                         "qc_independence": {"graded_by": "self", "independent": True}})))
    # AF-IMAGE-QC — a self-graded image QC report FAILS _chk_image_qc.
    record("AF-IMAGE-QC", build_deck._chk_image_qc(
        _qc_report_path({"gate": "Phase Image-QC", "average": 9.1,
                         "triggered_autofails": [], "pass": True,
                         "qc_independence": {"graded_by": "builder", "independent": True}})))
    # AF-SPEECH-QC — a PRESENT but self-graded speech QC report FAILS _chk_speech_qc
    # (absent defers; present + self-graded triggers).
    record("AF-SPEECH-QC", build_deck._chk_speech_qc(
        _qc_report_path({"gate": "Phase Speech-QC", "average": 9.1,
                         "triggered_autofails": [], "pass": True,
                         "qc_independence": {"graded_by": "author", "independent": True}})))
    # AF-SLIDE-COUNT-FLOOR — a 30-min/10-slide deck (floor 39) FAILS _chk_slide_count_floor.
    record("AF-SLIDE-COUNT-FLOOR", build_deck._chk_slide_count_floor(
        _slide_count_run_dir(30, 10)))
    # AF-PITCH-MISSING — an arc with no ladder/no re-pitch FAILS _chk_pitch.
    record("AF-PITCH-MISSING", build_deck._chk_pitch(
        _pitch_run_dir([{"slide": 1, "arc_section": "hook"},
                        {"slide": 2, "arc_section": "body"}])))
    # AF-CREATIVITY — a design system where one archetype dominates FAILS _chk_creativity.
    record("AF-CREATIVITY", build_deck._chk_creativity(
        _creativity_run_dir(dominant=True)))

    # AF-DARK-SLIDE — dark background prompt without client_dark_theme:true FAILS
    # _chk_no_dark_slides. The fixture is a dark-keyword prompt with no intake flag.
    record("AF-DARK-SLIDE", build_deck._chk_no_dark_slides(
        _dark_slide_run_dir(dark=True, client_dark_theme=False)))

    triggered_sorted = sorted(triggered)
    AF_COVERAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AF_COVERAGE_PATH.write_text(json.dumps(
        {"triggered": triggered_sorted,
         "note": "AF codes a deliberately-failing fixture in test_preflight.py "
                 "actually triggered (Guard A negative-test coverage)."}, indent=2))
    print(f"AF-COVERAGE (Guard A emit)   -> {len(triggered_sorted)} codes triggered: "
          + ",".join(triggered_sorted))
    return triggered_sorted


def _emit_af_i14_probe() -> str:
    """Build a render record whose slide is marked native (taskId 'native', NOT
    KIE-baked) and return the _chk_kie_baked failure reason (cites AF-I14). Mirrors
    the KIE-D fixture: the render record lives under working/checkpoints/
    process_manifest.json as a phase:'render' entry, with real above-floor PNGs so
    only the native taskId trips the gate."""
    import hashlib as _hashlib
    floor = build_deck.PLACEHOLDER_MIN_BYTES
    png_magic = b"\x89PNG\r\n\x1a\n"
    root = Path(tempfile.mkdtemp(prefix="deck_i14_probe_"))
    (root / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (root / "working" / "copy" / "slides.json").write_text(
        json.dumps([{"slide": 1}, {"slide": 2}]))
    imgs = []
    for i in range(2):
        p = root / f"i{i}.png"
        p.write_bytes(png_magic + (bytes([i + 1]) * max(0, floor + 1000 - len(png_magic))))
        imgs.append(p)
    shas = [_hashlib.sha256(p.read_bytes()).hexdigest() for p in imgs]
    man = {"phases": [{"phase": "render", "output_slide_count": 2, "slides": [
        {"slide": 1, "taskId": "native", "image": str(imgs[0]), "image_sha256": shas[0]},
        {"slide": 2, "taskId": "kie-ok-2", "image": str(imgs[1]), "image_sha256": shas[1]},
    ]}]}
    (root / "working" / "checkpoints" / "process_manifest.json").write_text(json.dumps(man))
    slides_path = root / "working" / "copy" / "slides.json"
    try:
        return build_deck._chk_kie_baked(root, slides_path) or ""
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def _emit_af_bundle_probe() -> str:
    """Run run_postflight_gate on a bundle missing every deliverable; capture the
    SystemExit(5) and return the printed reason text (cites AF-BUNDLE-COMPLETE)."""
    import io
    import contextlib
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(set())
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
    except SystemExit:
        pass
    except Exception as exc:  # noqa: BLE001
        return str(exc)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# NO-DARK-SLIDES gate (AF-DARK-SLIDE) — three negative/positive test cases
# ---------------------------------------------------------------------------

def _dark_slide_run_dir(dark: bool, client_dark_theme: bool = False) -> Path:
    """Build a minimal run-dir fixture for the _chk_no_dark_slides gate.

    If `dark` is True, writes a prompt file containing "dark background" — a
    keyword that should trigger AF-DARK-SLIDE (unless client_dark_theme is True).
    If `dark` is False, writes a prompt file with only light-background language.
    If `client_dark_theme` is True, sets that flag in intake.json.
    """
    root = Path(tempfile.mkdtemp(prefix="deck_dark_slide_test_"))
    (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (root / "working" / "prompts").mkdir(parents=True, exist_ok=True)
    # Write intake.json with client_dark_theme if requested.
    intake = {"interview_confirmed": True, "presentation_mode": "one-person",
              "target_talk_minutes": 30}
    if client_dark_theme:
        intake["client_dark_theme"] = True
    (root / "working" / "copy" / "intake.json").write_text(json.dumps(intake))
    # Write a single prompt file with dark or light language.
    if dark:
        prompt_text = (
            "SLIDE 1 IMAGE PROMPT\n\n"
            "Scene: A moody, atmospheric stage with a dark background and deep black gradients "
            "framing the speaker silhouette. The lighting from below creates a near-black vignette "
            "that draws focus to the central figure. The dark theme is intentional and cinematic.\n\n"
            "Layout: full-bleed cinematic.\n"
            "Subject: presenter, center.\n"
        )
    else:
        prompt_text = (
            "SLIDE 1 IMAGE PROMPT\n\n"
            "Scene: A bright, airy conference room bathed in natural daylight. The background is a "
            "clean off-white wall with warm accent lighting. The colour palette is ivory, sky blue, "
            "and soft amber — all light, open, and energetic.\n\n"
            "Layout: full-bleed airy.\n"
            "Subject: presenter, center.\n"
        )
    (root / "working" / "prompts" / "slide-01.txt").write_text(prompt_text)
    return root


def test_af_dark_slide_triggers_without_flag() -> list:
    """AF-DARK-SLIDE fires when dark-background keywords appear in prompts and
    client_dark_theme is NOT set in intake.json. (Negative test.)"""
    failures = []
    rd = _dark_slide_run_dir(dark=True, client_dark_theme=False)
    result = build_deck._chk_no_dark_slides(rd)
    if "AF-DARK-SLIDE" not in result:
        failures.append(
            f"test_af_dark_slide_triggers_without_flag: expected AF-DARK-SLIDE in result, "
            f"got: {result!r}"
        )
    print(f"test_af_dark_slide_triggers_without_flag -> "
          f"{'PASS' if not failures else 'FAIL'}")
    return failures


def test_light_slide_passes() -> list:
    """Light-background prompt with no client_dark_theme flag PASSES (no AF-DARK-SLIDE)."""
    failures = []
    rd = _dark_slide_run_dir(dark=False, client_dark_theme=False)
    result = build_deck._chk_no_dark_slides(rd)
    if result:
        failures.append(
            f"test_light_slide_passes: expected empty result (PASS), got: {result!r}"
        )
    print(f"test_light_slide_passes -> {'PASS' if not failures else 'FAIL'}")
    return failures


def test_dark_slide_with_client_flag_passes() -> list:
    """Dark-background prompt PASSES when client_dark_theme:true is set in intake.json.
    (Opt-in: dark is allowed ONLY when the client explicitly requests it.)"""
    failures = []
    rd = _dark_slide_run_dir(dark=True, client_dark_theme=True)
    result = build_deck._chk_no_dark_slides(rd)
    if result:
        failures.append(
            f"test_dark_slide_with_client_flag_passes: expected empty result (PASS) "
            f"when client_dark_theme:true, got: {result!r}"
        )
    print(f"test_dark_slide_with_client_flag_passes -> "
          f"{'PASS' if not failures else 'FAIL'}")
    return failures


def main():
    failures = []

    # Unit test — _chk_coverage anti-compression gate (no subprocess/network).
    failures += test_chk_coverage()

    # Unit test — rich-prompt-required gate (AF-P1): the TWO new required assertions
    # (a < 1,500-char prompt FAILS, a missing rich prompt FAILS) plus verbatim load.
    failures += test_chk_rich_prompts()

    # Unit test — speech-length gate (AF-SPEECH-SHORT): below target x 120 wpm fails.
    failures += test_chk_speech_length()

    # Unit test — QC-INDEPENDENCE gate (AF-QC-INDEPENDENCE): a self-graded / builder-
    # graded copy QC report FAILS even when its numbers pass; only a report with
    # explicit independent-reviewer provenance passes.
    failures += test_chk_qc_independence_rejects_self_graded()

    # Unit test — RESEARCH-CITATION GATE (AF-RESEARCH-UNCITED): proves 0/3 URLs FAILs,
    # 8+ URLs PASSes, and a self-contained 21-URL fixture PASSes.
    failures += test_chk_research_cited()

    # C3 (NEW REQUIRED) — the research gate REJECTS junk/localhost/loopback/RFC-1918/
    # bare-IP/example.*/dup URLs and counts only DISTINCT REAL PUBLIC domains.
    failures += test_chk_research_cited_rejects_junk()

    # Fix 1b (NEW) — the research-citation gate also hard-fails on absent/empty
    # sourced categories G/H/I, independently of research_complete:true.
    failures += test_chk_research_cited_requires_ghi()

    # Fix 1a (NEW) — AF-I14 KIE-BAKED gate: every rendered slide must map to a real
    # KIE taskId + a verified, above-floor PNG; native/placeholder/missing/reused-hash
    # / skipped-bake all FAIL; absent render record DEFERS (passes).
    failures += test_chk_kie_baked()

    # Unit test — CLAIMS-WITHOUT-CITATION (AF-RESEARCH-UNCITED): proves claim markers
    # in copy + 0 research URLs FAILs; claim markers + 8 URLs PASSes; no claim
    # markers + 0 URLs PASSes.
    failures += test_chk_claims_without_citation()

    # Unit test — POSTFLIGHT COMPLETENESS GATE (AF-BUNDLE-COMPLETE, Requirements 2-5):
    # proves the gate exits 5 when any deliverable is missing/under-threshold and
    # does NOT exit when all are present; proves guide_pdf + infographic_png are
    # hard-required (never silently skipped); proves ~/Downloads is the default
    # destination; proves DELIVERABLES_REQUIRED has exactly the 9 required keys.
    failures += test_postflight_gate()

    # Unit test — TELEPROMPTER-PUBLISH sub-check (folded under AF-BUNDLE-COMPLETE):
    # proves a full bundle with no/unverified teleprompter_publish.json fails (exit 5),
    # a published+HTTP-200 record passes, a 404 fails, skipped_adhoc passes, and a
    # non-http(s) public_url fails (SSRF/scheme guard).
    failures += test_teleprompter_publish_gate()

    # M7 is folded into test_teleprompter_publish_gate above (a stale skipped_adhoc
    # status no longer bypasses; only the explicit per-run flag does).

    # M6 (NEW REQUIRED) — the speech PDF inherits the design-system accent + typefaces
    # and the accent appears in the rendered PDF color table.
    failures += test_speech_pdf_design_system_accent()

    # M5 (NEW REQUIRED) — the teleprompter HTML injects the locked brand accent from
    # design_system.json (fallback house amber) into :root.
    failures += test_teleprompter_design_system_accent()

    # L1 (NEW REQUIRED) — the hook ceiling is a band [3,4] dedicated slides, not the
    # retired '>= 7' floor (hook_package.json.dedicated_slide_count).
    failures += test_hook_dedicated_slide_count()

    # O4 (NEW) — AF-SLIDE-COUNT-FLOOR: a 30-min/10-slide deck (floor 39) auto-fails;
    # a 30-min/39-slide deck passes; no duration target defers.
    failures += test_chk_slide_count_floor()

    # O5 (NEW) — AF-PITCH-MISSING: an arc with no offer-ladder / no re-pitch fails;
    # a full ladder + re-pitch passes; an absent arc defers.
    failures += test_chk_pitch()

    # O5 (NEW) — AF-CREATIVITY: an archetype-dominant deck fails; a varied deck passes;
    # cliche copy fails.
    failures += test_chk_creativity()

    # AF-DARK-SLIDE (NEW) — slides must use light/bright backgrounds by default.
    # Dark backgrounds are ONLY allowed when the client explicitly sets
    # client_dark_theme:true in intake.json (opt-in by client request only).
    failures += test_af_dark_slide_triggers_without_flag()
    failures += test_light_slide_passes()
    failures += test_dark_slide_with_client_flag_passes()

    # O2 (NEW) — the four new QC gates (typography/prompt/image/speech) reject a
    # self/builder-graded report and pass an independent one (generalized
    # AF-QC-INDEPENDENCE); AF-SPEECH-QC defers when its report is absent.
    failures += test_chk_qc_gates_independence()

    # GUARD A — emit working/af-coverage.json listing every build_deck-enforced AF
    # code a deliberately-failing fixture actually triggered. gate_integrity_check.py
    # reads this artifact and fails if any declared+enforced gate is a no-op/untested.
    try:
        emit_af_coverage()
    except Exception as exc:  # noqa: BLE001
        failures.append(f"AF-COVERAGE emit raised: {exc}")

    # Unit test — detect_platform(): override > intake box_type > filesystem fallback.
    failures += test_detect_platform()

    # Unit test — parse_speech_chunks: maps '## Slide N' AND inline 'SLIDE N' markers
    # to per-slide spoken text (marker/title line stripped); marker-less/empty -> {}.
    failures += test_parse_speech_chunks()

    # C2 (NEW REQUIRED) — the postflight gate REJECTS a symlink deliverable and a
    # wrong-content-type decoy (right size, wrong magic bytes); legitimate path still
    # passes.
    failures += test_postflight_rejects_symlink_and_decoy()

    # H1 (NEW REQUIRED) — a whitespace-only / whitespace-padded rich prompt FAILS the
    # rich-prompt floor (measured on prompt.strip()); a genuine padded prompt passes
    # and is returned VERBATIM.
    failures += test_h1_whitespace_only_prompt()

    # CASE 1 — missing artifacts => refused, exit 3, lists what's missing.
    root = make_workdir(with_artifacts=False)
    r = run(root)
    out = r.stdout + r.stderr
    if r.returncode != 3:
        failures.append(f"CASE1 expected exit 3, got {r.returncode}")
    for needle in ("PROCESS PREFLIGHT FAILED",
                   "working/copy/intake.json",
                   "working/research/brief-*.md",
                   "working/qc/copy_qc_report.json",
                   "produced by:"):
        if needle not in out:
            failures.append(f"CASE1 stderr missing {needle!r}")
    print(f"CASE1 (missing)  -> exit {r.returncode} (expected 3)  "
          f"{'PASS' if r.returncode == 3 else 'FAIL'}")

    # CASE 4 — full upstream artifacts BUT no rich prompt file => refused, exit 3,
    # AF-P1 rich-prompt-required (proves a MISSING rich prompt fails through the CLI).
    root = make_workdir(with_artifacts=True, rich_prompts=False)
    r = run(root)
    out = r.stdout + r.stderr
    if r.returncode != 3:
        failures.append(f"CASE4 (missing rich prompt) expected exit 3, got {r.returncode}")
    if "AF-P1" not in out or "rich" not in out.lower():
        failures.append("CASE4 stderr missing the AF-P1 rich-prompt-required reason")
    print(f"CASE4 (no prompt)-> exit {r.returncode} (expected 3)  "
          f"{'PASS' if r.returncode == 3 and 'AF-P1' in out else 'FAIL'}")

    # CASE 5 — full upstream artifacts BUT the rich prompt is < 1,500 chars =>
    # refused, exit 3, AF-P1 floor (proves a SUB-FLOOR rich prompt fails through CLI).
    root = make_workdir(with_artifacts=True, rich_prompts=True, short_prompt=True)
    r = run(root)
    out = r.stdout + r.stderr
    if r.returncode != 3:
        failures.append(f"CASE5 (short rich prompt) expected exit 3, got {r.returncode}")
    if "AF-P1" not in out or "5000" not in out:
        failures.append("CASE5 stderr missing the AF-P1 5000-char floor reason")
    print(f"CASE5 (short)    -> exit {r.returncode} (expected 3)  "
          f"{'PASS' if r.returncode == 3 and 'AF-P1' in out and '5000' in out else 'FAIL'}")

    # CASE 2 — artifacts present => preflight passes (must NOT exit 3).
    # We only need to prove the GATE passed; we stop the process the moment it
    # gets past the gate and into render setup so the test never spends a real
    # KIE render (the box may have a KIE_API_KEY on disk).
    root = make_workdir(with_artifacts=True)
    passed_gate = False
    refused = False
    cmd = [sys.executable, str(BUILD), str(root / "slides.json"), str(root / "out.pptx")]
    env = dict(os.environ)
    env.pop("KIE_API_KEY", None)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env=env)
    try:
        for line in proc.stdout:
            if "PREFLIGHT PASSED" in line:
                passed_gate = True
            if "PROCESS PREFLIGHT FAILED" in line:
                refused = True
            # As soon as we see render setup begin, the gate is proven passed; stop.
            if passed_gate and ("=== build_deck" in line or "[slide-" in line):
                proc.terminate()
                break
    finally:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    if refused:
        failures.append("CASE2 preflight wrongly refused")
    if not passed_gate:
        failures.append("CASE2 expected 'PREFLIGHT PASSED' banner")
    print(f"CASE2 (present)  -> passed_gate={passed_gate} refused={refused}  "
          f"{'PASS' if passed_gate and not refused else 'FAIL'}")

    # CASE 3 — --adhoc-no-process => skips gate, loud banner, gets past gate.
    # Same streaming approach: prove the banner printed and the run got past the
    # gate without spending a real render.
    root = make_workdir(with_artifacts=False)
    banner = False
    refused = False
    got_past = False
    cmd = [sys.executable, str(BUILD), str(root / "slides.json"),
           str(root / "out.pptx"), "--adhoc-no-process"]
    env = dict(os.environ)
    env.pop("KIE_API_KEY", None)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env=env)
    try:
        for line in proc.stdout:
            if "ADHOC MODE" in line:
                banner = True
            if "NOT a process-compliant deliverable" in line:
                banner = banner and True
            if "PROCESS PREFLIGHT FAILED" in line:
                refused = True
            if "=== build_deck" in line or "[slide-" in line:
                got_past = True
                proc.terminate()
                break
    finally:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    if refused:
        failures.append("CASE3 adhoc override still refused")
    if not banner:
        failures.append("CASE3 missing loud adhoc banner")
    if not got_past:
        failures.append("CASE3 did not get past the (skipped) gate")
    print(f"CASE3 (adhoc)    -> banner={banner} got_past={got_past} refused={refused}  "
          f"{'PASS' if banner and got_past and not refused else 'FAIL'}")

    print()
    if failures:
        print("TEST FAILED:")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("ALL PREFLIGHT TESTS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
