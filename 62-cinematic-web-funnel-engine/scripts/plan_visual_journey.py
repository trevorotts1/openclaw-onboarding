#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan_visual_journey.py — the visual-journey / scene planner (Skill 62, U10).

Implements spec Section 9 ("Visual Journey and Scene Architecture"): reads the
LOCKED `content-manifest.json` a content methodology already produced (U8,
P3-CONTENT — ADR-10: this engine never authors copy itself, it only consumes
the locked manifest's `section_order` / `page_profiles` / `cta_map` /
`claims`) and deterministically emits `journey/scene-plan.json` — spec 9.2's
scene proposal artifact — schema-validated against `structure/scene-plan.
schema.json` (U6) on every write via `state_engine.ProjectState.save()`.

This module is a PRODUCER, not a phase gate. CWFE-MANIFEST.json already wires
P4-JOURNEY's gate to `scripts/prove_budget.py:evaluate_forecast` (built in
U7) — exactly the same producer/gate split `intake_engine.py` (producer) has
from `prove_intake.py` (gate) and, before it, the way U6's schemas are
separate from U7's budget logic. This module's job ends at writing a
schema-valid `scene-plan.json`; whether that plan's forecast actually PASSES
the live model registry's pricing is prove_budget.py's call, not this
module's — `check_budget_forecast()` below calls straight into
`prove_budget.evaluate_forecast()` to prove that reuse rather than
re-implementing any pricing/forecast logic here (ADR-8: model slugs and
prices resolve from the live registry, never a hardcoded number, and the ONLY
sanctioned resolver is `providers/base.py:ModelRegistry` / `estimate_cost.py`
built in U4/U7).

Determinism: every field on every scene is a pure function of
(content-manifest's locked fields, the chosen architecture, the chosen
generation_tier, the live model-registry snapshot). No randomness, no wall-
clock-dependent branching (only `created_at`/`updated_at` carry the current
time, exactly as every other manifest kind in this skill does).

Model selection deliberately does NOT require a verified/priced candidate
(`require_priced=False`) — picking the semantically-correct model for a
scene's generation_tier is this planner's job; requiring that model's price
be VERIFIED before any paid call is `prove_budget.evaluate_paid_call_
preconditions`'s job (AF-CWFE-PAID-GATE), not this one's. A scene plan that
targets a currently-unpriced model (e.g. `kie-bytedance-seedance-1.5-pro`,
whose Kie.ai doc page states pricing is not listed as of this snapshot)
correctly, deliberately fails `prove_budget.evaluate_forecast` until Kie
publishes a verified price or the plan is rebuilt against a verified tier
(`premium-override`) — this is fail-closed behavior working as designed,
mirroring prove_budget.py's own documented Seedance case, not a defect in
this module.

stdlib only. Phase-gate-style CLI convention (exit 0 = PASS / 2 = FAIL / 3 =
usage error) even though this script is not itself a manifest-declared gate,
for consistency with every other script in this skill.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

import estimate_cost as ec  # noqa: E402
import resolve_content_engine as rce  # noqa: E402
import state_engine as se  # noqa: E402
from providers import base as providers_base  # noqa: E402

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

# scene-plan.schema.json architecture enum (spec 9.1 A/B/C).
_ALLOWED_ARCHITECTURES = ("continuous-forward-journey", "scene-dives-plus-connectors", "hybrid")

# scene-plan.schema.json generation_tier enum, mapped onto
# providers/model-registry.json's capability_tiers (spec 10.2). This mapping
# is the ONLY place a generation_tier string is associated with a capability
# tier name — never duplicated elsewhere.
_TIER_TO_CAPABILITY: Dict[str, str] = {
    "concept": "concept_image",
    "production-anchor": "production_scene_image",
    "draft-motion": "draft_motion",
    "final-motion": "final_connected_motion",
    "premium-override": "premium_photoreal_override",
}
_ALLOWED_TIERS = tuple(_TIER_TO_CAPABILITY.keys())

_CROP_RULES = {"desktop": "16:9 full-bleed", "mobile": "9:16 crop-safe"}
_DEFAULT_TARGET_DURATION = 8.0
_DEFAULT_CHAPTER_SIZE = 3


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


class PlanVisualJourneyError(Exception):
    """Base class for every error this module raises. A caller (the CLI, or
    a later orchestrator-integration unit) always turns this into a (False,
    detail) pair rather than an uncaught traceback."""


