#!/usr/bin/env python3
"""test_webinar_intro_outro.py — Feature L2-H (webinar framing layer) unit tests.

Covers the offline, deterministic surfaces of webinar_intro_outro.py and its
wiring into synthesize_full_speech.py:

  1. SECTION GENERATION:
       * welcome targets ~5 min (~650 words at 130 wpm), +/-12%.
       * qa targets ~2 min (~260 words), +/-12%.
       * close targets ~3 min (~390 words), +/-12%.
       * every section rotates >= 2 distinct Fish reader tags (no flat reads).

  2. CONTENT REQUIREMENTS (the "feels like a real webinar" checklist):
       * welcome: greeting, housekeeping, made-up attendee first names
         (Stephanie, Thomas, Jill, Marcus, David, Sarah), a light joke, two chat
         prompts, and the frame (the problem + why it matters now + outcomes).
       * qa: attendee questions are answered confidently (name + location +
         question + an expertise-proving answer), and an email CTA is offered.
       * close: an emotional crescendo — the "boulder" achievement, what they now
         know, and a call to act.

  3. INJECTION / EXTRACTION:
       * inject_framing puts the WELCOME section before the first `## Slide N`
         and the Q&A + CLOSE after the last slide.
       * extract_deck_body strips exactly the framing sections and preserves the
         deck body WORD-FOR-WORD (via speech_fish_tag.verify_strip_equals_source),
         so the deck-only verify gate keeps passing.
       * verify_sections() reports word counts inside the +/-12% band.

NO network, NO audio, NO API calls — tmp_path / in-memory only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import webinar_intro_outro as w
import speech_fish_tag as sf
import synthesize_full_speech as synthesize

# ---------------------------------------------------------------------------
# A representative 2-slide tagged deck (the deck contract shape).
# ---------------------------------------------------------------------------
_TAGGED_DECK = """# PRESENTER'S SPEECH -- test
DURATION_MIN: 30.0 | SPOKEN_RATE_WPM: 130

## Slide 1 -- Welcome  (HOOK)
> STAGE: HOOK  KIND: normal  BUDGET: 50w  ACTUAL: 50w  SECONDS: 23s
[deliberate and measured] Have you ever felt that hesitation right before a prospect says no? The friction to buy is real.
[pause]

---

