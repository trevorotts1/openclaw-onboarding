#!/usr/bin/env python3
"""launch_persona_adapter.py — launch-specific task adapter over the Skill 22
persona blueprints.

WHY THIS EXISTS
---------------
Skill 22 ships dual-purpose blueprints: a Coaching Mode (long, quota-heavy,
question-led sessions) and a Task Mode that governs a concrete deliverable.
A launch needs the Task Mode reasoning and none of the coaching machinery:

  * ``hormozi-100m-offers`` governs offer value, the promise, scope, price
    logic and deliverability (Section 4A/4B: value architecture before copy,
    one avatar and one specific outcome, real scarcity only where the client
    recorded it, guarantee conditions, first-week deliverability).
  * ``russell-brunson-the-funnel-hackers-cookbook`` governs the lead magnet,
    the page sequence, the order bump, the one-click upsell/downsell and the
    conversion path (Section 4A: right recipe first, full sequence, every
    ingredient, follow-up wired).
  * ``sinek-start-with-why`` governs WHY, audience alignment, the brand
    promise and voice (Section 4A: WHY before WHAT, HOW as verbs, WHAT as
    proof, belief-fit audience).

WHAT THIS ADAPTER ACTUALLY DOES
-------------------------------
``recommend(task, answers)`` turns the client's OWN recorded answers into one
recommendation for the task that persona maps to, and names the answers it
read (``governed``) plus the exact values it used (``evidence``). The intake
calls it while it is building the offer record, so the recommendation changes
what is proposed rather than decorating a record after the fact. A task whose
answers are absent returns ``value: None`` with the missing facts named - it
never invents an offer, a page or a voice line.

WHAT IS DELIBERATELY NOT IMPORTED
---------------------------------
The blueprints' coaching quotas and their own QC gates are NOT applied to a
launch: no 32-64 obstacle map requirement, no 16-objection minimum, no 22
recipe / 37 page-recipe count, no 4-8 coaching-session arc, and no extra
persona QC gate beyond the launcher's existing checks. ``SUPPRESSED`` records
that in the output.

GUARDRAIL AND HONESTY
---------------------
``copy_persona_blend_seam.render_blend_directive_variable`` is the ONE seam
that renders the directive, so it always ends in the mandatory
style-inspired / NEVER-impersonation clause. Nothing here renders a quotation,
claims an author wrote anything, or implies a real person's endorsement: the
blueprints' direct quotes stay unused, and only the task reasoning is applied.

THE COUNCIL IS NOT TOUCHED HERE
-------------------------------
This module never opens, convenes or starts a Council session and never calls
a Council front door. The Council step of a launch stays the offline package
check in ``83-black-friday-launcher/launcher_core/council.py``
(``run_skill77``).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_SKILL_DIR = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent

PERSONA_SKILL_SLUG = "book-to-persona-coaching-leadership-system"
BLUEPRINT_FILE = "persona-blueprint.md"
ADAPTER_ID = "skill83-launch-task-personas/v2"

# One launch task -> the ONE blueprint the Skill 22 router names for it.
# ``sections`` are the blueprint sections whose Task-Mode reasoning is applied.
TASK_PERSONAS = (
    {
        "task": "offer_architecture",
        "persona_id": "hormozi-100m-offers",
        "governs": "offer value, promise, scope, price logic and deliverability",
        "sections": ("Section 4A - The Execution Standard",
                     "Section 4B - Quality Control Protocol"),
        "preserves": (
            "value architecture before copy",
            "one avatar and one specific outcome",
            "the real price and scope logic the client supplied",
            "scarcity and urgency only where the client recorded them",
            "a deliverable first-week promise",
        ),
    },
    {
        "task": "conversion_path",
        "persona_id": "russell-brunson-the-funnel-hackers-cookbook",
        "governs": "lead magnet, page sequence, order bump, upsell, downsell and conversion path",
        "sections": ("Section 4A - The Execution Standard",),
        "preserves": (
            "the named funnel recipe before any page",
            "the complete page sequence in order",
            "the order bump on the order form",
            "one-click upsell and downsell offers",
            "follow-up after the thank-you page",
        ),
    },
    {
        "task": "why_and_voice",
        "persona_id": "sinek-start-with-why",
        "governs": "WHY, audience alignment, brand promise and voice",
        "sections": ("Section 4A - The Execution Standard",),
        "preserves": (
            "WHY before WHAT",
            "a belief-fit audience, named as who it is for and not for",
            "the brand promise as behaviour, not a slogan",
            "voice that proves the belief instead of pressuring the buyer",
        ),
    },
)

# Explicitly NOT applied to a launch. Recorded so the record never implies a
# quota or a coaching arc was honoured.
SUPPRESSED = (
    "the 32-64 item obstacle-map quota and the 16-objection minimum",
    "the 22-recipe / 37-page-recipe completeness quotas",
    "the 4-8 session coaching arc and its intake scripts",
    "persona QC gates beyond the launcher's existing checks",
    "quota-based questioning during the friendly client interview",
)

VOICE_TASK = "why_and_voice"
TOPIC_TASK = "offer_architecture"

# What each task actually touched in THIS launch, read from the launch record.
# Only keys that are really present are listed; nothing is asserted.
_APPLIED_TO = {
    "offer_architecture": ("offers", "price", "level", "delivery", "promotion"),
    "conversion_path": ("offers", "journey_mode", "route", "purchase_graph"),
    "why_and_voice": ("brand", "copy_profile", "promotion"),
}

# The client answers each task reads, in the order it reads them. This is the
# declaration ``governed`` is measured against: a key is only reported when the
# answer really exists.
_TASK_ANSWERS = {
    "offer_architecture": ("funnel_shape", "price", "packages", "deliverables",
                           "offer_name", "offer_description", "offer_transformation",
                           "audience"),
    "conversion_path": ("funnel_shape", "bump", "upsell_1", "downsell_1", "upsell_2",
                        "page_set", "copy_profile"),
    "why_and_voice": ("voice", "audience", "offer_transformation", "pains",
                      "founder_story", "business_name"),
}

# funnel_shape answer -> journey_mode, the one vocabulary the route law takes.
_SHAPE_TO_MODE = {"single_simple": "single_simple", "multiple_options": "multiple_options",
                  "folded_levels": "folded_levels"}
_SHAPE_TEXT = (("one offer", "single_simple"), ("few package", "multiple_options"),
               ("packages", "multiple_options"), ("levels", "folded_levels"),
               ("build on each other", "folded_levels"))


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _blend_seam():
    """The one existing blend seam, imported by path so this module never
    depends on the caller's sys.path."""
    try:
        if str(_SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(_SCRIPTS_DIR))
        import copy_persona_blend_seam as seam  # type: ignore
        return seam
    except Exception:  # noqa: BLE001
        return None


