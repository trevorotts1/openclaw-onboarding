"""Prompt template data layer (U15a) + Kling avatar assembler/checker (U15e) +
H3 assembler (U15b) + Kling video assembler (U15f) + the length-class table
(U15h). Re-exports."""
from .prompt_templates import (  # noqa: F401
    CLASS_FIELDS, CORE_DIR, KIE_LANE_SHARE_NUM, KIE_PER_WINDOW, KLING_AVATAR_MODEL,
    KLING_FORBIDDEN, KLING_FRAMING_ALT, KLING_FRAMING_DEFAULT, KLING_HEAD_EXTRAS,
    KLING_VERBS, LANE_MIN_SONG_S, LANE_TARGET_S, LENGTH_CLASSES_S, LOOKS, MODES,
    SHOT_TYPES, SKILL_ROOT, TEMPLATES_DIR, VILLAIN_SHOT_TYPE_NAME,
    PromptTemplateError, assemble_h3, assemble_kling_avatar, assemble_kling_video,
    band, band_cap, caps, catalog_path, check, check_kling, check_kling_avatar,
    check_product_seconds, expand, has_receipt, kling_avatar_model,
    kling_section_limits, lane_source, length_class, length_class_code, load,
    product_seconds_bounds, receipt, templates_dir,
)

__all__ = [
    "CLASS_FIELDS", "CORE_DIR", "KIE_LANE_SHARE_NUM", "KIE_PER_WINDOW",
    "KLING_AVATAR_MODEL", "KLING_FORBIDDEN", "KLING_FRAMING_ALT",
    "KLING_FRAMING_DEFAULT", "KLING_HEAD_EXTRAS", "KLING_VERBS", "LANE_MIN_SONG_S",
    "LANE_TARGET_S", "LENGTH_CLASSES_S", "LOOKS", "MODES", "SHOT_TYPES",
    "SKILL_ROOT", "TEMPLATES_DIR", "VILLAIN_SHOT_TYPE_NAME", "PromptTemplateError",
    "assemble_h3", "assemble_kling_avatar", "assemble_kling_video", "band",
    "band_cap", "caps", "catalog_path", "check", "check_kling", "check_kling_avatar",
    "check_product_seconds", "expand", "has_receipt", "kling_avatar_model",
    "kling_section_limits", "lane_source", "length_class", "length_class_code",
    "load", "product_seconds_bounds", "receipt", "templates_dir"]
