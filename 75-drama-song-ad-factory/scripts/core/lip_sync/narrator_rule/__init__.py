"""narrator_rule package: Decision 26 / plan 6.6 -- the narrator lip-sync
rule for stage V2-08L. Stdlib only, no network, no spend."""
from __future__ import annotations

from .narrator_rule import (  # noqa: F401
    EXIT,
    NARRATOR_TOKENS,
    QC_SCHEMA_VERSION,
    RULE_CITE,
    RULE_FLAGGED,
    RULE_UNFLAGGED,
    RULE_VOICE_OVER,
    SCHEMA_VERSION,
    TOOL_NAME,
    TOOL_VERSION,
    NarratorRuleBlocked,
    build_screened_plan,
    check_lipsync_attempt,
    check_stems,
    is_narrator,
    is_voice_source,
    lipsync_selection,
    narrator_qc_rules,
    person_on_screen,
    refuse_lipsync,
    screen_line,
    screen_selection,
)

__all__ = [
    "SCHEMA_VERSION", "QC_SCHEMA_VERSION", "TOOL_NAME", "TOOL_VERSION",
    "RULE_CITE", "NARRATOR_TOKENS", "RULE_VOICE_OVER", "RULE_FLAGGED",
    "RULE_UNFLAGGED", "EXIT", "NarratorRuleBlocked", "is_narrator",
    "is_voice_source", "person_on_screen", "check_stems", "screen_line",
    "screen_selection", "lipsync_selection", "check_lipsync_attempt",
    "refuse_lipsync", "narrator_qc_rules", "build_screened_plan",
]
