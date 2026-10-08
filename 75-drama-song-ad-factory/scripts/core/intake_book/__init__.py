"""core.intake_book -- book campaign intake (owner decision D26, plan 6.14).

Six book brief fields (title, author, cover, buy link, audience,
pain/transformation) folded into the factory's three intake questions
(directive 24.3) -- never a fourth question, never a new question id. The
cover becomes the product image path and is stored as a product reference
with provenance. stdlib only: no network, no runner, no paid call.
"""
from __future__ import annotations

from .book import (
    ALIASES,
    BOOK_FIELDS,
    CTA_PREFIX,
    COVER_NOTE,
    COVER_SOURCE,
    FOLDED_FIELDS,
    LINK_NOTE,
    Q_BOOK_AUDIENCE,
    Q_BOOK_OFFER,
    STORY_ROLE,
    TOOL_NAME,
    TOOL_VERSION,
    SCHEMA_VERSION,
    card_notes,
    evaluate,
    main,
    normalize,
    product_reference,
    to_intake_brief,
)

__all__ = [
    "ALIASES",
    "BOOK_FIELDS",
    "CTA_PREFIX",
    "COVER_NOTE",
    "COVER_SOURCE",
    "FOLDED_FIELDS",
    "LINK_NOTE",
    "Q_BOOK_AUDIENCE",
    "Q_BOOK_OFFER",
    "SCHEMA_VERSION",
    "STORY_ROLE",
    "TOOL_NAME",
    "TOOL_VERSION",
    "card_notes",
    "evaluate",
    "main",
    "normalize",
    "product_reference",
    "to_intake_brief",
]
