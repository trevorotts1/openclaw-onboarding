#!/usr/bin/env python3
"""test_gip_weave_af_p24.py -- pins FIX-PLAN Item 26 (the GIP doctrine weave):
AF-P24, the five SOP-GIP-01 v2.0 BlackCEO negative classes, enforced on prompts
that cast a Black / African-descended subject.

What is proven here:
  * ACCEPT: a fully GIP-conformant Black-subject slide prompt (8 base classes +
    5 BlackCEO classes + per-string spelling-lock + density signals) clears the
    SHARED gate end to end (prompt_gate.prompt_problems == [] and verify_prompt
    returns the text) and clears build_deck.rich_prompt_quality_problems.
  * REJECT per class: dropping any ONE of the five BlackCEO sentences makes
    BOTH gates report AF-P24 naming exactly that class.
  * REJECT spelling-lock: a Black-subject prompt with the BlackCEO classes but
    no spelling-lock still fails AF-P14 (the pre-existing teeth are untouched).
  * REJECT base class: a prompt missing a base class still fails AF-P13.
  * SCOPE CONTROL: a prompt with NO Black subject and no BlackCEO classes does
    NOT fire AF-P24 (the classes are conditional, exactly as SOP-GIP-01 v2.0
    scopes them), so existing non-Black-subject decks see no verdict change.
  * TWIN PARITY: prompt_gate and build_deck carry identical token tables and
    identical helper verdicts (the two gates share teeth by discipline).
  * REGISTRATION: AF-P24 is in PIPELINE-MANIFEST.json (build_deck-enforced,
    py_symbol resolves in build_deck.py), in the cluster MASTER ruleset
    Section 5, in the dept SOP-SLIDE-00 table, and in the enforcement registry.

The deterministic measurer's C6b block (build_deck.check_prompt_qc_deterministic)
emits AF-P24 from the same _blackceo_negative_class_problems helper covered
here; a full run-dir measurer fixture is out of scope for this file (no sibling
test builds one either).

Flat file inside tests/, manages its own import path -- matching every sibling.
No network, no credentials.
"""
from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
REPO = SCRIPTS
for _ in range(6):
    if (REPO / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json").is_file():
        break
    REPO = REPO.parent

import pytest  # noqa: E402

import build_deck as bd  # noqa: E402
import prompt_gate as pg  # noqa: E402

COPY = "Stop Guessing. Start Closing."

BLACKCEO_SENTENCES = {
    "BlackCEO skin chromatic depth":
        "Do not render melanated skin as gray, ashy, muddy, dull, or desaturated.",
    "BlackCEO hair strand integrity":
        "Do not crush Black hair to featureless black; preserve individual strands and shape.",
    "BlackCEO skin microtexture":
        "Do not smooth skin to plastic/wax/CGI; preserve fine microtexture.",
    "BlackCEO hairstyle fidelity":
        "Do not replace a specified hairstyle with a generic one or fuse braids into clothing.",
    "BlackCEO skin-tone direction lock":
        "Do not lighten deep skin in aspirational scenes or darken it for dramatic effect.",
}


def _conformant_prompt(chars: int = 19400, black_subject: bool = True,
                       drop_bc_class: str | None = None,
                       spelling_lock: bool = True,
                       english_pin: bool = True,
                       drop_base_sentence: str | None = None) -> str:
    """A rich slide prompt in the prove_pres_prompt_floor fixture shape (head +
    parameterized distinct body + DO-NOT BLOCK + English pin), carrying a Black
    woman founder cast with a SOP-GIP-01 v2.0 skin-tone library label, the full
    8 base negative classes, and (unless dropped) the 5 BlackCEO classes."""
    subject = (
        "People: a Black woman founder, role chief executive, skin tone espresso brown, "
        "hairstyle silk press with clearly defined strands and true shape, attire tailored "
        "charcoal suit, expression determined gaze with relaxed shoulders. Melanated skin "
        "rendered chromatically rich, warm brown with golden and subtle red undertones, "
        "natural pore-level skin texture preserved, dimensional beauty lighting with a "
        "rim light separating her hair from the background. "
        if black_subject else
        "People: a founder at a standing desk, tailored charcoal suit, determined gaze "
        "with relaxed shoulders, dimensional lighting with a rim light. "
    )
    lock = (
        f'HEADLINE VERBATIM + SPELLING-LOCK: render this exact string letter-for-letter, '
        f'spelled exactly: "{COPY}". ' if spelling_lock else
        f'HEADLINE VERBATIM: the headline reads "{COPY}". '
    )
    head = (
        "[ARCHETYPE: split-hero editorial]\n"
        "Composition: rule of thirds grid, headline in the upper-third safe margin, "
        "focal point in the right third. Palette anchored on brand hex #0A2540 with an "
        "accent of #F2B134. Headline typography set at 96pt bold, subhead at 42pt.\n"
        + lock + subject
    )
    vocab = (
        "photoreal cinematic boardroom dusk amber glass table reflection confident "
        "tailored poised gesture layered depth bokeh shallow aperture volumetric haze "
        "directional key soft fill practical sconces warm tungsten cool teal contrast "
        "graded editorial magazine luminous shadows highlights specular skyline window "
        "twilight metropolitan architectural leading lines negative space typographic "
        "hierarchy kerning tracking baseline ligature counters serif humanist geometric "
        "grotesque palette saturation vibrance clarity texture grain filmic anamorphic"
    ).split()
    base_sentences = [
        "Do not render any misspelled or garbled text; render every quoted letter-for-letter.",
        "Do not redraw, recolor, or reinterpret the logo or monogram.",
        "Do not include any placeholder, bracketed token, or TBD build note.",
        "Do not add presenter narration, stage direction, or webinar self-talk into the picture.",
        "Do not produce anatomical artifacts such as a fused hand, extra limb, or malformed fingers.",
        "Do not let a busy cluttered background compete behind any text zone; keep legible negative space.",
        "Do not lighten, ashen, or desaturate any deep skin tone; preserve skin-tone fidelity.",
        "Do not add a watermark, emoji, clipart, Calibri or Arial system default font, or any UI artifact.",
    ]
    if not spelling_lock:
        # The class-1 sentence above itself carries a "letter-for-letter" lock
        # token; a lock-free variant must strip it while still naming class 1.
        base_sentences[0] = "Do not render any misspelled or garbled text in any element."
    if drop_base_sentence:
        base_sentences = [s for s in base_sentences if drop_base_sentence not in s]
    bc = [s for cls, s in BLACKCEO_SENTENCES.items() if cls != drop_bc_class]
    do_not = ("\n\nDO-NOT BLOCK:\n" + " ".join(base_sentences + (bc if black_subject else []))
              + "\n") + ("\n" + pg.ENGLISH_PIN if english_pin else "")
    room = chars - len(head) - len(do_not.rstrip())
    body = []
    for i in range(room // 150 + 2):
        w = vocab[i % len(vocab)]
        body.append(
            f"Detail {i}: the {w} element is described with a distinct clause "
            f"number {i} carrying its own descriptive nuance about lighting palette "
            f"placement and mood so the prompt reads rich and specific throughout stage {i}.")
    return head + " ".join(body)[:max(room, 0)] + do_not.rstrip()


def _af(problems, code):
    return [p for p in problems if p.startswith(code)]


# ===========================================================================
# ACCEPT
# ===========================================================================
class TestAccept:
    def test_shared_gate_accepts_fully_conformant_black_subject_prompt(self):
        prompt = _conformant_prompt()
        assert pg.prompt_problems(prompt, COPY) == []
        assert pg.verify_prompt(prompt, COPY) == prompt

    def test_build_deck_quality_layer_accepts(self):
        assert bd.rich_prompt_quality_problems(_conformant_prompt(), COPY) == []

    def test_helper_verdicts_clean(self):
        lc = _conformant_prompt().lower()
        assert pg._blackceo_negative_class_problems(lc) == []
        assert bd._blackceo_negative_class_problems(lc) == []


# ===========================================================================
# REJECT -- one BlackCEO class at a time, named by AF-P24 in both gates
# ===========================================================================
class TestRejectBlackCEOClasses:
    @pytest.mark.parametrize("cls", sorted(BLACKCEO_SENTENCES))
    def test_each_missing_class_named(self, cls):
        prompt = _conformant_prompt(drop_bc_class=cls)
        for problems in (pg.rich_prompt_quality_problems(prompt, COPY),
                         bd.rich_prompt_quality_problems(prompt, COPY)):
            hits = _af(problems, "AF-P24")
            assert len(hits) == 1, f"expected exactly one AF-P24 problem, got {problems}"
            assert cls in hits[0]
            # and ONLY that class is named missing
            for other in BLACKCEO_SENTENCES:
                if other != cls:
                    assert other not in hits[0]

    def test_full_gate_rejects_missing_class(self):
        prompt = _conformant_prompt(drop_bc_class="BlackCEO skin microtexture")
        hits = _af(pg.prompt_problems(prompt, COPY), "AF-P24")
        assert hits and "BlackCEO skin microtexture" in hits[0]
        with pytest.raises(pg.PromptGateError):
            pg.verify_prompt(prompt, COPY)


# ===========================================================================
# REJECT -- the pre-existing teeth are untouched (AF-P14 / AF-P13)
# ===========================================================================
class TestExistingTeethUnchanged:
    def test_missing_spelling_lock_still_fails_af_p14(self):
        # Measured on the AUTHORED prompt (no English pin): the mandatory pin
        # itself carries a "letter-for-letter" phrase, so a submitted prompt
        # always has a lock token; the authoring floor is what AF-P14 guards.
        prompt = _conformant_prompt(spelling_lock=False, english_pin=False)
        for problems in (pg.rich_prompt_quality_problems(prompt, COPY),
                         bd.rich_prompt_quality_problems(prompt, COPY)):
            assert _af(problems, "AF-P14"), problems
            assert not _af(problems, "AF-P24"), problems

    def test_missing_base_class_still_fails_af_p13(self):
        prompt = _conformant_prompt(drop_base_sentence="watermark")
        for problems in (pg.rich_prompt_quality_problems(prompt, COPY),
                         bd.rich_prompt_quality_problems(prompt, COPY)):
            assert _af(problems, "AF-P13"), problems


# ===========================================================================
# SCOPE CONTROL -- no Black subject, no AF-P24 (verdicts on existing decks hold)
# ===========================================================================
class TestScopeControl:
    def test_non_black_subject_prompt_not_bound(self):
        prompt = _conformant_prompt(black_subject=False)
        assert pg._blackceo_negative_class_problems(prompt.lower()) == []
        assert bd._blackceo_negative_class_problems(prompt.lower()) == []
        assert not _af(pg.rich_prompt_quality_problems(prompt, COPY), "AF-P24")
        assert not _af(bd.rich_prompt_quality_problems(prompt, COPY), "AF-P24")

    def test_library_label_alone_binds(self):
        # A skin-tone library label with no explicit "Black" naming still casts a
        # melanated subject (SOP-CAST-01 Section 8 vocabulary), so AF-P24 binds.
        lc = "people: a founder, skin tone espresso brown, silk press hairstyle."
        assert pg._black_subject_present(lc)
        assert len(pg._blackceo_negative_class_problems(lc)) == 5


# ===========================================================================
# TWIN PARITY + REGISTRATION
# ===========================================================================
class TestParityAndRegistration:
    def test_token_tables_identical(self):
        assert pg.BLACKCEO_NEGATIVE_BLOCK_CLASS_TOKENS == bd.BLACKCEO_NEGATIVE_BLOCK_CLASS_TOKENS
        assert pg.BLACK_SUBJECT_TOKENS == bd.BLACK_SUBJECT_TOKENS
        assert pg.NEGATIVE_BLOCK_CLASS_TOKENS == bd.NEGATIVE_BLOCK_CLASS_TOKENS

    def test_registered_in_manifest_rulesets_registry(self):
        manifest = json.loads(
            (REPO / "universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json")
            .read_text(encoding="utf-8"))
        entry = {a["code"]: a for a in manifest["autofails"]}["AF-P24"]
        assert entry["enforced_by"] == "build_deck"
        assert entry["py_symbol"] == "_blackceo_negative_class_problems"
        assert entry["in_ruleset"] is True
        assert hasattr(bd, "_blackceo_negative_class_problems")
        cluster_ruleset = (REPO / "universal-sops/presentation-slide-craft/"
                           "MASTER-QC-AUTOFAIL-RULESET.md").read_text(encoding="utf-8")
        assert "| AF-P24 |" in cluster_ruleset
        registry = (REPO / "universal-sops/presentation-slide-craft/"
                    "SOP-MECHANICAL-ENFORCEMENT-REGISTRY.md").read_text(encoding="utf-8")
        assert "`AF-P24`" in registry
        dept_ruleset = (SCRIPTS.parent / "sops" /
                        "SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md").read_text(encoding="utf-8")
        assert "| AF-P24 |" in dept_ruleset
