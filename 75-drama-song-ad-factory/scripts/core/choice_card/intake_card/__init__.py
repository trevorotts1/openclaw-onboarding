"""choice_card.intake_card: the intake card questions (Part H9).

SWI-002: no total is written here on purpose -- a docstring cannot read the
live count, so the only total anyone may print is len(QUESTIONS). The companion
test test_intake_card_h9.py fails the moment a count claim reappears and
disagrees with the card.
"""
from .intake_card import (  # noqa: F401
    CLOSING_LINE,
    QUESTIONS,
    TELEGRAM_LIMIT,
    StudioExportError,
    assert_registry_options,
    conversation,
    fit_card,
    render_recap,
    render_step,
    format_questions,
    openclaw_send_argv,
    render_card,
    render_messages,
    studio_json,
    studio_questions,
    telegram_payload,
)