# ---------------------------------------------------------------------------
# Section narrative/camera library (spec 9.2's per-scene narrative_purpose /
# conversion_purpose / visual_motif / camera fields). Deterministic lookup by
# lowercased section name; any section name not in this table still resolves
# through _fallback_section_profile() below rather than raising, so an
# operator-supplied custom section_order never breaks the planner.
# ---------------------------------------------------------------------------
_SECTION_LIBRARY: Dict[str, Dict[str, str]] = {
    "hero": {
        "narrative_purpose": "establish the world and the promise in the first three seconds",
        "conversion_purpose": "hook attention and earn the scroll",
        "visual_motif": "wide establishing shot of the subject in its native environment",
        "start_state": "wide", "end_state": "medium", "motion_direction": "push-in", "motion_speed": "slow",
    },
    "problem": {
        "narrative_purpose": "surface the pain the audience already feels",
        "conversion_purpose": "create urgency and self-recognition",
        "visual_motif": "tighter, tenser framing on the friction point",
        "start_state": "medium", "end_state": "close", "motion_direction": "push-in", "motion_speed": "medium",
    },
    "solution": {
        "narrative_purpose": "introduce the mechanism that resolves the problem",
        "conversion_purpose": "build belief the offer actually works",
        "visual_motif": "reveal shot of the product/system in motion",
        "start_state": "close", "end_state": "medium", "motion_direction": "pull-back-reveal", "motion_speed": "medium",
    },
    "offer": {
        "narrative_purpose": "lay out exactly what is being offered",
        "conversion_purpose": "make the offer concrete and desirable",
        "visual_motif": "clean offer composition with breathing room for overlay copy",
        "start_state": "medium", "end_state": "medium", "motion_direction": "lateral-drift", "motion_speed": "slow",
    },
    "proof": {
        "narrative_purpose": "demonstrate the promise is real",
        "conversion_purpose": "neutralize skepticism with evidence",
        "visual_motif": "documentary-style proof composition (results, testimonial subject, or data)",
        "start_state": "medium", "end_state": "close", "motion_direction": "push-in", "motion_speed": "slow",
    },
    "testimonial": {
        "narrative_purpose": "let a real voice vouch for the outcome",
        "conversion_purpose": "transfer trust from a third party",
        "visual_motif": "intimate portrait-style framing",
        "start_state": "medium", "end_state": "close", "motion_direction": "push-in", "motion_speed": "slow",
    },
    "pricing": {
        "narrative_purpose": "frame the investment against the value already established",
        "conversion_purpose": "remove price friction",
        "visual_motif": "clean, calm composition — no visual noise competing with the numbers",
        "start_state": "medium", "end_state": "medium", "motion_direction": "static-drift", "motion_speed": "slow",
    },
    "guarantee": {
        "narrative_purpose": "remove risk from the decision",
        "conversion_purpose": "lower the perceived cost of saying yes",
        "visual_motif": "reassuring, warm, stable composition",
        "start_state": "medium", "end_state": "medium", "motion_direction": "static-drift", "motion_speed": "slow",
    },
    "faq": {
        "narrative_purpose": "answer the objections still standing between interest and action",
        "conversion_purpose": "clear the last hesitations",
        "visual_motif": "orderly, calm, low-motion composition",
        "start_state": "medium", "end_state": "medium", "motion_direction": "static-drift", "motion_speed": "slow",
    },
    "urgency": {
        "narrative_purpose": "make the cost of waiting visible",
        "conversion_purpose": "compress the decision timeline",
        "visual_motif": "tighter, faster-feeling composition",
        "start_state": "medium", "end_state": "close", "motion_direction": "push-in", "motion_speed": "fast",
    },
    "cta": {
        "narrative_purpose": "arrive at the moment of decision",
        "conversion_purpose": "convert — the primary conversion action lives in this scene",
        "visual_motif": "clean, focused composition around the call to action",
        "start_state": "medium", "end_state": "close", "motion_direction": "push-in", "motion_speed": "medium",
    },
    "close": {
        "narrative_purpose": "leave the visitor with a final, memorable impression",
        "conversion_purpose": "reinforce the decision already made",
        "visual_motif": "wide, resolving composition that mirrors the hero's world",
        "start_state": "close", "end_state": "wide", "motion_direction": "pull-back-reveal", "motion_speed": "slow",
    },
    "footer": {
        "narrative_purpose": "provide a calm, trustworthy landing point after the call to action",
        "conversion_purpose": "reinforce legitimacy (trust marks, contact, legal)",
        "visual_motif": "static, low-motion, brand-mark composition",
        "start_state": "wide", "end_state": "wide", "motion_direction": "static-drift", "motion_speed": "slow",
    },
}


