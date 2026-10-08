"""core.style_defaults -- owner decision D24 (2026-10-07).

When the client makes no choice the factory applies **Lifelike 3D + Soul
Ballad**. The pair is resolved once in ``defaults`` and wired into the three
seams that consume it:

* ``card``         -- the choice card's Style and Music lines, and applying them
* ``style_bible``  -- which Style Bible block is injected into visual prompts
* ``music``        -- which music style (and Suno prompt) the song is built on

An explicit choice always overrides the default, and an off-menu choice is
refused by name rather than silently defaulted.

stdlib only: no network, no runner, no paid call, no file writes.
"""
from __future__ import annotations

from .card import (
    MUSIC_FIELD,
    STYLE_FIELD,
    apply_choices,
    choice_card_lines,
    music_line,
    style_line,
)
from .card_gate import (
    CARD_REQUIRED_FIELDS,
    CARD_UNANSWERED,
    CardGateError,
    answers_recorded,
    answered_stamped,
    gate_run_state,
)
from .defaults import (
    DEFAULT_MUSIC_STYLE,
    DEFAULT_STYLE,
    LENGTH_LABELS_S,
    LENGTH_OPTIONS_S,
    LOOKS,
    MUSIC_STYLES,
    RECOMMENDED_LENGTH_S,
    SOURCE_OF_DEFAULT,
    SOURCE_OF_LENGTH_MENU,
    StyleDefaultsError,
    default_pair,
    music_label,
    resolve_music_style,
    resolve_style,
    style_label,
)
from .music import music_style_ref
from .style_bible import (
    compile_visual,
    inject_style_block,
    style_bible_block,
    style_record,
)

TOOL_NAME = "style_defaults"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.style-defaults/v1"

__all__ = [
    "CARD_REQUIRED_FIELDS",
    "CARD_UNANSWERED",
    "DEFAULT_MUSIC_STYLE",
    "DEFAULT_STYLE",
    "LENGTH_LABELS_S",
    "LENGTH_OPTIONS_S",
    "LOOKS",
    "MUSIC_FIELD",
    "MUSIC_STYLES",
    "SCHEMA_VERSION",
    "SOURCE_OF_DEFAULT",
    "STYLE_FIELD",
    "TOOL_NAME",
    "TOOL_VERSION",
    "CardGateError",
    "StyleDefaultsError",
    "answers_recorded",
    "answered_stamped",
    "apply_choices",
    "choice_card_lines",
    "compile_visual",
    "default_pair",
    "gate_run_state",
    "inject_style_block",
    "music_label",
    "music_line",
    "music_style_ref",
    "resolve_music_style",
    "resolve_style",
    "resolve_style",
    "style_bible_block",
    "style_label",
    "style_line",
    "style_record",
    "RECOMMENDED_LENGTH_S",
    "SOURCE_OF_LENGTH_MENU",
]
