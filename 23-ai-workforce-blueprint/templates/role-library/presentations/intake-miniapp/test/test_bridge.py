#!/usr/bin/env python3
"""Offline gate for intake_bridge.py pure logic.

Proves the bridge builds the correct deck-intake-driver.py commands and the
correct signature record — without any network or subprocess. The bridge is
just a replay layer over the existing driver; these tests pin that contract.
Run: python3 test/test_bridge.py
"""
from __future__ import annotations

import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "bridge"))

import intake_bridge as br  # noqa: E402

DRIVER = "/box/23-ai-workforce-blueprint/scripts/deck-intake-driver.py"
RUN = "/box/runs/RUN1"


class TestBridge(unittest.TestCase):
    def test_answer_cmd_passes_value_as_one_arg(self):
        cmd = br.driver_answer_cmd(DRIVER, RUN, "grounded_content", "The Momentum Method")
        self.assertEqual(cmd[-3:], ["--answer", "grounded_content", "The Momentum Method"])
        self.assertIn("--run-dir", cmd)
        self.assertIn(RUN, cmd)
        # The value is a single argv element (no shell splitting) — injection-safe.
        self.assertEqual(cmd.count("The Momentum Method"), 1)

    def test_next_and_complete_cmds(self):
        self.assertEqual(br.driver_next_cmd(DRIVER, RUN)[-1], "--next")
        self.assertEqual(br.driver_complete_cmd(DRIVER, RUN)[-1], "--complete")

    def test_signature_record_cmd(self):
        cmd = br.driver_signature_record_cmd(DRIVER, RUN, "/box/runs/RUN1/rec.json")
        self.assertIn("--signature", cmd)
        self.assertEqual(cmd[-2:], ["--record", "/box/runs/RUN1/rec.json"])

    def test_build_sp_record_shape(self):
        answers = {f"q{i}": f"answer {i}" for i in range(1, 9)}
        answers["frame_selection"] = "Rulebook"
        rec = br.build_sp_record(answers, answers.get("frame_selection"))
        self.assertEqual(set(rec["answers"].keys()), {f"q{i}" for i in range(1, 9)})
        self.assertTrue(rec["asked_all_at_once"])
        self.assertFalse(rec["one_question_per_turn"])
        self.assertEqual(rec["signature_frame"], "rulebook")  # normalized lower
        self.assertEqual(rec["offer_token_ledger"], ["answer 7"])  # q7 seeds the ledger

    def test_build_sp_record_empty_offer_when_q7_missing(self):
        rec = br.build_sp_record({"q1": "t"}, "vault")
        self.assertEqual(rec["offer_token_ledger"], [])
        self.assertEqual(rec["signature_frame"], "vault")

    def test_is_complete(self):
        self.assertTrue(br.is_complete("complete", None))
        self.assertTrue(br.is_complete("open", {"complete": True}))
        self.assertFalse(br.is_complete("open", {"complete": False}))
        self.assertFalse(br.is_complete("open", None))

    def test_driver_path_walks_up_or_falls_back(self):
        # With an explicit override it is returned resolved.
        p = br._driver_path("/tmp/x/deck-intake-driver.py")
        self.assertTrue(str(p).endswith("deck-intake-driver.py"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
