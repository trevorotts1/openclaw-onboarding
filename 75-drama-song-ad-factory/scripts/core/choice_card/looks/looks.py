#!/usr/bin/env python3
"""Six-look choice card (owner decisions D29 + D23, plan 4.1 / 6.11; N-37).

Look menu, exactly as Trevor named them (D29), plus Stylized 3D animation::

    Lifelike 3D (default)  /  2D Hand-Painted  /  Sketch to Life
                          /  Canvas to Life    /  Canvas to 3D
                          /  Stylized 3D

No choice means Lifelike 3D (defaults decision D23, cited as D24 by the
restart unit). The card's Style line lists all six. Applying a look writes
the look field and NOTHING else -- length, shape, music, voice, clips and
price are untouched and the input card is never mutated.

Style Bible block injection: each look resolves to its own
``[STYLE]...[/STYLE]`` block. The two looks that already have a canonical
Style Bible record reuse it rather than restating it -- 2D Hand-Painted is
the current block (``style_bible_integration.DEFAULT_STYLE``, plan 6.11) and
Sketch to Life is the sketch record (``style_bibles.hybrid``); the three new
looks carry their own record. Pure looks render one block; hybrid looks carry
a ``style_switch:`` line with the plan 6.11 switching rules.

stdlib only, no network, no spend, no provider calls.
"""
from __future__ import annotations

import re

try:
    from style_bible_integration import DEFAULT_STYLE as _PAINTED_STYLE
except ImportError as _e:                      # imported as core.choice_card.looks
    if "style_bible_integration" not in str(_e):
        raise
    from ..style_bible_integration import DEFAULT_STYLE as _PAINTED_STYLE  # type: ignore

try:
    from style_bibles.hybrid.hybrid_bible import SKETCH_STYLE as _SKETCH_STYLE
except ImportError as _e:
    if "style_bibles" not in str(_e):
        raise
    from ...style_bibles.hybrid.hybrid_bible import SKETCH_STYLE as _SKETCH_STYLE  # type: ignore

TOOL_NAME = "choice_card.looks"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.choice-card/looks/v1"

#: The one field this module is allowed to write on a choice card.
LOOK_FIELD = "style"

#: No choice -> Lifelike 3D (decision D23; unit source line cites D24).
DEFAULT_LOOK_ID = "lifelike-3d"

#: Ordered exactly as plan 4.1 prints the Style line.
LOOK_ORDER = (
    "lifelike-3d",
    "2d-hand-painted",
    "sketch-to-life",
    "canvas-to-life",
    "canvas-to-3d",
    "stylized-3d",
)

LOOK_LABELS = {
    "lifelike-3d": "Lifelike 3D",
    "2d-hand-painted": "2D Hand-Painted",
    "sketch-to-life": "Sketch to Life",
    "canvas-to-life": "Canvas to Life",
    "canvas-to-3d": "Canvas to 3D",
    "stylized-3d": "Stylized 3D",
}

LOOK_DESCRIPTIONS = {
    "lifelike-3d": "cinematic CGI animation; clearly animated, lifelike faces",
    "2d-hand-painted": "hand-painted 2D cartoon (current Style Bible block)",
    "sketch-to-life": ("black-and-white sketch to real footage, warm golden "
                       "finale (the reference ad)"),
    "canvas-to-life": "2D painted cartoon to real footage, warm golden finale",
    "canvas-to-3d": "2D painted cartoon to lifelike 3D (Version E)",
    #: N-37: the look clients call "Pixar-style"; plan 3B.5 words, no studio name.
    "stylized-3d": ("rounded, appealing 3D animation: enlarged eyes, simplified "
                    "skin, soft bounced light, rich colour"),
}

#: Plan 6.11 switching rules, per hybrid look. Pure looks have none.
STYLE_SWITCH_NOTES = {
    "sketch-to-life": (
        "black-and-white hand-drawn sketch switching to REALISM "
        "(style-bibles/realism-cinematic.md) and back, warm golden realism "
        "finale; switch on matching poses or framings with a 0.3-0.4 s "
        "dissolve, hold each style at least 3 s, no flicker; the character "
        "is identical across the switch (reference-image keyframes and the "
        "identity lock); no lip-sync on sketch shots"),
    "canvas-to-life": (
        "2D hand-painted cartoon switching to REALISM "
        "(style-bibles/realism-cinematic.md) and back, warm golden realism "
        "finale; same switching rules as Sketch to Life: matching poses or "
        "framings, 0.3-0.4 s dissolve, at least 3 s hold, no flicker, "
        "identity lock across the switch"),
    "canvas-to-3d": (
        "2D hand-painted cartoon switching to lifelike 3D cinematic CGI "
        "(Version E recipe) and back; matching poses or framings, 0.3-0.4 s "
        "dissolve, at least 3 s hold, no flicker, identity lock across the "
        "switch; lip-sync only on the lifelike 3D close-ups"),
}