def _page_set():
    """Skill 49's page_set module, so the landing-page rule has ONE source."""
    try:
        if str(_SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(_SCRIPTS_DIR))
        import page_set as ps  # type: ignore
        return ps
    except Exception:  # noqa: BLE001
        return None


def persona_root() -> Optional[Path]:
    """The installed Skill 22 tree under either naming convention."""
    repo_root = _SKILL_DIR.parent
    home = Path.home()
    numbered = "22-" + PERSONA_SKILL_SLUG
    candidates = [repo_root / numbered,
                  repo_root / PERSONA_SKILL_SLUG,
                  repo_root / ".claude" / "skills" / numbered,
                  repo_root / ".claude" / "skills" / PERSONA_SKILL_SLUG,
                  home / ".openclaw" / "skills" / numbered,
                  home / ".openclaw" / "skills" / PERSONA_SKILL_SLUG,
                  home / ".claude" / "skills" / numbered,
                  home / ".claude-nine" / "skills" / numbered,
                  Path("/data/.openclaw/skills") / numbered]
    if repo_root.is_dir():
        try:
            for path in sorted(repo_root.iterdir()):
                if path.is_dir() and re.fullmatch(r"\d+-" + re.escape(PERSONA_SKILL_SLUG),
                                                  path.name):
                    candidates.insert(0, path)
        except OSError:
            pass
    for path in candidates:
        if (path / "personas").is_dir():
            return path
    return None


def blueprint_path(persona_id: str, root: Optional[Path] = None) -> Optional[Path]:
    root = root or persona_root()
    if root is None:
        return None
    path = root / "personas" / persona_id / BLUEPRINT_FILE
    return path if path.is_file() else None


# --------------------------------------------------------------------------- #
# recommend() — the task recommendation, from the client's own answers only.
# --------------------------------------------------------------------------- #
def _given(answers: Dict[str, Any], key: str) -> Any:
    """The client's usable value for one answer key, or None. Accepts both the
    intake's plain view (key -> value) and the answers ledger (key -> entry)."""
    if not isinstance(answers, dict):
        return None
    value = answers.get(key)
    if isinstance(value, dict) and "value" in value and "state" in value:
        if value.get("state") == "unknown":
            return None
        value = value.get("value")
    if value in (None, "", [], {}):
        return None
    return value


