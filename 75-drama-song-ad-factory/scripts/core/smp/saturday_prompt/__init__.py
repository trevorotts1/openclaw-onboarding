"""saturday_prompt package: Saturday theme prompt line for the weekly drama
song (Owner D27 / plan section 6.15, 2026-10-07).

Adds "Drama song of the week: keep [current style] or change it?" to the
planner's Saturday theme question. No answer means keep, so the style
persists across weeks. Prompt building and parsing only — no KIE, no network;
Skill 74 stays the sole KIE path. stdlib only.
"""
from .saturday_prompt import (
    DEFAULT_STATE_PATH,
    DEFAULT_STYLE,
    DRAMA_LINE_HEAD,
    DRAMA_LINE_TAIL,
    PROMPT_PREFIX,
    SCHEMA_VERSION,
    TOOL_VERSION,
    build_saturday_prompt,
    load_style,
    main,
    normalize_style,
    parse_reply,
    render_style,
    resolve_week,
    save_style,
)

__all__ = [
    "DEFAULT_STATE_PATH",
    "DEFAULT_STYLE",
    "DRAMA_LINE_HEAD",
    "DRAMA_LINE_TAIL",
    "PROMPT_PREFIX",
    "SCHEMA_VERSION",
    "TOOL_VERSION",
    "build_saturday_prompt",
    "load_style",
    "main",
    "normalize_style",
    "parse_reply",
    "render_style",
    "resolve_week",
    "save_style",
]
