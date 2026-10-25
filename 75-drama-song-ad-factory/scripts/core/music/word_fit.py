#!/usr/bin/env python3
"""word_fit.py -- S75-T25 word fit per duration and per style, before dispatch.

Stdlib only. No provider call, no spend, no client write.

The contract formula (MUSIC-AND-VIDEO-UX.md section 3):

    available_vocal_seconds = selected_duration
                              - verified_instrumental_only_seconds
                              - explicit_breath_transition_allowance

Each delivery block is estimated at the style's measured words-per-second rate
and summed with its pauses. The estimate stays an estimate; measured
timestamps after generation are the proof, never BPM or a character count.

Rates come from ``words_fit.rates_for`` (one table, the G9 calibration). A
style it does not know takes the calm-ballad defaults, which fail closed:
"too slow to fit" is reported before dispatch, never "promised to fit".

Protected offer/claim/CTA words are never removed to make a fit. An overflow
returns a precise excess and routes the wording through the existing package
revision/review.

Run: python3 tests/test_music_constraints_t25.py
"""
from __future__ import annotations

import math

try:                                                     # core/ on sys.path
    from words_fit import rates_for as _rates_for
    from words_fit import WordsFitError as _WordsFitError
    from words_fit import DEFAULT_RATES as _DEFAULT_RATES
except ImportError:                                      # imported as core.music
    from ..words_fit import rates_for as _rates_for
    from ..words_fit import WordsFitError as _WordsFitError
    from ..words_fit import DEFAULT_RATES as _DEFAULT_RATES

try:
    from music.constraints import DELIVERIES, duration_seconds
except ImportError:
    from .constraints import DELIVERIES, duration_seconds

TOOL_NAME = "music_word_fit"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.music-word-fit/v1"
SOURCE = "MUSIC-AND-VIDEO-UX.md section 3; S75-T25/S75-A25; core/words_fit rates"

class WordFitError(ValueError):
    """Malformed input or an infeasible plan. Code carries the reason."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message

def _num(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)) or float(value) < 0:
        raise WordFitError("BAD_INPUT", "%s must be a finite number >= 0, got %r"
                           % (name, value))
    return float(value)

def _words(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WordFitError("BAD_INPUT", "words must be an int >= 0, got %r"
                           % (value,))
    return value

def style_rates(style_id):
    """Measured delivery rates for a style id (one table, core/words_fit)."""
    rates = _rates_for(style_id)
    return {d: float(rates.get(d, _DEFAULT_RATES[d])) for d in DELIVERIES}

def available_vocal_seconds(duration_s, instrumental_only_s=0.0,
                            breath_allowance_s=0.0):
    """selected_duration - instrumental_only - breath/transition allowance."""
    duration = duration_seconds(duration_s)
    instrumental = _num(instrumental_only_s, "instrumental_only_s")
    breath = _num(breath_allowance_s, "breath_allowance_s")
    available = duration - instrumental - breath
    if available <= 0:
        raise WordFitError(
            "NO_VOCAL_TIME",
            "%ss cut leaves %.3fs after %.3fs instrumental and %.3fs breath"
            % (duration, available, instrumental, breath))
    return round(available, 6)

def block_seconds(words, delivery, rates):
    """Estimated seconds for one delivery block at its measured rate."""
    _words(words)
    if delivery not in DELIVERIES:
        raise WordFitError("BAD_DELIVERY", "delivery must be one of %s, got %r"
                           % (list(DELIVERIES), delivery))
    rate = _num(rates.get(delivery), "rate[%s]" % delivery)
    if rate <= 0:
        raise WordFitError("BAD_RATE", "rate[%s] must exceed 0" % delivery)
    return round(words / rate, 6)

def fit(blocks, duration_s, style_id, instrumental_only_s=0.0,
        breath_allowance_s=0.0, protected=()):
    """Fit delivery blocks into one style x duration cut.

    ``blocks``: [{delivery, words, pause_s?}] in performance order.
    Returns the plan with ``status`` OK or OVERFLOW. OVERFLOW is a refusal to
    dispatch, carrying the exact excess and the review route; it never trims
    protected words or rewrites approved lines.
    """
    duration = duration_seconds(duration_s)
    if not isinstance(blocks, (list, tuple)) or not blocks:
        raise WordFitError("BAD_INPUT", "at least one delivery block is required")
    rates = style_rates(style_id)
    available = available_vocal_seconds(duration, instrumental_only_s,
                                        breath_allowance_s)
    planned = 0.0
    detail = []
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            raise WordFitError("BAD_INPUT", "block %d must be a dict" % index)
        words = _words(block.get("words"))
        delivery = block.get("delivery")
        pause = _num(block.get("pause_s", 0.0), "pause_s")
        seconds = block_seconds(words, delivery, rates)
        planned += seconds + pause
        detail.append({"delivery": delivery, "words": words,
                       "estimated_s": seconds, "pause_s": pause})
    planned = round(planned, 6)
    protected_words = [w for w in (protected or []) if isinstance(w, str) and w]
    status = "OK" if planned <= available + 1e-9 else "OVERFLOW"
    result = {
        "style_id": style_id,
        "duration_s": duration,
        "rates": rates,
        "available_vocal_seconds": available,
        "planned_seconds": planned,
        "status": status,
        "blocks": detail,
        "protected_words": protected_words,
        "basis": "estimated_words/measured_rate + pauses; measured timestamps after generation",
    }
    if status == "OVERFLOW":
        result["excess_s"] = round(planned - available, 6)
        result["requires"] = "PACKAGE_REVISION_REVIEW"
        result["proposed_edit"] = (
            "shorten proposed wording through the existing package revision; "
            "preserve protected offer/claim/CTA words and never alter owner facts"
        )
    return result
