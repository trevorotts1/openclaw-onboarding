"""Style Bible consumption gate (directive 13.3, Trevor order 2026-10-07).

The default visual style is a real animated Resilia-like style record
(rendering style, palette, character-design doctrine) compiled through
product_style_bible.bible.compile_visual_prompt. assert_compiled is the
consumption gate: image, shot and video prompt intake refuse hand-written
prompts. stdlib only, no schema changes, no network.
"""
from __future__ import annotations

import copy

try:
    from product_style_bible import bible as _bible
except ImportError as _e:  # imported as core.style_bible_integration
    if "product_style_bible" not in str(_e):
        raise
    from ..product_style_bible import bible as _bible

SCHEMA_VERSION = "1.0.0"
TOOL_VERSION = "1.0.0"

#: Re-exported so consumers gate on the one canonical check.
assert_compiled = _bible.assert_compiled

#: Default look: animated Resilia-like. Aspect 9:16 = the live vertical
#: campaign default (sunburst image route per provider-contracts.md).
DEFAULT_STYLE = {
    "schema_version": "1.0.0",
    "style_id": "resilia-animated-01",
    "aspect_ratio": "9:16",
    "aesthetic": ("animated Resilia-like look: expressive stylised 2D "
                  "character animation staged like live-action drama, "
                  "never photoreal"),
    "rendering_style": ("hand-painted 2D animation with clean confident line "
                        "art, painterly backgrounds, soft cel shading on "
                        "characters; no photoreal skin texture"),
    "camera_language": ("intimate eye-level medium shots, slow deliberate "
                        "moves, silhouettes readable at phone width"),
    "lens_tendencies": ("35mm-equivalent framing with gentle depth layering; "
                        "focus guides the eye, no lens distortion"),
    "lighting_doctrine": ("warm golden key with soft teal fill, motivated "
                          "practicals, readable shadow shapes"),
    "contrast_architecture": ("lifted shadows, warm rolled highlights, "
                              "stable midtone contrast"),
    "environment_texture": ("lived-in painterly sets with visible brush "
                            "texture and soft atmospheric depth"),
    "grain_sharpness": ("fine animation grain, crisp line edges, no digital "
                        "sharpening halo"),
    "color_palette": ["warm amber", "deep teal", "soft cream",
                      "coral accent"],
    "visual_continuity_constraints": [
        "character design: fixed proportions; model sheets govern face, "
        "wardrobe and hair in every shot",
        "same palette and line weight across all shots; no photoreal "
        "texture shifts",
        "backgrounds painted in the same brush family as the character "
        "layer",
    ],
    "banned_visual_cliches": [
        "photoreal deepfake skin",
        "generic city timelapse",
        "lens dust overlays",
        "stock cinematic b-roll",
    ],
}


class StyleGateError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def default_style(aspect_ratio=None):
    """Copy of the default animated Resilia style record."""
    rec = copy.deepcopy(DEFAULT_STYLE)
    if aspect_ratio is not None:
        rec["aspect_ratio"] = aspect_ratio
    return rec


def validate_default_style():
    """Error list (empty = the default record is a real valid style)."""
    return _bible.validate_style(DEFAULT_STYLE)


def compile_visual(base_prompt, characters, product, shot, style=None,
                   aspect_ratio=None):
    """Compile a visual prompt with the default (or given) style record.

    Returns bible.compile_visual_prompt's dict: prompt carries the
    [compiled:style= mark, model/aspect routed per provider contracts.
    Raises bible.CompilerError on invalid inputs.
    """
    if not isinstance(base_prompt, str) or not base_prompt.strip():
        raise StyleGateError("BASE_INVALID",
                             "base_prompt must be a non-empty string")
    if not isinstance(shot, dict) or not shot.get("shot_id"):
        raise StyleGateError("SHOT_INVALID",
                             "shot record with shot_id required")
    rec = dict(shot)
    rec["base_prompt"] = base_prompt
    if style is None:
        style_rec = default_style(aspect_ratio)
    else:
        style_rec = dict(style)
        if aspect_ratio is not None:
            style_rec["aspect_ratio"] = aspect_ratio
    return _bible.compile_visual_prompt(style_rec, characters, product, rec)


def require_compiled(prompt, where="visual prompt"):
    """Consumption gate: refuse anything the compiler did not produce."""
    if not _bible.assert_compiled(prompt):
        raise StyleGateError(
            "UNCOMPILED_PROMPT",
            "%s refused: missing [compiled:style= mark; run it through "
            "style_bible_integration.compile_visual first" % where)
    return prompt


def intake_image_prompt(prompt):
    """Image-generation prompt intake: compiler output only."""
    return require_compiled(prompt, "image-generation prompt")
