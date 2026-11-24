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
from .look_lock import (
    LOOK_LOCK_RELPATH,
    LookLockError,
    banned_word_hits,
    build_lock,
    is_current,
    is_stale,
    lock_fingerprint,
    look_lock_path,
    mode_banned_words,
    mode_client_wording,
    mode_style_blocks,
    read_lock,
    read_lock_for_run,
    require_lock,
    resolve_look_modes,
    rotate,
    verify_fingerprint,
    verify_still_matches,
    write_lock,
)
from .mode_files import (
    MODES_DIR,
    REQUIRED_BLOCKS as MODE_REQUIRED_BLOCKS,
    check_banned_words,
    check_prompt,
    load_all_modes,
    load_mode,
    modes_dir,
)
from .client_wording import (
    WHAT_CLIENTS_SAY,
    check_guide_file,
    check_guide_wording,
    client_wording_for,
    guide_line_for,
    map_client_wording,
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
    "LOOK_LOCK_RELPATH",
    "LookLockError",
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
    "banned_word_hits",
    "build_lock",
    "choice_card_lines",
    "compile_visual",
    "default_pair",
    "gate_run_state",
    "inject_style_block",
    "is_current",
    "is_stale",
    "lock_fingerprint",
    "look_lock_path",
    "mode_banned_words",
    "mode_client_wording",
    "mode_style_blocks",
    "modes_dir",
    "resolve_look_modes",
    "MODE_REQUIRED_BLOCKS",
    "MODES_DIR",
    "check_banned_words",
    "check_prompt",
    "load_all_modes",
    "load_mode",
    "WHAT_CLIENTS_SAY",
    "check_guide_file",
    "check_guide_wording",
    "client_wording_for",
    "guide_line_for",
    "map_client_wording",
    "music_label",
    "music_line",
    "music_style_ref",
    "read_lock",
    "read_lock_for_run",
    "require_lock",
    "resolve_music_style",
    "resolve_style",
    "resolve_style",
    "rotate",
    "style_bible_block",
    "style_label",
    "style_line",
    "style_record",
    "verify_fingerprint",
    "verify_still_matches",
    "write_lock",
    "RECOMMENDED_LENGTH_S",
    "SOURCE_OF_LENGTH_MENU",
]
