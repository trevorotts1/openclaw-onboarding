#!/usr/bin/env python3
"""F16 tests: model_lock.check_video_model_delivery wired into the delivery path.

Done-when (manual Part F F16):
  1. a delivery receipt whose clips all used the card-locked video model
     still PASSES the delivery checklist;
  2. one clip on a different model FAILS the gate -- repair_scope names
     MODELS only, the shared gate verdict is FAIL (targeted repair), never
     BLOCKED, and never CANCEL;
  3. a clip recording no model at all FAILS (absence is not a pass);
  4. a receipt that lists clips but records no lock FAILS (a claim with no
     measurement is a "no", G7 law 2) -- it is never judged against a
     default the run never proved;
  5. the wiring is real: delivery_checklist calls
     model_lock.check_video_model_delivery (proved by a spy, not by a
     passing fixture) and the mismatch string the module builds is what
     the receipt reports;
  6. a receipt with no clip list is untouched by the gate (the per-asset
     `used` check still governs) -- no legacy receipt regresses.

stdlib only, HOME=$(mktemp -d), no network, no provider call, no spend.
Run: python3 core/delivery_checklist/test_video_model_delivery_f16.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                       # .../scripts/core
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import delivery_checklist.delivery_checklist as dc  # noqa: E402
import qc_gate                                     # noqa: E402
import kie_dispatch.model_lock as ML                # noqa: E402
from delivery_checklist.test_delivery_checklist import (  # noqa: E402
    full_answered_receipt, final_edit_record, MAKERS, FINAL_GATE_REQUIRED,
    RUN, STAGE, REVIEWER,
)

LOCKED = ML.DEFAULT_VIDEO_MODEL                  # minimax-h3/*
GOOD = "minimax-h3/text-to-video"
GOOD_FAMILY = "minimax-h3/image-to-video"
OFF_LOCK = "bytedance/seedance-2-mini"


def with_clips(receipt, clips, locked=LOCKED):
    """A complete receipt carrying F16 clip provenance + the card lock."""
    out = dict(receipt)
    out["clips"] = list(clips)
    out["locked_video_model"] = locked
    return out


def clips(*models):
    return [{"id": "c%d" % i, "model": m} for i, m in enumerate(models)]


class F16DeliveryWiring(unittest.TestCase):
    # 1. matching clips pass -------------------------------------------------
    def test_locked_family_clips_pass(self):
        res = dc.evaluate(with_clips(full_answered_receipt(),
                                     clips(GOOD, GOOD_FAMILY)))
        self.assertTrue(res["pass"], res["detail"])
        self.assertEqual(res["repair_scope"], [])
        self.assertIn("video clips=2 locked=%s mismatches=0" % LOCKED,
                      res["answers"]["MODELS"]["measurement"])

    # 2. a mismatched clip fails delivery -----------------------------------
    def test_mismatched_clip_fails_delivery(self):
        res = dc.evaluate(with_clips(full_answered_receipt(),
                                     clips(GOOD, OFF_LOCK)))
        self.assertFalse(res["pass"])
        self.assertEqual(res["repair_scope"], ["MODELS"])
        self.assertIn("VIDEO_MODEL_MISMATCH", res["detail"])
        self.assertIn(dc.CHECKLIST_WRONG_MODEL, res["reason_code"])
        self.assertNotIn("CANCEL", res["reason_code"])
        # the gate stays FAIL, never BLOCKED, never a cancel
        rec = dc.to_qc_record(res, RUN, STAGE, REVIEWER)
        gate = qc_gate.evaluate(RUN, STAGE, [rec, final_edit_record()],
                                MAKERS, FINAL_GATE_REQUIRED,
                                master={"chosen_length_s": 60,
                                        "measured_s": 58})
        self.assertEqual(gate["gate"], "FAIL")
        self.assertEqual(gate["repair_scope"], [dc.CHECK_ID])
        self.assertNotEqual(gate["gate"], "BLOCKED")

    # 3. a clip that records no model cannot pass ---------------------------
    def test_clip_without_model_fails(self):
        res = dc.evaluate(with_clips(full_answered_receipt(),
                                     [{"id": "c0"}]))
        self.assertFalse(res["pass"])
        self.assertEqual(res["repair_scope"], ["MODELS"])
        self.assertIn("records no model", res["detail"])
        self.assertIn(dc.CHECKLIST_WRONG_MODEL, res["reason_code"])

    # 4. clips with no recorded lock fail, never a silent default ----------
    def test_clips_without_recorded_lock_fail(self):
        receipt = dict(full_answered_receipt())
        receipt["clips"] = clips(GOOD)
        res = dc.evaluate(receipt)
        self.assertFalse(res["pass"])
        self.assertEqual(res["repair_scope"], ["MODELS"])
        self.assertIn("records no locked video model", res["detail"])
        self.assertIn(dc.CHECKLIST_NO_MEASUREMENT, res["reason_code"])

    # 5. the wiring is real --------------------------------------------------
    def test_wiring_calls_model_lock(self):
        calls = []
        real = dc.model_lock

        class Spy:
            def __getattr__(self, name):
                return getattr(real, name)

            @staticmethod
            def check_video_model_delivery(receipt, locked):
                calls.append((receipt, locked))
                return real.check_video_model_delivery(receipt, locked)

        dc.model_lock = Spy()
        try:
            dc.evaluate(with_clips(full_answered_receipt(),
                                   clips(GOOD), locked=LOCKED))
        finally:
            dc.model_lock = real
        self.assertEqual(len(calls), 1, "delivery path never called the gate")
        self.assertEqual(calls[0][1], LOCKED)
        self.assertEqual([c["model"] for c in calls[0][0]["clips"]],
                         [GOOD])

    def test_module_used_is_the_real_one(self):
        self.assertIs(dc.model_lock, ML)
        self.assertTrue(callable(dc.model_lock.check_video_model_delivery))

    # 6. no clip list -> the gate does not touch a legacy receipt ----------
    def test_no_clip_list_is_untouched(self):
        calls = []
        real = dc.model_lock

        class Spy:
            def __getattr__(self, name):
                return getattr(real, name)

            @staticmethod
            def check_video_model_delivery(receipt, locked):
                calls.append(receipt)
                return real.check_video_model_delivery(receipt, locked)

        dc.model_lock = Spy()
        try:
            res = dc.evaluate(full_answered_receipt())
        finally:
            dc.model_lock = real
        self.assertTrue(res["pass"], res["detail"])
        self.assertEqual(calls, [], "gate ran with no clip provenance")

    # clip provenance also rides the MODELS answer ---------------------------
    def test_clip_list_on_the_models_answer(self):
        receipt = full_answered_receipt()
        receipt["MODELS"] = dict(receipt["MODELS"])
        receipt["MODELS"]["clips"] = clips(GOOD, OFF_LOCK)
        receipt["MODELS"]["locked_video_model"] = LOCKED
        res = dc.evaluate(receipt)
        self.assertFalse(res["pass"])
        self.assertEqual(res["repair_scope"], ["MODELS"])
        self.assertIn("VIDEO_MODEL_MISMATCH", res["detail"])

    # the per-asset `used` keys are never eaten by the new answer keys -------
    def test_clip_keys_do_not_pollute_used(self):
        receipt = full_answered_receipt()
        receipt["MODELS"] = {"clips": clips(GOOD),
                             "locked_video_model": LOCKED,
                             "used": {"video": "MiniMax H3 768P"}}
        res = dc.evaluate(receipt)
        self.assertTrue(res["pass"], res["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
