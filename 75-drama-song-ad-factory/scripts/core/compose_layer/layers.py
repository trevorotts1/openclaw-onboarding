"""Designed text layers: transitions, end card, offer lower-third
(row N-10, section 3D.2).

HyperFrames is the default engine and Remotion is allowed; both are reached
through Skill 72's adapters, never a home-grown renderer. These jobs are
TEXT LAYERS ONLY -- program name, system name, website, logo, soft scrim --
never an AI picture. A marked section change never gets a bare hard cut:
it gets a designed transition, or the short ffmpeg crossfade of 3D.2's
fallback column.

Stdlib only; this module builds plans, it does not render.
"""
from __future__ import annotations

from .engine import (
    FFMPEG_FALLBACK,
    HYPERFRAMES,
    REMOTION,
    adapter_entry,
)

TOOL_NAME = "compose_layers"
TOOL_VERSION = "1.0.0"

END_CARD = "end_card"
OFFER_LOWER_THIRD = "offer_lower_third"
TRANSITION = "transition"
SECTION_TRANSITION = "section_transition"
KINDS = (END_CARD, OFFER_LOWER_THIRD, TRANSITION, SECTION_TRANSITION)

#: Fields spelled from the run's records, never invented at render time.
REQUIRED_FIELDS = {
    END_CARD: ("program_name", "system_name", "website"),
    OFFER_LOWER_THIRD: ("program_name", "offer", "website"),
    TRANSITION: ("label",),
    SECTION_TRANSITION: ("label",),
}

#: A bare cut at a marked section change is refused (3D.2).
BARE_HARD_CUT_AT_SECTION = "BARE_HARD_CUT_AT_SECTION"
AI_PICTURE_IN_CARD = "AI_PICTURE_IN_CARD"
MISSING_FIELD = "TEXT_LAYER_FIELD_MISSING"
UNKNOWN_KIND = "COMPOSE_LAYER_KIND_UNKNOWN"

#: Fallback crossfade length at a marked join, seconds (short, 3D.2).
CROSSFADE_S = 0.4


class ComposeLayerError(RuntimeError):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def _check_background(background):
    background = background or {"type": "scrim"}
    kind = str(background.get("type", "")).lower()
    if kind in ("ai_picture", "image", "ai"):
        raise ComposeLayerError(AI_PICTURE_IN_CARD,
                                "cards and lower-thirds are text layers only")
    return background


def text_layer(role, value):
    """One text layer: the client-facing string, byte-identical."""
    if value is None or str(value).strip() == "":
        raise ComposeLayerError(MISSING_FIELD, "text layer %r is empty" % role)
    return {"role": role, "type": "text", "value": str(value)}


def build_layer_plan(kind, fields, engine, duration_s, size=(1080, 1920),
                     fps=24, background=None, logo=None, run_id=None):
    """Plan one designed job; ``fields`` come from the run records."""
    if kind not in KINDS:
        raise ComposeLayerError(UNKNOWN_KIND, "unknown layer kind %r" % kind)
    missing = [name for name in REQUIRED_FIELDS[kind]
               if not str(fields.get(name, "")).strip()]
    if missing:
        raise ComposeLayerError(MISSING_FIELD,
                                "fields not spelled from the run records: %s"
                                % ", ".join(missing))
    background = _check_background(background)
    layers = [text_layer(name, fields[name]) for name in REQUIRED_FIELDS[kind]]
    entry = None
    if engine in (HYPERFRAMES, REMOTION):
        entry = adapter_entry(engine)
    plan = {
        "kind": kind,
        "engine": engine,
        "size": list(size),
        "fps": fps,
        "duration_s": float(duration_s),
        "background": background,          # scrim, never an AI picture
        "logo": logo,                      # transparent logo asset, allowed
        "layers": layers,
        "adapter": entry,
        "run_id": run_id,
        "render": "adapter" if entry else "fallback",
    }
    if not entry:
        plan["fallback"] = fallback_plan(kind, duration_s)
    return plan


def fallback_plan(kind, duration_s):
    """3D.2's fallback column, as data for the assembler."""
    if kind in (TRANSITION, SECTION_TRANSITION):
        return {"method": "ffmpeg-crossfade", "duration_s": CROSSFADE_S,
                "why": "no compose engine; never a bare hard cut"}
    return {"method": "ffmpeg-card-picture", "duration_s": float(duration_s),
            "why": "card drawn as one text picture by the skill, placed by ffmpeg"}


def section_changes(changes):
    """Validate marked section changes; a bare hard cut is refused."""
    checked = []
    for change in changes:
        if not change.get("marked"):
            checked.append(dict(change))
            continue
        transition = change.get("transition")
        if not transition or str(transition).lower() in ("cut", "hard_cut", "none"):
            raise ComposeLayerError(
                BARE_HARD_CUT_AT_SECTION,
                "section change at %ss is marked and has no designed transition"
                % change.get("at_s"))
        checked.append(dict(change))
    return checked


def transition_plans(changes, engine):
    """One plan per marked section change, in timeline order."""
    rows = []
    for change in sorted(section_changes(changes), key=lambda c: c.get("at_s", 0)):
        if not change.get("marked"):
            continue
        rows.append(build_layer_plan(
            SECTION_TRANSITION,
            {"label": change.get("label") or "section"},
            engine, change.get("duration_s") or CROSSFADE_S,
            run_id=change.get("run_id")))
    return rows


def crossfade_filter(duration_s=CROSSFADE_S):
    """The ffmpeg fallback: a short xfade, never a bare cut."""
    return ("xfade=transition=fade:duration=%.3f" % float(duration_s))
