"""Prompt template data layer (U15a) + Kling avatar assembler/checker (U15e) +
H3 assembler (U15b) + Kling video assembler (U15f). Re-exports."""
from .prompt_templates import (  # noqa: F401
    CORE_DIR, KLING_AVATAR_MODEL, KLING_FORBIDDEN, KLING_FRAMING_ALT,
    KLING_FRAMING_DEFAULT, KLING_HEAD_EXTRAS, KLING_VERBS, LOOKS, MODES,
    SHOT_TYPES, SKILL_ROOT, TEMPLATES_DIR, VILLAIN_SHOT_TYPE_NAME,
    PromptTemplateError, assemble_h3, assemble_kling_avatar, assemble_kling_video,
    band, band_cap, caps, catalog_path, check, check_kling, check_kling_avatar,
    expand, has_receipt, kling_avatar_model, kling_section_limits, load, receipt,
    templates_dir,
)

__all__ = ["CORE_DIR", "KLING_AVATAR_MODEL", "KLING_FORBIDDEN", "KLING_FRAMING_ALT",
           "KLING_FRAMING_DEFAULT", "KLING_HEAD_EXTRAS", "KLING_VERBS", "LOOKS",
           "MODES", "SHOT_TYPES", "SKILL_ROOT", "TEMPLATES_DIR",
           "VILLAIN_SHOT_TYPE_NAME", "PromptTemplateError", "assemble_h3",
           "assemble_kling_avatar", "assemble_kling_video", "band", "band_cap",
           "caps", "catalog_path", "check", "check_kling", "check_kling_avatar",
           "expand", "has_receipt", "kling_avatar_model", "kling_section_limits",
           "load", "receipt", "templates_dir"]