def _journey_mode(answers: Dict[str, Any]) -> Optional[str]:
    shape = _given(answers, "funnel_shape")
    if isinstance(shape, str):
        if shape in _SHAPE_TO_MODE:
            return shape
        low = shape.lower()
        for needle, mode in _SHAPE_TEXT:
            if needle in low:
                return mode
    if _given(answers, "packages"):
        return "multiple_options"
    price = _given(answers, "price")
    if isinstance(price, dict) and price.get("amount_minor") == 0:
        return "free_entry"
    return None


def _landing_pages(mode: Optional[str], answers: Dict[str, Any]) -> List[str]:
    """Skill 49 page_set's own rule, so the sequence has one source."""
    ps = _page_set()
    if ps is None or mode is None:
        return []
    extras = {slot: _given(answers, slot) not in (None, "none")
              for slot in ("upsell_1", "downsell_1", "upsell_2")}
    try:
        return list(ps.recommended_landing_pages({"journey_mode": mode, "extras": extras}))
    except Exception:  # noqa: BLE001 - an unreachable rule recommends nothing
        return []


def _recommend_offer_architecture(answers: Dict[str, Any]) -> Dict[str, Any]:
    mode = _journey_mode(answers)
    free = isinstance(_given(answers, "price"), dict) and \
        (_given(answers, "price") or {}).get("amount_minor") == 0
    gaps: List[str] = []
    if _given(answers, "offer_name") is None and _given(answers, "offer_description") is None:
        gaps.append("what is being sold")
    if _given(answers, "deliverables") is None:
        gaps.append("what the buyer actually gets")
    if _given(answers, "price") is None:
        gaps.append("the price (a number the client gives, or 'it is free')")
    value = None
    if mode is not None:
        value = {"journey_mode": mode,
                 "free_route": bool(free),
                 "one_outcome": _given(answers, "offer_transformation"),
                 "one_avatar": _given(answers, "audience")}
    rationale = ("Read the client's own funnel shape, price, deliverables and outcome. "
                 "The offer is built from those facts only; a free offer takes the free "
                 "route, which is the one route that accepts a zero price, and a missing "
                 "price is named rather than filled in.")
    return {"kind": "offer_architecture", "value": value, "missing": gaps,
            "rationale": rationale}


def _recommend_conversion_path(answers: Dict[str, Any]) -> Dict[str, Any]:
    mode = _journey_mode(answers)
    pages = _landing_pages(mode, answers)
    extras = {slot: _given(answers, slot) not in (None, "none")
              for slot in ("upsell_1", "downsell_1", "upsell_2")}
    sequence: List[str] = list(pages)
    if mode == "multiple_options":
        sequence.append("product_selection")
    sequence.append("checkout")
    if extras["upsell_1"]:
        sequence.append("upsell_1")
    if extras["downsell_1"]:
        sequence.append("downsell_1")
    if extras["upsell_2"]:
        sequence.append("upsell_2")
    sequence.append("thank_you")
    value = {"page_sequence": sequence, "landing_pages": pages, "extras": extras,
             "bump": _given(answers, "bump") not in (None, "none")} if mode else None
    rationale = ("The page sequence comes from Skill 49's own landing-page rule and the "
                 "route law: landing, a selection page only for a few-packages launch, "
                 "checkout, the upsell and downsell the client enabled, then thank-you. "
                 "Nothing is added that the client did not choose.")
    return {"kind": "conversion_path", "value": value,
            "missing": [] if mode else ["the funnel shape (one offer, a few packages, or levels)"],
            "rationale": rationale}


def _recommend_why_and_voice(answers: Dict[str, Any]) -> Dict[str, Any]:
    voice = _given(answers, "voice")
    audience = _given(answers, "audience")
    why = _given(answers, "offer_transformation")
    pains = _given(answers, "pains")
    value = None
    if any(x is not None for x in (voice, audience, why)):
        value = {"voice_terms": voice, "audience": audience,
                 "why_line": why, "pains": pains if isinstance(pains, list) else None}
    missing = []
    if voice is None:
        missing.append("how the client talks (their own words)")
    if audience is None:
        missing.append("who it is for")
    if why is None:
        missing.append("what is different afterwards")
    rationale = ("WHY and voice are taken from the client's own words only. No quote is "
                 "used, no author is named, and no endorsement is implied: the blueprint "
                 "supplies the reasoning, never a quotation.")
    return {"kind": "why_and_voice", "value": value, "missing": missing,
            "rationale": rationale}


