"""Prompt template data layer (U15a) + H3 assembler (U15b) + the length-class
table (U15h). Re-exports."""
from .prompt_templates import (  # noqa: F401
    CLASS_FIELDS, CORE_DIR, KIE_LANE_SHARE_NUM, KIE_PER_WINDOW, LANE_MIN_SONG_S,
    LANE_TARGET_S, LENGTH_CLASSES_S, LOOKS, MODES, SHOT_TYPES, SKILL_ROOT,
    TEMPLATES_DIR, VILLAIN_SHOT_TYPE_NAME, PromptTemplateError, assemble_h3,
    band, caps, catalog_path, check, check_product_seconds, expand,
    has_receipt, lane_source, length_class, length_class_code, load,
    product_seconds_bounds, receipt, templates_dir,
)

__all__ = ["CORE_DIR", "LOOKS", "MODES", "SHOT_TYPES", "SKILL_ROOT", "TEMPLATES_DIR",
           "VILLAIN_SHOT_TYPE_NAME", "PromptTemplateError", "assemble_h3", "band",
           "caps", "catalog_path", "check", "check_product_seconds", "expand",
           "has_receipt", "lane_source", "length_class", "length_class_code",
           "load", "product_seconds_bounds", "receipt", "templates_dir",
           "CLASS_FIELDS", "KIE_LANE_SHARE_NUM", "KIE_PER_WINDOW",
           "LANE_MIN_SONG_S", "LANE_TARGET_S", "LENGTH_CLASSES_S"]
