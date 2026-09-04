"""Tests for the NO-CHOICE-OPENER choice-order fix (HOT 2026-08-27).

THE FAULT (live run denise-calloway/trust-ledger/2026-08-27, P-SP-INTAKE-TRACE
parked BLOCKED, run terminal=BLOCKED): the checker demanded the
quick-vs-in-depth choice in the FIRST assistant turn (literal turn_index 0),
while deck-intake-driver.py's canonical order (deck-intake-questions.json:
order 0 presentation_type -> turn 0, order 0.6 standard_mode "Quick or
in-depth?" -> turn 2, sp_mode later for signature decks) can NEVER put it
there. The result: every driver-produced, one-question-per-turn signature
transcript auto-failed AF-INTAKE-BATCH/NO-CHOICE-OPENER @turn 0 -- the
conversation gate rejected the canonical order it is paired with.

THE FIX: the protected invariant is CHOICE-FIRST (the choice precedes the
first Signature 8-Question), not "literal turn 0". Position detection uses
the same VERBATIM bank-prompt match the BATCH-IN-TURN exemption and the E2
regression guard trust -- keyword matching is live-proven too loose (turn 0's
"What kind of presentation is this?" keyword-matches sp:q1 on
'presentation'/'signature' while verbatim-matching only deck:presentation_type).

No test here touches the live run directory; every scenario is synthetic.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from intake_trace_check import (  # noqa: E402
    AF_CODE,
    check_driver_provenance,
    load_bank_questions,
    parse_transcript,
    scan_transcript,
)

CHOICE = ("Quick or in-depth? QUICK asks the 12 essential questions and gets you "
          "moving fast. IN-DEPTH asks the full expanded interview for maximum "
          "precision and control over every detail.")
PT_TURN = ("What kind of presentation is this? (1) From scratch -- we brainstorm "
           "and build it new. (2) From your content -- personal: turn something "
           "you already have (deck/video/transcript) into a presentation.")


@pytest.fixture(scope="module")
def bank():
    return load_bank_questions()


def _reasons(res):
    return [(v["reason"], v.get("turn_index")) for v in res["violations"]]


# ---------------------------------------------------------------------------
# Part 1: the live fault -- driver canonical order must PASS
# ---------------------------------------------------------------------------
class TestCanonicalOrderPasses:
    def test_canonical_driver_order_pt_then_choice_then_questions(self, bank):
        q1 = bank["sp:q1"]["prompt"]
        q2 = bank["sp:q2"]["prompt"]
        turns = [
            {"role": "assistant", "text": PT_TURN},
            {"role": "owner", "text": "from_scratch"},
            {"role": "assistant", "text": CHOICE},
            {"role": "owner", "text": "QUICK"},
            {"role": "assistant", "text": q1},
            {"role": "owner", "text": "My Signature Talk"},
            {"role": "assistant", "text": q2},
            {"role": "owner", "text": "ans"},
        ]
        res = scan_transcript(turns, bank)
        assert res["pass"] is True, f"canonical order must pass, got {_reasons(res)}"

    def test_sp_mode_late_offering_also_passes(self, bank):
        """Signature path: sp_mode's QUICK-or-IN-DEPTH offered mid-interview,
        before q1 -- the exact live transcript's shape."""
        q1 = bank["sp:q1"]["prompt"]
        q2 = bank["sp:q2"]["prompt"]
        turns = [
            {"role": "assistant", "text": PT_TURN},
            {"role": "owner", "text": "signature"},
            {"role": "assistant", "text": "What are you SELLING at the end -- the exact name of the product or offer?"},
            {"role": "owner", "text": "Course"},
            {"role": "assistant", "text": "QUICK or IN-DEPTH? QUICK = 1-2hr build. IN-DEPTH = full 4-phase signature talk (100+ slides, 8 Questions, frame selection)."},
            {"role": "owner", "text": "QUICK"},
            {"role": "assistant", "text": q1},
            {"role": "owner", "text": "Title"},
            {"role": "assistant", "text": q2},
            {"role": "owner", "text": "ans"},
        ]
        res = scan_transcript(turns, bank)
        assert res["pass"] is True, f"late-but-before-q1 offering must pass, got {_reasons(res)}"


