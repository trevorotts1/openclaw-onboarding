#!/usr/bin/env python3
"""
prompt_gate.py — the ONE shared image-prompt gate for the Presentations pipeline.

WHY THIS FILE EXISTS
--------------------
Before this module, the prompt length floor + structural-block +
8-class negative-block + spelling-lock + density + demographic-landmine gates
lived ONLY inside the 8,753-line build_deck.py. Every OTHER path to the paid
kie.ai image API carried ZERO prompt-quality checks:

  * scripts/kie_generate.py (both repo copies) — allow-listed as canonical yet
    submitted any `slide.prompt` unchecked.
  * 46-kie-callback-relay/kie-slide-submitter.js — same, for the batch relay.

A slide generated through those side-doors inherited NONE of the guarantees, so
a thin/garbled/CJK prompt could reach the paid API and ship a bad image. This
module is the single source of truth every image-API path imports so NO path can
submit a prompt that has not cleared the same floor + quality + pin gate.

The LENGTH band is KIE prompt rule 12 (owner order 2026-10-05): 95 to 100 percent of the
model's maxLength, hard floor 80 percent, hard ceiling 100 percent. Neither this module nor
build_deck.py keeps a number: both call the shared enforcer
shared-utils/kie_prompt_enforcer.py (Skill 74 prompt-budget --check). sync_check.py (V-check)
proves both modules import that enforcer and define no band constant of their own.

WHAT IT ENFORCES (verify_prompt — the one entry every path calls)
-----------------------------------------------------------------
  * dead-endpoint fragment never rides inside a prompt payload
  * forbidden demographic-default landmine (AF-R3)
  * empty / whitespace-only prompt                            (AF-P1 floor)
  * length >= the rule 12 floor, 80 percent of the model max  (AF-P1, names the chars to ADD)
  * length <= the model max, English pin included             (AF-P2, names the chars to CUT)
  * required structural blocks ([ARCHETYPE ...], negative block, "Do not ")
  * 8-class negative block                                    (AF-P13)
  * per-string spelling-lock                                  (AF-P14)
  * density: hex palette + type size + composition token + distinct-word floor (AF-P-DENSITY)
  * verbatim copy baked into the prompt body (when copy is supplied)  (AF-P-VERBATIM)

PLUS the pieces that make the pipeline's other image invariants REAL on every path:
  * ensure_english_pin()  — appends the mandatory English/Latin anti-garble pin
    (formerly a dead constant that was defined and never appended anywhere).
  * check_mode_consistency() — input_urls present => model MUST be image-to-image;
    a logo-bearing slide with empty input_urls hard-fails (invented-logo defect).
  * verify_aspect_ratio()  — reads the downloaded PNG's real dimensions (from the
    PNG IHDR chunk, stdlib only) and refuses a non-16:9 / sub-2K response instead
    of letting assemble_pptx stretch it silently.
  * ocr_readback()         — deterministic post-render text readback (optional
    OCR engine; provenance-recorded when the engine is absent) that compares the
    baked text to the slide's approved copy so garbled text becomes a CODE catch,
    not an LLM-honesty check.

This module has NO third-party imports at module load (PIL / pytesseract are
imported lazily and are optional) so it always loads on any client box.
"""

import difflib
import os
import re
import struct
import sys
from pathlib import Path
from typing import List, Optional


def _load_kie_prompt_enforcer():
    """Find shared-utils/kie_prompt_enforcer.py (repo checkout or installed skills tree) and import it.
    Fail closed: without the shared enforcer there is no prompt length gate."""
    here = Path(__file__).resolve()
    envd = os.environ.get("OPENCLAW_SKILLS_DIR")
    dirs = [p / "shared-utils" for p in here.parents]
    dirs += ([Path(envd) / "shared-utils"] if envd else []) + [
        Path.home() / ".openclaw" / "skills" / "shared-utils", Path.home() / "openclaw-onboarding" / "shared-utils",
        Path("/data/.openclaw/skills/shared-utils")]
    for d in dirs:
        if (d / "kie_prompt_enforcer.py").is_file():
            if str(d) not in sys.path:
                sys.path.insert(0, str(d))
            import kie_prompt_enforcer
            return kie_prompt_enforcer
    raise ImportError("shared-utils/kie_prompt_enforcer.py not found: the KIE prompt length gate (rule 12) is "
                      "unavailable. Install or update the onboarding skills (update-skills.sh).")


KPE = _load_kie_prompt_enforcer()

# FIX 13 — model pins resolve from the central catalog (presentation_job/
# model_catalog.py), NOT from literals here. Bootstrap is the same pattern
# kie_generate.py uses to import THIS module: put the scripts dir on sys.path
# (it already is whenever build_deck imports prompt_gate) so the sibling
# package resolves from any caller cwd. Fail-closed: a broken catalog aborts
# the gate rather than enforcing a stale model id.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from presentation_job import model_catalog as _model_catalog  # noqa: E402


def _image_models() -> "tuple":
    """(t2i, i2i) live ids — re-read per call so a catalog bump is honored."""
    t = _model_catalog.image_mode_table()
    return t["MODEL_T2I"], t["MODEL_I2I"]


# ---------------------------------------------------------------------------
# MODEL / ASPECT / RESOLUTION PINS  (catalog aliases; must match build_deck.py
# + kie_generate.py — all three resolve from the SAME model_catalog.json now)
# ---------------------------------------------------------------------------
MODEL_T2I, MODEL_I2I = _image_models()
ASPECT_RATIO = "16:9"
RESOLUTION = "2K"

# The dead endpoint — refuse to ever let it ride inside a prompt payload.
DEAD_ENDPOINT_FRAGMENT = "/api/v1/image/gpt-image"

# ---------------------------------------------------------------------------
# THE MANDATORY TRAILING PIN appended to EVERY prompt (was dead in build_deck.py).
# ---------------------------------------------------------------------------
# Kept byte-identical to build_deck.py::ENGLISH_PIN. This is the #1 defense against
# garbled / misspelled / CJK glyph baked text; before this module it was defined and
# appended NOWHERE. ensure_english_pin() now makes it real on every image-API path.
ENGLISH_PIN = (
    "All text rendered in the image MUST be in English, Latin alphabet ONLY. "
    "NO Chinese/CJK or non-Latin characters anywhere. Render the copy spelled "
    "correctly, letter-for-letter. No garbled, misspelled, or invented text."
)

# ---------------------------------------------------------------------------
# PROMPT CHAR-COUNT GATE = KIE prompt rule 12 through the shared enforcer (see length_problems).
# No floor or ceiling number lives here: the limit is read from Skill 74 prompt-budget.
# ---------------------------------------------------------------------------
PROMPT_MIN_DISTINCT_WORDS = 220  # AF-P-DENSITY: catches paste-repetition padding

