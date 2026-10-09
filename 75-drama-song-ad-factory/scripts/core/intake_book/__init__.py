"""core.intake_book -- book campaign intake (owner decision D26, plan 6.14).

Book brief fields (title, author, cover, buy link, language, audience,
pain/transformation) folded into the factory's three intake questions
(directive 24.3) -- never a fourth question, never a new question id. The
cover becomes the product image path and is stored as a product reference
with provenance; its aspect is measured from the file header, and
brief.language (default "en") selects the reading direction the book
orientation contract enforces. stdlib only: no network, no runner, no paid
call.
"""
from __future__ import annotations

from .book import (
    ALIASES,
    BOOK_FIELDS,
    BRIEF_INVENTED_FIELD,
    CTA_PREFIX,
    COVER_NOTE,
    COVER_SOURCE,
    DEFAULT_LANGUAGE,
    FOLDED_FIELDS,
    GATE_ALIASES,
    GATE_KEYS,
    LINK_NOTE,
    Q_BOOK_AUDIENCE,
    Q_BOOK_OFFER,
    STORY_ROLE,
    STYLE_ALIASES,
    STYLE_KEYS,
    TOOL_NAME,
    TOOL_VERSION,
    SCHEMA_VERSION,
    card_notes,
    cover_aspect,
    evaluate,
    main,
    normalize,
    product_reference,
    reading_direction,
    reject_any_invented,
    to_intake_brief,
)

__all__ = [
    "ALIASES",
    "BOOK_FIELDS",
    "BRIEF_INVENTED_FIELD",
    "CTA_PREFIX",
    "COVER_NOTE",
    "COVER_SOURCE",
    "DEFAULT_LANGUAGE",
    "FOLDED_FIELDS",
    "GATE_ALIASES",
    "GATE_KEYS",
    "LINK_NOTE",
    "Q_BOOK_AUDIENCE",
    "Q_BOOK_OFFER",
    "SCHEMA_VERSION",
    "STORY_ROLE",
    "STYLE_ALIASES",
    "STYLE_KEYS",
    "TOOL_NAME",
    "TOOL_VERSION",
    "card_notes",
    "cover_aspect",
    "evaluate",
    "main",
    "normalize",
    "product_reference",
    "reading_direction",
    "reject_any_invented",
    "to_intake_brief",
]
