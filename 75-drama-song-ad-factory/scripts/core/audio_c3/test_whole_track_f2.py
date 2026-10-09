#!/usr/bin/env python3
"""F2 whole-track retake tests (unit W-F-U2, manual Part F F2, High).

Proves, mocked only (no network, zero paid calls):
  * a full-track job PASSES the F2 intake gate;
  * a partial slice job REFUSES PARTIAL_SUNO_JOB;
  * one whole-track retake of a FAILED take passes;
  * negative controls: partial patch, second bed, unlabelled kind, no F1
    stamp, wrong mode, retake of another run's generation, retake after a
    succeeded take, malformed rows -- all fail closed;
  * THE SEAM IS LIVE: the real kie_dispatch.dispatch() refuses a partial
    Suno job at intake (outcome rejected, reason PARTIAL_SUNO_JOB, no
    ledger row, no Skill 74 call) and a full-track F1 request/whole-track
    retake goes through untouched.

Dual-mode -- plain python3 and pytest:

    python3 core/audio_c3/test_whole_track_f2.py
    python3 -m pytest core/audio_c3/test_whole_track_f2.py
"""
from __future__ import annotations

import importlib
import os
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for p in (HERE, CORE):
    if p not in sys.path:
        sys.path.insert(0, p)

import soundtrack as S  # noqa: E402  module under test
import spend_ledger as L  # noqa: E402  sibling core/ module (seam ledger)
import kie_dispatch as KD  # noqa: E402  package: the dispatch seam
KD_MOD = importlib.import_module("kie_dispatch.kie_dispatch")

def _no_paid_runner(*_a, **_k):
    raise AssertionError("real Skill 74 runner disabled in tests")

KD_MOD.make_runner = _no_paid_runner   # zero paid calls, held for the run

def _receipt(gen="gen-1111"):
    """A run receipt in F1 mode: record_soundtrack's stamp on the run."""
    return S.record_soundtrack({}, gen)

def _f1_request(run_receipt=None, **extra):
    """The dispatcher's request for the one F1 full-track generation.

    Carries the run's stamp so the seam sees F1 mode. Only mocked shapes:
    the request is never sent anywhere (the runner is a fake).
    """
    req = {"model": "suno-generate", "input": {"prompt": "p" * 200},
           "soundtrack": {"mode": S.TRACK_MODE}}
    if run_receipt is not None:
        req["run_receipt"] = run_receipt
    req.update(extra)
    return req

#: The recorded F15 choice-card receipt (four answers, stamped); the card
#: gate sits AFTER the F2 shape gate, so the seam only needs it for the
#: cases that reach further into dispatch.
_STAMPED_CARD = {"answers": {"video_style": "Lifelike 3D",
                             "audio_style": "Soul Ballad",
                             "length": 60,
                             "video_model": "MiniMax H3 768P"},
                 "who": "W-F-U2 seam test",
                 "at": "2026-10-08T09:00:00Z"}

