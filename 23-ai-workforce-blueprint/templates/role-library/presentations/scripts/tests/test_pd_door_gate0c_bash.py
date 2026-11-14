"""PD-033 — the door runs GATE 0c through bash, not by executing the file.

A1  A fixture drift-gate file with mode 0644 that exits 0: the door logs
    "GATE 0c PASSED". Before PD-033 the door executed the file directly, so a
    readable-but-not-executable gate died with "Permission denied" and the run
    was logged as drift (WARNING) instead of a pass.

Stub trees only. Nothing here touches a live box.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent  # .../presentations/scripts
_ENTRY_DEPLOYED = SCRIPTS / "presentation-canonical-entry.sh"
_ENTRY_REPO = SCRIPTS.parents[3] / "scripts" / "presentation-canonical-entry.sh"
ENTRY = _ENTRY_DEPLOYED if _ENTRY_DEPLOYED.is_file() else _ENTRY_REPO
assert ENTRY.is_file(), f"canonical entry script not found ({ENTRY})"

ENVELOPE = {
    "format": "sp-intake-transcript-v1",
    "driver_signature": "fixture-signed",
    "qid_sequence": ["q1", "q2"],
    "turns": [{"q": "What topic?", "a": "A long answer " * 20},
              {"q": "Who for?", "a": "A fixture audience"}],
}


def make_run_dir(base: Path) -> Path:
    run_dir = base / "run"
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    (run_dir / "working" / "interview").mkdir(parents=True)
    (run_dir / "working" / "interview" / "intake_ledger.json").write_text(
        json.dumps({"status": "complete", "complete": True}))
    (run_dir / "working" / "interview" / "intake_transcript.json").write_text(
        json.dumps(ENVELOPE))
    (run_dir / "slides.json").write_text("{}")
    return run_dir


def make_scripts_dir(base: Path) -> Path:
    d = base / "fake-scripts"
    d.mkdir(exist_ok=True)
    (d / "build_deck.py").write_text("import sys\nsys.exit(0)\n")
    (d / "run_signature_deck.py").write_text("import sys\nsys.exit(0)\n")
    (d / "ghl_media.py").write_text(
        "def upload_media(*a, **k): pass\n"
        "def list_media(*a, **k): return {'data': []}\n"
        "def create_media_folder(*a, **k): pass\n")
    (d / "sync_check.py").write_text(
        "import json, sys\n"
        "print(json.dumps({'in_sync': True, 'manifest_version': 39, 'drift': [],\n"
        "                  'drift_summary': {'total': 0, 'render_path': 0, 'library_only': 0}}))\n"
        "sys.exit(0)\n")
    return d


def make_door_dir(base: Path) -> Path:
    """A private copy of the door with a 0644 drift gate beside it."""
    door = base / "door"
    door.mkdir()
    shutil.copy2(ENTRY, door / "presentation-canonical-entry.sh")
    gate = door / "presentations-drift-gates.sh"
    gate.write_text("#!/bin/sh\n# fixture: no drift\nexit 0\n")
    os.chmod(gate, 0o644)
    return door


def test_a1_readable_gate_0644_runs_and_passes(tmp_path):
    run_dir = make_run_dir(tmp_path)
    scripts = make_scripts_dir(tmp_path)
    door = make_door_dir(tmp_path)
    gate = door / "presentations-drift-gates.sh"
    # The fixture must really be unreadable-by-exec: this row is about mode 0644.
    assert not os.access(gate, os.X_OK), "fixture gate is executable; the row would prove nothing"

    env = dict(os.environ)
    env["QC_SKIP_PRESENTATION_DEPS"] = "1"
    # PD-201b: the test seam is an environment name, not a marker file.
    env["PRESENTATION_ALLOW_DEGRADED_VERIFIERS"] = "1"
    env["OPENCLAW_WORKSPACE"] = str(tmp_path / "no-ws")
    r = subprocess.run(
        ["/bin/bash", str(door / "presentation-canonical-entry.sh"),
         "--run-dir", str(run_dir), "--scripts-dir", str(scripts), "--plan"],
        env=env, capture_output=True, text=True, timeout=120)

    assert "Permission denied" not in (r.stdout + r.stderr), (
        f"the door executed the 0644 gate directly\nstdout:{r.stdout}\nstderr:{r.stderr}")
    assert "GATE 0c PASSED" in r.stdout, (
        f"a 0644 gate that exits 0 was not logged as PASSED\n"
        f"stdout:{r.stdout}\nstderr:{r.stderr}")