_RECOMMENDERS = {"offer_architecture": _recommend_offer_architecture,
                 "conversion_path": _recommend_conversion_path,
                 "why_and_voice": _recommend_why_and_voice}


def governed(task: str, answers: Dict[str, Any]) -> List[str]:
    """The answer keys this task really read: only those the client actually gave."""
    return [key for key in _TASK_ANSWERS.get(task, ()) if _given(answers, key) is not None]


def recommend(task: str, answers: Dict[str, Any]) -> Dict[str, Any]:
    """One task's recommendation, with what it governed. Never raises.

    ``value`` is None when the answers do not support a recommendation, and
    ``missing`` names what is absent - a recommendation is never manufactured
    from a fact the client did not give.
    """
    record = next((r for r in TASK_PERSONAS if r["task"] == task), None)
    if record is None:
        return {"task": task, "persona_id": None, "recommendation": None,
                "governed": [], "evidence": {}, "missing": ["an unknown launch task"],
                "quotes_used": False, "endorsement_claimed": False}
    fn = _RECOMMENDERS.get(task)
    body = fn(answers or {}) if fn else {"kind": task, "value": None, "missing": [], "rationale": ""}
    used = governed(task, answers or {})
    return {
        "task": task,
        "persona_id": record["persona_id"],
        "governs": record["governs"],
        "sections": list(record["sections"]),
        "recommendation": body,
        "governed": used,
        "evidence": {key: _given(answers or {}, key) for key in used},
        "recommended_journey_mode": (body.get("value") or {}).get("journey_mode")
        if task == "offer_architecture" else None,
        "quotes_used": False,
        "endorsement_claimed": False,
    }


def recommend_all(answers: Dict[str, Any]) -> Dict[str, Any]:
    """Every task's recommendation, keyed by task. Used by the launch record."""
    return {record["task"]: recommend(record["task"], answers) for record in TASK_PERSONAS}


# --------------------------------------------------------------------------- #
# The bundle + the record that travels with the launch.
# --------------------------------------------------------------------------- #
def _applied_to(task: str, launch: Dict[str, Any]) -> List[str]:
    """The launch facts a task actually governed, read from the launch alone."""
    out: List[str] = []
    for key in _APPLIED_TO.get(task, ()):
        if key in ("offers", "price", "level", "delivery"):
            if key == "offers" and isinstance(launch.get("offers"), list) and launch["offers"]:
                out.append("offers")
            elif key != "offers" and isinstance(launch.get("offers"), list) and any(
                    key in offer for offer in launch["offers"] if isinstance(offer, dict)):
                out.append("offers[].%s" % key)
        elif isinstance(launch.get(key), (dict, list, str)) and launch.get(key) not in (None, "", [], {}):
            out.append(key)
    if task == "conversion_path":
        roles = sorted({offer.get("role") for offer in (launch.get("offers") or [])
                        if isinstance(offer, dict) and offer.get("role")})
        out.extend("role:%s" % role for role in roles)
    return out