# ---------------------------------------------------------------------------
# Part 2: the anti-starvation control -- real violations still fire
# ---------------------------------------------------------------------------
class TestRealViolationsStillFire:
    def test_no_choice_ever_offered_fails(self, bank):
        q1 = bank["sp:q1"]["prompt"]
        q2 = bank["sp:q2"]["prompt"]
        res = scan_transcript([
            {"role": "assistant", "text": q1},
            {"role": "owner", "text": "Title"},
            {"role": "assistant", "text": q2},
            {"role": "owner", "text": "ans"},
        ], bank)
        assert res["pass"] is False
        assert ("NO-CHOICE-OPENER", 0) in _reasons(res)

    def test_choice_offered_after_first_8q_fails(self, bank):
        q1 = bank["sp:q1"]["prompt"]
        q2 = bank["sp:q2"]["prompt"]
        turns = [
            {"role": "assistant", "text": q1},
            {"role": "owner", "text": "Title"},
            {"role": "assistant", "text": CHOICE},
            {"role": "owner", "text": "quick"},
            {"role": "assistant", "text": q2},
            {"role": "owner", "text": "ans"},
        ]
        res = scan_transcript(turns, bank)
        assert res["pass"] is False
        assert ("NO-CHOICE-OPENER", 0) in _reasons(res)

    def test_keyword_only_sp_match_is_not_position_evidence(self, bank):
        """The live false positive: turn 0's generic presentation_type question
        keyword-matches sp:q1 ('presentation'/'signature') but verbatim-matches
        only deck:presentation_type. A choice at turn 2 must not be judged
        'after the first 8-Question' because of that loose match."""
        turns = [
            {"role": "assistant", "text": PT_TURN},   # keyword-matches sp:q1 only
            {"role": "owner", "text": "from_scratch"},
            {"role": "assistant", "text": CHOICE},
            {"role": "owner", "text": "QUICK"},
            {"role": "assistant", "text": bank["sp:q1"]["prompt"]},
            {"role": "owner", "text": "Title"},
        ]
        res = scan_transcript(turns, bank)
        assert res["pass"] is True, f"keyword-only matches must not count as 8-Question position, got {_reasons(res)}"


# ---------------------------------------------------------------------------
# Part 3: live-run replay (shape, not content, from the real transcript)
# ---------------------------------------------------------------------------
class TestLiveRunReplay:
    def test_canonical_order_via_driver_envelope_passes_provenance_and_scan(self, bank):
        """End-to-end: a signed driver envelope in the driver's canonical order
        must pass BOTH check_driver_provenance and scan_transcript -- the two
        gates _chk_sp_intake_trace chains (build_deck.py:9205-9215)."""
        mod = sys.modules["intake_trace_check"]
        q1 = bank["sp:q1"]["prompt"]
        q2 = bank["sp:q2"]["prompt"]
        turns = [
            {"role": "assistant", "text": PT_TURN, "qid": "presentation_type"},
            {"role": "owner", "text": "from_scratch", "qid": "presentation_type"},
            {"role": "assistant", "text": CHOICE, "qid": "standard_mode"},
            {"role": "owner", "text": "QUICK", "qid": "standard_mode"},
            {"role": "assistant", "text": q1, "qid": "q1"},
            {"role": "owner", "text": "Title", "qid": "q1"},
            {"role": "assistant", "text": q2, "qid": "q2"},
            {"role": "owner", "text": "ans", "qid": "q2"},
        ]
        seq = ["presentation_type", "standard_mode", "q1", "q2"]
        env = mod.build_driver_envelope(seq, turns)
        assert check_driver_provenance(env) == []
        parsed = parse_transcript(json.dumps(env))
        res = scan_transcript(parsed, bank)
        assert res["pass"] is True, f"signed canonical envelope must pass, got {_reasons(res)}"
        assert AF_CODE not in {v["code"] for v in res["violations"]}