# ---------------------------------------------------------------------------
# REQUIRED STRUCTURAL BLOCKS (AF-P1)  — folded in from the retired render_deck.py
# ---------------------------------------------------------------------------
REQUIRED_STRUCTURAL_BLOCKS = ["[ARCHETYPE", "DO-NOT BLOCK", "Do not "]

# The negative-block header is the only block with historical label drift: the
# canonical header is "DO-NOT BLOCK" but earlier authoring used "NEGATIVE BLOCK".
# Both must satisfy the structural requirement.
STRUCTURAL_BLOCK_ALIASES = {
    "DO-NOT BLOCK": ["NEGATIVE BLOCK"],
}

# AF-P13 — the EIGHT mandatory negative-block defect CLASSES (slide-image-creator.md
# SOP 9.8). Each class must have >=1 of its tolerant tokens present.
NEGATIVE_BLOCK_CLASS_TOKENS = {
    "garbled/misspelled text": [
        "misspell", "garble", "letter-for-letter", "letter for letter",
        "render every quoted", "exactly as written", "render every letter"],
    "logo mutation": [
        "logo", "monogram", "tagline lockup", "reference mark", "redraw",
        "redesign", "recolor", "restyle", "reinterpret"],
    "placeholder/bracket tokens": [
        "bracketed token", "square bracket", "owner to confirm", "placeholder",
        "tbd", "build note", "to supply", "pending", "insert"],
    "image narration/presenter/meta": [
        "narrat", "presenter line", "spoken-script", "spoken script",
        "stage direction", "telegraphing", "webinar", "self-talk",
        "describe the picture", "description of the picture", "build note"],
    "anatomical artifacts": [
        "finger", "fused hand", "malformed", "anatom", "distorted facial",
        "mismatched eye", "asymmetric eye", "distorted teeth",
        "over-smoothed skin", "body proportion", "extra limb"],
    "background competing with text": [
        "busy", "cluttered", "high-detail background", "compete", "behind any text",
        "text zone", "scrim", "legib", "negative space"],
    "demographic/skin-tone fidelity": [
        "demographic", "skin tone", "skin-tone", "representation_mix", "lighten",
        "ashen", "desaturate", "mono-cast", "mono cast", "deep skin"],
    "carried-forward universal baseline": [
        "watermark", "emoji", "clipart", "default font", "calibri", "arial",
        "times new roman", "system default", "ui artifact", "user-interface",
        "em dash", "pure-black", "pure black"],
}

# AF-P14 — per-string SPELLING-LOCK. At least one marker token must be present.
SPELLING_LOCK_TOKENS = [
    "spelling-lock", "spelling lock", "letter-for-letter", "letter for letter",
    "render this exact string", "reads exactly", "render every quoted text string exactly",
    "spelled exactly", "exact spelling", "render every letter",
]

# AF-P-DENSITY — concrete specificity signals: brand HEX, a type SIZE, a composition token.
PROMPT_COMPOSITION_TOKENS = [
    "thirds", "rule of thirds", "grid", "left third", "right third", "upper third",
    "lower third", "left-third", "right-third", "upper-third", "lower-third", "zone",
    "safe margin", "safe-margin", "quadrant", "negative space", "focal point", "composition",
]
_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
_TYPE_SIZE_RE = re.compile(r"\b\d{2,4}\s?(?:pt|px|pixels)\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'\-]+")

# FACIAL-INTELLIGENCE / REPRESENTATION landmines (AF-R3): representation must come from
# the client's captured audience, never a baked-in default split.
FORBIDDEN_DEMOGRAPHIC_DEFAULTS = [
    "60/30/10",
    "60-30-10",
    "60/30/10 ratio",
    "default demographic",
    "default ethnicity",
    "default race",
    "default skin tone",
    "default skin-tone",
    "standard demographic mix",
    "standard representation mix",
    "assume the audience is",
    "assumed demographic",
    "inferred demographic",
    "system default demographic",
]

# ---------------------------------------------------------------------------
# ASPECT / RESOLUTION verification thresholds (verify_aspect_ratio)
# ---------------------------------------------------------------------------
_EXPECTED_RATIO = 16.0 / 9.0        # 1.7778 — the pinned 16:9 aspect
ASPECT_RATIO_TOLERANCE = 0.01       # accept within 1% of 16:9 (spec §7.3-4)
# "2K" 16:9 is 2048x1152. Floor the accepted width conservatively so a downscaled
# 1280x720 / 1024x576 response is caught while a legitimate 2048-wide render passes.
MIN_2K_WIDTH = 1536

# OCR text-readback fuzzy-match threshold: an approved copy string is "present" in the
# OCR output if a normalized-substring hit OR a difflib similarity >= this ratio.
OCR_MATCH_RATIO = 0.82


class PromptGateError(ValueError):
    """Raised when a prompt fails the shared image-prompt gate. Subclasses ValueError
    so existing callers that catch ValueError (build_deck.render_slide) keep working."""


# ---------------------------------------------------------------------------
# text helpers (identical semantics to build_deck.py)
# ---------------------------------------------------------------------------
def _norm_ws(s: str) -> str:
    """Lowercase + collapse whitespace runs to one space + strip."""
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def _structural_block_present(block: str, text_lc: str) -> bool:
    candidates = [block] + STRUCTURAL_BLOCK_ALIASES.get(block, [])
    return any(c.lower() in text_lc for c in candidates)


def _missing_structural_blocks(text_lc: str) -> List[str]:
    return [b for b in REQUIRED_STRUCTURAL_BLOCKS if not _structural_block_present(b, text_lc)]


def _negative_block_class_problems(prompt_lc: str) -> List[str]:
    missing = []
    for cls, tokens in NEGATIVE_BLOCK_CLASS_TOKENS.items():
        if not any(t in prompt_lc for t in tokens):
            missing.append(cls)
    return missing


def _spelling_lock_present(prompt_lc: str) -> bool:
    return any(t in prompt_lc for t in SPELLING_LOCK_TOKENS)


def _prompt_density_problems(prompt_text: str, prompt_lc: str) -> List[str]:
    problems = []
    if not _HEX_COLOR_RE.search(prompt_text):
        problems.append("no brand palette HEX (#RRGGBB) — element (f) palette is mandatory")
    if not _TYPE_SIZE_RE.search(prompt_text):
        problems.append("no explicit type SIZE token (e.g. '72pt', '28pt', '120px') — "
                        "typography size is a mandatory 15-element field")
    if not any(t in prompt_lc for t in PROMPT_COMPOSITION_TOKENS):
        problems.append("no composition/zone token (thirds grid, zone, safe margin, "
                        "quadrant) — 'centered' alone is an auto-fail in doctrine")
    distinct = len(set(_WORD_RE.findall(prompt_lc)))
    if distinct < PROMPT_MIN_DISTINCT_WORDS:
        problems.append(f"only {distinct} distinct words (floor {PROMPT_MIN_DISTINCT_WORDS}) "
                        "— a long file with few distinct words is paste-repetition padding, "
                        "not a rich 15-element spec")
    return problems