#: Plan 6.11: Lifelike 3D record of its own (no canonical record existed).
LIFELIKE_3D_STYLE = {
    "schema_version": "1.0.0",
    "style_id": "lifelike-3d-cgi-01",
    "aspect_ratio": "9:16",
    "aesthetic": ("cinematic CGI animation; clearly animated, lifelike faces "
                  "with believable weight, never photoreal live-action"),
    "rendering_style": ("high-end 3D character animation: physically-based "
                        "shading, groomed hair, subsurface-scattered skin; "
                        "no flat cartoon colour and no live-action plate"),
    "camera_language": ("cinematic eye-level staging, deliberate slow moves "
                        "and held close-ups, readable at phone width"),
    "lens_tendencies": ("35mm-equivalent framing with shallow depth layering; "
                        "focus guides the eye, no lens distortion"),
    "lighting_doctrine": ("motivated key with soft fill, controlled "
                          "specular highlights on skin, cloth and props"),
    "contrast_architecture": ("stable midtone contrast, rolled highlights, "
                              "shadow shapes that still read on a phone"),
    "environment_texture": ("CGI sets in the same render family as the "
                            "characters: physically-based surfaces with "
                            "settled wear and readable depth"),
    "grain_sharpness": ("fine film grain over a clean render, crisp edges, "
                        "no digital sharpening halo"),
    "color_palette": ["filmic neutral", "amber warmth", "cool steel"],
    "visual_continuity_constraints": [
        "one character model, wardrobe and grooming for the whole ad; the "
        "identity lock holds in every shot",
        "same render family and grade across all shots; no style drift",
        "clearly animated: the viewer always knows this is CGI, never film",
    ],
    "banned_visual_cliches": [
        "live-action plate passed off as CGI",
        "plastic waxy skin",
        "uncanny dead eyes",
        "stock cinematic b-roll",
    ],
}

#: N-37 / plan 3B.5: Stylized 3D animation, the look clients call "Pixar-like".
#: The canonical mode file is U-LOOK's `references/prompt-templates/modes/
#: stylized-3d.json`; this record is the card's own read-only copy so a look can
#: never be half-defined. No studio name appears anywhere: it never goes in a prompt.
STYLIZED_3D_STYLE = {
    "schema_version": "1.0.0",
    "style_id": "stylized-3d-animation-01",
    "aspect_ratio": "9:16",
    "aesthetic": ("rounded, appealing 3D character animation: big expressive "
                  "eyes, simplified skin, warm bounced light, rich colour; "
                  "clearly animated, never photoreal live-action"),
    "rendering_style": ("stylized 3D feature animation: soft rounded forms, "
                        "hand-tuned proportions, gentle rim light, clean "
                        "surfaces with no photographic texture"),
    "camera_language": ("friendly cinematic staging, clear silhouettes, slow "
                        "readable moves that hold on faces"),
    "lens_tendencies": ("mild wide-to-normal framing with soft depth layering; "
                        "no lens distortion, no photographic bokeh artefacts"),
    "lighting_doctrine": ("soft key with generous bounce fill, glowing warm "
                          "highlights, gentle shadows that leave faces open"),
    "contrast_architecture": ("bright midtones, lifted shadows, saturated but "
                              "controlled highlights"),
    "environment_texture": ("stylized sets in the same render family as the "
                            "characters: simplified surfaces, playful "
                            "proportions, readable depth"),
    "grain_sharpness": ("clean render with crisp edges and no film grain, no "
                        "digital sharpening halo"),
    "color_palette": ["sunny amber", "coral warm", "clear teal"],
    "visual_continuity_constraints": [
        "one character model, wardrobe and grooming for the whole ad; the "
        "identity lock holds in every shot",
        "same render family and grade across all shots; no style drift",
        "clearly animated: never a photograph, never live action",
    ],
    "banned_visual_cliches": [
        "photoreal skin texture",
        "live-action plate passed off as animation",
        "uncanny dead eyes",
    ],
}

#: Which record each look renders from (plan 6.11 column 2).
_RECORDS = {
    "lifelike-3d": LIFELIKE_3D_STYLE,
    "2d-hand-painted": _PAINTED_STYLE,
    "sketch-to-life": _SKETCH_STYLE,
    "canvas-to-life": _PAINTED_STYLE,
    "canvas-to-3d": _PAINTED_STYLE,
    "stylized-3d": STYLIZED_3D_STYLE,
}

_STYLE_BLOCK_RE = re.compile(r"\[STYLE\].*?\[/STYLE\]", re.DOTALL)

_RENDER_KEYS = (
    "aesthetic", "rendering_style", "camera_language", "lens_tendencies",
    "lighting_doctrine", "contrast_architecture", "environment_texture",
    "grain_sharpness",
)


class LookError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


