"""lyric_writer package: sung-copy rules over campaign-schema lyrics (directive 11.3). stdlib only."""
from .lyric_writer import (
    MAX_WORDS,
    SCHEMA_VERSION,
    TOOL_VERSION,
    brief_words,
    spoken_word_budget,
    steer_opening,
    validate_campaign,
    validate_lyrics,
)

__all__ = [
    "MAX_WORDS",
    "SCHEMA_VERSION",
    "TOOL_VERSION",
    "brief_words",
    "spoken_word_budget",
    "steer_opening",
    "validate_campaign",
    "validate_lyrics",
]