def _verbatim_copy_problems(prompt_text: str, copy_val) -> List[str]:
    if isinstance(copy_val, list):
        strings = [str(c) for c in copy_val]
    elif copy_val in (None, ""):
        strings = []
    else:
        strings = [str(copy_val)]
    prompt_norm = _norm_ws(prompt_text)
    missing = []
    for c in strings:
        cn = _norm_ws(c)
        if len(cn) < 3:
            continue
        if cn not in prompt_norm:
            short = c if len(str(c)) <= 60 else str(c)[:57] + "..."
            missing.append(short)
    return missing


def demographic_landmine(text: str) -> Optional[str]:
    """Return the first forbidden demographic-default landmine present in text (AF-R3),
    or None. Matched case-insensitively."""
    haystack = str(text).lower()
    for landmine in FORBIDDEN_DEMOGRAPHIC_DEFAULTS:
        if landmine.lower() in haystack:
            return landmine
    return None


def rich_prompt_quality_problems(prompt_text: str, copy_val=None) -> List[str]:
    """The QUALITY-LAYER teeth on a single rich prompt (AF-P13 / AF-P14 / AF-P-DENSITY /
    AF-P-VERBATIM). Returns a list of fatal problem strings (empty = clears every quality
    gate). Identical to build_deck.py::rich_prompt_quality_problems so every image path
    applies the SAME teeth."""
    prompt_lc = prompt_text.lower()
    problems = []
    missing_classes = _negative_block_class_problems(prompt_lc)
    if missing_classes:
        problems.append(
            "AF-P13: negative block does not name defect class(es): "
            + ", ".join(missing_classes)
            + " — the 8-class paired negative block (SOP 9.8) is mandatory; a "
            "one-line 'no text' AVOID stub does not satisfy it")
    if not _spelling_lock_present(prompt_lc):
        problems.append(
            "AF-P14: no per-string spelling-lock directive (e.g. 'render this exact "
            "string, letter-for-letter') — every verbatim on-slide string must be "
            "spelling-locked")
    for d in _prompt_density_problems(prompt_text, prompt_lc):
        problems.append("AF-P-DENSITY: " + d)
    if copy_val is not None:
        missing_copy = _verbatim_copy_problems(prompt_text, copy_val)
        if missing_copy:
            problems.append(
                "AF-P-VERBATIM: the slide's exact copy is NOT baked into the prompt "
                "body (must appear verbatim so kie.ai bakes the words, never overlaid): "
                + " | ".join(missing_copy))
    return problems


def length_budget(model: Optional[str] = None) -> dict:
    """The rule 12 numbers for sizing a rich prompt before it is written: {max, floor, target_min, ceiling,
    pin}. `ceiling` is the longest AUTHORED text that still fits once the mandatory English pin (`pin` chars,
    appended at submit when absent) is added, so it is what an author or a fan-out split must respect.
    Fails closed (PromptGateError) when the model limit is unknown."""
    b = KPE.budget_for(model or _image_models()[0])
    if b is None:
        raise PromptGateError("the prompt length limit is unavailable (Skill 74 prompt-budget gave no max for "
                              f"{model or _image_models()[0]}); refusing to size a prompt blind")
    pin = len("\n\n" + ENGLISH_PIN)
    return {"max": b["max"], "floor": b["floor"], "target_min": b["target_min"], "ceiling": b["max"] - pin, "pin": pin}


def length_problems(prompt_text: str, model: Optional[str] = None) -> List[str]:
    """The rule 12 LENGTH gate for one rich prompt, through the shared enforcer. [] when inside the band;
    else one message that names the exact characters to ADD (below the 80 percent floor, AF-P1) or to
    CUT (above the model max, AF-P2). The floor is measured on the authored prompt; the ceiling on the
    prompt plus the mandatory English pin (ensure_english_pin appends it when the author omitted it).
    `model` defaults to the catalog text-to-image id; the image-to-image id of the same generation has
    the same maxLength."""
    stripped = prompt_text.strip()
    if not stripped:
        return ["AF-P1: prompt is empty / whitespace-only; it carries none of the mandatory per-slide spec"]
    v = KPE.check(model or _image_models()[0], stripped)
    if not v["ok"]:
        return [("AF-P2: " if v["status"] == "ABOVE_MAX" else "AF-P1: ") + v["message"]
                + ". NOT run, NOT rendered, NOT updated; re-author into the rule 12 band"
                " (never delete the negative block or any spelling-lock to make room)."]
    pin = 0 if has_english_pin(stripped) else len("\n\n" + ENGLISH_PIN)
    if v["max"] and v["chars"] + pin > v["max"]:
        return [f"AF-P2: prompt is {v['chars']} chars; the mandatory English pin appended at submit adds {pin}, so the "
                f"payload is {v['chars'] + pin} against a max of {v['max']}; CUT exactly {v['chars'] + pin - v['max']} chars"]
    return []


