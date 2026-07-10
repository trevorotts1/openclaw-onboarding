#!/usr/bin/env python3
"""
prompt_gate.py — the ONE shared image-prompt gate for the Presentations pipeline.

WHY THIS FILE EXISTS
--------------------
Before this module, the 9,000–18,000-char prompt floor + structural-block +
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

The numeric floor/ceiling here are DRIFT-PINNED to build_deck.py's own
PROMPT_CHAR_FLOOR / PROMPT_CHAR_CEILING by sync_check.py (V-check), exactly the
way build_deck.py is already pinned to the retired render_deck.py — so this
extraction can never silently diverge from the canonical renderer's floor.

WHAT IT ENFORCES (verify_prompt — the one entry every path calls)
-----------------------------------------------------------------
  * dead-endpoint fragment never rides inside a prompt payload
  * forbidden demographic-default landmine (AF-R3)
  * empty / whitespace-only prompt                            (AF-P1 floor)
  * length >= PROMPT_CHAR_FLOOR (9,000)                       (AF-P1)
  * length <= PROMPT_CHAR_CEILING (18,000)                    (AF-P2)
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
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# MODEL / ASPECT / RESOLUTION PINS  (must match build_deck.py + kie_generate.py)
# ---------------------------------------------------------------------------
MODEL_T2I = "gpt-image-2-text-to-image"
MODEL_I2I = "gpt-image-2-image-to-image"  # OFFICIAL-LOGO mode: composites the REAL logo via input_urls
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
# PROMPT CHAR-COUNT GATE  (DRIFT-PINNED to build_deck.py by sync_check.py V-check)
# ---------------------------------------------------------------------------
PROMPT_CHAR_FLOOR = 9000       # HARD floor (AF-P1): a rich prompt under this is a thin stub — never run it
PROMPT_CHAR_TARGET_HIGH = 18000  # SOP authoring-target HIGH end (matches the hard ceiling)
PROMPT_CHAR_CEILING = 18000    # UNIVERSAL hard maximum (AF-P2; 2,000 under the 20,000 API ceiling)
PROMPT_MIN_DISTINCT_WORDS = 220  # AF-P-DENSITY: catches paste-repetition padding

# The GPT-Image-2 platform ceiling on input.prompt (both endpoints). ensure_english_pin
# never appends past this — but PROMPT_CHAR_CEILING (18,000) already leaves 2,000 chars
# of margin, so the pin (~230 chars) always fits.
API_PROMPT_HARD_CEILING = 20000

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


def prompt_problems(prompt_text: str, copy_val=None) -> List[str]:
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

    length = len(stripped)
    if length < PROMPT_CHAR_FLOOR:
        problems.append(
            f"AF-P1: prompt is {length} chars, UNDER the HARD floor of {PROMPT_CHAR_FLOOR}. "
            "Too short to carry the mandatory per-slide 15-element spec — NOT run, NOT "
            "rendered, NOT updated. Re-author the rich prompt.")
    if length > PROMPT_CHAR_CEILING:
        problems.append(
            f"AF-P2: prompt is {length} chars, over the hard ceiling of {PROMPT_CHAR_CEILING} "
            "(2,000 under the 20,000 GPT-Image-2 API ceiling). Tighten redundant phrasing "
            "(never delete the negative block or any spelling-lock).")

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
    9,000–18,000-char floor + structural + 8-class negative + spelling-lock + density
    teeth, the 2K width floor, the English/Latin pin, model/reference mode-consistency,
    and the OCR hard-fail) via the KIE_PROMPT_GATE env var.

    Default OFF, and this MATTERS: kie_generate.py and the Skill-46 relay are SHARED image
    helpers reused by non-presentations skills whose prompts are NOT 9,000-char rich deck
    specs and whose renders are NOT English-only 16:9 2K — Skill 06 (GHL landing images),
    Skill 49 (Signature Funnel, 5,000-char band), Skill 47 (movie frames), Skill 59
    (Anthology book covers, portrait), and the video roles. Forcing the presentations band /
    English-only pin / gpt-image-2 mode-pin on those callers would break them. So the heavy
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


def verify_prompt(prompt_text: str, copy_val=None, slide_id=None) -> str:
    """THE shared gate every image-API path calls before submitting to kie.ai. Raises
    PromptGateError (a ValueError) listing every failure when the prompt does not clear the
    9,000–18,000-char floor + structural + 8-class negative + spelling-lock + density +
    demographic-landmine gate. Returns the prompt unchanged on success (callers then run it
    through ensure_english_pin before submit).

    slide_id is an optional label (slide ordinal / name) folded into the error message."""
    problems = prompt_problems(prompt_text, copy_val)
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
    the prompt is returned unchanged; otherwise the pin is appended. Never appends past the
    GPT-Image-2 API hard ceiling (a post-gate prompt is <=18,000, so the ~230-char pin
    always fits with 2,000 chars of margin). This is what makes ENGLISH_PIN REAL — before
    this function the constant was defined and appended nowhere."""
    if has_english_pin(prompt_text):
        return prompt_text
    candidate = prompt_text.rstrip() + "\n\n" + ENGLISH_PIN
    if len(candidate) > API_PROMPT_HARD_CEILING:
        # Cannot safely append without risking API-side truncation of the pin. Leave the
        # prompt as-is; the caller's floor/ceiling gate already bounds length well under
        # this, so this branch is a defensive no-op that should never fire in practice.
        return prompt_text
    return candidate


# ---------------------------------------------------------------------------
# MODE CONSISTENCY  (kills the invented-logo / wrong-endpoint defect at the transport layer)
# ---------------------------------------------------------------------------
def check_mode_consistency(model: str, input_urls, logo_bearing: bool = False,
                           slide_id=None) -> None:
    """Refuse (PromptGateError) an inconsistent model/reference combination:
      * input_urls (reference images) present => model MUST be gpt-image-2-image-to-image
        (a text-to-image call ignores the references and invents its own mark).
      * a slide flagged logo-bearing with EMPTY input_urls => hard fail (the canonical
        invented-logo defect: T2I on a logo slide invents a new mark each render).
    No-op when there are no references and the slide is not logo-bearing."""
    who = f"slide {slide_id}: " if slide_id is not None else ""
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
def _ocr_engine_available():
    """Return (pytesseract_module, PIL_Image_module) if both are importable AND the
    tesseract binary is reachable, else (None, None). Lazy so this module always loads."""
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:  # noqa: BLE001 — engine absent is an EXPECTED, recorded state
        return None, None
    try:
        pytesseract.get_tesseract_version()
    except Exception:  # noqa: BLE001 — python binding present but no tesseract binary
        return None, None
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
# self-check (invoked by prove_pres_prompt_floor.py; `python3 prompt_gate.py --self-test`)
# ---------------------------------------------------------------------------
def _self_test() -> int:
    """Minimal in-module smoke test. The full fixture-driven prover is
    prove_pres_prompt_floor.py. Returns process exit code (0 = pass)."""
    failures = []

    # A thin stub must fail the FULL floor.
    if not prompt_problems("too short"):
        failures.append("thin stub did not fail the gate")

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
