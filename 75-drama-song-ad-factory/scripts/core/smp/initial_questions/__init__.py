"""initial_questions package: the drama-song block added to Skill 35's setup
questions (Owner D27 / D35, plan section 6.15, 2026-10-07).

One added block, defaults pre-selected so the client can just say yes: the
weekly yes/no (default yes only while Skill 74 is active), look / music /
voice / length asked once (Lifelike 3D / Soul Ballad / All Suno / 60 seconds,
90 optional), and the weekly call to action defaulting to the planner's own
weekly action link. Prompt building and answer resolution only -- no KIE, no
network, no spend; Skill 74 stays the sole KIE path. stdlib only.
"""
from .initial_questions import (
    BRIEF_ESSENTIALS,
    DEFAULT_LENGTH,
    DEFAULT_STYLE_PATH,
    LENGTHS,
    LOOKS,
    MUSICS,
    Q_WEEKLY_BRIEF,
    SCHEMA_VERSION,
    SOURCE,
    STYLE_FIELDS,
    STYLE_PATH_TEMPLATE,
    TOOL_VERSION,
    VOICES,
    InitialQuestionsError,
    build_block,
    default_weekly,
    load_style,
    main,
    resolve_budget,
    resolve_length,
    resolve_menu,
    resolve_style,
    resolve_weekly,
    resolve_weekly_budget,
    save_style,
)

__all__ = [
    "BRIEF_ESSENTIALS",
    "DEFAULT_LENGTH",
    "DEFAULT_STYLE_PATH",
    "LENGTHS",
    "LOOKS",
    "MUSICS",
    "Q_WEEKLY_BRIEF",
    "SCHEMA_VERSION",
    "SOURCE",
    "STYLE_FIELDS",
    "STYLE_PATH_TEMPLATE",
    "TOOL_VERSION",
    "VOICES",
    "InitialQuestionsError",
    "build_block",
    "default_weekly",
    "load_style",
    "main",
    "resolve_budget",
    "resolve_length",
    "resolve_menu",
    "resolve_style",
    "resolve_weekly",
    "resolve_weekly_budget",
    "save_style",
]