# ------------------------------------------------------------------ menu ----

def _norm(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


#: normal form of id AND label -> id, so the client may type either.
_BY_NORM = {}
for _lid in LOOK_ORDER:
    _BY_NORM[_norm(_lid)] = _lid
    _BY_NORM[_norm(LOOK_LABELS[_lid])] = _lid

#: N-37: the intake menu (`smp/initial_questions`) prints this look as
#: "Stylized 3D Animation" while the card prints "Stylized 3D". One look, so
#: both spellings resolve; the guard reads whatever label the sibling prints.
_BY_NORM[_norm("Stylized 3D Animation")] = "stylized-3d"


def looks_menu():
    """The six-look menu, in card order, each with its default flag."""
    return [
        {
            "id": lid,
            "label": LOOK_LABELS[lid],
            "description": LOOK_DESCRIPTIONS[lid],
            "default": lid == DEFAULT_LOOK_ID,
        }
        for lid in LOOK_ORDER
    ]


def resolve_look(choice=None):
    """Client choice -> look id. Nothing chosen means Lifelike 3D (D23).

    Case, spaces, dashes and parentheses are ignored, so "Canvas to 3D",
    "canvas-to-3d" and "Lifelike 3D (default)" all resolve. An unknown look
    is refused by name and the menu is listed (never silently defaulted).
    """
    if choice is None:
        return DEFAULT_LOOK_ID
    if not isinstance(choice, str):
        raise LookError("LOOK_NOT_OFFERED",
                        "%r is not a look name; offered: %s"
                        % (choice, ", ".join(LOOK_ORDER)))
    norm = _norm(choice)
    if not norm:
        return DEFAULT_LOOK_ID
    if norm in ("default", "nochoice", "none"):
        return DEFAULT_LOOK_ID
    if norm.endswith("default"):        # the card prints "Lifelike 3D (default)"
        norm = norm[:-len("default")]
    hit = _BY_NORM.get(norm)
    if hit is None:
        raise LookError("LOOK_NOT_OFFERED",
                        "%r is not one of the six looks: %s"
                        % (choice, ", ".join(LOOK_ORDER)))
    return hit


def style_line():
    """The card's Style line: all six looks, default marked (plan 4.1, N-37)."""
    parts = []
    for lid in LOOK_ORDER:
        label = LOOK_LABELS[lid]
        parts.append("%s (default)" % label if lid == DEFAULT_LOOK_ID else label)
    return "  Style:       %s" % "  /  ".join(parts)


# ------------------------------------------------------------ card write ----

def apply_look(card, choice=None):
    """Return a copy of the card with only the look field written.

    This is the whole override surface: length, shape, music, voice, clips,
    video model and price come back byte-identical, and the caller's card is
    never mutated. No choice writes the Lifelike 3D default.
    """
    if not isinstance(card, dict):
        raise LookError("CARD_INVALID", "choice card must be a dict")
    out = dict(card)
    out[LOOK_FIELD] = resolve_look(choice)
    return out


# --------------------------------------------------------- bible blocks ----

def bible_block(look=None, aspect_ratio=None):
    """The look's ``[STYLE]...[/STYLE]`` Style Bible block.

    Look chooses the record and, for a hybrid look, appends the plan 6.11
    ``style_switch:`` rules. Unknown look refuses by name.
    """
    lid = resolve_look(look)
    rec = _RECORDS[lid]
    lines = ["[STYLE]", "look: %s" % LOOK_LABELS[lid],
             "style_id: %s" % rec.get("style_id", lid),
             "aspect_ratio: %s" % (aspect_ratio or rec.get("aspect_ratio", "9:16"))]
    for key in _RENDER_KEYS:
        if rec.get(key):
            lines.append("%s: %s" % (key, rec[key]))
    for key in ("color_palette", "visual_continuity_constraints",
                "banned_visual_cliches"):
        if rec.get(key):
            lines.append("%s: %s" % (key, " | ".join(rec[key])))
    switch = STYLE_SWITCH_NOTES.get(lid)
    if switch:
        lines.append("style_switch: %s" % switch)
    lines.append("[/STYLE]")
    return "\n".join(lines)


def inject_style_block(prompt, look=None, aspect_ratio=None):
    """Put the look's Style Bible block into a prompt. Nothing else changes.

    An existing ``[STYLE]...[/STYLE]`` block is replaced in place (first one
    only); with no block present the look's block is prepended. The rest of
    the prompt comes back byte-for-byte.
    """
    if not isinstance(prompt, str):
        raise LookError("PROMPT_INVALID", "prompt must be a string")
    block = bible_block(look, aspect_ratio)
    if _STYLE_BLOCK_RE.search(prompt):
        return _STYLE_BLOCK_RE.sub(lambda _m: block, prompt, count=1)
    if not prompt:
        return block
    return "%s\n%s" % (block, prompt)