def build_bundle(launch: Optional[Dict[str, Any]] = None,
                 answers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The normalized persona bundle handed to the existing blend seam.

    Shape matches the bundle ``copy_persona_blend_seam`` already consumes
    (voice_persona_id / topic_persona_id / task_personas / blend_directive)."""
    launch = launch if isinstance(launch, dict) else {}
    answers = answers if isinstance(answers, dict) else {}
    task_personas = []
    for seq, record in enumerate(TASK_PERSONAS, start=1):
        rec = recommend(record["task"], answers)
        task_personas.append({
            "seq": seq,
            "task": record["task"],
            "persona_id": record["persona_id"],
            "governs": record["governs"],
            "sections": list(record["sections"]),
            "preserves": list(record["preserves"]),
            "applied_to": _applied_to(record["task"], launch),
            "governed": rec["governed"],
            "recommendation": rec["recommendation"],
        })
    directive = (
        "Launch task modes: build the offer from the client's own supplied value, "
        "price, scope and delivery facts (offer architecture); cook the named funnel "
        "recipe as a complete page sequence with the order bump, one-click upsell and "
        "downsell, and follow-up after the thank-you (conversion path); open with the "
        "brand's WHY, name who it is for and not for, and let the voice prove the "
        "belief rather than pressure the buyer (WHY and voice). Task reasoning only — "
        "no coaching arc, no quota, no persona gate.")
    return {
        "voice_persona_id": next(r["persona_id"] for r in TASK_PERSONAS
                                 if r["task"] == VOICE_TASK),
        "topic_persona_id": next(r["persona_id"] for r in TASK_PERSONAS
                                 if r["task"] == TOPIC_TASK),
        "task_personas": task_personas,
        "blend_directive": directive,
    }


def apply_launch_personas(*, launch: Optional[Dict[str, Any]] = None,
                          answers: Optional[Dict[str, Any]] = None,
                          run_dir: Optional[str] = None,
                          rationale: Optional[str] = None) -> Dict[str, Any]:
    """The record of what was actually applied. Never raises.

    ``directive`` is rendered through ``copy_persona_blend_seam`` so the
    mandatory guardrail is present and identical to every other copy seam.
    When ``run_dir`` is given, the blend seam's own
    ``persona-selection-log.md`` is written there and its digest recorded.
    """
    launch = launch if isinstance(launch, dict) else {}
    answers = answers if isinstance(answers, dict) else {}
    bundle = build_bundle(launch, answers)
    seam = _blend_seam()
    if seam is not None:
        directive = seam.render_blend_directive_variable(bundle)
        log_text = seam.render_persona_selection_log(
            bundle,
            rationale=rationale or "launch task modes over the Skill 22 blueprints")
        log_path = None
        if run_dir:
            try:
                log_path = seam.write_persona_selection_log(run_dir, bundle,
                                                            rationale=rationale or
                                                            "launch task modes over the "
                                                            "Skill 22 blueprints")
            except OSError:
                log_path = None
    else:  # the seam is unreachable: keep the honest, guardrail-bearing minimum
        directive = ("Launch task modes: offer architecture, conversion path and WHY/voice. "
                     "STYLE-INSPIRED, NEVER IMPERSONATION (mandatory, non-removable): adopt "
                     "the cadence, devices and register of the named voice(s) as an "
                     "INSPIRATION only. Never claim to be the author, never write in their "
                     "first person as if they authored this, never sign as them, never "
                     "quote them as if verified, and never imply their endorsement. This "
                     "clause may not be removed or weakened.")
        log_text = None
        log_path = None
    root = persona_root()
    personas = []
    for record in bundle["task_personas"]:
        path = blueprint_path(record["persona_id"], root)
        personas.append({
            "task": record["task"],
            "persona_id": record["persona_id"],
            "governs": record["governs"],
            "sections": record["sections"],
            "preserves": record["preserves"],
            "applied_to": record["applied_to"],
            "governed": record["governed"],
            "recommendation": record["recommendation"],
            "blueprint_present": path is not None,
            "blueprint_ref": (str(path.relative_to(root)) if path is not None and root else None),
        })
    return {
        "adapter": ADAPTER_ID,
        "engine": "Skill 22 persona blueprints, Task Mode",
        "persona_skill": PERSONA_SKILL_SLUG,
        "persona_root": str(root) if root is not None else None,
        "voice_persona_id": bundle["voice_persona_id"],
        "topic_persona_id": bundle["topic_persona_id"],
        "task_personas": personas,
        "blend_directive": directive,
        "blend_directive_sha256": _sha(directive),
        "selection_log_path": log_path,
        "selection_log_sha256": _sha(log_text) if log_text else None,
        "suppressed": list(SUPPRESSED),
        "guardrail_present": "NEVER IMPERSONATION" in directive.upper(),
        "quotes_used": False,
        "endorsement_claimed": False,
        "council_seat_note": (
            "Skill 22 personas govern launch tasks. They are not Council seats: the "
            "Council keeps its fixed nine seats, of which Simon Sinek and Russell "
            "Brunson are two; Alex Hormozi is not a seat and no tenth seat is added. "
            "This adapter never convenes a Council session."),
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="Launch task-mode persona adapter over the Skill 22 blueprints.")
    ap.add_argument("--launch", help="launch intake JSON to record applied_to from")
    ap.add_argument("--answers", help="the answers view/ledger to recommend from")
    ap.add_argument("--run-dir", help="write persona-selection-log.md here")
    a = ap.parse_args()
    payload: Dict[str, Any] = {}
    if a.launch:
        try:
            payload = json.loads(Path(a.launch).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
    given: Dict[str, Any] = {}
    if a.answers:
        try:
            given = json.loads(Path(a.answers).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            given = {}
    print(json.dumps(apply_launch_personas(launch=payload, answers=given,
                                           run_dir=a.run_dir), indent=2))
