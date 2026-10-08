"""speaker_check package: shot-list speaker-visibility QC (plan 6.6 +
Decision 26). Stdlib only, no spend.

The person visible while a line plays is the speaker, or the voice's
source; narrator plays voice-over but is never lip-synced onto a person;
lip-sync clips isolate the on-screen speaker's own line. Violations fail
the storyboard QC gate (core/qc_gate.py, check="storyboard").
"""
from __future__ import annotations

from .speaker_check import (  # noqa: F401
    CHECK,
    CHECK_ID,
    EXIT,
    GENDERS,
    QC_REQUIREMENT_MARKER,
    QC_SCHEMA_VERSION,
    RULE_CITE,
    SCHEMA_VERSION,
    SPEAKER_TYPES,
    TOOL_NAME,
    TOOL_VERSION,
    SpeakerCheckBlocked,
    SpeakerCheckError,
    check_shot_list,
    classify_speaker,
    evaluate,
    refuse_before_video_spend,
    shot_list_qc,
    to_qc_record,
)

__all__ = [
    "SCHEMA_VERSION", "QC_SCHEMA_VERSION", "TOOL_NAME", "TOOL_VERSION",
    "CHECK", "CHECK_ID", "RULE_CITE", "QC_REQUIREMENT_MARKER",
    "SPEAKER_TYPES", "GENDERS", "EXIT",
    "SpeakerCheckError", "SpeakerCheckBlocked",
    "classify_speaker", "check_shot_list", "evaluate", "to_qc_record",
    "shot_list_qc", "refuse_before_video_spend",
]
