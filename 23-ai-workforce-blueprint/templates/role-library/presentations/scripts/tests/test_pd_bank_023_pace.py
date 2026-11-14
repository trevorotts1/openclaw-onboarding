#!/usr/bin/env python3
"""test_pd_bank_023_pace.py -- PD-023: one speaking-pace default.

WHAT THIS PINS
--------------
The department states ONE pace vocabulary and ONE blank-WPM derivation:

  * the merged `audio_settings` row asks `standard`, `teaching`,
    `high-energy`, with the exact client copy, and keeps `"default": 140`;
  * its `target_wpm` note reads `blank WPM derives: default=140,
    medium=150, fast=160`;
  * `question_sequence.py` carries the old words `default`, `medium`,
    `fast` as aliases and projects them with the pace question;
  * the REAL driver CLI derives 140 for `standard`, 130 for `teaching`,
    155 for `high-energy`, and still accepts `default`.

A1 of the unit is the last point: the driver is driven as a real child
interpreter through its real CLI, exactly as the interview app drives it.

House style: flat file in tests/, direct calls, no network, no spend, no
media dependency (this file must never skip).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
PRESENTATIONS = SCRIPTS.parent
BANK_PATH = PRESENTATIONS / "intake" / "deck-intake-questions.json"
DRIVER = SCRIPTS / "deck-intake-driver.py"

PACE_PROMPT = (
    "How fast should the talk be spoken? Standard (about 140 words a minute), "
    "slower teaching pace (about 130), or high energy (about 155).")
NEW_VALUES = ["standard", "teaching", "high-energy"]
OLD_ALIASES = {"default": "standard", "medium": "teaching",
               "fast": "high-energy"}
NOTE = "blank WPM derives: default=140, medium=150, fast=160"


def _bank() -> dict:
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _audio_row() -> dict:
    return [q for q in _bank()["questions"] if q["id"] == "audio_settings"][0]


def _pace_annotation() -> dict:
    return _audio_row()["subfields"]["speech_speed_preference"]


def _sequencer():
    if str(PRESENTATIONS / "intake") not in sys.path:
        sys.path.insert(0, str(PRESENTATIONS / "intake"))
    import question_sequence
    return question_sequence


def test_bank_asks_the_one_pace_vocabulary():
    pace = _pace_annotation()
    assert pace["enum"] == NEW_VALUES, pace["enum"]
    assert pace["default"] == "standard", pace["default"]
    assert pace["question"]["prompt"] == PACE_PROMPT
    assert pace["question"]["allowed_values"] == NEW_VALUES
    assert pace["aliases"] == OLD_ALIASES


def test_bank_keeps_the_blank_wpm_default_and_note():
    sub = _audio_row()["subfields"]
    assert sub["target_wpm"]["default"] == 140, sub["target_wpm"]["default"]
    assert sub["target_wpm"]["note"] == NOTE, sub["target_wpm"]["note"]


def test_sequencer_projects_the_alias_map_and_normalizes():
    qs = _sequencer()
    projected = {q["id"]: q for q in qs.atomic_questions(_bank())}
    q = projected["speech_speed_preference"]
    assert q["allowed_values"] == NEW_VALUES, q["allowed_values"]
    assert q["prompt"] == PACE_PROMPT
    assert q["aliases"] == OLD_ALIASES, q["aliases"]
    for old, new in OLD_ALIASES.items():
        assert qs.normalize_pace(old) == new, old
    assert qs.normalize_pace("High Energy") == "high-energy"
    assert qs.normalize_pace("teaching") == "teaching"


def _drive(run_dir: Path, word: str) -> dict:
    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(DRIVER), "--run-dir", str(run_dir), *args],
            capture_output=True, text=True, timeout=180, cwd=str(PRESENTATIONS))

    r = run("--answer", "presentation_type", "from_scratch")
    assert r.returncode == 0, f"presentation_type: {r.stdout}\n{r.stderr}"
    r = run("--answer", "audio_settings", f"speech_speed_preference: {word}")
    assert r.returncode == 0, f"{word}: {r.stdout}\n{r.stderr}"
    r = run("--complete")
    assert r.returncode == 0, f"--complete: {r.stdout}\n{r.stderr}"
    return json.loads(
        (run_dir / "working" / "copy" / "intake.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("word,wpm", [
    ("standard", 140),
    ("teaching", 130),
    ("high-energy", 155),
    ("default", 140),
])
def test_driver_derives_the_one_pace_default(tmp_path, word, wpm):
    intake = _drive(tmp_path, word)
    assert intake["target_wpm"] == wpm, (word, intake.get("target_wpm"))
