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

S75-057 (unit U-T01) adds the run's OWN choices:
  7. a Seedance 2.5 run -- the model the card sells and the old fixed table
     refused -- answers MODELS yes;
  8. a run that recorded "Agnes: yes" passes its Agnes flash clips, and the
     same clips fail for a run that did not choose Agnes;
  9. every PAID job in the run's spend ledger must name a model: a job the
     ledger holds on a model the run did not choose answers no AND NAMES THE
     JOB, and a job with no model named answers no and names the job.

stdlib only, HOME=$(mktemp -d), no network, no provider call, no spend.
Run: python3 core/delivery_checklist/test_video_model_delivery_f16.py
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                       # .../scripts/core
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import delivery_checklist.delivery_checklist as dc  # noqa: E402
import qc_gate                                     # noqa: E402
import kie_dispatch.model_lock as ML                # noqa: E402
import spend_ledger as L                            # noqa: E402  (real ledger)
from delivery_checklist.test_delivery_checklist import (  # noqa: E402
    full_answered_receipt, final_edit_record, MAKERS, FINAL_GATE_REQUIRED,
    RUN, STAGE, REVIEWER,
)

LOCKED = ML.DEFAULT_VIDEO_MODEL                  # minimax-h3/*
GOOD = "hailuo/02-image-to-video-pro"
GOOD_FAMILY = "hailuo/02-image-to-video-standard"
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
            def check_video_model_delivery(receipt, locked, agnes_chosen=False):
                calls.append((receipt, locked, agnes_chosen))
                return real.check_video_model_delivery(
                    receipt, locked, agnes_chosen=agnes_chosen)

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


#: A ledger helper: one real spend_ledger DB with the paid jobs a run recorded.
def ledger_with_jobs(path, run_id="lanet-run", jobs=()):
    """Create the run's real spend ledger and insert its PAID job rows.

    ``jobs`` is (logical_key, state). The rows are inserted with the ledger's
    own columns; the model each job used is never a ledger column -- that is
    exactly why the run's own per-job rows must name it (S75-057).
    """
    assert L.init_run(str(path), run_id, 100000)["outcome"] == "ok"
    con = sqlite3.connect(str(path))
    try:
        for logical_key, state in jobs:
            con.execute(
                "INSERT INTO jobs(logical_key,attempt_id,run_id,"
                "request_digest,stage,state,final_outcome,created_at,"
                "updated_at) VALUES(?,?,?,?,?,?,?,datetime('now'),"
                "datetime('now'))",
                (logical_key, "att-" + logical_key, run_id, "d" * 64,
                 logical_key.split("/")[0], state, "succeeded"))
        con.commit()
    finally:
        con.close()
    return str(path)


class Q6RunOwnChoices(unittest.TestCase):
    """S75-057: MODELS judges the run's own choices, never a fixed table."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="s75-057-q6-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def seedance_receipt(self):
        receipt = full_answered_receipt()
        receipt["clips"] = clips("bytedance/seedance-2-5")
        receipt["locked_video_model"] = "bytedance/seedance-2-5"
        receipt["MODELS"] = dict(receipt["MODELS"])
        receipt["MODELS"]["used"] = dict(receipt["MODELS"]["used"],
                                         video="Seedance 2.5")
        return receipt

    def test_seedance_25_run_answers_yes(self):
        """The card sells Seedance 2.5; the old fixed table refused it."""
        res = dc.evaluate(self.seedance_receipt())
        self.assertTrue(res["pass"], res["detail"])
        self.assertEqual(res["answers"]["MODELS"]["answer"], "yes")
        self.assertIn("video=Seedance 2.5",
                      res["answers"]["MODELS"]["measurement"])

    def test_agnes_flash_clips_pass_only_when_the_run_chose_agnes(self):
        receipt = self.seedance_receipt()
        receipt["clips"] = clips(ML.AGNES_FLASH_MODEL)
        receipt["agnes"] = {"answer": "yes"}
        res = dc.evaluate(receipt)
        self.assertTrue(res["pass"], res["detail"])
        # the same clips for a run that did not choose Agnes fail, named
        receipt["agnes"] = {"answer": "no"}
        res = dc.evaluate(receipt)
        self.assertFalse(res["pass"])
        self.assertIn("MODELS", res["repair_scope"])
        self.assertIn("VIDEO_MODEL_MISMATCH", res["detail"])

    def test_ledger_job_on_a_different_model_names_the_job(self):
        db = ledger_with_jobs(self.tmp / "spend.sqlite3",
                              jobs=(("video/shot-2", "reconciled"),
                                    ("song/v1", "succeeded")))
        receipt = self.seedance_receipt()
        receipt["spend_ledger"] = db
        receipt["chosen"] = {"video": "bytedance/seedance-2-5",
                             "song": "suno v6"}
        receipt["MODELS"] = dict(receipt["MODELS"])
        receipt["MODELS"]["jobs"] = [
            {"logical_key": "video/shot-2",
             "model": "hailuo/02-image-to-video-standard"},
            {"logical_key": "song/v1", "model": "Suno V6"},
        ]
        res = dc.evaluate(receipt)
        self.assertFalse(res["pass"])
        self.assertIn("MODELS", res["repair_scope"])
        self.assertIn("video/shot-2", res["detail"])
        self.assertIn(dc.CHECKLIST_WRONG_MODEL, res["reason_code"])
        self.assertEqual(res["evidence"]["paid_jobs"]["mismatched"],
                         ["video/shot-2 used hailuo/02-image-to-video-standard "
                          "but the run chose bytedance/seedance-2-5 for video"])

    def test_paid_family_with_no_named_model_answers_no(self):
        """A paid job whose family names no model cannot pass (G7 law 2)."""
        db = ledger_with_jobs(self.tmp / "spend.sqlite3",
                              jobs=(("song/v1", "succeeded"),))
        receipt = full_answered_receipt()
        receipt["spend_ledger"] = db
        receipt["MODELS"] = {"used": {"video": "MiniMax H3 768P"}}
        res = dc.evaluate(receipt)
        self.assertFalse(res["pass"])
        self.assertIn("MODELS", res["repair_scope"])
        self.assertIn("song/v1", res["detail"])
        # the family named again answers yes
        receipt["MODELS"] = {"used": {"video": "MiniMax H3 768P",
                                      "song": "Suno V6"}}
        res = dc.evaluate(receipt)
        self.assertNotIn("MODELS", res["repair_scope"], res["detail"])

    def test_paid_job_the_run_never_names_answers_no(self):
        """Once the run names jobs, every PAID job must be named."""
        db = ledger_with_jobs(self.tmp / "spend.sqlite3",
                              jobs=(("video/shot-2", "reconciled"),
                                    ("song/v1", "succeeded")))
        receipt = self.seedance_receipt()
        receipt["spend_ledger"] = db
        receipt["chosen"] = {"video": "bytedance/seedance-2-5",
                             "song": "suno v6"}
        receipt["MODELS"] = dict(receipt["MODELS"])
        receipt["MODELS"]["jobs"] = [
            {"logical_key": "video/shot-2",
             "model": "bytedance/seedance-2-5"}]
        res = dc.evaluate(receipt)
        self.assertFalse(res["pass"])
        self.assertIn("MODELS", res["repair_scope"])
        self.assertIn("song/v1", res["detail"])
        # naming the missing job with its model answers yes
        receipt["MODELS"]["jobs"].append({"logical_key": "song/v1",
                                          "model": "Suno V6"})
        res = dc.evaluate(receipt)
        self.assertTrue(res["pass"], res["detail"])
        self.assertNotIn("MODELS", res["repair_scope"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