# Distinct, positive art-direction clauses for a designed web page (sales, checkout, video sales letter). A page-design
# builder uses them through deepen_to_band() to bring its prompt into the KIE rule 12 band; each is a real instruction
# for the same page, filled with its role and client, never a repeat and never filler.
PAGE_DESIGN_DEPTH_BLOCKS = (
    "Reading flow for the {role} page of {client}: the eye enters at the headline band, travels down through the proof and offer zones in a single clear path, and ends at the primary action area; no element sits outside that path, so the page can be understood in a few seconds without scrolling back.",
    "Headline band: the headline is the largest and heaviest type on the page, set in a clean modern face with tight tracking, placed in the upper third on a calm field with generous padding, and supported by one lighter subhead line that finishes the thought without repeating it.",
    "Hierarchy of type: three clear sizes carry the whole page, a display size for the headline, a medium size for section titles and prices, and a comfortable body size for supporting lines; weights step down in the same order, and no fourth size or decorative face is introduced.",
    "Color roles: the primary brand color anchors headlines and major bands, the secondary color tints supporting panels, the accent color appears only on the primary action and a few emphasis marks, and the base color forms the page ground; each color keeps its single job from top to bottom.",
    "Spacing rhythm: vertical gaps follow one repeating unit, doubled between major zones and halved inside a zone, so the page breathes evenly; margins are equal on both sides and wide enough that nothing feels pressed against the edge on a phone or a large display.",
    "Primary action: the action area is the most saturated, highest-contrast region on the page, with a button shape of generous size, a short action phrase in clear type, and quiet reassurance text beneath it; nothing else competes with it for attention.",
    "Offer panel: the offer is shown as one tidy panel with the product name, the key benefits as short lines with simple markers, the price in the second-largest type, and any guarantee set apart in a softly tinted strip; the panel has a single border weight and consistent inner padding.",
    "Trust elements: a small row of credibility marks, such as a guarantee seal shape, secure checkout wording, and a short customer line, sits close to the action area in a muted tone so it reassures without shouting; shapes are simple geometric forms, never clipart.",
    "Proof zone: testimonials or results appear as clean quote cards with a short line, a name and role in smaller type, and equal card sizes aligned to the page grid; avatars, if any, are neutral circles, and quote marks are drawn as simple type, not decorative art.",
    "Layout grid: every zone aligns to one underlying column grid so left edges, right edges, and baselines repeat from zone to zone; panels share a corner radius and a border weight, which makes the page feel engineered and trustworthy rather than assembled.",
    "Contrast and legibility: every line of copy sits on a calm background with strong tonal separation, light on dark in the headline band and dark on light in body zones; small type is never placed on a busy or tinted region, and no line depends on color alone to be read.",
    "Imagery and motif: if a supporting visual is used it is a single, restrained element, such as a clean product shot or a soft brand motif in the accent color, placed beside the copy rather than behind it, with soft edges and no overlap onto any line of text.",
    "Surface and finish: backgrounds are flat or very softly graded, without grain patterns, vignettes, or drop shadows that blur edges; thin rules separate zones, corners are softly rounded at one radius, and the overall finish is crisp, premium, and print-clean.",
    "Brand fidelity: the exact brand palette values are used without substitution, the supplied logo appears once, unaltered, at its assigned position and a legible size, and no other mark, badge, or slogan is invented; every approved word is rendered exactly as written.",
    "Copy integrity: every quoted string is rendered letter for letter with its original capitalization and punctuation; nothing is added, abbreviated, reworded, or translated, and no filler words appear anywhere on the page.",
    "Responsive behavior: the layout is designed so that the same hierarchy survives a narrow phone crop, with zones that stack naturally, text that stays inside a safe margin, and an action area that remains visible without covering other content.",
    "Consistency across the set: the band structure, zone geometry, footer, and logo placement are identical on every page of the funnel; only the content and the page role change, so the set reads as one designed system.",
    "Footer: the footer carries the client name and the small legal line in the quietest type on the page, separated from the content by a thin rule, and sits at the same height and alignment as on the other pages.",
    "Tone of the page: calm, confident, and respectful; the visual energy supports a visitor who is making a decision, with no clutter, no urgency gimmicks, and no ornament that competes with the message or the action.",
    "Quality read: a reviewer looking only at the rendered page can name the headline, the offer, the price, the proof, and the action, with every character legible and correctly spelled and every color matching the brand palette.",
    "Finishing checks: edges are crisp at 2K, spacing is even, alignment is exact, and no element is cropped, doubled, or floating; the page looks like a finished premium design a client would proudly publish.",
    "Above the fold: the first screen of the {role} page shows the headline, the subhead, and either the primary action or the first visual proof, with at least a quarter of that screen left as calm space, so a visitor knows what the page offers before any scrolling.",
    "Section dividers: zones are separated by a change of ground tone or a thin rule, never by heavy boxes or ornaments; the dividers repeat at the same weight and spacing across the page, which keeps the rhythm steady and the page light.",
    "Price presentation: the price uses lining numerals in a weight one step below the headline, with the currency mark smaller and raised, any comparison value set lighter and struck through with a thin line, and the billing note beneath in the smallest type that still reads clearly.",
    "Form and order details: if fields appear they are drawn as clean rules or softly bordered rectangles of equal height with small labels above, a single column, generous spacing between fields, and an order summary panel that echoes the offer panel's border and padding.",
    "Payment reassurance: a quiet row of generic payment shapes and a short security line sits beneath the action area, drawn in a muted tone and at a small size, with no real card brand marks and no animated badges, so the page stays trustworthy and uncluttered.",
    "Video frame treatment: if a video area is part of the page it is a clean rectangle at the page's main aspect ratio with a soft corner radius, a simple centered play shape in the accent color, and a short caption line below, with no screen glare, no fake interface chrome, and no overlapping text.",
    "Iconography: any small icon is a plain line drawing in one stroke weight and the secondary color, used only to mark benefits or steps, aligned to the first line of its text, and never replaced by a photograph, an emoji, or a decorative illustration.",
    "Whitespace budget: roughly a third of the page area is empty ground, distributed between zones and around the margins, so each zone reads as its own idea and the action area has room to stand out.",
    "Tap targets and focus: every button and link area is large enough for comfortable thumb use, with clear spacing from its neighbors, and the primary action shows a visible, high-contrast outline style so keyboard and touch users both see where to act.",
    "Microcopy: supporting lines under headings and buttons are short, plain, and specific, written in the client's voice, free of hype words and exclamation marks, and each one answers a single question the visitor is likely to have at that point.",
    "Numbers and lists: lists keep consistent markers and hanging indents so wrapped lines align with their text, numerals line up on one baseline, and no list exceeds six items, which keeps the offer scannable and the page balanced.",
    "Edge cases in the design: long names, long prices, and long headlines wrap gracefully inside their panels without touching the edge, and no element depends on a specific string length to look correct, so the page survives real client content.",
)


def deepen_to_band(prompt: str, blocks=PAGE_DESIGN_DEPTH_BLOCKS, ctx: Optional[dict] = None,
                   model: Optional[str] = None) -> str:
    """Rule 12 writer loop for a page-design builder: while the prompt is outside the band, append the next clauses
    from `blocks` (formatted with `ctx`) toward the middle of the target band, using the verdict's exact add count,
    up to 3 tries; raises PromptGateError when 3 tries do not fix it (escalate). Reserves room for the English pin."""
    queue = [b.format(**(ctx or {})) for b in blocks]
    reserve = len("\n\n" + ENGLISH_PIN)

    def rewriter(text, verdict):
        goal = (verdict["target_min"] + verdict["max"] - reserve) // 2
        out = text.rstrip()
        while queue and len(out) + len(queue[0]) + 2 <= goal:
            out += "\n\n" + queue.pop(0)
        return out

    try:
        fitted, _ = KPE.rewrite_to_band(model or _image_models()[0], prompt, rewriter)
    except KPE.PromptBudgetError as exc:
        raise PromptGateError(f"the page prompt could not be brought into the KIE rule 12 length band: {exc}") from exc
    return fitted


