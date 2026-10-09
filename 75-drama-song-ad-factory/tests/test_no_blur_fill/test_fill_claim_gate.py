#!/usr/bin/env python3
"""DEL-14 refusal gate: the QC gate refuses a blur-fill claim, always.

Owner order (Trevor, 2026-10-09 13:05 mass swarm item C via relita; 13:31
plan authorization, PKG-05): full height is reached by crop-in of the source
frame only. A PASS record for the no_blur_fill check whose evidence names a
blur fill is refused outright as FILL_CLAIM_MEASURED (structural -> BLOCKED:
the same record can never pass; repair means a new crop-in render).

The fill scanner lives in two places on purpose — qc_gate (stdlib, importable
on a partial tree) and no_blur_fill (the proof copy of the render path) — and this suite
asserts the two agree byte-for-byte, same pattern as the G3 detector-parity
rule in core/test_g3_sung_claim_gate.py.

Run: python3 tests/test_no_blur_fill/test_fill_claim_gate.py
  (or python3 -m pytest tests/test_no_blur_fill/ -q)
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

qc_gate = common.qc_gate
SF = common.SF


class FillClaimScanner(unittest.TestCase):
    CLAIMS = (
        "gblur=sigma=30 over the padded frame",
        "BLUR_FILL_REFUSED: filter chain carries gblur",
        "edge-sampled backdrop with gblur sigma=30",
        "duplicated blurred strip down the left edge",
        "gaussian-filled background behind the subject",
        "a blurred mask backdrop at 240px",
        "render used boxblur on the pad band",
        "alphamerge mask overlaid on the stretched fill",
    )
    NOT_CLAIMS = (
        "no blur fill; crop-in path",
        "never a blur fill or blurred mask",
        "blur fill is never used",
        "crop-in full height, no blur fill used",
        "without blur fill, crop-in only",
        "video_still_fill 1.0.0: CROP_IN_OK (fit=crop-in, zoom=1.500, "
        "full height 1080x1920)",
        "fill=none",
        "reverb-tail pass: 12 line(s), 0 failure(s)",
        "NONE",
        "",
    )

    def test_gate_and_module_scanners_agree_on_claims(self):
        for s in self.CLAIMS:
            self.assertTrue(qc_gate.fill_claim(s), s)
            self.assertTrue(SF.fill_claim(s), s)

    def test_gate_and_module_scanners_agree_on_non_claims(self):
        for s in self.NOT_CLAIMS:
            self.assertFalse(qc_gate.fill_claim(s), s)
            self.assertFalse(SF.fill_claim(s), s)

    def test_non_string_is_not_a_claim(self):
        self.assertFalse(qc_gate.fill_claim(None))
        self.assertFalse(SF.fill_claim(None))

    def test_detectors_share_one_name(self):
        self.assertEqual(qc_gate.FILL_CLAIM_DETECTOR, "fill_claim")
        self.assertEqual(SF.FILL_CLAIM_DETECTOR, qc_gate.FILL_CLAIM_DETECTOR)

    def test_scanner_source_is_byte_identical_across_modules(self):
        """The block from FILL_CLAIM_DETECTOR through fill_claim() is the
        same bytes in both modules, so the gate and the render path can
        never drift apart."""
        def block(path):
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            start = text.index("FILL_CLAIM_DETECTOR = ")
            end = text.index("def fill_claim(")
            fn_end = text.index("\n\n\n", end)
            return text[start:fn_end]
        gate_src = os.path.join(common.CORE, "qc_gate.py")
        fill_src = os.path.join(common.CORE, "no_blur_fill", "still_fill.py")
        self.assertEqual(block(gate_src), block(fill_src))


class RefusalGate(unittest.TestCase):
    def test_no_blur_fill_is_a_registered_check(self):
        self.assertIn("no_blur_fill", qc_gate.CHECKS)

    def test_pass_claiming_blur_fill_is_blocked(self):
        """RED: a PASS whose evidence names a blur fill can never pass."""
        res = common.gate([common.qc_record(
            "BLUR_FILL_REFUSED: gblur=sigma=30 fill kept at full height")])
        self.assertEqual(res["gate"], "BLOCKED", res)
        self.assertIn("FILL_CLAIM_MEASURED", common.codes(res))
        self.assertEqual(res["repair_scope"], [common.RECORD_ID])

    def test_pass_on_crop_in_path_passes(self):
        """GREEN: the crop-in path's PASS summary advances the stage."""
        res = common.gate([common.qc_record(
            "video_still_fill 1.0.0: CROP_IN_OK (fit=crop-in, zoom=1.500, "
            "full height 1080x1920)")])
        self.assertEqual(res["gate"], "PASS", res)

    def test_fail_verdict_with_blur_text_stays_plain_fail(self):
        """FAIL never advances anyway; diagnosis is not a second verdict."""
        res = common.gate([common.qc_record(
            "gblur=sigma=30 was used; redo the shot", verdict="FAIL")])
        self.assertEqual(res["gate"], "FAIL")
        self.assertNotIn("FILL_CLAIM_MEASURED", common.codes(res))

    def test_unavailable_still_blocks(self):
        res = common.gate([common.qc_record(
            "render probe unavailable", verdict="UNAVAILABLE")])
        self.assertEqual(res["gate"], "BLOCKED")
        self.assertIn("UNAVAILABLE_MANDATORY", common.codes(res))

    def test_claim_rule_binds_the_no_blur_fill_check(self):
        """Another check's PASS is judged by its own rules (G3 binds sung
        claims; DEL-14 binds the no_blur_fill record)."""
        rec = common.qc_record("gblur=sigma=30 fill kept",
                               check="video", check_id="final:video:x")
        res = common.gate([rec], required=("video",))
        self.assertEqual(res["gate"], "PASS", res)
        self.assertNotIn("FILL_CLAIM_MEASURED", common.codes(res))

    def test_self_review_is_still_refused_first(self):
        rec = common.qc_record("no blur fill; crop-in path")
        rec["reviewer"]["identity"] = common.MAKER
        res = common.gate([rec])
        self.assertEqual(res["gate"], "BLOCKED")
        self.assertIn("MAKER_SELF_REVIEW", common.codes(res))


if __name__ == "__main__":
    unittest.main(verbosity=2)
