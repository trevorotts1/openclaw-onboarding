#!/usr/bin/env python3
"""X06: run_takes freezes one outbound snapshot and re-admits it inside the
governor callback on every retry; the saved script election is honoured.
Dual-mode: python3 core/song_dispatch/test_x06_take_admission.py | pytest.
Zero network, zero spend: ``generate`` is a counter."""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
sys.path.insert(0, os.path.join(CORE, "suno_recipe"))

from song_dispatch import song_dispatch as SD   # noqa: E402  the MODULE


def _request():
    return {"model": "ai-music-api/generate", "lyrics": "hello",
            "input": {"duration": 60, "style": "s", "lyrics": "hello"}}


class TakeAdmission(unittest.TestCase):
    def setUp(self):
        self.checks = []
        p = mock.patch.multiple(
            SD, refuse_asr=lambda x: None, judge_take=lambda *a, **k: {},
            _outbound_view=lambda r: {}, _with_shipped_aliases=lambda c: {"x": 1},
            _input_of=lambda r: r.get("input") or {}, _lyrics_of=lambda r: r.get("lyrics") or "")
        p.start(); self.addCleanup(p.stop)
        for obj, name, val in (
                (SD._WF, "max_suno_duration", lambda n: n),
                (SD._R, "check_envelope", lambda r: []),
                (SD._PC, "check_pace_plan", lambda o: []),
                (SD._SCM, "check_pace_style", lambda s, o: []),
                (SD._PC, "pace_provider_leak", lambda r: False),
                (SD._PG, "guard_or_raise", lambda v, c: {"payload": {}}),
                (SD._SA, "script_sha_near", lambda *d: None),
                (SD._SA, "record_near", lambda *d: {"required": True, "status": "approved"}),
                (SD._SA, "check_script_approval",
                 lambda rec, lyr, sha=None: self.checks.append(1))):
            q = mock.patch.object(obj, name, val); q.start(); self.addCleanup(q.stop)

    def run_it(self, gov=None, cap=None, run_dir=None, req=None):
        got = []
        calls = {"gov": 0}

        def kie(call, label, generation=True):
            calls["gov"] += 1
            return gov(call) if gov else call()
        plan = {"delivered_s": 60, "pace_change": {"turns": ["a", "b"]}}
        out = SD.run_takes(req or _request(), plan, lambda r: got.append(r) or [],
                           lambda t: {}, lambda t, r: None, "hello", "hook",
                           cap_cents=cap or SD.GEN_COST_CENTS, cost_cents=SD.GEN_COST_CENTS,
                           kie=kie, run_dir=run_dir)
        return out, got, calls

    def test_exact_snapshot_and_digest(self):
        req = _request()
        out, got, _ = self.run_it(req=req)
        self.assertIn("submitted_digest", out)
        self.assertIsNot(got[0], req)
        self.assertEqual(got[0]["input"]["duration"], 60)

    def test_mutation_during_acquisition_cannot_change_submission(self):
        req = _request()

        def mutating(call):
            req["lyrics"] = "MUTATED"; req["input"]["duration"] = 999
            return call()
        _, got, _ = self.run_it(gov=mutating, req=req)
        self.assertEqual((got[0]["lyrics"], got[0]["input"]["duration"]), ("hello", 60))

    def test_every_retry_rechecks_inside_callback(self):
        _, _, calls = self.run_it(cap=2 * SD.GEN_COST_CENTS)
        self.assertEqual(calls["gov"], 2)
        self.assertEqual(len(self.checks), 3)      # 1 preamble + 2 callback

    def test_saved_yes_with_nonrequiring_record_refuses(self):
        import production_process as PP   # at call time: pytest drops cached skill modules per collector
        with mock.patch.object(SD._SA, "record_near", lambda *d: {"required": False}), \
                mock.patch.object(PP, "current_script_election", lambda d: True):
            with self.assertRaises(SD.DispatchError) as cm:
                self.run_it(run_dir=os.path.join(HERE, "no-such-run"))
        self.assertIn("SCRIPT_APPROVAL_ELECTION_CHANGED", str(cm.exception))

    def test_election_helper(self):
        import production_process as PP
        from script_approval import card_answers as CA
        for row, want in (({"n": 1}, True), ({"n": 2}, False)):
            with mock.patch.object(CA, "load", lambda d, r=row: {"state": CA.OK, "by_id": {"script": r}}):
                self.assertIs(PP.current_script_election("/x"), want)
        with mock.patch.object(CA, "load", lambda d: {"state": CA.MISSING, "by_id": {}}):
            self.assertIsNone(PP.current_script_election("/x"))


if __name__ == "__main__":
    unittest.main()
