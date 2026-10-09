"""lyric_writer package: sung-copy rules over campaign-schema lyrics (directive 11.3). stdlib only."""
from .lyric_structure import (
    SWITCH_EVERY_S,
    build_sheet,
    check_sheet,
    delivery_of_tag,
    delivery_switches,
    lint_delivery_grammar,
    render_tag,
    switch_allowance,
)
from .lyric_writer import (
    MAX_WORDS,
    SCHEMA_VERSION,
    TOOL_VERSION,
    brief_words,
    check_sung_lines,
    spoken_word_budget,
    steer_opening,
    validate_campaign,
    validate_lyrics,
)

__all__ = [
    "MAX_WORDS",
    "SCHEMA_VERSION",
    "SWITCH_EVERY_S",
    "TOOL_VERSION",
    "brief_words",
    "build_sheet",
    "check_sheet",
    "check_sung_lines",
    "delivery_of_tag",
    "delivery_switches",
    "lint_delivery_grammar",
    "render_tag",
    "spoken_word_budget",
    "steer_opening",
    "switch_allowance",
    "validate_campaign",
    "validate_lyrics",
]