# Scene-specific production direction per section type (scene-plan.production_direction). The prompt builder
# (providers/prompt_depth.py) expands these fields per scene, so each scene's long prompt is carried by what
# is true of THAT scene and the shared house rules are the minority. World-neutral on purpose: the project's
# own world comes from the style contract. An operator or agent may replace any scene's direction.
_SECTION_DIRECTION: Dict[str, Dict[str, str]] = {
    "hero": {
        "subject": "the hero subject of the project seen whole, large enough to read at a glance and framed with generous space around it",
        "setting": "its native environment, wide enough to show the scale and character of the place and what surrounds it",
        "time_of_day": "the best light of the day, shortly after sunrise or shortly before sunset, when the air is clear and the light is long",
        "light": "a low, warm key light raking across the subject from one side with long soft shadows and a gentle cool fill from the open sky",
        "materials": "the primary surfaces of the subject and its surroundings, shown with honest wear, edge detail and a believable sheen",
        "motion": "almost nothing moves except slow ambient life in the distance and the camera itself drifting forward",
        "camera_blocking": "the camera starts wide and level, then pushes in on a straight line toward the subject without any lateral wobble",
        "mood": "calm confidence and quiet anticipation, the feeling of arriving somewhere worth the trip",
        "continuity": "nothing precedes this scene, so it fixes the look every later scene must keep: the palette, the light direction and the proportions of the subject"
    },
    "problem": {
        "subject": "the point of friction, a specific object or situation that shows the audience's pain in concrete form",
        "setting": "the same world as the hero scene, but at its least comfortable: cramped framing, cluttered or neglected surroundings",
        "time_of_day": "flat, late-day light when energy is low and the day has gone slightly wrong",
        "light": "a harder, more directional key with deeper shadows and a cooler tint, so the frame feels tight and tense without becoming dark",
        "materials": "worn, strained or overloaded surfaces, with visible evidence of the problem such as scuffs, tangles, stains or overflow",
        "motion": "small repeating motions that show the problem in action, such as a hand retrying something or a loose part shifting",
        "camera_blocking": "the camera moves from medium to close on the friction point, slightly faster than in the hero scene, with a tiny handheld-like settle at the end",
        "mood": "recognition and mild discomfort, the feeling of 'that is exactly my situation'",
        "continuity": "carry over the hero scene's world, palette and proportions, but show it under strain; the subject's identity must stay unmistakable"
    },
    "solution": {
        "subject": "the product, system or method that resolves the problem, revealed working as intended",
        "setting": "the same world as the problem scene, now orderly, open and arranged around the solution",
        "time_of_day": "clear mid-morning light that feels fresh and decisive",
        "light": "a clean, soft key from above and to one side with open shadows and a bright, even fill, as if the weather had cleared",
        "materials": "crisp, well-finished surfaces on the solution, with polished edges, clean joints and a quality of manufacture you can feel",
        "motion": "the solution doing its job in one smooth, legible motion, with everything else holding still so the cause and effect are obvious",
        "camera_blocking": "the camera starts close on the old friction point, then pulls back and sideways to reveal the solution in context",
        "mood": "relief and clarity, the moment the knot comes undone",
        "continuity": "the same world and subject as the problem scene, visibly improved; keep the palette and light direction, but raise brightness and order"
    },
    "offer": {
        "subject": "the offer made tangible, a small, clear arrangement of what the customer receives, laid out with intention",
        "setting": "a calm, uncluttered stage with generous empty space around the offer where overlay copy can sit",
        "time_of_day": "steady, neutral daylight with no dramatic time cue, so nothing competes with the offer",
        "light": "a broad, soft, shadow-light key that shows every item clearly, with gentle gradient falloff toward the edges of the frame",
        "materials": "premium, tactile surfaces on each item in the offer, with consistent finishing so they read as one family",
        "motion": "a slow lateral drift across the arrangement, items fixed in place, with one subtle ambient movement in the background",
        "camera_blocking": "the camera drifts sideways at constant height and speed, keeping the arrangement centred in the safe region the whole time",
        "mood": "generous and orderly, an invitation that feels easy to accept",
        "continuity": "reuse the solution scene's materials and light so the offer feels like its natural continuation; keep the empty space stable for copy"
    },
    "proof": {
        "subject": "the evidence that the promise is real, shown as a concrete result, a documented outcome or a real person in context",
        "setting": "a believable working environment where the result happened, not a staged studio",
        "time_of_day": "plain, honest daylight, the look of documentation rather than advertising",
        "light": "natural, slightly diffuse light with believable contrast, close to what a documentary camera would capture without extra rigging",
        "materials": "real-world textures and honest imperfections that make the evidence credible, including small signs of use",
        "motion": "a small, natural action that confirms the result, such as a hand checking a measurement or a person glancing at the outcome",
        "camera_blocking": "the camera moves from medium to close on the evidence with a slow, steady push and settles on the most telling detail",
        "mood": "grounded trust, calm and unexaggerated, the feeling of seeing it with your own eyes",
        "continuity": "stay in the same world as the offer scene but at ground level and in more natural light; keep the subject's finish consistent"
    },
    "testimonial": {
        "subject": "one real-feeling person, shown in an intimate portrait as they speak or reflect about the outcome",
        "setting": "a quiet, personal space that belongs to them, softly out of focus behind the face",
        "time_of_day": "soft late-morning light, unhurried and private",
        "light": "a large soft key from one side at eye level, a faint fill, and a subtle edge light separating the person from the background",
        "materials": "natural skin, fabric and the textures of a lived-in space, none of it glossy or retouched flat",
        "motion": "small, human motions, a breath, a blink, a slight turn of the head, a hand settling, nothing theatrical",
        "camera_blocking": "the camera moves from medium to close very slowly, ending on the eyes and the beginning of an expression",
        "mood": "warmth, sincerity and quiet pride",
        "continuity": "keep the world's palette and the overall lens look, but allow the lighting to become softer and more intimate than in earlier scenes"
    },
    "pricing": {
        "subject": "a clean, simple object or arrangement that stands in for value, with nothing in the frame that suggests cost or clutter",
        "setting": "an open, almost empty space with a plain background and a single calm focal point",
        "time_of_day": "even, shadowless midday light that feels neutral and fair",
        "light": "soft, wide, even illumination with very gentle shadows so that numbers laid over the frame stay perfectly legible",
        "materials": "smooth, matte, low-reflectance surfaces with no sparkle or busy pattern that could fight the typography",
        "motion": "a nearly static frame with a slow, almost imperceptible drift and a faint breath of ambient movement",
        "camera_blocking": "the camera holds almost still and drifts a few centimetres at constant speed, never changing framing noticeably",
        "mood": "clarity and fairness, the feeling of nothing hidden",
        "continuity": "keep the offer scene's materials and palette, simplified; reduce detail density rather than changing style"
    },
    "guarantee": {
        "subject": "a steady, protective subject such as a sturdy object, a closed hand or a sheltering structure that signals safety",
        "setting": "a warm, secure space with solid walls or horizon lines and nothing precarious in view",
        "time_of_day": "warm late-afternoon light that feels settled and kind",
        "light": "a golden, enveloping key with soft shadows and a warm bounce, giving the whole frame a sense of shelter",
        "materials": "solid, weighty textures such as wood grain, stone, heavy fabric or brushed metal that suggest durability",
        "motion": "almost none, a single slow settling movement such as dust drifting or a light shifting gently across a surface",
        "camera_blocking": "the camera sits low and stable, then glides forward very slowly without any tilt",
        "mood": "reassurance and trust, the feeling of being looked after",
        "continuity": "continue the warm light direction of the proof scene and keep the subject's finish identical"
    },
    "faq": {
        "subject": "an orderly arrangement of a few distinct objects, each clearly separated, that suggest questions answered one by one",
        "setting": "a tidy, well-organised space with clear spacing and a simple background",
        "time_of_day": "calm daylight that does not draw attention to the time",
        "light": "even, neutral illumination that lets each object read separately without drama",
        "materials": "clean, simple surfaces with clear edges and consistent finish across the objects",
        "motion": "minimal, a single object quietly changing state while the others stay still",
        "camera_blocking": "the camera makes a very slow, level lateral move along the arrangement, pausing nowhere",
        "mood": "patient, helpful and uncomplicated",
        "continuity": "match the pricing scene's simplified look; keep the arrangement within the central safe region"
    },
    "urgency": {
        "subject": "a clear signal that time is passing, shown through the subject itself rather than through graphics or text",
        "setting": "the same world as the offer scene, but with the light and the shadows already moving along",
        "time_of_day": "the last strong light before the day changes, with shadows lengthening noticeably",
        "light": "a strong low-angle key that is visibly moving or fading, with colour shifting from warm toward cool at the edges",
        "materials": "the same surfaces as the offer scene, now catching the changing light so their highlights slide and shift",
        "motion": "purposeful motion with a little more energy, such as clouds, shadows or people moving across the frame at a steady, faster pace",
        "camera_blocking": "the camera pushes in a little faster than earlier scenes on a straight, confident line",
        "mood": "focus and gentle pressure, never panic",
        "continuity": "same world, subject and palette, with the light direction preserved while its intensity and colour progress"
    },
    "cta": {
        "subject": "the single object or gesture that stands for taking the next step, placed unmistakably at the centre of attention",
        "setting": "a clean, focused space where everything leads toward the one action and nothing else competes for attention",
        "time_of_day": "bright, confident daylight, the clearest moment of the whole journey",
        "light": "a clean key with a subtle halo of brightness around the focal object and calmer, slightly darker surroundings",
        "materials": "the best-finished surface in the whole project, with a crisp edge and a hint of reflection that invites a click",
        "motion": "a small, inviting movement of the focal object or a hand approaching it, with everything else stationary",
        "camera_blocking": "the camera makes a confident, steady push to a close framing of the focal action and stops precisely on it",
        "mood": "decisive, warm and encouraging, the feeling of a door held open",
        "continuity": "reuse the hero's world, light and subject so the end of the journey rhymes with its beginning; keep a clear area for the button"
    },
    "close": {
        "subject": "the hero subject again, now at rest in a resolved, settled pose, as if the journey has arrived",
        "setting": "the opening scene's environment, wide and still, now understood and familiar",
        "time_of_day": "the same time of day as the opening scene, a little later and a little softer",
        "light": "the opening scene's key light direction at a gentler intensity with a golden, quiet fill",
        "materials": "the same surfaces as the hero scene, now glowing with the warmth of the closing light",
        "motion": "a slow exhale of ambient motion, a breeze, drifting light or distant movement, then stillness",
        "camera_blocking": "the camera pulls back and rises slightly, revealing the whole world one last time before holding",
        "mood": "resolution and quiet satisfaction, a closing moment worth remembering",
        "continuity": "mirror the hero scene exactly in framing logic and palette so the end visibly answers the beginning"
    },
    "footer": {
        "subject": "a simple brand mark or a calm, symbolic object that anchors the page without competing with its copy",
        "setting": "a quiet, neutral space with a shallow depth and a plain background",
        "time_of_day": "neutral, timeless light",
        "light": "soft, even and low in contrast so that small text laid over it stays readable",
        "materials": "subtle, matte, low-detail surfaces",
        "motion": "none, a still frame with at most a barely perceptible drift",
        "camera_blocking": "the camera holds still, with no push, pull or tilt",
        "mood": "trustworthy, settled and professional",
        "continuity": "keep the palette and finish of the rest of the project in their quietest form"
    }
}


