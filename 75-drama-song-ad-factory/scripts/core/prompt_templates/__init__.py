"""Prompt template data layer (U15a) + the retired Kling avatar stubs (N-08) +
H3 assembler (U15b) + Kling video assembler (U15f) + the length-class table
(U15h). Re-exports."""
from .prompt_templates import (  # noqa: F401
    CLASS_FIELDS, CORE_DIR, H3_NATIVE_AUDIO_DECISIONS, H3_NATIVE_AUDIO_DEFAULT,
    KIE_LANE_SHARE_NUM, KIE_PER_WINDOW, LIPSYNC_MODEL, LIPSYNC_PROMPT_PRESENT,
    STILLNESS_PHRASES, ANGLE_CHEAT_PHRASES,
    LANE_MIN_SONG_S, LANE_TARGET_S, LENGTH_CLASSES_S, LOOKS, MODES,
    SHOT_TYPES, SKILL_ROOT, TEMPLATES_DIR, VILLAIN_SHOT_TYPE_NAME,
    PromptTemplateError, assemble_h3, assemble_kling_avatar, assemble_kling_video,
    band, band_cap, book_fragments, caps, catalog_path, check, check_kling, check_kling_avatar, check_run,
    check_product_seconds, expand, has_receipt, kling_avatar_model,
    kling_section_limits, lane_source, layering_refusal, length_class, length_class_code, load,
    native_audio_block, product_seconds_bounds, receipt, style_stamp, check_style_words, locked_look_block, templates_dir,
)

__all__ = [
    "CLASS_FIELDS", "CORE_DIR", "H3_NATIVE_AUDIO_DECISIONS",
    "H3_NATIVE_AUDIO_DEFAULT",
    "KIE_LANE_SHARE_NUM", "KIE_PER_WINDOW", "LIPSYNC_MODEL",
    "STILLNESS_PHRASES", "ANGLE_CHEAT_PHRASES",
    "LIPSYNC_PROMPT_PRESENT",
    "LANE_MIN_SONG_S",
    "LANE_TARGET_S", "LENGTH_CLASSES_S", "LOOKS", "MODES", "SHOT_TYPES",
    "SKILL_ROOT", "TEMPLATES_DIR", "VILLAIN_SHOT_TYPE_NAME", "PromptTemplateError",
    "assemble_h3", "assemble_kling_avatar", "assemble_kling_video", "band",
    "band_cap", "book_fragments", "caps", "catalog_path", "check", "check_kling",
    "check_kling_avatar", "check_run",
    "check_product_seconds", "expand", "has_receipt", "kling_avatar_model",
    "kling_section_limits", "lane_source", "layering_refusal", "length_class",
    "length_class_code", "load", "native_audio_block",
    "product_seconds_bounds", "receipt", "style_stamp", "check_style_words", "locked_look_block", "templates_dir"]
