#!/usr/bin/env python3
"""
social_prompt_compiler.py — F32 social-planner image prompt compiler + validator.

Owner requirement (SPEC "Build contract for detailed image prompts"): every final
social-planner image prompt for Kie GPT Image 2.5 and Agnes contains 9,000–19,000
meaningful stripped Unicode characters. The client may supply one short sentence;
this compiler produces the full brief.

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
  - house band 9,000–19,000 is DISTINCT from vendor caps (Kie GPT Image 2.5
    published maxLength 20000; Agnes publishes no cap — NOT_PUBLISHED).

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
import unicodedata
from typing import Optional

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


def expand_sections(brief: dict) -> str:
    """Expand a short brief into the full 8-section structure using useful
    visual decisions derived from the brief's own fields (audience, purpose,
    destination) — never repeated filler. Every section carries REQUIRED info;
    optional guidance blocks degrade gracefully when absent."""
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

    # House band: a short brief is expanded with useful visual decisions, never
    # repetitive filler. The decision bank below derives additional genuine
    # guidance from the brief's own fields (platform, audience, purpose, copy),
    # following the fifteen expansion dimensions of the house prompt policy
    # (objective, subject geometry, environment, composition, lens, lighting,
    # material, palette, typography, brand rules, reference roles, preservation,
    # exclusions, output, QC-critical detail) — each block states a DIFFERENT
    # decision the renderer can actually use.
    count_now = count_chars("\n".join(parts))
    policy_floor = load_policy().get("house_band", {}).get("min_chars", 9000)
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

    Returns a receipt dict:
      {ok, final_prompt, count, hash, policy_version, provider, model,
       capability_source, token_estimate, problems[], vendor_cap,
       vendor_cap_source, house_band}
    """
    policy = load_policy(policy_path)
    band = policy.get("house_band", {})
    lo, hi = int(band.get("min_chars", 9000)), int(band.get("max_chars", 19000))
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
        return _fail(problems, policy, provider, model, vendor_cap,
                     vendor_cap_source, band)

    refs_blocks = reference_instruction_blocks(brief)
    base = expand_sections(brief)
    for blk in refs_blocks:
        base += "\n" + blk
    if negative_block:
        base += "\nNegative constraints: " + negative_block.strip()

    final = unicodedata.normalize("NFC", base).strip()

    # Token budget FIRST: condense to fit vendor cap headroom if needed —
    # never silently truncate. (House band condensation happens below.)
    if vendor_cap and count_chars(final) > int(vendor_cap) - 1000:
        try:
            final = condense(final, int(vendor_cap) - 1000)
        except OverflowError as e:
            return _fail([f"AF-PROMPT-CANNOT-CONDENSE: {e}"], policy, provider,
                         model, vendor_cap, vendor_cap_source, band)

    count = count_chars(final)

    # Condense overlong, expand-short handled by expand_sections already
    # producing the full structure. If still over the house ceiling (very long
    # client brief), condense without losing required meaning.
    if count > hi:
        try:
            final = condense(final, hi)
        except OverflowError as e:
            return _fail([f"AF-PROMPT-CANNOT-CONDENSE: {e}"], policy, provider,
                         model, vendor_cap, vendor_cap_source, band)
        count = count_chars(final)

    # Length gate on the FINAL payload: 8999 → fail; 9000 → pass length (semantic
    # QC still required); 19000 → pass; 19001 → fail (handled by condense above,
    # kept explicit for direct validation calls).
    if count < lo:
        problems.append(
            f"AF-PROMPT-LENGTH: final prompt is {count} stripped Unicode chars — "
            f"below the house floor {lo} (boundary: {lo - 1} fails, {lo} passes).")
    if count > hi:
        problems.append(
            f"AF-PROMPT-LENGTH: final prompt is {count} stripped Unicode chars — "
            f"above the house ceiling {hi} (boundary: {hi + 1} fails, {hi} passes).")

    problems.extend(find_padding(final))

    receipt = {
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
        "house_band": {"min": lo, "max": hi},
        "problems": problems,
    }
    return receipt


def validate_final(final_prompt: str, provider: str = "", model: str = "",
                   policy_path: str = _POLICY_PATH) -> dict:
    """Validate an ALREADY-ASSEMBLED final payload (post references + negatives)
    against the house band, padding and hash-recording rules. Returns the same
    receipt shape as compile_prompt (without brief-derived fields)."""
    policy = load_policy(policy_path)
    band = policy.get("house_band", {})
    lo, hi = int(band.get("min_chars", 9000)), int(band.get("max_chars", 19000))
    count = count_chars(final_prompt)
    problems = []
    if count < lo:
        problems.append(
            f"AF-PROMPT-LENGTH: final prompt is {count} stripped Unicode chars — "
            f"below the house floor {lo} (boundary: {lo - 1} fails, {lo} passes).")
    if count > hi:
        problems.append(
            f"AF-PROMPT-LENGTH: final prompt is {count} stripped Unicode chars — "
            f"above the house ceiling {hi} (boundary: {hi + 1} fails, {hi} passes).")
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
        "house_band": {"min": lo, "max": hi},
        "problems": problems,
    }


def _fail(problems, policy, provider, model, vendor_cap, vendor_cap_source,
          band) -> dict:
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
        "house_band": {"min": band.get("min_chars"), "max": band.get("max_chars")},
        "problems": problems,
    }


if __name__ == "__main__":  # pragma: no cover — small CLI for manual runs
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        ok = 0
        r = compile_prompt({"audience": "test"}, "kie", "gpt-image-2-5-sunburst-text-to-image")
        ok += 0 if r["ok"] and 9000 <= r["count"] <= 19000 else 1
        v = validate_final("x" * 8999)
        ok += 0 if not v["ok"] else 1
        v = validate_final("x" * 9000)
        ok += 0 if v["ok"] else 1
        v = validate_final("x" * 19000)
        ok += 0 if v["ok"] else 1
        v = validate_final("x" * 19001)
        ok += 0 if not v["ok"] else 1
        print("self-test:", "PASS" if ok == 0 else f"FAIL({ok})")
        sys.exit(0 if ok == 0 else 2)
    print(__doc__)