#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sf_prompt_floor.py — fail-closed two-floor gate for Signature Funnel image
prompts (Kie.ai gpt-image-2). EXACT clone of the presentations two-floor prompt gate
(build_deck.py PROMPT_CHAR_FLOOR / PROMPT_CHAR_CEILING / structural-block / density),
with the constants changed to the funnel band 5,000 / 19,000.

THE TWO FLOORS (both must clear or the prompt NEVER reaches a paid Kie call):
  FLOOR 1 — LENGTH: 5,000 <= stripped chars <= 19,000.        -> AF-FUN-PROMPT-FLOOR / -CEILING
  FLOOR 2 — STRUCTURE/EXCELLENCE: a real rich prompt carries the load-bearing blocks:
    * the SIGNATURE GRADE BLOCK fingerprint (the canonical grade paragraph, 2.4). -> AF-FUN-PROMPT-GRADE
    * a final-paragraph NEGATIVE BLOCK with at least one 'Do not ' imperative.     -> AF-FUN-PROMPT-NEGATIVE
    * >= 220 distinct words (padding one paragraph to length has few distinct words).-> AF-FUN-PROMPT-DENSITY
    * NO em dashes anywhere (presentations-inherited model-safety rule).           -> AF-FUN-PROMPT-EMDASH
    * TYPOGRAPHY discipline: a text-bearing prompt (e.g. Sec 11) carries a
      spelling-lock directive AND the exact baked words; a non-text prompt states
      "no text / no letters / no words".                                          -> AF-FUN-PROMPT-TYPO

CLONE PROVENANCE (cited): build_deck.py:325-327 (PROMPT_CHAR_FLOOR=9000/CEILING=18000),
build_deck.py:1082-1102 (stripped-length floor+ceiling), build_deck.py REQUIRED_STRUCTURAL_BLOCKS
+ _missing_structural_blocks, PROMPT_MIN_DISTINCT_WORDS density gate. Measured on the SAME
stripped text the char gate measures; any self-reported length in the ledger is IGNORED.

stdlib only. Exit 0 = pass, exit 2 = violation, exit 3 = usage/fail-closed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

# --- the funnel band (clone of build_deck.py:325-327, constants changed) -----
PROMPT_CHAR_FLOOR = 5000       # HARD low end (AF-FUN-PROMPT-FLOOR)
PROMPT_CHAR_CEILING = 19000    # HARD high end (AF-FUN-PROMPT-CEILING); ~1,000 under the API ceiling
PROMPT_MIN_DISTINCT_WORDS = 220  # AF-FUN-PROMPT-DENSITY: catches paragraph-repeat padding

# The canonical SIGNATURE GRADE BLOCK (SACRED IP) — embedded verbatim in block 4 of
# every image prompt (funnel_structure / IMPROVED-FRAMEWORK-v2 §2.4 and MASTERDOC §4).
# This constant is the single source of truth for the verbatim-containment gate below.
_GRADE_BLOCK = (
    "Render this image in the Trevor Otts Signature aesthetic, and treat this grading "
    "direction as the single most important instruction in this prompt. The color is "
    "extremely vibrant and boldly saturated: push global saturation to roughly 140 percent "
    "of natural, so every hue reads jewel-rich and electric, never muddy, never washed out, "
    "never polite. The image is heavily and deliberately color-graded like a high-fashion "
    "editorial cover with deep crushed inky shadows set against luminous glowing highlights. "
    "This is signature color: vivid, graded, unforgettable. Every human subject is lit and "
    "graded with melanin-true intelligence, deep skin tones rendered rich and dimensional."
)

# SIGNATURE GRADE BLOCK fingerprints — a FAST PRE-CHECK only (a canonical phrase must be
# somewhere in the prompt). Passing a fingerprint no longer CLEARS the gate: the verbatim
# containment check below is authoritative (funnel_structure / IMPROVED-FRAMEWORK-v2 §2.4).
GRADE_FINGERPRINTS = (
    "140 percent",
    "signature color",
    "melanin-true",
    "signature aesthetic",
    "signature grade",
)

# FIX-IMG-06: the "verbatim" grade-block requirement is enforced as normalized
# containment vs the canonical _GRADE_BLOCK — NOT any-of-five short substrings (the
# words "signature grade" alone previously cleared it). A prompt passes only when it
# carries the real block: >= 85% of its sentences present (normalized) OR a contiguous
# >= 600-normalized-char verbatim run of the block. Fingerprints remain a fast pre-check.
GRADE_MIN_SENTENCE_RATIO = 0.85
GRADE_CONTIGUOUS_NORM_CHARS = 600
_NORM_RE = re.compile(r"[^a-z0-9]+")

