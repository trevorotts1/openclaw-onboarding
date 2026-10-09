"""Prompt template data layer (U15a). Re-exports the loader, the caps reader
and the Kling avatar assembler/checker (U15e)."""
from .prompt_templates import (  # noqa: F401
    CORE_DIR, KLING_AVATAR_MODEL, KLING_FORBIDDEN, KLING_FRAMING_ALT,
    KLING_FRAMING_DEFAULT, KLING_HEAD_EXTRAS, KLING_VERBS, LOOKS, MODES,
    SHOT_TYPES, SKILL_ROOT, TEMPLATES_DIR, PromptTemplateError,
    assemble_kling_avatar, caps, catalog_path, check_kling_avatar,
    kling_avatar_model, load, templates_dir,
)

__all__ = ["CORE_DIR", "KLING_AVATAR_MODEL", "KLING_FORBIDDEN", "KLING_FRAMING_ALT",
           "KLING_FRAMING_DEFAULT", "KLING_HEAD_EXTRAS", "KLING_VERBS", "LOOKS",
           "MODES", "SHOT_TYPES", "SKILL_ROOT", "TEMPLATES_DIR",
           "PromptTemplateError", "assemble_kling_avatar", "caps", "catalog_path",
           "check_kling_avatar", "kling_avatar_model", "load", "templates_dir"]
