"""batch_mode -- ONE choice card for the whole batch, ONE ad per book.

Owner decision D26, plan 6.14 (choice-card-spec 3.10):

* ``make_card`` / ``set_books`` / ``price_batch`` / ``approve_batch`` --
  the five fields (length, shape, style, music, voice) are chosen once for the
  batch; the card takes a list of books, one brief each; the card shows the
  batch total (Skill 74 ``price`` per book + the 20% retake allowance) and one
  click approves the whole batch. An unreadable price means the card says
  unavailable and nothing starts.
* ``default_price_fn`` -- the shipped Skill 74 adapter wiring (B4): the
  price seam's default provider, resolved through the catalog calculator;
  ``None`` on a machine with no Skill 74 install (still fail closed).
* ``materialize`` -- one campaign folder, one receipt, one spend-ledger run and
  one Command Center register per book, plus the batch manifest that carries
  the single card.
* ``isolation`` -- the never-mix checks: books and authors never share a
  folder, a ledger run, a Command Center job, a cover, or a file.

No network, no spend, no provider calls: price is an injected seam and the
Command Center outbox is optional and injected too.
"""
from __future__ import annotations

from .batch import (
    BATCH_CARD_KEYS,
    BRIEF_FIELDS,
    BRIEF_OPTIONAL,
    BRIEF_REQUIRED,
    CARD_FIELDS,
    DEFAULT_LENGTH,
    DEFAULT_SHAPE,
    DEFAULT_VOICE,
    DEFAULT_WORKSPACE,
    LENGTH_VALUES,
    RETAKE_ALLOWANCE,
    SCHEMA_VERSION,
    SHAPE_VALUES,
    SOURCE,
    STAGES,
    TOOL_NAME,
    TOOL_VERSION,
    VOICE_LABELS,
    VOICE_VALUES,
    BatchError,
    approve_batch,
    card_digest,
    card_fields,
    card_lines,
    default_price_fn,
    make_card,
    materialize,
    normalize_brief,
    price_batch,
    set_books,
    slugify,
)
from .isolation import (
    REQUIRED_FILES,
    assert_isolated,
    check_briefs,
    find_violations,
)

__all__ = [
    "BATCH_CARD_KEYS",
    "BRIEF_FIELDS",
    "BRIEF_OPTIONAL",
    "BRIEF_REQUIRED",
    "CARD_FIELDS",
    "DEFAULT_LENGTH",
    "DEFAULT_SHAPE",
    "DEFAULT_VOICE",
    "DEFAULT_WORKSPACE",
    "LENGTH_VALUES",
    "RETAKE_ALLOWANCE",
    "REQUIRED_FILES",
    "SCHEMA_VERSION",
    "SHAPE_VALUES",
    "SOURCE",
    "STAGES",
    "TOOL_NAME",
    "TOOL_VERSION",
    "VOICE_LABELS",
    "VOICE_VALUES",
    "BatchError",
    "approve_batch",
    "assert_isolated",
    "card_digest",
    "card_fields",
    "card_lines",
    "default_price_fn",
    "check_briefs",
    "find_violations",
    "make_card",
    "materialize",
    "normalize_brief",
    "price_batch",
    "set_books",
    "slugify",
]
