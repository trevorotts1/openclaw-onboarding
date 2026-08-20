#!/usr/bin/env python3
"""test_pitch_anti_fab_intake_questions.py — F11 regression pin.

GROUND TRUTH THIS FILE PINS
----------------------------
pitch_engines_check.chk_branded_method / chk_time_to_result read
`intake.json`'s TRUE ROOT `named_methodology` / `time_to_result` keys
directly (`(intake or {}).get("named_methodology")`, `intake.get(
"time_to_result")`) -- deliberate anti-fabrication design: the copywriter
must never be able to invent a method name or a delivery timeline, only the
CLIENT can supply them. Before this fix, `intake/deck-intake-questions.json`
never asked either question, so AF-NO-BRANDED-METHOD and AF-NO-TIME-TO-RESULT
auto-failed EVERY deck, unconditionally, forever, and no amount of copy
re-authoring could clear them (the gate was right; the interview was
incomplete).

This file proves, mechanically, in order:
  1. the question bank now carries both questions, unconditional (no
     ask_if -- the pitch checks run regardless of QUICK/IN-DEPTH), required,
     block_gate.
  2. running the REAL, unmodified deck-intake-driver.py end-to-end (the
     sanctioned chat intake path) against those two question ids produces a
     working/copy/intake.json whose TRUE ROOT carries `named_methodology` /
     `time_to_result` -- not nested under deck_brief or pre_presentation_capture.
  3. pitch_engines_check.chk_branded_method / chk_time_to_result, called for
     real (not mocked) against that driver-produced intake.json plus a
     synthetic arc-tagged slides_copy.md, no longer raise
     AF-NO-BRANDED-METHOD / AF-NO-TIME-TO-RESULT on the anti-fabrication
     clause -- and DOES still raise them when the two fields are absent
     (proving the test can actually detect the fault it pins, not just
     rubber-stamp a pass).

Unit-level, no kie.ai spend, no renderer, no network. Flat file inside
tests/, manages its own import path -- matching every sibling in this
directory (test_upsell_intake_shape.py, test_upsell_verifiers.py).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
PRES_DEPT = SCRIPTS.parent
BANK_PATH = PRES_DEPT / "intake" / "deck-intake-questions.json"
DRIVER_PATH = SCRIPTS / "deck-intake-driver.py"

sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

import pitch_engines_check as pec  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _load_bank() -> dict:
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _question(bank: dict, qid: str) -> dict:
    for q in bank.get("questions", []):
        if q.get("id") == qid:
            return q
    raise AssertionError(f"question id {qid!r} not found in {BANK_PATH}")


def _run_driver(run_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DRIVER_PATH), "--run-dir", str(run_dir), *args],
        capture_output=True, text=True,
    )


def _drive_minimal_intake(run_dir: Path, named_methodology: str | None,
                          time_to_result: str | None) -> dict:
    """Drive the REAL deck-intake-driver.py CLI (never a hand-authored
    intake.json) through presentation_type + the two anti-fab questions
    (when given), then --complete. Returns the written intake.json.
    """
    r = _run_driver(run_dir, "--answer", "presentation_type", "from_scratch")
    assert r.returncode == 0, f"--answer presentation_type failed: {r.stdout}\n{r.stderr}"
    if named_methodology is not None:
        r = _run_driver(run_dir, "--answer", "named_methodology", named_methodology)
        assert r.returncode == 0, f"--answer named_methodology failed: {r.stdout}\n{r.stderr}"
    if time_to_result is not None:
        r = _run_driver(run_dir, "--answer", "time_to_result", time_to_result)
        assert r.returncode == 0, f"--answer time_to_result failed: {r.stdout}\n{r.stderr}"
    r = _run_driver(run_dir, "--complete")
    assert r.returncode == 0, f"--complete failed: {r.stdout}\n{r.stderr}"
    intake_path = run_dir / "working" / "copy" / "intake.json"
    assert intake_path.is_file(), "driver did not write working/copy/intake.json"
    return json.loads(intake_path.read_text(encoding="utf-8"))


ARC_COPY_WITH_METHOD_AND_EXPECTATION = (
    "<!-- ARC: NAMED_METHOD -->\n"
    "Introducing the Three-Move Pipeline System.\n\n"
    "<!-- ARC: EXPECTATION -->\n"
    "Most clients see their first shift within 2 weeks, and the full "
    "result lands by week 8.\n"
)


# ---------------------------------------------------------------------------
# 1. the bank itself
# ---------------------------------------------------------------------------
class TestBankHasAntiFabricationQuestions:
    def test_named_methodology_question_present_and_unconditional(self):
        bank = _load_bank()
        q = _question(bank, "named_methodology")
        assert q.get("storeOn") == "NAMED_METHODOLOGY"
        assert q.get("required") is True
        assert q.get("block_gate") is True
        assert "ask_if" not in q, (
            "named_methodology must be unconditional -- pitch_engines_check "
            "runs regardless of QUICK/IN-DEPTH (standard_mode), so gating "
            "this question behind IN-DEPTH would leave QUICK-mode decks "
            "auto-failing exactly as before this fix.")
        assert "conditional_on" not in q

    def test_time_to_result_question_present_and_unconditional(self):
        bank = _load_bank()
        q = _question(bank, "time_to_result")
        assert q.get("storeOn") == "TIME_TO_RESULT"
        assert q.get("required") is True
        assert q.get("block_gate") is True
        assert "ask_if" not in q
        assert "conditional_on" not in q

    def test_storeTarget_entries_present(self):
        bank = _load_bank()
        store_target = bank.get("storeTarget", {})
        assert store_target.get("NAMED_METHODOLOGY") == "deck_brief.NAMED_METHODOLOGY"
        assert store_target.get("TIME_TO_RESULT") == "deck_brief.TIME_TO_RESULT"


# ---------------------------------------------------------------------------
# 2 + 3. end-to-end through the REAL driver + the REAL checker
# ---------------------------------------------------------------------------
class TestDriverAndPitchCheckIntegration:
    def test_driver_writes_true_root_flat_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            intake = _drive_minimal_intake(
                run_dir, "Three-Move Pipeline System", "8 weeks")
            assert intake.get("named_methodology") == "Three-Move Pipeline System"
            assert intake.get("time_to_result") == "8 weeks"

    def test_pitch_check_anti_fabrication_clause_passes_when_answered(self):
        """The exact consumer (pitch_engines_check.py) sees the client's own
        answer and does NOT auto-fail AF-NO-BRANDED-METHOD / AF-NO-TIME-TO-RESULT."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            intake = _drive_minimal_intake(
                run_dir, "Three-Move Pipeline System", "8 weeks")
            run = {
                "intake": intake,
                "slides_copy": ARC_COPY_WITH_METHOD_AND_EXPECTATION,
                "method_approval": None,
            }
            method_fails = pec.chk_branded_method(run)
            time_fails = pec.chk_time_to_result(run)
            method_codes = {f.get("code") for f in method_fails if "code" in f}
            time_codes = {f.get("code") for f in time_fails if "code" in f}
            assert "AF-NO-BRANDED-METHOD" not in method_codes
            assert "AF-METHOD-FABRICATED" not in method_codes
            assert "AF-NO-TIME-TO-RESULT" not in time_codes

    def test_pitch_check_still_fails_when_fields_absent(self):
        """NON-VACUOUSNESS PROOF: this test's own machinery can still detect
        the fault it pins. Drive the SAME real driver but withhold the two
        answers (the pre-fix state, question bank aside) -- the anti-fab
        checks must still fire, proving test_pitch_check_anti_fabrication_
        clause_passes_when_answered above is a real assertion, not a tautology.
        """
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            intake = _drive_minimal_intake(run_dir, None, None)
            assert "named_methodology" not in intake
            assert "time_to_result" not in intake
            run = {
                "intake": intake,
                "slides_copy": ARC_COPY_WITH_METHOD_AND_EXPECTATION,
                "method_approval": None,
            }
            method_fails = pec.chk_branded_method(run)
            time_fails = pec.chk_time_to_result(run)
            method_codes = {f.get("code") for f in method_fails if "code" in f}
            time_codes = {f.get("code") for f in time_fails if "code" in f}
            assert "AF-METHOD-FABRICATED" in method_codes, (
                "a NAMED_METHOD beat with no client-supplied name and no "
                "owner_approved record must still be flagged as fabricated")
            assert "AF-NO-TIME-TO-RESULT" in time_codes, (
                "an EXPECTATION beat with a duration token but no "
                "intake.time_to_result must still be flagged")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
