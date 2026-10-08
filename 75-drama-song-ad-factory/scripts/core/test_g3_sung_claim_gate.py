#!/usr/bin/env python3
"""G3-WIRE: the QC gate refuses a PASS sung claim without the detector.

Owner order (Trevor, 2026-10-08 11:35 Part G G3): the G3b singing detector
(core/singing_detector) exists but nothing in QC called it, so a receipt
could still assert "sung 61.0%" from section labels and the gate would
advance it. The gate now enforces detector provenance on every PASS record
whose evidence asserts a sung/first-sung share (SUNG_CLAIM_UNMEASURED,
structural -> BLOCKED: the same record can never pass).

stdlib only, no audio, no numpy (the detector-name cross-check self-skips
when numpy is absent, same as the detector's own suite).

Run: python3 core/test_g3_sung_claim_gate.py
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import qc_gate  # noqa: E402

RUN = "g3-run"
STAGE = "final_edit"
MAKER = "assembler-maker"
REVIEWER = "independent-qc-checker"


def _rec(summary, verdict="PASS", check="audio", check_id="final:audio:x"):
    return {"schema_version": "1.0.0", "check_id": check_id, "run_id": RUN,
            "stage": STAGE, "check": check, "verdict": verdict,
            "evidence": {"summary": summary},
            "checker_version": "1.0.0",
            "reviewer": {"identity": REVIEWER, "session": "s1",
                         "authority": "qc"}}


def _gate(records, required=("audio",)):
    return qc_gate.evaluate(RUN, STAGE, list(records),
                            {r["check_id"]: MAKER for r in records},
                            list(required))


class SungClaimGate(unittest.TestCase):

    # ------------------------------------------------------- claim text ---
    def test_claim_patterns(self):
        for s in ("sung_vocal_guard 1.0.0: SUNG_COVERAGE_OK "
                  "(mode=all_suno, sung_coverage=0.75)",
                  "SUNG=yes(sung 61.0% / spoken 39.0% (labels))",
                  "sung_pct=61.0 spoken_pct=39.0",
                  "FIRST_SUNG=yes(first real singing at 14.0% ...)",
                  "first_sung at 14.0% of runtime"):
            self.assertTrue(qc_gate.sung_claim(s), s)

    def test_non_claim_text(self):
        for s in ("reverb-tail pass: 12 line(s), 0 failure(s)",
                  "pass fixture (export)",
                  "voice-match pass: 4 line(s), 0 failure(s)",
                  "the song sung brightly (no number)"):
            self.assertFalse(qc_gate.sung_claim(s), s)

    def test_provenance_forms(self):
        for s in ("... | detector=singing_detector v2.0.0 "
                  "share_source=measured sung_share=61.0%",
                  "sung 61.0% / spoken 39.0% (singing-detector(vocal-stem))",
                  "measured by the SINGING DETECTOR on the vocal stem"):
            self.assertTrue(qc_gate.sung_claim_measured(s), s)
        for s in ("sung 61.0% / spoken 39.0% (section labels)",
                  "share_source=timing_map (unmeasured)",
                  ""):
            self.assertFalse(qc_gate.sung_claim_measured(s), s)

    # ------------------------------------------------------ gate wiring ---
    def test_pass_claim_without_detector_is_blocked(self):
        rec = _rec("sung_vocal_guard 1.0.0: SUNG_COVERAGE_OK "
                   "(mode=all_suno, sung_coverage=0.75) | "
                   "share_source=timing_map (unmeasured)")
        res = _gate([rec])
        self.assertEqual(res["gate"], "BLOCKED")
        codes = {f["code"] for f in res["failures"]}
        self.assertIn("SUNG_CLAIM_UNMEASURED", codes)
        self.assertEqual(res["repair_scope"], ["final:audio:x"])

    def test_pass_claim_with_detector_passes(self):
        rec = _rec("sung_vocal_guard 1.0.0: SUNG_COVERAGE_OK "
                   "(mode=all_suno, sung_coverage=0.75) | "
                   "detector=singing_detector v2.0.0 share_source=measured "
                   "sung_share=75.0%")
        res = _gate([rec])
        self.assertEqual(res["gate"], "PASS", res)

    def test_pass_claim_naming_detector_form_passes(self):
        """The delivery-checklist summary carries the receipt detector name."""
        rec = _rec("delivery checklist pass: 11/11 measured | "
                   "FIRST_SUNG=yes(first real singing at 14.0% of runtime "
                   "(ACCEPT)); SUNG=yes(sung 61.0% / spoken 39.0% "
                   "(singing-detector(vocal-stem)))",
                   check="delivery_checklist", check_id="delivery-checklist")
        res = _gate([rec], required=("delivery_checklist",))
        self.assertEqual(res["gate"], "PASS", res)

    def test_fail_claim_without_detector_stays_fail(self):
        """FAIL never advances, so provenance is diagnosis, not a gate."""
        rec = _rec("SUNG_COVERAGE_LOW: sung 45.00% of voice time is 12.5 "
                   "points off; redo", verdict="FAIL")
        res = _gate([rec])
        self.assertEqual(res["gate"], "FAIL")
        self.assertNotIn("SUNG_CLAIM_UNMEASURED",
                         {f["code"] for f in res["failures"]})

    def test_non_sung_pass_record_unaffected(self):
        rec = _rec("reverb-tail pass: 12 line(s), 0 failure(s), max 0.012 s")
        self.assertEqual(_gate([rec])["gate"], "PASS")

    def test_self_review_still_refused_before_the_claim_rule(self):
        rec = _rec("sung 61.0% of voice time", verdict="PASS")
        rec["reviewer"]["identity"] = MAKER
        res = _gate([rec])
        self.assertEqual(res["gate"], "BLOCKED")
        self.assertIn("MAKER_SELF_REVIEW",
                      {f["code"] for f in res["failures"]})

    # ------------------------------------------ detector constant parity ---
    def test_gate_names_the_real_detector(self):
        """qc_gate.SUNG_DETECTOR must equal singing_detector.TOOL_NAME.

        Self-skips when numpy is absent (the detector package imports it),
        exactly like the detector's own suite on the CI runner.
        """
        try:
            import singing_detector as SD  # noqa: E402
        except Exception:  # noqa: BLE001 - no numpy on the runner
            self.skipTest("singing_detector not importable (no numpy)")
        self.assertEqual(qc_gate.SUNG_DETECTOR, SD.TOOL_NAME)
        self.assertEqual(SD.SCHEMA_VERSION, "blackceo.singing-detector/v1")
        share = {"detector": SD.TOOL_NAME, "share_source": "measured",
                 "detector_version": SD.TOOL_VERSION}
        self.assertTrue(qc_gate.sung_claim_measured(
            "detector=%s v%s share_source=measured"
            % (share["detector"], share["detector_version"])))


if __name__ == "__main__":
    unittest.main(verbosity=2)
