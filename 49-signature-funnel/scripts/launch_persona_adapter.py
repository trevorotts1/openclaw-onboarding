#!/usr/bin/env python3
"""launch_persona_adapter.py — launch-specific task adapter over the Skill 22
persona blueprints (F10).

WHY THIS EXISTS
---------------
Skill 22 ships dual-purpose blueprints: a Coaching Mode (long, quota-heavy,
question-led sessions) and a Task Mode that governs a concrete deliverable.
The Black Friday launcher needs the Task Mode reasoning and none of the
coaching machinery:

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

WHAT IS DELIBERATELY NOT IMPORTED
---------------------------------
The blueprints' coaching quotas and their own QC gates are NOT applied to a
launch: no 32-64 obstacle map requirement, no 16-objection minimum, no 22
recipe / 37 page-recipe count, no 4-8 coaching-session arc, and no extra
persona QC gate beyond the launcher's existing checks. The client's approved
promotion, idea-development needs and the friendly interview stay exactly as
the launcher already runs them. ``SUPPRESSED`` records that in the output.

GUARDRAIL AND HONESTY
---------------------
``copy_persona_blend_seam.render_blend_directive_variable`` is the ONE seam
that renders the directive, so it always ends in the mandatory
style-inspired / NEVER-impersonation clause. Nothing here renders a quotation,
claims an author wrote anything, or implies a real person's endorsement: the
blueprints' direct quotes stay unused, and only the task reasoning is applied.
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
ADAPTER_ID = "skill83-launch-task-personas/v1"

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


def build_bundle(launch: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The normalized persona bundle handed to the existing blend seam.

    Shape matches the bundle ``copy_persona_blend_seam`` already consumes
    (voice_persona_id / topic_persona_id / task_personas / blend_directive)."""
    launch = launch if isinstance(launch, dict) else {}
    task_personas = []
    for seq, record in enumerate(TASK_PERSONAS, start=1):
        task_personas.append({
            "seq": seq,
            "task": record["task"],
            "persona_id": record["persona_id"],
            "governs": record["governs"],
            "sections": list(record["sections"]),
            "preserves": list(record["preserves"]),
            "applied_to": _applied_to(record["task"], launch),
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
                          run_dir: Optional[str] = None,
                          rationale: Optional[str] = None) -> Dict[str, Any]:
    """The record of what was actually applied. Never raises.

    ``directive`` is rendered through ``copy_persona_blend_seam`` so the
    mandatory guardrail is present and identical to every other copy seam.
    When ``run_dir`` is given, the blend seam's own
    ``persona-selection-log.md`` is written there and its digest recorded.
    """
    launch = launch if isinstance(launch, dict) else {}
    bundle = build_bundle(launch)
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
            "Brunson are two; Alex Hormozi is not a seat and no tenth seat is added."),
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="Launch task-mode persona adapter over the Skill 22 blueprints (F10).")
    ap.add_argument("--launch", help="launch intake JSON to record applied_to from")
    ap.add_argument("--run-dir", help="write persona-selection-log.md here")
    a = ap.parse_args()
    payload: Dict[str, Any] = {}
    if a.launch:
        try:
            payload = json.loads(Path(a.launch).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
    print(json.dumps(apply_launch_personas(launch=payload, run_dir=a.run_dir), indent=2))
