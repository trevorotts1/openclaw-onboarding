#!/usr/bin/env python3
"""test_pd_bank_014_declined_reason_flags.py -- PD-014: no "why not?" for
options that default to no.

WHAT THIS PINS
--------------
Three opt-ins default to "no" (want_vsl_page, want_email_sequences,
want_motion_graphics). Accepting such a default is not a decline, so it
owes the client no reason:

  * every bank row for those three reasons -- the alias rows AND the
    grouped decline_context subfields -- carries required false,
    block_gate false, and ask_only_if_previously_wanted true;
  * each of the three waiver_field_mapping entries keeps its toggle and
    reason, gains waiver_required false, and carries the no-waiver
    comment;
  * the five toggles that default to YES (teleprompter, speech script,
    GHL upload, audio, sales and checkout) keep their required reasons
    and their blocking gate, so this change did not quietly disarm them;
  * question_sequence projects the prior-YES half as ask_if on those
    three only.

The end-to-end half of PD-014's acceptance (an all-defaults interview is
never asked a _declined_reason, and a teleprompter "no" is still asked its
reason) is driven through the real CLI in the unit's build report; this
file is the definition-level guard that fails in milliseconds if a later
edit flips any of those flags back.

House style: flat file in tests/, direct function calls, no network, no
spend, no media dependency (this file must never skip).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
PRESENTATIONS = SCRIPTS.parent
BANK_PATH = PRESENTATIONS / "intake" / "deck-intake-questions.json"

DEFAULT_NO = {
    "want_vsl_page": "vsl_page_declined_reason",
    "want_email_sequences": "email_sequences_declined_reason",
    "want_motion_graphics": "motion_graphics_declined_reason",
}
DEFAULT_YES = {
    "want_teleprompter": "teleprompter_declined_reason",
    "want_speech_script": "speech_script_declined_reason",
    "want_ghl_upload": "ghl_upload_declined_reason",
    "want_audio_deliverable": "audio_declined_reason",
    "want_sales_checkout": "sales_checkout_declined_reason",
}
NO_WAIVER_COMMENT = ("Declining an opt-in that defaults to no is not a "
                     "waiver; no reason is required.")


def _bank():
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _atomic_questions():
    if str(PRESENTATIONS / "intake") not in sys.path:
        sys.path.insert(0, str(PRESENTATIONS / "intake"))
    from question_sequence import atomic_questions
    return {q["id"]: q for q in atomic_questions(_bank())}


def test_default_no_reasons_are_optional_in_both_bank_shapes():
    deck = _bank()
    rows = {q["id"]: q for q in deck.get("questions", []) if q.get("id")}
    for toggle, reason_id in DEFAULT_NO.items():
        # alias row
        alias = rows[reason_id]
        assert alias["required"] is False, reason_id
        assert alias["block_gate"] is False, reason_id
        assert alias["ask_only_if_previously_wanted"] is True, reason_id
        assert alias["conditional_on"] == {"id": toggle, "equals": "no"}, reason_id
        # grouped subfield
        parent = rows["decline_context"]
        sub = parent["subfields"][reason_id]
        assert sub["required"] is False, reason_id
        assert sub["block_gate"] is False, reason_id
        assert sub["ask_only_if_previously_wanted"] is True, reason_id
        assert sub["conditional_on"] == {"id": toggle, "equals": "no"}, reason_id


def test_default_yes_reasons_keep_their_blocking_gate():
    rows = {q["id"]: q for q in _bank().get("questions", []) if q.get("id")}
    for toggle, reason_id in DEFAULT_YES.items():
        alias = rows[reason_id]
        assert alias["required"] is True, reason_id
        assert alias["block_gate"] is True, reason_id
        assert "ask_only_if_previously_wanted" not in alias, reason_id
        assert alias["conditional_on"] == {"id": toggle, "equals": "no"}, reason_id


def test_waiver_mapping_marks_the_three_as_not_required():
    mapping = _bank()["waiver_field_mapping"]
    for toggle, reason_id in DEFAULT_NO.items():
        gate = toggle[len("want_"):]
        entry = mapping[gate]
        assert entry["toggle"] == toggle, gate
        assert entry["reason"] == reason_id, gate
        assert entry["waiver_required"] is False, gate
        assert entry["waiver_comment"] == NO_WAIVER_COMMENT, gate
    # The five default-YES toggles keep their gate entry untouched: no
    # waiver_required and no no-waiver comment.
    for toggle, reason_id in DEFAULT_YES.items():
        entries = [e for e in mapping.values()
                   if isinstance(e, dict) and e.get("toggle") == toggle]
        assert len(entries) == 1, toggle
        entry = entries[0]
        assert entry["reason"] == reason_id, toggle
        assert "waiver_required" not in entry, toggle
        assert "waiver_comment" not in entry, toggle


def test_question_sequence_projects_the_prior_yes_half():
    by_id = _atomic_questions()
    for toggle, reason_id in DEFAULT_NO.items():
        q = by_id[reason_id]
        assert q["ask_if"] == {"question_id": toggle, "equals": "yes"}, reason_id
        assert q["conditional_on"] == {"id": toggle, "equals": "no"}, reason_id
        assert q["required"] is False, reason_id
        assert q["block_gate"] is False, reason_id
    for reason_id in DEFAULT_YES.values():
        assert "ask_if" not in by_id[reason_id], reason_id
