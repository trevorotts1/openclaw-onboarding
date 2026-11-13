#!/usr/bin/env python3
"""PD-001 -- the signature intake always asks the 8 questions; no false success.

Acceptance rows A1-A7 of unit PD-001 (01-BUILD-SPEC.md, lane FL02, Critical
finding PD-001, decision D-7 default). Driven at the subprocess level against
the REAL deck-intake-driver.py; no renderer, no network, no live service, no
paid call. Every case runs in a temporary run folder.

A4 builds a MINIMAL department (the driver plus the pinned spec and nothing
else) so Skill 51's prover is on none of the driver's search paths while the
walk itself still works -- that is what "hide the prover" means here.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
DEPT = SCRIPTS.parent
ROOT = DEPT.parents[3]
DRIVER = SCRIPTS / "deck-intake-driver.py"
SPEC = ROOT / "51-signature-presentation" / "intake" / "sp-8-questions.json"

QIDS = ("q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8")
LEDGER = Path("working") / "interview" / "intake_ledger.json"
SP_INTAKE = Path("working") / "copy" / "sp_intake.json"


def _env(tmp_path: Path) -> dict:
    """Isolated profile/capacity dirs plus a THROWAWAY per-process turn-ledger
    key (never the box's provisioned record, never a real key): --sig-finalize
    signs the turn ledger for every signature record that carries the eight
    answers."""
    env = dict(os.environ)
    env.update({
        "PRESENTATION_RESOURCE_PROFILE_DIR": str(tmp_path / "profile"),
        "PRESENTATION_CAPACITY_CONFIG_DIR": str(tmp_path / "profile"),
        "PRESENTATION_PROVIDER_PROBES": "0",
        "PRESENTATION_MODEL_FRESHNESS": "0",
        "PRESENTATION_SP_TURN_LEDGER_KEYS_FILE": "",
        "PRESENTATION_SP_TURN_LEDGER_CURRENT_KEY": "pd-001-test-key-material",
        "PRESENTATION_SP_TURN_LEDGER_CURRENT_KEY_ID": "pd-001-test-1",
        "PRESENTATION_SP_TURN_LEDGER_ROTATION_STARTED_AT": "2026-01-01T00:00:00+00:00",
    })
    return env


@pytest.fixture
def sig(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    env = _env(tmp_path)

    def call(*args):
        return subprocess.run(
            [sys.executable, str(DRIVER), "--run-dir", str(run), *args],
            capture_output=True, text=True, timeout=180, env=env)

    return run, call


def _answer_the_eight(call, confirm: bool):
    """sp_mode first, then q1..q8 one at a time (rc 0 each); optionally
    confirm each answer quote-back, exactly as a client conversation would."""
    out = call("--signature", "--sig-answer", "sp_mode", "QUICK")
    assert out.returncode == 0, out.stdout + out.stderr
    for n, qid in enumerate(QIDS, 1):
        out = call("--signature", "--sig-answer", qid, f"Client answer {n}")
        assert out.returncode == 0, out.stdout + out.stderr
        if confirm:
            confirmed = call("--signature", "--sig-confirm", qid, "--sig-confirmed")
            assert confirmed.returncode == 0, confirmed.stdout + confirmed.stderr
    return out


def _ledger(run: Path) -> dict:
    return json.loads((run / LEDGER).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# A1 -- QUICK asks the eight questions, starting at q1
# ---------------------------------------------------------------------------
def test_a1_quick_mode_asks_q1_next(sig):
    _run, call = sig
    out = call("--signature", "--sig-answer", "sp_mode", "QUICK")
    assert out.returncode == 0, out.stdout + out.stderr
    payload = json.loads(out.stdout)
    assert payload["question_id"] == "q1", out.stdout


# ---------------------------------------------------------------------------
# A2 -- an unfinished interview never writes sp_intake.json (exit 3)
# ---------------------------------------------------------------------------
def test_a2_incomplete_interview_exits_3_and_writes_no_record(sig):
    run, call = sig
    # The eight required answers are EMPTY (the frame is the only real
    # answer): the walk reaches --sig-finalize, which must refuse.
    out = call("--signature", "--sig-answer", "sp_mode", "QUICK")
    assert out.returncode == 0, out.stdout + out.stderr
    for qid in QIDS:
        out = call("--signature", "--sig-answer", qid, "")
        assert out.returncode == 0, out.stdout + out.stderr
    call("--signature", "--sig-answer", "signature_frame", "vault")

    out = call("--signature", "--sig-next")
    assert out.returncode == 3, out.stdout + out.stderr
    payload = json.loads(out.stdout)
    assert payload["status"] == "incomplete", out.stdout
    assert payload["missing"] == list(QIDS), out.stdout
    assert not (run / SP_INTAKE).exists(), "an unfinished interview wrote sp_intake.json"
    assert _ledger(run).get("status") != "complete"


# ---------------------------------------------------------------------------
# A3 -- unconfirmed answers are needs_attention (exit 4), ledger not complete
# ---------------------------------------------------------------------------
def test_a3_unconfirmed_answers_are_needs_attention(sig):
    run, call = sig
    _answer_the_eight(call, confirm=False)
    out = call("--signature", "--sig-answer", "signature_frame", "vault")
    assert out.returncode == 4, out.stdout + out.stderr
    payload = json.loads(out.stdout)
    assert payload["status"] == "needs_attention", out.stdout
    assert sorted(payload["unconfirmed_answers"]) == list(QIDS), out.stdout
    ledger = _ledger(run)
    assert ledger.get("status") != "complete"
    assert ledger.get("complete") is not True


# ---------------------------------------------------------------------------
# A4 -- a hidden prover is reported as not_run (exit 4), never as a pass
# ---------------------------------------------------------------------------
def test_a4_missing_prover_is_not_run(tmp_path):
    dept = tmp_path / "dept"
    (dept / "scripts").mkdir(parents=True)
    (dept / "51-signature-presentation" / "intake").mkdir(parents=True)
    driver = dept / "scripts" / "deck-intake-driver.py"
    shutil.copyfile(DRIVER, driver)
    shutil.copyfile(SPEC, dept / "51-signature-presentation" / "intake"
                    / "sp-8-questions.json")

    run = tmp_path / "run"
    run.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    env = _env(tmp_path)
    env["HOME"] = str(home)

    def call(*args):
        return subprocess.run(
            [sys.executable, str(driver), "--run-dir", str(run), *args],
            capture_output=True, text=True, timeout=180, env=env)

    _answer_the_eight(call, confirm=True)
    out = call("--signature", "--sig-answer", "signature_frame", "vault")
    assert out.returncode == 4, out.stdout + out.stderr
    payload = json.loads(out.stdout)
    assert payload["prover"] == "not_run", out.stdout
    assert payload["status"] == "needs_attention", out.stdout


# ---------------------------------------------------------------------------
# A5 -- a full confirmed run completes, with the prover actually passing
# ---------------------------------------------------------------------------
def test_a5_full_confirmed_run_completes(sig):
    run, call = sig
    _answer_the_eight(call, confirm=True)
    out = call("--signature", "--sig-answer", "signature_frame", "vault")
    assert out.returncode == 0, out.stdout + out.stderr
    payload = json.loads(out.stdout)
    assert payload["status"] == "complete", out.stdout
    assert payload["prover"] == "passed", out.stdout
    assert payload["prover_failures"] == [], out.stdout
    assert (run / SP_INTAKE).is_file()
    assert _ledger(run).get("status") == "complete"


# ---------------------------------------------------------------------------
# A6 -- the hard-coded success sentence is gone from the driver
# ---------------------------------------------------------------------------
def test_a6_hard_coded_success_sentence_is_gone():
    source = DRIVER.read_text(encoding="utf-8")
    assert "SP intake prover passed" not in source


# ---------------------------------------------------------------------------
# A7 -- the driver's own offline self-test still passes
# ---------------------------------------------------------------------------
def test_a7_selftest_exits_0(sig):
    _run, call = sig
    out = call("--selftest")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "ALL PASS" in out.stdout, out.stdout
