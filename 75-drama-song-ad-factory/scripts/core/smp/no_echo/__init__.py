"""no_echo package: D22a no-echo rule on the SMP weekly drama-song step
(Owner AF-SMP-U1, Decision log 36-37 applied to Skill 35, plan 6.15).

Every Suno request the weekly step builds carries the dry close-microphone
vocal rule and the seven negative tags (reverb, echo, delay, hall, ethereal,
ambient, choir pad); a spoken part naming spacious, cinematic or choir is
refused by name. Prompt/request shaping and verification only — no network,
no media, no operator paths; Skill 74 stays the sole KIE path. stdlib only.
"""
from .no_echo import (  # noqa: F401
    CARD_LINE,
    DRY_RULE,
    KIE_PATH,
    NEGATIVE_TAGS,
    NoEchoError,
    PROVIDER,
    RULE_ID,
    RULE_TEXT,
    SCHEMA_VERSION,
    SPOKEN_BANNED_STYLE_WORDS,
    STEP,
    TOOL_VERSION,
    card_line,
    check,
    main,
    negative_tags,
    refused_style_words,
    rule_text,
    stamp,
    style_phrase,
    weekly_request,
)

__all__ = [
    "CARD_LINE",
    "DRY_RULE",
    "KIE_PATH",
    "NEGATIVE_TAGS",
    "NoEchoError",
    "PROVIDER",
    "RULE_ID",
    "RULE_TEXT",
    "SCHEMA_VERSION",
    "SPOKEN_BANNED_STYLE_WORDS",
    "STEP",
    "TOOL_VERSION",
    "card_line",
    "check",
    "main",
    "negative_tags",
    "refused_style_words",
    "rule_text",
    "stamp",
    "style_phrase",
    "weekly_request",
]