## Slide 2 -- The close  (CLOSE)
> STAGE: CLOSE  KIND: normal  BUDGET: 50w  ACTUAL: 50w  SECONDS: 23s
[sincere, warm] Thank you for being here. Make the decision tonight.
"""

_UNTAGGED_DECK = w.strip_tags(_TAGGED_DECK)


def _count_words(text: str) -> int:
    return w.word_count(text)


# ---------------------------------------------------------------------------
# 1. SECTION GENERATION + WORD BUDGETS
# ---------------------------------------------------------------------------

def test_intro_word_budget():
    body = w.generate_intro()
    n = _count_words(body)
    assert w.INTRO_TARGET_WORDS * (1 - w.TOLERANCE) <= n <= w.INTRO_TARGET_WORDS * (1 + w.TOLERANCE), \
        f"intro words {n} outside +/-{w.TOLERANCE:.0%} of {w.INTRO_TARGET_WORDS}"


def test_qa_word_budget():
    body = w.generate_qa()
    n = _count_words(body)
    assert w.QA_TARGET_WORDS * (1 - w.TOLERANCE) <= n <= w.QA_TARGET_WORDS * (1 + w.TOLERANCE), \
        f"qa words {n} outside +/-{w.TOLERANCE:.0%} of {w.QA_TARGET_WORDS}"


def test_close_word_budget():
    body = w.generate_crescendo_close()
    n = _count_words(body)
    assert w.CLOSE_TARGET_WORDS * (1 - w.TOLERANCE) <= n <= w.CLOSE_TARGET_WORDS * (1 + w.TOLERANCE), \
        f"close words {n} outside +/-{w.TOLERANCE:.0%} of {w.CLOSE_TARGET_WORDS}"


def test_each_section_rotates_at_least_two_tags():
    """No flat reads: each section must use >= 2 distinct bracket reader tags."""
    cases = [
        ("welcome", w.generate_intro()),
        ("qa", w.generate_qa()),
        ("close", w.generate_crescendo_close()),
    ]
    for name, body in cases:
        tags = {m.group(1) for m in re.finditer(r"^\s*\[([^\]]*)\]", body, re.M)}
        assert len(tags) >= 2, f"{name} used only {len(tags)} distinct tags: {tags}"


# ---------------------------------------------------------------------------
# 2. CONTENT REQUIREMENTS
# ---------------------------------------------------------------------------

def test_welcome_has_greeting_housekeeping_names_joke_chat_frame():
    body = w.generate_intro()
    low = body.lower()
    assert "welcome" in low, "no greeting"
    assert "recorded" in low and "twenty four hours" in low, "no housekeeping/replay"
    for name in ("stephanie", "thomas", "jill", "marcus", "david", "sarah"):
        assert name in low, f"made-up attendee {name} not greeted"
    assert "confession" in low or "break the ice" in low, "no light joke / warm aside"
    assert "chat" in low and "number one thing" in low, "no interactive chat prompt"
    assert "holding your business back" in low, "no 'what's holding you back' prompt"
    assert "friction to buy" in low, "no problem frame"
    assert "three things" in low, "no outcomes/objectives list"


def test_qa_answers_questions_and_offers_email():
    body = w.generate_qa()
    low = body.lower()
    assert "jill from florida" in low, "no Jill question"
    assert "will this work for a service business" in low, "no service-business question"
    assert "thomas from washington" in low, "no Thomas question"
    assert "marcus asks" in low, "no Marcus question"
    assert "send them to the address on the screen" in low, "no email CTA"
    assert "personally get back to you" in low, "no personal-reply promise"


def test_close_is_crescendo_with_boulder_and_call_to_act():
    body = w.generate_crescendo_close()
    low = body.lower()
    assert "boulder" in low, "no boulder (achievement) weave"
    assert "friction" in low, "no friction payoff"
    assert "call" in body or "ask" in low, "no call to act"
    assert "tonight" in low or "today" in low or "right now" in low, "no immediacy"
    assert "thank you for being here" in low, "no grateful close"


# ---------------------------------------------------------------------------
# 3. INJECTION / EXTRACTION
# ---------------------------------------------------------------------------

def test_inject_framing_places_welcome_before_first_slide():
    rewritten = w.inject_framing(_TAGGED_DECK)
    pos_welcome = rewritten.index("## Section WELCOME")
    pos_slide1 = rewritten.index("## Slide 1")
    pos_qna = rewritten.index("## Section QNA")
    pos_close = rewritten.index("## Section CLOSE")
    pos_slide2 = rewritten.index("## Slide 2")
    assert pos_welcome < pos_slide1, "welcome must come before Slide 1"
    assert pos_slide2 < pos_qna < pos_close, "Q&A + close must come after the last slide"


def test_extract_deck_body_preserves_deck_word_for_word():
    rewritten = w.inject_framing(_TAGGED_DECK)
    deck_body = w.extract_deck_body(rewritten)
    # No framing sections left.
    assert "## Section WELCOME" not in deck_body
    assert "## Section QNA" not in deck_body
    assert "## Section CLOSE" not in deck_body
    # The SPOKEN contract is preserved word-for-word (the load-bearing gate that
    # synthesize_full_speech.py actually checks before synthesizing).
    assert sf.verify_strip_equals_source(
        synthesize.extract_spoken(deck_body),
        synthesize.extract_spoken(_TAGGED_DECK),
    ), "extract_deck_body changed the deck SPOKEN content"


def test_extract_deck_body_preserves_raw_deck_modulo_trailing_ws():
    """The raw deck text is preserved byte-for-byte except for a trailing blank
    line (injection normalizes the final newline)."""
    rewritten = w.inject_framing(_TAGGED_DECK)
    deck_body = w.extract_deck_body(rewritten)
    assert deck_body.rstrip() == _TAGGED_DECK.rstrip(), "raw deck text changed"


def test_extract_deck_body_untouched_deck():
    """extract_deck_body on a deck with no framing is a no-op."""
    assert w.extract_deck_body(_TAGGED_DECK) == _TAGGED_DECK


def test_rewrite_webinar_speech_returns_all_sections():
    rewritten = w.rewrite_webinar_speech(_TAGGED_DECK)
    for section in ("WELCOME", "QNA", "CLOSE"):
        assert f"## Section {section}" in rewritten, f"missing {section} section"


def test_verify_sections_all_in_band():
    report = w.verify_sections()
    for name, r in report.items():
        assert r["within_band"], f"{name} words {r['words']} not in +/-{w.TOLERANCE:.0%} band"
        assert r["n_distinct_tags"] >= 2, f"{name} has flat tags"


# ---------------------------------------------------------------------------
# 4. F-H WIRING LOCKSTEP — the webinar framing is a dedicated manifest phase, not a
#    silent flag someone can omit. These tests prove the four-part contract the
#    diagnosis (PROCESS-WIRING-DIAGNOSIS.md, GAP 1) requires: manifest phase with
#    --webinar-intro-outro executor, AF code in manifest + ruleset, verifier
#    registered.
# ---------------------------------------------------------------------------

def _manifest_path():
    """Deployed layout first (scripts/../sops/PIPELINE-MANIFEST.json), repo
    walk-up fallback (universal-sops/presentation-slide-craft/) — mirrors
    manifest_source.resolve_manifest's installed-then-cluster tiering."""
    here = Path(__file__).resolve().parent
    deployed = here.parent.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    cur = here
    for _ in range(12):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def test_fh_manifest_declares_webinar_intro_phase():
    """P9-SPEECH-WEBINAR-INTRO must be a declared manifest phase whose executor passes
    --webinar-intro-outro to synthesize_full_speech.py and produces the webinarized
    audio. A framing feature with no phase can be skipped — the diagnosis's GAP 1."""
    mp = _manifest_path()
    assert mp is not None, "PIPELINE-MANIFEST.json not found"
    man = json.loads(mp.read_text())
    phases = {p.get("id"): p for p in man.get("phases", [])}
    ph = phases.get("P9-SPEECH-WEBINAR-INTRO")
    assert ph is not None, "P9-SPEECH-WEBINAR-INTRO phase missing from the manifest"
    # It must sit AFTER FISH-TAG (which produces the tagged speech it consumes).
    orders = {p["id"]: p.get("order") for p in man.get("phases", [])}
    assert orders.get("P9-SPEECH-WEBINAR-INTRO") > orders.get("P8.4-FISH-TAG", 0), (
        "P9-SPEECH-WEBINAR-INTRO must run after P8.4-FISH-TAG (it consumes the tagged speech)")
    ex = ph.get("executor") or {}
    assert ex.get("kind") == "script", "P9-SPEECH-WEBINAR-INTRO executor kind is not 'script'"
    cmd = ex.get("cmd", "")
    assert "synthesize_full_speech.py" in cmd, "executor does not name synthesize_full_speech.py"
    assert "--webinar-intro-outro" in cmd, "executor does not pass --webinar-intro-outro"
    assert "PRESENTER-AUDIO-WEBINAR.mp3" in cmd, (
        "executor does not produce PRESENTER-AUDIO-WEBINAR.mp3")
    assert "PRESENTERS-SPEECH-FISH-TAGGED.md" in cmd, (
        "executor does not consume the FISH-TAGGED speech (--tagged-speech)")
    assert "AF-WEBINAR-INTRO" in ph.get("gate_codes", []), (
        "P9-SPEECH-WEBINAR-INTRO does not carry the AF-WEBINAR-INTRO gate code")