def prompt_problems(prompt_text: str, copy_val=None, model: Optional[str] = None) -> List[str]:
    """Return EVERY reason `prompt_text` fails the shared image-prompt gate (empty list =
    clears the whole gate). This is the accumulating (non-raising) form used by provers and
    by the side-doors that want to report all problems for a slide at once."""
    problems: List[str] = []

    if DEAD_ENDPOINT_FRAGMENT in prompt_text:
        problems.append(
            f"dead endpoint fragment {DEAD_ENDPOINT_FRAGMENT!r} present in prompt body")

    landmine = demographic_landmine(prompt_text)
    if landmine:
        problems.append(
            f"AF-R3: forbidden hardcoded demographic default {landmine!r} — representation "
            "must come from the client's captured audience / casting ledger, never a "
            "baked-in default split")

    stripped = prompt_text.strip()
    if not stripped:
        problems.append("AF-P1: prompt is empty / whitespace-only — carries none of the "
                        "mandatory per-slide spec")
        return problems  # nothing else measurable

    problems.extend(length_problems(prompt_text, model))

    missing_blocks = _missing_structural_blocks(prompt_text.lower())
    if missing_blocks:
        problems.append(
            "AF-P1: missing required structural block(s): " + ", ".join(missing_blocks)
            + " — a real rich prompt declares its [ARCHETYPE ...] layout, carries the "
            "final-paragraph negative block ('DO-NOT BLOCK' / legacy 'NEGATIVE BLOCK'), "
            "and states 'Do not ...' imperatives")

    problems.extend(rich_prompt_quality_problems(prompt_text, copy_val))
    return problems


def presentations_gate_enabled() -> bool:
    """True iff the caller opted into the FULL presentations rich-prompt gate (the
    rule 12 length band + structural + 8-class negative + spelling-lock + density
    teeth, the 2K width floor, the English/Latin pin, model/reference mode-consistency,
    and the OCR hard-fail) via the KIE_PROMPT_GATE env var.

    Default OFF, and this MATTERS: kie_generate.py and the Skill-46 relay are SHARED image
    helpers reused by non-presentations skills whose prompts are NOT 9,000-char rich deck
    specs and whose renders are NOT English-only 16:9 2K — Skill 06 (GHL landing images),
    Skill 49 (Signature Funnel, 5,000-char band), Skill 47 (movie frames), Skill 59
    (Anthology book covers, portrait), and the video roles. Forcing the presentations band /
    English-only pin / gpt-image-2.5 mode-pin on those callers would break them. So the heavy
    gate is opt-in: the PRESENTATIONS context sets KIE_PROMPT_GATE=presentations to enable
    it; every other caller gets only the always-on universal-safe checks
    (verify_prompt_minimal: dead-endpoint + empty-prompt refusal)."""
    return os.environ.get("KIE_PROMPT_GATE", "").strip().lower() in (
        "presentations", "full", "1", "on", "true")


def verify_prompt_minimal(prompt_text: str, slide_id=None) -> str:
    """The UNIVERSAL-SAFE checks that apply to EVERY image-API caller regardless of skill —
    the floor below which no submission is ever valid for anyone: refuse the dead endpoint
    fragment riding inside the prompt, and refuse an empty / whitespace-only prompt. Does
    NOT impose the presentations 9,000-char rich floor, the English pin, or the model pin —
    those are opt-in via presentations_gate_enabled(). Returns the prompt unchanged on
    success. This is what keeps the shared side-doors from ever submitting a literally-empty
    prompt to the paid API while remaining safe for GHL / funnel / movie / Anthology / video."""
    who = f"slide {slide_id}: " if slide_id is not None else ""
    if DEAD_ENDPOINT_FRAGMENT in prompt_text:
        raise PromptGateError(
            who + f"dead endpoint fragment {DEAD_ENDPOINT_FRAGMENT!r} present in prompt body — refusing")
    if not prompt_text.strip():
        raise PromptGateError(
            who + "empty / whitespace-only prompt — nothing to render; refusing to submit to the paid API")
    return prompt_text


def verify_prompt(prompt_text: str, copy_val=None, slide_id=None, model: Optional[str] = None) -> str:
    """THE shared gate every image-API path calls before submitting to kie.ai. Raises
    PromptGateError (a ValueError) listing every failure when the prompt does not clear the
    rule 12 length band + structural + 8-class negative + spelling-lock + density +
    demographic-landmine gate. Returns the prompt unchanged on success (callers then run it
    through ensure_english_pin before submit).

    slide_id is an optional label (slide ordinal / name) folded into the error message."""
    problems = prompt_problems(prompt_text, copy_val, model)
    if problems:
        who = f"slide {slide_id}: " if slide_id is not None else ""
        raise PromptGateError(
            who + "rich prompt FAILS the shared image-prompt gate — it is NOT run, NOT "
            "rendered, NOT updated. Re-author. Problems: " + " || ".join(problems))
    return prompt_text


# ---------------------------------------------------------------------------
# ENGLISH/LATIN anti-garble PIN  (make the dead constant real)
# ---------------------------------------------------------------------------
def has_english_pin(prompt_text: str) -> bool:
    """True iff the mandatory English/Latin pin is already present in the prompt.
    Whitespace-insensitive so a re-wrapped copy of the pin still counts."""
    return _norm_ws(ENGLISH_PIN) in _norm_ws(prompt_text)


def ensure_english_pin(prompt_text: str) -> str:
    """Return `prompt_text` guaranteed to carry the mandatory English/Latin anti-garble
    pin. Belt-and-braces: if the pin is already present (authoring-side responsibility),
    the prompt is returned unchanged; otherwise the pin is appended. The rule 12 length gate
    (length_problems) already counts the pin toward the model max, so a prompt that cleared
    the gate always fits with the pin appended. This is what makes ENGLISH_PIN REAL: before
    this function the constant was defined and appended nowhere."""
    if has_english_pin(prompt_text):
        return prompt_text
    return prompt_text.rstrip() + "\n\n" + ENGLISH_PIN


# ---------------------------------------------------------------------------
# MODE CONSISTENCY  (kills the invented-logo / wrong-endpoint defect at the transport layer)
# ---------------------------------------------------------------------------
def check_mode_consistency(model: str, input_urls, logo_bearing: bool = False,
                           slide_id=None) -> None:
    """Refuse (PromptGateError) an inconsistent model/reference combination:
      * input_urls (reference images) present => model MUST be gpt-image-2-5-sunburst-image-to-image
        (a text-to-image call ignores the references and invents its own mark).
      * a slide flagged logo-bearing with EMPTY input_urls => hard fail (the canonical
        invented-logo defect: T2I on a logo slide invents a new mark each render).
    No-op when there are no references and the slide is not logo-bearing.
    FIX 13: the expected i2i id is re-read from the catalog per call — a
    catalog bump changes what this gate accepts with no code edit."""
    who = f"slide {slide_id}: " if slide_id is not None else ""
    MODEL_I2I = _image_models()[1]  # catalog-live; shadows the module pin for this call
    has_inputs = bool(input_urls)
    if has_inputs and model != MODEL_I2I:
        raise PromptGateError(
            who + f"input_urls/reference images are present but model is {model!r}. A "
            f"reference-bearing render MUST use {MODEL_I2I!r} (image-to-image) or the "
            "references are ignored and the model invents its own logo/portrait. Refusing.")
    if logo_bearing and not has_inputs:
        raise PromptGateError(
            who + "slide is flagged logo-bearing but input_urls is EMPTY. A logo slide "
            f"MUST pass the real logo URL via input_urls and render with {MODEL_I2I!r} "
            "(image-to-image); a text-to-image call invents a NEW mark each render "
            "(the canonical logo-mutation defect). Refusing.")


