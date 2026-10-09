"""words_fit package: G9 words-and-time preflight before any spend. stdlib only."""
from .words_fit import (  # noqa: F401
    DEFAULT_RATES,
    STYLE_RATES,
    INTRO_OUTRO_S,
    HEADROOM,
    CARD_LENGTHS_S,
    BAND_PTS,
    DEFAULT_SUNG_TARGET_PCT,
    WordsFitError,
    rates_for,
    style_sung_target_pct,
    planned_seconds,
    sung_share_of_voice,
    suno_duration_s,
    max_suno_duration,
    preflight,
    parse_sheet_words,
    preflight_sheet,
)

__all__ = [
    "DEFAULT_RATES", "STYLE_RATES", "INTRO_OUTRO_S", "HEADROOM",
    "CARD_LENGTHS_S", "BAND_PTS", "DEFAULT_SUNG_TARGET_PCT",
    "WordsFitError", "rates_for", "style_sung_target_pct", "planned_seconds", "sung_share_of_voice",
    "suno_duration_s", "max_suno_duration", "preflight", "parse_sheet_words",
    "preflight_sheet",
]
