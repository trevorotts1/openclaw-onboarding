#!/usr/bin/env python3
"""core.qc: version 2 per-variant QC and gates (Plan 9.3, 9.4). stdlib only.

- variant_qc: one gate per length x shape variant; separate verdicts, a
  record from one variant can never pass another (Plan 9.3).
- media_gate: a media stage cannot pass without the real media file, the
  right duration and format, and an inspection receipt (Plan 9.4, the
  W4-07 lesson).
- creative_fidelity: style injected in every visual prompt, twelve-beat
  arc present, product reveal after the mentor (Plan 9.3).
- lyric_signoff: a recorded human decision on the exact lyrics before
  song generation (Plan 9.3; version 1 recorded none).

Record verdicts stay in core.qc_gate -- this package composes it with the
three V2 gates instead of duplicating it.
"""
from __future__ import annotations

from .creative_fidelity import CreativeError, check_creative
from .lyric_signoff import (
    PASS as SIGNOFF_PASS,
    SignoffError,
    check_signoff,
    lyrics_digest,
    song_generation_allowed,
)
from .media_gate import (
    DEFAULT_TOLERANCE_S,
    KINDS,
    MediaError,
    check_media,
    probe_duration,
    sniff_container,
)
from .variant_qc import (
    BLOCKED,
    CREATIVE_STAGES,
    LENGTHS,
    MEDIA_STAGES,
    REQUIRED_CHECKS,
    SHAPES,
    SIGNOFF_STAGES,
    VariantQCError,
    evaluate_variant,
    evaluate_variants,
    stage_for,
    variant_key,
)

TOOL_NAME = "qc"
TOOL_VERSION = "1.0.0"

__all__ = [
    "BLOCKED", "CREATIVE_STAGES", "CreativeError", "DEFAULT_TOLERANCE_S",
    "KINDS", "LENGTHS", "MEDIA_STAGES", "MediaError", "REQUIRED_CHECKS",
    "SHAPES", "SIGNOFF_STAGES", "SIGNOFF_PASS", "SignoffError", "TOOL_NAME",
    "TOOL_VERSION", "VariantQCError", "check_creative", "check_media",
    "check_signoff", "evaluate_variant", "evaluate_variants",
    "lyrics_digest", "probe_duration", "song_generation_allowed",
    "sniff_container", "stage_for", "variant_key",
]