# ---------------------------------------------------------------------------
# POST-DOWNLOAD ASPECT / RESOLUTION verification  (stdlib only — no PIL required)
# ---------------------------------------------------------------------------
def read_png_dimensions(png_path) -> tuple:
    """Return (width, height) of a PNG by reading its IHDR chunk directly (stdlib only,
    no PIL). Raises PromptGateError if the file is not a readable PNG."""
    path = Path(png_path)
    try:
        with open(path, "rb") as f:
            header = f.read(24)
    except OSError as exc:
        raise PromptGateError(f"{path}: cannot read PNG header ({exc}).") from exc
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise PromptGateError(
            f"{path}: not a PNG (bad signature) — cannot verify aspect ratio.")
    if header[12:16] != b"IHDR":
        raise PromptGateError(
            f"{path}: PNG has no IHDR chunk where expected — cannot verify dimensions.")
    width, height = struct.unpack(">II", header[16:24])
    if width <= 0 or height <= 0:
        raise PromptGateError(f"{path}: PNG reports a degenerate size {width}x{height}.")
    return width, height


def verify_aspect_ratio(png_path, expected_ratio: float = _EXPECTED_RATIO,
                        tolerance: float = ASPECT_RATIO_TOLERANCE,
                        min_width: int = MIN_2K_WIDTH, slide_id=None) -> dict:
    """Verify a freshly-downloaded slide PNG is actually the pinned 16:9 / 2K shape.
    Raises PromptGateError (retryable by the caller's per-slide attempt loop) when the
    width/height ratio is not within `tolerance` of 16:9, or the width is below the 2K
    floor. Returns {'width','height','ratio','expected_ratio','tolerance'} on success.

    WHY: verify_png() only checks PNG magic bytes; assemble_pptx() then stretches every
    image to 10"x5.625", so a non-16:9 response ships DISTORTED. This makes the shape a
    deterministic gate instead of a silent stretch."""
    width, height = read_png_dimensions(png_path)
    ratio = width / height
    who = f"slide {slide_id}: " if slide_id is not None else ""
    if abs(ratio - expected_ratio) > (expected_ratio * tolerance):
        raise PromptGateError(
            who + f"rendered PNG is {width}x{height} (ratio {ratio:.4f}); the pinned aspect "
            f"is 16:9 ({expected_ratio:.4f}) within {tolerance:.0%}. A non-16:9 image is "
            "stretched/distorted by assemble_pptx — re-render this slide (never stretch).")
    if width < min_width:
        raise PromptGateError(
            who + f"rendered PNG width is {width}px, below the 2K floor of {min_width}px. "
            f"The pinned resolution is {RESOLUTION} (2048x1152 for 16:9); a sub-2K image "
            "ships soft/pixelated — re-render this slide.")
    return {"width": width, "height": height, "ratio": ratio,
            "expected_ratio": expected_ratio, "tolerance": tolerance}


# ---------------------------------------------------------------------------
# OCR TEXT-READBACK QC  (deterministic garbled-text catch; optional engine)
# ---------------------------------------------------------------------------
def ocr_engine_diagnostic() -> dict:
    """Structured OCR-engine-availability diagnostic — the SINGLE source of truth
    _ocr_engine_available() (below, used by ocr_readback()'s POSTFLIGHT, provenance-
    recorded-optional path) and build_deck.ocr_engine_preflight() (the MASTER-SPEC
    7.4 Phase-0 fail-closed PREFLIGHT gate, minute-zero, before any paid generation)
    both build on, so the two never independently drift on what 'available' means.

    Distinguishes WHY the engine is unavailable (pytesseract not importable vs.
    Pillow not importable vs. the tesseract BINARY not reachable) so a fail-closed
    caller can print an actionable message instead of a bare 'missing'.

    Tests THIS interpreter only — it does no venv/PATH detection of its own. A
    caller that needs to know whether the RENDER environment has an engine must
    invoke this from the exact interpreter/process that performs the render (see
    build_deck.ocr_engine_preflight's docstring for the launchd/cron/venv/sudo
    user-site-packages invisibility trap this exists to catch).

    Returns one of:
      {"available": True,  "engine": "pytesseract", "version": "<tesseract version>"}
      {"available": False, "engine": None, "reason": "pytesseract-import-failed", "detail": "<exc>"}
      {"available": False, "engine": None, "reason": "pillow-import-failed",      "detail": "<exc>"}
      {"available": False, "engine": None, "reason": "tesseract-binary-not-found","detail": "<exc>"}
    """
    try:
        import pytesseract  # type: ignore
    except Exception as exc:  # noqa: BLE001 — engine absence is an EXPECTED, probed state
        return {"available": False, "engine": None,
                "reason": "pytesseract-import-failed", "detail": str(exc)}
    try:
        from PIL import Image  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "engine": None,
                "reason": "pillow-import-failed", "detail": str(exc)}
    try:
        version = pytesseract.get_tesseract_version()
    except Exception as exc:  # noqa: BLE001 — python binding present but no tesseract binary
        return {"available": False, "engine": None,
                "reason": "tesseract-binary-not-found", "detail": str(exc)}
    del Image  # imported only to prove PIL is importable; _ocr_engine_available re-imports it
    return {"available": True, "engine": "pytesseract", "version": str(version)}


def _ocr_engine_available():
    """Return (pytesseract_module, PIL_Image_module) if both are importable AND the
    tesseract binary is reachable, else (None, None). Lazy so this module always
    loads. Thin wrapper over ocr_engine_diagnostic() (the shared source of truth) —
    kept for the existing (module, module) call shape ocr_readback() below uses."""
    if not ocr_engine_diagnostic().get("available"):
        return None, None
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
    return pytesseract, Image


