"""Aspect variant engine. Directive 17.8 export baseline. Stdlib only.

Plans 16:9 / 9:16 / 1:1 variants from the 1080p master baseline. Computes
dimensions and safe areas only; actual transcoding belongs to the media
pipeline, never this module.
"""
from __future__ import annotations

ASPECTS = ("16:9", "9:16", "1:1")
BASELINE_1080P = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
FPS = 30
VIDEO_CODEC = "H.264"
AUDIO_CODEC = "AAC"
AUDIO_SAMPLE_RATE_HZ = 48000

# ponytail: fixed 5% action / 10% title safe insets; add per-placement
# overrides when the directive names values.
SAFE_ACTION_INSET = 0.05
SAFE_TITLE_INSET = 0.10


class VariantError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def expected_dimensions(aspect):
    """1080p (width, height) for an approved aspect. Unknown -> raise."""
    try:
        return BASELINE_1080P[aspect]
    except KeyError:
        raise VariantError("UNKNOWN_ASPECT",
                           "aspect %r not in %s" % (aspect, list(ASPECTS)))


def safe_area(width, height, inset=SAFE_ACTION_INSET):
    """Inset rect kept clear for placement-safe copy."""
    mx, my = int(width * inset), int(height * inset)
    return {"x": mx, "y": my,
            "width": width - 2 * mx, "height": height - 2 * my}


def build_variant_plan(master_path, aspects, profile=None):
    """One plan record per aspect: dims, codecs, safe areas, output path."""
    profile = profile or {}
    seen, plan = set(), []
    for aspect in aspects or []:
        if aspect in seen:
            raise VariantError("DUPLICATE_ASPECT", "duplicate aspect %r" % aspect)
        seen.add(aspect)
        width, height = expected_dimensions(aspect)
        plan.append({
            "aspect": aspect,
            "width": width,
            "height": height,
            "fps": profile.get("fps", FPS),
            "video_codec": profile.get("video_codec", VIDEO_CODEC),
            "audio_codec": profile.get("audio_codec", AUDIO_CODEC),
            "audio_sample_rate_hz": profile.get("audio_sample_rate_hz",
                                                AUDIO_SAMPLE_RATE_HZ),
            "safe_action": safe_area(width, height, SAFE_ACTION_INSET),
            "safe_title": safe_area(width, height, SAFE_TITLE_INSET),
            "source": master_path,
            "output_path": "variants/%s/final.mp4" % aspect.replace(":", "x"),
        })
    if not plan:
        raise VariantError("NO_VARIANTS",
                           "variant plan requires at least one aspect")
    return plan
