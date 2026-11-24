#!/usr/bin/env python3
"""SWB-300 item b1: the wireframe guide verifier checks each section's export.receipt_sha256.

_verify_wireframe_stage used to verify the slices, the stitch and the flat export receipt but never the
receipt hash each production-record section cites. It now uses the same helper as the final-mockups
panel path (build_hybrid_board._stale_export_claim). Negative twins: zeros, and the receipt hash of
another stage's export. Both refuse, write nothing, compose no board.
"""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

import build_hybrid_board as bhb  # noqa: E402
import test_hybrid_board_refresh as base  # noqa: E402
import test_swb290_guide_repin as gr  # noqa: E402


class GuideReceiptTests(gr.GuideBase):
    def wf_record(self):
        return json.loads((self.wf / "production-record.json").read_text())

    def test_a_correct_receipt_hash_is_recorded_and_passes(self):
        rec = self.wf_record()
        hashes = {s["export"]["receipt_sha256"] for s in rec["sections"]}
        self.assertEqual(len(hashes), 1)
        self.assertEqual(self.refresh().returncode, 0)

    def test_zeros_in_receipt_sha256_are_refused(self):
        self.edit(self.wf / "production-record.json",
                  lambda d: d["sections"][0]["export"].__setitem__("receipt_sha256", "0" * 64))
        self.assert_refused(self.refresh(), "the production record cites export receipt 000000000000")

    def test_a_receipt_of_another_stage_is_refused(self):
        other = json.loads((self.fm / "export-receipt.json").read_text())["receipt_sha256"]
        mine = self.wf_record()["sections"][0]["export"]["receipt_sha256"]
        self.assertNotEqual(other, mine)
        self.edit(self.wf / "production-record.json",
                  lambda d: [s["export"].__setitem__("receipt_sha256", other) for s in d["sections"]])
        self.assert_refused(self.refresh(), "the record is stale")

    def test_the_two_paths_share_one_helper(self):
        rec = {"export": {"receipt_sha256": "a" * 64}}
        self.assertIsNone(bhb._stale_export_claim("x", rec, "a" * 64))
        self.assertIn("is stale", bhb._stale_export_claim("x", rec, "b" * 64))
        import inspect
        self.assertIn("_stale_export_claim", inspect.getsource(bhb._verify_viewport))
        self.assertIn("_stale_export_claim", inspect.getsource(bhb._verify_wireframe_stage))


if __name__ == "__main__":
    unittest.main()