def _text_present(needle: str, haystack_norm: str) -> bool:
    """True iff `needle` (an approved copy string) is readable in the OCR output: a
    normalized-substring hit, else a fuzzy difflib similarity against the best-matching
    window of the OCR text >= OCR_MATCH_RATIO (tolerant of OCR noise / kerning)."""
    n = _norm_ws(needle)
    if len(n) < 3:
        return True  # a 1-2 char fragment proves nothing either way
    if n in haystack_norm:
        return True
    # Fuzzy: slide a window the size of the needle across the haystack and take the best ratio.
    best = 0.0
    step = max(1, len(n) // 4)
    for i in range(0, max(1, len(haystack_norm) - len(n) + 1), step):
        window = haystack_norm[i:i + len(n)]
        r = difflib.SequenceMatcher(None, n, window).ratio()
        if r > best:
            best = r
            if best >= OCR_MATCH_RATIO:
                return True
    return best >= OCR_MATCH_RATIO


def ocr_readback(png_path, expected_texts, slide_id=None) -> dict:
    """Deterministic post-render text readback. Runs OCR over the rendered slide PNG and
    checks that each approved copy string is readable in the output. Returns a provenance
    record:

        {
          "engine": "pytesseract" | None,
          "available": bool,          # False => engine absent on this box (recorded, non-fatal)
          "checked": bool,            # True => OCR actually ran and compared
          "matched": bool | None,     # True=all copy readable, False=one+ missing, None=not checked
          "expected": [...],          # the approved copy strings compared
          "misses": [...],            # approved strings NOT readable in the OCR output
          "ocr_text": "...",          # the raw OCR readout (truncated) for the QC record
        }

    This is intentionally PROVENANCE-RECORDED-OPTIONAL (mirrors AF-IMAGE-QC-VISION): on a
    box WITHOUT an OCR engine the absence is visible in the record rather than silently
    skipped. The CALLER decides policy — build_deck re-renders (capped) only when the
    engine ran and `matched` is False; it never hard-fails purely for a missing engine."""
    if isinstance(expected_texts, str):
        expected = [expected_texts]
    elif expected_texts in (None, ""):
        expected = []
    else:
        expected = [str(t) for t in expected_texts]
    # Drop trivial fragments (labels / single glyphs) from the comparison set.
    expected = [e for e in expected if len(_norm_ws(e)) >= 3]

    record = {"engine": None, "available": False, "checked": False,
              "matched": None, "expected": expected, "misses": [], "ocr_text": ""}

    pytesseract, Image = _ocr_engine_available()
    if pytesseract is None:
        return record  # engine absent — recorded, non-fatal
    record["engine"] = "pytesseract"
    record["available"] = True

    try:
        with Image.open(str(png_path)) as im:
            raw = pytesseract.image_to_string(im)
    except Exception as exc:  # noqa: BLE001 — a failed OCR pass is recorded, not fatal
        record["ocr_error"] = str(exc)
        return record

    record["checked"] = True
    record["ocr_text"] = raw.strip()[:4000]
    haystack = _norm_ws(raw)
    misses = [e for e in expected if not _text_present(e, haystack)]
    record["misses"] = misses
    record["matched"] = (len(misses) == 0)
    return record


# ---------------------------------------------------------------------------
# CANONICAL PROMPT-FILE NAMING + DUPLICATE DETECTION  (FIX-22 / D16)
# ---------------------------------------------------------------------------
# D16 (ERRORS-DETECTED): the prompt generator produced BOTH `slide-1.txt` and
# `slide-01.txt` — a zero-padding naming collision that made 21 prompt files for
# 20 slides. `slide-1.txt` and `slide-01.txt` are treated as DIFFERENT files by
# the build but both target slide 1. Root cause: mixed `%d` and `%02d` formatting.
#
# The canonical per-slide prompt filename is ZERO-PADDED `slide-%02d.txt`
# (build_deck.PROMPT_FILE_PATTERNS also accepts `slide-%02d-prompt.txt`; both
# variants must be zero-padded). These two helpers are the single duplicate-detector:
#   * scan_prompt_dir()   — returns a structured report of the prompt dir
#   * prompt_dir_problems() — returns fatal AF-PROMPT-DUP-FILE / AF-PROMPT-NAME
#     strings for every non-canonical or duplicate-target file ([] = clean).
#
# Every path that consumes `working/prompts/slide-*.txt` must run this before
# trusting the per-slide file set, so a `slide-1.txt` vs `slide-01.txt` collision
# fails the build instead of silently shipping two prompts for slide 1.
CANONICAL_PROMPT_FILE_RE = re.compile(r"^slide-(\d+)\.txt$")
CANONICAL_PROMPT_ALT_RE = re.compile(r"^slide-(\d+)-prompt\.txt$")
# The canonical ordinal field is EXACTLY two digits (`%02d`): slide-01..slide-99.
# A 1-digit (`slide-1.txt`) or 3+ digit (`slide-100.txt`) number is non-canonical
# and collides with its zero-padded twin — that is the D16 defect.
CANONICAL_PROMPT_DIGITS_RE = re.compile(r"^\d{2}$")


def _prompt_file_ordinal(name: str) -> int:
    """Parse the slide ordinal from a prompt filename (canonical or `-prompt`
    variant). Returns -1 when the name does not carry a slide number."""
    for r in (CANONICAL_PROMPT_FILE_RE, CANONICAL_PROMPT_ALT_RE):
        m = r.match(name)
        if m:
            return int(m.group(1))
    return -1


def scan_prompt_dir(prompts_dir) -> dict:
    """Scan a `working/prompts/` directory and return a structured report of the
    per-slide prompt files. Never raises on a missing/unreadable dir — it returns
    a fail-closed report the caller decides on.

    Return shape:
      {
        "dir": str,
        "exists": bool,
        "files": [str],            # every slide-*.txt name, sorted
        "count": int,              # number of slide-*.txt files
        "canonical": [str],        # names that are exactly slide-%02d.txt / slide-%02d-prompt.txt
        "non_canonical": [str],    # slide-*.txt names whose ordinal is NOT zero-padded %02d
        "targets": {ordinal: [names...]},  # every file grouped by its slide target
        "duplicates": [str],       # names whose slide target is ALSO carried by another file
      }
    """
    d = Path(prompts_dir)
    base = {"dir": str(d), "exists": d.is_dir(), "files": [], "count": 0,
            "canonical": [], "non_canonical": [], "targets": {}, "duplicates": []}
    if not d.is_dir():
        return base
    names = sorted(p.name for p in d.glob("slide-*.txt"))
    base["files"] = names
    base["count"] = len(names)
    targets: dict = {}
    for name in names:
        ordinal = _prompt_file_ordinal(name)
        if ordinal < 0:
            continue  # a slide-*.txt with no numeric suffix — leave out of targets
        targets.setdefault(ordinal, []).append(name)
    base["targets"] = {k: sorted(v) for k, v in targets.items()}
    for name in names:
        digit_part = name[len("slide-"):].split("-")[0].split(".")[0]
        if CANONICAL_PROMPT_DIGITS_RE.match(digit_part):
            base["canonical"].append(name)
        else:
            base["non_canonical"].append(name)
    for ordn, group in targets.items():
        if len(group) > 1:
            base["duplicates"].extend(group)
    base["duplicates"] = sorted(set(base["duplicates"]))
    return base


def prompt_dir_problems(prompts_dir) -> list:
    """Return EVERY fatal problem in a `working/prompts/` directory, or [] when it
    is clean. Two defect classes (D16 / FIX-22):
      * AF-PROMPT-DUP-FILE  — two+ files target the SAME slide (e.g. slide-1.txt
        and slide-01.txt both target slide 1); the build must fail closed because
        one slide would get two prompts (21 files for 20 slides).
      * AF-PROMPT-NAME      — a slide-*.txt name is NOT canonical zero-padded
        `slide-%02d.txt` / `slide-%02d-prompt.txt` (e.g. slide-1.txt); it is the
        half of the D16 collision that must never be authored.
    Callers (build_deck preflight, presentation_job.gates, prove_pres_prompt_floor
    --dir) all run this and fail closed when it is non-empty."""
    problems = []
    rep = scan_prompt_dir(prompts_dir)
    if not rep["exists"]:
        return problems  # the caller owns the "no prompts dir" case
    if rep["duplicates"]:
        dup_names = ", ".join(rep["duplicates"])
        # Name every colliding target with its exact file set so the fix is obvious.
        for ordn, group in sorted(rep["targets"].items()):
            if len(group) > 1:
                problems.append(
                    f"AF-PROMPT-DUP-FILE: slide {ordn} has {len(group)} prompt files "
                    f"({', '.join(group)}) — a zero-padding naming collision (D16). "
                    "Exactly ONE canonical zero-padded slide-%02d.txt per slide is "
                    "allowed; delete the non-canonical twin and regenerate prompts.")
        if not problems:
            problems.append(f"AF-PROMPT-DUP-FILE: duplicate slide targets: {dup_names}")
    for name in rep["non_canonical"]:
        problems.append(
            f"AF-PROMPT-NAME: {name!r} is NOT the canonical zero-padded "
            f"'slide-%02d.txt' (or 'slide-%02d-prompt.txt') prompt filename. A "
            "non-zero-padded name (e.g. slide-1.txt) collides with its zero-padded "
            "twin (slide-01.txt) — rename it to the %02d form.")
    return problems


# ---------------------------------------------------------------------------
# self-check (invoked by prove_pres_prompt_floor.py; `python3 prompt_gate.py --self-test`)
# ---------------------------------------------------------------------------
def _self_test() -> int:
    """Minimal in-module smoke test. The full fixture-driven prover is
    prove_pres_prompt_floor.py. Returns process exit code (0 = pass)."""
    failures = []

    # A thin stub must fail the FULL floor.
    if not prompt_problems("too short"):
        failures.append("thin stub did not fail the gate")

    # Rule 12 length through the shared enforcer (GPT Image 2.5 max 20,000): 79 percent rejected naming the
    # chars to add, 95 percent clears the length gate, 101 percent rejected naming the chars to cut.
    for n, want in ((15800, "ADD at least 200"), (19000, None), (20200, "CUT exactly")):
        lp = length_problems("x" * n)
        if want is None and lp:
            failures.append(f"{n}-char prompt must clear the rule 12 length gate, got {lp}")
        elif want is not None and not any(want in m for m in lp):
            failures.append(f"{n}-char prompt must be rejected with {want!r}, got {lp}")
    if not any("CUT exactly" in m for m in length_problems("x" * 19900)):  # 19,900 + the pin > 20,000
        failures.append("a prompt whose English pin overflows the max must name the chars to cut")

    # The universal-safe minimal gate must PASS a thin-but-nonempty prompt (shared callers
    # like GHL / funnel / movie / Anthology are not held to the 9,000-char deck floor) while
    # still rejecting an empty prompt and the dead endpoint.
    try:
        verify_prompt_minimal("a short non-empty prompt from a shared skill")
    except PromptGateError:
        failures.append("minimal gate wrongly rejected a short non-empty prompt")
    for bad, why in [("   ", "empty"), ("x " + DEAD_ENDPOINT_FRAGMENT, "dead-endpoint")]:
        try:
            verify_prompt_minimal(bad)
            failures.append(f"minimal gate did not reject {why} prompt")
        except PromptGateError:
            pass

    # The pin round-trips.
    pinned = ensure_english_pin("a slide prompt with no pin")
    if not has_english_pin(pinned):
        failures.append("ensure_english_pin did not add the pin")
    if ensure_english_pin(pinned) != pinned:
        failures.append("ensure_english_pin is not idempotent")

    # Mode consistency: references without I2I model must raise.
    try:
        check_mode_consistency(MODEL_T2I, ["https://x/logo.png"])
        failures.append("mode-consistency did not reject T2I with input_urls")
    except PromptGateError:
        pass
    # Logo-bearing with no inputs must raise.
    try:
        check_mode_consistency(MODEL_T2I, [], logo_bearing=True)
        failures.append("mode-consistency did not reject logo-bearing with empty input_urls")
    except PromptGateError:
        pass
    # Consistent I2I with inputs is fine.
    check_mode_consistency(MODEL_I2I, ["https://x/logo.png"])

    # FIX-22 / D16: canonical zero-padded prompt-file naming + duplicate detection.
    import tempfile
    td = Path(tempfile.mkdtemp(prefix="pg_dupfix_"))
    try:
        # Clean dir: 3 canonical zero-padded files -> NO problems, count == 3.
        for i in (1, 2, 3):
            (td / f"slide-{i:02d}.txt").write_text("x" * 100)
        clean_problems = prompt_dir_problems(td)
        if clean_problems:
            failures.append(f"canonical prompt dir must be clean, got {clean_problems}")
        clean_rep = scan_prompt_dir(td)
        if clean_rep["count"] != 3 or clean_rep["duplicates"] or clean_rep["non_canonical"]:
            failures.append(f"canonical prompt dir scan wrong: {clean_rep}")

        # The D16 collision: slide-1.txt + slide-01.txt both target slide 1.
        (td / "slide-1.txt").write_text("y" * 100)
        dup_problems = prompt_dir_problems(td)
        if not any("AF-PROMPT-DUP-FILE" in p and "slide 1" in p for p in dup_problems):
            failures.append(f"D16 dup detector did not fire on slide-1.txt vs slide-01.txt: "
                            f"{dup_problems}")
        dup_rep = scan_prompt_dir(td)
        if "slide-1.txt" not in dup_rep["non_canonical"]:
            failures.append("slide-1.txt must be flagged non-canonical (not %02d)")
        if len(dup_rep["targets"].get(1, [])) != 2:
            failures.append(f"both slide-1.txt and slide-01.txt must target slide 1: "
                            f"{dup_rep['targets']}")

        # A 3-digit ordinal is also non-canonical (slide-100.txt).
        (td / "slide-100.txt").write_text("z" * 100)
        name_problems = prompt_dir_problems(td)
        if not any("AF-PROMPT-NAME" in p and "slide-100" in p for p in name_problems):
            failures.append(f"AF-PROMPT-NAME did not fire on slide-100.txt: {name_problems}")
    finally:
        import shutil
        shutil.rmtree(td, ignore_errors=True)

    if failures:
        for f in failures:
            print(f"  SELF-TEST FAIL: {f}")
        return 1
    print("prompt_gate self-test: PASS")
    return 0


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        raise SystemExit(_self_test())
    print(__doc__)
