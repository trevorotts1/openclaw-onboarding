#!/usr/bin/env python3
"""
social_prompt_compiler.py — F32 social-planner image prompt compiler + validator.

Owner requirement (SPEC "Build contract for detailed image prompts" and KIE prompt
rule 12, 2026-10-05): every final social-planner image prompt for a KIE model is 95 to
100 percent of that model's maxLength, never below 80 percent. The limit and the band
come from the shared enforcer shared-utils/kie_prompt_enforcer.py (Skill 74
prompt-budget); this module keeps no floor or ceiling of its own. A model with no known
limit (Agnes is not a KIE model) has no floor. The client may supply one short sentence;
this compiler produces the full brief and rewrites it up to 3 times to reach the band.

Contract:
  - count = len(unicodedata.normalize("NFC", final_prompt).strip())  (Python)
    TypeScript parity: Array.from(normalized.trim()).length  (code points, NOT
    UTF-16 .length — see social_prompt_policy.json count_rule).
  - validate AFTER reference instructions + negatives are added (the final
    transmitted payload, never an intermediate draft).
  - record hash + count + policy version + provider/model + capability source
    with every compiled prompt (the "spend receipt").
  - expand a short brief with USEFUL visual decisions (never repetitive filler);
    condense an overlong brief without losing required meaning; reject
    padding/repetition and contradictory requirements (esp. the Agnes
    logo-vs-style-reference conflict) BEFORE any paid call.
  - token budget so limits cannot silently truncate: over-budget compiles are
    condensed to fit, never truncated mid-content, never silently sent.
  - the band is rule 12 (percentages of the model maxLength), not a fixed house number
    (Kie GPT Image 2.5 maxLength 20000; Agnes publishes no cap, NOT_PUBLISHED).

Scoped override: social planner ONLY. Unrelated skills keep their own bands.
Policy data lives in social_prompt_policy.json (same directory).

STDLIB ONLY.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import unicodedata
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kie_prompt_enforcer  # noqa: E402  (the one rule 12 enforcer; sits beside this file)

_DEFAULT_MODEL = "gpt-image-2-5-sunburst-text-to-image"

_EXIT_OK = 0
_EXIT_FAIL = 2

_POLICY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "social_prompt_policy.json")
_POLICY_CACHE: Optional[dict] = None


def load_policy(path: str = _POLICY_PATH) -> dict:
    """Load the social prompt policy (cached)."""
    global _POLICY_CACHE
    if _POLICY_CACHE is None or path != _POLICY_PATH:
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        if path == _POLICY_PATH:
            _POLICY_CACHE = data
        return data
    return _POLICY_CACHE


# ─── The counting rule (the contract) ────────────────────────────────────────

def count_chars(final_prompt: str) -> int:
    """THE count: len(unicodedata.normalize("NFC", final).strip()).

    Counts Unicode code points of the NFC-normalized, stripped final string.
    This is the exact rule the TypeScript mirror implements as
    Array.from(normalized.trim()).length — Array.from iterates code points,
    while .length would count UTF-16 units and double-count astral characters.
    """
    return len(unicodedata.normalize("NFC", final_prompt).strip())


def sha256_of(final_prompt: str) -> str:
    """Payload hash recorded with the spend receipt (over the EXACT transmitted
    NFC-normalized, stripped string — same bytes the count sees)."""
    normalized = unicodedata.normalize("NFC", final_prompt).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ─── Padding detection ────────────────────────────────────────────────────────

_SPLIT_RE = re.compile(r"\s+")


def _sentences(text: str) -> list:
    # Split on sentence enders and newlines; keep non-trivial sentences only.
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 8]


def _word_ngrams(text: str, n: int) -> list:
    words = [w for w in _SPLIT_RE.split(text.lower()) if w]
    return [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]


def find_padding(final_prompt: str) -> list:
    """Detect repetitive filler in the FINAL prompt. Returns a list of problems
    ([] = clean). Two signals, per policy rejection_rules.padding:
      1. any SENTENCE (>=8 chars) appearing more than once;
      2. duplicated 8-word-gram ratio above the policy threshold (0.08).
    """
    problems: list = []
    policy = load_policy()
    threshold = 0.08

    seen = {}
    for s in _sentences(final_prompt):
        key = re.sub(r"\s+", " ", s.lower())
        seen[key] = seen.get(key, 0) + 1
    for key, n in seen.items():
        if n > 1:
            problems.append(
                f"AF-PROMPT-PADDING: sentence appears {n} times in the final "
                f"prompt: {key[:80]!r}… — expansion must add useful visual "
                "decisions, never repeated filler.")

    grams = _word_ngrams(final_prompt, 8)
    if grams:
        from collections import Counter
        counts = Counter(grams)
        dup = sum(c - 1 for c in counts.values() if c > 1)
        ratio = dup / len(grams)
        if ratio > threshold:
            problems.append(
                f"AF-PROMPT-PADDING: duplicated 8-word-gram ratio {ratio:.3f} "
                f"exceeds {threshold} — the prompt is padded with repeated "
                "phrasing, not useful visual decisions.")
    _ = policy  # policy currently carries the threshold inline; kept for provenance
    return problems


# ─── Contradiction detection ─────────────────────────────────────────────────

def find_contradictions(brief: dict) -> list:
    """Reject contradictory requirements BEFORE spend. Returns problems ([]=ok).

    Priority contradiction (the corrected Agnes logo rule): an identity/logo
    reference PRESERVES the approved mark; a style-only reference must NOT copy
    subject/text. Per-reference instructions — never global. So:
      - identity reference carrying a style-only directive → conflict
      - style reference carrying a preserve-the-mark directive → conflict
    """
    problems: list = []
    refs = brief.get("logo_rules", {}).get("references") or \
        brief.get("references") or []
    style_only_markers = ("style only", "style-only", "do not copy", "don't copy",
                          "not copy their subjects", "do not copy their subjects")
    preserve_markers = ("preserve", "reproduce exactly", "preserve the approved mark",
                        "reproduce this reference exactly")

    for i, ref in enumerate(refs):
        if not isinstance(ref, dict):
            continue
        role = str(ref.get("role", "")).strip().lower()
        instruction = str(ref.get("instruction", "")).lower()
        if not instruction:
            continue
        has_style_only = any(m in instruction for m in style_only_markers)
        has_preserve = any(m in instruction for m in preserve_markers)
        if role == "identity" and has_style_only:
            problems.append(
                f"AF-PROMPT-CONFLICT: reference {i} is an identity/logo reference "
                "but carries a style-only do-not-copy directive. An identity/logo "
                "reference PRESERVES the approved mark; a style-only reference must "
                "not copy subject/text. Instructions are per-reference, never global.")
        if role == "style" and has_preserve:
            problems.append(
                f"AF-PROMPT-CONFLICT: reference {i} is a style-only reference but "
                "carries a preserve-the-mark directive. Style-only references must "
                "not copy subject/text; logo preservation belongs on an identity "
                "reference.")
    return problems


# ─── Reference instruction blocks (role-correct, per-reference) ──────────────

def reference_instruction_blocks(brief: dict) -> list:
    """Role-correct instruction block per reference. These are APPENDED to the
    prompt before final validation (validate AFTER references + negatives)."""
    blocks = []
    refs = brief.get("logo_rules", {}).get("references") or \
        brief.get("references") or []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        role = str(ref.get("role", "")).strip().lower()
        name = str(ref.get("name") or ref.get("asset_id") or "reference")
        if role == "identity":
            blocks.append(
                f"{name}: IDENTITY reference. REPRODUCE this reference exactly: "
                "preserve the approved mark's geometry, colors, proportions and "
                "wordmark spelling. Do not redraw, recolor, restyle or reinterpret it.")
        elif role == "product":
            blocks.append(
                f"{name}: PRODUCT reference. Match the reference product's shape, "
                "materials and labeling; do not invent product features.")
        elif role == "layout":
            blocks.append(
                f"{name}: LAYOUT reference. Use for layout structure and spacing "
                "only; do not copy the subject, faces or text.")
        elif role == "style":
            blocks.append(
                f"{name}: STYLE reference ONLY for color grading, lighting and "
                "composition mood — do not copy its subjects, faces, or text.")
        else:
            blocks.append(
                f"{name}: UNROLEd reference — assign an explicit role "
                "(identity|product|layout|style) before spend.")
    return blocks


# ─── Expansion / condensation ────────────────────────────────────────────────

def _palette_text(brief: dict) -> str:
    pal = brief.get("brand_palette") or {}
    if isinstance(pal, dict) and pal:
        parts = [f"{slot} {hexv}" for slot, hexv in sorted(pal.items())]
        return "; ".join(parts)
    return str(pal or "the client's verified brand palette")


def _dest(brief: dict) -> dict:
    d = brief.get("destination_dimensions") or {}
    return {
        "platform": d.get("platform", "the destination platform"),
        "ratio": d.get("ratio", "4:5"),
        "pixels": d.get("pixels", "1080x1350"),
    }


def expand_sections(brief: dict, target: Optional[int] = None) -> str:
    """Expand a short brief into the full 8-section structure using useful
    visual decisions derived from the brief's own fields (audience, purpose,
    destination) — never repeated filler. Every section carries REQUIRED info;
    optional guidance blocks degrade gracefully when absent.

    target: characters the writer is aiming for (rule 12 target from the enforcer). None means
    the model limit is unknown: the first-level decision bank is applied in full, no more."""
    dest = _dest(brief)
    audience = brief.get("audience") or "the client's intended audience"
    focal = (brief.get("composition") or {}).get("focal_message") or \
        brief.get("theme") or "the campaign's single focal message"
    palette = _palette_text(brief)
    copy = brief.get("copy") or {}
    on_image = copy.get("on_image_text") or ""
    safe = brief.get("safe_areas") or {}
    keep_in = safe.get("keep_in", "the central 80%")
    ratio = (brief.get("composition") or {}).get("ratio") or dest["ratio"]

    sections = [
        # 1. Purpose and audience
        (True, lambda: (
            f"Purpose and audience: {brief.get('objective') or 'a social-planner campaign image'} "
            f"for {dest['platform']}, intended emotional response: "
            f"{brief.get('emotional_response') or 'confidence and relevance'}, with one clear "
            f"focal message: {focal}. The audience is {audience}.")),
        # 2. Brand and reference roles
        (True, lambda: (
            f"Brand and reference roles: use the verified palette exactly — {palette}. "
            "Typography follows the client's brand rules; each attached reference is "
            "identified by role (identity, product, layout or style) and must be treated "
            "according to that role's instructions below.")),
        # 3. Subject and setting
        (True, lambda: (
            f"Subject and setting: {brief.get('subject') or 'the subject implied by the focal message'}; "
            f"{brief.get('setting') or 'an environment consistent with the real-world use of the brand'}, "
            "with accurate proportions, plausible materials and no invented client-specific "
            "product facts.")),
        # 4. Composition
        (True, lambda: (
            f"Composition: clear hierarchy with {focal} as the dominant focal point; framing "
            f"and whitespace planned for a {ratio} crop; important elements held inside "
            f"{keep_in} of the frame so platform UI never covers them; camera perspective "
            "chosen to flatter the subject without gimmick distortion.")),
        # 5. Lighting and finish
        (True, lambda: (
            f"Lighting and finish: {brief.get('lighting') or 'soft directional key light with gentle fill'}, "
            f"shadows consistent with the scene, color grade matched to the brand palette "
            f"({palette}), textures rendered photographically, contrast balanced for small-screen "
            "legibility; omit irrelevant camera jargon.")),
        # 6. Exact text
        (True, lambda: (
            f"Exact text: {'render the on-image copy exactly as specified: ' + repr(on_image) + '. Spelling is locked letter-for-letter; placement and hierarchy follow the copy plan.' if on_image else 'NO text appears in this image — state this explicitly and render zero letterforms.'}")),
        # 7. Preservation and exclusions (negatives appended by caller too)
        (True, lambda: (
            "Preservation and exclusions: for edits, keep what is approved unchanged and change "
            "only what is directed; avoid brand avoid-list items, watermarks, garbled or "
            "misspelled text, extra fingers or limbs, fused hands, warped faces, cluttered "
            "backgrounds behind text, off-palette color drift, and flat illustrated looks where "
            "photographic finish is required.")),
        # 8. Output and QC
        (True, lambda: (
            f"Output and QC: deliver {dest['pixels']} ({dest['ratio']}) for {dest['platform']}; "
            "acceptance requires exact dimensions, correct crop inside safe areas, legible "
            "correctly spelled text (if any), brand-consistent palette and mark fidelity, and "
            "visual consistency with the other assets in this cycle.")),
    ]
    parts = []
    for required, fn in sections:
        try:
            parts.append(fn())
        except Exception:  # pragma: no cover — defensive; a broken section is skipped
            continue

    # Rule 12: a short brief is expanded with useful visual decisions, never
    # repetitive filler. The decision bank below derives additional genuine
    # guidance from the brief's own fields (platform, audience, purpose, copy),
    # following the fifteen expansion dimensions of the house prompt policy
    # (objective, subject geometry, environment, composition, lens, lighting,
    # material, palette, typography, brand rules, reference roles, preservation,
    # exclusions, output, QC-critical detail) — each block states a DIFFERENT
    # decision the renderer can actually use.
    count_now = count_chars("\n".join(parts))
    policy_floor = target if target else float("inf")
    if count_now < policy_floor:
        # Second-pass enrichment: when the base sections plus the whole
        # decision bank still sit under the floor, deepen each decision block
        # with destination-specific detail (platform context, audience,
        # destination spec). This keeps expansion USEFUL (every sentence is a
        # distinct render decision) while meeting the house floor.
        ratio = (brief.get("composition") or {}).get("ratio") or dest["ratio"]
        enrichees = [
            ("Visual hierarchy decision",
             f" On a {dest['ratio']} placement the hierarchy also decides what survives the "
             "feed crop: the primary read sits high enough in the frame that the platform's "
             "overlay never covers it, and the composition works equally as a full-bleed "
             "story frame and as a cropped grid tile."),
            ("Screen-context decision",
             " Assume the feed shows this image between personal photos and competing "
             "creative for under a second: the value of stopping the scroll is placed in "
             "one unmistakable element rather than spread thin, and the frame avoids the "
             "generic stock look audiences scroll past without registering."),
            ("Palette application decision",
             " Where the platform interface itself is dark or light, the palette is checked "
             "against both: critical elements keep contrast on whichever theme the viewer "
             "uses, and no essential detail depends on a color the interface can wash out."),
            ("Material realism decision",
             " Edge quality matters as much as surface response: silhouettes are clean, "
             "aliased edges and halo artifacts are absent, and translucency (glass, liquid, "
             "fabric sheen) is rendered with believable refraction rather than a flat "
             "opacity trick."),
            ("Camera and lens decision",
             " The chosen vantage matches how the audience would actually encounter the "
             "subject — product work respects the angle a shopper would see, people work "
             "respects a respectful eye level — because a wrong vantage reads as falseness "
             "even when the render is otherwise flawless."),
            ("Emotional register decision",
             f" The register stays calibrated for {audience}: aspirational without being "
             "exclusive, credible without being clinical, and always consistent with the "
             "voice the brand uses in its copy so image and caption tell one story."),
            ("Consistency decision",
             " If this asset belongs to a carousel or series, its visual weight matches the "
             "sequence — the first frame carries the strongest pull, interior frames carry "
             "the value, and the final frame closes with the call to action rather than "
             "restarting the pitch."),
            ("Legibility and safety decision",
             " Contrast behind any letterform is verified at delivery size, not just at "
             "full resolution: what reads on a studio monitor must still read on a mid-range "
             "phone in daylight, so backgrounds behind text stay quiet and text zones keep "
             "a protected margin."),
            ("Geometry decision",
             " Depth cues agree across the frame — occlusion, scale, shadow and haze point "
             "to one consistent spatial story — and nothing renders inside-out or "
             "inside another object where surfaces meet."),
            ("Environment decision",
             " Every background element earns its place by reinforcing the message or the "
             "mood; the environment is dressed only to the level the destination justifies, "
             "because detail the viewer never sees is detail spent for nothing."),
            ("Typography decision",
             " Letter spacing, weight and size follow one scale across the whole image, the "
             "most important word carries the most weight, and no line breaks in a way that "
             "splits a name or number across lines."),
            ("Preservation decision",
             " Where two instructions could touch the same pixel — a style change near the "
             "mark, a crop near approved product art — preservation wins and the change "
             "moves to a safe area instead."),
            ("Exclusion decision",
             " The exclusion list is checked last, at full size and at delivery size, "
             "because the artifacts it names most often appear small: a stray finger at the "
             "crop edge, a misspelled word in fine print, a watermark masquerading as a "
             "texture."),
            ("Lighting continuity decision",
             " Practical lights inside the scene (screens, lamps, sky) agree in color and "
             "direction with the key light, so the frame never shows two kinds of daylight "
             "in one room."),
            ("Acceptance rehearsal decision",
             f" Final delivery states the exact provider output requested — {dest['pixels']}, "
             f"{dest['ratio']} — and any regeneration re-runs this entire instruction set "
             "rather than shrinking to a thinner prompt, so quality never degrades between "
             "attempts."),
        ]
        by_prefix = {name: block for name, block in
                     ((e[0], e[1]) for e in enrichees)}
        new_parts = []
        for line in "\n".join(parts).split("\n"):
            enriched = False
            for prefix, extra in by_prefix.items():
                if line.startswith(prefix):
                    line = line + extra
                    enriched = True
                    break
            new_parts.append(line)
        parts = ["\n".join(new_parts)]
        decision_bank = [
            lambda: (
                f"Visual hierarchy decision: the eye must land first on the focal element "
                f"carrying {focal}, second on the supporting subject, third on any brand "
                "element; every other detail is subordinated so nothing competes with the "
                "primary read at feed size. Secondary elements use reduced contrast and "
                "smaller scale, and the composition never splits attention between two "
                "equally weighted centers."),
            lambda: (
                f"Screen-context decision: {dest['platform']} renders this image at "
                f"{dest['pixels']} next to user-generated content, so contrast between the "
                "subject and background stays strong at thumbnail scale, edge-to-edge detail "
                "survives feed compression, and nothing critical sits under platform UI "
                "chrome such as captions, profile rails or action bars."),
            lambda: (
                f"Palette application decision: the verified brand palette ({palette}) is "
                "applied with the dominant color covering the largest area, an accent color "
                "reserved for the single most important element, and neutral tones carrying "
                "the background — never an even split that dilutes brand recognition. Color "
                "temperature stays consistent across the frame so the grade reads as one "
                "scene rather than a collage."),
            lambda: (
                f"Material realism decision: surfaces render with physically plausible "
                "response to the declared lighting — matte materials scatter softly, glossy "
                "surfaces show restrained specular highlights, and fabric, hair or skin "
                "texture stays true to scale so the finished frame reads as photography "
                "rather than an illustration or a render."),
            lambda: (
                f"Camera and lens decision: a natural field of view flatters the subject; "
                "perspective lines converge believably, the focal plane sits on the most "
                "expressive detail, and background separation comes from distance and light "
                "rather than artificial blur. Lens distortion is controlled at the edges so "
                "verticals stay straight where the composition places them."),
            lambda: (
                f"Emotional register decision: the pose, expression and setting align with "
                f"the intended response for {audience} — body language open and credible, "
                "genuine rather than stock-pose affect, the environment suggesting the real "
                "context in which the audience encounters the offer. The mood is specific "
                "enough to be recognized in a single glance."),
            lambda: (
                f"Consistency decision: this frame shares one visual system with the rest of "
                "the cycle's assets — the same grade, the same safe-area discipline and the "
                "same subject treatment — so the weekly set reads as one campaign rather "
                "than unrelated images. Reused motifs repeat exactly rather than "
                "approximately, so drift never reads as error."),
            lambda: (
                f"Legibility and safety decision: any text zone, logo or mark sits entirely "
                f"inside {keep_in} of the frame with clear space around the mark, high local "
                "contrast behind letterforms, and no element bleeding toward the crop edge on "
                f"the {dest['ratio']} placement. Fine detail keeps away from the corners "
                "where platform rounding and overlays bite first."),
            lambda: (
                "Geometry decision: proportions of the subject follow realistic anatomy and "
                "the real dimensions of any featured product; hands hold objects with "
                "correct finger count and grip; eyelines meet the implied viewer or scene "
                "partner consistently; symmetrical elements stay symmetrical and any "
                "deliberate asymmetry is compositional, not accidental."),
            lambda: (
                f"Environment decision: the setting carries period-appropriate and "
                "place-appropriate details that reinforce the message without clutter — "
                "background depth layers into foreground, midground and backdrop, and no "
                "nonsense object wanders into frame to fill space. Atmosphere (air, dust, "
                "humidity, time of day) matches the declared lighting."),
            lambda: (
                "Typography decision: when copy is present it renders in a clean, "
                "brand-appropriate type treatment with correct kerning and no invented "
                "letterforms, sized to remain readable on a phone held at arm's length; "
                "when no copy is present the frame contains zero letterforms, including "
                "incidental background signage."),
            lambda: (
                "Preservation decision: where the brief references approved assets, what is "
                "approved remains unchanged — the mark is not redrawn, recolored or "
                "reinterpreted, approved product details are not reinvented, and any edit "
                "confines itself to the areas the brief directs, leaving the rest of the "
                "approved composition intact."),
            lambda: (
                "Exclusion decision: the finished frame is free of watermarks, generated "
                "signatures, garbled or misspelled text, extra fingers or limbs, fused "
                "hands, warped faces, melted objects, clutter competing with the focal "
                "message, off-palette color drift, and flat illustrated looks where "
                "photographic finish is required."),
            lambda: (
                f"Lighting continuity decision: one light logic governs the whole frame — "
                "shadow direction, shadow density, highlight temperature and fill level all "
                "agree with the declared key light; reflections in glossy or glass surfaces "
                "show a plausible source; no element is lit from a direction the scene does "
                "not support."),
            lambda: (
                f"Acceptance rehearsal decision: before delivery the frame is checked "
                f"against the destination spec — exact {dest['pixels']} delivery, correct "
                f"{dest['ratio']} crop inside safe areas, correctly spelled text (if any), "
                "brand-consistent palette, faithful mark reproduction, and visual coherence "
                "with the other assets in this cycle; any failure returns to revision rather "
                "than to the client."),
        ]
        for fn in decision_bank:
            if count_chars("\n".join(parts)) >= policy_floor:
                break
            parts.append(fn())
        # Second pass AFTER the bank: re-run the enrichment so deepened
        # detail lands on any decision block added late; run until stable or
        # in-band (bounded loop, never infinite).
        for _ in range(3):
            if count_chars("\n".join(parts)) >= policy_floor:
                break
            joined = "\n".join(parts)
            new_parts = []
            for line in joined.split("\n"):
                for prefix, extra in by_prefix.items():
                    if line.startswith(prefix) and extra not in line:
                        line = line + extra
                        break
                new_parts.append(line)
            parts = ["\n".join(new_parts)]
    return "\n".join(parts)


_CONDENSE_DROP_ORDER = [
    "camera_perspective", "texture_notes", "lighting_note", "mood_notes",
]  # optional guidance blocks, dropped lowest-priority-first


def condense(text: str, target: int, keep_sentences: Optional[list] = None) -> str:
    """Condense an overlong prompt WITHOUT removing required meaning: drop
    optional guidance sentences lowest-priority-first, then compress whitespace.
    Never removes sentences in keep_sentences (required meaning: subject, exact
    text, brand, reference roles, negatives, output spec are protected by the
    caller passing their sentence keys). If required meaning alone exceeds the
    ceiling the caller fails closed — this function never truncates mid-content."""
    keep = set(keep_sentences or [])
    sents = _sentences(text)
    out = list(sents)
    # drop non-required trailing sentences from the tail until it fits
    for s in reversed(sents):
        if len("\n".join(out)) <= target:
            break
        if s not in keep:
            out.remove(s)
    result = re.sub(r"[ \t]+", " ", "\n".join(out))
    if len(result.strip()) > target:
        # required meaning alone exceeds target — signal, never truncate silently
        raise OverflowError(
            f"required meaning alone exceeds {target} chars after dropping all "
            "optional guidance — AF-PROMPT-CANNOT-CONDENSE (fail closed, never truncate)")
    return result.strip()


# ─── Token budget ────────────────────────────────────────────────────────────

def token_estimate(final_prompt: str) -> int:
    policy = load_policy()
    est = policy.get("token_budget", {}).get("estimate_chars_per_token", 4)
    return math.ceil(count_chars(final_prompt) / max(1, int(est or 4)))


# ─── Rule 12 band (from the shared enforcer, never from this file) ───────────

def _band(model: str, text: str, vendor_cap) -> dict:
    """The enforcer verdict for `text` on `model`: floor, target_min, max and the add/cut counts."""
    return kie_prompt_enforcer.check(model or _DEFAULT_MODEL, text, "descriptive",
                                     fallback_max=int(vendor_cap) if vendor_cap else None)


def _band_receipt(v: dict) -> dict:
    # source is reduced to its stable class (live-schema / registry / policy-owner) so a receipt is identical
    # whether the adapter answered from the live API or from its cache
    return {"floor": v.get("floor"), "target_min": v.get("target_min"), "max": v.get("max"),
            "status": v.get("status"), "source": (v.get("source") or "").split(":")[0].split(" (")[0],
            "rule": "KIE prompt rule 12"}


def _length_problems(v: dict) -> list:
    return [] if v["ok"] else [f"AF-PROMPT-LENGTH: final prompt: {v['message']}"]


# ─── Deepening bank (rule 12 writer) ─────────────────────────────────────────

def _deepening_bank(brief: dict) -> list:
    """Second-level render decisions, each a DIFFERENT decision the renderer can use, derived from the
    brief's own fields. Appended only while the final prompt sits below the target the shared enforcer
    reports (95 percent of the model maxLength). Never repeats a sentence of the first-level bank."""
    dest = _dest(brief)
    audience = brief.get("audience") or "the client's intended audience"
    focal = (brief.get("composition") or {}).get("focal_message") or brief.get("theme") or "the campaign's single focal message"
    palette = _palette_text(brief)
    keep_in = (brief.get("safe_areas") or {}).get("keep_in", "the central 80%")
    ratio = (brief.get("composition") or {}).get("ratio") or dest["ratio"]
    on_image = (brief.get("copy") or {}).get("on_image_text") or ""
    text_note = ("The exact words are rendered as one deliberate typographic unit: a clear dominant line, a quieter support line "
                 "if one exists, equal optical margins, and a baseline grid so nothing drifts or tilts by accident."
                 if on_image else
                 "With no copy declared, the image stays wordless: any sign, label, screen or page in the scene is blurred "
                 "or abstracted so no stray letterform can be mistaken for approved text.")
    return [
        (f"Narrative moment decision: the frame captures one believable instant that already implies what happened before it and "
         f"what follows, so that {focal} reads as a story and not a poster. The subject is caught mid-purpose rather than posed "
         f"at the camera, and the viewer, who is {audience}, can place themselves inside the moment within the first half second."),
        ("Depth layering decision: the foreground carries a small, softly defocused cue that frames the subject, the midground holds "
         "the subject and every critical detail in full sharpness, and the background simplifies into two or three large shapes "
         "of tone and color. Each layer has its own value range, which keeps the image legible when it is shrunk to a thumbnail."),
        (f"Color relationship decision: the verified palette ({palette}) is arranged so the strongest contrast sits exactly where the "
         "eye should land, mid-tones carry the supporting forms, and the darkest dark is reserved for a single anchor. Skin, wood, "
         "metal and fabric keep their natural hue shifts, so brand color shows through accents and environment instead of tinting people."),
        ("Human detail decision: when people appear, faces show natural asymmetry, believable pores and fine lines, eyes that share "
         "one focal point, teeth that look like teeth, and hair that has individual strands with a plausible hairline. Hands show "
         "correct knuckle structure, nails and relaxed tension. Every body part keeps true scale relative to the others."),
        ("Object fidelity decision: any product, tool or prop is drawn with the proportions, seams, hinges, labels and wear that a real "
         "item of that kind has. Packaging faces the viewer at its most flattering honest angle, reflections follow the surface "
         "curvature, and nothing is shown doing something the real object cannot physically do."),
        (f"Typography rendering decision: {text_note} Letterforms keep consistent stroke contrast, and counters stay open so small "
         "sizes remain readable on a phone in sunlight."),
        (f"Negative space decision: empty areas are planned, not leftover. They give the eye a place to rest, hold the safe margin "
         f"inside {keep_in}, and leave a quiet region that a platform caption or button can cover on a {ratio} crop without hiding "
         "anything the message depends on. The balance between filled and empty areas feels deliberate from corner to corner."),
        ("Micro-texture decision: fine surface detail matches the viewing distance. Fabric shows weave only where the camera is "
         "close, wood shows grain direction that follows the object's shape, glass shows a hint of dust or a clean edge highlight, "
         "and skin keeps subtle sheen. Texture never turns into noise, and it never smooths away into plastic."),
        ("Atmosphere decision: air has weight in the frame. Distant elements lose a little contrast and shift slightly cooler, "
         "close elements stay crisp and warm, and any haze, steam, dust or light shafts are present only when the declared scene "
         "would plausibly produce them. The time of day stays consistent between sky, shadows and interior light."),
        (f"Representation decision: people shown are depicted with dignity and specificity, reflecting the real makeup of {audience} "
         "as stated in the brief, never a stereotype and never a default demographic mix invented by the renderer. Skin tones keep "
         "their true depth and warmth under the chosen lighting, and clothing, setting and gesture respect the context of the brand."),
        ("Motion and stillness decision: if movement is implied, it shows as a believable direction of travel, a slight lean, trailing "
         "fabric or a settling of dust, and the rest of the frame stays calm so the movement is the only dynamic element. Frozen "
         "motion looks like a fast shutter, not like a cut-out pasted onto a background."),
        (f"Series cohesion decision: this image sits beside its siblings in the {dest['platform']} grid and carousel, so crop "
         "anchor, horizon height, subject scale and color grade repeat across the set while the subject and the moment change. A "
         "viewer scrolling past three images should recognize one brand voice before reading a single word."),
        ("Compression resilience decision: gradients are wide and smooth enough to survive platform recompression without banding, "
         "fine diagonal patterns are avoided because they shimmer, and every critical edge keeps at least a few pixels of contrast "
         "so it holds after the image is resized for different devices and for the feed preview."),
        (f"Platform convention decision: the composition respects how {dest['platform']} displays content, with the key subject "
         "away from the corners where rounding and badges appear, the focal point near the upper third where thumbs rarely cover, "
         "and a clean edge treatment that does not fight the interface chrome that frames the image on the viewer's screen."),
        ("Accessibility decision: contrast between essential elements and their backgrounds stays high enough to read for people with "
         "reduced vision, color is never the only carrier of meaning, and the scene description a screen reader would give is "
         "obvious from the image itself: one subject, one action, one setting, one message."),
        ("Eye path decision: the viewer's gaze is guided along a clear route, entering at a strong leading line or gesture, "
         "traveling across the subject and landing on the key detail before leaving toward the supporting element. Lines of "
         "sight inside the scene point inward, never off the frame, so attention stays with the message instead of escaping."),
        ("Wardrobe and styling decision: clothing, accessories and surfaces are chosen to suit the audience's real world, with "
         "believable fit, natural creasing, tidy but lived-in details and no anachronisms. Colors in styling support the palette "
         "without matching it so exactly that the subject disappears into the background."),
        ("Surface response decision: reflective and translucent materials show what is actually around them, so a window shows a "
         "plausible street, a polished table shows a soft inverted hint of the objects on it, and a screen shows a simple, "
         "generic interface with no readable brand names or invented logos."),
        ("Edge quality decision: outlines are clean without a cut-out halo, hair and fabric edges blend into the background with "
         "natural transparency, and overlapping shapes show believable contact shadows where they touch, so every element feels "
         "physically present in the same space rather than layered in after the fact."),
        ("Season and context decision: weather, foliage, clothing weight and light quality all agree with the season implied by the "
         "campaign, and incidental background details stay neutral, so the image does not date quickly and does not conflict with "
         "the offer, the holiday or the region the post is aimed at."),
        ("Optics decision: the virtual lens behaves like a real one, with gentle natural vignetting, no oversharpened halos, "
         "no chromatic fringing on high-contrast edges, controlled highlights that keep detail in bright areas, and shadows "
         "that keep a little texture instead of collapsing into flat black."),
        ("Scale and proportion decision: relative sizes follow the real world, so a hand fits the cup it holds, a doorway fits "
         "the person walking through it, and a product sits at the size a customer would recognize. Where the composition "
         "needs emphasis, it comes from framing and distance, never from distorting an object past what is believable."),
        ("Emphasis hierarchy decision: exactly one element receives the strongest saturation, one receives the sharpest "
         "focus, and one receives the largest scale, and these three advantages belong to the same element wherever possible. "
         "Competing highlights elsewhere are toned down until they support the message instead of contesting it."),
        ("Environmental honesty decision: the place shown is a place the audience could actually visit or use, with believable "
         "clutter levels, wear that suits its age, and fixtures in their usual positions, so the offer feels attainable and "
         "trustworthy rather than staged for a catalog."),
        ("Light quality decision: the key light has a clear size and distance, producing shadow edges that are soft where the "
         "source is large and crisp only where the scene demands it, with a gentle bounce from nearby surfaces filling the "
         "darkest areas so that detail remains visible in every part of the subject."),
        (f"Final self-review decision: before the render is accepted, the frame is read three ways, at full size for detail, at "
         f"thumbnail size for the single dominant read, and in grayscale for value structure. Any failure on {focal}, on exact "
         "spelling, on mark fidelity or on the declared exclusions sends the prompt back for revision with the same full instruction "
         "set instead of a shortened one."),
    ]


def deepen(text: str, brief: dict, target: int) -> str:
    """One rewrite pass for the rule 12 writer loop: append unused deepening blocks until the text reaches
    `target` characters or the bank is exhausted. Genuine render decisions only, never repeated filler."""
    out = text
    for block in _deepening_bank(brief):
        if count_chars(out) >= target:
            break
        if block not in out:
            out += "\n" + block
    return out


# ─── Compile + validate (the full contract) ─────────────────────────────────

def compile_prompt(brief: dict, provider: str, model: str,
                   negative_block: str = "",
                   policy_path: str = _POLICY_PATH) -> dict:
    """Compile a brief to a final in-band prompt and validate the FINAL payload.

    Order (policy validation_order):
      1. expand sections, 2. append per-reference instructions + negatives,
      3. count/hash the final payload, 4. reject padding/contradictions/
      out-of-band BEFORE spend, 5. token budget so limits cannot silently
      truncate (condense to fit, never truncate mid-content).
    Length: rule 12 through the shared enforcer. A prompt below the 95 percent target is
    rewritten (deepen) up to 3 times; one still below the 80 percent floor, or above the
    model max, is rejected with the exact characters to add or cut.

    Returns a receipt dict:
      {ok, final_prompt, count, hash, policy_version, provider, model,
       capability_source, token_estimate, problems[], vendor_cap,
       vendor_cap_source, band}
    """
    policy = load_policy(policy_path)
    prov = policy.get("providers", {}).get(f"{provider}-{model.split('/')[-1]}") or \
        policy.get("providers", {}).get(f"{provider}-gpt-image-2-5") or \
        policy.get("providers", {}).get("agnes-image-2.1-flash")
    vendor_cap = (prov or {}).get("vendor_cap_chars")
    vendor_cap_source = (prov or {}).get("vendor_cap_source")
    capability_source = (prov or {}).get("cap_status") or (
        "published schema" if vendor_cap else "unknown")

    problems: list = []
    problems.extend(find_contradictions(brief))
    if problems:
        return _fail(problems, policy, provider, model, vendor_cap, vendor_cap_source, {})

    refs_blocks = reference_instruction_blocks(brief)
    # the band for this model (the empty probe returns floor, target_min and max)
    v0 = _band(model, "", vendor_cap)
    target = v0.get("target_min")
    base = expand_sections(brief, target)
    for blk in refs_blocks:
        base += "\n" + blk
    if negative_block:
        base += "\nNegative constraints: " + negative_block.strip()

    final = unicodedata.normalize("NFC", base).strip()

    # Rule 12 writer loop: deepen up to 3 times while below the target. Genuine render decisions only.
    if target:
        for _ in range(kie_prompt_enforcer.TRIES):
            if count_chars(final) >= target:
                break
            final = deepen(final, brief, target).strip()

    # Condense an overlong prompt to the model max without losing required meaning; never truncate silently.
    limit = v0.get("max") or (int(vendor_cap) if vendor_cap else None)
    if limit and count_chars(final) > int(limit):
        try:
            final = condense(final, int(limit))
        except OverflowError as e:
            return _fail([f"AF-PROMPT-CANNOT-CONDENSE: {e}"], policy, provider,
                         model, vendor_cap, vendor_cap_source, v0)

    count = count_chars(final)
    v = _band(model, final, vendor_cap)
    problems.extend(_length_problems(v))
    problems.extend(find_padding(final))

    return {
        "ok": not problems,
        "final_prompt": final,
        "count": count,
        "hash": sha256_of(final),
        "policy_version": policy.get("policy_version", "0"),
        "provider": provider,
        "model": model,
        "capability_source": capability_source,
        "vendor_cap_chars": vendor_cap,
        "vendor_cap_source": vendor_cap_source,
        "token_estimate": token_estimate(final),
        "band": _band_receipt(v),
        "problems": problems,
    }


def validate_final(final_prompt: str, provider: str = "", model: str = "",
                   policy_path: str = _POLICY_PATH) -> dict:
    """Validate an ALREADY-ASSEMBLED final payload (post references + negatives)
    against rule 12 (shared enforcer), padding and hash-recording rules. Returns the
    same receipt shape as compile_prompt (without brief-derived fields)."""
    policy = load_policy(policy_path)
    kie = policy.get("providers", {}).get("kie-gpt-image-2-5", {})
    model = model or kie.get("model_id") or _DEFAULT_MODEL
    count = count_chars(final_prompt)
    v = _band(model, unicodedata.normalize("NFC", final_prompt).strip(), kie.get("vendor_cap_chars"))
    problems = _length_problems(v)
    problems.extend(find_padding(final_prompt))
    return {
        "ok": not problems,
        "final_prompt": unicodedata.normalize("NFC", final_prompt).strip(),
        "count": count,
        "hash": sha256_of(final_prompt),
        "policy_version": policy.get("policy_version", "0"),
        "provider": provider,
        "model": model,
        "token_estimate": token_estimate(final_prompt),
        "band": _band_receipt(v),
        "problems": problems,
    }


def _fail(problems, policy, provider, model, vendor_cap, vendor_cap_source,
          v) -> dict:
    return {
        "ok": False,
        "final_prompt": "",
        "count": 0,
        "hash": "",
        "policy_version": policy.get("policy_version", "0"),
        "provider": provider,
        "model": model,
        "capability_source": "unknown",
        "vendor_cap_chars": vendor_cap,
        "vendor_cap_source": vendor_cap_source,
        "token_estimate": 0,
        "band": _band_receipt(v) if v else {},
        "problems": problems,
    }


if __name__ == "__main__":  # pragma: no cover — small CLI for manual runs
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        ok = 0
        r = compile_prompt({"audience": "test"}, "kie", _DEFAULT_MODEL)
        ok += 0 if r["ok"] and 19000 <= r["count"] <= 20000 else 1
        for n, want in ((15800, False), (19000, True), (20000, True), (20200, False)):
            ok += 0 if validate_final("x" * n)["ok"] == want else 1
        print("self-test:", "PASS" if ok == 0 else f"FAIL({ok})")
        sys.exit(0 if ok == 0 else 2)
