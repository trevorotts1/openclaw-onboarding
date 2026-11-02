#!/usr/bin/env python3
"""X07: one dispatch mode family per run, persisted before any paid call.

Offline: no network, no provider. Run: python3 test_x07_mode_persist.py
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, os.path.join(CORE, "intake_preflight")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from song_choices import song_choices as SC          # noqa: E402
from intake_preflight import factory as F            # noqa: E402


class X07ModePersist(unittest.TestCase):
    def setUp(self):
        self.run = tempfile.mkdtemp(prefix="x07-mode-")
        self.addCleanup(shutil.rmtree, self.run, True)
        self.path = os.path.join(self.run, "music", "dispatch-mode.json")

    def _doc(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_first_selection_persists_and_survives_restart(self):
        SC._record_mode(self.run, "umbrella")
        self.assertEqual(self._doc(), {"mode": "umbrella", "family": "umbrella"})
        self.assertEqual(SC._record_mode(self.run, "umbrella"), "umbrella")  # resume
        self.assertEqual(os.listdir(os.path.dirname(self.path)),
                         ["dispatch-mode.json"])          # no temp litter

    def test_other_family_refused_both_ways_record_unchanged(self):
        SC._record_mode(self.run, "umbrella")
        with self.assertRaises(SC.ChoiceError) as cm:
            SC._record_mode(self.run, "unit:WW-001")
        self.assertIn("mode family", str(cm.exception))
        self.assertEqual(self._doc()["family"], "umbrella")
        run2 = tempfile.mkdtemp(prefix="x07-mode-")
        self.addCleanup(shutil.rmtree, run2, True)
        SC._record_mode(run2, "unit:WW-001")
        SC._record_mode(run2, "unit:WW-002")              # documented 3-unit flow
        with self.assertRaises(SC.ChoiceError):
            SC._record_mode(run2, "umbrella")

    def test_corrupt_record_refuses_instead_of_reopening_a_mode(self):
        os.makedirs(os.path.dirname(self.path))
        for junk in ("{not json", "[]", "{}", '{"family": "weird"}'):
            with open(self.path, "w") as f:
                f.write(junk)
            for mode in ("umbrella", "unit:WW-001"):
                with self.assertRaises(SC.ChoiceError, msg=(junk, mode)) as cm:
                    SC._record_mode(self.run, mode)
                self.assertIn("unreadable", str(cm.exception))
            with open(self.path) as f:
                self.assertEqual(f.read(), junk)            # never overwritten

    def test_lost_first_selection_race_is_refused_not_overwritten(self):
        """Deterministic: the opposite family wins between our check and our link."""
        real_link = os.link

        def winner_first(src, dst):
            os.link = real_link
            SC._record_mode(self.run, "unit:WW-001")        # the racing winner
            return real_link(src, dst)                      # -> FileExistsError

        os.link = winner_first
        self.addCleanup(setattr, os, "link", real_link)
        with self.assertRaises(SC.ChoiceError) as cm:
            SC._record_mode(self.run, "umbrella")
        self.assertIn("mode family", str(cm.exception))
        self.assertEqual(self._doc()["family"], "unit")

    def test_concurrent_opposite_first_selections_yield_one_winner(self):
        for trial in range(20):
            run = tempfile.mkdtemp(prefix="x07-race-")
            self.addCleanup(shutil.rmtree, run, True)
            gate, res = threading.Barrier(2), {}

            def go(mode):
                gate.wait()
                try:
                    res[mode] = SC._record_mode(run, mode)
                except SC.ChoiceError as exc:
                    res[mode] = exc

            ts = [threading.Thread(target=go, args=(m,))
                  for m in ("umbrella", "unit:WW-001")]
            [t.start() for t in ts]
            [t.join() for t in ts]
            won = [m for m, r in res.items() if not isinstance(r, Exception)]
            self.assertEqual(len(won), 1, (trial, res))
            with open(os.path.join(run, "music", "dispatch-mode.json")) as f:
                self.assertEqual(json.load(f)["mode"], won[0])

    def test_next_selector_refuses_the_other_family_without_a_command(self):
        SC.init(self.run, True)
        self.assertFalse(F._song_choices_next(self.run, orchestrated=True).get("refused"))
        SC._record_mode(self.run, "umbrella")
        other = F._song_choices_next(self.run, orchestrated=True)
        self.assertTrue(other["refused"], other)
        self.assertEqual(other["reason_code"], "MODE_CONFLICT")
        self.assertEqual((other["command"], other["umbrella_command"],
                          other["selected_command"]), ("", "", ""))
        same = F._song_choices_next(self.run, orchestrated=False)
        self.assertFalse(same.get("refused"))
        self.assertTrue(same["command"])

    def test_removal_control_without_the_write_nothing_is_refused(self):
        real = SC._record_mode
        SC._record_mode = lambda run_dir, mode: mode
        self.addCleanup(setattr, SC, "_record_mode", real)
        SC._record_mode(self.run, "umbrella")
        self.assertFalse(os.path.exists(self.path))
        self.assertIsNone(SC.mode_refusal(self.run, "unit:WW-001"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