def _fallback_section_profile(section: str, index: int) -> Dict[str, str]:
    """Deterministic fallback for any section name not in _SECTION_LIBRARY —
    a pure function of (section, index) so an operator-supplied custom
    section_order always produces valid, non-empty schema fields without
    fabricating a specific factual claim about the section's content."""
    even = index % 2 == 0
    return {
        "narrative_purpose": f"advance the story at the '{section}' section",
        "conversion_purpose": f"carry conversion momentum through the '{section}' section",
        "visual_motif": f"a visual motif purpose-built for the '{section}' section, consistent with the approved anchor style contract",
        "start_state": "medium",
        "end_state": "medium" if even else "close",
        "motion_direction": "push-in" if even else "lateral-drift",
        "motion_speed": "slow" if even else "medium",
    }


def _fallback_direction(section: str, index: int) -> Dict[str, str]:
    """Direction for a custom section name: a pure function of (section, index), distinct per section."""
    even = index % 2 == 0
    return {
        "subject": f"the one subject that best expresses the '{section}' section, large and unmistakable in the frame",
        "setting": f"the project's own world, framed so that it explains what the '{section}' section is about",
        "time_of_day": "the project's established moment of the day, held steady" if even else "the same moment of the day, a shade later and softer",
        "light": "one dominant key from a consistent direction with a soft fill" if even else "one dominant key from a consistent direction, slightly lower and warmer than the previous scene",
        "materials": f"the surfaces that belong to the '{section}' subject, finished consistently with the rest of the project",
        "motion": "one slow, motivated movement and otherwise stillness" if even else "a small, natural ambient movement and otherwise stillness",
        "camera_blocking": "a steady push toward the subject on a straight line" if even else "a steady lateral drift past the subject at constant height",
        "mood": f"the feeling this '{section}' section should leave, calm, credible and unforced",
        "continuity": "keep the approved anchor's palette, light direction and subject proportions unchanged",
    }


def _section_direction(section: str, index: int) -> Dict[str, str]:
    return dict(_SECTION_DIRECTION.get(section.strip().lower()) or _fallback_direction(section, index))


def _section_profile(section: str, index: int) -> Dict[str, str]:
    return _SECTION_LIBRARY.get(section.strip().lower()) or _fallback_section_profile(section, index)


