"""audio_c3.no_echo package: the D22a no-echo rule on every Suno payload
(Owner AF-ECHO-U1, Decision log 36 2026-10-07, plan 6.12 item 3).

The song payload and every voice-pack payload carry the dry close-microphone
vocal rule and the seven negative tags (reverb, echo, delay, hall, ethereal,
ambient, choir pad); a spoken part naming spacious, cinematic or choir is
refused by name. The choice card and the docs each state the dry vocal rule
in one line. Payload shaping and verification only — no network, no media, no
operator paths; Skill 74 stays the sole KIE path. stdlib only.
"""
from .no_echo import (  # noqa: F401
    BRIEF_NEGATIVE_TAGS,
    CARD_LINE,
    DOCS_LINE,
    DRY_RULE,
    KIND_SONG,
    KIND_VOICE_PACK,
    KIE_PATH,
    NEGATIVE_TAGS,
    NoEchoError,
    PROVIDER,
    REQUEST_KINDS,
    RULE_ID,
    RULE_TEXT,
    SCHEMA_VERSION,
    SPOKEN_BANNED_STYLE_WORDS,
    STYLE_TEXT_PATHS,
    TAG_LIST_TEXT,
    TOOL_VERSION,
    card_line,
    check,
    docs_line,
    main,
    negative_tags,
    refused_style_words,
    rule_text,
    song_request,
    stamp,
    voice_pack_request,
)

__all__ = [
    "BRIEF_NEGATIVE_TAGS",
    "CARD_LINE",
    "DOCS_LINE",
    "DRY_RULE",
    "KIND_SONG",
    "KIND_VOICE_PACK",
    "KIE_PATH",
    "NEGATIVE_TAGS",
    "NoEchoError",
    "PROVIDER",
    "REQUEST_KINDS",
    "RULE_ID",
    "RULE_TEXT",
    "SCHEMA_VERSION",
    "SPOKEN_BANNED_STYLE_WORDS",
    "STYLE_TEXT_PATHS",
    "TAG_LIST_TEXT",
    "TOOL_VERSION",
    "card_line",
    "check",
    "docs_line",
    "main",
    "negative_tags",
    "refused_style_words",
    "rule_text",
    "song_request",
    "stamp",
    "voice_pack_request",
]
