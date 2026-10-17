#!/usr/bin/env python3
"""test_motion_decline_bookkeeping.py -- FIX-PLAN Item 34 follow-on
(B34-FOLLOW): the chat driver's decline bookkeeping sees the motion
election.

B34-IMPL wired the want_motion_graphics / motion_graphics_declined_reason
pair into both question banks, the hosted contract and the engine
projection, but flagged that deck-intake-driver.py's hardcoded decline
enumerations still omitted the pair: the email pair had four hits in the
driver and the motion pair had zero. A motion decline was therefore
invisible to the driver's decline bookkeeping (_decline_present and the
decline_context arms of _refine_condition_met, plus the residual sweep's
_residual_skippable, which reads the same toggles tuple and delegates to
_decline_present), even though the bank's decline_context turn carries
the motion reason subfield and the generic block_gate machinery gates
completion. This suite pins the close of exactly that gap, in the
existing elections' pattern (the motion toggle sits between the VSL and
email toggles, the bank's own decline_context subfield order):

  * an explicit motion "no" (string or boolean False) is a decline
    present, alone or beside its verbatim recorded reason;
  * the decline_context turn is ASKED when the only decline is the
    motion one, in both _refine_condition_met branches (with and
    without a bank refine_condition);
  * the decline_context turn fails OPEN while the motion toggle is the
    only unanswered waiver toggle, and is skipped only once every
    toggle, motion included, is answered and none declined;
  * the residual safety-net sweep applies the same two rules.

Every test here fails on the tree without the B34-FOLLOW driver change
(the negative control): on that tree the motion toggle is invisible, so
a motion-only decline reads as no decline at all and an unanswered
motion toggle reads as all-answered. Unit-level, direct function calls
against the real driver module, no network, no spend -- the house style
of test_item10_park_classes.py's driver loader.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
DRIVER_PATH = SCRIPTS / "deck-intake-driver.py"

REASON = "No thanks, our brand team handles ALL motion in-house."

#: Every waiver toggle except motion, answered yes. On the pre-change
#: tree this map reads as "all toggles answered, none declined".
OTHERS_YES = {
    "want_teleprompter": "yes",
    "want_speech_script": "yes",
    "want_ghl_upload": "yes",
    "want_audio_deliverable": "yes",
    "want_sales_checkout": "yes",
    "want_vsl_page": "yes",
    "want_email_sequences": "yes",
}

DECLINE_TURN_NO_COND = {"id": "decline_context"}
DECLINE_TURN_WITH_COND = {
    "id": "decline_context",
    "refine_condition": {"deliverables": ["deck"], "missing_inputs": []},
}


def _load_driver():
    spec = importlib.util.spec_from_file_location(
        "deck_intake_driver_b34follow", DRIVER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DRIVER = _load_driver()


class TestDeclinePresentSeesMotion:
    def test_motion_string_no_is_a_decline(self):
        assert DRIVER._decline_present({"want_motion_graphics": "no"}) is True

    def test_motion_boolean_false_is_a_decline(self):
        assert DRIVER._decline_present({"want_motion_graphics": False}) is True

    def test_motion_no_with_verbatim_reason_is_a_decline(self):
        # The recorded pair the bank's decline_context turn produces:
        # the explicit "no" plus the client's verbatim reason.
        answers = {"want_motion_graphics": "no",
                   "motion_graphics_declined_reason": REASON}
        assert DRIVER._decline_present(answers) is True


class TestRefineConditionMetSeesMotion:
    def test_motion_only_decline_asks_the_turn_without_bank_condition(self):
        answers = dict(OTHERS_YES, want_motion_graphics="no",
                       motion_graphics_declined_reason=REASON)
        assert DRIVER._refine_condition_met(
            DECLINE_TURN_NO_COND, answers, {"deck"}) is True

    def test_motion_only_decline_asks_the_turn_with_bank_condition(self):
        answers = dict(OTHERS_YES, want_motion_graphics="no",
                       motion_graphics_declined_reason=REASON)
        assert DRIVER._refine_condition_met(
            DECLINE_TURN_WITH_COND, answers, {"deck"}) is True

    def test_motion_unanswered_fails_open_and_all_yes_skips(self):
        # Motion is the only unanswered waiver toggle: the turn must
        # still surface (fail OPEN, a reason owed is never lost). Once
        # motion is answered yes like the rest, no reason is owed and
        # the turn is skipped. The first assertion is the one the
        # pre-change tree fails: its shorter toggles tuple reads the
        # motion-less map as all-answered and skips the turn.
        assert DRIVER._refine_condition_met(
            DECLINE_TURN_NO_COND, dict(OTHERS_YES), {"deck"}) is True
        assert DRIVER._refine_condition_met(
            DECLINE_TURN_WITH_COND, dict(OTHERS_YES), {"deck"}) is True
        all_yes = dict(OTHERS_YES, want_motion_graphics="yes")
        assert DRIVER._refine_condition_met(
            DECLINE_TURN_NO_COND, all_yes, {"deck"}) is False
        assert DRIVER._refine_condition_met(
            DECLINE_TURN_WITH_COND, all_yes, {"deck"}) is False


class TestResidualSkippableSeesMotion:
    def test_motion_unanswered_is_not_residual_skippable(self):
        # The safety-net sweep must not skip the turn while the motion
        # toggle is unanswered: on the pre-change tree this same map is
        # judged skippable, stranding a reason the client may still owe.
        assert DRIVER._residual_skippable(
            DECLINE_TURN_NO_COND, dict(OTHERS_YES)) is False

    def test_motion_decline_is_not_residual_skippable(self):
        answers = dict(OTHERS_YES, want_motion_graphics="no",
                       motion_graphics_declined_reason=REASON)
        assert DRIVER._residual_skippable(
            DECLINE_TURN_NO_COND, answers) is False