# Negative-block imperative and text-presence markers.
NEGATIVE_IMPERATIVE = "do not "
NO_TEXT_MARKERS = (
    "no text", "no letters", "no words", "without any text", "no typography",
    "zero text", "no lettering",
)
SPELLING_LOCK_TOKENS = (
    "spelling-lock", "spelling lock", "letter-for-letter", "letter for letter",
    "spelled exactly", "exact spelling", "render this exact", "reads exactly",
)

# em dash + unicode variants (model-safety rule; the source forbids em dashes in prompts)
EM_DASH_CHARS = ("—", "–", "―")  # em dash, en dash, horizontal bar

_WORD_RE = re.compile(r"[a-z0-9]+")


def _stripped(text: Any) -> str:
    return str(text).strip()


def _distinct_words(text: str) -> int:
    return len({m.group(0) for m in _WORD_RE.finditer(text.lower())})


def _normalize_for_match(text: str) -> str:
    """Lowercase, fold every run of non-alphanumeric (punctuation/whitespace) to a
    single space, and strip. Verbatim grade-block containment is measured on THIS
    form so that spacing/punctuation drift never masks a genuinely-missing block."""
    return _NORM_RE.sub(" ", str(text).lower()).strip()


def _grade_sentences() -> List[str]:
    """The canonical grade block split into normalized sentences (empties dropped)."""
    return [n for n in (_normalize_for_match(s) for s in _GRADE_BLOCK.split(".")) if n]


def _contiguous_block_present(prompt_norm: str, block_norm: str, window: int) -> bool:
    """True iff any contiguous `window`-char slice of the normalized grade block
    appears verbatim in the normalized prompt. A block shorter than `window` can
    never produce a >= window contiguous match, so returns False (fail-closed)."""
    if len(block_norm) < window:
        return False
    for i in range(0, len(block_norm) - window + 1):
        if block_norm[i:i + window] in prompt_norm:
            return True
    return False


def _check_grade_block(stripped: str, lc: str, who: str) -> List[Tuple[str, str]]:
    """FIX-IMG-06: normalized VERBATIM containment of the canonical _GRADE_BLOCK.
    Fingerprints are a fast pre-check only; clearing them does NOT clear the gate."""
    # Fast pre-check: no fingerprint at all -> the canonical block is nowhere near.
    if not any(fp in lc for fp in GRADE_FINGERPRINTS):
        return [("AF-FUN-PROMPT-GRADE",
                 f"{who}: the SIGNATURE GRADE BLOCK is not embedded "
                 f"(no fingerprint of {list(GRADE_FINGERPRINTS)} present)")]
    prompt_norm = _normalize_for_match(stripped)
    sentences = _grade_sentences()
    present = [s for s in sentences if s in prompt_norm]
    ratio = (len(present) / len(sentences)) if sentences else 0.0
    if ratio >= GRADE_MIN_SENTENCE_RATIO:
        return []
    if _contiguous_block_present(prompt_norm, _normalize_for_match(_GRADE_BLOCK),
                                 GRADE_CONTIGUOUS_NORM_CHARS):
        return []
    missing = [s for s in sentences if s not in present]
    miss_preview = "; ".join(s[:48] + ("..." if len(s) > 48 else "")
                             for s in missing[:3]) or "(none isolated)"
    return [("AF-FUN-PROMPT-GRADE",
             f"{who}: the SIGNATURE GRADE BLOCK appears only in fragments "
             f"({len(present)}/{len(sentences)} canonical sentences = {ratio * 100:.0f}% "
             f"< {GRADE_MIN_SENTENCE_RATIO * 100:.0f}%, and no contiguous "
             f">={GRADE_CONTIGUOUS_NORM_CHARS}-char verbatim run) — missing e.g.: {miss_preview}")]