class Fake74:
    """Records every Skill 74 argv; answers health/preflight/submit/wait/save."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        sub = argv[1] if len(argv) > 1 else ""
        if sub == "health":
            return (0, {"adapter_mode": "active", "state": "success"})
        if sub == "preflight":
            return (0, {"state": "validated", "data": {"ok": True}})
        if sub == "prompt-budget":
            return (0, {"state": "success",
                        "data": {"status": "OK", "exit_code": 0,
                                 "max": 20000}})
        if sub == "submit":
            return (0, {"state": "queued", "task_id": "t-f2",
                        "credits_consumed": 6})
        if sub == "wait":
            return (0, {"state": "success", "task_id": "t-f2",
                        "result_urls": ["https://example.invalid/a.mp3"],
                        "credits_consumed": 6})
        if sub == "save":
            path = os.path.join(tempfile.gettempdir(), "f2-out.mp3")
            open(path, "w").close()
            return (0, {"state": "success", "task_id": "t-f2",
                        "saved_paths": [path], "credits_consumed": 6})
        raise AssertionError("unexpected Skill 74 call: %r" % sub)

def _dispatch(request, label):
    """One real dispatch() against a fake Skill 74; returns (env, db, fake)."""
    tmp = tempfile.mkdtemp(prefix="f2-seam-")
    db = os.path.join(tmp, "spend.db")
    L.init_run(db, "run-" + label, 10_000_000)
    fake = Fake74()
    env = KD.dispatch(
        model="suno-generate", request=request,
        save_dir=os.path.join(tmp, "out"), ledger_db=db, run_id="run-" + label,
        logical_key=label + "-job", attempt_id="att-1", estimated_cost=6,
        prompt="q" * 200, adapter_path=os.path.abspath(__file__),
        runner=fake)
    return env, db, fake

def _ledger_rows(db):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT state, final_outcome FROM jobs WHERE run_id LIKE 'run-%'"
        ).fetchall()
    finally:
        conn.close()

class FullTrackTests(unittest.TestCase):
    """The full-track generation itself always passes."""

    def test_full_track_job_passes(self):
        self.assertEqual(
            S.refuse_partial_suno_job(_receipt(), {
                "kind": "full-track", "generation_id": "gen-1111"}), [])

    def test_full_track_job_passes_before_a_generation_id_exists(self):
        # intake runs BEFORE the generation: no id on the row is fine.
        self.assertEqual(
            S.refuse_partial_suno_job(_receipt(), {"kind": "full-track"}), [])

    def test_full_track_with_empty_generation_id_fails(self):
        errs = S.refuse_partial_suno_job(
            _receipt(), {"kind": "full-track", "generation_id": " "})
        self.assertTrue(
            any(e.startswith(S.PARTIAL_SUNO_JOB) for e in errs), errs)

    def test_intake_seam_allows_full_track(self):
        allowed, refused = S.job_intake(_receipt(), [
            {"kind": "full-track", "generation_id": "gen-1111"}])
        self.assertEqual(len(allowed), 1)
        self.assertEqual(refused, [])

class PartialSliceTests(unittest.TestCase):
    """Any partial shape is refused PARTIAL_SUNO_JOB."""

    def _assert_refused(self, job):
        errs = S.refuse_partial_suno_job(_receipt(), job)
        self.assertTrue(
            any(e.startswith(S.PARTIAL_SUNO_JOB) for e in errs), errs)
        return errs

    def test_partial_slice_refused(self):
        self._assert_refused({
            "kind": "slice", "generation_id": "gen-1111",
            "line_id": "L1", "start_s": 3.2, "end_s": 6.1})

    def test_spoken_patch_refused(self):
        self._assert_refused({
            "kind": "patch", "generation_id": "gen-1111",
            "target": "spoken-take-1"})

    def test_second_bed_refused(self):
        self._assert_refused({"kind": "bed", "generation_id": "gen-1111"})

    def test_unlabelled_kind_refused(self):
        self._assert_refused({"generation_id": "gen-1111"})

    def test_missing_stamp_fails_closed(self):
        for receipt in (None, {}, {"soundtrack": None}):
            errs = S.refuse_partial_suno_job(receipt, {
                "kind": "full-track", "generation_id": "gen-1111"})
            self.assertTrue(
                any(e.startswith(S.PARTIAL_SUNO_JOB) for e in errs), errs)

    def test_wrong_mode_fails_closed(self):
        receipt = _receipt()
        receipt["soundtrack"]["mode"] = "piecemeal"
        errs = S.refuse_partial_suno_job(receipt, {
            "kind": "full-track", "generation_id": "gen-1111"})
        self.assertTrue(
            any(e.startswith(S.PARTIAL_SUNO_JOB) for e in errs), errs)

    def test_malformed_job_fails_closed(self):
        for bad in (None, 7, True, "not-json", "{oops", [1, 2]):
            self._assert_refused(bad)

class RetakeTests(unittest.TestCase):
    """One whole-track retake of a failed take passes; shapes outside it
    do not."""

    def test_whole_track_retake_of_failed_take_passes(self):
        self.assertEqual(
            S.refuse_partial_suno_job(_receipt(), {
                "kind": "whole-track-retake", "generation_id": "gen-2222",
                "retake_of": "gen-1111"}), [])

    def test_retake_missing_retake_of_refused(self):
        errs = S.refuse_partial_suno_job(_receipt(), {
            "kind": "whole-track-retake", "generation_id": "gen-2222"})
        self.assertTrue(
            any(e.startswith(S.PARTIAL_SUNO_JOB) for e in errs), errs)

    def test_retake_of_other_runs_generation_refused(self):
        errs = S.refuse_partial_suno_job(_receipt("gen-1111"), {
            "kind": "whole-track-retake", "generation_id": "gen-2222",
            "retake_of": "gen-9999"})
        self.assertTrue(
            any(e.startswith(S.PARTIAL_SUNO_JOB) for e in errs), errs)

    def test_retake_before_any_primary_generation_refused(self):
        errs = S.refuse_partial_suno_job(
            {"soundtrack": {"mode": S.TRACK_MODE}}, {
                "kind": "whole-track-retake", "generation_id": "gen-2222",
                "retake_of": "gen-1111"})
        self.assertTrue(
            any(e.startswith(S.PARTIAL_SUNO_JOB) for e in errs), errs)

    def test_same_retake_twice_refused(self):
        receipt = _receipt("gen-1111")
        receipt["soundtrack"]["retakes"] = [
            {"generation_id": "gen-2222", "kind": "whole-track",
             "reason": "failed"}]
        errs = S.refuse_partial_suno_job(receipt, {
            "kind": "whole-track-retake", "generation_id": "gen-2222",
            "retake_of": "gen-1111"})
        self.assertTrue(
            any(e.startswith(S.PARTIAL_SUNO_JOB) for e in errs), errs)

    def test_second_retake_after_success_refused(self):
        receipt = _receipt("gen-1111")
        receipt["soundtrack"]["retakes"] = [
            {"generation_id": "gen-2222", "kind": "whole-track",
             "reason": "succeeded"}]
        errs = S.refuse_partial_suno_job(receipt, {
            "kind": "whole-track-retake", "generation_id": "gen-3333",
            "retake_of": "gen-1111"})
        self.assertTrue(
            any(e.startswith(S.PARTIAL_SUNO_JOB) for e in errs), errs)

    def test_intake_seam_splits_allowed_and_refused(self):
        jobs = [
            {"kind": "full-track"},
            {"kind": "slice", "generation_id": "gen-1111", "line_id": "L2"},
            {"kind": "whole-track-retake", "generation_id": "gen-2222",
             "retake_of": "gen-1111"},
        ]
        allowed, refused = S.job_intake(_receipt(), jobs)
        self.assertEqual([j["kind"] for j in allowed],
                         ["full-track", "whole-track-retake"])
        self.assertEqual(len(refused), 1)
        self.assertIn(S.PARTIAL_SUNO_JOB, refused[0]["intake_errors"][0])

    def test_intake_seam_refuses_malformed_rows_without_crashing(self):
        jobs = [
            {"kind": "full-track"},
            None, 7, True, [1, 2], "not-json", "{oops", b"\xff\xfe",
        ]
        allowed, refused = S.job_intake(_receipt(), jobs)
        self.assertEqual(len(allowed), 1)
        self.assertEqual(len(refused), 7)
        for row in refused:
            self.assertIn(S.PARTIAL_SUNO_JOB, row["intake_errors"][0])

    def test_intake_seam_empty_and_none_jobs(self):
        self.assertEqual(S.job_intake(_receipt(), []), ([], []))
        self.assertEqual(S.job_intake(_receipt(), None), ([], []))

class DispatcherSeamTests(unittest.TestCase):
    """The seam is LIVE: the real dispatch() refuses at intake (not dead
    code) and lets the legal shapes through untouched."""

    def test_partial_slice_refused_at_dispatch_intake(self):
        req = _f1_request(_receipt(), card_receipt=_STAMPED_CARD,
                          suno_job={"kind": "slice",
                                    "generation_id": "gen-1111",
                                    "line_id": "L1"})
        env, db, fake = _dispatch(req, "f2-slice")
        self.assertEqual(env["outcome"], "rejected", env)
        self.assertEqual(env["reason_code"], KD_MOD.PARTIAL_SUNO_JOB, env)
        self.assertTrue(env["evidence"]["intake_errors"], env)
        # refused BEFORE the ledger and BEFORE any Skill 74 call
        self.assertEqual(_ledger_rows(db), [], _ledger_rows(db))
        self.assertEqual(fake.calls, [], fake.calls)

    def test_full_track_f1_request_untouched(self):
        req = _f1_request(_receipt(), card_receipt=_STAMPED_CARD)
        env, db, fake = _dispatch(req, "f2-full")
        self.assertNotEqual(env["reason_code"], KD_MOD.PARTIAL_SUNO_JOB, env)
        self.assertEqual(env["outcome"], "ok", env)
        leaves = [c[1] for c in fake.calls]
        self.assertIn("submit", leaves, leaves)

    def test_whole_track_retake_reaches_dispatch(self):
        receipt = _receipt("gen-1111")
        req = _f1_request(
            receipt, card_receipt=_STAMPED_CARD,
            suno_job={"kind": "whole-track-retake",
                      "generation_id": "gen-2222", "retake_of": "gen-1111"})
        env, db, fake = _dispatch(req, "f2-retake")
        self.assertNotEqual(env["reason_code"], KD_MOD.PARTIAL_SUNO_JOB, env)
        self.assertEqual(env["outcome"], "ok", env)

    def test_control_non_f1_run_untouched(self):
        # A run with no F1 soundtrack stamp is out of F2 scope: the exact
        # partial shape that refuses above goes through here (control: proves
        # the refusal above is the F2 gate, not an unrelated block).
        req = {"model": "suno-generate", "input": {"prompt": "p" * 200},
               "card_receipt": _STAMPED_CARD,
               "suno_job": {"kind": "slice", "generation_id": "gen-1111"}}
        env, db, fake = _dispatch(req, "f2-control")
        self.assertNotEqual(env["reason_code"], KD_MOD.PARTIAL_SUNO_JOB, env)
        self.assertEqual(env["outcome"], "ok", env)

def main():  # plain-python3 path, pytest path both fine
    suite = unittest.defaultTestLoader.loadTestsFromModule(
        sys.modules[__name__])
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if res.wasSuccessful() else 1

if __name__ == "__main__":
    sys.exit(main())
