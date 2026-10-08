"""weekly_step package: Skill 35 weekly drama-song step (Owner D27 / plan 6.15
/ decision 35, 2026-10-07).

One 9:16 drama-song ad per week from the Theme of the Week, made by the Drama
Song Ad Factory (Skill 75) on the client's own KIE key through Skill 74's live
adapter (active mode only), then handed to the planner schedule for every
connected channel that accepts it.

Skill 74 is the only KIE path: this package never talks to KIE, never holds a
key and never falls back to a private client. stdlib only.
"""
from .weekly_step import (
    DEFAULTS,
    DEFAULT_STYLE_PATH,
    EXIT,
    HARD_CAP_S,
    NINETY_WINDOW_S,
    ROUTE,
    SCHEMA_VERSION,
    SHAPE,
    TOOL_VERSION,
    build_brief,
    channel_acceptance,
    client_skip_reason,
    envelope,
    exit_code_for,
    kie_is_active,
    load_style,
    main,
    resolve_kie_mode,
    run_factory,
    run_weekly,
    validate_duration,
)

__all__ = [
    "DEFAULTS",
    "DEFAULT_STYLE_PATH",
    "EXIT",
    "HARD_CAP_S",
    "NINETY_WINDOW_S",
    "ROUTE",
    "SCHEMA_VERSION",
    "SHAPE",
    "TOOL_VERSION",
    "build_brief",
    "channel_acceptance",
    "client_skip_reason",
    "envelope",
    "exit_code_for",
    "kie_is_active",
    "load_style",
    "main",
    "resolve_kie_mode",
    "run_factory",
    "run_weekly",
    "validate_duration",
]
