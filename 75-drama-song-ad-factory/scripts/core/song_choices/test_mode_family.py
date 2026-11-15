#!/usr/bin/env python3
"""C11: one run dispatches in exactly ONE mode family (umbrella XOR orchestrated unit).

Real song_choices.cmd_generate; only I/O boundaries stubbed (no provider, no network, no ledger).
Run: python3 -m pytest core/song_choices/test_mode_family.py
"""
import json
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from song_choices import song_choices as SC  # noqa: E402

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "variants.json"), encoding="utf-8") as _f:
    ROWS = json.load(_f)["rnb-flow"]


def _call(run_dir, variant="", unit_id=""):
    ns = types.SimpleNamespace(run_dir=run_dir, request="req.json", variant=variant,
                               unit_id=unit_id, ledger="l.sqlite3", run_id="rid")
    return SC.cmd_generate(ns, generate=lambda v, r: [], measure=lambda t: None,
                           save=lambda v, t, rc: True)


class ModeFamily(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(SC, k) for k in
                       ("_load_request", "_hook_text", "build_requests", "_sheet_lyric_words", "run_unit", "generate_choices")}
        SC._load_request = lambda *a, **k: {
            "style_id": "rnb-flow", "sheet": [], "sheet_text": "s", "client_text": "c", "title": "t",
            "length_s": 180, "vocal_gender": "f", "hook_plan": [], "pace_plan": [], "run_authorities": {}}
        SC._hook_text = lambda spec: "hook"
        SC.build_requests = lambda *a, **k: [(dict(r), None) for r in ROWS]
        SC._sheet_lyric_words = lambda spec: "w"
        SC.run_unit = lambda reqs, unit_id=None, variant_id=None, **kw: [
            {"attempts": 1, "n": SC._select_one(reqs, unit_id or None, variant_id or None) + 1}]
        SC.generate_choices = lambda reqs, plan=None, **kw: [{"attempts": 1, "n": i + 1} for i, _ in enumerate(reqs)]
        self.tmp = tempfile.TemporaryDirectory()
        self.run = self.tmp.name
        os.makedirs(os.path.join(self.run, "song-choices"))
        with open(os.path.join(self.run, "song-choices", "state.json"), "w", encoding="utf-8") as f:
            json.dump({"required": True, "offered": {}}, f)

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(SC, k, v)
        self.tmp.cleanup()

    def test_umbrella_then_unit_refused(self):
        _call(self.run)
        with self.assertRaises(Exception) as cm:
            _call(self.run, unit_id="WW-002")
        self.assertIn("exactly ONE", str(cm.exception))

    def test_unit_then_umbrella_refused(self):
        _call(self.run, unit_id="WW-001")
        with self.assertRaises(Exception):
            _call(self.run)

    def test_three_units_share_one_run_dir(self):
        for u in ("WW-001", "WW-002", "WW-003"):
            _call(self.run, unit_id=u)

    def test_unit_id_and_variant_label_agree(self):
        _call(self.run, unit_id="WW-001")
        _call(self.run, variant="polished-modern")

    def test_same_mode_repeat_allowed(self):
        _call(self.run)
        _call(self.run)


if __name__ == "__main__":
    unittest.main()
