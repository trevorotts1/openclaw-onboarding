#!/usr/bin/env python3
"""PD-016 -- the frame question uses the approved wording.

Acceptance row A1 of unit PD-016 (01-BUILD-SPEC.md, lane FL02, Severe finding
PD-016). Driven at the subprocess level against the REAL deck-intake-driver.py:
prompt, allowed_values, value_labels and help must equal the
`frame_selection_question` block of sp-8-questions.json byte-for-byte, the
invented phrases must be gone, and a spec without the block must fail closed
with exit 3 ("frame question spec missing") rather than invent text.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
DEPT = SCRIPTS.parent
ROOT = DEPT.parents[3]
DRIVER = SCRIPTS / "deck-intake-driver.py"
SPEC = ROOT / "51-signature-presentation" / "intake" / "sp-8-questions.json"

QIDS = ("q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8")


def _env(tmp_path: Path) -> dict:
    env = dict(os.environ)
    env.update({
        "PRESENTATION_RESOURCE_PROFILE_DIR": str(tmp_path / "profile"),
        "PRESENTATION_CAPACITY_CONFIG_DIR": str(tmp_path / "profile"),
        "PRESENTATION_PROVIDER_PROBES": "0",
        "PRESENTATION_MODEL_FRESHNESS": "0",
        "PRESENTATION_SP_TURN_LEDGER_KEYS_FILE": "",
        "PRESENTATION_SP_TURN_LEDGER_CURRENT_KEY": "pd-016-test-key-material",
        "PRESENTATION_SP_TURN_LEDGER_CURRENT_KEY_ID": "pd-016-test-1",
        "PRESENTATION_SP_TURN_LEDGER_ROTATION_STARTED_AT": "2026-01-01T00:00:00+00:00",
    })
    return env


def _caller(driver: Path, run: Path):
    env = _env(run.parent)
    home = run.parent / "home"
    home.mkdir(exist_ok=True)
    env["HOME"] = str(home)

    def call(*args):
        return subprocess.run(
            [sys.executable, str(driver), "--run-dir", str(run), *args],
            capture_output=True, text=True, timeout=180, env=env)

    return call


def _answer_the_eight(call) -> None:
    out = call("--signature", "--sig-answer", "sp_mode", "QUICK")
    assert out.returncode == 0, out.stdout + out.stderr
    for qid in QIDS:
        out = call("--signature", "--sig-answer", qid, f"Client answer {qid}")
        assert out.returncode == 0, out.stdout + out.stderr


# ---------------------------------------------------------------------------
# A1 -- the emitted question is the spec's own wording, byte for byte
# ---------------------------------------------------------------------------
def test_a1_frame_question_is_the_spec_text(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    call = _caller(DRIVER, run)
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    frame_spec = spec["frame_selection_question"]

    _answer_the_eight(call)
    out = call("--signature", "--sig-next")
    assert out.returncode == 0, out.stdout + out.stderr
    payload = json.loads(out.stdout)

    assert payload["question_id"] == "signature_frame", out.stdout
    assert payload["prompt"] == frame_spec["prompt"], out.stdout
    assert payload["allowed_values"] == frame_spec["allowed_values"], out.stdout
    assert payload["value_labels"] == frame_spec["value_labels"], out.stdout
    assert payload["help"] == frame_spec["help"], out.stdout


def test_a1_invented_frame_phrases_are_gone():
    source = DRIVER.read_text(encoding="utf-8")
    for phrase in ("your methodology codified",
                   "your unique IP/proprietary system",
                   "the client's transformation journey"):
        assert phrase not in source


def test_frame_spec_missing_fails_closed_nonzero(tmp_path):
    dept = tmp_path / "dept"
    (dept / "scripts").mkdir(parents=True)
    (dept / "51-signature-presentation" / "intake").mkdir(parents=True)
    driver = dept / "scripts" / "deck-intake-driver.py"
    shutil.copyfile(DRIVER, driver)
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    spec.pop("frame_selection_question", None)
    (dept / "51-signature-presentation" / "intake" / "sp-8-questions.json") \
        .write_text(json.dumps(spec), encoding="utf-8")

    run = tmp_path / "run"
    run.mkdir()
    (tmp_path / "home").mkdir()
    call = _caller(driver, run)

    out = call("--signature", "--sig-answer", "sp_mode", "QUICK")
    assert out.returncode == 0, out.stdout + out.stderr
    for qid in QIDS[:-1]:
        out = call("--signature", "--sig-answer", qid, f"Client answer {qid}")
        assert out.returncode == 0, out.stdout + out.stderr
    # The q8 answer surfaces the frame question next, which must fail closed.
    out = call("--signature", "--sig-answer", "q8", "Client answer q8")
    assert out.returncode == 3, out.stdout + out.stderr
    assert "frame question spec missing" in out.stdout + out.stderr, out.stdout
