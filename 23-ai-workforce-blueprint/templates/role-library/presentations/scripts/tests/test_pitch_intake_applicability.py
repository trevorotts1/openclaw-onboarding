"""Driver-level applicability: explicit informational selection is typed."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRIVER = HERE.parent / "deck-intake-driver.py"


def _answer(run_dir: Path, qid: str, text: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DRIVER), "--run-dir", str(run_dir),
         "--answer", qid, text], capture_output=True, text=True, timeout=30)


def _ledger(run_dir: Path) -> dict:
    return json.loads((run_dir / "working" / "interview" / "intake_ledger.json").read_text())


def test_explicit_informational_selection_skips_method_and_timing_without_fake_values(tmp_path):
    run_dir = tmp_path / "run"
    assert _answer(run_dir, "deck_type_source", "presentation_type: from_scratch; pitch_included: false").returncode == 0
    assert _answer(run_dir, "grounding_and_method", "OpenClaw operations").returncode == 0
    assert _answer(run_dir, "promise_objection_timing", "A clear overview").returncode == 0
    entries = _ledger(run_dir)["entries"]
    assert entries["pitch_included"]["value"] is False
    assert entries["named_methodology"]["skipped"] is True
    assert entries["time_to_result"]["skipped"] is True

    complete = subprocess.run(
        [sys.executable, str(DRIVER), "--run-dir", str(run_dir), "--complete"],
        capture_output=True, text=True, timeout=30)
    assert complete.returncode == 0, complete.stderr
    intake = json.loads((run_dir / "working" / "copy" / "intake.json").read_text())
    assert intake["pitch_included"] is False
    assert "named_methodology" not in intake
    assert "time_to_result" not in intake
    assert intake["grounded_content"] == "OpenClaw operations"
    assert intake["transformation_promise"] == "A clear overview"


def test_commercial_selection_keeps_method_and_timing_requirements(tmp_path):
    run_dir = tmp_path / "run"
    assert _answer(run_dir, "deck_type_source", "presentation_type: from_scratch; pitch_included: true").returncode == 0
    assert _answer(run_dir, "grounding_and_method", "grounded_content: Guide; named_methodology: Three Steps").returncode == 0
    assert _answer(run_dir, "promise_objection_timing", "transformation_promise: Better; primary_objection: Time; time_to_result: 8 weeks").returncode == 0
    entries = _ledger(run_dir)["entries"]
    assert entries["pitch_included"]["value"] is True
    assert entries["named_methodology"]["value"] == "Three Steps"
    assert entries["time_to_result"]["value"] == "8 weeks"


def test_signature_cannot_select_pitchless_and_phrase_alone_does_not_skip(tmp_path):
    run_dir = tmp_path / "run"
    assert _answer(run_dir, "presentation_type", "signature").returncode == 0
    rejected = _answer(run_dir, "pitch_included", "false")
    assert rejected.returncode != 0
    assert "require pitch_included:true" in rejected.stdout

    phrase_only = tmp_path / "phrase-only"
    assert _answer(phrase_only, "presentation_type", "from_scratch").returncode == 0
    assert _answer(phrase_only, "goal_cta_feeling", "Teach the department without a pitch").returncode == 0
    assert "pitch_included" not in _ledger(phrase_only)["entries"]
