#!/usr/bin/env python3
"""PD-011 -- --complete fails loudly when the transcript cannot be signed.

Acceptance rows A1 and A2 of unit PD-011 (01-BUILD-SPEC.md, lane FL02).
Driven at the subprocess level against the REAL deck-intake-driver.py; no
renderer, no network, no live service, no paid call. Every case runs in a
temporary run folder.

A1 builds a MINIMAL department (the driver plus the intake question bank and
nothing else) with HOME pointed at an empty folder, so Skill 51's
intake_trace_check.py is on none of the driver's search paths while the intake
walk itself still works -- that is what "Skill 51 hidden" means here.
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
DRIVER = SCRIPTS / "deck-intake-driver.py"
INTAKE = DEPT / "intake"

LEDGER = Path("working") / "interview" / "intake_ledger.json"
TRANSCRIPT = Path("working") / "interview" / "intake_transcript.json"


def _env(tmp_path: Path) -> dict:
    """Isolated profile/capacity dirs, no provider probes, no paid call."""
    env = dict(os.environ)
    env.update({
        # PD-004c: this suite proves --complete signing, not provenance.
        "PRESENTATION_INTAKE_PROVENANCE": "warn",
        "PRESENTATION_RESOURCE_PROFILE_DIR": str(tmp_path / "profile"),
        "PRESENTATION_CAPACITY_CONFIG_DIR": str(tmp_path / "profile"),
        "PRESENTATION_PROVIDER_PROBES": "0",
        "PRESENTATION_MODEL_FRESHNESS": "0",
    })
    return env


def _caller(driver: Path, run: Path, env: dict):
    def call(*args):
        return subprocess.run(
            [sys.executable, str(driver), "--run-dir", str(run), *args],
            capture_output=True, text=True, timeout=180, env=env)
    return call


def _ledger(run: Path) -> dict:
    return json.loads((run / LEDGER).read_text(encoding="utf-8"))


def _walk_to_complete(call) -> None:
    """PD-913: --complete refuses an interview the turn gate has not finished,
    so a fixture that wants a finished intake answers the gate's own pending
    turns first. SETUP ONLY -- it reuses the live gate (--next) and makes no
    claim about the product; the test's own assertions decide pass/fail."""
    for _ in range(120):
        q = json.loads(call("--next").stdout or "{}")
        if q.get("status") == "complete":
            return
        qid = q.get("question_id")
        if not qid:
            return
        vals = q.get("allowed_values") or []
        if qid == "pitch_included" and "no" in vals:
            # SETUP: an informational deck. The commercial turns are then not
            # asked at all, so a fixture about some OTHER behaviour does not
            # have to supply commercial values it never asserts on.
            answer = "no"
        elif qid in ("workhorse_model", "reasoning_model", "qc_model",
                     "deepseek_variant", "openrouter_model", "provider_plan",
                     "thinking_mode", "ollama_plan"):
            answer = ""       # the client's wired provider is not probed here
        elif vals:
            answer = vals[0]
        elif q.get("kind") == "integer":
            answer = "20"
        else:
            answer = "Client supplied " + qid
        call("--answer", qid, answer)


# ---------------------------------------------------------------------------
# A1 -- Skill 51 hidden: --complete exits 5, ledger unchanged, no transcript
# ---------------------------------------------------------------------------
def test_a1_missing_skill51_blocks_complete(tmp_path):
    dept = tmp_path / "dept"
    (dept / "scripts").mkdir(parents=True)
    driver = dept / "scripts" / "deck-intake-driver.py"
    shutil.copyfile(DRIVER, driver)
    shutil.copytree(INTAKE, dept / "intake")
    home = tmp_path / "home"
    home.mkdir()

    run = tmp_path / "run"
    run.mkdir()
    env = _env(tmp_path)
    env["HOME"] = str(home)
    call = _caller(driver, run, env)

    answered = call("--answer", "presentation_type", "from_scratch")
    assert answered.returncode == 0, answered.stdout + answered.stderr
    assert (run / LEDGER).is_file(), "the intake walk never recorded a ledger"
    assert _ledger(run).get("status") != "complete"
    _walk_to_complete(call)

    out = call("--complete")
    assert out.returncode == 5, out.stdout + out.stderr
    payload = json.loads(out.stdout)
    assert payload["status"] == "blocked", out.stdout
    assert "was not found" in payload["error"], out.stdout
    assert "intake_trace_check.py" in payload["error"], out.stdout
    # The refusal NAMES every path it tried -- the operator never has to guess.
    assert payload["searched"], out.stdout
    assert all(p.endswith("intake_trace_check.py")
               for p in payload["searched"]), payload["searched"]

    ledger = _ledger(run)
    assert ledger.get("status") != "complete"
    assert ledger.get("complete") is not True
    assert not (run / TRANSCRIPT).exists(), \
        "a blocked --complete still wrote intake_transcript.json"


# ---------------------------------------------------------------------------
# A2 -- Skill 51 present: --complete exits 0 and the transcript is a real
#       signed driver envelope
# ---------------------------------------------------------------------------
def test_a2_present_skill51_signs_complete(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    env = _env(tmp_path)
    call = _caller(DRIVER, run, env)

    answered = call("--answer", "presentation_type", "from_scratch")
    assert answered.returncode == 0, answered.stdout + answered.stderr
    _walk_to_complete(call)

    out = call("--complete")
    assert out.returncode == 0, out.stdout + out.stderr
    payload = json.loads(out.stdout)
    assert payload["status"] == "complete", out.stdout
    assert payload["intake_transcript_signed"] is True, out.stdout
    assert _ledger(run).get("status") == "complete"

    envelope = json.loads((run / TRANSCRIPT).read_text(encoding="utf-8"))
    for key in ("format", "qid_sequence", "turns", "driver_signature"):
        assert key in envelope, f"envelope is missing {key}: {sorted(envelope)}"
    assert envelope["format"] == "sp-intake-transcript-v1"
    assert envelope["turns"], "the envelope carries no turns"