def test_fh_af_webinar_intro_registered_manifest_and_ruleset():
    """AF-WEBINAR-INTRO must be registered in BOTH the manifest autofails and the MASTER
    ruleset Section-5 table (sync_check A4 direction: every ruleset code must be a
    manifest code; and the phase carries it as a gate)."""
    import sys as _sys
    from pathlib import Path as _Path
    mp = _manifest_path()
    assert mp is not None, "PIPELINE-MANIFEST.json not found"
    man = json.loads(mp.read_text())
    codes = {a.get("code") for a in man.get("autofails", [])}
    assert "AF-WEBINAR-INTRO" in codes, "AF-WEBINAR-INTRO missing from PIPELINE-MANIFEST.autofails"

    # Ruleset Section-5 row must exist (resolved the same way sync_check does).
    here = _Path(__file__).resolve().parent.parent
    _sys.path.insert(0, str(here))
    import manifest_source
    ruleset_path, _ = manifest_source.resolve_ruleset(here)
    assert ruleset_path is not None and _Path(ruleset_path).is_file(), (
        "MASTER ruleset not resolved")
    text = _Path(ruleset_path).read_text()
    # Isolate Section 5 exactly as sync_check.parse_master_ruleset_section5 does.
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if "MACHINE-CHECKABLE SUMMARY TABLE" in ln.upper()), None)
    assert start is not None, "ruleset Section 5 (MACHINE-CHECKABLE SUMMARY TABLE) not found"
    section = "\n".join(lines[start:])
    assert "AF-WEBINAR-INTRO" in section, (
        "AF-WEBINAR-INTRO missing from MASTER ruleset Section-5 table")


def test_fh_verifier_registered_and_fails_closed_on_missing():
    """phase_verifiers must register P9-SPEECH-WEBINAR-INTRO, and the verifier must FAIL
    (not pass) when the webinarized audio is absent — the anti-skip substance proof."""
    import sys as _sys
    from pathlib import Path as _Path
    here = _Path(__file__).resolve().parent.parent
    _sys.path.insert(0, str(here))
    import phase_verifiers as pv
    assert "P9-SPEECH-WEBINAR-INTRO" in pv.PHASE_VERIFIERS, (
        "P9-SPEECH-WEBINAR-INTRO not registered in phase_verifiers.PHASE_VERIFIERS")
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        rd = _Path(t)
        ok, reasons = pv.verify("P9-SPEECH-WEBINAR-INTRO", rd)
        assert ok is False, "verifier must fail closed when the webinarized audio is absent"
        assert any("PRESENTER-AUDIO-WEBINAR" in r for r in reasons), (
            f"failure reason must name the missing artifact, got {reasons}")
