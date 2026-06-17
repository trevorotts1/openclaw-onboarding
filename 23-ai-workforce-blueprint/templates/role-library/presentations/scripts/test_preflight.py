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
# >= PROMPT_CHAR_FLOOR (1,500) is the HARD floor; build it well over the floor.
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
) * 4  # ~4x => comfortably over the 1,500 floor, under the 18,000 ceiling


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
    (root / "slides.json").write_text(json.dumps(SLIDES))
    if with_artifacts:
        (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
        (root / "working" / "research").mkdir(parents=True, exist_ok=True)
        (root / "working" / "qc").mkdir(parents=True, exist_ok=True)
        (root / "working" / "prompts").mkdir(parents=True, exist_ok=True)
        _write_intake(root)
        (root / "working" / "research" / "brief-demo.md").write_text(
            "# Research brief\nresearch_complete: true\nCategories A,C,D,F,G,H,I,K,L\n")
        (root / "working" / "qc" / "copy_qc_report.json").write_text(json.dumps(
            {"gate": "Phase 1Q", "average": 9.1, "triggered_autofails": [], "pass": True}))
        # Phase 3 — converting arc allocation (Signature Presentation Architect).
        (root / "working" / "copy" / "arc_allocation.json").write_text(json.dumps(
            [{"slide": 1, "arc_section": "hook"}]))
        # Phase 4 — slide copy authored per doctrine.
        (root / "working" / "copy" / "slides_copy.md").write_text(
            "# Slide copy\n" + ("Authored converting copy per doctrine. " * 40) + "\n")
        # Phase F — typography/design brief (per-slide art direction).
        (root / "working" / "research" / "design-brief-demo.md").write_text(
            "# Design brief\n" + ("Per-slide art direction and typography. " * 20) + "\n")
        # Phase 2 — rich per-slide prompt(s) (rendered VERBATIM). One slide => slide-01.txt.
        if rich_prompts:
            text = "short prompt" if short_prompt else RICH_PROMPT
            (root / "working" / "prompts" / "slide-01.txt").write_text(text)
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
    assert build_deck.PROMPT_CHAR_FLOOR == 1500, \
        f"PROMPT_CHAR_FLOOR must be 1500, got {build_deck.PROMPT_CHAR_FLOOR}"

    valid = RICH_PROMPT
    assert len(valid) >= 1500, "test fixture RICH_PROMPT must be >= 1500 chars"
    short = "way too thin to be a real slide prompt"  # well under 1,500

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


def main():
    failures = []

    # Unit test — _chk_coverage anti-compression gate (no subprocess/network).
    failures += test_chk_coverage()

    # Unit test — rich-prompt-required gate (AF-P1): the TWO new required assertions
    # (a < 1,500-char prompt FAILS, a missing rich prompt FAILS) plus verbatim load.
    failures += test_chk_rich_prompts()

    # Unit test — speech-length gate (AF-SPEECH-SHORT): below target x 120 wpm fails.
    failures += test_chk_speech_length()

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
    if "AF-P1" not in out or "1500" not in out:
        failures.append("CASE5 stderr missing the AF-P1 1500-char floor reason")
    print(f"CASE5 (short)    -> exit {r.returncode} (expected 3)  "
          f"{'PASS' if r.returncode == 3 and 'AF-P1' in out and '1500' in out else 'FAIL'}")

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