def evaluate_prompt(record: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Return a list of (AF-code, message) for ONE image-prompt record. Empty == clean."""
    fails: List[Tuple[str, str]] = []
    who = f"page '{record.get('page_type', '?')}' section {record.get('section', '?')}"
    prompt = record.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        fails.append(("AF-FUN-PROMPT-FLOOR", f"{who}: empty / whitespace-only prompt"))
        return fails

    stripped = _stripped(prompt)
    lc = stripped.lower()
    length = len(stripped)

    # FLOOR 1 — length band
    if length < PROMPT_CHAR_FLOOR:
        fails.append(("AF-FUN-PROMPT-FLOOR",
                      f"{who}: {length} stripped chars, under the {PROMPT_CHAR_FLOOR} floor — a prompt "
                      "this short cannot carry the signature specificity; NOT sent to Kie"))
    if length > PROMPT_CHAR_CEILING:
        fails.append(("AF-FUN-PROMPT-CEILING",
                      f"{who}: {length} stripped chars, over the {PROMPT_CHAR_CEILING} ceiling"))

    # FLOOR 2 — density
    distinct = _distinct_words(stripped)
    if distinct < PROMPT_MIN_DISTINCT_WORDS:
        fails.append(("AF-FUN-PROMPT-DENSITY",
                      f"{who}: only {distinct} distinct words (< {PROMPT_MIN_DISTINCT_WORDS}) — "
                      "reads as repetition padding, not a genuinely rich prompt"))

    # FLOOR 2 — signature grade block (FIX-IMG-06: verbatim containment, not a fingerprint)
    fails.extend(_check_grade_block(stripped, lc, who))

    # FLOOR 2 — negative block imperative
    if NEGATIVE_IMPERATIVE not in lc:
        fails.append(("AF-FUN-PROMPT-NEGATIVE",
                      f"{who}: no negative block ('Do not ...' imperative) in the prompt"))

    # FLOOR 2 — em dash ban
    for ch in EM_DASH_CHARS:
        if ch in stripped:
            fails.append(("AF-FUN-PROMPT-EMDASH",
                          f"{who}: contains an em/en dash ({ch!r}) — forbidden in image prompts "
                          "(model-safety rule)"))
            break

    # FLOOR 2 — typography discipline
    text_bearing = bool(record.get("text_bearing"))
    if text_bearing:
        if not any(tok in lc for tok in SPELLING_LOCK_TOKENS):
            fails.append(("AF-FUN-PROMPT-TYPO",
                          f"{who}: text-bearing prompt lacks a spelling-lock directive"))
        words = record.get("words")
        if isinstance(words, list) and words:
            for w in words:
                if str(w).strip() and str(w).strip().lower() not in lc:
                    fails.append(("AF-FUN-PROMPT-TYPO",
                                  f"{who}: baked word {w!r} is not present verbatim in the prompt body"))
                    break
        else:
            fails.append(("AF-FUN-PROMPT-TYPO",
                          f"{who}: text-bearing prompt declares no 'words' array to spelling-lock"))
    else:
        if not any(m in lc for m in NO_TEXT_MARKERS):
            fails.append(("AF-FUN-PROMPT-TYPO",
                          f"{who}: non-text prompt does not state 'no text / no letters / no words'"))

    return fails


def verify(ledger: Dict[str, Any]) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    notes: List[str] = []
    prompts = ledger.get("prompts")
    if not isinstance(prompts, list) or not prompts:
        violations.append(("AF-FUN-PROMPT-FLOOR", "prompt ledger carries no non-empty 'prompts' array"))
        return violations, notes
    for rec in prompts:
        if not isinstance(rec, dict):
            violations.append(("AF-FUN-PROMPT-FLOOR", "a prompt entry is not an object"))
            continue
        violations.extend(evaluate_prompt(rec))
    notes.append(f"checked {len(prompts)} image prompt(s) against the {PROMPT_CHAR_FLOOR}-{PROMPT_CHAR_CEILING} band")
    return violations, notes


# ===========================================================================
# FIX-IMG-07 — COVERAGE (the --structure mode).
# ---------------------------------------------------------------------------
# The two-floor gate above proves each prompt that IS present is rich enough. It
# says nothing about whether the ledger is COMPLETE: a 2-prompt ledger for a
# 12-section, 5-page funnel cleared P2, and a 2-image media ledger certified a
# ~40-image funnel. This mode cross-checks the prompt ledger AND the media ledger
# against the REQUIRED (page_type, section) image set derived deterministically
# from structure/funnel_structure.json (profiles + funnel_matrix) + the brief's
# funnel_size, per MASTERDOC §4 (every numbered copy section carries one signature
# image; the Thank-You page carries one celebratory hero; the Checkout order page
# carries none). Missing pairs fail closed:
#   * a prompt ledger missing a required slot  -> AF-FUN-PROMPT-COVERAGE
#   * a media ledger missing a required slot    -> AF-FUN-IMG-COVERAGE
# ===========================================================================

# A page-level requirement (">= 1 image on this page, no per-section split") is
# carried as this sentinel section key so thank-you/one-hero pages are honored.
ANY_IMAGE = "*"


class StructureError(Exception):
    """Raised when the funnel structure / size cannot resolve -> fail-closed (exit 3)."""


def _default_structure_path() -> Path:
    """structure/funnel_structure.json beside the skill (mirror of prove_sf_graph)."""
    return Path(__file__).resolve().parent.parent / "structure" / "funnel_structure.json"


def load_structure(structure_path: Optional[Path] = None) -> Dict[str, Any]:
    path = structure_path or _default_structure_path()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StructureError(f"cannot load funnel structure {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise StructureError(f"funnel structure {path} is not a JSON object")
    return data


def _norm_section(sec: Any) -> str:
    return str(sec).strip()


def required_image_pairs(size: Any,
                         structure: Dict[str, Any]) -> List[Tuple[str, str]]:
    """The ordered required (page_type, section_key) image set for a funnel size.

    section_key is str(section) for a numbered copy section, or ANY_IMAGE ('*')
    for a page that requires >= 1 image with no per-section split (Thank-You). A
    page whose policy declares zero images (Checkout order page) contributes none.
    Source of truth: funnel_matrix[size] (which pages) + profiles[page].sections
    (which sections) + the image_coverage.page_policies overrides — all in
    structure/funnel_structure.json, per MASTERDOC §4."""
    matrix = structure.get("funnel_matrix")
    if not isinstance(matrix, dict) or not matrix:
        raise StructureError("funnel_structure.json carries no funnel_matrix")
    key = str(size)
    pages = matrix.get(key)
    if not isinstance(pages, list) or not pages:
        raise StructureError(
            f"funnel_size {size!r} is not a matrix key (known sizes: "
            f"{sorted(k for k in matrix if k.isdigit())})")
    profiles = structure.get("profiles") if isinstance(structure.get("profiles"), dict) else {}
    coverage = structure.get("image_coverage") if isinstance(structure.get("image_coverage"), dict) else {}
    page_policies = coverage.get("page_policies") if isinstance(coverage.get("page_policies"), dict) else {}

    pairs: List[Tuple[str, str]] = []
    for raw_page in pages:
        page = str(raw_page).strip()
        if not page:
            continue
        profile = profiles.get(page) if isinstance(profiles.get(page), dict) else {}
        policy = page_policies.get(page) if isinstance(page_policies.get(page), dict) else None
        # 1) explicit per-page policy wins (unless it re-opts into per_section).
        if policy is not None and not policy.get("per_section", False):
            try:
                min_images = int(policy.get("min_images", 0))
            except (TypeError, ValueError):
                min_images = 0
            if min_images >= 1:
                pairs.append((page, ANY_IMAGE))
            continue  # min_images == 0 -> no image required (e.g. checkout)
        # 2) a page with numbered copy sections -> one image per section.
        sections = profile.get("sections")
        if isinstance(sections, list) and sections:
            for sec in sections:
                pairs.append((page, _norm_section(sec)))
            continue
        # 3) a section-less page: thank-you (one hero) needs >= 1; a microcopy-only
        #    order page needs none; anything else defensively needs >= 1.
        if profile.get("thank_you"):
            pairs.append((page, ANY_IMAGE))
        elif profile.get("microcopy_only"):
            continue
        else:
            pairs.append((page, ANY_IMAGE))
    return pairs


def _index_records(records: List[Any]) -> Tuple[set, set]:
    """(present (page_type, section) pairs, present page_types) for a record list."""
    pairs: set = set()
    pages: set = set()
    for rec in records:
        if not isinstance(rec, dict):
            continue
        page = str(rec.get("page_type", "")).strip()
        if not page:
            continue
        pages.add(page)
        sec = rec.get("section")
        if sec is not None and str(sec).strip():
            pairs.add((page, _norm_section(sec)))
    return pairs, pages


def coverage_violations(required: List[Tuple[str, str]],
                        records: List[Any],
                        af_code: str,
                        kind: str) -> List[Tuple[str, str]]:
    """List the required image slots that `records` does NOT cover. A concrete
    (page, section) requirement is met by a matching record; an ANY_IMAGE
    requirement is met by ANY record on that page."""
    present_pairs, present_pages = _index_records(records)
    missing: List[str] = []
    for page, sec in required:
        if sec == ANY_IMAGE:
            if page not in present_pages:
                missing.append(f"{page}:<any-image>")
        elif (page, sec) not in present_pairs:
            missing.append(f"{page}:{sec}")
    if missing:
        return [(af_code,
                 f"the {kind} ledger is missing {len(missing)} of {len(required)} required image "
                 f"slot(s) per MASTERDOC §4 (a partial ledger can never certify a full funnel) — "
                 f"missing: {', '.join(missing)}")]
    return []


def verify_structure(size: Any,
                     ledger: Dict[str, Any],
                     structure: Optional[Dict[str, Any]] = None
                     ) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Coverage cross-check for one ledger. Auto-detects kind by content:
    a `prompts` array is checked for AF-FUN-PROMPT-COVERAGE; an `images` array for
    AF-FUN-IMG-COVERAGE; a ledger carrying both is checked for both. A ledger with
    neither array is a fail-closed usage error (raised by the caller)."""
    structure = structure if structure is not None else load_structure()
    required = required_image_pairs(size, structure)
    violations: List[Tuple[str, str]] = []
    notes: List[str] = []
    prompts = ledger.get("prompts")
    images = ledger.get("images")
    checked_any = False
    if isinstance(prompts, list):
        checked_any = True
        violations.extend(coverage_violations(required, prompts, "AF-FUN-PROMPT-COVERAGE", "prompt"))
        notes.append(f"prompt coverage: {len(prompts)} prompt(s) vs {len(required)} required slot(s)")
    if isinstance(images, list):
        checked_any = True
        violations.extend(coverage_violations(required, images, "AF-FUN-IMG-COVERAGE", "media"))
        notes.append(f"image coverage: {len(images)} image(s) vs {len(required)} required slot(s)")
    if not checked_any:
        raise StructureError(
            "ledger carries neither a 'prompts' nor an 'images' array — nothing to "
            "coverage-check (fail-closed; a vacuous PASS is never allowed)")
    return violations, notes


def _resolve_size(explicit: Optional[str], brief_path: Optional[str]) -> int:
    """Resolve the funnel size from --funnel-size or the brief's funnel_size."""
    if explicit is not None:
        try:
            return int(explicit)
        except (TypeError, ValueError):
            raise StructureError(f"--funnel-size {explicit!r} is not an integer")
    if brief_path:
        try:
            brief = json.loads(Path(brief_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise StructureError(f"cannot read --brief {brief_path}: {exc}")
        size = brief.get("funnel_size") if isinstance(brief, dict) else None
        if not isinstance(size, int):
            raise StructureError(f"brief {brief_path} has no integer funnel_size (got {size!r})")
        return size
    raise StructureError("no funnel size — pass --funnel-size N or --brief brief.json")


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------
def _load_json(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def _report(violations, notes) -> None:
    for note in notes:
        print(f"NOTE: {note}")
    if not violations:
        print(f"PASS: every image prompt clears the two-floor gate ({PROMPT_CHAR_FLOOR}-{PROMPT_CHAR_CEILING}).")
        return
    print(f"FAIL: {len(violations)} prompt violation(s) — the failing prompt is NOT sent to Kie.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test fixtures.
# ---------------------------------------------------------------------------
# A large distinct-word vocabulary so the valid fixture clears the density floor without padding.
_VOCAB = (
    "commanding runway editorial wardrobe tailored silk velvet emerald sapphire crimson "
    "amber onyx pearl bronze copper indigo scarlet marigold teal magenta ivory obsidian "
    "posture stance confidence composition foreground midground background aperture bokeh "
    "strobe softbox rimlight backlight golden dawn dusk horizon skyline atelier boulevard "
    "sculpted cheekbones jawline gaze intensity serenity triumph resilience momentum ascent "
    "photographer hasselblad medium format microcontrast grain filmic tackssharp focal plane "
    "gallery canvas frame lighting texture material couture threadwork embroidery lapel cuff "
    "hue chroma luminance vibrance grade cinematic palette contrast shadow highlight radiance "
    "portrait figure silhouette angle profile symmetry asymmetry negative space rulethirds "
    "brand emerald deep green accent statement garment jewelry adornment regal spiritual deco "
    "oilpaint depth painterly stroke pigment saturation dimensional warmth undertone glow "
    "electric jeweltone disruptive provocative unforgettable striking scrolling thumb stops"
)


def _valid_photo_prompt(target: int = 6500) -> str:
    body = ("A single commanding subject fills the frame in a fashion-show hero portrait. "
            "SUBJECT AND WARDROBE: an editorial figure in brand-color couture. "
            "COMPOSITION AND SHOT: eye level, off center left on rule of thirds. ")
    body += _GRADE_BLOCK + " "
    body += "LIGHTING: studio strobe with a rim light carving the silhouette. "
    body += "QUALITY AND RENDER: 2K editorial finish, medium format microcontrast. "
    body += "FACIAL INTELLIGENCE: deep skin tones rendered rich and dimensional, never ashy. "
    body += "No text, no letters, no words anywhere in the image. "
    # extend with distinct vocabulary until the length target is met (no em dashes)
    words = (_VOCAB + " ").split()
    i = 0
    while len(body) < target:
        body += words[i % len(words)] + " "
        i += 1
    body += ("BRAND STYLE AND NEGATIVE BLOCK: fashion show rendered as gallery art. "
             "Do not produce flat, muted, pastel, desaturated, washed out, or low contrast color. "
             "Do not add any text. Do not distort hands, eyes, or teeth.")
    return body


def _valid_typography_prompt(target: int = 6500) -> str:
    body = ("An art gallery interior with three framed canvases. TYPOGRAPHY: each canvas "
            "carries one big bold artistic word, spelling-lock each string letter for letter, "
            'the words "DECIDE" and "COMMIT" and "RISE" spelled exactly as written. ')
    body += _GRADE_BLOCK + " "
    body += "LIGHTING: gallery track lighting grazing each canvas. "
    words = (_VOCAB + " ").split()
    i = 0
    while len(body) < target:
        body += words[i % len(words)] + " "
        i += 1
    body += ("BRAND STYLE AND NEGATIVE BLOCK. Do not misspell any word. "
             "Do not add any words other than those specified. Do not distort the letterforms.")
    return body


def _valid_ledger() -> Dict[str, Any]:
    return {
        "funnel_type": "signature_funnel",
        "prompts": [
            {"page_type": "main", "section": 1, "aspect_ratio": "16:9",
             "text_bearing": False, "prompt": _valid_photo_prompt()},
            {"page_type": "main", "section": 11, "aspect_ratio": "16:9",
             "text_bearing": True, "words": ["DECIDE", "COMMIT", "RISE"],
             "prompt": _valid_typography_prompt()},
        ],
    }


def _violation_cases():
    def too_short(led):
        led["prompts"][0]["prompt"] = "short prompt " * 5
    def too_long(led):
        led["prompts"][0]["prompt"] = _valid_photo_prompt(19100) + _VOCAB * 60
    def no_grade(led):
        p = _valid_photo_prompt().replace("140 percent", "a bit more").replace(
            "signature color", "regular color").replace("melanin-true", "even").replace(
            "Signature aesthetic", "plain look")
        led["prompts"][0]["prompt"] = p
    def no_negative(led):
        p = _valid_photo_prompt()
        led["prompts"][0]["prompt"] = p.replace("Do not ", "Please avoid ")
    def em_dash(led):
        p = _valid_photo_prompt()
        led["prompts"][0]["prompt"] = p + " a striking subject — the hero of the page."
    def typo_notext(led):
        p = _valid_photo_prompt().replace("No text, no letters, no words anywhere in the image. ", "")
        led["prompts"][0]["prompt"] = p
    def typo_nolock(led):
        p = _valid_typography_prompt()
        for tok in SPELLING_LOCK_TOKENS:
            p = p.replace(tok, "written").replace(tok.title(), "written")
        p = p.replace("spelling-lock", "written").replace("spelled exactly", "written")
        led["prompts"][1]["prompt"] = p
    def density(led):
        # long enough but only a few distinct words repeated
        led["prompts"][0]["text_bearing"] = False
        led["prompts"][0]["prompt"] = ((_GRADE_BLOCK.split(".")[0] + ". no text here. do not add text. ")
                                       + "signature color grade vibrant bold " * 400)

    def grade_fingerprint_only(led):
        # FIX-IMG-06 anti-gaming: a fingerprint phrase ("signature grade") is present
        # but the canonical block is NOT — the old any-of-five substring gate cleared
        # this; verbatim containment must now reject it.
        p = _valid_photo_prompt().replace(
            _GRADE_BLOCK, "The overall look should feel like signature grade work. ")
        led["prompts"][0]["prompt"] = p

    def _mk(fn):
        led = _valid_ledger()
        fn(led)
        return led

    return [
        ("too_short", "AF-FUN-PROMPT-FLOOR", lambda: _mk(too_short)),
        ("too_long", "AF-FUN-PROMPT-CEILING", lambda: _mk(too_long)),
        ("no_grade_block", "AF-FUN-PROMPT-GRADE", lambda: _mk(no_grade)),
        ("no_negative_block", "AF-FUN-PROMPT-NEGATIVE", lambda: _mk(no_negative)),
        ("em_dash", "AF-FUN-PROMPT-EMDASH", lambda: _mk(em_dash)),
        ("typo_missing_no_text", "AF-FUN-PROMPT-TYPO", lambda: _mk(typo_notext)),
        ("typo_missing_spelling_lock", "AF-FUN-PROMPT-TYPO", lambda: _mk(typo_nolock)),
        ("density_padding", "AF-FUN-PROMPT-DENSITY", lambda: _mk(density)),
        ("grade_fingerprint_only", "AF-FUN-PROMPT-GRADE", lambda: _mk(grade_fingerprint_only)),
    ]


# --- FIX-IMG-07 coverage fixtures -------------------------------------------
def _full_coverage_prompts(size: int) -> Dict[str, Any]:
    """A prompt ledger whose (page_type, section) set exactly covers the required
    image set for `size` (prompt bodies are irrelevant to the coverage gate)."""
    required = required_image_pairs(size, load_structure())
    prompts = []
    for page, sec in required:
        section = 1 if sec == ANY_IMAGE else sec
        prompts.append({"page_type": page, "section": section, "prompt": "covered"})
    return {"funnel_type": "signature_funnel", "prompts": prompts}


def _floor_passing_full_prompts(size: int) -> Dict[str, Any]:
    """A prompt ledger that covers the required set for `size` AND whose every prompt
    clears the two-floor gate — used by the orchestrator self-test so a valid run
    passes BOTH the P2 floor gate and the P2 coverage cross-check."""
    required = required_image_pairs(size, load_structure())
    prompts = []
    for page, sec in required:
        if page == "main" and str(sec) == "11":
            prompts.append({"page_type": page, "section": 11, "text_bearing": True,
                            "words": ["DECIDE", "COMMIT", "RISE"],
                            "prompt": _valid_typography_prompt()})
        else:
            section = "hero" if sec == ANY_IMAGE else sec
            prompts.append({"page_type": page, "section": section, "text_bearing": False,
                            "prompt": _valid_photo_prompt()})
    return {"funnel_type": "signature_funnel", "prompts": prompts}


def _full_coverage_images(size: int) -> Dict[str, Any]:
    """A media ledger whose image records exactly cover the required set for `size`."""
    required = required_image_pairs(size, load_structure())
    images = []
    for page, sec in required:
        section = "hero" if sec == ANY_IMAGE else sec
        images.append({"page_type": page, "section": section,
                       "kie_task_id": f"kie_{page}_{section}",
                       "media_url": f"https://storage.gohighlevel.com/loc/x/{page}-{section}.png"})
    return {"funnel_type": "signature_funnel", "images": images}


def run_coverage_self_test() -> bool:
    ok = True
    structure = load_structure()
    for size in (3, 5, 7):
        required = required_image_pairs(size, structure)
        # (a) a full-coverage prompt ledger clears AF-FUN-PROMPT-COVERAGE.
        v, _ = verify_structure(size, _full_coverage_prompts(size), structure)
        if v:
            ok = False
            print(f"COVERAGE SELF-TEST FAIL: full prompt coverage (size {size}) flagged: {v}")
        else:
            print(f"COVERAGE SELF-TEST ok: full prompt coverage (size {size}) PASSES ({len(required)} slots).")
        # (b) a full-coverage media ledger clears AF-FUN-IMG-COVERAGE.
        v, _ = verify_structure(size, _full_coverage_images(size), structure)
        if v:
            ok = False
            print(f"COVERAGE SELF-TEST FAIL: full image coverage (size {size}) flagged: {v}")
        else:
            print(f"COVERAGE SELF-TEST ok: full image coverage (size {size}) PASSES ({len(required)} slots).")
        # (c) a 2-prompt ledger for a full funnel is caught (AF-FUN-PROMPT-COVERAGE).
        skimpy_p = {"prompts": [{"page_type": "main", "section": 1, "prompt": "x"},
                                {"page_type": "main", "section": 2, "prompt": "y"}]}
        v, _ = verify_structure(size, skimpy_p, structure)
        codes = {c for c, _ in v}
        if "AF-FUN-PROMPT-COVERAGE" in codes:
            print(f"COVERAGE SELF-TEST ok: 2-prompt ledger (size {size}) -> AF-FUN-PROMPT-COVERAGE.")
        else:
            ok = False
            print(f"COVERAGE SELF-TEST FAIL: 2-prompt ledger (size {size}) not caught: {sorted(codes)}")
        # (d) a 2-image media ledger for a full funnel is caught (AF-FUN-IMG-COVERAGE).
        skimpy_i = {"images": [{"page_type": "main", "section": 1, "kie_task_id": "k",
                                "media_url": "https://msgsndr.com/a.png"},
                               {"page_type": "main", "section": 5, "kie_task_id": "k2",
                                "media_url": "https://msgsndr.com/b.png"}]}
        v, _ = verify_structure(size, skimpy_i, structure)
        codes = {c for c, _ in v}
        if "AF-FUN-IMG-COVERAGE" in codes:
            print(f"COVERAGE SELF-TEST ok: 2-image ledger (size {size}) -> AF-FUN-IMG-COVERAGE.")
        else:
            ok = False
            print(f"COVERAGE SELF-TEST FAIL: 2-image ledger (size {size}) not caught: {sorted(codes)}")
    # (e) an unknown funnel size is fail-closed (StructureError).
    try:
        required_image_pairs(4, structure)
        ok = False
        print("COVERAGE SELF-TEST FAIL: funnel_size 4 did not raise StructureError.")
    except StructureError:
        print("COVERAGE SELF-TEST ok: unknown funnel_size 4 -> fail-closed (StructureError).")
    # (f) a ledger with neither prompts nor images is fail-closed.
    try:
        verify_structure(3, {"funnel_type": "signature_funnel"}, structure)
        ok = False
        print("COVERAGE SELF-TEST FAIL: empty ledger did not raise StructureError.")
    except StructureError:
        print("COVERAGE SELF-TEST ok: ledger with no prompts/images -> fail-closed (StructureError).")
    return ok


def run_self_test() -> int:
    ok = True
    v, _ = verify(_valid_ledger())
    if v:
        ok = False
        print(f"SELF-TEST FAIL: valid fixture produced {len(v)} violation(s): {v}")
    else:
        print("SELF-TEST ok: valid fixture PASSES (0 violations).")
    cases = _violation_cases()
    caught = 0
    for name, expected, build in cases:
        vio, _ = verify(build())
        codes = {c for c, _ in vio}
        if not vio:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' produced NO violations (expected {expected}).")
        elif expected not in codes:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' -> {sorted(codes)} (expected {expected}).")
        else:
            caught += 1
            print(f"SELF-TEST ok: '{name}' -> nonzero, carries {expected}.")
    print(f"SELF-TEST FIXTURES: {1 if not v else 0} valid-pass, {caught}/{len(cases)} violation-catch")
    # FIX-IMG-07 — the --structure coverage cross-check (prompt + image ledgers).
    if not run_coverage_self_test():
        ok = False
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description=f"Fail-closed two-floor gate for Signature Funnel image prompts "
                    f"({PROMPT_CHAR_FLOOR}-{PROMPT_CHAR_CEILING} chars). Exit 0 pass, 2 violation, 3 usage.")
    ap.add_argument("--ledger", help="path to the image-prompt ledger JSON ('-' reads stdin)")
    # FIX-IMG-05: also accept an optional POSITIONAL ledger path so the SOP-FUNNEL-03
    # verify form (`prove_sf_prompt_floor.py <ledger>`) resolves to a real run instead
    # of an argparse rc=2 that is indistinguishable from a genuine violation.
    ap.add_argument("ledger_pos", nargs="?",
                    help="optional positional ledger path (equivalent to --ledger)")
    ap.add_argument("--self-test", action="store_true",
                    help="construct a VALID fixture (must PASS) + each VIOLATION fixture (must FAIL)")
    # FIX-IMG-07: --structure runs the COVERAGE cross-check instead of the two-floor
    # gate — the ledger's (page_type, section) set must cover the required image set
    # derived from funnel_structure.json + funnel_size (per MASTERDOC §4).
    ap.add_argument("--structure", action="store_true",
                    help="coverage mode: prove the ledger covers the required (page_type, section) "
                         "image set for the funnel size (AF-FUN-PROMPT-COVERAGE / AF-FUN-IMG-COVERAGE)")
    ap.add_argument("--funnel-size", help="funnel size 3/5/7 (coverage mode; or use --brief)")
    ap.add_argument("--brief", help="brief.json to read funnel_size from (coverage mode)")
    ap.add_argument("--structure-source",
                    help="path to funnel_structure.json (default: the skill's structure/funnel_structure.json)")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()

    ledger_path = args.ledger or args.ledger_pos
    if not ledger_path:
        print("USAGE ERROR: pass --ledger <prompts.json> (or a positional path, or --self-test).")
        return EXIT_FAILCLOSED
    try:
        ledger = _load_json(ledger_path)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load ledger {ledger_path!r}: {exc}")
        return EXIT_FAILCLOSED
    if not isinstance(ledger, dict):
        print("USAGE/IO ERROR: ledger must be a JSON object.")
        return EXIT_FAILCLOSED

    if args.structure:
        try:
            structure = load_structure(Path(args.structure_source) if args.structure_source else None)
            size = _resolve_size(args.funnel_size, args.brief)
            violations, notes = verify_structure(size, ledger, structure)
        except StructureError as exc:
            print(f"FAIL-CLOSED: {exc}")
            return EXIT_FAILCLOSED
        for note in notes:
            print(f"NOTE: {note}")
        if not violations:
            print(f"PASS: the ledger covers every required (page_type, section) image slot "
                  f"for the {size}-step funnel.")
            return EXIT_OK
        print(f"FAIL: {len(violations)} coverage violation(s) — a partial ledger can never certify a full funnel.")
        for code, msg in violations:
            print(f"  VIOLATION [{code}] {msg}")
        return EXIT_VIOLATION

    violations, notes = verify(ledger)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