def _slugify(section: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", section.strip().lower()).strip("-")
    return slug or "section"


# ---------------------------------------------------------------------------
# Architecture / connector / duration rules (spec 9.1, 9.5)
# ---------------------------------------------------------------------------
def _pick_architecture(project_manifest: Optional[Dict[str, Any]], num_sections: int) -> str:
    """Deterministic default (spec 9.1): `scroll-story-page` deliverables are
    architecture A by definition; short (<=3 section) journeys default to
    continuous motion; longer funnels default to hybrid, which spec 9.1
    itself names 'the most practical default for longer funnels'."""
    deliverable_type = (project_manifest or {}).get("deliverable_type")
    if deliverable_type == "scroll-story-page":
        return "continuous-forward-journey"
    if num_sections <= 3:
        return "continuous-forward-journey"
    return "hybrid"


def _connector_required(architecture: str, index: int, chapter_size: int) -> bool:
    """spec 9.1: architecture A never needs an explicit connector clip (each
    clip continues from the prior clip's actual final frame); architecture B
    needs one at every scene boundary; architecture C (hybrid) needs one only
    at chapter boundaries. The very first scene never has an incoming
    connector regardless of architecture."""
    if index == 0:
        return False
    if architecture == "continuous-forward-journey":
        return False
    if architecture == "scene-dives-plus-connectors":
        return True
    if architecture == "hybrid":
        return index % max(chapter_size, 1) == 0
    raise PlanVisualJourneyError(f"unknown architecture {architecture!r}")


def _pick_duration(model_entry: Dict[str, Any], target: float = _DEFAULT_TARGET_DURATION) -> float:
    limits = model_entry.get("duration_limits")
    if not limits:
        return target
    valid = limits.get("valid_values")
    if valid:
        return float(min(valid, key=lambda v: (abs(v - target), v)))
    lo, hi = limits.get("min"), limits.get("max")
    if lo is not None and target < lo:
        return float(lo)
    if hi is not None and target > hi:
        return float(hi)
    return target


def _expected_generation_count(connector_required: bool) -> int:
    # 1 generation for the scene's own clip; +1 for its connector clip
    # joining from the prior scene's boundary frame (spec 9.5).
    return 2 if connector_required else 1


# ---------------------------------------------------------------------------
# content-manifest-derived fields (never fabricated — every value traces
# back to a field already present in the locked content-manifest.json)
# ---------------------------------------------------------------------------
def _extract_sections(content_manifest: Dict[str, Any]) -> List[str]:
    sections = list(content_manifest.get("section_order") or [])
    if sections:
        return sections
    profiles = content_manifest.get("page_profiles") or []
    if profiles and profiles[0].get("sections"):
        return list(profiles[0]["sections"])
    return []


def _anchor_inputs(content_manifest: Dict[str, Any]) -> List[str]:
    claims = content_manifest.get("claims") or []
    sources = {c.get("truth_source") for c in claims if c.get("truth_source")}
    return sorted(sources)


def _cta_relationship(section: str, cta_map: Dict[str, Any]) -> str:
    if section in cta_map:
        return "primary-cta"
    if section in ("hero", "offer", "pricing"):
        return "supports-conversion"
    return "none"


def _copy_overlay_timing(section: str, cta_map: Dict[str, Any], duration: float) -> List[Dict[str, Any]]:
    if section not in cta_map:
        return []
    return [{"at_seconds": round(duration * 0.6, 2), "cta_key": section, "cta_value": cta_map[section]}]


def _informational_cost_estimate(
    model_entry: Dict[str, Any], duration: float, connector_required: bool, registry: providers_base.ModelRegistry
) -> float:
    """The scene-level estimated_cost_usd field is informational only (spec
    9.2; see prove_budget.py's own docstring: 'a scene's own pre-recorded
    estimated_cost_usd is never trusted as authoritative' — the real forecast
    is always RE-COMPUTED against the live registry by
    prove_budget.evaluate_forecast / estimate_cost.estimate_scene_plan).
    Computed here via estimate_cost.estimate_scene() with strict=False so an
    unverified/unpriced model resolves to a best-effort (possibly 0.0)
    number rather than raising — never re-implements pricing math."""
    scene_stub = {
        "scene_id": "informational-stub",
        "generation_model": model_entry["model_id"],
        "duration_seconds": duration,
        "expected_generation_count": _expected_generation_count(connector_required),
    }
    forecast = ec.estimate_scene(scene_stub, registry, strict=False)
    return forecast.estimated_cost_usd if forecast.estimated_cost_usd is not None else 0.0


def _build_scene(
    section: str,
    index: int,
    *,
    content_manifest: Dict[str, Any],
    model_entry: Dict[str, Any],
    generation_tier: str,
    architecture: str,
    chapter_size: int,
    registry: providers_base.ModelRegistry,
) -> Dict[str, Any]:
    profile = _section_profile(section, index)
    cta_map = content_manifest.get("cta_map") or {}
    connector_required = _connector_required(architecture, index, chapter_size)
    duration = _pick_duration(model_entry)

    return {
        "scene_id": f"scene-{index + 1:02d}-{_slugify(section)}",
        "page_section": section,
        "narrative_purpose": profile["narrative_purpose"],
        "conversion_purpose": profile["conversion_purpose"],
        "visual_motif": profile["visual_motif"],
        "anchor_inputs": _anchor_inputs(content_manifest),
        "camera": {
            "start_state": profile["start_state"],
            "end_state": profile["end_state"],
            "motion_direction": profile["motion_direction"],
            "motion_speed": profile["motion_speed"],
        },
        "duration_seconds": duration,
        "crop_rules": dict(_CROP_RULES),
        "copy_overlay_timing": _copy_overlay_timing(section, cta_map, duration),
        "cta_relationship": _cta_relationship(section, cta_map),
        "generation_model": model_entry["model_id"],
        "generation_tier": generation_tier,
        "connector_required": connector_required,
        "expected_generation_count": _expected_generation_count(connector_required),
        "estimated_cost_usd": _informational_cost_estimate(model_entry, duration, connector_required, registry),
        "approval_status": "proposed",
        "anchor_asset_hash": None,
        "production_direction": _section_direction(section, index),
    }


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------
def build_scene_plan(
    content_manifest: Dict[str, Any],
    project_manifest: Optional[Dict[str, Any]],
    *,
    registry: providers_base.ModelRegistry,
    architecture: Optional[str] = None,
    generation_tier: str = "final-motion",
    chapter_size: int = _DEFAULT_CHAPTER_SIZE,
) -> Dict[str, Any]:
    """Pure function: (locked content-manifest, optional project-manifest,
    live model registry, choices) -> a scene-plan.json-shaped dict. Never
    writes to disk itself — see plan_visual_journey() for the disk-writing,
    schema-validating driver."""
    if generation_tier not in _TIER_TO_CAPABILITY:
        raise PlanVisualJourneyError(
            f"unknown generation_tier {generation_tier!r} (known: {sorted(_TIER_TO_CAPABILITY)})"
        )
    if not content_manifest.get("locked"):
        raise PlanVisualJourneyError(
            "content-manifest.locked is not true — refusing to plan scenes against unlocked/unapproved "
            "copy (ADR-10: content methodology is delegated/locked before this engine ever builds on it)"
        )

    project_id = content_manifest["project_id"]
    if project_manifest is not None and project_manifest.get("project_id") != project_id:
        raise PlanVisualJourneyError(
            f"project-manifest.project_id={project_manifest.get('project_id')!r} does not match "
            f"content-manifest.project_id={project_id!r} — refusing to plan against mismatched artifacts"
        )

    sections = _extract_sections(content_manifest)
    if not sections:
        raise PlanVisualJourneyError(
            "content-manifest has no page sections to plan scenes for (section_order and "
            "page_profiles[0].sections are both empty)"
        )

    architecture_resolved = architecture or _pick_architecture(project_manifest, len(sections))
    if architecture_resolved not in _ALLOWED_ARCHITECTURES:
        raise PlanVisualJourneyError(
            f"unknown architecture {architecture_resolved!r} (known: {_ALLOWED_ARCHITECTURES})"
        )
    if chapter_size < 1:
        raise PlanVisualJourneyError(f"chapter_size must be >= 1 (got {chapter_size})")

    capability_tier = _TIER_TO_CAPABILITY[generation_tier]
    try:
        model_entry = registry.resolve_default(capability_tier, require_priced=False)
    except providers_base.ModelRegistryError as exc:
        raise PlanVisualJourneyError(
            f"model registry could not resolve generation_tier {generation_tier!r} "
            f"(capability_tier {capability_tier!r}): {exc}"
        ) from exc

    scenes = [
        _build_scene(
            section,
            i,
            content_manifest=content_manifest,
            model_entry=model_entry,
            generation_tier=generation_tier,
            architecture=architecture_resolved,
            chapter_size=chapter_size,
            registry=registry,
        )
        for i, section in enumerate(sections)
    ]

    now = _now()
    return {
        "schema_version": "1.0.0",
        "project_id": project_id,
        "architecture": architecture_resolved,
        "scenes": scenes,
        "created_at": now,
        "updated_at": now,
    }


def plan_visual_journey(
    run_dir: Path,
    *,
    architecture: Optional[str] = None,
    generation_tier: str = "final-motion",
    registry_path: Optional[str] = None,
    chapter_size: int = _DEFAULT_CHAPTER_SIZE,
) -> "tuple[bool, str]":
    """The disk-writing driver. Reads content-manifest.json (+ project-
    manifest.json if present) from run_dir via state_engine.ProjectState,
    builds a scene plan, and writes journey/scene-plan.json through
    ProjectState.save() — schema-validated + atomic, the same path every
    other manifest kind in this skill uses. Also writes
    scene-planner-receipt.json documenting the build. Returns (passed,
    detail); never raises for an expected precondition failure (missing/
    unlocked content-manifest, empty sections, unresolvable tier)."""
    state = se.ProjectState(run_dir)

    if not state.exists("content-manifest"):
        return False, (
            "content-manifest.json does not exist yet — P3-CONTENT must run and lock content before "
            "P4-JOURNEY scene planning (spec 9.2 consumes the locked content manifest)"
        )
    try:
        content_manifest = state.load("content-manifest")
    except se.StateEngineError as exc:
        return False, f"content-manifest.json failed to load/validate: {exc}"

    project_manifest: Optional[Dict[str, Any]] = None
    if state.exists("project-manifest"):
        try:
            project_manifest = state.load("project-manifest")
        except se.StateEngineError as exc:
            return False, f"project-manifest.json failed to load/validate: {exc}"

    try:
        registry = providers_base.ModelRegistry(registry_path or providers_base.DEFAULT_REGISTRY_PATH)
    except providers_base.ModelRegistryError as exc:
        return False, f"model registry failed to load: {exc}"

    try:
        scene_plan = build_scene_plan(
            content_manifest,
            project_manifest,
            registry=registry,
            architecture=architecture,
            generation_tier=generation_tier,
            chapter_size=chapter_size,
        )
    except PlanVisualJourneyError as exc:
        return False, str(exc)

    try:
        state.save("scene-plan", scene_plan)
    except se.SchemaValidationFailed as exc:
        return False, f"scene-plan.json failed schema validation on write: {exc}"

    receipt = {
        "producer": "scripts/plan_visual_journey.py",
        "checked_at": _now(),
        "project_id": scene_plan["project_id"],
        "architecture": scene_plan["architecture"],
        "generation_tier": generation_tier,
        "scene_count": len(scene_plan["scenes"]),
        "connector_scene_count": sum(1 for s in scene_plan["scenes"] if s["connector_required"]),
        "registry_snapshot_id": registry.snapshot_id,
        "detail": "journey/scene-plan.json written and schema-validated against structure/scene-plan.schema.json",
    }
    _write_json(run_dir / "scene-planner-receipt.json", receipt)

    detail = (
        f"journey/scene-plan.json written: architecture={scene_plan['architecture']!r}, "
        f"{len(scene_plan['scenes'])} scene(s), generation_tier={generation_tier!r}, "
        f"generation_model={scene_plan['scenes'][0]['generation_model']!r} "
        f"(registry snapshot {registry.snapshot_id[:12]})"
    )
    return True, detail


def check_budget_forecast(run_dir: Path, *, registry_path: Optional[str] = None) -> "tuple[bool, str]":
    """REUSES prove_budget.evaluate_forecast (the real, already-built
    P4-JOURNEY phase gate CWFE-MANIFEST.json wires this skill to) against
    whatever scene-plan.json currently sits in run_dir. Never re-implements
    forecast/pricing logic in this module (ADR-8) — this is a thin,
    intentionally-trivial pass-through, imported lazily so a caller that only
    wants to BUILD a scene plan never pays for importing prove_budget's
    dependency chain."""
    import prove_budget as pbud  # local import: see docstring

    return pbud.evaluate_forecast(run_dir, registry_path=registry_path)


# ---------------------------------------------------------------------------
# Test-fixture helper — builds a REAL locked content-manifest.json via the
# actual U6/U8 production code path (state_engine.create_project +
# resolve_content_engine's cinematic-native builder + finalize_and_save_
# content_manifest), rather than a hand-fabricated dict. Used by both
# self_test() below and tests/unit/test_plan_visual_journey.py, so the two
# suites never drift on what a "valid locked content-manifest" looks like.
# ---------------------------------------------------------------------------
def build_fixture_project_and_content_manifest(
    run_dir: Path,
    *,
    project_id: str = "proj-scene-planner-fixture",
    client_slug: str = "acme",
    project_slug: str = "launch",
    deliverable_type: str = "cinematic-funnel",
    budget_cap_usd: float = 25.0,
    sections: Optional[List[str]] = None,
    cta_map: Optional[Dict[str, Any]] = None,
    claims: Optional[List[Dict[str, str]]] = None,
) -> "tuple[Dict[str, Any], Dict[str, Any]]":
    sections = ["hero", "problem", "solution", "offer", "proof", "cta"] if sections is None else sections
    cta_map = cta_map if cta_map is not None else {
        "hero": {"label": "See How It Works", "type": "scroll"},
        "cta": {"label": "Book a Call", "type": "calendar"},
    }
    claims = claims if claims is not None else [
        {"claim": "500+ clients served", "truth_source": "client-provided case study index"},
    ]

    state = se.ProjectState(run_dir)
    project_manifest = state.create_project(
        project_id=project_id,
        client_slug=client_slug,
        project_slug=project_slug,
        deliverable_type=deliverable_type,
        budget_cap_usd=budget_cap_usd,
    )

    decision_payload = {
        "decision": {"methodology_source": "cinematic-native"},
        "request": {"conversion_requirements": {"form": True, "calendar": True, "payment": False}},
    }
    manifest_fields = rce.build_cinematic_native_manifest_fields(project_id, decision_payload)
    manifest_fields["page_profiles"] = [{"profile_id": "main", "sections": list(sections)}]
    manifest_fields["section_order"] = list(sections)
    manifest_fields["cta_map"] = cta_map
    manifest_fields["claims"] = claims
    content_manifest = rce.finalize_and_save_content_manifest(run_dir, manifest_fields)
    return project_manifest, content_manifest


# ---------------------------------------------------------------------------
# Self-test — offline, temp run_dir, no network. Exercises the happy path,
# the deterministic architecture/connector rules, and the required break-it
# cases, plus a real (not re-implemented) reuse of prove_budget.evaluate_forecast.
# ---------------------------------------------------------------------------
def self_test() -> int:
    import shutil
    import tempfile

    fails = 0

    def check(label: str, cond: bool) -> None:
        nonlocal fails
        if cond:
            print(f"  [PASS] {label}")
        else:
            print(f"  [FAIL] {label}")
            fails += 1

    tmp = Path(tempfile.mkdtemp(prefix="cwfe-plan-visual-journey-selftest-"))
    try:
        # ---- break-it: no content-manifest yet ------------------------------
        passed, detail = plan_visual_journey(tmp)
        check(f"fails cleanly with no content-manifest.json yet ({detail})", not passed)

        state = se.ProjectState(tmp)
        state.create_project(
            project_id="proj-selftest",
            client_slug="acme",
            project_slug="launch",
            deliverable_type="cinematic-funnel",
            budget_cap_usd=25.0,
        )

        # ---- break-it: content-manifest exists but is not locked -------------
        unlocked = {
            "schema_version": "1.0.0",
            "project_id": "proj-selftest",
            "methodology_source": "cinematic-native",
            "source_skill": "62-cinematic-web-funnel-engine",
            "source_skill_version": "0.0.0",
            "page_profiles": [{"profile_id": "main", "sections": ["hero", "cta"]}],
            "section_order": ["hero", "cta"],
            "approved_copy_paths": [],
            "cta_map": {},
            "offer_ledger": [],
            "conversion_requirements": {"form": False, "calendar": False, "payment": False},
            "claims": [],
            "copy_qc_receipt": {},
            "content_hash": "a" * 64,
            "locked": False,
            "created_at": _now(),
            "updated_at": _now(),
        }
        state.save("content-manifest", unlocked)
        passed, detail = plan_visual_journey(tmp)
        check(f"fails cleanly against an unlocked content-manifest ({detail})", not passed)

        # ---- happy path: real locked content-manifest via the actual U8 path -
        tmp2 = Path(tempfile.mkdtemp(prefix="cwfe-plan-visual-journey-selftest2-"))
        try:
            project_manifest, content_manifest = build_fixture_project_and_content_manifest(tmp2)
            check("fixture content-manifest.json is locked=true", content_manifest["locked"] is True)

            passed, detail = plan_visual_journey(tmp2)
            check(f"plan_visual_journey PASSES against a real locked content-manifest ({detail})", passed)

            scene_plan = se.ProjectState(tmp2).load("scene-plan")
            check("scene-plan.json round-trips through the U6 schema validator (load succeeded)", True)
            check("scene count matches section_order length (6)", len(scene_plan["scenes"]) == 6)
            check(
                "architecture auto-selected 'hybrid' for a 6-section, non-scroll-story deliverable",
                scene_plan["architecture"] == "hybrid",
            )
            connector_scene_indices = [i for i, s in enumerate(scene_plan["scenes"]) if s["connector_required"]]
            check(
                "exactly one hybrid chapter-boundary connector at scene index 3 (chapter_size=3 default)",
                connector_scene_indices == [3],
            )
            check(
                "the first scene never carries an incoming connector",
                scene_plan["scenes"][0]["connector_required"] is False,
            )
            check(
                "scene_ids are unique even though architecture/section names could repeat",
                len({s["scene_id"] for s in scene_plan["scenes"]}) == len(scene_plan["scenes"]),
            )
            check(
                "the 'cta' section resolved cta_relationship='primary-cta' (it is a cta_map key)",
                next(s for s in scene_plan["scenes"] if s["page_section"] == "cta")["cta_relationship"]
                == "primary-cta",
            )
            check(
                "the 'cta' section carries a non-empty copy_overlay_timing (it is a cta_map key)",
                len(next(s for s in scene_plan["scenes"] if s["page_section"] == "cta")["copy_overlay_timing"]) == 1,
            )
            check(
                "anchor_inputs carries the locked content-manifest's claim truth_source(s)",
                scene_plan["scenes"][0]["anchor_inputs"] == ["client-provided case study index"],
            )
            check(
                "scene-planner-receipt.json was written",
                (tmp2 / "scene-planner-receipt.json").exists(),
            )

            # ---- determinism: rebuilding from the SAME inputs (minus timestamps) is byte-identical
            registry = providers_base.ModelRegistry()
            rebuilt = build_scene_plan(content_manifest, project_manifest, registry=registry)
            a = {k: v for k, v in scene_plan.items() if k not in ("created_at", "updated_at")}
            b = {k: v for k, v in rebuilt.items() if k not in ("created_at", "updated_at")}
            # per-scene estimated_cost_usd is deterministic too, but scene_plan on disk
            # came from a DIFFERENT registry load (same file, but re-read) — still must match.
            check(
                "rebuilding from identical inputs is deterministic (identical modulo timestamps)",
                json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True),
            )

            # ---- break-it: unknown architecture override ------------------------
            try:
                build_scene_plan(content_manifest, project_manifest, registry=registry, architecture="sideways-shuffle")
                check("build_scene_plan rejects an unknown architecture override", False)
            except PlanVisualJourneyError:
                check("build_scene_plan rejects an unknown architecture override", True)

            # ---- break-it: unknown generation_tier -------------------------------
            try:
                build_scene_plan(content_manifest, project_manifest, registry=registry, generation_tier="ultra-mega-tier")
                check("build_scene_plan rejects an unknown generation_tier", False)
            except PlanVisualJourneyError:
                check("build_scene_plan rejects an unknown generation_tier", True)

            # ---- break-it: project_id mismatch between the two manifests ---------
            mismatched_project_manifest = dict(project_manifest)
            mismatched_project_manifest["project_id"] = "proj-someone-else"
            try:
                build_scene_plan(content_manifest, mismatched_project_manifest, registry=registry)
                check("build_scene_plan rejects a project_id mismatch across manifests", False)
            except PlanVisualJourneyError:
                check("build_scene_plan rejects a project_id mismatch across manifests", True)

            # ---- reuse (not re-implement) prove_budget.evaluate_forecast ---------
            # Default generation_tier ('final-motion') resolves to the
            # currently-UNPRICED bytedance/seedance-1.5-pro model — the
            # forecast gate correctly, deliberately fails-closed (mirrors
            # prove_budget.py's own documented Seedance case), never silently
            # priced at $0.
            budget_ok, budget_detail = check_budget_forecast(tmp2)
            check(
                f"reused prove_budget.evaluate_forecast correctly fails-closed on an unpriced "
                f"generation_tier ({budget_detail})",
                not budget_ok,
            )

            # Rebuilding the SAME project against 'premium-override' (kie-veo3-fast,
            # a VERIFIED price) makes the reused forecast gate PASS end-to-end —
            # proving real integration, not a stub call.
            passed, detail = plan_visual_journey(tmp2, generation_tier="premium-override")
            check(f"rebuilding with generation_tier='premium-override' succeeds ({detail})", passed)
            budget_ok, budget_detail = check_budget_forecast(tmp2)
            check(
                f"reused prove_budget.evaluate_forecast PASSES once every scene targets a "
                f"verified-priced model ({budget_detail})",
                budget_ok,
            )

            # ---- CLI --check-budget wiring (subprocess, exact contract a caller sees) -----
            import subprocess

            cli_result = subprocess.run(
                [sys.executable, str(_SCRIPT_DIR / "plan_visual_journey.py"), "--run-dir", str(tmp2),
                 "--generation-tier", "premium-override", "--check-budget"],
                capture_output=True, text=True,
            )
            check(
                f"CLI --check-budget exits 0 once the scene plan is fully verified-priced (stderr={cli_result.stderr!r})",
                cli_result.returncode == 0,
            )
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

        # ---- break-it: locked content-manifest with no sections at all ---------
        tmp3 = Path(tempfile.mkdtemp(prefix="cwfe-plan-visual-journey-selftest3-"))
        try:
            build_fixture_project_and_content_manifest(tmp3, project_id="proj-empty-sections", sections=[])
            passed, detail = plan_visual_journey(tmp3)
            check(f"fails cleanly against a locked content-manifest with zero sections ({detail})", not passed)
        finally:
            shutil.rmtree(tmp3, ignore_errors=True)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"RESULT: FAIL — {fails} self-test check(s) failed.", file=sys.stderr)
        return 1
    print("RESULT: PASS — visual journey / scene planner self-test green.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visual journey + scene planner producer for the Cinematic and Web Funnel Engine "
        "(Skill 62, U10, spec Section 9). Reads a locked content-manifest.json from --run-dir and writes "
        "journey/scene-plan.json, schema-validated against structure/scene-plan.schema.json. Not itself a "
        "manifest-declared phase gate — CWFE-MANIFEST.json wires P4-JOURNEY to prove_budget.py:"
        "evaluate_forecast, reused (not re-implemented) here via --check-budget."
    )
    parser.add_argument("--run-dir", help="project run directory (required unless --self-test)")
    parser.add_argument("--architecture", choices=_ALLOWED_ARCHITECTURES, default=None,
                         help="override the deterministic architecture default (spec 9.1)")
    parser.add_argument("--generation-tier", choices=_ALLOWED_TIERS, default="final-motion",
                         help="capability tier every scene's generation_model resolves through (default: final-motion)")
    parser.add_argument("--chapter-size", type=int, default=_DEFAULT_CHAPTER_SIZE,
                         help="hybrid-architecture chapter size for connector placement (default: 3)")
    parser.add_argument("--registry", default=None, help="override path to model-registry.json")
    parser.add_argument("--check-budget", action="store_true",
                         help="after writing scene-plan.json, also run (reuse) prove_budget.evaluate_forecast "
                         "and report its result")
    parser.add_argument("--self-test", action="store_true", help="run the built-in offline self-test and exit")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    if not args.run_dir:
        print("USAGE ERROR: --run-dir is required (unless --self-test)", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"USAGE ERROR: --run-dir does not exist: {run_dir}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    if args.chapter_size < 1:
        print("USAGE ERROR: --chapter-size must be >= 1", file=sys.stderr)
        sys.exit(EXIT_USAGE)

    passed, detail = plan_visual_journey(
        run_dir,
        architecture=args.architecture,
        generation_tier=args.generation_tier,
        registry_path=args.registry,
        chapter_size=args.chapter_size,
    )
    if not passed:
        print(f"[FAIL] scene planner — {detail}", file=sys.stderr)
        sys.exit(EXIT_FAIL)
    print(f"[PASS] scene planner — {detail}")

    if args.check_budget:
        budget_ok, budget_detail = check_budget_forecast(run_dir, registry_path=args.registry)
        if budget_ok:
            print(f"[PASS] P4-JOURNEY forecast (reused prove_budget.evaluate_forecast) — {budget_detail}")
        else:
            print(
                f"[FAIL] P4-JOURNEY forecast (reused prove_budget.evaluate_forecast) — {budget_detail}",
                file=sys.stderr,
            )
            sys.exit(EXIT_FAIL)

    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
