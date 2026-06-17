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
        # Research brief with >= MIN_CITED_SOURCES (8) real cited URLs so the
        # AF-RESEARCH-UNCITED gate passes.  Each URL is on its own line and is a
        # distinct authoritative source (the gate counts distinct URLs, not lines).
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
        )
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
      (d) Full bundle + status=skipped_adhoc                      -> PASSES (ad-hoc).
      (e) Full bundle + public_url that is not http(s) (file://)  -> exit 5.

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

    # (d) status=skipped_adhoc -> PASSES (ad-hoc output is not a client deliverable).
    bundle_dir, ledger_path, slug = _postflight_bundle_dir(all_keys, with_publish=False)
    _write_publish_ledger(bundle_dir, status="skipped_adhoc", verified_http_status=None)
    try:
        build_deck.run_postflight_gate(bundle_dir, ledger_path, slug)
    except SystemExit as exc:
        fails.append(f"TELE-D: skipped_adhoc should PASS, got sys.exit({exc.code})")
    except Exception as exc:  # noqa: BLE001
        fails.append(f"TELE-D: unexpected error: {exc}")
    print(f"TELE-D (skipped_adhoc)       -> {'PASS' if not [f for f in fails if 'TELE-D' in f] else 'FAIL'}")

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
    (root / "working" / "research" / "brief-demo.md").write_text("".join(lines))
    return root


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
    whitespace_only = (" \t\n" * 1000)  # ~3,000 raw chars, 0 non-whitespace
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


def main():
    failures = []

    # Unit test — _chk_coverage anti-compression gate (no subprocess/network).
    failures += test_chk_coverage()

    # Unit test — rich-prompt-required gate (AF-P1): the TWO new required assertions
    # (a < 1,500-char prompt FAILS, a missing rich prompt FAILS) plus verbatim load.
    failures += test_chk_rich_prompts()

    # Unit test — speech-length gate (AF-SPEECH-SHORT): below target x 120 wpm fails.
    failures += test_chk_speech_length()

    # Unit test — RESEARCH-CITATION GATE (AF-RESEARCH-UNCITED): proves 0/3 URLs FAILs,
    # 8+ URLs PASSes, and a self-contained 21-URL fixture PASSes.
    failures += test_chk_research_cited()

    # C3 (NEW REQUIRED) — the research gate REJECTS junk/localhost/loopback/RFC-1918/
    # bare-IP/example.*/dup URLs and counts only DISTINCT REAL PUBLIC domains.
    failures += test_chk_research_cited_rejects_junk()

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
